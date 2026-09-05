"""Integration checks against isolated SQLite state and mocked bank responses."""
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from email.message import Message
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import db, server, analytics, plaid_client, subscriptions, cancellations, auth, scheduler

class IntegratedLedger(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=(db.DATA_DIR,db.DB_PATH,db.CONFIG_PATH)
        db.DATA_DIR=self.tmp.name; db.DB_PATH=self.tmp.name+'/ledger.db'; db.CONFIG_PATH=self.tmp.name+'/config.json'
        db.init_db(); subscriptions.init_schema(); cancellations.init_schema(); auth.init_schema(); scheduler.init_schema()
        self.account('cash',100)
    def tearDown(self):
        db.DATA_DIR,db.DB_PATH,db.CONFIG_PATH=self.old
        self.tmp.cleanup()
    def account(self,aid,balance=0,item=None,plaid=None):
        db.ex("INSERT INTO accounts(id,item_id,name,type,scope,balance,plaid_account_id,created_at) VALUES(?,?,?,'depository','personal',?,?,?)",(aid,item,aid,balance,plaid,'2026-01-01'))
    def request(self,path,body=None,method=None,headers=None,demomode=True):
        h=object.__new__(server.Handler); h.path=path; h.client_address=('127.0.0.1',1)
        h.headers=Message(); h.headers['Host']='127.0.0.1:8907'; h.headers['X-Ledger-Request']='1'
        h.headers['Content-Type']='application/json'
        raw=json.dumps(body).encode() if body is not None else b''
        h.headers['Content-Length']=str(len(raw))
        for k,v in (headers or {}).items():
            if k in h.headers: del h.headers[k]
            h.headers[k]=v
        h.rfile=io.BytesIO(raw); result={}
        def send(code,payload,ctype='application/json'):
            result.update(code=code,body=json.loads(payload) if ctype=='application/json' else payload,cookie=getattr(h,'auth_cookie',''))
        h._send=send
        with patch.object(server,'DEMO',demomode), patch.object(server,'PUBLIC_ORIGIN',''):
            h._dispatch(method or ('POST' if body is not None else 'GET'))
        return result
    def test_auth_guard_setup_login_logout_and_origin(self):
        self.assertEqual(self.request('/api/accounts',demomode=False)['code'],401)
        self.assertEqual(self.request('/api/auth/setup',{'password':'sample test password long'},headers={'Origin':'https://hostile.example'},demomode=False)['code'],403)
        result=self.request('/api/auth/setup',{'password':'sample test password long'},demomode=False)
        self.assertEqual(result['code'],200)
        cookie=result['cookie'].split(';')[0]
        self.assertIn('HttpOnly',result['cookie']);self.assertIn('SameSite=Strict',result['cookie'])
        self.assertEqual(self.request('/api/accounts',headers={'Cookie':cookie},demomode=False)['code'],200)
        self.request('/api/auth/logout',{},headers={'Cookie':cookie},demomode=False)
        self.assertEqual(self.request('/api/accounts',headers={'Cookie':cookie},demomode=False)['code'],401)
    def test_rejected_body_cannot_corrupt_next_proxy_request(self):
        import http.client
        import threading
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        client = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=3)
        try:
            client.request('POST', '/api/auth/setup', body='{}', headers={'Content-Type': 'application/json'})
            denied = client.getresponse()
            self.assertEqual(denied.status, 403)
            self.assertEqual(denied.getheader('Connection'), 'close')
            denied.read()
            client.request('GET', '/api/health')
            healthy = client.getresponse()
            self.assertEqual(healthy.status, 200)
            self.assertTrue(json.loads(healthy.read())['ok'])
        finally:
            client.close()
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)
    def test_manual_entry_balance_reports_and_atomic_failure(self):
        result=self.request('/api/transactions',{'transaction':{'account_id':'cash','name':'Test coffee','amount':-5,'posted':date.today().isoformat()}})
        self.assertEqual(result['code'],200,result)
        self.assertEqual(db.q1('SELECT balance FROM accounts WHERE id="cash"')['balance'],95)
        self.assertEqual(analytics.overview()['spend_this_month'],5)
        self.request('/api/transactions',{'transaction':{'account_id':'cash','name':'Transfer','amount':-20,'is_transfer':True}})
        self.assertEqual(analytics.overview()['spend_this_month'],5)
        count=len(db.q('SELECT * FROM transactions'))
        bad=self.request('/api/transactions',{'transaction':{'account_id':'cash','name':'Invalid','amount':-30,'category_id':'missing'}})
        self.assertEqual(bad['code'],400)
        self.assertEqual(len(db.q('SELECT * FROM transactions')),count)
        self.assertEqual(db.q1('SELECT balance FROM accounts WHERE id="cash"')['balance'],75)
        self.request('/api/transactions?id='+result['body']['id'],method='DELETE')
        self.assertEqual(db.q1('SELECT balance FROM accounts WHERE id="cash"')['balance'],80)
    def test_config_redaction_and_demo_action_boundaries(self):
        saved=self.request('/api/config',{'plaid_client_id':'fake-client','plaid_secret':'fake-secret','theme':'light'})
        self.assertEqual(saved['code'],200);self.assertNotIn('fake-secret',str(saved));self.assertTrue(saved['body']['plaid_configured'])
        self.request('/api/config',{'theme':'dark','plaid_secret':''})
        self.assertEqual(db.get_config()['plaid_secret'],'fake-secret')
        for path in ['/api/plaid/link-token','/api/plaid/exchange','/api/plaid/sandbox-token','/api/plaid/sandbox-full-link','/api/cancellations/request']:
            self.assertEqual(self.request(path,{})['code'],400,path)
        self.assertEqual(self.request('/api/config',{'theme':'other'})['code'],400)
        self.assertEqual(self.request('/%2e%2e/backend/db.py')['code'],404)
        self.assertEqual(self.request('/api/health',headers={'Host':'hostile.example'})['code'],403)
    def test_reports_include_month_end_exclude_pending_transfers(self):
        for tid,posted,amount,pending,transfer in [('end','2026-08-31',-11,0,0),('pending','2026-08-30',-40,1,0),('transfer','2026-08-30',-60,0,1),('income','2026-08-31',20,0,0)]:
            db.ex('INSERT INTO transactions(id,account_id,scope,amount,posted,name,category_id,pending,is_transfer,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(tid,'cash','personal',amount,posted,tid,'cat-groceries',pending,transfer,posted))
        with patch.object(analytics,'month_list',return_value=[(2026,8)]):
            self.assertEqual(analytics.cashflow_series()[0]['spend'],11)
            self.assertEqual(analytics.monthly_matrix()['series']['Groceries']['2026-08'],11)
        self.assertEqual(analytics.heatmap_data()['2026-08-31'],11)
        self.assertNotIn('2026-08-30',analytics.heatmap_data())
    def test_goals_require_matching_active_account_and_account_changes_exist(self):
        for path in ('/api/accounts/archive', '/api/accounts/classify'):
            self.assertEqual(self.request(path, {'id':'missing', 'scope':'personal'})['code'],404)
        goal={'name':'Trip','target':500,'scope':'business','account_id':'cash'}
        self.assertEqual(self.request('/api/goals',goal)['code'],400)
        goal['scope']='personal'
        self.request('/api/accounts/archive',{'id':'cash'})
        self.assertEqual(self.request('/api/goals',goal)['code'],400)
        self.request('/api/accounts/archive',{'id':'cash','restore':True})
        self.assertEqual(self.request('/api/goals',goal)['code'],200)
        self.assertEqual(len(db.q('SELECT * FROM goals')),1)

    def test_account_default_changes_preserve_manual_transaction_scope(self):
        for tid, override in [('inherited', None), ('manual', 'personal')]:
            db.ex("INSERT INTO transactions(id,account_id,scope,scope_override,amount,posted,name,created_at) VALUES(?,?,'personal',?,-10,'2026-09-01','Synthetic','2026-09-01')", (tid, 'cash', override))
        with patch.object(server.receipt_store, 'invalidate_transaction') as invalidate:
            response = self.request('/api/accounts/classify', {'id': 'cash', 'scope': 'business'})
            self.assertEqual(response['code'], 200)
            self.assertEqual([call.args[0] for call in invalidate.call_args_list], ['inherited'])
        self.assertEqual(db.q1("SELECT scope,scope_override FROM transactions WHERE id='manual'"), {'scope':'personal','scope_override':'personal'})
        self.assertEqual(db.q1("SELECT scope FROM transactions WHERE id='inherited'")['scope'], 'business')
        with patch.object(server.receipt_store, 'invalidate_transaction') as invalidate:
            response = self.request('/api/accounts/manual', {'id':'cash','name':'Cash','balance':200,'scope':'business'})
            self.assertEqual(response['code'], 200)
            invalidate.assert_not_called()
        self.assertEqual(db.q1("SELECT scope_override FROM transactions WHERE id='manual'")['scope_override'], 'personal')

    def test_exchange_preserves_existing_item_reference_and_starts_sync(self):
        with patch.object(plaid_client,'ingest_item',return_value=('bank',[])) as ingest, patch.object(server.threading,'Thread') as background:
            # Dispatch seam only: the public guard is independently tested above.
            h=object.__new__(server.Handler); response={}; h._json=lambda code,body:response.update(code=code,body=body)
            with patch.object(server,'DEMO',False):
                h._api_post('/api/plaid/exchange',{'public_token':'fake','item_id':'bank'})
            self.assertEqual(ingest.call_args.kwargs['existing_item_id'],'bank')
            background.return_value.start.assert_called_once()
            self.assertEqual(response['code'],200)

    def test_plaid_pagination_restart_and_cursor(self):
        mutation=plaid_client.PlaidError('retry','TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION')
        pages=[{'added':[{'id':'stale'}],'next_cursor':'mid','has_more':True},mutation,{'added':[{'id':'one'}],'next_cursor':'m2','has_more':True},{'modified':[{'id':'two'}],'removed':[{'transaction_id':'old'}],'next_cursor':'done','has_more':False}]
        with patch.object(plaid_client,'_post',side_effect=pages) as mock:
            r=plaid_client.sync_transactions({'access_token':'fake-token','env':'sandbox','cursor':'start'})
        self.assertEqual(r['cursor'],'done');self.assertEqual(r['added'],[{'id':'one'}]);self.assertEqual(mock.call_args_list[2].args[1]['cursor'],'start')
    def test_plaid_pending_replacement_modifications_removed_new_accounts(self):
        db.ex('INSERT INTO items(id,institution,env,access_token,cursor,created_at) VALUES(?,?,?,?,?,?)',('bank','Test','sandbox','fake-token','before','2026-01-01'))
        self.account('linked',0,'bank','p1')
        db.ex('INSERT INTO transactions(id,account_id,scope,amount,posted,name,pending,plaid_transaction_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',('pending','linked','personal',-10,'2026-09-01','Coffee',1,'pending1','2026-09-01'))
        tx={'transaction_id':'posted1','pending_transaction_id':'pending1','account_id':'p1','amount':12,'date':'2026-09-02','name':'Coffee','personal_finance_category':{'primary':'FOOD_AND_DRINK'}}
        meta={'accounts':[{'account_id':'p1','type':'depository','balances':{'current':500}},{'account_id':'p2','name':'New card','type':'credit','balances':{'current':200}}]}
        changes={'added':[tx,dict(tx,transaction_id='posted2',account_id='p2',amount=20)],'modified':[],'removed':[],'cursor':'after'}
        with patch.object(plaid_client,'sync_transactions',return_value=changes),patch.object(plaid_client,'fetch_accounts',return_value=meta):
            plaid_client.refresh_item('bank')
        self.assertEqual(len(db.q('SELECT * FROM transactions')),2)
        self.assertEqual(db.q1('SELECT balance FROM accounts WHERE plaid_account_id="p2"')['balance'],-200)
        self.assertEqual(db.q1('SELECT cursor FROM items')['cursor'],'after')
        db.ex('UPDATE transactions SET note="keep",category_id="cat-shopping" WHERE plaid_transaction_id="posted1"')
        changed={'added':[],'modified':[dict(tx,amount=15)],'removed':[{'transaction_id':'posted2'}],'cursor':'last'}
        with patch.object(plaid_client,'sync_transactions',return_value=changed),patch.object(plaid_client,'fetch_accounts',return_value=meta):plaid_client.refresh_item('bank')
        row=db.q1('SELECT * FROM transactions');self.assertEqual((row['amount'],row['note'],row['category_id']),(-15,'keep','cat-shopping'))
        bad={'added':[dict(tx,transaction_id='bad',account_id='unknown')],'modified':[],'removed':[],'cursor':'badcursor'}
        with patch.object(plaid_client,'sync_transactions',return_value=bad),patch.object(plaid_client,'fetch_accounts',return_value=meta):
            with self.assertRaises(plaid_client.PlaidError):plaid_client.refresh_item('bank')
        self.assertEqual(db.q1('SELECT cursor FROM items')['cursor'],'last')

if __name__=='__main__':unittest.main()

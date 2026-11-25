"""Reviewed category batches cannot cross scopes or silently expand after preview."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, os.environ.get('LEDGER_TEST_BACKEND', '/app/backend'))
import db, category_rules as rules, category_picker, receipt_store, server, subscriptions, plaid_client


class CategoryRulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctx = db.isolated_data(self.tmp.name)
        self.ctx.__enter__()
        db.init_db(); receipt_store.init_schema(); rules.init_schema(); subscriptions.init_schema()
        for aid, scope, archived in [('p','personal',0),('b','business',0),('old','personal',1)]:
            db.ex("INSERT INTO accounts(id,name,scope,archived,balance,created_at) VALUES(?,?,?,?,100,'2026-09-01')", (aid,aid,scope,archived))
        self.tx('anchor', category='cat-dining')
        self.tx('match',category='cat-shopping',override=1)
        self.tx('biz',account='b',scope='business')
        self.tx('archived',account='old')
        self.tx('refund',amount=10)
        self.tx('transfer',transfer=1)
        self.tx('different',name='Cafe Two')
        self.tx('same',category='cat-dining')
        self.tx('renamed',name='Special gift',merchant='Cafe One',name_override=1)

    def tearDown(self):
        self.ctx.__exit__(None,None,None); self.tmp.cleanup()

    def tx(self, tid, account='p',scope='personal',name='Cafe One',merchant=None,category=None,amount=-12,override=None,transfer=0,name_override=None):
        db.ex('''INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,created_at,category_override,is_transfer,name_override)
            VALUES(?,?,?,?,'2026-09-01',?,?,?,'2026-09-01',?,?,?)''', (tid,account,scope,amount,name,merchant or name,category,override,transfer,name_override))

    def test_preview_exact_list_and_future_rule_and_undo(self):
        p=rules.preview('anchor','cat-dining')
        self.assertEqual([t['id'] for t in p['transactions']],['match'])
        self.assertEqual(p['transactions'][0]['category_name'],'Shopping')
        self.tx('arrived-after-preview')
        result=rules.apply(p['preview_id'],True)
        self.assertEqual(result['changed'],1)
        self.assertIsNone(db.q1("SELECT category_id FROM transactions WHERE id='arrived-after-preview'")['category_id'])
        self.assertEqual(rules.match({'name':'  CAFE  ONE  ','scope':'personal','amount':-2})['category_id'],'cat-dining')
        self.assertIsNone(rules.match({'name':'Cafe One','scope':'business','amount':-2}))
        self.assertIsNone(rules.match({'name':'Cafe One','scope':'personal','amount':-2,'category_override':1}))
        with self.assertRaises(ValueError): rules.apply(p['preview_id'])
        self.assertEqual(rules.undo(result['batch_id'])['restored'],1)
        self.assertEqual(db.q1("SELECT category_id,category_override FROM transactions WHERE id='match'"),{'category_id':'cat-shopping','category_override':1})
        self.assertIsNone(rules.match({'name':'Cafe One','scope':'personal','amount':-2}))

    def test_changed_preview_refuses_entire_batch(self):
        self.tx('second-match')
        p=rules.preview('anchor','cat-dining')
        db.ex("UPDATE transactions SET scope='business' WHERE id='match'")
        with self.assertRaisesRegex(ValueError,'changed'):rules.apply(p['preview_id'],True)
        self.assertIsNone(db.q1("SELECT category_id FROM transactions WHERE id='second-match'")['category_id'])
        self.assertEqual(db.q('SELECT * FROM transaction_category_rules'),[])

    def test_split_is_visible_as_skipped_and_undo_preserves_new_manual_edit(self):
        db.ex("INSERT INTO receipt_jobs(id,transaction_id,provider,status,created_at,updated_at) VALUES('job','match','amazon','applied','today','today')")
        db.ex("INSERT INTO receipt_allocations(id,job_id,transaction_id,line_key,description,amount_cents,category_id,confidence,active,created_at,updated_at) VALUES('split','job','match','1','Item',1200,'cat-shopping',1,1,'today','today')")
        p=rules.preview('anchor','cat-dining')
        self.assertEqual((p['count'],p['skipped_splits']),(0,1))
        db.ex("UPDATE receipt_allocations SET active=0")
        result=rules.apply(rules.preview('anchor','cat-dining')['preview_id'])
        receipt_store.manual_update('match',{'category_id':'cat-groceries'})
        self.assertEqual(rules.undo(result['batch_id'])['skipped'],1)

    def test_route_manual_entry_learns_rule_and_uses_account_scope(self):
        rules.apply(rules.preview('anchor','cat-dining')['preview_id'],True)
        h=object.__new__(server.Handler);h._json=lambda code,body:(code,body)
        with patch.object(server,'_scan_safely'):
            code,body=h._api_post('/api/transactions',{'transaction':{'account_id':'p','name':'Cafe One','scope':'business','amount':-6}})
        self.assertEqual(code,200)
        self.assertEqual(db.q1('SELECT category_id,category_override,scope FROM transactions WHERE id=?',(body['id'],)),{'category_id':'cat-dining','category_override':0,'scope':'personal'})

    def test_category_only_edit_does_not_override_account_scope(self):
        receipt_store.manual_update('match',{'category_id':'cat-groceries','note':'category correction'})
        c=db._conn()
        try:
            with c:server._scope_account(c,'p','business')
        finally:c.close()
        self.assertEqual(db.q1("SELECT scope,scope_override FROM transactions WHERE id='match'"),{'scope':'business','scope_override':None})

    def test_rules_validate_target_and_expiry(self):
        for anchor,category in [('refund','cat-dining'),('transfer','cat-dining'),('anchor','cat-income'),('anchor','missing')]:
            with self.assertRaises(ValueError):rules.preview(anchor,category)
        p=rules.preview('anchor','cat-dining')
        db.ex('UPDATE category_edit_previews SET expires_at=0')
        with self.assertRaisesRegex(ValueError,'expired'):rules.apply(p['preview_id'])

    def test_bank_sync_uses_saved_rule_and_leaves_manual_override(self):
        rules.apply(rules.preview('anchor','cat-dining')['preview_id'],True)
        db.ex("INSERT INTO items(id,institution,env,access_token,created_at) VALUES('bank','Example','sandbox','fake-test-token','today')")
        db.ex("UPDATE accounts SET item_id='bank',plaid_account_id='provider-p' WHERE id='p'")
        def sync():
            row={'transaction_id':'new-bank','account_id':'provider-p','amount':5,'date':'2026-09-01','name':'Cafe One','merchant_name':'Cafe One','personal_finance_category':{'primary':'GENERAL_MERCHANDISE'}}
            with patch.object(plaid_client,'sync_transactions',return_value={'added':[row],'modified':[],'removed':[],'cursor':'end'}),patch.object(plaid_client,'fetch_accounts',return_value={'accounts':[{'account_id':'provider-p','name':'p','balances':{'current':100}}]}):
                plaid_client.refresh_item('bank')
        sync()
        row=db.q1("SELECT * FROM transactions WHERE plaid_transaction_id='new-bank'")
        self.assertEqual(row['category_id'],'cat-dining')
        receipt_store.manual_update(row['id'],{'category_id':'cat-groceries'})
        sync()
        self.assertEqual(db.q1('SELECT category_id FROM transactions WHERE id=?',(row['id'],))['category_id'],'cat-groceries')


if __name__=='__main__':unittest.main()

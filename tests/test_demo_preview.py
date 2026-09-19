"""Demo privacy boundary, real calculations and authentication regression checks."""
import io
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from email.message import Message
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import auth
import db
import demo_preview
import server


class DemoPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH
        db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH = self.tmp.name, self.tmp.name+'/ledger.db', self.tmp.name+'/config.json'
        db.init_db()
        auth.init_schema()
        db.ex("INSERT INTO accounts(id,name,type,scope,balance,created_at) VALUES('private-account','PRIVATE SENTINEL','depository','personal',987654.32,'2026-01-01')")
        db.save_config({'owner_name': 'PRIVATE OWNER', 'plaid_secret': 'PRIVATE SECRET', 'monthly_spending_target': 99999})
        self.cookie = 'ledger_session=' + auth.setup('fictional test password only')
        self.before = db.q('SELECT * FROM accounts'), db.get_config()

    def tearDown(self):
        db.DATA_DIR, db.DB_PATH, db.CONFIG_PATH = self.old
        self.tmp.cleanup()

    def request(self, route, method='GET', body=None, signed_in=True):
        handler = object.__new__(server.Handler)
        handler.path = route
        handler.client_address = ('127.0.0.1', 1)
        handler.headers = Message()
        for name, value in {'Host':'localhost:8907', 'Content-Type':'application/json',
                            'X-Ledger-Request':'1', 'Cookie':self.cookie if signed_in else ''}.items():
            handler.headers[name] = value
        raw = json.dumps(body or {}).encode() if method == 'POST' else b''
        handler.headers['Content-Length'] = str(len(raw))
        handler.rfile = io.BytesIO(raw)
        result = {}
        def send(status, payload, ctype='application/json'):
            result.update(status=status, data=json.loads(payload) if ctype == 'application/json' else payload.decode())
        handler._send = send
        with patch.object(server, 'DEMO', False), patch.object(server, 'PUBLIC_ORIGIN', ''):
            handler._dispatch(method)
        return result

    def assertLiveUnchanged(self):
        self.assertEqual(self.before, (db.q('SELECT * FROM accounts'), db.get_config()))
        self.assertEqual(db.q1('SELECT COUNT(*) n FROM transactions')['n'], 0)

    def test_all_demo_reads_exclude_private_data(self):
        for route in sorted(demo_preview.READ_PATHS - {'/receipts/transaction'}):
            with self.subTest(route=route):
                result = self.request('/api/preview' + route)
                self.assertEqual(result['status'], 200, result)
                self.assertNotIn('PRIVATE', str(result))
                self.assertNotIn('987654', str(result))
        self.assertLiveUnchanged()
        self.assertEqual(self.request('/api/accounts')['data'][0]['name'], 'PRIVATE SENTINEL')

    def test_writes_and_unknown_routes_fail_closed(self):
        paths = set(demo_preview.READ_PATHS) | {'/data/reset', '/demo/seed', '/sync', '/accounts/manual',
            '/plaid/link-token', '/plaid/exchange', '/items/refresh', '/cancellations/request',
            '/receipts/request', '/receipts/settings', '/auth/setup', '/new-future-feature'}
        for method in ('POST', 'DELETE'):
            for route in paths:
                with self.subTest(method=method, route=route):
                    self.assertEqual(self.request('/api/preview'+route, method, {'force':True})['status'], 403)
        self.assertEqual(self.request('/api/preview/new-future-feature')['status'], 403)
        self.assertLiveUnchanged()

    def test_demo_keeps_owner_authentication_and_origin_guard(self):
        for route in ('/api/accounts', '/api/preview/accounts', '/api/preview/config', '/api/preview/export/transactions.csv'):
            self.assertEqual(self.request(route, signed_in=False)['status'], 401)

    def test_filters_exports_and_details_use_demo_records(self):
        result = self.request('/api/preview/transactions?search=Willow&scope=personal&limit=2&offset=1')['data']
        self.assertEqual(len(result['rows']), 2)
        self.assertGreater(result['total'], 2)
        self.assertTrue(all(row['merchant']=='Willow Market' for row in result['rows']))
        tid = result['rows'][0]['id']
        detail = self.request('/api/preview/receipts/transaction?id='+tid)
        self.assertEqual(detail['status'], 200, detail)
        self.assertTrue(detail['data']['demo'])
        self.assertNotEqual(self.request('/api/preview/receipts/transaction?id=private-account')['status'], 200)
        empty = self.request('/api/preview/transactions?account_id=private-account')['data']
        self.assertEqual(empty['rows'], [])
        csv = self.request('/api/preview/export/transactions.csv')['data']
        self.assertIn('Willow Market', csv)
        self.assertNotIn('PRIVATE', csv)
        self.assertLiveUnchanged()

    def test_projection_uses_curated_account_balances(self):
        defaults = self.request('/api/preview/projections/defaults')['data']
        self.assertEqual(defaults['starting_investments'], 28450)
        defaults['years'] = 5
        result = self.request('/api/preview/projections', 'POST', defaults)
        self.assertEqual(result['status'], 200, result)
        self.assertLiveUnchanged()

    def test_concurrent_live_request_never_inherits_demo_context(self):
        def demo_read():
            with demo_preview.dataset():
                # An independent worker thread must still see the live database.
                with ThreadPoolExecutor(max_workers=1) as worker:
                    private = worker.submit(db.q, 'SELECT name FROM accounts').result()
                self.assertEqual(private, [{'name':'PRIVATE SENTINEL'}])
                return db.q('SELECT id FROM accounts')
        with ThreadPoolExecutor(max_workers=2) as workers:
            demo = workers.submit(demo_read).result()
        self.assertTrue(all(row['id'].startswith('demo-') for row in demo))
        self.assertLiveUnchanged()

    def test_storage_context_restores_after_error(self):
        with self.assertRaises(RuntimeError):
            with demo_preview.dataset():
                raise RuntimeError('test failure')
        self.assertLiveUnchanged()

    def test_curated_data_is_current_and_coherent_at_calendar_boundaries(self):
        for today in (date(2026,1,1), date(2028,2,29), date(2026,12,31)):
            with self.subTest(today=today), tempfile.TemporaryDirectory() as directory, db.isolated_data(directory):
                demo_preview.seed(today)
                self.assertEqual(db.q1('SELECT COUNT(*) n FROM accounts')['n'], 5)
                self.assertGreater(db.q1('SELECT COUNT(*) n FROM transactions')['n'], 290)
                self.assertEqual(db.q1('SELECT COUNT(*) n FROM transactions WHERE posted>?', (today.isoformat(),))['n'], 0)
                self.assertEqual(db.q1('SELECT SUM(amount) total FROM transactions WHERE is_transfer=1')['total'], 0)
                self.assertEqual(db.q1('SELECT COUNT(*) n FROM subscriptions WHERE next_due<?', (today.isoformat(),))['n'], 0)
        self.assertLiveUnchanged()


if __name__ == '__main__':
    unittest.main()

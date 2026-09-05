import os
import json
import io
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from backend import db, cancellations, codex_worker


class CancellationQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.DATA_DIR = self.tmp.name
        db.DB_PATH = os.path.join(self.tmp.name, 'ledger.db')
        db.CONFIG_PATH = os.path.join(self.tmp.name, 'config.json')
        c = db._conn()
        c.execute("CREATE TABLE subscriptions (id TEXT PRIMARY KEY, merchant TEXT, status TEXT, env TEXT, management_url TEXT, billing_channel TEXT, amount REAL, notes TEXT)")
        c.executemany("INSERT INTO subscriptions VALUES (?,?,?,?,?,?,?,?)", [(f'sub-{i}', 'Example', 'active', 'production', 'https://example.com/manage', 'direct', 10, '') for i in range(1, 4)])
        c.commit(); c.close()
        cancellations.init_schema()

    def tearDown(self): self.tmp.cleanup()

    def test_request_is_idempotent_and_selected_subscription_authorizes(self):
        a = cancellations.request('sub-1')
        b = cancellations.request('sub-1')
        self.assertEqual(a['id'], b['id'])
        self.assertEqual(a['status'], 'queued')

    def test_missing_browser_needs_user_and_never_completes(self):
        job = cancellations.request('sub-2')
        with patch.dict(os.environ, {}, clear=True):
            done = cancellations.run_once()
        self.assertEqual(done['id'], job['id'])
        self.assertEqual(done['status'], 'needs_user')
        self.assertTrue(done['evidence'])

    def test_resume_and_completed_requires_evidence(self):
        job = cancellations.request('sub-3')
        cancellations._update(job['id'], 'needs_user', 'login')
        self.assertEqual(cancellations.resume(job['id'])['status'], 'queued')
        cancellations._update(job['id'], 'failed', 'bad')
        self.assertEqual(cancellations.resume(job['id'])['status'], 'queued')

    def test_completion_requires_provider_url_text_and_date_and_updates_subscription(self):
        job = cancellations.request('sub-1')
        with self.assertRaises(ValueError):
            cancellations._update(job['id'], 'completed', 'done',
                                  [{'provider_confirmed': True, 'url': 'http://example.com', 'text': 'Canceled', 'date': '2026-09-04'}],
                                  '2026-09-04')
        with self.assertRaises(ValueError):
            cancellations._update(job['id'], 'completed', 'done',
                                  [{'provider_confirmed': True, 'url': 'https://example.com', 'text': '', 'date': '2026-09-04'}],
                                  '2026-09-04')
        done = cancellations._update(job['id'], 'completed', 'done',
                                     [{'provider_confirmed': True, 'url': 'https://example.com/account', 'text': 'Membership canceled', 'date': '2026-09-04'}],
                                     '2026-09-04')
        self.assertEqual(done['status'], 'completed')
        self.assertEqual(db.q1('SELECT status FROM subscriptions WHERE id=?', ('sub-1',))['status'], 'canceled')

    def test_candidate_and_demo_linked_account_are_not_cancellable(self):
        c = db._conn()
        c.execute("UPDATE subscriptions SET status='candidate' WHERE id='sub-1'")
        c.commit()
        c.close()
        with self.assertRaises(ValueError): cancellations.request('sub-1')
        c = db._conn()
        c.execute("CREATE TABLE items (id TEXT PRIMARY KEY, env TEXT, access_token TEXT)")
        c.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, item_id TEXT)")
        c.execute("ALTER TABLE subscriptions ADD COLUMN account_id TEXT")
        c.execute("INSERT INTO items VALUES ('item-demo','demo',NULL)")
        c.execute("INSERT INTO accounts VALUES ('acct-demo','item-demo')")
        c.execute("UPDATE subscriptions SET status='active',account_id='acct-demo' WHERE id='sub-1'")
        c.commit(); c.close()
        with self.assertRaisesRegex(ValueError, 'demo'):
            cancellations.request('sub-1')

    def test_request_is_atomic_under_concurrent_duplicate_clicks(self):
        results, errors = [], []
        def click():
            try: results.append(cancellations.request('sub-1', 'same-click'))
            except Exception as exc: errors.append(exc)
        threads = [threading.Thread(target=click) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['id'], results[1]['id'])
        self.assertEqual(len(db.q('SELECT * FROM cancellation_jobs')), 1)

    def test_worker_uses_mcp_override_minimal_context_and_sanitized_environment(self):
        bridge = os.path.join(self.tmp.name, 'cancellation-browser.mjs')
        with open(bridge, 'w', encoding='utf-8') as f: f.write('// test bridge')
        mcp_cli = os.path.join(self.tmp.name, 'mcp-cli.js')
        with open(mcp_cli, 'w', encoding='utf-8') as f: f.write('// test mcp')
        job = cancellations.request('sub-2')
        calls = []
        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[1:3] == ['login', 'status']:
                return Mock(returncode=0, stdout='Logged in using ChatGPT', stderr='')
            output = argv[argv.index('--output-last-message') + 1]
            with open(output, 'w', encoding='utf-8') as f:
                import json
                json.dump({'status': 'completed', 'message': 'confirmed', 'effective_date': '2026-09-04',
                           'evidence': [{'provider_confirmed': True, 'url': 'https://example.com/manage',
                                         'text': 'Membership canceled', 'date': '2026-09-04'}]}, f)
            with open(os.path.join(kwargs['cwd'], 'browser-receipts.jsonl'), 'w', encoding='utf-8') as f:
                json.dump({'urls': ['https://example.com/manage'], 'text': 'Membership canceled', 'date': '2026-09-04'}, f)
                f.write('\n')
            return Mock(returncode=0, stdout='', stderr='')
        class FakeProcess:
            pid = 99999
            returncode = 0
            def communicate(self, timeout=None):
                result = fake_run(self.argv, **self.kwargs)
                return result.stdout, result.stderr
        def fake_popen(argv, **kwargs):
            proc = FakeProcess(); proc.argv, proc.kwargs = argv, kwargs; return proc
        with patch.dict(os.environ, {'LEDGER_BROWSER_BRIDGE': bridge, 'LEDGER_PLAYWRIGHT_MCP_CLI': mcp_cli, 'OPENAI_API_KEY': 'secret', 'PLAID_SECRET': 'bank-secret'}, clear=False), \
             patch.object(cancellations.shutil, 'which', side_effect=lambda name: '/bin/' + name), \
             patch.object(cancellations.subprocess, 'run', side_effect=fake_run), \
             patch.object(cancellations.subprocess, 'Popen', side_effect=fake_popen):
            done = cancellations.run_once()
        self.assertEqual(done['status'], 'completed')
        login_argv, worker_kwargs = calls[0][0], calls[1][1]
        worker_argv = calls[1][0]
        self.assertEqual(login_argv[1:3], ['login', 'status'])
        self.assertLess(worker_argv.index('-a'), worker_argv.index('exec'))
        self.assertIn('--output-last-message', worker_argv)
        self.assertIn('--output-schema', worker_argv)
        self.assertTrue(any('mcp_servers.ledger_browser.command' in x for x in worker_argv))
        self.assertTrue(any('mcp_servers.ledger_browser.args' in x and bridge in x for x in worker_argv))
        prompt = worker_argv[-1]
        self.assertIn('Example', prompt)
        self.assertNotIn('sub-2', prompt)
        self.assertNotIn('amount', prompt)
        self.assertNotIn('cadence', prompt)
        self.assertNotIn('OPENAI_API_KEY', worker_kwargs['env'])
        self.assertNotIn('PLAID_SECRET', worker_kwargs['env'])
        self.assertIn('LEDGER_BROWSER_PROFILE', worker_kwargs['env'])

    def test_stale_running_job_is_requeued_for_safe_handoff(self):
        job = cancellations.request('sub-1')
        c = db._conn()
        old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        c.execute("UPDATE cancellation_jobs SET status='running',updated_at=? WHERE id=?", (old, job['id']))
        c.commit(); c.close()
        with patch.dict(os.environ, {}, clear=True):
            resumed = cancellations.run_once()
        self.assertEqual(resumed['status'], 'needs_user')
        self.assertIn('not ready', resumed['message'])

    def test_manual_handoff_reuses_persisted_profile_and_provider_url(self):
        job = cancellations.request('sub-1')
        cancellations._update(job['id'], 'needs_user', 'login')
        mcp_cli = os.path.join(self.tmp.name, 'mcp-cli.js')
        with open(mcp_cli, 'w', encoding='utf-8') as f: f.write('// test mcp')
        fake_process = Mock(wait=Mock(return_value=0))
        fake_process.stdin = Mock()
        fake_process.stdout = io.StringIO('{"jsonrpc":"2.0","id":1,"result":{}}\n{"jsonrpc":"2.0","id":2,"result":{}}\n')
        with patch.dict(os.environ, {'LEDGER_PLAYWRIGHT_MCP_CLI': mcp_cli}, clear=False), \
             patch.object(codex_worker.shutil, 'which', return_value='/bin/node'), \
             patch.object(codex_worker.subprocess, 'Popen', return_value=fake_process) as launch:
            result = codex_worker.handoff(job['id'])
        self.assertIs(result, fake_process)
        argv = launch.call_args.args[0]
        self.assertEqual(argv[0], '/bin/node')
        self.assertIn(mcp_cli, argv)
        init_page = argv[argv.index('--init-page') + 1]
        with open(init_page, encoding='utf-8') as stream:
            self.assertIn('https://example.com/manage', stream.read())
        self.assertNotIn('--headless', argv)
        self.assertEqual(launch.call_args.kwargs['shell'], False)
        self.assertIn('browser-profile', launch.call_args.kwargs['env']['LEDGER_BROWSER_PROFILE'])
        sent = ''.join(call.args[0] for call in fake_process.stdin.write.call_args_list)
        self.assertIn('notifications/initialized', sent)
        self.assertIn('browser_navigate', sent)
        self.assertIn('https://example.com/manage', sent)
        cancellations._release_profile(fake_process._ledger_profile_lock)

    def test_manual_handoff_requires_needs_user_state(self):
        job = cancellations.request('sub-1')
        with self.assertRaisesRegex(ValueError, 'waiting for user action'):
            codex_worker.handoff(job['id'])

    def test_cancellation_profile_lock_is_shared_by_worker_and_handoff(self):
        job = cancellations.request('sub-1')
        cancellations._update(job['id'], 'needs_user', 'login')
        info = cancellations.handoff_info(job['id'])
        lock_fd = cancellations._acquire_profile(info['profile'])
        self.assertIsNotNone(lock_fd)
        try:
            with self.assertRaises(cancellations.ProfileBusy):
                cancellations._run_worker(['/bin/true'], profile=info['profile'])
            with patch.dict(os.environ, {'LEDGER_PLAYWRIGHT_MCP_CLI': os.path.join(self.tmp.name, 'missing.js')}), \
                 self.assertRaisesRegex(RuntimeError, 'profile is busy'):
                codex_worker.handoff(job['id'])
        finally:
            cancellations._release_profile(lock_fd)

    def test_browser_bridge_preserves_split_mcp_frames_and_records_receipt(self):
        fake_cli = os.path.join(self.tmp.name, 'fake-mcp.mjs')
        with open(fake_cli, 'w', encoding='utf-8') as stream:
            stream.write("""import readline from 'node:readline';
const rl=readline.createInterface({input:process.stdin});
for await (const line of rl) { const q=JSON.parse(line); let result={};
if(q.method==='initialize') result={protocolVersion:'2024-11-05'};
else if(q.method==='tools/list') result={tools:[]};
else if(q.method==='tools/call') result={content:[{type:'text',text:'https://example.com/manage Membership canceled'}]};
if(q.id!==undefined) process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:q.id,result})+'\\n'); }
""")
        workspace = os.path.join(self.tmp.name, 'bridge-work')
        os.makedirs(workspace)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.tmp.name,
               "LEDGER_BROWSER_JOB_ID": "split-test", "LEDGER_BROWSER_WORKSPACE": workspace,
               "LEDGER_BROWSER_PROFILE": os.path.join(workspace, "profile"),
               "LEDGER_PLAYWRIGHT_MCP_CLI": fake_cli,
               "LEDGER_BROWSER_ALLOWED_ORIGINS": "https://example.com",
               "LEDGER_BROWSER_ALLOWED_HOSTS": "example.com"}
        bridge = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cancellation-browser.mjs')
        proc = subprocess.Popen(["node", os.path.abspath(bridge)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env)
        try:
            initialize = json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}) + "\n"
            proc.stdin.write(initialize[:7]); proc.stdin.flush(); time.sleep(0.02)
            proc.stdin.write(initialize[7:]); proc.stdin.flush()
            self.assertEqual(json.loads(proc.stdout.readline())["id"], 1)
            call = json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"browser_snapshot","arguments":{}}}) + "\n"
            proc.stdin.write(call[:11]); proc.stdin.flush(); time.sleep(0.02)
            proc.stdin.write(call[11:]); proc.stdin.flush()
            self.assertEqual(json.loads(proc.stdout.readline())["id"], 2)
            receipt = os.path.join(workspace, 'browser-receipts.jsonl')
            with open(receipt, encoding='utf-8') as stream: saved = json.loads(stream.readline())
            self.assertEqual(saved['tool'], 'browser_snapshot')
            self.assertIn('https://example.com/manage', saved['urls'])
        finally:
            proc.terminate(); proc.wait(timeout=5)
            for handle in (proc.stdin, proc.stdout, proc.stderr):
                if handle: handle.close()
if __name__ == '__main__': unittest.main()

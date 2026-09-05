import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))
import receipt_worker


class ReceiptWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = os.path.join(self.tmp.name, "job")
        self.profile = os.path.join(self.tmp.name, "profiles", "amazon", "acct")
        os.makedirs(self.workspace)
        os.makedirs(self.profile)

    def tearDown(self):
        self.tmp.cleanup()

    def job(self):
        return {"id": "receipt-1", "transaction_id": "tx-1", "provider": "amazon",
                "merchant": "AMAZON MKTPLACE", "name": "AMZN Mktp US*123",
                "amount": -12.34, "posted": "2026-09-01", "scope": "personal",
                "account_id": "acct-1", "currency": "USD"}

    def payload(self):
        return {"status": "matched", "message": "Order matched.", "proposal": {
            "description": "Widget", "receipt": {"url": "https://www.amazon.com/gp/order/123?x=secret",
                "order_id": "123-4567890-1234567", "purchased_on": "2026-08-31", "currency": "USD",
                "total_cents": 1234, "card_last4": "4242", "capture_id": "capture-1"}, "items": [
                {"description": "Widget", "amount_cents": 1234, "category_id": None, "confidence": 0.96}],
            "ambiguous": False, "match_confidence": 0.96}}

    def capture(self):
        with open(os.path.join(self.workspace, "receipt-captures.jsonl"), "w", encoding="utf-8") as stream:
            json.dump({"id": "capture-1", "tool": "browser_snapshot", "url": "https://www.amazon.com/gp/order/123?token=hidden",
                       "text": "Order 123-4567890-1234567 Widget Total $12.34 Purchased August 31, 2026 USD Card ending in 4242", "captured_at": "2026-09-04T12:00:00Z"}, stream)
            stream.write("\n")

    def test_schema_has_strict_required_nested_fields_and_read_only_sandbox(self):
        schema = receipt_worker._schema()
        proposal = schema["properties"]["proposal"]
        receipt = proposal["properties"]["receipt"]
        self.assertEqual(set(receipt["required"]), set(receipt["properties"]))
        item = proposal["properties"]["items"]["items"]
        self.assertEqual(set(item["required"]), set(item["properties"]))
        with patch.dict(os.environ, {"LEDGER_RECEIPT_WORK_DIR": self.tmp.name}), \
             patch.object(receipt_worker, "status", return_value={"ready": False, "message": "not configured"}):
            result = receipt_worker.investigate(self.job())
        self.assertFalse(result["verified"])
        self.assertEqual(result["payload"]["status"], "needs_user")

    def test_provider_navigation_preserves_safe_order_query(self):
        job = self.job(); job["provider_url"] = "https://www.amazon.com/gp/order?orderID=123-4567890-1234567"
        self.assertEqual(receipt_worker._provider_url(job), job["provider_url"])

    def test_investigate_sends_minimal_context_and_accepts_only_capture_backed_match(self):
        calls = []
        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            output = argv[argv.index("--output-last-message") + 1]
            with open(output, "w", encoding="utf-8") as stream: json.dump(self.payload(), stream)
            self.capture()
            return subprocess.CompletedProcess(argv, 0, "", "")
        with patch.dict(os.environ, {"LEDGER_RECEIPT_WORK_DIR": self.tmp.name, "OPENAI_API_KEY": "secret", "PLAID_SECRET": "bank"}, clear=False), \
             patch.object(receipt_worker, "status", return_value={"ready": True}), \
             patch.object(receipt_worker, "_run", side_effect=fake_run), \
             patch.object(receipt_worker, "_paths", return_value=(self.workspace, self.profile)), \
             patch.object(receipt_worker.shutil, "which", return_value="/usr/bin/node"):
            result = receipt_worker.investigate(self.job())
        self.assertTrue(result["verified"])
        argv, kwargs = calls[0]
        self.assertEqual(argv[argv.index("-s") + 1], "read-only")
        self.assertIn("--ignore-user-config", argv)
        self.assertIn("--output-schema", argv)
        self.assertIn("features.shell_tool=false", argv)
        self.assertIn("features.computer_use=false", argv)
        self.assertIn("receipt_browser", " ".join(argv))
        self.assertIn("AMAZON MKTPLACE", argv[-1])
        self.assertIn("12.34", argv[-1])
        self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
        self.assertNotIn("PLAID_SECRET", kwargs["env"])

    def test_match_without_current_page_capture_is_unverified(self):
        calls = []
        def fake_run(argv, **kwargs):
            calls.append(1)
            with open(argv[argv.index("--output-last-message") + 1], "w", encoding="utf-8") as stream: json.dump(self.payload(), stream)
            return subprocess.CompletedProcess(argv, 0, "", "")
        with patch.dict(os.environ, {"LEDGER_RECEIPT_WORK_DIR": self.tmp.name}), \
             patch.object(receipt_worker, "status", return_value={"ready": True}), \
             patch.object(receipt_worker, "_run", side_effect=fake_run), \
             patch.object(receipt_worker, "_paths", return_value=(self.workspace, self.profile)), \
             patch.object(receipt_worker.shutil, "which", return_value="/usr/bin/node"):
            result = receipt_worker.investigate(self.job())
        self.assertFalse(result["verified"])

    def test_handoff_requires_display_and_reuses_provider_profile(self):
        job = self.job()
        fake = Mock()
        fake.stdin = Mock()
        fake.stdout = __import__("io").StringIO('{"jsonrpc":"2.0","id":1,"result":{}}\n{"jsonrpc":"2.0","id":2,"result":{}}\n')
        with patch.dict(os.environ, {"DISPLAY": ":99", "LEDGER_RECEIPT_WORK_DIR": self.tmp.name}), \
             patch.object(receipt_worker, "_job_for_handoff", return_value=job), \
             patch.object(receipt_worker, "_paths", return_value=(self.workspace, self.profile)), \
             patch.object(receipt_worker.shutil, "which", return_value="/usr/bin/node"), \
             patch.object(receipt_worker.subprocess, "Popen", return_value=fake) as launch:
            result = receipt_worker.handoff("receipt-1")
        self.assertIs(result, fake)
        self.assertEqual(launch.call_args.kwargs["env"]["LEDGER_RECEIPT_PROFILE"], self.profile)
        self.assertEqual(launch.call_args.kwargs["env"]["LEDGER_RECEIPT_HEADLESS"], "0")
        sent = "".join(call.args[0] for call in fake.stdin.write.call_args_list)
        self.assertIn("browser_navigate", sent)
        self.assertIn("amazon.com", sent)
        receipt_worker._release_profile(fake._ledger_profile_lock)

    def test_handoff_rejects_jobs_not_waiting_for_user(self):
        for state in ("queued", "running", "applied", "dismissed"):
            with patch.object(receipt_worker.receipt_store, "listing", return_value={"jobs": [{"id": "r1", "status": state}]}):
                with self.assertRaisesRegex(ValueError, "waiting for user"):
                    receipt_worker._job_for_handoff("r1")

    def test_bridge_filters_mutations_and_records_actual_page_url(self):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.tmp.name,
               "LEDGER_RECEIPT_JOB_ID": "split", "LEDGER_RECEIPT_WORKSPACE": self.workspace,
               "LEDGER_RECEIPT_PROFILE": self.profile,
               "LEDGER_RECEIPT_ALLOWED_ORIGINS": "https://amazon.com", "LEDGER_RECEIPT_ALLOWED_HOSTS": "amazon.com",
               "LEDGER_RECEIPT_FAKE_BROWSER": "1"}
        bridge = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "receipt-browser.mjs"))
        proc = subprocess.Popen(["node", bridge], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=env)
        try:
            initialize = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
            proc.stdin.write(initialize[:9]); proc.stdin.flush(); time.sleep(0.02); proc.stdin.write(initialize[9:]); proc.stdin.flush()
            initialized = json.loads(proc.stdout.readline())
            self.assertEqual(initialized["id"], 1)
            self.assertIn("tools", initialized["result"]["capabilities"])
            listed = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"
            proc.stdin.write(listed); proc.stdin.flush()
            tools = json.loads(proc.stdout.readline())["result"]["tools"]
            self.assertIn("browser_snapshot", [t["name"] for t in tools])
            self.assertNotIn("browser_click", [t["name"] for t in tools])
            navigate = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "browser_navigate", "arguments": {"url": "https://www.amazon.com/gp/order/123?x=1"}}}) + "\n"
            proc.stdin.write(navigate[:13]); proc.stdin.flush(); time.sleep(0.02); proc.stdin.write(navigate[13:]); proc.stdin.flush()
            navigated = json.loads(proc.stdout.readline())
            self.assertEqual(navigated["id"], 3)
            self.assertIn("x=1", navigated["result"]["url"])
            self.assertIn("receipt_capture_id=", navigated["result"]["content"][0]["text"])
            snapshot = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "browser_snapshot", "arguments": {}}}) + "\n"
            proc.stdin.write(snapshot); proc.stdin.flush(); self.assertEqual(json.loads(proc.stdout.readline())["id"], 4)
            denied = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "browser_click", "arguments": {}}}) + "\n"
            proc.stdin.write(denied); proc.stdin.flush(); self.assertIn("error", json.loads(proc.stdout.readline()))
            blocked_url = json.dumps({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "browser_navigate", "arguments": {"url": "https://www.amazon.com/gp/checkout?orderID=123"}}}) + "\n"
            proc.stdin.write(blocked_url); proc.stdin.flush(); self.assertIn("error", json.loads(proc.stdout.readline()))
            with open(os.path.join(self.workspace, "receipt-captures.jsonl"), encoding="utf-8") as stream:
                rows = [json.loads(line) for line in stream if line.strip()]
            self.assertTrue(rows)
            self.assertEqual(rows[-1]["url"], "https://www.amazon.com/gp/order/123")
            self.assertNotIn("token", rows[-1]["url"])
        finally:
            proc.terminate(); proc.wait(timeout=5)
            for handle in (proc.stdin, proc.stdout, proc.stderr):
                if handle: handle.close()


if __name__ == "__main__":
    unittest.main()

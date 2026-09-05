"""Ledger — localhost HTTP server (stdlib only).

Routes are /api/*; everything else serves the SPA from ../web/.
Binds localhost by default; containers publish their internal port to host loopback only.
"""
import json
import math
import secrets
import ipaddress
from http.cookies import SimpleCookie
from urllib.parse import urlsplit, unquote
import mimetypes
import os
import sqlite3
import threading
import uuid
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import analytics
import db
import plaid_client
import auth
import subscriptions
import forecasts
import reports
import receipt_store
import receipt_service
import cancellations
import scheduler
from db import q, q1, ex

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
PORT = int(os.environ.get("LEDGER_PORT", "8907"))
BIND_HOST = os.environ.get("LEDGER_BIND_HOST", "127.0.0.1")
if BIND_HOST not in ("127.0.0.1", "0.0.0.0"):
    raise RuntimeError("Ledger supports loopback binding or its Docker container binding.")
if BIND_HOST == "0.0.0.0" and not os.path.exists("/.dockerenv"):
    raise RuntimeError("Use Docker's loopback port mapping for a container bind.")
DEMO = os.environ.get("LEDGER_DEMO") == "1"
PUBLIC_ORIGIN = os.environ.get("LEDGER_PUBLIC_ORIGIN", "").rstrip("/")

_lock = threading.Lock()


def _json_bytes(obj):
    return json.dumps(obj, default=str).encode()


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Ledger/1.0"

    def log_message(self, fmt, *args):  # quiet console
        pass

    # ---------------- plumbing ----------------
    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if getattr(self, "close_connection", False):
            self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.plaid.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.plaid.com; connect-src 'self' https://*.plaid.com; frame-src https://*.plaid.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if getattr(self, "auth_cookie", None): self.send_header("Set-Cookie", self.auth_cookie)
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, code, obj):
        self._send(code, _json_bytes(obj))

    def _body(self):
        try: n = int(self.headers.get("Content-Length") or 0)
        except ValueError: raise ApiError(400, "Invalid request length.")
        if n < 0 or n > 1048576: raise ApiError(413, "This request is too large.")
        if not n: return {}
        if self.headers.get_content_type() != "application/json": raise ApiError(415, "Use a JSON request.")
        try:
            data = json.loads(self.rfile.read(n).decode(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
            if not isinstance(data, dict): raise ValueError()
            return data
        except (ValueError, UnicodeError): raise ApiError(400, "The request must be a valid JSON object.")

    def _static(self, path):
        full = os.path.realpath(os.path.join(WEB, unquote(path).lstrip("/") or "index.html"))
        if os.path.commonpath([WEB, full]) != WEB: raise ApiError(404, "Not found.")
        if not os.path.isfile(full):
            if "." in os.path.basename(path): raise ApiError(404, "Not found.")
            full = os.path.join(WEB, "index.html")
        with open(full, "rb") as f: body = f.read()
        self._send(200, body, mimetypes.guess_type(full)[0] or "application/octet-stream")

    def _session(self):
        cookie = SimpleCookie()
        try: cookie.load(self.headers.get("Cookie", ""))
        except Exception: return ""
        return cookie["ledger_session"].value if "ledger_session" in cookie else ""

    def _cookie(self, token):
        local = urlsplit("http://"+self.headers.get("Host", "")).hostname in ("127.0.0.1","localhost","::1")
        secure = "; Secure" if PUBLIC_ORIGIN.startswith("https://") and not local else ""
        self.auth_cookie = f"ledger_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={43200 if token else 0}{secure}"

    def _guard(self, method, path):
        host = self.headers.get("Host", "")
        local_hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
        # Local-forward ports are allowed only when address is a loopback literal/name.
        try: local = urlsplit("http://" + host).hostname in ("127.0.0.1", "localhost", "::1")
        except ValueError: local = False
        public_host = urlsplit(PUBLIC_ORIGIN).netloc if PUBLIC_ORIGIN else None
        if not local and (DEMO or not public_host or host != public_host): raise ApiError(403, "Open Ledger using its configured private address.")
        if method != "GET":
            origin = self.headers.get("Origin")
            allowed = {"http://"+host, "https://"+host, PUBLIC_ORIGIN}
            if self.headers.get("X-Ledger-Request") != "1" or (origin and origin not in allowed):
                raise ApiError(403, "Reload Ledger before trying again.")
            if path == "/api/auth/setup" and not local: raise ApiError(403, "Create the owner login on the home-lab computer first.")
        if path.startswith("/api/") and path not in ("/api/health", "/api/auth/status", "/api/auth/login", "/api/auth/setup") and not DEMO and not auth.validate(self._session()):
            raise ApiError(401, "Sign in to Ledger to continue.")

    def _dispatch(self, method):
        path = urlsplit(self.path).path
        try:
            self._guard(method, path)
            if not path.startswith("/api/"):
                if method == "GET": return self._static(path)
                raise ApiError(404, "Not found.")
            if method == "GET": return self._api(method, path)
            if method == "POST": return self._api_post(path, self._body())
            if method == "DELETE": return self._api_delete(path)
        except ApiError as e:
            # Guards can reject before consuming a POST body. Never let a
            # proxy reuse that connection and parse the body as a request.
            self.close_connection = True
            self._json(e.code, {"error":e.message})
        except plaid_client.PlaidError as e: self._json(400, {"error":str(e), "code":e.code})
        except (ValueError, TypeError, KeyError) as e: self._json(400, {"error":str(e) if isinstance(e, ValueError) else "Some fields are missing or invalid."})
        except sqlite3.IntegrityError: self._json(400, {"error":"That change conflicts with an existing record. Check the selected account and fields."})
        except Exception: self._json(500, {"error":"Ledger could not complete this request. Please check your latest records before trying again."})

    def do_GET(self): self._dispatch("GET")
    def do_POST(self): self._dispatch("POST")
    def do_DELETE(self): self._dispatch("DELETE")

    # ---------------- GET API ----------------
    def _api(self, method, path):
        if path == "/api/health":
            return self._json(200, {"ok": True, "time": datetime.now().isoformat(timespec="seconds")})

        if path == "/api/auth/status":
            return self._json(200, {"configured":auth.configured(), "authenticated":DEMO or auth.validate(self._session()), "demo":DEMO})
        if path == "/api/config":
            return self._json(200, {**db.public_config(), "demo":DEMO})
        if path == "/api/monthly-plan":
            qs = self._query_params()
            plan = subscriptions.monthly_plan(qs.get("scope"),qs.get("month"))
            return self._json(200, plan)
        if path == "/api/projections/defaults": return self._json(200, forecasts.defaults(self._query_params().get("scope")))
        if path == "/api/cancellations": return self._json(200, cancellations.listing())
        if path == "/api/cancellations/status": return self._json(200, cancellations.status())
        if path == "/api/receipts": return self._json(200, receipt_service.listing(demo=DEMO))
        if path == "/api/receipts/transaction":
            detail = receipt_store.detail(self._query_params().get("id"))
            detail["transaction"] = receipt_store.decorate_transactions([detail["transaction"]])[0]
            worker = receipt_service.status(demo=DEMO)
            job = detail.get("job") or {}
            if not DEMO and job.get("status") == "needs_user":
                worker["instructions"] = (
                    "On your home lab, open this lookup’s dedicated browser using the handoff command in "
                    "docs/INSTALL.md. Sign in, close that browser, then choose Continue lookup here. "
                    "Lookup ID: " + str(job["id"]))
            return self._json(200, {**detail, "demo": DEMO,
                                    "worker": worker})
        if path == "/api/sync/status": return self._json(200, scheduler.status())

        if path == "/api/accounts":
            archived = self._query_params().get("archived") == "1"
            rows = q("SELECT * FROM accounts WHERE archived=? ORDER BY scope, name", (int(archived),))
            return self._json(200, rows)

        if path == "/api/items":
            rows = q("""SELECT i.*, COUNT(a.id) n_accounts,
                               COALESCE(SUM(CASE WHEN a.archived=0 THEN a.balance END),0) balance
                        FROM items i LEFT JOIN accounts a ON a.item_id=i.id
                        GROUP BY i.id ORDER BY i.created_at""")
            cfg = db.get_config()
            for r in rows:
                r["has_token"] = bool(r.pop("access_token", None))
                r["plaid_configured"] = plaid_client.configured()
                r["env_label"] = r["env"]
            return self._json(200, rows)

        if path == "/api/categories":
            return self._json(200, q("SELECT * FROM categories ORDER BY kind DESC, name"))

        if path == "/api/transactions":
            args = []
            where = ["1=1"]
            qs = self._query_params()
            if qs.get("scope"):
                where.append("t.scope=?"); args.append(qs["scope"])
            if qs.get("account_id"):
                where.append("account_id=?"); args.append(qs["account_id"])
            if qs.get("category_id"):
                receipt_store.init_schema()
                where.append("(t.category_id=? OR EXISTS (SELECT 1 FROM receipt_allocations ra WHERE ra.transaction_id=t.id AND ra.category_id=? AND ra.active=1))")
                args.extend([qs["category_id"], qs["category_id"]])
            if qs.get("since"):
                where.append("posted>=?"); args.append(qs["since"])
            if qs.get("until"):
                where.append("posted<=?"); args.append(qs["until"])
            if qs.get("search"):
                receipt_store.init_schema()
                where.append("(t.name LIKE ? OR t.merchant LIKE ? OR t.note LIKE ? OR EXISTS (SELECT 1 FROM receipt_allocations ra JOIN receipt_jobs rj ON rj.id=ra.job_id WHERE ra.transaction_id=t.id AND ra.active=1 AND rj.status='applied' AND ra.description LIKE ?))")
                like = f"%{qs['search']}%"; args += [like, like, like, like]
            limit = max(1, min(int(qs.get("limit", 200)), 1000))
            offset = max(0, int(qs.get("offset", 0)))
            w = " AND ".join(where)
            select = f"""SELECT t.*, c.name cat_name, c.icon cat_icon, a.name acct_name, a.mask acct_mask
                    FROM transactions t
                    LEFT JOIN categories c ON t.category_id=c.id
                    LEFT JOIN accounts a ON t.account_id=a.id
                    WHERE {w} ORDER BY posted DESC, t.rowid DESC"""
            if qs.get("category_id"):
                candidates = q(select, args)
                allocations = receipt_store.allocation_map([row["id"] for row in candidates])
                rows = [row for row in candidates if (
                    any(item["category_id"] == qs["category_id"] for item in allocations[row["id"]])
                    if row["id"] in allocations else row["category_id"] == qs["category_id"])]
                total = len(rows)
                rows = rows[offset:offset + limit]
            else:
                total = q1(f"SELECT COUNT(*) n FROM transactions t WHERE {w}", args)["n"]
                rows = q(select + " LIMIT ? OFFSET ?", (*args, limit, offset))
            return self._json(200, {"rows": receipt_store.decorate_transactions(rows), "total": total, "limit": limit, "offset": offset})

        if path == "/api/summary/overview":
            qs = self._query_params()
            return self._json(200, analytics.overview(qs.get("scope")))

        if path == "/api/summary/networth":
            qs = self._query_params()
            return self._json(200, analytics.net_worth_series(max(1,min(120,int(qs.get("months", 12)))), qs.get("scope")))

        if path == "/api/summary/cashflow":
            qs = self._query_params()
            return self._json(200, analytics.cashflow_series(max(1,min(120,int(qs.get("months", 8)))), qs.get("scope")))

        if path == "/api/summary/categories":
            qs = self._query_params()
            return self._json(200, analytics.category_breakdown(
                qs.get("scope"), int(qs.get("days", 90)), qs.get("kind", "expense")))

        if path == "/api/summary/heatmap":
            qs = self._query_params()
            return self._json(200, analytics.heatmap_data(qs.get("scope")))

        if path == "/api/summary/matrix":
            qs = self._query_params()
            return self._json(200, analytics.monthly_matrix(qs.get("scope"), max(1,min(120,int(qs.get("months", 6))))))

        if path == "/api/reports/spending":
            qs = self._query_params()
            try:
                return self._json(200, reports.spending_report(qs.get("year"), qs.get("scope") or None))
            except ValueError as e:
                raise ApiError(400, str(e))

        if path == "/api/budgets":
            return self._json(200, analytics.budget_status())

        if path == "/api/subscriptions":
            return self._json(200, subscriptions.listing(self._query_params().get("scope")))

        if path == "/api/goals":
            return self._json(200, analytics.goal_projections())

        if path == "/api/business/summary":
            return self._json(200, analytics.business_summary())

        if path == "/api/export/transactions.csv":
            rows = q("""SELECT t.id, t.posted, t.scope, a.name account, COALESCE(c.name,'') category,
                               t.name, t.merchant, t.amount, t.recurring, t.note
                        FROM transactions t LEFT JOIN accounts a ON t.account_id=a.id
                        LEFT JOIN categories c ON t.category_id=c.id ORDER BY t.posted""")
            import csv, io
            buf = io.StringIO()
            wr = csv.writer(buf)
            wr.writerow(["date", "scope", "account", "category", "name", "merchant", "amount", "recurring", "note"])
            allocations = receipt_store.allocation_map([row["id"] for row in rows])
            for r in rows:
                # Export allocations instead of the original expense row, so
                # summing the amount column still counts each bank charge once.
                items = allocations.get(r["id"]) or [{"cat_name": r["category"], "description": r["name"], "amount": r["amount"]}]
                for item in items:
                    amount = -item["amount_cents"] / 100 if "amount_cents" in item else item["amount"]
                    values = [r["posted"],r["scope"],r["account"],item.get("cat_name") or "",item["description"],r["merchant"],amount,r["recurring"],r["note"]]
                    wr.writerow([("\'"+str(v)) if isinstance(v,str) and v.startswith(("=","+","-","@","\t","\r")) else v for v in values])
            return self._send(200, buf.getvalue().encode(), "text/csv")

        raise ApiError(404, f"unknown GET {path}")

    def _query_params(self):
        out = {}
        raw = self.path.split("?", 1)
        if len(raw) != 2:
            return out
        import urllib.parse
        for k, v in urllib.parse.parse_qsl(raw[1]):
            out[k] = v
        return out

    # ---------------- POST API ----------------
    def _api_post(self, path, b):
        if path == "/api/auth/setup":
            if auth.configured(): raise ApiError(409, "An owner login already exists.")
            token = auth.setup(b.get("password", "")); self._cookie(token)
            return self._json(200, {"ok":True})
        if path == "/api/auth/login":
            token = auth.login(b.get("password", ""), remote=self.client_address[0]); self._cookie(token)
            return self._json(200, {"ok":True})
        if path == "/api/auth/logout":
            auth.logout(self._session()); self._cookie("")
            return self._json(200, {"ok":True})
        if path == "/api/subscriptions": return self._json(200, subscriptions.save(b))
        if path == "/api/subscriptions/scan": return self._json(200, subscriptions.scan())
        if path == "/api/subscriptions/review": return self._json(200, subscriptions.review(b.get("id"),b.get("decision")))
        if path == "/api/projections": return self._json(200, forecasts.project(b))
        if path == "/api/cancellations/request":
            if DEMO: raise ApiError(400, "Cancellation agents are disabled in the demo. You can explore subscription tracking safely.")
            return self._json(200, cancellations.request(b.get("subscription_id")))
        if path == "/api/cancellations/resume":
            if DEMO: raise ApiError(400, "Cancellation agents are disabled in demo mode.")
            return self._json(200, cancellations.resume(b.get("id")))
        if path == "/api/receipts/settings":
            return self._json(200, receipt_service.save_settings(b, demo=DEMO))
        if path in ("/api/receipts/request", "/api/receipts/resume"):
            if DEMO or receipt_service.disabled():
                raise ApiError(400, "Purchase lookups are off in this preview. Your merchant accounts are never opened here.")
            result = (receipt_store.request(b.get("transaction_id")) if path.endswith("/request")
                      else receipt_store.resume(b.get("id")))
            return self._json(200, result)
        if path == "/api/receipts/review":
            return self._json(200, receipt_store.review(b.get("id"), b.get("decision"), category_ids=b.get("category_ids")))
        if path == "/api/receipts/undo":
            return self._json(200, receipt_store.undo(b.get("transaction_id")))
        if path == "/api/sync": return self._json(200, scheduler.sync_all())
        if path == "/api/accounts/manual":
            scope = b.get("scope", "personal")
            if scope not in ("personal", "business"): raise ValueError("Choose personal or business.")
            name = str(b.get("name", "")).strip()[:120]
            if not name: raise ValueError("Give this account a name.")
            balance = number(b.get("balance",0), -1e12, 1e12)
            kind = b.get("type", "depository")
            if kind not in ("depository","investment","credit","loan","other"): raise ValueError("Choose a valid account type.")
            if kind in ("credit", "loan"): balance = -abs(balance)
            aid = b.get("id") or "acct_"+uuid.uuid4().hex[:12]
            if b.get("id"):
                old = q1("SELECT * FROM accounts WHERE id=?", (aid,))
                if not old or old.get("item_id"): raise ValueError("Only manual account balances can be edited here.")
                c = db._conn()
                try:
                    with c:
                        c.execute("UPDATE accounts SET name=?,balance=?,scope=?,type=? WHERE id=?",(name,balance,scope,kind,aid))
                        _scope_account(c, aid, scope)
                finally: c.close()
            else:
                ex("INSERT INTO accounts(id,name,balance,scope,type,created_at) VALUES(?,?,?,?,?,?)", (aid,name,balance,scope,kind,datetime.now().isoformat()))
            return self._json(200, {"ok":True,"id":aid})
        if path == "/api/plaid/link-token":
            if DEMO: raise ApiError(400, "Real bank linking is disabled in this separate demo.")
            if q1("SELECT 1 FROM items WHERE env='demo'"): raise ApiError(400, "Clear sample data in Settings before linking real accounts.")
            try:
                return self._json(200, plaid_client.create_link_token(item_id=b.get("item_id")))
            except plaid_client.PlaidError as e:
                raise ApiError(400, str(e))

        if path == "/api/plaid/exchange":
            if DEMO: raise ApiError(400, "Bank linking is disabled in demo mode.")
            scope = b.get("scope") or "personal"
            item_id, accts = plaid_client.ingest_item(
                public_token=b.get("public_token"),
                institution=b.get("institution") or "Linked institution",
                scope=scope,
                existing_item_id=b.get("item_id"),
            )
            threading.Thread(target=scheduler.sync_all, daemon=True).start()
            return self._json(200, {"item_id": item_id, "accounts": accts})

        if path == "/api/plaid/sandbox-token":
            if DEMO: raise ApiError(400, "Bank linking is disabled in demo mode.")
            try:
                return self._json(200, plaid_client.sandbox_public_token())
            except plaid_client.PlaidError as e:
                raise ApiError(400, str(e))

        if path == "/api/plaid/sandbox-full-link":
            if DEMO: raise ApiError(400, "Bank linking is disabled in demo mode.")
            """Sandbox end-to-end: create token, exchange it, ingest accounts."""
            try:
                tok = plaid_client.sandbox_public_token(b.get("institution", "ins_109508"))
                item_id, accts = plaid_client.ingest_item(
                    public_token=tok["public_token"],
                    institution=b.get("institution_name", "Sandbox Financial"),
                    scope=b.get("scope", "personal"),
                    env_label="sandbox",
                )
                return self._json(200, {"item_id": item_id, "accounts": accts})
            except plaid_client.PlaidError as e:
                raise ApiError(400, str(e))

        if path == "/api/items/refresh":
            item_id = b.get("item_id")
            if not item_id:
                raise ApiError(400, "item_id required")
            try:
                result = plaid_client.refresh_item(item_id)
                _scan_safely()
                return self._json(200, result)
            except plaid_client.PlaidError as e:
                raise ApiError(400, str(e))

        if path == "/api/accounts/classify":
            aid = b.get("id")
            if not q1("SELECT 1 FROM accounts WHERE id=?", (aid,)): raise ApiError(404, "Account not found.")
            scope = b.get("scope")
            if scope not in ("business", "personal"):
                raise ApiError(400, "scope must be business|personal")
            c = db._conn()
            try:
                with c: _scope_account(c, aid, scope)
            finally: c.close()
            return self._json(200, {"ok": True})

        if path == "/api/accounts/archive":
            aid = b.get("id")
            changed, _ = ex("UPDATE accounts SET archived=? WHERE id=?", (0 if b.get("restore") else 1, aid))
            if not changed: raise ApiError(404, "Account not found.")
            return self._json(200, {"ok": True})

        if path == "/api/demo/seed":
            if q1("SELECT 1 FROM items WHERE access_token IS NOT NULL"): raise ApiError(400, "Sample data cannot replace linked bank data.")
            from seed_demo import seed_demo
            result = seed_demo(force=bool(b.get("force")))
            subscriptions.scan()
            return self._json(200, result)

        if path == "/api/data/reset":
            if q1("SELECT 1 FROM cancellation_jobs WHERE status IN ('queued','running','needs_user')"):
                raise ValueError("Finish or resolve pending cancellation requests before resetting data.")
            if q1("SELECT 1 FROM items WHERE access_token IS NOT NULL"):
                raise ValueError("Remove bank connections in Accounts before resetting data.")
            db.reset_all()
            return self._json(200, {"ok": True})

        if path == "/api/config":
            if any(key in b for key in ("receipt_lookup_enabled", "receipt_auto_apply", "receipt_daily_limit")):
                raise ValueError("Use the purchase lookup settings to change these preferences.")
            for key, allowed in (("palette",("colorful","paper")),("font_family",("system","nunito","manrope","lora")),("theme",("light","dark","system")),("accent",("blue","sage","plum","clay")),("density",("comfortable","compact")),("plaid_env",("sandbox","production"))):
                if key in b and b[key] not in allowed: raise ValueError(f"Invalid {key} choice.")
            for key, low, high in (("tax_rate_business",0,1),("monthly_spending_target",0,1e12),("sync_interval_minutes",15,1440)):
                if key in b: b[key] = number(b[key],low,high)
            if "home_cards" in b:
                cards = b["home_cards"]
                if not isinstance(cards,list) or len(cards)>4 or len(set(cards)) != len(cards) or any(v not in ("recent","upcoming","cashflow","goals") for v in cards): raise ValueError("Invalid dashboard layout.")
            if "owner_name" in b: b["owner_name"] = str(b["owner_name"])[:50]
            if b.get("plaid_redirect_uri") and not b["plaid_redirect_uri"].startswith("https://"): raise ValueError("The bank return address must start with https://.")
            saved = db.save_config(b)
            return self._json(200, saved)

        if path == "/api/transactions":
            tx = b.get("transaction") or {}
            acct = q1("SELECT * FROM accounts WHERE id=? AND archived=0", (tx.get("account_id"),))
            if not acct: raise ValueError("Choose an active account.")
            tx["scope"] = acct["scope"]
            tx["amount"] = number(tx.get("amount"),-1e12,1e12)
            if not tx["amount"]: raise ValueError("Enter a non-zero amount.")
            posted = tx.get("posted") or date.today().isoformat()
            if date.fromisoformat(posted)>date.today(): raise ValueError("Use subscriptions to plan future charges; transactions need today or an earlier date.")
            tx["posted"] = posted
            tx["name"] = str(tx.get("name") or "Manual entry")[:200]
            tx["merchant"] = str(tx.get("merchant") or tx["name"])[:200]
            tx["note"] = str(tx.get("note") or "")[:2000]
            tid = f"tx_{uuid.uuid4().hex[:16]}"
            now = datetime.now().isoformat(timespec="seconds")
            c = db._conn()
            try:
                with c:
                    c.execute("""INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,pending,recurring,note,plaid_transaction_id,created_at,is_transfer,category_override)
                      VALUES(?,?,?,?,?,?,?,?,0,0,?,NULL,?,?,?)""", (tid,acct["id"],acct["scope"],tx["amount"],posted,tx["name"],tx["merchant"],tx.get("category_id"),tx["note"],now,int(bool(tx.get("is_transfer"))),int(bool(tx.get("category_id")))))
                    if not acct.get("item_id"): c.execute("UPDATE accounts SET balance=balance+? WHERE id=?",(tx["amount"],acct["id"]))
            finally: c.close()
            _scan_safely()
            return self._json(200, {"ok": True, "id": tid})

        if path == "/api/transactions/update":
            tid = b.get("id")
            if not tid or not q1("SELECT 1 FROM transactions WHERE id=?", (tid,)):
                raise ApiError(404, "transaction not found")
            fields = ("category_id", "name", "note", "scope", "recurring", "is_transfer")
            receipt_store.manual_update(tid, {key: b[key] for key in fields if key in b})
            return self._json(200, {"ok": True})

        if path == "/api/budgets":
            if b.get("scope", "personal") not in ("all","personal","business"): raise ValueError("Choose a valid scope.")
            b["month_limit"] = number(b.get("month_limit"),0.01,1e12)
            bid = b.get("id") or f"bud_{uuid.uuid4().hex[:8]}"
            cid = b.get("category_id")
            if not q1("SELECT 1 FROM categories WHERE id=?", (cid,)):
                raise ApiError(400, "unknown category")
            ex("INSERT OR REPLACE INTO budgets(id,category_id,scope,month_limit,period) VALUES(?,?,?,?,?)",
               (bid, cid, b.get("scope", "personal"), float(b.get("month_limit") or 0), "monthly"))
            return self._json(200, {"ok": True, "id": bid})

        if path == "/api/goals/contribute":
            gid = b.get("id")
            amt = number(b.get("amount"),0.01,1e12)
            g = q1("SELECT * FROM goals WHERE id=?", (gid,))
            if not g:
                raise ApiError(404, "goal not found")
            newsaved = g["saved"] + amt
            done = datetime.now().isoformat(timespec="seconds") if newsaved >= g["target"] else None
            ex("UPDATE goals SET saved=?, completed_at=COALESCE(?, completed_at) WHERE id=?",
               (round(newsaved, 2), done, gid))
            return self._json(200, {"ok": True, "saved": round(newsaved, 2)})

        if path == "/api/goals":
            scope = b.get("scope", "personal")
            if scope not in ("personal", "business"): raise ValueError("Choose personal or business for this goal.")
            account_id = b.get("account_id") or None
            if account_id and not q1("SELECT 1 FROM accounts WHERE id=? AND archived=0 AND scope=?", (account_id, scope)):
                raise ValueError("Choose an active account in the same personal or business space as this goal.")
            b["target"] = number(b.get("target"),0.01,1e12)
            b["saved"] = number(b.get("saved",0),0,1e12)
            b["monthly_plan"] = number(b.get("monthly_plan",0),0,1e12)
            if b.get("target_date"): date.fromisoformat(b["target_date"])
            gid = b.get("id") or f"goal_{uuid.uuid4().hex[:8]}"
            now = datetime.now().isoformat(timespec="seconds")
            ex("""INSERT INTO goals(id,name,target,saved,monthly_plan,target_date,scope,account_id,completed_at,created_at)
                  VALUES(?,?,?,?,?,?,?,?,NULL,?)""",
               (gid, b.get("name") or "Goal", float(b.get("target") or 0),
                float(b.get("saved") or 0), float(b.get("monthly_plan") or 0),
                b.get("target_date"), scope, account_id, now))
            return self._json(200, {"ok": True, "id": gid})

        raise ApiError(404, f"unknown POST {path}")

    # ---------------- DELETE API ----------------
    def _api_delete(self, path):
        if path == "/api/budgets":
            pid = self._query_params().get("id")
            ex("DELETE FROM budgets WHERE id=?", (pid,))
            return self._json(200, {"ok": True})
        if path == "/api/goals":
            gid = self._query_params().get("id")
            ex("DELETE FROM goals WHERE id=?", (gid,))
            return self._json(200, {"ok": True})
        if path == "/api/transactions":
            tid = self._query_params().get("id")
            tx=q1("SELECT t.*,a.item_id FROM transactions t LEFT JOIN accounts a ON t.account_id=a.id WHERE t.id=?",(tid,))
            c = db._conn()
            try:
                with c:
                    if tx and not tx.get("item_id"): c.execute("UPDATE accounts SET balance=balance-? WHERE id=?",(tx["amount"],tx["account_id"]))
                    c.execute("DELETE FROM transactions WHERE id=?", (tid,))
            finally: c.close()
            return self._json(200, {"ok": True})
        if path == "/api/items":
            iid = self._query_params().get("id")
            plaid_client.remove_item(iid)
            return self._json(200, {"ok": True})
        raise ApiError(404, f"unknown DELETE {path}")


def _scan_safely():
    # A successful saved transaction must not look failed if detection needs repair.
    try: subscriptions.scan()
    except Exception: pass

def _scope_account(c, aid, scope):
    c.execute("UPDATE accounts SET scope=? WHERE id=?", (scope, aid))
    affected = c.execute("SELECT id FROM transactions WHERE account_id=? AND scope_override IS NULL AND scope<>?", (aid, scope)).fetchall()
    c.execute("UPDATE transactions SET scope=? WHERE account_id=? AND scope_override IS NULL", (scope, aid))
    for tx in affected:
        receipt_store.invalidate_transaction(tx["id"], conn=c)
    for sub in c.execute("SELECT id,merchant,normalized_key FROM subscriptions WHERE account_id=?",(aid,)).fetchall():
        key = subscriptions._norm(sub["merchant"]) + "|" + scope + "|" + aid
        c.execute("UPDATE subscriptions SET scope=?,normalized_key=? WHERE id=?",(scope,key,sub["id"]))
        c.execute("UPDATE OR REPLACE subscription_learning SET normalized_key=? WHERE normalized_key=?",(key,sub["normalized_key"]))

def number(value, low, high):
    try: value = float(value)
    except (TypeError, ValueError): raise ValueError("Enter a valid number.")
    if not math.isfinite(value) or not low <= value <= high: raise ValueError(f"Enter a number between {low:g} and {high:g}.")
    return value

def main():
    os.umask(0o077)
    db.init_db()
    auth.init_schema()
    subscriptions.init_schema()
    cancellations.init_schema()
    receipt_store.init_schema()
    scheduler.init_schema()
    if DEMO:
        if q1("SELECT 1 FROM items WHERE access_token IS NOT NULL"): raise RuntimeError("Use a separate empty data directory for demo mode.")
        from seed_demo import seed_demo
        seed_demo()
        subscriptions.scan()
    else:
        scheduler.start()
        def worker_loop():
            import time
            while True:
                try: cancellations.run_once()
                except Exception: pass
                try: receipt_service.run_once()
                except Exception: pass
                time.sleep(5)
        threading.Thread(target=worker_loop,daemon=True).start()
    srv = ThreadingHTTPServer((BIND_HOST, PORT), Handler)
    print(f"Ledger running at http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

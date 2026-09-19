"""Plaid Link and cursor-based sync. Credentials stay on the local backend."""
import json
import urllib.request
import urllib.error
import uuid
import threading
from datetime import date, datetime
import db
import receipt_store
import transaction_repair
import category_picker

ENVS = {"sandbox": "https://sandbox.plaid.com", "production": "https://production.plaid.com"}
TIMEOUT = 30
_sync_lock = threading.Lock()

class PlaidError(Exception):
    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code, self.status = code or "UNKNOWN", status

def _post(path, payload, env=None):
    cfg = db.get_config()
    environment = env or cfg.get("plaid_env", "sandbox")
    if environment not in ENVS: raise PlaidError("Choose Sandbox or Production in Settings.")
    if not configured(): raise PlaidError("Connect your Plaid credentials in Settings first.", "NOT_CONFIGURED")
    data = {"client_id": cfg["plaid_client_id"], "secret": cfg["plaid_secret"], **payload}
    req = urllib.request.Request(ENVS[environment] + path, data=json.dumps(data).encode(), headers={"Content-Type":"application/json", "Plaid-Version":"2020-09-14"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read())
        except (ValueError, OSError): body = {}
        code = body.get("error_code", "BANK_ERROR")
        messages = {"ITEM_LOGIN_REQUIRED":"Your bank needs you to reconnect.", "INVALID_CREDENTIALS":"Check your Plaid credentials and environment.", "PRODUCT_NOT_READY":"Your bank is still preparing transactions. We will try again.", "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION":"Bank transactions changed during sync. Retrying safely."}
        # Match the known setup failure without exposing provider response text,
        # which can include submitted values. Only return our own safe guidance.
        detail = str(body.get("error_message", "")).lower()
        if code == "INVALID_FIELD" and "redirect" in detail and "uri" in detail:
            message = "Add the exact OAuth return URL from Ledger's bank settings to Plaid Dashboard → Developers → API → Allowed redirect URIs, then save and try Link account again."
        else:
            message = messages.get(code, "The bank connection needs attention. Please try again.")
        raise PlaidError(message, code, e.code) from None
    except (OSError, ValueError):
        raise PlaidError("The bank connection is temporarily unavailable. Your saved data is safe.", "NETWORK_ERROR") from None

def configured():
    cfg = db.get_config()
    return bool(cfg.get("plaid_client_id") and cfg.get("plaid_secret"))

def create_link_token(scope_hint=None, item_id=None):
    payload = {"client_name":"Ledger", "country_codes":["US"], "language":"en", "user":{"client_user_id":"ledger-owner"}}
    cfg = db.get_config()
    if item_id:
        item = db.q1("SELECT * FROM items WHERE id=?", (item_id,))
        if not item or not item.get("access_token"): raise PlaidError("Bank connection not found.")
        payload["access_token"] = item["access_token"]
    else:
        payload["products"] = ["transactions"]
        payload["transactions"] = {"days_requested":730}
    if cfg.get("plaid_redirect_uri"): payload["redirect_uri"] = cfg["plaid_redirect_uri"]
    return _post("/link/token/create", payload, item.get("env") if item_id else None)

def exchange_public_token(public_token):
    if not isinstance(public_token, str) or not public_token: raise PlaidError("A bank connection token is required.")
    return _post("/item/public_token/exchange", {"public_token":public_token})

def fetch_accounts(access_token, env=None):
    return _post("/accounts/get", {"access_token":access_token}, env)

def sandbox_public_token(institution="ins_109508"):
    if db.get_config()["plaid_env"] != "sandbox": raise PlaidError("Test banks are only available in Sandbox.")
    return _post("/sandbox/public_token/create", {"institution_id":institution, "initial_products":["transactions"]})

def _balance(a):
    value = float((a.get("balances") or {}).get("current") or 0)
    return -value if a.get("type") in ("credit", "loan") else value

def map_plaid_category(raw):
    key = (raw or "").lower().replace("_", " ")
    mapping = [("grocer","cat-groceries"),("food","cat-dining"),("rent","cat-rent"),("utilit","cat-utilities"),("phone","cat-internet"),("transport","cat-transport"),("gas","cat-transport"),("merchandise","cat-shopping"),("medical","cat-health"),("insurance","cat-insurance"),("subscription","cat-subscriptions"),("travel","cat-travel"),("entertain","cat-fun"),("fee","cat-fees"),("software","cat-biz-software"),("income","cat-income")]
    return next((cid for label,cid in mapping if label in key), None)

def ingest_item(public_token=None, access_token=None, institution="Unknown", scope="personal", env_label=None, existing_item_id=None):
    if scope not in ("personal","business"): raise PlaidError("Choose a valid account scope.")
    env = env_label or db.get_config()["plaid_env"]
    if env not in ENVS: raise PlaidError("Choose a valid Plaid environment.")
    exchanged = exchange_public_token(public_token) if public_token else {"access_token":access_token}
    access = exchanged.get("access_token")
    if not access: raise PlaidError("Bank connection failed. Try linking again.")
    meta = fetch_accounts(access, env)
    now = datetime.now().isoformat(timespec="seconds")
    plaid_item_id = exchanged.get("item_id")
    conn = db._conn()
    try:
        # Serialize lookup plus upsert so two concurrent Link callbacks cannot
        # both observe the item as absent and create duplicate local rows.
        conn.execute("BEGIN IMMEDIATE")
        transaction_repair.init_schema(conn)
        known_aliases = transaction_repair.aliases(conn)
        # Link update mode returns the same Plaid item.  Reuse the local row
        # and local account ids so reconnecting never doubles balances.  The
        # lookup also makes a repeated exchange idempotent if the frontend
        # loses the first response.  Existing duplicate rows are left intact;
        # a caller can explicitly select the local item to repair one.
        item = None
        if existing_item_id:
            item = conn.execute("SELECT * FROM items WHERE id=?", (existing_item_id,)).fetchone()
            if not item:
                raise PlaidError("Bank connection not found.")
            if plaid_item_id and item["plaid_item_id"] and item["plaid_item_id"] != plaid_item_id:
                raise PlaidError("That bank connection belongs to a different institution.")
        if item is None and plaid_item_id:
            item = conn.execute("SELECT * FROM items WHERE plaid_item_id=? ORDER BY created_at,id LIMIT 1", (plaid_item_id,)).fetchone()
        if item is None:
            iid = "item_"+uuid.uuid4().hex[:12]
            conn.execute("INSERT INTO items(id,plaid_item_id,institution,env,access_token,created_at) VALUES(?,?,?,?,?,?)", (iid,plaid_item_id,institution,env,access,now))
        else:
            iid = item["id"]
            conn.execute("UPDATE items SET plaid_item_id=COALESCE(?,plaid_item_id),institution=?,env=?,access_token=? WHERE id=?", (plaid_item_id,institution,env,access,iid))
        for a in meta.get("accounts",[]):
            existing = conn.execute("SELECT id,archived FROM accounts WHERE item_id=? AND plaid_account_id=?", (iid,a["account_id"])).fetchone()
            values = (a.get("name") or "Bank account",a.get("official_name"),a.get("type"),a.get("subtype"),a.get("mask"),_balance(a),(a.get("balances") or {}).get("iso_currency_code") or "USD")
            if existing:
                if existing["archived"] or existing["id"] in known_aliases:
                    continue
                # Archived accounts are frozen history, including their last
                # known balance. Reconnecting never restores them implicitly.
                conn.execute("UPDATE accounts SET name=?,official_name=?,type=?,subtype=?,mask=?,balance=?,iso_currency=? WHERE id=?", (*values,existing["id"]))
            else:
                conn.execute("INSERT INTO accounts(id,item_id,name,official_name,type,subtype,scope,mask,balance,iso_currency,plaid_account_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", ("acct_"+uuid.uuid4().hex[:12],iid,*values[:4],scope,values[4],values[5],values[6],a["account_id"],now))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
    return iid, db.q("SELECT * FROM accounts WHERE item_id=?",(iid,))

def sync_transactions(item):
    start = item.get("cursor")
    for attempt in range(3):
        cursor = start
        added, modified, removed = [], [], []
        try:
            for page in range(1000):
                payload = {"access_token":item["access_token"], "count":500}
                if cursor: payload["cursor"] = cursor
                body = _post("/transactions/sync",payload,item.get("env"))
                added.extend(body.get("added",[])); modified.extend(body.get("modified",[])); removed.extend(body.get("removed",[]))
                cursor = body.get("next_cursor",cursor)
                if not body.get("has_more"): return {"added":added,"modified":modified,"removed":removed,"cursor":cursor}
            raise PlaidError("The bank returned too many pages. Contact support.")
        except PlaidError as e:
            if e.code != "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION" or attempt == 2: raise

def refresh_item(item_id):
    with _sync_lock:
        item = db.q1("SELECT * FROM items WHERE id=?",(item_id,))
        if not item or not item.get("access_token"): raise PlaidError("This account is not linked to a bank.")
        local_accounts = db.q("SELECT * FROM accounts WHERE item_id=?", (item_id,))
        if local_accounts and all(a["archived"] for a in local_accounts):
            return {"status":"skipped", "reason":"archived_accounts", "added":0, "modified":0, "removed":0,
                    "message":"All accounts on this connection are archived. Saved history is preserved."}
        try:
            changes = sync_transactions(item)
            meta = fetch_accounts(item["access_token"],item.get("env"))
        except PlaidError as error:
            if error.code != "ITEM_NOT_FOUND":
                raise
            # Plaid confirms this connection was removed or depermissioned.
            # Archive locally, never cascade-delete its imported history.
            c = db._conn()
            try:
                with c: _archive_connection(c, item_id)
            finally: c.close()
            return {"status":"archived", "reason":"connection_removed", "added":0, "modified":0, "removed":0,
                    "message":"Bank access has ended. Accounts were archived and saved history is preserved."}
        if not isinstance(meta.get("accounts"), list):
            raise PlaidError("The bank returned an incomplete account list. Saved history was not changed.", "INVALID_ACCOUNT_LIST")
        account_map = {a["plaid_account_id"]:a for a in db.q("SELECT * FROM accounts WHERE item_id=?",(item_id,))}
        now = datetime.now().isoformat(timespec="seconds")
        c = db._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            transaction_repair.init_schema(c)
            present_accounts = {a["account_id"] for a in meta["accounts"]}
            for provider_id, local in account_map.items():
                if provider_id and provider_id not in present_accounts and not local["archived"]:
                    # Closed/revoked accounts disappear from the complete
                    # accounts response. Freeze them before processing removals.
                    db.set_account_archived(c, local["id"], 1)
                    local["archived"] = 1
            tx_columns = {row[1] for row in c.execute("PRAGMA table_info(transactions)")}
            scope_update = "scope=COALESCE(transactions.scope_override,excluded.scope)" if "scope_override" in tx_columns else "scope=excluded.scope"
            transfer_update = "is_transfer=COALESCE(transactions.is_transfer_override,excluded.is_transfer)" if "is_transfer_override" in tx_columns else "is_transfer=excluded.is_transfer"
            category_update = ("category_id=CASE WHEN COALESCE(transactions.category_override,0)=1 "
                               "THEN transactions.category_id WHEN transactions.category_id IN (SELECT id FROM categories WHERE lower(name) IN ('uncategorized','uncategorised')) "
                               "THEN COALESCE(excluded.category_id,transactions.category_id) ELSE COALESCE(transactions.category_id,excluded.category_id) END") if "category_override" in tx_columns else "category_id=COALESCE(transactions.category_id,excluded.category_id)"
            name_update = "name=CASE WHEN COALESCE(transactions.name_override,0)=1 THEN transactions.name ELSE excluded.name END" if "name_override" in tx_columns else "name=excluded.name"
            # Newly granted accounts must be inserted before advancing the cursor.
            default_scope = next(iter(account_map.values()), {}).get("scope", "personal")
            for a in meta.get("accounts", []):
                if a["account_id"] not in account_map:
                    aid = "acct_" + uuid.uuid4().hex[:12]
                    c.execute("INSERT INTO accounts(id,item_id,name,official_name,type,subtype,scope,mask,balance,iso_currency,plaid_account_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (aid,item_id,a.get("name") or "Bank account",a.get("official_name"),a.get("type"),a.get("subtype"),default_scope,a.get("mask"),_balance(a),(a.get("balances") or {}).get("iso_currency_code") or "USD",a["account_id"],now))
                    account_map[a["account_id"]] = dict(c.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone())
            # Some banks grant the same real card through two linked items.
            # Explicitly verified aliases keep one authoritative feed. All
            # archived accounts retain frozen history and never absorb updates.
            account_aliases = transaction_repair.aliases(c)
            incoming_by_account = {}
            for t in changes["added"] + changes["modified"]:
                incoming_by_account.setdefault(t["account_id"], []).append({
                    "posted": t.get("date") or date.today().isoformat(),
                    "amount": round(-float(t["amount"]), 2),
                    "name": t.get("name") or "Bank transaction",
                    "merchant": t.get("merchant_name") or t.get("name") or "",
                    "pending": int(bool(t.get("pending"))),
                })
            for provider_id, account in account_map.items():
                if account["archived"] or account["id"] in account_aliases:
                    continue
                identity = {**account, "institution": item["institution"], "env": item["env"]}
                canonical = transaction_repair.automatic_alias_candidate(c, identity, incoming_by_account.get(provider_id, []))
                if canonical:
                    c.execute("INSERT INTO transaction_account_aliases VALUES(?,?,?,?)", (account["id"], canonical, "Verified complete duplicate bank history during sync", now))
                    c.execute("UPDATE accounts SET archived=1,scope=(SELECT scope FROM accounts WHERE id=?) WHERE id=?", (canonical, account["id"]))
                    account_aliases[account["id"]] = canonical
            for t in changes["added"]+changes["modified"]:
                a = account_map.get(t["account_id"])
                if not a: raise PlaidError("A new account is still being prepared. We will retry this sync.", "ACCOUNT_NOT_READY")
                if a["archived"] or a["id"] in account_aliases:
                    continue
                if c.execute("""SELECT 1 FROM transactions t JOIN accounts saved ON saved.id=t.account_id
                    WHERE saved.archived=1 AND t.plaid_transaction_id IN (?,?)""",
                    (t["transaction_id"], t.get("pending_transaction_id"))).fetchone():
                    # A provider may move/reissue an id under another account.
                    # Its original archived identity still owns the saved row.
                    continue
                pfc = t.get("personal_finance_category") or {}
                primary = pfc.get("primary", "")
                if t.get("pending_transaction_id"):
                    pending = c.execute("SELECT id FROM transactions WHERE plaid_transaction_id=? AND pending=1 AND account_id=?", (t["pending_transaction_id"], a["id"])).fetchone()
                    posted = c.execute("SELECT id FROM transactions WHERE plaid_transaction_id=?", (t["transaction_id"],)).fetchone()
                    if pending and not posted:
                        # Promote in place: a pending-to-posted replacement must
                        # keep the user's category, notes and receipt references.
                        c.execute("UPDATE transactions SET plaid_transaction_id=? WHERE id=?", (t["transaction_id"], pending["id"]))
                    elif pending and posted:
                        transaction_repair.merge_pending_replacement(c, pending["id"], posted["id"])
                previous = c.execute("SELECT * FROM transactions WHERE plaid_transaction_id=?", (t["transaction_id"],)).fetchone()
                candidate = dict(previous) if previous else {}
                candidate.update(account_id=a["id"], account_scope=a["scope"],
                    scope=candidate.get("scope_override") or a["scope"],
                    amount=round(-float(t["amount"]),2),
                    name=candidate.get("name") if candidate.get("name_override") else t.get("name") or "Bank transaction",
                    merchant=t.get("merchant_name") or t.get("name") or "",
                    personal_finance_category=pfc,
                    is_transfer=candidate.get("is_transfer_override") if candidate.get("is_transfer_override") is not None else int(primary in ("TRANSFER_IN","TRANSFER_OUT","LOAN_PAYMENTS")))
                suggestion = category_picker.choose(candidate, conn=c)
                selected_category = suggestion["category_id"] if suggestion else ("cat-income" if primary == "INCOME" and candidate["amount"] > 0 else None)
                sql = """INSERT INTO transactions(id,account_id,scope,amount,posted,name,merchant,category_id,pending,plaid_transaction_id,created_at,pending_transaction_id,is_transfer)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(plaid_transaction_id) DO UPDATE SET
                 account_id=excluded.account_id,{scope_update},
                 amount=excluded.amount,posted=excluded.posted,{name_update},merchant=excluded.merchant,pending=excluded.pending,
                 pending_transaction_id=excluded.pending_transaction_id,
                 {category_update},
                 {transfer_update}""".format(transfer_update=transfer_update, scope_update=scope_update, category_update=category_update, name_update=name_update)
                c.execute(sql, ("tx_"+uuid.uuid4().hex[:16],a["id"],a["scope"],round(-float(t["amount"]),2),t.get("date") or date.today().isoformat(),t.get("name") or "Bank transaction",t.get("merchant_name") or t.get("name") or "",selected_category,int(bool(t.get("pending"))),t["transaction_id"],now,t.get("pending_transaction_id"),int(primary in ("TRANSFER_IN","TRANSFER_OUT","LOAN_PAYMENTS"))))
                current = c.execute("SELECT id FROM transactions WHERE plaid_transaction_id=?", (t["transaction_id"],)).fetchone()
                if current:
                    receipt_store.invalidate_transaction(current["id"], conn=c)
            # Process removals last so a pending row can first be promoted to
            # its posted identity. Removed alias ids cannot delete canonical ids.
            for tx in changes["removed"]:
                c.execute("DELETE FROM transactions WHERE plaid_transaction_id=? AND account_id IN (SELECT id FROM accounts WHERE item_id=? AND archived=0) AND account_id NOT IN (SELECT duplicate_account_id FROM transaction_account_aliases)", (tx["transaction_id"], item_id))
            for a in meta.get("accounts",[]):
                local = account_map.get(a["account_id"])
                if local and not local["archived"] and local["id"] not in account_aliases:
                    c.execute("UPDATE accounts SET balance=? WHERE plaid_account_id=? AND item_id=?",(_balance(a),a["account_id"],item_id))
            c.execute("UPDATE items SET cursor=? WHERE id=?",(changes["cursor"],item_id))
            c.commit()
        except Exception:
            c.rollback(); raise
        finally: c.close()
        return {"added":len(changes["added"]),"modified":len(changes["modified"]),"removed":len(changes["removed"])}

def archive_account(account_id, restore=False):
    """Pause one account without changing any of its saved financial records."""
    with _sync_lock:
        c = db._conn()
        try:
            with c:
                changed = db.set_account_archived(c, account_id, 0 if restore else 1)
                if not changed: raise PlaidError("Account not found.")
        finally: c.close()


def _archive_connection(c, item_id):
    # Keep account ids, provider ids, transactions, receipt allocations, goals,
    # subscription references and learning intact. Never DELETE an item here:
    # the historical schema has cascading account/transaction foreign keys.
    for row in c.execute("SELECT id FROM accounts WHERE item_id=?", (item_id,)).fetchall():
        db.set_account_archived(c, row["id"], 1)
    c.execute("UPDATE items SET access_token=NULL,cursor=NULL WHERE id=?", (item_id,))


def remove_item(item_id):
    """Disconnect bank access and archive its accounts while preserving history."""
    # Serialize with in-flight refreshes so an old sync cannot write after the
    # disconnect, nor overwrite the cleared cursor/token or archived history.
    with _sync_lock:
        item=db.q1("SELECT * FROM items WHERE id=?",(item_id,))
        if not item: raise PlaidError("Account connection not found.")
        c = db._conn()
        try:
            if c.execute("SELECT 1 FROM cancellation_jobs j JOIN subscriptions s ON s.id=j.subscription_id JOIN accounts a ON a.id=s.account_id WHERE a.item_id=? AND j.status IN ('queued','running','needs_user')",(item_id,)).fetchone():
                raise PlaidError("Finish pending cancellation requests for this bank before disconnecting it.")
            if item.get("access_token"):
                try: _post("/item/remove",{"access_token":item["access_token"]},item.get("env"))
                except PlaidError as error:
                    if error.code != "ITEM_NOT_FOUND": raise
            with c: _archive_connection(c, item_id)
        finally: c.close()

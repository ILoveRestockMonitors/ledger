# Parallel implementation contracts

Root owns backend/server.py, backend/db.py, backend/analytics.py, backend/plaid_client.py, web/*.
Finance agent owns backend/subscriptions.py, backend/forecasts.py, tests/test_finance.py only.
Cancellation agent owns backend/cancellations.py, backend/codex_worker.py, scripts/cancellation-browser.mjs, tests/test_cancellations.py only.
Operations agent owns backend/auth.py, backend/scheduler.py, scripts/install-ubuntu.sh, scripts/backup.py, scripts/ledger.service, scripts/backup.service, scripts/backup.timer, requirements.txt, package.json, docs/INSTALL.md, tests/test_auth.py only.

Existing db.py exposes _conn(), q(), q1(), ex(), get_config(), save_config(), DATA_DIR, DB_PATH. All modules import db; roots are configurable via LEDGER_DATA_DIR (root will implement). New module init_schema() must be idempotent.

Subscriptions: init_schema(); scan() -> summary; listing(scope=None) -> {items,candidates,monthly_total,business_monthly,personal_monthly}; save(data)->record; review(id,decision)->record; monthly_plan(scope=None,month=None)->{spent,upcoming,total_expected,monthly_subscriptions,upcoming_items,paid_items}. Amounts positive expense amounts. Data fields id,merchant,scope,account_id,amount,cadence,next_due,status,confidence,reason,management_url,billing_channel,notes. status candidate/active/cancel_requested/canceled/dismissed. Root endpoints GET/POST /api/subscriptions, POST /api/subscriptions/scan,/review, GET /api/monthly-plan.

Forecasts: defaults(scope=None) -> input defaults; project(data)->{assumptions,series,summary}, series rows {year,label,contributions,conservative,base,optimistic,investments,cash,debt,real_value}. Inputs years,starting_cash,starting_investments,starting_debt,monthly_savings,monthly_investment,monthly_debt_payment,annual_return,inflation,debt_apr. Rates are percentages. Root GET /api/projections/defaults, POST /api/projections.

Cancellations: init_schema(); request(subscription_id)->job; listing()->jobs; get(job_id)->job; resume(job_id)->job; run_once()->optional job; status()->worker readiness. Jobs {id,subscription_id,status,message,created_at,updated_at,evidence,effective_date}. statuses queued/running/needs_user/completed/failed. Never finalize real cancellation in tests. Subscription completion requires evidence. Root endpoints GET /api/cancellations,/cancellations/status; POST /api/cancellations/request,/resume. No raw browser session tokens in API. Browser tool implementation must be explicit, no assumption of inherited desktop tools.

Auth: init_schema(); configured()->bool; setup(password)->token; login(password,remote='')->token; validate(token)->bool; logout(token); cookie helpers optional. Root owns HTTP headers/cookie/session plumbing. Tokens random, store hashes; password scrypt/PBKDF2; rate limit. Setup localhost only root handles. LEDGER_DEMO=1 bypass controlled in root ONLY for separate local demo data.
Scheduler: init_schema(); start()->stop event or equivalent; status()->dict; sync_all()->dict. Import plaid_client lazily; scheduled sync non-overlapping and per-item status. External calls never during tests. No logging secrets.

## Purchase lookup and sidebar — September 4, 2026

Receipt integration is implemented in `receipt_store.py` (queue, validation,
allocations), `receipt_service.py` (server coordination), `receipt_worker.py`
(local Codex Luna), and `scripts/receipt-browser.mjs` (read-only provider MCP).
GET `/api/receipts` and `/api/receipts/transaction?id=...`; POST
`/api/receipts/settings`, `/request`, `/resume`, `/review`, `/undo`.
Review accepts optional ordered `category_ids`; amounts stay fixed. Worker
finalization supplies `expected_attempt` from the claim to reject stale results.
Daily attempt limits are enforced transactionally when claiming, including
resumes. `allocation_map(ids)` supplies valid category splits; total spending
and transaction counts still use the original bank rows. Manual edits use
`manual_update`; Plaid refresh preserves overrides and invalidates changed
financial evidence. Public jobs include real boolean `verified` and `can_apply`.

`web/receipt-lookup.js` owns the small Transactions review drawer, detail modal,
category choices, original description, apply/undo, and Settings controls.
Automatic lookup remains off until configured. See INSTALL for dedicated
profile login and the headless-worker limitation. No live merchant account
was opened in development; protocol and accounting tests use isolated data.

Sidebar refinements live in `web/sidebar.css`, with state handling in
`comfort.js` and initial state in `index.html`: 248px desktop width, 78px compact
rail, native title labels, readable themed ink, mobile drawer preserved.
The wordmark moves 3px right/down and has 0.2px tracking. The collapsed choice
persists in `ledger-sidebar-collapsed`. Preserve Lora, cream paper, muted dark
card colors, and the existing fine divider treatment.

Validation: 95 unit tests passed; receipt bridge tests and JavaScript syntax
checks passed after the final worker changes. Browser checks covered desktop
collapse/reload/expand, both themes, a 390px mobile drawer, and applying/undoing
an isolated three-category synthetic receipt. The home-lab deployment has not
been updated by these UI/receipt changes.

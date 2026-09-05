# Ledger

A private finance dashboard for everyday spending, subscriptions, and the future you are planning. Built on the original Ledger.zip foundation with vanilla JavaScript, Python's standard library, SQLite, and locally bundled fonts.

The default appearance uses creamy paper surfaces, Lora headings, green and blue financial text, and warm copper details. Light, dark, and system modes are available. Settings also offers a colorful palette, font choices, spacing, and a simpler or fuller home layout.

## Start locally

Python 3.11 or newer is sufficient for manual tracking and the dashboard:

```bash
python3 backend/server.py
```

Open <http://127.0.0.1:8907/> and create your owner password. Your data stays in `backend/data/` unless `LEDGER_DATA_DIR` points elsewhere. Keep data outside the source directory for a permanent installation.

For a separate preview with synthetic data and bank/cancellation actions disabled:

```bash
LEDGER_DATA_DIR=/tmp/ledger-demo LEDGER_DEMO=1 LEDGER_PORT=18907 python3 backend/server.py
```

Open <http://127.0.0.1:18907/>. Use a dedicated demo directory; sample data must not mix with real bank data.

## What is included

- A home dashboard with monthly spending, pending and expected charges, net worth, recent activity, upcoming payments, and quick transaction entry.
- Manual accounts and transactions; account balances update when manual transactions are entered or deleted. Transfers stay out of income and spending totals.
- Plaid Link in Sandbox or Production, bank reconnection, incremental transaction syncing, and background sync status. Plaid credentials are saved on the server and redacted from API responses.
- Persistent subscriptions with cadence, next payment, billing channel, management links, notes, and cancellation state. Recurring charges become review candidates when uncertain; known subscription price changes get a separate review.
- Monthly subscription reconciliation that counts actual payments and remaining expected commitments without counting both for the same due payment.
- Cancellation requests queued for a local Codex Luna worker. Jobs pause for login or other user action; completion requires provider text, URL, date, and a matching browser receipt. Sending a request alone never marks a subscription canceled.
- Net worth and investment scenarios with adjustable savings, contributions, returns, inflation, horizon, and debt assumptions. These are illustrations, not forecasts of actual market performance.
- Category budgets, savings goals and contributions, personal/business views, transaction search and notes, CSV export, account archive and restore.
- Reports with a calendar-year selector, all 12 monthly spending totals, yearly and all-time recorded spending, and personal/business filters. Historical reports include archived accounts and exclude pending charges and transfers. Category detail, recent heatmap, and income sources remain available below the overview.
- Purchase lookup for unclear Amazon, Apple and Google charges, using a separate local Codex receipt worker. Verified items can be allocated across category budgets without duplicating the bank charge. Original bank descriptions and manual choices are retained, with review and undo controls in Transactions. Automatic lookups are off until enabled in Settings after setup.
- Single-owner login, private deployment, scheduled syncing, and an encrypted backup utility.

## Home lab installation

See [the Ubuntu and Docker guide](docs/INSTALL.md). The Docker deployment runs as a non-root user with persistent data and publishes only to host loopback. Tailscale Serve or an SSH forward provides private access from other devices.

Plaid production access and your own credentials are required for real banks. Enter credentials in Ledger Settings after signing in. OAuth bank flows also need the private HTTPS return URL registered in your Plaid dashboard.

The optional cancellation worker uses a ChatGPT-authenticated Codex CLI and requests `gpt-5.6-luna`; it rejects API-key login. Model access and usage limits follow your account. Provider login, MFA, CAPTCHA, phone-only cancellation, or account-specific terms can require your involvement. The Docker browser is headless; a visible browser handoff requires the documented GUI worker setup.

## Validation and boundaries

Run isolated checks with:

```bash
python3 -m unittest discover -s tests -v
```

Bank responses and model execution in tests are mocked. Live production bank linking and subscription cancellation require your account setup and have not been used as tests. Projection history is reconstructed from balances and transactions; it does not include historical market prices or holding-level performance.

Purchase lookup also needs merchant sign-in in the worker's dedicated browser profile. Signing in to Amazon, Apple or Google in the Ledger app's browser does not sign in the worker. Unmatched, grouped or partially funded orders can require review. Receipt lookup does not access email, make purchases, request refunds, or cancel orders. Live merchant receipt retrieval requires setup and has not been used as a test.

Source files and generated releases exclude databases, bank secrets, browser profiles, and Codex login credentials. The app requires its server; it is not a standalone offline phone app.

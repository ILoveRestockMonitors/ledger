# Cash and manual transactions

Transactions includes an **Add cash transaction** action. The Home shortcut, sidebar action, mobile action and appearance-specific flows open the same form. Choose **Cash / manual (no account)** to record money without attaching it to an account.

Cash entries support Personal or Business scope, money in, money out, transfer in, transfer out, amount, merchant/name, date, category and note. They can later be edited, marked recurring or deleted. They participate in transaction filtering, category rules, budgets, reports, cash flow and CSV export. They intentionally do not change an account balance or reconstructed net-worth history.

Selecting an account preserves the existing behavior: a manual-account transaction updates that account, while linked-account amount and date protections remain in force. The server accepts a null account only with a valid scope and rejects zero, non-finite or future-dated cash entries.

The production release is `20260919-cash-transactions`. It was built as a six-file overlay on the verified main and Sarah baselines. Both hosted containers passed health, runtime-hash and HTTPS-asset checks. Eight focused backend tests passed across the exact variants, JavaScript syntax and UI wiring passed for both, and the broader suite had no regression delta from the untouched baselines. A desktop and 390×844 mobile preview confirmed the form fits without horizontal overflow.

Production database backups and recovery snapshots remain on the deployment host under `/home/sneezy/Ledger-cash-transactions-20260919/`. The rollout audit found no account, transaction, budget, category or goal changes; only normal service-start timestamp refreshes occurred.

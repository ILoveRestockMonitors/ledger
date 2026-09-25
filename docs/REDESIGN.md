# New layout — Everything / Personal / Business

Released September 25, 2026 on top of V2.2.0. Financial records, bank sync, workers and APIs are unchanged; the only backend change is one new preference (`layout`).

## What changes

- **One switch for whose money you're looking at.** Everything, Personal or Business sits at the top of Home, Transactions and Budgets, shows each side's net for the month, re-tints the page (Personal warm, Business cool) and filters every figure. It is remembered per browser. The separate Personal and Business pages are folded into it.
- **Home** is rebuilt around the switch: net worth with the accounts behind it, a row that changes with the scope (spending split and reviews; rent-free spending, runway and savings; tax set-aside, deductibles and clients), the monthly plan or scope budgets, stacked monthly spending, the spend constellation with category detail, recent activity with a one-tap Personal/Business move, upcoming subscriptions and goals.
- **Transactions** adds spending at a glance (every category on one bar, categorized vs uncategorized, tap a category to filter, tap Uncategorized to list only those), a category picker in each row (the existing "apply to matching purchases" prompt still follows), a Personal/Business toggle per row, bulk moves, and an offer to move the other purchases from the same merchant. Every move has Undo. Receipts, notes, edit, filters and pagination are kept.
- **Budgets** lists every category with spending, budgeted or not, with over / near limit / on track status, an Uncategorized row with a shortcut to sort it, budget health, "Set budget" for unbudgeted categories, the month picker and the monthly history.
- Surfaces are cleaner (one corner radius instead of Sarah's leaf-shaped cards and buttons). Sarah's forest video, leaf-shaped constellation, Cornelious' storm/sunfire videos, lightning and fire hovers, card tints and all other animations are kept. Pause animations and reduced motion are respected.

Files: `web/redesign.js`, `web/redesign.css` (loaded last in `web/index.html`), the `layout` preference in `backend/db.py` / `backend/server.py`, and the demo preference allowlist in `web/demo.js`. The classic pages are untouched and stay registered underneath.

## Deploy

Frontend files plus the small config change. From the home-lab checkout used by each hosted app (main and mobile deployment), update the code and rebuild the same way you normally do, for example with Docker:

```bash
git fetch origin && git checkout main && git pull --ff-only
docker compose build && docker compose up -d
```

or, for the systemd install, `sudo ./scripts/install-ubuntu.sh --mode update --source-dir "$PWD" --app-dir /opt/ledger --data-dir /var/lib/ledger`. Home-screen iPhone apps and the connected Windows launcher use the hosted app, so they update on their next reload. The standalone Windows package needs a rebuild with `desktop/build_windows.py` and a reinstall. Data directories are not touched.

## Revert

Pick whichever is easiest; none of them touch your records.

1. **Instant, no redeploy:** Settings → Layout → **Classic layout**. It is saved on your Ledger, so every device and home-screen app switches after a reload. Choose **New layout** to come back.
2. **One browser only:** open Ledger with `?layout=classic` (or `?layout=new`). Settings shows a "Use the saved setting" link to clear it.
3. **Remove the code:** revert the pull request that added this layout on GitHub (Revert button), or check out the `pre-redesign` tag on the home lab and rebuild. The extra `layout` preference is ignored by older versions.

If the new layout ever fails to load a page, that page falls back to the classic version automatically and says so.

## Validation

Tested against the Ledger server with sample data in Chromium: Sarah and Cornelious, light and dark, 1440px desktop and 390px phone; scope switching, one-tap and bulk moves with Undo, the same-merchant prompt, category changes with Undo, the Uncategorized filter, setting and removing budgets, Classic/New switching and the per-browser override, with no page errors. The backend suite has 148 tests; 145 pass and the same 3 fail with and without this change (two date-sensitive finance tests and one Plaid removal test). Native iPhone Safari and the Windows package were not tested.

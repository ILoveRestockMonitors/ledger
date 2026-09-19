# Sidebar demo version

The sidebar offers **Demo version**, replacing the document with the same app at `?demo=1#overview`. In demo, that control reads **Return to my Ledger**. A banner identifies fictional, read-only finances and a compact header badge stays visible while scrolling. Desktop, collapsed navigation and the phone drawer use the same control. Reloads and route navigation retain demo selection through the URL.

A dedicated `/api/preview/` boundary serves a curated temporary SQLite database. It shares the application's calculations, filtering and rendering. A request-local context selects storage without changing the live database/configuration paths or worker configuration. Authentication and origin checks still apply. Only explicitly listed reads and the non-persisting projection calculation are available; unknown endpoints and financial/configuration writes are rejected. Worker and sync status responses are synthetic. CSV exports and purchase details also use demo records.

The fictional Alex / Juniper Studio scenario includes five accounts, twelve calendar months of transactions, eight budgets, three savings goals and eight recurring payments, including a candidate and price review. Dates follow the current calendar; no transactions are future dated, and paired savings transfers are excluded from income/spending. Daily regeneration happens only in temporary storage. No production seeding or reset is involved.

Presentation preferences use a separate session-storage entry. Projections remain interactive. Financial editing, bank linking/syncing and receipt/cancellation assistants are unavailable. Settings routes users into the separate demo rather than the old sample-insertion action. A full navigation discards page caches, transaction filters, forms, receipt state and projections when changing mode.

Alternatives considered: inserting sample rows into the live workspace risks mixing records; static JSON snapshots require duplicate filtering/calculation logic and can show stale figures. A separate temporary database preserves the existing app's behavior with a small, explicit API boundary.

Validation covers authorization, all demo reads, write denial, unknown endpoints, private IDs, CSV contents, filters, projections, concurrent live/demo access, context cleanup after failure and calendar boundaries. Browser checks cover both palettes/themes at 320, 390, 768 and 1440 pixels, refresh persistence, sidebar switching and restoration of private fixture records and preferences.

Implemented locally, then deployed to both hosted services with user authorization on September 6 as `20260906-demo-qa`. Download packages and physical iPhone/Safari verification remain outside this rollout.

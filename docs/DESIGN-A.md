# Design A release — 2026-10-14

Net worth leads Home; compact Activity rows open an edit sheet; mobile navigation
includes Add. Existing page renderers provide Budgets, Subscriptions, Goals,
Accounts, Reports and Settings. Personal is orange and Business purple in the
Cornelious palette. The Sarah palette maps the same layout to its existing color,
font and background tokens and retains the posted-spending-without-rent card.
All animation and media files remain unchanged.

Bank-backed entries expose Name / merchant without permitting amount/date edits;
unchanged names do not create overrides. The demo permits the read-only budget
overview route. The static artifact's API shim and recorded data are excluded.

Load frontend-a.css, frontend-a-theme.css and frontend-a.js last, after redesign
and home-cache. Older hosted variants need home-cache.js and redesign.css/js too.
An existing browser can use ?design=current to return to the preceding layout,
or ?design=a to enable Design A. Existing Classic layout preferences are honored.

Validation: 126 isolated fictional-data checks across 320/390/1440px, light/dark,
both palettes, nine pages, bank-name validation/save and Sarah rent detail.
Deployment compares full application manifests and all HTTPS patch bytes,
checks SQLite integrity and financial-table fingerprints, and retains previous
images, compose and source copies. Native iPhone Safari/VoiceOver are not tested.

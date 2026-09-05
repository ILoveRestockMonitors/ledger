# Ledger V2 — Sarah & Cornelious

Approved September 5, 2026. This release applies the approved design to the existing full Ledger app; financial storage, authentication, bank sync, cancellation workers and APIs remain unchanged.

- **Sarah:** Lora typography, translucent green and blush pink, leaf-shaped surfaces and sidebar, and a woodland stream background.
- **Cornelious:** Manrope typography and Aurora iris/cyan glass surfaces.
- Select either palette in the header, then choose light or dark. Palette preferences persist on each browser/device.
- Animated tint layers, sidebar labels, cards, spending bubbles and controls; animated palette and light/dark transitions.
- Sarah uses a silent 1280 × 720 video with a 0.75-second tail-to-head dissolve for a 5.292-second loop. Its still fallback retains the generated native 1672 × 941 resolution.
- Pause animations and reduced-motion preferences stop ambient movement. Hidden tabs and offscreen elements pause where supported.
- Responsive desktop, tablet and phone layouts retain transactions, accounts, budgets, subscriptions, manual cancellation tracking, projections, reports, goals, receipts, import/export and settings.

## Platforms

The same web assets serve the main Docker app, independent mobile deployment, installed iPhone home-screen app, and connected Windows launcher. The standalone Windows package includes its own local backend and the same V2 frontend. Existing records remain in the original data directory. Native iPhone and Windows first-run behavior requires validation on those devices.

The separately hosted design showcase uses fictional snapshot data. It is not connected to real accounts and does not save financial changes.

## Release and rollback

Deploy frontend overlays onto each existing production image so worker dependencies and private configuration remain intact. Back up each compose file, configuration and SQLite database first. Keep the previous image tags for rollback; restore the previous compose image and recreate only the Ledger service if necessary. Never replace the persistent data directories with demo data.

Runtime assets are in `web/`. The generated video is a bundled local asset: no generation API or API key is needed by the deployed app. Comparison screenshots, generation credentials and provider job records are excluded.

The historical reconstruction document describes the earlier base. Use the V2 tagged repository or V2 source release to reproduce this version.

## Mobile fit correction

The V2 release also addresses two emailed iPhone screenshots: toolbar controls now fit at 320 CSS pixels, and the leaf drawer is capped at 280 pixels with tighter navigation spacing, safe-area padding and independent scrolling. Verified at 320 × 693 and 390 × 844; 44-pixel tap targets are retained.

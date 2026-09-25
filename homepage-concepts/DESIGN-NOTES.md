# Design notes

Self-authored under explicit creative delegation. The request was five new homepage designs for Ledger, from scratch, inspired by the Dollarwise budgeting app and built with scroll-craft, as a homepage template only, for approval before the rest of the app.

## Brief

- **What this is:** the Home screen of Ledger, a private finance app for one owner's personal money and a small studio business.
- **What the visitor must believe by the end:** "I know where I stand this month, and nothing is waiting on me."
- **The one action:** the weekly check-in (answer the charges Ledger is unsure about). Adding a transaction is the secondary action.
- **Taken from Dollarwise:** the 50/30/20 split of needs, wants and savings, sorted automatically and easy to change; a single spendable number; a short weekly review habit; plain language for beginners.
- **Kept from Ledger:** Everything / Personal / Business scope, net worth and accounts, budgets, upcoming bills and paydays, goals, and the review queue for recurring charges and price changes.
- **Assets:** none generated. Every page is type, color, SVG and live markup computing from `shared/ledger-sample.js`. No invented numbers.

## Five page styles, one each

scroll-craft defines eight page grammars that each forbid what the others require. Each concept uses a different one, so no two share a structure. Filmic one-shot, continuous world and gallery were not used: the first two need video footage and one continuous place, and a gallery suits a product range more than a daily dashboard.

| # | Concept | Grammar | Navigation | First screen | Ending | Signature move |
|---|---------|---------|------------|--------------|--------|----------------|
| 1 | Console | Live surface | Real app chrome: sidebar, scope tabs, phone tab bar | The dashboard already in today's state | A real input: one-line transaction entry that updates every panel | Scroll moves a date cursor through the next 30 days; bills and paydays land and projected cash moves (draggable too) |
| 2 | The Seam | Split stage | The divider itself carries labels, progress ticks and the Everything net | Personal and Business at 50/50, both headlines readable | The collapse: the divider travels to the side with open items, which takes the page and holds the reviews | Dragging the divider is the scope switch; release near an edge and that side takes the full width |
| 3 | The Almanac | Chaptered editorial | Folio in the margin that follows the chapter | A title page, type only | Colophon, with the call to action as a line of running text | Every dollar figure is a numbered footnote that opens its receipt (the transactions or math that make it up) |
| 4 | The Poster | Typographic poster | Wordmark set vertically as part of the composition; scope as three small words | One number at poster scale | The page inverts to cream, smallest type on the site, plain underlined links | NEEDS, WANTS and SAVINGS gain weight and width day by day as scroll replays September |
| 5 | Pulse | Rhythmic cutlist | A loud bar: wordmark, gauge and Check in at equal weight, plus a balance ticker | "Your week. Six things. Two need you." | Abrupt full-bleed Check in button | The gauge in the bar replays the week, draining and refilling per cut; at the peak the bar unfurls to show what is left |

Each row differs from every other row on all six fingerprint dimensions.

## Feeling curves

- **Console:** oriented (today, at a glance) → curious (the future plays out) → in control (budgets, goals) → done (added and updated).
- **The Seam:** balanced (two sides even) → comparing (row by row) → tipped (one side needs you) → resolved (answered, the line returns to center).
- **The Almanac:** settled (a letter) → understood (receipts behind every number) → prepared (what is coming) → hopeful (what you are building) → finished (the week reviewed). Peak: opening a receipt.
- **The Poster:** struck (one number) → grounded (what it means per day) → seeing (the type fills with the month, the peak) → aware (what cost the most) → quiet (the inverted close).
- **Pulse:** energized (your week) → quick recognition per cut → relief (the bar opens: under pace, the peak) → focused (the two questions) → done.

## Verification

Checked in headless Chromium at 1440 by 900 and 390 by 844, walking each page top to bottom: no script errors, no sideways scrolling, pinned sections hold, and the first screen of every page is complete before any scrolling. Not checked: a real iPhone or Android device, Safari, keyboard-only walkthroughs of every control, and screen readers.

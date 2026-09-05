# Shared brief — Ledger home page concepts

You are drawing ONE home-page concept for **Ledger**, a private, single-owner
personal finance dashboard (vanilla JS + Python + SQLite, self-hosted, no
marketing site). The "home page" is the app's **Home / Overview dashboard** —
the first screen after sign-in. Desktop width.

Ledger's voice is quiet, warm and human. Never "Dashboard", "KPI", "Analytics",
"Optimize". The real product copy reads: "Here's where things stand.",
"A little more peace of mind.", "Small steps. More possibilities.",
"Keep what earns its place.", "Made for your everyday."
Match that register exactly. No exclamation marks. No emoji anywhere.

---

## 1. The real design system (lifted from `web/`)

Default appearance is `data-palette="paper"` `data-theme="light"` `data-font="lora"`.
These are the EXACT resolved token values — use them literally, do not round:

```
--bg:          #fffaf4   warm paper ground
--bg-soft:     #fbf5ed
--panel:       #fffdf9   card surface
--panel-2:     #f7ede3
--text:        #373a32   body ink
--ink:         #30372f   headline ink
--muted:       #737365
--faint:       #868274
--border:      #2b3b49   strong rule (dark slate — Ledger's signature hairline)
--border-soft: #71808b
--accent:      #656c48   olive
--accent-2:    #989772
--green:       #53725e   money in
--red:         #a35642   money out / over plan
--amber:       #9c7f37
--cyan:        #526f76
--soft-accent: #f8ece2   warm blush fill
--rail:        #b8b294   expected-spend rail
--copper:      #c18f68   warm copper detail (active nav marker)
--copper-ink:  #ad7956   copper on type
--shadow:      0 4px 16px rgba(87,75,47,.03)
--radius:      14px
```

Merchant-avatar tints (rotate by merchant): `#ece8fc/#8a6abb`, `#e2f1ec/#3a947c`,
`#fceade/#ba7a50`.

Real component metrics (copy these, don't invent):
```
.card            padding 22px 24px; border 1px solid var(--border-soft);
                 border-radius 14px; box-shadow 0 3px 12px rgba(16,43,64,.06)
.card h3         15px/600, color var(--text), margin-bottom 16px, flex row-between
.stat-value      31px, weight 550, letter-spacing -1.1px, color var(--ink)
.hero-card .stat-value  34px, margin 10px 0 5px
.stat-label      11px, weight 550, letter-spacing .1px
.welcome h2      27px, weight 550, letter-spacing -.8px, color var(--ink)
.welcome p       13px, color var(--muted)
.hero-grid       grid 1.3fr 1fr 1fr, gap 18px, margin-bottom 23px
.hero-card       min-height 169px
.hero-card.primary  background var(--soft-accent), border color-mix(accent 15%, border-soft)
.home-section    grid minmax(0,1.55fr) minmax(260px,1fr), gap 20px, align-items start
.transaction-row flex, gap 13px, padding 13px 0, border-bottom 1px solid var(--border-soft)
.merchant-avatar 37x37, border-radius 12px, weight 600, 14px
.money-number    13px/600, tabular-nums, white-space nowrap
.card-footer     margin-top 14px; padding-top 13px; border-top 1px solid var(--border-soft);
                 11px, var(--muted), flex space-between
.quiet-note      11px, line-height 1.8, var(--muted), margin-top 14px
.spend-rail      height 6px, radius 6px, flex; spent = var(--accent), expected = var(--rail)
.review-strip    border 1px solid, radius 14px, padding 15px 19px, flex gap 13px
.period-pill     border 1px solid var(--border), radius 9px, padding 7px 12px, 12px
.metric-foot     11px, var(--muted), flex gap 7px
#sidebar         218px wide, padding 32px 18px 18px, background var(--bg-soft),
                 border-right 1px solid var(--border)
#topbar          height 78px, padding 0 42px, border-bottom 1px solid var(--border)
.owner-avatar    34px circle, background var(--soft-accent), color var(--accent)
```

Logo: a 44×44 square with 1px `--border` rule, radius 3px, containing `L·` in
Georgia 28px — `L` in `--accent`, the `·` in `#ad7956`. Beside it the wordmark
`ledger.` in Lora 30px/600, letter-spacing −1.2px, and under it, in Georgia
italic 10px, `A little more peace of mind.`

Navigation (real order): Home · Transactions · Subscriptions · Your future —
then section label "A closer look": Budgets · Goals · More insights — then
section label "Your setup": Accounts · Settings.

**Fonts** load in `<helmet>` from Google Fonts (the only permitted host):
`<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=...&display=swap">`
Always give a real fallback stack. Your assigned faces are in your own spec.
Never use Inter, Roboto, Arial or Fraunces.

**Icons**: inline SVG only — stroke-based, 1.5px stroke, 20px or 16px grid,
`currentColor`, one consistent style. Never emoji, never dingbat glyphs.

---

## 2. The content model — the same numbers in every concept

Use these EXACT figures and names. They are internally consistent; do not
change or re-derive them. September 2026, viewed on Sep 5.

**Greeting** — "Good afternoon," / "Here's where things stand." / pill: `September 2026`

**Three hero figures**
| | |
|---|---|
| Room in your monthly plan | **$485.20** |
| — supporting | $2,714.80 spent or expected · $3,200.00 plan |
| — rail | spent 71.8% (accent) + expected 13.0% (rail) of plan |
| — foot | Tracked commitments only · other spending may still come up |
| Spent so far | **$2,298.33** |
| — supporting | $343.26 / month in subscriptions |
| — foot | $86.20 also pending |
| Your net worth | **$48,915.00** |
| — supporting | Assets, less what you owe |
| — link | See what's possible → |

**Review strip** — icon ↻ · "A few payments look recurring." /
"A quick check helps keep your monthly picture accurate." / button `Review 2`

**Recent activity** (5 rows: merchant · category · date · amount)
```
Paycheck              Income        · Sep 1            +$2,480.00
Con Edison            Utilities     · Sep 3 · Pending    $88.40
Trader Joe's          Groceries     · Sep 4             $63.18
Spotify               Subscriptions · Sep 4             $12.99
Coffee with a friend  Dining        · Sep 4              $4.75
```
footer: "Everything in one place." · "View all →"

**Still to come · this month** (date chip · merchant · cadence · amount)
```
Sep 8   iCloud+         monthly payment    $9.99
Sep 12  Verizon Fios    monthly payment   $89.99
Sep 15  Car insurance   monthly payment  $142.30
Sep 17  New York Times  monthly payment   $25.00
Sep 22  Peloton         monthly payment   $44.00
```
footer: "$330.27 expected" · "Subscriptions →"
NOTE: seven tracked payments remain this month, totalling $330.27; the five above
are the ones shown (the app truncates this list). The two not listed are
Figma $16.00 on Sep 26 and Google One $2.99 on Sep 28. So never label the visible
list "5 items" against the $330.27 total — write "5 of 7 shown", or show no count.

**Money in, money out · 6 months** (income, spending)
```
Apr  4,960 / 3,412      Jul  4,960 / 3,120
May  4,960 / 2,884      Aug  5,480 / 2,948
Jun  5,210 / 3,706      Sep  2,480 / 2,298   (month in progress)
```
note: "Posted income and spending. Transfers between accounts stay out."

**A little closer** (goals)
```
Emergency fund   68%   $6,800 of $10,000
Trip to Lisbon   41%   $1,230 of $3,000
New laptop       22%   $396 of $1,800
```
note: "Small, steady progress counts."

**Budgets this month** (only if your spec asks for it)
```
Groceries       $486 / $550      Subscriptions  $343 / $350
Dining          $312 / $300  over Home           $1,009 / $1,050
Transport       $148 / $200
```

**Accounts / net worth breakdown** (only if your spec asks for it)
```
Everyday Checking  Chase     $4,182.16
Savings            Ally     $12,640.00
Brokerage          Fidelity $38,410.44
Sapphire card      Chase    −$1,284.02
Student loan       Nelnet   −$5,033.58
                            = $48,915.00
```

**Subscriptions at a glance** — 8 active · $343.26 / month · $4,119.12 a year at this pace

Primary action, wherever one is needed: **Add a transaction**.
Secondary: Link account · Sync banks · Export.

---

## 3. The file format you must write

One file, a Design Component (`.dc.html`). Exact skeleton:

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lora:wght@400;500;600&display=swap">
  <style>
    body { margin: 0; }
    a { color: #656c48; text-decoration: none; }
    a:hover { color: #30372f; }
  </style>
</helmet>
<div style="...">  <!-- your design, one fixed-width root -->
</div>
</x-dc>
</body>
</html>
```

Hard rules — every violation below fails **silently**:

1. Keep the `<script src="./support.js"></script>` head line EXACTLY as written.
   Do not inline it, do not remove it.
2. **Write NO `<script data-dc-script>` block at all.** These are static
   mockups. No JS, no props, no `{{handlebars}}` holes, no `<sc-for>`,
   no `<sc-if>`, no `<dc-import>`. Every value is literal text in the markup.
3. Canonical HTML: close every non-void element, double-quote every attribute.
4. **Inline `style="..."` attributes for everything the viewer might restyle** —
   colors, spacing, type sizes, borders. Use `<helmet><style>` only for the
   font `@import`/link, `body` reset, `a`/`a:hover`, `@keyframes`, and
   pseudo-elements you genuinely cannot inline. Prefer inline styles.
5. **Lay out every sibling group with flex or grid + `gap`** — never rely on
   source whitespace, `<br>`, or per-element margins for spacing between
   siblings. Direct-manipulation editing depends on this.
6. The root element is a FIXED width matching your assigned frame width, with
   an explicit background color (surplus frame area must not show through as
   white). Set `overflow: hidden` nowhere — let it be the natural height.
7. Tabular figures everywhere money appears: `font-variant-numeric: tabular-nums`.
8. No fake browser chrome, no fake OS status bar, no fake window controls.
9. All interactive-looking hit targets ≥ 36px tall (desktop); ≥ 44px if your
   spec says phone.
10. Real, specific copy only — the strings above. Never lorem ipsum, never
    invented figures, never placeholder names.

Charts and sparklines: draw them as inline `<svg>` with hand-computed
coordinates. Give every `<svg>` a `viewBox` and `role="img"` with an
`aria-label` naming what it shows. Bars/areas use the palette's `--green`
(#53725e) for money in and `--red`/`--accent` for money out; never a rainbow.

Write the file and nothing else. Do not run any other command, do not modify
any other file, do not create extra files, do not commit.

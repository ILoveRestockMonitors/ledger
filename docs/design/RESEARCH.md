# Design study — building Ledger to a Refero Styles standard

Research notes behind the three homepage mockups in `mockups/`. The brief: make every
pixel look like it deserves a spot on styles.refero.design — simple on the surface,
meticulous underneath.

## What Refero Styles actually rewards

Refero Styles is a curated library that breaks a real product's visual language into
colors, typography, spacing, motion and component patterns, published as machine-readable
`DESIGN.md` files. The lesson from how those files are written:

- **A style is a set of constraints, not a mood board.** Every catalogued system is
  defined as much by its *do-not-use* rules as by its palette.
- **Concrete values or nothing.** `#5266eb`, `4px base`, `radius cap 8px`, `120ms ease-out`.
- **One accent, held to one job.** Nearly every strong system in the catalog restricts its
  saturated color to primary action, link, and focus ring.
- **Restraint reads as expensive.** Vercel's system states it outright: "we don't need a
  color to look expensive."

Each mockup here therefore ships with its own token block at the top of the file and a
stated set of rejections — the same shape as a `DESIGN.md`.

## Finance products studied (18)

| Product | The one thing worth stealing |
|---|---|
| **Mercury** | Warm cream canvas `#f6f5f2`, warm-gray ink `#2a2924`→`#8a8478`, and indigo `#5266eb` as *the only saturated color on the page*. Tabular numerals mandatory; currency symbols set lighter than the value. |
| **Ramp** | Density as a feature — pros live in the product, so speed beats breathing room. Leads with total spend + anomalies rather than a balance. |
| **Stripe** | Five numbers with sparklines beneath. Financial data packed tight, UI chrome spaced generously — the gap itself is a typographic decision. |
| **Brex** | Dense finance-team views; hierarchy carried by weight and rule, not by boxes. |
| **Monzo** | Hot Coral deliberately reads *un-bank-like*. Color-coded categories made financial awareness automatic. Custom display/text pair (MonzoSansDisplay/Text). |
| **Revolut** | Product UI is nearly achromatic — white surfaces, `#1f1f1f` ink, hairline `#c9c9cd` rules — while marketing runs 136px Aeonik at `-2.72px` tracking. Chromatic tokens reserved for *state* (`#e23b4a` danger, `#00a87e` teal). |
| **Wise** | White + space so the single lime `#9FE870` tells you where to click. |
| **Robinhood** | Card modularity; green/red movement animation as the core signal. |
| **Cash App** | Bold for finance — dark canvas, oversized type, identity as a design object. |
| **Copilot Money** | Best-in-class craft: typography, motion, color and information density all deliberate. Feels like a native app, not a dashboard. |
| **Monarch** | Neutral palette, collapsible panels, expandable charts, *no gratuitous animation*. |
| **YNAB** | Forward-looking allocation screens instead of backward-looking reports. Structure follows philosophy. |
| **Betterment** | Contextualizes performance against long-term goals to damp reaction to noise. |
| **Klarna** | Aesthetics carried in function as much as form. |
| **N26** | 19 tokens across brand-teal/rhubarb/gold/slate-blue/ink/surface; 80px hero down to 14px caption; `+0.3px` letter-spacing on every reading size. |
| **Coinbase** | `#0052ff` primary on a 16px spacing increment; separate display/sans/text cuts. |
| **Nubank** | *Roxinho* purple as a defensible, single-color brand conviction. |
| **Toss** | The finance-specific rulebook: Toss Blue `#3182f6` is the only branded hue, `#00c896`/`#f04452` reserved for state, tabular figures globally on money, 64px dense rows, `scale(0.98)` at 96ms on tap. |

**Synthesis — the five rules every good finance UI obeys:**

1. Lead with a single trusted number, sized far larger than anything near it.
2. Tabular figures on every monetary value, always; align decimals.
3. One brand hue. Green and red are *state*, never decoration.
4. Density where the data lives, generosity around the chrome.
5. Set the currency symbol lighter/smaller than the digits.

## Animation-led sites studied (14)

| Site | The technique |
|---|---|
| **Linear** | Motion as confirmation, never spectacle. Purple only on action, link underline, focus ring. |
| **Vercel** | Flat, border-only depth; hover *strengthens a border* rather than lifting a card. |
| **Framer** | Springs for anything interruptible; easing curves for state changes. |
| **Arc** | Glass: `backdrop-filter: blur()` on every surface, inner highlight `inset 0 1px 0 rgba(255,255,255,0.6)`, fixed gradient with content scrolling over it. |
| **Runway** | Cinematic dark: oversized display type as a feature, `scale(1.02)` hover, border shifts to accent over 300ms, focus glow rings. |
| **Lusion** | Scroll-synced state; interaction that advances a narrative. |
| **Active Theory** | Bloom and dispersion — light as a material. |
| **Igloo Inc** | Every object encased in its own volume; camera drift between scenes. |
| **Cuberto** | Sequence scrolling via ScrollTrigger; parallax reveal. |
| **Made With GSAP / By-Kin** | Weighted smooth scroll, orchestrated page transitions. |
| **Apple** | Scroll as a timeline scrubber. |
| **Awwwards SOTY** | The best animated sites of 2026 are also the *fastest* — beauty at 60fps is the discipline. |
| **animations.dev (Emil Kowalski)** | The rules used verbatim below. |
| **2026 trend read** | After years of elaborate scroll effects, the best products pulled back toward faster, simpler, purposeful feedback. |

**Motion contract applied to all three mockups:**

- Entering/exiting → `ease-out`. Moving on-screen → `ease-in-out`. Hover → `ease`.
  Never `ease-in` (the delayed start reads as sluggish).
- Micro-interactions 100–150ms; standard UI 150–250ms; panels 200–300ms. Nothing over 300ms.
- Exits ~20% faster than entrances. Larger elements move slower than small ones.
- Animate `transform` and `opacity` only — they skip layout and paint.
- Start from `scale(0.95)`, never `scale(0)`. Press feedback is `scale(0.97)`.
- Paired elements share one duration and one curve.
- Springs only where a gesture can be interrupted; bounce kept to 0.1–0.3, or none.
- `prefers-reduced-motion: reduce` disables everything, no exceptions.
- Counters fire on `IntersectionObserver`, not on load, so nothing animates off-screen.

```css
--ease-out-quart: cubic-bezier(0.165, 0.84, 0.44, 1);
--ease-out-expo:  cubic-bezier(0.19, 1, 0.22, 1);
--ease-in-out-cubic: cubic-bezier(0.645, 0.045, 0.355, 1);
```

## The three directions

| | **Aurora** | **Quiet** | **Almanac** |
|---|---|---|---|
| Brief | Futuristic | Minimalist | The surprise |
| Lineage | Runway × Arc × Igloo | Linear × Vercel × Mercury | Granola × Mercury × Toss, on Ledger's own paper DNA |
| Canvas | `#06070c` aurora + grain | `#fcfcfd` | `#f7f4ec` ruled paper |
| Accent | Iris `#8b7cff` + cyan data | Indigo `#5266eb`, alone | Copper `#b0562f` + ledger green |
| Type | Manrope, 88px hero | Inter, 56px hero | Lora display + Nunito Sans |
| Depth | Translucency | Hairlines only | Letterpress + risograph offset |
| Rejects | Light mode, flat fills | Gradients, shadows, radius > 8px | Cold grays, pure black, heavy shadow |

All three use the same curated dataset so they can be compared like-for-like, and all three
are non-functional: no network, no storage, no backend.

## Interaction vocabulary (identical logic, three costumes)

Every data element responds to a click, per the brief:

- **Bar graph** — click selects: the bar lifts on `translateY`, a value chip pops in from
  `scale(0.95)`, siblings drop to 40% opacity. Click again to release.
- **Spend bubbles** — press `scale(0.96)`, release to `scale(1.04)` and settle; a ripple ring
  expands and fades; the detail panel re-counts to the new figure.
- **Budget ring** — click re-sweeps the arc via `stroke-dashoffset`.
- **Sparkline / cashflow** — click re-draws the path left to right.
- **Transaction rows** — click expands detail; chevron rotates 90°.
- **Segmented control** — the indicator pill slides on `transform` beneath the labels.
- **Stat tiles** — press to `scale(0.985)`, value re-counts.
- **Accounts, upcoming payments, nav, toggles** — all carry press feedback and a state slide.

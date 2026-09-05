# Ledger — front-end redesign brief

You are implementing a visual redesign of **Ledger**, a private personal-finance dashboard.
Three finished, non-functional mockups already exist. Your job is to bring the real app up to
one of them. This document is the whole spec — you do not need any prior conversation.

Read this file end to end before touching code. Section 11 (Pitfalls) will save you the most time;
it is a list of bugs that were actually hit and fixed while building the mockups.

---

## 1. Ground rules

The codebase is deliberately dependency-free. Do not change that.

- **Vanilla JS only.** No React, no build step, no bundler, no npm packages, no TypeScript.
- **No CSS framework.** No Tailwind, no Bootstrap. Hand-written CSS with custom properties.
- **Fonts are local.** `web/fonts/` holds Lora, Manrope and Nunito Sans as woff2, served from
  `/fonts/…`. Do not add Google Fonts or any remote font.
- **No network calls for assets.** No CDN scripts, no remote images, no icon packages. Icons are
  inline SVG.
- **Backend is out of scope.** Python stdlib + SQLite. Do not touch `backend/`, the Plaid
  integration, the workers, or any data logic. This is a front-end task.
- **Do not break existing behaviour.** Every current feature must keep working. This is a reskin
  plus interaction polish, not a rewrite.
- Keep the existing markup structure wherever you can and restyle it. Add elements only where a
  component genuinely needs them.

---

## 2. What already exists

### Files you will touch

| File | Lines | Role |
|---|---|---|
| `web/styles.css` | 289 | **Token block + core components.** Start here. |
| `web/dark.css` | 372 | Dark-mode and chart styling |
| `web/sidebar.css` | 76 | Desktop navigation rail |
| `web/mobile.css` | 42 | Phone layout, bottom nav, safe-area handling |
| `web/reports.css` | 64 | Reports page |
| `web/comfort.css`, `web/paper.css` | 43 / 18 | Density and paper-surface options |
| `web/charts.js`, `web/charts2.js` | — | Chart rendering — where bar/ring/sparkline animation goes |
| `web/app.js`, `web/app2.js` | — | Home dashboard behaviour |
| `web/mobile.js` | — | Phone navigation |
| `web/index.html` | — | Single-page shell |

### Existing token names — reuse these, do not invent a parallel system

`web/styles.css` already defines a token block. Keep **the same variable names** and replace
**the values**. That way every existing rule inherits the new design for free.

```
--bg  --bg-soft  --panel  --panel-2  --border  --border-soft
--text  --muted  --faint
--accent  --accent-2  --green  --red  --amber  --cyan  --pink
--shadow  --radius  --sidebar-w  --font
```

### Existing component classes — restyle these, do not rename

`.card` `.grid` `.cols-2/3/4` `.btn` `.btn-primary` `.btn-accent` `.btn-ghost` `.btn-sm`
`.input` `.modal` `.modal-backdrop` `.modal-actions` `.nav-link` `.acct-card` `.acct-bal`
`.acct-name` `.amt-pos` `.amt-neg` `.cat-chip` `.bar` `.legend` `.legend-dot` `.heat-cell`
`.matrix-table` `.goal-head` `.muted` `.empty` `.delta-up`

### Theming as it works today

The app is **dark-first**, with light applied via `[data-theme="light"]` on the root, and Settings
offers light / dark / system. **Keep that convention.** The mockups use
`prefers-color-scheme` plus a `[data-theme]` override, which is the same idea; map onto what the
app already does rather than replacing its mechanism.

---

## 3. Pick one direction

Three complete mockups live in `docs/design/mockups/`. Open them in a browser — they are
self-contained and interactive. Screenshots of every state are in `../handoff/screenshots/`.

| Direction | File | Character |
|---|---|---|
| **Aurora** | `aurora.html` + `aurora-mobile.html` | Futuristic. Cinematic dark glass over a fixed aurora field. **The only direction with a finished phone layout — pick this one unless told otherwise.** |
| **Quiet** | `quiet.html` | Minimalist. Hairlines and a single indigo. No gradients, no shadows, radius capped at 8px. |
| **Almanac** | `almanac.html` | Editorial. The month set as a printed broadsheet — letterpress rules, engraved hatch columns, ink-blot spend discs. |

**Default to Aurora** unless the person directing you says otherwise. Section 4 gives Aurora in
full; Section 5 gives the other two if you need them.

Do not blend the three. Each is internally consistent and mixing them produces mush.

---

## 4. Aurora — the token contract

Paste this over the existing `:root` block in `web/styles.css`, keeping the app's variable names.
Values are exact. Do not "improve" them.

```css
:root{
  /* ---- flip channels: every translucent fill derives from these ---- */
  --tint:255,255,255;              /* surface tint base */
  --accent-rgb:139,124,255;
  --cyan-rgb:79,216,245;
  --green-rgb:74,222,128;

  /* ---- app tokens (dark, the native mode) ---- */
  --bg:#06070c;
  --bg-soft:#0a0c14;
  --panel:rgba(255,255,255,.038);
  --panel-2:rgba(255,255,255,.06);
  --border:rgba(255,255,255,.085);
  --border-soft:rgba(255,255,255,.14);
  --text:#eaedf7;
  --muted:#98a1bd;
  --faint:#5d6580;
  --accent:#8b7cff;
  --accent-2:#a99bff;
  --green:#4ade80;
  --red:#ff6b8b;
  --amber:#fcd34d;
  --cyan:#4fd8f5;
  --pink:#ff9a6b;
  --shadow:0 10px 30px rgba(0,0,0,.35);
  --radius:16px;
  --radius-lg:22px;

  /* ---- surfaces and effects ---- */
  --hi:inset 0 1px 0 rgba(255,255,255,.10);      /* glass inner highlight */
  --col-hi:inset 0 1px 0 rgba(255,255,255,.22);  /* chart column highlight */
  --chip-bg:rgba(10,12,20,.94);
  --chip-fg:#eaedf7;
  --on-accent:#0a0710;                            /* text on an accent-filled button */
  --grain:.028;
  --field:
    radial-gradient(900px 620px at 12% -8%, rgba(var(--accent-rgb),.20), transparent 62%),
    radial-gradient(760px 520px at 88% 4%,  rgba(var(--cyan-rgb),.13),   transparent 60%),
    radial-gradient(900px 700px at 60% 106%,rgba(var(--accent-rgb),.10), transparent 62%),
    linear-gradient(180deg,#06070c 0%,#080a11 40%,#06070c 100%);
}

[data-theme="light"]{
  --tint:24,24,48;
  --accent-rgb:106,90,224;
  --cyan-rgb:14,147,180;
  --green-rgb:15,138,82;

  --bg:#f6f6fc;
  --bg-soft:#eef0f9;
  --panel:rgba(255,255,255,.72);
  --panel-2:rgba(255,255,255,.86);
  --border:rgba(24,24,48,.11);
  --border-soft:rgba(24,24,48,.20);
  --text:#151522;
  --muted:#5a5a74;
  --faint:#8787a3;
  --accent:#6a5ae0;
  --accent-2:#8b7cff;
  --green:#0f8a52;
  --red:#d3455f;
  --amber:#a5690f;
  --cyan:#0e93b4;
  --pink:#dd7040;
  --shadow:0 10px 30px rgba(24,24,48,.08);

  --hi:inset 0 1px 0 rgba(255,255,255,.9);
  --col-hi:inset 0 1px 0 rgba(255,255,255,.5);
  --chip-bg:rgba(21,21,34,.95);
  --chip-fg:#ffffff;
  --on-accent:#ffffff;
  --grain:.02;
  --field:
    radial-gradient(900px 620px at 12% -8%, rgba(var(--accent-rgb),.18), transparent 62%),
    radial-gradient(760px 520px at 88% 4%,  rgba(var(--cyan-rgb),.14),   transparent 60%),
    radial-gradient(900px 700px at 60% 106%,rgba(var(--accent-rgb),.12), transparent 62%),
    linear-gradient(180deg,#fbfbff 0%,#f4f5fd 40%,#f8f8fe 100%);
}
```

### The flip-channel rule — follow it

Every translucent fill in the app must be written `rgba(var(--tint),.06)`, never
`rgba(255,255,255,.06)`. One token then flips the entire surface system between themes. The same
applies to `--accent-rgb`, `--cyan-rgb`, `--green-rgb`.

Sweep the existing CSS for hardcoded `rgba(255,255,255,…)` and convert every one. This is
mechanical and safe.

### Surfaces

- Page background is `var(--field)` on a **fixed** pseudo-element, with content scrolling over it.
  It must not scroll with the page.
- A grain overlay sits above the field at `opacity:var(--grain)`, `pointer-events:none`, using an
  inline SVG `feTurbulence` data URI. It stops the gradients banding.
- `.card` = `background:var(--panel)` + `backdrop-filter:blur(22px) saturate(140%)` +
  `1px solid var(--border)` + `box-shadow:var(--hi)` + `border-radius:var(--radius-lg)`.
- Cards get **no drop shadow** in dark. Depth comes from translucency and the inner highlight.
- Hover strengthens the border to `--border-soft`. It does not lift the card.

### Typography

- Family: **Manrope** (already bundled), fallback `-apple-system, 'Segoe UI', Roboto, Inter, sans-serif`.
- **`font-variant-numeric: tabular-nums` and `font-feature-settings:"tnum" 1` on `body`.**
  Non-negotiable — every monetary figure must align.
- The hero net-worth figure is 76px, weight 600, letter-spacing `-.038em`.
- The currency symbol is set **smaller and lighter** than the digits (34px, `--faint`, weight 400)
  and nudged up with `transform:translateY(-14px)`. Cents are also 34px, in `--muted`.
- Section labels: 10px, `letter-spacing:.16em`, uppercase, `--faint`.
- Amounts in lists use a monospace stack for column alignment.

---

## 5. The alternate directions

Only needed if you were told to build Quiet or Almanac instead.

### Quiet — minimalist

```css
:root{ /* light is native */
  --bg:#fcfcfd; --panel:#ffffff; --panel-2:#f7f7f9;
  --border:#eaeaee; --border-soft:#dcdce2;
  --text:#0e0e11; --muted:#6b6b76; --faint:#9b9ba6;
  --accent:#5266eb; --accent-soft:#eef0fd;
  --green:#0f7b52; --red:#b3261e;
  --on-ink:#ffffff; --bar:#d3d3db; --bar-hover:#c3c3cc;
  --radius:8px;
}
[data-theme="dark"]{
  --bg:#08080a; --panel:#0e0e11; --panel-2:#16161a;
  --border:#1e1e25; --border-soft:#30303a;
  --text:#f1f1f4; --muted:#9797a3; --faint:#6c6c79;
  --accent:#7c8aff; --accent-soft:#191c34;
  --green:#3fbf85; --red:#f0736c;
  --on-ink:#0b0b0e; --bar:#33333e; --bar-hover:#454553;
}
```

Rules: no gradients. No drop shadows (one exception: popovers may use
`0 1px 2px rgba(0,0,0,.06)`). **Radius never exceeds 8px.** Indigo appears only on primary action,
selection and focus ring — nowhere else. Depth is borders only; hover strengthens a border rather
than lifting anything.

### Almanac — editorial broadsheet

```css
:root{ /* day edition */
  --ink-rgb:31,28,22; --copper-rgb:176,86,47; --oxblood-rgb:156,59,46;
  --paper:#f7f4ec; --paper-2:#f1ece0; --paper-3:#eae3d4;
  --ink:#1f1c16; --ink-2:#4e463a; --faint:#8d8375;
  --copper:#b0562f; --ledger:#2f6b4f; --oxblood:#9c3b2e;
  --rule:rgba(31,28,22,.14); --rule-2:rgba(31,28,22,.28);
  --grain:.05; --col-blend:multiply; --radius:3px;
}
[data-theme="dark"]{ /* night edition */
  --ink-rgb:240,232,217; --copper-rgb:217,136,79; --oxblood-rgb:226,119,95;
  --paper:#15130e; --paper-2:#1d1a14; --paper-3:#272119;
  --ink:#f0e8d9; --ink-2:#bdb19d; --faint:#8b8172;
  --copper:#d9884f; --ledger:#68b891; --oxblood:#e2775f;
  --rule:rgba(240,232,217,.15); --rule-2:rgba(240,232,217,.28);
  --grain:.055; --col-blend:screen;
}
```

Rules: Lora for display, Nunito Sans for body — both already bundled. Never cold gray, never pure
black, never a heavy shadow. Radius stays at 3px; this is paper, not glass. Hierarchy comes from
rules (single and double hairlines) and from type weight, not from boxes.

---

## 6. Motion contract

These rules apply to every animation you write, in all three directions. They come from Emil
Kowalski's animations.dev and are not negotiable.

```css
--ease-out-quart: cubic-bezier(.165,.84,.44,1);
--ease-out-expo:  cubic-bezier(.19,1,.22,1);
--ease-in-out-cubic: cubic-bezier(.645,.045,.355,1);
```

- Entering or exiting → `ease-out`. Moving on screen → `ease-in-out`. Hover → `ease`.
  **Never `ease-in`** — the delayed start reads as sluggish.
- Micro-interactions 100–150ms. Standard UI 150–250ms. Panels and sheets 200–300ms.
  **Nothing over 300ms.**
- Exits run about 20% faster than entrances. Larger elements move slower than small ones.
- **Animate `transform` and `opacity` only.** They skip layout and paint. Never animate
  `width`, `height`, `margin` or `padding`. The one sanctioned exception is an accordion using
  `grid-template-rows: 0fr → 1fr`, which is rare enough to be worth it.
- Start from `scale(0.95)`, never `scale(0)`. Press feedback is `scale(0.97)`.
- Elements that animate together share one duration and one curve.
- Counters and chart reveals fire on `IntersectionObserver`, never on load, so nothing animates
  off-screen.
- **Every animation needs a `prefers-reduced-motion: reduce` escape**, and the JS must check
  `matchMedia('(prefers-reduced-motion: reduce)').matches` before running any scripted animation.

```css
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{ animation:none !important; transition:none !important; }
  /* then restore any end-state the animation was responsible for:      */
  .reveal{opacity:1; transform:none;} .bar .col{transform:scaleY(1);}
}
```

That last line matters. If an element's visible state depends on an animation having run, disabling
motion must not leave it invisible.

---

## 7. Component specs

### Hero figure
One trusted number, far larger than anything near it. Currency symbol lighter and smaller than the
digits. Delta shown as a pill: green tint background, `inset 0 0 0 1px` ring, arrow glyph, never a
plain colored word.

### Bar chart (12 months)
- Structure each column as `button.bar > span.track > span.col`, where `.track` is `flex:1` and the
  column's `height:N%` is a percentage **of the track**, not of the button. If you put the month
  label inside the same flex column without a track, the label compresses the bars non-linearly.
- Reveal: `transform:scaleY(0) → scaleY(1)`, `transform-origin:bottom`, staggered by
  `transition-delay: i * 45ms`.
- Click selects: the bar lifts on `translateY(-4px)`, a value chip pops in from
  `scale(.95) translateY(3px)`, and siblings drop to 40% opacity. Click again to release.
- The chip is absolutely positioned against `.col`, at `bottom: calc(100% + 8px)`, so it tracks the
  top of the bar rather than the top of the button.
- Range switching (12M/6M/3M) must also reset `grid-template-columns` to the visible count,
  otherwise the remaining bars bunch into the left half of the track.

### Spend bubbles
Area encodes share of month — size by `sqrt(value / max)`, never by raw value. Press gives
`scale(.96)`, release settles at `scale(1.04)`, and a ring expands and fades
(`transform:scale(1.55); opacity:0` over ~620ms). The detail panel re-counts to the new figure.

### Budget ring
SVG circle, `stroke-dasharray` = circumference, animate `stroke-dashoffset` over 900ms
`ease-out-expo`. Rotate the SVG `-90deg` so the sweep starts at twelve o'clock. Clicking replays it.

### Sparkline
Smooth path via cubic segments through the midpoints. Draw with
`stroke-dasharray = getTotalLength()` and animate `stroke-dashoffset` to 0 over ~1400ms. Fade the
area fill in behind it with a delay.

### Meters
Animate `transform: scaleX()` with `transform-origin:left`. Over-budget switches to the red ramp.

### Odometer counters
Count up with `requestAnimationFrame` and ease-out-expo (`1 - 2^(-10p)`), ~1000–1100ms, formatted
with `toLocaleString('en-US', {minimumFractionDigits:2})`. Under reduced motion, set the final value
immediately.

### Lists and tables
Dense — around 64px rows. Amounts monospaced and right-aligned. Row click expands detail (desktop)
or opens a bottom sheet (phone).

---

## 8. Interaction vocabulary

**Every data element responds to a click.** This is a core requirement, not a nice-to-have. Bars,
spend bubbles, budget rings, sparklines, meters, stat tiles, account cards, transaction rows,
upcoming payments, nav items and toggles all need press feedback and a state change. Nothing that
looks tappable may be inert.

Press feedback is `transform: scale(.97)` (or `.985` for large surfaces) at 120ms `ease-out`.

---

## 9. Phone rules

The app already has a phone layout — Home / Spending / Budgets / More, a 70px bottom bar, a 56px
floating add button, and `env(safe-area-inset-*)` handling in `web/mobile.css`. **Keep that
structure.** Match `aurora-mobile.html`, which was built against it.

- **44px minimum tap target. 64px list rows.** For this reason the phone spending chart defaults to
  **6M, not 12M** — six columns clear 44px each, twelve do not.
- Detail opens in a **bottom sheet**, not the desktop inline accordion. Scrim fades 220ms, sheet
  rises 280ms `ease-out`. Dismissible by scrim tap, grab handle, an explicit Close button, and Escape.
- Accounts become a snap-scrolling rail (`scroll-snap-type:x mandatory`), not a grid.
- The spend constellation is **re-packed** for a narrow column — new positions and radii — not
  scaled down.
- Respect `env(safe-area-inset-*)` everywhere, and use `100dvh` rather than `100vh`.

---

## 10. Accessibility — non-negotiable

- Every interactive element is a real `<button>`. Never a clickable `<div>`.
- `:focus-visible` gets a 2px accent outline with `outline-offset:2px`. Never remove focus rings.
- Selection state is carried by `aria-pressed`, expansion by `aria-expanded`, current nav by
  `aria-current`. Style from those attributes rather than from a separate class where you can — the
  accessible state and the visual state then cannot drift apart.
- Icon-only buttons need `aria-label`, updated when their meaning changes (a theme toggle should
  read "Switch to light mode" / "Switch to dark mode").
- Body text must clear WCAG AA in **both** themes. Check the muted and faint tokens specifically —
  they are where contrast quietly fails.
- `prefers-reduced-motion` disables all motion, with no exceptions.

---

## 11. Pitfalls that actually bit

Every one of these was a real bug found by rendering the page, not by reading the code. Check for
them proactively.

1. **Inline `<span>` children collapse onto one line.** A `<span>` inside a `<span>` stays inline,
   so a name and its subtitle render as `"Blue Bottle CoffeeDining · today"`. This bit **five
   separate times** across the mockups. Any stacked label pair needs `display:block` on both
   children — or make the parent a flex column. Check every list row, card and sheet header.
2. **`height` does nothing on an inline element.** A `<span class="meter">` with `height:6px`
   collapses to a hairline tick. Every budget bar in two files was invisible because of this. Give
   it `display:block`.
3. **A duplicated property silently wins.** One rule declared `margin-top:auto` and then
   `margin-top:var(--s5)` later in the same block; the second killed the first and a card footer
   never bottom-aligned. Grep for repeated properties inside a single rule.
4. **Table headers must share the body's grid.** A `<thead>` with four `<th>` over a body of single
   `<td>` cells containing their own grid aligns to nothing. Use one shared
   `grid-template-columns` variable for both the header row and the body rows.
5. **Chart gridlines drawn at guessed pixel offsets will lie.** Measure the rendered track with
   `getBoundingClientRect()` and place lines from the real scale. Re-measure on resize and on
   range change.
6. **Bars need a dedicated track element** or the month label compresses them non-linearly.
7. **Filtering a chart range without resetting `grid-template-columns`** leaves the remaining bars
   bunched in the left half.
8. **`mix-blend-mode: multiply` stops working on a dark ground.** The Almanac's copper overprint
   only read because the offset landed on light paper; in the night edition every disc went flat.
   If you need an offset duplicate that works on both grounds, use an offset `box-shadow`, not a
   blend mode.
9. **A sticky header will collide with the phone's dynamic island.** Pin the status bar above it
   rather than sticking the app bar to `top:0`.
10. **Fixed-width flex items overflow and wrap their own content.** A sheet header amount needs
    `white-space:nowrap` and `flex:none`, with `min-width:0` on the flexible sibling.
11. **Headless Chromium clamps its window to a 500px minimum**, so `--window-size=390` still
    reports `innerWidth: 500` and a 460px media query will never match. This looks exactly like a
    broken breakpoint. Verify with `matchMedia().matches` before concluding the CSS is wrong.
12. **Sort out which year a month belongs to.** A rolling 12-month window ending in September 2026
    starts in October **2025**. Labels read "Dec 2026" for three months until this was caught.

---

## 12. How to verify your work

**Do not trust the markup — render it.** Chromium is available and every bug in Section 11 was
caught this way and none by reading code.

```bash
# full-page screenshot
chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
  --window-size=1440,2050 --virtual-time-budget=9000 \
  --screenshot=out.png "file:///path/to/web/index.html"

# settled final state: forces reduced motion, so counters and reveals land on their end values
chromium --headless --no-sandbox --disable-gpu --force-prefers-reduced-motion \
  --window-size=1440,2050 --virtual-time-budget=9000 --screenshot=final.png "file://…"
```

`--force-prefers-reduced-motion` is the single most useful flag: without it every screenshot catches
animations mid-flight and you cannot tell a real layout bug from an in-progress transition.

To verify interactions, append a probe script to a temporary copy of the page that clicks things and
writes the resulting state into `document.title`, then read it with `--dump-dom`:

```js
requestAnimationFrame(()=>setTimeout(()=>{
  document.querySelectorAll('#bars .bar')[2].click();
  document.querySelector('[data-row]').click();
  document.title = 'bar='   + document.querySelectorAll('#bars .bar')[2].getAttribute('aria-pressed')
                 + ' row='  + document.querySelector('[data-row]').getAttribute('aria-expanded');
}, 90));
```

Note that headless Chromium defaults to `prefers-color-scheme: light`, so to capture dark mode you
must click the theme control in your probe.

---

## 13. Acceptance checklist

Do not report the work finished until all of these hold.

- [ ] Both themes render correctly on the home dashboard, spending, budgets, subscriptions and reports.
- [ ] Every monetary figure uses tabular numerals and decimals align in columns.
- [ ] Bar chart: staggered reveal, click-to-select with chip, siblings dim, release on second click.
- [ ] Spend bubbles sized by area, with ripple and detail re-count on press.
- [ ] Budget ring sweeps; sparkline draws; meters fill from the left.
- [ ] Every clickable element has press feedback; nothing tappable is inert.
- [ ] Phone: 44px targets, 6M chart default, bottom sheet with four dismiss paths, safe-area insets.
- [ ] `prefers-reduced-motion` disables all motion and nothing disappears as a result.
- [ ] Keyboard: focus-visible rings everywhere, tab order sane, Escape closes the sheet.
- [ ] Contrast passes AA in both themes, `--muted` and `--faint` specifically.
- [ ] No hardcoded `rgba(255,255,255,…)` remains — all converted to `rgba(var(--tint),…)`.
- [ ] No console errors. No network requests for fonts, scripts or images.
- [ ] Screenshots taken of every changed screen in both themes and visually reviewed.
- [ ] All 12 pitfalls in Section 11 explicitly checked.

---

## 14. Out of scope

Do not: touch `backend/`, alter data or business logic, add dependencies, introduce a build step,
change the Plaid integration or the workers, rename existing CSS classes or JS functions, or
redesign screens the mockups do not cover without asking first.

If a mockup and this document disagree, **this document wins**. If something is genuinely
underspecified, choose the option most consistent with Sections 6 and 10, and say what you chose.

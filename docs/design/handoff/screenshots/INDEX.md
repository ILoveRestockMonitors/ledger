# Screenshot index

All captured from the finished mockups in `../../mockups/` with `--force-prefers-reduced-motion`,
so every counter, chart reveal and meter is shown at its settled final value.

## Aurora — futuristic (the recommended direction)

| File | Shows |
|---|---|
| `01-aurora-desktop-dark.png` | Full home dashboard, dark. The native mode. |
| `02-aurora-desktop-light.png` | Same page, light. Frosted white over a lilac field. |
| `03-aurora-desktop-selected-dark.png` | **Interaction states**: Dec bar selected with value chip and siblings dimmed, a bubble selected, a transaction row expanded. |

## Aurora — phone

| File | Shows |
|---|---|
| `10-phone-dark-home.png` | Top of home in the device frame, dark. |
| `11-phone-light-home.png` | Same, light. |
| `12-phone-constellation-light.png` | Spend constellation, category readout, snap-scrolling account rail. |
| `13-phone-constellation-dark.png` | Same, dark. |
| `14-phone-bottom-sheet-dark.png` | **Bottom sheet** open over a blurred scrim — the phone's replacement for the desktop accordion. |
| `15-phone-bottom-sheet-light.png` | Same, light. |
| `16-phone-fullbleed-no-frame.png` | Below 460px the presentation device frame drops away and the app runs full-bleed. This is what a real handset gets. |

## Quiet — minimalist

| File | Shows |
|---|---|
| `04-quiet-light.png` | Full dashboard, light. The native mode. |
| `05-quiet-dark.png` | Dark mode. |
| `06-quiet-selected-light.png` | Bar selected, bubble selected, row expanded. |

## Almanac — editorial

| File | Shows |
|---|---|
| `07-almanac-day.png` | Full broadsheet, day edition. |
| `08-almanac-night.png` | Night edition — warm charcoal, never cold gray. |
| `09-almanac-selected-day.png` | **The risograph effect**: the selected Dec column takes its copper overprint, and the selected spend disc snaps into register while the others keep their offset crescent. |

## Gallery

| File | Shows |
|---|---|
| `17-gallery-light.png` | The index page listing all directions. |
| `18-gallery-dark.png` | Same, dark. |

## Reading the interaction shots

`03`, `06` and `09` are the important ones for implementation — they show what *selected* looks
like, which the idle screens cannot convey. Note in each: the selected element gains emphasis while
its siblings drop to roughly 40% opacity. Selection is a change in the whole group, not just the
one item.

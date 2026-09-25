# Ledger homepage concepts

Five from-scratch designs for Ledger's Home screen, for choosing a direction before the rest of the app is redesigned. They are standalone preview pages: they do not change the Ledger app, its server or any data.

Open `index.html` to compare all five, or open one directly:

| # | Name | In one line |
|---|------|-------------|
| 1 | [Console](1-console.html) | The home screen is the working app; scrolling plays the next 30 days forward. |
| 2 | [The Seam](2-seam.html) | Personal and Business side by side; the line between them is the switch. |
| 3 | [The Almanac](3-almanac.html) | The month as a short letter; every dollar figure opens its receipt. |
| 4 | [The Poster](4-poster.html) | One "left to spend" number at poster size; the words gain weight as money is used. |
| 5 | [Pulse](5-pulse.html) | The week as fast colorful screens, with a gauge in the top bar that drains as you go. |

All five borrow Dollarwise's simplest ideas: a 50/30/20 split of needs, wants and savings, one clear "left to spend" number, and a weekly check-in where things are sorted for you and easy to change.

## Sample data

Every figure is calculated in `shared/ledger-sample.js` from the same fictional dataset the app's Demo version uses (Alex and Juniper Studio, Thursday, September 24, 2026). Buttons and forms work, but reloading resets everything.

## View locally

From the repository root:

```bash
python3 -m http.server 8000 --directory homepage-concepts
```

Then open <http://localhost:8000/>.

## Files

- `index.html`: the comparison page.
- `1-console.html` to `5-pulse.html`: the five concepts. Each is one self-contained page.
- `shared/ledger-sample.js`: sample data and the math behind every number.
- `shared/scrollcraft.js`, `shared/scrollcraft.css`: the scroll engine from [nateherkai/scroll-craft](https://github.com/nateherkai/scroll-craft) (MIT, see `shared/SCROLLCRAFT-LICENSE.txt`), unmodified.
- `previews/`: screenshots used on the comparison page.
- `DESIGN-NOTES.md`: the design brief, page styles and how each concept differs.

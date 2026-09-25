# Ledger redesign demo

A clickable website version of the redesign explored on the design canvas: one switch for **Everything / Personal / Business**, a spending-at-a-glance band that shows categorized and uncategorized spending, and both designs — **Sarah** (forest) and **Cornelious** (Zekrom storm in dark mode, Reshiram sunfire in light mode).

It uses the app's fictional demo dataset (Alex and Juniper Studio, September 2026). Nothing is saved; reloading resets the numbers. It does not touch the Ledger server, your database or `backend/`.

## Run it

```bash
python3 redesign-demo/serve.py
```

That opens <http://localhost:8000/redesign-demo/>. Use another port with `python3 redesign-demo/serve.py 8010`, or skip opening a browser with `--no-browser`. The server only answers on this computer and only serves `redesign-demo/` and `web/`.

- Wide windows (1100px and up) show the desktop screens; narrower windows and phones show the phone screens.
- **Preview** (bottom right) shows the phone layout in a device frame on a desktop browser.
- Home, Transactions and Budgets are linked from the sidebar and the phone tab bar.
- The Sarah / Cornelious switch, light/dark and your last scope are remembered in this browser.
- URL options: `?layout=cornelious`, `?dark=1`, `?view=phone`.

## Files

- `screens/*.dc.html` — the six screens exactly as they are on the canvas (desktop and phone Home, Transactions, Budgets).
- `runtime.js` — renders those screens as plain web pages: `{{holes}}`, `sc-for` / `sc-if`, event bindings and a small DOM morph so transitions keep playing.
- `site.js`, `site.css` — routes, desktop/phone switching, fluid page layout and remembered preferences.
- `assets/` — the shared Sarah/Cornelious layer, lightning and flame artwork, and compressed video posters. Videos and fonts come from `web/`.

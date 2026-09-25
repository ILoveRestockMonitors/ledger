/* Routes, responsive desktop/phone switching and shared preferences for the redesign demo. */
(function () {
  'use strict';
  // Canvas asset ids → files in this repository.
  const ASSETS = {
    '/_blob/55500abe80d8505e21a77d94bb9ff3f7': '../web/sarah-stream-loop.mp4',
    '/_blob/e11cc25bab12a944321d615565f52917': 'assets/woodland-poster.jpg',
    '/_blob/06f732d4ecae4eaf2ffaed2b793f6719': '../web/zekrom-storm-loop.mp4',
    '/_blob/b744d976bf900167facbc520e33ba41f': 'assets/storm-poster.jpg',
    '/_blob/0453cd8912e0423510ad98529ce9d8f7': '../web/reshiram-sunfire-loop.mp4',
    '/_blob/f011880bf12ed93b6337dbf790957ed7': 'assets/sunfire-poster.jpg',
    '/_blob/9b7171f5b4a5952ab68580f51a24231f': '../web/ledger-logo-20260914-quiet-l-aurora.png',
  };
  const ROUTES = {
    home: { desktop: 'Main', phone: 'Mobile', title: 'Home' },
    transactions: { desktop: 'Transactions', phone: 'MobileTransactions', title: 'Transactions' },
    budgets: { desktop: 'Budgets', phone: 'MobileBudgets', title: 'Budgets' },
  };
  const ROUTE_OF = { Main: 'home', Home: 'home', Mobile: 'home', Transactions: 'transactions', MobileTransactions: 'transactions', Budgets: 'budgets', MobileBudgets: 'budgets' };
  const DESKTOP_MIN = 1100, KEY = 'ledger-redesign-demo';

  const params = new URLSearchParams(location.search);
  let prefs = { layout: 'sarah', dark: false, scope: 'everything', motion: 'on', view: '' };
  try { prefs = Object.assign(prefs, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) {}
  if (params.get('layout') === 'cornelious' || params.get('layout') === 'sarah') prefs.layout = params.get('layout');
  if (params.has('dark')) prefs.dark = params.get('dark') === '1';
  if (params.get('view') === 'phone' || params.get('view') === 'desktop') prefs.view = params.get('view');
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch (e) {} };

  const app = document.getElementById('app');
  const screenStyle = document.getElementById('screen-style');
  const liveStyle = document.getElementById('live-style');
  const cache = {};
  let current = null, currentKey = '';

  const wide = () => innerWidth >= DESKTOP_MIN;
  const view = () => (prefs.view === 'phone' || !wide()) ? 'phone' : 'desktop';
  const route = () => { const r = location.hash.replace(/^#\/?/, ''); return ROUTES[r] ? r : 'home'; };

  async function load(name) {
    if (!cache[name]) {
      const res = await fetch('screens/' + name + '.dc.html');
      if (!res.ok) throw new Error('Could not load ' + name);
      cache[name] = LedgerDC.compile(await res.text(), ASSETS);
    }
    return cache[name];
  }

  // Keep the scope and design washes centred on the control that triggered them.
  function after(root) {
    prefs.scope = root.dataset.scope || prefs.scope;
    prefs.layout = root.dataset.layout || prefs.layout;
    prefs.dark = root.dataset.theme === 'dark';
    prefs.motion = root.dataset.motion || prefs.motion;
    save();
    document.body.dataset.theme = prefs.dark ? 'dark' : 'light';
    document.body.dataset.layout = prefs.layout;
    const fixed = view() === 'desktop';
    const base = fixed ? { left: 0, top: 0 } : root.getBoundingClientRect();
    const centre = el => { const r = el.getBoundingClientRect(); return [r.left - base.left + r.width / 2, r.top - base.top + r.height / 2]; };
    const tab = root.querySelector('.switch .tab[aria-selected="true"]');
    const design = root.querySelector('.seg[aria-label="Design"]');
    let css = '';
    if (tab) { const [x, y] = centre(tab); css += `--wx:${x}px!important;--wy:${y}px!important;`; }
    if (design) { const [x, y] = centre(design); css += `--lx:${x}px!important;--ly:${y}px!important;`; }
    liveStyle.textContent = css ? `.lg{${css}}` : '';
  }

  async function go() {
    const r = route(), v = view(), name = ROUTES[r][v], key = r + '|' + v;
    if (key === currentKey) return;
    currentKey = key;
    let screen;
    try { screen = await load(name); } catch (e) {
      app.innerHTML = '<p style="font:600 15px system-ui;padding:40px">' + e.message + '. Start the demo with <code>python3 redesign-demo/serve.py</code>.</p>';
      return;
    }
    if (key !== currentKey) return;
    if (current) current.unmount();
    screenStyle.textContent = screen.styles;
    document.body.className = 'site-' + v + (v === 'phone' && wide() ? ' site-device' : '');
    document.title = 'Ledger · ' + ROUTES[r].title + ' · Redesign demo';
    current = LedgerDC.mount(screen, app, { layout: prefs.layout, dark: prefs.dark, startScope: prefs.scope }, after);
    if (prefs.motion === 'paused') current.inst.setState({ motion: 'paused' });
    window.scrollTo(0, 0);
    syncViewToggle();
  }

  // Links inside the screens name canvas artboards; map them to routes.
  document.addEventListener('click', event => {
    const a = event.target.closest('a[href]');
    if (!a || !app.contains(a)) return;
    const href = a.getAttribute('href');
    const artboard = href.match(/^(?:Cornelious|Sunfire)?([A-Za-z]+)\.dc\.html$/);
    if (artboard) { event.preventDefault(); location.hash = '#/' + (ROUTE_OF[artboard[1]] || 'home'); return; }
    if (href.charAt(0) === '#' && href.charAt(1) !== '/') { event.preventDefault(); if (href === '#top') window.scrollTo({ top: 0, behavior: 'smooth' }); }
  });

  // Desktop browsers can preview the phone layout in a device frame.
  const toggle = document.getElementById('view-toggle');
  function syncViewToggle() {
    toggle.hidden = !wide();
    toggle.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.view === view())));
  }
  toggle.addEventListener('click', event => {
    const b = event.target.closest('button[data-view]');
    if (!b) return;
    prefs.view = b.dataset.view === 'phone' ? 'phone' : '';
    save();
    go();
  });

  addEventListener('hashchange', go);
  let resizeTimer;
  addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { syncViewToggle(); go(); }, 120); });
  if (!location.hash) history.replaceState(null, '', '#/home');
  go();
})();

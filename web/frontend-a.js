/* Design A: compact, readable surfaces over the animated theme backgrounds.
   Rebuilds Home (net worth first) and Activity, the edit/add sheets, and the
   phone navigation. Other pages keep their renderers and take the new styles.
   Open ?design=current to return this browser to the previous look, ?design=a to come back. */
(() => {
  'use strict';
  const root = document.documentElement;
  const view = document.getElementById('view');
  const read = key => { try { return localStorage.getItem(key); } catch { return null; } };
  const write = (key, value) => { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch {} };
  const urlDesign = new URLSearchParams(location.search).get('design');
  if (urlDesign === 'a' || urlDesign === 'current') write('ledger-design', urlDesign);
  if (read('ledger-design') === 'current') { root.dataset.design = 'current'; return; }
  root.dataset.design = 'a';
  // Boot can start rendering before this file loads; if it did, render again with these pages.
  const bootedEarly = !/Opening your space/.test(view?.textContent || '');

  /* ---------------- Formatting ---------------- */
  const cash = n => fmtMoney(Number(n) || 0, { decimals: 2 });
  const whole = n => fmtMoney(Math.round(Number(n) || 0), { decimals: 0 });
  const signed = n => (Number(n) > 0 ? '+' : '') + cash(n);
  const signedWhole = n => (Number(n) > 0 ? '+' : '') + whole(n);
  const split = n => { const s = cash(n); return `${s.slice(0, -3)}<span class="a-cents">${s.slice(-3)}</span>`; };
  const LABEL = { everything: 'All', personal: 'Personal', business: 'Business', all: 'Both' };
  const monthKey = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  const isoToday = () => monthKey() + '-' + String(new Date().getDate()).padStart(2, '0');
  const dayDiff = iso => Math.round((new Date(iso + 'T12:00:00') - new Date(isoToday() + 'T12:00:00')) / 864e5);
  const monthLong = (d = new Date()) => d.toLocaleDateString('en-US', { month: 'long' });
  const getScope = () => { const s = read('ledger-scope'); return ['everything', 'personal', 'business'].includes(s) ? s : 'everything'; };
  const inScope = (scope, s) => scope === 'everything' || s === scope || s === 'all';
  const C = path => LedgerHomeCache.read(path);
  const scopeDot = s => `<span class="a-scope" data-s="${s === 'business' ? 'business' : 'personal'}"><i></i>${s === 'business' ? 'Business' : 'Personal'}</span>`;

  /* ---------------- Icons (one stroke set) ---------------- */
  const P = {
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
    swap: '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    sync: '<path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M3 21v-5h5"/>',
    moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    sliders: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    chev: '<path d="m9 6 6 6-6 6"/>',
    alert: '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
    tag: '<path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9-9-9z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    repeat: '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
    check: '<path d="m5 12 5 5 9-10"/>',
    cart: '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M3 4h2l2.4 11.2a1 1 0 0 0 1 .8h9.7a1 1 0 0 0 1-.8L21 8H6.2"/>',
    coffee: '<path d="M4 8h13v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V8z"/><path d="M17 10h1.5a2.5 2.5 0 0 1 0 5H17"/><path d="M8 2v3M12 2v3"/>',
    cutlery: '<path d="M7 3v8a2 2 0 0 0 2 2v8M11 3v8a2 2 0 0 1-2 2M7 3v5M17 21V3c-2 1-3 4-3 8h3"/>',
    fuel: '<path d="M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16"/><path d="M3 21h12"/><path d="M4 10h10"/><path d="M14 8h2a2 2 0 0 1 2 2v6a1.5 1.5 0 0 0 3 0V8l-3-3"/>',
    car: '<path d="M5 17h14v-5l-2-5H7l-2 5v5z"/><path d="M3 12h18"/><circle cx="7.5" cy="17" r="1.5"/><circle cx="16.5" cy="17" r="1.5"/>',
    park: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M10 16V8h3a2.5 2.5 0 0 1 0 5h-3"/>',
    laptop: '<rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/>',
    wifi: '<path d="M2 9a15 15 0 0 1 20 0"/><path d="M5 12.5a10 10 0 0 1 14 0"/><path d="M8.5 16a5 5 0 0 1 7 0"/><path d="M12 19.5h.01"/>',
    bank: '<path d="M3 10 12 4l9 6"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/><path d="M3 21h18"/>',
    heart: '<path d="M12 20s-7-4.4-9-9a4.8 4.8 0 0 1 9-3 4.8 4.8 0 0 1 9 3c-2 4.6-9 9-9 9z"/>',
    shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3z"/>',
    bag: '<path d="M5 8h14l-1 13H6L5 8z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
    plane: '<path d="M10.5 13.5 3 11l1.5-1.5 8 1L17 6a2 2 0 0 1 3 3l-4.5 4.5 1 8L15 23l-2.5-7.5L9 19v3l-1.5 1L6 19l-4-1.5L3 16h3l4.5-2.5z"/>',
    film: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    clip: '<path d="M21 11.5 12.5 20a5 5 0 0 1-7-7L14 4.5a3.3 3.3 0 0 1 4.7 4.7L10.2 17.7a1.7 1.7 0 0 1-2.4-2.4L15.5 7.6"/>',
    megaphone: '<path d="M3 11v3a1 1 0 0 0 1 1h3l6 4V6L7 10H4a1 1 0 0 0-1 1z"/><path d="M17 8a5 5 0 0 1 0 8"/>',
    box: '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9z"/><path d="m3 7.5 9 4.5 9-4.5M12 12v9"/>',
    in: '<path d="M17 7 7 17"/><path d="M15 17H7V9"/>',
    bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
    book: '<path d="M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3V4z"/><path d="M4 17a3 3 0 0 1 3-3h11"/>',
    paw: '<circle cx="6" cy="10" r="2"/><circle cx="10" cy="6" r="2"/><circle cx="14" cy="6" r="2"/><circle cx="18" cy="10" r="2"/><path d="M8 17a4 4 0 0 1 8 0c0 2-2 3-4 3s-4-1-4-3z"/>',
    sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    brief: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/><path d="M3 13h18"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    trend: '<path d="M3 17 9 11l4 4 8-8"/><path d="M15 7h6v6"/>',
    flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    wallet: '<path d="M3 7a2 2 0 0 1 2-2h13v4"/><path d="M3 7v11a2 2 0 0 0 2 2h15V9H5a2 2 0 0 1-2-2z"/><circle cx="16" cy="14.5" r="1.2"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    pie: '<path d="M21 12A9 9 0 1 1 12 3v9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>',
  };
  const ico = (name, cls = 'a-i') => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[name] || P.tag}</svg>`;
  const RULES = [
    [/transfer|credit card payment|loan|debt/, 'swap'], [/grocer|supermarket/, 'cart'], [/coffee|cafe/, 'coffee'],
    [/eat|restaurant|meal|food|dining|bar\b/, 'cutlery'], [/gas|fuel|transport/, 'fuel'], [/parking/, 'park'], [/\bcar\b|auto/, 'car'],
    [/software|saas|hardware|equipment|computer/, 'laptop'], [/internet|phone/, 'wifi'], [/bank|fee|interest/, 'bank'],
    [/rent|mortgage|home|garden|studio|cowork/, 'home'], [/health|fitness|gym|medical|care/, 'heart'], [/insurance/, 'shield'],
    [/shop|amazon|clothing/, 'bag'], [/travel|vacation|flight|hotel/, 'plane'], [/entertain|movie|music|stream|game/, 'film'],
    [/subscription/, 'repeat'], [/office|suppl/, 'clip'], [/advertis|marketing/, 'megaphone'], [/ship|postage|inventory/, 'box'],
    [/income|payroll|salary|invoice|client|refund|reimburse|revenue/, 'in'], [/utilit|bill|electric/, 'bolt'], [/educat|book|course/, 'book'],
    [/kid|pet/, 'paw'], [/personal care|beauty/, 'sparkle'], [/professional|contractor|consult|work|business/, 'brief'], [/invest/, 'trend'], [/cash|check/, 'wallet'],
  ];
  const catIcon = name => { const n = String(name || '').toLowerCase(); return (RULES.find(([re]) => re.test(n)) || [, 'tag'])[1]; };
  const txIcon = t => t.is_transfer ? 'swap' : t.amount > 0 ? 'in' : t.category_id ? catIcon(t.cat_name) : 'tag';
  const txTone = t => t.is_transfer ? '' : t.amount > 0 ? 'pos' : !t.category_id ? 'dash' : t.scope === 'business' ? 'biz' : 'per';

  /* ---------------- Chrome: header, scope switch, navigation ---------------- */
  function chrome() {
    const menu = document.getElementById('btn-menu');
    if (menu && !menu.querySelector('svg')) menu.innerHTML = ico('menu');
    const refresh = document.getElementById('btn-refresh');
    if (refresh && !refresh.querySelector('svg')) refresh.innerHTML = ico('sync');
    const theme = document.querySelector('#topbar [aria-label="Switch light / dark"]');
    const want = root.dataset.theme === 'dark' ? 'sun' : 'moon';
    if (theme && theme.dataset.aIcon !== want) { theme.innerHTML = ico(want); theme.dataset.aIcon = want; }
    document.querySelectorAll('#topbar > .btn').forEach(b => { if (/Edit design/.test(b.textContent)) b.classList.add('a-hide'); });
    const allTab = document.querySelector('#scope-bar [data-rd-scope="everything"] .rd-switch-top span');
    if (allTab && allTab.textContent !== 'All') allTab.textContent = 'All';
    const navIcons = { overview: 'home', transactions: 'swap', subscriptions: 'repeat', future: 'trend', budgets: 'target', goals: 'flag', personal: 'user', business: 'brief', reports: 'chart', accounts: 'wallet', settings: 'gear' };
    document.querySelectorAll('#nav .nav-link[data-page]').forEach(link => {
      const span = link.querySelector('.nav-icon');
      if (span && navIcons[link.dataset.page] && !span.querySelector('svg')) span.innerHTML = ico(navIcons[link.dataset.page]);
      if (link.dataset.page === 'transactions') { const l = link.querySelector('.nav-label'); if (l && l.textContent !== 'Activity') l.textContent = 'Activity'; }
    });
    const bottom = document.getElementById('mobile-nav');
    if (bottom && !bottom.dataset.a) {
      bottom.dataset.a = '1';
      const icons = { overview: 'home', transactions: 'swap', budgets: 'target' };
      bottom.querySelectorAll('[data-mobile-page]').forEach(link => {
        link.querySelector('.mobile-nav-icon').innerHTML = ico(icons[link.dataset.mobilePage] || 'grid');
        if (link.dataset.mobilePage === 'transactions') link.lastElementChild.textContent = 'Activity';
      });
      const more = bottom.querySelector('#mobile-more');
      if (more) more.querySelector('.mobile-nav-icon').innerHTML = ico('grid');
      const add = document.createElement('button');
      add.type = 'button';
      add.className = 'mobile-nav-item a-nav-add';
      add.dataset.action = 'add-tx';
      add.setAttribute('aria-label', 'Add a transaction');
      add.innerHTML = `<span class="mobile-nav-icon" aria-hidden="true">${ico('plus')}</span><span>Add</span>`;
      bottom.querySelector('[data-mobile-page="budgets"]')?.before(add);
    }
  }
  new MutationObserver(() => chrome()).observe(document.body, { childList: true });
  new MutationObserver(() => chrome()).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  chrome();

  /* ---------------- Home ---------------- */
  const homeState = { month: null, data: null };

  function sparkline(points) {
    const v = (points || []).map(p => p.balance);
    if (v.length < 2) return '';
    const lo = Math.min(...v), hi = Math.max(...v), den = hi - lo || 1;
    const pts = v.map((y, i) => [i / (v.length - 1) * 300, 40 - (y - lo) / den * 34]);
    const d = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
    return `<svg class="a-spark" viewBox="0 0 300 44" preserveAspectRatio="none" aria-hidden="true"><path class="a-spark-area" d="${d} L300,44 L0,44 Z"/><path class="a-spark-line" d="${d}"/></svg>`;
  }

  function row({ icon, tone = '', title, meta = '', amount = '', amountCls = '', right = '', attrs = '', chev = false, tag = 'button' }) {
    const open = tag === 'button' ? `<button type="button" class="a-row" ${attrs}>` : `<div class="a-row a-row-static" ${attrs}>`;
    return `${open}<span class="a-ic" data-tone="${tone}">${ico(icon)}</span><span class="a-rt"><b>${title}</b>${meta ? `<small>${meta}</small>` : ''}</span>${amount || right ? `<span class="a-ra">${amount ? `<b class="a-amt ${amountCls}">${amount}</b>` : ''}${right ? `<small>${right}</small>` : ''}</span>` : ''}${chev ? ico('chev', 'a-i a-chev') : ''}${tag === 'button' ? '</button>' : '</div>'}`;
  }
  const card = (tile, title, body, link = '', cls = '') => `<section class="card a-card ${cls}" data-home-tile="${tile}"><div class="a-card-h"><h3>${title}</h3>${link}</div>${body}</section>`;
  const link = (label, attrs) => `<button type="button" class="a-link" ${attrs}>${label}</button>`;
  const stat = (label, value, cls = '') => `<div class="a-stat"><small>${label}</small><b class="${cls}">${value}</b></div>`;

  function chartMarkup() {
    const { cfP, cfB, scope } = homeState.data;
    const months = cfP.map((m, i) => ({ key: m.month, label: m.label, p: scope === 'business' ? 0 : m.spend || 0, b: scope === 'personal' ? 0 : (cfB[i] || {}).spend || 0 })).slice(-6);
    const max = Math.max(1, ...months.map(m => m.p + m.b));
    const sel = months.find(m => m.key === homeState.month);
    const avg = months.reduce((s, m) => s + m.p + m.b, 0) / (months.length || 1);
    const pct = v => (v / max * 100).toFixed(1);
    return `<div class="a-bars" data-any="${!!sel}">${months.map(m => `<button type="button" class="a-bar" data-a-month="${m.key}" aria-pressed="${m.key === homeState.month}" aria-label="${esc(m.label)} spending ${cash(m.p + m.b)}${scope === 'everything' ? `, Personal ${cash(m.p)}, Business ${cash(m.b)}` : ''}"><span class="a-bar-track">${m.b ? `<span class="a-bseg" data-s="business" style="height:${pct(m.b)}%"></span>` : ''}${m.p ? `<span class="a-bseg" data-s="personal" style="height:${pct(m.p)}%"></span>` : ''}</span><small>${esc(String(m.label).slice(0, 3))}</small></button>`).join('')}</div>
      ${scope === 'everything' ? '<div class="a-key"><span><i data-s="personal"></i>Personal</span><span><i data-s="business"></i>Business</span></div>' : ''}
      <div class="a-bar-foot"><span>${sel ? esc(sel.label) + (sel.key === monthKey() ? ' so far' : '') : '6-month average'}</span><b>${cash(sel ? sel.p + sel.b : avg)}</b></div>`;
  }

  async function homeA() {
    const scope = getScope();
    const q = scope === 'everything' ? '' : '?scope=' + scope, amp = q ? '&' + q.slice(1) : '';
    const days = Math.max(0, new Date().getDate() - 1);
    const [ov, plan, subs, recent, cfP, cfB, goals, cats, budgets, accounts, nw, bov, biz] = await Promise.all([
      C('/summary/overview' + q), C('/monthly-plan'), C('/subscriptions'), C('/transactions?limit=5' + amp),
      C('/summary/cashflow?months=12&scope=personal'), C('/summary/cashflow?months=12&scope=business'),
      C('/goals'), C(`/summary/categories?days=${days}&kind=expense` + amp), C('/budgets'), C('/accounts'),
      C('/summary/networth?months=12' + amp), C(`/budgets/overview?month=${monthKey()}` + amp).catch(() => ({ summary: { uncategorized_count: 0, uncategorized: 0 } })),
      scope === 'business' ? C('/business/summary') : null,
    ]);
    if (scope !== getScope()) return view.innerHTML;
    updateBadge(subs);
    comfort.subscriptions = [...subs.items, ...subs.candidates, ...(subs.canceled || [])];
    homeState.data = { cfP, cfB, nw, plan, scope, goals, cats };
    const c = comfort.config, today = isoToday(), now = new Date();
    const dim = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate(), day = now.getDate(), left = dim - day + 1;
    const accts = accounts.filter(a => inScope(scope, a.scope));
    const assets = accts.reduce((s, a) => s + Math.max(0, a.balance), 0), debt = accts.reduce((s, a) => s - Math.min(0, a.balance), 0);
    const cashOnHand = accts.filter(a => ['depository', 'checking', 'savings', 'cash'].includes(a.type)).reduce((s, a) => s + a.balance, 0);
    const hour = now.getHours(), greeting = `Good ${hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'}${c.owner_name ? ', ' + esc(c.owner_name) : ''}`;

    // 1. Net worth (first, per the latest direction)
    const nwTitle = { everything: 'Net worth', personal: 'Personal net worth', business: 'Business net position' }[scope];
    const netWorth = `<section class="card a-card a-nw" data-home-tile="net-worth">
      <div class="a-card-h"><h3 class="a-eyebrow">${nwTitle}</h3>${link('Accounts', 'data-rd-page="accounts"')}</div>
      <div class="a-fig">${split(ov.net_worth)}</div>
      <span class="a-delta" data-up="${ov.net_this_month >= 0}">${ov.net_this_month >= 0 ? '▲' : '▼'} ${signedWhole(ov.net_this_month)} this month</span>
      <button type="button" class="a-plain a-spark-btn" data-a-history aria-label="Net worth history">${sparkline(nw)}</button>
      <div class="a-stats">${stat('Assets', whole(assets))}${stat('Debts', whole(debt))}${stat('Cash', whole(cashOnHand))}</div>
      <div class="a-accts">${accts.slice(0, 4).map(a => `<button type="button" class="a-acct" data-rd-account="${esc(a.id)}"><span class="a-dot" data-s="${esc(a.scope)}"></span><span class="a-acct-n">${esc(a.name)}</span><b class="${a.balance < 0 ? 'a-neg' : ''}">${cash(a.balance)}</b></button>`).join('')}</div>
    </section>`;

    // 2. Left to spend
    const target = Number(c.monthly_spending_target || 0), upcomingSum = (plan.pending_spend || 0) + (plan.upcoming || 0);
    const scoped = budgets.filter(b => inScope(scope, b.scope));
    let planCard;
    const month = monthLong();
    if (scope === 'everything' && target) {
      const remaining = target - plan.total_expected, used = plan.total_expected / target * 100;
      planCard = `<div class="a-label">${remaining >= 0 ? `Left to spend in ${month}` : `Over ${month} plan by`}</div>
        <div class="a-fig a-fig-m ${remaining < 0 ? 'a-neg' : ''}">${split(Math.abs(remaining))}</div>
        <p class="a-sub">of ${whole(target)} plan · ${remaining > 0 ? `<b>${whole(remaining / left)}/day</b> for ${left} days` : `${left} days to go`}</p>
        <div class="a-meter" role="img" aria-label="${Math.round(used)}% of plan used, day ${day} of ${dim}"><i style="width:${Math.min(100, used).toFixed(1)}%" data-over="${used > 100}"></i><b style="left:${(day / dim * 100).toFixed(1)}%"></b></div>
        <div class="a-meter-legend"><span>${Math.round(used)}% used</span><span>Day ${day} of ${dim}</span></div>`;
    } else if (scope === 'everything') {
      planCard = `<div class="a-label">Spent in ${month}</div><div class="a-fig a-fig-m">${split(plan.spent)}</div>
        <p class="a-sub">${whole(upcomingSum)} more expected · ${link('Set a plan', 'data-action="spending-plan"')}</p>`;
    } else {
      const lim = scoped.reduce((s, b) => s + b.month_limit, 0), sp = scoped.reduce((s, b) => s + b.spent, 0);
      planCard = lim ? `<div class="a-label">Left in ${LABEL[scope].toLowerCase()} budgets</div><div class="a-fig a-fig-m ${lim - sp < 0 ? 'a-neg' : ''}">${split(lim - sp)}</div>
        <p class="a-sub">of ${whole(lim)} budgeted · ${left} days to go</p>
        <div class="a-meter"><i style="width:${Math.min(100, sp / lim * 100).toFixed(1)}%" data-over="${sp > lim}"></i><b style="left:${(day / dim * 100).toFixed(1)}%"></b></div>
        <div class="a-meter-legend"><span>${Math.round(sp / lim * 100)}% used</span><span>Day ${day} of ${dim}</span></div>`
        : `<div class="a-label">Spent in ${month}</div><div class="a-fig a-fig-m">${split(ov.spend_this_month)}</div><p class="a-sub">No ${LABEL[scope].toLowerCase()} budgets yet · ${link('Add budgets', 'data-rd-page="budgets"')}</p>`;
    }
    const third = scope === 'everything' ? stat('Upcoming', whole(upcomingSum)) : stat(scope === 'business' ? 'Profit' : 'Saved', signedWhole(ov.net_this_month), ov.net_this_month >= 0 ? 'a-pos' : 'a-neg');
    const planSection = `<section class="card a-card a-plan" data-home-tile="plan">
      <div class="a-card-h"><h3 class="a-eyebrow">This month</h3>${scope === 'everything' ? link('Edit plan', 'data-action="spending-plan"') : link('Budgets', 'data-rd-page="budgets"')}</div>
      ${planCard}
      <div class="a-stats">${stat('Income', '+' + whole(ov.income_this_month), 'a-pos')}${scope === 'everything' && !target ? stat('Net', signedWhole(ov.net_this_month), ov.net_this_month >= 0 ? 'a-pos' : 'a-neg') : stat('Spent', whole(scope === 'everything' ? plan.spent : ov.spend_this_month))}${third}</div>
    </section>`;

    // 3. Scope insight
    let insight = '';
    if (scope === 'business') {
      const rate = Number(c.tax_rate_business) || 0;
      insight = card('taxes', 'Set aside for taxes', `<div class="a-fig a-fig-s">${split(Math.max(0, ov.net_this_month) * rate)}</div><p class="a-sub">${(rate * 100).toFixed(1).replace(/\.0$/, '')}% of this month’s profit · ${whole(biz?.estimated_tax_setaside)} over 12 months</p>`, '', 'a-insight');
    } else if (scope === 'personal') {
      const d = ov.net_this_month - ov.prev_net;
      insight = card('saved', 'Saved this month', `<div class="a-fig a-fig-s ${ov.net_this_month < 0 ? 'a-neg' : ''}">${split(ov.net_this_month)}</div><p class="a-sub">${d >= 0 ? '▲' : '▼'} ${whole(Math.abs(d))} vs last month · savings rate ${ov.savings_rate == null ? '—' : Math.round(ov.savings_rate * 100) + '%'}</p>`, '', 'a-insight');
    }

    let withoutRent = '';
    if (root.dataset.reviewMode === 'custom' && scope !== 'business') {
      const rentFree = LedgerSarahBudget.totals(cats);
      withoutRent = card('without-rent', `${month} without rent`, `<button type="button" class="a-plain a-fig a-fig-s" data-a-rentfree aria-label="Inspect spending excluding rent">${split(rentFree.spent)}</button><p class="a-sub">Posted spending outside Rent / Mortgage</p><div class="a-stats">${stat('Rent', whole(rentFree.rent))}${stat('Categories', rentFree.categories.length)}</div>`, '', 'a-insight');
    }

    // 4. Needs a look
    const scopedSubs = subs.items.filter(s => inScope(scope, s.scope));
    const overdue = scopedSubs.filter(s => s.next_due && s.next_due < today && s.status !== 'cancel_requested');
    const looks = [];
    if (overdue.length) looks.push(row({ icon: 'alert', tone: 'warn', title: `${overdue.length} bill${overdue.length === 1 ? '' : 's'} past due date`, meta: esc(overdue.slice(0, 2).map(s => s.merchant).join(', ') + (overdue.length > 2 ? '…' : '')), chev: true, attrs: 'data-rd-page="subscriptions"' }));
    if (bov.summary.uncategorized_count) looks.push(row({ icon: 'tag', tone: '', title: `${bov.summary.uncategorized_count} to categorize`, meta: cash(bov.summary.uncategorized) + ' this month', chev: true, attrs: 'data-a-unc' }));
    const cand = subs.candidates.filter(s => inScope(scope, s.scope));
    if (cand.length) looks.push(row({ icon: 'repeat', tone: '', title: cand.length === 1 ? '1 payment looks recurring' : `${cand.length} payments look recurring`, meta: esc(cand.slice(0, 2).map(s => s.merchant).join(', ')), chev: true, attrs: 'data-rd-page="subscriptions"' }));
    if ((subs.price_reviews || []).length) looks.push(row({ icon: 'alert', tone: 'warn', title: `${subs.price_reviews.length} price change${subs.price_reviews.length === 1 ? '' : 's'}`, meta: esc(subs.price_reviews.slice(0, 2).map(s => s.merchant).join(', ')), chev: true, attrs: 'data-rd-page="subscriptions"' }));
    scoped.filter(b => b.pct >= 90).sort((a, b) => b.pct - a.pct).slice(0, 2).forEach(b => looks.push(row({ icon: catIcon(b.cat_name), tone: b.pct >= 100 ? 'neg' : 'warn', title: `${esc(b.cat_name)} at ${Math.round(b.pct)}%`, meta: `${cash(b.spent)} of ${cash(b.month_limit)}`, chev: true, attrs: `data-rd-budget="${esc(b.category_id)}" data-scope-of="${esc(b.scope)}"` })));
    const review = card('review', 'Needs a look', `<div class="a-rows">${looks.slice(0, 4).join('') || row({ icon: 'check', tone: 'pos', title: 'All caught up', meta: 'Nothing needs you right now', tag: 'div' })}</div>`);

    // 5. Coming up
    const upcoming = scopedSubs.filter(s => s.next_due).sort((a, b) => a.next_due.localeCompare(b.next_due)).slice(0, 4);
    const when = s => { const n = dayDiff(s.next_due); return n < 0 ? `<span class="a-pill" data-tone="warn">${-n} day${n === -1 ? '' : 's'} overdue</span>` : n === 0 ? 'Due today' : n === 1 ? 'Tomorrow' : `In ${n} days`; };
    const coming = card('upcoming', 'Coming up', `<div class="a-rows">${upcoming.map(s => { const d = new Date(s.next_due + 'T12:00:00'); return `<button type="button" class="a-row" data-action="edit-sub" data-id="${esc(s.id)}"><span class="a-date"><b>${d.getDate()}</b><small>${d.toLocaleDateString('en-US', { month: 'short' })}</small></span><span class="a-rt"><b>${esc(s.merchant)}</b><small>${when(s)}</small></span><span class="a-ra"><b class="a-amt">${cash(s.amount)}</b><small>${scopeDot(s.scope)}</small></span></button>`; }).join('') || '<p class="a-empty">No tracked payments coming up.</p>'}</div>`, link('All bills', 'data-rd-page="subscriptions"'));

    // 6. Recent activity
    const recentCard = card('recent', 'Recent activity', `<div class="a-rows">${recent.rows.map(txRow).join('') || '<p class="a-empty">No recent activity.</p>'}</div>`, link('See all', 'data-rd-page="transactions"'));

    // 7. Monthly spending
    const chart = card('monthly-chart', 'Monthly spending', `<div id="a-bars">${chartMarkup()}</div>`, link('Reports', 'data-rd-page="reports"'));

    // 8. Top categories
    const top = cats.slice(0, 5), max = top[0]?.amt || 1;
    const catsCard = card('categories', 'Top categories', `<div class="a-rows">${top.map((x, i) => `<button type="button" class="a-row a-catrow" data-k="k${i + 1}" data-a-catname="${esc(x.name)}"><span class="a-ic">${ico(catIcon(x.name))}</span><span class="a-rt"><b>${esc(x.name)}</b><span class="a-catbar"><i style="width:${(x.amt / max * 100).toFixed(1)}%"></i></span></span><span class="a-ra"><b class="a-amt">${cash(x.amt)}</b><small>${Math.round(x.pct)}%</small></span></button>`).join('') || '<p class="a-empty">Spending will appear here.</p>'}</div>`, cats.length > 5 ? link(`All ${cats.length}`, 'data-rd-page="budgets"') : '');

    // 9. Goals
    const goalRows = goals.filter(g => inScope(scope, g.scope)).slice(0, 3);
    const goalsCard = card('goals', 'Savings goals', `<div class="a-rows">${goalRows.map(g => `<button type="button" class="a-row a-goal" data-s="${g.scope === 'business' ? 'business' : 'personal'}" data-a-goal="${esc(g.id)}"><span class="a-ic" data-tone="${g.scope === 'business' ? 'biz' : 'per'}">${ico('flag')}</span><span class="a-rt"><b>${esc(g.name)}</b><span class="a-catbar"><i style="width:${Math.min(100, g.pct).toFixed(1)}%"></i></span></span><span class="a-ra"><b class="a-amt">${Math.round(g.pct)}%</b><small>${whole(g.saved)} of ${whole(g.target)}</small></span></button>`).join('')}${goalRows.length < 3 ? `<button type="button" class="a-row a-add-row" data-rd-page="goals"><span class="a-ic" data-tone="dash">${ico('plus')}</span><span class="a-rt"><b>Add a goal</b></span></button>` : ''}</div>`, goalRows.length ? link('Manage', 'data-rd-page="goals"') : '');

    return `<div class="rd rd-home a-home" data-home-scope="${scope}" data-insight="${!!insight}">
      <div class="rd-welcome a-welcome"><div><p class="a-date-line">${now.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })} · ${accounts.length} accounts</p><h2>${greeting}</h2></div>${action('add-tx', '＋ Add transaction', '', 'btn btn-primary')}</div>
      <div class="a-home-grid">${netWorth}${planSection}${insight}${withoutRent}${review}${coming}${recentCard}${chart}${catsCard}${goalsCard}</div>
    </div>`;
  }

  /* ---------------- Activity ---------------- */
  const txA = { uncOnly: false, limit: 40, filtersOpen: false };
  function txRow(t) {
    const name = receiptDisplayName(t);
    const cat = t.is_transfer ? 'Transfer' : t.allocations?.length > 1 ? 'Split purchase' : t.cat_name || '';
    const acct = t.account_id ? (t.acct_mask ? '…' + t.acct_mask : t.acct_name || 'Account') : 'Cash';
    const meta = cat ? `${esc(cat)} · ${esc(acct)}` : `<span class="a-addcat">+ Add category</span>`;
    const right = t.pending ? '<span class="a-pill">Pending</span>' : scopeDot(t.scope);
    return row({ icon: txIcon(t), tone: txTone(t), title: esc(name), meta, amount: signed(t.amount), amountCls: t.amount > 0 && !t.is_transfer ? 'a-pos' : '', right, attrs: `data-rd-tx="${esc(t.id)}"` });
  }
  const dayLabel = iso => { const n = dayDiff(iso); return n === 0 ? 'Today' : n === -1 ? 'Yesterday' : new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', ...(iso.slice(0, 4) === isoToday().slice(0, 4) ? {} : { year: 'numeric' }) }); };

  async function activityA() {
    const scope = getScope(), f = state.txFilters;
    f.scope = '';
    const month = (f.since || '').slice(0, 7) || monthKey();
    const sq = scope === 'everything' ? '' : '&scope=' + scope;
    const [receipts, active, archived, ov] = await Promise.all([api('/receipts'), api('/accounts'), api('/accounts?archived=1'), api(`/budgets/overview?month=${month}` + sq).catch(() => ({ summary: { total: 0, uncategorized: 0, uncategorized_count: 0 }, categories: [], uncategorized_transactions: [] }))]);
    let data;
    if (txA.uncOnly) {
      const ids = new Set(ov.uncategorized_transactions.map(t => t.id));
      const end = new Date(+month.slice(0, 4), +month.slice(5), 0).getDate();
      const all = await api(`/transactions?since=${month}-01&until=${month}-${String(end).padStart(2, '0')}&limit=1000` + sq);
      const rows = all.rows.filter(t => ids.has(t.id));
      data = { rows, total: rows.length, limit: rows.length || 1, offset: 0 };
    } else {
      const params = new URLSearchParams(Object.entries({ search: f.search, account_id: f.account_id, category_id: f.category_id, since: f.since, until: f.until }).filter(([, v]) => v));
      if (scope !== 'everything') params.set('scope', scope);
      params.set('limit', txA.limit); params.set('offset', f.offset || 0);
      data = await api('/transactions?' + params);
    }
    receiptState.summary = receipts;
    const accounts = [...active, ...archived];
    const nFilters = [f.account_id, f.category_id, f.since, f.until].filter(Boolean).length;
    const s = ov.summary, total = s.total || 0;
    const named = ov.categories.filter(x => x.id !== null && x.total > 0);
    const tones = ['k1', 'k2', 'k3', 'k4'];
    const segs = named.slice(0, 4).map((x, i) => ({ k: tones[i], total: x.total })).concat([{ k: 'k5', total: named.slice(4).reduce((a, x) => a + x.total, 0) }, { k: 'unc', total: s.uncategorized || 0 }]).filter(x => x.total > 0);
    const activeCat = state.categories.find(x => x.id === f.category_id);
    const groups = [];
    for (const t of data.rows) { const g = groups.at(-1); if (g && g.day === t.posted) g.rows.push(t); else groups.push({ day: t.posted, rows: [t] }); }
    const dayTotal = rows => rows.filter(t => !t.is_transfer).reduce((a, t) => a + t.amount, 0);
    const glanceCard = `<section class="card a-card a-glance">
            <div class="a-label">Spent in ${esc(new Date(month + '-01T12:00:00').toLocaleDateString('en-US', { month: 'long' }))}</div>
            <div class="a-fig a-fig-m">${split(total)}</div>
            <div class="a-stack" role="img" aria-label="Spending by category">${segs.map(x => `<i data-k="${x.k}" style="flex:${x.total.toFixed(2)}"></i>`).join('')}</div>
            <div class="a-legend">${named.slice(0, 4).map((x, i) => `<button type="button" class="a-leg" data-k="${tones[i]}" data-a-catf="${esc(x.id)}" aria-pressed="${f.category_id === x.id}"><i></i><span>${esc(x.name)}</span><b>${whole(x.total)}</b></button>`).join('')}${s.uncategorized > 0 ? `<button type="button" class="a-leg" data-k="unc" data-a-unc aria-pressed="${txA.uncOnly}"><i></i><span>Uncategorized</span><b>${whole(s.uncategorized)}</b></button>` : ''}</div>
            ${named.length > 4 ? `<button type="button" class="a-link a-glance-more" data-rd-page="budgets">All ${named.length} categories</button>` : ''}
          </section>`;
    return `<div class="rd a-activity">
      <div class="a-pagehead"><div><h2>Activity</h2><p>${esc(new Date(month + '-01T12:00:00').toLocaleDateString('en-US', { month: 'long', year: 'numeric' }))} · ${LABEL[scope]}</p></div>${action('add-cash-tx', '＋ Cash', '', 'btn btn-primary btn-sm')}</div>
      <div class="a-act-grid">
        <div class="a-act-main">
          <div class="a-search" role="search" aria-label="Transaction filters">
            <label class="a-field">${ico('search')}<span class="rd-sr">Search transactions</span><input id="tx-search" data-a-search type="search" placeholder="Search merchant or note" value="${esc(f.search)}" autocomplete="off"></label>
            <button type="button" class="a-iconbtn" data-a-filters aria-expanded="${txA.filtersOpen}" aria-controls="a-filters" aria-label="Filters${nFilters ? ', ' + nFilters + ' active' : ''}">${ico('sliders')}${nFilters ? `<span class="a-badge">${nFilters}</span>` : ''}</button>
          </div>
          <div class="a-filters" id="a-filters" ${txA.filtersOpen ? '' : 'hidden'}>
            <label><span>Account</span><select class="input" data-rd-filter="account_id"><option value="">All accounts</option><option value="__cash__" ${f.account_id === '__cash__' ? 'selected' : ''}>Cash / manual</option>${accounts.map(a => `<option value="${esc(a.id)}" ${f.account_id === a.id ? 'selected' : ''}>${esc(a.name)}${a.mask ? ' …' + esc(a.mask) : ''}${a.archived ? ' · archived' : ''}</option>`).join('')}</select></label>
            <label><span>Category</span><select class="input" data-rd-filter="category_id"><option value="">All categories</option>${state.categories.map(x => `<option value="${esc(x.id)}" ${f.category_id === x.id ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select></label>
            <label><span>From</span><input type="date" class="input" value="${esc(f.since)}" data-rd-filter="since"></label>
            <label><span>To</span><input type="date" class="input" value="${esc(f.until)}" data-rd-filter="until"></label>
            <button type="button" class="btn btn-sm" data-a-clear>Clear filters</button>
          </div>
          <div class="a-chips" role="group" aria-label="Quick filters">
            <button type="button" class="a-chip" data-a-unc aria-pressed="${txA.uncOnly}">Needs category${s.uncategorized_count ? ' · ' + s.uncategorized_count : ''}</button>
            <button type="button" class="a-chip" data-a-cash aria-pressed="${f.account_id === '__cash__'}">Cash</button>
            ${activeCat ? `<button type="button" class="a-chip" aria-pressed="true" data-a-catf="${esc(activeCat.id)}">${esc(activeCat.name)} ✕</button>` : ''}
            ${f.search ? `<button type="button" class="a-chip" aria-pressed="true" data-a-clear-search>“${esc(f.search)}” ✕</button>` : ''}
          </div>
          <div class="a-glance-phone">${glanceCard}</div>
          ${(() => { const r = receiptSummaryMarkup(receipts); return r.includes('Nothing needs a closer look') ? '' : r; })()}
          ${groups.map(g => `<div class="card a-list"><div class="a-day"><span>${esc(dayLabel(g.day))}</span><b>${signed(dayTotal(g.rows))}</b></div>${g.rows.map(txRow).join('')}</div>`).join('') || `<div class="card a-list"><p class="a-empty">${txA.uncOnly ? 'Nothing uncategorized this month.' : 'No transactions match.'}</p></div>`}
          ${txA.uncOnly ? '' : `<div class="a-pager"><button type="button" class="btn btn-sm" data-a-step="-1" ${data.offset > 0 ? '' : 'disabled'}>Newer</button><span>${data.rows.length ? data.offset + 1 : 0}–${data.offset + data.rows.length} of ${data.total}</span><button type="button" class="btn btn-sm" data-a-step="1" ${data.offset + data.limit < data.total ? '' : 'disabled'}>Older</button></div>`}
        </div>
        <aside class="a-act-side">
          ${glanceCard}
        </aside>
      </div>
    </div>`;
  }

  /* ---------------- Sheets ---------------- */
  const seg = (target, value, options, label) => `<div class="a-seg" role="group" aria-label="${label}" style="--n:${options.length}">${options.map(([v, l, s]) => `<button type="button" data-a-set="${target}" data-v="${v}" aria-pressed="${v === value}">${s ? `<span class="a-dot" data-s="${s}"></span>` : ''}${l}</button>`).join('')}</div>`;
  const PRIORITY = ['groceries', 'eat out', 'restaurants', 'gas', 'shopping', 'entertainment', 'health', 'coffee', 'travel'];
  function quickCats(kind, current) {
    const pool = state.categories.filter(c => !kind || c.kind === kind);
    const ranked = pool.slice().sort((a, b) => {
      const ia = PRIORITY.findIndex(p => a.name.toLowerCase().includes(p)), ib = PRIORITY.findIndex(p => b.name.toLowerCase().includes(p));
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
    const cur = pool.find(c => c.id === current);
    return [...(cur ? [cur] : []), ...ranked.filter(c => c.id !== current)];
  }
  const catGrid = (target, list, current) => `<div class="a-cats" role="group" aria-label="Category">${list.map(c => `<button type="button" class="a-cat" data-a-set="${target}" data-v="${esc(c.id)}" data-name="${esc(c.name.toLowerCase())}" aria-pressed="${c.id === current}">${ico(catIcon(c.name))}<span>${esc(c.name)}</span></button>`).join('')}</div>`;

  window.openTxEdit = async function (id) {
    const f = state.txFilters;
    let t = (await api('/transactions?' + new URLSearchParams(Object.entries(f).filter(([, v]) => v !== '' && v != null)))).rows.find(r => r.id === id);
    if (!t) t = (await api('/transactions?limit=500')).rows.find(r => r.id === id);
    if (!t) return toast('Transaction not found', 'err');
    let subscription;
    try { subscription = txSubscriptionMatch(await api('/subscriptions'), t); }
    catch (e) { return toast(e.message || 'Could not load subscription frequency. Try again.', 'err'); }
    txRecurringContext = { transaction: t, subscription };
    const frequency = subscription?.cadence || 'monthly';
    const isCash = !t.account_id, name = receiptDisplayName(t);
    const kind = t.is_transfer ? (t.amount > 0 ? 'transfer-in' : 'transfer-out') : (t.amount > 0 ? 'income' : 'expense');
    const catKind = t.is_transfer ? '' : t.amount > 0 ? 'income' : 'expense';
    const curCat = state.categories.find(c => c.id === t.category_id);
    showModal(`<div class="a-sheet">
      <button type="button" class="close-button" data-action="close" aria-label="Close dialog">${ico('plus', 'a-i a-x')}</button>
      <h2>${isCash ? 'Edit cash entry' : esc(name)}</h2>
      <p class="a-meta"><b class="${t.amount > 0 && !t.is_transfer ? 'a-pos' : ''}">${signed(t.amount)}</b> · ${fmtDate(t.posted)} · ${esc(t.account_id ? (t.acct_name || 'Account') + (t.acct_mask ? ' …' + t.acct_mask : '') : 'Cash / manual')}${t.pending ? ' · Pending' : ''}</p>
      <label class="fld" for="txe-name">Name / merchant</label><input class="input" id="txe-name" value="${esc(t.display_name || t.merchant || t.name)}" maxlength="200">
      ${isCash ? `
        <span class="fld">Type</span>${seg('txe-kind', kind, [['expense', 'Out'], ['income', 'In'], ['transfer-out', 'Xfer out'], ['transfer-in', 'Xfer in']], 'Type')}<input type="hidden" id="txe-kind" value="${kind}">
        <div class="form-pair"><div><label class="fld" for="txe-amount">Amount</label><input class="input" id="txe-amount" type="number" inputmode="decimal" min="0.01" step="0.01" value="${Math.abs(t.amount)}"></div><div><label class="fld" for="txe-posted">Date</label><input class="input" id="txe-posted" type="date" max="${todayISO()}" value="${esc(t.posted)}"></div></div>`
        : `<p class="a-note">Amount and date come from your bank.</p>`}
      <span class="fld">Whose money</span>${seg('txe-scope', t.scope, [['personal', 'Personal', 'personal'], ['business', 'Business', 'business']], 'Whose money')}<input type="hidden" id="txe-scope" value="${esc(t.scope)}">
      <div class="a-fldrow"><span class="fld">Category</span><span class="a-cur" data-a-cur="txe-cat">${esc(curCat ? curCat.name : 'Uncategorized')}</span></div>
      <label class="a-field a-field-s">${ico('search')}<span class="rd-sr">Find a category</span><input type="search" placeholder="Find a category" data-a-catsearch autocomplete="off"></label>
      ${catGrid('txe-cat', quickCats(catKind, t.category_id), t.category_id)}
      <input type="hidden" id="txe-cat" value="${esc(t.category_id || '')}" data-original-value="${esc(t.category_id || '')}">
      ${Array.isArray(t.allocations) && t.allocations.length ? `<p class="a-note a-warn">This charge is split across ${t.allocations.length} items. Choosing a category replaces the split.</p>` : ''}
      <details class="a-more"><summary>Note, recurring${isCash ? '' : ', transfer, bank text'}</summary>
        <label class="fld" for="txe-note">Note</label><input class="input" id="txe-note" value="${esc(t.note || '')}">
        <label class="a-check"><input type="checkbox" id="txe-rec" onchange="toggleTxFrequency()" ${t.recurring ? 'checked' : ''}><span>Recurring payment</span></label>
        <div id="txe-frequency-fields" ${t.recurring ? '' : 'hidden'}>
          <label class="fld" for="txe-frequency">Frequency</label><select class="input" id="txe-frequency" onchange="toggleTxFrequency()">${txFrequencies.map(([v, l]) => `<option value="${v}" ${frequency === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
          <div id="txe-custom-field" ${frequency === 'custom' ? '' : 'hidden'}><label class="fld" for="txe-custom-days">Days between payments</label><input class="input" id="txe-custom-days" type="number" inputmode="numeric" min="1" max="366" step="1" value="${Number(subscription?.custom_interval_days) || 30}"></div>
        </div>
        ${isCash ? '' : `<label class="a-check"><input type="checkbox" id="txe-transfer" ${t.is_transfer ? 'checked' : ''}><span>Transfer between my accounts</span></label><p class="a-raw"><small>Bank description</small>${esc(t.name)}</p>`}
        <div class="receipt-edit-cta">${receiptEditAction(t.id, t.receipt_status)}</div>
        <button type="button" class="a-danger" onclick="deleteTx(${esc(JSON.stringify(t.id))})">Delete transaction</button>
      </details>
      <div class="modal-actions a-actions"><button type="button" class="btn btn-primary a-save" onclick="saveTxEdit(${esc(JSON.stringify(t.id))}, this)">Save</button></div>
    </div>`);
    document.querySelector('.modal')?.classList.add('a-modal');
  };

  openAddTx = async function (options = {}) {
    state.accounts = await api('/accounts');
    const isCash = options === true || options?.cash, remembered = isCash ? '' : (read('ledger-last-account') || '');
    const selected = state.accounts.find(a => a.id === remembered), scope0 = selected?.scope || (getScope() === 'business' ? 'business' : 'personal');
    showModal(`<div class="a-sheet">${modalTitle(isCash ? 'Add cash' : 'Add transaction')}
      <form data-form="transaction" class="a-add">
        ${seg('f-kind', 'expense', [['expense', 'Money out'], ['income', 'Money in'], ['transfer-out', 'Transfer']], 'Type')}<input type="hidden" name="kind" id="f-kind" value="expense">
        <label class="a-amount"><span aria-hidden="true">$</span><input id="f-amount" name="amount" type="number" inputmode="decimal" min="0.01" step="0.01" required autofocus placeholder="0.00" aria-label="Amount"></label>
        <label class="fld" for="f-name">Name</label><input class="input" id="f-name" name="name" required maxlength="200" placeholder="e.g. Farmers market">
        <div class="form-pair">
          <div><label class="fld" for="f-posted">Date</label><input class="input" id="f-posted" name="posted" type="date" required max="${todayISO()}" value="${todayISO()}"></div>
          <div><span class="fld">For</span>${seg('f-transaction-scope', scope0, [['personal', 'Pers.', 'personal'], ['business', 'Biz', 'business']], 'For')}<input type="hidden" name="scope" id="f-transaction-scope" value="${scope0}"></div>
        </div>
        <label class="fld" for="f-account">Paid from</label><select class="input" id="f-account" name="account_id" data-a-acct>${transactionAccountOptions(remembered)}</select>
        <div class="a-fldrow"><span class="fld">Category</span><span class="a-cur" data-a-cur="f-category">Uncategorized</span></div>
        <label class="a-field a-field-s">${ico('search')}<span class="rd-sr">Find a category</span><input type="search" placeholder="Find a category" data-a-catsearch autocomplete="off"></label>
        ${catGrid('f-category', quickCats('expense', ''), '')}<input type="hidden" name="category_id" id="f-category" value="">
        <details class="a-more"><summary>Add a note</summary>${field('note', 'Note', '', 'text', 'maxlength="2000"')}</details>
        <p class="auth-error" role="alert" data-form-error></p>
        <div class="modal-actions a-actions"><button class="btn btn-primary a-save" type="submit">Save</button></div>
      </form></div>`);
    document.querySelector('.modal')?.classList.add('a-modal');
  };

  /* ---------------- Other pages: wording fixes ---------------- */
  function wrapPage(id, transform) {
    const base = PAGES[id];
    if (base) registerPage(id, base.title, async () => transform(await base.render()));
  }
  wrapPage('subscriptions', html => html
    .replace(/>Monthly commitment</g, '>Per month<').replace(/>A year at this pace</g, '>Per year<').replace(/>Details</g, '>Edit<').replace(/>Cancel subscription</g, '>Cancel it<').replace(/>Mark as canceled</g, '>Mark canceled<')
    .replace(/Next ([A-Z][a-z]{2} \d{1,2}, \d{4})/g, (m, d) => new Date(d) < new Date(isoToday() + 'T00:00:00') ? `<span class="a-overdue">Overdue · ${d.replace(/, \d{4}$/, '')}</span>` : 'Next ' + d.replace(/, \d{4}$/, '')));
  wrapPage('settings', html => html.replace(/`([^`<]{1,80})`/g, '<code>$1</code>'));
  // One icon language: drop emoji category icons from page text (budgets, subscriptions, reports).
  const stripEmoji = html => { for (const c of state.categories || []) if (c.icon) html = html.split(esc(c.icon) + ' ' + esc(c.name)).join(esc(c.name)); return html; };
  for (const id of ['budgets', 'reports']) wrapPage(id, stripEmoji);
  wrapPage('goals', html => stripEmoji(html)
    .replace('<div class="row-between" style="margin-bottom:14px">', '<div class="row-between a-intro-row" style="margin-bottom:12px">')
    .replace(/🎯 by /g, 'Target ').replace(/📈 projected /g, 'On pace for ').replace(/🏆 /g, '').replace(/Complete 🎉/g, 'Complete').replace(/⚠ behind/g, 'behind')
    .replace(/>✕<\/button>/g, ` aria-label="Delete goal">${ico('plus', 'a-i a-x')}</button>`));
  wrapPage('accounts', html => html
    .replace(/<span class="merchant-avatar">▣<\/span>/g, `<span class="merchant-avatar">${ico('bank')}</span>`)
    .replace(/<span class="merchant-avatar">−<\/span>/g, `<span class="merchant-avatar">${ico('wallet')}</span>`)
    .replace(/<span class="merchant-avatar">↗<\/span>/g, `<span class="merchant-avatar">${ico('trend')}</span>`));

  /* ---------------- Registration ---------------- */
  const prev = { overview: PAGES.overview, transactions: PAGES.transactions };
  const layoutOn = () => root.dataset.layout !== 'classic';
  function guarded(render, fallback) {
    return async () => {
      if (!layoutOn()) return fallback.render();
      try { return await render(); }
      catch (e) { console.error('Design A page failed; showing the previous page.', e); return fallback.render(); }
    };
  }
  registerPage('overview', 'Home', guarded(homeA, prev.overview));
  registerPage('transactions', 'Activity', guarded(activityA, prev.transactions));
  for (const id of ['personal', 'business']) registerPage(id, 'Home', guarded(homeA, PAGES[id]));
  if (bootedEarly) setTimeout(() => navigate(state.page), 0);

  /* ---------------- Interactions ---------------- */
  let token = 0;
  async function rerender() {
    const mine = ++token;
    const html = await PAGES[state.page].render();
    if (mine === token) view.innerHTML = html;
  }
  const resetFilters = (extra = {}) => { state.txFilters = { search: '', account_id: '', scope: '', category_id: '', since: '', until: '', offset: 0, ...extra }; };

  document.addEventListener('click', async event => {
    const el = event.target.closest('button');
    if (!el || root.dataset.design !== 'a') return;
    const d = el.dataset;
    try {
      if (d.aSet) {
        const input = document.getElementById(d.aSet);
        if (!input) return;
        input.value = d.v;
        el.parentElement.querySelectorAll('[data-a-set]').forEach(b => b.setAttribute('aria-pressed', String(b === el)));
        const cur = document.querySelector(`[data-a-cur="${d.aSet}"]`);
        if (cur) cur.textContent = el.querySelector('span')?.textContent || 'Uncategorized';
        return;
      }
      if (el.hasAttribute('data-a-rentfree')) {
        const detail = LedgerSarahBudget.totals(homeState.data.cats);
        return showModal(`${modalTitle('This month · without rent')}<p class="sub">Posted expenses only. Transfers, pending payments, and the Rent / Mortgage category are excluded.</p><div class="setting-row"><span>Spending outside rent</span><b>${cash(detail.spent)}</b></div>${detail.categories.map(c => `<div class="setting-row"><span>${esc(c.name)}</span><b>${cash(c.amt)}</b></div>`).join('') || '<p class="quiet-note">No spending outside rent recorded yet.</p>'}<div class="modal-actions">${action('close', 'Close')}</div>`);
      }
      if (el.hasAttribute('data-a-history')) return showModal(`${modalTitle('Net worth history')}<p class="sub">Estimated from current balances and recorded transactions.</p>${lineChart(homeState.data.nw.map(p => ({ label: p.month, v: p.balance })))}<div class="modal-actions">${action('close', 'Close')}${action('page', 'Your future', 'future', 'btn btn-primary')}</div>`);
      if (d.aGoal) { const g = homeState.data.goals.find(x => x.id === d.aGoal); if (g) contribute(g.id, g.name, Math.max(0, g.target - g.saved)); return; }
      if (d.aMonth) { homeState.month = homeState.month === d.aMonth ? null : d.aMonth; document.getElementById('a-bars').innerHTML = chartMarkup(); return; }
      if (d.aCatname !== undefined) { const c = state.categories.find(x => x.name === d.aCatname); if (!c) return; resetFilters({ category_id: c.id }); txA.uncOnly = false; return navigate('transactions'); }
      if (el.hasAttribute('data-a-unc')) {
        if (state.page !== 'transactions') { resetFilters(); txA.uncOnly = true; return navigate('transactions'); }
        txA.uncOnly = !txA.uncOnly; state.txFilters.category_id = ''; state.txFilters.offset = 0; return rerender();
      }
      if (el.hasAttribute('data-a-filters')) { txA.filtersOpen = !txA.filtersOpen; el.setAttribute('aria-expanded', String(txA.filtersOpen)); document.getElementById('a-filters').hidden = !txA.filtersOpen; return; }
      if (el.hasAttribute('data-a-clear')) { resetFilters(); txA.uncOnly = false; return rerender(); }
      if (el.hasAttribute('data-a-clear-search')) { state.txFilters.search = ''; state.txFilters.offset = 0; return rerender(); }
      if (el.hasAttribute('data-a-cash')) { state.txFilters.account_id = state.txFilters.account_id === '__cash__' ? '' : '__cash__'; state.txFilters.offset = 0; txA.uncOnly = false; return rerender(); }
      if (d.aCatf) { state.txFilters.category_id = state.txFilters.category_id === d.aCatf ? '' : d.aCatf; state.txFilters.offset = 0; txA.uncOnly = false; return rerender(); }
      if (d.aStep) { state.txFilters.offset = Math.max(0, (state.txFilters.offset || 0) + Number(d.aStep) * txA.limit); await rerender(); document.getElementById('main')?.scrollTo?.({ top: 0 }); scrollTo({ top: 0 }); return; }
    } catch (e) { toast(e.message || 'Something went wrong. Try again.', 'err'); }
  });
  document.addEventListener('input', event => {
    const el = event.target;
    if (el.matches?.('[data-a-catsearch]')) {
      const q = el.value.trim().toLowerCase();
      el.closest('.a-sheet')?.querySelectorAll('.a-cat').forEach(b => { b.hidden = q && !b.dataset.name.includes(q); });
    }
  });
  document.addEventListener('change', event => {
    const el = event.target;
    if (el.matches?.('[data-a-acct]')) {
      syncTransactionAccountScope(el);
      const v = document.getElementById('f-transaction-scope')?.value;
      el.closest('form')?.querySelectorAll('[data-a-set="f-transaction-scope"]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.v === v)));
    }
  });
  document.addEventListener('keydown', event => {
    const el = event.target;
    if (event.key === 'Enter' && el.matches?.('[data-a-search]')) { state.txFilters.search = el.value.trim(); state.txFilters.offset = 0; txA.uncOnly = false; rerender(); }
  });
  document.addEventListener('search', event => {
    if (event.target.matches?.('[data-a-search]') && !event.target.value) { state.txFilters.search = ''; rerender(); }
  }, true);
})();

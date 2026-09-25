/* Redesign layer: one Everything / Personal / Business switch with a cleaner Home,
   Transactions and Budgets. The classic pages stay registered underneath; choose
   Settings → Layout → Classic (saved for every device) or open ?layout=classic
   (this browser only) to return to them without redeploying. */
(() => {
  'use strict';
  const root = document.documentElement;
  const view = document.getElementById('view');
  const main = document.getElementById('main');
  const classic = {};
  for (const page of ['overview', 'transactions', 'budgets', 'personal', 'business', 'settings']) classic[page] = PAGES[page];

  const SCOPES = ['everything', 'personal', 'business'];
  const SCOPED = new Set(['overview', 'transactions', 'budgets']);
  const LABEL = { everything: 'Everything', personal: 'Personal', business: 'Business' };
  const NET_WORD = { everything: 'net this month', personal: 'saved this month', business: 'profit this month' };
  const read = key => { try { return localStorage.getItem(key); } catch { return null; } };
  const write = (key, value) => { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch {} };

  const urlLayout = new URLSearchParams(location.search).get('layout');
  if (urlLayout === 'classic' || urlLayout === 'new') write('ledger-layout-local', urlLayout);
  const localLayout = () => read('ledger-layout-local');
  const on = () => {
    const local = localLayout();
    if (local === 'classic') return false;
    if (local === 'new') return true;
    return (comfort.config.layout || 'new') !== 'classic';
  };

  // Avoid a flash of the other layout's chrome before the saved setting loads.
  root.dataset.layout = localLayout() === 'classic' ? 'classic' : localLayout() === 'new' ? 'new' : (read('ledger-layout-cache') || 'new');

  let scope = SCOPES.includes(read('ledger-scope')) ? read('ledger-scope') : 'everything';
  const scopeQuery = (prefix = '?') => scope === 'everything' ? '' : `${prefix}scope=${scope}`;
  const inScope = s => scope === 'everything' || s === scope || s === 'all';

  const cash = n => fmtMoney(Number(n) || 0, { decimals: 2 });
  const signed = n => (Number(n) > 0 ? '+' : '') + cash(n);
  const pct = n => Number.isFinite(n) ? Math.round(n) + '%' : '—';
  const monthKey = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  const monthName = key => new Date(key + '-01T12:00:00').toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  const shortMonth = key => new Date(key + '-01T12:00:00').toLocaleDateString('en-US', { month: 'short' });
  const shortDate = iso => { const d = new Date(iso + 'T12:00:00'); return d.toLocaleDateString('en-US', d.getFullYear() === new Date().getFullYear() ? { month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric', year: 'numeric' }); };
  const daysLeft = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate() - d.getDate(); };
  const initials = name => String(name || '·').replace(/[^A-Za-z0-9 ]/g, ' ').split(' ').filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '·';
  const icon = {
    everything: '<svg class="rd-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 13 9 5 9-5"/></svg>',
    personal: '<svg class="rd-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11 12 4l8 7"/><path d="M6 10v10h12V10"/><path d="M10 20v-5h4v5"/></svg>',
    business: '<svg class="rd-ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M3 13h18"/></svg>',
    swap: '<svg class="rd-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4 3 8l4 4"/><path d="M3 8h14"/><path d="m17 20 4-4-4-4"/><path d="M21 16H7"/></svg>',
    up: '<svg class="rd-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
    down: '<svg class="rd-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12l7 7 7-7"/></svg>',
    check: '<svg class="rd-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 5 5L20 7"/></svg>',
  };
  const chip = s => `<span class="rd-chip" data-s="${s === 'business' ? 'business' : s === 'personal' ? 'personal' : 'all'}">${s === 'all' ? 'Both' : LABEL[s] || 'Personal'}</span>`;
  const head = (title, note = '', right = '') => `<div class="rd-head"><div><h3>${title}</h3>${note ? `<p class="rd-note">${note}</p>` : ''}</div>${right}</div>`;

  /* ---------------- Scope switch ---------------- */
  const bar = document.createElement('div');
  bar.id = 'scope-bar';
  bar.className = 'rd-scope-bar';
  bar.hidden = true;
  bar.innerHTML = `<div class="rd-switch" role="tablist" aria-label="Whose money"><span class="rd-switch-ind" aria-hidden="true"></span>${SCOPES.map(s => `
    <button type="button" class="rd-switch-tab" role="tab" data-rd-scope="${s}" aria-selected="${s === scope}">
      <span class="rd-switch-top">${icon[s]}<span>${s === 'business' ? 'Business' : LABEL[s]}</span></span>
      <span class="rd-switch-fig"><b data-rd-net="${s}">—</b><small>${NET_WORD[s]}</small></span>
      <span class="rd-switch-sub" data-rd-sub="${s}"></span>
    </button>`).join('')}</div>`;
  main.insertBefore(bar, view);

  let netsAt = 0;
  async function loadNets(force) {
    if (!force && Date.now() - netsAt < 20000) return;
    netsAt = Date.now();
    try {
      const [all, per, biz] = await Promise.all(['', '?scope=personal', '?scope=business'].map(q => LedgerHomeCache.read('/summary/overview' + q)));
      const data = { everything: all, personal: per, business: biz };
      for (const s of SCOPES) {
        bar.querySelector(`[data-rd-net="${s}"]`).textContent = signed(data[s].net_this_month);
        bar.querySelector(`[data-rd-sub="${s}"]`).textContent = `${s === 'business' ? 'Revenue' : 'In'} ${cash(data[s].income_this_month)} · ${s === 'business' ? 'Costs' : 'Out'} ${cash(data[s].spend_this_month)}`;
      }
    } catch { netsAt = 0; }
  }
  function syncChrome() {
    const active = on();
    root.dataset.layout = active ? 'new' : 'classic';
    if (comfort.config.layout || localLayout()) write('ledger-layout-cache', root.dataset.layout);
    const scoped = active && SCOPED.has(state.page);
    bar.hidden = !scoped;
    root.dataset.scope = scoped ? scope : 'everything';
    bar.querySelectorAll('[data-rd-scope]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.rdScope === scope)));
    if (scoped) loadNets();
  }

  function wash(origin) {
    if (root.dataset.motionPaused === 'true' || matchMedia('(max-width: 700px), (prefers-reduced-motion: reduce)').matches) return;
    const r = origin?.getBoundingClientRect?.();
    const el = document.createElement('div');
    el.className = 'rd-wash';
    el.setAttribute('aria-hidden', 'true');
    el.style.setProperty('--wx', (r ? r.left + r.width / 2 : innerWidth / 2) + 'px');
    el.style.setProperty('--wy', (r ? r.top + r.height / 2 : 80) + 'px');
    document.body.append(el);
    setTimeout(() => el.remove(), 1200);
  }

  // Re-render the current page in place (no "Loading…" flash) and roll the content in.
  async function refresh({ scopeSwitch = false } = {}) {
    const page = state.page;
    const token = state.renderToken = (state.renderToken || 0) + 1;
    try {
      const html = await PAGES[page].render();
      if (state.renderToken !== token) return;
      view.innerHTML = html;
      view.classList.remove('rd-enter');
      if (!scopeSwitch) {
        void view.offsetWidth;
        view.classList.add('rd-enter');
      }
      afterRender();
    } catch (e) {
      if (state.renderToken === token) toast(e.message || 'Could not refresh this page.', 'err');
    }
  }
  function setScope(next, origin) {
    if (!SCOPES.includes(next) || next === scope) return;
    scope = next;
    write('ledger-scope', scope);
    txLocal.uncOnly = false;
    txLocal.selected.clear();
    state.txFilters.offset = 0;
    syncChrome();
    wash(origin);
    refresh({ scopeSwitch: true });
  }

  const baseNavigate = navigate;
  navigate = async function (page) {
    if (on() && (page === 'personal' || page === 'business')) {
      scope = page;
      write('ledger-scope', scope);
      page = 'overview';
    }
    const result = await baseNavigate(page);
    syncChrome();
    afterRender();
    return result;
  };
  const baseApply = applyComfort;
  applyComfort = config => { baseApply(config); syncChrome(); };

  /* ---------------- Undo snackbar ---------------- */
  let undoTimer;
  function undoable(text, undo) {
    document.getElementById('rd-undo')?.remove();
    clearTimeout(undoTimer);
    const el = document.createElement('div');
    el.id = 'rd-undo';
    el.className = 'rd-undo';
    el.setAttribute('role', 'status');
    el.innerHTML = `<span>${esc(text)}</span>${undo ? '<button type="button" class="rd-undo-btn">Undo</button>' : ''}`;
    document.body.append(el);
    el.querySelector('.rd-undo-btn')?.addEventListener('click', async () => {
      el.remove();
      try { await undo(); await refresh(); toast('Undone', 'ok'); } catch (e) { toast(e.message || 'Could not undo.', 'err'); }
    });
    undoTimer = setTimeout(() => el.remove(), 6500);
  }
  const updateTx = body => api('/transactions/update', { method: 'POST', body: JSON.stringify(body) });

  /* ---------------- Home ---------------- */
  const home = { range: matchMedia('(max-width:700px)').matches ? 6 : 12, metric: 'spend', month: null, cat: 0, data: null };

  function spark(points) {
    const values = points.map(p => p.balance);
    if (values.length < 2) return '';
    const lo = Math.min(...values), hi = Math.max(...values), den = hi - lo || 1;
    const pts = values.map((v, i) => [i / (values.length - 1) * 600, 70 - (v - lo) / den * 62]);
    let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) { const [x, y] = pts[i], [px, py] = pts[i - 1], m = ((x + px) / 2).toFixed(1); d += ` C${m},${py.toFixed(1)} ${m},${y.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`; }
    return `<svg class="rd-spark" viewBox="0 0 600 78" preserveAspectRatio="none" aria-hidden="true"><path class="rd-spark-area" d="${d} L600,78 L0,78 Z"/><path class="rd-spark-line" d="${d}" pathLength="1"/></svg>`;
  }

  function barsMarkup() {
    const { cfP, cfB } = home.data;
    const months = cfP.map((m, i) => ({ key: m.month, label: m.label, p: m[home.metric] || 0, b: (cfB[i] || {})[home.metric] || 0 })).slice(-home.range)
      .map(m => ({ ...m, p: scope === 'business' ? 0 : m.p, b: scope === 'personal' ? 0 : m.b }));
    const max = Math.max(1, ...months.map(m => m.p + m.b));
    const word = home.metric === 'spend' ? 'spending' : 'income';
    const sel = months.find(m => m.key === home.month);
    const avg = months.reduce((s, m) => s + m.p + m.b, 0) / (months.length || 1);
    return `<div class="rd-bars" data-any="${!!sel}" style="grid-template-columns:repeat(${months.length},minmax(0,1fr))">${months.map(m => `
      <button type="button" class="rd-bar" data-rd-month="${m.key}" aria-pressed="${m.key === home.month}" aria-label="${esc(monthName(m.key))} ${word} ${cash(m.p + m.b)}">
        <span class="rd-bar-track"><span class="rd-bar-val">${cash(m.p + m.b)}</span><span class="rd-seg rd-seg-b" style="height:${(m.b / max * 100).toFixed(2)}%"></span><span class="rd-seg rd-seg-p" style="height:${(m.p / max * 100).toFixed(2)}%"></span></span>
        <span class="rd-bar-lbl">${esc(m.label)}</span></button>`).join('')}</div>
      <div class="rd-foot"><span>${sel ? esc(monthName(sel.key)) + (sel.key === monthKey() ? ' so far' : '') : home.range + '-month average'}${scope === 'everything' ? '<span class="rd-legend"><span data-s="personal"><i></i>Personal</span><span data-s="business"><i></i>Business</span></span>' : ''}</span><b>${cash(sel ? sel.p + sel.b : avg)}</b></div>`;
  }

  function catDetail() {
    const { cats, budgets } = home.data;
    const c = cats[home.cat];
    if (!c) return '<p class="rd-note">Your spending will appear here as you add transactions.</p>';
    const b = budgets.filter(x => x.cat_name === c.name && inScope(x.scope));
    const limit = b.reduce((s, x) => s + x.month_limit, 0), spent = b.reduce((s, x) => s + x.spent, 0);
    const width = limit ? Math.min(100, spent / limit * 100) : c.pct;
    const cat = state.categories.find(x => x.name === c.name);
    return `<div class="rd-detail rd-enter">
      <h4>${esc(c.name)}</h4><p class="rd-note">${c.pct}% of ${scope === 'everything' ? 'all' : LABEL[scope].toLowerCase()} spending this month</p>
      <div class="rd-big">${cash(c.amt)}</div>
      <div class="rd-track"><i style="width:${width}%"></i></div>
      <div class="rd-stat3"><div><small>Budget</small><b>${limit ? cash(limit) : 'Not set'}</b></div><div><small>Purchases</small><b>${c.n}</b></div><div><small>Remaining</small><b>${limit ? cash(limit - spent) : '—'}</b></div></div>
      <div class="rd-links">${cat ? `<button type="button" class="link-button" data-rd-filter-cat="${esc(cat.id)}">View transactions →</button>` : ''}<button type="button" class="link-button" data-rd-page="budgets">Budgets →</button></div></div>`;
  }

  function homePaths(selectedScope) {
    const q = selectedScope === 'everything' ? '' : '&scope=' + selectedScope;
    const days = Math.max(0, new Date().getDate() - 1);
    return [
      '/summary/overview' + (q ? '?' + q.slice(1) : ''), '/summary/overview?scope=personal', '/summary/overview?scope=business',
      '/monthly-plan', '/subscriptions', '/transactions?limit=6' + q,
      '/summary/cashflow?months=12&scope=personal', '/summary/cashflow?months=12&scope=business',
      '/goals', `/summary/categories?days=${days}&kind=expense` + q, '/budgets', '/accounts',
      '/summary/networth?months=12' + q, selectedScope === 'business' ? '/business/summary' : null,
    ];
  }
  let warmTimer;
  function warmHomeScopes(selectedScope) {
    clearTimeout(warmTimer);
    warmTimer = setTimeout(() => {
      if (state.page !== 'overview' || scope !== selectedScope || document.hidden) return;
      const paths = new Set(SCOPES.filter(s => s !== selectedScope).flatMap(homePaths).filter(Boolean));
      // Best-effort preload; errors are retried on demand, never cached.
      for (const path of paths) LedgerHomeCache.read(path).catch(() => {});
    }, 200);
  }
  async function homePage() {
    const selectedScope = scope;
    const [ov, ovP, ovB, plan, subs, recent, cfP, cfB, goals, cats, budgets, accounts, nw, biz] = await Promise.all(
      homePaths(selectedScope).map(path => path ? LedgerHomeCache.read(path) : null)
    );
    // A later tap owns the render; don't overwrite its chart/detail state.
    if (scope !== selectedScope) return '';
    warmHomeScopes(selectedScope);
    updateBadge(subs);
    comfort.subscriptions = [...subs.items, ...subs.candidates, ...(subs.canceled || [])];
    home.data = { ov, plan, cfP, cfB, goals, cats, budgets, accounts, nw };
    home.cat = Math.min(home.cat, Math.max(0, cats.length - 1));
    const c = comfort.config, month = new Date().toLocaleDateString('en-US', { month: 'long' });
    const accts = accounts.filter(a => inScope(a.scope));
    const assets = accts.reduce((s, a) => s + Math.max(0, a.balance), 0), debt = accts.reduce((s, a) => s - Math.min(0, a.balance), 0);
    const cashOnHand = accts.filter(a => ['depository', 'checking', 'savings', 'cash'].includes(a.type)).reduce((s, a) => s + a.balance, 0);
    const figure = cash(ov.net_worth), whole = figure.slice(0, -3), cents = figure.slice(-3);
    const greeting = `Good ${new Date().getHours() < 12 ? 'morning' : new Date().getHours() < 18 ? 'afternoon' : 'evening'}${c.owner_name ? ', ' + esc(c.owner_name) : ''}`;
    const reviewCount = subs.candidates.length + (subs.price_reviews || []).length;

    let insights;
    if (scope === 'everything') {
      const p = ovP.spend_this_month, b = ovB.spend_this_month, t = p + b || 1;
      const reviews = [...subs.candidates.slice(0, 2).map(s => `<div class="rd-rev"><div><b>${esc(s.merchant)} looks recurring</b><small>${cash(s.amount)} · ${esc(s.cadence)} · ${esc(LABEL[s.scope] || s.scope)}</small></div><div class="rd-row-btns"><button type="button" class="btn btn-sm" data-action="dismiss-sub" data-id="${esc(s.id)}">Not recurring</button><button type="button" class="btn btn-sm btn-primary" data-action="confirm-sub" data-id="${esc(s.id)}">Track it</button></div></div>`),
        ...(subs.price_reviews || []).slice(0, 2).map(s => `<div class="rd-rev"><div><b>${esc(s.merchant)} changed price</b><small>Planned ${cash(s.amount)} · latest ${cash(s.observed_amount)}</small></div><div class="rd-row-btns"><button type="button" class="btn btn-sm" data-action="keep-price" data-id="${esc(s.id)}">Keep ${cash(s.amount)}</button><button type="button" class="btn btn-sm btn-primary" data-action="accept-price" data-id="${esc(s.id)}">Use ${cash(s.observed_amount)}</button></div></div>`)].slice(0, 2);
      insights = `
        <section class="card rd-card" data-home-tile="spending-split">${head('Where this month’s spending went', 'Posted purchases · transfers excluded')}
          <div class="rd-split" role="group" aria-label="Spending split"><button type="button" data-rd-scope="personal" data-s="personal" style="width:${(p / t * 100).toFixed(2)}%" aria-label="Personal ${cash(p)}. Show personal"></button><button type="button" data-rd-scope="business" data-s="business" style="width:${(b / t * 100).toFixed(2)}%" aria-label="Business ${cash(b)}. Show business"></button></div>
          <div class="rd-srow" data-s="personal"><i></i><span>Personal</span><b>${cash(p)}</b><small>${pct(p / t * 100)}</small><button type="button" class="link-button" data-rd-scope="personal">View</button></div>
          <div class="rd-srow" data-s="business"><i></i><span>Business</span><b>${cash(b)}</b><small>${pct(b / t * 100)}</small><button type="button" class="link-button" data-rd-scope="business">View</button></div></section>
        <section class="card rd-card" data-home-tile="cashflow">${head('Money in, money out', 'This month, both sides together')}
          <div class="rd-kv"><div><small>Income</small><b class="rd-pos">${cash(ov.income_this_month)}</b></div><div><small>Spending</small><b>${cash(ov.spend_this_month)}</b></div><div><small>Saved</small><b>${cash(ov.net_this_month)}</b></div><div><small>Savings rate</small><b>${ov.savings_rate == null ? '—' : (ov.savings_rate * 100).toFixed(1) + '%'}</b></div></div></section>
        <section class="card rd-card" data-home-tile="review">${head('Needs a look', reviewCount ? reviewCount + ' to review' : 'All caught up', reviewCount > 2 ? '<button type="button" class="link-button" data-rd-page="subscriptions">All →</button>' : '')}
          ${reviews.join('') || '<p class="rd-note">Your recurring payments match your plan.</p>'}</section>`;
    } else if (scope === 'personal') {
      const rentFree = LedgerSarahBudget.totals(cats), d = ov.net_this_month - ov.prev_net;
      insights = `
        <section class="card rd-card" data-home-tile="without-rent">${head(esc(month) + ' without rent', 'Posted spending outside Rent / Mortgage')}
          <button type="button" class="rd-big rd-plain" data-rd-rentfree>${cash(rentFree.spent)}</button>
          <div class="rd-track"><i style="width:${rentFree.share.toFixed(1)}%"></i></div>
          <div class="rd-line"><span>Rent excluded</span><b>${cash(rentFree.rent)}</b></div><div class="rd-line"><span>Other categories</span><b>${rentFree.categories.length}</b></div></section>
        <section class="card rd-card" data-home-tile="runway">${head('Runway', 'How long personal balances cover this month’s pace')}
          <div class="rd-big">${ov.runway_months == null ? '—' : ov.runway_months}<span class="rd-unit">months</span></div>
          <div class="rd-line"><span>Personal balances</span><b>${cash(ov.net_worth)}</b></div><div class="rd-line"><span>Spent this month</span><b>${cash(ov.spend_this_month)}</b></div></section>
        <section class="card rd-card" data-home-tile="saved">${head('Saved this month', 'Personal income less personal spending')}
          <div class="rd-big">${cash(ov.net_this_month)}</div>
          <span class="rd-delta">${d >= 0 ? icon.up : icon.down}${cash(Math.abs(d))} vs last month</span>
          <div class="rd-line"><span>Savings rate</span><b>${ov.savings_rate == null ? '—' : (ov.savings_rate * 100).toFixed(1) + '%'}</b></div></section>`;
    } else {
      const rate = Number(c.tax_rate_business) || 0, profit = ov.net_this_month;
      const ded = (biz.expense_categories_12mo || []).filter(x => x.td);
      insights = `
        <section class="card rd-card" data-home-tile="taxes">${head('Set aside for taxes', `At your ${(rate * 100).toFixed(1).replace(/\.0$/, '')}% rate on this month’s profit`)}
          <div class="rd-big">${cash(Math.max(0, profit) * rate)}</div>
          <div class="rd-line"><span>Profit this month</span><b>${cash(profit)}</b></div><div class="rd-line"><span>Last 12 months</span><b>${cash(biz.estimated_tax_setaside)}</b></div></section>
        <section class="card rd-card" data-home-tile="deductible">${head('Deductible spend', '12 months')}
          <div class="rd-big rd-big-s">${cash(biz.deductible_12mo)}</div>
          ${ded.slice(0, 4).map(x => `<div class="rd-line"><span>${esc(x.name)}</span><b>${cash(x.amt)}</b></div>`).join('') || '<p class="rd-note">No deductible spending yet.</p>'}</section>
        <section class="card rd-card" data-home-tile="clients">${head('Clients', '12 months')}
          ${(biz.top_clients || []).slice(0, 3).map(x => `<div class="rd-client"><span class="rd-av" data-s="business">${esc(initials(x.name))}</span><span><b>${esc(x.name)}</b><small>${x.n} payments</small></span><b class="rd-pos">${cash(x.amt)}</b></div>`).join('') || '<p class="rd-note">No business income recorded yet.</p>'}
          <div class="rd-line rd-line-top"><span>Profit, 12 months</span><b>${cash(biz.profit_ttm)}</b></div></section>`;
    }

    const target = Number(c.monthly_spending_target || 0);
    const scoped = budgets.filter(b => inScope(b.scope));
    let ring;
    if (scope === 'everything') {
      const p = target ? Math.round(plan.total_expected / target * 100) : null;
      ring = { title: `${month} plan`, pct: p, cap: 'of plan', rows: [['Spent', cash(plan.spent)], ['Pending & expected', cash((plan.pending_spend || 0) + plan.upcoming)], [target ? 'Room left' : 'Monthly plan', target ? cash(target - plan.total_expected) : '<button type="button" class="link-button" data-action="spending-plan">Set a plan</button>']] };
    } else {
      const lim = scoped.reduce((s, b) => s + b.month_limit, 0), sp = scoped.reduce((s, b) => s + b.spent, 0);
      ring = { title: `${LABEL[scope]} budgets`, pct: lim ? Math.round(sp / lim * 100) : null, cap: 'of budgets', rows: [['Spent in budgets', cash(sp)], ['Budgeted', cash(lim)], ['Remaining', lim ? cash(lim - sp) : '<button type="button" class="link-button" data-rd-page="budgets">Add budgets</button>']] };
    }
    const watch = scoped.slice().sort((a, b) => b.pct - a.pct).slice(0, 3);
    const upcoming = (subs.items || []).filter(s => s.next_due && inScope(s.scope)).sort((a, b) => a.next_due.localeCompare(b.next_due)).slice(0, 6);
    const goalRows = goals.filter(g => inScope(g.scope)).slice(0, 3);
    const top = cats.slice(0, 7), max = top[0]?.amt || 1;

    return `<div class="rd rd-home" data-home-scope="${scope}">
      <div class="rd-welcome"><div><h2>${greeting}</h2><p>${new Date().toLocaleDateString('en-US', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })} · ${accounts.length} accounts</p></div>${action('add-tx', 'Add transaction', '', 'btn btn-primary')}</div>
      <section class="card rd-card rd-hero" data-home-tile="net-worth">
        <div class="rd-hero-main">
          <div class="rd-eyebrow">${{ everything: 'Total net worth', personal: 'Personal net worth', business: 'Business net position' }[scope]}</div>
          <div class="rd-figure">${whole}<span>${cents}</span></div>
          <span class="rd-delta">${ov.net_this_month >= 0 ? icon.up : icon.down}${signed(ov.net_this_month)} ${scope === 'business' ? 'profit' : 'net income'} this month</span>
          <button type="button" class="rd-plain rd-spark-btn" data-rd-history aria-label="Inspect estimated net worth history">${spark(nw)}</button>
          <div class="rd-meta"><div><small>Assets</small><b>${cash(assets)}</b></div><div><small>Liabilities</small><b>${cash(debt)}</b></div><div><small>Cash on hand</small><b>${cash(cashOnHand)}</b></div></div>
        </div>
        <div class="rd-accts">${head(scope === 'everything' ? 'All accounts' : LABEL[scope] + ' accounts', accts.length + ' tracked', '<button type="button" class="link-button" data-rd-page="accounts">View all</button>')}
          ${accts.slice(0, 6).map(a => `<button type="button" class="rd-acct" data-rd-account="${esc(a.id)}" data-s="${esc(a.scope)}"><i></i><span><b>${esc(a.name)}</b><small>${esc(a.type)} · ${esc(LABEL[a.scope] || a.scope)}${a.mask ? ' · ' + esc(a.mask) : ''}</small></span><b class="${a.balance < 0 ? 'rd-neg' : ''}">${cash(a.balance)}</b></button>`).join('') || action('manual-account', 'Add an account', '', 'btn')}</div>
      </section>
      <div class="rd-grid rd-3">${insights}</div>
      <div class="rd-grid rd-5-7">
        <section class="card rd-card" data-home-tile="plan">${head(ring.title, `${new Date().getDate()} days in · ${daysLeft()} to go`, '<button type="button" class="link-button" data-action="spending-plan">Edit plan</button>')}
          <div class="rd-ring-row"><button type="button" class="rd-ring rd-plain" data-rd-ring aria-label="Inspect monthly plan"><svg viewBox="0 0 120 120"><circle class="rd-ring-bg" cx="60" cy="60" r="50"/><circle class="rd-ring-fg" cx="60" cy="60" r="50" style="stroke-dashoffset:${(314.159 * (1 - Math.min(ring.pct || 0, 100) / 100)).toFixed(2)}"/></svg><span><b>${ring.pct == null ? '—' : ring.pct + '%'}</b><small>${ring.cap}</small></span></button>
            <div class="rd-ring-stats">${ring.rows.map(([k, v]) => `<div class="rd-line"><span>${k}</span><b>${v}</b></div>`).join('')}</div></div>
          <div class="rd-watch">${watch.map(b => `<button type="button" class="rd-plain rd-watch-row" data-rd-budget="${esc(b.category_id)}" data-scope-of="${esc(b.scope)}"><span class="rd-line"><span>${esc(b.cat_icon || '')} ${esc(b.cat_name)} ${scope === 'everything' ? chip(b.scope) : ''}</span><b class="${b.pct >= 100 ? 'rd-neg' : b.pct >= 80 ? 'rd-warn' : ''}">${Math.round(b.pct)}%</b></span><span class="rd-track"><i class="${b.pct >= 100 ? 'over' : b.pct >= 80 ? 'warn' : ''}" style="width:${Math.min(100, b.pct)}%"></i></span></button>`).join('')}</div>
        </section>
        <section class="card rd-card" data-home-tile="monthly-chart">${head('Monthly ' + (home.metric === 'spend' ? 'spending' : 'income'), 'Select a month to inspect', `<div class="rd-segs"><div class="rd-seg-group" role="group" aria-label="Measure">${[['spend', 'Spending'], ['income', 'Income']].map(([k, l]) => `<button type="button" data-rd-metric="${k}" aria-pressed="${home.metric === k}">${l}</button>`).join('')}</div><div class="rd-seg-group" role="group" aria-label="Chart range">${[12, 6, 3].map(n => `<button type="button" data-rd-range="${n}" aria-pressed="${home.range === n}">${n}M</button>`).join('')}</div></div>`)}
          <div id="rd-bars">${barsMarkup()}</div></section>
      </div>
      <div class="rd-grid rd-7-5">
        <section class="card rd-card" data-home-tile="categories">${head('Spend constellation', `${scope === 'everything' ? 'All' : LABEL[scope]} categories this month · tap to inspect`, cats.length > 7 ? `<button type="button" class="link-button" data-rd-page="budgets">All ${cats.length} →</button>` : '')}
          <div class="rd-cloud">${top.map((cat, i) => `<button type="button" class="rd-bub" data-rd-cat="${i}" aria-pressed="${i === home.cat}" style="--size:${Math.round(84 + Math.sqrt(cat.amt / max) * 84)}px;--delay:${(-i * 1.7).toFixed(1)}s;--dur:${(6 + (i % 3) * 1.4).toFixed(1)}s" aria-label="${esc(cat.name)} ${cash(cat.amt)}"><b>${esc(cat.name)}</b><small>${cash(cat.amt)}</small></button>`).join('') || '<p class="rd-note">Your spending will appear here.</p>'}</div></section>
        <section class="card rd-card" data-home-tile="category-detail" id="rd-cat-detail">${catDetail()}</section>
      </div>
      <div class="rd-grid rd-2">
        <section class="card rd-card" data-home-tile="recent">${head('Recent activity', 'Tap the scope to move a purchase', '<button type="button" class="link-button" data-rd-page="transactions">View all</button>')}
          ${recent.rows.map(t => { const name = receiptDisplayName(t), to = t.scope === 'personal' ? 'business' : 'personal'; return `<div class="rd-tx" data-s="${esc(t.scope)}"><button type="button" class="rd-plain rd-tx-main" data-rd-tx="${esc(t.id)}"><span class="rd-av">${esc(initials(name))}</span><span><b>${esc(name)}</b><small>${esc(t.is_transfer ? 'Transfer' : (t.allocations?.length > 1 ? 'Split purchase' : t.cat_name || 'Uncategorized'))} · ${fmtDate(t.posted)}${t.pending ? ' · Pending' : ''}</small></span></button><b class="rd-amt ${t.amount > 0 && !t.is_transfer ? 'rd-pos' : ''}">${signed(t.amount)}</b><button type="button" class="rd-flip" data-rd-flip="${esc(t.id)}" data-from="${esc(t.scope)}" data-name="${esc(name)}" aria-label="Move ${esc(name)} to ${LABEL[to]}" title="Move to ${LABEL[to]}">${chip(t.scope)}${icon.swap}</button></div>`; }).join('') || '<p class="rd-note">No recent activity.</p>'}
        </section>
        <section class="card rd-card" data-home-tile="upcoming">${head('Coming up', upcoming.length ? cash(upcoming.reduce((s, x) => s + (x.amount || 0), 0)) + ' expected' : 'Tracked subscriptions', '<button type="button" class="link-button" data-rd-page="subscriptions">Subscriptions</button>')}
          ${upcoming.map(s => { const d = new Date(s.next_due + 'T12:00:00'); return `<button type="button" class="rd-plain rd-tx rd-up" data-action="edit-sub" data-id="${esc(s.id)}" data-s="${esc(s.scope)}"><span class="rd-day"><b>${d.getDate()}</b><small>${d.toLocaleDateString('en-US', { month: 'short' })}</small></span><span class="rd-tx-name"><b>${esc(s.merchant)}</b><small>${esc(s.cadence)}${s.status === 'cancel_requested' ? ' · cancellation in progress' : ''}</small></span><b class="rd-amt">${cash(s.amount)}</b>${chip(s.scope)}</button>`; }).join('') || '<p class="rd-note">No tracked payments coming up. Add subscriptions to see them here.</p>'}
        </section>
      </div>
      <section class="card rd-card" data-home-tile="goals">${head('Savings goals', '', '<button type="button" class="link-button" data-rd-page="goals">Manage goals</button>')}
        <div class="rd-goals">${goalRows.map(g => `<button type="button" class="rd-plain rd-goal" data-rd-goal="${esc(g.id)}" data-s="${esc(g.scope)}"><span class="rd-line"><b>${esc(g.name)}</b>${chip(g.scope)}</span><span class="rd-goal-fig"><b>${Math.round(g.pct)}%</b><small>${cash(g.saved)} of ${cash(g.target)}</small></span><span class="rd-track"><i style="width:${Math.min(100, g.pct)}%"></i></span><small>${g.monthly_plan ? cash(g.monthly_plan) + ' a month · ' : ''}${g.target_date ? 'by ' + fmtDate(g.target_date) : ''}</small></button>`).join('')}${goalRows.length < 3 ? `<button type="button" class="rd-plain rd-goal rd-goal-add" data-rd-page="goals">＋ Add a${scope === 'business' ? ' business' : ''} goal</button>` : ''}</div>
      </section>
    </div>`;
  }

  /* ---------------- Transactions ---------------- */
  const txLocal = { uncOnly: false, selected: new Set(), prompt: null, limit: 50 };
  const expenseCats = () => state.categories.filter(c => c.kind === 'expense');
  const incomeCats = () => state.categories.filter(c => c.kind === 'income');

  function glance(overview, { filterable = false, activeId = '', uncOn = false } = {}) {
    const s = overview.summary, total = s.total || 0;
    const named = overview.categories.filter(c => c.id !== null && c.total > 0);
    const unc = overview.categories.find(c => c.id === null);
    const segs = (unc && unc.total > 0 ? [{ k: 'u', id: '__unc__', total: unc.total }] : [])
      .concat(named.slice(0, 7).map((c, i) => ({ k: String(i + 1), id: c.id, total: c.total })));
    const rest = named.slice(7).reduce((a, c) => a + c.total, 0);
    if (rest > 0) segs.push({ k: '8', id: '__rest__', total: rest });
    const filtered = filterable && (activeId || uncOn);
    const kOf = i => String(Math.min(i + 1, 8));
    const legend = named.map((c, i) => filterable
      ? `<button type="button" class="rd-gchip" data-k="${kOf(i)}" data-rd-cat-filter="${esc(c.id)}" aria-pressed="${activeId === c.id}"><i></i>${esc(c.name)}<b>${cash(c.total)}</b></button>`
      : `<span class="rd-gl" data-k="${kOf(i)}"><i></i>${esc(c.name)}<b>${cash(c.total)}</b></span>`).join('');
    return `<div class="rd-glance">
      <div class="rd-gtop">
        <div class="rd-gtotal"><span class="rd-eyebrow">${esc(monthName(overview.month))} spending</span><b>${cash(total)}</b></div>
        <div class="rd-gstat"><small>Categorized</small><b>${cash(s.categorized)}</b><span>${total ? Math.round(s.categorized / total * 100) : 100}% · ${named.length} categories</span></div>
        ${filterable ? `<button type="button" class="rd-gstat rd-gunc" data-rd-unc data-zero="${!(s.uncategorized > 0)}" aria-pressed="${uncOn}">` : `<div class="rd-gstat rd-gunc" data-zero="${!(s.uncategorized > 0)}">`}<small>Uncategorized</small><b>${cash(s.uncategorized)}</b><span>${s.uncategorized > 0 ? s.uncategorized_count + ' to sort' + (filterable ? ' · show them' : '') : 'Everything is sorted'}</span>${filterable ? '</button>' : '</div>'}
        <span class="rd-note rd-gnote">${s.transaction_count} purchases · transfers excluded${filterable ? '<br>Tap a category to filter the list' : ''}</span>
      </div>
      <div class="rd-gbar" role="img" data-filtered="${!!filtered}" aria-label="Spending by category: ${esc((unc && unc.total > 0 ? 'Uncategorized ' + cash(unc.total) + ', ' : '') + named.map(c => c.name + ' ' + cash(c.total)).join(', '))}">${segs.map(x => `<span data-k="${x.k}" data-on="${!filtered || x.id === activeId || (uncOn && x.id === '__unc__')}" style="width:${(total ? x.total / total * 100 : 0).toFixed(2)}%"></span>`).join('')}</div>
      <div class="rd-glegend" ${filterable ? 'role="group" aria-label="Filter by category"' : ''}>${legend}</div>
    </div>`;
  }

  function catSelect(t) {
    const pool = t.amount > 0 ? incomeCats() : expenseCats();
    const current = state.categories.find(c => c.id === t.category_id);
    const options = (current && !pool.includes(current) ? [current] : []).concat(pool);
    return `<select class="rd-catsel" data-rd-cat-set="${esc(t.id)}" data-old="${esc(t.category_id || '')}" data-unc="${!t.category_id}" aria-label="Category for ${esc(receiptDisplayName(t))}"><option value="">Uncategorized</option>${options.map(c => `<option value="${esc(c.id)}" ${c.id === t.category_id ? 'selected' : ''}>${esc(c.icon || '')} ${esc(c.name)}</option>`).join('')}</select>`;
  }
  function scopeToggle(t) {
    return `<span class="rd-seg2" data-s="${esc(t.scope)}" role="group" aria-label="Whose money: ${esc(receiptDisplayName(t))}"><span class="rd-knob" aria-hidden="true"></span>${['personal', 'business'].map(s => `<button type="button" data-rd-scope-set="${s}" data-id="${esc(t.id)}" data-from="${esc(t.scope)}" data-name="${esc(receiptDisplayName(t))}" aria-pressed="${t.scope === s}">${LABEL[s]}</button>`).join('')}</span>`;
  }

  async function txPage() {
    const f = state.txFilters;
    f.scope = '';
    const month = (f.since || '').slice(0, 7) || monthKey();
    const params = new URLSearchParams(Object.entries({ search: f.search, account_id: f.account_id, category_id: f.category_id, since: f.since, until: f.until }).filter(([, v]) => v));
    if (scope !== 'everything') params.set('scope', scope);
    let data;
    const [receipts, activeAccounts, archivedAccounts, ov] = await Promise.all([api('/receipts'), api('/accounts'), api('/accounts?archived=1'), api(`/budgets/overview?month=${month}` + scopeQuery('&'))]);
    if (txLocal.uncOnly) {
      const ids = new Set(ov.uncategorized_transactions.map(t => t.id));
      const start = month + '-01', end = new Date(+month.slice(0, 4), +month.slice(5), 0).toISOString().slice(0, 10);
      const monthRows = await api(`/transactions?since=${start}&until=${end}&limit=1000` + scopeQuery('&'));
      const rows = monthRows.rows.filter(t => ids.has(t.id));
      data = { rows, total: rows.length, limit: rows.length || 1, offset: 0 };
    } else {
      params.set('limit', txLocal.limit);
      params.set('offset', f.offset || 0);
      data = await api('/transactions?' + params.toString());
    }
    receiptState.summary = receipts;
    const accounts = [...activeAccounts, ...archivedAccounts];
    const activeFilters = [f.account_id, f.category_id, f.since, f.until].filter(Boolean).length;
    const prompt = txLocal.prompt;
    txLocal.selected = new Set([...txLocal.selected].filter(id => data.rows.some(t => t.id === id)));
    return `<div class="rd rd-tx-page">
      <div class="page-intro transaction-intro"><div><h2>Transactions</h2><p>Bank activity and cash entries you add yourself.</p></div>${action('add-cash-tx', '＋ Add cash transaction', '', 'btn btn-primary')}</div>
      <section class="card rd-card">${glance(ov, { filterable: true, activeId: f.category_id, uncOn: txLocal.uncOnly })}</section>
      <div class="filter-row transaction-filters ${state.txFiltersExpanded ? 'tx-filters-expanded' : ''}" role="search" aria-label="Transaction filters">
        <input class="input" id="tx-search" aria-label="Search transactions" placeholder="Search merchant, note…" value="${esc(f.search)}" data-rd-search>
        <button class="btn tx-filter-toggle" aria-expanded="${!!state.txFiltersExpanded}" aria-controls="tx-advanced-filters" onclick="toggleTransactionFilters(this)">Filters${activeFilters ? ' · ' + activeFilters : ''}</button>
        <div class="tx-advanced-filters" id="tx-advanced-filters">
          <select class="input" aria-label="Transaction account" data-rd-filter="account_id"><option value="">All accounts, including archived</option><option value="__cash__" ${f.account_id === '__cash__' ? 'selected' : ''}>Cash / manual</option>${accounts.map(a => `<option value="${esc(a.id)}" ${f.account_id === a.id ? 'selected' : ''}>${esc(a.name)}${a.mask ? ' ••' + esc(a.mask) : ''}${a.archived ? ' · Archived' : ''}</option>`).join('')}</select>
          <select class="input" aria-label="Transaction category" data-rd-filter="category_id"><option value="">All categories</option>${state.categories.map(c => `<option value="${esc(c.id)}" ${f.category_id === c.id ? 'selected' : ''}>${esc(c.icon)} ${esc(c.name)}</option>`).join('')}</select>
          <label class="transaction-date">From<input type="date" class="input" value="${esc(f.since)}" data-rd-filter="since"></label>
          <label class="transaction-date">To<input type="date" class="input" value="${esc(f.until)}" data-rd-filter="until"></label>
          <button class="btn btn-sm btn-ghost" type="button" data-rd-clear>Clear</button>
        </div>
        <span class="small muted tx-result-count">${data.total} transaction${data.total === 1 ? '' : 's'}${txLocal.uncOnly ? ' · uncategorized' : ''}</span>
        ${state.lastCategoryBatch ? '<button class="btn btn-sm" onclick="undoCategoryBatch(this)">Undo last category batch</button>' : ''}
      </div>
      <div id="rd-actionbar">${prompt ? promptMarkup(prompt) : ''}</div>
      ${receiptSummaryMarkup(receipts)}
      <div class="card tx-list-card rd-tx-card">
        <div class="table-wrap"><table class="tbl tx-table rd-table" aria-label="Transactions">
          <thead><tr><th class="tx-select"><input type="checkbox" data-rd-select-all aria-label="Select all on this page"></th><th>Date</th><th>Name</th><th>Account</th><th>Category</th><th>Whose money</th><th class="num">Amount</th><th></th></tr></thead><tbody>
          ${data.rows.map(t => `<tr class="tx-row" data-id="${esc(t.id)}" data-checked="${txLocal.selected.has(t.id)}">
            <td class="tx-select"><input type="checkbox" data-rd-select="${esc(t.id)}" ${txLocal.selected.has(t.id) ? 'checked' : ''} aria-label="Select ${esc(receiptDisplayName(t))}"></td>
            <td style="white-space:nowrap" class="muted tx-date">${shortDate(t.posted)}</td>
            <td class="tx-name"><b>${esc(receiptDisplayName(t))}</b>${receiptOriginalName(t)}${t.note ? `<div class="small muted tx-note-desktop">${esc(t.note)}</div><details class="tx-note-mobile"><summary>Note</summary><p>${esc(t.note)}</p></details>` : ''}${t.pending ? '<span class="tag tag-rec">Pending</span>' : ''}${t.is_transfer ? '<span class="tag tag-rec">Transfer</span>' : ''}${t.recurring ? '<span class="tag tag-rec" title="Recurring">↻</span>' : ''}</td>
            <td class="muted small tx-account">${esc(t.account_id ? (t.acct_name || '—') : 'Cash / manual')}${t.acct_mask ? ` ••${esc(t.acct_mask)}` : ''}</td>
            <td class="tx-category">${t.is_transfer ? '<span class="muted small">Transfer</span>' : Array.isArray(t.allocations) && t.allocations.length ? receiptCategoryCell(t) : catSelect(t)}</td>
            <td class="tx-scope">${scopeToggle(t)}</td>
            <td class="num tx-amount ${t.amount > 0 ? 'amt-pos' : 'amt-neg'}">${t.amount > 0 ? '+' : ''}${fmtMoney(t.amount, { decimals: 2 })}</td>
            <td class="tx-actions"><button class="btn btn-sm btn-ghost tx-edit" aria-label="${esc('Edit ' + receiptDisplayName(t))}" title="Edit" onclick="openTxEdit(${esc(JSON.stringify(t.id))})"><span class="tx-edit-icon">✏️</span><span class="tx-edit-label">Edit</span></button>${t.receipt_provider && t.receipt_status !== 'dismissed' ? receiptEditAction(t.id, t.receipt_status) : ''}</td>
          </tr>`).join('') || `<tr class="tx-empty"><td colspan="8" class="muted" style="text-align:center;padding:30px">${txLocal.uncOnly ? 'Nothing uncategorized this month.' : 'No transactions match. Add a cash transaction or link an account.'}</td></tr>`}
          </tbody></table></div>
        ${txLocal.uncOnly ? '' : `<div class="row-between mt tx-pagination"><button class="btn btn-sm" type="button" data-rd-page-step="-1" ${data.offset > 0 ? '' : 'disabled'}>← Newer</button><span class="small muted">showing ${data.rows.length ? data.offset + 1 : 0}–${data.offset + data.rows.length} of ${data.total}</span><button class="btn btn-sm" type="button" data-rd-page-step="1" ${data.offset + data.limit < data.total ? '' : 'disabled'}>Older →</button></div>`}
      </div>
    </div>`;
  }

  function promptMarkup(p) {
    if (p.kind === 'bulk') return `<div class="rd-bulk" role="region" aria-label="Selected transactions"><b>${p.count} selected</b><span class="rd-grow"></span><button type="button" class="btn btn-sm rd-to" data-s="personal" data-rd-bulk="personal">Move to Personal</button><button type="button" class="btn btn-sm rd-to" data-s="business" data-rd-bulk="business">Move to Business</button><button type="button" class="link-button" data-rd-bulk-clear>Clear</button></div>`;
    return `<div class="rd-prompt" data-s="${esc(p.to)}" role="region" aria-label="Move matching purchases"><span class="rd-grow"><b>Move the other ${p.ids.length === 1 ? '' : p.ids.length + ' '}${esc(p.name)} purchase${p.ids.length === 1 ? '' : 's'} too?</b> <span class="muted">They’re still marked ${esc(LABEL[p.from])}.</span></span><button type="button" class="btn btn-sm" data-rd-prompt="skip">Just this one</button><button type="button" class="btn btn-sm btn-primary" data-rd-prompt="apply">Move ${p.ids.length} more</button></div>`;
  }
  function renderActionbar() {
    const holder = document.getElementById('rd-actionbar');
    if (!holder) return;
    const p = txLocal.selected.size ? { kind: 'bulk', count: txLocal.selected.size } : txLocal.prompt;
    holder.innerHTML = p ? promptMarkup(p) : '';
  }

  async function moveScope(id, to, from, name) {
    if (to === from) return;
    await updateTx({ id, scope: to });
    const key = String(name || '').trim().toLowerCase();
    let others = [];
    try {
      const matches = await api(`/transactions?search=${encodeURIComponent(name)}&scope=${from}&limit=200`);
      others = matches.rows.filter(t => t.id !== id && receiptDisplayName(t).trim().toLowerCase() === key).map(t => t.id);
    } catch {}
    txLocal.prompt = others.length ? { kind: 'match', ids: others, origin: id, name, from, to } : null;
    netsAt = 0;
    undoable(`Moved ${name} to ${LABEL[to]}`, async () => { txLocal.prompt = null; await updateTx({ id, scope: from }); });
    await refresh();
    syncChrome();
  }

  /* ---------------- Budgets ---------------- */
  const budLocal = { editing: null };
  async function budgetsPage() {
    const month = budgetView.month;
    const [all, ov] = await Promise.all([api('/budgets?month=' + month), api(`/budgets/overview?month=${month}` + scopeQuery('&'))]);
    const budgets = all.filter(b => inScope(b.scope));
    const s = ov.summary, total = s.total || 0;
    const byCat = new Map();
    ov.categories.filter(c => c.id !== null).forEach((c, i) => byCat.set(c.id, { ...c, k: String(Math.min(i + 1, 8)), budgets: [] }));
    budgets.forEach(b => {
      if (!byCat.has(b.category_id)) byCat.set(b.category_id, { id: b.category_id, name: b.cat_name || 'Category', icon: b.cat_icon, total: 0, pending: 0, k: '8', budgets: [] });
      byCat.get(b.category_id).budgets.push(b);
    });
    const rows = [...byCat.values()].sort((a, b) => b.total - a.total);
    const statusOf = p => p >= 100 ? 'over' : p >= 80 ? 'warn' : 'ok';
    const health = { ok: 0, warn: 0, over: 0 };
    budgets.forEach(b => health[statusOf(b.pct)]++);
    const unc = ov.categories.find(c => c.id === null);
    const unbudgeted = rows.filter(r => !r.budgets.length && r.total > 0);
    const current = month === monthKey();
    const history = ov.months.map(m => ({ ...m }));
    const hmax = Math.max(1, ...history.map(m => m.total));
    const rowMarkup = r => {
      const limit = r.budgets.reduce((a, b) => a + b.month_limit, 0), spent = r.budgets.reduce((a, b) => a + b.spent, 0);
      const p = limit ? spent / limit * 100 : 0, st = limit ? statusOf(p) : 'none';
      const scopes = [...new Set(r.budgets.map(b => b.scope))];
      return `<div class="rd-crow" role="row" data-k="${r.k}">
        <span role="cell" class="rd-cname"><i></i><span>${r.id ? `<button type="button" class="rd-plain rd-cat-link" data-rd-budget="${esc(r.id)}" data-scope-of="${esc(scope === 'everything' ? '' : scope)}" title="View ${esc(r.name)} transactions"><b>${esc(r.icon || '')} ${esc(r.name)}</b></button>` : `<b>${esc(r.icon || '')} ${esc(r.name)}</b>`}${scope === 'everything' && scopes.length ? `<small>${scopes.map(x => x === 'all' ? 'Both' : LABEL[x]).join(' · ')} budget</small>` : ''}</span></span>
        <span role="cell" class="rd-prog"><span class="rd-track" data-state="${st}"><i style="width:${limit ? Math.min(100, p) : (total ? r.total / total * 100 : 0)}%"></i></span><small>${limit ? `${Math.round(p)}% used · ${cash(Math.max(0, limit - spent))} left${r.pending ? ` · ${cash(r.pending)} pending` : ''}` : `${total ? Math.round(r.total / total * 100) : 0}% of spending`}</small></span>
        <span role="cell" class="rd-num">${cash(limit ? spent : r.total)}</span>
        <span role="cell" class="rd-num rd-muted">${limit ? cash(limit) : '—'}</span>
        <span role="cell" class="rd-status" data-state="${st}">${st === 'over' ? 'Over by ' + cash(spent - limit) : st === 'warn' ? 'Near limit' : st === 'ok' ? 'On track' : 'No budget'}</span>
        <span role="cell" class="rd-row-btns">${r.budgets.map(b => `<button type="button" class="btn btn-sm btn-ghost" aria-label="Delete ${esc(r.name)} ${esc(b.scope)} budget" onclick="deleteBudget(${esc(JSON.stringify(b.id))})">✕</button>`).join('')}</span>
      </div>`;
    };
    return `<div class="rd rd-budgets">
      <div class="page-intro"><div><h2>Budgets</h2><p>${esc(monthName(month))} · every category, budgeted or not</p></div>
        <div class="rd-intro-actions"><label class="rd-month">Month<input aria-label="Budget month" class="input" type="month" min="1900-01" max="${esc(ov.as_of.slice(0, 7))}" value="${esc(month)}" onchange="if(this.value)setBudgetView('month',this.value)"></label><button class="btn btn-primary" type="button" onclick="openBudgetForm()">＋ New budget</button></div></div>
      <div class="rd-grid rd-5-7">
        <section class="card rd-card">
          <div class="rd-eyebrow">${esc(monthName(month))} · ${scope === 'everything' ? 'All spending' : LABEL[scope]}</div>
          <div class="rd-head" style="margin:8px 0 0"><h3>Total spending</h3><span class="rd-note">${s.transaction_count} purchases</span></div>
          <div class="rd-figure rd-figure-m">${cash(total)}</div>
          <div class="rd-parts"><div><small>Posted</small><b>${cash(s.posted)}</b></div><div><small>Pending</small><b>${cash(s.pending)}</b></div><div><small>Categorized</small><b>${cash(s.categorized)}</b></div><div class="rd-gunc" data-zero="${!(s.uncategorized > 0)}"><small>Uncategorized</small><b>${cash(s.uncategorized)}</b></div></div>
          <p class="rd-note">Total includes pending charges. Transfers and card repayments stay out. Categorized + uncategorized = total spending.${s.refunds ? ` Refunds and credits: ${cash(s.refunds)}, shown separately.` : ''}</p>
        </section>
        <section class="card rd-card">${head('Spending at a glance', '', s.uncategorized > 0 ? `<button type="button" class="btn btn-sm rd-sort" data-rd-sort="${esc(month)}">Sort ${s.uncategorized_count} uncategorized</button>` : `<span class="rd-status" data-state="ok">${icon.check}Everything is categorized</span>`)}${glance(ov)}</section>
      </div>
      <div class="rd-grid rd-8-4">
        <section class="card rd-card rd-list" role="table" aria-label="Every spending category">
          ${head('Every spending category', 'Includes categories without a budget. Envelope progress uses posted purchases.', `<span class="rd-note">${rows.length} categories</span>`)}
          <div class="rd-thead" role="row"><span role="columnheader">Category</span><span role="columnheader">Progress</span><span role="columnheader" class="rd-num">Spent</span><span role="columnheader" class="rd-num">Budget</span><span role="columnheader" class="rd-status">Status</span><span></span></div>
          ${unc && unc.total > 0 ? `<div class="rd-crow rd-crow-unc" role="row"><span role="cell" class="rd-cname"><i class="rd-hatch"></i><span><b>Uncategorized</b><small>${s.uncategorized_count} to sort</small></span></span><span role="cell" class="rd-prog"><span class="rd-track" data-state="unc"><i style="width:${(unc.total / total * 100).toFixed(1)}%"></i></span><small>${Math.round(unc.total / total * 100)}% of spending</small></span><span role="cell" class="rd-num">${cash(unc.total)}</span><span role="cell" class="rd-num rd-muted">—</span><span role="cell" class="rd-status" data-state="unc">Needs sorting</span><span role="cell" class="rd-row-btns"><button type="button" class="btn btn-sm" data-rd-sort="${esc(month)}">Sort</button></span></div>` : ''}
          ${rows.map(rowMarkup).join('') || '<p class="rd-note" style="padding:0 20px 20px">No spending or budgets for this month yet.</p>'}
        </section>
        <div class="rd-side">
          <section class="card rd-card">${head('Budget health', `${budgets.length} budget${budgets.length === 1 ? '' : 's'}${current ? ` · ${daysLeft()} days left this month` : ''}`)}
            <div class="rd-health"><div><b class="rd-pos">${health.ok}</b><small>On track</small></div><div><b class="rd-warn">${health.warn}</b><small>Near limit</small></div><div><b class="rd-neg">${health.over}</b><small>Over</small></div></div></section>
          <section class="card rd-card">${head('Spending without a budget', unbudgeted.length ? `${cash(unbudgeted.reduce((a, r) => a + r.total, 0))} across ${unbudgeted.length} categor${unbudgeted.length === 1 ? 'y' : 'ies'}` : 'Every category with spending has a budget.')}
            ${unbudgeted.map(r => `<div class="rd-ub" data-k="${r.k}"><i></i><span class="rd-grow"><b>${esc(r.name)}</b><small>${cash(r.total)} this month</small></span>${budLocal.editing === r.id ? `<label class="rd-inline"><span class="rd-sr">Monthly budget for ${esc(r.name)}</span><input class="input" inputmode="decimal" placeholder="$ / month" data-rd-budget-input="${esc(r.id)}"></label><button type="button" class="btn btn-sm btn-primary" data-rd-budget-save="${esc(r.id)}">Save</button>` : `<button type="button" class="btn btn-sm" data-rd-budget-edit="${esc(r.id)}">Set budget</button>`}</div>`).join('')}
          </section>
        </div>
      </div>
      ${ov.uncategorized_transactions.length ? `<section class="card rd-card">${head('Uncategorized purchases', `${ov.uncategorized_transactions.length} this month · for split receipts only the uncategorized part is listed`)}
        ${ov.uncategorized_transactions.slice(0, 8).map(t => `<div class="rd-tx"><span class="rd-tx-name"><b>${esc(t.name)}</b><small>${fmtDate(t.posted)} · ${esc(t.account_name || 'Manual')}${t.pending ? ' · Pending' : ''}${t.partially_categorized ? ' · Split receipt' : ''}</small></span>${chip(t.scope)}<b class="rd-amt">${cash(t.uncategorized_amount)}</b><button class="btn btn-sm" type="button" onclick="reviewBudgetPurchase(${esc(JSON.stringify(t.name))},${esc(JSON.stringify(t.posted))})">Review</button></div>`).join('')}</section>` : ''}
      <section class="card rd-card">${head(`Monthly spending · ${esc(month.slice(0, 4))}`, 'Select a month')}
        <div class="rd-hist">${history.map(m => `<button type="button" class="rd-hcol" data-cur="${m.month === month}" ${m.future ? 'disabled' : ''} onclick="setBudgetView('month','${m.month}')" aria-label="${esc(monthName(m.month))} ${m.future ? 'not started' : cash(m.total)}"><b>${m.future ? '—' : fmtMoney(m.total, { compact: true })}</b><span class="rd-htrack"><span style="height:${(m.total / hmax * 100).toFixed(1)}%"></span></span><span>${shortMonth(m.month)}</span></button>`).join('')}</div>
      </section>
    </div>`;
  }

  /* ---------------- Settings: layout choice ---------------- */
  function layoutCard() {
    const saved = (comfort.config.layout || 'new') === 'classic' ? 'classic' : 'new';
    const local = localLayout();
    return `<section class="card rd-card rd-layout-card"><h3>Layout</h3>
      <p class="rd-note">The new layout adds the Everything / Personal / Business switch and redesigned Home, Transactions and Budgets. Classic is the previous layout. Your records are the same in both.</p>
      <div class="rd-seg-group rd-seg-lg" role="group" aria-label="Layout"><button type="button" data-rd-layout="new" aria-pressed="${saved === 'new'}">New layout</button><button type="button" data-rd-layout="classic" aria-pressed="${saved === 'classic'}">Classic layout</button></div>
      <p class="rd-note">Saved on your Ledger, so every device and home-screen app follows it after a reload.</p>
      ${local ? `<p class="rd-note"><b>This browser is set to ${local === 'classic' ? 'Classic' : 'New'}</b> by a link option. <button type="button" class="link-button" data-rd-layout-local-clear>Use the saved setting</button></p>` : ''}
    </section>`;
  }

  // Saved on the server for every device; an older server that cannot store it keeps the choice on this device.
  async function chooseLayout(choice) {
    const saved = await savePreference({ layout: choice });
    if (saved && saved.layout === choice) {
      write('ledger-layout-local', null);
      toast(choice === 'classic' ? 'Classic layout restored on every device.' : 'New layout turned on for every device.', 'ok');
    } else {
      write('ledger-layout-local', choice);
      toast(`${choice === 'classic' ? 'Classic' : 'New'} layout saved on this device. Update Ledger on your server to share it everywhere.`, 'ok', 6500);
    }
  }

  /* ---------------- Page registration ---------------- */
  function safe(render, fallback) {
    return async () => {
      if (!on()) return fallback.render();
      try { return await render(); }
      catch (e) {
        console.error('New layout failed; showing classic page.', e);
        toast('This page is showing the classic layout because the new one could not load.', 'err', 6500);
        return fallback.render();
      }
    };
  }
  registerPage('overview', 'Home', safe(homePage, classic.overview));
  registerPage('transactions', 'Transactions', safe(txPage, classic.transactions));
  registerPage('budgets', 'Budgets', safe(budgetsPage, classic.budgets));
  registerPage('personal', 'Personal', async () => on() ? homePage() : classic.personal.render());
  registerPage('business', 'Business', async () => on() ? homePage() : classic.business.render());
  registerPage('settings', 'Settings', async () => {
    const html = await classic.settings.render();
    return html.includes('<div class="settings-grid">') ? html.replace('<div class="settings-grid">', '<div class="settings-grid">' + layoutCard()) : layoutCard() + html;
  });

  function afterRender() {
    if (!on() || !SCOPED.has(state.page)) return;
    if (state.page === 'overview' || state.page === 'personal' || state.page === 'business') document.getElementById('page-title').textContent = 'Home';
  }

  /* ---------------- Interactions ---------------- */
  document.addEventListener('click', async event => {
    const el = event.target.closest('button, [data-rd-scope]');
    if (!el || !on()) return;
    const d = el.dataset;
    try {
      if (d.rdScope) return setScope(d.rdScope, el);
      if (d.rdPage) return navigate(d.rdPage);
      if (d.rdMetric) { home.metric = d.rdMetric; home.month = null; }
      if (d.rdRange) { home.range = Number(d.rdRange); home.month = null; }
      if (d.rdMetric || d.rdRange) {
        document.getElementById('rd-bars').innerHTML = barsMarkup();
        el.closest('.card').querySelectorAll('[data-rd-metric]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.rdMetric === home.metric)));
        el.closest('.card').querySelectorAll('[data-rd-range]').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.rdRange) === home.range)));
        el.closest('.card').querySelector('h3').textContent = 'Monthly ' + (home.metric === 'spend' ? 'spending' : 'income');
        return;
      }
      if (d.rdMonth) { home.month = home.month === d.rdMonth ? null : d.rdMonth; document.getElementById('rd-bars').innerHTML = barsMarkup(); return; }
      if (d.rdCat !== undefined) {
        home.cat = Number(d.rdCat);
        document.querySelectorAll('.rd-bub').forEach(b => b.setAttribute('aria-pressed', String(b === el)));
        document.getElementById('rd-cat-detail').innerHTML = catDetail();
        return;
      }
      if (d.rdFilterCat) { state.txFilters = { search: '', account_id: '', scope: '', category_id: d.rdFilterCat, since: '', until: '', offset: 0 }; txLocal.uncOnly = false; return navigate('transactions'); }
      if (d.rdBudget) return openBudgetSpending(d.rdBudget, d.scopeOf || (scope === 'everything' ? 'all' : scope));
      if (d.rdTx !== undefined) return openTxEdit(d.rdTx);
      if (d.rdAccount) { const a = state.accounts.find(x => x.id === d.rdAccount); return a && !a.item_id ? openManualAccount(a.id) : navigate('accounts'); }
      if (d.rdGoal) { const g = home.data.goals.find(x => x.id === d.rdGoal); if (g) contribute(g.id, g.name, Math.max(0, g.target - g.saved)); return; }
      if (el.hasAttribute('data-rd-history')) return showModal(`${modalTitle('Estimated net worth history')}<p class="sub">Reconstructed from current balances and recorded transactions. It excludes historical investment price changes.</p>${lineChart(home.data.nw.map(p => ({ label: p.month, v: p.balance })))}<div class="modal-actions">${action('close', 'Close')}${action('page', 'Explore your future', 'future', 'btn btn-primary')}</div>`);
      if (el.hasAttribute('data-rd-ring')) { const p = home.data.plan; return showModal(`${modalTitle('Your monthly plan')}<p class="sub">Actual payments, pending charges, and tracked commitments are counted once.</p>${[['Spent', p.spent], ['Pending', p.pending_spend || 0], ['Upcoming', p.upcoming], ['Total expected', p.total_expected]].map(([k, v]) => `<div class="setting-row"><span>${k}</span><b>${cash(v)}</b></div>`).join('')}<div class="modal-actions">${action('close', 'Close')}${action('spending-plan', 'Edit plan', '', 'btn btn-primary')}</div>`); }
      if (el.hasAttribute('data-rd-rentfree')) { const t = LedgerSarahBudget.totals(home.data.cats); return showModal(`${modalTitle('This month · without rent')}<p class="sub">Posted expenses only. Transfers, pending payments, and the Rent / Mortgage category are excluded.</p><div class="setting-row"><span>Spending outside rent</span><b>${cash(t.spent)}</b></div>${t.categories.map(c => `<div class="setting-row"><span>${esc(c.name)}</span><b>${cash(c.amt)}</b></div>`).join('')}<div class="modal-actions">${action('close', 'Close')}</div>`); }
      if (d.rdFlip) { const to = d.from === 'personal' ? 'business' : 'personal'; el.disabled = true; await updateTx({ id: d.rdFlip, scope: to }); netsAt = 0; undoable(`Moved ${d.name} to ${LABEL[to]}`, () => updateTx({ id: d.rdFlip, scope: d.from })); await refresh(); syncChrome(); return; }
      // Transactions
      if (d.rdScopeSet) { if (d.rdScopeSet === d.from) return; el.closest('.rd-seg2')?.setAttribute('data-s', d.rdScopeSet); return moveScope(d.id, d.rdScopeSet, d.from, d.name); }
      if (el.hasAttribute('data-rd-unc')) { txLocal.uncOnly = !txLocal.uncOnly; state.txFilters.category_id = ''; state.txFilters.offset = 0; return refresh(); }
      if (d.rdCatFilter) { state.txFilters.category_id = state.txFilters.category_id === d.rdCatFilter ? '' : d.rdCatFilter; state.txFilters.offset = 0; txLocal.uncOnly = false; return refresh(); }
      if (el.hasAttribute('data-rd-clear')) { state.txFilters = { search: '', account_id: '', scope: '', category_id: '', since: '', until: '', offset: 0 }; txLocal.uncOnly = false; return refresh(); }
      if (d.rdPageStep) { state.txFilters.offset = Math.max(0, (state.txFilters.offset || 0) + Number(d.rdPageStep) * txLocal.limit); return refresh(); }
      if (d.rdPrompt) {
        const p = txLocal.prompt;
        txLocal.prompt = null;
        if (d.rdPrompt === 'apply' && p) {
          el.disabled = true;
          for (const id of p.ids) await updateTx({ id, scope: p.to });
          netsAt = 0;
          undoable(`Moved ${p.ids.length + 1} ${p.name} purchases to ${LABEL[p.to]}`, async () => { for (const id of [p.origin, ...p.ids]) await updateTx({ id, scope: p.from }); });
          await refresh(); syncChrome(); return;
        }
        return renderActionbar();
      }
      if (d.rdBulk) {
        const ids = [...txLocal.selected], rows = ids.map(id => document.querySelector(`tr[data-id="${CSS.escape(id)}"] [data-rd-scope-set]`)?.dataset.from);
        el.disabled = true;
        for (const id of ids) await updateTx({ id, scope: d.rdBulk });
        txLocal.selected.clear();
        netsAt = 0;
        undoable(`Moved ${ids.length} transaction${ids.length === 1 ? '' : 's'} to ${LABEL[d.rdBulk]}`, async () => { for (let i = 0; i < ids.length; i++) if (rows[i]) await updateTx({ id: ids[i], scope: rows[i] }); });
        await refresh(); syncChrome(); return;
      }
      if (el.hasAttribute('data-rd-bulk-clear')) { txLocal.selected.clear(); document.querySelectorAll('[data-rd-select]').forEach(c => { c.checked = false; c.closest('tr').dataset.checked = 'false'; }); return renderActionbar(); }
      // Budgets
      if (d.rdSort) { const m = d.rdSort, end = new Date(+m.slice(0, 4), +m.slice(5), 0).getDate(); state.txFilters = { search: '', account_id: '', scope: '', category_id: '', since: m + '-01', until: `${m}-${String(end).padStart(2, '0')}`, offset: 0 }; txLocal.uncOnly = true; return navigate('transactions'); }
      if (d.rdBudgetEdit) { budLocal.editing = d.rdBudgetEdit; await refresh(); document.querySelector(`[data-rd-budget-input="${CSS.escape(d.rdBudgetEdit)}"]`)?.focus(); return; }
      if (d.rdBudgetSave) {
        const input = document.querySelector(`[data-rd-budget-input="${CSS.escape(d.rdBudgetSave)}"]`);
        const limit = parseFloat(String(input?.value || '').replace(/[$,\s]/g, ''));
        if (!(limit > 0)) return toast('Enter a monthly amount greater than zero.', 'err');
        el.disabled = true;
        const saved = await api('/budgets', { method: 'POST', body: JSON.stringify({ category_id: d.rdBudgetSave, scope: scope === 'everything' ? 'all' : scope, month_limit: limit }) });
        budLocal.editing = null;
        undoable('Budget set', () => api('/budgets?id=' + encodeURIComponent(saved.id), { method: 'DELETE' }));
        return refresh();
      }
      // Settings
      if (d.rdLayout) { await chooseLayout(d.rdLayout); return navigate('settings'); }
      if (el.hasAttribute('data-rd-layout-local-clear')) { write('ledger-layout-local', null); return navigate('settings'); }
    } catch (e) {
      toast(e.message || 'Something went wrong. Try again.', 'err');
    }
  });

  // Layout choice must work while the classic layout is active too.
  document.addEventListener('click', async event => {
    const el = event.target.closest('[data-rd-layout], [data-rd-layout-local-clear]');
    if (!el || on()) return;
    try {
      if (el.dataset.rdLayout) await chooseLayout(el.dataset.rdLayout);
      else write('ledger-layout-local', null);
      await navigate('settings');
    } catch (e) { toast(e.message || 'Could not save the layout.', 'err'); }
  });

  document.addEventListener('change', async event => {
    const el = event.target;
    if (!on() || !view.contains(el)) return;
    try {
      if (el.dataset.rdCatSet) {
        const id = el.dataset.rdCatSet, old = el.dataset.old || null, value = el.value || null;
        el.dataset.unc = String(!value);
        await updateTx({ id, category_id: value });
        const chosen = state.categories.find(c => c.id === value);
        undoable(value ? `Filed under ${chosen ? chosen.name : 'category'}` : 'Category cleared', () => updateTx({ id, category_id: old }));
        await refresh();
        if (value && chosen?.kind === 'expense') await previewCategoryBatch(id, value);
        return;
      }
      if (el.dataset.rdFilter) { state.txFilters[el.dataset.rdFilter] = el.value; state.txFilters.offset = 0; return refresh(); }
      if (el.dataset.rdSelect) {
        el.checked ? txLocal.selected.add(el.dataset.rdSelect) : txLocal.selected.delete(el.dataset.rdSelect);
        el.closest('tr').dataset.checked = String(el.checked);
        txLocal.prompt = null;
        return renderActionbar();
      }
      if (el.hasAttribute('data-rd-select-all')) {
        document.querySelectorAll('[data-rd-select]').forEach(c => { c.checked = el.checked; el.checked ? txLocal.selected.add(c.dataset.rdSelect) : txLocal.selected.delete(c.dataset.rdSelect); c.closest('tr').dataset.checked = String(el.checked); });
        txLocal.prompt = null;
        return renderActionbar();
      }
    } catch (e) { toast(e.message || 'Could not save that change.', 'err'); await refresh(); }
  });
  document.addEventListener('keydown', event => {
    const el = event.target;
    if (event.key === 'Enter' && el.matches?.('[data-rd-search]') && on()) { state.txFilters.search = el.value; state.txFilters.offset = 0; txLocal.uncOnly = false; refresh(); }
  });

  syncChrome();
})();

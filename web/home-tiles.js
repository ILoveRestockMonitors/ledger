/* Local home-dashboard visibility preferences, independent for each money scope. */
(() => {
  'use strict';
  const view = document.getElementById('view');
  if (!view) return;
  const labels = {
    'net-worth': 'Net worth and accounts', 'spending-split': 'Spending split',
    cashflow: 'Money in, money out', review: 'Needs a look', 'without-rent': 'Spending without rent',
    runway: 'Runway', saved: 'Saved this month', taxes: 'Set aside for taxes',
    deductible: 'Deductible spend', clients: 'Clients', plan: 'Monthly plan',
    'monthly-chart': 'Monthly spending / income', categories: 'Spend constellation',
    'category-detail': 'Category details', recent: 'Recent activity', upcoming: 'Coming up', goals: 'Savings goals'
  };
  const cache = new Map();
  const key = scope => `ledger-hidden-home-tiles-v1:${scope}`;
  function preferences(scope) {
    if (!cache.has(scope)) {
      let value;
      try { value = JSON.parse(localStorage.getItem(key(scope))); } catch {}
      cache.set(scope, new Set(Array.isArray(value) ? value.filter(id => Object.hasOwn(labels, id)) : []));
    }
    return cache.get(scope);
  }
  function apply() {
    const home = view.querySelector('.rd-home[data-home-scope]');
    if (!home) return;
    const hidden = preferences(home.dataset.homeScope);
    const cards = [...home.querySelectorAll('[data-home-tile]')];
    let manager = home.querySelector('.home-tile-manager');
    if (!manager) {
      manager = document.createElement('details');
      manager.className = 'home-tile-manager';
      const summary = document.createElement('summary');
      summary.textContent = 'Manage tiles';
      summary.className = 'btn';
      manager.append(summary);
      const options = document.createElement('div');
      options.className = 'home-tile-options';
      const note = document.createElement('p');
      note.textContent = 'Choose tiles to show. Saved for this browser and money view.';
      options.append(note);
      for (const card of cards) {
        const id = card.dataset.homeTile;
        const label = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'checkbox'; input.dataset.homeTileToggle = id;
        label.append(input, document.createTextNode(labels[id] || id)); options.append(label);
      }
      const restore = document.createElement('button');
      restore.type = 'button'; restore.className = 'btn btn-sm';
      restore.dataset.homeTilesRestore = ''; restore.textContent = 'Show all tiles';
      options.append(restore); manager.append(options);
      const add = home.querySelector('.rd-welcome [data-action="add-tx"]');
      const actions = document.createElement('div');
      actions.className = 'home-tile-actions';
      add.before(actions);
      actions.append(manager, add);
    }
    for (const card of cards) {
      const id = card.dataset.homeTile;
      card.hidden = hidden.has(id);
      if (!card.querySelector('[data-home-tile-hide]')) {
        const controls = document.createElement('div'); controls.className = 'home-tile-controls';
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'link-button home-tile-hide';
        button.dataset.homeTileHide = id;
        button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.5 5.4A11 11 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3.1 3.7M6.2 6.2A20 20 0 0 0 2 12s4 7 10 7a10 10 0 0 0 5-1.4"/></svg><span>Hide</span>';
        button.setAttribute('aria-label', `Hide ${labels[id] || id} tile`);
        controls.append(button); card.prepend(controls);
      }
    }
    manager.querySelectorAll('[data-home-tile-toggle]').forEach(input => { input.checked = !hidden.has(input.dataset.homeTileToggle); });
    home.querySelectorAll('.rd-grid').forEach(grid => {
      const children = [...grid.children].filter(el => el.matches('[data-home-tile]'));
      if (!children.length) return;
      const visible = children.filter(el => !el.hidden).length;
      grid.hidden = visible === 0;
      grid.classList.toggle('home-tiles-reflow', visible > 0 && visible < children.length);
      grid.style.setProperty('--home-visible-columns', visible);
    });
  }
  function save(home) {
    try { localStorage.setItem(key(home.dataset.homeScope), JSON.stringify([...preferences(home.dataset.homeScope)])); }
    catch { if (typeof toast === 'function') toast('Tiles hidden for this session. Browser storage is unavailable.', 'err'); }
    apply();
  }
  view.addEventListener('click', event => {
    const button = event.target.closest('[data-home-tile-hide], [data-home-tiles-restore]');
    if (!button) return;
    const home = button.closest('.rd-home'); if (!home) return;
    const hidden = preferences(home.dataset.homeScope);
    if (button.hasAttribute('data-home-tile-hide')) hidden.add(button.dataset.homeTileHide);
    else hidden.clear();
    save(home);
    if (button.hasAttribute('data-home-tile-hide')) home.querySelector('.home-tile-manager summary').focus();
  });
  view.addEventListener('change', event => {
    const input = event.target.closest('[data-home-tile-toggle]'); if (!input) return;
    const home = input.closest('.rd-home'); const hidden = preferences(home.dataset.homeScope);
    input.checked ? hidden.delete(input.dataset.homeTileToggle) : hidden.add(input.dataset.homeTileToggle);
    save(home);
  });
  // Rendering and the category-detail panel replace their markup in place.
  new MutationObserver(apply).observe(view, { childList: true, subtree: true });
  window.addEventListener('storage', event => { if (event.key === null || event.key.startsWith('ledger-hidden-home-tiles-v1:')) { cache.clear(); apply(); } });
  apply();
})();

/* A full document navigation discards private records, filters and open dialogs. */
const LedgerDemo = (() => {
  const active = new URLSearchParams(location.search).get('demo') === '1';
  const key = 'ledger-demo-presentation';
  const allowed = new Set(['theme', 'density', 'home_cards', 'palette', 'font_family', 'accent']);
  let preferences = {};
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || '{}');
    for (const [name, value] of Object.entries(saved)) if (allowed.has(name)) preferences[name] = value;
  } catch {}
  function switchMode() {
    const url = new URL(location.href);
    // OAuth return parameters belong to the private bank-linking session.
    url.search = active ? '' : '?demo=1';
    url.hash = 'overview';
    location.assign(url.href);
  }
  const button = document.getElementById('btn-demo');
  button.addEventListener('click', switchMode);
  const label = active ? 'Return to my Ledger' : 'Demo version';
  button.querySelector('.sidebar-button-label').textContent = label;
  button.setAttribute('aria-label', label);
  button.title = label;
  button.setAttribute('aria-pressed', String(active));
  document.documentElement.dataset.demo = String(active);
  if (active) {
    document.title = 'Ledger · Demo version';
    document.getElementById('page-title').insertAdjacentHTML('afterend', '<span class="demo-indicator" aria-label="Demo version">DEMO</span>');
    const banner = document.getElementById('demo-banner');
    banner.hidden = false;
    banner.innerHTML = '<strong>Demo version</strong><span>Fictional finances · Read-only. Explore filters, reports and projections.</span>';
  }
  return {
    active,
    switchMode,
    url: path => '/api' + (active && !path.startsWith('/auth/') ? '/preview' : '') + path,
    config: data => active ? {...data, ...preferences, demo: true} : data,
    savePreferences: async changes => {
      if (typeof changes === 'string') changes = JSON.parse(changes);
      if (!changes || Object.keys(changes).some(name => !allowed.has(name))) {
        throw new Error('Demo version is read-only. You can change its appearance or explore a projection.');
      }
      if (('theme' in changes && !['light', 'dark', 'system'].includes(changes.theme)) ||
          ('density' in changes && !['compact', 'comfortable'].includes(changes.density)) ||
          ('home_cards' in changes && (!Array.isArray(changes.home_cards) || changes.home_cards.length > 4 ||
           changes.home_cards.some(k => !['recent', 'upcoming', 'cashflow', 'goals'].includes(k))))) {
        throw new Error('Choose a valid presentation preference.');
      }
      preferences = {...preferences, ...changes};
      try { sessionStorage.setItem(key, JSON.stringify(preferences)); } catch {}
      return api('/config');
    },
  };
})();

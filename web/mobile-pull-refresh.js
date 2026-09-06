/* A bounded, read-only Home refresh. Never invokes the bank-sync action. */
(() => {
  const root = document.documentElement;
  const main = document.getElementById('main');
  const view = document.getElementById('view');
  if (!main || !view) return;
  const mobile = matchMedia('(max-width: 700px)');
  const ignored = 'a, button, input, select, textarea, label, summary, [role="button"], [contenteditable="true"], .table-wrap, .ar-accts';
  const indicator = document.createElement('div');
  indicator.id = 'mobile-pull-status';
  indicator.setAttribute('role', 'status');
  indicator.setAttribute('aria-live', 'polite');
  indicator.innerHTML = '<span aria-hidden="true">↓</span><span class="pull-label">Pull to refresh</span>';
  document.body.append(indicator);
  const label = indicator.querySelector('.pull-label');
  const icon = indicator.firstElementChild;
  let gesture = null, distance = 0, busy = false, settleTimer;
  const atHome = () => !location.hash || location.hash === '#overview';
  const blocked = () => !mobile.matches || !atHome() || busy ||
    document.body.matches('.nav-open, .modal-active, .keyboard-open, .auth-active') ||
    Boolean(document.querySelector('.modal-backdrop, #auth-screen'));
  function setDistance(value) {
    distance = value;
    root.style.setProperty('--mobile-pull-distance', `${Math.round(value)}px`);
    const ready = value >= 40;
    root.toggleAttribute('data-pull-ready', ready);
    label.textContent = ready ? 'Release to refresh' : 'Pull to refresh';
    icon.textContent = ready ? '↻' : '↓';
  }
  function settle() {
    gesture = null;
    root.removeAttribute('data-pull-active');
    root.removeAttribute('data-pull-ready');
    root.removeAttribute('data-pull-loading');
    root.setAttribute('data-pull-settling', '');
    root.style.setProperty('--mobile-pull-distance', '0px');
    distance = 0;
    clearTimeout(settleTimer);
    settleTimer = setTimeout(() => root.removeAttribute('data-pull-settling'), 220);
  }
  function nestedScroller(target) {
    for (let node = target; node && node !== main; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1) return true;
    }
    return false;
  }
  main.addEventListener('touchstart', event => {
    if (blocked() || event.touches.length !== 1 || window.scrollY > 1 ||
        !(event.target instanceof Element) || event.target.closest(ignored) || nestedScroller(event.target)) return;
    clearTimeout(settleTimer);
    root.removeAttribute('data-pull-settling');
    const touch = event.touches[0];
    root.style.setProperty('--mobile-pull-top', `${Math.max(0, view.getBoundingClientRect().top)}px`);
    gesture = {x: touch.clientX, y: touch.clientY, claimed: false};
  }, {passive: true});
  main.addEventListener('touchmove', event => {
    if (!gesture) return;
    if (blocked() || event.touches.length !== 1) { settle(); return; }
    const dx = event.touches[0].clientX - gesture.x;
    const dy = event.touches[0].clientY - gesture.y;
    if (!gesture.claimed) {
      if (Math.abs(dx) > Math.abs(dy) || dy < 0 || window.scrollY > 1) { gesture = null; return; }
      if (dy < 3) return;
      gesture.claimed = true;
      root.setAttribute('data-pull-active', '');
    }
    if (event.cancelable) event.preventDefault();
    // Damped resistance caps even very long swipes at 52 CSS pixels.
    setDistance(Math.max(0, Math.min(52, dy * 0.45)));
  }, {passive: false});
  main.addEventListener('touchend', async () => {
    if (!gesture) return;
    const refresh = gesture.claimed && distance >= 40 && !blocked();
    gesture = null;
    if (!refresh) { settle(); return; }
    busy = true;
    root.setAttribute('data-pull-loading', '');
    label.textContent = 'Refreshing Home…';
    icon.textContent = '↻';
    try {
      if (typeof navigate === 'function') await navigate('overview');
    } finally {
      busy = false;
      settle();
    }
  }, {passive: true});
  main.addEventListener('touchcancel', settle, {passive: true});
  window.addEventListener('hashchange', settle);
  mobile.addEventListener('change', settle);
  document.addEventListener('visibilitychange', () => { if (document.hidden) settle(); });
})();

/* Phone navigation shares the existing routes and transaction actions. */
(() => {
  const media = matchMedia('(max-width: 700px)');
  const sidebar = document.getElementById('sidebar');
  const main = document.getElementById('main');
  const menu = document.getElementById('btn-menu');
  const add = document.getElementById('mobile-add');
  if (!sidebar || !main || !menu || !add) return;

  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'mobile-drawer-close';
  closeButton.setAttribute('aria-label', 'Close navigation');
  closeButton.textContent = '×';
  sidebar.prepend(closeButton);
  const bottom = document.createElement('nav');
  bottom.id = 'mobile-nav';
  bottom.setAttribute('aria-label', 'Quick navigation');
  bottom.innerHTML = [['overview', '⌂', 'Home'], ['transactions', '⇄', 'Spending'], ['budgets', '◎', 'Budgets']]
    .map(([page, icon, label]) => `<a class="mobile-nav-item" href="#${page}" data-mobile-page="${page}"><span class="mobile-nav-icon" aria-hidden="true">${icon}</span><span>${label}</span></a>`).join('')
    + '<button id="mobile-more" class="mobile-nav-item" type="button" aria-expanded="false" aria-controls="sidebar"><span class="mobile-nav-icon" aria-hidden="true">☷</span><span>More</span></button>';
  document.body.append(bottom);
  const more = bottom.querySelector('#mobile-more');
  menu.setAttribute('aria-controls', 'sidebar');
  let drawerOpen = false;
  let returnFocus = null;
  const modalOpen = () => Boolean(document.querySelector('.modal-backdrop'));
  const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
  const focusables = () => [...sidebar.querySelectorAll('a[href], button:not(:disabled), summary, input:not(:disabled), select:not(:disabled), [tabindex="0"]')].filter(visible);
  const toggleClass = (name, value) => {
    if (document.body.classList.contains(name) !== value) document.body.classList.toggle(name, value);
  };
  function setDrawer(open, restoreFocus = true) {
    const active = Boolean(open && media.matches && !modalOpen() && !document.getElementById('auth-screen'));
    const wasOpen = drawerOpen;
    drawerOpen = active;
    if (active && !wasOpen) returnFocus = document.activeElement;
    toggleClass('nav-open', active);
    menu.setAttribute('aria-expanded', String(active));
    more.setAttribute('aria-expanded', String(active));
    main.inert = active;
    add.inert = active || modalOpen();
    bottom.inert = active || modalOpen();
    if (media.matches) sidebar.setAttribute('aria-hidden', String(!active));
    else sidebar.removeAttribute('aria-hidden');
    if (active && !wasOpen) requestAnimationFrame(() => {
      if (drawerOpen) focusables()[0]?.focus();
    });
    if (!active && wasOpen) {
      const target = returnFocus;
      returnFocus = null;
      requestAnimationFrame(() => {
        if (restoreFocus && !drawerOpen && !modalOpen() && target?.isConnected && visible(target)) target.focus();
      });
    }
  }
  menu.onclick = () => setDrawer(!drawerOpen);
  more.onclick = () => setDrawer(true);
  closeButton.onclick = () => setDrawer(false);
  document.getElementById('nav-shade').onclick = () => setDrawer(false);
  sidebar.addEventListener('click', event => {
    if (event.target.closest('a[href^="#"], #btn-add-tx')) setDrawer(false, false);
  }, true);
  bottom.addEventListener('click', event => {
    const link = event.target.closest('[data-mobile-page]');
    if (!link) return;
    event.preventDefault();
    setDrawer(false);
    navigate(link.dataset.mobilePage);
  });
  document.addEventListener('keydown', event => {
    if (!drawerOpen) return;
    if (event.key === 'Escape') { event.preventDefault(); setDrawer(false); return; }
    if (event.key !== 'Tab') return;
    const controls = focusables(), first = controls[0], last = controls.at(-1);
    if (!first) return;
    if (event.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) {
      event.preventDefault(); first.focus();
    }
  });
  function updateRoute() {
    const page = location.hash.slice(1) || 'overview';
    bottom.querySelectorAll('[data-mobile-page]').forEach(link => {
      if (link.dataset.mobilePage === page) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }
  function reconcile() {
    const auth = Boolean(document.getElementById('auth-screen'));
    const modal = modalOpen();
    toggleClass('auth-active', auth);
    toggleClass('modal-active', modal);
    if (drawerOpen && (auth || modal || !document.body.classList.contains('nav-open'))) setDrawer(false, !modal);
    bottom.inert = drawerOpen || modal || auth;
  }
  new MutationObserver(reconcile).observe(document.body, {childList: true, subtree: true});
  new MutationObserver(reconcile).observe(document.body, {attributes: true, attributeFilter: ['class']});
  window.addEventListener('hashchange', updateRoute);
  media.addEventListener('change', () => { setDrawer(false); updateViewport(); });
  function updateViewport() {
    const viewport = window.visualViewport;
    const gap = viewport && media.matches ? Math.max(0, innerHeight - viewport.height - viewport.offsetTop) : 0;
    toggleClass('keyboard-open', gap > 120);
  }
  window.visualViewport?.addEventListener('resize', updateViewport);
  window.visualViewport?.addEventListener('scroll', updateViewport);
  setDrawer(false);
  reconcile();
  updateRoute();
  updateViewport();
})();

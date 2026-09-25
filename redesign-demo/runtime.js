/* Runs the canvas's .dc.html screens as plain web pages: {{holes}}, sc-for / sc-if,
   event bindings and a small DOM morph so CSS transitions survive re-renders. */
(function () {
  'use strict';
  const HOLE = /\{\{\s*([^}]+?)\s*\}\}/g;
  const WHOLE = /^\s*\{\{\s*([^}]+?)\s*\}\}\s*$/;

  function lookup(ctx, path) {
    path = path.trim();
    if (path === 'true') return true;
    if (path === 'false') return false;
    if (path === 'null') return null;
    if (/^-?\d+(\.\d+)?$/.test(path)) return Number(path);
    if (/^(['"]).*\1$/.test(path)) return path.slice(1, -1);
    let value = ctx;
    for (const key of path.split('.')) {
      if (value == null) return undefined;
      value = value[key];
    }
    return value;
  }
  const interpolate = (text, ctx) => text.replace(HOLE, (_, path) => {
    const value = lookup(ctx, path);
    return value == null ? '' : String(value);
  });
  const holeValue = (raw, ctx) => {
    const whole = raw && raw.match(WHOLE);
    return whole ? lookup(ctx, whole[1]) : raw;
  };

  // sc-for / sc-if become <template> so the HTML parser keeps them inside <select> and friends.
  function compile(source, assets) {
    let text = source;
    for (const [from, to] of Object.entries(assets)) text = text.split(from).join(to);
    text = text.replace(/<sc-(for|if)\b/g, '<template data-sc="$1"').replace(/<\/sc-(for|if)>/g, '</template>');
    const doc = new DOMParser().parseFromString(text, 'text/html');
    const xdc = doc.querySelector('x-dc');
    const helmet = xdc.querySelector('helmet');
    const styles = helmet ? [...helmet.querySelectorAll('style')].map(s => s.textContent).join('\n') : '';
    if (helmet) helmet.remove();
    const script = doc.querySelector('script[data-dc-script]');
    return {
      root: xdc.firstElementChild,
      styles,
      code: script.textContent,
      title: (doc.querySelector('title') || {}).textContent || '',
    };
  }

  // React's onChange fires on every keystroke for text fields.
  function domEvent(el, name) {
    if (name !== 'change') return name;
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    return (el.localName === 'input' && type !== 'checkbox' && type !== 'radio') || el.localName === 'textarea' ? 'input' : 'change';
  }
  function listen(el) {
    if (!el.__dcOn) return;
    el.__dcBound = el.__dcBound || new Set();
    for (const type of Object.keys(el.__dcOn)) {
      if (el.__dcBound.has(type)) continue;
      el.__dcBound.add(type);
      el.addEventListener(type, event => {
        const handler = el.__dcOn && el.__dcOn[type];
        if (handler) handler(event);
      });
    }
  }
  function applyProps(live, fresh) {
    if (fresh.__value !== undefined && live.value !== fresh.__value) live.value = fresh.__value;
    if (fresh.__checked !== undefined && live.checked !== fresh.__checked) live.checked = fresh.__checked;
  }

  function build(node, ctx, parent) {
    if (node.nodeType === 3) { parent.appendChild(document.createTextNode(interpolate(node.nodeValue, ctx))); return; }
    if (node.nodeType !== 1) return;
    if (node.localName === 'template' && node.dataset.sc) {
      if (node.dataset.sc === 'if') {
        if (holeValue(node.getAttribute('value'), ctx)) for (const child of node.content.childNodes) build(child, ctx, parent);
        return;
      }
      const list = holeValue(node.getAttribute('list'), ctx) || [];
      const as = node.getAttribute('as') || 'item';
      list.forEach((item, index) => {
        const scope = Object.create(ctx);
        scope[as] = item;
        scope.$index = index;
        for (const child of node.content.childNodes) build(child, scope, parent);
      });
      return;
    }
    const el = node.namespaceURI === 'http://www.w3.org/2000/svg'
      ? document.createElementNS(node.namespaceURI, node.localName)
      : document.createElement(node.localName);
    for (const attr of node.attributes) {
      const name = attr.name;
      if (name.startsWith('hint-')) continue;
      const whole = attr.value.match(WHOLE);
      if (/^on[a-z]+$/.test(name)) {
        const handler = whole && lookup(ctx, whole[1]);
        if (typeof handler === 'function') (el.__dcOn = el.__dcOn || {})[domEvent(el, name.slice(2))] = handler;
        continue;
      }
      const value = whole ? lookup(ctx, whole[1]) : interpolate(attr.value, ctx);
      if (name === 'value' && el.localName !== 'option') { if (value != null) el.__value = String(value); continue; }
      if (name === 'checked') { el.__checked = !!value; continue; }
      if (value === false || value == null || typeof value === 'function' || typeof value === 'object') continue;
      el.setAttribute(name, value === true ? '' : String(value));
    }
    for (const child of node.childNodes) build(child, ctx, el);
    applyProps(el, el);
    listen(el);
    parent.appendChild(el);
  }

  function morph(live, fresh) {
    if (live.nodeType !== fresh.nodeType || live.nodeName !== fresh.nodeName) { live.replaceWith(fresh); return fresh; }
    if (live.nodeType === 3) { if (live.nodeValue !== fresh.nodeValue) live.nodeValue = fresh.nodeValue; return live; }
    for (const attr of [...live.attributes]) if (!fresh.hasAttribute(attr.name)) live.removeAttribute(attr.name);
    for (const attr of fresh.attributes) if (live.getAttribute(attr.name) !== attr.value) live.setAttribute(attr.name, attr.value);
    live.__dcOn = fresh.__dcOn;
    listen(live);
    const oldKids = [...live.childNodes], newKids = [...fresh.childNodes];
    newKids.forEach((kid, i) => { if (i < oldKids.length) morph(oldKids[i], kid); else live.appendChild(kid); });
    for (let i = newKids.length; i < oldKids.length; i++) oldKids[i].remove();
    live.__value = fresh.__value;
    live.__checked = fresh.__checked;
    applyProps(live, fresh);
    return live;
  }

  class DCLogic {
    constructor(props) { this.props = props || {}; this.state = {}; }
    setState(update) {
      if (!this.__prevState) this.__prevState = Object.assign({}, this.state);
      const patch = typeof update === 'function' ? update(this.state, this.props) : update;
      this.state = Object.assign({}, this.state, patch);
      if (this.__host) this.__host.schedule();
    }
    forceUpdate() { if (this.__host) this.__host.schedule(); }
  }

  function mount(screen, container, props, after) {
    const Component = new Function('DCLogic', screen.code + '\n;return Component;')(DCLogic);
    const inst = new Component(props);
    inst.props = props;
    let live = null, mounted = false, queued = false;
    const host = { schedule() { if (!queued) { queued = true; queueMicrotask(render); } } };
    function render() {
      queued = false;
      if (inst.__host !== host) return;
      const prevState = inst.__prevState || inst.state;
      inst.__prevState = null;
      const frag = document.createDocumentFragment();
      build(screen.root, inst.renderVals(), frag);
      const fresh = frag.firstElementChild;
      if (!live) { container.appendChild(fresh); live = fresh; } else live = morph(live, fresh);
      if (!mounted) { mounted = true; if (inst.componentDidMount) inst.componentDidMount(); }
      else if (inst.componentDidUpdate) inst.componentDidUpdate(inst.props, prevState);
      if (after) after(live, inst);
    }
    inst.__host = host;
    render();
    return {
      inst,
      unmount() {
        if (inst.componentWillUnmount) inst.componentWillUnmount();
        inst.__host = null;
        container.replaceChildren();
      },
    };
  }

  window.LedgerDC = { compile, mount };
})();

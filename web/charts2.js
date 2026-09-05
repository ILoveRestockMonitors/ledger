/* Ledger charts — part 2: heatmap, sparkline, helpers. */

function heatMap(dayMap, opt = {}) {
  // dayMap: {"YYYY-MM-DD": spend}
  const weeks = opt.weeks || 26;
  const today = new Date();
  const end = new Date(today);
  end.setDate(end.getDate() + (6 - end.getDay())); // align to Saturday
  const days = [];
  for (let w = weeks; w >= 0; w--) {
    for (let d = 0; d < 7; d++) {
      const dt = new Date(end);
      dt.setDate(end.getDate() - w*7 + d - 6);
      days.push(dt);
    }
  }
  let cells = "";
  const vals = Object.values(dayMap);
  const max = Math.max(1, ...vals);
  function colorFor(v) {
    if (!v) return "rgba(128,140,165,.10)";
    const t = Math.sqrt(v / max);
    return `rgba(var(--heat-rgb),${(0.18 + t*0.82).toFixed(2)})`;
  }
  days.forEach(dt => {
    const iso = dt.toISOString().slice(0,10);
    const v = dayMap[iso] || 0;
    const future = dt > today;
    cells += `<i class="heat-cell" style="opacity:${future ? 0 : 1};background:${future ? "transparent" : colorFor(v)}" title="${iso}: ${fmtMoney(v)}"></i>`;
  });
  return `<div class="heat-grid">${cells}</div>
    <div class="row-between small muted mt">
      <span>${weeks} weeks</span>
      <span class="row">less
        <i class="heat-cell" style="background:rgba(128,140,165,.10)"></i>
        <i class="heat-cell" style="background:rgba(var(--heat-rgb),.35)"></i>
        <i class="heat-cell" style="background:rgba(var(--heat-rgb),.65)"></i>
        <i class="heat-cell" style="background:rgba(var(--heat-rgb),1)"></i> more
      </span>
    </div>`;
}

function sparkline(vals, color="#6c8cff") {
  if (!vals.length) return "";
  const W = 110, H = 30;
  let min = Math.min(...vals), max = Math.max(...vals);
  if (min === max) max = min + 1;
  const pts = vals.map((v,i)=>`${(W*i/(vals.length-1||1)).toFixed(1)},${(H-2-(H-4)*(v-min)/(max-min)).toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"><polyline fill="none" stroke="${color}" stroke-width="1.8" points="${pts}"/></svg>`;
}

/* ---------- modal helper ---------- */
let modalReturnFocus = null;
function showModal(html) {
  closeModal();
  modalReturnFocus = document.activeElement;
  const root = document.getElementById("modal-root");
  root.innerHTML = `<div class="modal-backdrop" id="modal-backdrop"><div class="modal" role="dialog" aria-modal="true" tabindex="-1">${html}</div></div>`;
  const modal = root.querySelector('.modal'), heading = modal.querySelector('h2');
  if (heading) { heading.id='dialog-title'; modal.setAttribute('aria-labelledby',heading.id); }
  document.getElementById('app').inert = true;
  document.getElementById('mobile-add').inert = true;
  document.body.style.overflow = 'hidden';
  root.querySelector("#modal-backdrop").addEventListener("click", e => { if (e.target.id === "modal-backdrop") closeModal(); });
  requestAnimationFrame(()=> (modal.querySelector('[autofocus]')||modal.querySelector('input, select')||modal.querySelector('button')||modal).focus());
}
function closeModal() {
  document.getElementById("modal-root").innerHTML = "";
  document.getElementById('app').inert = false;
  document.getElementById('mobile-add').inert = false;
  document.body.style.overflow = '';
  const returnTarget = modalReturnFocus;
  modalReturnFocus = null;
  // Mobile controls become visible after the modal-state observer runs.
  requestAnimationFrame(() => {
    if (!document.querySelector('.modal') && returnTarget?.isConnected &&
        !returnTarget.closest('[inert]') && returnTarget.getClientRects().length) {
      returnTarget.focus({preventScroll: true});
    }
  });
}
document.addEventListener('keydown',e=>{
  const modal=document.querySelector('.modal'); if(!modal)return;
  if(e.key==='Escape'){e.preventDefault();closeModal();}
  if(e.key==='Tab'){
    const controls=[...modal.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea, a[href], [tabindex="0"]')].filter(el=>el.getClientRects().length);
    const first=controls[0],last=controls[controls.length-1];
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
    if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
  }
});

/* ---------- toast ---------- */
function toast(msg, kind="ok", ms=3400) {
  const root = document.getElementById("toast-root");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  root.appendChild(el);
  setTimeout(()=>{ el.style.opacity="0"; setTimeout(()=>el.remove(), 250); }, ms);
}

/* CSS the charts rely on */
const CHART_CSS = `
.ax-label { font-size: 9.5px; fill: #8b94a7; font-family: inherit; }
.donut-wrap { display:flex; gap:18px; align-items:center; flex-wrap:wrap; }
.donut-num { font-size:15px; font-weight:700; fill:var(--text); }
.heat-grid { display:grid; grid-template-rows: repeat(7, 13px); grid-auto-flow: column; gap:3px; overflow-x:auto; padding-bottom:4px; }
`;
const _style = document.createElement("style");
_style.textContent = CHART_CSS;
document.head.appendChild(_style);

/* Ledger charts — hand-rolled SVG, no dependencies.
   All functions return an HTML string. */

const CHART_COLORS = Array.from({length:8},(_,i)=>`var(--chart-${i+1})`);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));
}

function fmtMoney(v, opts={}) {
  const n = Number(v) || 0;
  const sign = n < 0 ? "-" : "";
  const a = Math.abs(n);
  let s;
  if (opts.compact && a >= 1000) {
    s = (a/1000).toFixed(a >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k";
  } else {
    s = a.toLocaleString("en-US", { minimumFractionDigits: opts.decimals ?? (Number.isInteger(n) ? 0 : 2), maximumFractionDigits: opts.decimals ?? 2 });
  }
  return sign + "$" + s;
}

/* ---------- grouped bars: income vs spend by month ---------- */
function barChart(data, opt = {}) {
  const W = opt.width || 640, H = opt.height || 240;
  const padL = 46, padR = 10, padT = 12, padB = 26;
  const iw = W - padL - padR, ih = H - padT - padB;
  if (!data.length) return "<div class='empty'>No data yet</div>";
  const maxV = Math.max(1, ...data.map(d => Math.max(d.income || 0, d.spend || 0)));
  const step = iw / data.length;
  const bw = Math.min(20, step * 0.32);
  let bars = "", labels = "";
  data.forEach((d, i) => {
    const x = padL + i * step + step / 2;
    const hi = ih * (d.income || 0) / maxV;
    const hs = ih * (d.spend || 0) / maxV;
    bars += `<rect x="${(x-bw-1.5).toFixed(1)}" y="${(padT+ih-hi).toFixed(1)}" width="${bw}" height="${hi.toFixed(1)}" rx="3" fill="url(#gInc)"><title>${esc(d.label)} income ${fmtMoney(d.income)}</title></rect>`;
    bars += `<rect x="${(x+1.5).toFixed(1)}" y="${(padT+ih-hs).toFixed(1)}" width="${bw}" height="${hs.toFixed(1)}" rx="3" fill="url(#gSpend)"><title>${esc(d.label)} spending ${fmtMoney(d.spend)}</title></rect>`;
    labels += `<text x="${x.toFixed(1)}" y="${H-8}" text-anchor="middle" class="ax-label">${esc(d.label)}</text>`;
  });
  let grid = "";
  for (let g = 0; g <= 4; g++) {
    const gy = padT + ih * g / 4;
    grid += `<line x1="${padL}" x2="${W-padR}" y1="${gy.toFixed(1)}" y2="${gy.toFixed(1)}" stroke="#888" stroke-opacity=".12"/>`;
    grid += `<text x="${padL-7}" y="${gy+4}" text-anchor="end" class="ax-label">${fmtMoney(maxV*(1-g/4),{compact:true})}</text>`;
  }
  const legend = opt.legend === false ? "" :
    `<div class="legend">
      <span class="legend-item"><i class="legend-dot" style="background:var(--green)"></i>Income</span>
      <span class="legend-item"><i class="legend-dot" style="background:var(--accent)"></i>Spending</span>
    </div>`;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">
    <defs>
      <linearGradient id="gInc" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--green)"/><stop offset="1" stop-color="var(--panel-2)"/></linearGradient>
      <linearGradient id="gSpend" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--accent)"/><stop offset="1" stop-color="var(--panel-2)"/></linearGradient>
    </defs>
    ${grid}${bars}${labels}</svg>` + legend;
}

/* ---------- line/area chart: net worth over time ---------- */
function lineChart(points, opt = {}) {
  const W = opt.width || 640, H = opt.height || 220;
  const padL = 52, padR = 12, padT = 14, padB = 24;
  const iw = W - padL - padR, ih = H - padT - padB;
  if (!points.length) return "<div class='empty'>No data yet</div>";
  const vals = points.map(p => p.v);
  let min = Math.min(...vals), max = Math.max(...vals);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.08; min -= pad; max += pad;
  const X = i => padL + (points.length === 1 ? iw/2 : iw * i / (points.length - 1));
  const Y = v => padT + ih * (1 - (v - min) / (max - min));
  const dLine = points.map((p,i) => `${i?"L":"M"}${X(i).toFixed(1)},${Y(p.v).toFixed(1)}`).join(" ");
  const area = `${dLine} L${X(points.length-1).toFixed(1)},${(padT+ih).toFixed(1)} L${X(0).toFixed(1)},${(padT+ih).toFixed(1)} Z`;
  let grid = "";
  for (let g = 0; g <= 3; g++) {
    const gy = padT + ih*g/3;
    grid += `<line x1="${padL}" x2="${W-padR}" y1="${gy.toFixed(1)}" y2="${gy.toFixed(1)}" stroke="#888" stroke-opacity=".12"/>`;
    grid += `<text x="${padL-7}" y="${gy+4}" text-anchor="end" class="ax-label">${fmtMoney(max-(max-min)*g/3,{compact:true})}</text>`;
  }
  // x labels: ~6 evenly spaced
  let xlabels = "";
  const nl = Math.min(6, points.length);
  for (let k = 0; k < nl; k++) {
    const i = Math.round(k*(points.length-1)/Math.max(nl-1,1));
    xlabels += `<text x="${X(i).toFixed(1)}" y="${H-6}" text-anchor="middle" class="ax-label">${esc(points[i].label)}</text>`;
  }
  const dots = points.map((p,i)=>`<circle cx="${X(i).toFixed(1)}" cy="${Y(p.v).toFixed(1)}" r="2.6" fill="var(--cyan)"><title>${esc(p.label)}: ${fmtMoney(p.v)}</title></circle>`).join("");
  const last = points[points.length-1];
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">
    <defs><linearGradient id="gArea" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--cyan)" stop-opacity=".24"/><stop offset="1" stop-color="var(--cyan)" stop-opacity="0"/></linearGradient></defs>
    ${grid}
    <path d="${area}" fill="url(#gArea)"/>
    <path d="${dLine}" fill="none" stroke="var(--cyan)" stroke-width="2.2" stroke-linejoin="round"/>
    ${dots}${xlabels}</svg>
    <div class="row-between small muted"><span>${opt.leftLabel||""}</span><b style="color:var(--text)">now: ${fmtMoney(last.v)}</b></div>`;
}

/* ---------- donut: category share ---------- */
function donutChart(rows, opt = {}) {
  rows = rows.filter(r => r.amt > 0).slice(0, opt.max || 8);
  if (!rows.length) return "<div class='empty'>No data yet</div>";
  const total = rows.reduce((s,r)=>s+r.amt, 0);
  const R = 60, CX = 80, CY = 80, SW = 20;
  const C = 2*Math.PI*R;
  let off = 0, segs = "";
  rows.forEach((r,i)=>{
    const frac = r.amt/total, len = frac*C;
    const col = CHART_COLORS[i % CHART_COLORS.length];
    segs += `<circle cx="${CX}" cy="${CY}" r="${R}" fill="none" stroke="${col}" stroke-width="${SW}"
      stroke-dasharray="${len.toFixed(2)} ${(C-len).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}"
      transform="rotate(-90 ${CX} ${CY})"><title>${esc(r.name)}: ${fmtMoney(r.amt)} (${r.pct}%)</title></circle>`;
    off += len;
  });
  const legend = rows.map((r,i)=>`<span class="legend-item"><i class="legend-dot" style="background:${CHART_COLORS[i%CHART_COLORS.length]}"></i>${esc(r.name)} · ${r.pct}%</span>`).join("");
  const centerLabel = opt.centerLabel ?? fmtMoney(total, {compact:true});
  return `<div class="donut-wrap">
    <svg viewBox="0 0 160 160" style="max-width:170px;width:100%">
      ${segs}
      <text x="${CX}" y="76" text-anchor="middle" class="donut-num">${centerLabel}</text>
      <text x="${CX}" y="92" text-anchor="middle" class="ax-label">total</text>
    </svg>
    <div class="donut-legend legend" style="flex-direction:column;align-items:flex-start;gap:6px">${legend}</div>
  </div>`;
}

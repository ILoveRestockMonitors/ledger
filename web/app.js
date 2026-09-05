/* Ledger SPA — core: API client, state, router, money pages. */

const state = {
  page: "overview",
  categories: [],
  accounts: [],
  txFilters: { scope: "", search: "", category_id: "", since: "", until: "" },
  theme: localStorage.getItem("ledger-theme") || "dark",
};

async function api(path, opts = {}) {
  const { body, ...rest } = opts;
  const payload = body === undefined || body === null ? undefined
    : typeof body === "string" ? body            // already serialized
    : JSON.stringify(body);                      // plain object
  const res = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json", "X-Ledger-Request": "1" },
    ...rest,
    body: payload,
  });
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || `HTTP ${res.status}`);
  return data;
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function statCard(label, value, opts = {}) {
  let delta = "";
  if (opts.delta !== undefined && opts.delta !== null) {
    const up = opts.delta >= 0;
    delta = `<div class="stat-delta ${up ? "delta-up" : "delta-down"}">${up ? "▲" : "▼"} ${opts.deltaLabel || ""}</div>`;
  }
  return `<div class="card ${opts.tint ? "tint-" + opts.tint : ""}">
    <div class="stat-label">${esc(label)}</div>
    <div class="stat-value" style="${opts.color ? "color:" + opts.color : ""}">${value}</div>
    ${delta}
    ${opts.sub ? `<div class="small muted mt" style="margin-top:4px">${opts.sub}</div>` : ""}
  </div>`;
}

function scopeTag(scope) {
  return scope === "business"
    ? `<span class="tag tag-biz">Business</span>`
    : `<span class="tag tag-per">Personal</span>`;
}

function catOptions(selectedId, kind = "") {
  const cats = state.categories.filter(c => !kind || c.kind === kind);
  return `<option value="">—</option>` + cats.map(c =>
    `<option value="${c.id}" ${c.id === selectedId ? "selected" : ""}>${c.icon} ${esc(c.name)}</option>`).join("");
}

/* ================= pages registry & router ================= */
const PAGES = {};
function registerPage(id, title, render) { PAGES[id] = { title, render }; }

async function navigate(page) {
  if (!PAGES[page]) page = "overview";
  state.page = page;
  setPill(null);
  document.querySelectorAll(".nav-link").forEach(a => a.classList.toggle("active", a.dataset.page === page));
  document.getElementById("page-title").textContent = PAGES[page].title;
  location.hash = page;
  document.body.classList.remove("nav-open");
  const token = state.renderToken = (state.renderToken || 0) + 1;
  const view = document.getElementById("view");
  view.innerHTML = `<div class="empty">Loading…</div>`;
  try {
    const html = await PAGES[page].render();
    if (state.renderToken !== token) return;
    view.innerHTML = html;
    document.querySelectorAll(".nav-link").forEach(a => a.setAttribute("aria-current", a.dataset.page === page ? "page" : "false"));
  } catch (e) {
    if (state.renderToken !== token) return;
    view.innerHTML = `<div class="empty"><div class="big">⚠️</div>${esc(e.message)}</div>`;
  }
  window.scrollTo(0, 0);
}

document.getElementById("nav").addEventListener("click", e => {
  const a = e.target.closest(".nav-link");
  if (a) { e.preventDefault(); navigate(a.dataset.page); }
});

/* ================= Overview ================= */
registerPage("overview", "Overview", async () => {
  const [ov, nw, cf, cats, budgets, goals, recent] = await Promise.all([
    api("/summary/overview"),
    api("/summary/networth?months=12"),
    api("/summary/cashflow?months=8"),
    api("/summary/categories?days=90&kind=expense"),
    api("/budgets"),
    api("/goals"),
    api("/transactions?limit=7"),
  ]);
  const netDelta = ov.net_this_month - ov.prev_net;
  const topBudgets = budgets.slice(0, 5);
  return `
  <div class="grid cols-4">
    ${statCard("Net worth", fmtMoney(ov.net_worth), { sub: "all linked accounts" })}
    ${statCard("Income this month", fmtMoney(ov.income_this_month), { color: "var(--green)" })}
    ${statCard("Spending this month", fmtMoney(ov.spend_this_month))}
    ${statCard("Saved this month", fmtMoney(ov.net_this_month), {
      color: ov.net_this_month >= 0 ? "var(--green)" : "var(--red)",
      delta: netDelta, deltaLabel: `${fmtMoney(Math.abs(netDelta))} vs last month`,
      sub: ov.savings_rate != null ? `${Math.round(ov.savings_rate*100)}% savings rate` : "",
    })}
  </div>

  <div class="grid cols-3 mt">
    <div class="card" style="grid-column: span 2">
      <h3>Cashflow <span class="h3-extra">last 8 months</span></h3>
      ${barChart(cf)}
    </div>
    <div class="card">
      <h3>Spending mix <span class="h3-extra">90 days</span></h3>
      ${donutChart(cats)}
    </div>
  </div>

  <div class="grid cols-3 mt">
    <div class="card" style="grid-column: span 2">
      <h3>Net worth trend</h3>
      ${lineChart(nw.map(p => ({ label: p.month, v: p.balance })))}
    </div>
    <div class="card">
      <h3>Budget watchlist</h3>
      ${topBudgets.length ? topBudgets.map(b => `
        <div class="mb" style="margin-bottom:11px">
          <div class="row-between small"><span>${b.cat_icon||""} ${esc(b.cat_name)} · ${scopeTag(b.scope)}</span>
          <span class="${b.pct>100?"amt-pos":""}" style="${b.pct>100?"color:var(--red)":"color:var(--muted)"}">${b.pct}%</span></div>
          <div class="bar ${b.pct>=100?"over":b.pct>=80?"warn":""}"><i style="width:${Math.min(b.pct,100)}%"></i></div>
        </div>`).join("") : `<div class="small muted">No budgets yet — create some on the Budgets page.</div>`}
      <a class="btn btn-ghost btn-sm mt" style="display:inline-block;margin-top:10px" onclick="navigate('budgets')">Manage budgets →</a>
    </div>
  </div>

  <div class="grid cols-3 mt">
    <div class="card" style="grid-column: span 2">
      <h3>Recent transactions</h3>
      <div class="table-wrap"><table class="tbl">
        ${recent.rows.map(t => `<tr>
          <td class="muted small" style="white-space:nowrap">${fmtDate(t.posted)}</td>
          <td>${t.cat_icon ? t.cat_icon + " " : ""}<b>${esc(t.merchant || t.name)}</b></td>
          <td>${scopeTag(t.scope)}</td>
          <td class="num ${t.amount>0?"amt-pos":""}">${fmtMoney(t.amount,{decimals:2})}</td>
        </tr>`).join("") || `<tr><td colspan="4" class="muted">No transactions yet — load demo data in Settings.</td></tr>`}
      </table></div>
      <a class="btn btn-ghost btn-sm" style="display:inline-block;margin-top:10px" onclick="navigate('transactions')">All transactions →</a>
    </div>
    <div class="card">
      <h3>Goals</h3>
      ${goals.slice(0,3).map(g => `
        <div style="margin-bottom:12px">
          <div class="row-between small"><span>${esc(g.name)}</span><span class="muted">${g.pct}%</span></div>
          <div class="bar green"><i style="width:${g.pct}%"></i></div>
        </div>`).join("") || `<div class="small muted">No goals yet.</div>`}
      <a class="btn btn-ghost btn-sm" style="display:inline-block;margin-top:10px" onclick="navigate('goals')">All goals →</a>
    </div>
  </div>`;
});

/* recent transactions are fetched separately so overview paints fast */
document.addEventListener("navigate-done", () => {});

/* ================= Business page ================= */
registerPage("business", "Business", async () => {
  setPill("Business");
  const [biz, cf] = await Promise.all([
    api("/business/summary"),
    api("/summary/cashflow?months=8&scope=business"),
  ]);
  const ov = biz.overview;
  const dedCats = biz.expense_categories_12mo.filter(c => c.td);
  return `
  <div class="grid cols-4">
    ${statCard("Revenue TTM", fmtMoney(biz.income_sources_12mo.reduce((s,r)=>s+r.amt,0)), { color: "var(--green)", tint: "biz" })}
    ${statCard("Expenses TTM", fmtMoney(biz.expense_categories_12mo.reduce((s,c)=>s+c.amt,0)), { tint: "biz" })}
    ${statCard("Profit TTM", fmtMoney(biz.profit_ttm), { color: biz.profit_ttm >= 0 ? "var(--green)" : "var(--red)", tint: "biz" })}
    ${statCard("Est. tax set-aside", fmtMoney(biz.estimated_tax_setaside), {
      tint: "biz", sub: "at your configured rate — Settings", color: "var(--amber)" })}
  </div>

  <div class="grid cols-3 mt">
    <div class="card" style="grid-column: span 2">
      <h3>Revenue vs expenses <span class="h3-extra">business accounts only</span></h3>
      ${barChart(cf)}
    </div>
    <div class="card">
      <h3>Deductible spend <span class="h3-extra">TTM</span></h3>
      <div class="stat-value" style="font-size:22px;color:var(--amber)">${fmtMoney(biz.deductible_12mo)}</div>
      <div class="small muted mb" style="margin-bottom:10px">across ${dedCats.length} deductible categories</div>
      ${dedCats.slice(0,6).map(c => `
        <div class="row-between small" style="padding:3px 0">
          <span>${esc(c.name)}</span><b>${fmtMoney(c.amt)}</b></div>`).join("")}
    </div>
  </div>

  <div class="grid cols-2 mt">
    <div class="card">
      <h3>Top clients / income sources <span class="h3-extra">TTM</span></h3>
      <div class="table-wrap"><table class="tbl">
        <tr><th>Source</th><th class="num">Payments</th><th class="num">Total</th></tr>
        ${biz.top_clients.map(c => `<tr>
          <td><div class="cat-chip">🏢 ${esc(c.name)}</div></td>
          <td class="num muted">${c.n}</td>
          <td class="num amt-pos">${fmtMoney(c.amt)}</td></tr>`).join("") ||
          `<tr><td colspan="3" class="muted">No business income recorded yet.</td></tr>`}
      </table></div>
    </div>
    <div class="card">
      <h3>Expense breakdown <span class="h3-extra">12 months</span></h3>
      ${donutChart(biz.expense_categories_12mo, { centerLabel: fmtMoney(biz.expense_categories_12mo.reduce((s,c)=>s+c.amt,0),{compact:true}) })}
    </div>
  </div>`;
});

/* ================= Personal page ================= */
registerPage("personal", "Personal", async () => {
  setPill("Personal");
  const [ov, cf, cats, subs, heat] = await Promise.all([
    api("/summary/overview?scope=personal"),
    api("/summary/cashflow?months=8&scope=personal"),
    api("/summary/categories?scope=personal&days=90&kind=expense"),
    api("/subscriptions"),
    api("/summary/heatmap?scope=personal"),
  ]);
  return `
  <div class="grid cols-4">
    ${statCard("Household net worth", fmtMoney(ov.net_worth), { tint: "per" })}
    ${statCard("Income this month", fmtMoney(ov.income_this_month), { color: "var(--green)", tint: "per" })}
    ${statCard("Spending this month", fmtMoney(ov.spend_this_month), { tint: "per" })}
    ${statCard("Runway", ov.runway_months ? ov.runway_months + " mo" : "—", {
      tint: "per", sub: "months your cash covers current spending" })}
  </div>

  <div class="grid cols-3 mt">
    <div class="card" style="grid-column: span 2">
      <h3>Personal cashflow <span class="h3-extra">last 8 months</span></h3>
      ${barChart(cf)}
    </div>
    <div class="card">
      <h3>Where it goes <span class="h3-extra">90 days</span></h3>
      ${donutChart(cats)}
    </div>
  </div>

  <div class="grid cols-2 mt">
    <div class="card">
      <h3>Daily spend heatmap <span class="h3-extra">personal accounts</span></h3>
      ${heatMap(heat)}
    </div>
    <div class="card">
      <h3>Subscriptions detected</h3>
      <div class="subs-total">${fmtMoney(subs.personal_monthly)}<span class="small muted" style="font-size:13px;font-weight:400">/mo personal</span></div>
      <div class="small muted" style="margin-bottom:10px">+ ${fmtMoney(subs.business_monthly)}/mo on the business side</div>
      ${(subs.items||[]).filter(s=>s.scope==="personal").slice(0,7).map(s=>`
        <div class="row-between small" style="padding:4px 0;border-bottom:1px solid var(--border-soft)">
          <span>${esc(s.merchant)}</span><b>${fmtMoney(s.monthly_cost)}/mo</b></div>`).join("") ||
        `<div class="small muted">Nothing recurring detected yet.</div>`}
      <a class="btn btn-ghost btn-sm" style="display:inline-block;margin-top:10px" onclick="navigate('subscriptions')">See all →</a>
    </div>
  </div>`;
});

/* Calendar-year and lifetime spending reports live in reports.js. */

/* ---------- shared chrome helpers ---------- */
function setPill(scope) {
  const pill = document.getElementById("scope-pill");
  const s = (scope || "").toLowerCase();
  if (!s) { pill.className = "pill pill-hidden"; return; }
  pill.textContent = s === "business" ? "● Business view" : "● Personal view";
  pill.className = "pill " + (s === "business" ? "pill-biz" : "pill-per");
}

/* Spending history: calendar-year totals and all recorded purchases. */
function reportPreference(key) {
  try { return localStorage.getItem(key) || ""; } catch { return ""; }
}

function changeReportFilter(key, value) {
  try { localStorage.setItem(key, value); } catch {}
  navigate("reports");
}

function reportMonthLabel(month, long = false) {
  return new Date(month + "-01T12:00:00").toLocaleDateString("en-US", {
    month: long ? "long" : "short",
  });
}

function spendingMonths(report) {
  const peak = Math.max(1, ...report.months.map(month => month.spend));
  return `<ol class="spending-months" aria-label="Monthly spending in ${report.year}">
    ${report.months.map(month => {
      const current = month.month === report.as_of.slice(0, 7);
      const amount = fmtMoney(month.spend, {decimals: 2});
      return `<li class="spending-month ${month.is_future ? "is-future" : ""} ${current ? "is-current" : ""}">
        <span class="spending-month-label">${reportMonthLabel(month.month)}${current ? '<small>so far</small>' : ''}</span>
        <div class="spending-month-track" aria-hidden="true"><span style="height:${Math.max(0, Math.min(100, month.spend / peak * 100))}%"></span></div>
        <b>${month.is_future ? '—' : amount}</b>
        ${month.is_future ? '<small>Not yet</small>' : `<span class="report-sr-only">${month.transaction_count} recorded purchases</span>`}
      </li>`;
    }).join("")}
  </ol>`;
}

function spendingCategories(report) {
  if (!report.categories.length) {
    return `<p class="quiet-note">No spending recorded for ${report.year} in this view.</p>`;
  }
  return `<p class="quiet-note">Scroll across the table to compare all 12 months.</p>
    <div class="table-wrap report-table-wrap" role="region" aria-label="Spending by category and month" tabindex="0">
      <table class="tbl report-matrix">
        <caption class="report-sr-only">Recorded spending by category for ${report.year}</caption>
        <thead><tr><th scope="col">Category</th>${report.months.map(month => `<th scope="col" class="num">${reportMonthLabel(month.month)}</th>`).join("")}<th scope="col" class="num">Year total</th></tr></thead>
        <tbody><tr class="report-category-total"><th scope="row">All categories</th>${report.months.map(month => `<td class="num"><b>${month.is_future ? '—' : fmtMoney(month.spend, {decimals: 2})}</b></td>`).join("")}<td class="num"><b>${fmtMoney(report.year_total, {decimals: 2})}</b></td></tr>${report.categories.map(category => `<tr>
          <th scope="row">${esc(category.name)}</th>
          ${category.months.map((amount, index) => `<td class="num">${report.months[index].is_future ? '—' : fmtMoney(amount, {decimals: 2})}</td>`).join("")}
          <td class="num"><b>${fmtMoney(category.total, {decimals: 2})}</b></td>
        </tr>`).join("")}</tbody>
      </table>
    </div>`;
}

registerPage("reports", "Reports", async () => {
  const savedScope = reportPreference("reports-scope");
  const scope = ["personal", "business"].includes(savedScope) ? savedScope : "";
  const savedYear = reportPreference("reports-year");
  const params = new URLSearchParams();
  if (scope) params.set("scope", scope);
  if (/^\d{4}$/.test(savedYear) && Number(savedYear) >= 1900 && Number(savedYear) <= new Date().getFullYear()) params.set("year", savedYear);
  const scopeQuery = scope ? "&scope=" + scope : "";
  const [report, heat, catsIn, catsOut] = await Promise.all([
    api("/reports/spending?" + params),
    api("/summary/heatmap" + (scope ? "?scope=" + scope : "")),
    api("/summary/categories?kind=income&days=180" + scopeQuery),
    api("/summary/categories?kind=expense&days=180" + scopeQuery),
  ]);
  const currentYear = Number(report.as_of.slice(0, 4));
  const scopeName = scope === "personal" ? "Personal accounts" : scope === "business" ? "Business accounts" : "All accounts";
  const periodLabel = report.year === currentYear ? `${report.year} spending so far` : `${report.year} spending`;
  const yearDates = report.year === currentYear ? `Jan 1 – ${fmtDate(report.as_of)}` : `Jan 1 – Dec 31, ${report.year}`;
  const historyNote = report.first_recorded_date ? `Recorded since ${fmtDate(report.first_recorded_date)}` : "No spending recorded yet";
  return `<div class="spending-report">
    <div class="page-intro"><div><h2>A wider view of your spending.</h2><p>Your months together, with the bigger picture in reach.</p></div></div>
    <div class="report-filters">
      <label for="rep-year">Year<select class="input" id="rep-year" onchange="changeReportFilter('reports-year', this.value)">${report.available_years.map(year => `<option value="${year}" ${year === report.year ? 'selected' : ''}>${year}${year === currentYear ? ' · so far' : ''}</option>`).join("")}</select></label>
      <label for="rep-scope">Accounts<select class="input" id="rep-scope" onchange="changeReportFilter('reports-scope', this.value)">
        <option value="" ${!scope ? 'selected' : ''}>All accounts</option><option value="personal" ${scope === 'personal' ? 'selected' : ''}>Personal only</option><option value="business" ${scope === 'business' ? 'selected' : ''}>Business only</option>
      </select></label>
      <button class="btn btn-sm btn-ghost report-export" onclick="exportCSV()">Export all transactions CSV</button>
    </div>
    <section class="card report-totals" aria-label="Spending totals">
      <div><div class="stat-label">${periodLabel}</div><div class="stat-value report-year-total">${fmtMoney(report.year_total, {decimals: 2})}</div><p class="small muted">${yearDates}</p></div>
      <div><div class="stat-label">All-time spending</div><div class="stat-value report-all-time-total">${fmtMoney(report.all_time_total, {decimals: 2})}</div><p class="small muted">${historyNote}</p></div>
    </section>
    <section class="card report-month-card"><h3>Month by month <span class="h3-extra">${report.year} · ${scopeName}</span></h3>
      ${spendingMonths(report)}
      <p class="quiet-note">$0 means no spending recorded. Future months are left blank.</p>
    </section>
    <p class="quiet-note report-basis">Recorded purchases, including archived accounts. Pending charges and transfers are excluded; income and refunds aren’t subtracted. All-time covers the history stored in Ledger.</p>
    <details class="card report-detail"><summary>Spending by category <span>${report.year}</span></summary>${spendingCategories(report)}</details>
    <details class="card report-detail"><summary>Recent patterns <span>Rolling periods</span></summary>
      <p class="quiet-note">These recent views follow the account filter, independently of the selected calendar year.</p>
      <div class="grid cols-2 report-patterns">
        <section><h3>Spend heatmap <span class="h3-extra">Last 26 weeks</span></h3>${heatMap(heat)}</section>
        <section><h3>Income sources <span class="h3-extra">Last 180 days</span></h3>
          ${catsIn.length ? catsIn.map(row => `<div class="row-between small report-source"><span>${esc(row.icon || '')} ${esc(row.name)}</span><span class="report-source-values"><b>${fmtMoney(row.amt, {decimals: 2})}</b><small>${row.n} payments</small></span></div>`).join("") : '<p class="quiet-note">No income recorded in this period.</p>'}
          <h3 class="report-expense-heading">Top expense categories <span class="h3-extra">Last 180 days</span></h3>
          ${catsOut.slice(0, 8).map(row => `<div class="row-between small report-source"><span>${esc(row.icon || '')} ${esc(row.name)}</span><span class="report-source-values"><b>${fmtMoney(row.amt, {decimals: 2})}</b><small>${row.pct}% of spending</small></span></div>`).join("") || '<p class="quiet-note">No spending recorded in this period.</p>'}
        </section>
      </div>
    </details>
  </div>`;
});

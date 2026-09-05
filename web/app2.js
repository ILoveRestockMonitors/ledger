/* Ledger SPA — part 2: transactions, budgets, goals, subs, accounts, settings,
   Plaid Link flow with business/personal classification, boot. */

/* ================= Transactions ================= */
registerPage("transactions", "Transactions", async () => {
  setPill(null);
  const f = state.txFilters;
  const q = new URLSearchParams(Object.entries(f).filter(([,v])=>v)).toString();
  const [data, receipts] = await Promise.all([api("/transactions?" + q), api("/receipts")]);
  receiptState.summary = receipts;
  return `
  <div class="filter-row transaction-filters" role="search" aria-label="Transaction filters">
    <input class="input" id="tx-search" aria-label="Search transactions" placeholder="🔍 Search merchant, note…" value="${esc(f.search)}"
      onkeydown="if(event.key==='Enter'){state.txFilters.search=this.value;state.txFilters.offset=0;navigate('transactions')}">
    <select class="input" onchange="state.txFilters.scope=this.value;state.txFilters.offset=0;navigate('transactions')">
      <option value="">All scopes</option>
      <option value="business" ${f.scope==="business"?"selected":""}>💼 Business</option>
      <option value="personal" ${f.scope==="personal"?"selected":""}>🏠 Personal</option>
    </select>
    <select class="input" onchange="state.txFilters.category_id=this.value;state.txFilters.offset=0;navigate('transactions')">
      <option value="">All categories</option>
      ${state.categories.map(c=>`<option value="${c.id}" ${f.category_id===c.id?"selected":""}>${c.icon} ${esc(c.name)}</option>`).join("")}
    </select>
    <label class="transaction-date">From<input type="date" class="input" value="${esc(f.since)}" onchange="state.txFilters.since=this.value;state.txFilters.offset=0;navigate('transactions')"></label>
    <label class="transaction-date">To<input type="date" class="input" value="${esc(f.until)}" onchange="state.txFilters.until=this.value;state.txFilters.offset=0;navigate('transactions')"></label>
    <button class="btn btn-sm btn-ghost" onclick="state.txFilters={search:'',scope:'',category_id:'',since:'',until:'',offset:0};navigate('transactions')">Clear</button>
    <span class="small muted">${data.total} total</span>
  </div>

  ${receiptSummaryMarkup(receipts)}

  <div class="card">
    <div class="table-wrap"><table class="tbl">
      <tr><th>Date</th><th>Name</th><th>Account</th><th>Category</th><th>Scope</th><th class="num">Amount</th><th></th></tr>
      ${data.rows.map(t => `
        <tr>
          <td style="white-space:nowrap" class="muted">${fmtDate(t.posted)}</td>
          <td><b>${esc(t.display_name || t.merchant || t.name)}</b>${receiptOriginalName(t)}${t.note?`<div class="small muted">📝 ${esc(t.note)}</div>`:""}
              ${t.pending?'<span class="tag tag-rec">Pending</span>':''}${t.is_transfer?'<span class="tag tag-rec">Transfer</span>':''}${t.recurring?`<span class="tag tag-rec" title="recurring">↻</span>`:""}</td>
          <td class="muted small">${esc(t.acct_name||"—")}${t.acct_mask?` ••${t.acct_mask}`:""}</td>
          <td>${receiptCategoryCell(t)}</td>
          <td>
            <select class="cat-select" onchange="setTxScope(${esc(JSON.stringify(t.id))}, this.value)">
              <option value="personal" ${t.scope==="personal"?"selected":""}>🏠 Personal</option>
              <option value="business" ${t.scope==="business"?"selected":""}>💼 Business</option>
            </select>
          </td>
          <td class="num ${t.amount>0?"amt-pos":"amt-neg"+(t.scope==="business"?" biz-neg":"")}"
              style="${t.amount<0&&t.scope==="business"?"color:var(--accent)":""}">${t.amount>0?"+":""}${fmtMoney(t.amount,{decimals:2})}</td>
          <td><button class="btn btn-sm btn-ghost" title="Edit" onclick="openTxEdit(${esc(JSON.stringify(t.id))})">✏️</button>${t.receipt_provider && t.receipt_status !== "dismissed" ? receiptEditAction(t.id, t.receipt_status) : ""}</td>
        </tr>`).join("") || `<tr><td colspan="7" class="muted" style="text-align:center;padding:30px">
            No transactions match. Load demo data in Settings, or link an account.</td></tr>`}
    </table></div>
    <div class="row-between mt">
      <button class="btn btn-sm" ${data.offset>0?"":"disabled"} onclick="state.txFilters.offset=${Math.max(data.offset-data.limit,0)};navigate('transactions')">← Newer</button>
      <span class="small muted">showing ${data.rows.length} of ${data.total}</span>
      <button class="btn btn-sm" ${data.offset+data.limit<data.total?"":"disabled"} onclick="state.txFilters.offset=${data.offset+data.limit};navigate('transactions')">Older →</button>
    </div>
  </div>`;
});

async function setTxScope(id, scope) {
  await api("/transactions/update", { method: "POST", body: JSON.stringify({ id, scope }) });
  toast(`Marked as ${scope}`, "ok");
}

window.openTxEdit = async function (id) {
  const f = state.txFilters;
  const data = await api("/transactions?" + new URLSearchParams(Object.entries(f).filter(([,v])=>v && v!=="")).toString());
  const t = data.rows.find(r => r.id === id);
  if (!t) return toast("Transaction not found", "err");
  showModal(`
    <h2>Edit transaction</h2>
    <p class="sub">${esc(t.name)} · ${fmtDate(t.posted)} · ${fmtMoney(t.amount,{decimals:2})}</p>
    <label class="fld" for="txe-cat">Category</label>
    <select class="input" id="txe-cat" data-original-value="${esc(t.category_id || "")}">${catOptions(t.category_id)}</select>
    ${Array.isArray(t.allocations) && t.allocations.length ? `<div class="receipt-edit-context"><span class="micro-label">Current purchase split</span>${t.allocations.map(a => `<div class="receipt-edit-allocation"><span>${esc(a.description || "Purchase")}</span><span>${esc(a.cat_name || "Choose a budget")}</span><strong>${receiptMoney(a.amount_cents)}</strong></div>`).join("")}<p class="receipt-edit-warning">Changing Category applies to the whole charge and replaces this item split.</p></div>` : ""}
    <label class="fld" for="txe-scope">Scope</label>
    <select class="input" id="txe-scope">
      <option value="personal" ${t.scope==="personal"?"selected":""}>🏠 Personal</option>
      <option value="business" ${t.scope==="business"?"selected":""}>💼 Business</option>
    </select>
    <label class="fld" for="txe-note">Note</label>
    <input class="input" id="txe-note" value="${esc(t.note||"")}">
    <label class="fld row" style="gap:8px;margin-top:12px">
      <input type="checkbox" id="txe-rec" ${t.recurring?"checked":""} style="width:auto"> Mark as recurring
    </label>
    <label class="fld row" style="gap:8px"><input type="checkbox" id="txe-transfer" ${t.is_transfer?'checked':''}> Transfer between accounts</label>
    <div class="receipt-edit-cta">${receiptEditAction(t.id, t.receipt_status)}</div>
    <div class="modal-actions">
      <button class="btn btn-danger" onclick="deleteTx(${esc(JSON.stringify(t.id))})">Delete</button>
      <span style="flex:1"></span>
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveTxEdit(${esc(JSON.stringify(t.id))}, this)">Save</button>
    </div>`);
};
function setPending(button, pending, label) {
  if (!button) return;
  if (pending) {
    if (button.dataset.pending === "1") return false;
    button.dataset.pending = "1";
    button.dataset.label = button.textContent;
    button.disabled = true;
    button.textContent = label || "Saving…";
  } else {
    button.disabled = false;
    button.textContent = button.dataset.label || button.textContent;
    delete button.dataset.pending;
    delete button.dataset.label;
  }
  return true;
}
async function saveTxEdit(id, button) {
  if (button?.dataset.pending === "1") return;
  const category = document.getElementById("txe-cat");
  const body = {
    id,
    scope: document.getElementById("txe-scope").value,
    note: document.getElementById("txe-note").value,
    recurring: document.getElementById("txe-rec").checked,
    is_transfer: document.getElementById("txe-transfer").checked,
  };
  if (category.value !== (category.dataset.originalValue || "")) body.category_id = category.value || null;
  if (!setPending(button, true, "Saving…")) return;
  try {
    await api("/transactions/update", { method: "POST", body: JSON.stringify(body) });
    closeModal(); toast("Saved", "ok"); navigate(state.page);
  } catch (e) {
    toast(e.message || "Could not save this transaction. Try again.", "err");
  } finally { setPending(button, false); }
}
async function deleteTx(id) {
  if (!confirm("Delete this transaction?")) return;
  await api("/transactions?id=" + id, { method: "DELETE" });
  closeModal(); toast("Deleted", "ok"); navigate(state.page);
}

function openAddTx() {
  if (!state.accounts.length) return toast("Add an account first (Accounts →)", "err");
  showModal(`
    <h2>Add transaction</h2>
    <label class="fld" for="addtx-acct">Account</label>
    <select class="input" id="addtx-acct">${state.accounts.map(a=>
      `<option value="${a.id}" data-scope="${a.scope}">${esc(a.name)} (${a.scope[0].toUpperCase()})</option>`).join("")}</select>
    <label class="fld" for="addtx-amt">Amount <span class="muted">(negative = expense, positive = income)</span></label>
    <input class="input" id="addtx-amt" type="number" step="0.01" placeholder="-24.50">
    <label class="fld" for="addtx-name">Name / merchant</label>
    <input class="input" id="addtx-name" placeholder="Coffee shop">
    <label class="fld" for="addtx-date">Date</label>
    <input class="input" id="addtx-date" type="date" value="${new Date().toISOString().slice(0,10)}">
    <label class="fld" for="addtx-cat">Category</label>
    <select class="input" id="addtx-cat"><option value="">—</option>
      ${state.categories.map(c=>`<option value="${c.id}">${c.icon} ${esc(c.name)}</option>`).join("")}</select>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveAddTx(this)">Add</button>
    </div>`);
}
async function saveAddTx(button) {
  if (button?.dataset.pending === "1") return;
  const acctSel = document.getElementById("addtx-acct");
  const body = {
    transaction: {
      account_id: acctSel.value,
      scope: acctSel.selectedOptions[0].dataset.scope,
      amount: parseFloat(document.getElementById("addtx-amt").value || "0"),
      name: document.getElementById("addtx-name").value || "Manual entry",
      posted: document.getElementById("addtx-date").value,
      category_id: document.getElementById("addtx-cat").value || null,
    },
  };
  if (!body.transaction.amount) return toast("Enter an amount", "err");
  if (!setPending(button, true, "Adding…")) return;
  try {
    await api("/transactions", { method: "POST", body: JSON.stringify(body) });
    closeModal(); toast("Added", "ok"); navigate(state.page);
  } catch (e) {
    toast(e.message || "Could not add this transaction. Try again.", "err");
  } finally { setPending(button, false); }
}

/* ================= Budgets ================= */
registerPage("budgets", "Budgets", async () => {
  setPill(null);
  const budgets = await api("/budgets");
  const groups = {
    business: budgets.filter(b => b.scope === "business"),
    personal: budgets.filter(b => b.scope === "personal"),
    all: budgets.filter(b => b.scope === "all"),
  };
  const card = b => `
    <div class="card ${b.scope==="business"?"tint-biz":b.scope==="personal"?"tint-per":""}">
      <div class="row-between">
        <b>${b.cat_icon||"◎"} ${esc(b.cat_name)} ${scopeTag(b.scope)}</b>
        <button class="btn btn-sm btn-ghost" onclick="deleteBudget(${esc(JSON.stringify(b.id))})">✕</button>
      </div>
      <div class="row-between small muted" style="margin:8px 0 6px">
        <span>${fmtMoney(b.spent)} spent</span><span>of ${fmtMoney(b.month_limit)}</span>
      </div>
      <div class="bar ${b.pct>=100?"over":b.pct>=80?"warn":""}"><i style="width:${Math.min(b.pct,100)}%"></i></div>
      <div class="row-between small mt" style="margin-top:8px">
        <span class="${b.remaining<0?"":"muted"}" style="${b.remaining<0?"color:var(--red);font-weight:700":""}">
          ${b.remaining<0 ? fmtMoney(-b.remaining)+" over" : fmtMoney(b.remaining)+" left"}</span>
        <span class="muted">${b.pct}%</span>
      </div>
    </div>`;
  const section = (title, arr, tint) => arr.length ? `
    <div class="section-title">${title}</div>
    <div class="grid cols-3">${arr.map(card).join("")}</div>` : "";
  return `
  <div class="row-between mb" style="margin-bottom:14px">
    <span class="muted small">Monthly envelopes reset automatically each calendar month.</span>
    <button class="btn btn-primary btn-sm" onclick="openBudgetForm()">+ New budget</button>
  </div>
  ${section("💼 Business budgets", groups.business)}
  ${section("🏠 Personal budgets", groups.personal)}
  ${section("◎ Combined budgets", groups.all)}
  ${!budgets.length ? `<div class="empty"><div class="big">◎</div>No budgets yet.<br><br>
     <button class="btn btn-primary" onclick="openBudgetForm()">Create your first budget</button></div>` : ""}`;
});
function openBudgetForm() {
  showModal(`
    <h2>New budget</h2>
    <label class="fld" for="bud-cat">Category</label>
    <select class="input" id="bud-cat">${state.categories.filter(c=>c.kind==="expense")
      .map(c=>`<option value="${c.id}">${c.icon} ${esc(c.name)}</option>`).join("")}</select>
    <label class="fld" for="bud-scope">Applies to</label>
    <select class="input" id="bud-scope">
      <option value="personal">🏠 Personal spending in this category</option>
      <option value="business">💼 Business spending in this category</option>
      <option value="all">◎ Both combined</option>
    </select>
    <label class="fld" for="bud-limit">Monthly limit ($)</label>
    <input class="input" id="bud-limit" type="number" step="1" min="1" placeholder="300">
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveBudget(this)">Create budget</button>
    </div>`);
}
async function saveBudget(button) {
  if (button?.dataset.pending === "1") return;
  const body = {
    category_id: document.getElementById("bud-cat").value,
    scope: document.getElementById("bud-scope").value,
    month_limit: parseFloat(document.getElementById("bud-limit").value || "0"),
  };
  if (!body.month_limit) return toast("Set a monthly limit", "err");
  if (!setPending(button, true, "Creating…")) return;
  try {
    await api("/budgets", { method: "POST", body: JSON.stringify(body) });
    closeModal(); toast("Budget created", "ok"); navigate("budgets");
  } catch (e) {
    toast(e.message || "Could not create this budget. Try again.", "err");
  } finally { setPending(button, false); }
}
async function deleteBudget(id) {
  if (!confirm("Delete this budget?")) return;
  await api("/budgets?id=" + id, { method: "DELETE" }); navigate("budgets");
}

/* ================= Goals ================= */
registerPage("goals", "Goals", async () => {
  setPill(null);
  const goals = await api("/goals");
  const gcard = g => `
    <div class="card ${g.scope==="business"?"tint-biz":"tint-per"}">
      <div class="goal-head">
        <b>${g.completed_at ? "🏆 " : ""}${esc(g.name)} ${scopeTag(g.scope)}</b>
        <button class="btn btn-sm btn-ghost" onclick="deleteGoal(${esc(JSON.stringify(g.id))})">✕</button>
      </div>
      <div class="bar green"><i style="width:${g.pct}%"></i></div>
      <div class="row-between small mt" style="margin-top:8px">
        <span><b>${fmtMoney(g.saved)}</b> <span class="muted">of ${fmtMoney(g.target)}</span></span>
        <span class="muted">${g.pct}%${g.on_track===false?" · ⚠ behind":""}</span>
      </div>
      <div class="goal-meta">
        ${g.target_date ? `<span>🎯 by ${fmtDate(g.target_date)}</span>` : ""}
        ${g.eta ? `<span>📈 projected ${fmtDate(g.eta)}</span>` : (g.remaining<=0?"":"")}
        ${g.monthly_plan ? `<span>$${g.monthly_plan}/mo planned</span>` : ""}
      </div>
      ${g.remaining > 0 ? `<button class="btn btn-sm mt" style="margin-top:10px" onclick="contribute(${esc(JSON.stringify(g.id))}, ${esc(JSON.stringify(g.name))}, ${g.remaining})">＋ Contribute</button>` :
        `<div class="small mt" style="margin-top:10px;color:var(--green)">Complete 🎉</div>`}
    </div>`;
  return `
  <div class="row-between" style="margin-bottom:14px">
    <span class="muted small">Savings goals with automatic projected completion dates.</span>
    <button class="btn btn-primary btn-sm" onclick="openGoalForm()">+ New goal</button>
  </div>
  <div class="grid cols-3">${goals.map(gcard).join("") ||
    `<div class="empty" style="grid-column:1/-1"><div class="big">▲</div>No goals yet.<br><br>
     <button class="btn btn-primary" onclick="openGoalForm()">Create your first goal</button></div>`}</div>`;
});
function openGoalForm() {
  showModal(`
    <h2>New savings goal</h2>
    <label class="fld" for="g-name">Name</label>
    <input class="input" id="g-name" placeholder="Emergency fund">
    <div class="grid cols-2" style="gap:10px">
      <div><label class="fld" for="g-target">Target ($)</label><input class="input" id="g-target" type="number" step="1"></div>
      <div><label class="fld" for="g-saved">Already saved ($)</label><input class="input" id="g-saved" type="number" step="1" value="0"></div>
    </div>
    <div class="grid cols-2" style="gap:10px">
      <div><label class="fld" for="g-plan">Monthly plan ($)</label><input class="input" id="g-plan" type="number" step="1" value="100"></div>
      <div><label class="fld" for="g-date">Target date</label><input class="input" id="g-date" type="date"></div>
    </div>
    <label class="fld" for="g-scope">Scope</label>
    <select class="input" id="g-scope"><option value="personal">🏠 Personal</option><option value="business">💼 Business</option></select>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveGoal(this)">Create goal</button>
    </div>`);
}
async function saveGoal(button) {
  if (button?.dataset.pending === "1") return;
  const body = {
    name: document.getElementById("g-name").value,
    target: parseFloat(document.getElementById("g-target").value || "0"),
    saved: parseFloat(document.getElementById("g-saved").value || "0"),
    monthly_plan: parseFloat(document.getElementById("g-plan").value || "0"),
    target_date: document.getElementById("g-date").value || null,
    scope: document.getElementById("g-scope").value,
  };
  if (!body.name || !body.target) return toast("Need a name and target", "err");
  if (!setPending(button, true, "Creating…")) return;
  try {
    await api("/goals", { method: "POST", body: JSON.stringify(body) });
    closeModal(); toast("Goal created", "ok"); navigate("goals");
  } catch (e) {
    toast(e.message || "Could not create this goal. Try again.", "err");
  } finally { setPending(button, false); }
}
function contribute(id, name, remaining) {
  showModal(`
    <h2>Contribute to “${esc(name)}”</h2>
    <p class="sub">${fmtMoney(remaining)} remaining</p>
    <label class="fld" for="c-amt">Amount ($)</label>
    <input class="input" id="c-amt" type="number" step="0.01" value="100">
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveContribution(${esc(JSON.stringify(id))}, this)">Add contribution</button>
    </div>`);
}
async function saveContribution(id, button) {
  if (button?.dataset.pending === "1") return;
  const amt = parseFloat(document.getElementById("c-amt").value || "0");
  if (!amt) return toast("Enter an amount", "err");
  if (!setPending(button, true, "Adding…")) return;
  try {
    const r = await api("/goals/contribute", { method: "POST", body: JSON.stringify({ id, amount: amt }) });
    closeModal(); toast(r.saved >= 0 ? "Contribution added — nice." : "Updated", "ok"); navigate("goals");
  } catch (e) {
    toast(e.message || "Could not add this contribution. Try again.", "err");
  } finally { setPending(button, false); }
}
async function deleteGoal(id) {
  if (!confirm("Delete this goal?")) return;
  await api("/goals?id=" + id, { method: "DELETE" }); navigate("goals");
}

/* ================= Subscriptions ================= */
registerPage("subscriptions", "Subscriptions", async () => {
  setPill(null);
  const s = await api("/subscriptions");
  const row = r => `<tr>
    <td><b>${esc(r.merchant)}</b></td>
    <td>${scopeTag(r.scope)}</td>
    <td class="num">${fmtMoney(r.monthly_cost,{decimals:2})}</td>
    <td class="num muted">${r.times}× over ${r.months_seen} mo</td></tr>`;
  return `
  <div class="grid cols-3">
    ${statCard("Personal recurring", fmtMoney(s.personal_monthly)+"/mo", { color:"var(--green)" })}
    ${statCard("Business recurring", fmtMoney(s.business_monthly)+"/mo", { color:"var(--accent)" })}
    ${statCard("Combined burn", fmtMoney(s.personal_monthly+s.business_monthly)+"/mo", { sub:"auto-detected from repeats" })}
  </div>
  <div class="card mt">
    <h3>Detected recurring payments <span class="h3-extra">≥3 months, similar amounts</span></h3>
    <div class="table-wrap"><table class="tbl">
      <tr><th>Merchant</th><th>Scope</th><th class="num">Monthly</th><th class="num">History</th></tr>
      ${(s.items||[]).map(row).join("") || `<tr><td colspan="4" class="muted" style="text-align:center;padding:26px">Nothing recurring detected yet.</td></tr>`}
    </table></div>
  </div>`;
});

/* ================= Accounts ================= */
registerPage("accounts", "Accounts", async () => {
  setPill(null);
  const [items, accounts] = await Promise.all([api("/items"), api("/accounts")]);
  const cfg = await api("/config");
  const acctCard = a => `
    <div class="card acct-card ${a.scope==="business"?"tint-biz":"tint-per"}">
      <div class="acct-name">
        <b>${esc(a.name)} ${a.mask?`<span class="muted small">••${a.mask}</span>`:""}</b>
        <span>${esc(a.subtype||a.type||"")} · ${esc(a.iso_currency)}</span>
      </div>
      <div class="row">
        <div class="acct-bal ${a.balance<0?"neg":""}">${fmtMoney(a.balance,{decimals:2})}</div>
        <button class="btn btn-sm ${a.scope==="business"?"":"btn-ghost"}" onclick="classifyAcct(${esc(JSON.stringify(a.id))},'business')">💼</button>
        <button class="btn btn-sm ${a.scope==="personal"?"":"btn-ghost"}" onclick="classifyAcct(${esc(JSON.stringify(a.id))},'personal')">🏠</button>
        <button class="btn btn-sm btn-ghost" onclick="archiveAcct(${esc(JSON.stringify(a.id))})" title="Archive">📦</button>
      </div>
    </div>`;
  return `
  <div class="card mb" style="margin-bottom:14px">
    <div class="row-between">
      <div>
        <b>Connect your bank</b>
        <div class="small muted">Plaid Link opens, you sign in once, then choose Business or Personal for the connection.</div>
      </div>
      <div class="row">
        <button class="btn btn-accent" onclick="startLinkFlow()">🔗 Link account</button>
        ${cfg.plaid_env==="sandbox" ? `<button class="btn" onclick="startSandboxFlow()" title="Creates a sandbox connection instantly">⚡ Sandbox quick-add</button>` : ""}
      </div>
    </div>
    ${!cfg.plaid_client_id ? `<div class="small muted" style="margin-top:8px;border-top:1px solid var(--border-soft);padding-top:8px">
      ⓘ No Plaid keys yet — add them in <a href="#" onclick="navigate('settings');return false" style="color:var(--accent)">Settings</a>,
      or explore with demo data.</div>` : ""}
  </div>

  ${items.map(it => `
    <div class="section-title">${esc(it.institution)}
      <span class="tag ${it.env_label==="demo"?"tag-rec":"tag-ded"}" style="margin-left:6px">${it.env_label}</span>
      <span class="small muted" style="font-weight:400">· ${it.n_accounts} account(s)</span>
      ${it.has_token ? `<button class="btn btn-sm btn-ghost" style="float:right" onclick="refreshItem(${esc(JSON.stringify(it.id))})">⟳ Sync now</button>
                        <button class="btn btn-sm btn-danger" style="float:right;margin-right:6px" onclick="unlinkItem(${esc(JSON.stringify(it.id))})">Unlink</button>` : ""}
    </div>
    <div class="grid cols-2">${accounts.filter(a => a.item_id === it.id).map(acctCard).join("") || `<div class="small muted">No accounts.</div>`}</div>
  `).join("")}
  ${!items.length ? `<div class="empty"><div class="big">🏦</div>No accounts connected yet.</div>` : ""}`;
});
async function classifyAcct(id, scope) {
  await api("/accounts/classify", { method: "POST", body: JSON.stringify({ id, scope }) });
  toast(`Account marked ${scope}. Its transactions moved too.`, "ok");
  navigate("accounts");
}
async function archiveAcct(id) {
  if (!confirm("Archive this account? It disappears from totals but keeps history.")) return;
  await api("/accounts/archive", { method: "POST", body: JSON.stringify({ id }) });
  navigate("accounts");
}
async function refreshItem(id) {
  try {
    const r = await api("/items/refresh", { method: "POST", body: JSON.stringify({ item_id: id }) });
    toast(`Synced — ${r.added} new transactions`, "ok");
    navigate("accounts");
  } catch (e) { toast(e.message, "err"); }
}
async function unlinkItem(id) {
  if (!confirm("Unlink this bank? All its accounts and transactions will be removed.")) return;
  await api("/items?id=" + id, { method: "DELETE" });
  toast("Unlinked", "ok"); navigate("accounts");
}

/* ================= Plaid Link flow ================= */
let plaidHandler = null;

async function startLinkFlow() {
  let cfg;
  try { cfg = await api("/config"); } catch (e) { toast(e.message, "err"); return; }
  if (!cfg.plaid_configured) {
    showModal(`
      <h2>Connect Plaid first</h2>
      <p class="sub">Add your Plaid credentials in Settings to connect a bank.</p>
      <ol class="small muted" style="padding-left:18px;line-height:1.7">
        <li>Open your account at <b>dashboard.plaid.com</b></li>
        <li>Copy your <code class="kbd">client_id</code> and <code class="kbd">secret</code></li>
        <li>Paste them in Settings → Bank connection settings and save. Choose <b>Production</b> for real banks; Sandbox is only for test data.</li>
        <li>Come back and hit Link account</li>
      </ol>
      <div class="modal-actions">
        <button class="btn" onclick="closeModal()">Later</button>
        <button class="btn btn-primary" onclick="closeModal();navigate('settings')">Open Settings</button>
      </div>`);
    return;
  }
  // OAuth return state lives in this origin's sessionStorage. Start on the
  // configured app address so the bank can return to the same session.
  if (cfg.plaid_redirect_uri) {
    const redirect = new URL(cfg.plaid_redirect_uri);
    if (redirect.origin !== location.origin) {
      showModal(`<h2>Connect from your Ledger address</h2>
        <p class="sub">Open your private Ledger address to connect a bank. This lets your bank return you to the same session afterward.</p>
        <div class="modal-actions"><button class="btn" onclick="closeModal()">Later</button>
        <a class="btn btn-primary" href="${esc(redirect.href)}">Open Ledger</a></div>`);
      return;
    }
  }
  askScopeThen(async scope => {
    try {
      toast("Opening Plaid Link…", "ok");
      const lt = await api("/plaid/link-token", { method: "POST", body: "{}" });
      await openPlaidLink(lt.link_token, scope);
    } catch (e) {
      showModal(`<h2>Bank connection needs a setup step</h2><p class="sub">${esc(e.message)}</p>
        <div class="modal-actions"><button class="btn" onclick="closeModal()">Close</button>
        <button class="btn btn-primary" onclick="closeModal();navigate('settings')">Bank settings</button></div>`);
    }
  });
}

function loadPlaidScript() {
  return new Promise((resolve, reject) => {
    if (window.Plaid) return resolve();
    const s = document.createElement("script");
    s.src = "https://cdn.plaid.com/link/v2/stable/link-initialize.js";
    s.onload = resolve; s.onerror = () => reject(new Error("Could not load Plaid Link (offline?)"));
    document.head.appendChild(s);
  });
}

async function openPlaidLink(linkToken, scope, receivedRedirectUri=null, updateItem=null) {
  await loadPlaidScript();
  sessionStorage.setItem('ledger-link',JSON.stringify({token:linkToken,scope,updateItem}));
  plaidHandler = window.Plaid.create({
    token:linkToken, ...(receivedRedirectUri?{receivedRedirectUri}:{}),
    onSuccess: async (public_token, metadata) => {
      try {
        if(!updateItem){
          const inst=metadata?.institution?.name||'Linked bank';
          await api('/plaid/exchange',{method:'POST',body:{public_token,institution:inst,scope,item_id:updateItem||null}});
          toast(`${inst} connected. Your bank is preparing the first transactions.`);
        } else { await api('/items/refresh',{method:'POST',body:{item_id:updateItem}}); toast('Your connection is refreshed.'); }
        sessionStorage.removeItem('ledger-link');
        history.replaceState(null,'',location.pathname+'#accounts');
        state.accounts=await api('/accounts');
        await navigate('accounts');
      } catch(e){toast(e.message,'err',6500);}
      finally{plaidHandler?.destroy();}
    },
    onExit: err=>{if(err)toast(err.display_message||'Your bank connection needs another try.','err');plaidHandler?.destroy();}
  });
  plaidHandler.open();
}

async function startSandboxFlow() {
  askScopeThen(async scope => {
    try {
      toast("Creating sandbox connection…", "ok");
      await api("/plaid/sandbox-full-link", { method: "POST",
        body: JSON.stringify({ scope, institution_name: "Sandbox Financial (First Platypus)" }) });
      toast("Sandbox bank linked as " + scope + " ✓ — use Sync now to pull transactions.", "ok", 6000);
      navigate("accounts");
    } catch (e) { toast(e.message, "err", 6000); }
  });
}

/* THE classification modal — business or personal, asked right after linking */
function askScopeThen(onChoice) {
  let chosen = null;
  showModal(`
    <h2>Business or Personal?</h2>
    <p class="sub">Choose how to treat every account under this bank connection. You can flip any single account later on the Accounts page.</p>
    <div class="scope-cards">
      <div class="scope-card" id="sc-biz" onclick="pickScope('business')">
        <div class="ic">💼</div><b>Business</b>
        <span>revenue, deductions, tax estimates</span>
      </div>
      <div class="scope-card" id="sc-per" onclick="pickScope('personal')">
        <div class="ic">🏠</div><b>Personal</b>
        <span>household cashflow & budgets</span>
      </div>
    </div>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" id="sc-go" disabled onclick="confirmScope()">Continue</button>
    </div>`);
  window.pickScope = s => {
    chosen = s;
    document.getElementById("sc-biz").className = "scope-card" + (s==="business" ? " sel-biz" : "");
    document.getElementById("sc-per").className = "scope-card" + (s==="personal" ? " sel-per" : "");
    document.getElementById("sc-go").disabled = false;
  };
  window.confirmScope = () => { closeModal(); onChoice(chosen); };
}

/* ================= Settings ================= */
registerPage("settings", "Settings", async () => {
  setPill(null);
  const cfg = await api("/config");
  const accounts = await api("/accounts");
  return `
  <div class="grid cols-2">
    <div class="card">
      <h3>Plaid API</h3>
      <label class="fld" for="cfg-cid">Client ID</label>
      <input class="input" id="cfg-cid" value="${esc(cfg.plaid_client_id||"")}" placeholder="xxxxxxxxxxxxxxxx">
      <label class="fld" for="cfg-secret">Secret</label>
      <input class="input" id="cfg-secret" type="password" value="${esc(cfg.plaid_secret||"")}" placeholder="••••••••••••••••">
      <label class="fld" for="cfg-env">Environment</label>
      <select class="input" id="cfg-env">
        ${["sandbox","development","production"].map(e=>`<option ${cfg.plaid_env===e?"selected":""}>${e}</option>`).join("")}
      </select>
      <div class="small muted mt" style="margin-top:8px">Sandbox keys are free and come with fake banks for testing. Development has live banks with test credentials. Get keys at dashboard.plaid.com.</div>
      <div class="mt" style="margin-top:12px;text-align:right">
        <button class="btn btn-primary btn-sm" onclick="saveSettings(this)">Save settings</button>
      </div>
    </div>

    <div class="card">
      <h3>Preferences</h3>
      <label class="fld" for="cfg-theme">Theme</label>
      <select class="input" id="cfg-theme">
        <option value="dark" ${state.theme==="dark"?"selected":""}>🌙 Dark</option>
        <option value="light" ${state.theme==="light"?"selected":""}>☀ Light</option>
      </select>
      <label class="fld" for="cfg-tax">Business tax set-aside rate (0–1)</label>
      <input class="input" id="cfg-tax" type="number" step="0.01" min="0" max="0.9" value="${cfg.tax_rate_business}">
      <div class="small muted mt" style="margin-top:8px">Used for the estimated tax number on the Business page.</div>
      <div class="mt" style="margin-top:12px;text-align:right">
        <button class="btn btn-primary btn-sm" onclick="saveSettings(this)">Save preferences</button>
      </div>
    </div>

    <div class="card">
      <h3>Demo data</h3>
      <p class="small muted">Loads ~9 months of realistic sample data across 4 accounts so you can explore everything instantly.</p>
      <div class="row">
        <button class="btn btn-primary btn-sm" onclick="seedDemo(false)">Load demo data</button>
        <button class="btn btn-danger btn-sm" onclick="seedDemo(true)">Reload (wipes existing)</button>
      </div>
    </div>

    <div class="card">
      <h3>Data</h3>
      <div class="row" style="flex-wrap:wrap">
        <button class="btn btn-sm" onclick="exportCSV()">⬇ Export transactions CSV</button>
        <button class="btn btn-sm btn-danger" onclick="resetData()">⚠ Reset all data</button>
      </div>
      <div class="small muted mt" style="margin-top:10px">
        SQLite file: <code class="kbd">backend/data/ledger.db</code> · ${accounts.length} active accounts
      </div>
    </div>
  </div>`;
});
async function saveSettings(button) {
  if (button?.dataset.pending === "1") return;
  const body = {
    plaid_client_id: document.getElementById("cfg-cid").value.trim(),
    plaid_secret: document.getElementById("cfg-secret").value.trim(),
    plaid_env: document.getElementById("cfg-env").value,
    theme: document.getElementById("cfg-theme").value,
    tax_rate_business: parseFloat(document.getElementById("cfg-tax").value || "0.25"),
  };
  if (!setPending(button, true, "Saving…")) return;
  try {
    await api("/config", { method: "POST", body: JSON.stringify(body) });
    if (body.theme !== state.theme) applyTheme(body.theme);
    toast("Settings saved", "ok");
  } catch (e) {
    toast(e.message || "Could not save settings. Try again.", "err");
  } finally { setPending(button, false); }
}
async function seedDemo(force) {
  if (force && !confirm("This wipes ALL current data and regenerates the demo dataset. Continue?")) return;
  try {
    const r = await api("/demo/seed", { method: "POST", body: JSON.stringify({ force }) });
    toast(r.already ? "Demo data already loaded" : `Loaded ${r.transactions} demo transactions ✓`, "ok", 5000);
    navigate("overview");
  } catch (e) { toast(e.message, "err"); }
}
async function resetData() {
  if (!confirm("Delete ALL accounts and transactions? This cannot be undone.")) return;
  await api("/data/reset", { method: "POST", body: "{}" });
  toast("All data cleared", "ok"); navigate("overview");
}
function exportCSV() { window.open("/api/export/transactions.csv", "_blank"); }

/* ================= theme & boot ================= */
function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("ledger-theme", theme);
  const b = document.getElementById("btn-theme");
  if (b) b.textContent = theme === "dark" ? "☀ Light" : "🌙 Dark";
}

window.addEventListener("hashchange", () => {
  const p = location.hash.replace("#", "");
  if (p && p !== state.page) navigate(p);
});


async function syncAllBanks() {
  try {
    const items = await api("/items");
    const real = items.filter(i => i.has_token);
    if (!real.length) return toast("No Plaid-connected banks to sync (demo data is static).", "err");
    let total = 0;
    for (const it of real) {
      const r = await api("/items/refresh", { method: "POST", body: JSON.stringify({ item_id: it.id }) });
      total += r.added;
    }
    toast(`Banks synced — ${total} new transactions`, "ok");
    navigate(state.page);
  } catch (e) { toast(e.message, "err"); }
}

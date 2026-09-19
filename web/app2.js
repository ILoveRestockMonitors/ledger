/* Ledger SPA — part 2: transactions, budgets, goals, subs, accounts, settings,
   Plaid Link flow with business/personal classification, boot. */

/* ================= Transactions ================= */
registerPage("transactions", "Transactions", async () => {
  setPill(null);
  const f = state.txFilters;
  const q = new URLSearchParams(Object.entries(f).filter(([,v])=>v)).toString();
  const [data, receipts, activeAccounts, archivedAccounts] = await Promise.all([
    api("/transactions?" + q), api("/receipts"), api("/accounts"), api("/accounts?archived=1")
  ]);
  const transactionAccounts = [...activeAccounts, ...archivedAccounts];
  receiptState.summary = receipts;
  return `
  <div class="page-intro transaction-intro">
    <div><h2>Transactions</h2><p>Bank activity and cash entries you add yourself.</p></div>
    ${action('add-cash-tx','＋ Add cash transaction','','btn btn-primary')}
  </div>
  <div class="filter-row transaction-filters ${state.txFiltersExpanded?'tx-filters-expanded':''}" role="search" aria-label="Transaction filters">
    <input class="input" id="tx-search" aria-label="Search transactions" placeholder="🔍 Search merchant, note…" value="${esc(f.search)}"
      onkeydown="if(event.key==='Enter'){state.txFilters.search=this.value;state.txFilters.offset=0;navigate('transactions')}">
    <button class="btn tx-filter-toggle" aria-expanded="${!!state.txFiltersExpanded}" aria-controls="tx-advanced-filters" onclick="toggleTransactionFilters(this)">Filters${[f.account_id,f.scope,f.category_id,f.since,f.until].filter(Boolean).length?' · '+[f.account_id,f.scope,f.category_id,f.since,f.until].filter(Boolean).length:''}</button>
    <div class="tx-advanced-filters" id="tx-advanced-filters">
    <select class="input" aria-label="Transaction account" onchange="state.txFilters.account_id=this.value;state.txFilters.offset=0;navigate('transactions')">
      <option value="">All accounts, including archived</option>
      <option value="__cash__" ${f.account_id==="__cash__"?"selected":""}>Cash / manual</option>
      ${transactionAccounts.map(a=>`<option value="${esc(a.id)}" ${f.account_id===a.id?"selected":""}>${esc(a.name)}${a.mask?' ••'+esc(a.mask):''}${a.archived?' · Archived':''}</option>`).join("")}
    </select>
    <select class="input" aria-label="Transaction scope" onchange="state.txFilters.scope=this.value;state.txFilters.offset=0;navigate('transactions')">
      <option value="">All scopes</option>
      <option value="business" ${f.scope==="business"?"selected":""}>💼 Business</option>
      <option value="personal" ${f.scope==="personal"?"selected":""}>🏠 Personal</option>
    </select>
    <select class="input" aria-label="Transaction category" onchange="state.txFilters.category_id=this.value;state.txFilters.offset=0;navigate('transactions')">
      <option value="">All categories</option>
      ${state.categories.map(c=>`<option value="${c.id}" ${f.category_id===c.id?"selected":""}>${c.icon} ${esc(c.name)}</option>`).join("")}
    </select>
    <label class="transaction-date">From<input type="date" class="input" value="${esc(f.since)}" onchange="state.txFilters.since=this.value;state.txFilters.offset=0;navigate('transactions')"></label>
    <label class="transaction-date">To<input type="date" class="input" value="${esc(f.until)}" onchange="state.txFilters.until=this.value;state.txFilters.offset=0;navigate('transactions')"></label>
    <button class="btn btn-sm btn-ghost" onclick="state.txFilters={search:'',account_id:'',scope:'',category_id:'',since:'',until:'',offset:0};navigate('transactions')">Clear</button>
    </div>
    <span class="small muted tx-result-count">${data.total} transaction${data.total===1?'':'s'}</span>
    ${state.lastCategoryBatch ? '<button class="btn btn-sm" onclick="undoCategoryBatch(this)">Undo last category batch</button>' : ''}
  </div>

  ${receiptSummaryMarkup(receipts)}

  <div class="card tx-list-card">
    <div class="table-wrap"><table class="tbl tx-table" aria-label="Transactions">
      <thead><tr><th>Date</th><th>Name</th><th>Account</th><th>Category</th><th>Scope</th><th class="num">Amount</th><th></th></tr></thead><tbody>
      ${data.rows.map(t => `
        <tr class="tx-row">
          <td style="white-space:nowrap" class="muted tx-date">${fmtDate(t.posted)}</td>
          <td class="tx-name"><b>${esc(t.display_name || t.merchant || t.name)}</b>${receiptOriginalName(t)}${t.note?`<div class="small muted tx-note-desktop">📝 ${esc(t.note)}</div><details class="tx-note-mobile"><summary>Note</summary><p>${esc(t.note)}</p></details>`:""}
              ${t.pending?'<span class="tag tag-rec">Pending</span>':''}${t.is_transfer?'<span class="tag tag-rec">Transfer</span>':''}${t.recurring?`<span class="tag tag-rec" title="recurring">↻</span>`:""}</td>
          <td class="muted small tx-account">${esc(t.account_id ? (t.acct_name||"—") : "Cash / manual")}${t.acct_mask?` ••${esc(t.acct_mask)}`:""}</td>
          <td class="tx-category">${receiptCategoryCell(t)}</td>
          <td class="tx-scope">
            <select class="cat-select" aria-label="${esc('Scope for '+(t.display_name||t.merchant||t.name))}" onchange="setTxScope(${esc(JSON.stringify(t.id))}, this.value)">
              <option value="personal" ${t.scope==="personal"?"selected":""}>🏠 Personal</option>
              <option value="business" ${t.scope==="business"?"selected":""}>💼 Business</option>
            </select>
          </td>
          <td class="num tx-amount ${t.amount>0?"amt-pos":"amt-neg"+(t.scope==="business"?" biz-neg":"")}"
              style="${t.amount<0&&t.scope==="business"?"color:var(--accent)":""}">${t.amount>0?"+":""}${fmtMoney(t.amount,{decimals:2})}</td>
          <td class="tx-actions"><button class="btn btn-sm btn-ghost tx-edit" aria-label="${esc('Edit '+(t.display_name||t.merchant||t.name))}" title="Edit" onclick="openTxEdit(${esc(JSON.stringify(t.id))})"><span class="tx-edit-icon">✏️</span><span class="tx-edit-label">Edit</span></button>${t.receipt_provider && t.receipt_status !== "dismissed" ? receiptEditAction(t.id, t.receipt_status) : ""}</td>
        </tr>`).join("") || `<tr class="tx-empty"><td colspan="7" class="muted" style="text-align:center;padding:30px">
            No transactions match. Add a cash transaction, load demo data, or link an account.</td></tr>`}
    </tbody></table></div>
    <div class="row-between mt tx-pagination">
      <button class="btn btn-sm" ${data.offset>0?"":"disabled"} onclick="state.txFilters.offset=${Math.max(data.offset-data.limit,0)};navigate('transactions')">← Newer</button>
      <span class="small muted">showing ${data.rows.length} of ${data.total}</span>
      <button class="btn btn-sm" ${data.offset+data.limit<data.total?"":"disabled"} onclick="state.txFilters.offset=${data.offset+data.limit};navigate('transactions')">Older →</button>
    </div>
  </div>`;
});

function toggleTransactionFilters(button) {
  state.txFiltersExpanded=!state.txFiltersExpanded;
  button.closest('.transaction-filters').classList.toggle('tx-filters-expanded',state.txFiltersExpanded);
  button.setAttribute('aria-expanded',String(state.txFiltersExpanded));
}

async function setTxScope(id, scope) {
  try {
    await api("/transactions/update", { method: "POST", body: JSON.stringify({ id, scope }) });
    toast(`Marked as ${scope}`, "ok");
    await navigate(state.page);
  } catch(e) { toast(e.message || 'Could not change the scope.', 'err'); await navigate(state.page); }
}

// Transaction recurrence uses the same subscription records as the Subscriptions page.
const txFrequencies = [['weekly','Weekly'],['biweekly','Every 2 weeks'],['monthly','Monthly'],['quarterly','Every 3 months'],['semiannual','Every 6 months'],['annual','Yearly'],['custom','Custom days']];
let txRecurringContext;
const txMerchantKey = value => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim() || 'unknown merchant';
function txSubscriptionMatch(list, transaction, scope = transaction.scope) {
  const rows = [...(list.items || []), ...(list.candidates || []), ...(list.canceled || [])];
  const matches = rows.filter(s => s.scope === scope && txMerchantKey(s.merchant) === txMerchantKey(transaction.merchant || transaction.name));
  const exact = matches.filter(s => s.account_id === transaction.account_id);
  const candidates = exact.length ? exact : matches.filter(s => !s.account_id);
  if (candidates.length > 1) throw new Error('Multiple subscriptions match this purchase. Set the frequency on the Subscriptions page.');
  return candidates[0];
}
function txNextPayment(posted, cadence, days, today = todayISO()) {
  const [y,m,d] = posted.slice(0,10).split('-').map(Number);
  const months = {monthly:1,quarterly:3,semiannual:6,annual:12}[cadence];
  let next = new Date(Date.UTC(y,m-1,d));
  do {
    if (months) {
      const first = new Date(Date.UTC(next.getUTCFullYear(),next.getUTCMonth()+months,1));
      next = new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth(),Math.min(d,new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth()+1,0)).getUTCDate())));
    } else next.setUTCDate(next.getUTCDate() + ({weekly:7,biweekly:14}[cadence] || days));
  } while (next.toISOString().slice(0,10) <= today);
  return next.toISOString().slice(0,10);
}
function toggleTxFrequency() {
  document.getElementById('txe-frequency-fields').hidden = !document.getElementById('txe-rec').checked;
  document.getElementById('txe-custom-field').hidden = document.getElementById('txe-frequency').value !== 'custom';
}
async function saveTxFrequency(body) {
  if (!body.recurring) return;
  const t = txRecurringContext.transaction;
  const cadence = document.getElementById('txe-frequency').value;
  const days = Number(document.getElementById('txe-custom-days').value);
  const list = await api('/subscriptions');
  const old = txSubscriptionMatch(list,t,body.scope);
  if (old && old.cadence === cadence && (cadence !== 'custom' || old.custom_interval_days === days) && old.status !== 'candidate') return;
  const payload = old ? {id:old.id,cadence,custom_interval_days:cadence === 'custom' ? days : null} : {
    merchant:body.name || t.merchant || t.name,scope:body.scope,account_id:t.account_id || null,
    amount:Math.abs(body.amount ?? t.amount),cadence,custom_interval_days:cadence === 'custom' ? days : null,status:'active'
  };
  if (!old || old.status === 'candidate') payload.status = 'active';
  payload.next_due = txNextPayment(body.posted || t.posted,cadence,days);
  payload.billing_day = Number((body.posted || t.posted).slice(8,10));
  await api('/subscriptions',{method:'POST',body:JSON.stringify(payload)});
}

window.openTxEdit = async function (id) {
  const f = state.txFilters;
  const data = await api("/transactions?" + new URLSearchParams(Object.entries(f).filter(([,v])=>v && v!=="")).toString());
  const t = data.rows.find(r => r.id === id);
  if (!t) return toast("Transaction not found", "err");
  let subscription;
  try { subscription = txSubscriptionMatch(await api('/subscriptions'),t); }
  catch (e) { return toast(e.message || 'Could not load subscription frequency. Try again.', 'err'); }
  txRecurringContext = {transaction:t,subscription};
  const frequency = subscription?.cadence || 'monthly';
  const cash = !t.account_id;
  const cashKind = t.is_transfer ? (t.amount > 0 ? 'transfer-in' : 'transfer-out') : (t.amount > 0 ? 'income' : 'expense');
  showModal(`
    <h2>${cash?'Edit cash transaction':'Edit transaction'}</h2>
    ${cash ? `<p class="sub">Cash entries count in budgets, reports, and cash flow without changing an account balance.</p>
    <label class="fld" for="txe-name">Name / merchant</label>
    <input class="input" id="txe-name" value="${esc(t.display_name || t.merchant || t.name)}" maxlength="200">
    <div class="form-pair"><div><label class="fld" for="txe-kind">Type</label><select class="input" id="txe-kind">
      <option value="expense" ${cashKind==='expense'?'selected':''}>Money out</option>
      <option value="income" ${cashKind==='income'?'selected':''}>Money in</option>
      <option value="transfer-out" ${cashKind==='transfer-out'?'selected':''}>Transfer out</option>
      <option value="transfer-in" ${cashKind==='transfer-in'?'selected':''}>Transfer in</option>
    </select></div><div><label class="fld" for="txe-amount">Amount</label><input class="input" id="txe-amount" type="number" inputmode="decimal" min="0.01" step="0.01" value="${Math.abs(t.amount)}"></div></div>
    <label class="fld" for="txe-posted">Date</label><input class="input" id="txe-posted" type="date" max="${todayISO()}" value="${esc(t.posted)}">` : `<p class="sub">${esc(t.name)} · ${fmtDate(t.posted)} · ${fmtMoney(t.amount,{decimals:2})}</p>`}
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
      <input type="checkbox" id="txe-rec" onchange="toggleTxFrequency()" ${t.recurring?"checked":""} style="width:auto"> Mark as recurring
    </label>
    <div id="txe-frequency-fields" ${t.recurring?'':'hidden'}>
      <label class="fld" for="txe-frequency">Subscription frequency</label>
      <select class="input" id="txe-frequency" onchange="toggleTxFrequency()">${txFrequencies.map(([value,label])=>`<option value="${value}" ${frequency===value?'selected':''}>${label}</option>`).join('')}</select>
      <div id="txe-custom-field" ${frequency==='custom'?'':'hidden'}>
        <label class="fld" for="txe-custom-days">Days between payments</label>
        <input class="input" id="txe-custom-days" type="number" inputmode="numeric" min="1" max="366" step="1" value="${Number(subscription?.custom_interval_days)||30}">
      </div>
    </div>
    ${cash ? '' : `<label class="fld row" style="gap:8px"><input type="checkbox" id="txe-transfer" ${t.is_transfer?'checked':''}> Transfer between accounts</label>`}
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
  const original = txRecurringContext.transaction;
  const cash = !original.account_id;
  const body = {
    id,
    scope: document.getElementById("txe-scope").value,
    note: document.getElementById("txe-note").value,
    recurring: document.getElementById("txe-rec").checked,
    is_transfer: cash ? document.getElementById("txe-kind").value.startsWith('transfer') : document.getElementById("txe-transfer").checked,
  };
  if (cash) {
    const kind = document.getElementById("txe-kind").value;
    const amount = Number(document.getElementById("txe-amount").value);
    if (!Number.isFinite(amount) || amount <= 0) return toast('Enter an amount greater than zero.', 'err');
    body.amount = amount * (kind === 'income' || kind === 'transfer-in' ? 1 : -1);
    body.name = document.getElementById("txe-name").value.trim();
    body.posted = document.getElementById("txe-posted").value;
    if (!body.name) return toast('Enter a name or merchant.', 'err');
    if (!body.posted) return toast('Choose a date.', 'err');
  }
  if (category.value !== (category.dataset.originalValue || "")) body.category_id = category.value || null;
  if (body.recurring) {
    if (body.is_transfer || (body.amount ?? original.amount) >= 0) return toast('Only outgoing purchases can be tracked as subscriptions.', 'err');
    const days = Number(document.getElementById('txe-custom-days').value);
    if (document.getElementById('txe-frequency').value === 'custom' && (!Number.isInteger(days) || days < 1 || days > 366)) return toast('Enter a whole number from 1 to 366 days.', 'err');
  }
  let transactionSaved = false;
  if (!setPending(button, true, "Saving…")) return;
  try {
    const update = {...body};
    if (body.scope === original.scope) delete update.scope;
    if (body.is_transfer === Boolean(original.is_transfer)) delete update.is_transfer;
    await api("/transactions/update", { method: "POST", body: JSON.stringify(update) });
    transactionSaved = true;
    await saveTxFrequency(body);
    closeModal(); toast("Saved", "ok"); await navigate(state.page);
    const selected = state.categories.find(c => c.id === body.category_id);
    if (body.category_id && selected?.kind === 'expense' && (body.amount ?? original.amount) < 0 && !body.is_transfer) {
      await previewCategoryBatch(id, body.category_id);
    }
  } catch (e) {
    toast(transactionSaved ? "Transaction saved, but subscription frequency could not be saved. " + (e.message || "Try Save again.") : (e.message || "Could not save this transaction. Try again."), "err");
  } finally { setPending(button, false); }
}
let categoryBatchPreview;
async function previewCategoryBatch(id, categoryId) {
  try {
    const p = await api('/transactions/category-preview', {method:'POST',body:JSON.stringify({id,category_id:categoryId})});
    categoryBatchPreview = p;
    showModal(`
      <h2>Apply this category to matching purchases?</h2>
      <p class="sub">This purchase is saved. ${p.count === 1 ? 'This other' : p.count ? `These ${p.count} other` : 'No other'} ${esc(p.scope)} ${p.count === 1 ? 'purchase' : 'purchases'} named <b>${esc(p.label)}</b> ${p.count ? 'will change' : 'need changing'} to <b>${esc(p.category_name)}</b>.</p>
      ${p.count ? `<div class="category-batch-list" role="region" aria-label="Purchases that will change" tabindex="0">${p.transactions.map(t => `
        <div class="category-batch-row">
          <div><b>${esc(t.name_override ? t.name : t.merchant || t.name)}</b><div class="small muted">${fmtDate(t.posted)} · ${esc(t.account_name)}${t.account_mask ? ` ••${esc(t.account_mask)}` : ''}${t.pending ? ' · Pending' : ''}</div><div class="small">${esc(t.category_name || 'Uncategorized')} → ${esc(p.category_name)}${t.category_override ? ' · Previously chosen manually' : ''}</div></div>
          <strong>${fmtMoney(t.amount,{decimals:2})}</strong>
        </div>`).join('')}</div>` : ''}
      ${p.skipped_splits ? `<p class="small muted">${p.skipped_splits} matching purchases have item splits and are left unchanged.</p>` : ''}
      <label class="fld row category-batch-remember"><input type="checkbox" id="category-batch-remember" checked> Use this category for future ${esc(p.scope)} purchases with this name</label>
      <div class="modal-actions">
        <button class="btn" onclick="categoryBatchPreview=null;closeModal()">Only this purchase</button>
        <button class="btn btn-primary" onclick="applyCategoryBatch(this)">${p.count ? `Apply to ${p.count} ${p.count === 1 ? 'purchase' : 'purchases'}` : 'Save future preference'}</button>
      </div>`);
  } catch(e) { toast('Purchase saved. ' + (e.message || 'Could not load matching purchases.'), 'err'); }
}
async function applyCategoryBatch(button) {
  if (!categoryBatchPreview || !setPending(button,true,'Applying…')) return;
  try {
    const result = await api('/transactions/category-apply',{method:'POST',body:JSON.stringify({preview_id:categoryBatchPreview.preview_id,remember:document.getElementById('category-batch-remember').checked})});
    state.lastCategoryBatch = result.batch_id;
    categoryBatchPreview = null; closeModal();
    toast(`${result.changed} purchases updated${result.remembered ? '; future preference saved' : ''}. You can undo this batch.`, 'ok');
    await navigate(state.page);
  } catch(e) { toast(e.message || 'Could not apply categories. Try again.', 'err'); }
  finally { setPending(button,false); }
}
async function undoCategoryBatch(button) {
  if (!state.lastCategoryBatch || !setPending(button,true,'Undoing…')) return;
  try {
    const result = await api('/transactions/category-undo',{method:'POST',body:JSON.stringify({batch_id:state.lastCategoryBatch})});
    state.lastCategoryBatch = null;
    toast(`${result.restored} categories restored${result.skipped ? `; ${result.skipped} newer changes preserved` : ''}.`, 'ok');
    await navigate(state.page);
  } catch(e) { toast(e.message || 'Could not undo this batch.', 'err'); }
  finally { setPending(button,false); }
}
async function deleteTx(id) {
  if (!confirm("Delete this transaction?")) return;
  try {
    await api("/transactions?id=" + id, { method: "DELETE" });
    closeModal(); toast("Deleted", "ok"); await navigate(state.page);
  } catch (e) { toast(e.message || "Could not delete this transaction. Try again.", "err"); }
}

function openAddTx(preferCash=false) {
  showModal(`
    <h2>${preferCash?'Add cash transaction':'Add transaction'}</h2>
    <p class="sub">Cash entries count in budgets, reports, and cash flow without changing an account balance.</p>
    <label class="fld" for="addtx-acct">Account</label>
    <select class="input" id="addtx-acct" onchange="document.getElementById('addtx-scope').value=this.selectedOptions[0].dataset.scope||'personal'">
      <option value="" data-scope="personal" ${preferCash?'selected':''}>Cash / manual (no account)</option>${state.accounts.map(a=>
      `<option value="${a.id}" data-scope="${a.scope}">${esc(a.name)} (${a.scope[0].toUpperCase()})</option>`).join("")}</select>
    <label class="fld" for="addtx-scope">For</label><select class="input" id="addtx-scope"><option value="personal">Personal</option><option value="business">Business</option></select>
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
      account_id: acctSel.value || null,
      scope: acctSel.value ? acctSel.selectedOptions[0].dataset.scope : document.getElementById("addtx-scope").value,
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
const budgetView = {month: `${new Date().getFullYear()}-${String(new Date().getMonth()+1).padStart(2,'0')}`, scope:'', tab:'all'};
function setBudgetView(field, value) { budgetView[field]=value; navigate('budgets'); }
function openBudgetSpending(categoryId, scope) {
  const [year, month] = budgetView.month.split('-').map(Number);
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  state.txFilters = {search:'', scope:scope==='all'?'':scope, category_id:categoryId,
    since:budgetView.month+'-01', until:budgetView.month+'-'+String(lastDay).padStart(2,'0'), offset:0};
  navigate('transactions');
}
function reviewBudgetPurchase(name, posted) {
  state.txFilters={search:name,scope:budgetView.scope,category_id:'',since:posted,until:posted,offset:0};
  navigate('transactions');
}
function monthlySpendingView(data) {
  const s=data.summary, money=n=>fmtMoney(n,{decimals:2});
  const monthLabel=new Date(data.month+'-01T12:00:00').toLocaleDateString(undefined,{month:'long',year:'numeric'});
  const detail=budgetView.tab==='uncategorized'
    ? `<h3>Uncategorized spending · ${money(s.uncategorized)}</h3><p class="muted small">${s.uncategorized_count} purchases. For split receipts, only the uncategorized portion is listed.</p>
       ${data.uncategorized_transactions.length ? `<div class="budget-table-wrap"><table class="budget-spending-table"><thead><tr><th>Date / Purchase</th><th>Account</th><th>Status</th><th>Uncategorized</th><th></th></tr></thead><tbody>
       ${data.uncategorized_transactions.map(t=>`<tr><td>${fmtDate(t.posted)}<br><b>${esc(t.name)}</b></td><td>${esc(t.account_name||'Manual')}${t.account_mask?' ••'+esc(t.account_mask):''}<br>${scopeTag(t.scope)}</td><td>${t.pending?'Pending':'Posted'}${t.partially_categorized?' · Split receipt':''}</td><td>${money(t.uncategorized_amount)}</td><td><button class="btn btn-sm" onclick="reviewBudgetPurchase(${esc(JSON.stringify(t.name))},${esc(JSON.stringify(t.posted))})">Review</button></td></tr>`).join('')}</tbody></table></div>` : '<p>All spending in this month is categorized.</p>'}`
    : `<h3>Every spending category</h3><p class="muted small">Includes categories with no budget limit.</p><div class="budget-table-wrap"><table class="budget-spending-table"><thead><tr><th>Category</th><th>Posted</th><th>Pending</th><th>Total</th></tr></thead><tbody>
       ${data.categories.map(c=>`<tr><td>${c.id===null?`<button class="btn btn-sm" onclick="setBudgetView('tab','uncategorized')">Uncategorized</button>`:esc(c.name)}</td><td>${money(c.posted)}</td><td>${money(c.pending)}</td><td><b>${money(c.total)}</b></td></tr>`).join('')}
       </tbody><tfoot><tr><th>Total spending</th><td>${money(s.posted)}</td><td>${money(s.pending)}</td><td><b>${money(s.total)}</b></td></tr></tfoot></table></div>`;
  return `<div class="budget-month-controls"><label>Month<input aria-label="Budget month" class="input" type="month" min="1900-01" max="${data.as_of.slice(0,7)}" value="${data.month}" onchange="if(this.value)setBudgetView('month',this.value)"></label>
    <label>Spending scope<select aria-label="Budget scope" class="input" onchange="setBudgetView('scope',this.value)">${[['','All spending'],['business','Business'],['personal','Personal']].map(([v,n])=>`<option value="${v}" ${budgetView.scope===v?'selected':''}>${n}</option>`).join('')}</select></label></div>
    <div class="card budget-month-summary"><div class="micro-label">${esc(monthLabel)} · ${esc(budgetView.scope||'All spending')}</div><h2>Total spending</h2><div class="budget-month-total">${money(s.total)}</div>
    <div class="budget-summary-parts"><span>Posted <b>${money(s.posted)}</b></span><span>Pending <b>${money(s.pending)}</b></span><span>Categorized <b>${money(s.categorized)}</b></span><span>Uncategorized <b>${money(s.uncategorized)}</b></span></div>
    <p class="small muted">${s.transaction_count} purchases. Total includes pending charges. Transfers and credit card repayments are excluded. Categorized + uncategorized = total spending.</p>
    ${s.refunds?`<p class="small muted">Refunds and credits in expense categories: ${money(s.refunds)}, shown separately from purchases.</p>`:''}</div>
    <div class="budget-view-tabs" role="tablist" aria-label="Monthly spending details"><button class="btn" role="tab" aria-selected="${budgetView.tab==='all'}" onclick="setBudgetView('tab','all')">All spending</button><button class="btn" role="tab" aria-selected="${budgetView.tab==='uncategorized'}" onclick="setBudgetView('tab','uncategorized')">Uncategorized (${s.uncategorized_count}) · ${money(s.uncategorized)}</button></div>
    <div class="card" role="tabpanel">${detail}</div>
    <div class="section-title">Monthly spending · ${data.month.slice(0,4)}</div><div class="budget-month-history">${data.months.map(m=>`<button class="card budget-history-month" ${m.future?'disabled':''} aria-pressed="${m.month===data.month}" onclick="setBudgetView('month','${m.month}')"><span>${new Date(m.month+'-01T12:00:00').toLocaleDateString(undefined,{month:'short'})}</span><b>${m.future?'—':money(m.total)}</b>${m.pending?`<small>${money(m.pending)} pending</small>`:''}</button>`).join('')}</div>`;
}
registerPage("budgets", "Budgets", async () => {
  setPill(null);
  const params=new URLSearchParams({month:budgetView.month,scope:budgetView.scope});
  const [allBudgets,spending] = await Promise.all([api('/budgets?'+params),api('/budgets/overview?'+params)]);
  const budgets=allBudgets.filter(b=>!budgetView.scope||b.scope===budgetView.scope);
  const groups = {
    business: budgets.filter(b => b.scope === "business"),
    personal: budgets.filter(b => b.scope === "personal"),
    all: budgets.filter(b => b.scope === "all"),
  };
  const card = b => `
    <div class="card budget-clickable ${b.scope==="business"?"tint-biz":b.scope==="personal"?"tint-per":""}">
      <button class="budget-open" aria-label="${esc('View '+b.cat_name+' spending for '+budgetView.month+' · '+b.scope)}" onclick="openBudgetSpending(${esc(JSON.stringify(b.category_id))},${esc(JSON.stringify(b.scope))})"></button>
      <div class="row-between">
        <b>${b.cat_icon||"◎"} ${esc(b.cat_name)} ${scopeTag(b.scope)}</b>
        <button class="btn btn-sm btn-ghost budget-delete" aria-label="${esc('Delete '+b.cat_name+' budget')}" onclick="deleteBudget(${esc(JSON.stringify(b.id))})">✕</button>
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
      <div class="small muted" style="margin-top:10px">View transactions →</div>
    </div>`;
  const section = (title, arr, tint) => arr.length ? `
    <div class="section-title">${title}</div>
    <div class="grid cols-3">${arr.map(card).join("")}</div>` : "";
  return `
  ${monthlySpendingView(spending)}
  <div class="section-title">Budget limits</div>
  <div class="row-between mb" style="margin-bottom:14px">
    <span class="muted small">Envelope progress uses posted purchases for the selected month.</span>
    <button class="btn btn-primary btn-sm" onclick="openBudgetForm()">+ New budget</button>
  </div>
  ${section("💼 Business budgets", groups.business)}
  ${section("🏠 Personal budgets", groups.personal)}
  ${section("◎ Combined budgets", groups.all)}
  ${!budgets.length ? `<div class="empty"><div class="big">◎</div>No budget limits set for this scope.<br><br>
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
  try {
    await api("/budgets?id=" + id, { method: "DELETE" }); await navigate("budgets");
  } catch (e) { toast(e.message || "Could not delete this budget. Try again.", "err"); }
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
  try {
    await api("/goals?id=" + id, { method: "DELETE" }); await navigate("goals");
  } catch (e) { toast(e.message || "Could not delete this goal. Try again.", "err"); }
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
  const [items, accounts, archived] = await Promise.all([api("/items"), api("/accounts"), api("/accounts?archived=1")]);
  state.accounts = accounts;
  const cfg = await api("/config");
  const acctCard = a => `
    <div class="card acct-card ${a.scope==="business"?"tint-biz":"tint-per"}">
      <div class="acct-name">
        <b>${esc(a.name)} ${a.mask?`<span class="muted small">••${esc(a.mask)}</span>`:""}</b>
        <span>${esc(a.subtype||a.type||"")} · ${esc(a.iso_currency)}</span>
      </div>
      <div class="row">
        <div class="acct-bal ${a.balance<0?"neg":""}">${fmtMoney(a.balance,{decimals:2})}</div>
        <button class="btn btn-sm ${a.scope==="business"?"":"btn-ghost"}" onclick="classifyAcct(${esc(JSON.stringify(a.id))},'business')">💼</button>
        <button class="btn btn-sm ${a.scope==="personal"?"":"btn-ghost"}" onclick="classifyAcct(${esc(JSON.stringify(a.id))},'personal')">🏠</button>
        <button class="btn btn-sm btn-ghost" onclick="archiveAcct(${esc(JSON.stringify(a.id))})" title="Archive account and keep history" aria-label="${esc('Archive '+a.name+' and keep history')}">📦</button>
      </div>
    </div>`;
  const archivedCard = a => {
    const item = items.find(it => it.id === a.item_id);
    const connection = !a.item_id ? 'Manual account' : item?.has_token ? 'Updates paused' : 'Disconnected';
    return `<div class="card acct-card">
      <div class="acct-name">
        <b>${esc(a.name)} ${a.mask?`<span class="muted small">••${esc(a.mask)}</span>`:""}</b>
        <span>${esc(item?.institution || a.subtype || a.type || '')} · ${connection}</span>
      </div>
      <div class="row" style="flex-wrap:wrap">
        <button class="btn btn-sm" onclick="showAccountHistory(${esc(JSON.stringify(a.id))})">Show history</button>
        <button class="btn btn-sm btn-ghost" onclick="restoreAcct(${esc(JSON.stringify(a.id))})">Restore</button>
      </div>
    </div>`;
  };
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
      <span class="tag ${it.env_label==="demo"?"tag-rec":"tag-ded"}" style="margin-left:6px">${esc(it.env_label)}</span>
      <span class="small muted" style="font-weight:400">· ${Number(it.n_active_accounts)||0} active account(s)${it.has_token ? Number(it.n_active_accounts)>0 ? '' : ' · Updates paused' : it.env_label==='demo' ? ' · Sample data' : ' · Disconnected'}</span>
      ${it.has_token && Number(it.n_active_accounts)>0 ? `<button class="btn btn-sm btn-ghost" style="float:right" onclick="refreshItem(${esc(JSON.stringify(it.id))})">⟳ Sync now</button>` : ""}
      ${it.has_token ? `<button class="btn btn-sm btn-ghost" style="float:right;margin-right:6px" onclick="unlinkItem(${esc(JSON.stringify(it.id))})">Disconnect</button>` : ""}
    </div>
    <div class="grid cols-2">${accounts.filter(a => a.item_id === it.id).map(acctCard).join("") || `<div class="small muted">No active accounts. Saved history is available below.</div>`}</div>
  `).join("")}
  ${archived.length ? `<section aria-labelledby="archived-accounts-title" style="margin-top:24px">
    <h3 id="archived-accounts-title">Archived accounts <span class="h3-extra">${archived.length}</span></h3>
    <p class="small muted">Updates are stopped and these accounts are excluded from current balances. All transactions, categories, notes, and report history are preserved.</p>
    <div class="grid cols-2">${archived.map(archivedCard).join("")}</div>
  </section>` : ""}
  ${!items.length ? `<div class="empty"><div class="big">🏦</div>No accounts connected yet.</div>` : ""}`;
});
async function classifyAcct(id, scope) {
  await api("/accounts/classify", { method: "POST", body: JSON.stringify({ id, scope }) });
  toast(`Account marked ${scope}. Its transactions moved too.`, "ok");
  navigate("accounts");
}
async function archiveAcct(id) {
  if (!confirm("Archive this account? Future sync updates stop and the account is excluded from current balances. All transactions, categories, notes, and report history are preserved.")) return;
  try {
    await api("/accounts/archive", { method: "POST", body: JSON.stringify({ id }) });
    state.accounts = await api("/accounts");
    toast("Account archived. Updates stopped; all history is preserved.", "ok");
    await navigate("accounts");
  } catch (e) { toast(e.message || "Could not archive this account.", "err"); }
}
function showAccountHistory(id) {
  state.txFilters = {search:'',account_id:id,scope:'',category_id:'',since:'',until:'',offset:0};
  state.txFiltersExpanded = true;
  return navigate("transactions");
}
async function restoreAcct(id) {
  if (!confirm("Restore this account to current balances? All saved history stays intact. Syncing resumes if its bank connection is still linked; a disconnected account needs a bank connection to receive updates.")) return;
  try {
    await api("/accounts/archive", { method: "POST", body: JSON.stringify({ id, restore: true }) });
    state.accounts = await api("/accounts");
    toast("Account restored. All saved history is preserved.", "ok");
    await navigate("accounts");
  } catch (e) { toast(e.message || "Could not restore this account.", "err"); }
}
async function refreshItem(id) {
  try {
    const r = await api("/items/refresh", { method: "POST", body: JSON.stringify({ item_id: id }) });
    toast(r.message || `Synced — ${r.added} new transactions`, "ok");
    navigate("accounts");
  } catch (e) { toast(e.message, "err"); }
}
async function unlinkItem(id) {
  if (!confirm("Disconnect this bank? Future sync updates stop and all its accounts are archived and excluded from current balances. All transactions, categories, notes, and report history are preserved.")) return;
  try {
    await api("/items?id=" + encodeURIComponent(id), { method: "DELETE" });
    state.accounts = await api("/accounts");
    toast("Bank disconnected and accounts archived. All history is preserved.", "ok");
    await navigate("accounts");
  } catch (e) { toast(e.message || "Could not disconnect this bank.", "err"); }
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
function exportCSV() { window.open(LedgerDemo.url("/export/transactions.csv"), "_blank", "noopener"); }

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
    const real = items.filter(i => i.has_token && Number(i.n_active_accounts)>0);
    if (!real.length) return toast("No connected active accounts to sync. Archived history is preserved.", "ok");
    let total = 0;
    for (const it of real) {
      const r = await api("/items/refresh", { method: "POST", body: JSON.stringify({ item_id: it.id }) });
      total += r.added;
    }
    toast(`Banks synced — ${total} new transactions`, "ok");
    navigate(state.page);
  } catch (e) { toast(e.message, "err"); }
}

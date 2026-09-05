/* Receipt lookup UI. The backend owns the worker and proposal state; this
   file keeps the browser surface small, reviewable, and free of inline code. */
const receiptState = { summary: null, detail: null };

function receiptText(value) { return esc(String(value ?? "")); }
function receiptAttr(value) { return receiptText(value); }
function receiptMoney(cents) { return fmtMoney((Number(cents) || 0) / 100, { decimals: 2 }); }
function receiptDate(value) { return value ? fmtDate(String(value).slice(0, 10)) : ""; }
function receiptSafeURL(value, provider = "") {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    const providerHosts = {
      amazon: ["amazon.com", "amazon.co.uk", "amazon.ca", "amazon.de", "amazon.fr", "amazon.it", "amazon.es", "amazon.co.jp", "amazon.in", "amazon.com.au", "amazon.com.mx", "amazon.nl", "amazon.se", "amazon.pl", "amazon.sg", "amazon.ae", "amazon.sa", "amazon.tr", "amazon.be"],
      apple: ["apple.com"],
      google: ["google.com", "google.co.uk", "google.ca", "google.de", "google.fr", "google.es", "google.it", "google.com.au", "google.co.jp", "google.co.in"]
    };
    const roots = providerHosts[provider] || Object.values(providerHosts).flat();
    const allowed = roots.some(root => host === root || host.endsWith(`.${root}`));
    return url.protocol === "https:" && allowed && !url.username && !url.password ? url.href : "";
  } catch { return ""; }
}
function receiptButton(label, action, id = "", cls = "btn btn-sm") {
  return `<button type="button" class="${receiptAttr(cls)}" data-receipt-action="${receiptAttr(action)}" data-receipt-id="${receiptAttr(id)}">${label}</button>`;
}
function receiptStatus(status) {
  return ({ queued: "Waiting", running: "Working", needs_user: "Needs your help", review: "Ready to review", applied: "Applied", dismissed: "Dismissed", failed: "Needs attention" })[status] || "Not started";
}
function receiptStatusTag(status) {
  return `<span class="receipt-status receipt-status-${receiptAttr(status || "none")}">${receiptText(receiptStatus(status))}</span>`;
}
function receiptProvider(provider) {
  return ({ amazon: "Amazon", apple: "Apple", google: "Google" })[provider] || "Purchase details";
}
function receiptCategory(categoryId) {
  const categories = typeof state !== "undefined" ? state.categories || [] : [];
  const found = categories.find(c => c.id === categoryId);
  return found ? `${receiptText(found.icon || "")} ${receiptText(found.name)}` : "Choose a budget";
}
function receiptDisplayName(transaction) {
  if (transaction?.name_override) return transaction.name || transaction.display_name || "Purchase";
  return transaction?.receipt_status === "applied" && transaction?.display_name
    ? transaction.display_name
    : transaction?.merchant || transaction?.name || "Purchase";
}
function receiptCandidateTransaction(candidate) {
  return candidate?.transaction || candidate || {};
}
function receiptOriginalName(transaction) {
  if (transaction?.receipt_status !== "applied") return "";
  const display = receiptDisplayName(transaction);
  const original = transaction?.name || transaction?.merchant || "";
  return original && original !== display ? `<span class="receipt-original">Original charge: ${receiptText(original)}</span>` : "";
}
function receiptDetailName(transaction, job) {
  return receiptDisplayName(transaction);
}
function receiptCategoryCell(transaction) {
  const allocations = Array.isArray(transaction?.allocations) ? transaction.allocations : [];
  const budgetIds = [...new Set(allocations.map(a => a.category_id).filter(Boolean))];
  if (budgetIds.length > 1) {
    const preview = [...new Set(allocations.map(a => a.cat_name ? receiptText(a.cat_name) : receiptCategory(a.category_id)))].slice(0, 3);
    return `<span class="receipt-split-label">Split across ${budgetIds.length} budgets</span><span class="receipt-allocation-preview">${preview.join(" · ")}</span>`;
  }
  if (budgetIds.length === 1) return `<span class="cat-chip">${receiptCategory(allocations[0].category_id)}</span>`;
  return transaction?.cat_name ? `<span class="cat-chip">${receiptText(transaction.cat_icon || "")} ${receiptText(transaction.cat_name)}</span>` : `<span class="muted small">uncategorized</span>`;
}

function receiptEditAction(id, status = "") {
  const label = ["review", "applied"].includes(status) ? "Purchase details" : "Look up purchase";
  return receiptButton(label, "detail", id, "btn btn-sm btn-ghost receipt-edit-action");
}

function receiptSettingsCard(summary = {}, config = {}) {
  const settings = summary.settings || {};
  const demo = Boolean(config.demo || summary.demo);
  const worker = summary.worker || {};
  const enabled = Boolean(settings.enabled);
  const autoApply = settings.auto_apply !== false;
  const dailyLimit = Math.max(1, Math.min(30, Number(settings.daily_limit) || 10));
  const message = worker.message || (worker.ready ? "Your home-lab worker is ready." : "Set up the dedicated home-lab browser before enabling lookups.");
  const guidance = worker.instructions || worker.handoff || worker.setup;
  return `<section class="card receipt-settings-card">
    <h3>Purchase details assistant</h3>
    <p class="small muted">Find the items inside an unclear Amazon, Apple, or Google charge, then place each item in the right budget.</p>
    <form data-receipt-settings-form>
      <label class="setting-row receipt-toggle" for="receipt-enabled"><span><b>Look up unclear purchases</b><small>Runs on the dedicated home-lab browser.</small></span><input id="receipt-enabled" name="enabled" type="checkbox" ${enabled ? "checked" : ""} ${demo ? "disabled" : ""}></label>
      <label class="setting-row receipt-toggle" for="receipt-auto-apply"><span><b>Apply clear splits automatically</b><small>Turn this off to review every clear match; uncertain matches always ask.</small></span><input id="receipt-auto-apply" name="auto_apply" type="checkbox" ${autoApply ? "checked" : ""} ${demo ? "disabled" : ""}></label>
      <label class="setting-row" for="receipt-daily-limit"><span><b>Daily lookup limit</b><small>Limit how many purchases the assistant looks up each day.</small></span><input class="input receipt-limit" id="receipt-daily-limit" name="daily_limit" type="number" min="1" max="30" step="1" value="${dailyLimit}" ${demo ? "disabled" : ""}></label>
      <p class="receipt-worker-note ${worker.ready ? "ready" : ""}">${receiptText(demo ? "Sample mode keeps purchase lookups off." : message)}</p>
      ${guidance ? `<details class="disclosure"><summary>Setup guidance</summary><p class="quiet-note">${receiptText(guidance)}</p></details>` : ""}
      <div class="receipt-settings-actions"><button class="btn btn-primary btn-sm" type="submit" ${demo ? "disabled" : ""}>Save purchase settings</button></div>
    </form>
  </section>`;
}

async function loadReceiptSummary() {
  receiptState.summary = await api("/receipts");
  return receiptState.summary;
}

function receiptSummaryMarkup(summary = receiptState.summary || {}) {
  const candidates = Array.isArray(summary.candidates) ? summary.candidates : [];
  const jobs = Array.isArray(summary.jobs) ? summary.jobs : [];
  const activeJobs = jobs.filter(j => !["applied", "dismissed"].includes(j.status));
  const candidateIds = new Set(candidates.map(t => receiptCandidateTransaction(t).id || t.transaction_id));
  const count = candidates.length + activeJobs.filter(j => !candidateIds.has(j.transaction_id)).length;
  const phrase = count ? `${count} purchase${count === 1 ? "" : "s"} could use a closer look` : "Nothing needs a closer look";
  const worker = summary.worker || {};
  return `<details class="receipt-review-drawer">
    <summary><span class="receipt-drawer-title">Clarify purchases</span><span class="receipt-drawer-summary">${receiptText(phrase)}</span></summary>
    <div class="receipt-drawer-body"><p class="small muted">Clear matches can apply automatically from your setting; uncertain matches stay ready for review. Mixed orders can be placed across budgets.</p>
      <div class="row-between"><span class="receipt-worker-inline">${receiptText(worker.message || (summary.demo ? "Sample mode keeps the assistant off." : "Purchase lookup is ready when you are."))}</span>${receiptButton(count ? "Review list" : "See lookup status", "review-list", "", "btn btn-sm btn-ghost")}</div>
    </div>
  </details>`;
}

function receiptJobLine(job, transaction) {
  const label = receiptDisplayName(transaction || job.transaction || { name: job.transaction_id });
  const action = ["needs_user", "failed"].includes(job.status) ? receiptButton("Continue", "resume", job.id, "btn btn-sm btn-primary") : ["queued", "running"].includes(job.status) ? receiptButton("Refresh status", "detail", job.transaction_id, "btn btn-sm btn-ghost") : receiptButton("Open", "detail", job.transaction_id, "btn btn-sm btn-ghost");
  return `<div class="receipt-review-row"><div class="merchant-info"><b>${receiptText(label)}</b><small>${receiptText(receiptProvider(job.provider))} · ${receiptText(job.message || receiptStatus(job.status))}</small></div>${receiptStatusTag(job.status)}${action}</div>`;
}

async function openReceiptReviewList() {
  const summary = await loadReceiptSummary();
  const candidates = Array.isArray(summary.candidates) ? summary.candidates : [];
  const jobs = Array.isArray(summary.jobs) ? summary.jobs : [];
  const candidateIds = new Set(jobs.map(j => j.transaction_id));
  const rows = candidates.map(receiptCandidateTransaction).filter(t => !candidateIds.has(t.id)).map(t => `<div class="receipt-review-row"><div class="merchant-info"><b>${receiptText(receiptDisplayName(t))}</b><small>${receiptText(t.merchant || t.name || "")} · ${receiptDate(t.posted)} · ${fmtMoney(t.amount, { decimals: 2 })}</small></div>${receiptButton("Look up", "detail", t.id, "btn btn-sm btn-primary")}</div>`).join("");
  const jobRows = jobs.filter(j => !["dismissed"].includes(j.status)).map(j => receiptJobLine(j, candidates.map(receiptCandidateTransaction).find(t => t.id === j.transaction_id) || j.transaction)).join("");
  showModal(`<button type="button" class="close-button" data-receipt-action="close" aria-label="Close dialog">×</button><h2>Clarify purchases</h2><p class="sub">Clear matches follow your auto-apply setting; uncertain matches wait for review.</p><div class="receipt-review-list">${rows || jobRows ? `${rows}${jobRows}` : `<div class="empty inline-empty">No purchase details are waiting for you.</div>`}</div>`);
}

function receiptProposalMarkup(job) {
  const proposal = job?.proposal;
  if (!proposal) return "";
  const items = Array.isArray(proposal.items) ? proposal.items : [];
  return `<section class="receipt-proposal"><div class="receipt-proposal-head"><div><span class="micro-label">Suggested split</span><h3>${receiptText(proposal.description || "Purchase items")}</h3></div><strong>${receiptMoney(proposal.receipt?.total_cents)}</strong></div>
    <div class="receipt-item-list">${items.map(item => `<div class="receipt-item"><span>${receiptText(item.description || "Item")}</span><select class="input receipt-category-select" data-receipt-category aria-label="Category for ${receiptAttr(item.description || 'item')}"><option value="">Choose a category</option>${state.categories.filter(category => category.kind === 'expense').map(category => `<option value="${receiptAttr(category.id)}" ${category.id === item.category_id ? 'selected' : ''}>${receiptText(category.name)}</option>`).join('')}</select><strong>${receiptMoney(item.amount_cents)}</strong></div>`).join("") || `<p class="small muted">No item breakdown is ready yet.</p>`}</div>
    ${receiptEvidenceMarkup(job)}</section>`;
}

function receiptEvidenceMarkup(job) {
  const receipt = job?.proposal?.receipt;
  if (!receipt) return "";
  const url = receiptSafeURL(receipt.url, job.provider);
  return `<p class="receipt-meta">${receipt.order_id ? `Order ${receiptText(receipt.order_id)} · ` : ""}${receiptDate(receipt.purchased_on)}${url ? ` · <a href="${receiptAttr(url)}" target="_blank" rel="noopener noreferrer">View purchase history ↗</a>` : ""}</p>`;
}

function receiptDetailMarkup(detail) {
  const t = detail.transaction || {};
  const job = detail.job;
  const allocations = Array.isArray(detail.allocations) ? detail.allocations : [];
  const status = job?.status || t.receipt_status || "none";
  const demo = Boolean(detail.demo || receiptState.summary?.demo);
  let actions = "";
  if (job?.status === "review") {
    const canApply = (job.can_apply === true || job.verified === true) && Array.isArray(job.proposal?.items) && job.proposal.items.length > 0;
    const apply = canApply ? receiptButton("Apply split", "review-accept", job.id, "btn btn-sm btn-primary") : `<button type="button" class="btn btn-sm btn-primary" disabled title="Trusted receipt evidence is required before applying">Apply split</button>`;
    actions = `${receiptButton("Dismiss", "review-dismiss", job.id, "btn btn-sm btn-ghost")}${apply}`;
  }
  else if (["needs_user", "failed"].includes(job?.status)) actions = receiptButton("Continue lookup", "resume", job.id, "btn btn-sm btn-primary");
  else if (["queued", "running"].includes(job?.status)) actions = receiptButton("Refresh status", "detail", t.id, "btn btn-sm btn-ghost");
  else if (job?.status === "applied") actions = receiptButton("Undo split", "undo", t.id, "btn btn-sm btn-ghost");
  else if (job?.status === "dismissed") actions = receiptButton("Look up again", "request", t.id, "btn btn-sm btn-primary");
  else if (!job && !demo) actions = receiptButton("Look up purchase", "request", t.id, "btn btn-primary");
  else if (!job && demo) actions = `<span class="small muted">Unavailable in sample mode</span>`;
  const allocationMarkup = allocations.length ? `<section class="receipt-current"><span class="micro-label">Current budget split</span>${allocations.map(a => `<div class="receipt-item"><span>${receiptText(a.description || "Purchase")}</span><span class="receipt-item-category">${a.cat_name ? receiptText(a.cat_name) : receiptCategory(a.category_id)}</span><strong>${receiptMoney(a.amount_cents)}</strong></div>`).join("")}${receiptEvidenceMarkup(job)}</section>` : "";
  const workerMessage = job?.message || detail.worker?.message;
  const workerGuidance = detail.worker?.instructions || detail.worker?.handoff || detail.worker?.setup;
  return `<button type="button" class="close-button" data-receipt-action="close" aria-label="Close dialog">×</button><h2>Purchase details</h2>
    <div class="receipt-detail-heading"><div><b>${receiptText(receiptDetailName(t, job))}</b>${receiptOriginalName(t)}<small>${receiptDate(t.posted)} · ${fmtMoney(t.amount, { decimals: 2 })}${detail.provider ? ` · ${receiptProvider(detail.provider)}` : ""}</small></div>${receiptStatusTag(status)}</div>
    ${workerMessage ? `<div class="status-panel receipt-detail-status">${receiptText(workerMessage)}</div>` : ""}
    ${workerGuidance && ["needs_user", "failed"].includes(status) ? `<details class="disclosure receipt-worker-guidance" open><summary>What to do next</summary><p class="quiet-note">${receiptText(workerGuidance)}</p></details>` : ""}
    ${job?.status === "review" ? receiptProposalMarkup(job) : ""}${allocationMarkup}
    ${job?.status === "review" ? `<p class="quiet-note">Check the item names and categories before applying. Mixed orders can be split across several budgets.</p>` : ""}
    <div class="modal-actions">${receiptButton("Close", "close", "", "btn")}<span style="flex:1"></span>${actions}</div>`;
}

async function openReceiptDetail(id) {
  if (!receiptState.summary) await loadReceiptSummary();
  const detail = await api(`/receipts/transaction?id=${encodeURIComponent(id)}`);
  receiptState.detail = detail;
  showModal(receiptDetailMarkup(detail));
}

async function receiptRequest(id) {
  if (receiptState.summary?.demo) return toast("Purchase lookup is off in sample mode.", "err");
  await api("/receipts/request", { method: "POST", body: { transaction_id: id } });
  toast("Purchase lookup queued.", "ok");
  await openReceiptDetail(id);
}
async function receiptResume(id) {
  const job = await api("/receipts/resume", { method: "POST", body: { id } });
  toast(job?.message || "Lookup continued.", "ok");
  await openReceiptDetail(job?.transaction_id || receiptState.detail?.transaction?.id);
}
async function receiptReview(id, decision) {
  const detail = receiptState.detail;
  const categoryIds = decision === "accept" ? Array.from(document.querySelectorAll('[data-receipt-category]'), select => select.value) : undefined;
  if (categoryIds?.some(category => !category)) return toast("Choose a category for every item first.", "err");
  await api("/receipts/review", { method: "POST", body: { id, decision, category_ids: categoryIds } });
  toast(decision === "accept" ? "Budget split applied." : "Proposal dismissed.", "ok");
  if (detail?.transaction?.id) { await navigate(state.page); await openReceiptDetail(detail.transaction.id); } else await openReceiptReviewList();
}
async function receiptUndo(id) {
  await api("/receipts/undo", { method: "POST", body: { transaction_id: id } });
  toast("Budget split undone.", "ok");
  await navigate(state.page);
  await openReceiptDetail(id);
}
async function receiptSaveSettings(form) {
  const data = new FormData(form);
  const body = { enabled: data.get("enabled") === "on", auto_apply: data.get("auto_apply") === "on", daily_limit: Math.max(1, Math.min(30, Number(data.get("daily_limit")) || 10)) };
  const summary = await api("/receipts/settings", { method: "POST", body });
  receiptState.summary = { ...(receiptState.summary || {}), settings: summary.settings || summary };
  toast("Purchase settings saved.", "ok");
}

document.addEventListener("click", async event => {
  const button = event.target.closest("[data-receipt-action]");
  if (!button || button.disabled) return;
  event.preventDefault();
  const action = button.dataset.receiptAction;
  const id = button.dataset.receiptId || "";
  button.disabled = true;
  try {
    if (action === "close") closeModal();
    else if (action === "detail") await openReceiptDetail(id);
    else if (action === "review-list") await openReceiptReviewList();
    else if (action === "request") await receiptRequest(id);
    else if (action === "resume") await receiptResume(id);
    else if (action === "review-accept") await receiptReview(id, "accept");
    else if (action === "review-dismiss") await receiptReview(id, "dismiss");
    else if (action === "undo") await receiptUndo(id);
  } catch (error) { toast(error.message || "Purchase details could not be loaded.", "err", 5500); }
  finally { if (button.isConnected) button.disabled = false; }
});
document.addEventListener("submit", async event => {
  const form = event.target.closest("form[data-receipt-settings-form]");
  if (!form) return;
  event.preventDefault();
  const button = form.querySelector("[type=submit]");
  if (button) button.disabled = true;
  try { await receiptSaveSettings(form); } catch (error) { toast(error.message || "Purchase settings could not be saved.", "err"); }
  finally { if (button) button.disabled = false; }
});

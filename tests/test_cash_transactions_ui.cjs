const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'web', 'app2.js'), 'utf8');
const comfort = fs.readFileSync(path.join(root, 'web', 'comfort.js'), 'utf8');

for (const token of [
  'add-cash-tx',
  'Cash / manual',
  'const cash = !t.account_id',
  'body.amount = amount',
  'body.posted = document.getElementById("txe-posted").value',
]) {
  if (!app.includes(token)) throw new Error(`app2.js is missing ${token}`);
}

for (const token of [
  'transactionAccountOptions',
  'openAddTx({cash:true})',
  'account_id:data.account_id||null',
  'Cash / manual entries count in budgets, reports, and cash flow',
]) {
  if (!comfort.includes(token)) throw new Error(`comfort.js is missing ${token}`);
}

if (/if\s*\(!state\.accounts\.length\)\s*return openManualAccount/.test(comfort)) {
  throw new Error('Account-free transaction entry is still blocked');
}

console.log('cash transaction UI wiring verified');

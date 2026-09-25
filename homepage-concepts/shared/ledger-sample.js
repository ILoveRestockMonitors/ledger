/* Ledger homepage concepts: shared sample data.
   Every figure on the five concept pages is computed here from the same
   fictional dataset the app's Demo version uses (backend/demo_preview.py):
   Alex and Juniper Studio, month to date on Thursday, September 24, 2026.
   Nothing is saved and nothing reaches the Ledger server. */
(function (global) {
  'use strict';

  var TODAY = '2026-09-24';
  var MONTH_DAYS = 30;
  var PLAN = 4200;           // September plan, Everything scope
  var TAX_RATE = 0.25;       // business tax set-aside

  var ACCOUNTS = [
    { name: 'Everyday checking', type: 'Checking', scope: 'personal', bal: 6840.25 },
    { name: 'Rainy day savings', type: 'Savings', scope: 'personal', bal: 16200 },
    { name: 'Long-term investments', type: 'Investments', scope: 'personal', bal: 28450 },
    { name: 'Juniper Studio checking', type: 'Checking', scope: 'business', bal: 12860.50 },
    { name: 'Studio rewards card', type: 'Credit card', scope: 'business', bal: -640.75 }
  ];

  var TX = [
    ['t01', '2026-09-01', 'Maple Court rent', 'Rent / Mortgage', 'Everyday checking', -1650, 'personal', 1, 0],
    ['t02', '2026-09-01', 'Cedar Labs payroll', 'Payroll', 'Everyday checking', 2750, 'personal', 0, 0],
    ['t03', '2026-09-02', 'Willow Market', 'Groceries', 'Everyday checking', -92.40, 'personal', 0, 0],
    ['t04', '2026-09-03', 'City transit pass', 'Transport & Fuel', 'Everyday checking', -46.80, 'personal', 0, 0],
    ['t05', '2026-09-03', 'The Workshop desk', 'Studio / Coworking', 'Juniper Studio checking', -280, 'business', 1, 0],
    ['t06', '2026-09-04', 'Juniper Kitchen', 'Dining & Coffee', 'Everyday checking', -32.50, 'personal', 0, 0],
    ['t07', '2026-09-05', 'Linden Design retainer', 'Invoice Payment', 'Juniper Studio checking', 3060, 'business', 0, 0],
    ['t08', '2026-09-06', 'Weekend Supply Co.', 'Shopping', 'Everyday checking', -84.50, 'personal', 0, 0],
    ['t09', '2026-09-07', 'Streamlight TV', 'Subscriptions', 'Everyday checking', -17.99, 'personal', 1, 0],
    ['t10', '2026-09-08', 'Paper & Pine supplies', 'Office Supplies', 'Studio rewards card', -76.50, 'business', 0, 0],
    ['t11', '2026-09-09', 'Willow Market', 'Groceries', 'Everyday checking', -100.55, 'personal', 0, 0],
    ['t12', '2026-09-10', 'Hearth Internet', 'Internet & Phone', 'Everyday checking', -65, 'personal', 1, 0],
    ['t13', '2026-09-11', 'Juniper Kitchen', 'Dining & Coffee', 'Everyday checking', -38.50, 'personal', 0, 0],
    ['t14', '2026-09-11', 'Starlight Cinema', 'Entertainment', 'Everyday checking', -42, 'personal', 0, 0],
    ['t15', '2026-09-12', 'Studio Design Suite', 'Software & SaaS', 'Studio rewards card', -49, 'business', 1, 0],
    ['t16', '2026-09-14', 'Soundwave Music', 'Subscriptions', 'Everyday checking', -10.99, 'personal', 1, 0],
    ['t17', '2026-09-15', 'Cedar Labs payroll', 'Payroll', 'Everyday checking', 2750, 'personal', 0, 0],
    ['t18', '2026-09-16', 'Willow Market', 'Groceries', 'Everyday checking', -108.70, 'personal', 0, 0],
    ['t19', '2026-09-16', 'Ellis Illustration', 'Contractors', 'Juniper Studio checking', -350, 'business', 0, 0],
    ['t20', '2026-09-18', 'Trailside Fitness', 'Health & Fitness', 'Everyday checking', -35, 'personal', 1, 0],
    ['t21', '2026-09-18', 'Juniper Kitchen', 'Dining & Coffee', 'Everyday checking', -44.50, 'personal', 0, 0],
    ['t22', '2026-09-19', 'Harbor House project', 'Invoice Payment', 'Juniper Studio checking', 1250, 'business', 0, 0],
    ['t23', '2026-09-20', 'Transfer to rainy day savings', 'Transfer', 'Everyday checking', -500, 'personal', 0, 1],
    ['t24', '2026-09-20', 'Transfer from everyday checking', 'Transfer', 'Rainy day savings', 500, 'personal', 0, 1],
    ['t25', '2026-09-22', 'Cloudbox Storage', 'Software & SaaS', 'Studio rewards card', -12, 'business', 1, 0],
    ['t26', '2026-09-23', 'Willow Market', 'Groceries', 'Everyday checking', -116.85, 'personal', 0, 0]
  ].map(function (r) {
    return { id: r[0], d: r[1], name: r[2], cat: r[3], acct: r[4], amt: r[5], scope: r[6], rec: !!r[7], transfer: !!r[8] };
  });

  var BUDGETS = [
    ['Groceries', 'personal', 550], ['Dining & Coffee', 'personal', 220], ['Shopping', 'personal', 160],
    ['Entertainment', 'personal', 120], ['Transport & Fuel', 'personal', 150], ['Subscriptions', 'personal', 45],
    ['Software & SaaS', 'business', 100], ['Contractors', 'business', 700]
  ];

  // Scheduled in the app's Upcoming list. Income rows are the recurring
  // deposits the dataset already shows (payroll on the 1st and 15th, the
  // Linden retainer on the 5th); they are labelled as expected, not promised.
  var UPCOMING = [
    ['2026-10-01', 'Maple Court rent', 'personal', -1650, 'Everyday checking', 'Rent / Mortgage'],
    ['2026-10-01', 'Cedar Labs payroll', 'personal', 2750, 'Everyday checking', 'Payroll'],
    ['2026-10-03', 'The Workshop desk', 'business', -280, 'Juniper Studio checking', 'Studio / Coworking'],
    ['2026-10-05', 'Linden Design retainer', 'business', 3060, 'Juniper Studio checking', 'Invoice Payment'],
    ['2026-10-07', 'Streamlight TV', 'personal', -17.99, 'Everyday checking', 'Subscriptions'],
    ['2026-10-10', 'Hearth Internet', 'personal', -65, 'Everyday checking', 'Internet & Phone'],
    ['2026-10-12', 'Studio Design Suite', 'business', -49, 'Studio rewards card', 'Software & SaaS'],
    ['2026-10-14', 'Soundwave Music', 'personal', -10.99, 'Everyday checking', 'Subscriptions'],
    ['2026-10-15', 'Cedar Labs payroll', 'personal', 2750, 'Everyday checking', 'Payroll'],
    ['2026-10-18', 'Trailside Fitness', 'personal', -35, 'Everyday checking', 'Health & Fitness'],
    ['2026-10-22', 'Cloudbox Storage', 'business', -12, 'Studio rewards card', 'Software & SaaS']
  ].map(function (r) {
    return { d: r[0], name: r[1], scope: r[2], amt: r[3], acct: r[4], cat: r[5], income: r[3] > 0 };
  });

  var GOALS = [
    { name: 'A softer landing', scope: 'personal', saved: 16200, target: 20000, monthly: 500, by: 'May 2027' },
    { name: 'A week in Kyoto', scope: 'personal', saved: 2450, target: 6000, monthly: 300, by: 'Oct 2027' },
    { name: 'Studio upgrade', scope: 'business', saved: 1800, target: 4000, monthly: 250, by: 'Jul 2027' }
  ];

  var REVIEWS = [
    { id: 'cloud', title: 'Cloudbox Storage looks recurring', detail: '$12.00 a month on the Studio rewards card', scope: 'business', yes: 'Track it', no: 'Not recurring' },
    { id: 'suite', title: 'Studio Design Suite changed price', detail: 'Planned $49.00, latest charge $54.00', scope: 'business', yes: 'Use $54.00', no: 'Keep $49.00' }
  ];

  // Dollarwise-style 50/30/20 sorting of personal spending.
  var NEEDS = ['Rent / Mortgage', 'Groceries', 'Transport & Fuel', 'Internet & Phone', 'Utilities', 'Insurance'];
  var WANTS = ['Dining & Coffee', 'Shopping', 'Entertainment', 'Subscriptions', 'Health & Fitness', 'Travel', 'Personal Care'];

  var LABEL = { everything: 'Everything', personal: 'Personal', business: 'Business' };
  var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var FULL = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  var DOW = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

  var r2 = function (n) { return Math.round(n * 100) / 100; };
  var sum = function (list, f) { return r2(list.reduce(function (s, x) { return s + f(x); }, 0)); };
  var inScope = function (scope) { return function (x) { return scope === 'everything' || !scope || x.scope === scope; }; };

  function money(n, opt) {
    opt = opt || {};
    var v = r2(n);
    var digits = opt.whole ? 0 : 2;
    var s = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
    var sign = v < 0 ? '−' : (opt.sign && v > 0 ? '+' : '');
    return sign + '$' + s;
  }
  function day(d) { return MON[+d.slice(5, 7) - 1] + ' ' + (+d.slice(8, 10)); }
  function dayLong(d) {
    var dt = new Date(d + 'T12:00:00');
    return DOW[dt.getDay()] + ', ' + FULL[dt.getMonth()] + ' ' + dt.getDate();
  }
  function pct(a, b) { return b ? Math.round(a / b * 100) : 0; }
  function initials(n) {
    return n.replace(/[^A-Za-z ]/g, '').split(' ').filter(Boolean).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase();
  }
  function daysBetween(a, b) { return Math.round((new Date(b + 'T12:00:00') - new Date(a + 'T12:00:00')) / 864e5); }
  function addDays(d, n) {
    var dt = new Date(d + 'T12:00:00'); dt.setDate(dt.getDate() + n);
    return dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0') + '-' + String(dt.getDate()).padStart(2, '0');
  }

  function create() {
    // A fresh working copy per page, so each concept can add or move things.
    var tx = TX.map(function (t) { return Object.assign({}, t); });
    var reviewed = {};

    function spendTx(scope, upto) {
      return tx.filter(function (t) { return !t.transfer && t.amt < 0 && inScope(scope)(t) && (!upto || t.d <= upto); });
    }
    function flows(scope, upto) {
      var list = tx.filter(function (t) { return !t.transfer && inScope(scope)(t) && (!upto || t.d <= upto); });
      var inc = sum(list.filter(function (t) { return t.amt > 0; }), function (t) { return t.amt; });
      var out = sum(list.filter(function (t) { return t.amt < 0; }), function (t) { return -t.amt; });
      return { inc: inc, out: out, net: r2(inc - out) };
    }
    function bucketOf(t) {
      if (t.transfer) return t.amt < 0 && /savings/i.test(t.name) ? 'savings' : null;
      if (t.bucket) return t.bucket;
      if (t.scope !== 'personal' || t.amt >= 0) return null;
      if (NEEDS.indexOf(t.cat) >= 0) return 'needs';
      if (WANTS.indexOf(t.cat) >= 0) return 'wants';
      return 'wants';
    }
    // baseIncome: optional month income to set the 50/30/20 targets from
    function buckets(upto, baseIncome) {
      var income = baseIncome || flows('personal', upto).inc;
      var out = { needs: [], wants: [], savings: [] };
      tx.forEach(function (t) {
        if (upto && t.d > upto) return;
        var b = bucketOf(t); if (b) out[b].push(t);
      });
      var mk = function (key, share, label) {
        var spent = sum(out[key], function (t) { return -t.amt; });
        var target = r2(income * share);
        return { key: key, label: label, share: share, spent: spent, target: target, left: r2(target - spent), pct: pct(spent, target), ofIncome: pct(spent, income), tx: out[key] };
      };
      return { income: income, needs: mk('needs', 0.5, 'Needs'), wants: mk('wants', 0.3, 'Wants'), savings: mk('savings', 0.2, 'Savings') };
    }
    function plan(upto) {
      var spent = flows('everything', upto).out;
      var today = upto || TODAY;
      var daysLeft = MONTH_DAYS - (+today.slice(8, 10));
      var left = r2(PLAN - spent);
      return { limit: PLAN, spent: spent, left: left, pct: pct(spent, PLAN), daysLeft: daysLeft, perDay: daysLeft ? r2(left / daysLeft) : left };
    }
    function budgets(scope) {
      return BUDGETS.filter(function (b) { return inScope(scope)({ scope: b[1] }); }).map(function (b) {
        var list = spendTx(b[1]).filter(function (t) { return t.cat === b[0]; });
        var spent = sum(list, function (t) { return -t.amt; });
        var p = pct(spent, b[2]);
        return { name: b[0], scope: b[1], limit: b[2], spent: spent, left: r2(b[2] - spent), pct: p, status: p >= 100 ? 'over' : p >= 80 ? 'near' : 'ok', tx: list };
      });
    }
    function scopeBudget(scope) {
      if (scope === 'everything') { var p = plan(); return { label: 'September plan', limit: p.limit, spent: p.spent, left: p.left, pct: p.pct }; }
      var list = budgets(scope);
      var limit = sum(list, function (b) { return b.limit; }), spent = sum(list, function (b) { return b.spent; });
      return { label: LABEL[scope] + ' budgets', limit: limit, spent: spent, left: r2(limit - spent), pct: pct(spent, limit) };
    }
    function accounts(scope) { return ACCOUNTS.filter(inScope(scope)); }
    function netWorth(scope) { return sum(accounts(scope), function (a) { return a.bal; }); }
    function categories(scope) {
      var m = {};
      spendTx(scope).forEach(function (t) {
        var k = t.scope + '|' + t.cat;
        if (!m[k]) m[k] = { name: t.cat, scope: t.scope, amt: 0, tx: [] };
        m[k].amt = r2(m[k].amt - t.amt); m[k].tx.push(t);
      });
      return Object.keys(m).map(function (k) { return m[k]; }).sort(function (a, b) { return b.amt - a.amt; });
    }
    function recent(scope, n) {
      return tx.filter(inScope(scope)).sort(function (a, b) { return b.d.localeCompare(a.d) || b.id.localeCompare(a.id); })
        .filter(function (t) { return !(t.transfer && t.amt > 0); }).slice(0, n || 6);
    }
    function week() {
      var from = addDays(TODAY, -6);
      return tx.filter(function (t) { return t.d >= from && t.d <= TODAY && !(t.transfer && t.amt > 0); })
        .sort(function (a, b) { return a.d.localeCompare(b.d) || a.id.localeCompare(b.id); });
    }
    function upcoming(scope, days) {
      var until = addDays(TODAY, days || 30);
      return UPCOMING.filter(inScope(scope)).filter(function (u) {
        return u.d <= until && !(u.name === 'Cloudbox Storage' && reviewed.cloud === 'no');
      }).map(function (u) {
        var amt = u.amt;
        if (u.name === 'Studio Design Suite' && reviewed.suite === 'yes') amt = -54;
        return Object.assign({}, u, { amt: amt });
      });
    }
    function goals(scope) {
      return GOALS.filter(inScope(scope)).map(function (g) {
        var months = Math.ceil((g.target - g.saved) / g.monthly);
        return Object.assign({}, g, { pct: pct(g.saved, g.target), left: r2(g.target - g.saved), months: months });
      });
    }
    function reviews() { return REVIEWS.filter(function (r) { return !reviewed[r.id]; }); }
    function review(id, answer) { reviewed[id] = answer; }
    // Cash in the scope's checking accounts, day by day for the next N days.
    function forecast(scope, days) {
      days = days || 30;
      var cashAccts = accounts(scope).filter(function (a) { return a.type === 'Checking'; });
      var start = sum(cashAccts, function (a) { return a.bal; });
      var names = cashAccts.map(function (a) { return a.name; });
      var items = upcoming(scope, days).filter(function (u) { return names.indexOf(u.acct) >= 0; });
      var out = [], bal = start;
      for (var i = 0; i <= days; i++) {
        var d = addDays(TODAY, i);
        var todays = i === 0 ? [] : items.filter(function (u) { return u.d === d; });
        todays.forEach(function (u) { bal = r2(bal + u.amt); });
        out.push({ d: d, bal: bal, events: todays });
      }
      return { start: start, accounts: cashAccts, days: out, items: items };
    }
    function addTx(t) {
      var n = Object.assign({ id: 'n' + Date.now() + Math.floor(Math.random() * 1000), d: TODAY, acct: 'Cash / manual', rec: false, transfer: false }, t);
      tx.push(n); return n;
    }
    function setBucket(id, bucket) { tx.forEach(function (t) { if (t.id === id) t.bucket = bucket; }); }

    return {
      tx: tx, flows: flows, buckets: buckets, bucketOf: bucketOf, plan: plan, budgets: budgets, scopeBudget: scopeBudget,
      accounts: accounts, netWorth: netWorth, categories: categories, recent: recent, week: week,
      upcoming: upcoming, goals: goals, reviews: reviews, review: review, forecast: forecast,
      addTx: addTx, setBucket: setBucket, spendTx: spendTx
    };
  }

  global.LedgerSample = {
    TODAY: TODAY, MONTH_DAYS: MONTH_DAYS, PLAN: PLAN, TAX_RATE: TAX_RATE, LABEL: LABEL, MON: MON, FULL: FULL,
    NEEDS: NEEDS, WANTS: WANTS, CATS: {
      personal: ['Groceries', 'Dining & Coffee', 'Rent / Mortgage', 'Utilities', 'Internet & Phone', 'Transport & Fuel', 'Shopping', 'Health & Fitness', 'Subscriptions', 'Entertainment', 'Travel'],
      business: ['Software & SaaS', 'Contractors', 'Office Supplies', 'Studio / Coworking', 'Advertising', 'Business Meals', 'Other Business']
    },
    money: money, day: day, dayLong: dayLong, pct: pct, initials: initials, addDays: addDays, daysBetween: daysBetween, r2: r2, sum: sum,
    create: create
  };
})(window);

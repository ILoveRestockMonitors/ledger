# Subscription detection logic

The review queue must not ask whether routine fast-food, restaurant, coffee,
grocery, retail website or vehicle-fuel purchases are subscriptions. Preserve early detection
for known recurring services and unfamiliar renewals supported by explicit subscription or recurring-bill evidence. Annual is the longest detected cadence; the screenshot showing 435 days as annual must be rejected.

## Decision

Filter everyday spending by normalized merchant phrases and transaction
categories before candidate creation or activation. Use word boundaries to
avoid matching Shellshock as Shell or BPCloud as BP. Narrow, named membership
products (such as DashPass and Costco Membership) and gas-utility descriptions
remain eligible. Manual records and explicit confirmation/cancellation decisions
remain authoritative; recurring dining charges can still be tracked manually.

Require positive service evidence before considering timing: a recognized
subscription product, a Subscriptions/recurring-bill category, or an explicit
subscription/membership/billing-plan description. Neutral website names and
repeated shopping orders do not qualify. General Software & SaaS classification
alone does not prove a recurring service. Existing unconfirmed records cannot
serve as their own evidence. Explicit annual/yearly descriptions keep a known
service's first observed charge from being defaulted to monthly.

Validate individual billing intervals instead of trusting their average.
Cadence matching allows at most seven days of drift, including annual renewals;
365- and 366-day annual intervals qualify, while 435-day intervals do not.
No automatic evidence gap may exceed 372 days, even when testing skipped cycles. Two
charges at a supported cadence remain reviewable. Unusual custom cycles need
three charges at consistent intervals of at least seven days. A supported
calendar cadence with an observed normal cycle and up to two missing cycles
remains a candidate, with an explicit missing-cycle reason and correct next due.
Unfamiliar merchants with amount spread above 35% need utility/bill evidence;
known recurring services and existing active price-change reviews retain their
current handling. Existing activation confidence and variation thresholds stay.

Old unconfirmed false detections become hidden using the existing dismissed
status, without creating a user dismissal in subscription_learning. This lets
corrected categorization restore a legitimate inference. Scans run on normal
server startup and existing scan/sync/edit paths so persisted false suggestions
are re-evaluated. Financial transactions are never rewritten by this cleanup.

## Alternatives considered

A merchant-only blocklist fixes familiar chains but misses local businesses.
Raising the overall confidence threshold reduces useful early detection.
Combining merchant/category evidence and billing-pattern checks addresses both
problems while retaining the current early-review behavior.

## Verification

Synthetic SQLite regression tests cover two-charge fast food, gas stations,
unknown merchants with dining/fuel categories, ordinary websites with regular purchases, the exact 435-day screenshot case, annual/leap-year renewals, explicit annual descriptions, merchant word boundaries,
membership exceptions, gas utilities, irregular/daily spending, varying amounts,
weekly/custom/annual/month-end renewals, missing months, manual/confirmed/canceled
records, learned dismissals, old false-positive cleanup and price reviews. An
API regression checks the scan and listing responses used by the UI. Existing
desktop lifecycle tests exercise server startup. Run from the release folder:

```sh
python3 -m unittest discover -s tests
```

This change targets the maintained `ledger-v2-release` source. Historical ZIPs
and reconstruction snapshots are unchanged. Hosted deployment and release
publication are separate from this local implementation.

Final local validation: all 136 backend tests passed, including 20 new detector
and API regressions. `git diff --check` passed for all changed application and
test files. The test runtime emitted non-failing SQLite resource warnings.

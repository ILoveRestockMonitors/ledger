# Sarah spending view and mobile navigation

Sarah's Home adds a monthly “budget · without rent” card to the right of the existing budget on wide screens; it stacks below the budget on phones and narrower layouts. Cornelious does not show the extra card and retains its existing grid. The month follows the current monthly dashboard, so September advances naturally when the month changes.

The value uses the same complete category totals as the spending constellation, including split-purchase allocations. It sums posted expenses outside the Rent / Mortgage category in integer cents. Transfers, pending payments and future commitments are excluded. The existing overall plan is unchanged; this card does not invent a separate non-rent budget target. Selecting its amount opens the included category breakdown.

On mobile, both palettes use opaque, content-sized navigation drawers. Content exceeding the viewport remains scrollable. The Home pull-down gesture is capped at 52px; releasing past 40px reloads Home summaries once, without invoking bank sync. The revealed strip and outer overscroll canvas are beige. Controls, dialogs, menus, horizontal/nested scrolling and desktop gestures are excluded.

Validation includes arithmetic edge cases and reconciliation with the existing monthly total, palette visibility and responsive layout, drawer opacity and sizing, and bounded refresh gesture behavior. Native Safari/iPhone rubber-band behavior still needs physical-device verification; browser checks cannot substitute for that.

Completed checks: four arithmetic edge cases; demo monthly reconciliation ($4,703.30 total − $1,620.34 rent = $3,082.96); 24 combined palette/theme layouts; 24 drawer states; nine gesture scenarios; category detail dialog; and native Chromium touch input confirming the 52px cap and a single read-only refresh. Desktop fit was checked at 1101, 1280 and 1440px. No page errors were observed in the integrated pass.

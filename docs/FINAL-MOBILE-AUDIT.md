# Final mobile audit — September 5, 2026

A second review covers small phones, landscape and breakpoint layouts, both palettes and themes, dialog scrolling and focus, navigation history, date filters, and deployed service health.

## Correction

Closing a mobile dialog tried to restore focus while the floating Add button was still hidden by modal-state styling. Focus restoration now waits for the next frame, checks that the original control is present and usable, and avoids taking focus from a newly opened dialog. Direct browser verification confirmed focus returns to Add.

## Verification

All 116 backend tests pass, including finance, receipt invariants, authentication, reports and desktop lifecycle. The first sandboxed attempt could not bind local sockets; the permitted rerun passed. The production services are running and recent mobile logs contain no errors.

Detailed browser results are retained in the local QA artifacts. Browser mobile emulation and WebKit checks do not replace testing on a physical iPhone with its keyboard, low-power mode and network conditions.

Final browser results: 308 Chromium layout cases passed across seven viewport sizes, both palettes, both themes and eleven routes. No horizontal overflow, page errors, or visible mobile inputs below 16px were found. Small-phone dialog scrolling, invalid amount validation, Escape/reopening, drawer navigation, browser Back, palette persistence, focus restoration, replacement-dialog focus and simulated API error recovery passed.

WebKit validation remains unavailable: the temporary WebKit runtime timed out even on a blank data-URL page and then reported a missing web frame. This is a test-runtime failure, not a passing Safari result. Physical Safari/iPhone verification remains outstanding.

## Sign-in animation follow-up
The sign-in screen mounts directly under `body` after its asynchronous authentication check. Motion enhancement previously observed only route and dialog containers, so the sign-in button could miss its hover/tap animation. Direct body insertions are now observed as well. A signed-out browser regression confirms the login button receives motion and honors reduced-motion preferences.

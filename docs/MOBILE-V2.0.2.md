# V2.0.2 — Mobile readability and motion

The emailed Transactions screenshot showed controls nearly transparent over Sarah's forest background and two unlabeled empty date fields. Filters now sit on a readable panel with solid input surfaces and visible From/To labels. Phone date fields share one compact row.

Phone layouts keep the stream, leaf shapes, and animated tints, while removing stacked backdrop blur over moving video. A single smaller tint layer replaces two oversized layers on phones. Scrolling, open navigation, and form entry pause decorative animation and the video; the video retains its current frame and resumes afterward. Mobile palette switches use a 280ms color wash instead of a full-screen clipped snapshot. Touch feedback is shorter; desktop hover effects remain.

Validation: JavaScript syntax checks and browser checks for filter readability, drawer motion suspension, and theme switching. Responsive regression and scroll/filter checks are recorded in the local QA report. These are browser-emulated mobile checks, not a physical iPhone frame-rate measurement. Backend and financial data are unchanged.

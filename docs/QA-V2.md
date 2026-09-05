# V2 web and mobile QA

Scope: full Ledger routes on isolated demo data, Sarah and Cornelious, light/dark, 320/390/768/1024/1440 pixel browser viewports. Production checks are read-only; no real financial records are changed.

## Corrections

- Settings now offers Sarah and Cornelious and correctly describes their assigned Lora/Manrope fonts, replacing obsolete controls that no longer represented the design.
- Homepage cards follow the saved order from dashboard settings.
- A closed phone drawer is inert, preventing keyboard navigation into offscreen controls.
- Tablet headers no longer overflow when desktop secondary actions compete with the title.
- The separate snapshot showcase permits local presentation preferences while continuing to reject financial writes.

## Verification

The initial 176-case sweep found no JavaScript exceptions or page rendering errors. It identified tablet toolbar overflow, corrected in this patch. The corrected 220-case sweep (five widths × two palettes × two appearances × eleven routes) completed with zero JavaScript errors, zero page-render errors and zero document horizontal overflows. Targeted form, focus, ordering and appearance checks were completed directly in the browser; the separate functional runner had startup/click timing failures and is not counted as passing. Demo transaction saving, chart ranges, category leaves and pause/resume were exercised in-browser.

This is browser-based responsive testing, not a native iPhone or Windows device certification. Bank linking and cancellation agents were not invoked against real accounts.

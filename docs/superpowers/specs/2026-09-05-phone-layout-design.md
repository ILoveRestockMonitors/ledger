# Phone layout

The owner requested a mobile layout for Chrome and deployment to the existing
private hosted instance. Preserve the chosen paper palette, Lora headings,
existing dark theme, desktop layout, records, authentication and bank settings.

## Design

At phone widths up to 700 CSS pixels, use bottom navigation for Home, Spending,
Budgets and More. More opens the existing full navigation so subscriptions,
reports, projections, accounts and settings remain accessible. Keep Add a
transaction within thumb reach above navigation. Respect device safe areas.

Use readable form text and touch targets, stack narrow controls and summary
cards when needed, and constrain wide financial tables to their own scroll
regions. Preserve report category/month relationships. Do not hide financial
columns or change calculations to make a table fit.

The navigation drawer must support dismissal, keyboard focus containment and
return, and must not leave the main content inert after a viewport change.
Login and transaction dialogs take precedence over phone navigation. The
keyboard should not obscure the active form behind a fixed navigation bar.

## Implementation and verification

Keep phone changes in dedicated CSS and JavaScript loaded after existing
styles and behavior. Use existing routes and transaction actions. No backend
or financial data migrations are needed.

Exercise the main routes in isolated synthetic-data Chromium sessions at
320, 390 and 430 pixels, plus a desktop regression check. Inspect rendered
screenshots, overflow, navigation, transaction entry, drawer dismissal, and
both appearance modes. Browser emulation does not prove native iPhone keyboard
or installed-app behavior; those require a device check.

Deploy a frontend-only image overlay with an immutable prior image available
for rollback. Retain the existing data volume, environment and private network
configuration. Verify deployed asset bytes and authenticated API protection.
Deployment addresses and personal details belong only in private operations
notes, never in this repository.

## Verification completed

Chromium passed all eleven application routes in light and dark mode at 320,
390 and 430 pixel phone widths and at 1280 pixels on desktop, with no page
overflow or JavaScript errors. Synthetic transaction entry succeeded at each
phone width. Additional checks covered login hiding navigation, drawer focus
cycling and Escape, opening transaction entry from the drawer, programmatic
navigation, restoring desktop accessibility after resizing, and keeping the
full category/month matrix inside its own horizontal scroll region.

The final phone layout explicitly sizes the main container and view to the
viewport and prevents automatic text inflation while preserving browser zoom.
This addresses the inconsistent card widths observed in the supplied phone
screenshots. Native iPhone rendering and keyboard behavior still require a
device check after refreshing the deployed app.

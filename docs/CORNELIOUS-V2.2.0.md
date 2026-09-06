# Cornelious V2.2.0 — elemental backgrounds and dashboard polish

Prepared September 5, 2026. The user approved this release for all existing distribution targets. Rollout is pending; deployment results belong in the workspace's `V2-DEPLOYMENT.md` after verification.

This release updates Cornelious (`data-review-mode="aurora"`) in both light and dark modes. Sarah's layout, woodland background and styling are outside this change. No financial calculations, authentication, API behavior or stored financial records are changed by these frontend additions.

## Appearance and motion

- Dark mode uses the approved generated Zekrom storm still and a Seedance 2.0 Mini video loop. Branching white/blue lightning fades in and out within the hovered control. It follows that control's bounds and corner radius; it does not cover the whole page.
- Light mode uses the approved Reshiram still and the user's Google Flow video. Deep orange replaces the earlier red accents, orange gradients color the spending bars, and muted gold replaces green accent channels to match the warm background.
- Light-mode hover fire uses layered canvas ribbons with bright warm cores, soft edges and rising embers. Flames appear and fade independently. The center remains stronger while the outer mask makes nearby values easier to read.
- Actionable words turn ice blue in dark mode and orange in light mode on hover or keyboard focus. Filled primary buttons keep white labels in both modes. The net-income bubble keeps white hover text in dark mode and uses black hover text in light mode, following the final requested exception.
- Decorative hover shadows were removed. The appearance switch previews the destination's fire or lightning treatment. Decorative layers do not intercept input and are hidden from assistive technology.
- Both videos are muted, looped and played inline. They pause for hidden documents, reduced-motion preferences, the existing motion pause control and mobile activity. The appropriate still remains available when playback is disabled or fails. Only the active Cornelious theme displays its video.

## Layout and readability

Account headings, the bank connection/sync area, the spending-report heading, filters and export control use the same translucent panel material as other cards. The larger header/control panels use 22px backdrop blur and 140% saturation. The final treatment is glass, rather than the completely opaque boxes from the intermediate revision.

On phones, dashboard cards use the desktop panel background and the same 22px blur. Zekrom's portrait crop uses 72% horizontal positioning; Reshiram uses 42% to keep the face visible. Reshiram's desktop still and video are shifted right by 9vw from right alignment. The still and video crops use matching positions within each theme.

The desktop dashboard packs recent transactions, upcoming payments and monthly spending more tightly. Upcoming payments and monthly spending can share a row, with 4/8-column widths above 1100px and 6/6-column widths from 701px to 1100px.

Cornelious dashboard cards now have a hold-to-drag handle. Hold for 300ms and release over another card to move it before that card; arrow keys on the focused handle also reorder cards, and Escape cancels dragging. A Reset layout button restores the default arrangement. Order is saved locally under `ledger-cornelious-card-order-v1`, shared between light/dark and other same-origin windows. It is a browser preference, not a server-synced layout. Sarah's card order does not use this override.

## Media and provenance

| Active asset | Origin | Actual dimensions / duration |
| --- | --- | --- |
| `web/zekrom-storm-background-v1.png` | Approved AI-generated Zekrom still | 1672 × 941 |
| `web/zekrom-storm-loop.mp4` | Seedance 2.0 Mini, processed for a smoother restart | 1280 × 720, 24fps, 127 frames, 5.291667s |
| `web/reshiram-sunfire-background-v3.png` | Approved AI-generated Reshiram still | 1672 × 941 |
| `web/reshiram-sunfire-loop.mp4` | User-provided Google Flow video, processed for a smoother restart | 1280 × 720, 24fps, 222 frames, 9.25s |
| `web/reshiram-video-poster.jpg` | Poster for the supplied Reshiram clip | Video poster / loading fallback |

The Reshiram source was `Reshiram_soaring_with_fire_tail_202609052139.mp4`, supplied from the user's Downloads folder. It contains 240 video frames at 1280 × 720 and 24fps; its container duration is 10.005333s. A 0.75s overlap reduces the processed loop to 9.25s. The active Reshiram video came from the user; the rejected Seedance Reshiram attempt did not produce this asset.

Neither still is native 4K. The video backgrounds are 720p, not 1680 × 720 or 4K. See `web/cornelious-artwork.md` for artwork attribution and the retained official reference files.

## Validation and limits

Local `ffprobe` inspection confirms the video dimensions, frame rates, frame counts and durations above. Image metadata confirms the actual still dimensions.

Saved loop measurements in the workspace's `output/imagegen/` are:

| Evidence | Restart frame difference | Average adjacent-frame difference |
| --- | --- | --- |
| `reshiram-loop-check.json` | 2.203542 | 1.879221 |
| `zekrom-loop-check.json` | 1.608889 | 1.330590 |

These are image-difference measurements used to assess the restart seam, not a guarantee that every frame transition will be imperceptible. The saved Zekrom check also records playing desktop/mobile previews, muted looping, pausing/hiding in light mode, resuming in dark mode and the mobile card blur value.

Native iPhone/Safari playback, physical-device performance and native Windows first launch have not been tested for this release. Do not label those platforms as validated based on Chromium previews. Deployment health, asset hashes, package checksums and any additional release tests must be recorded after they run.

## Implementation map

- `web/cornelious-pokemon.css`: Cornelious palette, background crops, glass surfaces, hover exceptions and dashboard layout styling.
- `web/cornelious-pokemon.js`: still-background mounting, hover fire and appearance-switch feedback.
- `web/cornelious-storm.js`: control-bound branching lightning.
- `web/zekrom-video.js` and `web/reshiram-video.js`: theme-specific video playback and still fallback.
- `web/cornelious-layout.js`: hold-to-drag/keyboard card ordering and local persistence.
- `web/aurora.js`: avoids replacing Cornelious' light-mode orange accent with the saved alternate accent; Sarah's existing branch remains unchanged.
- `web/index.html`: includes the Cornelious assets. The separate design showcase mirrors them in `ledger-concepts/v2-showcase/`, with its existing fictional-data and write restrictions retained.

API credentials and provider job URLs are not release assets. Generated-media job records in the workspace are not required by the frontend.

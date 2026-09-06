# Twin-dragon backdrop

The dashboard backdrop is a pair of themed compositions built around two original
dragons: an ivory dragon wreathed in white-gold fire for the light theme, and an
obsidian dragon wreathed in cyan lightning for the dark one. Light is truth and
flame, dark is ideals and electricity.

The creature is an original design. It borrows the archetype — a rearing dragon
carrying a ring of energy at its tail — rather than any published character art,
so nothing trademarked ships in the repository.

## What is in the repository

| File | Role |
| --- | --- |
| `web/dragon-background.css` | Layer stack, both theme palettes, readability scrim, reduced-motion and paused states |
| `web/dragon-background.js` | Inline SVG creature plus the canvas that paints embers, flame, motes and lightning |
| `web/dragon-background.json` | Optional per-theme video source (see below) |

The backdrop renders procedurally, so it costs about 20 KB rather than the several
megabytes a pair of 4K stills would add, it stays sharp at any resolution, and it
retints itself instantly when the theme changes.

### Layers, back to front

1. `.dragon-sky` — the theme gradient.
2. `.dragon-cloud-far` / `.dragon-cloud-near` — one fractal-noise mask painted
   through a themed gradient, drifting at two speeds.
3. `.dragon-haze` — warm blooms in light, violet nebular haze in dark.
4. `.dragon-rays` — light shafts, visible in the light theme only.
5. `.dragon-aura` — the glow the tail ring casts, breathing on a 9 s cycle.
6. `.dragon-figure` — the creature. Its body is drawn as three stroked spines
   (slim neck, heavy torso, tapering tail) with every rim stroke laid down before
   every fill, which leaves one clean outline around the union of the shapes.
7. `.dragon-fx` — the canvas. Light paints rising embers and a flame plume over
   the ring; dark paints drifting motes, a constant crackle around the ring, and
   branching lightning strikes every few seconds.
8. `.dragon-scrim` — a left-weighted wash plus vignette, heaviest where the
   headings sit and thinnest over the creature.

### Motion and accessibility

Motion stops for `prefers-reduced-motion: reduce`, for the sidebar's
**Pause animations** control (`data-motion-paused`), and while the tab is hidden.
In each case the canvas holds a single composed still rather than going blank.

The canvas runs at 30 fps rather than 60, because the backdrop sits under cards
that use `backdrop-filter`, and every painted frame makes those cards re-blur.
When frames still arrive late the loop first thins the particle count and then
steps its own interval down to 20 and 12 fps. On a machine without GPU
compositing the glass cards are the ceiling, not the effects: with
`backdrop-filter` disabled the same scene more than doubles its frame rate.

Cards get a small extra veil (`--d-card-veil`) while the backdrop is on. Without
it the fire ring bleeds through card interiors and pulls secondary text down; with
it, every sampled label matches or beats its contrast from before this change.

While `data-dragon-bg="on"` is set, the Sarah forest video layer stands down.
Clearing that attribute brings the old backdrop back.

## Turning the stills into a Seedance 2.0 animation

Two photoreal 16:9 stills were generated to match these compositions and are in
the Higgsfield library for this account (2752 x 1536, model `nano_banana_2`):

- **Light — ivory dragon, cloud sea, white-gold fire turbine**
- **Dark — obsidian dragon, storm sky, cyan generator ring**

They are not committed here: this session's egress policy blocks the Higgsfield
CDN host (`d8j0ntlcm91z4.cloudfront.net`), so the bytes could not be pulled into
the repository. Download them from the Higgsfield library when you want them.

Feed each still to Seedance 2.0 as the first frame, with the prompt below.

### Light — "Truth"

> Subtle ambient motion, locked-off camera with a very slow push-in. The cloud sea
> drifts slowly from left to right. The ring of white-gold fire behind the dragon
> rotates slowly and throws swirling flame vortices; orange embers lift
> continuously off the fire and drift up through the frame, glowing and fading.
> Heat shimmer distorts the air just above the ring. The dragon breathes almost
> imperceptibly, the down along its neck ruffling in the updraft, and its head
> turns a few degrees. Long god rays sweep gently across the sky. No cuts, no
> camera shake, nothing new enters the frame.

### Dark — "Ideals"

> Subtle ambient motion, locked-off camera with a very slow push-in. Storm clouds
> churn slowly. The cylindrical generator ring at the dragon's tail spins and
> crackles continuously with white-cyan electricity, and thin filaments creep
> along the armoured ridges of its back. Every few seconds a branching bolt of
> lightning arcs out from the ring across the sky, briefly lighting the clouds
> from within, then fades. Glowing cyan motes drift upward. The dragon breathes
> slowly, its cyan eye pulsing faintly, and its head turns a few degrees. No cuts,
> no camera shake, nothing new enters the frame.

### Settings that matter

- Keep the camera nearly locked. A backdrop that pans pulls the eye off the data.
- 5 s is enough; the motion is ambient and loops well.
- Generate at the largest resolution offered, then encode down — see below.
- The left two thirds of both stills is intentionally quiet. Any prompt that adds
  motion there will fight the dashboard, so keep the action around the ring.

### Dropping the render into the site

Encode to H.264 MP4, no audio, and keep each file well under a couple of
megabytes so the backdrop never delays first paint:

```sh
ffmpeg -i truth.mp4  -an -vf "scale=1920:-2,fps=24" -c:v libx264 -crf 30 -preset slow -movflags +faststart web/dragon-light.mp4
ffmpeg -i ideals.mp4 -an -vf "scale=1920:-2,fps=24" -c:v libx264 -crf 30 -preset slow -movflags +faststart web/dragon-dark.mp4
```

Then point `web/dragon-background.json` at them:

```json
{"light": "/dragon-light.mp4", "dark": "/dragon-dark.mp4"}
```

The layer picks up the file for the current theme, cross-fades the procedural sky
and creature out behind it, and keeps painting embers and lightning on the canvas
over the top. Only paths matching `/^\/[a-zA-Z0-9/_-]+\.mp4$/` are accepted, and a
video that fails to load falls back to the procedural composition. Set either
value back to `null` to return that theme to the drawn backdrop.

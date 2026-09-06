# Cornelious artwork and background video

Updated for V2.2.0. These assets appear only in Cornelious' design. Sarah's woodland artwork and layout are unchanged.

## Active backgrounds

| Mode | Still fallback | Video |
| --- | --- | --- |
| Dark | `zekrom-storm-background-v1.png` — approved AI-generated image, 1672 × 941 | `zekrom-storm-loop.mp4` — Seedance 2.0 Mini, 1280 × 720 at 24fps, 127 frames / 5.291667s |
| Light | `reshiram-sunfire-background-v3.png` — approved AI-generated image, 1672 × 941 | `reshiram-sunfire-loop.mp4` — user-provided Google Flow video, 1280 × 720 at 24fps, 222 frames / 9.25s |

`reshiram-video-poster.jpg` is the loading poster for the light-mode clip. Earlier Reshiram still revisions remain as historical assets; the CSS currently selects v3.

The original Flow clip was supplied by the user as `Reshiram_soaring_with_fire_tail_202609052139.mp4`. Its 240-frame video stream is 1280 × 720 at 24fps. The processed 9.25s version uses a 0.75s overlap to soften the loop restart. The active Reshiram clip is not the failed Seedance attempt.

Neither generated still is native 4K. Both shipped videos are 720p. Playback is muted and inline, with still fallbacks and the app's existing motion controls respected.

Workspace evidence is retained in `output/imagegen/reshiram-loop-check.json` (restart difference 2.203542; average adjacent difference 1.879221) and `output/imagegen/zekrom-loop-check.json` (1.608889 and 1.330590 respectively). These measurements help assess the seam and do not guarantee an imperceptible loop on every device.

## Original official reference illustrations

The initial transparent images `zekrom.png` and `reshiram.png` are official Pokédex illustrations. They are distinct from the generated full-scene backgrounds and remain in the asset set.

- Zekrom: [Official Pokédex entry](https://zukan.pokemon.co.jp/detail/0644) and [reference illustration](https://zukan.pokemon.co.jp/zukan-api/up/images/index/4449f3e1ba5f48086fd2b16dc3eb36b1.png).
- Reshiram: [Official Pokédex entry](https://zukan.pokemon.co.jp/detail/0643) and [reference illustration](https://zukan.pokemon.co.jp/zukan-api/up/images/index/a6e4d980898b0a067db65bc38d93b25f.png).

Pokémon characters and official artwork belong to their respective rights holders. Generated and user-supplied media are identified here by provenance, without implying endorsement or an ownership transfer.

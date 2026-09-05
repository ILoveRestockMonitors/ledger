# Ledger design handoff

Everything needed to implement the redesign, packaged for a coding agent that has not seen the
conversation this came out of.

## What to hand over

| | |
|---|---|
| **`DESIGN-PROMPT.md`** | **The brief. Paste this in whole.** Self-contained: constraints, token contract for all three directions, motion rules, component specs, phone rules, accessibility, the pitfalls that actually bit, a verification recipe, and an acceptance checklist. |
| `screenshots/` | 18 renders covering every direction, both themes, and the interaction states. See `screenshots/INDEX.md`. |
| `../mockups/*.html` | The working mockups. Self-contained, interactive, no build step — open them in a browser. |
| `../RESEARCH.md` | Why the design is what it is: 18 finance products and 14 animation-led sites, and the rules drawn from them. Context, not instructions. |

## Suggested handoff message

> I'm redesigning the front end of a vanilla-JS personal finance app. The full brief is in
> DESIGN-PROMPT.md — read it end to end before writing code, especially Section 11 (pitfalls) and
> Section 12 (how to verify). Reference mockups are in docs/design/mockups/ and screenshots of
> every state are in docs/design/handoff/screenshots/. Build the **Aurora** direction. Work
> incrementally: token block first, then one component at a time, screenshotting each change in
> both themes before moving on.

Attach `DESIGN-PROMPT.md`, and as many screenshots as the tool allows — at minimum
`01`, `02`, `03`, `10`, `11`, `14`.

## Two things worth flagging to whoever executes

**Section 11 is the valuable part.** Those twelve pitfalls are real bugs found by rendering the
pages, not by reading the code. Five separate instances of one of them — inline `<span>` children
collapsing onto a single line — shipped invisibly until a screenshot caught them. An agent that
reads the CSS and declares victory will reproduce all of it.

**Insist on the screenshot loop.** `--force-prefers-reduced-motion` is the flag that makes it work;
without it every capture lands mid-animation and a real layout bug is indistinguishable from a
transition in progress.

## Scope

Front end only. The Python backend, SQLite layer, Plaid integration and workers are out of scope
and explicitly fenced off in Section 14 of the brief.

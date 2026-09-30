# AGENTS.md

## What this repo is
TrackPoint 4-wire strain gauge -> ADS1220 (SPI) -> nice!nano (ZMK).
`README.md` is the design of record; `layout/board.md` is the perfboard layout.
Changes are gated through numbered Experiments.

## Experiment workflow
Experiments are numbered EXP01, EXP02, ... One git branch per experiment,
one `experiments/EXP0N/README.md` per experiment. No change lands without an
experiment that states why.

| Step | Trigger | Action | Overview status |
|---|---|---|---|
| 1 Number   | user declares a new experiment | run `git log --oneline --branches`, read `experiments-overview.md`, tree `experiments/`; pick the next free number -> branch `EXP0N` | - |
| 2 Plan     | "start EXP0N ..." | plan mode: formalize + research viability; output Summary / Hypothesis / Methodology & blast radius / Open questions. Each open question carries a proposed default. No files written in plan mode. | - |
| 3 Record   | plan approved (build mode) | create the branch, write `experiments/EXP0N/README.md` from the template below, add an overview row | `todo` |
| 4 Run      | work begins | do the work; keep Learnings current as discoveries happen | `inProg` |
| 5 Conclude | user says "conclude EXP0N" | write the Conclusion/Findings, compress the Learnings, commit all changes on the branch, update the overview row | user-declared |

## Status
`todo | inProg | success | failed | abandoned`

Only the USER declares `success`, `failed` or `abandoned`. The agent recommends
and waits; it never declares a status on its own. Findings that contradict the
goal (e.g. goal = I2C, finding = "module is SPI-only") are a candidate for
`failed` -> propose it, do not set it.

`abandoned` is set only when the user says to abandon the experiment.

## Rules
- One experiment = one hypothesis. Make the blast radius explicit before starting.
- Branch per experiment, named after the EXP number (`EXP0N`).
- Plan mode is read-only: no branch, README or overview edits until the plan is approved.
- The overview is updated at every transition: plan-ready -> in progress -> final status.

## Open questions
- List them at plan time with a **proposed default** for each.
- If the user does not answer, adopt your proposed default, mark it explicitly
  as an assumption, and proceed. Never block waiting on an open question.
- If an assumption is later proven wrong, note it in Learnings and the Conclusion.

## Learnings (agent memory)
- Each experiment keeps a running `## Learnings` list: what was tried, the exact
  command that finally worked, and when to use it. Update it as you go so future
  sessions skip rediscovery instead of repeating it.
- On conclude, compress it to the smallest useful form.
- Durable, reusable facts only; never volatile per-run noise.
- At most ONE key learning may be promoted into AGENTS.md, and only after asking
  the user and getting the reason. Rare on purpose: keep AGENTS.md small.

## Experiment README template

```markdown
# EXP0N - <title>

## Summary
<goal for humans, < 250 chars>

## Hypothesis
<falsifiable prediction>

## Methodology & blast radius
- Method:
- May touch:
- Off-limits:

## Open questions (known unknowns)
- [ ] <question> — proposed default: <answer + why>

## Conclusion (findings)
_Pending._

## Learnings
- `<command that worked>` — use when <condition>
```

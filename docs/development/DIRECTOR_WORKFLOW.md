---
document_status: authoritative
last_verified: 2026-08-23
verified_by: founder/codex
---

# Director Workflow

This workflow replaces the retired autonomous queue and multi-agent handoff
experiments. Those attempts failed because queue execution lacked rigorous task
definition and acceptance judgment. Current work uses GitHub Flow plus direct
founder/Codex collaboration: a strong model remains in the planning and
acceptance loop, and any helper AI is limited to explicitly scoped work.

ADR-0016 aligns the 9/19 direction and 9/22 Codex/Gemini ownership; ADR-0011
originally changed the default scheduler from one global serial queue to the four
bounded swimlanes defined in
[`FIRST_LAUNCH_EXECUTION.md`](../current/FIRST_LAUNCH_EXECUTION.md). Each lane
may have one integration-sized implementation packet in progress, so work in
independent lanes proceeds concurrently without weakening task boundaries,
contract review, hardware safety, or evidence acceptance.

## Roles

| Role | Who | Owns |
|---|---|---|
| Operator | founder | Decisions, hardware operations (flashing, field runs, power), procurement/business contacts; may delegate scoped Git commits/integration |
| Director | Planning/acceptance session for this repo | Roadmap and ADRs, four-lane WIP, task packet authoring, collision-free integration order, acceptance review, STATUS/KR updates, fix instructions |
| Builder | Codex (or any coding AI session) | Implementing exactly one task packet in its assigned lane at a time, producing diff + validation output + evidence |

## Task Lifecycle

1. **Draft.** Director writes a task packet under `docs/tasks/active/` using
   `docs/tasks/TEMPLATE.md`, assigns it to Lane A/B/C/D, and confirms that the
   lane has no other integration-sized implementation packet in progress. The
   packet includes a `# Builder Prompt` section containing the exact prompt to
   give the builder. Parked packets, evidence waits, and continuous-regression
   packets may remain under `active/`; they do not consume lane WIP unless code
   or integration work is actively executing.
2. **Execute.** Operator gives the builder the Builder Prompt. The builder
   loads only `AGENTS.md`, `docs/CONTEXT_INDEX.md`, the packet, and the
   packet's `context` list; touches only `allowed_paths`; and stops with a
   report if any acceptance criterion cannot be met.
3. **Report.** The builder returns: changed files, validation command output,
   and evidence paths. The builder never marks its own task done and never
   updates `docs/current/STATUS.md`.
4. **Review.** Director checks, in order:
   - diff stays inside `allowed_paths`; no contract/protocol/pin drift unless
     the packet allows it;
   - every acceptance criterion has replayable evidence (Director re-runs the
     validation commands, does not trust pasted output alone);
   - hardware claims carry operator-confirmed evidence (board, firmware
     commit, connection path, timestamp, evidence file) — a passing build is
     never hardware evidence;
   - shared contracts and integration points match the owning lane's accepted
     version; cross-lane work did not create duplicate or competing contracts;
   - no secrets, no unrelated cleanup.
5. **Close.** On pass: the Operator or explicitly assigned builder commits, Director moves the packet to
   `docs/tasks/done/` and updates `docs/current/STATUS.md`. On fail: Director
   appends a numbered fix note (fix1, fix2, ...) to the packet with the exact
   gap.
6. **Fix budget.** Maximum 3 fix rounds per packet. If a packet is not
   acceptable after fix3, the Director must re-scope or split it instead of
   issuing fix4 (lesson from LTE-003's eight fix rounds).

## Cadence

Use two independent fields: `status` is packet lifecycle; `execution_state`
controls WIP. Only explicit `in_progress` counts as current implementation.
`queued`, `parked`, `acceptance_review`, `continuous_regression` and paused/blocked
work remain visible without inflating WIP. A checked checklist or code-complete
report enters `acceptance_review`; it is not automatic acceptance. Never archive
unresolved hardware evidence solely to reduce the number of active packets.

Every current item names an owner and consumer/dependency. For the 9/22 assignment,
follow [Codex/Gemini boundaries](../current/CODEX_GEMINI_HANDOFF_20260922.md).
Use isolated task worktrees when sharing a checkout with another builder, stage
exact paths, and integrate named commits after checking shared-file overlap.
Decision updates use `decision_updated`/`reviewed_at`; image/evidence dates change
only when new evidence exists. No source commit is automatically a flashed image.

- Four swimlanes run in parallel, with at most one integration-sized packet in
  progress in each lane:
  - **Lane A — L1 Reliable Location and Field Evidence**;
  - **Lane B — Ego Call and SOS**;
  - **Lane C — Reliability, Security, and Power**;
  - **Lane D — Product A0 and China Launch Readiness**.
- A builder still executes exactly one packet at a time. Up to four builders
  may work concurrently when they own different lanes, their `allowed_paths`
  do not collide, and no shared contract is being changed independently.
- A blocked lane reports its dependency and either takes its next safe,
  reversible packet or releases its WIP slot. Hardware, supplier, or founder
  waits in one lane do not serialize the other three lanes.
- One packet owns each shared contract change. Other lanes integrate against
  the accepted contract or a versioned fixture; they do not edit the same
  schema/protocol concurrently. The Director declares merge order before
  dispatch when file paths or contracts overlap.
- After every lane slice, restore a green repository and exercise the smallest
  relevant cross-lane integration. Product-level integration follows the order
  in `FIRST_LAUNCH_EXECUTION.md`: location context into Guardian/Call, native
  cellular primary voice, SOS alerts and data context over authenticated TLS,
  then measured traffic and power profiles into A0. Native voice must not wait
  for the data channel; RTC is an optional fallback with separate acceptance.
- The Director regenerates the founder progress board
  (`python scripts/build_progress_board.py`, output
  `docs/generated/PROGRESS_BOARD.md`) at every packet open/close/fix and
  keeps `docs/current/progress_board_config.json` (milestone map, assignees,
  founder asks) current.
- Direction review after every milestone exit or at least weekly: Director
  re-reads `docs/current/FIRST_LAUNCH_EXECUTION.md`, `docs/current/STATUS.md`,
  recent `docs/tasks/done/`, and `docs/roadmap/V1_PRODUCT_PLAN.md`, then
  re-prioritizes lane WIP without turning the lanes back into a serial wave.
- Milestone exits produce KR manifests via the existing release-gate flow.

## Builder Prompt Skeleton

```text
Read docs/tasks/active/<ID>.md in D:\pywork\egolink.
Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files listed in the
packet's `context`. This is Lane <A/B/C/D>; do only this task, obey
`allowed_paths` and
`out_of_scope`. Run the packet's validation commands before finishing.
If any acceptance criterion cannot be met, stop and report the exact
blocker instead of working around it. Return: changed files, validation
output, evidence paths. Do not update docs/current/STATUS.md and do not
move the packet to done/.
```

## Hard Rules Carried Over

- No unbounded autonomous multi-task queues. A founder-directed execution
  cycle may dispatch one bounded packet per lane; procurement, flashing,
  hardware commands, field runs, and other external actions still require the
  applicable explicit operator intent.
- Task packets remain the only unit of builder work.
- `python scripts/context_lint.py` after context/task edits;
  `scripts/verify.ps1` when behavior may change.
- Task `context` inputs must exist. A missing `allowed_paths` output is valid
  only when `git check-ignore --no-index` confirms it is ignored; paths must
  stay repository-relative without absolute paths or parent traversal. This
  permits later creation of local generated output in a clean worktree. It
  does not prove the output exists or satisfy an evidence/acceptance criterion.
- Evidence beats narrative: anything without a replayable artifact is
  treated as not done.

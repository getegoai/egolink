---
document_status: authoritative
last_verified: 2026-07-03
verified_by: claude
---

# Director Workflow

This workflow replaces the retired AutoDev autonomous loop and the Dual Codex
workflow (`docs/development/AUTODEV.md`, `docs/development/AUTODEV_MONITORING.md`,
`docs/development/DUAL_CODEX_WORKFLOW.md` are deprecated; see ADR-0002). The
AutoDev attempt failed because autonomous queue execution lacked rigorous task
definition and acceptance judgment. This workflow keeps a strong model in the
planning/acceptance loop and restricts builder AIs to explicitly scoped work.

## Roles

| Role | Who | Owns |
|---|---|---|
| Operator | founder | Decisions, hardware operations (flashing, field runs, power), procurement/business contacts, merges/commits |
| Director | Claude Code session for this repo | Roadmap and ADRs, task packet authoring, acceptance review, STATUS/KR updates, fix instructions |
| Builder | Codex (or any coding AI session) | Implementing exactly one task packet at a time, producing diff + validation output + evidence |

## Task Lifecycle

1. **Draft.** Director writes a task packet under `docs/tasks/active/` using
   `docs/tasks/TEMPLATE.md`, plus a `# Builder Prompt` section containing the
   exact prompt to paste into the builder.
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
   - no secrets, no unrelated cleanup.
5. **Close.** On pass: Operator commits, Director moves the packet to
   `docs/tasks/done/` and updates `docs/current/STATUS.md`. On fail: Director
   appends a numbered fix note (fix1, fix2, ...) to the packet with the exact
   gap.
6. **Fix budget.** Maximum 3 fix rounds per packet. If a packet is not
   acceptable after fix3, the Director must re-scope or split it instead of
   issuing fix4 (lesson from LTE-003's eight fix rounds).

## Cadence

- Serial execution by default: one active packet per builder at a time.
- The Director regenerates the founder progress board
  (`python scripts/build_progress_board.py`, output
  `docs/generated/PROGRESS_BOARD.md`) at every packet open/close/fix and
  keeps `docs/current/progress_board_config.json` (milestone map, assignees,
  founder asks) current.
- Direction review after every milestone exit or at least weekly: Director
  re-reads `docs/current/STATUS.md`, recent `docs/tasks/done/`, and
  `docs/roadmap/V1_PRODUCT_PLAN.md`, then re-prioritizes wave assignments.
- Milestone exits produce KR manifests via the existing release-gate flow.

## Builder Prompt Skeleton

```text
Read docs/tasks/active/<ID>.md in D:\pywork\egolink.
Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files listed in the
packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Run the packet's validation commands before finishing.
If any acceptance criterion cannot be met, stop and report the exact
blocker instead of working around it. Return: changed files, validation
output, evidence paths. Do not update docs/current/STATUS.md and do not
move the packet to done/.
```

## Hard Rules Carried Over

- No autonomous multi-task queues; a human triggers every execution.
- Task packets remain the only unit of builder work.
- `python scripts/context_lint.py` after context/task edits;
  `scripts/verify.ps1` when behavior may change.
- Evidence beats narrative: anything without a replayable artifact is
  treated as not done.

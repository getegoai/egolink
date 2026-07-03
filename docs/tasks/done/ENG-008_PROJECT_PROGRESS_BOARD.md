---
id: ENG-008
title: Founder-facing project progress board generator
status: done
priority: high
requires_hardware: false
created: 2026-07-03
last_updated: 2026-07-03

context:
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/tasks/TEMPLATE.md

allowed_paths:
  - scripts/
  - docs/current/progress_board_config.json
  - docs/generated/
  - docs/development/DIRECTOR_WORKFLOW.md
  - quality_tests/

out_of_scope:
  - firmware, server, or protocol changes
  - VPS deployment (Dashboard progress panel is a follow-up OBS task)
  - editing task packets or STATUS.md from the generator
---

# Problem

The founder cannot see project progress at a glance while the director
(claude) and builder (codex) work continuously. STATUS.md is an append-log,
TASK_TREE.md is a full structural record, and neither is a one-page current
view. The founder asked for a way to check progress at any time.

# Expected Result

A single-page generated board (`docs/generated/PROGRESS_BOARD.md` + JSON)
showing milestones with progress counts, in-flight tasks with assignees,
recent completions, pending founder actions, and key-release states — rebuilt
by the director at every task transition.

# Acceptance Criteria

- [x] `scripts/build_progress_board.py` scans `docs/tasks/active|done`
      frontmatter (handles both `id:` and `task_id:` keys), the milestone map
      in `docs/current/progress_board_config.json`, and
      `docs/current/key_releases/*.json` defensively.
- [x] Generates `docs/generated/PROGRESS_BOARD.md` and
      `docs/generated/progress_board.json`; never edits packets or STATUS.
- [x] Unit tests cover frontmatter parsing, milestone counting, markdown
      rendering, and broken-manifest tolerance.
- [x] `docs/development/DIRECTOR_WORKFLOW.md` requires regeneration at every
      packet open/close/fix.
- [x] `python scripts/context_lint.py` and `scripts/verify.ps1` pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_progress_board -v
python scripts/build_progress_board.py
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Not applicable (tooling/documentation task).

# Decisions

- Board lives in `docs/generated/` (generated artifact, not authoritative
  context; excluded from default agent context per AGENTS.md).
- Milestone map and founder-ask list are director-maintained config in
  `docs/current/progress_board_config.json`, so the board never guesses
  milestone intent.
- Phase 2 (VPS Dashboard progress panel via the existing report-store
  pattern) is a separate OBS task so production server changes get their own
  review.

# Completion Evidence

- Completed: 2026-07-03 by claude (director executed directly).
- Changed files: `scripts/build_progress_board.py`,
  `docs/current/progress_board_config.json`,
  `quality_tests/test_progress_board.py`,
  `docs/generated/PROGRESS_BOARD.md`, `docs/generated/progress_board.json`,
  `docs/development/DIRECTOR_WORKFLOW.md` (cadence rule).
- Test result: focused tests 4/4 OK; first board generated with
  active=4 / done=71; `context_lint` and `verify.ps1` results recorded in
  STATUS-adjacent session evidence.
- Hardware result: n/a
- Remaining risks: board freshness depends on director discipline; the
  DIRECTOR_WORKFLOW cadence rule is the control.

# Builder Prompt

```text
(Executed directly by the director; retained for template completeness.)
```

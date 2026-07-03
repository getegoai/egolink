---
id: ENG-007
title: Retire AutoDev/Dual-Codex docs and adopt Director Workflow references
status: done
priority: high
requires_hardware: false
created: 2026-07-03
last_updated: 2026-07-03

context:
  - docs/CONTEXT_INDEX.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md
  - docs/tasks/TASK_TREE.md
  - README.md

allowed_paths:
  - docs/
  - README.md
  - autodev/AGENTS.md

out_of_scope:
  - firmware logic changes
  - model behavior changes
  - deleting autodev/runs or autodev/runtime evidence files
  - scripts/ changes
---

# Problem

AutoDev and the Dual Codex workflow were tried and did not work
(founder decision 2026-07-03, ADR-0002). The docs still present them as
authoritative, `docs/CONTEXT_INDEX.md` routes "AutoDev" tasks to them, and
README/TASK_TREE still reference the old flow. New task prefixes introduced by
the V1 plan (OPS, PWR, PROD) are not registered.

# Expected Result

Repository documentation consistently points to
`docs/development/DIRECTOR_WORKFLOW.md` as the only active execution workflow;
AutoDev/Dual-Codex docs are archived as historical; new task prefixes are
registered; LTE-003 is closed as superseded.

# Acceptance Criteria

- [ ] `docs/development/AUTODEV.md`, `docs/development/AUTODEV_MONITORING.md`,
      `docs/development/DUAL_CODEX_WORKFLOW.md` moved to
      `docs/archive/autodev/` (keep filenames, add `_retired` suffix), each
      with frontmatter `document_status: archived` and a pointer to
      `DIRECTOR_WORKFLOW.md`.
- [ ] `autodev/AGENTS.md` gains a top banner stating the AutoDev loop is
      retired and pointing to `docs/development/DIRECTOR_WORKFLOW.md`.
- [ ] `docs/CONTEXT_INDEX.md`: the "AutoDev" routing row is replaced by a
      "Builder task execution" row requiring `DIRECTOR_WORKFLOW.md` + the
      active task packet; no remaining routing references to archived AutoDev
      docs.
- [ ] `README.md`: AutoDev monitoring references replaced with a short
      "Development workflow" pointer to `DIRECTOR_WORKFLOW.md`; V1 plan
      (`docs/roadmap/V1_PRODUCT_PLAN.md`) added to the task entry points.
- [ ] `docs/tasks/TASK_TREE.md`: prefixes `OPS-*` (VPS operations), `PWR-*`
      (power/battery engineering), `PROD-*` (mass-production definition and
      sourcing) registered with one-line descriptions.
- [ ] `docs/tasks/active/LTE-003_LTE_HTTP_COMMAND_POLL_ACK.md` moved to
      `docs/tasks/done/` with status `superseded` and a closing note that the
      FW-003 raw-frame path replaced it.
- [ ] `python scripts/context_lint.py` passes.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Not applicable (documentation-only task).

# Decisions

- Archive, do not delete: autodev run/runtime records stay as historical
  evidence per repository archive policy.

# Completion Evidence

- Completed: 2026-07-03 by claude (director executed directly; first packet
  under the new workflow).
- Changed files: `docs/archive/autodev/AUTODEV_retired.md`,
  `docs/archive/autodev/AUTODEV_MONITORING_retired.md`,
  `docs/archive/autodev/DUAL_CODEX_WORKFLOW_retired.md` (moved from
  `docs/development/`, frontmatter `archived`), `autodev/AGENTS.md` (retired
  banner), `docs/CONTEXT_INDEX.md` (Builder task execution + V1 planning
  routing rows, authority rules), `README.md` (workflow/V1 pointers),
  `docs/tasks/TASK_TREE.md` (V1 Wave 1 queue, new OPS/PWR/PROD prefixes,
  LTE-003 closure), `docs/tasks/done/LTE-003_LTE_HTTP_COMMAND_POLL_ACK.md`
  (status `superseded` + closure note), `docs/current/STATUS.md`
  (governance re-baseline note).
- Test result: `python scripts/context_lint.py` PASS;
  `scripts/verify.ps1` OK (334 tests).
- Hardware result: n/a
- Remaining risks: `scripts/watch_autodev.ps1` still exists as a legacy
  monitor script (out of scope here); remove or rename in a later ENG task
  if it causes confusion.

# Builder Prompt

```text
Read docs/tasks/active/ENG-007_AUTODEV_DEPRECATION_DIRECTOR_WORKFLOW.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
in this packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Run the validation commands before finishing. If any
acceptance criterion cannot be met, stop and report the blocker. Return:
changed files, validation output, evidence paths. Do not update
docs/current/STATUS.md and do not move this packet to done/.
```

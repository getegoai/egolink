---
document_status: current_snapshot
generated_at: 2026-06-27
generated_by: codex
scope: engineering-control-plane
---

# EGOLINK Project Snapshot

This snapshot rebuilds the current project state from read-only repository
inspection. It intentionally does not modify firmware, model, simulator, or
contract implementation code.

## One-Line State

EGOLINK has a verified Demo v0.5 safety-loop runner on branch
`autodev/egolink-p0`, and the completed DEMO task packets have been moved out
of `docs/tasks/active/`; the remaining control-plane issue is that many context
and documentation migration files are still uncommitted and no Git remote is
configured.

2026-06-28 addendum: the USB-Free VPS Message Hub path has progressed beyond
this snapshot's original state. FW-002C resetdiag fix3 has USB-Free
firmware-side SIM7670G real-fix evidence, and the near-term route has been
corrected to observable-first development: R2.1 observability completion, R2.2
short USB-Free baseline stability, R2.3 LTE HTTP thin-slice, R2.4 LTE command
loop, R2.5 multi-source location observation and memory, then R3 product
gates. The source planning draft used `ENG-003` for the route update, but the
current task tree already uses `ENG-003` for Legacy Archive Review, so the
route update is tracked with a non-conflicting task ID while preserving the
same intent.

## Commands Executed

- `git status`
- `git branch --show-current`
- `git log --oneline --decorate --graph --all -n 30`
- `git diff --stat`
- `git diff --name-only`
- `make validate`: not run because no `Makefile` or `makefile` was found.

## Current Branch

- Branch: `autodev/egolink-p0`
- Remote: none reported by `git remote -v`
- GitHub Flow implication: local commits exist, but PR/merge/push flow cannot be
  completed until a remote and target branch policy are confirmed.

## Recent Commits

- `694bb04` `demo: add full safety loop runner`
- `ef839e9` `demo: wire amoled imu confirmation loop`
- `556e41e` `docs: add demo-first amoled imu task`
- `65ad81f` `Add Demo v0.3 live safety loop`
- `6a72057` `Run AMOLED ask_user demo from PC bridge`
- `53ce590` `Pin AMOLED demo display dependencies`
- `f43bfb5` `Add AMOLED safety prompt demo firmware`
- `04b85af` `Add demo-first minimal safety loop`
- `dd8abdd` `Update P0 dual-board bridge architecture docs`
- `7cc06fe` `Add QMI8658 labeled fixture repeatability capture`

## Uncommitted Changes

Tracked modified files:

- `AGENTS.md`
- `MODEL_PACKAGE_README.md`
- `README.md`
- `docs/AGENTS.md`
- `docs/EGO_LINK_P0_CONTEXT.md`
- `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md`
- `docs/hardware/CODEX_HARDWARE_PROMPT.md`
- `docs/hardware/README.md`
- `docs/hardware/TIMU_007_PLATFORM_IMU_REAL_BACKEND_POC_20260624.md`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`
- `docs/tasks/CURRENT_TASK.md`
- `docs/tasks/TASK_TEMPLATE.md`

Tracked deleted files:

- `CHANGELOG_SAFETY_COMPANION.md`
- `docs/AUTODEV_GUIDE.md`
- `docs/AUTODEV_MONITORING.md`
- `docs/AUTODEV_V0_2_UPGRADE.md`
- `docs/DEVELOPMENT_WORKFLOW.md`
- `docs/EGO_LINK_AGENTIC_DEV_PLAN.md`
- `docs/P0_BOARD_VALIDATION.md`
- `docs/产品定位.md`
- `模型架构.md`

Untracked high-level additions:

- `.agents/`
- `.codex/`
- `autodev/AGENTS.md`
- `docs/CONTEXT_INDEX.md`
- `docs/architecture/SYSTEM_OVERVIEW.md`
- `docs/architecture/adr/`
- `docs/archive/`
- `docs/current/`
- `docs/development/`
- `docs/generated/`
- `docs/hardware/BOARD_MATRIX.md`
- `docs/hardware/validation/`
- `docs/modeling/MODEL_ARCHITECTURE.md`
- `docs/product/`
- `docs/safety/`
- `docs/tasks/TEMPLATE.md`
- `docs/tasks/active/.gitkeep`
- `docs/tasks/done/`
- `firmware/AGENTS.md`
- `model_lab/AGENTS.md`
- `pc_simulator/AGENTS.md`
- `quality_tests/AGENTS.md`
- `scripts/context_lint.py`
- `上下文重构.md`

## Current Active Tasks

No task packet with `status: active` is currently present under
`docs/tasks/active/`. The directory contains only `.gitkeep`.

## Completed Tasks

Task packets currently under `docs/tasks/done/`:

- `DEMO-001_AMOLED_IMU_CONFIRMATION_LOOP.md`
  - id: `DEMO-001`
  - title: `AMOLED IMU Confirmation Loop`
  - status: `completed`
- `DEMO-004_FULL_DEMO_ORCHESTRATOR.md`
  - id: `DEMO-004`
  - title: `Full Demo Orchestrator`
  - status: `completed`
- `TIMU-009C-B2_QMI8658_LABELED_FIXTURE_REPEATABILITY_CAPTURE.md`
  - title: `TIMU-009C-B2 / QMI8658 Labeled Fixture Repeatability Capture`
  - note: done task has narrative format rather than the current frontmatter task
    template.

Recently completed implementation commits indicate these additional completed
work slices:

- Demo v0.5 full safety loop runner.
- AMOLED IMU confirmation loop.
- Demo v0.3 live safety loop.
- AMOLED ask_user PC bridge script.
- AMOLED safety prompt firmware.
- Minimal Demo-first safety loop.
- QMI8658 labeled fixture repeatability capture.

## Current Blockers

- The worktree is not clean; there are large documentation/context migration
  changes, deletions, and untracked authoritative documents.
- `docs/current/` is an authoritative context directory according to
  `docs/CONTEXT_INDEX.md`, but it is currently untracked.
- `docs/current/STATUS.md` still contained an obsolete "next task" statement
  pointing at DEMO-002 even though DEMO-004 is already completed.
- No Git remote is configured, so GitHub Flow cannot yet include push, PR, or
  merge review steps.
- No `make validate` target exists; validation currently relies on repository
  scripts such as `scripts/context_lint.py` and `scripts/verify.ps1`.

## Current Risks

- Demo v0.5 audio evidence is mock-only structured evidence; real microphone
  capture and acceptance remain unverified.
- SIM7670G GNSS AT probing works indoors, but the latest evidence remains
  `fix=false` / `no_fix`; real outdoor GNSS fix is unverified.
- The IMU trigger used in the demo is a demo heuristic, not production
  fall-detection accuracy and not MotionNet output.
- Formal IMU product acceptance remains false until final mounting, calibration,
  FIFO/DRDY, and power evidence are complete.
- The uncommitted context migration makes it hard to identify which documents
  are current authority versus staged-but-uncommitted restructuring.

## Most Trustworthy Authority Documents

These files are authoritative by repository instructions or context routing:

- `AGENTS.md`
- `docs/CONTEXT_INDEX.md`
- `docs/product/PRODUCT_CHARTER.md`
- `docs/product/P0_SCOPE.md`
- `docs/current/STATUS.md`
- `docs/current/ACTIVE_BUILD.md`
- `docs/hardware/BOARD_MATRIX.md`
- `docs/architecture/SYSTEM_OVERVIEW.md`
- `docs/architecture/adr/README.md`
- `shared/contracts/`

Important caveat: several of these authority documents are currently untracked
or part of the broader context migration. They are the most trustworthy local
documents, but the Git history does not yet fully preserve them.

## Obviously Stale Or Conflicting Documents

- `docs/current/STATUS.md`: the "当前建议任务" section pointed at DEMO-002,
  which conflicts with completed DEMO-004 status.
- `docs/tasks/done/TIMU-009C-B2_QMI8658_LABELED_FIXTURE_REPEATABILITY_CAPTURE.md`:
  completed task is useful, but it does not follow the current frontmatter task
  packet template.
- Tracked legacy docs are deleted while archived replacements are untracked,
  for example AutoDev docs and Chinese top-level context files.
- `docs/tasks/CURRENT_TASK.md` is a pointer only; it does not identify the next
  concrete active task.

## Suggested Next 3 Tasks

1. `ENG-002 Control Plane Commit / Remote Policy`
   - Decide whether to commit the full context migration as one baseline or
     split it into reviewable chunks.
   - Confirm remote, target branch, and GitHub Flow branch naming.
   - Produce a clean worktree checkpoint.

2. `DEMO-005 Real GNSS Fix Evidence`
   - Run bounded outdoor or near-window SIM7670G GNSS fix validation.
   - Feed the resulting `location_report fix=true` into the full Demo v0.5
     runner.
   - Keep no-fix behavior as a valid indoor fallback, not as real fix evidence.

3. `DEMO-006 Real Audio Chain Bring-Up`
   - Replace the v0.5 mock-only structured audio evidence with a minimal real
     microphone path only after hardware evidence exists.
   - Preserve privacy boundaries: no raw audio by default, explicit consent if
     raw clips are ever captured.

## Human Confirmation Needed

- Should the current context migration be committed as the new documentation
  baseline, or should parts of it be reverted/split?
- Which branch should be the protected target branch for GitHub Flow: `main`,
  current `autodev/egolink-p0`, or a new integration branch?
- Is real GNSS fix or real audio chain the next product priority?

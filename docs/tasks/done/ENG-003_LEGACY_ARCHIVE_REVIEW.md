---
id: ENG-003
title: Legacy Archive Review
status: completed
priority: medium
requires_hardware: false
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/AGENTS.md
  - docs/tasks/TASK_TREE.md

allowed_paths:
  - README.md
  - MODEL_PACKAGE_README.md
  - docs/
  - reports/dev_runs/

out_of_scope:
  - firmware logic changes
  - model behavior changes
  - simulator behavior changes
  - shared contract changes
  - hardware flashing or live capture
---

# Problem

The control-plane migration left old documentation deletions, compatibility
pointer updates, and archive/generated files uncommitted. The project needed a
reviewable archive cleanup so historical content was preserved before old
paths were removed or redirected.

# Expected Result

Old documentation paths that are no longer authoritative are either redirected
to current authority or deleted only after their full legacy content is
preserved under `docs/archive/` or an exact current destination.

# Acceptance Criteria

- [x] Each deleted legacy document has an exact preserved copy or exact current
  destination.
- [x] `docs/DEVELOPMENT_WORKFLOW.md` is preserved as a legacy archive before
  deletion.
- [x] Compatibility pointer updates remain limited to documentation.
- [x] Active task queue remains empty.
- [x] Context lint passes.
- [x] Full repository verification passes.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Board: not applicable.
- Firmware commit: not applicable.
- Connection: not applicable.
- Expected output: not applicable.
- Evidence path: not applicable.

# Decisions

- Keep `docs/EGO_LINK_P0_CONTEXT.md` as a compatibility pointer instead of
  deleting the path.
- Keep old completed task and context history in `docs/archive/` and
  `docs/tasks/done/`.
- Leave operator input `上下文重构.md` outside this cleanup unless a later task
  explicitly makes it repository context.

# Completion Evidence

- Changed files:
  - legacy deletions for old context/workflow/autodev paths
  - `README.md`
  - `MODEL_PACKAGE_README.md`
  - `docs/EGO_LINK_P0_CONTEXT.md`
  - `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`
  - `docs/archive/`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/ENG-003_LEGACY_ARCHIVE_REVIEW.md`
- Test result:
  - `python scripts/context_lint.py`: PASS
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1`:
    PASS, 192 tests OK
- Hardware result: not run; no hardware work was in scope.
- Remaining risks:
  - `docs/generated/` and `上下文重构.md` remain uncommitted review candidates.

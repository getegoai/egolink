---
id: ENG-004
title: Generated Docs Review
status: completed
priority: medium
requires_hardware: false
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/AGENTS.md
  - docs/generated/CONTEXT_MIGRATION_REPORT.md
  - docs/generated/REPOSITORY_MAP.md

allowed_paths:
  - docs/generated/
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/ENG-004_GENERATED_DOCS_REVIEW.md
  - reports/dev_runs/

out_of_scope:
  - editing generated report contents by hand
  - firmware logic changes
  - model behavior changes
  - simulator behavior changes
  - shared contract changes
  - hardware validation
---

# Problem

After ENG-003, `docs/generated/` remained untracked. The project needed a
decision on whether these generated documents should be versioned or left as
local runtime output.

# Expected Result

Generated migration evidence is either versioned as non-authoritative project
evidence or explicitly left out of Git with a recorded reason.

# Acceptance Criteria

- [x] `docs/generated/CONTEXT_MIGRATION_REPORT.md` is treated as generated
  migration evidence, not current authority.
- [x] `docs/generated/REPOSITORY_MAP.md` is treated as generated repository
  baseline evidence, not current authority.
- [x] Existing generated file contents are not hand-edited.
- [x] `上下文重构.md` remains outside version control unless a future task makes
  it repository context.
- [x] Context lint passes.

# Validation Commands

```powershell
python scripts/context_lint.py
```

# Hardware Validation

- Board: not applicable.
- Firmware commit: not applicable.
- Connection: not applicable.
- Expected output: not applicable.
- Evidence path: not applicable.

# Decisions

- Version both current files under `docs/generated/` because they document the
  control-plane migration and repository baseline.
- Do not make `docs/generated/` part of default context.
- Do not version the operator input file `上下文重构.md` in this task.

# Completion Evidence

- Changed files:
  - `docs/generated/CONTEXT_MIGRATION_REPORT.md`
  - `docs/generated/REPOSITORY_MAP.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/ENG-004_GENERATED_DOCS_REVIEW.md`
- Test result:
  - `python scripts/context_lint.py`: PASS
- Hardware result: not run; no hardware work was in scope.
- Remaining risks:
  - The generated reports are historical evidence and may describe old paths.
    Current authority remains routed through `docs/CONTEXT_INDEX.md`.

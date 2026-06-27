# ENG-001 Control Plane Baseline

- Date: 2026-06-27
- Branch: `autodev/egolink-p0`
- Scope: engineering control plane only
- Hardware actions: none
- Business implementation changes: none

## Summary

ENG-001 moved completed DEMO task packets out of the active queue, added current
development-control documents, refreshed the project snapshot/task tree/status
facts, and validated the repository without flashing firmware or running live
hardware controls.

## Files To Include In Git Baseline

Authoritative context and control files to include:

- `AGENTS.md`
- `docs/CONTEXT_INDEX.md`
- `docs/current/STATUS.md`
- `docs/current/PROJECT_SNAPSHOT.md`
- `docs/current/ACTIVE_BUILD.md`
- `docs/tasks/TASK_TREE.md`
- `docs/tasks/TEMPLATE.md`
- `docs/tasks/active/.gitkeep`
- `docs/tasks/done/`
- `docs/product/`
- `docs/architecture/`
- `docs/development/`
- `docs/hardware/`
- `docs/modeling/`
- `docs/safety/`
- `scripts/context_lint.py`
- module instructions:
  - `autodev/AGENTS.md`
  - `firmware/AGENTS.md`
  - `model_lab/AGENTS.md`
  - `pc_simulator/AGENTS.md`
  - `quality_tests/AGENTS.md`

Legacy documents that are no longer default authority should be preserved in
archive or migration notes rather than deleted without trace:

- `docs/archive/autodev/`
- `docs/archive/context/`
- `docs/archive/tasks/`
- `docs/hardware/validation/`
- `docs/generated/CONTEXT_MIGRATION_REPORT.md`
- `docs/generated/REPOSITORY_MAP.md`

Local or private items that should not be included in the Git baseline:

- `.codex/config.toml`
- `.agents/` personal skill scaffolding unless reviewed separately
- runtime logs and large generated runtime artifacts
- API keys, local credentials, or private device logs

## File Migration List

No business implementation files were modified.

Control-plane files added or updated by this ENG-001 task:

- `docs/current/PROJECT_SNAPSHOT.md`
- `docs/current/STATUS.md`
- `docs/tasks/TASK_TREE.md`
- `docs/development/GIT_FLOW.md`
- `docs/development/VALIDATION.md`
- `docs/development/DUAL_CODEX_WORKFLOW.md`
- `reports/dev_runs/ENG-001-control-plane-baseline.md`

## Task Move List

Moved completed task packets:

- `docs/tasks/active/DEMO-001_AMOLED_IMU_CONFIRMATION_LOOP.md`
  -> `docs/tasks/done/DEMO-001_AMOLED_IMU_CONFIRMATION_LOOP.md`
- `docs/tasks/active/DEMO-004_FULL_DEMO_ORCHESTRATOR.md`
  -> `docs/tasks/done/DEMO-004_FULL_DEMO_ORCHESTRATOR.md`

Active queue after the move:

- `docs/tasks/active/.gitkeep`
- No task packet with `status: active`.

## Validation Results

Passed:

```powershell
python scripts/context_lint.py
```

Result: `context_lint: PASS`

Passed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Result: `Ran 192 tests ... OK`

Not run:

```powershell
make validate
```

Reason: no `Makefile` or `makefile` with a `validate` target is currently part
of the repository root.

## Unresolved Issues

- No Git remote is configured, so the project is still using local-only GitHub
  Flow.
- A broad documentation/context migration remains uncommitted.
- `.codex/config.toml` and `.agents/` are untracked local items and should stay
  out of the baseline unless explicitly reviewed.
- `docs/tasks/done/TIMU-009C-B2_QMI8658_LABELED_FIXTURE_REPEATABILITY_CAPTURE.md`
  is useful evidence, but it does not use the current frontmatter task template.
- Real GNSS fix, real audio chain, and formal IMU product acceptance remain
  outside ENG-001.

## Next Suggested Task

Preferred next task:

- `ENG-002 Control Plane Commit / Remote Policy`
  - decide whether to commit the context migration as one baseline or split it;
  - configure or confirm the remote;
  - confirm target branch protection and local-to-remote GitHub Flow.

Then proceed to:

- `DEMO-005 Real GNSS Fix Evidence`
  - capture bounded SIM7670G `fix=true` evidence;
  - replay it through the full Demo v0.5 runner.

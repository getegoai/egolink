# Context Migration Report

Generated: 2026-06-26

## Inventory

Repository documentation/config inventory after migration, excluding `.git`, runtime logs, run folders, and caches:

| extension | count |
|---|---:|
| `.md` | 164 |
| `.json` | 118 |
| `.yaml` | 14 |
| `.yml` | 29 |
| `.toml` | 2 |
| `.txt` | 127 |

## Directory Structure Added

- `docs/product`
- `docs/current`
- `docs/architecture/adr`
- `docs/hardware/validation`
- `docs/modeling`
- `docs/development`
- `docs/safety`
- `docs/tasks/active`
- `docs/tasks/done`
- `docs/generated`
- `docs/archive`
- `.agents/skills`
- `.codex`

## File Migration Mapping

| old path | new path or current handling |
|---|---|
| `docs/EGO_LINK_P0_CONTEXT.md` | full legacy content moved to `docs/archive/context/EGO_LINK_P0_CONTEXT_legacy.md`; old path is now a pointer |
| `docs/产品定位.md` | moved to `docs/archive/context/产品定位_legacy.md`; current authority is `docs/product/PRODUCT_CHARTER.md` |
| `docs/STATUS.md` | copied to `docs/current/STATUS.md`; old path kept for compatibility |
| `docs/P0_BOARD_VALIDATION.md` | moved to `docs/hardware/validation/P0_BOARD_VALIDATION.md` |
| `模型架构.md` | moved to `docs/modeling/MODEL_ARCHITECTURE.md` |
| `CHANGELOG_SAFETY_COMPANION.md` | moved to `docs/safety/CHANGELOG.md` |
| `docs/DEVELOPMENT_WORKFLOW.md` | moved to `docs/development/WORKFLOW.md` |
| `docs/AUTODEV_GUIDE.md` | moved to `docs/archive/autodev/AUTODEV_GUIDE_legacy.md`; merged authority is `docs/development/AUTODEV.md` |
| `docs/AUTODEV_MONITORING.md` | moved to `docs/archive/autodev/AUTODEV_MONITORING_legacy.md`; merged authority is `docs/development/AUTODEV_MONITORING.md` |
| `docs/AUTODEV_V0_2_UPGRADE.md` | moved to `docs/archive/autodev/AUTODEV_V0_2_UPGRADE_legacy.md` |
| `docs/EGO_LINK_AGENTIC_DEV_PLAN.md` | moved to `docs/archive/autodev/EGO_LINK_AGENTIC_DEV_PLAN_legacy.md` |
| `docs/tasks/CURRENT_TASK.md` | moved completed task content to `docs/tasks/done/TIMU-009C-B2_QMI8658_LABELED_FIXTURE_REPEATABILITY_CAPTURE.md`; old path is now a pointer |
| `docs/tasks/TASK_TEMPLATE.md` | legacy template moved to `docs/archive/tasks/TASK_TEMPLATE_legacy.md`; current template is `docs/tasks/TEMPLATE.md` |
| `docs/repository_baseline.md` | copied to `docs/generated/REPOSITORY_MAP.md`; old path kept for AutoDev bootstrap compatibility |

## New Authoritative Context Files

- `docs/CONTEXT_INDEX.md`
- `docs/product/PRODUCT_CHARTER.md`
- `docs/product/P0_SCOPE.md`
- `docs/current/STATUS.md`
- `docs/current/ACTIVE_BUILD.md`
- `docs/hardware/BOARD_MATRIX.md`
- `docs/architecture/SYSTEM_OVERVIEW.md`
- `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`
- `docs/safety/SAFETY_CONTRACT.md`
- `docs/development/AUTODEV.md`
- `docs/development/AUTODEV_MONITORING.md`
- `docs/architecture/adr/README.md`

## Context Rule Files Added

- root `AGENTS.md` rewritten as repository-level context loading, boundaries, hardware safety, and completion gates
- `docs/AGENTS.md` reduced to documentation editing rules
- `firmware/AGENTS.md`
- `model_lab/AGENTS.md`
- `pc_simulator/AGENTS.md`
- `quality_tests/AGENTS.md`
- `autodev/AGENTS.md`
- `.agents/skills/execute-task/SKILL.md`
- `.agents/skills/board-validation/SKILL.md`
- `.agents/skills/firmware-change/SKILL.md`
- `.agents/skills/release-review/SKILL.md`

## Conflicts Found

- Root `AGENTS.md` and `docs/AGENTS.md` both contained global operating rules. The new split makes root `AGENTS.md` global and `docs/AGENTS.md` documentation-only.
- Older P0 documents described a single SIM7670G-centered Mock-first setup, while newer hardware context describes a dual-board plus PC bridge P0. Current authority now lives in `docs/product/P0_SCOPE.md`, `docs/current/ACTIVE_BUILD.md`, `docs/hardware/BOARD_MATRIX.md`, and `docs/architecture/SYSTEM_OVERVIEW.md`.
- `docs/STATUS.md` and `docs/current/STATUS.md` now intentionally duplicate status content. The new path is authoritative; the old path remains for compatibility with existing tests and scripts.
- `docs/repository_baseline.md` and `docs/generated/REPOSITORY_MAP.md` intentionally duplicate repository baseline content. The generated path is for the new structure; the old path remains for AutoDev bootstrap compatibility.
- `HARDWARE_CONTEXT_PACKAGE_README.md` still references the old `docs/EGO_LINK_P0_CONTEXT.md` path. It was not changed because it is covered by `PACKAGE_MANIFEST.json`; changing it should be paired with a manifest/hash refresh task.
- Historical task logs inside status and integration reports may mention old paths. They were not treated as current authority.

## Unresolved Issues

- Decide in a later task whether compatibility pointer files should remain permanently or be removed after tests and scripts adopt new paths.
- Decide whether `scripts/autodev.py`, AutoDev tests, and repository baseline scripts should be updated to the new context paths. This migration kept business/script behavior stable.
- Decide whether `PACKAGE_MANIFEST.json` and `HARDWARE_CONTEXT_PACKAGE_README.md` should be regenerated under the new context layout.
- Some historical documents are still encoded/displayed inconsistently in Windows terminal output. Content was preserved, but future documentation cleanup may choose a UTF-8 normalization pass.

## Facts Requiring Human Confirmation

- Whether `docs/current/ACTIVE_BUILD.md` should be refreshed with a new live hardware observation after the next device run.
- Whether the final accepted P0 product target should keep the current wording: one low-power MCU or AI MCU plus cellular module.
- Whether the current compatibility files (`docs/EGO_LINK_P0_CONTEXT.md`, `docs/tasks/CURRENT_TASK.md`, `docs/tasks/TASK_TEMPLATE.md`) are acceptable as long-term redirect stubs.
- Whether the untracked instruction file `上下文重构.md` should be archived into the repository or left outside version control as operator input.

## Business Code Not Modified

This migration did not modify implementation files under:

- `firmware/amoled_bridge`
- `firmware/amoled_safety_demo`
- `firmware/camera_smoke`
- `firmware/mqtt_heartbeat`
- `model_lab/safety_companion`
- `pc_simulator/*.py`
- `quality_tests/*.py`
- `shared/contracts`

Only context, documentation, module instruction files, and `scripts/context_lint.py` were added or changed.

## Validation

Commands run:

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

Observed results:

```text
context_lint: PASS
scripts\verify.ps1: PASS, 183 tests OK
```

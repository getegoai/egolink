---
id: REL-012
title: v0.1.0 Engineering Alpha Release Gate
status: completed
completed: 2026-07-10
demo: RELEASE
context:
  - docs/product/NORTH_STAR.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-008_V010_ENGINEERING_ALPHA.json
  - docs/development/GIT_FLOW.md
allowed_paths:
  - README.md
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-008_V010_ENGINEERING_ALPHA.json
  - docs/current/progress_board_config.json
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/development/GIT_FLOW.md
  - docs/tasks/done/REL-012_V010_ENGINEERING_ALPHA_RELEASE_GATE.md
  - docs/tasks/TASK_TREE.md
  - docs/archive/development/
  - autodev/
  - scripts/autodev.py
  - scripts/autodev_bootstrap_check.py
  - scripts/run_autodev.ps1
  - scripts/watch_autodev.ps1
validation:
  - python scripts/context_lint.py
  - python -m unittest quality_tests.test_key_release_gate quality_tests.test_location_field_evidence quality_tests.test_location_data_flywheel quality_tests.test_location_d2_d5_pipeline -v
  - python scripts/run_key_release_gate.py --manifest docs/current/key_releases/KR-008_V010_ENGINEERING_ALPHA.json --json
  - powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
---

# REL-012 v0.1.0 Engineering Alpha Release Gate

This task records the release-line decision for the current P0 branch.

## Result

`egolink-p0` is treated as the v0.1.0 Engineering Alpha candidate branch. It may
merge to `main` only after the KR-008 release gate, context lint, full verify,
and clean tracked worktree checks pass.

## Release Meaning

The release freezes this product-like engineering loop:

```text
4G board -> LTE -> Message Hub -> Web Dashboard
          -> bounded field evidence -> D2/D5 location data flywheel
```

## Changes

- Removed the retired autonomous queue code and wrappers from the active
  workspace.
- Rewrote `README.md` with the current product-like run path.
- Updated GitHub Flow policy: `main` is always runnable/releaseable;
  `egolink-p0` is a candidate branch until release-gated.
- Added KR-008 `v0.1.0 Engineering Alpha` release manifest.
- Moved stale project snapshot/baseline documents from current context to
  archive.

## Non-Claims

- No commercial product-readiness or mass-production claim.
- No product location-accuracy claim.
- No real calling/SMS/emergency-dispatch/contact-notification claim.
- No product battery-life claim.
- No model-performance or on-device AI deployment claim.
- No training use of private field data without explicit review gates.

## Evidence

Validation commands listed in frontmatter are the completion gate for this
task. Generated local release-gate reports are written under `reports/` and are
not committed.

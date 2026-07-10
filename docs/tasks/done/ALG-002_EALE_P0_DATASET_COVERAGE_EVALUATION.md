---
id: ALG-002
title: EALE-P0 Dataset Coverage Evaluation
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30
completed: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/development/DEV_FLOW.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/tasks/done/DATA-001_LOCATION_FUSION_DATASET_BASELINE.md
  - docs/tasks/done/ALG-000_LOCATION_FUSION_ALGORITHM_DESIGN.md
  - docs/tasks/done/ALG-001_SERVER_DERIVED_LOCATION_BELIEF.md
  - shared/contracts/location_fusion_sample.schema.json

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/ALG-002_EALE_P0_DATASET_COVERAGE_EVALUATION.md
  - scripts/evaluate_eale_p0_dataset.py
  - quality_tests/test_eale_p0_dataset_evaluation.py

out_of_scope:
  - changing firmware logic or flashing hardware
  - sending hardware control commands
  - changing live device wire protocol or raw-frame profile
  - changing DATA-001 sample schema
  - changing Message Hub runtime behavior or VPS deployment
  - training or publishing a learned model
  - claiming GNSS acceptance, cell-only positioning, positioning accuracy, or product readiness
  - committing private coordinates, raw Wi-Fi BSSID values, raw audio, raw images, private device logs, or large runtime datasets
  - modifying GitLab or unrelated VPS services
---

# ALG-002 EALE-P0 Dataset Coverage Evaluation

## Goal

Add a repeatable offline review step between DATA-001 dataset export and
KR-004 promotion:

```text
test_run_export.json
-> DATA-001 samples.jsonl + manifest.json
-> EALE-P0 coverage report
-> release-review and future corpus-quality decision
```

The report should explain what evidence exists, what failed, whether failure
windows were retained, and whether the dataset is ready for future learned
model experiments.

## Acceptance

- [x] Read DATA-001 `samples.jsonl` plus `manifest.json` without contacting
      the VPS, serial ports, or hardware.
- [x] Count sample types, label states, label sources, failure modes, quality
      statuses, privacy classes, and split names.
- [x] Report raw-frame lineage coverage, derived-event coverage, raw parse
      statuses, feature-group coverage, and source-state/evidence-state
      coverage.
- [x] Report EALE-P0 review counters for Fine candidates, retained failure
      windows, Unknown/no-fix samples, raw-parse failures retained, and
      cell/LTE evidence that must not become a position by itself.
- [x] Keep release-review readiness separate from learned-model readiness.
- [x] Output JSON and Markdown reports under ignored runtime/report storage.
- [x] Add focused unit tests for failure-window and Fine-candidate cases.

## Implementation

- Added `scripts/evaluate_eale_p0_dataset.py`.
- Added `quality_tests/test_eale_p0_dataset_evaluation.py`.
- Documented ALG-002 in `LOCATION_DATASET.md`,
  `LOCATION_FUSION_ALGORITHM.md`, `LOCATION_ENGINE.md`, and the task tree.

## LOC-005A Evidence

The current LOC-005A field export was converted to DATA-001 and evaluated:

- DATA-001 dataset:
  `reports/location_fusion_datasets/loc005a-source-states-20260630-001/`.
- ALG-002 report:
  `reports/location_fusion_eale/loc005a-source-states-20260630-001/eale_p0_dataset_report.json`
  and
  `reports/location_fusion_eale/loc005a-source-states-20260630-001/eale_p0_dataset_report.md`.
- Result: `warn`.
- Summary: one retained `failure_window`, one `gnss_no_fix` failure mode, one
  `Unknown` label state, raw-frame lineage present, derived-event lineage
  present, cell/LTE/Wi-Fi/IMU/power evidence groups present, zero Fine
  candidates, and `model_training_ready=false`.

This is the expected release-review shape for the current no-fix LOC-005A
evidence: useful and explainable, but not a positioning-accuracy or learned
model claim.

## Validation

- `python -m unittest quality_tests.test_eale_p0_dataset_evaluation quality_tests.test_location_fusion_dataset_export -v`
  passed with 8 tests.
- `python scripts/context_lint.py` passed.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed with
  307 tests.
- `git diff --check` passed.
- `python scripts\run_key_release_gate.py --manifest docs\current\key_releases\KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json --json`
  passed.
- `python scripts\export_location_fusion_dataset.py --input reports\field_validation\loc005a-source-states-20260630-001\test_run_export.json --output-dir reports\location_fusion_datasets\loc005a-source-states-20260630-001 --json`
  passed.
- `python scripts\evaluate_eale_p0_dataset.py --dataset-dir reports\location_fusion_datasets\loc005a-source-states-20260630-001 --output-dir reports\location_fusion_eale\loc005a-source-states-20260630-001 --json`
  passed with `result.status=warn`.

## Boundary

ALG-002 is an offline data-quality and release-review increment only. It does
not change firmware, hardware state, raw-frame payload shape, public device
wire protocol, DATA-001 schema, Message Hub runtime behavior, learned model
behavior, key-release status, GNSS behavior, LTE stability, battery/power
behavior, or product readiness.

---
id: DATA-001
title: Location Fusion Dataset Baseline
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30
completed: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/DEV_FLOW.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/PROTOCOL.md
  - docs/development/VPS_MESSAGE_HUB.md
  - shared/contracts/
  - server/message_hub.py
  - scripts/validate_lte_command_loop.py

allowed_paths:
  - docs/CONTEXT_INDEX.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/PROTOCOL.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/DATA-001_LOCATION_FUSION_DATASET_BASELINE.md
  - shared/contracts/
  - server/message_hub.py
  - scripts/
  - quality_tests/

out_of_scope:
  - changing device wire fields without a Protocol task
  - training or publishing a learned fusion model
  - claiming cell-only positioning accuracy
  - copying exact private coordinates, Wi-Fi identifiers, raw audio, or raw images into committed docs
  - changing firmware logic or flashing hardware
  - running long LTE stability or product acceptance tests
  - modifying GitLab or unrelated VPS services
---

# DATA-001 Location Fusion Dataset Baseline

## Goal

Create the first repeatable data-export path for location fusion and future
model training:

```text
test_run_id export
-> raw-frame lineage
-> derived location/LTE/GNSS/IMU/power features
-> observation windows
-> labels and quality checks
-> JSONL dataset shard plus manifest
```

The output should make both successful and failed field runs useful to the
fusion algorithm without turning transient Dashboard state into training data.

## Acceptance

- [x] Define an initial `location_fusion_sample` schema or documented JSONL
      manifest shape.
- [x] Build observation windows from a named test-run export, including
      `location_report`, `location_observation`, ACK, raw-frame summaries, and
      observability summary when available.
- [x] Preserve lineage to raw evidence by frame ID, byte length, SHA-256, CRC,
      parse status, parser version, command ID, sequence, firmware version,
      and server receive time.
- [x] Include failure windows such as no-fix, stale command, parse failure,
      checksum failure, missing ACK, reset, transport failure, or missing
      observation.
- [x] Include label source and confidence fields, even when the initial label
      is only `unknown`, `rule`, `user_confirmation`, or `operator_note`.
- [x] Add privacy class, redaction state, consent/training flags, and explicit
      exclusion reasons for data that should not enter training.
- [x] Add quality checks for missing timestamps, sequence regressions,
      duplicate command execution, split leakage, and missing raw-frame
      lineage.
- [x] Keep the first export as JSONL plus manifest under ignored runtime or
      report paths unless a tiny synthetic fixture is explicitly added for
      tests.
- [x] Run `python scripts/context_lint.py`.
- [x] Run focused tests for the export script/schema. Run full
      `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` if server
      behavior changes.

## Boundary

DATA-001 is a data foundation task. It should make large future data
collection possible, but it does not itself collect a large corpus, train a
model, evaluate positioning accuracy, or change the KR-003 raw LTE runtime
loop.

## Completion Evidence

- Schema: `shared/contracts/location_fusion_sample.schema.json`.
- Exporter: `scripts/export_location_fusion_dataset.py`.
- Focused tests:
  `python -m unittest quality_tests.test_location_fusion_dataset_export -v`.
- Contract regression tests:
  `python -m unittest quality_tests.test_message_hub_contracts -v`.
- Context lint: `python scripts/context_lint.py` passed.
- Full verification:
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed
  299 tests.
- Output policy: JSONL samples and manifest are written under an operator
  selected output directory, with default runtime output under ignored
  `reports/location_fusion_datasets/`.
- Boundary held: no firmware, hardware, VPS, server runtime behavior, or wire
  protocol changes were made.

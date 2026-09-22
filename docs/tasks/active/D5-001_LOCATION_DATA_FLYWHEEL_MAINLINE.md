---
id: D5-001
title: D5 location data flywheel mainline
status: active
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-09
last_updated: 2026-07-11

context:
  - docs/product/NORTH_STAR.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md

allowed_paths:
  - scripts/
  - server/
  - pc_simulator/
  - docs/development/
  - docs/current/
  - docs/tasks/
  - shared/contracts/
  - quality_tests/
  - reports/

out_of_scope:
  - training a learned model before labelled D2-quality evidence exists
  - deploying a model to device
  - safety-classification model expansion
  - reading private raw coordinates outside explicit bounded evidence inputs
  - changing firmware protocol fields
execution_state: queued
owner: unassigned
reviewed_at: 2026-09-22
---

This task serves D5. It starts the data flywheel for location accuracy while
D2 establishes the first measurable accuracy baseline.

# Goal

Turn field evidence into a repeatable location-data pipeline:

```text
field evidence
-> cleaned observation windows
-> labels and privacy review
-> dataset manifest
-> rule/model evaluation plan
-> next field version
```

# Expected Result

The project can ingest explicit D2/FIELD evidence, summarize data readiness,
queue human review/label decisions, and produce dataset/evaluation handoff
artifacts without claiming model performance or starting training prematurely.

# Acceptance Criteria

- [x] Define the D5 location-data flywheel status model and Dashboard summary.
- [x] Bind D2 baseline reports as first-class data sources, not transient
      Dashboard snapshots.
- [x] Reuse existing DATA/labeling pipeline assets where compatible, but orient
      them to location accuracy labels and privacy gates.
- [x] Produce a review packet format for reference point, known-place, no-fix,
      and bad-fix samples.
- [x] Produce a dataset manifest only from explicitly selected evidence with
      privacy/training flags.
- [x] Keep model training/deployment blocked until labelled D2-quality samples
      are available and founder approves the next model task.
- [ ] First real D2 baseline report is consumed into the D5 location-data
      flywheel and reviewed.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

Not required for the D5 plumbing baseline. Hardware evidence comes from D2,
FIELD, and PWR runs and must be explicitly referenced by path.

# Decisions

- D5 immediate mainline is location improvement. Tiny Safety and
  safety-classification assets remain retained for later reuse but are not the
  current flywheel target.
- Synthetic data may be used only for tool/format tests. It must stay
  synthetic-only and cannot be promoted to product model performance evidence.

# Progress

- 2026-07-09 D5 location-data flywheel plumbing:
  - Added `scripts/summarize_location_data_flywheel.py`, an offline
    no-hardware tool that converts a bounded D2
    `location_accuracy_report.json` into Dashboard-compatible
    `data_flywheel_status.json`.
  - The tool also writes a location review packet and a location dataset
    manifest gate under `reports/data_flywheel/<run-id>/`.
  - Review records are oriented to `location_reference_point`,
    `location_known_place`, `location_no_fix`, and `location_bad_fix` labels.
  - Dataset records are emitted only from an explicit selection file with
    privacy, quality, training, and split-leakage review flags; model training
    remains blocked pending founder approval.
  - Added focused tests for Dashboard compatibility, privacy redaction, and
    explicit-selection gating.
- 2026-07-09 D5 Dashboard location summary:
  - The Data Flywheel panel now preserves and displays D2 baseline count,
    reference points, fixed/no-fix attempts, source report summary, review
    packet path, and dataset manifest gate path.
- 2026-07-09 D2->D5 post-field pipeline:
  - Added `scripts/run_location_d2_d5_pipeline.py`, a one-command offline
    processor from explicit Message Hub export plus FIELD manifest into D2
    baseline, D5 data-flywheel status, and a bounded pipeline summary.
- 2026-07-10 field readiness observer:
  - Added `scripts/observe_field_readiness.py` so long field sessions can
    produce bounded server-side readiness samples and reports while preserving
    the D5 boundary: summaries and artifact refs only, no raw private
    coordinate export and no model-training claim.
- 2026-07-11 bounded D2 intake:
  - D2 post-run intake now uses an authenticated device/time-window export
    derived from the field manifest instead of the firmware's indefinitely
    accumulating test-run ID.
  - Truncated exports, incomplete timestamps, and device mismatches stop before
    D5 review artifacts are produced; no model-training gate was relaxed.

# Completion Evidence

- Changed files: `scripts/summarize_location_data_flywheel.py`,
  `scripts/run_location_d2_d5_pipeline.py`, `server/message_hub.py`,
  `quality_tests/test_location_data_flywheel.py`,
  `quality_tests/test_location_d2_d5_pipeline.py`,
  `quality_tests/test_message_hub_dashboard.py`
- Test result: focused D5/D2/Dashboard tests PASS; `python
  scripts/context_lint.py` PASS; `powershell -ExecutionPolicy Bypass -File
  scripts\verify.ps1` PASS with 536 tests
- Data evidence: no real D2 baseline report was present locally during this
  implementation, so only synthetic fixture tests were used for tool behavior
- Remaining risks: first real D2 outdoor baseline still needs to be analyzed,
  then rerun through the D5 flywheel for review and selection

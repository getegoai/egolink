---
id: D5-001
title: D5 location data flywheel mainline
status: active
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-09
last_updated: 2026-07-09

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

- [ ] Define the D5 location-data flywheel status model and Dashboard summary.
- [ ] Bind D2 baseline reports as first-class data sources, not transient
      Dashboard snapshots.
- [ ] Reuse existing DATA/labeling pipeline assets where compatible, but orient
      them to location accuracy labels and privacy gates.
- [ ] Produce a review packet format for reference point, known-place, no-fix,
      and bad-fix samples.
- [ ] Produce a dataset manifest only from explicitly selected evidence with
      privacy/training flags.
- [ ] Keep model training/deployment blocked until labelled D2-quality samples
      are available and founder approves the next model task.

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

# Completion Evidence

- Changed files:
- Test result:
- Data evidence:
- Remaining risks:

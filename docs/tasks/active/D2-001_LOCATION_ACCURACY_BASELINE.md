---
id: D2-001
title: D2 location accuracy baseline and metric gate
status: active
priority: high
requires_hardware: true
serves_demo: D2
created: 2026-07-09
last_updated: 2026-07-09

context:
  - docs/product/NORTH_STAR.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/tasks/active/FIELD-003_OUTDOOR_GNSS_ACCEPTANCE.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md

allowed_paths:
  - scripts/
  - server/
  - docs/development/
  - docs/hardware/
  - docs/current/
  - docs/tasks/
  - quality_tests/
  - reports/gnss/
  - reports/

out_of_scope:
  - product accuracy claims
  - learned model training or deployment
  - safety-classification model work
  - firmware GNSS driver changes unless a later hardware task explicitly allows them
  - raw private coordinate publication outside bounded evidence
---

This task serves D2. The current lowest active mainline demo is D2; D1 field
and power runs continue as regression, not as a transition blocker.

# Goal

Create the first repeatable location-accuracy baseline for the active 4G board:
reference points, fix rate, TTFF, median error, and an explainable report that
can drive later AI/rule improvements.

# Expected Result

After a D2 run, the project can answer these questions with evidence:

- How often does the device produce a usable fix outdoors?
- How long does a cold/warm attempt take?
- What is the median and p90 error against reference points?
- When there is no fix, which evidence explains why?
- Does the Dashboard/map surface show enough context for review?

# Acceptance Criteria

- [x] FIELD-003 protocol is current and runnable for D2 reference-point tests.
- [x] A D2 analysis script computes fix rate, TTFF, median error, p90 error,
      and per-point breakdown from bounded VPS/export evidence.
- [x] A synthetic fixture test protects error-distance and TTFF calculations.
- [x] A D2 report writes JSON/Markdown under `reports/location_accuracy/`.
- [x] Dashboard/Field Test Results can surface the latest D2 baseline summary
      without exposing private raw coordinates.
- [x] D2 baseline clearly records non-claims: engineering baseline only, no
      product accuracy guarantee.
- [ ] First real outdoor D2 baseline run is analyzed and reviewed.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Hardware Validation

- Board: connectivity-node Waveshare ESP32-S3-SIM7670G-4G.
- Connection: device -> LTE -> VPS Message Hub; USB only for flash/debug.
- Expected output: reference-point attempts with fix/no-fix, timestamps,
  coordinates when available, and bounded reference labels.
- Evidence path: `reports/location_accuracy/D2-001-<date>/`.

# Decisions

- Continuous outdoor testing remains ongoing regression. D2 acceptance is the
  creation of a measurable baseline and review loop, not the end of testing.
- D5 may prepare data flywheel plumbing in parallel, but training or model
  improvement claims require D2-quality labelled evidence.

# Progress

- 2026-07-09 D2 baseline toolchain:
  - Added `scripts/analyze_location_accuracy_baseline.py`, a no-hardware
    wrapper over FIELD-003 GNSS analysis that writes
    `location_accuracy_report.json` and `location_accuracy_report.md` under
    `reports/location_accuracy/`.
  - The report exposes fix rate, TTFF median/p90, median error, p90 error,
    per-point breakdown, and EALE-P0 radius comparison while omitting raw
    private coordinates from Dashboard summaries.
  - Added focused synthetic tests for D2 metric computation, CLI report
    writing, and privacy/non-claim boundaries.
- 2026-07-10 server-side field readiness observer:
  - Added `scripts/observe_field_readiness.py`, a read-only preflight and
    long-run observer for the VPS Message Hub / Dashboard path.
  - It checks health, `/api/state`, Dashboard markers, target-device
    freshness, D1 field readiness, no-key map status, Field Test Results, and
    D5 data-flywheel availability before or during D2 field work.
  - It does not replace the pending real FIELD-003 reference-point run.

# Completion Evidence

- Changed files: `scripts/analyze_location_accuracy_baseline.py`,
  `quality_tests/test_location_accuracy_baseline.py`
- Test result: focused D2/FIELD/Dashboard tests PASS; `python
  scripts/context_lint.py` PASS; `powershell -ExecutionPolicy Bypass -File
  scripts\verify.ps1` PASS with 532 tests
- Hardware result: pending first real D2 outdoor baseline run
- Evidence path: future runs write to `reports/location_accuracy/<run-id>/`
- Remaining risks: real D2 metrics still depend on an outdoor reference-point
  run and a matching VPS export/field manifest

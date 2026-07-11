---
id: D2-001
title: D2 location accuracy baseline and metric gate
status: active
priority: high
requires_hardware: true
serves_demo: D2
created: 2026-07-09
last_updated: 2026-07-11

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
- 2026-07-11 D2 field-run automation:
  - Added `scripts/prepare_d2_field_kit.py` to generate the strict three-point,
    30-attempt FIELD-003 manifest, runbook, checklist, and bounded commands.
  - Extended `scripts/run_location_d2_d5_pipeline.py` so post-run processing
    can fetch a named Message Hub test-run export read-only and preserve it
    under `reports/gnss/<run-id>/` before producing D2 and D5 reports.
  - The first real reference-point run remains the only open D2 acceptance
    item; partial runs remain review evidence, not accuracy acceptance.
  - VPS smoke backfilled the missing non-secret test-run registry row for the
    firmware-emitted `MODEL-DEVICE-006-hw-20260707-d1` ID. Read-only export
    then succeeded with 39,745 messages and 8,548 raw frames; the larger
    historical batch is why the post-run export timeout defaults to 120 s.
- 2026-07-11 mobile reference capture:
  - Dashboard `/d2-reference-capture` now creates a FIELD-003-compatible
    manifest from browser-local reference points and attempt timestamps.
  - The strict analyzer now rejects `phone_browser_single_fix`; only a phone
    five-minute average, satellite map pick, or survey marker can pass the
    reference-method gate.
- 2026-07-11 bounded field-window export:
  - Added authenticated `GET /api/v1/devices/{device_id}/field-export` with a
    48-hour window cap, bounded collections, raw-frame redaction, and explicit
    completeness/truncation metadata.
  - The one-command D2 -> D5 processor now reads field start/end from the
    manifest, verifies device identity, and rejects truncated exports before
    analysis. Existing named test-run exports remain compatible.
  - The first real reference-point run remains the only open acceptance item;
    this change removes accumulated historical records from that run's input.
- 2026-07-11 local reference overlay:
  - Dashboard can now import a FIELD-003 manifest locally and overlay reference
    markers with the server trajectory without uploading coordinates.
  - MAP-001 Web capability is complete; real D2 metric production still waits
    for the first outdoor reference run.
- 2026-07-11 historical VPS baseline:
  - Added `scripts/build_d2_historical_baseline.py` to summarize explicitly
    named field-observer windows through the bounded read-only VPS export.
  - Historical outdoor evidence contains 203 unique location-report events:
    96 fix and 107 no-fix, for provisional event fix rate `0.472906`.
  - Median/P90 position error and TTFF remain not measurable because these
    runs have no external reference truth or attempt boundaries. This is a
    useful starting observation, not the open strict FIELD-003 acceptance.

# Completion Evidence

- Changed files: D2 baseline/field-kit/pipeline scripts, bounded Message Hub
  export, Dashboard reference capture, focused tests, and routed docs
- Test result: focused D2/FIELD/Message Hub tests PASS; `python
  scripts/context_lint.py` PASS; latest `powershell -ExecutionPolicy Bypass
  -File scripts\verify.ps1` PASS with 551 tests
- Hardware result: pending first real D2 outdoor baseline run
- Evidence path: future runs write to `reports/location_accuracy/<run-id>/`
- Remaining risks: real D2 metrics still depend on an outdoor reference-point
  run and a matching VPS export/field manifest

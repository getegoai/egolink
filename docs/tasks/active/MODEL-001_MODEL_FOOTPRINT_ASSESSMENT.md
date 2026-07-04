---
id: MODEL-001
title: Model footprint assessment
status: active
priority: high
requires_hardware: false
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md
  - docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
  - docs/modeling/MODEL_ARCHITECTURE.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md

allowed_paths:
  - docs/modeling/
  - docs/product/
  - docs/roadmap/
  - docs/current/
  - docs/tasks/
  - docs/generated/
  - quality_tests/

out_of_scope:
  - training MotionNet, AudioGate, VisionGate, or learned ContextRouter
  - changing model behavior, thresholds, schemas, contracts, or artifacts
  - changing firmware logic, model runtime, OTA, or hardware configuration
  - replacing PROD-001 `TBD(MODEL-001)` values before measured evidence exists
  - selecting a production MCU
  - collecting private user data
---

# Problem

ADR-0002 makes on-device AI a V1 core differentiator, and PROD-001 cannot
select a production MCU until MotionNet-class RAM, flash, latency, and
sleep-vs-inference power are measured. The repository needs a MODEL-001
protocol before any estimate, build, runtime benchmark, or MCU comparison can
be treated as evidence.

# Expected Result

Open MODEL-001 and define the footprint assessment protocol, evidence levels,
minimum report fields, and non-claim boundaries. Keep actual model artifacts,
runtime measurement, power measurement, and MCU comparison as remaining work.

# Acceptance Criteria

- [x] A current document under `docs/modeling/` defines the MODEL-001 footprint
      assessment protocol.
- [x] The protocol separates estimates, build verification, runtime RAM/latency
      measurement, power measurement, and candidate comparison.
- [x] The protocol lists minimum report fields for RAM, flash, latency, energy,
      artifact identity, source status, known gaps, and evidence paths.
- [x] The protocol states that `TBD(MODEL-001)` values cannot be replaced in
      PROD-001 until reviewed measured evidence exists.
- [x] A focused quality test protects the protocol and non-claim boundaries.
- [ ] ESP32-S3 static footprint evidence is produced for a real or
      representative MotionNet-class artifact.
- [ ] ESP32-S3 runtime RAM/latency evidence is produced for the same artifact.
- [ ] Sleep-vs-inference power evidence is produced or explicitly deferred to
      the power measurement path.
- [ ] ESP32-S3, STM32U5A5, and Apollo4 are compared at a common evidence level.
- [ ] PROD-001 `TBD(MODEL-001)` values are replaced only after review.

# Validation Commands

```powershell
python -m unittest quality_tests.test_model_footprint_assessment_doc -v
python scripts/context_lint.py
git diff --check
```

Run full verify if code, behavior, contracts, firmware, or report tooling
changes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Not required for the protocol baseline.
- Future runtime and power evidence must identify board, firmware or benchmark
  build, model artifact, measurement path, timestamp, and evidence path.

# Decisions

- MODEL-001 starts as an active task, not completed, because real
  RAM/flash/latency/power measurements are still pending.
- Build size is not runtime RAM, latency, or energy evidence.
- MCU selection remains blocked until measured evidence and founder/business
  constraints converge.

# Progress Evidence

- protocol-baseline (2026-07-04, codex): created the MODEL-001 protocol and
  focused quality test. Remaining measurement gates stay open.
- Changed files:
  - `docs/modeling/MODEL_FOOTPRINT_ASSESSMENT.md`
  - `docs/tasks/active/MODEL-001_MODEL_FOOTPRINT_ASSESSMENT.md`
  - `docs/roadmap/V1_PRODUCT_PLAN.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/current/STATUS.md`
  - `docs/generated/PROGRESS_BOARD.md`
  - `docs/generated/progress_board.json`
  - `quality_tests/test_model_footprint_assessment_doc.py`
- Test result:
  - `python -m unittest quality_tests.test_model_footprint_assessment_doc -v`:
    PASS (4 tests).
  - `python scripts/context_lint.py`: PASS.
  - `python scripts/build_progress_board.py`: PASS
    (`active=4`, `done=76`).
  - `git diff --check`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS
    (355 tests).
- Hardware result: not applicable for protocol baseline.
- Remaining risks:
  - No actual model artifact, benchmark, ESP32-S3 runtime measurement, power
    measurement, or MCU comparison exists yet.

# Builder Prompt

```text
Read docs/tasks/active/MODEL-001_MODEL_FOOTPRINT_ASSESSMENT.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
in this packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Produce or extend MODEL-001 evidence without training a model,
changing model behavior, changing firmware/protocol/contracts, selecting an
MCU, or replacing PROD-001 TBD values without reviewed evidence. Run the
validation commands before finishing and return changed files, validation
output, evidence paths, unresolved decisions, and risks.
```

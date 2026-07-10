---
id: DATA-009
title: Synthetic scenario generator
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-05
last_updated: 2026-07-05

context:
  - docs/product/NORTH_STAR.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/tasks/done/DATA-006_DATA_FLYWHEEL_PIPELINE_RUNNER.md
  - docs/tasks/done/TRAIN-002_TRAINING_EXPERIMENT_REGISTRY.md

allowed_paths:
  - scripts/generate_synthetic_scenarios.py
  - quality_tests/test_synthetic_scenario_generator.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-009_SYNTHETIC_SCENARIO_GENERATOR.md

out_of_scope:
  - contacting hardware, opening serial ports, flashing firmware, or sending Message Hub commands
  - deploying to the VPS or touching GitLab
  - training or evaluating a model, integrating a runner, or producing model artifacts
  - copying candidate DBs, raw candidate records, private coordinates, raw payloads, runtime JSONL logs, or private training endpoints
  - using synthetic data as field evidence, release acceptance, model metrics, footprint, latency, power, battery-life, or product-readiness proof
---

# Goal

Serve D5: keep the model/data flywheel moving while hardware field evidence is
sparse by generating explicit synthetic-only scenario recordings that exercise
recording, annotation, candidate-store, review, dataset-handoff, and experiment
registry plumbing.

# Acceptance Criteria

- [x] A bounded CLI can generate deterministic synthetic session recordings
      under `reports/synthetic_scenarios/<run-id>/`.
- [x] Generated recordings carry explicit synthetic metadata, structured-only
      privacy, no raw audio/image permissions, and annotation training requests
      that still require review.
- [x] `--run-pipeline` ingests named generated recordings through DATA-006 and
      reports `needs_review` without exposing candidate DB paths or raw records.
- [x] `--review-synthetic` is explicit and can promote only the generated
      synthetic candidates for a dry-run `ready_for_training_handoff` /
      TRAIN-002 `ready_for_runner` handoff.
- [x] Reports state that synthetic records are not field evidence, release
      acceptance, model metrics, or power evidence.
- [x] Focused tests pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_synthetic_scenario_generator
python -m unittest quality_tests.test_training_candidate_store quality_tests.test_training_experiment_registry
python -m py_compile scripts\generate_synthetic_scenarios.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `scripts/generate_synthetic_scenarios.py`,
  `quality_tests/test_synthetic_scenario_generator.py`,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/STATUS.md`, and this packet.
- Local dry-run evidence: `reports/synthetic_scenarios/data009-local-smoke-20260705/`
  after running `scripts\generate_synthetic_scenarios.py --review-synthetic`.
- Validation: focused synthetic generator tests passed (3 tests); focused
  candidate-store and training-experiment tests passed (20 tests);
  `python -m py_compile scripts\generate_synthetic_scenarios.py` passed;
  `python scripts\context_lint.py` passed; `git diff --check` passed; full
  `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed (423
  tests).
- Remaining risks: synthetic data can keep the pipeline and future runner
  integration moving, but it cannot replace D1/D3 field recordings, human/user
  labeling, privacy review, split-leakage review, model evaluation, footprint
  measurement, power measurement, shadow-mode testing, or release gates.

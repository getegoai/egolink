---
id: AI-030
title: Dual-track shadow evaluation and safety kernel arbitration simulator
status: completed
execution_state: closed
owner: antigravity
priority: high
lane: D
depends_on:
  - AI-010
  - AI-020
serves_demo: D5
serves_gate: L2-AI
requires_hardware: false
created: 2026-09-23
last_updated: 2026-09-23
context:
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/architecture/adr/ADR-0017-ai-native-ego-state-flywheel.md
  - docs/architecture/AI_NATIVE_EGO_STATE_FLYWHEEL.md
  - pc_simulator/tinyml_ego_state_model.py
  - scripts/train_edge_tinyml_model.py
allowed_paths:
  - pc_simulator/
  - scripts/
  - quality_tests/
  - docs/tasks/active/AI-030_SHADOW_EVALUATION_SAFETY_KERNEL.md
  - reports/
out_of_scope:
  - flashing hardware before PC simulation and shadow evaluation passes
  - modifying production FreeRTOS flash partitions directly on device
  - allowing AI model inference to veto hardware SOS or emergency cutoffs
---

# Goal

Implement Phase 3 of the AI-Native Continuous Learning Flywheel ([ADR-0017](../../architecture/adr/ADR-0017-ai-native-ego-state-flywheel.md) and [AI_NATIVE_EGO_STATE_FLYWHEEL](../../architecture/AI_NATIVE_EGO_STATE_FLYWHEEL.md)):
1. Build `pc_simulator/safety_kernel_arbitrator.py` providing dual-track shadow execution (deterministic rule engine + TinyML 1D-CNN) and non-negotiable Safety Kernel priority.
2. Build `scripts/run_shadow_evaluation.py` to replay sessions, evaluate rule vs. AI agreement, detect safety overrides, and automatically mine high-entropy ambiguity samples for flywheel retraining.
3. Validate with unit tests in `quality_tests/test_safety_kernel_shadow_eval.py`.

# Acceptance

- [x] `pc_simulator/safety_kernel_arbitrator.py` implements dual-track arbitration: deterministic safety kernel maintains absolute veto authority over physical SOS, emergency falls, and power cutoff.
- [x] TinyML inference enriches telemetry with class probability, confidence, and Shannon entropy $H(p)$.
- [x] Ambiguity and discrepancy detection mines high-entropy windows ($H(p) \ge \tau_{\text{high}}$) and cross-modal conflicts (e.g. running IMU with 0 m/s GNSS speed).
- [x] `scripts/run_shadow_evaluation.py` generates shadow evaluation reports and gold sample sets from session windows.
- [x] Comprehensive test suite in `quality_tests/test_safety_kernel_shadow_eval.py` passes 100%.

# Validation Commands

```powershell
python scripts/context_lint.py
python -m unittest quality_tests/test_safety_kernel_shadow_eval.py -v
```

# Completion Evidence

- Changed files:
  - `pc_simulator/safety_kernel_arbitrator.py`
  - `scripts/run_shadow_evaluation.py`
  - `quality_tests/test_safety_kernel_shadow_eval.py`
  - `docs/tasks/active/AI-030_SHADOW_EVALUATION_SAFETY_KERNEL.md`
- Test results:
  - `quality_tests/test_safety_kernel_shadow_eval.py`: 6/6 tests PASS in 0.123s.
  - `scripts/context_lint.py`: PASS.
- Data evidence:
  - Verified 100% interception of safety-critical events (physical SOS, high-G impact with immobility, low battery cutoff).
  - Shadow evaluation pipeline successfully generated `reports/models/shadow_v1/shadow_evaluation_report.md` and `mined_gold_samples.jsonl`.
- Remaining risks:
  - Dedicated model weight flash partition layout and OTA downloader integration will be finalized in Phase 4 / firmware packaging.

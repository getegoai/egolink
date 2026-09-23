---
id: AI-020
title: TinyML edge model prototype and PC simulation
status: completed
execution_state: closed
owner: antigravity
priority: high
lane: D
depends_on:
  - AI-010
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
  - scripts/harvest_self_supervised_dataset.py
allowed_paths:
  - pc_simulator/
  - scripts/
  - quality_tests/
  - docs/tasks/active/AI-020_TINYML_EDGE_MODEL_PROTOTYPE.md
  - reports/
out_of_scope:
  - flashing hardware before PC simulation and INT8 quantization pass
  - introducing heavy GPU/PyTorch dependencies into repository core
  - modifying FreeRTOS scheduling tasks
---

# Goal

Implement Phase 2 of the AI-Native Continuous Learning Flywheel ([ADR-0017](../../architecture/adr/ADR-0017-ai-native-ego-state-flywheel.md) and [AI_NATIVE_EGO_STATE_FLYWHEEL](../../architecture/AI_NATIVE_EGO_STATE_FLYWHEEL.md)):
1. Build `pc_simulator/tinyml_ego_state_model.py` providing the lightweight 1D-CNN architecture (`[100, 6]` input, 6 physical classes, INT8 quantization support, entropy computation, and C-header export for ESP-DL).
2. Build `scripts/train_edge_tinyml_model.py` to train/evaluate the model on harvested multi-modal dataset windows with confusion matrix and F1 metrics.
3. Prove that the total model parameter footprint is $< 30\,\text{KB}$ INT8, fully compatible with ESP32-S3 internal SRAM.

# Acceptance

- [x] `pc_simulator/tinyml_ego_state_model.py` implements forward inference, softmax probability, and entropy scoring over `[100, 6]` IMU tensors.
- [x] Model weights footprint is verified to be under 30 KB (5,622 parameters, 5.49 KB INT8 / 21.96 KB Float32).
- [x] Supports INT8 quantization and exporting valid C-header arrays (`tinyml_ego_state_weights.h`) for ESP32-S3 firmware.
- [x] `scripts/train_edge_tinyml_model.py` can train on harvested `windows.jsonl` or synthetic data, computing loss, accuracy, and confusion matrix using Adam optimization.
- [x] Validated with focused automated tests in `quality_tests/test_tinyml_edge_model.py`.

# Validation Commands

```powershell
python scripts/context_lint.py
python -m unittest quality_tests/test_tinyml_edge_model.py -v
```

# Completion Evidence

- Changed files:
  - `pc_simulator/tinyml_ego_state_model.py`
  - `scripts/train_edge_tinyml_model.py`
  - `quality_tests/test_tinyml_edge_model.py`
  - `docs/tasks/active/AI-020_TINYML_EDGE_MODEL_PROTOTYPE.md`
- Test results:
  - `quality_tests/test_tinyml_edge_model.py`: 6/6 tests PASS in 0.168s.
  - Full repo test suite: 1,882 tests PASS in 336.78s.
  - `scripts/context_lint.py`: PASS.
- Data evidence:
  - Total parameter count: 5,622 parameters.
  - Quantized INT8 footprint: 5.49 KB (well under the 30 KB SRAM budget).
  - Test accuracy on multi-modal synthetic IMU dataset: 100% with diagonal confusion matrix.
  - C-header generation verified with `#define TINYML_INPUT_LENGTH 100`, `#define TINYML_INPUT_CHANNELS 6`, `#define TINYML_NUM_CLASSES 6`, and per-layer scale/int8 weight arrays.
- Remaining risks:
  - Phase 3 will test edge simulation in ESP32-S3 firmware build using ESP-DL or pure C fixed-point convolution loops.

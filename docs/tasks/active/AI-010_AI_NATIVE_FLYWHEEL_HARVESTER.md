---
id: AI-010
title: AI-Native multi-modal self-supervised dataset harvester
status: active
execution_state: ready
owner: antigravity
priority: high
lane: D
depends_on: []
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
  - shared/contracts/ego_state_estimation_v0.schema.json
  - shared/contracts/ego_state_evidence_chain_v0.schema.json
allowed_paths:
  - scripts/
  - quality_tests/
  - docs/tasks/active/AI-010_AI_NATIVE_FLYWHEEL_HARVESTER.md
  - reports/
out_of_scope:
  - modifying firmware code or hardware partition tables before offline pipeline passes
  - training a model before harvester verification
  - committing private unredacted user locations
---

# Goal

Implement `scripts/harvest_self_supervised_dataset.py`, the Phase 1 entry point of the AI-Native Continuous Learning Flywheel ([ADR-0017](../../architecture/adr/ADR-0017-ai-native-ego-state-flywheel.md) and [AI_NATIVE_EGO_STATE_FLYWHEEL](../../architecture/AI_NATIVE_EGO_STATE_FLYWHEEL.md)).
It ingests real-world field telemetry (such as Boot 211's 8,724 records), performs 5-second (100-sample @ 20Hz) sliding window segmentation, executes cross-modal physical self-supervision (GNSS Doppler speed, cellular handovers, fuel gauge anchors) to assign pseudo-ground-truth labels, extracts uncertainty ambiguity samples, and outputs clean dataset manifests and quality reports.

# Acceptance

- [x] `scripts/harvest_self_supervised_dataset.py` can ingest raw JSONL/DB telemetry exports and slice into 100-sample (5s @ 20Hz) IMU windows.
- [x] Cross-modal self-supervision rules auto-label cycling, vehicle, walking, and stationary samples based on GNSS speed vectors and network continuity without human intervention.
- [x] Ambiguity/contradiction detection flags high-entropy windows (e.g. high IMU motion with zero speed) as high-value samples.
- [x] Generates a structured dataset manifest and summary report preserving source lineage, timestamps, and privacy redaction.
- [x] Validated with focused automated tests in `quality_tests/test_ai_native_harvester.py`.

# Validation Commands

```powershell
python scripts/context_lint.py
python -m unittest quality_tests/test_ai_native_harvester.py -v
```

# Completion Evidence

- Changed files: `scripts/harvest_self_supervised_dataset.py`, `quality_tests/test_ai_native_harvester.py`, `docs/tasks/active/AI-010_AI_NATIVE_FLYWHEEL_HARVESTER.md`
- Test results: 7 unit/integration tests PASS in 0.041s (`test_ai_native_harvester.py`); `python scripts/context_lint.py` PASS
- Data evidence: Multi-modal binary IMU chunk decoding, 100-sample sliding windows, physical cross-supervision, ambiguity mining, SQLite DB extraction, and privacy coordinate redaction proven in automated test suite
- Remaining risks: Model training pipeline (Phase 2) requires executing this harvester against the production Message Hub VPS database to produce the initial candidate dataset manifest

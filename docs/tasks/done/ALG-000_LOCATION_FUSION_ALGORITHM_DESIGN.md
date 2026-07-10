---
id: ALG-000
title: Location Fusion Algorithm Design
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
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/tasks/done/DATA-001_LOCATION_FUSION_DATASET_BASELINE.md
  - shared/contracts/

allowed_paths:
  - docs/CONTEXT_INDEX.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/ALG-000_LOCATION_FUSION_ALGORITHM_DESIGN.md

out_of_scope:
  - changing firmware logic or flashing hardware
  - changing live device wire protocol
  - changing server runtime behavior
  - training or publishing a learned fusion model
  - claiming positioning accuracy, GNSS acceptance, cell-only positioning, or product readiness
  - committing private coordinates, raw Wi-Fi BSSID values, raw audio, raw images, or private device logs
  - modifying GitLab or unrelated VPS services
---

# ALG-000 Location Fusion Algorithm Design

## Goal

Freeze the P0 location-fusion algorithm direction as EALE-P0:
Evidence-Aware Location Estimator.

The design should turn the project from "try to get a coordinate" into a
versioned, explainable evidence system:

```text
raw-frame evidence
-> derived events
-> DATA-001 observation windows
-> evidence normalization
-> candidate generation
-> conservative server-side location_belief
```

## Acceptance

- [x] Define EALE-P0 as a server-side, derived-only rule/scoring baseline.
- [x] Keep public location states compatible with
      `Fine`, `Coarse`, `Predicted`, and `Unknown`.
- [x] Document input observation windows and DATA-001 integration.
- [x] Document source evidence normalization, source status, evidence status,
      lineage, quality, and privacy treatment.
- [x] Document feature roles for GNSS, cell/LTE, Wi-Fi, IMU, power,
      transport, runtime, and memory.
- [x] Document candidate generation, fusion decision rules, confidence
      scoring, failure taxonomy, and output shape.
- [x] Keep learned models as future optional replacements, not KR-004
      release content.
- [x] Record KR-004 gate direction and follow-on tasks.
- [x] Run `python scripts/context_lint.py`.

## Boundary

ALG-000 is a design freeze only. It does not change firmware, server runtime
behavior, Web behavior, public contracts, or hardware state. It does not train
a model, collect a corpus, or claim location accuracy.

## Completion Evidence

- Design document: `docs/development/LOCATION_FUSION_ALGORITHM.md`.
- Context routing: `docs/CONTEXT_INDEX.md`.
- Roadmap references: `docs/development/LOCATION_ENGINE.md`,
  `docs/development/LOCATION_DATASET.md`, and
  `docs/current/ROADMAP_EGOLINK_P0.md`.
- Task tree update: `docs/tasks/TASK_TREE.md`.
- Validation: `python scripts/context_lint.py` passed.

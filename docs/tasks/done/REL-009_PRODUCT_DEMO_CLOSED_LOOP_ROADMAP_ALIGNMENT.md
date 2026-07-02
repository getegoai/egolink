---
id: REL-009
title: Product Demo Closed Loop Roadmap Alignment
status: completed
priority: high
requires_hardware: false
created: 2026-07-02
last_updated: 2026-07-02
completed: 2026-07-02

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/development/DEV_FLOW.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/development/LOCATION_DATASET.md
  - docs/tasks/TASK_TREE.md

allowed_paths:
  - docs/current/KEY_RELEASES.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-009_PRODUCT_DEMO_CLOSED_LOOP_ROADMAP_ALIGNMENT.md

out_of_scope:
  - firmware changes or flashing
  - sending hardware control commands
  - changing live device wire protocol or raw-frame profile
  - creating a KR-007 or KR-008 release manifest
  - changing Message Hub runtime behavior
  - training or shipping a learned model
  - claiming product readiness, positioning accuracy, real reconnect recovery,
    durable store-forward, long LTE stability, GNSS acceptance, battery/power
    behavior, or enclosure behavior
  - modifying GitLab or unrelated VPS services
---

# REL-009 Product Demo Closed Loop Roadmap Alignment

## Goal

Bring the user-provided fusion-algorithm discussion back into the tracked
release path without renaming the already released KR-006.

The discussion proposed:

```text
KR-004: multi-source observation baseline
KR-005: reconnect/cache/retry/stability
KR-006: product demo closed loop
```

The repository later assigned KR-006 to the raw POST retry fault-injection
baseline. This task preserves that existing KR-006 meaning and moves the
product-demo closed loop into a later planned gate.

## Result

- `docs/current/KEY_RELEASES.md` now records the planned sequence after KR-006:
  KR-007 as the reconnect/store-forward evidence baseline candidate, followed
  by KR-008 or `DEMO-001` as the product-demo closed loop candidate.
- `docs/current/ROADMAP_EGOLINK_P0.md` now spells out the R4 product-demo loop:
  user trigger or safety event, device location/status request, LTE raw-frame
  uplink, multi-source evidence aggregation, EALE-P0 belief, user
  confirmation or safety rule, report export, and Web replay/review.
- `docs/tasks/TASK_TREE.md` now routes execution toward KR-007 candidate
  preparation before broader stability work and keeps the product-demo loop
  distinct from KR-006.

## Boundary

REL-009 is a documentation and roadmap alignment task only. It does not create
the KR-007 manifest, create the product-demo implementation, deploy to the VPS,
flash firmware, run hardware, change protocol contracts, train a model, or
make any product-readiness claim.

---
id: DATA-029
title: D1 labeling review packet Web/API visibility
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-06
last_updated: 2026-07-06

context:
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/tasks/done/DATA-028_D1_LABELING_REVIEW_PACKET.md

allowed_paths:
  - server/message_hub.py
  - scripts/deploy_message_hub_vps.ps1
  - scripts/prepare_d1_field_kit.py
  - quality_tests/test_message_hub_dashboard.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_d1_field_kit.py
  - docs/development/DATA_FLYWHEEL_PIPELINE.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-029_D1_LABELING_REVIEW_PACKET_VISIBILITY.md
  - docs/generated/PROGRESS_BOARD.md
  - docs/generated/progress_board.json

out_of_scope:
  - reading or exposing sample JSONL rows, raw payloads, exact coordinates, reviewer-private fields, feature rows, targets, candidate DBs, private endpoints, or model artifacts
  - marking items reviewed, applying review decisions, writing candidate DBs, creating training samples, training/evaluating models, measuring model footprint/power, deploying inference, or making release claims
  - contacting hardware, flashing firmware, sending Message Hub commands, or deploying to the VPS
---

# Goal

Serve D5: make the bounded D1 labeling review packet visible in the Message
Hub API and Dashboard so post-run human-review work is visible before any
candidate-store promotion or model training.

# Acceptance Criteria

- [x] `/api/state` includes a compact `d1_labeling_review_packet` summary.
- [x] `/api/v1/d1-labeling-review-packet/latest` returns the latest compact
      review packet.
- [x] Dashboard renders a `D1 Labeling Review Packet` panel with pending
      decisions and non-training gates.
- [x] The VPS deploy helper has an explicit review-summary switch that copies
      only `d1_labeling_review_packet.json/.md`.
- [x] Field kit post-run sync includes the review-summary switch.
- [x] Focused tests protect privacy, private-review-field, and non-training
      boundaries.

# Validation Commands

```powershell
python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server quality_tests.test_d1_field_kit -v
python -m py_compile server\message_hub.py scripts\prepare_d1_field_kit.py
python scripts/context_lint.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `server/message_hub.py`,
  `scripts/deploy_message_hub_vps.ps1`, `scripts/prepare_d1_field_kit.py`,
  focused dashboard/server endpoint/field-kit tests,
  `docs/development/DATA_FLYWHEEL_PIPELINE.md`, `docs/current/STATUS.md`,
  generated progress-board files, and this packet.
- Validation:
  - `python -m unittest quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_server quality_tests.test_d1_field_kit -v`
    passed, 68 tests.
  - `python -m py_compile server\message_hub.py scripts\prepare_d1_field_kit.py`
    passed.
  - `python scripts/context_lint.py` passed.
  - `git diff --check` passed with a line-ending warning only for
    `scripts/deploy_message_hub_vps.ps1`.
  - `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` passed, 484
    tests.
- Remaining risks: this is visibility only. Human labeling UI, applying review
  decisions to candidate-store records, training-server integration, model
  training, footprint/power measurement, and on-device deployment remain
  future work.

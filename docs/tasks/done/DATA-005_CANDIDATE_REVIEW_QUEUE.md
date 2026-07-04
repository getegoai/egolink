---
id: DATA-005
title: Candidate review queue
status: done
priority: high
requires_hardware: false
serves_demo: D5
created: 2026-07-04
last_updated: 2026-07-04

context:
  - docs/product/NORTH_STAR.md
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/tasks/done/DATA-003_TRAINING_CANDIDATE_STORE_BASELINE.md
  - docs/tasks/done/DATA-004_DATA_FLYWHEEL_CONTROL_PLANE.md

allowed_paths:
  - pc_simulator/training_candidate_store.py
  - scripts/review_training_candidates.py
  - scripts/summarize_data_flywheel.py
  - server/message_hub.py
  - quality_tests/test_training_candidate_store.py
  - quality_tests/test_message_hub_dashboard.py
  - docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md
  - docs/current/ROADMAP_EGOLINK_P0.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/current/STATUS.md
  - docs/tasks/done/DATA-005_CANDIDATE_REVIEW_QUEUE.md
  - docs/generated/

out_of_scope:
  - training a model
  - exporting a dataset manifest to a training server
  - changing firmware, public contracts, or Message Hub ingest
  - copying raw private payloads, candidate DBs, or runtime JSONL logs into committed artifacts
  - deploying on-device inference or claiming model accuracy/power impact
---

# Goal

Serve D5: add the first bounded review loop for training-candidate records, so
candidate samples can be listed, approved, rejected, or returned for more work
without exposing raw records or enabling training before privacy, consent,
quality, label, and split checks pass.

# Acceptance Criteria

- [x] Candidate records can be listed as a bounded review queue.
- [x] A conservative review action can promote an eligible record to
      `reviewed_training_candidate` and set `training_allowed=true`.
- [x] Rejection and needs-changes actions never enable training.
- [x] Data-flywheel status reports include bounded review-queue visibility.
- [x] Focused tests and repository validation pass.

# Validation Commands

```powershell
python -m unittest quality_tests.test_training_candidate_store quality_tests.test_message_hub_dashboard -v
python scripts/context_lint.py
python -m py_compile pc_simulator\training_candidate_store.py scripts\review_training_candidates.py scripts\summarize_data_flywheel.py server\message_hub.py
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

# Completion Evidence

- Changed files: `pc_simulator/training_candidate_store.py`,
  `scripts/review_training_candidates.py`, `server/message_hub.py`,
  `quality_tests/test_training_candidate_store.py`,
  `quality_tests/test_message_hub_dashboard.py`,
  `docs/modeling/ON_DEVICE_AI_DATA_FLYWHEEL_ROADMAP.md`,
  `docs/current/ROADMAP_EGOLINK_P0.md`, `docs/roadmap/V1_PRODUCT_PLAN.md`,
  `docs/current/STATUS.md`, generated progress board files, and this packet.
- Validation: focused candidate-store/dashboard tests passed (24 tests);
  `python scripts/context_lint.py` passed; `python -m py_compile
  pc_simulator\training_candidate_store.py scripts\review_training_candidates.py
  scripts\summarize_data_flywheel.py server\message_hub.py` passed; `git diff
  --check` passed; full `scripts\verify.ps1` passed (406 tests).
- Deployment: `scripts/deploy_message_hub_vps.ps1 -Public
  -IncludeFieldReportSummaries -IncludeDataFlywheelSummaries` deployed the
  updated Message Hub/Web code and curated DATA-005 status summary to
  `203.0.113.10:8790`, restarted `egolink-message-hub.service`, and did not
  modify GitLab.
- Smoke evidence: `/health` returned `ok=true`; unauthenticated `/api/state`
  returned `401`; Dashboard HTML contained `Review Queue`, `review_queue`,
  `sample_records`, and `available_actions`; authenticated `/api/state` returned
  `run_id=data005-review-queue-status-20260704`, `status=needs_capture`,
  `pipeline_stage=candidate_store_missing`, `review_queue.pending_records=0`,
  and actions `approve_for_training,reject,needs_changes`.
- Remaining risks: the default local candidate-store DB is still missing until
  reviewed session recordings are ingested; DATA-005 does not export dataset
  manifests, connect a training server, train/evaluate/deploy a model, or claim
  model accuracy, false-positive rate, latency, RAM/flash footprint, or power
  impact.

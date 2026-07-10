---
id: STAB-001A
title: Short Baseline Gate Tooling
status: completed
created_at: 2026-06-28
completed_at: 2026-06-28
---

# STAB-001A Short Baseline Gate Tooling

## Goal

Prepare the short USB-Free baseline gate so the next physical run can fail in
an explainable way from VPS/Web evidence.

## Context

- `docs/CONTEXT_INDEX.md`
- `docs/development/DEV_FLOW.md`
- `docs/development/FIELD_TEST.md`
- `docs/development/PROTOCOL.md`
- `docs/development/LOCATION_ENGINE.md`
- `docs/tasks/done/OBS-001_UNIFIED_OBSERVABILITY_ENVELOPE_BASELINE.md`
- `docs/tasks/done/LOC-002_LOCATION_OBSERVATION_CONTRACT_BASELINE.md`
- `scripts/validate_message_hub_stability.py`
- `pc_simulator/message_hub_client.py`

## Allowed Paths

- `scripts/validate_message_hub_stability.py`
- `pc_simulator/message_hub_client.py`
- `quality_tests/test_message_hub_stability_validation.py`
- `quality_tests/test_message_hub_client.py`
- `docs/development/FIELD_TEST.md`
- `docs/current/STATUS.md`
- `docs/tasks/TASK_TREE.md`
- `docs/tasks/done/STAB-001A_SHORT_BASELINE_GATE_TOOLING.md`

## Out Of Scope

- Firmware changes or flashing.
- Serial capture.
- Enqueuing hardware commands from the stability observer.
- Physical USB-Free stability acceptance.
- Long stability testing.
- LTE data transport validation.

## Implementation

- PC Simulator can now bind heartbeat, `location_report`,
  `location_observation`, command ACK, and test-run export evidence to a
  shared `test_run_id`.
- The stability observer now summarizes `location_observation`,
  `location_belief`, reason codes, command ACK state, and test-run export
  availability.
- The observer has optional strict gate flags for STAB-001A:
  `--min-location-observations`, `--require-observability`,
  `--require-location-belief`, `--require-command-ack`, and
  `--require-test-run-export`.
- By default, the observer remains passive and does not enqueue downlink
  commands.

## Validation

- `python -m unittest quality_tests.test_message_hub_client quality_tests.test_message_hub_stability_validation -v`:
  PASS, 5 tests.

## Remaining Risks

- This completes gate tooling only.
- A real STAB-001 pass still requires operator-confirmed independent power and
  USB disconnected for the whole observation.
- LTE transport remains LTE-001/LTE-002/LTE-003.

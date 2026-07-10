---
id: LOC-002
title: Location Observation Contract Baseline
status: completed
created_at: 2026-06-28
completed_at: 2026-06-28
---

# LOC-002 Location Observation Contract Baseline

## Goal

Add a multi-source `location_observation` event to the P0 Message Hub path
without replacing the existing `request_location -> location_report -> ACK`
loop.

## Context

- `docs/CONTEXT_INDEX.md`
- `docs/product/PRODUCT_CHARTER.md`
- `docs/product/P0_SCOPE.md`
- `docs/development/DEV_FLOW.md`
- `docs/development/PROTOCOL.md`
- `docs/development/LOCATION_ENGINE.md`
- `docs/current/ROADMAP_EGOLINK_P0.md`
- `shared/contracts/message_hub_event.schema.json`
- `server/message_hub.py`
- `pc_simulator/message_hub_client.py`

## Allowed Paths

- `server/message_hub.py`
- `pc_simulator/message_hub_client.py`
- `shared/contracts/message_hub_event.schema.json`
- `shared/contracts/README.md`
- `quality_tests/test_message_hub_server.py`
- `quality_tests/test_message_hub_dashboard.py`
- `quality_tests/test_message_hub_client.py`
- `quality_tests/test_message_hub_contracts.py`
- `docs/development/PROTOCOL.md`
- `docs/development/LOCATION_ENGINE.md`
- `docs/current/STATUS.md`
- `docs/tasks/TASK_TREE.md`
- `docs/tasks/done/LOC-002_LOCATION_OBSERVATION_CONTRACT_BASELINE.md`

## Out Of Scope

- Firmware changes or flashing.
- Real SIM7670G LTE data transport.
- Real firmware-side cell fingerprint collection.
- Real Wi-Fi scanning or raw BSSID upload.
- Real IMU fusion.
- Battery accuracy or power behavior.
- VPS location-memory tables.
- Rule-based or learned belief engine.

## Implementation

- `event_type=location_observation` is documented under the existing
  `egolink.p0.v1` event envelope.
- `message_hub_event.schema.json` now lists optional `wifi`, `imu`, and
  `location_belief` fields in addition to the existing OBS groups.
- PC Simulator uploads a mock `location_observation` with GNSS, cell, Wi-Fi
  hashed AP identifiers, IMU, power, and `location_belief`.
- Message Hub treats either `location_report` or `location_observation` as
  latest location evidence.
- `/api/state` exposes `latest_location_observation` and derives
  `observability.location_belief`.
- Dashboard renders location state, belief confidence/radius/source/reason,
  Wi-Fi AP count, and IMU motion.

## Deployment Evidence

- The updated Message Hub was redeployed to the operator VPS as
  `egolink-message-hub.service`.
- PC Simulator public smoke device `ego-link-r0-loc002-smoke` uploaded both
  `location_report` and `location_observation`.
- Authenticated `/api/state` showed:
  - `latest_location_event=location_observation`;
  - `latest_observation_event=location_observation`;
  - `belief_state=Fine`;
  - `belief_reason=gnss_fix_hdop_good`;
  - Wi-Fi AP count and IMU motion present in `observability`.
- The smoke output did not print bearer tokens or exact coordinates.
- Existing GitLab on the VPS was not modified.

## Validation

- `python -m unittest quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_client quality_tests.test_message_hub_contracts -v`:
  PASS, 18 tests.
- `python scripts/context_lint.py`: PASS.
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS,
  239 tests.

## Remaining Risks

- LOC-002 is a contract/server/simulator baseline only.
- Firmware-side multi-source observation remains future work.
- Location memory and rule-based belief generation remain LOC-003/LOC-004.
- LTE transport remains LTE-001/LTE-002/LTE-003.

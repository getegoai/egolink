---
id: REL-010
title: KR-007 Reconnect Store-Forward Evidence Release Gate
status: completed
priority: high
requires_hardware: false
created: 2026-07-02
last_updated: 2026-07-02
completed: 2026-07-02

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-007_RECONNECT_STORE_FORWARD_EVIDENCE.json
  - docs/development/DEV_FLOW.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-010_RECONNECT_STORE_FORWARD_GATE_BASELINE.md
  - docs/tasks/done/LTE-011_RECONNECT_STORE_FORWARD_EVIDENCE_TEST_MODE.md
  - docs/tasks/done/LTE-011_FIX1_OBSERVATION_PAYLOAD_MARGIN.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-007_RECONNECT_STORE_FORWARD_EVIDENCE.json
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-010_KR007_RECONNECT_STORE_FORWARD_EVIDENCE_RELEASE_GATE.md

out_of_scope:
  - firmware changes or flashing
  - sending hardware control commands
  - changing live device wire protocol or raw-frame profile
  - promoting KR-007 from release_candidate to released
  - changing Message Hub runtime behavior
  - training or shipping a learned model
  - claiming real modem reconnect recovery, durable store-forward, queue
    replay, long LTE stability, GNSS acceptance, battery/power behavior,
    enclosure behavior, product readiness, or product positioning accuracy
  - modifying GitLab or unrelated VPS services
---

# REL-010 KR-007 Reconnect Store-Forward Evidence Release Gate

## Goal

Create the KR-007 release-candidate gate for the LTE-011 fix1
reconnect/store-forward evidence baseline:

```text
LTE-011 fix1 USB-Free runtime export
-> LTE-010 reconnect/store-forward offline gate PASS
-> KR-007 manifest and evidence-first release gate
```

## Acceptance

- [x] KR-007 manifest exists under `docs/current/key_releases/`.
- [x] Manifest binds LTE-011 fix1 firmware, flash, USB-Free runtime, and
      LTE-010 gate reports.
- [x] Manifest checks command `cmd-000033`, raw LTE `location_report`, raw LTE
      `location_observation`, raw LTE ACK, reconnect evidence, failure reason,
      store-forward queue evidence, post-reconnect ready state, and LTE-010
      gate PASS.
- [x] KR-007 gate report is generated under `reports/key_releases/KR-007/`.

## Evidence

- Manifest:
  `docs/current/key_releases/KR-007_RECONNECT_STORE_FORWARD_EVIDENCE.json`.
- Runtime evidence:
  `reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/`.
- LTE-010 gate evidence:
  `reports/lte_reconnect_store_forward/lte011-fix1-20260702-001/`.
- KR-007 gate report:
  `reports/key_releases/KR-007/release_gate_report.json` and
  `reports/key_releases/KR-007/release_gate_report.md`.

## Validation

- `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-007_RECONNECT_STORE_FORWARD_EVIDENCE.json --json`:
  PASS, 6 gates, 20 JSON checks, 0 errors, 0 warnings.
- `python -m unittest quality_tests.test_key_release_gate -v`:
  PASS, 7 tests.

## Boundary

KR-007 is a release candidate only. It freezes evidence that the current
test-mode reconnect/store-forward field shape can pass a targeted gate. It
does not prove real modem reconnect recovery, durable local storage, queue
replay, long LTE stability, GNSS acceptance, battery/power behavior, enclosure
behavior, learned model behavior, product positioning accuracy, or product
readiness.

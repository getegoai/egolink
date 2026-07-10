---
id: REL-006
title: KR-005 Reliability Explainability Release Gate
status: completed
priority: high
requires_hardware: false
created: 2026-07-01
last_updated: 2026-07-01

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DEV_FLOW.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-005_LTE_RELIABILITY_GATE_BASELINE.md
  - docs/tasks/done/OBS-004_RELIABILITY_OBSERVABILITY_BASELINE.md
  - docs/tasks/done/LTE-006_FIRMWARE_SIDE_RELIABILITY_NONCLAIM_OBSERVABILITY.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-005_RELIABILITY_EXPLAINABILITY_PREFLIGHT.json
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-006_KR005_RELIABILITY_EXPLAINABILITY_RELEASE_GATE.md
  - quality_tests/test_key_release_gate.py

out_of_scope:
  - flashing firmware
  - running USB-Free hardware validation
  - VPS deployment or GitLab changes
  - changing firmware, protocol fields, raw-frame framing, or Message Hub runtime behavior
  - claiming reconnect recovery, cache durability, long LTE stability,
    battery/power behavior, enclosure behavior, GNSS acceptance, or product readiness
---

# REL-006 KR-005 Reliability Explainability Release Gate

## Goal

Create the KR-005 release-candidate gate for the reliability explainability
preflight path:

```text
LTE-005 offline reliability gate
-> OBS-004 reliability.network/cache visibility
-> LTE-006 firmware-side network state + cache non-claim fields
-> KR-005 release-candidate manifest
```

KR-005 freezes an explainable preflight state, not a runtime reliability
acceptance. It exists so the next hardware run can be judged against a stable
gate instead of a moving target.

## Acceptance

- [x] Add a machine-readable KR-005 manifest under
      `docs/current/key_releases/`.
- [x] Bind KR-005 to LTE-005, OBS-004, and LTE-006 evidence.
- [x] Keep LTE-006 USB-Free runtime as `NOT_RUN` until explicit operator
      hardware confirmation.
- [x] Check the existing LTE-005 smoke report remains expected `WARN` and does
      not contain concrete cache/drop-message evidence.
- [x] Preserve all non-claims around cache durability, reconnect recovery, long
      LTE stability, and product readiness.
- [x] Add unit coverage for release-candidate `NOT_RUN` gate warnings.

## Evidence

- Manifest:
  `docs/current/key_releases/KR-005_RELIABILITY_EXPLAINABILITY_PREFLIGHT.json`.
- Local LTE-005 smoke report:
  `reports/lte_reliability/loc005a-source-states-20260630-001-lte006-smoke/lte_reliability_gate_report.json`.
- LTE-006 build evidence:
  `firmware/mqtt_heartbeat/build_lte006_reliability_nonclaim/egolink_mqtt_heartbeat.bin`.
- KR-005 gate report:
  `reports/key_releases/KR-005/release_gate_report.json` and
  `reports/key_releases/KR-005/release_gate_report.md`.

## Validation

- `python -m unittest quality_tests.test_key_release_gate quality_tests.test_lte_reliability_gate quality_tests.test_mqtt_heartbeat_firmware -v`:
  PASS, 25 tests.
- `python scripts/context_lint.py`: PASS.
- `python scripts\validate_lte_reliability_gate.py --input reports\field_validation\loc005a-source-states-20260630-001\test_run_export.json --output-dir reports\lte_reliability\loc005a-source-states-20260630-001-lte006-smoke --json`
  returned expected `WARN`.
- `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-005_RELIABILITY_EXPLAINABILITY_PREFLIGHT.json --json`:
  PASS with expected warning `gate G5-LTE006-USB-FREE-RUNTIME is NOT_RUN`.
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`: PASS,
  314 tests.
- `git diff --check`: PASS.

## Completion Boundary

REL-006 is a release-candidate gate only. It does not flash firmware, validate
LTE-006 on USB-Free hardware, deploy to the VPS, implement durable cache,
prove reconnect recovery, prove long LTE stability, prove battery/power
behavior, or make any product-readiness claim.

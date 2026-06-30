---
id: REL-001
title: First Key Release Gate
status: completed
priority: high
requires_hardware: false
created: 2026-06-30
last_updated: 2026-06-30

context:
  - docs/CONTEXT_INDEX.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/KEY_RELEASES.md
  - docs/development/DEV_FLOW.md
  - docs/tasks/done/LTE-004_RAW_LTE_REQUEST_LOCATION_THIN_SLICE.md

allowed_paths:
  - docs/CONTEXT_INDEX.md
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-001_USB_FREE_RAW_LTE_LOCATION.json
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-001_FIRST_KEY_RELEASE_GATE.md
  - docs/tasks/done/LTE-004_RAW_LTE_REQUEST_LOCATION_THIN_SLICE.md
  - scripts/run_key_release_gate.py
  - quality_tests/test_key_release_gate.py

out_of_scope:
  - new hardware flashing or runtime validation
  - long LTE stability testing
  - product readiness claims
  - modifying GitLab or unrelated VPS services
---

# REL-001 First Key Release Gate

## Goal

Publish the first Ego Link P0 engineering key release without turning the next
step into repeated ad hoc field testing. The release mechanism is a versioned
manifest plus a reusable release gate.

## Result

Completed. KR-001 is recorded as `P0 USB-Free Raw LTE Location Walking
Skeleton`, release version `0.1.0-key-release-001`.

## Evidence

- Release index: `docs/current/KEY_RELEASES.md`.
- Release manifest:
  `docs/current/key_releases/KR-001_USB_FREE_RAW_LTE_LOCATION.json`.
- Gate script: `scripts/run_key_release_gate.py`.
- Gate report:
  `reports/key_releases/KR-001/release_gate_report.json` and
  `reports/key_releases/KR-001/release_gate_report.md`.
- LTE-004 task packet archived at
  `docs/tasks/done/LTE-004_RAW_LTE_REQUEST_LOCATION_THIN_SLICE.md`.

## Validation

- `python -m unittest quality_tests.test_key_release_gate -v`
- `python scripts\run_key_release_gate.py --manifest docs/current/key_releases/KR-001_USB_FREE_RAW_LTE_LOCATION.json --json`
- `python scripts\context_lint.py`
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`
- `git diff --check`

## Boundary

KR-001 is an engineering key release. It proves the first USB-Free raw LTE
`request_location -> location_report -> ACK` backbone. It does not prove real
GNSS fix, long LTE stability, reconnect recovery, battery/power behavior,
enclosure behavior, or product readiness.

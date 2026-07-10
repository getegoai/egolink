---
id: REL-011
title: KR-007 Reconnect Store-Forward Evidence Release
status: completed
priority: high
requires_hardware: false
created: 2026-07-02
last_updated: 2026-07-02
completed: 2026-07-02

context:
  - docs/CONTEXT_INDEX.md
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/ACTIVE_BUILD.md
  - docs/current/key_releases/KR-007_RECONNECT_STORE_FORWARD_EVIDENCE.json
  - docs/development/DEV_FLOW.md
  - docs/development/LTE_TRANSPORT.md
  - docs/tasks/done/LTE-010_RECONNECT_STORE_FORWARD_GATE_BASELINE.md
  - docs/tasks/done/LTE-011_RECONNECT_STORE_FORWARD_EVIDENCE_TEST_MODE.md
  - docs/tasks/done/LTE-011_FIX1_OBSERVATION_PAYLOAD_MARGIN.md
  - docs/tasks/done/REL-010_KR007_RECONNECT_STORE_FORWARD_EVIDENCE_RELEASE_GATE.md

allowed_paths:
  - docs/current/STATUS.md
  - docs/current/KEY_RELEASES.md
  - docs/current/key_releases/KR-007_RECONNECT_STORE_FORWARD_EVIDENCE.json
  - docs/tasks/TASK_TREE.md
  - docs/tasks/done/REL-011_KR007_RECONNECT_STORE_FORWARD_EVIDENCE_RELEASE.md

out_of_scope:
  - firmware changes or flashing
  - sending hardware control commands
  - VPS deployment or GitLab changes
  - changing live device wire protocol or raw-frame profile
  - changing Message Hub runtime behavior
  - training or shipping a learned model
  - claiming real modem reconnect recovery, durable store-forward, queue
    replay, long LTE stability, GNSS acceptance, battery/power behavior,
    enclosure behavior, product readiness, or product positioning accuracy
---

# REL-011 KR-007 Reconnect Store-Forward Evidence Release

## Goal

Promote KR-007 from release candidate to released engineering key version after
the release-candidate gate passed with the LTE-011 fix1 runtime evidence and
LTE-010 offline reconnect/store-forward gate report.

## Acceptance

- [x] KR-007 manifest status is `released`.
- [x] KR-007 release version is `0.1.0-key-release-007`.
- [x] Release index records KR-007 as released engineering key version.
- [x] KR-007 gate passes after promotion.
- [x] Non-claims remain explicit.

## Evidence

- Candidate gate task:
  `docs/tasks/done/REL-010_KR007_RECONNECT_STORE_FORWARD_EVIDENCE_RELEASE_GATE.md`.
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
  PASS, status `released`, version `0.1.0-key-release-007`, 6 gates, 20 JSON
  checks, 0 errors, 0 warnings.
- `python -m unittest quality_tests.test_key_release_gate -v`: PASS, 7 tests.
- `python scripts\context_lint.py`: PASS.
- `git diff --check`: PASS.

## Boundary

KR-007 is a released engineering key version for a test-mode
reconnect/store-forward evidence baseline. It does not prove real modem
reconnect recovery, durable local storage, queue replay, long LTE stability,
GNSS acceptance, battery/power behavior, enclosure behavior, learned model
behavior, product positioning accuracy, or product readiness.

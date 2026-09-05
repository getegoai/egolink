---
id: CALL-001
title: Freeze Ego Call minimum architecture and PC loop
status: accepted_for_transition
priority: critical
lane: B
execution_state: completed
requires_hardware: false
created: 2026-08-23
last_updated: 2026-08-23

context:
  - docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/product/EGO_MASTER_CONTEXT.md

allowed_paths:
  - docs/tasks/active/CALL-001_EGO_CALL_ARCHITECTURE_AND_PC_LOOP.md
  - docs/development/EGO_CALL.md
  - shared/contracts/README.md
  - shared/contracts/ego_call_session.schema.json
  - pc_simulator/ego_call.py
  - pc_simulator/ego_call_demo.py
  - quality_tests/test_ego_call_contract.py
  - quality_tests/test_ego_call_fixture.py

out_of_scope:
  - selecting a production RTC vendor without measured evidence
  - building a public PSTN/SIP gateway
  - claiming product audio, mobile-app, weak-network, or hardware acceptance
---

# Goal

Define and demonstrate the smallest authenticated, replayable Ego Call loop on
PC/browser infrastructure, including its SOS/location context boundary.

# Serves

First-launch Ego Call and SOS; runs in parallel with the L1 Location priority.

# Acceptance Criteria

- [x] Architecture documents media/signaling, identity/authorization, call
      states, retries, retention, privacy, NAT/relay assumptions, operating
      dependencies, and vendor decision criteria.
- [x] A machine-readable call-session contract validates allowed state
      transitions and carries location-belief references rather than copying
      unrestricted precise-location payloads.
- [x] A bounded PC/browser fixture demonstrates request -> ringing -> connected
      -> ended plus explicit failure/reconnect paths and replayable state.
- [x] SOS composition is deterministic and reports remote delivery/call state
      honestly; AI cannot veto or synthesize success.
- [x] Tests pass without network credentials or external service dependency.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion Evidence

- Changed files: `docs/development/EGO_CALL.md`,
  `shared/contracts/ego_call_session.schema.json`, and
  the bounded PC/browser fixture and its focused tests.
- Test result: schema validity, 13 allowed transitions, invalid
  transition rejection, precise-coordinate/RTC-secret rejection, and recording
  consent behavior pass; authorized/idempotent happy, reconnect, failure, SOS,
  ordering, call-session replay and static browser-artifact paths pass. Focused
  CALL tests `24/24` PASS and full repository tests `821/821` PASS.
- Hardware result: not required for this engineering slice.
- Remaining risks: mobile app, production RTC service, device audio and weak
  network require later measured tasks. The fixture's local SOS trace is
  in-memory and non-contract; durable safety-event persistence/replay must
  reuse the accepted safety contract and ADR-0010 priority outbox.
- Successor: `CALL-010` owns the exact-board audio loop; `CALL-020` owns the
  PC-bridged LTE-data RTC PoC. Neither successor inherits a product PASS from
  this control-loop acceptance.

# Builder Prompt

```text
Read docs/tasks/active/CALL-001_EGO_CALL_ARCHITECTURE_AND_PC_LOOP.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
listed in this packet's context. This is Lane B; do only this task, obey
allowed_paths and out_of_scope. Treat the accepted Ego Call schema as the
single contract owner. Build the smallest deterministic PC/browser fixture for
authorized request -> ringing -> connected -> ended plus failure/reconnect and
replay. Use no production credentials or external RTC dependency; do not build
a PSTN/SIP gateway or claim product audio. Run all validation commands and
return changed files, exact output, evidence paths and remaining risks. Do not
update STATUS or move this packet to done.
```

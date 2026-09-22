---
id: ALIGN-STATE-010
title: Align founder decisions and repair ego-state truth and contracts
status: done
execution_state: done
priority: critical
lane: integration
owner: codex
serves_gate: P0-LOC
requires_hardware: false
created: 2026-09-22
last_updated: 2026-09-22
completed: 2026-09-22
accepted_by: codex_integrator_under_founder_task_authority
context:
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/architecture/SYSTEM_OVERVIEW.md
  - docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/architecture/adr/ADR-0014-runtime-convergence.md
  - docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/development/GIT_FLOW.md
  - docs/roadmap/PROJECT_REVIEW_20260921.md
  - docs/AGENTS.md
  - firmware/AGENTS.md
  - pc_simulator/AGENTS.md
  - quality_tests/AGENTS.md
  - shared/contracts/
allowed_paths:
  - docs/
  - firmware/mqtt_heartbeat/components/ego_state_engine/
  - firmware/mqtt_heartbeat/main/collection_main.c # ego-state packaging only; no acquisition/transport changes
  - pc_simulator/ego_state_estimator.py
  - server/collection_store.py # ego-state validation/projection only
  - server/message_hub.py # ego-state API and truthful progress WIP summary only
  - server/web/ # ego-state presentation only
  - shared/contracts/ # bounded ego-state contract clarification/adaptation
  - quality_tests/
  - scripts/build_progress_board.py
  - scripts/context_lint.py # distinguish required inputs from ignored generated outputs
out_of_scope:
  - recovery, network switching, D2 acquisition and FIELD-020 implementation owned by Gemini
  - pin assignments, modem/camera/transport behavior, sampling policy and firmware profiles
  - new cellular call behavior, Ego Base deployment, advanced learned models
  - flashing, hardware control, network deployment, data migration or deletion
  - claiming hardware or product Gate completion from offline changes
---

# Goal and authority

The founder on 2026-09-22 assigned Codex decision/current-image/backlog alignment,
state truth/contract repairs, project management and Git commits, while assigning
single-board recovery/network switching and D2/FIELD-020 to Gemini. This packet
explicitly permits the bounded firmware rule/model and ego-state contract fixes
identified in the 2026-09-21 review; the integrator owns contract review.

# Acceptance

- [x] Record the 9/19 decision migration in a successor ADR and synchronize current product/execution authorities without inventing hardware evidence.
- [x] Separate the last reported running image from new unflashed source; reconcile stale current/next-work statements and assign Gemini's work explicitly.
- [x] Missing, stale, future or invalid sensor evidence cannot produce a confident normal state; retain source timing/mock lineage and deterministic recovery semantics.
- [x] DEVICE ingestion, canonical estimation, API view and Web use explicit compatible contracts/enums; invalid state cannot silently receive a valid projection.
- [x] Regression covers missing/stale/partial/mock data, replay/order/boot identity, invalid payloads and real Web rendering logic; privacy/encryption labels describe actual behavior.
- [x] WIP, parked/paused/acceptance-wait and completed tasks are distinguishable; regenerate the derived board; preserve unaccepted hardware tasks.
- [x] Full verify, context lint and diff checks pass; changes are committed in reviewable units with no unrelated Gemini work.

# Validation

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
python scripts/build_progress_board.py
git diff --check
```

Run focused ego-state tests during implementation and an available no-flash
build/compiler check. No new hardware evidence is expected from this task.

# Completion evidence

- Core source commit: `3a0728058` (`fix(state): preserve evidence truth across firmware, API and Web [D2]`).
- This done packet and the reconciled project state are recorded together by the following management commit; use `git log --follow` on this packet for its exact commit.
- Frozen `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: 1,867 tests in 300.883 s, 1,860 passed, 7 environment/opt-in skips, exit 0. Host compiler used `CC=D:/pywork/egolink/tmp/native_tools/w64devkit/bin/gcc.exe` and its directory on PATH. Local log: `D:/pywork/egolink-codex-state-20260922/tmp/align-state-verify-release.log`.
- Context lint, diff checks, no-flash ESP-IDF camera/collection build and 27 source-snapshot SHA-256 checks passed. Source and artifact hashes, exact scope, skipped checks and intermediate failures are documented in [the verification record](../../verification/ALIGN_STATE_010_20260922.md) and [build manifest](../../verification/ALIGN_STATE_010_OFFLINE_BUILD.json).
- Changed areas: accepted ADR/current product and specialist routing; short current image/state/capability records; task owners/states/dependencies and generated board; C/Python estimator; DEVICE packaging; strict API projection and Web; versioned view schema and truthful contract descriptions; scoped regression and portable/isolated test harnesses; WIP summary and ignored-output-aware context lint.
- Source completion is not deployment. The last reported running image remains Boot188 and P0-LOC/P0-CALL/P0-SOS remain NOT_RUN. No hardware control, flash, private-data migration/deletion, deployment or remote push was performed.
- Remaining risks: uncalibrated rule scores; independent DEVICE-frame budget must enter the next field profile; legacy all-source-loss health frames still overflow 4,000 bytes; source/image binding and hardware recovery/network/D2/FIELD remain Gemini's work. Base privacy lifecycle, native-call/audio/SOS and product assurance remain queued/unverified. See [the handoff](../../current/CODEX_GEMINI_HANDOFF_20260922.md).
- Decision conflicts identified in the 9/21 review are explicitly resolved by accepted ADR-0016 with source snapshots and clause migration maps. No unresolved authority conflict remains in this task's reviewed current documents; retained hardware unknowns are not decisions or passes.

# Builder / follow-up boundary

This packet is closed as offline source and project alignment. Future hardware,
transport/recovery, native-call or Base work belongs in its named consumer packet.
Read its context and amend its concrete dispatch scope before implementation;
do not inherit new I/O or deployment authority from this closed task.

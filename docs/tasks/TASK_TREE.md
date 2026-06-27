---
document_status: current_task_tree
generated_at: 2026-06-27
generated_by: codex
---

# EGOLINK Task Tree

This tree records the current task structure from the local repository state.
It does not move, delete, or rewrite task packets.

## Root Objective

EGOLINK P0 proves an AI-assisted active safety locator loop:

```text
motion candidate
-> PC Bridge receives event
-> AMOLED asks the user
-> user confirmation
-> location / communication evidence
-> complete safety event record
-> quality gate
-> replay without boards
```

## Control Plane

- `ENG-000 Repository context migration`
  - Status: completed as a local control-plane migration baseline.
  - Evidence: authoritative files are split into `docs/current/`,
    `docs/product/`, `docs/architecture/`, `docs/hardware/`, `docs/modeling/`,
    `docs/safety/`, module `AGENTS.md` files, and `scripts/context_lint.py`.
- `ENG-001 Control Plane Baseline`
  - Status: completed.
  - Evidence: `docs/current/PROJECT_SNAPSHOT.md`,
    `docs/tasks/TASK_TREE.md`, `docs/development/`, and
    `reports/dev_runs/ENG-001-control-plane-baseline.md`.
- `ENG-002 Control Plane Commit / Remote Policy`
  - Status: completed on local branch `task/ENG-002-control-plane-commit`.
  - Evidence: commits `12c79c0`, `a9270eb`, and `2194e58`.
  - Remote: none configured; no push performed.
- `ENG-003 Legacy Archive Review`
  - Status: completed on local branch `task/ENG-003-legacy-archive-review`.
  - Evidence: legacy documents were preserved under `docs/archive/` or exact
    current destinations before old paths were removed or redirected.
- `ENG-004 Generated Docs Review`
  - Status: completed on local branch
    `task/ENG-004-DEMO-005-generated-docs-gnss`.
  - Evidence: `docs/generated/CONTEXT_MIGRATION_REPORT.md` and
    `docs/generated/REPOSITORY_MAP.md` are versioned as generated,
    non-authoritative migration evidence.

## Active Queue

No task packet with `status: active` is currently present under
`docs/tasks/active/`. The directory is intentionally kept with `.gitkeep`.

## Demo-First Product Loop

- `DEMO-001 AMOLED IMU Confirmation Loop`
  - Path: `docs/tasks/done/DEMO-001_AMOLED_IMU_CONFIRMATION_LOOP.md`
  - Status: completed.
  - Result: real AMOLED/QMI8658 motion event, ask_user render, touch
    confirmation, PC safety event record.
- `DEMO-004 Full Demo Orchestrator`
  - Path: `docs/tasks/done/DEMO-004_FULL_DEMO_ORCHESTRATOR.md`
  - Status: completed.
  - Result: full Demo v0.5 runner with AMOLED evidence, SIM7670G GNSS/AT
    evidence, mock-only audio, recording, quality gate, and replay.
- `DEMO-005 Real GNSS Fix Evidence`
  - Status: deferred.
  - Goal: capture bounded real `fix=true` SIM7670G GNSS evidence and replay it
    through the full demo.
  - Current blocker: the SIM7670G board must stay connected to the PC USB AT
    port for the current probe path, but the host PC is too far from a window
    or outdoor sky view for a practical fix attempt with the available USB
    cable.
  - Latest bounded attempt: SIM7670G AT was reachable on `COM6`, GNSS power was
    on, and a `location_report fix=false` event was written; no real fix was
    claimed.
- `DEMO-006 Real Audio Chain Bring-Up`
  - Status: proposed.
  - Goal: replace mock-only audio evidence with accepted microphone evidence
    while preserving privacy gates.
- `DEMO-007 Stability / Reconnect / Long-Run Demo Gate`
  - Status: proposed.
  - Goal: repeat full demo under bounded reconnect/retry/longer capture windows.

## Hardware Evidence Line

- `TIMU-009C-B2 QMI8658 Labeled Fixture Repeatability Capture`
  - Path: `docs/tasks/done/TIMU-009C-B2_QMI8658_LABELED_FIXTURE_REPEATABILITY_CAPTURE.md`
  - Status: done.
  - Boundary: temporary fixture evidence only; formal IMU acceptance remains
    false.
- `TIMU-009C-B3 Equivalent Calibration Pose Set Or FIFO/DRDY Preflight`
  - Status: suggested by prior task record.
  - Goal: add labeled fixture pose evidence or interrupt-path evidence.
- Camera smoke evidence
  - Status: completed in history and status docs.
  - Boundary: not yet product camera path.
- SIM7670G GNSS / 4G evidence
  - Status: AT/GNSS no-fix evidence exists.
  - Needed: real fix and product-side control path remain separate tasks.
- Audio / microphone evidence
  - Status: mock-only in full demo.
  - Needed: real microphone path and privacy-preserving acceptance gate.

## Data, Quality, And Replay

- Session recording
  - Status: implemented.
  - Current role: converts event logs into structured recording directories.
- Quality gate
  - Status: implemented.
  - Current role: file integrity, source boundary, privacy, and schema checks.
- Replay
  - Status: implemented.
  - Current role: rebuilds model inputs and verifies deterministic Safety
    Companion behavior from recordings.
- Annotation CLI
  - Status: implemented.
  - Current role: can attach labels to recording targets.

## Architecture And Contracts

- P0 product scope
  - Authority: `docs/product/PRODUCT_CHARTER.md`,
    `docs/product/P0_SCOPE.md`.
- Current system topology
  - Authority: `docs/architecture/SYSTEM_OVERVIEW.md`,
    `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md`.
- Protocol and model contracts
  - Authority: `shared/contracts/`.
- ADR process
  - Authority: `docs/architecture/adr/README.md`.
  - Current state: only README/template observed in ADR directory.

## Current Recommended Execution Order

1. Resume `DEMO-005 Real GNSS Fix Evidence` only when the SIM7670G board can
   remain USB-connected while placed near a window or outdoors, or after a
   product-side message path can trigger GNSS without moving the host PC.
2. Proceed with a non-location-blocked task such as `DEMO-006 Real Audio Chain
   Bring-Up`, `DEMO-007 Stability / Reconnect / Long-Run Demo Gate`, or the
   product-side `request_location -> connectivity_node -> GNSS` message path.
3. Run remote bootstrap only after the operator provides a remote URL and
   desired protected branch policy.

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
  - Status: partially applied, uncommitted.
  - Evidence: authoritative files such as `docs/CONTEXT_INDEX.md`,
    `docs/current/`, `docs/product/`, and module `AGENTS.md` files are
    currently untracked.
  - Next: decide commit/revert/split policy.
- `ENG-001 GitHub Flow baseline`
  - Status: in progress in this control-plane baseline.
  - Current branch: `autodev/egolink-p0`.
  - Remote: none configured.
  - Next: confirm remote, target branch, task branch naming, and merge rules.
- `ENG-002 Task directory hygiene`
  - Status: proposed follow-up.
  - Current issue: task queue is now empty, but broader backlog and PR/merge
    hygiene still need a clean baseline commit and human branch policy.

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
  - Status: proposed.
  - Goal: capture bounded real `fix=true` SIM7670G GNSS evidence and replay it
    through the full demo.
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

1. Finish ENG-001 control-plane baseline and review the resulting report.
2. Run ENG-002 only if a separate cleanup commit is needed for branch/remote or
   backlog policy.
3. Proceed to DEMO-005 real GNSS fix evidence before new audio work, unless the
   operator explicitly reprioritizes hardware.

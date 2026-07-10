---
id: ENG-005
title: P0 Dev Flow Baseline
status: completed
priority: high
requires_hardware: false
created: 2026-06-27
last_updated: 2026-06-27

context:
  - docs/CONTEXT_INDEX.md
  - docs/AGENTS.md
  - docs/EGO_LINK_P0_DEV_FLOW_FOR_CODEX.md
  - docs/product/P0_SCOPE.md
  - docs/architecture/SYSTEM_OVERVIEW.md

allowed_paths:
  - README.md
  - docs/CONTEXT_INDEX.md
  - docs/EGO_LINK_P0_DEV_FLOW_FOR_CODEX.md
  - docs/architecture/adr/
  - docs/current/
  - docs/development/
  - docs/tasks/

out_of_scope:
  - firmware logic changes
  - pc_simulator behavior changes
  - server or web implementation changes
  - shared contract schema changes
  - hardware flashing or live capture
  - VPS GitLab changes
  - storing real VPS credentials
---

# Problem

P0 development needed to move from ad hoc feature requests to a USB-Free,
VPS Message-First, Demo-Driven, Contract-First Walking Skeleton flow.

The source draft used `ENG-002`, but that task ID already exists in the
repository task tree. This completed task records the implemented baseline as
`ENG-005`.

# Expected Result

Codex and future task packets have a current, routed development baseline:
build a demonstrable device/simulator -> VPS -> Web loop first, then evolve
Firmware, Server-Web, and Protocol tracks by versioned tasks.

# Acceptance Criteria

- [x] Development flow baseline exists under `docs/development/`.
- [x] VPS Message Hub boundary and non-responsibilities are documented.
- [x] P0 message protocol baseline is documented without overwriting existing
      machine-readable model contracts.
- [x] USB-Free field-test evidence rules are documented.
- [x] R0-R4 near-term roadmap is documented.
- [x] Architecture decision is recorded in an ADR.
- [x] Existing `ENG-002` ID conflict is recorded.
- [x] Real VPS credentials are not persisted.

# Validation Commands

```powershell
python scripts/context_lint.py
```

# Hardware Validation

- Board: not applicable.
- Firmware commit or image: not applicable.
- Connection path: not applicable.
- Evidence path: not applicable.

# Completion Evidence

- Changed files:
  - `README.md`
  - `docs/CONTEXT_INDEX.md`
  - `docs/EGO_LINK_P0_DEV_FLOW_FOR_CODEX.md`
  - `docs/architecture/adr/ADR-0001-usb-free-vps-message-hub.md`
  - `docs/current/ROADMAP_EGOLINK_P0.md`
  - `docs/current/STATUS.md`
  - `docs/development/DEV_FLOW.md`
  - `docs/development/FIELD_TEST.md`
  - `docs/development/PROTOCOL.md`
  - `docs/development/VPS_MESSAGE_HUB.md`
  - `docs/tasks/TASK_TREE.md`
  - `docs/tasks/done/ENG-005_P0_DEV_FLOW_BASELINE.md`
- Validation result:
  - `python scripts/context_lint.py`: PASS.
  - `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`: PASS, 196 tests OK.
- Remaining risks:
  - `PROTO-001` must still freeze machine-readable message-hub contracts.
  - `SERVER-001` must still implement the actual VPS service.
  - Actual VPS deployment must protect existing GitLab and use credentials only
    through operator-approved runtime configuration.

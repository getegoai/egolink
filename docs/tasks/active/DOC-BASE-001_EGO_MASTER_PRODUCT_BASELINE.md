---
id: DOC-BASE-001
title: Establish the current Ego product-direction baseline
status: active
priority: high
requires_hardware: false
created: 2026-08-14
last_updated: 2026-08-14

context:
  - AGENTS.md
  - docs/AGENTS.md
  - docs/CONTEXT_INDEX.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/product/MASS_PRODUCTION_FOUNDER_DECISION_SHEET.md
  - docs/product/V1_PRO_FORM_FACTOR_BASELINE.md
  - docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md
  - docs/architecture/adr/ADR-0005-v1-pro-production-hardware-baseline.md
  - docs/architecture/adr/ADR-0006-v1-pro-product-peripheral-revision.md
  - docs/architecture/adr/ADR-0007-gnss-denied-personal-location-memory.md
  - docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md
  - docs/development/LOCATION_ENGINE.md
  - docs/tasks/active/PROD-001_MASS_PRODUCTION_REQUIREMENTS.md
  - docs/tasks/done/LOC-006_GNSS_DENIED_HYBRID_LOCATION_STRATEGY.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/hardware/V1_PRO_EVT_PROCUREMENT_BASELINE.md
  - docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md
  - docs/hardware/README.md
  - docs/current/STATUS.md
  - docs/development/DEV_FLOW.md
  - docs/development/DIRECTOR_WORKFLOW.md

allowed_paths:
  - AGENTS.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/product/MASS_PRODUCTION_REQUIREMENTS.md
  - docs/product/MASS_PRODUCTION_FOUNDER_DECISION_SHEET.md
  - docs/product/V1_PRO_FORM_FACTOR_BASELINE.md
  - docs/architecture/adr/ADR-0005-v1-pro-production-hardware-baseline.md
  - docs/architecture/adr/ADR-0006-v1-pro-product-peripheral-revision.md
  - docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md
  - docs/architecture/adr/ADR-0002-v1-ondevice-ai-companion-core.md
  - docs/architecture/adr/ADR-0007-gnss-denied-personal-location-memory.md
  - docs/development/LOCATION_ENGINE.md
  - docs/tasks/active/PROD-001_MASS_PRODUCTION_REQUIREMENTS.md
  - docs/tasks/done/LOC-006_GNSS_DENIED_HYBRID_LOCATION_STRATEGY.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/hardware/V1_PRO_EVT_PROCUREMENT_BASELINE.md
  - docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md
  - docs/hardware/README.md
  - docs/current/STATUS.md
  - docs/tasks/active/DOC-BASE-001_EGO_MASTER_PRODUCT_BASELINE.md

out_of_scope:
  - firmware, server, Web, model, protocol, schema, or hardware changes
  - flashing, serial access, remote deployment, or external service mutation
  - procurement or freezing a production BOM from unverified candidates
  - importing the untracked v0.2, v0.3, or v0.4 design packs
  - changing current development-board evidence in ACTIVE_BUILD or BOARD_MATRIX
execution_state: acceptance_review
owner: director
reviewed_at: 2026-09-22
---

# Problem

The founder supplied a newer `docs/EGO_MASTER_CONTEXT.md` and directed that it
become the baseline for the current sales-product path. The draft contains the
intended screenless modular EgoCore direction, but it also claims universal
authority, treats several unverified component candidates as an A0 baseline,
copies mutable project status, conflicts with the current privacy boundary,
and silently contradicts accepted V1 Pro decisions.

Promoting it unchanged would leave two mutually exclusive hardware and product
routes marked authoritative. The current ESP32-S3/SIM7670G development path
must continue in parallel and must not inherit unverified product claims.

# Expected Result

- The master context becomes the authoritative current sales-product direction
  and system-product baseline, with explicit limits on its authority.
- A founder-accepted ADR records the screenless modular EgoCore product pivot
  and explicitly supersedes the conflicting V1 Pro product, form-factor, and
  procurement decisions.
- Product requirements are separated from engineering candidates, verified
  development-board facts, machine-readable contracts, and mutable status.
- Candidate modem, MCU, IMU, audio, camera, power, RF, enclosure, and battery
  choices remain candidate or unknown until their named gates pass.
- P0/D2/D5 development continues under its existing scope and evidence
  authorities without firmware or protocol change.
- Raw audio/image persistence and training remain disabled by default, and
  exact location remains restricted evidence.

# Acceptance Criteria

- [x] `docs/product/EGO_MASTER_CONTEXT.md` has authoritative frontmatter, an authority
  boundary, corrected evidence claims, and no missing companion-file claim.
- [x] ADR-0008 records the founder decision and exact supersession boundary.
- [x] `AGENTS.md` and `CONTEXT_INDEX.md` route product-direction work through
  the master while retaining separate physical, P0, protocol, and ADR
  authorities.
- [x] ADR-0005/0006 and the conflicting V1 Pro form/procurement/roadmap text are
  retained as history but cannot control new design or purchasing.
- [x] The master does not claim unverified component capability, durable
  store-forward, product reconnect recovery, current corrected GNSS hardware
  validation, a missing engineering file, or an unsupported v0.5 baseline.
- [x] Current development-board execution is explicitly parallel and unchanged.
- [x] Only the task's allowed paths are changed; user design packs remain
  untracked and uncommitted.
- [x] Context lint, full repository verification, and diff checks pass.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
git status --short
```

# Hardware Validation

- Board: none; documentation/governance task only
- Firmware commit: unchanged
- Connection: none
- Expected output: not applicable
- Evidence path: Git diff and validation output

# Decisions

- The founder's 2026-08-14 instruction accepts the new product direction, not
  every named component as a verified or production-frozen part.
- The baseline governs the current sales-product path. The existing development
  boards remain evidence vehicles and continue their D2/D5/FIELD tasks.
- Accepted product-direction changes are recorded in ADR-0008 instead of
  silently overriding earlier ADRs.
- Untracked design packs are not imported or treated as repository authority.

# Completion Evidence

- Changed files: 23 task-allowed documentation/governance paths. The main
  artifacts are `docs/product/EGO_MASTER_CONTEXT.md`, accepted ADR-0008, the
  ADR-0002 amendment/history record, authority routing, superseded V1 Pro
  authorities, rebased product/production/procurement plans, and synchronized
  active planning/status documents.
- Test result: `python scripts/context_lint.py` PASS;
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1`
  PASS with 654/654 tests; worktree and staged diff checks PASS.
- Hardware result: not applicable
- Scope result: all 23 project changes are covered by `allowed_paths`; the three
  founder-supplied v0.2/v0.3/v0.4 design packs remain untracked and uncommitted.
- Remaining risks: candidate component documentation, schematic/BOM/AVL, RF,
  acoustics, enclosure, endurance, certification, privacy UX, and product
  hardware validation remain open after this governance baseline. Wi-Fi/BLE
  production inclusion, final modem/MCU/IMU/camera/power parts, battery and
  ingress target remain explicitly unfrozen.

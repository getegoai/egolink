---
id: PRIVACY-001
title: Product demo privacy and data boundary gate
status: active
priority: high
requires_hardware: false
created: 2026-07-03
last_updated: 2026-07-03

context:
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/safety/SAFETY_CONTRACT.md
  - shared/contracts/

allowed_paths:
  - docs/product/
  - docs/development/
  - docs/safety/
  - shared/contracts/
  - pc_simulator/
  - scripts/
  - quality_tests/

out_of_scope:
  - collecting real private user data
  - enabling raw audio or raw image retention by default
  - changing model behavior or safety decisions
  - implementing a mobile app or guardian account system
  - changing firmware wire protocol
---

# Problem

Claude's project review correctly calls out a planning gap: privacy controls
exist in several contracts and quality gates, but there is no single product
demo privacy boundary that says what data may be stored, exported, trained on,
or shown during KR-008/V1 field demos.

The current system already treats raw audio/image as disallowed in demos and
uses privacy fields in session recording, DATA-001, and EALE-P0. The missing
piece is a product-facing gate that ties those pieces together before real
family, child, elder, guardian, or private-location data is used.

# Expected Result

Create an explicit privacy/data boundary for product-demo and field-test
evidence. The result should be usable as a KR-008/V1 review gate and as an
input to DATA-002 consent/data-flywheel planning.

# Acceptance Criteria

- [ ] A current document under `docs/product/` or `docs/development/` defines
      data classes for GNSS coordinates, cell signatures, Wi-Fi identifiers,
      IMU windows, user confirmations, audio, image, guardian/contact data,
      VPS logs, and training/export artifacts.
- [ ] The document states default retention/export/training rules for each
      class, including `training_allowed=false` until consent and privacy
      review explicitly allow training use.
- [ ] Raw audio and raw image retention remain disabled by default; any future
      enablement requires explicit consent, retention limits, and a separate
      task.
- [ ] Wi-Fi raw BSSID retention is disallowed by default; hashed fingerprints
      require salt/rotation and retention rules before product-demo use.
- [ ] Private coordinates are bounded evidence/export data, not copied into
      current docs or generated summaries unless redacted or explicitly
      authorized.
- [ ] KR-008/product-demo report readiness includes a privacy gate result or
      blocker, without changing the existing release non-claim boundaries.
- [ ] Tests or lint checks cover the machine-readable parts that are changed.
- [ ] `python scripts/context_lint.py` passes; run full verify if code or
      contracts change.

# Validation Commands

```powershell
python scripts/context_lint.py
```

If code, schemas, or report generation change:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

# Hardware Validation

- Not applicable. This task is a privacy/product gate definition.

# Decisions

- This task is not a legal compliance certification. It is an engineering
  boundary so demos and datasets do not accidentally use private evidence as
  product-ready or training-ready data.
- Privacy decisions that affect product policy remain founder-owned.

# Completion Evidence

- Changed files:
- Test result:
- Hardware result: not applicable
- Remaining risks:

# Builder Prompt

```text
Read docs/tasks/active/PRIVACY-001_PRODUCT_DEMO_DATA_BOUNDARY_GATE.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and the files
in this packet's `context`. Do only this task; obey `allowed_paths` and
`out_of_scope`. Produce a privacy/data boundary suitable for KR-008 and V1
field-test review. Do not collect private data. Keep raw audio and raw image
retention disabled by default. Run the validation commands before finishing.
Return changed files, validation output, evidence paths, and unresolved
founder/legal decisions. Do not update docs/current/STATUS.md and do not move
this packet to done/.
```

---
id: LOC-006
title: GNSS-denied hybrid location strategy freeze
status: accepted_for_transition
priority: high
requires_hardware: false
serves_demo: D2
created: 2026-08-12
last_updated: 2026-08-14
execution_state: completed

context:
  - docs/AGENTS.md
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - docs/development/DEV_FLOW.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/LOCATION_DATASET.md
  - docs/development/LOCATION_FUSION_ALGORITHM.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/architecture/adr/ADR-0003-low-power-location-state-machine.md
  - docs/architecture/adr/ADR-0004-p0-rule-location-and-transitional-vps-memory.md
  - docs/architecture/adr/ADR-0005-v1-pro-production-hardware-baseline.md
  - docs/architecture/adr/ADR-0006-v1-pro-product-peripheral-revision.md
  - docs/architecture/adr/ADR-0007-gnss-denied-personal-location-memory.md
  - docs/architecture/adr/ADR-0008-egolink-core-product-direction-reset.md
  - docs/hardware/V1_PRO_EVT_PROCUREMENT_BASELINE.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/product/V1_PRO_FORM_FACTOR_BASELINE.md

allowed_paths:
  - docs/CONTEXT_INDEX.md
  - docs/tasks/done/LOC-006_GNSS_DENIED_HYBRID_LOCATION_STRATEGY.md
  - docs/architecture/adr/ADR-0007-gnss-denied-personal-location-memory.md
  - docs/development/LOCATION_ENGINE.md
  - docs/roadmap/V1_PRODUCT_PLAN.md
  - docs/product/V1_PRO_FORM_FACTOR_BASELINE.md

out_of_scope:
  - firmware, server, contract, or model behavior changes
  - learned coordinate regression or dead reckoning claims
  - hardware capability claims without direct evidence
  - changes to NORTH_STAR.md, STATUS.md, or ACTIVE_BUILD.md
---

# Goal

Freeze the smallest product and architecture strategy for useful, honest
location beliefs when GNSS is denied, while preserving EALE-P0 rule-first
behavior and remaining independent of the production radio/BOM choice. The
prior V1 Pro hardware topology is historical after ADR-0008.

# Expected Result

The authoritative location, product, and form-factor documents consistently
define precise/coarse anchor boundaries, personal place/route memory, bounded
Top-K hypotheses, active sensing, source and privacy boundaries, and an RF occlusion acceptance
matrix without silently depending on production Wi-Fi.

# Acceptance Criteria

- [x] ADR-0007 records the strategy, its rule-first boundary, and the fact
      that only the existing IMU motion candidate is approved under ADR-0004.
- [x] `LOCATION_ENGINE.md` routes the strategy into staged implementation.
- [x] `V1_PRODUCT_PLAN.md` distinguishes the ESP32 Wi-Fi engineering path from
      the unverified production Wi-Fi/BLE/radio topology reopened by ADR-0008.
- [x] The superseded `V1_PRO_FORM_FACTOR_BASELINE.md` retains its historical
      body/bag RF matrix, while the current Master Context carries forward
      acquisition/recovery, honesty, and A0/A1 RF gates without inheriting its
      watch/OLED/PCB envelope.
- [x] No exact private location, raw Wi-Fi identifier, model-performance
      claim, or unverified hardware capability is introduced.

# Validation Commands

```powershell
python scripts/context_lint.py
git diff --check -- docs/CONTEXT_INDEX.md docs/tasks/done/LOC-006_GNSS_DENIED_HYBRID_LOCATION_STRATEGY.md docs/architecture/adr/ADR-0007-gnss-denied-personal-location-memory.md docs/development/LOCATION_ENGINE.md docs/roadmap/V1_PRODUCT_PLAN.md docs/product/V1_PRO_FORM_FACTOR_BASELINE.md
```

# Hardware Validation

Not required for this strategy-only slice. Later EVT evidence must identify
board, firmware/image, connection path, timestamp, configuration, and evidence
path for every RF test.

# Decisions

- This slice serves D2 by defining how no-fix evidence remains useful without
  weakening the accuracy baseline or inventing coordinates.
- P0 uses replayable rules, lookup, clustering, statistics, and conservative
  decay. ADR-0004 still approves only IMU motion as a learned candidate.
  Reliability or sensing-value models remain post-P0 research ideas requiring
  a later founder-reviewed ADR/task; no model directly produces coordinates.
- Production Wi-Fi is not assumed. ADR-0008 supersedes the prior no-third-radio
  V1 Pro topology and reopens A0/A1 2.4 GHz decisions; Wi-Fi/BLE parts,
  antennas, coexistence, privacy and behavior remain `unverified` until a
  later accepted hardware decision and evidence prove otherwise.

# Completion Evidence

- Changed files: this packet, context routing, ADR-0007, and the three
  authoritative product/engineering documents listed in `allowed_paths`.
- Test result: `python scripts/context_lint.py` PASS; scoped
  `git diff --check` PASS.
- Hardware result: not applicable; no hardware action performed.
- Remaining risks: LOC-007 rule/memory implementation and GNSS-masked replay,
  replay thresholds, radio capabilities, RF performance, and any post-P0
  learned reliability research still require separately scoped work and
  measured evidence. This strategy slice performs no replay itself.

# Builder Prompt

```text
Read docs/tasks/done/LOC-006_GNSS_DENIED_HYBRID_LOCATION_STRATEGY.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, this packet,
and its context entries. Freeze only the GNSS-denied product strategy, its
rule-first/approved-model boundary, the production radio boundary, and the RF
occlusion acceptance matrix. Obey allowed_paths and out_of_scope. Run the
declared validation commands. Do not implement firmware, server, model, or
data-contract behavior; do not update STATUS or ACTIVE_BUILD. Return changed
files, validation output, and remaining risks.
```

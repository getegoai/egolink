---
document_status: historical_migration_map
archived_at: 2026-09-22
---

# Decision and execution migration map

All snapshots retain exact bytes before their named edit phase. They are not
all initial-HEAD snapshots: the manifest's per-entry `capture_scope` identifies
intermediate working-tree captures. Current targets preserve evidence dates.

| Source / current target | Migration | SHA-256 of snapshot |
|---|---|---|
| [docs/product/NORTH_STAR.md](docs/product/NORTH_STAR.md.source) -> [current](../../../../docs/product/NORTH_STAR.md) | Preserve 9/19 founder goal; route successor ADR, label older communications scope, repair stale remote instruction. | `e71b36e8a2642ff36acfe2395f9057c551371da95d6ae112b0ad80f3269ff6f4` |
| [docs/product/EGO_MASTER_CONTEXT.md](docs/product/EGO_MASTER_CONTEXT.md.source) -> [current](../../../../docs/product/EGO_MASTER_CONTEXT.md) | Align native-cellular primary, private Base endpoint, bounded cloud transition and engineering truth; preserve safety and assurance invariants. | `b1181cfd263ec61628cd78e0ac9320900ccacd758b729a92fb4cc9a31d8bc2b6` |
| [docs/product/PRODUCT_CHARTER.md](docs/product/PRODUCT_CHARTER.md.source) -> [current](../../../../docs/product/PRODUCT_CHARTER.md) | Align native-cellular primary, private Base endpoint, bounded cloud transition and engineering truth; preserve safety and assurance invariants. | `d1ac7a702920ba62fb17dee4ae6537a77ffa3d9a63300e01459c71e2b0b60b29` |
| [docs/product/P0_SCOPE.md](docs/product/P0_SCOPE.md.source) -> [current](../../../../docs/product/P0_SCOPE.md) | Align native-cellular primary, private Base endpoint, bounded cloud transition and engineering truth; preserve safety and assurance invariants. | `9ddad909ef810536af56ff81638d3e0d6e968baf1d32dfa5c63511ff8844681b` |
| [docs/CONTEXT_INDEX.md](docs/CONTEXT_INDEX.md.source) -> [current](../../../../docs/CONTEXT_INDEX.md) | Align native-cellular primary, private Base endpoint, bounded cloud transition and engineering truth; preserve safety and assurance invariants. | `86bf10ba4a8848be96dda32bc4bf4854f7d947dcde99b55b91cd30593236aa85` |
| [docs/architecture/SYSTEM_OVERVIEW.md](docs/architecture/SYSTEM_OVERVIEW.md.source) -> [current](../../../../docs/architecture/SYSTEM_OVERVIEW.md) | Align native-cellular primary, private Base endpoint, bounded cloud transition and engineering truth; preserve safety and assurance invariants. | `32b8a0063b7501d1bb63e047d5b6faeffdd1a41b4e3af1bf40d13a47aea7c175` |
| [docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md](docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md.source) -> [current](../../../../docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md) | Original decision retained; short ADR-0016 partial-supersession notice only. | `541724a90a8737eac60c256d018ccd07f434528c78cc5feb429c0d4aaae39b91` |
| [docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md](docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md.source) -> [current](../../../../docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md) | Original decision retained; short ADR-0016 partial-supersession notice only. | `63b154fabee7ab2fdde2c0324c3b7b140a69811dae9aa1ea26e5961ecfba5cb1` |
| [docs/architecture/adr/ADR-0014-runtime-convergence.md](docs/architecture/adr/ADR-0014-runtime-convergence.md.source) -> [current](../../../../docs/architecture/adr/ADR-0014-runtime-convergence.md) | Original decision retained; short ADR-0016 partial-supersession notice only. | `3bcf432df273f79ef5b34dc55cc425507c3fcf24ab578bced25257e20b108706` |
| [docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md](docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md.source) -> [current](../../../../docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md) | Original decision retained; short ADR-0016 partial-supersession notice only. | `0e7a4bcb0d5f60bd4f9e9b3ba188cc8ddc9edf7e4d9b2ef1ef8de56336c4af5a` |
| [docs/current/FIRST_LAUNCH_EXECUTION.md](docs/current/FIRST_LAUNCH_EXECUTION.md.source) -> [current](../../../../docs/current/FIRST_LAUNCH_EXECUTION.md) | Replace stale current schedule and RTC dependency graph; historical milestone traces remain in this snapshot and original packets. | `e83f60075bb7aa623c12c0bcc0cfa357ee86330fdd077c074fdbe15935bb8540` |
| [docs/current/EGO_LINK_AI_CURRENT_CONTEXT.md](docs/current/EGO_LINK_AI_CURRENT_CONTEXT.md.source) -> [current](../../../../docs/current/EGO_LINK_AI_CURRENT_CONTEXT.md) | Retain asynchronous/field methodology; align private endpoint and rule-state truth, distinguish historical implementation reports. | `b8de9d24cae0d5b3c481df378ed08781c59e8418f6b0a189dab3480e0b55d692` |
| [docs/development/DEV_FLOW.md](docs/development/DEV_FLOW.md.source) -> [current](../../../../docs/development/DEV_FLOW.md) | Align native-cellular primary, private Base endpoint, bounded cloud transition and engineering truth; preserve safety and assurance invariants. | `ce5aa6ebd5d007ad153cf7ed97717e30cbfa9664cb385208cb51d73f2a61214e` |
| [docs/roadmap/P0_TO_PRODUCT_MIGRATION.md](docs/roadmap/P0_TO_PRODUCT_MIGRATION.md.source) -> [current](../../../../docs/roadmap/P0_TO_PRODUCT_MIGRATION.md) | Replace stale current schedule and RTC dependency graph; historical milestone traces remain in this snapshot and original packets. | `a945b2b414335da57c58a2a7275139e35fd04c9e7e19c6cdc96ba4ec9cfd84ab` |
| [docs/roadmap/V1_PRODUCT_PLAN.md](docs/roadmap/V1_PRODUCT_PLAN.md.source) -> [current](../../../../docs/roadmap/V1_PRODUCT_PLAN.md) | Replace stale current schedule and RTC dependency graph; historical milestone traces remain in this snapshot and original packets. | `3e458f7d7c57aa61c9d66c61f67a878ff492a2c0acad0b6f01875ab65e5ba7d1` |

Retained across all replacements: three P0 Gate names and NOT_RUN states;
screenless people-first EgoCore, 48-hour measured guard target, product assurance,
source time/identity, exact ACK, local SOS degradation and hardware authorization.
The legacy RTC/native-reserve and Base-only-later scheduling clauses are replaced
by ADR-0016; historical successes and failures are not reclassified.

## Semantic destination map

| Prior material | Current destination | Treatment |
|---|---|---|
| Master v2.2 sections 2/4.2/5.2/8/9.2/13/15 native reserve and RTC primary | Master v2.3 sections 2/5/8/9.2/13/15; ADR-0016 sections 1/2 | Native primary replaces reserve-only; exact hardware candidates remain unverified, no old three-operator gate automatically restored |
| Master Base/planned roles and historical P4-only sequencing | Master sections 1/6; migration roadmap private-endpoint section; BASE-010 | Minimum endpoint parallel; complete private AI remains later growth |
| Master v2.2 sections 7-10 and 14-15 product construction/manufacturing candidates | Same numbered Master sections | Retained detailed candidates/physical constraints; only conflicting native-voice role wording migrated |
| FIRST_LAUNCH long 9/04-9/16 chronology and stale run017 next steps | Current STATUS/ACTIVE_BUILD and original named packets; exact snapshot here | Removed from scheduler, retained unchanged in snapshot; no success/failure reclassified |
| FIRST_LAUNCH/V1 old CALL-020 -> CALL-021 product dependency | Current execution/V1/migration graphs | CALL-030 + HW-022 -> CALL-031 supplies native call, later SOS and power consumers; old RTC remains paused |
| AI context old FW-007/FT/EXP current-state claims and 9/21 implementation guarantees | AI context sections 3/4/7/8; current fact authorities | Historical methodology retained; runtime facts routed, validity/contract/UI claims become explicit engineering acceptance |
| V1 numeric waves and historical P0-A through P4 command inventories | Exact V1/migration snapshots and original packets | Historical assets, not dispatch instructions; current WIP remains in TASK_TREE |
| Product declaration that native VoLTE/formal Base are out of scope | Charter/scope current promise and non-claims | Native product loop and minimal Base in scope; advanced models, self-operated public gateway and unmeasured claims remain excluded |
| North Star 8/23 communications and stale no-remote instruction | North Star dated history and Git-flow routing | 9/19 goal preserved; old applicability explicit, remote state checked rather than asserted |

The initial authority pass did not edit STATUS, ACTIVE_BUILD, BOARD_MATRIX,
TASK_TREE, task packets or progress configuration. The separately authorized
review pass below updates the named task clauses only; root owns current facts
and scheduling integration. No hardware, deployment, private-data operation or
commit ran in this subtask.

## Authorized consistency review follow-up

Exact paths and SHA-256 values for all 23 snapshots are in [manifest.json](manifest.json).
The original Master snapshot is retained; `EGO_MASTER_CONTEXT.md.review.source`
also records the intermediate shortened text before this corrective pass.
HW-021 was captured after root's WIP metadata migration but before this agent's
native-call/body edits: its `parked`/`unassigned`/`reviewed_at` fields are already
present. It is not attributed to the initial HEAD; see its null `source_commit`
and exact SHA-256 in the manifest. The remaining 21 snapshots match the
recorded comparison commit's blobs byte-for-byte.

| Source / current target | Preserved or migrated requirement |
|---|---|
| [Master review checkpoint](docs/product/EGO_MASTER_CONTEXT.md.review.source) -> [current](../../../../docs/product/EGO_MASTER_CONTEXT.md) | Restore current hard-power privacy target (unverified), encrypted volatile default media buffer, signed/verifiable/auditable artifacts, model/data/evaluation/device/rollout/rollback binding, reproducible learning restrictions, controlled call context and bare-module A0 measurement/manufacturing interfaces. Authorized engineering capture is not product acceptance. |
| [Mass-production requirements](docs/product/MASS_PRODUCTION_REQUIREMENTS.md.source) -> [current](../../../../docs/product/MASS_PRODUCTION_REQUIREMENTS.md) | Migrate native voice from reserve to P0-CALL; retain 48-hour/5-7-day profile distinctions, three-operator LTE-data evidence, cost/MOQ/sourcing, China compliance, acoustic/RF/privacy/manufacturing requirements. No automatic three-operator native gate. |
| [P0 architecture](docs/hardware/P0_PRODUCT_ARCHITECTURE.md.source) -> [current](../../../../docs/hardware/P0_PRODUCT_ARCHITECTURE.md) | Native control/audio ownership and CALL-030 + HW-021 -> HW-022 -> CALL-031; actual topology remains unknown, current build has no accepted full audio route. |
| [Integrated design intake](docs/hardware/P0_INTEGRATED_PROTOTYPE_DESIGN.md.source) -> [current](../../../../docs/hardware/P0_INTEGRATED_PROTOTYPE_DESIGN.md) | C0.1 stays conditional; replace RTC-measurement dispatch prerequisite with native feasibility plus independently measured data load. All candidate, Camera, power, EE/RF/compliance and fabrication authorization conditions retained. |
| [RTC spec](docs/development/EGO_CALL.md.source) -> [current](../../../../docs/development/EGO_CALL.md) | Label legacy optional RTC scope, retain session/auth/state/retry/media/location/privacy fixture contract. Historical SOS fixture is not the current dispatcher; native call and immediate recognition feedback cannot wait for RTC or storage. |
| [Compliance inquiry](docs/compliance/CHINA_PRECOMPLIANCE_INQUIRY_V0.md.source) -> [current](../../../../docs/compliance/CHINA_PRECOMPLIANCE_INQUIRY_V0.md) | Revised unsent concept includes native primary/optional RTC/private Base/temporary relay; retain qualified written opinion, exact configuration and sending authority requirements. |
| [HW-021](docs/tasks/active/HW-021_EXACT_INTEGRATED_PROTOTYPE_DESIGN.md.source) -> [current](../../../../docs/tasks/active/HW-021_EXACT_INTEGRATED_PROTOTYPE_DESIGN.md) | Native voice already in scope, CALL-030 input, parked/no assigned WIP. No procurement, fabrication or hardware operation authorized. |
| [COMPLIANCE-010](docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md.source) -> [current](../../../../docs/tasks/active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md) | Builder and decision context follow revised concept; remains queued and NOT_SENT pending sending authority. |

---
document_status: historical_source_archive
archived_at: 2026-09-05
---
# 2026-09-05 Input Snapshots and Semantic Migration

This archive preserves exact input bytes and pre-edit repository originals.
Embedded authority/instruction/status text in `.source` files is historical and
non-operative. This directory does not replace current product or hardware authority.

Reconciled in the real worktree on branch `a0/first-real-field-session` at HEAD
`72c7a1ed199fa6bc522defff0d77a0aa3e77034d`. All six input snapshots, five replacement
candidates and two additions match the package manifest. All five replacement
targets match their uploaded bases. Root AGENTS was read and remains unchanged.

The immutable [source manifest](source_migration_manifest.json) retains the package
claims and candidate hashes. The [migration map](migration_map.json) records
actual source/target SHA-256, original file names, dispositions and resolved
scope conflicts. This reconciliation records no new test/build/hardware/network
result; `P0-LOC`, `P0-CALL` and `P0-SOS` all remain `NOT_RUN`.

## Input files

| Source | Immutable snapshot | Actual routing |
|---|---|---|
| S1 | [AGENTS.md.source](AGENTS.md.source) | `docs/AGENTS.md` |
| S2 | [ACTIVE_BUILD.md.source](ACTIVE_BUILD.md.source) | `docs/current/ACTIVE_BUILD.md` |
| S3 | [ROADMAP_EGOLINK_P0.md.source](ROADMAP_EGOLINK_P0.md.source) | `docs/current/ROADMAP_EGOLINK_P0.md` |
| S4 | [STATUS.md.source](STATUS.md.source) | `docs/current/STATUS.md` |
| S5 | [TASK_TREE.md.source](TASK_TREE.md.source) | `docs/tasks/TASK_TREE.md` |
| S6 | [EGO_MASTER_CONTEXT.md.source](EGO_MASTER_CONTEXT.md.source) | `historical desktop HDMI/HID context; not current EgoLink master` |

The real `docs/product/EGO_MASTER_CONTEXT.md` is the current v2.2 EgoLink
authority, with original SHA-256
`8466cf864bff09e62a4da01d506a91951046143aff1b06875fa6d382231307c0`.
Its separate repository-original snapshot is retained; S6 is not merged into it.

## Semantic migration

| Actual target | Applied decision |
|---|---|
| `docs/AGENTS.md` | Semantic merge of candidate scope/evidence/operational rules; keep root authority and operative historical preservation rules. |
| `docs/current/ACTIVE_BUILD.md` | Keep all recorded image identities and prior failures; add distinct selected-live-profile direction and correct T0 global sequencing. |
| `docs/current/ROADMAP_EGOLINK_P0.md` | Add bounded-runtime, physical-safety/recovery, carry and campaign outcomes; retain existing R/D/KR lineage and release scope. |
| `docs/current/STATUS.md` | Retain complete dated evidence history; add only nine lines of accepted direction, no new verification result. |
| `docs/tasks/TASK_TREE.md` | Keep task IDs/history; update current WIP and execution order to concrete Location/CALL then SOS. |
| `docs/product/EGO_MASTER_CONTEXT.md` | Retain current EgoLink v2.2 product authority; uploaded desktop S6 is historical only; add ADR0014 runtime interpretation. |
| `docs/product/NORTH_STAR.md` | Founder-authorized dated direction and changelog; preserve last_verified and all product commitments. |
| `docs/product/PRODUCT_CHARTER.md` | Clarify independent recognized/stored/delivered outcomes and bounded live implementation unit without Gate changes. |
| `docs/product/P0_SCOPE.md` | Clarify device-owned local runtime, single-source live scope and retained concurrent recovery promises. |
| `docs/CONTEXT_INDEX.md` | Route current context to accepted ADR0014 and active convergence packet; maintain specialized fact ownership. |
| `docs/current/FIRST_LAUNCH_EXECUTION.md` | Replace immediate order and narrow global T0/T1 dependency; retain prior dated evidence and final campaigns. |
| `docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md` | Dispatch bounded real Location; explicitly retain original T0/T1 ordering/checkpoint/tombstone/no-output replay commitments. |
| `docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md` | Record recognized-input and storage-failure migration and no replayed ended-call effect; prior slices stay historical evidence. |
| `docs/architecture/adr/README.md` | Index accepted ADR0014; ADR0013 remains proposed. |

The candidate ADR was assigned unused number
[ADR-0014](../../../architecture/adr/ADR-0014-runtime-convergence.md) and accepted
under the founder's explicit implementation instruction. ADR-0013 remains
proposed. Candidate ADR-DRAFT links are replaced only in the operative migrated
files; the original review bundle and immutable snapshots retain their bytes.
The [active packet](../../../tasks/active/P0-CONVERGENCE-20260905.md) requires
actual runtime code, executable behavior tests and both builds; it is not
complete merely because this migration is written.

Current documents retain their prior `last_verified` dates. `decision_updated`
identifies the accepted direction change, not a newly verified capability.
No unresolved authority conflict was silently chosen; the scoped interpretations
and supersessions are explicit in ADR-0014 and the machine-readable map.

## Repository-original snapshots

| Original target | Snapshot | SHA-256 |
|---|---|---|
| `docs/AGENTS.md` | [AGENTS.md.source](AGENTS.md.source) | `76fcd243d794d6b68dfedcf9d39d1baaa5884bee6fcde31354814f0a3bbc519e` |
| `docs/CONTEXT_INDEX.md` | [docs__CONTEXT_INDEX.md.repository.source](docs__CONTEXT_INDEX.md.repository.source) | `9343e27559de0e6e9684c52913eaba56beb582721f4c86d15539340f0818cbad` |
| `docs/product/NORTH_STAR.md` | [docs__product__NORTH_STAR.md.repository.source](docs__product__NORTH_STAR.md.repository.source) | `afbb4660df6cb3f40d61896204120402afd6d555a8913d4ccc2d555af6ea3420` |
| `docs/product/EGO_MASTER_CONTEXT.md` | [docs__product__EGO_MASTER_CONTEXT.md.repository.source](docs__product__EGO_MASTER_CONTEXT.md.repository.source) | `8466cf864bff09e62a4da01d506a91951046143aff1b06875fa6d382231307c0` |
| `docs/product/PRODUCT_CHARTER.md` | [docs__product__PRODUCT_CHARTER.md.repository.source](docs__product__PRODUCT_CHARTER.md.repository.source) | `2236c89f21ec22ee9efa07697efe32b75851cfd7035fdefbc3c83028442d9561` |
| `docs/product/P0_SCOPE.md` | [docs__product__P0_SCOPE.md.repository.source](docs__product__P0_SCOPE.md.repository.source) | `c69a92549f322a67139ff7a52bce6868e7407869387c322001631e81d8c973a4` |
| `docs/current/FIRST_LAUNCH_EXECUTION.md` | [docs__current__FIRST_LAUNCH_EXECUTION.md.repository.source](docs__current__FIRST_LAUNCH_EXECUTION.md.repository.source) | `941bbbaf0ea2dcc4348e6acc47d4ac1e5f75027973219132eb8a23d13306f605` |
| `docs/current/ACTIVE_BUILD.md` | [ACTIVE_BUILD.md.source](ACTIVE_BUILD.md.source) | `d1e27683b51519eea570b480e286fb2800377bb749ac85d58de3c3733fd1950a` |
| `docs/current/ROADMAP_EGOLINK_P0.md` | [ROADMAP_EGOLINK_P0.md.source](ROADMAP_EGOLINK_P0.md.source) | `904ff9397bb1c6ad8b508c360eaf91d8c8d47060fbe7ff73a9010ba9789e74bf` |
| `docs/current/STATUS.md` | [STATUS.md.source](STATUS.md.source) | `b078d1b11fdd4e4b93edafba7af3aec6e40aa3dd66b49d54c07130c9e9f31e3a` |
| `docs/tasks/TASK_TREE.md` | [TASK_TREE.md.source](TASK_TREE.md.source) | `3f6eb8e8dcea2058e17aa4f6d1e504a3fd404e7e5de015e75b52a9ca6796e609` |
| `docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md` | [docs__tasks__active__LOC-021_DEVICE_LOCATION_INTEGRATION.md.repository.source](docs__tasks__active__LOC-021_DEVICE_LOCATION_INTEGRATION.md.repository.source) | `862e6d248629d1b608a232998edf095299e6b8673f59c88afecafb22950a5190` |
| `docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md` | [docs__tasks__active__SOS-010_SOS_WALKING_SKELETON.md.repository.source](docs__tasks__active__SOS-010_SOS_WALKING_SKELETON.md.repository.source) | `29e7f0652dfaf5e483c25630e76451e22540ae579790548efd1a6b8fcbced4f9` |
| `docs/architecture/adr/README.md` | [docs__architecture__adr__README.md.repository.source](docs__architecture__adr__README.md.repository.source) | `dafed0a608d4b635175babbff27efb900251bce0d182e445fc76ac8b26da4c6d` |

Original relative links inside raw snapshots resolve from their historical
repository location; they are intentionally not rewritten inside immutable bytes.
Root AGENTS SHA-256: `58e2e5ccd095f273e0202d5009c618c813982d11ec43d104c92f9df05e08b6c1`.

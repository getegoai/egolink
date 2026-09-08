---
document_status: proposed_current_task_tree
reviewed_at: 2026-09-05
evidence_as_of: 2026-09-04
---
# EgoLink — Current Execution Tree

This queue is a direction revision candidate. Existing task IDs, source code
and evidence remain intact. Repository reconciliation must read the real active
packets before changing their status or dependencies.

## One outcome

Move the existing offline assets into a demonstrable, measured runtime loop:
Location visible → physical SOS noticed → authorized two-way contact.
P0-LOC, P0-CALL and P0-SOS remain NOT_RUN until their campaigns run.

## Work in progress: one integrator, at most two disjoint builders

| Lane | Immediate deliverable | Existing assets | Exit evidence |
|---|---|---|---|
| A — mainline | Live device Location to bound Guardian | LOC-021 A-S + OPS-004 + OUTBOX-010 | Real state and exact ACK over a verified secure route; no-fix/stale honest |
| B — independent | Real bidirectional CALL and embedded-bearer feasibility | CALL-010 transition, CALL-020 A-R, HW-021 | Actual audio both ways, route proof, teardown and memory; migration limits |
| C — queued integration | Physical SOS and failure recovery | SOS-010 A-J, Lane A delivery, Lane B call seam | Physical trigger and local response; durable event; guardian notice/human ACK; independent call outcome |

Power baseline, antenna placement and Guardian locked-screen notice are small
experiments inside these lanes, not additional platform-building workstreams.
HW-021 continues only on design choices informed by these measurements.
No source path has two concurrent writers; integration owns shared contracts.

## Next implementation task

[P0-CONVERGENCE-20260905](active/P0-CONVERGENCE-20260905.md) is the one
next task packet. Its first code deliverable is a live Location profile and
an executable behavior test. A document-only update does not complete it.

## Reclassification of current work

| Existing work | Direction |
|---|---|
| LOC-021S | Reuse as isolated owner smoke; no automatic feature expansion or product claim |
| LOC-021T0 | Scope to minimum recovery inputs; justify every persisted stream; not a global live-test blocker |
| LOC-021T1 | Keep blocked under old invariant until scoped replacement or equivalent persistence/replay tests pass |
| CALL-020 | Finish concrete connector/endpoints; stop adding generic lifecycle layers without runtime demand |
| CALL-021 | Early embedded transport feasibility now; final gate remains after representative hardware |
| OUTBOX-010 | Retain strict ACK and critical reserves; verify actual backend and bounded recovery |
| SOS-010 | Test recognized-input feedback and storage-failure degraded help, then connect physical input |
| PWR-001 / PWR-020 | Early board baseline now; integrated campaign and claim verification later |
| DATA/TRAIN scaffolding | Freeze new planners/registries/report panels; reuse existing tools on consented real evidence |
| Camera/advanced AI/native VoLTE | Non-blocking later work or reserve; no new product dependency |

## What counts as progress

Report the user-visible outcome, the actually executed tests and their scope,
remaining hard blocker, and one next action. Keep build/source checks separate
from native concurrency, hardware, network, field and release checks.
Every skipped critical test names the missing environment and the next test
that will close it; never hide it behind the total green count.

Historical task inventory and all earlier completion records remain in the
[input archive](../archive/reviews/20260905_input_snapshots/README.md).

---
document_status: proposed_revision
reviewed_at: 2026-09-05
evidence_as_of: 2026-09-04
---
# EgoLink — Runtime-to-Product Roadmap

## Product commitment

First launch: Reliable Location, authorized Ego Call over LTE data, physical
SOS and honest delivery/failure states. Advanced learned fusion, camera,
pet-specific behaviors and native VoLTE reserve remain non-blocking.
An external service may carry authorized messages/media; deterministic local
safety and degraded location do not require a cloud model to make decisions.

The existing P0-LOC/P0-CALL/P0-SOS and P0-RELEASE-010 meanings are retained.
The stages below are development outcomes, not new names for product PASS.
Current product-gate state remains NOT_RUN for all three.

## B0 — bounded runtime proof

Deliver a new, explicitly selected live Location profile:
real GNSS/Cell evidence → device state → authenticated secure delivery →
Guardian display showing source, event age, uncertainty and transport state.
No-fix is an acceptable observation; permanent unknown is not an adequate
product positioning result. A single-source/current-boot slice must state
its missing restart/concurrent-ingress guarantees.

In parallel, exercise existing audio endpoints through a real authorized
bidirectional media path. First demonstrate both ends; then verify the LTE
route. Wi-Fi/local bench results remain labelled as such.
Capture local heap/stack/queue counters alongside server and Guardian results.

## B1 — physical safety and recovery

Join physical long-press input, recognized-input feedback, critical durable
journal/outbox, urgent Location and an independently attempted call.
Validate storage-full/write-failure, real outage/recovery, duplicate and late
ACK, controlled reboot, and expired call/SOS recovery behavior.
A network call failing must not erase the alert or make delivery look successful.
An unrecoverable journal failure must produce explicit degradation, not silence.

Checkpoint and outbox settlement must survive the selected fault model.
An accepted design may use compact snapshots + pending critical events instead
of a universal raw-sensor WAL, provided the same scoped safety invariants hold.
The old concurrent LOC-021T1 is not enabled before its replacement is proven.

## F0 — independently powered engineering carry prototype

Use a rigid carrier/enclosure and known antenna placement; an engineering
interconnect is allowed. No PC dependency in the device-side operating path.
Select one initial human-safety use case and document placement, runtime
configuration, reference method and consent. Do not simultaneously optimize
child watch, elderly pendant and pet collar in this stage.

Run familiar-route/carry/no-fix/weak-network cases, with a reference method
whose uncertainty is stated. Maintain source event time; label reference gaps.
Start power measurement in B0 and repeat here; do not wait for final integration.

## F1 — representative capability campaigns

Use FIELD-020, CALL-021 and SOS-010 with the integrated HW-022 candidate.
Retain the existing detailed campaign requirements after repository review;
one 60-second call or one correct position cannot replace them.

| Capability | Required measurement family |
|---|---|
| Location | Time-weighted usable-position coverage, accuracy conditional on reference quality, stale duration, transition continuity, update latency, uncertainty calibration, energy |
| Call | Setup outcomes, both directions, duration, blackout/recovery, delay with measurement method, teardown/mic/PA state, heap/stack, weak-network and guardian app state |
| SOS | Qualified input/feedback, persistence/recovery, server receipt, terminal notice, explicit human acknowledgement, independent call outcome |
| Reliability | Reset/power-loss matrix, bounded queue/drop accounting, reconnect/failback, storage writes, data loss and duplicate behavior |

## Release — P0-RELEASE-010

Converge P0-LOC/P0-CALL/P0-SOS with OPS-004, OUTBOX-010, HW-022,
PWR-020 and COMPLIANCE-010 plus measured acoustic/RF/enclosure/security/
privacy/manufacturing evidence. Validate update, rollback, provisioning,
binding/revocation, retention/deletion and recovery of deployed data.
Forty-eight-hour evidence cannot by itself substantiate seven-day endurance.
A sale date, battery promise and production BOM require their own evidence.

## Dependency corrections

- S modem-only smoke and secure-transport validation do not wait for T0/T1.
- General cross-source historical replay does not gate a bounded B0 run.
- SOS local handling does not wait for fresh GNSS, a model or the HTTP owner.
- Embedded-bearer risk reduction starts before final HW-022; final CALL-021
  acceptance still requires the representative prototype.
- Early power, RF placement and Guardian reachability experiments run in
  parallel; full acceptance still converges at release.

Implementation: [current packet](../tasks/active/P0-CONVERGENCE-20260905.md).
Decision rationale: [ADR candidate](../architecture/adr/ADR-DRAFT-20260905-runtime-convergence.md).
Old R/D/KR lineage: [input archive](../archive/reviews/20260905_input_snapshots/README.md).

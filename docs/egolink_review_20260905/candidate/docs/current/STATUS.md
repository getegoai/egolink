---
document_status: proposed_revision
reviewed_at: 2026-09-05
evidence_as_of: 2026-09-04
evidence_method: uploaded_document_review
repository_reverified: false
---
# EgoLink — Current Status

## Outcome and stage

First-launch scope remains **Reliable Location + Ego Call + physical SOS**.
The engineering stage is **runtime integration before a representative product
closed loop**. The new development priority is to obtain real runtime evidence
from existing components, while retaining safety, privacy and release criteria.

| Product gate | Recorded state | Missing outcome |
|---|---|---|
| P0-LOC | NOT_RUN | Live device-owned state, honest Guardian view, representative field evidence |
| P0-CALL | NOT_RUN | Authorized two-way LTE-data voice on a representative PC-free path |
| P0-SOS | NOT_RUN | Physical long press, durable event, feedback, Guardian alert and independent call attempt |

These are retained source states, not a new gate execution.

## What actually exists

| Area | Latest recorded evidence | Remaining boundary |
|---|---|---|
| Connectivity hardware | FW-007: bounded LTE-to-Wi-Fi takeover and prior LTE uplink/command evidence | No new P0 runtime on the flashed node; failback, durable queue and endurance unverified |
| Wearable hardware | UI-001 restored after CALL-010; run 008 speaker audibility confirmed; run 007 input changed with spoken stimulus | Full duplex, mic mapping, acoustic delay and product acoustics unverified |
| Location candidate | LOC-021 A-S: reducer/policy/emitter/outbox/owner; S is isolated modem-only composition | S not run; live secure delivery and external concurrent ingress not composed |
| Call candidate | CALL-020 A-R: host/device media and owner/cleanup components | Real authentication/TLS/SIM route, Guardian media and runtime memory unverified |
| SOS candidate | SOS-010 A-J: input, journal, ordering and server/Guardian semantics | Physical button, flash failure behavior, push/human delivery and call not exercised |
| Storage/security | Persistent adapter and strict ACK contracts in offline tests | 22,240-byte full-slot mutation is field-test-only; retention and key lifecycle incomplete |

Reported full-repository result: **1614 passed, 12 environment-guarded skips**
on 2026-09-04. This review did not rerun it. Critical skips must be classified
by the actual runner before enabling the corresponding runtime.

## Current leadership decisions

The [runtime-convergence ADR candidate](../architecture/adr/ADR-DRAFT-20260905-runtime-convergence.md)
changes development ordering, not existing evidence. The immediate work is:

1. Deliver a bounded live **Location → authenticated transport → Guardian**
   vertical slice, reusing the existing owner/reducer and a narrow profile.
2. In parallel, prove a real bidirectional CALL route and a clear path from
   the bench fixture to an embedded bearer. Avoid extending the PC bridge
   without a named runtime consumer.
3. Integrate physical SOS and storage-failure degradation, then take the same
   candidate through outage/reboot recovery and independent-power field work.

`LOC-021T0/T1` are scoped persistence/recovery work. They do not block an
isolated S smoke or a separately bounded single-source live slice. The original
concurrent T1 guarantees are not waived by renaming the slice.

## Highest-priority risks

- Positive HTTP/ACK counters are not proof of a usable position or human notice.
- Location local state must not silently freeze when outbound persistence is full.
- SOS input recognition and attempted help require an explicit degraded path
  when storage fails; a stored/received claim still requires its real evidence.
- Data and command sharing of one modem needs a measured mode/ownership design.
- Power, antenna/enclosure and Guardian locked-screen reachability require
  early experiments; they cannot wait for every software submodule to finish.

## Scope conflicts and unavailable context

The uploaded `AGENTS.md` applies only to `docs/`. The uploaded
`EGO_MASTER_CONTEXT.md` describes an early desktop HDMI/HID Ego project and is
not the revised 2026-08-14 EgoLink master mentioned by the status history.
Do not apply its board/model/cloud constraints to EgoLink by filename alone.
Read the real product charter, NORTH_STAR, FIRST_LAUNCH_EXECUTION, relevant
ADRs, BOARD_MATRIX and root/module AGENTS before merging behavioral changes.
Final display/form factor, production BOM, costs and sale date are not frozen
by this review. Existing AMOLED use does not settle the production display.

## Evidence and execution

Physical image identities are in [ACTIVE_BUILD.md](ACTIVE_BUILD.md).
Stages are in [ROADMAP_EGOLINK_P0.md](ROADMAP_EGOLINK_P0.md).
The working queue is [TASK_TREE.md](../tasks/TASK_TREE.md).
Detailed original history is preserved in the
[input archive](../archive/reviews/20260905_input_snapshots/README.md).

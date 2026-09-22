---
document_status: accepted_decision
decision_updated: 2026-09-05
reviewed_at: 2026-09-05
authority_basis: founder_authorized_runtime_convergence
implementation_status: in_progress
---
# ADR-0014: Runtime Convergence With Scoped Safety Invariants

- Status: accepted
- Date: 2026-09-05
- Decision owner: founder
- Scope: runnable Location/CALL/SOS integration order, local degradation and recovery

## Subsequent decision — 2026-09-22

[ADR-0016](ADR-0016-local-first-ego-state-cellular-primary.md) records the founder's 2026-09-19 decision and
2026-09-22 migration instruction. It partially supersedes RTC-primary/native-
reserve wording, defers no longer the minimal private Base endpoint, and admits
bounded rule-state truth work. Three P0 Gate names, evidence obligations,
local safety, source time, exact ACK and the current single-board field scope
remain; CALL-020/021 and full SOS are not automatically resumed. The text
below is the original dated decision, not a new current-state report.

## Context and evidence boundary

The founder explicitly directed implementation of the 2026-09-05 review in the
real worktree. Reconciliation started at HEAD
`72c7a1ed199fa6bc522defff0d77a0aa3e77034d` on
`a0/first-real-field-session`; ADR-0014 was unused. All six source snapshots,
five replacement candidates and two additions match their manifest hashes.
The five target files match the uploaded bases, but the uploaded desktop
HDMI/HID Master Context differs from the current EgoLink v2.2 product authority
and is retained solely as history. Root AGENTS is unchanged.

The 2026-09-04 repository documents report LOC-021 A-S, CALL-020 A-R and
1614 passing tests / 12 skips, with all product Gates NOT_RUN. Those are dated
prior results; this decision records no new source-test/build/hardware/network
verification. Physical node evidence remains with ACTIVE_BUILD and BOARD_MATRIX.
The decision is accepted; its individual runtime behaviors remain subject to
implementation, executable regression and appropriately authorized evidence.

Original bytes and the semantic migration map are preserved in the
[input archive](../../archive/reviews/20260905_input_snapshots/README.md).

## Decision 1 — retain the product, change the development unit

First launch remains Reliable Location + LTE-data Ego Call + physical SOS.
Deliver a runnable vertical behavior with its failure path and measured outcome.
One complete capability has greater scheduling priority than additional dormant
abstractions. Keep each patch small enough to review; it must name the next
executable consumer, not merely a future adapter.

Component tests, bench validation, field validation and product acceptance
remain distinct. Default-off protects general builds; an explicitly selected
engineering profile must execute the intended function after its run conditions
are satisfied. Production gates and irreversible operations remain protected.

USB/PC use is permitted for diagnosis and intermediate media proof. A final
PC-free product path still requires its own measured acceptance.

## Decision 2 — local operational state and durable delivery have different jobs

Preserve original observation identity and exact bytes for durable event retry.
Separate current in-memory Location state, persisted recovery state, pending
outbound state and server-confirmed state. Give each an explicit version/status.

A full outbound queue or a storage error must not silently stop local aging,
new observations, SOS policy or feedback. The implementation must expose
persistence/delivery degradation and preserve the last durable checkpoint.
Normal accepted durable events continue to obey write-before-send and strict
matching ACK semantics; never mark an uncommitted event as durable.

This explicitly replaces LOC-021J's universal write-before-local-state-commit
interpretation for the selected bounded runtime. Existing durable delivery
identity, exact payload bytes and server contracts remain intact; shared
contract changes require integrator review and additive compatibility tests.
The code must expose local advancement and failed persistence separately.

## Decision 3 — event-time correctness without an unbounded global wait

Continue asynchronous independent acquisition. Preserve source timestamp,
clock domain, boot identity, per-source sequence and provenance. Never replace
source occurrence time with network receive time.

A live safety controller processes bounded inputs and timers promptly. It does
not wait for every sensor lane to advance a watermark. Record the admitted
processing order separately from source event time. Late observations retain
their real age; apply an explicit stale/late policy and do not overwrite a
newer authoritative current state with a delayed old record.

Use a shared boot-monotonic clock when available. If source clocks cannot be
compared, record uncertainty rather than inventing a strict total order.
A live bounded-lateness policy and an offline chronological analysis may give
different results; label the replay mode and preserve the real live decision.

A compact checkpoint plus pending critical events is an admissible alternative
to a universal sensor WAL. Define the supported recovery model before choosing.
Critical input durability, stable event identity, ACK settlement and prevention
of unintended duplicate effects remain mandatory for the claimed behavior.
Do not write every raw IMU sample to the critical outbox.

## Decision 4 — recovery must not resurrect or suppress the wrong effect

Distinguish historical analysis from service recovery. Historical replay performs
no physical output or new call. Service recovery resumes still-pending authorized
alerts via the delivery dispatcher with stable identity and deduplication.
An already settled alert must not become pending after reboot. An expired or
explicitly ended call must not reopen merely because its old input is replayed.
The same user event, service receipt, terminal notice and human acknowledgement
are separate states. Never equate them.

Keep server deduplication at least as long as the supported device retry/replay
window; deletion/compaction and retry expiration must agree. Exact settlement
records may be compacted only after their bounded resurrection risk is closed.
Do not add an infinite tombstone history by default.

## Decision 5 — SOS remains useful when one dependency fails

Acknowledge the recognized qualified button input immediately using an honest
local signal. That signal means input recognized, not stored or received.
Attempt the critical journal promptly, reserve resources, and then attempt
alert delivery, urgent Location and authorized contact independently.

On storage failure, show storage degradation and take the explicitly designed
best-effort help path if identity, authorization and secure transport are still
valid. This path makes no durability/reboot guarantee and is counted as a
reliability failure. It must not bypass authentication, privacy controls or TLS.
If credentials/identity are unusable, provide local failure feedback and avoid
unsafe external actions. A privacy hardware switch retains its authority.

No fresh GNSS fix, historical sensor replay, model inference or HTTP-owner lock
may delay recognition of a physical SOS. Long-press qualification/debounce
still applies; this decision does not turn every raw edge into an emergency.
Normal persistence ordering and every degraded branch need explicit tests.

## Decision 6 — one modem owner, concrete bearer and measured migration

Keep one physical modem/transport owner and bounded cancellation. A new IP
bearer cannot be added as a second independent AT caller. For command and data
coexistence choose an exact supported mode/interface for the actual board.

Finish the existing thin CALL proof while evaluating the shortest embedded
route. Prefer a maintained media stack over growing a custom transport stack
without a demonstrated need. External SDK support is a candidate, never proof
that SIM7670G, this board or the final product works. Pin dependencies and review
licenses and board configuration before adoption.

A TLS socket alone is not a complete Guardian calling product. Prove signaling,
media compatibility, two acoustic directions, authorization, cancellation and
user-visible call state. A verified PC LTE route proves only that fixture.

## Decision 7 — correct meaning of position and safety confidence

Preserve `location_belief` and honest source/age/uncertainty. A last trusted point
can remain visible as historical evidence even when current location is Unknown.
Do not force a fresh location by perpetually relabelling an old point Predicted.
A Cell fingerprint alone is not a new global coordinate. Motion alone does not
supply an absolute geographic anchor.

Separate receiver fix validity, quality-field availability and estimated
reliability. Review whether mandatory positive HDOP improperly discards usable
fix observations; preserve an incomplete-quality candidate without calling it
high-confidence. Validate the selected receiver format and coordinate parser.

L2 experiments compare against simple last-trusted/age/motion/source baselines
on consented real sessions split by route/session, with calibration and energy
metrics. Model predictions cannot veto or delay manual SOS.

## Decision 8 — development authority and review levels

Routine offline work under the assigned packet does not need per-command
founder confirmation. Use one integrator and at most two builders on disjoint
paths; external models receive only the minimal permitted non-secret context.
Review behavioral invariants, not the amount of documentation or test count.

An authorized experiment scope can cover a bounded sequence of build/flash/run/
restore actions, with exact devices, target endpoints, participant permission,
maximum attempts, traffic/capture/storage limits, stop rules and recovery image.
No scope is inferred from this ADR. Do not weaken encryption or add credentials
merely to make a live test pass. eFuse changes, destructive erase, purchases and
non-test notifications remain separately controlled.

## Supersession and validation

ADR-0012 section 6 is refined only where it postpones recognized-input feedback
until storage succeeds: recognized input, durable recording and remote outcomes
are separate facts. ADR-0011 deterministic safety and ADR-0010 source-event
lineage and Store-and-Forward remain accepted. ADR-0013 stays proposed; this
decision does not silently approve its USB control/media architecture.

T0/T1 do not block isolated S smoke or a bounded current-boot/single-source live
profile. The existing concurrent SOS/IMU product bridge and reboot-equivalence
promises remain blocked until their original WAL/checkpoint/tombstone/no-output
replay guarantees or an explicitly reviewed, behaviorally proven equivalent
are present. No current task silently waives those guarantees.

Scoped replacements: the global priority of T0/T1 before bounded live evidence;
universal write-before-local-state-commit; delaying all input feedback until
persistence; interpreting USB-Free as a ban on bench diagnosis; treating each
new offline wrapper as a delivered increment.

Retained: product gates, source lineage, privacy/consent, strict authenticated
ACK, critical durability, deterministic safety, exact hardware identity,
rollback and historical evidence. No whole prior ADR is erased.

Before activating affected paths, run source review plus executable regression
for queue-full/location progress, storage-failure SOS, late input, reboot/event
identity, lost ACK, settled-event recovery, call teardown and concurrent modem
ownership. Use physical fault tests for claims about physical persistence.

## Current execution

The first implementation is
[P0-CONVERGENCE-20260905](../../tasks/active/P0-CONVERGENCE-20260905.md):
reuse LOC-021 A-S for real Location -> authenticated secure transport -> bound
Guardian, advance concrete bidirectional CALL and embedded-bearer evidence in
parallel, then connect physical SOS and scoped recovery. Build/native tests,
hardware, network, field and product Gates are reported separately. An unused
fake transport callback does not complete code delivery.

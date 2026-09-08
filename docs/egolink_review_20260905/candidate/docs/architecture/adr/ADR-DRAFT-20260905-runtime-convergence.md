---
document_status: proposed_decision
reviewed_at: 2026-09-05
authority_basis: founder_delegated_project_review_and_revision
implementation_status: not_applied_to_repository
---
# ADR candidate — Runtime convergence with scoped safety invariants

## Context and evidence boundary

The 2026-09-04 input documents report LOC-021 A-S, CALL-020 A-R and
1614 passing tests / 12 skips, with all product gates NOT_RUN. The new paths
remain offline. Physical nodes retain FW-007 and UI-001. This is a document
review, not an independent source/build/hardware audit.

The source snapshots are preserved in the
[input archive](../../archive/reviews/20260905_input_snapshots/README.md).
Merge this decision under an available ADR number after reading the real root
instructions, router, product charter and active architecture decisions.
Do not assume ADR-0014 or another number is unused.

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

This changes the interpretation of LOC-021J only through a reviewed code and
contract migration. First inspect whether existing paths already isolate this
risk. Do not label an uninspected implementation as defective.

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

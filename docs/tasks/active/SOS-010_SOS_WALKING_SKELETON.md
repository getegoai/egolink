---
id: SOS-010
title: Physical SOS walking skeleton
status: active
priority: critical
lane: B
execution_state: in_progress
depends_on:
  - LOC-021
  - CALL-021
  - OUTBOX-010
serves_gate: P0-SOS
requires_hardware: true
created: 2026-08-23
last_updated: 2026-09-05

context:
  - docs/architecture/adr/ADR-0014-runtime-convergence.md
  - docs/tasks/active/P0-CONVERGENCE-20260905.md
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/safety/SAFETY_CONTRACT.md
  - docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md
  - docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md
  - docs/tasks/active/CALL-021_EMBEDDED_LTE_RTC_MEDIA.md
  - docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md

allowed_paths:
  - docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md
  - firmware/mqtt_heartbeat/components/sos_input/
  - firmware/mqtt_heartbeat/components/sos_orchestrator/
  - firmware/mqtt_heartbeat/components/sos_outbox_adapter/
  - firmware/mqtt_heartbeat/components/sos_device_runtime/
  - firmware/mqtt_heartbeat/components/sos_pending_edge_journal/
  - firmware/mqtt_heartbeat/components/sos_pending_edge_journal_nvs/
  - firmware/mqtt_heartbeat/components/sos_delivery_composition/
  - pc_simulator/sos_walking_skeleton.py
  - shared/contracts/safety_event.schema.json
  - quality_tests/test_sos_input_firmware.py
  - quality_tests/test_sos_orchestrator_firmware.py
  - quality_tests/test_sos_outbox_adapter.py
  - quality_tests/test_sos_device_runtime.py
  - quality_tests/test_sos_pending_edge_journal.py
  - quality_tests/test_sos_pending_edge_journal_nvs.py
  - quality_tests/test_sos_delivery_composition.py
  - quality_tests/test_sos_walking_skeleton.py
  - server/manual_sos_store.py
  - server/manual_sos_delivery_ack.py
  - server/message_hub.py
  - server/guardian_location_page.py
  - quality_tests/test_manual_sos_store.py
  - quality_tests/test_manual_sos_delivery_ack.py
  - quality_tests/test_message_hub_server.py
  - quality_tests/test_message_hub_dashboard.py
  - docs/operations/VPS_RUNBOOK.md

out_of_scope:
  - inventing another SOS/safety-event contract
  - camera AI, anomaly models, emergency dispatch, PSTN or SMS
  - edits to firmware outside the isolated SOS components, server, or existing
    LOC/CALL/outbox seams; the only shared-contract edit allowed is making
    `safety_event.context.battery_percent` nullable
  - physical SOS or P0-SOS acceptance claims from component/host-only evidence
---

# Current Runtime Migration (2026-09-05)

[ADR-0014](../../architecture/adr/ADR-0014-runtime-convergence.md) refines the
old enqueue-before-all-feedback interpretation. A qualified physical edge
immediately receives honest input-recognition feedback, distinct from durable
recording, server receipt, terminal notice and human acknowledgement. Attempt
the critical journal promptly; failed storage or queue saturation must expose
degradation and preserve an explicit bounded local/best-effort help policy.
It cannot disable recognition, local Location/SOS policy or independently
permitted contact. No degraded path bypasses identity, authorization or TLS;
no failed write is represented as durable.

Pending-event recovery preserves original event identity and strict ACK
settlement. Replay for analysis performs no physical/call action; service
recovery resumes only still-pending authorized delivery and never reopens an
expired or explicitly ended call. Prior at-least-once callback behavior must
be migrated with executable tests before activation; historical test/build
results below do not validate this changed behavior.

The integrator owns shared LOC/CALL/outbox seams through
[P0-CONVERGENCE-20260905](P0-CONVERGENCE-20260905.md). Physical integration
follows the real Location and CALL paths; retained concurrent T0/T1/recovery
promises remain in force. This task grants no physical input, flash, SIM,
recording or external-notification authorization. `P0-SOS=NOT_RUN`.

# Goal

Compose the existing physical-button safety event, Location Engine/Sensor
Policy, persistent priority outbox, Guardian alert and Ego Call into one honest
product loop.

# Acceptance

- [ ] Qualified long press immediately signals recognized input, separately
      attempts durable recording and exposes storage failure before any
      stored/delivered claim; independent local help remains explicit. Healthy
      storage must durably retain the original event; a failed write cannot
      pass durability acceptance.
- [ ] Last trusted belief uploads immediately; GNSS/LTE enter SOS policy.
- [ ] Guardian sees device, belief age/confidence/uncertainty, battery and
      independent alert/call state; Ego Call is requested immediately.
- [ ] Offline/reboot evidence proves queued replay and idempotent exact ACK
      deletion without re-triggering an expired or explicitly ended call.
- [ ] Camera and AI cannot veto or fabricate success.

# Dispatch Boundary

The former blanket requirement to wait until LOC-021, CALL-021 and OUTBOX-010
were all accepted before writing any code was too strict for parallel delivery.
An isolated host composition may proceed now against their frozen contracts and
public seams, without editing those dependency modules. The three dependencies
remain hard gates for physical integration: this slice is not permission to
edit shared firmware/server paths or to claim physical SOS/P0-SOS acceptance.

The SOS-010A host slice is limited exactly to its two implementation/test files
in `allowed_paths`. It uses a temporary host outbox, synthetic button
observations and the existing deterministic Ego Call fixture. It performs no
network, serial, hardware, audio or media operation and exports no precise
coordinate.

## SOS-010B Device Input Ownership (2026-09-02)

The dispatched SOS-010B slice owns only the new transport-free
`firmware/mqtt_heartbeat/components/sos_input/` component,
`quality_tests/test_sos_input_firmware.py`, and this packet. It provides a
GPIO-independent physical-button state machine with bounded configurable
debounce and long-press timing. A valid long press emits one edge, and only a
debounced release re-arms the next edge. Startup-held input, bounce, monotonic
time rollback/wrap and near-`UINT64_MAX` elapsed-time arithmetic fail or settle
explicitly; battery state is intentionally absent from the decision API so low
battery cannot veto a physical SOS edge.

The engineering defaults are `50 ms` debounce and `2000 ms` hold, matching the
SOS-010A host replay seam. The stable-press and trigger times are reconstructed
as exact checked deadlines (`candidate + debounce`, then `stable + hold`) so a
sparse caller does not shift the event clock. Deadline overflow and time
rollback/wrap latch an explicit fault instead of wrapping arithmetic.

This slice does not edit or bind `app_main`, a pin assignment, transport, LOC,
CALL or outbox code. It does not persist or deliver the emitted edge and cannot
claim local durable recording, Guardian delivery, Ego Call, physical-button
evidence or `P0-SOS` acceptance.

## SOS-010C Offline Device Orchestration Ownership (2026-09-02)

This build-only slice owns exactly:

- `docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md`;
- new `firmware/mqtt_heartbeat/components/sos_orchestrator/` files;
- new `quality_tests/test_sos_orchestrator_firmware.py`;
- `shared/contracts/safety_event.schema.json` only for the backward-compatible
  nullable `context.battery_percent` relaxation; and
- `pc_simulator/sos_walking_skeleton.py` plus
  `quality_tests/test_sos_walking_skeleton.py` only for matching unknown-
  battery runtime/schema coverage.

It must not modify or bind `app_main`, GPIO, transport, server, audio, the
existing SOS input/outbox/location-policy implementations, or any CALL/LOC
component. The new component consumes a qualified `sos_input` edge and uses
injected, synchronous seams only. It first attempts a CRITICAL coordinate-free
`manual_sos` outbox enqueue, then independently attempts local feedback,
Location Policy SOS activation, an urgent last-trusted/current-location
request, and an Ego Call request. Persistence or policy failure remains
explicit but cannot suppress later best-effort branches. Camera, AI and low
battery have no veto input or branch.

The deterministic event ID is derived only from immutable physical-edge
lineage: device/boot/session scope in the outbox identity plus boot count,
source sequence and exact reconstructed edge time in the event ID. Replaying
that complete immutable input reaches outbox duplicate/conflict handling
without inventing another durable event. Every distinct physical edge has a
different edge time and/or source sequence and retriggers the location/call
seams even if Location Policy is already in SOS. Callback requests reuse the
safety event ID as their idempotency key; this is bounded at-least-once
orchestration, not exactly-once remote execution.

Unknown battery is represented as JSON `null`. The former schema/runtime rule
requiring a numeric percentage was unsafe because an unavailable gauge forced
the caller either to reject a physical SOS or fabricate a measurement. Known
finite values remain constrained to `[0, 100]`; battery state never gates the
manual SOS path.

Focused/build-only validation for this slice:

```powershell
python -m unittest quality_tests.test_sos_orchestrator_firmware -v
python -m unittest quality_tests.test_sos_input_firmware quality_tests.test_sos_walking_skeleton -v
python -m unittest quality_tests.test_persistent_priority_outbox_device_core quality_tests.test_location_policy_core_firmware -v
python -m unittest quality_tests.model_contract.test_contract_schemas quality_tests.model_contract.test_contracts -v
python scripts/context_lint.py
```

The final static gate also uses an ESP-IDF v5.4.2 ESP32-S3 build with the new
component's local warnings-as-errors enabled. It does not flash or execute the
component and cannot establish physical-button, flash, network, audio,
Guardian, reboot/outage, call or `P0-SOS` evidence.

## SOS-010D Server Durable Ingest And Guardian Surface Ownership (2026-09-02)

This loopback-only slice owns exactly the four server files, four focused or
existing quality-test files and VPS runbook entry added to `allowed_paths`
above, plus this packet. It must preserve the just-landed LOC-021I Guardian
device-binding/location behavior. It may add one manual-SOS ingest route, one
durable SQLite SOS timeline/current store, the existing outbox positive-ACK
shape for durable server receipt, a bound Guardian latest-alert query, and an
independent idempotent Guardian manual-acknowledgement seam. It must not alter
the shared safety-event schema, create a second event contract, deploy, contact
the VPS, or touch firmware/device/network/hardware.

The ingest boundary accepts only the strict coordinate-free `manual_sos`,
`critical`, `device_rule` subset already defined by
`shared/contracts/safety_event.schema.json`. It is protected by the existing
device-ingest bearer-token boundary and must reject oversized/non-JSON bodies,
duplicate JSON keys, non-finite values, unsafe identities, inconsistent
boot-monotonic lineage and values outside SQLite signed-64-bit bounds before
mutation. The store hashes and durably retains the exact raw request bytes.
The same device/event/exact bytes are an idempotent duplicate; any identity
collision with different bytes fails closed and cannot replace `current`.

Only a transactionally durable accepted/duplicate result may return the
outbox ACK contract: `ack_id=ack-<payload_sha256>`, exact body `event_id`,
`device_id` and raw-body SHA-256, with
`scope=server_durable_ingest_only`. HTTP success and this ACK do not mean a
Guardian saw or acknowledged the event, that a push notification ran, or that
Ego Call connected. Guardian read and acknowledgement routes require a
Guardian bearer token authorizer and an exact device binding; absence of that
authorizer fails with service unavailable and must never fall back to the
global device-ingest token.

The Guardian projection is deliberately bounded metadata: identity/type,
battery if known, server receipt/delivery state, an independent
`guardian_ack_state`, and `call_state=not_reported`. It never returns the raw
body, coordinates or media. Any optional page rendering uses `textContent` and
keeps bearer credentials out of URLs, Web Storage and logs. All successful and
error responses are `no-store`. Manual Guardian acknowledgement is a separate
durable idempotent record and cannot delete the device outbox, rewrite the
server-ingest ACK, or fabricate call state.

The event's `privacy.retention_seconds=86400` is accepted as source metadata,
not an implemented deletion guarantee. This slice has no expiry worker,
backup-propagated deletion or verified erasure path. Enforced retention,
authorized erasure and at-rest encryption/key lifecycle therefore remain
pre-production privacy blockers.

Validation is local/loopback only and includes the new focused store/HTTP
tests plus all existing Guardian/location/message-hub regressions. This slice
cannot claim push delivery, call signaling, a device sender/ACK parser,
physical operation or `P0-SOS` acceptance.

## SOS-010E Offline Device Delivery Adapter Ownership (2026-09-02)

This build-only slice owns only the new
`firmware/mqtt_heartbeat/components/sos_outbox_adapter/` component,
`quality_tests/test_sos_outbox_adapter.py`, and this packet. The existing
orchestrator already writes its generated exact `manual_sos` payload once as a
CRITICAL record through the injected outbox, so this adapter must not enqueue
a second copy or change the orchestrator public contract. It binds the same
already-initialized outbox, selects its next due record through the outbox
attempt API, and exposes a borrowed, bounded send view only when that record is
the expected CRITICAL `manual_sos` shape. A non-SOS head is reported explicitly
and never interpreted as SOS.

For a caller-confirmed successful HTTP result, completion first parses and
matches the response without mutating the outbox. It accepts only the bounded
SOS-010D response with `ok=true`, `result.status=accepted|duplicate`, exact
`server_durable_ingest_only` scope, and the exact seven-member positive outbox
ACK. Device ID, event ID and exact transmitted-payload SHA-256 must all match
the active send view; `ack_id` must equal `ack-<payload_sha256>`. Only then may
the adapter durably record transport acceptance and call the outbox positive-
ACK handler. HTTP success alone, malformed or truncated JSON, duplicate keys,
escaped identity strings, missing/extra members, negative semantics or any
identity/hash conflict is durably classified as a failed attempt and retained
in `RETRY_WAIT`.

The adapter is lock-free and default-unwired. Exactly one caller must
serialize orchestrator enqueue, begin/send/finish and every other API call on
the shared outbox; it must finish or explicitly record failure for the active
attempt before beginning another. The send view borrows caller-owned
`egolink_outbox_send_item_t` memory and becomes invalid when that memory is
cleared or reused. This slice adds no transport, URL, token, TLS, task,
`app_main`, storage backend or hardware behavior and performs no network or
device operation.

The selected payload is bounded-parsed against the existing orchestrator
subset before any send view is exposed: device/event/boot/session/sequence/time,
manual type, critical priority, device-rule source, null-media evidence and
privacy flags must match the outbox record and adapter identity. This cJSON
boundary deliberately admits only JSON-safe integer lineage; a larger device
integer remains retained rather than being rounded. A failed positive-ACK
storage commit leaves the active view and exact send item intact. However, the
current outbox core latches any slot-write failure, so same-instance retry is
not available after that storage fault; the caller must reinitialize from the
last valid mirror and start a new attempt. On reboot, an intact
`AWAITING_POSITIVE_ACK` record is immediately due under the new runtime epoch.
Changing the core fault-recovery contract is outside this slice.

## SOS-010F Device Runtime Composition Ownership (2026-09-02)

This offline/build-only slice owns only the new
`firmware/mqtt_heartbeat/components/sos_device_runtime/` component,
`quality_tests/test_sos_device_runtime.py`, and this packet. It composes the
existing SOS input and orchestrator while borrowing the shared already-
initialized outbox and the caller's one already-bound SOS delivery adapter.
It never creates, binds or drives a second adapter. Its sample API accepts only
an injected raw pressed level and boot-monotonic time. It owns no GPIO, task,
transport, network, storage backend or hardware driver and remains disabled in
the default configuration and unwired from `app_main`.

The runtime preserves the orchestrator's fixed downstream safety order. With
G's prerequisite journal step described below, a qualified edge is first made
recoverable, then reaches the CRITICAL outbox enqueue attempt, local feedback,
Location Policy SOS activation, a uniquely identified callback request for
last-trusted/current urgent location work, and Ego Call. Sender wake is a
separate final callback. Each downstream branch result remains independent;
outbox, LOC, Call or wake failure cannot roll back a journaled/committed event
or veto the other best-effort branches. Battery is represented as unknown and
no low-battery, camera or AI input exists at this boundary.

The current LOC APIs do not expose a safe way for this component to construct
a durable, unique SOS location observation. It therefore emits only the
existing coordinate-free urgent location request with the manual-SOS event
identity; the serialized external owner must resolve last-trusted/current
state and create any LOC observation. This component neither fabricates a LOC
identity nor claims a location upload occurred.

Input, orchestrator, policy, outbox, dispatcher delivery/ACK and runtime
cancel/close are lock-free and must all be serialized by the same external
task or mutex. A local busy flag only rejects recursive callback entry. The
composition root order is: initialize the shared outbox, bind exactly one SOS
adapter to it, initialize the single outbox dispatcher with that adapter, then
initialize this runtime with the same outbox/adapter/device identity. The
dispatcher is the only send/finish/ACK owner. Runtime cancel and close merely
clear their borrowed references; they never bind/unbind the adapter, settle an
active dispatcher attempt, call outbox deinit/positive ACK, or delete queued
records. A dispatcher-owned active attempt remains untouched and independently
recoverable after this button runtime closes.

Before SOS-010G, a qualified edge consumed its volatile source sequence after
the orchestration attempt. If the CRITICAL outbox enqueue or storage commit
failed, the returned partial result was observable but F had no persistent
pending-edge journal or retry API. The G slice below replaces that unsafe
volatile-only boundary; the historical F evidence alone remains insufficient
for physical/reboot claims.

## SOS-010G Pending Edge Journal And Replay Ownership (2026-09-02)

This offline/build-only slice owns only the new
`firmware/mqtt_heartbeat/components/sos_pending_edge_journal/` component,
the existing `sos_device_runtime` component, their two focused tests and this
packet. It may add a minimal source-clock replay flag to the existing
orchestrator context because an old boot-monotonic edge can be later than the
new boot's `now_ms`; the flag is not serialized and cannot change identity.
It must not otherwise change the orchestrator, input, outbox, dispatcher or
public safety-event contract. It remains unwired from `app_main` and provides no
GPIO, task, NVS/partition adapter, network, transport or hardware behavior.

The journal stores one fixed, versioned, pointer-free physical-edge lineage
record through caller-owned synchronous load/store/clear callbacks. A storage
callback may report success only after an atomic durable replacement. The
record's integrity check detects accidental corruption and torn bytes; it is
not authenticity, at-rest confidentiality, wear management or proof of a
particular flash backend. Exact backend power-loss and erase behavior remain
integration work.

For a newly qualified edge, F must durably store that exact boot/session/
sequence/edge-time lineage before it invokes the existing orchestrator. It may
clear the journal only after the manual-SOS outbox enqueue returns committed or
an exact duplicate. A failed enqueue or failed/ambiguous clear keeps recovery
explicit. Startup recovery reuses the exact stored lineage so outbox duplicate
handling is the idempotency boundary; it never creates a second delivery
adapter and does not take send/finish/ACK ownership from the single dispatcher.

The exact v1 wire image is 320 bytes: explicit little-endian header/version/
lengths and three JSON-safe boot-monotonic integers, two canonical fixed ASCII
identity fields, reserved-zero bytes and a trailing CRC32. The decoder requires
all unused identity padding and reserved bytes to be zero, so there is one
canonical encoding. CRC32 detects accidental/torn bytes but is not an
authenticator. Store and clear callbacks are treated as ambiguous on error;
bounded readback decides whether the exact record or durable absence actually
committed. A different valid record is `OCCUPIED` and is never overwritten or
cleared. Journal init binds callbacks only and performs no load, store, clear
or erase.

F now binds exactly one already-initialized journal for the same device. A new
qualified edge is placed there and read back before its source sequence is
consumed or the orchestrator is invoked. A journal-store failure leaves the
candidate in volatile RAM, invokes no F branch, blocks every later input sample
and prevents cancel/close; `replay_pending` can retry after storage recovers.
If power is lost while the backend still cannot make any valid record durable,
the physical edge remains unrecoverable; this seam cannot defeat failed media.
A successfully journaled edge still attempts feedback, policy, LOC intent,
Call and sender wake independently even if the outbox enqueue fails.

Only `COMMITTED` or exact outbox `DUPLICATE` permits compare-before-clear. A
failed clear leaves the record replayable; replay reconstructs the identical
event ID and all callbacks are deliberately at-least-once under that same
idempotency key. While the single record is pending, a second physical edge is
not admitted. This bounded fail-closed capacity is not product sizing and must
be revisited with the physical input/backend composition.

Runtime init accepts a pending edge from an earlier boot/session for the same
device and does not let it advance the new boot's source sequence. A pending
edge in the current boot/session advances `next_source_sequence` past its
already-consumed sequence, including explicit max-sequence exhaustion. A
future-boot record or different session within the current boot fails closed.
Recovered event identity and source time remain exact, while the outbox retry
clock and Location Policy action use the current runtime `now_ms`; an old boot
clock cannot poison the new boot's monotonic state. The minimal orchestrator
flag enabling this distinction is trusted-runtime-only, not serialized, and
is unreachable through F without a journal-loaded or just-stored record.

This slice still supplies no real NVS/raw-partition backend, boot counter,
wear/endurance policy, encryption/key lifecycle, erase/privacy proof, task or
GPIO binding. It does not execute target C on a CPU or simulate flash power
loss. Therefore it is replay-seam/build evidence, not hardware reboot,
physical-button or `P0-SOS` acceptance evidence.

## SOS-010H Build-only NVS Pending-edge Backend Ownership (2026-09-02)

This build-only slice owns only the new
`firmware/mqtt_heartbeat/components/sos_pending_edge_journal_nvs/` component,
`quality_tests/test_sos_pending_edge_journal_nvs.py`, and this packet. It
adapts the G journal's existing synchronous load/store/clear callbacks to the
fixed ESP-IDF NVS partition label `nvs`, namespace `ego_sos_pend`, and key
`edge_v1`. It does not change the journal/runtime contracts, connect
`app_main`, create a task, initialize or erase NVS, format a partition, or
perform any automatic I/O.

Adapter initialization only creates caller-owned RAM state and callback
bindings. The composition root remains responsible for successfully
initializing the named NVS partition before any callback. Load opens the
namespace read-only and treats an absent namespace or key as `NOT_FOUND`.
Store is the only operation allowed to create the namespace: it opens
read-write, accepts exactly the G core's 320-byte record, calls
`nvs_set_blob` then `nvs_commit`, and closes the handle on every opened path.
Clear first checks existence read-only so an empty device is not mutated; it
then uses `nvs_erase_key` plus `nvs_commit` and closes both handles. All other
NVS/argument/size failures map to the journal's storage error, while commit
failures remain deliberately ambiguous for G's exact readback logic.

The adapter and G/F/outbox/dispatcher remain lock-free at the composition
boundary and require one external owner task or mutex. RAM-only saturating
operation/handle/byte/error counters contain no payload or identity and reset
at adapter initialization. This slice has no payload logging and makes no
claim that NVS commits are brownout-atomic, endurance-qualified, encrypted or
securely erased. The current default application's existing NVS init-and-
conditional-erase ownership must be reviewed before later wiring because this
slice neither invokes nor changes it.

Focused/build validation for this slice:

```powershell
python -m unittest quality_tests.test_sos_pending_edge_journal_nvs -v
python -m unittest quality_tests.test_sos_pending_edge_journal quality_tests.test_sos_device_runtime -v
python scripts/context_lint.py
git diff --check -- docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md firmware/mqtt_heartbeat/components/sos_pending_edge_journal_nvs quality_tests/test_sos_pending_edge_journal_nvs.py
```

The final compile gate is a clean dedicated ESP-IDF v5.4.2 ESP32-S3 build
with the component's local warnings-as-errors flags. It may compile/link only;
it must not flash, open COM, access a board, or be reported as NVS runtime,
power-loss, reboot or `P0-SOS` evidence.

## SOS-010I Offline Delivery Composition Ownership (2026-09-02)

This offline/build-only slice owns only the new
`firmware/mqtt_heartbeat/components/sos_delivery_composition/` component,
`quality_tests/test_sos_delivery_composition.py`, and this packet. It composes
the already-frozen E/F/G delivery and pending-edge seams with the single P0
outbox dispatcher and delivery runtime. It remains disabled by default and is
not referenced by `app_main`.

The caller retains ownership of the already-initialized shared outbox,
Location outbox adapter bound to that exact outbox and device, initialized
Location Policy core, pending-edge storage callbacks, and synchronous HTTP
callback. Enabled initialization validates those identities, then owns exactly
one SOS adapter, one pending journal, one dispatcher, one P0 delivery runtime,
and one SOS device runtime. Initialization is staged in that order; failures
close completed stages in reverse without deinitializing, erasing, closing or
otherwise mutating caller-owned dependencies. If reverse settlement cannot be
proved safe, the composition stays present in explicit recovery state rather
than pretending initialization failed cleanly.

All APIs are lock-free and serialize-only: one external task or mutex must own
sample, pending replay, outbox producer work, delivery drive/recovery, status,
cancel and close. The internal sender-wake callback only sets a bounded RAM
intent and saturating counter. It never recursively selects, sends or calls the
HTTP callback from the SOS orchestration stack. After sample or replay, that
same external owner must explicitly call `drive_once`; one call performs at
most one send or one already-required recovery settlement. CRITICAL manual SOS
priority is supplied by the existing outbox selector and cannot be bypassed by
a location head.

This is a serialized composition reference, not the final device scheduling
topology. Its synchronous `drive_once -> HTTP callback` path must not run on
the physical safety-input or Ego Call task, and integration must not retain the
single-owner mutex across blocking HTTP in a way that prevents those paths from
running. In particular, I does not prove SOS latency or preemption while a
Location POST is already in flight. A bounded immutable payload snapshot,
independent sender execution context, and reviewed urgent cancellation or
preemption policy are mandatory next P0 runtime work; this slice deliberately
does not add an unreviewed task or lock.

Cancel and close never clear a pending-edge journal or delete a queued event.
They must first preserve/settle any dispatcher-owned attempt through the
existing delivery contracts. A volatile store-failed edge, ambiguous
dispatcher settlement, or other recovery state rejects safe shutdown and
retains the composition object for explicit replay/recovery. Successful close
unbinds only the SOS adapter owned here; it does not deinitialize the caller's
outbox, Location adapter, policy core, storage backend or HTTP owner.
An initialization rollback that cannot close an owned delivery stage remains
in an explicit rollback-recovery lifecycle with every lower binding retained;
`drive_once` cannot start a send there. A later serialized `close` or `cancel`
may retry at most one required begin/finish settlement and the remaining owned
stage cleanup, releasing the adapter/journal only after cleanup succeeds.

Focused/build validation for this slice:

```powershell
python -m unittest quality_tests.test_sos_delivery_composition -v
python -m unittest quality_tests.test_sos_delivery_composition quality_tests.test_p0_delivery_runtime quality_tests.test_p0_outbox_dispatcher quality_tests.test_sos_device_runtime quality_tests.test_sos_pending_edge_journal quality_tests.test_sos_outbox_adapter -v
python scripts/context_lint.py
git diff --check -- docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md firmware/mqtt_heartbeat/components/sos_delivery_composition quality_tests/test_sos_delivery_composition.py
```

The final compile gate is a clean dedicated ESP-IDF v5.4.2 ESP32-S3 build
with the new component's local warnings-as-errors flags. It compiles and links
only; it must not flash, open COM, initialize NVS, access a network or board, or
be reported as a physical SOS, Guardian, Call or `P0-SOS` result.

# Validation Commands

```powershell
python -m unittest quality_tests.test_sos_walking_skeleton
python -m unittest quality_tests.test_sos_input_firmware -v
python -m unittest quality_tests.test_sos_outbox_adapter -v
python -m unittest quality_tests.test_sos_device_runtime -v
python -m unittest quality_tests.test_sos_pending_edge_journal -v
python -m unittest quality_tests.test_sos_pending_edge_journal quality_tests.test_sos_device_runtime quality_tests.test_sos_orchestrator_firmware -v
python -m unittest quality_tests.test_sos_device_runtime quality_tests.test_sos_outbox_adapter quality_tests.test_sos_orchestrator_firmware quality_tests.test_sos_input_firmware quality_tests.test_sos_walking_skeleton quality_tests.test_persistent_priority_outbox_device_core quality_tests.test_persistent_priority_outbox quality_tests.test_location_policy_core_firmware -v
python -m unittest quality_tests.test_sos_outbox_adapter quality_tests.test_sos_orchestrator_firmware quality_tests.test_sos_input_firmware quality_tests.test_sos_walking_skeleton quality_tests.test_persistent_priority_outbox_device_core quality_tests.test_persistent_priority_outbox quality_tests.test_manual_sos_store quality_tests.test_manual_sos_delivery_ack -v
python -m unittest quality_tests.test_manual_sos_store quality_tests.test_manual_sos_delivery_ack -v
python -m unittest quality_tests.test_guardian_device_authorization quality_tests.test_location_state_http quality_tests.test_location_delivery_ack quality_tests.test_location_state_store quality_tests.test_location_state_runtime quality_tests.test_location_state_mirror quality_tests.test_message_hub_server quality_tests.test_message_hub_dashboard quality_tests.test_message_hub_contracts quality_tests.test_message_hub_client quality_tests.test_message_hub_stability_validation -v
python scripts/context_lint.py
git diff --check -- docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md firmware/mqtt_heartbeat/components/sos_input/ firmware/mqtt_heartbeat/components/sos_orchestrator/ firmware/mqtt_heartbeat/components/sos_outbox_adapter/ firmware/mqtt_heartbeat/components/sos_device_runtime/ firmware/mqtt_heartbeat/components/sos_pending_edge_journal/ pc_simulator/sos_walking_skeleton.py shared/contracts/safety_event.schema.json server/manual_sos_store.py server/manual_sos_delivery_ack.py server/message_hub.py server/guardian_location_page.py quality_tests/test_sos_input_firmware.py quality_tests/test_sos_orchestrator_firmware.py quality_tests/test_sos_outbox_adapter.py quality_tests/test_sos_device_runtime.py quality_tests/test_sos_pending_edge_journal.py quality_tests/test_sos_walking_skeleton.py quality_tests/test_manual_sos_store.py quality_tests/test_manual_sos_delivery_ack.py quality_tests/test_message_hub_server.py quality_tests/test_message_hub_dashboard.py docs/operations/VPS_RUNBOOK.md
```

The repository-wide static/host gate is:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

The operator-approved hardware drill remains closure work and must be
coordinated after the physical LOC/CALL/outbox integrations settle.

# Completion Evidence

- Host-only composition covers healthy, offline, declined-call, same-process
  and concurrent idempotency, stable outbox/call input across a location-state-
  absent reopen, repeated distinct SOS edges, low-battery priority, missing-
  location and debounce-boundary paths. A current-event scheduler settles each
  earlier due outbox attempt through an explicit simulated transport result
  before selecting the new SOS; it cannot strand the older record in
  `attempt_started` or apply the new event's ACK to it. Every distinct manual
  SOS edge explicitly requests location upload and Ego Call even while SOS
  policy is already active, and the contract-valid policy view matches the
  actions actually attempted.
- Location snapshot failure persists a coordinate-free `Unknown` belief with a
  bounded reason before policy work. Injected location/policy and Guardian-
  branch failures prove that the durable event and local feedback remain, and
  that alert/call branches continue independently. Location upload is only a
  policy request with no connected adapter, and an outbox positive ACK proves
  only server receipt, never Guardian human delivery or acknowledgement.
  Focused SOS validation passed `13/13`; the combined SOS/outbox/policy/call
  regression passed `64/64`, and `context_lint` passed on 2026-09-02. This is
  not hardware evidence or remote-session durability evidence.
- Host persistence is only the existing atomic JSON-mirror reference. Physical
  button, product NVS, authenticated delivery, embedded call and representative
  hardware failure/recovery remain unverified. True physical release/re-arm
  behavior and concurrent device-side branch scheduling remain later
  integration work; this host adapter serializes state mutation and simulates
  transport.
- SOS-010B adds a dormant, caller-owned C input state machine with no GPIO,
  task, transport, persistence, location, call or battery-veto dependency. It
  emits one edge plus its reconstructed logical time, requires a debounced
  release before re-arm, rejects startup-held input until release, and latches
  rollback/deadline-overflow faults. Focused SOS-010B validation passed `15/15`;
  combined input/host SOS regression passed `28/28`. The actual C source and an
  API harness cross-compiled for ESP32-S3 under warnings-as-errors. The Python
  executable fixture checks semantics and host-boundary equivalence but does
  not execute the target C object; no host C compiler/target emulator was
  available. No image was built or flashed, no board/GPIO was sampled, and no
  P0 Gate advanced.
- SOS-010C adds the dormant, caller-owned `sos_orchestrator` component. For a
  qualified edge it constructs a bounded, coordinate-free safety-event JSON
  and attempts its CRITICAL outbox enqueue before local feedback, Location
  Policy SOS evaluation, urgent last-trusted/current-location enqueue and Ego
  Call request, in that fixed order. Persistence, policy and all three
  callbacks report independently; an earlier failure does not veto a later
  best-effort branch. The event identity is stable over a replay of the exact
  device/boot/session/sequence/edge-time lineage, while distinct physical
  edges retrigger all remote request seams. Callback requests are at-least-
  once and must be idempotently consumed by later adapters.
- `safety_event.context.battery_percent` now accepts either the prior bounded
  number or JSON `null`. The host runtime and schema tests prove that an
  unavailable gauge remains unknown and cannot force a fabricated number or
  veto manual SOS; known values remain bounded to `[0, 100]`.
- SOS-010C focused orchestration validation passed `13/13`. The combined
  orchestration/input/host-SOS/device-outbox/device-policy/schema regression
  ran `80` tests: `79` passed and the existing native Location Policy runtime
  harness was skipped because no native host GCC/Clang was available. Its
  target C source still cross-compiled. `python scripts/context_lint.py`, JSON
  parsing, tracked diff checks and explicit whitespace/final-LF checks for the
  new untracked files passed on 2026-09-02.
- A clean dedicated ESP-IDF v5.4.2 ESP32-S3 build used
  `idf.py -C firmware/mqtt_heartbeat -B D:\pywork\egolink\tmp\sos010c_clean_idf_build -D IDF_TARGET=esp32s3 -D SDKCONFIG=D:\pywork\egolink\tmp\sos010c_clean_sdkconfig -D SDKCONFIG_DEFAULTS=sdkconfig.defaults build`.
  It linked `egolink_mqtt_heartbeat.bin` at `0xDACF0` bytes against the default
  `0x100000` app partition with `0x25310` bytes (15%) reported free. The actual
  component compile command contains `-Werror -Wconversion -Wformat=2
  -Wshadow -Wsign-conversion`.
- This evidence is build/static/host-reference evidence only. The Python
  orchestration fixture does not execute the target C object, and the default
  `app_main` does not instantiate the component. No callback here is a LOC
  delivery, Guardian alert, human acknowledgement or connected Ego Call; no
  GPIO, flash/reboot, network, audio, board or operator drill ran. The caller
  must serialize the orchestrator, outbox, policy, LOC/send/ACK mutations and
  ensure the copied `device_id` exactly matches the injected outbox identity,
  because the outbox currently exposes no identity read API. The existing
  full-image outbox partition adapter remains bounded field-test engineering
  persistence, not a product-endurance backend. Physical/P0-SOS acceptance
  therefore remains open.
- SOS-010D adds a standard-library-only, authenticated manual-SOS server
  ingest at `/api/v1/safety-events/manual-sos`. The runtime validator accepts
  no second contract: it enforces the exact coordinate-free
  `manual_sos`/`critical`/`device_rule` subset generated under the existing
  `safety_event.schema.json`, with a 1024-byte ceiling. Duplicate JSON members,
  malformed UTF-8/JSON, non-finite or non-device numeric shapes, unknown
  fields, non-null media references, unsafe identities, lineage mismatch and
  SQLite signed-integer overflow all fail before mutation.
- Accepted exact request bytes and their SHA-256 are committed to an
  independent SQLite timeline. Same device/event/exact bytes return a durable
  duplicate; different bytes or reused physical-edge lineage conflict without
  changing current. Current is ordered by device boot then same-boot session
  source sequence/time, not receipt order: a delayed old-boot or older-sequence
  event remains durably recorded and ACK-eligible but cannot replace the
  latest alert. One boot bound to multiple sessions and monotonic time/sequence
  inconsistency fail closed. Startup validates every timeline/ack row and
  transactionally rebuilds the derived current cache with the same ordering;
  timeline corruption stops store construction.
- Only committed accepted/duplicate results produce the existing outbox ACK
  shape. Its `ack_id` is `ack-<SHA-256>`, while `device_id`, device `event_id`
  and `payload_sha256` are cross-checked against the exact raw request. The
  response separately states `server_durable_ingest_only`; HTTP `2xx` is not a
  Guardian-view, human-acknowledgement, push-delivery or call-success claim.
- The bound Guardian latest-alert API and independent manual-ack POST require
  the existing hashed Guardian authorizer and exact device binding. Missing
  Guardian configuration returns `503` even if the global ingest token is
  supplied. The projection exposes only alert/event/time, battery and server
  receipt/delivery/Guardian-ack/call states; it excludes raw bytes, payload
  hash, boot/session/sequence fields, coordinates and media. Manual Guardian
  ACK is durable/idempotent but does not delete device/server records, rewrite
  the device ACK or change `call_state=not_reported`. The existing Guardian
  page starts both bound reads from one lookup action, renders with
  `textContent`, and does not store or place the bearer token in a URL.
- SOS-010D focused store/ACK/loopback tests passed `18/18`; the compatible
  SOS-010C focused suite passed `13/13`. The expanded pre-existing
  Guardian/location/message-hub/dashboard/client/stability regression passed
  `194/194` in 60.357 seconds on 2026-09-02. These tests used only loopback and
  temporary SQLite databases; no VPS or device endpoint was contacted.
- The repository-wide `scripts/verify.ps1` static/host gate passed `1196/1196`
  tests in 140.987 seconds on 2026-09-02, with two tests skipped by their
  existing environment guards. This broad regression remains software-only
  evidence and does not advance the physical SOS acceptance checklist.
- The store serializes in-process operations with one `RLock`, uses SQLite
  `BEGIN IMMEDIATE` for timeline/current/Guardian-ack mutations, and returns no
  positive ACK after transaction or recovery failure. Cross-process behavior
  is limited to SQLite's locking/atomicity. The exact raw body is private data
  at rest, and this slice provides neither database encryption nor a product
  key lifecycle. Timeline growth is not pruned. In particular, source
  `retention_seconds=86400` is not enforced by expiry, backup deletion or an
  erasure workflow and remains a pre-production privacy blocker.
- SOS-010D did not deploy or contact the VPS, send network traffic beyond
  loopback, wire a device sender/ACK parser, implement push notification or
  call signaling, run on hardware, or exercise a physical button. Guardian
  page visibility is pull-only. `P0-SOS` remains `NOT_RUN`.
- SOS-010E adds a dormant device-side selector/send-view/completion adapter;
  it does not enqueue a second SOS record. Before exposing borrowed exact
  payload bytes, it checks the selected record is CRITICAL `manual_sos`,
  recomputes the exact-byte SHA-256, and bounded-parses the existing
  coordinate-free orchestrator subset so device/event/boot/session/sequence/
  time/type/priority/source and privacy/evidence identities all agree. A
  non-SOS head and an invalid SOS-shaped record are explicit retained states,
  not payloads silently routed to the SOS endpoint.
- For an HTTP `2xx`, SOS-010E strictly parses and identity-matches the bounded
  response before recording transport acceptance. Malformed, truncated,
  duplicate-key, extra/missing-field, wrong-result/scope/ACK or wrong-identity
  responses are recorded as failed attempts and remain retryable. Only an
  exact `accepted|duplicate` durable-ingest result is recorded transport-
  accepted and passed to the existing exact positive-ACK deletion API. The
  executable host scenario proves a malformed `2xx` enters retry wait, then a
  later exact server `duplicate` ACK deletes the same durable event.
- A positive-response delete-commit failure deliberately keeps the adapter's
  active identity and caller-owned send item intact. The current outbox core
  nevertheless latches a storage write fault, so recovery requires outbox
  reinitialization from the last valid mirror and a new attempt; SOS-010E does
  not claim same-instance flash-fault recovery. Exactly one owner must
  serialize the shared outbox and adapter lifecycle.
- SOS-010E focused validation passed `13/13`; the combined adapter,
  orchestrator, input, host-SOS, device-outbox, host-outbox and server SOS
  ingest/ACK regression passed `104/104` on 2026-09-02. The focused suite
  cross-compiled the actual adapter C source for ESP32-S3 with warnings as
  errors. Python response/retry fixtures validate the boundary contract but
  do not execute the target C object.
- No transport, endpoint, token, TLS, `app_main`, task, GPIO, partition
  wiring, network, device, audio or physical SOS drill was added or run. The
  default firmware remains unwired. Flash endurance/confidentiality and the
  earlier server retention/privacy blockers remain open; `P0-SOS` remains
  `NOT_RUN`.
- SOS-010F adds a default-disabled, task/GPIO/network-free device composition
  over the real C input and orchestrator. Its per-sample surface accepts only
  `raw_pressed` and boot-monotonic `now_ms`; the runtime owns the bounded,
  securely wiped orchestrator scratch. A qualified edge delegates to the
  existing enqueue-before-feedback order, advances one boot-scoped source
  sequence even when later branches fail, then emits a separate sender-wake
  intent. Repeated held samples do not replay the edge, and a debounced release
  is still required before the next sequence.
- F deliberately does not create a second E adapter or claim send ownership.
  Initialization requires the caller's single already-bound adapter, exact
  shared-outbox pointer and matching device ID. The composition root must bind
  that adapter once, give it to the single outbox dispatcher, and pass the
  same borrowed objects to F. F contains no adapter bind/unbind/begin/finish or
  ACK call. Runtime cancel/close do not mutate the outbox or adapter, so even a
  dispatcher-owned active attempt is untouched.
- The Location dependency cannot currently provide this runtime with a safe
  unique observation-construction API. F therefore evaluates SOS policy from
  an explicit unknown sensor snapshot and emits the existing coordinate-free,
  event-identified request for last-trusted/current urgent location work. The
  callback owner must construct and deduplicate any real LOC observation. This
  is an intent, not evidence of GNSS start, location enqueue or upload.
- SOS-010F focused validation ran `10` tests: `9` passed and the native C
  behavioral harness was skipped because no host GCC/Clang was available. The
  actual runtime C source and the composition harness cross-compiled for
  ESP32-S3 with warnings as errors.
  The combined F/E/orchestrator/input/host-SOS/device-outbox/host-outbox/policy
  regression ran `110` tests: `108` passed and the two guarded native harnesses
  skipped for the same missing host compiler. `context_lint` passed on
  2026-09-02.
- The target-cross-compiled but non-executed native harness specifies
  startup-held/release/re-arm, repeated-sample suppression, fixed durable/
  feedback/policy/LOC/CALL/wake order, storage failure, independent LOC/CALL
  failures, distinct sequence advancement and cancel/close retention. These
  are not physical execution evidence. The caller still owns durable
  boot-count/source-sequence allocation; this volatile runtime cannot prevent
  identity reuse after an incorrectly configured reboot.
- When a CRITICAL enqueue/storage commit fails, F still consumes that
  qualified edge's volatile sequence after reporting the failure. There is no
  persistent pending-edge journal or retry API, so the result alone cannot
  replay the physical edge after reset. Caller-owned edge journaling/replay is
  an explicit physical/reboot acceptance blocker.
- F remains absent from `app_main`; no pin, driver, transport, dispatcher,
  device, flash, network, audio, operator or physical-button test was added or
  run. The shared full-image outbox endurance/confidentiality blockers and
  server retention blocker remain. `P0-SOS` remains `NOT_RUN`.
- SOS-010G adds a caller-owned one-record pending-edge journal seam. Its v1
  storage image is exactly 320 bytes and has explicit little-endian offsets,
  format/header/total-size markers, canonical zero padding and CRC32. The C
  decoder rejects size/version/reserved/padding/CRC/identity/integer failures;
  exact readback resolves callbacks that report an error after committing.
  Different valid records are never overwritten or compare-cleared.
- F now stores and verifies a qualified edge in that journal before consuming
  its sequence or calling the orchestrator. A store failure leaves the exact
  RAM candidate, blocks later samples and rejects shutdown so an explicit
  replay can retry. Once stored, outbox failure or clear failure retains the
  record. A later replay produces the same event ID; an exact outbox duplicate
  is enough to clear the journal, but never enough to claim server, Guardian or
  Call completion. All remote/local callbacks remain at-least-once and require
  idempotency by that stable event ID.
- Recovery accepts same-device old-boot/session lineage without modifying the
  new boot's sequence. Current-boot/current-session recovery advances past the
  pending sequence and handles the JSON-safe maximum as exhausted; future boot
  and current-boot/different-session records fail closed. The trusted runtime
  replay flag is not serialized. It preserves original payload/source identity
  while using current `now_ms` for outbox and Location Policy mutations so old
  boot-monotonic time cannot poison a new runtime epoch.
- SOS-010G focused journal validation ran `11` tests: `10` passed and the
  actual-C native execution was skipped because no host GCC/Clang was present.
  The executable Python fault model covers ambiguous store/clear, absent-store
  failure, pending admission blocking, duplicate replay, cross-boot identity/
  clock behavior, current-boot sequence advancement/max exhaustion, corrupt/
  size/wrong-device/future-boot/session rejection and shutdown retention. It is
  an executable specification and does not execute the target C object.
- The focused G/F/orchestrator run completed `34` tests: `32` passed and two
  native-C guards skipped. The broader G/F/E/orchestrator/input/host-SOS/
  outbox/policy regression completed `121` tests: `118` passed and three
  native-C guards skipped. The actual journal, runtime, orchestrator and input
  C sources plus the fault harness cross-linked for ESP32-S3 under
  `-Werror -Wconversion -Wformat=2 -Wshadow -Wsign-conversion`.
- A dedicated clean ESP-IDF v5.4.2 ESP32-S3 build passed with
  `idf.py -C D:/pywork/egolink/firmware/mqtt_heartbeat -B D:/pywork/egolink/tmp/sos010g_clean_idf_build2 -D IDF_TARGET=esp32s3 -D SDKCONFIG=D:/pywork/egolink/tmp/sos010g_clean_sdkconfig2 -D SDKCONFIG_DEFAULTS=sdkconfig.defaults build`.
  The journal and runtime compiled and linked. The resulting app was
  `0xDACF0` bytes in the default `0x100000` factory partition, with `0x25310`
  bytes (15%) reported free; the bootloader was `0x51C0` bytes with `0x2E40`
  bytes (36%) free. The new components retained their local strict warning
  flags, but existing `app_main` warnings mean this is not a claim that the
  entire application was built with warnings as errors. The build used the
  default partition table rather than the separate outbox partition profile
  and did not flash or execute target code.
- The SOS-010G scoped diff/whitespace check and `python
  scripts/context_lint.py` passed on 2026-09-02.
- No NVS/partition backend, atomicity/power-loss implementation, wear policy,
  flash confidentiality, boot-counter provider, GPIO/task/app wiring, device
  run or reboot test exists in G. A reset while the journal store still cannot
  make any valid record durable can still lose the volatile physical edge, and
  the single-record fail-closed admission policy can delay a second physical
  edge. These are physical/product integration blockers; `P0-SOS` remains
  `NOT_RUN`.
- SOS-010H adds the default-unwired ESP-IDF NVS callback adapter at the exact
  default partition `nvs`, namespace `ego_sos_pend` and key `edge_v1`. Its init
  is RAM-only and neither initializes nor accesses NVS. Load is read-only;
  missing namespace/key maps to `NOT_FOUND`. Store alone may create the
  namespace and accepts only the exact 320-byte G image before
  `nvs_set_blob` plus `nvs_commit`. Clear uses a read-only existence/size
  preflight before `nvs_erase_key` plus `nvs_commit`, so clearing an absent
  record does not create a namespace. Every successfully opened handle is
  closed on all exits, and wrong sizes or other NVS errors fail closed.
- H exposes only RAM-resetting, saturating operation/handle/byte/error metrics;
  they retain no payload or identity and are not lifetime evidence. Commit
  failure remains an ambiguous storage error for the existing G exact-readback
  decision rather than being promoted to success. The adapter contains no log,
  allocation, task, NVS initialization/erase/format or `app_main` binding.
- H focused validation ran `9` tests: `8` passed and the native-host execution
  guard skipped because no host GCC/Clang was available. The actual adapter
  and a fake-NVS fault harness cross-compiled for ESP32-S3 with strict warnings;
  that harness was not executed. The combined H/G/F validation ran `30` tests:
  `27` passed with three native-host execution guards skipped.
- A clean dedicated ESP-IDF v5.4.2 ESP32-S3 build passed with
  `idf.py -C D:/pywork/egolink/firmware/mqtt_heartbeat -B D:/pywork/egolink/tmp/sos010h_clean_idf_build -D IDF_TARGET=esp32s3 -D SDKCONFIG=D:/pywork/egolink/tmp/sos010h_clean_sdkconfig -D SDKCONFIG_DEFAULTS=sdkconfig.defaults build`.
  The actual adapter compiled with `-Werror -Wconversion -Wformat=2 -Wshadow
  -Wsign-conversion` and linked. The app was `0xDACF0` bytes in the default
  `0x100000` factory partition with `0x25310` bytes (15%) free; the bootloader
  was `0x51C0` bytes with `0x2E40` bytes (36%) free. Existing `app_main`
  unused-symbol warnings remained outside H, so this is not a whole-program
  warnings-as-errors claim. The default table retained its existing 24 KiB
  `nvs` partition; build/link alone does not prove runtime capacity/endurance.
- H scoped `git diff --check` passed. `context_lint` was attempted but remained
  blocked outside SOS-010 by two concurrent CALL-020 allowed paths whose files
  were not yet present; the root merged-tree rerun remains required.
- No real callback, NVS write/read/erase, restart, power loss, flash,
  provisioning, device, COM, network or hardware operation ran. Successful
  NVS commit is not claimed brownout-atomic or endurance-qualified, and this
  slice neither enables nor proves flash encryption, key lifecycle or secure
  erasure. Before runtime wiring, the composition root must resolve NVS init
  ownership and the current default app's conditional whole-partition erase,
  plus measure namespace capacity and write cadence. `P0-SOS` remains
  `NOT_RUN`.
- SOS-010I adds the default-disabled caller-owned composition root over the
  single SOS adapter, pending-edge journal, P0 dispatcher, delivery runtime
  and SOS device runtime. It validates that the borrowed initialized Location
  adapter owns the exact shared outbox/device identity and that the borrowed
  policy/storage/HTTP seams are present. Enabled initialization follows the
  fixed adapter -> journal -> dispatcher -> delivery -> SOS-runtime order;
  completed owned stages roll back in reverse without deinitializing the
  caller's outbox, Location adapter, policy core, pending storage or HTTP
  owner.
- The internal wake callback stores only one bounded intent plus a saturating
  counter. Sample and pending replay never call delivery recursively. One
  later explicit `drive_once` performs at most one normal dispatcher/POST/
  finish action or one existing begin/finish recovery action. The one shared
  dispatcher preserves CRITICAL `manual_sos` selection ahead of a lower-
  priority Location head, and only the existing exact accepted/duplicate
  server durable-ingest ACK path can delete either durable record.
- Root review found and closed an initialization-rollback recovery hole. If an
  owned delivery/dispatcher close fails, I now retains every lower owned
  binding, enters an explicit rollback-recovery state and rejects sample,
  replay and new delivery. A later serialized close/cancel retries at most one
  existing begin/finish settlement and remaining reverse cleanup; it releases
  the adapter/journal only after that cleanup succeeds. The strict fake-
  dependency harness covers dispatcher-close failure followed by successful
  retry, verifies no HTTP call in between, and truthfully distinguishes SOS-
  runtime, delivery-runtime and owned-dispatcher cleanup metadata. It also
  probes and closes a dependency implementation that leaves a partially
  initialized SOS runtime; the current real SOS runtime self-clears on every
  rejected init path.
- I focused validation is `8 PASS / 1 native-host skip`; its prescribed
  composition/delivery/dispatcher/runtime/journal/adapter set is `61 PASS / 4
  native-host skips`. The complete `test_sos*.py` regression is `90 PASS / 4
  native-host skips`, and every `test_*outbox*.py` test passes `76/76`.
  The actual I source and fake lifecycle harness cross-link for ESP32-S3 under
  `-Werror -Wconversion -Wformat=2 -Wshadow -Wsign-conversion`; no cross-
  compiled C was executed. `python scripts/context_lint.py`, the merged
  tracked `git diff --check`, and explicit final-LF/trailing-whitespace checks
  for every untracked I file pass.
- ESP32-S3 ABI sizing is: public composition context `32,768` bytes, private
  implementation `25,712`, event result `288`, drive result `136`, shutdown
  result `152` and snapshot `96`. Compiler stack-usage output reports the
  largest local frame as `784` bytes in rollback cleanup; public entry frames
  are at most `304` bytes for init and `176` bytes for drive/status. These are
  isolated static frames, not a measured task high-water mark or full
  transitive HTTP/parser/storage call-chain result.
- A clean ESP-IDF v5.4.2 ESP32-S3 build under
  `tmp/sos010i_clean_idf_build/`, followed by a final-source incremental
  rebuild in that clean tree, compiled I with its local strict flags and
  linked successfully. The app is `0xDACF0` bytes in the default `0x100000`
  factory partition with `0x25310` bytes (15%) free; the bootloader is
  `0x51C0` bytes with `0x2E40` bytes (36%) free. Unrelated application/
  concurrently owned component warnings mean this is not a whole-program
  warnings-as-errors claim.
- This synchronous single-owner layer remains a composition reference. A
  blocking in-flight Location POST could delay a newly sampled SOS if product
  integration puts delivery on the safety-input/Call task or holds one mutex
  across HTTP. I therefore does not prove SOS latency or preemption. The next
  P0 runtime slice must hand a bounded immutable payload snapshot to an
  independent sender and review urgent cancellation/preemption without moving
  safety input or Ego Call behind blocking delivery.
- No `app_main`, GPIO, task, NVS initialization, storage callback, HTTP
  implementation, credential, SIM, VPS, network, flash, reboot, board or
  physical drill was added or run. Urgent Location and Ego Call remain
  injected coordinate-free/idempotency-keyed requests, not a proved Location
  upload, Guardian alert or connected call. NVS ownership, wear/confidentiality,
  server retention and physical outage/reboot/latency evidence remain open;
  `P0-SOS` stays `NOT_RUN`.
- SOS-010J replaces the product sender seam with explicit split phases:
  composition `prepare` and `settle_prepared` run under the caller's shared
  owner, while `execute_prepared` runs after that owner is released and calls
  only the injected bounded transport. This lets the serialized SOS input
  owner durably journal and enqueue `manual_sos`, then complete local feedback,
  urgent Location and Ego Call callbacks while a Location callback is in
  flight. The wake callback remains bounded and invokes only the P0 runtime's
  atomic durable-SOS preemption signal; it never sends recursively.
- Preemption is cooperative cancellation, not a modem abort claim. It targets
  only an active Location transfer; `manual_sos` is never cancellable by this
  signal. On cancel-wins the later settlement cancels/retains Location for
  retry and the next prepare selects the due CRITICAL SOS. On result-wins the
  already-ready transport result remains authoritative. A non-cooperative
  callback may finish or block until its own timeout, so acceptance can remain
  unknown and no hard latency bound is claimed.
- J remains default-disabled and has no task, mutex, GPIO, HTTP owner,
  credentials, NVS initialization or application binding. Its focused checks
  are fake-storage/fake-transport only; no network or hardware is used.
  Urgent Location and Ego Call are still injected requests, not proved
  end-to-end effects. `P0-SOS` remains `NOT_RUN` until physical acceptance.
- J focused validation passes `8/8`; the actual composition and H runtime
  compile under the ESP32-S3 strict warning set and relocatable-link together,
  with all four split-phase/preemption symbols resolved. The combined H/I/J
  focused run passes `25` tests with two native-host execution guards skipped
  (`27` collected).
  The installed environment has no host GCC/Clang, so no cross-compiled race
  executable was run; result-wins/cancel-wins execution evidence remains H's
  fake-runtime harness boundary rather than a physical or timing claim. Root
  later supplied the installed ESP-IDF v5.4.2 tool paths explicitly and
  completed a fresh final-source ESP32-S3 build in
  `tmp/p0_mainline_final_clean_20260903/`. It compiled and linked J with the H
  runtime and all current dormant P0 components; the application is `0xDACF0`
  bytes with `0x25310` bytes (15%) free in the `0x100000` factory partition.
  This is compile/link evidence only; no race path, device, network or SOS was
  executed.
- A combined-audit correction moves the durable sender wake/preemption seam
  into the orchestrator's exact post-persistence boundary. It runs only after
  `manual_sos` enqueue returns durable committed/duplicate and before local
  feedback, SOS policy, urgent Location or Ego Call callbacks. A slow
  synchronous branch can therefore no longer delay the atomic Location
  cancellation request. Wake failure remains an independent partial-failure
  result, does not veto the other branches and is not retried recursively.
  Outbox failure deliberately emits no `durable=false` wake and no preemption:
  without a durable `manual_sos` record there is nothing safe for the sender
  to prioritize. The retained pending edge must use explicit pending replay;
  a later COMMITTED/DUPLICATE result then emits the one durable-ready wake.
  For standalone orchestrator users the hook remains optional, but when it is
  configured and returns false the orchestration result is `PARTIAL_FAILURE`;
  an absent hook retains the previous optional-branch completeness semantics.
- The J product path also exposes an owner-held, single-action delivery
  recovery wrapper for both BEGIN and FINISH recovery. It invokes only the
  matching P0 retry operation, never POST/prepare/execute, so split-phase
  liveness does not depend on the legacy synchronous `drive_once`. Shutdown
  continues to fail closed while prepared, executing, result-ready or recovery
  state remains unresolved.
- Lifecycle audit refinement: cancel/close may settle a `PREPARED` attempt
  through the P0 runtime's safe unsent cancel/close path, retaining its durable
  record and never forcing HTTP execution during shutdown. `EXECUTING` rejects
  concurrent shutdown, while `TRANSPORT_RESULT_READY` explicitly requires
  `settle_prepared`; BEGIN/FINISH explicitly require the recovery wrapper. The
  recovery wrapper reports these next actions distinctly instead of returning
  a generic recovery loop for every non-recovery phase.

# Builder Prompt

```text
Read docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md in D:\pywork\egolink.
Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's context. The
isolated host slice may compose the frozen Location, Sensor Policy, outbox and
Ego Call seams in the two explicitly allowed new files before LOC-021/CALL-021
physical acceptance. Do not edit those dependency modules or create a second
safety contract. Physical composition still waits for the real integrations.
Flashing, hardware commands, network changes, audio capture and real drills
require explicit operator intent. Run the focused/static commands for the host
slice; coordinate full verification and the reviewed bounded drill at closure.
Never let camera, AI or low battery veto SOS, and do not mark a P0 Gate PASS
from component or host-only evidence.
```

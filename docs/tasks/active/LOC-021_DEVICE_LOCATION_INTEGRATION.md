---
id: LOC-021
title: Device, Message Hub and Guardian Location integration
status: active
priority: critical
lane: A
execution_state: in_progress
depends_on:
  - LOC-020
  - POLICY-010
  - REPLAY-010
serves_gate: P0-LOC
requires_hardware: true
created: 2026-08-23
last_updated: 2026-09-05

context:
  - docs/architecture/adr/ADR-0014-runtime-convergence.md
  - docs/tasks/active/P0-CONVERGENCE-20260905.md
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/tasks/done/LOC-020_LOCATION_ENGINE_V0.md
  - docs/tasks/done/POLICY-010_SENSOR_POLICY_V0.md
  - docs/tasks/done/REPLAY-010_LOCATION_POLICY_REPLAY.md

allowed_paths:
  - docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md
  - docs/development/LOCATION_ENGINE.md
  - docs/development/VPS_MESSAGE_HUB.md
  - firmware/mqtt_heartbeat/
  - server/
  - shared/contracts/
  - pc_simulator/
  - pc_simulator/sensor_policy_v0.py
  - pc_simulator/location_engine_v0.py
  - quality_tests/
  - scripts/deploy_message_hub_vps.ps1

out_of_scope:
  - learned fusion, dead reckoning, camera AI or context/anomaly models
  - changing a public contract without contract-first compatibility tests
  - allowing server receive time to replace source event time
  - fabricating coordinates, accuracy, confidence or delivery freshness
  - flashing, device commands, network changes or field runs without explicit
    operator intent
---

# Current Runtime Dispatch (2026-09-05)

[ADR-0014](../../architecture/adr/ADR-0014-runtime-convergence.md) and
[P0-CONVERGENCE-20260905](P0-CONVERGENCE-20260905.md) now prioritize a selected
finite current-boot/single-source live Location -> authenticated secure
transport -> bound Guardian slice, reusing A-S. The old isolated S profile
remains an independent modem smoke; neither path waits globally for T0/T1.
A real connector, exact complete ACK, one modem owner and source-event time are
required. Local Location state/policy/aging and outbound durability have
independent status: queue-full or failed storage cannot silently freeze local
progress, and failed persistence cannot be called stored or delivered.

The original concurrent SOS/IMU product bridge and reboot-equivalence promises
below remain pending. Enabling them requires their original ordered WAL,
persistent K checkpoint or equivalent full replay, exact tombstone and
no-output replay guarantees, or a reviewed behaviorally proven replacement.
A finite single-source slice does not satisfy or waive them. Historical replay
has no physical/call side effects; service recovery only resumes pending
identity-stable delivery and cannot resurrect expired/ended calls.

These are current implementation requirements, not new execution evidence.
All prior results retain their dates; `P0-LOC=NOT_RUN`. Hardware and live
network actions still require a valid bounded operator experiment scope.

# Goal

Integrate the accepted Location Engine v0 and Sensor Policy v0 semantics into
the current device runtime, Message Hub mirror and minimum Guardian surface,
with one versioned configuration identity and replay-equivalent behavior.

# Acceptance

- [ ] Device observations carry source event time, boot/session lineage,
      attempt/result and the exact policy/config version or hash used.
- [ ] Device behavior conforms to reviewed LOC-020/POLICY-010 golden fixtures
      for `STABLE`, `MOVING`, `LOCATION_UNCERTAIN`, `SOS` and `LOW_BATTERY`,
      including GNSS timeout/no-fix/backoff and SOS precedence.
- [ ] The runtime preserves last trusted location without manufacturing a new
      coordinate or presenting historical accuracy as current accuracy.
- [ ] Message Hub stores an idempotent event timeline and a derived current
      mirror; source event time, not receive time, owns ordering/freshness.
- [ ] Guardian shows location belief/source, age, accuracy when applicable,
      confidence, uncertainty, battery and an honest stale/offline state.
- [ ] Offline/reconnect/reboot fixtures and Replay produce equivalent accepted
      state/action output for the same observations and configuration.
- [ ] One operator-approved exact-board run records board, image, connection,
      SIM/network, timestamps and evidence paths; a build alone cannot pass.
- [ ] Completion remains component/integration evidence. `P0-LOC` stays
      `NOT_RUN` until FIELD-020 and representative product criteria pass.

# Dispatch Boundary

The LOC-020/POLICY-010/REPLAY-010 dispatch condition is satisfied. LOC-021A/B/C
have frozen the additive envelope, implemented the package-free admission core,
persisted its event-time timeline in SQLite, and connected authenticated bounded
Message Hub ingest plus a coordinate-redacted current-state read. LOC-021D/E
add dormant firmware envelope and policy components. LOC-021F returns a
request-byte-bound positive ACK only after durable server ingest, and LOC-021G
connects exact emitter bytes to the injected persistent outbox plus that ACK
contract without owning a transport. LOC-021H adds the missing transport-free
device Location Engine reducer, while LOC-021I adds explicit Guardian-token to
device authorization for exact-position reads. LOC-021J now composes the four
dormant device cores behind one serialized, fail-closed runtime pipeline; it
still does not own observation capture, a persistent replay journal, outbox
initialization/storage, transport or a task. LOC-021K wraps that pipeline in a
default-disabled lifecycle owner which borrows the caller-initialized location
adapter and the one persistent outbox that must also be shared with SOS, then
surfaces bounded synchronous actuator intents without adding automatic I/O.
LOC-021L adds a dormant caller-timed conversion boundary for the existing
SIM7670 GNSS/LTE and platform IMU report types plus explicit battery input; all
currently unsafe or missing actuator operations fail as `NOT_SUPPORTED`.
LOC-021M adds query-by-query observed/parse-valid evidence so those adapters
can distinguish proven modem facts from legacy/default false values. LOC-021N
adds a default-off, fixed-capacity `location_modem_arbiter` core for transient
single-owner ordering only. It neither executes a command nor replaces the
shared persistent outbox: durability remains with OUTBOX-010. LOC-021O extends
that core with explicit urgent-SOS GNSS ordering and adds a dormant, no-I/O
`location_modem_executor` composition boundary around LOC-021K/M, the existing
split-phase P0 delivery runtime and shared durable outbox semantics. LOC-021P
adds a default-disabled native SIM7670 GNSS/Cell callback adapter with bounded
query entry points for that executor; it creates no task, owns no `app_main`
wiring and performs no automatic modem operation. LOC-021Q adds the separately
default-off, boot-long `sim7670_location_modem_owner`: one pinned static task
claims the UART for its exact `TaskHandle_t`, composes P/O around the exact
borrowed outbox/Location adapter/P0 delivery runtime, and wraps every GNSS
query in bounded power-off compensation before a report may be admitted.
LOC-021R makes Q/O the sole full durable-SOS ingress and preserves a deferred
Cell obligation when arbiter admission is rejected or displaced; signal-only
SOS preemption remains independent from the later full ordered drain.
LOC-021S now adds a separately default-off, modem-only application profile.
Its final source selection compiles `loc021s_modem_owner_main.c` instead of the
legacy `app_main.c`; final compile database and linker-map checks prove that
the legacy application translation unit is absent. S initializes the exact
shared partition-backed outbox, Location adapter, SOS adapter, dispatcher and
P0 delivery runtime with an explicit no-I/O `TRANSPORT_FAILED` callback, then
starts Q and queues at most one GNSS-status request. The durable boot epoch is
committed and read back from NVS before any Q start, with no automatic erase.
All Q-borrowed objects are boot-long and there is no teardown claim.
ESP-IDF expands component requirements before project Kconfig is available,
so main declares the exact static union of default and S dependencies; library
presence in that build graph is not a runtime ingress. The final S ELF and
source checks retain no legacy HTTP/GNSS/LTE query, external SOS or IMU caller.
`EGOLINK_MESSAGE_HUB_HTTP_ENABLED` likewise remains only because the existing
GNSS/LTE Kconfig requires it; probe, command-loop, observation and D1 modes are
all off and S performs no network I/O. S deliberately exposes no external
SOS/IMU/mapped ingress and may use Q's internal boot-local capture sequence for
a later modem-only smoke. Before those concurrent producers are enabled, one
shared replayable identity/order journal must prevent collisions and preserve
physical source occurrence time. The general persistent raw-observation
journal, secure transport composition and reconnect replay remain separate
reliability work. P/Q/S use the same `esp_timer` millisecond time domain.
Hardware execution, VPS deployment, and network traffic still require
separately reviewed scope and explicit operator intent.

# LOC-021T Concurrent Product Ingress Commitment (planned 2026-09-04)

The following is the retained concurrent-product design and fault-test bar.
ADR-0014 removes its global scheduling priority over bounded single-source
live proof, not its ordering/recovery promises. Any equivalent replacement
must record the migration and execute the same scoped fault invariants.

The retained T design uses more than a shared RAM sequence allocator: it
is a persistent ingress WAL between mapped sensor/SOS producers and the single
Q/O/K drain. Records are ordered by source occurrence time, not callback
completion or handling time. A later-arriving qualified SOS edge may describe
an earlier physical occurrence than a modem result that was ready first.

`LOC-021T0` is an isolated, no-I/O core with injected dual-mirror storage. It
owns fixed-capacity records, stable upstream key/content hashes, per-producer
inclusive `complete_through_ns` watermarks and persistent Location sequence/
observation identity. Append does not allocate a Location sequence. A head may
be sealed, and its sequence allocated in the same durable transaction, only
after every enabled producer watermark covers that occurrence time. The fixed
tie-break is occurrence time, SOS before sensor at equal time, producer rank,
then upstream-key hash. Exact upstream replay returns the original receipt;
same key with different content, rollback, corruption, capacity exhaustion or
sequence exhaustion fails closed. Committed records are never evicted to make
room, and capacity reserves at least a configured SOS quota.

`LOC-021T1` later converts pointer-free owning WAL payloads back into mapped
inputs and is the only product path allowed to invoke full durable SOS or
mapped sensor processing. Signal-only SOS may still preempt an in-flight modem
operation, but only after the manual-SOS event is durable; full SOS waits for O
to return to `IDLE` and then drains in WAL head order. The existing pending-SOS
journal cannot be cleared until T has durably imported the same edge.

An applied head enters `APPLIED_RETAINED`; it is not immediately deleted. K's
reducer/policy state, last identity and retry latch are currently RAM-only, and
an already server-ACKed Location envelope can collide with the outbox tombstone
on replay. Physical compaction therefore requires either a persistent K
checkpoint covering the exact record hash/sequence, or a proven equivalent
full-replay path with exact outbox-tombstone query and no-output replay. This
is a T1 correctness blocker, not a documentation waiver. T0 remains scoped
recovery work; neither T0 nor T1 blocks a separately authorized modem-only S
smoke or finite current-boot/single-source secure live profile.

Required T0/T1 fault tests include: out-of-arrival-order SOS-before-sensor
sealing; stopped and invalid watermarks; exact duplicate versus identity
conflict; write-succeeded/callback-failed readback; power loss after append,
seal, K apply, apply acknowledgement, checkpoint and compaction; dual-slot
corruption/generation conflict; SOS-reserve exhaustion; and static proof that
the eventual product profile has no direct Q mapped/full-SOS bypass.

# Static Slice Ownership (2026-08-23)

The dispatched static work now owns:

- `docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md`;
- `server/location_state_mirror.py` (new, isolated from the live Message Hub);
- `server/location_state_runtime.py` (pure-standard-library admission,
  ordering and projection core for the constrained live runtime);
- `quality_tests/test_location_state_mirror.py` (new focused conformance tests);
- `quality_tests/test_location_state_runtime.py` (schema-oracle differential
  and `python -S` import coverage);
- `server/location_state_store.py` and
  `quality_tests/test_location_state_store.py` (LOC-021B additive SQLite
  persistence, restart recovery and privacy-default projection seam);
- `server/message_hub.py` and `quality_tests/test_location_state_http.py`
  (LOC-021C authenticated bounded HTTP seam only);
- `scripts/deploy_message_hub_vps.ps1` only for packaging the accepted Sensor
  Policy configuration plus the exact runtime imports
  `pc_simulator/sensor_policy_v0.py` and
  `pc_simulator/location_engine_v0.py` alongside the stdlib runtime;
- `shared/contracts/location_state_envelope_v0.schema.json` (new additive
  ingress contract); and
- the matching contract inventory row in `shared/contracts/README.md`;
- `firmware/mqtt_heartbeat/components/location_state_emitter/` and
  `quality_tests/test_location_state_device_emitter.py` for the LOC-021D
  dormant envelope-construction seam and its offline spec fixtures; and
- `firmware/mqtt_heartbeat/components/location_policy_core/` and
  `quality_tests/test_location_policy_core_firmware.py` for the LOC-021E
  dormant, transport-free Sensor Policy decision core and host-oracle golden
  vectors. It does not own `app_main`, the LOC-021D emitter, durable outbox,
  SOS input, HTTPS/server code, public contracts, or pin assignments.
- `server/location_delivery_ack.py` and
  `quality_tests/test_location_delivery_ack.py` for the LOC-021F exact-request-
  byte durable-ingest ACK seam; and
- `firmware/mqtt_heartbeat/components/location_outbox_adapter/` plus
  `quality_tests/test_location_outbox_adapter.py` for the LOC-021G dormant,
  transport-neutral emitter/outbox/positive-ACK adapter. It owns neither the
  emitter or outbox implementation, `app_main`, a storage backend, HTTPS nor
  any task, pin or hardware behavior; and
- `firmware/mqtt_heartbeat/components/location_engine_core/` plus
  `quality_tests/test_location_engine_core_firmware.py` for the LOC-021H
  dormant, transport-free C reducer, bounded snapshot serializer and host-
  oracle/ESP32-S3 compile evidence. It does not own observation acquisition,
  runtime composition, storage, transport, logging, pins or hardware behavior.
- `server/guardian_device_authorization.py` and its focused/server HTTP tests
  for the LOC-021I hashed Guardian-token binding boundary. The server builder
  owns that implementation; LOC-021H does not modify it; and
- `firmware/mqtt_heartbeat/components/location_runtime_pipeline/` plus
  `quality_tests/test_location_runtime_pipeline.py` for the LOC-021J dormant,
  transport-free, single-owner composition of engine, policy, emitter and
  injected outbox adapter. It does not own `app_main`, capture, journal,
  adapter/outbox initialization, storage, HTTPS, tasks, pins or hardware; and
- `firmware/mqtt_heartbeat/components/device_location_runtime/` plus
  `quality_tests/test_device_location_runtime.py` for the LOC-021K default-off
  lifecycle/composition owner and bounded actuator callback seam. It borrows,
  but never initializes or closes, the caller-owned location adapter and shared
outbox; it does not own `app_main`, a task, drivers, transport, storage, pins,
sensors, SOS orchestration or hardware behavior.
- `firmware/mqtt_heartbeat/components/location_hardware_adapter/` plus
  `quality_tests/test_location_hardware_adapter.py` for the LOC-021L
  default-off observation/actuator adaptation boundary. It maps caller-timed
  SIM7670 GNSS/LTE reports, real non-mock platform IMU samples and explicit
  caller-supplied non-mock battery values into LOC-021J/K types. It owns no
  capture task, UART/modem call, clock, journal, storage or `app_main` wiring.
- `firmware/mqtt_heartbeat/components/location_modem_arbiter/` plus
  `quality_tests/test_location_modem_arbiter.py` for the LOC-021N default-off,
  fixed-capacity, no-heap transient scheduler. It owns command-attempt ordering
  and generation-bound cooperative Location cancellation only; the persistent
  outbox retains all durable event, payload, retry, ACK and deletion ownership.
  It owns no executor callback, modem/UART API, task, clock, storage, transport,
  `app_main` wiring, pin or hardware behavior.
- `firmware/mqtt_heartbeat/components/location_modem_executor/` plus
  `quality_tests/test_location_modem_executor.py` for LOC-021O's default-off,
  fixed-storage split-phase composition seam. It owns transient command
  attempts and injected callback result mapping only; it borrows LOC-021K/M,
  the existing P0 delivery runtime and the one shared outbox. It owns no task,
  persistent queue, HTTP success/ACK rule, UART/modem implementation, clock,
  observation identity, `app_main`, pin or hardware behavior. The additive
  read-only dependency-match APIs in `p0_outbox_dispatcher` and
  `p0_delivery_runtime`, with their focused compatibility checks, let O prove
  that P0 retains the exact same outbox and Location adapter; they perform no
  selection, storage mutation or transport operation.
- `firmware/mqtt_heartbeat/components/sim7670_location_modem_adapter/` plus
  `quality_tests/test_sim7670_location_modem_adapter.py` for LOC-021P's
  default-disabled, task-free native SIM7670 GNSS/Cell callback boundary. It
  borrows a pre-initialized UART and one external modem owner, and is absent
  from `app_main`; it owns no UART initialization, task, persistent journal,
  storage, secure transport, clock-domain conversion, pin or live behavior.
- `firmware/mqtt_heartbeat/components/sim7670_location_modem_owner/` plus
  `quality_tests/test_sim7670_location_modem_owner.py` for LOC-021Q's
  compile-only owner/task boundary. It owns one fixed-storage P adapter and O
  executor, one pinned static task, the outer non-recursive mutex, boot-local
  capture sequence generation, explicit exclusive UART initialization and
  GNSS power-off compensation/recovery. O still privately owns its one N
  arbiter and one K runtime; Q borrows but never initializes, copies or closes
  the exact shared persistent outbox, Location adapter or P0 delivery runtime.
  Q remains absent from `app_main`; its Kconfig exclusions do not make the
  current LTE-status application safe because legacy direct callers remain.
  It owns no SOS journal, persistent observation journal, storage backend,
  secure HTTP configuration, pin change, teardown or live product profile.
- `firmware/mqtt_heartbeat/main/loc021s_modem_owner_main.c`, the conditional
  main source selection/Kconfig, `sdkconfig.loc021s_modem_owner.defaults` and
  `quality_tests/test_loc021s_modem_owner_profile.py` for LOC-021S's isolated
  build profile. S owns only fail-closed boot composition and a single optional
  GNSS-status enqueue after Q reaches ACTIVE. It does not own external SOS or
  IMU ingress, direct SIM7670/UART calls, a secure transport, shutdown, pin
  changes, flashing or hardware evidence. The legacy main dependencies remain
  an ESP-IDF two-pass build-graph union, but the legacy main source is mutually
  exclusive and absent from the S compile database/map.

Parallel builders retain `firmware/audio_loop/` and the persistent outbox core
implementation path. LOC-021C now owns its narrow additive changes in
`server/message_hub.py`;
unrelated Message Hub work still requires coordination in the shared file.
This work may read the accepted reference/config/contracts but does not deploy,
flash, contact a device or network, or expose exact coordinates in ordinary
test output. The host-side event-time mirror, SQLite persistence, authenticated
ingest, honest redacted Guardian read and explicit bound-device exact-position
authorization are implemented. The new firmware components are compile/static
evidence only; runtime emission, account-security/UI completion, device
reconnect equivalence, VPS deployment, and hardware evidence remain later
LOC-021 work.

The 2026-09-02 LOC-021A split retains JSON Schema as a development-time oracle
and delegates accepted mutation/projection to the package-free runtime core.
LOC-021B implements SQLite persistence and statically packages
`shared/config/sensor_policy_v0.json` with the service. LOC-021C routes the
existing authenticated, bounded HTTP boundary into `LocationStateStore` and
adds a redacted current-state read. These are local tests only: no deployment,
network operation, device upload, or real Guardian authorization is claimed.

# Validation Commands

```powershell
python -m unittest quality_tests.test_location_state_mirror -v
python -m unittest quality_tests.test_location_state_runtime -v
python -m unittest quality_tests.test_location_state_store -v
python -m unittest quality_tests.test_location_state_http -v
python -m unittest quality_tests.test_location_state_device_emitter -v
python -m unittest quality_tests.test_location_policy_core_firmware -v
python -m unittest quality_tests.test_location_delivery_ack -v
python -m unittest quality_tests.test_location_outbox_adapter -v
python -m unittest quality_tests.test_location_engine_core_firmware -v
python -m unittest quality_tests.test_location_runtime_pipeline -v
python -m unittest quality_tests.test_device_location_runtime -v
python -m unittest quality_tests.test_location_hardware_adapter -v
python -m unittest quality_tests.test_location_modem_arbiter -v
python -m unittest quality_tests.test_location_modem_executor -v
python -m unittest quality_tests.test_sim7670_location_modem_adapter -v
python -m unittest quality_tests.test_sim7670_location_modem_owner -v
python -m unittest quality_tests.test_loc021s_modem_owner_profile -v
$env:EGOLINK_LOC021S_BUILD_DIR = "tmp/loc021s_profile_clean_20260904_c"
python -m unittest quality_tests.test_loc021s_modem_owner_profile -v
python -m unittest quality_tests.test_guardian_device_authorization -v
python -m unittest quality_tests.test_message_hub_server -v
python -m unittest quality_tests.test_location_engine_v0 quality_tests.test_sensor_policy_v0 quality_tests.test_location_policy_replay -v
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Completion Evidence

- Changed files in this isolated slice:
  `server/location_state_mirror.py`,
  `quality_tests/test_location_state_mirror.py`,
  `shared/contracts/location_state_envelope_v0.schema.json`, the contract
  inventory row, the Location Engine/Message Hub boundary docs, the dormant
  `firmware/mqtt_heartbeat/components/location_state_emitter/` component,
  `quality_tests/test_location_state_device_emitter.py`, and this packet.
- Static result on 2026-08-23: LOC-021 focused tests `27/27` PASS; accepted
  LOC/POLICY/REPLAY compatibility tests `50/50` PASS. The root integration set
  passed `132/132` and full repository verification passed `929/929`;
  `context_lint`, JSON parsing and `git diff --check` PASS.
- Configuration identity validated by the seam:
  `egolink.sensor_policy_config.v0.1` /
  `egolink.sensor_policy.semantic.v0.1` /
  `p0-sprint1-engineering-default-20260823` /
  SHA-256
  `c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d`.
- Static capability: the isolated in-memory seam validates the accepted state
  schema plus cross-field/capture semantics, rejects device/boot/session/
  event-time/sequence/observation rollback or conflict, treats exact retries
  idempotently, and keeps timeline/current separate. Receive time is retained
  only as transport evidence. Guardian projection exposes belief/source/age,
  accuracy applicability, heuristic confidence, uncertainty, battery and
  stale/offline truth. Exact position fails closed unless the future API
  adapter explicitly supplies an authorized-location decision; no focused test
  output or task report prints coordinates.
- Hardware result: `NOT_RUN`; no operator-approved integration run is recorded.
- Evidence path: unavailable until the bounded run is authorized.
- Contract boundary: the additive
  `egolink.location_state_envelope.v0.1` schema now binds device/boot/session/
  sequence/observation identity, the nanosecond source-event clock, exact
  Sensor Policy identity and the nested Location Engine state. It does not
  mutate `egolink.p0.v1`. The mirror additionally enforces cross-field clock,
  capture and accepted-config semantics that JSON Schema cannot express.
  `server_receive_time_ms` is transport evidence only and the future trusted
  server adapter must add/overwrite it rather than trusting a device value.
- Remaining risks: the dormant firmware reducer/emitter/outbox seams are not
  composed with observations, product storage or authenticated HTTPS. The C
  behavioral harness is cross-compiled but was not executed because no native
  host compiler or target run is available; serializer/runtime parity is not
  target evidence. Guardian-device authorization now has a local explicit
  binding seam, but account security, provisioning, exact-position UI,
  device-side reboot/reconnect replay, VPS deployment, and representative
  hardware/field/power/RF behavior remain unverified. SQLite restart recovery
  is host-verified but is not device reboot/reconnect evidence. LOC-021 stays
  `in_progress` and `P0-LOC` stays `NOT_RUN`.
- LOC-021A evidence (2026-09-02): schema-oracle compatibility and stdlib
  differential tests cover identical accepted ingest/current/Guardian output,
  shared malformed-boundary rejection, and successful construction under
  `python -S`. This is the accepted admission/reference layer, not device
  behavior.
- LOC-021B static evidence (2026-09-02): the additive SQLite adapter stores an
  append-only accepted envelope timeline, derives current state, overwrites
  untrusted receive time at the service boundary, rehydrates source-event
  ordering after restart, preserves existing Message Hub tables, keeps exact
  position redacted unless authorization is explicit, and fails closed when
  the packaged policy config is absent or differs from the accepted hash.
  Focused tests cover duplicate idempotency, rollback rejection without an
  append, restart recovery, default coordinate redaction and old-DB additive
  migration.
- LOC-021C static evidence (2026-09-02): authenticated
  `POST /api/v1/location-states` reuses the Message Hub JSON body limit and
  stores only server-overwritten receive time; authenticated
  `GET /api/v1/devices/{device_id}/location-state/current` returns a no-store,
  coordinate-redacted projection. Single-token auth explicitly does not claim
  Guardian-device binding. Query unlock is rejected, monotonic-clock freshness
  stays unavailable, and rejected payload/error bodies do not echo coordinates.
  No deployment or external traffic was run.
- LOC-021D static evidence (2026-09-02): a new independent ESP-IDF component
  is designed to wrap an already-evaluated compact Location Engine v0 JSON
  object with device/boot/session/sequence/observation identity, source event
  time and the exact deployed Sensor Policy identity. It checks only the state
  root, contract/event-time binding and absence of device-supplied
  `server_receive_time_ms`; complete state semantics remain owned by the
  accepted server oracle. Device IDs/state/output are bounded at
  256/4096/12288 bytes, SQLite-bound integers fail closed above `INT64_MAX`,
  UTC/monotonic clock-domain rules are explicit, and error/overflow paths are
  designed to clear partial output. The component has only the ESP-IDF `json`
  dependency and no transport, logging, GPIO, NVS or task call; it has no
  coordinate-generation fields. Focused tests pass `10/10`: spec-side UTC and
  monotonic fixtures are accepted by both server oracles, invalid/bounds/
  privacy cases are covered, source boundaries are inspected, and the actual C
  source cross-compiles for ESP32-S3 with warnings as errors. The Python spec
  fixture does not execute the C emitter, so this is not a claim that C output
  ran through the server oracle. Exact C runtime conformance remains for a
  future executable harness or bounded board run. Nothing was linked into the
  active runtime, flashed, deployed or sent over a network.
- LOC-021E static evidence (2026-09-02): the independent
  `location_policy_core` accepts only normalized location snapshots and
  source-event results, keeps the five-mode priority
  `SOS > LOW_BATTERY > LOCATION_UNCERTAIN > MOVING > STABLE`, and emits
  configuration-driven IMU/Cell/GNSS/LTE, last-trusted upload and Ego Call
  actions. It implements GNSS start/continue/timeout/no-fix, capped normal
  exponential backoff, fixed SOS retry, Cell observe/timeout/backoff, battery
  hysteresis and wakeup deadlines. The exact accepted config identity/hash and
  every current JSON value are centralized in a strict native config/default;
  a value change retaining that hash is rejected. This is one build-time frozen
  profile, not runtime configuration loading; Field tuning must produce a new
  reviewed identity/hash and generated validator. Evaluation stages a private
  core copy and rejects event-time regression, malformed normalized input,
  counter exhaustion or `uint64_t` deadline overflow before commit. Camera
  remains unrequested and no coordinate field exists. Raw IMU window/RMS
  normalization is deliberately not ported in this slice: the caller must
  supply attributable, normalized `MOBILITY` events. The focused suite ran 14
  tests: 13 passed and the native-execution test explicitly skipped because no
  host GCC/Clang was available. Host-generated golden traces cover all modes,
  bounded retry/timeout behavior and the frozen previous-mode ordering when a
  GNSS failure and SOS entry share one snapshot. The actual C source and the
  full critical-behavior harness cross-compile for ESP32-S3 with
  `-Wall -Wextra -Werror`. Because that cross-compiled object was not executed,
  C runtime parity, Location Engine/emitter/durable-outbox wiring, reboot
  recovery and target-board behavior remain unverified. No build was flashed
  and no hardware or network action ran. The event API deliberately carries no
  event identity and therefore offers no exactly-once guarantee: an equal-time
  duplicate `GNSS_NO_FIX` advances the counter again, matching the host policy.
  The eventual caller must serialize calls and deduplicate reconnect/replay
  input using complete boot/session/stream/sequence lineage before evaluation.
- LOC-021F host evidence (2026-09-02): authenticated location-state ingest now
  constructs `egolink.persistent_priority_outbox.ack.v0.1` only after the
  SQLite transaction durably accepts the exact envelope or confirms an exact
  idempotent duplicate. `payload_sha256` covers the raw request bytes without
  JSON re-encoding; event and ACK IDs are respectively
  `loc-<payload_sha256>` and `ack-<payload_sha256>`. The response scope is
  exactly `server_durable_ingest_only`, HTTP status alone never authorizes
  device deletion, and no location state or coordinates are echoed. Focused
  ACK coverage passes `5/5`; the root LOC/ACK integration set passes `63/63`.
  This is server durable-ingest evidence only, not Guardian display, human
  acknowledgement, freshness, device queue deletion or `P0-LOC` evidence.
- LOC-021G static evidence (2026-09-02): a new dormant adapter emits a compact
  location envelope into caller-owned scratch, SHA-256 hashes those exact
  bytes, derives `loc-<64 lowercase hex>`, and calls the injected outbox
  enqueue before any send can begin. It preserves source UTC/boot-monotonic
  time kind, event time, boot/session and sequence. Normal records remain
  `location_state` at normal priority; an explicit `SOS_ESCALATED` parameter
  may consume critical reserve without impersonating the separately durable
  `manual_sos` event. The adapter owns initialization of its injected outbox
  object and freezes the same configured device ID, so a mismatched envelope
  is rejected before emission or storage mutation. Scratch is cleared after
  enqueue, and result/error objects retain only bounded IDs, hash, length and
  statuses—not the location payload.
- LOC-021G response handling first persists the caller-classified transport
  result. A non-success transport result never enters ACK parsing. A successful
  transport result only becomes `AWAITING_POSITIVE_ACK`; deletion follows only
  an exact bounded JSON response with `ok=true`, scope
  `server_durable_ingest_only`, the seven-field accepted ACK contract,
  hash-derived `ack-`/`loc-` IDs and the outbox core's exact device/event/raw-
  payload-hash match. Missing, malformed, negative or mismatched ACKs retain
  the record. The actual adapter C cross-compiles for ESP32-S3 with all local
  warnings as errors, and focused coverage passes `12/12`, including an
  `1846`-byte representative emitter envelope checked against the server ACK
  helper. The Python fixture does not execute the C adapter. Runtime parity,
  caller serialization/deduplication, a product-qualified storage backend,
  secure transport, reboot/reconnect, target-board behavior, Guardian delivery
  and `P0-LOC` remain unverified. Durable identity supplies at-least-once
  mechanics; it is not an exactly-once claim. No device, flash or network
  operation ran.
- LOC-021H static evidence (2026-09-02): the new independent
  `location_engine_core` ports all thirteen accepted host event types into a
  bounded structured C observation/lineage API. Only capture-time-bound
  observed/verified GNSS fixes or explicit frozen coarse references can store a
  trusted coordinate. Cell, IMU, LTE, battery, SOS and policy assertions cannot
  create a point. Fine/Coarse freshness, forced or aged Predicted belief,
  uncertainty growth, confidence decay, Unknown expiry, retained trusted
  memory, GNSS lifecycle, mobility, LTE, battery, policy and SOS state follow
  the accepted host defaults. Invalid structural/coarse inputs and event-time
  regressions stage on a private copy and roll back; bad GNSS measurements are
  represented honestly as `fix_rejected`, matching the host reducer.
- LOC-021H configuration is frozen to the accepted Sensor Policy identity/hash
  `p0-sprint1-engineering-default-20260823` /
  `c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d`;
  retaining that hash with any changed Location Engine value is rejected. The
  compact JSON serializer is capped at `4096` bytes, owns no allocation or
  transport, and clears caller-owned output on failure. A spec-side `1698`-byte
  representative snapshot validates against the public schema, passes the
  existing emitter fixture and is admitted by the package-free server oracle.
  Focused coverage passes `8/8` runnable tests with one explicit native-runtime
  skip; the actual C source and full behavioral API harness cross-compile for
  ESP32-S3 under `-Wall -Wextra -Werror`. This compile is not C runtime or
  target-board evidence. The C boundary conservatively caps each lineage ID by
  UTF-8 bytes, caps rule-derived basis IDs at `16`, and accepts only values
  representable by its typed `uint64_t` clocks; larger host-only values fail
  closed during normalization rather than weakening trust.
- LOC-021H intentionally has no duplicate identity. Equal event time is
  accepted exactly as by the host reducer; the future serialized caller must
  deduplicate reconnect/replay observations by complete boot/session/stream/
  sequence lineage before calling. This component does not provide exactly-once
  processing and was not linked, flashed, run on hardware or sent over a
  network. `P0-LOC` remains `NOT_RUN`.
- LOC-021I host evidence (2026-09-02): a configured Guardian token hash now
  binds exact-position access to one exact device; global ingest authentication
  remains a separate boundary and an absent/wrong/device-mismatched binding
  stays coordinate-redacted. A credential-free same-origin
  `/guardian-location` shell performs a one-request bearer read without placing
  the token in URL/storage, clears the token field, renders through
  `textContent`, and sends strict CSP/no-store/referrer/permissions headers.
  Focused authorization/shell coverage passes `8/8` and legacy location HTTP
  coverage passes `9/9`. This is local authorization logic and a minimum shell,
  not deployment, account security, product UI/human acknowledgement or
  `P0-LOC` evidence.
- LOC-021J static evidence (2026-09-02): the new dormant
  `location_runtime_pipeline` gives one caller-owned owner a strict serial path
  through `location_engine_core`, `location_policy_core`, native snapshot
  serialization and `location_outbox_adapter`. Every input repeats its exact
  device/boot/session/stream/sequence/observation/source-time identity. The
  pipeline validates and fingerprints that complete normalized input before
  either reducer. An immediately adjacent exact replay returns duplicate
  without re-evaluating policy or touching the outbox; reused/conflicting
  identity, sequence rollback and source-time rollback fail closed. One fixed
  boot/session/stream is the P0 v0 boundary. A persistent observation journal
  and reboot replay are not implemented, so reboot equivalence is not claimed.
- LOC-021J reduces on private engine/policy copies, maps every supported policy
  event exactly, and deliberately treats `IMU_SAMPLE` as engine-only rather
  than disguising it as another event. A successful policy decision is written
  back to the staged engine before the emitted snapshot. Enqueue is limited to
  a frozen-policy upload action, accepted trusted GNSS/coarse update, any SOS
  event, or explicit initial/current-state publish; routine ticks and IMU do
  not write flash by default. Publish serialization and durable enqueue happen
  before reducer/identity commit. A failed serializer/outbox/full/storage path
  leaves both reducers and identity unchanged, latches `RETRY_REQUIRED`, and
  blocks every different input until the exact input is retried. The validated
  commit identity is materialized before reducers/enqueue, so an enqueue `OK`
  or durable `DUPLICATE` is followed only by infallible bounded assignments.
  This is temporary backpressure, not a lossless capture journal or an
  exactly-once claim.
- LOC-021J focused coverage passes `9/9`. The consolidated LOC regression ran
  `166` tests: `164` passed and the two pre-existing native-runtime cases
  explicitly skipped; slice `git diff --check` passes. The previously pending
  SOS-010E component and focused test are now present, and the shared-tree
  `context_lint` rerun passes. The actual pipeline source and a full
  API/maximum-shape behavioral harness cross-compile for ESP32-S3 with
  `-Wall -Wextra -Werror -Wconversion -Wformat=2 -Wshadow
  -Wsign-conversion`; no cross-compiled C was executed. The narrowed safe-ASCII
  identity cap is `48` bytes. A schema-valid fixture with five maximum-length
  trusted-evidence IDs, all eight reason slots, coarse reference and maximum
  signed-64-bit outer identity serializes to `1845` bytes of state and a
  `2653`-byte envelope, then passes the existing server admission oracle. The
  mechanical native lexical upper bound is `2749` bytes (declared proof ceiling
  `2750`), and `3072` bytes of state scratch plus the exact worst outer-envelope
  overhead `814` is `3886`, below the current `4096`-byte outbox payload limit.
  Target ABI sizes are: private pipeline implementation `6904` inside an
  `8192`-byte public context, engine core `1672`, policy core `584`, caller
  scratch `7170`, and result `464` bytes. Target compiler local stack frames are
  pipeline init `592`, process `384`, engine init `1840`, engine process `1744`,
  policy evaluation `1008`, adapter enqueue `1136`, emitter `80`, and outbox
  enqueue `288` bytes; these are static per-function frames, not measured task
  high-water marks or full mbedTLS/cJSON call-chain evidence.
- LOC-021J performs no logging, allocation, task, sensor, storage-backend,
  partition, transport, pin, hardware, USB, SIM, VPS or network operation. It
  does not initialize/deinitialize the adapter/outbox, is not linked into
  `app_main`, exposes no coordinate in its result, and does not establish
  reboot/reconnect equivalence, runtime behavior, product flash endurance,
  Guardian/human delivery or `P0-LOC` completion.
- LOC-021K static evidence (2026-09-02): the new default-disabled
  `device_location_runtime` gives one external owner fixed init/process/status/
  cancel/close lifecycle calls around LOC-021J. Enabled initialization accepts
  only a caller-initialized location adapter whose exact outbox pointer equals
  the supplied shared persistent outbox. That same outbox must be supplied to
  SOS orchestration, and the caller task or caller-owned mutex must serialize
  location processing, SOS enqueue, send, positive ACK, snapshot, cancel and
  close. The local busy bit rejects recursive entry but is explicitly not a
  cross-task lock. The component never initializes or deinitializes either
  borrowed dependency.
- After LOC-021J has committed the reducers/identity and, when required, the
  durable envelope, LOC-021K invokes synchronous callbacks in the fixed order
  GNSS start, GNSS stop, Cell observe, IMU rate, LTE keep-connected and upload
  intent. Every requested action reports success, failure or missing callback.
  A failed/missing action returns `ACTION_PARTIAL_FAILURE` without rolling back
  an already committed observation or durable envelope and without retrying in
  a loop/background task. IMU rate and LTE keep-connected remember only the
  last successfully applied declaration: the first value, a changed value, or
  a value whose preceding attempt failed is requested; an unchanged successful
  value and a duplicate pipeline input cause no reconfiguration. A later new
  attributable input is required to retry a failed declaration.
- LOC-021K cancel is terminal and close safely invokes the injected cancel seam
  at most once for an active owner, clears borrowed callbacks/dependencies and
  volatile pipeline state, and preserves durable outbox data. Status/results
  expose lifecycle, counters, bounded identifiers/hashes inherited from the
  pipeline and per-action outcomes, but no raw coordinate, observation payload
  or media. The focused suite is OK: `9` runnable tests pass and one native-host
  execution test is explicitly skipped because no host GCC/Clang is installed.
  The actual source and behavioral harness cross-compile for ESP32-S3 with
  `-Wall -Wextra -Werror -Wconversion -Wformat=2 -Wshadow
  -Wsign-conversion`. The consolidated LOC regression passes `237/237` with
  three explicit native-host runtime skips.
- ESP32-S3 target ABI static sizes for LOC-021K are: public owner context
  `10240`, private implementation `8384`, result `504`, status snapshot `120`,
  and caller-owned pipeline scratch `7170` bytes. Compiler local stack frames
  are init `96`, process `80`, cancel `64`, close `64`, current-status `96`,
  with callback helpers no larger than `80` bytes. These are isolated compile
  sizes/local frames, not a measured task high-water mark or full transitive
  call-chain/runtime proof. LOC-021K creates no task or implicit retry and is
  not linked into `app_main`; no driver, sensor, SOS, storage, flash, USB, SIM,
  VPS or network operation ran. Observation-journal replay, real actuator
  integration, reconnect/reboot equivalence, Guardian/human delivery and
  `P0-LOC` completion remain unverified.
- LOC-021L static evidence (2026-09-03): the new dormant
  `location_hardware_adapter` accepts only a caller-supplied boot-monotonic
  source capture time plus complete device/boot/session/stream/sequence/
  observation identity; it has no receive-time input and samples no clock.
  A SIM7670 fix becomes only a candidate when driver/UART/AT state, explicit
  coordinate-valid bits, finite coordinate ranges, `source_status=observed`
  and finite positive HDOP agree. The current SIM7670 report lacks a distinct
  query-observed/parse-valid bit, so `fix=false` is conservatively mapped as a
  GNSS error rather than promoted to `GNSS_NO_FIX`; disabled/error results
  carry no coordinates. The current LTE report likewise lacks per-query valid
  bits: only a completely asserted `LTE_READY` report maps to `ONLINE`, local
  driver/UART/AT absence maps to `UNAVAILABLE`, and every partial status maps
  to `UNKNOWN` rather than invented `OFFLINE`/`LIMITED` truth.
- LOC-021L cell mapping requires bounded MCC/MNC/TAC/cell grammar and a fully
  ready report, canonicalizes TAC/Cell hex case, then hashes the exact device
  scope and cell tuple into `cell:v1:<SHA-256/160>`. This is a stable
  device-scoped pseudonymous reference, not a keyed or anonymous identifier:
  low-entropy values may remain dictionary-recoverable, so the reference must
  not cross the controlled location-evidence domain. It does not retain raw
  cell IDs, operator/IP/raw AT fields or infer a coordinate, radius or
  accuracy. IMU mapping accepts only `sample_is_mock=false` paired with the
  current real driver label `qmi8658_i2c`; mock/unknown/custom labels fail
  closed. That label check is consistency validation, not unforgeable sensor
  attestation, and no mobility class is fabricated. Battery has no default and
  must be caller supplied; mock or non-finite/out-of-range values fail closed.
- LOC-021L does not invoke `sim7670_lte_query_status()` from the serialized
  device-runtime callback. The current synchronous multi-AT API could block
  the shared Location/SOS owner, so Cell observe, GNSS start/stop, dynamic IMU
  rate, LTE keep-connected, upload intent and cancel all explicitly record
  `NOT_SUPPORTED` and return false. A separately owned modem worker/arbiter,
  capture-time/basis binding, single-owner integration, observation journal
  and real action APIs remain live blockers. Focused static/strict target
  compile evidence is recorded by
  `quality_tests/test_location_hardware_adapter.py`: `10/10` focused checks pass,
  including strict ESP32-S3 compilation and relocatable link of the actual
  source plus an API harness that starts actuator storage with a nonzero byte
  pattern. Initialization writes the complete context before deriving its
  internal view; it never inspects uninitialized caller storage. The combined
  LOC-021J/K/L run is `28` PASS with one
  explicit native-host execution skip; `context_lint` and slice
  `git diff --check` pass. No target code, task, UART, sensor, SIM, network,
  flash or hardware operation ran. `P0-LOC` remains `NOT_RUN`.
- LOC-021M static evidence (2026-09-03) adds append-only query evidence to the
  existing `sim7670_gnss_report_t` and `sim7670_lte_report_t`; every legacy
  field and API entry point remains present. Each query now records
  `attempted`, a complete expected response plus terminal-OK observation, and
  command-specific parse validity. Report initialization zeroes the additive
  tail, where false means absence of evidence rather than a negative modem
  state. GNSS additionally records per-query fix/no-fix outcomes. Only the
  exact known all-empty CGPSINFO 9-field or CGNSSINFO 9/18-field grammar is a
  parsed no-fix; timeout, truncation, nonempty malformed data and invalid
  fix coordinates are not. CGNSS no-fix followed by a valid CGPS fix ends as
  `fix=true`, aggregate `no_fix_observed=false`, while retaining the individual
  first-query evidence. Parsing does not write coordinates before a complete
  fix grammar succeeds, so failed fallback cannot carry a partial coordinate.
- LOC-021M LTE parsing returns validity for CPIN, COPS, CEREG, CGATT, CGDCONT,
  CGACT, CGPADDR, CSQ and CPSI. `AT+CEREG?` requires the query form
  `<n>,<stat>`; a one-field response cannot impersonate registration. CGACT
  and CGDCONT scan multi-context responses for CID 1, and CGPADDR requires CID
  1. Driver classification checks each matching proof before reading a false
  content bit: proven SIM-not-ready or not-registered is offline; after proven
  SIM and registration, proven not-attached or inactive CID-1 PDP is limited;
  all four positive core proofs are online; any missing required proof is
  unknown. Local driver/UART/AT failure remains unavailable. Cell admission
  additionally requires one complete, parsed CPSI response and its same-parse
  `cell_identity_valid`; no query invents a coordinate.
- The LOC-021M adapter validates `response_observed => attempted`,
  `parse_valid => response_observed` and mutually exclusive per-query GNSS
  outcomes. A zeroed legacy evidence tail remains accepted but fails closed:
  legacy no-fix is GNSS error and legacy LTE booleans are unknown, never a
  trusted no-fix/online promotion. Focused static/contract coverage is in
  `quality_tests/test_sim7670_report_evidence.py` plus the updated FW-002B and
  hardware-adapter regression suites. LOC-021M focused coverage passes
  `11/11`; the combined report-evidence/FW-002B/hardware-adapter/host-GNSS-
  parser/probe run passes `52/52`. The enabled GNSS/LTE/HTTP parser source and
  adapter/API harness strictly ESP32-S3 cross-compile; an incremental IDF
  compile/link also passes with the application still `0xDACF0` bytes and
  `0x25310` bytes free. `context_lint` and repository `git diff --check` pass.
  Cross-compiled C was not executed. This slice creates no task and performs
  no UART, SIM, network, flash or hardware action; it remains absent from
  `app_main`. Live C parser behavior, modem arbitration, source capture
  identity, target-board validation, Guardian delivery and `P0-LOC` remain
  unverified/`NOT_RUN`.
- LOC-021N static evidence (2026-09-03): the new dormant
  `location_modem_arbiter` is a volatile, fixed-capacity (`8`, including one
  reserved CRITICAL slot), no-heap pure-C scheduling core. It recognizes only
  durable-SOS transport, Location transport, GNSS acquire/status and Cell
  observe attempt tokens plus the dedicated SOS-urgent GNSS attempt. Only
  durable SOS may be CRITICAL; the dedicated GNSS attempt is URGENT and every
  other attempt is NORMAL. At most one token is PREPARED/EXECUTING; priority
  and FIFO selection happen under the caller's external owner, and the owner
  must be released before any future executor performs I/O. The component has
  no executor callback and makes no UART, SIM7670, network, outbox or hardware
  call.
- An admitted CRITICAL SOS bypasses queued NORMAL Location work. At a full
  transient queue it may displace only the newest queued Location attempt and
  returns that exact attempt ID; it never silently evicts GNSS/Cell/SOS work.
  A prepared Location is surfaced by exact ID as cancelled-before-execution.
  An executing Location receives only a same-generation lock-free cooperative
  cancel request. There is no force-stop claim. If cancel wins after the
  conservative execution-start boundary, a late executor result is discarded
  and effect/remote acceptance remain unknown. Generation plus exact operation
  identity reject stale completions. Duplicate, identity-conflict, reserved-
  capacity and full outcomes are explicit. All exhaustion guards run before
  queue/flight identity or count removal; order/generation exhaustion returns
  explicitly without changing lifecycle, identities or counts.
- SOS-urgent GNSS runs after queued CRITICAL SOS and before NORMAL work. It
  coalesces one newest queued NORMAL GNSS/status/Cell attempt with the exact
  displaced kind, operation ID and reason. If seven NORMAL Location attempts
  already consume the non-critical allowance, it instead replaces exactly the
  newest Location attempt and reports a distinct exact-ID reason, never using
  the reserved CRITICAL slot. The Location durable record stays in OUTBOX-010.
  Generic cooperative cancel probes bind both generation and command kind. An
  exact pre-execution cancel reports `NOT_EXECUTED`; if cancel wins after the
  conservative start boundary, all later executor claims are discarded and
  the result is unknown. The additive exact PREPARED retarget seam lets the
  composition align an outbox-proven route without losing its prepared lease,
  and gives the replacement a fresh generation and operation identity.
- Displaced/preempted tokens are only transient execution attempts and are
  reported as cancelled-before-execution; they do not ACK, delete or duplicate
  their durable events. Durability remains exclusively in the shared
  OUTBOX-010 queue, whose owner must create a fresh operation ID for a later
  retry. Arbiter `QUEUED`, `EXECUTION_STARTED`, or `COMPLETED` never means
  `device_location_runtime ACTION_SUCCEEDED`, server durable-ingest ACK, outbox
  deletion or Guardian delivery. The component remains absent from `app_main`
  and owns no task or modem execution.
- Focused static and strict ESP32-S3 compile/relocatable-link coverage is in
  `quality_tests/test_location_modem_arbiter.py`: `14/14` focused checks pass,
  including compilation and relocatable link of the actual source plus API
  harness with the strict component warning set. Cross-compiled target C is
  not executed. No task, UART, sensor, SIM, network, flash or hardware
  operation is performed. Real driver safe points, live concurrency and
  target-board evidence remain blockers. `P0-LOC` remains `NOT_RUN`.
- LOC-021O static evidence (2026-09-03): the new default-disabled
  `location_modem_executor` owns one private N arbiter and one private K
  runtime. Every K callback is deliberately NULL. K therefore preserves its
  accepted `ACTION_PARTIAL_FAILURE` truth after committing an input; O reports
  transient admission separately as `QUEUED` and never upgrades it to
  `ACTION_SUCCEEDED`. K's committed reducer/outbox state is not rolled back by
  an execution-queue failure. No second durable queue, payload copy, HTTP
  success rule or ACK/delete rule is introduced. Enabled initialization also
  requires the existing P0 delivery runtime's transitive read-only proof that
  its dispatcher retains the exact same shared outbox and Location adapter;
  a caller assertion or merely ACTIVE/IDLE status is insufficient and a
  pointer mismatch fails closed.
- O uses the existing P0 delivery runtime as the authoritative durable selector
  and keeps its prepare -> owner-release execute -> owner-reacquire settle
  boundary. A hint/selected-route mismatch in either direction atomically
  retargets the exact unexecuted N ticket to the already-prepared P0 route with
  a fresh generation/operation ID, so the caller can immediately execute and
  settle that retained lease; the hinted route is deferred to a later selector
  pass. It never executes a manual-SOS hint as Location (or vice versa), and it
  never ACKs/deletes a displaced or cancelled Location attempt.
- A durable-SOS signal first invokes the P0 cooperative Location-preemption
  seam, then admits CRITICAL SOS transport, then admits SOS-urgent GNSS. A
  repeated signal always repeats the idempotent P0 hint but does not add
  another urgent GNSS while one is outstanding. One outstanding SOS transport
  is accompanied by only one bounded deferred selector pass, preventing
  repeated hints from growing the transient queue without bound while still
  allowing another durable SOS record to be discovered after settlement. The
  P0 preemption seam itself is lock-free, but O's complete signal function is
  not: it mutates N and O sidecars/deferred flags and therefore requires the
  same external owner as prepare/settle. During owner-released execution an SOS
  producer must acquire that owner before signalling; direct ISR or unlocked
  GPIO/task calls are forbidden. Settle runs only after execution returns and
  the owner is reacquired.
- Injected GNSS/Cell callbacks receive an exact generation/kind, declared
  timeout, and a between-AT cooperative cancel probe; hard cancellation is
  explicitly false. Missing callbacks prove only local no-effect failure.
  Timeout, malformed/invalid reports, callback-contract violations, partial AT
  work and cancel-first/late results are unknown, never fabricated no-fix or
  offline observations. A report is committed only through LOC-021M's typed
  mapper using a mandatory new caller-supplied capture identity; Cell falls
  back to LTE state only for the mapper's exact `CELL_ID_UNAVAILABLE` result.
- O/N focused coverage passes `27/27` (`14` N and `13` O), including strict
  ESP32-S3 compilation and relocatable link of both actual sources plus API
  harnesses. The related N/O/M/K/J/outbox/P0 compatibility set runs `118`
  tests: `116` pass and the two pre-existing native-host execution cases are
  explicitly skipped; target strict compile/link checks pass. The
  implementation is fixed-storage (O public context 24 KiB), no-heap and
  absent from `app_main`. Cross-compiled code was not executed. No task, clock
  read, UART, SIM, modem, HTTP, network, flash or hardware operation ran. The
  current synchronous SIM functions still need reviewed between-AT wrappers
  and cannot be hard-cancelled; a real single-owner task/app wiring, persistent
  observation journal/reboot replay, live concurrency/timeout evidence, secure
  transport, target-board evidence and Guardian delivery all remain blockers.
  `P0-LOC` remains `NOT_RUN`.
- LOC-021P static evidence (2026-09-03): the new default-disabled
  `sim7670_location_modem_adapter` binds the O executor's GNSS and Cell
  callbacks to additive native bounded SIM7670 query entry points. It creates
  no task, has no `app_main` wiring and performs no automatic UART/modem I/O.
  The UART must already be initialized; the caller must serialize one modem
  owner and pass deadlines in the same boot-monotonic `esp_timer` millisecond
  domain used by the adapter. Legacy synchronous GNSS/LTE entry points remain
  unchanged and are deliberately fail-closed at this boundary.
- The bounded driver seam checks the overall deadline and cooperative cancel
  probe between AT commands, while each in-flight command retains a declared
  per-AT cap. Cancellation is therefore cooperative and between-AT only, not a
  hard interrupt. A callback that returns after its deadline/AT cap, any
  partial or ambiguous UART effect, and cancellation after an AT command has
  begun are classified `UNKNOWN`; they are never promoted to a trusted
  observation. GNSS no-fix requires two complete independent query proofs
  (primary plus fallback). LTE admission requires the complete reviewed query
  evidence set; missing or malformed evidence remains unknown. If GNSS power-
  on occurred before an unsuccessful query, this slice has no compensating
  stop/power-off action and reports the resulting disposition conservatively.
- LOC-021P focused coverage passes `13/13`; the independently rerun related
  adapter/report/driver/location set passes `79/79`. Strict ESP32-S3
  cross-compilation covers the GNSS- and LTE-enabled bounded branches. The
  fresh clean ESP-IDF v5.4.2 build at
  `tmp/loc021p_idf_clean_20260903/` uses the default configuration with GNSS
  and LTE disabled, links successfully, and produces
  `egolink_mqtt_heartbeat.bin` at `0xDACF0` bytes with `0x25310` bytes (15%)
  free in the `0x100000` factory partition; SHA-256 is
  `70C2BEF5A332F3BA966C40159D926731609A5026E4647CCD469FECAFC361AAC5`.
  The enabled branches received strict cross-compile evidence only, not a
  complete enabled clean-link build or live run. Nothing was flashed and no
  UART, SIM, network or hardware operation ran.
- Persistent observation journal/reboot replay, a real single-owner modem
  task, secure transport composition, live timeout/cancellation/concurrency
  evidence, target-board validation and Guardian delivery remain pending.
  LOC-021 remains `in_progress`; `P0-LOC` remains `NOT_RUN`.
- Root then completed a fresh final-source ESP-IDF v5.4.2 ESP32-S3 build in
  `tmp/p0_mainline_final_clean_20260903/`. The adapter compiled and linked with
  every current dormant P0 component; the application is `0xDACF0` bytes with
  `0x25310` bytes (15%) free in the `0x100000` factory partition. This is
  compile/link evidence only: the adapter remains unwired and no target or
  hardware action ran.
- LOC-021Q static evidence (2026-09-04): the new default-off
  `sim7670_location_modem_owner` composes one P adapter and one O executor
  around the caller's exact shared outbox, Location adapter and active P0
  delivery runtime. It never creates another N/K/outbox/dispatcher/runtime.
  `init` deep-copies the fixed boot/session/stream/clock scope but creates no
  task or UART effect; explicit `start` creates exactly one pinned static task.
  Only that task may call the exclusive SIM7670 initializer or any bounded
  modem operation. Same-core foreign tasks are therefore rejected by the
  driver's exact `TaskHandle_t` proof, not treated as owners.
- Q preserves O's split phase with one outer non-recursive mutex: prepare and
  settle run while held, execute runs after release, and only the signal-only
  durable-SOS preemption API may take the same mutex during execution. The
  full durable-SOS ingress delegates synchronously to O's authoritative K
  composition only while O is idle; it requires a caller-supplied next
  Location-stream identity from a future shared replayable allocator and does
  not substitute the SOS journal sequence. Q's snapshot is not a reservation.
  A mapped input is likewise used synchronously and never shallow-copied.
- Startup requires a bounded accepted `AT+CGNSSPWR=0` before ACTIVE. Every
  GNSS acquisition is admitted only when O's original deadline has more than
  the configured cleanup reserve remaining. P receives that shortened bound;
  the following never-cancelled power-off uses the lesser of the configured
  reserve and the original deadline's actual remaining milliseconds, never a
  fresh full timeout. If acquisition occurred but no cleanup budget remains,
  Q wipes the report and enters cleanup recovery immediately. Any unconfirmed
  cleanup settles unknown, blocks ordinary work and retries power-off with
  configured backoff; fatal exclusive-owner or O dependency failure cannot be
  bypassed even by durable-SOS ingress. Terminal `OK` is only modem command-
  acceptance evidence, not physical RF-off proof.
- Q is boot-long and has no delete/deinit API; external ingress uses a bounded
  mutex wait, while the owner task is never force-deleted during an in-flight
  AT command. A metadata-locked start claim protects the one static TCB/stack
  from concurrent `start` calls and rolls back only if task creation fails.
  Mapped committed/queue-partial and signal-only SOS queue-partial are exposed
  as distinct top-level partial statuses, never folded into `OK`/`QUEUED`.
  The public snapshot is metadata-only. The fixed target task stack is declared
  in bytes and target compilation asserts the ESP-IDF `StackType_t` byte
  contract. Q focused checks pass `12/12`; the combined Q/P/O regression passes
  `41/41`, and `context_lint` passes. A fresh default-off ESP-IDF v5.4.2
  ESP32-S3 build completed in `tmp/loc021q_idf_clean_20260904/`; Q/P/O compiled
  with their strict warning sets and the final application is `0xDACF0` bytes
  with `0x25310` bytes (15%) free; binary SHA-256 is
  `E2DDFB9166A495757C18F4D08E111FC8DB3DCCD4AC0FC296D29A14D7074699FC`.
  The first cache-enabled attempt exposed a repeatable ccache-wrapped GCC
  internal error in the upstream `esp_lcd` translation unit; repeating the
  same clean tree with `CCACHE_DISABLE=1` completed. This is compile/link
  evidence only: no cross-compiled C ran, no task was created, and no UART,
  SIM, network, flash or hardware action occurred. The component is absent
  from `app_main`; no enabled profile or live concurrency evidence exists, and
  `P0-LOC` remains `NOT_RUN`.
- Before any live Q start, a dedicated application profile must statically
  prove that the legacy heartbeat/sensor LTE-status calls and every other
  direct SIM7670 initializer/query/HTTP path are unreachable. A modem-only Q
  smoke may then use its internal capture sequence without waiting for the
  general observation journal. Before external SOS/IMU/mapped ingress is wired
  concurrently, however, one shared replayable identity/order owner must
  prevent collisions and retain physical occurrence time independently of
  later processing. In particular, an SOS edge during modem execute/settle may
  be older than the sensor completion committed first: read-snapshot allocation
  or substituting handling time would be false. That future composition must
  order/replay those observations or carry a separately contracted occurrence
  time; this Q slice can only fail closed/return partial and does not claim
  full live SOS wiring. Persistent observation reboot replay remains pre-P0
  reliability work; secure transport, task high-water and live deadline/
  cancellation evidence, target-board validation and Guardian delivery also
  remain open.
- LOC-021R static evidence (2026-09-04): O now exposes the sole full durable-
  SOS ingress into its private authoritative K runtime. A caller may invoke it
  only after the physical edge is durably committed or proven an exact replay,
  and must supply the next identity from the same Location stream. R first
  preserves the independent manual-SOS transport/preemption and bounded urgent-
  GNSS signals, then commits one coordinate-free SOS observation, schedules
  its durable Location envelope and applies the Cell intent. It never invents
  a second GNSS request, coordinate, delivery, fix or Guardian-success claim.
- Queue admission remains separate from durable and product truth. A rejected
  Cell attempt is retained with its original bounded timeout. If urgent GNSS
  displaces an already queued Cell token, only the volatile token is removed
  and the Cell obligation is retained. An exact K replay immediately retries
  that obligation and cannot silently change `DURABLE_SOS_PARTIAL` to accepted;
  the deferred state clears only after real arbiter admission. The normal
  selector also retries one retained Cell token after higher-priority SOS and
  Location transport work. IMU rate, LTE keep-connected and Ego Call remain
  explicit product-composition responsibilities rather than fabricated action
  success.
- R focused checks pass `13/13`; the final Q/R/P/O focused selection passes
  `54/54`, including strict ESP32-S3 compilation and relocatable linking of the
  actual sources. Independent Q/R review found no remaining static correctness
  or safety blocker. A fresh default-off ESP-IDF v5.4.2 ESP32-S3 build of the
  final merged source at `tmp/loc021qr_mainline_clean_20260904/` passes and
  produces a `0xDACF0`-byte application with `0x25310` bytes (15%) free;
  SHA-256 is
  `F2C185EB678C8DE4C882C5D9448734661D26C25820D0C9A414E00E3DCF78348B`.
  This remains offline build evidence: R is not wired to a GPIO/journal owner,
  no target code or I/O ran, the dedicated legacy-free application profile and
  shared replayable external-ingress identity/order owner remain open, and
  `P0-LOC`/`P0-SOS` remain `NOT_RUN`.
- LOC-021S static/build evidence (2026-09-04): the new default-off profile
  selects a dedicated `loc021s_modem_owner_main.c` translation unit instead of
  legacy `app_main.c`. It advances one durable NVS boot epoch using
  get -> set -> commit -> readback and fails before Q start on every error or
  safe-integer exhaustion; it never formats or erases NVS. It then initializes
  the outbox partition/storage, the exact shared outbox through the Location
  adapter, the SOS adapter, dispatcher, and P0 delivery runtime in that order.
  Its explicit delivery callback performs no I/O and always returns
  `TRANSPORT_FAILED`/`OFFLINE`, retaining the durable record. Only after Q init
  and successful Q start may it enqueue one bounded GNSS-status request; there
  is no retry, external SOS/IMU/mapped ingress, direct SIM7670/UART call, or
  shutdown/deinit path. Every borrowed dependency remains in file-static
  boot-long storage. Metadata polling reports only non-request-specific owner
  progress and cannot be mistaken for exact GNSS completion evidence.
- A fresh profile-on ESP-IDF v5.4.2 ESP32-S3 build with ccache disabled passes
  at `tmp/loc021s_profile_clean_20260904_c/`. The application is `0x5DC90`
  bytes with `0xA2370` bytes (63%) free in the `0x100000` factory partition;
  SHA-256 is
  `1D9466776D4A388CB4EBE4E853ECFCAD28DDB966460CA3652FB4084099815F5A`.
  Its `957`-row final compile database contains exactly one S main row and zero
  legacy `app_main.c` rows; `build.ninja` and the linker map agree. Final
  `sdkconfig.json` proves profile/GNSS/LTE/Q/custom outbox partition enabled and
  scaffold/HTTP probe/HTTP command loop/location observation/D1/P0 test driver/
  LTE-Wi-Fi failover/Wi-Fi IMU disabled. The partition image contains the
  `ego_outbox` entry. A final-ELF `nm` check finds no legacy SIM7670 HTTP or
  synchronous GNSS/LTE query, platform IMU, SOS input/device/orchestrator, or
  pending-edge-journal symbol; Q's exclusive initializer and bounded modem
  operations remain as intended. The profile's focused source/config/generated
  artifact suite passes `9/9`.
- A fresh final-source default-off build passes independently at
  `tmp/loc021s_default_clean_20260904_b/`, compiles legacy `app_main.c`
  exactly once and S main zero times, and retains the prior `0xDACF0` size with
  `0x25310` bytes (15%) free. Its SHA-256 is
  `A3D300A60E60031A441826659362B25CB956B534D1C3677795571800BE6B5807`.
  The fixed main dependency union is required by ESP-IDF's pre-Kconfig
  component-expansion pass and does not weaken source mutual exclusion. The
  SIM7670 driver uses its existing configured HTTP timeout whenever HTTP is
  enabled and an internal compile-only `30000` ms fallback only for otherwise
  unreachable private HTTP helpers when every HTTP mode is disabled; no HTTP
  feature or runtime call is enabled by that fallback.
- Independent review found no remaining S static correctness/safety blocker.
  The future shared identity owner must be a durable ordered ingress journal,
  not a read-snapshot allocator: it must atomically retain the physical
  occurrence time, stable upstream key, canonical-input hash and assigned
  Location identity; replay exact duplicates, reject conflicts/corruption/
  rollback/exhaustion, and drain only the head. SOS may use the signal-only
  preemption seam during modem execution, but full SOS and sensor completion
  must later share that order before concurrent product wiring. This future
  journal does not block modem-only S. Nothing in S was run on target: no task,
  UART, SIM, modem, flash, network, VPS or hardware action occurred. Live NVS/
  outbox recovery, task stack/deadline behavior, GNSS/Cell truth, secure
  delivery, Guardian visibility and field performance remain unverified;
  `P0-LOC` and `P0-SOS` remain `NOT_RUN`.
- Root-review hardening uses a staging mirror and publishes it only after the
  SQLite transaction commits, preventing memory/disk split-brain. Fault-
  injected write failure leaves both the live and restarted timeline/current
  unchanged. Recovery recomputes and compares every persisted content hash and
  verifies the receive-time column against its JSON evidence; corruption fails
  closed. Reads share the ingest lock. A temporary clean deployment inventory
  constructs `LocationStateStore` under `python -S`; this is static packaging
  evidence only, and no deployment or network action was performed.

# Builder Prompt

```text
Read docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's
context. Begin only after LOC-020, POLICY-010 and REPLAY-010 are independently
accepted. Freeze exact per-file ownership against OPS-004/OUTBOX-010 and record
new focused validation commands before changing execution_state to in_progress.
Implement contract-first device/reference conformance, event-time Message Hub
mirroring and the minimum honest Guardian location surface. Do not add learned
fusion/camera AI, invent coordinates, substitute receive time, or weaken stale/
offline state. Static work may proceed after dispatch; flashing, device/network
commands and real runs require explicit operator intent. Run every validation
command and return changed files, exact outputs, configuration identity,
hardware/evidence paths and remaining risks. Do not mark P0-LOC PASS.
```

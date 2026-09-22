---
id: OUTBOX-010
title: Persistent priority outbox
status: active
priority: critical
lane: C
execution_state: parked
depends_on: []
serves_gate: P0-SOS
requires_hardware: true
created: 2026-08-23
last_updated: 2026-09-03

context:
  - docs/architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/current/ACTIVE_BUILD.md
  - docs/development/PROTOCOL.md
  - docs/development/LTE_TRANSPORT.md
  - docs/safety/SAFETY_CONTRACT.md
  - docs/tasks/active/OPS-004_DEVICE_HTTPS_INGRESS.md
  - firmware/mqtt_heartbeat/components/p0_outbox_dispatcher/include/p0_outbox_dispatcher.h

allowed_paths:
  - docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md
  - docs/development/PROTOCOL.md
  - docs/safety/SAFETY_CONTRACT.md
  - firmware/mqtt_heartbeat/
  - firmware/mqtt_heartbeat/components/p0_delivery_runtime/
  - server/
  - shared/contracts/
  - pc_simulator/
  - quality_tests/
  - quality_tests/test_p0_delivery_runtime.py

out_of_scope:
  - reusing any completed task identifier for this outbox work
  - buffering RTC media, recordings or arbitrary large payloads
  - introducing a general broker or changing unrelated protocols
  - claiming a RAM cache or successful send call is durable delivery
  - hiding overflow, deleting before positive ACK or fabricating event time
  - flashing, rebooting, disconnecting or commanding hardware without explicit
    operator intent
owner: unassigned
reviewed_at: 2026-09-22
---

# Goal

Provide the smallest persistent, priority-aware Store-and-Forward outbox needed
for SOS and other critical events: write before send, retain stable identity
through retries/reboots, and delete only after an idempotent positive ACK.

# Acceptance

- [ ] A critical event is durably written with stable event ID, source event
      time, boot/session lineage, type, priority and payload hash before send.
- [ ] Retry, reconnect and reboot preserve identity and source time; VPS ingest
      and ACK handling are idempotent and observable.
- [ ] The only durable local copy is removed only after a valid positive ACK
      for the same device/event/payload identity.
- [ ] Capacity, queued count, oldest age, attempts, next retry, ACK state and
      corruption/overflow/drop reason are bounded and observable.
- [ ] Priority rules prevent lower-priority observations from silently evicting
      an SOS event; if critical capacity is exhausted, local failure remains
      explicit and the event is never reported delivered.
- [x] Focused tests cover write-before-send, failed send, duplicate ACK,
      wrong/stale ACK, retry backoff, reboot recovery, corruption, full queue
      and priority overflow without depending on live hardware.
- [ ] One operator-approved exact-board drill proves power-cycle and network-
      unavailable recovery, recording board, image, connection, timestamps and
      private evidence path.
- [x] Completion does not claim authenticated ingress (OPS-004), full SOS
      closure (SOS-010) or `P0-SOS PASS`.
- [x] A default-disabled, offline unified delivery runtime drives exactly one
      dispatcher begin, at most one bounded injected POST, and exactly one
      dispatcher finish for each ready attempt; uncertain durable settlement
      is retained for explicit recovery without another selector or POST.

# Dispatch Boundary

Before implementation, freeze exact per-file ownership against LOC-021 and
OPS-004 in shared firmware/server paths and record focused test/build commands.
Static fixtures may proceed without hardware. Power-cycle, disconnection,
flash and device commands require explicit operator intent.

## Dispatched Static Reference Slice

This first slice is isolated from the concurrent LOC-021 and OPS-004 work. It
owns exactly these paths:

- `docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md`
- `pc_simulator/persistent_priority_outbox.py`
- `shared/contracts/persistent_priority_outbox_v0.schema.json`
- `quality_tests/test_persistent_priority_outbox.py`

It must not modify `server/message_hub.py`, `firmware/mqtt_heartbeat/`, any
Location Engine/Sensor Policy/Replay file, deployment state, or hardware. The
Python implementation is a crash/reopen semantics reference backed by ordinary
host files in temporary test directories. It is not a claim about ESP32 NVS,
flash endurance, brownout atomicity, authenticated VPS ACKs, or product
durability.

## OUTBOX-010B Isolated Device Core Slice

This slice owns exactly these paths while LOC-021, SOS-010 and OPS-004 proceed
in parallel:

- `docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md`
- `firmware/mqtt_heartbeat/components/persistent_priority_outbox/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/persistent_priority_outbox/include/persistent_priority_outbox.h`
- `firmware/mqtt_heartbeat/components/persistent_priority_outbox/persistent_priority_outbox.c`
- `quality_tests/test_persistent_priority_outbox_device_core.py`

It must not modify or connect `app_main.c`, the location-state emitter, SOS
GPIO/input, modem/HTTPS transport, Message Hub/server code, the public outbox
schema, or the existing Python reference. The component is a fixed-capacity
device algorithm with an injected two-slot blob-storage boundary. A successful
storage callback is an adapter obligation; this slice supplies no NVS adapter
and therefore makes no NVS, flash-endurance, brownout-atomicity, hardware or
product-durability claim. Raw RTC media is rejected and never enters a slot.
The compile-time proof ceiling is four queued records with up to 4096 exact
payload bytes each. This admits the current roughly 1.8 KiB representative
LOC-021 envelope while keeping two complete validated images (current plus
rollback/init scratch) inside the 48 KiB caller-owned opaque core. It is an
explicit RAM/capacity tradeoff for this isolated algorithm slice, not product
queue sizing; larger emitter output remains an explicit overflow until a
measured storage/workspace design is selected.
The Xtensa ESP32-S3 build fixes storage format v1 at 22,240 bytes per raw image,
so the two injected slots need at least 44,480 raw bytes before any backend
metadata, wear-leveling or atomic-write overhead. The current
`mqtt_heartbeat/sdkconfig` selects ESP-IDF `partitions_singleapp.csv`, whose NVS
partition is only `0x6000` = 24,576 bytes. No current partition is therefore
claimed compatible. The next persistence slice must select and verify a custom
raw partition or deliberately resized NVS/storage backend before integration.
The raw C layout is guarded by a compile-time 22,240-byte format-v1 assertion;
any layout change requires a format version and migration decision rather than
silently treating older recoverable data as corruption.
Recovery selects the highest independently hashed valid generation; a stale or
damaged peer slot stays observable, while same-generation different content
fails closed. This local pair cannot detect an external rollback that restores
both slots to an older mutually consistent image; a monotonic secure anchor is
an integration/product requirement.
The core is deliberately lock-free, not thread-safe: one owner task or an
external caller mutex must serialize every LOC/SOS/send/ACK/snapshot call, and
storage callbacks must not re-enter it. The 48 KiB core, the current 4,776-byte
send item and the 3,136-byte snapshot are caller-owned working memory and must
not be placed on an ordinary firmware task stack.

Focused/static validation for this slice:

```powershell
python -m unittest quality_tests.test_persistent_priority_outbox_device_core -v
python -m unittest quality_tests.test_persistent_priority_outbox -v
python scripts/context_lint.py
git diff --check
```

The component enables warnings-as-errors in its own CMake target. An ESP-IDF
5.4.2 build of `firmware/mqtt_heartbeat` may be run into a disposable `tmp/`
build directory without flashing. Python/static tests do not execute Xtensa C
and must not be reported as C runtime or persistence evidence.

## OUTBOX-010C Build-only Raw Partition Adapter Slice

This slice owns exactly these paths:

- `docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md`
- `firmware/mqtt_heartbeat/components/persistent_priority_outbox_partition/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/persistent_priority_outbox_partition/include/persistent_priority_outbox_partition.h`
- `firmware/mqtt_heartbeat/components/persistent_priority_outbox_partition/persistent_priority_outbox_partition.c`
- `firmware/mqtt_heartbeat/partitions_outbox.csv`
- `firmware/mqtt_heartbeat/sdkconfig.outbox_partition.defaults`
- `quality_tests/test_persistent_priority_outbox_partition.py`

It must not connect `app_main.c`, LOC/SOS emitters, transport or ACK paths; alter
the default partition profile; flash, erase or command a device; or claim a
hardware power-loss result. It supplies a synchronous injected-storage adapter
for one explicitly labeled custom raw partition and an additive build-only
profile. Two erase-aligned 24 KiB slots hold one exact 22,240-byte format-v1
image each. Adapter initialization performs read-only partition discovery and
geometry validation and never erases. A slot write erases only the requested
slot; after provisioning, that is the inactive mirror. It writes one
exact image and verifies it in bounded 256-byte chunks before returning
success. The adapter is lock-free and must share the core's single-owner or
external-mutex discipline.
RAM-only saturating counters expose slot erase attempts/successes, bytes whose
partition-write API returned success, and readback failures without retaining
payload content.
They reset on adapter initialization/reboot and are field-test diagnostics, not
persistent lifetime or endurance evidence.

Alternate-slot recovery applies only after at least one valid mirror exists.
On first-ever empty-store initialization, reset during the first slot write can
leave one torn slot plus one erased slot. The core correctly fails closed as
storage corruption on reboot, but it cannot self-recover or distinguish that
state from other corruption. An explicit provisioning/format-recovery flow and
its operator authorization are pending; this slice makes no universal reset-
recovery claim for an unprovisioned partition.

The raw partition adds integrity/tear-recovery mechanics only. It does not
provide at-rest confidentiality or prove flash encryption/key lifecycle,
erase remanence, write endurance, brownout behavior, or device recovery. The
product partition/security profile must decide and verify those separately;
this build-only slice intentionally does not enable an encryption flag.
Its full-image scheme also means every enqueue, attempt-start, transport-result,
ACK or observable-failure mutation erases one complete 24 KiB slot (six 4 KiB
sectors) and rewrites 22,240 bytes. This is acceptable only as a bounded
engineering crash-recovery backend. `OUTBOX-010D` append/journal or a measured
wear-levelled backend is a pre-product blocker before normal location cadence.

Focused validation for this slice:

```powershell
python -m unittest quality_tests.test_persistent_priority_outbox_partition -v
python -m unittest quality_tests.test_persistent_priority_outbox_device_core -v
python scripts/context_lint.py
```

The ESP-IDF validation uses a new dedicated SDKCONFIG and build directory,
explicit `IDF_TARGET=esp32s3`, and additive defaults
`sdkconfig.defaults;sdkconfig.outbox_partition.defaults`. It parses the emitted
partition-table binary and checks app fit, but does not flash or run it.

# Validation Commands

```powershell
python scripts/context_lint.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

The static slice's focused/schema commands below satisfy its dispatch
requirement. Add exact firmware/server build and integration commands before
those later paths enter `in_progress`.

Static reference commands for this dispatched slice:

```powershell
python -m unittest quality_tests.test_persistent_priority_outbox -v
python -m json.tool shared/contracts/persistent_priority_outbox_v0.schema.json > $null
python scripts/context_lint.py
git diff --check
```

There is no firmware build in this slice because firmware paths are explicitly
reserved from it. The root integrator runs `scripts/verify.ps1` once after the
parallel LOC-021/OUTBOX slices merge; it is intentionally not duplicated while
those working-tree changes are concurrent.

# Completion Evidence

- Changed files:
  - `docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md`
  - `pc_simulator/persistent_priority_outbox.py`
  - `shared/contracts/persistent_priority_outbox_v0.schema.json`
  - `quality_tests/test_persistent_priority_outbox.py`
- Static reference result: two atomically replaced host-file mirrors retain a
  hashed immutable identity over device/event/type/priority/payload/source-time/
  boot/session/sequence, attempt lineage and bounded ACK tombstones. No queue
  item is automatically evicted. Critical record slots and a derived critical
  payload-byte budget are both reserved from noncritical traffic; exhausted
  capacity is persisted as an explicit failure.
- Validation result:
  - focused regression: `17/17 PASS`;
  - JSON parse plus Draft 2020-12 schema self-check/document validation: `PASS`;
  - `python scripts/context_lint.py`: `PASS`;
  - `git diff --check`: `PASS` (line-ending warnings in pre-existing concurrent
    files only);
  - full `scripts/verify.ps1`: pending one root-level merged run.
- Hardware result: `NOT_RUN`; no power-cycle/offline drill is authorized.
- Static evidence paths: the implementation, schema and focused test paths
  listed above. Test persistence used disposable temporary directories only.
- Hardware evidence path: unavailable until an operator-approved run completes.
- Remaining risks: this is single-process host JSON, not product NVS. Storage
  selection/endurance, brownout guarantees, device/server integration, real
  reboot/network-loss drills, queue sizing and critical overflow remain
  unverified. ACKs are identity-matched but unauthenticated until OPS-004/server
  integration. Tombstones are intentionally bounded and pruning is observable,
  so an ancient duplicate ACK becomes `stale_or_unknown`; product retention
  sizing must be established. The payload privacy deny-list rejects common
  coordinate/media shapes but does not replace an integration-level allow-list
  and privacy review.

## OUTBOX-010B Device Core Evidence - 2026-09-02

- Changed files:
  - `docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md`
  - `firmware/mqtt_heartbeat/components/persistent_priority_outbox/CMakeLists.txt`
  - `firmware/mqtt_heartbeat/components/persistent_priority_outbox/include/persistent_priority_outbox.h`
  - `firmware/mqtt_heartbeat/components/persistent_priority_outbox/persistent_priority_outbox.c`
  - `quality_tests/test_persistent_priority_outbox_device_core.py`
- Device algorithm result: fixed capacity with separate critical record and
  byte reserves; no eviction; exact persisted/transmitted payload-byte SHA-256;
  stable device/event/type/priority/source-time/boot/session/sequence identity;
  committed attempt/backoff metadata before send; transport acceptance only
  enters `AWAITING_POSITIVE_ACK`; deletion requires positive exact
  `device_id + event_id + payload_sha256`; bounded ACK tombstones; explicit
  overflow, corruption, recovery and ambiguous-write fault states.
- LOC interoperability fixture: current representative compact LOC-021 event is
  1,801 bytes, greater than 1 KiB and within the 4,096-byte compile ceiling.
  `payload_sha256` covers those exact bytes with no JSON canonicalization; the
  transport integration must transmit exactly `payload_length` bytes.
- ESP32-S3 build result: ESP-IDF v5.4.2 compile and link `PASS`; the component
  compiled with `-Wall -Wextra -Werror -Wconversion -Wformat=2 -Wshadow
  -Wsign-conversion`. Existing unrelated `app_main.c` unused-symbol warnings
  remained non-fatal outside this component. No flash or device command ran.
- Exact build invocation:

  ```powershell
  $env:IDF_PATH = 'C:\Espressif\v5.4.2\esp-idf'
  $env:IDF_TOOLS_PATH = 'C:\Espressif\tools'
  $env:IDF_PYTHON_ENV_PATH = 'C:\Espressif\tools\python\v5.4.2\venv'
  $env:PATH = 'C:\Espressif\tools\cmake\3.30.2\bin;C:\Espressif\tools\ninja\1.12.1;C:\Espressif\tools\ccache\4.10.2\ccache-4.10.2-windows-x86_64;C:\Espressif\tools\xtensa-esp-elf\esp-14.2.0_20241119\xtensa-esp-elf\bin;' + $env:PATH
  & 'C:\Espressif\tools\python\v5.4.2\venv\Scripts\python.exe' 'C:\Espressif\v5.4.2\esp-idf\tools\idf.py' -C firmware/mqtt_heartbeat -B D:\pywork\egolink\tmp\outbox010b_idf_build -D SDKCONFIG=D:\pywork\egolink\tmp\outbox010b_sdkconfig build
  ```

- Xtensa build sizing: storage image = 22,240 bytes (`0x56e0`), two raw slots =
  44,480 bytes before backend overhead, opaque core implementation = 44,528
  bytes within its 49,152-byte allocation, send item = 4,776 bytes, snapshot =
  3,136 bytes. These are build facts, not product sizing or existing-partition
  compatibility claims. Removing payload-sized automatic arrays reduced the
  Xtensa `egolink_outbox_enqueue` frame from 4,848 to 176 bytes and
  `validate_payload` from 4,144 to 48 bytes; cJSON callee stack/heap still needs
  integration measurement.
- Validation result:
  - device focused static/spec suite: `14/14 PASS`;
  - existing host reference suite: `17/17 PASS`;
  - `python scripts/context_lint.py`: `PASS` before final packet evidence edit;
  - real Xtensa C compile/link: `PASS`;
  - full `scripts/verify.ps1`: pending one root-level merged run.
- C-runtime/persistence evidence: `NOT_RUN`. The Python suite statically checks
  C invariants and reuses host fixtures but does not execute this C object. The
  OUTBOX-010B core slice itself provided no storage adapter; the separate
  OUTBOX-010C build-only raw-partition adapter below is compiled but remains
  unwired and unexecuted. No reboot/brownout drill, flash-endurance result,
  hardware run, or authenticated ACK integration exists in this slice.
- Remaining device risks: choose and test a sufficiently large atomic storage
  backend/partition; measure write amplification and endurance; enforce the
  single-owner/mutex rule in integration; add a payload allow-list and at-rest
  privacy decision; add actual C runtime fault-injection tests; validate stack
  and heap margins; add a secure monotonic anchor if rollback detection is a
  product requirement. Server ACK authentication remains OPS-004 scope.

## OUTBOX-010C Partition Adapter Evidence - 2026-09-02

- Changed files:
  - `docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md`
  - `firmware/mqtt_heartbeat/components/persistent_priority_outbox_partition/CMakeLists.txt`
  - `firmware/mqtt_heartbeat/components/persistent_priority_outbox_partition/include/persistent_priority_outbox_partition.h`
  - `firmware/mqtt_heartbeat/components/persistent_priority_outbox_partition/persistent_priority_outbox_partition.c`
  - `firmware/mqtt_heartbeat/partitions_outbox.csv`
  - `firmware/mqtt_heartbeat/sdkconfig.outbox_partition.defaults`
  - `quality_tests/test_persistent_priority_outbox_partition.py`
- Compiled adapter result: exact label `ego_outbox`, data subtype `0x40`,
  49,152-byte partition, two erase-aligned 24,576-byte slots, exact
  22,240-byte images, and 256-byte bounded readback chunks. Initialization is
  read-only discovery/geometry validation. Each storage mutation erases only
  its selected slot, writes the exact image and clears its readback buffer with
  a non-optimizable volatile wipe after success or failure. RAM-only saturating
  counters expose erase attempts/successes, partition-write-API success bytes
  and readback failures;
  they contain no payload bytes and are not lifetime accounting.
- Recovery boundary: the alternate-slot design preserves a valid predecessor
  across a torn later write only after at least one valid mirror exists. Reset
  during the first-ever first-slot write can leave torn-plus-erased slots; on
  reboot the core fails closed as corruption and cannot self-format. Explicit
  provisioning/format recovery remains pending and no universal reset-recovery
  claim is made.
- Exact ESP-IDF v5.4.2 build invocation (the build directory and SDKCONFIG did
  not exist before the initial invocation; the same command rebuilt the final
  adapter source after the diagnostic counters were added):

  ```powershell
  $env:IDF_PATH = 'C:\Espressif\v5.4.2\esp-idf'
  $env:IDF_TOOLS_PATH = 'C:\Espressif\tools'
  $env:IDF_PYTHON_ENV_PATH = 'C:\Espressif\tools\python\v5.4.2\venv'
  $env:PATH = 'C:\Espressif\tools\cmake\3.30.2\bin;C:\Espressif\tools\ninja\1.12.1;C:\Espressif\tools\ccache\4.10.2\ccache-4.10.2-windows-x86_64;C:\Espressif\tools\xtensa-esp-elf\esp-14.2.0_20241119\xtensa-esp-elf\bin;' + $env:PATH
  & 'C:\Espressif\tools\python\v5.4.2\venv\Scripts\python.exe' 'C:\Espressif\v5.4.2\esp-idf\tools\idf.py' -C firmware/mqtt_heartbeat -B D:\pywork\egolink\tmp\outbox010c_final_idf_build -D IDF_TARGET=esp32s3 -D SDKCONFIG=D:\pywork\egolink\tmp\outbox010c_final_sdkconfig -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.outbox_partition.defaults' build
  ```

- ESP-IDF result: `PASS`, including final-source compile/link. The adapter C
  object used `-Wall -Wextra -Werror -Wconversion -Wformat=2 -Wshadow
  -Wsign-conversion`. Existing unrelated `app_main.c` unused-symbol warnings
  remained non-fatal. The missing `ESP_ROM_ELF_DIR` produced only the known
  non-fatal gdbinit-generation warning.
- Independently parsed emitted `partition-table.bin`:

  ```text
  nvs,data,nvs,0x9000,24K,
  phy_init,data,phy,0xf000,4K,
  factory,app,factory,0x10000,1M,
  ego_outbox,data,64,0x110000,48K,
  ```

  The clean dedicated SDKCONFIG records target `esp32s3`, 2 MB flash, custom
  table enabled, filename `partitions_outbox.csv`, and table offset `0x8000`.
  The emitted app is 896,240 bytes (`0xdacf0`) in a 1,048,576-byte factory
  partition, leaving 152,336 bytes (`0x25310`, 15%); the emitted partition
  binary is 3,072 bytes.
- Validation result:
  - partition adapter static/spec suite: `8/8 PASS`;
  - device core static/spec suite: `14/14 PASS`;
  - existing host reference suite: `17/17 PASS`;
  - `python scripts/context_lint.py`: `FAIL` in the concurrent merged worktree
    only because `CALL-020_LTE_DATA_VOICE_POC.md` currently names three paths
    not yet present; none is owned by this slice. Root merged rerun pending;
  - ESP32-S3 warnings-as-errors component compile and full link: `PASS`;
  - emitted partition-table parse/verification and app-size check: `PASS`;
  - full `scripts/verify.ps1`: pending one root-level merged run.
- Wiring/hardware result: `NOT_RUN`. The additive partition profile is not the
  default; `app_main.c` does not initialize the adapter; no adapter I/O,
  flash/erase/device command, network action, reboot, brownout or hardware test
  ran. Static tests and a successful build are not runtime power-loss evidence.
- Product nonclaims/blockers: this raw partition provides integrity and
  tear-recovery mechanics only, not at-rest confidentiality. Flash encryption,
  key lifecycle, erase/privacy behavior and data-remanence policy remain a
  separate product decision and verification task. Every full-image enqueue,
  attempt-start, transport-result, ACK or persisted failure erases six 4 KiB
  sectors and rewrites 22,240 bytes. This adapter is bounded field-test
  infrastructure, not suitable for normal location cadence or claimed flash
  endurance. `OUTBOX-010D` must select and measure an append/journal or
  wear-levelled backend before product integration.

## OUTBOX-010E — Unified P0 Delivery Dispatcher

`OUTBOX-010D` remains reserved for the pending append/journal persistence
backend. This independently numbered E slice closes the selector/routing seam
left by the SOS outbox adapter's explicit `NON_SOS_HEAD` result. It owns only:

- `docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md`
- `firmware/mqtt_heartbeat/components/p0_outbox_dispatcher/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/p0_outbox_dispatcher/include/p0_outbox_dispatcher.h`
- `firmware/mqtt_heartbeat/components/p0_outbox_dispatcher/p0_outbox_dispatcher.c`
- `quality_tests/test_p0_outbox_dispatcher.py`

The component is default-disabled, synchronous and transport-free. It borrows
one caller-initialized shared outbox plus its already-bound location and SOS
adapters, verifies exact pointer/device identity, and never initializes,
closes, unbinds or deinitializes those dependencies. Exactly one external
owner or mutex must serialize enqueue, selection, transport completion, ACK,
cancel and close. The same SOS adapter may also be borrowed by the SOS runtime
for identity/lifecycle checks, but only this dispatcher may call its send
`begin`/`finish`; a second SOS adapter or second selector is forbidden.

One SOS-adapter `begin` call performs the only priority selection. A strict
CRITICAL `manual_sos` is routed to the SOS endpoint and finish contract. Its
`NON_SOS_HEAD` handoff is admitted only as `location_state` when record state,
priority, lineage IDs, `loc-<payload_sha256>` identity and the SHA-256 of the
exact persisted payload bytes all match. Full location-envelope semantics
depend on the existing invariant that `location_outbox_adapter` is the only
location producer; this dispatcher deliberately does not add a second JSON
parser. Unknown or invalid heads are durably failed and retained, never sent.
The typed borrowed view contains exact payload bytes, endpoint path, bounded
response ceiling, priority, source time, boot/session/sequence and attempt
identity, but no bearer, Guardian or device-auth credential.

Finish is bound to the dispatcher's private route and exact attempt identity;
the transport caller cannot redirect one attempt through the other response
parser. A 2xx transport result alone never deletes. Deletion occurs only when
the route adapter accepts an exact positive ACK scoped to
`server_durable_ingest_only`. This is server durable-ingest acknowledgement,
not Guardian display, human acknowledgement, Call success, exactly-once
execution or a P0 gate result.

Terminal delete/duplicate/failure outcomes clear both the caller view and the
private payload-bearing send item. There is one required transactional
exception: if the SOS adapter cannot persist its transport or ACK mutation,
its existing retry contract retains the private canonical send item and active
identity, while the caller-visible payload remains cleared. The dispatcher
returns `MUST_FINISH_OR_RECOVER`; cancel and close cannot discard that state.
A location bad response/scope/ACK, including a durably recorded identity or
stale-ACK rejection, is instead terminal for that attempt only: the record is
retained and becomes selectable again after the attempt's already-persisted
backoff. Storage/fault/crypto/counter or otherwise uncertain attempt state is
the narrower location recovery case. An attempt/view mismatch likewise clears
the outward payload and returns a completion-only identity so the exact active
route can be finished after recovery; it never starts another selector.

Focused validation for this slice:

```powershell
python -m unittest quality_tests.test_p0_outbox_dispatcher -v
python -m unittest quality_tests.test_location_outbox_adapter quality_tests.test_location_delivery_ack -v
python -m unittest quality_tests.test_sos_outbox_adapter quality_tests.test_manual_sos_delivery_ack -v
python -m unittest quality_tests.test_persistent_priority_outbox quality_tests.test_persistent_priority_outbox_device_core quality_tests.test_persistent_priority_outbox_partition -v
python scripts/context_lint.py
git diff --check
```

### OUTBOX-010E Evidence — 2026-09-02

- Changed files are the five E-slice paths listed above; no `app_main`, sensor,
  pin, partition, storage backend, HTTP implementation or adapter public
  contract was changed.
- Runnable host interoperability covers a bad 2xx location ACK with wrong
  device identity, durable retention, the persisted one-second retry deadline,
  a new attempt, duplicate durable server ingest, exact positive ACK and final
  tombstoned deletion. A separate representative trusted-location envelope is
  1,799 exact UTF-8 bytes; accepted and duplicate SQLite ingest produce the
  same `loc-/ack-<sha256>` identity over those exact bytes. These are host
  reference results, not execution of the target C object.
- ESP32-S3 warnings-as-errors compile of the actual source and public/private
  size probes: `PASS` with `-std=c11 -Wall -Wextra -Werror -Wconversion
  -Wformat=2 -Wshadow -Wsign-conversion`. Xtensa sizes are dispatcher opaque
  context 8,192 bytes, implementation 5,464 bytes, send view 592 bytes,
  snapshot 664 bytes, begin result 32 bytes and finish result 48 bytes. The
  largest compiler-reported local frame is 160 bytes in exact payload hashing;
  public entry frames are at most 128 bytes. Dependency parser/crypto call
  depth and heap remain integration measurements.
- Final E focused suite: `12/12 PASS`, including actual ESP32-S3 strict compile
  and runnable host retry/ACK interoperability. The full location-pattern
  regression passed `158/158` with two environment-guarded native-C skips;
  the full outbox-pattern regression passed `39/39`. The focused location
  adapter/ACK and SOS adapter/ACK subsets separately passed `17/17` and
  `21/21`.
- The concurrently changing SOS-G tree was not an E regression: its broad SOS
  pattern run had `62 PASS`, one guarded native-C skip and two transient
  failures because `sos_device_runtime.h` already referenced the not-yet-
  present `sos_pending_edge_journal.h` and its packet evidence had not yet
  gained a new expected phrase. This E slice did not edit those paths.
  `python scripts/context_lint.py` was likewise blocked only by two concurrent
  task-packet paths not yet present:
  `quality_tests/test_ego_call_tls_stream_adapter.py` in CALL-020 and
  `quality_tests/test_sos_pending_edge_journal.py` in SOS-010. Root merged
  rerun is required after those owners land. `git diff --check` passed; it
  emitted only line-ending warnings for pre-existing concurrent files.
- The cross-compiled object was not executed. No storage callback,
  raw-partition write, network, VPS, SIM, USB, flash, reboot, brownout, device
  or hardware action ran.
- Remaining product blockers include `OUTBOX-010D` wear-suitable persistence,
  provisioning/recovery, authenticated deployed transport, complete target
  runtime/fault-injection tests, end-to-end offline/power-cycle drills, queue
  sizing/endurance/privacy validation and the single-owner runtime wiring.
  This slice does not establish Guardian/human delivery, P0-SOS or P0-LOC.

## OUTBOX-010F - Unified Delivery Runtime

This isolated slice owns only:

- `docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md`
- `firmware/mqtt_heartbeat/components/p0_delivery_runtime/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/p0_delivery_runtime/include/p0_delivery_runtime.h`
- `firmware/mqtt_heartbeat/components/p0_delivery_runtime/p0_delivery_runtime.c`
- `quality_tests/test_p0_delivery_runtime.py`

The component is default-disabled, synchronous and offline. It borrows one
already-active/idle OUTBOX-010E dispatcher and becomes that dispatcher's only
`begin`/`finish`/`cancel`/`close` driver. It does not initialize or close the
shared outbox, either route adapter, a storage backend, an HTTP client, a task,
SIM state or credentials. It remains dormant and is not connected to
`app_main.c`.

For one ready `manual_sos` or `location_state` head, `drive_once` calls the
dispatcher selector exactly once, calls one injected synchronous POST callback
with the fixed route path and exact borrowed persisted payload bytes, then
calls dispatcher finish exactly once. There is no loop or implicit retry. The
runtime owns an 8,192-byte response array inside its caller-owned opaque
object, but exposes exactly the route ceiling to the callback: 2,048 bytes for
SOS and 8,192 bytes for location. Status must be 100..599 for an HTTP outcome;
body length, outcome/error combinations and completion time are checked before
the result reaches the dispatcher. Default maximum reported POST duration is
30 seconds and the configurable hard ceiling is 120 seconds. Invalid,
oversize or over-duration callback results are cleared and converted to a
fixed local transport failure before the one finish call. A wrong 2xx body is
still only transport acceptance and goes to the existing strict route ACK
parser; it is never promoted to delivery.

The callback contract is a trust boundary. It must not retain borrowed
request/body/response pointers, must never write past `response_capacity`, and
must truthfully supply completion time. This component can reject a reported
oversize or invalid time only after a synchronous callback returns; it cannot
preempt a blocked callback, stop an out-of-contract memory write, or compare
against an independent clock. A future real transport adapter therefore owns
bounded I/O timeout/cancellation and clock sourcing.

If dispatcher finish cannot durably commit transport or ACK state, the runtime
keeps the bounded response/outcome plus exact completion-only attempt view and
requires an explicit `retry_finish`. That method calls finish once without a
new selector or POST. A separate adversarial begin-recovery path covers a
failure while the dispatcher is durably classifying an invalid head: an
invalid SOS completion view is replayed through finish, while an invalid-route
head is settled by one explicit cancel retry. Neither path can advance to a
new head until the selected attempt reaches a known terminal retained/delete
state. `cancel` and `close` cannot interrupt an on-stack callback and do not
discard a recovery settlement. Disabled close clears all borrowed callback,
context and dispatcher references.

Focused validation for this slice:

```powershell
python -m unittest quality_tests.test_p0_delivery_runtime -v
python -m unittest quality_tests.test_p0_outbox_dispatcher quality_tests.test_sos_outbox_adapter quality_tests.test_location_outbox_adapter -v
python -m unittest discover -s quality_tests -p "test_*outbox*.py" -v
python scripts/context_lint.py
git diff --check
```

### OUTBOX-010F Evidence - 2026-09-02

- Actual ESP32-S3 C source and its adversarial C harness compile and link with
  `-std=c11 -Wall -Wextra -Werror -Wconversion -Wformat=2 -Wshadow
  -Wsign-conversion`; the harness covers no-due, both routes, exact capacity,
  transport failure, wrong 2xx, oversize response, duration violation,
  callback re-entry, finish recovery, begin recovery, cancel and close. The
  Xtensa harness is not executed. The available Espressif clang contains no
  native x86 target, so the separately guarded native executable run is an
  expected environment skip rather than target-runtime evidence.
- Xtensa sizes are: opaque runtime 12,288 bytes, implementation 9,648 bytes,
  bounded response array 8,192 bytes, POST request 28 bytes, POST result 24
  bytes, runtime result 124 bytes and snapshot 120 bytes. The largest
  compiler-reported local frame is 144 bytes (`drive_once`). These numbers do
  not include dispatcher/outbox/adapters, nested parser/crypto stack, heap or a
  future HTTP implementation.
- Focused runtime suite: `9 PASS`, one expected native-x86-backend skip. The
  dispatcher/SOS/location adapter combination passed `37/37`; the complete
  `test_*outbox*.py` regression passed `76/76`. `git diff --check` passed with
  line-ending warnings only in unrelated concurrent files.
- A clean ESP-IDF 5.4.2 `esp32s3` build in
  `tmp/outbox010f_clean_20260902/` compiled this warnings-as-errors component
  and linked the full application. The binary is 896,240 bytes (`0xdacf0`) in
  the 1 MiB app partition, with 152,336 bytes free. The missing
  `ESP_ROM_ELF_DIR` emitted the repository's known non-fatal gdbinit warning;
  unrelated `app_main.c` unused-symbol warnings remained outside this target.
- `python scripts/context_lint.py` was blocked only by two concurrently
  declared CALL paths not yet present:
  `pc_simulator/ego_call_pc_endpoint_composition.py`,
  `quality_tests/test_ego_call_pc_endpoint_composition.py`. Root must rerun
  after that owner lands. Full `scripts/verify.ps1` remains a root merged run.
- No real HTTP request, network, SIM, USB, VPS, storage callback, partition
  access, flash, reboot, device task or hardware operation ran. The component
  supplies orchestration only and carries no credential.
- This is server durable-ingest ACK orchestration, not Guardian display,
  Guardian/human acknowledgement, Call success, exactly-once delivery,
  or product durability. It is not P0-SOS or P0-LOC evidence. Real transport wiring,
  authenticated credentials, task ownership, independent timeout/cancel,
  target execution/fault injection, OUTBOX-010D wear-suitable persistence and
  end-to-end offline/power-cycle testing remain open.

## OUTBOX-010G - Fail-closed SIM7670 P0 Delivery Adapter

This additive slice owns only:

- `docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md`
- `firmware/mqtt_heartbeat/components/sim7670_gnss/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/sim7670_gnss/include/sim7670_gnss.h`
- `firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_gnss.c`
- `firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_http_exact_parser.c`
- `firmware/mqtt_heartbeat/components/sim7670_gnss/sim7670_http_exact_parser.h`
- `firmware/mqtt_heartbeat/components/sim7670_p0_delivery_adapter/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/sim7670_p0_delivery_adapter/Kconfig.projbuild`
- `firmware/mqtt_heartbeat/components/sim7670_p0_delivery_adapter/include/sim7670_p0_delivery_adapter.h`
- `firmware/mqtt_heartbeat/components/sim7670_p0_delivery_adapter/sim7670_p0_delivery_adapter.c`
- `quality_tests/test_sim7670_p0_delivery_adapter.py`

The adapter is default-off and not instantiated by `app_main`. Enabled init
accepts only an explicitly injected lowercase DNS hostname, its exact matching
host-only `https://` origin and a bounded non-placeholder bearer token. It
admits only the dispatcher constants for manual SOS and location state. The
synchronous callback passes the original payload pointer and exact byte length
once to its driver and accepts success only when the driver proves that exact
length was written and returns a complete, declared-length-matched HTTP body.
The runtime's borrowed cancellation probe, context and transfer generation are
forwarded unchanged so a future bounded AT implementation can poll only at
reviewed cooperative safe points; this slice does not claim forced preemption.
All entry/error/disabled paths clear the full bounded caller response first.
It has no retry, task, NVS, credential provider or `app_main` wiring.

The real SIM7670 exact API is intentionally narrower than a transport
implementation in this slice. It clears the caller-owned response, validates
the HTTPS DNS authority, one of the same two fixed paths, bearer, byte ranges
and finite timeouts, then unconditionally returns
`TLS_PROFILE_UNVERIFIED`. OPS-004 has not supplied reviewed modem CA trust,
exact hostname/SNI and trustworthy-clock verification. The failure occurs
before UART initialization, AT commands, bearer construction or payload I/O.
No caller boolean or injected callback can promote this real path. The
separately default-disabled `TEST_DRIVER` option exists only for the offline C
harness; it is not an operator or production profile. The pure C
`HTTPACTION`/`HTTPREAD` parser remains compiled and tested for strict POST
method, status, declared length, complete body and no silent truncation, but is
not evidence that a secure modem transaction exists.

The exact response ceiling is 8,192 caller-owned bytes, aligned with the
existing location delivery runtime ceiling; no 8 KiB response is allocated on
this adapter's stack. Current server serializers are tested both for accepted
and duplicate responses. Representative pretty JSON bodies are 858/859 bytes
for location and 509/510 bytes for SOS; their compact forms are 716/717 and
438/439 bytes. Legal maximum identity fixtures, including a 256-character
four-byte UTF-8 location observation ID, are 2,200/2,201 bytes for location and
682/683 bytes for SOS. These values fit 8,192 without truncation. They are
host fixture evidence, not modem `HTTPREAD` evidence.

The default I/O phase budget is 25 seconds: eight 1-second command phases,
3 seconds data, 10 seconds action and 4 seconds read. It is separate from the
30-second callback hard bound, leaving a five-second scheduling/accounting
margin. Init requires the phase sum to be strictly less than the callback
bound, which cannot exceed 120 seconds. Final composition must additionally
set the delivery runtime `max_post_duration_ms` greater than or equal to the
adapter callback bound. The component cannot verify that cross-object setting
by itself.

The adapter is synchronous and lock-free. A future runtime owner must hold one
external single owner across the entire multi-command modem HTTP transaction;
the legacy SIM7670 mutex protects individual AT commands only and is not a
transaction lock. No real UART, SIM, modem, network, VPS, storage, flash or
hardware action is authorized by this slice.

Focused validation:

```powershell
python -m py_compile quality_tests/test_sim7670_p0_delivery_adapter.py
python -m unittest quality_tests.test_sim7670_p0_delivery_adapter -v
python -m unittest quality_tests.test_p0_delivery_runtime quality_tests.test_p0_outbox_dispatcher quality_tests.test_sos_outbox_adapter quality_tests.test_location_outbox_adapter -v
python -m unittest discover -s quality_tests -p "test_*outbox*.py" -v
python scripts/context_lint.py
git diff --check
```

### OUTBOX-010G Evidence - 2026-09-03

- `python -m py_compile quality_tests/test_sim7670_p0_delivery_adapter.py`:
  PASS.
- `python -m unittest quality_tests.test_sim7670_p0_delivery_adapter -v`:
  10 run, 8 PASS and 2 guarded SKIP because no native x86 C compiler backend
  is available. The ESP32-S3 GCC strict harness compilation/link test PASSes;
  that cross-build does not execute either C harness.
- The focused P0 delivery/dispatcher/SOS/location adapter regression ran 47
  tests: 46 PASS and one existing guarded native-C SKIP. The broader
  `test_*outbox*.py` discovery ran 76/76 PASS.
- `python scripts/context_lint.py` and the scoped final `git diff --check`
  both PASSed.
- A final-source clean ESP-IDF 5.4.2 `esp32s3` build PASSed at
  `tmp/outbox010g_final_clean_20260903`: both strict-warning G components
  compiled and linked. `egolink_mqtt_heartbeat.bin` is 896,240 bytes
  (`0xdacf0`), leaving 152,336 bytes (`0x25310`, 15%) in the 1 MiB app
  partition. The existing unrelated `app_main.c` unused-symbol warnings and
  non-fatal missing `ESP_ROM_ELF_DIR` gdbinit warning remain outside G.
- Final object evidence: adapter opaque context is 1,024 bytes and its actual
  internal structure is 864 bytes; it allocates no heap and no 8 KiB response
  array. The largest G adapter frame is 128 bytes, exact API frame 64 bytes and
  parser frame 48 bytes; the conservative deepest current fail-closed call
  chain is about 240 bytes beyond caller/ABI/RTOS costs. Adapter, parser and
  exact-boundary text symbols total 2,923, 1,738 and 281 bytes respectively.
  Target free-heap and task-stack watermarks remain unmeasured.
- The ESP-IDF build compiles and links the default-dormant adapter/parser/API;
  it does not execute them and is not TLS, UART, payload-write, response-read,
  SIM registration, network, VPS or hardware evidence.
- Remaining blockers are OPS-004 secure modem TLS configuration and actual
  CA/hostname/SNI/clock proof, a composed single modem owner, runtime wiring,
  target heap/stack watermark measurement, real bounded UART transaction code,
  authenticated network testing and an operator-authorized exact-board run.

#### OUTBOX-010G Host-validation audit amendment - 2026-09-03

- The adapter no longer maintains a second hostname grammar. Its host-only
  origin and `expected_tls_host` now pass the parser-owned shared
  `sim7670_http_exact_https_origin_matches_dns_host` validator before any
  configuration is admitted. Exact lowercase origin/host equality and the
  adapter's narrower copy capacities remain enforced.
- The shared grammar bounds the whole DNS name and every label (maximum 63
  bytes), rejects empty/leading-hyphen/trailing-hyphen labels, requires at
  least one lowercase ASCII letter, and therefore rejects dotted IPv4
  literals such as `127.0.0.1`. Bracketed or colon-containing IPv6 literals,
  userinfo, ports, paths, queries and fragments remain rejected. A 63-byte
  label is accepted while a 64-byte label is rejected by both parser URL and
  adapter-init paths.
- The amended focused suite collects 11 tests: 9 PASS and two guarded native
  execution SKIPs because the installed Espressif clang has no x86 backend.
  The parser harness plus both default-production and TEST_DRIVER adapter
  builds strictly compile and link for ESP32-S3, including the
  IPv4/63-byte/64-byte cases. They are not executed target evidence and no
  DNS lookup, TLS, UART, SIM, modem, network or hardware operation ran.

## OUTBOX-010H - Split-phase Delivery Runtime And Durable-SOS Preemption

This additive slice extends the existing default-disabled delivery runtime; it
does not create another dispatcher, selector, task or transport component. Its
owned implementation paths are:

- `firmware/mqtt_heartbeat/components/p0_delivery_runtime/CMakeLists.txt`
- `firmware/mqtt_heartbeat/components/p0_delivery_runtime/include/p0_delivery_runtime.h`
- `firmware/mqtt_heartbeat/components/p0_delivery_runtime/p0_delivery_runtime.c`
- `firmware/mqtt_heartbeat/components/p0_outbox_dispatcher/include/p0_outbox_dispatcher.h`
  (ownership clarification only; no dispatcher ABI or implementation change)
- `quality_tests/test_p0_delivery_runtime_split_phase.py`

The legacy synchronous `drive_once` contract remains available. Product
composition can instead use three additive calls:

1. `prepare` runs under the external shared-outbox owner and performs at most
   one dispatcher begin. The dispatcher's existing private `canonical_item`
   is already an immutable copy of the exact persisted payload, so the runtime
   retains only its borrowed view and does not make another 4,096-byte copy.
2. `execute_prepared` runs after releasing that owner. It calls only the
   injected bounded POST callback and stores its bounded result; it never calls
   dispatcher, outbox, adapter or storage APIs.
3. `settle_prepared` reacquires the owner and performs exactly one dispatcher
   finish. Storage-uncertain finish remains in the existing explicit recovery
   phase and `retry_finish` never reselects or re-POSTs.

Only `signal_durable_sos` may race with `execute_prepared`. The SOS owner may
invoke it only after the `manual_sos` record is durably available. An
always-lock-free 32-bit atomic word combines a bounded generation with the
active-transfer state, preventing a stale cancel probe or compare/exchange
from acting on a later attempt. The signal never carries payload or identity,
never targets `manual_sos`, and does not enter the runtime's ordinary owner or
busy path.

The race has an explicit bounded winner. If the transport publishes
`RESULT_READY` first, its real HTTP/failure result remains authoritative and a
later SOS signal is reported too late. If the durable-SOS signal changes the
same-generation active Location state first, a cooperative callback can exit
at its next reviewed safe point. If it had already been entered, remote
acceptance remains conservatively unknown and any later callback result is
not promoted to ACK. Settlement uses dispatcher `finish` with status zero and
`P0_DELIVERY_CANCELLED`, retaining Location for retry. It deliberately does
not call dispatcher `cancel`, whose contract is limited to a known-unsent
`SEND_READY` attempt. A subsequent prepare uses the existing due/priority
selector, allowing a due CRITICAL SOS to precede NORMAL Location traffic.

This is cooperative cancellation only. A callback that ignores the probe or
blocks inside an indivisible modem AT operation continues until its own
bounded timeout; neither the atomic signal nor this runtime hard-aborts it.
The split boundary keeps the shared outbox/dispatcher owner available for SOS
journaling, local feedback, urgent Location and an enqueue-only Ego Call
request, but it does not prove that those actions can preempt a separately
shared modem. That requires a composed modem transaction arbiter and reviewed
safe cancellation points.

Focused validation:

```powershell
python -m unittest quality_tests.test_p0_delivery_runtime_split_phase -v
python -m unittest quality_tests.test_p0_delivery_runtime quality_tests.test_p0_outbox_dispatcher -v
python -m unittest quality_tests.test_sim7670_p0_delivery_adapter quality_tests.test_p0_delivery_runtime quality_tests.test_p0_delivery_runtime_split_phase quality_tests.test_sos_delivery_composition quality_tests.test_sos_delivery_composition_split_phase -v
python -m unittest discover -s quality_tests -p "test_*outbox*.py" -v
python scripts/context_lint.py
git diff --check
```

### OUTBOX-010H Evidence - 2026-09-03

- H focused validation passes `5/5`. Its offline actual-C harness compiles and
  links the real runtime with a deterministic dispatcher double under the
  ESP32-S3 warnings-as-errors set. The harness specifies default-off behavior,
  prepare-without-POST/finish, pre-callback cancel, callback-observed cancel,
  non-cooperative late-result suppression, result-wins, non-cancellable SOS,
  stale generation probes, result-ready cancel/close guards and finish
  recovery without re-POST. The Xtensa harness was not executed: no native
  host C backend is installed, so these race paths remain `NOT_RUN` as runtime
  execution evidence rather than being inferred from cross-compilation.
- The existing runtime/dispatcher focused regression passes `21` tests with
  one environment-guarded native execution skip (`22` collected). The merged
  G/H/I/J composition regression passes `38` with four native-host execution
  guards skipped (`42` collected). The complete `test_*outbox*.py` regression
  passes `76/76`.
- ESP32-S3 compile/size evidence verifies `ATOMIC_INT_LOCK_FREE == 2` for the
  32-bit transfer-control word. The public runtime remains 12,288 bytes; the
  actual internal object is 9,736 bytes, including its single existing 8,192
  byte response array. The POST request is 40 bytes, result 132 bytes and
  snapshot 168 bytes. No dynamic allocation or payload-sized stack copy was
  added. The largest H local frame is 192 bytes in `execute_prepared`; target
  task-stack watermark and nested modem/parser/crypto depth remain unmeasured.
- SOS-010J separately strict-cross-compiles and relocatable-links the actual
  composition with this runtime and resolves all split/preemption symbols.
  This is link evidence, not concurrent execution, latency, network or device
  evidence.
- Root later supplied the installed ESP-IDF v5.4.2 tool paths explicitly and
  completed a fresh final-source ESP32-S3 build in
  `tmp/p0_mainline_final_clean_20260903/`. The build compiled and linked G/H,
  the SOS I/J composition and LOC-021L, producing an application image of
  `0xDACF0` bytes in the `0x100000` factory partition with `0x25310` bytes
  (15%) free; the bootloader is `0x51C0` bytes with `0x2E40` bytes (36%) free.
  This supersedes the earlier environment failure only as compile/link
  evidence; nothing was flashed or executed on target.
- No task, mutex, GPIO, application binding, network, credential, UART, SIM,
  VPS, storage callback, flash, reboot or hardware action was added or run.
  H does not establish secure TLS, remote acceptance certainty after a
  cancelled in-flight POST, Guardian/human delivery, Ego Call success,
  `P0-SOS` or `P0-LOC`.
- Remaining product work is OPS-004 verified TLS/hostname/SNI/clock handling,
  a real bounded and cooperatively cancellable modem transaction owner,
  application/task wiring, target race/fault execution, stack/heap watermarks,
  OUTBOX-010D wear-suitable persistence and operator-approved outage/reboot/
  latency drills.

# Builder Prompt

```text
Read docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md in
D:\pywork\egolink. Load only AGENTS.md, docs/CONTEXT_INDEX.md, and this packet's
context. Freeze exact per-file ownership against LOC-021/OPS-004 and add focused
test/build commands before changing execution_state to in_progress. Implement
the smallest contract-first priority outbox: durable write before send, stable
identity/time across retry and reboot, idempotent positive ACK, ACK-scoped
deletion, bounded capacity and explicit corruption/overflow. Do not buffer RTC
media, invent a broker, reuse another task ID, or label queued/sent data
delivered.
Static fixtures may proceed after dispatch; flash, power-cycle, disconnection
and device/network commands require explicit operator intent. Run every
validation command and return changed files, exact output, storage/config
identity, hardware/evidence paths and remaining risks. Do not claim SOS closure
or P0-SOS PASS.
```

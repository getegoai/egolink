---
id: P0-CONVERGENCE-20260905
title: Single-board Location and Camera field closure
status: active
priority: critical
execution_state: legacy_cleanup_verified_camera_integration_pending
owner: codex_integrator
created: 2026-09-05
last_updated: 2026-09-09
serves_gate: P0-LOC
serves_milestone: single_4g_board_camera_field
requires_hardware: true
runtime_authorization: not_granted_scope_decision_only
runtime_authorization_note: flashing_sim_traffic_deployment_and_real_scene_capture_require_a_named_bounded_operator_session
data_cleanup_authorization: founder_legacy_wifi_backup_and_clear_20260909
context:
  - AGENTS.md
  - docs/AGENTS.md
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/product/P0_SCOPE.md
  - docs/current/FIRST_LAUNCH_EXECUTION.md
  - docs/current/ACTIVE_BUILD.md
  - docs/hardware/BOARD_MATRIX.md
  - docs/architecture/SYSTEM_OVERVIEW.md
  - docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/architecture/adr/ADR-0014-runtime-convergence.md
  - docs/architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md
  - docs/product/PRODUCT_DEMO_PRIVACY_BOUNDARY.md
  - docs/hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md
  - docs/hardware/PRIVACY_WIFI_SPOOL_PURGE_20260909.md
  - docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md
  - docs/tasks/active/FIELD-020_L1_FIELD_DATASET.md
  - docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md
  - docs/tasks/active/OPS-004_DEVICE_HTTPS_INGRESS.md
  - firmware/AGENTS.md
  - pc_simulator/AGENTS.md
  - quality_tests/AGENTS.md
  - shared/contracts/
  - docs/egolink_review_20260905/migration_manifest.json
allowed_paths:
  - .gitattributes # exact archived source snapshots remain byte-preserved
  - .gitignore # founder-authorized private project backup remains untracked
  - firmware/mqtt_heartbeat/main/
  - firmware/mqtt_heartbeat/components/
  - firmware/mqtt_heartbeat/CMakeLists.txt
  - firmware/mqtt_heartbeat/dependencies.lock
  - firmware/mqtt_heartbeat/sdkconfig* # existing profile/config files
  - firmware/mqtt_heartbeat/partitions_camera_collection_16mb.csv
  - firmware/mqtt_heartbeat/partitions_loc021_live.csv # preserve occupied RUN001 outbox range
  - firmware/mqtt_heartbeat/partitions_collection.csv # preserve NVS and both historical outbox ranges
  - firmware/camera_smoke/ # historical driver reference and focused compatibility fixes only
  - pc_simulator/ # existing collection/export tooling only; no field runtime dependency
  - server/ # minimum authenticated ingest, ACK and bound Guardian projection only
  - shared/contracts/ # additive changes plus the named 2026-09-08 privacy-breaking Wi-Fi restriction
  - quality_tests/
  - scripts/ # native validation, existing build and bounded experiment tooling only
  - docs/ # named runtime-convergence authority, packet, evidence and experiment updates
out_of_scope:
  - root AGENTS replacement or overwriting parallel work
  - firmware outside the existing Location, collection, Camera, modem, transport and outbox seams
  - unsolicited pin, hardware or production BOM changes
  - shared protocol or state-machine changes without integrator review
  - model behavior, new sensors, camera AI/video, general event sourcing or full app work
  - HTTP downgrade, disabled certificate or hostname validation, committed secrets
  - automatic flashing, SIM traffic, recording, external notifications or deployment
  - claiming a P0 Gate PASS from source, native, build or isolated bench evidence
---

# P0-CONVERGENCE-20260905 — Single-board Location and Camera field closure

## Current execution adjustment — founder instruction 2026-09-09

[ADR-0015](../../architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md)
replaces the current scheduling portion of the older convergence plan. This
packet now owns one A-line result on `connectivity-node-001`: Location and
asynchronous GNSS/Cell/external-IMU/available-power collection continue while
the historically observed Camera is integrated into the same candidate,
captured JPEGs are reliably saved, uploaded over real LTE, persisted by the
VPS and viewed through the existing Web device surface. A bounded timed mode,
offline/restart recovery and an independently powered short carry run precede
FIELD-020.

AMOLED, board-to-board UART/Wi-Fi forwarding and PC runtime forwarding are not
part of this task's operation or acceptance. CALL-020, CALL-021 and full
physical SOS are paused; their code and final product Gates remain. Camera is
a milestone delivery, not a fourth Gate or a Location/SOS decision source.

### Ordered implementation slices

1. Reidentify the exact board/revision, Camera, external IMU, power, antennas,
   active and recovery images, LTE interface and actually persistent storage.
   Reconcile Camera SCCB, IMU/battery I2C, USB/modem, partition and memory/task
   ownership; an isolated camera-smoke flash is not completion.
2. Reuse the proven JPEG driver/settings in the collector. Capture and upload
   are bounded and release their software resources after success or failure;
   GNSS/network/sensor progress and resource watermarks remain observable.
3. Prove ordinary-observation delivery from this candidate over actual Wi-Fi
   and actual LTE, then perform one controlled route transition. Preserve the
   original record identity/event time, retain pending bytes until exact durable
   ACK and expose unavailable-route, retry, duplicate and loss accounting.
4. Reuse the authenticated command/ACK path for one expiring Web request. Bind
   command ID and observation/photo ID while distinguishing accepted,
   received, capture attempted, saved, pending upload, VPS verified/persisted
   and Web-visible states. Retry cannot cause unbounded recapture.
5. Add a default-off local timed configuration with explicit interval and
   session end. Browser disconnect does not cancel a delivered configuration;
   undelivered stop remains pending. Restart semantics are explicit and missed
   intervals are not recaptured later.
6. Store JPEG bytes separately from lightweight metadata and ordinary
   telemetry. Require a complete persistent file plus integrity value before
   local success and complete VPS durability before upload ACK. Set explicit
   photo byte/count quota, ordinary-observation reserve, corruption/full/loss
   accounting and same-ID restart recovery.
7. Run the authorized one-shot LTE closure, offline/restart timed recovery and
   independently powered joint short test including the reviewed Wi-Fi/LTE
   transition, then dispatch FIELD-020.

Every photo retains device/session/photo identity, source capture time and
quality, server receive time, trigger source, command/config version, outcome,
format/geometry/byte count, integrity value and storage reference. A linked
last-trusted location retains its own time/source/age/quality and is never
presented as a fresh position.

Timed collection is disabled by default. Live images require a named permitted
environment, participant consent, authorized viewers, retention limit and
deletion path. Images are excluded from public paths, ordinary Git commits and
unrelated logs; `training_allowed=false`. Video, continuous recording, audio
capture and visual inference are excluded.

The founder separately authorized backup and clearing of the legacy Wi-Fi data
and device spool. That bounded operation has completed for the identified
device partition, named local private report files, matching VPS rows and the
three affected remote daily archives. Exact bytes were hash-verified into an
ignored private project backup before removal. The selected device partition
received a complete empty readback while the application, NVS and `ego_outbox`
were not targeted. The live VPS database passed integrity checks and returned
healthy after atomic replacement; a clean remote recovery point remains. See
[the bounded purge evidence](../../hardware/PRIVACY_WIFI_SPOOL_PURGE_20260909.md)
for exact scope, hashes, recovery location and resulting bootloader state.

### Offline source/build checkpoint — 2026-09-09

The Camera/VPS/Web implementation slice is now source-complete for review and
has zero remaining merge blockers in independent backend and firmware audits.
The selected source contains one-shot and durable timer control, capture
journaling, a fixed-slot persistent JPEG store, metadata-before-media upload,
strict command/content ACK identity, retention deletion, reboot settlement and
ordinary/photo upload fairness. The server contains Guardian-bound control,
private persistence, integrity checking, status-separated preview/export and
failed-purge tombstones. This is not deployment or hardware evidence.

Focused Camera/media/control/delivery/HTTPS execution passes `26/26` and the
full repository suite passes `1,776` tests with `13` environment-guarded skips.
ESP-IDF 5.4.2 no-flash builds pass for default (`896,240 B`), legacy collector
(`991,504 B`) and Camera collector (`1,029,616 B`); exact hashes and partition
headroom are recorded in `docs/current/ACTIVE_BUILD.md`.

The produced Camera profile intentionally remains `NO_SIM=y`, LTE PPP off and
shared-I2C verification off. It therefore cannot produce the required real LTE
JPEG. Before any candidate flash, privately back up and confirm
`0x600000..0xF00000` as the dedicated media range; then prove OV5640/QMI8658A/
MAX17048 coexistence, generate a named ignored live config, deploy/flash under
one bounded authorization and run the live sequence in the Acceptance table.
The board remains in ROM bootloader and every product Gate remains `NOT_RUN`.

## Prior execution adjustment — founder instruction 2026-09-06

The then-current deliverable was the assembled portable asynchronous collection unit:
independent GNSS raw observations (including no-fix), Cell, continuous real
20 Hz IMU, available power readings, then Wi-Fi observations and bidirectional
Wi-Fi/LTE plus reboot-safe backlog upload to the existing Message Hub collection
view and complete authenticated export. CALL, product SOS, fusion accuracy and
uninstalled media do not block this engineering configuration. Product Gates
remain NOT_RUN. The prior bounded Location evidence below remains historical.

That explicit instruction superseded conflicting scope/principle clauses for
that collector only: GNSS stays powered during a collection session; IMU has
independent sampling, chunking and upload cadence. Extend existing raw frames,
time-lineage names, strict ACK, concrete TLS connector and exclusive modem
backend. Add append storage in checked free space; preserve NVS credentials,
pending data, old outbox and verified fallback. No whole-repository doc migration.
Firmware, raw contracts, existing server/UI and native behavior tests are allowed.
Two nonoverlapping executors handle spool and server; the integrator owns wire,
modem and main integration. Camera/audio remain disabled until actual assembly
and capture scope are confirmed. SIM removal is the last known physical state.

Acceptance: actual per-source ingest/export, then indoor -> LTE away from Wi-Fi
-> both offline -> controlled reboot -> automatic backlog recovery; real small
capacity eviction/loss accounting; portable power, mounting and local stop.
Normal no-fix/offline/declared eviction are handled states. Stop on hardware
fault, reboot loop, failed stop or data/credential/media/fee scope risk. Retain a
new compatible controllable image once proven; old FW-007 is rollback, not an
automatic end-of-batch downgrade. Run focused native concurrency/storage/wire
tests, legacy/live/collector builds, context_lint and scripts/verify.ps1.
Changes of experimental scope, if needed, are consolidated after implementation
and preflight; no per-command approval loop. No new hardware evidence is claimed
by this adjustment or by an unrun image.

Actual 2026-09-06 delivery: the existing target now independently captures
raw GNSS/Cell, continuous QMI8658 six-axis blocks, MAX17048 readings, Wi-Fi and
health into the 860,160-byte append spool and the authenticated Message Hub.
The run 002-006 evidence index is `reports/board_validation/COLLECTION-20260906-006/README.md`;
the final audit links earlier runs, exact images, full exports and all failures.
Run 002 exposed invalid bounded-request arguments and duplicate I2C driver
installation; both were corrected on hardware. Runs 004-005 demonstrated secure
connection reuse, reboot backlog delivery and the queue returning to zero while
sampling continued. Real full-capacity eviction discarded 41 ordinary records
with 20 persisted source/range summaries; read errors and sample gaps remain data.
The collection view is now `/`, with `/engineering` and Guardian preserved.

This is not a field handoff: USB PPP has native and enabled-component build
evidence, but no collector-main network policy or actual PPP/TLS path yet. The
actual USB route/interface, SIM/data scope, independent power, mounting and
physical BOOT hold need operator work; full two-network outage/restart/recovery
and configurable small-capacity acceptance remain unrun. No media was captured.
The present firmware retains its finite 300-second bench configuration and
preserves queued data on stop. Product Gates and concurrent SOS/CALL promises
are unchanged; the known FW-007 image remains a fallback, not the active image.

## Product outcome

Completion means that, on one identified connectivity node, genuine GNSS/Cell/
IMU/power observations change device-owned state and reach the authorized
server surface over actual Wi-Fi and LTE, including a controlled transition,
while the same candidate captures, persistently stores and uploads authorized
JPEG stills over verified LTE. Web users see source/capture time, separate
command/capture/save/upload truth and never receive a fabricated current
position or photo. This paragraph is a target, not current evidence.

This is the first runtime-convergence task. It does not claim P0-LOC, implement
all concurrent product ingress, or re-create the entire architecture.
CALL and full SOS are retained follow-ups and are paused for this milestone.

## Step 0 — reconcile the real workspace, then implement

Read root/module AGENTS, `docs/CONTEXT_INDEX.md`, product charter, NORTH_STAR,
FIRST_LAUNCH_EXECUTION, ADR-0011/0012/0014/0015, BOARD_MATRIX, current active packets
and source owners. Check branch/HEAD/worktree before any edit; do not overwrite
uncommitted work. Compare uploaded-source hashes to actual files.

Merge the revision candidates with newer facts and allocate the ADR number.
Update absent-from-this-package authorities only after reading their full text.
The docs/AGENTS candidate must never overwrite root AGENTS.
The short routing/document update is the start of this packet, not completion.

## Step 1 — trace one executable path

Inspect actual entry/config selection → Camera/IMU/I2C and storage ownership →
UART/modem owner → observation mapper → Location reducer/policy → ordinary
spool plus bounded photo storage → secure connector → server ingest/persistence
→ authorized Web projection. Produce a short seam checklist in the task result.
Choose the fewest unconnected seams. Reuse Q/R and the proven adapters where
appropriate; do not add a new generic owner, factory or adapter framework.

Specific decisions to resolve in code review:
- Current-boot single-source input avoids a general cross-source WAL dependency.
- Confirm whether zero/missing HDOP is being confused with receiver no-fix.
- Separate local state progress from failed outbound persistence.
- The actual transport must preserve exact complete response bytes and verified
  TLS peer identity, or remain unavailable; do not silently fall back to HTTP.
- Keep the existing field-test storage bounded and labelled; no endurance claim.

## Step 2 — implement one named engineering profile

Add/select a narrow live profile using existing build tooling. Keep the normal
legacy image unchanged. The profile must have a real application entry, one
modem owner, one state loop and one delivery owner; a fake TRANSPORT_FAILED
callback is not an implementation of live delivery.

Configuration declares exact board/pins/transport, run limits, GNSS/Camera work
budgets, ordinary/photo upload cadence, timed-session end and storage quotas.
Candidate secrets live only in the
existing ignored credential mechanism. No unrequested dependency/toolchain bump.

The profile emits/records boot identity, source event time, seq, source state,
last trusted reference, age/quality/uncertainty, current persistence status,
last attempted delivery and matched server acknowledgement. Aggregate counters
are enough; avoid sensitive raw-data logging by default.

A failed GNSS attempt returns promptly with no-fix/error provenance and aged
prior evidence. A stale point never becomes a fresh fix. A full queue reports
its policy and counters. A new claim of cross-boot recovery requires its own
persisted identity/checkpoint tests. T0/T1 do not globally block the isolated S
smoke or this bounded current-boot/single-source live profile; their original
concurrent SOS/IMU ordering, checkpoint, tombstone and no-output replay
commitments remain mandatory until a reviewed equivalent proves them.

## Step 3 — executable local regression and actual builds

Before hardware, run the C/host behavioral tests that really execute this path,
not only file-text assertions. Include finite event time, valid/no-fix/error,
missing quality, stale input, queue-full/storage-error, wrong/malformed ACK,
response truncation, cancellation, owner exclusivity, Camera busy/failure,
partial files, photo quota/full behavior, duplicate/expired commands, restart
recovery and graceful shutdown.
Inspect every skip touching the new path; run in an appropriate local native
runner or keep the affected capability unverified. Keep unaffected legacy tests.

Build both legacy default and the selected live profile with the pinned IDF.
Record source/config/image identity and show only the intended entry is linked.
Run repository context lint and diff check; full regression at the integrated
candidate boundary. Do not claim a test executed when only its source matched.

## Step 4 — bounded experiment scope

Use an existing unexpired authorization only if it covers this exact operation.
Otherwise return one combined scope for the operator, rather than repeated
per-command approval requests. No live I/O is authorized by this task text.

The scope must contain: exact node identity, image and recovery hashes, ports
reidentified at run time, endpoint and identity-verification rules, network/SIM
route, data/capture policy, duration/attempt/write/traffic limits, participants,
stop conditions and physical placement. Never test as someone's safety lifeline.

Suggested first run design, to approve and parameterize from source limits:
a short owner smoke, then a bounded live Location session with several cached
state queries, one normal source update and no-fix/error observation if the
environment produces it. Do not force a GNSS-success claim indoors.
Server/Web must bind the same device/run/image/observation/photo identity. The
scope must explicitly permit the Camera scene, viewers, retention/deletion and
training-disabled state. No microphone, audio or non-test Guardian notification
belongs to this run.

Stop on wrong device/image, unexpected reset/brownout/thermal issue, possible
concurrent modem owner, runaway writes/traffic, bad auth/TLS or privacy-policy
violation. Preserve evidence; restore the exact known image only within scope.

## Acceptance

| Layer | Required output |
|---|---|
| Code delivery | Concrete selected runtime, real transport implementation, executable tests, builds and migration |
| First live proof | Real device state reaches authorized Guardian on the verified route; age/source/failure correctly shown |
| Network paths | Same-candidate ordinary observations traverse actual Wi-Fi and actual LTE; a controlled transition preserves IDs/event time and reports pending, ACK, retry, duplicate and loss truth |
| Camera manual closure | One current authorized JPEG follows the existing command path over real LTE, is integrity-verified and durably saved before Web preview |
| Timed persistence | Delivered default-off configuration, offline quota, restart recovery of the same photo IDs/files, corruption/full truth and no catch-up recapture |
| Coexistence | Location, GNSS/Cell/IMU/power and network continue during bounded Camera capture/upload without unbounded resource or storage growth |
| Failure truth | No fake fix/ACK; incomplete responses retained for retry; cancellation bounded; local state degradation visible |
| Recovery | Candidate reset/retry scope accurately stated; unsupported power-loss/replay remains unclaimed |
| Handoff | One concise result naming user-visible change, source/config/image, measured evidence, remaining blocker and next action |

A successful build can complete the code-delivery portion, but not the live
portion. Mark `runtime_waiting_authorization` where appropriate. Do not mark the
entire packet or product gate PASS while the only evidence is offline.

## Paused CALL/SOS boundary

CALL-020, CALL-021 and full physical SOS are not writers in this packet. Keep
their existing source and evidence intact; do not run media, add a board bridge
or make A-line power/storage depend on AMOLED. They resume under their own
reviewed research and experiment scopes after an explicit scheduling decision.

## After the live slice

After manual and timed Camera closure, run the single-board independent-power
joint short test and FIELD-020. Feed measured Camera pin, power, image-size,
latency, memory and storage facts into HW-021. CALL/SOS and full release
convergence remain later work.

## Do not expand this task into

Universal sensor event sourcing, a new training platform, Camera AI/awareness,
video, production BOM freeze, full repository rewrite, arbitrary API churn, a
new Dashboard or control bus, or purchasing a new chip to avoid diagnosis. The
minimum existing-device Camera control/preview is expressly in scope.

## 2026-09-05 code delivery / runtime handoff

The integrator delivered the selected real Q/driver → local state → bounded,
verified HTTPS → existing ingest/ACK/Guardian path, concrete CALL mTLS entries,
and independent SOS recognition/storage/recovery behavior. Final source hashes,
builds, behavior coverage, every skip, limitations and the single combined
experiment request are in [the delivery report](../../development/RUNTIME_CONVERGENCE_20260905.md).
This completes the current code-delivery slice, not hardware or product acceptance.
Physical SOS/concurrent recovery and CALL RESULT remain explicit follow-ups.
The operator subsequently approved the combined scope. The real service and
Guardian binding are now deployed and externally checked; see
[run 001](../../development/RUNTIME_CONVERGENCE_20260905_RUN001.md).
The initial server stability window is not accepted. Subsequent per-socket
wired-interface pinning passed TLS/SSH checks. SIM removal and the actual FW-007
readback amendment were operator-confirmed. One live flash/boot reached Wi-Fi
and UTC, then failed on occupied outbox slots before modem start; actual FW-007
was restored with three-region verification and a 30-second startup smoke.
The live-only partition correction preserves the occupied range, passes native
readback reproduction, and builds with legacy. Full regression: 1,630 passed,
five skips individually explained in run 001; the S build check subsequently
passed 9/9. The corrected image's next bounded run changes both the consumed
one-attempt scope and the outbox write address. All three P0 Gates remained
`NOT_RUN`; within that historical approved scope no repeated permission request
was needed.
After operator reconnection, PnP and SetupAPI identify CH343 COM3; the WMI
serial inventory omits it and must not be used alone to declare it absent.
Subsequent authorized runs 002–004 validated the relocated outbox, corrected
main stack and confirmed same-owner GNSS-off cleanup. Run 004 identified an
initial AT terminal ERROR followed by successful cleanup; live main is now
corrected to wait briefly for Q's existing startup recovery before acquisition.
Runs 005-007 then delivered 16 real no-fix states over authenticated verified
HTTPS, with exact durable ACKs and bound Guardian API evidence. Reboot IDs and
actual delivery statistics were fixed and tested on two successive boots.
The shortest next GNSS seam now supplies a cancellable 30-second powered dwell
inside a 42-second request; four such acquisitions completed on the real board.
No fix was observed; antenna/sky placement is not yet operator-confirmed.
Legacy/live builds and final regression pass: 1644 passed, four individually
scoped skips in the [run report](../../development/RUNTIME_CONVERGENCE_20260905_RUN001.md).
FW-007 was restored at 10:48:12 UTC with verified transfers and startup smoke.
The continuous same-scope authorization recorded here was limited to that
historical Location run series. It does not authorize the current Camera/LTE
milestone, deployment, flashing, SIM traffic, or real-scene capture; those
actions require a new named bounded session. Next is real-fix validation after
antenna/placement confirmation; CALL/physical SOS and original concurrent
recovery remain open.
All three product Gates remain NOT_RUN. No further offline framework is needed.

## 2026-09-08 collector network-policy code slice

The collector now has an offline-testable Wi-Fi-priority route policy and an
explicitly opt-in USB LTE/PPP integration path. LTE admission requires the
observed SIM/registration/attachment state, an already configured CID 1/APN,
and an operator-verified USB descriptor; the firmware neither invents nor
writes APN settings. Loss of both routes leaves sensing and the append spool
running. Route, netif and generation are published as one snapshot. A route
generation change cancels the synchronous upload, retires its TLS connection,
and retains the pinned spool head unless the exact complete ACK matches.
LTE-to-Wi-Fi handoff publishes an offline generation until the uploader has
retired it and PPP DEAD/hangup are confirmed. Cleanup remains bound to the
original USB connection epoch; an unconfirmed cleanup emits no false
`LTE_QUIESCED`, disables LTE redial for the rest of that boot, and leaves stop
telemetry failed rather than claiming `STOPPED`.

The default tracked collector remains Wi-Fi/no-SIM and does not enable this LTE
path. Executable native and focused server coverage for policy
timeout/backoff/stale attempts, route flaps and retirement generations, strict
Wi-Fi/PPP interface binding, transport headers, cancellation/connection
retirement, aggregate-only Wi-Fi collection, privacy admission, USB connector
behavior, single-owner cleanup and independent stop facts passed locally
(52 core focused tests). An expanded 70-test regression covering the adjacent
LOC-021S and convergence paths also passed, with its one declared generated-
build proof skipped because that optional build-directory input was not set.
Clean ESP-IDF v5.4.2 builds from the final source also passed without flashing
for default (`896240` bytes, SHA-256
`78CE43F3FB749F7241DE70F6F3CA2EB08155A046C3B0F6AE7119D05E60D2EDBE`),
Wi-Fi/no-SIM collector (`990624` bytes, SHA-256
`D189EB7301759F22BE6F69C3E4C6564AC00BA8F1216770331186CA57A8FFDE4A`),
and LOC live (`993504` bytes, SHA-256
`DDF873865C12797183B05C1F8534B9C0839A919ED6FACDC40AA5086C8DA9EAF4`).
The usable installer profile was
`C:/Espressif/tools/Microsoft.v5.4.2.PowerShell_profile.ps1`; direct use of the
generic export had pointed at a stale missing Python environment.

The repository-wide verification gate for that slice passed from the same
source: `1716` tests passed with `12` pre-declared environment/build-evidence
skips.

`COLLECTOR-NET-COORD-NATIVE` subsequently extracted the collector's fixed-memory
LTE command, route-retirement and cleanup coordinator from `collection_main.c`
without changing its modem/wire ownership. The main remains the only task that
touches the SIM7670 UART and USB LTE connector; the extracted component owns no
task, netif, transport, spool or ACK state. A production-C native harness now
covers delayed admission and stale attempts, pre-DIAL failures, uncertain DIAL
cleanup, connection-epoch changes, route-generation retirement, Wi-Fi handoff,
UART/USB owner exclusion, graceful stop, invalid configuration, deadline
overflow and never-dialed idle facts. Coordinator/policy/USB/HTTPS/profile
focused validation passed `27/27`; adjacent LOC/profile validation ran 19
tests with one existing generated-build environment skip. Repository-wide
verification after the extraction passed `1726` tests with `12` pre-declared
environment/build-evidence skips. Three no-flash ESP-IDF v5.4.2 profile builds
also passed locally. Because those builds used a shared dirty workspace with
unrelated parallel changes, their binaries and hashes are not recorded as
final or release artifacts.

The LTE opt-in collector branch is still build-unverified because no ignored
overlay yet contains the operator-verified exact USB modem interface and
descriptor values; a synthetic value was not substituted. Its connector,
route policy and coordinator combination now have native execution evidence,
while the opt-in `collection_main.c` adapter compilation remains gated by that
real descriptor overlay. No flash, SIM traffic, network operation or hardware
command was performed. All P0 product Gates remain `NOT_RUN`.

The coordinator follow-up closes three fail-safe boundaries without claiming a
live LTE result. START and STOP actions are serial-numbered: exact STOP replay
cannot refresh retirement/cleanup deadlines or regress an active teardown
stage, while a stale/conflicting STOP reports `LTE_FAILED` for the actual owner
attempt so policy emits the matching STOP and retains the normal retirement
path. Attempt ID wrap from `UINT32_MAX` to `1` is covered by native execution.

Cleanup connector operations are now scoped to the captured USB connection
epoch inside the `collection_usb_lte` gate. Scoped begin, poll, cancel+poll and
quiesce return `STALE_EPOCH` without changing command, cancel or PPP state for
the newly connected lifecycle. The sole pre-check exception is connector-local
retirement of a generation-tagged netif residue left by the physical
disconnect: quick reconnect cannot erase that pending teardown, no new command
or PPP start is admitted until the old netif stop and observed PPP DEAD, and a
stale call can retire only that residue. The callback asserts an early I/O
fence before waiting for the connector gate, but only a separately committed,
gate-protected teardown fact may be drained, closing the pre-commit interleave.
The modem owner calls an explicit connector maintenance operation every loop,
so retirement does not depend on an old-epoch coordinator operation. A
separate status read followed by an
unscoped connector call is not treated as an epoch fence.
The connection epoch remains a boot-local 32-bit counter. This slice does not
claim an infinite stale-token lifetime across `UINT32_MAX` physical USB edges;
fail-closed exhaustion handling remains a pre-product hardening item.

Uploader retirement has one fixed cleanup deadline. If the uploader has not
retired by that deadline, the coordinator enters boot-local `LTE_DISABLED`,
emits no false `LTE_QUIESCED`, does not quiesce the active uploader/netif and
keeps same-modem UART work blocked because cleanup remains unconfirmed. The
main adapter also skips its final GNSS UART cleanup commands under that block.
This is a bounded terminal failure and can leave stop telemetry failed; it is
not clean shutdown evidence and does not authorize cross-epoch recovery.
The follow-up coordinator/USB/profile regression passed 36 focused tests with
one declared generated-build proof skipped because its optional directory was
not provided. Context lint and diff whitespace checks passed. Incremental,
no-flash ESP-IDF v5.4.2 builds also passed for the existing isolated default,
Wi-Fi/no-SIM collector and LOC-live configurations. The LTE opt-in main adapter
remains build-gated on the real operator descriptor overlay described above;
no substitute descriptor was introduced.

Privacy correction: collector Wi-Fi observations no longer emit or persist raw
SSID/BSSID values and retain only channel/count/RSSI aggregates with
`identifiers_retained=false` and an explicit reason. Data captured on 2026-09-06
predates this correction and requires a separate retention/deletion review
before reuse or distribution. This change did not delete or rewrite any report,
database, exported record or remote data.

This Wi-Fi privacy correction is deliberately **breaking**, not an additive
wire migration. The previous collector emitted `payload.aps[].bssid`; the new
server rejects that shape before opening a database transaction. A rejected old
record remains at the durable spool head because only a complete exact success
ACK may delete it, so an old backlog would block later upload. Therefore neither
the server guard nor a new collector image is deployable until the operator has
verified that the device spool is empty, or separately authorizes a bounded
local privacy purge with explicit loss accounting. The code does not turn a
privacy rejection into a positive ACK and does not silently discard queued
bytes. Existing server/report copies remain subject to the separate retention
decision above. The 2026-09-09 bounded operation subsequently cleared the
identified device collection partition, named local private report files and
the exact matching VPS Wi-Fi rows/associated raw frames after verified private
backup. The live service recovered healthy; the old remote copies were removed
after a sanitized remote recovery point was created.

---
id: P0-CONVERGENCE-20260905
title: Portable asynchronous raw collection on the assembled test unit
status: active
priority: critical
execution_state: wifi_raw_collector_bench_verified_field_network_pending
owner: codex_integrator
created: 2026-09-05
last_updated: 2026-09-06
serves_gate: P0-LOC
requires_hardware: true
runtime_authorization: founder_continuous_collector_wifi_bench_20260906
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
  - docs/architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md
  - docs/architecture/adr/ADR-0012-p0-productization-sprint-1.md
  - docs/architecture/adr/ADR-0013-call020-single-usb-phase-handoff.md
  - docs/architecture/adr/ADR-0014-runtime-convergence.md
  - docs/tasks/active/LOC-021_DEVICE_LOCATION_INTEGRATION.md
  - docs/tasks/active/CALL-020_LTE_DATA_VOICE_POC.md
  - docs/tasks/active/CALL-021_EMBEDDED_LTE_RTC_MEDIA.md
  - docs/tasks/active/SOS-010_SOS_WALKING_SKELETON.md
  - docs/tasks/active/OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md
  - docs/tasks/active/OPS-004_DEVICE_HTTPS_INGRESS.md
  - firmware/AGENTS.md
  - pc_simulator/AGENTS.md
  - quality_tests/AGENTS.md
  - shared/contracts/
  - docs/egolink_review_20260905/migration_manifest.json
allowed_paths:
  - firmware/mqtt_heartbeat/main/
  - firmware/mqtt_heartbeat/components/
  - firmware/mqtt_heartbeat/CMakeLists.txt
  - firmware/mqtt_heartbeat/sdkconfig* # existing profile/config files
  - firmware/mqtt_heartbeat/partitions_loc021_live.csv # preserve occupied RUN001 outbox range
  - firmware/mqtt_heartbeat/partitions_collection.csv # preserve NVS and both historical outbox ranges
  - firmware/audio_loop/sdkconfig.call_convergence.defaults # reviewed 15-second limit only
  - pc_simulator/ # concrete CALL connector and matching runtime only
  - server/ # minimum authenticated ingest, ACK and bound Guardian projection only
  - shared/contracts/ # integrator-reviewed additive compatibility changes only
  - quality_tests/
  - scripts/ # native validation, existing build and bounded experiment tooling only
  - docs/ # named runtime-convergence authority, packet, evidence and experiment updates
out_of_scope:
  - root AGENTS replacement or overwriting parallel work
  - firmware outside the existing Location, modem, transport, outbox and SOS seams
  - unsolicited pin, hardware or production BOM changes
  - shared protocol or state-machine changes without integrator review
  - model behavior, new sensors, camera AI, general event sourcing or full app work
  - HTTP downgrade, disabled certificate or hostname validation, committed secrets
  - automatic flashing, SIM traffic, recording, external notifications or deployment
  - claiming a P0 Gate PASS from source, native, build or isolated bench evidence
---

# P0-CONVERGENCE-20260905 — Deliver a live Location slice

## Current execution adjustment — founder instruction 2026-09-06

The current deliverable is the assembled portable asynchronous collection unit:
independent GNSS raw observations (including no-fix), Cell, continuous real
20 Hz IMU, available power readings, then Wi-Fi observations and bidirectional
Wi-Fi/LTE plus reboot-safe backlog upload to the existing Message Hub collection
view and complete authenticated export. CALL, product SOS, fusion accuracy and
uninstalled media do not block this engineering configuration. Product Gates
remain NOT_RUN. The prior bounded Location evidence below remains historical.

This explicit instruction supersedes conflicting scope/principle clauses for
this collector only: GNSS stays powered during a collection session; IMU has
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

On an identified connectivity node, a genuine GNSS/Cell observation changes
device-owned Location state and reaches an authorized Guardian via verified
secure transport. Guardian displays correct source/age/uncertainty and never
claims delivered, current or precise state from missing evidence.

This is the first runtime-convergence task. It does not claim P0-LOC, implement
all concurrent product ingress, or re-create the entire architecture.
Parallel CALL work delivers concrete connectors and evaluates an embedded bearer;
it does not block independent Location code delivery.

## Step 0 — reconcile the real workspace, then implement

Read root/module AGENTS, `docs/CONTEXT_INDEX.md`, product charter, NORTH_STAR,
FIRST_LAUNCH_EXECUTION, ADR-0011/0012/0013, BOARD_MATRIX, current active packets
and source owners. Check branch/HEAD/worktree before any edit; do not overwrite
uncommitted work. Compare uploaded-source hashes to actual files.

Merge the revision candidates with newer facts and allocate the ADR number.
Update absent-from-this-package authorities only after reading their full text.
The docs/AGENTS candidate must never overwrite root AGENTS.
The short routing/document update is the start of this packet, not completion.

## Step 1 — trace one executable path

Inspect actual entry/config selection → UART/modem owner → observation mapper
→ Location reducer/policy → emitter/outbox → secure connector → server ingest
→ bound Guardian projection. Produce a short seam checklist in the task result.
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

Configuration declares exact board/pins/transport, run limits, GNSS work budget,
upload cadence and storage-write budget. Candidate secrets live only in the
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
response truncation, cancellation, owner exclusivity and graceful shutdown.
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
Server/Guardian must bind the same device/run/image/observation identity.
No microphone/camera or non-test Guardian notification belongs to this run.

Stop on wrong device/image, unexpected reset/brownout/thermal issue, possible
concurrent modem owner, runaway writes/traffic, bad auth/TLS or privacy-policy
violation. Preserve evidence; restore the exact known image only within scope.

## Acceptance

| Layer | Required output |
|---|---|
| Code delivery | Concrete selected runtime, real transport implementation, executable tests, builds and migration |
| First live proof | Real device state reaches authorized Guardian on the verified route; age/source/failure correctly shown |
| Failure truth | No fake fix/ACK; incomplete responses retained for retry; cancellation bounded; local state degradation visible |
| Recovery | Candidate reset/retry scope accurately stated; unsupported power-loss/replay remains unclaimed |
| Handoff | One concise result naming user-visible change, source/config/image, measured evidence, remaining blocker and next action |

A successful build can complete the code-delivery portion, but not the live
portion. Mark `runtime_waiting_authorization` where appropriate. Do not mark the
entire packet or product gate PASS while the only evidence is offline.

## Parallel CALL slice: separate writer and clear stop point

Reuse CALL-010 endpoints and CALL-020 A-R. Close real authentication, concrete
TLS/route, Guardian endpoint, RESULT/post-stop telemetry and heap/stack counters.
Demonstrate both acoustic directions first; then repeat on a source-bound verified
SIM/LTE path. Existing longer/repeated CALL-020 campaign requirements remain.

Compare the existing custom bridge against a pinned maintained embedded RTC
candidate using exact board/codec/IDF compatibility, license, memory, transport
and measured integration effort. Do not adopt a new stack solely from a README.
A short embedded bearer probe may start before final HW-022. It must use the
same single modem ownership design; final CALL-021 still waits for product
hardware. Freeze additional generic PC-bridge layers unless a real run needs them.

## After the live slice

Integrate SOS physical input, distinguish recognized/stored/server-received/
terminal-noticed/human-acknowledged, and test full/storage failure and missing
GNSS. Join pending-event recovery and independently powered carry tests.
Start power/RF/Guardian-reachability measurements early, then use representative
campaigns before promoting product gates.

## Do not expand this task into

Universal sensor event sourcing, a new training platform, camera awareness,
production BOM freeze, full repository rewrite, arbitrary API churn, new visual
Dashboard report panels, or purchasing a new chip to avoid diagnosis.

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
one-attempt scope and the outbox write address. All three P0 Gates remain
`NOT_RUN`; no repeat permission request is needed inside an approved scope.
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
Continuous same-scope work is authorized; historical per-image proposals do not
require renewed approval. Next is real-fix validation after antenna/placement
confirmation; CALL/physical SOS and original concurrent recovery remain open.
All three product Gates remain NOT_RUN. No further offline framework is needed.

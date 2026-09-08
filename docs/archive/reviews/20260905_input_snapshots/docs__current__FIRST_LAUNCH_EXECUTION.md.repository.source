---
document_status: authoritative
last_verified: 2026-09-04
verified_by: founder/codex
decision_adr: ../architecture/adr/ADR-0012-p0-productization-sprint-1.md
---

# EgoLink Productization Sprint 1 Execution Baseline

## 2026-09-04 Current Convergence

The offline Location boundary has advanced through `LOC-021Q/R/S`. Q provides
the exact single modem owner and bounded cleanup/power-off recovery; R connects
durable SOS signalling, urgent GNSS and deferred Cell work without silently
dropping a coalesced retry. S adds a separately selected modem-only firmware
profile with a read-back-verified NVS boot epoch, the shared durable outbox and
an explicitly offline/no-I/O transport callback. The Q/R/P/O selection passes
`54/54`, S plus Q passes `21/21`, and the combined critical selection passes
`110/110`. A clean S build at `tmp/loc021s_profile_clean_20260904_c/` is
`0x5DC90` bytes with `0xA2370` bytes (63%) free; the final clean default build
at `tmp/loc021s_default_clean_20260904_b/` remains `0xDACF0` bytes with
`0x25310` bytes (15%) free. S is an isolated modem-only bring-up profile, not
the concurrent SOS/IMU product composition or secure server transport.

The offline Call boundary has advanced through `CALL-020R`. R adds the
default-off, single-task device lifecycle owner around the Q responder and
media runner. Cleanup is phase-idempotent and retained until it can prove
worker join, runner close, lease return and physical uninstall; the
post-MEDIA deadline/clock-failure path now enters the media finalizer instead
of the pre-media abort path. R/Q focused checks pass `33/33`. The clean default
and owner builds are respectively `0x2FB70` bytes (81% free) and `0x45930`
bytes (73% free). Authentication, real TLS/route establishment, RESULT and
post-stop telemetry, measured runtime memory and live media remain open.

No flash, device control, SIM traffic, VPS deployment, physical SOS or media
I/O occurred in this slice. The final repository-wide `scripts/verify.ps1`
run passes `1614` tests with `12` environment-guarded skips. `CALL-010` remains
`accepted_for_transition`, ADR-0013 remains `proposed`, and all three product
Gates remain `NOT_RUN`.

## Outcome and Hard Gates

The first sellable P0 is exactly:

```text
Reliable Location + Ego Call + physical SOS
```

| Gate | Product capability | Launch rule | Current state |
|---|---|---|---|
| `P0-LOC` | Guardian sees a fresh, honest, reliable device location | must PASS | `NOT_RUN` |
| `P0-CALL` | Device and Guardian establish reliable two-way voice | must PASS | `NOT_RUN` |
| `P0-SOS` | Long press causes durable alert, priority location and immediate call attempt | must PASS | `NOT_RUN` |
| `L2-AI` | GNSS reliability and mobility enhancement | non-blocking | data/replay only |
| `L3` | context, camera AI and broad state understanding | outside Sprint 1 | deferred |

The three capability Gates are necessary, not sufficient, for sale. Power,
RF, acoustic, water/structure, privacy/security, compliance, manufacturing and
NPI evidence remain cross-cutting release requirements. A PC reference, build,
fixture or development-board smoke cannot change a Gate from `NOT_RUN`.

## User Loop

```text
Guardian opens the minimum surface and sees where the device is
             +
Guardian calls device / device calls bound Guardian
             +
long-press SOS
-> durable local event and local feedback
-> upload last trusted location immediately
-> start high-priority GNSS/LTE policy
-> notify Guardian
-> request Ego Call
-> show location age/confidence/uncertainty, battery, alert and call state
```

Camera and AI cannot veto, fabricate or delay this loop.

## Sprint 1 Scope Freeze

In scope now:

- deterministic device-operational Location Engine v0;
- configurable Sensor Policy v0 and event-time Replay;
- exact-board microphone/speaker bring-up, LTE-data media and embedded RTC path;
- durable physical SOS composition and minimum Guardian surface;
- representative field/power/RF/acoustic evidence;
- A0 interface architecture and qualified China pre-compliance input.

Not on the critical path:

- new sensors, learned multi-source fusion or coordinate regression;
- anomaly/danger models, camera AI, broad context understanding;
- polished/full App, contacts, multiparty calls, recording or AI voice;
- PSTN/SMS/public emergency dispatch or Native VoLTE as launch dependencies.

Native VoLTE remains `G0V-VOLTE-RESERVE`. Camera may only be a manually
authorized experimental still source with trigger reason and event time.

## Current Dependency Graph

```text
LOC-020 -> POLICY-010 -> REPLAY-010 -> LOC-021 -> FIELD-020 ----+
                                             |                  |
CALL-001 -> CALL-010 -> CALL-020 ------+      +-> SOS-010 -------+-> release
HW-020 -> HW-021 ----------------------+-> HW-022 -> CALL-021 --^
OUTBOX-010 ----------------------------------------------------^

HW-022 + LOC-021 + CALL-021 + SOS-010 -> PWR-020

FIELD-020 + SOS-010 + OUTBOX-010 + OPS-004 + PWR-020 + HW-022
    + COMPLIANCE-010 + acoustic/RF/water/security/privacy/NPI evidence
    -> P0-RELEASE-010
```

LOC-020/POLICY-010/REPLAY-010 were implemented and accepted sequentially as one
PC reference boundary; their completion now permits LOC-021 dispatch but is not
hardware or P0-LOC evidence.

The arrows above describe product-evidence dependencies, not a rule that every
offline host slice must wait. LOC, CALL and SOS adapters may be developed and
tested in parallel against frozen contracts; only their physical/live
composition and Gate claims must wait for the named upstream evidence.

## Lane A — Reliable Location

### Accepted PC reference boundary

- `L1-000` and `LOC-006` are accepted for transition.
- `LOC-020` provides an atomic event-time reducer with explicit mobility, GNSS,
  LTE, battery, policy, last-trusted, belief, accuracy, confidence, source and
  uncertainty state. Trusted coordinates require capture-bound lineage.
- `POLICY-010` provides one semantically validated engineering configuration
  for stable, moving, uncertain, low-battery, GNSS timeout/backoff and SOS.
  `SOS > LOW_BATTERY > LOCATION_UNCERTAIN > MOVING > STABLE`, while condition
  flags remain independent and camera remains OFF.
- `REPLAY-010` reuses Field Session evidence, emits timer-driven state/action
  timelines, strips private coordinates and compares configuration behavior
  without claiming measured accuracy or battery savings. The real FT-001B
  fixture retains 2 GNSS observations and 100 annotations from 103 rows; both
  fixes remain rejected because source quality is absent.

Independent review closed the named semantic blockers. LOC/POLICY/REPLAY tests
passed `50/50`; repository verification at that acceptance point passed
`875/875`, and the later merged Sprint 1 suite passed `929/929`. Standard JSON
Schema cannot express sibling arithmetic or capture-nanosecond division, so
LOC-021 must port the named semantic validator and capture-time checks. These
are accepted reference artifacts, not P0 evidence; `P0-LOC` remains `NOT_RUN`.

### Next hard slice

LOC-021 A-S now spans the standard-library runtime, SQLite append-only
timeline/current state, authenticated bounded HTTP ingest, native device
Location Engine and Sensor Policy cores, state emission, exact-byte persistent
outbox delivery/ACK, hashed Guardian-device authorization and a hardened
minimum Guardian page, plus a transactional Engine -> Policy -> emitter ->
outbox pipeline, a default-off device runtime owner, a caller-timed hardware
observation mapper, a fixed-capacity priority modem arbiter, an owner-free
executor, a bounded SIM7670 GNSS/LTE adapter, the exact single modem owner,
durable SOS/Cell scheduling and an isolated modem-only boot profile. It binds
device/boot/session/sequence/observation identity, exact policy identity and
source-event time; server receive time does not replace the source clock. With
the additive SOS server slice, root verification of the combined Message Hub,
location, Guardian and SOS boundary passes `194/194`.

This remains offline/build evidence. The immediate correctness slice is
`LOC-021T0`: a fixed-capacity durable ingress WAL ordered by source occurrence
time, with per-producer inclusive watermarks and sequence allocation only when
the head can be sealed. A shared RAM counter is insufficient because a later-
arriving SOS edge may have an earlier logical occurrence time. `LOC-021T1`
then bridges mapped sensor and durable SOS records into the single Q/O/K drain.
It cannot claim reboot equivalence until K reducer/policy/last-identity/retry
state has a persistent checkpoint, or an equivalent full-replay path includes
an exact outbox tombstone probe and no-output replay. Applied records must stay
retained until that checkpoint proves safe compaction.

This revises the earlier broad journal deferral: T is not required for a
separately authorized bounded modem-only S smoke, but it is required before the
concurrent SOS/IMU product profile can make crash-safe ordering claims. Secure
device-to-Message-Hub transport and the live/reboot run remain separate work.
Only an accepted live LOC boundary permits FIELD-020 product claims.
`P0-LOC` remains `NOT_RUN`.

FIELD-020 reuses FT-001B, FIELD-003/004, D2/D5 and PWR tooling across outdoor,
indoor, mall, underground, walking, vehicle, stationary and bag-carried
conditions. L2-001 continuous IMU and later GNSS Reliability/Mobility models
remain queued behind LOC-021 and cannot block this work.

## Lane B — Ego Call and SOS

`CALL-001` is accepted control/replay evidence, not media evidence. The current
boards split capabilities: the wearable board has accepted-for-transition
basic input/output endpoint evidence and no LTE; the connectivity board has
LTE/GNSS evidence and no accepted audio application path.

- `CALL-010`: separately prove known playback, two microphone inputs and
  120-second simultaneous capture/playback on the exact wearable board.
- `CALL-020`: explicitly use a PC/USB development bridge to measure LTE-data
  media setup, two-way traffic, loss/jitter/gaps and recovery under the chosen
  configurable codec/transport. SIM7670G RNDIS/ECM and sustained media are
  planned/unverified until measured.
- `CALL-021`: remove PC and USB media/control from the path on an exact
  integrated independently powered prototype. This is required before
  `P0-CALL` can pass.
- `SOS-010`: compose the existing safety-event semantics, LOC-021, OUTBOX-010,
  Guardian alert and CALL-021. It does not invent a second SOS contract.

CALL-010 is `accepted_for_transition` on the development-board basic endpoint
boundary. Run 007 binds an operator-confirmed spoken input window to an
approximately tenfold logical-channel RMS increase, and run 008 completed its
three staged writes/register readbacks/final PA-off checks before the operator
reported the bounded sequence clear and normal overall. Individual run-008
stages were not separately confirmed. No raw audio was retained, the 4G board
was untouched, and UI-001 was restored and smoke-checked. This evidence does
not prove application-level full duplex, product acoustics, SPL, AEC/AGC or
`P0-CALL`; those states remain unverified/`NOT_RUN`. CALL-020 A-R now supplies
the metadata oracle, bounded host media runtime, strict framing/preflight,
concurrent bridge structure, wearable framing core, USB Serial/JTAG byte
endpoint, four-worker codec/I2S composition and a retained non-autorun operator
API, plus a default-off audited host control lifecycle whose CLI is plan-only,
the proposed single-USB phase boundary, a strict host CONTROL-to-MEDIA
connector with bounded boot-prefix drain, a default-off device EGLC responder
and a separately selected single-task device lifecycle owner.
A clean G build keeps the complete D/E/F chain in its ELF; the image is
`254,592` bytes and has `251,057` bytes of linker-reported shared D/IRAM
remaining. The boot stub is deliberately inert. Four `4,096`-byte stacks and
unmeasured TCB/driver/DMA/ring heap still require a measured runtime audit.
H adds a caller-injected, bounded ROM-prefix/EGLM serial resynchronizer and
passes `14/14`. I supplies strict process-local authenticated relay admission,
J validates a caller-injected already-connected TLS socket against frozen
external attestation/decision, and K adds a default-off exact-port OS serial
owner without enumeration, guessing or automatic reconnect. K passes `19/19`;
the CALL-focused set through K passes `166/166`, and the CALL contracts plus
CALL-010 static set passes `198/198`. L composes the K/H and J legs into the
actual four-worker bridge behind explicit single-use `open/start`; L passes
`15/15`, the focused set through L passes `181/181`, and the combined set
passes `213/213`. M's independently audited host lifecycle passes `24/24`;
the final CALL selection through M passes `237/237`. R now owns the Q responder
and media runner through bounded CONTROL, MEDIA, quiesce and retry-until-proven
cleanup phases. R/Q focused checks pass `33/33`; the final owner image is
`0x45930` bytes with 73% of its factory partition free.

These results retain no raw media. The dedicated R profile is default-off and
ran no real I/O; its independent reviews found no remaining offline
correctness/safety blocker. Authentication, real TLS handshake/listener/PKI
and route, RESULT/post-stop telemetry, verified SIM/LTE route, measured
runtime memory and real bidirectional media remain unconnected. Current RNDIS evidence is
read-only enumeration only; historical source-bound ping/curl through
`192.168.0.100` timed out, so an Up interface is not LTE-route evidence. Real
media still requires separate operator intent. CALL-021 remains queued behind
CALL-020 and HW-022.

SOS-010 A-J now covers isolated host semantics, dormant physical long-press
input, transport-free device orchestration, strict durable server ingest/ACK,
bound-Guardian latest-alert read and an independent human acknowledgement. The
device ordering is durable critical enqueue before feedback, SOS policy,
urgent location and an independent call attempt. E validates exact persisted
payload/response identity and deletes only on an accepted/duplicate durable
ACK; malformed 2xx responses retry. F/G add a default-off sampled-input owner
and a fixed 320-byte pending-edge journal that persists a qualified edge before
sequence consumption/orchestration and replays exact identity. H adds the
build-only fixed NVS callback backend; clean ESP32-S3 build and focused tests
pass, but no NVS callback, reboot or power loss ran and storage atomicity/
endurance remain unverified. Real device transport, push notification, remote
call and physical button execution remain unverified. The physical SOS product
slice still depends on the live
LOC/CALL/outbox adapters; `P0-SOS` remains `NOT_RUN`. Its accepted retention
value is not enforced by expiry or verified erasure, and the current database
has no product at-rest encryption/key lifecycle.

Hardware execution, flashing, audio capture, SIM traffic and VPS/RTC changes
require explicit operator intent and named evidence. CALL-020 success is only
`pc_side_verified`; it cannot be promoted to embedded or product evidence.

## Lane C — Reliability, Security and Power

- `OPS-004` removes public plaintext device ingress through a bounded TLS and
  rollback slice.
- `OUTBOX-010` owns write-before-send, stable event identity, ACK deletion,
  reboot recovery, bounded capacity and explicit overflow for priority events.
- OUTBOX-010 now has the mirrored persistent core, exact ACK identity, critical
  reserve and a raw-partition adapter. The adapter rewrites one complete
  `22,240`-byte slot per mutation, so it is field-test-only and is not a
  product-endurance, confidentiality or brownout claim.
- Its single dispatcher and default-off delivery runtime now route both
  `manual_sos` and `location_state`, invoke at most one injected POST per ready
  attempt, and retain uncertain settlement for explicit no-resend recovery.
  G/H add the bounded exact-byte SIM7670 seam and split-phase cooperative SOS
  preemption; real exact-board TLS/UART truth and authenticated runtime remain
  in progress.
- PWR-001 remains a development-board baseline; PWR-020 owns the integrated
  mode matrix and measured 48-hour guard result.

These are not optional polish. SOS durability, authenticated ingress and honest
failure state are release requirements, while their implementation proceeds in
parallel with audio and location work.

## Lane D — A0 and China Readiness

`HW-020` is accepted only as a P0 block/interface baseline. HW-021 now owns the
exact part/down-select and buildable design pack; HW-022 owns procurement-
authorized assembly and bring-up of the independently powered integrated
prototype. HW021-C0.1 now supplies a primary-source candidate matrix,
conditional UART/USB bearer and audio/storage/power/RF worksheets, but makes no
selection. Exact modem/battery identities, measured media budgets, calculations,
compliance constraints and independent review remain open; product selections
are therefore still `unknown`/`unverified`, and CALL-021 has no valid execution
target.

`COMPLIANCE-010` is the sole successor to PROD-002. Its evidence intake is
ready and the HW-020 concept is available, but no sent inquiry is recorded, so
it remains queued for founder authorization and minimum founder inputs. A named qualified
opinion—not web research—must address SRRC, 进网/分类, CCC, SAR/exposure,
battery/charging, intended users and child-product questions.

## Immediate Execution Order

1. In parallel, implement LOC-021T0's durable source-occurrence ordered ingress
   WAL and its persistent-watermark tests; close CALL authentication, real
   TLS/route, RESULT/post-stop telemetry and runtime-memory evidence around the
   R lifecycle; and confirm the OPS-004 exact-board/live-authorization
   boundary. Do not wait for L2 or unrelated lanes.
2. Continue HW-021, OPS-004, OUTBOX device/server integration and the
   conditional COMPLIANCE-010 inquiry independently at their own authorization
   boundaries.
3. With fresh operator intent, the isolated S profile may run a bounded
   modem-owner/GNSS cleanup smoke without waiting for T. Secure Location
   device-to-Message-Hub ingest, CALL media over a verified SIM/LTE route, and
   physical SOS delivery/call state each remain separate authorized slices.
   Feed measured CALL budgets into HW-021/HW-022.
4. Run FIELD-020 after the live LOC-021 boundary without waiting for L2. Build
   and bring up HW-022, then run CALL-021 without PC/USB media/control and
   complete physical SOS composition against LOC/CALL/outbox.
5. Run PWR-020 and the representative-day loop, freeze objective Gate Criteria
   v0 before final acceptance runs, then execute P0-RELEASE-010.

## Stop-the-Line Conditions

- Any of `P0-LOC`, `P0-CALL`, `P0-SOS` is not PASS at release review.
- A coordinate, delivery, call-connected or emergency-success state is
  fabricated from missing/stale evidence.
- SOS can be suppressed by low battery, AI, camera, network or server failure.
- Critical event identity/durability or authentication is missing.
- PC/USB bridge evidence is labelled as independent product behavior.
- Product hardware/compliance is frozen from board names, web assumptions or a
  passing build rather than official and measured evidence.

## Current Evidence Boundary

CALL-010 now has accepted-for-transition basic development-board input/output
endpoint evidence: the spoken-input metric response and clear/normal overall
speaker result are recorded without raw-audio retention, the 4G board was
untouched, and UI-001 was restored. It is not full-duplex, LTE/RTC or product-
acoustic evidence. LOC-021 A-S, CALL-020 A-R, SOS-010 A-J and the current
OUTBOX components strengthen the offline implementation boundary, but do not
supply device/live-network/deployment or end-user evidence. The location/
Guardian/SOS server regression is `194/194 PASS`; CALL-020G/H close the earlier
dead-link and host-resynchronization questions, while I/J/K add offline relay,
connected-TLS and explicit OS-serial seams; L composes those legs and M owns
the inert/default-off host lifecycle. N-R add the proposed single-USB phase
boundary, strict host connector, device responder and device lifecycle owner;
R/Q focused checks pass `33/33`. Location Q/R/S add the exact modem owner,
durable scheduling seam and isolated modem-only profile; the combined critical
selection passes `110/110`. Both paths remain offline. Location still lacks
the durable ordered product-ingress/checkpoint bridge, secure transport and
live evidence; Call still lacks authentication, real TLS/route, RESULT/post-
stop telemetry, verified LTE route and measured runtime memory.
The shared dispatcher/delivery owner and SOS pending-edge NVS backend are
build-only, while the persistent outbox partition remains field-test-only. No current
RNDIS observation proves an LTE route. No procurement,
compliance submission or external-message action occurred, and real hardware/
network actions require fresh explicit operator authorization. All three P0
Gates remain `NOT_RUN`.

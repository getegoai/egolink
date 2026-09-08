---
document_status: engineering_delivery
checked_at: 2026-09-05
execution_state: code_delivered_runtime_tracked_in_run001
---

# Runtime convergence delivery and combined experiment request

This records the initial code-delivery checkpoint and the exact experiment
proposal subsequently approved by the operator. Later deployment, actual
failed live boots, restoration and subsequent successful no-fix delivery are
tracked in [run 001 and its appended runs](RUNTIME_CONVERGENCE_20260905_RUN001.md).
Runs 005-007 establish the bounded real-device-to-Guardian API slice, including
cross-boot identity and powered acquisition; coordinate-fix and product
acceptance remain incomplete. `P0-LOC`, `P0-CALL`, `P0-SOS` remain `NOT_RUN`;
the initial source/native/build results below are not hardware evidence.

## Workspace and migration

Base: branch `a0/first-real-field-session`, HEAD
`72c7a1ed199fa6bc522defff0d77a0aa3e77034d`. At entry the tracked worktree was
clean; `docs/egolink_review_20260905/` was the existing untracked input. No
commit, reset, checkout, root AGENTS replacement or parallel-work overwrite ran.
Two executors had separate docs and CALL files; the integrator owned shared
Location/SOS state, protocol review, build and final regression.

The actual directory was `docs/egolink_review_20260905`, not `doc/…`.
All five replacement bases match the supplied manifest; changes were merged
with actual dated facts. The sixth, older desktop-oriented master snapshot
differs from current master v2.2 and is archive-only. Candidate ADR numbering
was resolved to unused [ADR-0014](../architecture/adr/ADR-0014-runtime-convergence.md).
Root AGENTS is unchanged. All six input snapshots and fourteen actual originals
are preserved with hashes in the [migration map](../archive/reviews/20260905_input_snapshots/migration_map.json).
Current charter, scope, master, North Star, execution/roadmap and task routing
now point to the accepted direction. Original concurrent/recovery commitments
are retained; T0/T1 do not globally block S or this one-source experiment.

## Executable seam checklist

| Seam | Delivered behavior and limit |
|---|---|
| Entry/config | Separate `loc021_live_main.c`; legacy `app_main.c` and original S remain distinct. Exact connectivity-node MAC guard, existing UART RX17/TX18/115200, no pin changes. Actual build selects Wi-Fi HTTPS and Q; no legacy modem/network loop is started. |
| Physical source/owner | Existing Q/P/O and SIM7670 bounded driver; one exclusive UART task, bounded GNSS acquisition and confirmed power-off. Concurrent start, status during execution, stop admission and quiescence execute on real OS threads in native tests. |
| Time/quality | Acquisition completion is captured before cleanup. A frozen SNTP anchor maps capture to `timestamp_utc_ns`; no receive-time substitution or GNSS-UTC claim. Without a usable anchor, local monotonic evidence continues and Guardian age remains incomparable. SNTP error/accuracy is unmeasured. Missing/zero HDOP is a fix candidate rejected by core quality rules, never invented no-fix or accuracy. |
| Local state/persistence | Live owner opts into local reducer/identity progress even when serialization/enqueue/storage fails; returns explicit degraded status. Legacy retry latch remains the default. No outbound durability or cross-boot local checkpoint is implied. Full queue keeps existing retention policy and exposes enqueue/storage failure. |
| Secure delivery | Real IDF `esp_http_client` over a concrete certificate-bundle TLS transport. Exact HTTPS DNS origin, hostname verification, bearer, no redirect or HTTP fallback. Every TLS read/write checks deadline; total response wire bytes capped at 16 KiB, complete declared ACK body at 8 KiB. Failed/truncated/late/cancelled/wrong ACK retains the record; only strict matching durable-ingest ACK can delete it. |
| Server/Guardian | Existing Message Hub authenticated ingest, SQLite store, exact-byte ACK builder and hashed Guardian/device binding are reused without server/schema changes. Native Q-emitted UTC bytes execute through the actual store, ACK builder, restart and authorized Guardian projection; source age is 5000 ms when receive age is 1000 ms, and no-fix has no position. Deployment remains pending. |
| Observability | Boot/run/clock, sequence, source GNSS/belief, trusted sequence/time, age validity, event-time accuracy/uncertainty, persistence failure, delivery attempts/settlement and matching ACK deletion counters. No raw coordinates, cell IDs or credentials are logged by the profile. ACK deletion means server ingest, not Guardian display/human notice. |
| SOS/recovery | Qualified-input callback precedes storage and is separate from stored/delivered feedback. Journal failure still attempts independent local/policy/outbox branches while retaining nondurable pending identity. Recovery explicitly suppresses call re-trigger without durable active-session/expiry proof and reports partial recovery; it does not silently claim full recovery. Physical GPIO input and concurrent SOS/IMU ordering remain unwired in this single-source profile. |
| CALL | Concrete source-bound mTLS relay/Guardian/wearable entries, real duplex OS/TLS tests and a 15-second R image. The SSLSocket simultaneous read/write race is fixed. RESULT/post-stop remains unconfirmed; no new post-MEDIA protocol was enabled. See [CALL delivery](CALL_CONVERGENCE_20260905.md). |

Storage is still the existing field-test backend: each mutation rewrites a
22,240-byte slot with a 24,576-byte erase region. This is not product endurance
or encrypted storage. Local state after reboot starts a new boot-scoped run;
only the existing outbox/pending journal has its tested recovery scope. An old
pending SOS cannot prove that a prior call remains active. These limitations do
not waive the original checkpoint, tombstone, no-output replay or Call campaign.

## Actual validation and evidence scope

Final logs and complete source/config/application/bootloader/partition hashes:
`tmp/convergence_evidence_manifest.json`. It identifies HEAD plus dirty source
hashes, not an invented firmware commit. Builds use pinned ESP-IDF **5.4.2**;
the firmware toolchain/dependencies were not upgraded. Private live credentials
were copied from the existing ignored `sdkconfig.vps.local` to ignored
`sdkconfig.loc021_live.local`; values and images are not committed.

| Layer | Executed result / evidence |
|---|---|
| Repository | `scripts/verify.ps1`: 1628 discovered, 1624 passed / 4 selector skips (three native harnesses separately rerun); final transcript `tmp/convergence_verify_final_candidate.log`. Context lint and diff check: PASS, `tmp/convergence_final_checks.log`. Source-shape checks are not counted as hardware/native concurrency. |
| Native C | `quality_tests.test_runtime_convergence_native`: real mapper/reducers/emitter/outbox, queue/write faults, exact parser/adapter/delivery harnesses, Q threads, UTC→SQLite/ACK/Guardian, concrete HTTPS transfer with injected SDK faults including slow/oversized headers. Existing native SOS journal/input/recovery and Location core/policy/pipeline tests also executed with GCC. |
| PC network/native | CALL 10 new tests passed, original CALL 228 passed; duplex repeated 20 times. Real loopback TCP/OpenSSL mTLS/role authentication and four workers; synthetic PCM, no audio devices. `pc_simulator/runtime/call_convergence_20260905/native_tls_tests.log` and `validation.json`. |
| Build | Legacy, full live, original S and CALL 15-second profiles passed. Compile graphs select only the intended entry; linked live symbols retain Q and concrete HTTPS. No image was flashed. |
| Embedded RTC candidate | Pinned esp-webrtc-solution v1.2.0 / esp_peer 1.2.7 / libsrtp 1.0.0 actually compiled on IDF5.4.2 but failed final link: prebuilt peer archive references missing `esp_log`. Not adopted; see CALL report and `rtc_peer_build.log`. |
| Hardware / external network / field | NOT_RUN: no serial/modem/SIM/flash/audio device, external service deployment/notification, acoustics, target TLS handshake, GNSS fix or independent-power experiment. Native SDK fault injection is not an ESP TLS handshake. |
| Product | All three P0 Gates remain NOT_RUN. |

Native runner: official [w64devkit v2.4.0](https://github.com/skeeto/w64devkit/releases/tag/v2.4.0),
download checksum verified (`80678c29a56982d7d3b342f12a0060157df5654c38d82d4adc40704070d6aafb`),
installed only under ignored `tmp/native_tools/`. Tests compile real C and IDF
cJSON/mbedTLS SHA implementations; no source-text substitute for native behavior.

Every skip touching this path:

1. P0 delivery freestanding harness: original Espressif clang/lld host selector
   skips; the **same C harness executes on native GCC** in the new suite.
2. SIM7670 exact parser harness: same selector skip, same harness rerun on GCC.
3. SIM7670 exact adapter/wipe/timing harness: same selector skip, same harness
   rerun on GCC. Native execution exposed an old test-instance reuse bug; the
   second independent invalid-init case now starts with a zeroed instance.
4. CALL USB Serial/JTAG C lifecycle harness: cross-compiled, native execution
   still skipped by its host selector. Its C endpoint lifecycle is not claimed
   native-verified; real USB/task/codec behavior remains pending. The separate
   PC mTLS/duplex and Q OS-thread tests do not substitute for this capability.
5. S generated-build check initially skipped without a build directory; S was
   actually built and `EGOLINK_LOC021S_BUILD_DIR` supplied for final verification.

The initial full regression found two stale assertions (dependency union and
SOS journal-failure liveness). They were updated to the reviewed behavior,
retaining native fault/restart checks and adding explicit no-call replay checks.
No test was deleted. Empty-SSID builds were rejected as evidence of the full
live path because the compiler removed it. The full debug build exceeded the
retained factory partition by 44,848 bytes; profile-only size optimization now
fits without enlarging the partition. Earlier failing logs are retained.
Final composition review also fixed Q's missing copy of the local-progress
option; the native thread test now injects storage failure through Q→O→K and
checks that local sequence/state still advance, rather than only testing K alone.

Final application identities (all unflashed; full auxiliary hashes in manifest):

| Profile / build directory | Bytes | Application SHA-256 |
|---|---:|---|
| Legacy / `tmp/convergence_legacy_build` | 896240 | `523e2d86a1c665200e18b6ad098d55be601ae27c4c31798425d9fe01a751eb05` |
| Live / `tmp/convergence_live_build` | 988992 | `8a0e6eff29868a1f9ba22e74026b42de3656e64ad5710c69f88342ac03601a87` |
| S / `tmp/convergence_s_build` | 385856 | `7b8d986b8f99226f652ab9684c66f75763eac75ac5e9e2bcee6b3a4a645e0450` |
| CALL 15 s / `tmp/convergence_call_build` | 284976 | `6b71a697134d588f5d954832df76a9bb07e796bfb30b4f4816ab4a72f70c864e` |

Final Location build commands use the pinned IDF environment and working
directory `firmware/mqtt_heartbeat`:

```powershell
idf.py -B ../../tmp/convergence_live_build -D SDKCONFIG=../../tmp/convergence_live_delivery.sdkconfig -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.outbox_partition.defaults;sdkconfig.loc021_live.defaults;sdkconfig.loc021_live.local" build
idf.py -B ../../tmp/convergence_legacy_build -D SDKCONFIG=../../tmp/convergence_legacy.sdkconfig -D SDKCONFIG_DEFAULTS=sdkconfig.defaults build
```

Corresponding final logs are `tmp/convergence_live_verified_build.log`,
`tmp/convergence_legacy_verified_build.log`, `tmp/convergence_s_verified_build.log`
and `tmp/convergence_call_final_build.log`. `nm` and compile-graph checks retain
one `app_main`, Q start/exclusive backend and concrete bounded TLS functions in
the live ELF. The CALL config is checked to contain an actual 15-second limit.

## Combined experiment request — subsequently approved

The operator subsequently replied **“同意，你继续”**. Execution and remaining
physical prerequisites are recorded in [run 001](RUNTIME_CONVERGENCE_20260905_RUN001.md).
The text below is the approved scope; “not run” statements describe the code
delivery snapshot, not later server deployment evidence.

Approve one staged bench experiment, with stop-on-failure between stages. No
operation below has run in this delivery. The operator approval, participants,
relay/Guardian endpoint and source interface must be recorded once for the run;
commands inside that approved scope need no repeated approval.

**Identities and recovery precondition.** Connectivity-node-001 is MAC
`02:00:00:00:00:03`, logical device `ego-link-001`, historical COM3 console and
COM4–7 modem. Wearable-node-001 is MAC `02:00:00:00:00:01`, historical COM8.
Reidentify USB/PnP/MAC, image descriptor and flash geometry at run time; no
guessing a COM port. Use one owning process per connection.

FW-007 expected restore application is 984,912 bytes, SHA-256
`8F3508C62CA96C54628B3C3FB0A64B5BB14EAF7BBB8188DA54FAEE0739283799`;
bootloader `1EDDD94A293C483AF64AFA6C1EED83EFA24D6FD7746A5D07AFEEFC189364B66E`,
partition `7F00B6C042A89B15B0CAC534F82ED988CAF29278FF5700B0C511EB1B5BB7C820`.
The named local app is now **985,168 bytes / A9894A86…EA36C7D**, not that
restore image; no matching application was found among the 14 local MQTT
heartbeat build images. Do not flash that mismatch as FW-007. Obtain the exact
backup first, or include a **single bounded pre-flash readback** of the current
connectivity board's first 2 MiB (capacity checked first; at most 120 seconds),
verify the expected app/boot/partition hashes and preserve it privately. If any
identity differs, stop before changing flash and reconcile the baseline.
This request does not automatically authorize an unknown replacement image.

UI-001 application exists and matches:
`firmware/amoled_safety_demo/build/egolink_amoled_safety_demo.bin`,
`11D72868A956E86F7B91D1B9D6008404FBD02B61299D566399DDC90F50A23139`.
Available bootloader SHA is
`2248730A914CA30FDEC279FE065EB3CB7F1E3C5CBB3F49BE33E6F1C358A9AD63`;
partition SHA is the same `7F00B6…7C820` above. Record this complete restore set
and check it before any wearable flash.

**Location stage.** One connectivity flash of the final live set in the manifest,
then one boot. Wi-Fi station transport to `https://ego.example.invalid`, exact DNS
hostname and normal CA verification; no SIM data is requested for this stage.
Keep the SIM absent during Location, backup and restore boot checks; prepare
this with the board unpowered. SIM insertion/data is limited to the explicitly
included CALL LTE phase, then remove it before restoring/booting FW-007.
Guardian binding must authorize **ego-link-001** for the named operator; bind
run `loclive-b<N>`, source/image hashes and observations in evidence. Verify
deployed server version/routes before the run; existing unverified VPS handlers
must not be assumed current. A deployment/configuration change is a separate
explicit item of this combined approval, with prior service/config backup and
rollback; provision only this test binding and do not notify non-test users.

Budget: station connect 20 s, SNTP 15 s, owner run 180 s, at most **4** GNSS
acquisitions (12 s each including cleanup), **6** actual HTTPS attempts (12 s
transaction deadline), **32** slot-write callbacks plus one boot-epoch
commit/readback. Main telemetry polls each 5 s, external read-only Guardian
queries at most 6. DNS/lwIP and hardware teardown are not hard-preempted by
the callback deadline; treat any late result as failed, and use an operator
**300 s total run stop**. At most **2 MiB** interface traffic including TLS,
DNS/SNTP and retries; stop at the cap. No retries/reboots beyond this one boot.
Final quiescence requires confirmed GNSS-off; otherwise stop physical operation
and record cleanup unconfirmed. Keep serial metadata below 256 KiB.

Use real outdoor/near-window receiver output if available; do not manufacture a
fix, missing HDOP, no-fix or error just to complete rows. Compare local sequence,
strict durable ACK and authorized Guardian source/age/uncertainty separately.
No microphone, camera, recording or external SOS notification in this stage.

**CALL stages.** After Location evidence is preserved, one wearable flash of
the final 15-second set and the exact named mTLS relay/Guardian/source interface
configuration in the [CALL request](CALL_CONVERGENCE_20260905.md). Two consenting
test operators, explicit audio-device names, volume retained at 55, no recordings.
First one Wi-Fi/Ethernet acoustic duplex setup: at most 500 frames/direction
(10 s PCM), 15 s media ceiling and 15 s setup. Optional second included setup
uses one named, source-bound and actually verified SIM/RNDIS route; interface
Up is insufficient. Cap each phase at 3 MiB, total 6 MiB. If no route proof is
available, skip the LTE phase and report it NOT_RUN. No more setup attempts.
RESULT is absent: stop host I/O, wait out the independent device 15 s limit and
observe PA-safe termination; remote cleanup remains unconfirmed until observed.

**Stop and recovery.** Bench placement, supervised independent endpoints, never
someone's safety lifeline. Stop on identity/hash/route mismatch, bad TLS/auth,
possible second modem/USB owner, reset/brownout/thermal issue, queue/write or
traffic budget exhaustion, one-way or persistent audio, privacy violation or
unconfirmed shutdown. Preserve redacted time/identity/counters, not audio or raw
location exports by default. Restore only the approved exact FW-007/UI-001
three-region sets; no erase-flash, NVS erase, eFuse, permission or pin changes.
Restore smoke is bounded to 30 s metadata per board. A failed restore or an
unmatched readback stops the experiment; it does not authorize another image.

Physical SOS and independently powered concurrent recovery follow successful
Location/CALL evidence in a later bounded packet. The current package does not
authorize them or mark their gate accepted.

---
document_status: authoritative
decision_updated: 2026-09-09
last_verified: 2026-09-16
verified_by: founder/codex
---

# Ego Link Current Status

## Current milestone

[ADR-0015](../architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md)
directs the current A line to one identified ESP32-S3-SIM7670G-4G board plus
the historically observed OV5640 Camera candidate, external QMI8658A, power source and
LTE/GNSS antennas. The milestone outcome is:

```text
asynchronous GNSS/LTE/IMU/raw collection
+ bounded persistent ordinary and JPEG backlogs
+ authorized Web one-shot still capture over real LTE
+ default-off local timed capture with outage/restart recovery
+ ordinary observations over actual Wi-Fi and LTE with a controlled transition
+ durable VPS storage, private Web preview and export
-> independently powered joint short run
-> FIELD-020 representative day
```

AMOLED, a board-to-board bridge, CALL and full physical SOS are not A-line
dependencies for this milestone. Camera is required here but is not a fourth
sellable-P0 Gate and is not a Location/SOS decision source.

## Actual hardware and running state

- `connectivity-node-001` was reidentified on CH343 `COM3` as ESP32-S3 rev
  v0.2, MAC `02:00:00:00:00:03`, with 16 MiB physical flash.
- The latest executed application is the app-only run016 image
  `0.1.0-camera-lte-trial-016`, run
  `camera-lte-trial-20260916-016`, 1,204,416 bytes, application SHA-256
  `A69B9AFB7292002A2D9745F5E90B261226329DA480791724CE91243C19B3DE9C`.
  It used the SIM7670G PPP route and retained the explicit manual-only
  `trial_unverified` Camera Gate; it is bounded engineering evidence, not a
  released Camera or field candidate.
- The current Camera-layout `ego_collection` partition at `0x500000`, length
  `0x100000`, was privately backed up and then exactly erased under the existing
  founder authorization. The immediate complete readback was all `0xFF`; later
  bounded boots resumed collection, so that post-clear result is not a claim
  that the partition remains empty. The app, NVS, media and outbox partitions
  were outside the erase.
- The proposed Camera media range `[0x600000,0xF00000)` was subsequently read
  in full into a private ignored backup. All 9,437,184 bytes were `0xFF`, and
  a subsequent `verify_flash` readback returned `verify OK`; the current
  observed occupancy permits reserving it for `ego_media` without displacing
  observed retained data.
- Run015 identified the OV5640 and completed exactly one fresh authenticated
  manual command -> real QVGA capture -> local save -> LTE metadata/content
  upload -> VPS durable storage -> private Guardian content-API download. The
  3,957-byte JPEG matched the device/server/API SHA-256 exactly. GNSS/no-fix,
  external IMU, LTE and available-power observations continued after capture.
- The bounded 300-second serial window observed PPP link/IP establishment and
  43 ordinary LTE HTTP-200 uploads without a panic, USB-enumeration failure or
  unexpected reboot. USB supplied power/serial/flash, so this is real LTE data
  evidence but not USB-free or independent-power evidence.
- After run015, the complete 1 MiB collection spool was privately backed up
  without erase. Its transient ROM-bootloader exit state was superseded by the
  run016 app-only write and independent matching `verify_flash`; no other
  partition was erased.
- Run016 then passed a 180-second LTE concurrency regression with one link-up,
  one PPP IPv4 event, 25 ordinary LTE HTTP-200 uploads and nine fresh healthy
  status snapshots. It recorded no stale/busy status, link-down, panic or photo
  event. No photo command was issued; run015 remains the Camera closure proof.
  Across the retained health samples, however, queued bytes rose from 502,511
  to 605,143 while persisted records rose from 3 to 66 and acknowledgements
  from 0 to 21. Errors/evictions stayed zero in that window, but the net growth
  keeps sustained throughput open.
- AMOLED is excluded from A-line runtime and acceptance; its retained UI/CALL
  image is unchanged. The `C-ME-0.1` C-line draft was not touched.
- Browser visual preview/export, timed/offline Camera capture, restart recovery
  of a pending photo, controlled Wi-Fi/LTE transition, independently powered
  operation and FIELD-020 remain `NOT_RUN`.

Exact active-image history and board capability boundaries are in
[ACTIVE_BUILD](ACTIVE_BUILD.md) and the
[board matrix](../hardware/BOARD_MATRIX.md).

The storage preflight is recorded in
[CAMERA-MEDIA-001](../hardware/CAMERA_MEDIA_RANGE_PREFLIGHT_20260909.md). It
involved no flash write and left the board in ROM bootloader at that checkpoint;
the later run006 app flash supersedes that transient device state.

The current joint-firmware run, hashes, exact partition clear and honest
failure/pass split are recorded in
[CAMERA-SHARED-I2C-TRIAL-20260909-001](../hardware/CAMERA_SHARED_I2C_TRIAL_20260909.md).
The later real-LTE manual Camera and private-API integrity slice is recorded in
[CAMERA-LTE-MANUAL-20260916-001](../hardware/CAMERA_LTE_MANUAL_CLOSURE_20260916.md).

## Verified evidence that may be inherited

- TCAM-001 on 2026-06-23 identified the attached OV5640 and captured three
  QVGA JPEGs in the isolated `camera_smoke` image. This does not prove current
  joint-firmware coexistence, persistent media storage or LTE upload.
- D2-006 identified the external ATK-NB018 V1.0 QMI8658A at I2C address
  `0x6A` on GPIO15/16 and captured 100 real non-mock six-axis samples.
- D2-008 later uploaded 26 real non-mock QMI8658A samples over a bounded Wi-Fi
  smoke. This does not prove the current joint image, LTE upload, calibration,
  mounting or continuous field operation.
- Existing GNSS/LTE and Location evidence remains scoped to its recorded
  images and runs. It cannot be combined arithmetically with the separate
  Camera smoke to claim the new milestone.

## Legacy Wi-Fi data cleanup

The founder-authorized cleanup completed across the identified device spool,
named local private reports and exact matching VPS rows. Every deleted item
was first hash-verified into the Git-ignored project backup at
`.local_backups/wifi_spool_20260909-120744/`.

Exactly 81 matching VPS collection records, 82 associated delivery attempts
and 81 associated raw frames were removed through a validated SQLite candidate
and atomic replacement. The live database passed integrity checks and the
service recovered healthy with zero remaining target rows. A sanitized remote
recovery point remains. This was a bounded deletion, not deletion of all
historical project data. Exact ranges, counts and hashes are recorded in
[PRIVACY_WIFI_SPOOL_PURGE_20260909](../hardware/PRIVACY_WIFI_SPOOL_PURGE_20260909.md).

## Current implementation state

- The accepted scope, privacy boundary and active task packet now describe the
  single-board Camera milestone; CALL-020, CALL-021 and SOS-010 are paused.
- The offline device source slice now contains bounded OV5640 one-shot capture,
  durable timer/command/capture journals, a separate fixed-slot JPEG store,
  metadata-before-media delivery, strict command/content ACK matching,
  retention cleanup, reboot recovery and fair ordinary/photo upload scheduling.
  The normal Camera profile defaults to the shared-I2C Gate `blocked`. The
  additive `sdkconfig.camera_shared_i2c_trial.defaults` profile is explicitly
  `trial_unverified` and permits only the existing Web manual command path,
  with at most one actual Camera/I2C attempt per boot. Busy admission does not
  consume the budget; any hardware attempt does. Blocked/trial images reject
  timed capture and never report the Camera source as verified/runtime-ready.
- Capture journal v2 now binds the capture-time Gate, driver profile, runtime
  config, firmware version and ELF digest. Legacy v1 capture state restores as
  `unknown_legacy`, never as the current image's identity. Final independent
  review also closed inherited-timer ACK paths that could otherwise misreport
  `applied` after a downgrade to blocked/trial.
- The deployed VPS/Web source slice now contains Guardian-bound capture sessions,
  one-shot/timer controls, immutable Camera metadata, private JPEG storage,
  integrity-verified content ACK, retention tombstones/retry, preview and
  export. Its ingest/storage path accepted the exact run005, run006, run006b
  and run015 Camera identities and bytes. Run015 additionally passed an
  authenticated private Guardian content-API byte-integrity check;
  browser-side visual preview/export remains unverified.
- Four earlier clean no-flash builds pass: default, legacy collector, Camera
  blocked and Camera trial. Both Camera profiles deliberately retain
  `NO_SIM=y` and LTE PPP disabled. The clean trial build has empty compiled
  Wi-Fi and bearer credentials, so its exact SHA is build evidence rather than
  a network-capable live image. The trial profile supplies the controlled
  mechanism first used by the ignored private run006 overlay. The later run015
  image enabled the real SIM7670G PPP path and completed one bounded manual
  Camera transfer over LTE, while the Camera Gate deliberately remained
  `trial_unverified` and timed capture stayed disabled.

## Product Gate status

| Gate | Current state | Why |
|---|---|---|
| `P0-LOC` | `NOT_RUN` | No accepted representative Location campaign on the current candidate/product boundary. |
| `P0-CALL` | `NOT_RUN` | CALL is paused for separate research; the earlier local audio loop is not a real LTE call. |
| `P0-SOS` | `NOT_RUN` | Full physical SOS and human closure are outside the current milestone and remain required later. |

The final sellable P0 remains Reliable Location + Ego Call + physical SOS;
all three Gates must eventually pass.

## Blocking facts before the next live run

1. Shared-I2C manual capture and one real-LTE delivery now have bounded success
   evidence, and run016 closes the immediate LTE status/PPP concurrency
   regression. The flashed profile is still the intentionally limited one-
   attempt-per-boot `trial_unverified` mode; any timed-capture promotion needs
   a separately bound candidate and explicit evidence.
2. Collection throughput is not field-ready. Run006 exposed old-backlog/`422`
   delay and bounded eviction; run015 still ended its last retained health
   sample with 230,047 queued bytes and two recorded errors. Run016 had zero
   errors/evictions in its retained window, but queued bytes nevertheless rose
   by 102,632 while only 21 of 63 newly persisted records were acknowledged.
   Close the sustained-rate/backlog cause before treating the dataset as
   representative or loss-free.
3. Verify the authorized browser preview/export for the exact run015 stored
   photo; the successful private API download is not browser rendering.
4. Prove timed enable/disable, outage capture and same-file reboot recovery.
5. Independent power, route transition, longer coexistence and FIELD-020 are
   still unrun. Camera hard-power cutoff and product power remain unverified.

## Immediate execution order

1. Use run016 as the bounded LTE concurrency baseline, close sustained
   upload/backlog errors without another broad spool clear, and bind the next
   Camera candidate without weakening privacy, TLS, modem ownership or exact
   ACK boundaries.
2. Verify browser decode/preview and export for the exact run015 photo identity.
3. Prove default-off timed enable/disable, full outage capture, restart and
   same-file recovery without catch-up recapture.
4. Exercise controlled Wi-Fi/LTE transition and retained-spool accounting,
   then run the independent-power short test and FIELD-020.

## Parallel and paused lanes

- HW-021 and COMPLIANCE-010 continue under their existing packets. The
  untracked `hardware/mechanical/C-ME-0.1/` founder draft is explicitly excluded
  from the current work and remains unchanged until the founder finishes it;
  this run does not treat draft contents as reviewed C-line conclusions.
  Measured Camera pin, standby, traffic, memory, file-size and timing facts will
  be handed to C line when that work resumes.
- CALL-020, CALL-021 and full SOS remain paused, not passed or deleted. AMOLED
  stays available as an independent indoor audio/UI bench resource.
- AI/visual inference remains outside the milestone. The data/replay interfaces
  remain, but no model may block the single-board collection closure.

## Validation record for this revision

- `python scripts/context_lint.py`: PASS after the 2026-09-16 run015/run016
  evidence update; the unfinished `C-ME-0.1` draft remained excluded.
- `scripts/verify.ps1`: PASS, 1,797 tests, 13 environment-guarded skips. A skip
  is not hardware evidence.
- Focused Camera/media/control/delivery/HTTPS suite: PASS, 84/84. The final
  Camera Gate/journal subset passes 16/16.
- Camera media-range hardware preflight: PASS for storage ownership only;
  `[0x600000,0xF00000)` read as 9,437,184 bytes of `0xFF`, SHA-256
  `BE1C8C26FAAE3AE3606606C9641F017A873F52A7833C9CF65142EF0E2405CE8A`,
  and the subsequent `verify_flash` readback returned `verify OK`. No write
  occurred.
- ESP-IDF 5.4.2 clean-commit no-flash builds at `ef3c06f6a`: default
  `896,240 B`, SHA-256
  `2EDC9153E618329378645D03FB8D808E68936179403FD7C9D2F88AFEA434A9AC`;
  legacy collector `991,568 B`, SHA-256
  `CF265EA61F3F275216F592F865E6810AC85B5A30B0415CA1F071EF60626E9317`;
  Camera blocked `1,033,680 B`, SHA-256
  `E00474A5610011527DB6CBD62BF62E074C20D831FBB848B09B10BA0275572AA1`;
  Camera trial `1,101,648 B`, SHA-256
  `320B7D51726B91ABAE6CD83B797038DC77232AE72D3094308825708223E02333`.
  The Camera images use a 3 MiB app partition with respectively `0x203A30`
  (67%) and `0x1F30B0` (65%) free. All embed
  `v0.1.0-123-gef3c06f6a` without `-dirty`; none of those four exact checkpoint
  binaries was flashed.
- Backend and firmware source reviews report no remaining known merge blocker;
  the final firmware review specifically closed provenance drift, nonverified
  timer ACK truth and trial-status overclaim paths.
- Commit `80c5e86fd` was built with the ignored run006 overlay and flashed
  app-only on COM3. Wi-Fi manual capture/recovery and exact VPS storage pass as
  described in the linked evidence. Browser decode, real LTE transfer,
  timed-outage/reboot capture, independent power and FIELD-020 remain
  `NOT_RUN`.
- Run015 flashed the app-only
  `0.1.0-camera-lte-trial-015` image and passed one real-SIM LTE PPP manual
  Camera -> VPS -> authenticated private-API byte-integrity slice. Application
  SHA-256 is
  `281C060625DC5F99EA37C7CAD01C419B65CF7D005ACC98334FFDB6090ED58B26`;
  the retained raw log SHA-256 is
  `418FC074D5B32EC86838B2F315295A1AA8536D60A3B3D6A485069FFDD630FD5C`.
  Browser rendering, timer/outage/restart, route transition, independent power,
  FIELD-020 and all three P0 Gates remain `NOT_RUN`.
- Run016 app-only write and independent verify matched application SHA-256
  `A69B9AFB7292002A2D9745F5E90B261226329DA480791724CE91243C19B3DE9C`.
  Its 180-second real-LTE ordinary-upload regression recorded 25 HTTP-200
  uploads, nine fresh healthy status snapshots and zero stale/busy/link-down/
  panic/photo events. The private log SHA-256 is
  `45EE643CFA281A9AD1B9679A242B363679021AE79361286779101AB6D3861DA5`.
  No Camera command was issued and no remaining milestone or P0 Gate advanced.

The prior 3,000-plus-line chronological status was preserved byte-for-byte as
a non-authoritative source snapshot under
[`docs/archive/status/20260909/`](../archive/status/20260909/README.md).

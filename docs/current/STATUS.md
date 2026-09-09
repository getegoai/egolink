---
document_status: authoritative
decision_updated: 2026-09-09
last_verified: 2026-09-09
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
- The board now contains the app-only Camera trial image built from commit
  `80c5e86fd8b39462128b831b9a06db7edbf2841a`, flashed at `0x200000`.
  Its application SHA-256 is
  `EE2FA5A3D2B65186B3A80597C1C574CAA66CBEB66DA5A5EE2125B3086C299D0D`.
  It is a Wi-Fi/no-SIM `UNVERIFIED_TRIAL` image, not an LTE candidate.
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
- The joint firmware identified the OV5640 and completed real QVGA captures,
  cross-reboot metadata/JPEG recovery and a fresh exact command/content ACK to
  the VPS while GNSS, external IMU and Wi-Fi collection continued. The clean
  run006b JPEG was 2,707 bytes and matched the VPS SHA-256 exactly.
- AMOLED is excluded from A-line runtime and acceptance; its retained UI/CALL
  image is unchanged. The `C-ME-0.1` C-line draft was not touched.
- No SIM traffic, real-LTE Camera transfer, timed/offline Camera run,
  independently powered run or FIELD-020 run has occurred. Private Web visual
  preview/export is not yet accepted.

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
  export. Its ingest/storage path accepted the exact run005, run006 and run006b
  Camera identities and bytes. Browser-side visual preview/export remains
  unverified.
- Four earlier clean no-flash builds pass: default, legacy collector, Camera
  blocked and Camera trial. Both Camera profiles deliberately retain
  `NO_SIM=y` and LTE PPP disabled. The clean trial build has empty compiled
  Wi-Fi and bearer credentials, so its exact SHA is build evidence rather than
  a network-capable live image. The trial profile supplies the controlled
  mechanism used by the ignored private run006 overlay. The resulting combined
  image was flashed and exercised, but remains `UNVERIFIED_TRIAL` and is not
  LTE-ready.

## Product Gate status

| Gate | Current state | Why |
|---|---|---|
| `P0-LOC` | `NOT_RUN` | No accepted representative Location campaign on the current candidate/product boundary. |
| `P0-CALL` | `NOT_RUN` | CALL is paused for separate research; the earlier local audio loop is not a real LTE call. |
| `P0-SOS` | `NOT_RUN` | Full physical SOS and human closure are outside the current milestone and remain required later. |

The final sellable P0 remains Reliable Location + Ego Call + physical SOS;
all three Gates must eventually pass.

## Blocking facts before the next live run

1. The shared-I2C manual trial now has real joint-firmware success evidence,
   but the current image is still the intentionally limited one-attempt-per-boot
   `UNVERIFIED_TRIAL`. A separate named candidate must consume the evidence and
   make the promotion explicit before timed capture is enabled.
2. Collection throughput is not field-ready. The first run006 command exposed
   old-backlog/`422` delay and command expiry; even after the exact spool clear,
   a 300-second boot reached about 722 KiB queued with 25 bounded evictions.
   Close the rejection/throughput cause and tune the experimental rate before
   treating the dataset as representative or loss-free.
3. Build and bind the actual SIM/LTE-enabled candidate. The current image has
   `NO_SIM=y`, LTE PPP disabled and only Wi-Fi evidence; it cannot satisfy the
   real-LTE milestone by reinterpretation.
4. Verify the private Web preview/export for the exact same stored photo, then
   prove timed enable/disable, outage capture and same-file reboot recovery.
5. Independent power, route transition, longer coexistence and FIELD-020 are
   still unrun. Camera hard-power cutoff and product power remain unverified.

## Immediate execution order

1. Diagnose and fix the ordinary-record `422`/upload-rate bottleneck using the
   retained run006 evidence; rerun one bounded Wi-Fi window without relying on
   another broad spool clear.
2. Convert the successful shared-I2C evidence into a separately named Camera
   candidate, keeping the privacy, TLS, ownership and exact-ACK boundaries.
3. Enable and prove the actual SIM/LTE route, then repeat one fresh command ->
   capture -> durable metadata/JPEG -> VPS exact verification -> private Web
   preview with GNSS/IMU/ordinary observations still progressing.
4. Prove default-off timed enable/disable, full outage capture, restart and
   same-file recovery without catch-up recapture.
5. Exercise controlled Wi-Fi/LTE transition and retained-spool accounting,
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

- `python scripts/context_lint.py`: PASS after the 2026-09-09 run006/run006b
  evidence update; the unfinished `C-ME-0.1` draft remained excluded.
- `scripts/verify.ps1`: PASS, 1,784 tests, 13 environment-guarded skips. A skip
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

The prior 3,000-plus-line chronological status was preserved byte-for-byte as
a non-authoritative source snapshot under
[`docs/archive/status/20260909/`](../archive/status/20260909/README.md).

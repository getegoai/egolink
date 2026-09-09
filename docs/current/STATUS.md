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
- The board is intentionally in the ESP32-S3 ROM bootloader after the bounded
  legacy collection-spool cleanup. The retained 2026-09-06 collector
  application and NVS were not erased, but that application is not running.
- The old `ego_collection` partition was backed up, selectively erased and
  completely read back as empty. The application, NVS and `ego_outbox` were
  outside that operation.
- The proposed Camera media range `[0x600000,0xF00000)` was subsequently read
  in full into a private ignored backup. All 9,437,184 bytes were `0xFF`, and
  a subsequent `verify_flash` readback returned `verify OK`; the current
  observed occupancy permits reserving it for `ego_media` without displacing
  observed retained data.
- AMOLED is excluded from A-line runtime and acceptance; its retained UI/CALL
  image is unchanged. Any separate USB attachment is not used by this runtime.
- No combined Location/Camera candidate has been flashed. No new SIM traffic,
  live Camera capture, independently powered run or FIELD-020 run has occurred.

Exact active-image history and board capability boundaries are in
[ACTIVE_BUILD](ACTIVE_BUILD.md) and the
[board matrix](../hardware/BOARD_MATRIX.md).

The storage preflight is recorded in
[CAMERA-MEDIA-001](../hardware/CAMERA_MEDIA_RANGE_PREFLIGHT_20260909.md). It
involved no flash write and leaves the board in ROM bootloader.

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
- The local VPS/Web source slice now contains Guardian-bound capture sessions,
  one-shot/timer controls, immutable Camera metadata, private JPEG storage,
  integrity-verified content ACK, retention tombstones/retry, preview and
  export. Its focused and cross-module tests pass; it has not been deployed.
- Four clean no-flash builds now pass: default, legacy collector, Camera
  blocked and Camera trial. Both Camera profiles deliberately retain
  `NO_SIM=y` and LTE PPP disabled. The clean trial build has empty compiled
  Wi-Fi and bearer credentials, so its exact SHA is build evidence rather than
  a network-capable live image. The trial profile supplies the controlled
  mechanism for obtaining coexistence evidence after a private overlay and
  rebuild; it is not verified or LTE-ready. No combined image has been flashed
  or run.

## Product Gate status

| Gate | Current state | Why |
|---|---|---|
| `P0-LOC` | `NOT_RUN` | No accepted representative Location campaign on the current candidate/product boundary. |
| `P0-CALL` | `NOT_RUN` | CALL is paused for separate research; the earlier local audio loop is not a real LTE call. |
| `P0-SOS` | `NOT_RUN` | Full physical SOS and human closure are outside the current milestone and remain required later. |

The final sellable P0 remains Reliable Location + Ego Call + physical SOS;
all three Gates must eventually pass.

## Blocking facts before the next live run

1. Reconfirm the physical OV5640, cable/orientation, external QMI8658A and
   MAX17048 wiring and 16 MiB flash before applying power. Keep the TF card
   physically removed and its driver disabled because Camera PCLK and TF
   card-detect share GPIO46; do not attach external GPIO JTAG on GPIO39-42.
   The static candidate uses I2C0 GPIO15/16 at 100 kHz with OV5640 `0x3C`,
   MAX17048 `0x36` and QMI8658A `0x6A`; the distinct addresses do not prove
   electrical or runtime coexistence.
2. Establish one named permitted Camera session and operator scope, with
   Guardian binding, authorized viewers, retention/deletion deadline and
   `training_allowed=false`. The initial trial must explicitly exclude timer,
   SIM and audio.
3. Within that scope, create one ignored private no-SIM trial overlay carrying
   the actual Wi-Fi/authentication and run/session identity, rebuild and bind a
   new exact SHA. The clean `320B7D...2333` build has empty live credentials and
   is not the image to flash.
4. Deploy the reviewed VPS/Web slice and flash only that exact named rebuild.
   Use the existing Web command for one bounded QVGA attempt and record
   Camera/IMU/power continuity, internal/DMA heap, largest DMA block, task-stack
   watermarks, UART errors, resets, brownouts and watchdog outcomes.
5. Review that named evidence before selecting a separate `verified` image.
   Trial success never changes the Gate automatically.
6. After verification, create one ignored, named live configuration that
   enables the actual SIM/LTE path and only the verified Camera/I2C choices;
   rebuild and bind its exact binary hash to the experiment scope.

## Immediate execution order

1. Complete the powered-off physical check and define the bounded
   operator/privacy scope for a permitted private scene.
2. Generate the ignored private no-SIM trial overlay, rebuild it and bind the
   resulting exact SHA; then deploy the reviewed VPS/Web slice and flash only
   that named COM3 image.
3. Use the existing Web command for one manual QVGA attempt while measuring
   Camera/QMI8658A/MAX17048 coexistence and runtime resource continuity.
4. If and only if the evidence passes review, build a separate verified
   Camera image and the ignored SIM/LTE-enabled run configuration without
   weakening TLS, route ownership, retention or Camera gates.
5. Then prove Web request -> device receive -> real JPEG -> persistent local
   save -> real LTE upload -> VPS verification -> private Web preview, while
   confirming GNSS/LTE/IMU and ordinary observations continue.
6. Prove default-off timed enable/disable, full outage capture, reboot and
   same-file recovery without catch-up recapture.
7. Exercise the controlled Wi-Fi/LTE route transition with exact ACK, retry,
   duplicate/loss and retained-spool accounting.
8. Run the independently powered coexistence short test, then FIELD-020.

## Parallel and paused lanes

- HW-021 and COMPLIANCE-010 continue. Camera pin/interface ownership, standby
  or power control, storage/traffic/RAM budget, lens/FOV/orientation,
  optical-window and sealing facts must flow into C line as measured inputs.
  Current C-line review keeps the product Camera/module/lens/FPC and image-media
  part unresolved: the engineering layout has no Camera hard-power control,
  zero count margin at five-minute capture over 24 hours, low-slot wear risk,
  a full media scan at boot, no A/B OTA layout and no image encryption.
- CALL-020, CALL-021 and full SOS remain paused, not passed or deleted. AMOLED
  stays available as an independent indoor audio/UI bench resource.
- AI/visual inference remains outside the milestone. The data/replay interfaces
  remain, but no model may block the single-board collection closure.

## Validation record for this revision

- `python scripts/context_lint.py`: PASS after the 2026-09-09 trial and C-line
  Camera-input reconciliation.
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
  `v0.1.0-123-gef3c06f6a` without `-dirty`; no binary was flashed.
- Backend and firmware source reviews report no remaining known merge blocker;
  the final firmware review specifically closed provenance drift, nonverified
  timer ACK truth and trial-status overclaim paths. Deployment, flashing,
  browser decode, real Camera capture,
  real LTE transfer, outage/reboot recovery, independent power and FIELD-020
  remain `NOT_RUN`.

The prior 3,000-plus-line chronological status was preserved byte-for-byte as
a non-authoritative source snapshot under
[`docs/archive/status/20260909/`](../archive/status/20260909/README.md).

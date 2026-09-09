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
+ ordinary observations over actual Wi-Fi and LTE with a controlled transition
+ authorized Web one-shot still capture over real LTE
+ default-off local timed capture with outage/restart recovery
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
- AMOLED is excluded from A-line runtime and acceptance; its retained UI/CALL
  image is unchanged. Any separate USB attachment is not used by this runtime.
- No combined Location/Camera candidate has been flashed. No new SIM traffic,
  live Camera capture, independently powered run or FIELD-020 run has occurred.

Exact active-image history and board capability boundaries are in
[ACTIVE_BUILD](ACTIVE_BUILD.md) and the
[board matrix](../hardware/BOARD_MATRIX.md).

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
  Independent source review found no remaining merge blocker, and default,
  legacy-collector and Camera-collector no-flash builds pass.
- The local VPS/Web source slice now contains Guardian-bound capture sessions,
  one-shot/timer controls, immutable Camera metadata, private JPEG storage,
  integrity-verified content ACK, retention tombstones/retry, preview and
  export. Its focused and cross-module tests pass; it has not been deployed.
- This is offline source/build evidence only. The Camera build deliberately
  retains `NO_SIM=y`, LTE PPP disabled and the shared-I2C verified Gate closed,
  so it cannot be used to claim a real Camera/LTE closure. No combined image
  has been flashed or run.

## Product Gate status

| Gate | Current state | Why |
|---|---|---|
| `P0-LOC` | `NOT_RUN` | No accepted representative Location campaign on the current candidate/product boundary. |
| `P0-CALL` | `NOT_RUN` | CALL is paused for separate research; the earlier local audio loop is not a real LTE call. |
| `P0-SOS` | `NOT_RUN` | Full physical SOS and human closure are outside the current milestone and remain required later. |

The final sellable P0 remains Reliable Location + Ego Call + physical SOS;
all three Gates must eventually pass.

## Blocking facts before the next live run

1. Before selecting the new partition table, privately read and back up
   `0x600000..0xF00000`, then explicitly confirm that this exact range may be
   dedicated to `ego_media`; the reviewed runtime scrubs every non-valid media
   slot in that range and must not encounter unowned data.
2. Reconfirm the physical OV5640, cable/orientation, external QMI8658A and
   MAX17048 wiring, 16 MiB flash, SIM, LTE/GNSS antennas and independent power.
   Prove shared-I2C coexistence before enabling its fail-closed build Gate.
3. Create one ignored, named live configuration that enables the actual SIM/LTE
   path and only the verified Camera/I2C choices; rebuild and bind its exact
   binary hash to the experiment scope.
4. Establish one named permitted Camera session with Guardian binding,
   retention deadline, authorized viewers, deletion path and
   `training_allowed=false`.
5. Obtain a bounded operator scope for VPS deployment, exact COM3 candidate
   flash, SIM data and the permitted real-scene one-shot/recovery experiment.

## Immediate execution order

1. Complete the private media-range pre-read/backup and physical shared-I2C
   coexistence check; keep the board in ROM bootloader until both are resolved.
2. Produce the ignored SIM/LTE-enabled run configuration and exact candidate
   build without weakening TLS, route ownership, retention or Camera gates.
3. Deploy the reviewed VPS/Web candidate and flash the exact combined firmware
   only under the bounded operator/privacy scope.
4. Prove ordinary observations from that same candidate over actual Wi-Fi and
   actual LTE, then exercise a controlled route transition with exact ACK,
   retry, duplicate/loss and retained-spool accounting.
5. Prove Web request -> device receive -> real JPEG -> persistent local save ->
   real LTE upload -> VPS verification -> private Web preview.
6. Prove default-off timed enable/disable, full outage capture, reboot and
   same-file recovery without catch-up recapture.
7. Run the independently powered coexistence short test, then FIELD-020.

## Parallel and paused lanes

- HW-021 and COMPLIANCE-010 continue. Camera pin/interface ownership, standby
  or power control, storage/traffic/RAM budget, lens/FOV/orientation,
  optical-window and sealing facts must flow into C line as measured inputs.
- CALL-020, CALL-021 and full SOS remain paused, not passed or deleted. AMOLED
  stays available as an independent indoor audio/UI bench resource.
- AI/visual inference remains outside the milestone. The data/replay interfaces
  remain, but no model may block the single-board collection closure.

## Validation record for this revision

- `python scripts/context_lint.py`: PASS after the 2026-09-09 scope and cleanup
  reconciliation.
- `scripts/verify.ps1`: PASS, 1,776 tests, 13 environment-guarded skips. A skip
  is not hardware evidence.
- Focused Camera/media/control/delivery/HTTPS tests: PASS, 26/26.
- ESP-IDF 5.4.2 no-flash builds: default `896,240 B`, SHA-256
  `D59B8337FC6280FB17D848D415505D5AEE9835164EEFE4936C008548FC0D4A36`;
  legacy collector `991,504 B`, SHA-256
  `F36C567D6C211BC84D41548407068A6E813F71EE3A9B371980541A2DF3299B91`;
  Camera collector `1,029,616 B`, SHA-256
  `E3640BE2D82C56DF79EE8F32E3CE62BC2CA27ACD122EE2756C9BF1F11EF5E016`.
  The Camera app uses a 3 MiB partition with `0x204A10` bytes (67%) free.
- Backend source review and firmware source review both report zero remaining
  merge blockers. Deployment, flashing, browser decode, real Camera capture,
  real LTE transfer, outage/reboot recovery, independent power and FIELD-020
  remain `NOT_RUN`.

The prior 3,000-plus-line chronological status was preserved byte-for-byte as
a non-authoritative source snapshot under
[`docs/archive/status/20260909/`](../archive/status/20260909/README.md).

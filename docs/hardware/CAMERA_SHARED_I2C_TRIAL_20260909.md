---
document_status: hardware_evidence
evidence_date: 2026-09-09
hardware_observed: true
write_performed: true
network_route: wifi_no_sim
verified_by: founder/codex
---

# CAMERA-SHARED-I2C-TRIAL-20260909-001 — joint-firmware Camera recovery and manual capture

## Outcome

`PASS` for the bounded Wi-Fi/no-SIM manual-Camera bench slice. The current
collector image identified the attached OV5640, captured real QVGA JPEGs while
GNSS, external IMU and Wi-Fi collection continued, durably recovered an older
photo across reboot, and delivered a fresh photo to the VPS with exact command
and content acknowledgement. The VPS-stored bytes matched the device-reported
byte count and SHA-256.

This result does **not** pass the current real-LTE Camera milestone, timed or
fully offline capture, independent-power carry test, FIELD-020, Web visual
preview/export, product Camera selection, or any P0 product Gate. The flashed
image remains the explicit shared-I2C `UNVERIFIED_TRIAL` profile; this evidence
supports a promotion review but does not silently relabel that image as
`VERIFIED`.

## Bound image and hardware

- Source commit:
  `80c5e86fd8b39462128b831b9a06db7edbf2841a`
  (`fix(firmware): prioritize recoverable camera delivery [A]`).
- Firmware identity: `0.1.0-camera-trial-80c5e86-006`; test run identity:
  `camera-trial-20260909-006`.
- Application: 1,104,464 bytes, SHA-256
  `EE2FA5A3D2B65186B3A80597C1C574CAA66CBEB66DA5A5EE2125B3086C299D0D`.
- ELF SHA-256:
  `6686F8E8BC1CECC19AEE4F89F01F2161DF3108847357BD9E64515DE9B3DD42EA`.
- Flash operation: application-only write at `0x200000` on the identified
  ESP32-S3 connectivity board through CH343 `COM3`. The partition table,
  bootloader, NVS and media partition were not rewritten by that app flash.
- Runtime profile: Camera enabled in `UNVERIFIED_TRIAL`, one hardware attempt
  per boot, 300-second run bound, timed capture disabled, `NO_SIM=y`, LTE PPP
  disabled. The observed transport was Wi-Fi and must not be described as LTE.
- Camera observed by the joint collector: OV5640; successful frames were JPEG,
  320 x 240. The external QMI8658A and GNSS collection paths also produced
  observations during the bounded run series.

AMOLED and the CALL line were not connected to, flashed by, or used in this
experiment. The untracked `hardware/mechanical/C-ME-0.1/` draft was not touched.

## Recovery and capture sequence

### Existing run005 photo recovery

The first run after the uploader scheduling fix recovered the already durable
run005 Camera metadata and JPEG rather than recapturing it:

- command: `run005-capture-20260909T143147Z`;
- session: `run005-photo-20260909T143147Z`;
- photo: `manual-979c4ec174274dfe5abfa981e85ba19e-n0`;
- JPEG: 5,448 bytes;
- SHA-256:
  `19ca7a584d4d44bd1f874fce36233ae5d194a1011a2778a9fada2bf41224c369`.

The server metadata and stored JPEG matched those exact values. This is
cross-reboot delivery evidence for an existing file, not evidence of a new
capture or LTE transport.

### First run006 command and useful failure

The fresh command `run006-capture-20260909T153836Z` in session
`run006-photo-20260909T153836Z` reached the device and produced photo
`manual-1d32f1a7aadfd35a6a6a31fcb5b99f92-n0`, 2,665 bytes, SHA-256
`dd7a33a3e83b5a2899734494a4c5687ad4dc5bfe21efc7cd6aa38594be7cf145`.

The inherited ordinary backlog and server `422` responses delayed Camera
metadata progress. The two-minute command expired before an exact command ACK
could close, so this command is not counted as a command-ACK pass. Subsequent
recovery nevertheless stored the same JPEG bytes on the VPS with the exact
size and hash. The failure demonstrates that capture, metadata delivery and
command acknowledgement are separate states; a stored image does not rewrite
an expired command as successful.

### Authorized collection-spool backup and clear

Before the exact clear, the entire current Camera-layout `ego_collection`
partition was read to the private evidence directory:

- range: `0x500000`, length `0x100000` (1,048,576 bytes);
- file:
  `reports/board_validation/CAMERA-SHARED-I2C-TRIAL-20260909-001/private/ego_collection_run006_preclear.bin`;
- SHA-256:
  `ABEC92241968E7B5C23677FDE0A5A0F4B2DD8FB9DBDF083B2A218B3FCBDEEFB1`.

Only `erase_region 0x500000 0x100000` was used. The complete post-clear
readback
`reports/board_validation/CAMERA-SHARED-I2C-TRIAL-20260909-001/private/ego_collection_run006_postclear.bin`
is 1,048,576 bytes of
`0xFF`, has zero non-`0xFF` bytes, and SHA-256
`F5FB04AA5B882706B9309E885F19477261336EF76A150C3B4D3489DFAC3953EC`.
The app at `0x200000`, NVS, `ego_media` and `ego_outbox` were outside this
erase. The pre-clear copy makes the cleared collection bytes recoverable; no
raw image was added to Git.

### Clean run006b command closure

After that bounded clear, command `run006b-capture-20260909T154922Z` in session
`run006b-photo-20260909T154922Z` completed with an exact HTTP 200 `ok` command
ACK (`matched=1`, `duplicate=0`). The OV5640 produced:

- photo: `manual-990f9579033d6372637b0da53c99f0dd-n0`;
- dimensions and format: 320 x 240 JPEG;
- size: 2,707 bytes;
- SHA-256:
  `f556e97da859083ae6a67f64fee3f1dc05d1cea29928611d52b1a45fa9314c2e`.

The server verified and durably stored content with the same photo ID, size
and SHA-256 before returning the exact content ACK. The device then released
that delivered media slot. The transport for command polling, metadata and
JPEG upload was Wi-Fi; no SIM or LTE bearer was active.

## Coexistence and bounded-runtime observations

- The raw serial windows contain continuing GNSS/no-fix work, external-IMU
  observations and Wi-Fi collection around the Camera attempts. Camera capture
  and upload did not stop those tasks for the remainder of the observed
  windows.
- Four deliberately started boots were observed. None of their bounded serial
  windows contained a Guru Meditation, panic, brownout, watchdog, stack
  overflow or second unexpected boot. Boots 87 through 89 reached the normal
  IMU/uploader/modem stop sequence at the 300-second firmware bound. The final
  boot-90 content-recovery log ended after the required JPEG result and does
  not by itself prove that boot's later terminal stop record.
- The persistent queue remained bounded, but it did not demonstrate field
  throughput. After the collection clear, boot 89 reached approximately
  722 KiB queued and recorded 25 bounded evictions by its final health sample.
  Therefore this trial proves explicit bounded-loss behavior, not loss-free
  day-scale collection. Sampling/upload throughput and the remaining `422` or
  timeout causes must be closed before FIELD-020.
- Camera deinitialization is still software release/standby only; this board
  profile has no proven Camera hard-power cutoff or product power result.

## Evidence handling

Private raw serial logs, flash readbacks and test JPEGs are retained only under
the Git-ignored directory:

`reports/board_validation/CAMERA-SHARED-I2C-TRIAL-20260909-001/private/`

The relevant raw logs are `run006_serial.raw.log`,
`run006_fresh_serial.raw.log`, `run006_postclear_recovery_serial.raw.log` and
`run006b_content_recovery_serial.raw.log`. They are path references only: this
document does not embed private scene bytes, credentials, raw Wi-Fi identifiers
or precise coordinates. The capture session remained bounded and
`training_allowed=false`.

## Remaining milestone work

1. Diagnose the ordinary-observation `422`/throughput backlog and select a
   collection rate that can complete a representative run without silent loss.
2. Build and bind the separate actual-SIM/LTE candidate, then repeat one fresh
   Web command -> device capture -> exact metadata/JPEG storage path over LTE.
3. Verify private Web preview/export against that same photo identity.
4. Enable the default-off timed profile only after the shared-I2C promotion
   review, then prove stop/expiry, outage capture, reboot and same-file
   recovery without catch-up recapture.
5. Run the independent-power single-board coexistence short test and only then
   dispatch FIELD-020.

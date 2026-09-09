---
document_status: hardware_evidence
evidence_date: 2026-09-09
evidence_time_local: 2026-09-09T16:31:13+08:00
hardware_observed: true
write_performed: false
verified_by: codex
---

# CAMERA-MEDIA-001 — Camera media-range preflight

## Outcome

`PASS` for the storage-ownership preflight only. The identified 16 MiB
connectivity board's future `ego_media` range, `[0x600000,0xF00000)`, was read
in full, privately backed up, characterized as completely erased, and then
matched by a subsequent `verify_flash` readback. This passes the current
observed-occupancy check for the proposed Camera partition; it does not prove
that the range can never contain data under a different image or partition map.

It does not authorize or record a partition-table/application flash, and it
does not advance Camera, LTE, Location, FIELD-020 or any P0 product Gate.

## Bound hardware and operation

- Board: `connectivity-node-001`, ESP32-S3 rev v0.2, MAC
  `02:00:00:00:00:03`.
- Observed USB path: CH343 `COM3`, serial `5B91047400`.
- Flash: manufacturer `0x85`, device `0x2018`, detected size 16 MiB, quad,
  3.3 V.
- Tool: esptool.py v4.12.0 at 921600 baud.
- Read: address `0x600000`, length `0x900000` (9,437,184 bytes).
- Verification: a subsequent `verify_flash` compared the same 9 MiB board
  range with the saved bytes and returned `verify OK (digest matched)`.
- Firmware executed: none; the ESP32-S3 ROM bootloader alone serviced the
  read/verify operation, and the retained collector application did not run.
- Device exit state: ROM bootloader (`--after no_reset`).

Only identity/read/verify operations were used. No erase, flash write, reset
into the retained collector, SIM traffic, sensor capture or network operation
occurred.

## Private backup and content result

- Git-ignored directory:
  `.local_backups/media_range_preflight_20260909-163113/`
- Git-ignored manifest:
  `.local_backups/media_range_preflight_20260909-163113/manifest.json`
- File: `flash_0x600000_0x900000.bin`
- Bytes: 9,437,184
- SHA-256:
  `BE1C8C26FAAE3AE3606606C9641F017A873F52A7833C9CF65142EF0E2405CE8A`
- Byte characterization: all 9,437,184 bytes are `0xFF`; non-`0xFF` count is
  zero.

The reviewed Camera partition profile may therefore reserve this exact range
for `ego_media` without displacing observed retained data. The runtime's
initial slot scrub remains bounded to the partition and may run only after a
separately authorized candidate flash. The next hardware blocker is physical
OV5640/QMI8658A/MAX17048 shared-I2C coexistence, not media-range ownership.

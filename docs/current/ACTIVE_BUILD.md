---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-09-21
reviewed_at: 2026-09-22
verified_by: codex
---

# Active Build

## Last reported connectivity image

This is a documentation reconciliation of the 2026-09-21 report, not a new probe
or flash. Source changes from ALIGN-STATE-010 do not change the running image.

| Identity | Recorded value |
|---|---|
| Board | `connectivity-node-001`, Waveshare ESP32-S3-SIM7670G-4G |
| Connection | CH343 ESP32 console `COM3`; actual LTE bearer is SIM7670G USB PPP |
| MCU / physical flash | ESP32-S3 rev v0.2 / 16 MiB; PCB revision remains unknown |
| Boot / report date | 188 / 2026-09-21 |
| Firmware version | `0.1.0-sensor-policy-continuous-021` |
| Run string | `field-sensor-policy-20260919-021` |
| App location / size | app-only at `0x200000` / 1,228,080 bytes |
| App SHA-256 | `f9869caeab2b4fce9cae2d553d9d0142dbb63e37bc386237a0524325712c6d3f` |
| ELF SHA-256 | `420d7607e026cc37d4cc03e9781ecb95abcb19d5d09cd3858ae3a0979efe9aa5` |
| Source/config binding | Complete immutable build/config manifest and raw Boot188 log path still need indexing; do not infer exact flashed commit from the documentation commit |
| Reported scope | QMI8658/MAX17048 probes, ego-state initialization, exclusive AT owner, LTE PPP/upload and one ego-state stored projection |
| Limits | No new contract/freshness repair deployed; AT configure result not established by its unconditional success log; no call/audio/SOS/representative-field acceptance |

The prior heading called this run022 while its firmware and run strings remained
run021. Boot + full image hashes distinguish it from Boot183 and Boot171; do not
rename historical telemetry or combine the three images. The source evidence is
[the preserved original ACTIVE_BUILD](../archive/alignment/20260922/docs__current__ACTIVE_BUILD.md.source)
and [original STATUS](../archive/alignment/20260922/docs__current__STATUS.md.source).
Their embedded old "current" statements are historical only.

## Prior candidates and reusable evidence

| Candidate | Identity / evidence | Scope |
|---|---|---|
| Boot183 run021 | App `dac596233d1da4d4607cc93015780c4046d1257d94bcfcdb49c22f8043903110`, ELF `c374cee46036b42dbd5495a5e46160f696776ee24dca07075204b2d75422490c` | Prior image; not Boot188 |
| Boot171 run021, 9/19 | App `79c0dae8689ffd91601303735384a3e7ab03a4f83b633af04eba7779c1a0bc54`; real sensor-policy/20Hz IMU/LTE bench report | Policy execution evidence, not calibrated accuracy or energy benefit |
| Boot142 run019, 9/18 | App `a67601c4001490eddf983e6f62ff00334dc0c9c22874b5229ff332f08d7f7481`; battery-powered timed capture/STOP in [P0-CONVERGENCE](../tasks/active/P0-CONVERGENCE-20260905.md) | Short functional timer evidence; not a representative carry day |
| run018, 9/17 | 9 MiB media mounted; manual photo persisted/uploaded and ordinary backlog drained; original chronology retained above | Candidate-specific coexistence |
| run017, 9/16 | App `07cf1ef3fea13548fb9b7f5ef8f5c965fe6b6bf53ebd6ae9369f2e8cf0223529`; 248/248 ordinary uploads in 600s | USB-powered empty-spool throughput |
| run015, 9/16 | [Named LTE Camera evidence](../hardware/CAMERA_LTE_MANUAL_CLOSURE_20260916.md) | Manual JPEG + private API matching hash; subsequent 9/17 browser preview documented |
| run006 / isolated TCAM | [Shared-I2C report](../hardware/CAMERA_SHARED_I2C_TRIAL_20260909.md), [TCAM-001](../hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md) | Historical Wi-Fi and isolated sensor evidence only |

## Current setup and next candidate

- One connectivity board plus OV5640, external QMI8658A, battery/power and
  LTE/GNSS antennas. AMOLED/PC forwarding is not an A-line runtime dependency.
- Retain current verified bus/pin constraints: shared I2C GPIO15/16; TF card
  absent/driver disabled because Camera PCLK and TF detect share GPIO46;
  GPIO39-42 not used for external JTAG. This document does not change wiring.
- Collection partition: `[0x500000,0x600000)`; Camera media:
  `[0x600000,0xF00000)`. Prior backups/clears are historical, not permission to
  erase or a statement that these ranges remain empty.
- Gemini binds the next exact source/config/board/boot/connection/evidence
  manifest and approved recovery image before a new experiment. FW-007 is a
  historical rollback reference, not an instruction to restore it over the
  current media layout without a reviewed migration.
- The Codex state-truth branch is offline source until its named binary is
  built, reviewed and explicitly selected for a later run. Do not mix its
  behavior with Boot188 evidence or change `last_verified` on source edits.
- Exact current VPS/Web deployed commit and artifact digest are unverified in
  this reconciliation; 9/21 deployment was reported, not re-inspected here.

## Offline source build (not flashed)

Offline source validation on 2026-09-22: firmware source matching `3a0728058`
built with the camera-blocked/no-SIM collection defaults (LTE PPP disabled).
App size is 1,064,272 bytes; exact app/ELF/config/source hashes and local artifact
paths are in [the offline build manifest](../verification/ALIGN_STATE_010_OFFLINE_BUILD.json).
This candidate has not been flashed and is not an approved recovery image.

## Other retained board

`wearable-node-001` ESP32-S3-Touch-AMOLED-2.06 was last recorded on COM8 after
CALL-010 run008 with UI-001 restored (659,120-byte app, hash/path retained in the
source archive). Basic endpoints were accepted for transition; full-duplex LTE
calling and product acoustics remain unverified. No new operation was performed.

See [BOARD_MATRIX](../hardware/BOARD_MATRIX.md) for capability limits and
[STATUS](STATUS.md) for current outcomes and blockers. Full snapshots/hashes are
listed in [the migration manifest](../archive/alignment/20260922/migration_manifest.json).

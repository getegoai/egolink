---
document_status: authoritative
decision_updated: 2026-10-21
last_verified: 2026-10-21
reviewed_at: 2026-10-21
verified_by: founder/gemini
---

# Active Build

## Custom prototype `HW021_C1_ESP32MODEL_VR00` (`PCB1`) integrated P0 runtime image (2026-10-21)

| Identity | Recorded value |
|---|---|
| Board | `hw021-pcb1-001`, custom `HW021_C1_ESP32MODEL_VR00` (`PCB1`, silkscreen `20260924`) |
| Connection | ESP32-S3 native `USB JTAG/serial debug unit` (`VID_303A&PID_1001`) on `COM8` |
| MCU / MAC / physical flash | `ESP32-S3R8` rev v0.2 (`MAC 02:00:00:00:00:02`) / Winbond `W25Q32JVSQ` 4 MiB (`JEDEC 0xef4016`) |
| Partition table | [partitions_pcb1_4mb.csv](../../firmware/hw021_pcb1_bringup/partitions_pcb1_4mb.csv) (`factory`: 1536KB, `ego_collection`: 1024KB, `ego_media`: 1408KB, `ego_outbox`: 64KB) |
| Firmware project | [firmware/hw021_pcb1_bringup](../../firmware/hw021_pcb1_bringup/README.md) (`CONFIG_SPIRAM=n`, `4MB` custom partition table) |
| App binary SHA-256 | `4C0263E2C85EC9D536606D05FE6DFA1742BDB1203C315838035288A946D2F235` |
| ELF SHA-256 | `4C6383F740E0A38F1C7B2A52B365D3EFB03667AB40BCA0E1744533F732C8790C` |
| Backup path | `.local_backups/pcb1_hw021_bringup_20261020/hw021_pcb1_p0_runtime_4mb.bin` |
| Factory firmware backup | `.local_backups/pcb1_hw021_bringup_20261020/hw021_bringup_0x0_0x50000.bin` (`SHA-256: 543503393D31F1170F8374D2687E83534199F76FC81542E8BD730C1DF92E2DB0`) |
| Evidence & review report | [HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md](../hardware/HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md), `reports/board_validation/pcb1_bringup_20261020/pcb1_integrated_p0_runtime_20261021.log`, `summary.json` |
| Verified scope | Full 10-stage hardware bring-up + Stage 11 integrated P0 runtime loop on hardware: 4MB Flash partition table verified (`factory`, `ego_collection`, `ego_media`, `ego_outbox`); battery switch/ADC (`4240 mV`, 100% SoC); buttons `KEY (GPIO6)` and `BOOT (GPIO0)`; `SC7A20TR` (`0x19`, `WHO_AM_I=0x11`, 16.7Hz `|a|=933 mg`) continuous ingestion; `Beitian BE-220` GNSS (`115200` baud NMEA `$GNRMC` parsing); `CON1` 64GB TF card (`SC64G`, 60,906 MB, 1-bit SDMMC, MBR type `0x07` exFAT/NTFS); `ML307A-DSLN` live China Mobile LTE SIM (`+CPIN: READY`, `46000`, `CSQ: 31,99`, RSRP `-78dBm` to `-99dBm`, PDP IPv4 `10.11.39.93` + IMS VoLTE IPv6 `2409:815B:...`); 2.4GHz Wi-Fi scan (7 APs, `-49 dBm`, BSSID hash `000000000000...`); `ego_state_engine` continuous 5s window evaluation (`indoor_weak_gnss`, `normal`, `wearable_or_bag`, confidence `0.50`, SHA-256 evidence digest); and persistent outbox record commits into the `ego_outbox` partition at offset `0x3f0000` with CRC32 checksum |
| Limits | Outdoor GNSS fix and live voice acoustic path unverified; camera SCCB (`GPIO7/8`) isolated via `CAM_PWDN=0` awaiting hardware trace cut rework |

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

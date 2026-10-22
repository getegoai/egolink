---
document_status: authoritative
last_verified: 2026-10-20
reviewed_at: 2026-10-20
latest_reported_runtime: 2026-10-20
verified_by: founder/gemini
---

# Board Capability Matrix

Newer 9/18-21 observations below are attributed to their dated runtime reports;
2026-10-20 adds live `COM8` bring-up evidence for the first custom prototype PCB
(`HW021_C1_ESP32MODEL_VR00` / `PCB1`). Exact image/boot identity belongs to
[ACTIVE_BUILD](../current/ACTIVE_BUILD.md). MCU revision is not PCB revision.

| Board | Role and hardware | Current evidence boundary |
|---|---|---|
| `hw021-pcb1-001` | Custom `HW021_C1_ESP32MODEL_VR00` (`PCB1`, silkscreen `20260924`); `ESP32-S3R8` rev v0.2 (`MAC 02:00:00:00:00:02`), Winbond `W25Q32JVSQ` 4 MiB flash (`0xef4016`), `ML307A-DSLN` (`ML307A-DSLN-MTSH1S00`), `SC7A20TR` (`0x19`), external `Beitian BE-220` GNSS, `TY-OV2640-75MM-V1.0` camera, `8002A` amp + mic/spk, `200mAh` LiPo | 2026-10-20 10-stage bring-up on `COM8` ([report](HW021_PCB1_BRINGUP_AND_REVIEW_20261020.md)): ADC `V_BAT=4242mV`, `SC7A20TR` 50Hz 1g PASS, `BE-220` 115200 NMEA PASS, Wi-Fi 7 APs (`-51dBm`) PASS, `ML307A-DSLN-MTSH1S00` AT + VoLTE/IMS/Audio command set (`+CAVIMS: 1`, `AT+CLCC`, `AT+VTS`, `AT+CMUT`, `AT*Audio`) PASS (no SIM inserted). Camera SCCB `GPIO7/8` blocked by schematic short to `3.3V_VCC` awaiting trace cut; `CONFIG_SPIRAM=n` required due to `GPIO26/33-37` pin assignment. |
| `connectivity-node-001` | Waveshare ESP32-S3-SIM7670G-4G; ESP32-S3 rev v0.2, 16 MiB physical flash; formal PCB revision unknown | Single-board A-line vehicle; last reported Boot188 on COM3, 9/21 (and Boot211 9/23). No product capability implied by the model name. |
| `wearable-node-001` | ESP32-S3-Touch-AMOLED-2.06; QMI8658 observed; no P0 onboard GNSS/cellular path | Historical CALL-010 endpoints accepted for transition, UI-001 restored; excluded from current A-line. Full duplex/product acoustics unverified. |
| `pc-bridge` | Development Windows host | Build, review and bench tool; not product Ego Base or field runtime dependency. |

## Connectivity capabilities

| Capability | Label / latest scoped evidence | Unverified boundary |
|---|---|---|
| LTE data | observed: run015 manual JPEG, run017 600s ordinary uploads, Boot171/188 sensor uploads; SIM7670G USB PPP | Current-candidate route transition, long-run loss/reconnect and representative field reliability |
| GNSS | observed: historical firmware fix and 9/21 bicycle fixes reported; no-fix preserved | Reference accuracy/TTFF campaign, receiver/antenna/body placement causality and product RF |
| External IMU | observed: ATK-NB018 V1.0 QMI8658A, `0x6A`, GPIO15/16; bounded samples and Boot171/188 20Hz reports | Calibration, mounting, orientation ground truth and activity/fall accuracy |
| Battery | observed: MAX17048 `0x36`, reported probe `0x0012` and telemetry | Meter accuracy, charging-state truth, 24h/48h endurance, energy benefit and peak-power behavior |
| Camera | observed: OV5640 manual QVGA joint capture and LTE/API hash match 9/16; preview 9/17; timed enable/limit/STOP with battery 9/18 | Current-candidate timed outage/reboot recovery, quotas/corruption, long coexistence, physical power-off and product optics |
| Persistent storage | observed: 16 MiB flash, collection spool and 9 MiB JPEG partition mounted in named runs; prior range readback documented | General loss-free recovery, all failure windows and long-wear behavior; SD/TF not product-verified |
| Ego-state | observed: initialization and one rule output uploaded/stored in Boot188 | Freshness/contract repair not flashed; classification validity, full replay evidence chain and measured confidence |
| Audio | unknown/unverified: current connectivity board has no attached microphone/speaker path established for this task | Native cellular acoustic closure requires a separately identified audio-capable carrier |
| Native cellular call | source/host-test integration plus reported driver initialization | Actual AT configuration, dialing/answering, operator support and bidirectional sound unverified |
| SOS/product hardware | unverified | Physical SOS/human closure, final PCB, waterproofing, RF, compliance and all product Gates |

## Constraints and retained evidence

Shared I2C uses GPIO15/16. Keep the TF card absent/driver disabled for this Camera
profile (GPIO46 conflict) and GPIO39-42 free of external JTAG. Preserve original
board, image, connection, time and evidence identity; a later source commit does
not extend an earlier run's result.

- [LTE Camera / concurrency / throughput report](CAMERA_LTE_MANUAL_CLOSURE_20260916.md)
- [Shared-I2C Camera report](CAMERA_SHARED_I2C_TRIAL_20260909.md)
- [Media preflight](CAMERA_MEDIA_RANGE_PREFLIGHT_20260909.md)
- [Latest timer record](../tasks/active/P0-CONVERGENCE-20260905.md)
- [Original full board matrix and historical test paths](../archive/alignment/20260922/docs__hardware__BOARD_MATRIX.md.source)

9/18-21 reports require completion of their raw evidence index; this matrix does
not invent missing logs or infer unmeasured capability. Historical failures stay
in the source archive and named reports.

## Cellular Calling/SMS Boundary

Voice calling and SMS are `unverified`: a native cellular AT driver is now
implemented, but there is no accepted ATD/ATA/CMGS evidence proving real calling
or SMS, and no implemented SMS product path. Driver initialization is not a call.
An operator-approved hardware task must bind actual dialing/answering scope,
participants, destinations, privacy and stop conditions. The new primary-cellular
product decision does not confer hardware evidence or authorize calls.

## Label rules

`unknown` means unproven; `observed` is dated engineering evidence; `verified`
requires a named acceptance result. PC-side/build/test evidence never becomes a
product claim. Product `P0-LOC`, `P0-CALL`, `P0-SOS` remain `NOT_RUN`.

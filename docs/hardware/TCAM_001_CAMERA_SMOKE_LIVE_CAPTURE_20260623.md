# TCAM-001 Camera Smoke Live Capture

Date: 2026-06-23

## Goal

Collect bounded real camera evidence from the Waveshare ESP32-S3-SIM7670G-4G
board without folding camera capture into the product `mqtt_heartbeat` firmware.

## Firmware Change

`firmware/camera_smoke` now emits a catchable startup capture sequence:

- Delay before first capture: 5000 ms.
- Capture count: 3.
- Capture interval: 3000 ms.
- Each capture logs `capture_index`, JPEG byte count, FNV-1a checksum, frame
  geometry, pixel format, and JPEG SOI/EOI bytes.

## Hardware Run

Flashed:

```powershell
. C:\Espressif\v5.4.2\esp-idf\export.ps1; idf.py -p COM4 flash
```

Result:

- Chip: ESP32-S3, MAC `02:00:00:00:00:03`.
- App: `egolink_camera_smoke`.
- App binary size: `0xdce40`.
- Smallest app partition free: `0x231c0` bytes, 14%.
- Flash and hash verification passed; board hard-reset successfully.

UART capture:

```text
pc_simulator/runtime/camera-smoke-live-20260623-1842-uart.log
```

The board was reset with `esptool.py --chip esp32s3 -p COM4 run`, then COM4 was
read at 115200 baud for 25 seconds.

## Evidence

Camera identity and init:

```text
Detected OV5640 camera
CAMERA_SMOKE_INIT_OK profile=waveshare_esp32s3_sim7670g_4g
CAMERA_SMOKE_CAPTURE_SEQUENCE delay_ms=5000 count=3 interval_ms=3000
```

Captured frames:

| Capture | Bytes | Checksum | Width | Height | Format | JPEG SOI | JPEG EOI |
|---:|---:|---|---:|---:|---:|---|---|
| 1 | 2893 | `a5db84d7` | 320 | 240 | 4 | `ffd8` | `ffd9` |
| 2 | 3708 | `94301dec` | 320 | 240 | 4 | `ffd8` | `ffd9` |
| 3 | 3700 | `7a151b26` | 320 | 240 | 4 | `ffd8` | `ffd9` |

Optional HTTP endpoint also came up because Wi-Fi credentials were present:

```text
CAMERA_SMOKE_HTTP_READY ip=192.168.31.12
```

This task did not fetch `/capture`; the durable evidence is the UART log above.

## Current Boundary

- Verified: the current physical camera path initializes as OV5640 and produces
  three valid QVGA JPEG frames through `firmware/camera_smoke`.
- Still not verified: product `mqtt_heartbeat` camera integration, privacy
  authorization, retention policy, image hash manifest, upload path,
  VisionGate, accident visual understanding, and camera power-state control.
- Current board firmware after this task is `firmware/camera_smoke`, not
  `firmware/mqtt_heartbeat`.

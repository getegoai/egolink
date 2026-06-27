---
document_status: authoritative
last_verified: 2026-06-26
verified_by: codex
---

# Active Build

## Host

- Workspace: `D:\pywork\egolink`
- Primary shell: Windows PowerShell
- ESP-IDF used in recent builds: `C:\Espressif\v5.4.2\esp-idf`

## Connected Development Boards

| role | current board | observed ports | current use |
|---|---|---|---|
| `wearable_node` | ESP32-S3-Touch-AMOLED-2.06 | Espressif USB Serial/JTAG, recently `COM9` | AMOLED prompt/touch demo, QMI8658 capture path |
| `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | CH343 ESP32 console, SIM7670G USB AT ports recently `COM6`/`COM7` | 4G/GNSS/camera capability validation |

Port numbers are observations, not stable configuration. Tooling must identify devices by USB identity and/or versioned `hello`.

## Recently Verified Capabilities

- Full Demo v0.5 runner can produce one complete summary from real AMOLED IMU/touch evidence, SIM7670G GNSS AT evidence, mock-only structured audio evidence, session recording, quality gate, and replay.
- Same-run AMOLED IMU/touch confirmation evidence has been captured: `motion_event`, `ask_user_rendered`, `user_confirmation=safe`, and final PC `safety_event`.
- AMOLED `ask_user` command path rendered and returned `user_confirmation=safe` in Demo v0.2 evidence.
- Demo v0.3 generated a complete safety record using Demo v0.2 real AMOLED confirmation evidence plus live SIM7670G GNSS AT probe.
- SIM7670G GNSS AT probe was reachable indoors, selected `COM6`, and produced `fix=false`.
- QMI8658 live data has been captured from the AMOLED board in an engineering fixture context.
- Camera smoke capture on the SIM7670G board has produced bounded JPEG evidence.

## Current Known Limits

- GNSS indoor no-fix is expected and is not a P0 failure by itself.
- SIM7670G GNSS refresh is currently PC-side USB AT probe, not yet connectivity-node firmware handling `request_location`.
- Full Demo v0.5 audio evidence is structured mock-only; real microphone capture and audio acceptance remain unverified.
- The latest Demo v0.3/v0.5 motion candidate can use real AMOLED QMI8658 `motion_event` evidence, but it is still a demo-only heuristic, not MotionNet output.
- Formal IMU product acceptance remains false until final mounting/calibration gates are met.

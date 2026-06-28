---
document_status: authoritative
last_verified: 2026-06-27
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
| `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | CH343 ESP32 console recently `COM4`, SIM7670G USB AT ports recently `COM5`/`COM6`/`COM7`/`COM8` | FW-002C resetdiag fix3 HTTP Message Hub firmware flashed; USB-Free SIM7670G GNSS real-fix validation passed through VPS Message Hub |

Port numbers are observations, not stable configuration. Tooling must identify devices by USB identity and/or versioned `hello`.

## Recently Verified Capabilities

- Full Demo v0.5 runner can produce one complete summary from real AMOLED IMU/touch evidence, SIM7670G GNSS AT evidence, mock-only structured audio evidence, session recording, quality gate, and replay.
- Same-run AMOLED IMU/touch confirmation evidence has been captured: `motion_event`, `ask_user_rendered`, `user_confirmation=safe`, and final PC `safety_event`.
- AMOLED `ask_user` command path rendered and returned `user_confirmation=safe` in Demo v0.2 evidence.
- Demo v0.3 generated a complete safety record using Demo v0.2 real AMOLED confirmation evidence plus live SIM7670G GNSS AT probe.
- SIM7670G GNSS AT probe was reachable indoors, selected `COM6`, and produced `fix=false`.
- QMI8658 live data has been captured from the AMOLED board in an engineering fixture context.
- Camera smoke capture on the SIM7670G board has produced bounded JPEG evidence.
- R1 connectivity-node firmware `0.1.0-fw001-hw-r1` has passed USB-Free
  Message Hub validation on independent power with USB disconnected:
  test run `fw001-hw-r1-20260627-133813`, heartbeat `seq=7`, command ACK
  `seq=8`, evidence under
  `reports/field_validation/fw001-hw-r1-20260627-133813/`.
- FW-002A connectivity-node firmware `0.1.0-fw002-location-scaffold` has passed
  USB-Free request-location scaffold validation on independent power with USB
  disconnected: test run `fw002-location-build-smoke`, heartbeat `seq=3`,
  `request_location` command `cmd-000004`, `location_report seq=4`
  (`fix=false`, `gnss_state=driver_not_integrated`,
  `source_status=unverified`), ACK `seq=5`, evidence under
  `reports/field_validation/fw002-location-build-smoke/`.
- FW-002B fix1 connectivity-node firmware
  `0.1.0-fw002b-sim7670-gnss-fix1` has passed USB-Free SIM7670G
  firmware GNSS AT validation on independent power with USB disconnected:
  test run `fw002b-fix1-gnss-r1-20260627-163246`, heartbeat `seq=57`,
  `request_location` command `cmd-000006`, `location_report seq=58`
  (`source=sim7670g_firmware_gnss`, `gnss_source=sim7670g_uart_at`,
  `gnss_driver=uart_at`, `gnss_query_ok=true`, `fix=false`,
  `gnss_state=no_fix`), ACK `seq=59`, evidence under
  `reports/field_validation/fw002b-fix1-gnss-r1-20260627-163246/`.
- The R3 preflight stability observer exists and first detected a FW-002B fix1
  reset/sequence regression under USB-Free operation:
  `reports/field_validation/stability-fw002b-fix1-20260627-170758/`.
- FW-002C reset-diagnostics firmware was flashed and runtime-observed on the
  connectivity node. Fix1 (`0.1.0-fw002c-resetdiag-fix1`) reproduced repeated
  `panic` resets during a 120-second USB-Free observation:
  `reports/field_validation/stability-fw002c-resetdiag-fix1-20260627-181600/`.
  Fix2 (`0.1.0-fw002c-resetdiag-fix2`) moved the heartbeat status payload off
  the task stack, increased heartbeat stack margin, and passed a 120-second
  USB-Free VPS stability observation with 15 messages, `seq_regressions=0`,
  max message gap 11.547434 seconds, and final last-seen age 6.563391 seconds:
  `reports/field_validation/stability-fw002c-resetdiag-fix2-20260627-183100/`.
- FW-002C resetdiag fix2 was also used for a window-side real-fix attempt over
  the USB-Free Message Hub path. The device received `request_location`
  command `cmd-000008`, returned `location_report seq=601`, and ACKed with
  `seq=602`, but the GNSS result remained `fix=false`, `gnss_state=no_fix`,
  no satellites/HDOP/coordinates, and raw response `+CGPSINFO: ,,,,,,,, OK`.
  Evidence is under
  `reports/field_validation/fw002c-fix2-window-gnss-retry1-20260627-195000/`.
- A later window-side attempt with the same FW-002C resetdiag fix2 image
  produced the first firmware-side SIM7670G `fix=true` report over the
  USB-Free VPS path: command `cmd-000010`, `location_report seq=6920`, ACK
  `seq=6921`, and latitude/longitude fields present. The run is still an
  acceptance FAIL because fix2 labels fixed coordinates as
  `source_status=unverified`; the gate requires `observed` or `verified`.
  Evidence is under
  `reports/field_validation/fw002c-fix2-window-gnss-fix-unverified-20260628-092703/`.
- FW-002C resetdiag fix3 has been build-verified as
  `0.1.0-fw002c-resetdiag-fix3` / `fw002c-resetdiag-fix3-20260628-093000`.
  It changes parsed SIM7670G fixed coordinates to `source_status=observed`.
  The image was flashed on `COM4` and USB-Free validated after the operator
  connected independent power and disconnected USB. The first request saw
  `gnss_state=at_unreachable` while AT was not ready; a retry after one minute
  passed with command `cmd-000012`, `location_report seq=31`, ACK `seq=33`,
  `fix=true`, `gnss_state=fix`, `source_status=observed`, and latitude/
  longitude fields present. Evidence is under
  `reports/field_validation/fw002c-fix3-window-gnss-retry1-20260628-093946/`.

## Current Known Limits

- GNSS indoor no-fix is expected and is not a P0 failure by itself.
- SIM7670G GNSS refresh has PC-side USB AT no-fix evidence and FW-002B
  firmware-side UART/AT no-fix evidence through the USB-Free Message Hub loop.
  Outdoor real fix remains unverified.
- The USB-Free R1 validation used Wi-Fi HTTP to the Message Hub; it does not
  prove SIM7670G LTE data transport, GNSS fix, battery/charging accuracy, or
  product power behavior.
- The currently flashed connectivity-node image is FW-002C resetdiag fix3. It
  reports `reset_reason`, persistent `boot_count`, and `boot_uptime_ms`, and it
  passed the short USB-Free VPS stability gate lineage and the firmware-side
  SIM7670G USB-Free real-fix validation.
- SIM7670G LTE data transport, product battery/charging accuracy, product
  power behavior, and final enclosure/mounting GNSS acceptance remain
  unverified.
- Full Demo v0.5 audio evidence is structured mock-only; real microphone capture and audio acceptance remain unverified.
- The latest Demo v0.3/v0.5 motion candidate can use real AMOLED QMI8658 `motion_event` evidence, but it is still a demo-only heuristic, not MotionNet output.
- Formal IMU product acceptance remains false until final mounting/calibration gates are met.

---
document_status: authoritative
last_verified: 2026-07-04
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
| `wearable_node` | ESP32-S3-Touch-AMOLED-2.06 | Espressif USB Serial/JTAG, recently `COM9` | UI-001 field-friendly D1 status sidecar is currently flashed: cJSON serial downlink parser, `display_status` full-screen `D1 FIELD` page with `LINK`/`LOC`/`PWR`/`POST` rows, non-disruptive `status_update`, payload-driven `ask_user` prompt, QMI8658 engineering sampler. Bounded smoke `ui001-amoled-friendly-smoke-20260704` observed `cmd=display_status` plus `status_rendered`. |
| `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | CH343 ESP32 console recently `COM4`, SIM7670G USB AT ports recently `COM5`/`COM6`/`COM7`/`COM8` | D1 periodic location firmware `0.1.0-d1-periodic-location` is currently flashed on `COM4` after explicit operator confirmation. Flash passed for ESP32-S3 MAC `02:00:00:00:00:03` with bootloader/app/partition-table hashes verified and hard reset completed. After SIM insertion and cold boot, read-only VPS checks verified live LTE periodic uploads with fresh 2026-07-04 timestamps, raw POST `9 ok / 0 fail`, LTE registered/PDP active, and measured MAX17048 power; GNSS coordinates remain unavailable indoors/at current placement (`lat/lon=null`). LTE-011 fix1 observation payload margin previously passed USB-Free runtime validation with `cmd-000033`, and the LTE-010 offline reconnect/store-forward evidence gate passed over that export. |

Port numbers are observations, not stable configuration. Tooling must identify devices by USB identity and/or versioned `hello`.

## Recently Verified Capabilities

- Full Demo v0.5 runner can produce one complete summary from real AMOLED IMU/touch evidence, SIM7670G GNSS AT evidence, mock-only structured audio evidence, session recording, quality gate, and replay.
- Same-run AMOLED IMU/touch confirmation evidence has been captured: `motion_event`, `ask_user_rendered`, `user_confirmation=safe`, and final PC `safety_event`.
- AMOLED-001 sidecar display smoke has been captured on `COM9`: `status_update`
  rendered a D1 status page and a payload-driven `ask_user` rendered the safety
  prompt; this did not re-test physical tap confirmation.
- AMOLED-002 sidecar runner can mirror current VPS `/api/state` D1 status to
  the AMOLED screen over `COM9`; smoke `amoled002-d1-status-vps-smoke2-20260704`
  rendered `estimate_visible`, LTE registered/PDP active, no-fix map mode,
  battery, and raw POST counters without sending 4G-board commands.
- AMOLED-003 field companion runner can start the D1 field observer and AMOLED
  sidecar together with one run ID; smoke
  `amoled003-companion-vps-smoke5-20260704` passed on `COM9` with one observer
  sample and one AMOLED `status_rendered` event.
- AMOLED-004 visible sidecar fix is flashed on `COM9`: `display_status` now
  forces the full-screen D1 status page and passed companion smoke
  `amoled004-companion-visible-vps-smoke-20260704`.
- UI-001 field-friendly AMOLED screen is flashed on `COM9`: `display_status`
  renders `D1 FIELD` with `LINK`, `LOC`, `PWR`, and `POST` rows and passed
  smoke `ui001-amoled-friendly-smoke-20260704`.
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
- LTE-001B status observability firmware has been build/flashed as
  `0.1.0-lte001b-observe` / `lte001b-observe-20260628-130400`. The image was
  built with SIM7670G GNSS and LTE-status observability enabled, flashed on
  `COM4`, and hard-reset successfully. The binary is
  `firmware/mqtt_heartbeat/build_lte001b_observe/egolink_mqtt_heartbeat.bin`.
  USB-Free runtime validation attempt 1 failed because the VPS saw new firmware
  registration but no fresh LTE-001B status heartbeat; evidence is under
  `reports/field_validation/lte001b-observe-20260628-130400/`.
- LTE-001B fix1 has been build-verified as
  `0.1.0-lte001b-observe-fix1` / `lte001b-observe-fix1-20260628-131739`.
  It moves LTE observation fragments out of heartbeat/sensor task stack and
  raises both task stacks to 12288 bytes. The binary is
  `firmware/mqtt_heartbeat/build_lte001b_observe_fix1/egolink_mqtt_heartbeat.bin`.
  The fix1 image was flashed on `COM4`, hard-reset successfully, and passed
  USB-Free LTE status observability validation through the VPS Message Hub:
  `reason_code=LTE_READY`, `registration_state=registered_home`,
  `pdp_state=active`, assigned IP present, RAT `LTE`, cell ID `180571649`, RSSI
  `-90`, RSRP `-97`, RSRQ `-7`, SINR `28`. Evidence is under
  `reports/field_validation/lte001b-observe-fix1-20260628-131739/`.
- LTE-002 LTE HTTP probe firmware has been build-verified as
  `0.1.0-lte002-lte-http-probe` /
  `lte002-lte-http-probe-20260628-141656`. The image enables SIM7670G GNSS,
  LTE status, and LTE HTTP probe mode, skips Wi-Fi runtime tasks in that mode,
  and builds to
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe/egolink_mqtt_heartbeat.bin`.
  The image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-20260628-141656/flash_report.md`.
  USB-Free LTE HTTP runtime validation attempt 1 failed as recorded below.
- LTE-002 validation attempt 1 failed after the operator connected independent
  power and disconnected USB. `scripts/validate_lte_http_probe.py` observed no
  fresh `lte_http_probe` telemetry through the VPS Message Hub between
  `2026-06-28T06:30:38Z` and `2026-06-28T06:34:41Z`; `/api/state` remained on
  the prior LTE-001B fix1 Wi-Fi message lineage with
  `observability.transport.type=mock_4g_over_wifi`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-20260628-141656/`.
- LTE-002 fix1 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix1` /
  `lte002-lte-http-probe-fix1-20260628-143631`. It waits up to 120 seconds for
  SIM7670G LTE status to report `LTE_READY` before attempting AT HTTP POST.
  The binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix1/egolink_mqtt_heartbeat.bin`.
  The fix1 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix1-20260628-143631/flash_report.md`.
  USB-Free runtime validation attempt 2 failed as recorded below.
- LTE-002 fix1 validation attempt 2 failed after the operator connected
  independent power and disconnected USB. `scripts/validate_lte_http_probe.py`
  observed no fresh `lte_http_probe` telemetry through the VPS Message Hub
  between `2026-06-28T08:12:31Z` and `2026-06-28T08:16:34Z`; `/api/state`
  remained on the prior LTE-001B fix1 Wi-Fi message lineage with
  `observability.transport.type=mock_4g_over_wifi`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix1-20260628-143631/`.
- LTE-002 fix2 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix2` /
  `lte002-lte-http-probe-fix2-20260628-161844`. It keeps Wi-Fi disabled for the
  LTE HTTP probe path and changes the probe from one round to a bounded retry:
  up to `CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_MAX_ATTEMPTS=6`, waiting
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_PROBE_RETRY_INTERVAL_SEC=20` seconds
  between failed rounds. The binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix2/egolink_mqtt_heartbeat.bin`.
  The fix2 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix2-20260628-161844/flash_report.md`.
  USB-Free runtime validation attempt 3 failed as recorded below.
- LTE-002 fix2 validation attempt 3 failed after the operator connected
  independent power and disconnected USB. `scripts/validate_lte_http_probe.py`
  observed no fresh `lte_http_probe` telemetry through the VPS Message Hub
  between `2026-06-28T08:55:08Z` and `2026-06-28T09:02:11Z`; `/api/state`
  remained on the prior LTE-001B fix1 Wi-Fi message lineage with
  `observability.transport.type=mock_4g_over_wifi`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix2-20260628-161844/`.
- LTE-002 fix3 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix3` /
  `lte002-lte-http-probe-fix3-20260628-170508`. It keeps Wi-Fi disabled and
  keeps the fix2 bounded retry behavior, but skips `AT+HTTPPARA="CID",1` by
  default through `CONFIG_EGOLINK_SIM7670_LTE_HTTP_SET_CID_PARAM=n`, matching
  the A7600/A7670-style SIMCom HTTP flow more closely. The binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix3/egolink_mqtt_heartbeat.bin`.
  The fix3 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix3-20260628-170508/flash_report.md`.
  USB-Free runtime validation attempt 4 failed as recorded below.
- LTE-002 fix3 validation attempt 4 failed after the operator connected
  independent power and disconnected USB. `scripts/validate_lte_http_probe.py`
  observed no fresh `lte_http_probe` telemetry through the VPS Message Hub
  between `2026-06-28T09:51:18Z` and `2026-06-28T09:58:22Z`; `/api/state`
  remained on the prior LTE-001B fix1 Wi-Fi message lineage with
  `observability.transport.type=mock_4g_over_wifi`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix3-20260628-170508/`.
- USB-attached LTE HTTP AT diagnosis then proved that the SIM7670G module and
  VPS path are capable of HTTP over LTE for compact payloads: `/health` GET
  returned HTTP 200, and a bearer-auth telemetry POST with a compact 211-byte
  payload returned HTTP 200. The same diagnostic reproduced `+HTTPACTION:
  1,706,0` once authenticated POST bodies reached 2237 and 3230 bytes, while a
  1232-byte POST still passed. Evidence is under
  `reports/field_validation/lte002-atdiag-http-20260628/`,
  `reports/field_validation/lte002-atdiag-authpost-20260628/`,
  `reports/field_validation/lte002-atdiag-authpost-pad1000-20260628/`,
  `reports/field_validation/lte002-atdiag-authpost-pad2000-com7-20260628/`,
  and `reports/field_validation/lte002-atdiag-authpost-large-20260628/`.
- LTE-002 fix4 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix4` /
  `lte002-lte-http-probe-fix4-20260628-184644`. It compacts the
  `lte_http_probe` payload to stay near the PC-side passing payload range while
  preserving `transport.type=lte`, HTTP status/reason, and LTE/cell readiness
  context. The binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix4/egolink_mqtt_heartbeat.bin`.
  The fix4 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix4-20260628-184644/flash_report.md`.
  USB-Free runtime validation failed with no fresh `lte_http_probe` telemetry
  reaching the VPS Message Hub; evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix4-20260628-184644/`.

## Current Known Limits

- GNSS indoor no-fix is expected and is not a P0 failure by itself.
- SIM7670G GNSS refresh has PC-side USB AT no-fix evidence and FW-002B
  firmware-side UART/AT no-fix evidence through the USB-Free Message Hub loop.
  FW-002C fix3 later observed a real firmware-side SIM7670G GNSS fix, but final
  enclosure/mounting GNSS acceptance remains unverified.
- The early USB-Free R1 validation used Wi-Fi HTTP to the Message Hub; it did
  not prove SIM7670G LTE transport, GNSS fix, battery/charging accuracy, or
  product power behavior. LTE-002 fix5 later proved one SIM7670G LTE HTTP
  telemetry uplink thin-slice only.
- Earlier LTE-002 fix5
  `0.1.0-lte002-lte-http-probe-fix5` proved one LTE HTTP uplink thin-slice.
  The first LTE-002 image and fix1 failed
  USB-Free LTE HTTP validation with no fresh LTE HTTP telemetry reaching the
  VPS; fix2 also failed with no fresh LTE HTTP telemetry reaching the VPS.
  Fix3 also failed with no fresh LTE HTTP telemetry reaching the VPS. The prior
  LTE-001B fix1 image passed USB-Free LTE status observation. USB-attached AT
  diagnosis indicates compact LTE HTTP payloads can reach the VPS, while larger
  POST bodies trigger SIM7670G `HTTPACTION` 706. Fix4 was flashed but failed USB-Free
  validation with zero test-run messages. USB-attached firmware console
  diagnosis then observed repeated `main` task stack overflows before any LTE
  readiness or HTTP AT command log appeared:
  `reports/field_validation/lte002-fix4-console-diag-20260628/`.
- LTE-002 fix5 has been build-verified as
  `0.1.0-lte002-lte-http-probe-fix5` /
  `lte002-lte-http-probe-fix5-20260628-193815`. It moves LTE HTTP probe
  execution out of the ESP-IDF `main` task and into a dedicated
  `lte_http_probe_task` with `LTE_HTTP_PROBE_TASK_STACK_SIZE=12288`. The
  binary is
  `firmware/mqtt_heartbeat/build_lte002_lte_http_probe_fix5/egolink_mqtt_heartbeat.bin`.
  The fix5 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix5-20260628-193815/flash_report.md`.
  USB-Free runtime validation passed after the operator disconnected USB and
  power-cycled the independent-power board: result `lte_http_probe` had
  `transport.type=lte`, `lte_http.reason_code=LTE_HTTP_OK`, HTTP status `200`,
  action elapsed `1570 ms`, LTE `reason_code=LTE_READY`, assigned IP
  `10.160.15.113`, and cell ID `180571649`. Evidence is under
  `reports/field_validation/lte002-lte-http-probe-fix5-20260628-193815/`.
- LTE-003 command-loop firmware has been build-verified as
  `0.1.0-lte003-command-loop` /
  `lte003-command-loop-20260628-210214`. It enables
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED`, skips Wi-Fi as the
  runtime data path for that image, polls the existing Message Hub command
  queue through SIM7670G AT HTTP GET, and ACKs one harmless
  `set_report_interval` command through SIM7670G AT HTTP POST with
  `transport.type=lte` evidence on the ACK. The binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop/egolink_mqtt_heartbeat.bin`.
  The image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte003-command-loop-20260628-210214/flash_report.md`.
  USB-Free runtime validation attempts 1 and 2 failed: `cmd-000013`
  (`set_report_interval`) remained pending, no ACK was received, the test-run
  export contained zero messages, and VPS state still showed the prior LTE-002
  fix5 telemetry as latest. Attempt 2 reused the pending command after an
  independent-power cold reboot with USB still disconnected. Runtime evidence
  is under `reports/field_validation/lte003-command-loop-20260628-210214/`,
  including `lte_command_loop_report_attempt2_existing_cmd.json`.
- LTE-003 fix1 has been build-verified as
  `0.1.0-lte003-command-loop-fix1` /
  `lte003-command-loop-fix1-20260628-223454`. It adds
  `lte_http_command_diag` telemetry over SIM7670G LTE HTTP POST around command
  polling and increases `lte_http_command_task` stack to `16384`. The binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix1/egolink_mqtt_heartbeat.bin`.
  The fix1 image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte003-command-loop-fix1-20260628-223454/flash_report.md`.
  Runtime validation failed with `cmd-000013` still pending and no ACK. The
  test-run export contained 37 earlier `lte_http_command_diag` messages: fix1
  reached LTE readiness and posted diagnostics, but command poll ended with
  `lte_http.poll_reason_code=LTE_HTTP_READ_FAILED`, HTTP status `200`, and
  `poll_data_len=592`. Evidence is under
  `reports/field_validation/lte003-command-loop-fix1-20260628-223454/`.
- LTE-003 fix2 has been build-verified as
  `0.1.0-lte003-command-loop-fix2` /
  `lte003-command-loop-fix2-20260629-074709`. It increases the SIM7670 AT
  response buffer from `512` to `1536` bytes so command-poll `HTTPREAD` can
  hold the observed response body plus SIMCom framing. The binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix2/egolink_mqtt_heartbeat.bin`.
  It was rebuilt after commit so the build app version is `43f5f55`. The fix2
  image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/partition
  table were written, hashes verified, and hard reset completed. Flash evidence
  is under
  `reports/field_validation/lte003-command-loop-fix2-20260629-074709/flash_report.md`.
  USB-Free runtime validation failed after the operator cold-booted the board
  on independent power with USB disconnected. The validator reused
  `cmd-000013` from `2026-06-28T23:58:07Z` to `2026-06-29T00:04:07Z`; the
  command remained pending and no ACK was received. The test-run export
  contained 51 LTE diagnostic messages, with the latest reporting HTTP poll
  status `200`, `poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_FAILED`. Evidence is under
  `reports/field_validation/lte003-command-loop-fix2-20260629-074709/`.
- LTE-003 fix3 has been build-verified as
  `0.1.0-lte003-command-loop-fix3` /
  `lte003-command-loop-fix3-20260629-081529`. It keeps LTE-003 acceptance
  unchanged, but makes command-poll `AT+HTTPREAD` use the longer LTE HTTP
  action timeout and splits the prior `LTE_HTTP_READ_FAILED` condition into
  `LTE_HTTP_READ_AT_FAILED` and `LTE_HTTP_READ_BODY_PARSE_FAILED`. The fix3
  code-change commit is `e79e4de`; the flashed build app version is `79a12c8`
  because the guarded flash re-ran CMake at the documentation commit. The binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix3/egolink_mqtt_heartbeat.bin`,
  and its size is `291488` bytes. Focused tests, `context_lint`,
  `verify.ps1`, `git diff --check`, and the guarded prepare/build passed.
  The image was flashed on `COM4`; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/lte003-command-loop-fix3-20260629-081529/flash_report.md`.
  USB-Free runtime validation failed from `2026-06-29T00:26:51Z` to
  `2026-06-29T00:32:53Z` after the operator connected independent power and
  disconnected USB. The validator reused `cmd-000013`; the command remained
  pending and no ACK was received. The test-run export contained 59 LTE
  diagnostic messages, with the latest reporting HTTP poll status `200`,
  `poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_AT_FAILED`. Evidence is under
  `reports/field_validation/lte003-command-loop-fix3-20260629-081529/`.
- LTE-003 fix4 has been implemented and build-verified as
  `0.1.0-lte003-command-loop-fix4` /
  `lte003-command-loop-fix4-20260629-084350`. It tries positional
  `AT+HTTPREAD=0,<data_len>` before falling back to bare `AT+HTTPREAD`, and
  separates HTTPREAD `ERROR` from timeout diagnostics with
  `LTE_HTTP_READ_AT_ERROR` and `LTE_HTTP_READ_AT_TIMEOUT`. The source/build
  app commit is `c8e1f59`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix4/egolink_mqtt_heartbeat.bin`,
  and its size is `291872` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. The image was flashed on `COM4` after explicit
  operator confirmation; ESP32-S3 was detected, bootloader/app/partition table
  were written, hashes verified, and hard reset completed. The flashed
  repo/app version is `b4eaa44` because the guarded flash re-ran CMake at the
  documentation commit. Flash evidence is under
  `reports/field_validation/lte003-command-loop-fix4-20260629-084350/flash_report.md`.
  USB-Free runtime validation failed from `2026-06-29T07:38:00Z` to
  `2026-06-29T07:44:00Z` after the operator connected independent power and
  disconnected USB. The validator reused `cmd-000013`; the command remained
  pending and no ACK was received. The test-run export contained 37 LTE
  diagnostic messages, with the latest reporting LTE ready, HTTP poll status
  `200`, `poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_BODY_PARSE_FAILED`. Evidence is
  under `reports/field_validation/lte003-command-loop-fix4-20260629-084350/`.
- LTE command polling/ACK, reconnect behavior, long-run LTE stability, product
  battery/charging accuracy, product power behavior, and final
  enclosure/mounting GNSS acceptance remain unverified. LTE-003 currently has
  fix4 build/flash evidence and failed runtime attempts through fix4; it does
  not prove LTE command polling/ACK until the USB-Free Message Hub validator
  passes.
- LTE-003 fix5 has been implemented and build-verified as
  `0.1.0-lte003-command-loop-fix5` /
  `lte003-command-loop-fix5-20260629-154839`. It keeps the positional
  `AT+HTTPREAD=0,<data_len>` attempt, but falls through to bare `AT+HTTPREAD`
  when the positional command returns `OK` without an extractable JSON body.
  The source/build app commit is `729c78b`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix5/egolink_mqtt_heartbeat.bin`,
  and its size is `291872` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. The image was flashed on `COM4` after explicit
  operator confirmation; ESP32-S3 was detected, bootloader/app/partition table
  were written, hashes verified, and hard reset completed. The flashed
  repo/app version is `efc9848` because the guarded flash re-ran CMake at the
  documentation commit. Flash evidence is under
  `reports/field_validation/lte003-command-loop-fix5-20260629-154839/flash_report.md`.
  USB-Free runtime validation failed from `2026-06-29T07:58:34Z` to
  `2026-06-29T08:04:36Z` after the operator connected independent power and
  disconnected USB. The validator reused `cmd-000013`; the command remained
  pending and no ACK was received. The test-run export contained 37 LTE
  diagnostic messages, with the latest reporting LTE ready, HTTP poll status
  `200`, `poll_data_len=592`, and
  `lte_http.poll_reason_code=LTE_HTTP_READ_BODY_PARSE_FAILED`. Evidence is
  under `reports/field_validation/lte003-command-loop-fix5-20260629-154839/`.
- LTE-003 fix6 has been implemented, build-verified, and flashed as
  `0.1.0-lte003-command-loop-fix6` /
  `lte003-command-loop-fix6-20260629-160859`. It adds an HTTPREAD-specific
  UART collection path that keeps reading past the generic AT `OK` match until
  a JSON body is captured, an error appears, or the bounded timeout/quiet
  window expires. The source/build app commit is `c1a90a0`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix6/egolink_mqtt_heartbeat.bin`,
  and its size is `292512` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. Flash on `COM4` passed after explicit operator
  confirmation; flashed repo/app version is `8d7395f`, and flash evidence is
  under
  `reports/field_validation/lte003-command-loop-fix6-20260629-160859/flash_report.md`.
  USB-Free runtime validation failed: the validator reused pending `cmd-000013`
  from `2026-06-29T08:31:32Z` to `2026-06-29T08:37:33Z`, the command remained
  `pending`, and no ACK was received. The test-run export contained 37 fix6
  diagnostics from `2026-06-29T08:18:30Z` to `2026-06-29T08:23:32Z`, with the
  latest showing LTE ready, HTTP poll status `200`, body length `592`,
  `LTE_HTTP_OK`, and empty `command.last_cmd_id`. Evidence is under
  `reports/field_validation/lte003-command-loop-fix6-20260629-160859/`.
  Fix7 should add command parser diagnostics and a longer bounded poll window.
- LTE-003 fix7 has been implemented and build-verified as
  `0.1.0-lte003-command-loop-fix7` /
  `lte003-command-loop-fix7-20260629-164429`. It adds command poll parser
  observability (`command.parse_status` and `command.command_count`) to both
  LTE command diagnostics and ACK payloads, and increases the bounded command
  poll window to
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_POLL_MAX_ATTEMPTS=120` at
  5-second intervals. The source/build app commit is `33b8503`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix7/egolink_mqtt_heartbeat.bin`,
  and its size is `293104` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. Flash on `COM4` passed after explicit operator
  confirmation; flashed repo/app version is `766f0d8`, and flash evidence is
  under
  `reports/field_validation/lte003-command-loop-fix7-20260629-164429/flash_report.md`.
  USB-Free runtime validation failed: the validator reused pending `cmd-000013`
  from `2026-06-29T08:54:55Z` to `2026-06-29T09:00:56Z`, the command remained
  `pending`, and no ACK was received. The test-run export contained 66 fix7
  diagnostics from `2026-06-29T08:51:43Z` to `2026-06-29T09:00:55Z`: one
  `phase=ready` / `command.parse_status=not_polled`, then 65
  `phase=poll_no_ack` with `command.parse_status=json_parse_failed`. Latest
  diagnostics showed LTE ready, HTTP poll status `200`, body length `592`,
  `LTE_HTTP_OK`, `command.command_count=0`, and empty `command.last_cmd_id`.
  Evidence is under
  `reports/field_validation/lte003-command-loop-fix7-20260629-164429/`.
  Fix8 should make HTTPREAD body extraction wait for a complete JSON object.
- LTE-003 fix8 has been implemented and build-verified as
  `0.1.0-lte003-command-loop-fix8` /
  `lte003-command-loop-fix8-20260629-170628`. It changes the SIM7670G HTTPREAD
  body extractor to wait for a complete brace-balanced JSON object, with
  string/escape awareness, before returning a JSON body. The source/build app
  commit is `a87a754`; the binary is
  `firmware/mqtt_heartbeat/build_lte003_command_loop_fix8/egolink_mqtt_heartbeat.bin`,
  and its size is `293216` bytes. Focused LTE/firmware tests,
  `context_lint`, `verify.ps1`, `git diff --check`, and the guarded
  prepare/build passed. Fix8 has not been flashed or USB-Free runtime
  validated yet.
- FW-003 raw-frame LTE command-loop firmware has been implemented and
  build-verified as `0.1.0-fw003-raw-command-loop` /
  `fw003-raw-command-loop-20260629-175608`. It keeps
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED`, skips Wi-Fi for that
  image, polls `GET /commands/poll.raw`, verifies the `EGLK/1` raw-frame
  length and CRC32, parses compact key/value commands, and posts raw ACK frames
  to `POST /commands/{cmd_id}/ack.raw`. The binary is
  `firmware/mqtt_heartbeat/build_fw003_raw_command_loop/egolink_mqtt_heartbeat.bin`,
  and its size is `286176` bytes. Focused firmware/server tests passed with
  24 tests, `context_lint` passed, full `verify.ps1` passed with 278 tests,
  `git diff --check` passed, and the guarded ESP-IDF prepare/build passed. The
  VPS Message Hub was redeployed after adding raw ACK derived LTE evidence; the
  public smoke `fw003-raw-derived-smoke-20260629-175946` ACKed `cmd-000016`
  through raw frames and derived `transport.type=lte` plus
  `lte_http.phase=command_ack`. FW-003 was then flashed on `COM4` after
  explicit operator confirmation; ESP32-S3 was detected, bootloader/app/
  partition table were written, hashes verified, and hard reset completed.
  Flash evidence is under
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/flash_report.md`.
  USB-Free runtime validation passed after an independent-power cold boot with
  USB disconnected: validator created `cmd-000017`, observed raw-frame ACK
  `seq=5`, `transport.type=lte`, `lte_http.phase=command_ack`,
  `lte_http.poll_reason_code=LTE_HTTP_OK`, HTTP status `200`, action elapsed
  `450 ms`, `command.parse_status=raw_command_selected`, and command status
  `ok`. Runtime evidence is under
  `reports/field_validation/fw003-raw-command-loop-20260629-175608/`.
- RAW-LTE-REPEAT-001 attempt 1 then passed as a short USB-Free repeat after an
  operator-confirmed independent-power cold boot with USB disconnected. The
  first validator invocation created `cmd-000018` and saw a healthy raw LTE
  ACK, then returned a false-negative due to ACK `test_run_id` comparison
  semantics. Reconciliation reused existing `cmd-000018` without queueing a new
  command and passed with `transport.type=lte`,
  `lte_http.phase=command_ack`, `LTE_HTTP_OK` / HTTP `200`,
  `command.parse_status=raw_command_selected`, and command/ACK status `ok`.
  Evidence is under
  `reports/field_validation/raw-lte-repeat-001-a1-20260629-190720/`.
- RAW-LTE-REPEAT-001 attempt 2 passed after a separate operator-confirmed
  independent-power cold boot with USB disconnected. Validator test run
  `raw-lte-repeat-001-a2-20260629-210939` created `cmd-000019` and observed a
  raw LTE ACK with `seq=7`, `transport.type=lte`,
  `lte_http.phase=command_ack`, `LTE_HTTP_OK` / HTTP `200`,
  `poll_action_elapsed_ms=680`, `command.parse_status=raw_command_selected`,
  `command.command_count=1`, and command/ACK status `ok`. Evidence is under
  `reports/field_validation/raw-lte-repeat-001-a2-20260629-210939/`. With
  attempts 1 and 2 both passed, the short USB-Free raw LTE repeat gate is
  satisfied; long LTE stability, reconnect recovery, GNSS-over-LTE, battery,
  power, and enclosure behavior remain unverified.
- LTE-004 raw LTE request-location thin slice is implemented, VPS-deployed, and
  build-verified as `0.1.0-lte004-raw-lte-location` /
  `lte004-raw-lte-location-20260629-213717`. Firmware now accepts
  `request_location` in the raw LTE command loop, uploads an `EGLK/1
  type=event` key/value `location_report` to `/raw-ingest`, and then posts the
  raw ACK. Message Hub derives Web/API `location_report` fields only after
  storing the raw frame. VPS smoke
  `lte004-vps-raw-location-smoke-20260629-133701` derived
  `event_type=location_report`, `fix=false`, `gnss_state=no_fix`,
  `transport.type=lte`, and `location_request_cmd_id=cmd-smoke-000001` from a
  synthetic raw event without touching GitLab. The binary is
  `firmware/mqtt_heartbeat/build_lte004_raw_lte_location/egolink_mqtt_heartbeat.bin`,
  and its size is `296112` bytes. Focused tests passed with 36 tests,
  `context_lint`, full `verify.ps1` with 282 tests, `git diff --check`, and
  guarded ESP-IDF prepare/build all passed. This build record was followed by
  the flash and USB-Free runtime evidence below.
- LTE-004 was flashed on `COM4` after explicit operator confirmation. Board
  probe evidence `reports/board_validation/20260630-075007/probe.md`
  identified `COM4` as the ESP32-S3 CH343 console and SIM7670G AT candidates
  `COM6` / `COM7` as registered/attached. Flash evidence is at
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/flash_report.md`.
  `esptool.py` detected ESP32-S3, wrote bootloader, app, and partition table,
  verified hashes, and hard reset the board.
- LTE-004 USB-Free runtime validation passed after the operator connected
  independent power and disconnected USB. Validator run
  `lte004-raw-lte-location-20260629-213717` created `cmd-000020`
  (`request_location`), required a matching LTE `location_report`, and passed.
  Derived raw location evidence: `seq=30`, raw frame `loc-cmd-000020`,
  `transport.type=lte`, `lte_http.phase=location_report`,
  `source=sim7670g_firmware_gnss`, `source_status=unverified`,
  `gnss_query_ok=true`, `gnss_state=no_fix`, `fix=false`, and
  `location_request_cmd_id=cmd-000020`. Raw ACK evidence: `seq=31`,
  `lte_http.phase=command_ack`, `LTE_HTTP_OK` / HTTP `200`,
  `poll_action_elapsed_ms=560`, `command.parse_status=raw_command_selected`,
  and command/ACK status `ok`. Evidence is under
  `reports/field_validation/lte004-raw-lte-location-20260629-213717/`. This
  proves the bounded raw LTE `request_location -> location_report -> ACK`
  slice only; real GNSS fix, long LTE stability, reconnect recovery, battery,
  power, and enclosure behavior remain unverified.
- LOC-004A real cell location observation is implemented, VPS-deployed,
  build-verified as `0.1.0-loc004a-cell-observation` /
  `loc004a-cell-observation-20260630-001`, flashed on `COM4` after explicit
  operator confirmation, and reconciled as a bounded USB-Free runtime PASS
  after an independent-power reboot with USB disconnected. Message Hub derives
  raw
  `event_type=location_observation` key/value frames into `cell`, `lte`,
  `transport`, `lte_http`, and `location_belief` fields after raw storage.
  Unknown observations preserve existing useful `location_memory` and can
  derive active belief `Predicted` with reason
  `last_known_after_unknown_location_observation`. VPS smoke
  `loc004a-vps-cell-observation-smoke-20260630-012442` passed with
  `cell.rat=LTE`, `cell.cell_id=01AF23`,
  `lte.reason_code=LTE_READY`, `transport.type=lte`, and
  `location_belief.state=Unknown`; evidence is under
  `reports/location_observation/loc004a-vps-cell-observation-smoke-20260630-012442/`.
  The build used `CONFIG_EGOLINK_SIM7670_GNSS_ENABLED=y`,
  `CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED=y`,
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_COMMAND_LOOP_ENABLED=y`, and
  `CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED=y`; binary is
  `firmware/mqtt_heartbeat/build_loc004a_cell_observation/egolink_mqtt_heartbeat.bin`
  (`298416` bytes). Focused tests passed with 50 tests, `context_lint` passed,
  full `verify.ps1` passed with 292 tests, `git diff --check` passed, and the
  guarded ESP-IDF prepare/build passed.
- LOC-004A flash evidence is recorded at
  `reports/field_validation/loc004a-cell-observation-20260630-001/flash_report.md`.
  `esptool.py` detected ESP32-S3 QFN56 rev v0.2 on `COM4`, wrote bootloader,
  app, and partition table, verified hashes, and completed hard reset.
- LOC-004A USB-Free runtime evidence is reconciled as PASS after the operator
  rebooted the connectivity node on independent power with USB disconnected.
  The device consumed pending command `cmd-000021` and produced raw
  `location_report` frame `loc-cmd-000021` (`seq=2`, `fix=false`,
  `gnss_state=no_fix`, `gnss_query_ok=true`, `transport.type=lte`), raw
  `location_observation` frame `obs-cmd-000021` (`seq=3`,
  `cell.rat=LTE`, `cell.cell_id=180571649`, `cell.rsrp=-98`,
  `lte.reason_code=LTE_READY`, assigned IP `10.91.147.246`,
  `location_belief.state=Unknown`, `transport.type=lte`), and raw ACK
  `cmd-000021` (`seq=4`, status `ok`, `LTE_HTTP_OK` / HTTP `200`). Evidence
  is under
  `reports/field_validation/loc004a-cell-observation-runtime-20260630-001/`.
  A later stale `cmd-000022` from the second validator attempt was cancelled
  server-side and is not hardware evidence. This validates only the bounded
  raw LTE `request_location -> location_report -> location_observation -> ACK`
  slice; long LTE stability, reconnect recovery, cell-only positioning,
  battery/power, and product readiness remain unverified.
- FIELD-002A then passed a reboot-aware USB-Free validator smoke against the
  same LOC-004A firmware without flashing. The validator armed `cmd-000023`
  under `loc004a-reboot-aware-20260630-001`, the operator rebooted on
  independent power with USB disconnected, and reconciliation reused
  `cmd-000023` with command-created evidence anchoring. The run produced raw
  `location_report` frame `loc-cmd-000023` (`seq=2`, `fix=false`,
  `gnss_state=no_fix`, `transport.type=lte`), raw `location_observation`
  frame `obs-cmd-000023` (`seq=3`, `cell.rat=LTE`,
  `cell.cell_id=180571649`, `cell.rsrp=-97`, `lte.reason_code=LTE_READY`,
  assigned IP `10.31.138.19`, `location_belief.state=Unknown`), and raw ACK
  `cmd-000023` (`seq=4`, status `ok`, `LTE_HTTP_OK` / HTTP `200`). Evidence
  is under `reports/field_validation/loc004a-reboot-aware-20260630-001/`.
  This validates the FIELD-002 arm/reboot/reconcile workflow on one real
  USB-Free command; it is not a long LTE stability or product readiness claim.
- LOC-005A source-state firmware has been build-verified, VPS-deployed, and
  flashed on `COM4` as `0.1.0-loc005a-source-states` /
  `loc005a-source-states-20260630-001`. It adds explicit Wi-Fi/IMU/power
  source-state slots to raw LTE `location_observation` while preserving
  raw-frame/KV transport. Flash evidence is under
  `reports/field_validation/loc005a-source-states-20260630-001/flash_report.md`.
  `esptool.py` detected ESP32-S3 QFN56 rev v0.2, wrote bootloader, app
  (`300448` bytes), and partition table, verified hashes, and hard-reset the
  board. USB-Free runtime validation passed after the operator rebooted the
  board on independent power with USB disconnected and the validator
  reconciled existing `cmd-000024`. Evidence is under
  `reports/field_validation/loc005a-source-states-20260630-001/`:
  raw LTE `location_report seq=2` (`fix=false`, `gnss_state=no_fix`,
  `transport.type=lte`), raw LTE `location_observation seq=3`
  (`cell.cell_id=180571649`, `lte.reason_code=LTE_READY`,
  `wifi.source_status=disabled`, `imu.source_status=unverified`,
  `power.source_status=mock`, `transport.type=lte`), and raw LTE ACK `seq=4`
  (`cmd_id=cmd-000024`, status `ok`, `LTE_HTTP_OK` / HTTP `200`).
- LTE-006 fix1 reliability non-claim firmware has been implemented,
  build-verified, flashed on `COM4`, and USB-Free runtime validated as
  `0.1.0-lte006-reliability-nonclaim-fix1` /
  `lte006-reliability-nonclaim-fix1-20260701-001`. It compacts the raw LTE
  `location_observation` payload to stay below the known SIM7670G large HTTP
  payload risk range while preserving network state, cache non-claim, source
  state, transport, and belief explanation fields. Flash on `COM4` passed
  after explicit operator confirmation; `esptool.py` detected ESP32-S3 QFN56
  rev v0.2, wrote bootloader, app (`299824` bytes), and partition table, and
  verified hashes. USB-Free runtime validation passed after the operator
  connected independent power and disconnected USB. Evidence is under
  `reports/field_validation/lte006-reliability-nonclaim-fix1-20260701-001/`:
  raw LTE `location_report seq=60` (`fix=false`, `gnss_state=no_fix`,
  `transport.type=lte`), raw LTE `location_observation seq=61`
  (`cell.cell_id=180571649`, `lte.reason_code=LTE_READY`, assigned IP
  `10.141.88.185`, `wifi.source_status=disabled`,
  `imu.source_status=unverified`, `power.source_status=mock`,
  `location_belief.state=Unknown`, `transport.type=lte`), and raw LTE ACK
  `seq=62` (`cmd_id=cmd-000026`, status `ok`, `LTE_HTTP_OK` / HTTP `200`).
  LTE-005 over the fix1 export returns expected `WARN` because real cache/drop
  evidence remains absent; this is not a long LTE stability, reconnect
  recovery, durable cache, or product-readiness claim.
- LTE-007 volatile cache/drop observability firmware has been implemented,
  build-verified, flashed on `COM4`, and USB-Free runtime validated. Firmware
  version `0.1.0-lte007-volatile-cache-observe` / test run
  `lte007-volatile-cache-20260701-001` builds to
  `firmware/mqtt_heartbeat/build_lte007_volatile_cache_observe/egolink_mqtt_heartbeat.bin`
  (`301056` bytes). Flash on `COM4` passed after explicit operator
  confirmation; `esptool.py` detected ESP32-S3 QFN56 rev v0.2, wrote
  bootloader, app, and partition table, and verified hashes. Local flash
  evidence is under
  `reports/field_validation/lte007-volatile-cache-20260701-001/flash_report.md`.
  USB-Free runtime validation passed after independent-power/USB-disconnected
  reboot using existing command `cmd-000028`: raw LTE `location_report seq=2`,
  raw LTE `location_observation seq=3`, and raw LTE ACK `seq=4` all arrived
  with LTE transport and matching test run ID. The VPS/Web deployment now
  derives `reliability.network/cache` from LTE-007 raw KV fields; the
  observation reported `cache_state=volatile_outbox`, zero queued/dropped
  messages, `cache_last_drop_reason=none`, and raw POST `1/1/0`, while ACK
  reported raw POST `2/2/0`. This is not durable offline cache, reconnect
  recovery, long LTE stability, or product-readiness evidence.
- LTE-008 bounded raw POST retry observability has been implemented,
  build-verified, flashed on `COM4`, failed once in an explainable way, and
  passed USB-Free runtime after the fix1 payload compaction.
  Firmware
  version `0.1.0-lte008-bounded-raw-retry` / test run
  `lte008-bounded-raw-retry-20260701-001` builds to
  `firmware/mqtt_heartbeat/build_lte008_bounded_raw_retry/egolink_mqtt_heartbeat.bin`
  (`301824` bytes) with
  `CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_RETRY_MAX=1`,
  SIM7670G GNSS enabled, LTE status enabled, raw LTE command loop enabled, and
  location observation enabled. The image retries one failed raw-frame LTE HTTP
  POST within the current boot before final drop accounting, and reports
  `cache_retry_policy=single_retry_current_boot` plus retry attempt/success/
  failure counters in raw LTE `location_observation` and ACK payloads. Flash
  evidence is under
  `reports/field_validation/lte008-bounded-raw-retry-20260701-001/flash_report.md`.
  The first USB-Free runtime validation attempt failed in an explainable way:
  command `cmd-000029` produced raw LTE `location_report seq=4` and raw LTE
  ACK `seq=6`, but ACK status was `error` with message
  `lte raw location_observation upload failed`, cache drop reason
  `location_observation_payload_truncated`, and evidence under
  `reports/field_validation/lte008-bounded-raw-retry-20260701-001/`.
  LTE-008 fix1 is build-verified as
  `0.1.0-lte008-bounded-raw-retry-fix1` /
  `lte008-bounded-raw-retry-fix1-20260701-001`, binary
  `firmware/mqtt_heartbeat/build_lte008_bounded_raw_retry_fix1/egolink_mqtt_heartbeat.bin`
  (`301680` bytes). The fix1 image was flashed on `COM4` after explicit
  operator confirmation; ESP32-S3 QFN56 rev v0.2 was detected, app size was
  `301680` bytes, hashes were verified, and flash evidence is under
  `reports/field_validation/lte008-bounded-raw-retry-fix1-20260701-001/flash_report.md`.
  USB-Free runtime validation then passed with command `cmd-000030`: raw LTE
  `location_report seq=15`, raw LTE `location_observation seq=16`, and raw
  LTE ACK `seq=17` reached the VPS with matching firmware/test-run IDs,
  `transport.type=lte`, `cache_retry_policy=single_retry_current_boot`,
  retry counters `0/0/0`, and ACK status `ok`. Evidence is under
  `reports/field_validation/lte008-bounded-raw-retry-fix1-20260701-001/`.
  This is not actual retry-after-failure, durable offline cache, reconnect
  recovery, long LTE stability, or product-readiness evidence.
- LTE-009 raw POST retry fault injection has been implemented, VPS-deployed,
  flashed on `COM4`, and USB-Free runtime validated as
  `0.1.0-lte009-raw-post-retry-fault` /
  `lte009-raw-post-retry-fault-20260701-001`. It adds a default-off firmware
  test switch, `CONFIG_EGOLINK_SIM7670_LTE_HTTP_RAW_POST_FAIL_ONCE_TEST`, and
  a Message Hub fail-once raw-ingest path that retains the first marked raw
  frame as `injected_failure` before returning HTTP 503. The binary is
  `firmware/mqtt_heartbeat/build_lte009_raw_post_retry_fault/egolink_mqtt_heartbeat.bin`
  (`301776` bytes). It was rebuilt during the flash with app version `88945b9`.
  The updated Message Hub was deployed to the VPS after commit
  `10e28fe`; `/health`, unauthenticated `/api/state` = `401`,
  authenticated `/api/state`, and a VPS-local in-memory fail-once smoke all
  passed. Flash evidence is under
  `reports/field_validation/lte009-raw-post-retry-fault-20260701-001/flash_report.md`.
  USB-Free runtime validation passed after the operator connected independent
  power and disconnected USB: validator command `cmd-000031` produced retained
  raw LTE `location_report` frame `loc-cmd-000031` first as
  `injected_failure`, then as retry `ok`, followed by raw LTE
  `location_observation seq=28` and raw LTE ACK `seq=29`. Retry evidence showed
  `cache_retry_policy=single_retry_current_boot`, retry counters `1/1/0`, and
  final raw POST counters `3/2/1`. Evidence is under
  `reports/field_validation/lte009-raw-post-retry-fault-20260701-001/`.
- LTE-011 reconnect/store-forward evidence test mode has been build-verified
  and flashed on `COM4` as `0.1.0-lte011-reconnect-store-forward-test` /
  `lte011-reconnect-store-forward-test-20260702-001`. It adds default-off
  `CONFIG_EGOLINK_SIM7670_LTE_RECONNECT_STORE_FORWARD_TEST`, script support
  for `-EnableReconnectStoreForwardTest`, raw LTE
  `network_reconnect_*` / `cache_flush_*` evidence fields, and Message Hub /
  Dashboard derivation for Cache Flush. Focused firmware/script/server/
  dashboard tests passed with 51 tests. Guarded ESP-IDF build passed and
  produced
  `firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test/egolink_mqtt_heartbeat.bin`
  (`302496` bytes). Flash on `COM4` passed after explicit operator
  confirmation; ESP32-S3 QFN56 rev v0.2, MAC `02:00:00:00:00:03`, was
  detected and bootloader/app/partition-table hashes were verified. Flash
  evidence is under
  `reports/field_validation/lte011-reconnect-store-forward-test-20260702-001/flash_report.md`.
  USB-Free runtime validation then failed in an explainable way. After an
  independent-power reboot with USB disconnected, command `cmd-000032`
  produced raw LTE `location_report` frame `loc-cmd-000032` (`seq=2`,
  `fix=false`, `gnss_state=no_fix`) and raw LTE ACK `seq=4`, but command
  status was `error` because the raw LTE `location_observation` frame was
  dropped before POST with
  `cache_last_drop_reason=location_observation_payload_truncated`. Evidence is
  under
  `reports/field_validation/lte011-reconnect-store-forward-test-20260702-001/`.
  LTE-011 fix1 is build-verified as
  `0.1.0-lte011-reconnect-store-forward-test-fix1` /
  `lte011-reconnect-store-forward-test-fix1-20260702-001`. It increases only
  the raw LTE `location_observation` local payload/frame buffers to
  `2050`/`2400` bytes; focused firmware tests passed with 13 tests, and the
  guarded ESP-IDF build produced
  `firmware/mqtt_heartbeat/build_lte011_reconnect_store_forward_test_fix1/egolink_mqtt_heartbeat.bin`
  (`302528` bytes). Fix1 was then flashed on `COM4` after explicit operator
  confirmation; ESP32-S3 QFN56 rev v0.2, MAC `02:00:00:00:00:03`, was
  detected and bootloader/app/partition-table hashes were verified. Flash
  evidence is under
  `reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/flash_report.md`.
  USB-Free runtime validation passed after the operator connected independent
  power and disconnected USB: command `cmd-000033` produced raw LTE
  `location_report` frame `loc-cmd-000033` (`seq=28`, `fix=false`,
  `gnss_state=no_fix`), raw LTE `location_observation` frame
  `obs-cmd-000033` (`seq=29`, `cell.cell_id=180571649`,
  `lte.reason_code=LTE_READY`, assigned IP `10.55.187.235`), and raw LTE ACK
  `seq=30` (`status=ok`, `LTE_HTTP_OK` / HTTP `200`). LTE-011 test-mode
  reliability evidence showed reconnect count `1`, reason `pdp_reactivate`,
  network failure reason `LTE_HTTP_ACTION_FAILED`, store-forward queue count
  `1`, oldest age `12000 ms`, and then ACK-side cache queue drained to `0`.
  Evidence is under
  `reports/field_validation/lte011-reconnect-store-forward-test-fix1-20260702-001/`.
  The LTE-010 offline reconnect/store-forward evidence gate then returned
  PASS over the export, with report under
  `reports/lte_reconnect_store_forward/lte011-fix1-20260702-001/`. This is a
  test-mode evidence pass and does not prove real modem reconnect recovery,
  durable local storage, queue replay, long LTE stability, GNSS acceptance,
  power behavior, enclosure behavior, or product readiness.
- Full Demo v0.5 audio evidence is structured mock-only; real microphone capture and audio acceptance remain unverified.
- The latest Demo v0.3/v0.5 motion candidate can use real AMOLED QMI8658 `motion_event` evidence, but it is still a demo-only heuristic, not MotionNet output.
- Formal IMU product acceptance remains false until final mounting/calibration gates are met.

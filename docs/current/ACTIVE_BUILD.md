---
document_status: authoritative
last_verified: 2026-06-29
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
| `connectivity_node` | Waveshare ESP32-S3-SIM7670G-4G | CH343 ESP32 console recently `COM4`, SIM7670G USB AT ports recently `COM5`/`COM6`/`COM7`/`COM8` | FW-003 raw-frame command-loop firmware currently flashed on COM4; USB-Free FW-003 raw command/ACK validation passed |

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
- Full Demo v0.5 audio evidence is structured mock-only; real microphone capture and audio acceptance remain unverified.
- The latest Demo v0.3/v0.5 motion candidate can use real AMOLED QMI8658 `motion_event` evidence, but it is still a demo-only heuristic, not MotionNet output.
- Formal IMU product acceptance remains false until final mounting/calibration gates are met.

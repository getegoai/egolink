---
document_status: current_task_tree
generated_at: 2026-06-27
generated_by: codex
---

# EGOLINK Task Tree

This tree records the current task structure from the local repository state.
It does not move, delete, or rewrite task packets.

## Root Objective

EGOLINK P0 proves an AI-assisted active safety locator loop:

```text
motion candidate
-> PC Bridge receives event
-> AMOLED asks the user
-> user confirmation
-> location / communication evidence
-> complete safety event record
-> quality gate
-> replay without boards
```

## Control Plane

- `ENG-000 Repository context migration`
  - Status: completed as a local control-plane migration baseline.
  - Evidence: authoritative files are split into `docs/current/`,
    `docs/product/`, `docs/architecture/`, `docs/hardware/`, `docs/modeling/`,
    `docs/safety/`, module `AGENTS.md` files, and `scripts/context_lint.py`.
- `ENG-001 Control Plane Baseline`
  - Status: completed.
  - Evidence: `docs/current/PROJECT_SNAPSHOT.md`,
    `docs/tasks/TASK_TREE.md`, `docs/development/`, and
    `reports/dev_runs/ENG-001-control-plane-baseline.md`.
- `ENG-002 Control Plane Commit / Remote Policy`
  - Status: completed on local branch `task/ENG-002-control-plane-commit`.
  - Evidence: commits `12c79c0`, `a9270eb`, and `2194e58`.
  - Remote: none configured; no push performed.
- `ENG-003 Legacy Archive Review`
  - Status: completed on local branch `task/ENG-003-legacy-archive-review`.
  - Evidence: legacy documents were preserved under `docs/archive/` or exact
    current destinations before old paths were removed or redirected.
- `ENG-004 Generated Docs Review`
  - Status: completed on local branch
    `task/ENG-004-DEMO-005-generated-docs-gnss`.
  - Evidence: `docs/generated/CONTEXT_MIGRATION_REPORT.md` and
    `docs/generated/REPOSITORY_MAP.md` are versioned as generated,
    non-authoritative migration evidence.
- `ENG-005 P0 Dev Flow Baseline`
  - Status: completed as a documentation/control-plane baseline.
  - Evidence: `docs/development/DEV_FLOW.md`,
    `docs/development/VPS_MESSAGE_HUB.md`,
    `docs/development/PROTOCOL.md`, `docs/development/FIELD_TEST.md`,
    `docs/current/ROADMAP_EGOLINK_P0.md`, and
    `docs/architecture/adr/ADR-0001-usb-free-vps-message-hub.md`.
  - Boundary: records USB-Free, VPS Message-First, Demo-Driven,
    Contract-First Walking Skeleton flow; no firmware, simulator, server, web,
    or shared schema implementation changed.
- `ENG-006 Location/LTE/Stability Route Update`
  - Path: `docs/tasks/done/ENG-006_LOCATION_LTE_STABILITY_ROUTE_UPDATE.md`
  - Status: completed as a documentation/control-plane update.
  - Source-plan note: the user-provided planning draft called this `ENG-003`,
    but current authority already uses `ENG-003` for Legacy Archive Review.
  - Evidence: `docs/current/ROADMAP_EGOLINK_P0.md`,
    `docs/development/FIELD_TEST.md`,
    `docs/development/LOCATION_ENGINE.md`,
    `docs/development/LTE_TRANSPORT.md`,
    `docs/development/PROTOCOL.md`, and this task tree.
  - Boundary: updates R2.1-R3.2 route and gate definitions only; no long
    stability run, LTE transport run, hardware flash, or hardware action was
    performed by the route update.

## Active Queue

- `LTE-003 LTE HTTP Command Poll And ACK`
  - Path: `docs/tasks/active/LTE-003_LTE_HTTP_COMMAND_POLL_ACK.md`
  - Status: active.
  - Goal: prove the existing Message Hub command queue can be polled over
    SIM7670G LTE HTTP and that one harmless `set_report_interval` command can
    be ACKed back over LTE with USB disconnected at runtime.
  - Current evidence: build-verified and flashed as `0.1.0-lte003-command-loop` /
    `lte003-command-loop-20260628-210214`; binary at
    `firmware/mqtt_heartbeat/build_lte003_command_loop/egolink_mqtt_heartbeat.bin`.
    Flash evidence:
    `reports/field_validation/lte003-command-loop-20260628-210214/flash_report.md`.
    USB-Free runtime validation attempts 1 and 2 failed with `cmd-000013` still
    pending and no test-run messages under
    `reports/field_validation/lte003-command-loop-20260628-210214/`; attempt 2
    reused the pending command after an independent-power cold reboot. Fix1 is
    build-verified as `0.1.0-lte003-command-loop-fix1` /
    `lte003-command-loop-fix1-20260628-223454` with diagnostic LTE command
    telemetry, and flashed on `COM4`; flash evidence is under
    `reports/field_validation/lte003-command-loop-fix1-20260628-223454/flash_report.md`.
    Runtime validation failed with `cmd-000013` still pending and no ACK, but
    fix1 produced diagnostic `lte_http_command_diag` events showing LTE ready,
    poll HTTP status `200`, body length `592`, and `LTE_HTTP_READ_FAILED`.
    Fix2 is build-verified as `0.1.0-lte003-command-loop-fix2` /
    `lte003-command-loop-fix2-20260629-074709` with the SIM7670 AT response
    buffer increased to `1536`; it has not been flashed yet.

## USB-Free VPS Walking Skeleton Line

- `PROTO-001 Freeze P0.1 Message-Hub Contract`
  - Path: `docs/tasks/done/PROTO-001_MESSAGE_HUB_CONTRACT_BASELINE.md`
  - Status: completed.
  - Goal: turn current `egolink.p0.v1` status/event/command/ack behavior into
    a stable message-hub contract without breaking existing local MQTT and PC
    simulator tests.
  - Evidence: `shared/contracts/message_hub_status.schema.json`,
    `shared/contracts/message_hub_event.schema.json`,
    `shared/contracts/message_hub_command.schema.json`,
    `shared/contracts/message_hub_ack.schema.json`,
    `shared/contracts/message_hub_error.schema.json`, and
    `quality_tests/test_message_hub_contracts.py`.
- `SERVER-001 VPS Message Service Minimal Loop`
  - Path: `docs/tasks/done/SERVER-001_VPS_MESSAGE_SERVICE_MINIMAL_LOOP.md`
  - Status: completed as a local deployable service baseline.
  - Goal: run the minimal device registration, heartbeat/telemetry ingest,
    command queue, ACK tracking, and event storage service on the VPS without
    touching existing GitLab.
  - Evidence: `server/message_hub.py`, `scripts/run_message_hub.py`, and
    `quality_tests/test_message_hub_server.py`.
- `WEB-001 Device Status Dashboard`
  - Path: `docs/tasks/done/WEB-001_MESSAGE_HUB_DASHBOARD_BASELINE.md`
  - Status: completed as a message-hub dashboard baseline.
  - Goal: show online/stale status, latest location, GNSS state, last seen,
    command, ACK, and error summary from server data.
  - Evidence: `server/message_hub.py` built-in Dashboard state panels and
    `quality_tests/test_message_hub_dashboard.py`.
- `WEB-002A Dashboard Latest Location And Auth Visibility`
  - Path: `docs/tasks/done/WEB-002A_DASHBOARD_LATEST_LOCATION_AUTH_VISIBILITY.md`
  - Status: completed as a field-observation fix after FW-002A validation.
  - Goal: make the Dashboard distinguish API auth failures from no-data states
    and keep the latest `location_report` visible even after newer generic
    telemetry arrives.
  - Evidence: `server/message_hub.py` now returns `latest_location` in device
    state, Dashboard field state prefers it for GNSS/fix/source fields, VPS
    `/api/state` returned HTTP 401 without token and authenticated device state
    returned `location_report seq=4` for `ego-link-r1-connectivity-001`.
- `SIM-001 PC Simulator VPS Loop`
  - Path: `docs/tasks/done/SIM-001_PC_SIMULATOR_MESSAGE_HUB_LOOP.md`
  - Status: completed as a local R0 simulator client.
  - Goal: use PC Simulator as the R0 virtual device against the VPS path.
  - Evidence: `pc_simulator/message_hub_client.py`,
    `scripts/run_message_hub_simulator.py`, and
    `quality_tests/test_message_hub_client.py`.
- `DEPLOY-001 Message Hub VPS Deployment`
  - Path: `docs/tasks/done/DEPLOY-001_MESSAGE_HUB_VPS_DEPLOYMENT.md`
  - Status: completed on the operator-provided VPS.
  - Goal: run the USB-Free Message Hub as a public field-test service without
    touching existing GitLab or storing real credentials in the repository.
  - Evidence: active `egolink-message-hub.service`, bearer-token API gate,
    public `/health`, and PC Simulator VPS smoke device
    `ego-link-r0-vps-auth-smoke`.
- `FW-001 Firmware Message Hub HTTP Client Baseline`
  - Path: `docs/tasks/done/FW-001_FIRMWARE_MESSAGE_HUB_HTTP_CLIENT_BASELINE.md`
  - Status: completed as a build-verified firmware transport baseline.
  - Goal: keep local MQTT as the default while adding an opt-in HTTP VPS
    Message Hub client for register, heartbeat, telemetry, command polling,
    and ACK.
  - Evidence: default MQTT ESP-IDF build PASS, HTTP Message Hub opt-in ESP-IDF
    build PASS, and `quality_tests/test_mqtt_heartbeat_firmware.py`.
- `FW-001-HW-PREP R1 USB-Free Validation Kit`
  - Path: `docs/tasks/done/FW-001-HW-PREP_R1_USB_FREE_VALIDATION_KIT.md`
  - Status: completed as a host-side validation and evidence-prep baseline.
  - Goal: prepare the real R1 hardware run by adding `test_run_id` evidence
    binding, fixing Message Hub test-run export, and providing a script that
    creates a test run, waits for fresh heartbeat, queues one harmless command,
    waits for ACK, and writes JSON/Markdown evidence.
  - Evidence: `scripts/validate_fw001_hw_loop.py`,
    `quality_tests/test_fw001_hw_validation.py`, server export tests, and both
    default MQTT and HTTP opt-in ESP-IDF builds; updated Message Hub redeployed
    to the VPS with `/health` and test-run export smoke passing.
  - Boundary: no firmware flash, USB-disconnected run, GNSS, LTE, battery,
    camera, audio, or power validation was performed.
- `FW-001-HW-CONFIG R1 Local Config And Build`
  - Path: `docs/tasks/done/FW-001-HW-CONFIG_R1_LOCAL_CONFIG_AND_BUILD.md`
  - Status: completed as a local ignored config and build baseline.
  - Goal: generate `firmware/mqtt_heartbeat/sdkconfig.vps.local` from
    operator runtime values without writing secrets to tracked files, then
    build the HTTP Message Hub firmware with
    `sdkconfig.defaults;sdkconfig.vps.local`.
  - Evidence: `scripts/prepare_fw001_hw_config.ps1`,
    `quality_tests/test_fw001_hw_config.py`, ignored local config
    `firmware/mqtt_heartbeat/sdkconfig.vps.local`, and ignored R1 build
    artifact `firmware/mqtt_heartbeat/build_fw001_hw/egolink_mqtt_heartbeat.bin`.
  - Boundary: no firmware flash, USB-disconnected run, serial capture, GNSS,
    LTE, battery, camera, audio, or power validation was performed.
- `FW-001-HW-RUNNER R1 Guarded Hardware Runner`
  - Path: `docs/tasks/done/FW-001-HW-RUNNER_R1_GUARDED_HARDWARE_RUNNER.md`
  - Status: completed as a guarded operator entry point.
  - Goal: wrap R1 prepare/build, optional flash, and optional USB-Free
    validation behind explicit phase switches and hardware-safety confirmations.
  - Evidence: `scripts/run_fw001_hw_r1.ps1`,
    `quality_tests/test_fw001_hw_runner.py`, and plan-only runner smoke.
  - Boundary: no firmware flash, USB-disconnected run, serial capture, Message
    Hub validation command, GNSS, LTE, battery, camera, audio, or power
    validation was performed.
- `FW-001-HW Real Device USB-Free Heartbeat Validation`
  - Path: `docs/tasks/done/FW-001-HW_REAL_DEVICE_USB_FREE_HEARTBEAT_VALIDATION.md`
  - Status: completed as the real R1 USB-Free Message Hub validation run.
  - Goal: flash the connectivity node with a local ignored VPS config and prove
    boot/heartbeat plus command ACK through the VPS Message Hub with USB
    disconnected at runtime.
  - Evidence: `reports/field_validation/fw001-hw-r1-20260627-133813/field_validation_report.md`
    records PASS, test run `fw001-hw-r1-20260627-133813`, connection path
    `independent_power_usb_disconnected`, heartbeat `seq=7`, command
    `cmd-000003`, and ACK `seq=8`.
  - Boundary: validates the Wi-Fi HTTP Message Hub skeleton path only; real
    GNSS fix, SIM7670G LTE control, battery/charging accuracy, camera, audio,
    storage, and product power behavior remain separate tasks.
- `FW-002A GNSS Command/Telemetry Scaffold`
  - Path: `docs/tasks/done/FW-002A_GNSS_COMMAND_TELEMETRY_SCAFFOLD.md`
  - Status: completed as a build-verified command/telemetry scaffold.
  - Goal: make `request_location` produce an explicit `location_report` over
    the Message Hub, then ACK the command, before real SIM7670G GNSS control is
    integrated.
  - Evidence: `scripts/validate_fw002_location_loop.py`,
    `quality_tests/test_fw002_gnss_scaffold.py`, updated Dashboard GNSS fields,
    default MQTT build PASS, HTTP Message Hub build PASS with firmware version
    `0.1.0-fw002-location-scaffold`.
  - Boundary: no firmware flash or real hardware runtime validation was
    performed; the scaffold reports `fix=false`,
    `source_status=unverified`, and `gnss_state=driver_not_integrated`.
- `FIELD-001A FW-002A USB-Free Location Scaffold Validation`
  - Path: `docs/tasks/done/FIELD-001A_FW002A_USB_FREE_LOCATION_SCAFFOLD_VALIDATION.md`
  - Status: completed as a real-device USB-Free scaffold validation.
  - Goal: prove that FW-002A running on independent power receives
    `request_location`, uploads `location_report`, and ACKs through the VPS
    Message Hub with USB disconnected.
  - Evidence: `reports/field_validation/fw002-location-build-smoke/field_validation_report.md`
    records PASS, connection path `independent_power_usb_disconnected`,
    heartbeat `seq=3`, command `cmd-000004`, location report `seq=4`,
    `fix=false`, `gnss_state=driver_not_integrated`, and ACK `seq=5`.
  - Boundary: validates the location command/telemetry scaffold only; no real
    GNSS fix or SIM7670G GNSS/LTE firmware control is claimed.
- `FW-002B SIM7670G Firmware GNSS AT Backend`
  - Path: `docs/tasks/done/FW-002B_SIM7670G_FIRMWARE_GNSS_AT_BACKEND.md`
  - Status: completed as a build-verified firmware GNSS backend baseline.
  - Goal: replace the `driver_not_integrated` scaffold with an opt-in
    SIM7670G UART/AT backend behind the same `request_location` envelope.
  - Evidence: new `firmware/mqtt_heartbeat/components/sim7670_gnss/` backend,
    updated `request_location` payload fields, guarded build switch
    `-EnableSim7670Gnss`, default ESP-IDF build PASS, and HTTP + GNSS opt-in
    build PASS for firmware `0.1.0-fw002b-sim7670-gnss`.
  - Boundary: no FW-002B flash, USB-Free runtime validation, outdoor GNSS fix,
    or SIM7670G LTE data transport validation was performed.
- `FIELD-001B FW-002B USB-Free SIM7670G GNSS AT Validation`
  - Path: `docs/tasks/done/FIELD-001B_FW002B_USB_FREE_SIM7670_GNSS_AT_VALIDATION.md`
  - Status: completed as a real-device USB-Free firmware GNSS AT validation.
  - Goal: prove that FW-002B running on independent power receives
    `request_location`, queries the SIM7670G GNSS AT backend, uploads
    `location_report`, and ACKs through the VPS Message Hub with USB
    disconnected.
  - Evidence: `reports/field_validation/fw002b-fix1-gnss-r1-20260627-163246/field_validation_report.md`
    records PASS, connection path `independent_power_usb_disconnected`,
    heartbeat `seq=57`, command `cmd-000006`, location report `seq=58`,
    `source=sim7670g_firmware_gnss`, `gnss_source=sim7670g_uart_at`,
    `gnss_driver=uart_at`, `gnss_query_ok=true`, `fix=false`,
    `gnss_state=no_fix`, and ACK `seq=59`.
  - Boundary: validates firmware-side SIM7670G UART/AT no-fix diagnostics only;
    no outdoor real GNSS fix, real coordinates, or SIM7670G LTE data transport
    is claimed.
- `FIELD-001C FW-002C USB-Free SIM7670G GNSS Real-Fix Validation`
  - Path: `docs/tasks/done/FIELD-001C_FW002C_USB_FREE_SIM7670_GNSS_REAL_FIX_VALIDATION.md`
  - Status: completed as the first USB-Free firmware-side SIM7670G real-fix
    validation.
  - Goal: prove that the connectivity node can receive `request_location`,
    query the SIM7670G firmware UART/AT backend, upload a fixed
    `location_report`, and ACK through the VPS Message Hub with USB
    disconnected.
  - Evidence:
    `reports/field_validation/fw002c-fix3-window-gnss-retry1-20260628-093946/field_validation_report.md`
    records PASS, connection path `independent_power_usb_disconnected`, fresh
    heartbeat `seq=30`, command `cmd-000012`, `location_report seq=31`,
    `fix=true`, `gnss_state=fix`, `source=sim7670g_firmware_gnss`,
    `source_status=observed`, `gnss_source=sim7670g_uart_at`,
    `gnss_driver=uart_at`, `gnss_query_ok=true`, and ACK `seq=33`.
  - Boundary: validates GNSS fix over the Wi-Fi HTTP VPS Message Hub path only;
    SIM7670G LTE data transport, battery accuracy, product power behavior, and
    final enclosure/mounting GNSS acceptance remain separate tasks.
- `OBS-001 Unified Observability Envelope Baseline`
  - Path: `docs/tasks/done/OBS-001_UNIFIED_OBSERVABILITY_ENVELOPE_BASELINE.md`
  - Status: completed as a server/web/protocol baseline.
  - Goal: make failures explainable before long stability, LTE, power, or
    enclosure gates.
  - Evidence: `/api/state` device rows now include derived `observability`
    for transport, runtime, command, power, GNSS, cell, and reason codes;
    test-run export includes `observability_summary`; the Dashboard renders
    the new state; optional contract fields were added to
    `message_hub_status.schema.json` and `message_hub_event.schema.json`.
  - Boundary: OBS-001 is additive and compatible with existing
    `egolink.p0.v1` messages. It does not prove LTE data transport, battery
    accuracy, long-run reliability, or enclosure GNSS performance.
- `LOC-002 Location Observation Contract Baseline`
  - Path: `docs/tasks/done/LOC-002_LOCATION_OBSERVATION_CONTRACT_BASELINE.md`
  - Status: completed as a protocol/server/web/simulator baseline.
  - Goal: add multi-source `location_observation` evidence without replacing
    the existing `request_location -> location_report -> ACK` loop.
  - Evidence: `docs/development/PROTOCOL.md` documents
    `event_type=location_observation`; `message_hub_event.schema.json`
    includes optional `wifi`, `imu`, and `location_belief`; PC Simulator
    uploads a mock `location_observation`; `/api/state` exposes
    `latest_location_observation`, treats it as `latest_location`, and derives
    `observability.location_belief`; Dashboard renders location state,
    belief confidence/radius/source/reason, Wi-Fi, and IMU state.
  - Boundary: no firmware-side cell, Wi-Fi, IMU fusion, battery accuracy,
    location-memory table, rule-engine, LTE transport, or hardware action is
    claimed by this task.
- `STAB-001A Short Baseline Gate Tooling`
  - Path: `docs/tasks/done/STAB-001A_SHORT_BASELINE_GATE_TOOLING.md`
  - Status: completed as gate tooling only.
  - Goal: make the next short USB-Free baseline run judgeable from VPS/Web
    evidence instead of serial logs.
  - Evidence: PC Simulator can bind heartbeat, `location_report`,
    `location_observation`, ACK, and export evidence to one `test_run_id`;
    `scripts/validate_message_hub_stability.py` can require
    `location_observation`, `observability`, `location_belief`, command ACK,
    and test-run export availability.
  - Boundary: no hardware stability pass, long run, LTE transport, firmware
    flash, or serial capture is claimed by this task.
- `LTE-001A LTE Registration Cell Observability Baseline`
  - Path: `docs/tasks/done/LTE-001A_LTE_REGISTRATION_CELL_OBSERVABILITY_BASELINE.md`
  - Status: completed as a build-verified firmware/server/protocol baseline.
  - Goal: expose SIM7670G LTE registration, SIM, APN/PDP, assigned-IP, cell
    fingerprint, signal, raw AT summary, and reason-code state before using
    LTE as the product transport.
  - Evidence: firmware adds opt-in `CONFIG_EGOLINK_SIM7670_LTE_STATUS_ENABLED`
    and optional `cell` / `lte` upload fragments; Message Hub derives
    `observability.lte`; Dashboard renders LTE registration/PDP/SIM/reason;
    contracts and docs list optional `lte` fields.
  - Boundary: no firmware flash, USB-Free hardware validation, Wi-Fi-disable
    run, `transport.type=lte`, DNS over LTE, HTTP over LTE, or LTE command loop
    is claimed by this task.
- `LTE-001B USB-Free LTE Status Observation`
  - Path: `docs/tasks/done/LTE-001B_USB_FREE_LTE_STATUS_OBSERVATION.md`
  - Status: completed.
  - Goal: flash the LTE-status observability image and validate that a real
    USB-disconnected device reports `observability.lte` with a known `LTE_*`
    reason code through the VPS Message Hub.
  - Evidence: after the original `0.1.0-lte001b-observe` image registered but
    failed to produce a fresh status heartbeat, fix1 moved LTE observation
    fragments out of heartbeat/sensor task stack and raised both task stacks to
    12288 bytes. The fix1 image `0.1.0-lte001b-observe-fix1` passed USB-Free
    Message Hub validation with `reason_code=LTE_READY`,
    `registration_state=registered_home`, `pdp_state=active`, assigned IP
    present, RAT `LTE`, and cell/signal metrics under
    `reports/field_validation/lte001b-observe-fix1-20260628-131739/`.
  - Boundary: LTE status observation only. No LTE HTTP transport,
    `transport.type=lte`, Wi-Fi-disable run, LTE command loop, battery,
    charging, power, or long-run LTE stability claim belongs to this task.
- `LTE-002 LTE HTTP Uplink Thin-Slice`
  - Path: `docs/tasks/done/LTE-002_LTE_HTTP_UPLINK_THIN_SLICE.md`
  - Status: completed.
  - Goal: send a bounded `lte_http_probe` telemetry event through SIM7670G LTE
    HTTP to the VPS Message Hub, with `transport.type=lte` visible in
    `/api/state`.
  - Evidence: fix5 USB-Free validation passed after independent-power
    power-cycle with USB disconnected: `transport.type=lte`,
    `lte_http.reason_code=LTE_HTTP_OK`, HTTP status `200`, LTE `LTE_READY`,
    assigned IP `10.160.15.113`, and cell ID `180571649`; evidence under
    `reports/field_validation/lte002-lte-http-probe-fix5-20260628-193815/`.
  - Boundary: this proves one LTE HTTP telemetry uplink thin-slice only. No
    LTE command polling, ACK migration, reconnect supervisor, long-run
    stability, battery, power, or product LTE acceptance belongs to this task.
- `RELIABILITY-001A USB-Free Stability Observer And Reset Diagnostics`
  - Path: `docs/tasks/done/RELIABILITY-001A_USB_FREE_STABILITY_OBSERVER_RESET_DIAGNOSTICS.md`
  - Status: completed as an R3 preflight diagnosability increment.
  - Goal: observe USB-Free Message Hub stability without serial logs or
    downlink commands, then add firmware reset diagnostics for the next image.
  - Evidence: `scripts/validate_message_hub_stability.py`,
    `quality_tests/test_message_hub_stability_validation.py`, additive
    `reset_reason` / `boot_count` / `boot_uptime_ms` fields in firmware and
    contracts, and build artifact
    `firmware/mqtt_heartbeat/build_fw002c_resetdiag/egolink_mqtt_heartbeat.bin`.
  - Live observation: `reports/field_validation/stability-fw002b-fix1-20260627-170758/stability_observation_report.md`
    records FAIL, with one seq regression from `125` to `1` at
    `2026-06-27T09:08:26Z`.
  - Boundary at completion: FW-002C reset diagnostics were build-verified only;
    subsequent flash/runtime validation is recorded in `RELIABILITY-001B`.
- `RELIABILITY-001B FW-002C USB-Free Reset Diagnostics Validation`
  - Path: `docs/tasks/done/RELIABILITY-001B_FW002C_USB_FREE_RESET_DIAGNOSTICS_VALIDATION.md`
  - Status: completed as a real-device USB-Free reset-diagnostics validation
    and short stability fix.
  - Goal: flash FW-002C reset diagnostics, diagnose the reset cause through VPS
    messages, and produce a passing command-free stability observation.
  - Evidence: FW-002C fix1
    `reports/field_validation/stability-fw002c-resetdiag-fix1-20260627-181600/stability_observation_report.md`
    records FAIL with repeated `panic` resets and 10 sequence regressions.
    FW-002C fix2
    `reports/field_validation/stability-fw002c-resetdiag-fix2-20260627-183100/stability_observation_report.md`
    records PASS over 120 seconds with 15 messages, `seq` 11 to 25,
    `seq_regressions=0`, max message gap 11.547434 seconds, and reset
    diagnostics showing `reset_reason=poweron`.
  - Boundary: validates the short Wi-Fi HTTP Message Hub stability gate only;
    no outdoor GNSS fix, SIM7670G LTE data transport, battery accuracy, or
    product power behavior is claimed.

## Demo-First Product Loop

- `DEMO-001 AMOLED IMU Confirmation Loop`
  - Path: `docs/tasks/done/DEMO-001_AMOLED_IMU_CONFIRMATION_LOOP.md`
  - Status: completed.
  - Result: real AMOLED/QMI8658 motion event, ask_user render, touch
    confirmation, PC safety event record.
- `DEMO-004 Full Demo Orchestrator`
  - Path: `docs/tasks/done/DEMO-004_FULL_DEMO_ORCHESTRATOR.md`
  - Status: completed.
  - Result: full Demo v0.5 runner with AMOLED evidence, SIM7670G GNSS/AT
    evidence, mock-only audio, recording, quality gate, and replay.
- `DEMO-005 Real GNSS Fix Evidence`
  - Status: completed as USB-Free firmware-side SIM7670G real-fix evidence.
  - Goal: capture bounded real `fix=true` SIM7670G GNSS evidence and replay it
    through the full demo.
  - Current evidence:
    `reports/field_validation/fw002c-fix3-window-gnss-retry1-20260628-093946/field_validation_report.md`
    records PASS with `fix=true`, `gnss_state=fix`,
    `source_status=observed`, and ACK through the VPS Message Hub with USB
    disconnected. Exact coordinates are retained only in ignored evidence
    exports, not copied into current docs.
- `DEMO-006 Real Audio Chain Bring-Up`
  - Status: proposed.
  - Goal: replace mock-only audio evidence with accepted microphone evidence
    while preserving privacy gates.
- `DEMO-007 Stability / Reconnect / Long-Run Demo Gate`
  - Status: proposed.
  - Goal: repeat full demo under bounded reconnect/retry/longer capture windows.

## Hardware Evidence Line

- `TIMU-009C-B2 QMI8658 Labeled Fixture Repeatability Capture`
  - Path: `docs/tasks/done/TIMU-009C-B2_QMI8658_LABELED_FIXTURE_REPEATABILITY_CAPTURE.md`
  - Status: done.
  - Boundary: temporary fixture evidence only; formal IMU acceptance remains
    false.
- `TIMU-009C-B3 Equivalent Calibration Pose Set Or FIFO/DRDY Preflight`
  - Status: suggested by prior task record.
  - Goal: add labeled fixture pose evidence or interrupt-path evidence.
- Camera smoke evidence
  - Status: completed in history and status docs.
  - Boundary: not yet product camera path.
- SIM7670G GNSS / 4G evidence
  - Status: PC-side AT/GNSS no-fix evidence and FW-002B firmware-side
    UART/AT no-fix evidence exist.
  - Needed: outdoor real fix and LTE data transport remain separate tasks.
- Audio / microphone evidence
  - Status: mock-only in full demo.
  - Needed: real microphone path and privacy-preserving acceptance gate.

## Data, Quality, And Replay

- Session recording
  - Status: implemented.
  - Current role: converts event logs into structured recording directories.
- Quality gate
  - Status: implemented.
  - Current role: file integrity, source boundary, privacy, and schema checks.
- Replay
  - Status: implemented.
  - Current role: rebuilds model inputs and verifies deterministic Safety
    Companion behavior from recordings.
- Annotation CLI
  - Status: implemented.
  - Current role: can attach labels to recording targets.

## Architecture And Contracts

- P0 product scope
  - Authority: `docs/product/PRODUCT_CHARTER.md`,
    `docs/product/P0_SCOPE.md`.
- Current system topology
  - Authority: `docs/architecture/SYSTEM_OVERVIEW.md`,
    `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md`.
- Protocol and model contracts
  - Authority: `shared/contracts/`.
- ADR process
  - Authority: `docs/architecture/adr/README.md`.
  - Current state: only README/template observed in ADR directory.

## Current Recommended Execution Order

1. Use OBS-001 observability and LOC-002 `location_observation` as the entry
   condition for any longer field run.
2. STAB-001A gate tooling is ready. The next physical stability step is a
   short operator-confirmed USB-Free baseline run over the current Wi-Fi HTTP
   path; do not treat it as product LTE acceptance.
3. Start LTE-001/LTE-002/LTE-003 in thin slices: LTE registration and cell
   state, LTE HTTP telemetry uplink, then LTE HTTP command polling and ACK.
4. LOC-002 is complete as a contract/server/simulator baseline. Next location
   work is LOC-003 VPS location memory tables and LOC-004 rule-based
   `Fine`/`Coarse`/`Predicted`/`Unknown` belief engine after the short
   baseline gate and LTE thin-slices are in motion.

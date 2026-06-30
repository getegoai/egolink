---
document_status: current_task_tree
generated_at: 2026-06-30
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
- `REL-001 First Key Release Gate`
  - Path: `docs/tasks/done/REL-001_FIRST_KEY_RELEASE_GATE.md`
  - Status: completed.
  - Evidence: `docs/current/KEY_RELEASES.md`,
    `docs/current/key_releases/KR-001_USB_FREE_RAW_LTE_LOCATION.json`,
    `scripts/run_key_release_gate.py`, and gate reports under
    `reports/key_releases/KR-001/`.
  - Boundary: publishes an engineering key release gate only; no new hardware
    flash, runtime validation, long LTE stability, or product readiness claim.
- `REL-002 Explainable LTE Location Observation Release Gate`
  - Path:
    `docs/tasks/done/REL-002_EXPLAINABLE_LTE_LOCATION_OBSERVATION_RELEASE_GATE.md`
  - Status: completed.
  - Evidence: `docs/current/KEY_RELEASES.md`,
    `docs/current/key_releases/KR-003_EXPLAINABLE_LTE_LOCATION_OBSERVATION.json`,
    `scripts/run_key_release_gate.py`, and gate reports under
    `reports/key_releases/KR-003/`.
  - Boundary: publishes KR-003 as an engineering key release only; no new
    firmware flash, runtime validation, long LTE stability, reconnect,
    battery/power, enclosure behavior, or product readiness claim.
- `REL-004 Multi-Source Explainable Location Evidence Release Gate`
  - Path:
    `docs/tasks/done/REL-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE_RELEASE_GATE.md`
  - Status: completed as a KR-004 release-candidate gate.
  - Evidence: `docs/current/KEY_RELEASES.md`,
    `docs/current/key_releases/KR-004_MULTI_SOURCE_EXPLAINABLE_LOCATION_EVIDENCE.json`,
    `scripts/run_key_release_gate.py`, and gate reports under
    `reports/key_releases/KR-004/`.
  - Current visible result: VPS Message Hub identifies current
    `loc005a-source-states-20260630-001` as `KR-004` /
    `release_candidate`; EALE-P0 remains `Unknown` / `no_precise_fix`, DATA-001
    window readiness is `failure_window` / `candidate_with_warnings`, and
    training stays disabled.
  - Boundary: publishes a release-candidate gate only; no new firmware flash,
    runtime validation, model training, product readiness, positioning
    accuracy, long LTE stability, reconnect, GNSS acceptance, or battery/power
    claim.

## Active Queue

- `LTE-003 LTE HTTP Command Poll And ACK`
  - Path: `docs/tasks/active/LTE-003_LTE_HTTP_COMMAND_POLL_ACK.md`
  - Status: raw-frame acceptance passed through FW-003; legacy JSON
    command-poll path remains paused.
  - Goal: prove the existing Message Hub command queue can be polled over
    SIM7670G LTE HTTP-carried raw frames and that one harmless
    `set_report_interval` command can be ACKed back over LTE with USB
    disconnected at runtime.
  - Current evidence: FW-003 raw-frame firmware
    `0.1.0-fw003-raw-command-loop` /
    `fw003-raw-command-loop-20260629-175608` passed USB-Free runtime
    validation after independent-power cold boot with USB disconnected.
    Validator created `cmd-000017`, observed raw-frame ACK `seq=5`,
    `transport.type=lte`, `lte_http.phase=command_ack`,
    `lte_http.poll_reason_code=LTE_HTTP_OK`, HTTP status `200`,
    `command.parse_status=raw_command_selected`, and command status `ok`.
    Evidence is under
    `reports/field_validation/fw003-raw-command-loop-20260629-175608/`.
    Earlier JSON evidence: build-verified and flashed as `0.1.0-lte003-command-loop` /
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
    buffer increased to `1536`, rebuilt with app version `43f5f55`, and flashed
    on `COM4`. Flash evidence is under
    `reports/field_validation/lte003-command-loop-fix2-20260629-074709/flash_report.md`.
    USB-Free runtime validation failed after independent-power cold reboot with
    USB disconnected: the validator reused `cmd-000013`, the command remained
    pending, no ACK was received, and the latest diagnostic still reported HTTP
    poll status `200`, body length `592`, and `LTE_HTTP_READ_FAILED`.
- `RAW-LTE-REPEAT-001 Short USB-Free Raw LTE Repeat Validation`
  - Path: `docs/tasks/done/RAW-LTE-REPEAT-001_SHORT_USB_FREE_RAW_LTE_REPEAT.md`
  - Status: completed as a short repeat gate and archived under `done`;
    retained here as the immediate predecessor evidence for LTE-004.
  - Goal: repeat the FW-003 raw-frame command/ACK loop over a few short
    USB-Free cold-boot attempts before moving into long LTE stability or
    GNSS-over-LTE work.
  - Current evidence: attempt 1
    `raw-lte-repeat-001-a1-20260629-190720` created `cmd-000018` and received
    a raw LTE ACK with `transport.type=lte`,
    `lte_http.phase=command_ack`, `lte_http.poll_reason_code=LTE_HTTP_OK`,
    HTTP status `200`, `command.parse_status=raw_command_selected`, command
    status `ok`, and ACK status `ok`. The first validator pass was a
    false-negative because it compared the repeat attempt `test_run_id` with
    the firmware build-time ACK `test_run_id`; this is recorded in
    `reports/field_validation/raw-lte-repeat-001-a1-20260629-190720/validation_reconciliation.md`.
    Reconciliation reused existing `cmd-000018` without queueing a new command
    and wrote the PASS report under
    `reports/field_validation/raw-lte-repeat-001-a1-20260629-190720/`.
    Attempt 2 `raw-lte-repeat-001-a2-20260629-210939` ran after a separate
    operator-confirmed independent-power cold boot, created `cmd-000019`, and
    passed with `transport.type=lte`, `lte_http.phase=command_ack`,
    `LTE_HTTP_OK` / HTTP `200`, `poll_action_elapsed_ms=680`,
    `command.parse_status=raw_command_selected`, command status `ok`, and ACK
    status `ok`; evidence is under
    `reports/field_validation/raw-lte-repeat-001-a2-20260629-210939/`.
  - Boundary: no firmware flash; no long stability claim; any failure must be
    recorded as explainable evidence.
    Runtime evidence is under
    `reports/field_validation/lte003-command-loop-fix2-20260629-074709/`.
    Fix3 is build-verified and flashed as
    `0.1.0-lte003-command-loop-fix3` /
    `lte003-command-loop-fix3-20260629-081529`; fix3 code-change commit is
    `e79e4de`, flashed build app version is `79a12c8`, and binary is at
    `firmware/mqtt_heartbeat/build_lte003_command_loop_fix3/egolink_mqtt_heartbeat.bin`.
    It makes command-poll `AT+HTTPREAD` use the longer HTTP action timeout and
    splits the failure into AT-read versus body-parse reason codes. Flash
    evidence is under
    `reports/field_validation/lte003-command-loop-fix3-20260629-081529/flash_report.md`.
    USB-Free runtime validation failed with `cmd-000013` still pending and no
    ACK. The fix3 test-run export contained 59 diagnostic messages, with the
    latest showing HTTP poll status `200`, body length `592`, and
    `LTE_HTTP_READ_AT_FAILED`, narrowing the blocker to the SIM7670G
    `AT+HTTPREAD` command path. Runtime evidence is under
    `reports/field_validation/lte003-command-loop-fix3-20260629-081529/`.
    Fix4 is implemented and build-verified as
    `0.1.0-lte003-command-loop-fix4` /
    `lte003-command-loop-fix4-20260629-084350`; source/build app commit is
    `c8e1f59`, and the binary is at
    `firmware/mqtt_heartbeat/build_lte003_command_loop_fix4/egolink_mqtt_heartbeat.bin`.
    It tries `AT+HTTPREAD=0,<data_len>` before falling back to bare
    `AT+HTTPREAD`, and separates HTTPREAD `ERROR` from timeout diagnostics.
    Fix4 was flashed on `COM4` after explicit operator confirmation; flashed
    repo/app version is `b4eaa44`, and flash evidence is under
    `reports/field_validation/lte003-command-loop-fix4-20260629-084350/flash_report.md`.
    USB-Free runtime validation failed with `cmd-000013` still pending and no
    ACK. The fix4 test-run export contained 37 diagnostic messages, with the
    latest showing LTE ready, HTTP poll status `200`, body length `592`, and
    `LTE_HTTP_READ_BODY_PARSE_FAILED`. Runtime evidence is under
    `reports/field_validation/lte003-command-loop-fix4-20260629-084350/`.
    Fix5 is implemented and build-verified as
    `0.1.0-lte003-command-loop-fix5` /
    `lte003-command-loop-fix5-20260629-154839`; source/build app commit is
    `729c78b`, and the binary is at
    `firmware/mqtt_heartbeat/build_lte003_command_loop_fix5/egolink_mqtt_heartbeat.bin`.
    It falls back to bare `AT+HTTPREAD` when positional HTTPREAD returns `OK`
    without an extractable JSON body. Fix5 was flashed on `COM4` after
    explicit operator confirmation; flashed repo/app version is `efc9848`, and
    flash evidence is under
    `reports/field_validation/lte003-command-loop-fix5-20260629-154839/flash_report.md`.
    USB-Free runtime validation failed with `cmd-000013` still pending and no
    ACK. The fix5 test-run export contained 37 diagnostic messages, with the
    latest showing LTE ready, HTTP poll status `200`, body length `592`, and
    `LTE_HTTP_READ_BODY_PARSE_FAILED`. Runtime evidence is under
    `reports/field_validation/lte003-command-loop-fix5-20260629-154839/`.
    Fix6 is implemented and build-verified as
    `0.1.0-lte003-command-loop-fix6` /
    `lte003-command-loop-fix6-20260629-160859`; source/build app commit is
    `c1a90a0`, and the binary is at
    `firmware/mqtt_heartbeat/build_lte003_command_loop_fix6/egolink_mqtt_heartbeat.bin`.
    It adds an HTTPREAD-specific UART collection path that waits for the JSON
    body instead of returning on the first generic `OK`. Fix6 flash on `COM4`
    passed after explicit operator confirmation; flashed repo/app version is
    `8d7395f`, and flash evidence is under
    `reports/field_validation/lte003-command-loop-fix6-20260629-160859/flash_report.md`.
    USB-Free runtime validation failed with 37 fix6 diagnostics: HTTP poll
    status `200`, body length `592`, and `LTE_HTTP_OK`, but empty
    `command.last_cmd_id` and no ACK. Runtime evidence is under
    `reports/field_validation/lte003-command-loop-fix6-20260629-160859/`.
    Fix7 is implemented and build-verified as
    `0.1.0-lte003-command-loop-fix7` /
    `lte003-command-loop-fix7-20260629-164429`; source/build app commit is
    `33b8503`, and the binary is at
    `firmware/mqtt_heartbeat/build_lte003_command_loop_fix7/egolink_mqtt_heartbeat.bin`.
    It adds command parser diagnostics (`command.parse_status` and
    `command.command_count`) and raises the bounded poll window to 120 attempts.
    Fix7 flash on `COM4` passed after explicit operator confirmation; flashed
    repo/app version is `766f0d8`, and flash evidence is under
    `reports/field_validation/lte003-command-loop-fix7-20260629-164429/flash_report.md`.
    USB-Free runtime validation failed with 66 fix7 diagnostics: HTTP poll
    status `200`, body length `592`, and `LTE_HTTP_OK`, but
    `command.parse_status=json_parse_failed`, `command.command_count=0`, and
    no ACK. Runtime evidence is under
    `reports/field_validation/lte003-command-loop-fix7-20260629-164429/`.
    Fix8 is implemented and build-verified as
    `0.1.0-lte003-command-loop-fix8` /
    `lte003-command-loop-fix8-20260629-170628`; source/build app commit is
    `a87a754`, and the binary is at
    `firmware/mqtt_heartbeat/build_lte003_command_loop_fix8/egolink_mqtt_heartbeat.bin`.
    It changes HTTPREAD body extraction to wait for a complete brace-balanced
    JSON object instead of accepting the first partial brace pair. Fix8 is not
    flashed or USB-Free runtime validated yet. After protocol review on
    2026-06-29, continuing JSON parser fixes is no longer the default next
    step; PROTO-002 raw-frame transport should provide the next LTE-003
    acceptance path.

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
- `PROTO-002 Raw Frame Transport Contract`
  - Path: `docs/tasks/done/PROTO-002_RAW_FRAME_TRANSPORT_CONTRACT.md`
  - Status: completed.
  - Goal: define a raw-frame-first device/server transport profile where the
    VPS preserves original bytes before parsing and derives existing
    `egolink.p0.v1` JSON Web/API views afterward.
  - Evidence: `docs/development/PROTOCOL.md`,
    `docs/development/LTE_TRANSPORT.md`,
    `docs/development/VPS_MESSAGE_HUB.md`,
    `shared/contracts/message_hub_raw_frame_record.schema.json`, SERVER-002,
    DEPLOY-002, and FW-003.
  - Boundary: raw-frame command/ACK passed through FW-003; long LTE stability,
    reconnect recovery, GNSS-over-LTE, battery/power, and product acceptance
    remain separate gates.
- `FW-003 Raw Frame LTE Command Loop`
  - Path: `docs/tasks/done/FW-003_RAW_FRAME_LTE_COMMAND_LOOP.md`
  - Status: completed.
  - Goal: move the LTE command-loop firmware path to PROTO-002 raw-frame
    poll/ACK over SIM7670G AT HTTP while keeping JSON views as derived
    server/Web compatibility state.
  - Evidence: focused firmware/server tests passed with 24 tests,
    `context_lint` passed, full `verify.ps1` passed with 278 tests,
    `git diff --check` passed, guarded ESP-IDF prepare/build passed for
    `0.1.0-fw003-raw-command-loop` /
    `fw003-raw-command-loop-20260629-175608`, and VPS smoke
    `fw003-raw-derived-smoke-20260629-175946` derived LTE ACK evidence from
    raw frames. The firmware was flashed on `COM4` after explicit operator
    confirmation, then USB-Free runtime validation passed with `cmd-000017`
    ACKed over LTE raw frames.
- `OBS-002 Raw Frame Dashboard Observability`
  - Path: `docs/tasks/done/OBS-002_RAW_FRAME_DASHBOARD_OBSERVABILITY.md`
  - Status: completed.
  - Goal: make the Message Hub Dashboard show recent raw-frame direction/type,
    parse status, derived message type, frame ID, and receive time without
    exposing raw payload bytes.
  - Evidence: focused dashboard/server tests passed with 15 tests, full
    `verify.ps1` passed with 279 tests, VPS deployment restarted
    `egolink-message-hub.service`, `/` includes the Raw Frames panel,
    unauthenticated `/api/state` remains `401`, and authenticated `/api/state`
    includes redacted raw frames with latest `cmd-000017` parsed as `ok` /
    `ack`.
- `SERVER-001 VPS Message Service Minimal Loop`
  - Path: `docs/tasks/done/SERVER-001_VPS_MESSAGE_SERVICE_MINIMAL_LOOP.md`
  - Status: completed as a local deployable service baseline.
  - Goal: run the minimal device registration, heartbeat/telemetry ingest,
    command queue, ACK tracking, and event storage service on the VPS without
    touching existing GitLab.
  - Evidence: `server/message_hub.py`, `scripts/run_message_hub.py`, and
    `quality_tests/test_message_hub_server.py`.
- `SERVER-002 Raw Frame Ingest And Storage`
  - Path: `docs/tasks/done/SERVER-002_RAW_FRAME_INGEST_STORAGE.md`
  - Status: completed as a local server implementation baseline.
  - Goal: add Message Hub raw-frame storage and HTTP routes so incoming bytes
    are retained before parser/schema conversion.
  - Evidence: `server/message_hub.py` adds the `raw_frames` table and
    raw ingest/poll/ACK routes; `quality_tests/test_message_hub_server.py`
    covers checksum-failed raw retention, raw ACK command update, and HTTP
    `poll.raw` / `ack.raw`.
  - Boundary: no firmware flash, hardware validation, VPS deployment, GitLab
    change, or removal of existing JSON endpoints.
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
- `DEPLOY-002 Raw Frame Message Hub VPS Deployment`
  - Path: `docs/tasks/done/DEPLOY-002_RAW_FRAME_MESSAGE_HUB_VPS_DEPLOYMENT.md`
  - Status: completed as a raw-frame server redeploy.
  - Goal: deploy SERVER-002 raw-frame storage and `poll.raw` / `ack.raw`
    routes to the operator VPS without touching GitLab.
  - Evidence: remote `egolink-message-hub.service` active on `0.0.0.0:8790`,
    `/health` OK, unauthenticated `/api/state` 401, authenticated
    `/api/state` includes `raw_frames`, and raw-frame smoke
    `raw-frame-vps-smoke-20260629-174047` ACKed a command through raw frames.
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
- `OBS-003 Current Run Key Release Failure Visibility`
  - Path: `docs/tasks/done/OBS-003_CURRENT_RUN_KEY_RELEASE_FAILURE_VISIBILITY.md`
  - Status: completed as a Server-Web/report observability increment.
  - Goal: make every runnable version demonstrable by showing current run,
    key-release or unreleased/baseline state, command/ACK chain, raw evidence,
    derived location, and failure reason in API, export, and Dashboard
    surfaces.
  - Evidence: `/api/state` includes top-level `current_run`; test-run export
    includes top-level `run_context`; `observability_summary` includes
    `failure_summary`; Dashboard renders a `Run Context` panel; the VPS deploy
    package includes `docs/current/key_releases`; focused Message Hub
    server/dashboard tests passed with 20 tests; full `scripts\verify.ps1`
    passed with 300 tests; VPS smoke confirmed current LOC-005A run as
    `unreleased` against baseline `KR-003`, `cmd-000024` command/ACK `ok`,
    raw-frame parse `ok`, and failure reason `GNSS_NO_FIX`.
  - Boundary: no firmware change, hardware action, new key release, long LTE
    stability, battery/power behavior, enclosure behavior, or product
    readiness is claimed.
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
- `LOC-003 Location Memory Gate`
  - Path: `docs/tasks/done/LOC-003_LOCATION_MEMORY_GATE.md`
  - Status: completed as a server/Web/API gate and small rule baseline.
  - Goal: persist VPS-side location memory and make a later GNSS no-fix
    explainable without erasing the prior useful calibration.
  - Evidence: Message Hub has a persistent `location_memory` table;
    `/api/state` exposes `location_memory` and
    `observability.location_memory`; `observability.location_belief` derives
    `Predicted` with reason `last_known_after_gnss_no_fix` when the latest
    report is no-fix but memory exists; test-run export rebuilds the same
    summary; Dashboard renders memory state/update/reason; and
    `scripts/validate_location_memory_gate.py` provides a hardware-free
    rerunnable gate.
  - Boundary: no firmware-side multi-source collection, learned known-place
    model, LTE long-run, product GNSS acceptance, battery/power behavior, or
    hardware action is claimed by this task.
- `LOC-004A Real Cell Location Observation`
  - Path: `docs/tasks/done/LOC-004A_REAL_CELL_LOCATION_OBSERVATION.md`
  - Status: completed as a bounded USB-Free runtime gate after
    independent-power reboot with USB disconnected; the pass is reconciled
    from actual VPS raw-frame evidence because the automatic validator
    attempts hit a one-command-per-boot timing issue.
  - Goal: make raw LTE `request_location` produce both GNSS
    `location_report` and real firmware-side SIM7670G cell/LTE
    `location_observation` evidence without returning to device-side JSON.
  - Evidence: Message Hub derives raw key/value `location_observation` into
    `cell`, `lte`, `transport`, `lte_http`, and `location_belief`; Unknown
    observations preserve existing useful `location_memory`; firmware adds
    opt-in `CONFIG_EGOLINK_SIM7670_LOCATION_OBSERVATION_ENABLED`; and
    `scripts/validate_lte_command_loop.py --require-location-observation`
    can gate command-scoped cell/LTE evidence.
    Flash evidence on `COM4` is recorded at
    `reports/field_validation/loc004a-cell-observation-20260630-001/flash_report.md`.
    Runtime evidence is recorded at
    `reports/field_validation/loc004a-cell-observation-runtime-20260630-001/validation_reconciliation.md`:
    `cmd-000021` produced raw LTE `location_report`, raw LTE
    `location_observation`, and raw LTE ACK with command/ACK status `ok`;
    stale `cmd-000022` was server-side cancelled and is not hardware evidence.
  - Boundary: no cell-only positioning, learned known-place model,
    Wi-Fi/IMU/power fusion, LTE long-run stability, reconnect recovery,
    battery/power behavior, enclosure behavior, or product readiness is
    claimed by this task.
- `LOC-005A Firmware-Side Observation Source States`
  - Path: `docs/tasks/done/LOC-005A_FIRMWARE_SIDE_OBSERVATION_SOURCE_STATES.md`
  - Status: completed as a firmware/server/Web contract increment, COM4 flash
    gate, and one-command USB-Free hardware runtime validation.
  - Goal: add Wi-Fi, IMU, and power source/evidence status slots to the raw
    LTE `location_observation` path without returning to device-side JSON or
    claiming unavailable sensor readiness.
  - Evidence: firmware raw KV observations now include explicit
    `wifi_*`, `imu_*`, and `power_*` source/evidence fields; Message Hub
    derives them into structured `wifi`, `imu`, and `power` groups; `/api/state`
    and Dashboard observability expose their `source_status` and
    `evidence_status`; focused firmware/server/dashboard tests passed; full
    `scripts\verify.ps1` passed with 299 tests; guarded ESP-IDF build produced
    `build_loc005a_source_states/egolink_mqtt_heartbeat.bin`; Message Hub/Web
    was redeployed to `203.0.113.10:8790` without touching GitLab; COM4 flash
    passed with evidence under
    `reports/field_validation/loc005a-source-states-20260630-001/flash_report.md`;
    independent-power USB-Free validation later reconciled existing
    `cmd-000024` as PASS with raw LTE `location_report`, raw LTE
    `location_observation`, and raw LTE ACK evidence under
    `reports/field_validation/loc005a-source-states-20260630-001/`.
  - Boundary: Wi-Fi remains `disabled` / `missing` in the current LTE mode,
    default IMU remains mock/unverified, and default power remains a
    mock/log-backend source. No battery accuracy, product power behavior,
    Wi-Fi fingerprinting, learned fusion, long LTE stability, enclosure, or
    product readiness is claimed.
- `FIELD-002 USB-Free Reboot-Aware Command Validator`
  - Path: `docs/tasks/done/FIELD-002_USB_FREE_REBOOT_AWARE_COMMAND_VALIDATOR.md`
  - Status: completed as field-validation tooling only; no hardware action was
    performed by this task.
  - Goal: make one-command-per-boot USB-Free slices validate through a stable
    arm/reboot/reconcile workflow instead of repeated ad hoc command enqueueing.
  - Evidence: `scripts/validate_lte_command_loop.py` supports `--arm-only`
    reports and `--evidence-since command-created|validator-start|test-run-created`;
    required location messages can use `--expected-message-test-run-id`;
    `scripts/run_fw001_hw_r1.ps1` exposes `-ArmLteCommandOnly`,
    `-LteEvidenceSince`, and `-ExpectedMessageTestRunId`;
    `docs/development/FIELD_TEST.md` and
    `firmware/mqtt_heartbeat/README.md` document the flow. Focused tests passed
    with 14 tests, and full `scripts\verify.ps1` passed with 294 tests.
  - Boundary: no firmware flash, real VPS command enqueue, hardware runtime
    pass, long LTE stability, reconnect, battery/power, enclosure behavior, or
    product readiness is claimed.
- `FIELD-002A Reboot-Aware Validator USB-Free Smoke`
  - Path: `docs/tasks/done/FIELD-002A_REBOOT_AWARE_VALIDATOR_USB_FREE_SMOKE.md`
  - Status: completed as a bounded hardware smoke of the FIELD-002
    arm/reboot/reconcile workflow.
  - Goal: prove the new validator flow on the real LOC-004A connectivity-node
    firmware without USB as the runtime data path.
  - Evidence: validator armed `cmd-000023` for
    `loc004a-reboot-aware-20260630-001`, the operator rebooted on independent
    power with USB disconnected, and existing-command reconciliation passed
    with raw LTE `location_report`, raw LTE `location_observation`, and raw LTE
    ACK. Evidence is under
    `reports/field_validation/loc004a-reboot-aware-20260630-001/`.
  - Boundary: no firmware flash, GNSS fix, cell-only positioning, long LTE
    stability, reconnect recovery, battery/power behavior, enclosure behavior,
    or product readiness is claimed.
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

- Location fusion dataset baseline
  - Path: `docs/tasks/done/DATA-001_LOCATION_FUSION_DATASET_BASELINE.md`
  - Status: completed as `DATA-001`.
  - Current role: exports Message Hub test-run JSON into JSONL observation
    windows plus a manifest, preserving raw-frame lineage, labels, quality
    checks, privacy class, and split assignment for future fusion work.
  - Evidence: `shared/contracts/location_fusion_sample.schema.json`,
    `scripts/export_location_fusion_dataset.py`, and
    `quality_tests/test_location_fusion_dataset_export.py`.
- Location fusion algorithm design
  - Path: `docs/tasks/done/ALG-000_LOCATION_FUSION_ALGORITHM_DESIGN.md`
  - Status: completed as `ALG-000`.
  - Current role: freezes EALE-P0 as a server-side, derived-only,
    explainable rule/scoring baseline that consumes DATA-001 observation
    windows without changing firmware wire protocol or claiming positioning
    accuracy.
  - Evidence: `docs/development/LOCATION_FUSION_ALGORITHM.md`.
- Server-derived EALE-P0 location belief
  - Path: `docs/tasks/done/ALG-001_SERVER_DERIVED_LOCATION_BELIEF.md`
  - Status: completed as `ALG-001`.
  - Current role: exposes conservative EALE-P0 derived `location_belief`,
    normalized source evidence, dataset-window readiness, and quality flags
    through `/api/state.current_run.eale_p0`, test-run export
    `run_context.eale_p0`, `observability_summary.eale_p0`, and the
    Dashboard Run Context panel.
  - Boundary: no firmware change, wire-protocol change, learned model,
    cell-only positioning claim, key release, or product-readiness claim.
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

1. Treat KR-003 as the current Walking Skeleton baseline: raw LTE command
   queue, command-scoped no-fix GNSS report, real firmware-side SIM7670G
   cell/LTE observation, raw ACK, Web/API derived view, and reboot-aware
   validator workflow.
2. Treat `DATA-001` as the completed dataset baseline: use
   `scripts/export_location_fusion_dataset.py` to turn selected test-run
   exports into JSONL samples and manifests before large collection or model
   training.
3. Treat `ALG-000` as the completed EALE-P0 design freeze: use
   `docs/development/LOCATION_FUSION_ALGORITHM.md` as the algorithm boundary
   for KR-004 preparation.
4. Treat `LOC-005A` as the completed source-state increment: Wi-Fi/IMU/power
   evidence is now present in the USB-Free raw LTE observation path with
   explicit source labels, not inferred capabilities.
5. Treat `OBS-003` as the completed Web/report visibility increment: current
   run, key-release/baseline state, command/ACK chain, raw evidence, derived
   location, and failure reason are now visible through API/export/Dashboard.
6. Treat `ALG-001` as the completed server-derived EALE-P0 visibility
   increment: current run, export, and Dashboard can now explain conservative
   location belief, source evidence, dataset-window readiness, and quality
   flags without firmware or DATA-001 schema changes.
7. Treat `REL-004` as the completed KR-004 release-candidate gate. Review the
   generated KR-004 report before promoting it from `release_candidate` to
   `released`.
8. Prepare `ALG-002` separately to run EALE-P0 over DATA-001 JSONL for
   evidence/failure coverage metrics before release promotion or broader data
   collection.
9. Use `STAB-001B` only as a short KR-003/KR-004 USB-Free baseline after the data and
   observability gates can explain failures. Do not promote it into long
   stability testing.
10. Move to `LTE-005` reconnect/retry/cache/stale-command behavior after the
    release-candidate gate remains explainable.

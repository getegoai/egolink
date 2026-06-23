# Ego Link HARCH-001 Platform Coupling Audit

> Status: HARCH-001 audit only  
> Date: 2026-06-23  
> Scope: Waveshare ESP32-S3-SIM7670G-4G P0 baseline, current firmware, PC Simulator, hardware reports, and M1 data tooling  
> Non-goal: no platform refactor, no firmware behavior change, no hardware I/O, no new driver implementation

## 1. Current Hardware Availability

This table records the current evidence boundary before HARCH-002, HPWR-001,
HDATA-001, and HPORT-001. This audit did not rerun serial, MQTT, GNSS, camera,
or power tests; it uses the latest checked-in evidence.

| Capability | Current status | Evidence | Boundary |
|---|---:|---|---|
| ESP32-S3 board enumeration | `verified` | `reports/board_validation/20260622-181619/probe.md` shows CH343 `COM4`. | Board is visible to the PC. This does not prove power, storage, or sensor readiness. |
| ESP32 Wi-Fi MQTT uplink | `verified` | `docs/hardware/HARDWARE_USABILITY_VALIDATION.md`; `firmware/mqtt_heartbeat/main/app_main.c`; T038 MQTT worker received `mqtt_status` and `sensor_sample/device_health seq=21548`. | Wi-Fi currently simulates 4G data. Business logic must not treat this as final cellular transport. |
| ESP32 device health sample | `verified` | `firmware/mqtt_heartbeat/main/app_main.c` publishes RSSI, uptime, free heap, and minimum free heap. | This is the only current real device-side structured sensor sample. Battery, modem, and GNSS fields in the same payload are still mock. |
| SIM7670G USB identity and LTE attach | `pc_side_verified` | `reports/board_validation/20260622-181619/probe.md` shows `COM6` / `COM7` model `SIM7670G-MNGV`, SIM inserted, registered, attached. | Verified through PC USB AT ports, not through ESP32 firmware control. |
| SIM7670G GNSS query | `pc_side_verified` | `reports/gnss_validation/20260622-181804/gnss_probe.md`; `scripts/sim7670_gnss_probe.py`. | GNSS can be queried from the PC and currently reports indoor no-fix. No real lat/lon, speed, accuracy, or fix-age dataset exists yet. |
| RNDIS | `pc_side_verified` | `reports/board_validation/20260622-181619/probe.md`. | Useful for diagnostics only. Product path cannot depend on the PC RNDIS interface. |
| Camera smoke frames | `semi_verified` | `docs/hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md`; `firmware/camera_smoke/main/app_main.c`; `firmware/camera_smoke/README.md`. | Camera smoke is a separate firmware app. Current `mqtt_heartbeat` firmware does not capture images. |
| M1 recording, quality gate, replay | `verified` on PC | `pc_simulator/session_recorder.py`, `pc_simulator/session_inspector.py`, `pc_simulator/session_replay.py`; T038 recording quality/replay reports. | PC event-log derived, not an ESP32 firmware recorder. |
| Annotation CLI | `verified` on PC | `pc_simulator/session_annotations.py`; `scripts/annotate_session_recording.py`; T037 tests. | No real user-confirmed labels exist until an operator applies them. |
| Safety Companion M0 firmware interface | `semi_verified` | `firmware/mqtt_heartbeat/components/safety_model/*`; firmware static tests. | Deterministic mock/rule baseline. It does not prove real incident detection. |
| IMU | `missing_or_unknown` | `docs/modeling/HARDWARE_SENSOR_MATRIX.md`. | No confirmed part, bus, pins, mounting direction, driver, samples, or ring buffer. |
| Microphone | `missing_or_unknown` | `docs/modeling/HARDWARE_SENSOR_MATRIX.md`. | No confirmed PDM/I2S/ADC path, sample rate, privacy gate, or audio buffer. |
| Physical SOS GPIO | `not_verified` | `docs/modeling/HARDWARE_SENSOR_MATRIX.md`. | SOS is currently CLI/Dashboard/synthetic unless a GPIO task verifies it. |
| SD or external local storage | `not_verified` | `reports/board_validation/20260622-181619/probe.md` warns SD mount not observed. | Not available for firmware session persistence. |
| SPI flash / NVS | `semi_verified` | `firmware/mqtt_heartbeat/main/app_main.c` initializes NVS. | Available for config/small state, not yet validated as session storage. |
| Battery, charger, fuel gauge | `mock_only` / `missing_or_unknown` | `firmware/mqtt_heartbeat/main/app_main.c`; `pc_simulator/session_recorder.py`. | `battery=87` and `charging=false` are placeholders. No real battery voltage, percentage, current, charger state, or gauge part is verified. |
| Power measurement markers | `not_verified` | `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md`. | No power-state events, GPIO markers, cumulative state duration, or PPK2 alignment records exist yet. |

## 2. Platform Coupling Findings

### 2.1 Firmware MQTT heartbeat app

`firmware/mqtt_heartbeat/main/app_main.c` is currently a compact smoke firmware,
but it binds multiple platform concerns in one file:

- ESP-IDF Wi-Fi, MQTT, NVS, timer, heap, event groups, tasks, and logs are used
  directly in the app file (`esp_wifi`, `esp_mqtt_client`, `nvs_flash`,
  `esp_timer`, `esp_get_free_heap_size`, FreeRTOS task creation).
- Status and sensor JSON are assembled directly with `snprintf`, so protocol
  payload construction is coupled to Wi-Fi/MQTT publishing.
- Mock fields are embedded in the same payload as real readings:
  `battery=87`, `charging=false`, `link_type=mock_4g_over_wifi`,
  `modem_state=mock_data_ready`, and `gnss_state=mock_fix`.
- `default_safety_mock_state()` declares camera and microphone available even
  though the hardware matrix says camera is only semi-verified and microphone is
  missing/unknown.
- The Safety model is called directly through `safety_model_*` functions rather
  than through an `inference_backend` boundary.
- Serial Safety CLI is implemented with `getchar()` in the same app file; this
  is fine for smoke testing but not a portable command/input service.

Audit conclusion: the file is useful as a smoke target, but HARCH-002 should not
grow it further. New platform abstractions should be introduced as narrow seams
around one concern at a time.

### 2.2 Firmware camera smoke app

`firmware/camera_smoke/main/app_main.c` verifies a camera path and TCAM-001
captured three OV5640 QVGA JPEG frame summaries over UART, but it is not a
portable camera service:

- Camera pin profile, `esp_camera_init`, frame capture, checksum logging,
  Wi-Fi startup, and HTTP `/capture` serving are all in one app.
- The Waveshare pinout is hard-coded in the app.
- There is no shared `platform_camera` API, no privacy gate, no capture token,
  no retention policy, no power-state marker, and no session-recorder hook.

Audit conclusion: keep `camera_smoke` as a board validation target. Do not fold
it into the product path until `platform_camera` and privacy/power boundaries
exist.

### 2.3 SIM7670G and GNSS PC-side probes

`scripts/egolink_board_probe.py` and `scripts/sim7670_gnss_probe.py` are
PC-side hardware validation tools:

- Board probe discovers Windows serial ports, RNDIS adapters, and sends basic
  AT commands such as `AT`, `ATI`, `AT+CPIN?`, `AT+CSQ`, `AT+CEREG?`, and
  `AT+CGATT?`.
- GNSS probe sends `AT+CGNSSPWR?`, optionally `AT+CGNSSPWR=1`,
  `AT+CGNSSINFO`, and `AT+CGPSINFO`; it writes PC Simulator `location_report`
  events.
- Both scripts use PowerShell and Windows COM-port behavior.

Audit conclusion: this evidence is real, but it is PC-side real. It should feed
reports and M1 PC recordings, not be confused with an ESP32-side modem/GNSS
driver.

### 2.4 PC Simulator app and MQTT worker

`pc_simulator/app.py` and `pc_simulator/mqtt_worker.py` are intentionally local,
but several product-facing assumptions are still embedded:

- `DeviceState` defaults to `battery=87`, `link_type=mock_4g_over_wifi`,
  `modem_state=mock_data_ready`, and `gnss_state=mock_fix`.
- Mock Dashboard endpoints create heartbeat, location, SOS, and wake events.
- MQTT worker shells out to `mosquitto_sub`, defaults to `127.0.0.1`, and
  normalizes topic payloads into PC Simulator events.
- Live hardware validation uses the LAN broker at `192.168.31.250:1883`; using
  loopback broker status is not proof of device uplink.
- Safety processing is an optional after-store hook, which is good for bounded
  validation, but it is still PC orchestration rather than device behavior.

Audit conclusion: PC Simulator remains the right local test harness. HARCH-002
should avoid moving PC-only assumptions into firmware abstractions.

### 2.5 Safety model and capability defaults

The current Safety model path has two different capability defaults:

- Firmware mock state marks `camera_available=true` and
  `microphone_available=true`.
- `pc_simulator/safety_companion.py` defaults camera/microphone availability to
  true when device fields are absent.
- `pc_simulator/session_replay.py` correctly derives camera/microphone
  availability from recording privacy flags, so replay currently lowers them to
  false for structured-only sessions.

Audit conclusion: capability availability needs a single descriptor source.
Until then, model evidence requests can overstate the current hardware.

### 2.6 Session recorder and replay

The M1 PC data tools already preserve many useful boundaries:

- `pc_simulator/session_recorder.py` explicitly marks IMU, microphone, physical
  SOS GPIO, SD storage, true battery telemetry, and ESP32-side SIM7670G control
  as unavailable or unverified.
- GNSS reports are marked `pc_side_probe`.
- Replay refuses to turn raw image/audio availability on unless recording
  privacy allows it.

Audit conclusion: keep this boundary. HDATA-001 should extend this path with
real IMU/power metadata only after HARCH-002/HPWR provide stable events.

## 3. Minimal Abstraction Boundaries

These are the smallest useful boundaries identified by the audit. HARCH-002
must choose exactly one slice per task.

| Boundary | Purpose | Current source | Minimal first shape |
|---|---|---|---|
| `board_capabilities` | Single truth for camera, microphone, IMU, battery gauge, storage, cellular, GNSS, and power marker availability. | Hardware matrix, recorder manifest, mock defaults. | Static descriptor for `waveshare_esp32s3_sim7670g_4g` plus mock descriptor for tests. |
| `platform_power` | Report power state, battery placeholders, charging status, reset reason, and measurement markers. | Mock fields in firmware/PC payloads. | `enter_state`, `leave_state`, `mark`, `snapshot`; first backend logs events only. |
| `platform_time` | Provide monotonic timestamp and optional wall-clock source for session alignment. | `esp_timer_get_time`, PC `received_at`. | `monotonic_ms`, `unix_ms_or_unknown`, `source`. |
| `inference_backend` | Decouple Safety/ContextRouter calls from concrete `safety_model_*` implementation. | `safety_model_evaluate`, PC package API. | `init`, `get_capabilities`, `run`, `get_last_profile`; no model change. |
| `platform_connectivity` | Separate link state and publish from Wi-Fi/MQTT specifics. | `esp_wifi_*`, `esp_mqtt_client_*`, `mosquitto_sub`. | `connect`, `publish_event`, `publish_status`, `link_snapshot`. |
| `platform_gnss` | Distinguish mock GNSS, PC-side AT probe, and future ESP32-side SIM7670G GNSS. | Mock payloads, `scripts/sim7670_gnss_probe.py`. | Start with explicit `NOT_SUPPORTED` in firmware backend plus PC probe import metadata. |
| `platform_imu` | Prepare M1-003 ring buffer without pretending real IMU exists. | None. | Mock sample generator, ring buffer contract, availability `not_available` for real backend. |
| `platform_storage` | Isolate session persistence and hash/manifest behavior. | PC recording files, NVS init, SD status warnings. | PC recorder remains canonical; firmware backend starts as `NOT_SUPPORTED` for SD sessions. |
| `platform_camera` | Keep camera smoke from product capture flow until privacy and power gates exist. | `firmware/camera_smoke`. | `capture_single` returns `NOT_SUPPORTED` in product firmware until verified. |

## 4. Recommended Task Order

The user-requested order is sound, with one important constraint: each task must
modify only the paths it owns and must keep hardware claims evidence-based.

### HARCH-002

Do one interface only. Because HPWR-001 follows immediately, the recommended
first slice is `platform_power`, not modem, camera, IMU, or storage.

Minimum HARCH-002 acceptance:

- Add a tiny power-state/marker interface and mock or log-only backend.
- Keep `battery=87` and `charging=false` explicitly marked as mock.
- Do not implement sleep, modem power control, battery ADC, fuel gauge, or GPIO
  marker toggling in the same task.
- Keep existing MQTT heartbeat and Safety tests passing.

### HPWR-001

Build on `platform_power`:

- Emit `BOOT`, `ACTIVE`, `GUARDING`, `NETWORK_ATTACH`, `UPLOAD`,
  `GNSS_FIX`, `CAPTURE_AUDIO`, `CAPTURE_IMAGE`, `STORAGE_WRITE`,
  `EMERGENCY`, and sleep-state entry/exit markers as structured events.
- Include cumulative duration counters and optional serial/GPIO marker IDs.
- Create a scenario report template for PPK2 or future higher-peak instruments.
- Do not claim any 48-hour or 5-7-day result without measured data.

### HDATA-001

Continue the M1 real data loop:

- Keep current real device-health and PC-side GNSS no-fix recordings.
- Add IMU ring-buffer mock/interface only if no real IMU is confirmed.
- Once IMU hardware is confirmed, record sample rate, jitter, missing frames,
  overflow count, and event-window completeness.
- Preserve annotation linkage and replay quality gate before using data for any
  MotionNet work.

### HPORT-001

Only after a new development board physically arrives:

- Port boot, log, clock, power marker, one IMU input or reference vector, model
  baseline, and ContextRouter contract.
- Do not port 4G, Dashboard, all storage, camera, or full business behavior in
  the first board PoC.
- Compare latency, RAM, Flash, and one measured energy marker against ESP32-S3
  before deciding whether to continue.

## 5. Risks If Refactored Too Broadly

- A large `firmware/platform/**` skeleton could create many unverified backends
  and hide the fact that IMU, microphone, SD, battery gauge, and ESP32-side
  SIM7670G control are still unavailable.
- Moving camera smoke into product firmware before privacy and power controls
  exist would blur the semi-verified camera status.
- Treating PC-side AT probe output as device-side modem/GNSS state would
  corrupt M1 provenance and future power measurements.
- Abstracting modem, GNSS, storage, camera, IMU, and power in one task would
  make regressions hard to isolate and would violate the current "one hardware
  interface at a time" rule.
- Keeping capability defaults scattered will let the model request evidence
  from sensors that are not actually present.

## 6. HARCH-001 Result

HARCH-001 is complete when this audit is reviewed and the next task chooses one
interface slice. The recommended next task is:

```text
HARCH-002A: add a minimal platform_power interface and log/mock backend.
```

After that, HPWR-001 can add power-state events and measurement markers without
rewriting connectivity, modem, GNSS, camera, IMU, or storage in the same step.

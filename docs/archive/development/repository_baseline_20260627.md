# Ego Link Repository Baseline

## Current Structure

This baseline records facts evidenced by files currently present in the repository. It does not claim that hardware-dependent behavior is currently verified in this run.

- `README.md` identifies the project as Ego Link P0, with the Waveshare ESP32-S3-SIM7670G-4G board as the current hardware and a first-stage goal of device networking, MQTT uplink, dashboard display, SOS, wake, and location event loops.
- `firmware/` contains two ESP-IDF smoke-test projects:
  - `firmware/camera_smoke/` validates the Waveshare board camera connector by initializing the camera, capturing one JPEG frame, and optionally serving captures over Wi-Fi when configured.
  - `firmware/mqtt_heartbeat/` validates the P0 data-link step by connecting to Wi-Fi, connecting to a local Mosquitto broker, and publishing status JSON to `ego/link/ego-link-001/status`.
- `pc_simulator/` contains a dependency-free Python HTTP dashboard in `app.py`, protocol message builders in `protocol.py`, and JSONL persistence helpers in `event_store.py`. The dashboard exposes local mock endpoints for heartbeat, location, SOS, wake, and `play_prompt` command events.
- `quality_tests/` contains Python `unittest` coverage for protocol builders, PC simulator event sequencing and JSONL writes, event-store loading, and board-probe parsing.
- `scripts/` contains local automation utilities:
  - `scripts/verify.ps1` runs `python -m unittest discover -s quality_tests -v`.
  - `scripts/start_mosquitto_lan.ps1` starts a user-mode Mosquitto broker using configuration generated under `pc_simulator/runtime/`.
  - `scripts/egolink_board_probe.py` is referenced by tests and status records for board/SIM probing.
  - `scripts/autodev_bootstrap_check.py` checks this baseline file for the required AUTO-001 headings.
- `docs/` contains project context, status, workflow notes, product positioning, board validation notes, and task records. `docs/EGO_LINK_P0_CONTEXT.md` defines the Mock-first P0 architecture and future hardware abstraction goals.
- `reports/board_validation/` contains at least one recorded board-validation report directory with `probe.json` and `probe.md`.
- `autodev/` is present as an automation control area. It was not modified for this task.

## Verified Commands

The following commands are evidenced by repository files. Only the AUTO-001 bootstrap check was run in this task; hardware and long-running commands are listed as repository entry points, not as newly verified hardware results.

- AUTO-001 verification command:

```powershell
python scripts/autodev_bootstrap_check.py AUTO-001
```

- General unit-test entry point from `scripts/verify.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

This script changes to the repository root and runs:

```powershell
python -m unittest discover -s quality_tests -v
```

- PC Simulator entry point from `README.md` and `pc_simulator/app.py`:

```powershell
python pc_simulator/app.py --port 8787
```

The documented local URL is:

```text
http://127.0.0.1:8787
```

- Local LAN Mosquitto broker entry point from `README.md` and `scripts/start_mosquitto_lan.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_mosquitto_lan.ps1 -BrokerIp 192.168.31.250 -Restart
```

This script depends on Mosquitto being installed at `C:\Program Files\mosquitto\mosquitto.exe`.

- Camera smoke-test build commands documented in `firmware/camera_smoke/README.md`:

```powershell
cd firmware/camera_smoke
idf.py set-target esp32s3
idf.py build
```

The same README documents flashing/monitoring with `idf.py -p COM4 flash monitor`, which is hardware-dependent and was not run in this task.

- MQTT heartbeat smoke-test build commands documented in `firmware/mqtt_heartbeat/README.md`:

```powershell
cd firmware/mqtt_heartbeat
idf.py set-target esp32s3
idf.py build
idf.py -p COM4 flash
```

The MQTT heartbeat README also documents subscribing with Mosquitto to `ego/link/ego-link-001/status`; this is environment- and broker-dependent and was not run in this task.

## P0 Boundary

- The repository context and AGENTS instructions define Ego Link P0 as Mock-first.
- Current P0 uses Wi-Fi to simulate the 4G data path, software to simulate GNSS, and CLI/button/timer-style simulated wake events.
- The PC acts as a local simulator and is explicitly not the formal EGO Base.
- The product path must remain local-first and privacy-first; repository instructions prohibit adding cloud services or external hosted AI dependencies.
- Safety-critical SOS behavior is required to remain deterministic and must not depend on an LLM decision.
- Hardware-dependent behavior remains distinct from software verification. A passing build or unit test is not evidence of 4G registration, GNSS fix, calling, or power consumption on physical hardware.
- `docs/STATUS.md` records prior hardware and network observations, including camera smoke, MQTT heartbeat, Mosquitto broker, and SIM7670G AT TCP/IP checks. Those are historical status records, not results newly reproduced by this baseline task.

## Risks and Gaps

- The current repository contains smoke-test firmware projects, but the broader P0 firmware architecture described in `docs/EGO_LINK_P0_CONTEXT.md` is not yet present as a single integrated ESP-IDF application with `LinkTransport`, `ModemDriver`, `GnssDriver`, `WakeDriver`, and `PowerDriver` abstractions.
- `pc_simulator/app.py` provides local mock HTTP/dashboard behavior and JSONL logging, but this baseline did not find a PC-side MQTT worker implementation that subscribes to device topics and writes received messages into the event log.
- Runtime files exist under `pc_simulator/runtime/`, including `events.jsonl`, Mosquitto config, log, and PID files. These appear to be generated local runtime artifacts, not source modules.
- Python `__pycache__/` directories are present under several source/test directories. These are generated artifacts.
- Real hardware behavior is not verified by this task. Any camera, MQTT heartbeat, SIM registration, LTE data, RNDIS, or SD-card claims should be traced to prior status/report files or rerun on hardware.
- `docs/STATUS.md` records known limitations: SD-card mount failure needs separate confirmation; system Mosquitto configuration could not be modified without administrator privileges; Windows RNDIS direct internet access through the SIM7670G path timed out even though module AT TCP/IP connectivity was reported as working.
- The currently documented `docs/tasks/CURRENT_TASK.md` describes T015, while this AutoDev run is executing AUTO-001 from the supervisor-provided task contract. That means the supervisor task contract, not `CURRENT_TASK.md`, is the controlling task for this run.

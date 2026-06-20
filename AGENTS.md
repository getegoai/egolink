# Ego Link P0 — Codex Working Agreement

## Project identity

- This repository is **Ego Link P0**, the wearable/mobile companion node for Project EGO.
- Target board: **Waveshare ESP32-S3-SIM7670G-4G**.
- Main MCU: ESP32-S3. Cellular/GNSS module: SIMCom SIM7670G.
- Current P0 is **Mock-first**:
  - Wi-Fi temporarily simulates the 4G data path.
  - GNSS is simulated in software.
  - Wake events are simulated by CLI/button/timer.
  - The PC acts only as a local simulator; this is not the formal EGO Base.
- Do not add cloud services or external hosted AI dependencies to the Ego Link product path.

## Repository boundaries

- `firmware/`: ESP-IDF firmware and hardware abstraction.
- `pc_simulator/`: local PC-side simulator, protocol endpoint, dashboard, and test utilities.
- `quality_tests/`: repeatable tests and contract checks.
- `docs/`: architecture, protocol, development and verification records.
- `scripts/`: local developer and automation utilities.
- `autodev/`: automation control files. Codex may read this directory but must not modify it.

## Automatic development rules

1. Work on exactly one backlog task per Codex run.
2. Treat the current task JSON embedded in the prompt as the task contract.
3. Modify only paths listed in `allowed_paths`.
4. Never modify:
   - `.git/`
   - `autodev/`
   - `AGENTS.md`
   - repository-wide configuration, unless the current task explicitly allows it.
5. Do not run Git commit, push, reset, clean, checkout, switch, rebase, or merge. The supervisor owns Git operations.
6. Do not install packages or access the network unless the task explicitly allows it.
7. Do not start long-running foreground processes such as serial monitors, MQTT brokers, web servers, `tail -f`, or watch mode.
8. Inspect existing code before editing. Preserve existing conventions and avoid unrelated refactoring.
9. Run every verification command specified by the task when possible.
10. Hardware-dependent behavior must be reported as unverified unless physical hardware was actually exercised.
11. A passing build is not evidence that 4G registration, GNSS fix, calling, or power consumption works on hardware.
12. Return the final result in the structured format requested by the supervisor.

## P0 engineering principles

- Business logic depends on abstractions, not directly on Wi-Fi, SIM7670G, GNSS, or a wake chip.
- Every uplink event has a stable `device_id`, monotonically increasing `seq`, and timestamp.
- SOS and safety-critical behavior use deterministic rules; they do not depend on an LLM decision.
- Preserve local-first and privacy-first behavior.
- Prefer small, reversible, testable changes.

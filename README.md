# EgoLink

**A wearable connection between personal AI and the physical world.**

[中文](README.zh-CN.md) · [EgoLabs](https://github.com/getegoai) · [Project Ego](https://github.com/getegoai/ego) · [getego.ai](https://getego.ai) · [Roadmap](docs/ROADMAP.md)

EgoLink combines location, motion sensing, cellular communication, and physical user controls. We are developing its hardware, firmware, backend, and tools together, starting with location, two-way cellular calling, and a physical SOS workflow.

It is the wearable part of [Ego](https://github.com/getegoai/ego), our longer-term project for personal AI under the user's control. EgoBase is the planned user-controlled endpoint for history, context, and further processing. Basic device interaction and help requests are intended to keep working when Base or AI is unavailable.

## Current status

**This first public version contains the product definition and roadmap. The actual implementation is being prepared for import; there is no buildable firmware or backend in this version yet.**

The project already has an engineering prototype built around ESP32-S3 and an ML307A cellular module. Project records from October 21–22, 2026 report cellular registration, telemetry upload, local logging, queued upload recovery, a connected VoLTE call, and an SOS backend alert on the custom PCB1.

These are bounded bench results. Representative location, full-duplex calling, and end-to-end SOS product acceptance remain open. Hardware rework is still needed. Battery life, model accuracy, and a fully local data path are not established; current development includes a server-side collection path.

We will publish the existing product work and continue developing it here, including known problems and incomplete features.

## Implementation being imported

| Planned path | Existing work |
|---|---|
| `firmware/` | ESP32-S3 firmware, custom-board bring-up, sensing, device state, communication, and local logging |
| `hardware/` | Prototype hardware and mechanical materials, with revision-specific limitations |
| `server/` | Telemetry, history, alerts, and web interfaces; existing Python and Java components |
| `shared/contracts/` | Versioned observation, state, event, command, and receipt schemas |
| `pc_simulator/`, `quality_tests/` | Development, replay, calibration, and verification tools |

The import will state which runtime and board each component supports. These paths are not present in this initial documentation version.

## Next development

- Resolve custom-board issues and improve independent battery-powered operation.
- Verify the complete audio/call and SOS workflows, location quality, and outage/restart recovery.
- Connect a minimum user-controlled EgoBase storage and replay endpoint.
- Continue through real commits, issues, and pull requests; see the [roadmap](docs/ROADMAP.md).

## Participate

Contribute to the device and software: report a problem, review a protocol, test a supported board, improve documentation, or propose code. Start with [issues](https://github.com/getegoai/egolink/issues) or [CONTRIBUTING.md](CONTRIBUTING.md).

## License

The original documentation in this initial publication is licensed under **CC BY 4.0**; see [LICENSE](LICENSE). Our own software is intended to use **Apache-2.0** when imported with an explicit license. Hardware, models, data, and third-party materials will be identified and licensed separately.

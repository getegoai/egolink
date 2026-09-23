---
document_status: authoritative
decision_updated: 2026-09-23
last_verified: 2026-09-23
reviewed_at: 2026-09-23
verified_by: founder/gemini
---

# Ego Link Current Status

## Current outcome and ownership

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
and [ADR-0017](../architecture/adr/ADR-0017-ai-native-ego-state-flywheel.md)
record the founder's direction: active ego-state estimation, local-first Ego Base,
native cellular calling primary, and AI-Native self-supervised continuous learning
flywheel (Phase 1 task [AI-010](../tasks/active/AI-010_AI_NATIVE_FLYWHEEL_HARVESTER.md)).
Advanced AI does not create a new product Gate. Gemini owns the retained single-board
recovery/route-transition milestone and D2/FIELD-020; Codex completed
[ALIGN-STATE-010](../tasks/done/ALIGN-STATE-010_DECISION_AND_STATE_TRUTH.md).
The [coordination note](CODEX_GEMINI_HANDOFF_20260922.md) defines shared-file seams.

## Last reported runtime, distinct from source

The latest recorded application is Boot 211 on `connectivity-node-001`, CH343
`COM3`, reported 2026-09-23. Completed continuous 7-hour field session (10:16~17:16).
Full app/ELF hashes, inherited evidence and gaps are in [ACTIVE_BUILD](ACTIVE_BUILD.md).

| Slice | Evidence and scope | Remaining limitation |
|---|---|---|
| GNSS/Cell/QMI8658/MAX17048 + LTE | Boot 211 9/23 7h field run: 8,724 records, 285 GNSS 3D fixes (66%, up to 22 sats, HDOP 0.62, 4.69 km cumulative trajectory, max 14.9 km/h); continuous MAX17048 power curve | Ground-truth error against survey references |
| Manual Camera -> LTE -> private API | [Run015, 9/16](../hardware/CAMERA_LTE_MANUAL_CLOSURE_20260916.md): matching JPEG hash | One bounded USB-powered engineering run |
| Ordinary-upload throughput | Run017: 248/248 in 600s, final queue zero; Boot 211: 8,724 records over 7h LTE PPP upload with 0 reboot | Not 48h result |
| Preview/export and battery timer | 9/17 preview/export; 9/18 run019 Boot142, 3 scheduled photos and a separate STOP case; [packet](../tasks/active/P0-CONVERGENCE-20260905.md) | Complete raw evidence index still needed; not a carry/representative-day or 48h result |
| Ego-state | Boot 211 9/23: 831 live state inferences (walking: 82, running: 6, vehicle: 1, stationary: 683, indoor: 58) across 7h trip; AI-Native continuous learning flywheel Phases 1-5 completed (Harvester AI-010, TinyML 1D-CNN AI-020, Dual-Track Shadow Evaluator & Safety Kernel AI-030, Fine-Tuning & Model Packaging AI-040, Ego Base Diary Synthesizer AI-050) | Full on-device ESP-DL execution |
| Cellular call | 9/23: Web->Cloud->Modem AT dispatch pipeline verified with ACK; SIM7670G-MNGV data-only module lack of VoLTE/audio codec confirmed on hardware | Audio-capable carrier board required for ringing phone call |
| Ego Base | Synchronously planned private endpoint | Not implemented or deployed; current VPS storage is an engineering transition, not local-first completion |

The 9/21 bicycle note reports outbound fixes and return no-fix. Inverted pocket
placement/body attenuation is an untested explanation, not a demonstrated cause.
Ground-truth error and controlled placement comparisons belong to Gemini's D2 run.

## Remaining work, in execution order

Codex's decision/image/backlog, state-truth, API/Web and WIP repair is complete
as offline source. Acceptance details are in [the verification record](../verification/ALIGN_STATE_010_20260922.md).

1. Gemini: bind one candidate/config/recovery manifest; prove outage capture,
   same-file/same-ID reboot recovery, quota/corruption/loss accounting, actual
   Wi-Fi/LTE controlled transition and short independent-power carry operation.
2. Gemini: run [FIELD-020](../tasks/active/FIELD-020_L1_FIELD_DATASET.md) and D2
   reference-point metrics. Already recorded preview and timer cases require
   scoped regression on the new candidate, not blanket reclassification as unrun.
3. Queued independent work: minimal Ego Base lifecycle, cellular/audio A0 path,
   power/reliability and qualified China pre-compliance. RTC CALL-020/021 stay
   paused; full SOS resumes against the primary cellular path after its inputs exist.

## Product Gates

| Gate | State | Missing acceptance |
|---|---|---|
| P0-LOC | NOT_RUN | Representative location scenarios and reference metrics |
| P0-CALL | NOT_RUN | Primary cellular inbound/outbound calls and real full-duplex audio |
| P0-SOS | NOT_RUN | Physical trigger, independent local/durable/remote outcomes and human contact |

Power/48h, reliability, water/acoustics, RF, NPI, security/privacy and compliance
remain mandatory release evidence. No code, build, schema or bench result closes them.

## Validation and traceability

The 9/22 frozen run completed 1,867 tests: 1,860 passed and 7 environment/opt-in
skips (300.883 s). Context lint, diff checks, 27 snapshot hashes and the no-flash
ESP-IDF camera/collection build passed. The earlier 9/21 run was 1,820 passes
plus 13 skips, not 1,833 executed passes. Source checks do not refresh the
hardware date above. Independent ego frames resolve the new camera/state frame
overflow; the pre-existing all-source-loss health overflow remains explicitly
assigned in the [Gemini handoff](CODEX_GEMINI_HANDOFF_20260922.md).

Full prior chronology, image history, failures and migration map are preserved in
[the 9/22 source archive](../archive/alignment/20260922/README.md). The
[9/21 review](../roadmap/PROJECT_REVIEW_20260921.md) remains a dated audit, not a
second current task scheduler.

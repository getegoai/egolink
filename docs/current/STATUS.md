---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-09-21
reviewed_at: 2026-09-22
verified_by: founder/codex
---

# Ego Link Current Status

## Current outcome and ownership

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
records the 9/19 founder direction and 9/22 alignment: active ego-state estimation,
local-first Ego Base, native cellular calling primary and RTC auxiliary. Advanced
AI does not create a new product Gate. Gemini owns the retained single-board
recovery/route-transition milestone and D2/FIELD-020; Codex completed
[ALIGN-STATE-010](../tasks/done/ALIGN-STATE-010_DECISION_AND_STATE_TRUTH.md).
The [coordination note](CODEX_GEMINI_HANDOFF_20260922.md) defines shared-file seams.

## Last reported runtime, distinct from source

The latest recorded application is Boot 188 on `connectivity-node-001`, CH343
`COM3`, reported 2026-09-21. Firmware version/run strings still say run021; the
older document heading's run022 label is not a separate image identity. Full
app/ELF hashes, inherited evidence and gaps are in [ACTIVE_BUILD](ACTIVE_BUILD.md).
The 9/22 source repair has not been flashed or deployed by Codex.

| Slice | Evidence and scope | Remaining limitation |
|---|---|---|
| GNSS/Cell/QMI8658/MAX17048 + LTE | Boot171/188 reported real probes and LTE uploads, latest 9/21 | No representative location-accuracy or endurance acceptance |
| Manual Camera -> LTE -> private API | [Run015, 9/16](../hardware/CAMERA_LTE_MANUAL_CLOSURE_20260916.md): matching JPEG hash | One bounded USB-powered engineering run |
| Ordinary-upload throughput | Run017: 248/248 in 600s, final queue zero; documented in the same report | Not long-run, outage or field proof |
| Preview/export and battery timer | 9/17 preview/export; 9/18 run019 Boot142, 3 scheduled photos and a separate STOP case; [packet](../tasks/active/P0-CONVERGENCE-20260905.md) | Complete raw evidence index still needed; not a carry/representative-day or 48h result |
| Ego-state | Boot188 reported state upload/storage; 9/22 source repair committed as `3a0728058` with C/PC/API/Web regression | Unflashed/undeployed; Boot188 score 0.83 was an estimator output, not accuracy |
| Cellular call | AT state machine and initialization reported | configure logging is not proof of successful configuration; no accepted dialing/answering or bidirectional audio |
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

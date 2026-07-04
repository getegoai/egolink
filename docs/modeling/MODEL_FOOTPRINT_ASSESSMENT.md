---
document_status: authoritative
last_verified: 2026-07-04
verified_by: codex
---

# MODEL-001 Model Footprint Assessment

MODEL-001 defines how Ego Link will measure RAM, flash, latency, and
per-inference energy for MotionNet-class on-device AI. It supports V1-M3 model
work and PROD-001 MCU selection.

This document is the assessment protocol and baseline. It does not train a
model, change model behavior, change firmware, change schemas, select a
production MCU, replace `TBD(MODEL-001)` values in production requirements, or
claim that ESP32-S3 or any candidate MCU is sufficient.

## Readiness Rule

No model-footprint value is verified until it is tied to:

- model artifact identity and hash;
- dataset or synthetic input manifest;
- runtime and kernel version;
- firmware or benchmark build identity;
- measurement environment;
- evidence path;
- reviewer outcome.

Estimates are useful for planning, but must remain marked `estimated` until a
matching build and runtime measurement exist.

## Evidence Levels

| Level | State | Meaning | May fill PROD-001 budget? |
|---|---|---|---|
| L0 | `protocol_defined` | MODEL-001 has a measurement protocol and report schema. | No |
| L1 | `artifact_estimated` | A candidate model has estimated parameters, ops, and tensor arena needs. | No |
| L2 | `build_verified` | Firmware or benchmark build includes the model/runtime and reports static size. | No |
| L3 | `runtime_measured` | Device or evaluation-board run reports peak RAM and inference latency. | Partially, marked engineering |
| L4 | `power_measured` | A power rig measures sleep-vs-inference current or energy per inference. | Partially, marked engineering |
| L5 | `candidate_compared` | ESP32-S3 and production MCU candidates are compared with the same model and evidence class. | Yes, with founder review |

`TBD(MODEL-001)` in production requirements may only be replaced by an L5
candidate comparison or an explicitly accepted engineering exception.

## Candidate Scope

MODEL-001 starts with MotionNet-class inference because it is the first V1
on-device AI dependency.

Initial model families to measure:

- statistical or threshold baseline;
- small 1D-CNN;
- lightweight TCN;
- CNN plus TinyGRU only if earlier candidates fail the quality/latency tradeoff.

Initial hardware candidates:

- ESP32-S3 development baseline;
- STM32U5A5 candidate;
- Apollo4 Blue Lite or Plus candidate.

Candidate MCU rows remain `unverified` until official datasheet, EVB identity,
toolchain/runtime support, and measurement logs are attached.

## Measurement Axes

Every report must cover:

- Model artifact: model name, version, artifact path, artifact hash, parameter
  count, input shape, quantization, ops/MACs estimate, weight bytes, tensor
  arena estimate, and feature-generator version.
- Static firmware footprint: build profile, firmware image bytes, `.text`,
  `.rodata`, `.data`, `.bss`, model weight placement, OTA/rollback slot
  assumption, and filesystem/log storage assumption.
- Runtime RAM: heap before/after model init, peak heap delta, tensor arena
  bytes, stack high-water marks, DMA/audio/display buffers that coexist with
  inference, and fragmentation notes.
- Latency: warm-up count, input window duration, inference P50/P95/max,
  end-to-end candidate latency, clock frequency, runtime/kernel backend, and
  concurrency assumptions.
- Power: sleep current, sensor-gate current, wake-to-infer current, inference
  current, inference duration, energy per inference, duty-cycle assumption, and
  measurement rig identity.
- Integration risk: LTE/GNSS/display/audio concurrency, watchdog/reset impact,
  OTA space, secure boot/rollback needs, and degraded no-LTE behavior.

## Minimum Report Manifest

Each MODEL-001 evidence report should include:

```text
model_id
model_version
artifact_hash
input_manifest
runtime_backend
firmware_or_benchmark_version
hardware_candidate
evidence_level
ram_peak_bytes
flash_total_bytes
latency_p50_ms
latency_p95_ms
latency_max_ms
energy_per_inference_mj
power_profile
measurement_environment
source_status
known_gaps
reviewer_outcome
evidence_paths
```

Unknown values must stay `unknown` or `unverified`; do not infer them from a
board name or vendor class.

## Acceptance Gates

MODEL-001 remains active until these gates are complete:

- Protocol baseline: this document exists and a quality test protects the
  non-claim boundary.
- ESP32-S3 static footprint: one MotionNet-class artifact or representative
  fixture has L2 `build_verified` static size evidence.
- ESP32-S3 runtime footprint: the same artifact reaches L3
  `runtime_measured` latency/RAM evidence.
- Power footprint: the same artifact reaches L4 `power_measured`
  sleep-vs-inference energy evidence or is explicitly deferred to PWR-001
  measurement readiness.
- Candidate comparison: ESP32-S3, STM32U5A5, and Apollo4 rows are compared at
  the same evidence level, or gaps are recorded as blockers.
- Production requirement update: PROD-001 `TBD(MODEL-001)` values are replaced
  only after the accepted comparison is reviewed.

## Non-Claims

- This protocol does not claim MotionNet accuracy, fall-detection acceptance,
  proactive-alert quality, or product safety performance.
- A passing build is not runtime RAM, latency, or power evidence.
- ESP32-S3 being the development baseline does not make it production
  sufficient.
- Vendor datasheet numbers do not replace measured app-level footprint.
- AudioGate, VisionGate, and learned ContextRouter budgets remain future
  extensions unless a later task explicitly brings them into scope.

## Next Steps

1. Create a small synthetic MotionNet-class benchmark fixture after DATA-002,
   M1 recorder, and labeling expectations are aligned.
2. Add an offline/static footprint exporter for artifact metadata and build
   size records.
3. Add an ESP32-S3 runtime measurement path only when a real artifact or
   representative fixture is available.
4. Feed power measurements into PWR-001/PWR follow-on evidence instead of
   estimating inference energy from build output.
5. Update PROD-001 only after a reviewed MODEL-001 comparison exists.

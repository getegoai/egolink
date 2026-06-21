# Safety Companion Architecture

## Position

Ego Link uses a shared "safety companion" core instead of splitting early into
separate child, elder, cycling, pet, and asset products. The first product line
stays focused on an AI-assisted safety locator: the device observes, routes
risk, applies deterministic safety rules, and uploads structured evidence only
when needed.

The approach from `模型架构.md` is feasible for the current project, with one
important constraint: P0 must start with contracts and rule baselines, not an
unverified neural network. Models can later be delivered as versioned packages
once real data collection is stable.

## Safety Loop

```text
sensor capture
  -> edge event detection
  -> edge risk routing
  -> deterministic local safety rule review
  -> structured event and evidence upload when needed
  -> Ego Base / PC Simulator assessment
  -> command back: ask, remind, collect more evidence, or escalate
```

## P0 Event Classes

P0 keeps the first event set deliberately small:

1. Manual SOS.
2. Possible fall, impact, or crash.
3. Long stationary period after impact.
4. Abnormal stay or safe-zone deviation.
5. Distress audio or abnormal loud sound.
6. Device risk such as low battery, link loss, or GNSS no-fix.

SOS, emergency calling, privacy disable, and other safety-critical actions must
remain deterministic. A model may provide risk scores, reason codes, and action
recommendations, but must not be the sole authority for emergency behavior.

## Ownership Boundary

Model owner responsibilities:

- Event taxonomy, data schemas, and model input/output contracts.
- Data collection and labeling specifications.
- Baseline rules, replay tooling, and model contract tests.
- MotionNet, AudioGate, ContextRouter, VisionGate, teacher models, distillation,
  quantization, model cards, thresholds, and versioned artifacts.

Codex integration responsibilities:

- Firmware drivers, sensor capture, ring buffers, timestamps, queues, transport,
  runtime adapters, hardware tests, and dashboard integration.
- Mapping existing Ego Link events into stable model inputs.
- Consuming model outputs through adapters that can switch between mock and real
  implementations.
- Recording integration issues rather than changing model semantics directly.

User responsibilities:

- Real-world scenario testing, data authorization, risk-rule approval, and final
  acceptance.

## Versioned Package Flow

Model work should arrive as a versioned overlay package, for example:

```text
EGOLINK_SAFETY_COMPANION_M0_V0_1.zip
EGOLINK_SAFETY_COMPANION_M1_V0_2.zip
EGOLINK_SAFETY_COMPANION_MODEL_V0_3.zip
```

Expected package content:

```text
docs/modeling/MODEL_HANDOFF.md
docs/modeling/INTEGRATION_TASKS.md
shared/contracts/
model_lab/
model_artifacts/
quality_tests/model_contract/
```

Codex may integrate the package, but should not silently rewrite model source,
artifacts, thresholds, feature order, field names, units, or contract semantics.
If a contract is hard to integrate, record it in
`docs/modeling/INTEGRATION_ISSUES.md`.

## Roadmap

### M0: Contracts And Rule Baseline

Deliver stable schemas, event definitions, a ContextRouter baseline, simulated
data, replay tooling, contract tests, and integration tasks. Codex maps current
mock GNSS, wake, SOS, sensor samples, and device risk events into the model
input contract and consumes model-like structured output.

### M1: Real Data Collection

Define recording format, directory layout, labeling flow, sample rates, windows,
and quality checks. Codex implements IMU/audio/GNSS/4G/button capture, unified
timestamps, event windows, and export manifests.

### M2: MotionNet Plus ContextRouter

Use motion and context first. Initial classes include normal activity,
stationary, impact, fall candidate, post-impact stationary, and not worn.
ContextRouter combines motion, GNSS, audio scores, network state, battery, base
availability, and recent history.

### M3: AudioGate

Add VAD, distress sound detection, abnormal sound detection, recording quality
checks, and short audio snippets around event triggers.

### M4: VisionGate

Use the camera only after events or explicit requests. Edge checks should decide
whether an image is too dark, blurry, blocked, contains a person, or is worth
uploading. Complex visual understanding remains in Ego Base.

### M5: Quantized Device Deployment

Model owner provides INT8 artifacts, normalization parameters, thresholds, PC
reference outputs, and firmware consistency vectors. Codex integrates with
ESP-DL, ESP-SR, or TFLite Micro only after M0/M1 evidence is stable.


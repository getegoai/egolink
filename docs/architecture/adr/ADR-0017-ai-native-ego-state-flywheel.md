---
document_status: accepted_decision
decision_updated: 2026-09-23
reviewed_at: 2026-09-23
authority_basis: founder_decision_20260923
implementation_status: in_progress
---

# ADR-0017: AI-Native Ego-State Estimation and Continuous Learning Data Flywheel

- Status: accepted
- Decision date: 2026-09-23
- Decision owner: founder
- Scope: AI-Native state estimation architecture, multi-modal self-supervised data flywheel, edge/base hierarchy, shadow evaluation, and OTA weight decoupling

---

## 1. Context and Decision Trigger

On 2026-09-23, EgoLink achieved its first continuous 7-hour outdoor field milestone (Boot 211, 8,724 telemetry records streamed over 4G LTE PPP, 285 GNSS 3D fixes, 831 battery samples, 0 reboots, 0 watchdog panics, and no noticeable device heating). This verified that the physical hardware, power, modem, and sensor capture pipeline are sufficiently robust for real daily wear.

Following this verification, the founder established a strategic paradigm shift:
1. **Transition from heuristic thresholds to AI-Native Active Ego-State Estimation**: Hardcoded rules (e.g. fixed acceleration RMS thresholds in `ego_state_engine.c`) cannot generalize across varying wearing postures (neck pendant, trouser pocket, backpack, desk) or complex real-world dynamics (metro transit, elevators, escalators, stop-and-go vehicles).
2. **MVP-First Continuous Learning Flywheel**: We do not wait for theoretical model perfection before product deployment. The initial product enters daily real-world usage scenarios, driving an autonomous closed-loop data flywheel: *daily real-world data collection -> automated cross-modal pseudo-labeling -> model retraining & knowledge distillation -> shadow evaluation & safety gating -> decoupled lightweight weight OTA -> steadily compounding device AI capability*.

---

## 2. AI-Native Hierarchical Estimation Architecture

EgoLink state estimation operates in three hierarchical, privacy-respecting tiers:

### Tier 1: Edge Real-Time Micro-Motion (ESP32-S3 TinyML, L1)
- **Inputs**: High-frequency 6-axis IMU (20Hz/50Hz accelerometer and gyroscope sliding windows, e.g. 5-second / 100-sample window).
- **Model**: Ultra-compact 1D-CNN or Temporal Convolutional Network (TCN), quantized to INT8 using ESP-DL / TFLite Micro (~15 KB to 30 KB weight footprint).
- **Latency & Power**: Inference time $< 5\,\text{ms}$ on ESP32-S3 dual-core 240MHz with SIMD vector extensions; negligible power delta.
- **Outputs**: High-confidence physical activity primitives (Stationary, Walking, Running, Cycling, Shock/Impact, Fall Suspected).
- **Offline Invariant**: Fully executed on-device with zero network latency and complete privacy.

### Tier 2: Macro-Mobility & Spatial Context (Edge/Base Fusion, L2)
- **Inputs**: Tier 1 micro-motion states + GNSS kinematic velocity vectors/HDOP + Cellular Cell-ID/RSRP handovers + Wi-Fi environment counts.
- **Inference**: Contextual state machine (In-Vehicle, Indoor Weak GNSS, Outdoor Pedestrian Transit, Stationary Dwell).

### Tier 3: Diurnal Semantic Storylines (Ego Base / Private Large Model, L3)
- **Inputs**: Day-long multi-modal evidence chains synchronized to the home station (Ego Base) during nightly charging.
- **Model**: Sequence Transformer / Small Language Model (e.g. 2B-parameter local LLM on Ego Base).
- **Outputs**: Structured life journals, circadian routine baselines, personalized mobility health reports, and proactive guardian anomaly insights.

---

## 3. The 5-Stage Closed-Loop Data Flywheel

The self-improving flywheel operates autonomously without expensive manual human labeling:

```text
       ┌────────────────────────────────────────────────────────┐
       │                                                        │
       ▼                                                        │
┌──────────────┐     ┌──────────────┐     ┌──────────────┐      │
│ 1. 真实佩戴采集 │ ──> │ 2. 跨模态自监督│ ──> │ 3. 轻量模型训练│ ─────┤
│ (日常出行/边缘)│     │   自动标注   │     │   与知识蒸馏 │      │
└──────────────┘     └──────────────┘     └──────────────┘      │
                            │                                   │
                            ▼                                   │
                     ┌──────────────┐     ┌──────────────┐      │
                     │ 4. 影子评估   │ ──> │ 5. 独立模型   │ ──────┘
                     │   与安全门禁 │     │   分区 OTA   │
                     └──────────────┘     └──────────────┘
```

### Stage 1: Edge Uncertainty Mining (端侧不确定度挖掘)
- When the edge TinyML model is highly confident (entropy $< \epsilon$), it executes normally and emits compact telemetry.
- When the model encounters high entropy (e.g. $P(\text{walking}) \approx P(\text{in\_vehicle})$) or cross-sensor contradiction (e.g. IMU indicates high RMS but GNSS Doppler speed is $0.0\,\text{m/s}$ and Wi-Fi APs are stationary), the edge flags the window as an **Ambiguity Gold Sample** and marks it for pipeline intake.

### Stage 2: Cross-Modal Self-Supervised Auto-Labeling (跨模态自然自监督)
Sensors act as physical ground-truth teachers for each other:
1. **GNSS Doppler Speed $\rightarrow$ IMU Teacher**:
   - In open-sky conditions with verified 3D fix and HDOP $< 2.0$, persistent ground speed $12 \le v \le 20\,\text{km/h}$ automatically pseudo-labels concurrent IMU vibration patterns as `cycling`.
   - Speed $v \ge 25\,\text{km/h}$ automatically pseudo-labels concurrent IMU patterns as `in_vehicle`.
2. **Cellular & Wi-Fi Stability $\rightarrow$ Indoor Anchor**:
   - GNSS loss combined with unchanged serving Cell-ID and $\ge 3$ fixed Wi-Fi BSSIDs automatically pseudo-labels the state as `indoor_stationary` or `indoor_pedestrian`.
3. **Power Telemetry $\rightarrow$ Absolute Resting Baseline**:
   - MAX17048 `is_charging=true` combined with zero IMU variance provides deterministic ground truth for `resting_desk_or_sleep`.

### Stage 3: Base Retraining & Knowledge Distillation (基站训练与模型蒸馏)
- Ego Base or development server ingests self-supervised candidate windows.
- A bi-directional Teacher Transformer performs offline retrospective smoothing over the entire session to resolve ambiguity.
- Knowledge distillation trains the Student 1D-CNN (INT8), optimizing for both cross-entropy loss against pseudo-labels and KL divergence against Teacher logits.

### Stage 4: Shadow Evaluation & Safety Invariant Gate (影子评估与安全红线)
- **Shadow Mode (影子双轨运行)**: Upgraded candidate models run in shadow mode on-device or in simulation, outputting shadow predictions alongside production rules to verify agreement without affecting live safety outputs.
- **Safety Kernel Invariant (North Star)**:
  - **Deterministic Safety Kernel takes absolute precedence**.
  - Physical button SOS, critical low-power shutdown, and unvetoed emergency alerts can **NEVER be delayed, suppressed, or vetoed by AI inference**.
  - AI enhances awareness and contextual fidelity; deterministic safety guarantees user protection.

### Stage 5: Decoupled Model Partition OTA (模型权重独立分区热更)
- ESP32-S3 Flash partition layout reserves a dedicated, non-executable data partition (`model_weights`, ~64 KB to 128 KB).
- Model updates transfer only the compact quantized tensor matrix (~20 KB to 30 KB) over 4G LTE / Wi-Fi in seconds.
- No risk of bricking core FreeRTOS, modem drivers, or cellular network stack during model evolution.

---

## 4. Phased Implementation Roadmap

1. **Phase 1: Ingestion & Self-Supervised Harvester (Immediate Mainline)**
   - Maintain current firmware rule engine untouched.
   - Implement `scripts/harvest_self_supervised_dataset.py` to ingest real-world field telemetry (such as Boot 211), perform sliding window segmentation, compute cross-modal teacher pseudo-labels, and output dataset manifests.
2. **Phase 2: TinyML Architecture & PC Simulator Benchmark**
   - Design the 1D-CNN INT8 topology.
   - Train on the harvested real-world dataset.
   - Evaluate classification accuracy, confusion matrices, and corner-case robustness in PC simulator and Python tests.
3. **Phase 3: Firmware Shadow Integration & Model Partition OTA**
   - Integrate ESP-DL / TFLite Micro runtime into firmware.
   - Allocate `model_weights` partition in partition table.
   - Run in shadow mode on hardware, streaming comparison metrics to Message Hub.
4. **Phase 4: Full Ego Base Flywheel & L3 Semantic Reports**
   - Connect Ego Base private home station pipeline.
   - Generate automated daily structured user status and health journals.

---

## 5. Architectural Consequences

- **Positive**:
  - Eliminates manual annotation bottlenecks through physical sensor cross-supervision.
  - Keeps wearable hardware cool and low-power while compounding AI capabilities week over week.
  - Fully adheres to Local-First and Strong Privacy principles (`ADR-0016`).
  - Strict Safety Kernel separation prevents AI hallucinations from endangering life safety.
- **Constraints**:
  - Raw private GPS coordinates used for Doppler speed supervision must remain within the user's private data boundary and must not be leaked into public training repositories.
  - Model weights must pass golden regression test suites before candidate promotion.

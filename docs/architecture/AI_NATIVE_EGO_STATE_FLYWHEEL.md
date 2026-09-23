---
document_status: authoritative
decision_updated: 2026-09-23
last_verified: 2026-09-23
verified_by: founder/antigravity
owner: founder
---

# AI-Native Ego-State Estimation and Continuous Learning Data Flywheel

This document defines the authoritative system architecture for AI-Native Active Ego-State Estimation and the autonomous continuous learning data flywheel in EgoLink, establishing the execution foundation accepted by [ADR-0017](adr/ADR-0017-ai-native-ego-state-flywheel.md) and governed by the [North Star](../product/NORTH_STAR.md).

---

## 1. System Overview and Core Vision

EgoLink is a wearable active ego-state estimation and guarding system. Rather than relying indefinitely on fragile, hardcoded heuristics (e.g. static accelerometer variance thresholds), the system is architected as an **AI-Native, self-evolving multi-modal intelligence loop**.

The core operational philosophy adheres to three non-negotiable principles:
1. **MVP-First into Real-World Usage**: We do not wait for a theoretically complete model before deploying. Deploying the robust MVP hardware into daily real-world scenarios generates the authentic multi-modal sensor stream required to drive continuous model evolution.
2. **Cross-Modal Self-Supervised Data Flywheel**: Multiple on-board sensors (IMU, GNSS Doppler speed, Cellular Cell-ID handovers, Wi-Fi environment, and battery fuel gauge) serve as physical ground-truth teachers for one another, enabling 90%+ autonomous pseudo-labeling without expensive manual human annotation.
3. **Safety Kernel Supremacy**: AI models enrich context, resolve ambiguous micro-motions, and reconstruct user life narratives, but **can never veto, delay, or suppress the deterministic Safety Kernel** (physical SOS, battery emergency protection, and unvetoed alerting).

---

## 2. Multi-Tier Hierarchical Inference Architecture

The system splits estimation across three distinct tiers to balance real-time responsiveness, battery endurance, and deep semantic intelligence:

```text
+-----------------------------------------------------------------------------------+
| Tier 3: Diurnal Semantic Storylines (Ego Base / Local LLM)                        |
| - Offline retrospective transformer modeling over 24h timeline                    |
| - Natural language daily health/activity journals, anomaly insight                |
| - Private, local-first execution during nightly charging                          |
+------------------------------------------^----------------------------------------+
                                           | Local Wi-Fi / Private Relay Sync
+------------------------------------------v----------------------------------------+
| Tier 2: Macro-Mobility & Spatial Context (Edge / Base Fusion)                     |
| - Multi-sensor fusion: Tier 1 primitives + GNSS kinematic vector + Cellular/Wi-Fi  |
| - Context states: In-Vehicle, Outdoor Pedestrian Transit, Indoor Dwell, Charging  |
+------------------------------------------^----------------------------------------+
                                           | Micro-Motion States (1Hz - 0.2Hz)
+------------------------------------------v----------------------------------------+
| Tier 1: Real-Time Micro-Motion (ESP32-S3 Edge TinyML)                             |
| - 20Hz/50Hz 6-axis IMU (QMI8658) 5-second sliding windows (100 samples)          |
| - Ultra-compact 1D-CNN INT8 (~20KB weights, ESP-DL / TFLite Micro)               |
| - Sub-second latency (< 5ms), < 30KB SRAM, zero cloud dependency, 100% offline    |
| - States: Stationary, Walking, Running, Cycling, Impact Shock, Fall Suspected     |
+-----------------------------------------------------------------------------------+
```

---

## 3. Edge TinyML Specification (Tier 1)

### Hardware Targets & Computational Budget
- **Processor**: ESP32-S3 Dual-Core Xtensa® 32-bit LX7 @ 240MHz with vector instructions (PIE).
- **Runtime Engine**: ESP-DL (Espressif Deep Learning Library) or TensorFlow Lite for Microcontrollers (TFLite Micro).
- **Weight Footprint**: $\le 32\,\text{KB}$ (quantized INT8).
- **Inference SRAM**: $\le 24\,\text{KB}$ tensor arena in internal SRAM (no PSRAM power penalty).
- **Execution Latency**: $\le 5\,\text{ms}$ per 5-second window inference (duty-cycled, $< 0.1\%$ CPU utilization).

### Input Tensor Definition
- **Sampling Frequency**: $20\,\text{Hz}$ (configurable up to $50\,\text{Hz}$).
- **Sliding Window**: $5.0\,\text{seconds}$ (100 temporal steps, $50\%$ overlap).
- **Channels (6 axes)**:
  1. $a_x$ (Linear Acceleration X, in $g$ or $\text{m/s}^2$)
  2. $a_y$ (Linear Acceleration Y, in $g$ or $\text{m/s}^2$)
  3. $a_z$ (Linear Acceleration Z, in $g$ or $\text{m/s}^2$)
  4. $g_x$ (Angular Velocity X, in $\text{dps}$)
  5. $g_y$ (Angular Velocity Y, in $\text{dps}$)
  6. $g_z$ (Angular Velocity Z, in $\text{dps}$)
- **Tensor Shape**: `[1, 100, 6]` (INT8 / Float32 normalized).

### Model Architecture (Compact 1D-CNN)
```text
Input: [1, 100, 6]
  │
  ├─► Conv1D(filters=16, kernel_size=5, stride=2, padding='same') + ReLU + BatchNorm
  │     Output: [1, 50, 16]
  │
  ├─► DepthwiseSeparableConv1D(filters=32, kernel_size=3, stride=2) + ReLU + BatchNorm
  │     Output: [1, 25, 32]
  │
  ├─► DepthwiseSeparableConv1D(filters=64, kernel_size=3, stride=2) + ReLU + BatchNorm
  │     Output: [1, 13, 64]
  │
  ├─► GlobalAveragePooling1D
  │     Output: [1, 64]
  │
  ├─► Dense(32) + ReLU
  │     Output: [1, 32]
  │
  └─► Dense(6, activation='softmax')
        Output: [1, 6] (Class Probabilities)
```

### Target Classification Primitives
1. `stationary`: User sitting, standing quietly, or device placed on a surface.
2. `walking`: Rhythmic cadence between $1.2\,\text{Hz}$ and $2.2\,\text{Hz}$.
3. `running`: High dynamic RMS with step frequency $> 2.5\,\text{Hz}$.
4. `cycling`: Moderate continuous cyclic vibration accompanied by forward kinematic speed.
5. `abnormal_shock`: High-amplitude mechanical impact ($> 2.5g / 25\,\text{m/s}^2$).
6. `fall_suspected`: High-G impact followed immediately by prolonged post-impact immobility ($< 0.15\,\text{m/s}^2$ RMS for $> 5\,\text{s}$).

---

## 4. The 5-Stage Continuous Learning Data Flywheel

The data flywheel automates the full cycle from field collection to on-device evolution:

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

### Stage 1: Edge Uncertainty Mining
The on-device model computes prediction entropy:
$$H(p) = - \sum_{i=1}^C p_i \log_2(p_i)$$
- **Low Entropy ($H(p) < \tau_{\text{low}}$)**: High model confidence. Device logs standard telemetry; no special action needed.
- **High Entropy ($H(p) \ge \tau_{\text{high}}$) or Sensor Conflict**:
  - Example: IMU indicates running/vibration, but GNSS reports $0.0\,\text{m/s}$ speed and fixed Wi-Fi BSSIDs (e.g. running on a treadmill or fidgeting at a desk).
  - The window is flagged as an **Ambiguity Gold Sample** and preserved with raw sensor context for ingestion.

### Stage 2: Cross-Modal Self-Supervision Algorithms
By leveraging physical invariants across different sensors, the system auto-labels training windows without human intervention:

| Target Class | Anchor Teacher Sensor | Physical Invariant Rule |
|---|---|---|
| `cycling` | GNSS Doppler ground speed | $10 \le v \le 22\,\text{km/h}$ continuously for $\ge 15\,\text{s}$, 3D Fix, HDOP $< 1.5$. |
| `in_vehicle` | GNSS ground speed & Cellular | $v \ge 25\,\text{km/h}$ OR rapid cell tower handovers ($> 2$ handovers in 2 minutes). |
| `indoor_stationary` | Wi-Fi BSSID + Cellular LAC/CID | Zero GNSS fix, $\ge 3$ consistent Wi-Fi APs, identical Cell-ID, IMU RMS $< 0.15\,\text{m/s}^2$. |
| `indoor_walking` | Wi-Fi RSSI gradient + IMU | Zero GNSS fix, Wi-Fi RSSI fluctuating, IMU step cadence $1.4 \sim 2.0\,\text{Hz}$. |
| `resting_sleep` | MAX17048 Fuel Gauge + IMU | `is_charging == true`, battery voltage $> 4.15\,\text{V}$, IMU variance $< 0.01\,\text{dps}^2$. |

### Stage 3: Ego Base Retraining & Knowledge Distillation
1. **Teacher Model**: A multi-modal bidirectional Transformer trained on long-sequence temporal windows (minutes to hours), fusing GNSS, cellular, and IMU data offline.
2. **Student Model**: The compact 1D-CNN running on ESP32-S3.
3. **Loss Function**:
   $$\mathcal{L} = (1 - \alpha) \mathcal{L}_{\text{CE}}(y_{\text{pseudo}}, \hat{y}_{\text{student}}) + \alpha \tau^2 \mathcal{L}_{\text{KL}}\left(\sigma\left(\frac{z_{\text{teacher}}}{\tau}\right), \sigma\left(\frac{z_{\text{student}}}{\tau}\right)\right)$$
   where $\tau$ is the temperature parameter and $\alpha$ balances hard pseudo-labels against soft teacher representations.

### Stage 4: Shadow Mode Evaluation & Safety Kernel Gate
- **Dual-Track Execution**: Before a newly trained model is promoted to active control, it runs on-device in **Shadow Mode**.
- The shadow model's inferences are recorded in telemetry alongside the existing rule engine outputs.
- **Safety Kernel Non-Negotiables**:
  - The deterministic safety kernel retains absolute authority over physical SOS triggers, emergency SMS/calls, and power cutoff.
  - An AI inference of `stationary` can **never override** a physical SOS button press.
  - A regression gate checks candidate models against a historical Golden Dataset; any false negative on simulated fall/shock samples causes an immediate build abort.

### Stage 5: Decoupled Model Partition OTA
To ensure rapid, safe updates without risks to core system firmware:
- **Flash Layout**:
  - `ota_0` / `ota_1`: Core FreeRTOS firmware, modem driver, network stack (1.5 MB - 2.0 MB).
  - `model_weights`: Dedicated raw data partition (64 KB - 128 KB).
- **Weight OTA Transfer**:
  - New model weights (~20 KB INT8 payload) are downloaded over 4G LTE HTTPS or local Wi-Fi in under 5 seconds.
  - Checked via SHA-256 integrity hash and cryptographic signature.
  - Reloaded dynamically into the inference engine memory buffer without requiring a full device reboot.

---

## 5. Phased Engineering Roadmap

```text
Phase 1: Multi-Modal Harvester & Auto-Labeling (Current Mainline)
  │  - Scripts to ingest real field runs (Boot 211+)
  │  - Self-supervised slicing and pseudo-label manifest generation
  │  - Zero firmware changes; hardware stability preserved
  ▼
Phase 2: TinyML Topology & PC Simulator Pipeline
  │  - Implement 1D-CNN model architecture in PyTorch/Keras
  │  - Train on harvested field dataset; evaluate F1 scores
  │  - Verify INT8 quantization and memory bounds
  ▼
Phase 3: ESP32-S3 Shadow Mode & Partition Decoupling
  │  - Integrate ESP-DL / TFLite Micro into ESP-IDF firmware
  │  - Allocate dedicated model_weights partition
  │  - Deploy dual-track shadow evaluation on hardware
  ▼
Phase 4: Ego Base Integration & L3 Semantic Diaries
     - Connect local Ego Base home station
     - Nightly auto-sync of full day evidence chains
     - Private local LLM life journal and guardian summary generation
```

---

## 6. Document and Authority References

- **Guiding Principles**: [NORTH_STAR.md](../product/NORTH_STAR.md)
- **Architectural Decision**: [ADR-0017](adr/ADR-0017-ai-native-ego-state-flywheel.md)
- **Local-First & Communications Decision**: [ADR-0016](adr/ADR-0016-local-first-ego-state-cellular-primary.md)
- **Context Routing**: [CONTEXT_INDEX.md](../CONTEXT_INDEX.md)
- **Active Build & Hardware State**: [ACTIVE_BUILD.md](../current/ACTIVE_BUILD.md)

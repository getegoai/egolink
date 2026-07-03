# Archive note

Moved from repository root `融合算法模型研讨.md` on 2026-07-03 during workspace
organization. This file is historical research input, not current authority.

根据 2026-06-30 的文档，当前方向判断是清楚的：**KR-003 已经把真实 LTE raw 主链路打通并冻结为关键基准，但下一步不能直接跳到“产品定位精度”或“训练模型”，而要先完成“多源证据统一接入、数据出口、可解释融合算法设计、短稳定性验证”四件事。** `LOCATION_DATASET.md` 已经把数据规则定义为“raw frame evidence → derived Web/API/event view → replayable observation window → labelled dataset sample → model or rule evaluation”，并明确不要从 Dashboard 临时状态直接训练；训练数据必须从 raw evidence、derived events、labels 和 manifest 重建。 `DATA-001` 的目标也是先建立 `test_run_id export → raw-frame lineage → derived features → observation windows → labels/quality checks → JSONL + manifest` 的可重复数据出口，而不是现在就训练或发布 learned fusion model。

我的建议是：**KR-004 作为“多源 observation baseline + EALE-P0 融合算法设计冻结”版本；KR-005 解决 reconnect/cache/retry/stability；KR-006 再做产品演示闭环。** 模型融合算法设计可以现在完成，但实现上应分成“规则/概率融合基线”与“后续学习型模型”两层。

---

## 一、当前阶段的核心判断

你现在不是在搭骨架，而是已经进入第一个主链路后的**关键版本演进阶段**。KR-003 的价值非常大，因为它把过去“盲测设备有没有上报位置”推进到“服务器能保存 raw frame、能产生 derived view、能解释 no-fix/失败状态、能断 USB 后外场复核”的阶段。

但 KR-003 之后最容易犯的错误是过早做“定位算法准确率”。现在数据还不够稳定，Wi-Fi / IMU / power 在真实 location path 上还没有全部验证，`LOCATION_DATASET.md` 也明确当前 Wi-Fi 是 contract/server/simulator baseline，firmware-side Wi-Fi observation 未验证；IMU 有 QMI8658 evidence，但尚未与 connectivity-node location observation 融合验证；power 字段存在但产品电池/功耗行为未验证。

所以当前战略应为：

**先做证据，不做结论；先做可解释，不做精度承诺；先做数据出口，不做模型训练；先做 server-side derived fusion，不改 device wire protocol。**

这与 `DATA-001` 的边界完全一致：该任务是 data foundation，不收集大语料、不训练模型、不评估定位精度、不改变 KR-003 raw LTE runtime loop。

---

## 二、下一步版本推进顺序

### 1. KR-004：多源 observation baseline，不急于宣称“融合定位”

KR-004 的正确目标不是“定位更准”，而是：

**把 GNSS / Cell-LTE / Wi-Fi / IMU / Power / Transport-runtime 全部接入同一个 observation evidence 体系，并且每个字段都能区分 real、unknown、unverified、mock、missing、failed。**

KR-004 应完成：

| 任务       | 目标                                                                           | 是否涉及融合算法              |
| -------- | ---------------------------------------------------------------------------- | --------------------- |
| LOC-005A | firmware-side Wi-Fi / IMU / power observation 接入真实或明确 unknown/unverified 数据  | 不做最终定位                |
| DATA-001 | 从 test_run_id 导出 observation window、features、labels、quality、privacy、manifest | 为算法准备数据               |
| OBS-003  | Web/API/报告展示当前 run、key release、failure reason、raw/derived evidence           | 让测试像产品控制台             |
| ALG-000  | 新增 `LOCATION_FUSION_ALGORITHM.md`，冻结 EALE-P0 融合算法设计                          | 只做设计冻结                |
| ALG-001  | 实现 server-side rule/probabilistic fusion baseline，可开关                        | 可以做 derived view，不改协议 |

KR-004 的 release 描述建议写成：

> KR-004: Multi-source explainable location evidence baseline.
> It proves that GNSS, LTE/cell, Wi-Fi, IMU, power, runtime, and transport evidence can be captured, exported, replayed, quality-checked, and converted into an explainable server-side location belief. It does not claim product positioning accuracy or cell-only positioning.

### 2. KR-005：短稳定性与 reconnect/cache/retry

KR-005 才是把外场问题收束的版本。当前最重要的是：

* 断网后 command queue 如何恢复；
* stale command 如何避免重复执行；
* ACK 丢失时服务器如何判断；
* 设备重启后 boot_id / seq / cmd_id 如何关联；
* cache 的 observation 如何标注 fresh/stale；
* no-fix、transport failure、parse failure、missing ACK 是否都有明确 failure reason。

KR-005 的目标不是长测，而是**短周期、可复现、可解释的稳定性基线**。

### 3. KR-006：产品演示闭环

KR-006 再把定位融合能力放进产品场景：

用户触发或安全事件
→ 设备请求位置/状态
→ LTE raw frame 上报
→ 多源 evidence 汇聚
→ location belief 生成
→ 用户确认/安全规则
→ 报告导出
→ Web 控制台可复盘。

这个阶段才适合面向展示说“这是一个可演示的 AI 随身端安全/定位闭环”。

---

## 三、模型融合算法设计：EALE-P0

建议把算法命名为：

**EALE-P0：Evidence-Aware Location Estimator，证据感知定位估计器。**

它不是一开始就训练深度模型，而是一个**可解释的规则 + 概率评分 + 记忆匹配 + 后续可学习替换**的融合框架。

设计原则：

1. **GNSS 是唯一可直接产生坐标的主证据。**
2. **Cell/LTE 在 P0 不推算坐标，只作为网络/区域/记忆证据。**
3. **Wi-Fi 在 P0 不保留 raw BSSID，使用 hash 后的 AP fingerprint 做 known-place 匹配。**
4. **IMU 不产生绝对位置，只判断 stationary / moving / activity，对 last-known hold 和 stale decay 起作用。**
5. **Power 不参与定位坐标，只影响采样可信度和设备状态解释。**
6. **Transport/runtime 不参与位置，但参与“这次失败是不是通信问题、运行时问题、GNSS no-fix 问题”的解释。**
7. **所有输出必须带 evidence_refs、confidence、radius、source、reason。**
8. **允许输出 unknown；unknown 是有效结果，不是失败。**

---

## 四、EALE-P0 输入数据结构

算法输入单位必须是 **observation window**，不是单条消息。这个与文档一致，`LOCATION_DATASET.md` 已经建议 sample unit 使用 `window_id / device_id / test_run_id / start_server_received_at / end_server_received_at / anchor_event_id / anchor_cmd_id / raw_frame_refs / derived_event_refs / features / labels / quality / privacy / split / generator`。

建议 EALE-P0 处理四类窗口：

| window_type                      | 用途                                                                                      |
| -------------------------------- | --------------------------------------------------------------------------------------- |
| `location_request_window`        | 从 command creation 到 location_report、location_observation、ACK                           |
| `passive_observation_window`     | 没有下行 command 的周期状态/传感观察                                                                 |
| `known_place_calibration_window` | 高置信 GNSS 或人工标注地点，用于建立位置记忆                                                               |
| `failure_window`                 | no-fix、partial frame、checksum failure、transport failure、reset、stale command、missing ACK |

文档也明确不完整和畸形数据应保留为 dataset candidates，因为这些 failure windows 对鲁棒性很有价值。

---

## 五、EALE-P0 算法流水线

### Step 1：Evidence Normalization

输入 raw/derived events 后，先统一成内部 evidence 对象。

```text
raw_frames + derived_events + commands + ACK + observability_summary
-> ObservationWindow
-> SourceEvidence[]
```

每个 evidence 都要有：

```json
{
  "source": "gnss | cell_lte | wifi | imu | power | transport | runtime",
  "present": true,
  "verified_state": "real | unknown | unverified | mock | missing | failed",
  "server_received_at": "...",
  "age_s": 0,
  "raw_frame_refs": [],
  "derived_event_refs": [],
  "quality_flags": [],
  "privacy_class": "public | internal | sensitive_location | sensitive_fingerprint",
  "redaction_state": "none | hashed | bounded_export_only | excluded"
}
```

这里最重要的是 `verified_state`。KR-004 不能把没有验证的 Wi-Fi/IMU/power 当成真实证据。

---

### Step 2：Feature Generation

每个 observation window 生成六组特征。

#### 1. GNSS features

```json
{
  "gnss_fix": true,
  "lat": "...bounded evidence only...",
  "lon": "...bounded evidence only...",
  "satellites": 8,
  "hdop": 1.4,
  "gnss_state": "fix | no_fix | error | unknown",
  "gnss_query_ok": true,
  "source_status": "real",
  "age_s": 3
}
```

GNSS quality：

```text
gnss_quality =
  fix_gate
  * freshness_score
  * hdop_score
  * satellite_score
  * source_status_score
```

P0 默认参数建议：

```text
fix_gate = 1 if fix=true else 0
freshness_score = exp(-age_s / 60)
hdop_score = clamp((8.0 - hdop) / (8.0 - 1.0), 0, 1)
satellite_score = clamp((satellites - 4) / 8, 0, 1)
```

radius 只作为保守估计，不宣称精度：

```text
gnss_radius_m = max(25, hdop * 8)
```

这个参数后续用真实数据再校准。

#### 2. Cell/LTE features

```json
{
  "cell_rat": "LTE",
  "mcc": "...",
  "mnc": "...",
  "tac_hash": "...",
  "cell_id_hash": "...",
  "rsrp": -92,
  "rsrq": -10,
  "rssi": -65,
  "sinr": 12,
  "registration_state": "registered",
  "pdp_state": "active",
  "assigned_ip_present": true,
  "lte_reason_code": "ok"
}
```

Cell/LTE 的 P0 作用：

* 证明设备确实在蜂窝网络中；
* 判断通信状态；
* 形成 coarse area memory；
* 辅助判断“是否仍在上一次区域”；
* 不直接输出 lat/lon；
* 不声明 cell-only positioning。

Cell quality：

```text
cell_quality =
  registered_gate
  * pdp_gate
  * freshness_score
  * radio_signal_score
  * source_status_score
```

但它只进入 area/consistency，不进入坐标融合。

#### 3. Wi-Fi fingerprint features

```json
{
  "wifi_scan_state": "ok | failed | unknown | unverified",
  "scan_duration_ms": 1200,
  "ap_count": 6,
  "ap_hashes": ["..."],
  "rssi_vector": [-42, -61, -70],
  "top_ap_rssi": -42
}
```

Wi-Fi 只能使用 hash 后的 AP identifier，不默认保存 raw BSSID。文档也明确 Wi-Fi AP identifiers 应 hash 或做隐私审查后再长期保留。

Wi-Fi known-place match：

```text
wifi_match_score =
  0.7 * weighted_jaccard(current_ap_hashes, place_ap_hashes)
  + 0.3 * rssi_similarity(shared_aps)
```

其中：

```text
rssi_similarity = avg(clamp(1 - abs(current_rssi - ref_rssi) / 30, 0, 1))
```

P0 阈值建议：

```text
wifi_match_score >= 0.75 -> strong known-place candidate
0.55 <= score < 0.75 -> weak known-place candidate
score < 0.55 -> no known-place match
```

#### 4. IMU motion features

```json
{
  "motion_state": "stationary | walking | moving | unknown",
  "motion_confidence": 0.86,
  "activity_label": "stationary",
  "stationary_seconds": 180,
  "imu_window_ref": "..."
}
```

IMU 的作用：

* stationary：允许 hold last known location / known place；
* moving：加快 last known location 的 radius 增长；
* unknown：不加分也不强惩罚；
* 不做惯导坐标推算，P0 不做 dead reckoning。

Motion gate：

```text
stationary_hold_bonus = 1.0 if stationary_seconds >= 60 and confidence >= 0.7
moving_decay_multiplier = 2.0 if moving else 1.0
```

#### 5. Power features

```json
{
  "battery_voltage": 3.86,
  "soc_estimate": 0.62,
  "charging_state": "not_charging",
  "power_source": "battery",
  "power_source_label": "wearable_battery"
}
```

Power 只影响 evidence quality：

* 低电量时 GNSS/Wi-Fi scan 失败更可解释；
* 不参与位置判断；
* 可用于 report 中解释“设备可能省电/扫描不完整”。

#### 6. Transport/runtime features

```json
{
  "transport_type": "lte_http_raw",
  "http_phase": "poll | post | ack",
  "http_status": 200,
  "reason": "ok | timeout | parse_failure | missing_ack | stale_command",
  "rtt_ms": 850,
  "reset_reason": "power_on | watchdog | unknown",
  "uptime_s": 320,
  "free_heap": 123456
}
```

Transport/runtime 只用于 explainability 和 quality，不参与位置坐标。

---

## 六、Candidate Generation：候选位置生成

EALE-P0 不直接“一步融合”，而是先生成候选。

### Candidate 1：GNSSCandidate

条件：

```text
gnss.fix = true
gnss_quality >= 0.5
coordinates present in bounded evidence/export
```

输出：

```json
{
  "candidate_type": "point",
  "source": "gnss",
  "lat": "...",
  "lon": "...",
  "radius_m": 25,
  "score": 0.82,
  "reason": "gnss_fix_valid",
  "evidence_refs": []
}
```

### Candidate 2：KnownPlaceCandidate

来源：

* Wi-Fi fingerprint strong match；
* operator-labelled place；
* high-confidence GNSS calibration window；
* user confirmation。

输出：

```json
{
  "candidate_type": "place",
  "source": "wifi_memory",
  "place_id": "home_001",
  "radius_m": 50,
  "score": 0.78,
  "reason": "wifi_fingerprint_match",
  "evidence_refs": []
}
```

注意：KnownPlace 可以有坐标，也可以没有坐标。没有用户授权或隐私等级不允许时，只输出 place state，不输出 exact lat/lon。

### Candidate 3：LastKnownCandidate

来源：

* 最近一次高置信 GNSS；
* 最近一次 confirmed known place；
* 最近一次 operator/user confirmation。

半径随时间增长：

```text
radius_m =
  last_radius_m
  + age_s * growth_rate_mps * moving_decay_multiplier
```

P0 默认：

```text
growth_rate_mps = 0.5 if stationary else 2.0
max_hold_age_s = 1800
```

超过 max_hold_age_s 后降级为 stale。

### Candidate 4：CellAreaCandidate

来源：

* cell_id/tac 与历史 known place 或 last known fix 匹配；
* 当前 cell signature 与近期 cell signature 一致。

输出：

```json
{
  "candidate_type": "coarse_area",
  "source": "cell_memory",
  "area_id": "cell_cluster_xxx",
  "radius_m": 500,
  "score": 0.35,
  "reason": "same_cell_cluster_as_recent_known_place"
}
```

CellAreaCandidate 只能做低置信粗粒度区域，不输出精确位置，不作为产品定位精度声明。

### Candidate 5：FailureCandidate

来源：

* no-fix；
* missing observation；
* stale command；
* parse failure；
* checksum failure；
* missing ACK；
* reset；
* transport failure。

输出：

```json
{
  "candidate_type": "failure",
  "source": "runtime",
  "score": 1.0,
  "reason": "gnss_no_fix_transport_ok",
  "evidence_refs": []
}
```

FailureCandidate 非常重要，因为它让系统从“没有定位结果”变成“知道为什么没有定位结果”。

---

## 七、Fusion Decision：融合决策规则

EALE-P0 采用 **dominance + consistency + decay** 策略。

### 规则 1：GNSS 有效时，GNSS 主导

```text
if valid GNSSCandidate:
    output = GNSSCandidate
    use Wi-Fi/cell/IMU as supporting evidence
```

但如果 Wi-Fi strong known-place 与 GNSS 明显冲突，不直接否定 GNSS，而是降低 confidence 并增加 reason：

```text
reason = "gnss_fix_with_context_conflict"
quality_flags += ["wifi_place_conflict"]
```

### 规则 2：GNSS 无效，Wi-Fi strong known-place 优先

```text
if no valid GNSS and strong Wi-Fi KnownPlaceCandidate:
    output = known_place
```

如果 IMU stationary，则提高 confidence；如果 IMU moving，则降低 confidence。

### 规则 3：GNSS 无效，Wi-Fi 不可用，但 last known fresh + stationary

```text
if no valid GNSS and no strong Wi-Fi and last_known_age < max_hold_age and stationary:
    output = last_known_hold
```

这个适合室内、弱 GNSS 场景。

### 规则 4：只有 Cell/LTE 时，只输出 coarse area 或 no precise fix

```text
if only cell evidence:
    if matched known cell cluster:
        output = coarse_area_memory
    else:
        output = no_precise_fix
```

不能输出 cell-only lat/lon。

### 规则 5：transport/runtime 失败优先解释

如果没有 location_report 或 ACK 缺失，不应简单输出 no-fix，而要区分：

```text
missing_location_report + command_sent -> transport_or_runtime_failure
location_report_no_fix + ACK_ok -> gnss_no_fix_transport_ok
parse_failure -> raw_frame_parse_failure
stale_command -> stale_command_ignored
reset_after_command -> device_reset_during_location_request
```

---

## 八、Location Belief 输出结构

建议 server-side derived view 输出 `location_belief`，不改设备协议。

```json
{
  "location_belief": {
    "state": "fix | known_place | last_known_hold | coarse_area | no_fix | unknown | failure",
    "source": "gnss | wifi_memory | last_known | cell_memory | runtime",
    "lat": null,
    "lon": null,
    "place_id": null,
    "radius_m": 50,
    "confidence": 0.72,
    "confidence_bucket": "high | medium | low | unknown",
    "freshness_s": 12,
    "reason": "wifi_fingerprint_match_stationary",
    "failure_reason": null,
    "quality_flags": [
      "gnss_no_fix",
      "wifi_real",
      "imu_stationary",
      "cell_registered"
    ],
    "evidence_refs": {
      "raw_frame_refs": [],
      "derived_event_refs": [],
      "anchor_cmd_id": "...",
      "anchor_event_id": "..."
    },
    "privacy": {
      "privacy_class": "sensitive_location",
      "redaction_state": "bounded_export_only",
      "training_allowed": false
    },
    "generator": {
      "name": "EALE-P0",
      "version": "0.1.0",
      "config_hash": "..."
    }
  }
}
```

P0 建议使用 `confidence_bucket` 作为 UI 主展示，避免用户误以为 0.72 是精确概率。

---

## 九、Confidence 计算方式

每个 candidate 都有 score，但最终 confidence 需要保守。

```text
candidate_score =
  source_quality
  * freshness_score
  * consistency_score
  * lineage_quality
  * privacy_allowed_gate
```

建议 source 初始权重：

| Source                  | P0 作用                   | 初始权重   |
| ----------------------- | ----------------------- | ------ |
| GNSS valid fix          | 坐标主证据                   | 1.00   |
| Wi-Fi known-place       | 室内地点证据                  | 0.75   |
| last known + stationary | 保守延续                    | 0.55   |
| cell memory             | 粗区域/辅助                  | 0.35   |
| IMU                     | motion modifier         | 不单独成位置 |
| power                   | quality modifier        | 不单独成位置 |
| transport/runtime       | explainability modifier | 不单独成位置 |

Consistency score：

```text
1.0 = no conflict
0.7 = weak conflict
0.4 = strong conflict
0.0 = impossible or invalid
```

Lineage quality：

```text
1.0 = raw_frame_refs + derived_event_refs + cmd_id + seq + parser status all present
0.7 = derived only but bounded run complete
0.4 = missing raw lineage
0.0 = cannot trace evidence
```

Privacy gate：

```text
1.0 = allowed for current output/export
0.0 = excluded from output/training
```

---

## 十、Place Memory 设计

EALE-P0 需要一个轻量 location memory，但必须隐私优先。

### `known_place` record

```json
{
  "place_id": "place_001",
  "label": "home | school | office | unknown_label",
  "label_source": "user_confirmation | operator_note | gnss_anchor | rule",
  "label_confidence": 0.9,
  "coordinate": {
    "lat": null,
    "lon": null,
    "radius_m": 50,
    "privacy_class": "sensitive_location"
  },
  "wifi_fingerprint": {
    "ap_hashes": [],
    "rssi_stats": {},
    "redaction_state": "hashed"
  },
  "cell_signature": {
    "mcc": "...",
    "mnc": "...",
    "tac_hash": "...",
    "cell_id_hashes": []
  },
  "created_from_window_id": "...",
  "updated_from_window_ids": [],
  "training_allowed": false
}
```

### 写入规则

只有以下情况可以写入/更新 known_place：

1. GNSSCandidate 高置信；
2. 用户确认；
3. operator note；
4. 多次 Wi-Fi + cell signature 稳定重复出现；
5. privacy/consent 允许。

不能因为一次 cell-only observation 就创建精确地点。

---

## 十一、训练数据与后续 learned model 路径

现在要完成的是**模型融合算法设计**，但 learned model 不应在 DATA-001/KR-004 中发布。`DATA-001` 已明确要求保留 raw-frame lineage、failure windows、label source/confidence、privacy class、quality checks、JSONL + manifest，并且不训练模型。

建议后续学习型模型只替换两个部分：

### Model A：Source Reliability Model

输入：

* GNSS hdop/satellites/fix age；
* Wi-Fi ap_count/match_score；
* cell rsrp/rsrq/sinr/stability；
* IMU stationary/moving；
* transport failure；
* runtime reset；
* power state。

输出：

```text
source_reliability scores
```

它不直接输出位置，只学习“这次证据可信不可信”。

### Model B：Known Place Classifier

输入：

* hashed Wi-Fi fingerprint；
* hashed cell signature；
* time block；
* motion state；
* last known context。

输出：

```text
place_id probability
```

这可以先用传统模型做：

* Logistic Regression；
* Random Forest / Gradient Boosting；
* kNN fingerprint matching；
* small MLP。

不建议一开始上复杂深度模型。当前数据量和标签质量不足，复杂模型会产生虚假精度。

---

## 十二、DATA-001 应该怎么服务融合算法

DATA-001 的产物应直接支持 EALE-P0。

### JSONL sample 建议结构

```json
{
  "schema_version": "location_fusion_sample.v0.1",
  "window_id": "win_...",
  "window_type": "location_request_window",
  "device_id": "ego_link_001",
  "test_run_id": "kr003_field_...",
  "start_server_received_at": "...",
  "end_server_received_at": "...",
  "anchor_cmd_id": "...",
  "anchor_event_id": "...",
  "raw_frame_refs": [
    {
      "frame_id": "...",
      "byte_length": 128,
      "sha256": "...",
      "crc": "...",
      "parse_status": "ok",
      "parser_version": "..."
    }
  ],
  "derived_event_refs": [],
  "features": {
    "gnss": {},
    "cell_lte": {},
    "wifi": {},
    "imu": {},
    "power": {},
    "transport_runtime": {},
    "memory": {}
  },
  "labels": {
    "label_type": "unknown | gnss_anchor | user_confirmation | operator_note | failure",
    "place_id": null,
    "lat": null,
    "lon": null,
    "label_confidence": 0.0,
    "failure_label": "gnss_no_fix_transport_ok"
  },
  "quality": {
    "missing_timestamps": false,
    "sequence_regression": false,
    "duplicate_command_execution": false,
    "stale_command": false,
    "missing_raw_frame_lineage": false,
    "split_leakage_risk": false
  },
  "privacy": {
    "privacy_class": "sensitive_location",
    "redaction_state": "hashed_or_bounded",
    "consent": "unknown",
    "training_allowed": false,
    "exclusion_reasons": []
  },
  "split": {
    "rule": "session_blocked",
    "name": "unassigned"
  },
  "generator": {
    "name": "DATA-001",
    "version": "0.1.0"
  }
}
```

这与文档要求一致：manifest 要包含 source test-run/session/device/firmware、parser/generator versions、raw-frame hash coverage、schema versions、split rule、label source/confidence、privacy class、known gaps 等；并且不能把同一 field session 的行随机拆到 train/test，优先 session/device/place/time blocked split。

---

## 十三、需要给 Codex 新增的任务包

建议在现有任务后面增加 4 个任务。

### ALG-000：Location Fusion Algorithm Design

目标：新增 `docs/development/LOCATION_FUSION_ALGORITHM.md`。

内容：

* EALE-P0 定义；
* 输入 evidence/window；
* feature groups；
* candidate generation；
* confidence scoring；
* fusion decision tree；
* failure reason taxonomy；
* location_belief 输出；
* privacy/retention；
* DATA-001 对接；
* KR-004/KR-005/KR-006 release gates。

边界：

* 不改 firmware；
* 不改 live wire protocol；
* 不训练模型；
* 不声明 accuracy；
* 不引入外部 cell positioning API；
* 不保存 raw private BSSID。

### ALG-001：Server-side Rule Fusion Baseline

目标：实现 server-side `location_belief` 派生层。

建议路径：

```text
server/location_fusion.py
shared/contracts/location_belief.schema.json
quality_tests/test_location_fusion_baseline.py
```

输入：

```text
test_run export / derived events / observation window
```

输出：

```text
location_belief derived view
```

边界：

* derived only；
* 可开关；
* 不改变 device wire；
* 不影响 KR-003 raw loop。

### ALG-002：Fusion Evaluation Harness

目标：用 DATA-001 JSONL 跑规则算法回放。

输出指标：

| 指标                           | 说明                                           |
| ---------------------------- | -------------------------------------------- |
| evidence_coverage            | 每个窗口有哪些 evidence                             |
| belief_coverage              | 有多少窗口能输出 fix/known_place/hold/coarse/unknown |
| failure_explanation_coverage | failure windows 中有多少能解释原因                    |
| false_high_confidence_rate   | 高置信但标签冲突的比例                                  |
| stale_detection_rate         | stale command/cache 是否识别                     |
| lineage_integrity_rate       | raw lineage 是否完整                             |
| privacy_exclusion_rate       | 被隐私规则排除的数据比例                                 |

这一步比“平均定位误差”更重要。P0 阶段先不要把指标中心放在米级误差上。

### ALG-003：Learned Reliability Prototype

目标：等 DATA-001 有一定真实样本后，再训练一个小模型预测 source reliability。

边界：

* 不上设备；
* 不进入产品默认路径；
* 只离线评估；
* 与 EALE-P0 rule baseline 对比；
* 只有在 false_high_confidence_rate 下降时才考虑进入 release candidate。

---

## 十四、KR-004 的验收标准建议

KR-004 通过条件建议写成：

1. KR-003 raw LTE command/location/ACK 主链路不回退。
2. `location_report`、`location_observation`、ACK、raw-frame summaries 能被 DATA-001 组合成 observation windows。
3. Wi-Fi / IMU / power 在真实 firmware-side location path 中至少满足以下之一：real verified / unknown / unverified / failed，不能静默缺失。
4. Web/API/报告能显示当前 run、key release、command、ACK、raw frame、derived observation、failure reason。
5. EALE-P0 设计文档冻结。
6. server-side 可选生成 `location_belief`。
7. failure window 被保留，而不是被过滤。
8. 不声明 GNSS fix 通过、不声明 cell-only 定位、不声明产品 ready、不声明融合定位精度。
9. `context_lint.py` 与相关 focused tests 通过。
10. 输出 KR-004 release note，明确与 KR-003 的差异。

---

## 十五、现在最重要的技术取舍

### 取舍 1：融合算法先 server-side，暂不上 firmware

原因：设备端现在最宝贵的是保持 KR-003 raw LTE runtime loop 稳定。融合算法一旦放到 firmware，很容易引入功耗、时序、内存、协议变更问题。

### 取舍 2：Cell 只做 evidence，不做定位

当前 KR-003 已证明 SIM7670G real cell/LTE observation over LTE raw frames，但没有从 cell data 推断位置。 所以任何 cell-only positioning 都不应成为 KR-004/KR-005 的目标。

### 取舍 3：Wi-Fi 是 known-place memory，不是地图定位

没有外部 Wi-Fi 定位数据库时，Wi-Fi 最适合作为“我是不是回到某个已知地点”的证据。

### 取舍 4：IMU 是 motion context，不是惯导

IMU 在 P0 的价值是判断 stationary/moving，从而决定能不能 hold last known location，以及 stale decay 的速度。

### 取舍 5：失败窗口是资产

no-fix、missing ACK、stale command、parse failure、transport failure 都要进入 DATA-001，而不是被当作垃圾数据删掉。这个方向文档已经明确。

---

## 十六、下一步执行指令建议

```text
Proceed with KR-004 preparation under the following boundary.

Do not modify firmware wire protocol. Do not train or publish a learned fusion model. Do not claim cell-only positioning accuracy. Preserve KR-003 raw LTE command/location/ACK loop.

1. Add docs/development/LOCATION_FUSION_ALGORITHM.md.
   Define EALE-P0: Evidence-Aware Location Estimator.
   Include input observation windows, feature groups, candidate generation, source reliability scoring, fusion decision rules, failure reason taxonomy, location_belief output shape, privacy rules, and DATA-001 integration.

2. Continue DATA-001.
   Implement the first location_fusion_sample JSONL + manifest export from a named test_run_id.
   Preserve raw-frame lineage, derived event refs, labels, quality checks, privacy, redaction, consent/training flags, and split rule.
   Include failure windows.

3. Prepare ALG-001 as a separate task, not mixed into DATA-001.
   Implement optional server-side derived location_belief generation from observation windows.
   Keep it off by default or clearly marked experimental until KR-004 release gate.

4. Continue LOC-005A.
   Connect firmware-side Wi-Fi / IMU / power observation into the same evidence path.
   Each field must be marked real, unknown, unverified, mock, missing, or failed.
   Do not silently fill fake values.

5. Continue OBS-003.
   Add Web/API/report visibility for current run, key release, raw evidence, derived observation, command/ACK chain, and failure reason.

6. Continue STAB-001B and LTE-005 after KR-004 evidence path is stable.
   Focus on short USB-Free baseline, reconnect, retry, cache, stale command, and reboot-aware explanations.

Run context_lint.py and focused tests. Run full verify.ps1 only if server behavior changes.
```

---

## 十七、最终建议

**下一步不要把项目推进成“定位算法项目”，而要推进成“可解释位置证据系统”。** 这更符合你现在的真实进度，也更适合产品化：用户真正需要的不是系统每次都假装知道精确位置，而是系统在关键时刻能说清楚：

* 我有没有收到设备请求；
* 设备有没有通过 LTE 回来；
* GNSS 是 fix 还是 no-fix；
* 当前蜂窝网络状态怎样；
* Wi-Fi/IMU/power 有没有真实证据；
* 这次位置判断来自哪个证据；
* 为什么没有精确位置；
* 上一次可信位置是否还能保守沿用；
* 数据是否可以进入训练集；
* 哪些信息因为隐私不能导出。

所以，**KR-004 的成功标志不是“定位准了”，而是“所有证据进入同一套可回放、可导出、可解释、可训练的数据结构，并且 EALE-P0 融合算法设计冻结”。** 这样 KR-005 才能解决稳定性，KR-006 才能形成真正可展示的产品闭环。

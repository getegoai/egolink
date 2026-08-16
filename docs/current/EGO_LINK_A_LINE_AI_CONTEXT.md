# Ego Link A线 AI能力开发基线与工程上下文

> 文档类型：项目记忆 / Codex 工程上下文\
> 项目：Project EGO / Ego Link\
> 研发线：A线 — AI能力线\
> 版本：v1.0\
> 日期：2026-08-16\
> 状态：当前有效基线（后续设计、开发、评测与任务拆解均应以本文为准，除非有新的明确决策覆盖）

---

## 1. 文档目的

本文用于固化 Ego Link A线的当前产品目标、AI架构、数据体系、模型路线、评测方法和近期开发顺序。

Codex 在继续开发 A线相关代码、任务文档、测试脚本、数据处理工具、模型训练工具或部署逻辑前，应先阅读本文，并遵守以下基本原则：

1. 从最终产品能力倒推模型与数据，不以“先训练一个模型”为研发起点。
2. A线核心目标是形成可持续迭代的 **数据采集 → 数据处理 → 模型训练 → 质量评测 → 部署应用 → 真实场景回流** 闭环。
3. 所有 AI 能力必须能够在真实外出测试数据上被回放、比较、解释和量化。
4. 优先建立数据和评测基础设施，再推进复杂模型。
5. 产品端保持低功耗、隐私优先、可离线运行的基本约束。
6. 模型设计采用“物理估计 + 小型时序模型 + 不确定性融合 + 长期记忆 + 私有训练”的分层架构，不采用单一大一统多模态模型直接处理全部传感器。

---

# 2. 当前硬件与测试能力

截至 2026-08-16，Ego Link 开发板已进入可以进行真实外出采集和地图验证的阶段。

当前可用能力：

- GNSS：可采集，定位数据已能在地图显示。
- 4G / LTE：可通信，并可采集与蜂窝网络相关数据。
- 六轴 IMU：已接入，可采集；下一步应先完成规范化校准。
- Camera：开发板自带摄像头，可按程序和采样策略获取图像。
- Audio：当前缺少麦克风和扬声器，后续将采购并接入，但不阻塞 A-R0 / A-R1。
- 设备已经具备外出测试和真实数据回流能力。

因此，A线当前工作重点正式从“传感器是否可用”转向：

> 如何将 GNSS、LTE、IMU、Camera 等信息组织为可训练、可评测、可部署的个人物理智能系统。

---

# 3. A线正式定义

A线不定义为“若干 AI 模型开发任务”，而定义为：

> **Personal Physical Intelligence Engine（个人物理智能引擎）**

它需要连续回答五个产品级问题：

1. **Where am I?**\
   我在哪里？

2. **What is happening?**\
   当前发生了什么？用户、设备和环境处于什么状态？

3. **Is this normal / safe?**\
   当前情况是否正常，是否存在需要关注的安全风险？

4. **What evidence am I missing?**\
   当前判断还缺什么证据？是否值得主动调用更多传感器？

5. **Should I do something?**\
   是否应该改变采样策略、主动询问、通知联系人或进入应急流程？

A线最终需要形成：

```text
Sense
  ↓
Understand
  ↓
Estimate uncertainty
  ↓
Actively acquire evidence
  ↓
Verify
  ↓
Decide / Act
```

---

# 4. A线向产品层输出的三个核心对象

## 4.1 Location Belief

Location Belief 是“系统当前对位置的综合判断”，不是一个简单经纬度。

建议基本结构：

```text
location_belief
├─ timestamp
├─ position
│  ├─ latitude
│  ├─ longitude
│  └─ zone / semantic_place
├─ confidence
├─ uncertainty_radius
├─ source_contributions
│  ├─ gnss
│  ├─ cellular
│  ├─ inertial
│  └─ vision
├─ source_quality
├─ age
├─ motion_consistency
├─ trajectory_context
└─ explanation
```

示例含义：

> 当前判断设备位于学校东门附近；可信度较高；GNSS 已失效一段时间，但 LTE 小区组合、IMU 运动轨迹和历史路线仍保持一致，因此位置仍具有可解释的置信区间。

核心要求：

- 必须表达“不确定性”；
- 必须保留各传感源贡献；
- 必须可解释；
- 必须支持 GNSS 丢失后的连续退化，而不是瞬间变成 Unknown。

---

## 4.2 State Belief

State Belief 描述人、设备和环境的当前状态。

第一阶段至少覆盖四类。

### 运动状态

```text
stationary
walking
running
stairs_up
stairs_down
vehicle
unknown
```

### 携带状态

```text
hand
pocket
bag
worn
table
unknown
```

### 环境 / 场景状态

```text
outdoor
indoor
transition
vehicle
unknown
```

### 设备状态

```text
normal
dropped
unattended
network_poor
low_battery
unknown
```

State Belief 不应仅输出单个分类标签，应逐步包含：

```text
state
confidence
duration
transition
evidence
uncertainty
```

---

## 4.3 Safety Belief

Safety Belief 表示系统对风险的综合判断。

建议结构：

```text
safety_belief
├─ risk_level
│  ├─ normal
│  ├─ watch
│  ├─ verify
│  ├─ contact
│  └─ emergency
├─ evidence[]
├─ missing_evidence[]
├─ confidence
├─ recommended_sensor_actions[]
├─ recommended_user_action
└─ explanation
```

其核心不是“检测到异常就报警”，而是：

> 先发现异常，再主动获取最有价值的新证据，再进行验证和升级。

---

# 5. 总体 AI 架构

建议采用以下分层结构：

```text
GNSS ─────┐
LTE ──────┤
IMU ──────┤
Camera ───┤
Audio ────┘  （后续加入）
    ↓
[0] Sensor Quality Layer
    ↓
[1] Modality Encoders
    ↓
[2] Multisource State Estimator
    ↓
[3] Temporal Context & Memory
    ↓
[4] Safety Reasoner
    ↓
[5] Active Sensing / Power Controller
```

---

## 5.1 Sensor Quality Layer

第一层不做语义理解，先判断“输入值不值得信”。

包括：

- GNSS quality
- LTE signal / observation quality
- IMU calibration / saturation / missing samples
- Camera image quality
- Audio quality（后续）
- sensor age
- timestamp consistency
- packet loss
- data freshness

后续融合算法必须使用质量信息，而不是默认所有数据同等可靠。

---

## 5.2 Modality Encoders

每类传感器先形成自己的低维特征或局部状态。

示例：

```text
GNSS → position / velocity / quality embedding
LTE  → cell fingerprint embedding
IMU  → temporal motion embedding
Camera → visual place / semantic embedding
Audio → acoustic event embedding
```

---

## 5.3 Multisource State Estimator

负责融合多个来源：

```text
absolute observations
+
relative motion
+
historical context
+
source uncertainty
```

输出：

- Location Belief
- State Belief
- 各自 uncertainty

---

## 5.4 Temporal Context & Memory

单个时间点的信息通常不足。

必须逐步加入：

- 最近若干分钟轨迹
- 位置转移历史
- Cell sequence
- 运动状态持续时间
- 常见路线
- 常见地点
- 用户个人行为基线
- 最近异常事件

---

## 5.5 Safety Reasoner

将 Location、State、历史和异常事件转化为风险判断。

安全逻辑应采用：

```text
High-recall Detector
        ↓
Context Verifier
        ↓
Safety Belief
```

---

## 5.6 Active Sensing / Power Controller

负责决定：

```text
IMU sampling rate
GNSS wake / sleep
LTE refresh interval
Camera trigger
Audio trigger
upload policy
local inference policy
```

该层是低功耗 AI 的核心。

---

# 6. A0 — AI Data & Evaluation Platform

A0 是当前最高优先级工作。

在 A0 完成之前，不应把大量时间投入复杂模型。

正式流水线：

```text
COLLECT
  ↓
INGEST
  ↓
VALIDATE
  ↓
SYNC
  ↓
SEGMENT
  ↓
LABEL
  ↓
BUILD DATASET
  ↓
TRAIN
  ↓
EVALUATE
  ↓
EXPORT
  ↓
DEVICE REPLAY
  ↓
SHADOW DEPLOY
  ↓
FIELD VALIDATE
```

---

# 7. Field Session 数据规范

每一次外出测试均形成唯一 session。

建议目录：

```text
data/
└── raw/
    └── 20260816_001/
        ├── session.json
        ├── imu.parquet
        ├── gnss.parquet
        ├── cellular.parquet
        ├── device.parquet
        ├── events.parquet
        ├── labels.parquet
        └── images/
```

---

## 7.1 session.json

至少包含：

```text
session_id
device_id
hardware_revision
firmware_commit
software_commit
calibration_id

start_time
end_time
timezone

test_scenario
route_id
operator

imu_rate
gnss_policy
lte_policy
camera_policy
audio_policy

battery_start
battery_end

notes
```

---

## 7.2 所有传感器的时间字段

至少保存：

```text
monotonic_timestamp
utc_timestamp
sequence_id
```

必要时增加：

```text
device_timestamp
source_timestamp
ingest_timestamp
```

多模态训练、事件关联和 Replay 都依赖精确时间同步。

---

# 8. IMU 校准要求

第一阶段必须完成规范 IMU 校准。

## 8.1 Accelerometer

六面静态校准：

```text
+X
-X
+Y
-Y
+Z
-Z
```

估计：

```text
bias
scale
```

---

## 8.2 Gyroscope

设备静止时估计：

```text
bias_x
bias_y
bias_z
```

建议每次开机静止阶段允许重新估计短期 bias。

---

## 8.3 六轴 IMU 的重要限制

仅靠六轴 IMU：

> 静止状态下 yaw 绝对方向不可观测。

因此算法不得假设 IMU 可以单独长期提供绝对航向。

应结合：

- gravity alignment
- orientation augmentation
- carry-state
- GNSS course
- route constraints
- map / visual anchor

解决方向漂移问题。

---

# 9. A1 — Multisource Localization

## 9.1 GNSS

GNSS 同时承担三个角色：

1. 当前绝对位置来源；
2. 其他模型的训练标签来源；
3. 融合系统的高质量 anchor。

不要只保存：

```text
lat
lon
```

应尽可能保存：

```text
fix / no_fix
fix_type
satellite_count
HDOP
VDOP
PDOP
speed
course
altitude
fix_age
NMEA / raw fields
timestamp
```

第一代应先实现：

> **GNSS Reliability Estimator**

输出当前 GNSS 是否可信以及可信程度。

---

## 9.2 LTE / Cellular

目标是逐步建立：

> **Ego Cellular Location Map**

尽可能采集：

```text
MCC
MNC
Cell ID
TAC
PCI
RSRP
RSRQ
RSSI
SINR
neighbor cells
timestamp
```

具体字段以当前 4G 模组实际支持为准。

LTE 定位模型按难度逐步推进：

```text
Baseline 0: cell centroid
Baseline 1: weighted KNN
Baseline 2: GBDT / MLP fingerprint
Baseline 3: sequence model
```

同时保留 Cell sequence：

```text
Cell A
→ Cell A
→ Cell B
→ Cell C
```

小区切换序列可以形成较强的路线和区域证据。

---

## 9.3 IMU

IMU 不只用于 activity classification。

建议建立共享时序 Encoder：

```text
6-axis IMU
    ↓
Shared Temporal Encoder
    ├─ activity head
    ├─ carry-state head
    ├─ impact / fall head
    ├─ relative displacement / velocity head
    └─ uncertainty head
```

第一代优先考虑轻量结构：

- DS-CNN
- TCN
- compact 1D CNN
- small GRU（必要时）

第一阶段不急于上大型 Transformer。

---

## 9.4 Camera

Camera 产品策略：

> 默认关闭或低频，仅作为高价值 Visual Anchor。

重点场景：

- 家门口
- 学校入口
- 常用楼道
- 电梯厅
- 地铁站
- 停车场
- 熟悉路口
- GNSS denied 区域

基本流程：

```text
capture
  ↓
visual embedding
  ↓
known-place matching
  ↓
visual anchor
  ↓
fusion
```

研发训练阶段允许使用较大 teacher model；产品端逐步蒸馏为轻量 encoder。

---

# 10. A2 — State Understanding

第一阶段状态理解重点：

### Motion

```text
stationary
walking
running
stairs
vehicle
```

### Carry

```text
hand
pocket
bag
worn
table
```

### Environment

```text
outdoor
indoor
transition
vehicle
```

### Device

```text
normal
dropped
unattended
network_poor
```

---

## 10.1 Camera → IMU Cross-modal Distillation

重要研发策略：

开发采集阶段：

```text
Camera ON
IMU ON
GNSS ON
LTE ON
```

服务器训练：

```text
Camera Teacher
      ↓
semantic knowledge
      ↓
IMU Student
```

产品运行：

```text
IMU always / mostly on
Camera mostly off
```

Camera 只在以下条件触发：

- state uncertainty 高；
- location uncertainty 高；
- Safety Risk 上升；
- 进入重要地点；
- 用户主动请求。

后续麦克风可采用相同逻辑。

---

# 11. A3 — Proactive Safety

主动安全采用两层结构。

## 11.1 High-recall Detector

优先发现：

- strong impact
- prolonged stillness
- unexpected running
- abnormal location deviation
- unexpected vehicle movement
- GNSS sudden loss
- abnormal Cell transition
- device dropped
- device left behind / unattended

Detector 允许偏敏感。

---

## 11.2 Context Verifier

Detector 触发后，不直接报警。

应综合：

```text
location
state
history
route
time
recent events
network
Camera
Audio（后续）
```

决定：

```text
normal
watch
verify
contact
emergency
```

---

## 11.3 主动取证机制

例如：

```text
strong impact
      ↓
40 s stillness
      ↓
risk ↑
      ↓
increase IMU rate
request GNSS reacquire
refresh LTE
capture Camera frame
listen Audio（future）
      ↓
verify
      ↓
Safety Belief
```

主动安全的核心能力定义为：

> **在不确定性和风险升高时，知道下一步最值得获取什么证据。**

---

# 12. A4 — Adaptive Sensing & Edge AI

低功耗优化不只做量化。

核心问题：

> 用多少能量换多少新增信息？

Active Sensing Controller 输入：

```text
location uncertainty
state uncertainty
safety risk
battery
network quality
motion
recent sensor history
```

输出：

```text
IMU sampling rate
GNSS policy
LTE refresh interval
Camera trigger
Audio trigger
upload policy
```

---

## 12.1 第一版策略

先使用规则系统。

例如：

### 熟悉地点 + 静止

```text
IMU low rate
GNSS sparse / off
LTE sparse
Camera off
```

### 开始运动

```text
IMU 50 Hz
GNSS wake
LTE normal
```

### GNSS 丢失但轨迹仍正常

```text
IMU continue
LTE higher frequency
Camera off
```

### Location uncertainty 持续扩大

```text
GNSS reacquire
LTE refresh
Camera one-shot
```

### Safety Risk 上升

```text
evidence acquisition mode
```

后续有足够数据后，再考虑：

- contextual bandit
- reinforcement learning
- learned sensing policy

---

# 13. Edge / VPS / Training Server 分工

## 13.1 Device — Fast Loop

必须在设备离线时仍可运行：

```text
IMU inference
event detection
GNSS quality estimation
basic LTE lookup
basic position filter
local safety trigger
sensor scheduling
local cache
```

---

## 13.2 VPS / Ego Base — Slow Intelligence

负责：

```text
trajectory smoothing
factor graph / advanced fusion
Cell fingerprint DB
Visual Place DB
long-term behavior memory
personalization
complex safety verification
model registry
dataset management
```

---

## 13.3 Training Server

负责：

```text
large teacher models
self-supervised pretraining
cross-modal distillation
fine-tuning
model comparison
quantization
export
benchmark
```

产品端默认隐私优先：

- 原始 Camera / Audio 不持续上传；
- 优先保留本地；
- 需要协同时优先上传结构化事件、embedding 或抽象语义；
- 原始数据上传必须由明确研发/调试策略控制。

---

# 14. 第一轮 Field Dataset Protocol

禁止采用“随便出去走一圈”的数据采集方式。

第一轮至少包含以下场景：

| ID | 场景 |
|---|---|
| LOC-01 | 开阔室外步行 |
| LOC-02 | 高楼 / 城市峡谷 |
| LOC-03 | 室外 → 室内 |
| LOC-04 | 室内 → 室外 |
| LOC-05 | 地库 / 商场等 GNSS-denied |
| MOT-01 | 静止 / 步行 / 跑步 / 上下楼 |
| MOT-02 | 汽车 / 公交 / 地铁 |
| CARRY-01 | 手持 / 口袋 / 包内 / 佩戴 |
| VIS-01 | 已知地点重复经过 |

同一路线建议：

> 跨不同日期重复采集至少 3–5 次。

后续增加：

- 不同天气；
- 不同时间；
- 不同用户；
- 不同设备姿态；
- 不同 LTE 覆盖条件。

---

# 15. 利用 GNSS 自动生产弱标签

当 GNSS quality 高时，可以自动形成监督信号。

## 15.1 LTE 标签

```text
Cell fingerprint
+
high-quality GNSS
→
location label
```

---

## 15.2 IMU 标签

```text
IMU sequence
+
GNSS trajectory
→
speed / displacement / motion label
```

---

## 15.3 人工 GNSS Blackout

使用已有高质量轨迹：

```text
full GNSS session
      ↓
mask GNSS
      ↓
simulate outage
      ↓
evaluate recovery / drift
```

第一代固定 benchmark：

```text
30 s
60 s
180 s
300 s
```

这是 A1 最重要的核心指标之一。

---

# 16. Replay Engine

必须建设统一 Replay Engine。

目标：

> 一次真实采集的数据，可以重复测试任意版本的模型和融合算法。

目标命令形式可参考：

```bash
ego-replay session_20260816_001 \
  --model imu_v003 \
  --fusion fusion_v005 \
  --mask-gnss 60:180
```

输出至少包含：

```text
Ground Truth
GNSS-only
LTE-only
IMU-only
Fusion
```

地图显示：

- 真实轨迹；
- 各模型轨迹；
- uncertainty；
- source state；
- event markers。

同时输出机器可读 metrics。

---

# 17. 评测标准

## 17.1 定位

至少记录：

```text
Median Error
P90
P95
Max Error
ATE
RTE

30 s GNSS outage error
60 s GNSS outage error
180 s GNSS outage error
300 s GNSS outage error

position jump
recovery time
uncertainty calibration
```

不确定性必须被评测。

例如：

> 模型声明 95% uncertainty radius 时，真实误差是否真的约有 95% 落在该范围内。

---

## 17.2 状态理解

至少：

```text
Macro F1
per-class F1
cross-session
cross-day
cross-route
cross-carry-position
transition latency
unknown / OOD rejection
```

数据集禁止将同一条路线切窗口后随机分 train/test。

优先：

```text
leave-one-session-out
leave-one-route-out
leave-one-day-out
```

后续：

```text
leave-one-user-out
```

---

## 17.3 主动安全

核心指标：

```text
critical-event recall
false alarms / day
false alarms / hour
detection latency
verification success rate
escalation precision
```

产品级重点指标之一：

> **false alarms / day**

---

## 17.4 低功耗

从现在开始同步记录：

```text
mWh / hour
GNSS active %
LTE TX / RX bytes
Camera activations / day
IMU sampling profile
inference latency
RAM
flash
CPU utilization
```

后续形成：

> 能力 / 精度 / 安全性 ↔ 电池寿命

的 Pareto 曲线。

---

# 18. A线 Workstreams

A线正式拆为五条工作流：

```text
A0 — AI Data & Evaluation Platform
A1 — Multisource Localization
A2 — State Understanding
A3 — Proactive Safety
A4 — Adaptive Sensing & Edge AI
```

当前执行优先级：

```text
A0
↓
A1 + A2
↓
A3
↓
A4
```

---

# 19. 近期迭代路线

## A-R0 — AI 实验基础设施

当前立即执行。

内容：

```text
IMU calibration
unified timestamp
dataset schema
field-session manager
label schema
data validation
replay engine
evaluation framework
```

### 退出条件

任意一次外出测试完成后：

> 可使用一条标准命令回放 GNSS / LTE / IMU / Camera 数据，并重新生成地图、状态轨迹和评测指标。

---

## A-R1 — 第一代多源智能

内容：

```text
GNSS reliability
LTE location baseline
IMU activity classifier
IMU carry classifier
GNSS + LTE + IMU fusion
Location Belief
location uncertainty
```

关键 benchmark：

```text
30 / 60 / 180 / 300 s GNSS blackout
```

目标是回答：

> GNSS 消失之后，Ego Link 可以在多长时间内继续维持具有实际意义并且可解释的位置判断？

---

## A-R2 — AI 原生感知

加入：

```text
learned inertial odometry
Camera visual anchors
cross-modal distillation
state memory
active sensing
safety verification
```

Audio 接入后扩展：

```text
acoustic event understanding
voice verification
audio-assisted safety evidence
```

---

# 20. 中长期研究方向

以下三项应作为 Ego Link 具有潜在研究创新价值的方向长期保留。

## 20.1 Physics-informed Self-supervised Inertial Learning

利用：

```text
大量无标签 IMU
+
物理运动约束
+
少量高质量 GNSS
```

训练 Ego Link 自有惯性运动模型。

目标：

- 减少人工标签；
- 提升 GNSS-denied 场景能力；
- 提升个体和设备适配能力；
- 形成产品专属时序运动模型。

---

## 20.2 Camera → IMU Cross-modal Knowledge Distillation

研发阶段：

```text
Camera + IMU
```

产品阶段：

```text
IMU mostly only
```

利用视觉的丰富语义提升 IMU 表征能力，同时保留产品端低功耗和隐私优势。

---

## 20.3 Active Perception for Personal Safety

长期核心技术表达：

```text
Sense
↓
Understand
↓
Become uncertain
↓
Actively sense
↓
Verify
↓
Act
```

系统主动选择：

> 下一条最值得获取的证据是什么？

该方向应作为 Ego Link 与传统 GPS 定位器、儿童手表和普通可穿戴设备的重要能力差异。

---

# 21. Codex 开发约束

Codex 后续处理 A线任务时应遵守：

1. **不要一次性重写现有定位链路。**\
   保留当前已能跑通的 GNSS/LTE/VPS/地图链路，在其上逐步增加数据质量、融合和 AI 层。

2. **任何模型任务必须绑定 Dataset 和 Evaluation。**\
   不接受只有训练脚本、没有数据版本和评测脚本的模型提交。

3. **任何外出数据必须可 Replay。**

4. **模型输出必须带版本。**

建议：

```text
dataset_version
model_version
fusion_version
firmware_commit
calibration_id
```

5. **模型输出必须尽量表达 confidence / uncertainty。**

6. **禁止通过随机窗口切分制造虚高测试精度。**

7. **设备端优先轻量、可解释、可回退。**

8. **先实现 baseline，再加入复杂模型。**

9. **新增 AI 逻辑必须能够与现有 source-state / location_belief / location_memory 体系兼容。**

10. **Camera / Audio 默认按事件触发，不设计持续上传原始数据的产品路线。**

11. **A0 是当前最高优先级。**\
    如果某项复杂模型工作依赖的数据规范、Replay 或 Benchmark 尚不存在，应优先补齐基础设施。

---

# 22. 推荐仓库位置

建议本文放置：

```text
docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md
```

并在以下文件中增加引用：

```text
docs/current/PROJECT_SNAPSHOT.md
docs/current/STATUS.md
docs/tasks/TASK_TREE.md
```

后续 A线任务可以按：

```text
A0-xxx
A1-xxx
A2-xxx
A3-xxx
A4-xxx
```

编号。

示例：

```text
A0-001 IMU calibration pipeline
A0-002 unified sensor timestamp
A0-003 field session schema
A0-004 dataset validator
A0-005 replay engine MVP
A0-006 evaluation report generator

A1-001 GNSS reliability baseline
A1-002 LTE fingerprint baseline
A1-003 GNSS blackout simulator
A1-004 first multisource fusion baseline

A2-001 IMU activity dataset
A2-002 activity classifier baseline
A2-003 carry-state classifier baseline
```

---

# 23. 当前最近目标

当前最近目标不是追求最高模型准确率，而是：

> **让每一次真实外出测试都变成可复用的数据资产，让每一次模型修改都可以在同一批真实数据上重复比较，让每一个最终产品能力都可以被量化。**

当 A-R0 完成后，Ego Link A线才真正具备持续训练和迭代的基础。

当前开发顺序明确为：

```text
IMU校准
→ 统一时间轴
→ Session / Dataset Schema
→ 数据校验
→ Replay Engine
→ Evaluation Framework
→ 第一批分类外出数据
→ GNSS Reliability
→ LTE Baseline
→ IMU State Baseline
→ Multisource Fusion
→ Location / State Belief
→ Proactive Safety
→ Active Sensing
```

---

# 24. 一句话项目基线

> **Ego Link A线的目标，是把持续可获得的低功耗物理世界信号转化为对“位置、状态、风险与下一步感知行动”的持续概率判断，并通过真实数据闭环不断学习和迭代。**

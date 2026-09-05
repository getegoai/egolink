---
document_status: authoritative
last_verified: 2026-08-23
verified_by: codex
owner: founder
decision_adr: ../architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md
productization_adr: ../architecture/adr/ADR-0012-p0-productization-sprint-1.md
---

# Ego Link A线当前阶段记忆与执行基线

> 项目：Project EGO / Ego Link
> 模块：A线 — Personal Physical Intelligence Engine
> 日期：2026-08-17（2026-08-18 经创始人再次确认）
> 状态：当前有效阶段性基线
> 架构决策：[ADR-0010](../architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md)

## 2026-08-23 Productization Sprint 1 集成说明

[ADR-0011](../architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md)
将首发闭环定为 `Reliable Location + Ego Call + SOS`。本文件继续控制 A 线的
异步观测、事件时间、持久化、回放和数据评估方法，但不再构成全项目串行许可链：
Reliable Location 的产品证据是首发必需；旧 L1-000/FT-001B/EXP-A1-000 链的
资产可复用，但不再构成全局或 `P0-LOC` 的串行前置。L2 连续 IMU/估计器工作
可并行且不能阻塞 LOC-021/FIELD-020；高级 L3 上下文能力后续演进。当前已验证
的仍只是有界 exact-100 IMU 窗口；连续 120–180 秒 IMU 与持久 spool 必须由
L2-001 单独实证。

[ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md)
进一步冻结 Sprint 1：设备端 Location Engine v0 / Sensor Policy v0 持有断网时仍
需工作的最小 operational state，VPS 负责版本化镜像、事件时间轴、回放、比较与
更丰富的 derived fusion，不再是唯一 live owner。AI 当前执行顺序是
`data quality -> event-time replay -> offline comparison -> Shadow Mode`；学习式
多源融合、相机 AI 和广义状态理解均为非阻塞 L2/L3。`P0-LOC`、`P0-CALL`、
`P0-SOS` 当前全部为 `NOT_RUN`，本文件中的 A-R0、数据工具或模型候选不能改变
这些 Gate。

## 1. 当前总体状态

Ego Link 已具备真实外出测试基础：

- GNSS 可采集并上报，但室内/遮挡环境出现 `no_fix` 属正常情况；
- LTE 可采集原始蜂窝观测并上报；
- 六轴 IMU 已接入，已有有界高频窗口采集验证；
- 开发板 Camera 仅为可选实验观测源；是否采集由单独授权、功耗与隐私任务决定，
  不阻塞 Sprint 1；
- Audio 暂未接入，不阻塞当前 A线；
- Web AI Control Plane 已部署并作为研发事实中枢使用；
- 当前阶段仍为 `A-R0 — AI Data & Evaluation Platform`；
- A-R0 Gate 必须由真实 Field Evidence 驱动，不能因工具代码完成而提前标 PASS。

A线产品主线：

```text
Where am I?
→ What is happening?
→ Is this normal / safe?
→ What evidence am I missing?
→ Should I do something?
```

## 2. 当前正式数据架构

多传感器采用**异步独立采集**，不要求设备端在同一时刻同步采样。

不同传感器按各自物理特性与功耗策略运行：

```text
IMU       高频连续/窗口采样
GNSS      按GNSS自身更新与功耗策略
LTE       数秒～数十秒或事件触发
Camera    自动低频JPEG snapshot / 后续事件触发
Audio     后续短窗口/事件触发
```

设备端正式职责：

```text
Sense
→ Timestamp
→ reduce minimum operational Location/Sensor Policy state
→ Persist
→ Upload
```

VPS 正式职责：

```text
Ingest
→ Align
→ Replay
→ Fuse
→ Learn
→ Evaluate
```

设备端不承担复杂跨传感器时间对齐，但必须维护断网安全所需的 last trusted
location、belief/uncertainty、GNSS/LTE/mobility/battery/policy state 与 action
lineage。VPS 根据各 Observation 的事件发生时间重建统一时间轴；derived fusion
保留独立 generator/config identity，不能覆盖或倒灌伪造设备当时状态。

## 3. 采集失败也是有效观测

必须区分：

```text
not_attempted
success
no_fix
timeout
error
```

尤其：

- `GNSS fix`：GNSS 当前形成了有效位置解；
- `GNSS no_fix`：GNSS 当前无法形成有效位置解，不等于模块故障；
- 即使存在 `fix`，位置仍可能漂移或不可信，因此后续仍需要 GNSS Reliability Estimator。

禁止在无数据时补造位置、补造标签或伪造 Baseline。

## 4. 时间体系

所有原始数据必须保存事件发生时间。

推荐 Observation Envelope 至少包含：

```text
record_id
device_id
boot_id
source
sequence_id

capture_monotonic
capture_utc
timestamp_source
timestamp_quality

status
payload
```

如果传感器自身提供 source timestamp，一并保存。

VPS 另外保存：

```text
receive_time
ingest_time
```

分析和对齐以 `capture/event time` 为准，不能使用网络到达时间代替事件时间。

设备时间采用：

```text
boot-scoped monotonic
+
UTC anchor
```

单调时钟保证同一 boot 内时间连续；UTC 可由 GNSS time、蜂窝网络时间、NTP 或设备 RTC/system clock 在可用时校准。

第一阶段不追求复杂高精度时钟同步，但必须保留时间来源与时间质量。

## 5. Store-and-Forward

网络临时失效属于正常产品场景。

设备端应采用简单、持久化、有限容量的 Store-and-Forward：

```text
Sensor Observation
→ Local Persistent Queue
→ Network available?
    ├─ No: keep queued
    └─ Yes: upload
             ↓
            VPS ACK
             ↓
            safely acknowledge/delete
```

原则：

- 采集先本地持久化，再尝试上传；
- ACK 前不能删除唯一副本；
- 支持重启恢复；
- `record_id / sequence_id` 用于去重；
- 有容量上限；
- 网络恢复后补传；
- 保持实现简单，不新增复杂消息基础设施。

优先复用 Ego Link 已有 reconnect / store-forward / reboot-aware 能力。

当前 FW-007 只有易失性 outbox、当前 boot 内有限 retry 与单向链路接管；
尚未实现或验证持久队列、重启恢复、ACK 后安全删除和断网补传。上述
Store-and-Forward 是已批准的下一步架构要求，不是当前开发板能力声明。

## 6. IMU 数据策略

高频 IMU 不逐样本发送网络请求。

采用 chunk/window，例如：

```text
chunk_id
boot_id
start_monotonic
start_utc
sample_period
sample_count
samples[]
```

VPS 可根据：

```text
sample_time = chunk_start + index × sample_period
```

恢复单样本时间。

当前已经验证有界 IMU window 采集与约 50 ms cadence。

当前关键问题不是继续证明 IMU 能采，而是确保真实 IMU 原始样本：

```text
Device
→ VPS DB
→ bounded read-only export
→ Field Session pack
→ Replay
```

链路完整。

## 7. Camera 与外场自动化原则

Sprint 1 覆盖规则：Camera 不在 P0 关键链，也不默认自动采集。若单独实验任务获
授权，只允许带 `event_time`、`trigger_reason` 和清晰隐私/电源状态的一张 still；
不得用 Camera 结果产生或否决 Location/SOS 决策。以下内容保留为数据研究方向，
不是当前固件或首发验收要求。

Field Dataset Protocol 长期采用：

> **低培训、低操作、自动采集。**

Naturalistic Session 理想操作：

```text
拿设备
→ 挂上/佩戴
→ 启动Session
→ 正常活动
→ 结束/回收
```

测试过程中尽量零操作。

Camera 后续实验阶段：

- 不要求测试人员手动拍照；
- 经明确授权后评估低频 JPEG snapshot；
- `neck_forward` 可作为正式 `mount_state`；
- 不使用持续视频作为默认采集方式；
- 如果自动 Camera 需要明显 firmware 重构，当前可暂缓；
- Camera 缺失不阻塞首个 GNSS blackout 实验。

Camera 能力演进：

```text
环境记录
→ 后标注辅助
→ Visual Anchor
→ Camera→IMU Teacher
→ Active Perception
```

手机 Sidecar 只是可选的 Field Test Companion / Orchestrator，不是数据采集必需组件，也不能成为 Session 成功的单点依赖。

## 8. LTE 当前定位

继续保留原始蜂窝观测，例如硬件可提供的：

```text
MCC
MNC
TAC
Cell ID
PCI
RSRP
RSRQ
RSSI
SINR
neighbor cells
```

当前不要求为了首个实验先建立完整 LTE 定位模型。

原术语 `centroid artifact` 面向用户和控制台优先改称：

> **Cell coarse-location mapping / 蜂窝小区粗位置映射**

最简单的映射可由历史高质量 GNSS 位置为 Cell 观测建立代表位置与覆盖范围。

后续路线：

```text
Cell coarse location
→ fingerprint
→ neighbor-cell fingerprint
→ Cell sequence
→ learned LTE location model
```

没有粗位置映射时：

```text
LTE location baseline = unavailable
```

这是合法实验结果，不阻塞首个 Smoke Experiment。

## 9. 历史可复用 Field Test 结论

最近 FT-001 探针已确认：

- LTE 命令链可触发真实 IMU window；
- 3/3 `capture_imu_window` 返回 OK；
- cadence 已验证；
- 同一 boot 可跟踪；
- 没有伪造 GNSS/LTE/IMU/Camera Baseline。

但尚未形成首个可 Replay 的定位实验 Session，原因包括：

- GNSS 当时全部 `no_fix`，无有效 Ground Truth；
- IMU 只有离散短窗口；它们足以作为 FT-001B 的诚实异步观测，但不能宣称
  连续覆盖，连续 120–180 秒采集已移交非阻塞的 L2-001；
- VPS 中真实 IMU 样本仍需可靠有界导出；
- LTE 只有原始观测，暂无粗位置映射；
- Camera 自动采集当前可暂缓。

因此：

```text
FT-001 Acquisition Probe = useful / verified
FT-001B Replayable Session = pending
EXP-A1-000 = not run
A-R0 = 0/8
```

这些事实仍可作为 LOC-021/FIELD-020/REPLAY-010 的输入，但 FT-001B 和
EXP-A1-000 不再是当前 P0-LOC 的串行许可门；其硬件等待不能阻塞其他 lane 或
已具备依赖的 Sprint 1 工作。

## 10. 历史 A 线 L1 工程任务：FT-001B

原任务目标：

> **First Replayable Asynchronous GNSS+IMU Session**

不再要求严格同步四源 Session。

最低必要条件（以当前 FT-001B task packet 为准）：

1. 无遮挡室外获得真实有效 GNSS 连续轨迹；
2. 同一 boot / Field Session；
3. 同一 Session 至少 3 个真实 exact-100 IMU 离散窗，每个窗及窗间 gap
   均显式保存，不冒充连续 IMU 或 IMU 定位；
4. 原始数据可靠进入 VPS；
5. VPS 有界只读导出成功；
6. Packer 成功；
7. Replay 能重建时间线与 GNSS trajectory。

LTE 是 opportunistic source。

Camera 是 optional source。

人工事件标记不是前置条件。

## 11. 历史相邻实验：EXP-A1-000

若 FT-001B 在独立硬件窗口完成，可复用其 Session 执行下述 blackout 实验；
它不控制 LOC-021/FIELD-020、Call/SOS、可靠性安全或 A0/合规的当前调度。

执行：

```text
完整真实GNSS轨迹
→ 中间人为mask 60秒GNSS
→ Replay
```

至少比较：

### Baseline A

```text
Last Known Position
```

### Baseline B

```text
LTE coarse location
```

仅当已有真实粗位置映射时使用，否则 `unavailable`。

### Baseline C

```text
IMU-assisted baseline
```

仅当已有可信方法能产生位置结果时使用。

如果 IMU 当前只能可靠提供：

```text
moving
stationary
motion intensity
turning
```

则：

```text
IMU position baseline = unavailable
```

不得为了完整图表临时创造未经验证的位置算法。

## 12. Sprint 1 禁止事项与历史约束

不得以下列工作替代 LOC-021/FIELD-020 的真实 `P0-LOC` 证据或擅自晋级
learned estimator。FT-001B/EXP-A1-000 的等待不是新增基础设施的理由，也不
禁止 CALL/SOS、TLS/持久队列、确定性 Safety Kernel、A0/合规等独立 lane 按
各自 task 推进：

- 扩展新的 Control Plane 功能；
- 继续设计复杂 Schema；
- 要求多传感器硬同步；
- 建生产级 IMU 校准体系；
- 为 Camera 大规模重构 firmware；
- 为 LTE 先建设完整基站位置数据库；
- 训练复杂定位神经网络；
- 上 Transformer；
- 扩展 Factor Graph；
- 开发 Safety Model；
- 开发 RL sensing policy；
- 用 synthetic trajectory 冒充真实 Field Evidence。

当前原则：

> **真实数据发现的问题优先于预想问题。**

## 13. 历史 Qwen / Codex 分工（非当前调度 authority）

以下分工保留为阶段记录。当前所有 builder 以
`FIRST_LAUNCH_EXECUTION.md`、active packet 和共享路径 WIP 规则为准。

### Qwen

主要负责 Execution Plane：

- 复用/完善 Store-and-Forward；
- 打通 VPS IMU bounded read-only export；
- 执行 FT-001B；
- Pack / Replay；
- 执行 EXP-A1-000；
- 不扩大任务范围。

### Codex

主要负责：

- Control Plane 当前事实更新；
- 独立架构 Review；
- 检查是否重复造 Store-and-Forward；
- 检查 capture time / receive time 语义；
- 验证 Field Evidence；
- 保持 A-R0 Gate 真实；
- 防止重新陷入过度设计。

## 14. 当前决策原则

如果旧文档与本文冲突，以本文及之后明确批准的 ADR / Current Task 为准。

当前最重要的 A 线里程碑是：

> **把 LOC-020/POLICY-010/REPLAY-010 的 device-semantic reference 收敛为
> 一个 review boundary，随后通过 LOC-021 建立 device operational state、server
> event-time mirror 和 Guardian view，再由 FIELD-020 形成代表性证据。**

旧 FT-001B/EXP-A1-000 数据可在独立硬件窗口继续产生并进入这一证据链，但不
阻塞已有依赖的 Sprint 1 切片。AI 模型只在数据质量、Replay 与 offline/Shadow
比较之后讨论晋级；其他互不冲突的 lane 继续执行。

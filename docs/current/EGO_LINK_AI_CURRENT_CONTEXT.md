---
document_status: authoritative
last_verified: 2026-08-18
verified_by: codex
owner: founder
decision_adr: ../architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md
---

# Ego Link A线当前阶段记忆与执行基线

> 项目：Project EGO / Ego Link
> 模块：A线 — Personal Physical Intelligence Engine
> 日期：2026-08-17（2026-08-18 经创始人再次确认）
> 状态：当前有效阶段性基线
> 架构决策：[ADR-0010](../architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md)

## 1. 当前总体状态

Ego Link 已具备真实外出测试基础：

- GNSS 可采集并上报，但室内/遮挡环境出现 `no_fix` 属正常情况；
- LTE 可采集原始蜂窝观测并上报；
- 六轴 IMU 已接入，已有有界高频窗口采集验证；
- 开发板自带 Camera，后续按自动低频 snapshot 策略采集；
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

设备端不承担复杂跨传感器时间对齐。VPS 根据各 Observation 的事件发生时间重建统一时间轴。

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

Camera 第一阶段：

- 不要求测试人员手动拍照；
- 优先自动低频 JPEG snapshot；
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

## 9. 当前 Field Test 结论

最近 FT-001 探针已确认：

- LTE 命令链可触发真实 IMU window；
- 3/3 `capture_imu_window` 返回 OK；
- cadence 已验证；
- 同一 boot 可跟踪；
- 没有伪造 GNSS/LTE/IMU/Camera Baseline。

但尚未形成首个可 Replay 的定位实验 Session，原因包括：

- GNSS 当时全部 `no_fix`，无有效 Ground Truth；
- IMU 只有离散短窗口，不是连续 120–180 秒；
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

## 10. 当前唯一工程主线：FT-001B

当前目标：

> **First Replayable Asynchronous GNSS+IMU Session**

不再要求严格同步四源 Session。

最低必要条件：

1. 无遮挡室外获得真实有效 GNSS 连续轨迹；
2. 同一 boot / FS ID；
3. IMU 连续覆盖至少 120–180 秒；
4. 原始数据可靠进入 VPS；
5. VPS 有界只读导出成功；
6. Packer 成功；
7. Replay 能重建时间线与 GNSS trajectory。

LTE 是 opportunistic source。

Camera 是 optional source。

人工事件标记不是前置条件。

## 11. FT-001B 后立即执行 EXP-A1-000

FT-001B 一旦成功，停止继续扩展基础设施。

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

## 12. 当前禁止事项

在 FT-001B + EXP-A1-000 真实结果出来前，不应：

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

## 13. Qwen / Codex 当前职责

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

当前最重要的里程碑已经从：

> “地图能看到设备”

更新为：

> **真实异步多源数据能够可靠地产生、保留事件时间、在断网情况下尽量不丢失、最终从 VPS 导出并 Replay；随后通过人为 GNSS blackout 第一次量化系统在 GNSS 信息被移除后还知道什么。**

完成 EXP-A1-000 后应暂停继续实现，把真实结果提交给架构 Review，再决定第一个正式 AI 模型是 GNSS Reliability、IMU Shared Encoder、LTE Fingerprint，还是其他最需要解决的能力。

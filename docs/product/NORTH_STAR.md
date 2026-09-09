---
document_status: authoritative
decision_updated: 2026-09-09
last_verified: 2026-08-23
verified_by: codex
owner: founder
---

## 2026-09-09 Founder Single-Board Camera Milestone Update

[ADR-0015](../architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md)
narrows the current A-line milestone to one identified SIM7670G connectivity
board plus its necessary Camera, existing external IMU, power source and
antennas. It must collect Location/raw observations, retain an honest bounded
offline backlog, upload ordinary observations over actual Wi-Fi and LTE with a
controlled transition, capture authorized JPEG stills and deliver them over
real LTE to durable VPS storage and the existing Web surface before FIELD-020.

AMOLED and board-to-board forwarding are not A-line dependencies. CALL-020,
CALL-021 and full physical SOS are paused for this milestone; their code,
evidence and final product obligations remain. Hardware architecture and China
pre-compliance continue independently. Camera is a required milestone output,
not a fourth sellable-P0 Gate, a visual-AI launch dependency or a Location/SOS
decision source.

This direction creates no new hardware, network, image or field evidence. The
three product Gates remain `NOT_RUN`, and the final first-launch promise remains
Reliable Location + Ego Call + physical SOS.

## 2026-09-05 Prior Founder Runtime-Convergence Update

[ADR-0014](../architecture/adr/ADR-0014-runtime-convergence.md) recorded the
prior founder-directed implementation unit: reuse LOC-021 A-S to deliver
bounded real-device Location -> authenticated secure transport -> bound
Guardian. At that point real bidirectional CALL and embedded-bearer validation
were scheduled in parallel, followed by physical SOS and recovery.

An isolated S smoke or finite current-boot/single-source live profile does not
wait for T0/T1. The original concurrent SOS/IMU ordering and recovery promises
remain required for that product composition or an explicitly reviewed and
behaviorally proven equivalent. No new global framework displaces the shortest
missing runtime seam. Local state and input-recognition feedback continue with
explicit queue/storage degradation; stored, received and human-noticed claims
still require their own evidence. Secure transport never downgrades to HTTP or
disables certificate/hostname verification to meet a schedule.

This is a decision update, not new `last_verified` hardware evidence. All three
P0 Gates remain `NOT_RUN`. Source, build, native concurrency, hardware, network,
field and product evidence are reported separately. The active packet is
[P0-CONVERGENCE-20260905](../tasks/active/P0-CONVERGENCE-20260905.md).

## 2026-08-23 Founder First-Launch Update

The first-launch value loop is now **Reliable Location + Ego Call + physical
SOS**, as accepted by
[ADR-0011](../architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md)
and operationally frozen by
[ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md).
The launch remains people-first: children and older adults are the primary
personas, adult use is compatible, and pet use remains a later platform
variant.

The sellable P0 release decision is deliberately smaller than the long-term
capability map:

| Gate | Capability | First-launch requirement |
| --- | --- | --- |
| `P0-LOC` | Reliable Location | must `PASS` |
| `P0-CALL` | Ego Call | must `PASS` |
| `P0-SOS` | physical-SOS loop | must `PASS` |
| `L2-AI` | AI-enhanced location | best effort; non-blocking |
| `L3` | context/event understanding | outside the launch critical path |

Productization Sprint 1 therefore adds no new sensor dependency and does not
build learned multi-source fusion, camera AI, general anomaly detection, a
polished complete app, PSTN, or native VoLTE. Interfaces and honest collection
hooks remain, but only Location Engine/Sensor Policy/Replay, the minimum real
Ego Call chain, SOS composition, and their product-assurance evidence consume
P0 critical-path capacity.

`Ego Call` over LTE data through a controlled RTC service and Guardian app is
the first-launch communications path. Native VoLTE is no longer a software
launch blocker; A0 must still preserve and evaluate a viable modem, audio,
power, and RF migration path under `G0V-VOLTE-RESERVE`.

`L1 Location`, `L2 Intelligence`, and `L3 Awareness` are capability-priority
layers, not replacements for the product-assurance gates. L1 is launch
mandatory, L2 is bounded best effort, and advanced learned L3 behavior evolves
after launch. A minimum deterministic `Rule Policy v0`/Safety Kernel remains on
the launch path: physical SOS, local feedback, location attempt, user outcome,
durable event recording, and honest `pending`/`failed` delivery state cannot be
deferred or vetoed by AI.

The 2026-08-23 execution model was multi-lane: Location evidence, Ego Call/SOS,
reliability and power, A0 hardware, privacy/compliance, and bounded AI/data work
could advance in parallel. The latest accepted ADR controls which independent
lanes are actually scheduled; ADR-0015 currently pauses CALL and full SOS while
the single-board Camera milestone, A0 hardware and compliance continue.

## 2026-08-14 Founder Product-Baseline Update

The current sales-product direction is now the screenless modular EgoLink Core
defined in [EGO_MASTER_CONTEXT.md](EGO_MASTER_CONTEXT.md) and accepted by
[ADR-0008](../architecture/adr/ADR-0008-egolink-core-product-direction-reset.md).
This North Star continues to own the highest-level purpose, evidence honesty,
48-hour measured guard target, Demo-first iteration, and D2/D5 execution
principles. The master owns current product requirements and system roles;
specialized facts remain with the authorities routed by `CONTEXT_INDEX.md`.

The new product PCB/enclosure/BOM path and the current ESP32-S3/SIM7670G
development path run in parallel. A product candidate must not overwrite
current-board evidence, and development boards must not be mistaken for the
sales product.

## 2026-07-09 Founder Direction Update

Continuous outdoor testing is a product regression loop, not an endless gate.
D1 is accepted for transition once the 4G board -> LTE -> VPS -> Dashboard
link is visible, repeatable, and reportable with honest non-claims. Longer
FIELD/PWR runs continue as regression and evidence collection, but they do not
block D2/D5 startup.

Current execution focus moves to the D2 -> D5 mainline:

- D2: establish the first location-accuracy baseline using median error,
  fix rate, and TTFF, with reference-point evidence and Dashboard/map
  visibility.
- D5: build the location-data flywheel from collected field evidence into
  cleaned, labelled, privacy-reviewed samples and eventually model/rule
  improvement loops.
- Map view is a D2/D5 usability and evidence-review requirement. Absence of a
  third-party map API is not a D1 blocker; use no-key/local coordinate and
  trajectory views until a provider/key/privacy decision is made.
- Tiny Safety and safety-classification assets remain reusable later, but the
  immediate AI/data mainline is location accuracy improvement, not synthetic
  safety classification.

# EgoLink 北极星与开发指导原则（NORTH STAR）

本文件是全项目最高层指导原则。任何执行者（Codex、Claude、其他 AI 或人）在开始
任何任务前必须先读本文件；当前销售产品要求和系统角色同时以
`EGO_MASTER_CONTEXT.md` 为准。当专项事实冲突时按 `CONTEXT_INDEX.md` 的
authority 分工处理，不得用本文件覆盖实机证据、协议或 accepted ADR。本文件
只能由创始人决策修改（由 Director 代笔），每次修改必须更新日期并在
`## 变更记录` 留一行。**执行者每次开工必须核对本文件日期，感知目标是否已
变化，并据此调整手头工作——这是防止路线漂移的强制机制。**

## 1. 最终产品（不可漂移的目标）

随身 AI 主动守护定位器（中国市场）：
首发用户价值闭环固定为 **可靠定位 + Ego Call + 实体 SOS**；Ego Call 通过 LTE
数据、受控 RTC 服务和 Guardian app 实现。所有远程动作都必须显示真实送达状态，
网络或 RTC 不可用时，本地 SOS、定位尝试、反馈和有界事件记录仍继续。

1. **核心功能一：定位**。至少以 GNSS、基站和 IMU 形成诚实降级的多源定位，
   配省电策略——传感器按需/占空比工作，绝不持续全速常开。Wi-Fi/BLE 是否
   进入量产产品由 Master Context 与独立 2.4 GHz/RF 门禁决定，基础安全链路
   不得预先依赖它。
2. **核心功能二：首发安全底座**。首发内置、可审计、可回放的规则式 Safety
   Kernel，但 Sprint 1 只负责实体 SOS、本地反馈、定位升级、低电/离线诚实状态、
   持久事件与有界重试。通用异常候选、主动 check-in、上下文理解和学习式风险
   判断保留接口与数据能力，转入 L2/L3，不占首发关键路径。AI 永远不能否决人工
   SOS 或强制安全动作。
3. 量产目标：按 ADR-0008 形成独立定制的模块化 EgoCore PCB，而不是简单相加
   两块开发板能力；48h 守护续航是硬指标，量产定义见
   `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`。

能力优先级使用 `L1 Location`、`L2 Intelligence`、`L3 Awareness`；它们用于安排
资源，不替代通信、定位、功耗、可靠性、防水声学、RF 和 NPI 等产品放行门。

## 2. 迭代哲学：Demo 阶梯，先通后好

**不做一步到位的完美产品。** 路径是 Demo → 第一台原型 → 版本化持续迭代。
每个 Demo 都是一个可刷机、可演示、打了 tag 的版本。定位精度一开始可以不
准，但**链路必须先通**；之后每个版本通过增加传感器数据、改进算法让精度
可量化地上升——"AI 逼近"本身就是发版节奏的主线。

### Demo 阶梯（当前版本）

| Demo | 目标（验收即演示给创始人） | 精度/指标要求 |
|---|---|---|
| **D1 链路通** | 4G 板+电池独立运行：定时采集 GNSS/基站/IMU/电量 → LTE 上报 → 服务器给出一个位置估计 → 看板地图可见 | 有位置就行，不要求准；上报成功率、电量曲线开始记录 |
| **D2 精度爬坡开始** | 加入 Wi-Fi 指纹 known-place 与 last-known 衰减，服务器端融合（EALE-P0 落地跑通）；建立参考点误差测量 | 首次输出误差中位数/fix率/TTFF 三个指标，形成基线 |
| **D3 可佩戴外场** | 挂脖外场 24h+：省电状态机（PWR-002 的 L0-L4）生效，轨迹回放可看 | 24h 实测续航数字；外场误差 vs D2 基线 |
| **D4 主动安全第一步** | 运动异常候选（阈值/统计即可）→ 自动通知联系人（短信或推送）闭环 | 误报率开始记录（打"实验性"标签） |
| **D5 数据飞轮转起来** | 外场数据→标注→模型/参数更新→下一版精度提升，形成"发版即变准"的可见循环 | 精度演进曲线（逐版本对比）上看板 |

这张 Demo 表保留研发谱系，不重开当前首发范围。Productization Sprint 1 直接围绕
`P0-LOC`、`P0-CALL`、`P0-SOS` 取用已有 D1/D2/D5 工具；D4 异常通知在首发后或
独立非阻塞实验中推进，不能成为进入定位、通话或 SOS 工作的串行前置条件。

每完成一个 Demo：打 tag（v0.D.x）→ 一页 demo 报告（含指标对比上一版）→
创始人验收。`才进入下一级` 只约束同一证据依赖链，不要求不同工作线天然串行；
实际并行项仍服从最新 accepted ADR。ADR-0015 当前暂停 Ego Call/完整 SOS，
D2/D5、可靠性/功耗、产品 A0 和合规继续按各自依赖推进。指标定义一旦建立
（D2）就逐版本追踪，不许断。

## 3. 防漂移规则（对执行者的硬约束）

1. 每个任务开工前自问并在结果中写明：**这个任务服务于哪个 Demo、首发能力
   或产品 Gate？** 答不出来的任务不做，报告 Director。
2. 与当前 Demo、首发能力或产品 Gate 无关的"完善型"工作（重构、补文档、加
   边界声明）一律推迟，除非它阻塞当前依赖链。
3. 连续 3 轮修复仍不过 → 停下上报，不许换路径蛮干（LTE-003 八轮修复的
   教训）。
4. 阻塞超过约 2 小时（等硬件、等决策、等资料）→ 立即上报，不空转。
5. 诚实证据规则不变：没实测过的不许声称；密钥不入库；契约变更须经
   Director。

## 4. 流程轻量化（敏捷规则）

**停止做的事：**
- 每个 fix 单独立档长篇记录——fix 过程写进 commit message 即可。
- STATUS.md 千行部署小说——每次只加 ≤10 行摘要，细节放 reports/。
- 任务包里大段 boundary/non-claim 声明——一句话即可，诚实规则全局适用。
- 为覆盖率而写的仪式性测试——只测会坏的东西。

**保留的事（不是官僚，是保命）：**
- 契约冻结（协议/schema 改动须 Director 审）；
- 硬件证据要素（板子、固件版本、时间、证据路径——一行写完就行）；
- 每任务一次 `verify.ps1` + `context_lint.py`。

任务包简化为：目标（一句）、服务哪个 Demo、验收（可执行命令/可观察结果）、
允许路径。其余字段可省。

## 5. Git 与发版规范

- **GitHub Flow**：`main` 永远可构建可刷机；短分支 `d<demo>/<topic>`
  （如 `d1/power-duty-cycle`）；小步快合，不留长分支。
- **必须建远程仓库**（当前没有远程，这是风险）：创始人建 GitHub 私有仓库
  或 VPS Gitea，之后每日至少 push 一次。
- Commit 规范：`<type>(<scope>): <说明> [D<n>]`，type ∈ feat/fix/power/
  loc/safety/ops/docs；例：`feat(loc): add wifi fingerprint upload [D2]`。
- 每个 Demo 验收即打 tag `v0.<demo>.<iter>` 并出一页报告。

## 6. 汇报与看板

- 看板 `docs/generated/PROGRESS_BOARD.md` 是面向创始人的脱敏派生视图，不是
  authority。任务开/关/阻塞以 active/done task packet、`STATUS.md` 和
  `CONTEXT_INDEX.md` 的专项事实源为准；派生看板必须由脚本刷新，不能手改。
- 上报给创始人的三类事：Demo 验收就绪、阻塞（含缺硬件/缺决策/缺资料）、
  目标疑似冲突（发现两个权威文档打架时停下来问，不自行裁决）。

## 7. 硬件与省电策略

- **当前主开发板 = 4G 板（ESP32-S3-SIM7670G）**，继续作为 D1-D5
  软件、通信、定位和数据证据车；它没有产品屏幕，其他能力只能按
  `ACTIVE_BUILD.md` 和 `BOARD_MATRIX.md` 的逐项 verified/observed/unknown
  状态描述，禁止笼统声称“其余功能都有”。AMOLED 板保留为后续交互、CALL
  与台架数据资产，不参与当前 A 线单板里程碑；最终销售产品走 ADR-0008
  的独立定制 PCB 路径，
  不能把两块开发板能力直接相加当作量产证据。
- **省电是定位功能的一部分，不是后补优化**：采用 PWR-002 决策的 L0-L4
  状态机——传感器占空比采样、GNSS 按需脉冲（移动/事件才开）、LTE 批量
  上报。任何新增传感器接入必须同时说明它的占空比策略，"常开"默认禁止。
- 真实电量遥测（MAX17048）已在 PWR-001 实装，电量曲线随 D1 起持续记录。

## 8. 文档层级（谁服从谁）

NORTH_STAR（原则）→ `EGO_MASTER_CONTEXT.md`（当前销售产品方向）→ accepted
ADR / 专项 authority（实现边界）→ roadmap / task packet（执行）。STATUS、
ACTIVE_BUILD 和 BOARD_MATRIX 反映现状；machine-readable contracts 控制协议。

## 变更记录

- 2026-09-09 Founder accepted ADR-0015: current A-line evidence moves to one
  4G board with bounded Camera capture/persistence/LTE/VPS/Web closure before
  FIELD-020; AMOLED/CALL/full SOS are outside this milestone, while the final
  three P0 Gates and parallel hardware/compliance work remain unchanged.

- 2026-09-05 Founder accepted ADR-0014: runnable Location first, concrete CALL
  in parallel, then physical SOS/recovery; scoped T0/T1 and local-failure
  invariants; original product Gates and hardware evidence unchanged.

- 2026-08-23 创始人进一步冻结 Productization Sprint 1：规则 Safety Kernel 的
  首发责任收敛到实体 SOS、定位升级、低电/离线诚实状态和持久事件；异常候选、
  主动 check-in 与广义状态理解转入 L2/L3，不再作为首发前置任务。
- 2026-08-23 创始人确认首发收敛为 Reliable Location + Ego Call + SOS；
  ADR-0011 将 LTE 数据 RTC/Guardian app 设为首发通话主线，把 Native VoLTE
  调整为并行 `G0V-VOLTE-RESERVE`，并明确 L1/L2/L3 是能力优先级、最低规则
  Safety Kernel 首发内置、高级上下文模型后置及多线并行执行。
- 2026-08-14 创始人确认新版 Master Context 为当前销售产品方向基线；ADR-0008
  记录无屏模块化 EgoCore 路线，并保留开发板 D2/D5 主线并行推进。
- 2026-07-09 创始人更新：D1 连续外场测试改为持续回归，不再作为无限期转入卡点；
  启动 D2 定位精度基线与 D5 定位数据飞轮，地图视图进入 D2/D5 证据可视化。
- 2026-07-04 创始人定调：Demo 阶梯 + 敏捷轻流程 + 4G 板为主板 + 省电定位
  优先、AI 主动安全其次；初版发布。

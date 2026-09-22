---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
owner: founder
---

## 2026-09-22 Decision migration

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
承接下方 9/19 决策与 9/22 对齐指令，明确蜂窝原生主路、RTC 备路、Ego Base
同步最小私有终点与云端有界工程过渡。已有规则状态真实性纳入本轮工程验收；
高级 L2/L3 与完整 Base AI 不新增首发能力 Gate。当前工作分工见
[FIRST_LAUNCH_EXECUTION](../current/FIRST_LAUNCH_EXECUTION.md)。
以下日期章节保留决策演进；较旧的 RTC-first、native reserve 与 Base 后置条款
已按 ADR-0016 部分取代，不能作为当前调度或硬件结论。

## 2026-09-19 Founder Ego-State Estimation & Home Station Update

创始人于 2026-09-19 对产品终局目标、系统架构与通话策略做出重大决策修订：

1. **终局目标升维：随身主动状态估计（Active Ego-State Estimation）**
   - 本产品的本质与终局目标是**随身主动状态估计**，而不只是普通定位器。
   - 对普通用户而言，“状态估计”专业抽象，但“定位”人人皆知，因此**高精度定位是面向用户最直接、最易感知的核心功能入口**与关键证据支柱。
   - 产品的终局系统目标是通过高可靠定位、多轴惯性传感（IMU）、环境与生理等多源数据构筑完整的可信证据链，主动推断与估计用户所处的物理轨迹、活动姿态、生理与环境状态，并自动生成结构化的用户状态报告与守护洞察。

2. **最高设计原则：强隐私性（Strong Privacy）与 本地优先（Local-First）**
   - 强隐私性与本地优先确立为全系统的最高指导原则，高于远端集中式公有云服务。
   - 用户个人轨迹、传感器明细与多模态数据的所有权和物理存储必须归属用户自身。

3. **系统新支柱：同步研发家庭基站（Home Station / Ego Base）**
   - 随身穿戴设备（EgoLink Core / Wearable）受体积与电池限制，端侧算力存在天然上限。
   - 系统架构中同步研发一套**家庭基站（Ego Base）**：
     - 代替传统集中式公有云服务器，作为用户私有数据和完整历史证据链的物理终点；
     - 承担随身设备的算力后备能力（运行私有大模型、复杂多模态融合分析与状态报告生成）；
     - 云端仅保留穿透代理、信令中继与公网桥接职责，不长期留存用户隐私明细。

4. **通话策略（Task 3.2）重大修订：LTE 蜂窝直拨为主，网络通话为备**
   - 通话链路首要保证：**可以直接使用 LTE 蜂窝语音模块像普通手机一样拨打/接听电话（Native Cellular Voice / VoLTE / CS 语音直拨）**，这是紧急与日常联络最可靠的通信生命线；
   - 纯网络通话（基于 LTE 数据的 WebRTC / Guardian App 通话）降级为备选/辅助功能，仅在网络与软件环境完备时作为低成本补充；
   - 当前开发板（ESP32-S3 + SIM7670G）暂无板载麦克风与扬声器硬件，跳过该板的声学闭环验证，避免在无音频外设的板子上强行开发测试 RTC 语音。


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

The 2026-08-23 first-launch value loop was **Reliable Location + Ego Call + physical
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

At that time Productization Sprint 1 added no new sensor dependency and did not
build learned multi-source fusion, camera AI, general anomaly
detection, a polished complete app, PSTN, or native VoLTE; the native-call
exclusion is superseded by ADR-0016. Interfaces and honest collection
hooks remain, but only Location Engine/Sensor Policy/Replay, the minimum real
Ego Call chain, SOS composition, and their product-assurance evidence consume
P0 critical-path capacity.

At that decision date, `Ego Call` used LTE data through controlled RTC and
Native VoLTE was `G0V-VOLTE-RESERVE`. ADR-0016 replaces those communications
clauses with native cellular primary and RTC optional fallback.

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

随身主动状态估计守护仪（中国市场，面向用户呈现为高可靠随身主动守护定位器）：
终局产品本质是**随身主动状态估计**，定位是面向用户最直观、最易感知的核心功能入口与关键证据支柱。
以**强隐私性、本地优先**为最高准则，同步研发**家庭基站（Ego Base）**替代传统公有云服务器，并承担随身设备算力不足的后备推理能力。
首发用户价值闭环固定为 **可靠定位/状态估计 + Ego Call（LTE 蜂窝直拨优先，网络通话备选）+ 实体 SOS**。所有远程动作都必须显示真实送达状态，网络不可用时，本地 SOS、状态/定位尝试、反馈和有界事件记录仍继续。

1. **核心功能一：状态估计与可靠定位**。至少以 GNSS、基站和 IMU 形成诚实降级的多源证据链，推断用户物理运动/空间状态并形成报告；配省电策略——传感器按需/占空比工作，绝不持续全速常开。Wi-Fi/BLE 是否进入量产产品由 Master Context 与独立 2.4 GHz/RF 门禁决定，基础安全链路不得预先依赖它。
2. **核心功能二：首发安全底座与通话生命线**。通话首要保证使用 LTE 模块直接进行蜂窝语音通话（Native Cellular Voice / VoLTE / CS 呼叫，像手机一样通话），纯网络通话（RTC）仅作为备选；规则式 Safety Kernel 负责实体 SOS、本地反馈、定位升级、低电/离线诚实状态、持久事件与有界重试。通用异常候选、主动 check-in、上下文理解和学习式风险判断转入 L2/L3。AI 永远不能否决人工 SOS 或强制安全动作。
3. **核心功能三：强隐私与家庭基站后备**。随身穿戴设备与家庭基站（Ego Base）协同，基站作为用户私有数据和完整历史证据链的物理存储终点与私有计算中心，公有云仅作为网络穿透与信令中继。
4. 量产目标：按 ADR-0008 形成独立定制的模块化 EgoCore PCB，而不是简单相加两块开发板能力；48h 守护续航是硬指标，量产定义见 `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`。

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
- **远程备份与协作**：按 `docs/development/GIT_FLOW.md` 核验当前 remote、访问权限和分支；
  不沿用历史“当前没有远程”的状态断言。保持可恢复提交与授权的远程备份。
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

- 2026-09-22 按创始人对齐指令接入 ADR-0016；明确旧条款适用期、当前分工与远程状态核验，不新增硬件证据。

- 2026-09-19 创始人决策修订：产品终局目标定调为“随身主动状态估计”，定位为最直观用户功能与核心证据；确立强隐私性、本地优先高阶原则，同步研发家庭基站（Ego Base）替代公有云并作为随身设备算力后备；通话策略首要保证 LTE 蜂窝直拨通话（像手机一样通话），网络通话转为备选；开发板跳过无麦克风扬声器的音频测试。

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

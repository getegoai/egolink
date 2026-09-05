---
document_status: historical
source_date: 2026-08-18
archived: 2026-09-05
superseded_by:
  - ../../product/NORTH_STAR.md
  - ../../product/EGO_MASTER_CONTEXT.md
  - ../../current/FIRST_LAUNCH_EXECUTION.md
---

# Ego Link 产品能力与首发策略记忆基线

**版本日期：2026-08-18**
**用途：Ego Link 后续产品设计、AI 能力开发、Codex/多模型协同、任务拆解、PCB/结构设计与首发规划的统一上下文。**

---

## 1. 产品当前核心定位

Ego Link 当前定义为面向儿童、老人，兼顾成年人和宠物场景的 **AI 原生随身安全终端**。第一代产品优先解决用户最直接、最容易理解和验证的需求：

1. **可靠定位**：用户随时尽可能知道 TA 在哪里；
2. **Ego Call**：设备与绑定家属 App 之间能够直接双向语音联系；
3. **SOS**：发生紧急情况时，通过按键触发定位升级、呼叫和事件上报。

第一代产品不等待复杂 AI 全部成熟。产品先解决刚需，再用 AI 增强刚需，最终依靠真实世界数据把定位终端演进为主动安全智能体。

---

## 2. 三层产品能力路线

### L1：Reliable Location —— 可靠定位

**定位：首发必须完成，属于产品上市基本盘。**

目标不是持续开启 GNSS，而是让设备持续维护一个可解释的 `location_belief`，尽可能保证位置服务连续存在。

核心输入包括：

- 最近一次可信 GNSS 位置；
- LTE Cell / 网络环境变化；
- IMU 静止、步行、跑动、乘车等移动状态；
- 时间经过；
- 间歇 GNSS 校准；
- 历史位置与定位质量。

第一层重点指标：

- **Position Availability**：任何时候打开 App，是否有位置结果；
- **Location Accuracy**：位置大致是否准确；
- **Location Continuity**：GNSS 消失后是否仍保留合理位置认知；
- **Update Latency**：设备移动后多久反映位置变化；
- **Battery Life**：定位策略是否满足数天级续航；
- **Failure Explainability**：无 GNSS、弱信号、室内等情况下能否解释当前位置质量。

第一层的关键原则是：

> 位置精度可以降级，位置服务尽量不断掉。

系统可从“精确 GNSS 点”逐步退化为“较可信位置”“大致区域”“最后可信位置 + 当前移动状态”，而不是直接变成 Unknown。

---

### L2：AI-Enhanced Location —— AI 增强定位

**定位：首发前争取完成部分能力，但不得阻塞上市；后续可持续 OTA 增强。**

第二层首先让 AI 服务于定位，而不是急于承担复杂安全决策。

优先模型：

#### 2.1 GNSS Reliability Estimator

判断 GNSS 当前输出是否可信。输入可包括：

- satellites；
- HDOP / accuracy；
- fix age；
- 信号条件；
- IMU 移动状态；
- 历史轨迹；
- LTE 变化；
- 当前环境下 GNSS 历史表现。

核心原则：

> GNSS 有 fix 不等于位置可信。

#### 2.2 Motion / Mobility Model

利用 IMU 判断：

- stationary；
- walking；
- running；
- vehicle；
- unusual movement；
- suspected fall。

这一模型首先服务于定位频率和功耗策略，例如静止时降低定位频率、乘车时提高位置更新速度。

#### 2.3 Multi-source Location Fusion

逐步融合：

- GNSS；
- LTE；
- IMU；
- 历史轨迹；
- 时间；
- 环境特征。

输出不仅包含 `location`，还应包含：

- `uncertainty`；
- `confidence`；
- 主要证据来源；
- 当前移动状态；
- GNSS 可靠度。

第二层 AI 的核心价值是：

> 设备不仅知道“在哪里”，还知道“有多确定”。

---

### L3：Context & Event Understanding —— 状态与事件理解

**定位：上市后依靠真实用户数据逐步演进。**

第三层开始回答：

- 世界有没有发生变化？
- 变化是什么？
- 当前事件意味着什么？
- 是否需要提高感知等级？
- 下一步最值得采集哪个传感器？
- 是否需要主动联系或处置？

长期能力包括：

- Event Model；
- Context Model；
- Camera / Vision；
- Audio；
- 多模态风险判断；
- Event State Machine；
- Sensor Policy；
- 主动安全动作。

长期闭环：

`持续感知 → 状态理解 → 多源定位 → 异常判断 → 主动联系/处置`

---

## 3. 当前研发优先级原则

统一采用：

- **L1 = MUST HAVE**
- **L2 = BEST EFFORT**
- **L3 = POST-LAUNCH**

当前 A 线工作应收缩为：

> **先把 L1 Location Engine 做到商品级，同时为 L2/L3 留出完整的数据和架构接口。**

任何 L2/L3 工作都不能拖慢 L1 首发主线。

---

## 4. 低功耗主动感知总体架构

### 4.1 异步独立采集

GNSS、LTE、IMU、Camera，以及未来 Audio 根据各自物理特性、功耗和采样策略独立运行。

设备端不要求严格多源同步，不以“同一时刻形成四源窗口”为前提。设备端重点保存每条 Observation 的事件时间和采集上下文，VPS 负责后续：

- 时间轴重建；
- 对齐；
- Replay；
- 融合；
- 训练；
- 评测。

采集失败本身是有效观测，必须区分：

- 未尝试采集；
- 尝试但 `no_fix / timeout / error`；
- 成功采集。

---

### 4.2 传感器的功耗与职责分层

#### IMU：最低成本 Always-on / Interrupt Sensor

职责：

- 判断设备是否静止；
- 检测开始移动；
- 区分步行、跑动、乘车；
- 检测剧烈运动或疑似跌落；
- 作为其他传感器升级采样的触发源。

可采用低功耗常驻模式，检测到事件后短时间提高采样率。

#### LTE：低边际成本空间变化证据

设备本身需要 LTE 联网，因此 Cell、TAC、PCI、RSRP、RSRQ 等可作为低边际成本位置证据。

典型用途：

- Cell 长时间不变 + IMU 静止 → 位置显著变化概率低；
- IMU 持续移动 + Cell 连续变化 → 设备发生明显空间位移。

LTE 适合作为低成本空间变化检测器。

#### GNSS：高成本绝对位置校准器

GNSS 不应持续开启，而应根据以下因素按需工作：

- movement；
- location uncertainty；
- 距离上次可信 fix 的时间；
- 历史 GNSS 成功率；
- 当前电量；
- 事件等级。

连续 `no_fix` 时应退避，避免无效高功耗重试。

#### Camera：高成本主动证据 / 消歧传感器

Camera 默认关闭，可独立断电。

主要触发条件：

1. **风险触发**：疑似跌倒、异常静止、SOS、异常移动等；
2. **不确定性触发**：GNSS no_fix、LTE 位置过粗、持续移动且 location uncertainty 快速上升。

Camera 的任务不是周期性录像，而是在值得支付高感知成本时获取高信息价值证据。

优先策略：

`单帧 → 少量帧 → 极少情况下短视频`

Camera 后续还可服务：

- visual place recognition；
- 室内/室外判断；
- 地铁站、商场、街道、建筑等场景识别；
- OCR 招牌/环境文字；
- 风险事件取证。

---

## 5. Event State Machine 与 Sensor Policy

长期应形成事件分级状态机，例如：

- **E0 Stable**：稳定状态；
- **E1 Changed**：检测到变化；
- **E2 Uncertain**：位置/状态不确定性增加；
- **E3 Suspicious**：出现明显异常；
- **E4 Critical**：高风险 / 求助事件。

事件必须支持：

- 升级；
- 降级；
- hysteresis（迟滞）；
- cooldown（冷却）。

避免一次异常后设备长期处于 GNSS、Camera、网络高功耗状态。

现阶段模型尚未成熟时，应先运行 **Rule Policy v0**，用规则完成：

`State → Observation → Trigger → Action → Outcome`

这套数据随后用于训练真正的 Energy-Aware Sensor Policy。

当前建议演进路径：

`规则策略 → 真实 Field Data → VPS 离线模型 → Shadow Mode → 模型逐步接管 Sensor Policy`

---

## 6. 第一代首发三条核心闭环

### 6.1 Reliable Location

技术核心：

`GNSS + LTE + IMU + history → location_belief`

目标：用户随时尽可能知道 TA 在哪里。

### 6.2 Ego Call

技术核心：

`Ego Link ↔ LTE Data ↔ Ego RTC Service ↔ Guardian App`

提供设备与绑定家属 App 的双向全双工网络语音。

### 6.3 SOS

典型流程：

`长按/触发 SOS → 定位策略升级 → 上传最新 location_belief → 发起 Ego Call → 家属接收事件和位置`

这三项完成即可形成具备上市价值的第一代产品。

---

## 7. 第一代通话方案决策

### 7.1 V1 主线：LTE 数据 + Ego Call

第一代软件主线采用网络语音，而不是把 Native VoLTE 普通电话作为上市前置条件。

Ego Call 目标：

- 设备一键呼叫监护人；
- Guardian App 呼叫设备；
- 双向全双工语音；
- 弱网重连；
- 多监护人；
- 呼叫超时转第二联系人；
- 通话同时传递位置、电量、定位可信度等上下文；
- 与 SOS 联动。

该方案使“通话”直接成为安全系统的一部分，而不是单纯复制手机通话。

---

### 7.2 第一代不自建公网 PSTN/SIP 电话网关

第一代不自行实现：

`Internet → SIP/PSTN Gateway → 公共电话网络`

避免引入号码资源、电信业务和额外运营复杂度。

未来若需要普通电话互通，优先与持牌通信服务商合作。

---

### 7.3 硬件保留 Native VoLTE 能力

硬件仍优先选择支持 VoLTE 的 Cat.1/LTE 模组，并完整预留：

- 麦克风；
- 扬声器；
- 功放 / Codec / 音频链路；
- VoLTE 相关接口和能力。

目的：V1.x / V2 可以增加普通手机号 Native VoLTE Call，而无需重新设计核心 PCB。

长期通信策略可演进为：

`Ego Call 主通道 + Native VoLTE Fallback`

后续还可加入 SMS、NFC、LoRa 等多通道安全冗余。

---

## 8. 上市合规原则

只使用 LTE 数据网络并不意味着整机可以跳过蜂窝通信终端相关合规。

进入自定义 PCB、射频和结构设计前，应尽早开展一次正式的 **pre-compliance / 产品归类评估**，至少确认：

- SRRC / 无线电发射设备型号核准；
- 电信设备进网许可 / 产品类别；
- CCC 适用性；
- 人体电磁暴露 / SAR 等要求；
- LTE / GNSS / Wi-Fi / BLE 等无线组合对认证的影响；
- 儿童产品/儿童手表相关强制标准的适用性；
- 电池、充电、防水和整机安全要求。

认证规划应与 PCB、天线和外壳结构设计同步推进，避免后期返工。

---

## 9. 统一产品能力 Gate

后续 AI Control Console、Codex、任务树和项目文档统一采用以下 Gate：

| Gate | 能力 | 产品要求 |
|---|---|---|
| **Gate L1 Location** | Reliable Location | 首发必须完成 |
| **Gate L2 Intelligence** | AI-Enhanced Location | 首发争取完成，可持续 OTA 增强 |
| **Gate L3 Awareness** | Context & Event Understanding | 上市后长期演进 |

任务优先级规则：

- 属于 L1：当前最高优先级；
- 属于 L2：并行研究，不阻塞 L1；
- 属于 L3：保证数据和架构兼容，暂不进入首发关键路径。

---

## 10. 数据策略与长期数据飞轮

功能可以分阶段实现，数据结构必须从第一代开始支持未来模型训练。

每次定位和传感行为建议记录：

- GNSS observation；
- LTE observation；
- IMU observation / mobility state；
- Camera observation（如有）；
- battery；
- device state；
- record_time / device_time；
- attempted / status / error；
- trigger_reason；
- location_belief_before；
- action_taken；
- location_belief_after；
- outcome；
- quality / confidence / uncertainty。

长期数据飞轮：

`产品使用 → 真实 Observation → Ground Truth / Weak Labels → 模型训练 → AI 增强定位 → 更优 Sensor Policy → 更好产品 → 更多真实数据`

所有真实用户数据训练必须建立在明确授权、匿名化、隐私保护和数据治理基础上。

---

## 11. 当前阶段的统一结论

Ego Link 当前不需要等完整 AI 能力成熟后再进入市场。

第一代优先做成：

> **可靠定位 + Ego Call + SOS**

其中：

- **可靠定位**是用户接受产品的基本盘；
- **Ego Call**解决设备与家属之间的直接联系；
- **SOS**把定位和通话组成安全闭环；
- **AI 增强定位**是首发差异化加分项；
- **状态理解与主动安全**依靠上市后的真实数据持续训练和演进。

当前 A 线核心任务应明确为：

> **先把 L1 Location Engine 做到可以作为商品交付，同时完成 Ego Call/SOS 首发闭环，并从第一天开始积累可用于 L2/L3 的高质量多源数据。**

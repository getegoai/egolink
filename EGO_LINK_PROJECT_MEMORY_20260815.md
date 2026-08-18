# Ego Link 项目记忆与产品开发基线

> **文件定位：Ego Link 当前 Single Source of Truth（产品与工程基线）**  
> **版本：v1.0**  
> **日期：2026-08-15**  
> **适用对象：ChatGPT / Codex / 研发人员 / 产品与结构设计人员**  
> **项目：Project Ego / Ego Link**

---

## 0. 使用规则

1. 本文件记录 **Ego Link 截至 2026-08-15 的最新产品定义、工程状态、关键原则与下一阶段路线**。
2. 项目原有 `EGO_MASTER_CONTEXT.md` 仍作为整个 Project Ego 的总体背景文件；但其中对 Ego Link 的早期定义已经过时。
3. **当旧版 `EGO_MASTER_CONTEXT.md` 中关于 Ego Link 的描述与本文件冲突时，Ego Link 相关决策以本文件为准。**
4. 后续 AI、Codex、工程人员在进行架构设计、代码实现、PCB、结构、功耗、测试或产品规划时，应优先检查是否符合本文件的约束。
5. 未经新一轮产品决策，不应擅自把 Ego Link 退化为传统 GPS 定位器、儿童电话手表、手机配件或云端大模型终端。

---

# 1. 产品定义

## 1.1 当前定义

**Ego Link 是一个 AI 原生随身安全终端。**

主要面向：

- 儿童；
- 老人；
- 同时兼顾成年人；
- 可扩展到宠物佩戴场景。

它的核心任务是：

> **持续感知 → 状态理解 → 多源定位 → 异常判断 → 主动联系 → 协助处置。**

Ego Link 的价值不依赖复杂屏幕菜单，也不依赖单一 GNSS 坐标。它应在真实环境中面对卫星信号弱、网络变化、用户无法操作设备等情况，仍尽可能形成对“用户在哪里、处于什么状态、是否存在风险、下一步该做什么”的可解释判断。

---

## 1.2 产品核心差异化

Ego Link 不以“多几个功能”为主要竞争逻辑，而以以下系统能力建立差异：

1. **无 GNSS 或弱 GNSS 条件下仍形成位置判断；**
2. **多源证据融合形成 Location Belief，而不是简单返回 Unknown；**
3. **AI 主动安全助手，而不是完全依赖用户主动操作；**
4. **Voice-first / Zero-UI / Proactive AI；**
5. **Core Capsule + Replaceable Shell 的产品架构；**
6. **长续航、可依赖、可长期佩戴；**
7. **作为 Ego Personal AI Network 的现实世界节点。**

---

# 2. 一级产品原则

以下原则属于产品级约束，后续设计不得轻易牺牲。

## 2.1 安全与可靠性优先

设备首先是一台长期随身的安全设备，因此：

- 通信链路必须可解释；
- 弱网、断网、重连、重启必须有确定行为；
- 关键数据不得因短时断网或设备重启轻易丢失；
- 定位失败必须输出原因和可用证据；
- 关键状态应形成日志和验证证据。

---

## 2.2 4G 是核心能力

Ego Link 不是 BLE Tag，也不是依赖手机的附件。

P0/P1 必须保留独立蜂窝通信能力，当前优先：

- 国内成熟 Cat.1 / Cat.1 bis；
- GNSS 能力；
- 数据通信；
- 电话能力。

打电话是主要功能之一。

Wi-Fi / BLE 用于：

- 环境感知；
- 热点共享；
- 近场发现；
- 辅助定位；
- 与周边 Ego 节点协同。

LoRa 可作为后续：

- 应急低速链路；
- 私有共享网络；
- 特定场景补充通信。

被动 NFC 可作为应急兜底能力。

---

## 2.3 续航与能源是一级系统约束

**续航优先级与安全可靠性、4G 通信同级。**

Ego Link 是长期随身设备，产品价值建立在“关键时刻设备仍有电”的前提上。续航不能被视为产品完成后的优化项，而必须从 SoC、模组、电池、PCB、天线、结构、软件架构阶段共同反推。

### 方向性目标

P1 阶段以：

> **典型使用场景下待机/综合续航约 7 天**

作为方向性目标。

该数值不是当前已经验证的承诺指标，最终必须通过真实样机功耗测试冻结。

### 设计取舍

为保障续航：

- 可以合理增加电池容量；
- 可以接受核心舱尺寸适度增加；
- 不为了极致轻薄牺牲安全设备的基本续航；
- 屏幕、持续视觉、高频 GNSS、高频蜂窝通信和持续 AI 推理均必须接受能源预算约束；
- 任何新增高功耗功能都要说明“用户价值 / 日均能耗 / 是否值得”。

---

# 3. 能源与续航路线

Ego Link 的能源创新采用：

> **先工程保障，再渐进创新。**

不追求一次性用高风险新技术解决全部能源问题。

## 3.1 第一阶段：工程手段实现 7 天级目标

优先使用成熟、可量产的技术：

- 低功耗主控和外围器件；
- 深睡眠；
- 分级唤醒；
- 多电源域；
- 4G 连接与上传批处理；
- GNSS 自适应扫描；
- 摄像头按需唤醒；
- 音频事件触发；
- IMU 低功耗常开；
- 非关键传感器断电；
- 数据本地聚合后批量上传；
- 合理增加电池容量；
- 优化待机漏电和电源转换损耗。

核心原则：

> **设备绝大多数时间应该处于低功耗状态，高功耗能力只在需要时短时间启动。**

---

## 3.2 第二阶段：智能能源管理

在硬件基础稳定后，增加软件和 AI 驱动的能源调度：

- 动态 GNSS 采样策略；
- 根据运动状态调整定位频率；
- 根据时间、地点、风险等级调整通信频率；
- 网络质量感知；
- 事件驱动视觉；
- DVFS；
- 异构计算调度；
- 高低功耗 SoC/协处理器分工；
- 用户行为与日程感知；
- 电池余量预测；
- 低电量安全模式。

例如：

```text
静止 + 熟悉地点 + 高位置置信度
        ↓
降低 GNSS / LTE / Camera 活动频率

持续移动 + 位置置信度下降
        ↓
提高定位观测频率

疑似风险事件
        ↓
临时解除节能限制
        ↓
优先安全与通信
```

---

## 3.3 第三阶段：混合供电与能量采集

在不影响可靠性的前提下逐步验证：

- 太阳能辅助；
- 运动 / 振动能量采集；
- 热电能量采集；
- 可更换辅助电池；
- 外挂电池配件；
- 腕带 / 挂件内辅助电池；
- 充电底座；
- 特定外壳集成附加能源；
- 其他适合可穿戴设备的混合供电方式。

判断标准：

1. 实际每天能够增加多少 mWh；
2. 是否显著增加体积；
3. 是否影响防水；
4. 是否降低可靠性；
5. 是否增加用户维护成本；
6. BOM 增量；
7. 实际续航收益；
8. 是否可以形成产品差异化。

**不为“新能源概念”牺牲可量产性。**

---

# 4. Energy Budget / Power State Model

从 P1 开始必须建立正式功耗模型。

至少覆盖：

```text
P_shipping
P_deep_sleep
P_sleep
P_idle
P_sensor_idle
P_IMU
P_audio_listen
P_audio_active
P_LTE_registered_idle
P_LTE_rx
P_LTE_tx
P_LTE_reconnect
P_GNSS_search
P_GNSS_tracking
P_WiFi_scan
P_BLE_scan
P_camera_boot
P_camera_capture
P_AI_low
P_AI_high
P_call
P_vibration
P_speaker
```

必须形成三个预算：

### A. Typical Day

典型一天：

```text
各状态功耗 × 每天驻留时间
        ↓
Typical Daily Energy Budget
```

### B. Stress Day

例如：

- 弱 LTE；
- 频繁基站切换；
- 长时间 GNSS no-fix；
- 用户频繁移动；
- 多次语音交互；
- 多次定位请求。

### C. Emergency Day

安全事件发生时允许功耗显著提高，因为此时：

> **安全优先于续航。**

但仍要测量设备能在应急高功耗状态维持多久。

最终通过：

```text
目标续航
   ↓
日均能耗预算
   ↓
有效电池容量
   ↓
电池体积
   ↓
核心舱尺寸
   ↓
PCB / 天线 / 声学 / 结构
```

反向设计整机。

---

# 5. 定位系统：从 GNSS 到 Location Belief

## 5.1 真实问题

实测已经证明：

- 设备在包内可以保持 4G；
- GNSS 可能长时间 no-fix。

因此不能假设随身设备始终拥有可靠卫星坐标。

天线仍必须认真设计，但产品架构不能建立在 GNSS 永远可用的假设上。

---

## 5.2 多源位置认知

目标架构：

```text
GNSS
LTE Cell
Wi-Fi Environment
BLE Environment
IMU / Motion State
Historical Trajectory
Time Context
Occasional Vision
User Interaction
        ↓
Location Observation
        ↓
Fusion / Memory
        ↓
Location Belief
        ↓
Confidence + Evidence + Reason
```

最终输出应能够表达：

- 当前最可能的位置；
- 坐标或区域；
- 位置来源；
- 置信度；
- 可用证据；
- 不确定性的原因；
- 最近一次高可信位置；
- 用户是否移动；
- 是否需要触发新的观测手段。

---

## 5.3 “无 GNSS 仍可定位”作为核心壁垒

这是 Ego Link 当前最值得投入算法和数据积累的方向之一。

长期应逐步形成：

- Location Observation Dataset；
- 不同场景的 source availability；
- GNSS no-fix 数据；
- LTE Cell 轨迹；
- Wi-Fi / BLE 指纹；
- IMU 运动特征；
- 场景视觉特征；
- 模型置信度校准；
- 位置记忆与时间窗口。

目标不是在没有证据时伪造精确坐标，而是：

> **最大化可解释的位置认知能力，并明确表达不确定性。**

---

# 6. 当前软件工程状态

## 6.1 Walking Skeleton 已成立

已形成主链路：

```text
Web / VPS Command
        ↓
Device LTE Poll / Receive
        ↓
request_location
        ↓
location_report
        ↓
location_observation
        ↓
ACK
        ↓
Web / API / Export
```

已经验证或推进：

- USB-Free runtime；
- SIM7670G LTE；
- VPS Message Hub；
- Web → Device command；
- Device → Server 回传；
- reconnect；
- store-forward；
- reboot-aware；
- GNSS no-fix；
- LTE Cell；
- source-state；
- location_report；
- location_observation；
- location_belief；
- location_memory；
- dataset window；
- 原始 ACK 与证据链。

---

## 6.2 当前阶段判断

项目已完成“主链路能否跑通”的核心验证，正在进入：

> **可解释可靠性 → 长时间稳定性 → 真实持久缓存 → 产品级重连 → 多源融合 → P1 产品样机。**

当前主要缺口：

1. 多源定位融合；
2. 真正掉电安全的 Persistent Store；
3. 8h / 24h / 72h 长时间稳定性门；
4. 产品级 LTE 状态机；
5. 正式 Energy Budget；
6. 音频链路产品化；
7. Camera 方案冻结；
8. 自定义 PCB；
9. 天线与结构协同；
10. 防水 Core Capsule。

---

# 7. 产品级重连与持久化

必须验证：

```text
断网
↓
产生数据
↓
持久化
↓
设备重启
↓
恢复本地队列
↓
LTE 重新注册
↓
数据链路恢复
↓
有序补传
↓
Server ACK
↓
安全清理
```

LTE 状态机至少要处理：

```text
Registered
Weak Signal
No Service
Re-registering
PDP Context Recovery
IP Restored
Application Session Restored
Store-forward Drain
```

不能依赖偶然成功。

---

# 8. 交互架构

Ego Link 的 P0/P1 交互方向：

> **Voice-first + Button + Proactive AI**

### 输入

- 麦克风；
- 按键；
- IMU；
- GNSS；
- LTE Cell；
- Wi-Fi / BLE；
- 摄像头；
- 设备状态；
- 用户行为上下文。

### 输出

- 扬声器；
- 振动；
- 电话；
- 网络消息；
- Ego Base / Phone / PC 通知。

系统应尽量减少：

```text
点亮屏幕 → 找 App → 进入菜单 → 找功能 → 点击
```

而采用：

```text
事件 / 语音 / 按键
        ↓
AI 理解
        ↓
执行或询问
        ↓
反馈
```

---

# 9. 屏幕策略

屏幕在消费产品外观和信息展示上可能有价值，但：

**P0 不以屏幕为架构中心。**

原则：

- 可为后续型号保留显示能力；
- 不让 UI 菜单成为主要交互逻辑；
- 不让屏幕持续亮屏侵蚀 7 天级续航目标；
- 不因为加入屏幕而把产品重新做成传统儿童电话手表。

---

# 10. 摄像头策略

摄像头是：

> **低占空比、偶发环境感知传感器。**

不是持续录像设备。

典型触发：

```text
GNSS unavailable
+
Location confidence low
+
Context requires more evidence
        ↓
Wake Camera
        ↓
Capture 1–3 frames
        ↓
Scene / Landmark / OCR / Risk analysis
        ↓
Update belief
        ↓
Camera power off
```

选型优先级：

1. 生命周期；
2. 供货稳定；
3. 模组成熟度；
4. 待机与启动功耗；
5. 驱动成熟度；
6. 尺寸；
7. BOM；
8. 画质。

当前状态：

- OV2640：放弃；
- OV3660：生命周期继续谨慎评估；
- GC2145 等长期供货方案：继续评估。

像素不是第一指标，目标是获得有用视觉语义证据。

---

# 11. 硬件架构原则

开发板阶段用于：

- 通信验证；
- 驱动验证；
- 算法验证；
- 模组选型；
- 功耗测量；
- 可靠性实验。

最终产品逐步转向自定义 PCB。

ESP32-S3 可继续承担：

- IMU；
- 麦克风；
- BLE / Wi-Fi；
- 外设管理；
- 简单 Camera；
- TinyML；
- 低功耗状态机。

但不默认锁死为最终视觉 AI 主处理器。

继续评估：

- Ambiq Apollo4；
- STM32U5；
- Alif；
- ESP32-P4；
- RK 系列；
- 其他低功耗 AI MCU / MPU。

长期可采用：

> **超低功耗 Always-on MCU + 按需唤醒通信 / 视觉 / AI 协处理器。**

SoC 决策必须由：

```text
续航 + 通信 + AI能力 + 成本 + 尺寸 + 供应链 + 开发成熟度
```

共同决定。

---

# 12. Core Capsule + Replaceable Shell

产品结构采用：

```text
Replaceable Shell
        ↓
Waterproof Core Capsule
        ↓
PCB + Battery + Antenna + Audio + Sensors + Camera + Type-C
```

## 12.1 核心舱负责

- 主 PCB；
- 电池；
- LTE；
- GNSS；
- Wi-Fi / BLE；
- 麦克风；
- 扬声器；
- IMU；
- Camera；
- Type-C；
- SIM；
- 振动；
- NFC；
- 防水；
- 天线；
- 声学；
- 散热；
- EMC；
- 电源与充电安全。

## 12.2 外壳负责

- 儿童款；
- 老人款；
- 成人款；
- 宠物款；
- 胸夹；
- 吊坠；
- 包挂；
- 腕带；
- 个性化配饰。

核心舱自身完成可靠防水，外壳不承担关键防水职责。

---

# 13. Type-C 原则

标准 USB Type-C 是产品体验原则。

避免：

- 专用磁吸线；
- 专有 pogo pin 充电线；
- 丢失专用线后无法使用。

可以继续探索：

- Type-C 主充电；
- 充电底座作为便利性补充；
- 外壳或配件辅助充电。

---

# 14. P1 产品开发三条并行主线

## A. AI 能力

- 多源定位；
- Location Belief；
- 状态理解；
- 异常检测；
- 主动安全；
- 位置与状态证据链；
- 低功耗 AI 调度。

## B. 产品工程

- **续航与能源；**
- 4G；
- GNSS；
- 音频；
- Camera；
- PCB；
- 天线；
- 电池；
- 电源；
- 防水；
- 长时稳定性；
- EMC / ESD；
- 可靠性。

## C. 产品形态

- Core Capsule；
- Replaceable Shell；
- 人体工程学；
- 儿童 / 老人 / 成人 / 宠物佩戴；
- 配饰化；
- 工业设计；
- 3D 打印快速迭代；
- 结构反推 PCB。

三条主线在：

> **P1 Product Prototype**

重新汇合。

---

# 15. P1 设计顺序

后续产品设计推荐顺序：

```text
Product Definition
↓
Target Scenarios
↓
Reliability Requirements
↓
7-day Energy Target
↓
Energy Budget
↓
Battery Capacity / Volume
↓
Core Capsule Envelope
↓
LTE / GNSS Antenna Keep-out
↓
Audio Chamber
↓
Camera FOV
↓
PCB Outline
↓
Mechanical Stack
↓
Industrial Design
↓
Prototype
↓
Measured Power / RF / Reliability
↓
Revision
```

特别注意：

> **不能先把外壳画得很小，再逼电池、天线和 PCB 塞进去。**

Ego Link 的体积应该由“可佩戴性”和“7 天级可靠续航”共同决定。

---

# 16. 下一阶段必须建立的验证门

## 16.1 REL-GATE：长时运行

- 8 小时；
- 24 小时；
- 72 小时。

观察：

- modem；
- 内存；
- reconnect；
- GNSS；
- queue；
- watchdog；
- 温升；
- 电池；
- 功耗漂移。

## 16.2 OFFLINE-GATE：断网与补传

验证：

- 断网产生数据；
- 掉电；
- 重启；
- 恢复；
- 补传；
- ACK；
- 去重；
- 清理。

## 16.3 POWER-GATE：功耗

必须获取真实数据：

- 深睡电流；
- LTE 注册待机；
- LTE TX 峰值；
- GNSS 搜星；
- GNSS tracking；
- 麦克风监听；
- Camera capture；
- 语音通话；
- AI 推理；
- 一天综合能耗。

## 16.4 LOCATION-GATE：多源位置认知

至少覆盖：

- 户外 GNSS fix；
- 包内 GNSS no-fix；
- 室内；
- 移动车辆；
- 静止；
- 弱 LTE；
- Wi-Fi 可见 / 不可见；
- 历史位置可用 / 不可用。

---

# 17. 明确避免的路线

后续开发应避免以下偏移：

1. 把 Ego Link 做成传统智能手表 UI；
2. 依赖手机才能完成核心安全能力；
3. 将单一 GNSS 当作唯一位置真值；
4. 长期开启 Camera；
5. 长期开启高算力 AI；
6. 为追求极致尺寸牺牲电池；
7. 为加入“先进功能”破坏 7 天级续航目标；
8. 先冻结漂亮外观，再被动压缩电池和天线；
9. 把开发板拼接形态直接当成产品架构；
10. 用公有云依赖替代本地 / 端侧 / 私有协同核心能力；
11. 在没有实测功耗收益前堆叠能量采集模块；
12. 在没有证据时输出虚假精确位置。

---

# 18. 与 Project Ego 的关系

Ego Link 长期是 Project Ego 的现实世界随身节点。

目标网络：

```text
Ego Link
   ↕
Ego Base
   ↕
Phone / PC
   ↕
Private AI / Local Compute
```

继承 Ego 的基本原则：

- 本地优先；
- 隐私优先；
- 可离线；
- 用户数据主权；
- 私有算力可增强；
- 公有云不是核心依赖；
- AI 应服务用户，而不是要求用户围绕 AI 调整行为。

---

# 19. 当前阶段一句话判断

> **Ego Link 已完成“通信主链路是否可行”的核心技术验证，当前正在进入以 7 天级续航、多源位置认知、产品级可靠性和 Core Capsule 自定义硬件为核心的第一次真正产品化阶段。**

---

# 20. 给 Codex / 后续 AI 的执行要求

处理 Ego Link 任务前，先确认：

1. 任务属于 AI、通信、可靠性、能源、PCB、结构还是产品形态；
2. 是否会影响 7 天级续航目标；
3. 是否会影响 4G / GNSS / 天线空间；
4. 是否会影响 Core Capsule 防水；
5. 是否会增加长期高功耗状态；
6. 是否增加新的单点故障；
7. 是否保留可解释证据；
8. 是否能在开发板上先验证，再进入自定义 PCB；
9. 是否与 Location Belief / Store-forward / Energy Budget 等已有架构兼容；
10. 是否真正增加用户安全价值。

对于重大硬件或架构变更，必须同步更新：

- 当前状态文档；
- 架构决策记录；
- Energy Budget；
- 测试门；
- BOM / PCB / 结构约束；
- 项目记忆。

---

## Change Log

### 2026-08-15 / v1.0

- 将 Ego Link 从旧定义“Ego 的 4G 远程语音接口”升级为独立 AI 原生随身安全终端；
- 固化多源位置认知 / Location Belief 路线；
- 固化 4G 和电话核心能力；
- 固化 Voice-first / Zero-UI / Proactive AI；
- 固化 Camera 为偶发低占空比感知；
- 固化 Core Capsule + Replaceable Shell；
- 固化 Type-C；
- 将 **续航与能源提升为一级系统约束**；
- 引入 **典型场景 7 天级续航方向性目标**；
- 明确可以通过更大电池、核心舱尺寸调整保障续航；
- 建立“工程保障 → 智能能源管理 → 混合供电/能量采集”的渐进式能源创新路线；
- 要求建立正式 Energy Budget / Power State Model；
- 明确下一阶段 P1 三条并行主线与验证门。

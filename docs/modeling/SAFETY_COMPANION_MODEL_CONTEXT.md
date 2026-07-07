# Ego Link Safety Companion 模型子系统上下文

> 文档状态：v0.2  
> 适用仓库：EGOLINK  
> 适用阶段：Safety Companion M0—M6  
> 目标读者：Codex、模型开发者、固件开发者、PC Simulator / Ego Base 开发者  
> 本文是模型子系统的长期上下文。具体字段定义以 `shared/contracts/**` 为准，具体阶段任务以 `docs/modeling/INTEGRATION_TASKS.md` 和后续里程碑文档为准。
>
> 2026-06-24 更新：当前 P0 模型与安全闭环运行在 **双开发板 + PC Development Bridge** 形态中。`wearable_node` 负责 IMU、音频和用户交互；`connectivity_node` 负责 4G、GNSS、摄像头和通信能力；PC Bridge 当前运行规则版 ContextRouter、Safety Kernel、记录和回放。PC 不是正式 Ego Base，ContextRouter 会在 P1 逐步迁回可穿戴主节点。

---

## 1. 项目定位

Ego Link 是 EGO 的随身安全感知、通信与交互节点。Safety Companion 的目标不是在 ESP32-S3 上运行一个通用大模型，而是建立一个低功耗、事件驱动、隐私优先的安全闭环：

```text
持续但低成本地感知
→ 发现值得关注的事件
→ 按需采集更多证据
→ 端侧快速判断并执行安全规则
→ 将结构化事件或必要证据发送到 PC Simulator / Ego Base
→ Base 结合长期记忆和较强模型进一步推理
→ 向 Ego Link 下发询问、提醒、补采或升级动作
→ 记录用户反馈，形成后续训练数据
```

Ego Link 是“反射系统和感觉器官”，Ego Base 是“长期记忆和复杂认知系统”。云端只能是用户明确授权后的可选增强层，不能成为基本安全闭环的必需依赖。

Safety Companion 不是医疗诊断系统，不承诺识别所有危险，也不允许由概率模型单独决定不可逆或高风险动作。

当前 P0 的实现形态见 `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md`。模型路线必须服务于真实数据闭环，不得把 PC Bridge、Mock 数据或规则模拟结果描述为已经完成产品级安全识别。

---

## 2. 核心设计原则

### 2.1 端侧专用微模型，不追求端侧通用智能

ESP32-S3 端不部署视觉语言模型或通用对话模型。模型能力拆成多个边界清晰、可量化、可独立替换的微模型：

- `MotionNet`：从 IMU 时间序列识别运动、撞击、跌倒候选和异常静止；
- `AudioGate`：从短音频判断是否有人声、呼救、撞击声或异常声音；
- `VisionGate`：对按需拍摄的单帧图像做质量与上传价值筛选；
- `ContextRouter`：综合各微模型输出、GNSS、4G、电量、历史和用户操作，决定下一步行动；
- `Safety Kernel`：以确定性规则保护 SOS、隐私、取消、紧急联系人、电源和不可逆操作。

### 2.2 先门控，再采集，再理解

摄像头、GNSS 冷启动、4G 上传、长音频采集都属于高功耗或高隐私成本动作。系统不持续采集全部数据，而是分级处理：

```text
低功耗触发
→ 结构化初判
→ 证据不足时主动补采
→ 只上传必要摘要或证据
```

这称为“主动感知”。系统的智能不仅体现在“判断结果”，也体现在“下一条最值得采集的信息是什么”。

### 2.3 模型输出建议，安全规则决定边界

标准执行链路：

```text
硬安全规则
→ 微模型推理
→ ContextRouter 行动建议
→ 二次安全策略检查
→ 可审计动作
```

物理 SOS、用户取消、隐私模式、紧急号码、电池与温度保护、不可逆配置、固件升级等不得只由模型决定。

### 2.4 先规则基线，再学习模型

没有真实数据前不训练一个表面可用但不可验证的神经网络。M0 使用透明规则版 `ContextRouter`，先固定输入、输出、风险类型、动作类型和协议语义。后续模型必须在同一契约下替换或增强规则实现。

### 2.5 原始证据最小化

默认长期保存结构化特征、模型结果和用户确认；原始声音与图像仅在事件触发、用户主动请求或 Base 明确请求时短时采集，并遵循授权、加密、保留期和删除机制。

---

## 3. 总体分层架构

```text
┌──────────────────────────────────────────────────────┐
│                    Safety Kernel                     │
│ SOS / 取消 / 隐私 / 紧急联系人 / 电源安全 / 权限边界 │
└──────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────┐
│                低功耗传感与事件触发                  │
│ IMU / 麦克风 / GNSS / 4G / 电量 / 按键 / 摄像头     │
└──────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────┐
│                 专用端侧感知模型                     │
│       MotionNet / AudioGate / VisionGate             │
└──────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────┐
│                   ContextRouter                      │
│ 多源融合 / 风险评分 / 证据请求 / 行动路由            │
└──────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────┐
│                   Ego Link 动作                      │
│ 忽略 / 本地提醒 / 询问 / 补采 / 发摘要 / 发证据 /升级│
└──────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────┐
│              PC Simulator / Ego Base                 │
│ ASR / 视觉理解 / 长期记忆 / 个性化推理 / 联系人联动  │
└──────────────────────────────────────────────────────┘
                         ↓
             命令、策略、反馈标签回到 Ego Link
```

---

## 4. MotionNet

### 4.1 作用

MotionNet 回答“设备或佩戴者刚才发生了什么运动事件”，不直接回答“用户是否受伤”。

### 4.2 输入

首版建议：

- 三轴加速度；
- 三轴角速度；
- 采样率初始值 50 Hz；
- 事件窗初始值：事件前 3 秒、事件后 7 秒；
- 可选派生特征：合加速度、角速度模长、姿态变化、静止时长、佩戴状态。

以上只是工程初始值，必须通过真实开发板与功耗测量修订。

### 4.3 输出

典型输出：

```json
{
  "activity_label": "fall_candidate",
  "activity_confidence": 0.88,
  "impact_score": 0.92,
  "fall_score": 0.81,
  "stationary_seconds": 16.5,
  "device_worn": true
}
```

### 4.4 任务范围

需要区分：

- 正常步行、跑步、上下楼；
- 坐下、躺下、快速起身；
- 骑行、乘车；
- 放下、拿起、背包晃动；
- 设备跌落或被扔到软物体；
- 强烈撞击；
- 跌倒候选；
- 撞击后静止；
- 未佩戴或放置状态。

困难重点是控制误报，而不是只追求跌倒召回率。

### 4.5 候选模型

首版优先比较：

- 小型 1D-CNN；
- 轻量 TCN；
- 必要时 CNN + TinyGRU。

选择标准：事件级准确率、误报率、召回率、RAM、Flash、延迟、单次推理能耗和量化后精度。

---

## 5. AudioGate

### 5.1 作用

AudioGate 不是完整 ASR，也不负责自然语言对话。它回答“当前声音是否值得进一步处理或上传”。

### 5.2 输入

首版建议：

- 16 kHz；
- 16-bit；
- 单声道；
- 环形缓冲初始值：事件前 2 秒、事件后 5 秒。

### 5.3 输出

```json
{
  "speech_score": 0.62,
  "distress_score": 0.86,
  "impact_sound_score": 0.73,
  "unknown_loud_sound_score": 0.41,
  "quality_score": 0.91
}
```

### 5.4 两级结构

```text
一级：低成本门控
VAD / 音量变化 / 是否有人声

二级：声音事件分类
普通说话 / 呼救 / 尖叫 / 撞击声 / 环境噪声 / 未知异常
```

完整语音识别和语义理解在 Ego Base 侧进行。

---

## 6. VisionGate

### 6.1 作用

摄像头不常开。VisionGate 只在事件触发、用户主动请求或 Base 请求补充证据时工作。

### 6.2 端侧任务

- 图片是否过暗；
- 是否模糊；
- 镜头是否被遮挡；
- 是否可能有人；
- 是否需要重新拍摄；
- 是否值得上传。

### 6.3 不属于端侧的任务

- 人物身份识别；
- 完整环境语义理解；
- 事故责任判断；
- 视觉问答；
- 通用多模态推理。

这些任务由 Ego Base 承担。隐私模式下必须禁止原始图像采集或上传。

---

## 7. ContextRouter

### 7.1 定位

ContextRouter 是 Ego Link 安全陪伴链路的行动路由核心。它不直接读取完整波形或图像，而读取结构化特征并决定行动。

当前 P0-A / P0-B 中，规则版 ContextRouter 运行在 PC Development Bridge 上，用于联通 `wearable_node`、`connectivity_node`、记录和回放。P1 起再逐步迁到可穿戴主节点。文档或测试不得把 PC Bridge 上的规则基线误写成最终产品依赖。

### 7.2 输入类别

1. MotionNet：活动、撞击、跌倒候选、静止、佩戴状态；
2. AudioGate：人声、呼救、撞击声、异常声音、质量；
3. VisionGate：图像质量、人物粗检测、上传价值；
4. GNSS：定位状态、速度、方向、安全区、停留、轨迹偏离；
5. 网络：4G 注册、信号等级、上传能力、离线时长、Base 在线状态；
6. 设备：电量、充电、温度、麦克风/摄像头可用性、隐私模式；
7. 历史：近期风险次数、上次用户响应、最近一次联系；
8. 直接操作：SOS、取消、确认安全、请求帮助。

### 7.3 输出动作

```text
ignore
local_prompt
ask_user
capture_more
send_summary
send_evidence
urgent_escalation
```

### 7.4 证据请求

ContextRouter 可以请求：

- `user_confirmation`；
- `gnss_refresh`；
- `imu_10s`；
- `audio_5s`；
- `image_single`；
- `network_probe`。

请求在执行前仍必须经过隐私、功耗和安全策略检查。

### 7.5 实现路线

- M0：透明规则基线；
- M2 初期：规则 + 学习型 MotionNet；
- 数据积累后：比较决策树、梯度提升树、小型 MLP；
- 只有时序依赖确实带来显著收益时，再考虑轻量时序模型。

ContextRouter 不必为了“看起来先进”而强行使用深度网络。结构化特征任务应优先选择可解释、易量化、易验证的模型。

---

## 8. Safety Kernel

Safety Kernel 独立于模型，至少覆盖：

- 物理 SOS 始终可触发；
- 用户取消和停止采集优先级最高；
- 隐私模式禁止原始音频和图像；
- 紧急联系人与号码由受控配置管理；
- 低电量、过温、电源异常进入保护策略；
- 网络失败时关键事件不得被普通事件挤出队列；
- 不可逆配置、Bootloader、固件升级需要人工或受控授权；
- 模型失败、超时或版本不兼容时回退到确定性安全基线。

---

## 9. 端、Base、云的职责划分

| 层级 | 主要职责 | 不承担的职责 |
|---|---|---|
| Ego Link | 低功耗感知、端侧微模型、事件路由、本地提醒、断网兜底、必要证据采集 | 通用多模态推理、长期记忆、复杂自然语言规划 |
| PC Development Bridge / PC Simulator | P0 双板中继、协议验证、事件回放、命令模拟、规则基线测试、时间同步和记录 | 正式用户长期记忆、生产级安全服务、最终产品必需依赖 |
| Ego Base | 本地 ASR、视觉理解、长期记忆、个性化推理、联系人联动、策略生成 | 未授权持续上传原始隐私数据 |
| 云端增强 | 经明确授权处理少数本地能力不足的复杂任务 | 基本安全闭环的强依赖 |

---

## 10. 典型事件闭环：撞击后静止

```text
1. AMOLED / `wearable_node` 的 QMI8658 检测到高冲击或跌倒候选
2. MotionNet 或规则基线输出 `motion_event`
3. PC Bridge 接收运动事件并交给规则版 ContextRouter
4. ContextRouter 发现证据不足，输出 `ask_user`
5. AMOLED 板显示“检测到异常，你现在安全吗？”
6. 用户点击“安全”或“需要帮助”
7. PC Bridge 记录 `user_confirmation`
8. ContextRouter 请求 `connectivity_node` 刷新 GNSS，并可按策略请求音频或图像证据
9. Safety Kernel 检查隐私、电量和动作边界
10. PC Bridge 形成完整安全事件记录
11. 同一 session 可离线回放给 ContextRouter
12. 结果回流为后续 MotionNet / AudioGate 训练标签
```

---

## 11. 数据与训练策略

### 11.1 数据优先于模型

首个神经网络前必须先具备：

- 统一时间戳和序号；
- 可追溯的设备、固件、传感器配置和模型版本；
- 事件前后环形缓冲；
- 用户确认标签；
- 数据授权和隐私字段；
- 原始证据与结构化记录的哈希关联；
- 按人员或完整 session 切分训练、验证和测试集。

### 11.2 首批数据顺序

1. 先大量采集正常负样本；
2. 再在成人志愿者和安全环境中采集受控模拟正样本；
3. 禁止通过真实伤害、危险驾驶或真实摔车制造数据；
4. 在成人模拟和工程验证稳定前，不将儿童或老人作为第一批模型训练对象。

### 11.3 Teacher 与蒸馏

未来较强模型可用于：

- 辅助切片和预标注；
- 发现难例；
- 生成软标签；
- 将复杂判断蒸馏为端侧专用任务。

Teacher 标签不能替代重要测试集的人工复核。

### 11.4 量化与部署

首选 INT8。模型交付必须包含：

- 模型文件；
- 输入维度、单位和归一化参数；
- 类别与阈值；
- PC 参考推理；
- 固件一致性测试向量；
- 模型卡；
- 精度、RAM、Flash、延迟和能耗报告；
- 文件哈希和版本号。

---

## 12. 当前状态

### MODEL-DEVICE-003 Tiny Safety firmware CLI closed loop

MODEL-DEVICE-003 makes the Tiny Safety firmware harness operator-observable
through the existing `mqtt_heartbeat` safety serial CLI. A flashed image can
run `safety tiny status`, `safety tiny selftest`, and `safety tiny demo ...` to
report the MODEL-DEVICE-001 model identity, execute exported synthetic
test-vector checks, and show dry-run candidate predictions. This remains a
candidate-only loop: no model output is mapped to SMS, calls, dispatch, or
external escalation, and SOS/cancel still require deterministic Safety Kernel
handling. No hardware runtime, latency, RAM, flash, power, field-data accuracy,
or release-readiness claim is made by this step.

### MODEL-DEVICE-002 Tiny Safety firmware dry-run harness

MODEL-DEVICE-002 connects the MODEL-DEVICE-001 generated C constants to the
existing firmware `safety_model` component as an explicit dry-run harness. It
can extract the 14-feature vector from `ego_sc_model_input_t`, run the tiny
linear classifier, and self-check the exported synthetic test vectors. The
existing deterministic `safety_model_evaluate()` path remains the active mock/
rule baseline. The tiny harness does not map model output to real calls, SMS,
dispatch, or external escalation; SOS/cancel still return
`safety_rule_required` and must be handled by Safety Kernel rules. No firmware
flash, device deployment, real-world accuracy, latency, RAM, flash, or power
claim is made by this step.

### MODEL-DEVICE-001 Tiny Safety Model v0

MODEL-DEVICE-001 adds the first local train/export loop for a device-shaped
Tiny Safety Model artifact. It consumes the existing `model_input` contract and
predicts `normal`, `uncertain`, `needs_check`, or `possible_risk` from bounded
structured features. The artifact is synthetic-only and dry-run only: it does
not replace Safety Kernel rules, does not handle SOS/cancel, does not use
private field samples, does not integrate firmware, and does not claim
real-world accuracy, latency, RAM, flash, power, or release readiness.

当前 M0 已建立：

- `sensor_frame`、`model_input`、`model_output`、`safety_event`、`base_command` 契约；
- 规则版 ContextRouter；
- 合成安全场景；
- 回放、契约和规则基线测试；
- 固件 C 接口契约；
- Codex 集成任务。

当前 P0 双板桥接已建立：

- `wearable_node` / `connectivity_node` 角色识别和桥接测试；
- `motion_event` 进入 PC Bridge 后生成 `ask_user` 与 `request_location` 命令的骨架；
- QMI8658 原始 IMU 数据采集、质量检查和夹具重复性记录；
- IMU 记录仍标记为 `bridge_uplink/unverified`，直到完成正式验收。

当前尚未完成：

- 真实 MotionNet；
- 真实 AudioGate；
- 真实 VisionGate；
- 学习型 ContextRouter；
- ESP32-S3 量化模型部署；
- AMOLED 屏幕确认回传与 PC Bridge 的现场端到端验收；
- SIM7670G 板 `request_location` / `capture_image` 命令 ACK 和真实能力证据；
- 正式 Ego Base 多模态协同；
- 实际硬件功耗与安全效果验证。

任何文档、测试或界面不得把 M0 规则模拟结果描述为真实安全识别能力已经验证。

---

## 13. 版本路线

| 阶段 | 目标 |
|---|---|
| M0 | 契约、规则基线、模拟场景、回放和集成接口 |
| M1 | 真实传感器数据采集、时间同步、会话记录、标注与质量检查 |
| M2 | MotionNet 初版 + 规则版 ContextRouter 协同 |
| M3 | AudioGate 和事件音频环形缓冲 |
| M4 | VisionGate 和主动视觉采集 |
| M5 | Ego Base 本地多模态理解、长期记忆和命令闭环 |
| M6 | 蒸馏、INT8 量化、ESP32-S3 部署、延迟/RAM/Flash/能耗评价 |

阶段可以局部交叉，但不得跳过 M1 数据基础，直接宣称模型有效。

---

## 14. 与 Codex 的协作边界

### 14.1 Codex 主维护

```text
firmware/**
pc_simulator/**
quality_tests/firmware/**
quality_tests/pc_simulator/**
```

主要负责：驱动、缓冲、记录、通信、模型运行时适配、OTA、串口工具、模拟器和硬件联调。

### 14.2 模型侧主维护

```text
model_lab/**
model_artifacts/**
shared/contracts/**
shared/embedded/**
quality_tests/model_contract/**
docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
```

Codex 集成时原则上不得自行改变字段、单位、枚举、特征顺序、阈值语义或模型版本。发现不适配应记录到：

```text
docs/modeling/INTEGRATION_ISSUES.md
```

### 14.3 契约优先级

发生冲突时：

1. 安全和隐私规则优先；
2. `shared/contracts/**` 的机器可读定义优先于说明性文字；
3. 当前阶段任务文档优先于长期路线；
4. 模拟、编译和单元测试不得替代真实硬件验证或模型效果验证。

---

## 15. 非目标

当前不做：

- 在 ESP32-S3 上运行通用 LLM、VLM 或长对话模型；
- 持续录像或持续上传原始音频；
- 人脸身份识别；
- 医疗诊断；
- 未经确认自动拨打真实联系人；
- 用单次演示代替统计测试；
- 在没有真实数据时训练并发布“跌倒识别模型”；
- 以云端 API 作为核心安全链路。

---

## 16. 一句话架构定义

> Ego Link 用 MotionNet、AudioGate 和 VisionGate 将现实世界压缩成低成本结构化证据，用 ContextRouter 决定是否打扰、补采、上报或升级，用 Safety Kernel限定不可突破的安全与隐私边界，再由 Ego Base 完成复杂理解、长期记忆和个性化行动。

# Ego Link P0 双开发板 + PC 中继集成验证架构

> **2026-09-09 状态：历史开发证据架构，已被 ADR-0015 覆盖当前 A 线排期。**
> 本文保留既有双板/PC Bridge 设计与证据，不作删除。当前 A 线只使用一块
> `connectivity-node-001` 及必要 Camera、外接 IMU、电源和天线；AMOLED、板间
> 转发和 PC runtime/forwarding 不参与本轮运行或验收，CALL/完整 SOS 暂停。
> 下文所有“当前”均是 2026-06-24 当时的历史表述，不是 2026-09-09 authority。

> 状态：P0 当前实现形态  
> 更新日期：2026-06-24  
> 适用阶段：P0-A / P0-B  
> 相关文档：`docs/CONTEXT_INDEX.md`、`docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md`、`docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`

## 1. 架构定义

当前 Ego Link P0 不推翻原有 Mock-first 和抽象接口原则，而是把实现形态明确为：

> **双开发板 + PC 中继的集成验证架构。**

Ego Link 长期仍是 EGO 的随身感知与 4G 交互入口。复杂多模态理解、长期记忆和主动协同最终与本地 Ego Base 配合完成。PC 当前只是开发期桥接器、观察器、记录器和回放工具，不能被固化为正式产品依赖。

AMOLED 板是当前的可穿戴应用主节点；SIM7670G 板是通信、定位和摄像头扩展节点。不要在架构上把 SIM7670G 开发板固化为最终主控。

## 2. 当前节点划分

```text
可穿戴主节点
ESP32-S3-Touch-AMOLED-2.06
├─ QMI8658六轴IMU
├─ 双麦克风
├─ 屏幕、触摸、扬声器
├─ MotionNet / AudioGate
└─ USB连接电脑

通信扩展节点
ESP32-S3-SIM7670G-4G
├─ SIM7670G 4G
├─ GNSS
├─ 摄像头
├─ TF卡和缓存
└─ USB连接电脑

PC Development Bridge
├─ 自动识别两个节点
├─ 串口消息中继
├─ 统一事件总线
├─ ContextRouter
├─ Safety Kernel
├─ 数据记录与时间同步
├─ 事件回放
└─ 调试Dashboard
```

## 3. 角色与职责

### 3.1 `wearable_node`

当前硬件：ESP32-S3-Touch-AMOLED-2.06。

职责：

- 采集 QMI8658 原始六轴 IMU 数据；
- 验证双麦克风链路和 AudioGate 输入路径；
- 承载屏幕、触摸、扬声器和用户确认交互；
- 逐步运行 MotionNet / AudioGate；
- 通过 USB 与 PC Development Bridge 通信；
- 在 `hello` 中声明 `role = "wearable_node"`。

### 3.2 `connectivity_node`

当前硬件：Waveshare ESP32-S3-SIM7670G-4G。

职责：

- 验证 SIM7670G 4G 能力状态；
- 验证 GNSS 能力状态和定位刷新命令；
- 验证摄像头能力状态和按需拍照命令；
- 验证 TF 卡、本地缓存和离线补传路径；
- 接收 `request_location`、`capture_image` 等命令并返回 ACK / 状态；
- 通过 USB 与 PC Development Bridge 通信；
- 在 `hello` 中声明 `role = "connectivity_node"`。

第一阶段允许 Mock 与真实驱动并存，但消息、日志和记录必须标明数据来源，不能把 Mock 结果当成真实硬件证据。

### 3.3 PC Development Bridge

PC Development Bridge 当前承担：

- 自动枚举和识别两个 USB 串口设备；
- 基于 `hello` 的 `device_id` 与 `role` 绑定节点，不写死 COM 口编号；
- 在两个节点之间转发版本化消息；
- 提供统一事件总线；
- 运行 P0 规则版 ContextRouter 和 Safety Kernel；
- 对齐时间、分配 `session_id`、记录原始事件和派生命令；
- 支持事件回放，使记录可脱离开发板重新喂给 ContextRouter；
- 提供调试 Dashboard。

PC 不等于正式 Ego Base。P0 中的 PC 只用于开发期桥接、观察、记录和回放。

## 4. P0 开发目标

### P0-1：双板接入

- 两块板同时连接电脑；
- 每块板启动后发送 `hello`；
- PC 根据 `device_id` 和 `role` 识别设备；
- 不把 COM 口编号写死；
- 任意一块板重启后可以重新加入；
- 建议角色名固定为 `wearable_node` 和 `connectivity_node`。

### P0-2：统一消息协议

两块板和 PC 都通过同一套版本化协议通信。未来传输从 USB 切换为 UART、BLE 或板内接口时，上层业务不重写。

最小消息包络：

```json
{
  "protocol_version": "0.2",
  "source": "wearable-node-001",
  "target": "pc-bridge",
  "type": "motion_event",
  "seq": 1024,
  "timestamp_ms": 1782210408000,
  "session_id": "session-001",
  "payload": {}
}
```

约束：

- `protocol_version` 必须显式存在；
- `source` 和 `target` 使用逻辑设备名，不使用 COM 口名；
- `seq` 在每个设备侧单调递增；
- `timestamp_ms` 使用统一毫秒时间语义；
- `session_id` 由 PC Bridge 分配或确认；
- `payload` 只放类型相关内容，不破坏外层包络。

### P0-3：真实传感器数据

AMOLED 板完成：

- QMI8658 原始六轴数据采集；
- 统一采样频率和时间戳；
- IMU 窗口记录；
- 麦克风链路验证；
- 屏幕询问和用户确认；
- 数据保存或上传电脑。

SIM7670G 板完成：

- 4G、GNSS、摄像头能力状态；
- Mock 与真实驱动并存的第一阶段能力矩阵；
- 接收并处理 `request_location`、`capture_image` 等命令；
- 对命令返回 ACK、错误码、能力状态和证据引用。

### P0-4：安全陪伴最小闭环

首先跑通一个完整场景：

```text
AMOLED板产生撞击/跌倒候选
        ↓
PC Bridge接收运动事件
        ↓
ContextRouter判断需要确认
        ↓
AMOLED板显示“检测到异常，你现在安全吗？”
        ↓
用户点击“安全”或“需要帮助”
        ↓
PC请求4G板刷新GNSS
        ↓
形成完整安全事件记录
```

P0-4 暂时不要求真实报警、真实拨号或正式联系人联动，先验证消息、状态、动作和证据闭环。

### P0-5：数据记录与回放

PC 必须保存：

- session 元数据；
- IMU 数据；
- AudioGate 结果；
- GNSS 和网络状态；
- 用户操作；
- 模型输入输出；
- 设备命令和 ACK；
- 异常和断线日志。

同一份记录必须能够脱离开发板重新回放给 ContextRouter。这是后续训练 MotionNet、评估 AudioGate 和复现实测问题的基础。

## 5. 当前实现进度

截至 2026-06-24，距离 P0-4 完整现场闭环还不是从零开始，但仍未达到验收。

已经具备：

- PC 侧 `board_bridge` PoC 能从 JSONL / stdin 消费两个节点的 `hello` 和上行事件；
- PC 侧能按 `role` 绑定 `wearable_node` 与 `connectivity_node`，不依赖固定 COM 口语义；
- 高冲击 / 跌倒候选 `motion_event` 能触发 `ask_user` 与 `request_location` 两条 `command_sent` 记录；
- session recorder 能把桥接进入的 IMU 事件记录为 `bridge_uplink/unverified` 传感器帧；
- AMOLED 桥接固件能发送 `hello`、QMI8658 `imu_whoami`、`imu_sample` 和 `amoled_bridge_done`；
- 已有 QMI8658 实物采样、质量检查和夹具重复性记录；
- SIM7670G 侧已有 PC AT GNSS probe 工具和 `location_report` 记录路径。

仍缺少：

- 双 USB 串口实时自动枚举、持续读取和断线重连的现场 Bridge；
- AMOLED 板接收 `ask_user` 后驱动屏幕显示，并通过触摸产生 `user_confirmation`；
- SIM7670G 板接收 `request_location` / `capture_image` 后返回命令 ACK、状态和证据引用；
- `motion_event → ask_user → user_confirmation → request_location → location_report/ACK → safety_event_record` 在同一 `session_id` 下的完整记录；
- 同一记录离线回放给 ContextRouter 的 P0-4 验收报告；
- 当前部分 PoC 仍使用 `protocol_version` 0.1，下一轮需要迁移到目标包络 `0.2`。

因此，完整场景的剩余工作可拆成三段：

1. **Bridge 在线化**：把当前文件/JSONL PoC 接到真实双串口，完成 hello 识别、重启重加入和命令下发；
2. **两端命令闭环**：AMOLED 完成屏幕/触摸确认，SIM7670G 完成定位命令 ACK 或真实 GNSS 状态；
3. **session 验收**：把用户确认、定位结果、命令 ACK 和最终安全事件记录到同一 session，并跑离线回放。

## 6. 设计边界

- 当前 P0 采用双开发板分别通过 USB 连接 PC；
- 当前不要求板间 UART 直连；
- PC 不是正式 Ego Base，也不是产品依赖；
- 不允许将 COM 口编号写死；
- 设备必须通过版本化 `hello` 消息识别；
- 两个节点必须共享同一套版本化消息协议；
- Mock 数据可以用于链路验证，但必须带有 Mock 标记；
- 最终产品目标不是两个 ESP32 开发板，而是单低功耗主控 / AI MCU + 蜂窝模组 + IMU、麦克风、摄像头等必要器件。

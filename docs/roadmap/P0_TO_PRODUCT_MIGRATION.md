---
document_status: authoritative
last_verified: 2026-08-23
verified_by: codex
---

# Ego Link 从 P0 到产品形态迁移路线

> 状态：P0 到首发产品的当前迁移路线
> 更新日期：2026-08-23
> 相关架构：`docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md`

## 2026-08-23 首发与调度重基线

[ADR-0011](../architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md)
、[ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md)
和 [FIRST_LAUNCH_EXECUTION.md](../current/FIRST_LAUNCH_EXECUTION.md) 控制当前
迁移顺序：首发闭环是 `Reliable Location + Ego Call + SOS`，由四条独立 lane
并行推进，而不是等待下方 P0-A → P4 全部串行完成。最低 Rule Policy/Safety
Kernel 仍必须在端侧确定性工作；MotionNet/AudioGate、事件相机和高级上下文理解
作为 L2/L3 并行或后续能力，不阻塞一个已满足产品保证门的首发闭环。

AMOLED/触摸板、双板与 PC Bridge 是已验证资产和迁移工具，不是当前无屏 EgoCore
的产品形态要求。首发通话主路由为 LTE data + managed RTC + Guardian App；最终 PCB
仍应评估并尽量保留 Native VoLTE 模组/音频/RF 迁移路径，但它受独立
`G0V-VOLTE-RESERVE` 管理，不是首发软件门。下方 P0-A/P0-B/P1/P2 阶段文本保留
历史依赖和验收资产价值，不得再解释为全局串行许可链。

ADR-0012 进一步冻结当前三项产品能力 Gate：`P0-LOC`、`P0-CALL`、`P0-SOS`
目前全部为 `NOT_RUN`。设备端 Location Engine v0 / Sensor Policy v0 持有断网时
仍需工作的最小定位与策略状态；服务器只做版本化镜像、事件时间轴、回放、比较
和更丰富的 derived fusion。任何 receive/ingest 顺序都不能代替 source event
time。旧 `G0-EGOCALL` 仅作为历史证据族名称，当前放行名称为 `P0-CALL`；旧
`PROD-002` 仅保留为合规 intake，执行后继为 `COMPLIANCE-010`。

当前依赖链是：

```text
LOC-020 -> POLICY-010 -> REPLAY-010 -> LOC-021 -> FIELD-020 ----+
                                             |                  |
CALL-010 -> CALL-020 ------------------+      +-> SOS-010 -------+-> release
HW-020 -> HW-021 -> HW-022 ------------+-> CALL-021 --^
OUTBOX-010 -----------------------------------------^

HW-022 + LOC-021 + CALL-021 + SOS-010 -> PWR-020

FIELD-020 + SOS-010 + OUTBOX-010 + OPS-004 + PWR-020 + HW-022
    + COMPLIANCE-010 + acoustic/RF/water/security/privacy/NPI evidence
    -> P0-RELEASE-010
```

`FIELD-020` 与 `SOS-010` 在各自依赖满足后并行推进，只在最终
`P0-RELEASE-010` 汇合；外场数据不是启动 SOS 集成的串行前置。硬件迁移必须经过
`HW-020` 接口基线 -> `HW-021` 精确可制造设计 -> `HW-022` 实体集成样机；
`CALL-021` 同时依赖真实 `CALL-020` 结果和 `HW-022`，不能用双开发板或 PC Bridge
证据代替。`COMPLIANCE-010` 在 HW-020 之后独立启动，并在最终 release review
汇合，而不是等待 PCB 完成后才开始。

当前状态：LOC/POLICY/REPLAY 与 HW-020 已完成参考/接口边界并获准进入下一步；
LOC-021、CALL-010、CALL-020 的离线准备、OUTBOX-010 主机参考和 HW-021 正在推进；
FIELD-020、OPS-004、HW-022、CALL-021、SOS-010、PWR-020 与最终 release review
仍未完成。所有这些工程状态均不改变三个 P0 Gate 的 `NOT_RUN`。

Sprint 1 不构建 PSTN、SMS、公共应急调度或 Native VoLTE；Camera 仅可作为带
授权、事件时间和触发原因的可选实验观测。AI 先做数据质量、事件时间回放、离线
对比和 Shadow Mode，不进入 P0 决策链。

## 1. 长期方向

Ego Link 长期定位不变：它是 EGO 的随身感知节点、安全前哨和 4G 交互入口。复杂能力最终与本地 Ego Base 协同完成。

当前双开发板 + PC 中继只服务于 P0 集成验证，不代表最终产品结构。PC 不能被固化为正式 Ego Base，SIM7670G 开发板也不能被固化为最终主控。

最终产品目标是：

```text
一颗低功耗主控 / AI MCU
    +
一颗 4G / VoLTE 蜂窝模组
    +
IMU、麦克风/扬声器、交互器件和电源系统
    +
可选摄像头兼容接口（非 P0 放行依赖）
```

## 2. 历史阶段路线（非当前 P0 依赖图）

下列 P0-A 至 P4 保留迁移资产和长期能力的历史分层，不控制 Productization
Sprint 1 的任务启动或放行。当前依赖只以上文 ADR-0012 图为准；其中 MotionNet、
AudioGate、摄像头和通用 ContextRouter 能力属于非阻塞 L2/L3 或后续阶段。

```text
P0-A
双板分别通过USB连接PC
PC承担中继、观察和ContextRouter

P0-B
接入真实IMU、声音、GNSS、4G和摄像头
建立真实数据集

P1
MotionNet和AudioGate运行在AMOLED板
ContextRouter逐渐迁到可穿戴主节点
PC只负责监控和记录

P2
两块板通过UART直接连接
脱离PC完成安全陪伴闭环

P3
通过自定义PCB收敛为：
一颗低功耗主控/AI MCU
+ 一颗4G/VoLTE模组
+ IMU、麦克风、摄像头

P4
接入Ego Base
完成长期记忆、多模态理解和主动协同
```

## 3. 阶段验收口径

### Demo-first 插队路线

在 P0-A / P0-B 之间先做最小功能原型，避免过早进入大而全验收。

```text
Demo v0.1
PC 最小安全循环：
motion_event -> ask_user -> user_confirmation -> request_location -> mock location -> safety_event

Demo v0.2
AMOLED 板接收 ask_user，屏幕显示询问，触摸回传 user_confirmation

Demo v0.3
SIM7670G 板接收 request_location 并返回 ACK / GNSS 状态

Demo v0.4
接入真实 GNSS / 4G / 摄像头状态，但仍允许 Mock 兜底

Demo v0.5
再补断线重连、回放质量、异常日志和长期稳定性
```

当前可运行入口：

```powershell
python scripts\run_minimal_safety_demo.py --response safe
python scripts\run_minimal_safety_demo.py --response help
```

当前 AMOLED 侧最小屏幕入口：

```powershell
cd firmware\amoled_safety_demo
idf.py -p <AMOLED_COM_PORT> flash
```

`firmware/amoled_safety_demo` 已能在可穿戴节点上创建安全询问 UI，并在串口输出
`hello` / `ask_user_rendered`；实机点击已捕获 `safe` 和 `help` 两类 `user_confirmation`。
它还不是完整 Demo v0.2：当前提示由固件启动后直接显示，尚未由 PC Bridge 的
`ask_user` 命令驱动。

Demo-first 的规则是：先让核心产品体验可演示，再逐步替换 Mock 输入、补硬件 ACK、补质量门和稳定性。

### P0-A：双板 USB + PC Bridge

验收重点：

- 两块板能同时接入 PC；
- 每块板启动后发送版本化 `hello`；
- PC 根据 `device_id` 和 `role` 识别 `wearable_node` 与 `connectivity_node`；
- 不硬编码 COM 口编号；
- 任意节点重启后可重新加入；
- PC Bridge 能中继消息、分配/维护 `session_id`、记录事件并驱动规则版 ContextRouter；
- 安全陪伴最小闭环能用 Mock 与真实数据混合跑通。

### P0-B：真实数据集

验收重点：

- AMOLED 板输出 QMI8658 原始六轴 IMU 数据和 IMU 窗口；
- 音频链路产生可记录的 AudioGate 输入或结果；
- 屏幕与触摸能完成“安全 / 需要帮助”确认；
- SIM7670G 板输出 4G、GNSS、摄像头能力状态；
- `request_location`、`capture_image` 等命令有 ACK、错误和证据记录；
- PC 保存 session 元数据、传感器数据、模型输入输出、用户操作、命令 ACK、异常和断线日志；
- 记录文件可以离线回放给 ContextRouter。

### P1：端侧微模型迁移

验收重点：

- MotionNet 和 AudioGate 在 AMOLED / `wearable_node` 上运行；
- ContextRouter 从 PC 逐步迁移到可穿戴主节点；
- PC 降级为监控、记录、回放和调试工具；
- 安全规则仍可审计，SOS 和用户取消不依赖概率模型。

### P2：脱离 PC 的双板闭环

验收重点：

- 两块板通过 UART 或等价板间接口通信；
- 不依赖 PC 完成安全陪伴最小闭环；
- `wearable_node` 能请求 `connectivity_node` 刷新 GNSS、上报网络状态或拍照；
- 断线、重启和缓存补传行为可复现。

### P3：自定义 PCB 收敛

验收重点：

- 架构从两块开发板收敛为产品 PCB；
- 主控 / AI MCU、蜂窝模组、IMU、麦克风、摄像头和电源系统完成工程选型；
- 功耗、成本、尺寸、热设计、天线、音频、摄像头和量产认证进入统一评估；
- ESP32-S3 开发板经验转化为协议、模型、数据和测试资产，而不是被当作必须保留的硬件结构。

### P4：接入 Ego Base

验收重点：

- Ego Base 接管长期记忆、多模态理解、个性化推理和主动协同；
- Ego Link 继续承担随身感知、安全前哨、交互入口和远程通信；
- 云端能力只作为用户授权后的增强，不成为基本安全闭环的必需依赖。

## 4. 不变原则

- 不为了阶段验证把 PC 固化成产品依赖；
- 不为了当前通信板便利把 SIM7670G 开发板固化成最终主控；
- 不跳过真实数据集直接声明 MotionNet / AudioGate 有效；
- 不把 Mock 结果当成真实传感器、4G、GNSS 或摄像头证据；
- 上层业务依赖版本化消息协议和硬件抽象，不依赖 USB、UART、BLE 或具体 COM 口。

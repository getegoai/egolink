# Ego Link 从 P0 到产品形态迁移路线

> 状态：P0 当前路线修订  
> 更新日期：2026-06-24  
> 相关架构：`docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md`

## 1. 长期方向

Ego Link 长期定位不变：它是 EGO 的随身感知节点、安全前哨和 4G 交互入口。复杂能力最终与本地 Ego Base 协同完成。

当前双开发板 + PC 中继只服务于 P0 集成验证，不代表最终产品结构。PC 不能被固化为正式 Ego Base，SIM7670G 开发板也不能被固化为最终主控。

最终产品目标是：

```text
一颗低功耗主控 / AI MCU
    +
一颗 4G / VoLTE 蜂窝模组
    +
IMU、麦克风、摄像头、交互器件和电源系统
```

## 2. 阶段路线

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

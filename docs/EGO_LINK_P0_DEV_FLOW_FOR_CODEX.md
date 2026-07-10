---
document_status: source_draft
last_verified: 2026-06-27
verified_by: user
superseded_by:
  - docs/development/DEV_FLOW.md
  - docs/development/VPS_MESSAGE_HUB.md
  - docs/development/PROTOCOL.md
  - docs/development/FIELD_TEST.md
  - docs/current/ROADMAP_EGOLINK_P0.md
---

# Ego Link P0 开发流程重整与 USB-Free VPS 中枢版本化路线

> 面向 Codex 的工程执行文档
> 版本：v0.1
> 日期：2026-06-27
> 目标：把 Ego Link P0 从“临时指令驱动开发”调整为“公网 VPS 消息中枢 + USB-Free 外场测试 + 可演示主干优先 + 三轨版本化演进”的工程开发流程。

> 落地状态：本文是用户提供的源草案。当前权威落地文档已拆分到 `docs/development/DEV_FLOW.md`、`docs/development/VPS_MESSAGE_HUB.md`、`docs/development/PROTOCOL.md`、`docs/development/FIELD_TEST.md` 和 `docs/current/ROADMAP_EGOLINK_P0.md`。本文中的 `ENG-002` 草案编号与仓库既有 `ENG-002 Control Plane Commit / Remote Policy` 冲突，实际落地任务记录为 `ENG-005 P0 Dev Flow Baseline`。

---

## 0. 本轮任务结论

Ego Link P0 不再采用“根据临时指令随时改功能”的开发方式，也不采用单纯模块化、长期不可演示的开发方式。

本项目从现在开始采用：

> **USB-Free、VPS Message-First、Demo-Driven、Contract-First 的 Walking Skeleton 开发模式。**

含义如下：

1. **USB-Free**：USB 只用于烧录、临时串口调试和失败后日志导出；任何正式测试、版本验收、外场演示都不能依赖 USB 串口作为运行链路。
2. **VPS Message-First**：已有公网 VPS 和公网 IP，电脑端消息系统应部署到 VPS，设备端、PC 模拟器、Web 控制台都通过公网 VPS 通信，按最接近产品实际运行状态的方式开发。
3. **Demo-Driven**：每一个版本都必须形成可演示闭环，不能长时间只完善内部模块而看不到端到端效果。
4. **Contract-First**：先固定通信协议和数据结构，再分别开发固件、消息系统、Web 页面，避免随意跨层修改。
5. **Walking Skeleton**：先建立一条最薄但完整的端到端主干链路，再沿着主干逐步增强功能和可靠性。

---

## 1. 产品化运行架构

### 1.1 默认架构

Ego Link P0 的最小产品化架构如下：

```text
[Ego Link Device / Firmware]
        |
        | 4G / Wi-Fi / Cat.1 / NB-IoT / LTE
        | HTTPS / MQTT over TLS / WebSocket
        v
[Public VPS Message Hub]
        |
        | WebSocket / HTTPS
        v
[Web Dashboard / Operator Console]

[PC Simulator]
        |
        | HTTPS / MQTT over TLS
        v
[Public VPS Message Hub]
```

关键原则：

- 设备端主动连接 VPS。
- Web 控制台连接 VPS。
- PC 模拟器连接 VPS。
- 电脑不直接连接设备。
- 设备外场测试时不依赖 USB。
- VPS 是消息中枢、设备状态中心、命令队列和测试观测层。
- VPS 不是核心 AI 大脑，不承载 Ego 主体的本地隐私数据和核心智能逻辑。

### 1.2 VPS 的职责边界

VPS 负责：

1. 设备注册与鉴权。
2. 接收设备心跳、GNSS、网络、电源、错误、日志等上行数据。
3. 为 Web Dashboard 提供设备状态、位置、轨迹、消息日志。
4. 保存下行命令队列。
5. 跟踪设备 ACK、命令超时、执行失败。
6. 支撑外场测试记录和测试报告导出。
7. 保存最小必要运行数据，用于 P0 工程验证。

VPS 不负责：

1. 不承载 Ego 主体的核心本地 Agent 逻辑。
2. 不保存用户隐私上下文、长期记忆、核心个人数据。
3. 不默认上传原始语音、图像、屏幕内容。
4. 不调用云端大模型作为核心智能链路。
5. 不把 USB 串口日志作为正式运行证据。

---

## 2. 三条版本轨道

后续开发必须拆成三条相互约束但独立演进的轨道。

### 2.1 Server-Web 轨道

负责 VPS 消息系统、设备管理、Web 控制台、地图轨迹、命令下发、日志查看。

建议版本：

| 版本 | 目标 | 验收状态 |
|---|---|---|
| S0 | VPS 上部署最小消息服务，支持模拟设备注册、心跳、模拟定位上报 | 必须可演示 |
| S1 | Web Dashboard 显示设备在线状态、最新坐标、最后上报时间 | 必须可演示 |
| S2 | 支持 Web 下发命令、设备拉取或订阅命令、设备 ACK | 必须可演示 |
| S3 | 支持地图轨迹、测试场次、消息日志、错误状态 | 必须可演示 |
| S4 | 支持多设备、外场测试报告导出、设备健康诊断 | 必须可演示 |

### 2.2 Firmware 轨道

负责硬件端启动、网络连接、GNSS 获取、数据上报、命令接收、ACK、缓存、重连、低功耗。

建议版本：

| 版本 | 目标 | USB 约束 |
|---|---|---|
| F0 | 设备启动后向 VPS 上报 boot 和 heartbeat | 运行验收不得依赖 USB |
| F1 | 周期性上报模拟 GNSS 或固定坐标 | 运行验收不得依赖 USB |
| F2 | 接入真实 GNSS，支持 fix / no-fix 状态上报 | 运行验收不得依赖 USB |
| F3 | 支持命令拉取或订阅，收到命令后 ACK | 运行验收不得依赖 USB |
| F4 | 网络掉线自动重连，本地缓存未发送消息，恢复后补发 | 运行验收不得依赖 USB |
| F5 | 上报电池、电量、RSSI、卫星数、HDOP、错误码、重启原因 | 运行验收不得依赖 USB |
| F6 | 支持外场测试模式、远程参数配置、日志摘要回传 | 运行验收不得依赖 USB |

### 2.3 Protocol / Contract 轨道

负责设备、模拟器、VPS、Web 之间的通信协议、字段命名、版本兼容、错误码和消息语义。

建议版本：

| 版本 | 目标 |
|---|---|
| P0.1 | 固定 telemetry / heartbeat / command / ack / error 的最小 JSON 结构 |
| P0.2 | 增加 GNSS 质量、电源、网络、错误码字段 |
| P0.3 | 增加本地缓存、补发、seq 去重、测试场次字段 |
| P0.4 | 增加多设备、设备能力描述、远程配置字段 |

协议变更规则：

- 任何固件和 Web 开发不得随意修改协议字段。
- 如必须修改协议，先更新 `docs/development/PROTOCOL.md` 或 `shared/contracts/`。
- 协议必须包含 `protocol_version`。
- 新字段优先做兼容新增，不要破坏旧字段。
- 删除字段必须升级协议版本，并说明兼容策略。

---

## 3. 端到端版本路线

### R0：VPS + PC Simulator 纯模拟闭环

目标：不接硬件，先证明公网 VPS 消息中枢和 Web 控制台成立。

链路：

```text
PC Simulator
  -> VPS Message Hub
  -> Web Dashboard
  -> Command Queue
  -> PC Simulator ACK
```

实现内容：

1. VPS 上运行消息服务。
2. PC Simulator 以虚拟设备身份注册。
3. PC Simulator 周期性发送 heartbeat。
4. PC Simulator 周期性发送模拟 GNSS 坐标。
5. Web Dashboard 显示设备在线、最后坐标、最后上报时间。
6. Web Dashboard 可下发一条简单命令。
7. PC Simulator 收到命令后返回 ACK。

Definition of Done：

- 在浏览器打开 VPS 上的 Web Dashboard，能看到一台虚拟设备在线。
- 虚拟设备坐标能持续更新。
- Web 下发命令后，能看到 ACK 状态从 pending 变为 ok。
- 不依赖任何硬件。
- 所有消息有服务端日志和基础数据库记录。

---

### R1：真实硬件无 GNSS 闭环

目标：真实设备接入 VPS，但 GNSS 先用模拟坐标或固定坐标，验证设备运行不依赖 USB。

链路：

```text
Real Device Firmware
  -> 4G / Wi-Fi
  -> VPS Message Hub
  -> Web Dashboard
  -> Command Queue
  -> Real Device ACK
```

实现内容：

1. 真实硬件启动后连接 VPS。
2. 设备上报 boot 事件。
3. 设备周期性上报 heartbeat。
4. 设备周期性上报模拟 GNSS 或固定坐标。
5. Web Dashboard 显示真实设备在线。
6. Web Dashboard 可下发命令。
7. 真实设备收到命令后返回 ACK。

Definition of Done：

- 设备烧录完成后，可以断开 USB。
- 设备通过电池或独立供电运行。
- Web Dashboard 能看到真实设备在线。
- Web Dashboard 能看到设备持续上报数据。
- Web 下发命令后真实设备返回 ACK。
- 串口日志不能作为验收依据，只能作为辅助调试信息。

---

### R2：真实 GNSS 外场闭环

目标：设备断开 USB 后到室外获取真实 GNSS 定位，并通过 VPS 展示位置和轨迹。

链路：

```text
Real Device + GNSS
  -> Outdoor Field Test
  -> 4G / Wi-Fi
  -> VPS Message Hub
  -> Web Dashboard Map / Trace
```

实现内容：

1. 设备上报真实 GNSS 数据。
2. 未定位时仍然上报 `fix=false`，不能沉默。
3. 已定位时上报经纬度、卫星数、HDOP、高度、速度等字段。
4. Web Dashboard 显示最新位置。
5. Web Dashboard 显示历史轨迹。
6. Web Dashboard 显示 GNSS 状态：searching / fixed / lost / error。
7. Web 可下发调整上报间隔命令。
8. 设备返回 ACK。

Definition of Done：

- 拿设备到室外测试，全程不连接 USB。
- Web Dashboard 能看到设备从 no-fix 到 fix 的状态变化。
- Web Dashboard 能看到真实经纬度更新。
- 步行一段距离后，Web Dashboard 能看到轨迹点。
- Web Dashboard 能显示最后上报时间、GNSS fix 状态、卫星数、HDOP。
- 若定位失败，Web Dashboard 能解释失败原因，而不是只显示“无数据”。

---

### R3：外场可靠性版本

目标：解决真实外场测试中的弱网、掉线、定位慢、日志不足、状态不可解释等问题。

实现内容：

1. 网络断开自动重连。
2. GNSS 无定位时持续上报状态。
3. 本地缓存未发送消息。
4. 网络恢复后补发缓存消息。
5. 消息带 `seq`，服务端支持去重。
6. 服务端记录 `server_received_at`。
7. 设备上报 RSSI、网络制式、电池电压、充电状态、重启原因、错误码。
8. Web Dashboard 显示设备健康状态。
9. Web Dashboard 显示最近错误和重连次数。

Definition of Done：

- 外场连续运行 30 分钟，设备不死机。
- 人为制造短暂断网后，设备能自动恢复上报。
- 断网期间的数据可补发或至少能上报断网事件。
- Web Dashboard 能区分 no-fix、no-network、low-battery、device-error 等状态。
- 不看串口日志也能判断设备当前问题类型。

---

### R4：产品化演示版本

目标：从工程测试页面升级为可展示的产品原型。

实现内容：

1. Web Dashboard 有设备列表。
2. 每台设备有设备详情页。
3. 显示地图位置和历史轨迹。
4. 显示消息日志。
5. 显示命令历史与 ACK 状态。
6. 支持测试场次管理。
7. 支持导出外场测试报告。
8. 支持基础远程参数配置。
9. 支持多设备。
10. 提供最小部署文档。

Definition of Done：

- 不连接串口、不打开开发工具，只通过 Web Dashboard 即可完成一次产品演示。
- 能展示设备在线、定位、轨迹、命令、ACK、错误状态、测试报告。
- 能让非开发人员理解设备当前是否正常工作。

---

## 4. 最小通信协议建议

### 4.1 通信方式建议

P0 阶段可以根据现有代码选择 HTTP polling 或 MQTT，但目标产品化路线建议按以下原则设计：

- 设备上行：MQTT over TLS 或 HTTPS POST。
- 设备下行：MQTT subscribe 或 HTTPS command polling。
- Web 控制台：HTTPS + WebSocket。
- 服务端存储：SQLite 起步，后续可迁移 PostgreSQL。
- 服务端运行：VPS 上使用 systemd / docker compose 均可。
- 访问入口：优先使用 443 端口，避免暴露过多调试端口。

如果当前项目中已经存在 HTTP server，则 P0 可以先沿用 HTTP，避免过早重构。但必须保留 transport abstraction，后续可迁移 MQTT。

### 4.2 设备上行 telemetry

```json
{
  "protocol_version": "0.1",
  "device_id": "ego-link-p0-001",
  "fw_version": "0.1.0",
  "seq": 1024,
  "type": "telemetry",
  "device_timestamp": 1760000000,
  "test_run_id": "field-20260627-001",
  "payload": {
    "gnss": {
      "fix": true,
      "state": "fixed",
      "lat": 22.5431,
      "lon": 114.0579,
      "alt": 32.5,
      "speed_mps": 0.8,
      "satellites": 12,
      "hdop": 0.9
    },
    "power": {
      "battery_mv": 3920,
      "battery_percent": 76,
      "charging": false
    },
    "network": {
      "mode": "4g",
      "rssi": -73,
      "operator": "unknown",
      "reconnect_count": 2
    },
    "device": {
      "state": "field_test",
      "uptime_sec": 3600,
      "boot_reason": "power_on",
      "last_error": null
    }
  }
}
```

### 4.3 设备上行 heartbeat

```json
{
  "protocol_version": "0.1",
  "device_id": "ego-link-p0-001",
  "fw_version": "0.1.0",
  "seq": 1025,
  "type": "heartbeat",
  "device_timestamp": 1760000010,
  "payload": {
    "state": "online",
    "uptime_sec": 3610,
    "free_heap": 123456,
    "rssi": -75,
    "battery_mv": 3918
  }
}
```

### 4.4 服务端下行 command

```json
{
  "protocol_version": "0.1",
  "device_id": "ego-link-p0-001",
  "cmd_id": "cmd-0001",
  "type": "set_report_interval",
  "created_at": 1760000020,
  "payload": {
    "interval_ms": 5000
  }
}
```

### 4.5 设备上行 ACK

```json
{
  "protocol_version": "0.1",
  "device_id": "ego-link-p0-001",
  "fw_version": "0.1.0",
  "seq": 1026,
  "type": "ack",
  "cmd_id": "cmd-0001",
  "status": "ok",
  "message": "report interval updated",
  "device_timestamp": 1760000022
}
```

### 4.6 设备上行 error

```json
{
  "protocol_version": "0.1",
  "device_id": "ego-link-p0-001",
  "fw_version": "0.1.0",
  "seq": 1027,
  "type": "error",
  "device_timestamp": 1760000030,
  "payload": {
    "error_code": "GNSS_NO_FIX_TIMEOUT",
    "severity": "warning",
    "message": "GNSS no fix for 180 seconds",
    "recoverable": true
  }
}
```

---

## 5. API / Topic 设计建议

### 5.1 如果采用 HTTP

建议最小 API：

```text
POST /api/v1/devices/register
POST /api/v1/devices/{device_id}/heartbeat
POST /api/v1/devices/{device_id}/telemetry
POST /api/v1/devices/{device_id}/ack
POST /api/v1/devices/{device_id}/error
GET  /api/v1/devices/{device_id}/commands/poll
POST /api/v1/devices/{device_id}/commands/{cmd_id}/ack

GET  /api/v1/devices
GET  /api/v1/devices/{device_id}
GET  /api/v1/devices/{device_id}/telemetry/latest
GET  /api/v1/devices/{device_id}/telemetry/history
POST /api/v1/devices/{device_id}/commands
GET  /api/v1/devices/{device_id}/commands

GET  /api/v1/test-runs
POST /api/v1/test-runs
GET  /api/v1/test-runs/{test_run_id}/export

GET  /health
WS   /ws/dashboard
```

### 5.2 如果采用 MQTT

建议最小 topic：

```text
ego-link/v1/device/{device_id}/heartbeat
ego-link/v1/device/{device_id}/telemetry
ego-link/v1/device/{device_id}/ack
ego-link/v1/device/{device_id}/error
ego-link/v1/device/{device_id}/log

ego-link/v1/server/{device_id}/command
ego-link/v1/server/{device_id}/config
```

服务端应将 MQTT 消息落库，并通过 WebSocket 推送给 Web Dashboard。

---

## 6. Web Dashboard 最小字段

外场测试时，Web Dashboard 要替代串口监视器。因此至少显示以下字段。

### 6.1 设备概览

| 字段 | 说明 |
|---|---|
| device_id | 设备 ID |
| fw_version | 固件版本 |
| online_status | online / offline / stale |
| last_seen_at | 服务端最后收到消息时间 |
| device_state | booting / idle / field_test / error |
| last_error | 最近错误 |

### 6.2 GNSS 状态

| 字段 | 说明 |
|---|---|
| fix | 是否定位 |
| state | searching / fixed / lost / error |
| lat / lon | 经纬度 |
| alt | 海拔 |
| speed_mps | 速度 |
| satellites | 卫星数 |
| hdop | 水平精度因子 |
| last_fix_at | 最后定位时间 |

### 6.3 网络状态

| 字段 | 说明 |
|---|---|
| mode | Wi-Fi / 4G / Cat.1 / NB-IoT |
| rssi | 信号强度 |
| reconnect_count | 重连次数 |
| last_network_error | 最近网络错误 |

### 6.4 电源状态

| 字段 | 说明 |
|---|---|
| battery_mv | 电池电压 |
| battery_percent | 电量百分比，如可估算 |
| charging | 是否充电 |
| low_battery | 是否低电量 |

### 6.5 消息状态

| 字段 | 说明 |
|---|---|
| seq | 最近消息序号 |
| report_interval_ms | 上报间隔 |
| pending_commands | 待执行命令数 |
| last_ack | 最近 ACK |
| dropped_or_duplicate | 重复或丢弃消息统计 |

---

## 7. USB-Free 外场测试规范

### 7.1 强制规则

1. USB 只能用于烧录、临时调试和失败后导出日志。
2. 正式验收时，设备必须断开 USB。
3. 外场测试证据必须来自 VPS、Web Dashboard、服务端日志、导出的测试报告。
4. 串口日志不能作为唯一验收证据。
5. 固件必须在无串口连接情况下仍然能自启动、自联网、自上报。

### 7.2 外场测试前检查清单

```text
[ ] VPS 服务已启动
[ ] VPS 公网 IP / 域名可访问
[ ] Web Dashboard 可访问
[ ] 设备 token / secret 已配置
[ ] 固件版本已记录
[ ] 电池电量充足
[ ] SIM 卡 / 网络连接正常
[ ] GNSS 天线连接正常
[ ] 设备断开 USB 后能独立供电
[ ] PC Simulator 已通过 R0 验证
[ ] 真实设备已通过 R1 验证
[ ] 已创建 test_run_id
```

### 7.3 外场测试过程

```text
1. 在 Web Dashboard 创建测试场次。
2. 启动设备，断开 USB。
3. 将设备带到室外开阔区域。
4. 观察 Web Dashboard 中 boot / heartbeat / gnss state。
5. 等待 GNSS 从 searching 进入 fixed。
6. 进行步行或短距离移动。
7. 观察位置点是否持续更新。
8. 在 Web Dashboard 下发 set_report_interval 命令。
9. 确认设备 ACK。
10. 结束测试并导出测试报告。
```

### 7.4 失败诊断规则

如果 Web Dashboard 没有位置数据，必须能区分以下情况：

| 情况 | Dashboard 应显示 |
|---|---|
| 设备未上线 | offline / never_seen |
| 网络不可用 | no_network / reconnecting |
| 设备在线但 GNSS 未定位 | gnss_searching / fix=false |
| GNSS 弱信号 | low_satellites / high_hdop |
| 电池不足 | low_battery |
| 固件异常重启 | reboot_detected / boot_reason |
| 协议错误 | protocol_error |
| 服务端异常 | server_error |

---

## 8. 安全与部署最低要求

### 8.1 鉴权

P0 最低要求：

- 每台设备有唯一 `device_id`。
- 每台设备有 `device_secret` 或 token。
- token 不得提交到 Git。
- 仓库只提供 `.env.example`。
- 服务端校验设备 token。

建议请求头：

```text
Authorization: Bearer <device_token>
```

或 MQTT username/password / client certificate。

### 8.2 端口

建议产品化入口：

```text
443  HTTPS / Web Dashboard / API / WebSocket
8883 MQTT over TLS，可选
22   SSH，仅限管理 IP 或密钥登录
```

开发阶段如使用 1883 / 8000 / 8080，必须在文档中标注为开发端口，不作为长期公网暴露方案。

### 8.3 日志与数据

服务端至少保存：

- device 表
- telemetry 表
- command 表
- ack 表
- error 表
- test_run 表
- event_log 表

P0 阶段可用 SQLite。若进入多设备和长期测试，再迁移 PostgreSQL。

---

## 9. 给 Codex 的首个任务：ENG-002

### 9.1 任务名称

```text
ENG-002：建立 Ego Link P0 的 VPS Message-First、USB-Free、Demo-Driven 开发流程文档
```

### 9.2 任务目标

本轮先做工程流程和接口规范，不急于继续增加复杂业务功能。

目标：

1. 明确 Ego Link P0 以后按公网 VPS 消息中枢架构开发。
2. 明确 USB 不作为正式运行链路。
3. 明确 Server-Web / Firmware / Protocol 三条版本轨道。
4. 明确 R0-R4 可演示版本路线。
5. 明确通信协议、Web Dashboard 字段、外场测试规范。
6. 明确后续任何功能任务都必须绑定版本号、边界、验收标准。

### 9.3 建议新增或更新文档

请在项目中新增或更新以下文档：

```text
docs/development/DEV_FLOW.md
docs/development/VPS_MESSAGE_HUB.md
docs/development/PROTOCOL.md
docs/development/FIELD_TEST.md
docs/current/ROADMAP_EGOLINK_P0.md
```

如项目已有类似文档，请优先合并，不要重复制造冲突文档。

### 9.4 DEV_FLOW.md 应包含

```text
1. Walking Skeleton 开发原则
2. USB-Free 原则
3. VPS Message-First 原则
4. Demo-Driven 原则
5. Contract-First 原则
6. Server-Web / Firmware / Protocol 三轨版本化规则
7. R0-R4 版本路线
8. 每个版本的 Definition of Done
9. 禁止随意跨层修改的规则
10. 后续任务命名规范
```

### 9.5 VPS_MESSAGE_HUB.md 应包含

```text
1. 公网 VPS 作为默认消息中枢
2. 设备、PC Simulator、Web Dashboard 与 VPS 的连接关系
3. VPS 的职责边界
4. VPS 不承载核心本地 AI 逻辑的原则
5. HTTP / MQTT 两种实现路径
6. 最小 API 或 topic 设计
7. 部署端口建议
8. 鉴权和 .env.example 要求
9. 日志和数据库建议
```

### 9.6 PROTOCOL.md 应包含

```text
1. protocol_version 规则
2. device_id / fw_version / seq / device_timestamp / server_received_at
3. telemetry 消息结构
4. heartbeat 消息结构
5. command 消息结构
6. ack 消息结构
7. error 消息结构
8. GNSS 字段规范
9. power 字段规范
10. network 字段规范
11. device state 字段规范
12. 错误码规范
13. 协议兼容规则
```

### 9.7 FIELD_TEST.md 应包含

```text
1. USB-Free 外场测试原则
2. 测试前检查清单
3. R1 室内真实设备无 GNSS 测试步骤
4. R2 室外 GNSS 测试步骤
5. R3 弱网/断网/重连测试步骤
6. 失败诊断流程
7. Web Dashboard 必须显示的状态字段
8. 测试报告导出字段
```

### 9.8 ROADMAP_EGOLINK_P0.md 应包含

```text
R0：VPS + PC Simulator 纯模拟闭环
R1：真实硬件无 GNSS 闭环
R2：真实 GNSS 外场闭环
R3：外场可靠性版本
R4：产品化演示版本

每个版本都要写：
- 目标
- 输入
- 输出
- 涉及模块
- 不允许改动的范围
- Definition of Done
```

### 9.9 本轮禁止事项

```text
1. 不要重构 firmware 业务逻辑。
2. 不要重构 pc_simulator 业务逻辑。
3. 不要重构 web/server 业务逻辑。
4. 不要新增复杂 AI 功能。
5. 不要加入云端大模型作为核心逻辑。
6. 不要把 USB 串口作为正式验收链路。
7. 不要引入多个互相冲突的协议版本。
8. 不要随意改目录结构。
9. 不要提交真实 VPS 密钥、token、IP 白名单等敏感信息。
```

### 9.10 可以改动的范围

```text
允许新增：
- docs/development/DEV_FLOW.md
- docs/development/VPS_MESSAGE_HUB.md
- docs/development/PROTOCOL.md
- docs/development/FIELD_TEST.md
- docs/current/ROADMAP_EGOLINK_P0.md

允许小幅更新：
- docs/current/STATUS.md
- docs/tasks/TASK_TREE.md
- README.md 中指向这些文档的索引链接

如发现已有文档冲突：
- 优先在文档中标注“本文件为 Ego Link P0 后续开发流程基准”。
- 不删除旧文档，除非项目已有明确归档规则。
```

---

## 10. 后续任务写法规范

以后不要用模糊任务，例如：

```text
把 GNSS 做好一点。
把 Web 完善一下。
让设备能外场测试。
```

必须改成版本化任务。

### 示例 1：Server-Web 任务

```text
任务：SERVER-001 实现 VPS 消息服务最小闭环

目标：
在公网 VPS 上运行消息服务，支持 PC Simulator 注册、heartbeat、telemetry、command、ack。

允许改动：
- server/
- pc_simulator/
- docs/development/VPS_MESSAGE_HUB.md
- docs/development/PROTOCOL.md，如发现协议示例需要补充

禁止改动：
- firmware/ 业务逻辑
- hardware/ 相关文件
- Web 大规模 UI 重构

验收标准：
1. PC Simulator 可连接 VPS。
2. Web 或 API 可看到模拟设备在线。
3. 模拟设备可上报模拟 GNSS。
4. 服务端可创建 command。
5. 模拟设备可返回 ACK。
6. 全部消息落库或写入 event log。
```

### 示例 2：Web 任务

```text
任务：WEB-001 实现设备状态 Dashboard

目标：
Web Dashboard 显示设备在线状态、最后坐标、最后上报时间、GNSS fix、卫星数、电池电压、最近错误。

允许改动：
- web/
- server/ 中 Dashboard API 或 WebSocket 推送相关代码

禁止改动：
- firmware/
- pc_simulator 的协议字段名
- PROTOCOL.md 中既有字段语义，除非先提出协议变更说明

验收标准：
1. PC Simulator 上报数据后 Web 能实时或准实时刷新。
2. offline / online / stale 状态可区分。
3. no-fix 和 fixed 可区分。
4. 页面可看到最近一条 telemetry 原始摘要。
```

### 示例 3：Firmware 任务

```text
任务：FW-001 实现真实设备 USB-Free heartbeat 上报

目标：
真实硬件断开 USB 后，通过 4G / Wi-Fi 连接 VPS，周期性上报 heartbeat。

允许改动：
- firmware/
- docs/development/FIELD_TEST.md 中对应测试步骤

禁止改动：
- server API 字段名
- web 主结构
- protocol_version，除非先更新 PROTOCOL.md

验收标准：
1. 设备烧录后断开 USB。
2. 设备独立供电运行。
3. VPS 收到 boot 事件。
4. VPS 每 10 秒左右收到 heartbeat。
5. Web Dashboard 显示真实设备 online。
6. 验收证据来自 Web Dashboard 和 VPS 日志，不来自串口日志。
```

### 示例 4：GNSS 外场任务

```text
任务：FW-002 实现真实 GNSS 上报与 USB-Free 外场测试

目标：
真实设备在室外获取 GNSS 定位，并通过 VPS 上报到 Web Dashboard。

允许改动：
- firmware/ 中 GNSS 采集与 telemetry 组包逻辑
- web/ 中 GNSS 状态展示
- server/ 中 telemetry 存储和历史查询
- docs/development/FIELD_TEST.md

禁止改动：
- 无关 AI 功能
- 无关 UI 大改
- 协议字段破坏性重命名

验收标准：
1. 设备断开 USB 后到室外运行。
2. Web Dashboard 显示 gnss.state 从 searching 到 fixed。
3. Web Dashboard 显示 lat/lon/satellites/hdop。
4. 步行测试后能看到位置点变化。
5. 定位失败时显示 fix=false 和原因字段，不允许沉默无数据。
```

---

## 11. 本项目当前应立即执行的顺序

建议后续按以下顺序推进：

```text
ENG-002：开发流程与文档基准
    ↓
PROTO-001：最小通信协议冻结
    ↓
SERVER-001：VPS 消息系统最小闭环
    ↓
WEB-001：设备状态 Dashboard
    ↓
SIM-001：PC Simulator 连接 VPS 完整闭环
    ↓
FW-001：真实硬件 USB-Free heartbeat 上报
    ↓
FW-002：真实 GNSS 上报
    ↓
FIELD-001：USB-Free 外场测试
    ↓
RELIABILITY-001：断网重连、本地缓存、状态诊断
    ↓
DEMO-001：产品化演示 Dashboard 和测试报告导出
```

---

## 12. 项目原则写入文档首页

建议将以下原则写入 Ego Link P0 的开发文档首页：

> **Ego Link P0 采用 USB-Free、VPS Message-First、Demo-Driven 的版本化开发流程：先建立设备—公网 VPS 消息系统—Web 控制台的可演示闭环，再按固件、协议、Server-Web 三条轨道逐步增强。USB 仅用于烧录和临时调试，不作为正式测试和验收链路。**

---

## 13. Codex 执行提示词

可以直接把下面这段发给 Codex：

```text
请执行 ENG-002：建立 Ego Link P0 的 VPS Message-First、USB-Free、Demo-Driven 开发流程文档。

背景：
本项目已有公网 VPS 和公网 IP，因此后续不再按临时内网、USB 串口、电脑直连设备的方式组织开发。Ego Link P0 应按最接近产品实际运行状态的架构推进：真实设备、PC Simulator、Web Dashboard 都连接公网 VPS；VPS 作为消息中枢、命令队列、状态观测和外场测试记录中心；USB 只用于烧录和临时调试，不能作为正式运行和验收链路。

本轮目标：
1. 不新增复杂业务功能。
2. 不重构 firmware、pc_simulator、web、server 的业务实现。
3. 新增或更新工程文档，明确后续开发按 USB-Free、VPS Message-First、Demo-Driven、Contract-First 的 Walking Skeleton 流程推进。
4. 明确 Server-Web / Firmware / Protocol 三条版本轨道。
5. 明确 R0-R4 可演示版本路线。
6. 明确最小通信协议、Web Dashboard 字段、USB-Free 外场测试规范。
7. 明确后续任务必须使用版本号、允许改动范围、禁止改动范围、Definition of Done。

请新增或更新以下文档：
- docs/development/DEV_FLOW.md
- docs/development/VPS_MESSAGE_HUB.md
- docs/development/PROTOCOL.md
- docs/development/FIELD_TEST.md
- docs/current/ROADMAP_EGOLINK_P0.md

如已有类似文档，请合并，不要制造冲突文档。

DEV_FLOW.md 需要包含：
- Walking Skeleton 开发原则
- USB-Free 原则
- VPS Message-First 原则
- Demo-Driven 原则
- Contract-First 原则
- Server-Web / Firmware / Protocol 三轨版本化规则
- R0-R4 版本路线
- 每个版本的 Definition of Done
- 禁止随意跨层修改的规则
- 后续任务命名规范

VPS_MESSAGE_HUB.md 需要包含：
- 公网 VPS 作为默认消息中枢
- 设备、PC Simulator、Web Dashboard 与 VPS 的连接关系
- VPS 的职责边界
- VPS 不承载核心本地 AI 逻辑的原则
- HTTP / MQTT 两种实现路径
- 最小 API 或 topic 设计
- 部署端口建议
- 鉴权和 .env.example 要求
- 日志和数据库建议

PROTOCOL.md 需要包含：
- protocol_version 规则
- device_id / fw_version / seq / device_timestamp / server_received_at
- telemetry 消息结构
- heartbeat 消息结构
- command 消息结构
- ack 消息结构
- error 消息结构
- GNSS 字段规范
- power 字段规范
- network 字段规范
- device state 字段规范
- 错误码规范
- 协议兼容规则

FIELD_TEST.md 需要包含：
- USB-Free 外场测试原则
- 测试前检查清单
- R1 室内真实设备无 GNSS 测试步骤
- R2 室外 GNSS 测试步骤
- R3 弱网/断网/重连测试步骤
- 失败诊断流程
- Web Dashboard 必须显示的状态字段
- 测试报告导出字段

ROADMAP_EGOLINK_P0.md 需要包含：
- R0：VPS + PC Simulator 纯模拟闭环
- R1：真实硬件无 GNSS 闭环
- R2：真实 GNSS 外场闭环
- R3：外场可靠性版本
- R4：产品化演示版本

每个版本都要写：
- 目标
- 输入
- 输出
- 涉及模块
- 不允许改动的范围
- Definition of Done

本轮禁止事项：
- 不要重构 firmware 业务逻辑。
- 不要重构 pc_simulator 业务逻辑。
- 不要重构 web/server 业务逻辑。
- 不要新增复杂 AI 功能。
- 不要加入云端大模型作为核心逻辑。
- 不要把 USB 串口作为正式验收链路。
- 不要引入多个互相冲突的协议版本。
- 不要随意改目录结构。
- 不要提交真实 VPS 密钥、token、IP 白名单等敏感信息。

允许小幅更新：
- docs/current/STATUS.md
- docs/tasks/TASK_TREE.md
- README.md 中指向这些文档的索引链接

完成后请输出：
1. 新增/修改文件清单。
2. 每个文件的核心内容摘要。
3. 是否发现现有文档冲突。
4. 下一步建议任务：PROTO-001、SERVER-001、WEB-001、SIM-001、FW-001。
```

---

## 14. 判断标准

ENG-002 完成后，项目应达到以下状态：

1. Codex 后续不会再根据临时口头需求随意跨层修改。
2. 每个开发任务都能归属到 Server-Web、Firmware、Protocol 三条轨道之一。
3. 每个版本都必须有可演示闭环。
4. VPS 是默认消息中枢，不再讨论临时内网替代方案。
5. USB 不再是运行依赖。
6. 外场测试从一开始就有 Web Dashboard 和服务端日志支撑。
7. GNSS 定位测试能按真实产品链路推进。

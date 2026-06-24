# EGO Link P0 工程开发上下文

> 本文档用于保存到 Codex 项目上下文。当前目标不是完整 EGO Base，也不是最终量产硬件，而是在电脑开发桥接环境下，先把 Ego Link 随身端感知、通信扩展、事件路由和安全陪伴最小闭环跑通。
>
> 2026-06-24 更新：当前 P0 实现形态明确为 **双开发板 + PC 中继的集成验证架构**。AMOLED 板是 `wearable_node` 可穿戴应用主节点；SIM7670G 板是 `connectivity_node` 通信、定位和摄像头扩展节点；PC 是开发期 Bridge、观察和回放工具，不是正式 Ego Base，也不能成为产品依赖。详细架构见 `docs/architecture/DUAL_BOARD_PC_BRIDGE_ARCHITECTURE.md`，产品迁移路线见 `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`。

---

## 0. 硬件更正与项目边界

### 0.1 当前硬件

当前 Ego Link P0 使用双开发板分别连接 PC：

- **ESP32-S3-Touch-AMOLED-2.06**：当前 `wearable_node`，负责 QMI8658 IMU、双麦克风、屏幕、触摸、扬声器、MotionNet / AudioGate 和用户交互；
- **微雪 ESP32-S3-SIM7670G-4G 开发板**：当前 `connectivity_node`，负责 SIM7670G 4G、GNSS、摄像头、TF 卡、缓存和通信能力验证；
- **PC Development Bridge**：开发期串口中继、统一事件总线、ContextRouter、Safety Kernel、数据记录、时间同步、事件回放和调试 Dashboard。

注意：

- 本项目当前不是 ESP32-S3-A7670E-4G，蜂窝模块不是 A7670E；
- SIM7670G 开发板是通信扩展节点和测试模组，不应被固化为最终主控；
- AMOLED 板是当前可穿戴应用主节点，但最终产品目标也不是两块 ESP32 开发板，而是单低功耗主控 / AI MCU + 蜂窝模组 + 传感器。

### 0.2 当前工程范围

当前阶段聚焦 **Ego Link P0 Firmware + PC Development Bridge + 真实数据采集闭环**。

暂不开发：

- 不开发正式 EGO Base；
- 不接入 Orange Pi 5 Plus；
- 不接入本地大模型；
- 不做长期记忆；
- 不做真实语音唤醒芯片；
- 不做真实报警、真实拨号或正式联系人联动；
- 不做手机 App；
- 不做云端服务；
- 不做外壳；
- 不做最终功耗优化。

当前要做的是：

- 两块开发板通过 USB 同时连接电脑；
- 每块板启动后发送版本化 `hello`，PC 根据 `device_id` 和 `role` 识别设备，不写死 COM 口；
- 两块板和 PC 使用同一套版本化消息协议；
- AMOLED 板采集 QMI8658 原始六轴数据、验证麦克风链路、显示询问并接收用户确认；
- SIM7670G 板验证 4G、GNSS、摄像头能力状态，并接收 `request_location`、`capture_image` 等命令；
- PC Development Bridge 运行 ContextRouter、Safety Kernel、数据记录、时间同步、事件回放和调试 Dashboard；
- 允许 Mock 与真实驱动并存，但必须标明数据来源；
- 跑通安全陪伴最小闭环：运动候选 → 用户确认 → 请求定位/证据 → 完整事件记录。

---

## 1. 产品定位

Ego Link 是 EGO 项目的随身设备原型，不是独立大脑，也不是小型手机。

它的定位是：

> Ego Link 是 EGO 的随身感知节点、低功耗安全前哨和远程通信入口。

P0 阶段暂时不依赖正式 EGO Base，而是通过 PC Development Bridge 验证随身端主节点、通信扩展节点和安全事件闭环。PC 仅是开发期桥接和观察工具，长期复杂能力仍由本地 Ego Base 协同完成。

---

## 2. P0 总体架构

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

P0 阶段仍必须坚持 Mock-first 和抽象接口原则。业务层不能直接绑定 USB、COM 口、Wi-Fi、SIM7670G、GNSS、摄像头、IMU 或唤醒芯片。所有外设能力都必须通过抽象接口和版本化消息协议访问。

---

## 3. 固件技术路线

### 3.1 开发框架

推荐使用：

- ESP-IDF，不建议 Arduino 作为主线；
- C / C++；
- FreeRTOS task；
- esp-mqtt；
- cJSON；
- NVS 保存配置；
- SPIFFS / FATFS / LittleFS 保存离线事件队列；
- UART 日志；
- 后续再加入 OTA、加密、真实蜂窝通信。

### 3.2 固件核心原则

1. **业务层只关心事件，不关心底层硬件。**
2. **通信链路必须可替换。** 当前 Wi-Fi 模拟 4G，后续替换为 SIM7670G AT / PPP。
3. **定位源必须可替换。** 当前 Mock GNSS，后续替换为 SIM7670G GNSS。
4. **唤醒源必须可替换。** 当前按键 / 串口模拟，后续替换为独立唤醒芯片或本地语音模型。
5. **所有上报事件必须有 seq。** 便于离线缓存、恢复补传和去重。
6. **紧急事件优先级最高。** SOS 不依赖模型判断。
7. **P0 不追求低功耗极限，但必须预留电源状态机。**

---

## 4. 固件目录建议

```text
ego-link-p0/
├─ firmware/
│  ├─ CMakeLists.txt
│  ├─ sdkconfig.defaults
│  ├─ main/
│  │  ├─ app_main.c
│  │  ├─ app_config.h
│  │  ├─ app_state_machine.c
│  │  ├─ app_state_machine.h
│  │  ├─ app_event_bus.c
│  │  ├─ app_event_bus.h
│  │  ├─ app_protocol.c
│  │  ├─ app_protocol.h
│  │  ├─ app_policy.c
│  │  ├─ app_policy.h
│  │  ├─ app_storage.c
│  │  ├─ app_storage.h
│  │  ├─ app_serial_cli.c
│  │  └─ app_serial_cli.h
│  │
│  ├─ components/
│  │  ├─ transport/
│  │  │  ├─ link_transport.h
│  │  │  ├─ wifi_mock_transport.c
│  │  │  ├─ wifi_mock_transport.h
│  │  │  ├─ sim7670_transport_stub.c
│  │  │  └─ sim7670_transport_stub.h
│  │  │
│  │  ├─ modem/
│  │  │  ├─ modem_driver.h
│  │  │  ├─ mock_modem_driver.c
│  │  │  ├─ mock_modem_driver.h
│  │  │  ├─ sim7670_at_driver_stub.c
│  │  │  └─ sim7670_at_driver_stub.h
│  │  │
│  │  ├─ gnss/
│  │  │  ├─ gnss_driver.h
│  │  │  ├─ mock_gnss_driver.c
│  │  │  ├─ mock_gnss_driver.h
│  │  │  ├─ sim7670_gnss_driver_stub.c
│  │  │  └─ sim7670_gnss_driver_stub.h
│  │  │
│  │  ├─ wake/
│  │  │  ├─ wake_driver.h
│  │  │  ├─ mock_wake_driver.c
│  │  │  ├─ mock_wake_driver.h
│  │  │  ├─ button_wake_driver.c
│  │  │  └─ button_wake_driver.h
│  │  │
│  │  └─ power/
│  │     ├─ power_driver.h
│  │     ├─ mock_power_driver.c
│  │     └─ mock_power_driver.h
│  │
│  └─ partitions.csv
│
├─ pc_simulator/
│  ├─ README.md
│  ├─ requirements.txt
│  ├─ docker-compose.yml
│  ├─ app.py
│  ├─ mqtt_worker.py
│  ├─ dashboard.py
│  ├─ policy_store.py
│  ├─ event_store.py
│  └─ sample_policy_child_safety.json
│
├─ docs/
│  ├─ protocol.md
│  ├─ state_machine.md
│  ├─ hardware_notes.md
│  └─ sim7670_future_driver.md
│
└─ README.md
```

---

## 5. 抽象接口设计

### 5.1 LinkTransport

通信链路抽象。当前实现 Wi-Fi + MQTT，命名上仍然代表“链路”，不要把业务层写死为 Wi-Fi。

```c
typedef enum {
    LINK_STATE_OFFLINE = 0,
    LINK_STATE_CONNECTING,
    LINK_STATE_CONNECTED,
    LINK_STATE_ERROR
} link_state_t;

typedef struct {
    esp_err_t (*init)(void);
    esp_err_t (*connect)(void);
    esp_err_t (*disconnect)(void);
    link_state_t (*get_state)(void);
    esp_err_t (*publish)(const char *topic, const char *payload, int qos);
    esp_err_t (*subscribe)(const char *topic, int qos);
} link_transport_t;
```

当前实现：

- `wifi_mock_transport`

后续实现：

- `sim7670_at_mqtt_transport`
- `sim7670_ppp_transport`

### 5.2 ModemDriver

调制解调器抽象。P0 只模拟状态。

```c
typedef enum {
    MODEM_OFF = 0,
    MODEM_BOOTING,
    MODEM_REGISTERED,
    MODEM_DATA_READY,
    MODEM_ERROR
} modem_state_t;

typedef struct {
    esp_err_t (*init)(void);
    esp_err_t (*power_on)(void);
    esp_err_t (*power_off)(void);
    modem_state_t (*get_state)(void);
    int (*get_rssi)(void);
    esp_err_t (*dial_call)(const char *number);
    esp_err_t (*hangup_call)(void);
} modem_driver_t;
```

当前实现：

- `mock_modem_driver`

后续实现：

- `sim7670_at_driver`

### 5.3 GnssDriver

定位抽象。

```c
typedef struct {
    double lat;
    double lon;
    float speed_mps;
    float accuracy_m;
    int satellites;
    bool valid;
    int64_t ts_ms;
} gnss_fix_t;

typedef struct {
    esp_err_t (*init)(void);
    esp_err_t (*start)(void);
    esp_err_t (*stop)(void);
    esp_err_t (*get_fix)(gnss_fix_t *fix);
} gnss_driver_t;
```

当前实现：

- `mock_gnss_driver`：固定轨迹 + 随机扰动

后续实现：

- `sim7670_gnss_driver`

### 5.4 WakeDriver

唤醒抽象。

```c
typedef enum {
    WAKE_SOURCE_BUTTON = 0,
    WAKE_SOURCE_SERIAL_CLI,
    WAKE_SOURCE_TIMER,
    WAKE_SOURCE_AUDIO_CHIP,
    WAKE_SOURCE_REMOTE_CMD
} wake_source_t;

typedef struct {
    wake_source_t source;
    float confidence;
    char keyword[32];
    int64_t ts_ms;
} wake_event_t;

typedef struct {
    esp_err_t (*init)(void);
    esp_err_t (*poll)(wake_event_t *event, bool *has_event);
} wake_driver_t;
```

当前实现：

- `mock_wake_driver`
- `button_wake_driver`
- `serial_cli_wake`

后续实现：

- 独立语音唤醒芯片驱动
- 本地 TinyML 唤醒模型

---

## 6. 设备状态机

P0 固件必须实现明确状态机。

```text
BOOT
  ↓
CONFIG_LOAD
  ↓
NETWORK_CONNECTING
  ↓
ONLINE_IDLE
  ↓
GUARDING
  ├─ HEARTBEAT_TIMER
  ├─ LOCATION_TIMER
  ├─ WAKE_EVENT
  ├─ SOS_EVENT
  ├─ POLICY_UPDATE
  └─ NETWORK_LOST
```

异常状态：

```text
NETWORK_LOST
  ↓
STORE_AND_FORWARD
  ↓
RECONNECTING
  ↓
FLUSH_QUEUE
  ↓
GUARDING
```

紧急状态：

```text
SOS_TRIGGERED
  ↓
GET_LAST_LOCATION
  ↓
UPLOAD_CRITICAL_EVENT
  ↓
SIMULATE_CALL_REQUEST
  ↓
WAIT_ACK_OR_REPEAT
  ↓
RECOVERY
```

---

## 7. MQTT Topic 规范

### 7.1 上行 Topic

```text
ego/link/{device_id}/status
ego/link/{device_id}/event
ego/link/{device_id}/log
ego/link/{device_id}/ack
```

### 7.2 下行 Topic

```text
ego/link/{device_id}/cmd
ego/link/{device_id}/policy
ego/link/{device_id}/config
```

---

## 8. JSON 消息格式

### 8.1 心跳消息

```json
{
  "device_id": "ego-link-001",
  "ts": 1710000000,
  "seq": 1,
  "fw_version": "0.1.0",
  "hw_target": "waveshare_esp32s3_sim7670g_4g",
  "battery": 87,
  "charging": false,
  "link_type": "mock_4g_over_wifi",
  "rssi": -61,
  "modem_state": "mock_data_ready",
  "gnss_state": "mock_fix",
  "guard_mode": "child_safety",
  "queue_size": 0
}
```

### 8.2 定位上报

```json
{
  "device_id": "ego-link-001",
  "ts": 1710000010,
  "seq": 2,
  "event_type": "location_report",
  "priority": "normal",
  "source": "mock_gnss",
  "lat": 22.543096,
  "lon": 114.057865,
  "speed_mps": 1.2,
  "accuracy_m": 8.5,
  "battery": 87
}
```

### 8.3 SOS 事件

```json
{
  "device_id": "ego-link-001",
  "ts": 1710000020,
  "seq": 3,
  "event_type": "sos_pressed",
  "priority": "critical",
  "source": "button_or_cli",
  "lat": 22.543096,
  "lon": 114.057865,
  "accuracy_m": 8.5,
  "battery": 86
}
```

### 8.4 模拟唤醒事件

```json
{
  "device_id": "ego-link-001",
  "ts": 1710000030,
  "seq": 4,
  "event_type": "wake_detected",
  "priority": "normal",
  "source": "mock_wake",
  "keyword": "小E",
  "confidence": 0.92,
  "battery": 86
}
```

### 8.5 下发命令

```json
{
  "cmd_id": "cmd-0001",
  "cmd": "play_prompt",
  "text": "你已经离开安全区域，请确认是否需要联系家长。",
  "level": "warning",
  "expire_sec": 60
}
```

### 8.6 策略包

```json
{
  "policy_id": "child_safety_v0",
  "mode": "child_safety",
  "heartbeat_interval_sec": 10,
  "location_interval_sec": 30,
  "safe_zones": [
    {
      "name": "home",
      "lat": 22.543096,
      "lon": 114.057865,
      "radius_m": 300
    }
  ],
  "rules": [
    {
      "when": "outside_safe_zone",
      "action": "prompt_and_report"
    },
    {
      "when": "sos_pressed",
      "action": "critical_alert"
    },
    {
      "when": "wake_detected",
      "action": "wait_for_command"
    }
  ]
}
```

---

## 9. PC Development Bridge / PC Simulator 设计

当前电脑承担开发期 Bridge、观察、记录和回放，同时保留 PC Simulator 能力用于 MQTT / Dashboard / 规则基线测试。它不命名为正式 EGO Base，也不能成为产品依赖。

### 9.1 PC Bridge / Simulator 组成

```text
pc_simulator/
├─ Board Bridge：自动识别 wearable_node / connectivity_node
├─ Serial Relay：中继双 USB 串口消息
├─ Event Bus：归一化 hello、motion_event、user_confirmation、location_report 和 command ACK
├─ ContextRouter / Safety Kernel：P0 规则基线
├─ MQTT Broker：Mosquitto
├─ MQTT Worker：订阅设备 status/event/log/ack
├─ FastAPI / Flask：提供本地 HTTP 页面和 API
├─ SQLite / JSONL：记录事件和 session
├─ Session Replay：把记录脱离开发板重新喂给 ContextRouter
├─ Dashboard：显示设备在线、电量、位置、事件和双板状态
├─ Command Console：向设备下发命令
└─ Policy Manager：下发策略包
```

### 9.2 PC Dashboard 最小页面

显示：

- Device ID；
- 在线 / 离线；
- 最近心跳时间；
- 电量；
- 当前模式；
- 最近位置；
- 最近事件列表；
- 离线队列长度；
- `wearable_node` / `connectivity_node` 在线状态；
- 当前 session 记录状态；
- 手动下发按钮：
  - request_location；
  - capture_image；
  - ask_user；
  - play_prompt；
  - set_policy；
  - simulate_call；
  - reboot_device。

---

## 10. 串口 CLI

ESP32-S3 固件必须提供串口调试命令，方便无外设情况下模拟事件。

建议命令：

```text
help
status
sos
wake
loc
loc set 22.543096 114.057865
net down
net up
battery 20
policy show
queue show
queue clear
reboot
```

用途：

- `sos`：模拟 SOS；
- `wake`：模拟语音唤醒；
- `loc`：立即上报一次定位；
- `net down`：模拟网络断开；
- `net up`：恢复网络并补传；
- `battery 20`：模拟低电量事件。

---

## 11. 任务拆分

### Sprint 0：工程初始化

- 创建 ESP-IDF 工程；
- 创建 PC Simulator 工程；
- 确定设备 ID、MQTT topic、JSON schema；
- 完成 README 和运行说明。

### Sprint 1：设备上线与心跳

- ESP32-S3 连接 Wi-Fi；
- 连接本地 Mosquitto；
- 发布 status 心跳；
- PC Simulator 显示设备在线。

验收：设备上电 10 秒内出现在 Dashboard。

### Sprint 2：Mock GNSS 与定位上报

- 实现 MockGnssDriver；
- 支持固定轨迹；
- 支持随机扰动；
- 支持串口设置坐标；
- 周期上报 location_report。

验收：Dashboard 可以看到位置持续变化。

### Sprint 3：SOS 与模拟唤醒

- 实现按键/串口 SOS；
- 实现 mock wake；
- SOS 事件 priority=critical；
- PC 端收到 SOS 后自动下发 simulate_call 或 play_prompt。

验收：触发 SOS 后 2 秒内 PC Dashboard 显示 Critical 事件。

### Sprint 4：策略包

- PC 端下发 child_safety 策略；
- ESP32-S3 保存策略；
- 修改心跳间隔和定位间隔；
- 简单判断是否离开安全区。

验收：修改策略后设备行为发生变化。

### Sprint 5：离线缓存与恢复补传

- 实现本地事件队列；
- 网络断开时事件入队；
- 网络恢复后按 seq 顺序补传；
- PC 端按 seq 去重。

验收：断网 2 分钟产生的事件，恢复后全部补传，顺序正确，不重复。

### Sprint 6：SIM7670G 扩展节点能力桩

- 建立 sim7670_at_driver_stub；
- 建立 sim7670_gnss_driver_stub；
- 文档记录后续 AT 指令接入点；
- 通过 `connectivity_node` 上报 4G、GNSS、摄像头能力状态；
- 支持 `request_location`、`capture_image` 等命令的 Mock / Stub ACK；
- P0-B 再逐步替换为真实 4G、GNSS 和摄像头证据。

验收：业务层不需要修改即可从 Mock / Stub 切换到真实驱动，并且所有记录都能区分 Mock、Stub 和真实硬件来源。

---

## 12. P0 明确不做的事情

P0 不做：

- 不做真实报警、真实拨号或正式联系人联动；
- 不做完整语音 ASR；
- 不做本地 LLM；
- 不接正式 EGO Base；
- 不把 PC 固化为产品依赖；
- 不把 SIM7670G 开发板固化为最终主控；
- 不做手机 App；
- 不做云端服务；
- 不做外壳；
- 不做最终功耗优化；
- 当前不要求板间 UART 直连。

P0-A 可以使用 Mock / Stub 跑通双板接入、统一协议、PC Bridge 和 ContextRouter 骨架。P0-B 开始接入真实 IMU、声音、GNSS、4G 和摄像头，建立真实数据集。Mock 与真实驱动可以并存，但必须在消息和记录中明确标记来源。

原因：P0 的核心目标是双板集成验证、真实数据采集基础和安全事件闭环，而不是冻结最终硬件或完成正式产品服务。

---

## 13. SIM7670G 扩展节点接入路线

SIM7670G 当前属于 `connectivity_node`，用于通信、定位、摄像头和缓存能力验证，不是最终主控结论。P0-A 允许 Stub / Mock，P0-B 开始接真实能力。

### 13.1 路线 A：SIM7670G AT MQTT

ESP32-S3 通过 UART 控制 SIM7670G，使用模块内置 AT 指令完成 MQTT 连接、发布、订阅。

优点：

- 上手较快；
- 适合 IoT 事件上报；
- ESP32-S3 不需要完整蜂窝网络协议栈。

缺点：

- 受模块 AT 命令限制；
- 调试复杂；
- 异常处理需要大量状态机。

### 13.2 路线 B：SIM7670G PPP

ESP32-S3 通过 PPP 获得 IP 网络，再使用 ESP-IDF 的 MQTT/HTTP 客户端。

优点：

- 上层网络代码统一；
- 更接近普通 TCP/IP；
- 长期扩展性更好。

缺点：

- P0 阶段不建议直接做；
- 调试链路更长；
- 功耗和稳定性要重点验证。

### 13.3 建议顺序

先完成双板 USB + PC Bridge 的 P0-A 闭环，再在 `connectivity_node` 上接路线 A；路线 A 稳定后再评估是否需要 PPP。所有上层业务仍通过版本化消息协议和硬件抽象访问，不直接绑定 SIM7670G AT 细节。

---

## 14. 验收标准

P0 成功标准：

1. AMOLED 板和 SIM7670G 板可以同时通过 USB 连接 PC；
2. 两块板启动后发送版本化 `hello`；
3. PC Bridge 根据 `device_id` 和 `role` 识别 `wearable_node` 与 `connectivity_node`；
4. 不硬编码 COM 口，任意一块板重启后可以重新加入；
5. 两块板和 PC 使用同一套版本化消息协议；
6. AMOLED 板可以输出 QMI8658 原始六轴数据、统一时间戳和 IMU 窗口；
7. AMOLED 板可以验证麦克风链路、屏幕询问和用户确认；
8. SIM7670G 板可以输出 4G、GNSS、摄像头能力状态；
9. SIM7670G 板可以接收 `request_location`、`capture_image` 等命令并返回 ACK / 状态；
10. PC Bridge 可以接收 `motion_event`，运行 ContextRouter，向 AMOLED 板下发 `ask_user`；
11. 用户确认后，PC Bridge 可以请求 SIM7670G 板刷新 GNSS；
12. PC 保存 session 元数据、IMU、AudioGate、GNSS/网络、用户操作、模型输入输出、命令 ACK、异常和断线日志；
13. 同一份记录可以离线回放给 ContextRouter；
14. 所有业务逻辑不直接依赖 USB、COM 口、Wi-Fi、真实 4G、真实 GNSS、摄像头或具体开发板。

---

## 15. Codex 当前任务提示词

请按照以下要求实现 Ego Link P0 工程：

```text
创建 Ego Link P0 工程。当前实现形态是双开发板 + PC Development Bridge 集成验证架构。

AMOLED 板作为 `wearable_node`，负责 QMI8658 IMU、音频、屏幕、触摸、扬声器、MotionNet / AudioGate 和用户确认。

微雪 ESP32-S3-SIM7670G-4G 板作为 `connectivity_node`，蜂窝模块为 SIM7670G，不是 A7670E，负责 4G、GNSS、摄像头、TF 卡、缓存和通信能力验证。

当前阶段不接入正式 EGO Base。PC Development Bridge 负责自动识别两个节点、串口中继、统一事件总线、ContextRouter、Safety Kernel、数据记录、时间同步、事件回放和调试 Dashboard。PC 不是正式 Ego Base，也不能成为产品依赖。

固件使用 ESP-IDF 开发。P0-A 可使用 Mock / Stub 跑通链路，P0-B 逐步接入真实 IMU、声音、GNSS、4G 和摄像头。Mock 与真实驱动可以并存，但必须在消息、日志和记录中明确标记来源。

固件和 PC 侧必须采用抽象接口和版本化消息协议。业务层不得直接调用 USB、COM 口、Wi-Fi、SIM7670G、GNSS、摄像头、IMU 或唤醒芯片接口。

实现功能：双板 `hello` 识别、统一消息协议、设备上线、心跳、运动事件、用户询问、用户确认、定位刷新命令、命令 ACK、低电量事件、策略包接收与执行、离线缓存、恢复补传、PC Dashboard、session 记录和回放。

P0 的成功标准是安全陪伴最小闭环跑通：AMOLED 板产生撞击/跌倒候选，PC Bridge 接收运动事件，ContextRouter 判断需要确认，AMOLED 板显示询问，用户点击安全或需要帮助，PC 请求 4G 板刷新 GNSS，最终形成完整安全事件记录。
```

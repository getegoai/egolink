# EGO Link P0 工程开发上下文

> 本文档用于保存到 Codex 项目上下文。当前目标不是完整 EGO Base，也不是最终量产硬件，而是在电脑模拟后端环境下，先把 Ego Link 随身端主控工程跑通。

---

## 0. 硬件更正与项目边界

### 0.1 当前硬件

当前 Ego Link P0 使用的主控开发板为：

- **微雪 ESP32-S3-SIM7670G-4G 开发板**
- 主控：ESP32-S3
- 蜂窝通信模块：SIMCom **SIM7670G**
- 能力：4G Cat-1 上网、GNSS 定位、摄像头、Wi-Fi、BLE
- 注意：本项目当前不是 ESP32-S3-A7670E-4G，蜂窝模块不是 A7670E。

### 0.2 当前工程范围

当前阶段只聚焦 **Ego Link P0 Firmware + PC Simulator**。

暂不开发：

- 不开发正式 EGO Base；
- 不接入 Orange Pi 5 Plus；
- 不接入本地大模型；
- 不做长期记忆；
- 不做真实语音唤醒芯片；
- 不做真实 4G 上网调试；
- 不做真实 GNSS 搜星定位；
- 不做摄像头功能；
- 不做低功耗深度优化。

当前要做的是：

- 用 ESP32-S3 作为随身端主控；
- 用 Wi-Fi 模拟 4G 数据链路；
- 用软件模拟 GNSS 定位；
- 用按键 / 串口命令 / 定时器模拟唤醒事件；
- 用电脑运行 MQTT Broker、PC Simulator、简单 Dashboard；
- 跑通设备上线、心跳、定位上报、SOS、模拟唤醒、策略下发、离线缓存、恢复补传的闭环。

---

## 1. 产品定位

Ego Link 是 EGO 项目的随身设备原型，不是独立大脑，也不是小型手机。

它的定位是：

> Ego Link 是 EGO 的随身感知节点、低功耗安全前哨和远程通信入口。

P0 阶段暂时不依赖 EGO Base，而是通过电脑模拟 EGO 侧服务，验证随身端主控架构。

---

## 2. P0 总体架构

```text
ESP32-S3-SIM7670G-4G 开发板
    ↓ Wi-Fi，暂时代替 4G 数据链路
本地路由器 / 电脑热点
    ↓
电脑 PC Simulator
    ├─ Mosquitto MQTT Broker
    ├─ Python FastAPI / Flask Dashboard
    ├─ MQTT Client
    ├─ SQLite / JSONL 事件记录
    ├─ 策略包下发
    └─ 调试控制台
```

P0 阶段必须坚持 Mock-first 架构。业务层不能直接绑定 Wi-Fi、SIM7670G、GNSS、唤醒芯片。所有外设能力都必须通过抽象接口访问。

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

## 9. PC Simulator 设计

当前电脑模拟 EGO 侧，不命名为正式 EGO Base，避免误导架构。

### 9.1 PC Simulator 组成

```text
pc_simulator/
├─ MQTT Broker：Mosquitto
├─ MQTT Worker：订阅设备 status/event/log/ack
├─ FastAPI / Flask：提供本地 HTTP 页面和 API
├─ SQLite / JSONL：记录事件
├─ Dashboard：显示设备在线、电量、位置、事件
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
- 手动下发按钮：
  - request_location；
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

### Sprint 6：预留 SIM7670G 驱动桩

- 建立 sim7670_at_driver_stub；
- 建立 sim7670_gnss_driver_stub；
- 文档记录后续 AT 指令接入点；
- 不在 P0 调真实 4G。

验收：业务层不需要修改即可从 Mock 切换到 Stub 编译目标。

---

## 12. P0 明确不做的事情

P0 不做：

- 不调真实 SIM7670G 4G 上网；
- 不调真实 GNSS；
- 不调摄像头；
- 不做语音 ASR；
- 不做本地 LLM；
- 不接 EGO Base；
- 不做手机 App；
- 不做云端服务；
- 不做外壳；
- 不做最终功耗优化。

原因：P0 的核心目标是主控软件架构和事件闭环，而不是硬件堆功能。

---

## 13. 后续真实 SIM7670G 接入路线

P0 完成后，SIM7670G 接入分两条路线：

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

先完成 P0 Mock-first 闭环，再接路线 A；路线 A 稳定后再评估是否需要 PPP。

---

## 14. 验收标准

P0 成功标准：

1. ESP32-S3-SIM7670G-4G 开发板可以作为 Ego Link 主控启动；
2. 通过 Wi-Fi 连接电脑 MQTT Broker；
3. 设备每 10 秒上报心跳；
4. 设备每 30 秒上报模拟定位；
5. 串口输入 `wake` 可以生成 wake_detected 事件；
6. 串口输入 `sos` 或按键可以生成 critical SOS 事件；
7. PC Simulator 可以下发 play_prompt 命令；
8. ESP32-S3 可以接收命令并在串口输出本地动作；
9. PC Simulator 可以下发策略包；
10. ESP32-S3 可以保存并执行策略包；
11. 网络断开后事件进入本地队列；
12. 网络恢复后事件按 seq 顺序补传；
13. 所有业务逻辑不直接依赖真实 4G、真实 GNSS、真实唤醒芯片。

---

## 15. Codex 当前任务提示词

请按照以下要求实现 Ego Link P0 工程：

```text
创建 Ego Link P0 工程。目标硬件为微雪 ESP32-S3-SIM7670G-4G 开发板，蜂窝模块为 SIM7670G，不是 A7670E。

当前阶段不接入正式 EGO Base，只用电脑运行 PC Simulator。PC Simulator 负责 MQTT Broker、事件接收、简单 Dashboard、策略包下发和命令下发。

固件使用 ESP-IDF 开发。P0 阶段不启用真实 4G、不启用真实 GNSS、不启用真实语音唤醒芯片。用 Wi-Fi 模拟 4G 数据链路，用 MockGnssDriver 模拟定位，用 MockWakeDriver 模拟唤醒。

固件必须采用抽象接口：LinkTransport、ModemDriver、GnssDriver、WakeDriver、PowerDriver。业务层不得直接调用 Wi-Fi、SIM7670G、GNSS、唤醒芯片接口。

实现功能：设备上线、心跳、定位上报、SOS、模拟唤醒、低电量事件、策略包接收与执行、离线缓存、恢复补传、串口 CLI、PC Dashboard。

预留 sim7670_at_driver_stub、sim7670_gnss_driver_stub、sim7670_transport_stub，但 P0 只写接口和 TODO，不调真实蜂窝模块。

P0 的成功标准是主控状态机、事件协议、策略包、离线缓存、PC 模拟协同闭环跑通。
```


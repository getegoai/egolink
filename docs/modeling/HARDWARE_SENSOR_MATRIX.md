# Ego Link M1 Hardware Sensor Matrix

> 状态：M1-001 初版  
> 更新时间：2026-06-21  
> 范围：Waveshare ESP32-S3-SIM7670G-4G 开发板 + PC Simulator  
> 原则：只记录已经由仓库、固件或报告支撑的事实；未知项保持未知。

## 1. 目的

M1 的目标不是训练神经网络，而是建立可信数据采集闭环。本文记录当前硬件与传感器能力，帮助后续 `safety_recorder`、session manifest、PC 导入器和数据质量报告按真实边界实现。

状态枚举：

| 状态 | 含义 |
|---|---|
| `verified` | 已通过当前仓库脚本、固件或报告验证。 |
| `semi_verified` | 已确认接口或单次能力，但还没有完整 M1 数据采集能力。 |
| `pc_side_verified` | 通过 PC/USB/AT 侧验证，尚未集成到 ESP32 固件。 |
| `mock_only` | 当前事件或字段为 Mock，不代表真实传感器。 |
| `not_verified` | 有候选硬件或代码线索，但当前没有验证证据。 |
| `missing_or_unknown` | 当前仓库没有足够证据确认硬件存在、接线或驱动。 |

## 2. 当前硬件事实

| 项目 | 当前事实 | 状态 | 证据 |
|---|---|---:|---|
| 主控板 | Waveshare ESP32-S3-SIM7670G-4G 开发板。 | `verified` | `docs/EGO_LINK_P0_CONTEXT.md`；`reports/board_validation/20260621-091239/probe.md` |
| 主控 MCU | ESP32-S3，经 CH343 USB 串口暴露为 `COM4`。 | `verified` | `reports/board_validation/20260621-091239/probe.md` |
| 蜂窝/GNSS 模块 | SIMCom SIM7670G-MNGV。 | `verified` | `reports/board_validation/20260621-091239/probe.md` |
| SIM / LTE 数据链路 | AT 侧注册与附着曾通过；当前 2026-06-21 报告显示 `registered=True`、`attached=True`、`CSQ=28,0`。 | `pc_side_verified` | `docs/STATUS.md`；`reports/board_validation/20260621-091239/probe.md` |
| RNDIS | Windows 识别 Remote NDIS 网卡，地址曾为 `192.168.0.100/24`。 | `pc_side_verified` | `docs/STATUS.md`；`reports/board_validation/20260621-091239/probe.md` |
| Wi-Fi | ESP32-S3 `mqtt_heartbeat` 已通过 Wi-Fi 连接本机 Mosquitto。 | `verified` | `firmware/mqtt_heartbeat/README.md`；`docs/STATUS.md` |
| 摄像头 | `camera_smoke` 固件定义 Waveshare 摄像头引脚并已完成单帧 JPEG smoke test；当前运行固件不是 camera smoke。 | `semi_verified` | `firmware/camera_smoke/README.md`；`firmware/camera_smoke/main/app_main.c`；`docs/STATUS.md` |
| SD 卡 | 板级探测未观察到 SD 挂载；历史日志解析支持识别挂载失败。 | `not_verified` | `reports/board_validation/20260621-091239/probe.md`；`quality_tests/test_board_probe.py` |
| IMU | 当前仓库无真实 IMU 型号、引脚、驱动或采样验证。 | `missing_or_unknown` | 本矩阵检查结果 |
| 麦克风 | 当前仓库无真实麦克风型号、引脚、I2S/PDM/ADC 驱动或采样验证。 | `missing_or_unknown` | 本矩阵检查结果 |
| 物理 SOS 按键 | 产品和 P0 文档要求按键/SOS；当前真实按键 GPIO、驱动和硬件验证未记录。 | `not_verified` | `docs/产品定位.md`；`docs/EGO_LINK_P0_CONTEXT.md` |
| 电源/电量 | MQTT payload 中 `battery=87`、`charging=false` 为 Mock；真实电量计/ADC 未验证。 | `mock_only` | `firmware/mqtt_heartbeat/main/app_main.c` |

## 3. 传感器与数据能力矩阵

| 能力 | 当前实现 / 观测 | 当前状态 | 时间戳与序号 | M1 数据可用性 | M1 阻塞项 |
|---|---|---:|---|---|---|
| 设备在线状态 | `mqtt_heartbeat` 周期发布 `status`，包含 device_id、seq、uptime、Wi-Fi RSSI、mock modem/GNSS、电量。 | `verified` | `ts=uptime_ms:<n>`；全局 `seq`。 | 可作为 session 设备日志和链路状态。 | 需要统一 Unix 时间、session_id、固件/配置 manifest。 |
| 设备健康样本 | `sensor_sample/device_health` 上报 uptime、Wi-Fi RSSI、free heap、min free heap、mock battery、mock modem/GNSS。 | `verified` | `ts=uptime_ms:<n>`；全局 `seq`。 | 可作为 M1 recorder 的最小结构化样本。 | 需要采样配置、缺帧统计、session manifest 和质量报告。 |
| Wi-Fi RSSI | 固件调用 `esp_wifi_sta_get_ap_info` 刷新 RSSI。 | `verified` | 跟随 status / sensor_sample。 | 可记录网络质量变化。 | 需要补充网络状态变化事件和离线时长。 |
| Heap / runtime | 固件调用 `esp_get_free_heap_size` 和 `esp_get_minimum_free_heap_size`。 | `verified` | 跟随 sensor_sample。 | 可记录系统健康和内存压力。 | 需要长期 session 趋势和异常阈值。 |
| SIM7670G AT 身份 | PC 侧 AT 可在 `COM6` / `COM7` 返回 SIM7670G-MNGV。 | `pc_side_verified` | PC 探测时间戳；非固件 seq。 | 可进入硬件 manifest，不作为端侧传感帧。 | ESP32 侧 SIM7670G UART/USB 控制链路未实现。 |
| LTE 注册/附着 | PC 侧 AT 报告 registered/attached。 | `pc_side_verified` | PC 探测时间戳；非固件 seq。 | 可作为板级验证记录。 | 端侧 4G MQTT/PPP 未接入；RNDIS PC 外网路径仍有超时限制。 |
| RNDIS | Windows 识别 Remote NDIS。 | `pc_side_verified` | Windows 网络状态；非固件 seq。 | 可作为诊断，不作为端侧模型输入。 | 端侧业务不应依赖 PC RNDIS。 |
| SIM7670G GNSS no-fix | `sim7670_gnss_probe.py` 可打开/查询 GNSS，写入 `location_report fix=false`；最新报告为 `reports/gnss_validation/20260621-161721/gnss_probe.md`。 | `pc_side_verified` | PC 生成 ISO 时间；seq 从 event log 续号。 | 可验证协议闭环和 no-fix 记录。 | 室内未获得 fix；ESP32 固件未直接控制 GNSS；缺 fix age、精度、速度、卫星等真实数据。 |
| Mock GNSS | 固件 status/sensor_sample 中 `gnss_state=mock_fix`；Dashboard 也可生成 mock location。 | `mock_only` | 固件 uptime 或 PC ISO 时间。 | 只用于协议和 UI，不用于训练定位模型。 | M1 必须区分 mock 与真实 GNSS 来源。 |
| 摄像头单帧 | `camera_smoke` 可初始化摄像头并采集 JPEG；引脚表已在固件中记录。 | `semi_verified` | camera smoke 日志时间；未进入统一 event log。 | 可作为 VisionGate 未来按需采集候选。 | 当前固件不是 camera smoke；未纳入 session recorder；隐私、授权、哈希、保留期未实现。 |
| IMU 加速度/陀螺仪 | 无驱动、型号、引脚或采样数据。 | `missing_or_unknown` | 无。 | 不可用于 M1 数据集。 | 需要确认板载/外接 IMU 型号、接口、安装方向、采样率和功耗。 |
| 麦克风/音频 | 无麦克风驱动、接口或音频样本。 | `missing_or_unknown` | 无。 | 不可用于 AudioGate 数据集。 | 需要确认硬件、I2S/PDM/ADC 接线、环形缓冲和隐私策略。 |
| 物理 SOS 按键 | 当前可用 Dashboard/CLI 模拟 SOS；真实按键 GPIO 未验证。 | `not_verified` | 模拟 SOS 使用 PC ISO 时间或固件 mock 状态。 | 可验证 Safety Kernel 规则，不可代表真实按键可靠性。 | 需要 GPIO、消抖、长按/短按策略、误触和断网优先级验证。 |
| 串口 Safety CLI | `mqtt_heartbeat` 支持 `safety status/demo normal/sos/impact`，输出 deterministic mock。 | `semi_verified` | 串口日志；未进入统一 event log。 | 可用于固件侧规则接口 smoke。 | 需要真实 event 上报和 recorder 关联。 |
| SD / 本地存储 | SD 挂载状态未观察到；P0 可先用 NVS/SPIFFS 或 JSONL PC 侧记录。 | `not_verified` | 无稳定采样时间戳。 | 不可作为 M1 session 存储。 | 需要确认卡格式、供电、引脚、挂载参数和故障恢复。 |
| 电量/充电 | 当前为 mock `battery=87`、`charging=false`。 | `mock_only` | 跟随 status / sensor_sample。 | 可用于协议字段占位。 | 需要真实电源路径、电池电压/电量计、充电状态和温度。 |
| 温度 | 当前无板载温度、电池温度或模块温度字段。 | `missing_or_unknown` | 无。 | 不可用于功耗/安全策略。 | 需要传感器来源和采样策略。 |

## 4. 当前可进入 M1 recorder 的最小字段

首轮 recorder 可以先接入已经存在的低风险结构化数据：

| 字段 | 来源 | 说明 |
|---|---|---|
| `device_id` | 固件 / PC Simulator | 当前为 `ego-link-001`。 |
| `seq` | 固件全局 seq 或 PC event log 续号 | 需要在 session 内检查连续性。 |
| `monotonic_ms` | 固件 `uptime_ms` | 当前以字符串形式出现在 `ts`，M1 应拆成结构化字段。 |
| `received_at` | PC MQTT worker | PC 侧接收时间，可用于链路延迟估计。 |
| `wifi_rssi` | ESP32 Wi-Fi | 已真实读取。 |
| `free_heap_bytes` / `min_free_heap_bytes` | ESP32 runtime | 已真实读取。 |
| `modem_state` | 固件 mock 或 PC AT 报告 | 必须标注 `source=mock` 或 `source=pc_at_probe`。 |
| `gnss_state` / `fix` | 固件 mock 或 PC AT GNSS probe | 必须标注真实/Mock；当前真实 GNSS 只有 no-fix。 |
| `battery` / `charging` | 当前 mock | 不可用于电源模型训练。 |
| `safety_evaluation` | PC Safety Companion M0 | 规则基线输出，可用于闭环调试，不可作为真实安全标签。 |

## 5. M1-002 recorder 最小接口建议

M1-002 不应先做复杂模型或大规模重构。建议先定义一个独立 recorder 边界：

```text
safety_recorder_start(session_id, manifest)
safety_recorder_append_event(event)
safety_recorder_append_sensor_frame(sensor_frame)
safety_recorder_append_annotation(annotation)
safety_recorder_stop(reason)
```

首轮 manifest 至少包含：

- device_id；
- board target；
- firmware name/version/build time；
- contract version；
- enabled sensors；
- each sensor source: `real`, `pc_side_probe`, `mock`, `not_available`；
- sampling configuration；
- privacy mode and consent state；
- clock sources and known limitations。

## 6. M1-002 阻塞项

| 阻塞项 | 影响 | 建议下一步 |
|---|---|---|
| IMU 型号和接口未知 | 无法开始 MotionNet 数据窗口。 | 检查原理图/板载传感器，或决定外接 IMU 型号和引脚。 |
| 麦克风硬件未知 | 无法开始 AudioGate 数据。 | 确认是否板载麦克风；否则选型 I2S/PDM 麦克风。 |
| 真实按键 GPIO 未验证 | SOS 硬安全路径仍是模拟。 | 查板级按键和 GPIO，加入消抖测试。 |
| SD 挂载未验证 | 本地 session 持久化可能不可靠。 | 先验证 SD；若继续失败，M1 recorder 先落 SPIFFS/NVS 或 PC 侧。 |
| ESP32 侧 SIM7670G 控制未实现 | 真实 4G/GNSS 尚不能由固件采集。 | 保留 PC AT probe 作为过渡，后续实现 SIM7670G driver。 |
| 统一时间未实现 | 难以对齐多传感器窗口。 | 在 M1-002 中同时记录 monotonic_ms、PC received_at 和可选 Unix 时间。 |
| 用户反馈标签未实现 | 训练标签不可用。 | M1-005 再做标注/反馈入口；M1-002 先预留 annotation 文件。 |

## 7. 安全与表述边界

- M0 Safety Companion 是确定性规则基线，不是已验证的真实跌倒、呼救或事故识别模型。
- 当前 `manual_sos` 路径可验证 Safety Kernel/ContextRouter 契约和无副作用 command，不等于真实物理按键已经验证。
- 当前 GNSS no-fix 说明 AT 查询和事件记录可用，不说明室内定位或户外定位效果已验证。
- 当前 camera smoke 说明摄像头单帧采集可行，不说明 VisionGate、隐私授权、图像上传或事故视觉理解已完成。
- 在 M1 数据质量门槛达成前，不进入 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter 效果声明。

## 8. 下一步

建议 T032 / M1-002 建立 session recorder 最小骨架，先记录真实 `sensor_sample`、PC AT GNSS no-fix、模拟 SOS、安全评估和 manifest。IMU、音频、真实按键和 SD 卡在 recorder 接口稳定后逐项接入。

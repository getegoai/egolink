# Ego Link M1 Hardware Sensor Matrix

> 状态：HCTX-001 硬件上下文评估版 + T038 硬件可用性验证
> 更新时间：2026-06-22
> 范围：Waveshare ESP32-S3-SIM7670G-4G 开发板、现有仓库证据、PC Simulator、硬件上下文包 v0.3、2026-06-22 板级/GNSS/MQTT/session smoke
> 原则：只记录已经由仓库、固件、报告或明确文档支撑的事实；采购清单和候选平台不等于已到货、已接线或已验证。

## 1. 目的

M1 的目标不是训练神经网络，而是建立可信数据采集闭环。本文在原 M1-001 硬件传感器矩阵基础上执行 HCTX-001：把当前可确认硬件能力、Mock 边界、缺失驱动、功耗控制能力和后续 HARCH-001 耦合审计重点放到同一个事实表里，供 M1-002 recorder、M1-004 replay、M1-005 annotation 和后续真实传感器接入使用。

当前实现基线仍是微雪 ESP32-S3-SIM7670G-4G 开发板。STM32U5A5、Apollo4、ESP32-P4、Alif B1 和其他蜂窝模组只是候选评估对象，未经单独任务和实测不得写成最终 BOM。

状态枚举：

| 状态 | 含义 |
|---|---|
| `verified` | 已通过当前仓库脚本、固件或报告验证。 |
| `semi_verified` | 已确认接口或单次能力，但还没有完整 M1 数据采集能力。 |
| `pc_side_verified` | 通过 PC/USB/AT 侧验证，尚未集成到 ESP32 固件。 |
| `mock_only` | 当前事件或字段为 Mock，不代表真实传感器。 |
| `not_verified` | 有候选硬件、产品要求或代码线索，但当前没有验证证据。 |
| `missing_or_unknown` | 当前仓库没有足够证据确认料号、接线、驱动或采样能力。 |

## 2. 当前硬件事实

| 项目 | 料号 / 平台 | 接口 / 引脚 | 当前状态 | 证据 |
|---|---|---|---:|---|
| P0 主控板 | Waveshare ESP32-S3-SIM7670G-4G 开发板 | USB CH343 调试串口；SIM7670G USB composite；板载 Wi-Fi/BLE；摄像头连接器 | `verified` | `docs/EGO_LINK_P0_CONTEXT.md`；`docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md`；`docs/hardware/HARDWARE_USABILITY_VALIDATION.md`；`reports/board_validation/20260622-181619/probe.md`；`reports/board_validation/20260621-091239/probe.md` |
| 主控 MCU | ESP32-S3 | 当前 Windows 识别 CH343 串口 `COM4` | `verified` | `reports/board_validation/20260622-181619/probe.md` |
| 蜂窝 / GNSS 测试模组 | SIMCom SIM7670G-MNGV | PC 侧 AT 口识别为 `COM6` / `COM7`；RNDIS 网卡可见 | `pc_side_verified` | `docs/hardware/HARDWARE_USABILITY_VALIDATION.md`；`reports/board_validation/20260622-181619/probe.md`；`reports/gnss_validation/20260622-181804/gnss_probe.md`；`reports/gnss_validation/20260621-161721/gnss_probe.md`；`scripts/sim7670_gnss_probe.py` |
| 量产主控 | 未冻结；STM32U5A5、Apollo4、ESP32-P4、Alif B1 仅为候选 | 不适用 | `not_verified` | `docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md`；`docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md` |
| 量产蜂窝模组 | 未冻结；SIM7670G 仅是当前测试模组 | 不适用 | `not_verified` | `docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md` |
| 采购清单 | `docs/hardware/EGOLINK_硬件开发采购清单_v1.xlsx` | sheet：概览、采购总表、已有物料、平台对比、到货验收 | `not_verified` | 该 Excel 可打开且结构有效；内容只作采购/验收参考，不作硬件到货事实 |

### 2.1 最新硬件可用性验证

T038 于 2026-06-22 执行了真实板级/GNSS/MQTT/session smoke，结论见 `docs/hardware/HARDWARE_USABILITY_VALIDATION.md`。本轮验证到可继续开发的最小闭环，但不扩大未实测硬件能力声明：

- 板级探测：`reports/board_validation/20260622-181619/probe.md` 显示 ESP32-S3 CH343 `COM4`、SIM7670G 串口 `COM6/COM7` AT 身份、RNDIS 均可用；SIM inserted，CSQ 为 `21,0` / `20,0`，LTE registered/attached 均为 true。
- GNSS 探测：`reports/gnss_validation/20260622-181804/gnss_probe.md` 显示 `COM6/COM7` AT 可达，`gnss_power_state=1`，室内 no-fix，并写入 `location_report fix=false`。
- MQTT 接收：`pc_simulator/mqtt_worker.py --host 192.168.31.250 --port 1883 --max-messages 3 --process-safety` 成功收到开发板 `mqtt_status` 和 `sensor_sample/device_health seq=21548`；LAN broker 上可见开发板连接 `192.168.31.12 -> 192.168.31.250:1883`。
- M1 session：`pc_simulator/runtime/recordings/t038-hardware-usability-smoke/session_quality_report.md` 为 PASS，`quality_score=0.91`；`session_replay_report.md` 为 PASS，说明当前硬件事件可进入 recorder、quality gate 和 replay。
- Broker 边界：本机存在 loopback broker 和 LAN broker 两个实例；开发板连接 LAN broker，后续 live worker 必须使用 `192.168.31.250:1883`，不能用 `127.0.0.1:1883` 判断设备上报。

## 3. 传感器与能力矩阵

| 能力 | 料号 / 来源 | 接口 / 引脚 | 驱动状态 | 数据能力 | 功耗控制能力 | 真实 / Mock 状态 | M1 数据可用性与阻塞项 |
|---|---|---|---|---|---|---:|---|
| 设备在线状态 | ESP32-S3 + `firmware/mqtt_heartbeat` | Wi-Fi STA + MQTT；topic `ego/link/ego-link-001/status` | 固件已实现并刷写过；T038 live worker 已再次收到 status | `device_id`、`seq`、`uptime_ms`、RSSI、guard mode、queue size、mock modem/GNSS、电量字段 | 仅有心跳间隔；未实现统一功耗状态事件 | `verified` | 可进入 M1-002 recorder 作为设备日志；仍需固件版本、session_id、Unix time 和配置 manifest。 |
| 设备健康样本 | ESP32-S3 runtime | MQTT event topic `ego/link/ego-link-001/event`；`sensor_sample/device_health` | 固件已实现并收到真实上报；T038 收到 `seq=21548` | uptime、Wi-Fi RSSI、free heap、minimum free heap、mock battery、mock modem/GNSS | 只有固定上报间隔；无低功耗采样策略 | `verified` | 可作为当前唯一真实端侧结构化传感样本；缺采样率统计、缺帧统计和功耗状态。 |
| Wi-Fi RSSI | ESP32-S3 Wi-Fi | `esp_wifi_sta_get_ap_info` | 固件已调用 | RSSI dBm，随 status / sensor_sample 上报 | 未实现 Wi-Fi 省电/断连状态统计 | `verified` | 可用于网络质量特征；后续需记录断连、重连、离线时长。 |
| Heap / runtime | ESP32-S3 runtime | ESP-IDF heap API | 固件已调用 | `free_heap_bytes`、`min_free_heap_bytes` | 无专门功耗控制 | `verified` | 可用于设备健康；不是用户安全传感器。 |
| BLE | ESP32-S3 片内能力 | 未在当前固件启用 | 无应用驱动 | 无 BLE 数据 | 无 | `not_verified` | 不进入 M1 数据集；若后续用于近场或配置，需要独立任务验证。 |
| 4G 数据链路 | SIM7670G-MNGV | PC 侧 USB AT / RNDIS；ESP32 侧控制链路未实现 | PC 侧 AT TCP/IP 栈曾验证公网访问；ESP32 固件未接入 | SIM、LTE 注册、分组数据附着、CSQ、AT TCP/IP 可用性 | 可通过 AT 电源/网络状态命令探测；尚无固件功耗状态机 | `pc_side_verified` | 可写入硬件验证报告，不作为端侧实时传感帧；阻塞项是 ESP32 侧 SIM7670G driver、弱网恢复和低功耗。 |
| RNDIS | SIM7670G USB composite | Windows Remote NDIS，曾获 `192.168.0.100/24` | PC 识别；外网指定源地址 ping/curl 曾超时 | 诊断网络接口 | 无固件控制 | `pc_side_verified` | 仅作 PC 侧诊断；业务不可依赖 PC RNDIS。 |
| SIM7670G GNSS no-fix | SIM7670G-MNGV | PC 侧 USB AT；`AT+CGNSSPWR`、`AT+CGNSSINFO`、`AT+CGPSINFO` | `scripts/sim7670_gnss_probe.py` 已实现 PC 侧探测；T038 `COM6/COM7` 均 AT 可达 | 当前可记录 `fix=false`、`gnss_power_state=1`、satellites 等；室内未获得 fix | PC 脚本可开 GNSS 电源；无固件级 GNSS 启停策略 | `pc_side_verified` | 可验证协议闭环和 no-fix 记录；不可作为真实定位数据集。需要户外 fix、fix age、精度、速度和 ESP32 侧控制。 |
| Mock GNSS | 固件 / Dashboard mock | MQTT status/event 或 PC Simulator | 已用于协议和 UI | `gnss_state=mock_fix`、模拟 location | 无真实功耗 | `mock_only` | 仅用于协议/UI，不可用于定位模型训练；M1 必须显式标注 source。 |
| 摄像头单帧 | Waveshare 板载/连接器摄像头；具体 sensor 型号未在仓库确认 | Y2-Y9=GPIO7-GPIO14，PCLK=GPIO46，VSYNC=GPIO42，HREF=GPIO41，XCLK=GPIO39，SIO_D=GPIO15，SIO_C=GPIO16；CAM DIP ON | `firmware/camera_smoke` 已完成 init 和单帧 JPEG smoke；证据见 `firmware/camera_smoke/main/app_main.c` 和 `firmware/camera_smoke/README.md`；当前运行固件不是 camera smoke | 单张 JPEG、size、checksum、SOI/EOI；未进入统一 event log | 可按需启用；无摄像头电源域、隐私授权、保留期或哈希链路 | `semi_verified` | 可作为未来 VisionGate 候选；M1 recorder 暂不记录原始图像。需要 sensor 型号、授权、哈希、功耗和按需采集策略。 |
| IMU 加速度/陀螺仪 | 未确认；可能需外接低功耗六轴 IMU | 未确认 I2C/SPI、引脚、安装方向 | 无驱动、无采样、无 ring buffer | 无真实 accel/gyro；无采样率、抖动、缺帧 | 无低功耗中断、FIFO、唤醒策略 | `missing_or_unknown` | 当前仓库无真实 IMU。阻塞 MotionNet 和事件前后窗口；需确认料号、接口、方向、ODR、FIFO 和功耗。 |
| 麦克风 / 音频 | 未确认；候选 PDM/I2S 麦克风 | 未确认 I2S/PDM/ADC、引脚、时钟 | 无驱动、无音频样本 | 无 VAD、音量、事件音频、clip ref | 无音频门控/环形缓冲功耗策略 | `missing_or_unknown` | 当前仓库无真实麦克风。阻塞 AudioGate；需确认硬件、采样率、隐私授权和短时缓冲。 |
| 物理 SOS 按键 | 产品要求存在；真实 GPIO 未确认 | 未确认 GPIO、上拉/下拉、消抖 | Dashboard/CLI 可模拟 SOS；真实按键 GPIO 未验证 | 模拟 `sos_pressed` 可进入 Safety flow | 物理按键低功耗唤醒未实现 | `not_verified` | 可验证规则基线，不代表真实 SOS 可靠性。阻塞硬安全路径验证。 |
| 串口 Safety CLI | ESP32-S3 固件 CLI | CH343 `COM4` | 固件提供 `safety status/demo normal/sos/impact` 静态测试路径 | deterministic mock safety input/output | 无功耗测量标记 | `semi_verified` | 可做接口 smoke；未写入统一 recorder。 |
| SD / 本地存储 | 板级 SD 能力未确认 | 未确认 SDMMC/SPI 引脚和卡状态 | 板级探测支持解析 SD 失败；当前未观察到挂载成功 | 无本地 session 持久化 | 无写入窗口/掉电恢复策略 | `not_verified` | 不可作为 M1 session 存储。需确认卡、供电、格式、引脚、挂载参数和异常恢复。 |
| SPI Flash / NVS | ESP32-S3 内部 flash | ESP-IDF NVS/分区；当前未作为 session recorder | P0 配置可用，M1 recorder 未实现固件存储 | 可作为小型队列/配置候选 | flash 写入功耗未测 | `semi_verified` | 可作为 SD 失败时的过渡存储候选，但需独立 recorder 任务验证。 |
| 电量 / 充电 | 真实电池、电量计、充电 IC 未确认 | 未确认 ADC/I2C fuel gauge/charger status | 当前固件固定 `battery=87`、`charging=false` | Mock battery_percent / charging | 无电源域控制、低电量策略和测量标记 | `mock_only` | `battery=87` 只能占位。阻塞低电量、续航和充电状态训练/策略验证。 |
| 电源控制 / 功耗状态 | 平台目标要求 48h 典型守护；PPK2 已作为仪器参考 | 未确认负载开关、模组 PWRKEY、电源域 GPIO | 无统一 `BOOT/GUARDING/GNSS_FIX/UPLOAD/...` 状态事件 | 无累计时长和测量标记 | 未实现状态进入/退出事件或 GPIO marker | `not_verified` | 阻塞续航声明和功耗优化；HARCH/HPWR 后续需审计平台_power、modem、GNSS、camera、audio。 |
| 温度 | 未确认板载温度、电池温度或模组温度来源 | 未确认 | 无驱动 | 无温度数据 | 无热保护状态 | `missing_or_unknown` | 不可用于安全/功耗策略。 |

## 4. 当前可进入 M1-002 recorder 的最小字段

首轮 recorder 可以继续只接入低风险结构化数据，且每个字段必须保留 source 与真实性：

| 字段 | 来源 | 真实边界 |
|---|---|---|
| `device_id` | 固件 / PC Simulator | 当前默认 `ego-link-001`。 |
| `seq` | 固件全局 seq 或 PC event log 续号 | 需要在 session 内检查连续性和回退。 |
| `monotonic_ms` | 固件 `uptime_ms` | 当前常嵌在 `ts=uptime_ms:<n>`；M1 应拆成结构化字段。 |
| `received_at` | PC MQTT worker | PC 接收时间，可用于链路延迟估计，不等同设备采样时间。 |
| `wifi_rssi` | ESP32 Wi-Fi | 已真实读取。 |
| `free_heap_bytes` / `min_free_heap_bytes` | ESP32 runtime | 已真实读取。 |
| `modem_state` | 固件 mock 或 PC AT 报告 | 必须标注 `mock` / `pc_side_probe` / future `device`。 |
| `gnss_state` / `fix` / `gnss_power_state` | 固件 mock 或 PC AT GNSS probe | 当前真实 GNSS 只有 PC 侧 no-fix。 |
| `battery` / `charging` | 当前 mock | 不可用于电源模型训练或续航结论。 |
| `safety_evaluation` / replay output | PC Safety Companion M0 | 规则基线输出，可用于闭环调试，不可作为真实安全标签。 |

## 5. 阻塞 M1 数据采集的缺失硬件或驱动

| 阻塞项 | 影响 | 建议下一步 |
|---|---|---|
| IMU 料号、接口、安装方向和驱动未知 | 无法采集 MotionNet 所需 accel/gyro 和事件窗口。 | 查开发板原理图；若无板载 IMU，选定外接低功耗六轴 IMU，先做 mock/driver interface 和 ring buffer，再做真实采样。 |
| 麦克风硬件和音频链路未知 | 无法采集 AudioGate 数据或事件音频。 | 确认 PDM/I2S/ADC 麦克风和引脚；先定义隐私和短时缓冲边界。 |
| 真实物理 SOS GPIO 未验证 | SOS 硬安全路径仍是 Dashboard/CLI 模拟。 | 确认按键 GPIO、消抖、长按/短按、低功耗唤醒和误触策略。 |
| SD 挂载未验证 | 固件侧长 session 持久化和掉电恢复不可靠。 | 复测 SD 卡格式、供电、引脚和挂载参数；若继续失败，先用 SPI flash/NVS 或 PC 侧 recorder 过渡。 |
| ESP32 侧 SIM7670G 控制链路未实现 | 端侧无法直接采集真实 4G/GNSS 状态。 | 保留 PC AT probe 作为过渡；后续实现 `platform_modem` / `platform_gnss` 后端。 |
| 真实电池、电量计、充电和电源控制未知 | 不能验证低电量策略、续航和功耗预算。 | 明确电池/充电/电量计料号，加入电源状态事件和 PPK2/Otii 对齐标记。 |
| 统一时间与功耗状态事件缺失 | 多传感器窗口和功耗波形无法对齐。 | M1-002 继续保留 monotonic + PC received_at；HPWR-001 再加入功耗状态进入/退出事件。 |
| 用户反馈标签入口仍未实现 | 训练标签不可用。 | T037 / M1-005 增加 annotation CLI，关联 session、source key、consent 和 outcome。 |

## 6. HARCH-001 应重点审计的耦合点

本轮不执行 HARCH-001，只列出后续审计重点：

| 耦合点 | 当前线索 | 审计目标 |
|---|---|---|
| Wi-Fi / MQTT 与业务事件耦合 | `firmware/mqtt_heartbeat/main/app_main.c` 直接构造 status/event JSON 并使用 Wi-Fi/MQTT 路径。 | 拆出 `platform_connectivity` / `connectivity_service`，让 4G、Wi-Fi、mock 后端可替换。 |
| SIM7670G PC 侧探测与未来固件后端边界 | `scripts/sim7670_gnss_probe.py` 能探测 PC AT，但固件未控制 SIM7670G。 | 审计 `platform_modem`、`platform_gnss`、PWRKEY、AT 命令队列、弱网恢复和功耗状态。 |
| Safety adapter 对设备可用性的默认值 | `pc_simulator/safety_companion.py` 当前默认 camera/microphone available 可能高于硬件矩阵事实；session replay 已按隐私和 recording 降低可用性。 | 确保 capability descriptor 驱动证据请求过滤，不让模型请求不存在的音频/图像能力。 |
| Recorder 与 PC event log 耦合 | `pc_simulator/session_recorder.py` 从 PC JSONL 派生 recording，不是固件内 `safety_recorder`。 | 审计固件 recorder 接口、文件哈希、掉电恢复和 PC import/replay 的兼容边界。 |
| 摄像头 smoke 与主固件分离 | `firmware/camera_smoke` 验证单帧，但 `mqtt_heartbeat` 未接入摄像头。 | 后续 `platform_camera` 需要把按需采集、隐私授权、hash、retention 和功耗状态连起来。 |
| 电量字段与真实电源路径耦合 | 多处 payload 使用 `battery=87`、`charging=false`。 | 建立 `platform_power`，禁止 mock 电量被当作真实策略依据。 |
| 厂商 API 泄漏风险 | 当前 ESP-IDF API 主要在固件内直接调用。 | HARCH-001 只审计，不一次性大重构；优先抽象 `inference_backend`、`platform_time`、`platform_power`。 |

## 7. 安全与表述边界

- M0 Safety Companion 是确定性规则基线，不是已验证的真实跌倒、呼救或事故识别模型。
- 当前 `manual_sos` 路径可验证 Safety Kernel / ContextRouter 契约和无副作用 command，不等于真实物理按键已经验证。
- 当前 GNSS no-fix 说明 PC 侧 AT 查询和事件记录可用，不说明室内定位或户外定位效果已验证。
- 当前 camera smoke 说明摄像头单帧采集可行，不说明 VisionGate、隐私授权、图像上传或事故视觉理解已完成。
- 48 小时和 5-7 天续航是工程目标，不是当前开发板或整机实测结论。
- 在 M1 数据质量门槛达成前，不进入 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter 效果声明。

## 8. 下一步

HCTX-001 后的建议顺序：

1. T037 / M1-005：最小 annotation CLI，先把现有 recording 的人工标签闭环补上。
2. T039：IMU mock/driver interface 和 ring buffer 骨架；真实 IMU 确认后再接入采样。
3. HARCH-001：输出 `docs/hardware/PLATFORM_COUPLING_AUDIT.md`，只审计平台耦合，不做大规模迁移。

T038 硬件可用性 smoke 已完成，但它只确认当前开发板最小闭环可继续推进；IMU、麦克风、物理 SOS GPIO、SD、真实电量/充电和 ESP32 侧 SIM7670G 控制链路仍需后续任务逐项验证。

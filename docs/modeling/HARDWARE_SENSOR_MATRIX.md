# Ego Link M1 Hardware Sensor Matrix

> 状态：HCTX-001 硬件上下文评估版 + T038 硬件可用性验证 + T039 IMU mock/ring skeleton/live mock capture + TIMU-001 real IMU bring-up evidence gate + TCAM-001 camera smoke live capture + HDBRIDGE-001 dual-board PC bridge PoC + HDBRIDGE-002 AMOLED QMI8658 live window + TIMU-002 QMI8658 sample quality gate + TIMU-003 QMI8658 timing retest + TIMU-004A QMI8658 single-pose quality gate + TIMU-004B QMI8658 three-pose quality gate + TIMU-005 QMI8658 motion window + TIMU-006 QMI8658 long window + TIMU-007 platform_imu backend boundary
> 更新时间：2026-06-24
> 范围：Waveshare ESP32-S3-SIM7670G-4G 开发板、ESP32-S3-Touch-AMOLED-2.06 双板开发候选、现有仓库证据、PC Simulator、硬件上下文包 v0.3、2026-06-22 板级/GNSS/MQTT/session smoke、2026-06-23 HDATA-001 HPWR live capture、T039 `platform_imu` mock/ring interface and live mock MQTT capture、TIMU-001 real IMU bring-up plan、TCAM-001 camera smoke UART live capture、HDBRIDGE-001 PC bridge PoC、HDBRIDGE-002 AMOLED USB JSONL + QMI8658 WHOAMI/sample window、TIMU-002 QMI8658 timing/orientation quality report、TIMU-003 QMI8658 20Hz 120-sample retest、TIMU-004A QMI8658 single-pose pose/calibration report、TIMU-004B QMI8658 manual three-pose report、TIMU-005 QMI8658 motion-window report、TIMU-006 QMI8658 long-window report、TIMU-007 platform_imu backend-boundary report
> 原则：只记录已经由仓库、固件、报告或明确文档支撑的事实；采购清单和候选平台不等于已到货、已接线或已验证。

## 1. 目的

M1 的目标不是训练神经网络，而是建立可信数据采集闭环。本文在原 M1-001 硬件传感器矩阵基础上执行 HCTX-001：把当前可确认硬件能力、Mock 边界、缺失驱动、功耗控制能力和后续 HARCH-001 耦合审计重点放到同一个事实表里，供 M1-002 recorder、M1-004 replay、M1-005 annotation 和后续真实传感器接入使用。

当前硬件基线仍是微雪 ESP32-S3-SIM7670G-4G 开发板；ESP32-S3-Touch-AMOLED-2.06 已作为双板感知节点候选完成 PC Bridge PoC，并在 HDBRIDGE-002 中完成 live USB JSONL、QMI8658 WHOAMI 和 40 条短窗口 I2C 样本采集。TIMU-002 发现原始采样调度只能达到约 `82.31 ms / 12.15 Hz`；TIMU-003 改为 `vTaskDelayUntil` 固定周期采样后，120 样本窗口达到约 `49.99 ms / 20.00 Hz`，并通过 analyzer quality gates、PC Bridge、recording、quality gate 和 replay。TIMU-004A 新增 pose/motion analyzer，并复测一个 `z_negative` 静置窗口，姿态、标签匹配和保守 offset 估计通过；TIMU-004B 完成人工三姿态静态采集，`z_negative`、`x_positive`、`y_positive` 三个窗口均通过静态质量、标签匹配、offset 和 source boundary，三姿态总 quality gates PASS。TIMU-005 复用三姿态证据并实采一个旋转/轻敲 motion window，motion sanity PASS，accel magnitude range 约 `490.04 mg`，gyro peak 约 `201921 mdps`，M1 合并闭环生成 480 条 `imu_motion` frame。TIMU-006 将 AMOLED bridge 改为 600 样本可配置长窗口，实测 30 秒窗口 observed mean interval 约 `49.9983 ms`、max interval deviation `1.0 ms`、`missed_deadlines=0`，M1 闭环生成 600 条 `imu_motion` frame。该结论仍不等于正式 IMU 验收或产品 BOM 冻结。STM32U5A5、Apollo4、ESP32-P4、Alif B1 和其他蜂窝模组只是候选评估对象，未经单独任务和实测不得写成最终 BOM。

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
| 双板感知节点候选 | ESP32-S3-Touch-AMOLED-2.06 | Native USB Serial/JTAG `COM9`；USB JSONL 接入 PC Bridge；I2C SDA GPIO15 / SCL GPIO14；板上 QMI8658 WHOAMI、120 样本 20Hz 窗口、三姿态静态窗口、motion window 和 600 样本长窗口已实测，麦克风、TF/SD、屏幕/触摸仍需 live 验证 | `semi_verified` | `docs/hardware/双板开发架构.md`；`docs/hardware/HDBRIDGE_001_DUAL_BOARD_PC_BRIDGE_POC_20260623.md`；`docs/hardware/HDBRIDGE_002_AMOLED_QMI8658_LIVE_CAPTURE_20260623.md`；`docs/hardware/TIMU_003_QMI8658_TIMING_RETEST_20260623.md`；`docs/hardware/TIMU_004_QMI8658_POSE_QUALITY_20260623.md`；`docs/hardware/TIMU_004B_QMI8658_MANUAL_CAPTURE_20260623.md`；`docs/hardware/TIMU_005_QMI8658_MOTION_WINDOW_20260624.md`；`docs/hardware/TIMU_006_QMI8658_LONG_WINDOW_20260624.md` |
| 双板 PC Bridge | PC Simulator bridge | JSONL/stdin PoC；后续可替换为 USB CDC transport | `semi_verified` | `pc_simulator/board_bridge.py`；`scripts/board_bridge.py`；`quality_tests/test_board_bridge.py` |
| 采购清单 | `docs/hardware/EGOLINK_硬件开发采购清单_v1.xlsx` | sheet：概览、采购总表、已有物料、平台对比、到货验收 | `not_verified` | 该 Excel 可打开且结构有效；内容只作采购/验收参考，不作硬件到货事实 |

### 2.1 最新硬件可用性验证

T038 于 2026-06-22 执行了真实板级/GNSS/MQTT/session smoke，结论见 `docs/hardware/HARDWARE_USABILITY_VALIDATION.md`。本轮验证到可继续开发的最小闭环，但不扩大未实测硬件能力声明：

- 板级探测：`reports/board_validation/20260622-181619/probe.md` 显示 ESP32-S3 CH343 `COM4`、SIM7670G 串口 `COM6/COM7` AT 身份、RNDIS 均可用；SIM inserted，CSQ 为 `21,0` / `20,0`，LTE registered/attached 均为 true。
- GNSS 探测：`reports/gnss_validation/20260622-181804/gnss_probe.md` 显示 `COM6/COM7` AT 可达，`gnss_power_state=1`，室内 no-fix，并写入 `location_report fix=false`。
- MQTT 接收：`pc_simulator/mqtt_worker.py --host 192.168.31.250 --port 1883 --max-messages 3 --process-safety` 成功收到开发板 `mqtt_status` 和 `sensor_sample/device_health seq=21548`；LAN broker 上可见开发板连接 `192.168.31.12 -> 192.168.31.250:1883`。
- M1 session：`pc_simulator/runtime/recordings/t038-hardware-usability-smoke/session_quality_report.md` 为 PASS，`quality_score=0.91`；`session_replay_report.md` 为 PASS，说明当前硬件事件可进入 recorder、quality gate 和 replay。
- Broker 边界：本机存在 loopback broker 和 LAN broker 两个实例；开发板连接 LAN broker，后续 live worker 必须使用 `192.168.31.250:1883`，不能用 `127.0.0.1:1883` 判断设备上报。

### 2.2 HDATA-001 live capture

HDATA-001 于 2026-06-23 在刷写 HPWR-001 固件后执行，耐久摘要见
`docs/hardware/HDATA_001_LIVE_CAPTURE_20260623.md`。本轮使用独立 event log
`pc_simulator/runtime/hdata-001-hpwr-live-20260623-0906-events.jsonl`，避免混入历史事件：

- ESP32-S3 `COM4` 刷写成功，SIM7670G `COM6/COM7` AT 身份可达，SIM ready，CSQ `18,0`，LTE registered/attached。
- MQTT clean capture 收到 6 条真实设备消息：4 条 `mqtt_status` 和 2 条 `sensor_sample/device_health`。
- 新固件 live payload 已带出 HPWR 字段：`power_state_elapsed_ms`、`power_state_cumulative_ms`、`power_marker_seq`、`power_serial_marker_id`、`power_gpio_marker_id`、`power_gpio_marker_enabled=false`。
- 示例真实样本：`sensor_sample/device_health seq=25`，RSSI `-34`，`free_heap_bytes=260136`，`POWER_MARKER_000102`；`sensor_sample/device_health seq=29`，RSSI `-32`，`free_heap_bytes=260172`，`POWER_MARKER_000118`。
- SIM7670G GNSS PC-side probe 写入 `location_report seq=31`，`gnss_power_state=1`，室内 `fix=false`，raw response `+CGNSSINFO: ,,,,,,,,`。
- Clean recording `pc_simulator/runtime/recordings/hdata-001-hpwr-live-20260623-0906/` 质量门 PASS：`quality_score=0.94`，`errors=0`，`warnings=2`；replay PASS：7 个输入均为 `risk_type=none`。

### 2.3 T039 IMU mock live capture

T039 于 2026-06-23 在 `platform_imu` mock/ring interface 加入后执行真板 MQTT
采集，耐久摘要见 `docs/hardware/T039_IMU_MOCK_LIVE_CAPTURE_20260623.md`。
首次烧录暴露 `sensor_task` 栈溢出，已通过静态 sensor JSON buffer 和
`sensor_task` 6144 stack 修复。修复后使用独立 event log
`pc_simulator/runtime/hdata-001-imu-mock-live-20260623-0926-events.jsonl`：

- ESP32-S3 `COM4` 刷写成功，app binary size `0xd8ff0`。
- MQTT clean capture 收到 10 条真实设备消息：7 条 `mqtt_status` 和 3 条 `sensor_sample/device_health`。
- 3 条 `device_health` 样本带出 `imu_source=mock_stationary`、`imu_hardware_present=false`、`imu_driver_enabled=false`、`imu_sample_mock=true`、ring count 和 accel/gyro mock 数值。
- 示例样本：`seq=13` RSSI `-47`，`free_heap_bytes=254896`，`imu_ring_count=4`，`accel_mg=(2,-2,1002)`；`seq=21` RSSI `-34`，`free_heap_bytes=254924`，`imu_ring_count=6`，`accel_mg=(-1,1,999)`。
- Clean recording `pc_simulator/runtime/recordings/hdata-001-imu-mock-live-20260623-0926/` 质量门 PASS：`quality_score=0.94`，`errors=0`，`warnings=2`；replay PASS：10 个输入均为 `risk_type=none`。
- 本轮仍不证明真实 IMU 存在、接线、方向、采样率、FIFO、中断或校准可用。

### 2.4 TIMU-001 real IMU bring-up evidence gate

TIMU-001 于 2026-06-23 将真实 IMU 的下一步从“写驱动”前移到“证据门”，见
`docs/hardware/TIMU_001_REAL_IMU_BRINGUP_PLAN.md`：

- 当前 Waveshare ESP32-S3-SIM7670G-4G P0 setup 没有仓库证据证明真实 IMU 已存在、已接线、已采样、已校准或已纳入功耗控制。
- 采购清单中可追踪的候选路径包括 `ST STEVAL-MKI227KA（LSM6DSV16X）` 和 `SensorTile.box PRO`；它们是评估/数据采集候选，不是已验证产品 BOM。
- 后续只有在记录精确料号、数据手册/原理图、I2C/SPI 引脚、INT 引脚、供电、安装方向、ODR、FIFO/DRDY 策略后，才允许写真实 `platform_imu` 后端。
- `imu_hardware_present=true`、`imu_driver_enabled=true`、`imu_sample_mock=false` 必须由身份探测、真实样本窗口、sample-rate/jitter/drop 报告、quality gate 和 replay 共同支撑。

### 2.5 TCAM-001 camera smoke live capture

TCAM-001 于 2026-06-23 重新刷写 `firmware/camera_smoke` 并通过 UART 捕获真实摄像头证据，见
`docs/hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md`：

- ESP32-S3 `COM4` 刷写 `egolink_camera_smoke.bin` 成功，app binary size `0xdce40`。
- 摄像头识别为 OV5640，`CAMERA_SMOKE_INIT_OK profile=waveshare_esp32s3_sim7670g_4g`。
- 3 帧 QVGA JPEG 样本采集成功：bytes `2893/3708/3700`，checksum `a5db84d7/94301dec/7a151b26`，SOI/EOI 均为 `ffd8/ffd9`。
- 当前证据仍属于独立 `camera_smoke` 固件；`mqtt_heartbeat` 没有接入图像采集、隐私授权、hash/retention 或功耗状态控制。

### 2.6 HDBRIDGE-001 dual-board PC bridge PoC

HDBRIDGE-001 于 2026-06-23 将 `docs/hardware/双板开发架构.md` 落成 PC-only 桥接 PoC，见
`docs/hardware/HDBRIDGE_001_DUAL_BOARD_PC_BRIDGE_POC_20260623.md`：

- `pc_simulator/board_bridge.py` 支持 `wearable_node` / `connectivity_node` 的 `hello` 角色绑定，不依赖 COM 编号。
- `motion_event` 可归一化写入 PC Simulator event log；高撞击/跌倒分数会生成 `ask_user` 和 `request_location` 的 `command_sent` 记录。
- M1 recorder 已支持 `imu_motion` frame，但来源标记为 `source_availability=bridge_uplink`、`source_status=unverified`。
- 本任务没有 live USB CDC、pyserial、AMOLED 固件、QMI8658 WHOAMI、麦克风、屏幕触摸或两板直连 UART 验证。

### 2.7 HDBRIDGE-002 AMOLED QMI8658 live window

HDBRIDGE-002 于 2026-06-23 将 ESP32-S3-Touch-AMOLED-2.06 的 QMI8658
身份探测和短窗口样本接入 PC Bridge，见
`docs/hardware/HDBRIDGE_002_AMOLED_QMI8658_LIVE_CAPTURE_20260623.md`：

- 新增 `firmware/amoled_bridge`，使用 vendor pin map：I2C SDA GPIO15、SCL GPIO14。
- AMOLED 板在 Windows 侧识别为 ESP32-S3 native USB `COM9`，VID/PID 为 `303A:1001`，flash 时识别为 ESP32-S3、PSRAM 8MB、MAC `02:00:00:00:00:01`。
- Live JSONL 捕获 43 行：1 条 `hello`、1 条 `imu_whoami`、40 条 `imu_sample`、1 条 `amoled_bridge_done`。
- AXP2101 chip id 为 `0x4A`；QMI8658 WHOAMI 为 `0x05`，reset result 为 `0x80`。
- 样本窗口结果为 `samples_emitted=40`、`read_errors=0`、`not_ready_count=0`。
- PC Bridge 存储 43 条事件，recording 生成 40 条 `imu_motion` frame，quality gate PASS `0.94`，replay PASS。
- 本任务仍不验证 ODR、PC 接收 jitter、drop-rate、安装方向、校准、FIFO/中断、麦克风、TF/SD、屏幕触摸、功耗或两板直连 UART。

### 2.8 TIMU-002 QMI8658 sample quality gate

TIMU-002 于 2026-06-23 将 HDBRIDGE-002 的 live JSONL 变成可重复的样本质量门，
见 `docs/hardware/TIMU_002_QMI8658_SAMPLE_QUALITY_20260623.md`：

- 新增 `pc_simulator/imu_quality.py` 和 `scripts/analyze_imu_quality.py`。
- 输入 capture：`pc_simulator/runtime/hdb002-amoled-live-20260623-194454.jsonl`。
- WHOAMI：`5`，expected `5`，identity gate PASS。
- 样本完整性：40 条 `imu_sample`，sample index 和 seq 连续，completion gate PASS。
- QMI timestamp：monotonic，PASS。
- 静置方向：warmup 后平均轴约 `[56.74, 26.00, -1029.54] mg`，dominant axis 为 `z negative`，mean accel magnitude 约 `1031.43 mg`，static orientation PASS。
- gyro 静置 sanity：warmup 后 mean absolute rate 约 `502.42 mdps`，PASS。
- device timing：目标 `50 ms / 20 Hz`，实测平均 `82.31 ms / 12.15 Hz`，FAIL。
- formal IMU acceptance 仍为 false，原因包括 `source_status_unverified`、`device_timing_gate_failed` 和 `quality_gates_not_all_passed`。

### 2.9 TIMU-003 QMI8658 timing retest

TIMU-003 于 2026-06-23 修复 AMOLED bridge 的采样调度并复测 120 样本窗口，
见 `docs/hardware/TIMU_003_QMI8658_TIMING_RETEST_20260623.md`：

- `firmware/amoled_bridge` 改为 `vTaskDelayUntil` 固定周期采样。
- `imu_sample.device_monotonic_ms` 改为采样开始时刻，避免 JSON 打印耗时污染采样间隔。
- 样本窗口从 40 条扩展为 120 条。
- 完成记录包含 `timing_mode=vTaskDelayUntil`、`missed_deadlines=0`、`max_sample_work_ms=42`。
- Analyzer 使用 `--min-samples 100`；120 条样本全部连续。
- device timing：目标 `50 ms / 20 Hz`，实测平均 `49.99 ms / 20.00 Hz`，PASS。
- static orientation：dominant axis 为 `z negative`，mean accel magnitude 约 `1033.37 mg`，PASS。
- PC Bridge 存储 123 条事件，recording 生成 120 条 `imu_motion` frame，quality gate PASS `0.94`，replay PASS。
- formal IMU acceptance 仍为 false，因为 source 仍保持 `bridge_uplink/unverified`，且安装方向、校准、FIFO/中断、功耗和 `platform_imu` real backend 仍未验收。

### 2.10 TIMU-004A QMI8658 single-pose quality gate

TIMU-004A 于 2026-06-23 新增 QMI8658 姿态/校准分析器，并对当前 AMOLED 板
位置执行单姿态复测，见 `docs/hardware/TIMU_004_QMI8658_POSE_QUALITY_20260623.md`：

- 新增 `pc_simulator/imu_pose_quality.py` 和 `scripts/analyze_imu_pose_quality.py`。
- Analyzer 支持 `LABEL=JSONL` 多姿态输入、axis/sign 标签匹配、静置 1g 检查、保守 calibration offset、motion sanity 和 `bridge_uplink/unverified` source 边界。
- 当前 live capture：`pc_simulator/runtime/timu004-qmi8658-single-pose-live-20260623-203238.jsonl`，123 行 JSONL，120 条 `imu_sample`。
- Timing cross-check 仍为 PASS：目标 `50 ms / 20 Hz`，实测约 `49.99 ms / 20.00 Hz`，`missed_deadlines=0`。
- 单姿态 `z_negative` PASS：mean axes 约 `[56.63, 22.98, -1030.48] mg`，conservative offset 约 `[56.6, 23.0, -30.5] mg`。
- TIMU-004 总质量门仍 FAIL：只有 1 个 pose window，`pose_count`、`axis_coverage`、`motion_sanity` 和 `pose_or_motion_evidence` 未通过。
- PC Bridge 存储 123 条事件，recording 生成 120 条 `imu_motion` frame，quality gate PASS `0.94`，replay PASS。
- 本任务还修复了 Windows UTF-8 BOM JSONL 输入兼容，避免 PowerShell 捕获文件丢失首行 `hello`。

### 2.11 TIMU-004B QMI8658 manual three-pose capture

TIMU-004B adds `scripts/capture_amoled_qmi8658_pose_set.ps1` and
`docs/hardware/TIMU_004B_QMI8658_MANUAL_CAPTURE_20260623.md` as the repeatable
operator entry for QMI8658 manual pose or motion capture.

The script captures bounded `COM9` JSONL windows from `firmware/amoled_bridge`,
writes UTF-8 without BOM, waits for `amoled_bridge_done`, and can run
`scripts/analyze_imu_pose_quality.py`, `scripts/board_bridge.py`,
`scripts/session_recorder.py`, `scripts/inspect_session_recording.py`, and
`scripts/replay_session_recording.py`.

The live preflight
`pc_simulator/runtime/timu004b/timu004b-qmi8658-preflight-live-20260623-205520-z_negative.jsonl`
captured 123 JSONL records, including 120 `imu_sample` records, `imu_whoami`,
and `amoled_bridge_done`. The single `z_negative` pose passed static quality,
label match, calibration offset, and source-boundary checks; the M1 recording
quality gate passed with score `0.94`, and replay returned 120 `risk_type=none`
outputs.

The manual three-pose evidence set then added:

- `x_positive`:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-manual-pose1-20260623-2100-x_positive.jsonl`
- `y_positive`:
  `pc_simulator/runtime/timu004b/timu004b-qmi8658-manual-pose2-20260623-2108-y_positive.jsonl`

Together with the preflight `z_negative` window, TIMU-004B passed
`pose_static_quality`, `pose_count`, `axis_coverage`, `pose_label_match`,
`calibration_offset`, `pose_or_motion_evidence`, and `source_boundary`. The M1
combined loop stored 369 bridge events, produced 360 `imu_motion` frames, passed
quality gate with score `0.91`, and replayed 360 `risk_type=none` outputs.

This does not change the current hardware truth table by itself. The AMOLED
QMI8658 path remains `semi_verified`, with recorder frames marked
`source_availability=bridge_uplink` and `source_status=unverified`, because the
source is still a dual-board bridge path, no optional motion window was supplied,
and later hardware gates must verify mounting, FIFO/interrupt behavior, power,
and a real `platform_imu` backend.

### 2.12 TIMU-005 QMI8658 motion window capture

TIMU-005 reuses the TIMU-004B `z_negative`, `x_positive`, and `y_positive`
static pose windows, then adds one operator rotation/light-tap motion window on
the same `COM9` AMOLED QMI8658 bridge path. The repeatable report is
`docs/hardware/TIMU_005_QMI8658_MOTION_WINDOW_20260624.md`.

- `scripts/capture_amoled_qmi8658_pose_set.ps1` now supports `-MotionOnly` and
  `-ExistingPose LABEL=PATH`, so motion evidence can be captured without asking
  the operator to repeat already-saved static poses.
- Motion capture:
  `pc_simulator/runtime/timu005/timu005-qmi8658-motion-live-20260624-0001-motion.jsonl`.
- The motion window contains 123 JSONL records, including 120 `imu_sample`
  records, `imu_whoami`, and `amoled_bridge_done`.
- Timing cross-check stayed at about `49.99 ms / 20.00 Hz`, with
  `missed_deadlines=0` and `max_sample_work_ms=43`.
- Motion sanity passed: accel magnitude range about `490.04 mg`, gyro peak
  about `201921 mdps`, and overall pose/motion quality gates passed.
- The M1 combined loop stored 492 bridge events, produced 480 `imu_motion`
  frames, passed quality gate with score `0.91`, and replayed 480
  `risk_type=none` outputs.

Formal IMU acceptance remains false. The source is still
`bridge_uplink/unverified`; continuous long-window ODR/jitter/drop behavior,
product mounting convention, FIFO/interrupt behavior, power/current evidence,
and a real `platform_imu` backend still need separate validation.

### 2.13 TIMU-006 QMI8658 long-window capture

TIMU-006 makes the AMOLED bridge window configurable and captures one 600-sample
long window on `COM9`. The repeatable report is
`docs/hardware/TIMU_006_QMI8658_LONG_WINDOW_20260624.md`.

- `firmware/amoled_bridge/main/Kconfig.projbuild` adds
  `CONFIG_EGOLINK_AMOLED_SAMPLE_COUNT=600` and
  `CONFIG_EGOLINK_AMOLED_SAMPLE_INTERVAL_MS=50`.
- `pc_simulator/imu_quality.py` adds `--long-window`, a `long_window_timing`
  analysis mode, and a `device_jitter` gate.
- Live capture:
  `pc_simulator/runtime/timu006/timu006-qmi8658-long-window-live-20260624-0001-motion.jsonl`.
- The long window contains 603 JSONL records, including 600 `imu_sample`
  records, `imu_whoami`, and `amoled_bridge_done`.
- Completion record reports `samples_emitted=600`, `read_errors=0`,
  `not_ready_count=0`, `missed_deadlines=0`, and `max_sample_work_ms=42`.
- Long-window analyzer passed with observed mean interval about `49.9983 ms`,
  observed sample rate about `20.0007 Hz`, and max interval deviation `1.0 ms`
  under a `10.0 ms` jitter limit.
- The M1 loop stored 603 bridge events, produced 600 `imu_motion` frames,
  passed quality gate with score `0.94`, and replayed 600 `risk_type=none`
  outputs.

Formal IMU acceptance remains false. The source is still
`bridge_uplink/unverified`; product mounting convention, FIFO/interrupt
behavior, power/current evidence, repeated worn-like long windows, and a real
`platform_imu` backend still need separate validation.

### 2.14 TIMU-007 platform_imu backend boundary

TIMU-007 adds a backend boundary to `firmware/mqtt_heartbeat/components/platform_imu`
without changing the default P0 IMU truth table. The repeatable report is
`docs/hardware/TIMU_007_PLATFORM_IMU_REAL_BACKEND_POC_20260624.md`.

- `app_main.c` now calls `platform_imu_sample()` instead of directly calling
  `platform_imu_sample_mock()`.
- `platform_imu` now exposes backend metadata and a Kconfig choice:
  default `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_MOCK=y`, opt-in
  `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658=y`.
- The opt-in QMI8658 backend can probe WHOAMI and read accel/gyro samples over
  I2C, but probe/read failure falls back to mock data.
- Default `firmware/mqtt_heartbeat` build passed with the mock backend, so the
  P0 main board still reports `imu_hardware_present=false`,
  `imu_driver_enabled=false`, and `imu_sample_mock=true`.

Formal IMU acceptance remains false. TIMU-007 is a firmware boundary and build
gate, not a product-mounted real-backend live capture.

## 3. 传感器与能力矩阵

| 能力 | 料号 / 来源 | 接口 / 引脚 | 驱动状态 | 数据能力 | 功耗控制能力 | 真实 / Mock 状态 | M1 数据可用性与阻塞项 |
|---|---|---|---|---|---|---:|---|
| 设备在线状态 | ESP32-S3 + `firmware/mqtt_heartbeat` | Wi-Fi STA + MQTT；topic `ego/link/ego-link-001/status` | 固件已实现并刷写过；T038 live worker 已再次收到 status；HDATA-001 clean capture 收到 `seq=26/27/28/30` | `device_id`、`seq`、`uptime_ms`、RSSI、guard mode、queue size、mock modem/GNSS、电量字段、HPWR marker 字段 | 仅有心跳间隔；HPWR marker 是 log/mock，不是电流测量 | `verified` | 可进入 M1-002 recorder 作为设备日志；仍需固件版本、session_id、Unix time 和配置 manifest。 |
| 设备健康样本 | ESP32-S3 runtime | MQTT event topic `ego/link/ego-link-001/event`；`sensor_sample/device_health` | 固件已实现并收到真实上报；T038 收到 `seq=21548`；HDATA-001 clean capture 收到 `seq=25/29`；T039 live capture 收到 `seq=13/17/21` | uptime、Wi-Fi RSSI、free heap、minimum free heap、mock battery、mock modem/GNSS、HPWR marker 字段、IMU mock/ring 字段 | 只有固定上报间隔；无低功耗采样策略；power marker 未接仪器波形 | `verified` | 可作为当前唯一真实端侧结构化传感样本；其中 `imu_*` 和 battery 仍是 mock，不可用于真实运动/电源训练。 |
| Wi-Fi RSSI | ESP32-S3 Wi-Fi | `esp_wifi_sta_get_ap_info` | 固件已调用 | RSSI dBm，随 status / sensor_sample 上报 | 未实现 Wi-Fi 省电/断连状态统计 | `verified` | 可用于网络质量特征；后续需记录断连、重连、离线时长。 |
| Heap / runtime | ESP32-S3 runtime | ESP-IDF heap API | 固件已调用 | `free_heap_bytes`、`min_free_heap_bytes` | 无专门功耗控制 | `verified` | 可用于设备健康；不是用户安全传感器。 |
| BLE | ESP32-S3 片内能力 | 未在当前固件启用 | 无应用驱动 | 无 BLE 数据 | 无 | `not_verified` | 不进入 M1 数据集；若后续用于近场或配置，需要独立任务验证。 |
| 4G 数据链路 | SIM7670G-MNGV | PC 侧 USB AT / RNDIS；ESP32 侧控制链路未实现 | PC 侧 AT TCP/IP 栈曾验证公网访问；ESP32 固件未接入 | SIM、LTE 注册、分组数据附着、CSQ、AT TCP/IP 可用性 | 可通过 AT 电源/网络状态命令探测；尚无固件功耗状态机 | `pc_side_verified` | 可写入硬件验证报告，不作为端侧实时传感帧；阻塞项是 ESP32 侧 SIM7670G driver、弱网恢复和低功耗。 |
| RNDIS | SIM7670G USB composite | Windows Remote NDIS，曾获 `192.168.0.100/24` | PC 识别；外网指定源地址 ping/curl 曾超时 | 诊断网络接口 | 无固件控制 | `pc_side_verified` | 仅作 PC 侧诊断；业务不可依赖 PC RNDIS。 |
| SIM7670G GNSS no-fix | SIM7670G-MNGV | PC 侧 USB AT；`AT+CGNSSPWR`、`AT+CGNSSINFO`、`AT+CGPSINFO` | `scripts/sim7670_gnss_probe.py` 已实现 PC 侧探测；T038 `COM6/COM7` 均 AT 可达；HDATA-001 写入 `location_report seq=31` | 当前可记录 `fix=false`、`gnss_power_state=1`、satellites/raw response 等；室内未获得 fix | PC 脚本可开 GNSS 电源；无固件级 GNSS 启停策略 | `pc_side_verified` | 可验证协议闭环和 no-fix 记录；不可作为真实定位数据集。需要户外 fix、fix age、精度、速度和 ESP32 侧控制。 |
| Mock GNSS | 固件 / Dashboard mock | MQTT status/event 或 PC Simulator | 已用于协议和 UI | `gnss_state=mock_fix`、模拟 location | 无真实功耗 | `mock_only` | 仅用于协议/UI，不可用于定位模型训练；M1 必须显式标注 source。 |
| 摄像头多帧 smoke | Waveshare 板载/连接器摄像头；TCAM-001 UART 识别为 OV5640 | Y2-Y9=GPIO7-GPIO14，PCLK=GPIO46，VSYNC=GPIO42，HREF=GPIO41，XCLK=GPIO39，SIO_D=GPIO15，SIO_C=GPIO16；CAM DIP ON | `firmware/camera_smoke` 已完成 init 和 3 帧 JPEG smoke；证据见 `docs/hardware/TCAM_001_CAMERA_SMOKE_LIVE_CAPTURE_20260623.md`、`firmware/camera_smoke/main/app_main.c` 和 `firmware/camera_smoke/README.md`；当前运行固件是 camera smoke，不是 MQTT heartbeat | QVGA JPEG、size、checksum、SOI/EOI；3 帧实测 bytes `2893/3708/3700`；未进入统一 event log | 可按需启用；无摄像头电源域、隐私授权、保留期或哈希链路 | `semi_verified` | 可作为未来 VisionGate 候选；M1 recorder 暂不记录原始图像。需要 `platform_camera`、授权、哈希、功耗和按需采集策略。 |
| P0 主控板 IMU 加速度/陀螺仪 | Waveshare ESP32-S3-SIM7670G-4G 未确认；外部候选评估路径包括 `ST STEVAL-MKI227KA（LSM6DSV16X）` / `SensorTile.box PRO` | P0 4G 主控板未确认 I2C/SPI、引脚、安装方向 | P0 主控默认固件仍为 mock；TIMU-007 只增加 opt-in QMI8658 后端边界；TIMU-001 仅定义 bring-up 证据门 | P0 主控板无真实 accel/gyro；无真实采样率、抖动、缺帧 | 无低功耗中断、FIFO、唤醒策略 | `missing_or_unknown` | 当前 P0 4G 主控板无真实 IMU 证据。AMOLED QMI8658 是双板感知候选路径，TIMU-004B 三姿态静态质量门已通过，TIMU-005 motion window 已通过，TIMU-006 600 样本长窗口已通过，TIMU-007 已补后端边界；但这不是 P0 4G 主控板板载 IMU，也仍需显式后端 live capture、安装方向、FIFO/中断和功耗验收。 |
| AMOLED 板 QMI8658 IMU via PC Bridge | ESP32-S3-Touch-AMOLED-2.06；HDBRIDGE-002 live WHOAMI `0x05` | Native USB Serial/JTAG `COM9` JSONL；I2C SDA GPIO15 / SCL GPIO14；QMI8658 address `0x6B`；AXP2101 address `0x34` | `firmware/amoled_bridge` 已完成最小 I2C probe；TIMU-003 改为 `vTaskDelayUntil` 固定周期采样；TIMU-004A 新增 pose/motion analyzer；TIMU-004B 新增人工采集脚本并完成三姿态实采；TIMU-005 新增 motion-only capture 并完成旋转/轻敲 motion window；TIMU-006 新增可配置 600 样本长窗口和 `device_jitter` gate；TIMU-007 在 `platform_imu` 中加入 opt-in QMI8658 后端边界；PC Bridge / recorder / quality gate / replay 已通过 | `hello`、`imu_whoami`、每窗口 120 或 600 条 `imu_sample`；identity/completeness/static orientation/device timing PASS；目标 `50 ms / 20 Hz`，TIMU-006 实测 mean interval 约 `49.9983 ms`、sample rate 约 `20.0007 Hz`、max interval deviation `1.0 ms`；三姿态 total quality gates PASS；motion window `motion_sanity` PASS；来源仍为 `bridge_uplink/unverified`；`platform_imu` 后端尚无 live capture | 无 IMU 低功耗、中断、FIFO、唤醒或功耗波形；600 样本长窗口已提供但真实后端 live capture 未接入；三姿态 offset 仍是保守估计，不是最终产品安装校准 | `semi_verified` | 可作为 `platform_imu` real backend live capture 的输入证据之一；不得用于 MotionNet 训练、跌倒判断或正式 IMU 声明，直到真实后端、安装方向、FIFO/中断、功耗和后端 quality gate 通过。 |
| IMU platform backend boundary | `firmware/mqtt_heartbeat/components/platform_imu` | 默认 mock 后端；TIMU-007 新增显式 opt-in QMI8658 I2C backend Kconfig | T039 已实现 `platform_imu_init`、`platform_imu_push_sample`、`platform_imu_read_recent` 和 32 样本 ring buffer；TIMU-007 新增 `platform_imu_sample()`、后端 metadata、QMI8658 WHOAMI/read sample PoC；默认 build 仍为 mock | 默认 `mock_stationary` accel/gyro、ring count、dropped samples、latest seq；`sensor_sample/device_health` 默认仍是 `imu_hardware_present=false`、`imu_driver_enabled=false`、`imu_sample_mock=true` | 无真实 IMU 功耗；无 FIFO/中断/唤醒；QMI8658 后端未做 live capture | `mock_only` | 只用于保持 M1 recorder 字段形状和未来驱动边界；TIMU-007 不可用于 MotionNet 训练或真实跌倒/碰撞判断。 |
| 麦克风 / 音频 | 未确认；候选 PDM/I2S 麦克风 | 未确认 I2S/PDM/ADC、引脚、时钟 | 无驱动、无音频样本 | 无 VAD、音量、事件音频、clip ref | 无音频门控/环形缓冲功耗策略 | `missing_or_unknown` | 当前仓库无真实麦克风。阻塞 AudioGate；需确认硬件、采样率、隐私授权和短时缓冲。 |
| 物理 SOS 按键 | 产品要求存在；真实 GPIO 未确认 | 未确认 GPIO、上拉/下拉、消抖 | Dashboard/CLI 可模拟 SOS；真实按键 GPIO 未验证 | 模拟 `sos_pressed` 可进入 Safety flow | 物理按键低功耗唤醒未实现 | `not_verified` | 可验证规则基线，不代表真实 SOS 可靠性。阻塞硬安全路径验证。 |
| 串口 Safety CLI | ESP32-S3 固件 CLI | CH343 `COM4` | 固件提供 `safety status/demo normal/sos/impact` 静态测试路径 | deterministic mock safety input/output | 无功耗测量标记 | `semi_verified` | 可做接口 smoke；未写入统一 recorder。 |
| SD / 本地存储 | 板级 SD 能力未确认 | 未确认 SDMMC/SPI 引脚和卡状态 | 板级探测支持解析 SD 失败；当前未观察到挂载成功 | 无本地 session 持久化 | 无写入窗口/掉电恢复策略 | `not_verified` | 不可作为 M1 session 存储。需确认卡、供电、格式、引脚、挂载参数和异常恢复。 |
| SPI Flash / NVS | ESP32-S3 内部 flash | ESP-IDF NVS/分区；当前未作为 session recorder | P0 配置可用，M1 recorder 未实现固件存储 | 可作为小型队列/配置候选 | flash 写入功耗未测 | `semi_verified` | 可作为 SD 失败时的过渡存储候选，但需独立 recorder 任务验证。 |
| 电量 / 充电 | 真实电池、电量计、充电 IC 未确认 | 未确认 ADC/I2C fuel gauge/charger status | 当前固件固定 `battery=87`、`charging=false` | Mock battery_percent / charging | 无电源域控制、低电量策略和测量标记 | `mock_only` | `battery=87` 只能占位。阻塞低电量、续航和充电状态训练/策略验证。 |
| 电源控制 / 功耗状态 | 平台目标要求 48h 典型守护；PPK2 已作为仪器参考 | 未确认负载开关、模组 PWRKEY、电源域 GPIO | HPWR-001 已加入 log/mock `PLATFORM_POWER_EVENT`、状态累计时长和串口 marker；HDATA-001 live MQTT 已看到 `POWER_MARKER_000102` 到 `POWER_MARKER_000122`；未接真实电源硬件 | 可记录 `power_state`、elapsed/cumulative ms、`POWER_MARKER_<seq>`、GPIO marker disabled | 未实现真实睡眠策略、电源域控制、GPIO marker 翻转或仪器波形对齐 | `log_mock_only` | 可用于后续 PPK2 对齐模板；仍阻塞续航声明和真实功耗优化。 |
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
| `power_state` / `power_marker_seq` / `power_serial_marker_id` | HPWR-001 firmware payload | HDATA-001 已在 live MQTT 中看到；只能用于日志/仪器对齐，不能当作真实电流数据。 |
| `imu_source` / `imu_ring_count` / `imu_latest_seq` / `imu_accel_mg_*` / `imu_gyro_mdps_*` | T039 `platform_imu` mock payload | T039 live capture 已看到这些字段，但当前仍是 `mock_stationary`，`imu_hardware_present=false`，`imu_driver_enabled=false`，不可当作真实 IMU 样本。 |
| `imu_motion` | HDBRIDGE-001 / HDBRIDGE-002 PC Bridge / TIMU-002-TIMU-006 analyzer | TIMU-006 已有 QMI8658 live WHOAMI、20Hz 样本、`z_negative` / `x_positive` / `y_positive` 三姿态静态证据、motion window 证据和 600 样本长窗口证据，TIMU-007 已补 `platform_imu` 后端边界；最新 M1 recording 生成 600 条 `imu_motion` frame；recorder 中仍必须保留 `source_availability=bridge_uplink`、`source_status=unverified`；不是已完成真实后端 live capture、产品安装/FIFO/中断/功耗验收的数据。 |
| `safety_evaluation` / replay output | PC Safety Companion M0 | 规则基线输出，可用于闭环调试，不可作为真实安全标签。 |

## 5. 阻塞 M1 数据采集的缺失硬件或驱动

| 阻塞项 | 影响 | 建议下一步 |
|---|---|---|
| IMU 安装方向、校准和产品后端仍未验收 | HDBRIDGE-002 已确认 AMOLED QMI8658 身份和样本，TIMU-003 已修复 20Hz timing，TIMU-004A 已完成单姿态 `z_negative` 偏置估计，TIMU-004B 已完成三姿态静态质量门，TIMU-005 已完成 motion sanity，TIMU-006 已完成 600 样本长窗口 timing/jitter/drop 证据，TIMU-007 已完成 `platform_imu` 后端边界；但真实后端 live capture、FIFO/中断、功耗和产品安装约定仍未验收，仍无法作为 MotionNet 所需正式 accel/gyro 数据集。 | 下一步 TIMU-008 显式启用 QMI8658 后端并做 live capture；通过后仍需安装方向、低功耗、FIFO/中断和后端 quality gate。 |
| 麦克风硬件和音频链路未知 | 无法采集 AudioGate 数据或事件音频。 | 确认 PDM/I2S/ADC 麦克风和引脚；先定义隐私和短时缓冲边界。 |
| 真实物理 SOS GPIO 未验证 | SOS 硬安全路径仍是 Dashboard/CLI 模拟。 | 确认按键 GPIO、消抖、长按/短按、低功耗唤醒和误触策略。 |
| SD 挂载未验证 | 固件侧长 session 持久化和掉电恢复不可靠。 | 复测 SD 卡格式、供电、引脚和挂载参数；若继续失败，先用 SPI flash/NVS 或 PC 侧 recorder 过渡。 |
| ESP32 侧 SIM7670G 控制链路未实现 | 端侧无法直接采集真实 4G/GNSS 状态。 | 保留 PC AT probe 作为过渡；后续实现 `platform_modem` / `platform_gnss` 后端。 |
| 真实电池、电量计、充电和电源控制未知 | 不能验证低电量策略、续航和功耗预算。 | 明确电池/充电/电量计料号，加入电源状态事件和 PPK2/Otii 对齐标记。 |
| 统一时间与真实功耗波形仍未对齐 | HPWR-001 只提供 log/mock marker；没有 PPK2/Otii 原始波形时仍无法声明电流或续航。 | 使用 `POWER_MEASUREMENT_SCENARIO_TEMPLATE.md` 采集仪器波形；保留 monotonic + PC received_at + `PLATFORM_POWER_EVENT` 对齐字段。 |
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
- 当前 camera smoke 说明摄像头 OV5640 多帧 JPEG 采集可行，不说明 VisionGate、隐私授权、图像上传或事故视觉理解已完成。
- 48 小时和 5-7 天续航是工程目标，不是当前开发板或整机实测结论。
- 在 M1 数据质量门槛达成前，不进入 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter 效果声明。

## 8. 下一步

HCTX-001 后的建议顺序：

1. 下一步 TIMU-008：在 TIMU-007 后端边界基础上，选择目标板并显式启用 `CONFIG_EGOLINK_PLATFORM_IMU_BACKEND_QMI8658=y`，执行 `platform_imu` QMI8658 后端 live capture。
2. 后续真实 IMU 验收：TIMU-008 通过后仍需产品安装方向、校准、FIFO/DRDY 中断、功耗波形和后端 quality gate；模型训练/跌倒判断继续禁用，直到数据集质量门通过。
3. 后续 TSTOR/TMIC：确认 AMOLED 或 4G 板 TF/SD、麦克风链路和隐私/短缓冲边界。
4. 后续 HDATA：在户外/靠窗环境复测 SIM7670G GNSS fix，并继续把 clean recording 作为 M1 数据质量入口。
5. 后续 HPWR：接入 PPK2/Otii 或等价仪器，把 `POWER_MARKER_<seq>` 与真实电流波形对齐。

T038 硬件可用性 smoke、HDATA-001 live capture、T039 IMU mock/ring skeleton、TIMU-001 real IMU bring-up evidence gate、TCAM-001 camera smoke live capture、HDBRIDGE-001 dual-board PC bridge PoC、HDBRIDGE-002 AMOLED QMI8658 live window、TIMU-002 QMI8658 sample quality gate、TIMU-003 QMI8658 timing retest、TIMU-004A single-pose quality gate、TIMU-004B manual three-pose capture、TIMU-005 motion window capture、TIMU-006 long window capture 和 TIMU-007 platform_imu backend boundary 已完成，但它们只确认当前开发板最小闭环、未来 IMU 接口形状、真实 IMU 验收门、独立摄像头 smoke、PC 侧双板消息桥、AMOLED QMI8658 身份/样本、20Hz timing、单姿态 `z_negative`、三姿态静态证据、一次 motion sanity 证据、600 样本 timing/jitter/drop 证据和默认 mock/显式 QMI8658 后端边界可继续推进；真实后端 live capture、安装方向/校准/FIFO/中断/功耗、麦克风、物理 SOS GPIO、SD、真实电量/充电、真实功耗波形、产品固件摄像头路径和 ESP32 侧 SIM7670G 控制链路仍需后续任务逐项验证。

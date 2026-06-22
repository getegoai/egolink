# Ego Link Hardware Usability Validation

更新时间：2026-06-22

## 目的

本报告记录 T038 硬件可用性 smoke 验证结果。目标不是扩展新驱动，而是确认当前开发板、SIM7670G、GNSS 查询、MQTT 上报、PC Simulator 落盘、session quality gate 和 replay 是否形成可继续开发的闭环。

## 验证环境

- 主机：Windows 11，Python 3.13.13。
- 开发板：Waveshare ESP32-S3-SIM7670G-4G。
- ESP32 串口：`COM4`，CH343。
- SIM7670G AT 候选口：`COM6` / `COM7`。
- MQTT broker：用户态 LAN Mosquitto，`192.168.31.250:1883`。
- 设备连接：broker 上观察到开发板连接 `192.168.31.12 -> 192.168.31.250:1883`。

## 运行命令与结果

### 板级探测

```powershell
python scripts\egolink_board_probe.py --probe-all-sim-ports --esp-listen-seconds 8
```

结果：通过，报告写入 `reports/board_validation/20260622-181619/probe.md`。

- `esp32_ch343_serial_present`: PASS，ESP32-S3 CH343 为 `COM4`。
- `sim7670_usb_serial_present`: PASS，SIM7670G 串口为 `COM6, COM8, COM7, COM5`。
- `sim7670_rndis_adapter_present`: PASS，RNDIS 网卡可见。
- `sim7670_at_identity`: PASS，`COM6` / `COM7` 均识别为 `SIM7670G-MNGV`。
- SIM 卡状态：`sim_not_inserted=False`，`COM6` / `COM7` 均已注册并分组附着，CSQ 分别为 `21,0` 和 `20,0`。
- ESP32 日志：观察到 `MQTT_HEARTBEAT_PUBLISH_OK`，topic 为 `ego/link/ego-link-001/status`。

### GNSS 探测

```powershell
python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2
```

结果：通过，报告写入 `reports/gnss_validation/20260622-181804/gnss_probe.md`。

- `COM6` / `COM7` 均 AT 可达，型号为 `SIM7670G-MNGV`。
- `gnss_power_state=1`。
- 室内未获得 GNSS fix，`AT+CGNSSINFO` 返回 no-fix。
- 已写入 `location_report` 事件，`fix=false`、`gnss_state=no_fix`、`source=sim7670g_gnss`。

### MQTT 接收与 Safety 处理

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --max-messages 3 --wait-seconds 90 --process-safety --safety-process-limit 30
```

结果：通过。

- PC 侧 worker 从 LAN broker 收到并存储 3 条 MQTT 消息。
- 当前 event log 中可见：
  - `mqtt_status seq=21547`，`received_at=2026-06-22T10:20:32.794276+00:00`。
  - `sensor_sample/device_health seq=21548`，`wifi_rssi=-34`，`free_heap_bytes=264972`，`received_at=2026-06-22T10:20:40.924497+00:00`。
  - `mqtt_status seq=21549`，`received_at=2026-06-22T10:20:42.824169+00:00`。
- Safety 处理产生 `risk_type=none` 的 `safety_evaluation`，没有生成真实外部副作用。

注意：本机同时存在 loopback broker 和 LAN broker。设备连接的是 `192.168.31.250:1883`，PC worker 验证时必须连接该地址；连接 `127.0.0.1:1883` 会订阅到另一个 broker 实例，无法收到开发板消息。

### Session 记录、质量门与回放

```powershell
python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t038-hardware-usability-smoke --output-dir pc_simulator\runtime\recordings\t038-hardware-usability-smoke --limit 12 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --json
```

结果：通过。

- Recording：12 条 source events，5 条 sensor frames，7 条 events。
- Quality gate：PASS，`quality_score=0.91`，`errors=0`，`warnings=3`。
- Replay：PASS，12 条 timeline records，6 条 replayed inputs，1 条 `manual_sos`，5 条 `none`，生成 1 条模拟 `base_command`。

## 当前可用结论

- 开发板枚举可用：ESP32 `COM4`、SIM7670G AT 口、RNDIS 均可识别。
- SIM/4G 基础状态可用：SIM 已插入，LTE 注册和分组附着成功。
- ESP32 到 PC 的 MQTT 上报可用：status 和 `sensor_sample/device_health` 能进入 PC Simulator event log。
- PC 侧 GNSS 查询可用：能打开/读取 SIM7670G GNSS 状态并写入 no-fix `location_report`。
- M1 数据基础闭环可用：当前硬件事件可以生成 recording，通过 quality gate，并可 replay。

## 仍未可用或未验证

- GNSS 当前只有室内 no-fix；尚未验证户外真实经纬度、精度、速度和 fix age。
- ESP32 固件尚未直接控制 SIM7670G LTE/GNSS；当前 4G/GNSS 真实探测仍是 PC USB AT 侧。
- 当前运行固件不是 `camera_smoke`，本次未验证摄像头图像采集。
- SD 挂载未观察到成功。
- IMU、麦克风、真实物理 SOS GPIO、真实电量/充电、电源状态和功耗标记仍未验证。
- `battery=87`、`charging=false`、`modem_state=mock_data_ready`、`gnss_state=mock_fix` 仍是当前 MQTT 固件里的 mock/占位字段。

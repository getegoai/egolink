# CURRENT_TASK: T038 Hardware Usability Smoke Validation

## 任务目标

验证当前插入开发板后的最小硬件闭环是否可继续开发：板级枚举、SIM/4G 状态、GNSS 查询、MQTT 上报、PC Simulator 落盘、session quality gate 和 replay。

## 范围

- 运行 `scripts/egolink_board_probe.py`，确认 ESP32-S3 CH343、SIM7670G USB composite、RNDIS、AT 身份和当前 ESP32 MQTT 日志。
- 运行 `scripts/sim7670_gnss_probe.py`，确认 SIM7670G GNSS AT 查询是否可达，并写入 `location_report`。
- 运行 `pc_simulator/mqtt_worker.py` 连接 LAN broker，确认真实固件 status / `sensor_sample/device_health` 能进入 `pc_simulator/runtime/events.jsonl`。
- 从当前 event log 生成 `t038-hardware-usability-smoke` recording，并运行 quality gate / replay。
- 更新硬件可用性报告、状态文档、硬件矩阵和集成报告。

## 不做

- 不刷机、不新增固件驱动、不修改硬件连接。
- 不拨号、不发短信、不打电话、不访问外部业务服务。
- 不启动摄像头拍照、不录音录像。
- 不把室内 GNSS no-fix 解释为真实定位能力已验证。
- 不把 mock 电量、mock GNSS、mock modem 状态当成真实传感器数据。

## 允许修改路径

- `docs/hardware/HARDWARE_USABILITY_VALIDATION.md`
- `docs/hardware/**`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python scripts\egolink_board_probe.py --probe-all-sim-ports --esp-listen-seconds 8
python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --max-messages 3 --wait-seconds 90 --process-safety --safety-process-limit 30
python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t038-hardware-usability-smoke --output-dir pc_simulator\runtime\recordings\t038-hardware-usability-smoke --limit 12 --json
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --json
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --json
python -m unittest quality_tests.test_hardware_sensor_matrix -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 板级探测通过，报告为 `reports/board_validation/20260622-181619/probe.md`。ESP32-S3 CH343 为 `COM4`；SIM7670G AT 身份在 `COM6` / `COM7` 可达；RNDIS 可见；SIM 已插入，LTE registered/attached 为 true。
- GNSS 探测通过，报告为 `reports/gnss_validation/20260622-181804/gnss_probe.md`。`COM6` / `COM7` 均 AT 可达，`gnss_power_state=1`，室内 no-fix，已写入 `location_report fix=false`。
- MQTT worker 连接 `192.168.31.250:1883` 通过，收到并落盘 3 条开发板 MQTT 消息，包括 `sensor_sample/device_health seq=21548`。
- 已确认本机存在两个 broker 实例：设备连接 LAN broker，后续 live worker 必须使用 `192.168.31.250:1883`。
- 已生成 `pc_simulator/runtime/recordings/t038-hardware-usability-smoke`，记录 12 条 source events、5 条 sensor frames、7 条 events。
- Quality gate 通过：`quality_score=0.91`、`errors=0`、`warnings=3`。
- Replay 通过：12 条 timeline records、6 条 replayed inputs、1 条 `manual_sos`、5 条 `none`、1 条模拟 `base_command`。
- 已新增 `docs/hardware/HARDWARE_USABILITY_VALIDATION.md` 并同步更新硬件矩阵、状态文档和集成报告。

## 完成标准

- [x] 板级枚举和 SIM/4G 基础状态可用。
- [x] GNSS AT 查询可用，并能写入 no-fix `location_report`。
- [x] MQTT status / `sensor_sample/device_health` 可从开发板进入 PC Simulator event log。
- [x] 当前事件可生成 recording，通过 quality gate 并 replay。
- [x] 未验证能力继续明确标记为未验证或 mock。
- [x] HCTX/T038 focused 测试通过。
- [x] 全量验证通过。

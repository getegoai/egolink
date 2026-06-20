# CURRENT_TASK：T019 固件采集传感器数据上报

## 任务目标

在现有 `firmware/mqtt_heartbeat` 基础上增加传感器/设备观测数据采集与 MQTT event 上报，让开发板除了心跳 `status` 外，还能周期性发布 `sensor_sample` 事件到 `ego/link/ego-link-001/event`。

## 范围

- 增加 `CONFIG_EGOLINK_EVENT_TOPIC`；
- 增加 `CONFIG_EGOLINK_SENSOR_EVENT_INTERVAL_SEC`；
- 固件采集 ESP32 当前可稳定读取的设备健康数据：
  - uptime；
  - Wi-Fi RSSI；
  - free heap；
  - minimum free heap；
  - mock battery / modem / GNSS 状态；
- 将采集结果封装为 `message_type=event`、`event_type=sensor_sample`、`sensor_kind=device_health`；
- 发布到 `ego/link/ego-link-001/event`；
- 保留原有 `status` heartbeat；
- Dashboard 事件详情展示 `sensor_sample` 的 `sensor_kind`、`wifi_rssi`、`free_heap_bytes`；
- 补充固件静态测试；
- 更新固件 README 和项目状态记录。

## 不做

- 不在本任务中接入 SIM7670G GNSS AT 驱动；
- 不接入真实电量 ADC；
- 不接入 IMU；
- 不修改 PC 端 MQTT worker / Dashboard 的核心逻辑；
- 不接入云端 EGO Base。

## 允许修改路径

- `firmware/mqtt_heartbeat/main/app_main.c`
- `firmware/mqtt_heartbeat/main/Kconfig.projbuild`
- `firmware/mqtt_heartbeat/sdkconfig`
- `firmware/mqtt_heartbeat/README.md`
- `pc_simulator/app.py`
- `quality_tests/test_mqtt_heartbeat_firmware.py`
- `quality_tests/test_pc_simulator.py`
- `README.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_mqtt_heartbeat_firmware -v
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
& "C:\Espressif\tools\ninja\1.12.1\ninja.exe" -C build
```

硬件验证命令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_mosquitto_lan.ps1 -BrokerIp 192.168.31.250 -Restart
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --max-messages 1 --wait-seconds 60
cd firmware\mqtt_heartbeat
idf.py -p COM4 flash
```

## 执行结果

- 固件已新增 `sensor_task`；
- `sensor_task` 周期由 `CONFIG_EGOLINK_SENSOR_EVENT_INTERVAL_SEC` 控制，当前默认 30 秒；
- 新增 `build_sensor_payload()`，上报 `sensor_sample` / `device_health`；
- 新增 `MQTT_SENSOR_PUBLISH_OK` 日志；
- Dashboard 已增加 `sensor_sample` 详情展示逻辑，显示 `sensor_kind`、RSSI 和 heap；
- 新增 `quality_tests/test_mqtt_heartbeat_firmware.py`；
- `python -m unittest quality_tests.test_mqtt_heartbeat_firmware -v` 通过，3 个测试全部成功；
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` 通过，30 个测试全部成功；
- ESP-IDF 环境可用，`ninja -C build` 增量编译通过，生成 `egolink_mqtt_heartbeat.bin`；
- `Get-PnpDevice -PresentOnly` 找到 ESP32-S3 CH343 串口 `COM4`；
- `idf.py -p COM4 flash` 通过，芯片识别为 ESP32-S3，固件写入并 hard reset；
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --max-messages 1 --wait-seconds 90` 通过，收到真实固件 `sensor_sample`；
- `pc_simulator/runtime/events.jsonl` 中真实样例：`event_type=sensor_sample`、`sensor_kind=device_health`、`wifi_rssi=-53`、`free_heap_bytes=265332`、`min_free_heap_bytes=256308`；
- Dashboard `/api/state` 最新事件已显示真实 `sensor_sample`；
- 已知技术债：`scripts/egolink_board_probe.py` 当前仍漏识别 PnP 中存在的 CH343 `COM4`，最新报告 `reports/board_validation/20260620-211839/probe.md` 仍显示该脚本质量门失败。

## 完成标准

- 固件代码和配置完成；
- 固件静态测试通过；
- ESP-IDF 编译通过；
- 开发板 ESP32 刷写完成；
- PC Simulator MQTT worker 收到真实 `sensor_sample`；
- Dashboard 事件流显示真实 `sensor_sample`。

# CURRENT_TASK：T018 MQTT event / ack 闭环

## 任务目标

扩展 PC Simulator MQTT worker 与 Dashboard 事件闭环，支持 `ego/link/+/event` 和 `ego/link/+/ack`，让 SOS / 唤醒 / 定位上报与命令确认进入同一个事件日志和看板事件流。

## 范围

- MQTT worker 默认订阅 `ego/link/+/status`、`ego/link/+/event`、`ego/link/+/ack`；
- `--topic` 支持重复传入，用于只订阅部分主题；
- worker 解析并校验 `message_type=status/event/ack`；
- status 写入为 `event_type=mqtt_status`；
- ack 写入为 `event_type=mqtt_ack`；
- event 保留设备上报的 `event_type`，并补充 `direction=uplink`；
- Dashboard 事件列表展示 `cmd_id`、`status`、`keyword` 等事件细节；
- 补充 worker 和 PC Simulator 单元测试；
- 更新 README 和状态记录。

## 不做

- 不改当前固件的 status heartbeat；
- 不实现真实 SOS / 唤醒 / 定位固件上报；
- 不实现下行命令 MQTT 发布；
- 不引入 Python MQTT 第三方依赖；
- 不接入云端 EGO Base。

## 允许修改路径

- `pc_simulator/mqtt_worker.py`
- `pc_simulator/app.py`
- `quality_tests/test_mqtt_worker.py`
- `quality_tests/test_pc_simulator.py`
- `README.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_mqtt_worker -v
python -m unittest quality_tests.test_pc_simulator -v
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
python pc_simulator\mqtt_worker.py --help
```

真实 broker smoke test：

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --topic ego/link/+/ack --max-messages 2 --wait-seconds 20
```

发布 JSON smoke payload 时，Windows 下优先使用 `mosquitto_pub -s` 从标准输入发送，避免 `-m` 参数传递时 JSON 双引号被剥离。

## 执行结果

- `pc_simulator/mqtt_worker.py` 已支持 status / event / ack 三类消息；
- worker 默认订阅三类 topic，仍支持 `--topic` 重复覆盖订阅范围；
- `quality_tests/test_mqtt_worker.py` 增加 event / ack 解析、默认 topic 和混合落盘覆盖；
- `quality_tests/test_pc_simulator.py` 增加 event / ack 日志进入 `/api/state` 的覆盖；
- Dashboard 事件 Detail 会显示 `cmd_id`、`status`、`keyword` 等字段；
- `python -m unittest quality_tests.test_mqtt_worker -v` 通过，8 个测试全部成功；
- `python -m unittest quality_tests.test_pc_simulator -v` 通过，5 个测试全部成功；
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` 通过，26 个测试全部成功；
- 实测 worker 订阅 `event` / `ack` topic 后，通过 Mosquitto 发布模拟 `sos_pressed` 和 `ack`，成功写入 JSONL；
- 默认 Dashboard 事件流已显示 `mqtt_ack`、`wake_detected`、`mqtt_status`。

## 完成标准

- worker 可处理 status / event / ack；
- Dashboard / `/api/state` 可展示 event / ack；
- 全量测试通过；
- 真实 broker smoke test 通过；
- `docs/STATUS.md` 记录 T018 结果和下一项建议任务。

# CURRENT_TASK：T016 PC Simulator MQTT worker

## 任务目标

实现电脑端 MQTT worker，订阅设备状态主题 `ego/link/+/status`，把开发板上报的 status JSON 写入 PC Simulator 事件日志，形成“设备发布 -> 本机接收 -> JSONL 留痕”的最小闭环。

## 范围

- 新增 `pc_simulator/mqtt_worker.py`；
- 复用本机已安装的 Mosquitto CLI，不引入新的 Python MQTT 依赖；
- 支持默认订阅 `ego/link/+/status`；
- 支持 Windows 默认安装路径 `C:\Program Files\mosquitto\mosquitto_sub.exe`；
- 将合法 status 消息写入 `pc_simulator/runtime/events.jsonl`；
- 为解析、命令构造和 JSONL 落盘补充单元测试；
- 更新 README 和状态记录中的运行入口。

## 不做

- 不改固件发布格式；
- 不接入正式云端 EGO Base；
- 不引入 LangGraph、AutoGen、CrewAI 等多智能体框架；
- 不把 worker 做成 Windows 服务或后台守护进程；
- 不处理下行命令订阅，后续任务单独实现。

## 允许修改路径

- `pc_simulator/mqtt_worker.py`
- `pc_simulator/app.py`
- `quality_tests/test_mqtt_worker.py`
- `README.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_mqtt_worker -v
python pc_simulator\mqtt_worker.py --help
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

可选硬件闭环验证：

```powershell
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/status --max-messages 1 --wait-seconds 45
```

## 执行结果

- `pc_simulator/mqtt_worker.py` 已实现；
- worker 使用 `mosquitto_sub -v` 获取 topic 和 payload；
- status 消息会补充 `event_type=mqtt_status`、`mqtt_topic`、`ingest_source`、`received_at` 后写入 JSONL；
- 无效行和非 status 消息会跳过并输出错误提示；
- `pc_simulator/app.py` 已补充直接脚本运行时的包路径兼容。
- `python -m unittest quality_tests.test_mqtt_worker -v` 通过，5 个测试全部成功；
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` 通过，21 个测试全部成功；
- 实测 `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/status --max-messages 1 --wait-seconds 20` 通过，收到 `device_id=ego-link-001`、`seq=2446`、`event_type=mqtt_status` 的真实开发板 status。

## 完成标准

- 新增单元测试通过；
- 全量 `scripts/verify.ps1` 通过；
- README 中可以看到 worker 运行命令；
- `docs/STATUS.md` 记录 T016 结果和下一项建议任务。

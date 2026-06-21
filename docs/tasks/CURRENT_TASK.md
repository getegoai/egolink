# CURRENT_TASK: T028 Supervised Live MQTT Safety Processing

## 任务目标

为 PC Simulator MQTT worker 增加可开关的监督式 Safety 处理模式：收到真实/半真实 MQTT 消息并写入事件日志后，可立即扫描最近事件并执行 Safety Companion flow，生成 `safety_evaluation`、必要的 `safety_event` 和无副作用模拟 command。

## 范围

- 在 `pc_simulator/mqtt_worker.py` 增加 `--process-safety` 开关。
- 增加 `--safety-process-limit`，控制每次 MQTT 入库后扫描的最近事件数量。
- 保持默认 MQTT ingester 行为不变：不开开关时只写事件日志。
- Safety 处理失败时只写入 stderr 诊断，不阻塞后续 MQTT 消息入库。
- 增加单元测试覆盖 after-store hook、失败隔离、参数解析和处理进度输出。
- 更新状态文档和集成报告。

## 不做

- 不修改 Safety Companion M0 模型包规则。
- 不把 GNSS no-fix 私自提升为模型风险。
- 不真实拨号、拍照、录音或访问外网。
- 不把 worker 做成 Windows 服务或长期后台守护；本轮只提供可显式启动的监督式处理模式。
- 不引入 LangGraph、AutoGen、CrewAI 等额外智能体框架。

## 允许修改路径

- `pc_simulator/mqtt_worker.py`
- `quality_tests/test_mqtt_worker.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_mqtt_worker -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --max-messages 1 --wait-seconds 90 --process-safety --safety-process-limit 20
```

## 执行结果

- `pc_simulator/mqtt_worker.py` 新增 `--process-safety` 和 `--safety-process-limit`。
- `consume_lines()` 新增 after-store hook；只对成功入库的 MQTT 事件触发，坏行不会触发。
- Safety 处理异常会写入 stderr，并保持 MQTT 入库继续执行。
- 真实 live MQTT 验证通过：收到 ESP32-S3 固件 `sensor_sample seq=9064`，worker 立即写入 1 条 `safety_evaluation`，`risk_type=none`。
- Dashboard API 幂等验证通过：对已处理的 live `sensor_sample` 再执行 `POST /api/safety/process-events` 返回 `processed=0`。
- SIM7670G GNSS no-fix 验证通过：报告见 `reports/gnss_validation/20260621-161721/gnss_probe.md`，写入 `location_report fix=false`。
- 模拟 SOS + GNSS no-fix 批处理验证通过：`POST /api/safety/process-events` 处理 2 个源事件，写入 2 条 `safety_evaluation`、1 条 `safety_event`、1 条无副作用模拟 command。
- `python -m unittest quality_tests.test_mqtt_worker -v` 通过，12 个测试成功。
- `python -m unittest quality_tests.test_safety_companion quality_tests.test_pc_simulator -v` 通过，26 个测试成功。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，87 个测试成功。
- Dashboard 已重启到最新代码，运行在 `http://127.0.0.1:8787`，PID `44568`。

## 完成标准

- [x] MQTT worker 可通过 `--process-safety` 启用入库后 Safety 处理。
- [x] 默认 MQTT worker 行为保持不变。
- [x] Safety 处理失败不阻断 MQTT 事件入库。
- [x] 测试覆盖新增监督式处理路径。
- [x] 文档记录运行方式、验证结果和剩余限制。

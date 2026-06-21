# CURRENT_TASK: T027 Real Event Safety Companion Flow

## 任务目标

把真实/半真实设备事件接入 Safety Companion 流程：MQTT `sensor_sample`、SOS/模拟 SOS、GNSS no-fix 等事件可以转换为标准 `sensor_frame`，经过 M0 router 得到 `model_output`，并在 PC Simulator 事件流中记录处理结果。

## 范围

- 支持单个设备事件评估：`safety_companion.evaluate_event(event, device)`。
- 支持判断可评估事件：`sensor_sample`、`location_report`、`sos_pressed`、`wake_detected`、`impact_detected` 等。
- 支持从事件日志批处理未处理事件。
- 新增 `POST /api/safety/process-events`。
- 对所有进入 Safety flow 的真实/半真实事件写入 `safety_evaluation`。
- 对非 `none` 输出继续写入 `safety_event` 和无副作用模拟命令。
- Dashboard 事件详情可展示 `safety_evaluation`。

## 不做

- 不修改模型包规则。
- 不把 GNSS no-fix 私自提升为模型风险。
- 不真实拨号、拍照、录音或访问外网。
- 不启动连续后台 worker；本轮只做 bounded process pass。

## 允许修改路径

- `pc_simulator/safety_companion.py`
- `pc_simulator/app.py`
- `quality_tests/test_safety_companion.py`
- `quality_tests/test_pc_simulator.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_safety_companion quality_tests.test_pc_simulator -v
python scripts\verify_safety_companion_m0.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- `sensor_sample` 中的 `wifi_rssi` 已映射为 `sensor_frame.sensors.network.rssi_dbm`。
- `location_report fix=false` 已映射为 `sensor_frame.sensors.location.fix_valid=false`，但不会被 adapter 私自提升为模型风险。
- `sos_pressed` 可生成 `manual_sos`、`safety_event` 和无副作用模拟 `ask_user` command。
- `POST /api/safety/process-events` 可处理最近事件日志，跳过已处理的 source event，避免重复写入。
- 真实/半真实日志验证：最近 20 条事件中处理 12 条可评估事件，写入 12 条 `safety_evaluation`、3 条 `safety_event`、3 条模拟 command。
- `python -m unittest quality_tests.test_safety_companion quality_tests.test_pc_simulator -v` 通过，26 个测试成功。
- `python scripts\verify_safety_companion_m0.py` 通过。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，83 个测试成功。

## 完成标准

- [x] 真实 `sensor_sample` 可进入 Safety Companion 输入。
- [x] GNSS no-fix 可进入 Safety Companion 输入且保留为 no-fix 状态。
- [x] SOS/模拟 SOS 可生成模型输出、安全事件和模拟命令。
- [x] PC Simulator 可记录 `safety_evaluation`。
- [x] 事件日志处理具备幂等性。
- [x] 无真实硬件、通信和安全动作副作用。

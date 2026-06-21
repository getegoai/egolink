# CURRENT_TASK: T023 PC Simulator Safety Companion Adapter

## 任务目标

实现 PC Simulator 侧 Safety Companion adapter，把现有事件转换为 `model_input`，并用确定性的 mock router 返回 `model_output`，先跑通模型接口闭环。

## 范围

- 新增 `pc_simulator/safety_companion.py`。
- 将 `sos_pressed`、`wake_detected`、`location_report`、`sensor_sample` 等事件映射为 `shared/contracts/model_input.schema.json` 兼容结构。
- 增加确定性 mock `model_output`：
  - SOS -> `manual_sos` / `escalate_emergency`
  - GNSS no-fix -> `device_risk` / `upload_summary`
  - 低电量 -> `device_risk` / `local_reminder`
  - wake -> `none` / `ask_user`
- `/api/state` 返回 `safety_companion.model_input` 和 `safety_companion.model_output`。
- Dashboard 显示风险类型、分数、建议动作和 reason codes。
- 新增 adapter 单元测试和 PC Simulator 回归测试。
- 更新集成报告和状态记录。

## 不做

- 不引入真实模型。
- 不引入模型训练代码。
- 不引入 ESP-DL、ESP-SR、TFLite Micro。
- 不改变固件运行行为。
- 不改变 MQTT topic 或设备上报格式。
- 不把 mock router 的输出解释为模型准确率。

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
python -m unittest quality_tests.test_safety_companion -v
python -m unittest quality_tests.test_pc_simulator -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 已新增 `pc_simulator/safety_companion.py`，输出契约版本 `safety-companion.contract.v0.1`。
- 已将 `/api/state` 扩展为返回 `safety_companion` 字段。
- 已在 Dashboard 增加 Safety 区块，展示 risk、score、action、reasons。
- 已新增 `quality_tests/test_safety_companion.py`，覆盖 SOS、GNSS no-fix、wake、低电量和时间戳转换。
- 已扩展 `quality_tests/test_pc_simulator.py`，确认 snapshot 包含 Safety Companion 输出。
- `python -m unittest quality_tests.test_safety_companion -v` 通过，5 个测试成功。
- `python -m unittest quality_tests.test_pc_simulator -v` 通过，9 个测试成功。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，54 个测试全部成功。
- 已重启 Dashboard，当前 `http://127.0.0.1:8787/api/state` 返回：
  - `active_event=location_report`
  - `safety_risk=device_risk`
  - `safety_action=upload_summary`
  - `reasons=gnss_no_fix`

## 完成标准

- [x] 现有 PC Simulator 事件可转换为 `model_input`。
- [x] mock router 可返回 `model_output`。
- [x] `/api/state` 和 Dashboard 可看到 Safety Companion 输出。
- [x] 单元测试和全量验证通过。
- [x] 明确记录该结果只验证接口闭环，不验证模型准确率。

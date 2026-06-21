# CURRENT_TASK: T024 Safety Companion M0 PC Simulator Adapter

## 任务目标

完成 `M0-INT-002`：让 PC Simulator 能接受 `sensor_frame` 或 `model_input`，调用 Safety Companion M0 包中的规则基线，并返回标准 `model_output`。非 `none` 结果可转换为 `safety_event`。

## 范围

- 替换旧的 PC 侧本地 mock router。
- `pc_simulator/safety_companion.py` 必须调用：
  - `model_lab.safety_companion.RuleRouter`
  - `model_lab.safety_companion.build_model_input`
- 新增 `evaluate_sensor_frame(sensor_frame)`。
- 新增 `evaluate_model_input(model_input)`。
- 新增 `/api/safety/evaluate` HTTP 入口。
- `/api/state` 继续返回 Dashboard 需要的 `safety_companion` 输出。
- 新增/更新单元测试，覆盖官方场景、传感器帧、隐私证据过滤和 HTTP 入口。

## 不做

- 不复制模型包规则到 PC Simulator。
- 不修改 `model_lab/**`、`model_artifacts/**`、`shared/contracts/**` 的语义。
- 不引入训练代码或第三方智能体框架。
- 不把合成场景通过描述成真实安全识别效果。
- 不在 adapter 中私自新增模型包没有定义的风险类型。

## 允许修改路径

- `pc_simulator/safety_companion.py`
- `pc_simulator/app.py`
- `quality_tests/test_safety_companion.py`
- `quality_tests/test_pc_simulator.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/modeling/INTEGRATION_ISSUES.md`
- `PACKAGE_MANIFEST.json`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_safety_companion quality_tests.test_pc_simulator -v
python scripts\verify_safety_companion_m0.py
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- `pc_simulator/safety_companion.py` 已改为薄适配层，调用模型包 `RuleRouter` / `build_model_input`。
- 已支持 `evaluate_sensor_frame(sensor_frame)` 和 `evaluate_model_input(model_input)`。
- 已支持 `POST /api/safety/evaluate`，输入错误返回明确 400 JSON。
- 非 `none` 输出可通过包内 `build_safety_event` 转换为 `safety_event`。
- `/api/state` 仍返回 `safety_companion`，供 Dashboard 展示 risk、score、action、reasons。
- 已记录差异：旧 T023 mock 会把 GNSS no-fix 作为 `device_risk`；官方 M0 包没有这条规则，当前 adapter 不私自提升为模型风险。
- `python -m unittest quality_tests.test_safety_companion quality_tests.test_pc_simulator -v` 通过，19 个测试成功。
- `python scripts\verify_safety_companion_m0.py` 通过。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，71 个测试成功。

## 完成标准

- [x] PC Simulator 可处理标准 `model_input`。
- [x] PC Simulator 可处理标准 `sensor_frame`。
- [x] 适配器调用模型包 API，不复制规则。
- [x] 新增可测试 HTTP 入口 `/api/safety/evaluate`。
- [x] 输入验证失败返回明确错误。
- [x] 覆盖正常步行、手动 SOS、撞击后静止、隐私模式证据过滤。
- [x] 模型包自检和项目全量验证通过。

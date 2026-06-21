# CURRENT_TASK: T026 Safety Companion M0 Simulated End-to-End Flow

## 任务目标

完成 `M0-INT-004`：跑通模拟传感器状态 -> `model_output` -> `safety_event` -> PC Simulator 记录/展示 -> 模拟 `base_command` 的端到端闭环。

## 范围

- 使用包内场景：
  - `normal_walk`
  - `manual_sos`
  - `post_impact_inactivity`
  - `privacy_restricted_impact`
- `none` 结果不生成 `safety_event`。
- 非 `none` 结果生成标准 `safety_event`。
- 对 `ask_user` 和 `urgent_escalation` 生成模拟 `base_command`。
- PC Simulator 可通过 `POST /api/safety/replay` 重放场景并写入事件流。
- Dashboard 事件详情展示 risk、action、evidence、privacy 信息。

## 不做

- 不真实拨号。
- 不真实拍照。
- 不真实录音。
- 不访问外网。
- 不声明合成场景通过等于真实安全识别准确率。

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

- 已新增 `safety_companion.replay_scenarios()`，默认重放 4 个 M0 场景。
- 已新增模拟 `base_command` 生成：
  - `ask_user` -> command `ask_user`
  - `urgent_escalation` -> command `ask_user` with emergency safety class
- 模拟命令带 `simulated=true` 和 `no_external_side_effects=true`。
- 已新增 `POST /api/safety/replay`。
- Replay 会持久化 3 个 `safety_event` 和 3 个 `command_sent` 记录。
- `normal_walk` 不生成 `safety_event` 或 `base_command`。
- `privacy_restricted_impact` 不请求原始音频和图片证据。
- `python -m unittest quality_tests.test_safety_companion quality_tests.test_pc_simulator -v` 通过，22 个测试成功。
- `python scripts\verify_safety_companion_m0.py` 通过。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，79 个测试成功。

## 完成标准

- [x] 自动测试可重放完整闭环。
- [x] 所有模型输出、安全事件和模拟命令符合契约。
- [x] 隐私模式下不产生原始音频/图像采集请求。
- [x] 无真实硬件、通信和安全动作副作用。

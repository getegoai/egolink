# CURRENT_TASK: T036 M1-004 PC Session Import / Replay

## 任务目标

为通过完整性校验的 M1 `recording/` 目录增加 PC 侧 import / replay 能力。目标是按录制文件重建 sensor frames / events 时间线，将可评估记录转换为 Safety Companion M0 `sensor_frame` / `model_input`，调用现有 `RuleRouter`，并生成可追溯的 replay report。

## 范围

- 新增 `pc_simulator/session_replay.py`。
- 新增 `scripts/replay_session_recording.py` CLI。
- replay 默认先运行 T033/T035 quality gate；质量门失败时拒绝回放。
- 按 `seq` / timestamp / 文件内顺序合并 `sensor_frames.jsonl` 和 `events.jsonl`。
- 将录制记录重建为模型契约 `sensor_frame`，来源标记为 `replay`。
- 调用现有 Safety Companion M0 `RuleRouter`，生成 `model_input`、`model_output`、可选 `safety_event` 和无副作用模拟 `base_command`。
- 跳过 `safety_evaluation`、`safety_event`、`command_sent` 等派生记录，避免重复评估历史输出。
- 写入 `session_replay_report.json` 和 `session_replay_report.md`。
- 增加测试覆盖成功回放、质量门失败拒绝回放、报告写入和 CLI。
- 更新状态文档和集成报告。

## 不做

- 不训练 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter。
- 不修改 `shared/contracts/**`、`model_lab/**` 或模型阈值。
- 不新增固件 recorder、不实现掉电恢复或采样窗口完整率。
- 不新增固件驱动、不刷机、不访问串口、不运行新的硬件探测。
- 不真实拨号、拍照、录音或访问外网。
- 不把 IMU、麦克风、真实物理 SOS、电量或 SD 标记为真实可用。
- 不实现 annotation CLI / UI。
- 不把 PC replay 结果声明为真实跌倒、呼救或事故识别准确率验证。

## 允许修改路径

- `pc_simulator/session_replay.py`
- `scripts/replay_session_recording.py`
- `quality_tests/test_session_replay.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_session_replay -v
python scripts\replay_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 已新增 `pc_simulator/session_replay.py`，可读取完整性校验通过的 recording 并重建 replay 时间线。
- 已新增 `scripts/replay_session_recording.py`，默认写入 `session_replay_report.json` / `.md`。
- replay 默认先运行 quality gate；当文件哈希或大小不匹配时拒绝执行模型回放。
- replay 会把录制的 `sensor_frame` / 可评估事件转换为 Safety Companion M0 契约帧，调用 `RuleRouter`，并在报告中保留 source event key、模型输入、模型输出、可选 safety event 和模拟 command。
- 派生记录 `safety_evaluation`、`safety_event`、`command_sent` 会被标记为 `derived_record` 并跳过，避免重复消费历史输出。
- 验证通过：`python -m unittest quality_tests.test_session_replay -v`，4 个测试成功。
- smoke replay 通过：`python scripts\replay_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke` 返回 `PASS replayed_inputs=37 safety_events=9 skipped=23`。
- 验证通过：`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`，107 个测试成功。

## 完成标准

- [x] replay 先检查 recording quality / integrity，失败时拒绝默认回放。
- [x] replay 按 recording 重建 sensor frames / events 时间线。
- [x] replay 为可评估记录生成模型契约输入并调用现有 RuleRouter。
- [x] replay report 输出 JSON / Markdown，并保留 source key 到结果的追溯关系。
- [x] 测试覆盖成功路径、篡改拒绝、报告写入和 CLI。
- [x] 全量验证通过。

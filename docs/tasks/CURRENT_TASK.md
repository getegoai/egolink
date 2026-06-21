# CURRENT_TASK: T030 Unified AutoDev And Device Monitor

## 任务目标

把 AutoDev 开发任务进度与本地设备 / Safety flow 状态合并到同一个观察入口。运行 `watch_autodev.ps1` 时，不只看到 Codex/AutoDev 的任务、阶段、空闲时间和文件变化，也能同时看到最近本地会话中的 Dashboard、broker、Safety evaluation、safety_event、模拟 command 和最新风险动作。

## 范围

- 扩展 `scripts/autodev.py watch`，读取最新 `pc_simulator/runtime/sessions/*/session_summary.json`。
- 如果没有 session summary，则从 `pc_simulator/runtime/events.jsonl` 生成只读 fallback 摘要。
- `scripts/autodev.py status` 也显示本地设备 / Safety flow 快照。
- `scripts/watch_autodev.ps1` 增加 `-NoLocalSession` 和 `-LocalSessionSummary` 参数。
- 增加 AutoDev supervisor 测试覆盖本地 session summary 读取和 event-log fallback。
- 更新 `docs/AUTODEV_MONITORING.md`、`docs/STATUS.md`、`docs/modeling/INTEGRATION_REPORT.md` 和 `README.md`。
- 纳入新增模型上下文文档，并明确下一步按 M1 数据基础推进。

## 不做

- 不启动新的长期后台服务。
- 不修改 AutoDev 执行 loop、任务选择、提交策略或失败回滚策略。
- 不修改 Safety Companion M0 模型包规则、契约字段或固件。
- 不训练 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter。
- 不真实拨号、拍照、录音或访问外网。

## 允许修改路径

- `scripts/autodev.py`
- `scripts/watch_autodev.ps1`
- `autodev/tests/test_supervisor.py`
- `docs/AUTODEV_MONITORING.md`
- `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
- `docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`
- `README.md`

## 验证命令

```powershell
python -m unittest autodev.tests.test_supervisor -v
python scripts\autodev.py watch --once --no-clear --events 4
powershell -ExecutionPolicy Bypass -File scripts\watch_autodev.ps1 -Once -NoClear -RecentEvents 4
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- `watch` 已显示 `LOCAL DEVICE / SAFETY SESSION` 区块。
- `watch` 默认读取最新 `session_summary.json`；没有 session summary 时可从 `events.jsonl` 生成 fallback。
- `watch_autodev.ps1` 已支持 `-NoLocalSession` 和 `-LocalSessionSummary <path>`。
- `status` 已显示本地设备 / Safety flow 快照。
- 新增模型上下文文档已纳入项目入口；下一步建议从 M1-001 硬件与传感器矩阵开始。
- `README.md` 已恢复为项目入口，并加入本地监督会话和模型上下文链接。
- `python -m unittest autodev.tests.test_supervisor -v` 通过，15 个测试成功。
- `python scripts\autodev.py watch --once --no-clear --events 4` 通过，显示 AutoDev 状态和本地 Safety 摘要。
- `powershell -ExecutionPolicy Bypass -File scripts\watch_autodev.ps1 -Once -NoClear -RecentEvents 4` 通过。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，90 个测试成功。

## 完成标准

- [x] AutoDev watch 同屏显示开发进度和设备 / Safety 状态。
- [x] 没有本地 session summary 时有只读 event-log fallback。
- [x] PowerShell wrapper 暴露本地 session 相关开关。
- [x] AutoDev supervisor 测试覆盖新增读取逻辑。
- [x] README 和监控文档记录新的统一观察入口。
- [x] 下一步路线对齐新增 M1 数据基础文档。

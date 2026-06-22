# CURRENT_TASK: T034 M1-004-pre Quality Gate Monitor Integration

## 任务目标

把 T033 session quality gate 接入本地监督会话脚本和 AutoDev/local monitor。每次生成 `recording/` 后自动运行 inspector，并在会话日志、AutoDev `watch` / `status` 的本地设备区块显示 PASS/FAIL、quality score、errors、warnings 和报告路径。

## 范围

- 扩展 `scripts/start_local_supervised_session.ps1`，在 recorder 后自动运行 `scripts/inspect_session_recording.py`。
- 会话日志输出 quality gate 摘要，并保留 `-NoQualityGate` 跳过开关。
- 扩展 `scripts/autodev.py`，读取 `session_summary.json` 同目录下的 `recording/session_quality_report.json`。
- AutoDev `watch` / `status` 的 `LOCAL DEVICE / SAFETY SESSION` 区块显示 Quality 和 Report 行。
- 增加测试覆盖 AutoDev 读取 quality gate 摘要，以及会话脚本包含 inspector 调用和跳过开关。
- 更新状态文档和集成报告。

## 不做

- 不训练 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter。
- 不修改 `shared/contracts/**`、`model_lab/**` 或模型阈值。
- 不新增固件驱动、不刷机、不访问串口、不运行新的硬件探测。
- 不真实拨号、拍照、录音或访问外网。
- 不声称 M0 规则模拟已经验证真实跌倒、呼救或事故识别能力。
- 不把 IMU、麦克风、真实物理 SOS、电量或 SD 标记为真实可用。
- 不实现 session replay、文件哈希、IMU 环形缓冲或用户标注 UI。
- 不让 quality gate 启动任何硬件或网络动作。

## 允许修改路径

- `scripts/start_local_supervised_session.ps1`
- `scripts/autodev.py`
- `autodev/tests/test_supervisor.py`
- `quality_tests/test_local_session_summary.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest autodev.tests.test_supervisor quality_tests.test_local_session_summary -v
powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker
python scripts\autodev.py watch --once --no-clear --events 4
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 已扩展 `scripts/start_local_supervised_session.ps1`，在生成 `recording/` 后自动运行 `scripts/inspect_session_recording.py`。
- 本地监督会话脚本新增 `-NoQualityGate` 跳过开关；当 quality gate 失败时记录 exit code，但不删除会话证据。
- 会话日志已输出 quality gate 摘要：`Quality gate: PASS score=0.85 errors=0 warnings=5`。
- 已扩展 `scripts/autodev.py`，读取 `session_summary.json` 同目录下的 `recording/session_quality_report.json`。
- AutoDev `watch` / `status` 的 `LOCAL DEVICE / SAFETY SESSION` 区块已显示 `Quality` 和 `Report` 行。
- no-start 本地会话验证通过，生成 `pc_simulator/runtime/sessions/20260621-211742/recording/session_quality_report.md`。
- `python scripts\autodev.py watch --once --no-clear --events 4` 验证通过，显示 `Quality   : PASS score=0.85 errors=0 warnings=5 frames=11 events=27`。
- `python scripts\autodev.py status` 验证通过，显示相同 Quality/Report 摘要。
- 验证通过：`python -m unittest autodev.tests.test_supervisor quality_tests.test_local_session_summary -v`，19 个测试成功。
- 验证通过：`powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker`。
- 验证通过：`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`，102 个测试成功。

## 完成标准

- [x] 本地监督会话脚本自动运行 quality gate 并写入报告。
- [x] 本地监督会话脚本日志显示 PASS/FAIL、score、errors、warnings。
- [x] 可用 `-NoQualityGate` 跳过自动质量门。
- [x] AutoDev `watch` / `status` 显示 Quality 和 Report。
- [x] 测试和全量验证通过。

# CURRENT_TASK: T035 M1-004-pre Session File Integrity

## 任务目标

为 T032/T033 的 session recording 增加 SHA-256 文件完整性记录，并让 quality gate 校验这些哈希。目标是在 replay/import、模型输入重建和标注之前，确保 `session_manifest.json`、`sensor_frames.jsonl`、`events.jsonl`、`annotations.jsonl` 和摘要文件可追溯且未被静默修改。

## 范围

- 扩展 `pc_simulator/session_recorder.py`，生成 `file_manifest.json`。
- `file_manifest.json` 记录 session 关键文件的相对路径、size bytes 和 SHA-256。
- `session_manifest.json` 的 `outputs` 中记录 `file_manifest.json`。
- 扩展 `pc_simulator/session_inspector.py`，把 `file_manifest.json` 作为必需文件。
- quality gate 校验 file manifest schema、hash algorithm、必需条目、文件大小和 SHA-256。
- 增加测试覆盖 file manifest 生成、CLI 输出、manifest 被改、JSONL 被改和 hash mismatch。
- 更新状态文档和集成报告。

## 不做

- 不训练 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter。
- 不修改 `shared/contracts/**`、`model_lab/**` 或模型阈值。
- 不新增固件驱动、不刷机、不访问串口、不运行新的硬件探测。
- 不真实拨号、拍照、录音或访问外网。
- 不声称 M0 规则模拟已经验证真实跌倒、呼救或事故识别能力。
- 不把 IMU、麦克风、真实物理 SOS、电量或 SD 标记为真实可用。
- 不实现 session replay、IMU 环形缓冲或用户标注 UI。
- 不让 hashing 或 quality gate 启动任何硬件或网络动作。

## 允许修改路径

- `pc_simulator/session_recorder.py`
- `pc_simulator/session_inspector.py`
- `quality_tests/test_session_recorder.py`
- `quality_tests/test_session_inspector.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_session_recorder quality_tests.test_session_inspector -v
python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t035-integrity-smoke --output-dir pc_simulator\runtime\recordings\t035-integrity-smoke
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 已扩展 `pc_simulator/session_recorder.py`，每次写入 recording 时生成 `file_manifest.json`。
- `file_manifest.json` 记录 `session_manifest.json`、`sensor_frames.jsonl`、`events.jsonl`、`annotations.jsonl` 和 `session_recording.md` 的相对路径、size bytes 和 SHA-256。
- `session_manifest.json` 的 `outputs.file_manifest` 已指向 `file_manifest.json`。
- 已扩展 `pc_simulator/session_inspector.py`，把 `file_manifest.json` 作为必需文件并校验 schema、hash algorithm、必需条目、文件大小和 SHA-256。
- 已新增/更新测试，覆盖 file manifest 生成、CLI 输出、manifest 被修改、events JSONL 被篡改和 hash mismatch。
- smoke recording 已生成：`pc_simulator/runtime/recordings/t035-integrity-smoke/`，包含 `file_manifest.json`；inspector 返回 `PASS quality_score=0.85 errors=0 warnings=5`。
- 验证通过：`python -m unittest quality_tests.test_session_recorder quality_tests.test_session_inspector -v`，9 个测试成功。
- 验证通过：`python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t035-integrity-smoke --output-dir pc_simulator\runtime\recordings\t035-integrity-smoke`。
- 验证通过：`python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke`。
- 验证通过：`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`，103 个测试成功。

## 完成标准

- [x] recorder 生成 `file_manifest.json`。
- [x] `file_manifest.json` 包含 session manifest、sensor frames、events、annotations 和 summary 的 SHA-256。
- [x] inspector 校验 file manifest 必需条目、文件大小和 SHA-256。
- [x] 文件缺失、大小不匹配或 hash mismatch 时 quality gate 失败。
- [x] 测试和全量验证通过。

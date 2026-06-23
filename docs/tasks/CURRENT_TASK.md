# CURRENT_TASK: T037 / M1-005 Minimal Session Annotation CLI

## 任务目标

为已录制的 M1 session 增加最小人工/用户标签入口。CLI 应能查看可标注 target，向 `annotations.jsonl` 追加结构化标签，并同步刷新 `session_manifest.json`、`session_recording.md` 和 `file_manifest.json`，保证 quality gate / replay 仍可通过并能读取 annotation 摘要。

## 范围

- 新增 session annotation 库函数，支持 `safe`、`needs_help`、`false_alarm`、`cancelled`、`no_response` 五类标签。
- 新增 `scripts/annotate_session_recording.py`，支持 `--list-targets`、`--source-event-key`、`--target-index`、`--label`、`--notes` 和 consent/training 选项。
- 追加 annotation 后自动刷新：
  - `annotations.jsonl`
  - `session_manifest.json` 中的 `record_counts.annotations`
  - `session_recording.md`
  - `file_manifest.json` 中的 SHA-256 和文件大小。
- 扩展 quality gate，让 `session_quality_report` 输出 `annotation_labels`、`annotation_outcomes` 和 `annotator_types` 摘要。
- 扩展 replay report，让 `session_replay_report` 输出 annotation 摘要。
- 对真实 T038 recording 只运行 `--list-targets`，不替用户创建真实人工标签。

## 不做

- 不做 Web 标注页面。
- 不把 Codex smoke 标签写成用户真实确认标签。
- 不启动硬件、broker、摄像头、麦克风、拨号或外部服务。
- 不引入训练流水线，不训练 MotionNet / AudioGate / VisionGate。
- 不修改正式 `shared/contracts/safety_annotation.schema.json`。

## 允许修改路径

- `pc_simulator/session_annotations.py`
- `pc_simulator/session_inspector.py`
- `pc_simulator/session_replay.py`
- `scripts/annotate_session_recording.py`
- `quality_tests/test_session_annotations.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_session_annotations quality_tests.test_session_inspector quality_tests.test_session_replay -v
python scripts\annotate_session_recording.py pc_simulator\runtime\recordings\t038-hardware-usability-smoke --list-targets --json
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 已新增 `pc_simulator/session_annotations.py`，实现 target 列表、annotation 构建、追加写入、manifest/summary/file manifest 刷新和 annotation 摘要统计。
- 已新增 `scripts/annotate_session_recording.py`。
- 已扩展 `pc_simulator/session_inspector.py`，quality report 可读取 annotation 标签、结果和标注者类型摘要；有 annotation 时不再产生 `annotations_empty` warning。
- 已扩展 `pc_simulator/session_replay.py`，replay report 可读取 annotation 摘要。
- 已新增 `quality_tests/test_session_annotations.py`，覆盖追加 annotation 后质量门通过、哈希不失效、CLI 通过 index 追加、replay report 读取摘要。
- 已对真实 T038 recording 运行只读 target 列表，确认 index 4 为 `sensor_sample/device_health seq=21548`；未写入真实用户标签。

## 完成标准

- [x] CLI 可列出可标注 target。
- [x] CLI 可通过 source key 或 target index 追加 annotation。
- [x] 追加 annotation 后 manifest count 和 file manifest hash 自动刷新。
- [x] Quality gate 可读取 annotation 摘要并保持通过。
- [x] Replay report 可读取 annotation 摘要。
- [x] 不伪造真实用户标签。
- [x] Focused 测试通过。
- [x] 全量验证通过。

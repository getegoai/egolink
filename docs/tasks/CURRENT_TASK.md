# CURRENT_TASK: T033 M1-004-pre Session Inspector Quality Gate

## 任务目标

建立 PC 侧 session inspector / quality gate：导入 T032 生成的 `recording/` 目录，校验 manifest、JSONL、record count、source key、seq / timestamp、隐私字段和传感源边界，并输出质量报告。该任务用于在进入 IMU 环形缓冲、回放和模型训练前先把数据包质量门补齐。

## 范围

- 新增 `pc_simulator/session_inspector.py`，读取 T032 recording 目录并生成结构化质量报告。
- 新增 `scripts/inspect_session_recording.py` CLI，默认写入 `session_quality_report.json` 和 `session_quality_report.md`。
- 检查必需文件：`session_manifest.json`、`sensor_frames.jsonl`、`events.jsonl`、`annotations.jsonl`。
- 检查 manifest schema、record counts、privacy、sensor_sources 和未验证传感器 availability。
- 检查 JSONL 行格式、frame/event 类型、source_event_key 唯一性、seq/timestamp 回退 warning。
- 修正 recorder `source_event_key`，包含 timestamp，避免不同来源 seq 重置时碰撞。
- 增加单元测试覆盖通过/失败质量门、重复 source key、report 写入和 CLI。
- 更新状态文档和集成报告。

## 不做

- 不训练 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter。
- 不修改 `shared/contracts/**`、`model_lab/**` 或模型阈值。
- 不新增固件驱动、不刷机、不访问串口、不运行新的硬件探测。
- 不真实拨号、拍照、录音或访问外网。
- 不声称 M0 规则模拟已经验证真实跌倒、呼救或事故识别能力。
- 不把 IMU、麦克风、真实物理 SOS、电量或 SD 标记为真实可用。
- 不实现 session replay、文件哈希、IMU 环形缓冲或用户标注 UI。

## 允许修改路径

- `pc_simulator/session_inspector.py`
- `pc_simulator/session_recorder.py`
- `scripts/inspect_session_recording.py`
- `quality_tests/test_session_inspector.py`
- `quality_tests/test_session_recorder.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_session_inspector quality_tests.test_session_recorder -v
python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t033-quality-smoke --output-dir pc_simulator\runtime\recordings\t033-quality-smoke
python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t033-quality-smoke
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 已新增 `pc_simulator/session_inspector.py`，可读取 T032 `recording/` 目录并生成结构化质量报告。
- 已新增 `scripts/inspect_session_recording.py`，默认写入 `session_quality_report.json` 和 `session_quality_report.md`；质量门通过返回 0，失败返回非 0。
- 已检查必需文件、manifest schema、record counts、privacy、sensor_sources、JSONL 行、frame/event 类型、source_event_key 唯一性、seq/timestamp 回退。
- 已修正 recorder `source_event_key`，在 seq 之外加入 timestamp，避免真实 MQTT、Dashboard 模拟和 Safety 派生事件的 seq 重置造成碰撞。
- 已新增 `quality_tests/test_session_inspector.py`，覆盖有效 recording、record count mismatch、未验证 source 被标记 real、重复 source key、报告写入和 CLI。
- smoke recording 已生成：`pc_simulator/runtime/recordings/t033-quality-smoke/`，包含 19 条 sensor frames、41 条关键 events、0 条 annotations。
- smoke inspector 通过：`PASS quality_score=0.85 errors=0 warnings=5`；warning 包括 firmware version unknown、annotations empty，以及历史 event log 中 Safety 派生事件 seq 回退。
- 验证通过：`python -m unittest quality_tests.test_session_inspector quality_tests.test_session_recorder -v`，8 个测试成功。
- 验证通过：`python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t033-quality-smoke --output-dir pc_simulator\runtime\recordings\t033-quality-smoke`。
- 验证通过：`python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t033-quality-smoke`。
- 验证通过：`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`，102 个测试成功。

## 完成标准

- [x] inspector 可读取 recording 目录并生成 JSON/Markdown 质量报告。
- [x] 必需文件、manifest、JSONL 和 record counts 校验可产生明确 error。
- [x] 未验证传感器被标记为 real 时质量门失败。
- [x] source_event_key 重复时质量门失败。
- [x] annotations 为空、firmware version unknown、seq/timestamp 回退只作为 warning。
- [x] CLI 对通过质量门返回 0，对失败质量门返回非 0。
- [x] 测试和全量验证通过。

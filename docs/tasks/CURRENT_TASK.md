# CURRENT_TASK: T032 M1-002 Session Recorder Skeleton

## 任务目标

建立 Safety Companion M1 数据基础的最小 session recorder 骨架：从现有 PC Simulator `events.jsonl` 派生可复现的 session 数据目录，写入 manifest、结构化 sensor frames、关键 events 和 annotations 占位，同时保持未验证传感器显式不可用。

## 范围

- 新增 `pc_simulator/session_recorder.py`，提供从 event log 构建 session recording 的核心函数。
- 新增 `scripts/session_recorder.py` CLI，可输出 `session_manifest.json`、`sensor_frames.jsonl`、`events.jsonl`、`annotations.jsonl` 和 Markdown 摘要。
- 将 `scripts/start_local_supervised_session.ps1` 接入 recorder，默认在 session 目录下生成 `recording/`，并提供跳过开关。
- recorder 只记录当前矩阵允许的真实/PC 侧/模拟边界：`sensor_sample/device_health`、`mqtt_status`、PC AT GNSS no-fix、模拟 SOS、安全评估和模拟 command。
- manifest 必须标注 IMU、麦克风、真实物理按键、SD、真实电量和 ESP32 侧 SIM7670G 控制仍不可用或未验证。
- 增加单元测试覆盖 manifest、JSONL 输出、CLI 路径和 PowerShell session runner 契约。
- 更新状态文档和集成报告。

## 不做

- 不训练 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter。
- 不修改 `shared/contracts/**`、`model_lab/**` 或模型阈值。
- 不新增固件驱动、不刷机、不访问串口、不运行新的硬件探测。
- 不真实拨号、拍照、录音或访问外网。
- 不声称 M0 规则模拟已经验证真实跌倒、呼救或事故识别能力。
- 不把 IMU、麦克风、真实物理 SOS、电量或 SD 标记为真实可用。

## 允许修改路径

- `pc_simulator/session_recorder.py`
- `scripts/session_recorder.py`
- `scripts/start_local_supervised_session.ps1`
- `quality_tests/test_session_recorder.py`
- `quality_tests/test_local_session_summary.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_session_recorder quality_tests.test_local_session_summary -v
powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 已新增 `pc_simulator/session_recorder.py`，可从 PC Simulator event log 构建 M1 session recording。
- 已新增 `scripts/session_recorder.py`，可输出 `session_manifest.json`、`sensor_frames.jsonl`、`events.jsonl`、`annotations.jsonl` 和 `session_recording.md`。
- 已把 `scripts/start_local_supervised_session.ps1` 接入 recorder，默认在 session 目录下生成 `recording/`；可用 `-NoRecorder` 跳过。
- manifest 已标注 `sensor_sample/device_health`、`mqtt_status`、Wi-Fi RSSI、PC 侧 SIM7670G GNSS、Mock GNSS、Safety Companion M0、摄像头 smoke、IMU、麦克风、真实 SOS GPIO、SD、真实电量和 ESP32 侧 SIM7670G 控制链路的 availability/status。
- `sensor_frames.jsonl` 当前只从结构化 `mqtt_status`、`sensor_sample/device_health` 和 PC AT GNSS `location_report` 派生，不启动真实录音、拍照或新硬件 I/O。
- `events.jsonl` 当前记录 `sos_pressed`、`wake_detected`、`safety_evaluation`、`safety_event` 和 `command_sent` 等关键事件。
- `annotations.jsonl` 已作为空占位创建，后续 M1-005 接入用户反馈/人工标注。
- no-start 本地会话验证通过，生成 `pc_simulator/runtime/sessions/20260621-201911/recording/session_recording.md`；本次最近 40 条 event log 派生出 11 条 sensor frames、27 条关键事件、0 条 annotations。
- 验证通过：`python -m unittest quality_tests.test_session_recorder quality_tests.test_local_session_summary -v`，6 个测试成功。
- 验证通过：`powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker`。
- 验证通过：`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`，97 个测试成功。

## 完成标准

- [x] recorder 可从 event log 生成完整 session 目录。
- [x] manifest 包含设备、固件/契约、隐私、传感源 availability 和输出文件清单。
- [x] `sensor_frames.jsonl` 只包含已允许的结构化状态/设备健康/GNSS no-fix 帧。
- [x] `events.jsonl` 保留 SOS、安全评估、安全事件和模拟 command 等关键事件。
- [x] `annotations.jsonl` 作为空占位创建，后续 M1-005 接入用户反馈。
- [x] 本地监督会话脚本可生成 recorder 输出，并可通过开关跳过。
- [x] 测试和全量验证通过。

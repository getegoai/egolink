# Safety Companion contracts 1.0.0 and P0 message-hub contracts

这些文件是 Ego Link 固件、PC Simulator、未来 Ego Base、模型训练代码和 P0 message hub 之间的稳定接口。

| 文件 | 含义 |
|---|---|
| `sensor_frame.schema.json` | 设备或模拟器产生的带时间戳传感器帧 |
| `model_input.schema.json` | 端侧风险路由器的归一化输入 |
| `model_output.schema.json` | 风险类型、分数、动作与证据请求 |
| `safety_event.schema.json` | 发往 PC Simulator / Ego Base 的安全事件 |
| `base_command.schema.json` | PC Simulator / Ego Base 下发给设备的命令 |
| `safety_annotation.schema.json` | 数据标注与用户确认结果 |
| `message_hub_status.schema.json` | P0 message hub heartbeat/status envelope |
| `message_hub_event.schema.json` | P0 message hub telemetry/event envelope, including additive `location_observation` groups |
| `message_hub_command.schema.json` | P0 message hub downlink command envelope |
| `message_hub_ack.schema.json` | P0 message hub command ACK envelope |
| `message_hub_error.schema.json` | P0 message hub diagnosable error envelope |
| `message_hub_raw_frame_record.schema.json` | P0 raw-frame storage and parse-result record; the device wire payload is not JSON |
| `location_fusion_sample.schema.json` | DATA-001 JSONL dataset sample contract for location fusion exports |
| `imu_window_chunk.schema.json` | Normalized complete KV wire object for one bounded real-QMI IMU chunk over exact lowercase `lte` or `wifi`; sample bytes remain Base64 and training-disabled. |
| `imu_window_manifest.schema.json` | Normalized complete KV wire object for a bounded real-QMI IMU window manifest over exact lowercase `lte` or `wifi`, including its privacy/quality gates. |
| `imu_calibration_artifact.schema.json` | A0-001 六面 accelerometer bias/sensitivity 与独立 signed gyro-bias 工程校准 artifact；绑定设备、固件、安装、来源窗口及 hashes，并固定 `production_ready=false` / `training_allowed=false`。 |
| `imu_calibrated_window.schema.json` | `imu_window_export.v1` 的非覆盖式 calibrated JSONL 派生视图；逐样本保留原始未校准 mg/mdps，并添加 calibrated mg/mdps 与 SI 值。 |
| `sensor_time_lineage.schema.json` | A0-002 的逐 observation 时间血缘合同；显式区分源时间、boot-scoped monotonic ns、UTC、receive/ingest UTC、alignment/uncertainty 与不可变来源。 |
| `clock_mapping_segment.schema.json` | A0-002 的 boot-scoped monotonic→UTC 有界映射段；绑定原点、显式 UTC rate correction、有效区间、可复算 anchors、fit error、uncertainty 与来源证据。 |

## 变更规则

1. 修正文档或添加可选字段，可发布兼容补丁版本。
2. 删除字段、修改单位、修改枚举含义、修改必填属性，必须提升主版本。
3. 传感器原始数组不是模型接口的必需输入；端侧模型主要消费归一化特征。
4. 既有 1.0.0 模型/传感器合同继续使用 Unix 毫秒。A0-002 时间血缘合同使用
   boot-scoped monotonic nanoseconds 和显式 UTC，同时原样保留 legacy/source
   值与单位；不得以 receive/ingest time 回填缺失的 source time。
5. 速度使用 m/s，距离使用 m，角度使用 degree，音频幅度使用 dBFS。
6. 原始音频和图像是否保留必须服从 `privacy_mode` 和用户授权。
7. P0 message hub 当前协议版本为 `egolink.p0.v1`，必须兼容既有
   `status` / `event` / `command` / `ack` 行为；新增字段优先兼容追加。

# Safety Companion contracts 1.0.0 and P0 message-hub contracts

这些文件是 Ego Link 固件、PC Simulator、未来 Ego Base、模型训练代码和 P0 message hub 之间的稳定接口。

## ADR-0016 / Sprint 1 合同边界

- `P0-LOC`、`P0-CALL`、`P0-SOS` 当前全部为 `NOT_RUN`。Schema、fixture、
  replay 或单元测试通过，只证明对应合同/工具切片，不代表产品 Gate 通过。
- 设备端 Location Engine v0 / Sensor Policy v0 拥有断网时仍需工作的最小
  operational state；服务器保存版本化镜像、事件时间轴、回放、比较和更丰富的
  derived fusion。两者的 belief/generator/config identity 不得静默互相覆盖。
- 语义排序使用 source event time + boot-scoped monotonic + 显式 clock mapping。
  `receive_time` / `ingest_time` 只记录传输过程，不能回填或代替缺失的事件时间；
  顺序不明确的数据必须显式标记/排除。
- `SOS-010` 复用 `safety_event.schema.json` 与 persistent priority outbox，不新建
  第二套 SOS truth record。Guardian delivery/ack、Ego Call request/signaling/media
  各自保持真实独立状态。
- Ego Call media 不经过 Message Hub。[ADR-0016](../../docs/architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
  已确定原生蜂窝主通话、RTC 可选辅助；CALL-030/031 负责主路可行性与产品验收。
  既有 RTC 信令合同仍服务暂停的 CALL-020/021，不是原生电话协议。
  自营公共 PSTN/SIP 网关、SMS 与公共应急调度仍不在本轮范围。
- L2/AI 先消费隐私审查后的数据与 event-time replay，进入 offline/Shadow
  comparison；Camera 仅是可选实验观测，不能产生或否决 P0 决策。

| 文件 | 含义 |
|---|---|
| `sensor_frame.schema.json` | 设备或模拟器产生的带时间戳传感器帧 |
| `model_input.schema.json` | 端侧风险路由器的归一化输入 |
| `model_output.schema.json` | 风险类型、分数、动作与证据请求 |
| `safety_event.schema.json` | 发往 PC Simulator / Ego Base 的安全事件 |
| `base_command.schema.json` | PC Simulator / Ego Base 下发给设备的命令 |
| `safety_annotation.schema.json` | 数据标注与用户确认结果 |
| `guardian_device_bindings_v0.schema.json` | P0 Guardian-to-device exact-location authorization; stores only lowercase SHA-256 token digests and never grants device ingest or general admin access. |
| `message_hub_status.schema.json` | P0 message hub heartbeat/status envelope |
| `message_hub_event.schema.json` | P0 message hub telemetry/event envelope, including additive `location_observation` groups |
| `message_hub_command.schema.json` | P0 message hub downlink command envelope |
| `message_hub_ack.schema.json` | P0 message hub command ACK envelope |
| `message_hub_error.schema.json` | P0 message hub diagnosable error envelope |
| `message_hub_raw_frame_record.schema.json` | P0 raw-frame storage and parse-result record; the device wire payload is not JSON |
| `ego_call_session.schema.json` | CALL-001 append-only Ego Call session transition contract：约束身份、触发来源、状态/原因、信令/媒体状态、位置 belief 引用与隐私；不保存 RTC 密钥或精确坐标。 |
| `location_engine_v0.schema.json` | LOC-020 device-semantic operational location-state reference contract；分离 belief、mobility、GNSS/LTE、battery、policy、last-trusted 与 action lineage，并保留与 event-time 对应的 UTC/GNSS UTC 或 boot-scoped monotonic capture evidence。合同存在不代表 device integration 或 `P0-LOC` 通过。 |
| `location_state_envelope_v0.schema.json` | LOC-021 additive source-event ingress envelope；绑定 outbox-safe device/session、boot/sequence/observation、纳秒事件时钟、Sensor Policy identity 与 Location Engine state。`server_receive_time_ms` 只能由受信服务端适配器添加并作为传输证据，不能决定排序或 freshness。成功持久化后的 HTTP response 可携带 `persistent_priority_outbox_v0.schema.json#/$defs/ack`；其 hash 覆盖 exact request bytes，且只证明 server durable ingest。 |
| `sensor_policy_v0.schema.json` | POLICY-010 可版本化工程配置合同；参数为未验证默认值，不是量产最优功耗/精度声明。标准 JSON Schema 之外的字段间关系由配置中必需的 `egolink.sensor_policy.semantic.v0.1` validator 标识约束，所有固件/VPS/replay consumer 必须实现同一规则。 |
| `sensor_policy_decision_v0.schema.json` | POLICY-010 replayable decision contract；保留独立 condition flags、effective state、原因与 action lineage。 |
| `location_fusion_sample.schema.json` | DATA-001 JSONL dataset sample contract for location fusion exports |
| `imu_window_chunk.schema.json` | Normalized complete KV wire object for one bounded real-QMI IMU chunk over exact lowercase `lte` or `wifi`; sample bytes remain Base64 and training-disabled. |
| `imu_window_manifest.schema.json` | Normalized complete KV wire object for a bounded real-QMI IMU window manifest over exact lowercase `lte` or `wifi`, including its privacy/quality gates. |
| `imu_calibration_artifact.schema.json` | A0-001 六面 accelerometer bias/sensitivity 与独立 signed gyro-bias 工程校准 artifact；绑定设备、固件、安装、来源窗口及 hashes，并固定 `production_ready=false` / `training_allowed=false`。 |
| `imu_calibrated_window.schema.json` | `imu_window_export.v1` 的非覆盖式 calibrated JSONL 派生视图；逐样本保留原始未校准 mg/mdps，并添加 calibrated mg/mdps 与 SI 值。 |
| `sensor_time_lineage.schema.json` | A0-002 的逐 observation 时间血缘合同；显式区分源时间、boot-scoped monotonic ns、UTC、receive/ingest UTC、alignment/uncertainty 与不可变来源。 |
| `clock_mapping_segment.schema.json` | A0-002 的 boot-scoped monotonic→UTC 有界映射段；绑定原点、显式 UTC rate correction、有效区间、可复算 anchors、fit error、uncertainty 与来源证据。 |
| `field_session_manifest.schema.json` | A0-003 标准 Session 包清单：绑定唯一 Session ID、四源与人工事件、device/boot/software/calibration、隐私、stream 范围、artifact hashes、A0-002 exact-input 报告及 seal/package closure；raw Session 不自行授权训练。 |
| `field_manual_event.schema.json` | A0-003 人工事件 weak-label 合同：保存事件类型、事件/传输时间、操作者、note，以及可用时的 device/boot/clock/mapping lineage。 |
| `imu_field_calibrated_window.schema.json` | A0-003 普通外场 IMU window 的非覆盖式 calibrated 视图；区别于只适用于 A0-001 七个校准姿态的 `imu_calibrated_window.v0.1`。 |
| `ego_state_estimation_v0.schema.json` | 规范状态身份、来源时间、移动/姿态/携带枚举、unknown、mock 与实验规则分数；分数不是准确率或安全确认。摘要由 producer 生成，不是签名或完整原始链校验。 |
| `ego_state_view_v0.schema.json` | API 视图内嵌严格 canonical `state`，单列旧帧推导来源、收件时间与实际存储属性；非法投影隔离，raw 采集和 ACK 保留；Web 只展示此视图。 |
| `ego_state_evidence_chain_v0.schema.json` | 多来源特征、来源身份和 producer 摘要的结构合同；不证明不可篡改、跨 C/Python 摘要一致、静态加密或已部署本地优先存储。 |
| `ego_state_report_v0.schema.json` | 组合估计与特征证据的报告结构；隐私标签是声明，不能替代加密、访问控制或生命周期实现，当前 Python 仅生成内存报告。 |

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

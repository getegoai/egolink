# Ego Link 状态记录

更新时间：2026-06-22

## 当前阶段

Stage 0：单智能体、单任务、低风险迭代开发模式。

产品锚点：AI 主动守护定位器。近期 v0.1 目标聚焦设备联网、MQTT 上报、网页看板、SOS / 唤醒 / 定位事件闭环，并为后续 AI 主动提醒打基础。

## 已完成

- T001：补齐可重复验证入口 `scripts/verify.ps1`。
- T002：定义 PC Simulator 事件/命令协议模型。
- T003：实现 PC Simulator 本地事件存储。
- T004：打通 PC Simulator 的事件生成、存储与命令记录。
- T005：更新 Stage 0 任务与状态记录。
- T011：摄像头拍照 smoke test 通过。ESP32-S3 已烧录过 `firmware/camera_smoke`，摄像头初始化成功并采集到一张 JPEG。
- T012：本机 Mosquitto broker 基线通过。Windows 版 Mosquitto 已安装，本机服务运行，用户态 LAN broker 可供开发板连接。
- T013：ESP32-S3 MQTT 心跳 smoke test 通过。开发板已烧录 `firmware/mqtt_heartbeat`，通过 Wi-Fi 连接本机 Mosquitto 并发布 status JSON。
- T014：项目目录清理与版本化迭代模式完成。已删除可再生构建产物和运行缓存，新增 `.gitignore`、`docs/DEVELOPMENT_WORKFLOW.md`、`scripts/start_mosquitto_lan.ps1`，并明确采用 GitHub Flow。
- T015：SIM 卡与 4G 数据链路基础验证通过。SIM7670G 可识别 SIM，注册 LTE，分组数据附着成功，并可通过模块 AT TCP/IP 栈访问公网 IP。
- T016：PC Simulator MQTT worker 完成。`pc_simulator/mqtt_worker.py` 可订阅 `ego/link/+/status`，接收开发板 status JSON，并写入 `pc_simulator/runtime/events.jsonl`。
- T017：PC Simulator Dashboard 读取 MQTT 事件日志完成。`/api/state` 可合并 JSONL 事件日志，并用最新 MQTT status 更新设备状态；网页看板展示 RSSI、最后在线时间和来源。
- T018：MQTT event / ack 闭环完成。worker 默认订阅 `status` / `event` / `ack` 三类 topic，Dashboard 事件流可展示 `mqtt_ack`、`wake_detected` 等上报与确认事件。
- T019：固件传感器数据上报完成。`firmware/mqtt_heartbeat` 已新增 `sensor_sample` / `device_health` event，上报 uptime、Wi-Fi RSSI、free heap、minimum free heap 等 ESP32 设备健康数据；已刷写 ESP32-S3 `COM4`，PC Simulator 收到真实 `sensor_sample`，Dashboard 可展示 sensor sample 的 RSSI/heap 详情。
- T020：板级探测 CH343 / RNDIS 识别修复完成。`egolink_board_probe.py` 已合并 Windows CIM 与 PnP 设备发现，真实探测可识别 ESP32-S3 `COM4`、SIM7670G 串口和 Remote NDIS 网卡。
- T021：SIM7670G GNSS 探测与 `location_report` 写入完成。新增 `scripts/sim7670_gnss_probe.py`，可自动探测 SIM7670G AT 口，打开/查询 GNSS，解析 `CGNSSINFO` / `CGPSINFO`，并写入 PC Simulator 事件日志；当前室内无 fix，但 `location_report` 已进入 Dashboard/API 闭环。
- T022：Safety Companion M0 契约基线完成。已将 `模型架构.md` 的“版本化模型包 + 明确接口契约”路线整合为 `docs/modeling/` 文档、`shared/contracts/` JSON Schema 和 `quality_tests/model_contract/` 契约测试；当前只做契约和边界，不引入训练代码或推理运行时。
- T023：PC Simulator Safety Companion adapter 完成。新增 `pc_simulator/safety_companion.py`，可将最近事件和设备状态转换为 `model_input`，并返回确定性 mock `model_output`；`/api/state` 和 Dashboard 已展示 Safety Companion 风险、分数、建议动作和 reason codes。
- T024：Safety Companion M0 PC Simulator adapter 完成。`pc_simulator/safety_companion.py` 已从本地 mock router 切换为调用模型包 `RuleRouter` / `build_model_input`；新增 `POST /api/safety/evaluate`，支持标准 `sensor_frame` / `model_input` 评估，并可将非 `none` 输出转换为 `safety_event`。
- T025：Safety Companion M0 固件模型接口完成。新增 `firmware/mqtt_heartbeat/components/safety_model`，围绕 `shared/embedded/safety_model_contract.h` 暴露 `safety_model_init/evaluate/version`，当前为明确标识的 deterministic mock；SOS 路径固定输出 `MANUAL_SOS + URGENT_ESCALATION`，并提供 mock 状态 adapter 与串口测试命令。
- T026：Safety Companion M0 模拟端到端闭环完成。新增 `POST /api/safety/replay`，可重放 `normal_walk`、`manual_sos`、`post_impact_inactivity`、`privacy_restricted_impact` 四个场景；非 `none` 输出生成 `safety_event`，`ask_user` / `urgent_escalation` 生成无副作用的模拟 `base_command`，Dashboard 事件详情可展示 risk/action/evidence/privacy。
- T027：真实/半真实设备事件接入 Safety Companion 流程完成。新增 `evaluate_event` 和 `POST /api/safety/process-events`，可将 MQTT `sensor_sample`、SOS/模拟 SOS、GNSS no-fix 等事件转换为标准 `sensor_frame` 并记录 `safety_evaluation`；非 `none` 输出继续生成 `safety_event` 和无副作用模拟 command。
- T028：live MQTT 监督式 Safety 处理完成。`pc_simulator/mqtt_worker.py` 新增 `--process-safety` / `--safety-process-limit`，可在真实 MQTT 消息入库后立即触发 Safety flow；默认入库行为保持不变，Safety 处理异常只写诊断、不阻断 MQTT 采集。
- T029：本地监督会话入口完成。新增 `scripts/start_local_supervised_session.ps1` 和 `scripts/local_session_summary.py`，可一条命令建立 session 目录，启动或复用 broker / Dashboard / live MQTT Safety worker，并输出 `session.log`、`session_summary.json`、`session_summary.md`。
- T030：AutoDev 与设备状态统一监控完成。`scripts/autodev.py watch` 和 `scripts/watch_autodev.ps1` 已同屏显示 AutoDev 任务进度与本地设备 / Safety session 摘要；`status` 也会显示本地 Safety 快照。
- T031：M1-001 硬件传感器矩阵完成。新增 `docs/modeling/HARDWARE_SENSOR_MATRIX.md`，把当前开发板、SIM7670G、Wi-Fi/MQTT、摄像头、SD、IMU、麦克风、物理 SOS、电源/电量和 PC 侧探测链路按 `verified` / `semi_verified` / `pc_side_verified` / `mock_only` / `not_verified` / `missing_or_unknown` 标明边界，并明确 M1-002 recorder 的最小字段和阻塞项。
- T032：M1-002 session recorder 骨架完成。新增 `pc_simulator/session_recorder.py` 和 `scripts/session_recorder.py`，可从 PC Simulator `events.jsonl` 派生 `session_manifest.json`、`sensor_frames.jsonl`、`events.jsonl`、`annotations.jsonl` 和 `session_recording.md`；本地监督会话脚本默认生成 `recording/`，且 manifest 显式标注未验证传感器不可用。
- T033：M1-004-pre PC session inspector / quality gate 完成。新增 `pc_simulator/session_inspector.py` 和 `scripts/inspect_session_recording.py`，可校验 T032 `recording/` 目录的必需文件、manifest、JSONL、record counts、privacy、sensor source 边界、source key 唯一性和 seq/timestamp warning，并输出 `session_quality_report.json` / `.md`。
- T034：M1-004-pre quality gate 监控接入完成。`scripts/start_local_supervised_session.ps1` 在 recorder 后自动运行 session inspector，写入 quality report 并在会话日志显示 PASS/FAIL；`scripts/autodev.py watch/status` 已在本地设备区块显示 Quality 和 Report。
- T035：M1-004-pre session 文件完整性完成。Recorder 现在生成 `file_manifest.json`，记录 session manifest、sensor frames、events、annotations 和 summary 的 SHA-256；quality gate 会校验必需条目、文件大小和哈希，发现静默修改时失败。
- T036：M1-004 PC session import / replay 完成。新增 `pc_simulator/session_replay.py` 和 `scripts/replay_session_recording.py`，可对完整性校验通过的 recording 重建 sensor frames / events 时间线，调用现有 RuleRouter，并输出 `session_replay_report.json` / `.md`；质量门失败时默认拒绝回放。
- HCTX-001：硬件上下文包 v0.3 评估与硬件矩阵更新完成。新增 `docs/hardware/**` 和 `HARDWARE_CONTEXT_PACKAGE_README.md`，验证硬件包 manifest 与采购清单 Excel 结构，修正 P0 上下文路径为 `docs/EGO_LINK_P0_CONTEXT.md`，并把 `docs/modeling/HARDWARE_SENSOR_MATRIX.md` 更新为 HCTX-001 版，补齐接口、驱动、数据能力、功耗控制、真实/Mock 边界、M1 阻塞项和 HARCH-001 审计重点。
- 模型上下文 v0.2 已纳入：新增 `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md` 和 `docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md`，明确 M0 是规则基线，下一阶段先做 M1 数据基础，不直接训练神经网络。

## 当前建议任务

下一项建议任务 T037 / M1-005：最小 annotation CLI，向已录制 session 的 `annotations.jsonl` 追加人工标签（`safe`、`needs_help`、`false_alarm`、`cancelled`、`no_response`），并让 quality gate / replay report 能读取 annotation 摘要；仍不进入 IMU 环形缓冲，直到 IMU 硬件事实确认。

## 后续任务路线

- T035：session 文件哈希与完整性校验，补齐 manifest / quality gate 的数据不可篡改基础。已完成。
- T036：PC session import / replay，按 recording 重建事件流并调用现有 RuleRouter，验证可回放。已完成。
- T037：最小 annotation CLI 或本地页面，写入 `safe`、`needs_help`、`false_alarm`、`cancelled`、`no_response`。
- T038：硬件决策门，确认 IMU、麦克风、物理 SOS GPIO、SD 和真实电量路径；未确认前不写真实驱动声明。
- T039：IMU mock/driver interface 和 ring buffer 骨架；真实 IMU 确认后再接入采样。

## 最近验证

- `python -m unittest quality_tests.test_hardware_sensor_matrix -v`：通过，5 个测试全部成功；覆盖 HCTX-001 范围、关键传感器状态、Mock/未知边界、证据路径、M1 阻塞项和 HARCH-001 审计重点。
- 硬件包 manifest 校验：通过，`PACKAGE_MANIFEST.json` 中 10 个文件的 bytes / SHA-256 全部匹配；采购清单 Excel 可作为 `.xlsx` 打开，包含“概览、采购总表、已有物料、平台对比、到货验收”5 个 sheet。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，108 个测试全部成功。
- `python -m unittest quality_tests.test_session_replay -v`：通过，4 个测试全部成功；覆盖成功回放、质量门失败拒绝回放、replay report 写入和 CLI。
- `python scripts\replay_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke`：通过，返回 `PASS replayed_inputs=37 safety_events=9 skipped=23`，生成 `session_replay_report.json` / `.md`。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，107 个测试全部成功。
- `python -m unittest quality_tests.test_session_recorder quality_tests.test_session_inspector -v`：通过，9 个测试全部成功；覆盖 file manifest 生成、hash manifest CLI 输出、manifest 篡改、JSONL 篡改和 hash mismatch。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t035-integrity-smoke --output-dir pc_simulator\runtime\recordings\t035-integrity-smoke`：通过，生成带 `file_manifest.json` 的 smoke recording。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t035-integrity-smoke`：通过，quality gate PASS；`quality_score=0.85`、`errors=0`、`warnings=5`。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，103 个测试全部成功。
- `python -m unittest autodev.tests.test_supervisor quality_tests.test_local_session_summary -v`：通过，19 个测试全部成功；覆盖 AutoDev 读取 quality gate 摘要和本地监督会话脚本契约。
- `powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker`：通过，生成 `pc_simulator/runtime/sessions/20260621-211742/recording/session_quality_report.md`，quality gate 为 PASS，`quality_score=0.85`、`errors=0`、`warnings=5`。
- `python scripts\autodev.py watch --once --no-clear --events 4`：通过，`LOCAL DEVICE / SAFETY SESSION` 显示 `Quality   : PASS score=0.85 errors=0 warnings=5 frames=11 events=27` 和 quality report 路径。
- `python scripts\autodev.py status`：通过，显示相同 Quality/Report 摘要。
- `python -m unittest quality_tests.test_session_inspector quality_tests.test_session_recorder -v`：通过，8 个测试全部成功；覆盖 quality gate pass/fail、record count mismatch、未验证 source 标记 real、重复 source key、报告写入和 CLI。
- `python scripts\session_recorder.py --event-log pc_simulator\runtime\events.jsonl --session-id t033-quality-smoke --output-dir pc_simulator\runtime\recordings\t033-quality-smoke`：通过，生成 smoke recording，包含 19 条 sensor frames、41 条关键 events、0 条 annotations。
- `python scripts\inspect_session_recording.py pc_simulator\runtime\recordings\t033-quality-smoke`：通过，质量门 PASS；`quality_score=0.85`、`errors=0`、`warnings=5`，warning 暴露 firmware version unknown、annotations empty 和历史 Safety 派生事件 seq 回退。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，102 个测试全部成功。
- `python -m unittest quality_tests.test_session_recorder quality_tests.test_local_session_summary -v`：通过，6 个测试全部成功；覆盖 recorder manifest、sensor frame/event 输出、CLI 写入和本地监督会话脚本契约。
- `powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker`：通过，生成 `pc_simulator/runtime/sessions/20260621-201911/recording/session_recording.md`，最近 40 条 event log 派生出 11 条 sensor frames、27 条关键事件、0 条 annotations，未启动新的后台进程。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，97 个测试全部成功。
- `python -m unittest quality_tests.test_hardware_sensor_matrix -v`：通过，4 个硬件传感器矩阵测试全部成功；覆盖 M1 范围、关键传感器状态、Mock/未知边界和证据路径。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，94 个测试全部成功。
- `python -m unittest autodev.tests.test_supervisor -v`：通过，15 个 AutoDev supervisor 测试全部成功；覆盖本地 session summary 读取、event-log fallback 和既有监控行为。
- `python scripts\autodev.py watch --once --no-clear --events 4`：通过，同屏显示 AutoDev 最近任务状态和 `LOCAL DEVICE / SAFETY SESSION`，其中最新 Safety 风险为 `manual_sos`，动作为 `urgent_escalation`。
- `powershell -ExecutionPolicy Bypass -File scripts\watch_autodev.ps1 -Once -NoClear -RecentEvents 4`：通过，PowerShell wrapper 可显示统一监控。
- 新增模型上下文文档静态检查：通过，M1 下一步明确为硬件与传感器矩阵，不训练 MotionNet/AudioGate/VisionGate。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，90 个测试全部成功。
- `python -m unittest quality_tests.test_local_session_summary -v`：通过，3 个本地监督会话测试全部成功；覆盖事件摘要统计、JSON/Markdown 文件输出和 PowerShell 启动脚本关键契约。
- `powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker`：通过，生成 `pc_simulator/runtime/sessions/20260621-174427/`，写入 `session.log`、`session_summary.json` 和 `session_summary.md`，未启动新的后台进程。
- `python scripts\local_session_summary.py --event-log pc_simulator\runtime\events.jsonl --limit 8 --markdown`：通过，摘要显示最新 Safety 风险为 `manual_sos`，建议动作为 `urgent_escalation`，最近 8 条事件中包含 3 条 `safety_evaluation`、1 条 `safety_event` 和 1 条模拟 command。
- `python -m unittest quality_tests.test_mqtt_worker -v`：通过，12 个 MQTT worker 测试全部成功；覆盖 `--process-safety` 参数、after-store hook、坏行跳过、Safety 失败隔离和进度输出。
- `python -m unittest quality_tests.test_safety_companion quality_tests.test_pc_simulator -v`：通过，26 个 PC Simulator / Safety Companion adapter 测试全部成功；覆盖 `POST /api/safety/replay`、`POST /api/safety/process-events`、真实 `sensor_sample` 映射、事件日志幂等处理、派生 safety 记录过滤、隐私证据过滤和无副作用命令。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --max-messages 1 --wait-seconds 90 --process-safety --safety-process-limit 20`：通过，收到真实固件 `sensor_sample seq=9064`，并立即写入 1 条 `safety_evaluation`；`risk_type=none`，未生成 `safety_event` 或 command。
- Dashboard API live worker 幂等验证：通过，`POST /api/safety/process-events` 对已处理 live `sensor_sample` 返回 `processed=0`、`safety_evaluations=0`、`safety_events=0`、`base_commands=0`。
- `python scripts\sim7670_gnss_probe.py --no-power-on --warmup-seconds 0 --poll-count 1 --poll-interval-seconds 0`：通过，报告见 `reports/gnss_validation/20260621-161721/gnss_probe.md`；`COM6/COM7` AT 可达，`gnss_power_state=1`，当前 no-fix，事件已写入 `pc_simulator/runtime/events.jsonl`。
- GNSS no-fix + 模拟 SOS Safety process：通过，`POST /api/safety/process-events` 处理 2 个源事件，写入 2 条 `safety_evaluation`、1 条 `safety_event`、1 条无副作用模拟 command。
- 真实/半真实日志 Safety process：通过，最近 20 条事件中处理 12 条可评估事件，写入 12 条 `safety_evaluation`、3 条 `safety_event`、3 条模拟 command。
- `python -m unittest quality_tests.test_safety_model_firmware quality_tests.test_mqtt_heartbeat_firmware -v`：通过，8 个固件侧静态测试全部成功。
- `python scripts\verify_safety_companion_m0.py`：通过，模型包自检、12 个合成场景、契约测试、包内测试和 C threshold header 比对全部成功。
- `python -m unittest quality_tests.model_contract.test_contract_schemas -v`：通过，5 个 Safety Companion M0 契约测试全部成功。
- `python -m unittest quality_tests.test_repository_contract -v`：通过，3 个仓库结构契约测试全部成功。
- `python -m unittest quality_tests.test_sim7670_gnss_probe -v`：通过，6 个 GNSS probe 测试全部成功。
- PC Simulator safety endpoint：通过，`POST /api/safety/evaluate` 可接收标准 `model_input` 并返回 M0 `model_output`；测试覆盖 `manual_sos -> urgent_escalation`。
- `python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2`：通过，首次报告见 `reports/gnss_validation/20260621-100651/gnss_probe.md`；`COM6/COM7` AT 可达，型号 `SIM7670G-MNGV`。
- `python scripts\sim7670_gnss_probe.py --no-power-on --warmup-seconds 0 --poll-count 1 --poll-interval-seconds 0`：通过，最终报告见 `reports/gnss_validation/20260621-101143/gnss_probe.md`；`gnss_power_state=1`，当前返回 no-fix，事件已写入 `pc_simulator/runtime/events.jsonl`。
- Dashboard API：通过，`http://127.0.0.1:8787/api/state` 最新事件为 `event_type=location_report`、`source=sim7670g_gnss`、`fix=false`、`gnss_power_state=1`、`device.gnss_state=no_fix`。
- `python -m unittest quality_tests.test_board_probe -v`：通过，8 个 board probe 测试全部成功。
- `python scripts\egolink_board_probe.py --skip-esp-log --probe-all-sim-ports`：通过，报告见 `reports/board_validation/20260621-091239/probe.md`；`COM4` CH343、SIM7670G 串口、Remote NDIS 和 AT 身份质量门均通过，ESP32 日志与 SD 状态因本次跳过日志读取仍为 WARN。
- `python -m unittest quality_tests.test_mqtt_heartbeat_firmware -v`：通过，3 个固件静态测试全部成功。
- `idf.py -p COM4 flash`：通过，识别芯片 `ESP32-S3`，写入 `egolink_mqtt_heartbeat.bin` 并 hard reset。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --max-messages 1 --wait-seconds 90`：通过，收到真实固件 `sensor_sample`。
- 本机 Dashboard 当前运行在 `http://127.0.0.1:8787`，进程 PID `44568`。

## 已知限制

- 当前 GNSS 在室内未获得卫星 fix，`location_report` 已可上报 no-fix 状态；后续需要户外或靠窗长时间冷启动验证真实经纬度。
- Safety Companion M0 官方规则包当前不把 GNSS no-fix 作为模型风险；PC Simulator adapter 只保留 `fix_valid=false` 输入，不再沿用旧 mock 的 `device_risk/upload_summary` 输出。
- 当前 shell 未加载 ESP-IDF，`idf.py --version` 不可用；T025 只完成固件接口和主机侧静态测试，尚未进行 ESP-IDF build、flash 或真实串口 CLI 验证。
- T026 是纯模拟 replay 闭环，只验证协议、记录、展示和无副作用命令，不验证真实事故/跌倒/呼救识别准确率。
- T030 的统一监控仍是只读观察入口，不负责启动、停止、重启或修复设备侧进程；长期运行守护、日志轮转和自动恢复仍未实现。
- M1 数据基础已开始于硬件传感器矩阵；当前没有真实 MotionNet、AudioGate、VisionGate，也没有可用于训练的正式 session 数据集。
- T032 recorder 是 PC event-log 派生骨架，不是固件内 `safety_recorder`；它尚未实现掉电恢复、窗口完整率或采样率统计。
- T033/T034/T035/T036 已提供 PC 侧质量门、文件完整性和 replay/model-input rebuild；但固件 recorder、用户标注和可训练正式 session 数据集仍未实现。
- 当前 IMU、麦克风、真实物理 SOS GPIO、SD 挂载、真实电量/充电和 ESP32 侧 SIM7670G 控制链路仍未验证，不能作为 M1 recorder 的真实传感源声明。
- 当前 T021 是 PC 侧通过 USB AT 口探测 SIM7670G GNSS，尚未把 ESP32 固件切换为直接控制 SIM7670G GNSS。
- SD 卡挂载曾失败，需要单独确认格式、接线、引脚、供电和固件挂载参数。
- 用户已确认当前 Wi-Fi 凭据可以在本机项目中明文保存，固件 `sdkconfig` 可保留 SSID/password。
- 当前 shell 不是管理员权限，无法修改 `C:\Program Files\mosquitto\mosquitto.conf`；因此系统服务仍只监听本机回环地址，局域网访问由用户态 Mosquitto 进程提供。
- 当前开发板已从 camera smoke 固件切换为 MQTT heartbeat 固件；如需继续看 HTTP 摄像头照片，需要重新烧录 `firmware/camera_smoke`。
- Windows 侧 SIM7670G RNDIS 网卡可获得 `192.168.0.100/24` 和默认网关 `192.168.0.1`，但从电脑指定该源地址 ping/curl 外网仍超时；当前 4G 可用性以模块 AT TCP/IP 栈验证为准。

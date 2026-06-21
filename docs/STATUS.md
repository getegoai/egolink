# Ego Link 状态记录

更新时间：2026-06-21

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

## 当前建议任务

下一项建议任务 T024：把 Safety Companion mock `model_output` 写成显式 PC Simulator 事件或下行命令建议，让事件流能展示 `ask_user`、`upload_summary`、`escalate_emergency` 等推荐动作。

## 最近验证

- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`：通过，54 个测试全部成功。
- `python -m unittest quality_tests.test_safety_companion -v`：通过，5 个 Safety Companion adapter 测试全部成功。
- `python -m unittest quality_tests.test_pc_simulator -v`：通过，9 个 PC Simulator 测试全部成功。
- `python -m unittest quality_tests.model_contract.test_contract_schemas -v`：通过，5 个 Safety Companion M0 契约测试全部成功。
- `python -m unittest quality_tests.test_repository_contract -v`：通过，3 个仓库结构契约测试全部成功。
- `python -m unittest quality_tests.test_sim7670_gnss_probe -v`：通过，6 个 GNSS probe 测试全部成功。
- Dashboard API：通过，`http://127.0.0.1:8787/api/state` 当前 `safety_companion.model_input.active_event=location_report`，`model_output.risk_type=device_risk`，`recommended_action=upload_summary`，`reason_codes=gnss_no_fix`。
- `python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2`：通过，首次报告见 `reports/gnss_validation/20260621-100651/gnss_probe.md`；`COM6/COM7` AT 可达，型号 `SIM7670G-MNGV`。
- `python scripts\sim7670_gnss_probe.py --no-power-on --warmup-seconds 0 --poll-count 1 --poll-interval-seconds 0`：通过，最终报告见 `reports/gnss_validation/20260621-101143/gnss_probe.md`；`gnss_power_state=1`，当前返回 no-fix，事件已写入 `pc_simulator/runtime/events.jsonl`。
- Dashboard API：通过，`http://127.0.0.1:8787/api/state` 最新事件为 `event_type=location_report`、`source=sim7670g_gnss`、`fix=false`、`gnss_power_state=1`、`device.gnss_state=no_fix`。
- `python -m unittest quality_tests.test_board_probe -v`：通过，8 个 board probe 测试全部成功。
- `python scripts\egolink_board_probe.py --skip-esp-log --probe-all-sim-ports`：通过，报告见 `reports/board_validation/20260621-091239/probe.md`；`COM4` CH343、SIM7670G 串口、Remote NDIS 和 AT 身份质量门均通过，ESP32 日志与 SD 状态因本次跳过日志读取仍为 WARN。
- `python -m unittest quality_tests.test_mqtt_heartbeat_firmware -v`：通过，3 个固件静态测试全部成功。
- `idf.py -p COM4 flash`：通过，识别芯片 `ESP32-S3`，写入 `egolink_mqtt_heartbeat.bin` 并 hard reset。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/event --max-messages 1 --wait-seconds 90`：通过，收到真实固件 `sensor_sample`。
- 本机 Dashboard 当前运行在 `http://127.0.0.1:8787`，进程 PID `18808`。

## 已知限制

- 当前 GNSS 在室内未获得卫星 fix，`location_report` 已可上报 no-fix 状态；后续需要户外或靠窗长时间冷启动验证真实经纬度。
- 当前 T021 是 PC 侧通过 USB AT 口探测 SIM7670G GNSS，尚未把 ESP32 固件切换为直接控制 SIM7670G GNSS。
- SD 卡挂载曾失败，需要单独确认格式、接线、引脚、供电和固件挂载参数。
- 用户已确认当前 Wi-Fi 凭据可以在本机项目中明文保存，固件 `sdkconfig` 可保留 SSID/password。
- 当前 shell 不是管理员权限，无法修改 `C:\Program Files\mosquitto\mosquitto.conf`；因此系统服务仍只监听本机回环地址，局域网访问由用户态 Mosquitto 进程提供。
- 当前开发板已从 camera smoke 固件切换为 MQTT heartbeat 固件；如需继续看 HTTP 摄像头照片，需要重新烧录 `firmware/camera_smoke`。
- Windows 侧 SIM7670G RNDIS 网卡可获得 `192.168.0.100/24` 和默认网关 `192.168.0.1`，但从电脑指定该源地址 ping/curl 外网仍超时；当前 4G 可用性以模块 AT TCP/IP 栈验证为准。

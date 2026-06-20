# Ego Link 状态记录

更新时间：2026-06-20

## 当前阶段

Stage 0：单智能体、单任务、低风险开发模式。

产品锚点：AI 主动守护定位器。近期 v0.1 目标聚焦设备联网、MQTT 上传、网页看板、SOS / 唤醒 / 定位事件闭环，并为后续 AI 主动提醒打基础。

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

## 当前建议任务

下一项建议任务 T017：让 PC Simulator Dashboard / API 读取 MQTT worker 写入的事件日志，展示最新设备状态和外部上报事件。

## 最近验证

- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`：通过，21 个测试全部成功。
- `python -m unittest quality_tests.test_mqtt_worker -v`：通过，5 个 MQTT worker 单元测试全部成功。
- `python pc_simulator\app.py --help` / `python pc_simulator\mqtt_worker.py --help`：通过，两个本地 CLI 入口均可直接运行。
- `python pc_simulator\mqtt_worker.py --host 192.168.31.250 --port 1883 --topic ego/link/+/status --max-messages 1 --wait-seconds 20`：通过，worker 收到 1 条真实开发板 status 并写入 `pc_simulator/runtime/events.jsonl`，样例字段包括 `device_id=ego-link-001`、`seq=2446`、`rssi=-56`、`event_type=mqtt_status`。
- `powershell -ExecutionPolicy Bypass -File scripts/start_mosquitto_lan.ps1 -BrokerIp 192.168.31.250 -Restart`：通过，用户态 LAN broker 监听 `192.168.31.250:1883`，PID `20100`。
- `Get-NetTCPConnection -LocalAddress 192.168.31.250 -LocalPort 1883`：通过，确认 broker 处于 `Listen` 状态，并存在开发板连接。
- `mosquitto_sub -h 192.168.31.250 -p 1883 -t ego/link/ego-link-001/status -C 1 -W 35`：通过，收到 `device_id=ego-link-001`、`message_type=status`、`seq=234` 的 JSON 心跳。
- 项目清理：已删除 `firmware/**/build/`、`firmware/**/managed_components/`、`firmware/**/captures/`、`pc_simulator/runtime/` 和 `**/__pycache__/` 等可再生目录；后续运行生成物已由 `.gitignore` 忽略。
- `AT+CFUN=1,1`：执行 SIM7670G 软重启后，模块重新识别 SIM。
- `AT+CPIN?`：通过，返回 `+CPIN: READY`。
- `AT+CICCID`：通过，ICCID 可读取，状态记录中不保存完整卡号。
- `AT+COPS?` / `AT+CEREG?` / `AT+CGATT?`：通过，注册到 `460-00` LTE 网络，`CEREG=0,1`，`CGATT=1`。
- `AT+CGDCONT?` / `AT+IPADDR`：通过，APN 为 `CMNET`，模块侧获得 IPv4 地址 `10.36.158.99`。
- `AT+CPING="8.8.8.8",1,4,64,1000,10000,255`：通过，4/4 收到响应，RTT 约 74-247 ms。

## 已知限制

- SD 卡挂载曾失败，需要单独确认格式、接线/引脚、供电和固件挂载参数。
- 用户已确认当前 Wi-Fi 凭据可以在本机项目中明文保存，固件 `sdkconfig` 可保留 SSID/password。
- 当前 shell 不是管理员权限，无法修改 `C:\Program Files\mosquitto\mosquitto.conf`；因此系统服务仍只监听本机回环地址，局域网访问由用户态 Mosquitto 进程提供。
- 当前开发板已从 camera smoke 固件切换为 MQTT heartbeat 固件；如需继续看 HTTP 摄像头照片，需要重新烧录 `firmware/camera_smoke`。
- Windows 侧 SIM7670G RNDIS 网卡可获得 `192.168.0.100/24` 和默认网关 `192.168.0.1`，但从电脑指定该源地址 ping/curl 外网仍超时；当前 4G 可用性以模块 AT TCP/IP 栈验证为准。

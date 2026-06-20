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

## 当前建议任务

下一项建议任务：实现 PC Simulator MQTT worker，订阅 `ego/link/+/status` 并写入事件日志。

## 最近验证

- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`：通过，11 个测试全部成功。
- `powershell -ExecutionPolicy Bypass -File scripts/start_mosquitto_lan.ps1 -BrokerIp 192.168.31.250 -Restart`：通过，用户态 LAN broker 监听 `192.168.31.250:1883`，PID `20100`。
- `Get-NetTCPConnection -LocalAddress 192.168.31.250 -LocalPort 1883`：通过，确认 broker 处于 `Listen` 状态，并存在开发板连接。
- `mosquitto_sub -h 192.168.31.250 -p 1883 -t ego/link/ego-link-001/status -C 1 -W 35`：通过，收到 `device_id=ego-link-001`、`message_type=status`、`seq=234` 的 JSON 心跳。
- 项目清理：已删除 `firmware/**/build/`、`firmware/**/managed_components/`、`firmware/**/captures/`、`pc_simulator/runtime/` 和 `**/__pycache__/` 等可再生目录；后续运行生成物已由 `.gitignore` 忽略。

## 已知限制

- SIM 卡未插入，4G 联网暂不验证。
- SD 卡挂载曾失败，需要单独确认格式、接线/引脚、供电和固件挂载参数。
- 用户已确认当前 Wi-Fi 凭据可以在本机项目中明文保存，固件 `sdkconfig` 可保留 SSID/password。
- 当前 shell 不是管理员权限，无法修改 `C:\Program Files\mosquitto\mosquitto.conf`；因此系统服务仍只监听本机回环地址，局域网访问由用户态 Mosquitto 进程提供。
- 当前开发板已从 camera smoke 固件切换为 MQTT heartbeat 固件；如需继续看 HTTP 摄像头照片，需要重新烧录 `firmware/camera_smoke`。

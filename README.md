# Ego Link P0

Ego Link P0 是“AI 主动守护定位器”的第一阶段验证项目。当前目标不是先做复杂硬件产品，而是尽快跑通设备联网、MQTT 上报、网页看板、SOS / 唤醒 / 定位事件闭环，并为后续 AI 主动提醒打基础。

## 当前阶段

- 硬件：Waveshare ESP32-S3-SIM7670G-4G 开发板。
- 固件：已验证摄像头拍照 smoke test 与 Wi-Fi MQTT 心跳 smoke test；`mqtt_heartbeat` 已支持设备健康 `sensor_sample` 事件上报。
- 本机服务：Windows Mosquitto 已安装，用户态 LAN broker 可供开发板连接，PC Simulator 可订阅 MQTT status、写入事件日志并在 Dashboard 展示。
- Safety Companion：M0 契约、规则基线、模拟回放、真实/半真实事件处理和本地监督会话已完成；M1 下一步进入数据基础与采集闭环。
- 开发模式：采用 GitHub Flow，第一阶段保持单智能体、单任务、可验证迭代。

详细约定见 `docs/development/WORKFLOW.md`。

## 常用命令

运行基础验证：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

启动本地监督会话：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local_supervised_session.ps1
```

打开 AutoDev + 设备/Safety 统一监控：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/watch_autodev.ps1
```

启动本机局域网 Mosquitto broker：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_mosquitto_lan.ps1 -BrokerIp 192.168.31.250 -Restart
```

运行 PC Simulator：

```powershell
python pc_simulator/app.py --port 8787
```

接收开发板 MQTT 并写入事件日志：

```powershell
python pc_simulator/mqtt_worker.py --host 192.168.31.250 --port 1883
```

启用 live MQTT Safety 处理：

```powershell
python pc_simulator/mqtt_worker.py --host 192.168.31.250 --port 1883 --process-safety --safety-process-limit 20
```

默认订阅 `ego/link/+/status`、`ego/link/+/event` 和 `ego/link/+/ack`。如需只订阅部分主题，可重复传入 `--topic`。

Dashboard 会读取 `pc_simulator/runtime/events.jsonl` 中的最新事件；worker 和 Dashboard 可以在两个终端同时运行。

打开：

```text
http://127.0.0.1:8787
```

## 模型上下文

新模型上下文入口：

- `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
- `docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md`

若 M0 尚未完成集成，先执行 `docs/modeling/INTEGRATION_TASKS.md`；M0 集成完成后，从 M1-001 的硬件与传感器矩阵开始，不直接训练神经网络。

## 任务入口

- 当前任务：`docs/tasks/active/`
- 项目状态：`docs/current/STATUS.md`
- 产品定位：`docs/product/PRODUCT_CHARTER.md`
- 板级验证：`docs/hardware/validation/P0_BOARD_VALIDATION.md`
- AutoDev 监控：`docs/development/AUTODEV_MONITORING.md`

## 版本化迭代

当前选择 GitHub Flow：

1. `main` 保持可构建、可运行、文档状态可信。
2. 每个任务从 `main` 拉出 `task/T###-short-name`。
3. 每轮只做 `CURRENT_TASK.md` 定义的一个目标。
4. 任务完成前运行验证并更新 `docs/current/STATUS.md`。
5. 可演示节点使用 `v0.x.y` tag 标记。

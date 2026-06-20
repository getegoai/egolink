# Ego Link P0

Ego Link P0 是“AI 主动守护定位器”的第一阶段验证项目。当前目标不是先做复杂硬件产品，而是尽快跑通设备联网、MQTT 上报、网页看板、SOS / 唤醒 / 定位事件闭环，并为后续 AI 主动提醒打基础。

## 当前阶段

- 硬件：Waveshare ESP32-S3-SIM7670G-4G 开发板。
- 固件：已验证摄像头拍照 smoke test 与 Wi-Fi MQTT 心跳 smoke test。
- 本机服务：Windows Mosquitto 已安装，用户态 LAN broker 可供开发板连接。
- 开发模式：采用 GitHub Flow，第一阶段保持单智能体、单任务、可验证迭代。

详细约定见 `docs/DEVELOPMENT_WORKFLOW.md`。

## 常用命令

运行基础验证：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

启动本机局域网 Mosquitto broker：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_mosquitto_lan.ps1 -BrokerIp 192.168.31.250 -Restart
```

运行 PC Simulator：

```powershell
python pc_simulator/app.py --port 8787
```

打开：

```text
http://127.0.0.1:8787
```

## 任务入口

- 当前任务：`docs/tasks/CURRENT_TASK.md`
- 项目状态：`docs/STATUS.md`
- 产品定位：`docs/产品定位.md`
- 板级验证：`docs/P0_BOARD_VALIDATION.md`

## 版本化迭代

当前选择 GitHub Flow：

1. `main` 保持可构建、可运行、文档状态可信。
2. 每个任务从 `main` 拉出 `task/T###-short-name`。
3. 每轮只做 `CURRENT_TASK.md` 定义的一个目标。
4. 任务完成前运行验证并更新 `docs/STATUS.md`。
5. 可演示节点使用 `v0.x.y` tag 标记。

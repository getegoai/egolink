# DEMO-003 Live Safety Loop Evidence

日期：2026-06-25

## 目标

Demo v0.3 的目标是把 Demo v0.2 的 AMOLED 屏幕确认链路继续接到 SIM7670G/GNSS 刷新，并形成一份完整的 safety event 记录：

```text
PC Bridge ask_user
-> AMOLED command_ack / ask_user_rendered / user_confirmation
-> PC Bridge request_location
-> SIM7670G GNSS probe location_report
-> safety_event
-> session recording / quality / replay
```

## 本轮新增实现

- 新增 `pc_simulator/live_safety_demo.py`，把 AMOLED JSONL、SIM7670G GNSS `location_report` 和 PC Bridge command 合成为同一 session 的事件流。
- 新增 `scripts/run_demo_v0_3_live_safety_loop.py`，默认运行真实 AMOLED ask_user 和真实 SIM7670G GNSS probe；也支持传入已有 JSONL/JSON 做复盘。
- `pc_simulator/board_bridge.py` 现在会保留 `response`、`cmd`、`cmd_id`、`ack_status`、`session_id` 和 `source`，用于真实触摸链路的关联。

## 通过项

使用上一轮已确认的真实 AMOLED 点击证据，加上本轮 live SIM7670G GNSS probe，Demo v0.3 记录闭环通过：

```text
command:
python scripts\run_demo_v0_3_live_safety_loop.py --json --amoled-jsonl pc_simulator\runtime\demo_v0_2\demo-v0-2-20260625-162540.jsonl --gnss-warmup-seconds 3 --gnss-poll-count 2 --gnss-poll-interval-seconds 1

session_id:
demo-v0-3-2026-06-25T084415.383678Z0000

result:
ok=true
response=safe
quality_score=0.94
replay_passed=true
```

事件计数：

```text
board_hello=2
motion_event=1
command_sent=2
command_ack=2
ask_user_rendered=1
user_confirmation=1
location_report=1
safety_event=1
```

GNSS probe 结果：

```text
candidate_ports=COM6, COM7
selected_port=COM6
at_ok=true
fix=false
event_written=false
```

证据路径：

```text
pc_simulator/runtime/demo_v0_3/demo-v0-3-2026-06-25T084415.383678Z0000.summary.json
pc_simulator/runtime/demo_v0_3/demo-v0-3-2026-06-25T084415.383678Z0000.events.jsonl
pc_simulator/runtime/demo_v0_3/recordings/demo-v0-3-2026-06-25T084415.383678Z0000/session_quality_report.json
pc_simulator/runtime/demo_v0_3/recordings/demo-v0-3-2026-06-25T084415.383678Z0000/session_replay_report.json
pc_simulator/runtime/demo_v0_3/gnss/20260625-164439/gnss_probe.md
```

## 未完全通过项

本轮直接运行同一轮实时链路时，AMOLED 板已经收到 PC 下发命令并渲染屏幕，但两次等待窗口内没有收到新的触摸确认：

```text
attempt 1:
ask_user command_ack=true
ask_user_rendered=true
user_confirmation=false
wait=60s

attempt 2:
ask_user command_ack=true
ask_user_rendered=true
user_confirmation=false
wait=90s
```

因此，当前验收表述应为：

- Demo v0.3 的 PC 编排、GNSS 刷新、safety event 记录、quality gate 和 replay 已通过。
- AMOLED 触摸确认使用了同日 Demo v0.2 的真实点击证据，而不是 v0.3 同一轮运行中新采到的点击。
- 下一次需要用户在 v0.3 脚本运行窗口内点击 `SAFE` 或 `HELP`，完成同一轮实时证据。

## 边界

- `motion_event` 仍是 demo synthetic candidate，不是 MotionNet 或真实跌倒模型输出。
- SIM7670G/GNSS 仍是 PC 通过 USB AT probe 刷新，不是 connectivity_node 固件收到 `request_location` 后自行回 ACK。
- 当前不做真实报警、拨号、短信或云端上报。
- GNSS 室内 no-fix 不阻塞 v0.3；本阶段要求 AT 可达、GNSS 状态可读、`location_report fix=false` 可入记录。

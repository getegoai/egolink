# CURRENT_TASK: T021 SIM7670G GNSS 探测与 location_report 写入

## 任务目标

接入一个可重复执行的 SIM7670G GNSS 探测入口，通过 AT 查询 GNSS 状态，解析定位响应，并把结果写成 PC Simulator 可读取的 `location_report` 事件。

## 范围

- 新增 `scripts/sim7670_gnss_probe.py`。
- 支持自动发现 SIM7670G AT 候选口。
- 支持执行 `AT+CGNSSPWR?`、`AT+CGNSSPWR=1`、`AT+CGNSSINFO`、`AT+CGPSINFO`。
- 支持解析有 fix 与无 fix 的 GNSS 响应。
- 支持写入 `pc_simulator/runtime/events.jsonl`。
- Dashboard/API 支持从真实 `location_report` 更新 GNSS 状态，并展示 no-fix / 坐标 / 卫星数等详情。
- 补充单元测试与状态记录。

## 不做

- 不把 ESP32 固件切换为直接控制 SIM7670G GNSS。
- 不把室内无卫星 fix 视为失败。
- 不做长时间冷启动搜星测试；该项留作后续户外硬件门禁。
- 不接入云端或外部地图服务。

## 允许修改路径

- `scripts/sim7670_gnss_probe.py`
- `quality_tests/test_sim7670_gnss_probe.py`
- `pc_simulator/app.py`
- `quality_tests/test_pc_simulator.py`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_sim7670_gnss_probe -v
python -m unittest quality_tests.test_pc_simulator -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
python scripts\sim7670_gnss_probe.py --warmup-seconds 5 --poll-count 3 --poll-interval-seconds 2
```

## 执行结果

- `python -m unittest quality_tests.test_sim7670_gnss_probe -v` 通过，5 个测试全部成功。
- `python -m unittest quality_tests.test_pc_simulator -v` 通过，8 个测试全部成功。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，42 个测试全部成功。
- 真实硬件 GNSS 探测通过，最终报告见 `reports/gnss_validation/20260621-101143/gnss_probe.md`。
- 探测到 SIM7670G AT 口 `COM6` / `COM7`，型号 `SIM7670G-MNGV`，AT 可达。
- 脚本已执行 GNSS 上电与查询流程；最终快速复测显示 `gnss_power_state=1`，当前室内无卫星 fix，返回 `+CGNSSINFO: ,,,,,,,,`。
- 已写入 `location_report` 事件到 `pc_simulator/runtime/events.jsonl`，最新事件字段包含 `source=sim7670g_gnss`、`fix=false`、`gnss_state=no_fix`、`gnss_power_state=1`。
- Dashboard 已重启在 `http://127.0.0.1:8787`，`/api/state` 显示最新事件为 `location_report`，设备 `gnss_state=no_fix`，来源 `sim7670g_gnss`。

## 完成标准

- [x] 能通过 AT 自动探测 SIM7670G GNSS 状态。
- [x] 能解析 `CGNSSINFO` / `CGPSINFO` 的 fix 与 no-fix 响应。
- [x] 能生成 PC Simulator 协议兼容的 `location_report`。
- [x] Dashboard/API 能展示真实 GNSS 探测事件。
- [x] 单元测试和全量验证通过。

# CURRENT_TASK: T029 Local Supervised Session Runner

## 任务目标

把本地调试时需要分别打开的 Mosquitto LAN broker、PC Simulator Dashboard、live MQTT Safety worker 和状态摘要整理成一个可显式启动的监督式会话入口，降低多终端运行的黑箱感，并为每次会话留下可追踪日志和摘要报告。

## 范围

- 新增 `scripts/start_local_supervised_session.ps1`，统一启动或复用 broker、Dashboard 和 live MQTT Safety worker。
- 新增 `scripts/local_session_summary.py`，从 `pc_simulator/runtime/events.jsonl` 生成会话 JSON / Markdown 摘要。
- 会话输出写入 `pc_simulator/runtime/sessions/<timestamp>/`，包括 `session.log`、进程日志和 summary 文件。
- 支持 `-NoBroker`、`-NoDashboard`、`-NoWorker`，便于只生成摘要或复用已有进程。
- 支持 `-Watch` 周期刷新 summary，方便运行时观察。
- 增加测试覆盖摘要统计、文件输出和 PowerShell 脚本关键契约。
- 更新状态文档和集成报告。

## 不做

- 不把会话脚本注册为 Windows 服务。
- 不实现进程自动重启、日志轮转或长期守护。
- 不修改 MQTT 协议、Safety Companion M0 模型规则或固件。
- 不真实拨号、拍照、录音或访问外网。
- 不引入 LangGraph、AutoGen、CrewAI 等额外智能体框架。

## 允许修改路径

- `scripts/start_local_supervised_session.ps1`
- `scripts/local_session_summary.py`
- `quality_tests/test_local_session_summary.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_local_session_summary -v
powershell -ExecutionPolicy Bypass -File scripts\start_local_supervised_session.ps1 -NoBroker -NoDashboard -NoWorker
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 新增 `scripts/start_local_supervised_session.ps1`，可统一启动或复用 Mosquitto LAN broker、Dashboard 和 live MQTT Safety worker。
- 新增 `scripts/local_session_summary.py`，可从 `events.jsonl` 生成 `session_summary.json` 和 `session_summary.md`。
- 会话输出目录为 `pc_simulator/runtime/sessions/<timestamp>/`，包含 `session.log`、summary 文件以及进程 stdout/stderr 日志路径。
- `-NoBroker -NoDashboard -NoWorker` 验证通过：不启动后台进程，只生成会话目录和 summary，便于做静态状态快照。
- 直接运行 `python scripts\local_session_summary.py --event-log pc_simulator\runtime\events.jsonl --limit 8 --markdown` 可显示最新 `manual_sos`、`urgent_escalation`、Safety 统计和最近事件。
- `python -m unittest quality_tests.test_local_session_summary -v` 通过，3 个测试成功。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，90 个测试成功。

## 完成标准

- [x] 可以一条命令建立本地监督会话目录并生成 summary。
- [x] 启动脚本可复用/跳过 broker、Dashboard、MQTT Safety worker。
- [x] Summary 同时输出 JSON 和 Markdown。
- [x] 测试覆盖新增摘要逻辑和脚本关键契约。
- [x] 文档记录运行方式、验证结果和剩余限制。

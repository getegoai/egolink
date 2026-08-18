---
id: FIELD-AI-001
title: 首个可回放四源 AI Field Session 与 60 秒 GNSS blackout smoke
status: superseded
priority: critical
requires_hardware: true
created: 2026-08-17
last_updated: 2026-08-18
superseded_by: FT-001B

context:
  - docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md
  - docs/architecture/adr/ADR-0009-ai-v0-1-belief-estimation-baseline.md
  - docs/development/IMU_CALIBRATION.md
  - docs/development/UNIFIED_TIMESTAMP.md
  - docs/development/FIELD_SESSION_SCHEMA.md
  - docs/tasks/active/A0-001_IMU_CALIBRATION_PIPELINE.md
  - docs/tasks/active/A0-002_UNIFIED_TIMESTAMP.md
  - docs/tasks/active/A0-003_FIELD_SESSION_SCHEMA.md
  - shared/contracts/

allowed_paths:
  - docs/tasks/done/FIELD-AI-001_FIRST_REAL_AI_SESSION.md
  - docs/tasks/active/A0-001_IMU_CALIBRATION_PIPELINE.md
  - docs/development/IMU_CALIBRATION.md
  - tools/field_session_sidecar/
  - pc_simulator/field_session_pack.py
  - pc_simulator/field_session_replay.py
  - scripts/pack_field_session.py
  - scripts/replay_field_session.py
  - quality_tests/test_field_session_sidecar.py
  - quality_tests/test_field_session_pack.py
  - quality_tests/test_field_session_replay.py

out_of_scope:
  - 新增或扩展 shared/contracts schema
  - 修改 firmware、Message Hub wire/API/数据库或线上部署
  - production-grade IMU calibration、模型训练或深度融合
  - WEB-004 或其他 Control Plane 新功能
  - 未经操作员确认的刷机、设备命令或硬件配置变更
  - 用 partial、fixture 或缺源数据推进 A0/A-R0 Gate
---

# Problem

> **Superseded on 2026-08-18.** This packet required a four-source Session,
> phone-side Camera/events and trustworthy four-source synchronization before
> the first blackout smoke. Founder direction replaced that prerequisite with
> [FT-001B](../active/FT-001B_FIRST_REPLAYABLE_ASYNC_GNSS_IMU_SESSION.md): independent
> asynchronous acquisition, a GNSS+IMU minimum, opportunistic LTE, optional
> Camera/manual events and server-side event-time reconstruction. The evidence
> and non-claims below remain historical; unchecked criteria are not carried
> forward as current blockers.

已有 A0-001 工程校准、A0-002 时间合同和 A0-003 包合同，但尚无同一次真实外出测试的
GNSS、LTE、IMU、Camera 与人工事件包，也没有能对该包执行 60 秒 GNSS 遮蔽的最小定位
回放。当前优先级是尽快获得真实实验反馈，不再继续扩展基础设施。

# Expected Result

用现有合同形成一个可重复验证、可回放的真实四源 Field Session；Camera 与人工事件可由
测试手机 sidecar 产生，且其独立时钟域和同步不确定性必须如实记录。随后仅运行一次
EXP-A1-000：遮蔽 60 秒 GNSS，比较 last-known、LTE coarse 与 LTE + simple IMU motion。

# Acceptance Criteria

- [x] 记录 sensor/PCB/device 坐标轴当前已知映射；未知部分保持 `unrecorded`，不扩展校准要求。
- [x] 手机 sidecar 在本地记录少量 JPEG 和 `START_WALKING`、`PUT_IN_BAG`、
  `ENTER_BUILDING`、`EXIT_BUILDING`、`STOP`，具有 UTC、单调时间、序列和来源；不上传网络。
- [x] packer 只消费点名的 Message Hub export、IMU window export、sidecar bundle 与 A0-001
  artifact，生成现有 `egolink.field_session.v0.1` 包；缺源或不可验证时间必须显式失败或降级。
  本项只表示实现与 synthetic fixture 往返已验证，不表示真实 Session 已取得。
- [ ] Session 同时保留未校准 IMU 工程值和确定性 calibrated 值，并引用真实 `calibration_id`。
- [x] replay 能按统一时间线加载 GNSS/LTE/IMU/Camera/events，并遮蔽任意 GNSS 区间；输入
  validation 状态和时间不确定性进入输出，不被静默忽略。
  本项只表示实现与 synthetic fixture 已验证，真实四源 Replay 仍未运行。
- [ ] EXP-A1-000 仅运行一次 60 秒遮蔽；三种 baseline 不满足数据先决条件时输出
  `unavailable`，不得补值或宣称胜者。
- [ ] 输出一张轨迹图、一份 error-vs-time、一项 60 秒末误差与机器可读结果；全部绑定
  Session hash、代码 commit 和实际输入。
- [ ] 完成前 A0-001/A0-002/A0-003 与 A-R0 维持现有 evidence-driven Gate，不以代码、
  fixture 或 partial preflight 代替真实 evidence。

# Validation Commands

```powershell
python -m unittest quality_tests.test_field_session_sidecar -v
python -m unittest quality_tests.test_field_session_pack -v
python -m unittest quality_tests.test_field_session_replay -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Hardware Validation

- Board: `ego-link-r1-connectivity-001`，以实际 Session manifest 为准。
- Firmware commit/image: 以实际 Session manifest 和 Field evidence 为准。
- Connection: LTE -> VPS Message Hub；测试手机 sidecar 为独立 Camera/event producer。
- Expected output: 一份真实四源 sealed package、validation report、Replay 与 EXP-A1-000 结果。
- Evidence path: 首个 Session 完成前 unavailable。

# Decisions

- 2026-08-17 当前外出窗口只作为 partial preflight：已有真实 QMI IMU、GNSS/LTE 事件，
  但缺 Camera、人工事件和可信四源同步，因此不进入 EXP-A1-000、不推进 Gate。
- 手机 Camera 是本轮研发 sidecar，不是设备端 Camera 能力或产品依赖证明。
- 使用已有 A0-001 engineering calibration artifact；本任务不增加 production calibration 条件。
- 真实数据问题优先；首个 smoke 完成后停止扩展并只选择一个下一问题。

## 2026-08-17 partial preflight

受控本地 evidence 路径为
`reports/field_validation/A0-FIRST-SESSION-PREFLIGHT-20260817-001/`（Git ignored，
不得提交）。60 秒只读 readiness observer 为 `4/4` successful、`4/4` ready，且观察到
新上传；`field_readiness_report.json` SHA-256 为
`10044011e3a5e93141201b2a49208b2b500bcc77db3ee1456406721943997e4e`。
06:00:00Z 至 06:42:37Z 的完整、未截断 private field export 含 235 messages、29
redacted raw frames、0 commands；其 SHA-256 为
`791386ced02d01a4564f394aabf6601c7762daa98a044a797e3a95b86e4ff0d0`。

这只证明 LTE -> VPS 数据路径在该窗口可读，不证明四源 Session、同步、定位精度或
blackout 实验。实际数据暴露的首要约束是 GNSS/LTE 约一分钟级上报，且低频 IMU 在后半段
没有继续增长；同时缺 Camera、五个人工事件与有界高频 IMU window。因此当前 run 只归档为
`partial_preflight / gate_ineligible`。
局部导出还横跨 3 个 boot domain，GNSS/LTE 观测本身又缺可信的 boot-scoped
monotonic lineage，所以不得将它重包装为单 boot 会话。

07:13:55Z 至 07:14:28Z 的第二次 30 秒只读抽样仍为 `3/3` ready，设备最新
sequence 为 394，但窗口内没有观察到新上传，因此结果为 WARN；报告 SHA-256 为
`8584ecbbbfe46e7b289f149e24f2fcb3720b5aa51dbe112d08ec63365d9e2a9b`。这与约一分钟级
cadence 一致，只说明本窗口过短，不能推断设备离线或链路失败。

下一次正式 run 不改 firmware/schema：使用同一 `FS-...` ID 启动手机 sidecar，按真实时刻
记录五个事件和少量 JPEG；在操作员明确确认安全、正常步行后，执行预先 dry-run 的恰好 3 个
现有 `100 x 50 ms` bounded IMU windows，不自动补采。只有封包后存在一个区间内至少 1 个
可信 GNSS fix、区间前 last-known fix 和恰好 60 秒终点 reference，才运行 EXP-A1-000。
没有冻结且带 provenance/hash 的 LTE centroid artifact 时 B 必须 `unavailable`；3 个短 IMU
window 不构成连续 60 秒覆盖，C 也不得通过放宽参数伪装可用。

# Completion Evidence

- Changed files: A0-001 收口文档、本任务包、离线手机 sidecar、最小 packer/Replay CLI
  及其聚焦测试；未改 firmware、Message Hub、shared schema 或部署。
- Test result: sidecar `4/4`、packer `9/9`、Replay `17/17`；pack -> sealed/valid -> Replay
  实际临时目录往返通过，但仅为 synthetic engineering smoke；`context_lint`、
  `py_compile`、`git diff --check` 通过，仓库完整回归 `777/777` 通过。
- Hardware result: partial preflight only; full four-source Session unavailable.
- Remaining risks: 当前 GNSS 只有同源 UTC、LTE 只有 receive time、sidecar 只有
  estimated mapping；当前导出跨 3 个 boot domain，且 60 秒内定位采样密度尚未达到实验先决条件。

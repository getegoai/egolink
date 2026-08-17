---
id: A0-003
title: Standard Field Session schema and sealed package validation
status: active
priority: critical
requires_hardware: true
created: 2026-08-17
last_updated: 2026-08-17

context:
  - docs/current/EGO_LINK_A_LINE_AI_CONTEXT.md
  - docs/current/ACTIVE_BUILD.md
  - docs/architecture/SYSTEM_OVERVIEW.md
  - docs/architecture/adr/ADR-0009-ai-v0-1-belief-estimation-baseline.md
  - docs/development/UNIFIED_TIMESTAMP.md
  - docs/development/FIELD_SESSION_SCHEMA.md
  - docs/development/DIRECTOR_WORKFLOW.md
  - shared/contracts/README.md

allowed_paths:
  - docs/CONTEXT_INDEX.md
  - docs/development/FIELD_SESSION_SCHEMA.md
  - docs/tasks/active/A0-003_FIELD_SESSION_SCHEMA.md
  - pc_simulator/field_session.py
  - quality_tests/test_a0_field_session.py
  - scripts/validate_field_session.py
  - shared/contracts/README.md
  - shared/contracts/field_manual_event.schema.json
  - shared/contracts/field_session_manifest.schema.json
  - shared/contracts/imu_field_calibrated_window.schema.json

out_of_scope:
  - firmware changes, flashing, device commands or hardware configuration
  - device wire protocol or existing egolink.p0.v1 behavior changes
  - VPS Message Hub schema, ingestion, storage or deployment changes
  - starting a Camera capture, serial capture or real Field Session in this static slice
  - A0-004 dataset quality thresholds, train/validation/test assignment or leakage approval
  - A0-005 labels beyond the bounded weak manual-event contract
  - replay, evaluation, model training, fusion or Location Belief behavior
  - marking A0-003, A0-002 or A-R0 passed without reviewed real evidence
---

# Problem

现有 IMU export、GNSS/LTE observation、Camera smoke output、Message Hub
`test_run_id` 与旧 `field_run_id` 尚未形成一个统一、不可变、可反复验证的采集
单元。缺少标准 Session 身份、四源范围、人工事件、calibration/software/device
provenance、artifact closure 与 A0-002 exact-input 绑定时，后续 validator、Replay
和 benchmark 无法确认自己使用的是同一次真实采集。

# Expected Result

建立 additive `egolink.field_session.v0.1` 与
`egolink.field_manual_event.v0.1` 契约，以及一个 fail-closed 离线命令，能创建
计划 manifest、验证显式包、重算并绑定 A0-002 报告、检查 seal/package closure，
且不改变 firmware、wire protocol 或 Message Hub。

本任务服务于 D2、D5 与 A-R0。静态实现完成只建立数据生产合同，不构成任何
AI Gate PASS。

# Acceptance Criteria

- [x] Manifest 机器可读地保存标准 Session ID、设备/boot/software/firmware、
  calibration、route/scenario/repeat、sensor policy、battery、privacy、artifact、
  stream、time-lineage 与旧 ID provenance。
- [x] 标准 profile 显式声明 GNSS、LTE、IMU、Camera 与 manual event；缺失来源
  必须以 unavailable/not-requested 和原因记录，不能静默省略。
- [x] 人工事件保存事件/传输时间、类型、note、operator、device/clock/mapping
  provenance，并明确仅为 weak operator event。
- [x] raw 与 calibrated IMU stream 可同时保存；calibrated stream 必须绑定
  calibration artifact、source stream 与 generator，raw 不得丢失。
- [x] 校验器拒绝路径逃逸、symlink/junction、额外文件、hash/size/count/分片
  不一致，并验证 manifest/artifact-set seal 与 package closure。
- [x] 校验器从 manifest 声明的 exact A0-002 inputs 重算报告，并核对包内报告、
  Session/device/boot/clock 及 source/anchor artifact path + SHA-256 绑定。
- [x] raw Session 固定 `training_status=not_evaluated`、
  `training_eligible=false`，且不能自行授权训练或分配数据集 split。
- [x] 聚焦测试覆盖标准包、malformed input、ID/hash 冲突、路径逃逸、seal tamper、
  closure、人工事件、隐私、A0-002 exact-input 及 Gate 不晋级语义。
- [ ] 一个真实、经审阅的 Field Session 捕获四类传感器和至少一个人工事件，
  并绑定真实 firmware/software/calibration/privacy/A0-002 evidence。

# Validation Commands

```powershell
python -m py_compile pc_simulator/field_session.py scripts/validate_field_session.py
python -m unittest quality_tests.test_a0_field_session -v
python -m unittest quality_tests.test_a0_unified_timestamp -v
python scripts/context_lint.py
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
git diff --check
```

# Hardware Validation

- Required later: yes, for the reviewed real four-source + manual-event Session.
- Board: unverified for the A0-003 Gate in this static slice.
- Firmware commit/image: unavailable until a producer task is authorized and run.
- Connection/capture path: unavailable.
- Evidence path/hash: unavailable.
- 本静态切片不发送硬件命令、不启动采集、不修改 firmware。

# Decisions

- 使用独立标准 `session_id`；旧 run/session ID 仅进入 provenance。
- 一个 `device_run` 只覆盖一次 boot/clock scope；跨 boot 必须拆分。
- 采用顶层 artifact inventory、规范化相对 POSIX path、SHA-256 与显式 package
  closure，`complete` 与 `sealed` 分离。
- 不信任包内缓存结论：A0-002 必须从 exact inputs 重算后精确比较。
- 场景声明和 manual event 均不自动成为 ground truth。
- A0-003 只判断单包结构完整性；训练适用性与 split leakage 交给 A0-004。
- 无论 static fixture 是否通过，报告的 `gate_status` 保持 `unverified`。

# Completion Evidence

- Changed files: 仅 `allowed_paths` 中的 10 个路径。
- Static validation: `test_a0_field_session` 17/17、`test_a0_unified_timestamp`
  22/22、全仓 `verify.ps1` 747/747，以及 `context_lint.py` 均通过。
- Hardware result: unavailable; no hardware action performed.
- Gate result: A0-003 remains active; A0-002 remains active; A-R0 remains 0/8.
- Remaining risks: 真实 Camera 结构化采集不可用；尚无真实四源 + manual event
  标准 Session；A0-002 共同 anchor、最大同步误差和冻结阈值仍缺失。

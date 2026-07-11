# EgoLink 项目进度看板

- 生成时间: 2026-07-11 13:20 UTC
- 分支: `d2/historical-baseline-and-rule-freeze` @ 703eed0 docs(map): record local overlay deployment [D2]
- 当前焦点: D2 historical VPS baseline is visible but provisional; next focus is the strict reference-point baseline, 24h measured battery run, and external QMI8658 bring-up.
- 已完成任务总数: 143，进行中: 6，暂停: 2

## 里程碑

| 里程碑 | 进度 | 任务 |
|---|---|---|
| RELEASE Engineering Alpha Release Gate | 3/3 | ✅v0.1.0 alpha readiness ✅retire autonomous queue ✅progress board |
| D1 Link-Through Regression | 0/2 | ⏳4G link-through ⏳power baseline |
| D2 Location Accuracy Baseline | 7/9 | ⏳location baseline tooling ⏳reference-point field run ✅no-key evidence map ✅server readiness observer ✅reference field automation ✅bounded field export ✅mobile reference capture ✅local reference overlay ✅historical VPS baseline and rule freeze |
| D5 Location Data Flywheel | 0/2 | ⏳location data flywheel 📋location model loop |
| PRODUCT Product Alpha Gaps | 1/3 | 📋call/SMS verification ✅long power baseline 📋location data policy |

图例: ✅完成 ⏳进行中 ⏸暂停 📋计划中

## 进行中/暂停的任务

| 任务 | 标题 | 状态 | 优先级 | 执行者 |
|---|---|---|---|---|
| D1-001 | D1 link-through baseline | accepted_for_transition | high | codex + founder field tests |
| D2-001 | D2 location accuracy baseline and metric gate | active | high | codex |
| D5-001 | D5 location data flywheel mainline | active | high | codex |
| FIELD-003 | Outdoor GNSS acceptance protocol and first measured run | active | high | founder outdoor run + codex postrun |
| FIELD-004 | D1 outdoor multi-hour field run | continuous_regression | high | - |
| MODEL-001 | Model footprint assessment | paused | high | - |
| PROD-001 | Mass-production requirements definition and module/MCU selection gates | paused | high | - |
| PWR-001 | Real power telemetry and first 24h battery baseline run | active | high | codex + founder field tests |

## 最近完成

| 任务 | 标题 | 日期 |
|---|---|---|
| D2-002 | D2 reference-point field-run automation | 2026-07-11 |
| D2-003 | Bounded device and time-window field export | 2026-07-11 |
| D2-004 | Historical VPS baseline and P0 location rule freeze | 2026-07-11 |
| MAP-001 | D2/D5 map evidence view | 2026-07-11 |
| MAP-002 | Mobile local-only D2 reference capture | 2026-07-11 |
| MAP-003 | Browser-local D2 reference overlay | 2026-07-11 |
| FIELD-010 | Server field readiness observer | 2026-07-10 |
| REL-012 | v0.1.0 Engineering Alpha Release Gate | 2026-07-10 |

## 等待创始人处理

- [ ] 24h 电池运行：现有 2.6Ah 18650 可用于工程基线；先确认板版本/极性，再刷 PWR-001 固件并断 USB 独立运行
- [ ] 采购：QMI8658/I2C IMU 小模块×2-3，优先选 3.3V、地址可确认、带 INT 和固定孔的模块
- [ ] 3D 打印：4G板+电池+IMU 挂绳壳（D3 佩戴测试机）
- [ ] 决策：EVT-1 自制合并板启动（嘉立创打样）—— 待创始人确认后我起草 HW-EVT1-001
- [ ] Do not claim call/SMS, product location accuracy, model performance, or battery life until named evidence exists.

## 关键版本 (KR)

| KR | 状态 | 标题 |
|---|---|---|
| KR-001 | released |  |
| KR-002 | release_candidate |  |
| KR-003 | released |  |
| KR-004 | released |  |
| KR-005 | released |  |
| KR-006 | released |  |
| KR-007 | released |  |
| KR-008 | released |  |

---

本文件由 `python scripts/build_progress_board.py` 生成，请勿手工编辑。
数据来源: docs/tasks/ 任务包 frontmatter、docs/current/progress_board_config.json、
docs/current/key_releases/。

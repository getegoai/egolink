# EgoLink 项目进度看板

- 生成时间: 2026-08-11 08:55 UTC
- 分支: `d2/gnss-imu-field-seed` @ 27e5ec4 feat(web): simplify founder dashboard [D2-D5]
- 当前焦点: FIELD-011 台架闭环已通过：同一镜像完成一次操作员确认的静止 QMI8658 LTE 窗口和 LTE/GNSS 状态上报。下一步是在独立供电、固定携带位置下完成户外 GNSS 与三次正常步行窗口，再进入 D2 指标和 D5 标注。
- 已完成任务总数: 147，进行中: 11，暂停: 2

## 里程碑

| 里程碑 | 进度 | 任务 |
|---|---|---|
| RELEASE Engineering Alpha Release Gate | 4/4 | ✅v0.1.0 alpha readiness ✅retire autonomous queue ✅progress board ✅VPS progress visibility |
| D1 Link-Through Regression | 0/2 | ⏳4G link-through ⏳power baseline |
| D2 Location Accuracy Baseline | 8/10 | ⏳location baseline tooling ⏳reference-point field run ✅no-key evidence map ✅server readiness observer ✅reference field automation ✅bounded field export ✅mobile reference capture ✅local reference overlay ✅historical VPS baseline and rule freeze ✅QMI configuration and motion readiness |
| D5 Location Data Flywheel | 0/2 | ⏳location data flywheel 📋location model loop |
| PRODUCT Product Alpha Gaps | 1/3 | 📋call/SMS verification ✅long power baseline 📋location data policy |

图例: ✅完成 ⏳进行中 ⏸暂停 📋计划中

## 进行中/暂停的任务

| 任务 | 标题 | 状态 | 优先级 | 执行者 |
|---|---|---|---|---|
| D1-001 | D1 link-through baseline | accepted_for_transition | high | codex + founder field tests |
| D2-001 | D2 location accuracy baseline and metric gate | active | high | codex |
| D2-006 | QMI8658 external-module hardware identity probe | active | high | - |
| D2-007 | QMI8658 bounded window capture and LTE uplink | active | high | - |
| D2-008 | Wi-Fi QMI8658 sensor telemetry smoke | active | high | - |
| D5-001 | D5 location data flywheel mainline | active | high | codex |
| FIELD-003 | Outdoor GNSS acceptance protocol and first measured run | active | high | founder outdoor run + codex postrun |
| FIELD-004 | D1 outdoor multi-hour field run | continuous_regression | high | - |
| FIELD-011 | GNSS plus IMU LTE joint outdoor seed | active | high | - |
| MODEL-001 | Model footprint assessment | paused | high | - |
| PROD-001 | Mass-production requirements definition and module/MCU selection gates | paused | high | - |
| PWR-001 | Real power telemetry and first 24h battery baseline run | active | high | codex + founder field tests |
| WEB-003 | Founder Dashboard clarity and field-first hierarchy | active | high | - |

## 最近完成

| 任务 | 标题 | 日期 |
|---|---|---|
| D2-009 | QMI8658 bounded Wi-Fi window uplink | 2026-08-11 |
| D5-002 | QMI8658 labelled multi-window dataset seed | 2026-08-11 |
| D2-002 | D2 reference-point field-run automation | 2026-07-11 |
| D2-003 | Bounded device and time-window field export | 2026-07-11 |
| D2-004 | Historical VPS baseline and P0 location rule freeze | 2026-07-11 |
| D2-005 | QMI8658 4G-board configuration and motion-data readiness | 2026-07-11 |
| MAP-001 | D2/D5 map evidence view | 2026-07-11 |
| MAP-002 | Mobile local-only D2 reference capture | 2026-07-11 |

## 等待创始人处理

- [ ] 户外联测：把开发板和传感器固定在一个明确携带位置，使用稳定移动电源，并在开阔处等待 GNSS。
- [ ] 开始前记录携带位置、方向和时间；准备好后再创建三次正常步行六轴窗口，任一异常即停止。
- [ ] v0.4 PCB、芯片和外壳设计继续并行迭代，不阻塞当前开发板的数据采集闭环。
- [ ] 在具名证据完成前，不宣称定位精度、模型效果、续航、量产或正式安全能力。

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

# EgoLink 项目进度看板

- 生成时间: 2026-09-09 08:26 UTC
- 分支: `a0/first-real-field-session` @ f15bb6852 fix(progress): emit repository-relative task paths
- 当前焦点: 单 4G 主板 Camera/Location 联合源码与离线构建已通过审计；当前不代表实机通过。下一步先私密备份并确认 0x600000..0xF00000 专用于照片，再验证 OV5640 与 QMI8658/MAX17048 共总线，生成启用 SIM/LTE 的具名本地候选，完成部署/刷写后执行真实 LTE 单拍、断网重启补传和独立供电短测，最后进入 FIELD-020。
- 已完成任务总数: 162，进行中: 30，暂停: 5

## 里程碑

| 里程碑 | 进度 | 任务 |
|---|---|---|
| A-CAMERA Single-board Location and Camera Closure | 0/2 | ⏳joint source and live closure ⏳representative field dataset |
| C-PRODUCT Hardware and Pre-compliance | 0/2 | ⏳integrated hardware architecture ⏳China pre-compliance |
| DEFERRED-P0 Paused Call and SOS Gates | 0/3 | ⏸LTE data voice PoC ⏸embedded RTC media ⏸physical SOS closure |
| RELEASE Engineering Alpha Release Gate | 4/4 | ✅v0.1.0 alpha readiness ✅retire autonomous queue ✅progress board ✅VPS progress visibility |
| D1 Link-Through Regression | 1/2 | ✅4G link-through ⏳power baseline |
| D2 Location Accuracy Baseline | 8/10 | ⏳location baseline tooling ⏳reference-point field run ✅no-key evidence map ✅server readiness observer ✅reference field automation ✅bounded field export ✅mobile reference capture ✅local reference overlay ✅historical VPS baseline and rule freeze ✅QMI configuration and motion readiness |
| D5 Location Data Flywheel | 0/2 | ⏳location data flywheel 📋location model loop |
| PRODUCT Product Alpha Gaps | 1/3 | 📋call/SMS verification ✅long power baseline 📋location data policy |

图例: ✅完成 ⏳进行中 ⏸暂停 📋计划中

## 进行中/暂停的任务

| 任务 | 标题 | 状态 | 优先级 | 执行者 |
|---|---|---|---|---|
| A0-001 | IMU six-face calibration pipeline | active | critical | - |
| A0-002 | Unified sensor timestamp and time-lineage validation | active | critical | - |
| A0-003 | Standard Field Session schema and sealed package validation | active | critical | - |
| CALL-020 | PC-bridged LTE-data RTC media PoC | paused | critical | paused |
| CALL-021 | Embedded LTE-data RTC media | paused | critical | paused |
| COMPLIANCE-010 | China P0 pre-compliance and classification | active | critical | codex + qualified labs/advisers |
| D2-001 | D2 location accuracy baseline and metric gate | active | high | codex |
| D5-001 | D5 location data flywheel mainline | active | high | codex |
| DOC-BASE-001 | Establish the current Ego product-direction baseline | active | high | - |
| FIELD-003 | Outdoor GNSS acceptance protocol and first measured run | active | high | founder outdoor run + codex postrun |
| FIELD-004 | D1 outdoor multi-hour field run | continuous_regression | high | - |
| FIELD-011 | GNSS plus IMU LTE joint outdoor seed | active | high | - |
| FIELD-020 | P0-LOC representative field dataset | active | critical | founder field run + codex evidence closure |
| FT-001B | First replayable asynchronous L1 GNSS and IMU field session | active | critical | - |
| FW-005 | SIM7670 GNSS coordinate and response correctness | active | high | - |
| FW-006 | Deploy the FW-005 GNSS correctness image to the connectivity node | active | high | - |
| FW-007 | Bounded LTE to Wi-Fi engineering failover | active | high | - |
| HW-021 | Exact integrated P0 prototype design and down-select | active | critical | codex hardware lane |
| HW-022 | Integrated P0 prototype build and bring-up | active | critical | - |
| L2-001 | Continuous IMU mobility capture, persistent spool and replay | active | medium | - |
| LOC-021 | Device, Message Hub and Guardian Location integration | active | critical | - |
| MODEL-001 | Model footprint assessment | paused | high | - |
| OPS-002 | Official ego.example.invalid HTTPS entry and always-visible AMap canvas | active | high | - |
| OPS-003 | Suppress AMap coordinate-convert access logs | active | high | - |
| OPS-004 | Migrate device ingress from plaintext HTTP to TLS | active | critical | - |
| OUTBOX-010 | Persistent priority outbox | active | critical | - |
| P0-CONVERGENCE-20260905 | Single-board Location and Camera field closure | active | critical | codex + founder bounded hardware run |
| P0-RELEASE-010 | Saleable P0 release criteria and evidence review | active | critical | - |
| PROD-001 | Mass-production requirements definition and module/MCU selection gates | paused | high | - |
| PWR-001 | Real power telemetry and first 24h battery baseline run | active | high | codex + founder field tests |
| PWR-020 | Integrated P0 power and 48-hour guard matrix | active | critical | - |
| SOS-010 | Physical SOS walking skeleton | paused | critical | paused |
| WEB-004 | AMap live location view with runtime-only credentials | active | high | - |
| WEB-005 | Manual Dashboard refresh and selected trusted trajectory | active | high | - |
| WEB-006 | Paginated searchable all-location history | active | high | - |

## 最近完成

| 任务 | 标题 | 日期 |
|---|---|---|
| D2-006 | QMI8658 external-module hardware identity probe | 2026-09-09 |
| D2-007 | QMI8658 bounded window capture and LTE uplink | 2026-09-09 |
| D2-008 | Wi-Fi QMI8658 sensor telemetry smoke | 2026-09-09 |
| CALL-010 | Wearable audio I/O and simultaneous-loop bring-up | 2026-09-05 |
| CALL-001 | Freeze Ego Call minimum architecture and PC loop | 2026-08-23 |
| HW-020 | P0 A0 architecture baseline and candidate constraints | 2026-08-23 |
| L1-000 | Restore contract-consistent green L1 engineering baseline | 2026-08-23 |
| LOC-020 | Location Engine v0 | 2026-08-23 |

## 等待创始人处理

- [ ] 保持当前 4G 板处于 ROM bootloader；首次 Camera 候选刷写前，允许并完成 0x600000..0xF00000 的私密预读备份和专用区确认。
- [ ] 核对实物 OV5640/排线方向、外接 QMI8658A/MAX17048 接线、SIM、LTE/GNSS 天线和独立电源；共享 I2C 未实测前不得打开 verified Gate。
- [ ] 下一次实机阶段一次性确认 VPS 部署、精确 COM3 刷写、SIM 流量、允许拍摄的测试场景/人员、授权查看者与保留截止；不采音频、不公开照片。
- [ ] 先完成真实 LTE 单拍和离线重启同文件补传，再做单板短程携带；现场 blocker 清零后才启动 FIELD-020。
- [ ] 在具名现场证据完成前，不宣称 Camera 外测就绪、定位精度、续航、量产或任何 P0 Gate 通过。

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

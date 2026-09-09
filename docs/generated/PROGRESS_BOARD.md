# EgoLink 项目进度看板

- 生成时间: 2026-09-09 11:09 UTC
- 分支: `a0/first-real-field-session` @ ef3c06f6a docs(hardware): add camera productization inputs [C]
- 当前焦点: Camera 默认 blocked；显式 shared-I2C trial profile 已完成干净离线构建，每次启动只允许一次 Web 手动实际尝试且禁止定时。该构建的 Wi-Fi/认证字段为空，只是构建证据，不能直接联网实拍。下一步是在具名操作/隐私范围内生成被 Git 忽略的 NO_SIM/Wi-Fi 私密 overlay，重建并绑定新 SHA，再部署/刷写/单拍；证据通过审查后才进入 VERIFIED、SIM/LTE、断网补传、独立供电短测和 FIELD-020。
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
| PRODUCT Product Alpha Gaps | 1/3 | 📋call/SMS verification ✅low-power location policy decision 📋location data policy |

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

- [ ] 保持 4G 板断电并核对：仅该板参与；TF 已拔除且驱动禁用，CAM 开关置于 Camera 位置，OV5640 排线方向及 QMI8658A/MAX17048 的 GPIO15/16 接线正确，GPIO39-42 无外部 JTAG；随后只接 4G 板数据 USB。
- [ ] 一次性明确参与者、获准拍摄场景、查看者、保留截止与删除路径，并授权：使用本机私密值生成被 Git 忽略的 NO_SIM/Wi-Fi trial overlay，重建并绑定新的精确 SHA，部署本次 VPS/Web，在 COM3 只刷该具名镜像，再由现有 Web 命令执行一次 QVGA 手动测试。training_allowed=false；不开定时、不使用 SIM、不采音频、不公开或提交照片。
- [ ] 试验后先审查 Camera/IMU/gauge/I2C、heap/DMA/stack、UART/reset/brownout/watchdog 证据，再决定是否生成 VERIFIED；试验成功不自动晋级。随后才准备 SIM、LTE/GNSS 天线和独立电源，进入真实 LTE 单拍与恢复补传。
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

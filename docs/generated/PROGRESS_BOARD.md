# EgoLink 项目进度看板

- 生成时间: 2026-10-27 07:38 UTC
- 分支: `main` @ e85fa39 Record final import validation and original-to-public commit mapping
- 当前焦点: OPEN-001 公开启动与源码导入已完成：Ego 原始 34 次、EgoLink 原始 471 次连续研发序列及当前源码已公开，后续以 getegoai 对应 GitHub main 为实际主线。Link → Base 最小闭环见 ego#2，原硬件任务继续；官网按用户要求以后单独更新。运行证据日期和产品 Gate 以 STATUS / ACTIVE_BUILD 为准。
- 已完成任务总数: 164，进行中: 3，暂停: 5，待验收: 9，排队: 21，搁置: 4，持续回归: 1

## 里程碑

| 里程碑 | 进度 | 任务 |
|---|---|---|
| PUBLIC-DEVELOPMENT EgoLabs 公开项目与协作 | 1/1 | ✅组织入口、项目定义与真实开发主线 |
| STATE-TRUTH 状态真实性与项目对齐 | 1/1 | ✅Codex state truth / contracts / governance |
| A-FIELD 单板恢复与真实外场数据 | 0/3 | ⏳Gemini recovery / route transition 📋reference metrics 📋representative field dataset |
| LOCAL-FIRST 最小用户私有终点（并行准备） | 0/1 | 📋BASE-010 |
| NATIVE-CALL 原生蜂窝主通话与 SOS | 0/4 | ⏳CALL-030 ⏳HW-022 📋CALL-031 ⏸SOS-010 |
| PRODUCT 产品保障 | 0/4 | ⏸HW-021 📋PWR-020 📋COMPLIANCE-010 📋P0-RELEASE-010 |
| RTC-RESERVE 已暂停的 RTC 备路资产 | 0/2 | ⏸CALL-020 ⏸CALL-021 |

图例: ✅完成 ⏳实施中 ⏸暂停/搁置 📋排队 🔎待验收 🔁持续回归

## 开放任务（只有实施中计入 WIP）

| 任务 | 标题 | 状态 | 优先级 | 执行者 |
|---|---|---|---|---|
| A0-001 | IMU six-face calibration pipeline | planned | critical | unassigned |
| A0-002 | Unified sensor timestamp and time-lineage validation | planned | critical | unassigned |
| A0-003 | Standard Field Session schema and sealed package validation | planned | critical | unassigned |
| AI-010 | AI-Native multi-modal self-supervised dataset harvester | planned | high | antigravity |
| AI-020 | TinyML edge model prototype and PC simulation | planned | high | antigravity |
| AI-030 | Dual-track shadow evaluation and safety kernel arbitration simulator | planned | high | antigravity |
| AI-040 | Flywheel continuous fine-tuning, safety regression gate, and model packaging | planned | high | antigravity |
| AI-050 | Ego Base local ingestion, episodic segmentation, and L3 semantic life diary | planned | high | antigravity |
| BASE-010 | Minimum user-controlled private data endpoint | planned | high | unassigned |
| CALL-020 | PC-bridged LTE-data RTC media PoC | paused | critical | paused |
| CALL-021 | Embedded LTE-data RTC media | paused | critical | paused |
| CALL-030 | Native cellular feasibility and audio interface | in_progress | high | gemini |
| CALL-031 | Native cellular primary product loop | planned | high | unassigned |
| COMPLIANCE-010 | China P0 pre-compliance and classification | planned | critical | unassigned / NOT_SENT |
| D2-001 | D2 location accuracy baseline and metric gate | planned | high | gemini |
| D5-001 | D5 location data flywheel mainline | planned | high | unassigned |
| DOC-BASE-001 | Establish the current Ego product-direction baseline | acceptance_review | high | director |
| FIELD-003 | Outdoor GNSS acceptance protocol and first measured run | planned | high | gemini |
| FIELD-004 | D1 outdoor multi-hour field run | continuous_regression | high | - |
| FIELD-011 | GNSS plus IMU LTE joint outdoor seed | planned | high | gemini |
| FIELD-020 | P0-LOC representative field dataset | planned | critical | gemini |
| FT-001B | First replayable asynchronous L1 GNSS and IMU field session | planned | critical | gemini |
| FW-005 | SIM7670 GNSS coordinate and response correctness | acceptance_review | high | director |
| FW-006 | Deploy the FW-005 GNSS correctness image to the connectivity node | acceptance_review | high | director |
| FW-007 | Bounded LTE to Wi-Fi engineering failover | acceptance_review | high | director |
| HW-021 | Exact integrated P0 prototype design and down-select | parked | critical | unassigned |
| HW-022 | Integrated P0 prototype build and bring-up | in_progress | critical | - |
| L2-001 | Continuous IMU mobility capture, persistent spool and replay | planned | medium | - |
| LOC-021 | Device, Message Hub and Guardian Location integration | parked | critical | unassigned |
| MODEL-001 | Model footprint assessment | paused | high | - |
| OPS-002 | Official ego.example.invalid HTTPS entry and always-visible AMap canvas | acceptance_review | high | director |
| OPS-003 | Suppress AMap coordinate-convert access logs | acceptance_review | high | director |
| OPS-004 | Migrate device ingress from plaintext HTTP to TLS | parked | critical | unassigned |
| OUTBOX-010 | Persistent priority outbox | parked | critical | unassigned |
| P0-CONVERGENCE-20260905 | Single-board Location and Camera field closure | in_progress | critical | gemini |
| P0-RELEASE-010 | Saleable P0 release criteria and evidence review | planned | critical | - |
| PROD-001 | Mass-production requirements definition and module/MCU selection gates | paused | high | - |
| PWR-001 | Real power telemetry and first 24h battery baseline run | planned | high | gemini |
| PWR-020 | Integrated P0 power and 48-hour guard matrix | planned | critical | - |
| SOS-010 | Physical SOS walking skeleton | paused | critical | paused |
| WEB-004 | AMap live location view with runtime-only credentials | acceptance_review | high | director |
| WEB-005 | Manual Dashboard refresh and selected trusted trajectory | acceptance_review | high | director |
| WEB-006 | Paginated searchable all-location history | acceptance_review | high | director |

## 最近完成

| 任务 | 标题 | 日期 |
|---|---|---|
| OPEN-001 | EgoLabs 公开项目启动与持续协作 | 2026-10-27 |
| ALIGN-STATE-010 | Align founder decisions and repair ego-state truth and contracts | 2026-09-22 |
| D2-006 | QMI8658 external-module hardware identity probe | 2026-09-09 |
| D2-007 | QMI8658 bounded window capture and LTE uplink | 2026-09-09 |
| D2-008 | Wi-Fi QMI8658 sensor telemetry smoke | 2026-09-09 |
| CALL-010 | Wearable audio I/O and simultaneous-loop bring-up | 2026-09-05 |
| CALL-001 | Freeze Ego Call minimum architecture and PC loop | 2026-08-23 |
| HW-020 | P0 A0 architecture baseline and candidate constraints | 2026-08-23 |

## 等待创始人处理


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

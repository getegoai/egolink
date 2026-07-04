# EgoLink 项目进度看板

- 生成时间: 2026-07-04 10:32 UTC
- 分支: `autodev/egolink-p0` @ 04be197 fix(amoled): force visible d1 status display [AMOLED-004]
- 当前焦点: D1 链路通：4G板+电池独立运行，定时采集 GNSS/基站/IMU/电量，经 LTE 上报，服务器给位置估计，看板地图可见；先通链路，不追求精度
- 已完成任务总数: 81，进行中: 2，暂停: 3

## 里程碑

| 里程碑 | 进度 | 任务 |
|---|---|---|
| D1 链路通 | 0/2 | ⏳D1-001 4G板链路通 ⏳PWR-001 |
| V1-M1 可靠性收尾 | 1/5 | ⏳PWR-001 ⏸FIELD-003 ✅OPS-001 📋STAB-002 LTE长运行/重连门 📋FT-1 可穿戴测试版组装 |
| V1-M2 家人端 MVP | 0/2 | 📋WEB-003 家人看板 📋围栏引擎+通知通道 |
| V1-M3 设备端 AI 轨道（核心） | 1/7 | 📋M1-002 端侧会话记录器 ⏸MODEL-001 模型footprint评估 ✅DATA-002 数据飞轮管线 📋M1-005 标注闭环 📋M1-006 场景采集协议执行 📋MotionNet v0.1 训练+端侧PoC 📋FW-004 固件能力真值源 |
| V1-M4 量产定义与选型 | 0/4 | ⏸PROD-001 📋中国移动模组评估（等资料） 📋MCU渠道报价与选型ADR（等报价） 📋麦克风方案决策 |
| GOV 治理 | 2/2 | ✅ENG-007 ✅ENG-008 |

图例: ✅完成 ⏳进行中 ⏸暂停 📋计划中

## 进行中/暂停的任务

| 任务 | 标题 | 状态 | 优先级 | 执行者 |
|---|---|---|---|---|
| D1-001 | D1 link-through baseline | active | high | codex |
| FIELD-003 | Outdoor GNSS acceptance protocol and first measured run | paused | high | 暂停到D2：claude+创始人（户外执行） |
| MODEL-001 | Model footprint assessment | paused | high | 暂停到D4/D5：codex |
| PROD-001 | Mass-production requirements definition and module/MCU selection gates | paused | high | 暂停：等D1/创始人输入 |
| PWR-001 | Real power telemetry and first 24h battery baseline run | active | high | claude+创始人（刷机/挂电池） |

## 最近完成

| 任务 | 标题 | 日期 |
|---|---|---|
| AMOLED-001 | AMOLED screen interaction sidecar | 2026-07-04 |
| AMOLED-002 | AMOLED D1 status sidecar runner | 2026-07-04 |
| AMOLED-003 | D1 field companion runner with AMOLED sidecar | 2026-07-04 |
| AMOLED-004 | Visible D1 status display on AMOLED sidecar | 2026-07-04 |
| D1-002 | Outdoor field kit with AMOLED companion | 2026-07-04 |
| DATA-002 | Data flywheel pipeline spec | 2026-07-04 |
| DEMO-010 | Product Demo Web Review Gate | 2026-07-03 |
| DEMO-011 | Product Demo Report Web Review Binding | 2026-07-03 |

## 等待创始人处理

- [ ] 采购：PH2.0 锂电池（建议 ≥1500mAh）+ 临时挂绳外壳
- [ ] 刷机操作（每次固件更新约 10 分钟）
- [ ] 24h 电池独立运行（摆放+起止记录）
- [ ] D1 验收：确认看板地图可见、位置估计出现、上报成功率和电量曲线开始记录
- [ ] 安全：修改 VPS root 密码（已在聊天中出现过）并考虑关闭 SSH 密码登录（运维手册第1节有步骤）
- [ ] 一次 2-3 小时户外佩戴走动测试（FIELD-003）
- [ ] 填写 docs/product/MASS_PRODUCTION_FOUNDER_DECISION_SHEET.md，并据此审阅 docs/product/MASS_PRODUCTION_REQUIREMENTS.md 的 TBD(founder) 值
- [ ] 商务：中国移动 4G 模组详细资料
- [ ] 商务：ESP32-S3 / STM32U5A5 / Apollo4 渠道报价
- [ ] 决策：麦克风/交互硬件方案（V1 端侧 AI 陪伴需要）
- [ ] 审阅并提交当前工作区变更（或授权我按任务粒度提交）

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

---

本文件由 `python scripts/build_progress_board.py` 生成，请勿手工编辑。
数据来源: docs/tasks/ 任务包 frontmatter、docs/current/progress_board_config.json、
docs/current/key_releases/。

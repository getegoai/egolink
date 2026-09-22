---
document_status: review
reviewed_at: 2026-09-21
reviewed_by: codex
source_commit: 9de56b92a
---

# 项目目标、现状与后续任务评估 — 2026-09-21

本文件是用户要求的只读审阅结论与排期建议，不替代现有 authority，不接受新的 ADR，不改变产品 Gate 或硬件验证日期。本轮服务 D2/D5、P0-LOC 及后续 P0-CALL/P0-SOS 的可验收任务规划；仅新增此文件。

2026-09-22 后续：用户已授权 [ALIGN-STATE-010](../tasks/done/ALIGN-STATE-010_DECISION_AND_STATE_TRUTH.md)
落实决策、镜像、状态真实性、合同和管理修复；[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
记录 accepted 决策迁移。本文件保留 9/21 审阅时点；最新实施结果以该任务与
[STATUS](../current/STATUS.md) 为准。单板恢复、网络切换、D2 与 FIELD-020 交由 Gemini。

## 1. 目标回顾

[NORTH_STAR](../product/NORTH_STAR.md) 最新决策日期为 **2026-09-19**：

- 终局是随身主动状态估计；可靠定位是用户最直接的功能入口和关键证据。
- 强隐私、本地优先：随身设备承担实时感知和最低安全能力，家庭基站 Ego Base 承担用户私有存储、历史证据和复杂计算，公有云保留中继职责。
- 联络方向改为蜂窝直拨优先、网络通话备用；当前无麦克风/扬声器的开发板跳过声学闭环验证。
- 首发仍需可靠定位、双向联络、实体 SOS，且 AI 不能阻断人工 SOS；无屏模块化产品、48h 实测守护续航、产品安全与制造保证继续有效。

这决定了下一阶段要证明“状态可信、数据归属用户、失联仍可用”。显示一个状态标签、上传成功或出现 SHA-256 字段，都不足以证明这些目标。

## 2. 当前阶段判断

**项目处于可运行工程原型向可测量外场原型收敛的阶段。已具备真实采集/传输/展示切片，尚未完成可靠状态估计、家庭基站和可售 P0 的验收。**

| 能力 | 已有证据与日期 | 尚缺的证明 |
|---|---|---|
| 单板 GNSS/IMU/电量/LTE | run021 Boot171/188 已记录探测、采样与 LTE 上报；最新状态见 [ACTIVE_BUILD](../current/ACTIVE_BUILD.md) 与 [STATUS](../current/STATUS.md)，截至 9/21 | 当前候选的完整运行清单、原始证据路径、代表场景长稳；不能跨镜像直接继承全部成功结论 |
| Camera 手动闭环 | 9/16 run015 真实 JPEG 经 LTE 入库，设备/服务器/认证 API 哈希一致；有[命名硬件报告](../hardware/CAMERA_LTE_MANUAL_CLOSURE_20260916.md) | 当前候选故障恢复和长期并行能力 |
| 普通上传吞吐 | run017 十分钟 248/248 成功、队列归零；仅 USB 供电台架范围 | 长时积压、断网、重启、额度/损坏/丢失统计 |
| 预览、定时与电池运行 | 9/17 预览/导出及 9/18 run019 Boot142 电池定时 3 张、另一轮 2 张后 STOP 已有文档记录；见[集成任务](../tasks/active/P0-CONVERGENCE-20260905.md) | 补齐对应证据文件索引；短时电池运行不代表代表日或续航通过 |
| Ego-state | 端侧规则引擎 → DEVICE frame → SQLite → API/Web 已接入，Boot188 有静止/桌面状态入库记录 | 缺测/过期语义、合同一致性、证据可回放性、人工标签准确度；0.83 是输出分数，不是 83% 准确率 |
| 原生蜂窝联络 | AT 驱动、主机测试、构建及初始化已有记录 | 用户发起/接听入口、失败状态、真实拨接、音频硬件及双向声音；初始化不证明可通话 |
| Ego Base / Local-First | 已有目标和报告/schema 雏形 | 用户私有存储终点、云中继期限与删除、权限/密钥、断网恢复；尚无家庭基站闭环证据 |
| 可售 P0 | P0-LOC / P0-CALL / P0-SOS 均为 `NOT_RUN` | 代表产品定位、通话、SOS、48h、电源、声学、防水、RF、安全隐私、NPI、合规证据 |

9/21 骑行记录中的去程 GNSS fix 可以作为采集线索，不能替代参考点误差基线。回程 no-fix 被归因为倒置口袋/人体衰减的叙述，缺少命名对照实验；该原因应保留为待验证假设。

## 3. 必须先解决的分歧与实现缺口

### 决策与事实冲突登记

| 冲突 | 对排期的影响 | 处理建议 |
|---|---|---|
| 9/19 North Star 蜂窝主路 vs [Master](../product/EGO_MASTER_CONTEXT.md)、[ADR-0011](../architecture/adr/ADR-0011-first-launch-reliable-location-ego-call-sos.md)、[ADR-0012](../architecture/adr/ADR-0012-p0-productization-sprint-1.md) 的 RTC 主路/VoLTE reserve | P0-CALL 与 SOS 联络验收不能直接套用旧定义 | 建立显式后继 ADR/迁移映射，同步产品范围、硬件路径和任务；本评估不自行变更 Gate |
| North Star 同步 Ego Base vs [P0_SCOPE](../product/P0_SCOPE.md) 明确排除正式 Ego Base，以及当前 VPS 持久存储路径 | 私有终点、过渡云存储用途/期限、首发范围尚未统一 | 固化最小 Ego Base 范围与过渡数据生命周期；不得用隐私标志代替实现 |
| North Star 状态估计目标 vs旧 Sprint 的广义状态理解非关键路径 | 不清楚哪些状态能力进入本轮验收 | 区分可解释规则状态基线与高级 L2/L3；明确前者本轮验收范围，禁止自动升级全部 AI 为首发门 |
| STATUS 顶部新证据 vs 后部旧待办；ACTIVE_BUILD 最新 Boot188 vs [BOARD_MATRIX](../hardware/BOARD_MATRIX.md) 的 run017 当前描述 | 可能重做已完成切片，或把旧镜像证据误套到新镜像 | 按 board/image/config/boot/session 和日期核对，仅消除有证据的过期“当前”叙述 |

这些冲突已记录，相关架构/发布变更须按仓库规则完成正式迁移。现有采集链路缺陷审阅、离线准备和不触碰冲突的工作可继续。

### 代码核对的具体缺口

1. **合同未贯穿端到端。** [API 行映射](../../server/collection_store.py) `_ego_state_row_view` 声明 `egolink.ego_state_estimation.v0.1`，但缺少[合同](../../shared/contracts/ego_state_estimation_v0.schema.json)要求的 `estimation_id`、`timestamp_monotonic_ns`、`timestamp_utc`，并混入额外视图字段。现有[API 测试](../../quality_tests/test_ego_state_store_and_api.py)接受 `walking/worn/fall_suspected`，与合同枚举不一致；[Web](../../server/web/scripts/main.js)也存在旧枚举。应明确合同对象和 API 视图边界，统一适配，不用放宽校验掩盖错误。
2. **缺测可能被当作正常静止。** [端侧引擎](../../firmware/mqtt_heartbeat/components/ego_state_engine/ego_state_engine.c)无 IMU 样本时特征为零，窗口过期时回用旧样本；分类仍可输出 stationary/tabletop，置信度从 0.80 起。GNSS 更新时间也未形成相应失效判断。优先补证据年龄、有效性、unknown/降级与回归。
3. **蜂窝驱动尚未形成用户闭环。** [collection_main.c](../../firmware/mqtt_heartbeat/main/collection_main.c)已有串行 modem owner 和拨接指令消费；dial/hangup 应用函数未发现实际调用方，answer 无提交入口，configure 返回失败仍可能置 `ready=true`。需要诚实就绪状态、显式联系人/授权入口及取消/失败处理。
4. **隐私标签与真实存储行为有距离。** 新 `collection_ego_states` 是 VPS SQLite 持久表，所审阅实现未见该表的过期清理；返回固定 `local_priority=true`、`realtime_transient` 不能证明私有存储或短暂保留。Python 报告中的加密标志也不等于加密实现。
5. **策略输出不等于完整省电。** 传感策略已改变 GNSS/Cell 查询间隔，但 `imu_rate_hz` 尚未用于实际 IMU 采样，完整 GNSS 电源占空比与电流收益未验收。应测量实际执行行为和功耗后再讨论续航提升。

## 4. 建议后续任务

下表是建议任务，未派发、未修改 existing active packets。一个集成负责人管理共享合同；每条线只保留一个正在实现的工作项。硬件等待只阻塞其依赖项。

| 顺序 | 工作与服务目标 | 可审阅交付物 / 验收 | 依赖与操作边界 |
|---|---|---|---|
| 第一轮，优先 | **决策迁移与实况对齐**；全项目 | 9/19 后继 ADR 草案、旧/新条款映射；统一 Master/范围/执行路由；当前镜像清单；每条“已验证”有来源，旧待办不重复派发 | Director 整理，Founder 接受决策迁移；不把新日期当新证据，不操作设备 |
| 第一轮，最高软件优先 | **Ego-state 真实性与合同贯通**；D2/D5、可信状态基线 | 缺测、过期、部分来源、mock、重启、重复/乱序均有明确结果；一组固定输入跨 C/Python/入库/API/Web 保持约定语义；非法枚举拒绝或显式隔离；版本、身份、时间、摘要可追溯 | 新窄任务包明确 firmware/model/contracts 权限；离线实现/回归可先做；不修改首发门、不触发 SOS |
| 第一轮准备，第二轮实测 | **单板采集恢复收尾**；现有 P0-CONVERGENCE、FIELD-020 前置 | 固定候选和回退镜像；断网采集 → 重启 → 同 ID/同 JPEG 哈希补传 → 精确 ACK；额度满、损坏、重复/丢失可核对；实际 Wi-Fi/LTE 受控切换和短时独立供电并行运行 | 先完成实验清单、脚本、停止条件与证据路径；刷机、控制、拍照和故障注入需要本任务明确操作者意图；已有预览/定时成功只复核当前候选兼容性 |
| 第二轮主验收 | **D2 参考基线 + FIELD-020**；P0-LOC、D5 | 按[现有 FIELD 包](../tasks/active/FIELD-020_L1_FIELD_DATASET.md)跑代表日；报告 fix rate、TTFF、median/P90 误差、可用率、延迟、队列、功耗及场景覆盖；附静止/步行/骑行/车内/携带方式人工标签、状态混淆矩阵与 unknown 比例 | 采集恢复前置通过；参考点与隐私范围先确定；无真值的场景不造误差；不以单次活动升级 P0-LOC |
| 决策迁移后并行 | **Ego Base v0 最小私有闭环**；Local-First | 先用用户控制的现有主机实现接收、持久化、查询/回放；云端只按明示限额/期限中继；证明基站离线时端侧仍工作、重连补传、权限隔离、删除与保留期限有效 | 依赖合同及数据生命周期决策；先合成数据离线验收，不先部署大模型；真实数据迁移/部署另按具体任务执行 |
| 决策迁移后并行 | **蜂窝联络可行性与 A0 接线**；P0-CALL/P0-SOS、HW-021/022 | 核实准确模组/固件/运营商与音频接口，修复 ready/发起/接听/挂断入口；在具备音频硬件的载体上分别留拨接信令与双向音频证据，再恢复 SOS 集成 | 无音频当前板只做允许范围内的驱动/信令验证，不宣称通话通过；不默认采购、不拨实际联系人、不重启旧 RTC 主路任务 |
| 持续并行、产品阶段收敛 | **功耗与产品保证**；PWR-020、HW、COMPLIANCE-010 | 建立采样/上传/通话负载下的实际电流和峰值供电基线；代表产品再验 48h；推进声学、RF、防水、NPI、书面合规输入 | 当前电池短跑不替代 48h；准备资料可先做，采购、对外发送与实验按具体授权执行 |

最近一轮应交付：**一致的执行基线、不会把缺测伪装成可靠状态的软件、可执行的恢复/切换实验包**。下一轮的主要结果应是**一份可回放且有参考指标的真实外场数据集**。Ego Base 与蜂窝硬件路线按各自依赖并行推进。

暂缓新增可视化装饰、传感器、相机 AI、复杂模型和扩展 RTC 框架；保留现有可用实现。active 目录不是实际 WIP：审阅时有 35 个包，其中包括 paused、回归和验收等待；仅按验收证据逐项归档，不批量宣告完成。

## 5. 本次验证与限制

- 审阅仓库基线：`9de56b92a`；开始时工作区干净。
- 独立合成数据探针：调用实际 `_ego_state_row_view`，按其声明版本的 JSON Schema 校验，复现缺少三个必填字段和额外字段不允许的问题。没有使用私有设备数据，也没有修改测试来制造失败或通过。
- 全量离线回归：`powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`，退出码 0；`Ran 1833 tests in 307.005s; OK (skipped=13)`，即 1,820 项通过、13 项环境条件跳过。日志：`C:/Users/binwe/AppData/Local/Temp/egolink-review-20260921-verify.log`。既有测试全绿不覆盖本次发现的全部语义缺口，跳过项不是实机证据。
- 文档检查：`python scripts/context_lint.py` PASS；`git diff --check` 无问题，新增文件的 `git diff --no-index --check -- NUL docs/roadmap/PROJECT_REVIEW_20260921.md` 也无空白错误输出（退出码 1 表示新增文件与空文件有差异）。
- 本次没有刷机、串口控制、外场采集、拨号、部署或联系第三方；硬件判断来自已有文档/命名证据，不是本轮复测。
- 未解决项：第 3 节决策/事实冲突、新增实机记录的完整证据索引、状态有效性与合同缺陷，以及全部产品验收风险。本次未改 STATUS、任务状态或发布 Gate。

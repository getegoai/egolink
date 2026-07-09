---
document_status: authoritative
last_verified: 2026-07-09
verified_by: codex
owner: founder
---

## 2026-07-09 Founder Direction Update

Continuous outdoor testing is a product regression loop, not an endless gate.
D1 is accepted for transition once the 4G board -> LTE -> VPS -> Dashboard
link is visible, repeatable, and reportable with honest non-claims. Longer
FIELD/PWR runs continue as regression and evidence collection, but they do not
block D2/D5 startup.

Current execution focus moves to the D2 -> D5 mainline:

- D2: establish the first location-accuracy baseline using median error,
  fix rate, and TTFF, with reference-point evidence and Dashboard/map
  visibility.
- D5: build the location-data flywheel from collected field evidence into
  cleaned, labelled, privacy-reviewed samples and eventually model/rule
  improvement loops.
- Map view is a D2/D5 usability and evidence-review requirement. Absence of a
  third-party map API is not a D1 blocker; use no-key/local coordinate and
  trajectory views until a provider/key/privacy decision is made.
- Tiny Safety and safety-classification assets remain reusable later, but the
  immediate AI/data mainline is location accuracy improvement, not synthetic
  safety classification.

# EgoLink 北极星与开发指导原则（NORTH STAR）

本文件是全项目最高层指导。任何执行者（Codex、Claude、其他 AI 或人）在开始
任何任务前必须先读本文件。当本文件与其他文档冲突时，以本文件为准；本文件
只能由创始人决策修改（由 Director 代笔），每次修改必须更新日期并在
`## 变更记录` 留一行。**执行者每次开工必须核对本文件日期，感知目标是否已
变化，并据此调整手头工作——这是防止路线漂移的强制机制。**

## 1. 最终产品（不可漂移的目标）

随身 AI 主动守护定位器（中国市场）：
1. **核心功能一：定位**。多源（GNSS/基站/Wi-Fi/IMU）+ AI 持续逼近的定位，
   配省电策略——传感器按需/占空比工作，绝不常开。
2. **核心功能二：AI 主动安全**。设备采集环境数据，AI 分析预测风险并主动
   执行动作（如给联系人发信息/打电话）。
3. 量产目标：定制 PCB（4G 板 + 手表板功能合并）、48h 守护续航硬指标、
   量产定义见 `docs/product/MASS_PRODUCTION_REQUIREMENTS.md`。

## 2. 迭代哲学：Demo 阶梯，先通后好

**不做一步到位的完美产品。** 路径是 Demo → 第一台原型 → 版本化持续迭代。
每个 Demo 都是一个可刷机、可演示、打了 tag 的版本。定位精度一开始可以不
准，但**链路必须先通**；之后每个版本通过增加传感器数据、改进算法让精度
可量化地上升——"AI 逼近"本身就是发版节奏的主线。

### Demo 阶梯（当前版本）

| Demo | 目标（验收即演示给创始人） | 精度/指标要求 |
|---|---|---|
| **D1 链路通** | 4G 板+电池独立运行：定时采集 GNSS/基站/IMU/电量 → LTE 上报 → 服务器给出一个位置估计 → 看板地图可见 | 有位置就行，不要求准；上报成功率、电量曲线开始记录 |
| **D2 精度爬坡开始** | 加入 Wi-Fi 指纹 known-place 与 last-known 衰减，服务器端融合（EALE-P0 落地跑通）；建立参考点误差测量 | 首次输出误差中位数/fix率/TTFF 三个指标，形成基线 |
| **D3 可佩戴外场** | 挂脖外场 24h+：省电状态机（PWR-002 的 L0-L4）生效，轨迹回放可看 | 24h 实测续航数字；外场误差 vs D2 基线 |
| **D4 主动安全第一步** | 运动异常候选（阈值/统计即可）→ 自动通知联系人（短信或推送）闭环 | 误报率开始记录（打"实验性"标签） |
| **D5 数据飞轮转起来** | 外场数据→标注→模型/参数更新→下一版精度提升，形成"发版即变准"的可见循环 | 精度演进曲线（逐版本对比）上看板 |

每完成一个 Demo：打 tag（v0.D.x）→ 一页 demo 报告（含指标对比上一版）→
创始人验收 → 才进入下一级。指标定义一旦建立（D2）就逐版本追踪，不许断。

## 3. 防漂移规则（对执行者的硬约束）

1. 每个任务开工前自问并在结果中写明：**这个任务服务于哪个 Demo？**
   答不出来的任务不做，报告 Director。
2. 与当前 Demo 无关的"完善型"工作（重构、补文档、加边界声明）一律推迟，
   除非它阻塞当前 Demo。
3. 连续 3 轮修复仍不过 → 停下上报，不许换路径蛮干（LTE-003 八轮修复的
   教训）。
4. 阻塞超过约 2 小时（等硬件、等决策、等资料）→ 立即上报，不空转。
5. 诚实证据规则不变：没实测过的不许声称；密钥不入库；契约变更须经
   Director。

## 4. 流程轻量化（敏捷规则）

**停止做的事：**
- 每个 fix 单独立档长篇记录——fix 过程写进 commit message 即可。
- STATUS.md 千行部署小说——每次只加 ≤10 行摘要，细节放 reports/。
- 任务包里大段 boundary/non-claim 声明——一句话即可，诚实规则全局适用。
- 为覆盖率而写的仪式性测试——只测会坏的东西。

**保留的事（不是官僚，是保命）：**
- 契约冻结（协议/schema 改动须 Director 审）；
- 硬件证据要素（板子、固件版本、时间、证据路径——一行写完就行）；
- 每任务一次 `verify.ps1` + `context_lint.py`。

任务包简化为：目标（一句）、服务哪个 Demo、验收（可执行命令/可观察结果）、
允许路径。其余字段可省。

## 5. Git 与发版规范

- **GitHub Flow**：`main` 永远可构建可刷机；短分支 `d<demo>/<topic>`
  （如 `d1/power-duty-cycle`）；小步快合，不留长分支。
- **必须建远程仓库**（当前没有远程，这是风险）：创始人建 GitHub 私有仓库
  或 VPS Gitea，之后每日至少 push 一次。
- Commit 规范：`<type>(<scope>): <说明> [D<n>]`，type ∈ feat/fix/power/
  loc/safety/ops/docs；例：`feat(loc): add wifi fingerprint upload [D2]`。
- 每个 Demo 验收即打 tag `v0.<demo>.<iter>` 并出一页报告。

## 6. 汇报与看板

- 看板 `docs/generated/PROGRESS_BOARD.md` 是唯一进度真相，任务开/关/阻塞
  都要刷新（`python scripts/build_progress_board.py`）；下一步把它接上 VPS
  Dashboard，创始人手机随时看（OBS-005）。
- 上报给创始人的三类事：Demo 验收就绪、阻塞（含缺硬件/缺决策/缺资料）、
  目标疑似冲突（发现两个权威文档打架时停下来问，不自行裁决）。

## 7. 硬件与省电策略

- **主开发板 = 4G 板（ESP32-S3-SIM7670G）**，单板打通 D1-D5 全部主线
  （它没有屏幕，其余功能都有）。手表板（AMOLED）作为副线单独接电脑开发
  屏幕/交互，不阻塞主线；最终定制 PCB 合并两者（量产阶段）。
- **省电是定位功能的一部分，不是后补优化**：采用 PWR-002 决策的 L0-L4
  状态机——传感器占空比采样、GNSS 按需脉冲（移动/事件才开）、LTE 批量
  上报。任何新增传感器接入必须同时说明它的占空比策略，"常开"默认禁止。
- 真实电量遥测（MAX17048）已在 PWR-001 实装，电量曲线随 D1 起持续记录。

## 8. 文档层级（谁服从谁）

NORTH_STAR（本文件，方向）→ `docs/roadmap/V1_PRODUCT_PLAN.md`（里程碑）→
任务包（执行）。看板反映现状。其余文档是参考资料，不得反向约束方向。

## 变更记录

- 2026-07-09 创始人更新：D1 连续外场测试改为持续回归，不再作为无限期转入卡点；
  启动 D2 定位精度基线与 D5 定位数据飞轮，地图视图进入 D2/D5 证据可视化。
- 2026-07-04 创始人定调：Demo 阶梯 + 敏捷轻流程 + 4G 板为主板 + 省电定位
  优先、AI 主动安全其次；初版发布。

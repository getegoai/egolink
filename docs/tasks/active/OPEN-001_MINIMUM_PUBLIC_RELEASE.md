---
id: OPEN-001
title: EgoLabs 公开项目启动与持续协作
status: done
execution_state: done
owner: Codex
priority: high
lane: public_development
depends_on: []
requires_hardware: false
created: 2026-10-27
last_updated: 2026-10-27
context:
  - docs/CONTEXT_INDEX.md
  - docs/product/NORTH_STAR.md
  - docs/product/OPEN_SOURCE_AND_COMMERCIALIZATION_STRATEGY.md
  - docs/product/EGO_MASTER_CONTEXT.md
  - docs/product/PRODUCT_CHARTER.md
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - README.md
allowed_paths:
  - docs/tasks/active/OPEN-001_MINIMUM_PUBLIC_RELEASE.md
  - tmp/open_source/OPEN-001/
out_of_scope:
  - 将教学案例、合成实验或完整教程设为首发目标或前置
  - 自动注册公司、商标或修改域名解析
  - 重写活跃原仓库历史、变更实机或服务器运行状态
  - 未经明确授权向外部人员发消息或作出商业承诺
---

# Goal

以 **EgoLabs** 建立持续建设的公开项目：先发布项目定义、愿景、产品关系和路线，然后在公开仓库中持续提交真实代码、设计与测试，使用 Issue 和 PR 接收社区参与。

已确认 GitHub 组织为 [getegoai](https://github.com/getegoai)，显示名为 **EgoLabs**；用户提供的 X 名称为 EgoLabs，域名为 `getego.ai`。公司与商标注册情况仍不作推定。

本任务取代上一版“状态真实性教学案例首发”计划。组织、定义/路线、贡献入口、真实源码及其连续研发历史已公开，OPEN-001 的公开启动与源码导入范围现已完成（`done`）。Ego 保留原始 34 次提交，EgoLink 保留原始 471 次提交的连续序列；EgoLink 对实际敏感内容作历史净化并提供提交映射。后续产品开发持续进行，Link → Base 最小闭环由 [ego#2](https://github.com/getegoai/ego/issues/2) 跟踪，不把长期开发留在本启动任务中。

# Launch progress — 2026-10-27

| 公开仓库 | 首发提交 | 本阶段结果 |
|---|---|---|
| [.github](https://github.com/getegoai/.github) | [`9033b9c43da3814b35b3cba4c95a728f6d076f44`](https://github.com/getegoai/.github/commit/9033b9c43da3814b35b3cba4c95a728f6d076f44) | EgoLabs 组织入口已发布 |
| [ego](https://github.com/getegoai/ego) | [`20bd0e6e63fba95ad8116fd59d2b9857ef000afc`](https://github.com/getegoai/ego/commit/20bd0e6e63fba95ad8116fd59d2b9857ef000afc) | 总体定义、愿景、路线与贡献说明已发布 |
| [egolink](https://github.com/getegoai/egolink) | [`73be5cc27e7e7869a2df86437b812a11eabdc794`](https://github.com/getegoai/egolink/commit/73be5cc27e7e7869a2df86437b812a11eabdc794) | 产品定义、真实阶段与源码导入路线已发布 |

源码导入已交付：Ego [`3dfe50e`](https://github.com/getegoai/ego/commit/3dfe50e47e1c9d0b4f642bf8995a41b81b853609)，EgoLink [`e85fa39`](https://github.com/getegoai/egolink/commit/e85fa39a0d07f20b0a735d479af8e043a8235ef2)。对应导入 Issue [ego#1](https://github.com/getegoai/ego/issues/1) 和 [egolink#1](https://github.com/getegoai/egolink/issues/1) 已关闭。首次公开日期为 2026-10-27，原始作者日期保留以呈现真实研发过程，不声称早期提交当时已公开。自有软件按 Apache-2.0，原创文档及 EgoLink 自有硬件设计按 CC BY 4.0；具体资产及第三方例外以各公开仓库 LICENSE/LICENSING 为准。

[官网源码](https://github.com/getegoai/ego/tree/main/website) 已单独发布；本次源码迁移保持网站文件不变，未进行网站部署。按用户明确要求，官网以后单独更新，不作为 OPEN-001 或产品源码导入的未完成项。首发链接与此前部署状态保留在[启动记录](../../archive/decisions/20261027_github_launch/README.md)。

# Repository Plan

`.github`、`ego` 和 `egolink` 已在 `getegoai` 组织下公开；Ego/Data Core 与 EgoLink 当前源码及连续历史已导入，后续以对应 GitHub `main` 为实际开发与协作主线，`egobase` 仍按需要再独立。

| 仓库 | 职责与首批内容 | 与当前实现的关系 |
|---|---|---|
| `.github` | `profile/README.md` 介绍 EgoLabs、愿景摘要、`getego.ai` 和项目入口 | 组织主页；不复制一套完整产品战略 |
| `ego` | 总项目 README、愿景、产品定义、系统关系、路线、贡献入口 | 对接现有 Ego 总仓库，EgoBase/Data Core 当前代码可继续位于已有工作区 |
| `egolink` | EgoLink 产品定义、当前实现、下一步任务；真实硬件、固件、服务端、工具及研发文档 | 延续现有独立仓库的逻辑结构，不为展示另造教学实现 |
| `egobase`，按需要再独立 | 本地中枢、数据和个人长期状态能力 | 初期保留现有 `ego/projects/egobase`；独立发布、接口或维护需要出现时再迁出 |

首批三个仓库不必同一时刻填满。愿景和定义先发布，实际代码按当前可公开范围连续提交；缺失、计划中和存在问题的部分照实标注。不按语言、硬件/固件或“社区版/商业版”过早拆出更多仓库。

# Execution Plan

| 步骤 | 负责人 | 输出与完成标志 |
|---|---|---|
| 1. 首批公开项目表达已完成 | Codex | 准备组织介绍，以及 `ego` 的愿景、产品定义、路线和 `egolink` 的 README；内容回答做什么、为什么、现在到哪、下一步做什么、怎样参与 |
| 2. 组织与三个初始仓库已建立 | 创始人负责组织所有权；Codex 在授权范围配置仓库 | 确认实际组织 URL，先发布 `.github` 和 `ego` 的项目入口；产品定义本身就是有效首次提交，不等代码整理完 |
| 3. 现有研发与连续历史已进入公开主线 | Codex | Ego 原始 34 次、EgoLink 原始 471 次提交序列及当前源码已公开；对具体敏感内容净化并保留映射，关键历史节点以 tag 导航；没有伪造早期公开活动 |
| 4. 首批真实开发 Issue 已建立 | Codex 整理，创始人确认产品优先级 | 从现有 backlog 选少量真正准备做的工作，写清问题、预期结果和复现条件；至少有一项外部贡献者可参与的任务，不要求立即有人领取 |
| 5. 持续在 GitHub 开发 | 维护者与贡献者 | 分支、小提交、PR、必要检查、维护者合并；重要取舍留在 Issue/ADR，阶段结果用 release/changelog 表达 |

公开启动与源码导入已完成。后续沿 GitHub `main` 继续真实研发，通过 Issue、分支和 PR 提交改动；优先推进 ego#2 的最小闭环以及已有硬件任务，不再安排独立教程筹备期。

第一步准备的文档可以很短，结构建议如下，不要求为凑文件而重复写内容：

```text
.github/profile/README.md      EgoLabs 组织介绍与项目入口
ego/README.md                 总项目定义、愿景和当前状态
ego/docs/VISION.md            长期目标；必要时先并入 README
ego/docs/ROADMAP.md           现在 / 接下来 / 更远期
egolink/README.md             产品职责、真实代码入口、使用条件与已知问题
各代码仓库 LICENSE           本批代码适用许可
CONTRIBUTING.md               如何报告、提出方案和提交改动
```

# Public Development Workflow

**一个项目只有一条实际开发主线；公开路线描述这条主线，社区贡献进入这条主线。**

- 对已经开放的部分，GitHub 成为实际协作主仓；现有内部 Git 服务可保存历史、备份及私有资料，不长期维护同一开放模块的两套独立主线。
- Issue 记录问题和计划；较大方向先讨论。分支与 PR 展示实现、检查与取舍，维护者决定合并；只有一个维护者时也可以直接提交小文档改动，不强行增加审批人。
- `main` 的可运行范围和已知失败如实说明；未完成工作可以用分支或 draft PR 公开。开源不要求项目先成熟。
- 社区参与包含问题复现、文档、硬件测试、设计建议和代码。起初以维护者持续推进为主，不等待社区形成才继续研发。
- 研发过程由真实提交、Issue、PR、ADR、测试记录及版本形成；精选案例和教程是可选补充，不是另一条生产线。
- 执行时沿现有授权推进；组织目标或权限确实缺失时只补齐该项，其他准备继续。外部邀约由创始人进行或按明确授权执行。

# Publication Boundary

仅对实际上传的内容及附带历史处理凭据、个人数据、第三方未许可材料和明确保留的细节。不以全仓专利研究、原始私有历史全量清洗或整机验收为公开定义/路线的前置条件。

本次已按用户决定保留连续研发历史，对其中具体敏感内容作替换并记录原始到公开提交的映射；没有采用仅发布当前快照、原历史长期留在内部的方案。暂存目录只用于此次迁移，不成为长期人工筛选导出的发布机制。

自有代码优先 Apache-2.0、文档优先 CC BY 4.0，实际上传时清楚标明适用范围和必要第三方通知。专利与商业验证继续并行；公司、品牌和域名的法律或运营动作不由仓库规划自动执行。

# Acceptance and Validation

- [x] EgoLabs 组织入口和总项目定义/愿景/路线已可访问，真实状态清楚。
- [x] `egolink` 已承载实际产品源码及连续历史，已知问题与未验证范围明确。
- [x] Issue/贡献入口可用，首批真实开发任务明确，本批文档许可清楚。
- [x] 产品源码实际导入，并明确本批代码许可和第三方通知。
- [x] 开放模块的实际协作主线明确，社区 PR 能进入产品开发流程。
- [x] 已记录组织/仓库 URL、文档首发与固定源码导入提交；官网明确为以后单独更新。

本轮文档状态同步验证：

```powershell
python scripts/context_lint.py
git diff --check
```

后续源码导入和修改按实际模块运行已有检查，不新增一个教学案例测试作为总发布门槛。文档/规划完成不冒充仓库已经公开。

# Builder Prompt

OPEN-001 的启动与源码导入已经完成，不重复导入或重建组织。后续从 getegoai/ego 与 getegoai/egolink 的 GitHub main 继续实际开发；Link → Base 最小闭环见 ego#2，其余沿已有产品/硬件任务推进。保留研发历史、公开失败和未完成项，社区贡献进入同一产品主线。官网按用户要求以后单独更新。专利与商业验证并行，不形成额外发布前置。

# Decision Record

2026-10-27 源码导入完成：Ego [`3dfe50e`](https://github.com/getegoai/ego/commit/3dfe50e47e1c9d0b4f642bf8995a41b81b853609)、EgoLink [`e85fa39`](https://github.com/getegoai/egolink/commit/e85fa39a0d07f20b0a735d479af8e043a8235ef2) 已公开；原始 34/471 次连续研发序列保留，GitHub main 成为后续主线。OPEN-001 完成，ego#2 的产品闭环与官网后续更新分别处理。本次未新增实机验收或改变产品 Gate；修改前快照见[导入记忆同步记录](../../archive/decisions/20261027_source_import/README.md)。

2026-10-27 启动进展：确认 `getegoai` 组织显示名为 EgoLabs，三个 public 仓库与首发提交已完成；源码导入和持续开发未完成，OPEN-001 保持 `in_progress`。官网源码已发布但新版未部署。证据与原文件快照见[启动记录](../../archive/decisions/20261027_github_launch/README.md)。

2026-10-27：用户明确 EgoLabs 品牌和 `getego.ai`，要求“定义/愿景/路线先公开、真实项目持续实现、社区可提交贡献”。本任务据此整体改写，取代此前案例首发方案。旧版及入口快照见[迁移记录](../../archive/decisions/20261027_egolabs_public_project/README.md)。

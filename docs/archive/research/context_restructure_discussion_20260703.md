# Archive note

Moved from repository root `上下文重构.md` on 2026-07-03 during workspace
organization. This file is historical research input, not current authority.

## 结论

**不要离开 VS Code，也不需要“完全切换到 Codex”。更合适的做法是：保留 VS Code，把仓库改造成 Codex 原生工程。**

你现在使用的 VS Code Codex 插件本身就是 Codex。官方说明，IDE 扩展与 Codex CLI 使用同一个 Agent，并共享配置；同时，VS Code 中打开的文件、选区和 `@文件名` 可以成为精确上下文，这对固件、串口、板卡验证和模型实验混合工程尤其有价值。([OpenAI 开发者][1])

建议形成下面的分工：

| 使用界面                     | 主要用途                                 |
| ------------------------ | ------------------------------------ |
| VS Code + Codex 插件       | 日常开发、查看代码、硬件调试、串口日志、交互式修改            |
| VS Code 集成终端中的 Codex CLI | 中转 API、不同模型 Profile、批处理、自动测试、Autodev |
| Codex 独立客户端              | 可选，用于长任务、并行 worktree、集中审查            |
| GPT-5.5                  | 架构、任务拆分、疑难问题、最终 review               |
| 中转 API 模型                | 常规开发、测试、文档、机械性重构                     |

核心不是更换编辑器，而是建立：

```text
AGENTS 约束
→ Context Index 路由
→ Task Packet 限定任务
→ 按需读取领域上下文
→ 修改与测试
→ Evidence 记录
→ GPT-5.5 差异审查
```

---

# 一、你当前目录结构存在的主要问题

仅从目录结构看，已经有一定的上下文工程意识，但目前更像是“积累了很多说明文档”，还没有形成明确的上下文加载机制。

## 1. 两个 `AGENTS.md` 的职责可能混乱

当前有：

```text
/AGENTS.md
/docs/AGENTS.md
```

Codex 并不会递归读取仓库中所有 `AGENTS.md`。它是从项目根目录沿着**当前工作目录**向下构造指令链，每层最多加载一个文件；默认总量达到约 32 KiB 后停止继续加入。([OpenAI 开发者][2])

因此：

* 根目录启动的 VS Code/Codex 会稳定读取根 `AGENTS.md`；
* `docs/AGENTS.md` 通常只有当前工作目录位于 `docs/` 下时才会进入原生发现链；
* 它不会因为正在修改 `docs/xxx.md` 就自动加载 `docs/AGENTS.md`。

调整原则：

* 根 `AGENTS.md`：全项目规则和上下文路由；
* `docs/AGENTS.md`：只保留文档编写规则；
* 如果 `docs/AGENTS.md` 里是全局开发要求，应合并到根文件；
* 根 `AGENTS.md` 要明确要求：修改特定模块前主动读取该目录的 `AGENTS.md`。

## 2. 文档比较扁平，权威性不明确

目前 `docs/` 根下同时存在：

```text
STATUS.md
EGO_LINK_P0_CONTEXT.md
EGO_LINK_AGENTIC_DEV_PLAN.md
DEVELOPMENT_WORKFLOW.md
repository_baseline.md
产品定位.md
多个 AUTODEV 文档
```

模型不容易判断：

* 哪个是当前事实；
* 哪个是未来规划；
* 哪个是历史版本；
* 哪个具有最高优先级；
* 文档冲突时应该信谁。

这会造成上下文浪费，也会出现“模型引用了旧状态，但看起来仍然很合理”的问题。

## 3. `EGO_LINK_P0_CONTEXT.md` 不宜继续承担全部信息

一个巨型 Context 文件容易同时包含：

* 产品定位；
* 当前硬件；
* 软件架构；
* 近期任务；
* 长期规划；
* 已经失效的实验结果。

其中任何一部分发生变化，整个文件就可能部分过期。

你此前的 `EGO_MASTER_CONTEXT.md` 将自己定义为 Single Source of Truth，同时仍保留 Sprint Day 1、Orange Pi 5 Plus、Qwen2.5 等旧阶段内容。它适合保留为 EGO 父项目历史资料，不适合直接作为当前 EGOLINK P0 的自动上下文，否则会与当前板卡、模型和开发状态产生竞争。

## 4. `.agents` 需要转化为正式 Skills 目录

团队共享 Codex Skill 的标准位置是：

```text
.agents/skills/<skill-name>/SKILL.md
```

Skill 采用渐进式披露：默认只把名称、描述和路径放进上下文，只有任务匹配时才读取完整 `SKILL.md`，比把所有开发流程写进根 `AGENTS.md` 更节省上下文。([OpenAI 开发者][3])

如果当前 `.agents` 里主要是普通提示词、角色说明或长文档，应逐步转成 Skills。

## 5. `reports` 和 `model_artifacts` 不应该被默认扫描

这两个目录可能包含：

* 大量日志；
* 实验报告；
* 模型导出信息；
* 重复结果；
* 二进制文件；
* 旧版本验证记录。

正确方式是：

```text
Task 文件明确指定某个报告
→ Codex 只读取该报告
```

而不是：

```text
Codex 每次自行扫描 reports 和 model_artifacts
```

---

# 二、建议调整后的目录结构

不需要立即改变源码目录，先重构上下文和文档层。

```text
EGOLINK/
├─ AGENTS.md                         # 全项目最高层开发规则与上下文路由
├─ README.md                         # 面向人的项目入口
│
├─ .codex/
│  ├─ config.toml                    # 项目级 Codex 行为配置
│  └─ rules/                         # 第二阶段再增加命令规则
│
├─ .agents/
│  └─ skills/
│     ├─ execute-task/
│     │  └─ SKILL.md
│     ├─ board-validation/
│     │  └─ SKILL.md
│     ├─ firmware-change/
│     │  └─ SKILL.md
│     ├─ model-evaluation/
│     │  └─ SKILL.md
│     └─ release-review/
│        └─ SKILL.md
│
├─ docs/
│  ├─ CONTEXT_INDEX.md               # 上下文路由总表
│  ├─ AGENTS.md                      # 仅限文档编辑规范
│  │
│  ├─ product/
│  │  ├─ PRODUCT_CHARTER.md          # 稳定产品定义
│  │  ├─ P0_SCOPE.md                 # P0边界、非目标、验收标准
│  │  └─ EGO_ECOSYSTEM_RELATION.md   # EGO、EGO Link关系
│  │
│  ├─ current/
│  │  ├─ STATUS.md                   # 当前里程碑及完成情况
│  │  ├─ ACTIVE_BUILD.md             # 当前实际接线、板卡、固件版本
│  │  └─ BLOCKERS.md                 # 当前阻塞与待决问题
│  │
│  ├─ architecture/
│  │  ├─ SYSTEM_OVERVIEW.md
│  │  ├─ INTERFACES.md
│  │  ├─ DATA_FLOW.md
│  │  └─ adr/
│  │     ├─ 0001-xxx.md
│  │     └─ 0002-xxx.md
│  │
│  ├─ hardware/
│  │  ├─ BOARD_MATRIX.md             # 已采购板卡及能力矩阵
│  │  ├─ PINOUTS.md
│  │  ├─ POWER_BUDGET.md
│  │  ├─ BENCH_SETUP.md
│  │  └─ validation/
│  │     └─ P0_BOARD_VALIDATION.md
│  │
│  ├─ modeling/
│  │  ├─ MODEL_ARCHITECTURE.md
│  │  ├─ MODEL_REGISTRY.md
│  │  ├─ DATASETS.md
│  │  └─ EVAL_PROTOCOL.md
│  │
│  ├─ development/
│  │  ├─ WORKFLOW.md
│  │  ├─ TESTING.md
│  │  ├─ AUTODEV.md
│  │  └─ AUTODEV_MONITORING.md
│  │
│  ├─ safety/
│  │  ├─ SAFETY_CONTRACT.md
│  │  └─ CHANGELOG.md
│  │
│  ├─ tasks/
│  │  ├─ active/
│  │  ├─ done/
│  │  └─ TEMPLATE.md
│  │
│  ├─ generated/
│  │  ├─ REPOSITORY_MAP.md
│  │  └─ TEST_INVENTORY.md
│  │
│  └─ archive/
│     ├─ EGO_LINK_P0_CONTEXT_legacy.md
│     └─ historical_plans/
│
├─ firmware/
│  └─ AGENTS.md
├─ model_lab/
│  └─ AGENTS.md
├─ pc_simulator/
│  └─ AGENTS.md
├─ quality_tests/
│  └─ AGENTS.md
├─ autodev/
│  └─ AGENTS.md
│
├─ model_artifacts/
├─ reports/
├─ scripts/
└─ shared/
   └─ contracts/
```

这里最关键的不是目录名称，而是把上下文分成四种性质：

| 类型   | 典型文件                          | 特征           |
| ---- | ----------------------------- | ------------ |
| 稳定规则 | `AGENTS.md`、产品定义、安全约束         | 很少变化，默认加载    |
| 当前事实 | `STATUS.md`、`ACTIVE_BUILD.md` | 经常更新，任务开始时读取 |
| 领域知识 | 硬件、模型、协议、架构                   | 按任务读取        |
| 历史证据 | reports、archive、旧 Context     | 只有明确需要时读取    |

---

# 三、现有文件的迁移建议

| 当前文件                                 | 建议处理                                       |
| ------------------------------------ | ------------------------------------------ |
| 根 `AGENTS.md`                        | 保留，改造成总规则和上下文路由                            |
| `docs/AGENTS.md`                     | 仅保留文档格式、语言、图表和链接维护规则                       |
| `docs/产品定位.md`                       | 移到 `docs/product/PRODUCT_CHARTER.md`       |
| `docs/EGO_LINK_P0_CONTEXT.md`        | 拆分后将原文件移入 `docs/archive/`                  |
| `docs/STATUS.md`                     | 移到 `docs/current/STATUS.md`                |
| `docs/repository_baseline.md`        | 改为自动生成的 `docs/generated/REPOSITORY_MAP.md` |
| `docs/P0_BOARD_VALIDATION.md`        | 移到 `docs/hardware/validation/`             |
| 根 `模型架构.md`                          | 移到 `docs/modeling/MODEL_ARCHITECTURE.md`   |
| `AUTODEV_GUIDE.md` 等                 | 合并到 `docs/development/`                    |
| `EGO_LINK_AGENTIC_DEV_PLAN.md`       | 提炼有效内容后归入 `AUTODEV.md`，原件归档                |
| `CHANGELOG_SAFETY_COMPANION.md`      | 移到 `docs/safety/CHANGELOG.md`              |
| `HARDWARE_CONTEXT_PACKAGE_README.md` | 移入 `docs/hardware/` 或对应硬件包目录               |
| `MODEL_PACKAGE_README.md`            | 移入 `model_artifacts/README.md`             |
| `PACKAGE_MANIFEST.json`              | 若脚本依赖路径则先保留；否则放入对应包目录                      |

建议自动化入口文件使用 ASCII 文件名，正文仍然可以全部使用中文。这样在 Windows、WSL、Python 脚本和模型工具链之间更稳定。

---

# 四、根目录 `AGENTS.md` 应该怎么写

根文件不要再写成长篇项目介绍，控制在大约 4–6 KB，只放长期有效的规则和路由。

可以按下面的结构改：

```markdown
# EGOLINK Repository Instructions

## 1. Authoritative sources

- 产品定义：docs/product/PRODUCT_CHARTER.md
- P0范围与非目标：docs/product/P0_SCOPE.md
- 当前状态：docs/current/STATUS.md
- 当前实际硬件与接线：docs/current/ACTIVE_BUILD.md
- 系统接口：docs/architecture/INTERFACES.md
- 已批准架构决策：docs/architecture/adr/
- 当前任务：docs/tasks/active/
- reports/、generated/ 和 archive/ 不是当前事实源。

## 2. Context loading

开始任务前：

1. 读取 docs/CONTEXT_INDEX.md。
2. 读取指定的 active task 文件。
3. 只读取 task 文件中 context 列出的文档。
4. 修改特定模块前，主动读取该模块的 AGENTS.md。
5. 除非任务明确要求，不递归扫描 reports/、model_artifacts/ 或 archive/。

## 3. Source-of-truth rules

- 同一事实只允许有一个权威维护位置。
- 当前板卡、传感器、接线和固件版本以 ACTIVE_BUILD.md 为准。
- 协议字段和数据结构以 shared/contracts/ 中的机器可读文件为准。
- 架构变更必须增加或更新 ADR。
- 不得根据开发板名称推断其具有 IMU、麦克风、GNSS 或其他器件。
- 未验证事实必须标记为 unknown 或 unverified。

## 4. Change discipline

- 一个任务只解决一个明确问题。
- 严格遵守 task 文件中的 allowed_paths 和 out_of_scope。
- 未经批准不得改变引脚、通信协议、持久化格式和公开接口。
- 不提交密钥、真实用户数据、大型模型权重或设备私密日志。
- 不修改 generated/ 中的文件，必须通过对应生成脚本更新。

## 5. Hardware safety

- 编译和静态测试可以自动执行。
- 擦除 Flash、烧录固件、修改设备权限、写入串口控制命令前必须请求确认。
- 硬件验证必须记录板卡型号、固件 commit、接线方式和验证时间。

## 6. Completion gate

完成任务前：

- 运行任务文件中声明的测试命令。
- 记录测试结果和证据路径。
- 更新任务状态。
- 只有里程碑发生变化时才更新 docs/current/STATUS.md。
- 输出修改文件、测试结果、剩余风险和未完成事项。
```

---

# 五、把 `docs/tasks` 变成真正的任务上下文入口

以后不要再给 Codex 一段很长的聊天提示，而是让它执行一个任务文件。

建议的任务模板：

````markdown
---
id: P0-FW-014
title: ESP32 与通信板状态同步验证
status: active
priority: high
execution_profile: ego-build
review_profile: ego-review
requires_hardware: true
created: 2026-06-25
last_updated: 2026-06-25

context:
  - docs/current/STATUS.md
  - docs/current/ACTIVE_BUILD.md
  - docs/architecture/INTERFACES.md
  - docs/hardware/PINOUTS.md
  - firmware/AGENTS.md

allowed_paths:
  - firmware/
  - shared/contracts/
  - quality_tests/

out_of_scope:
  - model_lab/
  - model_artifacts/
  - hardware pin reassignment
  - production cloud services
---

# Problem

描述当前问题及可复现现象。

# Expected result

描述完成后的可观察结果。

# Acceptance criteria

- [ ] 条件一
- [ ] 条件二
- [ ] 条件三

# Validation commands

```bash
<实际测试命令>
````

# Hardware validation

* Board:
* Firmware commit:
* Connection:
* Expected output:
* Evidence path:

# Decisions

记录任务过程中形成但尚未进入 ADR 的临时决定。

# Completion evidence

* Changed files:
* Test result:
* Hardware result:
* Remaining risks:

````

此后给 Codex 的提示可以缩短为：

```text
执行 docs/tasks/active/P0-FW-014.md。
先读取任务声明的 context 和相关模块 AGENTS.md。
严格遵守 allowed_paths，不修改 out_of_scope。
完成测试并把证据写回任务文件。
````

这比每次重新描述整个项目稳定得多。

---

# 六、硬件上下文需要单独强化

EGO Link 当前同时涉及多块开发板、通信模块、IMU、麦克风、电源和串口连接，最容易出现的错误是模型根据商品名推断硬件能力。

建议至少维护两个文件。

## `docs/hardware/BOARD_MATRIX.md`

```markdown
| board_id | 完整型号 | MCU/SoC | IMU | 麦克风 | GNSS | 蜂窝通信 | 验证状态 |
|---|---|---|---|---|---|---|---|
| dev-esp32-01 | 实际型号 | ESP32-... | unknown | unknown | no | no | 待查原理图 |
| modem-01 | 实际型号 | ... | no | no | yes | Cat-1 | 已通电 |
```

所有未确认项统一写：

```text
unknown
```

不能留空，也不能让 Codex自行推断。

## `docs/current/ACTIVE_BUILD.md`

只描述当前桌面上正在使用的组合：

```markdown
---
document_status: authoritative
last_verified: 2026-06-25
verified_by: human
---

# 当前主机环境

# 当前连接板卡

# USB/串口映射

# UART接线

# 固件版本

# 已验证能力

# 未验证能力

# 当前已知问题
```

它应该比“采购清单”优先级更高。采购了某块板，不代表当前原型已经接入了它。

---

# 七、`.agents/skills` 建议先做四个

不要一开始建立十几个 Agent。先把重复工作做成四个 Skill：

```text
.agents/skills/
├─ execute-task/
├─ board-validation/
├─ firmware-change/
└─ release-review/
```

分别负责：

| Skill              | 用途                        |
| ------------------ | ------------------------- |
| `execute-task`     | 读取任务包、限制修改范围、运行测试、回写证据    |
| `board-validation` | 生成或执行板卡验证步骤，更新能力矩阵        |
| `firmware-change`  | 按固件规范修改、构建、禁止未经批准烧录       |
| `release-review`   | 检查 diff、测试、协议兼容、安全风险和文档同步 |

Skill 的完整内容只在被选中时加载，因此比把所有工作流塞进 `AGENTS.md` 更节省上下文。团队 Skill 应放在仓库的 `.agents/skills` 中。([OpenAI 开发者][3])

现有 `autodev` 应改成：

```text
Task Packet
→ Context Resolver
→ 选定模型
→ 执行修改
→ 测试
→ Evidence
→ Review
```

而不是让 Autodev 每轮重新扫描整个仓库。

---

# 八、增加项目级 `.codex/config.toml`

建议先保持简单：

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
```

项目目录中的 `.codex/config.toml` 可以管理沙箱、批准行为和项目级设置，但模型供应商、API 地址、认证和 Profile 应放在用户目录 `~/.codex/` 中；项目级配置中的 provider、认证和 profile 重定向项会被忽略。([OpenAI 开发者][4])

因此结构应是：

```text
仓库：
EGOLINK/.codex/config.toml

个人电脑：
~/.codex/config.toml
~/.codex/ego-fast.config.toml
~/.codex/ego-build.config.toml
~/.codex/ego-review.config.toml
```

中转 API 密钥也只放个人环境变量或用户级配置，不进入项目仓库。

---

# 九、实际开发时的推荐模式

```text
VS Code + Codex
    负责交互、读代码、看 diff、硬件调试

Codex CLI + ego-fast
    负责搜索、测试补齐、文档整理、简单修复

Codex CLI + ego-build
    负责常规功能开发

GPT-5.5
    负责任务设计、接口变更、复杂故障、最终 review
```

不要让多个 Agent 同时修改同一工作区。Codex 的 subagent 会各自执行模型和工具调用，因此会增加 token 消耗；只在独立任务和独立 worktree 中使用。([OpenAI 开发者][5])

---

这次重构适合由 GPT-5.5 先完成盘点和冲突判定，再让普通开发模型执行文件迁移，最后由 GPT-5.5 只审查 `git diff`。完成以后，VS Code 继续作为主工作台，Codex CLI 和中转 API 承担低成本执行，整个项目的上下文消耗会明显下降。

[1]: https://developers.openai.com/codex/ide/features "Features – Codex IDE | OpenAI Developers"
[2]: https://developers.openai.com/codex/guides/agents-md "Custom instructions with AGENTS.md – Codex | OpenAI Developers"
[3]: https://developers.openai.com/codex/skills "Agent Skills – Codex | OpenAI Developers"
[4]: https://developers.openai.com/codex/config-advanced "Advanced Configuration – Codex | OpenAI Developers"
[5]: https://developers.openai.com/codex/subagents?utm_source=chatgpt.com "Subagents – Codex"

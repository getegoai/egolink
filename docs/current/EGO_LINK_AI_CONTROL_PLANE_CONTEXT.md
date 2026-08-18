# Ego Link AI Control Plane 记忆与架构基线

> 文档类型：长期项目记忆 / Codex 控制台上位上下文  
> 项目：Project EGO / Ego Link  
> 子系统：Ego Link AI Control Plane  
> 版本：v1.0  
> 日期：2026-08-16  
> 状态：当前有效基线

## 1. 定位

Ego Link A线建立独立 Web 研发控制台，正式定位为：

> **Ego Link AI Control Plane / AI Development Control Plane（AI研发控制平面）**

它不是普通项目看板，而是用户、Codex、云端 ChatGPT 三方共同使用的研发交流中枢和项目事实中枢。

控制台持续回答：

1. 最终产品目标是什么；
2. 当前处于哪个 Stage；
3. A0-A4 五个 Workstream 分别进展到哪里；
4. 当前最重要的 Gate 是什么；
5. 哪些真实证据支持当前进度；
6. 当前有哪些 Blocker；
7. 下一步 Codex 应执行什么；
8. 哪些技术与产品决策等待 Review 或批准。

控制台本身持续迭代，因此独立建立 Git 仓库并保留完整历史。

---

## 2. Control Plane 与 Execution Plane 分离

建议两个独立仓库：

```text
egolink/                         # Execution Plane
├─ firmware/
├─ pc_simulator/
├─ model_lab/
├─ shared/
├─ docs/
└─ ...

ego-ai-control-console/          # Control Plane
├─ app/
├─ control/
├─ docs/
├─ scripts/
└─ tests/
```

### Execution Plane

Ego Link 主仓库负责：

- firmware
- 数据采集程序
- 模型训练与部署
- shared contracts
- Replay
- Evaluation
- 产品代码
- 实际测试逻辑

### Control Plane

控制台仓库负责：

- 当前研发状态
- Stage / Gate
- Workstream / Task
- Evidence
- Dataset / Model / Benchmark 索引
- Research Frontier
- Decision / ADR
- Handoff
- 三方上下文同步
- Web 展示和控制

重要约束：

> Ego Link 产品运行不得依赖 AI Control Plane。控制台不可用时不得影响设备、数据采集、模型或产品代码运行。

---

## 3. 长期核心原则

### 3.1 Single Source of Truth

控制台形成 A线当前研发事实的统一来源。关键状态尽量只有一个权威来源。

### 3.2 Git-first

权威项目状态首先保存在 Git 中的人类可读、机器可读文件：

- YAML
- JSON
- Markdown

Web 页面只负责把这些文件渲染成研发态势。

SQLite 等数据库仅作为缓存、索引或查询加速，不能成为唯一事实源。

### 3.3 Evidence-driven

不以人工填写“完成 72%”作为主要进度。

优先展示：

```text
A-R0
5 / 8 exit criteria passed
```

或者：

```text
GNSS Blackout Benchmark
3 / 4 gates passed
```

### 3.4 Stage / Gate-driven

每个研发阶段有清晰 Exit Criteria 和 Exit Gate。只有满足 Gate 后才进入下一阶段。

### 3.5 不伪造结果

禁止伪造：

- Field Session
- Benchmark
- 模型指标
- 功耗指标
- 测试结果
- 完成状态

没有数据时明确显示：

```text
Not measured
Unavailable
Pending
Not started
```

### 3.6 统一 A线术语

持续使用：

- Personal Physical Intelligence Engine
- Location Belief
- State Belief
- Safety Belief
- Active Sensing

避免术语漂移。

---

## 4. A线最高层产品主线

控制台首页持续展示：

```text
Where am I?
        ↓
What is happening?
        ↓
Is this normal / safe?
        ↓
What evidence am I missing?
        ↓
Should I do something?
```

所有 Workstream、Stage、Task、Benchmark 和 Research Frontier 都应能映射回这条产品主线。

---

## 5. 五个 Workstream

一级结构固定为：

```text
A0 — AI Data & Evaluation Platform
A1 — Multisource Localization
A2 — State Understanding
A3 — Proactive Safety
A4 — Adaptive Sensing & Edge AI
```

### A0 — AI Data & Evaluation Platform

Mission：

```text
Collect
→ Ingest
→ Validate
→ Sync
→ Segment
→ Label
→ Dataset
→ Train
→ Evaluate
→ Export
→ Replay
→ Shadow Deploy
→ Field Validate
```

当前最高优先级。

页面重点：

- Current Stage
- Current Gate
- Capabilities
- Tasks
- Evidence
- Sessions / Datasets
- Benchmarks
- Blockers
- Next Action
- Pending Decision

### A1 — Multisource Localization

核心目标：

> GNSS 不可靠或消失之后，仍持续维护具有实际意义并可解释的 Location Belief。

重点模块：

```text
GNSS Reliability
LTE Fingerprint
Cell Sequence
IMU Relative Motion
Visual Anchor
Fusion
Uncertainty
```

核心 Benchmark：

```text
30 s GNSS blackout
60 s GNSS blackout
180 s GNSS blackout
300 s GNSS blackout
```

### A2 — State Understanding

重点状态：

```text
Motion:
stationary / walking / running / stairs / vehicle / unknown

Carry:
hand / pocket / bag / worn / table / unknown

Environment:
outdoor / indoor / transition / vehicle / unknown

Device:
normal / dropped / unattended / network_poor / unknown
```

重点指标：

```text
Macro F1
per-class F1
cross-session
cross-day
cross-route
cross-carry
transition latency
OOD rejection
```

### A3 — Proactive Safety

核心链路：

```text
DETECT
  ↓
abnormal event
  ↓
risk ↑
  ↓
VERIFY
  ├─ GNSS reacquire
  ├─ LTE refresh
  ├─ IMU high-rate
  ├─ Camera snapshot
  └─ Audio later
  ↓
DECIDE
  ↓
normal / watch / verify / contact / emergency
```

重点指标：

```text
Critical Event Recall
False Alarms / Day
Detection Latency
Verification Success
Escalation Precision
```

### A4 — Adaptive Sensing & Edge AI

核心目标：

> 用多少能量换多少新增信息。

页面应展示当前传感策略和功耗：

```text
mWh / hour
GNSS active %
LTE traffic
Camera activations / day
Inference latency
RAM
Flash
CPU
```

长期形成：

> Intelligence Capability ↔ Battery Life

Pareto Curve。

---

## 6. 三个 Cross-cutting Research Frontiers

三个前沿研究方向不扩展为新的独立 Workstream，而是跨 A0-A4 融入。

### F1 — Physics-informed Self-supervised Inertial Learning

对应：

```text
A1 + A2
```

### F2 — Camera → IMU Cross-modal Knowledge Distillation

对应：

```text
A2 + A4
```

### F3 — Active Perception for Personal Safety

对应：

```text
A3 + A4
```

研究成熟度统一采用：

```text
WATCH
↓
RESEARCH
↓
EXPERIMENT
↓
CANDIDATE
↓
PRODUCTIZED
```

明确区分“正在研究”和“产品当前依赖”。

Research 不因为前沿而自动成为当前开发 Blocker。

---

## 7. Stage 主轴

Workstream 回答“在研发哪一类能力”。

Stage 回答“项目整体成熟度到了哪里”。

当前定义：

```text
A-R0 — AI Data & Evaluation Platform
A-R1 — First Multisource Intelligence
A-R2 — AI-native Physical Intelligence
```

### A-R0 — 当前阶段

核心 Exit Gate：

```text
Field Session
      ↓
standardized dataset
      ↓
one-command Replay
      ↓
rerun model / fusion
      ↓
regenerate trajectory / map
      ↓
regenerate Metrics
```

A-R0 Exit Criteria：

```text
IMU calibration
Unified timestamp
Field Session schema
Dataset validation
Label schema
Replay Engine
Evaluation Framework
Field Dataset Protocol
```

控制台显示：

```text
x / 8 criteria passed
```

而不是人工百分比。

### A-R1

目标：

> First Multisource Intelligence

主要内容：

```text
GNSS Reliability
LTE Baseline
IMU Activity
IMU Carry State
Multisource Fusion
Location Uncertainty
```

核心 Benchmark：

```text
30 / 60 / 180 / 300 s GNSS blackout
```

### A-R2

目标：

> AI-native Physical Intelligence

主要内容：

```text
Learned Inertial Odometry
Visual Anchor
Cross-modal Distillation
State Memory
Proactive Safety
Active Sensing
Audio Integration
```

---

## 8. 首页目标

用户打开控制台约 30 秒内必须能回答：

1. 最终产品目标是什么；
2. 当前 Stage 是什么；
3. 当前 Gate 是什么；
4. A0-A4 分别处于什么状态；
5. 当前 Blocker 是什么；
6. 最近 Field Test / Evidence / Metrics 是什么；
7. 下一步 Codex 应执行什么。

首页核心区域：

```text
PROJECT GOAL
CURRENT STAGE
CURRENT GATE
A0-A4 WORKSTREAM STATUS
BLOCKERS
NEXT ACTIONS
LATEST FIELD TESTS
LATEST EVIDENCE
KEY METRICS
RESEARCH FRONTIERS
```

---

## 9. Workstream 页面统一结构

所有 Workstream 页面统一采用：

```text
Mission
Current Stage
Capabilities
Current Gate
Tasks
Evidence
Datasets
Models
Benchmarks
Blockers
Next Action
Pending Decision
```

便于用户理解、Codex解析、ChatGPT Review，以及未来扩展 B/C 线。

---

## 10. Git 数据结构

建议：

```text
control/
├─ project.yaml
├─ stages/
│  ├─ A-R0.yaml
│  ├─ A-R1.yaml
│  └─ A-R2.yaml
├─ workstreams/
│  ├─ A0.yaml
│  ├─ A1.yaml
│  ├─ A2.yaml
│  ├─ A3.yaml
│  └─ A4.yaml
├─ tasks/
├─ sessions/
├─ datasets/
├─ models/
├─ benchmarks/
├─ research/
│  ├─ F1.yaml
│  ├─ F2.yaml
│  └─ F3.yaml
├─ decisions/
├─ handoffs/
└─ snapshot/
   └─ current.json
```

---

## 11. Task 数据合同示例

```yaml
id: A0-005
title: Replay Engine MVP

workstream: A0
stage: A-R0

status: active

objective:
  Replay a recorded field session through
  different model and fusion versions.

acceptance_criteria:
  - load a complete field session
  - support GNSS masking
  - rerun fusion
  - regenerate trajectory
  - output metrics
  - retain model and dataset versions

evidence:
  commits: []
  tests: []
  sessions: []
  datasets: []
  benchmarks: []
  reports: []

blockers: []

next_action:
  Implement session loader

owner:
  type: codex

updated_at: 2026-08-16
```

---

## 12. Evidence Graph

控制台不能只有 Task Board。

必须建立：

```text
Task
 ↓
Code Commit
 ↓
Test
 ↓
Dataset
 ↓
Field Session
 ↓
Metric
 ↓
Gate
```

任务不应仅因为“代码已写完”就自动 Complete。

可关联证据包括：

```text
commit
automated test
dataset
field session
benchmark
evaluation report
artifact
```

用户应能从 Gate PASS 一路追溯回实际证据。

---

## 13. 三方协作职责

### 用户

负责：

```text
Priority
Decision
Stage Gate Approval
Risk Acceptance
Product Direction
```

决策状态可使用：

```text
APPROVE
REJECT
DEFER
NEEDS REVIEW
```

### Codex

开始任务前读取：

```text
Project Snapshot
Current Stage
Current Workstream
Task
Acceptance Criteria
Relevant Decisions
Relevant Evidence
Blockers
```

完成后回填：

```text
commit
changed files
tests
result
metrics
evidence
known limitations
recommended next task
```

### ChatGPT

主要承担：

```text
Architecture Review
Research Review
Model Recommendation
Risk Analysis
Experiment Design
Result Interpretation
Decision Proposal
```

ChatGPT 主要负责高层分析与 Review，不以“代码写完”作为职责边界。

---

## 14. AI Handoff

控制台应提供：

```text
Generate ChatGPT Brief
Generate Codex Context
```

自动生成 Context Pack。

至少包含：

```text
PROJECT GOAL
CURRENT STAGE
CURRENT WORKSTREAM
CURRENT QUESTION
LATEST CHANGES
LATEST FIELD TEST
METRICS
BLOCKERS
RELEVANT ADRs
FILES / COMMITS
QUESTION FOR AI
```

ChatGPT 输出可保存到：

```text
control/handoffs/
```

例如：

```text
2026-08-16-chatgpt-A0-review.md
```

随后供 Codex 读取。

---

## 15. Machine Context API / CLI

建议提供：

```text
GET /api/context/current
GET /api/context/workstream/A0
GET /api/context/task/A0-005
```

以及 CLI：

```bash
npm run context -- A0-005
```

输出：

```text
CODEX_CONTEXT.md
```

目标是以后用户只需告诉 Codex：

> 执行 A0-005。

Codex 就能自动获得完整上下文。

---

## 16. 推荐技术栈

第一版保持简单：

```text
Next.js App Router
TypeScript
Tailwind CSS
YAML / JSON / Markdown
Git
```

第一版避免：

```text
Microservices
Message Queue
Complex Distributed Architecture
Heavy Database
Vector Database
```

SQLite 如使用，只作为 Cache / Index。

公网部署后，所有修改状态的 API 必须鉴权。

---

## 17. 第一版页面

优先：

```text
/overview
/workstreams
/stages
/tasks
/field-sessions
/benchmarks
/research
/handoff
```

后续：

```text
/decisions
/models
/datasets
/history
/settings
```

---

## 18. 控制台自身开发 Gate

控制台按以下顺序开发：

```text
WEB-001 Repository + Data Contracts
WEB-002 Overview Dashboard
WEB-003 Workstream / Stage / Task Pages
WEB-004 Git-backed Editing + History
WEB-005 Codex Context API / CLI
WEB-006 Evidence / Benchmark Integration
WEB-007 ChatGPT Handoff
WEB-008 VPS Deployment + Authentication
```

优先完成 WEB-001～WEB-003。

---

## 19. 自举原则

WEB-001～WEB-003 完成后：

> **开始使用控制台管理控制台自身的开发。**

WEB-004～WEB-008 应作为控制台内部正式 Task 纳入 Control Plane。

这是控制台从 Demo 转为真实研发系统的关键节点。

---

## 20. Git History 与 ADR

所有重要状态变更都应通过 Git diff / commit / history 可追溯，包括：

- Stage 改变
- Gate PASS
- Task 状态变化
- Blocker 增减
- Decision
- Research maturity
- Benchmark 更新
- Model promotion

重要设计进入：

```text
control/decisions/
```

建议初始 ADR：

```text
ADR-0001-git-first-control-plane.md
ADR-0002-control-execution-separation.md
ADR-0003-evidence-driven-progress.md
```

避免关键架构只存在聊天记录。

---

## 21. 2026-08-16 当前真实状态基线

### A0

```text
ACTIVE
```

当前最高优先级。

### A1

```text
Early development / data acquisition available
```

GNSS、LTE 已具备真实采集能力。

### A2

```text
Early development
```

IMU 已接入，但校准是可信数据集工作的前置条件。

### A3

```text
Architecture defined
Validation not started
```

### A4

```text
Architecture defined
Power baseline not established
```

当前 Stage：

```text
A-R0 — AI Data & Evaluation Platform
```

当前核心 Gate：

> 任意一次真实 Field Session 能够通过一条标准命令完成 Replay，并重新生成轨迹、地图和 Metrics。

---

## 22. 未来扩展

控制台当前首先服务 Ego Link A线。

架构需预留未来扩展到 B、C 两条并行研发线的能力，但第一版禁止为了尚未发生的扩展进行过度设计。

原则：

> 先把 A线做成真实可用的研发控制平面，再通过 Namespace / Schema 扩展 B、C 线。

---

## 23. 最终原则

控制台不是为了“看起来项目很完整”。

它的核心价值是：

> **让每一次开发、测试、模型实验和架构判断留下可追溯证据，使用户、Codex 和 ChatGPT 始终基于同一批当前事实协作。**

一句话定义：

> **Ego Link AI Control Plane 是 A线研发的 Git-first、Evidence-driven、Stage/Gate-driven 控制平面，用于把产品目标、研发状态、真实证据、技术决策和 AI 协作统一到一个可持续迭代的事实中枢。**

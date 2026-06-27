# Ego Link 版本化迭代开发模式

## 1. 产品锚点

Ego Link 第一阶段按“AI主动守护定位器”推进，而不是儿童手表或复杂智能硬件。

近期 v0.1 目标聚焦：

- 设备联网；
- MQTT 上传；
- 网页看板显示；
- SOS / 唤醒 / 定位等事件闭环；
- 后续由 AI 生成主动提醒和解释文案。

## 2. 分支模式选择

当前采用 **GitHub Flow**。

原因：

- 项目处于 P0 / v0.1 快速验证阶段，单人或小团队开发，不需要 Git Flow 的 `develop`、`release/*`、`hotfix/*` 多层分支；
- 当前没有生产、预发、测试多环境部署链路，GitLab Flow 的环境分支价值暂时不高；
- GitHub Flow 更适合“一次一个小任务”：从 `main` 拉短分支，实现、验证、合并，必要时打 tag。

## 3. 版本规则

- `main`：始终保持可构建、可运行、文档状态可信；
- `task/T###-short-name`：单任务开发分支；
- `v0.x.y`：可演示或可回滚节点 tag；
- 每个任务完成前必须更新 `docs/STATUS.md`；
- 每个任务只修改 `docs/tasks/CURRENT_TASK.md` 允许的路径。

建议版本线：

- `v0.1.x`：通信定位 Demo，先跑通 Wi-Fi/MQTT/看板；
- `v0.2.x`：SOS 闭环 Demo；
- `v0.3.x`：AI 主动提醒 Demo；
- `v0.4.x`：可佩戴工程样机；
- `v0.5.x`：小场景试用版。

## 4. 智能体开发模式

第一阶段采用单智能体受控开发：

- 一次只做 `CURRENT_TASK.md` 里的一个目标；
- 不引入 LangGraph、AutoGen、CrewAI 等额外多智能体框架；
- 不自动并行修改多个领域；
- 先稳定任务契约、验证命令、停止规则和状态记录。

进入多智能体前置条件：

- 连续多个小任务能稳定按边界完成；
- Firmware、PC Simulator、协议文档的目录边界清晰；
- 协议和验收命令基本冻结；
- 多角色协作带来的收益明显大于调度成本。

第二阶段可以串行增加 Reviewer 角色；第三阶段再考虑按 Firmware、PC Simulator、Integration Reviewer 拆分角色。

## 5. 每轮任务模板

1. 更新 `docs/tasks/CURRENT_TASK.md`；
2. 从 `main` 创建 `task/T###-short-name`；
3. 实现最小可验证改动；
4. 运行任务指定验证；
5. 更新 `docs/STATUS.md`；
6. 合并回 `main`；
7. 到可演示节点时打 `v0.x.y` tag。

# 交给 Codex 的启动指令

你负责在真实 EgoLink 工作树实施本次 runtime-convergence 决定。
创始人已授权全面评估并修改必要原则和核心文件。请完成代码交付，避免止于整理文档。

先阅读实际仓库根/模块 AGENTS、docs/CONTEXT_INDEX、当前产品定义、
FIRST_LAUNCH_EXECUTION、ADR-0011/0012/0013、BOARD_MATRIX 和活跃任务。
检查 Git HEAD、未提交改动和分支；不要覆盖并行工作。
包内五份替换候选及新增 ADR/任务均尚未在实际仓库验证。

本轮优先级：
**复用 LOC-021 A-S，交付真实设备 Location → 安全认证传输 → Guardian 的有界纵向切片；
并行推进真实双向 CALL 与嵌入式承载验证；随后接通物理 SOS 和恢复。**

使用 `migration_manifest.json` 对照实际文件；内容不同就做有依据的语义合并，不盲覆盖。
`candidate/docs/AGENTS.md` 只对应 docs/AGENTS.md，绝不替换根 AGENTS。
旧文件的不可变快照保留在 docs/archive/reviews/20260905_input_snapshots/。
将候选 ADR 分配仓库未使用编号，并更新链接和真正的方向文件。
不要将未运行的候选或文档编辑记为新的 last_verified 硬件证据。

马上执行 `candidate/docs/tasks/active/P0-CONVERGENCE-20260905.md`。
检查真实调用链；只补最短缺失 seam，写能执行行为的测试，构建 legacy + live profile。
T0/T1 不作为独立 S smoke/有限单源 live 实验的全局阻塞；原并发恢复承诺不能被静默取消。
真实运行应使用具体 driver/connector，不以更多 TRANSPORT_FAILED fake 作为最终实现。

重点验证：存储失败/队列满时本地状态仍有明确行为，SOS 输入反馈与“已存储/已送达”分开，
单一 modem owner，真实事件时间，严格匹配 ACK，恢复不重复触发已结束通话。
安全传输不得因进度压力降为 HTTP 或关闭证书校验。

源代码、构建、native 行为、硬件、网络、外场与产品 Gate 分层报告。
逐项解释触及本路径的 skip；不要删测试或用源文本匹配替代 native 并发行为。
主集成 Codex，可最多委派两名执行者到不重叠文件；共享状态机/协议由集成负责人管理。

真实烧录、SIM流量、录音或外部通知不由本包自动授权。
已有有效实验授权覆盖时依范围执行；否则完成全部可独立实施的代码工作，
返回一份准确、有预算/停止/恢复条件的合并实验请求，不逐命令询问，也不继续扩建离线脚手架。

最终汇报只需：用户能力变化；实际执行的验证及证据范围；当前最大阻塞；下一动作。
P0-LOC/P0-CALL/P0-SOS 原状态均 NOT_RUN，只有对应实际验收能改变。

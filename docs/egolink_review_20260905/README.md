# EgoLink 项目审查与开发收束包｜2026-09-05

阅读 [全面评估与开发决策](EgoLink_全面评估与开发决策_20260905.md)，
将 [CODEX_START_HERE.md](CODEX_START_HERE.md) 和整个包交给实际仓库中的 Codex。

## 包内内容

| 内容 | 用途 |
|---|---|
| 全面评估与开发决策 | 项目事实、架构风险、产品取舍、推进顺序和一手技术参考 |
| CODEX_START_HERE.md | 可直接作为 Codex 的实施指令 |
| candidate/docs/ 下五份核心文件 | 保留现有文件职责的收束修订候选 |
| candidate/docs/architecture/adr/ 下决策候选 | 明确哪些旧原则被局部修订，哪些安全不变量保留 |
| candidate/docs/tasks/active/ 下单一任务包 | 先交付真实位置闭环，约束分工、实现、验证和实验授权 |
| candidate/docs/archive/reviews/20260905_input_snapshots/ | 六份逐字节原始快照；历史内容完整保留 |
| migration_manifest.json | 原路径、源文件/候选 SHA-256、合并范围和未提供的权威文件 |
| package_verification.json | 仅交付包检查，不是项目测试或硬件验证 |

## 使用边界

本轮完成的是文件证据审查、核心文件修订候选和实施任务设计。
没有实际代码仓库、没有源代码审查/测试重跑，没有烧录、VPS 部署、硬件或媒体采集。
GitLab 连接尚未在本次会话建立；插件建议本身不等于获得仓库访问。
包内没有自动覆盖脚本，不会改动你当前工作区。

先在真实仓库读取根 AGENTS 和 CONTEXT_INDEX，再检查文件差异并合并。
这些候选不能盲覆盖后来更新过的文件。根 AGENTS、产品 Charter、NORTH_STAR、
FIRST_LAUNCH_EXECUTION、BOARD_MATRIX 和原 ADR 未获全文，不能声称已修订。

`.md.source` 是不可变历史输入，不受其内嵌的旧 authority/instruction 字样约束。
保留该后缀和归档说明，避免把旧主文件重新路由为当前指令。

所有产品 Gate 保持原记录 NOT_RUN。包内结果不能替代实际仓库 context_lint、
源代码/native 测试、设备实验、现场验证或产品验收。

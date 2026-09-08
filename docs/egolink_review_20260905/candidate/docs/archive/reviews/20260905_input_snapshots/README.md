---
document_status: historical_source_archive
archived_at: 2026-09-05
---
# 输入快照与适用范围

本目录保留本次审查的六份上传文件，`.md.source` 文件与上传原件逐字节相同。
它们只用于历史追溯，不作为执行指令，也不作为当前权威文件。
其中保留的 `authoritative`、`current`、`Single Source of Truth` 等原文字样均属于历史输入。
原路径和 SHA-256 见交付包根目录 `migration_manifest.json`。

| 来源 | 文件 | 仓库目标路径 / 适用范围 |
|---|---|---|
| S1 | [AGENTS.md.source](AGENTS.md.source) | 仅 `docs/AGENTS.md`；不能覆盖仓库根 AGENTS.md |
| S2 | [ACTIVE_BUILD.md.source](ACTIVE_BUILD.md.source) | `docs/current/ACTIVE_BUILD.md` |
| S3 | [ROADMAP_EGOLINK_P0.md.source](ROADMAP_EGOLINK_P0.md.source) | `docs/current/ROADMAP_EGOLINK_P0.md` |
| S4 | [STATUS.md.source](STATUS.md.source) | `docs/current/STATUS.md` |
| S5 | [TASK_TREE.md.source](TASK_TREE.md.source) | `docs/tasks/TASK_TREE.md` |
| S6 | [EGO_MASTER_CONTEXT.md.source](EGO_MASTER_CONTEXT.md.source) | 早期桌面 Ego 上下文；不替换其他项目主文件 |

这些路径根据上传文件内容推定，尚未在 Git 工作树核实。
归档没有删除任何历史测试、失败记录、镜像身份或旧路线。
旧快照里的相对链接保留原文；追踪历史引用时应按其原仓库路径解析，不能从本归档目录直接解释。

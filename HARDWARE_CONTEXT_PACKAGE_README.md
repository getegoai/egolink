# Ego Link 硬件平台上下文包 v0.3

本包用于覆盖到现有 `EGOLINK` 仓库根目录，为 Codex 提供本轮芯片选型、功耗目标、平台迁移边界和采购验证计划。

## 安装

将压缩包解压到仓库根目录。它只新增 `docs/hardware/**` 和本说明文件，不应覆盖现有固件、模型、契约或 PC Simulator 代码。

建议提交：

```powershell
git add docs/hardware HARDWARE_CONTEXT_PACKAGE_README.md
git commit -m "docs: add Ego Link hardware platform context v0.3"
```

## 使用顺序

Codex 开始硬件相关任务前，按以下顺序读取：

1. `docs/EGO_LINK_P0_CONTEXT.md`
2. `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`
3. `docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md`
4. `docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md`
5. `docs/hardware/PLATFORM_PORTABILITY_ARCHITECTURE.md`
6. `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md`
7. 当前具体任务文件

`docs/hardware/EGOLINK_硬件开发采购清单_v1.xlsx` 是采购和到货验收参考，不是固件架构的唯一事实来源。

## AGENTS.md

不要直接用本包覆盖现有 `AGENTS.md`。将 `docs/hardware/AGENTS_HARDWARE_SNIPPET.md` 中的短规则合并到仓库根目录现有 `AGENTS.md`。

# Ego Link 硬件上下文目录

本目录保存硬件平台的稳定决策、候选路线、功耗目标、平台抽象规则和采购验证信息。

## 文档优先级

1. `docs/CONTEXT_INDEX.md`：当前可执行硬件与 P0 工程边界。
2. `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`：模型语义和端基协同边界。
3. `shared/contracts/**`：机器可校验的数据和模型接口。
4. `EGOLINK_HARDWARE_PLATFORM_CONTEXT.md`：本轮硬件决策和未决事项。
5. `PLATFORM_PORTABILITY_ARCHITECTURE.md`：固件如何避免绑定某一芯片。
6. `POWER_AND_BATTERY_ENGINEERING_TARGETS.md`：续航和功耗验证方法。
7. `HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md`：开发板、模组和仪器的评估计划。
8. `EGOLINK_硬件开发采购清单_v1.xlsx`：数量、预算、到货验收参考。

## 关键纪律

- 当前 P0 仍以 ESP32-S3 + SIM7670G 开发板为实现基线。
- 产品版主控和蜂窝模组尚未冻结。
- 候选芯片不等于 Codex 可以自行迁移平台。
- 任何新平台移植都必须以独立任务、独立后端和可比较基准进行。

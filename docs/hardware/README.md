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
8. `EGOLINK_硬件开发采购清单_v1.xlsx`：旧平台的历史评估和到货验收参考，
   不是当前 buy list，不得控制新 A0 数量、预算或采购。
9. `V1_PRO_EVT_PROCUREMENT_BASELINE.md`：已被 ADR-0008 取代的 V1 Pro 历史采购清单；不得用于新增采购。

## 关键纪律

- 当前 P0 仍以 ESP32-S3 + SIM7670G 开发板为实现基线。
- 当前销售产品方向以 `docs/product/EGO_MASTER_CONTEXT.md` 和 ADR-0008 为准；
  ESP32-S3-PICO 只是 A0 工程起点，量产主控、蜂窝模组及其余 BOM 未冻结。
  当前开发板事实仍只以 `BOARD_MATRIX.md` 和 `ACTIVE_BUILD.md` 为准。
- 候选芯片不等于 Codex 可以自行迁移平台。
- 任何新平台移植都必须以独立任务、独立后端和可比较基准进行。

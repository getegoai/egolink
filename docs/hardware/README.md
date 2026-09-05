# Ego Link 硬件上下文目录

本目录保存硬件平台的稳定决策、候选路线、功耗目标、平台抽象规则和采购验证信息。

## 文档优先级

1. `docs/CONTEXT_INDEX.md`：当前可执行硬件与 P0 工程边界。
2. `docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md`：模型语义和端基协同边界。
3. `shared/contracts/**`：机器可校验的数据和模型接口。
4. `P0_PRODUCT_ARCHITECTURE.md`：HW-020 接口基线与硬件迁移边界。
5. `P0_INTEGRATED_PROTOTYPE_DESIGN.md`：当前 HW-021 条件式候选、设计包和
   阻塞项入口；不是采购或投板授权。
6. `EGOLINK_HARDWARE_PLATFORM_CONTEXT.md`：本轮硬件决策和未决事项。
7. `PLATFORM_PORTABILITY_ARCHITECTURE.md`：固件如何避免绑定某一芯片。
8. `POWER_AND_BATTERY_ENGINEERING_TARGETS.md`：续航和功耗验证方法。
9. `HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md`：开发板、模组和仪器的评估计划。
10. `EGOLINK_硬件开发采购清单_v1.xlsx`：旧平台的历史评估和到货验收参考，
   不是当前 buy list，不得控制新 A0 数量、预算或采购。
11. `V1_PRO_EVT_PROCUREMENT_BASELINE.md`：已被 ADR-0008 取代的 V1 Pro 历史采购清单；不得用于新增采购。

## 关键纪律

- 当前 ESP32-S3 + SIM7670G 开发板仍是可复用软件/实测证据基线，不是
  `P0-CALL` 或可销售产品的最终集成硬件；产品迁移按
  `HW-020 -> HW-021 -> HW-022 -> CALL-021` 执行。
- 当前销售产品方向以 `docs/product/EGO_MASTER_CONTEXT.md`、ADR-0008 和
  ADR-0011 为准；ADR-0011 控制有冲突时的首发通信与能力优先级。
  ESP32-S3-PICO 只是 A0 工程起点，量产主控、蜂窝模组及其余 BOM 未冻结。
  当前开发板事实仍只以 `BOARD_MATRIX.md` 和 `ACTIVE_BUILD.md` 为准。
- 候选芯片不等于 Codex 可以自行迁移平台。
- 任何新平台移植都必须以独立任务、独立后端和可比较基准进行。
- 首发优先级是可靠定位、托管 RTC Ego Call 与物理 SOS。原生 VoLTE 是独立
  储备路线，先进模型与摄像头是非阻塞成长项；它们仍可并行测量，但不得
  重新成为首发总暂停条件。

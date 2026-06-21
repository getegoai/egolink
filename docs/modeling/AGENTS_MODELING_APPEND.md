# 可追加到仓库 AGENTS.md 的模型协同规则

```markdown
## Safety Companion model integration

- `shared/contracts/**`、`shared/embedded/**`、`model_lab/**`、`model_artifacts/**` 由模型侧维护。
- 固件和 PC Simulator 通过 adapter 集成，不复制或静默改写模型逻辑。
- 字段、单位、枚举、版本或阈值不适配时，记录到 `docs/modeling/INTEGRATION_ISSUES.md`。
- 物理 SOS、隐私停止、拨号和不可逆动作必须保留独立确定性安全规则。
- 模拟、编译和单元测试通过不等于真实模型效果已经验证。
- 当前不引入云端 API 作为 Ego Link 核心闭环依赖。
```

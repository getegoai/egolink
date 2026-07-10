# Codex 集成任务：Safety Companion M0

> 按顺序执行。每个任务完成、验证、提交后再进入下一任务。不要一次性重构整个仓库。

## 全局约束

- 当前硬件：微雪 ESP32-S3 + SIM7670G 开发板。
- 当前仍是 Ego Link P0，PC 代替正式 Ego Base。
- 不接真实 4G、真实 GNSS、摄像头或真实唤醒模型，除非仓库原本已经有稳定实现且本任务明确要求。
- 不修改 `model_lab/**`、`model_artifacts/**`、`shared/contracts/**`、`shared/embedded/**`。
- 字段、单位、枚举和模型语义不适配时，写入 `docs/modeling/INTEGRATION_ISSUES.md`。
- 不把模拟、编译或单元测试成功描述为真实安全识别效果已验证。
- 不引入云端 API 作为核心依赖。

---

## M0-INT-001：安装与验证模型包

### 目标

确认覆盖包在当前仓库中可独立运行，并记录现有 PC Simulator 与固件架构。

### 执行

1. 阅读：
   - `MODEL_PACKAGE_README.md`
   - `docs/modeling/MODEL_HANDOFF.md`
   - `shared/contracts/README.md`
2. 运行：

```powershell
python scripts\verify_safety_companion_m0.py
```

3. 检查当前 `pc_simulator/**` 和 `firmware/**` 的真实结构、入口和测试方式。
4. 创建 `docs/modeling/INTEGRATION_REPORT.md`，复制模板并填写仓库基线。

### 允许修改

```text
docs/modeling/INTEGRATION_REPORT.md
docs/modeling/INTEGRATION_ISSUES.md
```

### 完成条件

- 模型包自检通过；
- 集成报告记录当前 commit、入口、构建方式和硬件验证状态；
- 未修改模型侧目录。

---

## M0-INT-002：PC Simulator 模型适配器

### 目标

让 PC Simulator 能接受 `sensor_frame` 或 `model_input`，调用规则基线并返回标准 `model_output`；非 `none` 结果可转换为 `safety_event`。

### 必须实现

1. 在 `pc_simulator/**` 中建立适配器，提供等价接口：

```python
evaluate_sensor_frame(sensor_frame: dict) -> dict
evaluate_model_input(model_input: dict) -> dict
```

2. 适配器必须调用：

```python
from model_lab.safety_companion import RuleRouter, build_model_input
```

3. 不复制一份规则到 PC Simulator。
4. 按现有 PC Simulator 架构提供一个可测试入口：
   - 若已有 HTTP 服务，增加 `POST /api/safety/evaluate`；
   - 若没有 HTTP 服务，增加本地 CLI；
   - 可以同时提供，但不得为此重写整个模拟器。
5. 输入验证失败返回明确错误，不得静默补全非法数据。
6. 新增测试，至少覆盖：
   - 正常步行；
   - 手动 SOS；
   - 撞击后静止；
   - 隐私模式不请求音频和图像。

### 允许修改

```text
pc_simulator/**
quality_tests/pc_simulator/**
docs/modeling/INTEGRATION_REPORT.md
docs/modeling/INTEGRATION_ISSUES.md
```

### 验证

除现有 PC Simulator 测试外，必须再次运行：

```powershell
python scripts\verify_safety_companion_m0.py
```

### 完成条件

- PC Simulator 能处理包内 `scenario_suite.json`；
- 结果与规则基线一致；
- 模型输出和安全事件满足契约；
- 测试不会启动无法自动退出的常驻服务。

---

## M0-INT-003：固件模型接口与 Mock 适配

### 目标

在固件中建立稳定的模型调用边界，当前不要求部署真实神经网络。

### 必须实现

1. 按现有 ESP-IDF 组件风格新增 `safety_model` 组件或等价模块。
2. 使用或包装：

```text
shared/embedded/safety_model_contract.h
```

3. 对业务层暴露等价接口：

```c
bool safety_model_init(void);
bool safety_model_evaluate(
    const ego_sc_model_input_t *input,
    ego_sc_model_output_t *output
);
const char *safety_model_version(void);
```

4. 当前实现为 `mock`：
   - 物理/模拟 SOS 必须输出 `MANUAL_SOS + URGENT_ESCALATION`；
   - 其他输入可返回 `NONE`，或实现规则基线的安全子集；
   - 必须明确标识 `mock`，不得冒充真实模型。
5. 建立现有 Mock GNSS、Mock Wake、网络、电量等状态到 `ego_sc_model_input_t` 的 adapter。
6. 在串口 CLI 中增加不冲突的测试命令，例如：

```text
safety status
safety demo normal
safety demo sos
safety demo impact
```

7. 缺少 ESP-IDF 环境时只完成可静态审查的接口与主机侧测试，并在报告中标记“未进行硬件构建/烧录”。

### 允许修改

```text
firmware/**
quality_tests/firmware/**
docs/modeling/INTEGRATION_REPORT.md
docs/modeling/INTEGRATION_ISSUES.md
```

### 完成条件

- 业务代码不直接依赖未来模型框架；
- mock 与 future real implementation 可以切换；
- SOS 路径为确定性规则；
- 构建或测试结果真实记录。

---

## M0-INT-004：模拟端到端安全事件闭环

### 目标

跑通：模拟传感器状态 → 模型输入 → 模型输出 → safety event → PC Simulator 记录/展示 → 模拟命令。

### 必须实现

1. 使用包内至少 4 个场景，不需要真实硬件：
   - normal_walk；
   - manual_sos；
   - post_impact_inactivity；
   - privacy_restricted_impact。
2. `none` 不生成安全事件；其他结果生成 `safety_event`。
3. PC Simulator 能显示或记录：风险类型、分数、优先级、建议动作、证据请求、隐私限制。
4. 对 `ask_user` 或 `urgent_escalation` 生成模拟 `base_command`，但不得真实拨号、拍照或录音。
5. 保存可重复运行的集成测试，不依赖外网。
6. 更新 `INTEGRATION_REPORT.md`，列出已验证和未验证内容。

### 允许修改

```text
pc_simulator/**
firmware/**
quality_tests/**
docs/modeling/INTEGRATION_REPORT.md
docs/modeling/INTEGRATION_ISSUES.md
```

### 完成条件

- 自动测试可重放完整闭环；
- 所有消息符合契约；
- 隐私模式下不产生原始音频/图像采集请求；
- 无真实硬件、通信和安全动作副作用。

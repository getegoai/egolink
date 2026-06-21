# Safety Companion M0 模型交付说明

## 交付版本

- Package：`Safety Companion M0 0.1.0`
- Contract：`1.0.0`
- Reference router：`safety_rule_router 0.1.0`
- 目标：先建立固件、PC Simulator、未来 Ego Base 和模型实验之间的稳定接口。

## 当前交付是什么

当前 `model_artifacts` 是**规则基线**，不是神经网络模型。它用于：

- 明确安全场景的预期行为；
- 让 Codex 先完成设备数据到模型接口、模型输出到动作接口的集成；
- 让后续 MotionNet、AudioGate 和学习型 ContextRouter 有可比较的基线；
- 在没有真实传感器数据时避免伪造模型效果。

## 所有权边界

### 模型侧维护

```text
shared/contracts/**
shared/embedded/**
model_lab/**
model_artifacts/**
quality_tests/model_contract/**
docs/modeling/SAFETY_COMPANION_ARCHITECTURE.md
docs/modeling/DATA_COLLECTION_SPEC.md
```

### Codex 集成侧主要维护

```text
firmware/**
pc_simulator/**
quality_tests/firmware/**
quality_tests/pc_simulator/**
docs/modeling/INTEGRATION_REPORT.md
```

Codex 不得为了快速通过测试自行改变字段、单位、枚举顺序、阈值语义或模型版本。

## Python 参考接口

```python
from model_lab.safety_companion import RuleRouter, build_model_input

model_input = build_model_input(sensor_frame)
model_output = RuleRouter().evaluate(model_input)
```

## 固件参考接口

```c
#include "safety_model_contract.h"

bool safety_model_evaluate(
    const ego_sc_model_input_t *input,
    ego_sc_model_output_t *output
);
```

M0 固件可先使用 mock 或规则子集；完整规则结果以 PC 参考实现为准。后续端侧微模型必须提供测试向量，验证 PC 与设备输出误差。

## 验证

```powershell
python scripts\verify_safety_companion_m0.py
```

验收必须区分：

- 代码编译通过；
- 契约测试通过；
- PC 模拟闭环通过；
- ESP32-S3 实机运行通过；
- 模型效果经过真实数据验证。

前四项不能替代第五项。

# CURRENT_TASK: T022 Safety Companion M0 契约基线

## 任务目标

把 `模型架构.md` 的“版本化模型包 + 明确接口契约”思路整合进 Ego Link，并落成 Safety Companion M0 的文档、共享契约和契约测试。

## 可行性判断

该思路可行，但应从 M0 契约基线开始，而不是直接引入神经网络、训练代码或端侧推理框架。

当前 P0 已有 MQTT、Dashboard、SOS / wake / location / sensor 事件闭环，正适合先建立稳定的 `shared/contracts/`，再用 adapter 把现有事件转换为统一 `model_input`。这样模型侧可以独立演进，Codex 侧只负责固件、PC Simulator、采集、通信和运行时适配。

## 范围

- 新增 Safety Companion M0 架构文档。
- 新增模型交付 handoff、集成任务和问题记录文档。
- 新增 `shared/contracts/` 下的五个 JSON Schema：
  - `sensor_frame.schema.json`
  - `safety_event.schema.json`
  - `model_input.schema.json`
  - `model_output.schema.json`
  - `base_command.schema.json`
- 新增模型契约测试。
- 扩展仓库结构测试，保护 `docs/modeling`、`shared/contracts`、`quality_tests/model_contract`。
- 更新项目状态和下一步任务。

## 不做

- 不引入 `model_lab/` 或 `model_artifacts/` 空目录。
- 不实现模型训练。
- 不引入 ESP-DL、ESP-SR、TFLite Micro 或其他推理运行时。
- 不改变固件运行行为。
- 不改变现有 MQTT 协议。
- 不把单元测试通过解释为模型效果验证通过。

## 允许修改路径

- `模型架构.md`
- `docs/modeling/**`
- `shared/contracts/**`
- `quality_tests/model_contract/**`
- `quality_tests/test_repository_contract.py`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.model_contract.test_contract_schemas -v
python -m unittest quality_tests.test_repository_contract -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 已确认 `模型架构.md` 的路线与当前 P0 兼容：先契约、后采集、再模型。
- 已新增 Safety Companion M0 文档：
  - `docs/modeling/SAFETY_COMPANION_ARCHITECTURE.md`
  - `docs/modeling/MODEL_HANDOFF.md`
  - `docs/modeling/INTEGRATION_TASKS.md`
  - `docs/modeling/INTEGRATION_ISSUES.md`
- 已新增 `shared/contracts/` 五个 schema，统一契约版本为 `safety-companion.contract.v0.1`。
- 已新增 `quality_tests/model_contract/test_contract_schemas.py`，保护 schema 文件存在、JSON 合法、版本一致、关键 required 字段稳定、P0 风险事件覆盖。
- 已扩展 `quality_tests/test_repository_contract.py`，把模型契约目录纳入仓库结构契约。
- `python -m unittest quality_tests.model_contract.test_contract_schemas -v` 通过，5 个测试成功。
- `python -m unittest quality_tests.test_repository_contract -v` 通过，3 个测试成功。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，48 个测试全部成功。

## 完成标准

- [x] 模型协作路线被记录为可执行的 M0 契约基线。
- [x] 模型包与 Codex 集成边界明确。
- [x] 共享 JSON 契约存在且有测试保护。
- [x] 当前 P0 验证命令全部通过。
- [x] 下一步任务可以围绕 PC Simulator adapter 继续推进。

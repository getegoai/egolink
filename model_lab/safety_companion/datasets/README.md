# Safety Companion datasets

M0 只包含合成测试数据，不包含真实人员数据。

- `samples/scenario_suite.json`：12 个带预期结果的路由场景。
- `samples/model_inputs.jsonl`：可直接送入 RuleRouter 的输入。
- `samples/sensor_frames.jsonl`：传感器帧和特征适配示例。

真实采集必须遵守 `docs/modeling/DATA_COLLECTION_SPEC.md`，并保持原始数据、结构化特征、标注和用户授权可追溯。

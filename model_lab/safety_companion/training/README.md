# Training workspace

## Tiny Safety Model v0

`train_tiny_safety_model.py` creates the first local device-model shaped
artifact for D4-D5 integration. It uses deterministic synthetic templates only
and writes:

- `tiny_safety_model.json`
- `tiny_safety_model_card.md`
- `tiny_safety_eval.jsonl`

The output is a tiny linearized centroid classifier over bounded
`model_input` features. It predicts `normal`, `uncertain`, `needs_check`, or
`possible_risk`, but it does not replace Safety Kernel rules for SOS, cancel,
privacy, power, escalation, or firmware update behavior. It does not train on
private field samples, does not deploy to firmware, and makes no real-world
accuracy, latency, memory, flash, power, or release-readiness claim.

M0 没有神经网络训练。`build_feature_dataset.py` 将版本化 sensor-frame JSONL 转换为 model-input JSONL，作为未来 ContextRouter 数据集的基础。

后续模型实验必须单独记录：

- 数据集 manifest 和 split；
- 特征版本；
- Teacher 与 Student 结构；
- 量化方式；
- 精度、误报、漏报、延迟、RAM、Flash 和能耗；
- 与 M0 规则基线的消融比较。

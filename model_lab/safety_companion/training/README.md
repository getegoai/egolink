# Training workspace

M0 没有神经网络训练。`build_feature_dataset.py` 将版本化 sensor-frame JSONL 转换为 model-input JSONL，作为未来 ContextRouter 数据集的基础。

后续模型实验必须单独记录：

- 数据集 manifest 和 split；
- 特征版本；
- Teacher 与 Student 结构；
- 量化方式；
- 精度、误报、漏报、延迟、RAM、Flash 和能耗；
- 与 M0 规则基线的消融比较。

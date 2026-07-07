# Export

## Tiny Safety Model v0

`export_tiny_safety_model.py` converts a generated
`tiny_safety_model.json` artifact into firmware-friendly C constants and
synthetic test vectors:

- `tiny_safety_model.h`
- `tiny_safety_test_vectors.json`
- `tiny_safety_model_export.json`
- `tiny_safety_model_export.md`

This export is a handoff artifact for a future firmware task. It does not
modify firmware, flash a device, measure latency/RAM/flash/power, or claim
real-world model performance.

`generate_c_header.py` 将规则配置导出为 C 宏，便于固件 mock 或规则子集保持阈值一致。

未来神经模型交付还需要：

- INT8 模型文件；
- 输入归一化参数；
- 运行时版本；
- 测试向量与期望输出；
- 模型卡和哈希；
- 目标板延迟、内存和功耗报告。

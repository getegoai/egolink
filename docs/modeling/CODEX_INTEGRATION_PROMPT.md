# 可直接交给 Codex 的提示词

```text
你正在 EGOLINK 仓库中集成 Safety Companion M0。

先读取：
1. MODEL_PACKAGE_README.md
2. docs/modeling/SAFETY_COMPANION_ARCHITECTURE.md
3. docs/modeling/MODEL_HANDOFF.md
4. docs/modeling/INTEGRATION_TASKS.md
5. shared/contracts/README.md
6. 当前 firmware、pc_simulator、quality_tests 的真实结构

本轮只执行 M0-INT-001。完成、验证并报告后停止，不自动进入下一任务。

全局规则：
- 当前硬件是微雪 ESP32-S3 + SIM7670G。
- 当前只做 Ego Link P0，电脑模拟未来 Ego Base。
- 不接真实4G、真实GNSS、摄像头或真实唤醒模型。
- 不修改 model_lab/**、model_artifacts/**、shared/contracts/**、shared/embedded/**。
- 不改变字段名、类型、单位、枚举和阈值语义。
- 发现接口问题写入 docs/modeling/INTEGRATION_ISSUES.md。
- 不引入云端API作为核心依赖。
- 不执行无限等待的服务、串口监视或日志命令。
- 不把编译、模拟或单元测试成功表述成真实模型效果已经验证。
- 必须按 INTEGRATION_TASKS.md 的允许路径和完成条件执行。
- 最终列出修改文件、验证命令、结果、未验证项和下一任务建议，然后停止。
```

完成 M0-INT-001 后，在新一轮对话中把“本轮只执行 M0-INT-001”改为 M0-INT-002；随后依次执行 M0-INT-003 和 M0-INT-004。

# Ego Link Safety Companion M0 v0.1.0

这是一个可直接覆盖到现有 `EGOLINK` 仓库根目录的增量包，用于建立“随身安全陪伴”模型子系统的第一条稳定基线。

M0 **不交付未经真实数据验证的神经网络**。本包交付：

- 版本化 JSON 数据契约；
- ESP32-S3 侧紧凑 C 接口；
- 可执行的确定性安全规则基线；
- 传感器帧到模型输入的特征适配器；
- 合成安全场景、回放工具和评价程序；
- 数据采集与标注规范；
- 模型交付边界；
- Codex 集成任务书和固定提示词；
- 无第三方 Python 依赖的契约测试。

## 安装

1. 备份或确认当前 Git 工作区干净。
2. 将压缩包内容解压到 `EGOLINK` 仓库根目录。
3. 在仓库根目录执行：

```powershell
python scripts\verify_safety_companion_m0.py
```

4. 验证通过后提交：

```powershell
git add docs shared model_lab model_artifacts quality_tests scripts MODEL_PACKAGE_README.md docs/safety/CHANGELOG.md
git commit -m "model: add safety companion M0 contract and rule baseline"
```

5. 将 `docs/modeling/CODEX_INTEGRATION_PROMPT.md` 的内容交给 Codex。

## 快速演示

```powershell
python -m model_lab.safety_companion.src.cli demo
```

预期：12 个场景全部显示 `PASS`。

## 重要边界

- `shared/contracts/**`、`shared/embedded/**`、`model_lab/**`、`model_artifacts/**` 由模型侧维护。
- Codex 主要修改 `firmware/**`、`pc_simulator/**` 和对应集成测试。
- 接口不适配时记录到 `docs/modeling/INTEGRATION_ISSUES.md`，不要静默修改字段、单位、枚举或阈值语义。
- M0 规则基线用于建立行为契约，不代表真实跌倒、呼救或事故识别效果已经验证。
- SOS、隐私开关和紧急动作必须始终保留确定性安全规则。

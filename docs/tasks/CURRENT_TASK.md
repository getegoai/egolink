# CURRENT_TASK: HCTX-001 Hardware Context Sensor Matrix

## 任务目标

读取并遵守 `docs/hardware/CODEX_HARDWARE_PROMPT.md`，基于当前仓库、现有文档和真实可确认的开发板能力，更新 `docs/modeling/HARDWARE_SENSOR_MATRIX.md`。本轮只执行 HCTX-001，不执行 HARCH-001 或后续硬件迁移任务。

## 范围

- 读取硬件上下文包 v0.3：
  - `docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md`
  - `docs/hardware/PLATFORM_PORTABILITY_ARCHITECTURE.md`
  - `docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md`
  - `docs/hardware/CODEX_HARDWARE_INTEGRATION_TASKS.md`
  - `docs/hardware/HARDWARE_EVALUATION_AND_PROCUREMENT_PLAN.md`
- 修正硬件上下文包中 P0 上下文文档路径：仓库实际路径是 `docs/EGO_LINK_P0_CONTEXT.md`。
- 轻量验证 `docs/hardware/EGOLINK_硬件开发采购清单_v1.xlsx` 结构可读；该表只作为采购/验收参考。
- 更新 `docs/modeling/HARDWARE_SENSOR_MATRIX.md`，记录 IMU、麦克风、摄像头、GNSS、4G、Wi-Fi/BLE、按键、存储、电池/电量计和电源控制的当前事实、接口、驱动状态、数据能力、功耗控制能力和真实/Mock 边界。
- 列出阻塞 M1 数据采集的缺失硬件或驱动。
- 列出 HARCH-001 后续应重点审计的耦合点，但不创建 HARCH-001 审计报告。
- 更新硬件矩阵测试和项目状态文档。

## 不做

- 不执行 HARCH-001、HARCH-002、HPWR-001、HDATA-001 或 HPORT-001。
- 不自行迁移到 STM32U5A5、Apollo4、ESP32-P4 或 Alif B1。
- 不把候选芯片、采购清单或未到货物料写成最终 BOM。
- 不修改 `shared/contracts/**`、`model_lab/**` 或 `model_artifacts/**`。
- 不新增固件驱动、不刷机、不访问串口、不运行新的硬件探测。
- 不真实拨号、长时间录音录像或访问外网。
- 不宣称未实测的续航、模型性能或模组能力。
- 不修改根目录 `AGENTS.md`；硬件 snippet 仅保留在 `docs/hardware/AGENTS_HARDWARE_SNIPPET.md`。

## 允许修改路径

- `HARDWARE_CONTEXT_PACKAGE_README.md`
- `PACKAGE_MANIFEST.json`
- `docs/hardware/**`
- `docs/modeling/HARDWARE_SENSOR_MATRIX.md`
- `quality_tests/test_hardware_sensor_matrix.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_hardware_sensor_matrix -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## 执行结果

- 已读取 `docs/hardware/CODEX_HARDWARE_PROMPT.md` 并按 HCTX-001 执行。
- 已验证硬件包 manifest 中 10 个文件的 bytes / SHA-256。
- 已验证采购清单 Excel 是有效 `.xlsx`，sheet 包含：概览、采购总表、已有物料、平台对比、到货验收。
- 已修正硬件包引用的 P0 文档路径为 `docs/EGO_LINK_P0_CONTEXT.md`，并同步更新 `PACKAGE_MANIFEST.json`。
- 已更新 `docs/modeling/HARDWARE_SENSOR_MATRIX.md`，补齐料号/接口/驱动/数据能力/功耗控制/真实或 Mock 边界。
- 已列出 M1 数据采集阻塞项和 HARCH-001 后续审计重点。
- 验证通过：`python -m unittest quality_tests.test_hardware_sensor_matrix -v`，5 个测试成功。
- 验证通过：`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`，108 个测试成功。

## 完成标准

- [x] 读取并遵守硬件提示词。
- [x] 更新硬件传感器矩阵。
- [x] 明确 IMU、麦克风、物理 SOS、SD、电量/电源和 ESP32 侧 SIM7670G 控制仍未验证。
- [x] 明确候选平台和采购清单不是最终 BOM 或到货事实。
- [x] 列出 HARCH-001 审计重点但不执行 HARCH-001。
- [x] HCTX-001 focused 测试通过。
- [x] 全量验证通过。

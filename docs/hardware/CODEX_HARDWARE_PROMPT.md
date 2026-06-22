# 给 Codex 的硬件上下文提示词

```text
请读取并遵守：
1. docs/EGO_LINK_P0_CONTEXT.md
2. docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
3. docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md
4. docs/hardware/EGOLINK_HARDWARE_PLATFORM_CONTEXT.md
5. docs/hardware/PLATFORM_PORTABILITY_ARCHITECTURE.md
6. docs/hardware/POWER_AND_BATTERY_ENGINEERING_TARGETS.md
7. docs/hardware/CODEX_HARDWARE_INTEGRATION_TASKS.md
8. shared/contracts/**

当前仍以微雪 ESP32-S3-SIM7670G-4G开发板为实现基线。
STM32U5A5、Apollo4、ESP32-P4和Alif B1都只是评估候选，未冻结量产主控；SIM7670G也不是最终量产蜂窝模组。

不要自行迁移平台，不要根据采购清单假设硬件已经到货，不要把候选芯片写成最终BOM。

本轮只执行 HCTX-001：检查当前仓库、现有文档和真实可确认的开发板能力，创建或更新 docs/modeling/HARDWARE_SENSOR_MATRIX.md。逐项记录IMU、麦克风、摄像头、GNSS、4G、Wi-Fi/BLE、按键、存储、电池/电量计和电源控制的料号、接口、驱动状态、数据能力、功耗控制能力，以及当前是真实实现还是Mock。

完成后：
- 列出阻塞M1数据采集的缺失硬件或驱动；
- 列出HARCH-001应重点审计的耦合点；
- 不执行HARCH-001及后续任务；
- 不修改shared/contracts、model_lab、model_artifacts；
- 不真实拨号或长时间录音录像；
- 不宣称未实测的续航、模型性能或模组能力。
```

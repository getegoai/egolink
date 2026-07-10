# Codex 硬件开发任务顺序

## 当前结论

本轮文档加入后，不立即把固件迁移到 STM32U5 或 Apollo4。Codex继续围绕当前ESP32-S3完成P0、Safety Companion M0集成和M1数据基础，同时把阻碍迁移的耦合逐步隔离。

## HCTX-001：建立真实硬件能力矩阵

创建或更新：

```text
docs/modeling/HARDWARE_SENSOR_MATRIX.md
```

记录当前微雪ESP32-S3-SIM7670G开发板、已购传感器和测试设备：真实料号、接口、引脚、驱动状态、采样能力、功耗控制、时间戳来源、当前是真实还是Mock。

不得根据候选采购清单假设设备已经到货。

## HARCH-001：审计平台耦合

输出：

```text
docs/hardware/PLATFORM_COUPLING_AUDIT.md
```

列出：

- 业务层直接调用ESP-IDF或SIM7670G API的位置；
- 模型、传感器、存储、时间、网络和电源接口的耦合；
- 建议的最小抽象边界；
- 不能一次性重构的风险。

本任务只审计，不大规模改代码。

## HARCH-002：抽象当前最关键接口

仅对当前任务要求的接口做渐进重构，优先顺序：

1. `inference_backend`；
2. `platform_time`；
3. `platform_power`；
4. `platform_imu`；
5. `platform_audio`；
6. `platform_modem/gnss`；
7. `platform_camera`。

每次只抽象一个接口，保持ESP32-S3现有功能和测试通过。不要创建无法验证的大量空后端。

## HPWR-001：加入功耗测量标记

实现统一的功耗状态事件、累计时长、串口日志和可选GPIO标记。输出场景报告模板，方便PPK2或后续仪器对齐。

## HDATA-001：继续M1数据基础

按 `docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md` 完成session记录、IMU环形缓冲、导出、校验和回放。芯片选型不能替代真实数据采集。

## HPORT-001：新平台最小PoC（开发板到货后）

每个平台仅移植：

- 启动、日志、时钟；
- 一个IMU输入或参考测试向量；
- MotionNet / AudioGate参考模型；
- ContextRouter契约；
- 功耗测量标记。

不要第一步移植4G、Dashboard、全部存储和完整业务。先形成同指标对比，再决定是否继续。

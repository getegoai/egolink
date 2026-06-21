# CURRENT_TASK: T031 M1-001 Hardware Sensor Matrix

## 任务目标

进入 Safety Companion M1 数据基础阶段的第一步：创建 `docs/modeling/HARDWARE_SENSOR_MATRIX.md`，只基于当前仓库、固件、报告和已验证硬件事实，记录 Ego Link P0 开发板的真实传感器/外设能力、Mock 边界、采样/时间戳状态和 M1 阻塞项。

## 范围

- 读取 `SAFETY_COMPANION_MODEL_CONTEXT.md`、`NEXT_STEP_M1_DATA_FOUNDATION.md`、`DATA_COLLECTION_SPEC.md` 和现有 P0 验证资料。
- 建立硬件与传感器矩阵，覆盖主控、4G/GNSS、Wi-Fi/MQTT、摄像头、IMU、麦克风、按键、存储、电源、时间戳和 PC 侧采集链路。
- 区分 `verified`、`semi_verified`、`mock_only`、`not_verified`、`missing_or_unknown`。
- 明确 M1-002 所需最小接口和阻塞项。
- 增加轻量文档测试，防止后续误把 M0 规则基线描述成真实模型能力。
- 更新状态文档和集成报告。

## 不做

- 不训练 MotionNet、AudioGate、VisionGate 或学习型 ContextRouter。
- 不修改 `shared/contracts/**`、`model_lab/**` 或模型阈值。
- 不新增固件驱动、不刷机、不访问串口、不运行新的硬件探测。
- 不真实拨号、拍照、录音或访问外网。
- 不声称 M0 规则模拟已经验证真实跌倒、呼救或事故识别能力。

## 允许修改路径

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

- 已新增 `docs/modeling/HARDWARE_SENSOR_MATRIX.md`，记录 Waveshare ESP32-S3-SIM7670G-4G 开发板、ESP32-S3、SIM7670G、Wi-Fi/MQTT、摄像头、SD、IMU、麦克风、物理 SOS、电源/电量等能力现状。
- 已明确状态枚举：`verified`、`semi_verified`、`pc_side_verified`、`mock_only`、`not_verified`、`missing_or_unknown`。
- 已把当前可进入 M1 recorder 的最小字段和 M1-002 阻塞项写入矩阵：真实 `sensor_sample/device_health`、Wi-Fi RSSI、heap/runtime、PC AT GNSS no-fix、mock GNSS/battery、Safety M0 规则基线等。
- 已新增 `quality_tests/test_hardware_sensor_matrix.py`，覆盖矩阵存在性、关键传感器项、未知/Mock 边界和证据路径。
- 未进行新的硬件 I/O、刷机、拍照、录音、串口探测或外网访问。
- 验证通过：`python -m unittest quality_tests.test_hardware_sensor_matrix -v`，4 个测试成功。
- 验证通过：`powershell -ExecutionPolicy Bypass -File scripts\verify.ps1`，94 个测试成功。

## 完成标准

- [x] 传感器矩阵覆盖 M1-001 要求的主要能力。
- [x] 每项能力标明当前状态、证据、时间戳/采样能力和 M1 阻塞项。
- [x] 明确哪些是真实驱动、PC 侧验证、Mock 或未验证。
- [x] 测试覆盖文档存在性、关键章节和安全表述边界。
- [x] 文档更新后通过全量验证。

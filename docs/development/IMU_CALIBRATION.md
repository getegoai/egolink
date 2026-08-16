---
document_status: engineering_baseline
last_verified: 2026-08-16
verified_by: codex
---

# A0-001 IMU 六面工程校准

本文件定义 A0-001 的静态软件合同。它不代表已完成真实六面采集，也不代表
量产 IMU 验收。只有真实 QMI8658A 六面姿态和独立静止陀螺仪窗口经过评审并
生成命名 artifact 后，A0-001 才能进入 PASS；代码、schema 或 synthetic fixture
通过时，A-R0 仍保持 `0/8`。

## 当前输入边界

工具直接消费 `scripts/export_imu_windows.py` 生成的
`egolink.imu_window.v1` JSONL。每个窗口必须是当前固定合同：

```text
100 samples
requested_interval_us = 50000
current capture rate = 20 Hz
sample encoding = uint32 offset_us + six signed int32 values
accel unit = mg
gyro unit = mdps
time basis = device_monotonic_uptime_only
```

这里的 `accel_mg` / `gyro_mdps` 是固件从 QMI8658 寄存器值换算得到的**未校准
工程单位值**，不是 ADC/register raw counts。IMU window v1 未保留原始 counts、
温度或逐样本 UTC。工具必须明确写出这些 unavailable 状态，不能推断或补造。

A0-001 不改变 IMU wire、固件采样率、量程、Message Hub 或 exporter。`50 Hz /
2-4 s` 是未来 M1 数据设计的起始假设，不是当前采集能力声明。

## 采集集合

一次校准需要同一个 device、test run、firmware 和 sensor identity 下的七个唯一
窗口：

```text
x_positive
x_negative
y_positive
y_negative
z_positive
z_negative
gyro_stationary
```

六个 face label 指 QMI8658 sensor axes，不自动等同于产品 body axes。独立
`gyro_stationary` 窗口用于估计 signed gyro bias，不得复用任一 face window。
每个窗口必须 real/non-mock、cadence-qualified、静止，并通过 sample hash、姿态
主轴/符号和固定来源检查。

真实采集属于 task packet 的后续 hardware phase：每次由 operator 摆放并确认
姿态，稳定后才允许创建一个有界命令。静态实现阶段不得 flash、创建 VPS 命令
或操作设备。

## Metadata 合同

命令需要一个 operator-reviewed metadata JSON。字段严格匹配，额外或缺失字段
均 fail closed：

```json
{
  "schema_version": "egolink.imu_calibration_metadata.v0.1",
  "calibration_run_id": "A0-001-REAL-YYYYMMDD-001",
  "calibration_time_utc": "2026-08-16T00:00:00Z",
  "calibration_time_source": "operator_provided_utc",
  "device_id": "ego-link-r1-connectivity-001",
  "board_id": "connectivity-node-001",
  "hardware_revision": "unverified",
  "hardware_profile": "waveshare-esp32-s3-sim7670g-4g+atk-nb018-v1.0",
  "mounting_profile_id": "operator-reviewed-six-face-fixture-v0.1",
  "body_axis_mapping_status": "unrecorded",
  "imu_model": "QMI8658A",
  "imu_module": "ATK-NB018 V1.0",
  "sensor_i2c_address": 106,
  "test_run_id": "A0-001-REAL-YYYYMMDD-001",
  "firmware": {
    "fw_version": "record-the-observed-runtime-version",
    "firmware_commit": "0000000000000000000000000000000000000000",
    "firmware_image_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "calibration_software_commit": "0000000000000000000000000000000000000000",
  "temperature_status": "unavailable_in_imu_window_v1",
  "source_windows": {
    "x_positive": "imuw-a0001xp-b1",
    "x_negative": "imuw-a0001xn-b1",
    "y_positive": "imuw-a0001yp-b1",
    "y_negative": "imuw-a0001yn-b1",
    "z_positive": "imuw-a0001zp-b1",
    "z_negative": "imuw-a0001zn-b1",
    "gyro_stationary": "imuw-a0001gs-b1"
  }
}
```

占位 hash 只能用于 synthetic/local format exercise，不能作为硬件证据。真实
artifact 必须记录实际 source commit、被执行 image 的 SHA-256 和 calibration
software commit；`fw_version` 本身不能替代这些值。

`calibration_time_utc` 是校准作业的 provenance，不是 sample UTC。metadata 必须用
`calibration_time_source` 声明它来自 `operator_provided_utc` 或
`host_clock_utc`；v1 sample 仍只有设备 monotonic uptime，不能据此冒充 UTC。

## 标准命令

一个或多个 `--imu-windows` 文件合计必须只包含 metadata 选择的七个窗口：

```powershell
python scripts/generate_a0_imu_calibration.py `
  --metadata reports/imu_calibration/<run-id>/calibration_metadata.json `
  --imu-windows reports/imu_calibration/<run-id>/imu_windows.jsonl `
  --output-dir reports/imu_calibration/<run-id>/derived `
  --json
```

命令输出：

```text
imu_calibration_artifact.json
imu_calibrated_windows.jsonl
imu_calibration_report.md
```

源 JSONL 只读；输出路径若与 metadata 或任一输入 JSONL 相同，工具拒绝执行。

## 估计方法

v0.1 是可解释、axis-aligned、diagonal baseline。对每个 sensor axis：

```text
bias_i             = (mean_positive_i + mean_negative_i) / 2
sensitivity_i      = (mean_positive_i - mean_negative_i) / 2
correction_gain_i  = 1000 mg / sensitivity_i
accel_cal_i        = (accel_uncal_i - bias_i) * correction_gain_i

gyro_bias_i        = mean(signed stationary gyro_i)
gyro_cal_i         = gyro_uncal_i - gyro_bias_i
```

SI 派生使用标准重力 `9.80665 m/s²` 和 degree-to-radian 换算。artifact 同时记录
bias、sensitivity、correction gain、calibrated face residual、signed gyro bias、
质量门和来源 hashes。

v0.1 不估计 cross-axis/non-orthogonality matrix、温漂、最终产品安装或量产夹具
参数。这些限制必须保留，不能因为 face residual 通过而删除。

## Raw 与 calibrated 共存

`imu_calibrated_windows.jsonl` 每行仍是一个窗口。每个 sample 包含：

```text
index
offset_us
uncalibrated.accel_mg       # 与 source 数组逐值一致
uncalibrated.gyro_mdps      # 与 source 数组逐值一致
calibrated.accel_mg
calibrated.gyro_mdps
calibrated.accel_m_s2
calibrated.gyro_rad_s
```

每行绑定 `calibration_id`、完整 `calibration_identity_sha256`、source
window/cmd/test-run、source sample SHA-256、source export SHA-256 和原始
monotonic time basis。`calibration_identity_sha256` 由 metadata（包含七个 role/window
manifest）、source hashes 和估计结果共同计算，不依赖 materialized output，因而没有
循环引用。artifact 再绑定 materialized JSONL SHA-256；稳定 ID 与 payload hash 使用
sorted compact canonical JSON 计算。同一份 metadata 和相同 input bytes 必须得到相同
ID、artifact hash 与 calibrated JSONL。

六面 `primary_axis_mg` / `off_axis_mg` residual 是同一组六面数据的拟合内诊断，只用于
fail-closed sanity check，不是独立 holdout 精度、重复性或产品标定精度证据。

所有输出固定：

```text
stage = engineering
production_ready = false
training_allowed = false
adc_counts = unavailable_in_imu_window_v1
temperature = unavailable_in_imu_window_v1
sample_utc = unavailable_pending_A0-002
```

## Fail-closed 质量门

工具拒绝以下输入：

- 缺少、额外或重复 role/window/cmd/sample hash；
- sample content 与 v1 28-byte reconstruction hash 不一致；
- device、test run、firmware、sensor、I2C address 或 units 不一致；
- mock、非 observed、training-enabled 或非 monotonic-only 来源；
- sample count、offset、capture bounds、cadence metadata 不一致；
- cadence 不满足当前 20 Hz engineering qualification；
- 静止稳定性失败；
- face dominant axis/sign 与 label 不一致；
- bias、sensitivity 或校准后 face residual 超出明示阈值；
- metadata commit/image hash、UTC 或 provenance 缺失；
- output schema 不通过。

Synthetic fixture 仅保护算法和合同，永远不能成为 A0-001 Gate evidence。

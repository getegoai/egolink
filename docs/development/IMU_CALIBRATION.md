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

每个 `window_id` 必须满足 wire 合同的推导式
`imuw-<capture_cmd_id>-b<boot_count>`，`boot_count` 必须存在且有效。

**七个姿态不可能在一次开机内采完。** 固件
`EGOLINK_WIFI_IMU_WINDOW_MAX_SUCCESSFUL_COMMANDS` 的取值范围是 `1..4`（默认 1，
且有 4 条的编译期 cache 断言），即单次开机最多 4 条成功的
`capture_imu_window`。因此 7 个窗口必然跨至少 2 次开机（默认配置下是 7 次）。
提高该上限属于固件改动，明确在 A0-001 `out_of_scope` 内。

工具据此**记录而不是拒绝**跨 boot：`capture_profile.device_boot_counts` 列出全部
boot，每个 source window ref 绑定自己的 `boot_count`，跨 boot 时 artifact 自动
追加 `calibration_spans_multiple_device_boots` limitation。集合的连贯性由
device、firmware、sensor identity 和 test_run 一致性保证——这些仍然 fail closed。
跨 boot 的代价是 monotonic uptime 基准重置，因此绝不可跨窗口比较 uptime。

真实采集属于 task packet 的后续 hardware phase：每次由 operator 摆放并确认
姿态，稳定后才允许创建一个有界命令。静态实现阶段不得 flash、创建 VPS 命令
或操作设备。

## 操作员逐面清单

采集用 `scripts/run_a0_six_face_capture.py`，**一次调用只采一个姿态**，绝不连续
自动采多个——六面校准必须在窗口之间物理翻面并重新静置。

`scripts/run_imu_capture_session.py` 不适用于本任务：它要求每个 plan 恰好 3 个
窗口、无条件新建 test run、并把证据标记成 `D5-002` 或 `FIELD-011`。它保持不变。

每个姿态重复以下三步：

1. **摆放**。把设备按该姿态放稳在水平面上，手离开，等读数稳定。
2. **空跑确认**（不接触设备，不发命令）：

```bash
python scripts/run_a0_six_face_capture.py --device-id <device> --test-run-id <run> --pose z_positive --cmd-id a0001-zp --transport-type wifi --output reports/imu_calibration/<run-id>/capture/z_positive.json
```

3. **确认无误后执行**。加 `--execute --operator-confirmed-stationary`；**只有第一个
   姿态**额外加 `--create-test-run`，其余六个必须复用同一个 test run：

```bash
python scripts/run_a0_six_face_capture.py --device-id <device> --test-run-id <run> --pose z_positive --cmd-id a0001-zp --transport-type wifi --output reports/imu_calibration/<run-id>/capture/z_positive.json --hub <hub-url> --execute --operator-confirmed-stationary
```

要点：

- 七个姿态顺序：`x_positive` `x_negative` `y_positive` `y_negative`
  `z_positive` `z_negative` `gyro_stationary`；最后一个是独立静止窗口，设备
  保持任一稳定姿态不动即可，不得复用任何 face 窗口。
- 七个姿态必须用**同一个** `--device-id` 和 `--test-run-id`。
- `--cmd-id` 每个姿态唯一、≤16 字符；`window_id` 由它和 boot count 推导。
- token 只从环境变量 `--token-env` 读取，不写进记录、不打印。
- 已存在的姿态记录不会被覆盖，重采请换新的输出路径或先归档。
- 如果发命令前无法确定这一面是哪个轴朝上（模块固定在外壳里时很常见），`--pose`
  用 `unidentified`，不要猜一个 face 名字填进去。姿态归属在 metadata 里绑定，并由
  工具用数据反向校验；记录里写一个猜错的 face 名只会污染溯源。
- 每次开机的成功命令上限取决于走哪条路径。`1..4` 那个上限只属于专用 Wi-Fi profile
  （`EGOLINK_WIFI_IMU_WINDOW_MAX_SUCCESSFUL_COMMANDS`）。2026-08-16 在 FW-007 的
  **LTE 命令循环**上实测七条命令全部落在同一次开机（boot `26946`），该上限不适用。
  跨 boot 仍是允许的，artifact 会如实记录 `device_boot_counts`。

七个姿态全部完成后，用 `scripts/export_imu_windows.py` 导出，再运行标准生成命令。

## 重复性对比

单轮校准在构造上必然自洽，这说明不了第二轮会得到什么。`repeatability_not_yet_established`
因此是单轮 artifact 最大的空白。补它需要**第二轮独立六面采集**（新的 test run、新的
七个窗口，device 和 mounting 必须相同），然后：

```powershell
python scripts/compare_a0_imu_calibrations.py `
  --baseline <第一轮>/derived/imu_calibration_artifact.json `
  --repeat   <第二轮>/derived/imu_calibration_artifact.json `
  --output-dir reports/imu_calibration/<repeat-run-id>/derived `
  --json
```

工具逐轴给出 accel bias、sensitivity 和 gyro bias 的差值，并 fail closed 于：同一份
artifact 自比、两轮共用源窗口、device/sensor/mounting 不一致——重新装配过 IMU 的两轮
不构成重复性对比，因为它们测的不是同一个安装关系。

输出固定 `repeatability_characterized=false`：**两轮只给出一个差值，不是分布**，
表征至少需要三轮。其中的阈值是 proposed engineering observation bounds，用来让明显
发散的第二轮暴露出来，**不是已验证的规格**，落在界内也不构成精度结论。

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
    "firmware_commit": "<40-or-64-hex-of-the-flashed-source-commit>",
    "firmware_image_sha256": "<64-hex-of-the-executed-image>"
  },
  "calibration_software_commit": "<40-or-64-hex-of-this-repo-commit>",
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

真实 artifact 必须记录实际 source commit、被执行 image 的 SHA-256 和 calibration
software commit；`fw_version` 本身不能替代这些值。全零 hash 是"未填写"的典型
形态，工具直接拒绝 `firmware_commit`、`firmware_image_sha256` 和
`calibration_software_commit` 的全零值——否则照抄模板未改就会生成一个看起来
已绑定固件、实际什么都没绑定的 artifact。

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

七个姿态全部是静止采集，因此六个 face window 的 gyro 均值是同一个 zero-rate
offset 的独立观测。工具要求 `gyro_stationary` 估计出的 bias 与全部七个窗口的
gyro 均值逐轴一致（`max_cross_window_gyro_delta_mdps`），并把每个窗口的
`window_mean_mdps` 写进 artifact。单窗口静止阈值本身很宽，一个缓慢匀速转动的
窗口可以单独通过它，但会在这一步暴露——这是防止"真实转动被记成 gyro bias"的
关键闸门，而不是靠单窗口阈值。

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
fail-closed sanity check，不是独立 holdout 精度、重复性或产品标定精度证据。生成的
`imu_calibration_report.md` 现在直接打印这些 residual 和 gyro 跨窗口偏差，并在同一节
写明它们不是精度——避免读者把"residual 很小"读成"传感器很准"。

一个有用的实测边界：`off_axis` residual 闸门同时限制了整体夹具倾斜带来的系统性
scale 误差。若整套夹具相对重力一致倾斜 θ，倾斜会在 residual 中显现，θ ≳ 9° 时被
拒绝，因此能通过闸门的最坏情况 sensitivity 误差约 1.1%。这是闸门的约束力，不是
对该器件精度的测量结论。

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
- `window_id` 与自身 `capture_cmd_id`/`boot_count` 推导式不一致；
- `boot_count` 缺失或非法（跨 boot 本身不拒绝，但必须记录）；
- device、test run、firmware、sensor、I2C address 或 units 不一致；
- mock、非 observed、training-enabled 或非 monotonic-only 来源；
- sample count、offset、capture bounds、cadence metadata 不一致；
- cadence 不满足当前 20 Hz engineering qualification；
- 静止稳定性失败；
- `gyro_stationary` bias 与其余窗口 gyro 均值跨窗口不一致（有窗口在转动）；
- face dominant axis/sign 与 label 不一致；
- bias、sensitivity 或校准后 face residual 超出明示阈值；
- metadata commit/image hash、UTC 或 provenance 缺失或为全零占位；
- output schema 不通过。

Synthetic fixture 仅保护算法和合同，永远不能成为 A0-001 Gate evidence。

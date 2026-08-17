---
document_status: authoritative
last_verified: 2026-08-17
verified_by: codex
---

# A0-003 Field Session Schema

## 目的与边界

A0-003 为一次外出或台架采集建立可长期保存、可校验、可供后续 Replay
使用的标准 Session 包。它服务于 A-R0 的数据生产基础，并支撑 D2
定位基线与 D5 数据飞轮。

本能力是现有采集链路之上的 **additive 离线封装层**：不修改 firmware、
设备 wire protocol 或 VPS Message Hub。已有 `test_run_id`、`field_run_id`
和旧 Session 标识只作为 provenance 保存，不能冒充标准 `session_id`。

当前标准由以下实现共同约束：

- [Field Session manifest schema](../../shared/contracts/field_session_manifest.schema.json)
- [人工事件 schema](../../shared/contracts/field_manual_event.schema.json)
- [外场 IMU 校准窗口 schema](../../shared/contracts/imu_field_calibrated_window.schema.json)
- [Field Session 离线工具](../../pc_simulator/field_session.py)
- [A0-002 Unified Timestamp](UNIFIED_TIMESTAMP.md)

## 标准 Session 身份与范围

初始化器默认生成：

```text
FS-YYYYMMDDTHHMMSSZ-<12 lowercase hex>
```

`session_id` 一经写入，同一包内的 manifest、人工事件、A0-002 observation
与 clock mapping 必须使用同一个值。调用方也可显式提供合规 ID，但必须负责
其全局唯一性；工具不会把不同采集运行静默合并。

一个 `device_run` 只表示一个设备、一次 boot 和其声明的 monotonic clock
domain。重启或时钟域变化必须新建 `device_run`，不能让单个 stream 跨 boot。

A-R0 标准采集 profile 要求明确声明五类来源：

```text
GNSS + LTE + IMU + Camera + manual_event
```

每类来源都必须显式标为 `captured`、`declared_unavailable` 或
`not_requested`；缺失是可记录的事实，不能通过省略字段隐藏。只有真实包中
四类传感器与至少一个人工事件都被捕获，才可能达到结构性的
`field_eligible=true`。

人工事件是 weak label，不是事实真值。v0.1 支持：

```text
START_WALKING
ENTER_BUILDING
EXIT_BUILDING
PUT_IN_BAG
TAKE_FROM_BAG
ENTER_VEHICLE
LANDMARK
STOP
OTHER
```

每个事件保存事件时间、接收/入库时间、采集方式、操作者、可选 note，以及
可用时的 device run、boot、monotonic clock domain、A0-002 mapping 和
uncertainty。`OTHER` 必须带 note；缺失 monotonic/UTC 时必须保留原因码。

## Manifest 契约

`egolink.field_session.v0.1` 统一保存：

- Session 类型、生命周期、采集时间区间与 seal；
- 主设备、每次 device run、board/firmware/image identity；
- 软件仓库、commit、采集工具与版本；
- artifact 清单及 path、role、format、SHA-256、字节数和可验证记录数；
- calibration artifact 与 raw/calibrated stream 的绑定；
- protocol、route、repeat、人工声明的 carry/motion/environment；
- GNSS/LTE/IMU/Camera/Audio 的采集策略；
- 开始/结束电量及来源状态；
- consent、privacy review、retention 与 raw media 权限；
- split 占位、旧系统 provenance、stream 精确范围与限制；
- A0-002 observation、mapping 和 validation report 的 artifact ID。

场景声明仅描述采集计划，不自动成为 ground truth。v0.1 的可计数 stream
使用 JSONL；未知或当前不支持的格式不能仅凭 manifest 中的计数获得通过。
IMU calibrated stream 必须绑定 pre-calibration stream、calibration artifact
与 generator provenance，同时保留 raw 数据。

## Artifact 完整性与 Package Closure

Session 包采用显式清单，artifact path 必须是 session root 下规范化的相对
POSIX 路径。绝对路径、盘符、URI、反斜杠、`.` / `..`、symlink、junction
或其他逃逸方式一律拒绝。

验证器逐项复算：

- 文件存在性、regular-file 类型、size 和 SHA-256；
- JSON / JSONL 的严格可解析性，拒绝非有限数值；
- JSONL 的物理记录数；
- 分片编号完整性；
- stream、calibration、policy、privacy 与 time-lineage 引用闭包；
- session root 内除 manifest 与已声明 artifact 外不存在额外文件。

`lifecycle_state=complete` 不等于已封存。只有 complete manifest 才能生成
seal；seal 同时绑定排序后的 artifact descriptor 集合哈希，以及将
`manifest_core_sha256` 置空后所得 canonical JSON 核心哈希。验证报告不能写入
已封存的 session root，否则会破坏 package closure。`seal` 命令先将封存副本
写到包外，再由受控流程替换原 manifest。

## A0-002 Exact-input 绑定

A0-003 不信任包内已有的 A0-002 报告结论。验证器从 manifest 指定的
`record_artifact_ids` 与 `mapping_artifact_ids` 重新读取 **完全相同的输入**，
使用包内报告的 `generated_at` 复算 [A0-002](UNIFIED_TIMESTAMP.md)，再与包内
validation report 做结构化精确比较。

此外，A0-002 observation 的 source evidence 和 mapping anchor evidence
必须以 path + SHA-256 解析到同一个 Session 的封存 artifact 清单；对应
`field_session_id`、device run、boot 与 clock domain 也必须一致。只有重算
结果完全相同且所有绑定成立，才报告
`a0_002_report_binding_verified=true`。receive/ingest time 仍不能代替缺失的
source 或 device time。

## 数据集与 Gate 语义

原始 Session 不能自行授权训练，也不能自行决定 train/validation/test split：

```text
privacy.training_allowed = false
training_status = not_evaluated
training_eligible = false
split.name = unassigned | excluded
split.leakage_review_status = pending | failed
```

训练适用性、dataset-level split 与 leakage review 属于 A0-004 及后续数据集
治理。A0-003 只负责单包 schema、身份、完整性、精确范围、A0-002 绑定、隐私
一致性和结构性 field eligibility。

即使 `valid=true` 且 `field_eligible=true`，报告仍固定：

```text
field_eligibility_scope = structural_review_only
gate_status = unverified
```

静态 schema、工具或 synthetic fixture 不能让 A0-003 或 A-R0 PASS。仍需一个
经审阅的真实四源 + manual event Session，并附 firmware/software/calibration、
隐私与 A0-002 时间证据。当前 Camera 结构化采集和该真实闭环证据均不可用。

## 标准命令

创建 fail-closed 计划 manifest：

```powershell
python scripts/validate_field_session.py init `
  --output <session-root>/manifest.json `
  --device-id <device-id> `
  --operator-ref <operator-ref> `
  --protocol-id <protocol-id> `
  --test-scenario <scenario> `
  --route-id <route-id>
```

验证显式 Session 包；report 应位于包外：

```powershell
python scripts/validate_field_session.py validate `
  --manifest <session-root>/manifest.json `
  --session-root <session-root> `
  --report <outside-session-root>/validation-report.json
```

需要让结构性资格影响进程退出码时，增加 `--fail-if-ineligible`。

封存 complete manifest；输出先写到包外：

```powershell
python scripts/validate_field_session.py seal `
  --manifest <session-root>/manifest.json `
  --session-root <session-root> `
  --output <outside-session-root>/sealed-manifest.json `
  --sealed-by <reviewer>
```

退出码：`0` 表示输入可解析且自洽，`1` 表示确定性的 schema/语义/资格失败，
`2` 表示输入不可判定、不可读取或参数错误。

## 当前限制

- 当前实现是 additive static foundation；尚无现有 producer 直接输出该包。
- 当前真实 GNSS/LTE/IMU/Camera 还没有在一个标准 Session 中完成闭环。
- Camera 尚缺结构化 exposure/capture timing 与 Session ingestion。
- A0-002 仍缺真实四源共同 anchor、最大同步误差与冻结阈值证据。
- Dataset quality、采样异常、drop/jitter、标签 schema、Replay 和 evaluation
  分别属于 A0-004 及后续 Gate，不由 A0-003 静态校验器宣称完成。

# Field Session Camera + Event Sidecar

这个静态页面是首个真实 Field Session 的手机侧辅助采集器。它只做两件事：

- 记录 `START_WALKING`、`PUT_IN_BAG`、`ENTER_BUILDING`、
  `EXIT_BUILDING`、`STOP` 人工 weak events；
- 在相同 browser clock domain 下记录少量 JPEG 的本地索引和文件内容。

它不调用网络、不修改开发板、不改变 Message Hub wire，也不新增
`shared/contracts/` schema。导出物只是 A0-003 packer 的 adapter input；它本身
不是标准 Field Session、A0-002 时间报告或任何 Gate PASS 证据。

## 使用

1. 在主采集流程创建标准 `FS-...` Session ID，并把同一个 ID 填入页面。
2. 用手机打开 `index.html`。页面可直接作为静态文件使用；若浏览器禁止本地
   script，可在可信局域网环境用任意静态文件服务器提供本目录，但不要暴露到
   公网。
3. 填写 operator ref 与手机侧 device ID。未勾选图像许可也能开始并记录事件，
   但本 run 的 `raw_image_allowed=false`，拍照按钮会禁用。
4. 按真实发生时刻点击事件；需要 Camera evidence 时只拍少量 JPEG。
5. 点击 `STOP` 后下载 JSON bundle，记录页面显示的 SHA-256，并把文件交给
   packer。页面从不上传内容。

页面把草稿保存在浏览器 `localStorage`。如果文档 reload/restore，旧 run 会被
显式标记 `blocked_clock_discontinuity`，不能继续追加；应先导出已有 partial
bundle，再清除草稿并创建新的 sidecar run。页面的 hidden/visible 变化也会写入
clock log；如果 UTC 与 monotonic 的残差或 time origin 发生越界变化，同样阻断。

## Packer 的 exact input envelope

导出文件为 UTF-8 JSON，末尾一个换行。对象键按字典序 canonicalize，records
按 `sequence_id`、media 按 `path`、clock samples 按 `sample_index` 排序；同一
草稿重复导出应逐字节一致。顶层字段固定如下：

```json
{
  "format_version": "egolink.field_sidecar_bundle.v0.1",
  "bundle_role": "a0_003_adapter_input",
  "gate_status": "unverified",
  "status": "capturing | stopped | blocked_clock_discontinuity",
  "session": {
    "session_id": "FS-YYYYMMDDTHHMMSSZ-<12 lowercase hex>",
    "operator_ref": "...",
    "capture_start_utc": "...Z",
    "capture_end_utc": "...Z | null"
  },
  "producer": {
    "source": "test_phone",
    "device_id": "...",
    "device_run_id": "<session_id>:sidecar:0",
    "clock_domain_id": "browser-performance-<time-origin-us>",
    "clock_kind": "browser_performance"
  },
  "clock": {
    "alignment_status": "estimated_unverified",
    "time_origin_utc_ms": 0,
    "time_origin_utc": "...Z",
    "first_sample_id": "clock-000000",
    "last_sample_id": "clock-000004",
    "samples": [],
    "visibility_events": [],
    "discontinuity": null
  },
  "privacy": {
    "local_only": true,
    "network_upload": false,
    "raw_image_allowed": false,
    "raw_image_capture_acknowledged": false,
    "acknowledged_at_utc": null,
    "training_allowed": false,
    "consent_acknowledgement": {
      "acknowledged": false,
      "operator_ref": "...",
      "acknowledged_at_utc": null,
      "scope": "local_engineering_private_jpeg",
      "statements": [
        "small_bounded_jpeg_capture",
        "local_private_storage_only",
        "must_not_commit_to_git",
        "training_not_allowed"
      ]
    },
    "retention_acknowledgement": {
      "acknowledged": false,
      "operator_ref": "...",
      "acknowledged_at_utc": null,
      "status": "not_applicable_no_raw_media | post_experiment_review_required"
    },
    "control_plane_approval": false,
    "gate_approval": false
  },
  "records": [],
  "media": [],
  "limits": {},
  "limitations": []
}
```

每个 `clock.samples[]` 的 exact shape 是：

```json
{
  "sample_id": "clock-000000",
  "sample_index": 0,
  "sample_type": "start | manual_event | camera_capture_return | visibility_* | resume_check",
  "timestamp_monotonic_ns": 0,
  "timestamp_utc": "...Z",
  "pairing_span_ns": 0,
  "time_origin_utc_ms": 0,
  "visibility_state": "visible | hidden",
  "alignment_status": "estimated_unverified"
}
```

`timestamp_monotonic_ns` 来自本 document epoch 的 `performance.now()`；
`timestamp_utc` 来自紧邻采样的 `Date.now()`；`pairing_span_ns` 是两次
`performance.now()` 包围 UTC 读取的时间跨度。它们不是 verified mapping。

人工事件 record 的 exact shape 是：

```json
{
  "record_type": "manual_event",
  "event_id": "<session_id>:event:<six-digit-sequence>",
  "sequence_id": 0,
  "source": "manual_event",
  "capture_method": "test_phone",
  "event_type": "START_WALKING | PUT_IN_BAG | ENTER_BUILDING | EXIT_BUILDING | STOP",
  "timestamp_monotonic_ns": 0,
  "timestamp_utc": "...Z",
  "clock_domain_id": "browser-performance-...",
  "clock_sample_id": "clock-...",
  "alignment_status": "estimated_unverified",
  "timestamp_uncertainty_ns": 1000000,
  "operator_ref": "...",
  "note": null,
  "label_semantics": "weak_operator_event"
}
```

Camera record 是独立 observation，独占一个全局 `sequence_id`，不会与相邻人工
事件共用时间或序号：

```json
{
  "record_type": "camera",
  "observation_id": "<session_id>:camera:<six-digit-sequence>",
  "sequence_id": 1,
  "source": "camera",
  "capture_method": "test_phone",
  "timestamp_monotonic_ns": 0,
  "timestamp_utc": "...Z",
  "clock_domain_id": "browser-performance-...",
  "clock_sample_id": "clock-...",
  "alignment_status": "estimated_unverified",
  "timestamp_uncertainty_ns": 1000000,
  "timestamp_semantics": "capture_return",
  "media_path": "camera/000001.jpg",
  "media_sha256": "<lowercase sha256>",
  "media_size_bytes": 123,
  "reason_codes": ["browser_file_input_has_no_exposure_timestamp"]
}
```

对应 `media[]` exact shape：

```json
{
  "path": "camera/000001.jpg",
  "media_type": "image/jpeg",
  "sha256": "<lowercase sha256>",
  "size_bytes": 123,
  "data_base64": "..."
}
```

Packer 必须逐项解码 Base64、复算 size 与 SHA-256，并验证 Camera record 与 media
一一对应。然后将 JPEG 作为 A0-003 `raw_media` artifact、Camera 索引作为独立
stream data 保存；sidecar 原始 bundle 也应作为 immutable source evidence
保留。packer 还必须按 acknowledgement 原文生成不可变 consent/retention
policy artifacts 并单独走既有 privacy review；这里的本地确认不得自动转换为
Control Plane、A0-003 或 Gate 审批。不能把 `capture_return` 改写成 exposure time，不能把 browser UTC 当作
开发板 source UTC，也不能把 `estimated_unverified` 提升为 `verified`。如果
packer 不能建立符合既有 A0-002 合同的诚实时钟映射，应保留原始双时钟并把相应
最终 alignment/Gate 状态保持 unavailable/unverified，而不是用 server receive
time 回填。

## 明确限制

- Camera 时间是文件选择器返回页面的时间，不是硬件 exposure 时间；
  `timestamp_uncertainty_ns` 只覆盖本机双时钟读取跨度与 1 ms 最小分辨率，不覆盖
  exposure-to-return 延迟，也不代表跨设备同步误差。
- 输入 JPEG 最大 12 MiB；规范化后单张最大 512 KiB、最多 6 张、总计最大
  2 MiB；完整 bundle 最大 4 MiB UTF-8。任何超限都拒绝，不静默截断。
- 浏览器可能把计时器精度降低到毫秒级；页面只保存实际可见的整数 ns 表示和
  pairing span，不宣称真实纳秒精度。
- canvas 规范化会移除大部分原 JPEG metadata；bundle 保存的是规范化后的 JPEG
  和它的实际 hash。
- localStorage 不是长期证据库。完成后必须下载 bundle、核对 hash，并进入受控
  Field Session package。
- 即使 bundle 结构正确，A0-002、A0-003 与 A-R0 仍保持 `unverified`，直到真实
  四源 Session 经审阅。

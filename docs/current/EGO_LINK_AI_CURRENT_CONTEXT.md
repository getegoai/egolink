---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-09-21
verified_by: codex
owner: founder
decision_adr: ../architecture/adr/ADR-0010-asynchronous-observation-timeline-and-store-forward.md
productization_adr: ../architecture/adr/ADR-0012-p0-productization-sprint-1.md
current_milestone_adr: ../architecture/adr/ADR-0015-single-4g-board-camera-field-milestone.md
current_product_adr: ../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md
---

# Ego Link A 线当前阶段与状态估计执行基线

## 当前目标、分工与验收

[ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
承接创始人 9/19 的随身主动状态估计、强隐私/本地优先、同步 Ego Base 与蜂窝
原生主通话方向。高可靠定位是直接用户入口；原生通话与实体 SOS 仍属最终三 Gate。
`P0-LOC`、`P0-CALL`、`P0-SOS` 保持 `NOT_RUN`。

- Gemini：ADR-0015 单 4G 板 Location/GNSS/Cell/IMU/power/Camera 的持久恢复、真实 Wi-Fi/LTE 受控切换、独立供电短携带与 D2/FIELD-020。
- Codex：ALIGN-STATE-010 已完成决策/镜像/任务管理与规则状态真实性修复；源码 `3a0728058`，离线验收通过，未烧录/部署。采样/模组/Camera/传输行为不是该修复范围。
- BASE-010：同步研发最小用户私有 Session 终点、保存/回放/报告与生命周期；完整 Base 模型栈不成为新的首发硬门。
- CALL-030/031：原生可行性与代表性通话；CALL-020/021 RTC 备路和本轮完整 SOS 保持暂停，不是 A 线数据依赖。

已有确定性规则状态必须诚实处理缺失、过期、未来、mock、部分/无效和乱序输入，
不能产生高置信正常/安全结论。这是当前工程验收，不代表活动、跌倒、佩戴准确率
已验证。advanced learned L2/L3、Camera AI、复杂多模态和模型接管 Sensor Policy
保持非阻塞，遵循 data quality -> event-time replay -> offline comparison -> Shadow Mode。

当前 WIP/依赖只看 [FIRST_LAUNCH_EXECUTION](FIRST_LAUNCH_EXECUTION.md) 与任务包；
实际运行镜像/失败见 [ACTIVE_BUILD](ACTIVE_BUILD.md)、[STATUS](STATUS.md) 和
[BOARD_MATRIX](../hardware/BOARD_MATRIX.md)。本文件保留原始 last_verified 日期，
不把新文字、source 或测试当作新实机证据。

## 1. 异步观测与运行状态

不同源独立采集，不要求 GNSS/IMU/LTE/Camera 在同一时刻硬同步：

| 来源 | 采集边界 |
|---|---|
| IMU | 明确功耗策略下的 FIFO/chunk/window 或有界工程连续采样；不逐点网络请求 |
| GNSS | 独立更新/功耗策略；尝试、fix/no_fix 与质量分开 |
| LTE/Cell | 硬件实际可提供的网络/小区证据；定时或事件触发 |
| Camera | 默认关闭；命名授权的手动/设备定时有界 JPEG，非决策源 |
| Audio | 原生通话按独立任务；高级声音采集/分析另行授权 |

设备职责：Sense -> Timestamp -> minimum operational Location/Sensor Policy
and honest rule-state -> Persist -> bounded delivery。断网仍维护 last-trusted、
belief/uncertainty、GNSS/LTE/mobility/battery/policy 和 action lineage。

Base 目标职责：私有 ingest -> event-time align -> replay -> derived report /
comparison；复杂融合/训练后续分片。当前 VPS 数据库/导出是授权有界工程过渡，
不冒充私有物理终点。后验 replay/derived inference 不覆盖设备当时决策。

## 2. 失败、未知与时间

区分 not_attempted、success、no_fix、timeout、error；契约具体枚举以
[shared/contracts](../../shared/contracts/) 为准。GNSS no_fix 不等于模块坏，fix
也不等于高精度或高可靠。无数据不能补造坐标、标签或 baseline。

Observation 保留 record/device/boot/source/sequence、capture monotonic/UTC、
timestamp source/quality、status 与 payload；存在传感器自身时间则保留。
使用 boot-scoped monotonic + 可用 UTC anchor。receive/ingest time 是传输证据，
不能替代 capture/event time。无法比较的时钟明确 uncertainty，不虚构全局顺序。

当前状态须有缺失、过期、未来、无效和 mock 的显式行为；晚到数据保留真实年龄，
不能覆盖更新的有效状态或跨 boot 复活。来源有效、测量质量、规则置信和产品位置
不确定性是不同维度。没有新鲜可信来源时可展示历史 last-known，但不能伪装当前实测。

## 3. Store-and-Forward 与私有终点

Sensor Observation -> bounded local persistent queue -> available secure route
-> declared durable ACK -> settle。稳定 ID/seq/exact bytes、容量上限、关键事件
保留量、重复/丢失/损坏和重启恢复必须可验证。ACK 前不删唯一待交付副本。
采集/local state 可在出站存储失败时继续且显示降级；ADR-0014 的反馈/持久化
分离并不授予虚假 durability。物理掉电/寿命结论需要实测。

产品目标为设备 -> 有界中继 -> 用户 Base 私有历史。每个云临时缓冲声明目的、
数据/访问者、容量、时限、目的地、ACK 与删除验证；中继收到、Base 收到、人工
确认不同。现有 VPS consent/保留策略继续，不因本次对齐自动删库/迁移。迁移前
需独立范围、备份、身份/数量/重试一致性和恢复方案。

工程版本具体 persistence/route 支持以运行证据为准；旧 FW-007 易失 outbox
结论不能覆盖新候选，旧 Camera/HTTP smoke 也不能替代当前同镜像 recovery。

## 4. IMU、字段包装与规则估计

高频原始样本使用 chunk_id、boot_id、start time、sample period/count 和 samples。
若采集支持，按 chunk_start + index * sample_period 恢复样本时间；不得用理想
cadence 填补未采样的窗间 gap。calibration/mounting/source/mock 关系必须保留。
已有窗口可用于 mobility 证据，不能因此声明 IMU position baseline。

当前实现包含 ego_state_engine、PC reference estimator、DEVICE ego_state、
collection store/API 与 Web 消费。紧凑 DEVICE 输入不自动等于 canonical
`ego_state_estimation_v0`；使用明确版本化、可验证的投影/适配。无效枚举、字段或
identity/time 不能静默补成正常状态。当前 schema 与实际状态见任务及机器合同。

实验性的 mobility/posture/wear 输出保留来源、窗口、reason、unknown 与质量。
规则 confidence 不是经过校准的准确概率；SHA-256 仅覆盖指定完整性范围，不是
加密或完整证据链安全保证；local_priority 是策略字段，不证明数据实际位于用户家中。

本轮回归要覆盖 missing/stale/future/partial/mock、重复/乱序/boot/replay、
invalid payload 与真实 Web 渲染。状态报告必须显示局限，不能把模型结果直接
升级为健康/人身安全事实或自动触发未经授权的动作。

## 5. Camera 与自然采集

Camera 在 ADR-0015 是单板 milestone 必需交付，仍不是第四 P0 Gate，也不能
生成、改善或否决 Location/SOS。手动与默认关闭的本地定时路径共用有界采集。
保留 trigger/config/command/photo 身份、source time/quality、format/geometry/
bytes/integrity 与 capture/save/upload/preview 独立结果。离线配额保留普通观测
空间；重启补传同一文件，错过的定时不 catch-up recapture。

Naturalistic Session 目标仍是佩戴 -> 启动 -> 正常活动 -> 结束/回收，减少测试中
人工操作。手机 Sidecar 是可选辅助，不能成为 Session 或采集成功的单点依赖。
neck_forward 等安装状态按合同与真实记录处理。视觉 anchor/teacher/active
perception 只是后续研究；Camera 故障不否决有效定位，但可能使本次联合采集验收不完整。

## 6. 蜂窝位置与实验基线

保留硬件可提供的 MCC/MNC/TAC/Cell ID/PCI/RSRP/RSRQ/RSSI/SINR/neighbor 观测，
缺失字段明示 unavailable。不为首个位置实验先建完整基站数据库。Cell coarse-
location mapping 可在有高质量 GNSS/地面真值时研究；没有真实映射时 LTE location
baseline=unavailable。Cell 序列/fingerprint/learned model 是后续路线。

D2/FIELD 使用同一候选与完整 Session 身份，保留 failed attempts、参考点方法、
fix rate、TTFF、median/P90 error、时延/连续性、no-fix/backoff、路由和功耗。
没有外部真值的段不能算位置误差；姿态与 no-fix 相关不能直接宣称 RF 遮挡因果。
已有 FIELD-003/D2/D5/pack/replay 工具复用，不重复建采集或训练平台。

## 7. 历史 A-R0/FT/EXP 资产

A-R0 与 ADR-0009 的编号/估计器谱系继续作为数据/评估资产，不改变任何 P0 Gate。
FT-001 的 exact-100 IMU probe、FT-001B 的异步 GNSS+IMU Session 和 EXP-A1-000
的中间 60 秒 GNSS mask/last-known baseline 有各自旧范围；它们不是当前
LOC/FIELD 的全局串行许可门。是否完成以对应 packet/命名证据为准。

旧 FT-001B 可接受离散 IMU 窗、可选 Camera/LTE，不等于 ADR-0015 的 Camera-
inclusive 当前 milestone。IMU 无可信坐标方法时 position baseline=unavailable；
LTE 无映射时 coarse baseline=unavailable。不得为图表临时造坐标算法或 synthetic
trajectory 冒充实场。L2-001 原持续采集要求与当前 collector 证据须逐项匹配，
不能因一项新日志批量关闭旧 acceptance。

## 8. 3D IMU 可视化边界

现有 imu3d.js 的世界坐标、平面校准、陀螺偏置与静止抑制是可视化/工程观察
能力。tare 零点、无磁力计 yaw 漂移抑制与渲染平稳不证明绝对航向、正式 IMU
标定或所有姿态无奇点。几何/轴向与测量精度要分开；实际硬件结论保持证据范围。
9/21 的详细实现报告见[源快照](../archive/decisions/20260922/README.md)，不把其中
“严格 1:1”“彻底消除”措辞当成未经测试的产品保证。

## 9. 不扩张边界

当前修复服务已有消费者。不得借 state truth 重建 Control Plane、发明复杂
全局 schema/event framework、要求多源硬同步、改采样/硬件 pin、建设完整 LTE
地图、训练 Transformer/Factor Graph/RL policy 或升级 Camera AI。

真实数据暴露的问题优先于猜想。高级模型在质量、回放、离线/Shadow 比较后才讨论
晋级。原 Qwen/Codex 与 RTC-first 调度是历史；当前以 9/22 Codex/Gemini 分工、
任务 allowed_paths、共享路径 owner 和验收为准。

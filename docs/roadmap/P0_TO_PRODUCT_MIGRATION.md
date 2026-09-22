---
document_status: authoritative
decision_updated: 2026-09-22
last_verified: 2026-08-23
verified_by: codex
---

# Ego Link 从 P0 到产品形态迁移路线

本路线服从 [ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md)
与 [Master Context](../product/EGO_MASTER_CONTEXT.md)：随身主动状态估计、可靠
定位入口、强隐私/本地优先、蜂窝原生主通话与同步最小 Ego Base。路线更新不
新增实机证据；三个 P0 Gate 保持 `NOT_RUN`。

## 当前工程到产品的迁移

| 工作线 | 当前消费者和产出 | 下一证据边界 |
|---|---|---|
| 单 4G 板采集，Gemini | 保留 Camera/IMU/GNSS/Cell/power 与异步 source time；补断网/重启同文件与 ID 恢复、真实 Wi-Fi/LTE 切换 | 独立供电短携带 -> D2 参考点指标 -> FIELD-020 代表场景 |
| 状态真实性与项目管理，Codex | ALIGN-STATE-010 已离线完成；源码 `3a0728058`，合同与回归通过 | 未烧录/部署；下一候选绑定新镜像后，由 Gemini 验证外场行为 |
| 原生蜂窝通话 | CALL-030 精确模组/固件/运营商/音频可行性 -> HW-021 条件设计 -> HW-022 集成样机 | CALL-031 拨入/拨出与真实双向音频 -> P0-CALL |
| 用户私有终点 | BASE-010 授权/合成 Session 接收、私有保存、回放/报告、保留/导出/删除 | 最小可审查私有闭环；不等待完整模型栈，不宣称完成 Base 产品 |
| 产品 A0 与合规 | HW-021 精确器件/电源/RF/声学/结构输入；COMPLIANCE-010 条件询问 | 具名证据、独立复核 -> HW-022 -> A1/产品保证 |

CALL-020/021 保留为暂停的 RTC 备路资产，不自动重新派发或改名。完整 SOS 在
当前单板 milestone 仍暂停；其最终义务保留，后续消费 CALL-031 原生主路。
外场、硬件、供应商或审批等待仅阻塞对应依赖，不重新形成全项目串行波次。

```text
单板恢复/真实路由/短携带 -> D2/FIELD-020 -> P0-LOC
CALL-030 + HW-021 -> HW-022 -> CALL-031 -> P0-CALL
LOC-021 + OUTBOX-010 + CALL-031 -> SOS-010 -> P0-SOS
HW-022 + LOC-021 + CALL-031 + SOS-010 -> PWR-020
三 P0 Gate + 功耗/可靠性/声学防水/RF/隐私安全/中国合规/NPI -> P0-RELEASE-010

并行排队：BASE-010 最小私有终点；HW/合规条件输入
已离线完成：Codex 规则状态真实性；未烧录/部署
暂停：旧 CALL-020/021 RTC；本轮完整 physical SOS
```

这些箭头是消费者关系，不表示任务全部开工。实际 WIP 与共享路径整合顺序见
[FIRST_LAUNCH_EXECUTION](../current/FIRST_LAUNCH_EXECUTION.md)。HW-021 可先做
不依赖 CALL-030 的设计输入；原生音频/承载最终设计不得缺其证据。FIELD-020
与 SOS 后续各自按依赖启动，在最终 release 汇合。

## 必须保留的工程边界

ADR-0015 的单板证据载体不变：一块已识别 SIM7670G connectivity board，必要
Camera、外接 IMU、电源与天线。AMOLED、双板转发和 PC runtime 不参与 field
验收；bench 诊断、build 与 evidence review 可用 PC。Camera 是本轮交付，不是
第四 Gate，也不产生或否决 Location/SOS 决策。

已有 manual/timed/browser/battery 证据按准确 image/config/run 范围复用；不能
把旧“待做”列表当作当前事实。普通电池台架、一次 GNSS fix、一个类别或一个
原生 AT 驱动日志分别只证明其实际范围。短携带、参考点精度、代表日、掉电恢复、
原生双向声音与 48h 产品续航各需独立证据。

规则状态工程验收修复已存在消费者的真实性，不证明跌倒、佩戴或活动模型有效。
高级 learned L2/L3、Camera AI 与完整 Base 私有模型仍非首发关键路径。
三项 P0 Gate 名称与 `NOT_RUN` 不变；P0-CALL 内容迁移为原生拨接和稳定双向音频。

## 从现有 VPS 到用户私有终点

目标：设备本地 operational state/有界队列 -> 受控临时中继 -> 用户 Ego Base
私有历史/回放/报告。云仅承担穿透、信令和有界临时缓存；每个缓存声明目的、
数据/访问者、容量/期限、目的地、ACK 与删除验证。中继收到不等于 Base 收到。
唯一未交付副本不能在约定 durable ACK 前删除。

当前 collection/photo VPS 是已授权有界工程过渡，不是本地优先或静态加密实现。
现有数据遵守原 consent/期限/访问边界。本轮不部署 Base、不迁移或删除私人
数据；后续迁移先准备可逆备份、身份/数量核对、重试和 ACK 兼容、恢复及生命周期
验证。完整私有大模型、多模态和训练后续分片，不新增第四产品 Gate。

## 产品形态路径

- A0：独立定制 EgoCore 架构板，主控/蜂窝语音与 GNSS/IMU/完整音频/存储/电源；以可测流、可替换、可审查设计关闭风险。
- A1：产品板框与防水核心舱、天线、声学、光学、SIM/USB、电池和 Cradle/EgoSkin；代表性整机复测三 Gate 和横切保证。
- 后续版本：高级本地/Base AI、个体化模型、LoRa、LE Audio、场景扩展与可选附件。
- Base：最小用户私有终点从现在同步研发，不再等到旧 P4；完整私有 AI 不是首发新增硬门。

任何准确 MCU、modem、音频接口、电池或 Camera 仍按 Master/HW-021 的候选/
unknown 与正式资料/样品证据选择，不能固定当前开发板或简单相加双板能力。

## 历史资产

旧 P0-A/P0-B 双板 USB/PC Bridge、P1/P2 端侧模型/UART、P3 PCB、P4 Base 以及
Demo v0.1-v0.5 保留工程谱系，不控制当前启动顺序。原完整阶段说明、命令与证据
边界保存在[本次精确迁移快照](../archive/decisions/20260922/README.md)；现有
模拟器/AMOLED/安全 demo 代码和成功失败记录不删除、不改为产品证据。

不跳过真实数据，不用 synthetic/mock 替代传感器/定位/声音/电池实证。协议和
机器合同版本化；source event time、严格 ACK、one modem owner、SOS 局部降级、
结束呼叫不复活和已批准的授权边界继续有效。

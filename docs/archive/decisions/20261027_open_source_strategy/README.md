---
document_status: superseded
archived_at: 2026-10-27
owner: founder
---

# 开源策略评审前快照与迁移记录

本目录保存 2026-10-27 创始人同意整体评估、授权修订项目记忆之前的原始字节。
`.md.source` 文件仅为历史输入，其中的 `authoritative`、创始人确认、最高指导、
已验证及绝对红线等声明均不再作为当前指令或能力证据。不要把本目录加入默认上下文。
本目录包含未提交的在地编辑快照，不代表这些内容已经存在于某个 Git 提交。

当前入口：[开源策略](../../../product/OPEN_SOURCE_AND_COMMERCIALIZATION_STRATEGY.md)、
[北极星](../../../product/NORTH_STAR.md)、[上下文路由](../../../CONTEXT_INDEX.md)。

## 原始来源与 SHA-256

原始来源以 `pywork/` 下的同级仓库布局为基准；以下哈希仅用于快照完整性核对，
不作为公开日期或专利法律效力的证明。

| 原始来源 | 精确快照 | SHA-256 |
|---|---|---|
| `egolink/docs/product/OPEN_SOURCE_AND_COMMERCIALIZATION_STRATEGY.md` | [strategy.md.source](strategy.md.source) | `734c1ddd5066c0aa55203e7eeee04e5193148f1b1d8ccef8d31843289a201717` |
| `egolink/docs/product/NORTH_STAR.md` | [north-star.md.source](north-star.md.source) | `c3cb68c77fdd911d8efe5f2ba4c500bc547a6cd181e9a294737f4d3d9b31d709` |
| `egolink/docs/CONTEXT_INDEX.md` | [context-index.md.source](context-index.md.source) | `b5820ee94c7a8a2e7b5c56453cf86caa18dc636029ffe3765a9e5b2ebe7958ff` |
| `ego/projects/egolink/README.md` | [ego-registry.md.source](ego-registry.md.source) | `38375278e262bb39614c03a3346dc9069e4a2a2f58eb6aa4a8e3b154fc502aa5` |

## 迁移映射

| 旧表述或入口 | 本轮替代内容 |
|---|---|
| 策略自称全项目最高指导，所有方案均已确认 | 当前策略入口；确认原则与流程，分别标记商业假设、许可优先方案、发明候选与工程事实 |
| 公开过程的价值主要由完整日志体现 | 精选可复现案例，保留失败、人工纠错、当时证据与未解问题 |
| 固定硬件＋通信订阅＋B2B 商业闭环 | 候选收入逐一验证；社区参与和用户付款分别评价 |
| 源码公开即证明强隐私、量产规格构成现成壁垒 | 数据路径与实际部署单独验证；规格、隔离和产品能力按日期及范围声明 |
| Apache 反诉保证、文档默认 NC | 软件 Apache-2.0／文档 CC BY 4.0 为待检查方案；说明有限专利许可及商业边界 |
| 五项高价值发明、全仓等待申请号 | 发明候选池；候选内容先处理申请覆盖，无关材料分批公开 |
| Git 时间戳不可辩驳、阻止任何专利诉讼 | 公开记录的证据用途与限制；不保证自由实施 |
| 默认重写活跃仓库历史 | 白名单导出；保留内部原仓库与真实历史，必要时在发布副本处理 |
| North Star 顶部及同日变更记录 | 同步本轮已确认原则、待验证项、非工程验收边界 |
| Context Index 默认入口、任务路由、Authority Rules | 同步策略权威范围及公开声明的证据来源 |
| Ego 总仓库的 EgoLink 登记 | 增加唯一策略入口与本地同级检出链接，不复制策略正文 |

本次只修订战略记忆与登记；STATUS、ACTIVE_BUILD、P0 Gate、硬件证据日期、固件、
协议和运行配置不因本次评审改变。快照保存不表示相关材料已通过公开审查。

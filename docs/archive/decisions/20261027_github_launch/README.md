---
document_status: historical_record
recorded_at: 2026-10-27
owner: founder
---

# EgoLabs GitHub 首发记录与状态迁移

组织：[getegoai](https://github.com/getegoai)，显示名 EgoLabs。以下记录本轮已完成的公开发布；当前进度以 [OPEN-001](../../../tasks/active/OPEN-001_MINIMUM_PUBLIC_RELEASE.md) 为准。

| 仓库 | 首发提交 |
|---|---|
| [.github](https://github.com/getegoai/.github) | [`9033b9c43da3814b35b3cba4c95a728f6d076f44`](https://github.com/getegoai/.github/commit/9033b9c43da3814b35b3cba4c95a728f6d076f44) |
| [ego](https://github.com/getegoai/ego) | [`20bd0e6e63fba95ad8116fd59d2b9857ef000afc`](https://github.com/getegoai/ego/commit/20bd0e6e63fba95ad8116fd59d2b9857ef000afc) |
| [egolink](https://github.com/getegoai/egolink) | [`73be5cc27e7e7869a2df86437b812a11eabdc794`](https://github.com/getegoai/egolink/commit/73be5cc27e7e7869a2df86437b812a11eabdc794) |

本阶段完成组织入口、产品定义/愿景/路线、贡献入口及首批开发 Issue。Data Core 与 EgoLink 产品源码尚未导入；OPEN-001 为 `in_progress`，不能将整个任务标记完成。首批原创文档采用 CC BY 4.0，产品源码及其许可在实际导入时落实。

- [ego#1：Data Core 导入](https://github.com/getegoai/ego/issues/1)
- [ego#2：Link → Base 最小闭环](https://github.com/getegoai/ego/issues/2)
- [egolink#1：真实源码导入](https://github.com/getegoai/egolink/issues/1)

[官网源码](https://github.com/getegoai/ego/tree/main/website) 已发布，提交为 [`cedb380906ac88c27ac1613485169a3a09c52aa1`](https://github.com/getegoai/ego/commit/cedb380906ac88c27ac1613485169a3a09c52aa1)。页面实现采用 Apache-2.0，项目文档采用 CC BY 4.0。静态部署包为 `C:/Users/binwe/Documents/ChatGPT/ego/public-launch/getego-site-20261027.zip`。

新版官网未部署至原 Netlify 站点。浏览器工具因无法识别当前 URL 触发访问保护并停止；本轮不再使用浏览器部署。不能据此宣称 getego.ai 已显示新版。该问题不撤销已完成的 GitHub 发布，也不阻止产品源码导入继续。

本轮未登录公开 HTTP 检查确认组织、组织主页、两个项目 README、官网源码及三个 Issue 均返回 200，内容正确。已核对工作区 `public-launch/publication-verification.json`，其中八项均为 `public: true`、`content_verified: true`。

## 修改前快照与迁移范围

以下 `.md.source` 是修改前的原始字节，可能包含未提交改动；其中旧 `queued`、组织未知和未发布说法仅用于历史追溯，不再作为当前指令或状态。哈希用于快照完整性，不证明公开日期。

| 原路径 | 精确快照 | SHA-256 | 迁移范围 |
|---|---|---|---|
| `docs/tasks/active/OPEN-001_MINIMUM_PUBLIC_RELEASE.md` | [docs__tasks__active__OPEN-001_MINIMUM_PUBLIC_RELEASE.md.source](docs__tasks__active__OPEN-001_MINIMUM_PUBLIC_RELEASE.md.source) | `850842224c9c7962481481a5ee65fc99713af5d2ce219109748186e5d4d24308` | 首阶段完成，任务仍 in_progress；记录 URL/SHA、Issue、源码未导入和官网未部署 |
| `docs/tasks/TASK_TREE.md` | [docs__tasks__TASK_TREE.md.source](docs__tasks__TASK_TREE.md.source) | `9a9d523bf3bfe20a6fbd3c9ac46e642590ce97ce417e78dcc0d049f7f49dbf83` | 仅同步公开项目区，保留其余硬件/产品任务 |
| `docs/product/NORTH_STAR.md` | [docs__product__NORTH_STAR.md.source](docs__product__NORTH_STAR.md.source) | `4181fef2063922924d0e4ecc5a943d714b0345497056a580e4925448fb8244d5` | 组织未知改为已确认 getegoai；保留策略与工程日期 |
| `docs/product/OPEN_SOURCE_AND_COMMERCIALIZATION_STRATEGY.md` | [docs__product__OPEN_SOURCE_AND_COMMERCIALIZATION_STRATEGY.md.source](docs__product__OPEN_SOURCE_AND_COMMERCIALIZATION_STRATEGY.md.source) | `5e68b376edf1c3e16da08e52eef86cf877d2cdb8fac6b4ec76ba46d66844acbe` | 确认组织 slug 和定义已发布阶段，不重写策略 |
| `docs/CONTEXT_INDEX.md` | [docs__CONTEXT_INDEX.md.source](docs__CONTEXT_INDEX.md.source) | `cba21b4e5f5c5a8af9467a1981815e40946ae60c75dcc509b60ba623a8faccf3` | 确认组织及已发布定义，指向 OPEN-001 后续源码工作 |

本轮未修改 STATUS、ACTIVE_BUILD、P0 Gate、硬件证据日期、固件或协议。未改写活跃仓库历史，未执行部署或新增 GitHub 写操作。

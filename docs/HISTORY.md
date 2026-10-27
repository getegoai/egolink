# Development history

EgoLink's public project launch began on **2026-10-27**. Development took place before that date. Original author dates are retained to describe the actual sequence; they do not claim that the commits were public at the time.

## What was imported

- The existing development branch contained **471 commits**, from 2026-06-20 through the source baseline on 2026-10-23, original head `2a84b338b4f3f7bd6b9dced7bf18df356f4f6b5e`.
- One additional commit records the 36 selected current-session documentation files. This yields a 472-commit source-side lineage before the public-branch merge and import fixes.
- The already-public definition/roadmap commit, `73be5cc27e7e7869a2df86437b812a11eabdc794`, is retained when the histories are joined. Public development continues on `main`.

The implementation is imported as a connected development history, rather than a set of curated examples. It includes the existing firmware, hardware materials, services, contracts, host tools, tests, and dated design/experiment records. Later corrections and failed experiments are part of that history.

## Privacy edits and source correspondence

Publication preparation replaces concrete credentials and private identifiers/endpoints in the retained history. These edits change affected Git object IDs and their descendants; they do not turn the work into a new invention or erase its original author dates. Public-safe placeholders are examples, not working deployment settings.

The [original-to-public commit map](history/commit-map.tsv) records the final correspondence. Use it when a dated document still refers to an original commit hash. It contains commit IDs only, not removed private values. Validation and the precise import boundary are recorded in [PUBLIC_IMPORT_VALIDATION](PUBLIC_IMPORT_VALIDATION.md).

This cleanup also applies to retained archival snapshots. A historical snapshot's original checksum refers to the private source before redaction; a public redacted copy is not a byte-for-byte substitute for that private evidence. Raw private device captures, local databases, ignored scratch files, and build outputs were not added to make historical evidence links appear complete.

## Historical version

The original `v0.1.0` tag identifies the 2026-07-10 engineering-alpha checkpoint, originally commit `9ee3151c2a420ded2328b2998a686f556e1a7c35`. The published tag resolves to the corresponding cleaned commit; the commit map provides that correspondence.

This tag preserves a real historical milestone. It is not a newly validated product release, and older versions have not all been rebuilt or rerun with today's dependencies. The current source and the latest import checks should be read separately from historical board results.

Additional navigation tags were created during the public import:

| Tag | Original development checkpoint |
|---|---|
| `history/p0-baseline-20260620` | Initial P0 workflow baseline |
| `history/ai-flywheel-20260923` | AI-050 retraining/diary implementation; not measured real-world model accuracy |
| `history/pcb1-source-20261023` | Current source baseline before import documentation and build-portability changes |

## 中文

首次公开启动日期是 2026 年 10 月 27 日；此前的真实研发日期予以保留，不声称当时已公开。导入保留原有 471 次连续提交，并加入本会话 36 份选定文档的一次提交，再与既有公开定义/路线历史衔接。

公开准备中的具体凭据与隐私替换会改变提交 hash，最终对应关系见提交映射。历史 `v0.1.0` 保留真实工程节点含义；它和旧台架记录都不等于本轮重新完成产品验收。后续在公开 `main` 继续实际研发。

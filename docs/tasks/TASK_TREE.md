---
document_status: current_task_tree
reviewed_at: 2026-09-22
decision_updated: 2026-09-22
maintained_by: codex
open_source_plan_updated: 2026-10-27
---

# EGOLINK Current Task Tree

Current direction: [ADR-0016](../architecture/adr/ADR-0016-local-first-ego-state-cellular-primary.md).
Runtime facts: [STATUS](../current/STATUS.md), [ACTIVE_BUILD](../current/ACTIVE_BUILD.md).
The active directory is inventory, not WIP. Only `execution_state: in_progress`
counts as current implementation; a checked checklist is not acceptance.

## EgoLabs 公开项目启动（2026-10-27）

[OPEN-001：EgoLabs 公开项目启动与持续协作](active/OPEN-001_MINIMUM_PUBLIC_RELEASE.md)
由 Codex 推进，`in_progress`。[getegoai](https://github.com/getegoai) 组织显示名为 EgoLabs，`.github`、`ego`、`egolink` 三个 public 仓库的首批定义/路线已发布；Data Core 与 EgoLink 产品源码尚未导入。

- 已完成组织主页、Ego/EgoLink 定义与路线首发及贡献入口；首发提交见 OPEN-001。
- 接下来执行 [ego#1 Data Core 导入](https://github.com/getegoai/ego/issues/1)、[ego#2 Link → Base 最小闭环](https://github.com/getegoai/ego/issues/2)、[egolink#1 真实源码导入](https://github.com/getegoai/egolink/issues/1)；EgoBase 按真实独立维护需要再拆仓。
- [官网源码](https://github.com/getegoai/ego/tree/main/website) 已发布，但未部署至原 Netlify 站点；浏览器因当前 URL 识别失败触发访问保护并停止，本轮不再使用浏览器部署。
- 沿现有产品结构导入真实源码与研发文档，之后以 Issue、分支、PR 和版本持续开发；社区贡献进入实际产品主线。
- 原“没有数据为何不能显示正常”教学首发方案已被取代，教程与精选案例仅作可选补充。
- 专利和商业验证并行，不阻塞公开定义和开发；原硬件/产品调度保持其原有日期与证据范围。

本轮发布结果与修改前快照见[启动记录](../archive/decisions/20261027_github_launch/README.md)；此前规划保留在[前轮迁移记录](../archive/decisions/20261027_egolabs_public_project/README.md)。

## Assigned work and dependencies

| Owner | Packet / state | Next consumer and exit |
|---|---|---|
| Codex | [ALIGN-STATE-010](done/ALIGN-STATE-010_DECISION_AND_STATE_TRUTH.md), done / source only | State repair committed as `3a0728058`; 1,860 tests passed, 7 skipped; management alignment closed. Gemini selects a later exact field image; no flash/deploy implied |
| Gemini | [P0-CONVERGENCE](active/P0-CONVERGENCE-20260905.md), in_progress | Same-candidate outage/reboot JPEG and ordinary backlog truth; actual Wi-Fi/LTE transition; short independent-power carry evidence |
| Gemini | [D2-001](active/D2-001_LOCATION_ACCURACY_BASELINE.md) + [FIELD-020](active/FIELD-020_L1_FIELD_DATASET.md), queued | Recovery/route/carry acceptance -> reference error/fix/TTFF baseline and representative-day dataset |
| Unassigned | [BASE-010](active/BASE-010_LOCAL_FIRST_MINIMUM.md), queued | User-controlled private endpoint, bounded relay and verified retention/deletion; no new Gate |
| Unassigned | [CALL-030](active/CALL-030_NATIVE_CELLULAR_FEASIBILITY.md), queued | Exact native-cellular/audio feasibility -> HW-021/022 and CALL-031 |
| Unassigned | [HW-021](active/HW-021_EXACT_INTEGRATED_PROTOTYPE_DESIGN.md), parked | Conditional A0 inputs; no fabricated product implied |
| Unassigned | [COMPLIANCE-010](active/COMPLIANCE-010_CHINA_PRECOMPLIANCE.md), queued / NOT_SENT | Named written classification/pre-compliance input; not waiting for a reply to an unsent inquiry |

Shared-file and Git rules are in [Codex/Gemini handoff](../current/CODEX_GEMINI_HANDOFF_20260922.md).
Gemini does not need to wait for unrelated management work; a firmware containing
new state repairs must bind its exact source/image and relevant regression.

## Product convergence (queued, not current WIP)

```text
CALL-030 + HW-021 -> HW-022 -> CALL-031 -> SOS-010
LOC-021 + OUTBOX-010 --------------------^
HW-022 + LOC-021 + CALL-031 + SOS-010 -> PWR-020
FIELD-020 + CALL-031 + SOS-010 + OUTBOX-010 + OPS-004
  + PWR-020 + HW-022 + COMPLIANCE-010 + product assurance -> P0-RELEASE-010
BASE-010 -> private-endpoint/relay lifecycle evidence for G8
```

LOC-021, OUTBOX-010 and OPS-004 are parked reusable source/evidence assets, not
three additional concurrent implementations. Their remaining product recovery,
security and persistence obligations are retained. CALL-020/021 remain paused
RTC research; SOS-010 stays paused until primary-call/integration inputs exist.
P0-LOC, P0-CALL and P0-SOS all remain NOT_RUN.

## Acceptance queue and retained backlog

DOC-BASE-001, FW-005/006/007, OPS-002/003 and WEB-004/005/006 have completion
claims/checklists but remain `acceptance_review`, owned by Director. Review named
evidence before moving them to done; FW-006's failed startup summary and later
samples must retain their separate meanings. No historical FAIL is overwritten.

A0-001/002/003, FT-001B, L2-001 and D5-001 retain their declared calibration,
time-lineage, dataset or evaluation gaps; they are queued assets rather than
new parallel frameworks. FIELD-004 is continuous regression, not implementation
WIP. Detailed historical task inventory, old branch references and evidence are
preserved in [the source archive](../archive/alignment/20260922/README.md).

Regenerate the derived board with `python scripts/build_progress_board.py` after
state changes. Keep current docs short; per-run details stay in named evidence.

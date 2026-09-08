# Documentation Instructions

Scope: documentation under `docs/` only. This is a revision candidate prepared
on 2026-09-05, not a replacement for the repository-root `AGENTS.md`.
It becomes operative only after repository reconciliation and merge.

## Read and route

Read repository-root instructions, then `docs/CONTEXT_INDEX.md`, the current
product charter, `docs/current/STATUS.md`, `ACTIVE_BUILD.md`, and the one active
outcome packet. Read history only to resolve a specific issue.
Do not load every generated report or historical task as default context.

## Separate decisions, reported evidence, and observed runtime

- A direction decision is not implementation evidence. A build is not a boot.
- Reported test results must retain their source date; never write a fresh
  `last_verified` date merely because prose was edited.
- Capability labels remain `verified`, `observed`, `mock`, `pc_side_verified`,
  `unknown`, or `unverified`. Add evidence method, scope, source and date.
- A genuine experiment failure is useful evidence and must remain visible.
  Never convert historical FAIL to PASS after an unrun code change.
- Bench, field and product-release results have distinct scopes. USB/PC bench
  work is allowed within an authorized experiment; PC-free product evidence
  is still required where the product commitment says so.

## Keep current documents short and single-purpose

`STATUS.md`: current outcomes, blockers, next decisions.
`ACTIVE_BUILD.md`: flashed images, deploy identities, candidate profiles.
`TASK_TREE.md`: current work in progress and near dependencies.
`ROADMAP_EGOLINK_P0.md`: stage outcomes and release conditions.
An ADR records one meaningful trade-off, not each implementation substep.
Write detailed traces, hashes and past iterations once under evidence/archive.

When replacing material, preserve exact source snapshots and a migration map.
Raw immutable snapshots may use `.md.source`; an archive wrapper must clearly
make their embedded historical authority declarations non-operative.
Do not mark archives or generated reports as current authorities.

## Changes and conflicts

The founder has authorized review and revision of principles and core files.
Do not silently overwrite a newer decision or lower a capability gate.
A change to behavior, event semantics, persistence, security or a contract must
identify the old invariant, replacement invariant, migration and regression.
The runtime-convergence ADR candidate records the proposed scoped overrides.
Unprovided files must be read before editing; summaries are not their contents.

## Documentation and testing

Use relative Markdown links. Run `python scripts/context_lint.py` in the real
repository and `git diff --check` before acceptance.
Update brittle document/source-shape assertions when a reviewed design changes;
retain behavioral and safety regression coverage. Do not manufacture green tests.
A report-only task cannot count as delivered product functionality.
Every new preparatory abstraction must name the runtime consumer that needs it.

## Operational authority

This docs file cannot authorize physical I/O, alter top-level safety rules,
change credentials, deploy services, record people, make purchases, erase NVS,
or change eFuses. Offline edits/tests proceed under the current task authority.
Real experiments use one bounded, operator-approved experiment scope with exact
devices, endpoints, capture policy, budgets, stop conditions and recovery image.
Do not request approval for every command already inside that valid scope.
When authority is missing, finish independent code work and return one precise
experiment request; do not proliferate no-I/O adapters to avoid the boundary.

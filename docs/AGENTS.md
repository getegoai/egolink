# Documentation Instructions

This file applies only to documentation work under `docs/`.

## Scope

- Use `docs/CONTEXT_INDEX.md` as the router before editing project documentation.
- Keep current authoritative context in `docs/product/`, `docs/current/`, `docs/architecture/`, `docs/hardware/BOARD_MATRIX.md`, and active task packets.
- Keep historical sources in `docs/archive/`; archive files are evidence, not current authority.
- Keep generated reports in `docs/generated/`; do not use generated reports as default context.

## Editing Rules

- Do not delete historical information. Move it to `docs/archive/` when it is replaced.
- When splitting or merging documents, preserve source paths in a migration note or generated report.
- Add `document_status: authoritative` and `last_verified: YYYY-MM-DD` only when a document is intended to be a current authority.
- Do not mark archive files as authoritative.
- If documents conflict, record the conflict instead of silently choosing a fact.
- Keep Markdown links relative and runnable through `python scripts/context_lint.py`.

## Hardware Documentation

- Hardware capability must be written as `verified`, `observed`, `mock`, `pc_side_verified`, `unknown`, or `unverified`.
- A build, flash, or serial log is not proof of 4G, GNSS, camera, audio, battery, storage, or power behavior unless the evidence directly exercises that capability.
- PC-side bridge or AT-probe evidence must not be described as firmware-side product behavior.

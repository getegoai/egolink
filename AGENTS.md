# EGOLINK Repository Instructions

## Authoritative Sources

- North star and development guiding principles (read first, every session;
  check its date to sense goal changes): `docs/product/NORTH_STAR.md`
- Context router: `docs/CONTEXT_INDEX.md`
- Product definition: `docs/product/PRODUCT_CHARTER.md`
- P0 scope and non-goals: `docs/product/P0_SCOPE.md`
- Product migration roadmap: `docs/roadmap/P0_TO_PRODUCT_MIGRATION.md`
- Current status: `docs/current/STATUS.md`
- Current build and bench setup: `docs/current/ACTIVE_BUILD.md`
- Current board capability matrix: `docs/hardware/BOARD_MATRIX.md`
- System architecture: `docs/architecture/SYSTEM_OVERVIEW.md`
- Approved architecture decisions: `docs/architecture/adr/`
- Active task packets: `docs/tasks/active/`
- Machine-readable protocol/model contracts: `shared/contracts/`

`docs/archive/`, `docs/generated/`, `reports/`, `model_artifacts/`, and runtime folders are not default context. Read them only when a task packet explicitly names them.

## Context Loading Rules

1. Start by reading `docs/CONTEXT_INDEX.md`.
2. If an active task packet is provided, read only its `context` entries before editing.
3. Before modifying a module, read that module's local `AGENTS.md`.
4. Do not recursively scan `reports/`, `model_artifacts/`, `docs/archive/`, or runtime logs unless the task explicitly requires a named file.
5. When two documents conflict, prefer the authoritative source listed above. If both claim authority, stop and record the conflict instead of deciding silently.

## Change Boundaries

- Keep tasks narrow and reversible.
- Obey task `allowed_paths` and `out_of_scope` fields when present.
- Do not change firmware logic, model behavior, pin assignments, communication protocol, hardware configuration, or public data contracts unless the active task explicitly allows it.
- Do not commit secrets, real private user data, large model weights, or private device logs.
- Do not modify `docs/generated/` by hand except for reports explicitly requested as generated artifacts.

## Hardware Safety

- Build and static tests may run automatically.
- Flashing firmware, erasing flash, changing device permissions, sending hardware control commands, or starting long serial captures requires explicit operator intent for that task.
- Hardware evidence must identify board, firmware commit or image, connection path, timestamp, and evidence file path.
- A passing build is not evidence that 4G registration, GNSS fix, calling, IMU accuracy, audio, camera, battery, or power behavior works on hardware.
- Unknown hardware capability must be written as `unknown` or `unverified`, never inferred from a board name.

## Testing And Completion Gate

Before finishing:

- Run the validation commands declared by the task when possible.
- For context-only changes, run `python scripts/context_lint.py`.
- If repository behavior might be affected, also run `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`.
- Record changed files, validation results, evidence paths, unresolved conflicts, and remaining risks.
- Update `docs/current/STATUS.md` only when the current milestone or verified state actually changes.

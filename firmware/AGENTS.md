# Firmware Module Instructions

- Read root `AGENTS.md`, `docs/CONTEXT_INDEX.md`, `docs/current/ACTIVE_BUILD.md`, and `docs/hardware/BOARD_MATRIX.md` before firmware work.
- Do not change pin definitions, board configuration, protocol fields, or hardware control behavior unless the active task explicitly allows it.
- Keep firmware changes isolated to the named firmware target and its components.
- Hardware-dependent claims require board, port or connection path, firmware image or commit, timestamp, and evidence path.
- Do not start indefinite serial monitors; use bounded captures.

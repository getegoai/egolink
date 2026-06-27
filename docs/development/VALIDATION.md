---
document_status: authoritative
last_verified: 2026-06-27
verified_by: codex
---

# Validation

This document records the current validation entry points.

## Control-Plane Validation

Use this for context routing, task packets, and documentation-control changes:

```powershell
python scripts/context_lint.py
```

## Project Validation

Use this before merging any task that may affect repository behavior:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify.ps1
```

## make validate

`make validate` is not currently a required entry point. No `Makefile` or
`makefile` with a `validate` target was present during the ENG-001 baseline.

If a future task introduces `make validate`, it should be added deliberately and
documented here as a stable wrapper around the existing validation commands.

## Hardware Validation

Build success is not hardware proof. Any hardware claim must include:

- board identity;
- firmware commit or image;
- connection path;
- timestamp;
- bounded command or capture;
- evidence file path;
- real/mock/source-boundary label.

Do not run flashing, serial control, HID control, GNSS live tests, or audio
capture unless the active task explicitly allows the hardware action.

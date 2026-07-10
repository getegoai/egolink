# Tiny Safety Model v0

- Model ID: `MODEL-DEVICE-001-tiny-safety-v0-20260707`
- Version: `0.1.0-synthetic-dry-run`
- Generated: `2026-07-07T00:00:00+00:00`
- Scope: `synthetic_integration_only`
- Training rows: `72`
- Holdout rows: `24`
- Holdout accuracy: `1.0`

## State Labels

- `normal`
- `uncertain`
- `needs_check`
- `possible_risk`

## Deployment Status

- Export format: `c_header_ready`
- Firmware integrated: `False`
- Device deployed: `False`
- Measured latency ms: `None`
- Measured power mW: `None`

## Safety Boundary

- SOS/cancel handled by Safety Kernel: `True`
- Model controls external actions: `False`
- Release claim allowed: `False`

## Non-Claims

- Synthetic integration model only; no real-world accuracy is claimed.
- The model does not replace deterministic SOS, cancel, privacy, power, or escalation rules.
- No firmware integration, device deployment, latency, RAM, flash, or power measurement is claimed.
- No private field samples or candidate DB rows are read by this artifact.

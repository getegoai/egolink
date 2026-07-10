# Tiny Safety Static Footprint

- Model ID: `MODEL-DEVICE-001-tiny-safety-v0-20260707`
- Model version: `0.1.0-synthetic-dry-run`
- Evidence level: `L2_build_verified_static_partial`
- Artifact hash: `504de9511f18478002596c9ac90fcfd6941f08238f6f1b72c7307407adcbbbed`
- Features/classes: `14 / 4`
- Parameters: `60`
- Estimated C constants: `834` bytes
- Firmware app bytes: `321248`
- Firmware binary present: `True`

## Static Operation Estimate

- Score multiplies: `56`
- Score adds: `56`
- Confidence expf calls: `4`

## Unknown Until Measured

- RAM peak bytes: `unknown`
- Latency P50/P95/max: `unknown / unknown / unknown`
- Energy per inference: `unknown`

## Known Gaps

- Runtime RAM is unknown until measured on a target build.
- Latency is unknown until measured on a target build.
- Energy per inference is unknown until measured with a power path.
- Firmware app bytes are not the model static delta.
- Tiny Safety v0 is not MotionNet-class acceptance evidence.
- PROD-001 TBD(MODEL-001) values must not be replaced from this report.

## Non-Claims

- No real-world accuracy is claimed.
- No runtime RAM, latency, or power measurement is claimed.
- No MotionNet acceptance or production MCU selection is claimed.
- No real SMS, call, dispatch, or external escalation is enabled.

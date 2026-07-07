# Evaluation

## Deterministic M0 Baseline

Run:

```powershell
python model_lab\safety_companion\evaluation\evaluate_baseline.py --output artifacts\baseline_report.json
```

The M0 scenario pass rate checks deterministic contract behavior only. It is
not a real-world safety recognition accuracy claim.

## Tiny Safety Static Footprint

Run:

```powershell
python model_lab\safety_companion\evaluation\assess_tiny_safety_static_footprint.py
```

The report binds the existing MODEL-DEVICE-001 Tiny Safety artifact/export
files to static footprint evidence. If the local MODEL-DEVICE-006 firmware
build binary is present, the report records its app bytes as static build
context. Runtime RAM, latency, power, model delta, MotionNet acceptance, and
production MCU readiness remain `unknown` until separately measured.

## Tiny Safety Synthetic Stress

Run:

```powershell
python model_lab\safety_companion\evaluation\evaluate_tiny_safety_synthetic_stress.py
```

The stress report runs the existing Tiny Safety artifact against a
deterministic synthetic boundary matrix and lists disagreements,
low-confidence cases, and labeling priorities. Synthetic agreement is useful
for model iteration triage, but it is not real-world accuracy.

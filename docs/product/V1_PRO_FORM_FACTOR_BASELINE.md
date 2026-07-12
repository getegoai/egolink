---
document_status: authoritative
last_verified: 2026-07-12
verified_by: codex
owner: founder
---

# EgoLink V1 Pro Final Form-Factor Baseline

This document freezes the user-visible V1 Pro product envelope before the
custom PCB is drawn. The first custom board is a form-factor EVT board inside
this envelope, not a loose desktop development board.

## Product Form

- Primary user: children aged roughly 6-14; secondary use may include older
  people who need a simple active-safety locator.
- Wearing mode: wrist-worn safety watch with a replaceable 20 mm silicone
  strap.
- Interaction: no touch screen, no camera, no app grid and no rotating crown.
- Visual language: calm rounded-square body, matte PC+ABS housing, dark
  mineral or coated cover lens, charcoal/white body options and one
  high-visibility safety-orange SOS control.
- Product promise expressed by the object: it is a dependable guardian and
  locator, not a small entertainment smartwatch.

## Frozen Exterior Envelope

| Item | Frozen target |
|---|---|
| Body length | 46.0 mm |
| Body width | 42.0 mm |
| Body thickness | 15.2 mm, excluding button cap protrusion |
| Corner radius | 8.0 mm |
| Body mass | <= 38 g without strap |
| Complete mass | <= 55 g with strap |
| Strap interface | 20 mm, screwed quick-service lug; antenna version is a service part |
| Water/dust target | IP67 design target; claim only after DVT test |
| Charging | Four-contact magnetic pogo: 5 V, GND, factory UART TX/RX |
| Product debug | Internal SWD pads; no exposed USB connector |

The envelope is deliberately close to existing LTE children's wearables while
leaving enough thickness for a 700-900 mAh cell and cellular/GNSS antenna
clearance. It must not grow during PCB design without a founder decision.

## Display and Controls

- Frozen display: Sharp `LS013B7DH03`, 26.60 x 30.30 x 0.745 mm module,
  23.04 x 23.04 mm active area, centered on the face.
- Cover-lens visible window: 24.0 x 24.0 mm with a 1.0 mm black mask overlap.
- Two switched white front-light LEDs are reserved for dark use; they are off
  by default and do not create an always-on display claim.
- Right upper button: `SAFE / CONFIRM`, short press.
- Right lower safety-orange button: `SOS`, recessed shoulder, deliberate
  two-second hold, local vibration and visible countdown before escalation.
- Left button: `BACK / VOICE`, short press for back, hold for local voice
  interaction.
- Buttons use internal tactile switches with molded external caps and O-ring
  or membrane seals. Button functions remain usable with gloves and without
  looking at the screen.

## Internal Stack

Front to back target stack:

| Layer | Maximum allocation |
|---|---:|
| Cover lens, adhesive and seal | 1.35 mm |
| Display and optical gap | 1.15 mm |
| Component height above PCB | 2.60 mm |
| Four-layer rigid PCB | 0.80 mm |
| Battery and compression pad | 7.20 mm |
| Rear shell, gasket and clearance | 2.10 mm |
| Total design stack | 15.20 mm |

The protected battery target is approximately `7.0 x 34 x 38 mm`, nominally
about 800 mAh, with a 10k NTC lead. The final cell part number is selected
after supplier drawings and swelling tolerance are available; the battery
bay dimensions do not change.

## PCB Mechanical Contract

| Constraint | Value |
|---|---|
| Main PCB outline | 38.0 x 34.0 mm rounded rectangle, max 2.0 mm corner radius |
| PCB thickness | 0.80 mm |
| Layer count | 4 layers, controlled 50-ohm RF traces |
| Top component height | <= 2.60 mm except the Air780EGH body at its approved zone |
| Bottom component height | <= 0.80 mm; no hard components over the battery swelling area |
| Mounting | Four M1.4 holes on a 34.0 x 30.0 mm rectangle |
| Factory interface | Tag-Connect/SWD pads plus magnetic-pogo UART path |
| Board revision marking | Silkscreen and firmware-readable resistor ID |

Placement zones:

1. Top third: Air780EGH, SIM/eSIM, cellular power switch and bulk capacitors.
2. Center: display FPC and low-profile routing only.
3. Lower third: nRF54LM20B, QMI8658A, QSPI flash and always-on regulators.
4. Left edge: microphones, codec and acoustic keep-out.
5. Lower edge: speaker amplifier, motor driver and magnetic charging contacts.

No switching inductor, speaker, vibration motor, cellular bulk capacitor or
SIM metalwork may sit inside the QMI8658 mechanical keep-out. The IMU is placed
near the PCB centerline, aligned with the case axes, and its orientation mark
is visible after assembly.

## Antenna and Acoustic Structure

- LTE antenna: custom FPC in the upper strap/lug region, away from the battery
  and wrist; 50-ohm coax or spring-contact feed with a pi matching network.
- GNSS antenna: upward-facing FPC/ceramic element in the lower strap/lug
  region; no display metal or battery directly above its active area.
- 2.4 GHz antenna: PCB/chip antenna at the lower-right case edge with at least
  5 mm three-dimensional keep-out and an RF test connector on EVT.
- EVT keeps separate LTE, GNSS and 2.4 GHz RF test access. Final DVT may remove
  connectors after conducted and radiated tuning is complete.
- T5838 AI microphone: left upper side, independent waterproof acoustic vent.
- Call microphone: left lower side, separate from T5838 and speaker cavity.
- Speaker: lower side-facing sealed cavity with waterproof membrane; its
  acoustic volume is isolated from both microphones and the IMU.
- Vibration motor: lower-left internal wall with an elastomer isolation seat.

The antenna-carrying strap sections are replaceable service parts, but generic
third-party straps are not promised for V1 because RF performance has priority.

## Enclosure Construction

- EVT: SLA nylon/resin or CNC polymer shell using the final external envelope,
  screws and a replaceable gasket. No cosmetic tooling.
- DVT: production-intent PC+ABS top/midframe, hardened cover lens, silicone
  button seals, acoustic membranes and stainless fasteners.
- Production: ultrasonic weld or screw/gasket construction is selected only
  after repairability and IP67 tests. Injection tooling starts after DVT fit,
  drop, sweat, charging-temperature and RF tests pass.

## What Is Frozen and What Can Tune

Frozen through EVT/DVT:

- wrist-worn form, external body dimensions and strap width;
- display model and no-touch interaction;
- three physical controls and magnetic charging;
- main PCB maximum outline and battery bay;
- no camera and no exposed USB;
- core silicon from ADR-0005.

Allowed EVT tuning without changing product form:

- internal ribs, screw posts, gasket profile and acoustic membranes;
- antenna element supplier, matching values and coax length;
- passive values, test points and component rotation;
- battery supplier within the frozen bay;
- cosmetic color, texture and printed markings.

## Acceptance Before Tooling

- complete PCB and battery fit with 0.5 mm assembly tolerance;
- buttons operable with the device worn by a child-sized wrist;
- speaker intelligibility and both microphones free of structural feedback;
- LTE/GNSS/BLE antenna tuning in the worn and unworn states;
- 1 m drop sequence, sweat exposure and charging-temperature test;
- IP67 pre-compliance on at least three DVT enclosures;
- measured 48-hour guard profile or an explicit product decision before any
  endurance claim.

## Reference Drawing

See `docs/product/V1_PRO_FORM_FACTOR_DRAWING.svg`.

## Market Envelope References

- Fitbit Ace LTE: 41.04 x 44.89 x 13.35 mm, 28.03 g without strap:
  https://store.google.com/product/fitbit_ace_lte_specs
- Xiaomi Smart Kids Watch: 54.4 x 41.4 x 14.6 mm and 900 mAh:
  https://www.mi.com/my/product/xiaomi-smart-kids-watch/specs/
- Sharp display dimensions:
  https://global.sharp/products/device/lineup/selection/lcd/mobile/index.html

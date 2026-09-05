# HW021-C0.1 Independent Review and Release Checklist

All boxes are intentionally open. `HW021-C0.1` is an intake pack, not a design
release.

## Evidence Intake

- [ ] Exact SIM7670G GNSS-enabled order code, hardware/KDL revision, firmware,
      public hardware-design manual and errata are attached from SIMCom.
- [ ] Every received component's OPN, marking, lot/date code and document
      revision match the candidate matrix.
- [ ] Authorized-channel lifecycle, MOQ, lead time and alternates are reviewed
      without committing confidential quotes.
- [ ] CALL-020 measured codec/bitrate/frame/jitter/gap/reconnect/overhead fields
      replace every media placeholder.
- [ ] COMPLIANCE-010 qualified written response is tied to exact radio,
      antenna, Wi-Fi/BLE, battery, charger, enclosure and market assumptions.
- [ ] Founder decisions exist for carry form, size/weight, environmental
      target, battery capacity, operator/channel and charger-in-box.

## Electrical Engineering Review

- [ ] One MCU variant and one exact modem revision are conditionally
      down-selected with explicit rollback criteria.
- [ ] UART socket bearer or USB host bearer is selected from measured CALL-020
      traffic, with flow control, failure/recovery and debug arbitration proven.
- [ ] Modem IO voltage, level shifting, PWRKEY/reset/wake timing, boot state and
      brownout behavior follow the exact official hardware manual.
- [ ] Audio clock tree, PDM path, I2S full duplex, DMA, mute, PA enable, rail
      sequencing and crash/reset safe state are reviewed.
- [ ] Speaker electrical power is bounded below its continuous rating for all
      battery/USB/codec gain corners.
- [ ] Priority outbox capacity equation, critical byte/record reserve,
      authenticated ACK, torn-write and migration behavior are closed.
- [ ] Cell/protection/charger/gauge chemistry, thresholds, FET SOA, NTC,
      connector and pulse-current calculations are independently reviewed.
- [ ] Every rail has min/nominal/max voltage, peak/average load, source,
      decoupling, startup, shutdown, brownout and thermal margin.
- [ ] USB-C CC, ESD, shield/chassis, sink-current and service-data behavior are
      reviewed; no unsupported PD/fast-charge claim exists.
- [ ] SOS input is wake-capable, debounced, ESD-protected and independent from
      boot/debug straps; immediate local feedback survives no network.
- [ ] Test points do not create unsafe stubs on RF, SIM, USB or class-D nets.
- [ ] Schematic peer review and ERC report exist with every waiver owned.

## RF and Antenna Review

- [ ] Target mainland operator bands are mapped to the exact modem SKU using
      official evidence; each operator still has a representative test plan.
- [ ] LTE, GNSS and unavoidable 2.4-GHz radio placement/keep-out/coexistence is
      reviewed in the intended enclosure and carry orientations.
- [ ] 50-ohm stack-up, pi networks, connectors, cable loss, grounding and
      conducted-test topology are approved by an independent RF reviewer.
- [ ] Antenna candidates physically fit without crossing battery, speaker,
      microphone, USB/SIM, metal, waterproofing or body-loading constraints.
- [ ] Matching/VNA plus TRP/TIS/SAR-exposure and GNSS field evidence plan is
      accepted; vendor free-space plots are not used as product results.
- [ ] Layout peer review and DRC report exist with every RF waiver owned.

## Audio, Mechanical and Privacy Review

- [ ] Mic inlet, speaker chamber/outlet, acoustic membrane, antenna and SOS
      reachability are reviewed together for each intended carry form.
- [ ] SPL, intelligibility, echo, noise, wind, clipping, pop/click and thermal
      acceptance budgets are defined before acoustic tests.
- [ ] Microphone and codec power are hardware-controllable, default off outside
      authorized calls/tests, and their effective state is observable.
- [ ] No ordinary raw audio retention exists; authorized diagnostic capture has
      explicit consent, owner, expiry and deletion.
- [ ] Component face-level IP statements are not promoted to enclosure claims;
      sweat/rain/dust and port/membrane validation is planned.
- [ ] Child/elder access, choking, SIM/battery access, skin-contact material,
      SOS force and accidental activation are included in product review.

## Power and Representative Evidence

- [ ] Guard, moving, uncertain-location, SOS, sustained-call, weak-signal,
      charging and thermal load profiles have separate rail/current budgets.
- [ ] Representative battery usable capacity is measured across temperature,
      aging and high-pulse behavior; nominal mAh arithmetic is not a claim.
- [ ] Modem burst and reconnect, GNSS acquisition, class-D output and combined
      SOS+call transients pass without reset, data loss or false ACK.
- [ ] Typical guard reaches the accepted 48-hour target on representative
      battery/enclosure/antenna/firmware/operator configuration.
- [ ] Hardware evidence records exact board revision, firmware/image, SIM and
      operator, power source, connection path, timestamp and evidence path.

## Release Control

- [ ] Versioned schematic, BOM/AVL, net classes, stack-up/impedance,
      placement/keep-out, power tree and test plan form one reviewed pack.
- [ ] Independent EE, RF, audio/mechanical, firmware, security/privacy and
      compliance reviewers sign or record bounded objections.
- [ ] All conditional release blockers have an owner and disposition; no
      `unknown` is silently converted to pass.
- [ ] Founder explicitly authorizes procurement/fabrication under a later task.
- [ ] No Gate is advanced from design files: `P0-LOC`, `P0-CALL`, `P0-SOS`
      remain `NOT_RUN` until representative integrated-hardware evidence.

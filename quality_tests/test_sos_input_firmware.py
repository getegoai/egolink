from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from pc_simulator.sos_walking_skeleton import (
    SosTriggerRejected,
    detect_qualified_long_press,
)


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "firmware" / "mqtt_heartbeat" / "components" / "sos_input"
SOURCE = COMPONENT / "sos_input.c"
HEADER = COMPONENT / "include" / "sos_input.h"
CMAKE = COMPONENT / "CMakeLists.txt"

DEBOUNCE_MIN_MS = 5
DEBOUNCE_MAX_MS = 500
LONG_PRESS_MIN_MS = 500
LONG_PRESS_MAX_MS = 10_000
UINT64_MAX = (1 << 64) - 1


@dataclass
class _Step:
    status: str
    edge: bool
    edge_time_ms: int | None
    phase: str
    armed: bool
    stable_pressed: bool


class _SosInputSpecFixture:
    """Executable contract model; it does not execute the firmware C object."""

    def __init__(
        self,
        *,
        debounce_ms: int = 50,
        long_press_ms: int = 2000,
        initial_pressed: bool = False,
        now_ms: int = 0,
    ) -> None:
        if not (
            DEBOUNCE_MIN_MS <= debounce_ms <= DEBOUNCE_MAX_MS
            and LONG_PRESS_MIN_MS <= long_press_ms <= LONG_PRESS_MAX_MS
            and long_press_ms >= debounce_ms
        ):
            raise ValueError("invalid_config")
        if not 0 <= now_ms <= UINT64_MAX:
            raise ValueError("invalid_time")
        self.debounce_ms = debounce_ms
        self.long_press_ms = long_press_ms
        self.last_sample_ms = now_ms
        self.candidate_since_ms = now_ms
        self.stable_pressed_since_ms = now_ms
        self.stable_pressed = initial_pressed
        self.candidate_pressed = initial_pressed
        self.initial_release_required = initial_pressed
        self.armed = not initial_pressed
        self.event_latched = initial_pressed
        self.fault_latched = False
        self.phase = "wait_initial_release" if initial_pressed else "armed"

    def _refresh_phase(self) -> None:
        if self.fault_latched:
            self.phase = "fault"
        elif self.candidate_pressed != self.stable_pressed:
            self.phase = (
                "debounce_press" if self.candidate_pressed else "debounce_release"
            )
        elif self.stable_pressed:
            if self.initial_release_required:
                self.phase = "wait_initial_release"
            elif self.event_latched:
                self.phase = "triggered"
            else:
                self.phase = "pressed"
        else:
            self.phase = "armed"

    def _result(
        self,
        status: str = "ok",
        edge: bool = False,
        edge_time_ms: int | None = None,
    ) -> _Step:
        return _Step(
            status=status,
            edge=edge,
            edge_time_ms=edge_time_ms if edge else None,
            phase=self.phase,
            armed=self.armed,
            stable_pressed=self.stable_pressed,
        )

    @staticmethod
    def _deadline(start_ms: int, duration_ms: int) -> int:
        if start_ms > UINT64_MAX - duration_ms:
            raise OverflowError("time_overflow")
        return start_ms + duration_ms

    def _time_overflow(self) -> _Step:
        self.fault_latched = True
        self.armed = False
        self._refresh_phase()
        return self._result("time_overflow")

    def _advance(self, now_ms: int) -> tuple[bool, int | None] | _Step:
        edge = False
        edge_time_ms: int | None = None
        while True:
            debounce_pending = self.candidate_pressed != self.stable_pressed
            trigger_pending = (
                self.stable_pressed
                and self.armed
                and not self.initial_release_required
                and not self.event_latched
            )
            try:
                debounce_at_ms = (
                    self._deadline(self.candidate_since_ms, self.debounce_ms)
                    if debounce_pending
                    else None
                )
                trigger_at_ms = (
                    self._deadline(
                        self.stable_pressed_since_ms, self.long_press_ms
                    )
                    if trigger_pending
                    else None
                )
            except OverflowError:
                return self._time_overflow()

            if (
                trigger_at_ms is not None
                and trigger_at_ms <= now_ms
                and (debounce_at_ms is None or trigger_at_ms <= debounce_at_ms)
            ):
                self.event_latched = True
                self.armed = False
                edge = True
                edge_time_ms = trigger_at_ms
                self._refresh_phase()
                continue

            if debounce_at_ms is not None and debounce_at_ms <= now_ms:
                self.stable_pressed = self.candidate_pressed
                if self.stable_pressed:
                    self.stable_pressed_since_ms = debounce_at_ms
                    self.event_latched = False
                else:
                    self.initial_release_required = False
                    self.armed = True
                    self.event_latched = False
                self._refresh_phase()
                continue
            return edge, edge_time_ms

    def step(self, raw_pressed: bool, now_ms: int) -> _Step:
        if self.fault_latched:
            self._refresh_phase()
            return self._result("fault_latched")
        if not 0 <= now_ms <= UINT64_MAX or now_ms < self.last_sample_ms:
            self.fault_latched = True
            self.armed = False
            self._refresh_phase()
            return self._result("time_rollback")
        self.last_sample_ms = now_ms

        advanced = self._advance(now_ms)
        if isinstance(advanced, _Step):
            return advanced
        edge, edge_time_ms = advanced

        if raw_pressed != self.candidate_pressed:
            self.candidate_pressed = raw_pressed
            self.candidate_since_ms = now_ms
            self._refresh_phase()
            return self._result(edge=edge, edge_time_ms=edge_time_ms)
        self._refresh_phase()
        return self._result(edge=edge, edge_time_ms=edge_time_ms)


class SosInputFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")

    def test_component_is_isolated_and_has_no_gpio_or_remote_side_effects(self) -> None:
        self.assertEqual(
            'idf_component_register(\n    SRCS "sos_input.c"\n    INCLUDE_DIRS "include"\n)\n',
            self.cmake,
        )
        combined = self.source + self.header
        for forbidden in (
            "driver/gpio",
            "gpio_",
            "esp_http",
            "esp_wifi",
            "sim7670",
            "mqtt",
            "nvs_",
            "freertos/",
            "app_main",
            "location_state",
            "ego_call",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined.lower())

    def test_configuration_is_runtime_supplied_and_bounded(self) -> None:
        for token in (
            "EGOLINK_SOS_INPUT_DEBOUNCE_MIN_MS UINT32_C(5)",
            "EGOLINK_SOS_INPUT_DEBOUNCE_MAX_MS UINT32_C(500)",
            "EGOLINK_SOS_INPUT_LONG_PRESS_MIN_MS UINT32_C(500)",
            "EGOLINK_SOS_INPUT_LONG_PRESS_MAX_MS UINT32_C(10000)",
            "uint32_t debounce_ms",
            "uint32_t long_press_ms",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.header)
        self.assertIn("config_is_valid", self.source)
        self.assertIn(
            "return config->long_press_ms >= config->debounce_ms;", self.source
        )

        for values in (
            {"debounce_ms": 4},
            {"debounce_ms": 501},
            {"long_press_ms": 499},
            {"long_press_ms": 10_001},
        ):
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, "invalid_config"):
                    _SosInputSpecFixture(**values)

    def test_one_edge_per_long_press_and_release_rearms(self) -> None:
        machine = _SosInputSpecFixture()
        self.assertEqual("debounce_press", machine.step(True, 10).phase)
        pressed = machine.step(True, 60)
        self.assertEqual((False, "pressed", True), (pressed.edge, pressed.phase, pressed.armed))
        self.assertFalse(machine.step(True, 2059).edge)
        first = machine.step(True, 2060)
        self.assertEqual((True, 2060, "triggered", False), (first.edge, first.edge_time_ms, first.phase, first.armed))
        self.assertFalse(machine.step(True, 9000).edge)

        self.assertEqual("debounce_release", machine.step(False, 9010).phase)
        released = machine.step(False, 9060)
        self.assertEqual(("armed", True), (released.phase, released.armed))
        machine.step(True, 9100)
        machine.step(True, 9150)
        self.assertTrue(machine.step(True, 11_150).edge)

    def test_bounce_and_short_press_do_not_fabricate_an_edge(self) -> None:
        machine = _SosInputSpecFixture()
        samples = (
            (True, 10),
            (False, 30),
            (True, 40),
            (True, 89),
            (True, 90),
            (False, 200),
            (True, 220),
            (False, 300),
            (False, 350),
        )
        results = [machine.step(level, now) for level, now in samples]
        self.assertFalse(any(result.edge for result in results))
        self.assertEqual(("armed", True, False), (results[-1].phase, results[-1].armed, results[-1].stable_pressed))

    def test_release_bounce_preserves_the_same_press_but_never_duplicates(self) -> None:
        machine = _SosInputSpecFixture()
        machine.step(True, 10)
        machine.step(True, 60)
        self.assertEqual("debounce_release", machine.step(False, 2000).phase)
        self.assertEqual("pressed", machine.step(True, 2020).phase)
        edge = machine.step(True, 2060)
        self.assertTrue(edge.edge)
        self.assertFalse(machine.step(True, 3061).edge)

    def test_startup_held_requires_debounced_release_then_a_new_press(self) -> None:
        machine = _SosInputSpecFixture(initial_pressed=True, now_ms=100)
        held = machine.step(True, 10_000)
        self.assertEqual((False, "wait_initial_release", False), (held.edge, held.phase, held.armed))
        self.assertEqual("debounce_release", machine.step(False, 10_010).phase)
        released = machine.step(False, 10_060)
        self.assertEqual(("armed", True), (released.phase, released.armed))
        machine.step(True, 10_100)
        machine.step(True, 10_150)
        self.assertTrue(machine.step(True, 12_150).edge)

    def test_debounce_and_long_press_boundaries_are_inclusive(self) -> None:
        machine = _SosInputSpecFixture(debounce_ms=5, long_press_ms=500)
        machine.step(True, 1)
        before_debounce = machine.step(True, 5)
        self.assertEqual((False, "debounce_press"), (before_debounce.edge, before_debounce.phase))
        pressed = machine.step(True, 6)
        self.assertEqual("pressed", pressed.phase)
        self.assertFalse(machine.step(True, 505).edge)
        self.assertTrue(machine.step(True, 506).edge)

    def test_time_rollback_is_explicit_and_latches_until_reinit(self) -> None:
        machine = _SosInputSpecFixture(now_ms=100)
        rollback = machine.step(True, 99)
        self.assertEqual(("time_rollback", False, "fault", False), (rollback.status, rollback.edge, rollback.phase, rollback.armed))
        latched = machine.step(False, 101)
        self.assertEqual(("fault_latched", False, "fault"), (latched.status, latched.edge, latched.phase))

        recovered = _SosInputSpecFixture(now_ms=101)
        self.assertEqual(("ok", "armed"), (recovered.step(False, 101).status, recovered.phase))
        self.assertIn("if (now_ms < input->last_sample_ms)", self.source)
        self.assertIn("input->fault_latched = true", self.source)

    def test_sparse_polling_preserves_the_exact_debounced_edge_time(self) -> None:
        machine = _SosInputSpecFixture()
        machine.step(True, 10)
        edge = machine.step(True, 5000)
        self.assertEqual((True, 2060, "triggered"), (edge.edge, edge.edge_time_ms, edge.phase))
        self.assertIn("input->stable_pressed_since_ms = debounce_at_ms", self.source)
        self.assertIn("*sos_edge_time_ms = trigger_at_ms", self.source)

    def test_default_and_release_boundary_match_the_host_replay_contract(self) -> None:
        self.assertIn(
            "EGOLINK_SOS_INPUT_DEFAULT_LONG_PRESS_MS UINT32_C(2000)",
            self.header,
        )
        at_boundary = [
            {"event_time_ms": 0, "pressed": False},
            {"event_time_ms": 10, "pressed": True},
            {"event_time_ms": 2060, "pressed": False},
        ]
        host = detect_qualified_long_press(
            at_boundary, observed_until_ms=2110
        )
        self.assertEqual(2060, host["triggered_at_ms"])

        device = _SosInputSpecFixture()
        device.step(True, 10)
        device_edge = device.step(False, 2060)
        self.assertEqual(
            (True, 2060, "debounce_release"),
            (device_edge.edge, device_edge.edge_time_ms, device_edge.phase),
        )
        self.assertEqual(
            ("armed", True), (device.step(False, 2110).phase, device.armed)
        )

        before_boundary = [
            {"event_time_ms": 0, "pressed": False},
            {"event_time_ms": 10, "pressed": True},
            {"event_time_ms": 2009, "pressed": False},
        ]
        with self.assertRaises(SosTriggerRejected):
            detect_qualified_long_press(before_boundary, observed_until_ms=2060)
        early_release_device = _SosInputSpecFixture()
        early_release_device.step(True, 10)
        self.assertFalse(early_release_device.step(False, 2009).edge)
        self.assertFalse(early_release_device.step(False, 2060).edge)

    def test_near_uint64_max_checked_deadlines_and_wrap_fail_closed(self) -> None:
        start = UINT64_MAX - 5000
        machine = _SosInputSpecFixture(now_ms=start)
        machine.step(True, start + 10)
        edge = machine.step(True, start + 3060)
        self.assertEqual((True, start + 2060), (edge.edge, edge.edge_time_ms))
        wrapped = machine.step(True, 0)
        self.assertEqual(("time_rollback", False, "fault"), (wrapped.status, wrapped.edge, wrapped.phase))

        overflowing = _SosInputSpecFixture(now_ms=UINT64_MAX - 20)
        pending = overflowing.step(True, UINT64_MAX - 10)
        self.assertEqual(("ok", "debounce_press"), (pending.status, pending.phase))
        overflow = overflowing.step(True, UINT64_MAX - 10)
        self.assertEqual(("time_overflow", False, "fault", False), (overflow.status, overflow.edge, overflow.phase, overflow.armed))
        self.assertIn("start_ms > UINT64_MAX - (uint64_t)duration_ms", self.source)
        self.assertIn("return latch_time_overflow(input);", self.source)

    def test_low_battery_has_no_veto_surface(self) -> None:
        signature_start = self.header.index("egolink_sos_input_process(")
        signature_end = self.header.index(");", signature_start)
        signature = self.header[signature_start:signature_end]
        self.assertNotIn("battery", signature.lower())
        self.assertNotIn("power", signature.lower())
        self.assertIn("there is no low-power", self.header.lower())

        edges_by_battery_fixture = []
        for _low_battery in (False, True):
            machine = _SosInputSpecFixture()
            machine.step(True, 10)
            machine.step(True, 60)
            edges_by_battery_fixture.append(machine.step(True, 3060).edge)
        self.assertEqual([True, True], edges_by_battery_fixture)

    def test_errors_and_phases_have_explicit_names(self) -> None:
        for name in (
            "invalid_argument",
            "invalid_config",
            "not_initialized",
            "time_rollback",
            "time_overflow",
            "fault_latched",
            "wait_initial_release",
            "debounce_press",
            "triggered",
            "debounce_release",
            "fault",
        ):
            with self.subTest(name=name):
                self.assertIn(f'return "{name}";', self.source)

    def test_c_api_checks_initialization_and_clears_event_output_on_error(self) -> None:
        process_start = self.source.index(
            "egolink_sos_input_status_t egolink_sos_input_process("
        )
        process_body = self.source[process_start:]
        self.assertLess(
            process_body.index("clear_output(output);"),
            process_body.index("if (input == NULL || output == NULL)"),
        )
        for guard in (
            "EGOLINK_SOS_INPUT_STATUS_INVALID_ARGUMENT",
            "EGOLINK_SOS_INPUT_STATUS_NOT_INITIALIZED",
            "EGOLINK_SOS_INPUT_STATUS_TIME_ROLLBACK",
            "EGOLINK_SOS_INPUT_STATUS_FAULT_LATCHED",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, process_body)
        self.assertIn("(void)memset(input, 0, sizeof(*input));", self.source)
        self.assertIn("sos_edge ? sos_edge_time_ms : UINT64_C(0)", self.source)

    def test_actual_c_cross_compiles_with_esp32s3_warnings_as_errors(self) -> None:
        compiler_candidates = [
            shutil.which("xtensa-esp32s3-elf-gcc"),
            Path(
                "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
                "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
            ),
        ]
        compiler = next(
            (
                Path(candidate)
                for candidate in compiler_candidates
                if candidate and Path(candidate).is_file()
            ),
            None,
        )
        if compiler is None:
            self.skipTest("ESP32-S3 cross compiler unavailable")

        harness = r'''#include "sos_input.h"

int sos_input_compile_harness(void)
{
    const egolink_sos_input_config_t config = {
        .debounce_ms = EGOLINK_SOS_INPUT_DEFAULT_DEBOUNCE_MS,
        .long_press_ms = EGOLINK_SOS_INPUT_DEFAULT_LONG_PRESS_MS,
    };
    egolink_sos_input_t input;
    egolink_sos_input_output_t output;
    if (egolink_sos_input_init(&input, &config, false, UINT64_C(0)) !=
        EGOLINK_SOS_INPUT_STATUS_OK) {
        return 1;
    }
    if (egolink_sos_input_process(&input, true, UINT64_C(1), &output) !=
        EGOLINK_SOS_INPUT_STATUS_OK) {
        return 2;
    }
    return output.sos_edge ? 3 : 0;
}
'''
        warnings = (
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wsign-conversion",
            "-Wshadow",
            "-Wundef",
            "-Wswitch-enum",
            "-Wformat=2",
            "-pedantic",
        )
        with tempfile.TemporaryDirectory(prefix="egolink-sos-input-") as temp_dir:
            temp = Path(temp_dir)
            harness_path = temp / "sos_input_compile_harness.c"
            harness_path.write_text(harness, encoding="utf-8")
            for source, object_name in (
                (SOURCE, "sos_input.o"),
                (harness_path, "sos_input_compile_harness.o"),
            ):
                result = subprocess.run(
                    [
                        str(compiler),
                        "-std=c11",
                        *warnings,
                        f"-I{COMPONENT / 'include'}",
                        "-c",
                        str(source),
                        "-o",
                        str(temp / object_name),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertTrue((temp / object_name).is_file())


if __name__ == "__main__":
    unittest.main()

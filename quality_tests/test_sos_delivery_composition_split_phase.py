"""SOS-010J split-phase composition contract and strict C compile checks."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
SOURCE = COMPONENTS / "sos_delivery_composition" / "sos_delivery_composition.c"
HEADER = COMPONENTS / "sos_delivery_composition" / "include" / "sos_delivery_composition.h"
PACKET = ROOT / "docs" / "tasks" / "active" / "SOS-010_SOS_WALKING_SKELETON.md"


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        depth += source[index] == "{"
        depth -= source[index] == "}"
        if depth == 0:
            return source[start : index + 1]
    raise AssertionError(signature)


class SosCompositionSplitPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def test_public_split_phase_seam_is_explicit(self) -> None:
        for name in ("prepare", "execute_prepared", "settle_prepared"):
            self.assertIn(f"egolink_sos_delivery_composition_{name}(", self.header)
        prose = " ".join(self.header.split()).lower()
        self.assertIn("execute_prepared must run after releasing that owner", prose)
        self.assertIn("non-cooperative", prose)

    def test_execute_does_not_take_composition_busy_or_shared_dependencies(self) -> None:
        body = function_body(
            self.source,
            "egolink_sos_delivery_composition_execute_prepared(",
        )
        self.assertNotIn("internal->busy = true", body)
        self.assertNotIn("caller_dependencies_match", body)
        self.assertNotRegex(body, r"dispatcher|shared_outbox|location_adapter|policy_core")
        self.assertEqual(1, body.count("egolink_p0_delivery_runtime_execute_prepared("))

    def test_prepare_and_settle_are_owned_and_single_action(self) -> None:
        body = function_body(self.source, "static egolink_sos_delivery_composition_status_t split_phase_owned(")
        self.assertIn("delivery_ready(internal)", body)
        self.assertIn("internal->busy = true", body)
        self.assertIn("internal->busy = false", body)
        self.assertEqual(1, body.count("egolink_p0_delivery_runtime_prepare("))
        self.assertEqual(1, body.count("egolink_p0_delivery_runtime_settle_prepared("))

    def test_durable_wake_is_only_atomic_preemption_seam(self) -> None:
        body = function_body(self.source, "static bool record_sender_wake(")
        self.assertIn("request->durable_manual_sos_available", body)
        self.assertEqual(1, body.count("egolink_p0_delivery_runtime_signal_durable_sos("))
        for forbidden in ("http_post", "drive_once", "dispatcher_begin", "dispatcher_finish"):
            self.assertNotIn(forbidden, body)

    def test_shutdown_fails_closed_for_every_unsettled_split_phase(self) -> None:
        body = function_body(
            self.source,
            "static egolink_sos_delivery_composition_status_t delivery_shutdown_blocker(",
        )
        self.assertIn("EGOLINK_P0_DELIVERY_PHASE_PREPARED", body)
        self.assertIn("EGOLINK_P0_DELIVERY_PHASE_EXECUTING_PREPARED", body)
        self.assertIn("EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY", body)
        self.assertIn(
            "snapshot.phase != EGOLINK_P0_DELIVERY_PHASE_PREPARED",
            body,
        )
        self.assertIn(
            "EGOLINK_SOS_DELIVERY_COMPOSITION_TRANSPORT_RESULT_READY",
            body,
        )

    def test_split_recovery_wrapper_is_owner_only_and_never_posts(self) -> None:
        body = function_body(
            self.source,
            "egolink_sos_delivery_composition_recover_delivery_once(",
        )
        self.assertIn("internal->busy = true", body)
        self.assertIn("egolink_p0_delivery_runtime_retry_finish(", body)
        self.assertIn("egolink_p0_delivery_runtime_retry_begin_recovery(", body)
        self.assertNotIn("execute_prepared", body)
        self.assertNotIn("drive_once", body)
        self.assertIn("EGOLINK_P0_DELIVERY_PREPARED", body)
        self.assertIn("EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY", body)

    def test_packet_records_cooperative_and_non_claim_boundaries(self) -> None:
        for phrase in (
            "cooperative cancellation",
            "non-cooperative",
            "result-wins",
            "cancel-wins",
            "P0-SOS",
        ):
            self.assertIn(phrase, self.packet)

    def test_actual_source_cross_compiles_strictly(self) -> None:
        compiler = shutil.which("xtensa-esp32s3-elf-gcc") or str(
            Path("C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/")
            / "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        )
        if not Path(compiler).is_file():
            self.skipTest("ESP32-S3 compiler unavailable")
        names = (
            "sos_delivery_composition", "location_outbox_adapter",
            "location_state_emitter", "location_policy_core", "p0_delivery_runtime",
            "p0_outbox_dispatcher", "persistent_priority_outbox", "sos_device_runtime",
            "sos_input", "sos_orchestrator", "sos_outbox_adapter",
            "sos_pending_edge_journal",
        )
        with tempfile.TemporaryDirectory() as directory:
            command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-Wconversion", "-Wformat=2", "-Wshadow", "-Wsign-conversion"]
            command.extend(f"-I{COMPONENTS / name / 'include'}" for name in names)
            command.extend(["-c", str(SOURCE), "-o", str(Path(directory) / "composition.o")])
            completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60)
            self.assertEqual(0, completed.returncode, completed.stderr)

    def test_actual_composition_and_runtime_split_symbols_relocatable_link(self) -> None:
        compiler = Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        )
        nm = compiler.with_name("xtensa-esp32s3-elf-nm.exe")
        if not compiler.is_file() or not nm.is_file():
            self.skipTest("ESP32-S3 compiler unavailable")
        names = (
            "sos_delivery_composition", "location_outbox_adapter",
            "location_state_emitter", "location_policy_core", "p0_delivery_runtime",
            "p0_outbox_dispatcher", "persistent_priority_outbox", "sos_device_runtime",
            "sos_input", "sos_orchestrator", "sos_outbox_adapter",
            "sos_pending_edge_journal",
        )
        includes = [f"-I{COMPONENTS / name / 'include'}" for name in names]
        runtime = COMPONENTS / "p0_delivery_runtime" / "p0_delivery_runtime.c"
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            objects = []
            for source in (SOURCE, runtime):
                output = temporary / f"{source.stem}.o"
                command = [str(compiler), "-std=c11", "-Wall", "-Wextra", "-Werror",
                           "-Wconversion", "-Wformat=2", "-Wshadow", "-Wsign-conversion",
                           *includes, "-c", str(source), "-o", str(output)]
                completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60)
                self.assertEqual(0, completed.returncode, completed.stderr)
                objects.append(output)
            linked = temporary / "composition_runtime.o"
            completed = subprocess.run(
                [str(compiler), "-nostdlib", "-r", *(str(item) for item in objects), "-o", str(linked)],
                cwd=ROOT, text=True, capture_output=True, timeout=60,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            undefined = subprocess.run(
                [str(nm), "-u", str(linked)], text=True, capture_output=True, timeout=30, check=True
            ).stdout
            for symbol in ("prepare", "execute_prepared", "settle_prepared", "signal_durable_sos"):
                self.assertNotIn(f"egolink_p0_delivery_runtime_{symbol}", undefined)


if __name__ == "__main__":
    unittest.main()

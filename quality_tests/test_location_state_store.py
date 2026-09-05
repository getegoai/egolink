from __future__ import annotations

from copy import deepcopy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest

from quality_tests.test_location_state_mirror import envelope, location_state
from server.location_state_runtime import LocationStateRegressionError, LocationStateRuntimeMirror, LocationStateValidationError
from server.location_state_store import LocationStateStore


class LocationStateStoreTests(unittest.TestCase):
    def test_sqlite_integer_overflow_fails_before_staging_or_write(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            seed = LocationStateRuntimeMirror()
            store = LocationStateStore(Path(root) / "hub.sqlite3")
            base = envelope(seed, location_state(1_000))
            too_large = 1 << 63

            for field in ("boot_count", "event_time_ns", "sequence_id"):
                with self.subTest(field=field):
                    invalid = deepcopy(base)
                    invalid[field] = too_large
                    with self.assertRaises(LocationStateValidationError):
                        store.ingest(invalid, server_receive_time_ms=10)

            with self.assertRaises(LocationStateValidationError):
                store.ingest(base, server_receive_time_ms=too_large)
            self.assertEqual(store.timeline_length(base["device_id"]), 0)
            with closing(sqlite3.connect(store.db_path)) as db:
                self.assertEqual(
                    db.execute(
                        "SELECT COUNT(*) FROM location_state_timeline"
                    ).fetchone()[0],
                    0,
                )

    def test_failed_commit_does_not_advance_in_memory_or_disk(self) -> None:
        class FailingStore(LocationStateStore):
            fail = False
            def _persist(self, *args, **kwargs):
                if self.fail:
                    raise sqlite3.OperationalError("injected write failure")
                return super()._persist(*args, **kwargs)
        with tempfile.TemporaryDirectory() as root:
            seed = LocationStateRuntimeMirror()
            store = FailingStore(Path(root) / "hub.sqlite3")
            first = envelope(seed, location_state(1_000), observation_id="first")
            second = envelope(seed, location_state(2_000), sequence_id=2, observation_id="second")
            store.ingest(first)
            store.fail = True
            with self.assertRaises(sqlite3.OperationalError):
                store.ingest(second)
            self.assertEqual(store.timeline_length(first["device_id"]), 1)
            self.assertEqual(LocationStateStore(store.db_path).timeline_length(first["device_id"]), 1)

    def test_recovery_rejects_hash_or_receive_time_corruption(self) -> None:
        for column, value in (("content_hash", "0" * 64), ("server_receive_time_ms", 999)):
            with self.subTest(column=column), tempfile.TemporaryDirectory() as root:
                db_path = Path(root) / "hub.sqlite3"
                seed = LocationStateRuntimeMirror()
                store = LocationStateStore(db_path)
                store.ingest(envelope(seed, location_state(1_000)), server_receive_time_ms=10)
                with closing(sqlite3.connect(db_path)) as db:
                    db.execute(f"UPDATE location_state_timeline SET {column}=?", (value,))
                    db.commit()
                with self.assertRaises(LocationStateValidationError):
                    LocationStateStore(db_path)

    def test_restart_repairs_derived_current_from_validated_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.sqlite3"
            seed = LocationStateRuntimeMirror()
            item = envelope(seed, location_state(1_000))
            store = LocationStateStore(db_path)
            store.ingest(item, server_receive_time_ms=10)

            with closing(sqlite3.connect(db_path)) as db:
                db.execute(
                    """UPDATE location_state_current
                    SET timeline_id=?, envelope_json=?
                    WHERE device_id=?""",
                    (999, "{}", item["device_id"]),
                )
                db.commit()

            recovered = LocationStateStore(db_path)
            self.assertEqual(recovered.timeline_length(item["device_id"]), 1)
            with closing(sqlite3.connect(db_path)) as db:
                timeline = db.execute(
                    """SELECT id,envelope_json FROM location_state_timeline
                    WHERE device_id=?""",
                    (item["device_id"],),
                ).fetchone()
                current = db.execute(
                    """SELECT timeline_id,envelope_json FROM location_state_current
                    WHERE device_id=?""",
                    (item["device_id"],),
                ).fetchone()
            self.assertEqual(current, timeline)

    def test_append_duplicate_restart_and_default_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.sqlite3"
            seed = LocationStateRuntimeMirror()
            item = envelope(seed, location_state(1_000), server_receive_time_ms=1)
            store = LocationStateStore(db_path)
            self.assertEqual(store.ingest(item, server_receive_time_ms=10)["status"], "accepted")
            self.assertEqual(store.ingest(item, server_receive_time_ms=20)["status"], "duplicate")
            self.assertEqual(store.timeline_length(item["device_id"]), 1)
            with closing(sqlite3.connect(db_path)) as db:
                persisted = json.loads(db.execute("SELECT envelope_json FROM location_state_timeline").fetchone()[0])
            self.assertEqual(persisted["server_receive_time_ms"], 10)
            recovered = LocationStateStore(db_path)
            self.assertEqual(recovered.timeline_length(item["device_id"]), 1)
            snapshot = recovered.current(item["device_id"], view_event_time_ns=2_000_000_000, view_event_time_source="timestamp_utc_ns", stale_after_ms=5_000, offline_after_ms=10_000)
            self.assertIsNone(snapshot["position"])

    def test_regression_fails_without_appending(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            seed = LocationStateRuntimeMirror()
            store = LocationStateStore(Path(root) / "hub.sqlite3")
            newer = envelope(seed, location_state(2_000), sequence_id=2, observation_id="newer")
            older = envelope(seed, location_state(1_000), sequence_id=1, observation_id="older")
            store.ingest(newer)
            with self.assertRaises(LocationStateRegressionError):
                store.ingest(older)
            self.assertEqual(store.timeline_length(newer["device_id"]), 1)

    def test_existing_message_hub_database_migrates_additively(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "hub.sqlite3"
            with closing(sqlite3.connect(db_path)) as db:
                db.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, payload_json TEXT NOT NULL)")
                db.commit()
            LocationStateStore(db_path)
            with closing(sqlite3.connect(db_path)) as db:
                names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("messages", names)
            self.assertIn("location_state_timeline", names)

    def test_missing_or_modified_policy_config_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "missing.json"
            with self.assertRaises(LocationStateValidationError):
                LocationStateStore(Path(root) / "a.sqlite3", missing)
            config = json.loads((Path(__file__).parents[1] / "shared/config/sensor_policy_v0.json").read_text("utf-8"))
            config["moving"]["gnss_interval_s"] += 1
            modified = Path(root) / "modified.json"
            modified.write_text(json.dumps(config), "utf-8")
            with self.assertRaises(LocationStateValidationError):
                LocationStateStore(Path(root) / "b.sqlite3", modified)

    def test_deploy_inventory_constructs_store_under_python_s(self) -> None:
        repo = Path(__file__).parents[1]
        script = (repo / "scripts/deploy_message_hub_vps.ps1").read_text("utf-8")
        for relative in ("pc_simulator\\sensor_policy_v0.py", "pc_simulator\\location_engine_v0.py", "shared\\config\\sensor_policy_v0.json"):
            self.assertIn(relative, script)
        with tempfile.TemporaryDirectory() as root:
            package = Path(root)
            shutil.copytree(repo / "server", package / "server")
            (package / "pc_simulator").mkdir()
            for name in ("__init__.py", "sensor_policy_v0.py", "location_engine_v0.py"):
                shutil.copy2(repo / "pc_simulator" / name, package / "pc_simulator" / name)
            (package / "shared/config").mkdir(parents=True)
            shutil.copy2(repo / "shared/config/sensor_policy_v0.json", package / "shared/config/sensor_policy_v0.json")
            result = subprocess.run([sys.executable, "-S", "-c", "from server.location_state_store import LocationStateStore; LocationStateStore('runtime/test.sqlite3')"], cwd=package, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

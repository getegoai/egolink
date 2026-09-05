from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import unittest

from quality_tests.test_location_state_mirror import envelope, location_state
from server.location_state_mirror import LocationStateMirror, LocationStateValidationError
from server.location_state_runtime import (
    LocationStateRuntimeMirror,
    LocationStateValidationError as RuntimeValidationError,
)

ROOT = Path(__file__).resolve().parents[1]


class LocationStateRuntimeTests(unittest.TestCase):
    def test_runtime_and_schema_oracle_have_identical_valid_outputs(self) -> None:
        oracle, runtime = LocationStateMirror(), LocationStateRuntimeMirror()
        item = envelope(oracle, location_state(1_000))
        self.assertEqual(oracle.ingest(deepcopy(item)), runtime.ingest(deepcopy(item)))
        self.assertEqual(oracle.current_record(item["device_id"]), runtime.current_record(item["device_id"]))
        view = dict(view_event_time_ns=2_000_000_000, view_event_time_source="timestamp_utc_ns", stale_after_ms=5_000, offline_after_ms=10_000, location_access_authorized=False)
        self.assertEqual(oracle.guardian_snapshot(item["device_id"], **view), runtime.guardian_snapshot(item["device_id"], **view))

    def test_runtime_and_oracle_reject_shared_boundary_failures(self) -> None:
        oracle = LocationStateMirror()
        base = envelope(oracle, location_state(1_000))
        extra = deepcopy(base); extra["unexpected"] = True
        nan_value = deepcopy(base); nan_value["location_state"]["location_confidence"] = float("nan")
        wrong_bool = deepcopy(base); wrong_bool["location_state"]["sos_active"] = 1
        bad_enum = deepcopy(base); bad_enum["location_state"]["gnss_state"] = "maybe"
        missing_evidence = deepcopy(base); del missing_evidence["location_state"]["last_trusted_location"]["evidence_ref"]["capture_time_ns"]
        bad_coordinate = deepcopy(base); bad_coordinate["location_state"]["last_trusted_location"]["latitude_deg"] = 91
        inconsistent_unknown = deepcopy(base); inconsistent_unknown["location_state"]["location_belief"] = "Unknown"
        null_reference = deepcopy(base); null_reference["location_state"]["last_trusted_location"]["evidence_ref"]["reference_id"] = None
        null_receive = deepcopy(base); null_receive["server_receive_time_ms"] = None
        unsafe_device = deepcopy(base); unsafe_device["device_id"] = "设备-一"
        unsafe_session = deepcopy(base); unsafe_session["session_id"] = "session with spaces"
        oversized_device = deepcopy(base); oversized_device["device_id"] = "x" * 129
        for item in (extra, nan_value, wrong_bool, bad_enum, missing_evidence, bad_coordinate, inconsistent_unknown, null_reference, null_receive, unsafe_device, unsafe_session, oversized_device):
            with self.assertRaises(LocationStateValidationError):
                LocationStateMirror().ingest(deepcopy(item))
            with self.assertRaises(RuntimeValidationError):
                LocationStateRuntimeMirror().ingest(deepcopy(item))

    def test_runtime_imports_under_python_without_site_packages(self) -> None:
        command = "from server.location_state_runtime import LocationStateRuntimeMirror; assert LocationStateRuntimeMirror().policy_identity"
        result = subprocess.run([sys.executable, "-S", "-c", command], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("jsonschema", result.stderr)
        self.assertNotIn("referencing", result.stderr)


if __name__ == "__main__":
    unittest.main()

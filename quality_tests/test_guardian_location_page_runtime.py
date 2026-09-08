"""Execute the shipped page JavaScript in Node; no browser or network needed."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest

from server.guardian_location_page import GUARDIAN_LOCATION_JS


NODE_RUNTIME = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const elements = new Map();
let submit;
let current;
let requests;
const element = (id) => {
  if (!elements.has(id)) {
    elements.set(id, {
      value: '', textContent: '', hidden: true,
      set innerHTML(_) { throw new Error('HTML injection is forbidden'); },
      addEventListener(type, listener) {
        if (id !== 'lookup' || type !== 'submit') throw new Error('unexpected listener');
        submit = listener;
      },
    });
  }
  return elements.get(id);
};
const storage = new Proxy({}, {get() {throw new Error('credentials must not be stored');}});
const context = vm.createContext({
  document: {getElementById: element},
  localStorage: storage, sessionStorage: storage,
  fetch(url, options) {
    const location = url.endsWith('/location-state/current');
    if (!location && !url.endsWith('/safety-events/manual-sos/latest')) {
      throw new Error('unexpected endpoint');
    }
    const fixture = location ? current.location : current.sos;
    const request = {url, options, tokenAtFetch: element('guardian-token').value, jsonCalls: 0};
    requests.push(request);
    if (fixture.reject) return Promise.reject(new Error('injected fetch failure'));
    return Promise.resolve({
      ok: fixture.status >= 200 && fixture.status < 300,
      status: fixture.status,
      async json() {
        request.jsonCalls++;
        if (fixture.jsonReject) throw new Error('injected invalid JSON');
        return fixture.body;
      },
    });
  },
});
vm.runInContext(input.script, context, {timeout: 1000, filename: 'guardian-location.js'});
(async () => {
  const snapshots = [];
  for (const action of input.actions) {
    current = action;
    requests = [];
    element('device-id').value = 'device-test';
    element('guardian-token').value = action.token === undefined ? 'test-only-token' : action.token;
    let prevented = false;
    await submit({preventDefault() {prevented = true;}});
    snapshots.push({
      prevented, requests,
      hidden: element('result').hidden,
      token: element('guardian-token').value,
      fields: Object.fromEntries([...elements].map(([id, node]) => [id, node.textContent])),
    });
  }
  process.stdout.write(JSON.stringify(snapshots));
})().catch((error) => {console.error(error); process.exitCode = 1;});
"""


def response(status=200, body=None, **changes):
    return {"status": status, "body": body, **changes}


LOCATION = response(body={"location_state": {
    "device_id": "device-test", "available": True, "freshness": "fresh",
    "position": {"latitude_deg": 31.234567, "longitude_deg": 121.456789},
    "location_source": "gnss", "location_belief": "Known",
    "location_age_ms": 2000, "state_age_ms": 1000,
    "sos_active": False, "offline": False,
}})
SOS = response(body={"manual_sos_alert": {
    "available": True, "event_type": "manual_sos", "priority": "critical",
    "event_id": "event-test", "source_event_time_ms": 1234,
    "time_source": "device_monotonic", "server_receipt": {"state": "received"},
    "guardian_ack_state": "not_acknowledged", "call_state": "not_reported",
}})


class GuardianLocationPageRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if cls.node is None:
            raise RuntimeError("Node is required to execute Guardian page behavior tests")

    def execute(self, *actions):
        result = subprocess.run(
            [self.node, "-e", NODE_RUNTIME],
            input=json.dumps({"script": GUARDIAN_LOCATION_JS, "actions": actions}),
            text=True, encoding="utf-8", capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshots = json.loads(result.stdout)
        for snapshot in snapshots:
            self.assertTrue(snapshot["prevented"])
            self.assertEqual(snapshot["token"], "")
            for request in snapshot["requests"]:
                self.assertEqual(request["tokenAtFetch"], "")
                self.assertEqual(request["options"], {
                    "method": "GET", "headers": {"Authorization": "Bearer test-only-token"},
                    "cache": "no-store", "credentials": "same-origin", "redirect": "error",
                })
                self.assertIn(request["url"], (
                    "/api/v1/devices/device-test/location-state/current",
                    "/api/v1/devices/device-test/safety-events/manual-sos/latest",
                ))
        return snapshots

    def test_location_displays_when_sos_is_missing_failed_or_rejected(self):
        for sos in (response(404), response(500), response(reject=True), response(jsonReject=True),
                    response(body={}), response(body={"manual_sos_alert": {}})):
            with self.subTest(sos=sos):
                _, result = self.execute({"location": LOCATION, "sos": SOS},
                                         {"location": LOCATION, "sos": sos})
                self.assertFalse(result["hidden"])
                self.assertEqual(result["fields"]["position"], "31.234567, 121.456789")
                self.assertEqual(result["fields"]["source"], "gnss")
                self.assertEqual(result["fields"]["request-status"], "位置查询完成；SOS 不可用。")
                for field in ("sos", "sos-alert-state", "sos-event-id", "sos-source-time",
                              "sos-server-receipt", "sos-battery", "sos-guardian-ack", "sos-call-state"):
                    self.assertEqual(result["fields"][field], "不可用", field)

    def test_location_unauthorized_or_unbound_never_displays(self):
        for code, message in ((401, "家属凭证无效。"), (403, "该家属未绑定此设备。")):
            with self.subTest(code=code):
                _, result = self.execute({"location": LOCATION, "sos": SOS},
                                         {"location": response(code, LOCATION["body"]), "sos": SOS})
                self.assertTrue(result["hidden"])
                self.assertEqual(result["fields"]["request-status"], message)
                self.assertEqual(result["requests"][0]["jsonCalls"], 0)

    def test_sos_auth_failure_preserves_existing_denial(self):
        for code, message in ((401, "家属凭证无效。"), (403, "该家属未绑定此设备。")):
            with self.subTest(code=code):
                result, = self.execute({"location": LOCATION, "sos": response(code)})
                self.assertTrue(result["hidden"])
                self.assertEqual(result["fields"]["request-status"], message)
                self.assertEqual(result["requests"][0]["jsonCalls"], 0)

    def test_both_successes_display_location_and_actual_sos(self):
        result, = self.execute({"location": LOCATION, "sos": SOS})
        self.assertFalse(result["hidden"])
        self.assertEqual(result["fields"]["position"], "31.234567, 121.456789")
        self.assertEqual(result["fields"]["location-age"], "2 秒")
        self.assertEqual(result["fields"]["sos-alert-state"], "manual_sos / critical")
        self.assertEqual(result["fields"]["sos-event-id"], "event-test")
        self.assertEqual(result["fields"]["request-status"], "查询完成")

    def test_successful_no_sos_response_is_distinct_from_unavailable(self):
        sos = response(body={"manual_sos_alert": {"available": False, "reason": "no_durable_manual_sos"}})
        result, = self.execute({"location": LOCATION, "sos": sos})
        self.assertFalse(result["hidden"])
        self.assertEqual(result["fields"]["sos-alert-state"], "no_durable_manual_sos")
        self.assertEqual(result["fields"]["sos"], "未触发")

    def test_location_transport_or_payload_failure_hides_prior_result(self):
        for location in (response(500), response(reject=True), response(jsonReject=True)):
            with self.subTest(location=location):
                _, result = self.execute({"location": LOCATION, "sos": SOS},
                                         {"location": location, "sos": SOS})
                self.assertTrue(result["hidden"])

    def test_empty_credential_does_not_fetch_and_hides_prior_result(self):
        _, result = self.execute({"location": LOCATION, "sos": SOS},
                                 {"location": LOCATION, "sos": SOS, "token": ""})
        self.assertTrue(result["hidden"])
        self.assertEqual(result["requests"], [])


if __name__ == "__main__":
    unittest.main()

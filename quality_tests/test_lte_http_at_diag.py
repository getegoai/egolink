from __future__ import annotations

import unittest

from scripts import diag_lte_http_at


class LteHttpAtDiagTests(unittest.TestCase):
    def test_http_get_sequence_uses_public_health_without_token_or_cid_by_default(self) -> None:
        steps = diag_lte_http_at.build_http_get_steps(
            "http://203.0.113.10:8790/health",
            include_cid=False,
            action_timeout_sec=60,
        )
        commands = [item.command for item in steps]

        self.assertIn('AT+HTTPPARA="URL","http://203.0.113.10:8790/health"', commands)
        self.assertIn("AT+HTTPACTION=0", commands)
        self.assertNotIn('AT+HTTPPARA="CID",1', commands)
        self.assertFalse(any("USERDATA" in command for command in commands))
        self.assertFalse(any("Bearer" in command for command in commands))

    def test_http_get_sequence_can_include_cid_for_comparison(self) -> None:
        steps = diag_lte_http_at.build_http_get_steps(
            "http://example.test/health",
            include_cid=True,
            action_timeout_sec=10,
        )

        self.assertIn('AT+HTTPPARA="CID",1', [item.command for item in steps])

    def test_unauth_post_sequence_uses_httpdata_without_token(self) -> None:
        steps = diag_lte_http_at.build_http_steps(
            "http://203.0.113.10:8790/api/v1/devices/ego-link-r1-connectivity-001/telemetry",
            mode="telemetry-post-unauth",
            device_id="ego-link-r1-connectivity-001",
            bearer_token=None,
            include_cid=False,
            payload_padding_bytes=0,
            action_timeout_sec=60,
        )
        commands = [item.command for item in steps]
        http_data = next(item for item in steps if item.label == "HTTPDATA")

        self.assertIn('AT+HTTPPARA="CONTENT","application/json"', commands)
        self.assertTrue(http_data.command.startswith("AT+HTTPDATA="))
        self.assertIsNotNone(http_data.data)
        self.assertIn('"event_type":"lte_http_at_diag"', http_data.data or "")
        self.assertFalse(any("USERDATA" in command for command in commands))
        self.assertFalse(any("Bearer" in item.command or "Bearer" in (item.data or "") for item in steps))

    def test_auth_post_sequence_redacts_token_command(self) -> None:
        steps = diag_lte_http_at.build_http_steps(
            "http://203.0.113.10:8790/api/v1/devices/ego-link-r0-lte002-atdiag/telemetry",
            mode="telemetry-post-auth",
            device_id="ego-link-r0-lte002-atdiag",
            bearer_token="secret-token",
            include_cid=False,
            payload_padding_bytes=0,
            action_timeout_sec=60,
        )
        userdata = next(item for item in steps if item.label == "HTTPPARA_USERDATA")

        self.assertEqual(userdata.command, "__EGOLINK_AUTH_USERDATA__")
        self.assertIn("[REDACTED_SECRET]", userdata.log_command or "")
        self.assertNotIn("secret-token", userdata.command + (userdata.log_command or ""))

    def test_post_sequence_can_add_padding_to_exercise_larger_payloads(self) -> None:
        steps = diag_lte_http_at.build_http_steps(
            "http://203.0.113.10:8790/api/v1/devices/ego-link-r0-lte002-atdiag/telemetry",
            mode="telemetry-post-auth",
            device_id="ego-link-r0-lte002-atdiag",
            bearer_token="secret-token",
            include_cid=False,
            payload_padding_bytes=128,
            action_timeout_sec=60,
        )
        http_data = next(item for item in steps if item.label == "HTTPDATA")

        self.assertIn('"padding":"', http_data.data or "")
        self.assertGreater(len(http_data.data or ""), 300)

    def test_parse_status_probe_reports_lte_ready(self) -> None:
        parsed = diag_lte_http_at.parse_status_probe(
            {
                "port": "COM6",
                "ok": True,
                "responses": [
                    {"label": "AT", "response": "AT\r\r\nOK\r\n"},
                    {
                        "label": "ATI",
                        "response": (
                            "Manufacturer: SIMCOM INCORPORATED\r\n"
                            "Model: SIM7670G-MNGV\r\n"
                            "Revision: V1.9.05\r\nOK\r\n"
                        ),
                    },
                    {"label": "CPIN", "response": "+CPIN: READY\r\nOK\r\n"},
                    {"label": "CEREG", "response": "+CEREG: 0,1\r\nOK\r\n"},
                    {"label": "CGATT", "response": "+CGATT: 1\r\nOK\r\n"},
                    {"label": "CGACT", "response": "+CGACT: 1,1\r\nOK\r\n"},
                    {"label": "CGPADDR", "response": "+CGPADDR: 1,10.1.2.3\r\nOK\r\n"},
                    {"label": "CSQ", "response": "+CSQ: 21,0\r\nOK\r\n"},
                ],
            }
        )

        self.assertTrue(parsed["is_sim7670g"])
        self.assertTrue(parsed["lte_ready"])
        self.assertEqual(parsed["assigned_ip"], "10.1.2.3")

    def test_parse_http_probe_accepts_health_get_success(self) -> None:
        parsed = diag_lte_http_at.parse_http_probe(
            {
                "port": "COM6",
                "ok": True,
                "responses": [
                    {"label": "AT", "response": "OK\r\n"},
                    {"label": "HTTPINIT", "response": "OK\r\n"},
                    {"label": "HTTPPARA_URL", "response": "OK\r\n"},
                    {"label": "HTTPACTION_GET", "response": "OK\r\n+HTTPACTION: 0,200,12\r\n"},
                    {"label": "HTTPREAD", "response": '+HTTPREAD: 12\r\n{"ok":true}\r\nOK\r\n'},
                ],
            }
        )

        self.assertEqual(parsed["reason_code"], "LTE_HTTP_OK")
        self.assertEqual(parsed["status_code"], 200)
        self.assertTrue(parsed["health_ok"])

    def test_parse_http_probe_accepts_unauth_post_auth_gate(self) -> None:
        parsed = diag_lte_http_at.parse_http_probe(
            {
                "port": "COM6",
                "ok": True,
                "responses": [
                    {"label": "AT", "response": "OK\r\n"},
                    {"label": "HTTPINIT", "response": "OK\r\n"},
                    {"label": "HTTPPARA_URL", "response": "OK\r\n"},
                    {"label": "HTTPPARA_CONTENT", "response": "OK\r\n"},
                    {"label": "HTTPPARA_USERDATA", "response": "OK\r\n"},
                    {"label": "HTTPDATA", "response": "DOWNLOAD\r\nOK\r\n"},
                    {"label": "HTTPACTION_POST", "response": "OK\r\n+HTTPACTION: 1,401,24\r\n"},
                ],
            },
            mode="telemetry-post-unauth",
        )

        self.assertEqual(parsed["reason_code"], "LTE_HTTP_AUTH_GATE_REACHED")
        self.assertEqual(parsed["status_code"], 401)

    def test_parse_http_probe_accepts_auth_post_success(self) -> None:
        parsed = diag_lte_http_at.parse_http_probe(
            {
                "port": "COM6",
                "ok": True,
                "responses": [
                    {"label": "AT", "response": "OK\r\n"},
                    {"label": "HTTPINIT", "response": "OK\r\n"},
                    {"label": "HTTPPARA_URL", "response": "OK\r\n"},
                    {"label": "HTTPPARA_CONTENT", "response": "OK\r\n"},
                    {"label": "HTTPPARA_USERDATA", "response": "OK\r\n"},
                    {"label": "HTTPDATA", "response": "DOWNLOAD\r\nOK\r\n"},
                    {"label": "HTTPACTION_POST", "response": "OK\r\n+HTTPACTION: 1,200,468\r\n"},
                ],
            },
            mode="telemetry-post-auth",
        )

        self.assertEqual(parsed["reason_code"], "LTE_HTTP_OK")
        self.assertEqual(parsed["status_code"], 200)

    def test_parse_http_probe_identifies_missing_action(self) -> None:
        parsed = diag_lte_http_at.parse_http_probe(
            {
                "port": "COM6",
                "ok": True,
                "responses": [
                    {"label": "AT", "response": "OK\r\n"},
                    {"label": "HTTPINIT", "response": "OK\r\n"},
                    {"label": "HTTPPARA_URL", "response": "OK\r\n"},
                    {"label": "HTTPACTION_GET", "response": "OK\r\n"},
                ],
            }
        )

        self.assertEqual(parsed["reason_code"], "LTE_HTTP_ACTION_FAILED")

    def test_markdown_redacts_bearer_like_strings(self) -> None:
        self.assertIn(
            "Bearer [REDACTED_SECRET]",
            diag_lte_http_at.redact_sensitive("Authorization: Bearer secret-token"),
        )
        self.assertEqual(
            'AT+HTTPPARA="USERDATA","Authorization: Bearer [REDACTED_SECRET]"',
            diag_lte_http_at.redact_sensitive(
                'AT+HTTPPARA="USERDATA","Authorization: Bearer [REDACTED_SECRET]suffix"'
            ),
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import diag_lte_http_at
from scripts.egolink_board_probe import SerialPortInfo


TLS_CAPABILITY_PRESENT_FIXTURE = {
    "port": "COM_TEST",
    "ok": True,
    "error": None,
    "responses": [
        {
            "label": "ATI",
            "response": "Manufacturer: SIMCOM INCORPORATED\r\nModel: SIM7670G-MNGV\r\nRevision: V1.9.05\r\nOK\r\n",
        },
        {"label": "CGMR", "response": "V1.9.05\r\nOK\r\n"},
        {
            "label": "CSSLCFG_TEST",
            "response": (
                '+CSSLCFG: "authmode",(0-9),(0-2)\r\n'
                '+CSSLCFG: "cacert",(0-9),(5-108)\r\n'
                '+CSSLCFG: "enableSNI",(0-9),(0,1)\r\n'
                '+CSSLCFG: "ignorecertCN",(0-9),(0,1)\r\n'
                '+CSSLCFG: "ignorelocaltime",(0-9),(0,1)\r\nOK\r\n'
            ),
        },
        {"label": "CSSLCFG_READ", "response": "+CSSLCFG: 0,3,2\r\nOK\r\n"},
        {"label": "CCERTDOWN_TEST", "response": "+CCERTDOWN: (1-64),(1-10240)\r\nOK\r\n"},
        {"label": "CCERTLIST", "response": '+CCERTLIST: "private-client.crt"\r\nOK\r\n'},
        {"label": "CCLK_READ", "response": '+CCLK: "26/09/02,13:45:10+32"\r\nOK\r\n'},
    ],
}


class LteHttpAtDiagTests(unittest.TestCase):
    def test_http_get_sequence_uses_public_health_without_token_or_cid_by_default(self) -> None:
        steps = diag_lte_http_at.build_http_get_steps(
            "https://ego.example.invalid/health",
            include_cid=False,
            action_timeout_sec=60,
        )
        commands = [item.command for item in steps]

        self.assertIn('AT+HTTPPARA="URL","https://ego.example.invalid/health"', commands)
        self.assertIn("AT+HTTPACTION=0", commands)
        self.assertNotIn('AT+HTTPPARA="CID",1', commands)
        self.assertFalse(any("USERDATA" in command for command in commands))
        self.assertFalse(any("Bearer" in command for command in commands))

    def test_http_get_sequence_can_include_cid_for_comparison(self) -> None:
        steps = diag_lte_http_at.build_http_get_steps(
            "https://example.test/health",
            include_cid=True,
            action_timeout_sec=10,
        )

        self.assertIn('AT+HTTPPARA="CID",1', [item.command for item in steps])

    def test_unauth_post_sequence_uses_httpdata_without_token(self) -> None:
        steps = diag_lte_http_at.build_http_steps(
            "https://ego.example.invalid/api/v1/devices/ego-link-r1-connectivity-001/telemetry",
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
            "https://ego.example.invalid/api/v1/devices/ego-link-r0-lte002-atdiag/telemetry",
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
            "https://ego.example.invalid/api/v1/devices/ego-link-r0-lte002-atdiag/telemetry",
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
        redacted = diag_lte_http_at.redact_sensitive(
            "https://user:password@example.test/health?access_token=top-secret&api_key=also-secret"
        )
        self.assertNotIn("password", redacted)
        self.assertNotIn("top-secret", redacted)
        self.assertNotIn("also-secret", redacted)

    def test_target_url_requires_exact_https_host(self) -> None:
        transport = diag_lte_http_at.validate_ingress_url(
            "https://ego.example.invalid/health",
            mode="health-get",
        )

        self.assertEqual(transport["scheme"], "https")
        self.assertFalse(transport["production_acceptable"])
        with self.assertRaisesRegex(ValueError, "plaintext ingress is disabled"):
            diag_lte_http_at.validate_ingress_url(
                "http://ego.example.invalid/health",
                mode="health-get",
            )
        with self.assertRaisesRegex(ValueError, "does not match"):
            diag_lte_http_at.validate_ingress_url(
                "https://evil.example/health",
                mode="health-get",
            )
        with self.assertRaisesRegex(ValueError, "must not contain credentials"):
            diag_lte_http_at.validate_ingress_url(
                "https://user:secret@ego.example.invalid/health",
                mode="health-get",
            )

    def test_plaintext_fallback_is_expiring_health_only(self) -> None:
        now = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
        expires = (now + timedelta(minutes=30)).isoformat()
        transport = diag_lte_http_at.validate_ingress_url(
            "http://ego.example.invalid/health",
            mode="health-get",
            allow_plaintext_engineering=True,
            plaintext_expires_at_utc=expires,
            now=now,
        )

        self.assertTrue(transport["plaintext_fallback"])
        self.assertFalse(transport["production_acceptable"])
        with self.assertRaisesRegex(ValueError, "limited to credential-free"):
            diag_lte_http_at.validate_ingress_url(
                "http://ego.example.invalid/api/v1/devices/device/telemetry",
                mode="telemetry-post-unauth",
                allow_plaintext_engineering=True,
                plaintext_expires_at_utc=expires,
                now=now,
            )
        with self.assertRaisesRegex(ValueError, "within the next 3600"):
            diag_lte_http_at.validate_ingress_url(
                "http://ego.example.invalid/health",
                mode="health-get",
                allow_plaintext_engineering=True,
                plaintext_expires_at_utc=(now + timedelta(hours=2)).isoformat(),
                now=now,
            )

    def test_authenticated_modem_post_stays_disabled_without_peer_verification(self) -> None:
        with self.assertRaisesRegex(ValueError, "certificate-chain and hostname verification"):
            diag_lte_http_at.validate_ingress_url(
                "https://ego.example.invalid/api/v1/devices/device/telemetry",
                mode="telemetry-post-auth",
            )

    def test_token_file_load_is_bounded_and_not_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "token.txt"
            token_path.write_bytes(b"x" * (diag_lte_http_at.MAX_BEARER_TOKEN_BYTES + 2))
            with self.assertRaisesRegex(SystemExit, "exceeds the bounded token size"):
                diag_lte_http_at.load_bearer_token("EGOLINK_TEST_TOKEN_MISSING", token_path)

    def test_tls_capability_steps_match_exact_query_only_allowlist(self) -> None:
        steps = diag_lte_http_at.build_tls_capability_steps()

        self.assertEqual(
            tuple(step.command for step in steps),
            diag_lte_http_at.TLS_CAPABILITY_COMMANDS,
        )
        self.assertTrue(all(step.data is None for step in steps))
        self.assertFalse(any("HTTP" in step.command for step in steps))
        self.assertFalse(any(step.command.startswith("AT+CSSLCFG=\"") for step in steps))
        self.assertFalse(any(step.command.startswith("AT+CCERTDOWN=\"") for step in steps))

    def test_tls_capability_low_level_allowlist_rejects_writes_traffic_and_data(self) -> None:
        unsafe_steps = (
            diag_lte_http_at.AtStep("AT+HTTPACTION=0", "HTTP"),
            diag_lte_http_at.AtStep('AT+CSSLCFG="authmode",0,1', "WRITE"),
            diag_lte_http_at.AtStep('AT+CCERTDOWN="ca.pem",100', "UPLOAD"),
        )
        for step in unsafe_steps:
            with self.subTest(command=step.command):
                with self.assertRaisesRegex(ValueError, "outside the supplied allowlist"):
                    diag_lte_http_at.run_at_sequence(
                        "COM_TEST",
                        [step],
                        timeout_seconds=1,
                        command_allowlist=diag_lte_http_at.TLS_CAPABILITY_COMMAND_ALLOWLIST,
                    )
        with self.assertRaisesRegex(ValueError, "cannot send data"):
            diag_lte_http_at.run_at_sequence(
                "COM_TEST",
                [diag_lte_http_at.AtStep("ATI", "ATI", data="payload")],
                timeout_seconds=1,
                command_allowlist=diag_lte_http_at.TLS_CAPABILITY_COMMAND_ALLOWLIST,
            )
        with self.assertRaisesRegex(ValueError, "cannot receive an auth header"):
            diag_lte_http_at.run_at_sequence(
                "COM_TEST",
                [diag_lte_http_at.AtStep("ATI", "ATI")],
                timeout_seconds=1,
                auth_header="Authorization: Bearer forbidden",
                command_allowlist=diag_lte_http_at.TLS_CAPABILITY_COMMAND_ALLOWLIST,
            )

    def test_tls_capability_parser_reports_present_without_raw_certificate_name(self) -> None:
        parsed = diag_lte_http_at.parse_tls_capability_probe(TLS_CAPABILITY_PRESENT_FIXTURE)

        self.assertEqual(parsed["capability"], "present")
        self.assertEqual(parsed["model"], "SIM7670G-MNGV")
        self.assertEqual(parsed["revision"], "V1.9.05")
        self.assertEqual(parsed["missing_or_unadvertised"], [])
        self.assertTrue(parsed["clock_shape_recognized"])
        self.assertFalse(parsed["raw_responses_persisted"])
        self.assertNotIn("private-client.crt", str(parsed))

    def test_tls_capability_parser_reports_missing_option(self) -> None:
        fixture = {
            **TLS_CAPABILITY_PRESENT_FIXTURE,
            "responses": [
                {
                    **item,
                    "response": item["response"].replace(
                        '+CSSLCFG: "ignorecertCN",(0-9),(0,1)\r\n', ""
                    ),
                }
                for item in TLS_CAPABILITY_PRESENT_FIXTURE["responses"]
            ],
        }

        parsed = diag_lte_http_at.parse_tls_capability_probe(fixture)

        self.assertEqual(parsed["capability"], "missing")
        self.assertIn("ignorecertcn", parsed["missing_or_unadvertised"])

    def test_tls_capability_diagnostic_never_dispatches_network_or_write_commands(self) -> None:
        port = SerialPortInfo(
            port="COM_TEST",
            name="SIM AT",
            description="fixture",
            pnp_device_id="fixture",
            role="sim_at",
        )
        dispatched: list[diag_lte_http_at.AtStep] = []

        def fake_run_at_sequence(
            selected_port: str,
            steps: object,
            *,
            timeout_seconds: int,
            auth_header: str | None = None,
            command_allowlist: frozenset[str] | None = None,
        ) -> dict[str, object]:
            del timeout_seconds
            dispatched.extend(list(steps))  # type: ignore[arg-type]
            self.assertEqual(selected_port, "COM_TEST")
            self.assertIsNone(auth_header)
            self.assertEqual(command_allowlist, diag_lte_http_at.TLS_CAPABILITY_COMMAND_ALLOWLIST)
            return TLS_CAPABILITY_PRESENT_FIXTURE

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(diag_lte_http_at, "discover_serial_ports", return_value=[port]),
                patch.object(diag_lte_http_at, "choose_sim_ports", return_value=[port]),
                patch.object(diag_lte_http_at, "run_at_sequence", side_effect=fake_run_at_sequence),
            ):
                report = diag_lte_http_at.run_tls_capability_diagnostic(
                    sim_ports=[],
                    probe_all_sim_ports=False,
                    output_dir=Path(temp_dir),
                )

        commands = [step.command for step in dispatched]
        self.assertEqual(tuple(commands), diag_lte_http_at.TLS_CAPABILITY_COMMANDS)
        self.assertFalse(any("HTTP" in command for command in commands))
        self.assertFalse(any(command.startswith("AT+NET") or command.startswith("AT+CNACT") for command in commands))
        self.assertFalse(any(command.startswith("AT+CGACT") or command.startswith("AT+CGATT") for command in commands))
        self.assertFalse(any(step.data for step in dispatched))
        self.assertEqual(report["summary"]["classification"], "capability-present")
        self.assertEqual(report["exact_firmware"]["status"], "unverified")
        self.assertEqual(report["negative_behavior"]["status"], "unverified")
        self.assertFalse(report["probe_contract"]["network_traffic"])
        self.assertFalse(report["probe_contract"]["token_or_payload_access"])
        self.assertNotIn("private-client.crt", str(report))


if __name__ == "__main__":
    unittest.main()

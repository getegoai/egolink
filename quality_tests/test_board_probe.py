from __future__ import annotations

import unittest

from scripts.egolink_board_probe import (
    classify_serial_port,
    is_rndis_adapter,
    parse_com_port,
    parse_esp_log,
    parse_sim_probe,
    serial_rows_to_port_infos,
)


class BoardProbeParsingTests(unittest.TestCase):
    def test_classifies_esp32_ch343_port(self) -> None:
        info = classify_serial_port(
            {
                "DeviceID": "COM4",
                "Name": "USB-Enhanced-SERIAL CH343 (COM4)",
                "Description": "USB-Enhanced-SERIAL CH343",
                "PNPDeviceID": r"USB\VID_1A86&PID_55D3\5B91047400",
            }
        )

        self.assertEqual(info.role, "esp32_s3_ch343")

    def test_classifies_pnp_only_ch343_port(self) -> None:
        info = classify_serial_port(
            {
                "DeviceID": "",
                "Name": "USB-Enhanced-SERIAL CH343 (COM4)",
                "Description": "USB-Enhanced-SERIAL CH343 (COM4)",
                "PNPDeviceID": r"USB\VID_1A86&PID_55D3\5B91047400",
            }
        )

        self.assertEqual(info.port, "COM4")
        self.assertEqual(info.role, "esp32_s3_ch343")

    def test_serial_rows_to_port_infos_deduplicates_cim_and_pnp(self) -> None:
        rows = [
            {
                "DeviceID": "COM4",
                "Name": "USB-Enhanced-SERIAL CH343 (COM4)",
                "Description": "USB-Enhanced-SERIAL CH343",
                "PNPDeviceID": r"USB\VID_1A86&PID_55D3\5B91047400",
            },
            {
                "DeviceID": "",
                "Name": "USB-Enhanced-SERIAL CH343 (COM4)",
                "Description": "USB-Enhanced-SERIAL CH343 (COM4)",
                "PNPDeviceID": r"USB\VID_1A86&PID_55D3\5B91047400",
            },
        ]

        infos = serial_rows_to_port_infos(rows)

        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].port, "COM4")

    def test_parse_com_port_from_friendly_name(self) -> None:
        self.assertEqual(parse_com_port("USB-Enhanced-SERIAL CH343 (COM4)"), "COM4")
        self.assertIsNone(parse_com_port("USB Composite Device"))

    def test_detects_remote_ndis_adapter(self) -> None:
        self.assertTrue(
            is_rndis_adapter(
                {
                    "Name": "以太网 2",
                    "InterfaceDescription": "Remote NDIS based Internet Sharing Device",
                }
            )
        )

    def test_classifies_sim7670_at_candidate(self) -> None:
        info = classify_serial_port(
            {
                "DeviceID": "COM6",
                "Name": "USB 串行设备 (COM6)",
                "Description": "USB 串行设备",
                "PNPDeviceID": r"USB\VID_05C6&PID_9330&MI_02\7&ABC&0&0002",
            }
        )

        self.assertEqual(info.role, "sim7670_at_candidate")
        self.assertEqual(info.usb_mi, "02")

    def test_parses_sim7670_identity_and_missing_sim(self) -> None:
        parsed = parse_sim_probe(
            {
                "probe": {
                    "port": "COM6",
                    "ok": True,
                    "responses": [
                        {
                            "command": "ATI",
                            "response": (
                                "Manufacturer: SIMCOM INCORPORATED\r\n"
                                "Model: SIM7670G-MNGV\r\n"
                                "Revision: V1.9.05\r\n"
                                "IMEI: 864643061175164\r\nOK\r\n"
                            ),
                        },
                        {"command": "AT+CPIN?", "response": "+CME ERROR: SIM not inserted\r\n"},
                        {"command": "AT+CSQ", "response": "+CSQ: 25,99\r\nOK\r\n"},
                    ],
                }
            }
        )

        self.assertTrue(parsed["is_sim7670g"])
        self.assertTrue(parsed["sim_not_inserted"])
        self.assertEqual(parsed["csq"], "25,99")
        self.assertTrue(parsed["imei_present"])

    def test_parses_esp_sd_failure_log(self) -> None:
        parsed = parse_esp_log(
            "ESP-ROM:esp32s3-20210327\r\n"
            "Camera init successful\r\n"
            "ERROR: Card Mount Failed\r\n"
        )

        self.assertTrue(parsed["boot_rom_seen"])
        self.assertTrue(parsed["camera_init_ok"])
        self.assertTrue(parsed["sd_mount_failed"])
        self.assertFalse(parsed["sd_mount_ok"])


if __name__ == "__main__":
    unittest.main()

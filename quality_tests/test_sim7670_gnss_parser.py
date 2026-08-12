from __future__ import annotations

import unittest

from scripts import sim7670_gnss_probe as gnss


class Sim7670GnssCoordinateParserTests(unittest.TestCase):
    def test_cgnss_decimal_degrees_primary_layout(self) -> None:
        fix = gnss.parse_cgnssinfo(
            "+CGNSSINFO:3,10,04,00,00,35.123456,N,110.654321,E,120826,123456.00,50.0,1.0,90.0,1.5,0.9,1.1,10"
        )

        self.assertTrue(fix.fix)
        self.assertEqual(fix.lat, 35.123456)
        self.assertEqual(fix.lon, 110.654321)
        self.assertEqual(fix.altitude_m, 50.0)
        self.assertEqual(fix.satellites, 10)

    def test_cgnss_decimal_degrees_alternate_layout_uses_dynamic_tail(self) -> None:
        fix = gnss.parse_cgnssinfo(
            "+CGNSSINFO:2,08,03,00,12.345678,S,45.678901,W,120826,102030.00,60.5,2.0,180.0,1.8,1.0,1.2,8"
        )

        self.assertTrue(fix.fix)
        self.assertEqual(fix.lat, -12.345678)
        self.assertEqual(fix.lon, -45.678901)
        self.assertEqual(fix.utc_date, "120826")
        self.assertEqual(fix.utc_time, "102030.00")
        self.assertEqual(fix.altitude_m, 60.5)
        self.assertEqual(fix.hdop, 1.0)
        self.assertEqual(fix.satellites, 8)

    def test_cgnss_legacy_ddmm_pair_is_supported(self) -> None:
        fix = gnss.parse_cgnssinfo(
            "+CGNSSINFO:2,09,05,00,00,3512.000000,N,11030.000000,E,120826,123456.00,10.0,0.0,0.0,1.1,0.8,0.7,9"
        )

        self.assertTrue(fix.fix)
        self.assertEqual(fix.lat, 35.2)
        self.assertEqual(fix.lon, 110.5)

    def test_cgps_is_always_ddmm_even_when_raw_values_fit_decimal_ranges(self) -> None:
        fix = gnss.parse_cgpsinfo(
            "+CGPSINFO:35.500000,N,110.500000,E,120826,123456.00,12.0,0.0,0.0"
        )

        self.assertTrue(fix.fix)
        self.assertEqual(fix.lat, 0.591667)
        self.assertEqual(fix.lon, 1.175)

    def test_cgnss_rejects_non_fix_mode(self) -> None:
        for mode in ("0", "1", "4", ""):
            with self.subTest(mode=mode):
                fix = gnss.parse_cgnssinfo(
                    f"+CGNSSINFO:{mode},10,04,00,00,35.123456,N,110.654321,E,120826,123456.00,50.0,1.0,90.0,1.5,0.9,1.1,10"
                )
                self.assertFalse(fix.fix)

    def test_invalid_coordinates_do_not_leak_quality_metadata(self) -> None:
        fix = gnss.parse_cgnssinfo(
            "+CGNSSINFO:3,10,04,00,00,3560.000000,N,11030.000000,E,120826,123456.00,50.0,1.0,90.0,1.5,0.9,1.1,10"
        )

        self.assertFalse(fix.fix)
        self.assertIsNone(fix.lat)
        self.assertIsNone(fix.hdop)
        self.assertIsNone(fix.satellites)

    def test_coordinate_pair_rejects_invalid_values(self) -> None:
        invalid_pairs = (
            ("3560.0", "N", "11030.0", "E", "ddmm"),
            ("35.0", "E", "110.0", "E", "cgnss_auto"),
            ("35.0", "N", "110.0", "N", "cgnss_auto"),
            ("nan", "N", "110.0", "E", "cgnss_auto"),
            ("1e100", "N", "110.0", "E", "ddmm"),
            ("35.0junk", "N", "110.0", "E", "cgnss_auto"),
            ("35.0", "N", "11065.0", "E", "cgnss_auto"),
        )
        for latitude, ns, longitude, ew, coordinate_format in invalid_pairs:
            with self.subTest(latitude=latitude, longitude=longitude):
                self.assertEqual(
                    gnss.parse_coordinate_pair(
                        latitude,
                        ns,
                        longitude,
                        ew,
                        coordinate_format=coordinate_format,
                    ),
                    (None, None),
                )

    def test_coordinate_boundaries_are_accepted(self) -> None:
        self.assertEqual(
            gnss.parse_coordinate_pair(
                "90.0", "N", "180.0", "E", coordinate_format="cgnss_auto"
            ),
            (90.0, 180.0),
        )
        self.assertEqual(
            gnss.parse_coordinate_pair(
                "9000.0", "S", "18000.0", "W", coordinate_format="ddmm"
            ),
            (-90.0, -180.0),
        )


class Sim7670AtResponseCompletionTests(unittest.TestCase):
    def test_expected_line_and_ok_are_both_required(self) -> None:
        expected = "+CGNSSINFO:"
        self.assertFalse(gnss.at_response_complete("+CGNSSINFO:3,10", expected))
        self.assertFalse(gnss.at_response_complete("+CGNSSINFO:3,10\r\n", expected))
        self.assertFalse(gnss.at_response_complete("OK\r\n", expected))
        self.assertFalse(gnss.at_response_complete("BROKENOK\r\n+CGNSSINFO:3,10\r\n", expected))
        self.assertTrue(gnss.at_response_complete("+CGNSSINFO:3,10\r\nOK\r\n", expected))

    def test_async_result_can_arrive_after_ok(self) -> None:
        response = "AT+HTTPACTION=1\r\nOK\r\n\r\n+HTTPACTION: 1,200,42\r\n"

        self.assertTrue(gnss.at_response_complete(response, "+HTTPACTION:"))

    def test_error_result_wins_over_ok_and_expected_line(self) -> None:
        for error in ("ERROR", "+CME ERROR: 30", "+CMS ERROR: 500"):
            with self.subTest(error=error):
                response = f"OK\r\n+CGNSSINFO:3,10\r\n{error}\r\n"
                self.assertFalse(gnss.at_response_complete(response, "+CGNSSINFO:"))

    def test_incomplete_gnss_transcript_is_not_parsed(self) -> None:
        line = "+CGNSSINFO:3,10,04,00,00,35.123456,N,110.654321,E,120826,123456.00,50.0,1.0,90.0,1.5,0.9,1.1,10"

        incomplete = gnss.parse_gnss_responses(
            [{"command": "AT+CGNSSINFO", "response": f"{line}\r\n"}]
        )
        complete = gnss.parse_gnss_responses(
            [{"command": "AT+CGNSSINFO", "response": f"{line}\r\nOK\r\n"}]
        )

        self.assertFalse(incomplete.fix)
        self.assertTrue(complete.fix)

    def test_uart_sized_chunks_only_complete_after_quality_tail_and_ok(self) -> None:
        line = "+CGNSSINFO:3,10,04,00,00,35.123456,N,110.654321,E,120826,123456.00,50.0,1.0,90.0,1.5,0.9,1.1,10"
        transcript = f"{line}\r\nOK\r\n"
        chunks = [transcript[index : index + 96] for index in range(0, len(transcript), 96)]
        accumulated = ""

        for chunk in chunks[:-1]:
            accumulated += chunk
            self.assertFalse(gnss.at_response_complete(accumulated, "+CGNSSINFO:"))

        accumulated += chunks[-1]
        self.assertTrue(gnss.at_response_complete(accumulated, "+CGNSSINFO:"))
        fix = gnss.parse_gnss_responses(
            [{"command": "AT+CGNSSINFO", "response": accumulated}]
        )
        self.assertTrue(fix.fix)
        self.assertEqual(fix.pdop, 1.5)
        self.assertEqual(fix.hdop, 0.9)
        self.assertEqual(fix.vdop, 1.1)
        self.assertEqual(fix.satellites, 10)

    def test_terminated_gnss_lines_without_full_tail_are_rejected(self) -> None:
        cgnss = "+CGNSSINFO:3,10,04,00,00,35.123456,N,110.654321,E"
        cgps = "+CGPSINFO:3512.000000,N,11030.000000,E"

        for command, line in (("AT+CGNSSINFO", cgnss), ("AT+CGPSINFO", cgps)):
            with self.subTest(command=command):
                fix = gnss.parse_gnss_responses(
                    [{"command": command, "response": f"{line}\r\nOK\r\n"}]
                )
                self.assertFalse(fix.fix)

    def test_negative_satellite_count_is_not_exposed(self) -> None:
        line = "+CGNSSINFO:3,10,04,00,00,35.123456,N,110.654321,E,120826,123456.00,50.0,1.0,90.0,1.5,0.9,1.1,-1"
        fix = gnss.parse_gnss_responses(
            [{"command": "AT+CGNSSINFO", "response": f"{line}\r\nOK\r\n"}]
        )

        self.assertTrue(fix.fix)
        self.assertIsNone(fix.satellites)


if __name__ == "__main__":
    unittest.main()

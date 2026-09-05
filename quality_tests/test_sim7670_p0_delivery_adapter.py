"""Focused offline checks for OUTBOX-010G.

The native harnesses execute the pure C parser/validators and the adapter
against injected fakes. They do not open UART, a modem, a port, or a network.
The ESP-IDF build is separate compile/link evidence, not transport evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from quality_tests.test_p0_outbox_dispatcher import _location_envelope, _wire
from quality_tests.test_sos_orchestrator_firmware import _payload as _sos_payload
from server.location_delivery_ack import build_location_state_delivery_ack
from server.location_state_store import LocationStateStore
from server.manual_sos_delivery_ack import (
    DELIVERY_SCOPE,
    build_manual_sos_delivery_ack,
)
from server.manual_sos_store import ManualSosStore
from server.message_hub import dumps


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
SIM = COMPONENTS / "sim7670_gnss"
ADAPTER = COMPONENTS / "sim7670_p0_delivery_adapter"
SIM_SOURCE = SIM / "sim7670_gnss.c"
SIM_HEADER = SIM / "include" / "sim7670_gnss.h"
PARSER_SOURCE = SIM / "sim7670_http_exact_parser.c"
PARSER_HEADER = SIM / "sim7670_http_exact_parser.h"
ADAPTER_SOURCE = ADAPTER / "sim7670_p0_delivery_adapter.c"
ADAPTER_HEADER = ADAPTER / "include" / "sim7670_p0_delivery_adapter.h"
ADAPTER_KCONFIG = ADAPTER / "Kconfig.projbuild"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md"


def _native_tools() -> tuple[Path, Path] | None:
    root = Path("C:/Espressif/tools/esp-clang/esp-18.1.2_20240912/esp-clang/bin")
    clang = root / "clang.exe"
    linker = root / "lld.exe"
    if not clang.is_file() or not linker.is_file():
        return None
    probe = subprocess.run(
        [str(clang), "--print-targets"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return (clang, linker) if probe.returncode == 0 and "x86" in probe.stdout.casefold() else None


def _xtensa_compiler() -> Path | None:
    candidates = (
        os.environ.get("XTENSA_ESP32S3_GCC"),
        "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe",
    )
    return next((Path(value) for value in candidates if value and Path(value).is_file()), None)


def _function_body(source: str, name: str) -> str:
    start = source.index(name)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {name}")


PARSER_HARNESS = r"""
#include <stddef.h>
#include <stdint.h>
#include "sim7670_http_exact_parser.h"

void *memcpy(void *dst, const void *src, size_t count) {
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    while (count-- > 0U) { *d++ = *s++; }
    return dst;
}
int memcmp(const void *left, const void *right, size_t count) {
    const unsigned char *a = (const unsigned char *)left;
    const unsigned char *b = (const unsigned char *)right;
    while (count-- > 0U) { if (*a != *b) return (int)*a - (int)*b; ++a; ++b; }
    return 0;
}
int strcmp(const char *left, const char *right) {
    while (*left != '\0' && *left == *right) { ++left; ++right; }
    return (int)(unsigned char)*left - (int)(unsigned char)*right;
}

#define CHECK(value, code) do { if (!(value)) return (code); } while (0)
#define LABEL_8 "aaaaaaaa"
#define LABEL_16 LABEL_8 LABEL_8
#define LABEL_32 LABEL_16 LABEL_16
#define LABEL_63 LABEL_32 LABEL_16 LABEL_8 "aaaaaaa"
#define LABEL_64 LABEL_32 LABEL_32

int mainCRTStartup(void) {
    static const char *valid_urls[] = {
        "https://ego.example/api/v1/location-states",
        "https://ego.example/api/v1/safety-events/manual-sos",
        "https://" LABEL_63 ".example/api/v1/location-states"
    };
    static const char *invalid_urls[] = {
        "https:///api/v1/location-states",
        "http://ego.example/api/v1/location-states",
        "https://ego.example:443/api/v1/location-states",
        "https://u@ego.example/api/v1/location-states",
        "https://[::1]/api/v1/location-states",
        "https://127.0.0.1/api/v1/location-states",
        "https://" LABEL_64 ".example/api/v1/location-states",
        "https://ego..example/api/v1/location-states",
        "https://-ego.example/api/v1/location-states",
        "https://ego.example/other",
        "https://ego.example/api/v1/location-states?x=1"
    };
    for (size_t i = 0U; i < 3U; ++i) {
        CHECK(sim7670_http_exact_url_is_valid(valid_urls[i]) == 1, 10 + (int)i);
    }
    for (size_t i = 0U; i < 11U; ++i) {
        CHECK(sim7670_http_exact_url_is_valid(invalid_urls[i]) == 0, 20 + (int)i);
    }
    CHECK(
        sim7670_http_exact_https_origin_matches_dns_host(
            "https://ego.example", "ego.example") == 1,
        35);
    CHECK(
        sim7670_http_exact_https_origin_matches_dns_host(
            "https://127.0.0.1", "127.0.0.1") == 0,
        36);
    CHECK(
        sim7670_http_exact_https_origin_matches_dns_host(
            "https://" LABEL_64 ".example", LABEL_64 ".example") == 0,
        37);
    CHECK(sim7670_http_exact_bearer_is_valid("Abc_1-+/=") == 1, 31);
    CHECK(sim7670_http_exact_bearer_is_valid("<runtime-token>") == 0, 32);
    CHECK(sim7670_http_exact_bearer_is_valid("bad token") == 0, 33);
    CHECK(sim7670_http_exact_bearer_is_valid("bad\"token") == 0, 34);

    uint16_t status = 0U;
    size_t length = 0U;
    static const uint8_t action[] = "\r\n+HTTPACTION: 1,202,3\r\n";
    CHECK(sim7670_http_exact_parse_action(action, sizeof(action) - 1U, &status, &length) == 1, 40);
    CHECK(status == 202U && length == 3U, 41);
    static const uint8_t bad_method[] = "\r\n+HTTPACTION: 0,200,3\r\n";
    static const uint8_t bad_status[] = "\r\n+HTTPACTION: 1,600,3\r\n";
    static const uint8_t false_marker[] = "x+HTTPACTION: 1,200,3\r\n";
    static const uint8_t duplicate[] = "\r\n+HTTPACTION: 1,200,3\r\n+HTTPACTION: 1,200,3\r\n";
    static const uint8_t terminal[] = "\r\nERROR\r\n+HTTPACTION: 1,200,3\r\n";
    CHECK(sim7670_http_exact_parse_action(bad_method, sizeof(bad_method) - 1U, &status, &length) == 0, 42);
    CHECK(sim7670_http_exact_parse_action(bad_status, sizeof(bad_status) - 1U, &status, &length) == 0, 43);
    CHECK(sim7670_http_exact_parse_action(false_marker, sizeof(false_marker) - 1U, &status, &length) == 0, 44);
    CHECK(sim7670_http_exact_parse_action(duplicate, sizeof(duplicate) - 1U, &status, &length) == 0, 45);
    CHECK(sim7670_http_exact_parse_action(terminal, sizeof(terminal) - 1U, &status, &length) == 0, 46);

    static const uint8_t wire[] = {'\r','\n','+','H','T','T','P','R','E','A','D',':',' ','3','\r','\n','A',0U,'B','\r','\n','O','K','\r','\n'};
    uint8_t body[4] = {0xa5U, 0xa5U, 0xa5U, 0xa5U};
    size_t body_length = 99U;
    CHECK(sim7670_http_exact_extract_body(wire, sizeof(wire) - 1U, 3U, body, sizeof(body), &body_length) == SIM7670_HTTP_EXACT_PARSE_NEED_MORE, 50);
    CHECK(body_length == 0U && body[0] == 0xa5U, 51);
    CHECK(sim7670_http_exact_extract_body(wire, sizeof(wire), 3U, body, sizeof(body), &body_length) == SIM7670_HTTP_EXACT_PARSE_COMPLETE, 52);
    CHECK(body_length == 3U && body[0] == 'A' && body[1] == 0U && body[2] == 'B', 53);
    CHECK(sim7670_http_exact_extract_body(wire, sizeof(wire), 2U, body, sizeof(body), &body_length) == SIM7670_HTTP_EXACT_PARSE_INVALID, 54);
    return 0;
}
"""


ADAPTER_HARNESS = r"""
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "sim7670_p0_delivery_adapter.h"

void *memset(void *dst, int value, size_t count) { unsigned char *d=(unsigned char *)dst; while(count-- > 0U) *d++=(unsigned char)value; return dst; }
void *memcpy(void *dst, const void *src, size_t count) { unsigned char *d=(unsigned char *)dst; const unsigned char *s=(const unsigned char *)src; while(count-- > 0U) *d++=*s++; return dst; }
int memcmp(const void *left, const void *right, size_t count) { const unsigned char *a=(const unsigned char *)left; const unsigned char *b=(const unsigned char *)right; while(count-- > 0U){if(*a!=*b)return (int)*a-(int)*b;++a;++b;} return 0; }
int strcmp(const char *left, const char *right) { while(*left!='\0'&&*left==*right){++left;++right;} return (int)(unsigned char)*left-(int)(unsigned char)*right; }
int strncmp(const char *left, const char *right, size_t count) { while(count>0U&&*left!='\0'&&*left==*right){--count;++left;++right;} return count==0U?0:(int)(unsigned char)*left-(int)(unsigned char)*right; }
size_t strlen(const char *value) { size_t n=0U; while(value[n]!='\0')++n; return n; }

static uint8_t response[EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES];
static const uint8_t payload[] = {'A', 0U, 'B'};
static uint64_t clock_values[4];
static size_t clock_index;
static unsigned int fake_mode;
static unsigned int fake_calls;
static unsigned int cancel_calls;
static uint8_t cancel_cookie;
#define CHECK(value, code) do { if (!(value)) return (code); } while (0)
#define LABEL_8 "aaaaaaaa"
#define LABEL_16 LABEL_8 LABEL_8
#define LABEL_32 LABEL_16 LABEL_16
#define LABEL_63 LABEL_32 LABEL_16 LABEL_8 "aaaaaaa"
#define LABEL_64 LABEL_32 LABEL_32

void sim7670_lte_http_exact_result_init(sim7670_lte_http_exact_result_t *result) {
    if (result != NULL) { (void)memset(result, 0, sizeof(*result)); result->status = SIM7670_LTE_HTTP_EXACT_INVALID_ARGUMENT; }
}
sim7670_lte_http_exact_status_t sim7670_lte_http_post_bytes_exact(const sim7670_lte_http_exact_request_t *request, sim7670_lte_http_exact_result_t *result) {
    (void)request; sim7670_lte_http_exact_result_init(result); result->status=SIM7670_LTE_HTTP_EXACT_TLS_PROFILE_UNVERIFIED; return result->status;
}
static uint64_t now_ms(void *context) { (void)context; return clock_values[clock_index++]; }
static bool cancel_probe(void *context, uint32_t transfer_generation) {
    ++cancel_calls; return context == &cancel_cookie && transfer_generation == 77U;
}
static sim7670_lte_http_exact_status_t fake_post(void *context, const sim7670_lte_http_exact_request_t *request, sim7670_lte_http_exact_result_t *result) {
    (void)context; ++fake_calls; sim7670_lte_http_exact_result_init(result);
    if (request->payload_length != sizeof(payload) || memcmp(request->payload, payload, sizeof(payload)) != 0) return SIM7670_LTE_HTTP_EXACT_INVALID_ARGUMENT;
    if (strcmp(request->url, "https://ego.example/api/v1/safety-events/manual-sos") != 0) return SIM7670_LTE_HTTP_EXACT_INVALID_CONFIG;
    if (request->cancel_requested == NULL || request->cancel_context != &cancel_cookie || request->transfer_generation != 77U || !request->cancel_requested(request->cancel_context, request->transfer_generation)) return SIM7670_LTE_HTTP_EXACT_INVALID_ARGUMENT;
    request->response_body[0]='O'; request->response_body[1]='K';
    result->status=SIM7670_LTE_HTTP_EXACT_HTTP_RESPONSE; result->http_status_code=202U;
    result->declared_response_length=2U; result->response_length=2U; result->response_complete=true;
    result->payload_bytes_written=fake_mode == 0U ? sizeof(payload) : sizeof(payload)-1U;
    result->payload_write_complete=fake_mode == 0U;
    return result->status;
}
static int all_zero(size_t length) { for(size_t i=0U;i<length;++i) if(response[i]!=0U)return 0; return 1; }
static void fill_response(void) { (void)memset(response, 0xa5, sizeof(response)); }

int mainCRTStartup(void) {
    egolink_sim7670_p0_delivery_adapter_t adapter;
    (void)memset(&adapter, 0, sizeof(adapter));
    egolink_sim7670_p0_delivery_adapter_config_t config;
    egolink_sim7670_p0_delivery_adapter_default_config(&config);
    CHECK(!config.enabled, 10);
    CHECK(config.command_timeout_ms*8U+config.data_timeout_ms+config.action_timeout_ms+config.read_timeout_ms == 25000U, 11);
    CHECK(config.max_callback_duration_ms == 30000U, 12);
    config.enabled=true; config.base_url="https://ego.example"; config.expected_tls_host="ego.example"; config.bearer_token="Token_1"; config.driver_post=fake_post; config.now_ms=now_ms;
    CHECK(egolink_sim7670_p0_delivery_adapter_init(&adapter, &config) == EGOLINK_SIM7670_P0_DELIVERY_OK, 13);
    egolink_sim7670_p0_delivery_adapter_snapshot_t snapshot;
    CHECK(egolink_sim7670_p0_delivery_adapter_current_status(&adapter, &snapshot) == EGOLINK_SIM7670_P0_DELIVERY_OK, 14);
    CHECK(snapshot.configured_io_phase_budget_ms == 25000U && snapshot.configured_max_callback_duration_ms == 30000U, 15);

    egolink_p0_delivery_post_request_t request;
    (void)memset(&request, 0, sizeof(request)); request.route=EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE; request.path=EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH;
    request.body=payload; request.body_length=sizeof(payload); request.response=response; request.response_capacity=EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES; request.priority=EGOLINK_OUTBOX_PRIORITY_NORMAL; request.cancel_requested=cancel_probe; request.cancel_context=&cancel_cookie; request.transfer_generation=77U;
    egolink_p0_delivery_post_result_t post_result;
    fill_response(); (void)memset(&post_result, 0xa5, sizeof(post_result));
    CHECK(egolink_sim7670_p0_delivery_adapter_http_post(NULL, &request, &post_result) == EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED, 20);
    CHECK(all_zero(request.response_capacity) && post_result.http_status_code==0U && post_result.response_length==0U && post_result.transport_error==EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE, 21);

    request.route=EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS; request.path=EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH; request.response_capacity=EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES; request.priority=EGOLINK_OUTBOX_PRIORITY_CRITICAL;
    fill_response(); clock_index=0U; clock_values[0]=1000U; clock_values[1]=1001U; fake_mode=0U;
    CHECK(egolink_sim7670_p0_delivery_adapter_http_post(&adapter, &request, &post_result) == EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE, 22);
    CHECK(fake_calls==1U && cancel_calls==1U && response[0]=='O' && response[1]=='K' && post_result.http_status_code==202U && post_result.response_length==2U, 23);
    fill_response(); clock_index=0U; clock_values[0]=2000U; clock_values[1]=2001U; fake_mode=1U;
    CHECK(egolink_sim7670_p0_delivery_adapter_http_post(&adapter, &request, &post_result) == EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED, 24);
    CHECK(all_zero(request.response_capacity) && post_result.response_length==0U, 25);
    CHECK(egolink_sim7670_p0_delivery_adapter_close(&adapter) == EGOLINK_SIM7670_P0_DELIVERY_CLOSED_STATUS, 26);

    static const char *bad_origins[] = {"https:///", "http://ego.example", "https://ego.example/path", "https://ego.example:443", "https://u@ego.example", "https://ego..example"};
    for(size_t i=0U;i<6U;++i){ (void)memset(&adapter,0,sizeof(adapter)); egolink_sim7670_p0_delivery_adapter_default_config(&config); config.enabled=true; config.base_url=bad_origins[i]; config.expected_tls_host="ego.example"; config.bearer_token="Token_1"; config.driver_post=fake_post; config.now_ms=now_ms; CHECK(egolink_sim7670_p0_delivery_adapter_init(&adapter,&config)==EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG,30+(int)i); }
    (void)memset(&adapter,0,sizeof(adapter)); egolink_sim7670_p0_delivery_adapter_default_config(&config); config.enabled=true; config.base_url="https://ego.example"; config.expected_tls_host="ego.example"; config.bearer_token="<runtime-token>"; config.driver_post=fake_post; config.now_ms=now_ms;
    CHECK(egolink_sim7670_p0_delivery_adapter_init(&adapter,&config)==EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG,40);
    config.bearer_token="Token_1"; config.max_callback_duration_ms=25000U;
    CHECK(egolink_sim7670_p0_delivery_adapter_init(&adapter,&config)==EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG,41);

    (void)memset(&adapter,0,sizeof(adapter)); egolink_sim7670_p0_delivery_adapter_default_config(&config); config.enabled=true; config.base_url="https://127.0.0.1"; config.expected_tls_host="127.0.0.1"; config.bearer_token="Token_1"; config.driver_post=fake_post; config.now_ms=now_ms;
    CHECK(egolink_sim7670_p0_delivery_adapter_init(&adapter,&config)==EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG,42);
    (void)memset(&adapter,0,sizeof(adapter)); egolink_sim7670_p0_delivery_adapter_default_config(&config); config.enabled=true; config.base_url="https://" LABEL_64 ".example"; config.expected_tls_host=LABEL_64 ".example"; config.bearer_token="Token_1"; config.driver_post=fake_post; config.now_ms=now_ms;
    CHECK(egolink_sim7670_p0_delivery_adapter_init(&adapter,&config)==EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG,43);
    (void)memset(&adapter,0,sizeof(adapter)); egolink_sim7670_p0_delivery_adapter_default_config(&config); config.enabled=true; config.base_url="https://" LABEL_63 ".example"; config.expected_tls_host=LABEL_63 ".example"; config.bearer_token="Token_1"; config.driver_post=fake_post; config.now_ms=now_ms;
    CHECK(egolink_sim7670_p0_delivery_adapter_init(&adapter,&config)==EGOLINK_SIM7670_P0_DELIVERY_OK,44);
    CHECK(egolink_sim7670_p0_delivery_adapter_close(&adapter)==EGOLINK_SIM7670_P0_DELIVERY_CLOSED_STATUS,45);
    return 0;
}
"""


class Sim7670P0DeliveryAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sim_source = SIM_SOURCE.read_text(encoding="utf-8")
        cls.sim_header = SIM_HEADER.read_text(encoding="utf-8")
        cls.parser_source = PARSER_SOURCE.read_text(encoding="utf-8")
        cls.adapter_source = ADAPTER_SOURCE.read_text(encoding="utf-8")
        cls.adapter_header = ADAPTER_HEADER.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def test_default_off_and_not_wired_into_app_main(self) -> None:
        self.assertIn("default n", ADAPTER_KCONFIG.read_text(encoding="utf-8"))
        app_main = APP_MAIN.read_text(encoding="utf-8")
        self.assertNotIn("sim7670_p0_delivery_adapter", app_main)
        self.assertNotIn("egolink_sim7670_p0_delivery_adapter_init", app_main)

    def test_real_exact_api_is_unique_and_tls_blocked_before_io(self) -> None:
        self.assertEqual(1, self.sim_source.count("sim7670_lte_http_post_bytes_exact("))
        body = _function_body(self.sim_source, "sim7670_lte_http_post_bytes_exact(")
        self.assertIn("SIM7670_LTE_HTTP_EXACT_TLS_PROFILE_UNVERIFIED", body)
        for forbidden in ("sim7670_gnss_init", "uart_", "HTTPDATA", "USERDATA", "ESP_LOG"):
            self.assertNotIn(forbidden, body)
        self.assertLess(body.index("sim7670_exact_clear_caller_response"), body.index("request == NULL"))

    def test_caps_and_exact_response_contract_are_caller_owned(self) -> None:
        self.assertIn("EXACT_RESPONSE_MAX_BYTES 8192U", self.sim_header)
        self.assertIn("CALLER_RESPONSE_CAPACITY_MAX_BYTES 8192U", self.sim_header)
        self.assertNotIn("response[8192", self.sim_source)
        self.assertIn("response_complete", self.adapter_source)
        self.assertIn("declared_response_length", self.adapter_source)
        self.assertIn("payload_write_complete", self.adapter_source)
        self.assertIn("payload_bytes_written == request->body_length", self.adapter_source)
        self.assertIn("driver_request.cancel_requested = request->cancel_requested", self.adapter_source)
        self.assertIn("driver_request.cancel_context = request->cancel_context", self.adapter_source)
        self.assertIn("driver_request.transfer_generation = request->transfer_generation", self.adapter_source)

    def test_adapter_is_fixed_route_bounded_and_has_no_work_loop(self) -> None:
        for token in (
            "EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH",
            "EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH",
            "SIM7670_LTE_HTTP_EXACT_PAYLOAD_MAX_BYTES",
            "EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES",
        ):
            self.assertIn(token, self.adapter_source)
        for forbidden in ("xTaskCreate", "while (true)", "nvs_", "fopen(", "retry"):
            self.assertNotIn(forbidden, self.adapter_source)

    def test_dns_authority_validator_is_shared_and_rejects_literals(self) -> None:
        validator = "sim7670_http_exact_https_origin_matches_dns_host"
        self.assertIn(validator, self.sim_header)
        self.assertIn(validator, self.parser_source)
        self.assertEqual(1, self.adapter_source.count(f"{validator}("))
        self.assertNotIn("static bool valid_base_url", self.adapter_source)
        self.assertNotIn("static bool valid_expected_tls_host", self.adapter_source)
        self.assertIn("SIM7670_HTTP_EXACT_DNS_LABEL_MAX_BYTES 63U", self.parser_source)
        self.assertIn("return has_alpha && label_length > 0U", self.parser_source)
        for boundary in ("127.0.0.1", "LABEL_63", "LABEL_64"):
            self.assertIn(boundary, PARSER_HARNESS)
            self.assertIn(boundary, ADAPTER_HARNESS)

    def test_timing_phase_sum_and_callback_bound_are_separate(self) -> None:
        defaults = [int(value) for value in re.findall(r"DEFAULT_(?:COMMAND|DATA|ACTION|READ)_TIMEOUT_MS UINT32_C\((\d+)\)", self.adapter_header)]
        self.assertEqual([1000, 3000, 10000, 4000], defaults)
        self.assertEqual(25_000, 8 * defaults[0] + sum(defaults[1:]))
        self.assertIn("DEFAULT_MAX_CALLBACK_DURATION_MS", self.adapter_header)
        self.assertIn("total >= (uint64_t)config->max_callback_duration_ms", self.adapter_source)
        self.assertIn("configured_max_callback_duration_ms", self.adapter_source)

    def test_parser_and_request_validation_execute_in_native_c(self) -> None:
        self._compile_and_run(PARSER_HARNESS, (PARSER_SOURCE,), (SIM,))

    def test_adapter_exact_bytes_wipe_and_timing_execute_in_native_c(self) -> None:
        includes = (
            ADAPTER / "include",
            SIM / "include",
            COMPONENTS / "p0_delivery_runtime" / "include",
            COMPONENTS / "p0_outbox_dispatcher" / "include",
            COMPONENTS / "location_outbox_adapter" / "include",
            COMPONENTS / "location_state_emitter" / "include",
            COMPONENTS / "persistent_priority_outbox" / "include",
            COMPONENTS / "sos_outbox_adapter" / "include",
        )
        self._compile_and_run(
            ADAPTER_HARNESS,
            (ADAPTER_SOURCE, PARSER_SOURCE),
            includes,
            defines=("CONFIG_EGOLINK_SIM7670_P0_DELIVERY_TEST_DRIVER_ENABLED=1",),
            needs_esp_stub=True,
        )

    def test_actual_c_harnesses_cross_compile_and_link_for_esp32s3(self) -> None:
        compiler = _xtensa_compiler()
        if compiler is None:
            self.skipTest("ESP32-S3 GCC is unavailable")
        adapter_includes = (
            ADAPTER / "include",
            SIM / "include",
            COMPONENTS / "p0_delivery_runtime" / "include",
            COMPONENTS / "p0_outbox_dispatcher" / "include",
            COMPONENTS / "location_outbox_adapter" / "include",
            COMPONENTS / "location_state_emitter" / "include",
            COMPONENTS / "persistent_priority_outbox" / "include",
            COMPONENTS / "sos_outbox_adapter" / "include",
        )
        self._cross_compile_harness(
            compiler,
            PARSER_HARNESS,
            (PARSER_SOURCE,),
            (SIM,),
        )
        self._cross_compile_harness(
            compiler,
            ADAPTER_HARNESS,
            (ADAPTER_SOURCE, PARSER_SOURCE),
            adapter_includes,
            defines=("CONFIG_EGOLINK_SIM7670_P0_DELIVERY_TEST_DRIVER_ENABLED=1",),
            needs_esp_stub=True,
        )
        self._cross_compile_harness(
            compiler,
            ADAPTER_HARNESS,
            (ADAPTER_SOURCE, PARSER_SOURCE),
            adapter_includes,
            needs_esp_stub=True,
        )

    def test_current_and_maximum_server_ack_bodies_fit_without_truncation(self) -> None:
        location = _location_envelope(with_fix=True)
        representative_location = _wire(location)
        location_bodies = self._location_responses(location, representative_location)
        self.assertEqual([858, 859], [len(value) for value in location_bodies])
        self.assertEqual(716, len(json.dumps(json.loads(location_bodies[0]), sort_keys=True, separators=(",", ":")).encode("utf-8")))

        maximum_location = _location_envelope(with_fix=True)
        maximum_location["device_id"] = "d" * 128
        maximum_location["session_id"] = "s" * 128
        maximum_location["observation_id"] = chr(0x1F600) * 256
        maximum_payload = json.dumps(maximum_location, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        maximum_location_bodies = self._location_responses(maximum_location, maximum_payload, maximum_clock=True)
        self.assertEqual([2200, 2201], [len(value) for value in maximum_location_bodies])

        _, sos_payload, _ = _sos_payload()
        sos_bodies = self._sos_responses(sos_payload)
        self.assertEqual(438, len(json.dumps(json.loads(sos_bodies[0]), sort_keys=True, separators=(",", ":")).encode("utf-8")))
        _, maximum_sos_payload, _ = _sos_payload(
            device_id="d" * 128,
            boot_count=(1 << 63) - 1,
            session_id="s" * 128,
            sequence=(1 << 63) - 1,
            edge_time_ms=(1 << 63) - 1,
        )
        maximum_sos_bodies = self._sos_responses(maximum_sos_payload, maximum_clock=True)
        self.assertEqual([682, 683], [len(value) for value in maximum_sos_bodies])
        for body in (*location_bodies, *maximum_location_bodies, *sos_bodies, *maximum_sos_bodies):
            self.assertLessEqual(len(body), 8192)

    def test_packet_records_outbox_010g_truth_boundary(self) -> None:
        for phrase in (
            "OUTBOX-010G",
            "TLS_PROFILE_UNVERIFIED",
            "external single owner",
            "8,192",
            "25",
            "30",
            "127.0.0.1",
            "63-byte",
            "64-byte",
        ):
            self.assertIn(phrase, self.packet)

    @staticmethod
    def _location_responses(envelope: dict, payload: bytes, *, maximum_clock: bool = False) -> list[bytes]:
        clock = (1 << 63) - 1 if maximum_clock else 11_000
        with tempfile.TemporaryDirectory(prefix="egolink-outbox010g-loc-") as temp:
            store = LocationStateStore(Path(temp) / "location.sqlite3")
            results = [
                store.ingest(envelope, server_receive_time_ms=clock - 3),
                store.ingest(envelope, server_receive_time_ms=clock - 2),
            ]
        bodies = []
        for offset, result in enumerate(results):
            ack = build_location_state_delivery_ack(
                payload, envelope, result, ack_time_ms=clock - 1 + offset
            )
            body = {
                "ok": True,
                "result": result,
                "delivery_ack": ack,
                "delivery_scope": "server_durable_ingest_only",
            }
            bodies.append(dumps(body, indent=2).encode("utf-8"))
        return bodies

    @staticmethod
    def _sos_responses(payload: bytes, *, maximum_clock: bool = False) -> list[bytes]:
        clock = (1 << 63) - 1 if maximum_clock else 11_000
        with tempfile.TemporaryDirectory(prefix="egolink-outbox010g-sos-") as temp:
            store = ManualSosStore(Path(temp) / "sos.sqlite3")
            results = [
                store.ingest(payload, server_receive_time_ms=clock - 3),
                store.ingest(payload, server_receive_time_ms=clock - 2),
            ]
        bodies = []
        for offset, result in enumerate(results):
            ack = build_manual_sos_delivery_ack(payload, result, ack_time_ms=clock - 1 + offset)
            body = {
                "ok": True,
                "result": {"status": result["status"]},
                "delivery_ack": ack,
                "delivery_scope": DELIVERY_SCOPE,
            }
            bodies.append(dumps(body, indent=2).encode("utf-8"))
        return bodies

    def _compile_and_run(
        self,
        harness_text: str,
        sources: tuple[Path, ...],
        includes: tuple[Path, ...],
        *,
        defines: tuple[str, ...] = (),
        needs_esp_stub: bool = False,
    ) -> None:
        tools = _native_tools()
        if tools is None:
            self.skipTest("Espressif clang/lld native host mode is unavailable")
        clang, linker = tools
        with tempfile.TemporaryDirectory(prefix="egolink-outbox010g-native-") as temp:
            temp_path = Path(temp)
            (temp_path / "string.h").write_text(
                "#include <stddef.h>\nvoid *memset(void *, int, size_t);\n"
                "void *memcpy(void *, const void *, size_t);\n"
                "int memcmp(const void *, const void *, size_t);\n"
                "int strcmp(const char *, const char *);\n"
                "int strncmp(const char *, const char *, size_t);\n"
                "size_t strlen(const char *);\n",
                encoding="utf-8",
            )
            if needs_esp_stub:
                (temp_path / "esp_err.h").write_text("typedef int esp_err_t;\n", encoding="utf-8")
            harness = temp_path / "harness.c"
            harness.write_text(harness_text, encoding="utf-8")
            common = [
                str(clang), "--target=x86_64-pc-windows-msvc", "-std=c11",
                "-ffreestanding", "-fno-builtin", "-fno-stack-protector",
                "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wformat=2",
                "-Wshadow", "-Wsign-conversion", "-I", str(temp_path),
                *[item for path in includes for item in ("-I", str(path))],
                *[f"-D{value}" for value in defines],
            ]
            objects = []
            for index, source in enumerate((*sources, harness)):
                output = temp_path / f"unit{index}.obj"
                result = subprocess.run(
                    [*common, "-c", str(source), "-o", str(output)],
                    capture_output=True, text=True, timeout=60, check=False,
                )
                self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
                objects.append(output)
            executable = temp_path / "harness.exe"
            linked = subprocess.run(
                [str(linker), "-flavor", "link", "/entry:mainCRTStartup", "/subsystem:console", "/nodefaultlib", "/machine:x64", f"/out:{executable}", *map(str, objects)],
                capture_output=True, text=True, timeout=60, check=False,
            )
            self.assertEqual(0, linked.returncode, msg=linked.stdout + linked.stderr)
            executed = subprocess.run([str(executable)], capture_output=True, timeout=30, check=False)
            self.assertEqual(0, executed.returncode, msg=f"harness failure={executed.returncode}")

    def _cross_compile_harness(
        self,
        compiler: Path,
        harness_text: str,
        sources: tuple[Path, ...],
        includes: tuple[Path, ...],
        *,
        defines: tuple[str, ...] = (),
        needs_esp_stub: bool = False,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="egolink-outbox010g-xtensa-") as temp:
            temp_path = Path(temp)
            (temp_path / "string.h").write_text(
                "#include <stddef.h>\nvoid *memset(void *, int, size_t);\n"
                "void *memcpy(void *, const void *, size_t);\n"
                "int memcmp(const void *, const void *, size_t);\n"
                "int strcmp(const char *, const char *);\n"
                "int strncmp(const char *, const char *, size_t);\n"
                "size_t strlen(const char *);\n",
                encoding="utf-8",
            )
            if needs_esp_stub:
                (temp_path / "esp_err.h").write_text("typedef int esp_err_t;\n", encoding="utf-8")
            harness = temp_path / "harness.c"
            harness.write_text(harness_text, encoding="utf-8")
            common = [
                str(compiler), "-std=c11", "-mlongcalls", "-ffreestanding",
                "-fno-builtin", "-Wall", "-Wextra", "-Werror", "-Wconversion",
                "-Wformat=2", "-Wshadow", "-Wsign-conversion", "-I", str(temp_path),
                *[item for path in includes for item in ("-I", str(path))],
                *[f"-D{value}" for value in defines],
            ]
            objects = []
            for index, source in enumerate((*sources, harness)):
                output = temp_path / f"unit{index}.o"
                result = subprocess.run(
                    [*common, "-c", str(source), "-o", str(output)],
                    capture_output=True, text=True, timeout=60, check=False,
                )
                self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
                objects.append(output)
            executable = temp_path / "harness.elf"
            linked = subprocess.run(
                [str(compiler), "-nostdlib", "-Wl,-e,mainCRTStartup", *map(str, objects), "-o", str(executable)],
                capture_output=True, text=True, timeout=60, check=False,
            )
            self.assertEqual(0, linked.returncode, msg=linked.stdout + linked.stderr)
            self.assertGreater(executable.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

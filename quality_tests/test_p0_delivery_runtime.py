"""Focused OUTBOX-010F checks for the dormant unified delivery runtime.

The native freestanding harness executes the actual C runtime against a
deterministic dispatcher double. The Xtensa build is compile/size evidence
only. Neither path is network, storage, device, Guardian/human delivery, or
P0 Gate evidence.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "firmware" / "mqtt_heartbeat" / "components"
COMPONENT = COMPONENTS / "p0_delivery_runtime"
SOURCE = COMPONENT / "p0_delivery_runtime.c"
HEADER = COMPONENT / "include" / "p0_delivery_runtime.h"
CMAKE = COMPONENT / "CMakeLists.txt"
DISPATCHER_HEADER = (
    COMPONENTS / "p0_outbox_dispatcher" / "include" / "p0_outbox_dispatcher.h"
)
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = (
    ROOT / "docs" / "tasks" / "active" / "OUTBOX-010_PERSISTENT_PRIORITY_OUTBOX.md"
)


def _esp_toolchain() -> tuple[Path, Path] | None:
    compiler_candidates = (
        shutil.which("xtensa-esp32s3-elf-gcc"),
        Path(
            "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/"
            "xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
        ),
    )
    compiler = next(
        (
            Path(candidate)
            for candidate in compiler_candidates
            if candidate and Path(candidate).is_file()
        ),
        None,
    )
    idf_candidates = (
        Path(os.environ["IDF_PATH"]) if os.environ.get("IDF_PATH") else None,
        Path("C:/Espressif/v5.4.2/esp-idf"),
    )
    idf = next(
        (candidate for candidate in idf_candidates if candidate and candidate.is_dir()),
        None,
    )
    return None if compiler is None or idf is None else (compiler, idf)


def _include_paths(idf: Path | None = None) -> tuple[Path, ...]:
    paths = (
        COMPONENT / "include",
        COMPONENTS / "p0_outbox_dispatcher" / "include",
        COMPONENTS / "location_outbox_adapter" / "include",
        COMPONENTS / "location_state_emitter" / "include",
        COMPONENTS / "persistent_priority_outbox" / "include",
        COMPONENTS / "sos_outbox_adapter" / "include",
    )
    if idf is None:
        return paths
    return paths + (
        idf / "components" / "mbedtls" / "port" / "include",
        idf / "components" / "mbedtls" / "mbedtls" / "include",
        idf / "components" / "mbedtls" / "mbedtls" / "library",
    )


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
    raise AssertionError(f"unterminated C function {name}")


def _native_tools() -> tuple[Path, Path] | None:
    root = Path(
        "C:/Espressif/tools/esp-clang/esp-18.1.2_20240912/esp-clang/bin"
    )
    clang = root / "clang.exe"
    linker = root / "lld.exe"
    if not clang.is_file() or not linker.is_file():
        return None
    targets = subprocess.run(
        [str(clang), "--print-targets"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if targets.returncode != 0 or "x86" not in targets.stdout.casefold():
        return None
    return clang, linker


HARNESS = r"""
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "p0_delivery_runtime.h"

void *memset(void *destination, int value, size_t length)
{
    unsigned char *cursor = (unsigned char *)destination;
    while (length > 0U) {
        *cursor = (unsigned char)value;
        ++cursor;
        --length;
    }
    return destination;
}

void *memcpy(void *destination, const void *source, size_t length)
{
    unsigned char *output = (unsigned char *)destination;
    const unsigned char *input = (const unsigned char *)source;
    while (length > 0U) {
        *output = *input;
        ++output;
        ++input;
        --length;
    }
    return destination;
}

int strcmp(const char *left, const char *right)
{
    while (*left != '\0' && *left == *right) {
        ++left;
        ++right;
    }
    return (int)(unsigned char)*left - (int)(unsigned char)*right;
}

static egolink_p0_delivery_runtime_t runtime_object;
static egolink_p0_delivery_runtime_result_t runtime_result;
static egolink_p0_delivery_runtime_result_t nested_result;
static egolink_p0_outbox_dispatcher_t dispatcher_object;
static const uint8_t payload[] = {0x7bU, 0x22U, 0x78U, 0x22U, 0x3aU, 0x31U, 0x7dU};
static unsigned int begin_calls;
static unsigned int post_calls;
static unsigned int finish_calls;
static unsigned int cancel_calls;
static unsigned int close_calls;
static unsigned int failure;
static unsigned int callback_mode;
static unsigned int finish_recoveries;
static unsigned int control_must_recover;
static unsigned int begin_recovery_mode;
static unsigned int cancel_returns_retained;
static egolink_p0_outbox_route_t selected_route;
static uint64_t callback_begin_time;
static uint64_t captured_finish_time;
static uint16_t captured_http_status;
static size_t captured_response_length;
static bool captured_error_present;

#define CHECK(condition, code) do { if (!(condition) && failure == 0U) { failure = (code); } } while (0)

void egolink_p0_outbox_dispatcher_clear_send_view(
    egolink_p0_outbox_send_view_t *view)
{
    if (view != NULL) {
        (void)memset(view, 0, sizeof(*view));
    }
}

egolink_p0_outbox_dispatcher_status_t
egolink_p0_outbox_dispatcher_current_status(
    const egolink_p0_outbox_dispatcher_t *dispatcher,
    egolink_p0_outbox_dispatcher_snapshot_t *snapshot)
{
    CHECK(dispatcher == &dispatcher_object, 1U);
    if (snapshot == NULL) {
        return EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->lifecycle = EGOLINK_P0_OUTBOX_DISPATCHER_ACTIVE;
    snapshot->phase = EGOLINK_P0_OUTBOX_PHASE_IDLE;
    snapshot->active_route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
    snapshot->enabled = true;
    snapshot->dependency_bound = true;
    return EGOLINK_P0_OUTBOX_OK;
}

bool egolink_p0_outbox_dispatcher_dependencies_match(
    const egolink_p0_outbox_dispatcher_t *dispatcher,
    const egolink_outbox_t *shared_outbox,
    const egolink_location_outbox_adapter_t *location_adapter)
{
    (void)shared_outbox;
    (void)location_adapter;
    return dispatcher == &dispatcher_object;
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_begin(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *view,
    egolink_p0_outbox_begin_result_t *result)
{
    (void)now_ms;
    CHECK(dispatcher == &dispatcher_object, 2U);
    ++begin_calls;
    (void)memset(result, 0, sizeof(*result));
    egolink_p0_outbox_dispatcher_clear_send_view(view);
    if (begin_recovery_mode == 1U) {
        result->status = EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
        result->route = EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED;
        return result->status;
    }
    if (begin_recovery_mode == 2U) {
        view->completion_only = true;
        view->attempt.route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
        view->attempt.priority = EGOLINK_OUTBOX_PRIORITY_CRITICAL;
        result->status = EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
        result->route = EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED;
        return result->status;
    }
    if (selected_route == EGOLINK_P0_OUTBOX_ROUTE_NONE) {
        result->status = EGOLINK_P0_OUTBOX_NO_DUE_RECORD;
        return result->status;
    }
    view->payload = payload;
    view->payload_length = sizeof(payload);
    view->attempt.route = selected_route;
    view->attempt.priority =
        selected_route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS
            ? EGOLINK_OUTBOX_PRIORITY_CRITICAL
            : EGOLINK_OUTBOX_PRIORITY_NORMAL;
    view->endpoint_path =
        selected_route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS
            ? EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH
            : EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH;
    view->response_max_bytes =
        selected_route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS
            ? EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES
            : EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES;
    result->status = EGOLINK_P0_OUTBOX_BEGIN_READY;
    result->route = selected_route;
    return result->status;
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_finish(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    egolink_p0_outbox_send_view_t *view,
    uint16_t http_status_code,
    const char *transport_error_code,
    const uint8_t *response_json,
    size_t response_length,
    uint64_t now_ms,
    egolink_p0_outbox_finish_result_t *result)
{
    CHECK(dispatcher == &dispatcher_object, 3U);
    CHECK(view != NULL, 4U);
    ++finish_calls;
    captured_http_status = http_status_code;
    captured_error_present = transport_error_code != NULL;
    captured_response_length = response_length;
    captured_finish_time = now_ms;
    if (http_status_code >= UINT16_C(200) && http_status_code <= UINT16_C(299)) {
        CHECK(transport_error_code == NULL, 5U);
        CHECK(response_length == 0U || response_json != NULL, 6U);
    } else {
        CHECK(transport_error_code != NULL, 7U);
        CHECK(response_json == NULL && response_length == 0U, 8U);
    }
    (void)memset(result, 0, sizeof(*result));
    result->route = view->attempt.route;
    if (finish_recoveries > 0U) {
        --finish_recoveries;
        view->payload = NULL;
        view->payload_length = 0U;
        view->endpoint_path = NULL;
        view->response_max_bytes = 0U;
        view->completion_only = true;
        result->status = EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
        result->durable_record_retained = true;
        result->private_canonical_item_retained = true;
        return result->status;
    }
    egolink_p0_outbox_dispatcher_clear_send_view(view);
    result->status = EGOLINK_P0_OUTBOX_FINISHED_RETAINED;
    result->terminal = true;
    result->durable_record_retained = true;
    return result->status;
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_cancel(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *view,
    egolink_p0_outbox_finish_result_t *result)
{
    (void)now_ms;
    CHECK(dispatcher == &dispatcher_object, 9U);
    ++cancel_calls;
    (void)memset(result, 0, sizeof(*result));
    if (control_must_recover != 0U) {
        result->status = EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
        result->durable_record_retained = true;
        return result->status;
    }
    if (cancel_returns_retained != 0U) {
        egolink_p0_outbox_dispatcher_clear_send_view(view);
        result->status = EGOLINK_P0_OUTBOX_CANCELLED_RETAINED;
        result->terminal = true;
        result->durable_record_retained = true;
        return result->status;
    }
    egolink_p0_outbox_dispatcher_clear_send_view(view);
    result->status = EGOLINK_P0_OUTBOX_OK;
    return result->status;
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_close(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *view,
    egolink_p0_outbox_finish_result_t *result)
{
    (void)now_ms;
    CHECK(dispatcher == &dispatcher_object, 10U);
    ++close_calls;
    (void)memset(result, 0, sizeof(*result));
    if (control_must_recover != 0U) {
        result->status = EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
        result->durable_record_retained = true;
        return result->status;
    }
    egolink_p0_outbox_dispatcher_clear_send_view(view);
    result->status = EGOLINK_P0_OUTBOX_CLOSED_STATUS;
    result->terminal = true;
    return result->status;
}

static egolink_p0_delivery_post_outcome_t post_callback(
    void *context,
    const egolink_p0_delivery_post_request_t *request,
    egolink_p0_delivery_post_result_t *result)
{
    (void)context;
    ++post_calls;
    CHECK(request->body == payload, 11U);
    CHECK(request->body_length == sizeof(payload), 12U);
    CHECK(request->response != NULL, 13U);
    if (request->route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS) {
        CHECK(strcmp(request->path, EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH) == 0, 14U);
        CHECK(request->response_capacity == EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES, 15U);
    } else {
        CHECK(request->route == EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE, 16U);
        CHECK(strcmp(request->path, EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH) == 0, 17U);
        CHECK(request->response_capacity == EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES, 18U);
    }
    (void)memset(result, 0, sizeof(*result));
    result->completion_time_ms = callback_begin_time + UINT64_C(1);
    if (callback_mode == 0U) {
        result->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TIMEOUT;
        return EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED;
    }
    if (callback_mode == 1U) {
        request->response[0] = (uint8_t)'{';
        request->response[1] = (uint8_t)'}';
        result->http_status_code = UINT16_C(200);
        result->response_length = 2U;
        return EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE;
    }
    if (callback_mode == 2U) {
        request->response[0] = UINT8_C(0x41);
        result->http_status_code = UINT16_C(200);
        result->response_length = request->response_capacity + 1U;
        return EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE;
    }
    if (callback_mode == 3U) {
        result->http_status_code = UINT16_C(503);
        result->completion_time_ms = callback_begin_time + UINT64_C(30001);
        return EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE;
    }
    if (callback_mode == 4U) {
        result->http_status_code = UINT16_C(200);
        result->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER;
        return EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE;
    }
    if (callback_mode == 5U) {
        const egolink_p0_delivery_runtime_status_t nested =
            egolink_p0_delivery_runtime_drive_once(
                &runtime_object, callback_begin_time, &nested_result);
        CHECK(nested == EGOLINK_P0_DELIVERY_REENTRANT_CALL, 19U);
        result->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_IO;
        return EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED;
    }
    return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
}

static int initialize_active(void)
{
    (void)memset(&runtime_object, 0, sizeof(runtime_object));
    egolink_p0_delivery_runtime_config_t config;
    egolink_p0_delivery_runtime_default_config(&config);
    CHECK(!config.enabled, 20U);
    CHECK(config.max_post_duration_ms == UINT32_C(30000), 21U);
    config.enabled = true;
    config.http_post = post_callback;
    const egolink_p0_delivery_runtime_status_t status =
        egolink_p0_delivery_runtime_init(
            &runtime_object, &config, &dispatcher_object);
    CHECK(status == EGOLINK_P0_DELIVERY_OK, 22U);
    return status == EGOLINK_P0_DELIVERY_OK ? 0 : 1;
}

int mainCRTStartup(void)
{
    egolink_p0_delivery_runtime_config_t disabled;
    egolink_p0_delivery_runtime_default_config(&disabled);
    CHECK(
        egolink_p0_delivery_runtime_init(&runtime_object, &disabled, NULL) ==
            EGOLINK_P0_DELIVERY_DISABLED_STATUS,
        23U);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, UINT64_C(0), &runtime_result) ==
            EGOLINK_P0_DELIVERY_DISABLED_STATUS,
        24U);
    CHECK(
        egolink_p0_delivery_runtime_close(
            &runtime_object, UINT64_C(0), &runtime_result) ==
            EGOLINK_P0_DELIVERY_CLOSED_STATUS,
        25U);

    if (initialize_active() != 0) {
        return (int)failure;
    }
    selected_route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, UINT64_C(100), &runtime_result) ==
            EGOLINK_P0_DELIVERY_NO_DUE_RECORD,
        26U);
    CHECK(begin_calls == 1U && post_calls == 0U && finish_calls == 0U, 27U);

    selected_route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
    callback_mode = 0U;
    callback_begin_time = UINT64_C(200);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, callback_begin_time, &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        28U);
    CHECK(begin_calls == 2U && post_calls == 1U && finish_calls == 1U, 29U);
    CHECK(captured_http_status == UINT16_C(0) && captured_error_present, 30U);

    selected_route = EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE;
    callback_mode = 1U;
    callback_begin_time = UINT64_C(300);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, callback_begin_time, &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        31U);
    CHECK(begin_calls == 3U && post_calls == 2U && finish_calls == 2U, 32U);
    CHECK(captured_http_status == UINT16_C(200), 33U);
    CHECK(!captured_error_present && captured_response_length == 2U, 34U);

    selected_route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
    callback_mode = 2U;
    callback_begin_time = UINT64_C(400);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, callback_begin_time, &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        35U);
    CHECK(runtime_result.response_oversize, 36U);
    CHECK(!runtime_result.post_contract_valid, 37U);
    CHECK(captured_http_status == UINT16_C(0) && captured_response_length == 0U, 38U);
    CHECK(begin_calls == 4U && post_calls == 3U && finish_calls == 3U, 39U);

    callback_mode = 3U;
    callback_begin_time = UINT64_C(500);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, callback_begin_time, &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        40U);
    CHECK(!runtime_result.post_contract_valid, 41U);
    CHECK(captured_finish_time == callback_begin_time, 42U);
    CHECK(begin_calls == 5U && post_calls == 4U && finish_calls == 4U, 43U);

    callback_mode = 4U;
    callback_begin_time = UINT64_C(600);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, callback_begin_time, &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        44U);
    CHECK(!runtime_result.post_contract_valid, 45U);
    CHECK(begin_calls == 6U && post_calls == 5U && finish_calls == 5U, 46U);

    callback_mode = 1U;
    callback_begin_time = UINT64_C(700);
    finish_recoveries = 1U;
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, callback_begin_time, &runtime_result) ==
            EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED,
        47U);
    CHECK(runtime_result.private_settlement_retained_for_recovery, 48U);
    CHECK(begin_calls == 7U && post_calls == 6U && finish_calls == 6U, 49U);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, UINT64_C(701), &runtime_result) ==
            EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED,
        50U);
    CHECK(begin_calls == 7U && post_calls == 6U && finish_calls == 6U, 51U);
    CHECK(
        egolink_p0_delivery_runtime_retry_finish(
            &runtime_object, UINT64_C(702), &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        52U);
    CHECK(begin_calls == 7U && post_calls == 6U && finish_calls == 7U, 53U);

    callback_mode = 5U;
    callback_begin_time = UINT64_C(800);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, callback_begin_time, &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        54U);
    CHECK(begin_calls == 8U && post_calls == 7U && finish_calls == 8U, 55U);
    CHECK(
        egolink_p0_delivery_runtime_cancel(
            &runtime_object, UINT64_C(900), &runtime_result) ==
            EGOLINK_P0_DELIVERY_CANCELLED_STATUS,
        56U);
    CHECK(cancel_calls == 1U, 57U);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, UINT64_C(901), &runtime_result) ==
            EGOLINK_P0_DELIVERY_CANCELLED_STATUS,
        58U);
    CHECK(begin_calls == 8U, 59U);
    CHECK(
        egolink_p0_delivery_runtime_close(
            &runtime_object, UINT64_C(902), &runtime_result) ==
            EGOLINK_P0_DELIVERY_CLOSED_STATUS,
        60U);
    CHECK(close_calls == 1U, 61U);

    if (initialize_active() != 0) {
        return (int)failure;
    }
    selected_route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
    callback_mode = 1U;
    callback_begin_time = UINT64_C(1000);
    finish_recoveries = 1U;
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, callback_begin_time, &runtime_result) ==
            EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED,
        62U);
    control_must_recover = 1U;
    CHECK(
        egolink_p0_delivery_runtime_cancel(
            &runtime_object, UINT64_C(1002), &runtime_result) ==
            EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED,
        63U);
    CHECK(runtime_result.private_settlement_retained_for_recovery, 64U);
    CHECK(
        egolink_p0_delivery_runtime_close(
            &runtime_object, UINT64_C(1003), &runtime_result) ==
            EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED,
        65U);
    CHECK(runtime_result.private_settlement_retained_for_recovery, 66U);
    control_must_recover = 0U;
    CHECK(
        egolink_p0_delivery_runtime_retry_finish(
            &runtime_object, UINT64_C(1004), &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        67U);

    if (initialize_active() != 0) {
        return (int)failure;
    }
    begin_recovery_mode = 1U;
    selected_route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, UINT64_C(1100), &runtime_result) ==
            EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED,
        68U);
    CHECK(runtime_result.begin_called && !runtime_result.post_called, 69U);
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, UINT64_C(1101), &runtime_result) ==
            EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED,
        70U);
    control_must_recover = 1U;
    CHECK(
        egolink_p0_delivery_runtime_retry_begin_recovery(
            &runtime_object, UINT64_C(1102), &runtime_result) ==
            EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED,
        71U);
    control_must_recover = 0U;
    cancel_returns_retained = 1U;
    CHECK(
        egolink_p0_delivery_runtime_retry_begin_recovery(
            &runtime_object, UINT64_C(1103), &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        72U);
    CHECK(runtime_result.durable_record_retained, 73U);
    CHECK(post_calls == 8U && finish_calls == 10U, 74U);

    begin_recovery_mode = 2U;
    cancel_returns_retained = 0U;
    selected_route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
    CHECK(
        egolink_p0_delivery_runtime_drive_once(
            &runtime_object, UINT64_C(1200), &runtime_result) ==
            EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED,
        75U);
    CHECK(!runtime_result.post_called, 76U);
    CHECK(runtime_result.response_length == 0U, 79U);
    CHECK(runtime_result.private_settlement_retained_for_recovery, 80U);
    CHECK(
        egolink_p0_delivery_runtime_retry_finish(
            &runtime_object, UINT64_C(1201), &runtime_result) ==
            EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
        77U);
    CHECK(post_calls == 8U && finish_calls == 11U, 78U);
    return (int)failure;
}
"""


class P0DeliveryRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def test_component_is_dormant_bounded_and_transport_free(self) -> None:
        self.assertIn('SRCS "p0_delivery_runtime.c"', self.cmake)
        self.assertIn("p0_outbox_dispatcher", self.cmake)
        for option in (
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
        ):
            self.assertIn(option, self.cmake)
        for forbidden in (
            "esp_http_client",
            "esp_wifi",
            "mqtt_client",
            "freertos/",
            "xtaskcreate",
            "gpio_",
            "nvs_",
            "esp_partition",
            "esp_log",
            "authorization",
            "bearer",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source.casefold())
        self.assertNotIn("p0_delivery_runtime", APP_MAIN.read_text(encoding="utf-8"))
        self.assertIn("config->enabled = false", self.source)
        self.assertIn("EGOLINK_P0_DELIVERY_RUNTIME_CONTEXT_BYTES (12U * 1024U)", self.header)
        self.assertIn("EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES", self.header)

    def test_each_ready_drive_has_one_begin_one_post_and_one_finish(self) -> None:
        drive = _function_body(
            self.source, "egolink_p0_delivery_runtime_drive_once("
        )
        retry = _function_body(
            self.source, "egolink_p0_delivery_runtime_retry_finish("
        )
        finish = _function_body(self.source, "static egolink_p0_delivery_runtime_status_t finish_once(")
        self.assertEqual(1, drive.count("egolink_p0_outbox_dispatcher_begin("))
        self.assertEqual(1, drive.count("internal->http_post("))
        self.assertEqual(1, drive.count("finish_once("))
        self.assertEqual(1, finish.count("egolink_p0_outbox_dispatcher_finish("))
        self.assertNotIn("egolink_p0_outbox_dispatcher_begin(", retry)
        self.assertNotIn("internal->http_post(", retry)
        self.assertEqual(1, retry.count("finish_once("))
        self.assertNotIn("while (", drive)

    def test_fixed_routes_exact_bytes_and_exact_response_ceilings(self) -> None:
        validator = _function_body(self.source, "static bool valid_send_view(")
        drive = _function_body(
            self.source, "egolink_p0_delivery_runtime_drive_once("
        )
        self.assertIn("view->payload != NULL", validator)
        self.assertIn("view->payload_length <= EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES", validator)
        self.assertIn("exact_path(view->endpoint_path, path)", validator)
        self.assertIn("view->response_max_bytes == response_capacity", validator)
        self.assertIn("request.body = internal->send_view.payload", drive)
        self.assertIn("request.body_length = internal->send_view.payload_length", drive)
        self.assertIn("request.path = path", drive)
        self.assertIn("request.response_capacity = response_capacity", drive)
        self.assertIn("EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES", self.source)
        self.assertIn("EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES", self.source)
        request_match = re.search(
            r"typedef struct \{(?P<body>[^{}]*const char \*path;[^{}]*)\}\s*"
            r"egolink_p0_delivery_post_request_t;",
            self.header,
            re.DOTALL,
        )
        self.assertIsNotNone(request_match)
        request_fields = request_match.group("body").casefold()
        for secret in ("token", "credential", "authorization", "bearer"):
            self.assertNotIn(secret, request_fields)

    def test_callback_contract_checks_status_length_time_and_enum(self) -> None:
        capture = _function_body(self.source, "static void capture_callback_result(")
        prose = " ".join(self.header.split())
        for required in (
            "valid_transport_error(post_result->transport_error)",
            "post_result->completion_time_ms < begin_time_ms",
            "elapsed_ms > (uint64_t)internal->max_post_duration_ms",
            "post_result->response_length > response_capacity",
            "post_result->http_status_code < UINT16_C(100)",
            "post_result->http_status_code > UINT16_C(599)",
            "P0_SETTLEMENT_RESPONSE_OVERSIZE",
            "P0_SETTLEMENT_DURATION_EXCEEDED",
        ):
            self.assertIn(required, capture)
        self.assertIn("EGOLINK_P0_DELIVERY_RUNTIME_MAX_POST_DURATION_MS", self.header)
        self.assertIn("config->max_post_duration_ms >", self.source)
        self.assertIn("cannot preempt a callback", self.header)
        self.assertIn("cannot interrupt a synchronous POST callback", self.header)
        self.assertIn("must not retain request, body or response pointers", prose)
        self.assertIn("trusted never to write past response_capacity", prose)
        self.assertIn("no independent clock source", prose)

    def test_finish_recovery_retains_private_settlement_and_requires_explicit_retry(self) -> None:
        finish = _function_body(self.source, "static egolink_p0_delivery_runtime_status_t finish_once(")
        retry = _function_body(
            self.source, "egolink_p0_delivery_runtime_retry_finish("
        )
        for status in (
            "EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER",
            "EGOLINK_P0_OUTBOX_ATTEMPT_MISMATCH",
            "EGOLINK_P0_OUTBOX_DEPENDENCY_MISMATCH",
        ):
            self.assertIn(status, finish)
        self.assertIn("internal->settlement_retained = true", finish)
        self.assertIn("EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED", finish)
        self.assertIn("!internal->settlement_retained", retry)
        self.assertIn("now_ms < internal->settlement_time_ms", retry)
        self.assertIn("explicit_finish_retries", retry)
        self.assertNotIn("http_post", retry)
        self.assertNotIn("dispatcher_begin", retry)

    def test_begin_failure_preserves_exact_view_for_bounded_recovery(self) -> None:
        drive = _function_body(
            self.source, "egolink_p0_delivery_runtime_drive_once("
        )
        recovery = _function_body(
            self.source,
            "egolink_p0_delivery_runtime_retry_begin_recovery(",
        )
        must_branch = drive[
            drive.index("EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER") :
            drive.index(
                "if (result->dispatcher_begin_status != "
                "EGOLINK_P0_OUTBOX_BEGIN_READY)"
            )
        ]
        self.assertNotIn("clear_send_view", must_branch)
        self.assertIn("internal->send_view.completion_only", must_branch)
        self.assertIn("P0_SETTLEMENT_ROUTE_INVALID", must_branch)
        self.assertIn("internal->begin_recovery_pending = true", must_branch)
        self.assertIn("egolink_p0_outbox_dispatcher_cancel(", recovery)
        self.assertNotIn("egolink_p0_outbox_dispatcher_begin(", recovery)
        self.assertNotIn("internal->http_post(", recovery)
        self.assertNotIn("egolink_p0_outbox_dispatcher_finish(", recovery)

    def test_cancel_close_do_not_discard_recovery_and_have_no_hidden_retry(self) -> None:
        cancel = _function_body(self.source, "egolink_p0_delivery_runtime_cancel(")
        close = _function_body(self.source, "egolink_p0_delivery_runtime_close(")
        control = _function_body(self.source, "static egolink_p0_delivery_runtime_status_t map_control_result(")
        self.assertIn("egolink_p0_outbox_dispatcher_cancel(", cancel)
        self.assertIn("egolink_p0_outbox_dispatcher_close(", close)
        self.assertIn("internal->settlement_retained = true", control)
        self.assertIn("EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED", control)
        for body in (cancel, close):
            self.assertNotIn("while (", body)
            self.assertNotIn("internal->http_post(", body)
            self.assertNotIn("dispatcher_begin", body)

    def test_actual_c_behavior_with_freestanding_native_harness(self) -> None:
        tools = _native_tools()
        if tools is None:
            self.skipTest("Espressif clang/lld native host mode is unavailable")
        clang, linker = tools
        with tempfile.TemporaryDirectory(prefix="egolink-p0-delivery-native-") as temp:
            temp_path = Path(temp)
            (temp_path / "string.h").write_text(
                "#include <stddef.h>\n"
                "void *memset(void *, int, size_t);\n"
                "int strcmp(const char *, const char *);\n",
                encoding="utf-8",
            )
            harness = temp_path / "harness.c"
            harness.write_text(HARNESS, encoding="utf-8")
            common = [
                str(clang),
                "--target=x86_64-pc-windows-msvc",
                "-std=c11",
                "-ffreestanding",
                "-fno-builtin",
                "-fno-stack-protector",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wconversion",
                "-Wformat=2",
                "-Wshadow",
                "-Wsign-conversion",
                "-I",
                str(temp_path),
                *[
                    argument
                    for path in _include_paths()
                    for argument in ("-I", str(path))
                ],
            ]
            runtime_object = temp_path / "runtime.obj"
            harness_object = temp_path / "harness.obj"
            for source, output in (
                (SOURCE, runtime_object),
                (harness, harness_object),
            ):
                compiled = subprocess.run(
                    [*common, "-c", str(source), "-o", str(output)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                self.assertEqual(
                    0,
                    compiled.returncode,
                    msg=compiled.stdout + compiled.stderr,
                )
            executable = temp_path / "harness.exe"
            linked = subprocess.run(
                [
                    str(linker),
                    "-flavor",
                    "link",
                    "/entry:mainCRTStartup",
                    "/subsystem:console",
                    "/nodefaultlib",
                    "/machine:x64",
                    f"/out:{executable}",
                    str(runtime_object),
                    str(harness_object),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(0, linked.returncode, msg=linked.stdout + linked.stderr)
            executed = subprocess.run(
                [str(executable)],
                capture_output=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(
                0,
                executed.returncode,
                msg=(
                    f"harness failure code={executed.returncode}; "
                    f"stdout={executed.stdout!r}; stderr={executed.stderr!r}"
                ),
            )

    def test_actual_source_cross_compiles_and_sizes_are_bounded(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 compiler or ESP-IDF 5.4.2 is unavailable")
        compiler, idf = toolchain
        includes = [
            argument
            for path in _include_paths(idf)
            for argument in ("-I", str(path))
        ]
        common = [
            str(compiler),
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wformat=2",
            "-Wshadow",
            "-Wsign-conversion",
            "-fstack-usage",
            *includes,
        ]
        with tempfile.TemporaryDirectory(prefix="egolink-p0-delivery-compile-") as temp:
            temp_path = Path(temp)
            source_object = temp_path / "runtime.o"
            compiled = subprocess.run(
                [*common, "-c", str(SOURCE), "-o", str(source_object)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(0, compiled.returncode, msg=compiled.stdout + compiled.stderr)

            probe_source = temp_path / "probe.c"
            probe_source.write_text(
                textwrap.dedent(
                    """
                    #include "p0_delivery_runtime.h"
                    char probe_context[sizeof(egolink_p0_delivery_runtime_t)];
                    char probe_request[sizeof(egolink_p0_delivery_post_request_t)];
                    char probe_post_result[sizeof(egolink_p0_delivery_post_result_t)];
                    char probe_runtime_result[sizeof(egolink_p0_delivery_runtime_result_t)];
                    char probe_snapshot[sizeof(egolink_p0_delivery_runtime_snapshot_t)];
                    _Static_assert(sizeof(egolink_p0_delivery_runtime_t) == 12288U,
                                   "public context drift");
                    _Static_assert(EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES == 8192U,
                                   "response ceiling drift");
                    int p0_delivery_header_probe(void) { return 0; }
                    """
                ),
                encoding="utf-8",
            )
            probe_object = temp_path / "probe.o"
            compiled_probe = subprocess.run(
                [*common, "-c", str(probe_source), "-o", str(probe_object)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(
                0,
                compiled_probe.returncode,
                msg=compiled_probe.stdout + compiled_probe.stderr,
            )

            internal_source = temp_path / "internal_probe.c"
            internal_source.write_text(
                '#include "p0_delivery_runtime.c"\n'
                "char probe_internal[sizeof(p0_delivery_runtime_internal_t)];\n",
                encoding="utf-8",
            )
            internal_object = temp_path / "internal_probe.o"
            compiled_internal = subprocess.run(
                [
                    *common,
                    "-I",
                    str(COMPONENT),
                    "-c",
                    str(internal_source),
                    "-o",
                    str(internal_object),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(
                0,
                compiled_internal.returncode,
                msg=compiled_internal.stdout + compiled_internal.stderr,
            )

            harness_source = temp_path / "harness.c"
            harness_source.write_text(HARNESS, encoding="utf-8")
            harness_object = temp_path / "harness.o"
            compiled_harness = subprocess.run(
                [
                    *common,
                    "-ffreestanding",
                    "-fno-builtin",
                    "-c",
                    str(harness_source),
                    "-o",
                    str(harness_object),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(
                0,
                compiled_harness.returncode,
                msg=compiled_harness.stdout + compiled_harness.stderr,
            )
            harness_elf = temp_path / "harness.elf"
            linked_harness = subprocess.run(
                [
                    str(compiler),
                    "-nostdlib",
                    "-Wl,-e,mainCRTStartup",
                    str(source_object),
                    str(harness_object),
                    "-o",
                    str(harness_elf),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(
                0,
                linked_harness.returncode,
                msg=linked_harness.stdout + linked_harness.stderr,
            )
            self.assertGreater(harness_elf.stat().st_size, 0)

            nm = compiler.with_name(compiler.name.replace("gcc", "nm"))
            self.assertTrue(nm.is_file(), msg=f"missing size tool: {nm}")
            sizes: dict[str, int] = {}
            for object_path in (probe_object, internal_object):
                listing = subprocess.run(
                    [str(nm), "-S", str(object_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(0, listing.returncode, msg=listing.stderr)
                for line in listing.stdout.splitlines():
                    match = re.search(
                        r"^[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+\w\s+(probe_\w+)$",
                        line.strip(),
                    )
                    if match:
                        sizes[match.group(2)] = int(match.group(1), 16)

            self.assertEqual(12288, sizes["probe_context"])
            self.assertLessEqual(sizes["probe_internal"], sizes["probe_context"])
            self.assertLessEqual(sizes["probe_request"], 64)
            self.assertLessEqual(sizes["probe_post_result"], 32)
            self.assertLessEqual(sizes["probe_runtime_result"], 384)
            self.assertLessEqual(sizes["probe_snapshot"], 192)

            stack_file = source_object.with_suffix(".su")
            stack_sizes = []
            for line in stack_file.read_text(encoding="utf-8").splitlines():
                fields = line.split("\t")
                if len(fields) >= 2 and fields[1].isdigit():
                    stack_sizes.append(int(fields[1]))
            self.assertTrue(stack_sizes)
            self.assertLessEqual(max(stack_sizes), 192)

    def test_packet_names_outbox_010f_and_evidence_boundary(self) -> None:
        self.assertIn("OUTBOX-010F", self.packet)
        self.assertIn("Unified Delivery Runtime", self.packet)
        lowered = self.packet.casefold()
        self.assertIn("no real http", lowered)
        self.assertIn("not guardian", lowered)
        self.assertIn("not p0-sos", lowered)


if __name__ == "__main__":
    unittest.main()

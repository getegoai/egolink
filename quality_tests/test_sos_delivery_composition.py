"""Focused SOS-010I checks for the dormant single-owner composition.

The target C source and a fake-dependency lifecycle harness are cross-linked
for ESP32-S3. A native run is attempted only when a real host compiler exists.
Neither path performs storage, HTTP, NVS, GPIO, device, or network I/O.
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
COMPONENT = COMPONENTS / "sos_delivery_composition"
SOURCE = COMPONENT / "sos_delivery_composition.c"
HEADER = COMPONENT / "include" / "sos_delivery_composition.h"
CMAKE = COMPONENT / "CMakeLists.txt"
APP_MAIN = ROOT / "firmware" / "mqtt_heartbeat" / "main" / "app_main.c"
PACKET = ROOT / "docs" / "tasks" / "active" / "SOS-010_SOS_WALKING_SKELETON.md"


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


def _native_compiler() -> Path | None:
    for candidate in (shutil.which("gcc"), shutil.which("clang")):
        if candidate:
            return Path(candidate)
    return None


def _include_paths() -> tuple[Path, ...]:
    names = (
        "sos_delivery_composition",
        "location_outbox_adapter",
        "location_state_emitter",
        "location_policy_core",
        "p0_delivery_runtime",
        "p0_outbox_dispatcher",
        "persistent_priority_outbox",
        "sos_device_runtime",
        "sos_input",
        "sos_orchestrator",
        "sos_outbox_adapter",
        "sos_pending_edge_journal",
    )
    return tuple(COMPONENTS / name / "include" for name in names)


def _normalized(value: str) -> str:
    value = re.sub(r"(?m)^\s*\*\s?", "", value)
    return " ".join(value.split()).casefold()


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
    raise AssertionError(f"unterminated C function: {name}")


HARNESS = r"""
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "sos_delivery_composition.h"

void *memset(void *destination, int value, size_t length)
{
    unsigned char *cursor = (unsigned char *)destination;
    while (length > 0U) { *cursor++ = (unsigned char)value; --length; }
    return destination;
}

void *memcpy(void *destination, const void *source, size_t length)
{
    unsigned char *output = (unsigned char *)destination;
    const unsigned char *input = (const unsigned char *)source;
    while (length > 0U) { *output++ = *input++; --length; }
    return destination;
}

int memcmp(const void *left, const void *right, size_t length)
{
    const unsigned char *a = (const unsigned char *)left;
    const unsigned char *b = (const unsigned char *)right;
    while (length > 0U) {
        if (*a != *b) { return *a < *b ? -1 : 1; }
        ++a; ++b; --length;
    }
    return 0;
}

static egolink_sos_delivery_composition_t composition;
static egolink_sos_delivery_composition_drive_result_t nested_drive;
static char order[64];
static size_t order_length;
static unsigned int failure;
static unsigned int dependency_calls;
static unsigned int http_calls;
static unsigned int delivery_mode;
static unsigned int delivery_init_mode;
static unsigned int dispatcher_close_failures_remaining;
static unsigned int runtime_init_mode;
static bool pending_available;
static bool pending_durable;
static egolink_sos_device_runtime_callbacks_t captured_callbacks;
static egolink_p0_delivery_http_post_fn captured_http;
static void *captured_http_context;
static egolink_p0_delivery_runtime_lifecycle_t delivery_lifecycle;
static egolink_p0_delivery_runtime_phase_t delivery_phase;
static egolink_sos_device_runtime_lifecycle_t runtime_lifecycle;

#define CHECK(condition, code) do { \
    if (!(condition) && failure == 0U) { failure = (code); } \
} while (0)

static void append(char value)
{
    if (order_length + 1U < sizeof(order)) {
        order[order_length++] = value;
        order[order_length] = '\0';
    }
}

static int text_equal(const char *left, const char *right)
{
    while (*left != '\0' && *left == *right) { ++left; ++right; }
    return *left == *right;
}

egolink_outbox_status_t egolink_sos_outbox_adapter_bind(
    egolink_sos_outbox_adapter_t *adapter,
    egolink_outbox_t *outbox,
    const char *device_id)
{
    ++dependency_calls; append('b');
    (void)memset(adapter, 0, sizeof(*adapter));
    adapter->outbox = outbox;
    adapter->initialized = true;
    (void)memcpy(adapter->device_id, device_id, 11U);
    return EGOLINK_OUTBOX_OK;
}

void egolink_sos_outbox_adapter_unbind(egolink_sos_outbox_adapter_t *adapter)
{
    ++dependency_calls; append('u');
    (void)memset(adapter, 0, sizeof(*adapter));
}

egolink_sos_pending_edge_status_t egolink_sos_pending_edge_journal_init(
    egolink_sos_pending_edge_journal_t *journal,
    const egolink_sos_pending_edge_storage_t *storage,
    const char *device_id)
{
    (void)journal; (void)storage; (void)device_id;
    ++dependency_calls; append('j');
    return EGOLINK_SOS_PENDING_EDGE_OK;
}

bool egolink_sos_pending_edge_journal_is_initialized(
    const egolink_sos_pending_edge_journal_t *journal)
{
    return journal != NULL;
}

bool egolink_sos_pending_edge_journal_matches_device(
    const egolink_sos_pending_edge_journal_t *journal,
    const char *device_id)
{
    return journal != NULL && text_equal(device_id, "wearable-1");
}

void egolink_p0_outbox_dispatcher_default_config(
    egolink_p0_outbox_dispatcher_config_t *config)
{
    (void)memset(config, 0, sizeof(*config));
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_init(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    const egolink_p0_outbox_dispatcher_config_t *config,
    egolink_outbox_t *outbox,
    egolink_location_outbox_adapter_t *location,
    egolink_sos_outbox_adapter_t *sos)
{
    (void)dispatcher; ++dependency_calls; append('d');
    CHECK(config->enabled, 1U);
    CHECK(location->outbox == outbox && sos->outbox == outbox, 2U);
    return EGOLINK_P0_OUTBOX_OK;
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_close(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *view,
    egolink_p0_outbox_finish_result_t *result)
{
    (void)dispatcher; (void)now_ms; (void)view;
    (void)memset(result, 0, sizeof(*result)); append('D');
    if (dispatcher_close_failures_remaining > 0U) {
        --dispatcher_close_failures_remaining;
        return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
    }
    return EGOLINK_P0_OUTBOX_CLOSED_STATUS;
}

void egolink_p0_delivery_runtime_default_config(
    egolink_p0_delivery_runtime_config_t *config)
{
    (void)memset(config, 0, sizeof(*config));
    config->max_post_duration_ms = 30000U;
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_init(
    egolink_p0_delivery_runtime_t *runtime,
    const egolink_p0_delivery_runtime_config_t *config,
    egolink_p0_outbox_dispatcher_t *dispatcher)
{
    (void)runtime; (void)dispatcher; ++dependency_calls; append('p');
    CHECK(config->enabled && config->http_post != NULL, 3U);
    if (delivery_init_mode != 0U) {
        return EGOLINK_P0_DELIVERY_INVALID_CONFIG;
    }
    captured_http = config->http_post;
    captured_http_context = config->http_context;
    delivery_lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE;
    delivery_phase = EGOLINK_P0_DELIVERY_PHASE_IDLE;
    return EGOLINK_P0_DELIVERY_OK;
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_current_status(
    const egolink_p0_delivery_runtime_t *runtime,
    egolink_p0_delivery_runtime_snapshot_t *snapshot)
{
    (void)runtime; (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->lifecycle = delivery_lifecycle;
    snapshot->phase = delivery_phase;
    snapshot->enabled = delivery_lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE;
    snapshot->dispatcher_bound = delivery_lifecycle != EGOLINK_P0_DELIVERY_RUNTIME_CLOSED;
    if (delivery_phase == EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED) {
        return EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED;
    }
    if (delivery_phase == EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED) {
        return EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED;
    }
    if (delivery_phase == EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED) {
        return EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
    }
    if (delivery_lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED) {
        return EGOLINK_P0_DELIVERY_CANCELLED_STATUS;
    }
    if (delivery_lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CLOSED) {
        return EGOLINK_P0_DELIVERY_CLOSED_STATUS;
    }
    return EGOLINK_P0_DELIVERY_OK;
}

static egolink_p0_delivery_runtime_status_t fake_drive(
    egolink_p0_delivery_runtime_result_t *result)
{
    (void)memset(result, 0, sizeof(*result)); append('x');
    if (captured_http != NULL) {
        static const uint8_t body[] = {'{', '}'};
        uint8_t response[8];
        egolink_p0_delivery_post_request_t request;
        egolink_p0_delivery_post_result_t post_result;
        (void)memset(&request, 0, sizeof(request));
        (void)memset(&post_result, 0, sizeof(post_result));
        request.route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
        request.path = EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH;
        request.body = body; request.body_length = sizeof(body);
        request.response = response; request.response_capacity = sizeof(response);
        request.priority = EGOLINK_OUTBOX_PRIORITY_CRITICAL;
        (void)captured_http(captured_http_context, &request, &post_result);
    }
    result->route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
    if (delivery_mode == 1U) {
        result->durable_record_retained = true;
        return EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED;
    }
    return EGOLINK_P0_DELIVERY_ACK_DELETED;
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_drive_once(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    (void)runtime; (void)now_ms; return fake_drive(result);
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_prepare(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    (void)runtime; (void)now_ms; (void)memset(result, 0, sizeof(*result));
    delivery_phase = EGOLINK_P0_DELIVERY_PHASE_PREPARED;
    return EGOLINK_P0_DELIVERY_PREPARED;
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_execute_prepared(
    egolink_p0_delivery_runtime_t *runtime,
    egolink_p0_delivery_runtime_result_t *result)
{
    (void)runtime; (void)memset(result, 0, sizeof(*result));
    delivery_phase = EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY;
    return EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY;
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_settle_prepared(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    (void)runtime; (void)now_ms; (void)memset(result, 0, sizeof(*result));
    delivery_phase = EGOLINK_P0_DELIVERY_PHASE_IDLE;
    return EGOLINK_P0_DELIVERY_ACK_DELETED;
}

egolink_p0_delivery_sos_preempt_status_t
egolink_p0_delivery_runtime_signal_durable_sos(
    egolink_p0_delivery_runtime_t *runtime)
{
    (void)runtime;
    return EGOLINK_P0_DELIVERY_SOS_PREEMPT_NO_ACTIVE_LOCATION;
}

bool egolink_p0_delivery_runtime_location_cancel_requested(
    void *context,
    uint32_t transfer_generation)
{
    (void)context; (void)transfer_generation; return false;
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_retry_finish(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    (void)runtime; (void)now_ms; append('r');
    delivery_phase = EGOLINK_P0_DELIVERY_PHASE_IDLE;
    (void)memset(result, 0, sizeof(*result));
    return EGOLINK_P0_DELIVERY_ACK_DELETED;
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_retry_begin_recovery(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    (void)runtime; (void)now_ms; append('r');
    delivery_phase = EGOLINK_P0_DELIVERY_PHASE_IDLE;
    (void)memset(result, 0, sizeof(*result));
    return EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED;
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_cancel(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    (void)runtime; (void)now_ms; (void)memset(result, 0, sizeof(*result));
    append('q'); delivery_lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED;
    return EGOLINK_P0_DELIVERY_CANCELLED_STATUS;
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_close(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    (void)runtime; (void)now_ms; (void)memset(result, 0, sizeof(*result));
    append('P'); delivery_lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_CLOSED;
    return EGOLINK_P0_DELIVERY_CLOSED_STATUS;
}

void egolink_sos_device_runtime_default_config(
    egolink_sos_device_runtime_config_t *config)
{
    (void)memset(config, 0, sizeof(*config));
    config->input.debounce_ms = 50U;
    config->input.long_press_ms = 2000U;
    config->first_source_sequence = 1U;
}

egolink_sos_device_runtime_status_t egolink_sos_device_runtime_init(
    egolink_sos_device_runtime_t *runtime,
    const egolink_sos_device_runtime_config_t *config,
    egolink_outbox_t *outbox,
    egolink_sos_outbox_adapter_t *adapter,
    egolink_sos_pending_edge_journal_t *journal,
    egolink_location_policy_core_t *policy,
    bool initial_pressed,
    uint64_t now_ms)
{
    (void)runtime; (void)outbox; (void)adapter; (void)journal; (void)policy;
    (void)initial_pressed; (void)now_ms; ++dependency_calls; append('f');
    CHECK(config->enabled && config->callbacks.wake_sender != NULL, 4U);
    captured_callbacks = config->callbacks;
    runtime_lifecycle = EGOLINK_SOS_DEVICE_RUNTIME_ACTIVE;
    if (runtime_init_mode == 2U) { return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_CONFIG; }
    if (runtime_init_mode == 1U) {
        pending_available = true; pending_durable = true;
        return EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED;
    }
    return EGOLINK_SOS_DEVICE_RUNTIME_OK;
}

static egolink_sos_device_runtime_status_t fake_event(
    egolink_sos_device_runtime_result_t *result)
{
    egolink_sos_branch_identity_t identity;
    egolink_sos_sender_wake_request_t wake;
    (void)memset(result, 0, sizeof(*result));
    (void)memset(&identity, 0, sizeof(identity));
    wake.identity = &identity;
    wake.durable_manual_sos_available = true;
    wake.persistence_state = EGOLINK_SOS_PERSISTENCE_COMMITTED;
    if (captured_callbacks.local_feedback != NULL) {
        (void)captured_callbacks.local_feedback(
            captured_callbacks.local_feedback_context, NULL); append('l');
    }
    if (captured_callbacks.request_urgent_location != NULL) {
        (void)captured_callbacks.request_urgent_location(
            captured_callbacks.location_context, NULL); append('o');
    }
    if (captured_callbacks.request_call != NULL) {
        (void)captured_callbacks.request_call(
            captured_callbacks.call_context, NULL); append('c');
    }
    CHECK(http_calls == 0U, 5U);
    CHECK(captured_callbacks.wake_sender(
        captured_callbacks.sender_context, &wake), 6U);
    append('w');
    result->qualified_edge = true;
    result->durable_manual_sos_available = true;
    return EGOLINK_SOS_DEVICE_RUNTIME_OK;
}

egolink_sos_device_runtime_status_t egolink_sos_device_runtime_process_sample(
    egolink_sos_device_runtime_t *runtime,
    bool pressed,
    uint64_t now_ms,
    egolink_sos_device_runtime_result_t *result)
{
    (void)runtime; (void)pressed; (void)now_ms; append('s');
    return fake_event(result);
}

egolink_sos_device_runtime_status_t
egolink_sos_device_runtime_replay_pending(
    egolink_sos_device_runtime_t *runtime,
    uint64_t now_ms,
    egolink_sos_device_runtime_result_t *result)
{
    (void)runtime; (void)now_ms; append('y');
    pending_available = false; pending_durable = false;
    return fake_event(result);
}

egolink_sos_device_runtime_status_t egolink_sos_device_runtime_cancel(
    egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_shutdown_result_t *result)
{
    (void)runtime; (void)memset(result, 0, sizeof(*result)); append('a');
    if (pending_available && !pending_durable) {
        return EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED;
    }
    runtime_lifecycle = EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED;
    return EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS;
}

egolink_sos_device_runtime_status_t egolink_sos_device_runtime_close(
    egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_shutdown_result_t *result)
{
    (void)runtime; (void)memset(result, 0, sizeof(*result)); append('A');
    if (pending_available && !pending_durable) {
        return EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED;
    }
    runtime_lifecycle = EGOLINK_SOS_DEVICE_RUNTIME_CLOSED;
    return EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS;
}

egolink_sos_device_runtime_status_t
egolink_sos_device_runtime_current_status(
    const egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_snapshot_t *snapshot)
{
    (void)runtime; (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->lifecycle = runtime_lifecycle;
    snapshot->pending_edge_available = pending_available;
    snapshot->pending_edge_durable = pending_durable;
    if (pending_available) {
        return EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED;
    }
    if (runtime_lifecycle == EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED) {
        return EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS;
    }
    if (runtime_lifecycle == EGOLINK_SOS_DEVICE_RUNTIME_CLOSED) {
        return EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS;
    }
    return EGOLINK_SOS_DEVICE_RUNTIME_OK;
}

static egolink_sos_pending_edge_storage_result_t load_record(
    void *context, void *destination, size_t capacity, size_t *length)
{
    (void)context; (void)destination; (void)capacity; *length = 0U;
    return EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND;
}

static egolink_sos_pending_edge_storage_result_t store_record(
    void *context, const void *source, size_t length)
{
    (void)context; (void)source; (void)length;
    return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
}

static egolink_sos_pending_edge_storage_result_t clear_record(void *context)
{
    (void)context; return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
}

static bool feedback(void *context, const egolink_sos_branch_identity_t *request)
{
    (void)context; (void)request;
    CHECK(egolink_sos_delivery_composition_drive_once(
        &composition, 99U, &nested_drive) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL, 7U);
    return true;
}

static bool location(
    void *context,
    const egolink_sos_location_enqueue_request_t *request)
{
    (void)context; (void)request; return true;
}

static bool call(void *context, const egolink_sos_call_request_t *request)
{
    (void)context; (void)request; return true;
}

static egolink_p0_delivery_post_outcome_t http_post(
    void *context,
    const egolink_p0_delivery_post_request_t *request,
    egolink_p0_delivery_post_result_t *result)
{
    (void)context; ++http_calls;
    CHECK(request->route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS, 8U);
    CHECK(request->priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL, 9U);
    (void)memset(result, 0, sizeof(*result));
    result->http_status_code = 200U; result->completion_time_ms = 101U;
    return EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE;
}

static void reset_globals(void)
{
    (void)memset(&composition, 0, sizeof(composition));
    (void)memset(order, 0, sizeof(order)); order_length = 0U;
    dependency_calls = 0U; http_calls = 0U; delivery_mode = 0U;
    delivery_init_mode = 0U; dispatcher_close_failures_remaining = 0U;
    runtime_init_mode = 0U; pending_available = false; pending_durable = false;
    captured_http = NULL; captured_http_context = NULL;
    delivery_lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_NEVER_INITIALIZED;
    delivery_phase = EGOLINK_P0_DELIVERY_PHASE_IDLE;
    runtime_lifecycle = EGOLINK_SOS_DEVICE_RUNTIME_NEVER_INITIALIZED;
}

static void make_config(
    egolink_sos_delivery_composition_config_t *config,
    egolink_outbox_t *outbox,
    egolink_location_outbox_adapter_t *location_adapter,
    egolink_location_policy_core_t *policy,
    egolink_sos_pending_edge_storage_t *storage)
{
    egolink_sos_delivery_composition_default_config(config);
    config->enabled = true; config->device_id = "wearable-1";
    config->session_id = "session-1"; config->boot_count = 1U;
    config->local_feedback = feedback;
    config->request_urgent_location = location;
    config->request_call = call; config->http_post = http_post;
    (void)memset(outbox, 0, sizeof(*outbox));
    (void)memset(location_adapter, 0, sizeof(*location_adapter));
    location_adapter->outbox = outbox; location_adapter->initialized = true;
    (void)memcpy(location_adapter->device_id, "wearable-1", 11U);
    (void)memset(policy, 0, sizeof(*policy)); policy->initialized = true;
    storage->context = NULL; storage->load_record = load_record;
    storage->store_record = store_record; storage->clear_record = clear_record;
}

int main(void)
{
    egolink_outbox_t outbox;
    egolink_location_outbox_adapter_t location_adapter;
    egolink_location_policy_core_t policy;
    egolink_sos_pending_edge_storage_t storage;
    egolink_sos_delivery_composition_config_t config;
    egolink_sos_delivery_composition_event_result_t event_result;
    egolink_sos_delivery_composition_drive_result_t drive_result;
    egolink_sos_delivery_composition_shutdown_result_t shutdown;
    egolink_sos_delivery_composition_snapshot_t snapshot;

    reset_globals();
    egolink_sos_delivery_composition_default_config(&config);
    CHECK(egolink_sos_delivery_composition_init(
        &composition, &config, NULL, NULL, NULL, NULL, false, 0U) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS, 10U);
    CHECK(dependency_calls == 0U, 11U);
    CHECK(egolink_sos_delivery_composition_close(
        &composition, 0U, &shutdown) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS, 12U);

    reset_globals(); make_config(
        &config, &outbox, &location_adapter, &policy, &storage);
    CHECK(egolink_sos_delivery_composition_init(
        &composition, &config, &outbox, &location_adapter, &policy,
        &storage, false, 0U) == EGOLINK_SOS_DELIVERY_COMPOSITION_OK, 13U);
    CHECK(text_equal(order, "bjdpf"), 14U);
    order_length = 0U; order[0] = '\0';
    CHECK(egolink_sos_delivery_composition_process_sample(
        &composition, true, 50U, &event_result) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_OK, 15U);
    CHECK(text_equal(order, "slocw"), 16U);
    CHECK(http_calls == 0U && event_result.external_drive_required, 17U);
    CHECK(egolink_sos_delivery_composition_drive_once(
        &composition, 100U, &drive_result) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_DELETED, 18U);
    CHECK(http_calls == 1U && drive_result.wake_intent_consumed, 19U);

    delivery_mode = 1U;
    CHECK(egolink_sos_delivery_composition_drive_once(
        &composition, 200U, &drive_result) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_DELIVERY_RETAINED, 20U);
    CHECK(drive_result.durable_record_may_remain, 21U);
    delivery_phase = EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED;
    CHECK(egolink_sos_delivery_composition_drive_once(
        &composition, 201U, &drive_result) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_DELETED, 22U);
    CHECK(drive_result.recovery_retry_called, 23U);

    CHECK(egolink_sos_delivery_composition_cancel(
        &composition, 300U, &shutdown) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS, 24U);
    CHECK(text_equal(order + order_length - 2U, "aq"), 25U);
    CHECK(egolink_sos_delivery_composition_close(
        &composition, 301U, &shutdown) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS, 26U);
    CHECK(shutdown.sos_adapter_unbound, 27U);

    reset_globals(); make_config(
        &config, &outbox, &location_adapter, &policy, &storage);
    CHECK(egolink_sos_delivery_composition_init(
        &composition, &config, &outbox, &location_adapter, &policy,
        &storage, false, 0U) == EGOLINK_SOS_DELIVERY_COMPOSITION_OK, 60U);
    CHECK(egolink_sos_delivery_composition_prepare(
        &composition, 1U, &drive_result) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_PREPARED, 61U);
    CHECK(delivery_phase == EGOLINK_P0_DELIVERY_PHASE_PREPARED, 62U);
    CHECK(egolink_sos_delivery_composition_cancel(
        &composition, 2U, &shutdown) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS, 63U);
    CHECK(http_calls == 0U && shutdown.delivery_shutdown_called, 64U);

    reset_globals(); make_config(
        &config, &outbox, &location_adapter, &policy, &storage);
    runtime_init_mode = 1U;
    CHECK(egolink_sos_delivery_composition_init(
        &composition, &config, &outbox, &location_adapter, &policy,
        &storage, false, 0U) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_PENDING_REPLAY_REQUIRED, 28U);
    CHECK(egolink_sos_delivery_composition_replay_pending(
        &composition, 10U, &event_result) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_OK, 29U);
    CHECK(event_result.external_drive_required && http_calls == 0U, 30U);

    pending_available = true; pending_durable = false;
    CHECK(egolink_sos_delivery_composition_cancel(
        &composition, 11U, &shutdown) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_PENDING_REPLAY_REQUIRED, 31U);
    CHECK(!shutdown.delivery_shutdown_called, 32U);
    pending_available = false; pending_durable = false;
    CHECK(egolink_sos_delivery_composition_close(
        &composition, 12U, &shutdown) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS, 33U);

    reset_globals(); make_config(
        &config, &outbox, &location_adapter, &policy, &storage);
    runtime_init_mode = 2U;
    CHECK(egolink_sos_delivery_composition_init(
        &composition, &config, &outbox, &location_adapter, &policy,
        &storage, false, 0U) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_INITIALIZATION_FAILED, 34U);
    CHECK(text_equal(order, "bjdpfAPu"), 35U);

    reset_globals(); make_config(
        &config, &outbox, &location_adapter, &policy, &storage);
    (void)memcpy(location_adapter.device_id, "wrong-id", 9U);
    CHECK(egolink_sos_delivery_composition_init(
        &composition, &config, &outbox, &location_adapter, &policy,
        &storage, false, 0U) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_CONFIG, 36U);
    CHECK(dependency_calls == 0U, 37U);

    reset_globals(); make_config(
        &config, &outbox, &location_adapter, &policy, &storage);
    delivery_init_mode = 1U;
    dispatcher_close_failures_remaining = 1U;
    CHECK(egolink_sos_delivery_composition_init(
        &composition, &config, &outbox, &location_adapter, &policy,
        &storage, false, 0U) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED, 38U);
    CHECK(text_equal(order, "bjdpD"), 39U);
    CHECK(egolink_sos_delivery_composition_drive_once(
        &composition, 1U, &drive_result) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED, 40U);
    CHECK(http_calls == 0U, 41U);
    CHECK(egolink_sos_delivery_composition_current_status(
        &composition, &snapshot) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED, 42U);
    CHECK(snapshot.sos_adapter_owned_and_bound, 43U);
    CHECK(egolink_sos_delivery_composition_close(
        &composition, 2U, &shutdown) ==
        EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS, 44U);
    CHECK(text_equal(order, "bjdpDDu"), 45U);
    CHECK(shutdown.sos_adapter_unbound &&
          shutdown.caller_dependencies_not_deinitialized, 46U);
    CHECK(shutdown.rollback_cleanup_attempted &&
          shutdown.owned_dispatcher_cleanup_attempted &&
          !shutdown.delivery_shutdown_called &&
          !shutdown.sos_runtime_shutdown_called, 47U);

    return (int)failure;
}
"""


class SosDeliveryCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.cmake = CMAKE.read_text(encoding="utf-8")
        cls.packet = PACKET.read_text(encoding="utf-8")

    def test_component_is_default_disabled_and_unwired(self) -> None:
        self.assertIn('SRCS "sos_delivery_composition.c"', self.cmake)
        for dependency in (
            "location_outbox_adapter",
            "location_policy_core",
            "p0_delivery_runtime",
            "p0_outbox_dispatcher",
            "persistent_priority_outbox",
            "sos_device_runtime",
            "sos_outbox_adapter",
            "sos_pending_edge_journal",
        ):
            self.assertIn(dependency, self.cmake)
        self.assertIn("config->enabled = false", self.source)
        self.assertNotIn(
            "sos_delivery_composition",
            APP_MAIN.read_text(encoding="utf-8"),
        )
        for forbidden in (
            "app_main",
            "gpio_",
            "nvs_",
            "nvs_flash",
            "esp_http_client",
            "mqtt_client",
            "esp_wifi",
            "freertos/",
            "xtaskcreate",
            "esp_log",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source.casefold())

    def test_init_owns_one_adapter_and_stages_then_rolls_back_in_reverse(self) -> None:
        body = _function_body(
            self.source, "egolink_sos_delivery_composition_init("
        )
        stages = (
            "egolink_sos_outbox_adapter_bind(",
            "egolink_sos_pending_edge_journal_init(",
            "egolink_p0_outbox_dispatcher_init(",
            "egolink_p0_delivery_runtime_init(",
            "egolink_sos_device_runtime_init(",
        )
        offsets = tuple(body.index(stage) for stage in stages)
        self.assertEqual(tuple(sorted(offsets)), offsets)
        rollback = _function_body(self.source, "close_owned_delivery_for_rollback(")
        sos_rollback = _function_body(self.source, "close_owned_sos_for_rollback(")
        self.assertIn("egolink_sos_device_runtime_close(", sos_rollback)
        self.assertIn("egolink_p0_delivery_runtime_close(", rollback)
        self.assertIn("egolink_p0_delivery_runtime_retry_finish(", rollback)
        self.assertIn("egolink_p0_delivery_runtime_retry_begin_recovery(", rollback)
        self.assertIn("egolink_p0_outbox_dispatcher_close(", rollback)
        release = _function_body(self.source, "release_memory_only_owned_bindings(")
        self.assertIn("egolink_sos_outbox_adapter_unbind(", release)
        for forbidden in (
            "egolink_location_outbox_adapter_deinit(",
            "egolink_outbox_deinit(",
            "nvs_",
            "clear_record(",
        ):
            self.assertNotIn(forbidden, sos_rollback + rollback + release)

    def test_exact_caller_identity_and_shared_outbox_are_validated(self) -> None:
        validate = _function_body(self.source, "validate_enabled_config(")
        self.assertIn("location_adapter->outbox == shared_outbox", validate)
        self.assertIn(
            "exact_identifier(config->device_id, location_adapter->device_id)",
            validate,
        )
        self.assertIn("policy_core->initialized", validate)
        self.assertIn("pending_storage->load_record", validate)
        self.assertIn("pending_storage->store_record", validate)
        self.assertIn("pending_storage->clear_record", validate)

    def test_wake_is_bounded_metadata_and_never_drives_recursively(self) -> None:
        wake = _function_body(self.source, "record_sender_wake(")
        self.assertIn("wake_intent_pending = true", wake)
        self.assertIn("increment_saturated", wake)
        for forbidden in (
            "drive_once(",
            "http_post",
            "dispatcher_begin",
            "outbox_begin",
            "payload",
        ):
            self.assertNotIn(forbidden, wake)
        run_event = _function_body(self.source, "run_event(")
        self.assertNotIn("egolink_p0_delivery_runtime_drive_once", run_event)

    def test_drive_is_explicit_single_action_and_recovery_aware(self) -> None:
        body = _function_body(
            self.source, "egolink_sos_delivery_composition_drive_once("
        )
        self.assertEqual(1, body.count("egolink_p0_delivery_runtime_drive_once("))
        self.assertEqual(1, body.count("egolink_p0_delivery_runtime_retry_finish("))
        self.assertEqual(
            1, body.count("egolink_p0_delivery_runtime_retry_begin_recovery(")
        )
        self.assertIn("wake_intent_pending = false", body)
        self.assertIn("RECOVERY_REQUIRED", body)
        self.assertNotRegex(body, r"\b(?:while|for)\s*\(")

    def test_shutdown_preserves_journal_queue_and_caller_ownership(self) -> None:
        body = _function_body(self.source, "shutdown_composition(")
        self.assertIn("volatile_pending_edge(internal)", body)
        self.assertIn("delivery_shutdown_blocker(internal)", body)
        self.assertIn("pending_journal_untouched = true", body)
        self.assertIn("outbox_records_retained = true", body)
        self.assertIn("caller_dependencies_not_deinitialized = true", body)
        self.assertLess(
            body.index("egolink_sos_device_runtime_close("),
            body.index("egolink_p0_delivery_runtime_close("),
        )
        for forbidden in (
            "egolink_outbox_handle_ack",
            "egolink_outbox_deinit",
            "egolink_location_outbox_adapter_deinit",
            "clear_record(",
        ):
            self.assertNotIn(forbidden, body)

    def test_contract_documents_single_owner_and_nonclaims(self) -> None:
        prose = _normalized(self.header + "\n" + self.packet)
        for phrase in (
            "one external task or mutex must own",
            "local busy guard is not a lock",
            "never recursively selects, sends or calls the http callback",
            "must explicitly call `drive_once`",
            "critical manual sos priority",
            "does not deinitialize the caller's outbox",
            "p0-sos",
        ):
            self.assertIn(phrase, prose)
        self.assertIsNone(re.search(r"\b(?:malloc|calloc|realloc|free)\s*\(", self.source))

    def test_actual_c_and_fake_lifecycle_harness_cross_link_strictly(self) -> None:
        toolchain = _esp_toolchain()
        if toolchain is None:
            self.skipTest("ESP32-S3 cross compiler or ESP-IDF unavailable")
        compiler, _ = toolchain
        with tempfile.TemporaryDirectory(prefix="egolink-sos-i-cross-") as temp:
            temp_path = Path(temp)
            harness = temp_path / "harness.c"
            harness.write_text(textwrap.dedent(HARNESS), encoding="utf-8")
            output = temp_path / "harness.elf"
            command = [
                str(compiler),
                "-std=c11",
                "-ffreestanding",
                "-fno-builtin",
                "-nostdlib",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wconversion",
                "-Wformat=2",
                "-Wshadow",
                "-Wsign-conversion",
                *(f"-I{path}" for path in _include_paths()),
                str(SOURCE),
                str(harness),
                "-Wl,-e,main",
                "-o",
                str(output),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(output.is_file())

    def test_fake_lifecycle_harness_executes_when_native_compiler_exists(self) -> None:
        compiler = _native_compiler()
        if compiler is None:
            self.skipTest("native host GCC/Clang unavailable")
        with tempfile.TemporaryDirectory(prefix="egolink-sos-i-native-") as temp:
            temp_path = Path(temp)
            harness = temp_path / "harness.c"
            harness.write_text(textwrap.dedent(HARNESS), encoding="utf-8")
            output = temp_path / "harness.exe"
            command = [
                str(compiler),
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wconversion",
                "-Wformat=2",
                "-Wshadow",
                "-Wsign-conversion",
                *(f"-I{path}" for path in _include_paths()),
                str(SOURCE),
                str(harness),
                "-o",
                str(output),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            executed = subprocess.run(
                [str(output)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(0, executed.returncode, executed.stderr)


if __name__ == "__main__":
    unittest.main()

/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 */

#include "call020_device_control_responder.h"

#include <limits.h>
#include <string.h>

#include "call020_device_control_wire.h"
#include "driver/usb_serial_jtag.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"
#include "sdkconfig.h"

#if defined(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER) && \
    CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER
#if !defined(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER) || \
    !CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER
#error "CALL-020Q requires CALL-020G operator runner"
#endif
#if !defined(CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT) || \
    !CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT
#error "CALL-020Q requires the exclusive USB Serial/JTAG endpoint profile"
#endif
#if !defined(CONFIG_ESP_CONSOLE_NONE) || !CONFIG_ESP_CONSOLE_NONE
#error "CALL-020Q requires CONFIG_ESP_CONSOLE_NONE"
#endif
#if !defined(CONFIG_ESP_CONSOLE_SECONDARY_NONE) || \
    !CONFIG_ESP_CONSOLE_SECONDARY_NONE
#error "CALL-020Q requires CONFIG_ESP_CONSOLE_SECONDARY_NONE"
#endif
#if !defined(CONFIG_LOG_DEFAULT_LEVEL_NONE) || \
    !CONFIG_LOG_DEFAULT_LEVEL_NONE
#error "CALL-020Q requires CONFIG_LOG_DEFAULT_LEVEL_NONE"
#endif
#if !defined(CONFIG_BOOTLOADER_LOG_LEVEL_NONE) || \
    !CONFIG_BOOTLOADER_LOG_LEVEL_NONE
#error "CALL-020Q requires CONFIG_BOOTLOADER_LOG_LEVEL_NONE"
#endif
#if defined(CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN) && \
    CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN
#error "CALL-020Q cannot coexist with CALL-010 autorun"
#endif
#endif

#define RESPONDER_MAGIC UINT32_C(0x43413251)

typedef enum {
    RESPONSE_NONE = 0,
    RESPONSE_PREPARE,
    RESPONSE_ACK,
    RESPONSE_TELEMETRY_UNAVAILABLE,
} response_kind_t;

typedef struct {
    bool used;
    call020_control_action_t action;
    uint32_t timeout_ms;
    char run_id[CALL020_CONTROL_RUN_ID_CAPACITY];
    char operation_id[CALL020_CONTROL_OPERATION_ID_CAPACITY];
    response_kind_t response_kind;
    char ack_state[16];
    call020_control_pre_start_telemetry_t telemetry;
} operation_cache_entry_t;

typedef enum {
    TRANSFER_OK = 0,
    TRANSFER_ZERO_PROGRESS,
    TRANSFER_PARTIAL,
    TRANSFER_UNKNOWN,
} control_transfer_result_t;

typedef struct {
    uint32_t magic;
    call020_device_control_responder_config_t config;
    call020_device_control_responder_metadata_t metadata;
    call020_usb_driver_lease_t lease;
    call020_operator_session_descriptor_t descriptor;
    operation_cache_entry_t operations[
        CALL020_DEVICE_CONTROL_MAX_OPERATION_CACHE];
    uint32_t operation_count;
    bool runner_prepared;
    bool runner_closed;
    bool lease_cleanup_required;
    char bound_run_id[CALL020_CONTROL_RUN_ID_CAPACITY];
    uint8_t request_frame[CALL020_CONTROL_MAX_FRAME_BYTES];
    uint8_t response_frame[CALL020_CONTROL_MAX_FRAME_BYTES];
} responder_internal_t;

_Static_assert(
    sizeof(responder_internal_t) <= CALL020_DEVICE_CONTROL_CONTEXT_BYTES,
    "CALL-020Q opaque context is too small");
_Static_assert(
    _Alignof(responder_internal_t) <=
        _Alignof(call020_device_control_responder_t),
    "CALL-020Q opaque context alignment is insufficient");
_Static_assert(
    CALL020_CONTROL_MAX_FRAME_BYTES <= UINT32_MAX,
    "CALL-020Q frame must fit the IDF USB read API");

static responder_internal_t *internal_of(
    call020_device_control_responder_t *responder)
{
    return (responder_internal_t *)responder;
}

static const responder_internal_t *const_internal_of(
    const call020_device_control_responder_t *responder)
{
    return (const responder_internal_t *)responder;
}

static esp_err_t preserve_first_error(esp_err_t current, esp_err_t candidate)
{
    return current == ESP_OK && candidate != ESP_OK ? candidate : current;
}

static bool dedicated_build_enabled(void)
{
#if defined(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER) && \
    CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER && \
    defined(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER) && \
    CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER && \
    defined(CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT) && \
    CONFIG_EGOLINK_CALL020_USB_SERIAL_JTAG_ENDPOINT && \
    defined(CONFIG_ESP_CONSOLE_NONE) && CONFIG_ESP_CONSOLE_NONE && \
    defined(CONFIG_ESP_CONSOLE_SECONDARY_NONE) && \
    CONFIG_ESP_CONSOLE_SECONDARY_NONE && \
    defined(CONFIG_LOG_DEFAULT_LEVEL_NONE) && \
    CONFIG_LOG_DEFAULT_LEVEL_NONE && \
    defined(CONFIG_BOOTLOADER_LOG_LEVEL_NONE) && \
    CONFIG_BOOTLOADER_LOG_LEVEL_NONE && \
    (!defined(CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN) || \
     !CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN)
    return true;
#else
    return false;
#endif
}

static bool config_valid(
    const call020_device_control_responder_config_t *config)
{
    return config != NULL && config->result_phase_enabled == false &&
        config->frame_wait_timeout_ms > 0U &&
        config->frame_wait_timeout_ms <= UINT32_C(10000) &&
        config->io_wait_slice_ms > 0U &&
        config->io_wait_slice_ms <= UINT32_C(20) &&
        config->max_io_calls >= UINT32_C(2) &&
        config->max_io_calls <= CALL020_DEVICE_CONTROL_MAX_IO_CALLS &&
        config->max_operation_timeout_ms > 0U &&
        config->max_operation_timeout_ms <= UINT32_C(10000);
}

static bool checked_deadline_us(
    uint64_t start_us,
    uint32_t timeout_ms,
    uint64_t *deadline_us)
{
    uint64_t duration_us = (uint64_t)timeout_ms * UINT64_C(1000);
    if (deadline_us == NULL || UINT64_MAX - start_us < duration_us) {
        return false;
    }
    *deadline_us = start_us + duration_us;
    return true;
}

static bool now_us(uint64_t *value)
{
    if (value == NULL) {
        return false;
    }
    int64_t observed = esp_timer_get_time();
    if (observed < 0) {
        return false;
    }
    *value = (uint64_t)observed;
    return true;
}

static bool operation_budget_available(uint64_t deadline_us)
{
    uint64_t current_us = 0U;
    return now_us(&current_us) && current_us < deadline_us;
}

static bool operation_completed_within_deadline(uint64_t deadline_us)
{
    uint64_t completed_us = 0U;
    return now_us(&completed_us) && completed_us <= deadline_us;
}

static TickType_t bounded_ticks(
    uint64_t current_us,
    uint64_t deadline_us,
    uint32_t slice_ms)
{
    if (current_us >= deadline_us) {
        return 0;
    }
    uint64_t remaining_us = deadline_us - current_us;
    uint64_t slice_us = (uint64_t)slice_ms * UINT64_C(1000);
    uint64_t wait_us = remaining_us < slice_us ? remaining_us : slice_us;
    /*
     * Round down. A zero-tick poll is intentional when less than one RTOS
     * tick remains: rounding up would authorize the driver to outlive the
     * caller's monotonic deadline.
     */
    uint64_t ticks =
        (wait_us * (uint64_t)configTICK_RATE_HZ) / UINT64_C(1000000);
    if (ticks > (uint64_t)portMAX_DELAY) {
        ticks = (uint64_t)portMAX_DELAY;
    }
    return (TickType_t)ticks;
}

static void clear_io_buffers(responder_internal_t *internal)
{
    call020_control_wire_clear(
        internal->request_frame, sizeof(internal->request_frame));
    internal->metadata.request_buffers_cleared++;
    call020_control_wire_clear(
        internal->response_frame, sizeof(internal->response_frame));
    internal->metadata.response_buffers_cleared++;
}

static void clear_control_identities(responder_internal_t *internal)
{
    call020_control_wire_clear(
        internal->operations, sizeof(internal->operations));
    call020_control_wire_clear(
        internal->bound_run_id, sizeof(internal->bound_run_id));
    call020_control_wire_clear(
        &internal->descriptor, sizeof(internal->descriptor));
    internal->operation_count = 0U;
    internal->metadata.run_id_bound = false;
}

static void latch_terminal(
    responder_internal_t *internal,
    call020_device_control_terminal_reason_t reason,
    esp_err_t error,
    bool start_unknown)
{
    if (internal->metadata.terminal_reason ==
        CALL020_DEVICE_CONTROL_TERMINAL_NONE) {
        internal->metadata.terminal_reason = reason;
    }
    internal->metadata.first_error = preserve_first_error(
        internal->metadata.first_error,
        error == ESP_OK ? ESP_FAIL : error);
    internal->metadata.state = start_unknown
        ? CALL020_DEVICE_CONTROL_START_UNKNOWN
        : CALL020_DEVICE_CONTROL_TERMINAL;
    internal->metadata.control_writes_permanently_disabled = true;
}

static esp_err_t latch_operation_deadline(
    responder_internal_t *internal,
    esp_err_t observed_error,
    bool start_unknown)
{
    esp_err_t error = observed_error == ESP_OK
        ? ESP_ERR_TIMEOUT
        : observed_error;
    latch_terminal(
        internal,
        CALL020_DEVICE_CONTROL_TERMINAL_OPERATION_DEADLINE,
        error,
        start_unknown);
    return error;
}

static bool on_owner_core(const responder_internal_t *internal)
{
    return internal->metadata.owner_core_id >= 0 &&
        (int)xPortGetCoreID() == internal->metadata.owner_core_id;
}

static control_transfer_result_t read_exact(
    responder_internal_t *internal,
    uint8_t *destination,
    size_t bytes,
    uint64_t deadline_us,
    size_t *transferred)
{
    *transferred = 0U;
    uint32_t calls = 0U;
    while (*transferred < bytes) {
        uint64_t current_us = 0U;
        if (!now_us(&current_us)) {
            return TRANSFER_UNKNOWN;
        }
        if (current_us >= deadline_us ||
            ++calls > internal->config.max_io_calls) {
            return *transferred == 0U
                ? TRANSFER_ZERO_PROGRESS
                : TRANSFER_PARTIAL;
        }
        TickType_t ticks = bounded_ticks(
            current_us, deadline_us, internal->config.io_wait_slice_ms);
        int count = usb_serial_jtag_read_bytes(
            destination + *transferred,
            (uint32_t)(bytes - *transferred),
            ticks);
        if (count < 0 || (size_t)count > bytes - *transferred) {
            return TRANSFER_UNKNOWN;
        }
        *transferred += (size_t)count;
        uint64_t completed_us = 0U;
        if (!now_us(&completed_us)) {
            return TRANSFER_UNKNOWN;
        }
        if (completed_us > deadline_us) {
            return *transferred == 0U
                ? TRANSFER_ZERO_PROGRESS
                : TRANSFER_PARTIAL;
        }
    }
    return TRANSFER_OK;
}

static control_transfer_result_t write_exact_and_drain(
    responder_internal_t *internal,
    const uint8_t *source,
    size_t bytes,
    uint64_t deadline_us,
    size_t *transferred)
{
    *transferred = 0U;
    uint32_t calls = 0U;
    while (*transferred < bytes) {
        uint64_t current_us = 0U;
        if (!now_us(&current_us)) {
            return TRANSFER_UNKNOWN;
        }
        if (current_us >= deadline_us ||
            ++calls > internal->config.max_io_calls) {
            return *transferred == 0U
                ? TRANSFER_ZERO_PROGRESS
                : TRANSFER_PARTIAL;
        }
        TickType_t ticks = bounded_ticks(
            current_us, deadline_us, internal->config.io_wait_slice_ms);
        int count = usb_serial_jtag_write_bytes(
            source + *transferred, bytes - *transferred, ticks);
        if (count < 0 || (size_t)count > bytes - *transferred) {
            return TRANSFER_UNKNOWN;
        }
        *transferred += (size_t)count;
        uint64_t completed_us = 0U;
        if (!now_us(&completed_us)) {
            return TRANSFER_UNKNOWN;
        }
        if (completed_us > deadline_us) {
            return *transferred == 0U
                ? TRANSFER_ZERO_PROGRESS
                : TRANSFER_PARTIAL;
        }
    }
    for (;;) {
        uint64_t current_us = 0U;
        if (!now_us(&current_us) || current_us >= deadline_us ||
            ++calls > internal->config.max_io_calls) {
            return TRANSFER_UNKNOWN;
        }
        TickType_t ticks = bounded_ticks(
            current_us, deadline_us, internal->config.io_wait_slice_ms);
        esp_err_t wait_result = usb_serial_jtag_wait_tx_done(ticks);
        uint64_t completed_us = 0U;
        if (!now_us(&completed_us) || completed_us > deadline_us) {
            return TRANSFER_UNKNOWN;
        }
        if (wait_result == ESP_OK) {
            return TRANSFER_OK;
        }
        if (wait_result != ESP_ERR_TIMEOUT || completed_us >= deadline_us) {
            return TRANSFER_UNKNOWN;
        }
    }
}

static operation_cache_entry_t *find_operation(
    responder_internal_t *internal,
    const call020_control_request_t *request,
    bool *duplicate)
{
    *duplicate = false;
    for (uint32_t index = 0U; index < internal->operation_count; ++index) {
        operation_cache_entry_t *entry = &internal->operations[index];
        if (strcmp(entry->operation_id, request->operation_id) != 0) {
            continue;
        }
        if (entry->action != request->action ||
            entry->timeout_ms != request->timeout_ms ||
            strcmp(entry->run_id, request->run_id) != 0) {
            internal->metadata.operation_identity_rejections++;
            latch_terminal(
                internal,
                CALL020_DEVICE_CONTROL_TERMINAL_IDEMPOTENCY,
                ESP_ERR_INVALID_STATE,
                false);
            return NULL;
        }
        /*
         * The device cannot know whether a response reached the host, so the
         * immediately latest operation may be replayed exactly. Once a newer
         * operation exists, an older response is stale and must not move the
         * host back across a later lifecycle phase.
         */
        if (index + UINT32_C(1) != internal->operation_count) {
            internal->metadata.operation_identity_rejections++;
            latch_terminal(
                internal,
                CALL020_DEVICE_CONTROL_TERMINAL_IDEMPOTENCY,
                ESP_ERR_INVALID_STATE,
                false);
            return NULL;
        }
        *duplicate = true;
        internal->metadata.duplicate_requests++;
        return entry;
    }
    if (internal->operation_count >=
        CALL020_DEVICE_CONTROL_MAX_OPERATION_CACHE) {
        internal->metadata.operation_identity_rejections++;
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_IDEMPOTENCY,
            ESP_ERR_NO_MEM,
            false);
        return NULL;
    }
    operation_cache_entry_t *entry =
        &internal->operations[internal->operation_count++];
    memset(entry, 0, sizeof(*entry));
    entry->used = true;
    entry->action = request->action;
    entry->timeout_ms = request->timeout_ms;
    memcpy(entry->run_id, request->run_id, strlen(request->run_id) + 1U);
    memcpy(
        entry->operation_id,
        request->operation_id,
        strlen(request->operation_id) + 1U);
    return entry;
}

static bool bind_run(
    responder_internal_t *internal,
    const call020_control_request_t *request)
{
    if (!internal->metadata.run_id_bound) {
        memcpy(
            internal->bound_run_id,
            request->run_id,
            strlen(request->run_id) + 1U);
        internal->metadata.run_id_bound = true;
        return true;
    }
    if (strcmp(internal->bound_run_id, request->run_id) == 0) {
        return true;
    }
    internal->metadata.run_binding_rejections++;
    latch_terminal(
        internal,
        CALL020_DEVICE_CONTROL_TERMINAL_RUN_BINDING,
        ESP_ERR_INVALID_STATE,
        false);
    return false;
}

static bool capture_telemetry(
    call020_control_pre_start_telemetry_t *telemetry)
{
    uint64_t current_us = 0U;
    if (telemetry == NULL || !now_us(&current_us) ||
        current_us > (uint64_t)INT64_MAX / UINT64_C(1000)) {
        return false;
    }
    size_t free_bytes = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    size_t minimum_bytes =
        heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL);
    if (free_bytes == 0U || minimum_bytes == 0U ||
        minimum_bytes > free_bytes || free_bytes > UINT32_MAX ||
        minimum_bytes > UINT32_MAX) {
        return false;
    }
    telemetry->captured_at_monotonic_ns = current_us * UINT64_C(1000);
    telemetry->free_internal_heap_bytes = (uint32_t)free_bytes;
    telemetry->minimum_free_internal_heap_bytes = (uint32_t)minimum_bytes;
    return true;
}

static bool request_allowed(
    const responder_internal_t *internal,
    call020_control_action_t action)
{
    switch (action) {
    case CALL020_CONTROL_ACTION_PREPARE:
        return internal->metadata.state == CALL020_DEVICE_CONTROL_OWNED;
    case CALL020_CONTROL_ACTION_START:
        return internal->metadata.state == CALL020_DEVICE_CONTROL_PREPARED;
    case CALL020_CONTROL_ACTION_CANCEL:
        return internal->metadata.state == CALL020_DEVICE_CONTROL_OWNED ||
            internal->metadata.state == CALL020_DEVICE_CONTROL_PREPARED;
    case CALL020_CONTROL_ACTION_JOIN:
        return internal->metadata.state == CALL020_DEVICE_CONTROL_STOPPING;
    case CALL020_CONTROL_ACTION_CLOSE:
        return internal->metadata.state == CALL020_DEVICE_CONTROL_OWNED ||
            internal->metadata.state == CALL020_DEVICE_CONTROL_PREPARED ||
            internal->metadata.state == CALL020_DEVICE_CONTROL_STOPPING ||
            internal->metadata.state == CALL020_DEVICE_CONTROL_JOINED;
    case CALL020_CONTROL_ACTION_TELEMETRY:
        return internal->metadata.state == CALL020_DEVICE_CONTROL_OWNED ||
            internal->metadata.state == CALL020_DEVICE_CONTROL_PREPARED ||
            internal->metadata.state == CALL020_DEVICE_CONTROL_STOPPING ||
            internal->metadata.state == CALL020_DEVICE_CONTROL_JOINED;
    default:
        return false;
    }
}

static esp_err_t prepare_new_operation(
    responder_internal_t *internal,
    const call020_control_request_t *request,
    operation_cache_entry_t *entry,
    uint64_t deadline_us)
{
    esp_err_t result = ESP_OK;
    bool deadline_failed = false;
    switch (request->action) {
    case CALL020_CONTROL_ACTION_PREPARE:
        if (!operation_budget_available(deadline_us)) {
            deadline_failed = true;
            result = ESP_ERR_TIMEOUT;
            break;
        }
        internal->metadata.runner_prepare_calls++;
        result = call020_operator_runner_prepare(
            &internal->config.runner, &internal->descriptor);
        if (result == ESP_OK) {
            /* Runner ownership exists even if later telemetry fails. */
            internal->runner_prepared = true;
        }
        if (!operation_completed_within_deadline(deadline_us)) {
            deadline_failed = true;
            result = result == ESP_OK ? ESP_ERR_TIMEOUT : result;
            break;
        }
        if (result == ESP_OK) {
            if (!operation_budget_available(deadline_us)) {
                deadline_failed = true;
                result = ESP_ERR_TIMEOUT;
                break;
            }
            bool captured = capture_telemetry(&entry->telemetry);
            if (!operation_completed_within_deadline(deadline_us)) {
                deadline_failed = true;
                result = ESP_ERR_TIMEOUT;
                break;
            }
            if (!captured) {
                result = ESP_ERR_INVALID_STATE;
                break;
            }
            entry->response_kind = RESPONSE_PREPARE;
            internal->metadata.state = CALL020_DEVICE_CONTROL_PREPARED;
        }
        break;
    case CALL020_CONTROL_ACTION_START:
        entry->response_kind = RESPONSE_ACK;
        memcpy(entry->ack_state, "STARTING", sizeof("STARTING"));
        internal->metadata.state = CALL020_DEVICE_CONTROL_START_ACK_PENDING;
        break;
    case CALL020_CONTROL_ACTION_CANCEL:
        if (internal->runner_prepared && !internal->runner_closed) {
            if (!operation_budget_available(deadline_us)) {
                deadline_failed = true;
                result = ESP_ERR_TIMEOUT;
                break;
            }
            internal->metadata.runner_cancel_calls++;
            result = call020_operator_runner_cancel();
            if (!operation_completed_within_deadline(deadline_us)) {
                deadline_failed = true;
                result = result == ESP_OK ? ESP_ERR_TIMEOUT : result;
                break;
            }
        }
        if (result == ESP_OK) {
            entry->response_kind = RESPONSE_ACK;
            memcpy(entry->ack_state, "STOPPING", sizeof("STOPPING"));
            internal->metadata.state = CALL020_DEVICE_CONTROL_STOPPING;
        }
        break;
    case CALL020_CONTROL_ACTION_JOIN:
        if (internal->runner_prepared && !internal->runner_closed) {
            if (!operation_budget_available(deadline_us)) {
                deadline_failed = true;
                result = ESP_ERR_TIMEOUT;
                break;
            }
            internal->metadata.runner_join_calls++;
            result = call020_operator_runner_join();
            if (!operation_completed_within_deadline(deadline_us)) {
                deadline_failed = true;
                result = result == ESP_OK ? ESP_ERR_TIMEOUT : result;
                break;
            }
        }
        if (result == ESP_OK) {
            entry->response_kind = RESPONSE_ACK;
            memcpy(entry->ack_state, "JOINED", sizeof("JOINED"));
            internal->metadata.state = CALL020_DEVICE_CONTROL_JOINED;
        }
        break;
    case CALL020_CONTROL_ACTION_CLOSE:
        if (internal->runner_prepared && !internal->runner_closed) {
            if (!operation_budget_available(deadline_us)) {
                deadline_failed = true;
                result = ESP_ERR_TIMEOUT;
                break;
            }
            internal->metadata.runner_close_calls++;
            result = call020_operator_runner_close();
            internal->runner_closed = result == ESP_OK;
            if (!operation_completed_within_deadline(deadline_us)) {
                deadline_failed = true;
                result = result == ESP_OK ? ESP_ERR_TIMEOUT : result;
                break;
            }
        }
        if (result == ESP_OK) {
            entry->response_kind = RESPONSE_ACK;
            memcpy(entry->ack_state, "CLOSED", sizeof("CLOSED"));
            internal->metadata.state = CALL020_DEVICE_CONTROL_CLOSE_ACK_PENDING;
        }
        break;
    case CALL020_CONTROL_ACTION_TELEMETRY:
        if (!operation_budget_available(deadline_us)) {
            deadline_failed = true;
            result = ESP_ERR_TIMEOUT;
            break;
        }
        bool captured = capture_telemetry(&entry->telemetry);
        if (!operation_completed_within_deadline(deadline_us)) {
            deadline_failed = true;
            result = ESP_ERR_TIMEOUT;
        } else if (!captured) {
            result = ESP_ERR_INVALID_STATE;
        } else {
            entry->response_kind = RESPONSE_TELEMETRY_UNAVAILABLE;
        }
        break;
    default:
        result = ESP_ERR_INVALID_ARG;
        break;
    }
    if (deadline_failed) {
        return latch_operation_deadline(internal, result, false);
    }
    if (result != ESP_OK) {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_RUNNER,
            result,
            false);
    }
    return result;
}

static call020_control_wire_result_t encode_cached_response(
    responder_internal_t *internal,
    const call020_control_request_t *request,
    const operation_cache_entry_t *entry,
    bool duplicate,
    size_t *response_bytes)
{
    if (entry->response_kind == RESPONSE_PREPARE) {
        const call020_control_prepare_descriptor_t descriptor = {
            .session_id = internal->descriptor.session_id,
            .device_id = internal->descriptor.device_id,
            .guardian_id = internal->descriptor.guardian_id,
            .uplink_clock_id = internal->descriptor.uplink_clock_id,
            .downlink_clock_id = internal->descriptor.downlink_clock_id,
            .nonce_bits = internal->descriptor.nonce_bits,
        };
        if (internal->descriptor.random_quality !=
                CALL020_OPERATOR_RANDOM_QUALITY_UNVERIFIED ||
            !internal->descriptor.correlated_routing_ids ||
            internal->descriptor.provenance !=
                CALL020_WEARABLE_IDENTITY_RUNTIME_EPHEMERAL) {
            return CALL020_CONTROL_WIRE_INVALID_ARGUMENT;
        }
        return call020_control_wire_encode_prepare_ack(
            request,
            &descriptor,
            &entry->telemetry,
            duplicate,
            internal->response_frame,
            sizeof(internal->response_frame),
            response_bytes);
    }
    if (entry->response_kind == RESPONSE_ACK) {
        return call020_control_wire_encode_ack(
            request,
            entry->ack_state,
            true,
            duplicate,
            internal->response_frame,
            sizeof(internal->response_frame),
            response_bytes);
    }
    if (entry->response_kind == RESPONSE_TELEMETRY_UNAVAILABLE) {
        return call020_control_wire_encode_telemetry_unavailable_ack(
            request,
            &entry->telemetry,
            duplicate,
            internal->response_frame,
            sizeof(internal->response_frame),
            response_bytes);
    }
    return CALL020_CONTROL_WIRE_INVALID_ARGUMENT;
}

static esp_err_t local_cleanup(responder_internal_t *internal)
{
    internal->metadata.local_cleanup_attempts++;
    esp_err_t result = ESP_OK;
    if (internal->runner_prepared && !internal->runner_closed) {
        internal->metadata.runner_close_calls++;
        esp_err_t runner_result = call020_operator_runner_close();
        result = preserve_first_error(result, runner_result);
        internal->runner_closed = runner_result == ESP_OK;
    }
    if (internal->lease_cleanup_required) {
        call020_usb_driver_lease_metadata_t lease_metadata = {0};
        esp_err_t metadata_result = call020_usb_driver_lease_get_metadata(
            &internal->lease, &lease_metadata);
        result = preserve_first_error(result, metadata_result);
        if (metadata_result == ESP_OK) {
            internal->metadata.lease_installed =
                lease_metadata.driver_installed;
        }
        if (metadata_result == ESP_OK &&
            lease_metadata.state != CALL020_USB_DRIVER_LEASE_MEDIA_BORROWED &&
            lease_metadata.state != CALL020_USB_DRIVER_LEASE_CLOSED) {
            esp_err_t lease_result = call020_usb_driver_lease_close(
                &internal->lease);
            result = preserve_first_error(result, lease_result);
            if (lease_result == ESP_OK) {
                internal->lease_cleanup_required = false;
                internal->metadata.lease_installed = false;
            }
        } else if (metadata_result == ESP_OK &&
            lease_metadata.state == CALL020_USB_DRIVER_LEASE_CLOSED) {
            internal->lease_cleanup_required = false;
            internal->metadata.lease_installed = false;
        } else if (metadata_result == ESP_OK) {
            result = preserve_first_error(result, ESP_ERR_INVALID_STATE);
        }
    }
    if (result != ESP_OK) {
        internal->metadata.local_cleanup_failures++;
        internal->metadata.first_error = preserve_first_error(
            internal->metadata.first_error, result);
    }
    return result;
}

const char *call020_device_control_responder_version(void)
{
    return CALL020_DEVICE_CONTROL_RESPONDER_VERSION;
}

esp_err_t call020_device_control_responder_init(
    call020_device_control_responder_t *responder,
    const call020_device_control_responder_config_t *config)
{
    if (responder == NULL || !config_valid(config)) {
        return ESP_ERR_INVALID_ARG;
    }
    call020_control_wire_clear(responder, sizeof(*responder));
    responder_internal_t *internal = internal_of(responder);
    internal->magic = RESPONDER_MAGIC;
    internal->config = *config;
    internal->metadata.state = CALL020_DEVICE_CONTROL_DORMANT;
    internal->metadata.first_error = ESP_OK;
    internal->metadata.owner_core_id = -1;
    internal->metadata.enabled_by_config = config->enabled;
    internal->metadata.dedicated_build_enabled = dedicated_build_enabled();
    internal->metadata.result_phase_enabled = false;
    internal->metadata.post_stop_telemetry_supported = false;
    internal->metadata.raw_audio_logged_or_persisted = false;
    internal->metadata.identifiers_or_payload_logged = false;
    internal->metadata.device_runtime_termination_proven = false;
    internal->metadata.remote_cleanup_acknowledged_after_media = false;
    return ESP_OK;
}

esp_err_t call020_device_control_responder_open_control(
    call020_device_control_responder_t *responder)
{
    responder_internal_t *internal = internal_of(responder);
    if (responder == NULL || internal->magic != RESPONDER_MAGIC) {
        return ESP_ERR_INVALID_ARG;
    }
    internal->metadata.open_calls++;
    if (!internal->config.enabled || !dedicated_build_enabled()) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    if (internal->metadata.state != CALL020_DEVICE_CONTROL_DORMANT) {
        return ESP_ERR_INVALID_STATE;
    }
    internal->metadata.owner_core_id = (int)xPortGetCoreID();
    esp_err_t result = call020_usb_driver_lease_install(
        &internal->lease, &internal->config.runner.usb_endpoint);
    internal->lease_cleanup_required = internal->lease.initialized;
    if (internal->lease.initialized) {
        call020_usb_driver_lease_metadata_t lease_metadata = {0};
        if (call020_usb_driver_lease_get_metadata(
                &internal->lease, &lease_metadata) == ESP_OK) {
            internal->metadata.lease_installed =
                lease_metadata.driver_installed;
        }
    }
    if (result != ESP_OK) {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP,
            result,
            false);
        if (internal->lease_cleanup_required) {
            local_cleanup(internal);
        }
        return result;
    }
    internal->lease_cleanup_required = true;
    internal->metadata.lease_installed = true;
    internal->metadata.state = CALL020_DEVICE_CONTROL_OWNED;
    return ESP_OK;
}

call020_device_control_serve_result_t
call020_device_control_responder_serve_once(
    call020_device_control_responder_t *responder)
{
    responder_internal_t *internal = internal_of(responder);
    if (responder == NULL || internal->magic != RESPONDER_MAGIC ||
        internal->metadata.state == CALL020_DEVICE_CONTROL_DORMANT ||
        internal->metadata.state == CALL020_DEVICE_CONTROL_CLOSED ||
        internal->metadata.control_writes_permanently_disabled) {
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    internal->metadata.serve_calls++;
    if (!on_owner_core(internal)) {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_WRONG_CORE,
            ESP_ERR_INVALID_STATE,
            false);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    clear_io_buffers(internal);
    uint64_t started_us = 0U;
    uint64_t frame_deadline_us = 0U;
    if (!now_us(&started_us) || !checked_deadline_us(
            started_us,
            internal->config.frame_wait_timeout_ms,
            &frame_deadline_us)) {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_READ_PARTIAL_OR_UNKNOWN,
            ESP_ERR_INVALID_STATE,
            false);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    size_t header_bytes = 0U;
    control_transfer_result_t read_result = read_exact(
        internal,
        internal->request_frame,
        CALL020_CONTROL_HEADER_BYTES,
        frame_deadline_us,
        &header_bytes);
    if (read_result == TRANSFER_ZERO_PROGRESS) {
        internal->metadata.zero_progress_timeouts++;
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_IDLE;
    }
    if (read_result != TRANSFER_OK) {
        internal->metadata.partial_or_unknown_transfers++;
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_READ_PARTIAL_OR_UNKNOWN,
            ESP_ERR_INVALID_SIZE,
            false);
        local_cleanup(internal);
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    size_t declared_frame_bytes = 0U;
    if (call020_control_wire_request_frame_bytes_from_header(
            internal->request_frame,
            CALL020_CONTROL_HEADER_BYTES,
            &declared_frame_bytes) != CALL020_CONTROL_WIRE_OK) {
        internal->metadata.malformed_frames++;
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_FRAME,
            ESP_ERR_INVALID_SIZE,
            false);
        local_cleanup(internal);
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    size_t payload_bytes = declared_frame_bytes -
        CALL020_CONTROL_HEADER_BYTES - CALL020_CONTROL_CRC_BYTES;
    size_t remainder_bytes = payload_bytes + CALL020_CONTROL_CRC_BYTES;
    size_t received_remainder = 0U;
    read_result = read_exact(
        internal,
        internal->request_frame + CALL020_CONTROL_HEADER_BYTES,
        remainder_bytes,
        frame_deadline_us,
        &received_remainder);
    if (read_result != TRANSFER_OK) {
        internal->metadata.partial_or_unknown_transfers++;
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_READ_PARTIAL_OR_UNKNOWN,
            ESP_ERR_INVALID_SIZE,
            false);
        local_cleanup(internal);
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    size_t request_bytes = CALL020_CONTROL_HEADER_BYTES + remainder_bytes;
    call020_control_request_t request = {0};
    if (call020_control_wire_decode_request(
            internal->request_frame, request_bytes, &request) !=
            CALL020_CONTROL_WIRE_OK ||
        request.timeout_ms > internal->config.max_operation_timeout_ms) {
        internal->metadata.malformed_frames++;
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_FRAME,
            ESP_ERR_INVALID_ARG,
            false);
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    /*
     * Frame acquisition has its own deadline.  Start the device operation
     * budget only after a complete frame has passed bounded wire validation;
     * idle frame-wait time must not silently consume the caller's operation
     * timeout.  The host retains its independent end-to-end deadline.
     */
    uint64_t request_accepted_us = 0U;
    uint64_t operation_deadline_us = 0U;
    if (!now_us(&request_accepted_us) || !checked_deadline_us(
            request_accepted_us,
            request.timeout_ms,
            &operation_deadline_us)) {
        latch_operation_deadline(internal, ESP_ERR_INVALID_STATE, false);
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    internal->metadata.complete_requests++;
    /* Scheduling after acceptance cannot authorize an already-expired call. */
    if (!operation_budget_available(operation_deadline_us)) {
        latch_operation_deadline(internal, ESP_ERR_TIMEOUT, false);
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    if (!bind_run(internal, &request)) {
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    bool duplicate = false;
    operation_cache_entry_t *entry = find_operation(
        internal, &request, &duplicate);
    if (entry == NULL) {
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    if (!duplicate && !request_allowed(internal, request.action)) {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_RUNNER,
            ESP_ERR_INVALID_STATE,
            false);
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    if (!duplicate && prepare_new_operation(
            internal, &request, entry, operation_deadline_us) != ESP_OK) {
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    size_t response_bytes = 0U;
    if (encode_cached_response(
            internal, &request, entry, duplicate, &response_bytes) !=
            CALL020_CONTROL_WIRE_OK) {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_FRAME,
            ESP_ERR_INVALID_SIZE,
            request.action == CALL020_CONTROL_ACTION_START);
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    size_t response_transferred = 0U;
    control_transfer_result_t write_result = write_exact_and_drain(
        internal,
        internal->response_frame,
        response_bytes,
        operation_deadline_us,
        &response_transferred);
    if (write_result == TRANSFER_ZERO_PROGRESS) {
        internal->metadata.zero_progress_timeouts++;
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_RETRYABLE_ZERO_PROGRESS;
    }
    if (write_result != TRANSFER_OK) {
        internal->metadata.partial_or_unknown_transfers++;
        bool start_unknown = request.action == CALL020_CONTROL_ACTION_START;
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_WRITE_PARTIAL_OR_UNKNOWN,
            ESP_ERR_TIMEOUT,
            start_unknown);
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }
    internal->metadata.complete_responses++;

    if (request.action == CALL020_CONTROL_ACTION_START) {
        internal->metadata.start_ack_fully_transmitted = true;
        internal->metadata.control_writes_permanently_disabled = true;
        bool handoff_completed = false;
        bool deadline_failed = false;
        esp_err_t result = ESP_OK;
        if (!operation_budget_available(operation_deadline_us)) {
            deadline_failed = true;
            result = ESP_ERR_TIMEOUT;
        } else {
            internal->metadata.lease_handoff_calls++;
            result = call020_usb_driver_lease_begin_media_handoff(
                &internal->lease);
            handoff_completed = result == ESP_OK;
            if (!operation_completed_within_deadline(operation_deadline_us)) {
                deadline_failed = true;
                result = result == ESP_OK ? ESP_ERR_TIMEOUT : result;
            }
        }
        if (result == ESP_OK && !deadline_failed) {
            if (!operation_budget_available(operation_deadline_us)) {
                deadline_failed = true;
                result = ESP_ERR_TIMEOUT;
            } else {
                internal->metadata.runner_start_calls++;
                result = call020_operator_runner_start_with_usb_driver_lease(
                    &internal->lease);
                if (!operation_completed_within_deadline(
                        operation_deadline_us)) {
                    deadline_failed = true;
                    result = result == ESP_OK ? ESP_ERR_TIMEOUT : result;
                }
            }
        }
        if (deadline_failed || result != ESP_OK) {
            if (deadline_failed) {
                latch_operation_deadline(internal, result, true);
            } else {
                latch_terminal(
                    internal,
                    handoff_completed
                        ? CALL020_DEVICE_CONTROL_TERMINAL_RUNNER
                        : CALL020_DEVICE_CONTROL_TERMINAL_HANDOFF,
                    result,
                    true);
            }
            local_cleanup(internal);
            call020_control_wire_clear(&request, sizeof(request));
            clear_io_buffers(internal);
            clear_control_identities(internal);
            return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
        }
        internal->metadata.state = CALL020_DEVICE_CONTROL_MEDIA;
        internal->metadata.media_started = true;
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        clear_control_identities(internal);
        return CALL020_DEVICE_CONTROL_SERVE_MEDIA_STARTED;
    }

    if (request.action == CALL020_CONTROL_ACTION_CLOSE) {
        internal->metadata.control_writes_permanently_disabled = true;
        esp_err_t result = local_cleanup(internal);
        internal->metadata.state = result == ESP_OK
            ? CALL020_DEVICE_CONTROL_CLOSED
            : CALL020_DEVICE_CONTROL_TERMINAL;
        if (result != ESP_OK) {
            internal->metadata.terminal_reason =
                CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP;
        }
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        clear_control_identities(internal);
        return result == ESP_OK
            ? CALL020_DEVICE_CONTROL_SERVE_CLOSE_COMPLETE
            : CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }

    if (request.action == CALL020_CONTROL_ACTION_TELEMETRY) {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_POST_STOP_TELEMETRY_UNAVAILABLE,
            ESP_ERR_NOT_SUPPORTED,
            false);
        local_cleanup(internal);
        call020_control_wire_clear(&request, sizeof(request));
        clear_io_buffers(internal);
        clear_control_identities(internal);
        return CALL020_DEVICE_CONTROL_SERVE_TERMINAL;
    }

    call020_control_wire_clear(&request, sizeof(request));
    clear_io_buffers(internal);
    return CALL020_DEVICE_CONTROL_SERVE_RESPONSE_SENT;
}

esp_err_t call020_device_control_responder_abort_local(
    call020_device_control_responder_t *responder)
{
    responder_internal_t *internal = internal_of(responder);
    if (responder == NULL || internal->magic != RESPONDER_MAGIC) {
        return ESP_ERR_INVALID_ARG;
    }
    if (internal->metadata.owner_core_id >= 0 && !on_owner_core(internal)) {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_WRONG_CORE,
            ESP_ERR_INVALID_STATE,
            false);
        return ESP_ERR_INVALID_STATE;
    }
    if (internal->metadata.state == CALL020_DEVICE_CONTROL_MEDIA) {
        return ESP_ERR_INVALID_STATE;
    }
    internal->metadata.control_writes_permanently_disabled = true;
    esp_err_t result = local_cleanup(internal);
    if (result == ESP_OK) {
        internal->metadata.state = CALL020_DEVICE_CONTROL_CLOSED;
    } else {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP,
            result,
            internal->metadata.start_ack_fully_transmitted);
    }
    clear_io_buffers(internal);
    clear_control_identities(internal);
    return result;
}

esp_err_t call020_device_control_responder_finish_media_local(
    call020_device_control_responder_t *responder)
{
    responder_internal_t *internal = internal_of(responder);
    if (responder == NULL || internal->magic != RESPONDER_MAGIC) {
        return ESP_ERR_INVALID_ARG;
    }
    internal->metadata.media_finalize_calls++;
    if (internal->metadata.owner_core_id < 0 || !on_owner_core(internal)) {
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_WRONG_CORE,
            ESP_ERR_INVALID_STATE,
            false);
        return ESP_ERR_INVALID_STATE;
    }
    if (internal->metadata.state == CALL020_DEVICE_CONTROL_CLOSED &&
        internal->metadata.device_runtime_termination_proven &&
        internal->metadata.physical_driver_close_confirmed) {
        return ESP_OK;
    }
    bool recovery_entry = internal->metadata.state ==
        CALL020_DEVICE_CONTROL_TERMINAL;
    if (!internal->metadata.media_started ||
        (internal->metadata.state != CALL020_DEVICE_CONTROL_MEDIA &&
         !recovery_entry) ||
        !internal->runner_prepared) {
        return ESP_ERR_INVALID_STATE;
    }

    /*
     * START ACK remains the final wire byte. Everything below is local and
     * phase-idempotent: a terminal cleanup attempt retains enough ownership
     * state for this same-core owner to retry without repeating a completed
     * runner close or physical lease close.
     */
    internal->metadata.control_writes_permanently_disabled = true;
    call020_operator_runner_metadata_t runner_metadata = {0};
    if (!internal->metadata.media_workers_quiescent ||
        !internal->metadata.media_output_safe_verified) {
        internal->metadata.runner_cancel_calls++;
        esp_err_t cancel_result = call020_operator_runner_cancel();
        internal->metadata.first_error = preserve_first_error(
            internal->metadata.first_error, cancel_result);

        internal->metadata.runner_join_calls++;
        esp_err_t join_result = call020_operator_runner_join();
        internal->metadata.first_error = preserve_first_error(
            internal->metadata.first_error, join_result);

        esp_err_t metadata_result = call020_operator_runner_get_metadata(
            &runner_metadata);
        internal->metadata.first_error = preserve_first_error(
            internal->metadata.first_error, metadata_result);
        bool workers_quiescent = metadata_result == ESP_OK &&
            runner_metadata.composition.workers_created == UINT32_C(4) &&
            runner_metadata.composition.workers_finished == UINT32_C(4);
        bool output_safe = metadata_result == ESP_OK &&
            runner_metadata.composition.pa_off_verified &&
            runner_metadata.composition.codec_muted_verified;
        internal->metadata.media_workers_quiescent = workers_quiescent;
        internal->metadata.media_output_safe_verified = output_safe;

        if (!workers_quiescent || !output_safe) {
            esp_err_t error = join_result != ESP_OK
                ? join_result
                : (metadata_result != ESP_OK
                    ? metadata_result
                    : (cancel_result != ESP_OK
                        ? cancel_result
                        : ESP_ERR_INVALID_STATE));
            latch_terminal(
                internal,
                CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP,
                error,
                false);
            clear_io_buffers(internal);
            clear_control_identities(internal);
            return error;
        }
    }

    if (!internal->runner_closed) {
        internal->metadata.runner_close_calls++;
        esp_err_t runner_close_result = call020_operator_runner_close();
        esp_err_t metadata_result = call020_operator_runner_get_metadata(
            &runner_metadata);
        bool runner_closed = metadata_result == ESP_OK &&
            runner_metadata.state == CALL020_OPERATOR_CLOSED &&
            runner_metadata.resources_closed &&
            runner_metadata.usb_driver_binding_closed &&
            runner_metadata.usb_driver_lease_returned &&
            runner_metadata.composition.workers_created == UINT32_C(4) &&
            runner_metadata.composition.workers_finished == UINT32_C(4) &&
            runner_metadata.composition.pa_off_verified &&
            runner_metadata.composition.codec_muted_verified;
        internal->runner_closed = runner_closed;
        internal->metadata.media_runner_resources_closed = runner_closed;
        internal->metadata.media_driver_lease_returned = runner_closed;
        internal->metadata.first_error = preserve_first_error(
            internal->metadata.first_error, runner_close_result);
        internal->metadata.first_error = preserve_first_error(
            internal->metadata.first_error, metadata_result);
        if (!runner_closed) {
            esp_err_t error = metadata_result != ESP_OK
                ? metadata_result
                : (runner_close_result != ESP_OK
                    ? runner_close_result
                    : ESP_ERR_INVALID_STATE);
            latch_terminal(
                internal,
                CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP,
                error,
                false);
            clear_io_buffers(internal);
            clear_control_identities(internal);
            return error;
        }
    }

    call020_usb_driver_lease_metadata_t lease_metadata = {0};
    esp_err_t lease_metadata_result = call020_usb_driver_lease_get_metadata(
        &internal->lease, &lease_metadata);
    bool already_physically_closed = lease_metadata_result == ESP_OK &&
        lease_metadata.state == CALL020_USB_DRIVER_LEASE_CLOSED &&
        !lease_metadata.driver_installed;
    bool lease_returned = lease_metadata_result == ESP_OK &&
        ((lease_metadata.state == CALL020_USB_DRIVER_LEASE_MEDIA_RETURNED &&
          lease_metadata.media_binding_returned &&
          lease_metadata.driver_installed) || already_physically_closed);
    internal->metadata.media_driver_lease_returned = lease_returned;
    if (!lease_returned) {
        esp_err_t error = lease_metadata_result != ESP_OK
            ? lease_metadata_result
            : ESP_ERR_INVALID_STATE;
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP,
            error,
            false);
        clear_io_buffers(internal);
        clear_control_identities(internal);
        return error;
    }

    esp_err_t lease_close_result = ESP_OK;
    if (!already_physically_closed) {
        lease_close_result = call020_usb_driver_lease_close(&internal->lease);
        lease_metadata_result = call020_usb_driver_lease_get_metadata(
            &internal->lease, &lease_metadata);
    }
    bool physical_close_confirmed = lease_metadata_result == ESP_OK &&
        lease_metadata.state == CALL020_USB_DRIVER_LEASE_CLOSED &&
        !lease_metadata.driver_installed;
    internal->metadata.physical_driver_close_confirmed =
        physical_close_confirmed;
    internal->metadata.lease_installed = !physical_close_confirmed;
    if (!physical_close_confirmed) {
        esp_err_t error = lease_close_result != ESP_OK
            ? lease_close_result
            : (lease_metadata_result != ESP_OK
                ? lease_metadata_result
                : ESP_ERR_INVALID_STATE);
        latch_terminal(
            internal,
            CALL020_DEVICE_CONTROL_TERMINAL_LOCAL_CLEANUP,
            error,
            false);
        clear_io_buffers(internal);
        clear_control_identities(internal);
        return error;
    }

    internal->lease_cleanup_required = false;
    internal->metadata.device_runtime_termination_proven = true;
    internal->metadata.state = CALL020_DEVICE_CONTROL_CLOSED;
    clear_io_buffers(internal);
    clear_control_identities(internal);
    return ESP_OK;
}

esp_err_t call020_device_control_responder_get_metadata(
    const call020_device_control_responder_t *responder,
    call020_device_control_responder_metadata_t *metadata)
{
    const responder_internal_t *internal = const_internal_of(responder);
    if (responder == NULL || metadata == NULL ||
        internal->magic != RESPONDER_MAGIC) {
        return ESP_ERR_INVALID_ARG;
    }
    *metadata = internal->metadata;
    return ESP_OK;
}

static const call020_device_control_responder_api_t s_retained_api = {
    .api_version = UINT32_C(1),
    .init = call020_device_control_responder_init,
    .open_control = call020_device_control_responder_open_control,
    .serve_once = call020_device_control_responder_serve_once,
    .abort_local = call020_device_control_responder_abort_local,
    .get_metadata = call020_device_control_responder_get_metadata,
};

const call020_device_control_responder_api_t *
call020_device_control_responder_retained_entry(void)
{
    return &s_retained_api;
}

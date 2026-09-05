#include "p0_outbox_dispatcher.h"

#include <string.h>

#include "mbedtls/sha256.h"

#define P0_OUTBOX_DISPATCHER_MAGIC UINT32_C(0x50304f44)
#define P0_INVALID_ROUTE_ERROR "P0_ROUTE_INVALID"
#define P0_CANCELLED_ERROR "P0_DISPATCH_CANCELLED"

typedef struct {
    uint32_t magic;
    egolink_p0_outbox_dispatcher_lifecycle_t lifecycle;
    bool busy;
    egolink_outbox_t *shared_outbox;
    egolink_location_outbox_adapter_t *location_adapter;
    egolink_sos_outbox_adapter_t *sos_adapter;
    egolink_outbox_send_item_t canonical_item;
    egolink_p0_outbox_dispatcher_snapshot_t status;
} p0_outbox_dispatcher_internal_t;

_Static_assert(sizeof(p0_outbox_dispatcher_internal_t) <=
                   EGOLINK_P0_OUTBOX_DISPATCHER_CONTEXT_BYTES,
               "P0 outbox dispatcher context is too small");
_Static_assert(EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES <=
                   EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES,
               "route response ceilings are unexpectedly ordered");

static p0_outbox_dispatcher_internal_t *internal_of(
    egolink_p0_outbox_dispatcher_t *dispatcher)
{
    return (p0_outbox_dispatcher_internal_t *)(void *)dispatcher->opaque;
}

static const p0_outbox_dispatcher_internal_t *internal_of_const(
    const egolink_p0_outbox_dispatcher_t *dispatcher)
{
    return (const p0_outbox_dispatcher_internal_t *)(const void *)
        dispatcher->opaque;
}

static void secure_clear(void *data, size_t length)
{
    volatile uint8_t *cursor = (volatile uint8_t *)data;
    while (cursor != NULL && length > 0U) {
        *cursor = 0U;
        ++cursor;
        --length;
    }
}

static void increment_saturated(uint64_t *value)
{
    if (*value != UINT64_MAX) {
        ++(*value);
    }
}

static size_t bounded_length(const char *value, size_t capacity)
{
    size_t length = 0U;
    if (value == NULL) {
        return capacity;
    }
    while (length < capacity && value[length] != '\0') {
        ++length;
    }
    return length;
}

static bool safe_identifier(const char *value)
{
    const size_t length = bounded_length(value, EGOLINK_OUTBOX_ID_CAPACITY);
    if (length == 0U || length >= EGOLINK_OUTBOX_ID_CAPACITY) {
        return false;
    }
    for (size_t index = 0U; index < length; ++index) {
        const char character = value[index];
        const bool alphanumeric =
            (character >= 'A' && character <= 'Z') ||
            (character >= 'a' && character <= 'z') ||
            (character >= '0' && character <= '9');
        if ((!alphanumeric && index == 0U) ||
            (!alphanumeric && character != '.' && character != '_' &&
             character != ':' && character != '@' && character != '-')) {
            return false;
        }
    }
    return true;
}

static bool lowercase_sha256(const char *value)
{
    if (bounded_length(value, EGOLINK_OUTBOX_SHA256_HEX_CAPACITY) !=
        EGOLINK_OUTBOX_SHA256_HEX_CAPACITY - 1U) {
        return false;
    }
    for (size_t index = 0U;
         index < EGOLINK_OUTBOX_SHA256_HEX_CAPACITY - 1U;
         ++index) {
        const char character = value[index];
        if (!((character >= '0' && character <= '9') ||
              (character >= 'a' && character <= 'f'))) {
            return false;
        }
    }
    return true;
}

static bool exact_text(const char *left, const char *right, size_t capacity)
{
    const size_t left_length = bounded_length(left, capacity);
    const size_t right_length = bounded_length(right, capacity);
    return left_length < capacity && left_length == right_length &&
        memcmp(left, right, left_length + 1U) == 0;
}

static bool valid_magic(const p0_outbox_dispatcher_internal_t *internal)
{
    return internal != NULL &&
        internal->magic == P0_OUTBOX_DISPATCHER_MAGIC;
}

static bool adapters_bound(const p0_outbox_dispatcher_internal_t *internal)
{
    return internal->shared_outbox != NULL &&
        internal->location_adapter != NULL &&
        internal->sos_adapter != NULL &&
        internal->location_adapter->initialized &&
        internal->sos_adapter->initialized &&
        internal->location_adapter->outbox == internal->shared_outbox &&
        internal->sos_adapter->outbox == internal->shared_outbox &&
        safe_identifier(internal->location_adapter->device_id) &&
        safe_identifier(internal->sos_adapter->device_id) &&
        exact_text(
            internal->location_adapter->device_id,
            internal->sos_adapter->device_id,
            EGOLINK_OUTBOX_ID_CAPACITY);
}

static bool sos_activity_consistent(
    const p0_outbox_dispatcher_internal_t *internal)
{
    const bool expected = internal->status.phase != EGOLINK_P0_OUTBOX_PHASE_IDLE &&
        internal->status.active_route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
    return internal->sos_adapter != NULL &&
        internal->sos_adapter->attempt_active == expected;
}

static void update_common_status(
    p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_dispatcher_status_t status)
{
    internal->status.lifecycle = internal->lifecycle;
    internal->status.last_status = status;
    internal->status.enabled =
        internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_ACTIVE;
    internal->status.dependency_bound = adapters_bound(internal);
    internal->status.busy = internal->busy;
}

static void clear_canonical_item(p0_outbox_dispatcher_internal_t *internal)
{
    egolink_sos_outbox_clear_send_item(&internal->canonical_item);
    internal->status.private_canonical_item_retained = false;
}

void egolink_p0_outbox_dispatcher_clear_send_view(
    egolink_p0_outbox_send_view_t *send_view)
{
    if (send_view != NULL) {
        secure_clear(send_view, sizeof(*send_view));
    }
}

static void invalidate_payload_view(
    egolink_p0_outbox_send_view_t *send_view)
{
    if (send_view == NULL) {
        return;
    }
    send_view->payload = NULL;
    send_view->payload_length = 0U;
    send_view->endpoint_path = NULL;
    send_view->response_max_bytes = 0U;
    send_view->completion_only = true;
}

static void clear_active(p0_outbox_dispatcher_internal_t *internal)
{
    clear_canonical_item(internal);
    secure_clear(
        &internal->status.active_attempt,
        sizeof(internal->status.active_attempt));
    internal->status.active_route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
    internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_IDLE;
}

static void initialize_begin_result(egolink_p0_outbox_begin_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    result->route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
    result->sos_begin_status = EGOLINK_SOS_OUTBOX_BEGIN_INVALID_ARGUMENT;
    result->sos_begin_result.outbox_status = EGOLINK_OUTBOX_INVALID_ARGUMENT;
    result->sos_begin_result.invalid_sos_settlement_status =
        EGOLINK_OUTBOX_INVALID_ARGUMENT;
    result->invalid_event_settlement_status =
        EGOLINK_OUTBOX_INVALID_ARGUMENT;
}

static void initialize_finish_result(egolink_p0_outbox_finish_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    result->route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
    result->sos_finish_status = EGOLINK_SOS_OUTBOX_FINISH_INVALID_ARGUMENT;
    result->sos_finish_result.transport_status =
        EGOLINK_OUTBOX_INVALID_ARGUMENT;
    result->sos_finish_result.ack_status = EGOLINK_OUTBOX_INVALID_ACK;
    result->location_finish_status =
        EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ARGUMENT;
    result->location_finish_result.transport_status =
        EGOLINK_OUTBOX_INVALID_ARGUMENT;
    result->location_finish_result.ack_status = EGOLINK_OUTBOX_INVALID_ACK;
}

static bool location_event_id_matches_hash(
    const egolink_outbox_record_view_t *record)
{
    const size_t prefix_length =
        sizeof(EGOLINK_LOCATION_OUTBOX_EVENT_PREFIX) - 1U;
    const size_t event_length = bounded_length(
        record->event_id, EGOLINK_OUTBOX_ID_CAPACITY);
    return event_length ==
            prefix_length + EGOLINK_OUTBOX_SHA256_HEX_CAPACITY - 1U &&
        memcmp(
            record->event_id,
            EGOLINK_LOCATION_OUTBOX_EVENT_PREFIX,
            prefix_length) == 0 &&
        memcmp(
            record->event_id + prefix_length,
            record->payload_sha256,
            EGOLINK_OUTBOX_SHA256_HEX_CAPACITY) == 0;
}

static bool exact_payload_hash(
    const egolink_outbox_send_item_t *send_item)
{
    uint8_t digest[EGOLINK_OUTBOX_SHA256_BYTES];
    char digest_hex[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    static const char digits[] = "0123456789abcdef";
    (void)memset(digest, 0, sizeof(digest));
    (void)memset(digest_hex, 0, sizeof(digest_hex));
    const bool hashed = send_item->payload_length > 0U &&
        mbedtls_sha256(
            send_item->payload,
            send_item->payload_length,
            digest,
            0) == 0;
    if (hashed) {
        for (size_t index = 0U;
             index < EGOLINK_OUTBOX_SHA256_BYTES;
             ++index) {
            digest_hex[index * 2U] = digits[digest[index] >> 4U];
            digest_hex[index * 2U + 1U] =
                digits[digest[index] & UINT8_C(0x0f)];
        }
        digest_hex[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY - 1U] = '\0';
    }
    const bool matches = hashed && exact_text(
        digest_hex,
        send_item->record.payload_sha256,
        EGOLINK_OUTBOX_SHA256_HEX_CAPACITY);
    secure_clear(digest, sizeof(digest));
    secure_clear(digest_hex, sizeof(digest_hex));
    return matches;
}

static bool location_send_item_valid(
    const egolink_outbox_send_item_t *send_item)
{
    const egolink_outbox_record_view_t *record = &send_item->record;
    const bool allowed_priority =
        record->priority == EGOLINK_OUTBOX_PRIORITY_NORMAL ||
        record->priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL;
    return exact_text(
               record->event_type,
               EGOLINK_LOCATION_OUTBOX_EVENT_TYPE,
               EGOLINK_OUTBOX_EVENT_TYPE_CAPACITY) &&
        allowed_priority &&
        record->source_time_kind <=
            EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS &&
        record->send_state == EGOLINK_OUTBOX_SEND_ATTEMPT_STARTED &&
        record->last_attempt_result == EGOLINK_OUTBOX_ATTEMPT_PENDING &&
        record->attempt_count > 0U && safe_identifier(record->session_id) &&
        send_item->payload_length > 0U &&
        send_item->payload_length == record->payload_length &&
        send_item->payload_length <= EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES &&
        lowercase_sha256(record->payload_sha256) &&
        lowercase_sha256(record->identity_sha256) &&
        lowercase_sha256(record->last_attempt_token) &&
        location_event_id_matches_hash(record) &&
        exact_payload_hash(send_item);
}

static void capture_attempt(
    p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_route_t route)
{
    const egolink_outbox_record_view_t *record =
        &internal->canonical_item.record;
    egolink_p0_outbox_attempt_identity_t *attempt =
        &internal->status.active_attempt;
    secure_clear(attempt, sizeof(*attempt));
    attempt->route = route;
    (void)memcpy(
        attempt->device_id,
        internal->location_adapter->device_id,
        sizeof(attempt->device_id));
    (void)memcpy(
        attempt->event_id, record->event_id, sizeof(attempt->event_id));
    (void)memcpy(
        attempt->payload_sha256,
        record->payload_sha256,
        sizeof(attempt->payload_sha256));
    (void)memcpy(
        attempt->attempt_token,
        record->last_attempt_token,
        sizeof(attempt->attempt_token));
    attempt->priority = record->priority;
    attempt->source_time_kind = record->source_time_kind;
    attempt->source_event_time_ms = record->source_event_time_ms;
    attempt->boot_count = record->boot_count;
    (void)memcpy(
        attempt->session_id,
        record->session_id,
        sizeof(attempt->session_id));
    attempt->source_sequence = record->source_sequence;
    attempt->attempt_count = record->attempt_count;
    internal->status.active_route = route;
}

static void fill_send_view(
    const p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_send_view_t *send_view)
{
    egolink_p0_outbox_dispatcher_clear_send_view(send_view);
    send_view->payload = internal->canonical_item.payload;
    send_view->payload_length = internal->canonical_item.payload_length;
    send_view->endpoint_path =
        internal->status.active_route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS
            ? EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH
            : EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH;
    send_view->response_max_bytes =
        internal->status.active_route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS
            ? EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES
            : EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES;
    send_view->attempt = internal->status.active_attempt;
}

static void fill_completion_view(
    const p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_send_view_t *send_view)
{
    egolink_p0_outbox_dispatcher_clear_send_view(send_view);
    send_view->completion_only = true;
    send_view->attempt = internal->status.active_attempt;
}

static void enter_recovery(
    p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_send_view_t *send_view)
{
    internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED;
    if (internal->status.active_route !=
        EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS) {
        clear_canonical_item(internal);
    }
    internal->status.private_canonical_item_retained =
        internal->status.active_route ==
        EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
    fill_completion_view(internal, send_view);
    increment_saturated(&internal->status.recovery_required);
}

static bool attempt_identity_matches(
    const egolink_p0_outbox_attempt_identity_t *left,
    const egolink_p0_outbox_attempt_identity_t *right)
{
    return left != NULL && right != NULL && left->route == right->route &&
        exact_text(left->device_id, right->device_id, sizeof(left->device_id)) &&
        exact_text(left->event_id, right->event_id, sizeof(left->event_id)) &&
        exact_text(
            left->payload_sha256,
            right->payload_sha256,
            sizeof(left->payload_sha256)) &&
        exact_text(
            left->attempt_token,
            right->attempt_token,
            sizeof(left->attempt_token)) &&
        left->priority == right->priority &&
        left->source_time_kind == right->source_time_kind &&
        left->source_event_time_ms == right->source_event_time_ms &&
        left->boot_count == right->boot_count &&
        exact_text(
            left->session_id,
            right->session_id,
            sizeof(left->session_id)) &&
        left->source_sequence == right->source_sequence &&
        left->attempt_count == right->attempt_count;
}

static bool active_view_matches(
    const p0_outbox_dispatcher_internal_t *internal,
    const egolink_p0_outbox_send_view_t *send_view)
{
    if (send_view == NULL ||
        !attempt_identity_matches(
            &send_view->attempt, &internal->status.active_attempt)) {
        return false;
    }
    if (internal->status.phase == EGOLINK_P0_OUTBOX_PHASE_SEND_READY) {
        return !send_view->completion_only &&
            send_view->payload == internal->canonical_item.payload &&
            send_view->payload_length == internal->canonical_item.payload_length;
    }
    return send_view->completion_only && send_view->payload == NULL &&
        send_view->payload_length == 0U;
}

static bool sos_view_matches(
    const p0_outbox_dispatcher_internal_t *internal,
    const egolink_sos_outbox_send_view_t *sos_view)
{
    return sos_view != NULL &&
        sos_view->payload == internal->canonical_item.payload &&
        sos_view->payload_length == internal->canonical_item.payload_length &&
        exact_text(
            sos_view->device_id,
            internal->location_adapter->device_id,
            EGOLINK_OUTBOX_ID_CAPACITY) &&
        exact_text(
            sos_view->event_id,
            internal->canonical_item.record.event_id,
            EGOLINK_OUTBOX_ID_CAPACITY) &&
        exact_text(
            sos_view->payload_sha256,
            internal->canonical_item.record.payload_sha256,
            EGOLINK_OUTBOX_SHA256_HEX_CAPACITY) &&
        exact_text(
            sos_view->attempt_token,
            internal->canonical_item.record.last_attempt_token,
            EGOLINK_OUTBOX_SHA256_HEX_CAPACITY);
}

static egolink_p0_outbox_dispatcher_status_t return_begin(
    p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_begin_result_t *result,
    egolink_p0_outbox_dispatcher_status_t status)
{
    internal->busy = false;
    result->status = status;
    update_common_status(internal, status);
    return status;
}

static egolink_p0_outbox_dispatcher_status_t return_finish(
    p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_finish_result_t *result,
    egolink_p0_outbox_dispatcher_status_t status)
{
    internal->busy = false;
    result->status = status;
    update_common_status(internal, status);
    return status;
}

static egolink_p0_outbox_dispatcher_status_t settle_invalid_event(
    p0_outbox_dispatcher_internal_t *internal,
    uint64_t now_ms,
    egolink_p0_outbox_begin_result_t *result)
{
    capture_attempt(internal, EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED);
    result->route = EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED;
    result->invalid_event_settlement_status =
        egolink_outbox_record_transport_result(
            internal->shared_outbox,
            internal->status.active_attempt.attempt_token,
            false,
            P0_INVALID_ROUTE_ERROR,
            now_ms);
    result->durable_record_retained = true;
    if (result->invalid_event_settlement_status == EGOLINK_OUTBOX_OK ||
        result->invalid_event_settlement_status == EGOLINK_OUTBOX_DUPLICATE) {
        result->durable_failure_recorded = true;
        increment_saturated(&internal->status.invalid_events_retained);
        clear_active(internal);
        return EGOLINK_P0_OUTBOX_INVALID_EVENT_RETAINED;
    }
    clear_canonical_item(internal);
    internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED;
    increment_saturated(&internal->status.recovery_required);
    return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
}

static egolink_p0_outbox_dispatcher_status_t settle_invalid_sos_view(
    p0_outbox_dispatcher_internal_t *internal,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_begin_result_t *result)
{
    capture_attempt(internal, EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS);
    internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_SEND_READY;
    internal->status.private_canonical_item_retained = true;
    result->route = EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED;
    result->durable_record_retained = true;

    egolink_sos_outbox_finish_result_t finish_result;
    (void)memset(&finish_result, 0, sizeof(finish_result));
    const egolink_sos_outbox_finish_status_t finish_status =
        egolink_sos_outbox_finish_attempt(
            internal->sos_adapter,
            internal->status.active_attempt.attempt_token,
            UINT16_C(0),
            P0_INVALID_ROUTE_ERROR,
            NULL,
            0U,
            now_ms,
            &internal->canonical_item,
            &finish_result);
    result->invalid_event_settlement_status = finish_result.transport_status;
    secure_clear(&finish_result, sizeof(finish_result));

    if (finish_status == EGOLINK_SOS_OUTBOX_FINISH_HTTP_REJECTED_RETAINED) {
        result->durable_failure_recorded = true;
        increment_saturated(&internal->status.invalid_events_retained);
        clear_active(internal);
        return EGOLINK_P0_OUTBOX_INVALID_EVENT_RETAINED;
    }

    internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED;
    internal->status.private_canonical_item_retained = true;
    fill_completion_view(internal, send_view);
    increment_saturated(&internal->status.recovery_required);
    return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
}

void egolink_p0_outbox_dispatcher_default_config(
    egolink_p0_outbox_dispatcher_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->enabled = false;
    }
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_init(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    const egolink_p0_outbox_dispatcher_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter,
    egolink_sos_outbox_adapter_t *sos_adapter)
{
    if (dispatcher == NULL || config == NULL) {
        return EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    }
    p0_outbox_dispatcher_internal_t *internal = internal_of(dispatcher);
    if (valid_magic(internal)) {
        return EGOLINK_P0_OUTBOX_ALREADY_INITIALIZED;
    }
    secure_clear(dispatcher, sizeof(*dispatcher));
    internal = internal_of(dispatcher);
    internal->magic = P0_OUTBOX_DISPATCHER_MAGIC;
    internal->lifecycle = EGOLINK_P0_OUTBOX_DISPATCHER_DISABLED;
    internal->status.lifecycle = internal->lifecycle;
    internal->status.last_status = EGOLINK_P0_OUTBOX_DISABLED_STATUS;
    if (!config->enabled) {
        return EGOLINK_P0_OUTBOX_DISABLED_STATUS;
    }
    internal->shared_outbox = shared_outbox;
    internal->location_adapter = location_adapter;
    internal->sos_adapter = sos_adapter;
    if (!adapters_bound(internal) || sos_adapter->attempt_active) {
        secure_clear(dispatcher, sizeof(*dispatcher));
        return EGOLINK_P0_OUTBOX_DEPENDENCY_MISMATCH;
    }
    internal->lifecycle = EGOLINK_P0_OUTBOX_DISPATCHER_ACTIVE;
    internal->status.lifecycle = internal->lifecycle;
    internal->status.enabled = true;
    internal->status.dependency_bound = true;
    internal->status.last_status = EGOLINK_P0_OUTBOX_OK;
    return EGOLINK_P0_OUTBOX_OK;
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_begin(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_begin_result_t *result)
{
    egolink_p0_outbox_dispatcher_clear_send_view(send_view);
    initialize_begin_result(result);
    if (dispatcher == NULL || send_view == NULL || result == NULL) {
        return EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    }
    p0_outbox_dispatcher_internal_t *internal = internal_of(dispatcher);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_P0_OUTBOX_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_P0_OUTBOX_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_DISABLED) {
        result->status = EGOLINK_P0_OUTBOX_DISABLED_STATUS;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_CLOSED) {
        result->status = EGOLINK_P0_OUTBOX_CLOSED_STATUS;
        return result->status;
    }
    if (!adapters_bound(internal) || !sos_activity_consistent(internal)) {
        result->status = EGOLINK_P0_OUTBOX_DEPENDENCY_MISMATCH;
        update_common_status(internal, result->status);
        return result->status;
    }
    if (internal->status.phase != EGOLINK_P0_OUTBOX_PHASE_IDLE) {
        result->status = EGOLINK_P0_OUTBOX_ATTEMPT_ALREADY_ACTIVE;
        return result->status;
    }

    internal->busy = true;
    internal->status.busy = true;
    increment_saturated(&internal->status.begin_calls);
    clear_canonical_item(internal);
    egolink_sos_outbox_send_view_t sos_view;
    (void)memset(&sos_view, 0, sizeof(sos_view));
    result->sos_begin_status = egolink_sos_outbox_begin_attempt(
        internal->sos_adapter,
        now_ms,
        &internal->canonical_item,
        &sos_view,
        &result->sos_begin_result);

    if (result->sos_begin_status == EGOLINK_SOS_OUTBOX_BEGIN_NO_DUE_RECORD) {
        increment_saturated(&internal->status.no_due_records);
        clear_canonical_item(internal);
        return return_begin(
            internal, result, EGOLINK_P0_OUTBOX_NO_DUE_RECORD);
    }
    if (result->sos_begin_status == EGOLINK_SOS_OUTBOX_BEGIN_READY) {
        if (!sos_view_matches(internal, &sos_view)) {
            secure_clear(&sos_view, sizeof(sos_view));
            const egolink_p0_outbox_dispatcher_status_t settlement =
                settle_invalid_sos_view(
                    internal, now_ms, send_view, result);
            return return_begin(internal, result, settlement);
        }
        capture_attempt(internal, EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS);
        internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_SEND_READY;
        internal->status.private_canonical_item_retained = true;
        increment_saturated(&internal->status.ready_manual_sos);
        result->route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
        result->exact_payload_borrowed = true;
        result->durable_record_retained = true;
        fill_send_view(internal, send_view);
        secure_clear(&sos_view, sizeof(sos_view));
        return return_begin(
            internal, result, EGOLINK_P0_OUTBOX_BEGIN_READY);
    }
    secure_clear(&sos_view, sizeof(sos_view));

    if (result->sos_begin_status == EGOLINK_SOS_OUTBOX_BEGIN_NON_SOS_HEAD) {
        if (location_send_item_valid(&internal->canonical_item)) {
            capture_attempt(internal, EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE);
            internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_SEND_READY;
            internal->status.private_canonical_item_retained = true;
            increment_saturated(&internal->status.ready_location_state);
            result->route = EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE;
            result->exact_payload_borrowed = true;
            result->durable_record_retained = true;
            fill_send_view(internal, send_view);
            return return_begin(
                internal, result, EGOLINK_P0_OUTBOX_BEGIN_READY);
        }
        const egolink_p0_outbox_dispatcher_status_t settlement =
            settle_invalid_event(internal, now_ms, result);
        return return_begin(internal, result, settlement);
    }
    if (result->sos_begin_status ==
        EGOLINK_SOS_OUTBOX_BEGIN_INVALID_SOS_RETAINED) {
        increment_saturated(&internal->status.invalid_events_retained);
        result->route = EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED;
        result->durable_failure_recorded = true;
        result->durable_record_retained = true;
        clear_active(internal);
        return return_begin(
            internal, result, EGOLINK_P0_OUTBOX_INVALID_EVENT_RETAINED);
    }
    clear_active(internal);
    if (result->sos_begin_status ==
            EGOLINK_SOS_OUTBOX_BEGIN_OUTBOX_STATE_FAILED ||
        result->sos_begin_status ==
            EGOLINK_SOS_OUTBOX_BEGIN_NOT_INITIALIZED) {
        increment_saturated(&internal->status.recovery_required);
        return return_begin(
            internal,
            result,
            EGOLINK_P0_OUTBOX_DEPENDENCY_RECOVERY_REQUIRED);
    }
    if (result->sos_begin_status ==
        EGOLINK_SOS_OUTBOX_BEGIN_ATTEMPT_ALREADY_ACTIVE) {
        return return_begin(
            internal, result, EGOLINK_P0_OUTBOX_ATTEMPT_ALREADY_ACTIVE);
    }
    return return_begin(
        internal, result, EGOLINK_P0_OUTBOX_INVALID_ARGUMENT);
}

static egolink_p0_outbox_dispatcher_status_t map_sos_finish(
    p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_finish_result_t *result)
{
    switch (result->sos_finish_status) {
    case EGOLINK_SOS_OUTBOX_FINISH_ACK_DELETED:
        result->terminal = true;
        result->deleted_after_server_durable_ingest_ack = true;
        increment_saturated(&internal->status.server_durable_ack_deletes);
        clear_active(internal);
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_ACK_DELETED;
    case EGOLINK_SOS_OUTBOX_FINISH_ACK_ALREADY_APPLIED:
        result->terminal = true;
        clear_active(internal);
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_ACK_ALREADY_APPLIED;
    case EGOLINK_SOS_OUTBOX_FINISH_HTTP_REJECTED_RETAINED:
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_RESPONSE_RETAINED:
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_RESULT_RETAINED:
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_SCOPE_RETAINED:
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_ACK_RETAINED:
    case EGOLINK_SOS_OUTBOX_FINISH_IDENTITY_MISMATCH_RETAINED:
        result->terminal = true;
        result->durable_record_retained = true;
        increment_saturated(&internal->status.retained_finishes);
        clear_active(internal);
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_FINISHED_RETAINED;
    case EGOLINK_SOS_OUTBOX_FINISH_ACK_STATE_FAILED:
    case EGOLINK_SOS_OUTBOX_FINISH_TRANSPORT_STATE_FAILED:
        internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED;
        internal->status.private_canonical_item_retained = true;
        result->durable_record_retained = true;
        result->private_canonical_item_retained = true;
        increment_saturated(&internal->status.recovery_required);
        return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
    case EGOLINK_SOS_OUTBOX_FINISH_ATTEMPT_MISMATCH:
    case EGOLINK_SOS_OUTBOX_FINISH_NO_ACTIVE_ATTEMPT:
    case EGOLINK_SOS_OUTBOX_FINISH_INVALID_ARGUMENT:
    case EGOLINK_SOS_OUTBOX_FINISH_NOT_INITIALIZED:
    default:
        internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED;
        internal->status.private_canonical_item_retained = true;
        result->durable_record_retained = true;
        result->private_canonical_item_retained = true;
        increment_saturated(&internal->status.recovery_required);
        return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
    }
}

static egolink_p0_outbox_dispatcher_status_t map_location_finish(
    p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_finish_result_t *result)
{
    clear_canonical_item(internal);
    switch (result->location_finish_status) {
    case EGOLINK_LOCATION_OUTBOX_FINISH_ACK_DELETED:
        result->terminal = true;
        result->deleted_after_server_durable_ingest_ack = true;
        increment_saturated(&internal->status.server_durable_ack_deletes);
        clear_active(internal);
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_ACK_DELETED;
    case EGOLINK_LOCATION_OUTBOX_FINISH_ACK_ALREADY_APPLIED:
        result->terminal = true;
        clear_active(internal);
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_ACK_ALREADY_APPLIED;
    case EGOLINK_LOCATION_OUTBOX_FINISH_TRANSPORT_REJECTED_RETAINED:
        result->terminal = true;
        result->durable_record_retained = true;
        increment_saturated(&internal->status.retained_finishes);
        clear_active(internal);
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_FINISHED_RETAINED;
    case EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_RESPONSE:
    case EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_SCOPE:
    case EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ACK:
        result->terminal = true;
        result->durable_record_retained = true;
        increment_saturated(&internal->status.retained_finishes);
        clear_active(internal);
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_FINISHED_RETAINED;
    case EGOLINK_LOCATION_OUTBOX_FINISH_ACK_STATE_FAILED:
        switch (result->location_finish_result.ack_status) {
        case EGOLINK_OUTBOX_NEGATIVE_ACK:
        case EGOLINK_OUTBOX_STALE_OR_UNKNOWN_ACK:
        case EGOLINK_OUTBOX_ACK_IDENTITY_MISMATCH:
        case EGOLINK_OUTBOX_INVALID_ACK:
            /* These semantic rejections either were persisted by the core or
             * leave the accepted record untouched. End only this attempt. */
            result->terminal = true;
            result->durable_record_retained = true;
            increment_saturated(&internal->status.retained_finishes);
            clear_active(internal);
            egolink_p0_outbox_dispatcher_clear_send_view(send_view);
            return EGOLINK_P0_OUTBOX_FINISHED_RETAINED;
        case EGOLINK_OUTBOX_NOT_INITIALIZED:
        case EGOLINK_OUTBOX_FAULT_LATCHED:
        case EGOLINK_OUTBOX_COUNTER_OVERFLOW:
        case EGOLINK_OUTBOX_TIME_ROLLBACK:
        case EGOLINK_OUTBOX_TIME_OVERFLOW:
        case EGOLINK_OUTBOX_GENERATION_OVERFLOW:
        case EGOLINK_OUTBOX_STORAGE_ERROR:
        case EGOLINK_OUTBOX_STORAGE_CORRUPTION:
        case EGOLINK_OUTBOX_CONFIGURATION_MISMATCH:
        case EGOLINK_OUTBOX_CRYPTO_ERROR:
            internal->status.phase =
                EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED;
            result->durable_record_retained = true;
            increment_saturated(&internal->status.recovery_required);
            return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
        default:
            /* An impossible/unclassified status makes attempt state
             * uncertain, so fail closed rather than silently advancing. */
            internal->status.phase =
                EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED;
            result->durable_record_retained = true;
            increment_saturated(&internal->status.recovery_required);
            return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
        }
    case EGOLINK_LOCATION_OUTBOX_FINISH_TRANSPORT_STATE_FAILED:
    case EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ARGUMENT:
    default:
        internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED;
        result->durable_record_retained = true;
        increment_saturated(&internal->status.recovery_required);
        return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
    }
}

static egolink_p0_outbox_dispatcher_status_t finish_active(
    p0_outbox_dispatcher_internal_t *internal,
    egolink_p0_outbox_send_view_t *send_view,
    uint16_t http_status_code,
    const char *transport_error_code,
    const uint8_t *response_json,
    size_t response_length,
    uint64_t now_ms,
    egolink_p0_outbox_finish_result_t *result)
{
    result->route = internal->status.active_route;
    invalidate_payload_view(send_view);
    if (internal->status.active_route ==
        EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS) {
        result->sos_finish_status = egolink_sos_outbox_finish_attempt(
            internal->sos_adapter,
            internal->status.active_attempt.attempt_token,
            http_status_code,
            transport_error_code,
            response_json,
            response_length,
            now_ms,
            &internal->canonical_item,
            &result->sos_finish_result);
        return map_sos_finish(internal, send_view, result);
    }
    if (internal->status.active_route ==
        EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE) {
        const bool accepted_by_transport =
            http_status_code >= UINT16_C(200) &&
            http_status_code <= UINT16_C(299);
        result->location_finish_status =
            egolink_location_outbox_finish_attempt(
                internal->location_adapter,
                internal->status.active_attempt.attempt_token,
                accepted_by_transport,
                transport_error_code,
                response_json,
                response_length,
                now_ms,
                &result->location_finish_result);
        return map_location_finish(internal, send_view, result);
    }
    internal->status.phase = EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED;
    clear_canonical_item(internal);
    result->durable_record_retained = true;
    increment_saturated(&internal->status.recovery_required);
    return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_finish(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    egolink_p0_outbox_send_view_t *send_view,
    uint16_t http_status_code,
    const char *transport_error_code,
    const uint8_t *response_json,
    size_t response_length,
    uint64_t now_ms,
    egolink_p0_outbox_finish_result_t *result)
{
    initialize_finish_result(result);
    if (dispatcher == NULL || send_view == NULL || result == NULL) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    }
    p0_outbox_dispatcher_internal_t *internal = internal_of(dispatcher);
    if (!valid_magic(internal)) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle != EGOLINK_P0_OUTBOX_DISPATCHER_ACTIVE) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status =
            internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_DISABLED
                ? EGOLINK_P0_OUTBOX_DISABLED_STATUS
                : EGOLINK_P0_OUTBOX_CLOSED_STATUS;
        return result->status;
    }
    if (internal->status.phase == EGOLINK_P0_OUTBOX_PHASE_IDLE) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_ATTEMPT_MISMATCH;
        return result->status;
    }
    if (!active_view_matches(internal, send_view)) {
        enter_recovery(internal, send_view);
        result->status = EGOLINK_P0_OUTBOX_ATTEMPT_MISMATCH;
        result->route = internal->status.active_route;
        result->durable_record_retained = true;
        result->private_canonical_item_retained =
            internal->status.private_canonical_item_retained;
        update_common_status(internal, result->status);
        return result->status;
    }
    if (!adapters_bound(internal) || !sos_activity_consistent(internal)) {
        enter_recovery(internal, send_view);
        result->status = EGOLINK_P0_OUTBOX_DEPENDENCY_MISMATCH;
        result->route = internal->status.active_route;
        result->durable_record_retained = true;
        result->private_canonical_item_retained =
            internal->status.private_canonical_item_retained;
        update_common_status(internal, result->status);
        return result->status;
    }

    internal->busy = true;
    internal->status.busy = true;
    increment_saturated(&internal->status.finish_calls);
    const egolink_p0_outbox_dispatcher_status_t status = finish_active(
        internal,
        send_view,
        http_status_code,
        transport_error_code,
        response_json,
        response_length,
        now_ms,
        result);
    result->private_canonical_item_retained =
        internal->status.private_canonical_item_retained;
    return return_finish(internal, result, status);
}

static egolink_p0_outbox_dispatcher_status_t cancel_active(
    p0_outbox_dispatcher_internal_t *internal,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_finish_result_t *result)
{
    if (internal->status.phase != EGOLINK_P0_OUTBOX_PHASE_SEND_READY) {
        invalidate_payload_view(send_view);
        result->route = internal->status.active_route;
        result->durable_record_retained = true;
        result->private_canonical_item_retained =
            internal->status.private_canonical_item_retained;
        increment_saturated(&internal->status.recovery_required);
        return EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
    }
    const egolink_p0_outbox_dispatcher_status_t status = finish_active(
        internal,
        send_view,
        UINT16_C(0),
        P0_CANCELLED_ERROR,
        NULL,
        0U,
        now_ms,
        result);
    if (status == EGOLINK_P0_OUTBOX_FINISHED_RETAINED) {
        return EGOLINK_P0_OUTBOX_CANCELLED_RETAINED;
    }
    return status;
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_cancel(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_finish_result_t *result)
{
    initialize_finish_result(result);
    if (dispatcher == NULL || send_view == NULL || result == NULL) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    }
    p0_outbox_dispatcher_internal_t *internal = internal_of(dispatcher);
    if (!valid_magic(internal)) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle != EGOLINK_P0_OUTBOX_DISPATCHER_ACTIVE) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status =
            internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_DISABLED
                ? EGOLINK_P0_OUTBOX_DISABLED_STATUS
                : EGOLINK_P0_OUTBOX_CLOSED_STATUS;
        return result->status;
    }
    if (internal->status.phase == EGOLINK_P0_OUTBOX_PHASE_IDLE) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_OK;
        return result->status;
    }
    if (internal->status.active_route !=
            EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED &&
        !active_view_matches(internal, send_view)) {
        enter_recovery(internal, send_view);
        result->status = EGOLINK_P0_OUTBOX_ATTEMPT_MISMATCH;
        result->route = internal->status.active_route;
        result->durable_record_retained = true;
        result->private_canonical_item_retained =
            internal->status.private_canonical_item_retained;
        update_common_status(internal, result->status);
        return result->status;
    }
    if (!adapters_bound(internal) || !sos_activity_consistent(internal)) {
        enter_recovery(internal, send_view);
        result->status = EGOLINK_P0_OUTBOX_DEPENDENCY_MISMATCH;
        result->route = internal->status.active_route;
        result->durable_record_retained = true;
        result->private_canonical_item_retained =
            internal->status.private_canonical_item_retained;
        update_common_status(internal, result->status);
        return result->status;
    }

    internal->busy = true;
    internal->status.busy = true;
    egolink_p0_outbox_dispatcher_status_t status;
    if (internal->status.active_route ==
            EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED &&
        internal->status.phase == EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED) {
        result->route = internal->status.active_route;
        const egolink_outbox_status_t settlement =
            egolink_outbox_record_transport_result(
                internal->shared_outbox,
                internal->status.active_attempt.attempt_token,
                false,
                P0_INVALID_ROUTE_ERROR,
                now_ms);
        if (settlement == EGOLINK_OUTBOX_OK ||
            settlement == EGOLINK_OUTBOX_DUPLICATE) {
            result->terminal = true;
            result->durable_record_retained = true;
            clear_active(internal);
            egolink_p0_outbox_dispatcher_clear_send_view(send_view);
            status = EGOLINK_P0_OUTBOX_CANCELLED_RETAINED;
        } else {
            result->durable_record_retained = true;
            increment_saturated(&internal->status.recovery_required);
            status = EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
        }
    } else {
        status = cancel_active(internal, now_ms, send_view, result);
    }
    result->private_canonical_item_retained =
        internal->status.private_canonical_item_retained;
    return return_finish(internal, result, status);
}

static void close_bindings(p0_outbox_dispatcher_internal_t *internal)
{
    clear_active(internal);
    internal->shared_outbox = NULL;
    internal->location_adapter = NULL;
    internal->sos_adapter = NULL;
    internal->lifecycle = EGOLINK_P0_OUTBOX_DISPATCHER_CLOSED;
}

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_close(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_finish_result_t *result)
{
    initialize_finish_result(result);
    if (dispatcher == NULL || send_view == NULL || result == NULL) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        return EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    }
    p0_outbox_dispatcher_internal_t *internal = internal_of(dispatcher);
    if (!valid_magic(internal)) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_CLOSED) {
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_CLOSED_STATUS;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_DISABLED) {
        close_bindings(internal);
        egolink_p0_outbox_dispatcher_clear_send_view(send_view);
        result->status = EGOLINK_P0_OUTBOX_CLOSED_STATUS;
        update_common_status(internal, result->status);
        return result->status;
    }
    if (internal->status.phase != EGOLINK_P0_OUTBOX_PHASE_IDLE) {
        if (internal->status.active_route !=
                EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED &&
            !active_view_matches(internal, send_view)) {
            enter_recovery(internal, send_view);
            result->status = EGOLINK_P0_OUTBOX_ATTEMPT_MISMATCH;
            result->route = internal->status.active_route;
            result->durable_record_retained = true;
            result->private_canonical_item_retained =
                internal->status.private_canonical_item_retained;
            update_common_status(internal, result->status);
            return result->status;
        }
        if (internal->status.phase != EGOLINK_P0_OUTBOX_PHASE_SEND_READY) {
            invalidate_payload_view(send_view);
            result->route = internal->status.active_route;
            result->durable_record_retained = true;
            result->private_canonical_item_retained =
                internal->status.private_canonical_item_retained;
            result->status = EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER;
            increment_saturated(&internal->status.recovery_required);
            update_common_status(internal, result->status);
            return result->status;
        }
        if (!adapters_bound(internal) || !sos_activity_consistent(internal)) {
            enter_recovery(internal, send_view);
            result->status = EGOLINK_P0_OUTBOX_DEPENDENCY_MISMATCH;
            result->route = internal->status.active_route;
            result->durable_record_retained = true;
            result->private_canonical_item_retained =
                internal->status.private_canonical_item_retained;
            update_common_status(internal, result->status);
            return result->status;
        }
        internal->busy = true;
        internal->status.busy = true;
        const egolink_p0_outbox_dispatcher_status_t cancelled =
            cancel_active(internal, now_ms, send_view, result);
        if (cancelled != EGOLINK_P0_OUTBOX_CANCELLED_RETAINED) {
            return return_finish(internal, result, cancelled);
        }
    }
    close_bindings(internal);
    egolink_p0_outbox_dispatcher_clear_send_view(send_view);
    result->terminal = true;
    return return_finish(
        internal, result, EGOLINK_P0_OUTBOX_CLOSED_STATUS);
}

egolink_p0_outbox_dispatcher_status_t
egolink_p0_outbox_dispatcher_current_status(
    const egolink_p0_outbox_dispatcher_t *dispatcher,
    egolink_p0_outbox_dispatcher_snapshot_t *snapshot)
{
    if (snapshot != NULL) {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        snapshot->lifecycle =
            EGOLINK_P0_OUTBOX_DISPATCHER_NEVER_INITIALIZED;
        snapshot->last_status = EGOLINK_P0_OUTBOX_NOT_INITIALIZED;
    }
    if (dispatcher == NULL || snapshot == NULL) {
        return EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    }
    const p0_outbox_dispatcher_internal_t *internal =
        internal_of_const(dispatcher);
    if (!valid_magic(internal)) {
        return EGOLINK_P0_OUTBOX_NOT_INITIALIZED;
    }
    *snapshot = internal->status;
    snapshot->lifecycle = internal->lifecycle;
    snapshot->enabled =
        internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_ACTIVE;
    snapshot->dependency_bound = adapters_bound(internal);
    snapshot->busy = internal->busy;
    if (internal->busy) {
        return EGOLINK_P0_OUTBOX_REENTRANT_CALL;
    }
    if (internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_DISABLED) {
        return EGOLINK_P0_OUTBOX_DISABLED_STATUS;
    }
    if (internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_CLOSED) {
        return EGOLINK_P0_OUTBOX_CLOSED_STATUS;
    }
    return EGOLINK_P0_OUTBOX_OK;
}

bool egolink_p0_outbox_dispatcher_dependencies_match(
    const egolink_p0_outbox_dispatcher_t *dispatcher,
    const egolink_outbox_t *shared_outbox,
    const egolink_location_outbox_adapter_t *location_adapter)
{
    if (dispatcher == NULL || shared_outbox == NULL ||
        location_adapter == NULL) {
        return false;
    }
    const p0_outbox_dispatcher_internal_t *internal =
        internal_of_const(dispatcher);
    return valid_magic(internal) &&
        internal->lifecycle == EGOLINK_P0_OUTBOX_DISPATCHER_ACTIVE &&
        internal->shared_outbox == shared_outbox &&
        internal->location_adapter == location_adapter &&
        adapters_bound(internal);
}

const char *egolink_p0_outbox_dispatcher_status_name(
    egolink_p0_outbox_dispatcher_status_t status)
{
    switch (status) {
    case EGOLINK_P0_OUTBOX_OK: return "ok";
    case EGOLINK_P0_OUTBOX_BEGIN_READY: return "begin_ready";
    case EGOLINK_P0_OUTBOX_NO_DUE_RECORD: return "no_due_record";
    case EGOLINK_P0_OUTBOX_INVALID_EVENT_RETAINED:
        return "invalid_event_retained";
    case EGOLINK_P0_OUTBOX_ACK_DELETED: return "ack_deleted";
    case EGOLINK_P0_OUTBOX_ACK_ALREADY_APPLIED:
        return "ack_already_applied";
    case EGOLINK_P0_OUTBOX_FINISHED_RETAINED: return "finished_retained";
    case EGOLINK_P0_OUTBOX_CANCELLED_RETAINED: return "cancelled_retained";
    case EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER:
        return "must_finish_or_recover";
    case EGOLINK_P0_OUTBOX_ATTEMPT_ALREADY_ACTIVE:
        return "attempt_already_active";
    case EGOLINK_P0_OUTBOX_ATTEMPT_MISMATCH: return "attempt_mismatch";
    case EGOLINK_P0_OUTBOX_DEPENDENCY_RECOVERY_REQUIRED:
        return "dependency_recovery_required";
    case EGOLINK_P0_OUTBOX_DEPENDENCY_MISMATCH:
        return "dependency_mismatch";
    case EGOLINK_P0_OUTBOX_DISABLED_STATUS: return "disabled";
    case EGOLINK_P0_OUTBOX_CLOSED_STATUS: return "closed";
    case EGOLINK_P0_OUTBOX_INVALID_ARGUMENT: return "invalid_argument";
    case EGOLINK_P0_OUTBOX_NOT_INITIALIZED: return "not_initialized";
    case EGOLINK_P0_OUTBOX_ALREADY_INITIALIZED:
        return "already_initialized";
    case EGOLINK_P0_OUTBOX_REENTRANT_CALL: return "reentrant_call";
    default: return "unknown";
    }
}

const char *egolink_p0_outbox_route_name(egolink_p0_outbox_route_t route)
{
    switch (route) {
    case EGOLINK_P0_OUTBOX_ROUTE_NONE: return "none";
    case EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS: return "manual_sos";
    case EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE: return "location_state";
    case EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED:
        return "invalid_retained";
    default: return "unknown";
    }
}

const char *egolink_p0_outbox_phase_name(egolink_p0_outbox_phase_t phase)
{
    switch (phase) {
    case EGOLINK_P0_OUTBOX_PHASE_IDLE: return "idle";
    case EGOLINK_P0_OUTBOX_PHASE_SEND_READY: return "send_ready";
    case EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED:
        return "recovery_required";
    default: return "unknown";
    }
}

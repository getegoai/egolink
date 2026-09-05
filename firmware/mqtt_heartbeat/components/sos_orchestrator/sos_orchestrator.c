#include "sos_orchestrator.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

_Static_assert(
    EGOLINK_SOS_ORCHESTRATOR_PAYLOAD_MAX_BYTES <=
        EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES,
    "SOS payload ceiling must fit the outbox ceiling");
_Static_assert(
    EGOLINK_SOS_ORCHESTRATOR_EVENT_ID_CAPACITY <=
        EGOLINK_OUTBOX_ID_CAPACITY,
    "SOS event ID must fit the outbox identity field");

typedef enum {
    PAYLOAD_BUILD_OK = 0,
    PAYLOAD_BUILD_UNAVAILABLE,
    PAYLOAD_BUILD_INVALID,
    PAYLOAD_BUILD_OVERFLOW,
} payload_build_status_t;

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

static bool ascii_id_first(char value)
{
    return (value >= 'A' && value <= 'Z') ||
        (value >= 'a' && value <= 'z') ||
        (value >= '0' && value <= '9');
}

static bool ascii_id_rest(char value)
{
    return ascii_id_first(value) || value == '.' || value == '_' ||
        value == ':' || value == '@' || value == '-';
}

static bool safe_identifier(const char *value)
{
    const size_t length = bounded_length(value, EGOLINK_OUTBOX_ID_CAPACITY);
    if (length == 0U || length >= EGOLINK_OUTBOX_ID_CAPACITY ||
        !ascii_id_first(value[0])) {
        return false;
    }
    for (size_t index = 1U; index < length; ++index) {
        if (!ascii_id_rest(value[index])) {
            return false;
        }
    }
    return true;
}

static void secure_zero(void *buffer, size_t length)
{
    volatile uint8_t *cursor = (volatile uint8_t *)buffer;
    while (length > 0U) {
        *cursor = 0U;
        ++cursor;
        --length;
    }
}

static size_t bounded_scratch_length(size_t capacity)
{
    const size_t maximum =
        (size_t)EGOLINK_SOS_ORCHESTRATOR_PAYLOAD_MAX_BYTES + 1U;
    return capacity < maximum ? capacity : maximum;
}

static void wipe_scratch(char *scratch, size_t capacity)
{
    if (scratch != NULL) {
        secure_zero(scratch, bounded_scratch_length(capacity));
    }
}

static void clear_result(egolink_sos_orchestration_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->persistence_state = EGOLINK_SOS_PERSISTENCE_NOT_ATTEMPTED;
        result->durable_ready = EGOLINK_SOS_BRANCH_NOT_CONFIGURED;
        result->outbox_status = EGOLINK_OUTBOX_NOT_INITIALIZED;
        result->policy_status = EGOLINK_LOCATION_POLICY_NOT_INITIALIZED;
        result->local_feedback = EGOLINK_SOS_BRANCH_NOT_CONFIGURED;
        result->location_enqueue = EGOLINK_SOS_BRANCH_NOT_CONFIGURED;
        result->call_request = EGOLINK_SOS_BRANCH_NOT_CONFIGURED;
    }
}

static bool context_identity_valid(
    const egolink_sos_event_context_t *context)
{
    return context != NULL && safe_identifier(context->session_id);
}

static bool build_event_id(
    const egolink_sos_event_context_t *context,
    uint64_t edge_time_ms,
    char output[EGOLINK_SOS_ORCHESTRATOR_EVENT_ID_CAPACITY])
{
    const int written = snprintf(
        output,
        EGOLINK_SOS_ORCHESTRATOR_EVENT_ID_CAPACITY,
        "sos-b%" PRIu64 "-q%" PRIu64 "-t%" PRIu64,
        context->boot_count,
        context->source_sequence,
        edge_time_ms);
    return written > 0 &&
        (size_t)written < EGOLINK_SOS_ORCHESTRATOR_EVENT_ID_CAPACITY;
}

static payload_build_status_t build_payload(
    const char *event_id,
    uint64_t edge_time_ms,
    const char *device_id,
    const egolink_sos_event_context_t *context,
    char *scratch,
    size_t scratch_capacity,
    size_t *payload_length)
{
    if (payload_length == NULL) {
        return PAYLOAD_BUILD_INVALID;
    }
    *payload_length = 0U;
    if (scratch == NULL || scratch_capacity == 0U) {
        return PAYLOAD_BUILD_UNAVAILABLE;
    }

    char battery[32];
    if (context->battery_percent_available) {
        if (context->battery_percent > 100U) {
            return PAYLOAD_BUILD_INVALID;
        }
        const int battery_written = snprintf(
            battery,
            sizeof(battery),
            "%" PRIu32,
            context->battery_percent);
        if (battery_written <= 0 ||
            (size_t)battery_written >= sizeof(battery)) {
            secure_zero(battery, sizeof(battery));
            return PAYLOAD_BUILD_INVALID;
        }
    } else {
        (void)memcpy(battery, "null", sizeof("null"));
    }

    const size_t format_capacity = bounded_scratch_length(scratch_capacity);
    const int written = snprintf(
        scratch,
        format_capacity,
        "{\"contract_version\":\"1.0.0\","
        "\"event_id\":\"%s\",\"device_id\":\"%s\","
        "\"timestamp_ms\":%" PRIu64 ",\"sequence\":%" PRIu64 ","
        "\"event_type\":\"manual_sos\",\"priority\":\"critical\","
        "\"source\":\"device_rule\",\"model_result\":{"
        "\"manual_input\":true,\"qualified_long_press\":true,"
        "\"time_source\":\"boot_monotonic_ms\",\"boot_count\":%" PRIu64 ","
        "\"session_id\":\"%s\",\"source_sequence\":%" PRIu64 "},"
        "\"context\":{\"mode\":\"manual_sos\",\"battery_percent\":%s,"
        "\"base_online\":%s,\"upload_available\":%s},"
        "\"evidence\":{\"audio_clip_ref\":null,\"image_ref\":null,"
        "\"imu_window_ref\":null,\"location_fresh\":false},"
        "\"privacy\":{\"privacy_mode\":true,"
        "\"raw_evidence_allowed\":false,\"retention_seconds\":86400}}",
        event_id,
        device_id,
        edge_time_ms,
        context->source_sequence,
        context->boot_count,
        context->session_id,
        context->source_sequence,
        battery,
        context->base_online ? "true" : "false",
        context->upload_available ? "true" : "false");
    secure_zero(battery, sizeof(battery));
    if (written <= 0 || (size_t)written >= format_capacity ||
        (size_t)written > EGOLINK_SOS_ORCHESTRATOR_PAYLOAD_MAX_BYTES) {
        wipe_scratch(scratch, scratch_capacity);
        return PAYLOAD_BUILD_OVERFLOW;
    }
    *payload_length = (size_t)written;
    return PAYLOAD_BUILD_OK;
}

static egolink_sos_branch_identity_t make_branch_identity(
    const egolink_sos_orchestrator_t *orchestrator,
    const egolink_sos_orchestration_result_t *result,
    const egolink_sos_event_context_t *context,
    uint64_t edge_time_ms)
{
    const egolink_sos_branch_identity_t identity = {
        .device_id = orchestrator->device_id,
        .event_id = result->event_id,
        .source_event_time_ms = edge_time_ms,
        .boot_count = context->boot_count,
        .session_id = context->session_id,
        .source_sequence = context->source_sequence,
    };
    return identity;
}

static egolink_sos_branch_state_t attempt_feedback(
    const egolink_sos_orchestrator_t *orchestrator,
    const egolink_sos_branch_identity_t *identity)
{
    if (orchestrator->callbacks.local_feedback == NULL) {
        return EGOLINK_SOS_BRANCH_NOT_CONFIGURED;
    }
    return orchestrator->callbacks.local_feedback(
        orchestrator->callbacks.local_feedback_context, identity)
        ? EGOLINK_SOS_BRANCH_SUCCEEDED
        : EGOLINK_SOS_BRANCH_FAILED;
}

static egolink_sos_branch_state_t attempt_location_enqueue(
    const egolink_sos_orchestrator_t *orchestrator,
    const egolink_sos_branch_identity_t *identity,
    const egolink_location_policy_snapshot_t *snapshot)
{
    if (orchestrator->callbacks.enqueue_location == NULL) {
        return EGOLINK_SOS_BRANCH_NOT_CONFIGURED;
    }
    const bool trusted_available =
        snapshot != NULL && snapshot->last_trusted_time_available &&
        snapshot->last_trusted_time_ms <= identity->source_event_time_ms;
    const egolink_sos_location_enqueue_request_t request = {
        .identity = *identity,
        .urgent = true,
        .request_last_trusted = true,
        .last_trusted_available = trusted_available,
        .last_trusted_time_ms = trusted_available
            ? snapshot->last_trusted_time_ms
            : UINT64_C(0),
        .request_current = true,
    };
    return orchestrator->callbacks.enqueue_location(
        orchestrator->callbacks.location_context, &request)
        ? EGOLINK_SOS_BRANCH_SUCCEEDED
        : EGOLINK_SOS_BRANCH_FAILED;
}

static egolink_sos_branch_state_t attempt_call(
    const egolink_sos_orchestrator_t *orchestrator,
    const egolink_sos_branch_identity_t *identity)
{
    if (orchestrator->callbacks.request_call == NULL) {
        return EGOLINK_SOS_BRANCH_NOT_CONFIGURED;
    }
    const egolink_sos_call_request_t request = {
        .identity = *identity,
        .safety_event_ref = identity->event_id,
        .manual_sos = true,
    };
    return orchestrator->callbacks.request_call(
        orchestrator->callbacks.call_context, &request)
        ? EGOLINK_SOS_BRANCH_SUCCEEDED
        : EGOLINK_SOS_BRANCH_FAILED;
}

static void attempt_policy(
    egolink_sos_orchestrator_t *orchestrator,
    const egolink_location_policy_snapshot_t *snapshot,
    uint64_t edge_time_ms,
    egolink_sos_orchestration_result_t *result)
{
    result->policy_attempted = true;
    if (snapshot == NULL) {
        result->policy_status = EGOLINK_LOCATION_POLICY_INVALID_ARGUMENT;
        return;
    }
    egolink_location_policy_snapshot_t sos_snapshot = *snapshot;
    sos_snapshot.event_time_ms = edge_time_ms;
    sos_snapshot.sos_active = true;
    const egolink_location_policy_event_t event = {
        .type = EGOLINK_LOCATION_POLICY_EVENT_SOS,
        .event_time_ms = edge_time_ms,
        .attributable_lineage = true,
    };
    egolink_location_policy_decision_t decision;
    result->policy_status = egolink_location_policy_evaluate(
        orchestrator->policy_core, &sos_snapshot, &event, &decision);
    if (result->policy_status == EGOLINK_LOCATION_POLICY_OK) {
        result->policy_mode = decision.policy_mode;
        result->policy_sos_active =
            decision.policy_mode == EGOLINK_LOCATION_POLICY_SOS &&
            decision.conditions.sos_active;
    }
}

static bool persistence_succeeded(
    egolink_sos_persistence_state_t state)
{
    return state == EGOLINK_SOS_PERSISTENCE_COMMITTED ||
        state == EGOLINK_SOS_PERSISTENCE_DUPLICATE;
}

egolink_sos_orchestration_status_t egolink_sos_orchestrator_init(
    egolink_sos_orchestrator_t *orchestrator,
    egolink_outbox_t *outbox,
    egolink_location_policy_core_t *policy_core,
    const char *device_id,
    const egolink_sos_orchestrator_callbacks_t *callbacks)
{
    if (orchestrator == NULL || outbox == NULL || policy_core == NULL ||
        !safe_identifier(device_id) || callbacks == NULL) {
        return EGOLINK_SOS_ORCHESTRATION_INVALID_ARGUMENT;
    }
    (void)memset(orchestrator, 0, sizeof(*orchestrator));
    orchestrator->outbox = outbox;
    orchestrator->policy_core = policy_core;
    orchestrator->callbacks = *callbacks;
    const size_t device_id_length = strlen(device_id);
    (void)memcpy(
        orchestrator->device_id, device_id, device_id_length + 1U);
    orchestrator->initialized = true;
    return EGOLINK_SOS_ORCHESTRATION_OK;
}

egolink_sos_orchestration_status_t egolink_sos_orchestrate_edge(
    egolink_sos_orchestrator_t *orchestrator,
    const egolink_sos_input_output_t *edge,
    const egolink_sos_event_context_t *event_context,
    const egolink_location_policy_snapshot_t *policy_snapshot,
    uint64_t now_ms,
    char *payload_scratch,
    size_t payload_scratch_capacity,
    egolink_sos_orchestration_result_t *result)
{
    clear_result(result);
    wipe_scratch(payload_scratch, payload_scratch_capacity);
    if (orchestrator == NULL || edge == NULL || event_context == NULL ||
        result == NULL) {
        return EGOLINK_SOS_ORCHESTRATION_INVALID_ARGUMENT;
    }
    if (!orchestrator->initialized || orchestrator->outbox == NULL ||
        orchestrator->policy_core == NULL) {
        return EGOLINK_SOS_ORCHESTRATION_NOT_INITIALIZED;
    }
    if (!edge->sos_edge) {
        return EGOLINK_SOS_ORCHESTRATION_NO_EDGE;
    }
    if (!context_identity_valid(event_context) ||
        (!event_context->recovered_pending_edge &&
         edge->sos_edge_time_ms > now_ms) ||
        !build_event_id(
            event_context, edge->sos_edge_time_ms, result->event_id)) {
        return EGOLINK_SOS_ORCHESTRATION_INVALID_CONTEXT;
    }

    size_t payload_length = 0U;
    const payload_build_status_t payload_status = build_payload(
        result->event_id,
        edge->sos_edge_time_ms,
        orchestrator->device_id,
        event_context,
        payload_scratch,
        payload_scratch_capacity,
        &payload_length);
    if (payload_status == PAYLOAD_BUILD_OK) {
        const egolink_outbox_enqueue_request_t enqueue = {
            .event_id = result->event_id,
            .event_type = EGOLINK_SOS_ORCHESTRATOR_EVENT_TYPE,
            .priority = EGOLINK_OUTBOX_PRIORITY_CRITICAL,
            .payload_kind = EGOLINK_OUTBOX_PAYLOAD_EVENT_JSON,
            .payload = (const uint8_t *)payload_scratch,
            .payload_length = payload_length,
            .source_time_kind =
                EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS,
            .source_event_time_ms = edge->sos_edge_time_ms,
            .boot_count = event_context->boot_count,
            .session_id = event_context->session_id,
            .source_sequence = event_context->source_sequence,
        };
        egolink_outbox_record_view_t record;
        result->outbox_attempted = true;
        result->outbox_status = egolink_outbox_enqueue(
            orchestrator->outbox, &enqueue, now_ms, &record);
        result->payload_length = payload_length;
        if (result->outbox_status == EGOLINK_OUTBOX_OK ||
            result->outbox_status == EGOLINK_OUTBOX_DUPLICATE) {
            (void)memcpy(
                result->payload_sha256,
                record.payload_sha256,
                sizeof(result->payload_sha256));
            result->replayed_durable_identity =
                result->outbox_status == EGOLINK_OUTBOX_DUPLICATE;
            result->persistence_state = result->replayed_durable_identity
                ? EGOLINK_SOS_PERSISTENCE_DUPLICATE
                : EGOLINK_SOS_PERSISTENCE_COMMITTED;
        } else {
            result->persistence_state =
                EGOLINK_SOS_PERSISTENCE_OUTBOX_FAILED;
        }
    } else if (payload_status == PAYLOAD_BUILD_UNAVAILABLE) {
        result->persistence_state =
            EGOLINK_SOS_PERSISTENCE_PAYLOAD_UNAVAILABLE;
    } else if (payload_status == PAYLOAD_BUILD_INVALID) {
        result->persistence_state = EGOLINK_SOS_PERSISTENCE_PAYLOAD_INVALID;
    } else {
        result->persistence_state = EGOLINK_SOS_PERSISTENCE_PAYLOAD_OVERFLOW;
    }
    wipe_scratch(payload_scratch, payload_scratch_capacity);

    const egolink_sos_branch_identity_t identity = make_branch_identity(
        orchestrator, result, event_context, edge->sos_edge_time_ms);
    if (persistence_succeeded(result->persistence_state)) {
        result->durable_ready = orchestrator->callbacks.durable_ready == NULL
            ? EGOLINK_SOS_BRANCH_NOT_CONFIGURED
            : (orchestrator->callbacks.durable_ready(
                   orchestrator->callbacks.durable_ready_context,
                   &identity,
                   result->persistence_state)
                   ? EGOLINK_SOS_BRANCH_SUCCEEDED
                   : EGOLINK_SOS_BRANCH_FAILED);
    }
    result->local_feedback = attempt_feedback(orchestrator, &identity);
    const uint64_t policy_action_time_ms =
        event_context->recovered_pending_edge
        ? now_ms
        : edge->sos_edge_time_ms;
    attempt_policy(
        orchestrator,
        policy_snapshot,
        policy_action_time_ms,
        result);
    result->location_enqueue = attempt_location_enqueue(
        orchestrator, &identity, policy_snapshot);
    result->call_request = attempt_call(orchestrator, &identity);

    const bool complete = persistence_succeeded(result->persistence_state) &&
        (result->durable_ready == EGOLINK_SOS_BRANCH_SUCCEEDED ||
         result->durable_ready == EGOLINK_SOS_BRANCH_NOT_CONFIGURED) &&
        result->local_feedback == EGOLINK_SOS_BRANCH_SUCCEEDED &&
        result->policy_status == EGOLINK_LOCATION_POLICY_OK &&
        result->policy_sos_active &&
        result->location_enqueue == EGOLINK_SOS_BRANCH_SUCCEEDED &&
        result->call_request == EGOLINK_SOS_BRANCH_SUCCEEDED;
    return complete
        ? EGOLINK_SOS_ORCHESTRATION_OK
        : EGOLINK_SOS_ORCHESTRATION_PARTIAL_FAILURE;
}

const char *egolink_sos_orchestration_status_name(
    egolink_sos_orchestration_status_t status)
{
    switch (status) {
    case EGOLINK_SOS_ORCHESTRATION_OK: return "ok";
    case EGOLINK_SOS_ORCHESTRATION_NO_EDGE: return "no_edge";
    case EGOLINK_SOS_ORCHESTRATION_PARTIAL_FAILURE: return "partial_failure";
    case EGOLINK_SOS_ORCHESTRATION_INVALID_ARGUMENT: return "invalid_argument";
    case EGOLINK_SOS_ORCHESTRATION_NOT_INITIALIZED: return "not_initialized";
    case EGOLINK_SOS_ORCHESTRATION_INVALID_CONTEXT: return "invalid_context";
    default: return "unknown";
    }
}

const char *egolink_sos_persistence_state_name(
    egolink_sos_persistence_state_t state)
{
    switch (state) {
    case EGOLINK_SOS_PERSISTENCE_NOT_ATTEMPTED: return "not_attempted";
    case EGOLINK_SOS_PERSISTENCE_COMMITTED: return "committed";
    case EGOLINK_SOS_PERSISTENCE_DUPLICATE: return "duplicate";
    case EGOLINK_SOS_PERSISTENCE_PAYLOAD_UNAVAILABLE:
        return "payload_unavailable";
    case EGOLINK_SOS_PERSISTENCE_PAYLOAD_INVALID: return "payload_invalid";
    case EGOLINK_SOS_PERSISTENCE_PAYLOAD_OVERFLOW: return "payload_overflow";
    case EGOLINK_SOS_PERSISTENCE_OUTBOX_FAILED: return "outbox_failed";
    default: return "unknown";
    }
}

const char *egolink_sos_branch_state_name(egolink_sos_branch_state_t state)
{
    switch (state) {
    case EGOLINK_SOS_BRANCH_NOT_CONFIGURED: return "not_configured";
    case EGOLINK_SOS_BRANCH_SUCCEEDED: return "succeeded";
    case EGOLINK_SOS_BRANCH_FAILED: return "failed";
    default: return "unknown";
    }
}

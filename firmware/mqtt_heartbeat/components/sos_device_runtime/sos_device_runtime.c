#include "sos_device_runtime.h"

#include <string.h>

#define SOS_DEVICE_RUNTIME_MAGIC UINT32_C(0x534f5352)

typedef struct {
    uint32_t magic;
    egolink_sos_device_runtime_lifecycle_t lifecycle;
    bool busy;
    egolink_outbox_t *shared_outbox;
    egolink_sos_outbox_adapter_t *delivery_adapter;
    egolink_sos_pending_edge_journal_t *pending_journal;
    egolink_location_policy_core_t *policy_core;
    egolink_sos_device_runtime_callbacks_t callbacks;
    uint64_t boot_count;
    uint64_t next_source_sequence;
    bool source_sequence_exhausted;
    bool pending_edge_available;
    bool pending_edge_durable;
    bool pending_sequence_consumed;
    egolink_sos_pending_edge_record_t pending_edge;
    char session_id[EGOLINK_OUTBOX_ID_CAPACITY];
    egolink_sos_input_t input;
    egolink_sos_orchestrator_t orchestrator;
    char payload_scratch[EGOLINK_SOS_ORCHESTRATOR_PAYLOAD_MAX_BYTES + 1U];
    egolink_sos_device_runtime_snapshot_t status;
} sos_device_runtime_internal_t;

_Static_assert(
    sizeof(sos_device_runtime_internal_t) <=
        EGOLINK_SOS_DEVICE_RUNTIME_CONTEXT_BYTES,
    "SOS device runtime context is too small");

static sos_device_runtime_internal_t *runtime_internal(
    egolink_sos_device_runtime_t *runtime)
{
    return (sos_device_runtime_internal_t *)(void *)runtime->opaque;
}

static const sos_device_runtime_internal_t *runtime_internal_const(
    const egolink_sos_device_runtime_t *runtime)
{
    return (const sos_device_runtime_internal_t *)(const void *)
        runtime->opaque;
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

static size_t bounded_string_length(const char *value, size_t capacity)
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
    const size_t length = bounded_string_length(
        value, EGOLINK_OUTBOX_ID_CAPACITY);
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

static bool valid_magic(const sos_device_runtime_internal_t *internal)
{
    return internal != NULL &&
        internal->magic == SOS_DEVICE_RUNTIME_MAGIC;
}

static bool dependencies_match(
    const sos_device_runtime_internal_t *internal)
{
    return internal->shared_outbox != NULL &&
        internal->delivery_adapter != NULL &&
        internal->delivery_adapter->initialized &&
        internal->delivery_adapter->outbox == internal->shared_outbox &&
        internal->pending_journal != NULL &&
        egolink_sos_pending_edge_journal_is_initialized(
            internal->pending_journal) &&
        egolink_sos_pending_edge_journal_matches_device(
            internal->pending_journal, internal->orchestrator.device_id) &&
        internal->policy_core != NULL && internal->policy_core->initialized &&
        internal->orchestrator.initialized &&
        internal->orchestrator.outbox == internal->shared_outbox &&
        internal->orchestrator.policy_core == internal->policy_core;
}

static egolink_sos_device_runtime_status_t lifecycle_status(
    egolink_sos_device_runtime_lifecycle_t lifecycle)
{
    switch (lifecycle) {
    case EGOLINK_SOS_DEVICE_RUNTIME_DISABLED:
        return EGOLINK_SOS_DEVICE_RUNTIME_DISABLED_STATUS;
    case EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED:
        return EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS;
    case EGOLINK_SOS_DEVICE_RUNTIME_CLOSED:
        return EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS;
    case EGOLINK_SOS_DEVICE_RUNTIME_ACTIVE:
        return EGOLINK_SOS_DEVICE_RUNTIME_OK;
    case EGOLINK_SOS_DEVICE_RUNTIME_NEVER_INITIALIZED:
    default:
        return EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED;
    }
}

static void set_last_status(
    sos_device_runtime_internal_t *internal,
    egolink_sos_device_runtime_status_t status)
{
    internal->status.lifecycle = internal->lifecycle;
    internal->status.last_status = status;
    internal->status.enabled =
        internal->lifecycle == EGOLINK_SOS_DEVICE_RUNTIME_ACTIVE;
    internal->status.busy = internal->busy;
    internal->status.dependencies_bound = dependencies_match(internal);
    internal->status.dispatcher_attempt_observed_active =
        internal->delivery_adapter != NULL &&
        internal->delivery_adapter->attempt_active;
    internal->status.source_sequence_exhausted =
        internal->source_sequence_exhausted;
    internal->status.pending_edge_available =
        internal->pending_edge_available;
    internal->status.pending_edge_durable = internal->pending_edge_durable;
    internal->status.next_source_sequence = internal->next_source_sequence;
}

static void initialize_process_result(
    egolink_sos_device_runtime_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT;
    result->input_status = EGOLINK_SOS_INPUT_STATUS_INVALID_ARGUMENT;
    result->orchestration_status =
        EGOLINK_SOS_ORCHESTRATION_INVALID_ARGUMENT;
    result->journal_store_status =
        EGOLINK_SOS_PENDING_EDGE_NOT_INITIALIZED;
    result->journal_clear_status =
        EGOLINK_SOS_PENDING_EDGE_NOT_INITIALIZED;
    result->sender_wake = EGOLINK_SOS_BRANCH_NOT_CONFIGURED;
}

static void initialize_shutdown_result(
    egolink_sos_device_runtime_shutdown_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT;
}

static egolink_location_policy_snapshot_t conservative_policy_snapshot(
    uint64_t event_time_ms)
{
    const egolink_location_policy_snapshot_t snapshot = {
        .event_time_ms = event_time_ms,
        .mobility_state = EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN,
        .gnss_state = EGOLINK_LOCATION_POLICY_GNSS_UNAVAILABLE,
        .battery_state = EGOLINK_LOCATION_POLICY_BATTERY_UNKNOWN,
        .battery_percent_available = false,
        .battery_percent = 0.0,
        .sos_active = false,
        .location_belief = EGOLINK_LOCATION_POLICY_BELIEF_UNKNOWN,
        .location_uncertainty_available = false,
        .location_uncertainty_m = 0.0,
        .last_trusted_time_available = false,
        .last_trusted_time_ms = UINT64_C(0),
    };
    return snapshot;
}

static bool persistence_succeeded(egolink_sos_persistence_state_t state)
{
    return state == EGOLINK_SOS_PERSISTENCE_COMMITTED ||
        state == EGOLINK_SOS_PERSISTENCE_DUPLICATE;
}

static egolink_sos_branch_state_t wake_sender(
    const sos_device_runtime_internal_t *internal,
    const egolink_sos_branch_identity_t *identity,
    egolink_sos_persistence_state_t persistence_state)
{
    if (internal->callbacks.wake_sender == NULL) {
        return EGOLINK_SOS_BRANCH_NOT_CONFIGURED;
    }
    const egolink_sos_sender_wake_request_t request = {
        .identity = identity,
        .durable_manual_sos_available =
            persistence_succeeded(persistence_state),
        .persistence_state = persistence_state,
    };
    return internal->callbacks.wake_sender(
               internal->callbacks.sender_context, &request)
        ? EGOLINK_SOS_BRANCH_SUCCEEDED
        : EGOLINK_SOS_BRANCH_FAILED;
}

static bool notify_durable_ready(
    void *context,
    const egolink_sos_branch_identity_t *identity,
    egolink_sos_persistence_state_t persistence_state)
{
    const sos_device_runtime_internal_t *internal =
        (const sos_device_runtime_internal_t *)context;
    return wake_sender(internal, identity, persistence_state) ==
        EGOLINK_SOS_BRANCH_SUCCEEDED;
}

void egolink_sos_device_runtime_default_config(
    egolink_sos_device_runtime_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->enabled = false;
        config->input.debounce_ms = EGOLINK_SOS_INPUT_DEFAULT_DEBOUNCE_MS;
        config->input.long_press_ms =
            EGOLINK_SOS_INPUT_DEFAULT_LONG_PRESS_MS;
        config->first_source_sequence = UINT64_C(1);
    }
}

egolink_sos_device_runtime_status_t egolink_sos_device_runtime_init(
    egolink_sos_device_runtime_t *runtime,
    const egolink_sos_device_runtime_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_sos_outbox_adapter_t *delivery_adapter,
    egolink_sos_pending_edge_journal_t *pending_journal,
    egolink_location_policy_core_t *policy_core,
    bool initial_raw_pressed,
    uint64_t now_ms)
{
    if (runtime == NULL || config == NULL) {
        return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT;
    }
    sos_device_runtime_internal_t *internal = runtime_internal(runtime);
    if (valid_magic(internal)) {
        return EGOLINK_SOS_DEVICE_RUNTIME_ALREADY_INITIALIZED;
    }
    secure_clear(runtime, sizeof(*runtime));
    internal = runtime_internal(runtime);
    internal->magic = SOS_DEVICE_RUNTIME_MAGIC;
    internal->lifecycle = EGOLINK_SOS_DEVICE_RUNTIME_DISABLED;
    internal->status.lifecycle = internal->lifecycle;
    internal->status.last_status =
        EGOLINK_SOS_DEVICE_RUNTIME_DISABLED_STATUS;
    if (!config->enabled) {
        set_last_status(
            internal, EGOLINK_SOS_DEVICE_RUNTIME_DISABLED_STATUS);
        return EGOLINK_SOS_DEVICE_RUNTIME_DISABLED_STATUS;
    }
    if (shared_outbox == NULL || delivery_adapter == NULL ||
        !delivery_adapter->initialized ||
        delivery_adapter->outbox != shared_outbox ||
        pending_journal == NULL ||
        !egolink_sos_pending_edge_journal_is_initialized(pending_journal) ||
        !egolink_sos_pending_edge_journal_matches_device(
            pending_journal, config->device_id) || policy_core == NULL ||
        !policy_core->initialized) {
        secure_clear(runtime, sizeof(*runtime));
        return EGOLINK_SOS_DEVICE_RUNTIME_DEPENDENCY_MISMATCH;
    }
    if (!safe_identifier(config->device_id) ||
        !safe_identifier(config->session_id) ||
        !safe_identifier(delivery_adapter->device_id) ||
        strcmp(config->device_id, delivery_adapter->device_id) != 0 ||
        config->boot_count > EGOLINK_SOS_OUTBOX_JSON_SAFE_INTEGER_MAX ||
        config->first_source_sequence >
            EGOLINK_SOS_OUTBOX_JSON_SAFE_INTEGER_MAX ||
        now_ms > EGOLINK_SOS_OUTBOX_JSON_SAFE_INTEGER_MAX) {
        secure_clear(runtime, sizeof(*runtime));
        return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_CONFIG;
    }

    const egolink_sos_input_status_t input_status = egolink_sos_input_init(
        &internal->input,
        &config->input,
        initial_raw_pressed,
        now_ms);
    if (input_status != EGOLINK_SOS_INPUT_STATUS_OK) {
        secure_clear(runtime, sizeof(*runtime));
        return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_CONFIG;
    }
    internal->shared_outbox = shared_outbox;
    internal->delivery_adapter = delivery_adapter;
    internal->pending_journal = pending_journal;
    internal->policy_core = policy_core;
    internal->callbacks = config->callbacks;
    internal->boot_count = config->boot_count;
    internal->next_source_sequence = config->first_source_sequence;

    egolink_sos_orchestrator_callbacks_t orchestrator_callbacks = {
        .durable_ready = config->callbacks.wake_sender == NULL
            ? NULL
            : notify_durable_ready,
        .durable_ready_context = internal,
        .local_feedback = config->callbacks.local_feedback,
        .local_feedback_context = config->callbacks.local_feedback_context,
        .enqueue_location = config->callbacks.request_urgent_location,
        .location_context = config->callbacks.location_context,
        .request_call = config->callbacks.request_call,
        .call_context = config->callbacks.call_context,
    };
    const egolink_sos_orchestration_status_t orchestrator_status =
        egolink_sos_orchestrator_init(
            &internal->orchestrator,
            shared_outbox,
            policy_core,
            config->device_id,
            &orchestrator_callbacks);
    secure_clear(&orchestrator_callbacks, sizeof(orchestrator_callbacks));
    if (orchestrator_status != EGOLINK_SOS_ORCHESTRATION_OK) {
        secure_clear(runtime, sizeof(*runtime));
        return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_CONFIG;
    }
    const size_t session_length = bounded_string_length(
        config->session_id, sizeof(internal->session_id));
    (void)memcpy(
        internal->session_id, config->session_id, session_length + 1U);

    egolink_sos_pending_edge_record_t recovered_edge;
    const egolink_sos_pending_edge_status_t journal_status =
        egolink_sos_pending_edge_journal_load(
            internal->pending_journal, &recovered_edge);
    internal->status.last_journal_status = journal_status;
    if (journal_status == EGOLINK_SOS_PENDING_EDGE_OK) {
        if (recovered_edge.boot_count > internal->boot_count ||
            (recovered_edge.boot_count == internal->boot_count &&
             strcmp(recovered_edge.session_id, internal->session_id) != 0)) {
            secure_clear(&recovered_edge, sizeof(recovered_edge));
            secure_clear(runtime, sizeof(*runtime));
            return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_CONFIG;
        }
        internal->pending_edge = recovered_edge;
        internal->pending_edge_available = true;
        internal->pending_edge_durable = true;
        internal->pending_sequence_consumed = true;
        if (recovered_edge.boot_count == internal->boot_count &&
            recovered_edge.source_sequence >=
                internal->next_source_sequence) {
            if (recovered_edge.source_sequence ==
                EGOLINK_SOS_PENDING_EDGE_JSON_SAFE_INTEGER_MAX) {
                internal->next_source_sequence =
                    EGOLINK_SOS_PENDING_EDGE_JSON_SAFE_INTEGER_MAX;
                internal->source_sequence_exhausted = true;
            } else {
                internal->next_source_sequence =
                    recovered_edge.source_sequence + UINT64_C(1);
            }
        }
        secure_clear(&recovered_edge, sizeof(recovered_edge));
    } else if (journal_status != EGOLINK_SOS_PENDING_EDGE_NOT_FOUND) {
        secure_clear(&recovered_edge, sizeof(recovered_edge));
        secure_clear(runtime, sizeof(*runtime));
        return EGOLINK_SOS_DEVICE_RUNTIME_JOURNAL_FAILED;
    }
    secure_clear(&recovered_edge, sizeof(recovered_edge));
    internal->lifecycle = EGOLINK_SOS_DEVICE_RUNTIME_ACTIVE;
    const egolink_sos_device_runtime_status_t init_status =
        internal->pending_edge_available
        ? EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED
        : EGOLINK_SOS_DEVICE_RUNTIME_OK;
    set_last_status(internal, init_status);
    return init_status;
}

static bool journal_store_succeeded(
    egolink_sos_pending_edge_status_t status)
{
    return status == EGOLINK_SOS_PENDING_EDGE_OK ||
        status == EGOLINK_SOS_PENDING_EDGE_DUPLICATE;
}

static bool journal_clear_succeeded(
    egolink_sos_pending_edge_status_t status)
{
    return status == EGOLINK_SOS_PENDING_EDGE_OK ||
        status == EGOLINK_SOS_PENDING_EDGE_NOT_FOUND;
}

static void consume_pending_sequence(sos_device_runtime_internal_t *internal)
{
    if (internal->pending_sequence_consumed) {
        return;
    }
    if (internal->pending_edge.boot_count == internal->boot_count &&
        strcmp(internal->pending_edge.session_id, internal->session_id) == 0 &&
        internal->pending_edge.source_sequence ==
            internal->next_source_sequence) {
        if (internal->next_source_sequence ==
            EGOLINK_SOS_OUTBOX_JSON_SAFE_INTEGER_MAX) {
            internal->source_sequence_exhausted = true;
        } else {
            ++internal->next_source_sequence;
        }
    }
    internal->pending_sequence_consumed = true;
}

static egolink_sos_device_runtime_status_t run_pending_edge(
    sos_device_runtime_internal_t *internal,
    uint64_t now_ms,
    bool replayed,
    egolink_sos_device_runtime_result_t *result)
{
    const egolink_sos_pending_edge_record_t edge_record =
        internal->pending_edge;
    result->qualified_edge = true;
    result->replayed_pending_edge = replayed;
    result->source_sequence = edge_record.source_sequence;
    result->input_status = EGOLINK_SOS_INPUT_STATUS_OK;
    result->input_output.sos_edge = true;
    result->input_output.sos_edge_time_ms = edge_record.edge_time_ms;

    if (!internal->pending_edge_durable) {
        result->journal_store_attempted = true;
        result->journal_store_status =
            egolink_sos_pending_edge_journal_store(
                internal->pending_journal, &edge_record);
        internal->status.last_journal_status =
            result->journal_store_status;
        if (!journal_store_succeeded(result->journal_store_status)) {
            increment_saturated(&internal->status.journal_store_failures);
            result->pending_edge_retained = true;
            result->status = EGOLINK_SOS_DEVICE_RUNTIME_JOURNAL_FAILED;
            return result->status;
        }
        internal->pending_edge_durable = true;
    } else {
        result->journal_store_status = EGOLINK_SOS_PENDING_EDGE_DUPLICATE;
    }
    consume_pending_sequence(internal);
    result->pending_edge_durable = true;

    const egolink_sos_event_context_t event_context = {
        .boot_count = edge_record.boot_count,
        .session_id = edge_record.session_id,
        .source_sequence = edge_record.source_sequence,
        .battery_percent_available = false,
        .battery_percent = 0U,
        .base_online = false,
        .upload_available = false,
        .recovered_pending_edge = replayed,
    };
    const egolink_location_policy_snapshot_t policy_snapshot =
        conservative_policy_snapshot(edge_record.edge_time_ms);
    result->orchestration_status = egolink_sos_orchestrate_edge(
        &internal->orchestrator,
        &result->input_output,
        &event_context,
        &policy_snapshot,
        now_ms,
        internal->payload_scratch,
        sizeof(internal->payload_scratch),
        &result->orchestration);

    result->durable_manual_sos_available = persistence_succeeded(
        result->orchestration.persistence_state);
    if (result->durable_manual_sos_available) {
        result->journal_clear_attempted = true;
        result->journal_clear_status =
            egolink_sos_pending_edge_journal_clear(
                internal->pending_journal, &edge_record);
        internal->status.last_journal_status = result->journal_clear_status;
        if (journal_clear_succeeded(result->journal_clear_status)) {
            internal->pending_edge_available = false;
            internal->pending_edge_durable = false;
            internal->pending_sequence_consumed = false;
            secure_clear(&internal->pending_edge, sizeof(internal->pending_edge));
            increment_saturated(&internal->status.durable_edges);
        } else {
            increment_saturated(&internal->status.journal_clear_failures);
        }
    }

    result->sender_wake = result->orchestration.durable_ready;
    if (result->sender_wake != EGOLINK_SOS_BRANCH_SUCCEEDED) {
        increment_saturated(&internal->status.sender_wake_failures);
    }
    result->pending_edge_retained = internal->pending_edge_available;
    result->pending_edge_durable = internal->pending_edge_durable;

    const bool complete =
        result->orchestration_status == EGOLINK_SOS_ORCHESTRATION_OK &&
        result->sender_wake == EGOLINK_SOS_BRANCH_SUCCEEDED &&
        !result->pending_edge_retained;
    result->status = complete
        ? EGOLINK_SOS_DEVICE_RUNTIME_OK
        : EGOLINK_SOS_DEVICE_RUNTIME_PARTIAL_FAILURE;
    if (!complete) {
        increment_saturated(&internal->status.partial_edges);
    }
    return result->status;
}

static egolink_sos_device_runtime_status_t runtime_ready(
    sos_device_runtime_internal_t *internal)
{
    if (!valid_magic(internal)) {
        return EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED;
    }
    if (internal->busy) {
        return EGOLINK_SOS_DEVICE_RUNTIME_REENTRANT_CALL;
    }
    if (internal->lifecycle != EGOLINK_SOS_DEVICE_RUNTIME_ACTIVE) {
        return lifecycle_status(internal->lifecycle);
    }
    if (!dependencies_match(internal)) {
        return EGOLINK_SOS_DEVICE_RUNTIME_DEPENDENCY_MISMATCH;
    }
    return EGOLINK_SOS_DEVICE_RUNTIME_OK;
}

egolink_sos_device_runtime_status_t egolink_sos_device_runtime_process_sample(
    egolink_sos_device_runtime_t *runtime,
    bool raw_pressed,
    uint64_t now_ms,
    egolink_sos_device_runtime_result_t *result)
{
    initialize_process_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT;
    }
    sos_device_runtime_internal_t *internal = runtime_internal(runtime);
    result->status = runtime_ready(internal);
    if (result->status != EGOLINK_SOS_DEVICE_RUNTIME_OK) {
        if (valid_magic(internal)) {
            set_last_status(internal, result->status);
        }
        return result->status;
    }
    if (internal->pending_edge_available) {
        result->pending_edge_durable = internal->pending_edge_durable;
        result->pending_edge_retained = true;
        result->source_sequence = internal->pending_edge.source_sequence;
        result->status =
            EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED;
        set_last_status(internal, result->status);
        return result->status;
    }

    internal->busy = true;
    increment_saturated(&internal->status.sample_calls);
    result->input_status = egolink_sos_input_process(
        &internal->input, raw_pressed, now_ms, &result->input_output);
    if (result->input_status != EGOLINK_SOS_INPUT_STATUS_OK) {
        result->status = EGOLINK_SOS_DEVICE_RUNTIME_INPUT_FAILED;
        internal->busy = false;
        set_last_status(internal, result->status);
        return result->status;
    }
    if (!result->input_output.sos_edge) {
        result->status = EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE;
        internal->busy = false;
        set_last_status(internal, result->status);
        return result->status;
    }

    result->qualified_edge = true;
    increment_saturated(&internal->status.qualified_edges);
    if (internal->source_sequence_exhausted ||
        internal->next_source_sequence >
            EGOLINK_SOS_OUTBOX_JSON_SAFE_INTEGER_MAX ||
        result->input_output.sos_edge_time_ms >
            EGOLINK_SOS_OUTBOX_JSON_SAFE_INTEGER_MAX) {
        result->status = EGOLINK_SOS_DEVICE_RUNTIME_SEQUENCE_EXHAUSTED;
        increment_saturated(&internal->status.partial_edges);
        internal->busy = false;
        set_last_status(internal, result->status);
        return result->status;
    }

    (void)memset(&internal->pending_edge, 0, sizeof(internal->pending_edge));
    const size_t device_length = bounded_string_length(
        internal->orchestrator.device_id,
        sizeof(internal->pending_edge.device_id));
    const size_t session_length = bounded_string_length(
        internal->session_id, sizeof(internal->pending_edge.session_id));
    (void)memcpy(
        internal->pending_edge.device_id,
        internal->orchestrator.device_id,
        device_length + 1U);
    (void)memcpy(
        internal->pending_edge.session_id,
        internal->session_id,
        session_length + 1U);
    internal->pending_edge.boot_count = internal->boot_count;
    internal->pending_edge.source_sequence = internal->next_source_sequence;
    internal->pending_edge.edge_time_ms =
        result->input_output.sos_edge_time_ms;
    internal->pending_edge_available = true;
    internal->pending_edge_durable = false;
    internal->pending_sequence_consumed = false;

    result->status = run_pending_edge(internal, now_ms, false, result);
    internal->busy = false;
    set_last_status(internal, result->status);
    return result->status;
}

egolink_sos_device_runtime_status_t
egolink_sos_device_runtime_replay_pending(
    egolink_sos_device_runtime_t *runtime,
    uint64_t now_ms,
    egolink_sos_device_runtime_result_t *result)
{
    initialize_process_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT;
    }
    sos_device_runtime_internal_t *internal = runtime_internal(runtime);
    result->status = runtime_ready(internal);
    if (result->status != EGOLINK_SOS_DEVICE_RUNTIME_OK) {
        if (valid_magic(internal)) {
            set_last_status(internal, result->status);
        }
        return result->status;
    }
    if (!internal->pending_edge_available) {
        result->status = EGOLINK_SOS_DEVICE_RUNTIME_NO_PENDING_EDGE;
        set_last_status(internal, result->status);
        return result->status;
    }

    internal->busy = true;
    increment_saturated(&internal->status.pending_replay_attempts);
    result->status = run_pending_edge(internal, now_ms, true, result);
    internal->busy = false;
    set_last_status(internal, result->status);
    return result->status;
}

static void clear_bound_state(sos_device_runtime_internal_t *internal)
{
    secure_clear(&internal->input, sizeof(internal->input));
    secure_clear(&internal->orchestrator, sizeof(internal->orchestrator));
    secure_clear(&internal->callbacks, sizeof(internal->callbacks));
    secure_clear(&internal->pending_edge, sizeof(internal->pending_edge));
    secure_clear(internal->payload_scratch, sizeof(internal->payload_scratch));
    secure_clear(internal->session_id, sizeof(internal->session_id));
    internal->shared_outbox = NULL;
    internal->delivery_adapter = NULL;
    internal->pending_journal = NULL;
    internal->policy_core = NULL;
    internal->boot_count = UINT64_C(0);
    internal->next_source_sequence = UINT64_C(0);
    internal->source_sequence_exhausted = false;
    internal->pending_edge_available = false;
    internal->pending_edge_durable = false;
    internal->pending_sequence_consumed = false;
}

static egolink_sos_device_runtime_status_t shutdown_runtime(
    egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_shutdown_result_t *result,
    egolink_sos_device_runtime_lifecycle_t target)
{
    initialize_shutdown_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT;
    }
    sos_device_runtime_internal_t *internal = runtime_internal(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_SOS_DEVICE_RUNTIME_REENTRANT_CALL;
        return result->status;
    }
    if (internal->pending_edge_available &&
        !internal->pending_edge_durable) {
        result->durable_records_retained = true;
        result->dispatcher_attempt_untouched = true;
        result->pending_edge_journal_untouched = true;
        result->status =
            EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED;
        set_last_status(internal, result->status);
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_SOS_DEVICE_RUNTIME_CLOSED) {
        result->durable_records_retained = true;
        result->dispatcher_attempt_untouched = true;
        result->pending_edge_journal_untouched = true;
        result->status = EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS;
        return result->status;
    }
    if (target == EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED &&
        internal->lifecycle == EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED) {
        result->durable_records_retained = true;
        result->dispatcher_attempt_untouched = true;
        result->pending_edge_journal_untouched = true;
        result->status = EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS;
        return result->status;
    }

    internal->busy = true;
    result->dispatcher_attempt_untouched = true;
    result->pending_edge_journal_untouched = true;
    clear_bound_state(internal);
    internal->lifecycle = target;
    internal->busy = false;
    result->durable_records_retained = true;
    result->status = target == EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED
        ? EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS
        : EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS;
    set_last_status(internal, result->status);
    return result->status;
}

egolink_sos_device_runtime_status_t egolink_sos_device_runtime_cancel(
    egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_shutdown_result_t *result)
{
    return shutdown_runtime(
        runtime,
        result,
        EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED);
}

egolink_sos_device_runtime_status_t egolink_sos_device_runtime_close(
    egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_shutdown_result_t *result)
{
    return shutdown_runtime(
        runtime,
        result,
        EGOLINK_SOS_DEVICE_RUNTIME_CLOSED);
}

egolink_sos_device_runtime_status_t
egolink_sos_device_runtime_current_status(
    const egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_snapshot_t *snapshot)
{
    if (snapshot != NULL) {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        snapshot->lifecycle = EGOLINK_SOS_DEVICE_RUNTIME_NEVER_INITIALIZED;
        snapshot->last_status = EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED;
    }
    if (runtime == NULL || snapshot == NULL) {
        return EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT;
    }
    const sos_device_runtime_internal_t *internal =
        runtime_internal_const(runtime);
    if (!valid_magic(internal)) {
        return EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED;
    }
    *snapshot = internal->status;
    snapshot->lifecycle = internal->lifecycle;
    snapshot->enabled =
        internal->lifecycle == EGOLINK_SOS_DEVICE_RUNTIME_ACTIVE;
    snapshot->busy = internal->busy;
    snapshot->dependencies_bound = dependencies_match(internal);
    snapshot->dispatcher_attempt_observed_active =
        internal->delivery_adapter != NULL &&
        internal->delivery_adapter->attempt_active;
    snapshot->source_sequence_exhausted =
        internal->source_sequence_exhausted;
    snapshot->pending_edge_available = internal->pending_edge_available;
    snapshot->pending_edge_durable = internal->pending_edge_durable;
    snapshot->next_source_sequence = internal->next_source_sequence;
    if (internal->busy) {
        return EGOLINK_SOS_DEVICE_RUNTIME_REENTRANT_CALL;
    }
    if (internal->lifecycle == EGOLINK_SOS_DEVICE_RUNTIME_ACTIVE &&
        internal->pending_edge_available) {
        return EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED;
    }
    return lifecycle_status(internal->lifecycle);
}

const char *egolink_sos_device_runtime_status_name(
    egolink_sos_device_runtime_status_t status)
{
    switch (status) {
    case EGOLINK_SOS_DEVICE_RUNTIME_OK: return "ok";
    case EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE: return "no_edge";
    case EGOLINK_SOS_DEVICE_RUNTIME_PARTIAL_FAILURE:
        return "partial_failure";
    case EGOLINK_SOS_DEVICE_RUNTIME_DISABLED_STATUS: return "disabled";
    case EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS: return "cancelled";
    case EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS: return "closed";
    case EGOLINK_SOS_DEVICE_RUNTIME_INPUT_FAILED: return "input_failed";
    case EGOLINK_SOS_DEVICE_RUNTIME_JOURNAL_FAILED:
        return "journal_failed";
    case EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED:
        return "pending_replay_required";
    case EGOLINK_SOS_DEVICE_RUNTIME_NO_PENDING_EDGE:
        return "no_pending_edge";
    case EGOLINK_SOS_DEVICE_RUNTIME_SEQUENCE_EXHAUSTED:
        return "sequence_exhausted";
    case EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_SOS_DEVICE_RUNTIME_INVALID_CONFIG: return "invalid_config";
    case EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED:
        return "not_initialized";
    case EGOLINK_SOS_DEVICE_RUNTIME_ALREADY_INITIALIZED:
        return "already_initialized";
    case EGOLINK_SOS_DEVICE_RUNTIME_DEPENDENCY_MISMATCH:
        return "dependency_mismatch";
    case EGOLINK_SOS_DEVICE_RUNTIME_REENTRANT_CALL:
        return "reentrant_call";
    default: return "unknown";
    }
}

const char *egolink_sos_device_runtime_lifecycle_name(
    egolink_sos_device_runtime_lifecycle_t lifecycle)
{
    switch (lifecycle) {
    case EGOLINK_SOS_DEVICE_RUNTIME_NEVER_INITIALIZED:
        return "never_initialized";
    case EGOLINK_SOS_DEVICE_RUNTIME_DISABLED: return "disabled";
    case EGOLINK_SOS_DEVICE_RUNTIME_ACTIVE: return "active";
    case EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED: return "cancelled";
    case EGOLINK_SOS_DEVICE_RUNTIME_CLOSED: return "closed";
    default: return "unknown";
    }
}

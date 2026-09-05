#include "sos_delivery_composition.h"

#include <string.h>

#define SOS_DELIVERY_COMPOSITION_MAGIC UINT32_C(0x53444349)

typedef struct {
    uint32_t magic;
    egolink_sos_delivery_composition_lifecycle_t lifecycle;
    bool busy;
    bool sos_adapter_bound;
    bool pending_journal_bound;
    bool dispatcher_initialized;
    bool delivery_runtime_initialized;
    bool sos_runtime_initialized;
    bool rollback_cleanup_pending;
    bool wake_intent_pending;
    egolink_outbox_t *shared_outbox;
    egolink_location_outbox_adapter_t *location_adapter;
    egolink_location_policy_core_t *policy_core;
    const egolink_sos_pending_edge_storage_t *pending_storage;
    char device_id[EGOLINK_OUTBOX_ID_CAPACITY];
    egolink_sos_outbox_adapter_t sos_adapter;
    egolink_sos_pending_edge_journal_t pending_journal;
    egolink_p0_outbox_dispatcher_t dispatcher;
    egolink_p0_delivery_runtime_t delivery_runtime;
    egolink_sos_device_runtime_t sos_runtime;
    uint64_t wake_intents_observed;
    uint64_t wake_intents_consumed;
    uint64_t sample_calls;
    uint64_t replay_calls;
    uint64_t drive_calls;
    uint64_t prepare_calls;
    uint64_t settle_prepared_calls;
    uint64_t durable_sos_preemption_signals;
    egolink_p0_delivery_sos_preempt_status_t last_sos_preemption_status;
    uint64_t recovery_results;
    egolink_sos_delivery_composition_status_t last_status;
} sos_delivery_composition_internal_t;

_Static_assert(
    sizeof(sos_delivery_composition_internal_t) <=
        EGOLINK_SOS_DELIVERY_COMPOSITION_CONTEXT_BYTES,
    "SOS delivery composition context is too small");

static sos_delivery_composition_internal_t *internal_of(
    egolink_sos_delivery_composition_t *composition)
{
    return (sos_delivery_composition_internal_t *)(void *)
        composition->opaque;
}

static const sos_delivery_composition_internal_t *internal_of_const(
    const egolink_sos_delivery_composition_t *composition)
{
    return (const sos_delivery_composition_internal_t *)(const void *)
        composition->opaque;
}

static void secure_clear(void *data, size_t length)
{
    volatile uint8_t *cursor = (volatile uint8_t *)data;
    while (cursor != NULL && length > 0U) {
        *cursor = UINT8_C(0);
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
    const size_t length = bounded_length(
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

static bool exact_identifier(const char *left, const char *right)
{
    const size_t left_length = bounded_length(
        left, EGOLINK_OUTBOX_ID_CAPACITY);
    const size_t right_length = bounded_length(
        right, EGOLINK_OUTBOX_ID_CAPACITY);
    return left_length < EGOLINK_OUTBOX_ID_CAPACITY &&
        left_length == right_length &&
        memcmp(left, right, left_length + 1U) == 0;
}

static bool valid_magic(
    const sos_delivery_composition_internal_t *internal)
{
    return internal != NULL &&
        internal->magic == SOS_DELIVERY_COMPOSITION_MAGIC;
}

static bool caller_dependencies_match(
    const sos_delivery_composition_internal_t *internal)
{
    return internal->shared_outbox != NULL &&
        internal->location_adapter != NULL &&
        internal->location_adapter->initialized &&
        internal->location_adapter->outbox == internal->shared_outbox &&
        safe_identifier(internal->location_adapter->device_id) &&
        safe_identifier(internal->device_id) &&
        exact_identifier(
            internal->location_adapter->device_id, internal->device_id) &&
        internal->policy_core != NULL && internal->policy_core->initialized &&
        internal->pending_storage != NULL &&
        internal->pending_storage->load_record != NULL &&
        internal->pending_storage->store_record != NULL &&
        internal->pending_storage->clear_record != NULL;
}

static void set_last_status(
    sos_delivery_composition_internal_t *internal,
    egolink_sos_delivery_composition_status_t status)
{
    internal->last_status = status;
    if (status == EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED ||
        status ==
            EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED) {
        increment_saturated(&internal->recovery_results);
    }
}

static void initialize_event_result(
    egolink_sos_delivery_composition_event_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->status =
            EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
        result->runtime_status =
            EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED;
    }
}

static void initialize_drive_result(
    egolink_sos_delivery_composition_drive_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->status =
            EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
        result->delivery_status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
    }
}

static void initialize_shutdown_result(
    egolink_sos_delivery_composition_shutdown_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->status =
            EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
        result->sos_runtime_status =
            EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED;
        result->delivery_status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
    }
}

static egolink_sos_delivery_composition_status_t lifecycle_status(
    egolink_sos_delivery_composition_lifecycle_t lifecycle)
{
    switch (lifecycle) {
    case EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS;
    case EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS;
    case EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_REQUIRED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
    case EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS;
    case EGOLINK_SOS_DELIVERY_COMPOSITION_ACTIVE:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_OK;
    case EGOLINK_SOS_DELIVERY_COMPOSITION_NEVER_INITIALIZED:
    default:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED;
    }
}

static egolink_sos_delivery_composition_status_t event_status(
    egolink_sos_device_runtime_status_t status)
{
    switch (status) {
    case EGOLINK_SOS_DEVICE_RUNTIME_OK:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_OK;
    case EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_NO_EDGE;
    case EGOLINK_SOS_DEVICE_RUNTIME_PARTIAL_FAILURE:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_PARTIAL_FAILURE;
    case EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED:
    case EGOLINK_SOS_DEVICE_RUNTIME_JOURNAL_FAILED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_PENDING_REPLAY_REQUIRED;
    case EGOLINK_SOS_DEVICE_RUNTIME_NO_PENDING_EDGE:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_NO_PENDING_EDGE;
    case EGOLINK_SOS_DEVICE_RUNTIME_DISABLED_STATUS:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS;
    case EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS;
    case EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS;
    case EGOLINK_SOS_DEVICE_RUNTIME_DEPENDENCY_MISMATCH:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_DEPENDENCY_MISMATCH;
    case EGOLINK_SOS_DEVICE_RUNTIME_REENTRANT_CALL:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL;
    case EGOLINK_SOS_DEVICE_RUNTIME_INPUT_FAILED:
    case EGOLINK_SOS_DEVICE_RUNTIME_SEQUENCE_EXHAUSTED:
    case EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT:
    case EGOLINK_SOS_DEVICE_RUNTIME_INVALID_CONFIG:
    case EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED:
    case EGOLINK_SOS_DEVICE_RUNTIME_ALREADY_INITIALIZED:
    default:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_PARTIAL_FAILURE;
    }
}

static egolink_sos_delivery_composition_status_t drive_status(
    egolink_p0_delivery_runtime_status_t status)
{
    switch (status) {
    case EGOLINK_P0_DELIVERY_OK:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_OK;
    case EGOLINK_P0_DELIVERY_NO_DUE_RECORD:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_NO_DUE_RECORD;
    case EGOLINK_P0_DELIVERY_ACK_DELETED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_DELETED;
    case EGOLINK_P0_DELIVERY_ACK_ALREADY_APPLIED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_ALREADY_APPLIED;
    case EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED:
    case EGOLINK_P0_DELIVERY_INVALID_EVENT_RETAINED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_DELIVERY_RETAINED;
    case EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED:
    case EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED:
    case EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
    case EGOLINK_P0_DELIVERY_DISABLED_STATUS:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS;
    case EGOLINK_P0_DELIVERY_CANCELLED_STATUS:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS;
    case EGOLINK_P0_DELIVERY_CLOSED_STATUS:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS;
    case EGOLINK_P0_DELIVERY_REENTRANT_CALL:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL;
    case EGOLINK_P0_DELIVERY_PREPARED:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_PREPARED;
    case EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_TRANSPORT_RESULT_READY;
    case EGOLINK_P0_DELIVERY_INVALID_ARGUMENT:
    case EGOLINK_P0_DELIVERY_INVALID_CONFIG:
    case EGOLINK_P0_DELIVERY_NOT_INITIALIZED:
    case EGOLINK_P0_DELIVERY_ALREADY_INITIALIZED:
    default:
        return EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
    }
}

static bool record_sender_wake(
    void *context,
    const egolink_sos_sender_wake_request_t *request)
{
    sos_delivery_composition_internal_t *internal =
        (sos_delivery_composition_internal_t *)context;
    if (!valid_magic(internal) || request == NULL ||
        request->identity == NULL ||
        internal->lifecycle != EGOLINK_SOS_DELIVERY_COMPOSITION_ACTIVE) {
        return false;
    }
    internal->wake_intent_pending = true;
    increment_saturated(&internal->wake_intents_observed);
    if (request->durable_manual_sos_available) {
        internal->last_sos_preemption_status =
            egolink_p0_delivery_runtime_signal_durable_sos(
                &internal->delivery_runtime);
        increment_saturated(&internal->durable_sos_preemption_signals);
    }
    return true;
}

void egolink_sos_delivery_composition_default_config(
    egolink_sos_delivery_composition_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->enabled = false;
        config->input.debounce_ms = EGOLINK_SOS_INPUT_DEFAULT_DEBOUNCE_MS;
        config->input.long_press_ms =
            EGOLINK_SOS_INPUT_DEFAULT_LONG_PRESS_MS;
        config->first_source_sequence = UINT64_C(1);
        config->max_post_duration_ms =
            EGOLINK_P0_DELIVERY_RUNTIME_DEFAULT_MAX_POST_DURATION_MS;
    }
}

static bool validate_enabled_config(
    const egolink_sos_delivery_composition_config_t *config,
    egolink_outbox_t *shared_outbox,
    const egolink_location_outbox_adapter_t *location_adapter,
    const egolink_location_policy_core_t *policy_core,
    const egolink_sos_pending_edge_storage_t *pending_storage)
{
    return safe_identifier(config->device_id) &&
        safe_identifier(config->session_id) && shared_outbox != NULL &&
        location_adapter != NULL && location_adapter->initialized &&
        location_adapter->outbox == shared_outbox &&
        safe_identifier(location_adapter->device_id) &&
        exact_identifier(config->device_id, location_adapter->device_id) &&
        policy_core != NULL && policy_core->initialized &&
        pending_storage != NULL && pending_storage->load_record != NULL &&
        pending_storage->store_record != NULL &&
        pending_storage->clear_record != NULL && config->http_post != NULL &&
        config->max_post_duration_ms > UINT32_C(0) &&
        config->max_post_duration_ms <=
            EGOLINK_P0_DELIVERY_RUNTIME_MAX_POST_DURATION_MS;
}

static bool close_owned_sos_for_rollback(
    sos_delivery_composition_internal_t *internal)
{
    if (!internal->sos_runtime_initialized) {
        return true;
    }
    egolink_sos_device_runtime_shutdown_result_t result;
    const egolink_sos_device_runtime_status_t status =
        egolink_sos_device_runtime_close(&internal->sos_runtime, &result);
    secure_clear(&result, sizeof(result));
    if (status != EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS) {
        return false;
    }
    internal->sos_runtime_initialized = false;
    return true;
}

static bool close_owned_delivery_for_rollback(
    sos_delivery_composition_internal_t *internal,
    uint64_t now_ms)
{
    if (internal->delivery_runtime_initialized) {
        egolink_p0_delivery_runtime_snapshot_t snapshot;
        egolink_p0_delivery_runtime_status_t current =
            egolink_p0_delivery_runtime_current_status(
                &internal->delivery_runtime, &snapshot);
        if (current == EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED ||
            snapshot.phase ==
                EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED) {
            egolink_p0_delivery_runtime_result_t recovery_result;
            current = egolink_p0_delivery_runtime_retry_finish(
                &internal->delivery_runtime, now_ms, &recovery_result);
            secure_clear(&recovery_result, sizeof(recovery_result));
        } else if (
            current == EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED ||
            snapshot.phase ==
                EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED) {
            egolink_p0_delivery_runtime_result_t recovery_result;
            current = egolink_p0_delivery_runtime_retry_begin_recovery(
                &internal->delivery_runtime, now_ms, &recovery_result);
            secure_clear(&recovery_result, sizeof(recovery_result));
        }
        secure_clear(&snapshot, sizeof(snapshot));
        if (current == EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED ||
            current == EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED ||
            current == EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED ||
            current == EGOLINK_P0_DELIVERY_REENTRANT_CALL) {
            return false;
        }
        egolink_p0_delivery_runtime_result_t result;
        const egolink_p0_delivery_runtime_status_t status =
            egolink_p0_delivery_runtime_close(
                &internal->delivery_runtime, now_ms, &result);
        secure_clear(&result, sizeof(result));
        if (status != EGOLINK_P0_DELIVERY_CLOSED_STATUS) {
            return false;
        }
        internal->delivery_runtime_initialized = false;
        internal->dispatcher_initialized = false;
    } else if (internal->dispatcher_initialized) {
        egolink_p0_outbox_send_view_t view;
        egolink_p0_outbox_finish_result_t result;
        (void)memset(&view, 0, sizeof(view));
        const egolink_p0_outbox_dispatcher_status_t status =
            egolink_p0_outbox_dispatcher_close(
                &internal->dispatcher, now_ms, &view, &result);
        secure_clear(&view, sizeof(view));
        secure_clear(&result, sizeof(result));
        if (status != EGOLINK_P0_OUTBOX_CLOSED_STATUS) {
            return false;
        }
        internal->dispatcher_initialized = false;
    }
    return true;
}

static void release_memory_only_owned_bindings(
    sos_delivery_composition_internal_t *internal)
{
    if (internal->sos_adapter_bound) {
        egolink_sos_outbox_adapter_unbind(&internal->sos_adapter);
        internal->sos_adapter_bound = false;
    }
    if (internal->pending_journal_bound) {
        secure_clear(
            &internal->pending_journal, sizeof(internal->pending_journal));
        internal->pending_journal_bound = false;
    }
}

static egolink_sos_delivery_composition_status_t clean_init_failure(
    egolink_sos_delivery_composition_t *composition,
    egolink_sos_delivery_composition_status_t failure,
    uint64_t now_ms)
{
    sos_delivery_composition_internal_t *internal = internal_of(composition);
    if (!close_owned_sos_for_rollback(internal) ||
        !close_owned_delivery_for_rollback(internal, now_ms)) {
        internal->rollback_cleanup_pending = true;
        internal->lifecycle =
            EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_REQUIRED;
        set_last_status(
            internal,
            EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED);
        return internal->last_status;
    }
    release_memory_only_owned_bindings(internal);
    secure_clear(composition, sizeof(*composition));
    return failure;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_init(
    egolink_sos_delivery_composition_t *composition,
    const egolink_sos_delivery_composition_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter,
    egolink_location_policy_core_t *policy_core,
    const egolink_sos_pending_edge_storage_t *pending_storage,
    bool initial_raw_pressed,
    uint64_t now_ms)
{
    if (composition == NULL || config == NULL) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
    }
    sos_delivery_composition_internal_t *internal = internal_of(composition);
    if (valid_magic(internal)) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_ALREADY_INITIALIZED;
    }
    secure_clear(composition, sizeof(*composition));
    internal = internal_of(composition);
    internal->magic = SOS_DELIVERY_COMPOSITION_MAGIC;
    internal->lifecycle = EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED;
    internal->last_status =
        EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS;
    internal->last_sos_preemption_status =
        EGOLINK_P0_DELIVERY_SOS_PREEMPT_NO_ACTIVE_LOCATION;
    if (!config->enabled) {
        return internal->last_status;
    }
    if (!validate_enabled_config(
            config,
            shared_outbox,
            location_adapter,
            policy_core,
            pending_storage)) {
        secure_clear(composition, sizeof(*composition));
        return EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_CONFIG;
    }

    internal->shared_outbox = shared_outbox;
    internal->location_adapter = location_adapter;
    internal->policy_core = policy_core;
    internal->pending_storage = pending_storage;
    const size_t device_length = bounded_length(
        config->device_id, sizeof(internal->device_id));
    (void)memcpy(
        internal->device_id, config->device_id, device_length + 1U);

    if (egolink_sos_outbox_adapter_bind(
            &internal->sos_adapter,
            shared_outbox,
            config->device_id) != EGOLINK_OUTBOX_OK) {
        return clean_init_failure(
            composition,
            EGOLINK_SOS_DELIVERY_COMPOSITION_DEPENDENCY_MISMATCH,
            now_ms);
    }
    internal->sos_adapter_bound = true;

    if (egolink_sos_pending_edge_journal_init(
            &internal->pending_journal,
            pending_storage,
            config->device_id) != EGOLINK_SOS_PENDING_EDGE_OK) {
        return clean_init_failure(
            composition,
            EGOLINK_SOS_DELIVERY_COMPOSITION_DEPENDENCY_MISMATCH,
            now_ms);
    }
    internal->pending_journal_bound = true;

    egolink_p0_outbox_dispatcher_config_t dispatcher_config;
    egolink_p0_outbox_dispatcher_default_config(&dispatcher_config);
    dispatcher_config.enabled = true;
    const egolink_p0_outbox_dispatcher_status_t dispatcher_status =
        egolink_p0_outbox_dispatcher_init(
            &internal->dispatcher,
            &dispatcher_config,
            shared_outbox,
            location_adapter,
            &internal->sos_adapter);
    secure_clear(&dispatcher_config, sizeof(dispatcher_config));
    if (dispatcher_status != EGOLINK_P0_OUTBOX_OK) {
        return clean_init_failure(
            composition,
            EGOLINK_SOS_DELIVERY_COMPOSITION_DEPENDENCY_MISMATCH,
            now_ms);
    }
    internal->dispatcher_initialized = true;

    egolink_p0_delivery_runtime_config_t delivery_config;
    egolink_p0_delivery_runtime_default_config(&delivery_config);
    delivery_config.enabled = true;
    delivery_config.http_post = config->http_post;
    delivery_config.http_context = config->http_context;
    delivery_config.max_post_duration_ms = config->max_post_duration_ms;
    const egolink_p0_delivery_runtime_status_t delivery_status =
        egolink_p0_delivery_runtime_init(
            &internal->delivery_runtime,
            &delivery_config,
            &internal->dispatcher);
    secure_clear(&delivery_config, sizeof(delivery_config));
    if (delivery_status != EGOLINK_P0_DELIVERY_OK) {
        return clean_init_failure(
            composition,
            EGOLINK_SOS_DELIVERY_COMPOSITION_INITIALIZATION_FAILED,
            now_ms);
    }
    internal->delivery_runtime_initialized = true;

    egolink_sos_device_runtime_config_t runtime_config;
    egolink_sos_device_runtime_default_config(&runtime_config);
    runtime_config.enabled = true;
    runtime_config.input = config->input;
    runtime_config.device_id = config->device_id;
    runtime_config.boot_count = config->boot_count;
    runtime_config.session_id = config->session_id;
    runtime_config.first_source_sequence = config->first_source_sequence;
    runtime_config.callbacks.local_feedback = config->local_feedback;
    runtime_config.callbacks.local_feedback_context =
        config->local_feedback_context;
    runtime_config.callbacks.request_urgent_location =
        config->request_urgent_location;
    runtime_config.callbacks.location_context = config->location_context;
    runtime_config.callbacks.request_call = config->request_call;
    runtime_config.callbacks.call_context = config->call_context;
    runtime_config.callbacks.wake_sender = record_sender_wake;
    runtime_config.callbacks.sender_context = internal;
    const egolink_sos_device_runtime_status_t runtime_status =
        egolink_sos_device_runtime_init(
            &internal->sos_runtime,
            &runtime_config,
            shared_outbox,
            &internal->sos_adapter,
            &internal->pending_journal,
            policy_core,
            initial_raw_pressed,
            now_ms);
    secure_clear(&runtime_config, sizeof(runtime_config));
    if (runtime_status != EGOLINK_SOS_DEVICE_RUNTIME_OK &&
        runtime_status !=
            EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED) {
        egolink_sos_device_runtime_snapshot_t runtime_snapshot;
        const egolink_sos_device_runtime_status_t probe_status =
            egolink_sos_device_runtime_current_status(
                &internal->sos_runtime, &runtime_snapshot);
        internal->sos_runtime_initialized =
            probe_status != EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED &&
            probe_status != EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT &&
            runtime_snapshot.lifecycle !=
                EGOLINK_SOS_DEVICE_RUNTIME_NEVER_INITIALIZED;
        secure_clear(&runtime_snapshot, sizeof(runtime_snapshot));
        return clean_init_failure(
            composition,
            EGOLINK_SOS_DELIVERY_COMPOSITION_INITIALIZATION_FAILED,
            now_ms);
    }
    internal->sos_runtime_initialized = true;
    internal->lifecycle = EGOLINK_SOS_DELIVERY_COMPOSITION_ACTIVE;
    const egolink_sos_delivery_composition_status_t status =
        runtime_status == EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED
        ? EGOLINK_SOS_DELIVERY_COMPOSITION_PENDING_REPLAY_REQUIRED
        : EGOLINK_SOS_DELIVERY_COMPOSITION_OK;
    set_last_status(internal, status);
    return status;
}

static egolink_sos_delivery_composition_status_t event_ready(
    const sos_delivery_composition_internal_t *internal)
{
    if (!valid_magic(internal)) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED;
    }
    if (internal->busy) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL;
    }
    if (internal->rollback_cleanup_pending) {
        return
            EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED;
    }
    if (internal->lifecycle != EGOLINK_SOS_DELIVERY_COMPOSITION_ACTIVE) {
        return lifecycle_status(internal->lifecycle);
    }
    if (!internal->sos_runtime_initialized ||
        !caller_dependencies_match(internal)) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_DEPENDENCY_MISMATCH;
    }
    return EGOLINK_SOS_DELIVERY_COMPOSITION_OK;
}

static egolink_sos_delivery_composition_status_t run_event(
    egolink_sos_delivery_composition_t *composition,
    bool replay,
    bool raw_pressed,
    uint64_t now_ms,
    egolink_sos_delivery_composition_event_result_t *result)
{
    initialize_event_result(result);
    if (composition == NULL || result == NULL) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
    }
    sos_delivery_composition_internal_t *internal = internal_of(composition);
    result->status = event_ready(internal);
    if (result->status != EGOLINK_SOS_DELIVERY_COMPOSITION_OK) {
        if (valid_magic(internal)) {
            set_last_status(internal, result->status);
        }
        return result->status;
    }

    internal->busy = true;
    result->runtime_called = true;
    if (replay) {
        increment_saturated(&internal->replay_calls);
        result->runtime_status = egolink_sos_device_runtime_replay_pending(
            &internal->sos_runtime, now_ms, &result->runtime_result);
    } else {
        increment_saturated(&internal->sample_calls);
        result->runtime_status = egolink_sos_device_runtime_process_sample(
            &internal->sos_runtime,
            raw_pressed,
            now_ms,
            &result->runtime_result);
    }
    internal->busy = false;
    result->wake_intent_pending = internal->wake_intent_pending;
    result->wake_intents_observed = internal->wake_intents_observed;
    result->durable_sos_preemption_signalled =
        result->runtime_result.durable_manual_sos_available;
    result->durable_sos_preemption_status =
        internal->last_sos_preemption_status;
    result->external_drive_required = internal->wake_intent_pending;
    result->status = event_status(result->runtime_status);
    set_last_status(internal, result->status);
    return result->status;
}

static egolink_sos_delivery_composition_status_t delivery_ready(
    const sos_delivery_composition_internal_t *internal);

static egolink_sos_delivery_composition_status_t split_phase_owned(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    bool settling,
    egolink_sos_delivery_composition_drive_result_t *result)
{
    initialize_drive_result(result);
    if (composition == NULL || result == NULL) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
    }
    sos_delivery_composition_internal_t *internal = internal_of(composition);
    result->status = delivery_ready(internal);
    if (result->status != EGOLINK_SOS_DELIVERY_COMPOSITION_OK) {
        return result->status;
    }
    internal->busy = true;
    result->delivery_called = true;
    if (settling) {
        result->settle_prepared_called = true;
        increment_saturated(&internal->settle_prepared_calls);
        result->delivery_status =
            egolink_p0_delivery_runtime_settle_prepared(
                &internal->delivery_runtime, now_ms, &result->delivery_result);
    } else {
        result->prepare_called = true;
        increment_saturated(&internal->prepare_calls);
        if (internal->wake_intent_pending) {
            internal->wake_intent_pending = false;
            increment_saturated(&internal->wake_intents_consumed);
            result->wake_intent_consumed = true;
        }
        result->delivery_status = egolink_p0_delivery_runtime_prepare(
            &internal->delivery_runtime, now_ms, &result->delivery_result);
    }
    internal->busy = false;
    result->status = drive_status(result->delivery_status);
    result->durable_record_may_remain =
        result->delivery_result.durable_record_retained ||
        result->status == EGOLINK_SOS_DELIVERY_COMPOSITION_DELIVERY_RETAINED ||
        result->status == EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
    set_last_status(internal, result->status);
    return result->status;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_prepare(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_drive_result_t *result)
{
    return split_phase_owned(composition, now_ms, false, result);
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_execute_prepared(
    egolink_sos_delivery_composition_t *composition,
    egolink_sos_delivery_composition_drive_result_t *result)
{
    initialize_drive_result(result);
    if (composition == NULL || result == NULL) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
    }
    sos_delivery_composition_internal_t *internal = internal_of(composition);
    if (!valid_magic(internal) || !internal->delivery_runtime_initialized) {
        result->status = EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED;
        return result->status;
    }
    /* Deliberately no composition busy/owner: only the p0 transport phase. */
    result->delivery_called = true;
    result->execute_prepared_called = true;
    result->delivery_status = egolink_p0_delivery_runtime_execute_prepared(
        &internal->delivery_runtime, &result->delivery_result);
    result->status = drive_status(result->delivery_status);
    return result->status;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_settle_prepared(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_drive_result_t *result)
{
    return split_phase_owned(composition, now_ms, true, result);
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_recover_delivery_once(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_drive_result_t *result)
{
    initialize_drive_result(result);
    if (composition == NULL || result == NULL) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
    }
    sos_delivery_composition_internal_t *internal = internal_of(composition);
    result->status = delivery_ready(internal);
    if (result->status != EGOLINK_SOS_DELIVERY_COMPOSITION_OK) {
        return result->status;
    }
    egolink_p0_delivery_runtime_snapshot_t snapshot;
    result->delivery_status = egolink_p0_delivery_runtime_current_status(
        &internal->delivery_runtime, &snapshot);
    internal->busy = true;
    result->delivery_called = true;
    result->recovery_retry_called = true;
    if (snapshot.phase == EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED) {
        result->delivery_status = egolink_p0_delivery_runtime_retry_finish(
            &internal->delivery_runtime, now_ms, &result->delivery_result);
    } else if (snapshot.phase ==
               EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED) {
        result->delivery_status =
            egolink_p0_delivery_runtime_retry_begin_recovery(
                &internal->delivery_runtime, now_ms, &result->delivery_result);
    } else {
        result->delivery_called = false;
        result->recovery_retry_called = false;
        result->delivery_status = snapshot.phase ==
                EGOLINK_P0_DELIVERY_PHASE_PREPARED
            ? EGOLINK_P0_DELIVERY_PREPARED
            : (snapshot.phase ==
                       EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY
                   ? EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY
                   : (snapshot.phase ==
                              EGOLINK_P0_DELIVERY_PHASE_EXECUTING_PREPARED
                          ? EGOLINK_P0_DELIVERY_REENTRANT_CALL
                          : EGOLINK_P0_DELIVERY_INVALID_ARGUMENT));
    }
    internal->busy = false;
    secure_clear(&snapshot, sizeof(snapshot));
    result->status = drive_status(result->delivery_status);
    result->durable_record_may_remain =
        result->delivery_result.durable_record_retained ||
        result->status == EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
    set_last_status(internal, result->status);
    return result->status;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_process_sample(
    egolink_sos_delivery_composition_t *composition,
    bool raw_pressed,
    uint64_t now_ms,
    egolink_sos_delivery_composition_event_result_t *result)
{
    return run_event(
        composition, false, raw_pressed, now_ms, result);
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_replay_pending(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_event_result_t *result)
{
    return run_event(composition, true, false, now_ms, result);
}

static egolink_sos_delivery_composition_status_t delivery_ready(
    const sos_delivery_composition_internal_t *internal)
{
    if (!valid_magic(internal)) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED;
    }
    if (internal->busy) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL;
    }
    if (internal->rollback_cleanup_pending) {
        return
            EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED;
    }
    if (internal->lifecycle == EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED ||
        internal->lifecycle == EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED ||
        internal->lifecycle == EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED) {
        return lifecycle_status(internal->lifecycle);
    }
    if (!internal->delivery_runtime_initialized ||
        !internal->dispatcher_initialized ||
        !internal->sos_adapter_bound ||
        !caller_dependencies_match(internal)) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_DEPENDENCY_MISMATCH;
    }
    return EGOLINK_SOS_DELIVERY_COMPOSITION_OK;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_drive_once(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_drive_result_t *result)
{
    initialize_drive_result(result);
    if (composition == NULL || result == NULL) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
    }
    sos_delivery_composition_internal_t *internal = internal_of(composition);
    result->status = delivery_ready(internal);
    if (result->status != EGOLINK_SOS_DELIVERY_COMPOSITION_OK) {
        if (valid_magic(internal)) {
            set_last_status(internal, result->status);
        }
        return result->status;
    }

    egolink_p0_delivery_runtime_snapshot_t delivery_snapshot;
    const egolink_p0_delivery_runtime_status_t current =
        egolink_p0_delivery_runtime_current_status(
            &internal->delivery_runtime, &delivery_snapshot);
    if (current == EGOLINK_P0_DELIVERY_REENTRANT_CALL) {
        result->status =
            EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL;
        set_last_status(internal, result->status);
        return result->status;
    }
    if (current == EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED ||
        delivery_snapshot.phase ==
            EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED) {
        result->delivery_status = current;
        result->durable_record_may_remain = true;
        result->status =
            EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
        secure_clear(&delivery_snapshot, sizeof(delivery_snapshot));
        set_last_status(internal, result->status);
        return result->status;
    }
    if (internal->lifecycle ==
            EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_REQUIRED &&
        delivery_snapshot.phase == EGOLINK_P0_DELIVERY_PHASE_IDLE) {
        result->delivery_status = current;
        result->durable_record_may_remain = true;
        result->status =
            EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
        secure_clear(&delivery_snapshot, sizeof(delivery_snapshot));
        set_last_status(internal, result->status);
        return result->status;
    }

    internal->busy = true;
    increment_saturated(&internal->drive_calls);
    result->delivery_called = true;
    if (internal->wake_intent_pending) {
        internal->wake_intent_pending = false;
        increment_saturated(&internal->wake_intents_consumed);
        result->wake_intent_consumed = true;
    }
    if (delivery_snapshot.phase ==
        EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED) {
        result->recovery_retry_called = true;
        result->delivery_status = egolink_p0_delivery_runtime_retry_finish(
            &internal->delivery_runtime,
            now_ms,
            &result->delivery_result);
    } else if (delivery_snapshot.phase ==
               EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED) {
        result->recovery_retry_called = true;
        result->delivery_status =
            egolink_p0_delivery_runtime_retry_begin_recovery(
                &internal->delivery_runtime,
                now_ms,
                &result->delivery_result);
    } else {
        result->delivery_status = egolink_p0_delivery_runtime_drive_once(
            &internal->delivery_runtime,
            now_ms,
            &result->delivery_result);
    }
    internal->busy = false;
    secure_clear(&delivery_snapshot, sizeof(delivery_snapshot));
    result->status = drive_status(result->delivery_status);
    result->durable_record_may_remain =
        result->delivery_result.durable_record_retained ||
        result->status ==
            EGOLINK_SOS_DELIVERY_COMPOSITION_DELIVERY_RETAINED ||
        result->status ==
            EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
    set_last_status(internal, result->status);
    return result->status;
}

static bool volatile_pending_edge(
    sos_delivery_composition_internal_t *internal)
{
    if (!internal->sos_runtime_initialized) {
        return false;
    }
    egolink_sos_device_runtime_snapshot_t snapshot;
    const egolink_sos_device_runtime_status_t status =
        egolink_sos_device_runtime_current_status(
            &internal->sos_runtime, &snapshot);
    const bool volatile_pending =
        (status == EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED ||
         status == EGOLINK_SOS_DEVICE_RUNTIME_OK) &&
        snapshot.pending_edge_available && !snapshot.pending_edge_durable;
    secure_clear(&snapshot, sizeof(snapshot));
    return volatile_pending;
}

static egolink_sos_delivery_composition_status_t delivery_shutdown_blocker(
    sos_delivery_composition_internal_t *internal)
{
    if (!internal->delivery_runtime_initialized) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_OK;
    }
    egolink_p0_delivery_runtime_snapshot_t snapshot;
    const egolink_p0_delivery_runtime_status_t status =
        egolink_p0_delivery_runtime_current_status(
            &internal->delivery_runtime, &snapshot);
    egolink_sos_delivery_composition_status_t blocker =
        EGOLINK_SOS_DELIVERY_COMPOSITION_OK;
    if (snapshot.phase == EGOLINK_P0_DELIVERY_PHASE_EXECUTING_PREPARED ||
        status == EGOLINK_P0_DELIVERY_REENTRANT_CALL) {
        blocker = EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL;
    } else if (snapshot.phase ==
                   EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY ||
               status == EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY) {
        blocker =
            EGOLINK_SOS_DELIVERY_COMPOSITION_TRANSPORT_RESULT_READY;
    } else if (snapshot.phase != EGOLINK_P0_DELIVERY_PHASE_IDLE &&
               snapshot.phase != EGOLINK_P0_DELIVERY_PHASE_PREPARED) {
        blocker = EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
    }
    secure_clear(&snapshot, sizeof(snapshot));
    return blocker;
}

static egolink_sos_delivery_composition_status_t shutdown_ready(
    const sos_delivery_composition_internal_t *internal)
{
    if (!valid_magic(internal)) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED;
    }
    if (internal->busy) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL;
    }
    if (internal->lifecycle == EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS;
    }
    if (internal->lifecycle == EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS;
    }
    return EGOLINK_SOS_DELIVERY_COMPOSITION_OK;
}

static egolink_sos_delivery_composition_status_t
retry_init_rollback_cleanup(
    sos_delivery_composition_internal_t *internal,
    uint64_t now_ms,
    bool closing,
    egolink_sos_delivery_composition_shutdown_result_t *result)
{
    const bool adapter_was_bound = internal->sos_adapter_bound;
    const bool sos_runtime_was_initialized =
        internal->sos_runtime_initialized;
    const bool delivery_was_initialized =
        internal->delivery_runtime_initialized;
    const bool dispatcher_was_initialized = internal->dispatcher_initialized;

    result->rollback_cleanup_attempted = true;
    result->sos_runtime_shutdown_called = sos_runtime_was_initialized;
    result->delivery_shutdown_called = delivery_was_initialized;
    result->owned_dispatcher_cleanup_attempted =
        dispatcher_was_initialized;
    internal->busy = true;
    if (!close_owned_sos_for_rollback(internal) ||
        !close_owned_delivery_for_rollback(internal, now_ms)) {
        internal->busy = false;
        internal->lifecycle =
            EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_REQUIRED;
        result->caller_dependencies_not_deinitialized = true;
        result->outbox_records_retained = true;
        result->pending_journal_untouched = true;
        result->status =
            EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED;
        set_last_status(internal, result->status);
        return result->status;
    }

    release_memory_only_owned_bindings(internal);
    internal->shared_outbox = NULL;
    internal->location_adapter = NULL;
    internal->policy_core = NULL;
    internal->pending_storage = NULL;
    secure_clear(internal->device_id, sizeof(internal->device_id));
    internal->wake_intent_pending = false;
    internal->rollback_cleanup_pending = false;
    internal->busy = false;
    internal->lifecycle = closing
        ? EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED
        : EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED;
    result->sos_adapter_unbound = adapter_was_bound;
    result->caller_dependencies_not_deinitialized = true;
    result->outbox_records_retained = true;
    result->pending_journal_untouched = true;
    result->status = closing
        ? EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS
        : EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS;
    set_last_status(internal, result->status);
    return result->status;
}

static egolink_sos_delivery_composition_status_t shutdown_composition(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    bool closing,
    egolink_sos_delivery_composition_shutdown_result_t *result)
{
    initialize_shutdown_result(result);
    if (composition == NULL || result == NULL) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
    }
    sos_delivery_composition_internal_t *internal = internal_of(composition);
    result->status = shutdown_ready(internal);
    if (result->status == EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS) {
        result->caller_dependencies_not_deinitialized = true;
        result->outbox_records_retained = true;
        result->pending_journal_untouched = true;
        return result->status;
    }
    if (result->status == EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS) {
        internal->lifecycle = EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED;
        result->caller_dependencies_not_deinitialized = true;
        result->outbox_records_retained = true;
        result->pending_journal_untouched = true;
        result->status = EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS;
        set_last_status(internal, result->status);
        return result->status;
    }
    if (result->status != EGOLINK_SOS_DELIVERY_COMPOSITION_OK) {
        if (valid_magic(internal)) {
            set_last_status(internal, result->status);
        }
        return result->status;
    }
    if (internal->rollback_cleanup_pending) {
        return retry_init_rollback_cleanup(
            internal, now_ms, closing, result);
    }
    result->caller_dependencies_not_deinitialized = true;
    result->outbox_records_retained = true;
    result->pending_journal_untouched = true;

    if (volatile_pending_edge(internal)) {
        result->status =
            EGOLINK_SOS_DELIVERY_COMPOSITION_PENDING_REPLAY_REQUIRED;
        set_last_status(internal, result->status);
        return result->status;
    }
    const egolink_sos_delivery_composition_status_t delivery_blocker =
        delivery_shutdown_blocker(internal);
    if (delivery_blocker != EGOLINK_SOS_DELIVERY_COMPOSITION_OK) {
        if (delivery_blocker ==
            EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED) {
            internal->lifecycle =
                EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_REQUIRED;
        }
        result->status = delivery_blocker;
        set_last_status(internal, result->status);
        return result->status;
    }

    internal->busy = true;
    if (internal->sos_runtime_initialized) {
        result->sos_runtime_shutdown_called = true;
        result->sos_runtime_status = closing
            ? egolink_sos_device_runtime_close(
                  &internal->sos_runtime, &result->sos_runtime_result)
            : egolink_sos_device_runtime_cancel(
                  &internal->sos_runtime, &result->sos_runtime_result);
        const bool runtime_settled = closing
            ? result->sos_runtime_status ==
                  EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS
            : result->sos_runtime_status ==
                  EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS;
        if (!runtime_settled) {
            internal->busy = false;
            result->status = event_status(result->sos_runtime_status);
            set_last_status(internal, result->status);
            return result->status;
        }
        if (closing) {
            internal->sos_runtime_initialized = false;
        }
    }

    if (internal->delivery_runtime_initialized) {
        result->delivery_shutdown_called = true;
        result->owned_dispatcher_cleanup_attempted = true;
        result->delivery_status = closing
            ? egolink_p0_delivery_runtime_close(
                  &internal->delivery_runtime,
                  now_ms,
                  &result->delivery_result)
            : egolink_p0_delivery_runtime_cancel(
                  &internal->delivery_runtime,
                  now_ms,
                  &result->delivery_result);
        const bool delivery_settled = closing
            ? result->delivery_status == EGOLINK_P0_DELIVERY_CLOSED_STATUS
            : result->delivery_status ==
                  EGOLINK_P0_DELIVERY_CANCELLED_STATUS;
        if (!delivery_settled) {
            internal->lifecycle =
                EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_REQUIRED;
            internal->busy = false;
            result->status =
                EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED;
            set_last_status(internal, result->status);
            return result->status;
        }
        if (closing) {
            internal->delivery_runtime_initialized = false;
            internal->dispatcher_initialized = false;
        }
    }

    if (closing) {
        release_memory_only_owned_bindings(internal);
        result->sos_adapter_unbound = true;
        internal->shared_outbox = NULL;
        internal->location_adapter = NULL;
        internal->policy_core = NULL;
        internal->pending_storage = NULL;
        secure_clear(internal->device_id, sizeof(internal->device_id));
        internal->wake_intent_pending = false;
        internal->lifecycle = EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED;
        result->status = EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS;
    } else {
        internal->lifecycle = EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED;
        result->status = EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS;
    }
    internal->busy = false;
    set_last_status(internal, result->status);
    return result->status;
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_cancel(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_shutdown_result_t *result)
{
    return shutdown_composition(
        composition, now_ms, false, result);
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_close(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_shutdown_result_t *result)
{
    return shutdown_composition(composition, now_ms, true, result);
}

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_current_status(
    const egolink_sos_delivery_composition_t *composition,
    egolink_sos_delivery_composition_snapshot_t *snapshot)
{
    if (snapshot != NULL) {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        snapshot->lifecycle =
            EGOLINK_SOS_DELIVERY_COMPOSITION_NEVER_INITIALIZED;
        snapshot->last_status =
            EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED;
        snapshot->sos_runtime_lifecycle =
            EGOLINK_SOS_DEVICE_RUNTIME_NEVER_INITIALIZED;
        snapshot->sos_runtime_status =
            EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED;
        snapshot->delivery_lifecycle =
            EGOLINK_P0_DELIVERY_RUNTIME_NEVER_INITIALIZED;
        snapshot->delivery_phase = EGOLINK_P0_DELIVERY_PHASE_IDLE;
        snapshot->delivery_status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
    }
    if (composition == NULL || snapshot == NULL) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT;
    }
    const sos_delivery_composition_internal_t *internal =
        internal_of_const(composition);
    if (!valid_magic(internal)) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED;
    }
    snapshot->lifecycle = internal->lifecycle;
    snapshot->last_status = internal->last_status;
    snapshot->enabled =
        internal->lifecycle == EGOLINK_SOS_DELIVERY_COMPOSITION_ACTIVE;
    snapshot->busy = internal->busy;
    snapshot->caller_dependencies_bound =
        caller_dependencies_match(internal);
    snapshot->sos_adapter_owned_and_bound =
        internal->sos_adapter_bound && internal->sos_adapter.initialized &&
        internal->sos_adapter.outbox == internal->shared_outbox &&
        exact_identifier(internal->sos_adapter.device_id, internal->device_id);
    snapshot->pending_journal_owned_and_bound =
        internal->pending_journal_bound &&
        egolink_sos_pending_edge_journal_is_initialized(
            &internal->pending_journal) &&
        egolink_sos_pending_edge_journal_matches_device(
            &internal->pending_journal, internal->device_id);
    snapshot->dispatcher_owned_and_initialized =
        internal->dispatcher_initialized;
    snapshot->delivery_runtime_owned_and_initialized =
        internal->delivery_runtime_initialized;
    snapshot->sos_runtime_owned_and_initialized =
        internal->sos_runtime_initialized;
    snapshot->wake_intent_pending = internal->wake_intent_pending;
    snapshot->wake_intents_observed = internal->wake_intents_observed;
    snapshot->wake_intents_consumed = internal->wake_intents_consumed;
    snapshot->sample_calls = internal->sample_calls;
    snapshot->replay_calls = internal->replay_calls;
    snapshot->drive_calls = internal->drive_calls;
    snapshot->prepare_calls = internal->prepare_calls;
    snapshot->settle_prepared_calls = internal->settle_prepared_calls;
    snapshot->durable_sos_preemption_signals =
        internal->durable_sos_preemption_signals;
    snapshot->last_sos_preemption_status =
        internal->last_sos_preemption_status;
    snapshot->recovery_results = internal->recovery_results;

    if (internal->sos_runtime_initialized) {
        egolink_sos_device_runtime_snapshot_t runtime_snapshot;
        snapshot->sos_runtime_status =
            egolink_sos_device_runtime_current_status(
                &internal->sos_runtime, &runtime_snapshot);
        snapshot->sos_runtime_lifecycle = runtime_snapshot.lifecycle;
        snapshot->pending_edge_available =
            runtime_snapshot.pending_edge_available;
        snapshot->pending_edge_durable =
            runtime_snapshot.pending_edge_durable;
        secure_clear(&runtime_snapshot, sizeof(runtime_snapshot));
    }
    if (internal->delivery_runtime_initialized) {
        egolink_p0_delivery_runtime_snapshot_t delivery_snapshot;
        snapshot->delivery_status =
            egolink_p0_delivery_runtime_current_status(
                &internal->delivery_runtime, &delivery_snapshot);
        snapshot->delivery_lifecycle = delivery_snapshot.lifecycle;
        snapshot->delivery_phase = delivery_snapshot.phase;
        secure_clear(&delivery_snapshot, sizeof(delivery_snapshot));
    }
    if (internal->busy) {
        return EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL;
    }
    if (internal->rollback_cleanup_pending) {
        return
            EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED;
    }
    return lifecycle_status(internal->lifecycle);
}

const char *egolink_sos_delivery_composition_status_name(
    egolink_sos_delivery_composition_status_t status)
{
    switch (status) {
    case EGOLINK_SOS_DELIVERY_COMPOSITION_OK: return "ok";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_NO_EDGE: return "no_edge";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_PARTIAL_FAILURE:
        return "partial_failure";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_PENDING_REPLAY_REQUIRED:
        return "pending_replay_required";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_NO_PENDING_EDGE:
        return "no_pending_edge";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_NO_DUE_RECORD:
        return "no_due_record";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_DELETED:
        return "ack_deleted";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_ALREADY_APPLIED:
        return "ack_already_applied";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_DELIVERY_RETAINED:
        return "delivery_retained";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED:
        return "recovery_needed";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS:
        return "disabled";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS:
        return "cancelled";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS: return "closed";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_CONFIG:
        return "invalid_config";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_DEPENDENCY_MISMATCH:
        return "dependency_mismatch";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_INITIALIZATION_FAILED:
        return "initialization_failed";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED:
        return "rollback_recovery_required";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED:
        return "not_initialized";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_ALREADY_INITIALIZED:
        return "already_initialized";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL:
        return "reentrant_call";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_PREPARED: return "prepared";
    case EGOLINK_SOS_DELIVERY_COMPOSITION_TRANSPORT_RESULT_READY:
        return "transport_result_ready";
    default: return "unknown";
    }
}

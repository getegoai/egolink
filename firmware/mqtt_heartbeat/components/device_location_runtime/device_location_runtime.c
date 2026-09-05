#include "device_location_runtime.h"

#include <math.h>
#include <string.h>

#define DEVICE_LOCATION_RUNTIME_MAGIC UINT32_C(0x45474f4c)

typedef struct {
    uint32_t magic;
    egolink_device_location_runtime_lifecycle_t lifecycle;
    bool busy;
    egolink_outbox_t *shared_outbox;
    egolink_location_outbox_adapter_t *location_adapter;
    egolink_device_location_runtime_callbacks_t callbacks;
    bool imu_rate_applied;
    double applied_imu_rate_hz;
    bool lte_keep_connected_applied;
    bool applied_lte_keep_connected;
    egolink_location_runtime_pipeline_t pipeline;
    egolink_device_location_runtime_snapshot_t status;
} device_location_runtime_internal_t;

_Static_assert(sizeof(device_location_runtime_internal_t) <=
                   EGOLINK_DEVICE_LOCATION_RUNTIME_CONTEXT_BYTES,
               "device location runtime context is too small");
_Static_assert(EGOLINK_DEVICE_LOCATION_RUNTIME_CONTEXT_BYTES >=
                   EGOLINK_LOCATION_RUNTIME_CONTEXT_BYTES,
               "owner context cannot hold the location pipeline");

static device_location_runtime_internal_t *runtime_internal(
    egolink_device_location_runtime_t *runtime)
{
    return (device_location_runtime_internal_t *)(void *)runtime->opaque;
}

static const device_location_runtime_internal_t *runtime_internal_const(
    const egolink_device_location_runtime_t *runtime)
{
    return (const device_location_runtime_internal_t *)(const void *)
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

static egolink_device_location_action_results_t empty_actions(void)
{
    const egolink_device_location_action_results_t result = {
        .gnss_start = EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED,
        .gnss_stop = EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED,
        .cell_observe = EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED,
        .imu_rate = EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED,
        .lte_keep_connected =
            EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED,
        .upload_intent = EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED,
    };
    return result;
}

static void initialize_result(egolink_device_location_runtime_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT;
    result->pipeline_status = EGOLINK_LOCATION_RUNTIME_INVALID_ARGUMENT;
    result->pipeline_result.status =
        EGOLINK_LOCATION_RUNTIME_INVALID_ARGUMENT;
    result->pipeline_result.engine_status =
        EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    result->pipeline_result.policy_status =
        EGOLINK_LOCATION_POLICY_INVALID_ARGUMENT;
    result->pipeline_result.serializer_status =
        EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    result->pipeline_result.enqueue_status =
        EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVALID_ARGUMENT;
    result->actions = empty_actions();
}

static bool valid_magic(const device_location_runtime_internal_t *internal)
{
    return internal != NULL &&
           internal->magic == DEVICE_LOCATION_RUNTIME_MAGIC;
}

static void set_last_status(
    device_location_runtime_internal_t *internal,
    egolink_device_location_runtime_status_t status)
{
    internal->status.last_status = status;
    internal->status.lifecycle = internal->lifecycle;
    internal->status.enabled =
        internal->lifecycle == EGOLINK_DEVICE_LOCATION_RUNTIME_ACTIVE;
    internal->status.dependency_bound =
        internal->shared_outbox != NULL &&
        internal->location_adapter != NULL;
    internal->status.busy = internal->busy;
}

static bool action_failed(egolink_device_location_action_outcome_t outcome)
{
    return outcome == EGOLINK_DEVICE_LOCATION_ACTION_FAILED ||
           outcome == EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED;
}

static void record_action(
    device_location_runtime_internal_t *internal,
    egolink_device_location_action_outcome_t outcome)
{
    if (outcome == EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED) {
        return;
    }
    increment_saturated(&internal->status.action_requests);
    if (action_failed(outcome)) {
        increment_saturated(&internal->status.action_failures);
    }
}

static egolink_device_location_action_outcome_t invoke_gnss_start(
    const device_location_runtime_internal_t *internal,
    const egolink_location_runtime_input_t *input,
    const egolink_location_policy_decision_t *decision)
{
    if (decision->gnss_action !=
        EGOLINK_LOCATION_POLICY_GNSS_ACTION_START) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    }
    if (internal->callbacks.gnss_start == NULL) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED;
    }
    const egolink_device_location_gnss_start_request_t request = {
        .identity = &input->identity,
        .acquisition_timeout_ms = decision->gnss_acquisition_timeout_ms,
        .sos_priority =
            decision->policy_mode == EGOLINK_LOCATION_POLICY_SOS,
    };
    return internal->callbacks.gnss_start(
               internal->callbacks.context, &request)
               ? EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED
               : EGOLINK_DEVICE_LOCATION_ACTION_FAILED;
}

static egolink_device_location_action_outcome_t invoke_gnss_stop(
    const device_location_runtime_internal_t *internal,
    const egolink_location_runtime_input_t *input,
    const egolink_location_policy_decision_t *decision)
{
    if (decision->gnss_action !=
        EGOLINK_LOCATION_POLICY_GNSS_ACTION_STOP_TIMEOUT) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    }
    if (internal->callbacks.gnss_stop == NULL) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED;
    }
    const egolink_device_location_gnss_stop_request_t request = {
        .identity = &input->identity,
        .timeout_stop = true,
    };
    return internal->callbacks.gnss_stop(
               internal->callbacks.context, &request)
               ? EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED
               : EGOLINK_DEVICE_LOCATION_ACTION_FAILED;
}

static egolink_device_location_action_outcome_t invoke_cell_observe(
    const device_location_runtime_internal_t *internal,
    const egolink_location_runtime_input_t *input,
    const egolink_location_policy_decision_t *decision)
{
    if (!decision->cell_observe_now) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    }
    if (internal->callbacks.cell_observe == NULL) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED;
    }
    const egolink_device_location_cell_observe_request_t request = {
        .identity = &input->identity,
        .request_timeout_ms = decision->cell_request_timeout_ms,
        .sos_priority =
            decision->policy_mode == EGOLINK_LOCATION_POLICY_SOS,
    };
    return internal->callbacks.cell_observe(
               internal->callbacks.context, &request)
               ? EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED
               : EGOLINK_DEVICE_LOCATION_ACTION_FAILED;
}

static egolink_device_location_action_outcome_t invoke_imu_rate(
    device_location_runtime_internal_t *internal,
    const egolink_location_runtime_input_t *input,
    const egolink_location_policy_decision_t *decision)
{
    if (!isfinite(decision->imu_rate_hz) || decision->imu_rate_hz < 0.0) {
        return EGOLINK_DEVICE_LOCATION_ACTION_FAILED;
    }
    if (internal->imu_rate_applied &&
        internal->applied_imu_rate_hz == decision->imu_rate_hz) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    }
    if (internal->callbacks.set_imu_rate == NULL) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED;
    }
    const egolink_device_location_imu_rate_request_t request = {
        .identity = &input->identity,
        .rate_hz = decision->imu_rate_hz,
    };
    if (!internal->callbacks.set_imu_rate(
            internal->callbacks.context, &request)) {
        return EGOLINK_DEVICE_LOCATION_ACTION_FAILED;
    }
    internal->imu_rate_applied = true;
    internal->applied_imu_rate_hz = decision->imu_rate_hz;
    return EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED;
}

static egolink_device_location_action_outcome_t invoke_lte_keep_connected(
    device_location_runtime_internal_t *internal,
    const egolink_location_runtime_input_t *input,
    const egolink_location_policy_decision_t *decision)
{
    if (internal->lte_keep_connected_applied &&
        internal->applied_lte_keep_connected ==
            decision->lte_keep_connected) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    }
    if (internal->callbacks.set_lte_keep_connected == NULL) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED;
    }
    const egolink_device_location_lte_connection_request_t request = {
        .identity = &input->identity,
        .keep_connected = decision->lte_keep_connected,
    };
    if (!internal->callbacks.set_lte_keep_connected(
            internal->callbacks.context, &request)) {
        return EGOLINK_DEVICE_LOCATION_ACTION_FAILED;
    }
    internal->lte_keep_connected_applied = true;
    internal->applied_lte_keep_connected =
        decision->lte_keep_connected;
    return EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED;
}

static bool enqueue_metadata_valid(
    const egolink_location_outbox_enqueue_result_t *enqueue)
{
    return enqueue != NULL && enqueue->event_id[0] != '\0' &&
           enqueue->payload_sha256[0] != '\0' && enqueue->payload_length > 0U &&
           enqueue->payload_length <= EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES;
}

static egolink_device_location_action_outcome_t invoke_upload_intent(
    const device_location_runtime_internal_t *internal,
    const egolink_location_runtime_input_t *input,
    const egolink_location_runtime_result_t *pipeline_result)
{
    if (!pipeline_result->published) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    }
    if (!enqueue_metadata_valid(&pipeline_result->enqueue_result)) {
        return EGOLINK_DEVICE_LOCATION_ACTION_FAILED;
    }
    if (internal->callbacks.upload_intent == NULL) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED;
    }
    const egolink_device_location_upload_intent_t request = {
        .identity = &input->identity,
        .event_id = pipeline_result->enqueue_result.event_id,
        .payload_sha256 = pipeline_result->enqueue_result.payload_sha256,
        .payload_length = pipeline_result->enqueue_result.payload_length,
        .publish_reasons = pipeline_result->publish_reasons,
        .durable_envelope_present = true,
        .sos_priority =
            pipeline_result->enqueue_result.priority ==
            EGOLINK_OUTBOX_PRIORITY_CRITICAL,
    };
    return internal->callbacks.upload_intent(
               internal->callbacks.context, &request)
               ? EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED
               : EGOLINK_DEVICE_LOCATION_ACTION_FAILED;
}

static bool any_action_failed(
    const egolink_device_location_action_results_t *actions)
{
    return action_failed(actions->gnss_start) ||
           action_failed(actions->gnss_stop) ||
           action_failed(actions->cell_observe) ||
           action_failed(actions->imu_rate) ||
           action_failed(actions->lte_keep_connected) ||
           action_failed(actions->upload_intent);
}

static void record_actions(
    device_location_runtime_internal_t *internal,
    const egolink_device_location_action_results_t *actions)
{
    record_action(internal, actions->gnss_start);
    record_action(internal, actions->gnss_stop);
    record_action(internal, actions->cell_observe);
    record_action(internal, actions->imu_rate);
    record_action(internal, actions->lte_keep_connected);
    record_action(internal, actions->upload_intent);
    internal->status.last_actions = *actions;
}

static egolink_device_location_runtime_status_t lifecycle_status(
    egolink_device_location_runtime_lifecycle_t lifecycle)
{
    switch (lifecycle) {
    case EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED:
        return EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED_STATUS;
    case EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED:
        return EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED_STATUS;
    case EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED:
        return EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED_STATUS;
    case EGOLINK_DEVICE_LOCATION_RUNTIME_ACTIVE:
        return EGOLINK_DEVICE_LOCATION_RUNTIME_OK;
    case EGOLINK_DEVICE_LOCATION_RUNTIME_NEVER_INITIALIZED:
    default:
        return EGOLINK_DEVICE_LOCATION_RUNTIME_NOT_INITIALIZED;
    }
}

static void clear_bound_runtime(device_location_runtime_internal_t *internal)
{
    secure_clear(&internal->pipeline, sizeof(internal->pipeline));
    secure_clear(&internal->callbacks, sizeof(internal->callbacks));
    internal->imu_rate_applied = false;
    internal->applied_imu_rate_hz = 0.0;
    internal->lte_keep_connected_applied = false;
    internal->applied_lte_keep_connected = false;
    internal->shared_outbox = NULL;
    internal->location_adapter = NULL;
}

static egolink_device_location_action_outcome_t perform_cancel(
    device_location_runtime_internal_t *internal,
    egolink_device_location_cancel_reason_t reason)
{
    if (internal->callbacks.safe_cancel == NULL) {
        return EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED;
    }
    const bool retry_may_need_replay =
        internal->status.last_pipeline_status ==
            EGOLINK_LOCATION_RUNTIME_RETRY_REQUIRED ||
        internal->status.last_pipeline_status ==
            EGOLINK_LOCATION_RUNTIME_BLOCKED_RETRY_REQUIRED;
    const egolink_device_location_cancel_request_t request = {
        .reason = reason,
        .durable_envelopes_retained = true,
        .volatile_uncommitted_observation_may_require_journal_replay =
            retry_may_need_replay,
    };
    return internal->callbacks.safe_cancel(
               internal->callbacks.context, &request)
               ? EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED
               : EGOLINK_DEVICE_LOCATION_ACTION_FAILED;
}

void egolink_device_location_runtime_default_config(
    egolink_device_location_runtime_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->enabled = false;
    }
}

egolink_device_location_runtime_status_t
egolink_device_location_runtime_init(
    egolink_device_location_runtime_t *runtime,
    const egolink_device_location_runtime_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter)
{
    if (runtime == NULL || config == NULL) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT;
    }
    device_location_runtime_internal_t *internal = runtime_internal(runtime);
    if (valid_magic(internal)) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_ALREADY_INITIALIZED;
    }
    secure_clear(runtime, sizeof(*runtime));
    internal = runtime_internal(runtime);
    internal->magic = DEVICE_LOCATION_RUNTIME_MAGIC;
    internal->lifecycle = EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED;
    internal->status.lifecycle = internal->lifecycle;
    internal->status.last_status =
        EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED_STATUS;
    internal->status.last_pipeline_status =
        EGOLINK_LOCATION_RUNTIME_NOT_INITIALIZED;
    internal->status.last_actions = empty_actions();
    internal->status.cancel_action =
        EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    if (!config->enabled) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED_STATUS;
    }
    if (shared_outbox == NULL || location_adapter == NULL ||
        !location_adapter->initialized ||
        location_adapter->outbox != shared_outbox) {
        secure_clear(runtime, sizeof(*runtime));
        return EGOLINK_DEVICE_LOCATION_RUNTIME_DEPENDENCY_MISMATCH;
    }

    internal->shared_outbox = shared_outbox;
    internal->location_adapter = location_adapter;
    internal->callbacks = config->callbacks;
    const egolink_location_runtime_status_t pipeline_status =
        egolink_location_runtime_pipeline_init(
            &internal->pipeline, location_adapter, &config->pipeline_owner);
    if (pipeline_status != EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH) {
        secure_clear(runtime, sizeof(*runtime));
        return EGOLINK_DEVICE_LOCATION_RUNTIME_DEPENDENCY_MISMATCH;
    }
    internal->lifecycle = EGOLINK_DEVICE_LOCATION_RUNTIME_ACTIVE;
    internal->status.lifecycle = internal->lifecycle;
    internal->status.enabled = true;
    internal->status.dependency_bound = true;
    internal->status.last_status = EGOLINK_DEVICE_LOCATION_RUNTIME_OK;
    internal->status.last_pipeline_status = pipeline_status;
    return EGOLINK_DEVICE_LOCATION_RUNTIME_OK;
}

egolink_device_location_runtime_status_t
egolink_device_location_runtime_process(
    egolink_device_location_runtime_t *runtime,
    const egolink_location_runtime_input_t *input,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_device_location_runtime_result_t *result)
{
    initialize_result(result);
    if (runtime == NULL || input == NULL || scratch == NULL || result == NULL) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT;
    }
    device_location_runtime_internal_t *internal = runtime_internal(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_DEVICE_LOCATION_RUNTIME_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_DEVICE_LOCATION_RUNTIME_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle != EGOLINK_DEVICE_LOCATION_RUNTIME_ACTIVE) {
        result->status = lifecycle_status(internal->lifecycle);
        return result->status;
    }
    if (internal->shared_outbox == NULL ||
        internal->location_adapter == NULL ||
        internal->location_adapter->outbox != internal->shared_outbox ||
        !internal->location_adapter->initialized) {
        result->status =
            EGOLINK_DEVICE_LOCATION_RUNTIME_DEPENDENCY_MISMATCH;
        set_last_status(internal, result->status);
        return result->status;
    }

    internal->busy = true;
    internal->status.busy = true;
    increment_saturated(&internal->status.process_calls);
    result->pipeline_status = egolink_location_runtime_pipeline_process(
        &internal->pipeline, input, outbox_now_ms, scratch,
        &result->pipeline_result);
    internal->status.last_pipeline_status = result->pipeline_status;

    if (result->pipeline_status ==
        EGOLINK_LOCATION_RUNTIME_DUPLICATE_INPUT) {
        increment_saturated(&internal->status.duplicate_inputs);
        result->status = EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT;
        internal->busy = false;
        set_last_status(internal, result->status);
        return result->status;
    }
    if (result->pipeline_status != EGOLINK_LOCATION_RUNTIME_OK_NO_PUBLISH &&
        result->pipeline_status != EGOLINK_LOCATION_RUNTIME_OK_PUBLISHED) {
        increment_saturated(&internal->status.pipeline_failures);
        result->status =
            result->pipeline_status == EGOLINK_LOCATION_RUNTIME_RETRY_REQUIRED ||
                    result->pipeline_status ==
                        EGOLINK_LOCATION_RUNTIME_BLOCKED_RETRY_REQUIRED
                ? EGOLINK_DEVICE_LOCATION_RUNTIME_PIPELINE_RETRY_REQUIRED
                : EGOLINK_DEVICE_LOCATION_RUNTIME_PIPELINE_FAILED;
        internal->busy = false;
        set_last_status(internal, result->status);
        return result->status;
    }

    result->new_input_committed = true;
    result->durable_envelope_present = result->pipeline_result.published;
    increment_saturated(&internal->status.committed_inputs);
    if (result->durable_envelope_present) {
        increment_saturated(&internal->status.durable_envelopes);
    }
    internal->status.last_input_available = true;
    internal->status.last_sequence_id = input->identity.sequence_id;
    internal->status.last_event_time_ms = input->identity.event_time_ms;

    if (result->pipeline_result.policy_evaluated) {
        result->actions.gnss_start = invoke_gnss_start(
            internal, input, &result->pipeline_result.policy_decision);
        result->actions.gnss_stop = invoke_gnss_stop(
            internal, input, &result->pipeline_result.policy_decision);
        result->actions.cell_observe = invoke_cell_observe(
            internal, input, &result->pipeline_result.policy_decision);
        result->actions.imu_rate = invoke_imu_rate(
            internal, input, &result->pipeline_result.policy_decision);
        result->actions.lte_keep_connected = invoke_lte_keep_connected(
            internal, input, &result->pipeline_result.policy_decision);
    }
    result->actions.upload_intent = invoke_upload_intent(
        internal, input, &result->pipeline_result);
    record_actions(internal, &result->actions);

    const bool failed = any_action_failed(&result->actions);
    result->action_failure_after_commit = failed;
    result->status = failed
                         ? EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE
                         : EGOLINK_DEVICE_LOCATION_RUNTIME_OK;
    internal->busy = false;
    set_last_status(internal, result->status);
    return result->status;
}

egolink_device_location_runtime_status_t
egolink_device_location_runtime_cancel(
    egolink_device_location_runtime_t *runtime,
    egolink_device_location_action_outcome_t *cancel_action)
{
    if (cancel_action != NULL) {
        *cancel_action = EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    }
    if (runtime == NULL || cancel_action == NULL) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT;
    }
    device_location_runtime_internal_t *internal = runtime_internal(runtime);
    if (!valid_magic(internal)) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_NOT_INITIALIZED;
    }
    if (internal->busy) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_REENTRANT_CALL;
    }
    if (internal->lifecycle != EGOLINK_DEVICE_LOCATION_RUNTIME_ACTIVE) {
        return lifecycle_status(internal->lifecycle);
    }

    internal->busy = true;
    *cancel_action = perform_cancel(
        internal, EGOLINK_DEVICE_LOCATION_CANCEL_EXPLICIT);
    record_action(internal, *cancel_action);
    internal->status.cancel_action = *cancel_action;
    internal->lifecycle = EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED;
    clear_bound_runtime(internal);
    internal->busy = false;
    const egolink_device_location_runtime_status_t status =
        action_failed(*cancel_action)
            ? EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE
            : EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED_STATUS;
    set_last_status(internal, status);
    return status;
}

egolink_device_location_runtime_status_t
egolink_device_location_runtime_close(
    egolink_device_location_runtime_t *runtime,
    egolink_device_location_action_outcome_t *cancel_action)
{
    if (cancel_action != NULL) {
        *cancel_action = EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    }
    if (runtime == NULL || cancel_action == NULL) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT;
    }
    device_location_runtime_internal_t *internal = runtime_internal(runtime);
    if (!valid_magic(internal)) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_NOT_INITIALIZED;
    }
    if (internal->busy) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_REENTRANT_CALL;
    }
    if (internal->lifecycle == EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED_STATUS;
    }

    internal->busy = true;
    if (internal->lifecycle == EGOLINK_DEVICE_LOCATION_RUNTIME_ACTIVE) {
        *cancel_action = perform_cancel(
            internal, EGOLINK_DEVICE_LOCATION_CANCEL_CLOSE);
        record_action(internal, *cancel_action);
        internal->status.cancel_action = *cancel_action;
    }
    internal->lifecycle = EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED;
    clear_bound_runtime(internal);
    internal->busy = false;
    const egolink_device_location_runtime_status_t status =
        action_failed(*cancel_action)
            ? EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE
            : EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED_STATUS;
    set_last_status(internal, status);
    return status;
}

egolink_device_location_runtime_status_t
egolink_device_location_runtime_current_status(
    const egolink_device_location_runtime_t *runtime,
    egolink_device_location_runtime_snapshot_t *snapshot)
{
    if (snapshot != NULL) {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        snapshot->lifecycle =
            EGOLINK_DEVICE_LOCATION_RUNTIME_NEVER_INITIALIZED;
        snapshot->last_status =
            EGOLINK_DEVICE_LOCATION_RUNTIME_NOT_INITIALIZED;
        snapshot->last_pipeline_status =
            EGOLINK_LOCATION_RUNTIME_NOT_INITIALIZED;
        snapshot->last_actions = empty_actions();
        snapshot->cancel_action =
            EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED;
    }
    if (runtime == NULL || snapshot == NULL) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT;
    }
    const device_location_runtime_internal_t *internal =
        runtime_internal_const(runtime);
    if (!valid_magic(internal)) {
        return EGOLINK_DEVICE_LOCATION_RUNTIME_NOT_INITIALIZED;
    }
    *snapshot = internal->status;
    snapshot->lifecycle = internal->lifecycle;
    snapshot->enabled =
        internal->lifecycle == EGOLINK_DEVICE_LOCATION_RUNTIME_ACTIVE;
    snapshot->dependency_bound =
        internal->shared_outbox != NULL &&
        internal->location_adapter != NULL;
    snapshot->busy = internal->busy;
    return internal->busy
               ? EGOLINK_DEVICE_LOCATION_RUNTIME_REENTRANT_CALL
               : lifecycle_status(internal->lifecycle);
}

const char *egolink_device_location_runtime_status_name(
    egolink_device_location_runtime_status_t status)
{
    switch (status) {
    case EGOLINK_DEVICE_LOCATION_RUNTIME_OK:
        return "ok";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT:
        return "duplicate_input";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE:
        return "action_partial_failure";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_PIPELINE_RETRY_REQUIRED:
        return "pipeline_retry_required";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_PIPELINE_FAILED:
        return "pipeline_failed";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED_STATUS:
        return "disabled";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED_STATUS:
        return "cancelled";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED_STATUS:
        return "closed";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_NOT_INITIALIZED:
        return "not_initialized";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_ALREADY_INITIALIZED:
        return "already_initialized";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_DEPENDENCY_MISMATCH:
        return "dependency_mismatch";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_REENTRANT_CALL:
        return "reentrant_call";
    default:
        return "unknown";
    }
}

const char *egolink_device_location_runtime_lifecycle_name(
    egolink_device_location_runtime_lifecycle_t lifecycle)
{
    switch (lifecycle) {
    case EGOLINK_DEVICE_LOCATION_RUNTIME_NEVER_INITIALIZED:
        return "never_initialized";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED:
        return "disabled";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_ACTIVE:
        return "active";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED:
        return "cancelled";
    case EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED:
        return "closed";
    default:
        return "unknown";
    }
}

const char *egolink_device_location_action_outcome_name(
    egolink_device_location_action_outcome_t outcome)
{
    switch (outcome) {
    case EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED:
        return "not_requested";
    case EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED:
        return "succeeded";
    case EGOLINK_DEVICE_LOCATION_ACTION_FAILED:
        return "failed";
    case EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED:
        return "not_configured";
    default:
        return "unknown";
    }
}

#include "p0_delivery_runtime.h"

#include <limits.h>
#include <stdatomic.h>
#include <string.h>

#define P0_DELIVERY_RUNTIME_MAGIC UINT32_C(0x50304452)

#define P0_DELIVERY_HTTP_REJECTED "P0_DELIVERY_HTTP_REJECTED"
#define P0_DELIVERY_OFFLINE "P0_DELIVERY_OFFLINE"
#define P0_DELIVERY_DNS_FAILED "P0_DELIVERY_DNS_FAILED"
#define P0_DELIVERY_CONNECT_FAILED "P0_DELIVERY_CONNECT_FAILED"
#define P0_DELIVERY_TLS_FAILED "P0_DELIVERY_TLS_FAILED"
#define P0_DELIVERY_TIMEOUT "P0_DELIVERY_TIMEOUT"
#define P0_DELIVERY_IO_FAILED "P0_DELIVERY_IO_FAILED"
#define P0_DELIVERY_TRANSPORT_FAILED "P0_DELIVERY_TRANSPORT_FAILED"
#define P0_DELIVERY_CANCELLED "P0_DELIVERY_CANCELLED"
#define P0_DELIVERY_CALLBACK_FAILED "P0_DELIVERY_CALLBACK_FAILED"
#define P0_DELIVERY_CALLBACK_INVALID "P0_DELIVERY_CALLBACK_INVALID"
#define P0_DELIVERY_DURATION_EXCEEDED "P0_DELIVERY_DURATION_EXCEEDED"
#define P0_DELIVERY_RESPONSE_OVERSIZE "P0_DELIVERY_RESPONSE_OVERSIZE"
#define P0_DELIVERY_ROUTE_INVALID "P0_DELIVERY_ROUTE_INVALID"

#define P0_DELIVERY_TRANSFER_STATE_BITS 3U
#define P0_DELIVERY_TRANSFER_STATE_MASK UINT32_C(0x7)
#define P0_DELIVERY_TRANSFER_GENERATION_MAX \
    (UINT32_MAX >> P0_DELIVERY_TRANSFER_STATE_BITS)

typedef enum {
    P0_TRANSFER_IDLE = 0,
    P0_TRANSFER_LOCATION_ACTIVE,
    P0_TRANSFER_LOCATION_CANCEL_REQUESTED,
    P0_TRANSFER_NON_LOCATION_ACTIVE,
    P0_TRANSFER_RESULT_READY,
    P0_TRANSFER_RECOVERY_REQUIRED,
} p0_delivery_transfer_state_t;

typedef enum {
    P0_SETTLEMENT_NONE = 0,
    P0_SETTLEMENT_HTTP_SUCCESS,
    P0_SETTLEMENT_HTTP_REJECTED,
    P0_SETTLEMENT_TRANSPORT_FAILED,
    P0_SETTLEMENT_CANCELLED,
    P0_SETTLEMENT_CALLBACK_FAILED,
    P0_SETTLEMENT_CALLBACK_INVALID,
    P0_SETTLEMENT_DURATION_EXCEEDED,
    P0_SETTLEMENT_RESPONSE_OVERSIZE,
    P0_SETTLEMENT_ROUTE_INVALID,
} p0_delivery_settlement_t;

typedef struct {
    uint32_t magic;
    egolink_p0_delivery_runtime_lifecycle_t lifecycle;
    egolink_p0_delivery_runtime_phase_t phase;
    bool busy;
    bool configured_enabled;
    bool dispatcher_bound;
    bool settlement_retained;
    bool begin_recovery_pending;
    bool post_contract_valid;
    bool response_oversize;
    egolink_p0_outbox_dispatcher_t *dispatcher;
    egolink_p0_delivery_http_post_fn http_post;
    void *http_context;
    uint32_t max_post_duration_ms;
    egolink_p0_outbox_send_view_t send_view;
    uint8_t response[EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES];
    size_t response_length;
    size_t reported_response_length;
    uint16_t http_status_code;
    uint64_t settlement_time_ms;
    p0_delivery_settlement_t settlement;
    egolink_p0_outbox_route_t active_route;
    egolink_p0_delivery_post_outcome_t post_outcome;
    egolink_p0_delivery_transport_error_t transport_error;
    atomic_uint transfer_control;
    atomic_uint preemption_request_count;
    atomic_uint preemption_win_count;
    atomic_uint preemption_too_late_count;
    uint32_t transfer_generation;
    uint64_t split_begin_time_ms;
    bool prepared_snapshot_available;
    bool execute_prepared_called;
    bool preemption_observed;
    bool preemption_won;
    bool late_transport_result_discarded;
    bool transport_acceptance_may_be_unknown;
    egolink_p0_outbox_dispatcher_snapshot_t dispatcher_probe;
    egolink_p0_delivery_runtime_snapshot_t status;
} p0_delivery_runtime_internal_t;

_Static_assert(
    sizeof(p0_delivery_runtime_internal_t) <=
        EGOLINK_P0_DELIVERY_RUNTIME_CONTEXT_BYTES,
    "P0 delivery runtime context is too small");
_Static_assert(
    EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES ==
        EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES,
    "P0 delivery response buffer must match the location ceiling");
_Static_assert(
    EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES <=
        EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES,
    "P0 delivery response buffer cannot hold the SOS ceiling");
_Static_assert(sizeof(unsigned int) == sizeof(uint32_t),
               "split delivery requires a 32-bit unsigned int");
#if ATOMIC_INT_LOCK_FREE != 2
#error "split delivery requires always-lock-free 32-bit atomic unsigned int"
#endif

static p0_delivery_runtime_internal_t *internal_of(
    egolink_p0_delivery_runtime_t *runtime)
{
    return (p0_delivery_runtime_internal_t *)(void *)runtime->opaque;
}

static const p0_delivery_runtime_internal_t *internal_of_const(
    const egolink_p0_delivery_runtime_t *runtime)
{
    return (const p0_delivery_runtime_internal_t *)(const void *)
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

static uint32_t transfer_control_value(
    uint32_t generation,
    p0_delivery_transfer_state_t state)
{
    return (generation << P0_DELIVERY_TRANSFER_STATE_BITS) |
        (uint32_t)state;
}

static uint32_t transfer_control_generation(uint32_t control)
{
    return control >> P0_DELIVERY_TRANSFER_STATE_BITS;
}

static p0_delivery_transfer_state_t transfer_control_state(uint32_t control)
{
    return (p0_delivery_transfer_state_t)(
        control & P0_DELIVERY_TRANSFER_STATE_MASK);
}

static void increment_atomic_saturated(atomic_uint *value)
{
    unsigned int observed = atomic_load_explicit(value, memory_order_relaxed);
    while (observed != UINT_MAX &&
           !atomic_compare_exchange_weak_explicit(
               value,
               &observed,
               observed + 1U,
               memory_order_relaxed,
               memory_order_relaxed)) {
    }
}

static void publish_transfer_state(
    p0_delivery_runtime_internal_t *internal,
    p0_delivery_transfer_state_t state)
{
    atomic_store_explicit(
        &internal->transfer_control,
        transfer_control_value(internal->transfer_generation, state),
        memory_order_release);
}

static bool valid_magic(const p0_delivery_runtime_internal_t *internal)
{
    return internal != NULL && internal->magic == P0_DELIVERY_RUNTIME_MAGIC;
}

static bool exact_path(const char *left, const char *right)
{
    return left != NULL && right != NULL && strcmp(left, right) == 0;
}

static bool valid_transport_error(
    egolink_p0_delivery_transport_error_t error)
{
    return error >= EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE &&
        error <= EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER;
}

static void initialize_result(egolink_p0_delivery_runtime_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    result->route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
    result->post_outcome = EGOLINK_P0_DELIVERY_POST_NOT_CALLED;
    result->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE;
    result->dispatcher_begin_status = EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    result->dispatcher_finish_status = EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    result->dispatcher_begin_result.status =
        EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
    result->dispatcher_finish_result.status =
        EGOLINK_P0_OUTBOX_INVALID_ARGUMENT;
}

static void update_status(
    p0_delivery_runtime_internal_t *internal,
    egolink_p0_delivery_runtime_status_t status)
{
    const uint32_t transfer_control = atomic_load_explicit(
        &internal->transfer_control, memory_order_acquire);
    internal->status.lifecycle = internal->lifecycle;
    internal->status.phase = internal->phase;
    internal->status.last_status = status;
    internal->status.enabled = internal->configured_enabled;
    internal->status.busy = internal->busy;
    internal->status.dispatcher_bound = internal->dispatcher_bound;
    internal->status.private_settlement_retained_for_recovery =
        internal->settlement_retained;
    internal->status.begin_recovery_pending =
        internal->begin_recovery_pending;
    internal->status.active_route = internal->active_route;
    internal->status.transfer_generation =
        transfer_control_generation(transfer_control);
    internal->status.durable_sos_preemption_requests =
        atomic_load_explicit(
            &internal->preemption_request_count, memory_order_relaxed);
    internal->status.durable_sos_preemption_wins =
        atomic_load_explicit(
            &internal->preemption_win_count, memory_order_relaxed);
    internal->status.durable_sos_preemption_too_late =
        atomic_load_explicit(
            &internal->preemption_too_late_count, memory_order_relaxed);
    internal->status.prepared_snapshot_available =
        internal->prepared_snapshot_available;
    internal->status.durable_sos_preemption_requested =
        transfer_control_state(transfer_control) ==
            P0_TRANSFER_LOCATION_CANCEL_REQUESTED;
}

static egolink_p0_delivery_runtime_status_t return_status(
    p0_delivery_runtime_internal_t *internal,
    egolink_p0_delivery_runtime_result_t *result,
    egolink_p0_delivery_runtime_status_t status)
{
    internal->busy = false;
    if (result != NULL) {
        result->status = status;
        result->private_settlement_retained_for_recovery =
            internal->settlement_retained;
    }
    update_status(internal, status);
    return status;
}

static void clear_attempt(p0_delivery_runtime_internal_t *internal)
{
    egolink_p0_outbox_dispatcher_clear_send_view(&internal->send_view);
    secure_clear(internal->response, sizeof(internal->response));
    internal->response_length = 0U;
    internal->reported_response_length = 0U;
    internal->http_status_code = UINT16_C(0);
    internal->settlement_time_ms = UINT64_C(0);
    internal->settlement = P0_SETTLEMENT_NONE;
    internal->post_outcome = EGOLINK_P0_DELIVERY_POST_NOT_CALLED;
    internal->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE;
    internal->post_contract_valid = false;
    internal->response_oversize = false;
    internal->settlement_retained = false;
    internal->begin_recovery_pending = false;
    internal->active_route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
    internal->split_begin_time_ms = UINT64_C(0);
    internal->prepared_snapshot_available = false;
    internal->execute_prepared_called = false;
    internal->preemption_observed = false;
    internal->preemption_won = false;
    internal->late_transport_result_discarded = false;
    internal->transport_acceptance_may_be_unknown = false;
    internal->phase = EGOLINK_P0_DELIVERY_PHASE_IDLE;
    publish_transfer_state(internal, P0_TRANSFER_IDLE);
}

static const char *expected_path(egolink_p0_outbox_route_t route)
{
    if (route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS) {
        return EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH;
    }
    if (route == EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE) {
        return EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH;
    }
    return NULL;
}

static size_t expected_response_capacity(egolink_p0_outbox_route_t route)
{
    if (route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS) {
        return EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES;
    }
    if (route == EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE) {
        return EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES;
    }
    return 0U;
}

static bool expected_priority(const egolink_p0_outbox_send_view_t *view)
{
    if (view->attempt.route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS) {
        return view->attempt.priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL;
    }
    if (view->attempt.route == EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE) {
        return view->attempt.priority == EGOLINK_OUTBOX_PRIORITY_NORMAL ||
            view->attempt.priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL;
    }
    return false;
}

static bool valid_send_view(const egolink_p0_outbox_send_view_t *view)
{
    const char *path = expected_path(view->attempt.route);
    const size_t response_capacity =
        expected_response_capacity(view->attempt.route);
    return path != NULL && response_capacity > 0U &&
        view->payload != NULL && view->payload_length > 0U &&
        view->payload_length <= EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES &&
        !view->completion_only &&
        exact_path(view->endpoint_path, path) &&
        view->response_max_bytes == response_capacity &&
        expected_priority(view);
}

static const char *transport_error_code(
    egolink_p0_delivery_transport_error_t error)
{
    switch (error) {
    case EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OFFLINE:
        return P0_DELIVERY_OFFLINE;
    case EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_DNS:
        return P0_DELIVERY_DNS_FAILED;
    case EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_CONNECT:
        return P0_DELIVERY_CONNECT_FAILED;
    case EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TLS:
        return P0_DELIVERY_TLS_FAILED;
    case EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TIMEOUT:
        return P0_DELIVERY_TIMEOUT;
    case EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_IO:
        return P0_DELIVERY_IO_FAILED;
    case EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER:
    case EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE:
    default:
        return P0_DELIVERY_TRANSPORT_FAILED;
    }
}

static const char *settlement_error_code(
    const p0_delivery_runtime_internal_t *internal)
{
    switch (internal->settlement) {
    case P0_SETTLEMENT_HTTP_REJECTED:
        return P0_DELIVERY_HTTP_REJECTED;
    case P0_SETTLEMENT_TRANSPORT_FAILED:
        return transport_error_code(internal->transport_error);
    case P0_SETTLEMENT_CANCELLED:
        return P0_DELIVERY_CANCELLED;
    case P0_SETTLEMENT_CALLBACK_FAILED:
        return P0_DELIVERY_CALLBACK_FAILED;
    case P0_SETTLEMENT_CALLBACK_INVALID:
        return P0_DELIVERY_CALLBACK_INVALID;
    case P0_SETTLEMENT_DURATION_EXCEEDED:
        return P0_DELIVERY_DURATION_EXCEEDED;
    case P0_SETTLEMENT_RESPONSE_OVERSIZE:
        return P0_DELIVERY_RESPONSE_OVERSIZE;
    case P0_SETTLEMENT_ROUTE_INVALID:
        return P0_DELIVERY_ROUTE_INVALID;
    case P0_SETTLEMENT_HTTP_SUCCESS:
    case P0_SETTLEMENT_NONE:
    default:
        return NULL;
    }
}

static void prepare_callback_failure(
    p0_delivery_runtime_internal_t *internal,
    p0_delivery_settlement_t settlement,
    bool oversize)
{
    secure_clear(internal->response, sizeof(internal->response));
    internal->response_length = 0U;
    internal->http_status_code = UINT16_C(0);
    internal->settlement = settlement;
    internal->post_contract_valid = false;
    internal->response_oversize = oversize;
    internal->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER;
    increment_saturated(&internal->status.callback_contract_failures);
    if (oversize) {
        increment_saturated(&internal->status.oversize_responses);
    }
}

static void capture_callback_result(
    p0_delivery_runtime_internal_t *internal,
    uint64_t begin_time_ms,
    size_t response_capacity,
    egolink_p0_delivery_post_outcome_t outcome,
    const egolink_p0_delivery_post_result_t *post_result)
{
    internal->post_outcome = outcome;
    internal->reported_response_length = post_result->response_length;
    internal->settlement_time_ms = post_result->completion_time_ms;

    if (!valid_transport_error(post_result->transport_error) ||
        post_result->completion_time_ms < begin_time_ms) {
        internal->settlement_time_ms = begin_time_ms;
        prepare_callback_failure(
            internal, P0_SETTLEMENT_CALLBACK_INVALID, false);
        return;
    }
    const uint64_t elapsed_ms =
        post_result->completion_time_ms - begin_time_ms;
    if (elapsed_ms > (uint64_t)internal->max_post_duration_ms) {
        internal->settlement_time_ms = begin_time_ms;
        prepare_callback_failure(
            internal, P0_SETTLEMENT_DURATION_EXCEEDED, false);
        return;
    }
    if (post_result->response_length > response_capacity) {
        prepare_callback_failure(
            internal, P0_SETTLEMENT_RESPONSE_OVERSIZE, true);
        return;
    }

    switch (outcome) {
    case EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE:
        if (post_result->http_status_code < UINT16_C(100) ||
            post_result->http_status_code > UINT16_C(599) ||
            post_result->transport_error !=
                EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE) {
            prepare_callback_failure(
                internal, P0_SETTLEMENT_CALLBACK_INVALID, false);
            return;
        }
        internal->post_contract_valid = true;
        internal->http_status_code = post_result->http_status_code;
        internal->transport_error =
            EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE;
        if (post_result->http_status_code >= UINT16_C(200) &&
            post_result->http_status_code <= UINT16_C(299)) {
            internal->settlement = P0_SETTLEMENT_HTTP_SUCCESS;
            internal->response_length = post_result->response_length;
        } else {
            internal->settlement = P0_SETTLEMENT_HTTP_REJECTED;
            secure_clear(internal->response, sizeof(internal->response));
            internal->response_length = 0U;
        }
        return;
    case EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED:
        if (post_result->http_status_code != UINT16_C(0) ||
            post_result->response_length != 0U ||
            post_result->transport_error ==
                EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE) {
            prepare_callback_failure(
                internal, P0_SETTLEMENT_CALLBACK_INVALID, false);
            return;
        }
        internal->post_contract_valid = true;
        internal->settlement = P0_SETTLEMENT_TRANSPORT_FAILED;
        internal->transport_error = post_result->transport_error;
        secure_clear(internal->response, sizeof(internal->response));
        internal->response_length = 0U;
        internal->http_status_code = UINT16_C(0);
        return;
    case EGOLINK_P0_DELIVERY_POST_CANCELLED:
    case EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED:
        if (post_result->http_status_code != UINT16_C(0) ||
            post_result->response_length != 0U ||
            post_result->transport_error !=
                EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE) {
            prepare_callback_failure(
                internal, P0_SETTLEMENT_CALLBACK_INVALID, false);
            return;
        }
        internal->post_contract_valid = true;
        internal->settlement =
            outcome == EGOLINK_P0_DELIVERY_POST_CANCELLED
                ? P0_SETTLEMENT_CANCELLED
                : P0_SETTLEMENT_CALLBACK_FAILED;
        internal->transport_error =
            EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE;
        secure_clear(internal->response, sizeof(internal->response));
        internal->response_length = 0U;
        internal->http_status_code = UINT16_C(0);
        return;
    case EGOLINK_P0_DELIVERY_POST_NOT_CALLED:
    default:
        prepare_callback_failure(
            internal, P0_SETTLEMENT_CALLBACK_INVALID, false);
        return;
    }
}

static void copy_settlement_to_result(
    const p0_delivery_runtime_internal_t *internal,
    egolink_p0_delivery_runtime_result_t *result)
{
    result->route = internal->active_route;
    result->post_outcome = internal->post_outcome;
    result->transport_error = internal->transport_error;
    result->http_status_code = internal->http_status_code;
    result->response_length = internal->reported_response_length;
    result->post_contract_valid = internal->post_contract_valid;
    result->response_oversize = internal->response_oversize;
    result->prepared_snapshot_available =
        internal->prepared_snapshot_available;
    result->execute_prepared_called = internal->execute_prepared_called;
    result->durable_sos_preemption_observed =
        internal->preemption_observed;
    result->durable_sos_preemption_won = internal->preemption_won;
    result->late_transport_result_discarded =
        internal->late_transport_result_discarded;
    result->transport_acceptance_may_be_unknown =
        internal->transport_acceptance_may_be_unknown;
    result->transfer_generation = internal->transfer_generation;
}

static egolink_p0_delivery_runtime_status_t finish_once(
    p0_delivery_runtime_internal_t *internal,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    const bool http_success =
        internal->settlement == P0_SETTLEMENT_HTTP_SUCCESS;
    const bool http_rejected =
        internal->settlement == P0_SETTLEMENT_HTTP_REJECTED;
    const uint16_t http_status_code =
        (http_success || http_rejected)
            ? internal->http_status_code
            : UINT16_C(0);
    const char *error_code = http_success
        ? NULL
        : settlement_error_code(internal);
    const uint8_t *response =
        http_success && internal->response_length > 0U
            ? internal->response
            : NULL;
    const size_t response_length =
        http_success ? internal->response_length : 0U;

    result->finish_called = true;
    increment_saturated(&internal->status.finish_calls);
    result->dispatcher_finish_status = egolink_p0_outbox_dispatcher_finish(
        internal->dispatcher,
        &internal->send_view,
        http_status_code,
        error_code,
        response,
        response_length,
        now_ms,
        &result->dispatcher_finish_result);

    switch (result->dispatcher_finish_status) {
    case EGOLINK_P0_OUTBOX_ACK_DELETED:
        result->terminal = true;
        result->deleted_after_server_durable_ingest_ack = true;
        increment_saturated(&internal->status.ack_deletes);
        clear_attempt(internal);
        return EGOLINK_P0_DELIVERY_ACK_DELETED;
    case EGOLINK_P0_OUTBOX_ACK_ALREADY_APPLIED:
        result->terminal = true;
        clear_attempt(internal);
        return EGOLINK_P0_DELIVERY_ACK_ALREADY_APPLIED;
    case EGOLINK_P0_OUTBOX_FINISHED_RETAINED:
    case EGOLINK_P0_OUTBOX_CANCELLED_RETAINED:
        result->terminal = true;
        result->durable_record_retained = true;
        increment_saturated(&internal->status.retained_attempts);
        clear_attempt(internal);
        return EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED;
    case EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER:
    case EGOLINK_P0_OUTBOX_ATTEMPT_MISMATCH:
    case EGOLINK_P0_OUTBOX_DEPENDENCY_MISMATCH:
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        internal->settlement_retained = true;
        result->durable_record_retained = true;
        result->private_settlement_retained_for_recovery = true;
        increment_saturated(&internal->status.recovery_required);
        return EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED;
    case EGOLINK_P0_OUTBOX_DEPENDENCY_RECOVERY_REQUIRED:
    case EGOLINK_P0_OUTBOX_ATTEMPT_ALREADY_ACTIVE:
    case EGOLINK_P0_OUTBOX_DISABLED_STATUS:
    case EGOLINK_P0_OUTBOX_CLOSED_STATUS:
    case EGOLINK_P0_OUTBOX_INVALID_ARGUMENT:
    case EGOLINK_P0_OUTBOX_NOT_INITIALIZED:
    case EGOLINK_P0_OUTBOX_ALREADY_INITIALIZED:
    case EGOLINK_P0_OUTBOX_REENTRANT_CALL:
    case EGOLINK_P0_OUTBOX_OK:
    case EGOLINK_P0_OUTBOX_BEGIN_READY:
    case EGOLINK_P0_OUTBOX_NO_DUE_RECORD:
    case EGOLINK_P0_OUTBOX_INVALID_EVENT_RETAINED:
    default:
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        internal->settlement_retained = true;
        internal->dispatcher_bound = false;
        result->durable_record_retained = true;
        result->private_settlement_retained_for_recovery = true;
        increment_saturated(&internal->status.recovery_required);
        return EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
    }
}

void egolink_p0_delivery_runtime_default_config(
    egolink_p0_delivery_runtime_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->enabled = false;
        config->max_post_duration_ms =
            EGOLINK_P0_DELIVERY_RUNTIME_DEFAULT_MAX_POST_DURATION_MS;
    }
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_init(
    egolink_p0_delivery_runtime_t *runtime,
    const egolink_p0_delivery_runtime_config_t *config,
    egolink_p0_outbox_dispatcher_t *already_initialized_dispatcher)
{
    if (runtime == NULL || config == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (valid_magic(internal)) {
        return EGOLINK_P0_DELIVERY_ALREADY_INITIALIZED;
    }
    secure_clear(runtime, sizeof(*runtime));
    internal = internal_of(runtime);
    atomic_init(
        &internal->transfer_control,
        transfer_control_value(UINT32_C(0), P0_TRANSFER_IDLE));
    atomic_init(&internal->preemption_request_count, 0U);
    atomic_init(&internal->preemption_win_count, 0U);
    atomic_init(&internal->preemption_too_late_count, 0U);
    internal->magic = P0_DELIVERY_RUNTIME_MAGIC;
    internal->lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_DISABLED;
    internal->phase = EGOLINK_P0_DELIVERY_PHASE_IDLE;
    internal->status.lifecycle = internal->lifecycle;
    internal->status.phase = internal->phase;
    internal->status.last_status = EGOLINK_P0_DELIVERY_DISABLED_STATUS;
    internal->max_post_duration_ms = config->max_post_duration_ms;
    if (!config->enabled) {
        return EGOLINK_P0_DELIVERY_DISABLED_STATUS;
    }
    if (config->http_post == NULL ||
        config->max_post_duration_ms == UINT32_C(0) ||
        config->max_post_duration_ms >
            EGOLINK_P0_DELIVERY_RUNTIME_MAX_POST_DURATION_MS ||
        already_initialized_dispatcher == NULL) {
        secure_clear(runtime, sizeof(*runtime));
        return EGOLINK_P0_DELIVERY_INVALID_CONFIG;
    }

    internal->dispatcher = already_initialized_dispatcher;
    const egolink_p0_outbox_dispatcher_status_t dependency_status =
        egolink_p0_outbox_dispatcher_current_status(
            internal->dispatcher, &internal->dispatcher_probe);
    const bool dependency_ready =
        dependency_status == EGOLINK_P0_OUTBOX_OK &&
        internal->dispatcher_probe.lifecycle ==
            EGOLINK_P0_OUTBOX_DISPATCHER_ACTIVE &&
        internal->dispatcher_probe.phase == EGOLINK_P0_OUTBOX_PHASE_IDLE &&
        internal->dispatcher_probe.active_route ==
            EGOLINK_P0_OUTBOX_ROUTE_NONE &&
        internal->dispatcher_probe.enabled &&
        internal->dispatcher_probe.dependency_bound &&
        !internal->dispatcher_probe.busy;
    secure_clear(
        &internal->dispatcher_probe, sizeof(internal->dispatcher_probe));
    if (!dependency_ready) {
        secure_clear(runtime, sizeof(*runtime));
        return EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
    }

    internal->http_post = config->http_post;
    internal->http_context = config->http_context;
    internal->max_post_duration_ms = config->max_post_duration_ms;
    internal->configured_enabled = true;
    internal->dispatcher_bound = true;
    internal->lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE;
    update_status(internal, EGOLINK_P0_DELIVERY_OK);
    return EGOLINK_P0_DELIVERY_OK;
}

static egolink_p0_delivery_runtime_status_t inactive_runtime_status(
    const p0_delivery_runtime_internal_t *internal)
{
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_DISABLED) {
        return EGOLINK_P0_DELIVERY_DISABLED_STATUS;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED) {
        return EGOLINK_P0_DELIVERY_CANCELLED_STATUS;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CLOSED) {
        return EGOLINK_P0_DELIVERY_CLOSED_STATUS;
    }
    return EGOLINK_P0_DELIVERY_OK;
}

static void prepare_cancelled_settlement(
    p0_delivery_runtime_internal_t *internal,
    bool post_was_entered,
    bool late_result)
{
    secure_clear(internal->response, sizeof(internal->response));
    internal->response_length = 0U;
    internal->reported_response_length = 0U;
    internal->http_status_code = UINT16_C(0);
    internal->settlement_time_ms = internal->split_begin_time_ms;
    internal->settlement = P0_SETTLEMENT_CANCELLED;
    internal->post_outcome = post_was_entered
        ? EGOLINK_P0_DELIVERY_POST_CANCELLED
        : EGOLINK_P0_DELIVERY_POST_NOT_CALLED;
    internal->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE;
    internal->post_contract_valid = true;
    internal->response_oversize = false;
    internal->preemption_observed = true;
    internal->preemption_won = true;
    internal->late_transport_result_discarded = late_result;
    internal->transport_acceptance_may_be_unknown = post_was_entered;
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_prepare(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t begin_time_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    initialize_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_P0_DELIVERY_REENTRANT_CALL;
        return result->status;
    }
    const egolink_p0_delivery_runtime_status_t inactive_status =
        inactive_runtime_status(internal);
    if (inactive_status != EGOLINK_P0_DELIVERY_OK) {
        result->status = inactive_status;
        return result->status;
    }
    if (internal->phase == EGOLINK_P0_DELIVERY_PHASE_PREPARED) {
        copy_settlement_to_result(internal, result);
        result->status = EGOLINK_P0_DELIVERY_PREPARED;
        return result->status;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY) {
        copy_settlement_to_result(internal, result);
        result->status = EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY;
        return result->status;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED) {
        result->route = internal->active_route;
        result->private_settlement_retained_for_recovery = true;
        result->status = EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED;
        return result->status;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED) {
        result->route = internal->active_route;
        result->status = EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED;
        return result->status;
    }
    if (internal->phase != EGOLINK_P0_DELIVERY_PHASE_IDLE ||
        !internal->dispatcher_bound || internal->dispatcher == NULL ||
        internal->http_post == NULL) {
        result->route = internal->active_route;
        result->status = EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    if (internal->transfer_generation >=
        P0_DELIVERY_TRANSFER_GENERATION_MAX) {
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        increment_saturated(&internal->status.recovery_required);
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED);
    }

    internal->busy = true;
    increment_saturated(&internal->status.prepared_calls);
    clear_attempt(internal);
    internal->phase = EGOLINK_P0_DELIVERY_PHASE_DRIVING;

    result->begin_called = true;
    increment_saturated(&internal->status.begin_calls);
    result->dispatcher_begin_status = egolink_p0_outbox_dispatcher_begin(
        internal->dispatcher,
        begin_time_ms,
        &internal->send_view,
        &result->dispatcher_begin_result);
    internal->active_route = internal->send_view.attempt.route !=
            EGOLINK_P0_OUTBOX_ROUTE_NONE
        ? internal->send_view.attempt.route
        : result->dispatcher_begin_result.route;
    result->route = internal->active_route;

    if (result->dispatcher_begin_status == EGOLINK_P0_OUTBOX_NO_DUE_RECORD) {
        increment_saturated(&internal->status.no_due_records);
        clear_attempt(internal);
        return return_status(
            internal, result, EGOLINK_P0_DELIVERY_NO_DUE_RECORD);
    }
    if (result->dispatcher_begin_status ==
        EGOLINK_P0_OUTBOX_INVALID_EVENT_RETAINED) {
        result->terminal = true;
        result->durable_record_retained = true;
        increment_saturated(&internal->status.retained_attempts);
        clear_attempt(internal);
        return return_status(
            internal, result, EGOLINK_P0_DELIVERY_INVALID_EVENT_RETAINED);
    }
    if (result->dispatcher_begin_status ==
        EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER) {
        secure_clear(internal->response, sizeof(internal->response));
        internal->settlement_time_ms = begin_time_ms;
        internal->reported_response_length = 0U;
        internal->post_outcome = EGOLINK_P0_DELIVERY_POST_NOT_CALLED;
        internal->post_contract_valid = false;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        increment_saturated(&internal->status.recovery_required);
        if (internal->active_route ==
                EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS &&
            internal->send_view.completion_only) {
            internal->settlement = P0_SETTLEMENT_ROUTE_INVALID;
            internal->transport_error =
                EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER;
            internal->settlement_retained = true;
            internal->phase =
                EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED;
            publish_transfer_state(
                internal, P0_TRANSFER_RECOVERY_REQUIRED);
            result->private_settlement_retained_for_recovery = true;
            return return_status(
                internal,
                result,
                EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED);
        }
        internal->begin_recovery_pending = true;
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED);
    }
    if (result->dispatcher_begin_status != EGOLINK_P0_OUTBOX_BEGIN_READY) {
        egolink_p0_outbox_dispatcher_clear_send_view(&internal->send_view);
        secure_clear(internal->response, sizeof(internal->response));
        internal->dispatcher_bound = false;
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        increment_saturated(&internal->status.recovery_required);
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED);
    }

    ++internal->transfer_generation;
    internal->split_begin_time_ms = begin_time_ms;
    internal->active_route = internal->send_view.attempt.route;
    internal->prepared_snapshot_available = true;
    result->route = internal->active_route;
    if (!valid_send_view(&internal->send_view)) {
        internal->settlement = P0_SETTLEMENT_ROUTE_INVALID;
        internal->post_outcome = EGOLINK_P0_DELIVERY_POST_NOT_CALLED;
        internal->transport_error =
            EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER;
        internal->settlement_time_ms = begin_time_ms;
        internal->reported_response_length = 0U;
        internal->post_contract_valid = false;
        secure_clear(internal->response, sizeof(internal->response));
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY;
        publish_transfer_state(internal, P0_TRANSFER_RESULT_READY);
        copy_settlement_to_result(internal, result);
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY);
    }

    internal->phase = EGOLINK_P0_DELIVERY_PHASE_PREPARED;
    publish_transfer_state(
        internal,
        internal->active_route == EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE
            ? P0_TRANSFER_LOCATION_ACTIVE
            : P0_TRANSFER_NON_LOCATION_ACTIVE);
    copy_settlement_to_result(internal, result);
    return return_status(internal, result, EGOLINK_P0_DELIVERY_PREPARED);
}

bool egolink_p0_delivery_runtime_location_cancel_requested(
    void *context,
    uint32_t transfer_generation)
{
    if (context == NULL || transfer_generation == UINT32_C(0)) {
        return false;
    }
    const p0_delivery_runtime_internal_t *internal =
        internal_of_const((const egolink_p0_delivery_runtime_t *)context);
    if (!valid_magic(internal)) {
        return false;
    }
    const uint32_t control = atomic_load_explicit(
        &internal->transfer_control, memory_order_acquire);
    return transfer_control_generation(control) == transfer_generation &&
        transfer_control_state(control) ==
            P0_TRANSFER_LOCATION_CANCEL_REQUESTED;
}

egolink_p0_delivery_sos_preempt_status_t
egolink_p0_delivery_runtime_signal_durable_sos(
    egolink_p0_delivery_runtime_t *runtime)
{
    if (runtime == NULL) {
        return EGOLINK_P0_DELIVERY_SOS_PREEMPT_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (!valid_magic(internal)) {
        return EGOLINK_P0_DELIVERY_SOS_PREEMPT_NOT_INITIALIZED;
    }

    unsigned int observed = atomic_load_explicit(
        &internal->transfer_control, memory_order_acquire);
    for (;;) {
        const p0_delivery_transfer_state_t state =
            transfer_control_state(observed);
        if (state == P0_TRANSFER_LOCATION_ACTIVE) {
            const unsigned int desired = transfer_control_value(
                transfer_control_generation(observed),
                P0_TRANSFER_LOCATION_CANCEL_REQUESTED);
            if (atomic_compare_exchange_weak_explicit(
                    &internal->transfer_control,
                    &observed,
                    desired,
                    memory_order_acq_rel,
                    memory_order_acquire)) {
                increment_atomic_saturated(
                    &internal->preemption_request_count);
                increment_atomic_saturated(&internal->preemption_win_count);
                return EGOLINK_P0_DELIVERY_SOS_PREEMPT_REQUESTED;
            }
            continue;
        }
        if (state == P0_TRANSFER_LOCATION_CANCEL_REQUESTED) {
            return EGOLINK_P0_DELIVERY_SOS_PREEMPT_ALREADY_REQUESTED;
        }
        if (state == P0_TRANSFER_RESULT_READY) {
            increment_atomic_saturated(
                &internal->preemption_too_late_count);
            return EGOLINK_P0_DELIVERY_SOS_PREEMPT_RESULT_ALREADY_READY;
        }
        if (state == P0_TRANSFER_NON_LOCATION_ACTIVE) {
            return EGOLINK_P0_DELIVERY_SOS_PREEMPT_ROUTE_NOT_CANCELLABLE;
        }
        if (state == P0_TRANSFER_RECOVERY_REQUIRED) {
            return EGOLINK_P0_DELIVERY_SOS_PREEMPT_RECOVERY_REQUIRED;
        }
        return EGOLINK_P0_DELIVERY_SOS_PREEMPT_NO_ACTIVE_LOCATION;
    }
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_execute_prepared(
    egolink_p0_delivery_runtime_t *runtime,
    egolink_p0_delivery_runtime_result_t *result)
{
    initialize_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_P0_DELIVERY_REENTRANT_CALL;
        return result->status;
    }
    const egolink_p0_delivery_runtime_status_t inactive_status =
        inactive_runtime_status(internal);
    if (inactive_status != EGOLINK_P0_DELIVERY_OK) {
        result->status = inactive_status;
        return result->status;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY) {
        copy_settlement_to_result(internal, result);
        result->status = EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY;
        return result->status;
    }
    if (internal->phase != EGOLINK_P0_DELIVERY_PHASE_PREPARED ||
        !internal->prepared_snapshot_available ||
        internal->settlement != P0_SETTLEMENT_NONE) {
        result->route = internal->active_route;
        result->status = EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
        return result->status;
    }

    internal->busy = true;
    internal->phase = EGOLINK_P0_DELIVERY_PHASE_EXECUTING_PREPARED;
    internal->execute_prepared_called = true;
    increment_saturated(&internal->status.execute_prepared_calls);
    result->route = internal->active_route;

    unsigned int control = atomic_load_explicit(
        &internal->transfer_control, memory_order_acquire);
    const p0_delivery_transfer_state_t expected_active_state =
        internal->active_route == EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE
            ? P0_TRANSFER_LOCATION_ACTIVE
            : P0_TRANSFER_NON_LOCATION_ACTIVE;
    if (transfer_control_generation(control) !=
        internal->transfer_generation) {
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        increment_saturated(&internal->status.recovery_required);
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED);
    }
    if (transfer_control_state(control) ==
        P0_TRANSFER_LOCATION_CANCEL_REQUESTED) {
        prepare_cancelled_settlement(internal, false, false);
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY;
        publish_transfer_state(internal, P0_TRANSFER_RESULT_READY);
        copy_settlement_to_result(internal, result);
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY);
    }
    if (transfer_control_state(control) != expected_active_state) {
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        increment_saturated(&internal->status.recovery_required);
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED);
    }

    const char *path = expected_path(internal->send_view.attempt.route);
    const size_t response_capacity =
        expected_response_capacity(internal->send_view.attempt.route);
    egolink_p0_delivery_post_request_t request;
    (void)memset(&request, 0, sizeof(request));
    request.route = internal->send_view.attempt.route;
    request.path = path;
    request.body = internal->send_view.payload;
    request.body_length = internal->send_view.payload_length;
    request.response = internal->response;
    request.response_capacity = response_capacity;
    request.priority = internal->send_view.attempt.priority;
    request.cancel_requested =
        egolink_p0_delivery_runtime_location_cancel_requested;
    request.cancel_context = runtime;
    request.transfer_generation = internal->transfer_generation;
    egolink_p0_delivery_post_result_t post_result;
    (void)memset(&post_result, 0, sizeof(post_result));
    result->post_called = true;
    increment_saturated(&internal->status.post_calls);
    const egolink_p0_delivery_post_outcome_t outcome = internal->http_post(
        internal->http_context, &request, &post_result);
    capture_callback_result(
        internal,
        internal->split_begin_time_ms,
        response_capacity,
        outcome,
        &post_result);

    bool transport_result_won = false;
    unsigned int desired = transfer_control_value(
        internal->transfer_generation, P0_TRANSFER_RESULT_READY);
    unsigned int expected = transfer_control_value(
        internal->transfer_generation, expected_active_state);
    transport_result_won = atomic_compare_exchange_strong_explicit(
        &internal->transfer_control,
        &expected,
        desired,
        memory_order_acq_rel,
        memory_order_acquire);
    if (!transport_result_won &&
        transfer_control_generation(expected) ==
            internal->transfer_generation &&
        transfer_control_state(expected) ==
            P0_TRANSFER_LOCATION_CANCEL_REQUESTED) {
        prepare_cancelled_settlement(
            internal,
            true,
            outcome != EGOLINK_P0_DELIVERY_POST_CANCELLED);
        publish_transfer_state(internal, P0_TRANSFER_RESULT_READY);
    } else if (!transport_result_won) {
        secure_clear(&request, sizeof(request));
        secure_clear(&post_result, sizeof(post_result));
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        increment_saturated(&internal->status.recovery_required);
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED);
    }

    secure_clear(&request, sizeof(request));
    secure_clear(&post_result, sizeof(post_result));
    internal->phase =
        EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY;
    copy_settlement_to_result(internal, result);
    return return_status(
        internal,
        result,
        EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY);
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_settle_prepared(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    initialize_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_P0_DELIVERY_REENTRANT_CALL;
        return result->status;
    }
    const egolink_p0_delivery_runtime_status_t inactive_status =
        inactive_runtime_status(internal);
    if (inactive_status != EGOLINK_P0_DELIVERY_OK) {
        result->status = inactive_status;
        return result->status;
    }
    if (internal->phase !=
            EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY ||
        !internal->prepared_snapshot_available ||
        internal->settlement == P0_SETTLEMENT_NONE ||
        now_ms < internal->settlement_time_ms) {
        result->route = internal->active_route;
        result->status = internal->phase ==
                EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED
            ? EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED
            : EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
        return result->status;
    }

    internal->busy = true;
    increment_saturated(&internal->status.settle_prepared_calls);
    copy_settlement_to_result(internal, result);
    const egolink_p0_delivery_runtime_status_t finish_status =
        finish_once(internal, now_ms, result);
    return return_status(internal, result, finish_status);
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_drive_once(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t begin_time_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    initialize_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_P0_DELIVERY_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_DISABLED) {
        result->status = EGOLINK_P0_DELIVERY_DISABLED_STATUS;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED) {
        result->status = EGOLINK_P0_DELIVERY_CANCELLED_STATUS;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CLOSED) {
        result->status = EGOLINK_P0_DELIVERY_CLOSED_STATUS;
        return result->status;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED) {
        result->route = internal->active_route;
        result->private_settlement_retained_for_recovery = true;
        result->status = EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED;
        return result->status;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED) {
        result->route = internal->active_route;
        result->status = EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED;
        return result->status;
    }
    if (internal->phase != EGOLINK_P0_DELIVERY_PHASE_IDLE ||
        !internal->dispatcher_bound || internal->dispatcher == NULL ||
        internal->http_post == NULL) {
        result->route = internal->active_route;
        result->status =
            EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }

    internal->busy = true;
    internal->phase = EGOLINK_P0_DELIVERY_PHASE_DRIVING;
    increment_saturated(&internal->status.drive_calls);
    clear_attempt(internal);
    internal->phase = EGOLINK_P0_DELIVERY_PHASE_DRIVING;
    secure_clear(internal->response, sizeof(internal->response));

    result->begin_called = true;
    increment_saturated(&internal->status.begin_calls);
    result->dispatcher_begin_status = egolink_p0_outbox_dispatcher_begin(
        internal->dispatcher,
        begin_time_ms,
        &internal->send_view,
        &result->dispatcher_begin_result);
    internal->active_route = internal->send_view.attempt.route !=
            EGOLINK_P0_OUTBOX_ROUTE_NONE
        ? internal->send_view.attempt.route
        : result->dispatcher_begin_result.route;
    result->route = internal->active_route;

    if (result->dispatcher_begin_status == EGOLINK_P0_OUTBOX_NO_DUE_RECORD) {
        increment_saturated(&internal->status.no_due_records);
        clear_attempt(internal);
        return return_status(
            internal, result, EGOLINK_P0_DELIVERY_NO_DUE_RECORD);
    }
    if (result->dispatcher_begin_status ==
        EGOLINK_P0_OUTBOX_INVALID_EVENT_RETAINED) {
        result->terminal = true;
        result->durable_record_retained = true;
        increment_saturated(&internal->status.retained_attempts);
        clear_attempt(internal);
        return return_status(
            internal, result, EGOLINK_P0_DELIVERY_INVALID_EVENT_RETAINED);
    }
    if (result->dispatcher_begin_status ==
        EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER) {
        secure_clear(internal->response, sizeof(internal->response));
        internal->settlement_time_ms = begin_time_ms;
        internal->reported_response_length = 0U;
        internal->post_outcome = EGOLINK_P0_DELIVERY_POST_NOT_CALLED;
        internal->post_contract_valid = false;
        increment_saturated(&internal->status.recovery_required);
        if (internal->active_route ==
                EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS &&
            internal->send_view.completion_only) {
            internal->settlement = P0_SETTLEMENT_ROUTE_INVALID;
            internal->transport_error =
                EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER;
            internal->settlement_retained = true;
            internal->phase =
                EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED;
            result->private_settlement_retained_for_recovery = true;
            return return_status(
                internal,
                result,
                EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED);
        }
        internal->begin_recovery_pending = true;
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED;
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED);
    }
    if (result->dispatcher_begin_status != EGOLINK_P0_OUTBOX_BEGIN_READY) {
        egolink_p0_outbox_dispatcher_clear_send_view(&internal->send_view);
        secure_clear(internal->response, sizeof(internal->response));
        internal->dispatcher_bound = false;
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED;
        increment_saturated(&internal->status.recovery_required);
        return return_status(
            internal,
            result,
            EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED);
    }

    internal->active_route = internal->send_view.attempt.route;
    result->route = internal->active_route;
    if (!valid_send_view(&internal->send_view)) {
        internal->settlement = P0_SETTLEMENT_ROUTE_INVALID;
        internal->post_outcome = EGOLINK_P0_DELIVERY_POST_NOT_CALLED;
        internal->transport_error =
            EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER;
        internal->settlement_time_ms = begin_time_ms;
        internal->reported_response_length = 0U;
        internal->post_contract_valid = false;
        secure_clear(internal->response, sizeof(internal->response));
    } else {
        const char *path = expected_path(internal->send_view.attempt.route);
        const size_t response_capacity = expected_response_capacity(
            internal->send_view.attempt.route);
        egolink_p0_delivery_post_request_t request;
        (void)memset(&request, 0, sizeof(request));
        request.route = internal->send_view.attempt.route;
        request.path = path;
        request.body = internal->send_view.payload;
        request.body_length = internal->send_view.payload_length;
        request.response = internal->response;
        request.response_capacity = response_capacity;
        request.priority = internal->send_view.attempt.priority;
        egolink_p0_delivery_post_result_t post_result;
        (void)memset(&post_result, 0, sizeof(post_result));
        result->post_called = true;
        increment_saturated(&internal->status.post_calls);
        const egolink_p0_delivery_post_outcome_t outcome =
            internal->http_post(
                internal->http_context, &request, &post_result);
        capture_callback_result(
            internal,
            begin_time_ms,
            response_capacity,
            outcome,
            &post_result);
        secure_clear(&request, sizeof(request));
        secure_clear(&post_result, sizeof(post_result));
    }

    copy_settlement_to_result(internal, result);
    const egolink_p0_delivery_runtime_status_t finish_status = finish_once(
        internal, internal->settlement_time_ms, result);
    return return_status(internal, result, finish_status);
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_retry_finish(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    initialize_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_P0_DELIVERY_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle != EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE) {
        result->status =
            internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED
                ? EGOLINK_P0_DELIVERY_CANCELLED_STATUS
                : (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CLOSED
                       ? EGOLINK_P0_DELIVERY_CLOSED_STATUS
                       : EGOLINK_P0_DELIVERY_DISABLED_STATUS);
        return result->status;
    }
    if (internal->phase !=
            EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED ||
        !internal->settlement_retained ||
        internal->settlement == P0_SETTLEMENT_NONE ||
        now_ms < internal->settlement_time_ms) {
        result->status =
            internal->phase ==
                    EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED
                ? EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED
                : (internal->phase ==
                           EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED
                       ? EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED
                       : EGOLINK_P0_DELIVERY_INVALID_ARGUMENT);
        return result->status;
    }

    internal->busy = true;
    copy_settlement_to_result(internal, result);
    increment_saturated(&internal->status.explicit_finish_retries);
    const egolink_p0_delivery_runtime_status_t finish_status =
        finish_once(internal, now_ms, result);
    return return_status(internal, result, finish_status);
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_retry_begin_recovery(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    initialize_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_P0_DELIVERY_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle != EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE) {
        result->status =
            internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED
                ? EGOLINK_P0_DELIVERY_CANCELLED_STATUS
                : (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CLOSED
                       ? EGOLINK_P0_DELIVERY_CLOSED_STATUS
                       : EGOLINK_P0_DELIVERY_DISABLED_STATUS);
        return result->status;
    }
    if (internal->phase !=
            EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED ||
        !internal->begin_recovery_pending) {
        result->status = internal->phase ==
                EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED
            ? EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED
            : EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
        return result->status;
    }

    internal->busy = true;
    result->route = internal->active_route;
    increment_saturated(
        &internal->status.explicit_begin_recovery_retries);
    result->dispatcher_finish_status = egolink_p0_outbox_dispatcher_cancel(
        internal->dispatcher,
        now_ms,
        &internal->send_view,
        &result->dispatcher_finish_result);
    if (result->dispatcher_finish_status ==
        EGOLINK_P0_OUTBOX_CANCELLED_RETAINED) {
        result->terminal = true;
        result->durable_record_retained = true;
        increment_saturated(&internal->status.retained_attempts);
        clear_attempt(internal);
        return return_status(
            internal, result, EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED);
    }

    result->durable_record_retained = true;
    internal->begin_recovery_pending = true;
    internal->phase = EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED;
    publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
    increment_saturated(&internal->status.recovery_required);
    return return_status(
        internal,
        result,
        EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED);
}

static egolink_p0_delivery_runtime_status_t map_control_result(
    p0_delivery_runtime_internal_t *internal,
    egolink_p0_delivery_runtime_result_t *result,
    egolink_p0_outbox_dispatcher_status_t dispatcher_status,
    bool closing)
{
    result->dispatcher_finish_status = dispatcher_status;
    result->route = result->dispatcher_finish_result.route;
    if ((!closing && dispatcher_status == EGOLINK_P0_OUTBOX_OK) ||
        dispatcher_status == EGOLINK_P0_OUTBOX_CANCELLED_RETAINED) {
        result->terminal = true;
        result->durable_record_retained =
            dispatcher_status == EGOLINK_P0_OUTBOX_CANCELLED_RETAINED;
        if (result->durable_record_retained) {
            increment_saturated(&internal->status.retained_attempts);
        }
        clear_attempt(internal);
        internal->configured_enabled = false;
        internal->lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED;
        return EGOLINK_P0_DELIVERY_CANCELLED_STATUS;
    }
    if (closing && dispatcher_status == EGOLINK_P0_OUTBOX_CLOSED_STATUS) {
        result->terminal = true;
        clear_attempt(internal);
        internal->dispatcher = NULL;
        internal->http_post = NULL;
        internal->http_context = NULL;
        internal->dispatcher_bound = false;
        internal->configured_enabled = false;
        internal->lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_CLOSED;
        return EGOLINK_P0_DELIVERY_CLOSED_STATUS;
    }

    if (internal->begin_recovery_pending) {
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        result->durable_record_retained = true;
        increment_saturated(&internal->status.recovery_required);
        return EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED;
    }
    if (internal->settlement != P0_SETTLEMENT_NONE) {
        internal->settlement_retained = true;
        internal->phase =
            EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED;
        publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
        result->private_settlement_retained_for_recovery = true;
        result->durable_record_retained = true;
        increment_saturated(&internal->status.recovery_required);
        return EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED;
    }
    internal->dispatcher_bound = false;
    internal->phase =
        EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED;
    publish_transfer_state(internal, P0_TRANSFER_RECOVERY_REQUIRED);
    increment_saturated(&internal->status.recovery_required);
    return EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_cancel(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    initialize_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_P0_DELIVERY_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED) {
        result->terminal = true;
        result->status = EGOLINK_P0_DELIVERY_CANCELLED_STATUS;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CLOSED) {
        result->terminal = true;
        result->status = EGOLINK_P0_DELIVERY_CLOSED_STATUS;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_DISABLED) {
        result->status = EGOLINK_P0_DELIVERY_DISABLED_STATUS;
        return result->status;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED) {
        result->status =
            EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY) {
        copy_settlement_to_result(internal, result);
        result->status = EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY;
        return result->status;
    }

    internal->busy = true;
    result->dispatcher_finish_status = egolink_p0_outbox_dispatcher_cancel(
        internal->dispatcher,
        now_ms,
        &internal->send_view,
        &result->dispatcher_finish_result);
    const egolink_p0_delivery_runtime_status_t status = map_control_result(
        internal, result, result->dispatcher_finish_status, false);
    return return_status(internal, result, status);
}

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_close(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result)
{
    initialize_result(result);
    if (runtime == NULL || result == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    p0_delivery_runtime_internal_t *internal = internal_of(runtime);
    if (!valid_magic(internal)) {
        result->status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
        return result->status;
    }
    if (internal->busy) {
        result->status = EGOLINK_P0_DELIVERY_REENTRANT_CALL;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CLOSED) {
        result->terminal = true;
        result->status = EGOLINK_P0_DELIVERY_CLOSED_STATUS;
        return result->status;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_DISABLED) {
        clear_attempt(internal);
        internal->dispatcher = NULL;
        internal->http_post = NULL;
        internal->http_context = NULL;
        internal->dispatcher_bound = false;
        internal->max_post_duration_ms = UINT32_C(0);
        internal->lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_CLOSED;
        internal->configured_enabled = false;
        result->terminal = true;
        return return_status(
            internal, result, EGOLINK_P0_DELIVERY_CLOSED_STATUS);
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED) {
        result->status =
            EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY) {
        copy_settlement_to_result(internal, result);
        result->status = EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY;
        return result->status;
    }

    internal->busy = true;
    result->dispatcher_finish_status = egolink_p0_outbox_dispatcher_close(
        internal->dispatcher,
        now_ms,
        &internal->send_view,
        &result->dispatcher_finish_result);
    const egolink_p0_delivery_runtime_status_t status = map_control_result(
        internal, result, result->dispatcher_finish_status, true);
    return return_status(internal, result, status);
}

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_current_status(
    const egolink_p0_delivery_runtime_t *runtime,
    egolink_p0_delivery_runtime_snapshot_t *snapshot)
{
    if (snapshot != NULL) {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        snapshot->lifecycle = EGOLINK_P0_DELIVERY_RUNTIME_NEVER_INITIALIZED;
        snapshot->last_status = EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
    }
    if (runtime == NULL || snapshot == NULL) {
        return EGOLINK_P0_DELIVERY_INVALID_ARGUMENT;
    }
    const p0_delivery_runtime_internal_t *internal = internal_of_const(runtime);
    if (!valid_magic(internal)) {
        return EGOLINK_P0_DELIVERY_NOT_INITIALIZED;
    }
    *snapshot = internal->status;
    snapshot->lifecycle = internal->lifecycle;
    snapshot->phase = internal->phase;
    snapshot->enabled = internal->configured_enabled;
    snapshot->busy = internal->busy;
    snapshot->dispatcher_bound = internal->dispatcher_bound;
    snapshot->private_settlement_retained_for_recovery =
        internal->settlement_retained;
    snapshot->begin_recovery_pending = internal->begin_recovery_pending;
    snapshot->active_route = internal->active_route;
    const uint32_t transfer_control = atomic_load_explicit(
        &internal->transfer_control, memory_order_acquire);
    snapshot->transfer_generation =
        transfer_control_generation(transfer_control);
    snapshot->durable_sos_preemption_requests = atomic_load_explicit(
        &internal->preemption_request_count, memory_order_relaxed);
    snapshot->durable_sos_preemption_wins = atomic_load_explicit(
        &internal->preemption_win_count, memory_order_relaxed);
    snapshot->durable_sos_preemption_too_late = atomic_load_explicit(
        &internal->preemption_too_late_count, memory_order_relaxed);
    snapshot->prepared_snapshot_available =
        internal->prepared_snapshot_available;
    snapshot->durable_sos_preemption_requested =
        transfer_control_state(transfer_control) ==
            P0_TRANSFER_LOCATION_CANCEL_REQUESTED;
    if (internal->busy) {
        return EGOLINK_P0_DELIVERY_REENTRANT_CALL;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_DISABLED) {
        return EGOLINK_P0_DELIVERY_DISABLED_STATUS;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED) {
        return EGOLINK_P0_DELIVERY_CANCELLED_STATUS;
    }
    if (internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_CLOSED) {
        return EGOLINK_P0_DELIVERY_CLOSED_STATUS;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED) {
        return EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED) {
        return EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED) {
        return EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
    }
    if (internal->phase == EGOLINK_P0_DELIVERY_PHASE_PREPARED) {
        return EGOLINK_P0_DELIVERY_PREPARED;
    }
    if (internal->phase ==
        EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY) {
        return EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY;
    }
    return EGOLINK_P0_DELIVERY_OK;
}

bool egolink_p0_delivery_runtime_dependencies_match(
    const egolink_p0_delivery_runtime_t *runtime,
    const egolink_outbox_t *shared_outbox,
    const egolink_location_outbox_adapter_t *location_adapter)
{
    if (runtime == NULL || shared_outbox == NULL ||
        location_adapter == NULL) {
        return false;
    }
    const p0_delivery_runtime_internal_t *internal =
        internal_of_const(runtime);
    return valid_magic(internal) &&
        internal->lifecycle == EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE &&
        internal->dispatcher_bound && internal->dispatcher != NULL &&
        egolink_p0_outbox_dispatcher_dependencies_match(
            internal->dispatcher, shared_outbox, location_adapter);
}

const char *egolink_p0_delivery_runtime_status_name(
    egolink_p0_delivery_runtime_status_t status)
{
    switch (status) {
    case EGOLINK_P0_DELIVERY_OK: return "ok";
    case EGOLINK_P0_DELIVERY_NO_DUE_RECORD: return "no_due_record";
    case EGOLINK_P0_DELIVERY_ACK_DELETED: return "ack_deleted";
    case EGOLINK_P0_DELIVERY_ACK_ALREADY_APPLIED:
        return "ack_already_applied";
    case EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED:
        return "attempt_retained";
    case EGOLINK_P0_DELIVERY_INVALID_EVENT_RETAINED:
        return "invalid_event_retained";
    case EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED:
        return "finish_recovery_required";
    case EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED:
        return "begin_recovery_required";
    case EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED:
        return "dependency_recovery_required";
    case EGOLINK_P0_DELIVERY_CANCELLED_STATUS: return "cancelled";
    case EGOLINK_P0_DELIVERY_CLOSED_STATUS: return "closed";
    case EGOLINK_P0_DELIVERY_DISABLED_STATUS: return "disabled";
    case EGOLINK_P0_DELIVERY_INVALID_ARGUMENT: return "invalid_argument";
    case EGOLINK_P0_DELIVERY_INVALID_CONFIG: return "invalid_config";
    case EGOLINK_P0_DELIVERY_NOT_INITIALIZED: return "not_initialized";
    case EGOLINK_P0_DELIVERY_ALREADY_INITIALIZED:
        return "already_initialized";
    case EGOLINK_P0_DELIVERY_REENTRANT_CALL: return "reentrant_call";
    case EGOLINK_P0_DELIVERY_PREPARED: return "prepared";
    case EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY:
        return "transport_result_ready";
    default: return "unknown";
    }
}

const char *egolink_p0_delivery_runtime_phase_name(
    egolink_p0_delivery_runtime_phase_t phase)
{
    switch (phase) {
    case EGOLINK_P0_DELIVERY_PHASE_IDLE: return "idle";
    case EGOLINK_P0_DELIVERY_PHASE_DRIVING: return "driving";
    case EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED:
        return "finish_recovery_required";
    case EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED:
        return "begin_recovery_required";
    case EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED:
        return "dependency_recovery_required";
    case EGOLINK_P0_DELIVERY_PHASE_PREPARED: return "prepared";
    case EGOLINK_P0_DELIVERY_PHASE_EXECUTING_PREPARED:
        return "executing_prepared";
    case EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY:
        return "transport_result_ready";
    default: return "unknown";
    }
}

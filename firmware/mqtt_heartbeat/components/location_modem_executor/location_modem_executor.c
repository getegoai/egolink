#include "location_modem_executor.h"

#include <limits.h>
#include <string.h>

#define MODEM_EXECUTOR_MAGIC UINT32_C(0x4D455845)
#define MODEM_EXECUTOR_SIDECAR_CAPACITY EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY

typedef struct {
    bool occupied;
    egolink_modem_command_kind_t kind;
    uint64_t timeout_ms;
    char operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
} modem_executor_sidecar_t;

typedef struct {
    uint32_t magic;
    egolink_modem_executor_lifecycle_t lifecycle;
    egolink_modem_executor_phase_t phase;
    egolink_outbox_t *shared_outbox;
    egolink_location_outbox_adapter_t *location_adapter;
    egolink_p0_delivery_runtime_t *delivery_runtime;
    egolink_location_modem_gnss_execute_fn execute_gnss;
    void *gnss_context;
    egolink_location_modem_cell_execute_fn execute_cell;
    void *cell_context;
    uint64_t default_gnss_status_timeout_ms;
    egolink_modem_arbiter_t arbiter;
    egolink_device_location_runtime_t device_runtime;
    modem_executor_sidecar_t sidecars[MODEM_EXECUTOR_SIDECAR_CAPACITY];
    egolink_modem_arbiter_ticket_t active_ticket;
    uint64_t active_timeout_ms;
    bool active_callback_called;
    bool active_callback_contract_valid;
    bool active_cancel_before_callback;
    egolink_modem_callback_outcome_t active_callback_outcome;
    uint64_t active_completion_time_ms;
    sim7670_gnss_report_t active_gnss_report;
    sim7670_lte_report_t active_lte_report;
    egolink_p0_delivery_runtime_status_t active_p0_status;
    egolink_p0_delivery_runtime_result_t active_p0_result;
    bool p0_delivery_prepared;
    egolink_p0_outbox_route_t p0_prepared_route;
    bool sos_transport_outstanding;
    bool urgent_gnss_outstanding;
    bool deferred_sos_transport;
    bool deferred_location_transport;
    bool deferred_cell_observe;
    uint64_t deferred_cell_timeout_ms;
    uint64_t next_attempt;
    uint64_t generated_attempts;
    uint64_t process_calls;
    uint64_t committed_inputs;
    uint64_t queued_commands;
    uint64_t queue_failures;
    uint64_t callback_calls;
    uint64_t callback_contract_failures;
    uint64_t map_failures;
    uint64_t settled_commands;
} modem_executor_internal_t;

_Static_assert(
    sizeof(modem_executor_internal_t) <=
        EGOLINK_LOCATION_MODEM_EXECUTOR_CONTEXT_BYTES,
    "location modem executor context is too small");

static modem_executor_internal_t *internal_of(
    egolink_location_modem_executor_t *executor)
{
    return (modem_executor_internal_t *)(void *)executor->opaque;
}

static const modem_executor_internal_t *internal_of_const(
    const egolink_location_modem_executor_t *executor)
{
    return (const modem_executor_internal_t *)(const void *)executor->opaque;
}

static bool valid_magic(const modem_executor_internal_t *internal)
{
    uint32_t observed = UINT32_C(0);
    if (internal == NULL) {
        return false;
    }
    /* Byte-copy avoids a typed read from never-initialized caller storage. */
    (void)memcpy(&observed, (const void *)internal, sizeof(observed));
    return observed == MODEM_EXECUTOR_MAGIC;
}

static void increment_saturated(uint64_t *value)
{
    if (*value != UINT64_MAX) {
        ++(*value);
    }
}

static egolink_modem_executor_status_t lifecycle_status(
    const modem_executor_internal_t *internal)
{
    if (!valid_magic(internal)) {
        return EGOLINK_MODEM_EXECUTOR_NOT_INITIALIZED;
    }
    if (internal->lifecycle == EGOLINK_MODEM_EXECUTOR_DISABLED) {
        return EGOLINK_MODEM_EXECUTOR_DISABLED_STATUS;
    }
    if (internal->lifecycle == EGOLINK_MODEM_EXECUTOR_RECOVERY_REQUIRED) {
        return EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
    }
    if (internal->lifecycle != EGOLINK_MODEM_EXECUTOR_ACTIVE) {
        return EGOLINK_MODEM_EXECUTOR_NOT_INITIALIZED;
    }
    return EGOLINK_MODEM_EXECUTOR_OK;
}

static void latch_recovery(modem_executor_internal_t *internal)
{
    internal->lifecycle = EGOLINK_MODEM_EXECUTOR_RECOVERY_REQUIRED;
}

static bool valid_timeout(uint64_t timeout_ms)
{
    return timeout_ms > UINT64_C(0) &&
        timeout_ms <= EGOLINK_LOCATION_MODEM_EXECUTOR_MAX_TIMEOUT_MS;
}

static void defer_cell_observe(modem_executor_internal_t *internal,
                               uint64_t timeout_ms)
{
    if (!valid_timeout(timeout_ms)) {
        latch_recovery(internal);
        return;
    }
    /*
     * One bounded Cell attempt may satisfy coalesced policy requests. Keep the
     * tighter timeout so a later request can never silently relax an older
     * unsatisfied bound.
     */
    if (!internal->deferred_cell_observe ||
        timeout_ms < internal->deferred_cell_timeout_ms) {
        internal->deferred_cell_timeout_ms = timeout_ms;
    }
    internal->deferred_cell_observe = true;
}

static bool transport_kind(egolink_modem_command_kind_t kind)
{
    return kind == EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT ||
        kind == EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT;
}

static bool gnss_kind(egolink_modem_command_kind_t kind)
{
    return kind == EGOLINK_MODEM_COMMAND_GNSS_ACQUIRE ||
        kind == EGOLINK_MODEM_COMMAND_GNSS_STATUS ||
        kind == EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE;
}

static bool valid_callback_outcome(egolink_modem_callback_outcome_t outcome)
{
    return outcome >= EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE &&
        outcome < EGOLINK_MODEM_CALLBACK_OUTCOME_COUNT;
}

static egolink_modem_priority_t priority_for_kind(
    egolink_modem_command_kind_t kind)
{
    if (kind == EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT) {
        return EGOLINK_MODEM_PRIORITY_CRITICAL;
    }
    if (kind == EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE) {
        return EGOLINK_MODEM_PRIORITY_URGENT;
    }
    return EGOLINK_MODEM_PRIORITY_NORMAL;
}

static void initialize_enqueue_result(
    egolink_location_modem_enqueue_result_t *result,
    egolink_modem_command_kind_t kind)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_MODEM_EXECUTOR_OK;
    result->kind = kind;
    result->arbiter_status = EGOLINK_MODEM_ARBITER_OK;
    result->arbiter_result.status = EGOLINK_MODEM_ARBITER_OK;
}

static void initialize_process_result(
    egolink_location_modem_process_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    initialize_enqueue_result(&result->gnss, EGOLINK_MODEM_COMMAND_NONE);
    initialize_enqueue_result(&result->cell, EGOLINK_MODEM_COMMAND_CELL_OBSERVE);
    initialize_enqueue_result(
        &result->location_transport,
        EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT);
}

static void initialize_durable_sos_result(
    egolink_location_modem_durable_sos_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    result->location_status =
        EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT;
    result->location_result.status =
        EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT;
    result->location_result.pipeline_status =
        EGOLINK_LOCATION_RUNTIME_INVALID_ARGUMENT;
    result->location_result.pipeline_result.status =
        EGOLINK_LOCATION_RUNTIME_INVALID_ARGUMENT;
    result->location_result.pipeline_result.engine_status =
        EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    result->location_result.pipeline_result.policy_status =
        EGOLINK_LOCATION_POLICY_INVALID_ARGUMENT;
    result->location_result.pipeline_result.serializer_status =
        EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    result->location_result.pipeline_result.enqueue_status =
        EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVALID_ARGUMENT;
    result->signal_status = EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    initialize_enqueue_result(
        &result->location_transport,
        EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT);
    initialize_enqueue_result(
        &result->cell,
        EGOLINK_MODEM_COMMAND_CELL_OBSERVE);
    initialize_enqueue_result(
        &result->sos_transport,
        EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT);
    initialize_enqueue_result(
        &result->urgent_gnss,
        EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE);
}

static void initialize_prepare_result(
    egolink_location_modem_prepare_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->status = EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
        result->arbiter_status = EGOLINK_MODEM_ARBITER_OK;
        result->p0_status = EGOLINK_P0_DELIVERY_OK;
    }
}

static void initialize_execute_result(
    egolink_location_modem_execute_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->status = EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
        result->callback_outcome = EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
        result->p0_status = EGOLINK_P0_DELIVERY_OK;
    }
}

static void initialize_settle_result(
    egolink_location_modem_settle_result_t *result)
{
    if (result != NULL) {
        (void)memset(result, 0, sizeof(*result));
        result->status = EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
        result->reported_outcome = EGOLINK_MODEM_REPORTED_NOT_EXECUTED;
        result->arbiter_status = EGOLINK_MODEM_ARBITER_OK;
        result->p0_status = EGOLINK_P0_DELIVERY_OK;
        result->map_status = EGOLINK_LOCATION_HARDWARE_MAP_INVALID_ARGUMENT;
        result->mapped_origin = EGOLINK_LOCATION_HARDWARE_ORIGIN_NONE;
    }
}

static bool same_id(
    const char left[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY],
    const char right[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY])
{
    return strncmp(left, right,
                   EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY) == 0;
}

static modem_executor_sidecar_t *find_sidecar(
    modem_executor_internal_t *internal,
    const char operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY])
{
    for (size_t index = 0U; index < MODEM_EXECUTOR_SIDECAR_CAPACITY; ++index) {
        modem_executor_sidecar_t *sidecar = &internal->sidecars[index];
        if (sidecar->occupied && same_id(sidecar->operation_id, operation_id)) {
            return sidecar;
        }
    }
    return NULL;
}

static modem_executor_sidecar_t *free_sidecar(
    modem_executor_internal_t *internal)
{
    for (size_t index = 0U; index < MODEM_EXECUTOR_SIDECAR_CAPACITY; ++index) {
        if (!internal->sidecars[index].occupied) {
            return &internal->sidecars[index];
        }
    }
    return NULL;
}

static bool remove_sidecar(
    modem_executor_internal_t *internal,
    const char operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY])
{
    modem_executor_sidecar_t *sidecar = find_sidecar(internal, operation_id);
    if (sidecar == NULL) {
        return false;
    }
    (void)memset(sidecar, 0, sizeof(*sidecar));
    return true;
}

static size_t append_literal(char *destination, size_t capacity, size_t offset,
                             const char *literal)
{
    size_t index = 0U;
    while (literal[index] != '\0') {
        if (offset >= capacity - 1U) {
            return capacity;
        }
        destination[offset] = literal[index];
        ++offset;
        ++index;
    }
    return offset;
}

static size_t append_u64(char *destination, size_t capacity, size_t offset,
                         uint64_t value)
{
    char reversed[20];
    size_t digits = 0U;
    do {
        reversed[digits] = (char)('0' + (value % UINT64_C(10)));
        value /= UINT64_C(10);
        ++digits;
    } while (value != UINT64_C(0));
    if (digits > capacity - 1U - offset) {
        return capacity;
    }
    while (digits > 0U) {
        --digits;
        destination[offset] = reversed[digits];
        ++offset;
    }
    return offset;
}

static const char *kind_prefix(egolink_modem_command_kind_t kind)
{
    switch (kind) {
    case EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT: return "sos";
    case EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT: return "location";
    case EGOLINK_MODEM_COMMAND_GNSS_ACQUIRE: return "gnss";
    case EGOLINK_MODEM_COMMAND_GNSS_STATUS: return "gnss-status";
    case EGOLINK_MODEM_COMMAND_CELL_OBSERVE: return "cell";
    case EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE:
        return "sos-gnss";
    case EGOLINK_MODEM_COMMAND_NONE:
    case EGOLINK_MODEM_COMMAND_COUNT:
    default:
        return "invalid";
    }
}

static bool generate_operation_id(
    modem_executor_internal_t *internal,
    egolink_modem_command_kind_t kind,
    char output[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY])
{
    if (internal->next_attempt == UINT64_MAX) {
        return false;
    }
    const uint64_t attempt = internal->next_attempt;
    size_t offset = 0U;
    (void)memset(output, 0, EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY);
    offset = append_literal(output,
                            EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY,
                            offset, "o:");
    offset = append_literal(output,
                            EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY,
                            offset, kind_prefix(kind));
    offset = append_literal(output,
                            EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY,
                            offset, ":");
    offset = append_u64(output,
                        EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY,
                        offset, attempt);
    if (offset >= EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY) {
        return false;
    }
    output[offset] = '\0';
    ++internal->next_attempt;
    increment_saturated(&internal->generated_attempts);
    return true;
}

static bool expected_route_for_kind(egolink_modem_command_kind_t kind,
                                    egolink_p0_outbox_route_t *route)
{
    if (kind == EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT) {
        *route = EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS;
        return true;
    }
    if (kind == EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT) {
        *route = EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE;
        return true;
    }
    return false;
}

static egolink_modem_command_kind_t kind_for_route(
    egolink_p0_outbox_route_t route)
{
    if (route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS) {
        return EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT;
    }
    if (route == EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE) {
        return EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT;
    }
    return EGOLINK_MODEM_COMMAND_NONE;
}

static void reconcile_enqueue_removals(
    modem_executor_internal_t *internal,
    const egolink_modem_arbiter_enqueue_result_t *arbiter_result)
{
    if (arbiter_result->queued_location_displaced ||
        arbiter_result->queued_location_replaced_for_urgent) {
        if (!remove_sidecar(
                internal, arbiter_result->displaced_queued_operation_id)) {
            latch_recovery(internal);
        }
        /* Only the transient attempt was displaced; retry the durable view. */
        internal->deferred_location_transport = true;
    }
    if (arbiter_result->queued_sensor_coalesced) {
        modem_executor_sidecar_t *coalesced = find_sidecar(
            internal, arbiter_result->coalesced_queued_operation_id);
        if (coalesced == NULL ||
            coalesced->kind != arbiter_result->coalesced_queued_kind) {
            latch_recovery(internal);
        } else {
            if (coalesced->kind == EGOLINK_MODEM_COMMAND_CELL_OBSERVE) {
                /* Urgent GNSS supersedes only the transient queue token. */
                defer_cell_observe(internal, coalesced->timeout_ms);
            }
            (void)memset(coalesced, 0, sizeof(*coalesced));
        }
    }
    if (arbiter_result->prepared_location_preempted ||
        arbiter_result->prepared_sensor_preempted) {
        if (internal->phase != EGOLINK_MODEM_EXECUTOR_PHASE_EXECUTION_READY ||
            !same_id(internal->active_ticket.operation_id,
                     arbiter_result->preempted_prepared_operation_id)) {
            latch_recovery(internal);
            return;
        }
        if (internal->active_ticket.kind ==
            EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE) {
            internal->urgent_gnss_outstanding = false;
        } else if (internal->active_ticket.kind ==
                   EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT) {
            internal->deferred_location_transport = true;
        }
        (void)memset(&internal->active_ticket, 0,
                     sizeof(internal->active_ticket));
        internal->active_timeout_ms = UINT64_C(0);
        internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_IDLE;
    }
}

static egolink_modem_executor_status_t enqueue_command(
    modem_executor_internal_t *internal,
    egolink_modem_command_kind_t kind,
    uint64_t timeout_ms,
    egolink_location_modem_enqueue_result_t *result)
{
    initialize_enqueue_result(result, kind);
    if (result == NULL || kind <= EGOLINK_MODEM_COMMAND_NONE ||
        kind >= EGOLINK_MODEM_COMMAND_COUNT ||
        (!transport_kind(kind) && !valid_timeout(timeout_ms))) {
        if (result != NULL) {
            result->status = EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
        }
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    result->command_requested = true;

    modem_executor_sidecar_t *slot = free_sidecar(internal);
    if (slot == NULL &&
        kind != EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT &&
        kind != EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE) {
        increment_saturated(&internal->queue_failures);
        result->status = EGOLINK_MODEM_EXECUTOR_QUEUE_PARTIAL;
        result->arbiter_status = EGOLINK_MODEM_ARBITER_QUEUE_FULL;
        return result->status;
    }

    char operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
    if (!generate_operation_id(internal, kind, operation_id)) {
        latch_recovery(internal);
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    const egolink_modem_arbiter_request_t request = {
        .kind = kind,
        .priority = priority_for_kind(kind),
        .operation_id = {
            .data = operation_id,
            .length = strlen(operation_id),
        },
    };
    result->arbiter_status = egolink_modem_arbiter_enqueue(
        &internal->arbiter, &request, &result->arbiter_result);
    reconcile_enqueue_removals(internal, &result->arbiter_result);
    if (internal->lifecycle == EGOLINK_MODEM_EXECUTOR_RECOVERY_REQUIRED) {
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    if (result->arbiter_status != EGOLINK_MODEM_ARBITER_QUEUED ||
        !result->arbiter_result.admitted) {
        increment_saturated(&internal->queue_failures);
        result->status = EGOLINK_MODEM_EXECUTOR_QUEUE_PARTIAL;
        return result->status;
    }

    slot = free_sidecar(internal);
    if (slot == NULL) {
        /* N admitted an attempt that O cannot describe: fail closed. */
        latch_recovery(internal);
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    (void)memset(slot, 0, sizeof(*slot));
    slot->occupied = true;
    slot->kind = kind;
    slot->timeout_ms = timeout_ms;
    (void)memcpy(slot->operation_id, operation_id, strlen(operation_id) + 1U);
    if (kind == EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE) {
        internal->urgent_gnss_outstanding = true;
    } else if (kind == EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT) {
        internal->sos_transport_outstanding = true;
    }
    increment_saturated(&internal->queued_commands);
    result->admitted = true;
    result->status = EGOLINK_MODEM_EXECUTOR_QUEUED;
    return result->status;
}

static void clear_active_result(modem_executor_internal_t *internal)
{
    internal->active_callback_called = false;
    internal->active_callback_contract_valid = false;
    internal->active_cancel_before_callback = false;
    internal->active_callback_outcome =
        EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
    internal->active_completion_time_ms = UINT64_C(0);
    (void)memset(&internal->active_gnss_report, 0,
                 sizeof(internal->active_gnss_report));
    (void)memset(&internal->active_lte_report, 0,
                 sizeof(internal->active_lte_report));
    internal->active_p0_status = EGOLINK_P0_DELIVERY_OK;
    (void)memset(&internal->active_p0_result, 0,
                 sizeof(internal->active_p0_result));
}

static void release_active(modem_executor_internal_t *internal)
{
    if (internal->active_ticket.kind ==
        EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE) {
        internal->urgent_gnss_outstanding = false;
    } else if (internal->active_ticket.kind ==
               EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT) {
        internal->sos_transport_outstanding = false;
    }
    (void)memset(&internal->active_ticket, 0,
                 sizeof(internal->active_ticket));
    internal->active_timeout_ms = UINT64_C(0);
    clear_active_result(internal);
    internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_IDLE;
}

void egolink_location_modem_executor_default_config(
    egolink_location_modem_executor_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->enabled = false;
        config->default_gnss_status_timeout_ms =
            EGOLINK_LOCATION_MODEM_EXECUTOR_DEFAULT_STATUS_TIMEOUT_MS;
    }
}

egolink_modem_executor_status_t egolink_location_modem_executor_init(
    egolink_location_modem_executor_t *executor,
    const egolink_location_modem_executor_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter,
    egolink_p0_delivery_runtime_t *delivery_runtime)
{
    if (executor == NULL || config == NULL) {
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    const bool enabled = config->enabled;
    (void)memset(executor, 0, sizeof(*executor));
    modem_executor_internal_t *internal = internal_of(executor);
    internal->magic = MODEM_EXECUTOR_MAGIC;
    internal->lifecycle = EGOLINK_MODEM_EXECUTOR_DISABLED;
    internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_IDLE;
    internal->next_attempt = UINT64_C(1);
    internal->default_gnss_status_timeout_ms =
        config->default_gnss_status_timeout_ms;
    if (!enabled) {
        return EGOLINK_MODEM_EXECUTOR_DISABLED_STATUS;
    }
    if (shared_outbox == NULL || location_adapter == NULL ||
        delivery_runtime == NULL ||
        !valid_timeout(config->default_gnss_status_timeout_ms)) {
        (void)memset(executor, 0, sizeof(*executor));
        return EGOLINK_MODEM_EXECUTOR_INVALID_CONFIG;
    }

    egolink_p0_delivery_runtime_snapshot_t delivery_snapshot;
    const egolink_p0_delivery_runtime_status_t delivery_status =
        egolink_p0_delivery_runtime_current_status(
            delivery_runtime, &delivery_snapshot);
    if (delivery_status != EGOLINK_P0_DELIVERY_OK ||
        delivery_snapshot.lifecycle != EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE ||
        delivery_snapshot.phase != EGOLINK_P0_DELIVERY_PHASE_IDLE ||
        !delivery_snapshot.enabled || delivery_snapshot.busy ||
        delivery_snapshot.active_route != EGOLINK_P0_OUTBOX_ROUTE_NONE) {
        (void)memset(executor, 0, sizeof(*executor));
        return EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
    }
    if (!egolink_p0_delivery_runtime_dependencies_match(
            delivery_runtime, shared_outbox, location_adapter)) {
        (void)memset(executor, 0, sizeof(*executor));
        return EGOLINK_MODEM_EXECUTOR_DEPENDENCY_MISMATCH;
    }

    egolink_modem_arbiter_config_t arbiter_config;
    egolink_modem_arbiter_default_config(&arbiter_config);
    arbiter_config.enabled = true;
    if (egolink_modem_arbiter_init(&internal->arbiter, &arbiter_config) !=
        EGOLINK_MODEM_ARBITER_OK) {
        (void)memset(executor, 0, sizeof(*executor));
        return EGOLINK_MODEM_EXECUTOR_INVALID_CONFIG;
    }

    egolink_device_location_runtime_config_t device_config;
    egolink_device_location_runtime_default_config(&device_config);
    device_config.enabled = true;
    device_config.pipeline_owner = config->pipeline_owner;
    /* Every K callback intentionally stays NULL: queued is not succeeded. */
    const egolink_device_location_runtime_status_t device_status =
        egolink_device_location_runtime_init(
            &internal->device_runtime, &device_config,
            shared_outbox, location_adapter);
    if (device_status != EGOLINK_DEVICE_LOCATION_RUNTIME_OK) {
        (void)memset(executor, 0, sizeof(*executor));
        return device_status ==
                EGOLINK_DEVICE_LOCATION_RUNTIME_DEPENDENCY_MISMATCH
            ? EGOLINK_MODEM_EXECUTOR_DEPENDENCY_MISMATCH
            : EGOLINK_MODEM_EXECUTOR_INVALID_CONFIG;
    }

    internal->shared_outbox = shared_outbox;
    internal->location_adapter = location_adapter;
    internal->delivery_runtime = delivery_runtime;
    internal->execute_gnss = config->execute_gnss;
    internal->gnss_context = config->gnss_context;
    internal->execute_cell = config->execute_cell;
    internal->cell_context = config->cell_context;
    internal->lifecycle = EGOLINK_MODEM_EXECUTOR_ACTIVE;
    return EGOLINK_MODEM_EXECUTOR_OK;
}

static void update_process_queue_state(
    egolink_location_modem_process_result_t *result,
    const egolink_location_modem_enqueue_result_t *enqueue_result)
{
    if (!enqueue_result->command_requested) {
        return;
    }
    if (enqueue_result->admitted) {
        result->any_command_queued = true;
    } else {
        result->queue_partial = true;
    }
}

egolink_modem_executor_status_t
egolink_location_modem_executor_process_mapped_input(
    egolink_location_modem_executor_t *executor,
    const egolink_location_hardware_mapped_input_t *mapped,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_location_modem_process_result_t *result)
{
    initialize_process_result(result);
    if (executor == NULL || mapped == NULL || scratch == NULL ||
        result == NULL || mapped->origin <= EGOLINK_LOCATION_HARDWARE_ORIGIN_NONE ||
        mapped->origin >
            EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_NO_FIX_OBSERVED) {
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    modem_executor_internal_t *internal = internal_of(executor);
    const egolink_modem_executor_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_EXECUTOR_OK) {
        result->status = state;
        return state;
    }

    increment_saturated(&internal->process_calls);
    result->device_status = egolink_device_location_runtime_process(
        &internal->device_runtime, &mapped->input, outbox_now_ms,
        scratch, &result->device_result);
    result->input_committed = result->device_result.new_input_committed;
    result->k_partial_failure_preserved =
        result->device_status ==
        EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE;

    if (result->device_status ==
            EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT) {
        result->status = EGOLINK_MODEM_EXECUTOR_OK;
        return result->status;
    }
    if (result->device_status != EGOLINK_DEVICE_LOCATION_RUNTIME_OK &&
        result->device_status !=
            EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE) {
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    if (!result->device_result.new_input_committed) {
        latch_recovery(internal);
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }

    increment_saturated(&internal->committed_inputs);
    const egolink_location_runtime_result_t *pipeline =
        &result->device_result.pipeline_result;
    if (pipeline->policy_evaluated) {
        const egolink_location_policy_decision_t *decision =
            &pipeline->policy_decision;
        if (decision->gnss_action ==
            EGOLINK_LOCATION_POLICY_GNSS_ACTION_START) {
            const bool sos_mode = decision->policy_mode ==
                EGOLINK_LOCATION_POLICY_SOS;
            if (sos_mode) {
                result->sos_urgent_requires_durable_sos = true;
            }
            if (!internal->urgent_gnss_outstanding) {
                (void)enqueue_command(
                    internal, EGOLINK_MODEM_COMMAND_GNSS_ACQUIRE,
                    decision->gnss_acquisition_timeout_ms, &result->gnss);
            }
        } else if (decision->gnss_action ==
                   EGOLINK_LOCATION_POLICY_GNSS_ACTION_STOP_TIMEOUT) {
            /* The current synchronous modem API has no safe stop operation. */
            result->unsupported_gnss_stop = true;
        }
        if (decision->cell_observe_now) {
            (void)enqueue_command(
                internal, EGOLINK_MODEM_COMMAND_CELL_OBSERVE,
                decision->cell_request_timeout_ms, &result->cell);
            if (result->cell.admitted) {
                internal->deferred_cell_observe = false;
                internal->deferred_cell_timeout_ms = UINT64_C(0);
            } else if (internal->lifecycle == EGOLINK_MODEM_EXECUTOR_ACTIVE) {
                defer_cell_observe(
                    internal, decision->cell_request_timeout_ms);
                result->cell.followup_scan_deferred = true;
            }
        }
    }
    if (pipeline->published) {
        (void)enqueue_command(
            internal, EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT,
            UINT64_C(0), &result->location_transport);
        if (!result->location_transport.admitted) {
            /* The durable envelope already exists; retain one selector retry. */
            internal->deferred_location_transport = true;
        }
    }

    update_process_queue_state(result, &result->gnss);
    update_process_queue_state(result, &result->cell);
    update_process_queue_state(result, &result->location_transport);
    if (internal->lifecycle == EGOLINK_MODEM_EXECUTOR_RECOVERY_REQUIRED) {
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
    } else if (result->queue_partial) {
        result->status =
            EGOLINK_MODEM_EXECUTOR_INPUT_COMMITTED_QUEUE_PARTIAL;
    } else {
        result->status = EGOLINK_MODEM_EXECUTOR_INPUT_COMMITTED;
    }
    return result->status;
}

egolink_modem_executor_status_t
egolink_location_modem_executor_signal_durable_sos(
    egolink_location_modem_executor_t *executor,
    egolink_modem_durable_sos_evidence_t evidence,
    uint64_t urgent_gnss_timeout_ms,
    egolink_location_modem_enqueue_result_t *sos_transport,
    egolink_location_modem_enqueue_result_t *urgent_gnss)
{
    initialize_enqueue_result(
        sos_transport, EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT);
    initialize_enqueue_result(
        urgent_gnss, EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE);
    if (executor == NULL || sos_transport == NULL || urgent_gnss == NULL ||
        evidence != EGOLINK_MODEM_DURABLE_SOS_COMMITTED_OR_DUPLICATE ||
        !valid_timeout(urgent_gnss_timeout_ms)) {
        if (sos_transport != NULL) {
            sos_transport->status = EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
        }
        if (urgent_gnss != NULL) {
            urgent_gnss->status = EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
        }
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    modem_executor_internal_t *internal = internal_of(executor);
    const egolink_modem_executor_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_EXECUTOR_OK) {
        sos_transport->status = state;
        urgent_gnss->status = state;
        return state;
    }

    /* This lock-free P0 seam is called first; enqueue is never an ACK. */
    sos_transport->delivery_preemption_signalled = true;
    sos_transport->delivery_preempt_status =
        egolink_p0_delivery_runtime_signal_durable_sos(
            internal->delivery_runtime);
    if (internal->sos_transport_outstanding) {
        sos_transport->command_requested = true;
        sos_transport->already_outstanding = true;
        sos_transport->followup_scan_deferred = true;
        sos_transport->status = EGOLINK_MODEM_EXECUTOR_ALREADY_OUTSTANDING;
        /* One bounded follow-up selector pass covers repeated/new SOS records. */
        internal->deferred_sos_transport = true;
    } else {
        (void)enqueue_command(
            internal, EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT,
            UINT64_C(0), sos_transport);
    }
    if (internal->lifecycle != EGOLINK_MODEM_EXECUTOR_ACTIVE) {
        urgent_gnss->status =
            EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        return EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
    }
    if (internal->urgent_gnss_outstanding) {
        urgent_gnss->command_requested = true;
        urgent_gnss->already_outstanding = true;
        urgent_gnss->status = EGOLINK_MODEM_EXECUTOR_ALREADY_OUTSTANDING;
    } else {
        (void)enqueue_command(
            internal, EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE,
            urgent_gnss_timeout_ms, urgent_gnss);
    }

    if ((sos_transport->admitted || sos_transport->already_outstanding) &&
        (urgent_gnss->admitted || urgent_gnss->already_outstanding)) {
        return EGOLINK_MODEM_EXECUTOR_QUEUED;
    }
    return EGOLINK_MODEM_EXECUTOR_QUEUE_PARTIAL;
}

egolink_modem_executor_status_t
egolink_location_modem_executor_request_gnss_status(
    egolink_location_modem_executor_t *executor,
    uint64_t timeout_ms,
    egolink_location_modem_enqueue_result_t *result)
{
    initialize_enqueue_result(result, EGOLINK_MODEM_COMMAND_GNSS_STATUS);
    if (executor == NULL || result == NULL) {
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    modem_executor_internal_t *internal = internal_of(executor);
    const egolink_modem_executor_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_EXECUTOR_OK) {
        result->status = state;
        return state;
    }
    const uint64_t effective_timeout = timeout_ms == UINT64_C(0)
        ? internal->default_gnss_status_timeout_ms
        : timeout_ms;
    return enqueue_command(
        internal, EGOLINK_MODEM_COMMAND_GNSS_STATUS,
        effective_timeout, result);
}

static egolink_location_engine_text_t engine_text_from_runtime(
    egolink_location_runtime_text_t value)
{
    const egolink_location_engine_text_t converted = {
        .data = value.data,
        .length = value.length,
    };
    return converted;
}

static void build_durable_sos_input(
    const egolink_location_runtime_identity_t *identity,
    egolink_location_runtime_input_t *input)
{
    (void)memset(input, 0, sizeof(*input));
    input->identity = *identity;
    input->publish_intent = EGOLINK_LOCATION_RUNTIME_PUBLISH_NONE;
    input->observation.type = EGOLINK_LOCATION_ENGINE_EVENT_SOS;
    input->observation.event_time_ms = identity->event_time_ms;
    input->observation.sos_active_present = true;
    input->observation.sos_active = true;

    egolink_location_engine_lineage_t *lineage =
        &input->observation.lineage;
    lineage->present = true;
    lineage->observation_id =
        engine_text_from_runtime(identity->observation_id);
    lineage->source_status =
        EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED;
    lineage->stream_id_present = true;
    lineage->stream_id = engine_text_from_runtime(identity->stream_id);
    lineage->sequence_id_present = true;
    lineage->sequence_id = identity->sequence_id;
    lineage->device_run_id_present = true;
    lineage->device_run_id = engine_text_from_runtime(identity->session_id);
    lineage->boot_count_present = true;
    lineage->boot_count = identity->boot_count;
    lineage->outer_evidence_source_status_present = true;
    lineage->outer_evidence_source_status =
        EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED;

    switch (identity->event_time_source) {
    case EGOLINK_LOCATION_TIME_GNSS_SOURCE_UTC_NS:
        lineage->gnss_source_utc_ns_present = true;
        lineage->gnss_source_utc_ns = identity->event_time_ns;
        break;
    case EGOLINK_LOCATION_TIME_TIMESTAMP_UTC_NS:
        lineage->timestamp_utc_ns_present = true;
        lineage->timestamp_utc_ns = identity->event_time_ns;
        break;
    case EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS:
        lineage->timestamp_monotonic_ns_present = true;
        lineage->timestamp_monotonic_ns = identity->event_time_ns;
        lineage->monotonic_clock_domain_id_present = true;
        lineage->monotonic_clock_domain_id =
            engine_text_from_runtime(identity->monotonic_clock_domain_id);
        break;
    default:
        /* K rejects an invalid clock without suppressing the two SOS signals. */
        break;
    }
}

static bool usable_sos_preemption_signal(
    egolink_p0_delivery_sos_preempt_status_t status)
{
    switch (status) {
    case EGOLINK_P0_DELIVERY_SOS_PREEMPT_REQUESTED:
    case EGOLINK_P0_DELIVERY_SOS_PREEMPT_ALREADY_REQUESTED:
    case EGOLINK_P0_DELIVERY_SOS_PREEMPT_RESULT_ALREADY_READY:
    case EGOLINK_P0_DELIVERY_SOS_PREEMPT_NO_ACTIVE_LOCATION:
    case EGOLINK_P0_DELIVERY_SOS_PREEMPT_ROUTE_NOT_CANCELLABLE:
        return true;
    case EGOLINK_P0_DELIVERY_SOS_PREEMPT_RECOVERY_REQUIRED:
    case EGOLINK_P0_DELIVERY_SOS_PREEMPT_INVALID_ARGUMENT:
    case EGOLINK_P0_DELIVERY_SOS_PREEMPT_NOT_INITIALIZED:
    default:
        return false;
    }
}

static bool admitted_or_outstanding(
    const egolink_location_modem_enqueue_result_t *result)
{
    return result->admitted || result->already_outstanding;
}

egolink_modem_executor_status_t
egolink_location_modem_executor_process_durable_sos(
    egolink_location_modem_executor_t *executor,
    const egolink_location_runtime_identity_t *location_identity,
    egolink_modem_durable_sos_evidence_t evidence,
    uint64_t urgent_gnss_timeout_ms,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_location_modem_durable_sos_result_t *result)
{
    initialize_durable_sos_result(result);
    if (executor == NULL || location_identity == NULL || scratch == NULL ||
        result == NULL ||
        evidence != EGOLINK_MODEM_DURABLE_SOS_COMMITTED_OR_DUPLICATE ||
        !valid_timeout(urgent_gnss_timeout_ms)) {
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    modem_executor_internal_t *internal = internal_of(executor);
    const egolink_modem_executor_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_EXECUTOR_OK) {
        result->status = state;
        result->location_status =
            state == EGOLINK_MODEM_EXECUTOR_DISABLED_STATUS
                ? EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED_STATUS
                : EGOLINK_DEVICE_LOCATION_RUNTIME_NOT_INITIALIZED;
        result->signal_status = state;
        result->sos_transport.status = state;
        result->urgent_gnss.status = state;
        result->location_transport.status = state;
        result->cell.status = state;
        return state;
    }
    if (internal->phase != EGOLINK_MODEM_EXECUTOR_PHASE_IDLE) {
        result->status = EGOLINK_MODEM_EXECUTOR_IN_FLIGHT;
        result->signal_status = EGOLINK_MODEM_EXECUTOR_IN_FLIGHT;
        result->sos_transport.status = EGOLINK_MODEM_EXECUTOR_IN_FLIGHT;
        result->urgent_gnss.status = EGOLINK_MODEM_EXECUTOR_IN_FLIGHT;
        result->location_transport.status = EGOLINK_MODEM_EXECUTOR_IN_FLIGHT;
        result->cell.status = EGOLINK_MODEM_EXECUTOR_IN_FLIGHT;
        return result->status;
    }

    result->durable_evidence_accepted = true;
    /*
     * Signal the already-durable safety truth first. K is still called below
     * if either transient admission is partial; the branches do not gate one
     * another. The old signal-only API remains the execution-time preemptor.
     */
    result->signal_status =
        egolink_location_modem_executor_signal_durable_sos(
            executor, evidence, urgent_gnss_timeout_ms,
            &result->sos_transport, &result->urgent_gnss);
    result->manual_sos_transport_signal_satisfied =
        admitted_or_outstanding(&result->sos_transport) &&
        result->sos_transport.delivery_preemption_signalled &&
        usable_sos_preemption_signal(
            result->sos_transport.delivery_preempt_status);
    result->urgent_gnss_signal_satisfied =
        admitted_or_outstanding(&result->urgent_gnss);

    result->location_input_attempted = true;
    egolink_location_runtime_input_t input;
    build_durable_sos_input(location_identity, &input);
    increment_saturated(&internal->process_calls);
    result->location_status = egolink_device_location_runtime_process(
        &internal->device_runtime, &input, outbox_now_ms, scratch,
        &result->location_result);
    result->location_input_committed =
        result->location_result.new_input_committed;
    result->location_input_duplicate =
        result->location_status ==
        EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT;
    result->location_envelope_enqueued_now =
        result->location_result.durable_envelope_present;
    result->location_action_partial_failure_preserved =
        result->location_status ==
        EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE;
    result->location_branch_satisfied =
        result->location_input_duplicate ||
        ((result->location_status == EGOLINK_DEVICE_LOCATION_RUNTIME_OK ||
          result->location_action_partial_failure_preserved) &&
         result->location_input_committed &&
         result->location_result.pipeline_result.published &&
         result->location_envelope_enqueued_now);
    if (result->location_input_committed) {
        increment_saturated(&internal->committed_inputs);
    }

    const egolink_location_runtime_result_t *pipeline =
        &result->location_result.pipeline_result;
    result->policy_decision_available = pipeline->policy_evaluated;
    if (result->policy_decision_available) {
        const egolink_location_policy_decision_t *decision =
            &pipeline->policy_decision;
        result->policy_gnss_start_covered_by_urgent =
            decision->gnss_action ==
                EGOLINK_LOCATION_POLICY_GNSS_ACTION_START &&
            result->urgent_gnss_signal_satisfied;
        result->policy_gnss_stop_requires_product_owner =
            decision->gnss_action ==
            EGOLINK_LOCATION_POLICY_GNSS_ACTION_STOP_TIMEOUT;
        result->policy_cell_observe_requested = decision->cell_observe_now;
        /* K callbacks are intentionally NULL; the product owner applies both. */
        result->policy_imu_rate_requires_product_owner = true;
        result->policy_lte_keep_connected_requires_product_owner = true;
        result->policy_ego_call_requires_product_owner =
            decision->start_ego_call_now;
        result->policy_upload_transport_owned_by_executor =
            pipeline->published;
        if (result->policy_cell_observe_requested &&
            internal->lifecycle == EGOLINK_MODEM_EXECUTOR_ACTIVE) {
            (void)enqueue_command(
                internal, EGOLINK_MODEM_COMMAND_CELL_OBSERVE,
                decision->cell_request_timeout_ms, &result->cell);
            result->policy_cell_attempt_satisfied = result->cell.admitted;
            if (result->policy_cell_attempt_satisfied) {
                /* One fresh observation covers any coalesced pending request. */
                internal->deferred_cell_observe = false;
                internal->deferred_cell_timeout_ms = UINT64_C(0);
            } else {
                defer_cell_observe(
                    internal, decision->cell_request_timeout_ms);
                result->cell.followup_scan_deferred = true;
            }
        }
    } else if (result->location_input_duplicate &&
               internal->deferred_cell_observe) {
        /*
         * A K duplicate carries no policy decision. Retry the Cell branch
         * from its original partial attempt instead of upgrading the replay.
         */
        result->policy_cell_observe_requested = true;
        (void)enqueue_command(
            internal, EGOLINK_MODEM_COMMAND_CELL_OBSERVE,
            internal->deferred_cell_timeout_ms, &result->cell);
        result->policy_cell_attempt_satisfied = result->cell.admitted;
        if (result->policy_cell_attempt_satisfied) {
            internal->deferred_cell_observe = false;
            internal->deferred_cell_timeout_ms = UINT64_C(0);
        } else if (internal->lifecycle == EGOLINK_MODEM_EXECUTOR_ACTIVE) {
            result->cell.followup_scan_deferred = true;
        }
    }

    if (result->location_input_committed &&
        result->location_envelope_enqueued_now &&
        internal->lifecycle == EGOLINK_MODEM_EXECUTOR_ACTIVE) {
        (void)enqueue_command(
            internal, EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT,
            UINT64_C(0), &result->location_transport);
        if (!result->location_transport.admitted) {
            /* The Location envelope is durable; retain exactly one retry bit. */
            internal->deferred_location_transport = true;
            result->location_transport.followup_scan_deferred = true;
        }
    } else if (result->location_input_duplicate &&
               internal->deferred_location_transport) {
        /* A K duplicate is not proof that the prior envelope is still queued. */
        result->location_transport.followup_scan_deferred = true;
    }

    const bool location_kick_partial =
        (result->location_input_committed &&
         result->location_envelope_enqueued_now &&
         !result->location_transport.admitted) ||
        (result->location_input_duplicate &&
         result->location_transport.followup_scan_deferred);
    const bool cell_partial =
        result->policy_cell_observe_requested &&
        !result->policy_cell_attempt_satisfied;
    result->partial_failure =
        !result->location_branch_satisfied ||
        !result->manual_sos_transport_signal_satisfied ||
        !result->urgent_gnss_signal_satisfied || location_kick_partial ||
        cell_partial;
    if (internal->lifecycle == EGOLINK_MODEM_EXECUTOR_RECOVERY_REQUIRED) {
        result->status =
            EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
    } else {
        result->status = result->partial_failure
            ? EGOLINK_MODEM_EXECUTOR_DURABLE_SOS_PARTIAL
            : EGOLINK_MODEM_EXECUTOR_DURABLE_SOS_ACCEPTED;
    }
    return result->status;
}

static egolink_modem_executor_status_t requeue_one_deferred(
    modem_executor_internal_t *internal,
    egolink_location_modem_prepare_result_t *result)
{
    egolink_modem_command_kind_t kind = EGOLINK_MODEM_COMMAND_NONE;
    if (internal->deferred_sos_transport &&
        !internal->sos_transport_outstanding) {
        kind = EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT;
    } else if (internal->deferred_location_transport) {
        kind = EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT;
    } else if (internal->deferred_cell_observe) {
        kind = EGOLINK_MODEM_COMMAND_CELL_OBSERVE;
    } else {
        return EGOLINK_MODEM_EXECUTOR_OK;
    }
    const uint64_t timeout_ms = kind == EGOLINK_MODEM_COMMAND_CELL_OBSERVE
        ? internal->deferred_cell_timeout_ms
        : UINT64_C(0);
    (void)enqueue_command(
        internal, kind, timeout_ms, &result->actual_route_requeue);
    if (!result->actual_route_requeue.admitted) {
        if (internal->lifecycle ==
            EGOLINK_MODEM_EXECUTOR_RECOVERY_REQUIRED) {
            result->status =
                EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
            return result->status;
        }
        /* Preserve the deferred bit and drain one existing token first. */
        return EGOLINK_MODEM_EXECUTOR_OK;
    }
    if (kind == EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT) {
        internal->deferred_sos_transport = false;
    } else if (kind == EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT) {
        internal->deferred_location_transport = false;
    } else {
        internal->deferred_cell_observe = false;
        internal->deferred_cell_timeout_ms = UINT64_C(0);
    }
    result->status = EGOLINK_MODEM_EXECUTOR_ROUTE_REQUEUED;
    return result->status;
}

egolink_modem_executor_status_t
egolink_location_modem_executor_prepare_next(
    egolink_location_modem_executor_t *executor,
    uint64_t now_ms,
    egolink_location_modem_prepare_result_t *result)
{
    initialize_prepare_result(result);
    if (executor == NULL || result == NULL) {
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    modem_executor_internal_t *internal = internal_of(executor);
    const egolink_modem_executor_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_EXECUTOR_OK) {
        result->status = state;
        return state;
    }
    if (internal->phase != EGOLINK_MODEM_EXECUTOR_PHASE_IDLE) {
        result->status = EGOLINK_MODEM_EXECUTOR_IN_FLIGHT;
        return result->status;
    }
    const egolink_modem_executor_status_t deferred =
        requeue_one_deferred(internal, result);
    if (deferred != EGOLINK_MODEM_EXECUTOR_OK) {
        return deferred;
    }

    result->arbiter_status = egolink_modem_arbiter_take_next(
        &internal->arbiter, &result->ticket);
    if (result->arbiter_status == EGOLINK_MODEM_ARBITER_NO_COMMAND) {
        result->status = EGOLINK_MODEM_EXECUTOR_NO_COMMAND;
        return result->status;
    }
    if (result->arbiter_status != EGOLINK_MODEM_ARBITER_PREPARED) {
        if (result->arbiter_status ==
                EGOLINK_MODEM_ARBITER_GENERATION_EXHAUSTED ||
            result->arbiter_status == EGOLINK_MODEM_ARBITER_FAULT_LATCHED) {
            latch_recovery(internal);
            result->status =
                EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        } else {
            result->status = EGOLINK_MODEM_EXECUTOR_INVALID_PHASE;
        }
        return result->status;
    }

    modem_executor_sidecar_t *sidecar = find_sidecar(
        internal, result->ticket.operation_id);
    if (sidecar == NULL || sidecar->kind != result->ticket.kind) {
        (void)egolink_modem_arbiter_cancel_prepared(
            &internal->arbiter, &result->ticket,
            &result->cancelled_ticket);
        latch_recovery(internal);
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    internal->active_ticket = result->ticket;
    internal->active_timeout_ms = sidecar->timeout_ms;
    (void)memset(sidecar, 0, sizeof(*sidecar));
    clear_active_result(internal);
    result->timeout_ms = internal->active_timeout_ms;

    if (!transport_kind(result->ticket.kind)) {
        result->arbiter_status =
            egolink_modem_arbiter_mark_execution_started(
                &internal->arbiter, &result->ticket);
        if (result->arbiter_status !=
            EGOLINK_MODEM_ARBITER_EXECUTION_STARTED) {
            latch_recovery(internal);
            result->status =
                EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
            return result->status;
        }
        internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_EXECUTION_READY;
        result->status = EGOLINK_MODEM_EXECUTOR_PREPARED;
        return result->status;
    }

    egolink_p0_outbox_route_t expected_route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
    (void)expected_route_for_kind(result->ticket.kind, &expected_route);
    result->p0_prepare_called = true;
    result->p0_status = egolink_p0_delivery_runtime_prepare(
        internal->delivery_runtime, now_ms, &result->p0_result);
    if (result->p0_status == EGOLINK_P0_DELIVERY_NO_DUE_RECORD ||
        result->p0_status == EGOLINK_P0_DELIVERY_INVALID_EVENT_RETAINED) {
        result->arbiter_status = egolink_modem_arbiter_cancel_prepared(
            &internal->arbiter, &result->ticket,
            &result->cancelled_ticket);
        result->prepared_ticket_cancelled_without_execution =
            result->arbiter_status == EGOLINK_MODEM_ARBITER_COMPLETED;
        release_active(internal);
        result->status = result->p0_status ==
                EGOLINK_P0_DELIVERY_NO_DUE_RECORD
            ? EGOLINK_MODEM_EXECUTOR_DELIVERY_NO_DUE_RECORD
            : EGOLINK_MODEM_EXECUTOR_DELIVERY_RETAINED;
        return result->status;
    }
    if (result->p0_status != EGOLINK_P0_DELIVERY_PREPARED &&
        result->p0_status !=
            EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY) {
        (void)egolink_modem_arbiter_cancel_prepared(
            &internal->arbiter, &result->ticket,
            &result->cancelled_ticket);
        release_active(internal);
        latch_recovery(internal);
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    internal->p0_delivery_prepared = true;
    internal->p0_prepared_route = result->p0_result.route;
    if (result->p0_result.route != expected_route) {
        const egolink_modem_command_kind_t actual_kind =
            kind_for_route(result->p0_result.route);
        result->route_mismatch = true;
        if (actual_kind == EGOLINK_MODEM_COMMAND_NONE) {
            latch_recovery(internal);
            result->status =
                EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
            return result->status;
        }
        char replacement_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
        if (!generate_operation_id(internal, actual_kind, replacement_id)) {
            latch_recovery(internal);
            result->status =
                EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
            return result->status;
        }
        const egolink_modem_arbiter_request_t replacement = {
            .kind = actual_kind,
            .priority = priority_for_kind(actual_kind),
            .operation_id = {
                .data = replacement_id,
                .length = strlen(replacement_id),
            },
        };
        result->arbiter_status = egolink_modem_arbiter_retarget_prepared(
            &internal->arbiter, &result->ticket, &replacement,
            &result->actual_route_ticket, &result->cancelled_ticket);
        if (result->arbiter_status != EGOLINK_MODEM_ARBITER_PREPARED) {
            latch_recovery(internal);
            result->status =
                EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
            return result->status;
        }
        result->prepared_ticket_cancelled_without_execution = true;
        result->prepared_ticket_retargeted = true;
        if (result->ticket.kind ==
            EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT) {
            internal->deferred_sos_transport = true;
            internal->sos_transport_outstanding = false;
        } else {
            internal->deferred_location_transport = true;
        }
        internal->active_ticket = result->actual_route_ticket;
        result->ticket = result->actual_route_ticket;
        internal->active_timeout_ms = UINT64_C(0);
        if (actual_kind == EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT) {
            internal->sos_transport_outstanding = true;
        }
        result->arbiter_status =
            egolink_modem_arbiter_mark_execution_started(
                &internal->arbiter, &result->ticket);
        if (result->arbiter_status !=
            EGOLINK_MODEM_ARBITER_EXECUTION_STARTED) {
            latch_recovery(internal);
            result->status =
                EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
            return result->status;
        }
        if (result->p0_status ==
            EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY) {
            internal->active_p0_status = result->p0_status;
            internal->active_p0_result = result->p0_result;
            internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_RESULT_READY;
            result->status = EGOLINK_MODEM_EXECUTOR_RESULT_READY;
        } else {
            internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_EXECUTION_READY;
            result->status = EGOLINK_MODEM_EXECUTOR_PREPARED;
        }
        return result->status;
    }

    result->arbiter_status = egolink_modem_arbiter_mark_execution_started(
        &internal->arbiter, &result->ticket);
    if (result->arbiter_status !=
        EGOLINK_MODEM_ARBITER_EXECUTION_STARTED) {
        latch_recovery(internal);
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
        return result->status;
    }
    if (result->p0_status == EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY) {
        internal->active_p0_status = result->p0_status;
        internal->active_p0_result = result->p0_result;
        internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_RESULT_READY;
        result->status = EGOLINK_MODEM_EXECUTOR_RESULT_READY;
    } else {
        internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_EXECUTION_READY;
        result->status = EGOLINK_MODEM_EXECUTOR_PREPARED;
    }
    return result->status;
}

static bool completion_time_within_bound(uint64_t begin_time_ms,
                                         uint64_t completion_time_ms,
                                         uint64_t timeout_ms)
{
    return completion_time_ms >= begin_time_ms &&
        completion_time_ms - begin_time_ms <= timeout_ms;
}

egolink_modem_executor_status_t
egolink_location_modem_executor_execute_prepared(
    egolink_location_modem_executor_t *executor,
    uint64_t begin_time_ms,
    egolink_location_modem_execute_result_t *result)
{
    initialize_execute_result(result);
    if (executor == NULL || result == NULL) {
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    modem_executor_internal_t *internal = internal_of(executor);
    const egolink_modem_executor_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_EXECUTOR_OK) {
        result->status = state;
        return state;
    }
    result->kind = internal->active_ticket.kind;
    if (internal->phase == EGOLINK_MODEM_EXECUTOR_PHASE_RESULT_READY) {
        result->status = EGOLINK_MODEM_EXECUTOR_RESULT_READY;
        result->callback_called = internal->active_callback_called;
        result->callback_contract_valid =
            internal->active_callback_contract_valid;
        result->cancel_observed_before_callback =
            internal->active_cancel_before_callback;
        result->callback_outcome = internal->active_callback_outcome;
        result->completion_time_ms = internal->active_completion_time_ms;
        result->p0_status = internal->active_p0_status;
        result->p0_result = internal->active_p0_result;
        return result->status;
    }
    if (internal->phase != EGOLINK_MODEM_EXECUTOR_PHASE_EXECUTION_READY) {
        result->status = EGOLINK_MODEM_EXECUTOR_INVALID_PHASE;
        return result->status;
    }

    clear_active_result(internal);
    if (transport_kind(internal->active_ticket.kind)) {
        internal->active_p0_status =
            egolink_p0_delivery_runtime_execute_prepared(
                internal->delivery_runtime, &internal->active_p0_result);
        result->p0_status = internal->active_p0_status;
        result->p0_result = internal->active_p0_result;
        result->callback_called = internal->active_p0_result.post_called;
        internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_RESULT_READY;
        result->status = EGOLINK_MODEM_EXECUTOR_RESULT_READY;
        return result->status;
    }

    const egolink_modem_command_kind_t kind = internal->active_ticket.kind;
    const bool cancel_before = egolink_modem_arbiter_cancel_requested(
        &internal->arbiter, internal->active_ticket.generation, kind);
    internal->active_cancel_before_callback = cancel_before;
    if (cancel_before) {
        internal->active_callback_outcome =
            EGOLINK_MODEM_CALLBACK_COOPERATIVE_CANCELLED;
        internal->active_callback_contract_valid = true;
        internal->active_completion_time_ms = begin_time_ms;
    } else {
        const egolink_location_modem_sensor_request_t request = {
            .kind = kind,
            .generation = internal->active_ticket.generation,
            .begin_time_ms = begin_time_ms,
            .timeout_ms = internal->active_timeout_ms,
            .cancellation_safe_point =
                EGOLINK_MODEM_SAFE_POINT_BETWEEN_AT_COMMANDS,
            .hard_cancel_supported = false,
            .cancel_requested = egolink_modem_arbiter_cancel_requested,
            .cancel_context = &internal->arbiter,
        };
        egolink_modem_callback_outcome_t outcome =
            EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
        uint64_t completion_time_ms = UINT64_C(0);
        if (gnss_kind(kind)) {
            if (internal->execute_gnss == NULL) {
                internal->active_callback_contract_valid = true;
            } else {
                internal->active_callback_called = true;
                increment_saturated(&internal->callback_calls);
                outcome = internal->execute_gnss(
                    internal->gnss_context, &request,
                    &internal->active_gnss_report, &completion_time_ms);
            }
        } else if (kind == EGOLINK_MODEM_COMMAND_CELL_OBSERVE) {
            if (internal->execute_cell == NULL) {
                internal->active_callback_contract_valid = true;
            } else {
                internal->active_callback_called = true;
                increment_saturated(&internal->callback_calls);
                outcome = internal->execute_cell(
                    internal->cell_context, &request,
                    &internal->active_lte_report, &completion_time_ms);
            }
        } else {
            outcome = EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
        }
        internal->active_callback_outcome = outcome;
        internal->active_completion_time_ms = completion_time_ms;
        if (!internal->active_callback_called) {
            internal->active_callback_outcome =
                EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
        } else if (!valid_callback_outcome(outcome)) {
            internal->active_callback_contract_valid = false;
        } else if (outcome == EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE) {
            internal->active_callback_contract_valid =
                completion_time_within_bound(
                    begin_time_ms, completion_time_ms,
                    internal->active_timeout_ms);
        } else if (outcome ==
                   EGOLINK_MODEM_CALLBACK_COOPERATIVE_CANCELLED) {
            internal->active_callback_contract_valid =
                egolink_modem_arbiter_cancel_requested(
                    &internal->arbiter,
                    internal->active_ticket.generation, kind);
        } else {
            internal->active_callback_contract_valid = true;
        }
    }
    if (!internal->active_callback_contract_valid) {
        increment_saturated(&internal->callback_contract_failures);
    }
    internal->phase = EGOLINK_MODEM_EXECUTOR_PHASE_RESULT_READY;

    result->callback_called = internal->active_callback_called;
    result->callback_contract_valid =
        internal->active_callback_contract_valid;
    result->cancel_observed_before_callback =
        internal->active_cancel_before_callback;
    result->callback_outcome = internal->active_callback_outcome;
    result->completion_time_ms = internal->active_completion_time_ms;
    if (!internal->active_callback_called && !cancel_before) {
        result->status = EGOLINK_MODEM_EXECUTOR_CALLBACK_NOT_CONFIGURED;
    } else if (!internal->active_callback_contract_valid) {
        result->status = EGOLINK_MODEM_EXECUTOR_CALLBACK_CONTRACT_INVALID;
    } else {
        result->status = EGOLINK_MODEM_EXECUTOR_RESULT_READY;
    }
    return result->status;
}

static egolink_modem_reported_outcome_t transport_reported_outcome(
    const egolink_p0_delivery_runtime_result_t *p0_result)
{
    if (p0_result->durable_sos_preemption_won ||
        p0_result->post_outcome == EGOLINK_P0_DELIVERY_POST_CANCELLED) {
        return EGOLINK_MODEM_REPORTED_COOPERATIVE_CANCELLED;
    }
    if (p0_result->post_outcome ==
            EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE &&
        p0_result->post_contract_valid) {
        /* This means only that an HTTP response was obtained, never ACK. */
        return EGOLINK_MODEM_REPORTED_SUCCEEDED;
    }
    return EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
}

static egolink_location_hardware_map_status_t map_sensor_report(
    modem_executor_internal_t *internal,
    const egolink_location_hardware_identity_t *capture_identity,
    egolink_location_hardware_mapped_input_t *mapped)
{
    if (gnss_kind(internal->active_ticket.kind)) {
        return egolink_location_hardware_map_gnss(
            capture_identity, &internal->active_gnss_report, mapped);
    }
    if (internal->active_ticket.kind ==
        EGOLINK_MODEM_COMMAND_CELL_OBSERVE) {
        const egolink_location_hardware_map_status_t cell_status =
            egolink_location_hardware_map_cell(
                capture_identity, &internal->active_lte_report, mapped);
        if (cell_status != EGOLINK_LOCATION_HARDWARE_MAP_CELL_ID_UNAVAILABLE) {
            return cell_status;
        }
        return egolink_location_hardware_map_lte_state(
            capture_identity, &internal->active_lte_report, mapped);
    }
    return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
}

static bool p0_status_requires_recovery(
    egolink_p0_delivery_runtime_status_t status)
{
    return status == EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED ||
        status == EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED ||
        status == EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED;
}

egolink_modem_executor_status_t
egolink_location_modem_executor_settle_prepared(
    egolink_location_modem_executor_t *executor,
    const egolink_location_hardware_identity_t *capture_identity,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_location_modem_settle_result_t *result)
{
    initialize_settle_result(result);
    if (executor == NULL || result == NULL) {
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    modem_executor_internal_t *internal = internal_of(executor);
    const egolink_modem_executor_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_EXECUTOR_OK) {
        result->status = state;
        return state;
    }
    if (internal->phase != EGOLINK_MODEM_EXECUTOR_PHASE_RESULT_READY) {
        result->status = EGOLINK_MODEM_EXECUTOR_INVALID_PHASE;
        return result->status;
    }
    result->kind = internal->active_ticket.kind;

    egolink_modem_reported_outcome_t reported =
        EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
    bool dependency_recovery = false;
    if (transport_kind(internal->active_ticket.kind)) {
        result->p0_settle_called = true;
        result->p0_status = egolink_p0_delivery_runtime_settle_prepared(
            internal->delivery_runtime, outbox_now_ms, &result->p0_result);
        reported = transport_reported_outcome(&result->p0_result);
        internal->p0_delivery_prepared = false;
        internal->p0_prepared_route = EGOLINK_P0_OUTBOX_ROUTE_NONE;
        dependency_recovery = p0_status_requires_recovery(result->p0_status);
        if (result->p0_result.durable_record_retained) {
            if (internal->active_ticket.kind ==
                EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT) {
                internal->deferred_sos_transport = true;
            } else {
                internal->deferred_location_transport = true;
            }
        }
    } else {
        const bool cancel_won = egolink_modem_arbiter_cancel_requested(
            &internal->arbiter, internal->active_ticket.generation,
            internal->active_ticket.kind);
        if (cancel_won) {
            /* After mark-start, even a late usable report is discarded. */
            reported = EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
        } else if (!internal->active_callback_contract_valid) {
            reported = EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
        } else if (internal->active_callback_outcome ==
                   EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE) {
            reported = EGOLINK_MODEM_REPORTED_DEFINITE_FAILURE;
        } else if (internal->active_callback_outcome ==
                   EGOLINK_MODEM_CALLBACK_COOPERATIVE_CANCELLED) {
            reported = EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
        } else if (internal->active_callback_outcome ==
                   EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE) {
            if (capture_identity == NULL || scratch == NULL) {
                reported = EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
                result->map_status =
                    EGOLINK_LOCATION_HARDWARE_MAP_INVALID_ARGUMENT;
                increment_saturated(&internal->map_failures);
            } else {
                egolink_location_hardware_mapped_input_t mapped;
                (void)memset(&mapped, 0, sizeof(mapped));
                result->report_mapping_attempted = true;
                result->map_status = map_sensor_report(
                    internal, capture_identity, &mapped);
                result->mapped_origin = mapped.origin;
                if (result->map_status !=
                    EGOLINK_LOCATION_HARDWARE_MAP_OK) {
                    increment_saturated(&internal->map_failures);
                    reported = EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
                } else {
                    const egolink_modem_executor_status_t process_status =
                        egolink_location_modem_executor_process_mapped_input(
                            executor, &mapped, outbox_now_ms, scratch,
                            &result->process_result);
                    result->observation_committed =
                        result->process_result.input_committed ||
                        result->process_result.device_status ==
                            EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT;
                    reported = result->observation_committed
                        ? EGOLINK_MODEM_REPORTED_SUCCEEDED
                        : EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
                    if (process_status ==
                        EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED) {
                        dependency_recovery = true;
                    }
                }
            }
        } else {
            reported = EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
        }
    }

    result->reported_outcome = reported;
    result->arbiter_status = egolink_modem_arbiter_complete(
        &internal->arbiter, &internal->active_ticket,
        reported, &result->arbiter_result);
    if (result->arbiter_status != EGOLINK_MODEM_ARBITER_COMPLETED) {
        dependency_recovery = true;
    }
    increment_saturated(&internal->settled_commands);
    release_active(internal);
    if (dependency_recovery) {
        latch_recovery(internal);
        result->status = EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
    } else {
        result->status = EGOLINK_MODEM_EXECUTOR_SETTLED;
    }
    return result->status;
}

egolink_modem_executor_status_t
egolink_location_modem_executor_current_status(
    const egolink_location_modem_executor_t *executor,
    egolink_location_modem_executor_snapshot_t *snapshot)
{
    if (snapshot != NULL) {
        (void)memset(snapshot, 0, sizeof(*snapshot));
    }
    if (executor == NULL || snapshot == NULL) {
        return EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT;
    }
    const modem_executor_internal_t *internal = internal_of_const(executor);
    if (!valid_magic(internal)) {
        return EGOLINK_MODEM_EXECUTOR_NOT_INITIALIZED;
    }
    snapshot->initialized = true;
    snapshot->enabled =
        internal->lifecycle != EGOLINK_MODEM_EXECUTOR_DISABLED;
    snapshot->lifecycle = internal->lifecycle;
    snapshot->phase = internal->phase;
    snapshot->p0_delivery_prepared = internal->p0_delivery_prepared;
    snapshot->p0_prepared_route = internal->p0_prepared_route;
    snapshot->sos_transport_outstanding =
        internal->sos_transport_outstanding;
    snapshot->urgent_gnss_outstanding = internal->urgent_gnss_outstanding;
    snapshot->deferred_sos_transport = internal->deferred_sos_transport;
    snapshot->deferred_location_transport =
        internal->deferred_location_transport;
    snapshot->deferred_cell_observe = internal->deferred_cell_observe;
    snapshot->deferred_cell_timeout_ms =
        internal->deferred_cell_timeout_ms;
    snapshot->generated_attempts = internal->generated_attempts;
    snapshot->process_calls = internal->process_calls;
    snapshot->committed_inputs = internal->committed_inputs;
    snapshot->queued_commands = internal->queued_commands;
    snapshot->queue_failures = internal->queue_failures;
    snapshot->callback_calls = internal->callback_calls;
    snapshot->callback_contract_failures =
        internal->callback_contract_failures;
    snapshot->map_failures = internal->map_failures;
    snapshot->settled_commands = internal->settled_commands;
    const egolink_modem_arbiter_status_t arbiter_status =
        egolink_modem_arbiter_current_status(
            &internal->arbiter, &snapshot->arbiter);
    const egolink_device_location_runtime_status_t device_status =
        egolink_device_location_runtime_current_status(
            &internal->device_runtime, &snapshot->device_runtime);
    if (internal->lifecycle == EGOLINK_MODEM_EXECUTOR_ACTIVE &&
        (arbiter_status != EGOLINK_MODEM_ARBITER_OK ||
         device_status != EGOLINK_DEVICE_LOCATION_RUNTIME_OK)) {
        return EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED;
    }
    return lifecycle_status(internal);
}

const char *egolink_location_modem_executor_status_name(
    egolink_modem_executor_status_t status)
{
    switch (status) {
    case EGOLINK_MODEM_EXECUTOR_OK: return "ok";
    case EGOLINK_MODEM_EXECUTOR_QUEUED: return "queued";
    case EGOLINK_MODEM_EXECUTOR_ALREADY_OUTSTANDING:
        return "already_outstanding";
    case EGOLINK_MODEM_EXECUTOR_QUEUE_PARTIAL: return "queue_partial";
    case EGOLINK_MODEM_EXECUTOR_NO_COMMAND: return "no_command";
    case EGOLINK_MODEM_EXECUTOR_PREPARED: return "prepared";
    case EGOLINK_MODEM_EXECUTOR_ROUTE_REQUEUED: return "route_requeued";
    case EGOLINK_MODEM_EXECUTOR_RESULT_READY: return "result_ready";
    case EGOLINK_MODEM_EXECUTOR_SETTLED: return "settled";
    case EGOLINK_MODEM_EXECUTOR_INPUT_COMMITTED: return "input_committed";
    case EGOLINK_MODEM_EXECUTOR_INPUT_COMMITTED_QUEUE_PARTIAL:
        return "input_committed_queue_partial";
    case EGOLINK_MODEM_EXECUTOR_DURABLE_SOS_ACCEPTED:
        return "durable_sos_accepted";
    case EGOLINK_MODEM_EXECUTOR_DURABLE_SOS_PARTIAL:
        return "durable_sos_partial";
    case EGOLINK_MODEM_EXECUTOR_DELIVERY_NO_DUE_RECORD:
        return "delivery_no_due_record";
    case EGOLINK_MODEM_EXECUTOR_DELIVERY_RETAINED:
        return "delivery_retained";
    case EGOLINK_MODEM_EXECUTOR_MAP_REJECTED: return "map_rejected";
    case EGOLINK_MODEM_EXECUTOR_CALLBACK_NOT_CONFIGURED:
        return "callback_not_configured";
    case EGOLINK_MODEM_EXECUTOR_CALLBACK_CONTRACT_INVALID:
        return "callback_contract_invalid";
    case EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED:
        return "dependency_recovery_required";
    case EGOLINK_MODEM_EXECUTOR_IN_FLIGHT: return "in_flight";
    case EGOLINK_MODEM_EXECUTOR_INVALID_PHASE: return "invalid_phase";
    case EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT: return "invalid_argument";
    case EGOLINK_MODEM_EXECUTOR_INVALID_CONFIG: return "invalid_config";
    case EGOLINK_MODEM_EXECUTOR_DEPENDENCY_MISMATCH:
        return "dependency_mismatch";
    case EGOLINK_MODEM_EXECUTOR_NOT_INITIALIZED: return "not_initialized";
    case EGOLINK_MODEM_EXECUTOR_DISABLED_STATUS: return "disabled";
    default: return "unknown";
    }
}

#include "location_modem_arbiter.h"

#include <limits.h>
#include <stdatomic.h>
#include <string.h>

#define MODEM_ARBITER_MAGIC UINT32_C(0x4D415242)

#define MODEM_ARBITER_CONTROL_STATE_BITS 3U
#define MODEM_ARBITER_CONTROL_STATE_MASK UINT32_C(0x7)
#define MODEM_ARBITER_CONTROL_KIND_BITS 3U
#define MODEM_ARBITER_CONTROL_KIND_MASK UINT32_C(0x7)
#define MODEM_ARBITER_CONTROL_KIND_SHIFT MODEM_ARBITER_CONTROL_STATE_BITS
#define MODEM_ARBITER_CONTROL_GENERATION_SHIFT \
    (MODEM_ARBITER_CONTROL_STATE_BITS + MODEM_ARBITER_CONTROL_KIND_BITS)
#define MODEM_ARBITER_GENERATION_MAX \
    (UINT32_MAX >> MODEM_ARBITER_CONTROL_GENERATION_SHIFT)

typedef enum {
    MODEM_CONTROL_IDLE = 0,
    MODEM_CONTROL_PREPARED,
    MODEM_CONTROL_CANCELLABLE_ACTIVE,
    MODEM_CONTROL_CANCEL_REQUESTED,
    MODEM_CONTROL_NON_LOCATION_ACTIVE,
    MODEM_CONTROL_FAULTED,
} modem_control_state_t;

typedef struct {
    bool occupied;
    egolink_modem_command_kind_t kind;
    egolink_modem_priority_t priority;
    uint64_t order;
    char operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
} modem_arbiter_entry_t;

typedef struct {
    bool occupied;
    egolink_modem_command_kind_t kind;
    egolink_modem_priority_t priority;
    egolink_modem_completion_t completion;
    char operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
} modem_arbiter_recent_t;

typedef struct {
    uint32_t magic;
    egolink_modem_arbiter_lifecycle_t lifecycle;
    modem_arbiter_entry_t queue[EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY];
    size_t queued_count;
    uint64_t next_order;
    modem_arbiter_recent_t recent[EGOLINK_MODEM_ARBITER_RECENT_CAPACITY];
    size_t recent_next;
    modem_arbiter_entry_t flight;
    egolink_modem_arbiter_flight_phase_t flight_phase;
    uint32_t generation;
    atomic_uint transfer_control;
    uint64_t admitted_count;
    uint64_t duplicate_count;
    uint64_t conflict_count;
    uint64_t full_count;
    uint64_t prepared_preemption_count;
    uint64_t cooperative_cancel_request_count;
    uint64_t completion_count;
    uint64_t unknown_completion_count;
    uint64_t stale_operation_count;
} modem_arbiter_internal_t;

_Static_assert(
    sizeof(modem_arbiter_internal_t) <= EGOLINK_MODEM_ARBITER_CONTEXT_BYTES,
    "location modem arbiter context is too small");
_Static_assert(sizeof(unsigned int) == sizeof(uint32_t),
               "location modem arbiter requires a 32-bit unsigned int");
_Static_assert(EGOLINK_MODEM_COMMAND_COUNT <= 8,
               "command kind no longer fits transfer control");
#if ATOMIC_INT_LOCK_FREE != 2
#error "location modem arbiter requires lock-free 32-bit atomic unsigned int"
#endif

static modem_arbiter_internal_t *internal_of(
    egolink_modem_arbiter_t *arbiter)
{
    return (modem_arbiter_internal_t *)(void *)arbiter->opaque;
}

static const modem_arbiter_internal_t *internal_of_const(
    const egolink_modem_arbiter_t *arbiter)
{
    return (const modem_arbiter_internal_t *)(const void *)arbiter->opaque;
}

static bool valid_magic(const modem_arbiter_internal_t *internal)
{
    uint32_t observed_magic = UINT32_C(0);
    if (internal == NULL) {
        return false;
    }
    /* Byte-copying avoids a typed read from a never-initialized opaque object. */
    (void)memcpy(&observed_magic, (const void *)internal,
                 sizeof(observed_magic));
    return observed_magic == MODEM_ARBITER_MAGIC;
}

static void increment_saturated(uint64_t *value)
{
    if (*value != UINT64_MAX) {
        ++(*value);
    }
}

static uint32_t control_value(uint32_t generation,
                              egolink_modem_command_kind_t kind,
                              modem_control_state_t state)
{
    return (generation << MODEM_ARBITER_CONTROL_GENERATION_SHIFT) |
        ((uint32_t)kind << MODEM_ARBITER_CONTROL_KIND_SHIFT) |
        (uint32_t)state;
}

static uint32_t control_generation(uint32_t control)
{
    return control >> MODEM_ARBITER_CONTROL_GENERATION_SHIFT;
}

static egolink_modem_command_kind_t control_kind(uint32_t control)
{
    return (egolink_modem_command_kind_t)(
        (control >> MODEM_ARBITER_CONTROL_KIND_SHIFT) &
        MODEM_ARBITER_CONTROL_KIND_MASK);
}

static modem_control_state_t control_state(uint32_t control)
{
    return (modem_control_state_t)(
        control & MODEM_ARBITER_CONTROL_STATE_MASK);
}

static void publish_control(modem_arbiter_internal_t *internal,
                            modem_control_state_t state)
{
    const egolink_modem_command_kind_t kind =
        state == MODEM_CONTROL_IDLE || state == MODEM_CONTROL_FAULTED
            ? EGOLINK_MODEM_COMMAND_NONE
            : internal->flight.kind;
    atomic_store_explicit(
        &internal->transfer_control,
        control_value(internal->generation, kind, state),
        memory_order_release);
}

static bool valid_kind(egolink_modem_command_kind_t kind)
{
    return kind > EGOLINK_MODEM_COMMAND_NONE &&
        kind < EGOLINK_MODEM_COMMAND_COUNT;
}

static bool valid_priority(egolink_modem_priority_t priority)
{
    return priority >= EGOLINK_MODEM_PRIORITY_NORMAL &&
        priority < EGOLINK_MODEM_PRIORITY_COUNT;
}

static bool valid_pairing(egolink_modem_command_kind_t kind,
                          egolink_modem_priority_t priority)
{
    if (!valid_kind(kind) || !valid_priority(priority)) {
        return false;
    }
    if (kind == EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT) {
        return priority == EGOLINK_MODEM_PRIORITY_CRITICAL;
    }
    if (kind == EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE) {
        return priority == EGOLINK_MODEM_PRIORITY_URGENT;
    }
    return priority == EGOLINK_MODEM_PRIORITY_NORMAL;
}

static bool operation_id_char_allowed(char value)
{
    return (value >= 'a' && value <= 'z') ||
        (value >= 'A' && value <= 'Z') ||
        (value >= '0' && value <= '9') || value == '.' || value == '_' ||
        value == ':' || value == '-';
}

static bool valid_operation_id(egolink_modem_arbiter_text_t value)
{
    if (value.data == NULL || value.length == 0U ||
        value.length > EGOLINK_MODEM_ARBITER_OPERATION_ID_MAX_BYTES) {
        return false;
    }
    for (size_t index = 0U; index < value.length; ++index) {
        if (!operation_id_char_allowed(value.data[index])) {
            return false;
        }
    }
    return true;
}

static void copy_text(char destination[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY],
                      egolink_modem_arbiter_text_t source)
{
    (void)memcpy(destination, source.data, source.length);
    destination[source.length] = '\0';
}

static void copy_id(
    char destination[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY],
    const char source[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY])
{
    (void)memcpy(destination, source,
                 EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY);
    destination[EGOLINK_MODEM_ARBITER_OPERATION_ID_MAX_BYTES] = '\0';
}

static bool stored_id_matches(
    const char stored[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY],
    egolink_modem_arbiter_text_t candidate)
{
    const size_t stored_length = strlen(stored);
    return stored_length == candidate.length &&
        memcmp(stored, candidate.data, candidate.length) == 0;
}

static bool ticket_id_valid(
    const char operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY])
{
    const char *terminator = (const char *)memchr(
        operation_id, '\0', EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY);
    if (terminator == NULL) {
        return false;
    }
    const size_t length = (size_t)(terminator - operation_id);
    const egolink_modem_arbiter_text_t view = {
        .data = operation_id,
        .length = length,
    };
    return valid_operation_id(view);
}

static void copy_validated_ticket_id(
    char destination[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY],
    const char source[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY])
{
    const char *terminator = (const char *)memchr(
        source, '\0', EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY);
    const size_t length = terminator == NULL
        ? 0U
        : (size_t)(terminator - source);
    (void)memset(destination, 0,
                 EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY);
    if (length > 0U) {
        (void)memcpy(destination, source, length);
    }
}

static bool entry_metadata_matches(
    const modem_arbiter_entry_t *entry,
    const egolink_modem_arbiter_request_t *request)
{
    return entry->kind == request->kind &&
        entry->priority == request->priority;
}

static bool recent_metadata_matches(
    const modem_arbiter_recent_t *entry,
    const egolink_modem_arbiter_request_t *request)
{
    return entry->kind == request->kind &&
        entry->priority == request->priority;
}

static void initialize_enqueue_result(
    egolink_modem_arbiter_enqueue_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    result->duplicate_scope = EGOLINK_MODEM_DUPLICATE_NONE;
    result->coalesce_reason = EGOLINK_MODEM_COALESCE_NONE;
    result->coalesced_queued_kind = EGOLINK_MODEM_COMMAND_NONE;
}

static void initialize_ticket(egolink_modem_arbiter_ticket_t *ticket)
{
    if (ticket != NULL) {
        (void)memset(ticket, 0, sizeof(*ticket));
    }
}

static void initialize_completion_result(
    egolink_modem_arbiter_completion_result_t *result)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->status = EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    result->reported_outcome = EGOLINK_MODEM_REPORTED_NOT_EXECUTED;
    result->completion = EGOLINK_MODEM_COMPLETION_NONE;
}

static egolink_modem_arbiter_status_t lifecycle_status(
    const modem_arbiter_internal_t *internal)
{
    if (!valid_magic(internal)) {
        return EGOLINK_MODEM_ARBITER_NOT_INITIALIZED;
    }
    if (internal->lifecycle == EGOLINK_MODEM_ARBITER_DISABLED) {
        return EGOLINK_MODEM_ARBITER_DISABLED_STATUS;
    }
    if (internal->lifecycle == EGOLINK_MODEM_ARBITER_FAULTED) {
        return EGOLINK_MODEM_ARBITER_FAULT_LATCHED;
    }
    if (internal->lifecycle != EGOLINK_MODEM_ARBITER_ACTIVE) {
        return EGOLINK_MODEM_ARBITER_NOT_INITIALIZED;
    }
    return EGOLINK_MODEM_ARBITER_OK;
}

static void latch_fault(modem_arbiter_internal_t *internal)
{
    internal->lifecycle = EGOLINK_MODEM_ARBITER_FAULTED;
    publish_control(internal, MODEM_CONTROL_FAULTED);
}

static void remember_completion(
    modem_arbiter_internal_t *internal,
    const modem_arbiter_entry_t *entry,
    egolink_modem_completion_t completion)
{
    modem_arbiter_recent_t *recent = &internal->recent[internal->recent_next];
    (void)memset(recent, 0, sizeof(*recent));
    recent->occupied = true;
    recent->kind = entry->kind;
    recent->priority = entry->priority;
    recent->completion = completion;
    copy_id(recent->operation_id, entry->operation_id);
    internal->recent_next =
        (internal->recent_next + 1U) % EGOLINK_MODEM_ARBITER_RECENT_CAPACITY;
}

static bool normal_sensor_kind(egolink_modem_command_kind_t kind)
{
    return kind == EGOLINK_MODEM_COMMAND_GNSS_ACQUIRE ||
        kind == EGOLINK_MODEM_COMMAND_GNSS_STATUS ||
        kind == EGOLINK_MODEM_COMMAND_CELL_OBSERVE;
}

static size_t noncritical_queued_count(
    const modem_arbiter_internal_t *internal)
{
    size_t count = 0U;
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY; ++index) {
        if (internal->queue[index].occupied &&
            internal->queue[index].priority ==
                EGOLINK_MODEM_PRIORITY_NORMAL) {
            ++count;
        } else if (internal->queue[index].occupied &&
                   internal->queue[index].priority ==
                       EGOLINK_MODEM_PRIORITY_URGENT) {
            ++count;
        }
    }
    return count;
}

static bool any_queued_normal_sensor(
    const modem_arbiter_internal_t *internal)
{
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY; ++index) {
        if (internal->queue[index].occupied &&
            internal->queue[index].priority ==
                EGOLINK_MODEM_PRIORITY_NORMAL &&
            normal_sensor_kind(internal->queue[index].kind)) {
            return true;
        }
    }
    return false;
}

static bool any_queued_location(const modem_arbiter_internal_t *internal)
{
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY; ++index) {
        if (internal->queue[index].occupied &&
            internal->queue[index].kind ==
                EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT) {
            return true;
        }
    }
    return false;
}

static size_t first_free_index(const modem_arbiter_internal_t *internal)
{
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY; ++index) {
        if (!internal->queue[index].occupied) {
            return index;
        }
    }
    return EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY;
}

static size_t newest_queued_location_index(
    const modem_arbiter_internal_t *internal)
{
    size_t selected = EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY;
    uint64_t newest_order = UINT64_C(0);
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY; ++index) {
        const modem_arbiter_entry_t *entry = &internal->queue[index];
        if (entry->occupied &&
            entry->kind == EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT &&
            (selected == EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY ||
             entry->order > newest_order)) {
            selected = index;
            newest_order = entry->order;
        }
    }
    return selected;
}

static size_t newest_queued_normal_sensor_index(
    const modem_arbiter_internal_t *internal)
{
    size_t selected = EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY;
    uint64_t newest_order = UINT64_C(0);
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY; ++index) {
        const modem_arbiter_entry_t *entry = &internal->queue[index];
        if (entry->occupied &&
            entry->priority == EGOLINK_MODEM_PRIORITY_NORMAL &&
            normal_sensor_kind(entry->kind) &&
            (selected == EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY ||
             entry->order > newest_order)) {
            selected = index;
            newest_order = entry->order;
        }
    }
    return selected;
}

static size_t next_queue_index(const modem_arbiter_internal_t *internal)
{
    size_t selected = EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY;
    uint64_t selected_order = UINT64_MAX;
    egolink_modem_priority_t selected_priority =
        EGOLINK_MODEM_PRIORITY_NORMAL;
    bool found = false;
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY; ++index) {
        const modem_arbiter_entry_t *entry = &internal->queue[index];
        if (!entry->occupied) {
            continue;
        }
        if (!found || entry->priority > selected_priority ||
            (entry->priority == selected_priority &&
             entry->order < selected_order)) {
            selected = index;
            selected_order = entry->order;
            selected_priority = entry->priority;
            found = true;
        }
    }
    return selected;
}

static egolink_modem_arbiter_status_t find_existing_identity(
    modem_arbiter_internal_t *internal,
    const egolink_modem_arbiter_request_t *request,
    egolink_modem_arbiter_enqueue_result_t *result)
{
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY; ++index) {
        const modem_arbiter_entry_t *entry = &internal->queue[index];
        if (entry->occupied &&
            stored_id_matches(entry->operation_id, request->operation_id)) {
            if (entry_metadata_matches(entry, request)) {
                increment_saturated(&internal->duplicate_count);
                result->duplicate_scope = EGOLINK_MODEM_DUPLICATE_QUEUED;
                result->status = EGOLINK_MODEM_ARBITER_DUPLICATE;
                return result->status;
            }
            increment_saturated(&internal->conflict_count);
            result->status = EGOLINK_MODEM_ARBITER_IDENTITY_CONFLICT;
            return result->status;
        }
    }
    if (internal->flight_phase != EGOLINK_MODEM_ARBITER_FLIGHT_IDLE &&
        stored_id_matches(internal->flight.operation_id,
                          request->operation_id)) {
        if (entry_metadata_matches(&internal->flight, request)) {
            increment_saturated(&internal->duplicate_count);
            result->duplicate_scope = EGOLINK_MODEM_DUPLICATE_IN_FLIGHT;
            result->status = EGOLINK_MODEM_ARBITER_DUPLICATE;
            return result->status;
        }
        increment_saturated(&internal->conflict_count);
        result->status = EGOLINK_MODEM_ARBITER_IDENTITY_CONFLICT;
        return result->status;
    }
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_RECENT_CAPACITY; ++index) {
        const modem_arbiter_recent_t *entry = &internal->recent[index];
        if (entry->occupied &&
            stored_id_matches(entry->operation_id, request->operation_id)) {
            if (recent_metadata_matches(entry, request)) {
                increment_saturated(&internal->duplicate_count);
                result->duplicate_scope =
                    EGOLINK_MODEM_DUPLICATE_RECENTLY_COMPLETED;
                result->status = EGOLINK_MODEM_ARBITER_DUPLICATE;
                return result->status;
            }
            increment_saturated(&internal->conflict_count);
            result->status = EGOLINK_MODEM_ARBITER_IDENTITY_CONFLICT;
            return result->status;
        }
    }
    return EGOLINK_MODEM_ARBITER_OK;
}

static void fill_ticket(const modem_arbiter_internal_t *internal,
                        egolink_modem_arbiter_ticket_t *ticket)
{
    ticket->generation = internal->generation;
    ticket->kind = internal->flight.kind;
    ticket->priority = internal->flight.priority;
    copy_id(ticket->operation_id, internal->flight.operation_id);
}

static bool ticket_matches(const modem_arbiter_internal_t *internal,
                           const egolink_modem_arbiter_ticket_t *ticket)
{
    return ticket->generation == internal->generation &&
        ticket->kind == internal->flight.kind &&
        ticket->priority == internal->flight.priority &&
        strcmp(ticket->operation_id, internal->flight.operation_id) == 0;
}

static bool valid_ticket(const egolink_modem_arbiter_ticket_t *ticket)
{
    return ticket != NULL && ticket->generation > 0U &&
        valid_pairing(ticket->kind, ticket->priority) &&
        ticket_id_valid(ticket->operation_id);
}

static bool valid_reported_outcome(egolink_modem_reported_outcome_t outcome)
{
    return outcome >= EGOLINK_MODEM_REPORTED_SUCCEEDED &&
        outcome <= EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN;
}

static bool transport_kind(egolink_modem_command_kind_t kind)
{
    return kind == EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT ||
        kind == EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT;
}

static bool cancellable_flight(const modem_arbiter_entry_t *flight)
{
    return flight->kind == EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT ||
        (flight->priority == EGOLINK_MODEM_PRIORITY_NORMAL &&
         normal_sensor_kind(flight->kind));
}

static bool request_preempts_flight(
    const egolink_modem_arbiter_request_t *request,
    const modem_arbiter_entry_t *flight)
{
    if (request->kind ==
            EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT &&
        flight->kind == EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT) {
        return true;
    }
    return request->kind ==
               EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE &&
        flight->priority == EGOLINK_MODEM_PRIORITY_NORMAL &&
        normal_sensor_kind(flight->kind);
}

void egolink_modem_arbiter_default_config(
    egolink_modem_arbiter_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->enabled = false;
    }
}

egolink_modem_arbiter_status_t egolink_modem_arbiter_init(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_config_t *config)
{
    if (arbiter == NULL || config == NULL) {
        return EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    }

    const bool enabled = config->enabled;
    (void)memset(arbiter, 0, sizeof(*arbiter));
    modem_arbiter_internal_t *internal = internal_of(arbiter);
    internal->magic = MODEM_ARBITER_MAGIC;
    internal->lifecycle = enabled ? EGOLINK_MODEM_ARBITER_ACTIVE
                                  : EGOLINK_MODEM_ARBITER_DISABLED;
    internal->next_order = UINT64_C(1);
    internal->flight_phase = EGOLINK_MODEM_ARBITER_FLIGHT_IDLE;
    atomic_init(&internal->transfer_control,
                control_value(0U, EGOLINK_MODEM_COMMAND_NONE,
                              MODEM_CONTROL_IDLE));
    return enabled ? EGOLINK_MODEM_ARBITER_OK
                   : EGOLINK_MODEM_ARBITER_DISABLED_STATUS;
}

egolink_modem_arbiter_status_t egolink_modem_arbiter_enqueue(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_request_t *request,
    egolink_modem_arbiter_enqueue_result_t *result)
{
    initialize_enqueue_result(result);
    if (arbiter == NULL || request == NULL || result == NULL ||
        !valid_pairing(request->kind, request->priority) ||
        !valid_operation_id(request->operation_id)) {
        return EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    }
    modem_arbiter_internal_t *internal = internal_of(arbiter);
    const egolink_modem_arbiter_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_ARBITER_OK) {
        result->status = state;
        return state;
    }

    result->active_generation =
        internal->flight_phase == EGOLINK_MODEM_ARBITER_FLIGHT_IDLE
            ? 0U
            : internal->generation;
    const egolink_modem_arbiter_status_t existing =
        find_existing_identity(internal, request, result);
    if (existing != EGOLINK_MODEM_ARBITER_OK) {
        return existing;
    }

    const bool critical_sos =
        request->kind == EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT;
    const bool urgent_gnss = request->kind ==
        EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE;
    const bool queued_location_waiting =
        critical_sos && any_queued_location(internal);
    const bool queued_sensor_waiting =
        urgent_gnss && any_queued_normal_sensor(internal);

    size_t target = first_free_index(internal);
    bool displace_location = false;
    bool coalesce_sensor = false;
    bool replace_location_for_urgent = false;
    if (urgent_gnss) {
        const size_t sensor = newest_queued_normal_sensor_index(internal);
        if (sensor != EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY) {
            target = sensor;
            coalesce_sensor = true;
        } else if (noncritical_queued_count(internal) >=
                   (EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY -
                    EGOLINK_MODEM_ARBITER_CRITICAL_RESERVED_SLOTS)) {
            const size_t location = newest_queued_location_index(internal);
            if (location != EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY) {
                target = location;
                replace_location_for_urgent = true;
            }
        }
    }
    if (!critical_sos && !coalesce_sensor &&
        !replace_location_for_urgent &&
        noncritical_queued_count(internal) >=
            (EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY -
             EGOLINK_MODEM_ARBITER_CRITICAL_RESERVED_SLOTS)) {
        increment_saturated(&internal->full_count);
        result->status = EGOLINK_MODEM_ARBITER_NORMAL_CAPACITY_RESERVED;
        return result->status;
    }
    if (target == EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY) {
        if (!critical_sos) {
            increment_saturated(&internal->full_count);
            result->status = EGOLINK_MODEM_ARBITER_QUEUE_FULL;
            return result->status;
        }
        target = newest_queued_location_index(internal);
        if (target == EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY) {
            increment_saturated(&internal->full_count);
            result->status = EGOLINK_MODEM_ARBITER_QUEUE_FULL;
            return result->status;
        }
        displace_location = true;
    }
    /* No queue/recent/count mutation is permitted before this final guard. */
    if (internal->next_order == UINT64_MAX) {
        result->status = EGOLINK_MODEM_ARBITER_ORDER_EXHAUSTED;
        return result->status;
    }
    if (internal->queue[target].occupied) {
        if (displace_location) {
            copy_id(result->displaced_queued_operation_id,
                    internal->queue[target].operation_id);
        } else if (coalesce_sensor) {
            copy_id(result->coalesced_queued_operation_id,
                    internal->queue[target].operation_id);
            result->coalesced_queued_kind = internal->queue[target].kind;
            result->coalesce_reason =
                EGOLINK_MODEM_COALESCE_SOS_URGENT_SUPERSEDES_NORMAL_SENSOR;
        } else if (replace_location_for_urgent) {
            copy_id(result->displaced_queued_operation_id,
                    internal->queue[target].operation_id);
            result->coalesce_reason =
                EGOLINK_MODEM_COALESCE_SOS_URGENT_REPLACES_NORMAL_LOCATION_FOR_RESERVE;
        } else {
            latch_fault(internal);
            result->status = EGOLINK_MODEM_ARBITER_FAULT_LATCHED;
            return result->status;
        }
        /* This closes only a volatile attempt; it never ACKs its outbox event. */
        remember_completion(internal, &internal->queue[target],
                            EGOLINK_MODEM_COMPLETION_CANCELLED_BEFORE_EXECUTION);
        (void)memset(&internal->queue[target], 0,
                     sizeof(internal->queue[target]));
        --internal->queued_count;
        result->queued_location_displaced = displace_location;
        result->queued_location_replaced_for_urgent =
            replace_location_for_urgent;
        result->queued_sensor_coalesced = coalesce_sensor;
    }
    modem_arbiter_entry_t *entry = &internal->queue[target];
    (void)memset(entry, 0, sizeof(*entry));
    entry->occupied = true;
    entry->kind = request->kind;
    entry->priority = request->priority;
    entry->order = internal->next_order;
    ++internal->next_order;
    copy_text(entry->operation_id, request->operation_id);
    ++internal->queued_count;
    increment_saturated(&internal->admitted_count);
    result->admitted = true;
    result->queued_location_bypassed = queued_location_waiting;
    result->queued_sensor_bypassed = queued_sensor_waiting;

    if (request_preempts_flight(request, &internal->flight) &&
        internal->flight_phase == EGOLINK_MODEM_ARBITER_FLIGHT_PREPARED &&
        internal->flight.occupied) {
        copy_id(result->preempted_prepared_operation_id,
                internal->flight.operation_id);
        remember_completion(internal, &internal->flight,
                            EGOLINK_MODEM_COMPLETION_CANCELLED_BEFORE_EXECUTION);
        (void)memset(&internal->flight, 0, sizeof(internal->flight));
        internal->flight_phase = EGOLINK_MODEM_ARBITER_FLIGHT_IDLE;
        publish_control(internal, MODEM_CONTROL_IDLE);
        increment_saturated(&internal->prepared_preemption_count);
        result->prepared_location_preempted = critical_sos;
        result->prepared_sensor_preempted = urgent_gnss;
    } else if (
        request_preempts_flight(request, &internal->flight) &&
        internal->flight_phase == EGOLINK_MODEM_ARBITER_FLIGHT_EXECUTING &&
        internal->flight.occupied) {
        unsigned int expected = control_value(
            internal->generation, internal->flight.kind,
            MODEM_CONTROL_CANCELLABLE_ACTIVE);
        const unsigned int requested = control_value(
            internal->generation, internal->flight.kind,
            MODEM_CONTROL_CANCEL_REQUESTED);
        if (atomic_compare_exchange_strong_explicit(
                &internal->transfer_control, &expected, requested,
                memory_order_acq_rel, memory_order_acquire)) {
            increment_saturated(
                &internal->cooperative_cancel_request_count);
            result->cooperative_cancel_requested = true;
        }
    }

    result->status = EGOLINK_MODEM_ARBITER_QUEUED;
    return result->status;
}

egolink_modem_arbiter_status_t egolink_modem_arbiter_take_next(
    egolink_modem_arbiter_t *arbiter,
    egolink_modem_arbiter_ticket_t *ticket)
{
    initialize_ticket(ticket);
    if (arbiter == NULL || ticket == NULL) {
        return EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    }
    modem_arbiter_internal_t *internal = internal_of(arbiter);
    const egolink_modem_arbiter_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_ARBITER_OK) {
        return state;
    }
    if (internal->flight_phase != EGOLINK_MODEM_ARBITER_FLIGHT_IDLE) {
        return EGOLINK_MODEM_ARBITER_IN_FLIGHT;
    }
    if (internal->queued_count == 0U) {
        return EGOLINK_MODEM_ARBITER_NO_COMMAND;
    }
    if (internal->generation >= MODEM_ARBITER_GENERATION_MAX) {
        return EGOLINK_MODEM_ARBITER_GENERATION_EXHAUSTED;
    }
    const size_t selected = next_queue_index(internal);
    if (selected == EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY) {
        latch_fault(internal);
        return EGOLINK_MODEM_ARBITER_FAULT_LATCHED;
    }

    internal->flight = internal->queue[selected];
    (void)memset(&internal->queue[selected], 0,
                 sizeof(internal->queue[selected]));
    --internal->queued_count;
    ++internal->generation;
    internal->flight_phase = EGOLINK_MODEM_ARBITER_FLIGHT_PREPARED;
    publish_control(internal, MODEM_CONTROL_PREPARED);
    fill_ticket(internal, ticket);
    return EGOLINK_MODEM_ARBITER_PREPARED;
}

egolink_modem_arbiter_status_t egolink_modem_arbiter_mark_execution_started(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_ticket_t *ticket)
{
    if (arbiter == NULL || !valid_ticket(ticket)) {
        return EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    }
    modem_arbiter_internal_t *internal = internal_of(arbiter);
    const egolink_modem_arbiter_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_ARBITER_OK) {
        return state;
    }
    if (internal->flight_phase == EGOLINK_MODEM_ARBITER_FLIGHT_IDLE ||
        !ticket_matches(internal, ticket)) {
        increment_saturated(&internal->stale_operation_count);
        return EGOLINK_MODEM_ARBITER_STALE_OPERATION;
    }
    if (internal->flight_phase != EGOLINK_MODEM_ARBITER_FLIGHT_PREPARED) {
        return EGOLINK_MODEM_ARBITER_INVALID_PHASE;
    }

    internal->flight_phase = EGOLINK_MODEM_ARBITER_FLIGHT_EXECUTING;
    publish_control(
        internal,
        cancellable_flight(&internal->flight)
            ? MODEM_CONTROL_CANCELLABLE_ACTIVE
            : MODEM_CONTROL_NON_LOCATION_ACTIVE);
    return EGOLINK_MODEM_ARBITER_EXECUTION_STARTED;
}

egolink_modem_arbiter_status_t egolink_modem_arbiter_cancel_prepared(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_ticket_t *ticket,
    egolink_modem_arbiter_completion_result_t *result)
{
    initialize_completion_result(result);
    if (arbiter == NULL || !valid_ticket(ticket) || result == NULL) {
        return EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    }
    modem_arbiter_internal_t *internal = internal_of(arbiter);
    const egolink_modem_arbiter_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_ARBITER_OK) {
        result->status = state;
        return state;
    }
    result->generation = ticket->generation;
    copy_validated_ticket_id(result->operation_id, ticket->operation_id);
    if (internal->flight_phase == EGOLINK_MODEM_ARBITER_FLIGHT_IDLE ||
        !ticket_matches(internal, ticket)) {
        increment_saturated(&internal->stale_operation_count);
        result->status = EGOLINK_MODEM_ARBITER_STALE_OPERATION;
        return result->status;
    }
    if (internal->flight_phase != EGOLINK_MODEM_ARBITER_FLIGHT_PREPARED) {
        result->status = EGOLINK_MODEM_ARBITER_INVALID_PHASE;
        return result->status;
    }

    result->completion = EGOLINK_MODEM_COMPLETION_CANCELLED_BEFORE_EXECUTION;
    remember_completion(internal, &internal->flight, result->completion);
    (void)memset(&internal->flight, 0, sizeof(internal->flight));
    internal->flight_phase = EGOLINK_MODEM_ARBITER_FLIGHT_IDLE;
    publish_control(internal, MODEM_CONTROL_IDLE);
    increment_saturated(&internal->completion_count);
    result->status = EGOLINK_MODEM_ARBITER_COMPLETED;
    return result->status;
}

egolink_modem_arbiter_status_t egolink_modem_arbiter_retarget_prepared(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_ticket_t *current_ticket,
    const egolink_modem_arbiter_request_t *replacement,
    egolink_modem_arbiter_ticket_t *replacement_ticket,
    egolink_modem_arbiter_completion_result_t *replaced_result)
{
    initialize_ticket(replacement_ticket);
    initialize_completion_result(replaced_result);
    if (arbiter == NULL || !valid_ticket(current_ticket) ||
        replacement == NULL || replacement_ticket == NULL ||
        replaced_result == NULL ||
        !valid_pairing(replacement->kind, replacement->priority) ||
        !valid_operation_id(replacement->operation_id)) {
        return EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    }
    modem_arbiter_internal_t *internal = internal_of(arbiter);
    const egolink_modem_arbiter_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_ARBITER_OK) {
        replaced_result->status = state;
        return state;
    }
    replaced_result->generation = current_ticket->generation;
    copy_validated_ticket_id(
        replaced_result->operation_id, current_ticket->operation_id);
    if (internal->flight_phase == EGOLINK_MODEM_ARBITER_FLIGHT_IDLE ||
        !ticket_matches(internal, current_ticket)) {
        increment_saturated(&internal->stale_operation_count);
        replaced_result->status = EGOLINK_MODEM_ARBITER_STALE_OPERATION;
        return replaced_result->status;
    }
    if (internal->flight_phase != EGOLINK_MODEM_ARBITER_FLIGHT_PREPARED) {
        replaced_result->status = EGOLINK_MODEM_ARBITER_INVALID_PHASE;
        return replaced_result->status;
    }
    egolink_modem_arbiter_enqueue_result_t identity_result;
    initialize_enqueue_result(&identity_result);
    const egolink_modem_arbiter_status_t identity_status =
        find_existing_identity(internal, replacement, &identity_result);
    if (identity_status != EGOLINK_MODEM_ARBITER_OK) {
        replaced_result->status = identity_status;
        return identity_status;
    }
    /* Every fallible guard precedes completion/flight mutation. */
    if (internal->generation >= MODEM_ARBITER_GENERATION_MAX) {
        replaced_result->status =
            EGOLINK_MODEM_ARBITER_GENERATION_EXHAUSTED;
        return replaced_result->status;
    }

    replaced_result->reported_outcome =
        EGOLINK_MODEM_REPORTED_NOT_EXECUTED;
    replaced_result->completion =
        EGOLINK_MODEM_COMPLETION_CANCELLED_BEFORE_EXECUTION;
    remember_completion(internal, &internal->flight,
                        replaced_result->completion);
    increment_saturated(&internal->completion_count);

    internal->flight.kind = replacement->kind;
    internal->flight.priority = replacement->priority;
    copy_text(internal->flight.operation_id, replacement->operation_id);
    ++internal->generation;
    publish_control(internal, MODEM_CONTROL_PREPARED);
    fill_ticket(internal, replacement_ticket);
    replaced_result->status = EGOLINK_MODEM_ARBITER_COMPLETED;
    return EGOLINK_MODEM_ARBITER_PREPARED;
}

bool egolink_modem_arbiter_cancel_requested(
    const egolink_modem_arbiter_t *arbiter,
    uint32_t generation,
    egolink_modem_command_kind_t kind)
{
    if (arbiter == NULL || generation == 0U || !valid_kind(kind)) {
        return false;
    }
    const modem_arbiter_internal_t *internal = internal_of_const(arbiter);
    if (!valid_magic(internal)) {
        return false;
    }
    const unsigned int observed = atomic_load_explicit(
        &internal->transfer_control, memory_order_acquire);
    return control_generation(observed) == generation &&
        control_kind(observed) == kind &&
        control_state(observed) == MODEM_CONTROL_CANCEL_REQUESTED;
}

bool egolink_modem_arbiter_location_cancel_requested(
    const egolink_modem_arbiter_t *arbiter,
    uint32_t generation)
{
    return egolink_modem_arbiter_cancel_requested(
        arbiter, generation, EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT);
}

egolink_modem_arbiter_status_t egolink_modem_arbiter_complete(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_ticket_t *ticket,
    egolink_modem_reported_outcome_t outcome,
    egolink_modem_arbiter_completion_result_t *result)
{
    initialize_completion_result(result);
    if (arbiter == NULL || !valid_ticket(ticket) || result == NULL ||
        !valid_reported_outcome(outcome)) {
        return EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    }
    modem_arbiter_internal_t *internal = internal_of(arbiter);
    const egolink_modem_arbiter_status_t state = lifecycle_status(internal);
    if (state != EGOLINK_MODEM_ARBITER_OK) {
        result->status = state;
        return state;
    }
    result->reported_outcome = outcome;
    result->generation = ticket->generation;
    copy_validated_ticket_id(result->operation_id, ticket->operation_id);
    if (internal->flight_phase == EGOLINK_MODEM_ARBITER_FLIGHT_IDLE ||
        !ticket_matches(internal, ticket)) {
        increment_saturated(&internal->stale_operation_count);
        result->status = EGOLINK_MODEM_ARBITER_STALE_OPERATION;
        return result->status;
    }
    if (internal->flight_phase != EGOLINK_MODEM_ARBITER_FLIGHT_EXECUTING) {
        result->status = EGOLINK_MODEM_ARBITER_INVALID_PHASE;
        return result->status;
    }

    const unsigned int observed = atomic_load_explicit(
        &internal->transfer_control, memory_order_acquire);
    const modem_control_state_t observed_state = control_state(observed);
    const bool generation_matches =
        control_generation(observed) == internal->generation;
    const bool cancel_won =
        generation_matches && control_kind(observed) == internal->flight.kind &&
        observed_state == MODEM_CONTROL_CANCEL_REQUESTED;
    const bool flight_is_cancellable = cancellable_flight(&internal->flight);
    const bool expected_active = generation_matches &&
        control_kind(observed) == internal->flight.kind &&
        ((flight_is_cancellable &&
          (observed_state == MODEM_CONTROL_CANCELLABLE_ACTIVE || cancel_won)) ||
         (!flight_is_cancellable &&
          observed_state == MODEM_CONTROL_NON_LOCATION_ACTIVE));
    if (!expected_active) {
        latch_fault(internal);
        result->status = EGOLINK_MODEM_ARBITER_FAULT_LATCHED;
        return result->status;
    }

    result->cooperative_cancel_won = cancel_won;
    if (cancel_won) {
        result->completion =
            EGOLINK_MODEM_COMPLETION_CANCELLED_AFTER_START;
        result->effect_may_be_unknown = true;
        result->transport_acceptance_may_be_unknown =
            transport_kind(internal->flight.kind);
        result->late_executor_result_discarded = true;
    } else {
        switch (outcome) {
        case EGOLINK_MODEM_REPORTED_SUCCEEDED:
            result->completion = EGOLINK_MODEM_COMPLETION_SUCCEEDED;
            break;
        case EGOLINK_MODEM_REPORTED_DEFINITE_FAILURE:
            result->completion =
                EGOLINK_MODEM_COMPLETION_DEFINITE_FAILURE;
            break;
        case EGOLINK_MODEM_REPORTED_COOPERATIVE_CANCELLED:
            result->completion =
                EGOLINK_MODEM_COMPLETION_CANCELLED_AFTER_START;
            result->effect_may_be_unknown = true;
            result->transport_acceptance_may_be_unknown =
                transport_kind(internal->flight.kind);
            break;
        case EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN:
            result->completion = EGOLINK_MODEM_COMPLETION_OUTCOME_UNKNOWN;
            result->effect_may_be_unknown = true;
            result->transport_acceptance_may_be_unknown =
                transport_kind(internal->flight.kind);
            break;
        case EGOLINK_MODEM_REPORTED_NOT_EXECUTED:
        case EGOLINK_MODEM_REPORTED_OUTCOME_COUNT:
        default:
            latch_fault(internal);
            result->status = EGOLINK_MODEM_ARBITER_FAULT_LATCHED;
            return result->status;
        }
    }

    if (result->effect_may_be_unknown) {
        increment_saturated(&internal->unknown_completion_count);
    }
    remember_completion(internal, &internal->flight, result->completion);
    (void)memset(&internal->flight, 0, sizeof(internal->flight));
    internal->flight_phase = EGOLINK_MODEM_ARBITER_FLIGHT_IDLE;
    publish_control(internal, MODEM_CONTROL_IDLE);
    increment_saturated(&internal->completion_count);
    result->status = EGOLINK_MODEM_ARBITER_COMPLETED;
    return result->status;
}

egolink_modem_arbiter_status_t egolink_modem_arbiter_current_status(
    const egolink_modem_arbiter_t *arbiter,
    egolink_modem_arbiter_snapshot_t *snapshot)
{
    if (snapshot != NULL) {
        (void)memset(snapshot, 0, sizeof(*snapshot));
    }
    if (arbiter == NULL || snapshot == NULL) {
        return EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT;
    }
    const modem_arbiter_internal_t *internal = internal_of_const(arbiter);
    if (!valid_magic(internal)) {
        return EGOLINK_MODEM_ARBITER_NOT_INITIALIZED;
    }

    const unsigned int observed = atomic_load_explicit(
        &internal->transfer_control, memory_order_acquire);
    size_t normal_count = 0U;
    size_t urgent_count = 0U;
    size_t critical_count = 0U;
    for (size_t index = 0U;
         index < EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY; ++index) {
        if (!internal->queue[index].occupied) {
            continue;
        }
        if (internal->queue[index].priority ==
            EGOLINK_MODEM_PRIORITY_CRITICAL) {
            ++critical_count;
        } else if (internal->queue[index].priority ==
                   EGOLINK_MODEM_PRIORITY_URGENT) {
            ++urgent_count;
        } else {
            ++normal_count;
        }
    }
    snapshot->initialized = true;
    snapshot->enabled =
        internal->lifecycle != EGOLINK_MODEM_ARBITER_DISABLED;
    snapshot->lifecycle = internal->lifecycle;
    snapshot->flight_phase = internal->flight_phase;
    snapshot->queued_count = (uint16_t)internal->queued_count;
    snapshot->queued_normal_count = (uint16_t)normal_count;
    snapshot->queued_urgent_count = (uint16_t)urgent_count;
    snapshot->queued_critical_count = (uint16_t)critical_count;
    snapshot->in_flight =
        internal->flight_phase != EGOLINK_MODEM_ARBITER_FLIGHT_IDLE;
    snapshot->cooperative_cancel_requested =
        control_state(observed) == MODEM_CONTROL_CANCEL_REQUESTED;
    snapshot->active_generation = snapshot->in_flight
        ? internal->generation
        : 0U;
    snapshot->active_kind = snapshot->in_flight
        ? internal->flight.kind
        : EGOLINK_MODEM_COMMAND_NONE;
    snapshot->admitted_count = internal->admitted_count;
    snapshot->duplicate_count = internal->duplicate_count;
    snapshot->conflict_count = internal->conflict_count;
    snapshot->full_count = internal->full_count;
    snapshot->prepared_preemption_count =
        internal->prepared_preemption_count;
    snapshot->cooperative_cancel_request_count =
        internal->cooperative_cancel_request_count;
    snapshot->completion_count = internal->completion_count;
    snapshot->unknown_completion_count =
        internal->unknown_completion_count;
    snapshot->stale_operation_count = internal->stale_operation_count;
    if (snapshot->in_flight) {
        copy_id(snapshot->active_operation_id,
                internal->flight.operation_id);
    }

    return lifecycle_status(internal);
}

const char *egolink_modem_arbiter_status_name(
    egolink_modem_arbiter_status_t status)
{
    switch (status) {
    case EGOLINK_MODEM_ARBITER_OK: return "ok";
    case EGOLINK_MODEM_ARBITER_DISABLED_STATUS: return "disabled";
    case EGOLINK_MODEM_ARBITER_QUEUED: return "queued";
    case EGOLINK_MODEM_ARBITER_DUPLICATE: return "duplicate";
    case EGOLINK_MODEM_ARBITER_IDENTITY_CONFLICT:
        return "identity_conflict";
    case EGOLINK_MODEM_ARBITER_NORMAL_CAPACITY_RESERVED:
        return "normal_capacity_reserved";
    case EGOLINK_MODEM_ARBITER_QUEUE_FULL: return "queue_full";
    case EGOLINK_MODEM_ARBITER_NO_COMMAND: return "no_command";
    case EGOLINK_MODEM_ARBITER_IN_FLIGHT: return "in_flight";
    case EGOLINK_MODEM_ARBITER_PREPARED: return "prepared";
    case EGOLINK_MODEM_ARBITER_EXECUTION_STARTED:
        return "execution_started";
    case EGOLINK_MODEM_ARBITER_COMPLETED: return "completed";
    case EGOLINK_MODEM_ARBITER_STALE_OPERATION:
        return "stale_operation";
    case EGOLINK_MODEM_ARBITER_INVALID_PHASE: return "invalid_phase";
    case EGOLINK_MODEM_ARBITER_ORDER_EXHAUSTED:
        return "order_exhausted";
    case EGOLINK_MODEM_ARBITER_GENERATION_EXHAUSTED:
        return "generation_exhausted";
    case EGOLINK_MODEM_ARBITER_FAULT_LATCHED: return "fault_latched";
    case EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_MODEM_ARBITER_INVALID_CONFIG: return "invalid_config";
    case EGOLINK_MODEM_ARBITER_NOT_INITIALIZED:
        return "not_initialized";
    case EGOLINK_MODEM_ARBITER_STATUS_COUNT:
    default:
        return "unknown";
    }
}

const char *egolink_modem_command_kind_name(
    egolink_modem_command_kind_t kind)
{
    switch (kind) {
    case EGOLINK_MODEM_COMMAND_NONE: return "none";
    case EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT:
        return "durable_sos_transport";
    case EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT:
        return "location_transport";
    case EGOLINK_MODEM_COMMAND_GNSS_ACQUIRE: return "gnss_acquire";
    case EGOLINK_MODEM_COMMAND_GNSS_STATUS: return "gnss_status";
    case EGOLINK_MODEM_COMMAND_CELL_OBSERVE: return "cell_observe";
    case EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE:
        return "sos_urgent_gnss_acquire";
    case EGOLINK_MODEM_COMMAND_COUNT:
    default:
        return "unknown";
    }
}

const char *egolink_modem_completion_name(
    egolink_modem_completion_t completion)
{
    switch (completion) {
    case EGOLINK_MODEM_COMPLETION_NONE: return "none";
    case EGOLINK_MODEM_COMPLETION_SUCCEEDED: return "succeeded";
    case EGOLINK_MODEM_COMPLETION_DEFINITE_FAILURE:
        return "definite_failure";
    case EGOLINK_MODEM_COMPLETION_CANCELLED_BEFORE_EXECUTION:
        return "cancelled_before_execution";
    case EGOLINK_MODEM_COMPLETION_CANCELLED_AFTER_START:
        return "cancelled_after_start";
    case EGOLINK_MODEM_COMPLETION_OUTCOME_UNKNOWN:
        return "outcome_unknown";
    default:
        return "unknown";
    }
}

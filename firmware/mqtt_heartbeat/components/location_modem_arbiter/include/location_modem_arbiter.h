#ifndef EGOLINK_LOCATION_MODEM_ARBITER_H
#define EGOLINK_LOCATION_MODEM_ARBITER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_MODEM_ARBITER_CONTRACT_VERSION \
    "egolink.location_modem_arbiter.v0.1"
#define EGOLINK_MODEM_ARBITER_QUEUE_CAPACITY 8U
#define EGOLINK_MODEM_ARBITER_CRITICAL_RESERVED_SLOTS 1U
#define EGOLINK_MODEM_ARBITER_RECENT_CAPACITY 8U
#define EGOLINK_MODEM_ARBITER_OPERATION_ID_MAX_BYTES 128U
#define EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY 129U
#define EGOLINK_MODEM_ARBITER_CONTEXT_BYTES 4096U

/* Borrowed only for the duration of the API call. */
typedef struct {
    const char *data;
    size_t length;
} egolink_modem_arbiter_text_t;

typedef enum {
    EGOLINK_MODEM_COMMAND_NONE = 0,
    EGOLINK_MODEM_COMMAND_DURABLE_SOS_TRANSPORT,
    EGOLINK_MODEM_COMMAND_LOCATION_TRANSPORT,
    EGOLINK_MODEM_COMMAND_GNSS_ACQUIRE,
    EGOLINK_MODEM_COMMAND_GNSS_STATUS,
    EGOLINK_MODEM_COMMAND_CELL_OBSERVE,
    EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE,
    EGOLINK_MODEM_COMMAND_COUNT,
} egolink_modem_command_kind_t;

typedef enum {
    EGOLINK_MODEM_PRIORITY_NORMAL = 0,
    EGOLINK_MODEM_PRIORITY_URGENT,
    EGOLINK_MODEM_PRIORITY_CRITICAL,
    EGOLINK_MODEM_PRIORITY_COUNT,
} egolink_modem_priority_t;

typedef enum {
    EGOLINK_MODEM_ARBITER_UNINITIALIZED = 0,
    EGOLINK_MODEM_ARBITER_DISABLED,
    EGOLINK_MODEM_ARBITER_ACTIVE,
    EGOLINK_MODEM_ARBITER_FAULTED,
} egolink_modem_arbiter_lifecycle_t;

typedef enum {
    EGOLINK_MODEM_ARBITER_FLIGHT_IDLE = 0,
    EGOLINK_MODEM_ARBITER_FLIGHT_PREPARED,
    EGOLINK_MODEM_ARBITER_FLIGHT_EXECUTING,
} egolink_modem_arbiter_flight_phase_t;

typedef enum {
    EGOLINK_MODEM_ARBITER_OK = 0,
    EGOLINK_MODEM_ARBITER_DISABLED_STATUS,
    EGOLINK_MODEM_ARBITER_QUEUED,
    EGOLINK_MODEM_ARBITER_DUPLICATE,
    EGOLINK_MODEM_ARBITER_IDENTITY_CONFLICT,
    EGOLINK_MODEM_ARBITER_NORMAL_CAPACITY_RESERVED,
    EGOLINK_MODEM_ARBITER_QUEUE_FULL,
    EGOLINK_MODEM_ARBITER_NO_COMMAND,
    EGOLINK_MODEM_ARBITER_IN_FLIGHT,
    EGOLINK_MODEM_ARBITER_PREPARED,
    EGOLINK_MODEM_ARBITER_EXECUTION_STARTED,
    EGOLINK_MODEM_ARBITER_COMPLETED,
    EGOLINK_MODEM_ARBITER_STALE_OPERATION,
    EGOLINK_MODEM_ARBITER_INVALID_PHASE,
    EGOLINK_MODEM_ARBITER_ORDER_EXHAUSTED,
    EGOLINK_MODEM_ARBITER_GENERATION_EXHAUSTED,
    EGOLINK_MODEM_ARBITER_FAULT_LATCHED,
    EGOLINK_MODEM_ARBITER_INVALID_ARGUMENT,
    EGOLINK_MODEM_ARBITER_INVALID_CONFIG,
    EGOLINK_MODEM_ARBITER_NOT_INITIALIZED,
    EGOLINK_MODEM_ARBITER_STATUS_COUNT,
} egolink_modem_arbiter_status_t;

typedef enum {
    EGOLINK_MODEM_DUPLICATE_NONE = 0,
    EGOLINK_MODEM_DUPLICATE_QUEUED,
    EGOLINK_MODEM_DUPLICATE_IN_FLIGHT,
    EGOLINK_MODEM_DUPLICATE_RECENTLY_COMPLETED,
} egolink_modem_duplicate_scope_t;

typedef enum {
    EGOLINK_MODEM_COALESCE_NONE = 0,
    EGOLINK_MODEM_COALESCE_SOS_URGENT_SUPERSEDES_NORMAL_SENSOR,
    EGOLINK_MODEM_COALESCE_SOS_URGENT_REPLACES_NORMAL_LOCATION_FOR_RESERVE,
} egolink_modem_coalesce_reason_t;

typedef enum {
    EGOLINK_MODEM_REPORTED_SUCCEEDED = 0,
    EGOLINK_MODEM_REPORTED_DEFINITE_FAILURE,
    EGOLINK_MODEM_REPORTED_COOPERATIVE_CANCELLED,
    EGOLINK_MODEM_REPORTED_OUTCOME_UNKNOWN,
    EGOLINK_MODEM_REPORTED_NOT_EXECUTED,
    EGOLINK_MODEM_REPORTED_OUTCOME_COUNT,
} egolink_modem_reported_outcome_t;

typedef enum {
    EGOLINK_MODEM_COMPLETION_NONE = 0,
    EGOLINK_MODEM_COMPLETION_SUCCEEDED,
    EGOLINK_MODEM_COMPLETION_DEFINITE_FAILURE,
    EGOLINK_MODEM_COMPLETION_CANCELLED_BEFORE_EXECUTION,
    EGOLINK_MODEM_COMPLETION_CANCELLED_AFTER_START,
    EGOLINK_MODEM_COMPLETION_OUTCOME_UNKNOWN,
} egolink_modem_completion_t;

typedef struct {
    bool enabled;
} egolink_modem_arbiter_config_t;

/*
 * operation_id identifies one execution attempt, not a durable event. A
 * durable retry must use a new operation_id while retaining its outbox event
 * identity outside this component. Only DURABLE_SOS_TRANSPORT may be
 * CRITICAL. SOS_URGENT_GNSS_ACQUIRE is the sole URGENT command and may be
 * submitted only after the corresponding manual-SOS event is durable. Every
 * other current command must be NORMAL.
 */
typedef struct {
    egolink_modem_command_kind_t kind;
    egolink_modem_priority_t priority;
    /* 1..128 ASCII bytes from [A-Za-z0-9._:-]; not a durable event ID. */
    egolink_modem_arbiter_text_t operation_id;
} egolink_modem_arbiter_request_t;

typedef struct {
    egolink_modem_arbiter_status_t status;
    bool admitted;
    bool queued_location_bypassed;
    bool queued_sensor_bypassed;
    bool queued_location_displaced;
    bool queued_location_replaced_for_urgent;
    bool queued_sensor_coalesced;
    bool prepared_location_preempted;
    bool prepared_sensor_preempted;
    bool cooperative_cancel_requested;
    egolink_modem_duplicate_scope_t duplicate_scope;
    egolink_modem_coalesce_reason_t coalesce_reason;
    egolink_modem_command_kind_t coalesced_queued_kind;
    /* Generation observed at entry; zero when no attempt was in flight. */
    uint32_t active_generation;
    char displaced_queued_operation_id[
        EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
    char coalesced_queued_operation_id[
        EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
    char preempted_prepared_operation_id[
        EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
} egolink_modem_arbiter_enqueue_result_t;

/* Owned value; no pointer into arbiter storage is exposed. */
typedef struct {
    uint32_t generation;
    egolink_modem_command_kind_t kind;
    egolink_modem_priority_t priority;
    char operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
} egolink_modem_arbiter_ticket_t;

typedef struct {
    egolink_modem_arbiter_status_t status;
    egolink_modem_reported_outcome_t reported_outcome;
    egolink_modem_completion_t completion;
    uint32_t generation;
    bool cooperative_cancel_won;
    bool late_executor_result_discarded;
    bool effect_may_be_unknown;
    bool transport_acceptance_may_be_unknown;
    char operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
} egolink_modem_arbiter_completion_result_t;

typedef struct {
    bool initialized;
    bool enabled;
    egolink_modem_arbiter_lifecycle_t lifecycle;
    egolink_modem_arbiter_flight_phase_t flight_phase;
    uint16_t queued_count;
    uint16_t queued_normal_count;
    uint16_t queued_urgent_count;
    uint16_t queued_critical_count;
    bool in_flight;
    bool cooperative_cancel_requested;
    uint32_t active_generation;
    egolink_modem_command_kind_t active_kind;
    uint64_t admitted_count;
    uint64_t duplicate_count;
    uint64_t conflict_count;
    uint64_t full_count;
    uint64_t prepared_preemption_count;
    uint64_t cooperative_cancel_request_count;
    uint64_t completion_count;
    uint64_t unknown_completion_count;
    uint64_t stale_operation_count;
    char active_operation_id[EGOLINK_MODEM_ARBITER_OPERATION_ID_CAPACITY];
} egolink_modem_arbiter_snapshot_t;

/* Caller-owned; allocate statically or in other long-lived memory, not stack. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_MODEM_ARBITER_CONTEXT_BYTES];
} egolink_modem_arbiter_t;

void egolink_modem_arbiter_default_config(
    egolink_modem_arbiter_config_t *config);

/*
 * Default configuration is disabled. Enabled state is volatile: this core is
 * not another durable queue and stores no payload, ACK, credential or source
 * event. All ordinary APIs require one external owner/mutex. The owner must
 * not be held while modem execution runs.
 */
egolink_modem_arbiter_status_t egolink_modem_arbiter_init(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_config_t *config);

/*
 * A CRITICAL SOS may be submitted only after its existing outbox record is
 * durably available; this core cannot verify that external fact. It jumps
 * ahead of queued NORMAL work. At capacity it may displace one queued durable
 * Location transport, reported by exact operation identity. It never evicts
 * GNSS/Cell work or another SOS silently.
 *
 * If Location is PREPARED but not marked started, an admitted SOS invalidates
 * that ticket before execution. If Location is EXECUTING, only a cooperative
 * same-generation cancel flag is set. An admitted SOS-urgent GNSS request
 * similarly bypasses NORMAL sensor work, may coalesce one queued NORMAL
 * GNSS/status/Cell token by exact identity, and may cooperatively cancel one
 * PREPARED/EXECUTING NORMAL sensor attempt. If seven NORMAL Location attempts
 * consume the non-CRITICAL allowance, urgent GNSS replaces exactly one newest
 * Location attempt (reported by exact ID and a distinct reason) instead of
 * consuming the reserved CRITICAL slot. The durable Location remains in the
 * outbox; no modem call is force-stopped.
 */
egolink_modem_arbiter_status_t egolink_modem_arbiter_enqueue(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_request_t *request,
    egolink_modem_arbiter_enqueue_result_t *result);

/* Claims at most one command under the external owner; performs no I/O. */
egolink_modem_arbiter_status_t egolink_modem_arbiter_take_next(
    egolink_modem_arbiter_t *arbiter,
    egolink_modem_arbiter_ticket_t *ticket);

/*
 * Call under the owner immediately before releasing it for external
 * execution. From this conservative boundary onward, cancellation may make
 * the operation's effect/remote transport acceptance unknown.
 */
egolink_modem_arbiter_status_t egolink_modem_arbiter_mark_execution_started(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_ticket_t *ticket);

/*
 * Cancels an exact PREPARED attempt before any external execution. This is a
 * volatile attempt completion only; it never settles or deletes an outbox
 * event. The ticket cannot be reused.
 */
egolink_modem_arbiter_status_t egolink_modem_arbiter_cancel_prepared(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_ticket_t *ticket,
    egolink_modem_arbiter_completion_result_t *result);

/*
 * Atomically closes one exact PREPARED hint and installs a fresh PREPARED
 * attempt for an already-borrowed transport route proven by the durable
 * outbox selector. No queue selector or external execution runs. The old
 * attempt is reported NOT_EXECUTED/CANCELLED_BEFORE_EXECUTION, while the new
 * generation plus operation ID prevents either ticket being confused with
 * the other. This never settles, ACKs or deletes the durable event.
 */
egolink_modem_arbiter_status_t egolink_modem_arbiter_retarget_prepared(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_ticket_t *current_ticket,
    const egolink_modem_arbiter_request_t *replacement,
    egolink_modem_arbiter_ticket_t *replacement_ticket,
    egolink_modem_arbiter_completion_result_t *replaced_result);

/* Lock-free read at an executing command's reviewed cooperative safe points. */
bool egolink_modem_arbiter_cancel_requested(
    const egolink_modem_arbiter_t *arbiter,
    uint32_t generation,
    egolink_modem_command_kind_t kind);

/* Backward-compatible Location-named alias of the generic probe. */
bool egolink_modem_arbiter_location_cancel_requested(
    const egolink_modem_arbiter_t *arbiter,
    uint32_t generation);

/*
 * Complete under the external owner after execution returns. Exact generation
 * and operation identity must match. If a permitted cooperative cancellation
 * won after start, a later executor result is not promoted: effect is unknown
 * and transport acceptance is additionally unknown for Location transport.
 * SUCCEEDED here never means a
 * durable outbox ACK or deletion; the existing delivery runtime must settle
 * those independently. DEFINITE_FAILURE may be reported only when the
 * executor can prove there was no external effect/remote acceptance;
 * otherwise it must report OUTCOME_UNKNOWN.
 */
egolink_modem_arbiter_status_t egolink_modem_arbiter_complete(
    egolink_modem_arbiter_t *arbiter,
    const egolink_modem_arbiter_ticket_t *ticket,
    egolink_modem_reported_outcome_t outcome,
    egolink_modem_arbiter_completion_result_t *result);

egolink_modem_arbiter_status_t egolink_modem_arbiter_current_status(
    const egolink_modem_arbiter_t *arbiter,
    egolink_modem_arbiter_snapshot_t *snapshot);

const char *egolink_modem_arbiter_status_name(
    egolink_modem_arbiter_status_t status);
const char *egolink_modem_command_kind_name(
    egolink_modem_command_kind_t kind);
const char *egolink_modem_completion_name(
    egolink_modem_completion_t completion);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_LOCATION_MODEM_ARBITER_H */

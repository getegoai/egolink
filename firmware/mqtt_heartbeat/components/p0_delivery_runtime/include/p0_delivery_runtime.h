#ifndef EGOLINK_P0_DELIVERY_RUNTIME_H
#define EGOLINK_P0_DELIVERY_RUNTIME_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "p0_outbox_dispatcher.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_P0_DELIVERY_RUNTIME_CONTRACT_VERSION \
    "egolink.p0_delivery_runtime.v0.1"
#define EGOLINK_P0_DELIVERY_RUNTIME_CONTEXT_BYTES (12U * 1024U)
#define EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES \
    EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES
#define EGOLINK_P0_DELIVERY_RUNTIME_DEFAULT_MAX_POST_DURATION_MS UINT32_C(30000)
#define EGOLINK_P0_DELIVERY_RUNTIME_MAX_POST_DURATION_MS UINT32_C(120000)

typedef enum {
    EGOLINK_P0_DELIVERY_RUNTIME_NEVER_INITIALIZED = 0,
    EGOLINK_P0_DELIVERY_RUNTIME_DISABLED,
    EGOLINK_P0_DELIVERY_RUNTIME_ACTIVE,
    EGOLINK_P0_DELIVERY_RUNTIME_CANCELLED,
    EGOLINK_P0_DELIVERY_RUNTIME_CLOSED,
} egolink_p0_delivery_runtime_lifecycle_t;

typedef enum {
    EGOLINK_P0_DELIVERY_PHASE_IDLE = 0,
    EGOLINK_P0_DELIVERY_PHASE_DRIVING,
    EGOLINK_P0_DELIVERY_PHASE_FINISH_RECOVERY_REQUIRED,
    EGOLINK_P0_DELIVERY_PHASE_BEGIN_RECOVERY_REQUIRED,
    EGOLINK_P0_DELIVERY_PHASE_DEPENDENCY_RECOVERY_REQUIRED,
    EGOLINK_P0_DELIVERY_PHASE_PREPARED,
    EGOLINK_P0_DELIVERY_PHASE_EXECUTING_PREPARED,
    EGOLINK_P0_DELIVERY_PHASE_TRANSPORT_RESULT_READY,
} egolink_p0_delivery_runtime_phase_t;

typedef enum {
    EGOLINK_P0_DELIVERY_OK = 0,
    EGOLINK_P0_DELIVERY_NO_DUE_RECORD,
    EGOLINK_P0_DELIVERY_ACK_DELETED,
    EGOLINK_P0_DELIVERY_ACK_ALREADY_APPLIED,
    EGOLINK_P0_DELIVERY_ATTEMPT_RETAINED,
    EGOLINK_P0_DELIVERY_INVALID_EVENT_RETAINED,
    EGOLINK_P0_DELIVERY_FINISH_RECOVERY_REQUIRED,
    EGOLINK_P0_DELIVERY_BEGIN_RECOVERY_REQUIRED,
    EGOLINK_P0_DELIVERY_DEPENDENCY_RECOVERY_REQUIRED,
    EGOLINK_P0_DELIVERY_CANCELLED_STATUS,
    EGOLINK_P0_DELIVERY_CLOSED_STATUS,
    EGOLINK_P0_DELIVERY_DISABLED_STATUS,
    EGOLINK_P0_DELIVERY_INVALID_ARGUMENT,
    EGOLINK_P0_DELIVERY_INVALID_CONFIG,
    EGOLINK_P0_DELIVERY_NOT_INITIALIZED,
    EGOLINK_P0_DELIVERY_ALREADY_INITIALIZED,
    EGOLINK_P0_DELIVERY_REENTRANT_CALL,
    EGOLINK_P0_DELIVERY_PREPARED,
    EGOLINK_P0_DELIVERY_TRANSPORT_RESULT_READY,
} egolink_p0_delivery_runtime_status_t;

/*
 * This is the only runtime operation permitted concurrently with
 * execute_prepared. It carries no event identity or payload. The caller may
 * invoke it only after a manual_sos record is durably available in the shared
 * outbox. It can request cooperative cancellation of an active location POST;
 * it never cancels a manual_sos POST and never claims that modem I/O stopped.
 */
typedef enum {
    EGOLINK_P0_DELIVERY_SOS_PREEMPT_REQUESTED = 0,
    EGOLINK_P0_DELIVERY_SOS_PREEMPT_ALREADY_REQUESTED,
    EGOLINK_P0_DELIVERY_SOS_PREEMPT_RESULT_ALREADY_READY,
    EGOLINK_P0_DELIVERY_SOS_PREEMPT_NO_ACTIVE_LOCATION,
    EGOLINK_P0_DELIVERY_SOS_PREEMPT_ROUTE_NOT_CANCELLABLE,
    EGOLINK_P0_DELIVERY_SOS_PREEMPT_RECOVERY_REQUIRED,
    EGOLINK_P0_DELIVERY_SOS_PREEMPT_INVALID_ARGUMENT,
    EGOLINK_P0_DELIVERY_SOS_PREEMPT_NOT_INITIALIZED,
} egolink_p0_delivery_sos_preempt_status_t;

typedef bool (*egolink_p0_delivery_cancel_probe_fn)(
    void *context,
    uint32_t transfer_generation);

typedef enum {
    EGOLINK_P0_DELIVERY_POST_NOT_CALLED = 0,
    EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE,
    EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED,
    EGOLINK_P0_DELIVERY_POST_CANCELLED,
    EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED,
} egolink_p0_delivery_post_outcome_t;

typedef enum {
    EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE = 0,
    EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OFFLINE,
    EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_DNS,
    EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_CONNECT,
    EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TLS,
    EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TIMEOUT,
    EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_IO,
    EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER,
} egolink_p0_delivery_transport_error_t;

/*
 * path is one of the two fixed dispatcher endpoint constants. body borrows
 * the exact persisted outbox bytes and is not NUL-terminated. response points
 * into the runtime's bounded caller-owned opaque object and is valid only for
 * this synchronous callback. No credential, bearer or Guardian token is
 * carried by this contract; a future real HTTP owner must manage credentials
 * outside this component.
 * The callback must not retain request, body or response pointers.
 * It is trusted never to write past response_capacity; C cannot contain an
 * arbitrary callback that violates that memory contract.
 */
typedef struct {
    egolink_p0_outbox_route_t route;
    const char *path;
    const uint8_t *body;
    size_t body_length;
    uint8_t *response;
    size_t response_capacity;
    egolink_outbox_priority_t priority;
    /*
     * Cooperative hint for a location transport. Old callbacks may ignore
     * it. A true result means stop at the next transport-defined safe point;
     * it is not authority to tear down an unrelated modem operation.
     */
    egolink_p0_delivery_cancel_probe_fn cancel_requested;
    void *cancel_context;
    uint32_t transfer_generation;
} egolink_p0_delivery_post_request_t;

/*
 * HTTP_RESPONSE requires status 100..599, error NONE and response_length no
 * greater than request.response_capacity. TRANSPORT_FAILED requires status
 * and length zero plus a non-NONE bounded error enum. CANCELLED and
 * CALLBACK_FAILED require status/length zero and error NONE. The
 * completion_time_ms must not be
 * earlier than the begin time or later than the configured maximum duration.
 * Invalid combinations are converted to a fixed local failure and are never
 * passed through as a successful HTTP result.
 */
typedef struct {
    uint16_t http_status_code;
    size_t response_length;
    uint64_t completion_time_ms;
    egolink_p0_delivery_transport_error_t transport_error;
} egolink_p0_delivery_post_result_t;

typedef egolink_p0_delivery_post_outcome_t
(*egolink_p0_delivery_http_post_fn)(
    void *context,
    const egolink_p0_delivery_post_request_t *request,
    egolink_p0_delivery_post_result_t *result);

typedef struct {
    bool enabled;
    egolink_p0_delivery_http_post_fn http_post;
    void *http_context;
    uint32_t max_post_duration_ms;
} egolink_p0_delivery_runtime_config_t;

/* No response body, payload bytes, coordinates or credentials are exposed. */
typedef struct {
    egolink_p0_delivery_runtime_status_t status;
    egolink_p0_outbox_route_t route;
    egolink_p0_delivery_post_outcome_t post_outcome;
    egolink_p0_delivery_transport_error_t transport_error;
    uint16_t http_status_code;
    size_t response_length;
    bool begin_called;
    bool post_called;
    bool post_contract_valid;
    bool response_oversize;
    bool finish_called;
    bool terminal;
    bool durable_record_retained;
    bool deleted_after_server_durable_ingest_ack;
    bool private_settlement_retained_for_recovery;
    bool prepared_snapshot_available;
    bool execute_prepared_called;
    bool durable_sos_preemption_observed;
    bool durable_sos_preemption_won;
    bool late_transport_result_discarded;
    bool transport_acceptance_may_be_unknown;
    uint32_t transfer_generation;
    egolink_p0_outbox_dispatcher_status_t dispatcher_begin_status;
    egolink_p0_outbox_dispatcher_status_t dispatcher_finish_status;
    egolink_p0_outbox_begin_result_t dispatcher_begin_result;
    egolink_p0_outbox_finish_result_t dispatcher_finish_result;
} egolink_p0_delivery_runtime_result_t;

typedef struct {
    egolink_p0_delivery_runtime_lifecycle_t lifecycle;
    egolink_p0_delivery_runtime_phase_t phase;
    egolink_p0_delivery_runtime_status_t last_status;
    bool enabled;
    bool busy;
    bool dispatcher_bound;
    bool private_settlement_retained_for_recovery;
    bool begin_recovery_pending;
    egolink_p0_outbox_route_t active_route;
    uint64_t drive_calls;
    uint64_t begin_calls;
    uint64_t post_calls;
    uint64_t finish_calls;
    uint64_t explicit_finish_retries;
    uint64_t explicit_begin_recovery_retries;
    uint64_t no_due_records;
    uint64_t retained_attempts;
    uint64_t ack_deletes;
    uint64_t callback_contract_failures;
    uint64_t oversize_responses;
    uint64_t recovery_required;
    uint64_t prepared_calls;
    uint64_t execute_prepared_calls;
    uint64_t settle_prepared_calls;
    uint32_t transfer_generation;
    uint32_t durable_sos_preemption_requests;
    uint32_t durable_sos_preemption_wins;
    uint32_t durable_sos_preemption_too_late;
    bool prepared_snapshot_available;
    bool durable_sos_preemption_requested;
} egolink_p0_delivery_runtime_snapshot_t;

/* Allocate statically or in other long-lived caller-owned memory, not stack. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_P0_DELIVERY_RUNTIME_CONTEXT_BYTES];
} egolink_p0_delivery_runtime_t;

void egolink_p0_delivery_runtime_default_config(
    egolink_p0_delivery_runtime_config_t *config);

/*
 * Enabled init borrows one already-active, idle dispatcher. This runtime then
 * becomes its only begin/finish/cancel/close driver. The callback and all
 * calls are synchronous; no task, retry loop, transport or credential owner
 * is created. The external composition owner must serialize this runtime with
 * every producer and shared-outbox call. The local busy flag is not a lock.
 * The duration contract is checked after the callback returns using its
 * caller-supplied completion time; this component cannot preempt a callback
 * that blocks or violates the synchronous callback contract. A future real
 * transport owner needs its own bounded I/O timeout/cancellation mechanism.
 * The callback also owns the truthfulness of completion_time_ms; the runtime
 * can reject out-of-range reported time but has no independent clock source.
 */
egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_init(
    egolink_p0_delivery_runtime_t *runtime,
    const egolink_p0_delivery_runtime_config_t *config,
    egolink_p0_outbox_dispatcher_t *already_initialized_dispatcher);

/*
 * Split-phase product integration seam.
 *
 * prepare and settle_prepared must run under the external owner/mutex that
 * serializes every shared outbox, adapter and dispatcher API call. prepare
 * performs exactly one dispatcher begin and no POST/finish. That begin has
 * already copied the exact persisted payload into the dispatcher's private
 * canonical send item; the runtime retains the sole borrowed view and does
 * not allocate or make a second 4096-byte payload copy.
 *
 * execute_prepared must run without that shared owner held. It invokes the
 * existing injected callback at most once, never calls the dispatcher,
 * outbox, adapters or storage, and retains the bounded result for a later
 * settle. The callback may poll request.cancel_requested. A callback that
 * ignores the probe or blocks in an AT command cannot be hard-preempted; its
 * own bounded timeout remains mandatory.
 *
 * settle_prepared reacquires the shared owner and performs exactly one
 * dispatcher finish. A location whose cooperative cancellation wins is
 * finished as P0_DELIVERY_CANCELLED and retained for retry. It must not use
 * dispatcher cancel: once the POST callback has been entered, remote
 * acceptance may be unknown and dispatcher cancel is restricted to an
 * unsent SEND_READY attempt. settle never selects the next record. After a
 * retained location is settled, the caller may prepare again and the existing
 * outbox priority selector chooses a due CRITICAL record ahead of NORMAL
 * location traffic.
 */
egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_prepare(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t begin_time_ms,
    egolink_p0_delivery_runtime_result_t *result);

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_execute_prepared(
    egolink_p0_delivery_runtime_t *runtime,
    egolink_p0_delivery_runtime_result_t *result);

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_settle_prepared(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result);

egolink_p0_delivery_sos_preempt_status_t
egolink_p0_delivery_runtime_signal_durable_sos(
    egolink_p0_delivery_runtime_t *runtime);

bool egolink_p0_delivery_runtime_location_cancel_requested(
    void *context,
    uint32_t transfer_generation);

/*
 * Performs at most one dispatcher begin. A READY result invokes the injected
 * POST exactly once with the fixed path and exact bytes, then invokes
 * dispatcher finish exactly once. It never loops or retries implicitly.
 */
egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_drive_once(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t begin_time_ms,
    egolink_p0_delivery_runtime_result_t *result);

/*
 * Only valid after FINISH_RECOVERY_REQUIRED. It replays the private bounded
 * response/outcome into dispatcher finish exactly once, without another
 * selector or POST. External code must first recover the dependency state.
 */
egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_retry_finish(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result);

/*
 * Only valid after BEGIN_RECOVERY_REQUIRED. A dispatcher begin may itself
 * fail while durably classifying an invalid retained head. This retries the
 * one preselected dispatcher's cancel/settlement operation with the exact
 * preserved view. It never invokes begin, POST or dispatcher finish, and a
 * successful retained settlement returns the runtime to ACTIVE/IDLE.
 */
egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_retry_begin_recovery(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result);

/*
 * cancel/close never discard a private recovery settlement or active attempt.
 * They cannot interrupt a synchronous POST callback already on the call stack.
 */
egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_cancel(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result);

egolink_p0_delivery_runtime_status_t egolink_p0_delivery_runtime_close(
    egolink_p0_delivery_runtime_t *runtime,
    uint64_t now_ms,
    egolink_p0_delivery_runtime_result_t *result);

egolink_p0_delivery_runtime_status_t
egolink_p0_delivery_runtime_current_status(
    const egolink_p0_delivery_runtime_t *runtime,
    egolink_p0_delivery_runtime_snapshot_t *snapshot);

/*
 * Read-only transitive proof that this active runtime's dispatcher retains
 * the exact shared outbox and exact Location adapter supplied by a composing
 * owner. It performs no begin/finish, storage or transport operation.
 */
bool egolink_p0_delivery_runtime_dependencies_match(
    const egolink_p0_delivery_runtime_t *runtime,
    const egolink_outbox_t *shared_outbox,
    const egolink_location_outbox_adapter_t *location_adapter);

const char *egolink_p0_delivery_runtime_status_name(
    egolink_p0_delivery_runtime_status_t status);
const char *egolink_p0_delivery_runtime_phase_name(
    egolink_p0_delivery_runtime_phase_t phase);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_P0_DELIVERY_RUNTIME_H */

#ifndef EGOLINK_SOS_DELIVERY_COMPOSITION_H
#define EGOLINK_SOS_DELIVERY_COMPOSITION_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "location_outbox_adapter.h"
#include "location_policy_core.h"
#include "p0_delivery_runtime.h"
#include "sos_device_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_SOS_DELIVERY_COMPOSITION_CONTRACT_VERSION \
    "egolink.sos_delivery_composition.v0.1"
#define EGOLINK_SOS_DELIVERY_COMPOSITION_CONTEXT_BYTES (32U * 1024U)

typedef enum {
    EGOLINK_SOS_DELIVERY_COMPOSITION_NEVER_INITIALIZED = 0,
    EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_ACTIVE,
    EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_REQUIRED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED,
} egolink_sos_delivery_composition_lifecycle_t;

typedef enum {
    EGOLINK_SOS_DELIVERY_COMPOSITION_OK = 0,
    EGOLINK_SOS_DELIVERY_COMPOSITION_NO_EDGE,
    EGOLINK_SOS_DELIVERY_COMPOSITION_PARTIAL_FAILURE,
    EGOLINK_SOS_DELIVERY_COMPOSITION_PENDING_REPLAY_REQUIRED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_NO_PENDING_EDGE,
    EGOLINK_SOS_DELIVERY_COMPOSITION_NO_DUE_RECORD,
    EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_DELETED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_ALREADY_APPLIED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_DELIVERY_RETAINED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS,
    EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS,
    EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS,
    EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_ARGUMENT,
    EGOLINK_SOS_DELIVERY_COMPOSITION_INVALID_CONFIG,
    EGOLINK_SOS_DELIVERY_COMPOSITION_DEPENDENCY_MISMATCH,
    EGOLINK_SOS_DELIVERY_COMPOSITION_INITIALIZATION_FAILED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_ROLLBACK_RECOVERY_REQUIRED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_ALREADY_INITIALIZED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_REENTRANT_CALL,
    EGOLINK_SOS_DELIVERY_COMPOSITION_PREPARED,
    EGOLINK_SOS_DELIVERY_COMPOSITION_TRANSPORT_RESULT_READY,
} egolink_sos_delivery_composition_status_t;

/*
 * The wake callback is deliberately absent. This component installs the only
 * wake callback and converts it to one bounded RAM intent plus saturating
 * metadata. It cannot select, send, or invoke HTTP on the SOS callback stack.
 */
typedef struct {
    bool enabled;
    egolink_sos_input_config_t input;
    const char *device_id;
    uint64_t boot_count;
    const char *session_id;
    uint64_t first_source_sequence;
    egolink_sos_local_feedback_fn local_feedback;
    void *local_feedback_context;
    egolink_sos_location_enqueue_fn request_urgent_location;
    void *location_context;
    egolink_sos_call_request_fn request_call;
    void *call_context;
    egolink_p0_delivery_http_post_fn http_post;
    void *http_context;
    uint32_t max_post_duration_ms;
} egolink_sos_delivery_composition_config_t;

/* No payload, coordinates, media, credentials, or callback data. */
typedef struct {
    egolink_sos_delivery_composition_status_t status;
    bool runtime_called;
    bool external_drive_required;
    bool wake_intent_pending;
    uint64_t wake_intents_observed;
    bool durable_sos_preemption_signalled;
    egolink_p0_delivery_sos_preempt_status_t durable_sos_preemption_status;
    egolink_sos_device_runtime_status_t runtime_status;
    egolink_sos_device_runtime_result_t runtime_result;
} egolink_sos_delivery_composition_event_result_t;

/* No request/response body or attempt identity is exposed here. */
typedef struct {
    egolink_sos_delivery_composition_status_t status;
    bool delivery_called;
    bool recovery_retry_called;
    bool wake_intent_consumed;
    bool durable_record_may_remain;
    bool prepare_called;
    bool execute_prepared_called;
    bool settle_prepared_called;
    egolink_p0_delivery_runtime_status_t delivery_status;
    egolink_p0_delivery_runtime_result_t delivery_result;
} egolink_sos_delivery_composition_drive_result_t;

typedef struct {
    egolink_sos_delivery_composition_status_t status;
    bool rollback_cleanup_attempted;
    bool sos_runtime_shutdown_called;
    bool delivery_shutdown_called;
    bool owned_dispatcher_cleanup_attempted;
    bool sos_adapter_unbound;
    bool caller_dependencies_not_deinitialized;
    bool outbox_records_retained;
    bool pending_journal_untouched;
    egolink_sos_device_runtime_status_t sos_runtime_status;
    egolink_sos_device_runtime_shutdown_result_t sos_runtime_result;
    egolink_p0_delivery_runtime_status_t delivery_status;
    egolink_p0_delivery_runtime_result_t delivery_result;
} egolink_sos_delivery_composition_shutdown_result_t;

typedef struct {
    egolink_sos_delivery_composition_lifecycle_t lifecycle;
    egolink_sos_delivery_composition_status_t last_status;
    bool enabled;
    bool busy;
    bool caller_dependencies_bound;
    bool sos_adapter_owned_and_bound;
    bool pending_journal_owned_and_bound;
    bool dispatcher_owned_and_initialized;
    bool delivery_runtime_owned_and_initialized;
    bool sos_runtime_owned_and_initialized;
    bool wake_intent_pending;
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
    egolink_sos_device_runtime_lifecycle_t sos_runtime_lifecycle;
    egolink_sos_device_runtime_status_t sos_runtime_status;
    bool pending_edge_available;
    bool pending_edge_durable;
    egolink_p0_delivery_runtime_lifecycle_t delivery_lifecycle;
    egolink_p0_delivery_runtime_phase_t delivery_phase;
    egolink_p0_delivery_runtime_status_t delivery_status;
} egolink_sos_delivery_composition_snapshot_t;

/* Allocate in long-lived caller memory, never on a task stack. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_SOS_DELIVERY_COMPOSITION_CONTEXT_BYTES];
} egolink_sos_delivery_composition_t;

void egolink_sos_delivery_composition_default_config(
    egolink_sos_delivery_composition_config_t *config);

/*
 * Enabled init borrows, but never initializes/deinitializes, shared_outbox,
 * location_adapter, policy_core, pending_storage, or the synchronous HTTP
 * owner. location_adapter must already own that exact outbox and exact device
 * identity. The outbox has no public identity getter, so this invariant is
 * anchored at its sole initializing Location adapter and checked again at
 * every owned binding seam.
 *
 * Owned stages are initialized in this order: SOS adapter, pending journal,
 * dispatcher, delivery runtime, button runtime. A later failure rolls them
 * back in reverse. If dispatcher settlement cannot safely close, the object
 * remains queryable in RECOVERY_REQUIRED instead of unbinding dependencies.
 */
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_init(
    egolink_sos_delivery_composition_t *composition,
    const egolink_sos_delivery_composition_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter,
    egolink_location_policy_core_t *policy_core,
    const egolink_sos_pending_edge_storage_t *pending_storage,
    bool initial_raw_pressed,
    uint64_t now_ms);

/*
 * sample/replay never drive delivery. A qualified edge retains the existing
 * journal-before-CRITICAL-enqueue ordering, followed by independent feedback,
 * policy/urgent-location and Ego Call branches. The internally generated wake
 * only makes external_drive_required observable. The same external owner must
 * call drive_once later, after this API has returned.
 */
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_process_sample(
    egolink_sos_delivery_composition_t *composition,
    bool raw_pressed,
    uint64_t now_ms,
    egolink_sos_delivery_composition_event_result_t *result);

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_replay_pending(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_event_result_t *result);

/*
 * Performs at most one normal select/HTTP/finish action, or one already-
 * required finish/begin recovery settlement. It never loops. When shutdown
 * recovery is pending it will only settle recovery; it cannot start a new
 * request. The caller remains responsible for retry deadlines and scheduling.
 *
 * This synchronous API is a serialized composition reference, not the final
 * safety-task topology. A blocking HTTP callback must not run on the physical
 * input or Ego Call task, and the external owner must not hold a mutex across
 * HTTP that prevents those safety paths from running. This layer has not
 * proved SOS latency or preemption while a location POST is in flight. Product
 * integration still needs a bounded payload snapshot handed to an independent
 * sender plus a reviewed urgent cancellation/preemption policy.
 */
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_drive_once(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_drive_result_t *result);

/*
 * Product sender seam. prepare and settle_prepared require the same external
 * shared owner used for sample/replay and every caller-owned outbox operation.
 * execute_prepared MUST run after releasing that owner: it invokes only the
 * injected transport callback and deliberately does not take the composition
 * busy guard. While it is in flight, sample/replay may complete the durable
 * SOS journal/enqueue and all local branches; the internal wake callback then
 * issues the runtime's atomic LOCATION-only cancellation hint.
 *
 * The callback must cooperate by polling cancel_requested and keep its own
 * bounded timeout. A non-cooperative modem/HTTP callback cannot be stopped;
 * this API reports that truth and does not claim hard preemption. cancel,
 * close, status, prepare and settle must not race execute_prepared.
 */
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_prepare(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_drive_result_t *result);

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_execute_prepared(
    egolink_sos_delivery_composition_t *composition,
    egolink_sos_delivery_composition_drive_result_t *result);

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_settle_prepared(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_drive_result_t *result);

/*
 * Owner-held, single-action recovery only. It never prepares or posts.
 * PREPARED means cancel/close may safely settle the unsent begin; RESULT_READY
 * means settle_prepared is required; EXECUTING reports reentrant/in-flight.
 */
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_recover_delivery_once(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_drive_result_t *result);

/*
 * cancel/close never clear the pending journal or ACK/delete an outbox record.
 * A volatile pending edge or unresolved delivery settlement fails closed and
 * leaves the object available for explicit replay/recovery. Successful close
 * unbinds only this component's SOS adapter. Exactly one external task or
 * mutex must serialize all composition APIs and all direct caller-owned LOC,
 * policy, outbox and storage operations. The local busy guard is not a lock.
 */
egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_cancel(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_shutdown_result_t *result);

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_close(
    egolink_sos_delivery_composition_t *composition,
    uint64_t now_ms,
    egolink_sos_delivery_composition_shutdown_result_t *result);

egolink_sos_delivery_composition_status_t
egolink_sos_delivery_composition_current_status(
    const egolink_sos_delivery_composition_t *composition,
    egolink_sos_delivery_composition_snapshot_t *snapshot);

const char *egolink_sos_delivery_composition_status_name(
    egolink_sos_delivery_composition_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SOS_DELIVERY_COMPOSITION_H */

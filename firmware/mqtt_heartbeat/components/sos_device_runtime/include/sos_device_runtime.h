#ifndef EGOLINK_SOS_DEVICE_RUNTIME_H
#define EGOLINK_SOS_DEVICE_RUNTIME_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "sos_orchestrator.h"
#include "sos_outbox_adapter.h"
#include "sos_pending_edge_journal.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_SOS_DEVICE_RUNTIME_CONTRACT_VERSION \
    "egolink.sos_device_runtime.v0.1"
#define EGOLINK_SOS_DEVICE_RUNTIME_CONTEXT_BYTES (4U * 1024U)

typedef enum {
    EGOLINK_SOS_DEVICE_RUNTIME_NEVER_INITIALIZED = 0,
    EGOLINK_SOS_DEVICE_RUNTIME_DISABLED,
    EGOLINK_SOS_DEVICE_RUNTIME_ACTIVE,
    EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED,
    EGOLINK_SOS_DEVICE_RUNTIME_CLOSED,
} egolink_sos_device_runtime_lifecycle_t;

typedef enum {
    EGOLINK_SOS_DEVICE_RUNTIME_OK = 0,
    EGOLINK_SOS_DEVICE_RUNTIME_NO_EDGE,
    EGOLINK_SOS_DEVICE_RUNTIME_PARTIAL_FAILURE,
    EGOLINK_SOS_DEVICE_RUNTIME_DISABLED_STATUS,
    EGOLINK_SOS_DEVICE_RUNTIME_CANCELLED_STATUS,
    EGOLINK_SOS_DEVICE_RUNTIME_CLOSED_STATUS,
    EGOLINK_SOS_DEVICE_RUNTIME_INPUT_FAILED,
    EGOLINK_SOS_DEVICE_RUNTIME_JOURNAL_FAILED,
    EGOLINK_SOS_DEVICE_RUNTIME_PENDING_REPLAY_REQUIRED,
    EGOLINK_SOS_DEVICE_RUNTIME_NO_PENDING_EDGE,
    EGOLINK_SOS_DEVICE_RUNTIME_SEQUENCE_EXHAUSTED,
    EGOLINK_SOS_DEVICE_RUNTIME_INVALID_ARGUMENT,
    EGOLINK_SOS_DEVICE_RUNTIME_INVALID_CONFIG,
    EGOLINK_SOS_DEVICE_RUNTIME_NOT_INITIALIZED,
    EGOLINK_SOS_DEVICE_RUNTIME_ALREADY_INITIALIZED,
    EGOLINK_SOS_DEVICE_RUNTIME_DEPENDENCY_MISMATCH,
    EGOLINK_SOS_DEVICE_RUNTIME_REENTRANT_CALL,
} egolink_sos_device_runtime_status_t;

/*
 * This is a wake intent only. It carries no payload, coordinate, media,
 * endpoint or credential and does not claim a send occurred. The identity
 * pointers are borrowed for the synchronous callback only.
 */
typedef struct {
    const egolink_sos_branch_identity_t *identity;
    bool durable_manual_sos_available;
    egolink_sos_persistence_state_t persistence_state;
} egolink_sos_sender_wake_request_t;

typedef bool (*egolink_sos_sender_wake_fn)(
    void *context,
    const egolink_sos_sender_wake_request_t *request);

/*
 * All callbacks are synchronous and must copy any borrowed identity they
 * retain. They must not recursively call this runtime, the dispatcher, the
 * adapter, policy or outbox. wake_sender is a notification seam only; it must
 * not perform a send before returning. It is invoked only after the matching
 * manual_sos is durably COMMITTED or found DUPLICATE, before feedback/policy/
 * Location/Call branches. Outbox failure does not invoke it with
 * durable_manual_sos_available=false; the retained pending edge is recovered
 * through replay_pending instead.
 */
typedef struct {
    /* Means qualified input recognized only, never stored/delivered. Runs
     * before any journal I/O and receives the original physical edge time. */
    bool (*input_recognized)(void *context, const egolink_sos_input_output_t *edge);
    void *input_recognized_context;
    egolink_sos_local_feedback_fn local_feedback;
    void *local_feedback_context;
    egolink_sos_location_enqueue_fn request_urgent_location;
    void *location_context;
    egolink_sos_call_request_fn request_call;
    void *call_context;
    egolink_sos_sender_wake_fn wake_sender;
    void *sender_context;
} egolink_sos_device_runtime_callbacks_t;

/*
 * enabled=false is the deliberate default. Identity is boot-scoped and is
 * copied during init. first_source_sequence is consumed only after the exact
 * qualified physical edge is durable in the pending journal; later outbox or
 * callback failure cannot roll it back. Battery, camera and AI are
 * intentionally absent and therefore cannot veto SOS.
 */
typedef struct {
    bool enabled;
    egolink_sos_input_config_t input;
    const char *device_id;
    uint64_t boot_count;
    const char *session_id;
    uint64_t first_source_sequence;
    egolink_sos_device_runtime_callbacks_t callbacks;
} egolink_sos_device_runtime_config_t;

/* No safety-event payload, coordinate, media, secret or callback data. */
typedef struct {
    egolink_sos_device_runtime_status_t status;
    egolink_sos_input_status_t input_status;
    egolink_sos_input_output_t input_output;
    bool qualified_edge;
    egolink_sos_branch_state_t input_recognition;
    bool replayed_pending_edge;
    uint64_t source_sequence;
    bool journal_store_attempted;
    egolink_sos_pending_edge_status_t journal_store_status;
    bool journal_clear_attempted;
    egolink_sos_pending_edge_status_t journal_clear_status;
    bool pending_edge_durable;
    bool pending_edge_retained;
    egolink_sos_orchestration_status_t orchestration_status;
    egolink_sos_orchestration_result_t orchestration;
    egolink_sos_branch_state_t sender_wake;
    bool durable_manual_sos_available;
} egolink_sos_device_runtime_result_t;

typedef struct {
    egolink_sos_device_runtime_status_t status;
    bool durable_records_retained;
    bool dispatcher_attempt_untouched;
    bool pending_edge_journal_untouched;
} egolink_sos_device_runtime_shutdown_result_t;

typedef struct {
    egolink_sos_device_runtime_lifecycle_t lifecycle;
    egolink_sos_device_runtime_status_t last_status;
    bool enabled;
    bool busy;
    bool dependencies_bound;
    bool dispatcher_attempt_observed_active;
    bool source_sequence_exhausted;
    bool pending_edge_available;
    bool pending_edge_durable;
    egolink_sos_pending_edge_status_t last_journal_status;
    uint64_t next_source_sequence;
    uint64_t sample_calls;
    uint64_t qualified_edges;
    uint64_t durable_edges;
    uint64_t partial_edges;
    uint64_t sender_wake_failures;
    uint64_t pending_replay_attempts;
    uint64_t journal_store_failures;
    uint64_t journal_clear_failures;
} egolink_sos_device_runtime_snapshot_t;

/* Caller should allocate this opaque object statically, not on a task stack. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_SOS_DEVICE_RUNTIME_CONTEXT_BYTES];
} egolink_sos_device_runtime_t;

void egolink_sos_device_runtime_default_config(
    egolink_sos_device_runtime_config_t *config);

/*
 * shared_outbox must already be initialized. delivery_adapter must be the
 * single caller-owned E adapter already bound to that exact outbox and exact
 * config device identity. The runtime only borrows both; it never initializes,
 * binds, unbinds, sends, acknowledges, deinitializes or deletes them.
 * policy_core must also be initialized. initial_raw_pressed and now_ms are the
 * first boot-monotonic sample; boot-held input must debounce a release before
 * it can arm.
 *
 * The composition root initializes the shared outbox, binds exactly one E
 * adapter, gives that adapter to the single outbox dispatcher, then passes the
 * same outbox/adapter/device identity here. Before runtime init, the composition
 * root must also bind a caller-owned pending_journal for that exact device.
 * Runtime init loads but never clears a recovered record. An old boot/session
 * is replayable without changing the new boot sequence; a record from a future
 * boot or a different session within the current boot fails closed. For a
 * current boot/session, next sequence skips any recovered sequence already
 * consumed. The dispatcher remains the only
 * send/finish/ACK owner. Exactly one external task or mutex must serialize
 * every runtime API with SOS input/orchestration, policy, shared-outbox,
 * dispatcher and snapshot calls. The local busy guard rejects recursion but
 * is not a lock. boot_count/first_source_sequence must come from a caller-
 * owned monotonic lineage source; this volatile runtime does not persist them.
 */
egolink_sos_device_runtime_status_t egolink_sos_device_runtime_init(
    egolink_sos_device_runtime_t *runtime,
    const egolink_sos_device_runtime_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_sos_outbox_adapter_t *delivery_adapter,
    egolink_sos_pending_edge_journal_t *pending_journal,
    egolink_location_policy_core_t *policy_core,
    bool initial_raw_pressed,
    uint64_t now_ms);

/*
 * The only per-sample inputs are a caller-injected pressed level and the same
 * boot-monotonic clock. On one qualified edge the existing orchestrator owns
 * the fixed order: durable enqueue attempt, durable sender wake only for
 * COMMITTED/DUPLICATE, local feedback, policy SOS, coordinate-free urgent
 * location request, then Ego Call. Outbox failure skips wake/preemption and
 * remains recoverable through the pending-edge replay path. Repeated samples
 * cannot replay the latched edge;
 * only a debounced release re-arms the next source sequence.
 *
 * LOC currently exposes no safe API here for constructing a unique durable
 * SOS observation. request_urgent_location is therefore only an identified
 * intent seam; its serialized owner must resolve last-trusted/current state
 * and create any LOC observation without retaining borrowed pointers.
 *
 * Before an orchestrator call, a qualified edge is stored in the injected
 * journal and read back. Its sequence is consumed only after that exact
 * lineage is durably recoverable. A store failure retains the candidate in
 * volatile runtime state, blocks later input, and requires replay_pending;
 * reset during such an unresolved backend failure still cannot be recovered.
 * While any pending record/candidate exists, new samples are rejected with
 * PENDING_REPLAY_REQUIRED so the one-record journal cannot be overwritten.
 */
egolink_sos_device_runtime_status_t egolink_sos_device_runtime_process_sample(
    egolink_sos_device_runtime_t *runtime,
    bool raw_pressed,
    uint64_t now_ms,
    egolink_sos_device_runtime_result_t *result);

/*
 * Replays a boot-recovered or volatile pending edge using its exact original
 * boot/session/sequence/edge time. The journal is cleared only after the
 * orchestrator reports COMMITTED or exact DUPLICATE. Enqueue or clear failure
 * leaves it pending; callbacks are at-least-once and use the same event ID.
 * Call this before accepting samples when init/current_status reports pending.
 */
egolink_sos_device_runtime_status_t
egolink_sos_device_runtime_replay_pending(
    egolink_sos_device_runtime_t *runtime,
    uint64_t now_ms,
    egolink_sos_device_runtime_result_t *result);

/*
 * Cancel/close are terminal for button composition only. They never clear the
 * pending-edge journal and never mutate
 * the outbox or call adapter bind/unbind/begin/finish/ACK. In particular, a
 * dispatcher-owned active attempt remains wholly owned and untouched by the
 * dispatcher. The caller may keep delivering durable records after closing
 * this runtime. Shutdown is rejected while a store-failed edge exists only in
 * volatile memory, so the caller can repair storage and retry it first.
 */
egolink_sos_device_runtime_status_t egolink_sos_device_runtime_cancel(
    egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_shutdown_result_t *result);

egolink_sos_device_runtime_status_t egolink_sos_device_runtime_close(
    egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_shutdown_result_t *result);

egolink_sos_device_runtime_status_t
egolink_sos_device_runtime_current_status(
    const egolink_sos_device_runtime_t *runtime,
    egolink_sos_device_runtime_snapshot_t *snapshot);

const char *egolink_sos_device_runtime_status_name(
    egolink_sos_device_runtime_status_t status);
const char *egolink_sos_device_runtime_lifecycle_name(
    egolink_sos_device_runtime_lifecycle_t lifecycle);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SOS_DEVICE_RUNTIME_H */

#ifndef EGOLINK_SOS_DELIVERY_SENDER_TASK_H
#define EGOLINK_SOS_DELIVERY_SENDER_TASK_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "sos_delivery_composition.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_SOS_DELIVERY_SENDER_TASK_CONTRACT_VERSION \
    "egolink.sos_delivery_sender_task.v0.1"
#define EGOLINK_SOS_DELIVERY_SENDER_TASK_CONTEXT_BYTES (16U * 1024U)

typedef enum {
    EGOLINK_SOS_SENDER_TASK_NEVER_INITIALIZED = 0,
    EGOLINK_SOS_SENDER_TASK_DISABLED,
    EGOLINK_SOS_SENDER_TASK_RUNNING,
    EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED,
    EGOLINK_SOS_SENDER_TASK_STOPPED,
    EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
} egolink_sos_delivery_sender_task_lifecycle_t;

typedef enum {
    EGOLINK_SOS_SENDER_TASK_PHASE_IDLE = 0,
    EGOLINK_SOS_SENDER_TASK_PHASE_PREPARING,
    EGOLINK_SOS_SENDER_TASK_PHASE_PREPARED,
    EGOLINK_SOS_SENDER_TASK_PHASE_EXECUTING,
    EGOLINK_SOS_SENDER_TASK_PHASE_RESULT_READY,
    EGOLINK_SOS_SENDER_TASK_PHASE_SETTLING,
    EGOLINK_SOS_SENDER_TASK_PHASE_RECOVERING,
    EGOLINK_SOS_SENDER_TASK_PHASE_STOPPING,
} egolink_sos_delivery_sender_task_phase_t;

typedef enum {
    EGOLINK_SOS_SENDER_TASK_OK = 0,
    EGOLINK_SOS_SENDER_TASK_DISABLED_STATUS,
    EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS,
    EGOLINK_SOS_SENDER_TASK_STOPPED_STATUS,
    EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS,
    EGOLINK_SOS_SENDER_TASK_INVALID_ARGUMENT,
    EGOLINK_SOS_SENDER_TASK_INVALID_CONFIG,
    EGOLINK_SOS_SENDER_TASK_BUILD_DISABLED,
    EGOLINK_SOS_SENDER_TASK_ALREADY_INITIALIZED,
    EGOLINK_SOS_SENDER_TASK_NOT_INITIALIZED,
    EGOLINK_SOS_SENDER_TASK_TASK_CREATE_FAILED,
    EGOLINK_SOS_SENDER_TASK_GENERATION_EXHAUSTED,
    EGOLINK_SOS_SENDER_TASK_PUBLIC_CALL_LIMIT,
} egolink_sos_delivery_sender_task_status_t;

/* The composition root supplies the ONE lock shared with every direct
 * Location/outbox/composition owner. The sender task takes it only for
 * prepare, settle, recovery and orderly shutdown. It is never held while
 * execute_prepared invokes the bounded transport callback. */
typedef bool (*egolink_sos_delivery_sender_owner_enter_fn)(
    void *context,
    uint32_t timeout_ms);
typedef void (*egolink_sos_delivery_sender_owner_leave_fn)(void *context);
typedef uint64_t (*egolink_sos_delivery_sender_now_ms_fn)(void *context);

typedef struct {
    bool enabled;
    egolink_sos_delivery_composition_t *composition;
    egolink_sos_delivery_sender_owner_enter_fn owner_enter;
    egolink_sos_delivery_sender_owner_leave_fn owner_leave;
    void *owner_context;
    egolink_sos_delivery_sender_now_ms_fn now_ms;
    void *clock_context;
    uint32_t owner_timeout_ms;
    uint32_t idle_poll_ms;
    /* Cooperative worker-stop budget after any already-entered synchronous
     * transport/composition callback returns. It caps subsequent owner waits
     * and retry scheduling; it is not a callback wall-clock or hard-real-time
     * cancellation guarantee. */
    uint32_t stop_timeout_ms;
    uint32_t task_priority;
    bool start_with_pending_work;
} egolink_sos_delivery_sender_task_config_t;

typedef struct {
    egolink_sos_delivery_sender_task_lifecycle_t lifecycle;
    egolink_sos_delivery_sender_task_phase_t phase;
    egolink_sos_delivery_sender_task_status_t last_status;
    egolink_sos_delivery_composition_status_t last_composition_status;
    bool enabled;
    bool wake_pending;
    bool execute_in_progress;
    bool stop_requested;
    /* State-machine terminal commit, not proof that the RTOS self-delete has
     * completed. The public context remains boot-long and non-reclaimable. */
    bool terminal_committed;
    bool owner_held;
    uint32_t wake_generation;
    uint32_t consumed_wake_generation;
    /* Nonzero, monotonic-within-boot and saturating. Exhaustion fails closed. */
    uint32_t last_attempt_generation;
    uint32_t active_attempt_generation;
    uint32_t result_attempt_generation;
    uint32_t notifications;
    uint32_t coalesced_notifications;
    uint32_t stale_wake_generations_rejected;
    uint32_t prepare_calls;
    uint32_t execute_calls;
    uint32_t settle_calls;
    uint32_t recovery_calls;
    uint32_t owner_timeouts;
    uint32_t stop_requests;
    uint32_t public_calls_in_flight;
    /* The task calls only the composition split-phase API. Exact-ACK deletion
     * remains inside composition settlement; no outbox/journal API is exposed
     * to or called directly by this owner. */
    bool no_direct_outbox_or_journal_api;
} egolink_sos_delivery_sender_task_snapshot_t;

/* Boot-long fixed storage. It contains both the StaticTask_t and its stack;
 * the component never calls a dynamic allocator or xTaskCreate(). The object
 * MUST NOT be reclaimed, cleared or reinitialized after request_stop: public
 * calls are drained before self-delete, but there is deliberately no external
 * task join/reclaim claim in this v0 API. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_SOS_DELIVERY_SENDER_TASK_CONTEXT_BYTES];
} egolink_sos_delivery_sender_task_t;

void egolink_sos_delivery_sender_task_default_config(
    egolink_sos_delivery_sender_task_config_t *config);

egolink_sos_delivery_sender_task_status_t
egolink_sos_delivery_sender_task_init(
    egolink_sos_delivery_sender_task_t *task,
    const egolink_sos_delivery_sender_task_config_t *config);

/* Thread-safe, allocation-free edge notification. Repeated notifications
 * coalesce; the durable outbox remains the source of work and identity. */
egolink_sos_delivery_sender_task_status_t
egolink_sos_delivery_sender_task_notify(
    egolink_sos_delivery_sender_task_t *task,
    uint32_t *wake_generation);

/* Nonblocking request. EXECUTING is never force-killed; the worker waits for
 * an already-entered synchronous callback to return. stop_timeout then budgets
 * cooperative worker scheduling/owner waits/retries, not callback wall time.
 * A ready exact result is settled before composition cancellation, without
 * deleting a journal or an unacknowledged record. */
egolink_sos_delivery_sender_task_status_t
egolink_sos_delivery_sender_task_request_stop(
    egolink_sos_delivery_sender_task_t *task);

egolink_sos_delivery_sender_task_status_t
egolink_sos_delivery_sender_task_current_status(
    const egolink_sos_delivery_sender_task_t *task,
    egolink_sos_delivery_sender_task_snapshot_t *snapshot);

const char *egolink_sos_delivery_sender_task_status_name(
    egolink_sos_delivery_sender_task_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SOS_DELIVERY_SENDER_TASK_H */

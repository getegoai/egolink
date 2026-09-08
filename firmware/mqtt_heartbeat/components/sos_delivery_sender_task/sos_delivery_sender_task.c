#include "sos_delivery_sender_task.h"

#include <stdatomic.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#ifndef CONFIG_EGOLINK_SOS_DELIVERY_SENDER_TASK_ENABLED
#define CONFIG_EGOLINK_SOS_DELIVERY_SENDER_TASK_ENABLED 0
#endif

#define SENDER_MAGIC UINT32_C(0x534F534B)
/* ESP-IDF's xTaskCreateStatic() depth is bytes, unlike upstream FreeRTOS.
 * Keep both the API budget and backing-store calculation explicit. */
#define SENDER_STACK_BYTES 6144U
#define SENDER_STACK_STORAGE_WORDS \
    ((SENDER_STACK_BYTES + sizeof(StackType_t) - 1U) / sizeof(StackType_t))
#define SENDER_DEFAULT_OWNER_TIMEOUT_MS 100U
#define SENDER_DEFAULT_IDLE_POLL_MS 100U
#define SENDER_DEFAULT_STOP_TIMEOUT_MS 40000U
#define SENDER_DEFAULT_TASK_PRIORITY 3U
#define SENDER_PUBLIC_CALL_CLOSED UINT32_C(0x80000000)
#define SENDER_PUBLIC_CALL_COUNT_MASK UINT32_C(0x7FFFFFFF)

#ifndef EGOLINK_SOS_SENDER_ATTEMPT_GENERATION_MAX
#define EGOLINK_SOS_SENDER_ATTEMPT_GENERATION_MAX UINT32_MAX
#endif

#ifndef EGOLINK_SOS_SENDER_PUBLIC_CALL_MAX
#define EGOLINK_SOS_SENDER_PUBLIC_CALL_MAX SENDER_PUBLIC_CALL_COUNT_MASK
#endif

_Static_assert(EGOLINK_SOS_SENDER_ATTEMPT_GENERATION_MAX > 0U,
               "attempt generation space must be nonempty");
_Static_assert(EGOLINK_SOS_SENDER_ATTEMPT_GENERATION_MAX <= UINT32_MAX,
               "attempt generation must fit the public snapshot");
_Static_assert(EGOLINK_SOS_SENDER_PUBLIC_CALL_MAX > 0U,
               "at least one public call must be admissible");
_Static_assert(EGOLINK_SOS_SENDER_PUBLIC_CALL_MAX <=
                   SENDER_PUBLIC_CALL_COUNT_MASK,
               "public call reference count must leave one closed bit");

typedef enum {
    PUBLIC_CALL_ADMITTED = 0,
    PUBLIC_CALL_CLOSED,
    PUBLIC_CALL_LIMIT,
} public_call_admission_t;

typedef struct {
    uint32_t magic;
    egolink_sos_delivery_sender_task_config_t config;
    StaticTask_t task_buffer;
    StackType_t task_stack[SENDER_STACK_STORAGE_WORDS];
    TaskHandle_t task_handle;
    atomic_int lifecycle;
    atomic_int phase;
    atomic_int last_status;
    atomic_int last_composition_status;
    atomic_bool wake_pending;
    atomic_bool execute_in_progress;
    atomic_bool stop_requested;
    atomic_bool terminal_committed;
    atomic_bool owner_held;
    atomic_uint wake_generation;
    atomic_uint consumed_wake_generation;
    atomic_uint last_attempt_generation;
    atomic_uint active_attempt_generation;
    atomic_uint result_attempt_generation;
    atomic_uint notifications;
    atomic_uint coalesced_notifications;
    atomic_uint stale_wake_generations_rejected;
    atomic_uint prepare_calls;
    atomic_uint execute_calls;
    atomic_uint settle_calls;
    atomic_uint recovery_calls;
    atomic_uint owner_timeouts;
    atomic_uint stop_requests;
    /* High bit closes admission atomically; low bits count old callers that
     * may still touch task_handle and must drain before self-delete. */
    atomic_uint public_call_gate;
    uint64_t last_now_ms;
    uint64_t stop_deadline_ms;
    bool stop_deadline_set;
    TickType_t idle_poll_ticks;
} sender_internal_t;

_Static_assert(sizeof(sender_internal_t) <=
                   EGOLINK_SOS_DELIVERY_SENDER_TASK_CONTEXT_BYTES,
               "sender task context too small");

static sender_internal_t *internal_of(
    egolink_sos_delivery_sender_task_t *task)
{
    return (sender_internal_t *)(void *)task->opaque;
}

static const sender_internal_t *internal_of_const(
    const egolink_sos_delivery_sender_task_t *task)
{
    return (const sender_internal_t *)(const void *)task->opaque;
}

static bool valid_magic(const sender_internal_t *internal)
{
    return internal != NULL && internal->magic == SENDER_MAGIC;
}

static void increment_saturated(atomic_uint *value)
{
    unsigned int current = atomic_load(value);
    while (current != UINT32_MAX &&
           !atomic_compare_exchange_weak(value, &current, current + 1U)) {
    }
}

static unsigned int advance_saturated_nonzero(atomic_uint *value)
{
    unsigned int current = atomic_load(value);
    for (;;) {
        const unsigned int next = current == UINT32_MAX
            ? UINT32_MAX
            : current + 1U;
        if (atomic_compare_exchange_weak(value, &current, next)) {
            return next;
        }
    }
}

static public_call_admission_t enter_public_call(sender_internal_t *internal)
{
    unsigned int current = atomic_load(&internal->public_call_gate);
    for (;;) {
        if ((current & SENDER_PUBLIC_CALL_CLOSED) != 0U) {
            return PUBLIC_CALL_CLOSED;
        }
        const unsigned int count =
            current & SENDER_PUBLIC_CALL_COUNT_MASK;
        if (count >= (unsigned int)EGOLINK_SOS_SENDER_PUBLIC_CALL_MAX) {
            return PUBLIC_CALL_LIMIT;
        }
        if (atomic_compare_exchange_weak(
                &internal->public_call_gate,
                &current,
                current + 1U)) {
            return PUBLIC_CALL_ADMITTED;
        }
    }
}

static void leave_public_call(sender_internal_t *internal)
{
    const unsigned int previous =
        atomic_fetch_sub(&internal->public_call_gate, 1U);
    (void)previous;
}

static egolink_sos_delivery_sender_task_status_t lifecycle_status(
    const sender_internal_t *internal,
    egolink_sos_delivery_sender_task_lifecycle_t lifecycle)
{
    if (lifecycle == EGOLINK_SOS_SENDER_TASK_DISABLED) {
        return (egolink_sos_delivery_sender_task_status_t)
            atomic_load(&internal->last_status);
    }
    if (lifecycle == EGOLINK_SOS_SENDER_TASK_STOPPED) {
        return EGOLINK_SOS_SENDER_TASK_STOPPED_STATUS;
    }
    if (lifecycle == EGOLINK_SOS_SENDER_TASK_STOP_FAILED) {
        return EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS;
    }
    if (lifecycle == EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED) {
        return EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS;
    }
    return EGOLINK_SOS_SENDER_TASK_NOT_INITIALIZED;
}

static uint64_t add_ms(uint64_t now_ms, uint32_t duration_ms)
{
    return now_ms > UINT64_MAX - duration_ms
        ? UINT64_MAX
        : now_ms + duration_ms;
}

static bool __attribute__((unused)) bounded_wait_ticks(
    uint32_t milliseconds,
    TickType_t *result)
{
    if (milliseconds == 0U || result == NULL || configTICK_RATE_HZ == 0U) {
        return false;
    }
    const uint64_t numerator =
        (uint64_t)milliseconds * (uint64_t)configTICK_RATE_HZ;
    uint64_t ticks = (numerator + UINT64_C(999)) / UINT64_C(1000);
    if (ticks == 0U) {
        ticks = 1U;
    }
    /* portMAX_DELAY can mean an infinite wait. The sender's retry poll must
     * stay both nonzero and finite in every supported TickType_t width. */
    if (ticks >= (uint64_t)portMAX_DELAY) {
        return false;
    }
    *result = (TickType_t)ticks;
    return true;
}

static uint64_t monotonic_now(sender_internal_t *internal)
{
    uint64_t now_ms = internal->config.now_ms(internal->config.clock_context);
    if (now_ms < internal->last_now_ms) {
        now_ms = internal->last_now_ms;
    } else {
        internal->last_now_ms = now_ms;
    }
    return now_ms;
}

static void set_phase(
    sender_internal_t *internal,
    egolink_sos_delivery_sender_task_phase_t phase)
{
    atomic_store(&internal->phase, (int)phase);
}

static void set_status(
    sender_internal_t *internal,
    egolink_sos_delivery_sender_task_status_t status)
{
    atomic_store(&internal->last_status, (int)status);
}

static void set_composition_status(
    sender_internal_t *internal,
    egolink_sos_delivery_composition_status_t status)
{
    atomic_store(&internal->last_composition_status, (int)status);
}

static bool enter_owner_with_timeout(
    sender_internal_t *internal,
    uint32_t timeout_ms)
{
    if (timeout_ms == 0U) {
        return false;
    }
    if (!internal->config.owner_enter(
            internal->config.owner_context,
            timeout_ms)) {
        increment_saturated(&internal->owner_timeouts);
        return false;
    }
    atomic_store(&internal->owner_held, true);
    return true;
}

static bool enter_owner(sender_internal_t *internal)
{
    return enter_owner_with_timeout(
        internal, internal->config.owner_timeout_ms);
}

static void leave_owner(sender_internal_t *internal)
{
    atomic_store(&internal->owner_held, false);
    internal->config.owner_leave(internal->config.owner_context);
}

static bool stop_timed_out(sender_internal_t *internal, uint64_t now_ms)
{
    if (!internal->stop_deadline_set) {
        internal->stop_deadline_ms =
            add_ms(now_ms, internal->config.stop_timeout_ms);
        internal->stop_deadline_set = true;
    }
    return now_ms >= internal->stop_deadline_ms;
}

static uint32_t remaining_stop_owner_timeout(
    const sender_internal_t *internal,
    uint64_t now_ms)
{
    if (!internal->stop_deadline_set || now_ms >= internal->stop_deadline_ms) {
        return 0U;
    }
    const uint64_t remaining = internal->stop_deadline_ms - now_ms;
    return remaining < internal->config.owner_timeout_ms
        ? (uint32_t)remaining
        : internal->config.owner_timeout_ms;
}

static TickType_t stop_aware_wait_ticks(sender_internal_t *internal)
{
    if (!atomic_load(&internal->stop_requested) ||
        !internal->stop_deadline_set) {
        return internal->idle_poll_ticks;
    }
    const uint64_t now_ms = monotonic_now(internal);
    if (now_ms >= internal->stop_deadline_ms) {
        return (TickType_t)0U;
    }
    const uint64_t remaining_ms = internal->stop_deadline_ms - now_ms;
    const uint32_t wait_ms = remaining_ms < internal->config.idle_poll_ms
        ? (uint32_t)remaining_ms
        : internal->config.idle_poll_ms;
    TickType_t wait_ticks = 0U;
    if (!bounded_wait_ticks(wait_ms, &wait_ticks)) {
        return (TickType_t)0U;
    }
    return wait_ticks;
}

static bool final_stop_status(
    egolink_sos_delivery_composition_status_t status)
{
    return status == EGOLINK_SOS_DELIVERY_COMPOSITION_CANCELLED_STATUS ||
        status == EGOLINK_SOS_DELIVERY_COMPOSITION_CLOSED_STATUS ||
        status == EGOLINK_SOS_DELIVERY_COMPOSITION_DISABLED_STATUS;
}

static bool normal_settlement_status(
    egolink_sos_delivery_composition_status_t status)
{
    return status == EGOLINK_SOS_DELIVERY_COMPOSITION_OK ||
        status == EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_DELETED ||
        status == EGOLINK_SOS_DELIVERY_COMPOSITION_ACK_ALREADY_APPLIED ||
        status == EGOLINK_SOS_DELIVERY_COMPOSITION_DELIVERY_RETAINED ||
        status == EGOLINK_SOS_DELIVERY_COMPOSITION_NO_DUE_RECORD;
}

static void commit_terminal(
    sender_internal_t *internal,
    egolink_sos_delivery_sender_task_lifecycle_t lifecycle,
    egolink_sos_delivery_sender_task_status_t status)
{
    atomic_store(&internal->lifecycle, (int)lifecycle);
    set_status(internal, status);
    /* Close public admission in the same atomic modification order as ref
     * acquisition. A CAS either entered before this bit and must drain, or
     * observes CLOSED and can never touch task_handle. */
    (void)atomic_fetch_or(
        &internal->public_call_gate, SENDER_PUBLIC_CALL_CLOSED);
    /* Publish after lifecycle/status and admission close. This remains a
     * state-machine marker, not a storage-reclaim fence. */
    atomic_store(&internal->terminal_committed, true);
}

static void finish_worker(
    sender_internal_t *internal,
    egolink_sos_delivery_sender_task_lifecycle_t lifecycle,
    egolink_sos_delivery_sender_task_status_t status)
{
    atomic_store(&internal->execute_in_progress, false);
    atomic_store(&internal->owner_held, false);
    atomic_store(&internal->active_attempt_generation, 0U);
    atomic_store(&internal->result_attempt_generation, 0U);
    set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_IDLE);
    commit_terminal(internal, lifecycle, status);
}

static bool recover_once(sender_internal_t *internal, uint64_t now_ms)
{
    egolink_sos_delivery_composition_drive_result_t result;
    set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_RECOVERING);
    increment_saturated(&internal->recovery_calls);
    egolink_sos_delivery_composition_status_t status =
        egolink_sos_delivery_composition_recover_delivery_once(
            internal->config.composition, now_ms, &result);
    set_composition_status(internal, status);
    const bool recovered = normal_settlement_status(status);
    if (recovered) {
        atomic_store(&internal->active_attempt_generation, 0U);
        atomic_store(&internal->result_attempt_generation, 0U);
    }
    set_phase(internal, recovered
        ? EGOLINK_SOS_SENDER_TASK_PHASE_IDLE
        : EGOLINK_SOS_SENDER_TASK_PHASE_RECOVERING);
    return recovered;
}

static bool settle_result_with_timeout(
    sender_internal_t *internal,
    uint32_t owner_timeout_ms)
{
    const uint32_t active = atomic_load(&internal->active_attempt_generation);
    const uint32_t result_generation =
        atomic_load(&internal->result_attempt_generation);
    if (active == 0U || result_generation != active) {
        /* A result can settle only the exact currently prepared generation.
         * Leave the composition untouched for explicit recovery. */
        set_status(internal, EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
        return false;
    }
    if (!enter_owner_with_timeout(internal, owner_timeout_ms)) {
        return false;
    }
    set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_SETTLING);
    egolink_sos_delivery_composition_drive_result_t result;
    increment_saturated(&internal->settle_calls);
    egolink_sos_delivery_composition_status_t status =
        egolink_sos_delivery_composition_settle_prepared(
            internal->config.composition, monotonic_now(internal), &result);
    set_composition_status(internal, status);
    leave_owner(internal);
    const bool settled = normal_settlement_status(status);
    if (settled ||
        status == EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED) {
        atomic_store(&internal->active_attempt_generation, 0U);
        atomic_store(&internal->result_attempt_generation, 0U);
    }
    set_phase(internal, settled
        ? EGOLINK_SOS_SENDER_TASK_PHASE_IDLE
        : EGOLINK_SOS_SENDER_TASK_PHASE_RECOVERING);
    return settled;
}

static bool settle_result(sender_internal_t *internal)
{
    return settle_result_with_timeout(
        internal, internal->config.owner_timeout_ms);
}

static bool prepare_and_execute(
    sender_internal_t *internal,
    bool from_notification)
{
    if (!enter_owner(internal)) {
        return false;
    }
    const uint32_t observed_wake = atomic_load(&internal->wake_generation);
    const uint32_t consumed_wake =
        atomic_load(&internal->consumed_wake_generation);
    if (from_notification && observed_wake == consumed_wake &&
        !atomic_load(&internal->stop_requested)) {
        increment_saturated(&internal->stale_wake_generations_rejected);
        atomic_store(&internal->wake_pending, false);
        leave_owner(internal);
        return true;
    }
    atomic_store(&internal->consumed_wake_generation, observed_wake);
    atomic_store(&internal->wake_pending, false);
    const unsigned int last_attempt =
        atomic_load(&internal->last_attempt_generation);
    if (last_attempt ==
        (unsigned int)EGOLINK_SOS_SENDER_ATTEMPT_GENERATION_MAX) {
        leave_owner(internal);
        finish_worker(
            internal,
            EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
            EGOLINK_SOS_SENDER_TASK_GENERATION_EXHAUSTED);
        return false;
    }
    set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_PREPARING);
    egolink_sos_delivery_composition_drive_result_t prepare_result;
    increment_saturated(&internal->prepare_calls);
    egolink_sos_delivery_composition_status_t status =
        egolink_sos_delivery_composition_prepare(
            internal->config.composition,
            monotonic_now(internal),
            &prepare_result);
    set_composition_status(internal, status);
    if (status == EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED) {
        (void)recover_once(internal, monotonic_now(internal));
        leave_owner(internal);
        return true;
    }
    if (status != EGOLINK_SOS_DELIVERY_COMPOSITION_PREPARED) {
        set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_IDLE);
        leave_owner(internal);
        return normal_settlement_status(status);
    }

    const unsigned int generation = last_attempt + 1U;
    atomic_store(&internal->last_attempt_generation, generation);
    atomic_store(&internal->active_attempt_generation, generation);
    set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_PREPARED);
    if (atomic_load(&internal->stop_requested)) {
        /* Leave the unsent PREPARED attempt intact. The next stop pass owns
         * the single composition cancel/retention decision. */
        leave_owner(internal);
        return false;
    }
    leave_owner(internal);

    /* The shared owner is deliberately absent for the entire transport call. */
    set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_EXECUTING);
    atomic_store(&internal->execute_in_progress, true);
    egolink_sos_delivery_composition_drive_result_t execute_result;
    increment_saturated(&internal->execute_calls);
    status = egolink_sos_delivery_composition_execute_prepared(
        internal->config.composition, &execute_result);
    atomic_store(&internal->execute_in_progress, false);
    set_composition_status(internal, status);
    if (status != EGOLINK_SOS_DELIVERY_COMPOSITION_TRANSPORT_RESULT_READY) {
        set_status(internal, EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
        set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_RECOVERING);
        return false;
    }
    atomic_store(&internal->result_attempt_generation, generation);
    set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_RESULT_READY);
    if (atomic_load(&internal->stop_requested)) {
        /* Stop arrived during the non-preemptible transport callback. Start
         * the worker stop budget now and leave RESULT_READY untouched for
         * stop_worker_once(), whose settlement owner wait is capped to the
         * remaining budget. Never take the ordinary full owner timeout first. */
        (void)stop_timed_out(internal, monotonic_now(internal));
        return false;
    }
    return settle_result(internal);
}

static bool stop_worker_once(sender_internal_t *internal)
{
    const uint64_t now_ms = monotonic_now(internal);
    const bool timed_out = stop_timed_out(internal, now_ms);
    if ((egolink_sos_delivery_sender_task_phase_t)atomic_load(&internal->phase) ==
        EGOLINK_SOS_SENDER_TASK_PHASE_RESULT_READY) {
        const uint32_t settle_budget =
            remaining_stop_owner_timeout(internal, now_ms);
        if (settle_budget == 0U) {
            finish_worker(
                internal,
                EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
                EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
            return true;
        }
        if (!settle_result_with_timeout(internal, settle_budget) &&
            (egolink_sos_delivery_sender_task_phase_t)
                    atomic_load(&internal->phase) !=
                EGOLINK_SOS_SENDER_TASK_PHASE_RECOVERING) {
            if (timed_out ||
                stop_timed_out(internal, monotonic_now(internal))) {
                finish_worker(
                    internal,
                    EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
                    EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
                return true;
            }
            return false;
        }
    }
    if (atomic_load(&internal->execute_in_progress)) {
        return false;
    }
    const uint64_t owner_now_ms = monotonic_now(internal);
    const uint32_t owner_budget =
        remaining_stop_owner_timeout(internal, owner_now_ms);
    if (timed_out || owner_budget == 0U) {
        finish_worker(
            internal,
            EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
            EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
        return true;
    }
    if (!enter_owner_with_timeout(internal, owner_budget)) {
        if (stop_timed_out(internal, monotonic_now(internal))) {
            finish_worker(
                internal,
                EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
                EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
            return true;
        }
        return false;
    }
    if ((egolink_sos_delivery_sender_task_phase_t)
            atomic_load(&internal->phase) ==
        EGOLINK_SOS_SENDER_TASK_PHASE_RECOVERING) {
        if (!recover_once(internal, monotonic_now(internal))) {
            leave_owner(internal);
            if (timed_out) {
                finish_worker(
                    internal,
                    EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
                    EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
                return true;
            }
            return false;
        }
    }
    set_phase(internal, EGOLINK_SOS_SENDER_TASK_PHASE_STOPPING);
    egolink_sos_delivery_composition_shutdown_result_t shutdown_result;
    egolink_sos_delivery_composition_status_t status =
        egolink_sos_delivery_composition_cancel(
            internal->config.composition, monotonic_now(internal),
            &shutdown_result);
    set_composition_status(internal, status);
    if (status == EGOLINK_SOS_DELIVERY_COMPOSITION_RECOVERY_NEEDED) {
        (void)recover_once(internal, monotonic_now(internal));
    }
    leave_owner(internal);
    const bool timed_out_after =
        stop_timed_out(internal, monotonic_now(internal));
    if (final_stop_status(status) && !timed_out_after) {
        finish_worker(
            internal,
            EGOLINK_SOS_SENDER_TASK_STOPPED,
            EGOLINK_SOS_SENDER_TASK_STOPPED_STATUS);
        return true;
    }
    if (timed_out_after || status ==
            EGOLINK_SOS_DELIVERY_COMPOSITION_PENDING_REPLAY_REQUIRED) {
        finish_worker(
            internal,
            EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
            EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS);
        return true;
    }
    return false;
}

static void drive_recovery_once(sender_internal_t *internal)
{
    if (!enter_owner(internal)) {
        return;
    }
    (void)recover_once(internal, monotonic_now(internal));
    leave_owner(internal);
}

/* The symbol is intentionally unreachable in a default-off build: init's
 * create branch is compiled out. Keep that supported configuration strict. */
static void __attribute__((unused)) sender_task_entry(void *argument)
{
    sender_internal_t *internal = (sender_internal_t *)argument;
    for (;;) {
        const TickType_t wait_ticks = stop_aware_wait_ticks(internal);
        const uint32_t notification_count = wait_ticks == (TickType_t)0U
            ? 0U
            : (uint32_t)ulTaskNotifyTake(pdTRUE, wait_ticks);
        if (atomic_load(&internal->stop_requested)) {
            if (stop_worker_once(internal)) {
                break;
            }
            continue;
        }
        egolink_sos_delivery_sender_task_phase_t phase =
            (egolink_sos_delivery_sender_task_phase_t)
                atomic_load(&internal->phase);
        if (phase == EGOLINK_SOS_SENDER_TASK_PHASE_RESULT_READY) {
            (void)settle_result(internal);
        } else if (phase == EGOLINK_SOS_SENDER_TASK_PHASE_RECOVERING) {
            drive_recovery_once(internal);
        } else {
            (void)prepare_and_execute(
                internal, notification_count != 0U);
        }
        if (atomic_load(&internal->terminal_committed)) {
            break;
        }
    }
    /* A caller that observed RUNNING holds this reference across its task
     * notification. New callers observe the published terminal lifecycle and
     * never touch task_handle. No owner/composition call occurs in this drain. */
    while ((atomic_load(&internal->public_call_gate) &
            SENDER_PUBLIC_CALL_COUNT_MASK) != 0U) {
        vTaskDelay((TickType_t)1U);
    }
    vTaskDelete(NULL);
}

void egolink_sos_delivery_sender_task_default_config(
    egolink_sos_delivery_sender_task_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->owner_timeout_ms = SENDER_DEFAULT_OWNER_TIMEOUT_MS;
        config->idle_poll_ms = SENDER_DEFAULT_IDLE_POLL_MS;
        config->stop_timeout_ms = SENDER_DEFAULT_STOP_TIMEOUT_MS;
        config->task_priority = SENDER_DEFAULT_TASK_PRIORITY;
    }
}

egolink_sos_delivery_sender_task_status_t
egolink_sos_delivery_sender_task_init(
    egolink_sos_delivery_sender_task_t *task,
    const egolink_sos_delivery_sender_task_config_t *config)
{
    if (task == NULL || config == NULL) {
        return EGOLINK_SOS_SENDER_TASK_INVALID_ARGUMENT;
    }
    sender_internal_t *internal = internal_of(task);
    if (valid_magic(internal)) {
        return EGOLINK_SOS_SENDER_TASK_ALREADY_INITIALIZED;
    }
    (void)memset(task, 0, sizeof(*task));
    internal->magic = SENDER_MAGIC;
    internal->config = *config;
    atomic_init(&internal->lifecycle,
        (int)EGOLINK_SOS_SENDER_TASK_NEVER_INITIALIZED);
    atomic_init(&internal->phase, (int)EGOLINK_SOS_SENDER_TASK_PHASE_IDLE);
    atomic_init(&internal->last_status, (int)EGOLINK_SOS_SENDER_TASK_OK);
    atomic_init(&internal->last_composition_status,
        (int)EGOLINK_SOS_DELIVERY_COMPOSITION_NOT_INITIALIZED);
    atomic_init(&internal->wake_pending, false);
    atomic_init(&internal->execute_in_progress, false);
    atomic_init(&internal->stop_requested, false);
    atomic_init(&internal->terminal_committed, false);
    atomic_init(&internal->owner_held, false);
    atomic_init(&internal->wake_generation, 0U);
    atomic_init(&internal->consumed_wake_generation, 0U);
    atomic_init(&internal->last_attempt_generation, 0U);
    atomic_init(&internal->active_attempt_generation, 0U);
    atomic_init(&internal->result_attempt_generation, 0U);
    atomic_init(&internal->notifications, 0U);
    atomic_init(&internal->coalesced_notifications, 0U);
    atomic_init(&internal->stale_wake_generations_rejected, 0U);
    atomic_init(&internal->prepare_calls, 0U);
    atomic_init(&internal->execute_calls, 0U);
    atomic_init(&internal->settle_calls, 0U);
    atomic_init(&internal->recovery_calls, 0U);
    atomic_init(&internal->owner_timeouts, 0U);
    atomic_init(&internal->stop_requests, 0U);
    atomic_init(&internal->public_call_gate, 0U);
    if (!config->enabled) {
        commit_terminal(
            internal,
            EGOLINK_SOS_SENDER_TASK_DISABLED,
            EGOLINK_SOS_SENDER_TASK_DISABLED_STATUS);
        return EGOLINK_SOS_SENDER_TASK_DISABLED_STATUS;
    }
#if !CONFIG_EGOLINK_SOS_DELIVERY_SENDER_TASK_ENABLED
    commit_terminal(
        internal,
        EGOLINK_SOS_SENDER_TASK_DISABLED,
        EGOLINK_SOS_SENDER_TASK_BUILD_DISABLED);
    return EGOLINK_SOS_SENDER_TASK_BUILD_DISABLED;
#else
    if (config->composition == NULL || config->owner_enter == NULL ||
        config->owner_leave == NULL || config->now_ms == NULL ||
        config->owner_timeout_ms == 0U || config->idle_poll_ms == 0U ||
        config->stop_timeout_ms == 0U || config->task_priority == 0U ||
        config->owner_timeout_ms > config->stop_timeout_ms ||
        config->task_priority >= (uint32_t)configMAX_PRIORITIES) {
        commit_terminal(
            internal,
            EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
            EGOLINK_SOS_SENDER_TASK_INVALID_CONFIG);
        return EGOLINK_SOS_SENDER_TASK_INVALID_CONFIG;
    }
    if (!bounded_wait_ticks(
            config->idle_poll_ms, &internal->idle_poll_ticks)) {
        commit_terminal(
            internal,
            EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
            EGOLINK_SOS_SENDER_TASK_INVALID_CONFIG);
        return EGOLINK_SOS_SENDER_TASK_INVALID_CONFIG;
    }
    if (config->start_with_pending_work) {
        atomic_store(&internal->wake_generation, 1U);
        atomic_store(&internal->wake_pending, true);
    }
    atomic_store(&internal->lifecycle,
        (int)EGOLINK_SOS_SENDER_TASK_RUNNING);
    internal->task_handle = xTaskCreateStatic(
        sender_task_entry,
        "sos_sender",
        (configSTACK_DEPTH_TYPE)SENDER_STACK_BYTES,
        internal,
        (UBaseType_t)config->task_priority,
        internal->task_stack,
        &internal->task_buffer);
    if (internal->task_handle == NULL) {
        commit_terminal(
            internal,
            EGOLINK_SOS_SENDER_TASK_STOP_FAILED,
            EGOLINK_SOS_SENDER_TASK_TASK_CREATE_FAILED);
        return EGOLINK_SOS_SENDER_TASK_TASK_CREATE_FAILED;
    }
    if (config->start_with_pending_work) {
        (void)xTaskNotifyGive(internal->task_handle);
    }
    return EGOLINK_SOS_SENDER_TASK_OK;
#endif
}

egolink_sos_delivery_sender_task_status_t
egolink_sos_delivery_sender_task_notify(
    egolink_sos_delivery_sender_task_t *task,
    uint32_t *wake_generation)
{
    if (task == NULL) {
        return EGOLINK_SOS_SENDER_TASK_INVALID_ARGUMENT;
    }
    sender_internal_t *internal = internal_of(task);
    if (!valid_magic(internal)) {
        return EGOLINK_SOS_SENDER_TASK_NOT_INITIALIZED;
    }
    public_call_admission_t admission = enter_public_call(internal);
    if (admission == PUBLIC_CALL_LIMIT) {
        return EGOLINK_SOS_SENDER_TASK_PUBLIC_CALL_LIMIT;
    }
    egolink_sos_delivery_sender_task_lifecycle_t lifecycle =
        (egolink_sos_delivery_sender_task_lifecycle_t)
            atomic_load(&internal->lifecycle);
    if (admission == PUBLIC_CALL_CLOSED) {
        return lifecycle_status(internal, lifecycle);
    }
    if (lifecycle != EGOLINK_SOS_SENDER_TASK_RUNNING ||
        atomic_load(&internal->stop_requested)) {
        egolink_sos_delivery_sender_task_status_t result =
            lifecycle == EGOLINK_SOS_SENDER_TASK_STOPPED
            ? EGOLINK_SOS_SENDER_TASK_STOPPED_STATUS
            : (lifecycle == EGOLINK_SOS_SENDER_TASK_STOP_FAILED
                ? EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS
                : EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS);
        leave_public_call(internal);
        return result;
    }
    const unsigned int generation =
        advance_saturated_nonzero(&internal->wake_generation);
    if (atomic_exchange(&internal->wake_pending, true)) {
        increment_saturated(&internal->coalesced_notifications);
    }
    increment_saturated(&internal->notifications);
    if (wake_generation != NULL) {
        *wake_generation = generation;
    }
    (void)xTaskNotifyGive(internal->task_handle);
    leave_public_call(internal);
    return EGOLINK_SOS_SENDER_TASK_OK;
}

egolink_sos_delivery_sender_task_status_t
egolink_sos_delivery_sender_task_request_stop(
    egolink_sos_delivery_sender_task_t *task)
{
    if (task == NULL) {
        return EGOLINK_SOS_SENDER_TASK_INVALID_ARGUMENT;
    }
    sender_internal_t *internal = internal_of(task);
    if (!valid_magic(internal)) {
        return EGOLINK_SOS_SENDER_TASK_NOT_INITIALIZED;
    }
    public_call_admission_t admission = enter_public_call(internal);
    if (admission == PUBLIC_CALL_LIMIT) {
        return EGOLINK_SOS_SENDER_TASK_PUBLIC_CALL_LIMIT;
    }
    if (admission == PUBLIC_CALL_CLOSED) {
        egolink_sos_delivery_sender_task_lifecycle_t closed_lifecycle =
            (egolink_sos_delivery_sender_task_lifecycle_t)
                atomic_load(&internal->lifecycle);
        return lifecycle_status(internal, closed_lifecycle);
    }
    int lifecycle = (int)EGOLINK_SOS_SENDER_TASK_RUNNING;
    const bool stop_published = atomic_compare_exchange_strong(
        &internal->lifecycle,
        &lifecycle,
        (int)EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED);
    egolink_sos_delivery_sender_task_lifecycle_t observed = stop_published
        ? EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED
        : (egolink_sos_delivery_sender_task_lifecycle_t)lifecycle;
    if (observed == EGOLINK_SOS_SENDER_TASK_STOPPED) {
        leave_public_call(internal);
        return EGOLINK_SOS_SENDER_TASK_STOPPED_STATUS;
    }
    if (observed == EGOLINK_SOS_SENDER_TASK_STOP_FAILED) {
        leave_public_call(internal);
        return EGOLINK_SOS_SENDER_TASK_STOP_FAILED_STATUS;
    }
    if (observed != EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED) {
        egolink_sos_delivery_sender_task_status_t result =
            lifecycle_status(internal, observed);
        leave_public_call(internal);
        return result;
    }
    increment_saturated(&internal->stop_requests);
    atomic_store(&internal->stop_requested, true);
    (void)xTaskNotifyGive(internal->task_handle);
    leave_public_call(internal);
    return EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS;
}

egolink_sos_delivery_sender_task_status_t
egolink_sos_delivery_sender_task_current_status(
    const egolink_sos_delivery_sender_task_t *task,
    egolink_sos_delivery_sender_task_snapshot_t *snapshot)
{
    if (task == NULL || snapshot == NULL) {
        return EGOLINK_SOS_SENDER_TASK_INVALID_ARGUMENT;
    }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    const sender_internal_t *internal = internal_of_const(task);
    if (!valid_magic(internal)) {
        snapshot->lifecycle = EGOLINK_SOS_SENDER_TASK_NEVER_INITIALIZED;
        snapshot->last_status = EGOLINK_SOS_SENDER_TASK_NOT_INITIALIZED;
        return EGOLINK_SOS_SENDER_TASK_NOT_INITIALIZED;
    }
    /* Read the release-sequenced terminal marker first. If it is true, every
     * terminal lifecycle/status/phase store that precedes it must be visible
     * in this snapshot. If it is false and the worker commits concurrently,
     * callers simply poll again instead of observing terminal=true beside a
     * pre-terminal lifecycle. */
    snapshot->terminal_committed =
        atomic_load(&internal->terminal_committed);
    snapshot->lifecycle = (egolink_sos_delivery_sender_task_lifecycle_t)
        atomic_load(&internal->lifecycle);
    snapshot->phase = (egolink_sos_delivery_sender_task_phase_t)
        atomic_load(&internal->phase);
    snapshot->last_status = (egolink_sos_delivery_sender_task_status_t)
        atomic_load(&internal->last_status);
    if (!snapshot->terminal_committed &&
        snapshot->lifecycle == EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED) {
        /* Request publication is carried by lifecycle CAS. Do not let a
         * public caller write last_status after the worker can publish a
         * terminal status; derive this transient view instead. */
        snapshot->last_status = EGOLINK_SOS_SENDER_TASK_STOP_REQUESTED_STATUS;
    }
    snapshot->last_composition_status =
        (egolink_sos_delivery_composition_status_t)
            atomic_load(&internal->last_composition_status);
    snapshot->enabled = internal->config.enabled;
    snapshot->wake_pending = atomic_load(&internal->wake_pending);
    snapshot->execute_in_progress =
        atomic_load(&internal->execute_in_progress);
    snapshot->stop_requested = atomic_load(&internal->stop_requested);
    snapshot->owner_held = atomic_load(&internal->owner_held);
    snapshot->wake_generation = atomic_load(&internal->wake_generation);
    snapshot->consumed_wake_generation =
        atomic_load(&internal->consumed_wake_generation);
    snapshot->last_attempt_generation =
        atomic_load(&internal->last_attempt_generation);
    snapshot->active_attempt_generation =
        atomic_load(&internal->active_attempt_generation);
    snapshot->result_attempt_generation =
        atomic_load(&internal->result_attempt_generation);
    snapshot->notifications = atomic_load(&internal->notifications);
    snapshot->coalesced_notifications =
        atomic_load(&internal->coalesced_notifications);
    snapshot->stale_wake_generations_rejected =
        atomic_load(&internal->stale_wake_generations_rejected);
    snapshot->prepare_calls = atomic_load(&internal->prepare_calls);
    snapshot->execute_calls = atomic_load(&internal->execute_calls);
    snapshot->settle_calls = atomic_load(&internal->settle_calls);
    snapshot->recovery_calls = atomic_load(&internal->recovery_calls);
    snapshot->owner_timeouts = atomic_load(&internal->owner_timeouts);
    snapshot->stop_requests = atomic_load(&internal->stop_requests);
    snapshot->public_calls_in_flight =
        atomic_load(&internal->public_call_gate) &
        SENDER_PUBLIC_CALL_COUNT_MASK;
    snapshot->no_direct_outbox_or_journal_api = true;
    return snapshot->last_status;
}

const char *egolink_sos_delivery_sender_task_status_name(
    egolink_sos_delivery_sender_task_status_t status)
{
    static const char *const names[] = {
        "ok",
        "disabled",
        "stop_requested",
        "stopped",
        "stop_failed",
        "invalid_argument",
        "invalid_config",
        "build_disabled",
        "already_initialized",
        "not_initialized",
        "task_create_failed",
        "generation_exhausted",
        "public_call_limit",
    };
    return (unsigned int)status < sizeof(names) / sizeof(names[0])
        ? names[(unsigned int)status]
        : "invalid_status";
}

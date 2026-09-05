#include "sim7670_location_modem_owner.h"

#include <inttypes.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#include "esp_err.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include "sim7670_gnss.h"

#ifndef CONFIG_EGOLINK_SIM7670_LOCATION_MODEM_OWNER_ENABLED
#define CONFIG_EGOLINK_SIM7670_LOCATION_MODEM_OWNER_ENABLED 0
#endif

#define SIM7670_MODEM_OWNER_MAGIC UINT32_C(0x534D4F51)
#define SIM7670_MODEM_OWNER_TASK_NAME "ego_loc_modem"

typedef struct {
    uint32_t magic;
    bool enabled;
    bool start_claimed;
    bool task_created;
    bool uart_initialized;
    bool exclusive_owner_confirmed;
    bool startup_signalled;
    bool sequence_exhausted;
    int32_t owner_core_id;
    uint32_t task_priority;
    uint32_t startup_wait_timeout_ms;
    uint32_t owner_lock_timeout_ms;
    uint32_t idle_poll_ms;
    uint32_t recovery_retry_backoff_ms;
    uint32_t per_command_timeout_cap_ms;
    uint32_t gnss_power_off_timeout_ms;
    uint32_t max_commands_per_wake;
    uint64_t default_gnss_status_timeout_ms;
    uint64_t next_capture_sequence_id;
    egolink_location_runtime_publish_intent_t sensor_publish_intent;

    char device_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    char session_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    char stream_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    char monotonic_clock_domain_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    egolink_location_runtime_owner_t pipeline_owner;

    egolink_outbox_t *shared_outbox;
    egolink_location_outbox_adapter_t *location_adapter;
    egolink_p0_delivery_runtime_t *delivery_runtime;
    egolink_sim7670_location_modem_adapter_t modem_adapter;
    egolink_location_modem_executor_t executor;
    egolink_location_runtime_scratch_t scratch;
    egolink_location_modem_gnss_execute_fn native_gnss_execute;
    void *native_gnss_context;

    StaticSemaphore_t owner_mutex_storage;
    SemaphoreHandle_t owner_mutex;
    StaticSemaphore_t startup_signal_storage;
    SemaphoreHandle_t startup_signal;
    StaticTask_t task_storage;
    StackType_t task_stack[
        EGOLINK_SIM7670_LOCATION_MODEM_OWNER_TASK_STACK_BYTES];
    TaskHandle_t task_handle;

    atomic_bool execution_active;
    atomic_bool gnss_off_confirmed;
    atomic_bool cleanup_recovery_required;
    atomic_bool fatal_recovery_required;
    portMUX_TYPE metadata_lock;

    uint32_t cleanup_operation_token;
    uint64_t task_wakeups;
    uint64_t prepared_commands;
    uint64_t executed_commands;
    uint64_t settled_commands;
    uint64_t owner_lock_timeouts;
    uint64_t power_off_attempts;
    uint64_t power_off_confirmed;
    uint64_t power_off_unconfirmed;
    uint64_t recovery_attempts;
    uint64_t generated_capture_identities;
    egolink_modem_executor_status_t last_executor_status;
    egolink_sim7670_location_adapter_status_t last_adapter_status;
    sim7670_location_bounded_outcome_t last_power_off_outcome;
    sim7670_location_bounded_reason_t last_power_off_reason;
    egolink_sim7670_modem_owner_lifecycle_t lifecycle;
    egolink_sim7670_modem_owner_status_t last_status;
} sim7670_location_modem_owner_internal_t;

_Static_assert(
    sizeof(sim7670_location_modem_owner_internal_t) <=
        EGOLINK_SIM7670_LOCATION_MODEM_OWNER_CONTEXT_BYTES,
    "SIM7670 location modem owner context is too small");
_Static_assert(
    sizeof(StackType_t) == 1U,
    "ESP-IDF task stack depth/storage is byte-addressed on this target");

typedef enum {
    OWNER_DRIVE_IDLE = 0,
    OWNER_DRIVE_PROGRESS,
    OWNER_DRIVE_RETRY_LATER,
    OWNER_DRIVE_FATAL,
} owner_drive_result_t;

static sim7670_location_modem_owner_internal_t *internal_of(
    egolink_sim7670_location_modem_owner_t *owner)
{
    return (sim7670_location_modem_owner_internal_t *)(void *)owner->opaque;
}

static const sim7670_location_modem_owner_internal_t *internal_of_const(
    const egolink_sim7670_location_modem_owner_t *owner)
{
    return (const sim7670_location_modem_owner_internal_t *)(const void *)
        owner->opaque;
}

static bool valid_magic(
    const sim7670_location_modem_owner_internal_t *internal)
{
    uint32_t observed = UINT32_C(0);
    if (internal == NULL) {
        return false;
    }
    (void)memcpy(&observed, (const void *)internal, sizeof(observed));
    return observed == SIM7670_MODEM_OWNER_MAGIC;
}

static void increment_saturated(uint64_t *value)
{
    if (*value != UINT64_MAX) {
        ++(*value);
    }
}

static TickType_t ticks_for_ms(uint32_t milliseconds)
{
    TickType_t ticks = pdMS_TO_TICKS(milliseconds);
    if (milliseconds != UINT32_C(0) && ticks == (TickType_t)0) {
        ticks = (TickType_t)1;
    }
    return ticks;
}

static bool monotonic_now_ms(uint64_t *now_ms)
{
    if (now_ms == NULL) {
        return false;
    }
    const int64_t now_us = esp_timer_get_time();
    if (now_us < INT64_C(0)) {
        return false;
    }
    *now_ms = (uint64_t)now_us / UINT64_C(1000);
    return true;
}

static bool copy_runtime_text(
    egolink_location_runtime_text_t source,
    char destination[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY])
{
    if (source.data == NULL || source.length == 0U ||
        source.length > EGOLINK_LOCATION_RUNTIME_ID_MAX_BYTES ||
        memchr(source.data, '\0', source.length) != NULL) {
        return false;
    }
    (void)memcpy(destination, source.data, source.length);
    destination[source.length] = '\0';
    return true;
}

static egolink_location_runtime_text_t text_view(const char *value)
{
    const egolink_location_runtime_text_t view = {
        .data = value,
        .length = strlen(value),
    };
    return view;
}

static void record_status(
    sim7670_location_modem_owner_internal_t *internal,
    egolink_sim7670_modem_owner_status_t status)
{
    taskENTER_CRITICAL(&internal->metadata_lock);
    internal->last_status = status;
    taskEXIT_CRITICAL(&internal->metadata_lock);
}

static void record_executor_status(
    sim7670_location_modem_owner_internal_t *internal,
    egolink_modem_executor_status_t status)
{
    taskENTER_CRITICAL(&internal->metadata_lock);
    internal->last_executor_status = status;
    taskEXIT_CRITICAL(&internal->metadata_lock);
}

static void set_lifecycle(
    sim7670_location_modem_owner_internal_t *internal,
    egolink_sim7670_modem_owner_lifecycle_t lifecycle,
    egolink_sim7670_modem_owner_status_t status)
{
    taskENTER_CRITICAL(&internal->metadata_lock);
    internal->lifecycle = lifecycle;
    internal->last_status = status;
    taskEXIT_CRITICAL(&internal->metadata_lock);
}

static void latch_fatal_recovery(
    sim7670_location_modem_owner_internal_t *internal,
    egolink_sim7670_modem_owner_status_t status)
{
    atomic_store_explicit(
        &internal->fatal_recovery_required, true, memory_order_release);
    set_lifecycle(
        internal, EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED, status);
}

static bool never_cancel(void *context, uint32_t operation_token)
{
    (void)context;
    (void)operation_token;
    return false;
}

static uint32_t next_cleanup_token(
    sim7670_location_modem_owner_internal_t *internal)
{
    ++internal->cleanup_operation_token;
    if (internal->cleanup_operation_token == UINT32_C(0)) {
        internal->cleanup_operation_token = UINT32_C(1);
    }
    return internal->cleanup_operation_token;
}

static bool power_off_result_confirmed(
    sim7670_location_bounded_outcome_t returned_outcome,
    const sim7670_location_bounded_result_t *result)
{
    return result != NULL &&
        returned_outcome == SIM7670_LOCATION_BOUNDED_REPORT_READY &&
        result->outcome == returned_outcome &&
        result->reason == SIM7670_LOCATION_BOUNDED_REASON_NONE &&
        result->io_started && !result->cancel_before_io &&
        !result->cancelled_between_commands && !result->partial_or_unknown &&
        result->commands_attempted > UINT16_C(0) &&
        result->commands_attempted == result->commands_tx_complete &&
        result->commands_tx_complete == result->commands_completed;
}

static bool remaining_before_deadline_ms(
    const egolink_location_modem_sensor_request_t *request,
    uint32_t *remaining_ms)
{
    if (request == NULL || remaining_ms == NULL ||
        request->timeout_ms > UINT64_MAX - request->begin_time_ms) {
        return false;
    }
    uint64_t now_ms = UINT64_C(0);
    if (!monotonic_now_ms(&now_ms)) {
        return false;
    }
    const uint64_t deadline_ms =
        request->begin_time_ms + request->timeout_ms;
    if (now_ms >= deadline_ms) {
        return false;
    }
    const uint64_t remaining = deadline_ms - now_ms;
    if (remaining > UINT32_MAX) {
        return false;
    }
    *remaining_ms = (uint32_t)remaining;
    return true;
}

static void require_cleanup_recovery(
    sim7670_location_modem_owner_internal_t *internal)
{
    atomic_store_explicit(
        &internal->gnss_off_confirmed, false, memory_order_release);
    atomic_store_explicit(
        &internal->cleanup_recovery_required, true, memory_order_release);
    set_lifecycle(
        internal, EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED,
        EGOLINK_SIM7670_MODEM_OWNER_GNSS_POWER_OFF_UNCONFIRMED);
}

/* The exclusive owner task is the only caller of this function. */
static bool run_gnss_power_off(
    sim7670_location_modem_owner_internal_t *internal,
    bool recovery_attempt,
    uint32_t timeout_ms)
{
    if (!sim7670_at_backend_current_task_is_exclusive_owner()) {
        atomic_store_explicit(
            &internal->gnss_off_confirmed, false, memory_order_release);
        atomic_store_explicit(
            &internal->cleanup_recovery_required, true,
            memory_order_release);
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_EXCLUSIVE_OWNER_MISMATCH);
        return false;
    }

    const sim7670_location_bounded_request_t request = {
        .timeout_ms = timeout_ms,
        .per_command_timeout_cap_ms = internal->per_command_timeout_cap_ms,
        .cancel_requested = never_cancel,
        .cancel_context = internal,
        .operation_token = next_cleanup_token(internal),
    };
    sim7670_location_bounded_result_t result;
    sim7670_location_bounded_result_init(&result);
    const sim7670_location_bounded_outcome_t outcome =
        sim7670_gnss_power_off_bounded(&request, &result);
    const bool confirmed = power_off_result_confirmed(outcome, &result);

    taskENTER_CRITICAL(&internal->metadata_lock);
    increment_saturated(&internal->power_off_attempts);
    if (recovery_attempt) {
        increment_saturated(&internal->recovery_attempts);
    }
    if (confirmed) {
        increment_saturated(&internal->power_off_confirmed);
    } else {
        increment_saturated(&internal->power_off_unconfirmed);
    }
    internal->last_power_off_outcome = outcome;
    internal->last_power_off_reason = result.reason;
    taskEXIT_CRITICAL(&internal->metadata_lock);

    atomic_store_explicit(
        &internal->gnss_off_confirmed, confirmed, memory_order_release);
    atomic_store_explicit(
        &internal->cleanup_recovery_required, !confirmed,
        memory_order_release);
    if (!confirmed) {
        set_lifecycle(
            internal, EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED,
            EGOLINK_SIM7670_MODEM_OWNER_GNSS_POWER_OFF_UNCONFIRMED);
    }
    return confirmed;
}

/*
 * O calls this only after releasing the external owner mutex. The original P
 * callback gets a reduced acquisition budget; the reserved tail is consumed
 * by one never-cancelled GNSS power-off compensation. A usable report cannot
 * escape unless that compensation is confirmed inside O's original bound.
 */
static egolink_modem_callback_outcome_t execute_gnss_with_power_off(
    void *context,
    const egolink_location_modem_sensor_request_t *request,
    sim7670_gnss_report_t *report,
    uint64_t *completion_time_ms)
{
    if (report != NULL) {
        sim7670_gnss_report_init(report);
    }
    if (completion_time_ms != NULL) {
        *completion_time_ms = UINT64_C(0);
    }
    if (context == NULL || request == NULL || report == NULL ||
        completion_time_ms == NULL) {
        return EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
    }
    sim7670_location_modem_owner_internal_t *internal =
        (sim7670_location_modem_owner_internal_t *)context;
    if (!valid_magic(internal)) {
        return EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
    }
    if (internal->native_gnss_execute == NULL ||
        !sim7670_at_backend_current_task_is_exclusive_owner()) {
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_EXCLUSIVE_OWNER_MISMATCH);
        return EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
    }

    uint32_t remaining_ms = UINT32_C(0);
    if (!remaining_before_deadline_ms(request, &remaining_ms) ||
        remaining_ms <= internal->gnss_power_off_timeout_ms) {
        /* No modem effect occurred, so no compensating command is needed. */
        return EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
    }

    egolink_modem_callback_outcome_t acquisition_outcome =
        EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
    uint64_t acquisition_completion_ms = UINT64_C(0);
    egolink_location_modem_sensor_request_t acquisition_request = *request;
    acquisition_request.timeout_ms = request->timeout_ms -
        (uint64_t)internal->gnss_power_off_timeout_ms;
    atomic_store_explicit(
        &internal->gnss_off_confirmed, false, memory_order_release);
    acquisition_outcome = internal->native_gnss_execute(
        internal->native_gnss_context, &acquisition_request, report,
        &acquisition_completion_ms);

    bool power_off_confirmed = false;
    if (remaining_before_deadline_ms(request, &remaining_ms)) {
        const uint32_t cleanup_timeout_ms =
            remaining_ms < internal->gnss_power_off_timeout_ms
            ? remaining_ms
            : internal->gnss_power_off_timeout_ms;
        power_off_confirmed = run_gnss_power_off(
            internal, false, cleanup_timeout_ms);
    } else {
        /* Acquisition may have powered GNSS. Retry cleanup outside this
         * exhausted O bound before any ordinary modem work is admitted. */
        require_cleanup_recovery(internal);
    }
    uint64_t completion = UINT64_C(0);
    const bool clock_valid = monotonic_now_ms(&completion);
    *completion_time_ms = clock_valid ? completion : acquisition_completion_ms;

    const bool within_original_bound = clock_valid &&
        completion >= request->begin_time_ms &&
        completion - request->begin_time_ms <= request->timeout_ms;
    if (!power_off_confirmed || !within_original_bound) {
        sim7670_gnss_report_init(report);
        return EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
    }
    if (acquisition_outcome == EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE) {
        return acquisition_outcome;
    }
    sim7670_gnss_report_init(report);
    if (acquisition_outcome ==
            EGOLINK_MODEM_CALLBACK_COOPERATIVE_CANCELLED &&
        request->cancel_requested != NULL &&
        request->cancel_requested(
            request->cancel_context, request->generation, request->kind)) {
        return acquisition_outcome;
    }
    /* The compensating AT command is an effect, so DEFINITE_NO_EFFECT cannot
     * describe this composite callback even when acquisition never started. */
    return EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
}

static bool build_capture_identity(
    sim7670_location_modem_owner_internal_t *internal,
    uint64_t completion_time_ms,
    egolink_location_hardware_identity_t *identity,
    char observation_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY])
{
    if (identity == NULL || observation_id == NULL ||
        completion_time_ms >
            EGOLINK_LOCATION_RUNTIME_INT64_MAX / UINT64_C(1000000)) {
        return false;
    }
    uint64_t sequence_id = UINT64_C(0);
    taskENTER_CRITICAL(&internal->metadata_lock);
    if (!internal->sequence_exhausted &&
        internal->next_capture_sequence_id > UINT64_C(0) &&
        internal->next_capture_sequence_id <=
            EGOLINK_LOCATION_RUNTIME_INT64_MAX) {
        sequence_id = internal->next_capture_sequence_id;
        if (sequence_id == EGOLINK_LOCATION_RUNTIME_INT64_MAX) {
            internal->sequence_exhausted = true;
        } else {
            internal->next_capture_sequence_id = sequence_id + UINT64_C(1);
        }
        increment_saturated(&internal->generated_capture_identities);
    }
    taskEXIT_CRITICAL(&internal->metadata_lock);
    if (sequence_id == UINT64_C(0)) {
        return false;
    }
    const int written = snprintf(
        observation_id, EGOLINK_LOCATION_RUNTIME_ID_CAPACITY,
        "locq-%" PRIu64, sequence_id);
    if (written <= 0 ||
        (size_t)written >= EGOLINK_LOCATION_RUNTIME_ID_CAPACITY) {
        return false;
    }

    (void)memset(identity, 0, sizeof(*identity));
    identity->device_id = text_view(internal->device_id);
    identity->boot_count = internal->pipeline_owner.boot_count;
    identity->session_id = text_view(internal->session_id);
    identity->stream_id = text_view(internal->stream_id);
    identity->sequence_id = sequence_id;
    identity->observation_id = text_view(observation_id);
    identity->source_event_time_ms = completion_time_ms;
    identity->source_event_time_ns =
        completion_time_ms * UINT64_C(1000000);
    identity->source_event_time_source =
        EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS;
    identity->monotonic_clock_domain_id =
        text_view(internal->monotonic_clock_domain_id);
    identity->publish_intent = internal->sensor_publish_intent;

    return true;
}

static void update_sequence_after_external_input(
    sim7670_location_modem_owner_internal_t *internal,
    const egolink_location_hardware_mapped_input_t *mapped,
    const egolink_location_modem_process_result_t *result)
{
    const bool accepted = result->input_committed ||
        result->device_status ==
            EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT;
    if (!accepted) {
        return;
    }
    const uint64_t sequence_id = mapped->input.identity.sequence_id;
    taskENTER_CRITICAL(&internal->metadata_lock);
    if (sequence_id >= internal->next_capture_sequence_id) {
        if (sequence_id >= EGOLINK_LOCATION_RUNTIME_INT64_MAX) {
            internal->sequence_exhausted = true;
        } else {
            internal->next_capture_sequence_id = sequence_id + UINT64_C(1);
        }
    }
    taskEXIT_CRITICAL(&internal->metadata_lock);
}

static void update_sequence_after_durable_sos(
    sim7670_location_modem_owner_internal_t *internal,
    const egolink_location_runtime_identity_t *identity,
    const egolink_location_modem_durable_sos_result_t *result)
{
    if (!result->location_input_committed &&
        !result->location_input_duplicate) {
        return;
    }
    taskENTER_CRITICAL(&internal->metadata_lock);
    if (identity->sequence_id >= internal->next_capture_sequence_id) {
        if (identity->sequence_id >= EGOLINK_LOCATION_RUNTIME_INT64_MAX) {
            internal->sequence_exhausted = true;
        } else {
            internal->next_capture_sequence_id =
                identity->sequence_id + UINT64_C(1);
        }
    }
    taskEXIT_CRITICAL(&internal->metadata_lock);
}

static void notify_owner_task(
    sim7670_location_modem_owner_internal_t *internal)
{
    TaskHandle_t task = NULL;
    taskENTER_CRITICAL(&internal->metadata_lock);
    task = internal->task_handle;
    taskEXIT_CRITICAL(&internal->metadata_lock);
    if (task != NULL) {
        xTaskNotifyGive(task);
    }
}

static owner_drive_result_t settle_ready_command(
    sim7670_location_modem_owner_internal_t *internal,
    const egolink_location_modem_execute_result_t *execute_result,
    uint64_t fallback_now_ms)
{
    egolink_location_hardware_identity_t identity;
    char observation_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    const egolink_location_hardware_identity_t *identity_pointer = NULL;
    if (execute_result != NULL && execute_result->callback_called &&
        execute_result->callback_contract_valid &&
        execute_result->callback_outcome ==
            EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE) {
        if (!build_capture_identity(
                internal, execute_result->completion_time_ms, &identity,
                observation_id)) {
            record_status(
                internal, EGOLINK_SIM7670_MODEM_OWNER_IDENTITY_EXHAUSTED);
        } else {
            identity_pointer = &identity;
        }
    }

    uint64_t settle_now_ms = fallback_now_ms;
    (void)monotonic_now_ms(&settle_now_ms);
    egolink_location_modem_settle_result_t settle_result;
    const egolink_modem_executor_status_t settle_status =
        egolink_location_modem_executor_settle_prepared(
            &internal->executor, identity_pointer, settle_now_ms,
            &internal->scratch, &settle_result);
    record_executor_status(internal, settle_status);
    taskENTER_CRITICAL(&internal->metadata_lock);
    increment_saturated(&internal->settled_commands);
    taskEXIT_CRITICAL(&internal->metadata_lock);

    if (identity_pointer == NULL && execute_result != NULL &&
        execute_result->callback_outcome ==
            EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE) {
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_IDENTITY_EXHAUSTED);
        return OWNER_DRIVE_FATAL;
    }
    if (settle_status != EGOLINK_MODEM_EXECUTOR_SETTLED) {
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
        return OWNER_DRIVE_FATAL;
    }
    if (atomic_load_explicit(
            &internal->cleanup_recovery_required,
            memory_order_acquire)) {
        return OWNER_DRIVE_RETRY_LATER;
    }
    if (settle_result.p0_result.durable_record_retained) {
        return OWNER_DRIVE_RETRY_LATER;
    }
    return OWNER_DRIVE_PROGRESS;
}

static owner_drive_result_t drive_one_command(
    sim7670_location_modem_owner_internal_t *internal)
{
    (void)xSemaphoreTake(internal->owner_mutex, portMAX_DELAY);
    uint64_t prepare_now_ms = UINT64_C(0);
    if (!monotonic_now_ms(&prepare_now_ms)) {
        (void)xSemaphoreGive(internal->owner_mutex);
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
        return OWNER_DRIVE_FATAL;
    }

    egolink_location_modem_prepare_result_t prepare_result;
    const egolink_modem_executor_status_t prepare_status =
        egolink_location_modem_executor_prepare_next(
            &internal->executor, prepare_now_ms, &prepare_result);
    record_executor_status(internal, prepare_status);
    if (prepare_status == EGOLINK_MODEM_EXECUTOR_NO_COMMAND) {
        (void)xSemaphoreGive(internal->owner_mutex);
        return OWNER_DRIVE_IDLE;
    }
    if (prepare_status == EGOLINK_MODEM_EXECUTOR_ROUTE_REQUEUED) {
        (void)xSemaphoreGive(internal->owner_mutex);
        return OWNER_DRIVE_PROGRESS;
    }
    if (prepare_status == EGOLINK_MODEM_EXECUTOR_DELIVERY_NO_DUE_RECORD ||
        prepare_status == EGOLINK_MODEM_EXECUTOR_DELIVERY_RETAINED) {
        (void)xSemaphoreGive(internal->owner_mutex);
        return OWNER_DRIVE_RETRY_LATER;
    }
    if (prepare_status == EGOLINK_MODEM_EXECUTOR_RESULT_READY) {
        const owner_drive_result_t result = settle_ready_command(
            internal, NULL, prepare_now_ms);
        (void)xSemaphoreGive(internal->owner_mutex);
        return result;
    }
    if (prepare_status != EGOLINK_MODEM_EXECUTOR_PREPARED) {
        (void)xSemaphoreGive(internal->owner_mutex);
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
        return OWNER_DRIVE_FATAL;
    }

    taskENTER_CRITICAL(&internal->metadata_lock);
    increment_saturated(&internal->prepared_commands);
    taskEXIT_CRITICAL(&internal->metadata_lock);
    atomic_store_explicit(
        &internal->execution_active, true, memory_order_release);
    (void)xSemaphoreGive(internal->owner_mutex);

    uint64_t begin_time_ms = UINT64_C(0);
    if (!monotonic_now_ms(&begin_time_ms)) {
        begin_time_ms = prepare_now_ms;
    }
    egolink_location_modem_execute_result_t execute_result;
    const egolink_modem_executor_status_t execute_status =
        egolink_location_modem_executor_execute_prepared(
            &internal->executor, begin_time_ms, &execute_result);
    record_executor_status(internal, execute_status);
    taskENTER_CRITICAL(&internal->metadata_lock);
    increment_saturated(&internal->executed_commands);
    taskEXIT_CRITICAL(&internal->metadata_lock);

    /* Only durable-SOS ingress may have acquired this mutex while execute ran. */
    (void)xSemaphoreTake(internal->owner_mutex, portMAX_DELAY);
    const owner_drive_result_t result = settle_ready_command(
        internal, &execute_result, begin_time_ms);
    atomic_store_explicit(
        &internal->execution_active, false, memory_order_release);
    (void)xSemaphoreGive(internal->owner_mutex);
    return result;
}

static void signal_startup_once(
    sim7670_location_modem_owner_internal_t *internal)
{
    if (!internal->startup_signalled) {
        internal->startup_signalled = true;
        (void)xSemaphoreGive(internal->startup_signal);
    }
}

static void owner_task_main(void *context)
{
    sim7670_location_modem_owner_internal_t *internal =
        (sim7670_location_modem_owner_internal_t *)context;

    /* start() stores the returned handle before releasing this barrier. */
    (void)ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    const esp_err_t init_status =
        sim7670_at_backend_init_exclusive_current_task();
    const bool exclusive = init_status == ESP_OK &&
        sim7670_at_backend_current_task_is_exclusive_owner();
    taskENTER_CRITICAL(&internal->metadata_lock);
    internal->uart_initialized = init_status == ESP_OK;
    internal->exclusive_owner_confirmed = exclusive;
    taskEXIT_CRITICAL(&internal->metadata_lock);
    if (!exclusive) {
        latch_fatal_recovery(
            internal,
            init_status == ESP_OK
                ? EGOLINK_SIM7670_MODEM_OWNER_EXCLUSIVE_OWNER_MISMATCH
                : EGOLINK_SIM7670_MODEM_OWNER_UART_INIT_FAILED);
        signal_startup_once(internal);
    } else if (run_gnss_power_off(
                   internal, false,
                   internal->gnss_power_off_timeout_ms)) {
        set_lifecycle(
            internal, EGOLINK_SIM7670_MODEM_OWNER_ACTIVE,
            EGOLINK_SIM7670_MODEM_OWNER_STARTED);
        signal_startup_once(internal);
    } else {
        signal_startup_once(internal);
    }

    for (;;) {
        if (atomic_load_explicit(
                &internal->fatal_recovery_required,
                memory_order_acquire)) {
            (void)ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
            continue;
        }
        if (atomic_load_explicit(
                &internal->cleanup_recovery_required,
                memory_order_acquire)) {
            (void)ulTaskNotifyTake(
                pdTRUE, ticks_for_ms(internal->recovery_retry_backoff_ms));
            taskENTER_CRITICAL(&internal->metadata_lock);
            increment_saturated(&internal->task_wakeups);
            taskEXIT_CRITICAL(&internal->metadata_lock);
            if (!run_gnss_power_off(
                    internal, true,
                    internal->gnss_power_off_timeout_ms)) {
                continue;
            }
            if (atomic_load_explicit(
                    &internal->fatal_recovery_required,
                    memory_order_acquire)) {
                continue;
            }
            set_lifecycle(
                internal, EGOLINK_SIM7670_MODEM_OWNER_ACTIVE,
                EGOLINK_SIM7670_MODEM_OWNER_OK);
        }

        owner_drive_result_t drive_result = OWNER_DRIVE_IDLE;
        for (uint32_t index = UINT32_C(0);
             index < internal->max_commands_per_wake; ++index) {
            drive_result = drive_one_command(internal);
            if (drive_result != OWNER_DRIVE_PROGRESS) {
                break;
            }
        }
        if (drive_result == OWNER_DRIVE_FATAL) {
            continue;
        }
        const uint32_t wait_ms =
            drive_result == OWNER_DRIVE_RETRY_LATER
            ? internal->recovery_retry_backoff_ms
            : internal->idle_poll_ms;
        (void)ulTaskNotifyTake(pdTRUE, ticks_for_ms(wait_ms));
        taskENTER_CRITICAL(&internal->metadata_lock);
        increment_saturated(&internal->task_wakeups);
        taskEXIT_CRITICAL(&internal->metadata_lock);
    }
}

static bool valid_publish_intent(
    egolink_location_runtime_publish_intent_t publish_intent)
{
    return publish_intent >= EGOLINK_LOCATION_RUNTIME_PUBLISH_NONE &&
        publish_intent <= EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT;
}

static bool valid_enabled_config(
    const egolink_sim7670_location_modem_owner_config_t *config)
{
    return config->owner_core_id >= INT32_C(0) &&
        config->owner_core_id < (int32_t)portNUM_PROCESSORS &&
        config->task_priority > UINT32_C(0) &&
        config->task_priority < (uint32_t)configMAX_PRIORITIES &&
        config->startup_wait_timeout_ms > UINT32_C(0) &&
        config->startup_wait_timeout_ms <=
            SIM7670_LOCATION_BOUNDED_TIMEOUT_MAX_MS &&
        config->owner_lock_timeout_ms > UINT32_C(0) &&
        config->owner_lock_timeout_ms <=
            SIM7670_LOCATION_BOUNDED_TIMEOUT_MAX_MS &&
        config->idle_poll_ms > UINT32_C(0) &&
        config->recovery_retry_backoff_ms > UINT32_C(0) &&
        config->per_command_timeout_cap_ms > UINT32_C(0) &&
        config->per_command_timeout_cap_ms <=
            SIM7670_LOCATION_BOUNDED_COMMAND_CAP_MAX_MS &&
        config->gnss_power_off_timeout_ms > UINT32_C(0) &&
        config->gnss_power_off_timeout_ms <=
            SIM7670_LOCATION_BOUNDED_TIMEOUT_MAX_MS &&
        config->max_commands_per_wake > UINT32_C(0) &&
        config->max_commands_per_wake <=
            EGOLINK_SIM7670_LOCATION_MODEM_OWNER_MAX_COMMANDS_PER_WAKE &&
        config->default_gnss_status_timeout_ms > UINT64_C(0) &&
        config->default_gnss_status_timeout_ms <=
            EGOLINK_LOCATION_MODEM_EXECUTOR_MAX_TIMEOUT_MS &&
        config->first_sequence_id > UINT64_C(0) &&
        config->first_sequence_id <= EGOLINK_LOCATION_RUNTIME_INT64_MAX &&
        config->pipeline_owner.clock_domain ==
            EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC &&
        config->pipeline_owner.boot_count <=
            EGOLINK_LOCATION_RUNTIME_INT64_MAX &&
        valid_publish_intent(config->sensor_publish_intent);
}

void egolink_sim7670_location_modem_owner_default_config(
    egolink_sim7670_location_modem_owner_config_t *config)
{
    if (config == NULL) {
        return;
    }
    (void)memset(config, 0, sizeof(*config));
    config->enabled = false;
    config->owner_core_id = INT32_C(-1);
    config->task_priority =
        EGOLINK_SIM7670_LOCATION_MODEM_OWNER_DEFAULT_TASK_PRIORITY;
    config->startup_wait_timeout_ms = UINT32_C(5000);
    config->owner_lock_timeout_ms = UINT32_C(1000);
    config->idle_poll_ms = UINT32_C(1000);
    config->recovery_retry_backoff_ms = UINT32_C(5000);
    config->per_command_timeout_cap_ms =
        EGOLINK_SIM7670_LOCATION_DEFAULT_COMMAND_CAP_MS;
    config->gnss_power_off_timeout_ms = UINT32_C(3000);
    config->max_commands_per_wake = UINT32_C(4);
    config->default_gnss_status_timeout_ms =
        EGOLINK_LOCATION_MODEM_EXECUTOR_DEFAULT_STATUS_TIMEOUT_MS;
    config->first_sequence_id = UINT64_C(1);
    config->pipeline_owner.clock_domain =
        EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC;
    config->sensor_publish_intent = EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT;
}

egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_init(
    egolink_sim7670_location_modem_owner_t *owner,
    const egolink_sim7670_location_modem_owner_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter,
    egolink_p0_delivery_runtime_t *delivery_runtime)
{
    if (owner == NULL || config == NULL) {
        return EGOLINK_SIM7670_MODEM_OWNER_INVALID_ARGUMENT;
    }
    if (valid_magic(internal_of(owner))) {
        return EGOLINK_SIM7670_MODEM_OWNER_ALREADY_INITIALIZED;
    }
    (void)memset(owner, 0, sizeof(*owner));
    sim7670_location_modem_owner_internal_t *internal = internal_of(owner);
    internal->magic = SIM7670_MODEM_OWNER_MAGIC;
    internal->enabled = config->enabled;
    internal->owner_core_id = config->owner_core_id;
    internal->last_executor_status = EGOLINK_MODEM_EXECUTOR_NOT_INITIALIZED;
    internal->last_adapter_status = EGOLINK_SIM7670_ADAPTER_UNINITIALIZED;
    internal->last_power_off_outcome =
        SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN;
    internal->last_power_off_reason =
        SIM7670_LOCATION_BOUNDED_REASON_INVALID_ARGUMENT;
    internal->lifecycle = EGOLINK_SIM7670_MODEM_OWNER_DISABLED;
    internal->last_status = EGOLINK_SIM7670_MODEM_OWNER_DISABLED_STATUS;
    portMUX_INITIALIZE(&internal->metadata_lock);
    atomic_init(&internal->execution_active, false);
    atomic_init(&internal->gnss_off_confirmed, false);
    atomic_init(&internal->cleanup_recovery_required, false);
    atomic_init(&internal->fatal_recovery_required, false);

    if (!config->enabled) {
        return EGOLINK_SIM7670_MODEM_OWNER_DISABLED_STATUS;
    }
#if !CONFIG_EGOLINK_SIM7670_LOCATION_MODEM_OWNER_ENABLED
    internal->enabled = false;
    internal->last_status = EGOLINK_SIM7670_MODEM_OWNER_BUILD_DISABLED;
    return internal->last_status;
#endif
    if (shared_outbox == NULL || location_adapter == NULL ||
        delivery_runtime == NULL || !valid_enabled_config(config) ||
        !copy_runtime_text(
            config->pipeline_owner.device_id, internal->device_id) ||
        !copy_runtime_text(
            config->pipeline_owner.session_id, internal->session_id) ||
        !copy_runtime_text(
            config->pipeline_owner.stream_id, internal->stream_id) ||
        !copy_runtime_text(
            config->pipeline_owner.monotonic_clock_domain_id,
            internal->monotonic_clock_domain_id)) {
        internal->enabled = false;
        internal->last_status = EGOLINK_SIM7670_MODEM_OWNER_INVALID_CONFIG;
        return internal->last_status;
    }

    internal->task_priority = config->task_priority;
    internal->startup_wait_timeout_ms = config->startup_wait_timeout_ms;
    internal->owner_lock_timeout_ms = config->owner_lock_timeout_ms;
    internal->idle_poll_ms = config->idle_poll_ms;
    internal->recovery_retry_backoff_ms =
        config->recovery_retry_backoff_ms;
    internal->per_command_timeout_cap_ms =
        config->per_command_timeout_cap_ms;
    internal->gnss_power_off_timeout_ms =
        config->gnss_power_off_timeout_ms;
    internal->max_commands_per_wake = config->max_commands_per_wake;
    internal->default_gnss_status_timeout_ms =
        config->default_gnss_status_timeout_ms;
    internal->next_capture_sequence_id = config->first_sequence_id;
    internal->sensor_publish_intent = config->sensor_publish_intent;
    internal->pipeline_owner.device_id = text_view(internal->device_id);
    internal->pipeline_owner.boot_count = config->pipeline_owner.boot_count;
    internal->pipeline_owner.session_id = text_view(internal->session_id);
    internal->pipeline_owner.stream_id = text_view(internal->stream_id);
    internal->pipeline_owner.clock_domain =
        EGOLINK_LOCATION_RUNTIME_CLOCK_BOOT_MONOTONIC;
    internal->pipeline_owner.monotonic_clock_domain_id =
        text_view(internal->monotonic_clock_domain_id);
    internal->shared_outbox = shared_outbox;
    internal->location_adapter = location_adapter;
    internal->delivery_runtime = delivery_runtime;
    internal->owner_mutex =
        xSemaphoreCreateMutexStatic(&internal->owner_mutex_storage);
    internal->startup_signal =
        xSemaphoreCreateBinaryStatic(&internal->startup_signal_storage);
    if (internal->owner_mutex == NULL || internal->startup_signal == NULL) {
        internal->enabled = false;
        internal->last_status = EGOLINK_SIM7670_MODEM_OWNER_INVALID_CONFIG;
        return internal->last_status;
    }

    egolink_sim7670_location_modem_adapter_config_t adapter_config;
    egolink_sim7670_location_modem_adapter_bounded_config(
        &adapter_config, internal->owner_core_id,
        internal->per_command_timeout_cap_ms);
    internal->last_adapter_status =
        egolink_sim7670_location_modem_adapter_init(
            &internal->modem_adapter, &adapter_config);
    if (internal->last_adapter_status != EGOLINK_SIM7670_ADAPTER_READY) {
        internal->enabled = false;
        internal->last_status =
            EGOLINK_SIM7670_MODEM_OWNER_ADAPTER_INIT_FAILED;
        return internal->last_status;
    }

    egolink_location_modem_executor_config_t executor_config;
    egolink_location_modem_executor_default_config(&executor_config);
    executor_config.enabled = true;
    executor_config.pipeline_owner = internal->pipeline_owner;
    executor_config.default_gnss_status_timeout_ms =
        internal->default_gnss_status_timeout_ms;
    internal->last_adapter_status =
        egolink_sim7670_location_modem_adapter_bind_executor_config(
            &internal->modem_adapter, &executor_config);
    if (internal->last_adapter_status != EGOLINK_SIM7670_ADAPTER_READY ||
        executor_config.execute_gnss == NULL ||
        executor_config.execute_cell == NULL) {
        internal->enabled = false;
        internal->last_status =
            EGOLINK_SIM7670_MODEM_OWNER_ADAPTER_INIT_FAILED;
        return internal->last_status;
    }
    internal->native_gnss_execute = executor_config.execute_gnss;
    internal->native_gnss_context = executor_config.gnss_context;
    executor_config.execute_gnss = execute_gnss_with_power_off;
    executor_config.gnss_context = internal;

    internal->last_executor_status = egolink_location_modem_executor_init(
        &internal->executor, &executor_config, shared_outbox,
        location_adapter, delivery_runtime);
    if (internal->last_executor_status != EGOLINK_MODEM_EXECUTOR_OK) {
        internal->enabled = false;
        internal->last_status =
            internal->last_executor_status ==
                EGOLINK_MODEM_EXECUTOR_DEPENDENCY_MISMATCH
            ? EGOLINK_SIM7670_MODEM_OWNER_DEPENDENCY_MISMATCH
            : EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_INIT_FAILED;
        return internal->last_status;
    }

    internal->lifecycle = EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED;
    internal->last_status =
        EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED_STATUS;
    return internal->last_status;
}

egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_start(
    egolink_sim7670_location_modem_owner_t *owner)
{
    if (owner == NULL) {
        return EGOLINK_SIM7670_MODEM_OWNER_INVALID_ARGUMENT;
    }
    sim7670_location_modem_owner_internal_t *internal = internal_of(owner);
    if (!valid_magic(internal)) {
        return EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED;
    }
    bool already_started = false;
    egolink_sim7670_modem_owner_lifecycle_t lifecycle;
    taskENTER_CRITICAL(&internal->metadata_lock);
    lifecycle = internal->lifecycle;
    if (internal->start_claimed || internal->task_created) {
        already_started = true;
    } else if (internal->enabled &&
               lifecycle != EGOLINK_SIM7670_MODEM_OWNER_DISABLED) {
        /* Claim the one static TCB/stack before task creation. */
        internal->start_claimed = true;
    }
    taskEXIT_CRITICAL(&internal->metadata_lock);
    if (!internal->enabled ||
        lifecycle == EGOLINK_SIM7670_MODEM_OWNER_DISABLED) {
        return EGOLINK_SIM7670_MODEM_OWNER_DISABLED_STATUS;
    }
    if (already_started) {
        return EGOLINK_SIM7670_MODEM_OWNER_ALREADY_STARTED;
    }
    set_lifecycle(
        internal, EGOLINK_SIM7670_MODEM_OWNER_STARTING,
        EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED_STATUS);
    TaskHandle_t task = xTaskCreateStaticPinnedToCore(
        owner_task_main, SIM7670_MODEM_OWNER_TASK_NAME,
        EGOLINK_SIM7670_LOCATION_MODEM_OWNER_TASK_STACK_BYTES, internal,
        (UBaseType_t)internal->task_priority, internal->task_stack,
        &internal->task_storage, (BaseType_t)internal->owner_core_id);
    if (task == NULL) {
        taskENTER_CRITICAL(&internal->metadata_lock);
        internal->start_claimed = false;
        internal->lifecycle = EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED;
        internal->last_status =
            EGOLINK_SIM7670_MODEM_OWNER_TASK_CREATE_FAILED;
        taskEXIT_CRITICAL(&internal->metadata_lock);
        return EGOLINK_SIM7670_MODEM_OWNER_TASK_CREATE_FAILED;
    }
    taskENTER_CRITICAL(&internal->metadata_lock);
    internal->task_handle = task;
    internal->task_created = true;
    taskEXIT_CRITICAL(&internal->metadata_lock);
    xTaskNotifyGive(task);

    if (xSemaphoreTake(
            internal->startup_signal,
            ticks_for_ms(internal->startup_wait_timeout_ms)) != pdTRUE) {
        record_status(internal, EGOLINK_SIM7670_MODEM_OWNER_START_TIMEOUT);
        return EGOLINK_SIM7670_MODEM_OWNER_START_TIMEOUT;
    }

    egolink_sim7670_location_modem_owner_snapshot_t snapshot;
    const egolink_sim7670_modem_owner_status_t status =
        egolink_sim7670_location_modem_owner_current_status(owner, &snapshot);
    if (status != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        return status;
    }
    if (snapshot.lifecycle == EGOLINK_SIM7670_MODEM_OWNER_ACTIVE) {
        return EGOLINK_SIM7670_MODEM_OWNER_STARTED;
    }
    return snapshot.last_status;
}

static egolink_sim7670_modem_owner_status_t external_gate(
    sim7670_location_modem_owner_internal_t *internal,
    bool allow_execution,
    bool allow_recovery)
{
    if (!valid_magic(internal)) {
        return EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED;
    }
    egolink_sim7670_modem_owner_lifecycle_t lifecycle;
    bool task_created;
    taskENTER_CRITICAL(&internal->metadata_lock);
    lifecycle = internal->lifecycle;
    task_created = internal->task_created;
    taskEXIT_CRITICAL(&internal->metadata_lock);
    if (!internal->enabled ||
        lifecycle == EGOLINK_SIM7670_MODEM_OWNER_DISABLED) {
        return EGOLINK_SIM7670_MODEM_OWNER_DISABLED_STATUS;
    }
    if (!task_created ||
        lifecycle == EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED ||
        lifecycle == EGOLINK_SIM7670_MODEM_OWNER_STARTING) {
        return EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED;
    }
    if (atomic_load_explicit(
            &internal->fatal_recovery_required, memory_order_acquire)) {
        return EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED_STATUS;
    }
    if (lifecycle == EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED &&
        (!allow_recovery || !atomic_load_explicit(
            &internal->cleanup_recovery_required,
            memory_order_acquire))) {
        return EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED_STATUS;
    }
    if (!allow_execution && atomic_load_explicit(
            &internal->execution_active, memory_order_acquire)) {
        return EGOLINK_SIM7670_MODEM_OWNER_IN_FLIGHT;
    }
    return EGOLINK_SIM7670_MODEM_OWNER_OK;
}

static bool take_external_owner(
    sim7670_location_modem_owner_internal_t *internal)
{
    if (xSemaphoreTake(
            internal->owner_mutex,
            ticks_for_ms(internal->owner_lock_timeout_ms)) == pdTRUE) {
        return true;
    }
    taskENTER_CRITICAL(&internal->metadata_lock);
    increment_saturated(&internal->owner_lock_timeouts);
    internal->last_status =
        EGOLINK_SIM7670_MODEM_OWNER_OWNER_LOCK_TIMEOUT;
    taskEXIT_CRITICAL(&internal->metadata_lock);
    return false;
}

egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_process_mapped_input(
    egolink_sim7670_location_modem_owner_t *owner,
    const egolink_location_hardware_mapped_input_t *mapped,
    uint64_t outbox_now_ms,
    egolink_location_modem_process_result_t *result)
{
    if (owner == NULL || mapped == NULL || result == NULL) {
        return EGOLINK_SIM7670_MODEM_OWNER_INVALID_ARGUMENT;
    }
    sim7670_location_modem_owner_internal_t *internal = internal_of(owner);
    egolink_sim7670_modem_owner_status_t gate =
        external_gate(internal, false, false);
    if (gate != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        return gate;
    }
    if (!take_external_owner(internal)) {
        return EGOLINK_SIM7670_MODEM_OWNER_OWNER_LOCK_TIMEOUT;
    }
    gate = external_gate(internal, false, false);
    if (gate != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        (void)xSemaphoreGive(internal->owner_mutex);
        return gate;
    }
    const egolink_modem_executor_status_t executor_status =
        egolink_location_modem_executor_process_mapped_input(
            &internal->executor, mapped, outbox_now_ms, &internal->scratch,
            result);
    update_sequence_after_external_input(internal, mapped, result);
    record_executor_status(internal, executor_status);
    (void)xSemaphoreGive(internal->owner_mutex);
    notify_owner_task(internal);
    if (executor_status ==
        EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED) {
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
        return EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED_STATUS;
    }
    if (executor_status ==
        EGOLINK_MODEM_EXECUTOR_INPUT_COMMITTED_QUEUE_PARTIAL) {
        record_status(
            internal, EGOLINK_SIM7670_MODEM_OWNER_MAPPED_INPUT_PARTIAL);
        return EGOLINK_SIM7670_MODEM_OWNER_MAPPED_INPUT_PARTIAL;
    }
    if (result->input_committed ||
        result->device_status ==
            EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT) {
        record_status(internal, EGOLINK_SIM7670_MODEM_OWNER_OK);
        return EGOLINK_SIM7670_MODEM_OWNER_OK;
    }
    record_status(internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
    return EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED;
}

egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_process_durable_sos(
    egolink_sim7670_location_modem_owner_t *owner,
    const egolink_location_runtime_identity_t *location_identity,
    egolink_modem_durable_sos_evidence_t evidence,
    uint64_t urgent_gnss_timeout_ms,
    uint64_t outbox_now_ms,
    egolink_location_modem_durable_sos_result_t *result)
{
    if (owner == NULL || location_identity == NULL || result == NULL) {
        return EGOLINK_SIM7670_MODEM_OWNER_INVALID_ARGUMENT;
    }
    sim7670_location_modem_owner_internal_t *internal = internal_of(owner);
    egolink_sim7670_modem_owner_status_t gate =
        external_gate(internal, false, true);
    if (gate != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        return gate;
    }
    if (!take_external_owner(internal)) {
        return EGOLINK_SIM7670_MODEM_OWNER_OWNER_LOCK_TIMEOUT;
    }
    gate = external_gate(internal, false, true);
    if (gate != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        (void)xSemaphoreGive(internal->owner_mutex);
        return gate;
    }
    const egolink_modem_executor_status_t executor_status =
        egolink_location_modem_executor_process_durable_sos(
            &internal->executor, location_identity, evidence,
            urgent_gnss_timeout_ms, outbox_now_ms, &internal->scratch,
            result);
    update_sequence_after_durable_sos(
        internal, location_identity, result);
    record_executor_status(internal, executor_status);
    (void)xSemaphoreGive(internal->owner_mutex);
    notify_owner_task(internal);
    if (executor_status == EGOLINK_MODEM_EXECUTOR_DURABLE_SOS_ACCEPTED) {
        record_status(
            internal, EGOLINK_SIM7670_MODEM_OWNER_DURABLE_SOS_ACCEPTED);
        return EGOLINK_SIM7670_MODEM_OWNER_DURABLE_SOS_ACCEPTED;
    }
    if (executor_status == EGOLINK_MODEM_EXECUTOR_DURABLE_SOS_PARTIAL) {
        record_status(
            internal, EGOLINK_SIM7670_MODEM_OWNER_DURABLE_SOS_PARTIAL);
        return EGOLINK_SIM7670_MODEM_OWNER_DURABLE_SOS_PARTIAL;
    }
    if (executor_status ==
        EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED) {
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
        return EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED_STATUS;
    }
    record_status(internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
    return EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED;
}

egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_signal_durable_sos(
    egolink_sim7670_location_modem_owner_t *owner,
    egolink_modem_durable_sos_evidence_t evidence,
    uint64_t urgent_gnss_timeout_ms,
    egolink_location_modem_enqueue_result_t *sos_transport,
    egolink_location_modem_enqueue_result_t *urgent_gnss)
{
    if (owner == NULL || sos_transport == NULL || urgent_gnss == NULL) {
        return EGOLINK_SIM7670_MODEM_OWNER_INVALID_ARGUMENT;
    }
    sim7670_location_modem_owner_internal_t *internal = internal_of(owner);
    egolink_sim7670_modem_owner_status_t gate =
        external_gate(internal, true, true);
    if (gate != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        return gate;
    }
    if (!take_external_owner(internal)) {
        return EGOLINK_SIM7670_MODEM_OWNER_OWNER_LOCK_TIMEOUT;
    }
    gate = external_gate(internal, true, true);
    if (gate != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        (void)xSemaphoreGive(internal->owner_mutex);
        return gate;
    }
    const egolink_modem_executor_status_t executor_status =
        egolink_location_modem_executor_signal_durable_sos(
            &internal->executor, evidence, urgent_gnss_timeout_ms,
            sos_transport, urgent_gnss);
    record_executor_status(internal, executor_status);
    (void)xSemaphoreGive(internal->owner_mutex);
    notify_owner_task(internal);
    if (executor_status == EGOLINK_MODEM_EXECUTOR_QUEUED ||
        executor_status == EGOLINK_MODEM_EXECUTOR_ALREADY_OUTSTANDING) {
        record_status(internal, EGOLINK_SIM7670_MODEM_OWNER_QUEUED);
        return EGOLINK_SIM7670_MODEM_OWNER_QUEUED;
    }
    if (executor_status == EGOLINK_MODEM_EXECUTOR_QUEUE_PARTIAL) {
        record_status(
            internal, EGOLINK_SIM7670_MODEM_OWNER_SOS_SIGNAL_PARTIAL);
        return EGOLINK_SIM7670_MODEM_OWNER_SOS_SIGNAL_PARTIAL;
    }
    if (executor_status ==
        EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED) {
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
        return EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED_STATUS;
    }
    record_status(internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
    return EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED;
}

egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_request_gnss_status(
    egolink_sim7670_location_modem_owner_t *owner,
    uint64_t timeout_ms,
    egolink_location_modem_enqueue_result_t *result)
{
    if (owner == NULL || result == NULL) {
        return EGOLINK_SIM7670_MODEM_OWNER_INVALID_ARGUMENT;
    }
    sim7670_location_modem_owner_internal_t *internal = internal_of(owner);
    egolink_sim7670_modem_owner_status_t gate =
        external_gate(internal, false, false);
    if (gate != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        return gate;
    }
    if (!take_external_owner(internal)) {
        return EGOLINK_SIM7670_MODEM_OWNER_OWNER_LOCK_TIMEOUT;
    }
    gate = external_gate(internal, false, false);
    if (gate != EGOLINK_SIM7670_MODEM_OWNER_OK) {
        (void)xSemaphoreGive(internal->owner_mutex);
        return gate;
    }
    const egolink_modem_executor_status_t executor_status =
        egolink_location_modem_executor_request_gnss_status(
            &internal->executor, timeout_ms, result);
    record_executor_status(internal, executor_status);
    (void)xSemaphoreGive(internal->owner_mutex);
    notify_owner_task(internal);
    if (executor_status == EGOLINK_MODEM_EXECUTOR_QUEUED ||
        executor_status == EGOLINK_MODEM_EXECUTOR_ALREADY_OUTSTANDING) {
        record_status(internal, EGOLINK_SIM7670_MODEM_OWNER_QUEUED);
        return EGOLINK_SIM7670_MODEM_OWNER_QUEUED;
    }
    if (executor_status ==
        EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED) {
        latch_fatal_recovery(
            internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
        return EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED_STATUS;
    }
    record_status(internal, EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED);
    return EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED;
}

egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_current_status(
    const egolink_sim7670_location_modem_owner_t *owner,
    egolink_sim7670_location_modem_owner_snapshot_t *snapshot)
{
    if (snapshot != NULL) {
        (void)memset(snapshot, 0, sizeof(*snapshot));
    }
    if (owner == NULL || snapshot == NULL) {
        return EGOLINK_SIM7670_MODEM_OWNER_INVALID_ARGUMENT;
    }
    const sim7670_location_modem_owner_internal_t *const_view =
        internal_of_const(owner);
    if (!valid_magic(const_view)) {
        return EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED;
    }
    sim7670_location_modem_owner_internal_t *internal =
        (sim7670_location_modem_owner_internal_t *)(void *)const_view;
    taskENTER_CRITICAL(&internal->metadata_lock);
    snapshot->initialized = true;
    snapshot->enabled = internal->enabled;
    snapshot->task_created = internal->task_created;
    snapshot->uart_initialized = internal->uart_initialized;
    snapshot->exclusive_owner_confirmed =
        internal->exclusive_owner_confirmed;
    snapshot->owner_core_id = internal->owner_core_id;
    snapshot->per_command_timeout_cap_ms =
        internal->per_command_timeout_cap_ms;
    snapshot->gnss_power_off_timeout_ms =
        internal->gnss_power_off_timeout_ms;
    snapshot->task_wakeups = internal->task_wakeups;
    snapshot->prepared_commands = internal->prepared_commands;
    snapshot->executed_commands = internal->executed_commands;
    snapshot->settled_commands = internal->settled_commands;
    snapshot->owner_lock_timeouts = internal->owner_lock_timeouts;
    snapshot->power_off_attempts = internal->power_off_attempts;
    snapshot->power_off_confirmed = internal->power_off_confirmed;
    snapshot->power_off_unconfirmed = internal->power_off_unconfirmed;
    snapshot->recovery_attempts = internal->recovery_attempts;
    snapshot->generated_capture_identities =
        internal->generated_capture_identities;
    snapshot->last_executor_status = internal->last_executor_status;
    snapshot->last_adapter_status = internal->last_adapter_status;
    snapshot->last_power_off_outcome = internal->last_power_off_outcome;
    snapshot->last_power_off_reason = internal->last_power_off_reason;
    snapshot->lifecycle = internal->lifecycle;
    snapshot->last_status = internal->last_status;
    taskEXIT_CRITICAL(&internal->metadata_lock);
    snapshot->execution_active = atomic_load_explicit(
        &internal->execution_active, memory_order_acquire);
    snapshot->gnss_off_confirmed = atomic_load_explicit(
        &internal->gnss_off_confirmed, memory_order_acquire);
    snapshot->cleanup_recovery_required = atomic_load_explicit(
        &internal->cleanup_recovery_required, memory_order_acquire);
    snapshot->fatal_recovery_required = atomic_load_explicit(
        &internal->fatal_recovery_required, memory_order_acquire);
    return EGOLINK_SIM7670_MODEM_OWNER_OK;
}

const char *egolink_sim7670_modem_owner_status_name(
    egolink_sim7670_modem_owner_status_t status)
{
    switch (status) {
    case EGOLINK_SIM7670_MODEM_OWNER_OK: return "ok";
    case EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED_STATUS:
        return "initialized";
    case EGOLINK_SIM7670_MODEM_OWNER_STARTED: return "started";
    case EGOLINK_SIM7670_MODEM_OWNER_QUEUED: return "queued";
    case EGOLINK_SIM7670_MODEM_OWNER_DURABLE_SOS_ACCEPTED:
        return "durable_sos_accepted";
    case EGOLINK_SIM7670_MODEM_OWNER_DURABLE_SOS_PARTIAL:
        return "durable_sos_partial";
    case EGOLINK_SIM7670_MODEM_OWNER_DISABLED_STATUS: return "disabled";
    case EGOLINK_SIM7670_MODEM_OWNER_BUILD_DISABLED:
        return "build_disabled";
    case EGOLINK_SIM7670_MODEM_OWNER_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_SIM7670_MODEM_OWNER_INVALID_CONFIG:
        return "invalid_config";
    case EGOLINK_SIM7670_MODEM_OWNER_ALREADY_INITIALIZED:
        return "already_initialized";
    case EGOLINK_SIM7670_MODEM_OWNER_ALREADY_STARTED:
        return "already_started";
    case EGOLINK_SIM7670_MODEM_OWNER_DEPENDENCY_MISMATCH:
        return "dependency_mismatch";
    case EGOLINK_SIM7670_MODEM_OWNER_ADAPTER_INIT_FAILED:
        return "adapter_init_failed";
    case EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_INIT_FAILED:
        return "executor_init_failed";
    case EGOLINK_SIM7670_MODEM_OWNER_TASK_CREATE_FAILED:
        return "task_create_failed";
    case EGOLINK_SIM7670_MODEM_OWNER_START_TIMEOUT:
        return "start_timeout";
    case EGOLINK_SIM7670_MODEM_OWNER_UART_INIT_FAILED:
        return "uart_init_failed";
    case EGOLINK_SIM7670_MODEM_OWNER_EXCLUSIVE_OWNER_MISMATCH:
        return "exclusive_owner_mismatch";
    case EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED: return "not_started";
    case EGOLINK_SIM7670_MODEM_OWNER_OWNER_LOCK_TIMEOUT:
        return "owner_lock_timeout";
    case EGOLINK_SIM7670_MODEM_OWNER_IN_FLIGHT: return "in_flight";
    case EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED:
        return "executor_rejected";
    case EGOLINK_SIM7670_MODEM_OWNER_GNSS_POWER_OFF_UNCONFIRMED:
        return "gnss_power_off_unconfirmed";
    case EGOLINK_SIM7670_MODEM_OWNER_IDENTITY_EXHAUSTED:
        return "identity_exhausted";
    case EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED_STATUS:
        return "recovery_required";
    case EGOLINK_SIM7670_MODEM_OWNER_MAPPED_INPUT_PARTIAL:
        return "mapped_input_partial";
    case EGOLINK_SIM7670_MODEM_OWNER_SOS_SIGNAL_PARTIAL:
        return "sos_signal_partial";
    default: return "unknown";
    }
}

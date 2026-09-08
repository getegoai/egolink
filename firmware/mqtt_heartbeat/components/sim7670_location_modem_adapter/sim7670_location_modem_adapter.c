#include "sim7670_location_modem_adapter.h"

#include <math.h>
#include <stdatomic.h>
#include <string.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define SIM7670_LOCATION_ADAPTER_MAGIC UINT32_C(0x534C4D41)

typedef struct {
    uint32_t magic;
    bool enabled;
    bool callbacks_bound;
    egolink_sim7670_driver_mode_t driver_mode;
    int32_t owner_core_id;
    uint32_t per_command_timeout_cap_ms;
    uint32_t gnss_power_on_settle_ms;
    const atomic_bool *owner_stop_requested;
    uint32_t blocker_flags;
    atomic_bool callback_active;
    uint64_t callback_calls;
    uint64_t report_available_count;
    uint64_t unknown_outcome_count;
    uint64_t definite_no_effect_count;
    uint64_t cooperative_cancel_count;
    uint64_t wrong_core_count;
    uint64_t concurrent_rejection_count;
    egolink_modem_command_kind_t last_kind;
    egolink_modem_callback_outcome_t last_callback_outcome;
    sim7670_location_bounded_outcome_t last_driver_outcome;
    sim7670_location_bounded_reason_t last_driver_reason;
    bool last_driver_io_started;
    bool last_driver_cancel_before_io;
    bool last_driver_cancelled_between_commands;
    bool last_driver_partial_or_unknown;
    uint16_t last_driver_commands_attempted;
    uint16_t last_driver_commands_tx_complete;
    uint16_t last_driver_commands_completed;
    egolink_sim7670_location_adapter_status_t last_status;
    portMUX_TYPE metadata_lock;
} sim7670_location_adapter_internal_t;

_Static_assert(
    sizeof(sim7670_location_adapter_internal_t) <=
        EGOLINK_SIM7670_LOCATION_MODEM_ADAPTER_CONTEXT_BYTES,
    "SIM7670 location modem adapter context is too small");

static sim7670_location_adapter_internal_t *internal_of(
    egolink_sim7670_location_modem_adapter_t *adapter)
{
    return (sim7670_location_adapter_internal_t *)(void *)adapter->opaque;
}

static const sim7670_location_adapter_internal_t *internal_of_const(
    const egolink_sim7670_location_modem_adapter_t *adapter)
{
    return (const sim7670_location_adapter_internal_t *)(const void *)
        adapter->opaque;
}

static bool valid_magic(const sim7670_location_adapter_internal_t *internal)
{
    uint32_t observed = UINT32_C(0);
    if (internal == NULL) {
        return false;
    }
    (void)memcpy(&observed, (const void *)internal, sizeof(observed));
    return observed == SIM7670_LOCATION_ADAPTER_MAGIC;
}

static void increment_saturated(uint64_t *value)
{
    if (*value != UINT64_MAX) {
        ++(*value);
    }
}

static void record_status(
    sim7670_location_adapter_internal_t *internal,
    egolink_sim7670_location_adapter_status_t status)
{
    taskENTER_CRITICAL(&internal->metadata_lock);
    internal->last_status = status;
    taskEXIT_CRITICAL(&internal->metadata_lock);
}

static void increment_metadata_counter(
    sim7670_location_adapter_internal_t *internal,
    uint64_t *counter)
{
    taskENTER_CRITICAL(&internal->metadata_lock);
    increment_saturated(counter);
    taskEXIT_CRITICAL(&internal->metadata_lock);
}

static bool bounded_equals_literal(
    const char *value,
    size_t capacity,
    const char *literal)
{
    if (value == NULL || capacity == 0U || literal == NULL) {
        return false;
    }
    const char *terminator = (const char *)memchr(value, '\0', capacity);
    if (terminator == NULL) {
        return false;
    }
    const size_t length = (size_t)(terminator - value);
    const size_t literal_length = strlen(literal);
    return length == literal_length &&
        memcmp(value, literal, literal_length) == 0;
}

static bool all_gnss_text_is_terminated(const sim7670_gnss_report_t *report)
{
    return memchr(report->gnss_state, '\0', sizeof(report->gnss_state)) != NULL &&
        memchr(report->source_status, '\0', sizeof(report->source_status)) != NULL &&
        memchr(report->raw_command, '\0', sizeof(report->raw_command)) != NULL &&
        memchr(report->raw_response, '\0', sizeof(report->raw_response)) != NULL &&
        memchr(report->utc_date, '\0', sizeof(report->utc_date)) != NULL &&
        memchr(report->utc_time, '\0', sizeof(report->utc_time)) != NULL;
}

static bool all_lte_text_is_terminated(const sim7670_lte_report_t *report)
{
    return memchr(report->sim_state, '\0', sizeof(report->sim_state)) != NULL &&
        memchr(report->registration_state, '\0',
               sizeof(report->registration_state)) != NULL &&
        memchr(report->pdp_state, '\0', sizeof(report->pdp_state)) != NULL &&
        memchr(report->apn_state, '\0', sizeof(report->apn_state)) != NULL &&
        memchr(report->operator_name, '\0', sizeof(report->operator_name)) != NULL &&
        memchr(report->rat, '\0', sizeof(report->rat)) != NULL &&
        memchr(report->mcc, '\0', sizeof(report->mcc)) != NULL &&
        memchr(report->mnc, '\0', sizeof(report->mnc)) != NULL &&
        memchr(report->tac, '\0', sizeof(report->tac)) != NULL &&
        memchr(report->cell_id, '\0', sizeof(report->cell_id)) != NULL &&
        memchr(report->assigned_ip, '\0', sizeof(report->assigned_ip)) != NULL &&
        memchr(report->reason_code, '\0', sizeof(report->reason_code)) != NULL &&
        memchr(report->raw_command, '\0', sizeof(report->raw_command)) != NULL &&
        memchr(report->raw_response, '\0', sizeof(report->raw_response)) != NULL;
}

static bool valid_gnss_query_evidence(
    const sim7670_gnss_query_evidence_t *evidence)
{
    return evidence != NULL &&
        (!evidence->response_observed || evidence->attempted) &&
        (!evidence->parse_valid || evidence->response_observed) &&
        (!evidence->fix_observed || evidence->parse_valid) &&
        (!evidence->no_fix_observed || evidence->parse_valid) &&
        !(evidence->fix_observed && evidence->no_fix_observed);
}

static bool complete_gnss_query(
    const sim7670_gnss_query_evidence_t *evidence)
{
    return valid_gnss_query_evidence(evidence) && evidence->attempted &&
        evidence->response_observed && evidence->parse_valid &&
        (evidence->fix_observed || evidence->no_fix_observed);
}

static bool empty_gnss_query(
    const sim7670_gnss_query_evidence_t *evidence)
{
    return valid_gnss_query_evidence(evidence) && !evidence->attempted &&
        !evidence->response_observed && !evidence->parse_valid &&
        !evidence->fix_observed && !evidence->no_fix_observed;
}

static bool no_gnss_measurement_is_marked_valid(
    const sim7670_gnss_report_t *report)
{
    return !report->lat_valid && !report->lon_valid &&
        !report->altitude_valid && !report->speed_valid &&
        !report->course_valid && !report->pdop_valid &&
        !report->hdop_valid && !report->vdop_valid &&
        !report->satellites_valid;
}

egolink_sim7670_gnss_report_class_t
egolink_sim7670_location_classify_gnss_report(
    const sim7670_gnss_report_t *report)
{
    if (report == NULL || !all_gnss_text_is_terminated(report) ||
        !report->driver_enabled || !report->uart_ready || !report->at_ok ||
        !report->location_result_valid ||
        !valid_gnss_query_evidence(&report->cgnssinfo_query) ||
        !valid_gnss_query_evidence(&report->cgpsinfo_query) ||
        !complete_gnss_query(&report->cgnssinfo_query)) {
        return EGOLINK_SIM7670_GNSS_REPORT_INCOMPLETE_OR_AMBIGUOUS;
    }

    const bool cgnss_fix = report->cgnssinfo_query.fix_observed;
    if (cgnss_fix) {
        if (!empty_gnss_query(&report->cgpsinfo_query)) {
            return EGOLINK_SIM7670_GNSS_REPORT_INCOMPLETE_OR_AMBIGUOUS;
        }
    } else if (!report->cgnssinfo_query.no_fix_observed ||
               !complete_gnss_query(&report->cgpsinfo_query)) {
        /* A timeout/malformed first query followed by a usable fallback is a
         * partial transaction, not a complete callback result. */
        return EGOLINK_SIM7670_GNSS_REPORT_INCOMPLETE_OR_AMBIGUOUS;
    }

    const bool final_fix = cgnss_fix || report->cgpsinfo_query.fix_observed;
    if (final_fix) {
        if (!report->fix || report->no_fix_observed || !report->lat_valid ||
            !report->lon_valid || !isfinite(report->lat) ||
            !isfinite(report->lon) || report->lat < -90.0 ||
            report->lat > 90.0 || report->lon < -180.0 ||
            report->lon > 180.0 ||
            !bounded_equals_literal(report->gnss_state,
                                    sizeof(report->gnss_state), "fix") ||
            !bounded_equals_literal(report->source_status,
                                    sizeof(report->source_status),
                                    "observed")) {
            return EGOLINK_SIM7670_GNSS_REPORT_INCOMPLETE_OR_AMBIGUOUS;
        }
        return EGOLINK_SIM7670_GNSS_REPORT_COMPLETE_FIX;
    }

    if (report->fix || !report->no_fix_observed ||
        !report->cgnssinfo_query.no_fix_observed ||
        !report->cgpsinfo_query.no_fix_observed ||
        !no_gnss_measurement_is_marked_valid(report) ||
        !bounded_equals_literal(report->gnss_state,
                                sizeof(report->gnss_state), "no_fix") ||
        !bounded_equals_literal(report->source_status,
                                sizeof(report->source_status), "observed")) {
        return EGOLINK_SIM7670_GNSS_REPORT_INCOMPLETE_OR_AMBIGUOUS;
    }
    return EGOLINK_SIM7670_GNSS_REPORT_COMPLETE_NO_FIX;
}

static bool complete_at_query(const sim7670_at_query_evidence_t *evidence)
{
    return evidence != NULL && evidence->attempted &&
        evidence->response_observed && evidence->parse_valid;
}

static const char *expected_lte_reason(const sim7670_lte_report_t *report)
{
    if (!report->sim_ready) {
        return "LTE_SIM_NOT_READY";
    }
    if (!report->registered) {
        return "LTE_NOT_REGISTERED";
    }
    if (!report->attached) {
        return "LTE_NOT_ATTACHED";
    }
    if (!report->pdp_active) {
        return "LTE_PDP_INACTIVE";
    }
    return "LTE_READY";
}

static bool cell_digits(
    const char *value,
    size_t capacity,
    size_t minimum,
    size_t maximum)
{
    const char *terminator = (const char *)memchr(value, '\0', capacity);
    if (terminator == NULL) {
        return false;
    }
    const size_t length = (size_t)(terminator - value);
    if (length < minimum || length > maximum) {
        return false;
    }
    for (size_t index = 0U; index < length; ++index) {
        if (value[index] < '0' || value[index] > '9') {
            return false;
        }
    }
    return true;
}

static bool cell_hex(
    const char *value,
    size_t capacity,
    size_t minimum,
    size_t maximum)
{
    const char *terminator = (const char *)memchr(value, '\0', capacity);
    if (terminator == NULL) {
        return false;
    }
    const size_t length = (size_t)(terminator - value);
    if (length < minimum || length > maximum) {
        return false;
    }
    for (size_t index = 0U; index < length; ++index) {
        const char character = value[index];
        const bool digit = character >= '0' && character <= '9';
        const bool lower = character >= 'a' && character <= 'f';
        const bool upper = character >= 'A' && character <= 'F';
        if (!digit && !lower && !upper) {
            return false;
        }
    }
    return true;
}

static bool complete_cell_identity(const sim7670_lte_report_t *report)
{
    return report->cell_identity_valid &&
        cell_digits(report->mcc, sizeof(report->mcc), 3U, 3U) &&
        cell_digits(report->mnc, sizeof(report->mnc), 2U, 3U) &&
        cell_hex(report->tac, sizeof(report->tac), 1U, 8U) &&
        cell_hex(report->cell_id, sizeof(report->cell_id), 1U, 16U);
}

egolink_sim7670_lte_report_class_t
egolink_sim7670_location_classify_lte_report(
    const sim7670_lte_report_t *report)
{
    if (report == NULL || !all_lte_text_is_terminated(report) ||
        !report->driver_enabled || !report->uart_ready || !report->at_ok ||
        !complete_at_query(&report->cpin_query) ||
        !complete_at_query(&report->cops_query) ||
        !complete_at_query(&report->cereg_query) ||
        !complete_at_query(&report->cgatt_query) ||
        !complete_at_query(&report->cgdcont_query) ||
        !complete_at_query(&report->cgact_query) ||
        !complete_at_query(&report->cgpaddr_query) ||
        !complete_at_query(&report->csq_query) ||
        !complete_at_query(&report->cpsi_query) ||
        !bounded_equals_literal(report->reason_code,
                                sizeof(report->reason_code),
                                expected_lte_reason(report))) {
        return EGOLINK_SIM7670_LTE_REPORT_INCOMPLETE_OR_AMBIGUOUS;
    }

    if (!report->cell_identity_valid) {
        return EGOLINK_SIM7670_LTE_REPORT_COMPLETE_STATE;
    }
    if (!complete_cell_identity(report)) {
        return EGOLINK_SIM7670_LTE_REPORT_INCOMPLETE_OR_AMBIGUOUS;
    }
    return EGOLINK_SIM7670_LTE_REPORT_COMPLETE_STATE_AND_CELL;
}

static bool now_ms(uint64_t *value)
{
    if (value == NULL) {
        return false;
    }
    const int64_t microseconds = esp_timer_get_time();
    if (microseconds < INT64_C(0)) {
        return false;
    }
    *value = (uint64_t)microseconds / UINT64_C(1000);
    return true;
}

static void record_outcome(
    sim7670_location_adapter_internal_t *internal,
    egolink_modem_command_kind_t kind,
    egolink_modem_callback_outcome_t outcome,
    egolink_sim7670_location_adapter_status_t status)
{
    taskENTER_CRITICAL(&internal->metadata_lock);
    internal->last_kind = kind;
    internal->last_callback_outcome = outcome;
    internal->last_status = status;
    if (outcome == EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE) {
        increment_saturated(&internal->report_available_count);
    } else if (outcome == EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN) {
        increment_saturated(&internal->unknown_outcome_count);
    } else if (outcome ==
               EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE) {
        increment_saturated(&internal->definite_no_effect_count);
    } else if (outcome == EGOLINK_MODEM_CALLBACK_COOPERATIVE_CANCELLED) {
        increment_saturated(&internal->cooperative_cancel_count);
    }
    taskEXIT_CRITICAL(&internal->metadata_lock);
}

static bool valid_request_common(
    const egolink_location_modem_sensor_request_t *request,
    bool gnss)
{
    if (request == NULL || request->generation == UINT32_C(0) ||
        request->timeout_ms == UINT64_C(0) ||
        request->timeout_ms > EGOLINK_LOCATION_MODEM_EXECUTOR_MAX_TIMEOUT_MS ||
        request->cancellation_safe_point !=
            EGOLINK_MODEM_SAFE_POINT_BETWEEN_AT_COMMANDS ||
        request->hard_cancel_supported || request->cancel_requested == NULL ||
        request->cancel_context == NULL) {
        return false;
    }
    if (gnss) {
        return request->kind == EGOLINK_MODEM_COMMAND_GNSS_ACQUIRE ||
            request->kind == EGOLINK_MODEM_COMMAND_GNSS_STATUS ||
            request->kind == EGOLINK_MODEM_COMMAND_SOS_URGENT_GNSS_ACQUIRE;
    }
    return request->kind == EGOLINK_MODEM_COMMAND_CELL_OBSERVE;
}

static bool begin_callback(
    sim7670_location_adapter_internal_t *internal,
    const egolink_location_modem_sensor_request_t *request,
    bool gnss,
    uint64_t *entry_time_ms,
    uint64_t *deadline_time_ms,
    egolink_modem_callback_outcome_t *early_outcome)
{
    if (!valid_magic(internal) || !internal->enabled ||
        !valid_request_common(request, gnss) || entry_time_ms == NULL ||
        deadline_time_ms == NULL || early_outcome == NULL) {
        if (valid_magic(internal)) {
            record_status(
                internal,
                EGOLINK_SIM7670_ADAPTER_REQUEST_CONTRACT_INVALID);
        }
        return false;
    }
    increment_metadata_counter(internal, &internal->callback_calls);
    if ((int32_t)xPortGetCoreID() != internal->owner_core_id) {
        increment_metadata_counter(internal, &internal->wrong_core_count);
        *early_outcome = EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
        record_outcome(internal, request->kind, *early_outcome,
                       EGOLINK_SIM7670_ADAPTER_WRONG_CORE);
        return false;
    }
    bool expected = false;
    if (!atomic_compare_exchange_strong_explicit(
            &internal->callback_active, &expected, true,
            memory_order_acquire, memory_order_relaxed)) {
        increment_metadata_counter(
            internal, &internal->concurrent_rejection_count);
        *early_outcome = EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
        record_outcome(internal, request->kind, *early_outcome,
                       EGOLINK_SIM7670_ADAPTER_CONCURRENT_CALL_REJECTED);
        return false;
    }
    if (!now_ms(entry_time_ms)) {
        *early_outcome = EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
        record_outcome(internal, request->kind, *early_outcome,
                       EGOLINK_SIM7670_ADAPTER_CLOCK_REGRESSION);
        atomic_store_explicit(
            &internal->callback_active, false, memory_order_release);
        return false;
    }
    if (request->begin_time_ms > *entry_time_ms ||
        request->timeout_ms > UINT64_MAX - request->begin_time_ms) {
        *early_outcome = EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
        record_outcome(internal, request->kind, *early_outcome,
                       EGOLINK_SIM7670_ADAPTER_REQUEST_CONTRACT_INVALID);
        atomic_store_explicit(
            &internal->callback_active, false, memory_order_release);
        return false;
    }
    *deadline_time_ms = request->begin_time_ms + request->timeout_ms;
    if (*entry_time_ms >= *deadline_time_ms) {
        *early_outcome = EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
        record_outcome(internal, request->kind, *early_outcome,
                       EGOLINK_SIM7670_ADAPTER_REQUEST_DEADLINE_EXPIRED);
        atomic_store_explicit(
            &internal->callback_active, false, memory_order_release);
        return false;
    }
    if ((internal->owner_stop_requested != NULL &&
         atomic_load(internal->owner_stop_requested)) ||
        request->cancel_requested(
            request->cancel_context, request->generation, request->kind)) {
        *early_outcome = EGOLINK_MODEM_CALLBACK_COOPERATIVE_CANCELLED;
        record_outcome(internal, request->kind, *early_outcome,
                       EGOLINK_SIM7670_ADAPTER_CANCELLED_AT_SAFE_POINT);
        atomic_store_explicit(
            &internal->callback_active, false, memory_order_release);
        return false;
    }
    if (internal->driver_mode ==
        EGOLINK_SIM7670_DRIVER_CURRENT_SYNCHRONOUS_FAIL_CLOSED) {
        *early_outcome = EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
        record_outcome(internal, request->kind, *early_outcome,
                       EGOLINK_SIM7670_ADAPTER_BOUND_FAIL_CLOSED);
        atomic_store_explicit(
            &internal->callback_active, false, memory_order_release);
        return false;
    }
    return true;
}

static egolink_modem_callback_outcome_t finish_driver_call(
    sim7670_location_adapter_internal_t *internal,
    const egolink_location_modem_sensor_request_t *request,
    sim7670_location_bounded_outcome_t driver_outcome,
    bool driver_contract_valid,
    bool report_complete,
    uint64_t deadline_time_ms,
    uint64_t *completion_time_ms)
{
    uint64_t completion = UINT64_C(0);
    if (!now_ms(&completion)) {
        completion = deadline_time_ms;
        record_outcome(internal, request->kind,
                       EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN,
                       EGOLINK_SIM7670_ADAPTER_CLOCK_REGRESSION);
        *completion_time_ms = completion;
        atomic_store_explicit(
            &internal->callback_active, false, memory_order_release);
        return EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
    }
    *completion_time_ms = completion;
    if (completion < request->begin_time_ms || completion > deadline_time_ms) {
        record_outcome(internal, request->kind,
                       EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN,
                       completion < request->begin_time_ms
                           ? EGOLINK_SIM7670_ADAPTER_CLOCK_REGRESSION
                           : EGOLINK_SIM7670_ADAPTER_DRIVER_OUTCOME_UNKNOWN);
        atomic_store_explicit(
            &internal->callback_active, false, memory_order_release);
        return EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
    }

    egolink_modem_callback_outcome_t outcome =
        EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
    egolink_sim7670_location_adapter_status_t status =
        EGOLINK_SIM7670_ADAPTER_DRIVER_OUTCOME_UNKNOWN;
    if (!driver_contract_valid) {
        status = EGOLINK_SIM7670_ADAPTER_DRIVER_OUTCOME_UNKNOWN;
    } else if (driver_outcome == SIM7670_LOCATION_BOUNDED_REPORT_READY) {
        if (report_complete) {
            outcome = EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE;
            status = EGOLINK_SIM7670_ADAPTER_REPORT_AVAILABLE;
        } else {
            status =
                EGOLINK_SIM7670_ADAPTER_REPORT_INCOMPLETE_OR_AMBIGUOUS;
        }
    } else if (driver_outcome ==
               SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE) {
        outcome = EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
        status = EGOLINK_SIM7670_ADAPTER_DEFINITE_NO_EFFECT_FAILURE;
    } else if (driver_outcome ==
               SIM7670_LOCATION_BOUNDED_COOPERATIVE_CANCELLED) {
        if ((internal->owner_stop_requested != NULL &&
             atomic_load(internal->owner_stop_requested)) ||
            request->cancel_requested(
                request->cancel_context, request->generation, request->kind)) {
            outcome = EGOLINK_MODEM_CALLBACK_COOPERATIVE_CANCELLED;
            status = EGOLINK_SIM7670_ADAPTER_CANCELLED_AT_SAFE_POINT;
        }
    }
    record_outcome(internal, request->kind, outcome, status);
    atomic_store_explicit(
        &internal->callback_active, false, memory_order_release);
    return outcome;
}

typedef struct {
    const egolink_location_modem_sensor_request_t *request;
    const atomic_bool *owner_stop_requested;
} native_cancel_bridge_t;

static bool native_cancel_requested(void *context, uint32_t operation_token)
{
    const native_cancel_bridge_t *bridge =
        (const native_cancel_bridge_t *)context;
    return bridge != NULL && bridge->request != NULL &&
        operation_token == bridge->request->generation &&
        ((bridge->owner_stop_requested != NULL &&
          atomic_load(bridge->owner_stop_requested)) ||
         bridge->request->cancel_requested(
            bridge->request->cancel_context,
            bridge->request->generation,
            bridge->request->kind));
}

static bool native_result_contract_valid(
    const sim7670_location_bounded_result_t *result,
    sim7670_location_bounded_outcome_t returned_outcome)
{
    if (result == NULL || result->outcome != returned_outcome ||
        result->commands_tx_complete > result->commands_attempted ||
        result->commands_completed > result->commands_tx_complete) {
        return false;
    }
    if (returned_outcome == SIM7670_LOCATION_BOUNDED_REPORT_READY) {
        return result->reason == SIM7670_LOCATION_BOUNDED_REASON_NONE &&
            result->io_started && !result->cancel_before_io &&
            !result->cancelled_between_commands &&
            !result->partial_or_unknown &&
            result->commands_attempted > UINT16_C(0) &&
            result->commands_attempted == result->commands_tx_complete &&
            result->commands_tx_complete == result->commands_completed;
    }
    if (returned_outcome ==
        SIM7670_LOCATION_BOUNDED_DEFINITE_NO_EFFECT_FAILURE) {
        return !result->io_started && !result->partial_or_unknown &&
            result->commands_attempted == UINT16_C(0) &&
            result->commands_tx_complete == UINT16_C(0) &&
            result->commands_completed == UINT16_C(0);
    }
    if (returned_outcome ==
        SIM7670_LOCATION_BOUNDED_COOPERATIVE_CANCELLED) {
        const bool before = result->cancel_before_io && !result->io_started &&
            !result->cancelled_between_commands && !result->partial_or_unknown;
        const bool between = !result->cancel_before_io && result->io_started &&
            result->cancelled_between_commands && result->partial_or_unknown;
        return before || between;
    }
    return returned_outcome == SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN &&
        result->partial_or_unknown;
}

static void record_native_result(
    sim7670_location_adapter_internal_t *internal,
    const sim7670_location_bounded_result_t *result)
{
    taskENTER_CRITICAL(&internal->metadata_lock);
    internal->last_driver_outcome = result->outcome;
    internal->last_driver_reason = result->reason;
    internal->last_driver_io_started = result->io_started;
    internal->last_driver_cancel_before_io = result->cancel_before_io;
    internal->last_driver_cancelled_between_commands =
        result->cancelled_between_commands;
    internal->last_driver_partial_or_unknown = result->partial_or_unknown;
    internal->last_driver_commands_attempted = result->commands_attempted;
    internal->last_driver_commands_tx_complete =
        result->commands_tx_complete;
    internal->last_driver_commands_completed = result->commands_completed;
    taskEXIT_CRITICAL(&internal->metadata_lock);
}

static egolink_modem_callback_outcome_t execute_gnss_callback(
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
    sim7670_location_adapter_internal_t *internal =
        internal_of((egolink_sim7670_location_modem_adapter_t *)context);
    uint64_t entry_time_ms = UINT64_C(0);
    uint64_t deadline_time_ms = UINT64_C(0);
    egolink_modem_callback_outcome_t early =
        EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
    if (!begin_callback(internal, request, true, &entry_time_ms,
                        &deadline_time_ms, &early)) {
        *completion_time_ms = entry_time_ms;
        return early;
    }

    const uint64_t remaining_ms = deadline_time_ms - entry_time_ms;
    if (remaining_ms == UINT64_C(0) || remaining_ms > UINT32_MAX) {
        record_outcome(
            internal, request->kind,
            EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE,
            EGOLINK_SIM7670_ADAPTER_REQUEST_DEADLINE_EXPIRED);
        atomic_store_explicit(
            &internal->callback_active, false, memory_order_release);
        *completion_time_ms = entry_time_ms;
        return EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
    }
    const native_cancel_bridge_t cancel_bridge = {
        .request = request, .owner_stop_requested = internal->owner_stop_requested};
    const sim7670_location_bounded_request_t driver_request = {
        .timeout_ms = (uint32_t)remaining_ms,
        .per_command_timeout_cap_ms =
            internal->per_command_timeout_cap_ms,
        .cancel_requested = native_cancel_requested,
        .cancel_context = (void *)&cancel_bridge,
        .operation_token = request->generation,
        .power_on_settle_ms = internal->gnss_power_on_settle_ms,
    };
    sim7670_location_bounded_result_t driver_result;
    const sim7670_location_bounded_outcome_t driver_outcome =
        sim7670_gnss_request_location_bounded(
            &driver_request, report, &driver_result);
    record_native_result(internal, &driver_result);
    const egolink_sim7670_gnss_report_class_t classification =
        egolink_sim7670_location_classify_gnss_report(report);
    const bool complete =
        classification !=
        EGOLINK_SIM7670_GNSS_REPORT_INCOMPLETE_OR_AMBIGUOUS;
    const egolink_modem_callback_outcome_t outcome = finish_driver_call(
        internal, request, driver_outcome,
        native_result_contract_valid(&driver_result, driver_outcome), complete,
        deadline_time_ms, completion_time_ms);
    if (outcome != EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE) {
        sim7670_gnss_report_init(report);
    }
    return outcome;
}

static egolink_modem_callback_outcome_t execute_lte_callback(
    void *context,
    const egolink_location_modem_sensor_request_t *request,
    sim7670_lte_report_t *report,
    uint64_t *completion_time_ms)
{
    if (report != NULL) {
        sim7670_lte_report_init(report);
    }
    if (completion_time_ms != NULL) {
        *completion_time_ms = UINT64_C(0);
    }
    if (context == NULL || request == NULL || report == NULL ||
        completion_time_ms == NULL) {
        return EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
    }
    sim7670_location_adapter_internal_t *internal =
        internal_of((egolink_sim7670_location_modem_adapter_t *)context);
    uint64_t entry_time_ms = UINT64_C(0);
    uint64_t deadline_time_ms = UINT64_C(0);
    egolink_modem_callback_outcome_t early =
        EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
    if (!begin_callback(internal, request, false, &entry_time_ms,
                        &deadline_time_ms, &early)) {
        *completion_time_ms = entry_time_ms;
        return early;
    }

    const uint64_t remaining_ms = deadline_time_ms - entry_time_ms;
    if (remaining_ms == UINT64_C(0) || remaining_ms > UINT32_MAX) {
        record_outcome(
            internal, request->kind,
            EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE,
            EGOLINK_SIM7670_ADAPTER_REQUEST_DEADLINE_EXPIRED);
        atomic_store_explicit(
            &internal->callback_active, false, memory_order_release);
        *completion_time_ms = entry_time_ms;
        return EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE;
    }
    const native_cancel_bridge_t cancel_bridge = {
        .request = request, .owner_stop_requested = internal->owner_stop_requested};
    const sim7670_location_bounded_request_t driver_request = {
        .timeout_ms = (uint32_t)remaining_ms,
        .per_command_timeout_cap_ms =
            internal->per_command_timeout_cap_ms,
        .cancel_requested = native_cancel_requested,
        .cancel_context = (void *)&cancel_bridge,
        .operation_token = request->generation,
    };
    sim7670_location_bounded_result_t driver_result;
    const sim7670_location_bounded_outcome_t driver_outcome =
        sim7670_lte_query_status_bounded(
            &driver_request, report, &driver_result);
    record_native_result(internal, &driver_result);
    const egolink_sim7670_lte_report_class_t classification =
        egolink_sim7670_location_classify_lte_report(report);
    const bool complete =
        classification !=
        EGOLINK_SIM7670_LTE_REPORT_INCOMPLETE_OR_AMBIGUOUS;
    const egolink_modem_callback_outcome_t outcome = finish_driver_call(
        internal, request, driver_outcome,
        native_result_contract_valid(&driver_result, driver_outcome), complete,
        deadline_time_ms, completion_time_ms);
    if (outcome != EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE) {
        sim7670_lte_report_init(report);
    }
    return outcome;
}

void egolink_sim7670_location_modem_adapter_default_config(
    egolink_sim7670_location_modem_adapter_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->enabled = false;
        config->driver_mode =
            EGOLINK_SIM7670_DRIVER_CURRENT_SYNCHRONOUS_FAIL_CLOSED;
        config->owner_core_id = INT32_C(-1);
        config->per_command_timeout_cap_ms = UINT32_C(0);
        config->gnss_power_on_settle_ms = UINT32_C(0);
        config->owner_stop_requested = NULL;
    }
}

void egolink_sim7670_location_modem_adapter_bounded_config(
    egolink_sim7670_location_modem_adapter_config_t *config,
    int32_t owner_core_id,
    uint32_t per_command_timeout_cap_ms)
{
    egolink_sim7670_location_modem_adapter_default_config(config);
    if (config != NULL) {
        config->enabled = true;
        config->driver_mode = EGOLINK_SIM7670_DRIVER_NATIVE_BOUNDED;
        config->owner_core_id = owner_core_id;
        config->per_command_timeout_cap_ms = per_command_timeout_cap_ms;
    }
}

void egolink_sim7670_location_modem_adapter_legacy_fail_closed_config(
    egolink_sim7670_location_modem_adapter_config_t *config,
    int32_t owner_core_id)
{
    egolink_sim7670_location_modem_adapter_default_config(config);
    if (config != NULL) {
        config->enabled = true;
        config->owner_core_id = owner_core_id;
    }
}

egolink_sim7670_location_adapter_status_t
egolink_sim7670_location_modem_adapter_init(
    egolink_sim7670_location_modem_adapter_t *adapter,
    const egolink_sim7670_location_modem_adapter_config_t *config)
{
    if (adapter == NULL || config == NULL) {
        return EGOLINK_SIM7670_ADAPTER_INVALID_ARGUMENT;
    }
    (void)memset(adapter, 0, sizeof(*adapter));
    sim7670_location_adapter_internal_t *internal = internal_of(adapter);
    internal->magic = SIM7670_LOCATION_ADAPTER_MAGIC;
    internal->enabled = config->enabled;
    internal->driver_mode = config->driver_mode;
    internal->owner_core_id = config->owner_core_id;
    internal->per_command_timeout_cap_ms =
        config->per_command_timeout_cap_ms;
    internal->gnss_power_on_settle_ms = config->gnss_power_on_settle_ms;
    internal->owner_stop_requested = config->owner_stop_requested;
    internal->last_callback_outcome = EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN;
    internal->last_driver_outcome = SIM7670_LOCATION_BOUNDED_OUTCOME_UNKNOWN;
    internal->last_driver_reason =
        SIM7670_LOCATION_BOUNDED_REASON_INVALID_ARGUMENT;
    portMUX_INITIALIZE(&internal->metadata_lock);
    atomic_init(&internal->callback_active, false);

    if (!config->enabled) {
        internal->last_status = EGOLINK_SIM7670_ADAPTER_DISABLED;
        return internal->last_status;
    }
    if (config->owner_core_id < INT32_C(0) ||
        config->owner_core_id >= (int32_t)portNUM_PROCESSORS) {
        internal->enabled = false;
        internal->last_status = EGOLINK_SIM7670_ADAPTER_INVALID_CONFIG;
        return internal->last_status;
    }
    if (config->driver_mode ==
        EGOLINK_SIM7670_DRIVER_CURRENT_SYNCHRONOUS_FAIL_CLOSED) {
        if (config->per_command_timeout_cap_ms != UINT32_C(0)) {
            internal->enabled = false;
            internal->last_status = EGOLINK_SIM7670_ADAPTER_INVALID_CONFIG;
            return internal->last_status;
        }
        internal->blocker_flags =
            (uint32_t)EGOLINK_SIM7670_BLOCKER_REQUEST_DEADLINE_UNSUPPORTED |
            (uint32_t)EGOLINK_SIM7670_BLOCKER_BETWEEN_AT_CANCEL_UNSUPPORTED;
        internal->last_status = EGOLINK_SIM7670_ADAPTER_BOUND_FAIL_CLOSED;
        return internal->last_status;
    }
    if (config->driver_mode != EGOLINK_SIM7670_DRIVER_NATIVE_BOUNDED ||
        config->per_command_timeout_cap_ms == UINT32_C(0) ||
        config->per_command_timeout_cap_ms >
            SIM7670_LOCATION_BOUNDED_COMMAND_CAP_MAX_MS ||
        config->gnss_power_on_settle_ms > UINT32_C(60000)) {
        internal->enabled = false;
        internal->last_status = EGOLINK_SIM7670_ADAPTER_INVALID_CONFIG;
        return internal->last_status;
    }
    internal->last_status = EGOLINK_SIM7670_ADAPTER_READY;
    return internal->last_status;
}

egolink_sim7670_location_adapter_status_t
egolink_sim7670_location_modem_adapter_bind_executor_config(
    egolink_sim7670_location_modem_adapter_t *adapter,
    egolink_location_modem_executor_config_t *executor_config)
{
    if (adapter == NULL || executor_config == NULL) {
        return EGOLINK_SIM7670_ADAPTER_INVALID_ARGUMENT;
    }
    sim7670_location_adapter_internal_t *internal = internal_of(adapter);
    if (!valid_magic(internal)) {
        return EGOLINK_SIM7670_ADAPTER_UNINITIALIZED;
    }
    if (!internal->enabled) {
        return EGOLINK_SIM7670_ADAPTER_DISABLED;
    }
    executor_config->execute_gnss = execute_gnss_callback;
    executor_config->gnss_context = adapter;
    executor_config->execute_cell = execute_lte_callback;
    executor_config->cell_context = adapter;
    taskENTER_CRITICAL(&internal->metadata_lock);
    internal->callbacks_bound = true;
    if (internal->driver_mode ==
        EGOLINK_SIM7670_DRIVER_CURRENT_SYNCHRONOUS_FAIL_CLOSED) {
        internal->last_status = EGOLINK_SIM7670_ADAPTER_BOUND_FAIL_CLOSED;
    } else {
        internal->last_status = EGOLINK_SIM7670_ADAPTER_READY;
    }
    const egolink_sim7670_location_adapter_status_t status =
        internal->last_status;
    taskEXIT_CRITICAL(&internal->metadata_lock);
    return status;
}

egolink_sim7670_location_adapter_status_t
egolink_sim7670_location_modem_adapter_current_status(
    const egolink_sim7670_location_modem_adapter_t *adapter,
    egolink_sim7670_location_modem_adapter_snapshot_t *snapshot)
{
    if (adapter == NULL || snapshot == NULL) {
        return EGOLINK_SIM7670_ADAPTER_INVALID_ARGUMENT;
    }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    const sim7670_location_adapter_internal_t *internal =
        internal_of_const(adapter);
    if (!valid_magic(internal)) {
        return EGOLINK_SIM7670_ADAPTER_UNINITIALIZED;
    }
    sim7670_location_adapter_internal_t *mutable_internal =
        (sim7670_location_adapter_internal_t *)(void *)internal;
    taskENTER_CRITICAL(&mutable_internal->metadata_lock);
    snapshot->initialized = true;
    snapshot->enabled = internal->enabled;
    snapshot->callbacks_bound = internal->callbacks_bound;
    snapshot->callback_active = atomic_load_explicit(
        &internal->callback_active, memory_order_acquire);
    snapshot->hard_cancel_supported = false;
    snapshot->driver_mode = internal->driver_mode;
    snapshot->owner_core_id = internal->owner_core_id;
    snapshot->per_command_timeout_cap_ms =
        internal->per_command_timeout_cap_ms;
    snapshot->blocker_flags = internal->blocker_flags;
    snapshot->callback_calls = internal->callback_calls;
    snapshot->report_available_count = internal->report_available_count;
    snapshot->unknown_outcome_count = internal->unknown_outcome_count;
    snapshot->definite_no_effect_count = internal->definite_no_effect_count;
    snapshot->cooperative_cancel_count = internal->cooperative_cancel_count;
    snapshot->wrong_core_count = internal->wrong_core_count;
    snapshot->concurrent_rejection_count =
        internal->concurrent_rejection_count;
    snapshot->last_kind = internal->last_kind;
    snapshot->last_callback_outcome = internal->last_callback_outcome;
    snapshot->last_driver_outcome = internal->last_driver_outcome;
    snapshot->last_driver_reason = internal->last_driver_reason;
    snapshot->last_driver_io_started = internal->last_driver_io_started;
    snapshot->last_driver_cancel_before_io =
        internal->last_driver_cancel_before_io;
    snapshot->last_driver_cancelled_between_commands =
        internal->last_driver_cancelled_between_commands;
    snapshot->last_driver_partial_or_unknown =
        internal->last_driver_partial_or_unknown;
    snapshot->last_driver_commands_attempted =
        internal->last_driver_commands_attempted;
    snapshot->last_driver_commands_tx_complete =
        internal->last_driver_commands_tx_complete;
    snapshot->last_driver_commands_completed =
        internal->last_driver_commands_completed;
    snapshot->last_status = internal->last_status;
    const egolink_sim7670_location_adapter_status_t status =
        internal->last_status;
    taskEXIT_CRITICAL(&mutable_internal->metadata_lock);
    return status;
}

const char *egolink_sim7670_location_adapter_status_name(
    egolink_sim7670_location_adapter_status_t status)
{
    switch (status) {
    case EGOLINK_SIM7670_ADAPTER_UNINITIALIZED:
        return "uninitialized";
    case EGOLINK_SIM7670_ADAPTER_DISABLED:
        return "disabled";
    case EGOLINK_SIM7670_ADAPTER_READY:
        return "ready";
    case EGOLINK_SIM7670_ADAPTER_BOUND_FAIL_CLOSED:
        return "bound_fail_closed";
    case EGOLINK_SIM7670_ADAPTER_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_SIM7670_ADAPTER_INVALID_CONFIG:
        return "invalid_config";
    case EGOLINK_SIM7670_ADAPTER_WRONG_CORE:
        return "wrong_core";
    case EGOLINK_SIM7670_ADAPTER_CONCURRENT_CALL_REJECTED:
        return "concurrent_call_rejected";
    case EGOLINK_SIM7670_ADAPTER_REQUEST_CONTRACT_INVALID:
        return "request_contract_invalid";
    case EGOLINK_SIM7670_ADAPTER_REQUEST_DEADLINE_EXPIRED:
        return "request_deadline_expired";
    case EGOLINK_SIM7670_ADAPTER_CLOCK_REGRESSION:
        return "clock_regression";
    case EGOLINK_SIM7670_ADAPTER_DRIVER_OUTCOME_UNKNOWN:
        return "driver_outcome_unknown";
    case EGOLINK_SIM7670_ADAPTER_REPORT_INCOMPLETE_OR_AMBIGUOUS:
        return "report_incomplete_or_ambiguous";
    case EGOLINK_SIM7670_ADAPTER_CANCELLED_AT_SAFE_POINT:
        return "cancelled_at_safe_point";
    case EGOLINK_SIM7670_ADAPTER_DEFINITE_NO_EFFECT_FAILURE:
        return "definite_no_effect_failure";
    case EGOLINK_SIM7670_ADAPTER_REPORT_AVAILABLE:
        return "report_available";
    default:
        return "unknown";
    }
}

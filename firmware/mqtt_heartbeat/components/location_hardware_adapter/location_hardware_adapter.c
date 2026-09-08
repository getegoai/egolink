#include "location_hardware_adapter.h"

#include <math.h>
#include <string.h>

#include "mbedtls/sha256.h"

#define LOCATION_HARDWARE_ACTUATOR_MAGIC UINT32_C(0x4c484131)

typedef struct {
    uint32_t magic;
    egolink_location_hardware_actuator_snapshot_t snapshot;
} location_hardware_actuator_internal_t;

_Static_assert(sizeof(location_hardware_actuator_internal_t) <=
                   EGOLINK_LOCATION_HARDWARE_ADAPTER_CONTEXT_BYTES,
               "location hardware actuator context is too small");

static void clear_mapped(egolink_location_hardware_mapped_input_t *mapped)
{
    if (mapped != NULL) {
        (void)memset(mapped, 0, sizeof(*mapped));
    }
}

static bool safe_id_first(unsigned char value)
{
    return (value >= (unsigned char)'A' && value <= (unsigned char)'Z') ||
           (value >= (unsigned char)'a' && value <= (unsigned char)'z') ||
           (value >= (unsigned char)'0' && value <= (unsigned char)'9');
}

static bool safe_id_byte(unsigned char value)
{
    return safe_id_first(value) || value == (unsigned char)'.' ||
           value == (unsigned char)'_' || value == (unsigned char)':' ||
           value == (unsigned char)'@' || value == (unsigned char)'-';
}

static bool safe_runtime_text(egolink_location_runtime_text_t text)
{
    if (text.data == NULL || text.length == 0U ||
        text.length > EGOLINK_LOCATION_RUNTIME_ID_MAX_BYTES ||
        !safe_id_first((unsigned char)text.data[0])) {
        return false;
    }
    for (size_t index = 1U; index < text.length; ++index) {
        if (!safe_id_byte((unsigned char)text.data[index])) {
            return false;
        }
    }
    return true;
}

static bool copy_runtime_text(
    char output[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY],
    egolink_location_runtime_text_t input)
{
    if (!safe_runtime_text(input)) {
        return false;
    }
    (void)memset(output, 0, EGOLINK_LOCATION_RUNTIME_ID_CAPACITY);
    (void)memcpy(output, input.data, input.length);
    return true;
}

static egolink_location_runtime_text_t owned_runtime_text(const char *text)
{
    const egolink_location_runtime_text_t result = {
        .data = text,
        .length = text == NULL ? 0U : strlen(text),
    };
    return result;
}

static egolink_location_engine_text_t engine_text(const char *text)
{
    const egolink_location_engine_text_t result = {
        .data = text,
        .length = text == NULL ? 0U : strlen(text),
    };
    return result;
}

static bool valid_publish_intent(
    egolink_location_runtime_publish_intent_t value)
{
    return value >= EGOLINK_LOCATION_RUNTIME_PUBLISH_NONE &&
           value <= EGOLINK_LOCATION_RUNTIME_PUBLISH_CURRENT;
}

static bool valid_identity(
    const egolink_location_hardware_identity_t *identity)
{
    if (identity == NULL || !safe_runtime_text(identity->device_id) ||
        !safe_runtime_text(identity->session_id) ||
        !safe_runtime_text(identity->stream_id) ||
        !safe_runtime_text(identity->observation_id) ||
        identity->boot_count > EGOLINK_LOCATION_RUNTIME_INT64_MAX ||
        identity->sequence_id > EGOLINK_LOCATION_RUNTIME_INT64_MAX ||
        identity->source_event_time_ms > EGOLINK_LOCATION_RUNTIME_INT64_MAX ||
        identity->source_event_time_ns > EGOLINK_LOCATION_RUNTIME_INT64_MAX ||
        identity->source_event_time_ns / UINT64_C(1000000) !=
            identity->source_event_time_ms ||
        !valid_publish_intent(identity->publish_intent)) {
        return false;
    }
    if (identity->source_event_time_source == EGOLINK_LOCATION_TIME_TIMESTAMP_UTC_NS) {
        return identity->monotonic_clock_domain_id.data == NULL &&
            identity->monotonic_clock_domain_id.length == 0U;
    }
    return identity->source_event_time_source == EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS &&
        safe_runtime_text(identity->monotonic_clock_domain_id);
}

static void bind_lineage_clock(
    egolink_location_engine_lineage_t *lineage,
    const egolink_location_hardware_identity_t *identity,
    egolink_location_hardware_mapped_input_t *mapped)
{
    if (identity->source_event_time_source == EGOLINK_LOCATION_TIME_TIMESTAMP_UTC_NS) {
        lineage->timestamp_utc_ns_present = true;
        lineage->timestamp_utc_ns = identity->source_event_time_ns;
        return;
    }
    lineage->timestamp_monotonic_ns_present = true;
    lineage->timestamp_monotonic_ns = identity->source_event_time_ns;
    lineage->monotonic_clock_domain_id_present = true;
    lineage->monotonic_clock_domain_id =
        engine_text(mapped->monotonic_clock_domain_id);
}

static bool prepare_base(
    const egolink_location_hardware_identity_t *identity,
    egolink_location_hardware_mapped_input_t *mapped)
{
    clear_mapped(mapped);
    if (mapped == NULL || !valid_identity(identity) ||
        !copy_runtime_text(mapped->device_id, identity->device_id) ||
        !copy_runtime_text(mapped->session_id, identity->session_id) ||
        !copy_runtime_text(mapped->stream_id, identity->stream_id) ||
        !copy_runtime_text(mapped->observation_id,
                           identity->observation_id) ||
        (identity->source_event_time_source == EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS &&
         !copy_runtime_text(mapped->monotonic_clock_domain_id,
                            identity->monotonic_clock_domain_id))) {
        clear_mapped(mapped);
        return false;
    }

    mapped->input.identity.device_id =
        owned_runtime_text(mapped->device_id);
    mapped->input.identity.boot_count = identity->boot_count;
    mapped->input.identity.session_id =
        owned_runtime_text(mapped->session_id);
    mapped->input.identity.stream_id = owned_runtime_text(mapped->stream_id);
    mapped->input.identity.sequence_id = identity->sequence_id;
    mapped->input.identity.observation_id =
        owned_runtime_text(mapped->observation_id);
    mapped->input.identity.event_time_ms = identity->source_event_time_ms;
    mapped->input.identity.event_time_ns = identity->source_event_time_ns;
    mapped->input.identity.event_time_source =
        identity->source_event_time_source;
    if (identity->source_event_time_source == EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS)
        mapped->input.identity.monotonic_clock_domain_id =
            owned_runtime_text(mapped->monotonic_clock_domain_id);
    mapped->input.publish_intent = identity->publish_intent;

    egolink_location_engine_lineage_t *lineage =
        &mapped->input.observation.lineage;
    lineage->present = true;
    lineage->observation_id = engine_text(mapped->observation_id);
    lineage->source_status =
        EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED;
    lineage->stream_id_present = true;
    lineage->stream_id = engine_text(mapped->stream_id);
    lineage->sequence_id_present = true;
    lineage->sequence_id = identity->sequence_id;
    lineage->device_run_id_present = true;
    lineage->device_run_id = engine_text(mapped->session_id);
    lineage->boot_count_present = true;
    lineage->boot_count = identity->boot_count;
    lineage->outer_evidence_source_status_present = true;
    lineage->outer_evidence_source_status =
        EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED;
    bind_lineage_clock(lineage, identity, mapped);
    mapped->input.observation.event_time_ms =
        identity->source_event_time_ms;
    return true;
}

static bool bounded_c_string(
    const char *text, size_t capacity, size_t *length)
{
    if (text == NULL || capacity == 0U) {
        return false;
    }
    for (size_t index = 0U; index < capacity; ++index) {
        if (text[index] == '\0') {
            if (length != NULL) {
                *length = index;
            }
            return true;
        }
    }
    return false;
}

static bool bounded_equals_literal(
    const char *text, size_t capacity, const char *literal)
{
    size_t length = 0U;
    const size_t literal_length = literal == NULL ? 0U : strlen(literal);
    return bounded_c_string(text, capacity, &length) &&
           length == literal_length &&
           (length == 0U || memcmp(text, literal, length) == 0);
}

static bool valid_optional_gnss_measurements(
    const sim7670_gnss_report_t *report)
{
    return (!report->altitude_valid || isfinite(report->altitude_m)) &&
           (!report->speed_valid ||
            (isfinite(report->speed_mps) && report->speed_mps >= 0.0)) &&
           (!report->course_valid ||
            (isfinite(report->course_deg) && report->course_deg >= 0.0 &&
             report->course_deg <= 360.0)) &&
           (!report->pdop_valid ||
            (isfinite(report->pdop) && report->pdop > 0.0)) &&
           (!report->vdop_valid ||
            (isfinite(report->vdop) && report->vdop > 0.0)) &&
           (!report->satellites_valid ||
            (report->satellites >= 0 && report->satellites <= 128));
}

static bool valid_at_query_evidence(
    const sim7670_at_query_evidence_t *evidence)
{
    return evidence != NULL &&
           (!evidence->response_observed || evidence->attempted) &&
           (!evidence->parse_valid || evidence->response_observed);
}

static bool valid_gnss_query_evidence(
    const sim7670_gnss_query_evidence_t *evidence)
{
    return evidence != NULL &&
           (!evidence->response_observed || evidence->attempted) &&
           (!evidence->parse_valid || evidence->response_observed) &&
           (!evidence->fix_observed || evidence->parse_valid) &&
           (!evidence->no_fix_observed || evidence->parse_valid) &&
           !(evidence->fix_observed && evidence->no_fix_observed) &&
           (evidence->parse_valid ==
            (evidence->fix_observed || evidence->no_fix_observed));
}

static bool gnss_query_evidence_present(
    const sim7670_gnss_report_t *report)
{
    return report != NULL &&
           (report->cgnssinfo_query.attempted ||
            report->cgnssinfo_query.response_observed ||
            report->cgnssinfo_query.parse_valid ||
            report->cgnssinfo_query.fix_observed ||
            report->cgnssinfo_query.no_fix_observed ||
            report->cgpsinfo_query.attempted ||
            report->cgpsinfo_query.response_observed ||
            report->cgpsinfo_query.parse_valid ||
            report->cgpsinfo_query.fix_observed ||
            report->cgpsinfo_query.no_fix_observed);
}

static bool valid_gnss_evidence(const sim7670_gnss_report_t *report)
{
    if (report == NULL ||
        !valid_gnss_query_evidence(&report->cgnssinfo_query) ||
        !valid_gnss_query_evidence(&report->cgpsinfo_query)) {
        return false;
    }
    const bool any_parse = report->cgnssinfo_query.parse_valid ||
                           report->cgpsinfo_query.parse_valid;
    const bool any_fix = report->cgnssinfo_query.fix_observed ||
                         report->cgpsinfo_query.fix_observed;
    const bool any_no_fix = report->cgnssinfo_query.no_fix_observed ||
                            report->cgpsinfo_query.no_fix_observed;
    if (!gnss_query_evidence_present(report)) {
        /* Additive compatibility: a zero evidence tail proves no outcome. */
        return !report->location_result_valid &&
               !report->no_fix_observed;
    }
    if (report->location_result_valid != any_parse ||
        report->no_fix_observed != (!any_fix && any_no_fix) ||
        report->fix != any_fix) {
        return false;
    }
    return report->at_ok ||
           (!report->cgnssinfo_query.attempted &&
            !report->cgpsinfo_query.attempted && !any_parse);
}

static bool no_gnss_measurement_is_marked_valid(
    const sim7670_gnss_report_t *report)
{
    return report != NULL && !report->lat_valid && !report->lon_valid &&
           !report->altitude_valid && !report->speed_valid &&
           !report->course_valid && !report->pdop_valid &&
           !report->hdop_valid && !report->vdop_valid &&
           !report->satellites_valid;
}

egolink_location_hardware_map_status_t
egolink_location_hardware_map_gnss(
    const egolink_location_hardware_identity_t *identity,
    const sim7670_gnss_report_t *report,
    egolink_location_hardware_mapped_input_t *mapped)
{
    if (identity == NULL || report == NULL || mapped == NULL) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_ARGUMENT;
    }
    if (!prepare_base(identity, mapped)) {
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_IDENTITY;
    }
    if (!bounded_c_string(report->gnss_state,
                          sizeof(report->gnss_state), NULL) ||
        !bounded_c_string(report->source_status,
                          sizeof(report->source_status), NULL) ||
        !valid_gnss_evidence(report)) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
    }

    if (!report->driver_enabled) {
        if (report->uart_ready || report->at_ok || report->fix ||
            !no_gnss_measurement_is_marked_valid(report) ||
            !bounded_equals_literal(report->gnss_state,
                                    sizeof(report->gnss_state),
                                    "driver_disabled")) {
            clear_mapped(mapped);
            return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
        }
        mapped->origin =
            EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_DRIVER_DISABLED;
        mapped->input.observation.type =
            EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR;
        return EGOLINK_LOCATION_HARDWARE_MAP_OK;
    }

    if (!report->uart_ready || !report->at_ok) {
        const bool valid_error =
            !report->fix && !report->at_ok &&
            no_gnss_measurement_is_marked_valid(report) &&
            ((!report->uart_ready &&
              bounded_equals_literal(report->gnss_state,
                                     sizeof(report->gnss_state),
                                     "uart_init_failed")) ||
             (report->uart_ready &&
              bounded_equals_literal(report->gnss_state,
                                     sizeof(report->gnss_state),
                                     "at_unreachable")));
        if (!valid_error) {
            clear_mapped(mapped);
            return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
        }
        mapped->origin = EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_DRIVER_ERROR;
        mapped->input.observation.type =
            EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR;
        return EGOLINK_LOCATION_HARDWARE_MAP_OK;
    }

    if (!gnss_query_evidence_present(report)) {
        const bool valid_legacy_state =
            (report->fix &&
             bounded_equals_literal(report->gnss_state,
                                    sizeof(report->gnss_state), "fix") &&
             bounded_equals_literal(report->source_status,
                                    sizeof(report->source_status),
                                    "observed")) ||
            (!report->fix &&
             bounded_equals_literal(report->gnss_state,
                                    sizeof(report->gnss_state), "no_fix") &&
             bounded_equals_literal(report->source_status,
                                    sizeof(report->source_status),
                                    "unverified"));
        if (!valid_legacy_state) {
            clear_mapped(mapped);
            return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
        }
        mapped->origin =
            EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_UNVERIFIED_RESULT;
        mapped->input.observation.type =
            EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR;
        return EGOLINK_LOCATION_HARDWARE_MAP_OK;
    }

    if (!report->fix) {
        if (report->location_result_valid && report->no_fix_observed) {
            if (!no_gnss_measurement_is_marked_valid(report) ||
                !bounded_equals_literal(report->gnss_state,
                                        sizeof(report->gnss_state),
                                        "no_fix") ||
                !bounded_equals_literal(report->source_status,
                                        sizeof(report->source_status),
                                        "observed")) {
                clear_mapped(mapped);
                return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
            }
            mapped->origin =
                EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_NO_FIX_OBSERVED;
            mapped->input.observation.type =
                EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX;
            return EGOLINK_LOCATION_HARDWARE_MAP_OK;
        }
        const bool valid_unverified_state =
            bounded_equals_literal(report->gnss_state,
                                   sizeof(report->gnss_state),
                                   "query_unverified") ||
            bounded_equals_literal(report->gnss_state,
                                   sizeof(report->gnss_state), "no_fix");
        if (report->location_result_valid || report->no_fix_observed ||
            !no_gnss_measurement_is_marked_valid(report) ||
            !valid_unverified_state ||
            !bounded_equals_literal(report->source_status,
                                    sizeof(report->source_status),
                                    "unverified")) {
            clear_mapped(mapped);
            return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
        }
        mapped->origin =
            EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_UNVERIFIED_RESULT;
        mapped->input.observation.type =
            EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR;
        return EGOLINK_LOCATION_HARDWARE_MAP_OK;
    }

    if (!bounded_equals_literal(report->gnss_state,
                                sizeof(report->gnss_state), "fix") ||
        !bounded_equals_literal(report->source_status,
                                sizeof(report->source_status), "observed") ||
        !report->lat_valid || !report->lon_valid ||
        !isfinite(report->lat) || !isfinite(report->lon) ||
        report->lat < -90.0 || report->lat > 90.0 ||
        report->lon < -180.0 || report->lon > 180.0 ||
        !valid_optional_gnss_measurements(report) ||
        (report->hdop_valid && (!isfinite(report->hdop) || report->hdop < 0.0))) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
    }
    /* Receiver fix and quality availability are independent. The existing
     * reducer retains a rejected-quality candidate without inventing accuracy. */
    mapped->origin =
        EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_FIX_CANDIDATE;
    mapped->input.observation.type = EGOLINK_LOCATION_ENGINE_EVENT_GNSS_FIX;
    mapped->input.observation.latitude_deg_present = true;
    mapped->input.observation.latitude_deg = report->lat;
    mapped->input.observation.longitude_deg_present = true;
    mapped->input.observation.longitude_deg = report->lon;
    mapped->input.observation.hdop_present = report->hdop_valid && report->hdop > 0.0;
    mapped->input.observation.hdop = report->hdop;
    return EGOLINK_LOCATION_HARDWARE_MAP_OK;
}

static const char *expected_lte_reason(const sim7670_lte_report_t *report)
{
    if (!report->driver_enabled) {
        return "LTE_STATUS_DISABLED";
    }
    if (!report->uart_ready) {
        return "LTE_UART_INIT_FAILED";
    }
    if (!report->at_ok) {
        return "LTE_AT_UNREACHABLE";
    }
    if (!report->cpin_query.parse_valid) {
        return "LTE_STATUS_UNKNOWN";
    }
    if (!report->sim_ready) {
        return "LTE_SIM_NOT_READY";
    }
    if (!report->cereg_query.parse_valid) {
        return "LTE_STATUS_UNKNOWN";
    }
    if (!report->registered) {
        return "LTE_NOT_REGISTERED";
    }
    if (!report->cgatt_query.parse_valid) {
        return "LTE_STATUS_UNKNOWN";
    }
    if (!report->attached) {
        return "LTE_NOT_ATTACHED";
    }
    if (!report->cgact_query.parse_valid) {
        return "LTE_STATUS_UNKNOWN";
    }
    if (!report->pdp_active) {
        return "LTE_PDP_INACTIVE";
    }
    return "LTE_READY";
}

static bool any_lte_query_was_attempted(
    const sim7670_lte_report_t *report)
{
    return report->cpin_query.attempted || report->cops_query.attempted ||
           report->cereg_query.attempted || report->cgatt_query.attempted ||
           report->cgdcont_query.attempted ||
           report->cgact_query.attempted ||
           report->cgpaddr_query.attempted || report->csq_query.attempted ||
           report->cpsi_query.attempted;
}

static const char *legacy_lte_reason(
    const sim7670_lte_report_t *report)
{
    if (!report->driver_enabled) {
        return "LTE_STATUS_DISABLED";
    }
    if (!report->uart_ready) {
        return "LTE_UART_INIT_FAILED";
    }
    if (!report->at_ok) {
        return "LTE_AT_UNREACHABLE";
    }
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

static bool valid_lte_report(const sim7670_lte_report_t *report)
{
    const bool evidence_present =
        report != NULL && any_lte_query_was_attempted(report);
    if (report == NULL ||
        !valid_at_query_evidence(&report->cpin_query) ||
        !valid_at_query_evidence(&report->cops_query) ||
        !valid_at_query_evidence(&report->cereg_query) ||
        !valid_at_query_evidence(&report->cgatt_query) ||
        !valid_at_query_evidence(&report->cgdcont_query) ||
        !valid_at_query_evidence(&report->cgact_query) ||
        !valid_at_query_evidence(&report->cgpaddr_query) ||
        !valid_at_query_evidence(&report->csq_query) ||
        !valid_at_query_evidence(&report->cpsi_query) ||
        (report->uart_ready && !report->driver_enabled) ||
        (report->at_ok && !report->uart_ready) ||
        (!report->at_ok && evidence_present) ||
        (evidence_present &&
         ((report->sim_ready && !report->cpin_query.parse_valid) ||
          (report->registered &&
           (!report->sim_ready || !report->cereg_query.parse_valid)) ||
          (report->attached &&
           (!report->registered || !report->cgatt_query.parse_valid)) ||
          (report->pdp_active &&
           (!report->attached || !report->cgact_query.parse_valid)) ||
          (report->ip_valid &&
           (!report->pdp_active ||
            !report->cgpaddr_query.parse_valid)) ||
          (report->cell_identity_valid &&
           !report->cpsi_query.parse_valid) ||
          (report->rssi_valid &&
           !report->csq_query.parse_valid &&
           !report->cpsi_query.parse_valid) ||
          ((report->rsrp_valid || report->rsrq_valid ||
            report->sinr_valid) &&
           !report->cpsi_query.parse_valid)))) {
        return false;
    }
    if (bounded_equals_literal(
            report->reason_code,
            sizeof(report->reason_code),
            expected_lte_reason(report))) {
        return true;
    }
    return !evidence_present &&
           bounded_equals_literal(
               report->reason_code,
               sizeof(report->reason_code),
               legacy_lte_reason(report));
}

static egolink_location_engine_lte_state_t lte_state(
    const sim7670_lte_report_t *report)
{
    if (!report->driver_enabled || !report->uart_ready || !report->at_ok) {
        return EGOLINK_LOCATION_ENGINE_LTE_UNAVAILABLE;
    }
    if (!report->cpin_query.parse_valid) {
        return EGOLINK_LOCATION_ENGINE_LTE_UNKNOWN;
    }
    if (!report->sim_ready) {
        return EGOLINK_LOCATION_ENGINE_LTE_OFFLINE;
    }
    if (!report->cereg_query.parse_valid) {
        return EGOLINK_LOCATION_ENGINE_LTE_UNKNOWN;
    }
    if (!report->registered) {
        return EGOLINK_LOCATION_ENGINE_LTE_OFFLINE;
    }
    if (!report->cgatt_query.parse_valid) {
        return EGOLINK_LOCATION_ENGINE_LTE_UNKNOWN;
    }
    if (!report->attached) {
        return EGOLINK_LOCATION_ENGINE_LTE_LIMITED;
    }
    if (!report->cgact_query.parse_valid) {
        return EGOLINK_LOCATION_ENGINE_LTE_UNKNOWN;
    }
    return report->pdp_active ? EGOLINK_LOCATION_ENGINE_LTE_ONLINE
                              : EGOLINK_LOCATION_ENGINE_LTE_LIMITED;
}

egolink_location_hardware_map_status_t
egolink_location_hardware_map_lte_state(
    const egolink_location_hardware_identity_t *identity,
    const sim7670_lte_report_t *report,
    egolink_location_hardware_mapped_input_t *mapped)
{
    if (identity == NULL || report == NULL || mapped == NULL) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_ARGUMENT;
    }
    if (!prepare_base(identity, mapped)) {
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_IDENTITY;
    }
    if (!valid_lte_report(report)) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
    }
    mapped->origin = EGOLINK_LOCATION_HARDWARE_ORIGIN_LTE_STATE;
    mapped->input.observation.type = EGOLINK_LOCATION_ENGINE_EVENT_LTE_STATE;
    mapped->input.observation.lte_state_present = true;
    mapped->input.observation.lte_state = lte_state(report);
    return EGOLINK_LOCATION_HARDWARE_MAP_OK;
}

static bool cell_digits(
    const char *text, size_t capacity, size_t minimum, size_t maximum,
    size_t *length)
{
    size_t bounded_length = 0U;
    if (!bounded_c_string(text, capacity, &bounded_length) ||
        bounded_length < minimum || bounded_length > maximum) {
        return false;
    }
    for (size_t index = 0U; index < bounded_length; ++index) {
        const unsigned char value = (unsigned char)text[index];
        if (value < (unsigned char)'0' || value > (unsigned char)'9') {
            return false;
        }
    }
    *length = bounded_length;
    return true;
}

static bool cell_hex(
    const char *text, size_t capacity, size_t minimum, size_t maximum,
    size_t *length)
{
    size_t bounded_length = 0U;
    if (!bounded_c_string(text, capacity, &bounded_length) ||
        bounded_length < minimum || bounded_length > maximum) {
        return false;
    }
    for (size_t index = 0U; index < bounded_length; ++index) {
        const unsigned char value = (unsigned char)text[index];
        const bool digit = value >= (unsigned char)'0' &&
                           value <= (unsigned char)'9';
        const bool lower = value >= (unsigned char)'a' &&
                           value <= (unsigned char)'f';
        const bool upper = value >= (unsigned char)'A' &&
                           value <= (unsigned char)'F';
        if (!digit && !lower && !upper) {
            return false;
        }
    }
    *length = bounded_length;
    return true;
}

static bool hash_cell_field(
    mbedtls_sha256_context *context,
    const char *text,
    size_t length,
    bool canonical_lowercase)
{
    if (length > UINT8_MAX) {
        return false;
    }
    const unsigned char length_byte = (unsigned char)length;
    if (mbedtls_sha256_update(context, &length_byte, 1U) != 0) {
        return false;
    }
    if (!canonical_lowercase) {
        return mbedtls_sha256_update(
                   context, (const unsigned char *)text, length) == 0;
    }
    for (size_t index = 0U; index < length; ++index) {
        unsigned char value = (unsigned char)text[index];
        if (value >= (unsigned char)'A' && value <= (unsigned char)'F') {
            value = (unsigned char)(value +
                                    ((unsigned char)'a' -
                                     (unsigned char)'A'));
        }
        if (mbedtls_sha256_update(context, &value, 1U) != 0) {
            return false;
        }
    }
    return true;
}

static bool build_cell_reference(
    const sim7670_lte_report_t *report,
    const char *device_scope,
    char output[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY])
{
    size_t mcc_length = 0U;
    size_t mnc_length = 0U;
    size_t tac_length = 0U;
    size_t cell_length = 0U;
    if (!cell_digits(report->mcc, sizeof(report->mcc), 3U, 3U,
                     &mcc_length) ||
        !cell_digits(report->mnc, sizeof(report->mnc), 2U, 3U,
                     &mnc_length) ||
        !cell_hex(report->tac, sizeof(report->tac), 1U, 8U, &tac_length) ||
        !cell_hex(report->cell_id, sizeof(report->cell_id), 1U, 16U,
                  &cell_length)) {
        return false;
    }
    static const unsigned char domain[] =
        "egolink.cell.reference.v1";
    const size_t device_scope_length = strlen(device_scope);
    unsigned char digest[32];
    mbedtls_sha256_context context;
    mbedtls_sha256_init(&context);
    bool ok = mbedtls_sha256_starts(&context, 0) == 0 &&
              mbedtls_sha256_update(
                  &context, domain, sizeof(domain) - 1U) == 0 &&
              hash_cell_field(&context, device_scope,
                              device_scope_length, false) &&
              hash_cell_field(&context, report->mcc, mcc_length, false) &&
              hash_cell_field(&context, report->mnc, mnc_length, false) &&
              hash_cell_field(&context, report->tac, tac_length, true) &&
              hash_cell_field(&context, report->cell_id, cell_length, true) &&
              mbedtls_sha256_finish(&context, digest) == 0;
    mbedtls_sha256_free(&context);
    if (!ok) {
        (void)memset(digest, 0, sizeof(digest));
        return false;
    }
    static const char hex[] = "0123456789abcdef";
    (void)memset(output, 0, EGOLINK_LOCATION_RUNTIME_ID_CAPACITY);
    (void)memcpy(output, "cell:v1:", sizeof("cell:v1:") - 1U);
    const size_t prefix_length = sizeof("cell:v1:") - 1U;
    for (size_t index = 0U; index < 20U; ++index) {
        output[prefix_length + (index * 2U)] =
            hex[(digest[index] >> 4U) & 0x0fU];
        output[prefix_length + (index * 2U) + 1U] =
            hex[digest[index] & 0x0fU];
    }
    output[EGOLINK_LOCATION_RUNTIME_ID_MAX_BYTES] = '\0';
    (void)memset(digest, 0, sizeof(digest));
    return true;
}

egolink_location_hardware_map_status_t
egolink_location_hardware_map_cell(
    const egolink_location_hardware_identity_t *identity,
    const sim7670_lte_report_t *report,
    egolink_location_hardware_mapped_input_t *mapped)
{
    if (identity == NULL || report == NULL || mapped == NULL) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_ARGUMENT;
    }
    if (!prepare_base(identity, mapped)) {
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_IDENTITY;
    }
    if (!valid_lte_report(report)) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
    }
    if (lte_state(report) != EGOLINK_LOCATION_ENGINE_LTE_ONLINE ||
        !report->cpsi_query.response_observed ||
        !report->cpsi_query.parse_valid ||
        !report->cell_identity_valid ||
        !build_cell_reference(report, mapped->device_id,
                              mapped->cell_reference_id)) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_CELL_ID_UNAVAILABLE;
    }
    mapped->origin = EGOLINK_LOCATION_HARDWARE_ORIGIN_CELL_OBSERVATION;
    mapped->input.observation.type =
        EGOLINK_LOCATION_ENGINE_EVENT_CELL_OBSERVATION;
    mapped->input.observation.reference_id_present = true;
    mapped->input.observation.reference_id =
        engine_text(mapped->cell_reference_id);
    return EGOLINK_LOCATION_HARDWARE_MAP_OK;
}

egolink_location_hardware_map_status_t
egolink_location_hardware_map_imu(
    const egolink_location_hardware_identity_t *identity,
    const platform_imu_sample_t *sample,
    egolink_location_hardware_mapped_input_t *mapped)
{
    if (identity == NULL || sample == NULL || mapped == NULL) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_ARGUMENT;
    }
    if (!prepare_base(identity, mapped)) {
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_IDENTITY;
    }
    if (sample->sample_is_mock) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_MOCK_REJECTED;
    }
    if (sample->seq == 0U || sample->uptime_ms < 0 ||
        !bounded_equals_literal(sample->source,
                                sizeof("qmi8658_i2c"),
                                "qmi8658_i2c")) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
    }
    const uint64_t uptime_ms = (uint64_t)sample->uptime_ms;
    if (identity->source_event_time_source !=
            EGOLINK_LOCATION_TIME_TIMESTAMP_MONOTONIC_NS ||
        identity->source_event_time_ms != uptime_ms ||
        uptime_ms > UINT64_MAX / UINT64_C(1000000) ||
        identity->source_event_time_ns != uptime_ms * UINT64_C(1000000)) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_SOURCE_TIME_MISMATCH;
    }
    mapped->origin = EGOLINK_LOCATION_HARDWARE_ORIGIN_IMU_REAL;
    mapped->input.observation.type = EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE;
    return EGOLINK_LOCATION_HARDWARE_MAP_OK;
}

egolink_location_hardware_map_status_t
egolink_location_hardware_map_battery(
    const egolink_location_hardware_identity_t *identity,
    const egolink_location_hardware_battery_input_t *battery,
    egolink_location_hardware_mapped_input_t *mapped)
{
    if (identity == NULL || battery == NULL || mapped == NULL) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_ARGUMENT;
    }
    if (!prepare_base(identity, mapped)) {
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_IDENTITY;
    }
    if (battery->value_is_mock) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_MOCK_REJECTED;
    }
    if (battery->state < EGOLINK_LOCATION_ENGINE_BATTERY_NORMAL ||
        battery->state >= EGOLINK_LOCATION_ENGINE_BATTERY_COUNT ||
        (battery->percent_present &&
         (!isfinite(battery->percent) || battery->percent < 0.0 ||
          battery->percent > 100.0))) {
        clear_mapped(mapped);
        return EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT;
    }
    mapped->origin =
        EGOLINK_LOCATION_HARDWARE_ORIGIN_BATTERY_CALLER_SUPPLIED;
    mapped->input.observation.type = EGOLINK_LOCATION_ENGINE_EVENT_BATTERY;
    mapped->input.observation.battery_state_present = true;
    mapped->input.observation.battery_state = battery->state;
    mapped->input.observation.battery_percent_present =
        battery->percent_present;
    mapped->input.observation.battery_percent = battery->percent;
    return EGOLINK_LOCATION_HARDWARE_MAP_OK;
}

const char *egolink_location_hardware_map_status_name(
    egolink_location_hardware_map_status_t status)
{
    switch (status) {
    case EGOLINK_LOCATION_HARDWARE_MAP_OK:
        return "ok";
    case EGOLINK_LOCATION_HARDWARE_MAP_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_LOCATION_HARDWARE_MAP_INVALID_IDENTITY:
        return "invalid_identity";
    case EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT:
        return "invalid_report";
    case EGOLINK_LOCATION_HARDWARE_MAP_FIX_QUALITY_UNAVAILABLE:
        return "fix_quality_unavailable";
    case EGOLINK_LOCATION_HARDWARE_MAP_CELL_ID_UNAVAILABLE:
        return "cell_id_unavailable";
    case EGOLINK_LOCATION_HARDWARE_MAP_MOCK_REJECTED:
        return "mock_rejected";
    case EGOLINK_LOCATION_HARDWARE_MAP_SOURCE_TIME_MISMATCH:
        return "source_time_mismatch";
    default:
        return "unknown";
    }
}

static location_hardware_actuator_internal_t *actuator_internal(
    egolink_location_hardware_actuator_t *actuator)
{
    return (location_hardware_actuator_internal_t *)(void *)actuator->opaque;
}

static const location_hardware_actuator_internal_t *actuator_internal_const(
    const egolink_location_hardware_actuator_t *actuator)
{
    return (const location_hardware_actuator_internal_t *)(const void *)
        actuator->opaque;
}

static bool valid_actuator(
    const location_hardware_actuator_internal_t *internal)
{
    return internal != NULL && internal->magic == LOCATION_HARDWARE_ACTUATOR_MAGIC &&
           internal->snapshot.initialized;
}

static void increment_saturated(uint64_t *value)
{
    if (*value < UINT64_MAX) {
        ++(*value);
    }
}

static egolink_location_hardware_action_status_t unavailable_action(
    location_hardware_actuator_internal_t *internal)
{
    return internal->snapshot.enabled
               ? EGOLINK_LOCATION_HARDWARE_ACTION_NOT_SUPPORTED
               : EGOLINK_LOCATION_HARDWARE_ACTION_DISABLED;
}

static bool unsupported_gnss_start(
    void *context,
    const egolink_device_location_gnss_start_request_t *request)
{
    location_hardware_actuator_internal_t *internal =
        (location_hardware_actuator_internal_t *)context;
    if (!valid_actuator(internal) || request == NULL) {
        return false;
    }
    increment_saturated(&internal->snapshot.action_requests);
    internal->snapshot.gnss_start = unavailable_action(internal);
    return false;
}

static bool unsupported_gnss_stop(
    void *context,
    const egolink_device_location_gnss_stop_request_t *request)
{
    location_hardware_actuator_internal_t *internal =
        (location_hardware_actuator_internal_t *)context;
    if (!valid_actuator(internal) || request == NULL) {
        return false;
    }
    increment_saturated(&internal->snapshot.action_requests);
    internal->snapshot.gnss_stop = unavailable_action(internal);
    return false;
}

static bool observe_cell(
    void *context,
    const egolink_device_location_cell_observe_request_t *request)
{
    location_hardware_actuator_internal_t *internal =
        (location_hardware_actuator_internal_t *)context;
    if (!valid_actuator(internal) || request == NULL) {
        return false;
    }
    increment_saturated(&internal->snapshot.action_requests);
    internal->snapshot.cell_observe = unavailable_action(internal);
    return false;
}

static bool unsupported_imu_rate(
    void *context,
    const egolink_device_location_imu_rate_request_t *request)
{
    location_hardware_actuator_internal_t *internal =
        (location_hardware_actuator_internal_t *)context;
    if (!valid_actuator(internal) || request == NULL) {
        return false;
    }
    increment_saturated(&internal->snapshot.action_requests);
    internal->snapshot.imu_rate = unavailable_action(internal);
    return false;
}

static bool unsupported_lte_keep_connected(
    void *context,
    const egolink_device_location_lte_connection_request_t *request)
{
    location_hardware_actuator_internal_t *internal =
        (location_hardware_actuator_internal_t *)context;
    if (!valid_actuator(internal) || request == NULL) {
        return false;
    }
    increment_saturated(&internal->snapshot.action_requests);
    internal->snapshot.lte_keep_connected = unavailable_action(internal);
    return false;
}

static bool unsupported_upload_intent(
    void *context,
    const egolink_device_location_upload_intent_t *request)
{
    location_hardware_actuator_internal_t *internal =
        (location_hardware_actuator_internal_t *)context;
    if (!valid_actuator(internal) || request == NULL) {
        return false;
    }
    increment_saturated(&internal->snapshot.action_requests);
    internal->snapshot.upload_intent = unavailable_action(internal);
    return false;
}

static bool unsupported_safe_cancel(
    void *context,
    const egolink_device_location_cancel_request_t *request)
{
    location_hardware_actuator_internal_t *internal =
        (location_hardware_actuator_internal_t *)context;
    if (!valid_actuator(internal) || request == NULL) {
        return false;
    }
    increment_saturated(&internal->snapshot.action_requests);
    internal->snapshot.safe_cancel = unavailable_action(internal);
    return false;
}

void egolink_location_hardware_actuator_default_config(
    egolink_location_hardware_actuator_config_t *config)
{
    if (config != NULL) {
        (void)memset(config, 0, sizeof(*config));
        config->enabled = false;
    }
}

bool egolink_location_hardware_actuator_init(
    egolink_location_hardware_actuator_t *actuator,
    const egolink_location_hardware_actuator_config_t *config)
{
    if (actuator == NULL || config == NULL) {
        return false;
    }
    const bool enabled = config->enabled;
    /* Never inspect caller storage before establishing its object state. */
    (void)memset(actuator, 0, sizeof(*actuator));
    location_hardware_actuator_internal_t *internal =
        actuator_internal(actuator);
    internal->magic = LOCATION_HARDWARE_ACTUATOR_MAGIC;
    internal->snapshot.initialized = true;
    internal->snapshot.enabled = enabled;
    internal->snapshot.gnss_start =
        EGOLINK_LOCATION_HARDWARE_ACTION_NEVER_REQUESTED;
    internal->snapshot.gnss_stop =
        EGOLINK_LOCATION_HARDWARE_ACTION_NEVER_REQUESTED;
    internal->snapshot.cell_observe =
        EGOLINK_LOCATION_HARDWARE_ACTION_NEVER_REQUESTED;
    internal->snapshot.imu_rate =
        EGOLINK_LOCATION_HARDWARE_ACTION_NEVER_REQUESTED;
    internal->snapshot.lte_keep_connected =
        EGOLINK_LOCATION_HARDWARE_ACTION_NEVER_REQUESTED;
    internal->snapshot.upload_intent =
        EGOLINK_LOCATION_HARDWARE_ACTION_NEVER_REQUESTED;
    internal->snapshot.safe_cancel =
        EGOLINK_LOCATION_HARDWARE_ACTION_NEVER_REQUESTED;
    return true;
}

bool egolink_location_hardware_actuator_callbacks(
    egolink_location_hardware_actuator_t *actuator,
    egolink_device_location_runtime_callbacks_t *callbacks)
{
    if (actuator == NULL || callbacks == NULL ||
        !valid_actuator(actuator_internal_const(actuator))) {
        if (callbacks != NULL) {
            (void)memset(callbacks, 0, sizeof(*callbacks));
        }
        return false;
    }
    *callbacks = (egolink_device_location_runtime_callbacks_t){
        .context = actuator_internal(actuator),
        .gnss_start = unsupported_gnss_start,
        .gnss_stop = unsupported_gnss_stop,
        .cell_observe = observe_cell,
        .set_imu_rate = unsupported_imu_rate,
        .set_lte_keep_connected = unsupported_lte_keep_connected,
        .upload_intent = unsupported_upload_intent,
        .safe_cancel = unsupported_safe_cancel,
    };
    return true;
}

bool egolink_location_hardware_actuator_snapshot(
    const egolink_location_hardware_actuator_t *actuator,
    egolink_location_hardware_actuator_snapshot_t *snapshot)
{
    if (snapshot != NULL) {
        (void)memset(snapshot, 0, sizeof(*snapshot));
    }
    if (actuator == NULL || snapshot == NULL) {
        return false;
    }
    const location_hardware_actuator_internal_t *internal =
        actuator_internal_const(actuator);
    if (!valid_actuator(internal)) {
        return false;
    }
    *snapshot = internal->snapshot;
    return true;
}

const char *egolink_location_hardware_action_status_name(
    egolink_location_hardware_action_status_t status)
{
    switch (status) {
    case EGOLINK_LOCATION_HARDWARE_ACTION_NEVER_REQUESTED:
        return "never_requested";
    case EGOLINK_LOCATION_HARDWARE_ACTION_SUCCEEDED:
        return "succeeded";
    case EGOLINK_LOCATION_HARDWARE_ACTION_FAILED:
        return "failed";
    case EGOLINK_LOCATION_HARDWARE_ACTION_NOT_SUPPORTED:
        return "not_supported";
    case EGOLINK_LOCATION_HARDWARE_ACTION_DISABLED:
        return "disabled";
    default:
        return "unknown";
    }
}

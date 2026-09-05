#include "location_engine_core.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    char *data;
    size_t capacity;
    size_t length;
    bool overflow;
} json_writer_t;

#define ARRAY_COUNT(value) (sizeof(value) / sizeof((value)[0]))

static const char *const EVENT_NAMES[EGOLINK_LOCATION_ENGINE_EVENT_COUNT] = {
    "tick",
    "imu_sample",
    "mobility",
    "gnss_started",
    "gnss_stopped",
    "gnss_no_fix",
    "gnss_error",
    "gnss_fix",
    "coarse_location",
    "lte_state",
    "cell_observation",
    "battery",
    "sos",
};

static const char *const MOBILITY_NAMES[EGOLINK_LOCATION_ENGINE_MOBILITY_COUNT] = {
    "stable", "moving", "unknown"};

static const char *const GNSS_NAMES[EGOLINK_LOCATION_ENGINE_GNSS_COUNT] = {
    "idle", "acquiring", "fix", "no_fix", "fix_rejected", "error",
    "unavailable"};

static const char *const LTE_NAMES[EGOLINK_LOCATION_ENGINE_LTE_COUNT] = {
    "offline", "online", "limited", "unavailable", "unknown"};

static const char *const LTE_REASON_NAMES[EGOLINK_LOCATION_ENGINE_LTE_COUNT] = {
    "lte_offline", "lte_online", "lte_limited", "lte_unavailable",
    "lte_unknown"};

static const char *const BATTERY_NAMES[EGOLINK_LOCATION_ENGINE_BATTERY_COUNT] = {
    "normal", "low", "critical", "charging", "unknown"};

static const char *const BATTERY_REASON_NAMES[
    EGOLINK_LOCATION_ENGINE_BATTERY_COUNT] = {
    "battery_normal", "battery_low", "battery_critical", "battery_charging",
    "battery_unknown"};

static const char *const POLICY_NAMES[EGOLINK_LOCATION_ENGINE_POLICY_COUNT] = {
    "STABLE", "MOVING", "LOCATION_UNCERTAIN", "SOS", "LOW_BATTERY"};

static const char *const BELIEF_NAMES[EGOLINK_LOCATION_ENGINE_BELIEF_COUNT] = {
    "Fine", "Coarse", "Predicted", "Unknown"};

static const char *const SOURCE_NAMES[EGOLINK_LOCATION_ENGINE_SOURCE_COUNT] = {
    "gnss", "cell_reference", "wifi_reference", "known_place", "last_trusted",
    "none"};

static const char *const UNCERTAINTY_NAMES[
    EGOLINK_LOCATION_ENGINE_UNCERTAINTY_COUNT] = {
    "source_reported_accuracy",
    "hdop_rule_heuristic_v0",
    "reference_bound",
    "last_trusted_age_growth_rule_v0",
    "unavailable",
};

static const char *const SOURCE_STATUS_NAMES[
    EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_COUNT] = {
    "observed", "verified", "rule_derived"};

static const char *const TIME_SOURCE_NAMES[EGOLINK_LOCATION_ENGINE_TIME_COUNT] = {
    "gnss_source_utc_ns",
    "timestamp_utc_ns",
    "timestamp_monotonic_ns",
    "policy_rule_v0",
    "policy_timer_v0",
    "policy_action_v0",
};

static const char *const REASON_NAMES[EGOLINK_LOCATION_ENGINE_REASON_COUNT] = {
    "no_observation_yet",
    "no_trusted_location",
    "policy_clock_advanced",
    "imu_observed_without_coordinate_derivation",
    "mobility_stable",
    "mobility_moving",
    "mobility_unknown",
    "gnss_acquisition_started",
    "gnss_acquisition_stopped",
    "gnss_no_fix_preserved_last_trusted",
    "gnss_error_preserved_last_trusted",
    "gnss_fix_rejected_untrusted_lineage",
    "gnss_fix_rejected_invalid_measurement",
    "latitude_deg_must_be_numeric",
    "latitude_deg_must_be_finite",
    "longitude_deg_must_be_numeric",
    "longitude_deg_must_be_finite",
    "accuracy_m_must_be_finite",
    "hdop_must_be_finite",
    "gnss_fix_rejected_coordinate_range",
    "gnss_fix_rejected_reported_accuracy",
    "gnss_fix_rejected_hdop_uncertainty",
    "gnss_fix_rejected_quality_gate",
    "gnss_fix_accepted",
    "coarse_reference_accepted",
    "lte_offline",
    "lte_online",
    "lte_limited",
    "lte_unavailable",
    "lte_unknown",
    "cell_observed_without_coordinate_derivation",
    "battery_normal",
    "battery_low",
    "battery_critical",
    "battery_charging",
    "battery_unknown",
    "sos_active",
    "sos_cleared",
    "observation_applied",
    "trusted_location_fresh",
    "uncertainty_growth_overflow",
    "last_trusted_retained_as_memory_only",
    "last_trusted_preserved",
    "belief_forced_predicted",
    "belief_aged",
    "prediction_horizon_exceeded",
};

_Static_assert(ARRAY_COUNT(EVENT_NAMES) == EGOLINK_LOCATION_ENGINE_EVENT_COUNT,
               "event name table drift");
_Static_assert(
    ARRAY_COUNT(MOBILITY_NAMES) == EGOLINK_LOCATION_ENGINE_MOBILITY_COUNT,
    "mobility name table drift");
_Static_assert(ARRAY_COUNT(GNSS_NAMES) == EGOLINK_LOCATION_ENGINE_GNSS_COUNT,
               "GNSS name table drift");
_Static_assert(ARRAY_COUNT(LTE_NAMES) == EGOLINK_LOCATION_ENGINE_LTE_COUNT,
               "LTE name table drift");
_Static_assert(ARRAY_COUNT(BATTERY_NAMES) == EGOLINK_LOCATION_ENGINE_BATTERY_COUNT,
               "battery name table drift");
_Static_assert(ARRAY_COUNT(POLICY_NAMES) == EGOLINK_LOCATION_ENGINE_POLICY_COUNT,
               "policy name table drift");
_Static_assert(ARRAY_COUNT(BELIEF_NAMES) == EGOLINK_LOCATION_ENGINE_BELIEF_COUNT,
               "belief name table drift");
_Static_assert(ARRAY_COUNT(SOURCE_NAMES) == EGOLINK_LOCATION_ENGINE_SOURCE_COUNT,
               "source name table drift");
_Static_assert(
    ARRAY_COUNT(UNCERTAINTY_NAMES) ==
        EGOLINK_LOCATION_ENGINE_UNCERTAINTY_COUNT,
    "uncertainty name table drift");
_Static_assert(
    ARRAY_COUNT(SOURCE_STATUS_NAMES) ==
        EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_COUNT,
    "source-status name table drift");
_Static_assert(
    ARRAY_COUNT(TIME_SOURCE_NAMES) == EGOLINK_LOCATION_ENGINE_TIME_COUNT,
    "time-source name table drift");
_Static_assert(ARRAY_COUNT(REASON_NAMES) == EGOLINK_LOCATION_ENGINE_REASON_COUNT,
               "reason name table drift");

static bool enum_in_range(int value, int count)
{
    return value >= 0 && value < count;
}

static bool strings_equal(const char *left, const char *right)
{
    return left != NULL && right != NULL && strcmp(left, right) == 0;
}

static bool valid_utf8(const char *data, size_t length)
{
    size_t index = 0U;
    while (index < length) {
        const unsigned char first = (unsigned char)data[index];
        if (first <= 0x7fU) {
            ++index;
            continue;
        }
        size_t continuation_count = 0U;
        uint32_t code_point = 0U;
        uint32_t minimum = 0U;
        if (first >= 0xc2U && first <= 0xdfU) {
            continuation_count = 1U;
            code_point = first & 0x1fU;
            minimum = 0x80U;
        } else if (first >= 0xe0U && first <= 0xefU) {
            continuation_count = 2U;
            code_point = first & 0x0fU;
            minimum = 0x800U;
        } else if (first >= 0xf0U && first <= 0xf4U) {
            continuation_count = 3U;
            code_point = first & 0x07U;
            minimum = 0x10000U;
        } else {
            return false;
        }
        if (continuation_count > length - index - 1U) {
            return false;
        }
        for (size_t offset = 1U; offset <= continuation_count; ++offset) {
            const unsigned char next = (unsigned char)data[index + offset];
            if ((next & 0xc0U) != 0x80U) {
                return false;
            }
            code_point = (code_point << 6U) | (next & 0x3fU);
        }
        if (code_point < minimum || code_point > 0x10ffffU ||
            (code_point >= 0xd800U && code_point <= 0xdfffU)) {
            return false;
        }
        index += continuation_count + 1U;
    }
    return true;
}

static bool valid_text(egolink_location_engine_text_t text, size_t maximum)
{
    return text.data != NULL && text.length > 0U && text.length <= maximum &&
           valid_utf8(text.data, text.length);
}

static bool copy_text(
    egolink_location_engine_owned_text_t *output,
    egolink_location_engine_text_t input)
{
    if (output == NULL ||
        !valid_text(input, EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES)) {
        return false;
    }
    memset(output, 0, sizeof(*output));
    memcpy(output->data, input.data, input.length);
    output->length = input.length;
    return true;
}

static bool owned_text_valid(
    const egolink_location_engine_owned_text_t *text, size_t maximum)
{
    return text != NULL && text->length > 0U && text->length <= maximum &&
           text->data[text->length] == '\0' &&
           valid_utf8(text->data, text->length);
}

static void reasons_clear(egolink_location_engine_reasons_t *reasons)
{
    memset(reasons, 0, sizeof(*reasons));
}

static bool reasons_add(
    egolink_location_engine_reasons_t *reasons, const char *reason)
{
    const size_t length = reason == NULL ? 0U : strlen(reason);
    if (reasons == NULL || length == 0U ||
        length > EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_BYTES) {
        return false;
    }
    egolink_location_engine_reason_t selected =
        EGOLINK_LOCATION_ENGINE_REASON_COUNT;
    for (int index = 0; index < (int)EGOLINK_LOCATION_ENGINE_REASON_COUNT;
         ++index) {
        if (strlen(REASON_NAMES[index]) == length &&
            memcmp(REASON_NAMES[index], reason, length) == 0) {
            selected = (egolink_location_engine_reason_t)index;
            break;
        }
    }
    if (selected == EGOLINK_LOCATION_ENGINE_REASON_COUNT) {
        return false;
    }
    for (size_t index = 0U; index < reasons->count; ++index) {
        if (reasons->values[index] == selected) {
            return true;
        }
    }
    if (reasons->count >= EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_COUNT) {
        return false;
    }
    reasons->values[reasons->count] = selected;
    ++reasons->count;
    return true;
}

static bool reasons_copy(
    egolink_location_engine_reasons_t *output,
    const egolink_location_engine_reasons_t *input)
{
    if (output == NULL || input == NULL ||
        input->count > EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_COUNT) {
        return false;
    }
    reasons_clear(output);
    for (size_t index = 0U; index < input->count; ++index) {
        if (!enum_in_range((int)input->values[index],
                           (int)EGOLINK_LOCATION_ENGINE_REASON_COUNT) ||
            !reasons_add(output, REASON_NAMES[input->values[index]])) {
            return false;
        }
    }
    return true;
}

void egolink_location_engine_default_config(
    egolink_location_engine_config_t *output)
{
    if (output == NULL) {
        return;
    }
    *output = (egolink_location_engine_config_t){
        .profile_id = EGOLINK_LOCATION_ENGINE_CORE_PROFILE_ID,
        .profile_hash = EGOLINK_LOCATION_ENGINE_CORE_PROFILE_HASH,
        .provenance = EGOLINK_LOCATION_ENGINE_CORE_PROFILE_PROVENANCE,
        .fine_max_accuracy_m = 100.0,
        .fine_max_hdop = 5.0,
        .hdop_uncertainty_multiplier_m = 5.0,
        .coarse_max_uncertainty_m = 5000.0,
        .fine_freshness_ms = UINT64_C(30000),
        .coarse_freshness_ms = UINT64_C(120000),
        .prediction_horizon_ms = UINT64_C(900000),
        .uncertainty_growth_mps = 1.5,
        .fine_initial_confidence = 0.95,
        .coarse_initial_confidence = 0.65,
        .predicted_min_confidence = 0.10,
    };
}

egolink_location_engine_result_t egolink_location_engine_validate_config(
    const egolink_location_engine_config_t *config)
{
    if (config == NULL) {
        return EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    }
    if (!strings_equal(config->profile_id,
                       EGOLINK_LOCATION_ENGINE_CORE_PROFILE_ID) ||
        !strings_equal(config->profile_hash,
                       EGOLINK_LOCATION_ENGINE_CORE_PROFILE_HASH) ||
        !strings_equal(config->provenance,
                       EGOLINK_LOCATION_ENGINE_CORE_PROFILE_PROVENANCE) ||
        !isfinite(config->fine_max_accuracy_m) ||
        config->fine_max_accuracy_m != 100.0 ||
        !isfinite(config->fine_max_hdop) || config->fine_max_hdop != 5.0 ||
        !isfinite(config->hdop_uncertainty_multiplier_m) ||
        config->hdop_uncertainty_multiplier_m != 5.0 ||
        !isfinite(config->coarse_max_uncertainty_m) ||
        config->coarse_max_uncertainty_m != 5000.0 ||
        config->fine_freshness_ms != UINT64_C(30000) ||
        config->coarse_freshness_ms != UINT64_C(120000) ||
        config->prediction_horizon_ms != UINT64_C(900000) ||
        !isfinite(config->uncertainty_growth_mps) ||
        config->uncertainty_growth_mps != 1.5 ||
        !isfinite(config->fine_initial_confidence) ||
        config->fine_initial_confidence != 0.95 ||
        !isfinite(config->coarse_initial_confidence) ||
        config->coarse_initial_confidence != 0.65 ||
        !isfinite(config->predicted_min_confidence) ||
        config->predicted_min_confidence != 0.10) {
        return EGOLINK_LOCATION_ENGINE_INVALID_CONFIG;
    }
    return EGOLINK_LOCATION_ENGINE_OK;
}

egolink_location_engine_result_t egolink_location_engine_init(
    egolink_location_engine_core_t *core,
    const egolink_location_engine_config_t *config)
{
    if (core == NULL || config == NULL) {
        return EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    }
    const egolink_location_engine_result_t validation =
        egolink_location_engine_validate_config(config);
    if (validation != EGOLINK_LOCATION_ENGINE_OK) {
        memset(core, 0, sizeof(*core));
        return validation;
    }
    egolink_location_engine_core_t staged = {0};
    egolink_location_engine_config_t frozen_config;
    egolink_location_engine_default_config(&frozen_config);
    staged.initialized = true;
    staged.config = frozen_config;
    staged.mobility_state = EGOLINK_LOCATION_ENGINE_MOBILITY_UNKNOWN;
    staged.gnss_state = EGOLINK_LOCATION_ENGINE_GNSS_IDLE;
    staged.lte_state = EGOLINK_LOCATION_ENGINE_LTE_UNKNOWN;
    staged.battery_state = EGOLINK_LOCATION_ENGINE_BATTERY_UNKNOWN;
    staged.sensor_policy_state = EGOLINK_LOCATION_ENGINE_POLICY_STABLE;
    staged.last_trusted_belief = EGOLINK_LOCATION_ENGINE_BELIEF_UNKNOWN;
    if (!reasons_add(&staged.last_reason_codes, "no_observation_yet")) {
        memset(core, 0, sizeof(*core));
        return EGOLINK_LOCATION_ENGINE_INVALID_CONFIG;
    }
    *core = staged;
    return EGOLINK_LOCATION_ENGINE_OK;
}

egolink_location_engine_result_t egolink_location_engine_set_policy_context(
    egolink_location_engine_core_t *core,
    egolink_location_engine_policy_state_t policy_state)
{
    if (core == NULL) {
        return EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    }
    if (!core->initialized) {
        return EGOLINK_LOCATION_ENGINE_NOT_INITIALIZED;
    }
    if (!enum_in_range((int)policy_state,
                       (int)EGOLINK_LOCATION_ENGINE_POLICY_COUNT)) {
        return EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    core->sensor_policy_state = policy_state;
    return EGOLINK_LOCATION_ENGINE_OK;
}

static bool trusted_source_status(
    egolink_location_engine_source_status_t status)
{
    return status == EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED ||
           status == EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_VERIFIED;
}

static bool optional_text_valid(
    bool present, egolink_location_engine_text_t text)
{
    return !present ||
           valid_text(text, EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES);
}

static bool copy_optional_text(
    bool present,
    egolink_location_engine_text_t input,
    bool *output_present,
    egolink_location_engine_owned_text_t *output)
{
    *output_present = present;
    if (!present) {
        memset(output, 0, sizeof(*output));
        return true;
    }
    return copy_text(output, input);
}

static bool trusted_lineage_binding(
    const egolink_location_engine_lineage_t *lineage,
    uint64_t event_time_ms,
    egolink_location_engine_time_source_t *time_source,
    uint64_t *capture_time_ns)
{
    if (lineage == NULL || time_source == NULL || capture_time_ns == NULL ||
        !lineage->present ||
        !valid_text(lineage->observation_id,
                    EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES) ||
        !trusted_source_status(lineage->source_status) ||
        !optional_text_valid(lineage->stream_id_present, lineage->stream_id) ||
        !optional_text_valid(lineage->device_run_id_present,
                             lineage->device_run_id)) {
        return false;
    }
    if (lineage->outer_evidence_source_status_present &&
        lineage->outer_evidence_source_status != lineage->source_status) {
        return false;
    }

    if (lineage->gnss_source_utc_ns_present &&
        lineage->gnss_source_utc_ns / UINT64_C(1000000) == event_time_ms) {
        *time_source = EGOLINK_LOCATION_ENGINE_TIME_GNSS_SOURCE_UTC_NS;
        *capture_time_ns = lineage->gnss_source_utc_ns;
    } else if (lineage->timestamp_utc_ns_present &&
               lineage->timestamp_utc_ns / UINT64_C(1000000) ==
                   event_time_ms) {
        *time_source = EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_UTC_NS;
        *capture_time_ns = lineage->timestamp_utc_ns;
    } else if (lineage->timestamp_monotonic_ns_present &&
               lineage->timestamp_monotonic_ns / UINT64_C(1000000) ==
                   event_time_ms &&
               lineage->boot_count_present &&
               lineage->monotonic_clock_domain_id_present &&
               valid_text(lineage->monotonic_clock_domain_id,
                          EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES)) {
        *time_source = EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_MONOTONIC_NS;
        *capture_time_ns = lineage->timestamp_monotonic_ns;
    } else {
        return false;
    }
    return true;
}

static bool trusted_evidence_valid(
    const egolink_location_engine_lineage_t *lineage,
    uint64_t event_time_ms)
{
    egolink_location_engine_time_source_t time_source;
    uint64_t capture_time_ns;
    return trusted_lineage_binding(lineage, event_time_ms, &time_source,
                                   &capture_time_ns);
}

static bool trusted_evidence_ref(
    const egolink_location_engine_lineage_t *lineage,
    uint64_t event_time_ms,
    egolink_location_engine_evidence_ref_t *output)
{
    egolink_location_engine_time_source_t time_source;
    uint64_t capture_time_ns;
    if (output == NULL ||
        !trusted_lineage_binding(lineage, event_time_ms, &time_source,
                                 &capture_time_ns)) {
        return false;
    }

    egolink_location_engine_evidence_ref_t staged = {0};
    if (!copy_text(&staged.observation_id, lineage->observation_id) ||
        !copy_optional_text(lineage->stream_id_present, lineage->stream_id,
                            &staged.stream_id_present, &staged.stream_id) ||
        !copy_optional_text(lineage->device_run_id_present,
                            lineage->device_run_id,
                            &staged.device_run_id_present,
                            &staged.device_run_id)) {
        return false;
    }
    staged.source_status = lineage->source_status;
    staged.sequence_id_present = lineage->sequence_id_present;
    staged.sequence_id = lineage->sequence_id;
    staged.boot_count_present = lineage->boot_count_present;
    staged.boot_count = lineage->boot_count;
    staged.event_time_ms = event_time_ms;
    staged.event_time_source = time_source;
    staged.capture_time_ns = capture_time_ns;
    if (time_source == EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_MONOTONIC_NS) {
        if (!copy_optional_text(true, lineage->monotonic_clock_domain_id,
                                &staged.monotonic_clock_domain_id_present,
                                &staged.monotonic_clock_domain_id)) {
            return false;
        }
    }
    *output = staged;
    return true;
}

static bool text_views_equal(
    egolink_location_engine_text_t left,
    egolink_location_engine_text_t right)
{
    return left.length == right.length && left.data != NULL &&
           right.data != NULL && memcmp(left.data, right.data, left.length) == 0;
}

static bool rule_derived_lineage_valid(
    const egolink_location_engine_lineage_t *lineage)
{
    if (lineage == NULL || !lineage->present ||
        lineage->source_status !=
            EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_RULE_DERIVED ||
        !valid_text(lineage->observation_id,
                    EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES) ||
        !lineage->derived_time_source_present ||
        (lineage->derived_time_source !=
             EGOLINK_LOCATION_ENGINE_TIME_POLICY_RULE_V0 &&
         lineage->derived_time_source !=
             EGOLINK_LOCATION_ENGINE_TIME_POLICY_TIMER_V0 &&
         lineage->derived_time_source !=
             EGOLINK_LOCATION_ENGINE_TIME_POLICY_ACTION_V0) ||
        lineage->basis_count == 0U ||
        lineage->basis_count >
            EGOLINK_LOCATION_ENGINE_CORE_RULE_BASIS_MAX_COUNT) {
        return false;
    }
    for (size_t index = 0U; index < lineage->basis_count; ++index) {
        if (!valid_text(lineage->basis_observation_ids[index],
                        EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES)) {
            return false;
        }
        for (size_t prior = 0U; prior < index; ++prior) {
            if (text_views_equal(lineage->basis_observation_ids[index],
                                 lineage->basis_observation_ids[prior])) {
                return false;
            }
        }
    }
    return true;
}

static bool attributable_lineage_valid(
    const egolink_location_engine_lineage_t *lineage,
    uint64_t event_time_ms)
{
    return trusted_evidence_valid(lineage, event_time_ms) ||
           rule_derived_lineage_valid(lineage);
}

static bool coarse_source_valid(egolink_location_engine_source_t source)
{
    return source == EGOLINK_LOCATION_ENGINE_SOURCE_CELL_REFERENCE ||
           source == EGOLINK_LOCATION_ENGINE_SOURCE_WIFI_REFERENCE ||
           source == EGOLINK_LOCATION_ENGINE_SOURCE_KNOWN_PLACE;
}

static bool add_measurement_error_reasons(
    egolink_location_engine_reasons_t *reasons,
    const char *detail)
{
    return reasons_add(reasons, "gnss_fix_rejected_invalid_measurement") &&
           reasons_add(reasons, detail);
}

static void reject_fix(egolink_location_engine_core_t *core)
{
    core->force_predicted = core->last_trusted_location_present;
}

static void store_trusted_location(
    egolink_location_engine_core_t *core,
    double latitude,
    double longitude,
    bool accuracy_present,
    double accuracy,
    double uncertainty,
    egolink_location_engine_uncertainty_basis_t uncertainty_basis,
    egolink_location_engine_source_t source,
    egolink_location_engine_belief_t belief,
    uint64_t event_time_ms,
    const egolink_location_engine_evidence_ref_t *evidence)
{
    egolink_location_engine_trusted_location_t *point =
        &core->last_trusted_location;
    memset(point, 0, sizeof(*point));
    point->latitude_deg = latitude;
    point->longitude_deg = longitude;
    point->accuracy_m_present = accuracy_present;
    point->accuracy_m = accuracy;
    point->uncertainty_at_fix_m = uncertainty;
    point->uncertainty_basis = uncertainty_basis;
    point->source = source;
    point->evidence_ref = *evidence;
    core->last_trusted_location_present = true;
    core->last_trusted_time_present = true;
    core->last_trusted_time_ms = event_time_ms;
    core->last_trusted_belief = belief;
    core->force_predicted = false;
}

static egolink_location_engine_result_t apply_gnss_fix(
    egolink_location_engine_core_t *core,
    const egolink_location_engine_observation_t *observation)
{
    core->gnss_state = EGOLINK_LOCATION_ENGINE_GNSS_FIX_REJECTED;
    egolink_location_engine_evidence_ref_t evidence = {0};
    if (!trusted_evidence_ref(&observation->lineage,
                              observation->event_time_ms, &evidence)) {
        reject_fix(core);
        return reasons_add(&core->last_reason_codes,
                           "gnss_fix_rejected_untrusted_lineage")
                   ? EGOLINK_LOCATION_ENGINE_OK
                   : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    if (!observation->latitude_deg_present) {
        reject_fix(core);
        return add_measurement_error_reasons(
                   &core->last_reason_codes,
                   "latitude_deg_must_be_numeric")
                   ? EGOLINK_LOCATION_ENGINE_OK
                   : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    if (!isfinite(observation->latitude_deg)) {
        reject_fix(core);
        return add_measurement_error_reasons(
                   &core->last_reason_codes,
                   "latitude_deg_must_be_finite")
                   ? EGOLINK_LOCATION_ENGINE_OK
                   : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    if (!observation->longitude_deg_present) {
        reject_fix(core);
        return add_measurement_error_reasons(
                   &core->last_reason_codes,
                   "longitude_deg_must_be_numeric")
                   ? EGOLINK_LOCATION_ENGINE_OK
                   : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    if (!isfinite(observation->longitude_deg)) {
        reject_fix(core);
        return add_measurement_error_reasons(
                   &core->last_reason_codes,
                   "longitude_deg_must_be_finite")
                   ? EGOLINK_LOCATION_ENGINE_OK
                   : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    if (observation->accuracy_m_present &&
        !isfinite(observation->accuracy_m)) {
        reject_fix(core);
        return add_measurement_error_reasons(
                   &core->last_reason_codes,
                   "accuracy_m_must_be_finite")
                   ? EGOLINK_LOCATION_ENGINE_OK
                   : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    if (observation->hdop_present && !isfinite(observation->hdop)) {
        reject_fix(core);
        return add_measurement_error_reasons(
                   &core->last_reason_codes, "hdop_must_be_finite")
                   ? EGOLINK_LOCATION_ENGINE_OK
                   : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    if (observation->latitude_deg < -90.0 ||
        observation->latitude_deg > 90.0 ||
        observation->longitude_deg < -180.0 ||
        observation->longitude_deg > 180.0) {
        reject_fix(core);
        return reasons_add(&core->last_reason_codes,
                           "gnss_fix_rejected_coordinate_range")
                   ? EGOLINK_LOCATION_ENGINE_OK
                   : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }

    bool measurement_accuracy_present = false;
    double measurement_accuracy = 0.0;
    double initial_uncertainty = 0.0;
    egolink_location_engine_uncertainty_basis_t basis;
    if (observation->accuracy_m_present) {
        if (observation->accuracy_m <= 0.0 ||
            observation->accuracy_m > core->config.fine_max_accuracy_m) {
            reject_fix(core);
            return reasons_add(&core->last_reason_codes,
                               "gnss_fix_rejected_reported_accuracy")
                       ? EGOLINK_LOCATION_ENGINE_OK
                       : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        measurement_accuracy_present = true;
        measurement_accuracy = observation->accuracy_m;
        initial_uncertainty = observation->accuracy_m;
        basis =
            EGOLINK_LOCATION_ENGINE_UNCERTAINTY_SOURCE_REPORTED_ACCURACY;
    } else if (observation->hdop_present && observation->hdop > 0.0 &&
               observation->hdop <= core->config.fine_max_hdop) {
        initial_uncertainty =
            observation->hdop * core->config.hdop_uncertainty_multiplier_m;
        if (!isfinite(initial_uncertainty) || initial_uncertainty <= 0.0) {
            reject_fix(core);
            return reasons_add(&core->last_reason_codes,
                               "gnss_fix_rejected_hdop_uncertainty")
                       ? EGOLINK_LOCATION_ENGINE_OK
                       : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        basis = EGOLINK_LOCATION_ENGINE_UNCERTAINTY_HDOP_RULE_HEURISTIC_V0;
    } else {
        reject_fix(core);
        return reasons_add(&core->last_reason_codes,
                           "gnss_fix_rejected_quality_gate")
                   ? EGOLINK_LOCATION_ENGINE_OK
                   : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }

    core->gnss_state = EGOLINK_LOCATION_ENGINE_GNSS_FIX;
    store_trusted_location(
        core, observation->latitude_deg, observation->longitude_deg,
        measurement_accuracy_present, measurement_accuracy, initial_uncertainty,
        basis, EGOLINK_LOCATION_ENGINE_SOURCE_GNSS,
        EGOLINK_LOCATION_ENGINE_BELIEF_FINE, observation->event_time_ms,
        &evidence);
    return reasons_add(&core->last_reason_codes, "gnss_fix_accepted")
               ? EGOLINK_LOCATION_ENGINE_OK
               : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
}

static egolink_location_engine_result_t apply_coarse_location(
    egolink_location_engine_core_t *core,
    const egolink_location_engine_observation_t *observation)
{
    egolink_location_engine_evidence_ref_t evidence = {0};
    if (!trusted_evidence_ref(&observation->lineage,
                              observation->event_time_ms, &evidence)) {
        return EGOLINK_LOCATION_ENGINE_INVALID_LINEAGE;
    }
    if (!observation->reference_id_present ||
        !valid_text(observation->reference_id,
                    EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES) ||
        !observation->coarse_source_present ||
        !coarse_source_valid(observation->coarse_source) ||
        !observation->latitude_deg_present ||
        !observation->longitude_deg_present ||
        !isfinite(observation->latitude_deg) ||
        !isfinite(observation->longitude_deg) ||
        (observation->accuracy_m_present &&
         !isfinite(observation->accuracy_m)) ||
        (observation->uncertainty_m_present &&
         !isfinite(observation->uncertainty_m))) {
        return EGOLINK_LOCATION_ENGINE_INVALID_MEASUREMENT;
    }
    if (observation->latitude_deg < -90.0 ||
        observation->latitude_deg > 90.0 ||
        observation->longitude_deg < -180.0 ||
        observation->longitude_deg > 180.0) {
        return EGOLINK_LOCATION_ENGINE_INVALID_MEASUREMENT;
    }
    bool initial_present = false;
    double initial_uncertainty = 0.0;
    if (observation->uncertainty_m_present) {
        initial_present = true;
        initial_uncertainty = observation->uncertainty_m;
    }
    if (observation->accuracy_m_present &&
        (!initial_present || observation->accuracy_m > initial_uncertainty)) {
        initial_present = true;
        initial_uncertainty = observation->accuracy_m;
    }
    if (!initial_present || initial_uncertainty <= 0.0 ||
        initial_uncertainty > core->config.coarse_max_uncertainty_m ||
        (observation->accuracy_m_present && observation->accuracy_m <= 0.0)) {
        return EGOLINK_LOCATION_ENGINE_INVALID_MEASUREMENT;
    }
    if (!copy_text(&evidence.reference_id, observation->reference_id)) {
        return EGOLINK_LOCATION_ENGINE_INVALID_MEASUREMENT;
    }
    evidence.reference_id_present = true;
    store_trusted_location(
        core, observation->latitude_deg, observation->longitude_deg,
        observation->accuracy_m_present, observation->accuracy_m,
        initial_uncertainty,
        observation->uncertainty_m_present
            ? EGOLINK_LOCATION_ENGINE_UNCERTAINTY_REFERENCE_BOUND
            : EGOLINK_LOCATION_ENGINE_UNCERTAINTY_SOURCE_REPORTED_ACCURACY,
        observation->coarse_source, EGOLINK_LOCATION_ENGINE_BELIEF_COARSE,
        observation->event_time_ms, &evidence);
    return reasons_add(&core->last_reason_codes,
                       "coarse_reference_accepted")
               ? EGOLINK_LOCATION_ENGINE_OK
               : EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
}

static double round_half_even(double value, double scale)
{
    const double scaled = value * scale;
    const double lower = floor(scaled);
    const double fraction = scaled - lower;
    double rounded = lower;
    if (fraction > 0.5 ||
        (fraction == 0.5 && fmod(lower, 2.0) != 0.0)) {
        rounded = lower + 1.0;
    }
    return rounded / scale;
}

static bool set_unknown_belief(
    egolink_location_engine_snapshot_t *snapshot,
    const char *first_reason,
    const char *second_reason)
{
    snapshot->location_belief = EGOLINK_LOCATION_ENGINE_BELIEF_UNKNOWN;
    snapshot->location_accuracy_m_present = false;
    snapshot->location_accuracy_source_reported = false;
    snapshot->location_confidence = 0.0;
    snapshot->location_source = EGOLINK_LOCATION_ENGINE_SOURCE_NONE;
    snapshot->location_uncertainty_m_present = false;
    snapshot->location_uncertainty_basis =
        EGOLINK_LOCATION_ENGINE_UNCERTAINTY_UNAVAILABLE;
    return reasons_add(&snapshot->reason_codes, first_reason) &&
           (second_reason == NULL ||
            reasons_add(&snapshot->reason_codes, second_reason));
}

static egolink_location_engine_result_t build_snapshot(
    const egolink_location_engine_core_t *core,
    uint64_t event_time_ms,
    egolink_location_engine_snapshot_t *output)
{
    if (core->last_event_time_present &&
        event_time_ms < core->last_event_time_ms) {
        return EGOLINK_LOCATION_ENGINE_TIME_REGRESSION;
    }
    egolink_location_engine_snapshot_t staged = {0};
    staged.event_time_ms = event_time_ms;
    staged.last_event_initialized = core->last_event_initialized;
    staged.last_event_type = core->last_event_type;
    staged.mobility_state = core->mobility_state;
    staged.gnss_state = core->gnss_state;
    staged.lte_state = core->lte_state;
    staged.last_trusted_location_present =
        core->last_trusted_location_present;
    staged.last_trusted_location = core->last_trusted_location;
    staged.last_trusted_time_present = core->last_trusted_time_present;
    staged.last_trusted_time_ms = core->last_trusted_time_ms;
    staged.battery_state = core->battery_state;
    staged.battery_percent_present = core->battery_percent_present;
    staged.battery_percent = core->battery_percent;
    staged.sensor_policy_state = core->sensor_policy_state;
    staged.sos_active = core->sos_active;
    if (!reasons_copy(&staged.reason_codes, &core->last_reason_codes)) {
        return EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }

    if (!core->last_trusted_location_present ||
        !core->last_trusted_time_present) {
        if (!set_unknown_belief(&staged, "no_trusted_location", NULL)) {
            return EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        *output = staged;
        return EGOLINK_LOCATION_ENGINE_OK;
    }
    if (event_time_ms < core->last_trusted_time_ms) {
        return EGOLINK_LOCATION_ENGINE_TIME_REGRESSION;
    }
    const uint64_t age_ms = event_time_ms - core->last_trusted_time_ms;
    const bool fine =
        core->last_trusted_belief == EGOLINK_LOCATION_ENGINE_BELIEF_FINE;
    const uint64_t freshness_ms = fine ? core->config.fine_freshness_ms
                                       : core->config.coarse_freshness_ms;
    const double initial_confidence =
        fine ? core->config.fine_initial_confidence
             : core->config.coarse_initial_confidence;
    const egolink_location_engine_trusted_location_t *point =
        &core->last_trusted_location;

    if (age_ms <= freshness_ms && !core->force_predicted) {
        staged.location_belief = core->last_trusted_belief;
        staged.location_accuracy_m_present = point->accuracy_m_present;
        staged.location_accuracy_source_reported = point->accuracy_m_present;
        staged.location_accuracy_m = point->accuracy_m;
        staged.location_confidence =
            round_half_even(initial_confidence, 1000000.0);
        staged.location_source = point->source;
        staged.location_uncertainty_m_present = true;
        staged.location_uncertainty_m = point->uncertainty_at_fix_m;
        staged.location_uncertainty_basis = point->uncertainty_basis;
        if (!reasons_add(&staged.reason_codes, "trusted_location_fresh")) {
            return EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        *output = staged;
        return EGOLINK_LOCATION_ENGINE_OK;
    }

    if (age_ms <= core->config.prediction_horizon_ms) {
        const double age_s = (double)age_ms / 1000.0;
        const double uncertainty =
            point->uncertainty_at_fix_m +
            core->config.uncertainty_growth_mps * age_s;
        if (!isfinite(uncertainty)) {
            if (!set_unknown_belief(
                    &staged, "uncertainty_growth_overflow",
                    "last_trusted_retained_as_memory_only")) {
                return EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
            }
            *output = staged;
            return EGOLINK_LOCATION_ENGINE_OK;
        }
        uint64_t denominator =
            core->config.prediction_horizon_ms - freshness_ms;
        if (denominator < UINT64_C(1)) {
            denominator = UINT64_C(1);
        }
        const uint64_t decay_age =
            age_ms > freshness_ms ? age_ms - freshness_ms : UINT64_C(0);
        double fraction = (double)decay_age / (double)denominator;
        if (fraction > 1.0) {
            fraction = 1.0;
        }
        double confidence =
            initial_confidence -
            fraction *
                (initial_confidence - core->config.predicted_min_confidence);
        if (confidence < 0.0) {
            confidence = 0.0;
        }
        staged.location_belief = EGOLINK_LOCATION_ENGINE_BELIEF_PREDICTED;
        staged.location_accuracy_m_present = false;
        staged.location_accuracy_source_reported = false;
        staged.location_confidence = round_half_even(confidence, 1000000.0);
        staged.location_source = EGOLINK_LOCATION_ENGINE_SOURCE_LAST_TRUSTED;
        staged.location_uncertainty_m_present = true;
        staged.location_uncertainty_m = round_half_even(uncertainty, 1000.0);
        staged.location_uncertainty_basis =
            EGOLINK_LOCATION_ENGINE_UNCERTAINTY_LAST_TRUSTED_AGE_GROWTH_RULE_V0;
        if (!reasons_add(&staged.reason_codes, "last_trusted_preserved") ||
            !reasons_add(&staged.reason_codes,
                         core->force_predicted ? "belief_forced_predicted"
                                               : "belief_aged")) {
            return EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        *output = staged;
        return EGOLINK_LOCATION_ENGINE_OK;
    }

    if (!set_unknown_belief(&staged, "prediction_horizon_exceeded",
                            "last_trusted_retained_as_memory_only")) {
        return EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    *output = staged;
    return EGOLINK_LOCATION_ENGINE_OK;
}

static bool lineage_required_event(
    egolink_location_engine_event_type_t type)
{
    return type == EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STARTED ||
           type == EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STOPPED ||
           type == EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX ||
           type == EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR;
}

egolink_location_engine_result_t egolink_location_engine_process(
    egolink_location_engine_core_t *core,
    const egolink_location_engine_observation_t *observation,
    egolink_location_engine_snapshot_t *output)
{
    if (output != NULL) {
        memset(output, 0, sizeof(*output));
    }
    if (core == NULL || observation == NULL || output == NULL) {
        return EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    }
    if (!core->initialized) {
        return EGOLINK_LOCATION_ENGINE_NOT_INITIALIZED;
    }
    if (!enum_in_range((int)observation->type,
                       (int)EGOLINK_LOCATION_ENGINE_EVENT_COUNT)) {
        return EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    if (core->last_event_time_present &&
        observation->event_time_ms < core->last_event_time_ms) {
        return EGOLINK_LOCATION_ENGINE_TIME_REGRESSION;
    }
    if (lineage_required_event(observation->type) &&
        !attributable_lineage_valid(&observation->lineage,
                                    observation->event_time_ms)) {
        return EGOLINK_LOCATION_ENGINE_INVALID_LINEAGE;
    }

    egolink_location_engine_core_t candidate = *core;
    candidate.last_event_time_present = true;
    candidate.last_event_time_ms = observation->event_time_ms;
    candidate.last_event_initialized = true;
    candidate.last_event_type = observation->type;
    reasons_clear(&candidate.last_reason_codes);
    egolink_location_engine_result_t result = EGOLINK_LOCATION_ENGINE_OK;

    switch (observation->type) {
    case EGOLINK_LOCATION_ENGINE_EVENT_TICK:
        if (!reasons_add(&candidate.last_reason_codes,
                         "policy_clock_advanced")) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE:
        if (!reasons_add(&candidate.last_reason_codes,
                         "imu_observed_without_coordinate_derivation")) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_MOBILITY: {
        if (!trusted_evidence_valid(&observation->lineage,
                                    observation->event_time_ms) &&
            !rule_derived_lineage_valid(&observation->lineage)) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_LINEAGE;
            break;
        }
        if (!observation->mobility_state_present ||
            !enum_in_range((int)observation->mobility_state,
                           (int)EGOLINK_LOCATION_ENGINE_MOBILITY_COUNT)) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
            break;
        }
        candidate.mobility_state = observation->mobility_state;
        const char *reason =
            observation->mobility_state ==
                    EGOLINK_LOCATION_ENGINE_MOBILITY_STABLE
                ? "mobility_stable"
                : (observation->mobility_state ==
                           EGOLINK_LOCATION_ENGINE_MOBILITY_MOVING
                       ? "mobility_moving"
                       : "mobility_unknown");
        if (!reasons_add(&candidate.last_reason_codes, reason)) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    }
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STARTED:
        candidate.gnss_state = EGOLINK_LOCATION_ENGINE_GNSS_ACQUIRING;
        candidate.force_predicted = candidate.last_trusted_location_present;
        if (!reasons_add(&candidate.last_reason_codes,
                         "gnss_acquisition_started")) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STOPPED:
        candidate.gnss_state = EGOLINK_LOCATION_ENGINE_GNSS_IDLE;
        if (!reasons_add(&candidate.last_reason_codes,
                         "gnss_acquisition_stopped")) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX:
        candidate.gnss_state = EGOLINK_LOCATION_ENGINE_GNSS_NO_FIX;
        candidate.force_predicted = candidate.last_trusted_location_present;
        if (!reasons_add(&candidate.last_reason_codes,
                         "gnss_no_fix_preserved_last_trusted")) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR:
        candidate.gnss_state = EGOLINK_LOCATION_ENGINE_GNSS_ERROR;
        candidate.force_predicted = candidate.last_trusted_location_present;
        if (!reasons_add(&candidate.last_reason_codes,
                         "gnss_error_preserved_last_trusted")) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_GNSS_FIX:
        result = apply_gnss_fix(&candidate, observation);
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_COARSE_LOCATION:
        result = apply_coarse_location(&candidate, observation);
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_LTE_STATE:
        if (!observation->lte_state_present ||
            !enum_in_range((int)observation->lte_state,
                           (int)EGOLINK_LOCATION_ENGINE_LTE_COUNT)) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
            break;
        }
        candidate.lte_state = observation->lte_state;
        if (!reasons_add(
                &candidate.last_reason_codes,
                LTE_REASON_NAMES[observation->lte_state])) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_CELL_OBSERVATION:
        candidate.lte_state = EGOLINK_LOCATION_ENGINE_LTE_ONLINE;
        if (!reasons_add(&candidate.last_reason_codes,
                         "cell_observed_without_coordinate_derivation")) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_BATTERY:
        if (!observation->battery_state_present ||
            !enum_in_range((int)observation->battery_state,
                           (int)EGOLINK_LOCATION_ENGINE_BATTERY_COUNT) ||
            (observation->battery_percent_present &&
             (!isfinite(observation->battery_percent) ||
              observation->battery_percent < 0.0 ||
              observation->battery_percent > 100.0))) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_MEASUREMENT;
            break;
        }
        candidate.battery_state = observation->battery_state;
        candidate.battery_percent_present =
            observation->battery_percent_present;
        candidate.battery_percent = observation->battery_percent;
        if (!reasons_add(
                &candidate.last_reason_codes,
                BATTERY_REASON_NAMES[observation->battery_state])) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_SOS:
        if (!observation->sos_active_present) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
            break;
        }
        candidate.sos_active = observation->sos_active;
        if (!reasons_add(&candidate.last_reason_codes,
                         observation->sos_active ? "sos_active"
                                                 : "sos_cleared")) {
            result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        }
        break;
    case EGOLINK_LOCATION_ENGINE_EVENT_COUNT:
    default:
        result = EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
        break;
    }
    if (result != EGOLINK_LOCATION_ENGINE_OK) {
        return result;
    }
    if (candidate.last_reason_codes.count == 0U &&
        !reasons_add(&candidate.last_reason_codes, "observation_applied")) {
        return EGOLINK_LOCATION_ENGINE_INVALID_EVENT;
    }
    result = build_snapshot(&candidate, observation->event_time_ms, output);
    if (result != EGOLINK_LOCATION_ENGINE_OK) {
        memset(output, 0, sizeof(*output));
        return result;
    }
    *core = candidate;
    return EGOLINK_LOCATION_ENGINE_OK;
}

egolink_location_engine_result_t egolink_location_engine_snapshot(
    const egolink_location_engine_core_t *core,
    bool event_time_ms_present,
    uint64_t event_time_ms,
    egolink_location_engine_snapshot_t *output)
{
    if (output != NULL) {
        memset(output, 0, sizeof(*output));
    }
    if (core == NULL || output == NULL) {
        return EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    }
    if (!core->initialized) {
        return EGOLINK_LOCATION_ENGINE_NOT_INITIALIZED;
    }
    const uint64_t selected_time =
        event_time_ms_present
            ? event_time_ms
            : (core->last_event_time_present ? core->last_event_time_ms
                                             : UINT64_C(0));
    return build_snapshot(core, selected_time, output);
}

static bool evidence_ref_valid(
    const egolink_location_engine_evidence_ref_t *evidence)
{
    if (evidence == NULL ||
        !owned_text_valid(&evidence->observation_id,
                          EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES) ||
        !trusted_source_status(evidence->source_status) ||
        (evidence->stream_id_present &&
         !owned_text_valid(&evidence->stream_id,
                           EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES)) ||
        (evidence->device_run_id_present &&
         !owned_text_valid(&evidence->device_run_id,
                           EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES)) ||
        !enum_in_range((int)evidence->event_time_source,
                       (int)EGOLINK_LOCATION_ENGINE_TIME_COUNT) ||
        evidence->event_time_source >
            EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_MONOTONIC_NS ||
        evidence->capture_time_ns / UINT64_C(1000000) !=
            evidence->event_time_ms ||
        (evidence->reference_id_present &&
         !owned_text_valid(&evidence->reference_id,
                           EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES))) {
        return false;
    }
    if (evidence->event_time_source ==
        EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_MONOTONIC_NS) {
        return evidence->boot_count_present &&
               evidence->monotonic_clock_domain_id_present &&
               owned_text_valid(
                   &evidence->monotonic_clock_domain_id,
                   EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES);
    }
    return !evidence->monotonic_clock_domain_id_present;
}

static bool reasons_valid(const egolink_location_engine_reasons_t *reasons)
{
    if (reasons == NULL || reasons->count == 0U ||
        reasons->count > EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_COUNT) {
        return false;
    }
    for (size_t index = 0U; index < reasons->count; ++index) {
        if (!enum_in_range((int)reasons->values[index],
                           (int)EGOLINK_LOCATION_ENGINE_REASON_COUNT)) {
            return false;
        }
        for (size_t prior = 0U; prior < index; ++prior) {
            if (reasons->values[index] == reasons->values[prior]) {
                return false;
            }
        }
    }
    return true;
}

static bool snapshot_valid(
    const egolink_location_engine_snapshot_t *snapshot)
{
    if (snapshot == NULL ||
        (snapshot->last_event_initialized &&
         !enum_in_range((int)snapshot->last_event_type,
                        (int)EGOLINK_LOCATION_ENGINE_EVENT_COUNT)) ||
        !enum_in_range((int)snapshot->mobility_state,
                       (int)EGOLINK_LOCATION_ENGINE_MOBILITY_COUNT) ||
        !enum_in_range((int)snapshot->gnss_state,
                       (int)EGOLINK_LOCATION_ENGINE_GNSS_COUNT) ||
        !enum_in_range((int)snapshot->lte_state,
                       (int)EGOLINK_LOCATION_ENGINE_LTE_COUNT) ||
        !enum_in_range((int)snapshot->location_belief,
                       (int)EGOLINK_LOCATION_ENGINE_BELIEF_COUNT) ||
        !enum_in_range((int)snapshot->location_source,
                       (int)EGOLINK_LOCATION_ENGINE_SOURCE_COUNT) ||
        !enum_in_range((int)snapshot->location_uncertainty_basis,
                       (int)EGOLINK_LOCATION_ENGINE_UNCERTAINTY_COUNT) ||
        !enum_in_range((int)snapshot->battery_state,
                       (int)EGOLINK_LOCATION_ENGINE_BATTERY_COUNT) ||
        !enum_in_range((int)snapshot->sensor_policy_state,
                       (int)EGOLINK_LOCATION_ENGINE_POLICY_COUNT) ||
        snapshot->last_trusted_location_present !=
            snapshot->last_trusted_time_present ||
        snapshot->location_accuracy_m_present !=
            snapshot->location_accuracy_source_reported ||
        !isfinite(snapshot->location_confidence) ||
        snapshot->location_confidence < 0.0 ||
        snapshot->location_confidence > 1.0 ||
        (snapshot->battery_percent_present &&
         (!isfinite(snapshot->battery_percent) ||
          snapshot->battery_percent < 0.0 ||
          snapshot->battery_percent > 100.0)) ||
        !reasons_valid(&snapshot->reason_codes)) {
        return false;
    }
    if (snapshot->last_trusted_location_present) {
        const egolink_location_engine_trusted_location_t *point =
            &snapshot->last_trusted_location;
        if (!isfinite(point->latitude_deg) || point->latitude_deg < -90.0 ||
            point->latitude_deg > 90.0 || !isfinite(point->longitude_deg) ||
            point->longitude_deg < -180.0 || point->longitude_deg > 180.0 ||
            (point->accuracy_m_present &&
             (!isfinite(point->accuracy_m) || point->accuracy_m <= 0.0)) ||
            !isfinite(point->uncertainty_at_fix_m) ||
            point->uncertainty_at_fix_m <= 0.0 ||
            !enum_in_range((int)point->source,
                           (int)EGOLINK_LOCATION_ENGINE_SOURCE_COUNT) ||
            point->source > EGOLINK_LOCATION_ENGINE_SOURCE_KNOWN_PLACE ||
            !enum_in_range(
                (int)point->uncertainty_basis,
                (int)EGOLINK_LOCATION_ENGINE_UNCERTAINTY_COUNT) ||
            point->uncertainty_basis >
                EGOLINK_LOCATION_ENGINE_UNCERTAINTY_REFERENCE_BOUND ||
            !evidence_ref_valid(&point->evidence_ref) ||
            point->evidence_ref.event_time_ms !=
                snapshot->last_trusted_time_ms ||
            snapshot->last_trusted_time_ms > snapshot->event_time_ms ||
            (point->uncertainty_basis ==
                 EGOLINK_LOCATION_ENGINE_UNCERTAINTY_SOURCE_REPORTED_ACCURACY &&
             !point->accuracy_m_present) ||
            (point->uncertainty_basis ==
                 EGOLINK_LOCATION_ENGINE_UNCERTAINTY_HDOP_RULE_HEURISTIC_V0 &&
             point->accuracy_m_present) ||
            (point->source == EGOLINK_LOCATION_ENGINE_SOURCE_GNSS &&
             (point->evidence_ref.reference_id_present ||
              point->uncertainty_basis ==
                  EGOLINK_LOCATION_ENGINE_UNCERTAINTY_REFERENCE_BOUND)) ||
            (coarse_source_valid(point->source) &&
             (!point->evidence_ref.reference_id_present ||
              point->uncertainty_basis ==
                  EGOLINK_LOCATION_ENGINE_UNCERTAINTY_HDOP_RULE_HEURISTIC_V0))) {
            return false;
        }
    }
    if (snapshot->location_accuracy_m_present &&
        (!isfinite(snapshot->location_accuracy_m) ||
         snapshot->location_accuracy_m <= 0.0)) {
        return false;
    }
    if (snapshot->location_uncertainty_m_present &&
        (!isfinite(snapshot->location_uncertainty_m) ||
         snapshot->location_uncertainty_m <= 0.0)) {
        return false;
    }
    switch (snapshot->location_belief) {
    case EGOLINK_LOCATION_ENGINE_BELIEF_UNKNOWN:
        return !snapshot->location_accuracy_m_present &&
               snapshot->location_confidence == 0.0 &&
               snapshot->location_source == EGOLINK_LOCATION_ENGINE_SOURCE_NONE &&
               !snapshot->location_uncertainty_m_present &&
               snapshot->location_uncertainty_basis ==
                   EGOLINK_LOCATION_ENGINE_UNCERTAINTY_UNAVAILABLE;
    case EGOLINK_LOCATION_ENGINE_BELIEF_PREDICTED:
        return snapshot->last_trusted_location_present &&
               !snapshot->location_accuracy_m_present &&
               snapshot->location_source ==
                   EGOLINK_LOCATION_ENGINE_SOURCE_LAST_TRUSTED &&
               snapshot->location_uncertainty_m_present &&
               snapshot->location_uncertainty_basis ==
                   EGOLINK_LOCATION_ENGINE_UNCERTAINTY_LAST_TRUSTED_AGE_GROWTH_RULE_V0;
    case EGOLINK_LOCATION_ENGINE_BELIEF_FINE:
        return snapshot->last_trusted_location_present &&
               snapshot->location_source == EGOLINK_LOCATION_ENGINE_SOURCE_GNSS &&
               snapshot->last_trusted_location.source ==
                   EGOLINK_LOCATION_ENGINE_SOURCE_GNSS &&
               snapshot->location_uncertainty_m_present &&
               snapshot->location_uncertainty_basis ==
                   snapshot->last_trusted_location.uncertainty_basis &&
               snapshot->location_uncertainty_m ==
                   snapshot->last_trusted_location.uncertainty_at_fix_m &&
               snapshot->location_accuracy_m_present ==
                   snapshot->last_trusted_location.accuracy_m_present &&
               (!snapshot->location_accuracy_m_present ||
                snapshot->location_accuracy_m ==
                    snapshot->last_trusted_location.accuracy_m);
    case EGOLINK_LOCATION_ENGINE_BELIEF_COARSE:
        return snapshot->last_trusted_location_present &&
               coarse_source_valid(snapshot->location_source) &&
               snapshot->last_trusted_location.source ==
                   snapshot->location_source &&
               snapshot->location_uncertainty_m_present &&
               snapshot->location_uncertainty_basis ==
                   snapshot->last_trusted_location.uncertainty_basis &&
               snapshot->location_uncertainty_m ==
                   snapshot->last_trusted_location.uncertainty_at_fix_m &&
               snapshot->location_accuracy_m_present ==
                   snapshot->last_trusted_location.accuracy_m_present &&
               (!snapshot->location_accuracy_m_present ||
                snapshot->location_accuracy_m ==
                    snapshot->last_trusted_location.accuracy_m);
    case EGOLINK_LOCATION_ENGINE_BELIEF_COUNT:
    default:
        return false;
    }
}

static size_t bounded_output_capacity(size_t capacity)
{
    const size_t maximum = EGOLINK_LOCATION_ENGINE_CORE_JSON_MAX_BYTES + 1U;
    return capacity < maximum ? capacity : maximum;
}

static void clear_output(char *output, size_t capacity)
{
    volatile unsigned char *cursor = (volatile unsigned char *)output;
    const size_t clear_length = bounded_output_capacity(capacity);
    for (size_t index = 0U; cursor != NULL && index < clear_length; ++index) {
        cursor[index] = 0U;
    }
}

static bool writer_append(json_writer_t *writer, const char *value, size_t length)
{
    if (writer->overflow || length > writer->capacity - writer->length) {
        writer->overflow = true;
        return false;
    }
    if (length > 0U) {
        memcpy(writer->data + writer->length, value, length);
        writer->length += length;
    }
    return true;
}

static bool writer_literal(json_writer_t *writer, const char *value)
{
    return writer_append(writer, value, strlen(value));
}

static bool writer_u64(json_writer_t *writer, uint64_t value)
{
    char digits[20];
    size_t count = 0U;
    do {
        digits[count++] = (char)('0' + (value % UINT64_C(10)));
        value /= UINT64_C(10);
    } while (value != UINT64_C(0));
    while (count > 0U) {
        --count;
        if (!writer_append(writer, &digits[count], 1U)) {
            return false;
        }
    }
    return true;
}

static bool writer_double(json_writer_t *writer, double value)
{
    char number[32];
    if (!isfinite(value)) {
        return false;
    }
    const int count = snprintf(number, sizeof(number), "%.17g", value);
    return count > 0 && (size_t)count < sizeof(number) &&
           writer_append(writer, number, (size_t)count);
}

static bool writer_json_bytes(
    json_writer_t *writer, const char *data, size_t length)
{
    static const char hex[] = "0123456789abcdef";
    if (!writer_literal(writer, "\"")) {
        return false;
    }
    for (size_t index = 0U; index < length; ++index) {
        const unsigned char byte = (unsigned char)data[index];
        if (byte == '"' || byte == '\\') {
            const char escaped[2] = {'\\', (char)byte};
            if (!writer_append(writer, escaped, sizeof(escaped))) {
                return false;
            }
        } else if (byte < 0x20U) {
            const char escaped[6] = {
                '\\', 'u', '0', '0', hex[byte >> 4U], hex[byte & 0x0fU]};
            if (!writer_append(writer, escaped, sizeof(escaped))) {
                return false;
            }
        } else if (!writer_append(writer, data + index, 1U)) {
            return false;
        }
    }
    return writer_literal(writer, "\"");
}

static bool writer_owned_text(
    json_writer_t *writer, const egolink_location_engine_owned_text_t *text)
{
    return writer_json_bytes(writer, text->data, text->length);
}

static bool writer_nullable_double(
    json_writer_t *writer, bool present, double value)
{
    return present ? writer_double(writer, value)
                   : writer_literal(writer, "null");
}

static bool writer_nullable_u64(
    json_writer_t *writer, bool present, uint64_t value)
{
    return present ? writer_u64(writer, value)
                   : writer_literal(writer, "null");
}

static bool write_evidence_ref(
    json_writer_t *writer,
    const egolink_location_engine_evidence_ref_t *evidence)
{
    return writer_literal(writer, "{\"observation_id\":") &&
           writer_owned_text(writer, &evidence->observation_id) &&
           writer_literal(writer, ",\"source_status\":\"") &&
           writer_literal(writer, SOURCE_STATUS_NAMES[evidence->source_status]) &&
           writer_literal(writer, "\",\"stream_id\":") &&
           (evidence->stream_id_present
                ? writer_owned_text(writer, &evidence->stream_id)
                : writer_literal(writer, "null")) &&
           writer_literal(writer, ",\"sequence_id\":") &&
           writer_nullable_u64(writer, evidence->sequence_id_present,
                               evidence->sequence_id) &&
           writer_literal(writer, ",\"device_run_id\":") &&
           (evidence->device_run_id_present
                ? writer_owned_text(writer, &evidence->device_run_id)
                : writer_literal(writer, "null")) &&
           writer_literal(writer, ",\"boot_count\":") &&
           writer_nullable_u64(writer, evidence->boot_count_present,
                               evidence->boot_count) &&
           writer_literal(writer, ",\"event_time_ms\":") &&
           writer_u64(writer, evidence->event_time_ms) &&
           writer_literal(writer, ",\"event_time_source\":\"") &&
           writer_literal(writer, TIME_SOURCE_NAMES[evidence->event_time_source]) &&
           writer_literal(writer, "\",\"capture_time_ns\":") &&
           writer_u64(writer, evidence->capture_time_ns) &&
           writer_literal(writer, ",\"monotonic_clock_domain_id\":") &&
           (evidence->monotonic_clock_domain_id_present
                ? writer_owned_text(writer,
                                    &evidence->monotonic_clock_domain_id)
                : writer_literal(writer, "null")) &&
           (!evidence->reference_id_present ||
            (writer_literal(writer, ",\"reference_id\":") &&
             writer_owned_text(writer, &evidence->reference_id))) &&
           writer_literal(writer, "}");
}

static bool write_trusted_location(
    json_writer_t *writer,
    const egolink_location_engine_trusted_location_t *point)
{
    return writer_literal(writer, "{\"latitude_deg\":") &&
           writer_double(writer, point->latitude_deg) &&
           writer_literal(writer, ",\"longitude_deg\":") &&
           writer_double(writer, point->longitude_deg) &&
           writer_literal(writer, ",\"accuracy_m\":") &&
           writer_nullable_double(writer, point->accuracy_m_present,
                                  point->accuracy_m) &&
           writer_literal(writer, ",\"uncertainty_at_fix_m\":") &&
           writer_double(writer, point->uncertainty_at_fix_m) &&
           writer_literal(writer, ",\"uncertainty_basis\":\"") &&
           writer_literal(writer, UNCERTAINTY_NAMES[point->uncertainty_basis]) &&
           writer_literal(writer, "\",\"source\":\"") &&
           writer_literal(writer, SOURCE_NAMES[point->source]) &&
           writer_literal(writer, "\",\"evidence_ref\":") &&
           write_evidence_ref(writer, &point->evidence_ref) &&
           writer_literal(writer, "}");
}

egolink_location_engine_result_t egolink_location_engine_serialize_snapshot(
    const egolink_location_engine_snapshot_t *snapshot,
    char *output,
    size_t output_capacity,
    size_t *output_length)
{
    if (output_length != NULL) {
        *output_length = 0U;
    }
    clear_output(output, output_capacity);
    if (snapshot == NULL || output == NULL || output_length == NULL ||
        output_capacity == 0U || !snapshot_valid(snapshot)) {
        return EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT;
    }
    json_writer_t writer = {
        .data = output,
        .capacity = bounded_output_capacity(output_capacity) - 1U,
    };
    writer_literal(&writer, "{\"contract_version\":\"");
    writer_literal(&writer, EGOLINK_LOCATION_ENGINE_CORE_CONTRACT_VERSION);
    writer_literal(&writer, "\",\"event_time_ms\":");
    writer_u64(&writer, snapshot->event_time_ms);
    writer_literal(&writer, ",\"last_event_type\":\"");
    writer_literal(&writer, snapshot->last_event_initialized
                                ? EVENT_NAMES[snapshot->last_event_type]
                                : "initialized");
    writer_literal(&writer, "\",\"mobility_state\":\"");
    writer_literal(&writer, MOBILITY_NAMES[snapshot->mobility_state]);
    writer_literal(&writer, "\",\"gnss_state\":\"");
    writer_literal(&writer, GNSS_NAMES[snapshot->gnss_state]);
    writer_literal(&writer, "\",\"lte_state\":\"");
    writer_literal(&writer, LTE_NAMES[snapshot->lte_state]);
    writer_literal(&writer, "\",\"last_trusted_location\":");
    if (snapshot->last_trusted_location_present) {
        write_trusted_location(&writer, &snapshot->last_trusted_location);
    } else {
        writer_literal(&writer, "null");
    }
    writer_literal(&writer, ",\"last_trusted_time_ms\":");
    writer_nullable_u64(&writer, snapshot->last_trusted_time_present,
                        snapshot->last_trusted_time_ms);
    writer_literal(&writer, ",\"location_belief\":\"");
    writer_literal(&writer, BELIEF_NAMES[snapshot->location_belief]);
    writer_literal(&writer, "\",\"location_accuracy_m\":");
    writer_nullable_double(&writer, snapshot->location_accuracy_m_present,
                           snapshot->location_accuracy_m);
    writer_literal(&writer, ",\"location_accuracy_status\":\"");
    writer_literal(&writer, snapshot->location_accuracy_source_reported
                                ? "source_reported"
                                : "unavailable");
    writer_literal(&writer, "\",\"location_confidence\":");
    writer_double(&writer, snapshot->location_confidence);
    writer_literal(
        &writer,
        ",\"location_confidence_basis\":\"rule_heuristic_v0\","
        "\"location_confidence_calibrated\":false,\"location_source\":\"");
    writer_literal(&writer, SOURCE_NAMES[snapshot->location_source]);
    writer_literal(&writer, "\",\"location_uncertainty_m\":");
    writer_nullable_double(&writer, snapshot->location_uncertainty_m_present,
                           snapshot->location_uncertainty_m);
    writer_literal(&writer, ",\"location_uncertainty_basis\":\"");
    writer_literal(
        &writer, UNCERTAINTY_NAMES[snapshot->location_uncertainty_basis]);
    writer_literal(&writer, "\",\"battery_state\":\"");
    writer_literal(&writer, BATTERY_NAMES[snapshot->battery_state]);
    writer_literal(&writer, "\",\"battery_percent\":");
    writer_nullable_double(&writer, snapshot->battery_percent_present,
                           snapshot->battery_percent);
    writer_literal(&writer, ",\"sensor_policy_state\":\"");
    writer_literal(&writer, POLICY_NAMES[snapshot->sensor_policy_state]);
    writer_literal(&writer, "\",\"sos_active\":");
    writer_literal(&writer, snapshot->sos_active ? "true" : "false");
    writer_literal(&writer, ",\"reason_codes\":[");
    for (size_t index = 0U; index < snapshot->reason_codes.count; ++index) {
        if (index > 0U) {
            writer_literal(&writer, ",");
        }
        writer_json_bytes(
            &writer, REASON_NAMES[snapshot->reason_codes.values[index]],
            strlen(REASON_NAMES[snapshot->reason_codes.values[index]]));
    }
    writer_literal(&writer, "]}");

    if (writer.overflow ||
        writer.length > EGOLINK_LOCATION_ENGINE_CORE_JSON_MAX_BYTES ||
        writer.length >= output_capacity) {
        clear_output(output, output_capacity);
        return EGOLINK_LOCATION_ENGINE_OUTPUT_OVERFLOW;
    }
    output[writer.length] = '\0';
    *output_length = writer.length;
    return EGOLINK_LOCATION_ENGINE_OK;
}

const char *egolink_location_engine_result_name(
    egolink_location_engine_result_t result)
{
    switch (result) {
    case EGOLINK_LOCATION_ENGINE_OK:
        return "ok";
    case EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_LOCATION_ENGINE_INVALID_CONFIG:
        return "invalid_config";
    case EGOLINK_LOCATION_ENGINE_NOT_INITIALIZED:
        return "not_initialized";
    case EGOLINK_LOCATION_ENGINE_INVALID_EVENT:
        return "invalid_event";
    case EGOLINK_LOCATION_ENGINE_INVALID_LINEAGE:
        return "invalid_lineage";
    case EGOLINK_LOCATION_ENGINE_INVALID_MEASUREMENT:
        return "invalid_measurement";
    case EGOLINK_LOCATION_ENGINE_TIME_REGRESSION:
        return "time_regression";
    case EGOLINK_LOCATION_ENGINE_NUMERIC_OVERFLOW:
        return "numeric_overflow";
    case EGOLINK_LOCATION_ENGINE_OUTPUT_OVERFLOW:
        return "output_overflow";
    default:
        return "unknown";
    }
}

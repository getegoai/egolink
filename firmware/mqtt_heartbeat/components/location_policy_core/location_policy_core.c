#include "location_policy_core.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

typedef struct {
    uint64_t gnss_interval_ms;
    uint64_t gnss_acquisition_timeout_ms;
    uint64_t cell_interval_ms;
    double imu_rate_hz;
    bool lte_keep_connected;
} effective_schedule_t;

static const egolink_location_policy_config_t accepted_default_config = {
    .contract_version = EGOLINK_LOCATION_POLICY_CONFIG_CONTRACT_VERSION,
    .semantic_validation = EGOLINK_LOCATION_POLICY_SEMANTIC_VERSION,
    .config_id = EGOLINK_LOCATION_POLICY_CONFIG_ID,
    .config_hash = EGOLINK_LOCATION_POLICY_CONFIG_HASH,
    .provenance = EGOLINK_LOCATION_POLICY_PROVENANCE,
    .stationary = {
        .gnss_interval_ms = 600000U,
        .cell_interval_ms = 300000U,
        .imu_rate_hz = 1.0,
        .lte_keep_connected = false,
    },
    .moving = {
        .gnss_interval_ms = 120000U,
        .cell_interval_ms = 60000U,
        .imu_rate_hz = 10.0,
        .lte_keep_connected = true,
    },
    .location_uncertain = {
        .gnss_interval_ms = 60000U,
        .cell_interval_ms = 30000U,
        .imu_rate_hz = 10.0,
        .lte_keep_connected = true,
    },
    .gnss = {
        .acquisition_timeout_ms = 45000U,
        .retry_backoff_ms = 60000U,
        .retry_backoff_multiplier = 2.0,
        .max_retry_backoff_ms = 900000U,
    },
    .cell = {
        .request_timeout_ms = 10000U,
        .retry_backoff_ms = 20000U,
        .retry_backoff_multiplier = 2.0,
        .max_retry_backoff_ms = 300000U,
    },
    .movement = {
        .window_ms = 2000U,
        .min_samples = 20U,
        .enter_rms_m_s2 = 0.8,
        .exit_rms_m_s2 = 0.3,
        .enter_windows = 2U,
        .exit_windows = 2U,
        .evidence_stale_after_ms = 10000U,
    },
    .location = {
        .fine_max_accuracy_m = 100.0,
        .fine_max_hdop = 5.0,
        .hdop_uncertainty_multiplier_m = 5.0,
        .coarse_max_uncertainty_m = 5000.0,
        .fine_freshness_ms = 30000U,
        .coarse_freshness_ms = 120000U,
        .prediction_horizon_ms = 900000U,
        .uncertainty_growth_mps = 1.5,
        .uncertain_threshold_m = 250.0,
        .fine_initial_confidence = 0.95,
        .coarse_initial_confidence = 0.65,
        .predicted_min_confidence = 0.1,
    },
    .low_battery = {
        .enter_percent = 20.0,
        .exit_percent = 25.0,
        .critical_percent = 10.0,
        .schedule = {
            .gnss_interval_ms = 900000U,
            .cell_interval_ms = 600000U,
            .imu_rate_hz = 0.5,
            .lte_keep_connected = false,
        },
    },
    .sos = {
        .gnss_immediate = true,
        .gnss_retry_interval_ms = 30000U,
        .gnss_acquisition_timeout_ms = 60000U,
        .cell_interval_ms = 15000U,
        .imu_rate_hz = 20.0,
        .lte_keep_connected = true,
        .upload_last_trusted = true,
        .start_ego_call = true,
    },
};

static bool text_equals(const char *left, const char *right)
{
    return left != NULL && right != NULL && strcmp(left, right) == 0;
}

static bool finite_nonnegative(double value)
{
    return isfinite(value) && value >= 0.0;
}

static bool valid_schedule(
    const egolink_location_policy_schedule_config_t *schedule)
{
    return schedule != NULL && schedule->gnss_interval_ms > 0U &&
           schedule->cell_interval_ms > 0U &&
           finite_nonnegative(schedule->imu_rate_hz);
}

static bool equal_schedule(
    const egolink_location_policy_schedule_config_t *left,
    const egolink_location_policy_schedule_config_t *right)
{
    return left->gnss_interval_ms == right->gnss_interval_ms &&
           left->cell_interval_ms == right->cell_interval_ms &&
           left->imu_rate_hz == right->imu_rate_hz &&
           left->lte_keep_connected == right->lte_keep_connected;
}

static bool semantic_config_valid(
    const egolink_location_policy_config_t *config)
{
    if (config == NULL || !valid_schedule(&config->stationary) ||
        !valid_schedule(&config->moving) ||
        !valid_schedule(&config->location_uncertain) ||
        config->gnss.acquisition_timeout_ms == 0U ||
        config->gnss.retry_backoff_ms == 0U ||
        !isfinite(config->gnss.retry_backoff_multiplier) ||
        config->gnss.retry_backoff_multiplier < 1.0 ||
        config->gnss.max_retry_backoff_ms < config->gnss.retry_backoff_ms ||
        config->cell.request_timeout_ms == 0U ||
        config->cell.retry_backoff_ms == 0U ||
        !isfinite(config->cell.retry_backoff_multiplier) ||
        config->cell.retry_backoff_multiplier < 1.0 ||
        config->cell.max_retry_backoff_ms < config->cell.retry_backoff_ms) {
        return false;
    }

    const egolink_location_policy_movement_config_t *movement = &config->movement;
    if (movement->window_ms == 0U || movement->min_samples < 2U ||
        !isfinite(movement->enter_rms_m_s2) ||
        movement->enter_rms_m_s2 <= 0.0 ||
        !finite_nonnegative(movement->exit_rms_m_s2) ||
        movement->exit_rms_m_s2 >= movement->enter_rms_m_s2 ||
        movement->enter_windows == 0U || movement->exit_windows == 0U ||
        movement->evidence_stale_after_ms == 0U) {
        return false;
    }

    const egolink_location_policy_location_config_t *location = &config->location;
    if (!isfinite(location->fine_max_accuracy_m) ||
        location->fine_max_accuracy_m <= 0.0 ||
        !isfinite(location->fine_max_hdop) || location->fine_max_hdop <= 0.0 ||
        !isfinite(location->hdop_uncertainty_multiplier_m) ||
        location->hdop_uncertainty_multiplier_m <= 0.0 ||
        !isfinite(location->coarse_max_uncertainty_m) ||
        location->coarse_max_uncertainty_m <= 0.0 ||
        location->coarse_max_uncertainty_m < location->fine_max_accuracy_m ||
        location->fine_freshness_ms == 0U ||
        location->coarse_freshness_ms == 0U ||
        location->prediction_horizon_ms < location->fine_freshness_ms ||
        location->prediction_horizon_ms < location->coarse_freshness_ms ||
        !finite_nonnegative(location->uncertainty_growth_mps) ||
        !isfinite(location->uncertain_threshold_m) ||
        location->uncertain_threshold_m <= 0.0 ||
        !finite_nonnegative(location->fine_initial_confidence) ||
        location->fine_initial_confidence > 1.0 ||
        !finite_nonnegative(location->coarse_initial_confidence) ||
        location->coarse_initial_confidence > 1.0 ||
        !finite_nonnegative(location->predicted_min_confidence) ||
        location->predicted_min_confidence > 1.0 ||
        location->predicted_min_confidence > location->fine_initial_confidence ||
        location->predicted_min_confidence > location->coarse_initial_confidence) {
        return false;
    }

    const egolink_location_policy_low_battery_config_t *low = &config->low_battery;
    if (!finite_nonnegative(low->enter_percent) || low->enter_percent > 100.0 ||
        !finite_nonnegative(low->exit_percent) || low->exit_percent > 100.0 ||
        !finite_nonnegative(low->critical_percent) ||
        low->critical_percent > 100.0 ||
        low->critical_percent > low->enter_percent ||
        low->enter_percent >= low->exit_percent ||
        !valid_schedule(&low->schedule)) {
        return false;
    }

    const egolink_location_policy_sos_config_t *sos = &config->sos;
    return sos->gnss_retry_interval_ms > 0U &&
           sos->gnss_acquisition_timeout_ms > 0U &&
           sos->cell_interval_ms > 0U && finite_nonnegative(sos->imu_rate_hz);
}

static bool exact_accepted_config(
    const egolink_location_policy_config_t *config)
{
    const egolink_location_policy_config_t *accepted = &accepted_default_config;
    return text_equals(config->contract_version, accepted->contract_version) &&
           text_equals(config->semantic_validation,
                       accepted->semantic_validation) &&
           text_equals(config->config_id, accepted->config_id) &&
           text_equals(config->config_hash, accepted->config_hash) &&
           text_equals(config->provenance, accepted->provenance) &&
           equal_schedule(&config->stationary, &accepted->stationary) &&
           equal_schedule(&config->moving, &accepted->moving) &&
           equal_schedule(&config->location_uncertain,
                          &accepted->location_uncertain) &&
           config->gnss.acquisition_timeout_ms ==
               accepted->gnss.acquisition_timeout_ms &&
           config->gnss.retry_backoff_ms == accepted->gnss.retry_backoff_ms &&
           config->gnss.retry_backoff_multiplier ==
               accepted->gnss.retry_backoff_multiplier &&
           config->gnss.max_retry_backoff_ms ==
               accepted->gnss.max_retry_backoff_ms &&
           config->cell.request_timeout_ms == accepted->cell.request_timeout_ms &&
           config->cell.retry_backoff_ms == accepted->cell.retry_backoff_ms &&
           config->cell.retry_backoff_multiplier ==
               accepted->cell.retry_backoff_multiplier &&
           config->cell.max_retry_backoff_ms ==
               accepted->cell.max_retry_backoff_ms &&
           config->movement.window_ms == accepted->movement.window_ms &&
           config->movement.min_samples == accepted->movement.min_samples &&
           config->movement.enter_rms_m_s2 ==
               accepted->movement.enter_rms_m_s2 &&
           config->movement.exit_rms_m_s2 == accepted->movement.exit_rms_m_s2 &&
           config->movement.enter_windows == accepted->movement.enter_windows &&
           config->movement.exit_windows == accepted->movement.exit_windows &&
           config->movement.evidence_stale_after_ms ==
               accepted->movement.evidence_stale_after_ms &&
           config->location.fine_max_accuracy_m ==
               accepted->location.fine_max_accuracy_m &&
           config->location.fine_max_hdop == accepted->location.fine_max_hdop &&
           config->location.hdop_uncertainty_multiplier_m ==
               accepted->location.hdop_uncertainty_multiplier_m &&
           config->location.coarse_max_uncertainty_m ==
               accepted->location.coarse_max_uncertainty_m &&
           config->location.fine_freshness_ms ==
               accepted->location.fine_freshness_ms &&
           config->location.coarse_freshness_ms ==
               accepted->location.coarse_freshness_ms &&
           config->location.prediction_horizon_ms ==
               accepted->location.prediction_horizon_ms &&
           config->location.uncertainty_growth_mps ==
               accepted->location.uncertainty_growth_mps &&
           config->location.uncertain_threshold_m ==
               accepted->location.uncertain_threshold_m &&
           config->location.fine_initial_confidence ==
               accepted->location.fine_initial_confidence &&
           config->location.coarse_initial_confidence ==
               accepted->location.coarse_initial_confidence &&
           config->location.predicted_min_confidence ==
               accepted->location.predicted_min_confidence &&
           config->low_battery.enter_percent ==
               accepted->low_battery.enter_percent &&
           config->low_battery.exit_percent ==
               accepted->low_battery.exit_percent &&
           config->low_battery.critical_percent ==
               accepted->low_battery.critical_percent &&
           equal_schedule(&config->low_battery.schedule,
                          &accepted->low_battery.schedule) &&
           config->sos.gnss_immediate == accepted->sos.gnss_immediate &&
           config->sos.gnss_retry_interval_ms ==
               accepted->sos.gnss_retry_interval_ms &&
           config->sos.gnss_acquisition_timeout_ms ==
               accepted->sos.gnss_acquisition_timeout_ms &&
           config->sos.cell_interval_ms == accepted->sos.cell_interval_ms &&
           config->sos.imu_rate_hz == accepted->sos.imu_rate_hz &&
           config->sos.lte_keep_connected == accepted->sos.lte_keep_connected &&
           config->sos.upload_last_trusted ==
               accepted->sos.upload_last_trusted &&
           config->sos.start_ego_call == accepted->sos.start_ego_call;
}

void egolink_location_policy_default_config(
    egolink_location_policy_config_t *output)
{
    if (output != NULL) {
        *output = accepted_default_config;
    }
}

egolink_location_policy_result_t egolink_location_policy_validate_config(
    const egolink_location_policy_config_t *config)
{
    if (!semantic_config_valid(config) || !exact_accepted_config(config)) {
        return EGOLINK_LOCATION_POLICY_INVALID_CONFIG;
    }
    return EGOLINK_LOCATION_POLICY_OK;
}

egolink_location_policy_result_t egolink_location_policy_init(
    egolink_location_policy_core_t *core,
    const egolink_location_policy_config_t *config)
{
    if (core == NULL || config == NULL) {
        return EGOLINK_LOCATION_POLICY_INVALID_ARGUMENT;
    }
    const egolink_location_policy_result_t validation =
        egolink_location_policy_validate_config(config);
    if (validation != EGOLINK_LOCATION_POLICY_OK) {
        return validation;
    }

    egolink_location_policy_core_t candidate;
    memset(&candidate, 0, sizeof(candidate));
    candidate.initialized = true;
    candidate.config = accepted_default_config;
    candidate.runtime.initialized = true;
    candidate.runtime.mode = EGOLINK_LOCATION_POLICY_STABLE;
    candidate.runtime.observed_mobility_state =
        EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN;
    *core = candidate;
    return EGOLINK_LOCATION_POLICY_OK;
}

static bool valid_mobility(egolink_location_policy_mobility_t value)
{
    return value == EGOLINK_LOCATION_POLICY_MOBILITY_STABLE ||
           value == EGOLINK_LOCATION_POLICY_MOBILITY_MOVING ||
           value == EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN;
}

static bool valid_gnss_state(egolink_location_policy_gnss_state_t value)
{
    return value >= EGOLINK_LOCATION_POLICY_GNSS_IDLE &&
           value <= EGOLINK_LOCATION_POLICY_GNSS_UNAVAILABLE;
}

static bool valid_battery_state(
    egolink_location_policy_battery_state_t value)
{
    return value >= EGOLINK_LOCATION_POLICY_BATTERY_NORMAL &&
           value <= EGOLINK_LOCATION_POLICY_BATTERY_UNKNOWN;
}

static bool valid_belief(egolink_location_policy_belief_t value)
{
    return value >= EGOLINK_LOCATION_POLICY_BELIEF_FINE &&
           value <= EGOLINK_LOCATION_POLICY_BELIEF_UNKNOWN;
}

static bool valid_event_type(egolink_location_policy_event_type_t value)
{
    return value >= EGOLINK_LOCATION_POLICY_EVENT_TICK &&
           value <= EGOLINK_LOCATION_POLICY_EVENT_SOS;
}

static bool valid_mode(egolink_location_policy_mode_t value)
{
    return value >= EGOLINK_LOCATION_POLICY_STABLE &&
           value <= EGOLINK_LOCATION_POLICY_LOW_BATTERY;
}

static bool runtime_valid(
    const egolink_location_policy_runtime_t *runtime,
    uint64_t event_time_ms)
{
    if (runtime == NULL || !runtime->initialized || !valid_mode(runtime->mode) ||
        !valid_mobility(runtime->observed_mobility_state) ||
        (runtime->last_evaluation_available &&
         runtime->last_evaluation_ms > event_time_ms) ||
        (runtime->last_mobility_observation_available &&
         runtime->last_mobility_observation_ms > event_time_ms) ||
        (runtime->last_gnss_attempt_available &&
         runtime->last_gnss_attempt_ms > event_time_ms) ||
        (runtime->gnss_acquisition_started_available &&
         (!runtime->last_gnss_attempt_available ||
          runtime->gnss_acquisition_started_ms > event_time_ms)) ||
        (runtime->last_cell_action_available &&
         runtime->last_cell_action_ms > event_time_ms) ||
        (runtime->cell_request_started_available &&
         (!runtime->last_cell_action_available ||
          runtime->cell_request_started_ms > event_time_ms))) {
        return false;
    }
    return true;
}

static bool event_requires_lineage(egolink_location_policy_event_type_t value)
{
    return value == EGOLINK_LOCATION_POLICY_EVENT_MOBILITY ||
           value == EGOLINK_LOCATION_POLICY_EVENT_GNSS_STARTED ||
           value == EGOLINK_LOCATION_POLICY_EVENT_GNSS_STOPPED ||
           value == EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX ||
           value == EGOLINK_LOCATION_POLICY_EVENT_GNSS_ERROR;
}

static egolink_location_policy_result_t validate_inputs(
    const egolink_location_policy_core_t *core,
    const egolink_location_policy_snapshot_t *snapshot,
    const egolink_location_policy_event_t *event)
{
    if (core == NULL || snapshot == NULL || event == NULL) {
        return EGOLINK_LOCATION_POLICY_INVALID_ARGUMENT;
    }
    if (!core->initialized || !core->runtime.initialized) {
        return EGOLINK_LOCATION_POLICY_NOT_INITIALIZED;
    }
    if (egolink_location_policy_validate_config(&core->config) !=
        EGOLINK_LOCATION_POLICY_OK) {
        return EGOLINK_LOCATION_POLICY_INVALID_CONFIG;
    }
    if (!valid_mobility(snapshot->mobility_state) ||
        !valid_gnss_state(snapshot->gnss_state) ||
        !valid_battery_state(snapshot->battery_state) ||
        !valid_belief(snapshot->location_belief) ||
        (snapshot->battery_percent_available &&
         (!finite_nonnegative(snapshot->battery_percent) ||
          snapshot->battery_percent > 100.0)) ||
        (snapshot->location_uncertainty_available &&
         !finite_nonnegative(snapshot->location_uncertainty_m)) ||
        (snapshot->last_trusted_time_available &&
         snapshot->last_trusted_time_ms > snapshot->event_time_ms)) {
        return EGOLINK_LOCATION_POLICY_INVALID_SNAPSHOT;
    }
    if (!valid_event_type(event->type) ||
        event->event_time_ms != snapshot->event_time_ms ||
        (event_requires_lineage(event->type) && !event->attributable_lineage)) {
        return EGOLINK_LOCATION_POLICY_INVALID_EVENT;
    }
    if (core->runtime.last_evaluation_available &&
        snapshot->event_time_ms < core->runtime.last_evaluation_ms) {
        return EGOLINK_LOCATION_POLICY_TIME_REGRESSION;
    }
    if (!runtime_valid(&core->runtime, snapshot->event_time_ms)) {
        return EGOLINK_LOCATION_POLICY_INVALID_RUNTIME;
    }
    return EGOLINK_LOCATION_POLICY_OK;
}

static bool add_u64_checked(uint64_t left, uint64_t right, uint64_t *output)
{
    if (output == NULL || left > UINT64_MAX - right) {
        return false;
    }
    *output = left + right;
    return true;
}

static bool bounded_backoff_ms(
    uint64_t initial_ms,
    double multiplier,
    uint32_t failure_count,
    uint64_t maximum_ms,
    uint64_t *output)
{
    if (output == NULL || failure_count == 0U) {
        return false;
    }
    double result = (double)initial_ms;
    const double maximum = (double)maximum_ms;
    for (uint32_t index = 1U; index < failure_count; ++index) {
        if (result >= maximum || result > maximum / multiplier) {
            result = maximum;
            break;
        }
        result *= multiplier;
    }
    if (!isfinite(result) || result < 0.0) {
        return false;
    }
    if (result > maximum) {
        result = maximum;
    }
    *output = (uint64_t)result;
    return true;
}

static egolink_location_policy_result_t record_gnss_failure(
    egolink_location_policy_runtime_t *runtime,
    const egolink_location_policy_config_t *config,
    uint64_t event_time_ms,
    egolink_location_policy_mode_t effective_mode)
{
    if (runtime->consecutive_no_fix == UINT32_MAX) {
        return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
    }
    ++runtime->consecutive_no_fix;
    uint64_t backoff_ms = 0U;
    if (effective_mode == EGOLINK_LOCATION_POLICY_SOS) {
        backoff_ms = config->sos.gnss_retry_interval_ms;
    } else if (!bounded_backoff_ms(
                   config->gnss.retry_backoff_ms,
                   config->gnss.retry_backoff_multiplier,
                   runtime->consecutive_no_fix,
                   config->gnss.max_retry_backoff_ms,
                   &backoff_ms)) {
        return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
    }
    uint64_t retry_deadline = 0U;
    if (!add_u64_checked(event_time_ms, backoff_ms, &retry_deadline)) {
        return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
    }
    runtime->gnss_acquisition_started_available = false;
    runtime->last_gnss_attempt_available = true;
    runtime->last_gnss_attempt_ms = event_time_ms;
    runtime->retry_not_before_available = true;
    runtime->retry_not_before_ms = retry_deadline;
    return EGOLINK_LOCATION_POLICY_OK;
}

static egolink_location_policy_result_t apply_event_result(
    egolink_location_policy_runtime_t *runtime,
    const egolink_location_policy_config_t *config,
    const egolink_location_policy_snapshot_t *snapshot,
    const egolink_location_policy_event_t *event)
{
    const uint64_t event_time_ms = event->event_time_ms;
    switch (event->type) {
    case EGOLINK_LOCATION_POLICY_EVENT_GNSS_STARTED:
        runtime->last_gnss_attempt_available = true;
        runtime->last_gnss_attempt_ms = event_time_ms;
        runtime->gnss_acquisition_started_available = true;
        runtime->gnss_acquisition_started_ms = event_time_ms;
        break;
    case EGOLINK_LOCATION_POLICY_EVENT_GNSS_FIX:
        if (snapshot->gnss_state == EGOLINK_LOCATION_POLICY_GNSS_FIX) {
            runtime->gnss_acquisition_started_available = false;
            runtime->consecutive_no_fix = 0U;
            runtime->retry_not_before_available = false;
            runtime->last_gnss_attempt_available = true;
            runtime->last_gnss_attempt_ms = event_time_ms;
        } else {
            /*
             * Frozen host ordering applies a GNSS result before deriving the
             * mode from this snapshot. runtime->mode is therefore the last
             * committed (previous) mode, including on a same-event SOS entry.
             * The later SOS-entry action may immediately clear this backoff.
             */
            return record_gnss_failure(
                runtime, config, event_time_ms, runtime->mode);
        }
        break;
    case EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX:
    case EGOLINK_LOCATION_POLICY_EVENT_GNSS_ERROR:
        /* Keep the same previous-mode ordering as the frozen host oracle. */
        return record_gnss_failure(
            runtime, config, event_time_ms, runtime->mode);
    case EGOLINK_LOCATION_POLICY_EVENT_GNSS_STOPPED:
        runtime->gnss_acquisition_started_available = false;
        break;
    case EGOLINK_LOCATION_POLICY_EVENT_CELL_OBSERVATION:
        runtime->last_cell_action_available = true;
        runtime->last_cell_action_ms = event_time_ms;
        runtime->cell_request_started_available = false;
        runtime->consecutive_cell_timeouts = 0U;
        runtime->cell_retry_not_before_available = false;
        break;
    case EGOLINK_LOCATION_POLICY_EVENT_MOBILITY:
        runtime->observed_mobility_state = snapshot->mobility_state;
        runtime->last_mobility_observation_available = true;
        runtime->last_mobility_observation_ms = event_time_ms;
        break;
    case EGOLINK_LOCATION_POLICY_EVENT_TICK:
    case EGOLINK_LOCATION_POLICY_EVENT_COARSE_LOCATION:
    case EGOLINK_LOCATION_POLICY_EVENT_LTE_STATE:
    case EGOLINK_LOCATION_POLICY_EVENT_BATTERY:
    case EGOLINK_LOCATION_POLICY_EVENT_SOS:
        break;
    default:
        return EGOLINK_LOCATION_POLICY_INVALID_EVENT;
    }
    return EGOLINK_LOCATION_POLICY_OK;
}

static egolink_location_policy_mobility_t effective_mobility(
    const egolink_location_policy_runtime_t *runtime,
    const egolink_location_policy_config_t *config,
    uint64_t event_time_ms)
{
    if (runtime->last_mobility_observation_available &&
        event_time_ms >= runtime->last_mobility_observation_ms &&
        event_time_ms - runtime->last_mobility_observation_ms <=
            config->movement.evidence_stale_after_ms &&
        (runtime->observed_mobility_state ==
             EGOLINK_LOCATION_POLICY_MOBILITY_STABLE ||
         runtime->observed_mobility_state ==
             EGOLINK_LOCATION_POLICY_MOBILITY_MOVING)) {
        return runtime->observed_mobility_state;
    }
    return EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN;
}

static void update_low_battery_latch(
    egolink_location_policy_runtime_t *runtime,
    const egolink_location_policy_config_t *config,
    const egolink_location_policy_snapshot_t *snapshot)
{
    if (snapshot->battery_state == EGOLINK_LOCATION_POLICY_BATTERY_LOW ||
        snapshot->battery_state == EGOLINK_LOCATION_POLICY_BATTERY_CRITICAL) {
        runtime->low_battery_latched = true;
        return;
    }
    if (snapshot->battery_percent_available) {
        if (snapshot->battery_percent <= config->low_battery.enter_percent) {
            runtime->low_battery_latched = true;
        } else if (
            snapshot->battery_percent >= config->low_battery.exit_percent &&
            (snapshot->battery_state == EGOLINK_LOCATION_POLICY_BATTERY_NORMAL ||
             snapshot->battery_state ==
                 EGOLINK_LOCATION_POLICY_BATTERY_CHARGING)) {
            runtime->low_battery_latched = false;
        }
    } else if (
        snapshot->battery_state == EGOLINK_LOCATION_POLICY_BATTERY_NORMAL ||
        snapshot->battery_state == EGOLINK_LOCATION_POLICY_BATTERY_CHARGING) {
        runtime->low_battery_latched = false;
    }
}

static egolink_location_policy_conditions_t derive_conditions(
    const egolink_location_policy_runtime_t *runtime,
    const egolink_location_policy_config_t *config,
    const egolink_location_policy_snapshot_t *snapshot,
    egolink_location_policy_mobility_t mobility)
{
    bool uncertain =
        snapshot->location_belief == EGOLINK_LOCATION_POLICY_BELIEF_UNKNOWN ||
        snapshot->location_belief == EGOLINK_LOCATION_POLICY_BELIEF_PREDICTED;
    if (snapshot->location_uncertainty_available &&
        snapshot->location_uncertainty_m >=
            config->location.uncertain_threshold_m) {
        uncertain = true;
    }
    const bool critical =
        snapshot->battery_state == EGOLINK_LOCATION_POLICY_BATTERY_CRITICAL ||
        (snapshot->battery_percent_available &&
         snapshot->battery_percent <= config->low_battery.critical_percent);
    const egolink_location_policy_conditions_t conditions = {
        .sos_active = snapshot->sos_active,
        .low_battery = runtime->low_battery_latched,
        .critical_battery = critical,
        .location_uncertain = uncertain,
        .moving = mobility == EGOLINK_LOCATION_POLICY_MOBILITY_MOVING,
    };
    return conditions;
}

static egolink_location_policy_mode_t effective_mode(
    const egolink_location_policy_conditions_t *conditions)
{
    if (conditions->sos_active) {
        return EGOLINK_LOCATION_POLICY_SOS;
    }
    if (conditions->low_battery) {
        return EGOLINK_LOCATION_POLICY_LOW_BATTERY;
    }
    if (conditions->location_uncertain) {
        return EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN;
    }
    if (conditions->moving) {
        return EGOLINK_LOCATION_POLICY_MOVING;
    }
    return EGOLINK_LOCATION_POLICY_STABLE;
}

static effective_schedule_t schedule_for_mode(
    const egolink_location_policy_config_t *config,
    egolink_location_policy_mode_t mode)
{
    if (mode == EGOLINK_LOCATION_POLICY_SOS) {
        const effective_schedule_t schedule = {
            .gnss_interval_ms = config->sos.gnss_retry_interval_ms,
            .gnss_acquisition_timeout_ms =
                config->sos.gnss_acquisition_timeout_ms,
            .cell_interval_ms = config->sos.cell_interval_ms,
            .imu_rate_hz = config->sos.imu_rate_hz,
            .lte_keep_connected = config->sos.lte_keep_connected,
        };
        return schedule;
    }
    const egolink_location_policy_schedule_config_t *selected =
        &config->stationary;
    if (mode == EGOLINK_LOCATION_POLICY_LOW_BATTERY) {
        selected = &config->low_battery.schedule;
    } else if (mode == EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN) {
        selected = &config->location_uncertain;
    } else if (mode == EGOLINK_LOCATION_POLICY_MOVING) {
        selected = &config->moving;
    }
    const effective_schedule_t schedule = {
        .gnss_interval_ms = selected->gnss_interval_ms,
        .gnss_acquisition_timeout_ms = config->gnss.acquisition_timeout_ms,
        .cell_interval_ms = selected->cell_interval_ms,
        .imu_rate_hz = selected->imu_rate_hz,
        .lte_keep_connected = selected->lte_keep_connected,
    };
    return schedule;
}

static egolink_location_policy_result_t derive_gnss_action(
    egolink_location_policy_runtime_t *runtime,
    const egolink_location_policy_config_t *config,
    uint64_t event_time_ms,
    egolink_location_policy_mode_t mode,
    bool sos_entry,
    const effective_schedule_t *schedule,
    egolink_location_policy_decision_t *decision)
{
    decision->gnss_acquisition_timeout_ms =
        schedule->gnss_acquisition_timeout_ms;
    if (runtime->gnss_acquisition_started_available) {
        if (event_time_ms - runtime->gnss_acquisition_started_ms >=
            schedule->gnss_acquisition_timeout_ms) {
            const egolink_location_policy_result_t result = record_gnss_failure(
                runtime, config, event_time_ms, mode);
            if (result != EGOLINK_LOCATION_POLICY_OK) {
                return result;
            }
            decision->gnss_action =
                EGOLINK_LOCATION_POLICY_GNSS_ACTION_STOP_TIMEOUT;
            decision->gnss_retry_not_before_available = true;
            decision->gnss_retry_not_before_ms = runtime->retry_not_before_ms;
            return EGOLINK_LOCATION_POLICY_OK;
        }
        decision->gnss_action = EGOLINK_LOCATION_POLICY_GNSS_ACTION_CONTINUE;
        decision->gnss_retry_not_before_available =
            runtime->retry_not_before_available;
        decision->gnss_retry_not_before_ms = runtime->retry_not_before_ms;
        return EGOLINK_LOCATION_POLICY_OK;
    }

    if (sos_entry && config->sos.gnss_immediate) {
        runtime->retry_not_before_available = false;
        runtime->last_gnss_attempt_available = true;
        runtime->last_gnss_attempt_ms = event_time_ms;
        runtime->gnss_acquisition_started_available = true;
        runtime->gnss_acquisition_started_ms = event_time_ms;
        decision->gnss_action = EGOLINK_LOCATION_POLICY_GNSS_ACTION_START;
        return EGOLINK_LOCATION_POLICY_OK;
    }
    if (runtime->retry_not_before_available &&
        event_time_ms < runtime->retry_not_before_ms) {
        decision->gnss_action =
            EGOLINK_LOCATION_POLICY_GNSS_ACTION_WAIT_BACKOFF;
        decision->gnss_retry_not_before_available = true;
        decision->gnss_retry_not_before_ms = runtime->retry_not_before_ms;
        return EGOLINK_LOCATION_POLICY_OK;
    }
    if (runtime->retry_not_before_available &&
        event_time_ms >= runtime->retry_not_before_ms) {
        runtime->retry_not_before_available = false;
    }

    const bool due = !runtime->last_gnss_attempt_available ||
        event_time_ms - runtime->last_gnss_attempt_ms >=
            schedule->gnss_interval_ms;
    if (due) {
        runtime->retry_not_before_available = false;
        runtime->last_gnss_attempt_available = true;
        runtime->last_gnss_attempt_ms = event_time_ms;
        runtime->gnss_acquisition_started_available = true;
        runtime->gnss_acquisition_started_ms = event_time_ms;
        decision->gnss_action = EGOLINK_LOCATION_POLICY_GNSS_ACTION_START;
    } else {
        decision->gnss_action =
            EGOLINK_LOCATION_POLICY_GNSS_ACTION_WAIT_INTERVAL;
        decision->gnss_retry_not_before_available =
            runtime->retry_not_before_available;
        decision->gnss_retry_not_before_ms = runtime->retry_not_before_ms;
    }
    return EGOLINK_LOCATION_POLICY_OK;
}

static egolink_location_policy_result_t derive_cell_action(
    egolink_location_policy_runtime_t *runtime,
    const egolink_location_policy_config_t *config,
    uint64_t event_time_ms,
    bool force,
    const effective_schedule_t *schedule,
    egolink_location_policy_decision_t *decision)
{
    decision->cell_interval_ms = schedule->cell_interval_ms;
    decision->cell_request_timeout_ms = config->cell.request_timeout_ms;
    if (runtime->cell_request_started_available) {
        if (event_time_ms - runtime->cell_request_started_ms >=
            config->cell.request_timeout_ms) {
            if (runtime->consecutive_cell_timeouts == UINT32_MAX) {
                return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
            }
            ++runtime->consecutive_cell_timeouts;
            uint64_t backoff_ms = 0U;
            uint64_t deadline = 0U;
            if (!bounded_backoff_ms(
                    config->cell.retry_backoff_ms,
                    config->cell.retry_backoff_multiplier,
                    runtime->consecutive_cell_timeouts,
                    config->cell.max_retry_backoff_ms,
                    &backoff_ms) ||
                !add_u64_checked(event_time_ms, backoff_ms, &deadline)) {
                return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
            }
            runtime->cell_request_started_available = false;
            runtime->cell_retry_not_before_available = true;
            runtime->cell_retry_not_before_ms = deadline;
            decision->cell_action = EGOLINK_LOCATION_POLICY_CELL_ACTION_TIMEOUT;
            decision->cell_retry_not_before_available = true;
            decision->cell_retry_not_before_ms = deadline;
            return EGOLINK_LOCATION_POLICY_OK;
        }
        decision->cell_action = EGOLINK_LOCATION_POLICY_CELL_ACTION_CONTINUE;
        decision->cell_retry_not_before_available =
            runtime->cell_retry_not_before_available;
        decision->cell_retry_not_before_ms = runtime->cell_retry_not_before_ms;
        return EGOLINK_LOCATION_POLICY_OK;
    }

    if (runtime->cell_retry_not_before_available &&
        event_time_ms >= runtime->cell_retry_not_before_ms) {
        runtime->cell_retry_not_before_available = false;
    }
    if (runtime->cell_retry_not_before_available &&
        event_time_ms < runtime->cell_retry_not_before_ms && !force) {
        decision->cell_action =
            EGOLINK_LOCATION_POLICY_CELL_ACTION_WAIT_BACKOFF;
        decision->cell_retry_not_before_available = true;
        decision->cell_retry_not_before_ms = runtime->cell_retry_not_before_ms;
        return EGOLINK_LOCATION_POLICY_OK;
    }

    const bool due = force || !runtime->last_cell_action_available ||
        event_time_ms - runtime->last_cell_action_ms >=
            schedule->cell_interval_ms;
    if (due) {
        runtime->cell_retry_not_before_available = false;
        runtime->last_cell_action_available = true;
        runtime->last_cell_action_ms = event_time_ms;
        runtime->cell_request_started_available = true;
        runtime->cell_request_started_ms = event_time_ms;
        decision->cell_action = EGOLINK_LOCATION_POLICY_CELL_ACTION_OBSERVE;
        decision->cell_observe_now = true;
    } else {
        decision->cell_action =
            EGOLINK_LOCATION_POLICY_CELL_ACTION_WAIT_INTERVAL;
        decision->cell_retry_not_before_available =
            runtime->cell_retry_not_before_available;
        decision->cell_retry_not_before_ms = runtime->cell_retry_not_before_ms;
    }
    return EGOLINK_LOCATION_POLICY_OK;
}

static bool add_future_deadline(
    uint64_t event_time_ms,
    uint64_t base,
    uint64_t delta,
    bool plus_one,
    bool *has_candidate,
    uint64_t *candidate)
{
    uint64_t deadline = 0U;
    if (!add_u64_checked(base, delta, &deadline) ||
        (plus_one && !add_u64_checked(deadline, 1U, &deadline))) {
        return false;
    }
    if (deadline > event_time_ms &&
        (!*has_candidate || deadline < *candidate)) {
        *has_candidate = true;
        *candidate = deadline;
    }
    return true;
}

static void add_absolute_future_deadline(
    uint64_t event_time_ms,
    bool available,
    uint64_t deadline,
    bool *has_candidate,
    uint64_t *candidate)
{
    if (available && deadline > event_time_ms &&
        (!*has_candidate || deadline < *candidate)) {
        *has_candidate = true;
        *candidate = deadline;
    }
}

static egolink_location_policy_result_t derive_next_evaluation(
    const egolink_location_policy_runtime_t *runtime,
    const egolink_location_policy_config_t *config,
    const egolink_location_policy_snapshot_t *snapshot,
    const effective_schedule_t *schedule,
    egolink_location_policy_decision_t *decision)
{
    bool available = false;
    uint64_t candidate = 0U;
    const uint64_t now = snapshot->event_time_ms;

    if (runtime->gnss_acquisition_started_available) {
        if (!add_future_deadline(
                now,
                runtime->gnss_acquisition_started_ms,
                schedule->gnss_acquisition_timeout_ms,
                false,
                &available,
                &candidate)) {
            return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
        }
    } else {
        add_absolute_future_deadline(
            now,
            runtime->retry_not_before_available,
            runtime->retry_not_before_ms,
            &available,
            &candidate);
        if (runtime->last_gnss_attempt_available &&
            !add_future_deadline(
                now,
                runtime->last_gnss_attempt_ms,
                schedule->gnss_interval_ms,
                false,
                &available,
                &candidate)) {
            return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
        }
    }

    if (runtime->cell_request_started_available) {
        if (!add_future_deadline(
                now,
                runtime->cell_request_started_ms,
                config->cell.request_timeout_ms,
                false,
                &available,
                &candidate)) {
            return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
        }
    } else {
        add_absolute_future_deadline(
            now,
            runtime->cell_retry_not_before_available,
            runtime->cell_retry_not_before_ms,
            &available,
            &candidate);
        if (runtime->last_cell_action_available &&
            !add_future_deadline(
                now,
                runtime->last_cell_action_ms,
                schedule->cell_interval_ms,
                false,
                &available,
                &candidate)) {
            return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
        }
    }

    if (snapshot->last_trusted_time_available) {
        if (snapshot->location_belief == EGOLINK_LOCATION_POLICY_BELIEF_FINE &&
            !add_future_deadline(
                now,
                snapshot->last_trusted_time_ms,
                config->location.fine_freshness_ms,
                true,
                &available,
                &candidate)) {
            return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
        }
        if (snapshot->location_belief ==
                EGOLINK_LOCATION_POLICY_BELIEF_COARSE &&
            !add_future_deadline(
                now,
                snapshot->last_trusted_time_ms,
                config->location.coarse_freshness_ms,
                true,
                &available,
                &candidate)) {
            return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
        }
        if (!add_future_deadline(
                now,
                snapshot->last_trusted_time_ms,
                config->location.prediction_horizon_ms,
                true,
                &available,
                &candidate)) {
            return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
        }
    }

    if (runtime->last_mobility_observation_available &&
        (runtime->observed_mobility_state ==
             EGOLINK_LOCATION_POLICY_MOBILITY_STABLE ||
         runtime->observed_mobility_state ==
             EGOLINK_LOCATION_POLICY_MOBILITY_MOVING) &&
        !add_future_deadline(
            now,
            runtime->last_mobility_observation_ms,
            config->movement.evidence_stale_after_ms,
            true,
            &available,
            &candidate)) {
        return EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW;
    }

    decision->next_evaluation_available = available;
    decision->next_evaluation_ms = candidate;
    return EGOLINK_LOCATION_POLICY_OK;
}

egolink_location_policy_result_t egolink_location_policy_evaluate(
    egolink_location_policy_core_t *core,
    const egolink_location_policy_snapshot_t *snapshot,
    const egolink_location_policy_event_t *event,
    egolink_location_policy_decision_t *decision)
{
    if (decision == NULL) {
        return EGOLINK_LOCATION_POLICY_INVALID_ARGUMENT;
    }
    memset(decision, 0, sizeof(*decision));
    const egolink_location_policy_result_t input_result =
        validate_inputs(core, snapshot, event);
    if (input_result != EGOLINK_LOCATION_POLICY_OK) {
        return input_result;
    }

    egolink_location_policy_core_t candidate = *core;
    egolink_location_policy_decision_t staged;
    memset(&staged, 0, sizeof(staged));
    candidate.runtime.last_evaluation_available = true;
    candidate.runtime.last_evaluation_ms = snapshot->event_time_ms;

    egolink_location_policy_result_t result = apply_event_result(
        &candidate.runtime, &candidate.config, snapshot, event);
    if (result != EGOLINK_LOCATION_POLICY_OK) {
        return result;
    }
    update_low_battery_latch(&candidate.runtime, &candidate.config, snapshot);
    const egolink_location_policy_mobility_t mobility = effective_mobility(
        &candidate.runtime, &candidate.config, snapshot->event_time_ms);
    const egolink_location_policy_conditions_t conditions = derive_conditions(
        &candidate.runtime, &candidate.config, snapshot, mobility);
    const egolink_location_policy_mode_t previous_mode = candidate.runtime.mode;
    const egolink_location_policy_mode_t mode = effective_mode(&conditions);
    const bool sos_entry =
        mode == EGOLINK_LOCATION_POLICY_SOS &&
        previous_mode != EGOLINK_LOCATION_POLICY_SOS;
    const effective_schedule_t schedule =
        schedule_for_mode(&candidate.config, mode);

    staged.config_id = EGOLINK_LOCATION_POLICY_CONFIG_ID;
    staged.config_hash = EGOLINK_LOCATION_POLICY_CONFIG_HASH;
    staged.policy_mode = mode;
    staged.derived_mobility_state = mobility;
    staged.conditions = conditions;
    staged.transition_from = previous_mode;
    staged.transition_to = mode;
    staged.transition_changed = previous_mode != mode;
    staged.imu_rate_hz = schedule.imu_rate_hz;
    staged.lte_keep_connected = schedule.lte_keep_connected;
    staged.camera_requested = false;

    result = derive_gnss_action(
        &candidate.runtime,
        &candidate.config,
        snapshot->event_time_ms,
        mode,
        sos_entry,
        &schedule,
        &staged);
    if (result != EGOLINK_LOCATION_POLICY_OK) {
        return result;
    }
    result = derive_cell_action(
        &candidate.runtime,
        &candidate.config,
        snapshot->event_time_ms,
        sos_entry,
        &schedule,
        &staged);
    if (result != EGOLINK_LOCATION_POLICY_OK) {
        return result;
    }

    const bool accepted_location =
        (event->type == EGOLINK_LOCATION_POLICY_EVENT_GNSS_FIX &&
         snapshot->gnss_state == EGOLINK_LOCATION_POLICY_GNSS_FIX) ||
        (event->type == EGOLINK_LOCATION_POLICY_EVENT_COARSE_LOCATION &&
         snapshot->location_belief == EGOLINK_LOCATION_POLICY_BELIEF_COARSE);
    staged.upload_location_now = accepted_location;
    const bool sos_location_result =
        event->type == EGOLINK_LOCATION_POLICY_EVENT_GNSS_FIX ||
        event->type == EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX ||
        event->type == EGOLINK_LOCATION_POLICY_EVENT_GNSS_ERROR;
    if (mode == EGOLINK_LOCATION_POLICY_SOS &&
        (sos_entry || sos_location_result) && !accepted_location &&
        candidate.config.sos.upload_last_trusted) {
        staged.upload_location_now = true;
        staged.upload_last_trusted_now = true;
    }
    staged.start_ego_call_now =
        sos_entry && candidate.config.sos.start_ego_call;

    candidate.runtime.mode = mode;
    result = derive_next_evaluation(
        &candidate.runtime, &candidate.config, snapshot, &schedule, &staged);
    if (result != EGOLINK_LOCATION_POLICY_OK) {
        return result;
    }
    staged.runtime = candidate.runtime;

    *core = candidate;
    *decision = staged;
    return EGOLINK_LOCATION_POLICY_OK;
}

const char *egolink_location_policy_result_name(
    egolink_location_policy_result_t result)
{
    switch (result) {
    case EGOLINK_LOCATION_POLICY_OK:
        return "ok";
    case EGOLINK_LOCATION_POLICY_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_LOCATION_POLICY_INVALID_CONFIG:
        return "invalid_config";
    case EGOLINK_LOCATION_POLICY_INVALID_RUNTIME:
        return "invalid_runtime";
    case EGOLINK_LOCATION_POLICY_INVALID_SNAPSHOT:
        return "invalid_snapshot";
    case EGOLINK_LOCATION_POLICY_INVALID_EVENT:
        return "invalid_event";
    case EGOLINK_LOCATION_POLICY_TIME_REGRESSION:
        return "time_regression";
    case EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW:
        return "deadline_overflow";
    case EGOLINK_LOCATION_POLICY_NOT_INITIALIZED:
        return "not_initialized";
    default:
        return "unknown";
    }
}

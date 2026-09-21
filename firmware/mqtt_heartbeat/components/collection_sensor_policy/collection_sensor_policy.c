#include "collection_sensor_policy.h"

#include <math.h>
#include <string.h>

#define ACCEL_MG_TO_MS2 0.00980665
#define STANDARD_GRAVITY_MS2 9.80665

static void reevaluate_locked(
    collection_sensor_policy_t *policy,
    egolink_location_policy_event_type_t event_type,
    uint64_t now_ms)
{
    if (policy == NULL || !policy->initialized) {
        return;
    }

    /* Prevent time regression against the underlying policy runtime */
    if (policy->core.runtime.last_evaluation_available &&
        now_ms < policy->core.runtime.last_evaluation_ms) {
        now_ms = policy->core.runtime.last_evaluation_ms;
    }

    egolink_location_policy_snapshot_t snap = {0};
    snap.event_time_ms = now_ms;

    /* Check mobility staleness */
    if (policy->last_mobility_observation_ms > 0U &&
        now_ms >= policy->last_mobility_observation_ms &&
        now_ms - policy->last_mobility_observation_ms <=
            policy->config.movement.evidence_stale_after_ms) {
        snap.mobility_state = policy->detected_mobility;
    } else {
        snap.mobility_state = EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN;
    }

    snap.gnss_state = policy->gnss_state;
    snap.battery_state = policy->battery_state;
    snap.battery_percent_available = policy->battery_percent_available;
    snap.battery_percent = policy->battery_percent;
    snap.sos_active = policy->sos_active;

    /* Assess location belief from recent fix history */
    if (policy->last_gnss_fix_ms > 0U) {
        uint64_t fix_age_ms = now_ms >= policy->last_gnss_fix_ms ?
            now_ms - policy->last_gnss_fix_ms : 0U;
        if (fix_age_ms <= policy->config.location.fine_freshness_ms) {
            snap.location_belief = EGOLINK_LOCATION_POLICY_BELIEF_FINE;
        } else if (fix_age_ms <= policy->config.location.prediction_horizon_ms) {
            snap.location_belief = EGOLINK_LOCATION_POLICY_BELIEF_PREDICTED;
        } else {
            snap.location_belief = EGOLINK_LOCATION_POLICY_BELIEF_UNKNOWN;
        }
        snap.last_trusted_time_available = true;
        snap.last_trusted_time_ms = policy->last_gnss_fix_ms;
    } else {
        snap.location_belief = EGOLINK_LOCATION_POLICY_BELIEF_UNKNOWN;
        snap.last_trusted_time_available = false;
        snap.last_trusted_time_ms = 0U;
    }

    egolink_location_policy_event_t event = {
        .type = event_type,
        .event_time_ms = now_ms,
        .attributable_lineage = true,
    };

    egolink_location_policy_decision_t decision;
    egolink_location_policy_result_t res = egolink_location_policy_evaluate(
        &policy->core, &snap, &event, &decision);
    if (res != EGOLINK_LOCATION_POLICY_OK) {
        return;
    }

    /* Detect transition to moving for immediate GNSS trigger */
    if (policy->snapshot.policy_mode != decision.policy_mode &&
        decision.policy_mode == EGOLINK_LOCATION_POLICY_MOVING) {
        policy->snapshot.immediate_gnss_trigger = true;
    }

    policy->snapshot.policy_mode = decision.policy_mode;
    policy->snapshot.mobility_state = decision.derived_mobility_state;
    policy->snapshot.current_rms_m_s2 = policy->latest_rms;
    policy->snapshot.low_battery_latched = decision.conditions.low_battery;
    policy->snapshot.imu_rate_hz = decision.imu_rate_hz;
    policy->snapshot.transition_changed = decision.transition_changed;
    policy->snapshot.transition_from = decision.transition_from;
    policy->snapshot.transition_to = decision.transition_to;
    policy->snapshot.config_id = decision.config_id;
    policy->snapshot.config_hash = decision.config_hash;

    switch (decision.policy_mode) {
    case EGOLINK_LOCATION_POLICY_STABLE:
        policy->snapshot.gnss_interval_ms =
            policy->config.stationary.gnss_interval_ms;
        policy->snapshot.cell_interval_ms =
            policy->config.stationary.cell_interval_ms;
        break;
    case EGOLINK_LOCATION_POLICY_MOVING:
        policy->snapshot.gnss_interval_ms =
            policy->config.moving.gnss_interval_ms;
        policy->snapshot.cell_interval_ms =
            policy->config.moving.cell_interval_ms;
        break;
    case EGOLINK_LOCATION_POLICY_LOW_BATTERY:
        policy->snapshot.gnss_interval_ms =
            policy->config.low_battery.schedule.gnss_interval_ms;
        policy->snapshot.cell_interval_ms =
            policy->config.low_battery.schedule.cell_interval_ms;
        break;
    case EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN:
        policy->snapshot.gnss_interval_ms =
            policy->config.location_uncertain.gnss_interval_ms;
        policy->snapshot.cell_interval_ms =
            policy->config.location_uncertain.cell_interval_ms;
        break;
    case EGOLINK_LOCATION_POLICY_SOS:
        policy->snapshot.gnss_interval_ms =
            policy->config.sos.gnss_retry_interval_ms;
        policy->snapshot.cell_interval_ms =
            policy->config.sos.cell_interval_ms;
        break;
    default:
        policy->snapshot.gnss_interval_ms =
            policy->config.stationary.gnss_interval_ms;
        policy->snapshot.cell_interval_ms =
            policy->config.stationary.cell_interval_ms;
        break;
    }
}

bool collection_sensor_policy_init(collection_sensor_policy_t *policy)
{
    if (policy == NULL) {
        return false;
    }
    memset(policy, 0, sizeof(*policy));

    egolink_location_policy_default_config(&policy->config);
    if (egolink_location_policy_init(&policy->core, &policy->config) !=
        EGOLINK_LOCATION_POLICY_OK) {
        return false;
    }

    policy->detected_mobility = EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN;
    policy->gnss_state = EGOLINK_LOCATION_POLICY_GNSS_IDLE;
    policy->battery_state = EGOLINK_LOCATION_POLICY_BATTERY_UNKNOWN;
    policy->snapshot.config_id = EGOLINK_LOCATION_POLICY_CONFIG_ID;
    policy->snapshot.config_hash = EGOLINK_LOCATION_POLICY_CONFIG_HASH;
    policy->snapshot.gnss_interval_ms =
        policy->config.stationary.gnss_interval_ms;
    policy->snapshot.cell_interval_ms =
        policy->config.stationary.cell_interval_ms;
    policy->snapshot.imu_rate_hz = 1.0;
    policy->initialized = true;

    reevaluate_locked(policy, EGOLINK_LOCATION_POLICY_EVENT_TICK, 0U);
    return true;
}

void collection_sensor_policy_feed_imu_sample(
    collection_sensor_policy_t *policy,
    int accel_mg_x,
    int accel_mg_y,
    int accel_mg_z,
    uint64_t now_ms)
{
    if (policy == NULL || !policy->initialized) {
        return;
    }

    double ax = (double)accel_mg_x * ACCEL_MG_TO_MS2;
    double ay = (double)accel_mg_y * ACCEL_MG_TO_MS2;
    double az = (double)accel_mg_z * ACCEL_MG_TO_MS2;

    double mag = sqrt(ax * ax + ay * ay + az * az);
    double dev = fabs(mag - STANDARD_GRAVITY_MS2);

    policy->sum_dev_sq += dev * dev;
    policy->sample_count++;

    if (policy->window_start_ms == 0U) {
        policy->window_start_ms = now_ms;
    }

    const uint64_t window_ms = policy->config.movement.window_ms;
    if (now_ms >= policy->window_start_ms &&
        now_ms - policy->window_start_ms >= window_ms) {
        if (policy->sample_count >= policy->config.movement.min_samples) {
            double rms = sqrt(policy->sum_dev_sq / (double)policy->sample_count);
            policy->latest_rms = rms;
            policy->snapshot.current_rms_m_s2 = rms;

            egolink_location_policy_mobility_t prev_mob = policy->detected_mobility;

            if (rms >= policy->config.movement.enter_rms_m_s2) {
                policy->enter_windows++;
                policy->exit_windows = 0U;
                if (policy->enter_windows >=
                    policy->config.movement.enter_windows) {
                    policy->detected_mobility =
                        EGOLINK_LOCATION_POLICY_MOBILITY_MOVING;
                    policy->last_mobility_observation_ms = now_ms;
                }
            } else if (rms <= policy->config.movement.exit_rms_m_s2) {
                policy->exit_windows++;
                policy->enter_windows = 0U;
                if (policy->exit_windows >=
                    policy->config.movement.exit_windows) {
                    policy->detected_mobility =
                        EGOLINK_LOCATION_POLICY_MOBILITY_STABLE;
                    policy->last_mobility_observation_ms = now_ms;
                }
            } else {
                policy->enter_windows = 0U;
                policy->exit_windows = 0U;
                if (policy->detected_mobility !=
                    EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN) {
                    policy->last_mobility_observation_ms = now_ms;
                }
            }

            /* If mobility switched to MOVING, arm immediate GNSS */
            if (prev_mob != EGOLINK_LOCATION_POLICY_MOBILITY_MOVING &&
                policy->detected_mobility ==
                    EGOLINK_LOCATION_POLICY_MOBILITY_MOVING) {
                policy->snapshot.immediate_gnss_trigger = true;
            }
        }

        policy->window_start_ms = now_ms;
        policy->sample_count = 0U;
        policy->sum_dev_sq = 0.0;

        reevaluate_locked(policy, EGOLINK_LOCATION_POLICY_EVENT_MOBILITY, now_ms);
    }
}

void collection_sensor_policy_feed_battery(
    collection_sensor_policy_t *policy,
    double soc_percent,
    bool battery_is_mock,
    bool charging,
    uint64_t now_ms)
{
    if (policy == NULL || !policy->initialized) {
        return;
    }

    if (!battery_is_mock) {
        policy->battery_percent_available = true;
        policy->battery_percent = soc_percent;
        if (soc_percent <= policy->config.low_battery.critical_percent) {
            policy->battery_state = EGOLINK_LOCATION_POLICY_BATTERY_CRITICAL;
        } else if (soc_percent <= policy->config.low_battery.enter_percent) {
            policy->battery_state = EGOLINK_LOCATION_POLICY_BATTERY_LOW;
        } else if (charging) {
            policy->battery_state = EGOLINK_LOCATION_POLICY_BATTERY_CHARGING;
        } else {
            policy->battery_state = EGOLINK_LOCATION_POLICY_BATTERY_NORMAL;
        }
    } else {
        policy->battery_percent_available = false;
        policy->battery_state = EGOLINK_LOCATION_POLICY_BATTERY_UNKNOWN;
    }

    reevaluate_locked(policy, EGOLINK_LOCATION_POLICY_EVENT_BATTERY, now_ms);
}

void collection_sensor_policy_feed_gnss_result(
    collection_sensor_policy_t *policy,
    bool fix,
    bool no_fix,
    uint64_t now_ms)
{
    if (policy == NULL || !policy->initialized) {
        return;
    }

    if (fix) {
        policy->gnss_state = EGOLINK_LOCATION_POLICY_GNSS_FIX;
        policy->last_gnss_fix_ms = now_ms;
        reevaluate_locked(policy, EGOLINK_LOCATION_POLICY_EVENT_GNSS_FIX, now_ms);
    } else if (no_fix) {
        policy->gnss_state = EGOLINK_LOCATION_POLICY_GNSS_NO_FIX;
        reevaluate_locked(policy, EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX, now_ms);
    } else {
        policy->gnss_state = EGOLINK_LOCATION_POLICY_GNSS_IDLE;
        reevaluate_locked(policy, EGOLINK_LOCATION_POLICY_EVENT_TICK, now_ms);
    }
}

void collection_sensor_policy_feed_cell_result(
    collection_sensor_policy_t *policy,
    bool observed,
    uint64_t now_ms)
{
    if (policy == NULL || !policy->initialized) {
        return;
    }
    if (observed) {
        reevaluate_locked(policy, EGOLINK_LOCATION_POLICY_EVENT_CELL_OBSERVATION, now_ms);
    } else {
        reevaluate_locked(policy, EGOLINK_LOCATION_POLICY_EVENT_TICK, now_ms);
    }
}

void collection_sensor_policy_tick(
    collection_sensor_policy_t *policy,
    uint64_t now_ms)
{
    if (policy == NULL || !policy->initialized) {
        return;
    }
    reevaluate_locked(policy, EGOLINK_LOCATION_POLICY_EVENT_TICK, now_ms);
}

collection_sensor_policy_snapshot_t collection_sensor_policy_snapshot(
    const collection_sensor_policy_t *policy)
{
    if (policy == NULL) {
        collection_sensor_policy_snapshot_t empty = {0};
        return empty;
    }
    return policy->snapshot;
}

bool collection_sensor_policy_consume_immediate_gnss(
    collection_sensor_policy_t *policy)
{
    if (policy == NULL) {
        return false;
    }
    bool trigger = policy->snapshot.immediate_gnss_trigger;
    policy->snapshot.immediate_gnss_trigger = false;
    return trigger;
}

const char *collection_sensor_policy_mode_name(egolink_location_policy_mode_t mode)
{
    switch (mode) {
    case EGOLINK_LOCATION_POLICY_STABLE:
        return "stable";
    case EGOLINK_LOCATION_POLICY_MOVING:
        return "moving";
    case EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN:
        return "location_uncertain";
    case EGOLINK_LOCATION_POLICY_SOS:
        return "sos";
    case EGOLINK_LOCATION_POLICY_LOW_BATTERY:
        return "low_battery";
    default:
        return "unknown";
    }
}

const char *collection_sensor_policy_mobility_name(egolink_location_policy_mobility_t mobility)
{
    switch (mobility) {
    case EGOLINK_LOCATION_POLICY_MOBILITY_STABLE:
        return "stable";
    case EGOLINK_LOCATION_POLICY_MOBILITY_MOVING:
        return "moving";
    case EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN:
    default:
        return "unknown";
    }
}

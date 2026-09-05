#ifndef EGOLINK_LOCATION_POLICY_CORE_H
#define EGOLINK_LOCATION_POLICY_CORE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_LOCATION_POLICY_CONFIG_CONTRACT_VERSION \
    "egolink.sensor_policy_config.v0.1"
#define EGOLINK_LOCATION_POLICY_SEMANTIC_VERSION \
    "egolink.sensor_policy.semantic.v0.1"
#define EGOLINK_LOCATION_POLICY_CONFIG_ID \
    "p0-sprint1-engineering-default-20260823"
#define EGOLINK_LOCATION_POLICY_CONFIG_HASH \
    "c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d"
#define EGOLINK_LOCATION_POLICY_PROVENANCE \
    "engineering_default_unverified"

typedef enum {
    EGOLINK_LOCATION_POLICY_STABLE = 0,
    EGOLINK_LOCATION_POLICY_MOVING,
    EGOLINK_LOCATION_POLICY_LOCATION_UNCERTAIN,
    EGOLINK_LOCATION_POLICY_SOS,
    EGOLINK_LOCATION_POLICY_LOW_BATTERY,
} egolink_location_policy_mode_t;

typedef enum {
    EGOLINK_LOCATION_POLICY_MOBILITY_STABLE = 0,
    EGOLINK_LOCATION_POLICY_MOBILITY_MOVING,
    EGOLINK_LOCATION_POLICY_MOBILITY_UNKNOWN,
} egolink_location_policy_mobility_t;

typedef enum {
    EGOLINK_LOCATION_POLICY_GNSS_IDLE = 0,
    EGOLINK_LOCATION_POLICY_GNSS_ACQUIRING,
    EGOLINK_LOCATION_POLICY_GNSS_FIX,
    EGOLINK_LOCATION_POLICY_GNSS_NO_FIX,
    EGOLINK_LOCATION_POLICY_GNSS_FIX_REJECTED,
    EGOLINK_LOCATION_POLICY_GNSS_ERROR,
    EGOLINK_LOCATION_POLICY_GNSS_UNAVAILABLE,
} egolink_location_policy_gnss_state_t;

typedef enum {
    EGOLINK_LOCATION_POLICY_BATTERY_NORMAL = 0,
    EGOLINK_LOCATION_POLICY_BATTERY_LOW,
    EGOLINK_LOCATION_POLICY_BATTERY_CRITICAL,
    EGOLINK_LOCATION_POLICY_BATTERY_CHARGING,
    EGOLINK_LOCATION_POLICY_BATTERY_UNKNOWN,
} egolink_location_policy_battery_state_t;

typedef enum {
    EGOLINK_LOCATION_POLICY_BELIEF_FINE = 0,
    EGOLINK_LOCATION_POLICY_BELIEF_COARSE,
    EGOLINK_LOCATION_POLICY_BELIEF_PREDICTED,
    EGOLINK_LOCATION_POLICY_BELIEF_UNKNOWN,
} egolink_location_policy_belief_t;

/*
 * Raw IMU samples are intentionally outside this component. An upstream
 * bounded window/rule implementation emits the normalized MOBILITY event.
 */
typedef enum {
    EGOLINK_LOCATION_POLICY_EVENT_TICK = 0,
    EGOLINK_LOCATION_POLICY_EVENT_MOBILITY,
    EGOLINK_LOCATION_POLICY_EVENT_GNSS_STARTED,
    EGOLINK_LOCATION_POLICY_EVENT_GNSS_STOPPED,
    EGOLINK_LOCATION_POLICY_EVENT_GNSS_FIX,
    EGOLINK_LOCATION_POLICY_EVENT_GNSS_NO_FIX,
    EGOLINK_LOCATION_POLICY_EVENT_GNSS_ERROR,
    EGOLINK_LOCATION_POLICY_EVENT_COARSE_LOCATION,
    EGOLINK_LOCATION_POLICY_EVENT_LTE_STATE,
    EGOLINK_LOCATION_POLICY_EVENT_CELL_OBSERVATION,
    EGOLINK_LOCATION_POLICY_EVENT_BATTERY,
    EGOLINK_LOCATION_POLICY_EVENT_SOS,
} egolink_location_policy_event_type_t;

typedef enum {
    EGOLINK_LOCATION_POLICY_GNSS_ACTION_START = 0,
    EGOLINK_LOCATION_POLICY_GNSS_ACTION_CONTINUE,
    EGOLINK_LOCATION_POLICY_GNSS_ACTION_STOP_TIMEOUT,
    EGOLINK_LOCATION_POLICY_GNSS_ACTION_WAIT_BACKOFF,
    EGOLINK_LOCATION_POLICY_GNSS_ACTION_WAIT_INTERVAL,
} egolink_location_policy_gnss_action_t;

typedef enum {
    EGOLINK_LOCATION_POLICY_CELL_ACTION_OBSERVE = 0,
    EGOLINK_LOCATION_POLICY_CELL_ACTION_CONTINUE,
    EGOLINK_LOCATION_POLICY_CELL_ACTION_TIMEOUT,
    EGOLINK_LOCATION_POLICY_CELL_ACTION_WAIT_BACKOFF,
    EGOLINK_LOCATION_POLICY_CELL_ACTION_WAIT_INTERVAL,
} egolink_location_policy_cell_action_t;

typedef enum {
    EGOLINK_LOCATION_POLICY_OK = 0,
    EGOLINK_LOCATION_POLICY_INVALID_ARGUMENT,
    EGOLINK_LOCATION_POLICY_INVALID_CONFIG,
    EGOLINK_LOCATION_POLICY_INVALID_RUNTIME,
    EGOLINK_LOCATION_POLICY_INVALID_SNAPSHOT,
    EGOLINK_LOCATION_POLICY_INVALID_EVENT,
    EGOLINK_LOCATION_POLICY_TIME_REGRESSION,
    EGOLINK_LOCATION_POLICY_DEADLINE_OVERFLOW,
    EGOLINK_LOCATION_POLICY_NOT_INITIALIZED,
} egolink_location_policy_result_t;

typedef struct {
    uint64_t gnss_interval_ms;
    uint64_t cell_interval_ms;
    double imu_rate_hz;
    bool lte_keep_connected;
} egolink_location_policy_schedule_config_t;

typedef struct {
    uint64_t acquisition_timeout_ms;
    uint64_t retry_backoff_ms;
    double retry_backoff_multiplier;
    uint64_t max_retry_backoff_ms;
} egolink_location_policy_gnss_config_t;

typedef struct {
    uint64_t request_timeout_ms;
    uint64_t retry_backoff_ms;
    double retry_backoff_multiplier;
    uint64_t max_retry_backoff_ms;
} egolink_location_policy_cell_config_t;

typedef struct {
    uint64_t window_ms;
    uint32_t min_samples;
    double enter_rms_m_s2;
    double exit_rms_m_s2;
    uint32_t enter_windows;
    uint32_t exit_windows;
    uint64_t evidence_stale_after_ms;
} egolink_location_policy_movement_config_t;

typedef struct {
    double fine_max_accuracy_m;
    double fine_max_hdop;
    double hdop_uncertainty_multiplier_m;
    double coarse_max_uncertainty_m;
    uint64_t fine_freshness_ms;
    uint64_t coarse_freshness_ms;
    uint64_t prediction_horizon_ms;
    double uncertainty_growth_mps;
    double uncertain_threshold_m;
    double fine_initial_confidence;
    double coarse_initial_confidence;
    double predicted_min_confidence;
} egolink_location_policy_location_config_t;

typedef struct {
    double enter_percent;
    double exit_percent;
    double critical_percent;
    egolink_location_policy_schedule_config_t schedule;
} egolink_location_policy_low_battery_config_t;

typedef struct {
    bool gnss_immediate;
    uint64_t gnss_retry_interval_ms;
    uint64_t gnss_acquisition_timeout_ms;
    uint64_t cell_interval_ms;
    double imu_rate_hz;
    bool lte_keep_connected;
    bool upload_last_trusted;
    bool start_ego_call;
} egolink_location_policy_sos_config_t;

/*
 * This first device slice accepts exactly one build-time frozen profile whose
 * identity/hash are declared above; it is not a runtime JSON/config loader. A
 * changed numeric value requires a new reviewed identity/hash and generated
 * validator; it cannot retain this hash.
 */
typedef struct {
    const char *contract_version;
    const char *semantic_validation;
    const char *config_id;
    const char *config_hash;
    const char *provenance;
    egolink_location_policy_schedule_config_t stationary;
    egolink_location_policy_schedule_config_t moving;
    egolink_location_policy_schedule_config_t location_uncertain;
    egolink_location_policy_gnss_config_t gnss;
    egolink_location_policy_cell_config_t cell;
    egolink_location_policy_movement_config_t movement;
    egolink_location_policy_location_config_t location;
    egolink_location_policy_low_battery_config_t low_battery;
    egolink_location_policy_sos_config_t sos;
} egolink_location_policy_config_t;

typedef struct {
    uint64_t event_time_ms;
    egolink_location_policy_mobility_t mobility_state;
    egolink_location_policy_gnss_state_t gnss_state;
    egolink_location_policy_battery_state_t battery_state;
    bool battery_percent_available;
    double battery_percent;
    bool sos_active;
    egolink_location_policy_belief_t location_belief;
    bool location_uncertainty_available;
    double location_uncertainty_m;
    bool last_trusted_time_available;
    uint64_t last_trusted_time_ms;
} egolink_location_policy_snapshot_t;

typedef struct {
    egolink_location_policy_event_type_t type;
    uint64_t event_time_ms;
    /* Required for the same policy-action/capture-bound events as the host. */
    bool attributable_lineage;
} egolink_location_policy_event_t;

typedef struct {
    bool sos_active;
    bool low_battery;
    bool critical_battery;
    bool location_uncertain;
    bool moving;
} egolink_location_policy_conditions_t;

typedef struct {
    bool initialized;
    egolink_location_policy_mode_t mode;
    bool last_evaluation_available;
    uint64_t last_evaluation_ms;
    bool low_battery_latched;
    egolink_location_policy_mobility_t observed_mobility_state;
    bool last_mobility_observation_available;
    uint64_t last_mobility_observation_ms;
    bool last_gnss_attempt_available;
    uint64_t last_gnss_attempt_ms;
    bool gnss_acquisition_started_available;
    uint64_t gnss_acquisition_started_ms;
    uint32_t consecutive_no_fix;
    bool retry_not_before_available;
    uint64_t retry_not_before_ms;
    bool last_cell_action_available;
    uint64_t last_cell_action_ms;
    bool cell_request_started_available;
    uint64_t cell_request_started_ms;
    uint32_t consecutive_cell_timeouts;
    bool cell_retry_not_before_available;
    uint64_t cell_retry_not_before_ms;
} egolink_location_policy_runtime_t;

typedef struct {
    const char *config_id;
    const char *config_hash;
    egolink_location_policy_mode_t policy_mode;
    egolink_location_policy_mobility_t derived_mobility_state;
    egolink_location_policy_conditions_t conditions;
    egolink_location_policy_mode_t transition_from;
    egolink_location_policy_mode_t transition_to;
    bool transition_changed;
    double imu_rate_hz;
    egolink_location_policy_gnss_action_t gnss_action;
    uint64_t gnss_acquisition_timeout_ms;
    bool gnss_retry_not_before_available;
    uint64_t gnss_retry_not_before_ms;
    egolink_location_policy_cell_action_t cell_action;
    bool cell_observe_now;
    uint64_t cell_interval_ms;
    uint64_t cell_request_timeout_ms;
    bool cell_retry_not_before_available;
    uint64_t cell_retry_not_before_ms;
    bool lte_keep_connected;
    bool upload_location_now;
    bool upload_last_trusted_now;
    bool start_ego_call_now;
    bool camera_requested;
    bool next_evaluation_available;
    uint64_t next_evaluation_ms;
    egolink_location_policy_runtime_t runtime;
} egolink_location_policy_decision_t;

typedef struct {
    bool initialized;
    egolink_location_policy_config_t config;
    egolink_location_policy_runtime_t runtime;
} egolink_location_policy_core_t;

void egolink_location_policy_default_config(
    egolink_location_policy_config_t *output);

egolink_location_policy_result_t egolink_location_policy_validate_config(
    const egolink_location_policy_config_t *config);

egolink_location_policy_result_t egolink_location_policy_init(
    egolink_location_policy_core_t *core,
    const egolink_location_policy_config_t *config);

/*
 * Evaluation is transactional: core changes only after a complete decision.
 * On failure, decision is cleared and the prior core remains intact.
 *
 * This stateful core is not reentrant and intentionally has no event identity
 * or duplicate guard, matching the frozen host policy. The caller must
 * serialize evaluations and deduplicate reconnect/replay input by its complete
 * boot/session/stream/sequence lineage before calling. Repeating the same
 * event type and event_time_ms is otherwise a new evaluation and may advance
 * retry counters again; this API does not provide exactly-once processing.
 */
egolink_location_policy_result_t egolink_location_policy_evaluate(
    egolink_location_policy_core_t *core,
    const egolink_location_policy_snapshot_t *snapshot,
    const egolink_location_policy_event_t *event,
    egolink_location_policy_decision_t *decision);

const char *egolink_location_policy_result_name(
    egolink_location_policy_result_t result);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_LOCATION_POLICY_CORE_H */

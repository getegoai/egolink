#ifndef EGOLINK_LOCATION_ENGINE_CORE_H
#define EGOLINK_LOCATION_ENGINE_CORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_LOCATION_ENGINE_CORE_CONTRACT_VERSION \
    "egolink.location_engine.v0.1"
#define EGOLINK_LOCATION_ENGINE_CORE_PROFILE_ID \
    "p0-sprint1-engineering-default-20260823"
#define EGOLINK_LOCATION_ENGINE_CORE_PROFILE_HASH \
    "c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d"
#define EGOLINK_LOCATION_ENGINE_CORE_PROFILE_PROVENANCE \
    "engineering_default_unverified"

#define EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES 256U
#define EGOLINK_LOCATION_ENGINE_CORE_RULE_BASIS_MAX_COUNT 16U
#define EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_COUNT 8U
#define EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_BYTES 128U
#define EGOLINK_LOCATION_ENGINE_CORE_JSON_MAX_BYTES 4096U

typedef struct {
    const char *data;
    size_t length;
} egolink_location_engine_text_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_EVENT_TICK = 0,
    EGOLINK_LOCATION_ENGINE_EVENT_IMU_SAMPLE,
    EGOLINK_LOCATION_ENGINE_EVENT_MOBILITY,
    EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STARTED,
    EGOLINK_LOCATION_ENGINE_EVENT_GNSS_STOPPED,
    EGOLINK_LOCATION_ENGINE_EVENT_GNSS_NO_FIX,
    EGOLINK_LOCATION_ENGINE_EVENT_GNSS_ERROR,
    EGOLINK_LOCATION_ENGINE_EVENT_GNSS_FIX,
    EGOLINK_LOCATION_ENGINE_EVENT_COARSE_LOCATION,
    EGOLINK_LOCATION_ENGINE_EVENT_LTE_STATE,
    EGOLINK_LOCATION_ENGINE_EVENT_CELL_OBSERVATION,
    EGOLINK_LOCATION_ENGINE_EVENT_BATTERY,
    EGOLINK_LOCATION_ENGINE_EVENT_SOS,
    EGOLINK_LOCATION_ENGINE_EVENT_COUNT,
} egolink_location_engine_event_type_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_MOBILITY_STABLE = 0,
    EGOLINK_LOCATION_ENGINE_MOBILITY_MOVING,
    EGOLINK_LOCATION_ENGINE_MOBILITY_UNKNOWN,
    EGOLINK_LOCATION_ENGINE_MOBILITY_COUNT,
} egolink_location_engine_mobility_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_GNSS_IDLE = 0,
    EGOLINK_LOCATION_ENGINE_GNSS_ACQUIRING,
    EGOLINK_LOCATION_ENGINE_GNSS_FIX,
    EGOLINK_LOCATION_ENGINE_GNSS_NO_FIX,
    EGOLINK_LOCATION_ENGINE_GNSS_FIX_REJECTED,
    EGOLINK_LOCATION_ENGINE_GNSS_ERROR,
    EGOLINK_LOCATION_ENGINE_GNSS_UNAVAILABLE,
    EGOLINK_LOCATION_ENGINE_GNSS_COUNT,
} egolink_location_engine_gnss_state_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_LTE_OFFLINE = 0,
    EGOLINK_LOCATION_ENGINE_LTE_ONLINE,
    EGOLINK_LOCATION_ENGINE_LTE_LIMITED,
    EGOLINK_LOCATION_ENGINE_LTE_UNAVAILABLE,
    EGOLINK_LOCATION_ENGINE_LTE_UNKNOWN,
    EGOLINK_LOCATION_ENGINE_LTE_COUNT,
} egolink_location_engine_lte_state_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_BATTERY_NORMAL = 0,
    EGOLINK_LOCATION_ENGINE_BATTERY_LOW,
    EGOLINK_LOCATION_ENGINE_BATTERY_CRITICAL,
    EGOLINK_LOCATION_ENGINE_BATTERY_CHARGING,
    EGOLINK_LOCATION_ENGINE_BATTERY_UNKNOWN,
    EGOLINK_LOCATION_ENGINE_BATTERY_COUNT,
} egolink_location_engine_battery_state_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_POLICY_STABLE = 0,
    EGOLINK_LOCATION_ENGINE_POLICY_MOVING,
    EGOLINK_LOCATION_ENGINE_POLICY_LOCATION_UNCERTAIN,
    EGOLINK_LOCATION_ENGINE_POLICY_SOS,
    EGOLINK_LOCATION_ENGINE_POLICY_LOW_BATTERY,
    EGOLINK_LOCATION_ENGINE_POLICY_COUNT,
} egolink_location_engine_policy_state_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_BELIEF_FINE = 0,
    EGOLINK_LOCATION_ENGINE_BELIEF_COARSE,
    EGOLINK_LOCATION_ENGINE_BELIEF_PREDICTED,
    EGOLINK_LOCATION_ENGINE_BELIEF_UNKNOWN,
    EGOLINK_LOCATION_ENGINE_BELIEF_COUNT,
} egolink_location_engine_belief_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_SOURCE_GNSS = 0,
    EGOLINK_LOCATION_ENGINE_SOURCE_CELL_REFERENCE,
    EGOLINK_LOCATION_ENGINE_SOURCE_WIFI_REFERENCE,
    EGOLINK_LOCATION_ENGINE_SOURCE_KNOWN_PLACE,
    EGOLINK_LOCATION_ENGINE_SOURCE_LAST_TRUSTED,
    EGOLINK_LOCATION_ENGINE_SOURCE_NONE,
    EGOLINK_LOCATION_ENGINE_SOURCE_COUNT,
} egolink_location_engine_source_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_UNCERTAINTY_SOURCE_REPORTED_ACCURACY = 0,
    EGOLINK_LOCATION_ENGINE_UNCERTAINTY_HDOP_RULE_HEURISTIC_V0,
    EGOLINK_LOCATION_ENGINE_UNCERTAINTY_REFERENCE_BOUND,
    EGOLINK_LOCATION_ENGINE_UNCERTAINTY_LAST_TRUSTED_AGE_GROWTH_RULE_V0,
    EGOLINK_LOCATION_ENGINE_UNCERTAINTY_UNAVAILABLE,
    EGOLINK_LOCATION_ENGINE_UNCERTAINTY_COUNT,
} egolink_location_engine_uncertainty_basis_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_OBSERVED = 0,
    EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_VERIFIED,
    EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_RULE_DERIVED,
    EGOLINK_LOCATION_ENGINE_SOURCE_STATUS_COUNT,
} egolink_location_engine_source_status_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_TIME_GNSS_SOURCE_UTC_NS = 0,
    EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_UTC_NS,
    EGOLINK_LOCATION_ENGINE_TIME_TIMESTAMP_MONOTONIC_NS,
    EGOLINK_LOCATION_ENGINE_TIME_POLICY_RULE_V0,
    EGOLINK_LOCATION_ENGINE_TIME_POLICY_TIMER_V0,
    EGOLINK_LOCATION_ENGINE_TIME_POLICY_ACTION_V0,
    EGOLINK_LOCATION_ENGINE_TIME_COUNT,
} egolink_location_engine_time_source_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_OK = 0,
    EGOLINK_LOCATION_ENGINE_INVALID_ARGUMENT,
    EGOLINK_LOCATION_ENGINE_INVALID_CONFIG,
    EGOLINK_LOCATION_ENGINE_NOT_INITIALIZED,
    EGOLINK_LOCATION_ENGINE_INVALID_EVENT,
    EGOLINK_LOCATION_ENGINE_INVALID_LINEAGE,
    EGOLINK_LOCATION_ENGINE_INVALID_MEASUREMENT,
    EGOLINK_LOCATION_ENGINE_TIME_REGRESSION,
    EGOLINK_LOCATION_ENGINE_NUMERIC_OVERFLOW,
    EGOLINK_LOCATION_ENGINE_OUTPUT_OVERFLOW,
} egolink_location_engine_result_t;

typedef enum {
    EGOLINK_LOCATION_ENGINE_REASON_NO_OBSERVATION_YET = 0,
    EGOLINK_LOCATION_ENGINE_REASON_NO_TRUSTED_LOCATION,
    EGOLINK_LOCATION_ENGINE_REASON_POLICY_CLOCK_ADVANCED,
    EGOLINK_LOCATION_ENGINE_REASON_IMU_NO_COORDINATE_DERIVATION,
    EGOLINK_LOCATION_ENGINE_REASON_MOBILITY_STABLE,
    EGOLINK_LOCATION_ENGINE_REASON_MOBILITY_MOVING,
    EGOLINK_LOCATION_ENGINE_REASON_MOBILITY_UNKNOWN,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_ACQUISITION_STARTED,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_ACQUISITION_STOPPED,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_NO_FIX_PRESERVED,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_ERROR_PRESERVED,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_UNTRUSTED_LINEAGE,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_INVALID_MEASUREMENT,
    EGOLINK_LOCATION_ENGINE_REASON_LATITUDE_MUST_BE_NUMERIC,
    EGOLINK_LOCATION_ENGINE_REASON_LATITUDE_MUST_BE_FINITE,
    EGOLINK_LOCATION_ENGINE_REASON_LONGITUDE_MUST_BE_NUMERIC,
    EGOLINK_LOCATION_ENGINE_REASON_LONGITUDE_MUST_BE_FINITE,
    EGOLINK_LOCATION_ENGINE_REASON_ACCURACY_MUST_BE_FINITE,
    EGOLINK_LOCATION_ENGINE_REASON_HDOP_MUST_BE_FINITE,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_COORDINATE_RANGE,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_REPORTED_ACCURACY,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_HDOP_UNCERTAINTY,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_QUALITY_GATE,
    EGOLINK_LOCATION_ENGINE_REASON_GNSS_FIX_ACCEPTED,
    EGOLINK_LOCATION_ENGINE_REASON_COARSE_REFERENCE_ACCEPTED,
    EGOLINK_LOCATION_ENGINE_REASON_LTE_OFFLINE,
    EGOLINK_LOCATION_ENGINE_REASON_LTE_ONLINE,
    EGOLINK_LOCATION_ENGINE_REASON_LTE_LIMITED,
    EGOLINK_LOCATION_ENGINE_REASON_LTE_UNAVAILABLE,
    EGOLINK_LOCATION_ENGINE_REASON_LTE_UNKNOWN,
    EGOLINK_LOCATION_ENGINE_REASON_CELL_NO_COORDINATE_DERIVATION,
    EGOLINK_LOCATION_ENGINE_REASON_BATTERY_NORMAL,
    EGOLINK_LOCATION_ENGINE_REASON_BATTERY_LOW,
    EGOLINK_LOCATION_ENGINE_REASON_BATTERY_CRITICAL,
    EGOLINK_LOCATION_ENGINE_REASON_BATTERY_CHARGING,
    EGOLINK_LOCATION_ENGINE_REASON_BATTERY_UNKNOWN,
    EGOLINK_LOCATION_ENGINE_REASON_SOS_ACTIVE,
    EGOLINK_LOCATION_ENGINE_REASON_SOS_CLEARED,
    EGOLINK_LOCATION_ENGINE_REASON_OBSERVATION_APPLIED,
    EGOLINK_LOCATION_ENGINE_REASON_TRUSTED_LOCATION_FRESH,
    EGOLINK_LOCATION_ENGINE_REASON_UNCERTAINTY_GROWTH_OVERFLOW,
    EGOLINK_LOCATION_ENGINE_REASON_LAST_TRUSTED_MEMORY_ONLY,
    EGOLINK_LOCATION_ENGINE_REASON_LAST_TRUSTED_PRESERVED,
    EGOLINK_LOCATION_ENGINE_REASON_BELIEF_FORCED_PREDICTED,
    EGOLINK_LOCATION_ENGINE_REASON_BELIEF_AGED,
    EGOLINK_LOCATION_ENGINE_REASON_PREDICTION_HORIZON_EXCEEDED,
    EGOLINK_LOCATION_ENGINE_REASON_COUNT,
} egolink_location_engine_reason_t;

/*
 * This profile is a native projection of shared/config/sensor_policy_v0.json.
 * The identity/hash bind these exact values to the already accepted host
 * LocationEngineConfig defaults; retaining the hash while changing a value is
 * rejected. A newly tuned profile needs a newly reviewed identity and hash.
 */
typedef struct {
    const char *profile_id;
    const char *profile_hash;
    const char *provenance;
    double fine_max_accuracy_m;
    double fine_max_hdop;
    double hdop_uncertainty_multiplier_m;
    double coarse_max_uncertainty_m;
    uint64_t fine_freshness_ms;
    uint64_t coarse_freshness_ms;
    uint64_t prediction_horizon_ms;
    double uncertainty_growth_mps;
    double fine_initial_confidence;
    double coarse_initial_confidence;
    double predicted_min_confidence;
} egolink_location_engine_config_t;

/*
 * A trusted lineage may carry any supported UTC capture lane or the scoped
 * monotonic lane. UTC precedence is GNSS-source UTC, then timestamp UTC, then
 * monotonic, matching the host oracle. Rule-derived lineage is valid only for
 * mobility and GNSS lifecycle assertions and must have at least one unique
 * basis ID. basis_count may exceed the array bound only to request fail-closed
 * rejection; the reducer never reads beyond RULE_BASIS_MAX_COUNT.
 */
typedef struct {
    bool present;
    egolink_location_engine_text_t observation_id;
    egolink_location_engine_source_status_t source_status;
    bool stream_id_present;
    egolink_location_engine_text_t stream_id;
    bool sequence_id_present;
    uint64_t sequence_id;
    bool device_run_id_present;
    egolink_location_engine_text_t device_run_id;
    bool boot_count_present;
    uint64_t boot_count;
    bool gnss_source_utc_ns_present;
    uint64_t gnss_source_utc_ns;
    bool timestamp_utc_ns_present;
    uint64_t timestamp_utc_ns;
    bool timestamp_monotonic_ns_present;
    uint64_t timestamp_monotonic_ns;
    bool monotonic_clock_domain_id_present;
    egolink_location_engine_text_t monotonic_clock_domain_id;
    bool derived_time_source_present;
    egolink_location_engine_time_source_t derived_time_source;
    size_t basis_count;
    egolink_location_engine_text_t
        basis_observation_ids[EGOLINK_LOCATION_ENGINE_CORE_RULE_BASIS_MAX_COUNT];
    /* Models Python's separate lineage/evidence mismatch rejection. */
    bool outer_evidence_source_status_present;
    egolink_location_engine_source_status_t outer_evidence_source_status;
} egolink_location_engine_lineage_t;

typedef struct {
    egolink_location_engine_event_type_t type;
    uint64_t event_time_ms;
    egolink_location_engine_lineage_t lineage;

    bool mobility_state_present;
    egolink_location_engine_mobility_t mobility_state;
    bool lte_state_present;
    egolink_location_engine_lte_state_t lte_state;
    bool battery_state_present;
    egolink_location_engine_battery_state_t battery_state;
    bool battery_percent_present;
    double battery_percent;
    bool sos_active_present;
    bool sos_active;

    bool latitude_deg_present;
    double latitude_deg;
    bool longitude_deg_present;
    double longitude_deg;
    bool accuracy_m_present;
    double accuracy_m;
    bool hdop_present;
    double hdop;
    bool uncertainty_m_present;
    double uncertainty_m;
    bool coarse_source_present;
    egolink_location_engine_source_t coarse_source;
    bool reference_id_present;
    egolink_location_engine_text_t reference_id;
} egolink_location_engine_observation_t;

typedef struct {
    char data[EGOLINK_LOCATION_ENGINE_CORE_TEXT_MAX_BYTES + 1U];
    size_t length;
} egolink_location_engine_owned_text_t;

typedef struct {
    egolink_location_engine_owned_text_t observation_id;
    egolink_location_engine_source_status_t source_status;
    bool stream_id_present;
    egolink_location_engine_owned_text_t stream_id;
    bool sequence_id_present;
    uint64_t sequence_id;
    bool device_run_id_present;
    egolink_location_engine_owned_text_t device_run_id;
    bool boot_count_present;
    uint64_t boot_count;
    uint64_t event_time_ms;
    egolink_location_engine_time_source_t event_time_source;
    uint64_t capture_time_ns;
    bool monotonic_clock_domain_id_present;
    egolink_location_engine_owned_text_t monotonic_clock_domain_id;
    bool reference_id_present;
    egolink_location_engine_owned_text_t reference_id;
} egolink_location_engine_evidence_ref_t;

typedef struct {
    double latitude_deg;
    double longitude_deg;
    bool accuracy_m_present;
    double accuracy_m;
    double uncertainty_at_fix_m;
    egolink_location_engine_uncertainty_basis_t uncertainty_basis;
    egolink_location_engine_source_t source;
    egolink_location_engine_evidence_ref_t evidence_ref;
} egolink_location_engine_trusted_location_t;

typedef struct {
    egolink_location_engine_reason_t
        values[EGOLINK_LOCATION_ENGINE_CORE_REASON_MAX_COUNT];
    size_t count;
} egolink_location_engine_reasons_t;

typedef struct {
    uint64_t event_time_ms;
    egolink_location_engine_event_type_t last_event_type;
    bool last_event_initialized;
    egolink_location_engine_mobility_t mobility_state;
    egolink_location_engine_gnss_state_t gnss_state;
    egolink_location_engine_lte_state_t lte_state;
    bool last_trusted_location_present;
    egolink_location_engine_trusted_location_t last_trusted_location;
    bool last_trusted_time_present;
    uint64_t last_trusted_time_ms;
    egolink_location_engine_belief_t location_belief;
    bool location_accuracy_m_present;
    double location_accuracy_m;
    bool location_accuracy_source_reported;
    double location_confidence;
    egolink_location_engine_source_t location_source;
    bool location_uncertainty_m_present;
    double location_uncertainty_m;
    egolink_location_engine_uncertainty_basis_t location_uncertainty_basis;
    egolink_location_engine_battery_state_t battery_state;
    bool battery_percent_present;
    double battery_percent;
    egolink_location_engine_policy_state_t sensor_policy_state;
    bool sos_active;
    egolink_location_engine_reasons_t reason_codes;
} egolink_location_engine_snapshot_t;

typedef struct {
    bool initialized;
    egolink_location_engine_config_t config;
    bool last_event_time_present;
    uint64_t last_event_time_ms;
    bool last_event_initialized;
    egolink_location_engine_event_type_t last_event_type;
    egolink_location_engine_reasons_t last_reason_codes;
    egolink_location_engine_mobility_t mobility_state;
    egolink_location_engine_gnss_state_t gnss_state;
    egolink_location_engine_lte_state_t lte_state;
    egolink_location_engine_battery_state_t battery_state;
    bool battery_percent_present;
    double battery_percent;
    egolink_location_engine_policy_state_t sensor_policy_state;
    bool sos_active;
    bool last_trusted_location_present;
    egolink_location_engine_trusted_location_t last_trusted_location;
    bool last_trusted_time_present;
    uint64_t last_trusted_time_ms;
    egolink_location_engine_belief_t last_trusted_belief;
    bool force_predicted;
} egolink_location_engine_core_t;

void egolink_location_engine_default_config(
    egolink_location_engine_config_t *output);

egolink_location_engine_result_t egolink_location_engine_validate_config(
    const egolink_location_engine_config_t *config);

egolink_location_engine_result_t egolink_location_engine_init(
    egolink_location_engine_core_t *core,
    const egolink_location_engine_config_t *config);

egolink_location_engine_result_t egolink_location_engine_set_policy_context(
    egolink_location_engine_core_t *core,
    egolink_location_engine_policy_state_t policy_state);

/*
 * Processing is transactional. Rejected observations clear output and leave
 * the prior reducer byte-for-byte unchanged. Equal event_time_ms is accepted,
 * exactly as in the host reducer; this stateful API has no event identity and
 * does not provide exactly-once processing. The caller must serialize calls
 * and deduplicate reconnect/replay input using complete boot/session/stream/
 * sequence lineage before invoking the reducer.
 */
egolink_location_engine_result_t egolink_location_engine_process(
    egolink_location_engine_core_t *core,
    const egolink_location_engine_observation_t *observation,
    egolink_location_engine_snapshot_t *output);

/* A supplied time must not precede the latest event. */
egolink_location_engine_result_t egolink_location_engine_snapshot(
    const egolink_location_engine_core_t *core,
    bool event_time_ms_present,
    uint64_t event_time_ms,
    egolink_location_engine_snapshot_t *output);

/*
 * Serializes the exact bounded Location Engine v0 object consumed by
 * location_state_emitter. output is caller-owned, NUL-terminated on success,
 * and cleared (up to JSON_MAX_BYTES + NUL) on every failure. output_length
 * excludes the NUL and is zero on failure.
 */
egolink_location_engine_result_t egolink_location_engine_serialize_snapshot(
    const egolink_location_engine_snapshot_t *snapshot,
    char *output,
    size_t output_capacity,
    size_t *output_length);

const char *egolink_location_engine_result_name(
    egolink_location_engine_result_t result);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_LOCATION_ENGINE_CORE_H */

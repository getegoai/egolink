#ifndef EGOLINK_LOCATION_HARDWARE_ADAPTER_H
#define EGOLINK_LOCATION_HARDWARE_ADAPTER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "device_location_runtime.h"
#include "platform_imu.h"
#include "sim7670_gnss.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_LOCATION_HARDWARE_ADAPTER_CONTRACT_VERSION \
    "egolink.location_hardware_adapter.v0.1"
#define EGOLINK_LOCATION_HARDWARE_ADAPTER_CONTEXT_BYTES 1024U

/*
 * There is intentionally no receive-time field here. The caller must provide
 * the source capture time and every boot/session/stream/observation identity
 * field. map_* validates and copies them; it never samples a clock or invents
 * a sequence. It accepts an explicit boot-monotonic capture lane, or a UTC
 * capture mapped by the owner with a fixed clock anchor (no monotonic domain
 * in that lane). It does not claim receiver GNSS UTC. source_event_time_ms
 * must equal source_event_time_ns /
 * 1,000,000.
 */
typedef struct {
    egolink_location_runtime_text_t device_id;
    uint64_t boot_count;
    egolink_location_runtime_text_t session_id;
    egolink_location_runtime_text_t stream_id;
    uint64_t sequence_id;
    egolink_location_runtime_text_t observation_id;
    uint64_t source_event_time_ms;
    uint64_t source_event_time_ns;
    egolink_location_event_time_source_t source_event_time_source;
    egolink_location_runtime_text_t monotonic_clock_domain_id;
    egolink_location_runtime_publish_intent_t publish_intent;
} egolink_location_hardware_identity_t;

typedef enum {
    EGOLINK_LOCATION_HARDWARE_ORIGIN_NONE = 0,
    EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_FIX_CANDIDATE,
    EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_UNVERIFIED_RESULT,
    EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_DRIVER_DISABLED,
    EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_DRIVER_ERROR,
    EGOLINK_LOCATION_HARDWARE_ORIGIN_LTE_STATE,
    EGOLINK_LOCATION_HARDWARE_ORIGIN_CELL_OBSERVATION,
    EGOLINK_LOCATION_HARDWARE_ORIGIN_IMU_REAL,
    EGOLINK_LOCATION_HARDWARE_ORIGIN_BATTERY_CALLER_SUPPLIED,
    EGOLINK_LOCATION_HARDWARE_ORIGIN_GNSS_NO_FIX_OBSERVED,
} egolink_location_hardware_origin_t;

typedef enum {
    EGOLINK_LOCATION_HARDWARE_MAP_OK = 0,
    EGOLINK_LOCATION_HARDWARE_MAP_INVALID_ARGUMENT,
    EGOLINK_LOCATION_HARDWARE_MAP_INVALID_IDENTITY,
    EGOLINK_LOCATION_HARDWARE_MAP_INVALID_REPORT,
    EGOLINK_LOCATION_HARDWARE_MAP_FIX_QUALITY_UNAVAILABLE,
    EGOLINK_LOCATION_HARDWARE_MAP_CELL_ID_UNAVAILABLE,
    EGOLINK_LOCATION_HARDWARE_MAP_MOCK_REJECTED,
    EGOLINK_LOCATION_HARDWARE_MAP_SOURCE_TIME_MISMATCH,
} egolink_location_hardware_map_status_t;

/*
 * The input's text views point into this same object. Do not byte-copy or move
 * it after a successful map; pass &mapped.input synchronously to the runtime.
 * No raw modem response, IP address, IMU vector or battery source is retained.
 */
typedef struct {
    egolink_location_runtime_input_t input;
    egolink_location_hardware_origin_t origin;
    char device_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    char session_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    char stream_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    char observation_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    char monotonic_clock_domain_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
    char cell_reference_id[EGOLINK_LOCATION_RUNTIME_ID_CAPACITY];
} egolink_location_hardware_mapped_input_t;

/*
 * A fix becomes only a candidate for Location Engine validation when the
 * SIM7670 report is internally consistent, coordinates are explicitly valid,
 * finite and in range. Missing/zero HDOP stays absent so the core can report
 * FIX_REJECTED without manufacturing accuracy or reporting NO_FIX. The adapter
 * has no reported-accuracy input and therefore never manufactures one.
 * A non-fix becomes GNSS_NO_FIX only when a complete CGNSSINFO/CGPSINFO
 * response was observed and its parser recognized the explicit empty-fix
 * grammar. Timeout, truncation and malformed responses remain GNSS_ERROR.
 * Disabled, no-fix, unverified-result and driver-error inputs contain no
 * coordinate fields and cannot overwrite last-trusted location.
 */
egolink_location_hardware_map_status_t
egolink_location_hardware_map_gnss(
    const egolink_location_hardware_identity_t *identity,
    const sim7670_gnss_report_t *report,
    egolink_location_hardware_mapped_input_t *mapped);

/*
 * Maps only connectivity states proven by the matching parsed query. Missing
 * core query evidence maps to UNKNOWN; driver/UART/AT failure maps to
 * UNAVAILABLE. It never emits a coordinate.
 */
egolink_location_hardware_map_status_t
egolink_location_hardware_map_lte_state(
    const egolink_location_hardware_identity_t *identity,
    const sim7670_lte_report_t *report,
    egolink_location_hardware_mapped_input_t *mapped);

/*
 * A cell observation requires an internally consistent online report and all
 * MCC/MNC/TAC/cell IDs. TAC and cell ID are canonicalized to lowercase before
 * hashing. The raw identifiers plus exact device scope are domain-separated
 * and reduced to `cell:v1:<40 lowercase hex>` (the first 160 bits of SHA-256);
 * raw IDs are not retained in the mapped input. This is only a stable,
 * device-scoped pseudonymous fingerprint: it is not keyed, anonymous or
 * resistant to dictionary recovery, and must not leave the controlled
 * location-evidence domain. No cell coordinate/radius/accuracy is inferred.
 */
egolink_location_hardware_map_status_t
egolink_location_hardware_map_cell(
    const egolink_location_hardware_identity_t *identity,
    const sim7670_lte_report_t *report,
    egolink_location_hardware_mapped_input_t *mapped);

/*
 * Only direct non-mock `qmi8658_i2c` samples are admitted; false mock flags
 * paired with mock/unknown/custom provenance fail closed. Their source time
 * must use the boot-monotonic domain and exactly match
 * platform_imu_sample_t.uptime_ms at millisecond precision. Raw vectors do
 * not become location or mobility. The string/flag check is consistency
 * validation, not unforgeable attestation; callers must supply the direct
 * result of platform_imu_sample_real, not a hand-built lookalike.
 */
egolink_location_hardware_map_status_t
egolink_location_hardware_map_imu(
    const egolink_location_hardware_identity_t *identity,
    const platform_imu_sample_t *sample,
    egolink_location_hardware_mapped_input_t *mapped);

typedef struct {
    egolink_location_engine_battery_state_t state;
    bool percent_present;
    double percent;
    bool value_is_mock;
} egolink_location_hardware_battery_input_t;

/* Battery is caller supplied; mock values are rejected and no default exists. */
egolink_location_hardware_map_status_t
egolink_location_hardware_map_battery(
    const egolink_location_hardware_identity_t *identity,
    const egolink_location_hardware_battery_input_t *battery,
    egolink_location_hardware_mapped_input_t *mapped);

const char *egolink_location_hardware_map_status_name(
    egolink_location_hardware_map_status_t status);

typedef enum {
    EGOLINK_LOCATION_HARDWARE_ACTION_NEVER_REQUESTED = 0,
    EGOLINK_LOCATION_HARDWARE_ACTION_SUCCEEDED,
    EGOLINK_LOCATION_HARDWARE_ACTION_FAILED,
    EGOLINK_LOCATION_HARDWARE_ACTION_NOT_SUPPORTED,
    EGOLINK_LOCATION_HARDWARE_ACTION_DISABLED,
} egolink_location_hardware_action_status_t;

typedef struct {
    bool enabled;
} egolink_location_hardware_actuator_config_t;

typedef struct {
    bool initialized;
    bool enabled;
    uint64_t action_requests;
    egolink_location_hardware_action_status_t gnss_start;
    egolink_location_hardware_action_status_t gnss_stop;
    egolink_location_hardware_action_status_t cell_observe;
    egolink_location_hardware_action_status_t imu_rate;
    egolink_location_hardware_action_status_t lte_keep_connected;
    egolink_location_hardware_action_status_t upload_intent;
    egolink_location_hardware_action_status_t safe_cancel;
} egolink_location_hardware_actuator_snapshot_t;

typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_LOCATION_HARDWARE_ADAPTER_CONTEXT_BYTES];
} egolink_location_hardware_actuator_t;

/* Produces the deliberately disabled/no-driver configuration. */
void egolink_location_hardware_actuator_default_config(
    egolink_location_hardware_actuator_config_t *config);

/*
 * Initializes every byte without first reading caller storage, so automatic
 * storage need not be pre-zeroed. Calling init again unconditionally replaces
 * the dormant adapter state; the external owner must never do so while its
 * callback table is bound or a callback is running.
 */
bool egolink_location_hardware_actuator_init(
    egolink_location_hardware_actuator_t *actuator,
    const egolink_location_hardware_actuator_config_t *config);

/*
 * Builds the typed callback table consumed by device_location_runtime.
 * Current public hardware APIs do not implement policy-level GNSS start/stop,
 * IMU-rate changes or LTE keep-connected. Those callbacks therefore record
 * NOT_SUPPORTED and return false; they never claim a successful no-op.
 * Cell observation is also NOT_SUPPORTED: the current multi-AT query is
 * synchronous and may not run while the shared location/SOS owner is held.
 * A later modem worker/arbiter must capture its own completion time and basis.
 * upload/cancel have no safe hardware implementation here and likewise fail.
 */
bool egolink_location_hardware_actuator_callbacks(
    egolink_location_hardware_actuator_t *actuator,
    egolink_device_location_runtime_callbacks_t *callbacks);

bool egolink_location_hardware_actuator_snapshot(
    const egolink_location_hardware_actuator_t *actuator,
    egolink_location_hardware_actuator_snapshot_t *snapshot);

const char *egolink_location_hardware_action_status_name(
    egolink_location_hardware_action_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_LOCATION_HARDWARE_ADAPTER_H */

#ifndef EGOLINK_DEVICE_LOCATION_RUNTIME_H
#define EGOLINK_DEVICE_LOCATION_RUNTIME_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "location_runtime_pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_DEVICE_LOCATION_RUNTIME_CONTRACT_VERSION \
    "egolink.device_location_runtime.v0.1"
#define EGOLINK_DEVICE_LOCATION_RUNTIME_CONTEXT_BYTES (10U * 1024U)

typedef enum {
    EGOLINK_DEVICE_LOCATION_RUNTIME_NEVER_INITIALIZED = 0,
    EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED,
    EGOLINK_DEVICE_LOCATION_RUNTIME_ACTIVE,
    EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED,
    EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED,
} egolink_device_location_runtime_lifecycle_t;

typedef enum {
    EGOLINK_DEVICE_LOCATION_RUNTIME_OK = 0,
    EGOLINK_DEVICE_LOCATION_RUNTIME_DUPLICATE_INPUT,
    EGOLINK_DEVICE_LOCATION_RUNTIME_ACTION_PARTIAL_FAILURE,
    EGOLINK_DEVICE_LOCATION_RUNTIME_PIPELINE_RETRY_REQUIRED,
    EGOLINK_DEVICE_LOCATION_RUNTIME_PIPELINE_FAILED,
    EGOLINK_DEVICE_LOCATION_RUNTIME_DISABLED_STATUS,
    EGOLINK_DEVICE_LOCATION_RUNTIME_CANCELLED_STATUS,
    EGOLINK_DEVICE_LOCATION_RUNTIME_CLOSED_STATUS,
    EGOLINK_DEVICE_LOCATION_RUNTIME_INVALID_ARGUMENT,
    EGOLINK_DEVICE_LOCATION_RUNTIME_NOT_INITIALIZED,
    EGOLINK_DEVICE_LOCATION_RUNTIME_ALREADY_INITIALIZED,
    EGOLINK_DEVICE_LOCATION_RUNTIME_DEPENDENCY_MISMATCH,
    EGOLINK_DEVICE_LOCATION_RUNTIME_REENTRANT_CALL,
} egolink_device_location_runtime_status_t;

typedef enum {
    EGOLINK_DEVICE_LOCATION_ACTION_NOT_REQUESTED = 0,
    EGOLINK_DEVICE_LOCATION_ACTION_SUCCEEDED,
    EGOLINK_DEVICE_LOCATION_ACTION_FAILED,
    EGOLINK_DEVICE_LOCATION_ACTION_NOT_CONFIGURED,
} egolink_device_location_action_outcome_t;

typedef enum {
    EGOLINK_DEVICE_LOCATION_CANCEL_EXPLICIT = 0,
    EGOLINK_DEVICE_LOCATION_CANCEL_CLOSE,
} egolink_device_location_cancel_reason_t;

/*
 * Every request borrows the process input identity only for the callback's
 * synchronous duration. It carries no observation payload or coordinate.
 * Callbacks must neither retain a pointer nor recursively enter this runtime,
 * its location adapter, the shared outbox, SOS orchestration, send or ACK.
 */
typedef struct {
    const egolink_location_runtime_identity_t *identity;
    uint64_t acquisition_timeout_ms;
    bool sos_priority;
} egolink_device_location_gnss_start_request_t;

typedef struct {
    const egolink_location_runtime_identity_t *identity;
    bool timeout_stop;
} egolink_device_location_gnss_stop_request_t;

typedef struct {
    const egolink_location_runtime_identity_t *identity;
    uint64_t request_timeout_ms;
    bool sos_priority;
} egolink_device_location_cell_observe_request_t;

typedef struct {
    const egolink_location_runtime_identity_t *identity;
    double rate_hz;
} egolink_device_location_imu_rate_request_t;

typedef struct {
    const egolink_location_runtime_identity_t *identity;
    bool keep_connected;
} egolink_device_location_lte_connection_request_t;

typedef struct {
    const egolink_location_runtime_identity_t *identity;
    const char *event_id;
    const char *payload_sha256;
    size_t payload_length;
    uint32_t publish_reasons;
    bool durable_envelope_present;
    bool sos_priority;
} egolink_device_location_upload_intent_t;

typedef struct {
    egolink_device_location_cancel_reason_t reason;
    bool durable_envelopes_retained;
    bool volatile_uncommitted_observation_may_require_journal_replay;
} egolink_device_location_cancel_request_t;

typedef bool (*egolink_device_location_gnss_start_fn)(
    void *context,
    const egolink_device_location_gnss_start_request_t *request);
typedef bool (*egolink_device_location_gnss_stop_fn)(
    void *context,
    const egolink_device_location_gnss_stop_request_t *request);
typedef bool (*egolink_device_location_cell_observe_fn)(
    void *context,
    const egolink_device_location_cell_observe_request_t *request);
typedef bool (*egolink_device_location_set_imu_rate_fn)(
    void *context,
    const egolink_device_location_imu_rate_request_t *request);
typedef bool (*egolink_device_location_set_lte_keep_connected_fn)(
    void *context,
    const egolink_device_location_lte_connection_request_t *request);
typedef bool (*egolink_device_location_upload_intent_fn)(
    void *context,
    const egolink_device_location_upload_intent_t *request);
typedef bool (*egolink_device_location_safe_cancel_fn)(
    void *context,
    const egolink_device_location_cancel_request_t *request);

typedef struct {
    void *context;
    egolink_device_location_gnss_start_fn gnss_start;
    egolink_device_location_gnss_stop_fn gnss_stop;
    egolink_device_location_cell_observe_fn cell_observe;
    egolink_device_location_set_imu_rate_fn set_imu_rate;
    egolink_device_location_set_lte_keep_connected_fn
        set_lte_keep_connected;
    egolink_device_location_upload_intent_fn upload_intent;
    egolink_device_location_safe_cancel_fn safe_cancel;
} egolink_device_location_runtime_callbacks_t;

typedef struct {
    bool enabled;
    egolink_location_runtime_owner_t pipeline_owner;
    egolink_device_location_runtime_callbacks_t callbacks;
} egolink_device_location_runtime_config_t;

typedef struct {
    egolink_device_location_action_outcome_t gnss_start;
    egolink_device_location_action_outcome_t gnss_stop;
    egolink_device_location_action_outcome_t cell_observe;
    egolink_device_location_action_outcome_t imu_rate;
    egolink_device_location_action_outcome_t lte_keep_connected;
    egolink_device_location_action_outcome_t upload_intent;
} egolink_device_location_action_results_t;

/* No coordinate, observation payload, outbox payload or media is returned. */
typedef struct {
    egolink_device_location_runtime_status_t status;
    egolink_location_runtime_status_t pipeline_status;
    egolink_location_runtime_result_t pipeline_result;
    egolink_device_location_action_results_t actions;
    bool new_input_committed;
    bool durable_envelope_present;
    bool action_failure_after_commit;
} egolink_device_location_runtime_result_t;

typedef struct {
    egolink_device_location_runtime_lifecycle_t lifecycle;
    egolink_device_location_runtime_status_t last_status;
    egolink_location_runtime_status_t last_pipeline_status;
    egolink_device_location_action_results_t last_actions;
    egolink_device_location_action_outcome_t cancel_action;
    bool enabled;
    bool dependency_bound;
    bool busy;
    bool last_input_available;
    uint64_t last_sequence_id;
    uint64_t last_event_time_ms;
    uint64_t process_calls;
    uint64_t committed_inputs;
    uint64_t duplicate_inputs;
    uint64_t durable_envelopes;
    uint64_t pipeline_failures;
    uint64_t action_requests;
    uint64_t action_failures;
} egolink_device_location_runtime_snapshot_t;

typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_DEVICE_LOCATION_RUNTIME_CONTEXT_BYTES];
} egolink_device_location_runtime_t;

/* Produces the deliberately disabled configuration. */
void egolink_device_location_runtime_default_config(
    egolink_device_location_runtime_config_t *config);

/*
 * shared_outbox and location_adapter must already be initialized by one external owner,
 * and location_adapter->outbox must equal shared_outbox.
 * This runtime only borrows them and never initializes or deinitializes them.
 *
 * The identical shared_outbox pointer is the only outbox that may be supplied to SOS orchestration.
 * One caller task or caller-owned mutex must serialize process/cancel/close with SOS enqueue,
 * outbox send, ACK and snapshot calls.
 * The local busy guard catches recursive entry; it is not a cross-task lock.
 */
egolink_device_location_runtime_status_t
egolink_device_location_runtime_init(
    egolink_device_location_runtime_t *runtime,
    const egolink_device_location_runtime_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter);

/*
 * The pipeline commits first. Requested actuator callbacks then run once in
 * the fixed order GNSS start, GNSS stop, Cell observe, IMU rate,
 * LTE keep-connected, upload intent. IMU/LTE declarations run only initially,
 * when their desired value changes, or after their prior attempt failed; a
 * successfully applied unchanged value is not blindly reconfigured.
 * Every callback is synchronous and independently observable. Missing/failed
 * callbacks produce ACTION_PARTIAL_FAILURE but never roll back a committed
 * reducer input or durable envelope. There is no background task or implicit
 * action/input retry; an actuator failure must become a later attributable
 * observation or be handled explicitly by the caller.
 */
egolink_device_location_runtime_status_t
egolink_device_location_runtime_process(
    egolink_device_location_runtime_t *runtime,
    const egolink_location_runtime_input_t *input,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_device_location_runtime_result_t *result);

/*
 * cancel is terminal and invokes safe_cancel at most once. close also invokes
 * it when closing an active runtime, then clears all borrowed dependencies,
 * callbacks and volatile pipeline state without touching durable outbox data.
 * A latched but uncommitted input needs caller-owned journal replay; this
 * component does not claim reboot/cancel equivalence.
 */
egolink_device_location_runtime_status_t
egolink_device_location_runtime_cancel(
    egolink_device_location_runtime_t *runtime,
    egolink_device_location_action_outcome_t *cancel_action);

egolink_device_location_runtime_status_t
egolink_device_location_runtime_close(
    egolink_device_location_runtime_t *runtime,
    egolink_device_location_action_outcome_t *cancel_action);

egolink_device_location_runtime_status_t
egolink_device_location_runtime_current_status(
    const egolink_device_location_runtime_t *runtime,
    egolink_device_location_runtime_snapshot_t *snapshot);

const char *egolink_device_location_runtime_status_name(
    egolink_device_location_runtime_status_t status);
const char *egolink_device_location_runtime_lifecycle_name(
    egolink_device_location_runtime_lifecycle_t lifecycle);
const char *egolink_device_location_action_outcome_name(
    egolink_device_location_action_outcome_t outcome);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_DEVICE_LOCATION_RUNTIME_H */

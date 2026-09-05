#ifndef EGOLINK_LOCATION_MODEM_EXECUTOR_H
#define EGOLINK_LOCATION_MODEM_EXECUTOR_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "device_location_runtime.h"
#include "location_hardware_adapter.h"
#include "location_modem_arbiter.h"
#include "p0_delivery_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_LOCATION_MODEM_EXECUTOR_CONTRACT_VERSION \
    "egolink.location_modem_executor.v0.1"
#define EGOLINK_LOCATION_MODEM_EXECUTOR_CONTEXT_BYTES (24U * 1024U)
#define EGOLINK_LOCATION_MODEM_EXECUTOR_MAX_TIMEOUT_MS UINT64_C(120000)
#define EGOLINK_LOCATION_MODEM_EXECUTOR_DEFAULT_STATUS_TIMEOUT_MS \
    UINT64_C(10000)

typedef enum {
    EGOLINK_MODEM_EXECUTOR_UNINITIALIZED = 0,
    EGOLINK_MODEM_EXECUTOR_DISABLED,
    EGOLINK_MODEM_EXECUTOR_ACTIVE,
    EGOLINK_MODEM_EXECUTOR_RECOVERY_REQUIRED,
} egolink_modem_executor_lifecycle_t;

typedef enum {
    EGOLINK_MODEM_EXECUTOR_PHASE_IDLE = 0,
    EGOLINK_MODEM_EXECUTOR_PHASE_EXECUTION_READY,
    EGOLINK_MODEM_EXECUTOR_PHASE_RESULT_READY,
} egolink_modem_executor_phase_t;

typedef enum {
    EGOLINK_MODEM_EXECUTOR_OK = 0,
    EGOLINK_MODEM_EXECUTOR_QUEUED,
    EGOLINK_MODEM_EXECUTOR_ALREADY_OUTSTANDING,
    EGOLINK_MODEM_EXECUTOR_QUEUE_PARTIAL,
    EGOLINK_MODEM_EXECUTOR_NO_COMMAND,
    EGOLINK_MODEM_EXECUTOR_PREPARED,
    EGOLINK_MODEM_EXECUTOR_ROUTE_REQUEUED,
    EGOLINK_MODEM_EXECUTOR_RESULT_READY,
    EGOLINK_MODEM_EXECUTOR_SETTLED,
    EGOLINK_MODEM_EXECUTOR_INPUT_COMMITTED,
    EGOLINK_MODEM_EXECUTOR_INPUT_COMMITTED_QUEUE_PARTIAL,
    EGOLINK_MODEM_EXECUTOR_DURABLE_SOS_ACCEPTED,
    EGOLINK_MODEM_EXECUTOR_DURABLE_SOS_PARTIAL,
    EGOLINK_MODEM_EXECUTOR_DELIVERY_NO_DUE_RECORD,
    EGOLINK_MODEM_EXECUTOR_DELIVERY_RETAINED,
    EGOLINK_MODEM_EXECUTOR_MAP_REJECTED,
    EGOLINK_MODEM_EXECUTOR_CALLBACK_NOT_CONFIGURED,
    EGOLINK_MODEM_EXECUTOR_CALLBACK_CONTRACT_INVALID,
    EGOLINK_MODEM_EXECUTOR_DEPENDENCY_RECOVERY_REQUIRED,
    EGOLINK_MODEM_EXECUTOR_IN_FLIGHT,
    EGOLINK_MODEM_EXECUTOR_INVALID_PHASE,
    EGOLINK_MODEM_EXECUTOR_INVALID_ARGUMENT,
    EGOLINK_MODEM_EXECUTOR_INVALID_CONFIG,
    EGOLINK_MODEM_EXECUTOR_DEPENDENCY_MISMATCH,
    EGOLINK_MODEM_EXECUTOR_NOT_INITIALIZED,
    EGOLINK_MODEM_EXECUTOR_DISABLED_STATUS,
} egolink_modem_executor_status_t;

typedef enum {
    EGOLINK_MODEM_CALLBACK_REPORT_AVAILABLE = 0,
    EGOLINK_MODEM_CALLBACK_DEFINITE_NO_EFFECT_FAILURE,
    EGOLINK_MODEM_CALLBACK_COOPERATIVE_CANCELLED,
    EGOLINK_MODEM_CALLBACK_OUTCOME_UNKNOWN,
    EGOLINK_MODEM_CALLBACK_OUTCOME_COUNT,
} egolink_modem_callback_outcome_t;

typedef enum {
    EGOLINK_MODEM_SAFE_POINT_NONE = 0,
    EGOLINK_MODEM_SAFE_POINT_BETWEEN_AT_COMMANDS,
} egolink_modem_safe_point_t;

typedef enum {
    EGOLINK_MODEM_DURABLE_SOS_NONE = 0,
    EGOLINK_MODEM_DURABLE_SOS_COMMITTED_OR_DUPLICATE,
} egolink_modem_durable_sos_evidence_t;

typedef bool (*egolink_location_modem_cancel_probe_fn)(
    const egolink_modem_arbiter_t *arbiter,
    uint32_t generation,
    egolink_modem_command_kind_t kind);

/*
 * begin_time_ms/completion_time_ms are execution-bound accounting only. They
 * are never observation source time. The callback must use a bounded modem
 * operation and poll cancel_requested only at reviewed safe points between AT
 * commands. hard_cancel_supported is always false in this slice.
 */
typedef struct {
    egolink_modem_command_kind_t kind;
    uint32_t generation;
    uint64_t begin_time_ms;
    uint64_t timeout_ms;
    egolink_modem_safe_point_t cancellation_safe_point;
    bool hard_cancel_supported;
    egolink_location_modem_cancel_probe_fn cancel_requested;
    const egolink_modem_arbiter_t *cancel_context;
} egolink_location_modem_sensor_request_t;

/*
 * REPORT_AVAILABLE requires a fully initialized report output and a bounded
 * completion time. DEFINITE_NO_EFFECT_FAILURE is legal only before any modem
 * command or external effect could occur. Timeout, partial AT execution,
 * malformed response and uncertain cancellation must be OUTCOME_UNKNOWN.
 */
typedef egolink_modem_callback_outcome_t
(*egolink_location_modem_gnss_execute_fn)(
    void *context,
    const egolink_location_modem_sensor_request_t *request,
    sim7670_gnss_report_t *report,
    uint64_t *completion_time_ms);

typedef egolink_modem_callback_outcome_t
(*egolink_location_modem_cell_execute_fn)(
    void *context,
    const egolink_location_modem_sensor_request_t *request,
    sim7670_lte_report_t *report,
    uint64_t *completion_time_ms);

typedef struct {
    bool enabled;
    egolink_location_runtime_owner_t pipeline_owner;
    egolink_location_modem_gnss_execute_fn execute_gnss;
    void *gnss_context;
    egolink_location_modem_cell_execute_fn execute_cell;
    void *cell_context;
    uint64_t default_gnss_status_timeout_ms;
} egolink_location_modem_executor_config_t;

typedef struct {
    egolink_modem_executor_status_t status;
    bool command_requested;
    bool admitted;
    bool already_outstanding;
    bool followup_scan_deferred;
    egolink_modem_command_kind_t kind;
    egolink_modem_arbiter_status_t arbiter_status;
    egolink_modem_arbiter_enqueue_result_t arbiter_result;
    egolink_p0_delivery_sos_preempt_status_t delivery_preempt_status;
    bool delivery_preemption_signalled;
    bool urgent_gnss_requires_durable_sos;
} egolink_location_modem_enqueue_result_t;

/* No coordinates, report bytes, payload or credentials are returned. */
typedef struct {
    egolink_modem_executor_status_t status;
    egolink_device_location_runtime_status_t device_status;
    egolink_device_location_runtime_result_t device_result;
    bool input_committed;
    bool k_partial_failure_preserved;
    bool any_command_queued;
    bool queue_partial;
    bool unsupported_gnss_stop;
    bool sos_urgent_requires_durable_sos;
    egolink_location_modem_enqueue_result_t gnss;
    egolink_location_modem_enqueue_result_t cell;
    egolink_location_modem_enqueue_result_t location_transport;
} egolink_location_modem_process_result_t;

/*
 * This result reports independent actions after durable SOS evidence: the
 * authoritative Location input, manual-SOS transport wake-up, urgent-GNSS,
 * Location transport wake-up and policy-requested Cell observation.
 * `*_signal_satisfied` means only that a bounded transient attempt was
 * admitted or was already outstanding; it is never a delivery, GNSS-fix or
 * Guardian-notification claim. K intentionally has NULL callbacks, so the
 * owner-required flags preserve IMU/LTE/Call responsibility for the later
 * product composition instead of treating ACTION_PARTIAL_FAILURE as success.
 * No coordinate, payload, credential or raw report is returned.
 */
typedef struct {
    egolink_modem_executor_status_t status;
    bool durable_evidence_accepted;
    bool location_input_attempted;
    egolink_device_location_runtime_status_t location_status;
    egolink_device_location_runtime_result_t location_result;
    bool location_input_committed;
    bool location_input_duplicate;
    bool location_envelope_enqueued_now;
    bool location_action_partial_failure_preserved;
    bool location_branch_satisfied;
    egolink_modem_executor_status_t signal_status;
    bool manual_sos_transport_signal_satisfied;
    bool urgent_gnss_signal_satisfied;
    bool policy_decision_available;
    bool policy_gnss_start_covered_by_urgent;
    bool policy_gnss_stop_requires_product_owner;
    bool policy_cell_observe_requested;
    bool policy_cell_attempt_satisfied;
    bool policy_imu_rate_requires_product_owner;
    bool policy_lte_keep_connected_requires_product_owner;
    bool policy_ego_call_requires_product_owner;
    bool policy_upload_transport_owned_by_executor;
    bool partial_failure;
    egolink_location_modem_enqueue_result_t location_transport;
    egolink_location_modem_enqueue_result_t cell;
    egolink_location_modem_enqueue_result_t sos_transport;
    egolink_location_modem_enqueue_result_t urgent_gnss;
} egolink_location_modem_durable_sos_result_t;

typedef struct {
    egolink_modem_executor_status_t status;
    egolink_modem_arbiter_status_t arbiter_status;
    egolink_modem_arbiter_ticket_t ticket;
    uint64_t timeout_ms;
    bool p0_prepare_called;
    egolink_p0_delivery_runtime_status_t p0_status;
    egolink_p0_delivery_runtime_result_t p0_result;
    bool route_mismatch;
    bool prepared_ticket_cancelled_without_execution;
    bool prepared_ticket_retargeted;
    egolink_modem_arbiter_completion_result_t cancelled_ticket;
    egolink_modem_arbiter_ticket_t actual_route_ticket;
    egolink_location_modem_enqueue_result_t actual_route_requeue;
} egolink_location_modem_prepare_result_t;

/* No raw report is exposed; the result stays in the executor until settle. */
typedef struct {
    egolink_modem_executor_status_t status;
    egolink_modem_command_kind_t kind;
    bool callback_called;
    bool callback_contract_valid;
    bool cancel_observed_before_callback;
    egolink_modem_callback_outcome_t callback_outcome;
    uint64_t completion_time_ms;
    egolink_p0_delivery_runtime_status_t p0_status;
    egolink_p0_delivery_runtime_result_t p0_result;
} egolink_location_modem_execute_result_t;

/*
 * capture_identity is mandatory only for REPORT_AVAILABLE sensor results and
 * must describe the new hardware capture, never the trigger request. M owns
 * all validity/no-fix/offline mapping. scratch is required only when a mapped
 * observation is passed into K.
 */
typedef struct {
    egolink_modem_executor_status_t status;
    egolink_modem_command_kind_t kind;
    egolink_modem_reported_outcome_t reported_outcome;
    egolink_modem_arbiter_status_t arbiter_status;
    egolink_modem_arbiter_completion_result_t arbiter_result;
    bool p0_settle_called;
    egolink_p0_delivery_runtime_status_t p0_status;
    egolink_p0_delivery_runtime_result_t p0_result;
    bool report_mapping_attempted;
    egolink_location_hardware_map_status_t map_status;
    egolink_location_hardware_origin_t mapped_origin;
    bool observation_committed;
    egolink_location_modem_process_result_t process_result;
} egolink_location_modem_settle_result_t;

typedef struct {
    bool initialized;
    bool enabled;
    egolink_modem_executor_lifecycle_t lifecycle;
    egolink_modem_executor_phase_t phase;
    bool p0_delivery_prepared;
    egolink_p0_outbox_route_t p0_prepared_route;
    bool sos_transport_outstanding;
    bool urgent_gnss_outstanding;
    bool deferred_sos_transport;
    bool deferred_location_transport;
    bool deferred_cell_observe;
    uint64_t deferred_cell_timeout_ms;
    uint64_t generated_attempts;
    uint64_t process_calls;
    uint64_t committed_inputs;
    uint64_t queued_commands;
    uint64_t queue_failures;
    uint64_t callback_calls;
    uint64_t callback_contract_failures;
    uint64_t map_failures;
    uint64_t settled_commands;
    egolink_modem_arbiter_snapshot_t arbiter;
    egolink_device_location_runtime_snapshot_t device_runtime;
} egolink_location_modem_executor_snapshot_t;

/* Caller-owned; allocate statically or in long-lived memory, never on stack. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_LOCATION_MODEM_EXECUTOR_CONTEXT_BYTES];
} egolink_location_modem_executor_t;

/*
 * One caller task or caller-owned mutex is the external owner for every O,
 * K, adapter, outbox, dispatcher and P0 prepare/settle call. Only
 * execute_prepared runs after releasing that owner. While it runs, an SOS
 * producer may acquire the same owner and call signal_durable_sos; the P0
 * preemption probe is lock-free, but the complete O signal API is not because
 * it also mutates N's transient queue and O sidecars/deferred flags. Never call
 * signal_durable_sos directly from an ISR or an unlocked GPIO/SOS task.
 * process_durable_sos is a full K/outbox composition and is accepted only in
 * O's IDLE phase; it cannot participate in that execution-time preemption
 * race. If a durable SOS arrives while execute_prepared is running, call only
 * signal_durable_sos under the owner, finish execute/settle, then call
 * process_durable_sos with the same caller-allocated Location identity.
 * Settle starts only after execute_prepared has returned and the caller has
 * reacquired the same owner. No other prepare/execute/settle/status call may
 * race execute_prepared.
 */

void egolink_location_modem_executor_default_config(
    egolink_location_modem_executor_config_t *config);

/*
 * Enabled init owns one private K runtime (with every K callback NULL) and one
 * private N arbiter. It borrows exactly one already-active P0 split delivery
 * runtime plus the same shared outbox/location adapter used by K. Enabled init
 * requires the P0 runtime's additive transitive exact-pointer proof; this is
 * not a caller-attested association. O does not initialize/close those
 * borrowed dependencies or perform I/O.
 */
egolink_modem_executor_status_t egolink_location_modem_executor_init(
    egolink_location_modem_executor_t *executor,
    const egolink_location_modem_executor_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter,
    egolink_p0_delivery_runtime_t *delivery_runtime);

/*
 * Runs K under the external owner, then separately schedules its typed policy
 * intents. K's NULL callbacks deliberately remain NOT_CONFIGURED/PARTIAL;
 * arbiter admission is exposed only as O QUEUED and never ACTION_SUCCEEDED.
 */
egolink_modem_executor_status_t
egolink_location_modem_executor_process_mapped_input(
    egolink_location_modem_executor_t *executor,
    const egolink_location_hardware_mapped_input_t *mapped,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_location_modem_process_result_t *result);

/*
 * Sole durable-SOS ingress into O's private authoritative Location K runtime.
 * The caller must provide the next identity from that same Location stream;
 * an SOS journal sequence is not a substitute. Text views are borrowed only
 * for this synchronous call. Evidence is accepted only after the physical SOS
 * edge is committed to its durable journal or proven an exact duplicate.
 *
 * The function first signals the existing manual-SOS transport/preemption and
 * bounded urgent-GNSS paths, then independently evaluates one coordinate-free
 * SOS observation in K. A Location envelope/retry/identity failure therefore
 * cannot suppress those two safety signals. An exact adjacent identity replay
 * is idempotent in K, but does not prove that its earlier Location outbox
 * record remains present after ACK/deletion. The existing outstanding/deferred
 * flags coalesce repeated transport/GNSS hints without growing N's fixed queue
 * unboundedly. A policy-requested Cell attempt that is rejected or displaced
 * by urgent GNSS remains one bounded deferred obligation; an exact K replay
 * cannot silently upgrade that partial result to accepted.
 *
 * This API requires the shared external owner documented above and rejects
 * every non-IDLE phase without touching K or either queue. It performs no
 * GPIO, journal, AT, UART, HTTP, task or clock operation and must never run
 * from an ISR. DURABLE_SOS_ACCEPTED describes only local admission/queuing;
 * any unsatisfied branch returns DURABLE_SOS_PARTIAL and is detailed in the
 * result. The caller retains retry/recovery ownership.
 */
egolink_modem_executor_status_t
egolink_location_modem_executor_process_durable_sos(
    egolink_location_modem_executor_t *executor,
    const egolink_location_runtime_identity_t *location_identity,
    egolink_modem_durable_sos_evidence_t evidence,
    uint64_t urgent_gnss_timeout_ms,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_location_modem_durable_sos_result_t *result);

/*
 * Caller assertion is accepted only for a committed/duplicate durable SOS and
 * this whole API must hold the shared external owner described above.
 * The P0 cancellation hint is signalled on every call. Repeated calls do not
 * add another urgent-GNSS attempt while one is queued/in flight; likewise one
 * SOS transport attempt is coalesced into a single bounded deferred selector
 * pass so repeated hints cannot grow the transient queue without bound.
 */
egolink_modem_executor_status_t
egolink_location_modem_executor_signal_durable_sos(
    egolink_location_modem_executor_t *executor,
    egolink_modem_durable_sos_evidence_t evidence,
    uint64_t urgent_gnss_timeout_ms,
    egolink_location_modem_enqueue_result_t *sos_transport,
    egolink_location_modem_enqueue_result_t *urgent_gnss);

egolink_modem_executor_status_t
egolink_location_modem_executor_request_gnss_status(
    egolink_location_modem_executor_t *executor,
    uint64_t timeout_ms,
    egolink_location_modem_enqueue_result_t *result);

/*
 * prepare runs under the external owner and performs N take/mark plus P0
 * prepare for transport. The returned PREPARED boundary means release owner.
 * Route truth always comes from P0/outbox. A mismatched hint is atomically
 * retargeted to the already-prepared actual route with a fresh generation and
 * operation ID, then returned ready for execute/settle; the original hinted
 * route is deferred for a later selector pass. The legacy ROUTE_REQUEUED name
 * also covers admission of one retained Cell selector attempt. No prepared P0
 * lease is lost.
 */
egolink_modem_executor_status_t
egolink_location_modem_executor_prepare_next(
    egolink_location_modem_executor_t *executor,
    uint64_t now_ms,
    egolink_location_modem_prepare_result_t *result);

/* Runs without the external owner. Only injected sensor or P0 execute runs. */
egolink_modem_executor_status_t
egolink_location_modem_executor_execute_prepared(
    egolink_location_modem_executor_t *executor,
    uint64_t begin_time_ms,
    egolink_location_modem_execute_result_t *result);

/* Reacquire the owner before settle; no next command is selected implicitly. */
egolink_modem_executor_status_t
egolink_location_modem_executor_settle_prepared(
    egolink_location_modem_executor_t *executor,
    const egolink_location_hardware_identity_t *capture_identity,
    uint64_t outbox_now_ms,
    egolink_location_runtime_scratch_t *scratch,
    egolink_location_modem_settle_result_t *result);

egolink_modem_executor_status_t
egolink_location_modem_executor_current_status(
    const egolink_location_modem_executor_t *executor,
    egolink_location_modem_executor_snapshot_t *snapshot);

const char *egolink_location_modem_executor_status_name(
    egolink_modem_executor_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_LOCATION_MODEM_EXECUTOR_H */

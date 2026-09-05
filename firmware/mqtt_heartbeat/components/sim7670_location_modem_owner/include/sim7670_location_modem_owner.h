#ifndef EGOLINK_SIM7670_LOCATION_MODEM_OWNER_H
#define EGOLINK_SIM7670_LOCATION_MODEM_OWNER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "location_modem_executor.h"
#include "sim7670_location_modem_adapter.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_SIM7670_LOCATION_MODEM_OWNER_CONTRACT_VERSION \
    "egolink.sim7670_location_modem_owner.v0.1"
#define EGOLINK_SIM7670_LOCATION_MODEM_OWNER_CONTEXT_BYTES (64U * 1024U)
#define EGOLINK_SIM7670_LOCATION_MODEM_OWNER_TASK_STACK_BYTES (16U * 1024U)
#define EGOLINK_SIM7670_LOCATION_MODEM_OWNER_DEFAULT_TASK_PRIORITY 5U
#define EGOLINK_SIM7670_LOCATION_MODEM_OWNER_MAX_COMMANDS_PER_WAKE 8U

typedef enum {
    EGOLINK_SIM7670_MODEM_OWNER_UNINITIALIZED = 0,
    EGOLINK_SIM7670_MODEM_OWNER_DISABLED,
    EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED,
    EGOLINK_SIM7670_MODEM_OWNER_STARTING,
    EGOLINK_SIM7670_MODEM_OWNER_ACTIVE,
    EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED,
} egolink_sim7670_modem_owner_lifecycle_t;

typedef enum {
    EGOLINK_SIM7670_MODEM_OWNER_OK = 0,
    EGOLINK_SIM7670_MODEM_OWNER_INITIALIZED_STATUS,
    EGOLINK_SIM7670_MODEM_OWNER_STARTED,
    EGOLINK_SIM7670_MODEM_OWNER_QUEUED,
    EGOLINK_SIM7670_MODEM_OWNER_DURABLE_SOS_ACCEPTED,
    EGOLINK_SIM7670_MODEM_OWNER_DURABLE_SOS_PARTIAL,
    EGOLINK_SIM7670_MODEM_OWNER_DISABLED_STATUS,
    EGOLINK_SIM7670_MODEM_OWNER_BUILD_DISABLED,
    EGOLINK_SIM7670_MODEM_OWNER_INVALID_ARGUMENT,
    EGOLINK_SIM7670_MODEM_OWNER_INVALID_CONFIG,
    EGOLINK_SIM7670_MODEM_OWNER_ALREADY_INITIALIZED,
    EGOLINK_SIM7670_MODEM_OWNER_ALREADY_STARTED,
    EGOLINK_SIM7670_MODEM_OWNER_DEPENDENCY_MISMATCH,
    EGOLINK_SIM7670_MODEM_OWNER_ADAPTER_INIT_FAILED,
    EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_INIT_FAILED,
    EGOLINK_SIM7670_MODEM_OWNER_TASK_CREATE_FAILED,
    EGOLINK_SIM7670_MODEM_OWNER_START_TIMEOUT,
    EGOLINK_SIM7670_MODEM_OWNER_UART_INIT_FAILED,
    EGOLINK_SIM7670_MODEM_OWNER_EXCLUSIVE_OWNER_MISMATCH,
    EGOLINK_SIM7670_MODEM_OWNER_NOT_STARTED,
    EGOLINK_SIM7670_MODEM_OWNER_OWNER_LOCK_TIMEOUT,
    EGOLINK_SIM7670_MODEM_OWNER_IN_FLIGHT,
    EGOLINK_SIM7670_MODEM_OWNER_EXECUTOR_REJECTED,
    EGOLINK_SIM7670_MODEM_OWNER_GNSS_POWER_OFF_UNCONFIRMED,
    EGOLINK_SIM7670_MODEM_OWNER_IDENTITY_EXHAUSTED,
    EGOLINK_SIM7670_MODEM_OWNER_RECOVERY_REQUIRED_STATUS,
    EGOLINK_SIM7670_MODEM_OWNER_MAPPED_INPUT_PARTIAL,
    EGOLINK_SIM7670_MODEM_OWNER_SOS_SIGNAL_PARTIAL,
} egolink_sim7670_modem_owner_status_t;

/*
 * All timeouts are bounded boot-local controls. The pipeline owner is copied
 * during init; caller text storage need not outlive init. first_sequence_id
 * seeds Q's private modem-capture counter. It is not a public allocation
 * service. A future live composition must supply every external mapped/SOS
 * identity from one shared replayable allocator/journal and seed Q from that
 * same namespace; snapshot telemetry is never an identity reservation.
 */
typedef struct {
    bool enabled;
    int32_t owner_core_id;
    uint32_t task_priority;
    uint32_t startup_wait_timeout_ms;
    uint32_t owner_lock_timeout_ms;
    uint32_t idle_poll_ms;
    uint32_t recovery_retry_backoff_ms;
    uint32_t per_command_timeout_cap_ms;
    uint32_t gnss_power_off_timeout_ms;
    uint32_t max_commands_per_wake;
    uint64_t default_gnss_status_timeout_ms;
    uint64_t first_sequence_id;
    egolink_location_runtime_owner_t pipeline_owner;
    egolink_location_runtime_publish_intent_t sensor_publish_intent;
} egolink_sim7670_location_modem_owner_config_t;

/* No coordinate, cell identity, payload, response, credential or lineage ID. */
typedef struct {
    bool initialized;
    bool enabled;
    bool task_created;
    bool uart_initialized;
    bool exclusive_owner_confirmed;
    bool execution_active;
    bool gnss_off_confirmed;
    bool cleanup_recovery_required;
    bool fatal_recovery_required;
    int32_t owner_core_id;
    uint32_t per_command_timeout_cap_ms;
    uint32_t gnss_power_off_timeout_ms;
    uint64_t task_wakeups;
    uint64_t prepared_commands;
    uint64_t executed_commands;
    uint64_t settled_commands;
    uint64_t owner_lock_timeouts;
    uint64_t power_off_attempts;
    uint64_t power_off_confirmed;
    uint64_t power_off_unconfirmed;
    uint64_t recovery_attempts;
    uint64_t generated_capture_identities;
    egolink_modem_executor_status_t last_executor_status;
    egolink_sim7670_location_adapter_status_t last_adapter_status;
    sim7670_location_bounded_outcome_t last_power_off_outcome;
    sim7670_location_bounded_reason_t last_power_off_reason;
    egolink_sim7670_modem_owner_lifecycle_t lifecycle;
    egolink_sim7670_modem_owner_status_t last_status;
} egolink_sim7670_location_modem_owner_snapshot_t;

/* Caller-owned, long-lived storage. It must outlive the boot-long owner task. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_SIM7670_LOCATION_MODEM_OWNER_CONTEXT_BYTES];
} egolink_sim7670_location_modem_owner_t;

/* Produces the disabled configuration. It creates no task and touches no UART. */
void egolink_sim7670_location_modem_owner_default_config(
    egolink_sim7670_location_modem_owner_config_t *config);

/*
 * Initializes P and O around the exact borrowed outbox, Location adapter and
 * P0 delivery runtime. It does not create the task or touch the modem. Enabled
 * init fails unless the build-time owner switch is explicitly selected.
 */
egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_init(
    egolink_sim7670_location_modem_owner_t *owner,
    const egolink_sim7670_location_modem_owner_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter,
    egolink_p0_delivery_runtime_t *delivery_runtime);

/*
 * Creates exactly one pinned static task. That task exclusively initializes
 * the SIM7670 AT backend and proves GNSS power-off before becoming ACTIVE.
 * Concurrent start calls are fail-closed by one metadata-locked claim on the
 * static TCB/stack; only task-creation failure releases that claim for retry.
 * Calling this on an enabled build may configure UART and send one bounded AT
 * power-off command; the component remains absent from app_main in LOC-021Q.
 */
egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_start(
    egolink_sim7670_location_modem_owner_t *owner);

/*
 * Synchronous, pointer-safe ingress under the owner's mutex. mapped is never
 * copied because its text views point into the same object. This API rejects
 * the complete execute/settle interval as IN_FLIGHT. Like full SOS ingress,
 * live external producers require the future shared replayable identity/order
 * owner; a modem-only Q smoke can leave this API unwired. A committed input
 * whose requested modem work is only partly queued returns
 * MAPPED_INPUT_PARTIAL, never OK.
 */
egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_process_mapped_input(
    egolink_sim7670_location_modem_owner_t *owner,
    const egolink_location_hardware_mapped_input_t *mapped,
    uint64_t outbox_now_ms,
    egolink_location_modem_process_result_t *result);

/*
 * Sole full durable-SOS ingress into O/K. location_identity belongs to the
 * authoritative Location stream, not the SOS journal, and its text is
 * borrowed only for this call. It must come from the future shared replayable
 * Location sequence allocator; Q exposes no read-then-reserve shortcut and
 * this compile-only slice must not wire the API live without that allocator.
 * The allocator/journal must preserve the physical edge occurrence time and
 * replay-compatible event-time order; processing time or snapshot-read time
 * is not a substitute. This requires O IDLE. If SOS arrives during execute,
 * first use signal_durable_sos below for immediate preemption. Only process
 * the full Location ingress after the future journal/resequencer can order the
 * edge against the sensor completion; a later out-of-order call fails closed.
 */
egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_process_durable_sos(
    egolink_sim7670_location_modem_owner_t *owner,
    const egolink_location_runtime_identity_t *location_identity,
    egolink_modem_durable_sos_evidence_t evidence,
    uint64_t urgent_gnss_timeout_ms,
    uint64_t outbox_now_ms,
    egolink_location_modem_durable_sos_result_t *result);

/*
 * The only ingress allowed during owner-released execution. evidence must
 * mean the manual SOS is already durable. If either transient SOS/GNSS branch
 * is not queued, the top-level result is SOS_SIGNAL_PARTIAL rather than
 * QUEUED. Never call this from an ISR.
 */
egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_signal_durable_sos(
    egolink_sim7670_location_modem_owner_t *owner,
    egolink_modem_durable_sos_evidence_t evidence,
    uint64_t urgent_gnss_timeout_ms,
    egolink_location_modem_enqueue_result_t *sos_transport,
    egolink_location_modem_enqueue_result_t *urgent_gnss);

egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_request_gnss_status(
    egolink_sim7670_location_modem_owner_t *owner,
    uint64_t timeout_ms,
    egolink_location_modem_enqueue_result_t *result);

/*
 * Lock-free with respect to O: reads only short owner metadata under a
 * critical section and is safe while execute_prepared is running.
 */
egolink_sim7670_modem_owner_status_t
egolink_sim7670_location_modem_owner_current_status(
    const egolink_sim7670_location_modem_owner_t *owner,
    egolink_sim7670_location_modem_owner_snapshot_t *snapshot);

/*
 * LOC-021Q is deliberately boot-long. There is no delete/deinit API: a caller
 * must not vTaskDelete the owner or uninstall UART underneath bounded I/O.
 * A later shutdown slice must quiesce O, wait for the active AT bound, settle,
 * and confirm GNSS power-off before adding teardown.
 */

const char *egolink_sim7670_modem_owner_status_name(
    egolink_sim7670_modem_owner_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SIM7670_LOCATION_MODEM_OWNER_H */

#ifndef EGOLINK_SIM7670_LOCATION_MODEM_ADAPTER_H
#define EGOLINK_SIM7670_LOCATION_MODEM_ADAPTER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>

#include "location_modem_executor.h"
#include "sim7670_gnss.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_SIM7670_LOCATION_MODEM_ADAPTER_CONTRACT_VERSION \
    "egolink.sim7670_location_modem_adapter.v0.1"
#define EGOLINK_SIM7670_LOCATION_MODEM_ADAPTER_CONTEXT_BYTES 512U
#define EGOLINK_SIM7670_LOCATION_DEFAULT_COMMAND_CAP_MS UINT32_C(3000)

/*
 * The existing public sim7670_gnss_request_location() and
 * sim7670_lte_query_status() entry points are whole synchronous transactions.
 * They use compile-time per-command timeouts and expose neither a request-wide
 * deadline nor a between-AT cancellation probe. CURRENT_SYNCHRONOUS therefore
 * binds fail-closed callbacks but never calls either function. It exists to
 * expose that exact integration blocker without representing partial AT work
 * as a safe timeout, no-fix, offline state, or cancellable operation.
 *
 * NATIVE_BOUNDED calls only the additive request-wide bounded APIs declared in
 * sim7670_gnss.h. Those APIs require the UART backend to have been initialized
 * explicitly by the single modem owner; they never initialize it from inside
 * an O execution deadline.
 */
typedef enum {
    EGOLINK_SIM7670_DRIVER_CURRENT_SYNCHRONOUS_FAIL_CLOSED = 0,
    EGOLINK_SIM7670_DRIVER_NATIVE_BOUNDED,
} egolink_sim7670_driver_mode_t;

typedef enum {
    EGOLINK_SIM7670_ADAPTER_UNINITIALIZED = 0,
    EGOLINK_SIM7670_ADAPTER_DISABLED,
    EGOLINK_SIM7670_ADAPTER_READY,
    EGOLINK_SIM7670_ADAPTER_BOUND_FAIL_CLOSED,
    EGOLINK_SIM7670_ADAPTER_INVALID_ARGUMENT,
    EGOLINK_SIM7670_ADAPTER_INVALID_CONFIG,
    EGOLINK_SIM7670_ADAPTER_WRONG_CORE,
    EGOLINK_SIM7670_ADAPTER_CONCURRENT_CALL_REJECTED,
    EGOLINK_SIM7670_ADAPTER_REQUEST_CONTRACT_INVALID,
    EGOLINK_SIM7670_ADAPTER_REQUEST_DEADLINE_EXPIRED,
    EGOLINK_SIM7670_ADAPTER_CLOCK_REGRESSION,
    EGOLINK_SIM7670_ADAPTER_DRIVER_OUTCOME_UNKNOWN,
    EGOLINK_SIM7670_ADAPTER_REPORT_INCOMPLETE_OR_AMBIGUOUS,
    EGOLINK_SIM7670_ADAPTER_CANCELLED_AT_SAFE_POINT,
    EGOLINK_SIM7670_ADAPTER_DEFINITE_NO_EFFECT_FAILURE,
    EGOLINK_SIM7670_ADAPTER_REPORT_AVAILABLE,
} egolink_sim7670_location_adapter_status_t;

typedef enum {
    EGOLINK_SIM7670_BLOCKER_NONE = 0U,
    EGOLINK_SIM7670_BLOCKER_REQUEST_DEADLINE_UNSUPPORTED = 1U << 0,
    EGOLINK_SIM7670_BLOCKER_BETWEEN_AT_CANCEL_UNSUPPORTED = 1U << 1,
} egolink_sim7670_location_blocker_t;

typedef enum {
    EGOLINK_SIM7670_GNSS_REPORT_INCOMPLETE_OR_AMBIGUOUS = 0,
    EGOLINK_SIM7670_GNSS_REPORT_COMPLETE_FIX,
    EGOLINK_SIM7670_GNSS_REPORT_COMPLETE_NO_FIX,
} egolink_sim7670_gnss_report_class_t;

typedef enum {
    EGOLINK_SIM7670_LTE_REPORT_INCOMPLETE_OR_AMBIGUOUS = 0,
    EGOLINK_SIM7670_LTE_REPORT_COMPLETE_STATE,
    EGOLINK_SIM7670_LTE_REPORT_COMPLETE_STATE_AND_CELL,
} egolink_sim7670_lte_report_class_t;

typedef struct {
    bool enabled;
    egolink_sim7670_driver_mode_t driver_mode;
    int32_t owner_core_id;
    uint32_t per_command_timeout_cap_ms;
    uint32_t gnss_power_on_settle_ms;
    /* Borrowed boot-long owner flag, observed at the existing safe boundaries. */
    const atomic_bool *owner_stop_requested;
} egolink_sim7670_location_modem_adapter_config_t;

/* This snapshot deliberately contains no report, coordinate, cell ID or raw AT. */
typedef struct {
    bool initialized;
    bool enabled;
    bool callbacks_bound;
    bool callback_active;
    bool hard_cancel_supported;
    egolink_sim7670_driver_mode_t driver_mode;
    int32_t owner_core_id;
    uint32_t per_command_timeout_cap_ms;
    uint32_t blocker_flags;
    uint64_t callback_calls;
    uint64_t report_available_count;
    uint64_t unknown_outcome_count;
    uint64_t definite_no_effect_count;
    uint64_t cooperative_cancel_count;
    uint64_t wrong_core_count;
    uint64_t concurrent_rejection_count;
    egolink_modem_command_kind_t last_kind;
    egolink_modem_callback_outcome_t last_callback_outcome;
    sim7670_location_bounded_outcome_t last_driver_outcome;
    sim7670_location_bounded_reason_t last_driver_reason;
    bool last_driver_io_started;
    bool last_driver_cancel_before_io;
    bool last_driver_cancelled_between_commands;
    bool last_driver_partial_or_unknown;
    uint16_t last_driver_commands_attempted;
    uint16_t last_driver_commands_tx_complete;
    uint16_t last_driver_commands_completed;
    egolink_sim7670_location_adapter_status_t last_status;
} egolink_sim7670_location_modem_adapter_snapshot_t;

typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_SIM7670_LOCATION_MODEM_ADAPTER_CONTEXT_BYTES];
} egolink_sim7670_location_modem_adapter_t;

/* Produces the disabled configuration. No callback and no modem I/O starts. */
void egolink_sim7670_location_modem_adapter_default_config(
    egolink_sim7670_location_modem_adapter_config_t *config);

/*
 * Explicitly selects the current legacy synchronous API in fail-closed mode.
 * The resulting callbacks are observable but suppress all modem I/O because
 * that API cannot consume O's request deadline or cancellation probe.
 */
void egolink_sim7670_location_modem_adapter_legacy_fail_closed_config(
    egolink_sim7670_location_modem_adapter_config_t *config,
    int32_t owner_core_id);

/* Selects the additive native bounded query API; still does not start I/O. */
void egolink_sim7670_location_modem_adapter_bounded_config(
    egolink_sim7670_location_modem_adapter_config_t *config,
    int32_t owner_core_id,
    uint32_t per_command_timeout_cap_ms);

egolink_sim7670_location_adapter_status_t
egolink_sim7670_location_modem_adapter_init(
    egolink_sim7670_location_modem_adapter_t *adapter,
    const egolink_sim7670_location_modem_adapter_config_t *config);

/*
 * Installs this long-lived adapter as O's GNSS and Cell callbacks. It never
 * enables O. CURRENT_SYNCHRONOUS returns BOUND_FAIL_CLOSED after installing
 * the callbacks so the blocker remains executable and observable.
 *
 * One caller-owned task pinned to owner_core_id must serialize all O calls.
 * O's owner must be released during execute_prepared. The same task/composite
 * modem owner must also exclude every legacy HTTP/status/GNSS caller: this
 * adapter guards re-entry through itself, not unrelated direct driver calls.
 * It creates no task and never performs transport concurrently with a sensor.
 * O's begin_time_ms and this adapter's completion_time_ms must both use
 * esp_timer boot-monotonic milliseconds; another clock domain fails closed.
 */
egolink_sim7670_location_adapter_status_t
egolink_sim7670_location_modem_adapter_bind_executor_config(
    egolink_sim7670_location_modem_adapter_t *adapter,
    egolink_location_modem_executor_config_t *executor_config);

/* Pure report-evidence classifiers; they log and retain nothing. */
egolink_sim7670_gnss_report_class_t
egolink_sim7670_location_classify_gnss_report(
    const sim7670_gnss_report_t *report);
egolink_sim7670_lte_report_class_t
egolink_sim7670_location_classify_lte_report(
    const sim7670_lte_report_t *report);

egolink_sim7670_location_adapter_status_t
egolink_sim7670_location_modem_adapter_current_status(
    const egolink_sim7670_location_modem_adapter_t *adapter,
    egolink_sim7670_location_modem_adapter_snapshot_t *snapshot);

const char *egolink_sim7670_location_adapter_status_name(
    egolink_sim7670_location_adapter_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SIM7670_LOCATION_MODEM_ADAPTER_H */

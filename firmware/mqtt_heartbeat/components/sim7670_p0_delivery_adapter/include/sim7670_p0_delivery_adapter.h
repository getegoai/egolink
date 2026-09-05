#ifndef EGOLINK_SIM7670_P0_DELIVERY_ADAPTER_H
#define EGOLINK_SIM7670_P0_DELIVERY_ADAPTER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdalign.h>

#include "p0_delivery_runtime.h"
#include "sim7670_gnss.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_SIM7670_P0_DELIVERY_ADAPTER_CONTRACT_VERSION \
    "egolink.sim7670_p0_delivery_adapter.v0.1"
#define EGOLINK_SIM7670_P0_DELIVERY_ADAPTER_CONTEXT_BYTES 1024U
#define EGOLINK_SIM7670_P0_DELIVERY_BASE_URL_CAPACITY 257U
#define EGOLINK_SIM7670_P0_DELIVERY_EXPECTED_HOST_CAPACITY 249U
#define EGOLINK_SIM7670_P0_DELIVERY_BEARER_CAPACITY 193U
#define EGOLINK_SIM7670_P0_DELIVERY_FULL_URL_CAPACITY 321U
#define EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_COMMAND_TIMEOUT_MS UINT32_C(1000)
#define EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_DATA_TIMEOUT_MS UINT32_C(3000)
#define EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_ACTION_TIMEOUT_MS UINT32_C(10000)
#define EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_READ_TIMEOUT_MS UINT32_C(4000)
#define EGOLINK_SIM7670_P0_DELIVERY_MAX_TRANSACTION_MS \
    EGOLINK_P0_DELIVERY_RUNTIME_MAX_POST_DURATION_MS
#define EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_MAX_CALLBACK_DURATION_MS \
    EGOLINK_P0_DELIVERY_RUNTIME_DEFAULT_MAX_POST_DURATION_MS

typedef enum {
    EGOLINK_SIM7670_P0_DELIVERY_NEVER_INITIALIZED = 0,
    EGOLINK_SIM7670_P0_DELIVERY_DISABLED,
    EGOLINK_SIM7670_P0_DELIVERY_ACTIVE,
    EGOLINK_SIM7670_P0_DELIVERY_CLOSED,
} egolink_sim7670_p0_delivery_lifecycle_t;

typedef enum {
    EGOLINK_SIM7670_P0_DELIVERY_OK = 0,
    EGOLINK_SIM7670_P0_DELIVERY_DISABLED_STATUS,
    EGOLINK_SIM7670_P0_DELIVERY_CLOSED_STATUS,
    EGOLINK_SIM7670_P0_DELIVERY_INVALID_ARGUMENT,
    EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG,
    EGOLINK_SIM7670_P0_DELIVERY_NOT_INITIALIZED,
    EGOLINK_SIM7670_P0_DELIVERY_ALREADY_INITIALIZED,
    EGOLINK_SIM7670_P0_DELIVERY_REENTRANT_CALL,
} egolink_sim7670_p0_delivery_status_t;

typedef sim7670_lte_http_exact_status_t
(*egolink_sim7670_p0_delivery_driver_post_fn)(
    void *context,
    const sim7670_lte_http_exact_request_t *request,
    sim7670_lte_http_exact_result_t *result);

typedef uint64_t (*egolink_sim7670_p0_delivery_now_ms_fn)(void *context);

typedef struct {
    bool enabled;
    const char *base_url;
    const char *expected_tls_host;
    const char *bearer_token;
    uint32_t command_timeout_ms;
    uint32_t data_timeout_ms;
    uint32_t action_timeout_ms;
    uint32_t read_timeout_ms;
    uint32_t max_callback_duration_ms;
    egolink_sim7670_p0_delivery_driver_post_fn driver_post;
    void *driver_context;
    egolink_sim7670_p0_delivery_now_ms_fn now_ms;
    void *clock_context;
} egolink_sim7670_p0_delivery_adapter_config_t;

/* No URL, bearer, payload, response, coordinates or identity are exposed. */
typedef struct {
    egolink_sim7670_p0_delivery_lifecycle_t lifecycle;
    egolink_sim7670_p0_delivery_status_t last_status;
    sim7670_lte_http_exact_status_t last_driver_status;
    bool enabled;
    bool busy;
    uint32_t configured_io_phase_budget_ms;
    uint32_t configured_max_callback_duration_ms;
    uint64_t callback_calls;
    uint64_t http_responses;
    uint64_t transport_failures;
    uint64_t callback_failures;
} egolink_sim7670_p0_delivery_adapter_snapshot_t;

typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_SIM7670_P0_DELIVERY_ADAPTER_CONTEXT_BYTES];
} egolink_sim7670_p0_delivery_adapter_t;

void egolink_sim7670_p0_delivery_adapter_default_config(
    egolink_sim7670_p0_delivery_adapter_config_t *config);

/*
 * Enabled init accepts only an exact HTTPS host-only origin whose authority
 * equals expected_tls_host. Both pass the exact parser's shared lowercase DNS
 * validator: every label is at most 63 bytes and IPv4/IPv6 literals are
 * rejected. It then copies bounded base URL and bearer bytes into volatile
 * adapter memory. The caller must serialize this callback with every
 * other SIM7670 user for the complete multi-command HTTP transaction. The
 * modem component
 * takes its UART mutex per command, not across the whole transaction, so that
 * external single-owner rule is what prevents AT-command interleaving.
 *
 * No task, retry, NVS, credential source, modem initialization or network
 * action happens during init. The configured I/O phase budget must be less
 * than max_callback_duration_ms; the latter must be no greater than the
 * composing delivery runtime's max_post_duration_ms. The defaults are a
 * 25-second phase sum and a 30-second callback bound, leaving five seconds
 * for scheduling/accounting outside phase waits. A future owner must preserve
 * a reviewed margin when composing non-default values.
 * Underlying UART/RTOS APIs remain trusted to honor their own bounded-call
 * contracts.
 *
 * driver_post injection is admitted only by the separately default-disabled
 * TEST_DRIVER Kconfig used by offline harnesses. Ordinary firmware requires
 * the built-in exact driver, which currently fails TLS_PROFILE_UNVERIFIED
 * before UART/token/payload activity. A fake callback is never TLS evidence.
 */
egolink_sim7670_p0_delivery_status_t
egolink_sim7670_p0_delivery_adapter_init(
    egolink_sim7670_p0_delivery_adapter_t *adapter,
    const egolink_sim7670_p0_delivery_adapter_config_t *config);

/*
 * This is the synchronous egolink_p0_delivery_http_post_fn boundary. Only the
 * two fixed dispatcher route/path/capacity combinations are admitted. The
 * exact body range is forwarded once with its explicit length. The callback
 * performs no retry and must not be invoked concurrently or recursively. Its
 * borrowed cancellation probe/context/generation are forwarded unchanged to
 * the exact driver as a cooperative safe-point hint.
 */
egolink_p0_delivery_post_outcome_t
egolink_sim7670_p0_delivery_adapter_http_post(
    void *context,
    const egolink_p0_delivery_post_request_t *request,
    egolink_p0_delivery_post_result_t *result);

/* close performs no I/O and securely clears volatile URL/bearer state. */
egolink_sim7670_p0_delivery_status_t
egolink_sim7670_p0_delivery_adapter_close(
    egolink_sim7670_p0_delivery_adapter_t *adapter);

egolink_sim7670_p0_delivery_status_t
egolink_sim7670_p0_delivery_adapter_current_status(
    const egolink_sim7670_p0_delivery_adapter_t *adapter,
    egolink_sim7670_p0_delivery_adapter_snapshot_t *snapshot);

const char *egolink_sim7670_p0_delivery_adapter_status_name(
    egolink_sim7670_p0_delivery_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SIM7670_P0_DELIVERY_ADAPTER_H */

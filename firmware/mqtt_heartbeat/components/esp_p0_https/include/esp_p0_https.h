#pragma once
#include "p0_delivery_runtime.h"

/* One delivery owner; credentials borrowed from ignored engineering config.
 * Bounds count attempts, including failed handshakes. No automatic redirect,
 * credential fallback, logging, registration, retry or second outbox. */
typedef struct {
    const char *origin;
    const char *expected_host;
    const char *bearer;
    uint64_t deadline_ms;
    uint32_t max_attempts;
    uint32_t attempts;
    uint32_t complete_responses;
    uint32_t transaction_timeout_ms;
    /* Collection-only opt-in. One owner must keep this context at a stable
     * address, must not copy it while open, and closes it before network switch
     * or owner shutdown. Zero initialization preserves the one-request path. */
    bool reuse_connection;
    void *connection_state; /* private; initialize to NULL */
} egolink_esp_p0_https_t;

/* Same owner, between synchronous POST calls; idempotent and NULL-safe. */
void egolink_esp_p0_https_close(egolink_esp_p0_https_t *context);

bool egolink_esp_p0_https_config_valid(const egolink_esp_p0_https_t *config);
egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_post(
    void *context, const egolink_p0_delivery_post_request_t *request,
    egolink_p0_delivery_post_result_t *result);

/* Collection uses the same bounded certificate/hostname verified implementation,
 * a fixed per-device raw-ingest path and a named actual Wi-Fi or PPP interface.
 * Only strict st<digits>/pp<digits> names are admitted; the implementation
 * derives the transport header from that family and binds the socket to it. */
egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_post_collection(
    egolink_esp_p0_https_t *context, const char *device_id, const char *interface_name,
    const egolink_p0_delivery_post_request_t *request,
    egolink_p0_delivery_post_result_t *result);

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

/* Camera collection keeps one network owner and the existing Message Hub
 * command table. These narrow helpers expose only the three additional fixed
 * routes; callers cannot supply an origin or arbitrary path. All responses
 * require an explicit complete Content-Length within response_capacity. */
egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_poll_collection_command(
    egolink_esp_p0_https_t *context, const char *device_id,
    const char *interface_name, uint8_t *response, size_t response_capacity,
    egolink_p0_delivery_cancel_probe_fn cancel_requested, void *cancel_context,
    uint32_t transfer_generation, egolink_p0_delivery_post_result_t *result);

egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_ack_collection_command(
    egolink_esp_p0_https_t *context, const char *device_id, const char *cmd_id,
    const char *interface_name, const uint8_t *frame, size_t frame_bytes,
    uint8_t *response, size_t response_capacity,
    egolink_p0_delivery_cancel_probe_fn cancel_requested, void *cancel_context,
    uint32_t transfer_generation, egolink_p0_delivery_post_result_t *result);

egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_upload_collection_photo(
    egolink_esp_p0_https_t *context, const char *device_id,
    const char *photo_id, const char sha256_hex[65],
    const char *interface_name, const uint8_t *jpeg, size_t jpeg_bytes,
    uint8_t *response, size_t response_capacity,
    egolink_p0_delivery_cancel_probe_fn cancel_requested, void *cancel_context,
    uint32_t transfer_generation, egolink_p0_delivery_post_result_t *result);

#ifndef EGOLINK_PHOTO_DELIVERY_RUNTIME_H
#define EGOLINK_PHOTO_DELIVERY_RUNTIME_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PHOTO_DELIVERY_SHA256_HEX_BYTES 65U

typedef struct {
    const char *device_id;
    const char *photo_id;
    const char *trigger_reason;
    const char *command_id;
    const char *config_version;
    const char *capture_result;
    const char *local_save_status;
    const char *device_upload_status;
    const char *media_type;
    uint16_t width;
    uint16_t height;
    size_t byte_length;
    const char *sha256_hex;
    const char *storage_kind;
    const char *camera_model;
    const char *driver_profile;
    const char *location_observation_id;
    const char *location_event_utc;
    const char *location_timestamp_quality;
    const char *authorization_session_id;
    const char *retention_expires_at;
    const char *failure_reason;
    uint32_t capture_boot_count;
    uint32_t capture_sequence_id;
    uint64_t capture_monotonic_ns;
    const char *capture_event_utc;
    const char *timestamp_source;
    const char *timestamp_quality;
    const char *monotonic_clock_domain_id;
    const char *fw_version;
    const char *firmware_elf_sha256;
    const char *runtime_config_id;
} photo_delivery_metadata_t;

/* Produces the ordinary collection-spool record for one capture outcome.
 * A durable capture has actual JPEG dimensions/length/digest. A failed
 * capture has all content fields null and device_upload_status=not_ready. */
bool photo_delivery_build_metadata_frame(
    const photo_delivery_metadata_t *metadata,
    char *frame, size_t capacity, size_t *written);

/* Command ACK acceptance is not inferred from HTTP 2xx alone. */
bool photo_delivery_command_ack_response_matches(
    const void *response, size_t response_bytes, const char *cmd_id,
    const char *expected_command_status,
    const char posted_ack_sha256[PHOTO_DELIVERY_SHA256_HEX_BYTES]);

/* A media record may be released only after this exact durable-content ACK. */
bool photo_delivery_content_ack_response_matches(
    const void *response, size_t response_bytes,
    const char *device_id, const char *photo_id,
    const char sha256_hex[PHOTO_DELIVERY_SHA256_HEX_BYTES],
    size_t payload_bytes);

#endif

#ifndef EGOLINK_PLATFORM_CAMERA_H
#define EGOLINK_PLATFORM_CAMERA_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PLATFORM_CAMERA_SHA256_BYTES 32U
#define PLATFORM_CAMERA_SHA256_HEX_BYTES 65U

typedef enum {
    PLATFORM_CAMERA_OK = 0,
    PLATFORM_CAMERA_DISABLED,
    PLATFORM_CAMERA_BLOCKED_SHARED_I2C_UNVERIFIED,
    PLATFORM_CAMERA_TRIAL_READY_UNVERIFIED,
    PLATFORM_CAMERA_TRIAL_ATTEMPT_CONSUMED,
    PLATFORM_CAMERA_BUSY,
    PLATFORM_CAMERA_I2C_BUS_UNAVAILABLE,
    PLATFORM_CAMERA_INIT_FAILED,
    PLATFORM_CAMERA_UNSUPPORTED_SENSOR,
    PLATFORM_CAMERA_CAPTURE_FAILED,
    PLATFORM_CAMERA_INVALID_JPEG,
    PLATFORM_CAMERA_CONSUMER_FAILED,
    PLATFORM_CAMERA_DEINIT_FAILED
} platform_camera_status_t;

typedef enum {
    /* Used only for recovered legacy capture provenance. Runtime policy never
     * returns this state for the current image. */
    PLATFORM_CAMERA_SHARED_I2C_UNKNOWN_LEGACY = 0,
    PLATFORM_CAMERA_SHARED_I2C_BLOCKED,
    PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED,
    PLATFORM_CAMERA_SHARED_I2C_VERIFIED
} platform_camera_shared_i2c_state_t;

typedef struct {
    platform_camera_status_t status;
    const char *reason;
    const char *pin_profile;
    const char *camera_model;
    uint16_t sensor_pid;
    int64_t capture_started_us;
    int64_t capture_completed_us;
    size_t jpeg_bytes;
    uint16_t width;
    uint16_t height;
    uint8_t pixel_format;
    uint8_t sha256[PLATFORM_CAMERA_SHA256_BYTES];
    char sha256_hex[PLATFORM_CAMERA_SHA256_HEX_BYTES];
    platform_camera_shared_i2c_state_t shared_i2c_state;
    bool attempted;
    bool frame_acquired;
    bool jpeg_markers_valid;
    bool framebuffer_returned;
    bool driver_deinitialized;
} platform_camera_capture_result_t;

/* The consumer runs synchronously while the sole framebuffer is borrowed.
 * It must perform bounded work and must not retain data after returning.
 * Only intrinsic frame fields (dimensions/format/bytes/SHA-256/timestamps)
 * are valid during this callback; return/deinit lifecycle fields are final
 * only after platform_camera_capture_single() returns. Persist the final
 * result separately rather than copying this in-callback snapshot. */
typedef bool (*platform_camera_frame_consumer_t)(
    void *context, const uint8_t *jpeg, size_t jpeg_bytes,
    const platform_camera_capture_result_t *metadata);

platform_camera_status_t platform_camera_preflight(const char **reason);
platform_camera_shared_i2c_state_t platform_camera_shared_i2c_state(void);
const char *platform_camera_shared_i2c_state_name(
    platform_camera_shared_i2c_state_t);
bool platform_camera_unverified_trial_attempt_consumed(void);
bool platform_camera_timed_capture_allowed(void);

/* Low-level capture seam. It does not receive or persist commands.
 * The collection runtime owns capture_photo_once/configure_photo_timer, binds the
 * authorization_session_id/retention fields, forces training_allowed=false,
 * validates trusted UTC expiry, and enforces restart/no-backfill semantics. */
platform_camera_status_t platform_camera_capture_single(
    platform_camera_frame_consumer_t, void *,
    platform_camera_capture_result_t *);
const char *platform_camera_status_name(platform_camera_status_t);

#endif

#ifndef EGOLINK_PLATFORM_POWER_H
#define EGOLINK_PLATFORM_POWER_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    PLATFORM_POWER_STATE_BOOT = 0,
    PLATFORM_POWER_STATE_ACTIVE,
    PLATFORM_POWER_STATE_GUARDING,
    PLATFORM_POWER_STATE_LIGHT_SLEEP,
    PLATFORM_POWER_STATE_DEEP_SLEEP,
    PLATFORM_POWER_STATE_NETWORK_ATTACH,
    PLATFORM_POWER_STATE_GNSS_FIX,
    PLATFORM_POWER_STATE_CAPTURE_AUDIO,
    PLATFORM_POWER_STATE_CAPTURE_IMAGE,
    PLATFORM_POWER_STATE_STORAGE_WRITE,
    PLATFORM_POWER_STATE_UPLOAD,
    PLATFORM_POWER_STATE_EMERGENCY,
    PLATFORM_POWER_STATE_COUNT,
} platform_power_state_t;

typedef enum {
    PLATFORM_POWER_EVENT_INIT = 0,
    PLATFORM_POWER_EVENT_ENTER,
    PLATFORM_POWER_EVENT_LEAVE,
    PLATFORM_POWER_EVENT_MARK,
} platform_power_event_kind_t;

typedef struct {
    uint32_t seq;
    const char *serial_marker_id;
    const char *gpio_marker_id;
    bool gpio_marker_enabled;
} platform_power_marker_t;

typedef struct {
    int battery_percent;
    int battery_millivolt;
    bool battery_voltage_valid;
    bool charging;
    bool battery_is_mock;
    bool charging_is_mock;
    const char *battery_source;
    const char *charging_source;
    platform_power_state_t state;
    uint32_t marker_seq;
    int64_t state_entered_uptime_ms;
    int64_t state_elapsed_ms;
    int64_t state_cumulative_ms;
    platform_power_marker_t marker;
} platform_power_snapshot_t;

bool platform_power_init(void);
void platform_power_enter_state(platform_power_state_t state, const char *reason);
void platform_power_leave_state(platform_power_state_t state, const char *reason);
void platform_power_mark(const char *marker, const char *detail);
void platform_power_get_snapshot(platform_power_snapshot_t *snapshot);
const char *platform_power_state_name(platform_power_state_t state);
const char *platform_power_event_kind_name(platform_power_event_kind_t kind);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_PLATFORM_POWER_H */

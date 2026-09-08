#pragma once
#include "driver/i2c.h"

/* Install a legacy master bus once. Identical callers share it; an already
 * installed conflicting configuration is rejected before changing any pins.
 * Only this seam may install the platform sensor buses. No delete/reconfigure.
 * Installation failures are returned unchanged and may be retried. */
esp_err_t platform_i2c_bus_ensure(i2c_port_t port, const i2c_config_t *config);

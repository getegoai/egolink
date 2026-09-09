#pragma once
#include <stdint.h>
#include "driver/i2c.h"

/* Install a legacy master bus once. Identical callers share it; an already
 * installed conflicting configuration is rejected before changing any pins.
 * Only this seam may install the platform sensor buses. No delete/reconfigure.
 * Installation failures are returned unchanged and may be retried. */
esp_err_t platform_i2c_bus_ensure(i2c_port_t port, const i2c_config_t *config);

/* Serialize complete transactions performed by platform clients with code
 * that uses the same legacy I2C driver directly (for example camera SCCB).
 * A lease never installs or reconfigures the bus and waits for at most
 * timeout_ms. Leases are deliberately non-recursive: acquire once around an
 * actual transaction or one externally implemented transaction sequence, and
 * release it from the same task. */
esp_err_t platform_i2c_bus_lease_acquire(i2c_port_t port, uint32_t timeout_ms);
esp_err_t platform_i2c_bus_lease_release(i2c_port_t port);

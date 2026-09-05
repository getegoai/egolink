/*
 * CALL-020G dedicated-image inert boot entry.
 *
 * Retaining the operator API in an ELF is not permission to touch hardware.
 * A later, explicitly authorized control seam must call prepare/start.  Until
 * then this entry deliberately installs no driver, creates no task and emits
 * no output.
 */

#include "sdkconfig.h"

#if !CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER
#error "CALL-020G boot stub is only valid in the dedicated runner profile"
#endif

void app_main(void)
{
}

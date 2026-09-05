#ifndef EGOLINK_PERSISTENT_PRIORITY_OUTBOX_PARTITION_H
#define EGOLINK_PERSISTENT_PRIORITY_OUTBOX_PARTITION_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"
#include "esp_partition.h"
#include "persistent_priority_outbox.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_OUTBOX_PARTITION_ADAPTER_VERSION \
    "egolink.persistent_priority_outbox.partition_adapter.v0.1"
#define EGOLINK_OUTBOX_PARTITION_LABEL "ego_outbox"
#define EGOLINK_OUTBOX_PARTITION_SUBTYPE UINT8_C(0x40)
#define EGOLINK_OUTBOX_PARTITION_ERASE_BYTES UINT32_C(4096)
#define EGOLINK_OUTBOX_PARTITION_SLOT_STRIDE_BYTES UINT32_C(24576)
#define EGOLINK_OUTBOX_PARTITION_BYTES UINT32_C(49152)
#define EGOLINK_OUTBOX_PARTITION_VERIFY_CHUNK_BYTES UINT32_C(256)

/*
 * One owner task, or a caller-owned mutex, must serialize this adapter with
 * the outbox core. It deliberately has no internal task, timer, allocation,
 * retry, erase-on-init or logging path.
 *
 * A write erases only the selected 24 KiB slot, writes the complete 22,240
 * byte image, then reads it back before returning success. After at least one
 * valid mirror exists, the outbox core writes the inactive mirror. A reset
 * during a later erase/write therefore leaves either the previous mirror or
 * the new hash-validated image as the recoverable state; a torn target is
 * never reported as committed.
 *
 * The first-ever empty-store initialization is a narrower case: reset during
 * the first slot write can leave one torn slot and one erased slot. The core
 * then fails closed with storage corruption; this adapter neither erases nor
 * automatically formats that state. Explicit provisioning/format recovery is
 * still required before product integration. There is no universal reset-
 * recovery claim for an unprovisioned partition.
 *
 * This adapter provides corruption detection and alternate-slot tear recovery
 * only. It does not enable or prove at-rest confidentiality, flash encryption,
 * key lifecycle, erase remanence, endurance, or brownout behavior. Those are
 * separate product-profile and hardware-verification decisions. Every durable
 * core mutation erases one six-sector 24 KiB slot and rewrites 22,240 bytes;
 * this is an engineering recovery backend, not an endurance-qualified backend
 * for normal location cadence.
 */
typedef struct {
    uint64_t slot_erase_attempts;
    uint64_t slot_erase_successes;
    uint64_t write_api_success_bytes;
    uint64_t readback_failures;
} egolink_outbox_partition_metrics_t;

typedef struct {
    const esp_partition_t *partition;
    bool initialized;
    egolink_outbox_partition_metrics_t metrics;
} egolink_outbox_partition_t;

const char *egolink_outbox_partition_adapter_version(void);

/* Read-only discovery and geometry validation. This function never erases. */
esp_err_t egolink_outbox_partition_init(
    egolink_outbox_partition_t *adapter);

/*
 * Exposes synchronous callbacks only after successful initialization. The
 * returned callback context remains caller-owned for the outbox lifetime.
 */
esp_err_t egolink_outbox_partition_storage(
    egolink_outbox_partition_t *adapter,
    egolink_outbox_storage_t *storage);

/*
 * Copies RAM-only, saturating write-amplification counters. They reset during
 * adapter initialization/reboot and contain no payload bytes. They are
 * diagnostic metadata only, not persistent lifetime/endurance accounting.
 */
esp_err_t egolink_outbox_partition_get_metrics(
    const egolink_outbox_partition_t *adapter,
    egolink_outbox_partition_metrics_t *metrics);

#ifdef __cplusplus
}
#endif

#endif

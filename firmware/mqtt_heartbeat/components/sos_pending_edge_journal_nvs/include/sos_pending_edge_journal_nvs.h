#ifndef EGOLINK_SOS_PENDING_EDGE_JOURNAL_NVS_H
#define EGOLINK_SOS_PENDING_EDGE_JOURNAL_NVS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "sos_pending_edge_journal.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_SOS_PENDING_EDGE_NVS_PARTITION_LABEL "nvs"
#define EGOLINK_SOS_PENDING_EDGE_NVS_NAMESPACE "ego_sos_pend"
#define EGOLINK_SOS_PENDING_EDGE_NVS_KEY "edge_v1"
#define EGOLINK_SOS_PENDING_EDGE_NVS_CONTEXT_BYTES 192U

typedef enum {
    EGOLINK_SOS_PENDING_EDGE_NVS_OK = 0,
    EGOLINK_SOS_PENDING_EDGE_NVS_INVALID_ARGUMENT,
    EGOLINK_SOS_PENDING_EDGE_NVS_NOT_INITIALIZED,
} egolink_sos_pending_edge_nvs_status_t;

/*
 * RAM-only saturating diagnostic counters. They reset at adapter init, contain
 * no payload or identity, and are not persistent lifetime/endurance evidence.
 */
typedef struct {
    uint64_t load_attempts;
    uint64_t load_successes;
    uint64_t load_not_found;
    uint64_t load_failures;
    uint64_t size_mismatches;
    uint64_t store_attempts;
    uint64_t set_blob_successes;
    uint64_t store_commit_successes;
    uint64_t store_failures;
    uint64_t clear_attempts;
    uint64_t erase_key_successes;
    uint64_t clear_commit_successes;
    uint64_t clear_not_found;
    uint64_t clear_failures;
    uint64_t handles_opened;
    uint64_t handles_closed;
    uint64_t blob_read_success_bytes;
    uint64_t blob_set_success_bytes;
} egolink_sos_pending_edge_nvs_metrics_t;

typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_SOS_PENDING_EDGE_NVS_CONTEXT_BYTES];
} egolink_sos_pending_edge_nvs_t;

/*
 * Init only clears caller-owned RAM and returns callback bindings. It does not
 * open, initialize, erase, format or otherwise access NVS. The composition
 * root must initialize partition "nvs" before invoking a callback. Only store
 * may create namespace "ego_sos_pend"; load and an absent clear are read-only.
 * Reinitialization is allowed only while no journal retains the old binding.
 *
 * Every successful NVS open is closed before a callback returns. This adapter
 * retains no handle and creates no task. One external owner task or mutex must
 * serialize it with the journal, F runtime, outbox, dispatcher and ACK path;
 * no callback may re-enter those objects or mutate this private namespace/key.
 */
egolink_sos_pending_edge_nvs_status_t
egolink_sos_pending_edge_nvs_init(
    egolink_sos_pending_edge_nvs_t *adapter,
    egolink_sos_pending_edge_storage_t *storage_out);

bool egolink_sos_pending_edge_nvs_is_initialized(
    const egolink_sos_pending_edge_nvs_t *adapter);

egolink_sos_pending_edge_nvs_status_t
egolink_sos_pending_edge_nvs_get_metrics(
    const egolink_sos_pending_edge_nvs_t *adapter,
    egolink_sos_pending_edge_nvs_metrics_t *metrics_out);

const char *egolink_sos_pending_edge_nvs_status_name(
    egolink_sos_pending_edge_nvs_status_t status);

/*
 * `nvs_set_blob`/`nvs_erase_key` followed by a successful `nvs_commit` is the
 * exact ESP-IDF API boundary used here. A callback error, including commit
 * failure, is deliberately ambiguous; the G core must perform its existing
 * exact readback. This build-only adapter does not claim brownout atomicity,
 * flash endurance, flash encryption, key lifecycle or secure erase behavior.
 */

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SOS_PENDING_EDGE_JOURNAL_NVS_H */

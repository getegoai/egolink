#ifndef EGOLINK_SOS_OUTBOX_ADAPTER_H
#define EGOLINK_SOS_OUTBOX_ADAPTER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "persistent_priority_outbox.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_SOS_OUTBOX_ADAPTER_CONTRACT_VERSION \
    "egolink.sos_outbox_adapter.v0.1"
#define EGOLINK_SOS_OUTBOX_DELIVERY_SCOPE \
    "server_durable_ingest_only"
#define EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES 2048U
#define EGOLINK_SOS_OUTBOX_JSON_SAFE_INTEGER_MAX \
    UINT64_C(9007199254740991)

typedef enum {
    EGOLINK_SOS_OUTBOX_BEGIN_READY = 0,
    EGOLINK_SOS_OUTBOX_BEGIN_NO_DUE_RECORD,
    EGOLINK_SOS_OUTBOX_BEGIN_NON_SOS_HEAD,
    EGOLINK_SOS_OUTBOX_BEGIN_ATTEMPT_ALREADY_ACTIVE,
    EGOLINK_SOS_OUTBOX_BEGIN_INVALID_SOS_RETAINED,
    EGOLINK_SOS_OUTBOX_BEGIN_OUTBOX_STATE_FAILED,
    EGOLINK_SOS_OUTBOX_BEGIN_INVALID_ARGUMENT,
    EGOLINK_SOS_OUTBOX_BEGIN_NOT_INITIALIZED,
} egolink_sos_outbox_begin_status_t;

typedef enum {
    EGOLINK_SOS_OUTBOX_FINISH_ACK_DELETED = 0,
    EGOLINK_SOS_OUTBOX_FINISH_ACK_ALREADY_APPLIED,
    EGOLINK_SOS_OUTBOX_FINISH_HTTP_REJECTED_RETAINED,
    EGOLINK_SOS_OUTBOX_FINISH_INVALID_RESPONSE_RETAINED,
    EGOLINK_SOS_OUTBOX_FINISH_INVALID_RESULT_RETAINED,
    EGOLINK_SOS_OUTBOX_FINISH_INVALID_SCOPE_RETAINED,
    EGOLINK_SOS_OUTBOX_FINISH_INVALID_ACK_RETAINED,
    EGOLINK_SOS_OUTBOX_FINISH_IDENTITY_MISMATCH_RETAINED,
    EGOLINK_SOS_OUTBOX_FINISH_ACK_STATE_FAILED,
    EGOLINK_SOS_OUTBOX_FINISH_TRANSPORT_STATE_FAILED,
    EGOLINK_SOS_OUTBOX_FINISH_ATTEMPT_MISMATCH,
    EGOLINK_SOS_OUTBOX_FINISH_NO_ACTIVE_ATTEMPT,
    EGOLINK_SOS_OUTBOX_FINISH_INVALID_ARGUMENT,
    EGOLINK_SOS_OUTBOX_FINISH_NOT_INITIALIZED,
} egolink_sos_outbox_finish_status_t;

typedef enum {
    EGOLINK_SOS_OUTBOX_SERVER_RESULT_NONE = 0,
    EGOLINK_SOS_OUTBOX_SERVER_RESULT_ACCEPTED,
    EGOLINK_SOS_OUTBOX_SERVER_RESULT_DUPLICATE,
} egolink_sos_outbox_server_result_t;

/*
 * This adapter binds, but does not initialize or own, the shared outbox.
 * device_id must exactly equal both the outbox configuration identity and the
 * SOS orchestrator's copied payload identity. The outbox currently exposes no
 * read API that can prove this integration invariant at bind time.
 *
 * No payload bytes are retained here. active_* fields bind one in-flight
 * attempt to its eventual HTTP result and positive ACK.
 */
typedef struct {
    egolink_outbox_t *outbox;
    char device_id[EGOLINK_OUTBOX_ID_CAPACITY];
    bool initialized;
    bool attempt_active;
    char active_attempt_token[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    char active_event_id[EGOLINK_OUTBOX_ID_CAPACITY];
    char active_payload_sha256[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    size_t active_payload_length;
} egolink_sos_outbox_adapter_t;

/*
 * All pointers borrow the caller-owned send_item and adapter. payload is the
 * exact persisted byte range and is not NUL-terminated. It must be transmitted
 * byte-for-byte with payload_length and is valid only until send_item is wiped
 * or reused. This view is produced only for a validated CRITICAL manual_sos
 * head; it is never produced for another event type.
 */
typedef struct {
    const uint8_t *payload;
    size_t payload_length;
    const char *device_id;
    const char *event_id;
    const char *payload_sha256;
    const char *attempt_token;
} egolink_sos_outbox_send_view_t;

typedef struct {
    egolink_outbox_status_t outbox_status;
    bool invalid_sos_settlement_attempted;
    egolink_outbox_status_t invalid_sos_settlement_status;
} egolink_sos_outbox_begin_result_t;

typedef struct {
    egolink_outbox_status_t transport_status;
    egolink_sos_outbox_server_result_t server_result;
    bool ack_handler_called;
    egolink_outbox_status_t ack_status;
} egolink_sos_outbox_finish_result_t;

/* Binding is memory-only and does not initialize/deinitialize shared storage. */
egolink_outbox_status_t egolink_sos_outbox_adapter_bind(
    egolink_sos_outbox_adapter_t *adapter,
    egolink_outbox_t *already_initialized_outbox,
    const char *device_id);

void egolink_sos_outbox_adapter_unbind(
    egolink_sos_outbox_adapter_t *adapter);

/* Non-optimizable wipe for the payload-bearing, caller-owned send buffer. */
void egolink_sos_outbox_clear_send_item(
    egolink_outbox_send_item_t *send_item);

/*
 * Calls the shared outbox's priority selector, which durably starts an attempt
 * before returning bytes. If the selected head is not manual_sos, this returns
 * NON_SOS_HEAD, leaves send_view empty and leaves send_item intact so the one
 * owner can route or explicitly fail that already-started attempt. It must not
 * call this SOS completion API for such an item.
 *
 * A selected manual_sos must be CRITICAL, boot-monotonic and use the exact
 * orchestrator event-id lineage. Its bounded JSON subset and device/event/
 * boot/session/sequence/time identity must match this adapter and the record;
 * parsing uses bounded cJSON heap. Invalid SOS metadata/hash/payload is
 * explicitly settled as a failed transport attempt and retained for retry.
 */
egolink_sos_outbox_begin_status_t egolink_sos_outbox_begin_attempt(
    egolink_sos_outbox_adapter_t *adapter,
    uint64_t now_ms,
    egolink_outbox_send_item_t *send_item,
    egolink_sos_outbox_send_view_t *send_view,
    egolink_sos_outbox_begin_result_t *result);

/*
 * Exactly one owner must serialize orchestrator enqueue, begin, transport and
 * finish with every other outbox call. attempt_token must match the active
 * send view. A non-2xx status records a failed transport and retains the item.
 * A 2xx response is parsed and matched in memory first. Invalid application
 * responses are durably classified as failed attempts so they return to
 * RETRY_WAIT. Only a strict SOS-010D accepted/duplicate response whose
 * device_id, event_id and exact-request payload_sha256 match the active
 * attempt is recorded as transport-accepted and passed to positive ACK.
 *
 * A successfully recorded failure, or a successful ACK deletion, securely
 * wipes send_item and clears the active view. If the transport-state or ACK
 * deletion commit fails, the item/view are retained. The current outbox core
 * latches storage-write faults, so recovery then requires core re-init from a
 * valid mirror and a new attempt; this adapter does not claim same-instance
 * recovery. Invalid preconditions also leave the active item untouched. This
 * is at-least-once delivery plumbing, not Guardian acknowledgement, Call
 * success or exactly-once execution.
 */
egolink_sos_outbox_finish_status_t egolink_sos_outbox_finish_attempt(
    egolink_sos_outbox_adapter_t *adapter,
    const char *attempt_token,
    uint16_t http_status_code,
    const char *transport_error_code,
    const uint8_t *response_json,
    size_t response_length,
    uint64_t now_ms,
    egolink_outbox_send_item_t *send_item,
    egolink_sos_outbox_finish_result_t *result);

const char *egolink_sos_outbox_begin_status_name(
    egolink_sos_outbox_begin_status_t status);
const char *egolink_sos_outbox_finish_status_name(
    egolink_sos_outbox_finish_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SOS_OUTBOX_ADAPTER_H */

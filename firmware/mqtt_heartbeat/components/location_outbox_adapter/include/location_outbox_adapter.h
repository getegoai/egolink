#ifndef EGOLINK_LOCATION_OUTBOX_ADAPTER_H
#define EGOLINK_LOCATION_OUTBOX_ADAPTER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "location_state_emitter.h"
#include "persistent_priority_outbox.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_LOCATION_OUTBOX_EVENT_TYPE "location_state"
#define EGOLINK_LOCATION_OUTBOX_EVENT_PREFIX "loc-"
#define EGOLINK_LOCATION_OUTBOX_ACK_PREFIX "ack-"
#define EGOLINK_LOCATION_OUTBOX_DELIVERY_SCOPE \
    "server_durable_ingest_only"
#define EGOLINK_LOCATION_OUTBOX_EVENT_ID_CAPACITY 69U
#define EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES 8192U
#define EGOLINK_LOCATION_OUTBOX_JSON_SAFE_INTEGER_MAX \
    UINT64_C(9007199254740991)

/*
 * SOS_ESCALATED consumes critical outbox reserve for this location-state
 * record. It does not turn the record into a manual_sos event; the physical
 * SOS contract and durable SOS event remain separately owned by SOS-010.
 */
typedef enum {
    EGOLINK_LOCATION_OUTBOX_NORMAL = 0,
    EGOLINK_LOCATION_OUTBOX_SOS_ESCALATED,
} egolink_location_outbox_urgency_t;

typedef enum {
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_OK = 0,
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_DUPLICATE,
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVALID_ARGUMENT,
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_EMIT_FAILED,
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_PAYLOAD_TOO_LARGE,
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_CRYPTO_FAILED,
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_OUTBOX_FAILED,
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_INVARIANT_FAILED,
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_NOT_INITIALIZED,
    EGOLINK_LOCATION_OUTBOX_ENQUEUE_DEVICE_MISMATCH,
} egolink_location_outbox_enqueue_status_t;

/*
 * This adapter owns initialization of the supplied outbox object so its
 * device identity can be checked before a location payload is persisted.
 * Callers must not initialize or mutate that outbox through a parallel path.
 */
typedef struct {
    egolink_outbox_t *outbox;
    char device_id[EGOLINK_OUTBOX_ID_CAPACITY];
    bool initialized;
} egolink_location_outbox_adapter_t;

typedef struct {
    egolink_location_state_emit_result_t emit_status;
    egolink_outbox_status_t outbox_status;
    egolink_outbox_priority_t priority;
    size_t payload_length;
    char payload_sha256[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    char event_id[EGOLINK_LOCATION_OUTBOX_EVENT_ID_CAPACITY];
} egolink_location_outbox_enqueue_result_t;

typedef enum {
    EGOLINK_LOCATION_OUTBOX_FINISH_ACK_DELETED = 0,
    EGOLINK_LOCATION_OUTBOX_FINISH_ACK_ALREADY_APPLIED,
    EGOLINK_LOCATION_OUTBOX_FINISH_TRANSPORT_REJECTED_RETAINED,
    EGOLINK_LOCATION_OUTBOX_FINISH_TRANSPORT_STATE_FAILED,
    EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_RESPONSE,
    EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_SCOPE,
    EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ACK,
    EGOLINK_LOCATION_OUTBOX_FINISH_ACK_STATE_FAILED,
    EGOLINK_LOCATION_OUTBOX_FINISH_INVALID_ARGUMENT,
} egolink_location_outbox_finish_status_t;

typedef struct {
    egolink_outbox_status_t transport_status;
    bool ack_handler_called;
    egolink_outbox_status_t ack_status;
} egolink_location_outbox_finish_result_t;

egolink_outbox_status_t egolink_location_outbox_adapter_init(
    egolink_location_outbox_adapter_t *adapter,
    egolink_outbox_t *outbox,
    const egolink_outbox_config_t *config,
    const egolink_outbox_storage_t *storage,
    uint64_t runtime_epoch,
    uint64_t now_ms,
    egolink_outbox_init_report_t *report);

void egolink_location_outbox_adapter_deinit(
    egolink_location_outbox_adapter_t *adapter);

/*
 * Emit into caller-owned scratch, SHA-256 those exact bytes, derive
 * loc-<lowercase sha256>, then durably enqueue before any send is possible.
 * scratch is cleared before return on both success and failure. Allocate at
 * least EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES + 1 bytes to admit the current
 * outbox ceiling without truncation.
 */
egolink_location_outbox_enqueue_status_t
egolink_location_outbox_emit_and_enqueue(
    egolink_location_outbox_adapter_t *adapter,
    const egolink_location_state_emit_input_t *input,
    egolink_location_outbox_urgency_t urgency,
    uint64_t now_ms,
    char *scratch,
    size_t scratch_capacity,
    egolink_location_outbox_enqueue_result_t *result);

/*
 * accepted_by_transport must mean a caller-validated successful HTTP or
 * equivalent transport result. A non-2xx HTTP result must pass false and a
 * bounded outbox-safe error code. Transport acceptance only records
 * AWAITING_POSITIVE_ACK. It never deletes.
 *
 * Only after that durable state update succeeds does this function parse the
 * bounded response. Deletion requires ok=true, the exact delivery scope, an
 * exact seven-field accepted ACK contract, ack-/loc- hash-derived IDs, and
 * the outbox core's exact device/event/payload-hash match. Missing, malformed,
 * negative, mismatched or non-transport-accepted responses retain the record.
 */
egolink_location_outbox_finish_status_t
egolink_location_outbox_finish_attempt(
    egolink_location_outbox_adapter_t *adapter,
    const char *attempt_token,
    bool accepted_by_transport,
    const char *transport_error_code,
    const uint8_t *response_json,
    size_t response_length,
    uint64_t now_ms,
    egolink_location_outbox_finish_result_t *result);

/*
 * No function here is re-entrant. One owner task or caller-owned mutex must
 * serialize this adapter, its emitter input lineage, policy-core events and
 * every outbox API call. Replays must be deduplicated before policy reduction.
 * Durable identity and idempotent ACKs are at-least-once mechanics and do not
 * provide exactly-once delivery.
 */

const char *egolink_location_outbox_enqueue_status_name(
    egolink_location_outbox_enqueue_status_t status);
const char *egolink_location_outbox_finish_status_name(
    egolink_location_outbox_finish_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_LOCATION_OUTBOX_ADAPTER_H */

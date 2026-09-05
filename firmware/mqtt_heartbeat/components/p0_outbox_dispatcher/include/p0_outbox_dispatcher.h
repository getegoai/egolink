#ifndef EGOLINK_P0_OUTBOX_DISPATCHER_H
#define EGOLINK_P0_OUTBOX_DISPATCHER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "location_outbox_adapter.h"
#include "sos_outbox_adapter.h"

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_P0_OUTBOX_DISPATCHER_CONTRACT_VERSION \
    "egolink.p0_outbox_dispatcher.v0.1"
#define EGOLINK_P0_OUTBOX_DISPATCHER_CONTEXT_BYTES (8U * 1024U)
#define EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH \
    "/api/v1/safety-events/manual-sos"
#define EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH "/api/v1/location-states"

typedef enum {
    EGOLINK_P0_OUTBOX_DISPATCHER_NEVER_INITIALIZED = 0,
    EGOLINK_P0_OUTBOX_DISPATCHER_DISABLED,
    EGOLINK_P0_OUTBOX_DISPATCHER_ACTIVE,
    EGOLINK_P0_OUTBOX_DISPATCHER_CLOSED,
} egolink_p0_outbox_dispatcher_lifecycle_t;

typedef enum {
    EGOLINK_P0_OUTBOX_ROUTE_NONE = 0,
    EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS,
    EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE,
    EGOLINK_P0_OUTBOX_ROUTE_INVALID_RETAINED,
} egolink_p0_outbox_route_t;

typedef enum {
    EGOLINK_P0_OUTBOX_PHASE_IDLE = 0,
    EGOLINK_P0_OUTBOX_PHASE_SEND_READY,
    EGOLINK_P0_OUTBOX_PHASE_RECOVERY_REQUIRED,
} egolink_p0_outbox_phase_t;

typedef enum {
    EGOLINK_P0_OUTBOX_OK = 0,
    EGOLINK_P0_OUTBOX_BEGIN_READY,
    EGOLINK_P0_OUTBOX_NO_DUE_RECORD,
    EGOLINK_P0_OUTBOX_INVALID_EVENT_RETAINED,
    EGOLINK_P0_OUTBOX_ACK_DELETED,
    EGOLINK_P0_OUTBOX_ACK_ALREADY_APPLIED,
    EGOLINK_P0_OUTBOX_FINISHED_RETAINED,
    EGOLINK_P0_OUTBOX_CANCELLED_RETAINED,
    EGOLINK_P0_OUTBOX_MUST_FINISH_OR_RECOVER,
    EGOLINK_P0_OUTBOX_ATTEMPT_ALREADY_ACTIVE,
    EGOLINK_P0_OUTBOX_ATTEMPT_MISMATCH,
    EGOLINK_P0_OUTBOX_DEPENDENCY_RECOVERY_REQUIRED,
    EGOLINK_P0_OUTBOX_DEPENDENCY_MISMATCH,
    EGOLINK_P0_OUTBOX_DISABLED_STATUS,
    EGOLINK_P0_OUTBOX_CLOSED_STATUS,
    EGOLINK_P0_OUTBOX_INVALID_ARGUMENT,
    EGOLINK_P0_OUTBOX_NOT_INITIALIZED,
    EGOLINK_P0_OUTBOX_ALREADY_INITIALIZED,
    EGOLINK_P0_OUTBOX_REENTRANT_CALL,
} egolink_p0_outbox_dispatcher_status_t;

typedef struct {
    egolink_p0_outbox_route_t route;
    char device_id[EGOLINK_OUTBOX_ID_CAPACITY];
    char event_id[EGOLINK_OUTBOX_ID_CAPACITY];
    char payload_sha256[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    char attempt_token[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    egolink_outbox_priority_t priority;
    egolink_outbox_source_time_kind_t source_time_kind;
    uint64_t source_event_time_ms;
    uint64_t boot_count;
    char session_id[EGOLINK_OUTBOX_ID_CAPACITY];
    uint64_t source_sequence;
    uint32_t attempt_count;
} egolink_p0_outbox_attempt_identity_t;

/*
 * payload borrows the dispatcher's private canonical send item and is valid
 * only until finish/cancel/close or the next documented invalidation. It is
 * the exact persisted byte range and is not NUL-terminated. endpoint_path is
 * a fixed same-service relative path. response_max_bytes is a hard parser
 * ceiling, not permission to allocate that amount on a task stack.
 *
 * No bearer, Guardian, device-authentication or transport credential is
 * present. attempt_token is an outbox attempt identity, not an auth token.
 */
typedef struct {
    const uint8_t *payload;
    size_t payload_length;
    const char *endpoint_path;
    size_t response_max_bytes;
    bool completion_only;
    egolink_p0_outbox_attempt_identity_t attempt;
} egolink_p0_outbox_send_view_t;

typedef struct {
    bool enabled;
} egolink_p0_outbox_dispatcher_config_t;

typedef struct {
    egolink_p0_outbox_dispatcher_status_t status;
    egolink_p0_outbox_route_t route;
    egolink_sos_outbox_begin_status_t sos_begin_status;
    egolink_sos_outbox_begin_result_t sos_begin_result;
    egolink_outbox_status_t invalid_event_settlement_status;
    bool exact_payload_borrowed;
    bool durable_failure_recorded;
    bool durable_record_retained;
} egolink_p0_outbox_begin_result_t;

typedef struct {
    egolink_p0_outbox_dispatcher_status_t status;
    egolink_p0_outbox_route_t route;
    egolink_sos_outbox_finish_status_t sos_finish_status;
    egolink_sos_outbox_finish_result_t sos_finish_result;
    egolink_location_outbox_finish_status_t location_finish_status;
    egolink_location_outbox_finish_result_t location_finish_result;
    bool terminal;
    bool durable_record_retained;
    bool deleted_after_server_durable_ingest_ack;
    bool private_canonical_item_retained;
} egolink_p0_outbox_finish_result_t;

/* No payload bytes or coordinates are exposed through this snapshot. */
typedef struct {
    egolink_p0_outbox_dispatcher_lifecycle_t lifecycle;
    egolink_p0_outbox_dispatcher_status_t last_status;
    egolink_p0_outbox_phase_t phase;
    egolink_p0_outbox_route_t active_route;
    bool enabled;
    bool dependency_bound;
    bool busy;
    bool private_canonical_item_retained;
    egolink_p0_outbox_attempt_identity_t active_attempt;
    uint64_t begin_calls;
    uint64_t ready_manual_sos;
    uint64_t ready_location_state;
    uint64_t no_due_records;
    uint64_t invalid_events_retained;
    uint64_t finish_calls;
    uint64_t server_durable_ack_deletes;
    uint64_t retained_finishes;
    uint64_t recovery_required;
} egolink_p0_outbox_dispatcher_snapshot_t;

typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_P0_OUTBOX_DISPATCHER_CONTEXT_BYTES];
} egolink_p0_outbox_dispatcher_t;

void egolink_p0_outbox_dispatcher_default_config(
    egolink_p0_outbox_dispatcher_config_t *config);

/*
 * Enabled binding requires both already-initialized adapters to point to the
 * exact same shared_outbox, to carry the same device ID, and to have no SOS
 * attempt already active. This component never initializes, unbinds, closes
 * or deinitializes the adapters, outbox or storage backend.
 *
 * One caller task or caller-owned mutex must serialize every API call on this
 * dispatcher, the shared outbox and both adapters. A delivery runtime may
 * retain the one active borrowed send view while that owner is released and
 * transport reads the dispatcher's private canonical send item: the item is
 * an immutable copy and is not changed by a separately serialized outbox
 * enqueue. During that lease no other code may call dispatcher begin, finish,
 * cancel or close, unbind an adapter, or deinitialize the shared outbox. The
 * same SOS adapter may also be borrowed by the SOS runtime for identity/
 * lifecycle checks, but only this dispatcher owner may invoke its begin/finish
 * send APIs; no second adapter or selector is allowed. The local busy
 * bit only rejects recursive entry and is not a lock.
 */
egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_init(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    const egolink_p0_outbox_dispatcher_config_t *config,
    egolink_outbox_t *shared_outbox,
    egolink_location_outbox_adapter_t *location_adapter,
    egolink_sos_outbox_adapter_t *sos_adapter);

/*
 * Calls SOS-010E begin exactly once. Its NON_SOS_HEAD result is the sole hand-
 * off for validating/routing a location_state; selector/begin is never
 * duplicated. Only manual_sos and location_state can produce a send view.
 * Unknown or route-invalid records are durably marked failed and retained.
 * A routed location_state is checked against its record metadata and the
 * SHA-256 of the exact persisted bytes. Full envelope semantics remain the
 * responsibility of the only admitted producer, location_outbox_adapter.
 */
egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_begin(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_begin_result_t *result);

/*
 * The active route, attempt token, event ID and payload hash must exactly
 * match send_view. The route cannot be selected by the transport caller.
 * manual_sos delegates only to the strict SOS finish contract; location_state
 * delegates only to the location finish contract. HTTP/transport success is
 * never itself a deletion or Guardian/human acknowledgement.
 *
 * Caller-visible payload fields are invalidated before settlement. Terminal
 * results securely wipe the private send item and full view. If SOS finish
 * reports a storage-state failure, its existing contract requires the private
 * canonical item to remain for exact retry/recovery; the outward payload view
 * remains invalid. The dispatcher then returns MUST_FINISH_OR_RECOVER and will
 * not begin another attempt. A Location invalid response/scope/ACK or a
 * durably classified identity/stale ACK rejection is a terminal retained
 * result for that attempt: it does not delete, and the core may select a new
 * attempt only after its already-persisted retry deadline. Only an outbox
 * storage/fault/crypto/counter/state-uncertain result enters recovery.
 */
egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_finish(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    egolink_p0_outbox_send_view_t *send_view,
    uint16_t http_status_code,
    const char *transport_error_code,
    const uint8_t *response_json,
    size_t response_length,
    uint64_t now_ms,
    egolink_p0_outbox_finish_result_t *result);

/*
 * cancel safely records an unsent SEND_READY attempt as a durable transport
 * failure. It cannot downgrade an attempt whose acceptance/ACK persistence is
 * uncertain; that returns MUST_FINISH_OR_RECOVER with identity retained.
 * close uses the same rule and remains active until settlement succeeds.
 */
egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_cancel(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_finish_result_t *result);

egolink_p0_outbox_dispatcher_status_t egolink_p0_outbox_dispatcher_close(
    egolink_p0_outbox_dispatcher_t *dispatcher,
    uint64_t now_ms,
    egolink_p0_outbox_send_view_t *send_view,
    egolink_p0_outbox_finish_result_t *result);

egolink_p0_outbox_dispatcher_status_t
egolink_p0_outbox_dispatcher_current_status(
    const egolink_p0_outbox_dispatcher_t *dispatcher,
    egolink_p0_outbox_dispatcher_snapshot_t *snapshot);

/*
 * Read-only exact pointer proof for a higher-level single-owner composition.
 * True requires this active dispatcher to retain the exact shared outbox and
 * exact Location adapter and for all adapter bindings to remain valid. It
 * performs no selector, storage or transport operation.
 */
bool egolink_p0_outbox_dispatcher_dependencies_match(
    const egolink_p0_outbox_dispatcher_t *dispatcher,
    const egolink_outbox_t *shared_outbox,
    const egolink_location_outbox_adapter_t *location_adapter);

void egolink_p0_outbox_dispatcher_clear_send_view(
    egolink_p0_outbox_send_view_t *send_view);

const char *egolink_p0_outbox_dispatcher_status_name(
    egolink_p0_outbox_dispatcher_status_t status);
const char *egolink_p0_outbox_route_name(egolink_p0_outbox_route_t route);
const char *egolink_p0_outbox_phase_name(egolink_p0_outbox_phase_t phase);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_P0_OUTBOX_DISPATCHER_H */

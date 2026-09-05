#ifndef EGOLINK_PERSISTENT_PRIORITY_OUTBOX_H
#define EGOLINK_PERSISTENT_PRIORITY_OUTBOX_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EGOLINK_OUTBOX_STORAGE_CONTRACT_VERSION \
    "egolink.persistent_priority_outbox.device_storage.v0.1"
#define EGOLINK_OUTBOX_RECORD_CONTRACT_VERSION \
    "egolink.persistent_priority_outbox.record.v0.1"
#define EGOLINK_OUTBOX_ACK_CONTRACT_VERSION \
    "egolink.persistent_priority_outbox.ack.v0.1"

/* Compile-time safety ceilings, not product queue-sizing claims. */
#define EGOLINK_OUTBOX_SLOT_COUNT 2U
#define EGOLINK_OUTBOX_MAX_RECORDS 4U
#define EGOLINK_OUTBOX_MAX_TOMBSTONES 8U
#define EGOLINK_OUTBOX_ID_CAPACITY 129U
#define EGOLINK_OUTBOX_EVENT_TYPE_CAPACITY 129U
#define EGOLINK_OUTBOX_ERROR_CODE_CAPACITY 65U
#define EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES 4096U
#define EGOLINK_OUTBOX_SHA256_BYTES 32U
#define EGOLINK_OUTBOX_SHA256_HEX_CAPACITY 65U
#define EGOLINK_OUTBOX_CORE_STORAGE_BYTES (48U * 1024U)
#define EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES 22240U

/*
 * This core has no internal lock and none of its APIs are re-entrant. One
 * owner task, or a caller-owned mutex, must serialize every API call from LOC,
 * SOS, send and ACK paths. Storage callbacks are synchronous and must not call
 * back into this core.
 *
 * runtime_epoch is a nonzero boot/session ordinal that must never decrease
 * relative to stored state. now_ms must be monotonic within that epoch.
 */

typedef enum {
    EGOLINK_OUTBOX_STORAGE_OK = 0,
    EGOLINK_OUTBOX_STORAGE_NOT_FOUND,
    EGOLINK_OUTBOX_STORAGE_IO_ERROR,
} egolink_outbox_storage_result_t;

/*
 * write_slot must atomically replace exactly one logical slot and return OK
 * only after that slot is durable according to the adapter's documented
 * guarantee. Each slot must hold EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES exact
 * bytes; two slots and backend metadata/atomicity overhead are required. The
 * core never interprets a successful transport send as a storage commit. This
 * component does not provide an NVS adapter or claim compatibility with the
 * current firmware partition table.
 */
typedef egolink_outbox_storage_result_t (*egolink_outbox_read_slot_fn)(
    void *context,
    uint8_t slot,
    void *destination,
    size_t destination_capacity,
    size_t *actual_length);

typedef egolink_outbox_storage_result_t (*egolink_outbox_write_slot_fn)(
    void *context,
    uint8_t slot,
    const void *source,
    size_t source_length);

typedef struct {
    void *context;
    egolink_outbox_read_slot_fn read_slot;
    egolink_outbox_write_slot_fn write_slot;
} egolink_outbox_storage_t;

typedef struct {
    const char *device_id;
    uint16_t max_records;
    uint16_t reserved_critical_records;
    uint32_t max_total_payload_bytes;
    uint16_t max_payload_bytes;
    uint64_t base_retry_ms;
    uint64_t max_retry_ms;
    uint16_t tombstone_capacity;
} egolink_outbox_config_t;

typedef enum {
    EGOLINK_OUTBOX_PRIORITY_INFO = 0,
    EGOLINK_OUTBOX_PRIORITY_NORMAL,
    EGOLINK_OUTBOX_PRIORITY_WARNING,
    EGOLINK_OUTBOX_PRIORITY_HIGH,
    EGOLINK_OUTBOX_PRIORITY_CRITICAL,
} egolink_outbox_priority_t;

typedef enum {
    EGOLINK_OUTBOX_PAYLOAD_EVENT_JSON = 0,
    EGOLINK_OUTBOX_PAYLOAD_RTC_MEDIA,
    EGOLINK_OUTBOX_PAYLOAD_AUDIO,
    EGOLINK_OUTBOX_PAYLOAD_IMAGE,
    EGOLINK_OUTBOX_PAYLOAD_VIDEO,
} egolink_outbox_payload_kind_t;

typedef enum {
    EGOLINK_OUTBOX_SOURCE_TIME_UTC_MS = 0,
    EGOLINK_OUTBOX_SOURCE_TIME_BOOT_MONOTONIC_MS,
} egolink_outbox_source_time_kind_t;

typedef enum {
    EGOLINK_OUTBOX_SEND_QUEUED = 0,
    EGOLINK_OUTBOX_SEND_ATTEMPT_STARTED,
    EGOLINK_OUTBOX_SEND_RETRY_WAIT,
    EGOLINK_OUTBOX_SEND_AWAITING_POSITIVE_ACK,
} egolink_outbox_send_state_t;

typedef enum {
    EGOLINK_OUTBOX_ATTEMPT_NOT_ATTEMPTED = 0,
    EGOLINK_OUTBOX_ATTEMPT_PENDING,
    EGOLINK_OUTBOX_ATTEMPT_FAILED,
    EGOLINK_OUTBOX_ATTEMPT_TRANSPORT_ACCEPTED,
} egolink_outbox_attempt_result_t;

typedef enum {
    EGOLINK_OUTBOX_ACK_ACCEPTED = 0,
    EGOLINK_OUTBOX_ACK_REJECTED,
} egolink_outbox_ack_status_t;

typedef enum {
    EGOLINK_OUTBOX_SLOT_NOT_READ = 0,
    EGOLINK_OUTBOX_SLOT_NOT_FOUND,
    EGOLINK_OUTBOX_SLOT_VALID,
    EGOLINK_OUTBOX_SLOT_IO_ERROR,
    EGOLINK_OUTBOX_SLOT_SIZE_MISMATCH,
    EGOLINK_OUTBOX_SLOT_CORRUPT,
    EGOLINK_OUTBOX_SLOT_CONFIG_MISMATCH,
} egolink_outbox_slot_state_t;

typedef enum {
    EGOLINK_OUTBOX_RECOVERY_NONE = 0,
    EGOLINK_OUTBOX_RECOVERY_NEW_MIRRORS,
    EGOLINK_OUTBOX_RECOVERY_EQUAL_MIRRORS,
    EGOLINK_OUTBOX_RECOVERY_LATEST_GENERATION_SELECTED,
    EGOLINK_OUTBOX_RECOVERY_GENERATION_GAP,
    EGOLINK_OUTBOX_RECOVERY_SINGLE_VALID_SLOT,
    EGOLINK_OUTBOX_RECOVERY_FAILED,
} egolink_outbox_recovery_state_t;

typedef enum {
    EGOLINK_OUTBOX_FAILURE_NONE = 0,
    EGOLINK_OUTBOX_FAILURE_CRITICAL_RESERVE_PROTECTED,
    EGOLINK_OUTBOX_FAILURE_CRITICAL_PAYLOAD_RESERVE_PROTECTED,
    EGOLINK_OUTBOX_FAILURE_RECORD_CAPACITY_EXHAUSTED,
    EGOLINK_OUTBOX_FAILURE_CRITICAL_CAPACITY_EXHAUSTED,
    EGOLINK_OUTBOX_FAILURE_PAYLOAD_EXCEEDS_RECORD_LIMIT,
    EGOLINK_OUTBOX_FAILURE_TOTAL_PAYLOAD_CAPACITY_EXHAUSTED,
    EGOLINK_OUTBOX_FAILURE_NEGATIVE_ACK,
    EGOLINK_OUTBOX_FAILURE_ACK_IDENTITY_MISMATCH,
    EGOLINK_OUTBOX_FAILURE_ACK_STALE_OR_UNKNOWN,
    EGOLINK_OUTBOX_FAILURE_TRANSPORT,
} egolink_outbox_failure_reason_t;

typedef enum {
    EGOLINK_OUTBOX_OK = 0,
    EGOLINK_OUTBOX_NO_DUE_RECORD,
    EGOLINK_OUTBOX_DUPLICATE,
    EGOLINK_OUTBOX_DELETED_AFTER_POSITIVE_ACK,
    EGOLINK_OUTBOX_DUPLICATE_POSITIVE_ACK,
    EGOLINK_OUTBOX_NEGATIVE_ACK,
    EGOLINK_OUTBOX_STALE_OR_UNKNOWN_ACK,
    EGOLINK_OUTBOX_ACK_IDENTITY_MISMATCH,
    EGOLINK_OUTBOX_INVALID_ARGUMENT,
    EGOLINK_OUTBOX_INVALID_CONFIG,
    EGOLINK_OUTBOX_NOT_INITIALIZED,
    EGOLINK_OUTBOX_FAULT_LATCHED,
    EGOLINK_OUTBOX_INVALID_IDENTITY,
    EGOLINK_OUTBOX_INVALID_PAYLOAD,
    EGOLINK_OUTBOX_MEDIA_FORBIDDEN,
    EGOLINK_OUTBOX_IDENTITY_CONFLICT,
    EGOLINK_OUTBOX_FULL,
    EGOLINK_OUTBOX_PAYLOAD_OVERFLOW,
    EGOLINK_OUTBOX_COUNTER_OVERFLOW,
    EGOLINK_OUTBOX_TIME_ROLLBACK,
    EGOLINK_OUTBOX_TIME_OVERFLOW,
    EGOLINK_OUTBOX_GENERATION_OVERFLOW,
    EGOLINK_OUTBOX_STORAGE_ERROR,
    EGOLINK_OUTBOX_STORAGE_CORRUPTION,
    EGOLINK_OUTBOX_CONFIGURATION_MISMATCH,
    EGOLINK_OUTBOX_INVALID_ACK,
    EGOLINK_OUTBOX_STALE_ATTEMPT,
    EGOLINK_OUTBOX_ATTEMPT_CONFLICT,
    EGOLINK_OUTBOX_CRYPTO_ERROR,
} egolink_outbox_status_t;

typedef struct {
    const char *event_id;
    const char *event_type;
    egolink_outbox_priority_t priority;
    egolink_outbox_payload_kind_t payload_kind;
    const uint8_t *payload;
    size_t payload_length;
    egolink_outbox_source_time_kind_t source_time_kind;
    uint64_t source_event_time_ms;
    uint64_t boot_count;
    const char *session_id;
    uint64_t source_sequence;
} egolink_outbox_enqueue_request_t;

typedef struct {
    const char *contract_version;
    const char *ack_id;
    const char *device_id;
    const char *event_id;
    const char *payload_sha256;
    egolink_outbox_ack_status_t status;
    uint64_t ack_time_ms;
} egolink_outbox_ack_t;

typedef struct {
    char event_id[EGOLINK_OUTBOX_ID_CAPACITY];
    char event_type[EGOLINK_OUTBOX_EVENT_TYPE_CAPACITY];
    egolink_outbox_priority_t priority;
    egolink_outbox_source_time_kind_t source_time_kind;
    uint64_t source_event_time_ms;
    uint64_t boot_count;
    char session_id[EGOLINK_OUTBOX_ID_CAPACITY];
    uint64_t source_sequence;
    char payload_sha256[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    size_t payload_length;
    char identity_sha256[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    uint32_t attempt_count;
    uint64_t next_retry_runtime_epoch;
    uint64_t next_retry_time_ms;
    char last_attempt_token[EGOLINK_OUTBOX_SHA256_HEX_CAPACITY];
    egolink_outbox_attempt_result_t last_attempt_result;
    egolink_outbox_send_state_t send_state;
} egolink_outbox_record_view_t;

typedef struct {
    egolink_outbox_record_view_t record;
    uint8_t payload[EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES];
    size_t payload_length;
} egolink_outbox_send_item_t;

typedef struct {
    uint64_t enqueue_count;
    uint64_t duplicate_enqueue_count;
    uint64_t rejected_enqueue_count;
    uint64_t send_attempt_count;
    uint64_t send_failure_count;
    uint64_t transport_accept_count;
    uint64_t ack_delete_count;
    uint64_t duplicate_ack_count;
    uint64_t ack_mismatch_count;
    uint64_t full_count;
    uint64_t priority_overflow_count;
    uint64_t payload_overflow_count;
    uint64_t tombstone_pruned_count;
    uint64_t storage_failure_count;
} egolink_outbox_metrics_t;

typedef struct {
    egolink_outbox_failure_reason_t reason;
    char event_id[EGOLINK_OUTBOX_ID_CAPACITY];
    egolink_outbox_priority_t priority;
    uint64_t runtime_epoch;
    uint64_t at_ms;
    char transport_error_code[EGOLINK_OUTBOX_ERROR_CODE_CAPACITY];
} egolink_outbox_failure_t;

typedef struct {
    egolink_outbox_slot_state_t slot_state[EGOLINK_OUTBOX_SLOT_COUNT];
    egolink_outbox_recovery_state_t recovery_state;
    int8_t selected_slot;
    uint64_t selected_generation;
    size_t storage_image_bytes;
} egolink_outbox_init_report_t;

typedef struct {
    bool initialized;
    bool fault_latched;
    const char *storage_backend;
    const char *durability_claim;
    uint64_t generation;
    uint8_t active_slot;
    egolink_outbox_recovery_state_t recovery_state;
    uint16_t queued_count;
    uint16_t queued_by_priority[5];
    uint16_t max_records;
    uint16_t reserved_critical_records;
    uint32_t payload_bytes;
    uint32_t max_total_payload_bytes;
    uint32_t reserved_critical_payload_bytes;
    bool oldest_age_available;
    uint64_t oldest_age_ms;
    bool next_retry_available;
    uint64_t next_retry_runtime_epoch;
    uint64_t next_retry_time_ms;
    uint16_t awaiting_positive_ack_count;
    uint16_t ack_tombstone_count;
    egolink_outbox_metrics_t metrics;
    egolink_outbox_failure_t last_failure;
    egolink_outbox_record_view_t records[EGOLINK_OUTBOX_MAX_RECORDS];
} egolink_outbox_snapshot_t;

/* Caller should allocate this opaque object statically, not on a task stack. */
typedef union {
    max_align_t alignment;
    uint8_t opaque[EGOLINK_OUTBOX_CORE_STORAGE_BYTES];
} egolink_outbox_t;

/* Returns EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES for one of the two slots. */
size_t egolink_outbox_storage_image_bytes(void);

egolink_outbox_status_t egolink_outbox_init(
    egolink_outbox_t *outbox,
    const egolink_outbox_config_t *config,
    const egolink_outbox_storage_t *storage,
    uint64_t runtime_epoch,
    uint64_t now_ms,
    egolink_outbox_init_report_t *report);

void egolink_outbox_deinit(egolink_outbox_t *outbox);

/*
 * OK or DUPLICATE is returned only after the durable slot commit completes.
 * payload_sha256 is SHA-256 of payload[0..payload_length) exactly as stored
 * and later returned for transport; the core performs no canonicalization.
 */
egolink_outbox_status_t egolink_outbox_enqueue(
    egolink_outbox_t *outbox,
    const egolink_outbox_enqueue_request_t *request,
    uint64_t now_ms,
    egolink_outbox_record_view_t *record_view);

/*
 * Attempt metadata is committed before payload bytes are returned to send.
 * send_item contains the 4096-byte payload buffer; allocate it statically or
 * from an integration-owned memory region, not on a normal task stack.
 */
egolink_outbox_status_t egolink_outbox_begin_send_attempt(
    egolink_outbox_t *outbox,
    uint64_t now_ms,
    egolink_outbox_send_item_t *send_item);

/* A transport/HTTP success only enters AWAITING_POSITIVE_ACK; it never deletes. */
egolink_outbox_status_t egolink_outbox_record_transport_result(
    egolink_outbox_t *outbox,
    const char *attempt_token,
    bool accepted_by_transport,
    const char *error_code,
    uint64_t now_ms);

/*
 * Deletion requires ACK status ACCEPTED plus an exact device_id + event_id +
 * payload_sha256 match. A 2xx/transport result is not an ACK.
 */
egolink_outbox_status_t egolink_outbox_handle_ack(
    egolink_outbox_t *outbox,
    const egolink_outbox_ack_t *ack,
    uint64_t now_ms);

/* snapshot is also a large caller-owned output; avoid task-stack allocation. */
egolink_outbox_status_t egolink_outbox_snapshot(
    egolink_outbox_t *outbox,
    uint64_t now_ms,
    egolink_outbox_snapshot_t *snapshot);

const char *egolink_outbox_status_name(egolink_outbox_status_t status);
const char *egolink_outbox_slot_state_name(egolink_outbox_slot_state_t state);
const char *egolink_outbox_recovery_state_name(
    egolink_outbox_recovery_state_t state);
const char *egolink_outbox_failure_reason_name(
    egolink_outbox_failure_reason_t reason);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_PERSISTENT_PRIORITY_OUTBOX_H */

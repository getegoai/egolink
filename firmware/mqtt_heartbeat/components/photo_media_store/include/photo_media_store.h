#ifndef EGOLINK_PHOTO_MEDIA_STORE_H
#define EGOLINK_PHOTO_MEDIA_STORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Dedicated binary-media store. It must never share the collection record
 * spool. Callers serialize operations and callbacks complete durable media
 * I/O before returning true. The caller must provide an exclusively-owned,
 * pre-authorized media partition. On init, every non-erased slot that is not a
 * fully verifiable committed image is erased and read back so partial private
 * JPEG bytes cannot survive a torn write or torn multi-sector release. */
#define PHOTO_MEDIA_STORE_SHA256_BYTES 32U
#define PHOTO_MEDIA_STORE_ID_CAPACITY 84U
#define PHOTO_MEDIA_STORE_HEADER_BYTES 192U
#define PHOTO_MEDIA_STORE_MAX_SLOTS 512U

typedef enum {
    PHOTO_MEDIA_STORE_OK = 0,
    PHOTO_MEDIA_STORE_ALREADY_COMMITTED,
    PHOTO_MEDIA_STORE_NOT_FOUND,
    PHOTO_MEDIA_STORE_FULL,
    PHOTO_MEDIA_STORE_TOO_LARGE,
    PHOTO_MEDIA_STORE_BAD_ARGUMENT,
    PHOTO_MEDIA_STORE_BUSY,
    PHOTO_MEDIA_STORE_IDENTITY_CONFLICT,
    PHOTO_MEDIA_STORE_INCOMPLETE,
    PHOTO_MEDIA_STORE_IO_ERROR,
    PHOTO_MEDIA_STORE_CORRUPT
} photo_media_store_result_t;

typedef struct {
    void *context;
    bool (*read)(void *, size_t, void *, size_t);
    bool (*write)(void *, size_t, const void *, size_t);
    bool (*erase)(void *, size_t, size_t);
    size_t capacity_bytes;
    size_t erase_bytes;
    size_t slot_bytes;
    size_t max_payload_bytes;
    uint32_t max_committed_photos;
    uint64_t max_committed_payload_bytes;
} photo_media_store_config_t;

/* Local binary identity/integrity handle, not an observation contract. It
 * deliberately has no authorization_session_id, retention_expires_at text,
 * or training permission: the photo delivery runtime binds those
 * server/operator-controlled fields and always emits training_allowed=false.
 * The device/store must never manufacture or self-authorize a session. */
typedef struct {
    uint32_t slot;
    uint32_t payload_bytes;
    uint32_t identity_tag;
    uint64_t retention_expires_at_unix_ms;
    uint64_t capture_unix_ms;
    uint64_t capture_monotonic_ns;
    uint32_t capture_boot_count;
    uint32_t capture_sequence_id;
    uint16_t width;
    uint16_t height;
    char photo_id[PHOTO_MEDIA_STORE_ID_CAPACITY];
    uint8_t sha256[PHOTO_MEDIA_STORE_SHA256_BYTES];
} photo_media_store_record_t;

typedef struct {
    uint32_t empty_slots;
    uint32_t committed_slots;
    uint32_t torn_slots;
    uint32_t corrupt_slots;
    uint32_t reconciled_owned_slots;
    uint32_t reconciled_torn_slots;
    uint32_t reconciled_corrupt_slots;
    uint32_t reconciled_unrecognized_slots;
    uint64_t committed_payload_bytes;
    uint64_t written_payload_bytes_this_boot;
    uint64_t erased_bytes_this_boot;
    uint64_t io_errors_this_boot;
    size_t capacity_bytes;
    size_t slot_bytes;
    size_t max_payload_bytes;
} photo_media_store_stats_t;

/* Public for static allocation only; fields are not a persistence contract. */
typedef struct {
    photo_media_store_config_t config;
    photo_media_store_stats_t stats;
    uint8_t slot_states[PHOTO_MEDIA_STORE_MAX_SLOTS];
    photo_media_store_record_t active;
    size_t active_written;
    uint32_t slot_count;
    bool active_valid;
    bool initialized;
} photo_media_store_t;

photo_media_store_result_t photo_media_store_init(
    photo_media_store_t *, const photo_media_store_config_t *);

/* prepare writes and verifies an uncommitted header into an erased slot. A
 * later commit is the only operation that makes the image discoverable. */
photo_media_store_result_t photo_media_store_prepare(
    photo_media_store_t *, const char *photo_id, size_t payload_bytes,
    const uint8_t sha256[PHOTO_MEDIA_STORE_SHA256_BYTES],
    photo_media_store_record_t *prepared);

/* Runtime variant. The expiry is stored in the committed header so a reboot
 * can still enforce the authorized retention deadline after metadata has
 * already been acknowledged and removed from the ordinary spool. */
photo_media_store_result_t photo_media_store_prepare_with_expiry(
    photo_media_store_t *, const char *photo_id, size_t payload_bytes,
    const uint8_t sha256[PHOTO_MEDIA_STORE_SHA256_BYTES],
    uint64_t retention_expires_at_unix_ms,
    uint64_t capture_unix_ms, uint64_t capture_monotonic_ns,
    uint32_t capture_boot_count, uint32_t capture_sequence_id,
    uint16_t width, uint16_t height,
    photo_media_store_record_t *prepared);

/* Chunks must be sequential and the caller-provided handle must still match
 * the active prepare. A write uncertainty triggers verified slot cleanup; an
 * unverifiable cleanup fails the whole media store closed. */
photo_media_store_result_t photo_media_store_write(
    photo_media_store_t *, const photo_media_store_record_t *,
    size_t payload_offset, const void *, size_t);

/* Verifies the complete payload SHA-256 from storage, then writes the commit
 * word last. It never changes photo_id across a retry or reboot. */
photo_media_store_result_t photo_media_store_commit(
    photo_media_store_t *, const photo_media_store_record_t *);

photo_media_store_result_t photo_media_store_find(
    photo_media_store_t *, const char *photo_id,
    photo_media_store_record_t *);

/* Deterministic reboot/upload enumeration seam. Search starts at start_slot
 * (inclusive) in physical slot order. Every returned record is committed and
 * its payload SHA-256 is reverified before return. Pass record.slot + 1 to
 * continue; slot_count (available in stats via capacity/slot_bytes) yields
 * NOT_FOUND. Corruption or I/O uncertainty is reported, never skipped. */
photo_media_store_result_t photo_media_store_peek_committed(
    photo_media_store_t *, uint32_t start_slot,
    photo_media_store_record_t *);

photo_media_store_result_t photo_media_store_read(
    photo_media_store_t *, const photo_media_store_record_t *,
    size_t payload_offset, void *, size_t);

/* Release is explicit and intended only after a future server ACK has been
 * verified by the caller. It erases exactly one matching committed slot. */
photo_media_store_result_t photo_media_store_release(
    photo_media_store_t *, const photo_media_store_record_t *);

void photo_media_store_get_stats(
    const photo_media_store_t *, photo_media_store_stats_t *);
const char *photo_media_store_result_name(photo_media_store_result_t);

#endif

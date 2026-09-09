#ifndef EGOLINK_PHOTO_CONTROL_RUNTIME_H
#define EGOLINK_PHOTO_CONTROL_RUNTIME_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PHOTO_CONTROL_ID_BYTES 129U
#define PHOTO_CONTROL_TIME_TEXT_BYTES 40U
#define PHOTO_CONTROL_MESSAGE_BYTES 128U
#define PHOTO_CONTROL_TIMER_BLOB_BYTES 512U
#define PHOTO_CONTROL_JOURNAL_BLOB_BYTES 384U
#define PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES 1024U

typedef enum {
    PHOTO_CONTROL_COMMAND_NONE = 0,
    PHOTO_CONTROL_COMMAND_CAPTURE_ONCE,
    PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER,
} photo_control_command_kind_t;

typedef struct {
    photo_control_command_kind_t kind;
    char cmd_id[PHOTO_CONTROL_ID_BYTES];
    uint64_t expires_at_unix_ms;
    char authorization_session_id[PHOTO_CONTROL_ID_BYTES];
    char retention_expires_at[PHOTO_CONTROL_TIME_TEXT_BYTES];
    uint64_t retention_expires_at_unix_ms;
    bool training_allowed;
    char trigger_reason[24];
    char config_version[PHOTO_CONTROL_ID_BYTES];
    bool timer_enabled;
    uint32_t interval_seconds;
    uint64_t session_expires_at_unix_ms;
    uint32_t max_photos;
} photo_control_command_t;

typedef enum {
    PHOTO_CONTROL_PARSE_OK = 0,
    PHOTO_CONTROL_PARSE_EMPTY,
    PHOTO_CONTROL_PARSE_BAD_ARGUMENT,
    PHOTO_CONTROL_PARSE_BAD_FRAME,
    PHOTO_CONTROL_PARSE_BAD_CRC,
    PHOTO_CONTROL_PARSE_UNSUPPORTED,
    PHOTO_CONTROL_PARSE_BAD_PAYLOAD,
} photo_control_parse_result_t;

/* Parses the exact Message Hub EGLK/1 flattened command representation. It
 * rejects duplicate/unknown keys and never accepts training_allowed=true. */
photo_control_parse_result_t photo_control_parse_raw_command(
    const uint8_t *frame, size_t frame_bytes, photo_control_command_t *out);

bool photo_control_command_is_live(
    const photo_control_command_t *command, bool utc_trusted,
    uint64_t now_utc_ms);

typedef struct {
    bool enabled;
    char command_id[PHOTO_CONTROL_ID_BYTES];
    char authorization_session_id[PHOTO_CONTROL_ID_BYTES];
    char config_version[PHOTO_CONTROL_ID_BYTES];
    char retention_expires_at[PHOTO_CONTROL_TIME_TEXT_BYTES];
    uint64_t session_expires_at_unix_ms;
    uint64_t retention_expires_at_unix_ms;
    uint32_t interval_seconds;
    uint32_t max_photos;
    uint32_t captured_photos;
    char state_reason[32];
    bool status_report_pending;
    bool schedule_armed;
    uint64_t next_due_monotonic_ms;
} photo_control_timer_t;

typedef enum {
    PHOTO_CONTROL_TIMER_INACTIVE = 0,
    PHOTO_CONTROL_TIMER_WAITING_FOR_TRUSTED_UTC,
    PHOTO_CONTROL_TIMER_WAITING,
    PHOTO_CONTROL_TIMER_DUE,
    PHOTO_CONTROL_TIMER_EXPIRED,
    PHOTO_CONTROL_TIMER_LIMIT_REACHED,
} photo_control_timer_decision_t;

void photo_control_timer_default(photo_control_timer_t *timer);
bool photo_control_timer_apply(
    photo_control_timer_t *timer, const photo_control_command_t *command,
    bool utc_trusted, uint64_t now_utc_ms, uint64_t now_monotonic_ms);
photo_control_timer_decision_t photo_control_timer_tick(
    photo_control_timer_t *timer, bool utc_trusted,
    uint64_t now_utc_ms, uint64_t now_monotonic_ms);
void photo_control_timer_complete_attempt(
    photo_control_timer_t *timer, bool saved,
    uint64_t completed_monotonic_ms);

/* Persistent form excludes monotonic scheduling. A decoded/rebooted enabled
 * timer always waits one new interval after trusted UTC appears; no missed
 * intervals are backfilled. */
bool photo_control_timer_encode(
    const photo_control_timer_t *timer,
    uint8_t out[PHOTO_CONTROL_TIMER_BLOB_BYTES], size_t *written);
bool photo_control_timer_decode(
    const uint8_t *blob, size_t bytes, photo_control_timer_t *timer);

typedef enum {
    PHOTO_CONTROL_JOURNAL_NONE = 0,
    PHOTO_CONTROL_JOURNAL_EXECUTING,
    PHOTO_CONTROL_JOURNAL_COMPLETE,
} photo_control_journal_phase_t;

typedef struct {
    photo_control_journal_phase_t phase;
    photo_control_command_kind_t kind;
    char cmd_id[PHOTO_CONTROL_ID_BYTES];
    char status[16];
    char message[PHOTO_CONTROL_MESSAGE_BYTES];
    char photo_id[96];
} photo_control_journal_t;

void photo_control_journal_default(photo_control_journal_t *journal);
bool photo_control_journal_encode(
    const photo_control_journal_t *journal,
    uint8_t out[PHOTO_CONTROL_JOURNAL_BLOB_BYTES], size_t *written);
bool photo_control_journal_decode(
    const uint8_t *blob, size_t bytes, photo_control_journal_t *journal);

/* A capture attempt is a separate durable transaction from command
 * delivery.  Timer captures have no command redelivery to reconstruct them,
 * and manual captures can lose power after the JPEG commit but before their
 * metadata/ACK.  STARTED is persisted before touching the camera; RESULT is
 * persisted before appending metadata.  Recovery may therefore replay the
 * exact metadata without taking another frame. */
typedef enum {
    PHOTO_CONTROL_CAPTURE_NONE = 0,
    PHOTO_CONTROL_CAPTURE_STARTED,
    PHOTO_CONTROL_CAPTURE_RESULT,
} photo_control_capture_phase_t;

typedef struct {
    photo_control_capture_phase_t phase;
    photo_control_command_kind_t kind;
    char photo_id[96];
    char trigger_reason[24];
    char command_id[PHOTO_CONTROL_ID_BYTES];
    char config_version[PHOTO_CONTROL_ID_BYTES];
    char authorization_session_id[PHOTO_CONTROL_ID_BYTES];
    char retention_expires_at[PHOTO_CONTROL_TIME_TEXT_BYTES];
    char failure_reason[96];
    uint64_t execution_expires_at_unix_ms;
    uint64_t retention_expires_at_unix_ms;
    uint64_t source_event_utc_ms;
    uint64_t source_event_monotonic_ns;
    uint32_t capture_boot_count;
    uint32_t capture_sequence_id;
    uint32_t timer_captured_count_before;
    bool attempted;
    bool frame_acquired;
    bool media_saved;
} photo_control_capture_journal_t;

void photo_control_capture_journal_default(
    photo_control_capture_journal_t *journal);
bool photo_control_capture_journal_encode(
    const photo_control_capture_journal_t *journal,
    uint8_t out[PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES], size_t *written);
bool photo_control_capture_journal_decode(
    const uint8_t *blob, size_t bytes,
    photo_control_capture_journal_t *journal);
/* A durable capture transaction is globally exclusive. The command poller
 * must not dequeue another FIFO command until recovery has settled and
 * persisted NONE. */
bool photo_control_capture_journal_allows_new_command(
    const photo_control_capture_journal_t *journal);

/* Builds an EGLK/1 ACK using only bounded caller-provided fields. */
bool photo_control_build_ack_frame(
    const char *cmd_id, const char *status, const char *message,
    const char *fw_version, const char *transport_type, uint32_t seq,
    bool duplicate_prevented, char *out, size_t capacity, size_t *written);
bool photo_control_build_timer_ack_frame(
    const char *cmd_id, const char *message, const char *fw_version,
    const char *transport_type, uint32_t seq, bool duplicate_prevented,
    const photo_control_timer_t *timer, bool trusted_utc,
    char *out, size_t capacity, size_t *written);
bool photo_control_build_timer_state_ack_frame(
    const char *cmd_id, const char *status, const char *message,
    const char *fw_version, const char *transport_type, uint32_t seq,
    bool duplicate_prevented, const photo_control_timer_t *timer,
    bool trusted_utc, char *out, size_t capacity, size_t *written);

uint32_t photo_control_crc32(const void *data, size_t bytes);
const char *photo_control_parse_result_name(photo_control_parse_result_t result);
const char *photo_control_timer_decision_name(photo_control_timer_decision_t result);

#endif

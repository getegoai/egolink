#include "photo_control_runtime.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TIMER_MAGIC UINT32_C(0x50544d52)
#define JOURNAL_MAGIC UINT32_C(0x50434a52)
#define CAPTURE_JOURNAL_MAGIC UINT32_C(0x50434150)
#define PERSIST_VERSION UINT32_C(1)
#define CAPTURE_JOURNAL_VERSION_LEGACY UINT32_C(1)
#define CAPTURE_JOURNAL_VERSION_CURRENT UINT32_C(2)
#define CAPTURE_LEGACY_CAMERA_STATE "unknown_legacy"
#define CAPTURE_LEGACY_DRIVER_PROFILE \
    "qvga-jpeg-q12-v1-shared-i2c-unknown_legacy"
#define CAPTURE_BLOCKED_CAMERA_STATE "blocked"
#define CAPTURE_BLOCKED_DRIVER_PROFILE \
    "qvga-jpeg-q12-v1-shared-i2c-blocked"
#define CAPTURE_TRIAL_CAMERA_STATE "trial_unverified"
#define CAPTURE_TRIAL_DRIVER_PROFILE \
    "qvga-jpeg-q12-v1-shared-i2c-trial_unverified"
#define CAPTURE_VERIFIED_CAMERA_STATE "verified"
#define CAPTURE_VERIFIED_DRIVER_PROFILE \
    "qvga-jpeg-q12-v1-shared-i2c-verified"
#define CAPTURE_LEGACY_BUILD_ID "unknown_legacy"
#define CAPTURE_LEGACY_ELF_SHA256 \
    "0000000000000000000000000000000000000000000000000000000000000000"

static uint32_t crc32_update(uint32_t crc, const void *data, size_t bytes)
{
    const uint8_t *p = data;
    for (size_t i = 0U; i < bytes; ++i) {
        crc ^= p[i];
        for (unsigned bit = 0U; bit < 8U; ++bit)
            crc = (crc >> 1U) ^ (UINT32_C(0xedb88320) & (0U - (crc & 1U)));
    }
    return crc;
}

uint32_t photo_control_crc32(const void *data, size_t bytes)
{ return ~crc32_update(UINT32_MAX, data, bytes); }

static bool safe_id(const char *text)
{
    if (!text) return false;
    size_t n = strlen(text);
    if (!n || n >= PHOTO_CONTROL_ID_BYTES ||
        !((text[0] >= 'A' && text[0] <= 'Z') ||
          (text[0] >= 'a' && text[0] <= 'z') ||
          (text[0] >= '0' && text[0] <= '9'))) return false;
    for (size_t i = 1U; i < n; ++i) {
        unsigned char c = (unsigned char)text[i];
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
              (c >= '0' && c <= '9') || c == '.' || c == '_' || c == ':' ||
              c == '@' || c == '-')) return false;
    }
    return true;
}

static bool safe_text(const char *text, size_t capacity)
{
    if (!text || !*text || strlen(text) >= capacity) return false;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p)
        if (*p < 0x20U || *p > 0x7eU || *p == '\n' || *p == '\r') return false;
    return true;
}

static bool lowercase_sha256(const char *text)
{
    if (!text || strlen(text) != 64U) return false;
    for (size_t i = 0U; i < 64U; ++i)
        if (!((text[i] >= '0' && text[i] <= '9') ||
              (text[i] >= 'a' && text[i] <= 'f'))) return false;
    return true;
}

static bool capture_camera_provenance_consistent(
    const photo_control_capture_journal_t *journal)
{
    if (!journal) return false;
    const char *expected_profile = NULL;
    if (!strcmp(journal->camera_shared_i2c_state,
                CAPTURE_LEGACY_CAMERA_STATE))
        expected_profile = CAPTURE_LEGACY_DRIVER_PROFILE;
    else if (!strcmp(journal->camera_shared_i2c_state,
                     CAPTURE_BLOCKED_CAMERA_STATE))
        expected_profile = CAPTURE_BLOCKED_DRIVER_PROFILE;
    else if (!strcmp(journal->camera_shared_i2c_state,
                     CAPTURE_TRIAL_CAMERA_STATE))
        expected_profile = CAPTURE_TRIAL_DRIVER_PROFILE;
    else if (!strcmp(journal->camera_shared_i2c_state,
                     CAPTURE_VERIFIED_CAMERA_STATE))
        expected_profile = CAPTURE_VERIFIED_DRIVER_PROFILE;
    return expected_profile &&
        !strcmp(journal->camera_driver_profile, expected_profile);
}

static bool leap(unsigned year)
{ return year % 4U == 0U && (year % 100U != 0U || year % 400U == 0U); }

static unsigned month_days(unsigned year, unsigned month)
{
    static const uint8_t days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    return month == 2U && leap(year) ? 29U : days[month - 1U];
}

/* Howard Hinnant's civil-date transform, shifted to Unix epoch. */
static int64_t days_from_civil(int year, unsigned month, unsigned day)
{
    year -= month <= 2U;
    const int era = (year >= 0 ? year : year - 399) / 400;
    const unsigned yoe = (unsigned)(year - era * 400);
    const unsigned adjusted_month = month > 2U ? month - 3U : month + 9U;
    const unsigned doy = (153U * adjusted_month + 2U) / 5U + day - 1U;
    const unsigned doe = yoe * 365U + yoe / 4U - yoe / 100U + doy;
    return (int64_t)era * 146097 + (int64_t)doe - 719468;
}

static bool two_digits(const char *p, unsigned *value)
{
    if (p[0] < '0' || p[0] > '9' || p[1] < '0' || p[1] > '9') return false;
    *value = (unsigned)(p[0] - '0') * 10U + (unsigned)(p[1] - '0');
    return true;
}

static bool utc_millis(const char *text, uint64_t *result)
{
    if (!text || !result) return false;
    size_t n = strlen(text);
    if (n < 20U || n >= PHOTO_CONTROL_TIME_TEXT_BYTES || text[n - 1U] != 'Z' ||
        text[4] != '-' || text[7] != '-' || text[10] != 'T' ||
        text[13] != ':' || text[16] != ':') return false;
    unsigned year = 0U, month, day, hour, minute, second;
    for (unsigned i = 0U; i < 4U; ++i) {
        if (text[i] < '0' || text[i] > '9') return false;
        year = year * 10U + (unsigned)(text[i] - '0');
    }
    if (!two_digits(text + 5, &month) || !two_digits(text + 8, &day) ||
        !two_digits(text + 11, &hour) || !two_digits(text + 14, &minute) ||
        !two_digits(text + 17, &second) || year < 1970U || year > 9999U ||
        month < 1U || month > 12U || day < 1U || day > month_days(year, month) ||
        hour > 23U || minute > 59U || second > 59U) return false;
    uint32_t millis = 0U;
    if (n == 20U) {
        if (text[19] != 'Z') return false;
    } else {
        if (text[19] != '.' || n < 22U) return false;
        size_t digits = n - 21U;
        if (!digits || digits > 6U) return false;
        uint32_t fraction = 0U;
        for (size_t i = 0U; i < digits; ++i) {
            char c = text[20U + i];
            if (c < '0' || c > '9') return false;
            fraction = fraction * 10U + (uint32_t)(c - '0');
        }
        if (digits == 1U) millis = fraction * 100U;
        else if (digits == 2U) millis = fraction * 10U;
        else if (digits == 3U) millis = fraction;
        else {
            for (size_t i = digits; i > 3U; --i) fraction /= 10U;
            millis = fraction;
        }
    }
    int64_t days = days_from_civil((int)year, month, day);
    if (days < 0) return false;
    uint64_t seconds = (uint64_t)days * UINT64_C(86400) +
        (uint64_t)hour * 3600U + (uint64_t)minute * 60U + second;
    if (seconds > (UINT64_MAX - millis) / 1000U) return false;
    *result = seconds * 1000U + millis;
    return true;
}

static bool u64_text(const char *text, uint64_t *value)
{
    if (!text || !*text || !value) return false;
    uint64_t out = 0U;
    for (const char *p = text; *p; ++p) {
        if (*p < '0' || *p > '9') return false;
        unsigned digit = (unsigned)(*p - '0');
        if (out > (UINT64_MAX - digit) / 10U) return false;
        out = out * 10U + digit;
    }
    if (!out) return false;
    *value = out;
    return true;
}

static bool u32_text(const char *text, uint32_t *value)
{
    uint64_t parsed;
    if (!u64_text(text, &parsed) || parsed > UINT32_MAX) return false;
    *value = (uint32_t)parsed;
    return true;
}

typedef struct {
    char key[40];
    char value[PHOTO_CONTROL_ID_BYTES];
} kv_t;

static const char *lookup(const kv_t *values, size_t count, const char *key)
{
    for (size_t i = 0U; i < count; ++i)
        if (strcmp(values[i].key, key) == 0) return values[i].value;
    return NULL;
}

static bool exact_keys(const kv_t *values, size_t count,
                       const char *const *expected, size_t expected_count)
{
    if (count != expected_count) return false;
    for (size_t i = 0U; i < expected_count; ++i)
        if (!lookup(values, count, expected[i])) return false;
    return true;
}

photo_control_parse_result_t photo_control_parse_raw_command(
    const uint8_t *frame, size_t frame_bytes, photo_control_command_t *out)
{
    if (!frame || !frame_bytes || !out || frame_bytes > 2048U)
        return PHOTO_CONTROL_PARSE_BAD_ARGUMENT;
    memset(out, 0, sizeof(*out));
    if (frame_bytes < 8U || memcmp(frame, "EGLK/1 ", 7U) != 0)
        return PHOTO_CONTROL_PARSE_BAD_FRAME;
    size_t split = SIZE_MAX;
    for (size_t i = 0U; i + 1U < frame_bytes; ++i)
        if (frame[i] == '\n' && frame[i + 1U] == '\n') { split = i + 2U; break; }
    if (split == SIZE_MAX || split >= frame_bytes) return PHOTO_CONTROL_PARSE_BAD_FRAME;
    for (size_t i = 0U; i < frame_bytes; ++i)
        if (frame[i] == 0U || frame[i] == '\r') return PHOTO_CONTROL_PARSE_BAD_FRAME;

    char header[512];
    if (split >= sizeof(header)) return PHOTO_CONTROL_PARSE_BAD_FRAME;
    memcpy(header, frame, split); header[split] = '\0';
    char type[24] = {0}, header_id[PHOTO_CONTROL_ID_BYTES] = {0};
    char len_text[24] = {0}, crc_text[16] = {0};
    unsigned found = 0U;
    char *first_end = strchr(header, '\n');
    if (!first_end) return PHOTO_CONTROL_PARSE_BAD_FRAME;
    *first_end = '\0';
    char *cursor = header + 7U;
    while (*cursor) {
        while (*cursor == ' ') ++cursor;
        if (!*cursor) break;
        char *end = strchr(cursor, ' ');
        if (!end) end = cursor + strlen(cursor);
        char *equal = memchr(cursor, '=', (size_t)(end - cursor));
        if (!equal || equal == cursor || equal + 1 == end) return PHOTO_CONTROL_PARSE_BAD_FRAME;
        size_t key_n = (size_t)(equal - cursor), value_n = (size_t)(end - equal - 1);
        char *target = NULL; size_t target_n = 0U; unsigned bit = 0U;
        if (key_n == 4U && memcmp(cursor, "type", 4U) == 0) { target=type;target_n=sizeof(type);bit=1U; }
        else if (key_n == 2U && memcmp(cursor, "id", 2U) == 0) { target=header_id;target_n=sizeof(header_id);bit=2U; }
        else if (key_n == 3U && memcmp(cursor, "len", 3U) == 0) { target=len_text;target_n=sizeof(len_text);bit=4U; }
        else if (key_n == 5U && memcmp(cursor, "crc32", 5U) == 0) { target=crc_text;target_n=sizeof(crc_text);bit=8U; }
        else if (key_n == 3U && memcmp(cursor, "seq", 3U) == 0) { bit=16U; }
        else return PHOTO_CONTROL_PARSE_BAD_FRAME;
        if ((found & bit) != 0U || (target && value_n >= target_n)) return PHOTO_CONTROL_PARSE_BAD_FRAME;
        found |= bit;
        if (target) { memcpy(target, equal + 1, value_n); target[value_n] = '\0'; }
        cursor = end;
    }
    if ((found & 15U) != 15U || strcmp(type, "command") != 0 || !safe_id(header_id))
        return PHOTO_CONTROL_PARSE_BAD_FRAME;
    if (strncmp(first_end + 1, "content-type=text/x-egolink-kv\n", 31U) != 0)
        return PHOTO_CONTROL_PARSE_BAD_FRAME;
    uint64_t declared64;
    if (!u64_text(len_text, &declared64) || declared64 != frame_bytes - split)
        return PHOTO_CONTROL_PARSE_BAD_FRAME;
    char *crc_end = NULL;
    unsigned long declared_crc = strtoul(crc_text, &crc_end, 16);
    if (crc_end == crc_text || *crc_end || declared_crc > UINT32_MAX)
        return PHOTO_CONTROL_PARSE_BAD_FRAME;
    if (photo_control_crc32(frame + split, frame_bytes - split) != (uint32_t)declared_crc)
        return PHOTO_CONTROL_PARSE_BAD_CRC;

    kv_t values[12]; size_t count = 0U;
    size_t at = split;
    while (at < frame_bytes) {
        size_t end = at;
        while (end < frame_bytes && frame[end] != '\n') ++end;
        if (end == at || count >= sizeof(values)/sizeof(values[0]))
            return PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
        const uint8_t *equal = memchr(frame + at, '=', end - at);
        if (!equal) return PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
        size_t key_n = (size_t)(equal - (frame + at));
        size_t value_n = end - at - key_n - 1U;
        if (!key_n || key_n >= sizeof(values[count].key) || !value_n ||
            value_n >= sizeof(values[count].value)) return PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
        memcpy(values[count].key, frame + at, key_n); values[count].key[key_n] = '\0';
        memcpy(values[count].value, equal + 1, value_n); values[count].value[value_n] = '\0';
        if (lookup(values, count, values[count].key)) return PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
        ++count; at = end + (end < frame_bytes ? 1U : 0U);
    }
    const char *cmd = lookup(values, count, "cmd");
    if (!cmd) return PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
    if (strcmp(cmd, "none") == 0)
        return count == 1U ? PHOTO_CONTROL_PARSE_EMPTY : PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
    const char *cmd_id = lookup(values, count, "cmd_id");
    const char *auth = lookup(values, count, "authorization_session_id");
    const char *retention = lookup(values, count, "retention_expires_at");
    const char *training = lookup(values, count, "training_allowed");
    const char *expiry = lookup(values, count, "expires_at_unix_ms");
    if (!cmd_id || strcmp(cmd_id, header_id) != 0 || !safe_id(cmd_id) ||
        !auth || !safe_id(auth) || !retention || !utc_millis(retention, &out->retention_expires_at_unix_ms) ||
        !training || strcmp(training, "false") != 0 || !expiry ||
        !u64_text(expiry, &out->expires_at_unix_ms)) return PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
    memcpy(out->cmd_id, cmd_id, strlen(cmd_id) + 1U);
    memcpy(out->authorization_session_id, auth, strlen(auth) + 1U);
    memcpy(out->retention_expires_at, retention, strlen(retention) + 1U);
    out->training_allowed = false;
    if (strcmp(cmd, "capture_photo_once") == 0) {
        static const char *const expected[] = {"cmd","cmd_id","authorization_session_id",
            "retention_expires_at","training_allowed","trigger_reason","expires_at_unix_ms"};
        const char *trigger = lookup(values, count, "trigger_reason");
        if (!exact_keys(values,count,expected,sizeof(expected)/sizeof(expected[0])) ||
            !trigger || strcmp(trigger,"web_manual") != 0)
            return PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
        out->kind=PHOTO_CONTROL_COMMAND_CAPTURE_ONCE;
        memcpy(out->trigger_reason,trigger,strlen(trigger)+1U);
    } else if (strcmp(cmd, "configure_photo_timer") == 0) {
        static const char *const expected[] = {"cmd","cmd_id","authorization_session_id",
            "config_version","enabled","interval_seconds","session_expires_at_unix_ms",
            "retention_expires_at","max_photos","training_allowed","expires_at_unix_ms"};
        const char *version=lookup(values,count,"config_version"),*enabled=lookup(values,count,"enabled");
        const char *interval=lookup(values,count,"interval_seconds"),*session=lookup(values,count,"session_expires_at_unix_ms");
        const char *maximum=lookup(values,count,"max_photos");
        if (!exact_keys(values,count,expected,sizeof(expected)/sizeof(expected[0])) ||
            !version || !safe_id(version) || !enabled ||
            (strcmp(enabled,"true") != 0 && strcmp(enabled,"false") != 0) ||
            !interval || !u32_text(interval,&out->interval_seconds) ||
            out->interval_seconds < 60U || out->interval_seconds > 86400U ||
            !session || !u64_text(session,&out->session_expires_at_unix_ms) ||
            !maximum || !u32_text(maximum,&out->max_photos) || !out->max_photos ||
            out->max_photos > 1000U || out->session_expires_at_unix_ms > out->retention_expires_at_unix_ms ||
            out->expires_at_unix_ms > out->session_expires_at_unix_ms)
            return PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
        out->kind=PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER;
        out->timer_enabled=strcmp(enabled,"true") == 0;
        memcpy(out->config_version,version,strlen(version)+1U);
    } else return PHOTO_CONTROL_PARSE_UNSUPPORTED;
    if (out->expires_at_unix_ms > out->retention_expires_at_unix_ms)
        return PHOTO_CONTROL_PARSE_BAD_PAYLOAD;
    return PHOTO_CONTROL_PARSE_OK;
}

bool photo_control_command_is_live(const photo_control_command_t *command,
                                   bool utc_trusted, uint64_t now_utc_ms)
{
    return command && command->kind != PHOTO_CONTROL_COMMAND_NONE && utc_trusted &&
        now_utc_ms < command->expires_at_unix_ms &&
        now_utc_ms < command->retention_expires_at_unix_ms;
}

void photo_control_timer_default(photo_control_timer_t *timer)
{ if (timer) memset(timer, 0, sizeof(*timer)); }

bool photo_control_timer_apply(photo_control_timer_t *timer,
    const photo_control_command_t *command, bool utc_trusted,
    uint64_t now_utc_ms, uint64_t now_monotonic_ms)
{
    if (!timer || !command || command->kind != PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER ||
        !photo_control_command_is_live(command,utc_trusted,now_utc_ms)) return false;
    bool version_seen = timer->config_version[0] &&
        strcmp(timer->config_version,command->config_version) == 0;
    bool same = version_seen &&
        strcmp(timer->authorization_session_id,command->authorization_session_id) == 0 &&
        strcmp(timer->retention_expires_at,command->retention_expires_at) == 0 &&
        timer->session_expires_at_unix_ms==command->session_expires_at_unix_ms &&
        timer->retention_expires_at_unix_ms==command->retention_expires_at_unix_ms &&
        timer->interval_seconds==command->interval_seconds &&
        timer->max_photos==command->max_photos &&
        timer->enabled==command->timer_enabled;
    if(version_seen&&!same)return false;
    if(command->timer_enabled&&now_utc_ms>=command->session_expires_at_unix_ms)return false;
    uint32_t captured = same ? timer->captured_photos : 0U;
    memset(timer,0,sizeof(*timer));
    timer->enabled=command->timer_enabled;
    memcpy(timer->command_id,command->cmd_id,strlen(command->cmd_id)+1U);
    memcpy(timer->authorization_session_id,command->authorization_session_id,
           strlen(command->authorization_session_id)+1U);
    memcpy(timer->config_version,command->config_version,strlen(command->config_version)+1U);
    memcpy(timer->retention_expires_at,command->retention_expires_at,
           strlen(command->retention_expires_at)+1U);
    timer->session_expires_at_unix_ms=command->session_expires_at_unix_ms;
    timer->retention_expires_at_unix_ms=command->retention_expires_at_unix_ms;
    timer->interval_seconds=command->interval_seconds;
    timer->max_photos=command->max_photos;
    timer->captured_photos=captured > timer->max_photos ? timer->max_photos : captured;
    memcpy(timer->state_reason,command->timer_enabled?"active":"disabled_by_command",
           command->timer_enabled?7U:20U);
    timer->status_report_pending=false;
    if (timer->enabled && timer->captured_photos < timer->max_photos &&
        now_utc_ms < timer->session_expires_at_unix_ms) {
        timer->schedule_armed=true;
        timer->next_due_monotonic_ms=now_monotonic_ms+(uint64_t)timer->interval_seconds*1000U;
    } else timer->enabled=false;
    return true;
}

photo_control_timer_decision_t photo_control_timer_tick(photo_control_timer_t *timer,
    bool utc_trusted,uint64_t now_utc_ms,uint64_t now_monotonic_ms)
{
    if (!timer || !timer->enabled) return PHOTO_CONTROL_TIMER_INACTIVE;
    if (!utc_trusted) { timer->schedule_armed=false;return PHOTO_CONTROL_TIMER_WAITING_FOR_TRUSTED_UTC; }
    if (now_utc_ms >= timer->session_expires_at_unix_ms ||
        now_utc_ms >= timer->retention_expires_at_unix_ms) {
        timer->enabled=false;timer->schedule_armed=false;
        memcpy(timer->state_reason,"session_expired",16U);
        timer->status_report_pending=true;
        return PHOTO_CONTROL_TIMER_EXPIRED;
    }
    if (timer->captured_photos >= timer->max_photos) {
        timer->enabled=false;timer->schedule_armed=false;
        memcpy(timer->state_reason,"max_photos_reached",19U);
        timer->status_report_pending=true;
        return PHOTO_CONTROL_TIMER_LIMIT_REACHED;
    }
    if (!timer->schedule_armed) {
        timer->schedule_armed=true;
        timer->next_due_monotonic_ms=now_monotonic_ms+(uint64_t)timer->interval_seconds*1000U;
        return PHOTO_CONTROL_TIMER_WAITING;
    }
    return now_monotonic_ms >= timer->next_due_monotonic_ms ?
        PHOTO_CONTROL_TIMER_DUE : PHOTO_CONTROL_TIMER_WAITING;
}

void photo_control_timer_complete_attempt(photo_control_timer_t *timer,bool saved,
                                          uint64_t completed_monotonic_ms)
{
    if (!timer || !timer->enabled) return;
    if (saved && timer->captured_photos < UINT32_MAX) ++timer->captured_photos;
    if (timer->captured_photos >= timer->max_photos) {
        timer->enabled=false;timer->schedule_armed=false;
        memcpy(timer->state_reason,"max_photos_reached",19U);
        timer->status_report_pending=true;return;
    }
    timer->schedule_armed=true;
    timer->next_due_monotonic_ms=completed_monotonic_ms+(uint64_t)timer->interval_seconds*1000U;
}

static void put32(uint8_t *p,uint32_t v)
{ for(unsigned i=0U;i<4U;++i)p[i]=(uint8_t)(v>>(i*8U)); }
static uint32_t get32(const uint8_t *p)
{ return (uint32_t)p[0]|((uint32_t)p[1]<<8U)|((uint32_t)p[2]<<16U)|((uint32_t)p[3]<<24U); }
static void put64(uint8_t *p,uint64_t v)
{ for(unsigned i=0U;i<8U;++i)p[i]=(uint8_t)(v>>(i*8U)); }
static uint64_t get64(const uint8_t *p)
{ uint64_t v=0U;for(unsigned i=0U;i<8U;++i)v|=(uint64_t)p[i]<<(i*8U);return v; }

static bool append_text(uint8_t *out,size_t capacity,size_t *at,const char *text)
{
    size_t n=strlen(text);
    if(n>UINT8_MAX||*at+1U+n>capacity)return false;
    out[(*at)++]=(uint8_t)n;memcpy(out+*at,text,n);*at+=n;return true;
}
static bool read_text(const uint8_t *blob,size_t bytes,size_t *at,char *out,size_t capacity)
{
    if(*at>=bytes)return false;
    size_t n=blob[(*at)++];
    if(!n||n>=capacity||*at+n>bytes)return false;
    memcpy(out,blob+*at,n);out[n]='\0';*at+=n;return true;
}

bool photo_control_timer_encode(const photo_control_timer_t *timer,
    uint8_t out[PHOTO_CONTROL_TIMER_BLOB_BYTES],size_t *written)
{
    if(!timer||!out||!written)return false;
    memset(out,0xff,PHOTO_CONTROL_TIMER_BLOB_BYTES);
    put32(out,TIMER_MAGIC);put32(out+4U,PERSIST_VERSION);
    put32(out+8U,(timer->enabled?1U:0U)|(timer->status_report_pending?2U:0U));
    put32(out+12U,timer->interval_seconds);put32(out+16U,timer->max_photos);
    put32(out+20U,timer->captured_photos);put64(out+24U,timer->session_expires_at_unix_ms);
    put64(out+32U,timer->retention_expires_at_unix_ms);
    size_t at=44U;
    if(!append_text(out,PHOTO_CONTROL_TIMER_BLOB_BYTES,&at,timer->command_id)||
       !append_text(out,PHOTO_CONTROL_TIMER_BLOB_BYTES,&at,timer->authorization_session_id)||
       !append_text(out,PHOTO_CONTROL_TIMER_BLOB_BYTES,&at,timer->config_version)||
       !append_text(out,PHOTO_CONTROL_TIMER_BLOB_BYTES,&at,timer->retention_expires_at)||
       !append_text(out,PHOTO_CONTROL_TIMER_BLOB_BYTES,&at,timer->state_reason))return false;
    put32(out+40U,photo_control_crc32(out+44U,at-44U));*written=at;return true;
}

bool photo_control_timer_decode(const uint8_t *blob,size_t bytes,photo_control_timer_t *timer)
{
    if(!blob||!timer||bytes<47U||bytes>PHOTO_CONTROL_TIMER_BLOB_BYTES||
       get32(blob)!=TIMER_MAGIC||get32(blob+4U)!=PERSIST_VERSION||
       get32(blob+40U)!=photo_control_crc32(blob+44U,bytes-44U))return false;
    photo_control_timer_t value={0};uint32_t flags=get32(blob+8U);
    if(flags>3U)return false;
    value.enabled=(flags&1U)!=0U;value.status_report_pending=(flags&2U)!=0U;
    value.interval_seconds=get32(blob+12U);
    value.max_photos=get32(blob+16U);value.captured_photos=get32(blob+20U);
    value.session_expires_at_unix_ms=get64(blob+24U);value.retention_expires_at_unix_ms=get64(blob+32U);
    size_t at=44U;
    if(!read_text(blob,bytes,&at,value.command_id,sizeof(value.command_id))||
       !read_text(blob,bytes,&at,value.authorization_session_id,sizeof(value.authorization_session_id))||
       !read_text(blob,bytes,&at,value.config_version,sizeof(value.config_version))||
       !read_text(blob,bytes,&at,value.retention_expires_at,sizeof(value.retention_expires_at))||
       !read_text(blob,bytes,&at,value.state_reason,sizeof(value.state_reason))||at!=bytes||
       !safe_id(value.command_id)||!safe_id(value.authorization_session_id)||!safe_id(value.config_version)||
       !utc_millis(value.retention_expires_at,&value.retention_expires_at_unix_ms)||
       value.interval_seconds<60U||value.interval_seconds>86400U||!value.max_photos||
       value.max_photos>1000U||value.captured_photos>value.max_photos||
       value.session_expires_at_unix_ms>value.retention_expires_at_unix_ms||
       !safe_text(value.state_reason,sizeof(value.state_reason)))return false;
    value.schedule_armed=false;value.next_due_monotonic_ms=0U;*timer=value;return true;
}

void photo_control_journal_default(photo_control_journal_t *journal)
{ if(journal)memset(journal,0,sizeof(*journal)); }

bool photo_control_journal_encode(const photo_control_journal_t *journal,
    uint8_t out[PHOTO_CONTROL_JOURNAL_BLOB_BYTES],size_t *written)
{
    if(!journal||!out||!written||journal->phase>PHOTO_CONTROL_JOURNAL_COMPLETE||
       journal->kind>PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER)return false;
    memset(out,0xff,PHOTO_CONTROL_JOURNAL_BLOB_BYTES);put32(out,JOURNAL_MAGIC);
    put32(out+4U,PERSIST_VERSION);put32(out+8U,(uint32_t)journal->phase);
    put32(out+12U,(uint32_t)journal->kind);size_t at=20U;
    if(journal->phase!=PHOTO_CONTROL_JOURNAL_NONE&&
       (!safe_id(journal->cmd_id)||!append_text(out,sizeof(uint8_t)*PHOTO_CONTROL_JOURNAL_BLOB_BYTES,&at,journal->cmd_id) ||
        !append_text(out,PHOTO_CONTROL_JOURNAL_BLOB_BYTES,&at,journal->status[0]?journal->status:"pending")||
        !append_text(out,PHOTO_CONTROL_JOURNAL_BLOB_BYTES,&at,journal->message[0]?journal->message:"pending")||
        !append_text(out,PHOTO_CONTROL_JOURNAL_BLOB_BYTES,&at,journal->photo_id[0]?journal->photo_id:"none")))return false;
    if(journal->phase==PHOTO_CONTROL_JOURNAL_NONE)out[at++]=0U;
    put32(out+16U,photo_control_crc32(out+20U,at-20U));*written=at;return true;
}

bool photo_control_journal_decode(const uint8_t *blob,size_t bytes,photo_control_journal_t *journal)
{
    if(!blob||!journal||bytes<21U||bytes>PHOTO_CONTROL_JOURNAL_BLOB_BYTES||
       get32(blob)!=JOURNAL_MAGIC||get32(blob+4U)!=PERSIST_VERSION||
       get32(blob+16U)!=photo_control_crc32(blob+20U,bytes-20U))return false;
    photo_control_journal_t value={0};value.phase=(photo_control_journal_phase_t)get32(blob+8U);
    value.kind=(photo_control_command_kind_t)get32(blob+12U);
    if(value.phase>PHOTO_CONTROL_JOURNAL_COMPLETE||value.kind>PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER)return false;
    size_t at=20U;
    if(value.phase==PHOTO_CONTROL_JOURNAL_NONE){if(bytes!=21U||blob[20U]!=0U)return false;*journal=value;return true;}
    if(!read_text(blob,bytes,&at,value.cmd_id,sizeof(value.cmd_id))||
       !read_text(blob,bytes,&at,value.status,sizeof(value.status))||
       !read_text(blob,bytes,&at,value.message,sizeof(value.message))||
       !read_text(blob,bytes,&at,value.photo_id,sizeof(value.photo_id))||at!=bytes||
       !safe_id(value.cmd_id)||!safe_text(value.status,sizeof(value.status))||
       !safe_text(value.message,sizeof(value.message))||!safe_text(value.photo_id,sizeof(value.photo_id)))return false;
    *journal=value;return true;
}

void photo_control_capture_journal_default(photo_control_capture_journal_t *journal)
{ if(journal)memset(journal,0,sizeof(*journal)); }

static uint32_t capture_journal_crc(const uint8_t *blob,size_t bytes)
{
    uint32_t crc=crc32_update(UINT32_MAX,blob,28U);
    if(bytes>32U)crc=crc32_update(crc,blob+32U,bytes-32U);
    return ~crc;
}

bool photo_control_capture_journal_encode(
    const photo_control_capture_journal_t *journal,
    uint8_t out[PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES],size_t *written)
{
    if(!journal||!out||!written||journal->phase>PHOTO_CONTROL_CAPTURE_RESULT||
       journal->kind>PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER)return false;
    if(journal->phase!=PHOTO_CONTROL_CAPTURE_NONE&&
       (!safe_text(journal->camera_shared_i2c_state,
            sizeof(journal->camera_shared_i2c_state))||
        !safe_text(journal->camera_driver_profile,
            sizeof(journal->camera_driver_profile))||
        !safe_text(journal->runtime_config_id,
            sizeof(journal->runtime_config_id))||
        !safe_text(journal->capture_fw_version,
            sizeof(journal->capture_fw_version))||
        !lowercase_sha256(journal->capture_firmware_elf_sha256)||
        !capture_camera_provenance_consistent(journal)))return false;
    memset(out,0xff,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES);
    put32(out,CAPTURE_JOURNAL_MAGIC);
    put32(out+4U,CAPTURE_JOURNAL_VERSION_CURRENT);
    put32(out+8U,(uint32_t)journal->phase);put32(out+12U,(uint32_t)journal->kind);
    put32(out+16U,(journal->attempted?1U:0U)|(journal->frame_acquired?2U:0U)|
        (journal->media_saved?4U:0U));
    put32(out+20U,journal->capture_boot_count);
    put32(out+24U,journal->capture_sequence_id);
    put64(out+32U,journal->execution_expires_at_unix_ms);
    put64(out+40U,journal->retention_expires_at_unix_ms);
    put64(out+48U,journal->source_event_utc_ms);
    put64(out+56U,journal->source_event_monotonic_ns);
    put32(out+64U,journal->timer_captured_count_before);
    size_t at=68U;
    if(journal->phase==PHOTO_CONTROL_CAPTURE_NONE){out[at++]=0U;}
    else if(!append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,journal->photo_id)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,journal->trigger_reason)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,journal->command_id)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,journal->config_version)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,journal->authorization_session_id)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,journal->retention_expires_at)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,journal->failure_reason)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,
           journal->camera_shared_i2c_state)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,
           journal->camera_driver_profile)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,
           journal->runtime_config_id)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,
           journal->capture_fw_version)||
       !append_text(out,PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES,&at,
           journal->capture_firmware_elf_sha256))return false;
    put32(out+28U,capture_journal_crc(out,at));*written=at;return true;
}

bool photo_control_capture_journal_decode(const uint8_t *blob,size_t bytes,
    photo_control_capture_journal_t *journal)
{
    if(!blob||!journal||bytes<69U||bytes>PHOTO_CONTROL_CAPTURE_JOURNAL_BLOB_BYTES||
       get32(blob)!=CAPTURE_JOURNAL_MAGIC||
       (get32(blob+4U)!=CAPTURE_JOURNAL_VERSION_LEGACY&&
        get32(blob+4U)!=CAPTURE_JOURNAL_VERSION_CURRENT)||
       get32(blob+28U)!=capture_journal_crc(blob,bytes))return false;
    const uint32_t version=get32(blob+4U);
    photo_control_capture_journal_t value={0};
    value.phase=(photo_control_capture_phase_t)get32(blob+8U);
    value.kind=(photo_control_command_kind_t)get32(blob+12U);
    uint32_t flags=get32(blob+16U);
    if(value.phase>PHOTO_CONTROL_CAPTURE_RESULT||
       value.kind>PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER||flags>7U)return false;
    value.attempted=(flags&1U)!=0U;value.frame_acquired=(flags&2U)!=0U;
    value.media_saved=(flags&4U)!=0U;
    value.capture_boot_count=get32(blob+20U);
    value.capture_sequence_id=get32(blob+24U);
    value.execution_expires_at_unix_ms=get64(blob+32U);
    value.retention_expires_at_unix_ms=get64(blob+40U);
    value.source_event_utc_ms=get64(blob+48U);
    value.source_event_monotonic_ns=get64(blob+56U);
    value.timer_captured_count_before=get32(blob+64U);
    size_t at=68U;
    if(value.phase==PHOTO_CONTROL_CAPTURE_NONE){
        if(bytes!=69U||blob[68U]!=0U||value.kind!=PHOTO_CONTROL_COMMAND_NONE||flags||
           value.capture_boot_count||value.capture_sequence_id||
           value.execution_expires_at_unix_ms||value.retention_expires_at_unix_ms||
           value.source_event_utc_ms||value.source_event_monotonic_ns||
           value.timer_captured_count_before)return false;
        *journal=value;return true;
    }
    if(!read_text(blob,bytes,&at,value.photo_id,sizeof(value.photo_id))||
       !read_text(blob,bytes,&at,value.trigger_reason,sizeof(value.trigger_reason))||
       !read_text(blob,bytes,&at,value.command_id,sizeof(value.command_id))||
       !read_text(blob,bytes,&at,value.config_version,sizeof(value.config_version))||
       !read_text(blob,bytes,&at,value.authorization_session_id,sizeof(value.authorization_session_id))||
       !read_text(blob,bytes,&at,value.retention_expires_at,sizeof(value.retention_expires_at))||
       !read_text(blob,bytes,&at,value.failure_reason,sizeof(value.failure_reason)))return false;
    if(version==CAPTURE_JOURNAL_VERSION_CURRENT){
        if(!read_text(blob,bytes,&at,value.camera_shared_i2c_state,
               sizeof(value.camera_shared_i2c_state))||
           !read_text(blob,bytes,&at,value.camera_driver_profile,
               sizeof(value.camera_driver_profile))||
           !read_text(blob,bytes,&at,value.runtime_config_id,
               sizeof(value.runtime_config_id))||
           !read_text(blob,bytes,&at,value.capture_fw_version,
               sizeof(value.capture_fw_version))||
           !read_text(blob,bytes,&at,value.capture_firmware_elf_sha256,
               sizeof(value.capture_firmware_elf_sha256)))return false;
    }else{
        snprintf(value.camera_shared_i2c_state,
            sizeof(value.camera_shared_i2c_state),"%s",
            CAPTURE_LEGACY_CAMERA_STATE);
        snprintf(value.camera_driver_profile,
            sizeof(value.camera_driver_profile),"%s",
            CAPTURE_LEGACY_DRIVER_PROFILE);
        snprintf(value.runtime_config_id,sizeof(value.runtime_config_id),"%s",
            CAPTURE_LEGACY_BUILD_ID);
        snprintf(value.capture_fw_version,sizeof(value.capture_fw_version),"%s",
            CAPTURE_LEGACY_BUILD_ID);
        snprintf(value.capture_firmware_elf_sha256,
            sizeof(value.capture_firmware_elf_sha256),"%s",
            CAPTURE_LEGACY_ELF_SHA256);
    }
    if(at!=bytes||
       !safe_id(value.photo_id)||!safe_id(value.command_id)||
       !safe_id(value.config_version)||!safe_id(value.authorization_session_id)||
       (strcmp(value.trigger_reason,"web_manual")&&strcmp(value.trigger_reason,"device_timer"))||
       !safe_text(value.failure_reason,sizeof(value.failure_reason))||
       !utc_millis(value.retention_expires_at,&value.retention_expires_at_unix_ms)||
       !value.execution_expires_at_unix_ms||
       value.execution_expires_at_unix_ms>value.retention_expires_at_unix_ms||
       !value.source_event_utc_ms||!value.source_event_monotonic_ns||
       !value.capture_boot_count||!value.capture_sequence_id||
       (value.kind==PHOTO_CONTROL_COMMAND_CAPTURE_ONCE&&
        strcmp(value.trigger_reason,"web_manual"))||
       (value.kind==PHOTO_CONTROL_COMMAND_CONFIGURE_TIMER&&
        strcmp(value.trigger_reason,"device_timer"))||
       (value.frame_acquired&&!value.attempted)||
       (value.media_saved&&!value.frame_acquired)||
       (value.phase==PHOTO_CONTROL_CAPTURE_STARTED&&flags!=0U)||
       !safe_text(value.camera_shared_i2c_state,
           sizeof(value.camera_shared_i2c_state))||
       !safe_text(value.camera_driver_profile,
           sizeof(value.camera_driver_profile))||
       !safe_text(value.runtime_config_id,sizeof(value.runtime_config_id))||
       !safe_text(value.capture_fw_version,
           sizeof(value.capture_fw_version))||
       !lowercase_sha256(value.capture_firmware_elf_sha256)||
       !capture_camera_provenance_consistent(&value))return false;
    *journal=value;return true;
}

bool photo_control_capture_journal_allows_new_command(
    const photo_control_capture_journal_t *journal)
{
    return journal&&journal->phase==PHOTO_CONTROL_CAPTURE_NONE;
}

void photo_control_capture_settle_retry_reset(
    photo_control_capture_settle_retry_t *state,
    uint32_t initial_backoff_ms)
{
    if(!state)return;
    state->next_retry_monotonic_ms=0U;
    state->backoff_ms=initial_backoff_ms;
    state->retention_deadline_bypass_used=false;
}

bool photo_control_capture_settle_retry_due(
    photo_control_capture_settle_retry_t *state,
    uint64_t now_monotonic_ms,bool retention_expired)
{
    if(!state)return false;
    if(retention_expired&&!state->retention_deadline_bypass_used){
        state->retention_deadline_bypass_used=true;
        return true;
    }
    return now_monotonic_ms>=state->next_retry_monotonic_ms;
}

static uint64_t retry_deadline_after(uint64_t now_monotonic_ms,
                                     uint32_t delay_ms)
{
    if(now_monotonic_ms>UINT64_MAX-(uint64_t)delay_ms)return UINT64_MAX;
    return now_monotonic_ms+(uint64_t)delay_ms;
}

bool photo_control_capture_settle_retry_schedule_failure(
    photo_control_capture_settle_retry_t *state,
    uint64_t now_monotonic_ms,bool retention_expired,
    uint32_t expiry_retry_ms,uint32_t maximum_backoff_ms)
{
    if(!state||!expiry_retry_ms||!maximum_backoff_ms||!state->backoff_ms)
        return false;

    uint32_t delay_ms;
    if(retention_expired){
        state->retention_deadline_bypass_used=true;
        delay_ms=expiry_retry_ms<maximum_backoff_ms
            ?expiry_retry_ms:maximum_backoff_ms;
    }else{
        delay_ms=state->backoff_ms<maximum_backoff_ms
            ?state->backoff_ms:maximum_backoff_ms;
        state->backoff_ms=state->backoff_ms>maximum_backoff_ms/2U
            ?maximum_backoff_ms:state->backoff_ms*2U;
    }
    state->next_retry_monotonic_ms=
        retry_deadline_after(now_monotonic_ms,delay_ms);
    return true;
}

bool photo_control_build_ack_frame(const char *cmd_id,const char *status,
    const char *message,const char *fw_version,const char *transport_type,uint32_t seq,
    bool duplicate_prevented,char *out,size_t capacity,size_t *written)
{
    if(!safe_id(cmd_id)||!safe_text(status,16U)||!safe_text(message,PHOTO_CONTROL_MESSAGE_BYTES)||
       !safe_text(fw_version,96U)||(strcmp(transport_type,"wifi")&&strcmp(transport_type,"lte"))||
       !out||!capacity||!written)return false;
    char payload[768];
    int n=snprintf(payload,sizeof(payload),
        "cmd_id=%s\nstatus=%s\nmessage=%s\nfw_version=%s\nseq=%" PRIu32 "\n"
        "transport_type=%s\ncommand_last_cmd_id=%s\ncommand_parse_status=raw_command_selected\n"
        "command_count=1\nduplicate_local_execution_prevented=%s\n",
        cmd_id,status,message,fw_version,seq,transport_type,cmd_id,
        duplicate_prevented?"true":"false");
    if(n<=0||(size_t)n>=sizeof(payload))return false;
    uint32_t crc=photo_control_crc32(payload,(size_t)n);
    int total=snprintf(out,capacity,
        "EGLK/1 type=ack id=%s seq=%" PRIu32 " len=%u crc32=%08" PRIX32 "\n"
        "content-type=text/x-egolink-kv\n\n%s",cmd_id,seq,(unsigned)n,crc,payload);
    if(total<=0||(size_t)total>=capacity)return false;
    *written=(size_t)total;return true;
}

bool photo_control_build_timer_state_ack_frame(const char *cmd_id,const char *status,
    const char *message,const char *fw_version,const char *transport_type,uint32_t seq,
    bool duplicate_prevented,const photo_control_timer_t *timer,bool trusted_utc,
    char *out,size_t capacity,size_t *written)
{
    if(!timer||!safe_id(timer->config_version)||!safe_text(timer->state_reason,sizeof(timer->state_reason))||
       !safe_id(cmd_id)||!safe_text(status,16U)||!safe_text(message,PHOTO_CONTROL_MESSAGE_BYTES)||!safe_text(fw_version,96U)||
       (strcmp(transport_type,"wifi")&&strcmp(transport_type,"lte"))||!out||!capacity||!written)return false;
    char payload[1024];
    int n=snprintf(payload,sizeof(payload),
        "cmd_id=%s\nstatus=%s\nmessage=%s\nfw_version=%s\nseq=%" PRIu32 "\n"
        "transport_type=%s\ncommand_last_cmd_id=%s\ncommand_parse_status=raw_command_selected\n"
        "command_count=1\nduplicate_local_execution_prevented=%s\n"
        "timer_config_version=%s\ntimer_enabled=%s\ntimer_interval_seconds=%" PRIu32 "\n"
        "timer_session_expires_at_unix_ms=%" PRIu64 "\ntimer_max_photos=%" PRIu32 "\n"
        "timer_captured_count=%" PRIu32 "\ntimer_state_reason=%s\ntimer_trusted_utc=%s\n",
        cmd_id,status,message,fw_version,seq,transport_type,cmd_id,duplicate_prevented?"true":"false",
        timer->config_version,timer->enabled?"true":"false",timer->interval_seconds,
        timer->session_expires_at_unix_ms,timer->max_photos,timer->captured_photos,
        timer->state_reason,trusted_utc?"true":"false");
    if(n<=0||(size_t)n>=sizeof(payload))return false;
    uint32_t crc=photo_control_crc32(payload,(size_t)n);
    int total=snprintf(out,capacity,
        "EGLK/1 type=ack id=%s seq=%" PRIu32 " len=%u crc32=%08" PRIX32 "\n"
        "content-type=text/x-egolink-kv\n\n%s",cmd_id,seq,(unsigned)n,crc,payload);
    if(total<=0||(size_t)total>=capacity)return false;
    *written=(size_t)total;return true;
}

bool photo_control_build_timer_ack_frame(const char *cmd_id,const char *message,
    const char *fw_version,const char *transport_type,uint32_t seq,bool duplicate_prevented,
    const photo_control_timer_t *timer,bool trusted_utc,char *out,size_t capacity,size_t *written)
{
    return photo_control_build_timer_state_ack_frame(cmd_id,"applied",message,
        fw_version,transport_type,seq,duplicate_prevented,timer,trusted_utc,
        out,capacity,written);
}

const char *photo_control_parse_result_name(photo_control_parse_result_t result)
{
    switch(result){
    case PHOTO_CONTROL_PARSE_OK:return "ok";case PHOTO_CONTROL_PARSE_EMPTY:return "empty";
    case PHOTO_CONTROL_PARSE_BAD_ARGUMENT:return "bad_argument";case PHOTO_CONTROL_PARSE_BAD_FRAME:return "bad_frame";
    case PHOTO_CONTROL_PARSE_BAD_CRC:return "bad_crc";case PHOTO_CONTROL_PARSE_UNSUPPORTED:return "unsupported";
    case PHOTO_CONTROL_PARSE_BAD_PAYLOAD:return "bad_payload";default:return "unknown";
    }
}

const char *photo_control_timer_decision_name(photo_control_timer_decision_t result)
{
    switch(result){
    case PHOTO_CONTROL_TIMER_INACTIVE:return "inactive";
    case PHOTO_CONTROL_TIMER_WAITING_FOR_TRUSTED_UTC:return "waiting_for_trusted_utc";
    case PHOTO_CONTROL_TIMER_WAITING:return "waiting";case PHOTO_CONTROL_TIMER_DUE:return "due";
    case PHOTO_CONTROL_TIMER_EXPIRED:return "expired";case PHOTO_CONTROL_TIMER_LIMIT_REACHED:return "limit_reached";
    default:return "unknown";
    }
}

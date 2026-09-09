#include "photo_delivery_runtime.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "cJSON.h"
#include "collection_record.h"

static bool safe_id(const char *value)
{
    if (!value) return false;
    const size_t length = strlen(value);
    if (!length || length > 128U ||
        !((value[0] >= 'A' && value[0] <= 'Z') ||
          (value[0] >= 'a' && value[0] <= 'z') ||
          (value[0] >= '0' && value[0] <= '9'))) return false;
    for (size_t index = 1U; index < length; ++index) {
        const char c = value[index];
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
              (c >= '0' && c <= '9') || c == '.' || c == '_' ||
              c == ':' || c == '@' || c == '-')) return false;
    }
    return true;
}

static bool bounded_text(const char *value, size_t maximum)
{ return value && *value && strlen(value) <= maximum; }

static bool lowercase_sha256(const char *value)
{
    if (!value || strlen(value) != 64U) return false;
    for (const char *cursor = value; *cursor; ++cursor)
        if (!((*cursor >= '0' && *cursor <= '9') ||
              (*cursor >= 'a' && *cursor <= 'f'))) return false;
    return true;
}

static bool unique_keys(const cJSON *item)
{
    if (!item) return false;
    if (cJSON_IsObject(item)) {
        for (const cJSON *left = item->child; left; left = left->next)
            for (const cJSON *right = left->next; right; right = right->next)
                if (strcmp(left->string, right->string) == 0) return false;
    }
    for (const cJSON *child = item->child; child; child = child->next)
        if (!unique_keys(child)) return false;
    return true;
}

static bool exact_object_keys(const cJSON *object,
                              const char *const *expected,size_t count)
{
    if(!cJSON_IsObject(object))return false;
    size_t seen=0U;
    for(const cJSON *child=object->child;child;child=child->next){
        bool known=false;
        for(size_t index=0U;index<count;++index)
            if(strcmp(child->string,expected[index])==0){known=true;break;}
        if(!known)return false;
        ++seen;
    }
    return seen==count;
}

static cJSON *parse_exact_json(const void *response, size_t bytes)
{
    if (!response || !bytes || bytes > 8192U) return NULL;
    const char *end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(response, bytes, &end, false);
    const char *limit = (const char *)response + bytes;
    while (root && end && end < limit &&
           (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')) ++end;
    if (!root || !end || end != limit || !unique_keys(root)) {
        cJSON_Delete(root);
        return NULL;
    }
    return root;
}

static bool json_string_equals(const cJSON *object, const char *key,
                               const char *expected)
{
    const cJSON *value = cJSON_GetObjectItemCaseSensitive(object, key);
    return cJSON_IsString(value) && expected &&
        strcmp(value->valuestring, expected) == 0;
}

bool photo_delivery_build_metadata_frame(
    const photo_delivery_metadata_t *m, char *frame, size_t capacity,
    size_t *written)
{
    if (!m || !frame || !capacity || !written || !safe_id(m->device_id) ||
        !safe_id(m->photo_id) || !safe_id(m->command_id) ||
        !safe_id(m->config_version) || !safe_id(m->authorization_session_id) ||
        !bounded_text(m->retention_expires_at, 39U) ||
        !bounded_text(m->camera_model, 128U) ||
        !bounded_text(m->driver_profile, 128U) ||
        !bounded_text(m->capture_event_utc, 39U) ||
        !bounded_text(m->timestamp_source, 128U) ||
        !bounded_text(m->timestamp_quality, 128U) ||
        !bounded_text(m->monotonic_clock_domain_id, 128U) ||
        !bounded_text(m->fw_version, 128U) ||
        !lowercase_sha256(m->firmware_elf_sha256) ||
        !bounded_text(m->runtime_config_id, 128U) ||
        !m->capture_boot_count || !m->capture_sequence_id ||
        !m->capture_monotonic_ns ||
        (strcmp(m->trigger_reason, "web_manual") != 0 &&
         strcmp(m->trigger_reason, "device_timer") != 0)) return false;

    const bool captured = strcmp(m->capture_result, "captured") == 0;
    const bool capture_failed = strcmp(m->capture_result, "capture_failed") == 0;
    const bool not_attempted = strcmp(m->capture_result, "not_attempted") == 0;
    const bool outcome_unknown =
        strcmp(m->capture_result, "outcome_unknown") == 0;
    const bool saved = captured && strcmp(m->local_save_status, "saved") == 0;
    const bool save_failed = captured &&
        strcmp(m->local_save_status, "save_failed") == 0;
    const bool failed_before_frame = capture_failed &&
        strcmp(m->local_save_status, "not_attempted") == 0;
    const bool skipped = not_attempted &&
        strcmp(m->local_save_status, "not_attempted") == 0;
    const bool ambiguous = outcome_unknown &&
        strcmp(m->local_save_status, "unknown") == 0;
    if (saved) {
        if (strcmp(m->device_upload_status, "pending") != 0 ||
            !m->media_type || strcmp(m->media_type, "image/jpeg") != 0 ||
            !m->width || !m->height || m->width > 8192U || m->height > 8192U ||
            m->byte_length < 4U || m->byte_length > 65536U ||
            !lowercase_sha256(m->sha256_hex) ||
            strcmp(m->storage_kind, "persistent") != 0) return false;
    } else if (!(save_failed || failed_before_frame || skipped || ambiguous) ||
               strcmp(m->device_upload_status, "not_ready") != 0 ||
               m->media_type || m->width || m->height || m->byte_length ||
               m->sha256_hex || strcmp(m->storage_kind, "none") != 0 ||
               !bounded_text(m->failure_reason, 512U)) return false;

    if ((m->location_observation_id || m->location_event_utc ||
         m->location_timestamp_quality) &&
        (!safe_id(m->location_observation_id) ||
         !bounded_text(m->location_timestamp_quality, 128U))) return false;

    char observation_id[128];
    const int id_length = snprintf(observation_id, sizeof(observation_id),
                                   "camera-%s", m->photo_id);
    if (id_length <= 0 || (size_t)id_length >= sizeof(observation_id)) return false;
    cJSON *root = cJSON_CreateObject();
    cJSON *payload = cJSON_CreateObject();
    if (!root || !payload) { cJSON_Delete(root); cJSON_Delete(payload); return false; }
    cJSON_AddStringToObject(root, "contract_version", "egolink.collection.v1");
    cJSON_AddStringToObject(root, "observation_id", observation_id);
    cJSON_AddStringToObject(root, "device_id", m->device_id);
    cJSON_AddStringToObject(root, "source", "camera");
    cJSON_AddStringToObject(root, "stream_id", "camera");
    cJSON_AddNumberToObject(root, "sequence_id", m->capture_sequence_id);
    cJSON_AddNumberToObject(root, "boot_count", m->capture_boot_count);
    cJSON_AddStringToObject(root, "monotonic_clock_domain_id",
                            m->monotonic_clock_domain_id);
    cJSON_AddNumberToObject(root, "timestamp_monotonic_ns",
                            (double)m->capture_monotonic_ns);
    cJSON_AddStringToObject(root, "timestamp_utc", m->capture_event_utc);
    cJSON_AddStringToObject(root, "timestamp_source", m->timestamp_source);
    cJSON_AddStringToObject(root, "timestamp_quality", m->timestamp_quality);
    cJSON_AddStringToObject(root, "fw_version", m->fw_version);
    cJSON_AddStringToObject(root, "firmware_elf_sha256", m->firmware_elf_sha256);
    cJSON_AddStringToObject(root, "config_id", m->runtime_config_id);
    cJSON_AddStringToObject(root, "session_id", m->authorization_session_id);
    cJSON_AddStringToObject(root, "status", saved ? "captured" :
        (save_failed ? "save_failed" :
         (failed_before_frame ? "capture_failed" :
          (ambiguous ? "outcome_unknown" : "not_attempted"))));
    if (saved) cJSON_AddNullToObject(root, "missing_reason");
    else cJSON_AddStringToObject(root, "missing_reason", m->failure_reason);

    cJSON_AddStringToObject(payload, "photo_id", m->photo_id);
    cJSON_AddStringToObject(payload, "trigger_reason", m->trigger_reason);
    cJSON_AddStringToObject(payload, "command_id", m->command_id);
    cJSON_AddStringToObject(payload, "config_version", m->config_version);
    cJSON_AddStringToObject(payload, "capture_result", m->capture_result);
    cJSON_AddStringToObject(payload, "local_save_status", m->local_save_status);
    cJSON_AddStringToObject(payload, "device_upload_status", m->device_upload_status);
    if (saved) {
        cJSON_AddStringToObject(payload, "media_type", m->media_type);
        cJSON_AddNumberToObject(payload, "width", m->width);
        cJSON_AddNumberToObject(payload, "height", m->height);
        cJSON_AddNumberToObject(payload, "byte_length", (double)m->byte_length);
        cJSON_AddStringToObject(payload, "sha256", m->sha256_hex);
    } else {
        cJSON_AddNullToObject(payload, "media_type");
        cJSON_AddNullToObject(payload, "width");
        cJSON_AddNullToObject(payload, "height");
        cJSON_AddNullToObject(payload, "byte_length");
        cJSON_AddNullToObject(payload, "sha256");
    }
    cJSON_AddStringToObject(payload, "storage_kind", m->storage_kind);
    cJSON_AddStringToObject(payload, "camera_model", m->camera_model);
    cJSON_AddStringToObject(payload, "driver_profile", m->driver_profile);
    if (m->location_observation_id) {
        cJSON *location = cJSON_AddObjectToObject(payload, "location_ref");
        cJSON_AddStringToObject(location, "observation_id", m->location_observation_id);
        if (m->location_event_utc)
            cJSON_AddStringToObject(location, "event_utc", m->location_event_utc);
        else cJSON_AddNullToObject(location, "event_utc");
        cJSON_AddStringToObject(location, "timestamp_quality",
                                m->location_timestamp_quality);
    } else cJSON_AddNullToObject(payload, "location_ref");
    cJSON_AddStringToObject(payload, "authorization_session_id",
                            m->authorization_session_id);
    cJSON_AddStringToObject(payload, "retention_expires_at",
                            m->retention_expires_at);
    cJSON_AddBoolToObject(payload, "training_allowed", false);
    cJSON_AddItemToObject(root, "payload", payload);

    const size_t bytes = collection_record_frame(root, frame, capacity);
    cJSON_Delete(root);
    if (!bytes) return false;
    *written = bytes;
    return true;
}

bool photo_delivery_command_ack_response_matches(
    const void *response, size_t response_bytes, const char *cmd_id,
    const char *expected_command_status,
    const char posted_ack_sha256[PHOTO_DELIVERY_SHA256_HEX_BYTES])
{
    static const char *const root_keys[]={"ok","raw_frame","command_ack"};
    static const char *const acceptance_keys[]={"disposition","command_status",
        "posted_ack_sha256","accepted_ack_sha256"};
    if (!safe_id(cmd_id)||!bounded_text(expected_command_status,16U)||
        !lowercase_sha256(posted_ack_sha256)) return false;
    cJSON *root = parse_exact_json(response, response_bytes);
    const cJSON *ok = cJSON_GetObjectItemCaseSensitive(root, "ok");
    const cJSON *raw = cJSON_GetObjectItemCaseSensitive(root, "raw_frame");
    const cJSON *parse = cJSON_GetObjectItemCaseSensitive(raw, "parse_result");
    const cJSON *acceptance=cJSON_GetObjectItemCaseSensitive(root,"command_ack");
    const cJSON *disposition=cJSON_GetObjectItemCaseSensitive(acceptance,"disposition");
    const bool accepted_disposition=cJSON_IsString(disposition)&&
        (!strcmp(disposition->valuestring,"newly_applied")||
         !strcmp(disposition->valuestring,"refresh_applied")||
         !strcmp(disposition->valuestring,"idempotent_already_applied"));
    const bool matched = root&&exact_object_keys(root,root_keys,
        sizeof(root_keys)/sizeof(root_keys[0]))&&cJSON_IsTrue(ok)&&cJSON_IsObject(raw) &&
        json_string_equals(raw, "frame_id", cmd_id) && cJSON_IsObject(parse) &&
        json_string_equals(parse, "status", "ok") &&
        json_string_equals(parse, "derived_message_type", "ack")&&
        exact_object_keys(acceptance,acceptance_keys,
            sizeof(acceptance_keys)/sizeof(acceptance_keys[0]))&&accepted_disposition&&
        json_string_equals(acceptance,"command_status",expected_command_status)&&
        json_string_equals(acceptance,"posted_ack_sha256",posted_ack_sha256)&&
        json_string_equals(acceptance,"accepted_ack_sha256",posted_ack_sha256);
    cJSON_Delete(root);
    return matched;
}

bool photo_delivery_content_ack_response_matches(
    const void *response, size_t response_bytes, const char *device_id,
    const char *photo_id, const char sha256_hex[PHOTO_DELIVERY_SHA256_HEX_BYTES],
    size_t payload_bytes)
{
    static const char *const root_keys[]={"ok","result","delivery_ack"};
    static const char *const ack_keys[]={"contract_version","device_id","photo_id",
        "payload_sha256","payload_bytes","status","verification_scope","stored_at"};
    if (!safe_id(device_id) || !safe_id(photo_id) ||
        !lowercase_sha256(sha256_hex) || payload_bytes < 4U ||
        payload_bytes > 65536U) return false;
    cJSON *root = parse_exact_json(response, response_bytes);
    const cJSON *ok = cJSON_GetObjectItemCaseSensitive(root, "ok");
    const cJSON *ack = cJSON_GetObjectItemCaseSensitive(root, "delivery_ack");
    const cJSON *bytes = cJSON_GetObjectItemCaseSensitive(ack, "payload_bytes");
    const cJSON *stored_at = cJSON_GetObjectItemCaseSensitive(ack, "stored_at");
    const bool matched = root&&exact_object_keys(root,root_keys,
        sizeof(root_keys)/sizeof(root_keys[0]))&&cJSON_IsTrue(ok)&&
        exact_object_keys(ack,ack_keys,sizeof(ack_keys)/sizeof(ack_keys[0]))&&
        json_string_equals(ack, "contract_version", "egolink.photo.content.ack.v0.1") &&
        json_string_equals(ack, "device_id", device_id) &&
        json_string_equals(ack, "photo_id", photo_id) &&
        json_string_equals(ack, "payload_sha256", sha256_hex) &&
        json_string_equals(ack, "status", "server_verified") &&
        json_string_equals(ack, "verification_scope",
            "sha256_length_geometry_baseline_structure_v1") &&
        cJSON_IsNumber(bytes) && bytes->valuedouble == (double)payload_bytes &&
        bytes->valuedouble >= 4.0 && bytes->valuedouble <= 65536.0 &&
        floor(bytes->valuedouble) == bytes->valuedouble &&
        cJSON_IsString(stored_at) && bounded_text(stored_at->valuestring, 64U);
    cJSON_Delete(root);
    return matched;
}

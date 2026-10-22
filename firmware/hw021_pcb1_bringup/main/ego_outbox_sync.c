/**
 * @file ego_outbox_sync.c
 * @brief Local-First Offline Telemetry Cache & Cloud Breakpoint Resumption Implementation
 */

#include "ego_outbox_sync.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <sys/stat.h>
#include <unistd.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "EGO_OUTBOX";

static ego_outbox_sync_config_t s_cfg;
static ego_outbox_sync_status_t s_status = {0};
static SemaphoreHandle_t s_mutex = NULL;
static int64_t s_last_fail_time_ms = 0;

static void get_queue_filepath(char *buf, size_t max_len)
{
    snprintf(buf, max_len, "%s/queue.jsonl", s_cfg.storage_dir);
}

static void get_state_filepath(char *buf, size_t max_len)
{
    snprintf(buf, max_len, "%s/sync_state.json", s_cfg.storage_dir);
}

static void save_sync_state(void)
{
    char state_path[160];
    get_state_filepath(state_path, sizeof(state_path));
    FILE *fp = fopen(state_path, "w");
    if (fp) {
        fprintf(fp,
            "{\"read_offset\":%ld,\"pending_count\":%" PRIu32 ",\"total_enqueued\":%" PRIu32 ",\"total_acked\":%" PRIu32 "}\n",
            s_status.read_offset, s_status.pending_count, s_status.total_enqueued, s_status.total_acked);
        fflush(fp);
        fsync(fileno(fp));
        fclose(fp);
    }
}

static void load_sync_state(void)
{
    char state_path[160];
    get_state_filepath(state_path, sizeof(state_path));
    FILE *fp = fopen(state_path, "r");
    if (fp) {
        char buf[256];
        if (fgets(buf, sizeof(buf), fp)) {
            long roff = 0;
            uint32_t pend = 0, enq = 0, ack = 0;
            if (sscanf(buf, "{\"read_offset\":%ld,\"pending_count\":%" SCNu32 ",\"total_enqueued\":%" SCNu32 ",\"total_acked\":%" SCNu32 "}",
                       &roff, &pend, &enq, &ack) >= 1) {
                s_status.read_offset = roff;
                s_status.pending_count = pend;
                s_status.total_enqueued = enq;
                s_status.total_acked = ack;
            }
        }
        fclose(fp);
    }
}

static void count_pending_records(void)
{
    char qpath[160];
    get_queue_filepath(qpath, sizeof(qpath));
    FILE *fp = fopen(qpath, "r");
    if (!fp) {
        s_status.queue_file_bytes = 0;
        s_status.pending_count = 0;
        s_status.read_offset = 0;
        return;
    }

    fseek(fp, 0, SEEK_END);
    long fsize = ftell(fp);
    s_status.queue_file_bytes = (size_t)fsize;

    if (fsize <= s_status.read_offset) {
        /* Entire file already acked; truncate to 0 */
        fclose(fp);
        fp = fopen(qpath, "w");
        if (fp) fclose(fp);
        s_status.read_offset = 0;
        s_status.pending_count = 0;
        s_status.queue_file_bytes = 0;
        save_sync_state();
        return;
    }

    /* Count lines from read_offset to EOF */
    fseek(fp, s_status.read_offset, SEEK_SET);
    char line[1024];
    uint32_t count = 0;
    while (fgets(line, sizeof(line), fp)) {
        if (strchr(line, '|')) {
            count++;
        }
    }
    fclose(fp);
    s_status.pending_count = count;
}

esp_err_t ego_outbox_sync_init(const ego_outbox_sync_config_t *cfg)
{
    if (!cfg || !cfg->storage_dir || !cfg->post_fn) return ESP_ERR_INVALID_ARG;
    if (s_mutex == NULL) {
        s_mutex = xSemaphoreCreateMutex();
    }
    xSemaphoreTake(s_mutex, portMAX_DELAY);

    memcpy(&s_cfg, cfg, sizeof(ego_outbox_sync_config_t));
    if (s_cfg.max_queue_bytes == 0) {
        s_cfg.max_queue_bytes = 10 * 1024 * 1024; /* 10MB default */
    }

    /* Ensure outbox directory exists */
    mkdir(s_cfg.storage_dir, 0777);

    /* Load state & scan queue */
    load_sync_state();
    count_pending_records();

    s_status.is_initialized = true;
    s_status.is_draining = false;
    s_status.sim_offline_mode = false;

    ESP_LOGI(TAG, "Outbox Initialized: dir=%s, pending=%" PRIu32 ", offset=%ld, enq=%" PRIu32 ", acked=%" PRIu32,
             s_cfg.storage_dir, s_status.pending_count, s_status.read_offset,
             s_status.total_enqueued, s_status.total_acked);

    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

esp_err_t ego_outbox_sync_enqueue(const char *path, const char *json_payload)
{
    if (!path || !json_payload) return ESP_ERR_INVALID_ARG;
    if (s_mutex == NULL) return ESP_ERR_INVALID_STATE;

    xSemaphoreTake(s_mutex, portMAX_DELAY);

    char qpath[160];
    get_queue_filepath(qpath, sizeof(qpath));

    FILE *fp = fopen(qpath, "a");
    if (!fp) {
        ESP_LOGE(TAG, "Failed to open outbox queue file: %s", qpath);
        xSemaphoreGive(s_mutex);
        return ESP_FAIL;
    }

    int written = fprintf(fp, "%s|%s\n", path, json_payload);
    fflush(fp);
    fsync(fileno(fp));
    fseek(fp, 0, SEEK_END);
    s_status.queue_file_bytes = (size_t)ftell(fp);
    fclose(fp);

    if (written > 0) {
        s_status.pending_count++;
        s_status.total_enqueued++;
        save_sync_state();
        ESP_LOGI(TAG, "CACHED_OFFLINE_RECORD -> %s (pending=%" PRIu32 ", queue_bytes=%u)",
                 path, s_status.pending_count, (unsigned)s_status.queue_file_bytes);
    }

    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

esp_err_t ego_outbox_sync_submit(
    const char *path,
    const char *json_payload,
    bool is_network_online,
    bool *out_sent_direct)
{
    if (out_sent_direct) *out_sent_direct = false;
    if (!path || !json_payload) return ESP_ERR_INVALID_ARG;
    if (s_mutex == NULL) return ESP_ERR_INVALID_STATE;

    /* 1. If online, not simulating offline, and outbox queue is empty: try direct send */
    if (!s_status.sim_offline_mode && is_network_online && s_status.pending_count == 0) {
        int http_status = 0;
        esp_err_t err = s_cfg.post_fn(path, json_payload, &http_status);
        if (err == ESP_OK && http_status >= 200 && http_status < 300) {
            xSemaphoreTake(s_mutex, portMAX_DELAY);
            s_status.total_acked++;
            xSemaphoreGive(s_mutex);
            if (out_sent_direct) *out_sent_direct = true;
            return ESP_OK;
        }
        ESP_LOGW(TAG, "Direct send failed (status=%d), diverting to offline outbox cache...", http_status);
    }

    /* 2. Otherwise (offline, sim-offline, send failure, or backfilling in progress): enqueue */
    return ego_outbox_sync_enqueue(path, json_payload);
}

int ego_outbox_sync_step(bool is_network_online, bool can_use_modem)
{
    if (!s_status.is_initialized) return 0;
    if (s_status.sim_offline_mode) return 0;
    if (!is_network_online || !can_use_modem) return 0;
    if (s_status.pending_count == 0) return 0;

    int64_t now_ms = esp_timer_get_time() / 1000;
    if (s_last_fail_time_ms > 0 && (now_ms - s_last_fail_time_ms) < 3000) {
        return 0; /* Exponential / 3s backoff after network failure */
    }

    xSemaphoreTake(s_mutex, portMAX_DELAY);

    char qpath[160];
    get_queue_filepath(qpath, sizeof(qpath));

    FILE *fp = fopen(qpath, "r");
    if (!fp) {
        s_status.pending_count = 0;
        s_status.read_offset = 0;
        xSemaphoreGive(s_mutex);
        return 0;
    }

    fseek(fp, s_status.read_offset, SEEK_SET);

    char line[1024];
    if (!fgets(line, sizeof(line), fp)) {
        /* Reached EOF: all pending records drained! */
        fclose(fp);
        fp = fopen(qpath, "w"); /* Truncate queue to 0 */
        if (fp) fclose(fp);

        s_status.read_offset = 0;
        s_status.pending_count = 0;
        s_status.queue_file_bytes = 0;
        s_status.is_draining = false;
        save_sync_state();

        ESP_LOGI(TAG, "=== OUTBOX_SYNC_COMPLETE: All offline records successfully synced! Queue is empty. ===");
        xSemaphoreGive(s_mutex);
        return 0;
    }

    long next_offset = ftell(fp);
    fclose(fp);

    /* Strip trailing newline */
    char *eol = strpbrk(line, "\r\n");
    if (eol) *eol = '\0';

    char *sep = strchr(line, '|');
    if (!sep) {
        /* Corrupt line, skip to next */
        s_status.read_offset = next_offset;
        if (s_status.pending_count > 0) s_status.pending_count--;
        save_sync_state();
        xSemaphoreGive(s_mutex);
        return 0;
    }

    *sep = '\0';
    const char *path = line;
    const char *payload = sep + 1;

    s_status.is_draining = true;
    xSemaphoreGive(s_mutex);

    /* Perform POST request without holding mutex */
    int http_status = 0;
    esp_err_t post_ret = s_cfg.post_fn(path, payload, &http_status);

    xSemaphoreTake(s_mutex, portMAX_DELAY);

    if (post_ret == ESP_OK && http_status >= 200 && http_status < 300) {
        s_status.read_offset = next_offset;
        s_status.total_acked++;
        if (s_status.pending_count > 0) s_status.pending_count--;
        s_last_fail_time_ms = 0;

        if (s_status.pending_count == 0) {
            /* Entire queue drained: truncate queue file to 0 and reset offset */
            char trunc_path[160];
            get_queue_filepath(trunc_path, sizeof(trunc_path));
            FILE *tfp = fopen(trunc_path, "w");
            if (tfp) fclose(tfp);
            s_status.read_offset = 0;
            s_status.queue_file_bytes = 0;
            s_status.is_draining = false;
            ESP_LOGI(TAG, "=== OUTBOX_SYNC_COMPLETE: All offline records synced! Queue empty. ===");
        }

        save_sync_state();

        ESP_LOGI(TAG, "OUTBOX_SYNC_RESUMED_OK: %s (status=%d, remaining_pending=%" PRIu32 ")",
                 path, http_status, s_status.pending_count);
        xSemaphoreGive(s_mutex);
        return 1;
    } else {
        s_status.total_failed++;
        s_last_fail_time_ms = esp_timer_get_time() / 1000;
        ESP_LOGW(TAG, "OUTBOX_SYNC_POST_FAIL: %s (status=%d). Holding offset=%ld, retrying in 3s...",
                 path, http_status, s_status.read_offset);
        xSemaphoreGive(s_mutex);
        return -1;
    }
}

esp_err_t ego_outbox_sync_get_status(ego_outbox_sync_status_t *out_status)
{
    if (!out_status) return ESP_ERR_INVALID_ARG;
    if (s_mutex) xSemaphoreTake(s_mutex, portMAX_DELAY);
    memcpy(out_status, &s_status, sizeof(ego_outbox_sync_status_t));
    if (s_mutex) xSemaphoreGive(s_mutex);
    return ESP_OK;
}

void ego_outbox_sync_set_sim_offline(bool enable)
{
    if (s_mutex) xSemaphoreTake(s_mutex, portMAX_DELAY);
    s_status.sim_offline_mode = enable;
    ESP_LOGI(TAG, "Outbox simulated offline mode: %s", enable ? "ENABLED (Cache Only)" : "DISABLED (Live Resumption)");
    if (s_mutex) xSemaphoreGive(s_mutex);
}

esp_err_t ego_outbox_sync_clear(void)
{
    if (s_mutex == NULL) return ESP_ERR_INVALID_STATE;
    xSemaphoreTake(s_mutex, portMAX_DELAY);

    char qpath[160];
    get_queue_filepath(qpath, sizeof(qpath));
    FILE *fp = fopen(qpath, "w");
    if (fp) fclose(fp);

    s_status.read_offset = 0;
    s_status.pending_count = 0;
    s_status.queue_file_bytes = 0;
    save_sync_state();

    ESP_LOGI(TAG, "Outbox queue cleared by operator.");
    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

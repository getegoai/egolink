/**
 * @file ego_blackbox.c
 * @brief EgoLink Local-First SD Card Black Box Storage Implementation
 */

#include "ego_blackbox.h"
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include <sys/stat.h>
#include <dirent.h>
#include <unistd.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "driver/gpio.h"
#include "driver/sdmmc_host.h"
#include "sdmmc_cmd.h"
#include "esp_vfs_fat.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "EGO_BLACKBOX";

static ego_blackbox_config_t s_cfg;
static ego_blackbox_status_t s_status = {0};
static sdmmc_card_t *s_card = NULL;
static FILE *s_session_fp = NULL;
static SemaphoreHandle_t s_mutex = NULL;
static uint32_t s_session_seq = 1;
static uint32_t s_records_since_flush = 0;

static void update_free_space(void)
{
    if (!s_status.is_mounted) return;
    uint64_t total_bytes = 0;
    uint64_t free_bytes = 0;
    if (esp_vfs_fat_info(s_cfg.mount_point, &total_bytes, &free_bytes) == ESP_OK) {
        s_status.total_capacity_mb = total_bytes / (1024ULL * 1024ULL);
        s_status.free_space_mb = free_bytes / (1024ULL * 1024ULL);
    }
}

static uint32_t scan_next_session_seq(const char *sessions_dir)
{
    DIR *d = opendir(sessions_dir);
    if (!d) return 1;
    struct dirent *de;
    uint32_t max_seq = 0;
    while ((de = readdir(d)) != NULL) {
        uint32_t seq = 0;
        if (sscanf(de->d_name, "sess_%04" PRIu32 ".jsonl", &seq) == 1) {
            if (seq > max_seq) max_seq = seq;
        }
    }
    closedir(d);
    return max_seq + 1;
}

static esp_err_t open_session_file(void)
{
    if (s_session_fp != NULL) {
        fflush(s_session_fp);
        fsync(fileno(s_session_fp));
        fclose(s_session_fp);
        s_session_fp = NULL;
    }

    char sessions_dir[128];
    snprintf(sessions_dir, sizeof(sessions_dir), "%s/ego_blackbox/sessions", s_cfg.mount_point);
    s_session_seq = scan_next_session_seq(sessions_dir);

    snprintf(s_status.current_session_file, sizeof(s_status.current_session_file),
             "%s/sess_%04" PRIu32 ".jsonl", sessions_dir, s_session_seq);

    s_session_fp = fopen(s_status.current_session_file, "a+");
    if (!s_session_fp) {
        ESP_LOGE(TAG, "Failed to open session file: %s", s_status.current_session_file);
        s_status.write_errors++;
        return ESP_FAIL;
    }

    /* Seek to end and get current file size */
    fseek(s_session_fp, 0, SEEK_END);
    s_status.current_file_bytes = (uint32_t)ftell(s_session_fp);

    /* Write session start header if new file */
    if (s_status.current_file_bytes == 0) {
        int64_t now_ms = 1792594000000LL + esp_timer_get_time() / 1000;
        char header[256];
        int hlen = snprintf(header, sizeof(header),
            "{\"type\":\"SESSION_HEADER\",\"session_seq\":%" PRIu32 ",\"timestamp_ms\":%" PRIi64 ","
            "\"card\":\"%s\",\"cap_mb\":%" PRIu64 ",\"free_mb\":%" PRIu64 ",\"fw\":\"hw021_pcb1_p0_v0.2\"}\n",
            s_session_seq, now_ms, s_status.card_name, s_status.total_capacity_mb, s_status.free_space_mb);
        fwrite(header, 1, hlen, s_session_fp);
        fflush(s_session_fp);
        s_status.current_file_bytes += hlen;
    }

    ESP_LOGI(TAG, "Active session file: %s (size=%" PRIu32 " B)",
             s_status.current_session_file, s_status.current_file_bytes);
    return ESP_OK;
}

esp_err_t ego_blackbox_init(const ego_blackbox_config_t *cfg)
{
    if (!cfg || !cfg->mount_point) return ESP_ERR_INVALID_ARG;
    if (s_mutex == NULL) {
        s_mutex = xSemaphoreCreateMutex();
    }
    xSemaphoreTake(s_mutex, portMAX_DELAY);

    memcpy(&s_cfg, cfg, sizeof(ego_blackbox_config_t));
    if (s_cfg.max_file_size_bytes == 0) {
        s_cfg.max_file_size_bytes = 5 * 1024 * 1024; /* 5MB default */
    }

    /* 1. Ensure 3.3V_SD power rail is energized via Q5 (CAM_PWDN = LOW) */
    gpio_config_t pwr_cfg = {
        .pin_bit_mask = (1ULL << s_cfg.pin_pwr),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&pwr_cfg);
    gpio_set_level(s_cfg.pin_pwr, 0); /* LOW turns Q5 ON */
    vTaskDelay(pdMS_TO_TICKS(100));

    /* 2. Configure pin pullups */
    gpio_set_pull_mode(s_cfg.pin_clk, GPIO_PULLUP_ONLY);
    gpio_set_pull_mode(s_cfg.pin_cmd, GPIO_PULLUP_ONLY);
    gpio_set_pull_mode(s_cfg.pin_d0, GPIO_PULLUP_ONLY);

    /* 3. Setup SDMMC host & 1-bit slot config */
    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    host.flags = SDMMC_HOST_FLAG_1BIT | SDMMC_HOST_FLAG_DEINIT_ARG;
    host.max_freq_khz = SDMMC_FREQ_DEFAULT;

    sdmmc_slot_config_t slot_cfg = SDMMC_SLOT_CONFIG_DEFAULT();
    slot_cfg.width = 1;
    slot_cfg.clk = s_cfg.pin_clk;
    slot_cfg.cmd = s_cfg.pin_cmd;
    slot_cfg.d0 = s_cfg.pin_d0;
    slot_cfg.flags |= SDMMC_SLOT_FLAG_INTERNAL_PULLUP;

    esp_vfs_fat_mount_config_t mount_cfg = {
        .format_if_mount_failed = s_cfg.format_if_mount_failed,
        .max_files = 5,
        .allocation_unit_size = 32 * 1024,
        .disk_status_check_enable = false
    };

    ESP_LOGI(TAG, "Mounting SD card at %s (1-bit SDMMC, CLK=%d, CMD=%d, D0=%d)...",
             s_cfg.mount_point, s_cfg.pin_clk, s_cfg.pin_cmd, s_cfg.pin_d0);

    esp_err_t ret = esp_vfs_fat_sdmmc_mount(s_cfg.mount_point, &host, &slot_cfg, &mount_cfg, &s_card);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to mount SD card VFS (ret=0x%x)", ret);
        s_status.is_mounted = false;
        xSemaphoreGive(s_mutex);
        return ret;
    }

    s_status.is_mounted = true;
    snprintf(s_status.card_name, sizeof(s_status.card_name), "%s", s_card->cid.name);
    s_status.total_capacity_mb = ((uint64_t)s_card->csd.capacity * s_card->csd.sector_size) / (1024ULL * 1024ULL);
    update_free_space();

    ESP_LOGI(TAG, "SD Card VFS mounted: %s, Capacity: %" PRIu64 " MB, Free: %" PRIu64 " MB",
             s_status.card_name, s_status.total_capacity_mb, s_status.free_space_mb);

    /* 4. Create directory structure */
    char dir_buf[128];
    snprintf(dir_buf, sizeof(dir_buf), "%s/ego_blackbox", s_cfg.mount_point);
    mkdir(dir_buf, 0777);
    snprintf(dir_buf, sizeof(dir_buf), "%s/ego_blackbox/sessions", s_cfg.mount_point);
    mkdir(dir_buf, 0777);
    snprintf(dir_buf, sizeof(dir_buf), "%s/ego_blackbox/alerts", s_cfg.mount_point);
    mkdir(dir_buf, 0777);

    /* 5. Open initial session file */
    open_session_file();

    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

esp_err_t ego_blackbox_log_record(const ego_blackbox_record_t *rec)
{
    if (!rec || !s_status.is_mounted) return ESP_ERR_INVALID_STATE;
    if (s_mutex == NULL) return ESP_ERR_INVALID_STATE;

    xSemaphoreTake(s_mutex, portMAX_DELAY);

    if (s_session_fp == NULL) {
        open_session_file();
        if (s_session_fp == NULL) {
            xSemaphoreGive(s_mutex);
            return ESP_FAIL;
        }
    }

    /* Check file rotation */
    if (s_status.current_file_bytes >= s_cfg.max_file_size_bytes) {
        ESP_LOGI(TAG, "Session file reached %" PRIu32 " B, rotating...", s_status.current_file_bytes);
        open_session_file();
    }

    char line[768];
    int len = snprintf(
        line, sizeof(line),
        "{\"ts\":%" PRIi64 ",\"cyc\":%" PRIu32 ",\"est\":\"%s\",\"mob\":\"%s\",\"wear\":\"%s\","
        "\"anom\":\"%s\",\"conf\":%.2f,\"rms\":%.3f,\"imu_hz\":%.1f,"
        "\"ax\":%.1f,\"ay\":%.1f,\"az\":%.1f,\"vbat\":%d,\"soc\":%.1f,"
        "\"rsrp\":%d,\"rssi\":%d,\"net\":\"%s\","
        "\"fix\":%s,\"lat\":%.6f,\"lon\":%.6f,\"spd\":%.1f,\"sats\":%u,\"hdop\":%.1f,"
        "\"call\":\"%s\",\"sos\":%s,\"digest\":\"%s\",\"crc\":\"0x%08" PRIx32 "\"}\n",
        rec->timestamp_ms,
        rec->cycle,
        rec->est_id ? rec->est_id : "none",
        rec->mobility_str ? rec->mobility_str : "unknown",
        rec->wear_str ? rec->wear_str : "unknown",
        rec->anomaly_str ? rec->anomaly_str : "normal",
        (double)rec->confidence,
        (double)rec->motion_rms,
        (double)rec->imu_rate_hz,
        (double)rec->ax_mg,
        (double)rec->ay_mg,
        (double)rec->az_mg,
        rec->vbat_mv,
        (double)rec->soc_pct,
        rec->lte_rsrp,
        rec->csq_rssi,
        rec->network_type ? rec->network_type : "4G",
        rec->gnss_fix ? "true" : "false",
        rec->gnss_lat,
        rec->gnss_lon,
        (double)rec->gnss_speed,
        rec->gnss_sats,
        (double)rec->gnss_hdop,
        rec->call_state_str ? rec->call_state_str : "IDLE",
        rec->is_sos_active ? "true" : "false",
        rec->evidence_digest ? rec->evidence_digest : "",
        rec->outbox_crc);

    if (len > 0) {
        size_t written = fwrite(line, 1, len, s_session_fp);
        if (written == (size_t)len) {
            s_status.current_file_bytes += len;
            s_status.total_records_written++;
            s_records_since_flush++;

            /* High-priority immediate flush on SOS or non-idle call */
            bool urgent = (rec->is_sos_active || (rec->call_state_str && strcmp(rec->call_state_str, "IDLE") != 0));
            if (urgent || s_records_since_flush >= 3) {
                fflush(s_session_fp);
                fsync(fileno(s_session_fp));
                s_records_since_flush = 0;
            }
        } else {
            s_status.write_errors++;
            ESP_LOGW(TAG, "fwrite short: written=%u, expected=%d", (unsigned)written, len);
        }
    }

    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

esp_err_t ego_blackbox_log_event(const char *event_type, const char *detail_json)
{
    if (!event_type || !s_status.is_mounted) return ESP_ERR_INVALID_STATE;
    if (s_mutex == NULL) return ESP_ERR_INVALID_STATE;

    xSemaphoreTake(s_mutex, portMAX_DELAY);

    char alerts_path[128];
    snprintf(alerts_path, sizeof(alerts_path), "%s/ego_blackbox/alerts/events.jsonl", s_cfg.mount_point);

    FILE *afp = fopen(alerts_path, "a+");
    if (afp) {
        int64_t now_ms = 1792594000000LL + esp_timer_get_time() / 1000;
        char ev_line[512];
        int len = snprintf(ev_line, sizeof(ev_line),
            "{\"ts\":%" PRIi64 ",\"event\":\"%s\",\"detail\":%s}\n",
            now_ms, event_type, detail_json ? detail_json : "{}");
        fwrite(ev_line, 1, len, afp);
        fflush(afp);
        fsync(fileno(afp));
        fclose(afp);
        ESP_LOGI(TAG, "BlackBox Alert Logged: [%s] -> %s", event_type, alerts_path);
    } else {
        s_status.write_errors++;
    }

    /* Also write to active session file if open */
    if (s_session_fp) {
        int64_t now_ms = 1792594000000LL + esp_timer_get_time() / 1000;
        char ev_line[512];
        int len = snprintf(ev_line, sizeof(ev_line),
            "{\"type\":\"EVENT\",\"ts\":%" PRIi64 ",\"event\":\"%s\",\"detail\":%s}\n",
            now_ms, event_type, detail_json ? detail_json : "{}");
        fwrite(ev_line, 1, len, s_session_fp);
        fflush(s_session_fp);
        fsync(fileno(s_session_fp));
        s_status.current_file_bytes += len;
    }

    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

esp_err_t ego_blackbox_sync(void)
{
    if (!s_status.is_mounted || !s_session_fp) return ESP_ERR_INVALID_STATE;
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    fflush(s_session_fp);
    fsync(fileno(s_session_fp));
    s_records_since_flush = 0;
    update_free_space();
    xSemaphoreGive(s_mutex);
    return ESP_OK;
}

esp_err_t ego_blackbox_get_status(ego_blackbox_status_t *out_status)
{
    if (!out_status) return ESP_ERR_INVALID_ARG;
    if (s_mutex) xSemaphoreTake(s_mutex, portMAX_DELAY);
    update_free_space();
    memcpy(out_status, &s_status, sizeof(ego_blackbox_status_t));
    if (s_mutex) xSemaphoreGive(s_mutex);
    return ESP_OK;
}

esp_err_t ego_blackbox_deinit(void)
{
    if (!s_status.is_mounted) return ESP_OK;
    if (s_mutex) xSemaphoreTake(s_mutex, portMAX_DELAY);

    if (s_session_fp) {
        fflush(s_session_fp);
        fsync(fileno(s_session_fp));
        fclose(s_session_fp);
        s_session_fp = NULL;
    }

    if (s_card) {
        esp_vfs_fat_sdcard_unmount(s_cfg.mount_point, s_card);
        s_card = NULL;
    }

    s_status.is_mounted = false;
    ESP_LOGI(TAG, "SD Card VFS unmounted cleanly.");
    if (s_mutex) xSemaphoreGive(s_mutex);
    return ESP_OK;
}

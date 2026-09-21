#include "ego_state_engine.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mbedtls/sha256.h"

static void copy_string(char *dest, size_t dest_size, const char *src)
{
    if (dest == NULL || dest_size == 0) {
        return;
    }
    if (src == NULL) {
        dest[0] = '\0';
        return;
    }
    size_t src_len = strlen(src);
    size_t copy_len = src_len < (dest_size - 1) ? src_len : (dest_size - 1);
    memcpy(dest, src, copy_len);
    dest[copy_len] = '\0';
}

static void bytes_to_hex(const uint8_t *bytes, size_t len, char *out_hex, size_t hex_size)
{
    if (out_hex == NULL || hex_size < (len * 2 + 1)) {
        return;
    }
    static const char hex_chars[] = "0123456789abcdef";
    for (size_t i = 0; i < len; ++i) {
        out_hex[i * 2] = hex_chars[(bytes[i] >> 4) & 0x0F];
        out_hex[i * 2 + 1] = hex_chars[bytes[i] & 0x0F];
    }
    out_hex[len * 2] = '\0';
}

esp_err_t ego_state_engine_init(
    ego_state_engine_ctx_t *ctx,
    const char *device_id,
    uint32_t boot_count,
    const char *firmware_version,
    const char *elf_sha256)
{
    if (ctx == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(ctx, 0, sizeof(*ctx));
    copy_string(ctx->device_id, sizeof(ctx->device_id), device_id != NULL ? device_id : "ego-link-001");
    ctx->boot_count = boot_count;

    copy_string(ctx->provenance.source_driver_backend, sizeof(ctx->provenance.source_driver_backend), "qmi8658_max17048_sim7670g");
    copy_string(ctx->provenance.firmware_version, sizeof(ctx->provenance.firmware_version), firmware_version != NULL ? firmware_version : "0.1.0-sensor-policy-continuous-021");
    copy_string(ctx->provenance.firmware_elf_sha256, sizeof(ctx->provenance.firmware_elf_sha256), elf_sha256 != NULL ? elf_sha256 : "unknown");

    ctx->network.network_type = EGO_NETWORK_OFFLINE;
    ctx->initialized = true;
    return ESP_OK;
}

esp_err_t ego_state_engine_feed_imu(
    ego_state_engine_ctx_t *ctx,
    float ax_mg,
    float ay_mg,
    float az_mg,
    float gx_mdps,
    float gy_mdps,
    float gz_mdps,
    int64_t timestamp_ns,
    bool is_mock)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    uint16_t index = ctx->ring_head;
    ctx->imu_ring[index].ax_m_s2 = ax_mg * 0.00980665f;
    ctx->imu_ring[index].ay_m_s2 = ay_mg * 0.00980665f;
    ctx->imu_ring[index].az_m_s2 = az_mg * 0.00980665f;

    ctx->imu_ring[index].gx_dps = gx_mdps * 0.001f;
    ctx->imu_ring[index].gy_dps = gy_mdps * 0.001f;
    ctx->imu_ring[index].gz_dps = gz_mdps * 0.001f;

    ctx->imu_ring[index].timestamp_ns = timestamp_ns;
    ctx->imu_ring[index].is_mock = is_mock;

    ctx->ring_head = (uint16_t)((ctx->ring_head + 1) % EGO_STATE_MAX_IMU_SAMPLES);
    if (ctx->ring_count < EGO_STATE_MAX_IMU_SAMPLES) {
        ctx->ring_count++;
    }
    return ESP_OK;
}

esp_err_t ego_state_engine_feed_location(
    ego_state_engine_ctx_t *ctx,
    bool fix_valid,
    float ground_speed_m_s,
    double lat_deg,
    double lon_deg,
    float hdop,
    uint16_t sats,
    float course_deg,
    int64_t timestamp_ns)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    ctx->location.fix_valid = fix_valid;
    ctx->location.ground_speed_m_s = ground_speed_m_s;
    ctx->location.latitude_deg = lat_deg;
    ctx->location.longitude_deg = lon_deg;
    ctx->location.hdop = hdop;
    ctx->location.satellites_in_use = sats;
    ctx->location.course_over_ground_deg = course_deg;
    ctx->location.last_update_ns = timestamp_ns;
    return ESP_OK;
}

esp_err_t ego_state_engine_feed_network(
    ego_state_engine_ctx_t *ctx,
    ego_network_type_t net_type,
    float lte_rsrp_dbm,
    const char *lte_cell_id,
    uint16_t wifi_ap_count,
    const char *wifi_hash)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    ctx->network.network_type = net_type;
    ctx->network.lte_rsrp_dbm = lte_rsrp_dbm;
    if (lte_cell_id != NULL) {
        copy_string(ctx->network.lte_cell_id, sizeof(ctx->network.lte_cell_id), lte_cell_id);
    }
    ctx->network.wifi_ap_count = wifi_ap_count;
    if (wifi_hash != NULL) {
        copy_string(ctx->network.wifi_fingerprint_hash, sizeof(ctx->network.wifi_fingerprint_hash), wifi_hash);
    }
    return ESP_OK;
}

esp_err_t ego_state_engine_feed_power(
    ego_state_engine_ctx_t *ctx,
    float battery_soc_percent,
    int32_t battery_voltage_mv,
    bool is_charging)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    ctx->power.battery_soc_percent = battery_soc_percent;
    ctx->power.battery_voltage_mv = battery_voltage_mv;
    ctx->power.is_charging = is_charging;
    ctx->power.valid = true;
    return ESP_OK;
}

static void compute_window_imu_features(
    const ego_state_engine_ctx_t *ctx,
    int64_t now_monotonic_ns,
    uint32_t window_duration_ms,
    ego_imu_features_t *out_features)
{
    memset(out_features, 0, sizeof(*out_features));
    if (ctx->ring_count == 0) {
        return;
    }

    int64_t cutoff_ns = now_monotonic_ns - (int64_t)window_duration_ms * 1000000LL;

    /* Collect samples in window */
    const ego_imu_raw_sample_t *samples[EGO_STATE_MAX_IMU_SAMPLES];
    uint32_t count = 0;
    bool is_mock = false;

    for (uint16_t i = 0; i < ctx->ring_count; ++i) {
        /* Ring buffer traversal: oldest to newest */
        uint16_t idx = (uint16_t)((ctx->ring_head + EGO_STATE_MAX_IMU_SAMPLES - ctx->ring_count + i) % EGO_STATE_MAX_IMU_SAMPLES);
        if (ctx->imu_ring[idx].timestamp_ns >= cutoff_ns) {
            samples[count++] = &ctx->imu_ring[idx];
            if (ctx->imu_ring[idx].is_mock) {
                is_mock = true;
            }
        }
    }

    if (count == 0) {
        /* Fallback to latest up to 20 samples */
        uint16_t take = ctx->ring_count < 20 ? ctx->ring_count : 20;
        for (uint16_t i = 0; i < take; ++i) {
            uint16_t idx = (uint16_t)((ctx->ring_head + EGO_STATE_MAX_IMU_SAMPLES - take + i) % EGO_STATE_MAX_IMU_SAMPLES);
            samples[count++] = &ctx->imu_ring[idx];
            if (ctx->imu_ring[idx].is_mock) {
                is_mock = true;
            }
        }
    }

    out_features->sample_count = count;
    out_features->is_mock = is_mock;
    if (count == 0) {
        return;
    }

    /* Compute magnitudes, mean magnitude, and peak */
    float sum_mag = 0.0f;
    float peak_mag = 0.0f;
    float sum_gx = 0.0f;
    float sum_gy = 0.0f;
    float sum_gz = 0.0f;
    float mags[EGO_STATE_MAX_IMU_SAMPLES];

    for (uint32_t i = 0; i < count; ++i) {
        float ax = samples[i]->ax_m_s2;
        float ay = samples[i]->ay_m_s2;
        float az = samples[i]->az_m_s2;
        float mag = sqrtf(ax * ax + ay * ay + az * az);
        mags[i] = mag;
        sum_mag += mag;
        if (mag > peak_mag) {
            peak_mag = mag;
        }
        sum_gx += samples[i]->gx_dps;
        sum_gy += samples[i]->gy_dps;
        sum_gz += samples[i]->gz_dps;
    }

    float mean_mag = sum_mag / (float)count;
    float mean_gx = sum_gx / (float)count;
    float mean_gy = sum_gy / (float)count;
    float mean_gz = sum_gz / (float)count;

    /* Compute motion RMS and gyro variance */
    float sum_sq_diff_mag = 0.0f;
    float sum_sq_diff_g = 0.0f;

    for (uint32_t i = 0; i < count; ++i) {
        float diff_mag = mags[i] - mean_mag;
        sum_sq_diff_mag += diff_mag * diff_mag;

        float dgx = samples[i]->gx_dps - mean_gx;
        float dgy = samples[i]->gy_dps - mean_gy;
        float dgz = samples[i]->gz_dps - mean_gz;
        sum_sq_diff_g += (dgx * dgx + dgy * dgy + dgz * dgz);
    }

    out_features->motion_rms_m_s2 = sqrtf(sum_sq_diff_mag / (float)count);
    out_features->peak_accel_m_s2 = peak_mag;
    out_features->gyro_variance_dps2 = sum_sq_diff_g / (float)count;

    /* Compute sample rate */
    out_features->sample_rate_hz = 20.0f;
    if (count >= 2) {
        int64_t dt_ns = samples[count - 1]->timestamp_ns - samples[0]->timestamp_ns;
        if (dt_ns > 10000000LL) {
            float dt_s = (float)dt_ns / 1000000000.0f;
            out_features->sample_rate_hz = (float)count / dt_s;
        }
    }
}

static void add_reason_code(ego_state_estimation_t *state, const char *code)
{
    if (state == NULL || code == NULL || state->reason_code_count >= EGO_STATE_MAX_REASON_CODES) {
        return;
    }
    copy_string(
        state->reason_codes[state->reason_code_count],
        sizeof(state->reason_codes[state->reason_code_count]),
        code
    );
    state->reason_code_count++;
}

static void compute_evidence_digest(
    const ego_evidence_chain_t *evidence,
    char *out_digest,
    size_t digest_size)
{
    /* Format deterministic canonical string */
    char raw_buf[1024];
    char speed_str[24];
    char hdop_str[24];
    char rsrp_str[24];
    char wifi_str[24];
    char soc_str[24];
    char volt_str[24];
    char chg_str[16];

    if (evidence->location_evidence.fix_valid) {
        (void)snprintf(speed_str, sizeof(speed_str), "%.2f", (double)evidence->location_evidence.ground_speed_m_s);
        (void)snprintf(hdop_str, sizeof(hdop_str), "%.2f", (double)evidence->location_evidence.hdop);
    } else {
        copy_string(speed_str, sizeof(speed_str), "null");
        copy_string(hdop_str, sizeof(hdop_str), "null");
    }

    if (evidence->network_evidence.lte_rsrp_dbm != 0.0f) {
        (void)snprintf(rsrp_str, sizeof(rsrp_str), "%.1f", (double)evidence->network_evidence.lte_rsrp_dbm);
    } else {
        copy_string(rsrp_str, sizeof(rsrp_str), "null");
    }

    if (evidence->network_evidence.wifi_ap_count > 0) {
        (void)snprintf(wifi_str, sizeof(wifi_str), "%u", (unsigned int)evidence->network_evidence.wifi_ap_count);
    } else {
        copy_string(wifi_str, sizeof(wifi_str), "null");
    }

    if (evidence->power_evidence.valid) {
        (void)snprintf(soc_str, sizeof(soc_str), "%.1f", (double)evidence->power_evidence.battery_soc_percent);
        (void)snprintf(volt_str, sizeof(volt_str), "%ld", (long)evidence->power_evidence.battery_voltage_mv);
        copy_string(chg_str, sizeof(chg_str), evidence->power_evidence.is_charging ? "true" : "false");
    } else {
        copy_string(soc_str, sizeof(soc_str), "null");
        copy_string(volt_str, sizeof(volt_str), "null");
        copy_string(chg_str, sizeof(chg_str), "null");
    }

    (void)snprintf(
        raw_buf, sizeof(raw_buf),
        "{\"boot_count\":%lu,\"device_id\":\"%s\","
        "\"imu\":{\"gyro_variance_dps2\":%.4f,\"motion_rms_m_s2\":%.4f,\"peak_accel_m_s2\":%.4f,\"sample_count\":%lu,\"sample_rate_hz\":%.1f},"
        "\"location\":{\"fix_valid\":%s,\"ground_speed_m_s\":%s,\"hdop\":%s},"
        "\"network\":{\"lte_rsrp_dbm\":%s,\"network_type\":\"%s\",\"wifi_ap_count\":%s},"
        "\"power\":{\"battery_soc_percent\":%s,\"battery_voltage_mv\":%s,\"is_charging\":%s},"
        "\"timestamp_monotonic_ns\":%lld}",
        (unsigned long)evidence->boot_count,
        evidence->device_id,
        (double)evidence->imu_evidence.gyro_variance_dps2,
        (double)evidence->imu_evidence.motion_rms_m_s2,
        (double)evidence->imu_evidence.peak_accel_m_s2,
        (unsigned long)evidence->imu_evidence.sample_count,
        (double)evidence->imu_evidence.sample_rate_hz,
        evidence->location_evidence.fix_valid ? "true" : "false",
        speed_str,
        hdop_str,
        rsrp_str,
        ego_network_type_to_str(evidence->network_evidence.network_type),
        wifi_str,
        soc_str,
        volt_str,
        chg_str,
        (long long)evidence->timestamp_monotonic_ns
    );

    uint8_t hash[32];
    mbedtls_sha256_context sha_ctx;
    mbedtls_sha256_init(&sha_ctx);
    mbedtls_sha256_starts(&sha_ctx, 0);
    mbedtls_sha256_update(&sha_ctx, (const unsigned char *)raw_buf, strlen(raw_buf));
    mbedtls_sha256_finish(&sha_ctx, hash);
    mbedtls_sha256_free(&sha_ctx);

    bytes_to_hex(hash, sizeof(hash), out_digest, digest_size);
}

esp_err_t ego_state_engine_evaluate(
    ego_state_engine_ctx_t *ctx,
    int64_t now_monotonic_ns,
    uint32_t window_duration_ms,
    ego_state_estimation_t *out_state,
    ego_evidence_chain_t *out_evidence)
{
    if (ctx == NULL || !ctx->initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    ctx->estimation_sequence++;

    ego_imu_features_t imu_feat;
    compute_window_imu_features(ctx, now_monotonic_ns, window_duration_ms, &imu_feat);

    ego_state_estimation_t state;
    memset(&state, 0, sizeof(state));
    (void)snprintf(state.estimation_id, sizeof(state.estimation_id), "est-b%lu-%lu", (unsigned long)ctx->boot_count, (unsigned long)ctx->estimation_sequence);
    copy_string(state.device_id, sizeof(state.device_id), ctx->device_id);
    state.boot_count = ctx->boot_count;
    state.timestamp_monotonic_ns = now_monotonic_ns;
    state.window_duration_ms = window_duration_ms;
    state.is_mock = imu_feat.is_mock;

    /* 1. Spatial Mobility Decision */
    bool fix = ctx->location.fix_valid;
    float speed = ctx->location.ground_speed_m_s;
    float rms = imu_feat.motion_rms_m_s2;
    float peak_accel = imu_feat.peak_accel_m_s2;
    float gyro_var = imu_feat.gyro_variance_dps2;

    char reason_tmp[EGO_STATE_REASON_CODE_MAX_LEN];

    if (fix && speed >= 4.0f) {
        state.spatial_mobility = EGO_SPATIAL_MOBILITY_IN_VEHICLE;
        (void)snprintf(reason_tmp, sizeof(reason_tmp), "gnss_speed_high_%.1fmps", (double)speed);
        add_reason_code(&state, reason_tmp);
    } else if (fix && speed >= 1.8f && rms >= 1.2f) {
        state.spatial_mobility = EGO_SPATIAL_MOBILITY_RUNNING;
        (void)snprintf(reason_tmp, sizeof(reason_tmp), "high_speed_and_motion_rms_%.2f", (double)rms);
        add_reason_code(&state, reason_tmp);
    } else if (rms >= 0.3f) {
        state.spatial_mobility = EGO_SPATIAL_MOBILITY_PEDESTRIAN_WALKING;
        (void)snprintf(reason_tmp, sizeof(reason_tmp), "motion_rms_active_%.2f", (double)rms);
        add_reason_code(&state, reason_tmp);
    } else if (!fix && (
        (ctx->network.wifi_ap_count >= 3) ||
        ((ctx->network.network_type == EGO_NETWORK_LTE || ctx->network.network_type == EGO_NETWORK_MULTI) &&
         ctx->network.lte_rsrp_dbm != 0.0f && ctx->network.lte_rsrp_dbm > -115.0f)
    )) {
        state.spatial_mobility = EGO_SPATIAL_MOBILITY_INDOOR_WEAK_GNSS;
        add_reason_code(&state, "indoor_no_gnss_fix_with_rf_anchors");
    } else {
        state.spatial_mobility = EGO_SPATIAL_MOBILITY_STATIONARY;
        (void)snprintf(reason_tmp, sizeof(reason_tmp), "motion_rms_quiet_%.2f", (double)rms);
        add_reason_code(&state, reason_tmp);
    }

    /* 2. Posture Anomaly Decision */
    if (peak_accel >= 25.0f) {
        ctx->last_shock_time_ns = now_monotonic_ns;
        state.posture_anomaly = EGO_POSTURE_ANOMALY_ABNORMAL_SHOCK;
        (void)snprintf(reason_tmp, sizeof(reason_tmp), "impact_shock_%.1fmps2", (double)peak_accel);
        add_reason_code(&state, reason_tmp);
    } else if (ctx->last_shock_time_ns > 0 &&
               (now_monotonic_ns - ctx->last_shock_time_ns) < 10000000000LL &&
               rms < 0.15f) {
        state.posture_anomaly = EGO_POSTURE_ANOMALY_SUSPECTED_FALL;
        add_reason_code(&state, "shock_followed_by_stillness");
    } else if (rms < 0.05f) {
        if (ctx->immobility_start_ns == 0) {
            ctx->immobility_start_ns = now_monotonic_ns;
            state.posture_anomaly = EGO_POSTURE_ANOMALY_NORMAL;
        } else if ((now_monotonic_ns - ctx->immobility_start_ns) > 300000000000LL) {
            state.posture_anomaly = EGO_POSTURE_ANOMALY_PROLONGED_IMMOBILITY;
            add_reason_code(&state, "prolonged_stillness_over_300s");
        } else {
            state.posture_anomaly = EGO_POSTURE_ANOMALY_NORMAL;
        }
    } else {
        ctx->immobility_start_ns = 0;
        state.posture_anomaly = EGO_POSTURE_ANOMALY_NORMAL;
    }

    /* 3. Device Wear State Decision */
    if (ctx->power.valid && ctx->power.is_charging) {
        state.device_wear_state = EGO_DEVICE_WEAR_CHARGING_DOCKED;
        add_reason_code(&state, "charging_cable_or_dock_attached");
    } else if (rms < 0.05f && gyro_var < 0.02f) {
        state.device_wear_state = EGO_DEVICE_WEAR_TABLETOP_RESTING;
        add_reason_code(&state, "pure_rest_tabletop");
    } else if (state.spatial_mobility == EGO_SPATIAL_MOBILITY_STATIONARY && gyro_var > 0.05f && rms < 0.3f) {
        state.device_wear_state = EGO_DEVICE_WEAR_HANDHELD;
        add_reason_code(&state, "subtle_hand_movement");
    } else {
        state.device_wear_state = EGO_DEVICE_WEAR_WEARABLE_OR_BAG;
        add_reason_code(&state, "dynamic_body_attachment");
    }

    /* 4. Confidence Score */
    float confidence = 0.80f;
    if (imu_feat.sample_count >= 20) {
        confidence += 0.10f;
    }
    if (fix) {
        confidence += 0.05f;
    }
    if (ctx->power.valid) {
        confidence += 0.03f;
    }
    if (confidence > 0.99f) {
        confidence = 0.99f;
    }
    state.confidence = confidence;

    /* 5. Assemble Evidence Chain */
    ego_evidence_chain_t evidence;
    memset(&evidence, 0, sizeof(evidence));
    (void)snprintf(evidence.evidence_id, sizeof(evidence.evidence_id), "evid-b%lu-%lu", (unsigned long)ctx->boot_count, (unsigned long)ctx->estimation_sequence);
    copy_string(evidence.device_id, sizeof(evidence.device_id), ctx->device_id);
    evidence.boot_count = ctx->boot_count;
    evidence.timestamp_monotonic_ns = now_monotonic_ns;
    evidence.window_duration_ms = window_duration_ms;
    evidence.imu_evidence = imu_feat;
    evidence.location_evidence = ctx->location;
    evidence.network_evidence = ctx->network;
    evidence.power_evidence = ctx->power;
    evidence.provenance = ctx->provenance;

    compute_evidence_digest(&evidence, evidence.evidence_digest, sizeof(evidence.evidence_digest));
    copy_string(state.primary_evidence_digest, sizeof(state.primary_evidence_digest), evidence.evidence_digest);

    if (out_state != NULL) {
        *out_state = state;
    }
    if (out_evidence != NULL) {
        *out_evidence = evidence;
    }
    return ESP_OK;
}

const char *ego_spatial_mobility_to_str(ego_spatial_mobility_t mobility)
{
    switch (mobility) {
        case EGO_SPATIAL_MOBILITY_STATIONARY:
            return "stationary";
        case EGO_SPATIAL_MOBILITY_PEDESTRIAN_WALKING:
            return "pedestrian_walking";
        case EGO_SPATIAL_MOBILITY_RUNNING:
            return "running";
        case EGO_SPATIAL_MOBILITY_IN_VEHICLE:
            return "in_vehicle";
        case EGO_SPATIAL_MOBILITY_INDOOR_WEAK_GNSS:
            return "indoor_weak_gnss";
        default:
            return "unknown";
    }
}

const char *ego_posture_anomaly_to_str(ego_posture_anomaly_t anomaly)
{
    switch (anomaly) {
        case EGO_POSTURE_ANOMALY_NORMAL:
            return "normal";
        case EGO_POSTURE_ANOMALY_ABNORMAL_SHOCK:
            return "abnormal_shock";
        case EGO_POSTURE_ANOMALY_SUSPECTED_FALL:
            return "suspected_fall";
        case EGO_POSTURE_ANOMALY_PROLONGED_IMMOBILITY:
            return "prolonged_immobility";
        default:
            return "unknown";
    }
}

const char *ego_device_wear_to_str(ego_device_wear_state_t wear)
{
    switch (wear) {
        case EGO_DEVICE_WEAR_TABLETOP_RESTING:
            return "tabletop_resting";
        case EGO_DEVICE_WEAR_HANDHELD:
            return "handheld";
        case EGO_DEVICE_WEAR_WEARABLE_OR_BAG:
            return "wearable_or_bag";
        case EGO_DEVICE_WEAR_CHARGING_DOCKED:
            return "charging_docked";
        default:
            return "unknown";
    }
}

const char *ego_network_type_to_str(ego_network_type_t net)
{
    switch (net) {
        case EGO_NETWORK_WIFI:
            return "wifi";
        case EGO_NETWORK_LTE:
            return "lte";
        case EGO_NETWORK_MULTI:
            return "multi";
        default:
            return "offline";
    }
}

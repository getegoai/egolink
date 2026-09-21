"""Native unit tests for embedded Ego-State Engine (C component)."""

import unittest
from pathlib import Path
import os

from quality_tests.native_convergence import run_c

ROOT = Path(__file__).resolve().parents[1]
IDF = Path(os.environ.get("IDF_PATH", "C:/Espressif/v5.4.2/esp-idf"))
MBEDTLS_SHA256 = IDF / "components" / "mbedtls" / "mbedtls" / "library" / "sha256.c"
MBEDTLS_PLATFORM_UTIL = IDF / "components" / "mbedtls" / "mbedtls" / "library" / "platform_util.c"

HARNESS = r"""
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "ego_state_engine.h"

static void test_initialization_and_stationary(void)
{
    ego_state_engine_ctx_t ctx;
    assert(ego_state_engine_init(NULL, "test-001", 1, "0.1.0", "abc") == ESP_ERR_INVALID_ARG);
    assert(ego_state_engine_init(&ctx, "test-001", 171, "0.1.0", "elf_sha_123") == ESP_OK);

    /* Feed 20 stationary samples (approx 1g Z, almost zero noise) */
    int64_t base_time = 1000000000LL;
    for (int i = 0; i < 20; ++i) {
        assert(ego_state_engine_feed_imu(&ctx, 5, -3, 1002, 10, -15, 5, base_time + (int64_t)i * 50000000LL, false) == ESP_OK);
    }

    assert(ego_state_engine_feed_location(&ctx, true, 0.0f, 22.5431, 114.0579, 1.1f, 16, 0.0f, base_time + 20LL * 50000000LL) == ESP_OK);
    assert(ego_state_engine_feed_power(&ctx, 99.0f, 4250, false) == ESP_OK);
    assert(ego_state_engine_feed_network(&ctx, EGO_NETWORK_LTE, -85.0f, "460-00-1111", 0, NULL) == ESP_OK);

    ego_state_estimation_t state;
    ego_evidence_chain_t evidence;
    assert(ego_state_engine_evaluate(&ctx, base_time + 20LL * 50000000LL, 1000, &state, &evidence) == ESP_OK);

    assert(state.spatial_mobility == EGO_SPATIAL_MOBILITY_STATIONARY);
    assert(state.posture_anomaly == EGO_POSTURE_ANOMALY_NORMAL);
    assert(state.device_wear_state == EGO_DEVICE_WEAR_TABLETOP_RESTING);
    assert(state.confidence >= 0.90f);
    assert(strlen(state.primary_evidence_digest) == 64);
    assert(strcmp(state.primary_evidence_digest, evidence.evidence_digest) == 0);
    assert(evidence.imu_evidence.sample_count == 20);
    assert(evidence.imu_evidence.motion_rms_m_s2 < 0.10f);
}

static void test_walking_and_running(void)
{
    ego_state_engine_ctx_t ctx;
    assert(ego_state_engine_init(&ctx, "test-001", 171, "0.1.0", "elf_sha_123") == ESP_OK);

    /* Walking gait */
    int64_t base_time = 2000000000LL;
    for (int i = 0; i < 30; ++i) {
        float az = (i % 4 < 2) ? 1400.0f : 650.0f;
        assert(ego_state_engine_feed_imu(&ctx, 200.0f, 50.0f, az, 200.0f, -150.0f, 100.0f, base_time + (int64_t)i * 50000000LL, false) == ESP_OK);
    }
    assert(ego_state_engine_feed_location(&ctx, true, 1.2f, 22.5432, 114.0580, 1.4f, 14, 90.0f, base_time + 30LL * 50000000LL) == ESP_OK);

    ego_state_estimation_t state;
    assert(ego_state_engine_evaluate(&ctx, base_time + 30LL * 50000000LL, 1000, &state, NULL) == ESP_OK);
    assert(state.spatial_mobility == EGO_SPATIAL_MOBILITY_PEDESTRIAN_WALKING);
    assert(state.device_wear_state == EGO_DEVICE_WEAR_WEARABLE_OR_BAG);

    /* Running: speed >= 1.8 and rms >= 1.2 */
    for (int i = 0; i < 20; ++i) {
        float az = (i % 2 == 0) ? 2200.0f : 200.0f;
        assert(ego_state_engine_feed_imu(&ctx, 600.0f, 200.0f, az, 400.0f, -300.0f, 200.0f, base_time + 1000000000LL + (int64_t)i * 50000000LL, false) == ESP_OK);
    }
    assert(ego_state_engine_feed_location(&ctx, true, 2.8f, 22.5435, 114.0585, 1.2f, 16, 95.0f, base_time + 1000000000LL + 20LL * 50000000LL) == ESP_OK);
    assert(ego_state_engine_evaluate(&ctx, base_time + 1000000000LL + 20LL * 50000000LL, 1000, &state, NULL) == ESP_OK);
    assert(state.spatial_mobility == EGO_SPATIAL_MOBILITY_RUNNING);

    /* In vehicle: speed >= 4.0 */
    assert(ego_state_engine_feed_location(&ctx, true, 15.0f, 22.5500, 114.0700, 1.0f, 18, 120.0f, base_time + 2000000000LL) == ESP_OK);
    assert(ego_state_engine_evaluate(&ctx, base_time + 2000000000LL, 1000, &state, NULL) == ESP_OK);
    assert(state.spatial_mobility == EGO_SPATIAL_MOBILITY_IN_VEHICLE);
}

static void test_shock_and_suspected_fall(void)
{
    ego_state_engine_ctx_t ctx;
    assert(ego_state_engine_init(&ctx, "test-001", 171, "0.1.0", "elf_sha_123") == ESP_OK);

    int64_t t0 = 5000000000LL;
    /* Normal sample */
    assert(ego_state_engine_feed_imu(&ctx, 0, 0, 1000, 0, 0, 0, t0, false) == ESP_OK);

    /* Shock impact > 25 m/s^2 (2600 mg = ~25.5 m/s^2) */
    assert(ego_state_engine_feed_imu(&ctx, 2600, 500, 1200, 3000, 2000, 1000, t0 + 50000000LL, false) == ESP_OK);

    ego_state_estimation_t state_shock;
    assert(ego_state_engine_evaluate(&ctx, t0 + 50000000LL, 1000, &state_shock, NULL) == ESP_OK);
    assert(state_shock.posture_anomaly == EGO_POSTURE_ANOMALY_ABNORMAL_SHOCK);

    /* 2 seconds later: complete immobility / stillness following shock */
    int64_t t_after = t0 + 2000000000LL;
    for (int i = 0; i < 20; ++i) {
        assert(ego_state_engine_feed_imu(&ctx, 0, 0, 1000, 0, 0, 0, t_after + (int64_t)i * 50000000LL, false) == ESP_OK);
    }
    ego_state_estimation_t state_fall;
    assert(ego_state_engine_evaluate(&ctx, t_after + 20LL * 50000000LL, 1000, &state_fall, NULL) == ESP_OK);
    assert(state_fall.posture_anomaly == EGO_POSTURE_ANOMALY_SUSPECTED_FALL);
}

static void test_charging_and_handheld(void)
{
    ego_state_engine_ctx_t ctx;
    assert(ego_state_engine_init(&ctx, "test-001", 171, "0.1.0", "elf_sha_123") == ESP_OK);

    /* Charging docked */
    assert(ego_state_engine_feed_power(&ctx, 80.0f, 4100, true) == ESP_OK);
    assert(ego_state_engine_feed_imu(&ctx, 0, 0, 1000, 0, 0, 0, 1000, false) == ESP_OK);
    ego_state_estimation_t state;
    assert(ego_state_engine_evaluate(&ctx, 2000, 1000, &state, NULL) == ESP_OK);
    assert(state.device_wear_state == EGO_DEVICE_WEAR_CHARGING_DOCKED);

    /* Handheld: stationary linear accel (rms < 0.3) but subtle tremor (gyro_var > 0.05) */
    assert(ego_state_engine_init(&ctx, "test-001", 171, "0.1.0", "elf_sha_123") == ESP_OK);
    assert(ego_state_engine_feed_power(&ctx, 80.0f, 4100, false) == ESP_OK);
    for (int i = 0; i < 20; ++i) {
        float gx = (i % 2 == 0) ? 300.0f : -250.0f;
        float gy = (i % 2 == 0) ? 200.0f : -180.0f;
        float gz = (i % 2 == 0) ? 150.0f : -120.0f;
        assert(ego_state_engine_feed_imu(&ctx, 10, -5, 1000, gx, gy, gz, (int64_t)i * 50000000LL, false) == ESP_OK);
    }
    assert(ego_state_engine_evaluate(&ctx, 20LL * 50000000LL, 1000, &state, NULL) == ESP_OK);
    assert(state.spatial_mobility == EGO_SPATIAL_MOBILITY_STATIONARY);
    assert(state.device_wear_state == EGO_DEVICE_WEAR_HANDHELD);
}

static void test_indoor_and_immobility(void)
{
    ego_state_engine_ctx_t ctx;
    assert(ego_state_engine_init(&ctx, "test-001", 171, "0.1.0", "elf_sha_123") == ESP_OK);

    /* 1. Indoor with Wi-Fi APs */
    for (int i = 0; i < 20; ++i) {
        assert(ego_state_engine_feed_imu(&ctx, 0, 0, 1000, 0, 0, 0, (int64_t)i * 50000000LL, false) == ESP_OK);
    }
    assert(ego_state_engine_feed_location(&ctx, false, 0.0f, 0, 0, 0, 0, 0, 0) == ESP_OK);
    assert(ego_state_engine_feed_network(&ctx, EGO_NETWORK_WIFI, 0.0f, NULL, 5, "hash_wifi_123") == ESP_OK);

    ego_state_estimation_t state;
    assert(ego_state_engine_evaluate(&ctx, 20LL * 50000000LL, 1000, &state, NULL) == ESP_OK);
    assert(state.spatial_mobility == EGO_SPATIAL_MOBILITY_INDOOR_WEAK_GNSS);

    /* 2. Prolonged immobility: continuous stillness > 300 seconds */
    int64_t t1 = 1000000000LL;
    assert(ego_state_engine_evaluate(&ctx, t1, 1000, &state, NULL) == ESP_OK);
    assert(state.posture_anomaly == EGO_POSTURE_ANOMALY_NORMAL);

    int64_t t2 = t1 + 301000000000LL;
    for (int i = 0; i < 20; ++i) {
        assert(ego_state_engine_feed_imu(&ctx, 0, 0, 1000, 0, 0, 0, t2 - (int64_t)(20 - i) * 50000000LL, false) == ESP_OK);
    }
    assert(ego_state_engine_evaluate(&ctx, t2, 1000, &state, NULL) == ESP_OK);
    assert(state.posture_anomaly == EGO_POSTURE_ANOMALY_PROLONGED_IMMOBILITY);
}

static void test_string_helpers(void)
{
    assert(strcmp(ego_spatial_mobility_to_str(EGO_SPATIAL_MOBILITY_STATIONARY), "stationary") == 0);
    assert(strcmp(ego_spatial_mobility_to_str(EGO_SPATIAL_MOBILITY_PEDESTRIAN_WALKING), "pedestrian_walking") == 0);
    assert(strcmp(ego_spatial_mobility_to_str(EGO_SPATIAL_MOBILITY_RUNNING), "running") == 0);
    assert(strcmp(ego_spatial_mobility_to_str(EGO_SPATIAL_MOBILITY_IN_VEHICLE), "in_vehicle") == 0);
    assert(strcmp(ego_spatial_mobility_to_str(EGO_SPATIAL_MOBILITY_INDOOR_WEAK_GNSS), "indoor_weak_gnss") == 0);

    assert(strcmp(ego_posture_anomaly_to_str(EGO_POSTURE_ANOMALY_NORMAL), "normal") == 0);
    assert(strcmp(ego_posture_anomaly_to_str(EGO_POSTURE_ANOMALY_ABNORMAL_SHOCK), "abnormal_shock") == 0);
    assert(strcmp(ego_posture_anomaly_to_str(EGO_POSTURE_ANOMALY_SUSPECTED_FALL), "suspected_fall") == 0);
    assert(strcmp(ego_posture_anomaly_to_str(EGO_POSTURE_ANOMALY_PROLONGED_IMMOBILITY), "prolonged_immobility") == 0);

    assert(strcmp(ego_device_wear_to_str(EGO_DEVICE_WEAR_TABLETOP_RESTING), "tabletop_resting") == 0);
    assert(strcmp(ego_device_wear_to_str(EGO_DEVICE_WEAR_HANDHELD), "handheld") == 0);
    assert(strcmp(ego_device_wear_to_str(EGO_DEVICE_WEAR_WEARABLE_OR_BAG), "wearable_or_bag") == 0);
    assert(strcmp(ego_device_wear_to_str(EGO_DEVICE_WEAR_CHARGING_DOCKED), "charging_docked") == 0);

    assert(strcmp(ego_network_type_to_str(EGO_NETWORK_WIFI), "wifi") == 0);
    assert(strcmp(ego_network_type_to_str(EGO_NETWORK_LTE), "lte") == 0);
    assert(strcmp(ego_network_type_to_str(EGO_NETWORK_OFFLINE), "offline") == 0);
}

int main(void)
{
    test_initialization_and_stationary();
    test_walking_and_running();
    test_shock_and_suspected_fall();
    test_charging_and_handheld();
    test_indoor_and_immobility();
    test_string_helpers();
    printf("ALL EGO STATE ENGINE TESTS PASSED\n");
    return 0;
}
"""


class TestEgoStateEngineNative(unittest.TestCase):
    def test_native_ego_state_engine(self) -> None:
        extra_srcs = [str(MBEDTLS_SHA256)]
        if MBEDTLS_PLATFORM_UTIL.is_file():
            extra_srcs.append(str(MBEDTLS_PLATFORM_UTIL))

        stdout = run_c(
            harness=HARNESS,
            components=("ego_state_engine",),
            extra_sources=extra_srcs,
        )
        self.assertIn("ALL EGO STATE ENGINE TESTS PASSED", stdout)

    def test_collection_main_integration(self) -> None:
        main_c = (ROOT / "firmware" / "mqtt_heartbeat" / "main" / "collection_main.c").read_text(encoding="utf-8")
        self.assertIn('#include "ego_state_engine.h"', main_c)
        self.assertIn("static ego_state_engine_ctx_t s_ego_state_engine;", main_c)
        self.assertIn("static SemaphoreHandle_t s_ego_state_mutex;", main_c)
        self.assertIn("static atomic_bool s_ego_state_ready;", main_c)
        self.assertIn("ego_state_engine_feed_imu(", main_c)
        self.assertIn("ego_state_engine_feed_network(", main_c)
        self.assertIn("ego_state_engine_feed_location(", main_c)
        self.assertIn("ego_state_engine_feed_power(", main_c)
        self.assertIn("ego_state_engine_evaluate(", main_c)
        self.assertIn('cJSON_AddObjectToObject(p, "ego_state")', main_c)
        self.assertIn("ego_state_engine_init(&s_ego_state_engine,", main_c)
        self.assertIn('"ego_state_engine_enabled"', main_c)


if __name__ == "__main__":
    unittest.main()

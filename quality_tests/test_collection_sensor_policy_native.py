"""Execute the collector's sensor policy and IMU window detector as real freestanding C."""

import unittest

from quality_tests.native_convergence import run_c


HARNESS = r"""
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "collection_sensor_policy.h"

static void feed_stationary_samples(collection_sensor_policy_t *policy, uint64_t *clock_ms, int count)
{
    for (int i = 0; i < count; i++) {
        /* Flat 1g on Z axis: ax=0, ay=0, az=1000mg = 9.80665 m/s^2 */
        collection_sensor_policy_feed_imu_sample(policy, 0, 0, 1000, *clock_ms);
        *clock_ms += 50; /* 20Hz = 50ms */
    }
}

static void feed_moving_samples(collection_sensor_policy_t *policy, uint64_t *clock_ms, int count)
{
    for (int i = 0; i < count; i++) {
        /* Large acceleration: ax=400, ay=400, az=1300mg -> |a| ~ 1.41g = 13.8 m/s^2, dev ~ 4.0 m/s^2 >> 0.8 */
        collection_sensor_policy_feed_imu_sample(policy, 400, 400, 1300, *clock_ms);
        *clock_ms += 50;
    }
}

int main(void)
{
    collection_sensor_policy_t policy;
    assert(collection_sensor_policy_init(&policy));

    collection_sensor_policy_snapshot_t s = collection_sensor_policy_snapshot(&policy);
    assert(strcmp(s.config_id, "p0-sprint1-engineering-default-20260823") == 0);
    assert(strcmp(s.config_hash, "c9445e465f22d732c07477d6d32b7985db6478871355df96b5285086ba6ded6d") == 0);

    uint64_t clock_ms = 1000;

    /* Feed a fine GNSS fix to resolve location uncertainty */
    collection_sensor_policy_feed_gnss_result(&policy, true, false, clock_ms);
    s = collection_sensor_policy_snapshot(&policy);

    /* 1. Feed 85 stationary samples (4250ms = 2 windows of 2000ms) */
    feed_stationary_samples(&policy, &clock_ms, 85);
    s = collection_sensor_policy_snapshot(&policy);

    assert(s.mobility_state == EGOLINK_LOCATION_POLICY_MOBILITY_STABLE);
    assert(s.policy_mode == EGOLINK_LOCATION_POLICY_STABLE);
    assert(s.current_rms_m_s2 < 0.1);
    assert(s.gnss_interval_ms == 600000); /* 600s */
    assert(s.cell_interval_ms == 300000); /* 300s */
    assert(strcmp(collection_sensor_policy_mode_name(s.policy_mode), "stable") == 0);
    assert(strcmp(collection_sensor_policy_mobility_name(s.mobility_state), "stable") == 0);
    assert(!collection_sensor_policy_consume_immediate_gnss(&policy));

    /* 2. Feed moving samples (3 windows of 2000ms = 120 samples) */
    feed_moving_samples(&policy, &clock_ms, 120);
    s = collection_sensor_policy_snapshot(&policy);

    assert(s.mobility_state == EGOLINK_LOCATION_POLICY_MOBILITY_MOVING);
    assert(s.policy_mode == EGOLINK_LOCATION_POLICY_MOVING);
    assert(s.current_rms_m_s2 >= 0.8);
    assert(s.gnss_interval_ms == 120000); /* 120s */
    assert(s.cell_interval_ms == 60000);  /* 60s */
    assert(strcmp(collection_sensor_policy_mode_name(s.policy_mode), "moving") == 0);
    assert(strcmp(collection_sensor_policy_mobility_name(s.mobility_state), "moving") == 0);

    /* Verify immediate GNSS trigger was armed and can be consumed exactly once */
    assert(collection_sensor_policy_consume_immediate_gnss(&policy) == true);
    assert(collection_sensor_policy_consume_immediate_gnss(&policy) == false);

    /* 3. Feed low battery (15%) -> LOW_BATTERY mode takes priority */
    collection_sensor_policy_feed_battery(&policy, 15.0, false, false, clock_ms);
    s = collection_sensor_policy_snapshot(&policy);

    assert(s.policy_mode == EGOLINK_LOCATION_POLICY_LOW_BATTERY);
    assert(s.low_battery_latched == true);
    assert(s.gnss_interval_ms == 900000); /* 900s */
    assert(s.cell_interval_ms == 600000); /* 600s */
    assert(strcmp(collection_sensor_policy_mode_name(s.policy_mode), "low_battery") == 0);

    /* 4. Recover battery (30%) -> back to MOVING */
    collection_sensor_policy_feed_battery(&policy, 30.0, false, false, clock_ms);
    s = collection_sensor_policy_snapshot(&policy);
    assert(s.policy_mode == EGOLINK_LOCATION_POLICY_MOVING);
    assert(s.low_battery_latched == false);

    /* 5. Return to stationary for 3 windows -> back to STABLE */
    feed_stationary_samples(&policy, &clock_ms, 120);
    s = collection_sensor_policy_snapshot(&policy);
    assert(s.mobility_state == EGOLINK_LOCATION_POLICY_MOBILITY_STABLE);
    assert(s.policy_mode == EGOLINK_LOCATION_POLICY_STABLE);
    assert(s.gnss_interval_ms == 600000);

    /* 6. Intermediate acceleration (dev ~ 0.55 m/s^2, between 0.3 and 0.8) maintains STABLE */
    for (int i = 0; i < 80; i++) {
        /* ax=100, ay=100, az=1000mg -> |a| = sqrt(0.1^2+0.1^2+1.0^2)*g = 1.00995g = 9.904 m/s^2, dev = 0.098 m/s^2 */
        collection_sensor_policy_feed_imu_sample(&policy, 200, 200, 1000, clock_ms);
        clock_ms += 50;
    }
    s = collection_sensor_policy_snapshot(&policy);
    assert(s.mobility_state == EGOLINK_LOCATION_POLICY_MOBILITY_STABLE);
    assert(s.policy_mode == EGOLINK_LOCATION_POLICY_STABLE);

    /* 7. Feed cell query and tick */
    collection_sensor_policy_feed_cell_result(&policy, true, clock_ms);
    collection_sensor_policy_tick(&policy, clock_ms + 1000);

    /* 8. Null-pointer safety */
    assert(!collection_sensor_policy_init(NULL));
    collection_sensor_policy_feed_imu_sample(NULL, 0, 0, 0, 0);
    collection_sensor_policy_feed_battery(NULL, 0.0, false, false, 0);
    collection_sensor_policy_feed_gnss_result(NULL, false, false, 0);
    collection_sensor_policy_feed_cell_result(NULL, false, 0);
    collection_sensor_policy_tick(NULL, 0);
    assert(!collection_sensor_policy_consume_immediate_gnss(NULL));

    printf("PASS: collection_sensor_policy_native\n");
    return 0;
}
"""


class CollectionSensorPolicyNativeTests(unittest.TestCase):
    def test_movement_transitions_schedule_modulation_and_immediate_trigger(self) -> None:
        stdout = run_c(
            HARNESS,
            components=("location_policy_core", "collection_sensor_policy"),
            timeout=30,
        )
        self.assertIn("PASS: collection_sensor_policy_native", stdout)


if __name__ == "__main__":
    unittest.main()

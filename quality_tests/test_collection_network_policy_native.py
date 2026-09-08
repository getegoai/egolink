"""Execute the collector's route policy as real freestanding C."""

import unittest

from quality_tests.native_convergence import run_c


HARNESS = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "collection_network_policy.h"

static collection_network_policy_snapshot_t event(
    collection_network_policy_t *policy, collection_network_event_type_t type,
    uint64_t now_ms, uint32_t attempt)
{
    collection_network_policy_event_t input = {
        .type = type, .now_ms = now_ms, .lte_attempt_id = attempt,
    };
    return collection_network_policy_handle(policy, &input);
}

static collection_network_policy_config_t config(bool enabled)
{
    return (collection_network_policy_config_t){
        .lte_enabled = enabled,
        .lte_attempt_timeout_ms = 1000,
        .retry_initial_ms = 100,
        .retry_max_ms = 400,
    };
}

int main(void)
{
    collection_network_policy_t policy;
    collection_network_policy_config_t c = config(false);
    assert(collection_network_policy_init(&policy, &c));
    collection_network_policy_snapshot_t s = collection_network_policy_snapshot(&policy);
    assert(s.state == COLLECTION_NETWORK_NO_ROUTE);
    assert(s.route == COLLECTION_NETWORK_ROUTE_NONE && s.route_generation == 1);
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_READY, 1, 0);
    assert(s.state == COLLECTION_NETWORK_WIFI_READY && s.route == COLLECTION_NETWORK_ROUTE_WIFI);
    assert(s.route_generation == 2 && s.actions == COLLECTION_NETWORK_ACTION_NONE);
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_READY, 2, 0);
    assert(s.route_generation == 2);
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_LOST, 3, 0);
    assert(s.state == COLLECTION_NETWORK_NO_ROUTE && s.route == COLLECTION_NETWORK_ROUTE_NONE);
    assert(s.route_generation == 3 && s.actions == COLLECTION_NETWORK_ACTION_NONE);

    c = config(true);
    assert(collection_network_policy_init(&policy, &c));
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_LOST, 0, 0);
    uint32_t first = s.active_lte_attempt_id;
    assert(first && s.state == COLLECTION_NETWORK_LTE_DIALING);
    assert(s.actions == COLLECTION_NETWORK_ACTION_START_LTE && s.attempt_deadline_ms == 1000);
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_READY, 10, first + 1);
    assert(s.state == COLLECTION_NETWORK_LTE_DIALING && s.route == COLLECTION_NETWORK_ROUTE_NONE);
    s = event(&policy, COLLECTION_NETWORK_EVENT_TICK, 999, 0);
    assert(s.actions == 0 && s.state == COLLECTION_NETWORK_LTE_DIALING);
    s = event(&policy, COLLECTION_NETWORK_EVENT_TICK, 1000, 0);
    assert(s.state == COLLECTION_NETWORK_SWITCHING);
    assert(s.actions == COLLECTION_NETWORK_ACTION_STOP_LTE && s.retry_at_ms == 1100);
    s = event(&policy, COLLECTION_NETWORK_EVENT_TICK, 1001, 0);
    assert(s.actions == 0); /* stop request is an edge, never a spin */
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_QUIESCED, 1050, first + 1);
    assert(s.state == COLLECTION_NETWORK_SWITCHING); /* stale completion ignored */
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_QUIESCED, 1050, first);
    assert(s.state == COLLECTION_NETWORK_NO_ROUTE && s.actions == 0);
    s = event(&policy, COLLECTION_NETWORK_EVENT_TICK, 1099, 0);
    assert(s.actions == 0);
    s = event(&policy, COLLECTION_NETWORK_EVENT_TICK, 1100, 0);
    uint32_t second = s.active_lte_attempt_id;
    assert(second != first && s.actions == COLLECTION_NETWORK_ACTION_START_LTE);
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_READY, 1150, second);
    assert(s.state == COLLECTION_NETWORK_LTE_READY && s.route == COLLECTION_NETWORK_ROUTE_LTE);
    assert(s.route_generation == 2);

    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_READY, 1200, 0);
    assert(s.state == COLLECTION_NETWORK_SWITCHING && s.route == COLLECTION_NETWORK_ROUTE_NONE);
    assert(s.route_generation == 3 && s.actions == COLLECTION_NETWORK_ACTION_STOP_LTE);
    /* A flap while LTE is retiring stays on the same offline generation and
     * cannot start another route or another LTE teardown edge. */
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_LOST, 1200, 0);
    assert(s.state == COLLECTION_NETWORK_SWITCHING && s.route == COLLECTION_NETWORK_ROUTE_NONE);
    assert(s.route_generation == 3 && s.actions == 0);
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_READY, 1200, 0);
    assert(s.state == COLLECTION_NETWORK_SWITCHING && s.route == COLLECTION_NETWORK_ROUTE_NONE);
    assert(s.route_generation == 3 && s.actions == 0);
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_QUIESCED, 1201, first);
    assert(s.state == COLLECTION_NETWORK_SWITCHING);
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_QUIESCED, 1201, second);
    assert(s.state == COLLECTION_NETWORK_WIFI_READY && s.route == COLLECTION_NETWORK_ROUTE_WIFI);
    assert(s.route_generation == 4);
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_LOST, 1300, 0);
    uint32_t third = s.active_lte_attempt_id;
    assert(s.route == COLLECTION_NETWORK_ROUTE_NONE && s.route_generation == 5);
    assert(third != second && s.actions == COLLECTION_NETWORK_ACTION_START_LTE);
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_FAILED, 1310, third);
    assert(s.actions == COLLECTION_NETWORK_ACTION_STOP_LTE && s.retry_at_ms == 1410);
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_READY, 1311, 0);
    assert(s.state == COLLECTION_NETWORK_SWITCHING && s.retry_at_ms == 1410);
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_LOST, 1312, 0);
    assert(s.state == COLLECTION_NETWORK_SWITCHING && s.retry_at_ms == 1410);
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_QUIESCED, 1320, third);
    assert(s.state == COLLECTION_NETWORK_NO_ROUTE && s.actions == 0);
    s = event(&policy, COLLECTION_NETWORK_EVENT_TICK, 1410, 0);
    uint32_t fourth = s.active_lte_attempt_id;
    assert(fourth != third && s.actions == COLLECTION_NETWORK_ACTION_START_LTE);
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_FAILED, 1420, fourth);
    assert(s.retry_at_ms == 1620); /* bounded exponential backoff: 100 -> 200 */

    s = event(&policy, COLLECTION_NETWORK_EVENT_STOP, 1430, 0);
    assert(s.state == COLLECTION_NETWORK_STOPPING && s.route == COLLECTION_NETWORK_ROUTE_NONE);
    assert(s.actions == 0); /* the preceding failure already requested stop */
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_QUIESCED, 1431, fourth + 1);
    assert(s.state == COLLECTION_NETWORK_STOPPING);
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_QUIESCED, 1431, fourth);
    assert(s.state == COLLECTION_NETWORK_STOPPED && !s.active_lte_attempt_id);
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_READY, 1500, 0);
    assert(s.state == COLLECTION_NETWORK_STOPPED && s.route == COLLECTION_NETWORK_ROUTE_NONE);

    uint32_t retire_generation = 3;
    assert(!collection_network_retirement_ready(&retire_generation, 3, 2, 2));
    assert(retire_generation == 3);
    /* Route flap: follow generation 4 without resetting any caller deadline,
     * and reject the old generation's retirement. */
    assert(!collection_network_retirement_ready(&retire_generation, 4, 0, 3));
    assert(retire_generation == 4);
    assert(collection_network_retirement_ready(&retire_generation, 4, 0, 4));
    assert(!collection_network_retirement_ready(NULL, 4, 0, 4));
    assert(!collection_network_retirement_ready(&retire_generation, 0, 0, 0));

    c = config(true);
    assert(collection_network_policy_init(&policy, &c));
    s = event(&policy, COLLECTION_NETWORK_EVENT_STOP, 0, 0);
    assert(s.state == COLLECTION_NETWORK_STOPPED && s.actions == 0);
    assert(!collection_network_policy_init(NULL, &c));
    c.retry_initial_ms = 401;
    assert(!collection_network_policy_init(&policy, &c));
    assert(!strcmp(collection_network_state_name(COLLECTION_NETWORK_LTE_DIALING), "LTE_DIALING"));
    assert(!strcmp(collection_network_route_name(COLLECTION_NETWORK_ROUTE_NONE), "offline"));

    c = config(true);
    assert(collection_network_policy_init(&policy, &c));
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_LOST, 0, 0);
    uint32_t failed_cleanup = s.active_lte_attempt_id;
    s = event(&policy, COLLECTION_NETWORK_EVENT_WIFI_READY, 1, 0);
    assert(s.state == COLLECTION_NETWORK_SWITCHING && s.route == COLLECTION_NETWORK_ROUTE_NONE);
    s = event(&policy, COLLECTION_NETWORK_EVENT_LTE_DISABLED, 2, failed_cleanup);
    assert(s.state == COLLECTION_NETWORK_WIFI_READY && s.route == COLLECTION_NETWORK_ROUTE_WIFI);
    assert(!policy.config.lte_enabled && policy.stop_blocked);
    s = event(&policy, COLLECTION_NETWORK_EVENT_STOP, 3, 0);
    assert(s.state == COLLECTION_NETWORK_STOPPING && s.route == COLLECTION_NETWORK_ROUTE_NONE);
    s = event(&policy, COLLECTION_NETWORK_EVENT_TICK, 4, 0);
    assert(s.state == COLLECTION_NETWORK_STOPPING); /* cleanup failure is never STOPPED */
    puts("collector network policy native PASS");
    return 0;
}
"""


class CollectionNetworkPolicyNativeTests(unittest.TestCase):
    def test_wifi_priority_lte_timeout_backoff_stale_tokens_and_stop(self):
        output = run_c(HARNESS, components=("collection_network_policy",))
        self.assertIn("network policy native PASS", output)


if __name__ == "__main__":
    unittest.main()

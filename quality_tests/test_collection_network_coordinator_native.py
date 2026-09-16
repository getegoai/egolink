"""Execute the production collector policy/coordinator combination as native C.

The connector is a deterministic in-memory boundary. No USB enumeration, SIM,
serial port, network, flash, descriptor, credential, spool or ACK I/O occurs.
"""

import unittest

from quality_tests.native_convergence import run_c


HARNESS = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "collection_network_coordinator.h"
#include "collection_network_policy.h"

typedef struct {
    collection_network_connector_status_t status;
    collection_network_connector_result_t begin_result[5];
    collection_network_connector_result_t polls[32];
    collection_network_connector_operation_t operations[32];
    unsigned poll_head, poll_count, poll_calls, operation_count;
    unsigned cancel_count, quiesce_count;
    bool quiesce_ok;
} fake_connector_t;

typedef struct {
    fake_connector_t connector;
    collection_network_coordinator_t coordinator;
    collection_network_policy_t policy;
    collection_network_policy_snapshot_t policy_snapshot;
    collection_network_retirement_facts_t retirement;
} rig_t;

static collection_network_connector_result_t fake_begin(
    void *context, collection_network_connector_operation_t operation,
    uint32_t timeout_ms, uint32_t expected_epoch)
{
    fake_connector_t *fake = context;
    assert(fake && timeout_ms == 100);
    if (fake->status.connection_epoch != expected_epoch) {
        return COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH;
    }
    assert(fake->operation_count < 32);
    fake->operations[fake->operation_count++] = operation;
    return fake->begin_result[operation];
}

static collection_network_connector_result_t fake_poll(
    void *context, uint32_t expected_epoch)
{
    fake_connector_t *fake = context;
    assert(fake);
    if (fake->status.connection_epoch != expected_epoch) {
        return COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH;
    }
    ++fake->poll_calls;
    if (fake->poll_head < fake->poll_count) {
        return fake->polls[fake->poll_head++];
    }
    return COLLECTION_NETWORK_CONNECTOR_PENDING;
}

static collection_network_connector_result_t fake_cancel_poll(
    void *context, uint32_t expected_epoch)
{
    fake_connector_t *fake = context;
    assert(fake);
    if (fake->status.connection_epoch != expected_epoch) {
        return COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH;
    }
    ++fake->cancel_count;
    return fake_poll(context, expected_epoch);
}

static collection_network_connector_result_t fake_quiesce(
    void *context, uint32_t expected_epoch)
{
    fake_connector_t *fake = context;
    assert(fake);
    if (fake->status.connection_epoch != expected_epoch) {
        return COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH;
    }
    ++fake->quiesce_count;
    return fake->quiesce_ok
        ? COLLECTION_NETWORK_CONNECTOR_OK
        : COLLECTION_NETWORK_CONNECTOR_IO_ERROR;
}

static void fake_get_status(
    void *context, collection_network_connector_status_t *status)
{
    fake_connector_t *fake = context;
    assert(fake && status);
    *status = fake->status;
}

static collection_network_connector_ops_t fake_ops(fake_connector_t *fake)
{
    return (collection_network_connector_ops_t){
        .begin = fake_begin,
        .poll = fake_poll,
        .cancel_poll = fake_cancel_poll,
        .quiesce = fake_quiesce,
        .get_status = fake_get_status,
        .context = fake,
    };
}

static void push_poll(fake_connector_t *fake, collection_network_connector_result_t result)
{
    assert(fake->poll_count < 32);
    fake->polls[fake->poll_count++] = result;
}

static collection_network_policy_snapshot_t policy_event(
    rig_t *rig, collection_network_event_type_t type,
    uint64_t now_ms, uint32_t attempt_id)
{
    collection_network_policy_event_t event = {
        .type = type,
        .now_ms = now_ms,
        .lte_attempt_id = attempt_id,
    };
    rig->policy_snapshot = collection_network_policy_handle(&rig->policy, &event);
    rig->retirement.published_generation = rig->policy_snapshot.route_generation;
    return rig->policy_snapshot;
}

static void consume_notice(
    rig_t *rig, collection_network_coordinator_notice_t notice, uint64_t now_ms)
{
    unsigned count = 0;
    while (notice.valid) {
        assert(++count <= 4);
        collection_network_policy_snapshot_t policy = policy_event(
            rig, notice.type, now_ms, notice.attempt_id);
        notice = collection_network_coordinator_apply_policy(
            &rig->coordinator, &policy, &rig->retirement, now_ms);
    }
}

static void send_event(
    rig_t *rig, collection_network_event_type_t type,
    uint64_t now_ms, uint32_t attempt_id)
{
    collection_network_policy_snapshot_t policy = policy_event(
        rig, type, now_ms, attempt_id);
    collection_network_coordinator_notice_t notice =
        collection_network_coordinator_apply_policy(
            &rig->coordinator, &policy, &rig->retirement, now_ms);
    consume_notice(rig, notice, now_ms);
}

static void poll_coordinator(rig_t *rig, uint64_t now_ms)
{
    collection_network_coordinator_notice_t notice =
        collection_network_coordinator_poll(
            &rig->coordinator, &rig->retirement, now_ms);
    consume_notice(rig, notice, now_ms);
}

static void admit(rig_t *rig, bool admitted, uint64_t now_ms)
{
    collection_network_coordinator_notice_t notice =
        collection_network_coordinator_admit(
            &rig->coordinator,
            rig->policy_snapshot.active_lte_attempt_id,
            admitted,
            now_ms);
    consume_notice(rig, notice, now_ms);
}

static void rig_init(rig_t *rig)
{
    memset(rig, 0, sizeof(*rig));
    rig->connector.status.usb_connected = true;
    rig->connector.status.ppp_stopped = true;
    rig->connector.status.connection_epoch = 1;
    rig->connector.status.result = COLLECTION_NETWORK_CONNECTOR_PENDING;
    rig->connector.quiesce_ok = true;
    collection_network_coordinator_config_t coordinator_config = {
        .command_timeout_ms = 100,
        .cleanup_timeout_ms = 2000,
    };
    collection_network_connector_ops_t connector = fake_ops(&rig->connector);
    assert(collection_network_coordinator_init(
        &rig->coordinator, &coordinator_config, &connector));
    collection_network_coordinator_refresh_status(&rig->coordinator);
    collection_network_coordinator_snapshot_t initial =
        collection_network_coordinator_snapshot(&rig->coordinator);
    assert(initial.ppp_stopped && initial.cleanup_confirmed);

    collection_network_policy_config_t policy_config = {
        .lte_enabled = true,
        .lte_attempt_timeout_ms = 1000,
        .retry_initial_ms = 100,
        .retry_max_ms = 400,
    };
    assert(collection_network_policy_init(&rig->policy, &policy_config));
    rig->policy_snapshot = collection_network_policy_snapshot(&rig->policy);
    rig->retirement = (collection_network_retirement_facts_t){
        .published_generation = rig->policy_snapshot.route_generation,
        .uploader_active_generation = 0,
        .uploader_retired_generation = rig->policy_snapshot.route_generation,
    };
}

static uint32_t begin_attempt(rig_t *rig, uint64_t now_ms)
{
    send_event(rig, COLLECTION_NETWORK_EVENT_WIFI_LOST, now_ms, 0);
    assert(rig->policy_snapshot.state == COLLECTION_NETWORK_LTE_DIALING);
    assert(rig->policy_snapshot.active_lte_attempt_id != 0);
    assert(!collection_network_coordinator_blocks_uart_work(&rig->coordinator));
    return rig->policy_snapshot.active_lte_attempt_id;
}

static void apply_manual_start(rig_t *rig, uint32_t attempt_id, uint64_t now_ms)
{
    collection_network_policy_snapshot_t start = {
        .state = COLLECTION_NETWORK_LTE_DIALING,
        .route = COLLECTION_NETWORK_ROUTE_NONE,
        .route_generation = rig->policy_snapshot.route_generation,
        .active_lte_attempt_id = attempt_id,
        .actions = COLLECTION_NETWORK_ACTION_START_LTE,
    };
    collection_network_coordinator_notice_t notice =
        collection_network_coordinator_apply_policy(
            &rig->coordinator, &start, &rig->retirement, now_ms);
    assert(!notice.valid);
}

static collection_network_coordinator_notice_t apply_manual_stop(
    rig_t *rig, uint32_t attempt_id, uint32_t route_generation,
    uint64_t now_ms)
{
    collection_network_policy_snapshot_t stop = {
        .state = COLLECTION_NETWORK_SWITCHING,
        .route = COLLECTION_NETWORK_ROUTE_NONE,
        .route_generation = route_generation,
        .active_lte_attempt_id = attempt_id,
        .actions = COLLECTION_NETWORK_ACTION_STOP_LTE,
    };
    return collection_network_coordinator_apply_policy(
        &rig->coordinator, &stop, &rig->retirement, now_ms);
}

static void drive_to_dial(rig_t *rig, uint64_t now_ms)
{
    (void)begin_attempt(rig, now_ms);
    admit(rig, true, now_ms + 1);
    assert(collection_network_coordinator_blocks_uart_work(&rig->coordinator));
    push_poll(&rig->connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(rig, now_ms + 2);
    push_poll(&rig->connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(rig, now_ms + 3);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&rig->coordinator);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_DIAL);
    assert(state.dial_submitted && state.command_submitted);
}

static uint32_t drive_online(rig_t *rig, uint64_t now_ms)
{
    drive_to_dial(rig, now_ms);
    uint32_t attempt_id = rig->policy_snapshot.active_lte_attempt_id;
    push_poll(&rig->connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(rig, now_ms + 4);
    assert(!collection_network_coordinator_blocks_uart_work(&rig->coordinator));
    rig->connector.status.data_mode = true;
    rig->connector.status.ppp_stopped = false;
    rig->connector.status.ppp_has_ip = true;
    poll_coordinator(rig, now_ms + 5);
    assert(rig->policy_snapshot.state == COLLECTION_NETWORK_LTE_READY);
    assert(rig->policy_snapshot.route == COLLECTION_NETWORK_ROUTE_LTE);
    return attempt_id;
}

static void finish_guarded_cleanup(rig_t *rig, uint64_t guard_start_ms)
{
    poll_coordinator(rig, guard_start_ms + 999);
    assert(collection_network_coordinator_snapshot(&rig->coordinator).stage ==
        COLLECTION_NETWORK_COORDINATOR_GUARD);
    poll_coordinator(rig, guard_start_ms + 1000);
    assert(collection_network_coordinator_snapshot(&rig->coordinator).stage ==
        COLLECTION_NETWORK_COORDINATOR_ESCAPE);
    push_poll(&rig->connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(rig, guard_start_ms + 1001);
    assert(collection_network_coordinator_snapshot(&rig->coordinator).stage ==
        COLLECTION_NETWORK_COORDINATOR_HANGUP);
    push_poll(&rig->connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(rig, guard_start_ms + 1002);
    assert(collection_network_coordinator_snapshot(&rig->coordinator).stage ==
        COLLECTION_NETWORK_COORDINATOR_WAIT_PPP_DEAD);
    rig->connector.status.data_mode = false;
    rig->connector.status.ppp_has_ip = false;
    rig->connector.status.ppp_stopped = true;
    rig->connector.status.hangup_confirmed = true;
    poll_coordinator(rig, guard_start_ms + 1003);
}

static void test_delayed_usb_and_stale_attempt(void)
{
    rig_t rig;
    rig_init(&rig);
    uint32_t first = begin_attempt(&rig, 0);
    rig.connector.status.usb_connected = false;
    admit(&rig, false, 1);
    assert(rig.policy_snapshot.state == COLLECTION_NETWORK_NO_ROUTE);
    assert(collection_network_coordinator_snapshot(&rig.coordinator).cleanup_confirmed);
    rig.connector.status.usb_connected = true;
    send_event(&rig, COLLECTION_NETWORK_EVENT_TICK, 101, 0);
    uint32_t second = rig.policy_snapshot.active_lte_attempt_id;
    assert(second && second != first);
    send_event(&rig, COLLECTION_NETWORK_EVENT_LTE_READY, 102, first);
    assert(rig.policy_snapshot.state == COLLECTION_NETWORK_LTE_DIALING);
    assert(rig.policy_snapshot.active_lte_attempt_id == second);
    admit(&rig, true, 103);
    assert(rig.connector.operation_count == 1);
    puts("scenario delayed-usb/stale-attempt PASS");
}

static void test_start_replay_preserves_attempt_owner(void)
{
    rig_t active;
    rig_init(&active);
    uint32_t first = begin_attempt(&active, 0);
    collection_network_coordinator_snapshot_t before =
        collection_network_coordinator_snapshot(&active.coordinator);
    apply_manual_start(&active, first, 1);
    apply_manual_start(&active, first + 1U, 2);
    collection_network_coordinator_snapshot_t after =
        collection_network_coordinator_snapshot(&active.coordinator);
    assert(after.stage == before.stage && after.attempt_id == first);
    assert(after.last_started_attempt_id == first);
    assert(active.connector.operation_count == 0);

    admit(&active, true, 3);
    before = collection_network_coordinator_snapshot(&active.coordinator);
    assert(before.stage == COLLECTION_NETWORK_COORDINATOR_PROBE);
    assert(before.command_in_flight);
    unsigned operations = active.connector.operation_count;
    apply_manual_start(&active, first, 4);
    apply_manual_start(&active, first + 1U, 5);
    after = collection_network_coordinator_snapshot(&active.coordinator);
    assert(after.stage == before.stage && after.attempt_id == first);
    assert(after.command_in_flight && after.command_submitted);
    assert(active.connector.operation_count == operations);

    rig_t cleaned;
    rig_init(&cleaned);
    first = begin_attempt(&cleaned, 10);
    admit(&cleaned, false, 11);
    before = collection_network_coordinator_snapshot(&cleaned.coordinator);
    assert(before.stage == COLLECTION_NETWORK_COORDINATOR_IDLE);
    assert(before.attempt_id == 0 && before.last_started_attempt_id == first);
    apply_manual_start(&cleaned, first, 12);
    after = collection_network_coordinator_snapshot(&cleaned.coordinator);
    assert(after.stage == COLLECTION_NETWORK_COORDINATOR_IDLE);
    assert(after.last_started_attempt_id == first);
    assert(cleaned.connector.operation_count == 0);
    apply_manual_start(&cleaned, first + 1U, 13);
    after = collection_network_coordinator_snapshot(&cleaned.coordinator);
    assert(after.stage == COLLECTION_NETWORK_COORDINATOR_WAIT_ADMISSION);
    assert(after.attempt_id == first + 1U);
    apply_manual_start(&cleaned, first, 14);
    assert(collection_network_coordinator_snapshot(&cleaned.coordinator).attempt_id ==
        first + 1U);
    assert(cleaned.connector.operation_count == 0);
    puts("scenario start-replay/owner-preserved PASS");
}

static void test_attempt_wrap_preserves_serial_order(void)
{
    rig_t rig;
    rig_init(&rig);
    rig.coordinator.last_started_attempt_id = UINT32_MAX;
    apply_manual_start(&rig, UINT32_C(1), 1);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_WAIT_ADMISSION);
    assert(state.attempt_id == UINT32_C(1));
    apply_manual_start(&rig, UINT32_MAX, 2);
    state = collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.attempt_id == UINT32_C(1));
    assert(state.last_started_attempt_id == UINT32_C(1));
    assert(rig.connector.operation_count == 0);
    puts("scenario attempt-wrap/serial-order PASS");
}

static void assert_duplicate_stop_preserves_teardown(
    rig_t *rig, uint32_t attempt_id,
    collection_network_coordinator_stage_t expected_stage,
    uint64_t now_ms)
{
    collection_network_coordinator_snapshot_t before =
        collection_network_coordinator_snapshot(&rig->coordinator);
    unsigned operations = rig->connector.operation_count;
    unsigned cancellations = rig->connector.cancel_count;
    unsigned polls = rig->connector.poll_calls;
    unsigned quiesces = rig->connector.quiesce_count;
    collection_network_coordinator_notice_t replay = apply_manual_stop(
        rig, attempt_id, before.retire_generation + UINT32_C(9), now_ms);
    collection_network_coordinator_snapshot_t after =
        collection_network_coordinator_snapshot(&rig->coordinator);
    assert(!replay.valid && after.stage == expected_stage);
    assert(after.attempt_id == before.attempt_id);
    assert(after.retire_generation == before.retire_generation);
    assert(after.retire_deadline_ms == before.retire_deadline_ms);
    assert(rig->connector.operation_count == operations);
    assert(rig->connector.cancel_count == cancellations);
    assert(rig->connector.poll_calls == polls);
    assert(rig->connector.quiesce_count == quiesces);
}

static void test_stop_replay_and_conflict_are_fail_closed(void)
{
    rig_t rig;
    rig_init(&rig);
    uint32_t attempt = drive_online(&rig, 0);
    send_event(&rig, COLLECTION_NETWORK_EVENT_WIFI_READY, 10, 0);
    assert_duplicate_stop_preserves_teardown(
        &rig, attempt, COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER, 11);

    rig.retirement.uploader_active_generation = 0;
    rig.retirement.uploader_retired_generation = rig.retirement.published_generation;
    poll_coordinator(&rig, 12);
    assert_duplicate_stop_preserves_teardown(
        &rig, attempt, COLLECTION_NETWORK_COORDINATOR_GUARD, 13);
    poll_coordinator(&rig, 1012);
    assert_duplicate_stop_preserves_teardown(
        &rig, attempt, COLLECTION_NETWORK_COORDINATOR_ESCAPE, 1013);
    push_poll(&rig.connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(&rig, 1014);
    assert_duplicate_stop_preserves_teardown(
        &rig, attempt, COLLECTION_NETWORK_COORDINATOR_HANGUP, 1015);
    push_poll(&rig.connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(&rig, 1016);
    assert_duplicate_stop_preserves_teardown(
        &rig, attempt, COLLECTION_NETWORK_COORDINATOR_WAIT_PPP_DEAD, 1017);

    rig_t conflict;
    rig_init(&conflict);
    attempt = drive_online(&conflict, 20);
    unsigned operations = conflict.connector.operation_count;
    unsigned cancellations = conflict.connector.cancel_count;
    unsigned polls = conflict.connector.poll_calls;
    collection_network_coordinator_notice_t rejected = apply_manual_stop(
        &conflict, attempt + UINT32_C(1),
        conflict.policy_snapshot.route_generation, 30);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&conflict.coordinator);
    assert(rejected.valid &&
        rejected.type == COLLECTION_NETWORK_EVENT_LTE_FAILED &&
        rejected.attempt_id == attempt);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_ONLINE);
    assert(!state.cleanup_confirmed && state.hangup_required);
    assert(conflict.connector.status.ppp_has_ip &&
        !conflict.connector.status.ppp_stopped);
    assert(conflict.connector.operation_count == operations);
    assert(conflict.connector.cancel_count == cancellations);
    assert(conflict.connector.poll_calls == polls);
    consume_notice(&conflict, rejected, 30);
    state = collection_network_coordinator_snapshot(&conflict.coordinator);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER);
    assert(conflict.policy_snapshot.state == COLLECTION_NETWORK_SWITCHING);

    rig_t stale;
    rig_init(&stale);
    attempt = drive_online(&stale, 40);
    operations = stale.connector.operation_count;
    cancellations = stale.connector.cancel_count;
    polls = stale.connector.poll_calls;
    rejected = apply_manual_stop(
        &stale, UINT32_MAX, stale.policy_snapshot.route_generation, 50);
    state = collection_network_coordinator_snapshot(&stale.coordinator);
    assert(rejected.valid &&
        rejected.type == COLLECTION_NETWORK_EVENT_LTE_FAILED &&
        rejected.attempt_id == attempt);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_ONLINE);
    assert(stale.connector.status.ppp_has_ip &&
        !stale.connector.status.ppp_stopped);
    assert(stale.connector.operation_count == operations);
    assert(stale.connector.cancel_count == cancellations);
    assert(stale.connector.poll_calls == polls);
    consume_notice(&stale, rejected, 50);
    assert(collection_network_coordinator_snapshot(&stale.coordinator).stage ==
        COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER);
    puts("scenario stop-replay/conflict-fail-closed PASS");
}

static void test_predial_failures_cleanup_and_retry(void)
{
    const collection_network_connector_result_t failures[] = {
        COLLECTION_NETWORK_CONNECTOR_TIMEOUT,
        COLLECTION_NETWORK_CONNECTOR_IO_ERROR,
        COLLECTION_NETWORK_CONNECTOR_OVERFLOW,
    };
    for (unsigned i = 0; i < sizeof(failures) / sizeof(failures[0]); ++i) {
        rig_t rig;
        rig_init(&rig);
        (void)begin_attempt(&rig, 0);
        admit(&rig, true, 1);
        push_poll(&rig.connector, failures[i]);
        poll_coordinator(&rig, 2);
        assert(rig.policy_snapshot.state == COLLECTION_NETWORK_SWITCHING);
        rig.retirement.uploader_retired_generation = rig.retirement.published_generation;
        poll_coordinator(&rig, 3);
        collection_network_coordinator_snapshot_t state =
            collection_network_coordinator_snapshot(&rig.coordinator);
        assert(state.stage == COLLECTION_NETWORK_COORDINATOR_IDLE);
        assert(state.cleanup_confirmed);
        assert(rig.policy_snapshot.state == COLLECTION_NETWORK_NO_ROUTE);
        assert(rig.policy.config.lte_enabled && !rig.policy.stop_blocked);
        uint32_t first = rig.policy_snapshot.active_lte_attempt_id;
        send_event(&rig, COLLECTION_NETWORK_EVENT_TICK, 103, 0);
        assert(rig.policy_snapshot.state == COLLECTION_NETWORK_LTE_DIALING);
        assert(rig.policy_snapshot.active_lte_attempt_id != first);
        admit(&rig, true, 104);
        assert(rig.connector.operation_count == 2);
        assert(rig.connector.operations[1] == COLLECTION_NETWORK_CONNECTOR_PROBE);
    }
    puts("scenario predial-failure/cleanup-retry PASS");
}

static void test_uncertain_dial_requires_guarded_hangup(void)
{
    rig_t rig;
    rig_init(&rig);
    rig.connector.begin_result[COLLECTION_NETWORK_CONNECTOR_DIAL] =
        COLLECTION_NETWORK_CONNECTOR_IO_ERROR;
    (void)begin_attempt(&rig, 0);
    admit(&rig, true, 1);
    push_poll(&rig.connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(&rig, 2);
    push_poll(&rig.connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(&rig, 3);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.dial_submitted && !state.data_mode_entered);
    assert(state.hangup_required);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER);
    rig.retirement.uploader_retired_generation = rig.retirement.published_generation;
    poll_coordinator(&rig, 4);
    state = collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_GUARD);
    assert(state.hangup_required && !state.cleanup_confirmed);
    send_event(&rig, COLLECTION_NETWORK_EVENT_WIFI_READY, 5, 0);
    finish_guarded_cleanup(&rig, 4);
    assert(collection_network_coordinator_snapshot(&rig.coordinator).cleanup_confirmed);
    assert(rig.connector.operations[rig.connector.operation_count - 2] ==
        COLLECTION_NETWORK_CONNECTOR_ESCAPE);
    assert(rig.connector.operations[rig.connector.operation_count - 1] ==
        COLLECTION_NETWORK_CONNECTOR_HANGUP);
    puts("scenario uncertain-dial/guarded-hangup PASS");
}

static void test_dial_epoch_failure_retains_hangup_fact(void)
{
    rig_t rig;
    rig_init(&rig);
    drive_to_dial(&rig, 0);
    ++rig.connector.status.connection_epoch;
    poll_coordinator(&rig, 4);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER);
    assert(state.dial_submitted && state.command_in_flight);
    assert(state.hangup_required && !state.cleanup_confirmed);
    puts("scenario dial-epoch/hangup-fact PASS");
}

static void test_epoch_change_and_late_notice_fail_closed(void)
{
    rig_t rig;
    rig_init(&rig);
    uint32_t attempt = drive_online(&rig, 0);
    send_event(&rig, COLLECTION_NETWORK_EVENT_WIFI_READY, 10, 0);
    rig.retirement.uploader_retired_generation = rig.retirement.published_generation;
    ++rig.connector.status.connection_epoch;
    poll_coordinator(&rig, 11);
    assert(collection_network_coordinator_snapshot(&rig.coordinator).stage ==
        COLLECTION_NETWORK_COORDINATOR_DISABLED);
    assert(rig.policy_snapshot.state == COLLECTION_NETWORK_WIFI_READY);
    send_event(&rig, COLLECTION_NETWORK_EVENT_LTE_QUIESCED, 12, attempt);
    assert(rig.policy_snapshot.state == COLLECTION_NETWORK_WIFI_READY);
    send_event(&rig, COLLECTION_NETWORK_EVENT_STOP, 13, 0);
    assert(rig.policy_snapshot.state == COLLECTION_NETWORK_STOPPING);
    puts("scenario epoch-change/late-notice PASS");
}

static void test_generation_retirement_and_wifi_order(void)
{
    rig_t rig;
    rig_init(&rig);
    (void)drive_online(&rig, 0);
    uint32_t online_generation = rig.policy_snapshot.route_generation;
    send_event(&rig, COLLECTION_NETWORK_EVENT_WIFI_READY, 10, 0);
    assert(rig.policy_snapshot.route == COLLECTION_NETWORK_ROUTE_NONE);
    assert(rig.connector.quiesce_count == 0);
    rig.retirement.uploader_active_generation = online_generation;
    rig.retirement.uploader_retired_generation = online_generation;
    poll_coordinator(&rig, 11);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&rig.coordinator);
    uint64_t original_deadline = state.retire_deadline_ms;
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER);
    rig.retirement.published_generation = state.retire_generation + 1;
    rig.retirement.uploader_active_generation = 0;
    rig.retirement.uploader_retired_generation = state.retire_generation;
    poll_coordinator(&rig, 12);
    state = collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.retire_generation == rig.retirement.published_generation);
    assert(state.retire_deadline_ms == original_deadline);
    assert(rig.connector.quiesce_count == 0);
    rig.retirement.uploader_retired_generation = rig.retirement.published_generation;
    poll_coordinator(&rig, 13);
    assert(rig.connector.quiesce_count == 1);
    assert(rig.policy_snapshot.route == COLLECTION_NETWORK_ROUTE_NONE);
    finish_guarded_cleanup(&rig, 13);
    assert(rig.policy_snapshot.state == COLLECTION_NETWORK_WIFI_READY);
    assert(rig.policy_snapshot.route == COLLECTION_NETWORK_ROUTE_WIFI);
    puts("scenario generation-retirement PASS");
    puts("scenario wifi-handoff-order PASS");
}

static void test_uart_owner_gating(void)
{
    rig_t rig;
    rig_init(&rig);
    (void)begin_attempt(&rig, 0);
    assert(!collection_network_coordinator_blocks_uart_work(&rig.coordinator));
    admit(&rig, true, 1);
    assert(collection_network_coordinator_blocks_uart_work(&rig.coordinator));
    unsigned cancellations = rig.connector.cancel_count;
    collection_network_coordinator_cancel_setup(&rig.coordinator);
    assert(rig.connector.cancel_count == cancellations + 1);
    assert(collection_network_coordinator_snapshot(&rig.coordinator).stage ==
        COLLECTION_NETWORK_COORDINATOR_PROBE);
    push_poll(&rig.connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(&rig, 2);
    push_poll(&rig.connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(&rig, 3);
    push_poll(&rig.connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(&rig, 4);
    assert(!collection_network_coordinator_blocks_uart_work(&rig.coordinator));
    rig.connector.status.data_mode = true;
    rig.connector.status.ppp_stopped = false;
    rig.connector.status.ppp_has_ip = true;
    poll_coordinator(&rig, 5);
    send_event(&rig, COLLECTION_NETWORK_EVENT_WIFI_READY, 10, 0);
    assert(collection_network_coordinator_blocks_uart_work(&rig.coordinator));
    uint64_t deadline = collection_network_coordinator_snapshot(
        &rig.coordinator).retire_deadline_ms;
    rig.retirement.uploader_active_generation = rig.policy_snapshot.route_generation - 1;
    poll_coordinator(&rig, deadline);
    collection_network_coordinator_snapshot_t terminal =
        collection_network_coordinator_snapshot(&rig.coordinator);
    assert(terminal.stage == COLLECTION_NETWORK_COORDINATOR_DISABLED);
    assert(terminal.retire_wait_expired && !terminal.cleanup_confirmed);
    assert(collection_network_coordinator_blocks_uart_work(&rig.coordinator));
    assert(rig.connector.quiesce_count == 0);
    puts("scenario uart-usb-owner-gating PASS");
}

static void test_retirement_expiry_is_bounded_terminal_failure(void)
{
    rig_t rig;
    rig_init(&rig);
    drive_to_dial(&rig, 0);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.command_in_flight && state.hangup_required);

    send_event(&rig, COLLECTION_NETWORK_EVENT_WIFI_READY, 4, 0);
    state = collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER);
    uint64_t deadline = state.retire_deadline_ms;
    rig.retirement.uploader_active_generation = UINT32_C(77);
    rig.retirement.uploader_retired_generation =
        rig.retirement.uploader_active_generation;

    push_poll(&rig.connector, COLLECTION_NETWORK_CONNECTOR_PENDING);
    poll_coordinator(&rig, deadline);
    state = collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.retire_wait_expired && state.command_in_flight);
    assert(state.setup_cancel_requested);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_DISABLED);
    assert(!state.cleanup_confirmed && state.hangup_required);
    assert(collection_network_coordinator_blocks_uart_work(&rig.coordinator));
    assert(rig.connector.cancel_count == 1 && rig.connector.quiesce_count == 0);

    unsigned polls = rig.connector.poll_calls;
    push_poll(&rig.connector, COLLECTION_NETWORK_CONNECTOR_OK);
    poll_coordinator(&rig, deadline + 1U);
    state = collection_network_coordinator_snapshot(&rig.coordinator);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_DISABLED);
    assert(state.command_in_flight);
    assert(collection_network_coordinator_blocks_uart_work(&rig.coordinator));
    assert(rig.connector.poll_calls == polls);
    assert(rig.connector.cancel_count == 1 && rig.connector.quiesce_count == 0);
    assert(rig.retirement.uploader_active_generation != 0U);
    puts("scenario retirement-expiry/bounded-terminal PASS");
}

static void test_epoch_fences_expiry_and_cancel_setup(void)
{
    rig_t expiry;
    rig_init(&expiry);
    drive_to_dial(&expiry, 0);
    send_event(&expiry, COLLECTION_NETWORK_EVENT_WIFI_READY, 4, 0);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&expiry.coordinator);
    expiry.retirement.uploader_active_generation = UINT32_C(77);
    expiry.retirement.uploader_retired_generation = UINT32_C(77);
    ++expiry.connector.status.connection_epoch;
    unsigned cancellations = expiry.connector.cancel_count;
    unsigned polls = expiry.connector.poll_calls;
    unsigned quiesces = expiry.connector.quiesce_count;
    poll_coordinator(&expiry, state.retire_deadline_ms);
    state = collection_network_coordinator_snapshot(&expiry.coordinator);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_DISABLED);
    assert(!state.cleanup_confirmed && state.command_in_flight);
    assert(collection_network_coordinator_blocks_uart_work(&expiry.coordinator));
    assert(expiry.connector.cancel_count == cancellations);
    assert(expiry.connector.poll_calls == polls);
    assert(expiry.connector.quiesce_count == quiesces);

    rig_t setup;
    rig_init(&setup);
    drive_to_dial(&setup, 10);
    ++setup.connector.status.connection_epoch;
    cancellations = setup.connector.cancel_count;
    polls = setup.connector.poll_calls;
    collection_network_coordinator_notice_t failed =
        collection_network_coordinator_cancel_setup(&setup.coordinator);
    state = collection_network_coordinator_snapshot(&setup.coordinator);
    assert(failed.valid && failed.type == COLLECTION_NETWORK_EVENT_LTE_DISABLED);
    assert(failed.attempt_id == setup.policy_snapshot.active_lte_attempt_id);
    assert(state.stage == COLLECTION_NETWORK_COORDINATOR_DISABLED);
    assert(!state.cleanup_confirmed && state.command_in_flight);
    assert(collection_network_coordinator_blocks_uart_work(&setup.coordinator));
    assert(setup.connector.cancel_count == cancellations);
    assert(setup.connector.poll_calls == polls);
    puts("scenario epoch-fence/expiry-cancel-setup PASS");
}

static void test_graceful_stop_orders_uploader_and_cleanup(void)
{
    rig_t rig;
    rig_init(&rig);
    uint32_t online_generation = drive_online(&rig, 0);
    send_event(&rig, COLLECTION_NETWORK_EVENT_STOP, 10, 0);
    assert(rig.policy_snapshot.state == COLLECTION_NETWORK_STOPPING);
    assert(rig.policy_snapshot.route == COLLECTION_NETWORK_ROUTE_NONE);
    rig.retirement.uploader_active_generation = online_generation;
    rig.retirement.uploader_retired_generation = online_generation;
    poll_coordinator(&rig, 11);
    assert(rig.connector.quiesce_count == 0);
    collection_network_coordinator_cancel_setup(&rig.coordinator);
    assert(rig.connector.quiesce_count == 0);
    rig.retirement.uploader_active_generation = 0;
    rig.retirement.uploader_retired_generation = rig.retirement.published_generation;
    poll_coordinator(&rig, 12);
    assert(rig.connector.quiesce_count == 1);
    finish_guarded_cleanup(&rig, 12);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&rig.coordinator);
    assert(rig.policy_snapshot.state == COLLECTION_NETWORK_STOPPED);
    assert(state.ppp_stopped && state.hangup_required);
    assert(state.hangup_confirmed && state.cleanup_confirmed);
    puts("scenario graceful-stop PASS");
}

static void test_invalid_init_stale_admit_and_deadline_overflow(void)
{
    collection_network_coordinator_t zero = {0};
    collection_network_policy_snapshot_t start = {
        .actions = COLLECTION_NETWORK_ACTION_START_LTE,
        .active_lte_attempt_id = 1,
        .route_generation = 1,
    };
    collection_network_retirement_facts_t retirement = {0};
    assert(!collection_network_coordinator_apply_policy(
        &zero, &start, &retirement, 0).valid);
    assert(!collection_network_coordinator_admit(&zero, 1, true, 0).valid);
    assert(!collection_network_coordinator_poll(&zero, &retirement, 0).valid);

    collection_network_coordinator_config_t config = {
        .command_timeout_ms = 100,
        .cleanup_timeout_ms = 2000,
    };
    collection_network_connector_ops_t invalid = {0};
    assert(!collection_network_coordinator_init(&zero, &config, &invalid));

    fake_connector_t fake = {0};
    fake.status.usb_connected = true;
    fake.status.ppp_stopped = true;
    fake.status.connection_epoch = 1;
    fake.quiesce_ok = true;
    collection_network_connector_ops_t connector = fake_ops(&fake);
    collection_network_coordinator_t coordinator = {0};
    assert(collection_network_coordinator_init(&coordinator, &config, &connector));
    assert(!collection_network_coordinator_init(&coordinator, &config, &connector));
    assert(!collection_network_coordinator_admit(&coordinator, 2, true, 0).valid);
    assert(fake.operation_count == 0);
    assert(!collection_network_coordinator_apply_policy(
        &coordinator, &start, &retirement, 0).valid);
    assert(!collection_network_coordinator_admit(&coordinator, 2, true, 1).valid);
    assert(fake.operation_count == 0);
    assert(!collection_network_coordinator_admit(&coordinator, 1, true, 1).valid);
    assert(fake.operation_count == 1);
    collection_network_policy_snapshot_t stop = {
        .actions = COLLECTION_NETWORK_ACTION_STOP_LTE,
        .active_lte_attempt_id = 1,
        .route_generation = 2,
    };
    collection_network_coordinator_notice_t overflow =
        collection_network_coordinator_apply_policy(
            &coordinator, &stop, &retirement, UINT64_MAX - 1);
    assert(overflow.valid && overflow.type == COLLECTION_NETWORK_EVENT_LTE_DISABLED);
    assert(collection_network_coordinator_snapshot(&coordinator).stage ==
        COLLECTION_NETWORK_COORDINATOR_DISABLED);

    collection_network_coordinator_t null_context = {0};
    connector.context = NULL;
    assert(collection_network_coordinator_init(&null_context, &config, &connector));
    puts("scenario invalid-init/stale/overflow PASS");
}

static void test_idle_never_dialed_stop(void)
{
    rig_t rig;
    rig_init(&rig);
    send_event(&rig, COLLECTION_NETWORK_EVENT_STOP, 0, 0);
    collection_network_coordinator_snapshot_t state =
        collection_network_coordinator_snapshot(&rig.coordinator);
    assert(rig.policy_snapshot.state == COLLECTION_NETWORK_STOPPED);
    assert(state.ppp_stopped && state.cleanup_confirmed);
    assert(rig.connector.operation_count == 0 && rig.connector.quiesce_count == 0);
    puts("scenario idle-never-dialed-stop PASS");
}

int main(void)
{
    test_delayed_usb_and_stale_attempt();
    test_start_replay_preserves_attempt_owner();
    test_attempt_wrap_preserves_serial_order();
    test_stop_replay_and_conflict_are_fail_closed();
    test_predial_failures_cleanup_and_retry();
    test_uncertain_dial_requires_guarded_hangup();
    test_dial_epoch_failure_retains_hangup_fact();
    test_epoch_change_and_late_notice_fail_closed();
    test_generation_retirement_and_wifi_order();
    test_uart_owner_gating();
    test_retirement_expiry_is_bounded_terminal_failure();
    test_epoch_fences_expiry_and_cancel_setup();
    test_graceful_stop_orders_uploader_and_cleanup();
    test_invalid_init_stale_admit_and_deadline_overflow();
    test_idle_never_dialed_stop();
    puts("collector network coordinator native PASS");
    return 0;
}
"""


class CollectionNetworkCoordinatorNativeTests(unittest.TestCase):
    def test_policy_coordinator_lifecycle_executes_as_native_c(self):
        output = run_c(
            HARNESS,
            components=("collection_network_coordinator", "collection_network_policy"),
        )
        for marker in (
            "scenario delayed-usb/stale-attempt PASS",
            "scenario start-replay/owner-preserved PASS",
            "scenario attempt-wrap/serial-order PASS",
            "scenario stop-replay/conflict-fail-closed PASS",
            "scenario predial-failure/cleanup-retry PASS",
            "scenario uncertain-dial/guarded-hangup PASS",
            "scenario dial-epoch/hangup-fact PASS",
            "scenario epoch-change/late-notice PASS",
            "scenario generation-retirement PASS",
            "scenario wifi-handoff-order PASS",
            "scenario uart-usb-owner-gating PASS",
            "scenario retirement-expiry/bounded-terminal PASS",
            "scenario epoch-fence/expiry-cancel-setup PASS",
            "scenario graceful-stop PASS",
            "scenario invalid-init/stale/overflow PASS",
            "scenario idle-never-dialed-stop PASS",
            "collector network coordinator native PASS",
        ):
            self.assertIn(marker, output)


if __name__ == "__main__":
    unittest.main()

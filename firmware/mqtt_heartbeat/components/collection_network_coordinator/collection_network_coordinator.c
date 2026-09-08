#include "collection_network_coordinator.h"

#include <string.h>

static collection_network_coordinator_notice_t notice(
    collection_network_event_type_t type,
    uint32_t attempt_id,
    bool cleanup_confirmed)
{
    return (collection_network_coordinator_notice_t){
        .valid = true,
        .cleanup_confirmed = cleanup_confirmed,
        .type = type,
        .attempt_id = attempt_id,
    };
}

static bool deadline_after(uint64_t now_ms, uint32_t duration_ms, uint64_t *deadline)
{
    if (!deadline || UINT64_MAX - now_ms < duration_ms) {
        return false;
    }
    *deadline = now_ms + duration_ms;
    return true;
}

static bool attempt_is_newer(uint32_t candidate, uint32_t previous)
{
    if (candidate == 0U) {
        return false;
    }
    if (previous == 0U) {
        return true;
    }
    uint32_t distance = candidate - previous;
    return distance != 0U && distance < UINT32_C(0x80000000);
}

static void get_status(
    collection_network_coordinator_t *coordinator,
    collection_network_connector_status_t *status)
{
    memset(status, 0, sizeof(*status));
    coordinator->connector.get_status(coordinator->connector.context, status);
}

static bool epoch_matches(
    const collection_network_coordinator_t *coordinator,
    const collection_network_connector_status_t *status)
{
    return status->usb_connected &&
        status->connection_epoch == coordinator->connection_epoch;
}

static void reset_attempt(collection_network_coordinator_t *coordinator)
{
    coordinator->stage = COLLECTION_NETWORK_COORDINATOR_IDLE;
    coordinator->attempt_id = 0;
    coordinator->connection_epoch = 0;
    coordinator->retire_generation = 0;
    coordinator->last_submit_ms = 0;
    coordinator->retire_deadline_ms = 0;
    coordinator->guard_start_ms = 0;
    coordinator->cleanup_deadline_ms = 0;
    coordinator->command_submitted = false;
    coordinator->command_in_flight = false;
    coordinator->setup_cancel_requested = false;
    coordinator->dial_submitted = false;
    coordinator->data_mode_entered = false;
    coordinator->retire_wait_expired = false;
}

static collection_network_coordinator_notice_t cleanup_failed_observed(
    collection_network_coordinator_t *coordinator,
    const collection_network_connector_status_t *status)
{
    if (status != NULL) {
        coordinator->ppp_stopped = status->ppp_stopped;
        coordinator->hangup_confirmed = status->hangup_confirmed;
    }
    coordinator->cleanup_confirmed = false;
    coordinator->stage = COLLECTION_NETWORK_COORDINATOR_DISABLED;
    return notice(
        COLLECTION_NETWORK_EVENT_LTE_DISABLED,
        coordinator->attempt_id,
        false);
}

static collection_network_coordinator_notice_t cleanup_failed(
    collection_network_coordinator_t *coordinator)
{
    collection_network_connector_status_t status;
    get_status(coordinator, &status);
    return cleanup_failed_observed(coordinator, &status);
}

static collection_network_coordinator_notice_t cleanup_succeeded(
    collection_network_coordinator_t *coordinator)
{
    collection_network_connector_status_t status;
    get_status(coordinator, &status);
    coordinator->ppp_stopped = status.ppp_stopped;
    coordinator->hangup_confirmed = status.hangup_confirmed;
    uint32_t attempt_id = coordinator->attempt_id;
    reset_attempt(coordinator);
    coordinator->cleanup_confirmed = true;
    return notice(COLLECTION_NETWORK_EVENT_LTE_QUIESCED, attempt_id, true);
}

static collection_network_coordinator_notice_t start_command(
    collection_network_coordinator_t *coordinator,
    collection_network_connector_operation_t operation,
    collection_network_coordinator_stage_t stage,
    uint64_t now_ms)
{
    /* A DIAL call can reach the modem even if USB write or CONNECT parsing
     * later fails. Cleanup must therefore treat data mode as uncertain from
     * before the call onward. */
    coordinator->command_submitted = true;
    if (operation == COLLECTION_NETWORK_CONNECTOR_DIAL) {
        coordinator->dial_submitted = true;
        coordinator->hangup_required = true;
    }
    collection_network_connector_result_t result = coordinator->connector.begin(
        coordinator->connector.context,
        operation,
        coordinator->config.command_timeout_ms,
        coordinator->connection_epoch);
    coordinator->last_submit_ms = now_ms;
    coordinator->cleanup_confirmed = false;
    coordinator->command_in_flight =
        result == COLLECTION_NETWORK_CONNECTOR_PENDING;
    coordinator->setup_cancel_requested = false;
    if (result == COLLECTION_NETWORK_CONNECTOR_PENDING) {
        coordinator->stage = stage;
        return (collection_network_coordinator_notice_t){0};
    }
    coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_POLICY_STOP;
    return notice(COLLECTION_NETWORK_EVENT_LTE_FAILED, coordinator->attempt_id, false);
}

static void start_attempt(
    collection_network_coordinator_t *coordinator,
    uint32_t attempt_id)
{
    reset_attempt(coordinator);
    coordinator->attempt_id = attempt_id;
    coordinator->last_started_attempt_id = attempt_id;
    coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_ADMISSION;
    coordinator->ppp_stopped = false;
    coordinator->hangup_required = false;
    coordinator->hangup_confirmed = false;
    coordinator->cleanup_confirmed = false;
}

static collection_network_coordinator_notice_t begin_quiesce(
    collection_network_coordinator_t *coordinator,
    uint64_t now_ms)
{
    collection_network_connector_status_t before;
    get_status(coordinator, &before);
    if (!epoch_matches(coordinator, &before)) {
        return cleanup_failed(coordinator);
    }
    if (!deadline_after(
            now_ms,
            coordinator->config.cleanup_timeout_ms,
            &coordinator->cleanup_deadline_ms)) {
        return cleanup_failed(coordinator);
    }
    collection_network_connector_result_t cancelled =
        coordinator->connector.cancel_poll(
            coordinator->connector.context,
            coordinator->connection_epoch);
    if (cancelled == COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH) {
        return cleanup_failed(coordinator);
    }
    coordinator->command_in_flight =
        cancelled == COLLECTION_NETWORK_CONNECTOR_PENDING;
    coordinator->setup_cancel_requested = true;
    collection_network_connector_result_t quiesced =
        coordinator->connector.quiesce(
            coordinator->connector.context,
            coordinator->connection_epoch);
    if (quiesced != COLLECTION_NETWORK_CONNECTOR_OK) {
        return quiesced == COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH
            ? cleanup_failed(coordinator)
            : cleanup_failed_observed(coordinator, &before);
    }
    coordinator->guard_start_ms = now_ms;

    collection_network_connector_status_t status;
    get_status(coordinator, &status);
    if (!epoch_matches(coordinator, &status)) {
        return cleanup_failed(coordinator);
    }
    if (coordinator->command_submitted && !coordinator->dial_submitted &&
        status.ppp_stopped && !status.data_mode) {
        return cleanup_failed(coordinator);
    }
    bool needs_hangup = coordinator->dial_submitted ||
        coordinator->data_mode_entered || status.data_mode || !status.ppp_stopped;
    coordinator->hangup_required = needs_hangup;
    if (!needs_hangup && status.ppp_stopped) {
        return cleanup_succeeded(coordinator);
    }
    coordinator->stage = COLLECTION_NETWORK_COORDINATOR_GUARD;
    return (collection_network_coordinator_notice_t){0};
}

static collection_network_coordinator_notice_t stop_attempt(
    collection_network_coordinator_t *coordinator,
    uint32_t attempt_id,
    uint32_t retire_generation,
    uint64_t now_ms)
{
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_DISABLED) {
        return (collection_network_coordinator_notice_t){0};
    }
    bool has_active_attempt =
        coordinator->stage != COLLECTION_NETWORK_COORDINATOR_IDLE &&
        coordinator->stage != COLLECTION_NETWORK_COORDINATOR_DISABLED;
    if (has_active_attempt && coordinator->attempt_id != attempt_id) {
        /* A conflicting policy snapshot must never retarget teardown onto the
         * current PPP owner. Report failure for the actual active attempt;
         * policy will answer with a matching STOP that follows the ordinary
         * retirement and cleanup path. */
        return notice(
            COLLECTION_NETWORK_EVENT_LTE_FAILED,
            coordinator->attempt_id,
            false);
    }
    if (coordinator->attempt_id == attempt_id &&
        (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER ||
         coordinator->stage == COLLECTION_NETWORK_COORDINATOR_GUARD ||
         coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ESCAPE ||
         coordinator->stage == COLLECTION_NETWORK_COORDINATOR_HANGUP ||
         coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_PPP_DEAD)) {
        /* Exact STOP replay is idempotent: preserve the original retirement
         * and cleanup deadlines and never regress a teardown stage. */
        return (collection_network_coordinator_notice_t){0};
    }
    collection_network_connector_status_t status;
    get_status(coordinator, &status);
    if (coordinator->attempt_id == attempt_id &&
        !coordinator->command_submitted && !coordinator->dial_submitted &&
        !coordinator->data_mode_entered &&
        (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_ADMISSION ||
         coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_POLICY_STOP) &&
        status.ppp_stopped && !status.data_mode) {
        return cleanup_succeeded(coordinator);
    }
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_IDLE ||
        coordinator->attempt_id != attempt_id) {
        if (status.ppp_stopped && !status.data_mode) {
            return notice(COLLECTION_NETWORK_EVENT_LTE_QUIESCED, attempt_id, true);
        }
        coordinator->stage = COLLECTION_NETWORK_COORDINATOR_DISABLED;
        coordinator->cleanup_confirmed = false;
        return (collection_network_coordinator_notice_t){0};
    }
    coordinator->retire_generation = retire_generation;
    if (!deadline_after(
            now_ms,
            coordinator->config.cleanup_timeout_ms,
            &coordinator->retire_deadline_ms)) {
        return cleanup_failed(coordinator);
    }
    coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER;
    return (collection_network_coordinator_notice_t){0};
}

bool collection_network_coordinator_init(
    collection_network_coordinator_t *coordinator,
    const collection_network_coordinator_config_t *config,
    const collection_network_connector_ops_t *connector)
{
    if (!coordinator || !config || !connector || coordinator->initialized ||
        !config->command_timeout_ms ||
        !config->cleanup_timeout_ms || !connector->begin || !connector->poll ||
        !connector->cancel_poll || !connector->quiesce ||
        !connector->get_status) {
        return false;
    }
    memset(coordinator, 0, sizeof(*coordinator));
    coordinator->config = *config;
    coordinator->connector = *connector;
    coordinator->initialized = true;
    coordinator->stage = COLLECTION_NETWORK_COORDINATOR_IDLE;
    return true;
}

collection_network_coordinator_notice_t collection_network_coordinator_apply_policy(
    collection_network_coordinator_t *coordinator,
    const collection_network_policy_snapshot_t *policy,
    const collection_network_retirement_facts_t *retirement,
    uint64_t now_ms)
{
    (void)retirement;
    if (!coordinator || !coordinator->initialized || !policy) {
        return (collection_network_coordinator_notice_t){0};
    }
    if ((policy->actions & COLLECTION_NETWORK_ACTION_START_LTE) &&
        coordinator->stage == COLLECTION_NETWORK_COORDINATOR_IDLE &&
        attempt_is_newer(
            policy->active_lte_attempt_id,
            coordinator->last_started_attempt_id)) {
        start_attempt(coordinator, policy->active_lte_attempt_id);
    }
    if (policy->actions & COLLECTION_NETWORK_ACTION_STOP_LTE) {
        return stop_attempt(
            coordinator,
            policy->active_lte_attempt_id,
            policy->route_generation,
            now_ms);
    }
    return (collection_network_coordinator_notice_t){0};
}

collection_network_coordinator_notice_t collection_network_coordinator_admit(
    collection_network_coordinator_t *coordinator,
    uint32_t attempt_id,
    bool admitted,
    uint64_t now_ms)
{
    if (!coordinator || !coordinator->initialized ||
        coordinator->stage != COLLECTION_NETWORK_COORDINATOR_WAIT_ADMISSION ||
        coordinator->attempt_id != attempt_id) {
        return (collection_network_coordinator_notice_t){0};
    }
    collection_network_connector_status_t status;
    get_status(coordinator, &status);
    if (!admitted || !status.usb_connected) {
        coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_POLICY_STOP;
        return notice(COLLECTION_NETWORK_EVENT_LTE_FAILED, attempt_id, false);
    }
    coordinator->connection_epoch = status.connection_epoch;
    return start_command(
        coordinator,
        COLLECTION_NETWORK_CONNECTOR_PROBE,
        COLLECTION_NETWORK_COORDINATOR_PROBE,
        now_ms);
}

collection_network_coordinator_notice_t collection_network_coordinator_poll(
    collection_network_coordinator_t *coordinator,
    const collection_network_retirement_facts_t *retirement,
    uint64_t now_ms)
{
    if (!coordinator || !coordinator->initialized) {
        return (collection_network_coordinator_notice_t){0};
    }
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_IDLE ||
        coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_ADMISSION ||
        coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_POLICY_STOP ||
        coordinator->stage == COLLECTION_NETWORK_COORDINATOR_DISABLED) {
        return (collection_network_coordinator_notice_t){0};
    }

    collection_network_connector_status_t status;
    get_status(coordinator, &status);
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER) {
        if (retirement && collection_network_retirement_ready(
                &coordinator->retire_generation,
                retirement->published_generation,
                retirement->uploader_active_generation,
                retirement->uploader_retired_generation)) {
            return begin_quiesce(coordinator, now_ms);
        }
        if (now_ms >= coordinator->retire_deadline_ms) {
            coordinator->retire_wait_expired = true;
            coordinator->cleanup_confirmed = false;
            if (coordinator->command_in_flight) {
                if (!coordinator->setup_cancel_requested) {
                    coordinator->setup_cancel_requested = true;
                }
                collection_network_connector_result_t cancelled =
                    coordinator->connector.cancel_poll(
                        coordinator->connector.context,
                        coordinator->connection_epoch);
                if (cancelled == COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH) {
                    return cleanup_failed(coordinator);
                }
                coordinator->command_in_flight =
                    cancelled == COLLECTION_NETWORK_CONNECTOR_PENDING;
            }
            /* Retirement did not complete inside its fixed budget. Do not
             * quiesce an active uploader/netif and do not imply cleanup. This
             * is a terminal boot-local failure; unresolved ownership keeps
             * UART work blocked. */
            return cleanup_failed_observed(coordinator, &status);
        }
        return (collection_network_coordinator_notice_t){0};
    }

    if (!epoch_matches(coordinator, &status)) {
        if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_GUARD ||
            coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ESCAPE ||
            coordinator->stage == COLLECTION_NETWORK_COORDINATOR_HANGUP ||
            coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_PPP_DEAD) {
            return cleanup_failed(coordinator);
        }
        coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_POLICY_STOP;
        return notice(COLLECTION_NETWORK_EVENT_LTE_FAILED, coordinator->attempt_id, false);
    }

    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_IP ||
        coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ONLINE) {
        if (status.ppp_has_ip) {
            if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_IP) {
                coordinator->stage = COLLECTION_NETWORK_COORDINATOR_ONLINE;
                return notice(COLLECTION_NETWORK_EVENT_LTE_READY, coordinator->attempt_id, false);
            }
            return (collection_network_coordinator_notice_t){0};
        }
        if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ONLINE ||
            status.result == COLLECTION_NETWORK_CONNECTOR_DISCONNECTED) {
            coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_POLICY_STOP;
            return notice(COLLECTION_NETWORK_EVENT_LTE_FAILED, coordinator->attempt_id, false);
        }
        return (collection_network_coordinator_notice_t){0};
    }

    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_GUARD) {
        if (now_ms >= coordinator->cleanup_deadline_ms) {
            return cleanup_failed(coordinator);
        }
        if (now_ms < coordinator->guard_start_ms ||
            now_ms - coordinator->guard_start_ms < 1000U) {
            return (collection_network_coordinator_notice_t){0};
        }
        collection_network_connector_result_t result = coordinator->connector.begin(
            coordinator->connector.context,
            COLLECTION_NETWORK_CONNECTOR_ESCAPE,
            coordinator->config.command_timeout_ms,
            coordinator->connection_epoch);
        coordinator->last_submit_ms = now_ms;
        coordinator->command_in_flight =
            result == COLLECTION_NETWORK_CONNECTOR_PENDING;
        coordinator->setup_cancel_requested = false;
        if (result != COLLECTION_NETWORK_CONNECTOR_PENDING) {
            return cleanup_failed(coordinator);
        }
        coordinator->stage = COLLECTION_NETWORK_COORDINATOR_ESCAPE;
        return (collection_network_coordinator_notice_t){0};
    }

    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_WAIT_PPP_DEAD) {
        if (status.ppp_stopped && status.hangup_confirmed) {
            return cleanup_succeeded(coordinator);
        }
        if (now_ms >= coordinator->cleanup_deadline_ms) {
            return cleanup_failed(coordinator);
        }
        return (collection_network_coordinator_notice_t){0};
    }

    if ((coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ESCAPE ||
         coordinator->stage == COLLECTION_NETWORK_COORDINATOR_HANGUP) &&
        now_ms >= coordinator->cleanup_deadline_ms) {
        coordinator->setup_cancel_requested = true;
        collection_network_connector_result_t cancelled =
            coordinator->connector.cancel_poll(
                coordinator->connector.context,
                coordinator->connection_epoch);
        if (cancelled == COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH) {
            return cleanup_failed(coordinator);
        }
        coordinator->command_in_flight =
            cancelled == COLLECTION_NETWORK_CONNECTOR_PENDING;
        return cleanup_failed(coordinator);
    }

    collection_network_connector_result_t result = coordinator->connector.poll(
        coordinator->connector.context, coordinator->connection_epoch);
    if (result == COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH) {
        if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ESCAPE ||
            coordinator->stage == COLLECTION_NETWORK_COORDINATOR_HANGUP) {
            return cleanup_failed(coordinator);
        }
        coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_POLICY_STOP;
        return notice(
            COLLECTION_NETWORK_EVENT_LTE_FAILED,
            coordinator->attempt_id,
            false);
    }
    if (result == COLLECTION_NETWORK_CONNECTOR_PENDING) {
        return (collection_network_coordinator_notice_t){0};
    }
    coordinator->command_in_flight = false;
    if (result != COLLECTION_NETWORK_CONNECTOR_OK) {
        if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ESCAPE ||
            coordinator->stage == COLLECTION_NETWORK_COORDINATOR_HANGUP) {
            return cleanup_failed(coordinator);
        }
        coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_POLICY_STOP;
        return notice(COLLECTION_NETWORK_EVENT_LTE_FAILED, coordinator->attempt_id, false);
    }
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_PROBE) {
        return start_command(
            coordinator,
            COLLECTION_NETWORK_CONNECTOR_ECHO_OFF,
            COLLECTION_NETWORK_COORDINATOR_ECHO_OFF,
            now_ms);
    }
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ECHO_OFF) {
        return start_command(
            coordinator,
            COLLECTION_NETWORK_CONNECTOR_DIAL,
            COLLECTION_NETWORK_COORDINATOR_DIAL,
            now_ms);
    }
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_DIAL) {
        coordinator->data_mode_entered = true;
        coordinator->hangup_required = true;
        coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_IP;
        return (collection_network_coordinator_notice_t){0};
    }
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ESCAPE) {
        collection_network_connector_result_t started = coordinator->connector.begin(
            coordinator->connector.context,
            COLLECTION_NETWORK_CONNECTOR_HANGUP,
            coordinator->config.command_timeout_ms,
            coordinator->connection_epoch);
        coordinator->last_submit_ms = now_ms;
        coordinator->command_in_flight =
            started == COLLECTION_NETWORK_CONNECTOR_PENDING;
        coordinator->setup_cancel_requested = false;
        if (started != COLLECTION_NETWORK_CONNECTOR_PENDING) {
            return cleanup_failed(coordinator);
        }
        coordinator->stage = COLLECTION_NETWORK_COORDINATOR_HANGUP;
        return (collection_network_coordinator_notice_t){0};
    }
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_HANGUP) {
        coordinator->stage = COLLECTION_NETWORK_COORDINATOR_WAIT_PPP_DEAD;
    }
    return (collection_network_coordinator_notice_t){0};
}

collection_network_coordinator_notice_t
collection_network_coordinator_cancel_setup(
    collection_network_coordinator_t *coordinator)
{
    if (!coordinator || !coordinator->initialized) {
        return (collection_network_coordinator_notice_t){0};
    }
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_PROBE ||
        coordinator->stage == COLLECTION_NETWORK_COORDINATOR_ECHO_OFF ||
        coordinator->stage == COLLECTION_NETWORK_COORDINATOR_DIAL) {
        if (coordinator->command_in_flight) {
            if (!coordinator->setup_cancel_requested) {
                coordinator->setup_cancel_requested = true;
            }
            collection_network_connector_result_t cancelled =
                coordinator->connector.cancel_poll(
                    coordinator->connector.context,
                    coordinator->connection_epoch);
            if (cancelled == COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH) {
                return cleanup_failed(coordinator);
            }
            coordinator->command_in_flight =
                cancelled == COLLECTION_NETWORK_CONNECTOR_PENDING;
        }
    }
    return (collection_network_coordinator_notice_t){0};
}

void collection_network_coordinator_refresh_status(
    collection_network_coordinator_t *coordinator)
{
    if (!coordinator || !coordinator->initialized) {
        return;
    }
    collection_network_connector_status_t status;
    get_status(coordinator, &status);
    coordinator->ppp_stopped = status.ppp_stopped;
    coordinator->hangup_confirmed = status.hangup_confirmed;
    if (coordinator->stage == COLLECTION_NETWORK_COORDINATOR_IDLE &&
        coordinator->attempt_id == 0) {
        /* This is observed idle state, not an inferred teardown result. */
        coordinator->cleanup_confirmed = status.ppp_stopped && !status.data_mode;
    }
}

bool collection_network_coordinator_blocks_uart_work(
    const collection_network_coordinator_t *coordinator)
{
    if (!coordinator || !coordinator->initialized) {
        return false;
    }
    collection_network_coordinator_stage_t stage = coordinator->stage;
    return coordinator->command_in_flight ||
        (stage == COLLECTION_NETWORK_COORDINATOR_DISABLED &&
         !coordinator->cleanup_confirmed) ||
        stage == COLLECTION_NETWORK_COORDINATOR_PROBE ||
        stage == COLLECTION_NETWORK_COORDINATOR_ECHO_OFF ||
        stage == COLLECTION_NETWORK_COORDINATOR_DIAL ||
        (stage == COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER &&
         !coordinator->retire_wait_expired) ||
        stage == COLLECTION_NETWORK_COORDINATOR_GUARD ||
        stage == COLLECTION_NETWORK_COORDINATOR_ESCAPE ||
        stage == COLLECTION_NETWORK_COORDINATOR_HANGUP ||
        stage == COLLECTION_NETWORK_COORDINATOR_WAIT_PPP_DEAD;
}

collection_network_coordinator_snapshot_t collection_network_coordinator_snapshot(
    const collection_network_coordinator_t *coordinator)
{
    if (!coordinator || !coordinator->initialized) {
        return (collection_network_coordinator_snapshot_t){0};
    }
    return (collection_network_coordinator_snapshot_t){
        .stage = coordinator->stage,
        .attempt_id = coordinator->attempt_id,
        .last_started_attempt_id = coordinator->last_started_attempt_id,
        .connection_epoch = coordinator->connection_epoch,
        .retire_generation = coordinator->retire_generation,
        .retire_deadline_ms = coordinator->retire_deadline_ms,
        .command_submitted = coordinator->command_submitted,
        .command_in_flight = coordinator->command_in_flight,
        .setup_cancel_requested = coordinator->setup_cancel_requested,
        .dial_submitted = coordinator->dial_submitted,
        .data_mode_entered = coordinator->data_mode_entered,
        .retire_wait_expired = coordinator->retire_wait_expired,
        .blocks_uart_work = collection_network_coordinator_blocks_uart_work(coordinator),
        .ppp_stopped = coordinator->ppp_stopped,
        .hangup_required = coordinator->hangup_required,
        .hangup_confirmed = coordinator->hangup_confirmed,
        .cleanup_confirmed = coordinator->cleanup_confirmed,
    };
}

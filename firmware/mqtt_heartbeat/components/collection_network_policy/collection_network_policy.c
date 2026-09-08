#include "collection_network_policy.h"

#include <limits.h>
#include <string.h>

static uint64_t add_ms(uint64_t now, uint32_t duration)
{
    return now > UINT64_MAX - duration ? UINT64_MAX : now + duration;
}

static uint32_t next_nonzero(uint32_t value)
{
    ++value;
    return value == 0U ? 1U : value;
}

static void select_route(
    collection_network_policy_t *policy, collection_network_route_t route)
{
    if (policy->route == route) return;
    policy->route = route;
    policy->route_generation = next_nonzero(policy->route_generation);
}

static void reset_backoff(collection_network_policy_t *policy)
{
    policy->retry_backoff_ms = policy->config.retry_initial_ms;
    policy->retry_at_ms = 0U;
}

static void schedule_retry(collection_network_policy_t *policy, uint64_t now)
{
    policy->retry_at_ms = add_ms(now, policy->retry_backoff_ms);
    if (policy->retry_backoff_ms < policy->config.retry_max_ms) {
        uint64_t doubled = (uint64_t)policy->retry_backoff_ms * 2U;
        policy->retry_backoff_ms = doubled > policy->config.retry_max_ms ?
            policy->config.retry_max_ms : (uint32_t)doubled;
    }
}

static uint32_t request_lte_stop(collection_network_policy_t *policy)
{
    if (!policy->lte_active || policy->lte_stop_sent) return 0U;
    policy->lte_stop_sent = true;
    return COLLECTION_NETWORK_ACTION_STOP_LTE;
}

static uint32_t maybe_start_lte(collection_network_policy_t *policy, uint64_t now)
{
    if (!policy->config.lte_enabled || policy->wifi_ready || policy->lte_active ||
        policy->stopping || now < policy->retry_at_ms) {
        policy->state = policy->wifi_ready ? COLLECTION_NETWORK_WIFI_READY :
            COLLECTION_NETWORK_NO_ROUTE;
        return 0U;
    }
    policy->next_lte_attempt_id = next_nonzero(policy->next_lte_attempt_id);
    policy->active_lte_attempt_id = policy->next_lte_attempt_id;
    policy->lte_active = true;
    policy->lte_stop_sent = false;
    policy->attempt_deadline_ms = add_ms(now, policy->config.lte_attempt_timeout_ms);
    policy->state = COLLECTION_NETWORK_LTE_DIALING;
    return COLLECTION_NETWORK_ACTION_START_LTE;
}

static collection_network_policy_snapshot_t result(
    const collection_network_policy_t *policy, uint32_t actions)
{
    collection_network_policy_snapshot_t snapshot = {
        .state = policy->state,
        .route = policy->route,
        .route_generation = policy->route_generation,
        .active_lte_attempt_id = policy->active_lte_attempt_id,
        .actions = actions,
        .attempt_deadline_ms = policy->attempt_deadline_ms,
        .retry_at_ms = policy->retry_at_ms,
    };
    return snapshot;
}

bool collection_network_policy_init(
    collection_network_policy_t *policy,
    const collection_network_policy_config_t *config)
{
    if (!policy || !config || !config->lte_attempt_timeout_ms ||
        !config->retry_initial_ms || !config->retry_max_ms ||
        config->retry_initial_ms > config->retry_max_ms) return false;
    memset(policy, 0, sizeof(*policy));
    policy->config = *config;
    policy->state = COLLECTION_NETWORK_NO_ROUTE;
    policy->route = COLLECTION_NETWORK_ROUTE_NONE;
    policy->route_generation = 1U;
    reset_backoff(policy);
    return true;
}

collection_network_policy_snapshot_t collection_network_policy_handle(
    collection_network_policy_t *policy,
    const collection_network_policy_event_t *event)
{
    uint32_t actions = 0U;
    if (!policy || !event) return (collection_network_policy_snapshot_t){0};
    if (policy->state == COLLECTION_NETWORK_STOPPED) return result(policy, 0U);

    switch (event->type) {
    case COLLECTION_NETWORK_EVENT_WIFI_READY:
        policy->wifi_ready = true;
        /* Do not let a transient Wi-Fi edge erase the retry delay from an LTE
         * failure that is still being retired.  A usable Wi-Fi route resets
         * it once no LTE attempt remains. */
        if (!policy->lte_active) reset_backoff(policy);
        if (policy->lte_active) {
            /* Retire the LTE generation before publishing another usable
             * route.  This prevents a new Wi-Fi POST from keeping the LTE
             * netif teardown handshake perpetually busy. */
            select_route(policy, COLLECTION_NETWORK_ROUTE_NONE);
            policy->state = COLLECTION_NETWORK_SWITCHING;
            actions |= request_lte_stop(policy);
        } else {
            select_route(policy, COLLECTION_NETWORK_ROUTE_WIFI);
            policy->state = COLLECTION_NETWORK_WIFI_READY;
        }
        break;
    case COLLECTION_NETWORK_EVENT_WIFI_LOST:
        policy->wifi_ready = false;
        if (policy->route == COLLECTION_NETWORK_ROUTE_WIFI)
            select_route(policy, COLLECTION_NETWORK_ROUTE_NONE);
        if (policy->lte_active) {
            policy->state = policy->lte_stop_sent ? COLLECTION_NETWORK_SWITCHING :
                COLLECTION_NETWORK_LTE_DIALING;
        } else {
            actions |= maybe_start_lte(policy, event->now_ms);
        }
        break;
    case COLLECTION_NETWORK_EVENT_LTE_READY:
        if (!policy->lte_active ||
            event->lte_attempt_id != policy->active_lte_attempt_id) break;
        reset_backoff(policy);
        if (policy->wifi_ready || policy->stopping) {
            select_route(policy, COLLECTION_NETWORK_ROUTE_NONE);
            policy->state = policy->stopping ? COLLECTION_NETWORK_STOPPING :
                COLLECTION_NETWORK_SWITCHING;
            actions |= request_lte_stop(policy);
        } else {
            select_route(policy, COLLECTION_NETWORK_ROUTE_LTE);
            policy->state = COLLECTION_NETWORK_LTE_READY;
        }
        break;
    case COLLECTION_NETWORK_EVENT_LTE_FAILED:
        if (!policy->lte_active ||
            event->lte_attempt_id != policy->active_lte_attempt_id) break;
        if (policy->route == COLLECTION_NETWORK_ROUTE_LTE)
            select_route(policy, COLLECTION_NETWORK_ROUTE_NONE);
        schedule_retry(policy, event->now_ms);
        policy->state = policy->stopping ? COLLECTION_NETWORK_STOPPING :
            COLLECTION_NETWORK_SWITCHING;
        actions |= request_lte_stop(policy);
        break;
    case COLLECTION_NETWORK_EVENT_LTE_QUIESCED:
        if (!policy->lte_active ||
            event->lte_attempt_id != policy->active_lte_attempt_id) break;
        policy->lte_active = false;
        policy->lte_stop_sent = false;
        policy->active_lte_attempt_id = 0U;
        policy->attempt_deadline_ms = 0U;
        if (policy->stopping) {
            policy->state = COLLECTION_NETWORK_STOPPED;
        } else if (policy->wifi_ready) {
            reset_backoff(policy);
            select_route(policy, COLLECTION_NETWORK_ROUTE_WIFI);
            policy->state = COLLECTION_NETWORK_WIFI_READY;
        } else {
            select_route(policy, COLLECTION_NETWORK_ROUTE_NONE);
            actions |= maybe_start_lte(policy, event->now_ms);
        }
        break;
    case COLLECTION_NETWORK_EVENT_LTE_DISABLED:
        if (!policy->lte_active ||
            event->lte_attempt_id != policy->active_lte_attempt_id) break;
        select_route(policy, COLLECTION_NETWORK_ROUTE_NONE);
        policy->config.lte_enabled = false;
        policy->lte_active = false;
        policy->lte_stop_sent = false;
        policy->active_lte_attempt_id = 0U;
        policy->attempt_deadline_ms = 0U;
        policy->stop_blocked = true;
        if (policy->stopping) {
            policy->state = COLLECTION_NETWORK_STOPPING;
        } else if (policy->wifi_ready) {
            select_route(policy, COLLECTION_NETWORK_ROUTE_WIFI);
            policy->state = COLLECTION_NETWORK_WIFI_READY;
        } else {
            policy->state = COLLECTION_NETWORK_NO_ROUTE;
        }
        break;
    case COLLECTION_NETWORK_EVENT_STOP:
        policy->stopping = true;
        select_route(policy, COLLECTION_NETWORK_ROUTE_NONE);
        if (policy->stop_blocked) {
            policy->state = COLLECTION_NETWORK_STOPPING;
        } else if (policy->lte_active) {
            policy->state = COLLECTION_NETWORK_STOPPING;
            actions |= request_lte_stop(policy);
        } else {
            policy->state = COLLECTION_NETWORK_STOPPED;
        }
        break;
    case COLLECTION_NETWORK_EVENT_TICK:
        if (policy->stopping) {
            if (policy->stop_blocked) policy->state = COLLECTION_NETWORK_STOPPING;
            else if (!policy->lte_active) policy->state = COLLECTION_NETWORK_STOPPED;
            else actions |= request_lte_stop(policy);
        } else if (policy->lte_active && !policy->lte_stop_sent &&
                   policy->state == COLLECTION_NETWORK_LTE_DIALING &&
                   event->now_ms >= policy->attempt_deadline_ms) {
            schedule_retry(policy, event->now_ms);
            policy->state = COLLECTION_NETWORK_SWITCHING;
            actions |= request_lte_stop(policy);
        } else if (!policy->lte_active && !policy->wifi_ready) {
            actions |= maybe_start_lte(policy, event->now_ms);
        }
        break;
    default:
        break;
    }
    return result(policy, actions);
}

collection_network_policy_snapshot_t collection_network_policy_snapshot(
    const collection_network_policy_t *policy)
{
    return policy ? result(policy, 0U) : (collection_network_policy_snapshot_t){0};
}

bool collection_network_retirement_ready(
    uint32_t *target_generation,
    uint32_t published_generation,
    uint32_t uploader_active_generation,
    uint32_t uploader_retired_generation)
{
    if (!target_generation || published_generation == 0U) return false;
    *target_generation = published_generation;
    return uploader_active_generation == 0U &&
        uploader_retired_generation == published_generation;
}

const char *collection_network_state_name(collection_network_state_t state)
{
    static const char *const names[] = {
        "NO_ROUTE", "WIFI_READY", "LTE_DIALING", "LTE_READY", "SWITCHING",
        "STOPPING", "STOPPED",
    };
    return (unsigned)state < sizeof(names) / sizeof(names[0]) ? names[state] : "INVALID";
}

const char *collection_network_route_name(collection_network_route_t route)
{
    static const char *const names[] = {"offline", "wifi", "lte"};
    return (unsigned)route < sizeof(names) / sizeof(names[0]) ? names[route] : "invalid";
}

#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    COLLECTION_NETWORK_NO_ROUTE = 0,
    COLLECTION_NETWORK_WIFI_READY,
    COLLECTION_NETWORK_LTE_DIALING,
    COLLECTION_NETWORK_LTE_READY,
    COLLECTION_NETWORK_SWITCHING,
    COLLECTION_NETWORK_STOPPING,
    COLLECTION_NETWORK_STOPPED,
} collection_network_state_t;

typedef enum {
    COLLECTION_NETWORK_ROUTE_NONE = 0,
    COLLECTION_NETWORK_ROUTE_WIFI,
    COLLECTION_NETWORK_ROUTE_LTE,
} collection_network_route_t;

typedef enum {
    COLLECTION_NETWORK_EVENT_TICK = 0,
    COLLECTION_NETWORK_EVENT_WIFI_READY,
    COLLECTION_NETWORK_EVENT_WIFI_LOST,
    COLLECTION_NETWORK_EVENT_LTE_READY,
    COLLECTION_NETWORK_EVENT_LTE_FAILED,
    COLLECTION_NETWORK_EVENT_LTE_QUIESCED,
    COLLECTION_NETWORK_EVENT_LTE_DISABLED,
    COLLECTION_NETWORK_EVENT_STOP,
} collection_network_event_type_t;

enum {
    COLLECTION_NETWORK_ACTION_NONE = 0,
    COLLECTION_NETWORK_ACTION_START_LTE = 1U << 0,
    COLLECTION_NETWORK_ACTION_STOP_LTE = 1U << 1,
};

typedef struct {
    bool lte_enabled;
    uint32_t lte_attempt_timeout_ms;
    uint32_t retry_initial_ms;
    uint32_t retry_max_ms;
} collection_network_policy_config_t;

typedef struct {
    collection_network_event_type_t type;
    uint64_t now_ms;
    /* LTE events are accepted only for the currently active attempt. */
    uint32_t lte_attempt_id;
} collection_network_policy_event_t;

typedef struct {
    collection_network_state_t state;
    collection_network_route_t route;
    uint32_t route_generation;
    uint32_t active_lte_attempt_id;
    uint32_t actions;
    uint64_t attempt_deadline_ms;
    uint64_t retry_at_ms;
} collection_network_policy_snapshot_t;

typedef struct {
    collection_network_policy_config_t config;
    collection_network_state_t state;
    collection_network_route_t route;
    uint32_t route_generation;
    uint32_t next_lte_attempt_id;
    uint32_t active_lte_attempt_id;
    uint32_t retry_backoff_ms;
    uint64_t attempt_deadline_ms;
    uint64_t retry_at_ms;
    bool wifi_ready;
    bool lte_active;
    bool lte_stop_sent;
    bool stopping;
    bool stop_blocked;
} collection_network_policy_t;

bool collection_network_policy_init(
    collection_network_policy_t *policy,
    const collection_network_policy_config_t *config);

collection_network_policy_snapshot_t collection_network_policy_handle(
    collection_network_policy_t *policy,
    const collection_network_policy_event_t *event);

collection_network_policy_snapshot_t collection_network_policy_snapshot(
    const collection_network_policy_t *policy);

/* Advance an in-progress netif retirement to the latest published route
 * generation.  The caller owns the original deadline; this helper never
 * extends it. */
bool collection_network_retirement_ready(
    uint32_t *target_generation,
    uint32_t published_generation,
    uint32_t uploader_active_generation,
    uint32_t uploader_retired_generation);

const char *collection_network_state_name(collection_network_state_t state);
const char *collection_network_route_name(collection_network_route_t route);

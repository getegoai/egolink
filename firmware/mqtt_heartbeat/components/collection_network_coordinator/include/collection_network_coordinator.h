#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "collection_network_policy.h"

/* Fixed-memory coordinator only. It owns no task, UART, USB object, netif,
 * route publication, HTTP connection, spool record or ACK decision. The one
 * modem owner supplies connector operations and serializes every call. */
typedef enum {
    COLLECTION_NETWORK_COORDINATOR_IDLE = 0,
    COLLECTION_NETWORK_COORDINATOR_WAIT_ADMISSION,
    COLLECTION_NETWORK_COORDINATOR_PROBE,
    COLLECTION_NETWORK_COORDINATOR_ECHO_OFF,
    COLLECTION_NETWORK_COORDINATOR_DIAL,
    COLLECTION_NETWORK_COORDINATOR_WAIT_IP,
    COLLECTION_NETWORK_COORDINATOR_ONLINE,
    COLLECTION_NETWORK_COORDINATOR_WAIT_POLICY_STOP,
    COLLECTION_NETWORK_COORDINATOR_WAIT_UPLOADER,
    COLLECTION_NETWORK_COORDINATOR_GUARD,
    COLLECTION_NETWORK_COORDINATOR_ESCAPE,
    COLLECTION_NETWORK_COORDINATOR_HANGUP,
    COLLECTION_NETWORK_COORDINATOR_WAIT_PPP_DEAD,
    COLLECTION_NETWORK_COORDINATOR_DISABLED,
} collection_network_coordinator_stage_t;

typedef enum {
    COLLECTION_NETWORK_CONNECTOR_PROBE = 0,
    COLLECTION_NETWORK_CONNECTOR_ECHO_OFF,
    COLLECTION_NETWORK_CONNECTOR_DIAL,
    COLLECTION_NETWORK_CONNECTOR_ESCAPE,
    COLLECTION_NETWORK_CONNECTOR_HANGUP,
} collection_network_connector_operation_t;

typedef enum {
    COLLECTION_NETWORK_CONNECTOR_PENDING = 0,
    COLLECTION_NETWORK_CONNECTOR_OK,
    COLLECTION_NETWORK_CONNECTOR_DISCONNECTED,
    COLLECTION_NETWORK_CONNECTOR_FAILED,
    COLLECTION_NETWORK_CONNECTOR_TIMEOUT,
    COLLECTION_NETWORK_CONNECTOR_IO_ERROR,
    COLLECTION_NETWORK_CONNECTOR_OVERFLOW,
    COLLECTION_NETWORK_CONNECTOR_STALE_EPOCH,
} collection_network_connector_result_t;

typedef struct {
    bool usb_connected;
    bool data_mode;
    bool ppp_has_ip;
    bool ppp_stopped;
    bool hangup_confirmed;
    uint32_t connection_epoch;
    collection_network_connector_result_t result;
} collection_network_connector_status_t;

typedef struct {
    collection_network_connector_result_t (*begin)(
        void *context,
        collection_network_connector_operation_t operation,
        uint32_t timeout_ms,
        uint32_t expected_epoch);
    collection_network_connector_result_t (*poll)(
        void *context, uint32_t expected_epoch);
    collection_network_connector_result_t (*cancel_poll)(
        void *context, uint32_t expected_epoch);
    collection_network_connector_result_t (*quiesce)(
        void *context, uint32_t expected_epoch);
    void (*get_status)(void *context, collection_network_connector_status_t *status);
    void *context;
} collection_network_connector_ops_t;

typedef struct {
    uint32_t command_timeout_ms;
    uint32_t cleanup_timeout_ms;
} collection_network_coordinator_config_t;

typedef struct {
    uint32_t published_generation;
    uint32_t uploader_active_generation;
    uint32_t uploader_retired_generation;
} collection_network_retirement_facts_t;

typedef struct {
    bool valid;
    bool cleanup_confirmed;
    collection_network_event_type_t type;
    uint32_t attempt_id;
} collection_network_coordinator_notice_t;

typedef struct {
    collection_network_coordinator_stage_t stage;
    uint32_t attempt_id;
    uint32_t last_started_attempt_id;
    uint32_t connection_epoch;
    uint32_t retire_generation;
    uint64_t retire_deadline_ms;
    bool command_submitted;
    bool command_in_flight;
    bool setup_cancel_requested;
    bool dial_submitted;
    bool data_mode_entered;
    bool retire_wait_expired;
    bool blocks_uart_work;
    bool ppp_stopped;
    bool hangup_required;
    bool hangup_confirmed;
    bool cleanup_confirmed;
} collection_network_coordinator_snapshot_t;

typedef struct {
    collection_network_coordinator_config_t config;
    collection_network_connector_ops_t connector;
    bool initialized;
    collection_network_coordinator_stage_t stage;
    uint32_t attempt_id;
    uint32_t last_started_attempt_id;
    uint32_t connection_epoch;
    uint32_t retire_generation;
    uint64_t last_submit_ms;
    uint64_t retire_deadline_ms;
    uint64_t guard_start_ms;
    uint64_t cleanup_deadline_ms;
    bool command_submitted;
    bool command_in_flight;
    bool setup_cancel_requested;
    bool dial_submitted;
    bool data_mode_entered;
    bool retire_wait_expired;
    bool ppp_stopped;
    bool hangup_required;
    bool hangup_confirmed;
    bool cleanup_confirmed;
} collection_network_coordinator_t;

/* Storage must be zero-initialized. Re-initialization is rejected so an active
 * owner cannot silently discard an uncertain modem lifecycle. */
bool collection_network_coordinator_init(
    collection_network_coordinator_t *coordinator,
    const collection_network_coordinator_config_t *config,
    const collection_network_connector_ops_t *connector);

collection_network_coordinator_notice_t collection_network_coordinator_apply_policy(
    collection_network_coordinator_t *coordinator,
    const collection_network_policy_snapshot_t *policy,
    const collection_network_retirement_facts_t *retirement,
    uint64_t now_ms);

collection_network_coordinator_notice_t collection_network_coordinator_admit(
    collection_network_coordinator_t *coordinator,
    uint32_t attempt_id,
    bool admitted,
    uint64_t now_ms);

collection_network_coordinator_notice_t collection_network_coordinator_poll(
    collection_network_coordinator_t *coordinator,
    const collection_network_retirement_facts_t *retirement,
    uint64_t now_ms);

/* During the existing bounded uploader-first shutdown wait, cancel only a
 * setup command that is already in flight and still belongs to the captured
 * connection epoch. An epoch mismatch returns an LTE_DISABLED notice without
 * touching the new connector lifecycle. */
collection_network_coordinator_notice_t
collection_network_coordinator_cancel_setup(
    collection_network_coordinator_t *coordinator);

/* Refresh physical PPP/hangup facts without advancing policy state. */
void collection_network_coordinator_refresh_status(
    collection_network_coordinator_t *coordinator);

bool collection_network_coordinator_blocks_uart_work(
    const collection_network_coordinator_t *coordinator);

collection_network_coordinator_snapshot_t collection_network_coordinator_snapshot(
    const collection_network_coordinator_t *coordinator);

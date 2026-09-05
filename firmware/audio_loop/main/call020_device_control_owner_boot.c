/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Dedicated CALL-020R boot entry. Building it is not permission to flash or
 * run it; the profile is kept separate from every ordinary/default image.
 */

#include "call020_device_control_owner.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#if !defined(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER) || \
    !CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER
#error "CALL-020R boot entry requires its dedicated owner profile"
#endif

static const call020_device_control_owner_config_t s_boot_config = {
    .enabled = true,
    .control_total_timeout_us =
        (uint64_t)CONFIG_EGOLINK_CALL020_DEVICE_OWNER_CONTROL_TIMEOUT_MS *
        UINT64_C(1000),
    .poll_slice_ms = CONFIG_EGOLINK_CALL020_DEVICE_OWNER_POLL_MS,
    .media_quiesce_grace_us =
        (uint64_t)CONFIG_EGOLINK_CALL020_DEVICE_OWNER_QUIESCE_GRACE_MS *
        UINT64_C(1000),
    .responder = {
        .enabled = true,
        .frame_wait_timeout_ms =
            CONFIG_EGOLINK_CALL020_DEVICE_OWNER_FRAME_WAIT_MS,
        .io_wait_slice_ms = 20,
        .max_io_calls = 64,
        .max_operation_timeout_ms = 10000,
        .result_phase_enabled = false,
        .runner = {
            .handoff_queue_frames = 4,
            .frame_deadline_slack_us = UINT64_C(100000),
            .downlink_playout_delay_us = UINT64_C(60000),
            .max_runtime_us =
                (uint64_t)CONFIG_EGOLINK_CALL020_DEVICE_OWNER_MEDIA_SECONDS *
                UINT64_C(1000000),
            .audio_io_timeout_us = UINT64_C(100000),
            .usb_read_poll_us = UINT64_C(20000),
            .join_timeout_us = UINT64_C(5000000),
            .usb_endpoint = {
                .tx_buffer_bytes = 4096,
                .rx_buffer_bytes = 4096,
                .io_wait_slice_ms = 20,
                .max_operation_us = UINT64_C(1000000),
                .close_timeout_us = UINT64_C(1000000),
            },
        },
    },
};

static void call020_device_owner_task(void *unused)
{
    (void)unused;
    if (call020_device_control_owner_init(&s_boot_config) != ESP_OK) {
        /* Pure initialization acquired no hardware ownership. */
        vTaskDelete(NULL);
        return;
    }
    (void)call020_device_control_owner_run();

    call020_device_control_owner_metadata_t metadata = {0};
    if (call020_device_control_owner_get_metadata(&metadata) == ESP_OK &&
        metadata.state == CALL020_DEVICE_OWNER_CLOSED &&
        metadata.cleanup_complete) {
        vTaskDelete(NULL);
        return;
    }

    /*
     * run() normally performs the active retry loop. If it ever returns
     * without complete cleanup proof, retain the unique owner task forever in
     * a quiet fail-closed park instead of abandoning its lifecycle identity.
     */
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(
            CALL020_DEVICE_CONTROL_OWNER_MAX_RECOVERY_BACKOFF_MS));
    }
}

void app_main(void)
{
    BaseType_t created = xTaskCreatePinnedToCore(
        call020_device_owner_task,
        "call020_owner",
        CONFIG_EGOLINK_CALL020_DEVICE_OWNER_TASK_STACK_BYTES,
        NULL,
        CONFIG_EGOLINK_CALL020_DEVICE_OWNER_TASK_PRIORITY,
        NULL,
        CONFIG_EGOLINK_CALL020_DEVICE_OWNER_TASK_CORE);
    if (created != pdPASS) {
        /* No owner API or hardware boundary has run; fail closed and quiet. */
        return;
    }
}

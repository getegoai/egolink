"""Native unit test suite for SIM7670 cellular voice calling state machine."""

import unittest

from quality_tests.native_convergence import run_c


HARNESS = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "sim7670_cellular_call.h"

static char s_last_cmd[128];
static char s_mock_response[256];
static esp_err_t s_mock_err = ESP_OK;
static int64_t s_mock_time_us = 1000000;

static esp_err_t mock_at_send(
    void *user_ctx,
    const char *cmd,
    char *resp,
    size_t resp_size,
    uint32_t timeout_ms)
{
    (void)user_ctx;
    (void)timeout_ms;
    strncpy(s_last_cmd, cmd, sizeof(s_last_cmd) - 1);
    s_last_cmd[sizeof(s_last_cmd) - 1] = '\0';

    if (resp != NULL && resp_size > 0) {
        strncpy(resp, s_mock_response, resp_size - 1);
        resp[resp_size - 1] = '\0';
    }
    return s_mock_err;
}

static int64_t mock_clock(void)
{
    return s_mock_time_us;
}

static void test_initialization(void)
{
    sim7670_cellular_call_ctx_t ctx;
    sim7670_cellular_call_config_t config = {
        .at_send = mock_at_send,
        .user_ctx = NULL,
        .clock_fn = mock_clock,
    };

    /* Invalid arguments */
    assert(sim7670_cellular_call_init(NULL, &config) == ESP_ERR_INVALID_ARG);
    assert(sim7670_cellular_call_init(&ctx, NULL) == ESP_ERR_INVALID_ARG);

    sim7670_cellular_call_config_t bad_config = config;
    bad_config.at_send = NULL;
    assert(sim7670_cellular_call_init(&ctx, &bad_config) == ESP_ERR_INVALID_ARG);

    /* Valid initialization */
    assert(sim7670_cellular_call_init(&ctx, &config) == ESP_OK);

    sim7670_call_status_t status;
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_IDLE);
    assert(status.direction == SIM7670_CALL_DIR_NONE);
    assert(strcmp(sim7670_call_state_to_str(status.state), "IDLE") == 0);
}

static void test_outgoing_call_flow(void)
{
    sim7670_cellular_call_ctx_t ctx;
    sim7670_cellular_call_config_t config = {
        .at_send = mock_at_send,
        .user_ctx = NULL,
        .clock_fn = mock_clock,
    };
    assert(sim7670_cellular_call_init(&ctx, &config) == ESP_OK);

    /* Invalid phone numbers */
    assert(sim7670_cellular_call_dial(&ctx, NULL) == ESP_ERR_INVALID_ARG);
    assert(sim7670_cellular_call_dial(&ctx, "12") == ESP_ERR_INVALID_ARG); /* too short */
    assert(sim7670_cellular_call_dial(&ctx, "13800abc123") == ESP_ERR_INVALID_ARG); /* non-digit */

    /* Valid dial */
    s_mock_time_us = 10000000;
    assert(sim7670_cellular_call_dial(&ctx, "13800138000") == ESP_OK);
    assert(strcmp(s_last_cmd, "ATD13800138000;") == 0);

    sim7670_call_status_t status;
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_DIALING);
    assert(status.direction == SIM7670_CALL_DIR_OUTGOING);
    assert(strcmp(status.phone_number, "13800138000") == 0);

    /* Cannot dial while active or dialing */
    assert(sim7670_cellular_call_dial(&ctx, "10086") == ESP_ERR_INVALID_STATE);

    /* Poll status -> Alerting (stat = 3) */
    snprintf(s_mock_response, sizeof(s_mock_response), "+CLCC: 1,0,3,0,0,\"13800138000\",129");
    assert(sim7670_cellular_call_poll_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_ALERTING);
    assert(strcmp(sim7670_call_state_to_str(status.state), "ALERTING") == 0);

    /* Poll status -> Active (stat = 0) */
    s_mock_time_us = 15000000; /* Connected at 15s */
    snprintf(s_mock_response, sizeof(s_mock_response), "+CLCC: 1,0,0,0,0,\"13800138000\",129");
    assert(sim7670_cellular_call_poll_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_ACTIVE);
    assert(status.call_connected_time_us == 15000000);

    /* 30 seconds into call */
    s_mock_time_us = 45000000;
    assert(sim7670_cellular_call_poll_status(&ctx, &status) == ESP_OK);
    assert(status.call_duration_sec == 30);

    /* Local hangup */
    assert(sim7670_cellular_call_hangup(&ctx) == ESP_OK);
    assert(strcmp(s_last_cmd, "ATH") == 0);
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_IDLE);
    assert(status.last_disconnect_reason == SIM7670_CALL_DISCONNECT_LOCAL_HANGUP);
    assert(status.call_duration_sec == 30);
}

static void test_incoming_call_flow(void)
{
    sim7670_cellular_call_ctx_t ctx;
    sim7670_cellular_call_config_t config = {
        .at_send = mock_at_send,
        .user_ctx = NULL,
        .clock_fn = mock_clock,
    };
    assert(sim7670_cellular_call_init(&ctx, &config) == ESP_OK);

    /* Incoming RING URC */
    assert(sim7670_cellular_call_handle_urc(&ctx, "RING") == ESP_OK);
    sim7670_call_status_t status;
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_INCOMING);
    assert(status.direction == SIM7670_CALL_DIR_INCOMING);

    /* Caller ID URC */
    assert(sim7670_cellular_call_handle_urc(&ctx, "+CLIP: \"10086\",129,\"\",0,\"\",0") == ESP_OK);
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(strcmp(status.phone_number, "10086") == 0);

    /* Answer */
    s_mock_time_us = 20000000;
    assert(sim7670_cellular_call_answer(&ctx) == ESP_OK);
    assert(strcmp(s_last_cmd, "ATA") == 0);
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_ACTIVE);

    /* Remote ends call */
    s_mock_time_us = 35000000;
    assert(sim7670_cellular_call_handle_urc(&ctx, "NO CARRIER") == ESP_OK);
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_IDLE);
    assert(status.last_disconnect_reason == SIM7670_CALL_DISCONNECT_REMOTE_HANGUP);
    assert(status.call_duration_sec == 15);
}

static void test_call_rejections_and_timeouts(void)
{
    sim7670_cellular_call_ctx_t ctx;
    sim7670_cellular_call_config_t config = {
        .at_send = mock_at_send,
        .user_ctx = NULL,
        .clock_fn = mock_clock,
    };
    assert(sim7670_cellular_call_init(&ctx, &config) == ESP_OK);

    /* 1. Remote Busy */
    assert(sim7670_cellular_call_dial(&ctx, "13800000001") == ESP_OK);
    assert(sim7670_cellular_call_handle_urc(&ctx, "BUSY") == ESP_OK);
    sim7670_call_status_t status;
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_IDLE);
    assert(status.last_disconnect_reason == SIM7670_CALL_DISCONNECT_BUSY);

    /* 2. No Answer */
    assert(sim7670_cellular_call_dial(&ctx, "13800000002") == ESP_OK);
    assert(sim7670_cellular_call_handle_urc(&ctx, "NO ANSWER") == ESP_OK);
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_IDLE);
    assert(status.last_disconnect_reason == SIM7670_CALL_DISCONNECT_NO_ANSWER);

    /* 3. Dialing timeout (>60s) */
    s_mock_time_us = 100000000;
    assert(sim7670_cellular_call_dial(&ctx, "13800000003") == ESP_OK);
    s_mock_time_us += 65000000; /* +65 seconds */
    assert(sim7670_cellular_call_poll_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_IDLE);
    assert(status.last_disconnect_reason == SIM7670_CALL_DISCONNECT_TIMEOUT);
}

static void test_audio_configuration(void)
{
    sim7670_cellular_call_ctx_t ctx;
    sim7670_cellular_call_config_t config = {
        .at_send = mock_at_send,
        .user_ctx = NULL,
        .clock_fn = mock_clock,
    };
    assert(sim7670_cellular_call_init(&ctx, &config) == ESP_OK);
    assert(sim7670_cellular_call_configure(&ctx, 85) == ESP_OK);
}

static void test_unsolicited_voice_call_indicators(void)
{
    sim7670_cellular_call_ctx_t ctx;
    sim7670_cellular_call_config_t config = {
        .at_send = mock_at_send,
        .user_ctx = NULL,
        .clock_fn = mock_clock,
    };
    assert(sim7670_cellular_call_init(&ctx, &config) == ESP_OK);

    /* Dial */
    assert(sim7670_cellular_call_dial(&ctx, "10086") == ESP_OK);

    /* Direct VOICE CALL: BEGIN URC from modem */
    s_mock_time_us = 20000000;
    assert(sim7670_cellular_call_handle_urc(&ctx, "VOICE CALL: BEGIN") == ESP_OK);
    sim7670_call_status_t status;
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_ACTIVE);

    /* Direct VOICE CALL: END URC from modem */
    s_mock_time_us = 50000000;
    assert(sim7670_cellular_call_handle_urc(&ctx, "VOICE CALL: END: 00:00:30") == ESP_OK);
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_IDLE);
    assert(status.call_duration_sec == 30);
    assert(status.last_disconnect_reason == SIM7670_CALL_DISCONNECT_REMOTE_HANGUP);
}

static void test_dial_error_and_invalid_answer(void)
{
    sim7670_cellular_call_ctx_t ctx;
    sim7670_cellular_call_config_t config = {
        .at_send = mock_at_send,
        .user_ctx = NULL,
        .clock_fn = mock_clock,
    };
    assert(sim7670_cellular_call_init(&ctx, &config) == ESP_OK);

    /* Cannot answer when IDLE */
    assert(sim7670_cellular_call_answer(&ctx) == ESP_ERR_INVALID_STATE);

    /* Simulate AT error during dialing */
    s_mock_err = ESP_FAIL;
    assert(sim7670_cellular_call_dial(&ctx, "10086") == ESP_FAIL);
    sim7670_call_status_t status;
    assert(sim7670_cellular_call_get_status(&ctx, &status) == ESP_OK);
    assert(status.state == SIM7670_CALL_STATE_IDLE);
    assert(status.last_disconnect_reason == SIM7670_CALL_DISCONNECT_ERROR);
    s_mock_err = ESP_OK;
}

static void test_string_conversions(void)
{
    assert(strcmp(sim7670_call_state_to_str(SIM7670_CALL_STATE_IDLE), "IDLE") == 0);
    assert(strcmp(sim7670_call_state_to_str(SIM7670_CALL_STATE_DIALING), "DIALING") == 0);
    assert(strcmp(sim7670_call_state_to_str(SIM7670_CALL_STATE_ALERTING), "ALERTING") == 0);
    assert(strcmp(sim7670_call_state_to_str(SIM7670_CALL_STATE_INCOMING), "INCOMING") == 0);
    assert(strcmp(sim7670_call_state_to_str(SIM7670_CALL_STATE_ACTIVE), "ACTIVE") == 0);
    assert(strcmp(sim7670_call_state_to_str(SIM7670_CALL_STATE_DISCONNECTING), "DISCONNECTING") == 0);
    assert(strcmp(sim7670_call_state_to_str(SIM7670_CALL_STATE_ERROR), "ERROR") == 0);

    assert(strcmp(sim7670_call_disconnect_reason_to_str(SIM7670_CALL_DISCONNECT_NONE), "NONE") == 0);
    assert(strcmp(sim7670_call_disconnect_reason_to_str(SIM7670_CALL_DISCONNECT_LOCAL_HANGUP), "LOCAL_HANGUP") == 0);
    assert(strcmp(sim7670_call_disconnect_reason_to_str(SIM7670_CALL_DISCONNECT_REMOTE_HANGUP), "REMOTE_HANGUP") == 0);
    assert(strcmp(sim7670_call_disconnect_reason_to_str(SIM7670_CALL_DISCONNECT_BUSY), "BUSY") == 0);
    assert(strcmp(sim7670_call_disconnect_reason_to_str(SIM7670_CALL_DISCONNECT_NO_ANSWER), "NO_ANSWER") == 0);
    assert(strcmp(sim7670_call_disconnect_reason_to_str(SIM7670_CALL_DISCONNECT_NETWORK_REJECT), "NETWORK_REJECT") == 0);
    assert(strcmp(sim7670_call_disconnect_reason_to_str(SIM7670_CALL_DISCONNECT_TIMEOUT), "TIMEOUT") == 0);
    assert(strcmp(sim7670_call_disconnect_reason_to_str(SIM7670_CALL_DISCONNECT_ERROR), "ERROR") == 0);
}

int main(void)
{
    test_initialization();
    test_outgoing_call_flow();
    test_incoming_call_flow();
    test_call_rejections_and_timeouts();
    test_audio_configuration();
    test_unsolicited_voice_call_indicators();
    test_dial_error_and_invalid_answer();
    test_string_conversions();
    printf("ALL SIM7670 CELLULAR CALL TESTS PASSED\n");
    return 0;
}
"""


class TestSim7670CellularCallNative(unittest.TestCase):
    def test_native_sim7670_cellular_call_state_machine(self) -> None:
        stdout = run_c(
            harness=HARNESS,
            components=("sim7670_cellular_call",),
        )
        self.assertIn("ALL SIM7670 CELLULAR CALL TESTS PASSED", stdout)


if __name__ == "__main__":
    unittest.main()

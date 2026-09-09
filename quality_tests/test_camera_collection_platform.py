import csv
import io
import re
import unittest
from pathlib import Path

from quality_tests.native_convergence import ROOT, run_c


FIRMWARE = ROOT / "firmware" / "mqtt_heartbeat"


CAMERA_NATIVE_HEADERS = {
    "esp_err.h": r'''#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 258
#define ESP_ERR_INVALID_STATE 259
#define ESP_ERR_TIMEOUT 263
''',
    "driver/i2c.h": r'''#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
typedef int i2c_port_t;
#define I2C_NUM_0 0
#define I2C_MODE_MASTER 1
#define GPIO_PULLUP_ENABLE 1
typedef struct {
    int mode;
    int sda_io_num;
    int scl_io_num;
    int sda_pullup_en;
    int scl_pullup_en;
    struct { uint32_t clk_speed; } master;
    uint32_t clk_flags;
} i2c_config_t;
''',
    "esp_camera.h": r'''#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#define OV5640_PID 0x5640
#define LEDC_TIMER_0 0
#define LEDC_CHANNEL_0 0
#define PIXFORMAT_JPEG 4
#define FRAMESIZE_QVGA 5
#define CAMERA_FB_IN_DRAM 6
#define CAMERA_GRAB_WHEN_EMPTY 7
typedef struct {
    int pin_pwdn, pin_reset, pin_xclk, pin_sccb_sda, pin_sccb_scl;
    int sccb_i2c_port;
    int pin_d7, pin_d6, pin_d5, pin_d4, pin_d3, pin_d2, pin_d1, pin_d0;
    int pin_vsync, pin_href, pin_pclk;
    int xclk_freq_hz, ledc_timer, ledc_channel;
    int pixel_format, frame_size, jpeg_quality, fb_count, fb_location, grab_mode;
} camera_config_t;
typedef struct { struct { uint16_t PID; } id; } sensor_t;
typedef struct {
    uint8_t *buf;
    size_t len;
    size_t width;
    size_t height;
    int format;
} camera_fb_t;
esp_err_t esp_camera_init(const camera_config_t *);
esp_err_t esp_camera_deinit(void);
sensor_t *esp_camera_sensor_get(void);
camera_fb_t *esp_camera_fb_get(void);
void esp_camera_fb_return(camera_fb_t *);
''',
    "esp_timer.h": r'''#pragma once
#include <stdint.h>
int64_t esp_timer_get_time(void);
''',
    "mbedtls/sha256.h": r'''#pragma once
#include <stddef.h>
int mbedtls_sha256(const unsigned char *, size_t, unsigned char *, int);
''',
    "sys/lock.h": r'''#pragma once
typedef int _lock_t;
int _lock_try_acquire(_lock_t *);
void _lock_release(_lock_t *);
''',
    "sdkconfig.h": "/* Configuration is supplied by native -D flags. */\n",
}


CAMERA_NATIVE_DEFINES = (
    "CONFIG_EGOLINK_PLATFORM_CAMERA_ENABLED=1",
    "CONFIG_SCCB_HARDWARE_I2C_DRIVER_LEGACY=1",
    "CONFIG_SCCB_HARDWARE_I2C_PORT0=1",
    "CONFIG_SCCB_CLK_FREQ=100000",
)


CAMERA_NATIVE_HARNESS = r'''
#include "platform_camera.h"
#include "platform_i2c_bus.h"
#include "esp_camera.h"
#include "esp_timer.h"
#include "sys/lock.h"
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned lock_calls, unlock_calls, i2c_calls, lease_calls, lease_release_calls;
static unsigned init_calls, get_calls, return_calls, deinit_calls, consumer_calls;
static bool lock_busy;
static esp_err_t i2c_result=ESP_OK;
static esp_err_t lease_result=ESP_OK;
static int64_t clock_us=1000;
static sensor_t sensor={.id={.PID=OV5640_PID}};
static uint8_t jpeg[]={0xff,0xd8,0x11,0x22,0xff,0xd9};
static camera_fb_t frame={.buf=jpeg,.len=sizeof(jpeg),.width=320,.height=240,
    .format=PIXFORMAT_JPEG};

int _lock_try_acquire(_lock_t *lock)
{ (void)lock;++lock_calls;return lock_busy?1:0; }
void _lock_release(_lock_t *lock)
{ (void)lock;++unlock_calls; }
esp_err_t platform_i2c_bus_ensure(i2c_port_t port,const i2c_config_t *config)
{
    ++i2c_calls;assert(port==I2C_NUM_0);assert(config);
    assert(config->sda_io_num==15&&config->scl_io_num==16);
    assert(config->master.clk_speed==100000U);return i2c_result;
}
esp_err_t platform_i2c_bus_lease_acquire(i2c_port_t port,uint32_t timeout_ms)
{++lease_calls;assert(port==I2C_NUM_0);assert(timeout_ms==250U);return lease_result;}
esp_err_t platform_i2c_bus_lease_release(i2c_port_t port)
{++lease_release_calls;assert(port==I2C_NUM_0);return ESP_OK;}
esp_err_t esp_camera_init(const camera_config_t *config)
{
    ++init_calls;assert(config&&config->frame_size==FRAMESIZE_QVGA);
    assert(config->fb_count==1&&config->fb_location==CAMERA_FB_IN_DRAM);
    return ESP_OK;
}
esp_err_t esp_camera_deinit(void){++deinit_calls;return ESP_OK;}
sensor_t *esp_camera_sensor_get(void){return &sensor;}
camera_fb_t *esp_camera_fb_get(void){++get_calls;return &frame;}
void esp_camera_fb_return(camera_fb_t *returned)
{ assert(returned==&frame);++return_calls; }
int64_t esp_timer_get_time(void){clock_us+=100;return clock_us;}
int mbedtls_sha256(const unsigned char *data,size_t length,
                   unsigned char *digest,int is224)
{
    assert(data==jpeg&&length==sizeof(jpeg)&&digest&&!is224);
    memset(digest,0x5a,PLATFORM_CAMERA_SHA256_BYTES);return 0;
}
static bool consume(void *context,const uint8_t *data,size_t length,
                    const platform_camera_capture_result_t *metadata)
{
    (void)context;++consumer_calls;assert(data==jpeg&&length==sizeof(jpeg));
    assert(metadata&&metadata->frame_acquired&&metadata->jpeg_markers_valid);
    return true;
}

int main(void)
{
#if NATIVE_EXPECTED_MODE == 0
    assert(platform_camera_shared_i2c_state()==PLATFORM_CAMERA_SHARED_I2C_BLOCKED);
    assert(!strcmp(platform_camera_shared_i2c_state_name(
        platform_camera_shared_i2c_state()),"blocked"));
    assert(!platform_camera_unverified_trial_attempt_consumed());
    const char *reason=NULL;
    assert(platform_camera_preflight(&reason)==
        PLATFORM_CAMERA_BLOCKED_SHARED_I2C_UNVERIFIED);
    assert(reason&&strstr(reason,"unverified"));
    platform_camera_capture_result_t result;
    assert(platform_camera_capture_single(consume,NULL,&result)==
        PLATFORM_CAMERA_BLOCKED_SHARED_I2C_UNVERIFIED);
    assert(!result.attempted&&!result.frame_acquired);
    assert(!lock_calls&&!i2c_calls&&!init_calls&&!get_calls&&!deinit_calls);
    assert(!platform_camera_unverified_trial_attempt_consumed());
#elif NATIVE_EXPECTED_MODE == 1
    assert(platform_camera_shared_i2c_state()==
        PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED);
    assert(!strcmp(platform_camera_shared_i2c_state_name(
        platform_camera_shared_i2c_state()),"trial_unverified"));
    assert(!platform_camera_timed_capture_allowed());
    assert(!platform_camera_unverified_trial_attempt_consumed());
    const char *reason=NULL;
    assert(platform_camera_preflight(&reason)==PLATFORM_CAMERA_TRIAL_READY_UNVERIFIED);
    assert(reason&&strstr(reason,"trial"));
    platform_camera_capture_result_t busy;
    lock_busy=true;
    assert(platform_camera_capture_single(consume,NULL,&busy)==PLATFORM_CAMERA_BUSY);
    assert(!busy.attempted&&!i2c_calls&&!init_calls);
    assert(!platform_camera_unverified_trial_attempt_consumed());
    lock_busy=false;
    platform_camera_capture_result_t first;
    assert(platform_camera_capture_single(consume,NULL,&first)==PLATFORM_CAMERA_OK);
    assert(first.attempted&&first.frame_acquired&&first.framebuffer_returned&&
        first.driver_deinitialized);
    assert(platform_camera_unverified_trial_attempt_consumed());
    assert(i2c_calls==1&&lease_calls==1&&lease_release_calls==1&&
        init_calls==1&&get_calls==1&&return_calls==1&&deinit_calls==1&&
        consumer_calls==1&&unlock_calls==1);
    platform_camera_capture_result_t second;
    assert(platform_camera_capture_single(consume,NULL,&second)==
        PLATFORM_CAMERA_TRIAL_ATTEMPT_CONSUMED);
    assert(!second.attempted&&!second.frame_acquired);
    assert(i2c_calls==1&&lease_calls==1&&lease_release_calls==1&&
        init_calls==1&&get_calls==1&&return_calls==1&&deinit_calls==1&&
        consumer_calls==1&&unlock_calls==1);
#elif NATIVE_EXPECTED_MODE == 2
    assert(platform_camera_shared_i2c_state()==PLATFORM_CAMERA_SHARED_I2C_VERIFIED);
    assert(!strcmp(platform_camera_shared_i2c_state_name(
        platform_camera_shared_i2c_state()),"verified"));
    assert(platform_camera_timed_capture_allowed());
    for(unsigned i=0;i<2U;++i){
        platform_camera_capture_result_t result;
        assert(platform_camera_capture_single(consume,NULL,&result)==PLATFORM_CAMERA_OK);
        assert(result.attempted&&result.driver_deinitialized);
    }
    assert(!platform_camera_unverified_trial_attempt_consumed());
    assert(i2c_calls==2&&lease_calls==2&&lease_release_calls==2&&
        init_calls==2&&get_calls==2&&return_calls==2&&deinit_calls==2&&
        consumer_calls==2&&unlock_calls==2);
#elif NATIVE_EXPECTED_MODE == 3
    assert(platform_camera_shared_i2c_state()==
        PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED);
    i2c_result=ESP_FAIL;
    platform_camera_capture_result_t failed;
    assert(platform_camera_capture_single(consume,NULL,&failed)==
        PLATFORM_CAMERA_I2C_BUS_UNAVAILABLE);
    assert(failed.attempted&&!failed.frame_acquired);
    assert(platform_camera_unverified_trial_attempt_consumed());
    assert(i2c_calls==1&&!init_calls&&!get_calls&&!deinit_calls&&!consumer_calls);
    assert(unlock_calls==1);
    platform_camera_capture_result_t retry;
    assert(platform_camera_capture_single(consume,NULL,&retry)==
        PLATFORM_CAMERA_TRIAL_ATTEMPT_CONSUMED);
    assert(!retry.attempted);
    assert(i2c_calls==1&&!init_calls&&!get_calls&&!deinit_calls&&!consumer_calls);
    assert(unlock_calls==1);
#elif NATIVE_EXPECTED_MODE == 4
    assert(platform_camera_shared_i2c_state()==
        PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED);
    lease_result=ESP_ERR_TIMEOUT;
    platform_camera_capture_result_t failed;
    assert(platform_camera_capture_single(consume,NULL,&failed)==
        PLATFORM_CAMERA_I2C_BUS_UNAVAILABLE);
    assert(failed.attempted&&!failed.frame_acquired);
    assert(failed.reason&&!strcmp(failed.reason,
        "platform_i2c0_transaction_lease_timeout"));
    assert(platform_camera_unverified_trial_attempt_consumed());
    assert(i2c_calls==1&&lease_calls==1&&!lease_release_calls);
    assert(!init_calls&&!get_calls&&!deinit_calls&&!consumer_calls);
    assert(unlock_calls==1);
#else
#error "unknown native camera test mode"
#endif
    puts("camera shared-I2C gate native PASS");
    return 0;
}
'''


def _run_camera_native(mode: int) -> str:
    return run_c(
        CAMERA_NATIVE_HARNESS,
        components=("platform_camera",),
        headers=CAMERA_NATIVE_HEADERS,
        defines=CAMERA_NATIVE_DEFINES + (
            f"CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL={int(mode in (1, 3, 4))}",
            f"CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED={int(mode == 2)}",
            f"NATIVE_EXPECTED_MODE={mode}",
        ),
    )


def _sdkconfig_entries(path: Path) -> dict[str, str | None]:
    entries: dict[str, str | None] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        unset = re.fullmatch(r"# (CONFIG_[A-Z0-9_]+) is not set", line)
        if unset:
            entries[unset.group(1)] = None
            continue
        assigned = re.fullmatch(r"(CONFIG_[A-Z0-9_]+)=(.*)", line)
        if assigned:
            entries[assigned.group(1)] = assigned.group(2)
    return entries


def _check_camera_gate_profiles_are_explicit_and_mutually_exclusive():
    normal = _sdkconfig_entries(FIRMWARE / "sdkconfig.camera_collection.defaults")
    trial_path = FIRMWARE / "sdkconfig.camera_shared_i2c_trial.defaults"
    trial = _sdkconfig_entries(trial_path)
    verified = "CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED"
    unverified_trial = (
        "CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_UNVERIFIED_TRIAL"
    )
    assert normal[verified] is None
    assert normal[unverified_trial] is None
    assert trial[verified] is None
    assert trial[unverified_trial] == "y"

    kconfig = (
        FIRMWARE / "components" / "platform_camera" / "Kconfig.projbuild"
    ).read_text(encoding="utf-8")
    assert "choice EGOLINK_PLATFORM_CAMERA_SHARED_I2C_GATE" in kconfig
    choice = kconfig[
        kconfig.index("choice EGOLINK_PLATFORM_CAMERA_SHARED_I2C_GATE"):
        kconfig.index("endchoice")
    ]
    assert f"config {verified.removeprefix('CONFIG_')}" in choice
    assert f"config {unverified_trial.removeprefix('CONFIG_')}" in choice

    try:
        run_c(
            CAMERA_NATIVE_HARNESS,
            components=("platform_camera",),
            headers=CAMERA_NATIVE_HEADERS,
            defines=CAMERA_NATIVE_DEFINES + (
                f"{verified}=1",
                f"{unverified_trial}=1",
                "NATIVE_EXPECTED_MODE=2",
            ),
        )
    except AssertionError as error:
        assert "verified and unverified-trial camera states are mutually exclusive" in str(
            error
        )
    else:
        raise AssertionError("both shared-I2C camera gate states compiled together")


def _c_function_body(source: str, name: str) -> str:
    definition = re.search(
        rf"^[ \t]*(?:static[ \t]+)?[A-Za-z_][A-Za-z0-9_ \t*]*"
        rf"[ \t*]+\b{name}\s*\([^;{{]*\)\s*\{{",
        source,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert definition, f"C function not found: {name}"
    start = source.index("{", definition.start())
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:index]
    raise AssertionError(f"unterminated C function: {name}")


def _check_nonverified_camera_policy_is_manual_only_and_truthful():
    source = (FIRMWARE / "main" / "collection_main.c").read_text(encoding="utf-8")

    # A trial binary must remain identifiable in every ordinary observation
    # through CONFIG_ID and in successful photo metadata through driver_profile.
    assert '#define CONFIG_ID "collector-v1-camera-shared-i2c-trial_unverified"' in source
    assert '#define CONFIG_ID "collector-v1-camera-shared-i2c-verified"' in source
    assert '#define CONFIG_ID "collector-v1-camera-shared-i2c-blocked"' in source
    driver_profile = _c_function_body(source, "photo_camera_driver_profile")
    assert "if(persisted_profile&&persisted_profile[0])return persisted_profile;" in driver_profile
    assert "PLATFORM_CAMERA_SHARED_I2C_UNKNOWN_LEGACY" in driver_profile
    assert "PLATFORM_CAMERA_SHARED_I2C_TRIAL_UNVERIFIED" in driver_profile
    assert '"qvga-jpeg-q12-v1-shared-i2c-trial_unverified"' in driver_profile
    metadata = _c_function_body(source, "photo_append_capture_metadata")
    assert ".driver_profile=photo_camera_driver_profile(" in metadata
    for assignment in (
        ".runtime_config_id=outcome->intent.runtime_config_id",
        ".fw_version=outcome->intent.capture_fw_version",
        ".firmware_elf_sha256=outcome->intent.capture_firmware_elf_sha256",
        "outcome->intent.camera_driver_profile",
    ):
        assert assignment in metadata

    # The STARTED journal captures provenance before hardware I/O; reboot
    # recovery copies it back and never substitutes the new image's gate.
    stamp = _c_function_body(source, "photo_stamp_intent")
    for field in (
        "camera_shared_i2c_state",
        "camera_driver_profile",
        "runtime_config_id",
        "capture_fw_version",
        "capture_firmware_elf_sha256",
    ):
        assert f"intent->{field}" in stamp
    journal_from_intent = _c_function_body(
        source, "photo_capture_journal_from_intent"
    )
    intent_from_journal = _c_function_body(
        source, "photo_intent_from_capture_journal"
    )
    for field in (
        "camera_shared_i2c_state",
        "camera_driver_profile",
        "runtime_config_id",
        "capture_fw_version",
        "capture_firmware_elf_sha256",
    ):
        assert f"journal->{field}" in journal_from_intent
        assert f"intent->{field}" in journal_from_intent
        assert f"intent->{field}" in intent_from_journal
        assert f"journal->{field}" in intent_from_journal
    restore = _c_function_body(source, "photo_capture_restore_outcome")
    assert "photo_camera_shared_i2c_state_from_name(" in restore
    assert "outcome->intent.camera_shared_i2c_state" in restore
    assert "platform_camera_shared_i2c_state()" not in restore

    # Restoring a formerly enabled timer into a trial image is persisted
    # disabled before photo control is announced ready.
    initialize = _c_function_body(source, "photo_control_state_init")
    assert "inherited_timer_enable=" in initialize
    assert '"disabled_by_command"' in initialize
    assert "photo_timer.status_report_pending&&" in initialize
    assert "!photo_timer_camera_policy_rejected(photo_timer.state_reason)" in initialize
    gate_check = initialize.index(
        "!platform_camera_timed_capture_allowed()&&inherited_timer_enable"
    )
    disable = initialize.index("photo_timer.enabled=false", gate_check)
    save = initialize.index("save_photo_timer(&photo_timer)", disable)
    publish_ready = initialize.index(
        "atomic_store(&photo_command_ack_sequence", save
    )
    assert gate_check < disable < save < publish_ready
    assert "photo_timer_camera_policy_state_reason()" in initialize
    assert "photo_timer_camera_policy_message()" in initialize

    # Timer enable is rejected, including duplicate delivery, while a disable
    # command is not coupled to capture readiness and reaches the normal apply.
    handler = _c_function_body(source, "photo_handle_timer_command")
    duplicate_rejection = re.search(
        r"command->timer_enabled\s*&&\s*"
        r"!platform_camera_timed_capture_allowed\(\)",
        handler,
    )
    assert duplicate_rejection
    admission = re.search(
        r"command->timer_enabled\s*&&\s*"
        r"\(\s*!timed_capture_allowed\s*\|\|\s*!capture_ready\s*\)",
        handler,
    )
    assert admission
    assert handler.index("photo_control_timer_apply(", admission.end()) > admission.end()
    assert "photo_timer_camera_policy_message()" in handler

    # Runtime defense is before the timer tick/capture path, persists the
    # disabled state, and reports it instead of silently dropping the schedule.
    service = _c_function_body(source, "photo_service_local_timer")
    policy = service.index(
        "timer_policy_rejected="
    )
    assert "!platform_camera_timed_capture_allowed()" in service[policy:]
    fail_closed = service.index("timer.enabled&&(timer_policy_rejected", policy)
    service_disable = service.index("timer.enabled=false", fail_closed)
    service_save = service.index("save_photo_timer(&timer)", service_disable)
    timer_tick = service.index("photo_control_timer_tick(", service_save)
    assert fail_closed < service_disable < service_save < timer_tick
    assert "photo_timer_camera_policy_state_reason()" in service
    assert "photo_timer_camera_policy_message()" in service

    policy_rejected = _c_function_body(
        source, "photo_timer_camera_policy_rejected"
    )
    assert '"camera_trial_manual_only"' in policy_rejected
    assert '"camera_shared_i2c_blocked"' in policy_rejected
    pending = _c_function_body(source, "photo_post_pending_timer_state")
    assert "photo_timer_camera_policy_rejected(timer.state_reason)" in pending
    assert 'camera_policy_rejected?"error":"applied"' in pending
    assert "camera_policy_rejected?NULL:&timer" in pending
    assert 'camera_policy_rejected?NULL:"applied"' in pending

    # Settling a capture inherited from verified firmware may update several
    # terminal reasons. Every persistence branch must re-assert the current
    # blocked/trial policy so its pending ACK can never become `applied`.
    enforce = _c_function_body(source, "photo_timer_enforce_camera_policy")
    assert "!timer||platform_camera_timed_capture_allowed()" in enforce
    assert "timer->enabled=false" in enforce
    assert "timer->schedule_armed=false" in enforce
    assert "timer->status_report_pending=true" in enforce
    assert "photo_timer_camera_policy_state_reason()" in enforce
    settle = _c_function_body(source, "photo_settle_timer_capture")
    saves = [match.start() for match in re.finditer(r"save_photo_timer\(timer\)", settle)]
    enforcements = [
        match.start()
        for match in re.finditer(
            r"photo_timer_enforce_camera_policy\(timer\)", settle
        )
    ]
    assert len(saves) == len(enforcements) == 3
    assert all(enforcement < save for enforcement, save in zip(enforcements, saves))

    source_status = _c_function_body(source, "photo_source_status_payload")
    assert "const bool manual_chain_ready=" in source_status
    assert "const bool verified_ready=" in source_status
    assert "camera_status==PLATFORM_CAMERA_OK" in source_status
    assert "if(runtime_ready)*runtime_ready=verified_ready;" in source_status
    assert 'cJSON_AddBoolToObject(payload,"capture_trigger_wired",manual_chain_ready)' in source_status
    assert 'cJSON_AddBoolToObject(payload,"driver_preflight_ready",' in source_status

    # Health and session telemetry expose the unverified state and the
    # one-attempt budget separately from generic camera readiness.
    health = _c_function_body(source, "health")
    for key in (
        "shared_i2c_state",
        "manual_capture_ready",
        "timed_capture_allowed",
        "unverified_trial_attempt_consumed",
        "unverified_trial_attempt_remaining",
    ):
        assert f'"{key}"' in health
    app_main = _c_function_body(source, "app_main")
    assert '"camera_shared_i2c_state"' in app_main
    assert 'camera_preflight==PLATFORM_CAMERA_OK' in app_main
    assert '"camera_manual_capture_ready"' in app_main
    assert '"camera_timed_capture_allowed"' in app_main
    assert '"camera_unverified_trial_attempt_consumed"' in app_main
    assert '"camera_manual_capture_trial_unverified_ready"' in app_main


def _check_platform_camera_disabled_build_fails_closed_without_driver_symbols():
    harness = r'''
#include "platform_camera.h"
#include <assert.h>
#include <string.h>
int main(void){
    const char *reason=0;
    assert(platform_camera_preflight(&reason)==PLATFORM_CAMERA_DISABLED);
    assert(reason&&strcmp(reason,"camera_profile_disabled")==0);
    platform_camera_capture_result_t result;
    assert(platform_camera_capture_single(0,0,&result)==PLATFORM_CAMERA_DISABLED);
    assert(!result.attempted&&!result.frame_acquired&&!result.framebuffer_returned);
    assert(strcmp(platform_camera_status_name(result.status),"disabled")==0);
    return 0;
}
'''
    run_c(
        harness,
        components=("platform_camera",),
        headers={"sdkconfig.h": "/* camera remains default-off */\n"},
    )


def _check_camera_profile_is_explicit_i2c_gated_and_bounded_single_frame():
    source = (FIRMWARE / "components" / "platform_camera" / "platform_camera.c").read_text(encoding="utf-8")
    header = (FIRMWARE / "components" / "platform_camera" / "include" / "platform_camera.h").read_text(encoding="utf-8")
    kconfig = (FIRMWARE / "components" / "platform_camera" / "Kconfig.projbuild").read_text(encoding="utf-8")
    defaults = (FIRMWARE / "sdkconfig.camera_collection.defaults").read_text(encoding="utf-8")
    assert 'default n' in kconfig
    assert "CONFIG_EGOLINK_PLATFORM_CAMERA_SHARED_I2C_VERIFIED is not set" in defaults
    assert "blocked_shared_i2c_hardware_coexistence_unverified_gpio15_16_i2c0" in source
    for pin in (
        "CAMERA_PIN_D0 7", "CAMERA_PIN_D1 8", "CAMERA_PIN_D2 9", "CAMERA_PIN_D3 10",
        "CAMERA_PIN_D4 11", "CAMERA_PIN_D5 12", "CAMERA_PIN_D6 13", "CAMERA_PIN_D7 14",
        "CAMERA_PIN_SDA 15", "CAMERA_PIN_SCL 16", "CAMERA_PIN_XCLK 39",
        "CAMERA_PIN_HREF 41", "CAMERA_PIN_VSYNC 42", "CAMERA_PIN_PCLK 46",
    ):
        assert pin in source
    assert ".frame_size=FRAMESIZE_QVGA" in source
    assert ".pixel_format=PIXFORMAT_JPEG" in source
    assert ".fb_count=1" in source
    assert ".fb_location=CAMERA_FB_IN_DRAM" in source
    assert ".pin_sccb_sda=-1" in source and ".pin_sccb_scl=-1" in source
    assert ".sccb_i2c_port=CAMERA_I2C_PORT" in source
    assert "platform_i2c_bus_ensure(CAMERA_I2C_PORT,&bus)" in source
    assert source.index("platform_i2c_bus_ensure(CAMERA_I2C_PORT,&bus)") < source.index("esp_camera_init(&config)")
    assert "platform_i2c_bus_lease_acquire(" in source
    assert "CAMERA_I2C_LEASE_TIMEOUT_MS 250U" in source
    assert source.index("platform_i2c_bus_lease_acquire(") < source.index("esp_camera_init(&config)")
    assert source.count("platform_i2c_bus_lease_release(CAMERA_I2C_PORT)") == 3
    assert "CONFIG_SCCB_HARDWARE_I2C_DRIVER_LEGACY=y" in defaults
    assert "CONFIG_SCCB_HARDWARE_I2C_PORT0=y" in defaults
    assert "CONFIG_SCCB_CLK_FREQ=100000" in defaults
    assert "PHOTO_MEDIA_STORE_MAX_SLOTS" in (FIRMWARE / "main" / "collection_main.c").read_text(encoding="utf-8")
    assert "# CONFIG_SPIRAM is not set" in defaults
    assert source.count("esp_camera_fb_get()") == 1
    assert "esp_camera_fb_return(frame)" in source
    assert "esp_camera_deinit()" in source
    assert "sensor->id.PID!=OV5640_PID" in source
    assert "PLATFORM_CAMERA_UNSUPPORTED_SENSOR" in source
    assert "static atomic_bool s_lifecycle_blocked;" in source
    assert "atomic_load(&s_lifecycle_blocked)" in source
    assert "atomic_store(&s_lifecycle_blocked,true)" in source
    assert "mbedtls_sha256(frame->buf,frame->len" in source
    assert "low-level capture seam" in header.lower()
    assert "capture_photo_once/configure_photo_timer" in header
    assert "training_allowed=false" in header


def _check_camera_partition_profile_is_16mib_non_overlapping_and_media_is_separate():
    path = FIRMWARE / "partitions_camera_collection_16mb.csv"
    rows = []
    for row in csv.reader(io.StringIO(path.read_text(encoding="utf-8"))):
        if not row or row[0].lstrip().startswith("#"):
            continue
        name, kind, subtype, offset, size = [field.strip() for field in row[:5]]
        rows.append((name, kind, subtype, int(offset, 0), int(size, 0)))
    assert [row[0] for row in rows] == ["nvs", "phy_init", "factory", "ego_collection", "ego_media", "ego_outbox"]
    ordered = sorted(rows, key=lambda row: row[3])
    for left, right in zip(ordered, ordered[1:]):
        assert left[3] + left[4] <= right[3]
    assert max(offset + size for _, _, _, offset, size in rows) <= 16 * 1024 * 1024
    media = next(row for row in rows if row[0] == "ego_media")
    collection = next(row for row in rows if row[0] == "ego_collection")
    factory = next(row for row in rows if row[0] == "factory")
    outbox = next(row for row in rows if row[0] == "ego_outbox")
    assert factory[3:] == (0x200000, 0x300000)
    assert collection[2:] == ("0x41", 0x500000, 0x100000)
    assert media[2:] == ("0x42", 0x600000, 0x900000)
    assert outbox[2:] == ("0x40", 0xF00000, 0xC000)
    # Preserve the entire legacy app/data range. Future flashing still needs a
    # readback/decision because this layout does not itself back up old bytes.
    assert all(offset >= 0x200000 for name, _, _, offset, _ in rows if name not in {"nvs", "phy_init"})
    defaults = (FIRMWARE / "sdkconfig.camera_collection.defaults").read_text(encoding="utf-8")
    assert 'CONFIG_ESPTOOLPY_FLASHSIZE="16MB"' in defaults
    assert 'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions_camera_collection_16mb.csv"' in defaults
    source = (FIRMWARE / "main" / "collection_main.c").read_text(encoding="utf-8")
    assert "#define COLLECTION_PARTITION_ADDRESS 0x500000U" in source
    assert "#define COLLECTION_PARTITION_SIZE 0x100000U" in source
    assert "#define MEDIA_PARTITION_ADDRESS 0x600000U" in source
    assert "#define MEDIA_PARTITION_SIZE 0x900000U" in source


def _check_legacy_collection_profile_and_4k_record_spool_remain_unchanged():
    legacy = (FIRMWARE / "sdkconfig.collection.defaults").read_text(encoding="utf-8")
    partition = (FIRMWARE / "partitions_collection.csv").read_text(encoding="utf-8")
    record = (FIRMWARE / "components" / "collection_record" / "include" / "collection_record.h").read_text(encoding="utf-8")
    assert 'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions_collection.csv"' in legacy
    assert "ego_collection, data, 0x41, 0x122000, 0xD2000" in partition
    assert "COLLECTION_FRAME_CAPACITY 4000" in record
    assert "EGOLINK_COLLECTION_CAMERA_PROFILE=y" not in legacy


def _check_runtime_delivery_is_metadata_gated_fair_and_release_safe():
    source = (FIRMWARE / "main" / "collection_main.c").read_text(encoding="utf-8")
    assert 'PHOTO_METADATA_ACK_NVS_KEY "photo_meta_ack_v1"' in source
    assert "photo_record_metadata_acked(record.source_seq)" in source
    assert "metadata_identity>photo_metadata_ack_watermark" in source
    assert "PHOTO_ORDINARY_UPLOAD_BUDGET 8U" in source
    assert "PHOTO_FAIR_UPLOAD_INTERVAL_US 30000000LL" in source
    assert "photo_schedule_upload_retry(server_verified" in source
    assert "photo_control_capture_journal_allows_new_command(&pending_capture)" in source
    assert "photo_content_permanently_rejected" not in source
    assert "photo_append_media_terminal_status" not in source
    # The only ordinary upload release is inside the exact content-ACK branch;
    # the other release sites are local trusted-UTC retention paths.
    upload = source[source.index("static bool photo_upload_one"):source.index(
        "static void photo_schedule_upload_retry"
    )]
    assert upload.count("photo_media_release_locked(&record)") == 2
    assert upload.index("if(server_verified)") < upload.rindex(
        "photo_media_release_locked(&record)"
    )
    assert "posted.http_status_code>=200U&&posted.http_status_code<300U&&" in upload
    assert "photo_delivery_content_ack_response_matches" in upload
    assert "const bool success=" not in source


def _check_media_store_access_is_single_mutex_serialized_and_observable():
    source = (FIRMWARE / "main" / "collection_main.c").read_text(encoding="utf-8")
    wrapper_names = (
        "photo_media_init_locked",
        "photo_media_stats_locked",
        "photo_media_find_locked",
        "photo_media_peek_locked",
        "photo_media_read_locked",
        "photo_media_release_locked",
        "photo_media_capture_store_locked",
    )
    wrapper_start = source.index("static photo_media_store_result_t photo_media_init_locked")
    wrapper_end = source.index("static void photo_stack_hwm_observe")
    raw_calls = tuple(re.finditer(
        r"\bphoto_media_store_(?:init|get_stats|find|peek_committed|read|release|"
        r"prepare_with_expiry|write|commit)\s*\(",
        source,
    ))
    assert raw_calls
    assert all(wrapper_start <= call.start() < wrapper_end for call in raw_calls)

    for index, name in enumerate(wrapper_names):
        start = source.index(f"{name}(", wrapper_start)
        end = (source.index(f"{wrapper_names[index + 1]}(", start)
               if index + 1 < len(wrapper_names) else wrapper_end)
        body = source[start:end]
        assert body.count("photo_media_lock()") == 1
        assert body.count("photo_media_unlock()") == 1
        wrapped_calls = tuple(re.finditer(
            r"\bphoto_media_store_(?:init|get_stats|find|peek_committed|read|release|"
            r"prepare_with_expiry|write|commit)\s*\(",
            body,
        ))
        assert wrapped_calls
        assert body.index("photo_media_lock()") < wrapped_calls[0].start()
        assert wrapped_calls[-1].end() < body.index("photo_media_unlock()")

    assert "static SemaphoreHandle_t media_store_mutex;" in source
    assert "media_store_mutex=xSemaphoreCreateMutex();" in source
    assert "allocation_failed=allocation_failed||!media_store_mutex;" in source
    assert "vSemaphoreDelete(media_store_mutex);media_store_mutex=NULL;" in source
    assert "media_stats_valid=photo_media_stats_locked(&media);" in source
    assert "outcome->store_result=photo_media_capture_store_locked" in source
    assert source.count("outcome->store_result=photo_media_find_locked") == 2
    assert source.count("photo_media_peek_locked(*scan_cursor") == 2
    assert "store=photo_media_read_locked(&record,0U,jpeg,record.payload_bytes);" in source

    for api, field in (
        ("heap_caps_get_free_size(MALLOC_CAP_INTERNAL)", "internal_free_bytes"),
        ("heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL)", "internal_min_free_bytes"),
        ("heap_caps_get_free_size(MALLOC_CAP_DMA)", "dma_free_bytes"),
        ("heap_caps_get_largest_free_block(MALLOC_CAP_DMA)", "dma_largest_free_block_bytes"),
    ):
        assert api in source
        assert f'"{field}"' in source
    assert "uxTaskGetStackHighWaterMark2(NULL)" in source
    assert "sizeof(StackType_t)" in source
    assert '"task_stack_high_watermark_bytes"' in source
    for task in ("main", "store", "imu", "modem", "upload", "wifi"):
        assert f'photo_add_stack_hwm(stack_hwm,"{task}"' in source


class CameraCollectionPlatformTests(unittest.TestCase):
    def test_platform_camera_disabled_build_fails_closed_without_driver_symbols(self):
        _check_platform_camera_disabled_build_fails_closed_without_driver_symbols()

    def test_shared_i2c_default_blocked_does_not_touch_hardware(self):
        self.assertIn("native PASS", _run_camera_native(0))

    def test_shared_i2c_unverified_trial_is_one_actual_attempt_per_boot(self):
        self.assertIn("native PASS", _run_camera_native(1))

    def test_shared_i2c_failed_trial_attempt_also_consumes_boot_budget(self):
        self.assertIn("native PASS", _run_camera_native(3))

    def test_shared_i2c_lease_timeout_fails_before_camera_driver_entry(self):
        self.assertIn("native PASS", _run_camera_native(4))

    def test_shared_i2c_verified_mode_retains_repeat_capture(self):
        self.assertIn("native PASS", _run_camera_native(2))

    def test_shared_i2c_gate_profiles_are_explicit_and_mutually_exclusive(self):
        _check_camera_gate_profiles_are_explicit_and_mutually_exclusive()

    def test_nonverified_camera_modes_are_manual_only_and_truthful_in_collection_runtime(self):
        _check_nonverified_camera_policy_is_manual_only_and_truthful()

    def test_camera_profile_is_explicit_i2c_gated_and_bounded_single_frame(self):
        _check_camera_profile_is_explicit_i2c_gated_and_bounded_single_frame()

    def test_camera_partition_profile_is_16mib_non_overlapping_and_media_is_separate(self):
        _check_camera_partition_profile_is_16mib_non_overlapping_and_media_is_separate()

    def test_legacy_collection_profile_and_4k_record_spool_remain_unchanged(self):
        _check_legacy_collection_profile_and_4k_record_spool_remain_unchanged()

    def test_runtime_delivery_is_metadata_gated_fair_and_release_safe(self):
        _check_runtime_delivery_is_metadata_gated_fair_and_release_safe()

    def test_media_store_access_is_single_mutex_serialized_and_observable(self):
        _check_media_store_access_is_single_mutex_serialized_and_observable()

/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * CALL-010 static candidate. This firmware is intentionally isolated from
 * mqtt_heartbeat, LTE and RTC. A build is not permission to flash or run it.
 */

#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "bsp/esp-bsp.h"
#include "driver/gpio.h"
#include "esp_codec_dev.h"
#include "esp_attr.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "safe_audio_initializer_v1.h"
#include "sdkconfig.h"

#ifndef CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN
#define CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN 0
#endif

#ifndef CONFIG_EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC
#define CONFIG_EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC 0
#endif

#define AUDIO_SAMPLE_RATE_HZ 16000
#define AUDIO_CHANNELS 2
#define AUDIO_BITS_PER_SAMPLE 16
#define AUDIO_FRAME_MS 20
#define AUDIO_SAMPLES_PER_FRAME (AUDIO_SAMPLE_RATE_HZ * AUDIO_FRAME_MS / 1000)
#define AUDIO_FRAME_VALUES (AUDIO_SAMPLES_PER_FRAME * AUDIO_CHANNELS)
#define AUDIO_CLIP_THRESHOLD 32760
#define AUDIO_CHIRP_AMPLITUDE 1800
#define AUDIO_OUTPUT_DIAGNOSTIC_COUNTDOWN_SECONDS 15
#define AUDIO_OUTPUT_DIAGNOSTIC_STAGE_SECONDS 2
#define AUDIO_OUTPUT_DIAGNOSTIC_GAP_SECONDS 2
#define AUDIO_OUTPUT_DIAGNOSTIC_STAGE_COUNT 3
#define AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_1 55
#define AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_2 70
#define AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_3 85
#define AUDIO_OUTPUT_DIAGNOSTIC_MAX_VOLUME 85
#define AUDIO_OUTPUT_DIAGNOSTIC_PCM_PEAK 5000
#define AUDIO_OUTPUT_DIAGNOSTIC_FREQUENCY_HZ 1000
#define AUDIO_OUTPUT_DIAGNOSTIC_DEADLINE_SECONDS 30
#define AUDIO_PROCESSING_BUCKET_US 1000
#define AUDIO_PROCESSING_BUCKETS 64
#define AUDIO_DEADLINE_MARGIN_SECONDS 10
#define AUDIO_RUN_LATCH_MAGIC UINT32_C(0x45474F41)
#define ES8311_DAC_MUTE_REGISTER 0x31
#define ES8311_DAC_MUTE_MASK 0x60
#define ES8311_DAC_VOLUME_REGISTER 0x32
#define ES8311_VOLUME_REGISTER_BASE 98
#define ES8311_SAFE_VOLUME_REGISTER \
    (ES8311_VOLUME_REGISTER_BASE + CONFIG_EGOLINK_AUDIO_SAFE_VOLUME)
#define ES8311_MUTE_READBACK_ATTEMPTS 3
#define ES8311_MUTE_READBACK_DELAY_MS 2

_Static_assert(
    AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_3 <= AUDIO_OUTPUT_DIAGNOSTIC_MAX_VOLUME,
    "CALL-010 output diagnostic must never exceed the volume-85 cap");

static const char *TAG = "call010_audio";

static int16_t s_audio_frame[AUDIO_FRAME_VALUES];
static volatile bool s_audio_deadline_expired;
RTC_NOINIT_ATTR static volatile uint32_t s_audio_run_latch;

static esp_err_t pa_force_off(void)
{
    esp_err_t result = gpio_set_level(BSP_POWER_AMP_IO, 0);
    if (result != ESP_OK) {
        return result;
    }
    return gpio_get_level(BSP_POWER_AMP_IO) == 0 ? ESP_OK : ESP_FAIL;
}

static esp_err_t pa_prepare_off(void)
{
    /* Preload the output latch low before enabling output drive. */
    esp_err_t result = gpio_set_level(BSP_POWER_AMP_IO, 0);
    if (result != ESP_OK) {
        return result;
    }
    const gpio_config_t config = {
        .pin_bit_mask = UINT64_C(1) << BSP_POWER_AMP_IO,
        .mode = GPIO_MODE_INPUT_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    result = gpio_config(&config);
    return result == ESP_OK ? pa_force_off() : result;
}

static esp_err_t pa_enable(void)
{
    esp_err_t result = gpio_set_level(BSP_POWER_AMP_IO, 1);
    if (result != ESP_OK) {
        return result;
    }
    return gpio_get_level(BSP_POWER_AMP_IO) == 1 ? ESP_OK : ESP_FAIL;
}

static bool codec_mute_register_matches(int register_value, bool expected_muted)
{
    int mute_bits = register_value & ES8311_DAC_MUTE_MASK;
    return expected_muted
        ? mute_bits == ES8311_DAC_MUTE_MASK
        : mute_bits == 0;
}

static esp_err_t verify_codec_mute(
    esp_codec_dev_handle_t speaker, bool expected_muted)
{
    for (uint32_t attempt = 1;
         attempt <= ES8311_MUTE_READBACK_ATTEMPTS;
         ++attempt) {
        int register_value = 0;
        esp_err_t result = esp_codec_dev_read_reg(
            speaker, ES8311_DAC_MUTE_REGISTER, &register_value);
        if (result != ESP_OK) {
            ESP_LOGE(
                TAG,
                "ES8311 mute readback failed expected_muted=%s attempt=%" PRIu32
                " result=%s",
                expected_muted ? "true" : "false", attempt,
                esp_err_to_name(result));
            return result;
        }
        bool matched = codec_mute_register_matches(
            register_value, expected_muted);
        ESP_LOGI(
            TAG,
            "ES8311_MUTE_READBACK expected_muted=%s attempt=%" PRIu32
            " reg31=0x%02x matched=%s",
            expected_muted ? "true" : "false", attempt,
            register_value & 0xff, matched ? "true" : "false");
        if (matched) {
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(ES8311_MUTE_READBACK_DELAY_MS));
    }
    return ESP_FAIL;
}

static esp_err_t retry_codec_mute_register_once(
    esp_codec_dev_handle_t speaker, bool expected_muted)
{
    /* Exactly one bounded direct register retry; PA stays forced OFF. */
    int register_value = 0;
    esp_err_t result = esp_codec_dev_read_reg(
        speaker, ES8311_DAC_MUTE_REGISTER, &register_value);
    if (result != ESP_OK) {
        return result;
    }
    int requested_value = expected_muted
        ? register_value | ES8311_DAC_MUTE_MASK
        : register_value & ~ES8311_DAC_MUTE_MASK;
    ESP_LOGW(
        TAG,
        "ES8311 wrapper mute readback mismatch; PA remains OFF and one "
        "bounded direct register retry will run expected_muted=%s "
        "before=0x%02x requested=0x%02x",
        expected_muted ? "true" : "false", register_value & 0xff,
        requested_value & 0xff);
    result = esp_codec_dev_write_reg(
        speaker, ES8311_DAC_MUTE_REGISTER, requested_value);
    ESP_LOGI(
        TAG,
        "ES8311_MUTE_REPAIR_WRITE expected_muted=%s result=%s",
        expected_muted ? "true" : "false", esp_err_to_name(result));
    if (result != ESP_OK) {
        ESP_LOGE(TAG, "ES8311 direct mute retry write failed: %s",
                 esp_err_to_name(result));
        return result;
    }
    return verify_codec_mute(speaker, expected_muted);
}

static esp_err_t speaker_set_output_enabled(
    esp_codec_dev_handle_t speaker, bool enabled)
{
    esp_err_t result = pa_force_off();
    if (result != ESP_OK || speaker == NULL) {
        return result == ESP_OK ? ESP_ERR_INVALID_ARG : result;
    }

    result = esp_codec_dev_set_out_mute(speaker, !enabled);
    if (result == ESP_OK) {
        result = verify_codec_mute(speaker, !enabled);
    }
    if (result == ESP_FAIL) {
        result = retry_codec_mute_register_once(speaker, !enabled);
    }
    if (result == ESP_OK && enabled) {
        if (s_audio_deadline_expired) {
            result = ESP_ERR_TIMEOUT;
        } else {
            result = pa_enable();
            if (s_audio_deadline_expired) {
                pa_force_off();
                result = ESP_ERR_TIMEOUT;
            }
        }
    }
    if (result != ESP_OK || !enabled) {
        esp_err_t pa_result = pa_force_off();
        if (result == ESP_OK) {
            result = pa_result;
        }
    }
    return result;
}

static esp_err_t set_safe_output_volume_verified(
    esp_codec_dev_handle_t speaker)
{
    esp_err_t result = pa_force_off();
    if (result != ESP_OK || speaker == NULL) {
        return result == ESP_OK ? ESP_ERR_INVALID_ARG : result;
    }

    result = esp_codec_dev_set_out_vol(
        speaker, CONFIG_EGOLINK_AUDIO_SAFE_VOLUME);
    int register_value = -1;
    if (result == ESP_OK) {
        result = esp_codec_dev_read_reg(
            speaker, ES8311_DAC_VOLUME_REGISTER, &register_value);
    }
    bool matched = result == ESP_OK &&
        (register_value & 0xff) == ES8311_SAFE_VOLUME_REGISTER;
    ESP_LOGI(
        TAG,
        "ES8311_SAFE_VOLUME_READBACK configured=%d expected=0x%02x "
        "actual=0x%02x read_result=%s matched=%s pa_forced_off=true",
        CONFIG_EGOLINK_AUDIO_SAFE_VOLUME, ES8311_SAFE_VOLUME_REGISTER,
        register_value & 0xff, esp_err_to_name(result),
        matched ? "true" : "false");
    if (!matched) {
        pa_force_off();
        return result == ESP_OK ? ESP_FAIL : result;
    }
    return ESP_OK;
}

static esp_err_t set_output_diagnostic_volume_verified(
    esp_codec_dev_handle_t speaker,
    int volume,
    int *actual_register)
{
    esp_err_t result = pa_force_off();
    if (result != ESP_OK || speaker == NULL || actual_register == NULL) {
        return result == ESP_OK ? ESP_ERR_INVALID_ARG : result;
    }
    if (volume < 1 || volume > AUDIO_OUTPUT_DIAGNOSTIC_MAX_VOLUME) {
        return ESP_ERR_INVALID_ARG;
    }

    result = esp_codec_dev_set_out_vol(speaker, volume);
    int register_value = -1;
    if (result == ESP_OK) {
        result = esp_codec_dev_read_reg(
            speaker, ES8311_DAC_VOLUME_REGISTER, &register_value);
    }
    *actual_register = register_value;
    const int expected_register = ES8311_VOLUME_REGISTER_BASE + volume;
    bool matched = result == ESP_OK &&
        (register_value & 0xff) == expected_register;
    ESP_LOGI(
        TAG,
        "ES8311_OUTPUT_DIAGNOSTIC_VOLUME_READBACK volume=%d "
        "expected=0x%02x actual=0x%02x read_result=%s matched=%s "
        "pa_forced_off=true",
        volume, expected_register, register_value & 0xff,
        esp_err_to_name(result), matched ? "true" : "false");
    if (!matched) {
        pa_force_off();
        return result == ESP_OK ? ESP_FAIL : result;
    }
    return ESP_OK;
}

static void clear_audio_frame(void)
{
    volatile int16_t *frame = s_audio_frame;
    for (uint32_t index = 0; index < AUDIO_FRAME_VALUES; ++index) {
        frame[index] = 0;
    }
}

static esp_err_t open_output_diagnostic_codec_prearmed(
    call010_safe_audio_v1_t *audio,
    esp_codec_dev_sample_info_t *format)
{
    /*
     * esp_codec_dev's pinned I2S data interface unconditionally disables TX
     * while applying the initial format. Prime READY -> RUNNING immediately
     * before open so that internal disable is valid. The amplifier stays
     * forced off for this entire clock-only transition.
     */
    esp_err_t result = pa_force_off();
    if (result != ESP_OK) {
        return result;
    }
    if (audio == NULL || format == NULL || audio->speaker == NULL ||
        audio->tx_channel == NULL || audio->rx_channel != NULL ||
        audio->microphone != NULL || audio->speaker_codec_if == NULL ||
        audio->shared_i2s_data_if == NULL ||
        audio->shared_i2s_data_if->write == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if ((audio->speaker_codec_if->is_open != NULL &&
         !audio->speaker_codec_if->is_open(audio->speaker_codec_if)) ||
        (audio->shared_i2s_data_if->is_open != NULL &&
         !audio->shared_i2s_data_if->is_open(audio->shared_i2s_data_if))) {
        return ESP_ERR_INVALID_STATE;
    }

    result = i2s_channel_enable(audio->tx_channel);
    if (result != ESP_OK) {
        pa_force_off();
        return result;
    }
    ESP_LOGI(
        TAG,
        "AUDIO_OUTPUT_TX_PREARM result=ESP_OK "
        "speaker_pa_off_verified=true");

    result = esp_codec_dev_open(audio->speaker, format);
    if (result != ESP_OK) {
        /*
         * Readiness was checked before pre-arm, so esp_codec_dev_open owns
         * the channel by this point and close returns it to READY. The caller
         * still runs the normal idempotent deinitializer.
         */
        esp_codec_dev_close(audio->speaker);
        pa_force_off();
        return result;
    }

    result = pa_force_off();
    if (result != ESP_OK) {
        esp_codec_dev_close(audio->speaker);
        pa_force_off();
    }
    return result;
}

static void audio_deadline_callback(void *argument)
{
    (void)argument;
    s_audio_deadline_expired = true;
    gpio_set_level(BSP_POWER_AMP_IO, 0);
}

static bool claim_one_run_per_power_cycle(void)
{
    if (esp_reset_reason() == ESP_RST_POWERON) {
        s_audio_run_latch = 0;
    }
    ESP_LOGI(
        TAG,
        "AUDIO_RUN_LATCH_CHECK reset_reason=%d value=0x%08" PRIx32,
        (int)esp_reset_reason(), s_audio_run_latch);
    if (s_audio_run_latch == AUDIO_RUN_LATCH_MAGIC) {
        return false;
    }
    s_audio_run_latch = AUDIO_RUN_LATCH_MAGIC;
    return true;
}

typedef struct {
    uint32_t attempted_frames;
    uint32_t successful_frames;
    uint32_t frame_seq_gaps;
    uint32_t read_errors;
    uint32_t write_errors;
    uint64_t samples_per_channel;
    double sum_squares[AUDIO_CHANNELS];
    int32_t peak_abs[AUDIO_CHANNELS];
    uint64_t clipped[AUDIO_CHANNELS];
    uint64_t zero[AUDIO_CHANNELS];
    uint32_t processing_time_histogram[AUDIO_PROCESSING_BUCKETS];
} audio_metrics_t;

typedef enum {
    AUDIO_PHASE_OUTPUT_CHIRP,
    AUDIO_PHASE_INPUT_METRICS,
    AUDIO_PHASE_ATTENUATED_LOOP,
} audio_phase_t;

static const char *phase_name(audio_phase_t phase)
{
    switch (phase) {
    case AUDIO_PHASE_OUTPUT_CHIRP:
        return "output_chirp";
    case AUDIO_PHASE_INPUT_METRICS:
        return "input_metrics";
    case AUDIO_PHASE_ATTENUATED_LOOP:
        return "attenuated_local_loop";
    default:
        return "invalid";
    }
}

static uint32_t phase_seconds(audio_phase_t phase)
{
    switch (phase) {
    case AUDIO_PHASE_OUTPUT_CHIRP:
        return CONFIG_EGOLINK_AUDIO_OUTPUT_SECONDS;
    case AUDIO_PHASE_INPUT_METRICS:
        return CONFIG_EGOLINK_AUDIO_INPUT_SECONDS;
    case AUDIO_PHASE_ATTENUATED_LOOP:
        return CONFIG_EGOLINK_AUDIO_DUPLEX_SECONDS;
    default:
        return 0;
    }
}

static void fill_known_chirp(uint32_t frame_sequence)
{
    const double pi = 3.14159265358979323846;
    const double frequency_hz = 1000.0;
    const uint64_t first_sample =
        (uint64_t)frame_sequence * AUDIO_SAMPLES_PER_FRAME;
    for (uint32_t sample = 0; sample < AUDIO_SAMPLES_PER_FRAME; ++sample) {
        double phase = 2.0 * pi * frequency_hz *
                       (double)(first_sample + sample) /
                       (double)AUDIO_SAMPLE_RATE_HZ;
        int16_t value = (int16_t)(sin(phase) * AUDIO_CHIRP_AMPLITUDE);
        for (uint32_t channel = 0; channel < AUDIO_CHANNELS; ++channel) {
            s_audio_frame[sample * AUDIO_CHANNELS + channel] = value;
        }
    }
}

static void fill_output_diagnostic_tone(uint32_t frame_sequence)
{
    const double pi = 3.14159265358979323846;
    const uint64_t first_sample =
        (uint64_t)frame_sequence * AUDIO_SAMPLES_PER_FRAME;
    const uint64_t total_samples =
        (uint64_t)AUDIO_OUTPUT_DIAGNOSTIC_STAGE_SECONDS *
        AUDIO_SAMPLE_RATE_HZ;
    const uint32_t ramp_samples = AUDIO_SAMPLES_PER_FRAME;

    for (uint32_t sample = 0; sample < AUDIO_SAMPLES_PER_FRAME; ++sample) {
        const uint64_t absolute_sample = first_sample + sample;
        double envelope = 1.0;
        if (absolute_sample < ramp_samples) {
            envelope = (double)(absolute_sample + 1U) /
                (double)ramp_samples;
        } else if (absolute_sample >= total_samples - ramp_samples) {
            envelope = (double)(total_samples - absolute_sample) /
                (double)ramp_samples;
        }
        double phase = 2.0 * pi * AUDIO_OUTPUT_DIAGNOSTIC_FREQUENCY_HZ *
                       (double)absolute_sample /
                       (double)AUDIO_SAMPLE_RATE_HZ;
        int16_t value = (int16_t)(
            sin(phase) * AUDIO_OUTPUT_DIAGNOSTIC_PCM_PEAK * envelope);
        for (uint32_t channel = 0; channel < AUDIO_CHANNELS; ++channel) {
            s_audio_frame[sample * AUDIO_CHANNELS + channel] = value;
        }
    }
}

typedef struct {
    uint32_t attempted_frames;
    uint32_t successful_frames;
    uint32_t short_writes;
    uint32_t write_errors;
    uint64_t requested_bytes;
    uint64_t actual_bytes_written;
} output_diagnostic_metrics_t;

static esp_err_t output_diagnostic_countdown(
    esp_codec_dev_handle_t speaker)
{
    for (uint32_t remaining = AUDIO_OUTPUT_DIAGNOSTIC_COUNTDOWN_SECONDS;
         remaining > 0;
         --remaining) {
        if (s_audio_deadline_expired) {
            return ESP_ERR_TIMEOUT;
        }
        esp_err_t result = speaker_set_output_enabled(speaker, false);
        if (result != ESP_OK) {
            return result;
        }
        ESP_LOGI(
            TAG,
            "AUDIO_OUTPUT_COUNTDOWN remaining_seconds=%" PRIu32
            " speaker_muted=true speaker_pa_off_verified=true",
            remaining);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    return s_audio_deadline_expired ? ESP_ERR_TIMEOUT : ESP_OK;
}

static esp_err_t run_output_diagnostic_stage(
    call010_safe_audio_v1_t *audio,
    uint32_t stage_number,
    int volume)
{
    output_diagnostic_metrics_t metrics = {0};
    const uint32_t expected_frames =
        AUDIO_OUTPUT_DIAGNOSTIC_STAGE_SECONDS *
        (1000U / AUDIO_FRAME_MS);
    const size_t bytes_per_frame = sizeof(s_audio_frame);
    const uint64_t expected_bytes =
        (uint64_t)expected_frames * bytes_per_frame;
    const int expected_register = ES8311_VOLUME_REGISTER_BASE + volume;
    int actual_register = -1;

    esp_err_t result = set_output_diagnostic_volume_verified(
        audio->speaker, volume, &actual_register);
    if (result != ESP_OK) {
        pa_force_off();
        ESP_LOGE(
            TAG,
            "AUDIO_OUTPUT_STAGE_ABORT stage=%" PRIu32
            " volume=%d reason=volume_readback result=%s "
            "speaker_pa_off_verified=%s",
            stage_number, volume, esp_err_to_name(result),
            gpio_get_level(BSP_POWER_AMP_IO) == 0 ? "true" : "false");
        return result;
    }

    ESP_LOGI(
        TAG,
        "AUDIO_OUTPUT_STAGE_START stage=%" PRIu32
        " volume=%d expected_reg32=0x%02x actual_reg32=0x%02x "
        "frequency_hz=%d pcm_peak=%d seconds=%d expected_frames=%" PRIu32
        " bytes_per_frame=%u expected_bytes=%" PRIu64,
        stage_number, volume, expected_register, actual_register & 0xff,
        AUDIO_OUTPUT_DIAGNOSTIC_FREQUENCY_HZ,
        AUDIO_OUTPUT_DIAGNOSTIC_PCM_PEAK,
        AUDIO_OUTPUT_DIAGNOSTIC_STAGE_SECONDS, expected_frames,
        (unsigned)bytes_per_frame, expected_bytes);

    result = speaker_set_output_enabled(audio->speaker, true);
    if (result == ESP_OK) {
        for (uint32_t frame_sequence = 0;
             frame_sequence < expected_frames;
             ++frame_sequence) {
            if (s_audio_deadline_expired) {
                result = ESP_ERR_TIMEOUT;
                break;
            }
            fill_output_diagnostic_tone(frame_sequence);
            metrics.attempted_frames++;
            metrics.requested_bytes += bytes_per_frame;
            size_t bytes_written = 0;
            esp_err_t write_result = i2s_channel_write(
                audio->tx_channel,
                s_audio_frame,
                bytes_per_frame,
                &bytes_written,
                pdMS_TO_TICKS(1000));
            metrics.actual_bytes_written += bytes_written;
            if (write_result != ESP_OK) {
                metrics.write_errors++;
                result = write_result;
                break;
            }
            if (bytes_written != bytes_per_frame) {
                metrics.short_writes++;
                result = ESP_ERR_INVALID_SIZE;
                break;
            }
            metrics.successful_frames++;
        }
    }

    /* Mute/read back the codec and force/read back PA low before any result. */
    esp_err_t final_disable = speaker_set_output_enabled(audio->speaker, false);
    bool pa_off_verified = gpio_get_level(BSP_POWER_AMP_IO) == 0;
    if (result == ESP_OK && final_disable != ESP_OK) {
        result = final_disable;
    }
    clear_audio_frame();

    if (result == ESP_OK && final_disable == ESP_OK && pa_off_verified &&
        metrics.attempted_frames == expected_frames &&
        metrics.successful_frames == expected_frames &&
        metrics.requested_bytes == expected_bytes &&
        metrics.actual_bytes_written == expected_bytes &&
        metrics.short_writes == 0 && metrics.write_errors == 0) {
        ESP_LOGI(
            TAG,
            "AUDIO_OUTPUT_STAGE_END stage=%" PRIu32
            " volume=%d actual_reg32=0x%02x attempted_frames=%" PRIu32
            " successful_frames=%" PRIu32 " requested_bytes=%" PRIu64
            " actual_bytes_written=%" PRIu64
            " short_writes=%" PRIu32 " write_errors=%" PRIu32
            " speaker_muted=true speaker_pa_off_verified=true result=ESP_OK",
            stage_number, volume, actual_register & 0xff,
            metrics.attempted_frames, metrics.successful_frames,
            metrics.requested_bytes, metrics.actual_bytes_written,
            metrics.short_writes, metrics.write_errors);
        return ESP_OK;
    }

    if (result == ESP_OK) {
        result = ESP_FAIL;
    }
    pa_force_off();
    ESP_LOGE(
        TAG,
        "AUDIO_OUTPUT_STAGE_ABORT stage=%" PRIu32
        " volume=%d actual_reg32=0x%02x attempted_frames=%" PRIu32
        " successful_frames=%" PRIu32 " requested_bytes=%" PRIu64
        " actual_bytes_written=%" PRIu64
        " short_writes=%" PRIu32 " write_errors=%" PRIu32
        " final_disable_result=%s speaker_pa_off_verified=%s result=%s",
        stage_number, volume, actual_register & 0xff,
        metrics.attempted_frames, metrics.successful_frames,
        metrics.requested_bytes, metrics.actual_bytes_written,
        metrics.short_writes, metrics.write_errors,
        esp_err_to_name(final_disable),
        gpio_get_level(BSP_POWER_AMP_IO) == 0 ? "true" : "false",
        esp_err_to_name(result));
    return result;
}

static esp_err_t output_diagnostic_gap(
    esp_codec_dev_handle_t speaker, uint32_t completed_stage)
{
    esp_err_t result = speaker_set_output_enabled(speaker, false);
    if (result != ESP_OK) {
        return result;
    }
    ESP_LOGI(
        TAG,
        "AUDIO_OUTPUT_STAGE_GAP after_stage=%" PRIu32
        " seconds=%d speaker_muted=true speaker_pa_off_verified=true",
        completed_stage, AUDIO_OUTPUT_DIAGNOSTIC_GAP_SECONDS);
    for (uint32_t second = 0;
         second < AUDIO_OUTPUT_DIAGNOSTIC_GAP_SECONDS;
         ++second) {
        if (s_audio_deadline_expired) {
            return ESP_ERR_TIMEOUT;
        }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    return pa_force_off();
}

static void measure_input(audio_metrics_t *metrics)
{
    for (uint32_t sample = 0; sample < AUDIO_SAMPLES_PER_FRAME; ++sample) {
        for (uint32_t channel = 0; channel < AUDIO_CHANNELS; ++channel) {
            int32_t value = s_audio_frame[sample * AUDIO_CHANNELS + channel];
            int32_t absolute = value < 0 ? -value : value;
            metrics->sum_squares[channel] += (double)value * (double)value;
            if (absolute > metrics->peak_abs[channel]) {
                metrics->peak_abs[channel] = absolute;
            }
            if (absolute >= AUDIO_CLIP_THRESHOLD) {
                metrics->clipped[channel]++;
            }
            if (value == 0) {
                metrics->zero[channel]++;
            }
        }
        metrics->samples_per_channel++;
    }
}

static void attenuate_loop_frame(void)
{
    for (uint32_t index = 0; index < AUDIO_FRAME_VALUES; ++index) {
        s_audio_frame[index] = (int16_t)(s_audio_frame[index] / 16);
    }
}

static void record_processing_time(audio_metrics_t *metrics, int64_t processing_time_us)
{
    uint32_t bucket = processing_time_us <= 0 ? 0 :
        (uint32_t)(processing_time_us / AUDIO_PROCESSING_BUCKET_US);
    if (bucket >= AUDIO_PROCESSING_BUCKETS) {
        bucket = AUDIO_PROCESSING_BUCKETS - 1;
    }
    metrics->processing_time_histogram[bucket]++;
}

static uint32_t processing_time_percentile_us(
    const audio_metrics_t *metrics, uint32_t percentile)
{
    if (metrics->successful_frames == 0) {
        return 0;
    }
    uint32_t target =
        (metrics->successful_frames * percentile + 99U) / 100U;
    uint32_t seen = 0;
    for (uint32_t bucket = 0; bucket < AUDIO_PROCESSING_BUCKETS; ++bucket) {
        seen += metrics->processing_time_histogram[bucket];
        if (seen >= target) {
            return (bucket + 1U) * AUDIO_PROCESSING_BUCKET_US;
        }
    }
    return AUDIO_PROCESSING_BUCKETS * AUDIO_PROCESSING_BUCKET_US;
}

static void log_metrics(audio_phase_t phase, const audio_metrics_t *metrics)
{
    ESP_LOGI(
        TAG,
        "AUDIO_METRICS phase=%s attempted_frames=%" PRIu32
        " successful_frames=%" PRIu32 " frame_seq_gaps=%" PRIu32
        " read_errors=%" PRIu32 " write_errors=%" PRIu32
        " processing_time_p50_us=%" PRIu32
        " processing_time_p95_us=%" PRIu32,
        phase_name(phase), metrics->attempted_frames,
        metrics->successful_frames, metrics->frame_seq_gaps,
        metrics->read_errors, metrics->write_errors,
        processing_time_percentile_us(metrics, 50),
        processing_time_percentile_us(metrics, 95));

    for (uint32_t channel = 0; channel < AUDIO_CHANNELS; ++channel) {
        double rms = metrics->samples_per_channel == 0 ? 0.0 :
            sqrt(metrics->sum_squares[channel] /
                 (double)metrics->samples_per_channel);
        double clipped_ratio = metrics->samples_per_channel == 0 ? 0.0 :
            (double)metrics->clipped[channel] /
            (double)metrics->samples_per_channel;
        double zero_ratio = metrics->samples_per_channel == 0 ? 0.0 :
            (double)metrics->zero[channel] /
            (double)metrics->samples_per_channel;
        ESP_LOGI(
            TAG,
            "AUDIO_CHANNEL_METRICS phase=%s channel=%" PRIu32
            " rms=%.3f peak=%" PRId32 " clipped_ratio=%.6f zero_ratio=%.6f",
            phase_name(phase), channel, rms, metrics->peak_abs[channel],
            clipped_ratio, zero_ratio);
    }
}

static esp_err_t run_phase(
    audio_phase_t phase,
    esp_codec_dev_handle_t speaker,
    esp_codec_dev_handle_t microphone)
{
    audio_metrics_t metrics = {0};
    const uint32_t frame_count =
        phase_seconds(phase) * (1000U / AUDIO_FRAME_MS);
    esp_err_t overall = ESP_OK;

    bool output_enabled = phase != AUDIO_PHASE_INPUT_METRICS;
    esp_err_t mute_result = speaker_set_output_enabled(speaker, output_enabled);
    if (mute_result != ESP_OK) {
        ESP_LOGE(TAG, "phase=%s initial mute control failed: %s",
                 phase_name(phase), esp_err_to_name(mute_result));
        return mute_result;
    }

    ESP_LOGI(TAG, "AUDIO_PHASE_START phase=%s seconds=%" PRIu32,
             phase_name(phase), phase_seconds(phase));
    for (uint32_t frame_sequence = 0;
         frame_sequence < frame_count;
         ++frame_sequence) {
        if (s_audio_deadline_expired) {
            overall = ESP_ERR_TIMEOUT;
            break;
        }
        metrics.attempted_frames++;
        int64_t started_us = esp_timer_get_time();
        esp_err_t result = ESP_OK;

        if (phase == AUDIO_PHASE_OUTPUT_CHIRP) {
            fill_known_chirp(frame_sequence);
        } else {
            result = esp_codec_dev_read(
                microphone, s_audio_frame, sizeof(s_audio_frame));
            if (result != ESP_OK) {
                metrics.read_errors++;
            } else {
                measure_input(&metrics);
            }
        }

        if (result == ESP_OK && output_enabled) {
            if (phase == AUDIO_PHASE_ATTENUATED_LOOP) {
                attenuate_loop_frame();
            }
            result = esp_codec_dev_write(
                speaker, s_audio_frame, sizeof(s_audio_frame));
            if (result != ESP_OK) {
                metrics.write_errors++;
            }
        }

        if (result == ESP_OK) {
            metrics.successful_frames++;
            record_processing_time(&metrics, esp_timer_get_time() - started_us);
        } else {
            metrics.frame_seq_gaps++;
            overall = result;
            break;
        }
    }

    esp_err_t final_mute = speaker_set_output_enabled(speaker, false);
    if (final_mute != ESP_OK) {
        ESP_LOGE(TAG, "phase=%s final mute failed: %s",
                 phase_name(phase), esp_err_to_name(final_mute));
        overall = final_mute;
    }
    log_metrics(phase, &metrics);
    ESP_LOGI(TAG, "AUDIO_PHASE_END phase=%s result=%s",
             phase_name(phase), esp_err_to_name(overall));
    return overall;
}

static esp_err_t run_bounded_audio_sequence(void)
{
    esp_err_t result = pa_prepare_off();
    if (result != ESP_OK) {
        ESP_LOGE(TAG, "PA fail-closed setup failed: %s", esp_err_to_name(result));
        return result;
    }

    call010_safe_audio_v1_t audio = {0};
    result = call010_safe_audio_v1_init(&audio, AUDIO_SAMPLE_RATE_HZ);
    if (result != ESP_OK) {
        ESP_LOGE(
            TAG, "%s initialization failed: %s",
            call010_safe_audio_v1_version(), esp_err_to_name(result));
        pa_force_off();
        clear_audio_frame();
        return result;
    }
    esp_codec_dev_handle_t speaker = audio.speaker;
    esp_codec_dev_handle_t microphone = audio.microphone;

    esp_codec_dev_sample_info_t format = {
        .sample_rate = AUDIO_SAMPLE_RATE_HZ,
        .channel = AUDIO_CHANNELS,
        .bits_per_sample = AUDIO_BITS_PER_SAMPLE,
    };
    result = esp_codec_dev_open(speaker, &format);
    if (result != ESP_OK) {
        ESP_LOGE(TAG, "speaker open failed: %s", esp_err_to_name(result));
        goto cleanup;
    }
    result = speaker_set_output_enabled(speaker, false);
    if (result != ESP_OK) {
        ESP_LOGE(TAG, "initial speaker disable failed: %s", esp_err_to_name(result));
        goto cleanup;
    }

    result = esp_codec_dev_open(microphone, &format);
    if (result != ESP_OK) {
        ESP_LOGE(TAG, "microphone open failed: %s", esp_err_to_name(result));
        goto cleanup;
    }

    result = set_safe_output_volume_verified(speaker);
    if (result == ESP_OK) {
        result = esp_codec_dev_set_in_gain(microphone, 24.0f);
    }

    const audio_phase_t phases[] = {
        AUDIO_PHASE_OUTPUT_CHIRP,
        AUDIO_PHASE_INPUT_METRICS,
        AUDIO_PHASE_ATTENUATED_LOOP,
    };
    for (uint32_t index = 0;
         result == ESP_OK && index < sizeof(phases) / sizeof(phases[0]);
         ++index) {
        result = run_phase(phases[index], speaker, microphone);
    }

cleanup:
    esp_err_t final_disable = speaker_set_output_enabled(speaker, false);
    esp_err_t audio_deinit = call010_safe_audio_v1_deinit(&audio);
    esp_err_t final_pa_off = pa_force_off();
    clear_audio_frame();
    if (result == ESP_OK) {
        result = final_disable;
    }
    if (result == ESP_OK) {
        result = audio_deinit;
    }
    if (result == ESP_OK) {
        result = final_pa_off;
    }
    return result;
}

static esp_err_t run_bounded_output_diagnostic(void)
{
    static const int stage_volumes[AUDIO_OUTPUT_DIAGNOSTIC_STAGE_COUNT] = {
        AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_1,
        AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_2,
        AUDIO_OUTPUT_DIAGNOSTIC_VOLUME_3,
    };
    uint32_t completed_stages = 0;
    esp_err_t result = pa_prepare_off();
    if (result != ESP_OK) {
        return result;
    }

    call010_safe_audio_v1_t audio = {0};
    result = call010_safe_audio_v1_init_output_only(
        &audio, AUDIO_SAMPLE_RATE_HZ);
    if (result != ESP_OK) {
        ESP_LOGE(
            TAG, "output-only %s initialization failed: %s",
            call010_safe_audio_v1_version(), esp_err_to_name(result));
        pa_force_off();
        clear_audio_frame();
        return result;
    }
    esp_codec_dev_handle_t speaker = audio.speaker;

    if (audio.microphone != NULL || audio.rx_channel != NULL ||
        audio.microphone_codec_if != NULL ||
        audio.microphone_ctrl_if != NULL) {
        ESP_LOGE(TAG, "output-only initializer unexpectedly created input resources");
        result = ESP_ERR_INVALID_STATE;
        goto cleanup;
    }

    esp_codec_dev_sample_info_t format = {
        .sample_rate = AUDIO_SAMPLE_RATE_HZ,
        .channel = AUDIO_CHANNELS,
        .bits_per_sample = AUDIO_BITS_PER_SAMPLE,
    };
    result = open_output_diagnostic_codec_prearmed(&audio, &format);
    if (result != ESP_OK) {
        ESP_LOGE(TAG, "output-only speaker open failed: %s", esp_err_to_name(result));
        goto cleanup;
    }
    result = speaker_set_output_enabled(speaker, false);
    if (result != ESP_OK) {
        ESP_LOGE(TAG, "output-only initial speaker disable failed: %s",
                 esp_err_to_name(result));
        goto cleanup;
    }

    ESP_LOGI(
        TAG,
        "AUDIO_OUTPUT_DIAGNOSTIC_ARMED countdown_seconds=%d stage_count=%d "
        "microphone_constructed=false rx_channel_created=false "
        "no_audio_storage=true",
        AUDIO_OUTPUT_DIAGNOSTIC_COUNTDOWN_SECONDS,
        AUDIO_OUTPUT_DIAGNOSTIC_STAGE_COUNT);
    result = output_diagnostic_countdown(speaker);

    for (uint32_t index = 0;
         result == ESP_OK && index < AUDIO_OUTPUT_DIAGNOSTIC_STAGE_COUNT;
         ++index) {
        result = run_output_diagnostic_stage(
            &audio, index + 1U, stage_volumes[index]);
        if (result != ESP_OK) {
            break;
        }
        completed_stages++;
        if (index + 1U < AUDIO_OUTPUT_DIAGNOSTIC_STAGE_COUNT) {
            result = output_diagnostic_gap(speaker, index + 1U);
        }
    }

cleanup:
    {
        esp_err_t final_disable = speaker_set_output_enabled(speaker, false);
        esp_err_t audio_deinit = call010_safe_audio_v1_deinit(&audio);
        esp_err_t final_pa_off = pa_force_off();
        clear_audio_frame();
        if (result == ESP_OK) {
            result = final_disable;
        }
        if (result == ESP_OK) {
            result = audio_deinit;
        }
        if (result == ESP_OK) {
            result = final_pa_off;
        }
    }
    bool pa_off_verified = gpio_get_level(BSP_POWER_AMP_IO) == 0;
    if (!pa_off_verified && result == ESP_OK) {
        result = ESP_FAIL;
    }
    ESP_LOGI(
        TAG,
        "AUDIO_OUTPUT_DIAGNOSTIC_COMPLETE result=%s completed_stages=%" PRIu32
        " microphone_reads=0 raw_audio_retained=false "
        "speaker_pa_off_verified=%s deadline_expired=%s",
        esp_err_to_name(result), completed_stages,
        pa_off_verified ? "true" : "false",
        s_audio_deadline_expired ? "true" : "false");
    return result;
}

void app_main(void)
{
    esp_err_t startup_pa_off = pa_prepare_off();
    if (startup_pa_off != ESP_OK) {
        ESP_LOGE(
            TAG, "startup PA fail-closed setup failed: %s",
            esp_err_to_name(startup_pa_off));
        return;
    }

    ESP_LOGI(
        TAG,
        "CALL-010 static candidate declared_board_family=wearable-node-001 "
        "board_source_status=repository_mapping physical_revision=unknown "
        "bsp=waveshare/esp32_s3_touch_amoled_2_06@1.0.3 "
        "audio_initializer=%s autorun=%d output_diagnostic=%d "
        "no_audio_storage=true",
        call010_safe_audio_v1_version(), CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN,
        CONFIG_EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC);

    if (!CONFIG_EGOLINK_AUDIO_LOOP_AUTORUN) {
        s_audio_run_latch = 0;
        ESP_LOGI(
            TAG,
            "DORMANT_LATCH_CLEARED value=0x%08" PRIx32
            " speaker_pa_off_verified=true",
            s_audio_run_latch);
        ESP_LOGW(
            TAG,
            "bounded audio sequence disabled; explicit operator-approved "
            "hardware task and autorun build are required");
        return;
    }

    if (!claim_one_run_per_power_cycle()) {
        pa_prepare_off();
        ESP_LOGE(
            TAG,
            "audio sequence refused: one-run-per-power-cycle latch already set");
        return;
    }

    s_audio_deadline_expired = false;
    esp_timer_handle_t deadline_timer = NULL;
    const esp_timer_create_args_t deadline_args = {
        .callback = audio_deadline_callback,
        .name = "call010_deadline",
    };
    esp_err_t timer_result = esp_timer_create(&deadline_args, &deadline_timer);
    if (timer_result == ESP_OK) {
        uint64_t deadline_seconds = CONFIG_EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC
            ? AUDIO_OUTPUT_DIAGNOSTIC_DEADLINE_SECONDS
            : (uint64_t)CONFIG_EGOLINK_AUDIO_OUTPUT_SECONDS +
              (uint64_t)CONFIG_EGOLINK_AUDIO_INPUT_SECONDS +
              (uint64_t)CONFIG_EGOLINK_AUDIO_DUPLEX_SECONDS +
              AUDIO_DEADLINE_MARGIN_SECONDS;
        uint64_t deadline_us = deadline_seconds * UINT64_C(1000000);
        timer_result = esp_timer_start_once(deadline_timer, deadline_us);
    }
    if (timer_result != ESP_OK) {
        pa_prepare_off();
        if (deadline_timer != NULL) {
            esp_timer_delete(deadline_timer);
        }
        ESP_LOGE(TAG, "audio deadline setup failed: %s", esp_err_to_name(timer_result));
        return;
    }

    esp_err_t result = CONFIG_EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC
        ? run_bounded_output_diagnostic()
        : run_bounded_audio_sequence();
    esp_timer_stop(deadline_timer);
    esp_timer_delete(deadline_timer);
    esp_err_t final_pa_off = pa_force_off();
    bool pa_off_verified = final_pa_off == ESP_OK;
    if (!pa_off_verified && result == ESP_OK) {
        result = final_pa_off;
    }
    ESP_LOGI(
        TAG,
        "AUDIO_SEQUENCE_COMPLETE result=%s speaker_pa_off_verified=%s "
        "deadline_expired=%s mode=%s",
        esp_err_to_name(result), pa_off_verified ? "true" : "false",
        s_audio_deadline_expired ? "true" : "false",
        CONFIG_EGOLINK_AUDIO_OUTPUT_DIAGNOSTIC
            ? "output_diagnostic"
            : "full_audio_loop");
}

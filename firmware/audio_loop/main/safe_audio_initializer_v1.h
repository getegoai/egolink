/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef CALL010_SAFE_AUDIO_INITIALIZER_V1_H
#define CALL010_SAFE_AUDIO_INITIALIZER_V1_H

#include <stdbool.h>
#include <stdint.h>

#include "audio_codec_ctrl_if.h"
#include "audio_codec_data_if.h"
#include "audio_codec_if.h"
#include "driver/i2s_std.h"
#include "esp_codec_dev.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define CALL010_SAFE_AUDIO_INITIALIZER_VERSION "call010-safe-audio-init-v1"

/*
 * Caller-owned, single-instance resources for the isolated CALL-010 target.
 * The PA GPIO is intentionally absent: only app_main owns BSP_POWER_AMP_IO.
 */
typedef struct {
    esp_codec_dev_handle_t speaker;
    esp_codec_dev_handle_t microphone;
    const audio_codec_if_t *speaker_codec_if;
    const audio_codec_if_t *microphone_codec_if;
    const audio_codec_ctrl_if_t *speaker_ctrl_if;
    const audio_codec_ctrl_if_t *microphone_ctrl_if;
    const audio_codec_data_if_t *shared_i2s_data_if;
    i2s_chan_handle_t tx_channel;
    i2s_chan_handle_t rx_channel;
    bool bsp_i2c_acquired;
} call010_safe_audio_v1_t;

const char *call010_safe_audio_v1_version(void);

/*
 * Constructs a shared full-duplex I2S data path, ES8311 output with pa_pin=-1,
 * and ES7210 MIC1/MIC2 input. It never configures or drives the PA GPIO.
 */
esp_err_t call010_safe_audio_v1_init(
    call010_safe_audio_v1_t *context, uint32_t sample_rate_hz);

/*
 * Output-only diagnostic variant. It creates only the TX channel and ES8311
 * speaker path; no RX channel, ES7210 control interface, microphone codec, or
 * microphone device is constructed.
 */
esp_err_t call010_safe_audio_v1_init_output_only(
    call010_safe_audio_v1_t *context, uint32_t sample_rate_hz);

/*
 * Closes and frees every resource that was successfully acquired. It is safe
 * to call for a partially initialized or already-deinitialized context.
 */
esp_err_t call010_safe_audio_v1_deinit(call010_safe_audio_v1_t *context);

#ifdef __cplusplus
}
#endif

#endif

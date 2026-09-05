/*
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Local CALL-010 audio construction. This deliberately does not call the BSP
 * audio codec constructors because the pinned ES8311 BSP path passes the PA
 * GPIO to the codec constructor, which can enable the amplifier too early.
 */

#include "safe_audio_initializer_v1.h"

#include <string.h>

#include "bsp/esp-bsp.h"
#include "esp_codec_dev_defaults.h"

static esp_err_t preserve_first_error(esp_err_t current, int candidate)
{
    return current == ESP_OK && candidate != ESP_CODEC_DEV_OK
        ? (esp_err_t)candidate
        : current;
}

static esp_err_t disable_and_delete_channel(i2s_chan_handle_t *channel)
{
    if (channel == NULL || *channel == NULL) {
        return ESP_OK;
    }

    /*
     * Codec-device close owns channel disable. If initialization failed before
     * a codec device opened, the channel was never enabled. Calling disable a
     * second time emits a false hardware error even though deletion is safe.
     */
    esp_err_t result = i2s_del_channel(*channel);
    if (result == ESP_OK) {
        *channel = NULL;
    }
    return result;
}

const char *call010_safe_audio_v1_version(void)
{
    return CALL010_SAFE_AUDIO_INITIALIZER_VERSION;
}

esp_err_t call010_safe_audio_v1_deinit(call010_safe_audio_v1_t *context)
{
    if (context == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t result = ESP_OK;

    if (context->microphone != NULL) {
        result = preserve_first_error(
            result, esp_codec_dev_close(context->microphone));
        esp_codec_dev_delete(context->microphone);
        context->microphone = NULL;
    }
    if (context->speaker != NULL) {
        result = preserve_first_error(
            result, esp_codec_dev_close(context->speaker));
        esp_codec_dev_delete(context->speaker);
        context->speaker = NULL;
    }

    if (context->microphone_codec_if != NULL) {
        result = preserve_first_error(
            result, audio_codec_delete_codec_if(context->microphone_codec_if));
        context->microphone_codec_if = NULL;
    }
    if (context->speaker_codec_if != NULL) {
        result = preserve_first_error(
            result, audio_codec_delete_codec_if(context->speaker_codec_if));
        context->speaker_codec_if = NULL;
    }
    if (context->microphone_ctrl_if != NULL) {
        result = preserve_first_error(
            result, audio_codec_delete_ctrl_if(context->microphone_ctrl_if));
        context->microphone_ctrl_if = NULL;
    }
    if (context->speaker_ctrl_if != NULL) {
        result = preserve_first_error(
            result, audio_codec_delete_ctrl_if(context->speaker_ctrl_if));
        context->speaker_ctrl_if = NULL;
    }
    if (context->shared_i2s_data_if != NULL) {
        result = preserve_first_error(
            result, audio_codec_delete_data_if(context->shared_i2s_data_if));
        context->shared_i2s_data_if = NULL;
    }

    result = preserve_first_error(
        result, disable_and_delete_channel(&context->rx_channel));
    result = preserve_first_error(
        result, disable_and_delete_channel(&context->tx_channel));

    if (context->bsp_i2c_acquired) {
        esp_err_t i2c_result = bsp_i2c_deinit();
        if (i2c_result == ESP_OK) {
            context->bsp_i2c_acquired = false;
        }
        result = preserve_first_error(result, i2c_result);
    }
    return result;
}

static esp_err_t call010_safe_audio_v1_init_internal(
    call010_safe_audio_v1_t *context,
    uint32_t sample_rate_hz,
    bool include_microphone)
{
    if (context == NULL || sample_rate_hz == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(context, 0, sizeof(*context));

    esp_err_t result = bsp_i2c_init();
    if (result != ESP_OK) {
        return result;
    }
    context->bsp_i2c_acquired = true;

    i2s_chan_config_t channel_config = I2S_CHANNEL_DEFAULT_CONFIG(
        CONFIG_BSP_I2S_NUM, I2S_ROLE_MASTER);
    channel_config.auto_clear = true;
    i2s_chan_handle_t *rx_channel = include_microphone
        ? &context->rx_channel
        : NULL;
    result = i2s_new_channel(
        &channel_config, &context->tx_channel, rx_channel);
    if (result != ESP_OK) {
        goto fail;
    }

    const i2s_std_config_t i2s_config = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(sample_rate_hz),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(
            I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = BSP_I2S_MCLK,
            .bclk = BSP_I2S_SCLK,
            .ws = BSP_I2S_LCLK,
            .dout = BSP_I2S_DOUT,
            .din = include_microphone ? BSP_I2S_DSIN : I2S_GPIO_UNUSED,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv = false,
            },
        },
    };
    result = i2s_channel_init_std_mode(context->tx_channel, &i2s_config);
    if (result != ESP_OK) {
        goto fail;
    }
    if (include_microphone) {
        result = i2s_channel_init_std_mode(context->rx_channel, &i2s_config);
        if (result != ESP_OK) {
            goto fail;
        }
    }

    audio_codec_i2s_cfg_t data_config = {
        .port = CONFIG_BSP_I2S_NUM,
        .rx_handle = context->rx_channel,
        .tx_handle = context->tx_channel,
    };
    context->shared_i2s_data_if = audio_codec_new_i2s_data(&data_config);
    if (context->shared_i2s_data_if == NULL) {
        result = ESP_ERR_NO_MEM;
        goto fail;
    }

    i2c_master_bus_handle_t i2c_handle = bsp_i2c_get_handle();
    if (i2c_handle == NULL) {
        result = ESP_FAIL;
        goto fail;
    }
    audio_codec_i2c_cfg_t speaker_i2c_config = {
        .port = BSP_I2C_NUM,
        .addr = ES8311_CODEC_DEFAULT_ADDR,
        .bus_handle = i2c_handle,
    };
    context->speaker_ctrl_if = audio_codec_new_i2c_ctrl(&speaker_i2c_config);
    if (context->speaker_ctrl_if == NULL) {
        result = ESP_FAIL;
        goto fail;
    }
    if (include_microphone) {
        audio_codec_i2c_cfg_t microphone_i2c_config = {
            .port = BSP_I2C_NUM,
            .addr = ES7210_CODEC_DEFAULT_ADDR,
            .bus_handle = i2c_handle,
        };
        context->microphone_ctrl_if = audio_codec_new_i2c_ctrl(
            &microphone_i2c_config);
        if (context->microphone_ctrl_if == NULL) {
            result = ESP_FAIL;
            goto fail;
        }
    }

    const esp_codec_dev_hw_gain_t speaker_gain = {
        .pa_voltage = 5.0,
        .codec_dac_voltage = 3.3,
    };
    es8311_codec_cfg_t speaker_codec_config = {
        .ctrl_if = context->speaker_ctrl_if,
        .gpio_if = NULL,
        .codec_mode = ESP_CODEC_DEV_WORK_MODE_DAC,
        .pa_pin = -1,
        .pa_reverted = false,
        .master_mode = false,
        .use_mclk = true,
        .digital_mic = false,
        .invert_mclk = false,
        .invert_sclk = false,
        .hw_gain = speaker_gain,
    };
    context->speaker_codec_if = es8311_codec_new(&speaker_codec_config);
    if (context->speaker_codec_if == NULL) {
        result = ESP_FAIL;
        goto fail;
    }

    if (include_microphone) {
        es7210_codec_cfg_t microphone_codec_config = {
            .ctrl_if = context->microphone_ctrl_if,
            .master_mode = false,
            .mic_selected = ES7120_SEL_MIC1 | ES7120_SEL_MIC2,
            .mclk_src = ES7210_MCLK_FROM_PAD,
        };
        context->microphone_codec_if = es7210_codec_new(
            &microphone_codec_config);
        if (context->microphone_codec_if == NULL) {
            result = ESP_FAIL;
            goto fail;
        }
    }

    esp_codec_dev_cfg_t speaker_device_config = {
        .dev_type = ESP_CODEC_DEV_TYPE_OUT,
        .codec_if = context->speaker_codec_if,
        .data_if = context->shared_i2s_data_if,
    };
    context->speaker = esp_codec_dev_new(&speaker_device_config);
    if (context->speaker == NULL) {
        result = ESP_ERR_NO_MEM;
        goto fail;
    }
    if (include_microphone) {
        esp_codec_dev_cfg_t microphone_device_config = {
            .dev_type = ESP_CODEC_DEV_TYPE_IN,
            .codec_if = context->microphone_codec_if,
            .data_if = context->shared_i2s_data_if,
        };
        context->microphone = esp_codec_dev_new(&microphone_device_config);
        if (context->microphone == NULL) {
            result = ESP_ERR_NO_MEM;
            goto fail;
        }
    }
    return ESP_OK;

fail:
    call010_safe_audio_v1_deinit(context);
    return result;
}

esp_err_t call010_safe_audio_v1_init(
    call010_safe_audio_v1_t *context, uint32_t sample_rate_hz)
{
    return call010_safe_audio_v1_init_internal(
        context, sample_rate_hz, true);
}

esp_err_t call010_safe_audio_v1_init_output_only(
    call010_safe_audio_v1_t *context, uint32_t sample_rate_hz)
{
    return call010_safe_audio_v1_init_internal(
        context, sample_rate_hz, false);
}

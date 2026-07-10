#include "safety_model.h"

#include <float.h>
#include <math.h>
#include <stddef.h>

#include "tiny_safety_model.h"

#define SAFETY_MODEL_TINY_HARNESS_VERSION "tiny-safety-fw-harness-0.1.0"

static float clamp01(float value)
{
    if (value < 0.0f) {
        return 0.0f;
    }
    if (value > 1.0f) {
        return 1.0f;
    }
    return value;
}

static float bool_feature(bool value)
{
    return value ? 1.0f : 0.0f;
}

static void fill_safety_rule_required(safety_model_tiny_result_t *result)
{
    result->class_index = SAFETY_MODEL_TINY_SAFETY_RULE_CLASS_INDEX;
    result->state_label = "safety_rule_required";
    result->confidence = 1.0f;
    result->raw_score = 0.0f;
    result->score_margin = 0.0f;
    result->synthetic_only = true;
    result->safety_rule_required = true;
}

const char *safety_model_tiny_harness_version(void)
{
    return SAFETY_MODEL_TINY_HARNESS_VERSION;
}

const char *safety_model_tiny_model_id(void)
{
    return EGO_TINY_SAFETY_MODEL_ID;
}

const char *safety_model_tiny_model_version(void)
{
    return EGO_TINY_SAFETY_MODEL_VERSION;
}

uint8_t safety_model_tiny_feature_count(void)
{
    return (uint8_t)EGO_TINY_SAFETY_FEATURE_COUNT;
}

uint8_t safety_model_tiny_class_count(void)
{
    return (uint8_t)EGO_TINY_SAFETY_CLASS_COUNT;
}

bool safety_model_tiny_features_from_input(
    const ego_sc_model_input_t *input,
    float *features,
    uint8_t feature_count)
{
    if (input == NULL || features == NULL || feature_count < EGO_TINY_SAFETY_FEATURE_COUNT) {
        return false;
    }

    features[0] = clamp01(input->impact_score);
    features[1] = clamp01(input->fall_score);
    features[2] = clamp01(input->stationary_seconds / 120.0f);
    features[3] = clamp01(input->activity_confidence);
    features[4] = input->device_worn == 1 ? 1.0f : 0.0f;
    features[5] = clamp01(input->distress_score);
    features[6] = clamp01(input->impact_sound_score);
    features[7] = clamp01(input->unknown_loud_sound_score);
    features[8] = bool_feature(input->outside_safe_zone);
    features[9] = clamp01(input->dwell_seconds / 1800.0f);
    features[10] = clamp01(input->connectivity_score);
    features[11] = clamp01(input->offline_seconds / 1800.0f);
    features[12] = clamp01((100.0f - input->battery_percent) / 100.0f);
    features[13] = clamp01((float)input->recent_risk_count_5m / 5.0f);
    return true;
}

bool safety_model_tiny_predict_features(
    const float *features,
    uint8_t feature_count,
    safety_model_tiny_result_t *result)
{
    if (features == NULL || result == NULL || feature_count != EGO_TINY_SAFETY_FEATURE_COUNT) {
        return false;
    }

    float raw_scores[EGO_TINY_SAFETY_CLASS_COUNT];
    float best_score = -FLT_MAX;
    float second_score = -FLT_MAX;
    uint8_t best_index = 0;

    for (uint8_t class_index = 0; class_index < EGO_TINY_SAFETY_CLASS_COUNT; ++class_index) {
        float score = ego_tiny_safety_biases[class_index];
        for (uint8_t feature_index = 0; feature_index < EGO_TINY_SAFETY_FEATURE_COUNT; ++feature_index) {
            score += ego_tiny_safety_weights[class_index][feature_index] * clamp01(features[feature_index]);
        }
        raw_scores[class_index] = score;
        if (score > best_score) {
            second_score = best_score;
            best_score = score;
            best_index = class_index;
        } else if (score > second_score) {
            second_score = score;
        }
    }

    float peak = raw_scores[best_index];
    float probability_sum = 0.0f;
    for (uint8_t class_index = 0; class_index < EGO_TINY_SAFETY_CLASS_COUNT; ++class_index) {
        probability_sum += expf(raw_scores[class_index] - peak);
    }

    result->class_index = best_index;
    result->state_label = ego_tiny_safety_state_labels[best_index];
    result->confidence = probability_sum > 0.0f ? 1.0f / probability_sum : 0.0f;
    result->raw_score = best_score;
    result->score_margin = best_score - second_score;
    result->synthetic_only = true;
    result->safety_rule_required = false;
    return true;
}

bool safety_model_tiny_predict_input(
    const ego_sc_model_input_t *input,
    safety_model_tiny_result_t *result)
{
    if (input == NULL || result == NULL) {
        return false;
    }
    if (input->sos_pressed || input->cancel_pressed) {
        fill_safety_rule_required(result);
        return true;
    }

    float features[EGO_TINY_SAFETY_FEATURE_COUNT];
    if (!safety_model_tiny_features_from_input(input, features, EGO_TINY_SAFETY_FEATURE_COUNT)) {
        return false;
    }
    return safety_model_tiny_predict_features(features, EGO_TINY_SAFETY_FEATURE_COUNT, result);
}

bool safety_model_tiny_self_test(safety_model_tiny_self_test_result_t *result)
{
    if (result == NULL) {
        return false;
    }

    result->vector_count = (uint8_t)EGO_TINY_SAFETY_TEST_VECTOR_COUNT;
    result->passed_count = 0;
    result->failed_count = 0;
    result->first_failed_index = SAFETY_MODEL_TINY_SAFETY_RULE_CLASS_INDEX;

    for (uint8_t index = 0; index < EGO_TINY_SAFETY_TEST_VECTOR_COUNT; ++index) {
        safety_model_tiny_result_t prediction;
        bool ok = safety_model_tiny_predict_features(
            ego_tiny_safety_test_features[index],
            EGO_TINY_SAFETY_FEATURE_COUNT,
            &prediction);
        if (ok && prediction.class_index == ego_tiny_safety_test_expected[index]) {
            result->passed_count++;
        } else {
            if (result->failed_count == 0) {
                result->first_failed_index = index;
            }
            result->failed_count++;
        }
    }

    return result->failed_count == 0;
}

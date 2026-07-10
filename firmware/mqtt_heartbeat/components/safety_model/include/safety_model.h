#ifndef EGOLINK_SAFETY_MODEL_H
#define EGOLINK_SAFETY_MODEL_H

#include <stdbool.h>
#include <stdint.h>

#include "safety_model_contract.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SAFETY_MODEL_REASON_USER_CANCELLED 100u
#define SAFETY_MODEL_REASON_NO_RISK_SIGNAL 101u
#define SAFETY_MODEL_REASON_MANUAL_SOS 200u
#define SAFETY_MODEL_REASON_SAFETY_OVERRIDE 201u
#define SAFETY_MODEL_REASON_IMPACT_DETECTED 300u
#define SAFETY_MODEL_REASON_POST_IMPACT_STATIONARY 301u
#define SAFETY_MODEL_REASON_LOW_BATTERY 400u
#define SAFETY_MODEL_REASON_NETWORK_OFFLINE 500u

#define SAFETY_MODEL_TINY_SAFETY_RULE_CLASS_INDEX 255u

typedef struct {
    ego_sc_mode_t mode;
    bool sos_pressed;
    bool cancel_pressed;
    bool wake_detected;
    bool impact_detected;
    bool gnss_fix_valid;
    bool base_online;
    bool upload_available;
    uint8_t signal_level;
    float offline_seconds;
    float battery_percent;
    bool charging;
    bool privacy_mode;
    bool camera_available;
    bool microphone_available;
} safety_model_mock_state_t;

typedef struct {
    uint8_t class_index;
    const char *state_label;
    float confidence;
    float raw_score;
    float score_margin;
    bool synthetic_only;
    bool safety_rule_required;
} safety_model_tiny_result_t;

typedef struct {
    uint8_t vector_count;
    uint8_t passed_count;
    uint8_t failed_count;
    uint8_t first_failed_index;
} safety_model_tiny_self_test_result_t;

bool safety_model_init(void);
bool safety_model_evaluate(
    const ego_sc_model_input_t *input,
    ego_sc_model_output_t *output);
const char *safety_model_version(void);

bool safety_model_input_from_mock_state(
    const safety_model_mock_state_t *state,
    ego_sc_model_input_t *input);

const char *safety_model_risk_type_name(ego_sc_risk_type_t risk_type);
const char *safety_model_action_name(ego_sc_action_t action);

const char *safety_model_tiny_harness_version(void);
const char *safety_model_tiny_model_id(void);
const char *safety_model_tiny_model_version(void);
uint8_t safety_model_tiny_feature_count(void);
uint8_t safety_model_tiny_class_count(void);
bool safety_model_tiny_features_from_input(
    const ego_sc_model_input_t *input,
    float *features,
    uint8_t feature_count);
bool safety_model_tiny_predict_features(
    const float *features,
    uint8_t feature_count,
    safety_model_tiny_result_t *result);
bool safety_model_tiny_predict_input(
    const ego_sc_model_input_t *input,
    safety_model_tiny_result_t *result);
bool safety_model_tiny_self_test(safety_model_tiny_self_test_result_t *result);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SAFETY_MODEL_H */

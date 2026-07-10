#include "safety_model.h"

#include <stddef.h>
#include <string.h>

#define SAFETY_MODEL_MOCK_VERSION "safety-model-mock-0.1.0"
#define SAFETY_MODEL_DECISION_TTL_MS 30000u

static bool s_initialized;

static void reset_output(ego_sc_model_output_t *output)
{
    memset(output, 0, sizeof(*output));
    output->risk_type = EGO_SC_RISK_NONE;
    output->risk_score = 0.0f;
    output->confidence = 0.9f;
    output->priority = EGO_SC_PRIORITY_INFO;
    output->recommended_action = EGO_SC_ACTION_IGNORE;
    output->requires_base = false;
    output->evidence_mask = EGO_SC_EVIDENCE_NONE;
    output->safety_rule_applied = false;
    output->decision_ttl_ms = SAFETY_MODEL_DECISION_TTL_MS;
}

static void add_reason(ego_sc_model_output_t *output, uint16_t reason)
{
    if (output->reason_count < EGO_SC_REASON_CAPACITY) {
        output->reason_codes[output->reason_count] = reason;
        output->reason_count++;
    }
}

static uint32_t apply_evidence_policy(const ego_sc_model_input_t *input, uint32_t mask)
{
    if (input->privacy_mode || !input->microphone_available) {
        mask &= ~((uint32_t)EGO_SC_EVIDENCE_AUDIO_5S);
    }
    if (input->privacy_mode || !input->camera_available) {
        mask &= ~((uint32_t)EGO_SC_EVIDENCE_IMAGE_SINGLE);
    }
    return mask;
}

static void set_none_result(ego_sc_model_output_t *output, uint16_t reason)
{
    reset_output(output);
    add_reason(output, reason);
}

bool safety_model_init(void)
{
    s_initialized = true;
    return true;
}

bool safety_model_evaluate(const ego_sc_model_input_t *input, ego_sc_model_output_t *output)
{
    if (input == NULL || output == NULL) {
        return false;
    }
    if (!s_initialized && !safety_model_init()) {
        return false;
    }

    if (input->cancel_pressed && !input->sos_pressed) {
        set_none_result(output, SAFETY_MODEL_REASON_USER_CANCELLED);
        output->confidence = 1.0f;
        output->safety_rule_applied = true;
        return true;
    }

    if (input->sos_pressed) {
        reset_output(output);
        output->risk_type = EGO_SC_RISK_MANUAL_SOS;
        output->risk_score = 1.0f;
        output->confidence = 1.0f;
        output->priority = EGO_SC_PRIORITY_CRITICAL;
        output->recommended_action = EGO_SC_ACTION_URGENT_ESCALATION;
        output->requires_base = true;
        output->evidence_mask = EGO_SC_EVIDENCE_GNSS_REFRESH | EGO_SC_EVIDENCE_USER_CONFIRMATION;
        output->safety_rule_applied = true;
        add_reason(output, SAFETY_MODEL_REASON_MANUAL_SOS);
        add_reason(output, SAFETY_MODEL_REASON_SAFETY_OVERRIDE);
        return true;
    }

    if (input->impact_score >= 0.90f && input->stationary_seconds >= 15.0f) {
        reset_output(output);
        output->risk_type = EGO_SC_RISK_POST_IMPACT_INACTIVITY;
        output->risk_score = 0.86f;
        output->confidence = input->impact_score;
        output->priority = input->stationary_seconds >= 45.0f ? EGO_SC_PRIORITY_CRITICAL : EGO_SC_PRIORITY_HIGH;
        output->recommended_action =
            input->stationary_seconds >= 45.0f ? EGO_SC_ACTION_URGENT_ESCALATION : EGO_SC_ACTION_ASK_USER;
        output->requires_base = true;
        output->evidence_mask = apply_evidence_policy(
            input,
            EGO_SC_EVIDENCE_USER_CONFIRMATION | EGO_SC_EVIDENCE_GNSS_REFRESH |
                EGO_SC_EVIDENCE_IMU_10S | EGO_SC_EVIDENCE_AUDIO_5S | EGO_SC_EVIDENCE_IMAGE_SINGLE);
        output->safety_rule_applied = output->priority == EGO_SC_PRIORITY_CRITICAL;
        add_reason(output, SAFETY_MODEL_REASON_IMPACT_DETECTED);
        add_reason(output, SAFETY_MODEL_REASON_POST_IMPACT_STATIONARY);
        return true;
    }

    if (input->battery_percent <= 10.0f && !input->charging) {
        reset_output(output);
        output->risk_type = EGO_SC_RISK_LOW_BATTERY;
        output->risk_score = 0.95f;
        output->confidence = 1.0f;
        output->priority = EGO_SC_PRIORITY_CRITICAL;
        output->recommended_action =
            input->upload_available ? EGO_SC_ACTION_SEND_SUMMARY : EGO_SC_ACTION_LOCAL_PROMPT;
        output->requires_base = input->upload_available;
        output->safety_rule_applied = true;
        add_reason(output, SAFETY_MODEL_REASON_LOW_BATTERY);
        return true;
    }

    if (!input->base_online && input->offline_seconds >= 900.0f) {
        reset_output(output);
        output->risk_type = EGO_SC_RISK_COMMUNICATION_LOSS;
        output->risk_score = 0.85f;
        output->confidence = 1.0f - input->connectivity_score;
        output->priority = EGO_SC_PRIORITY_HIGH;
        output->recommended_action = EGO_SC_ACTION_LOCAL_PROMPT;
        output->requires_base = false;
        output->safety_rule_applied = true;
        add_reason(output, SAFETY_MODEL_REASON_NETWORK_OFFLINE);
        return true;
    }

    set_none_result(output, SAFETY_MODEL_REASON_NO_RISK_SIGNAL);
    return true;
}

const char *safety_model_version(void)
{
    return SAFETY_MODEL_MOCK_VERSION;
}

bool safety_model_input_from_mock_state(const safety_model_mock_state_t *state, ego_sc_model_input_t *input)
{
    if (state == NULL || input == NULL) {
        return false;
    }

    memset(input, 0, sizeof(*input));
    input->mode = state->mode;
    input->activity = state->impact_detected ? EGO_SC_ACTIVITY_IMPACT : EGO_SC_ACTIVITY_WALKING;
    input->activity_confidence = state->impact_detected ? 0.93f : 0.90f;
    input->impact_score = state->impact_detected ? 0.92f : 0.05f;
    input->fall_score = 0.03f;
    input->stationary_seconds = state->impact_detected ? 20.0f : 0.0f;
    input->device_worn = 1;

    input->speech_score = state->wake_detected ? 0.92f : 0.10f;
    input->distress_score = 0.02f;
    input->impact_sound_score = state->impact_detected ? 0.76f : 0.03f;
    input->unknown_loud_sound_score = 0.02f;
    input->audio_quality_score = 0.90f;

    input->gnss_fix_valid = state->gnss_fix_valid;
    input->speed_mps = state->impact_detected ? 0.0f : 1.2f;
    input->outside_safe_zone = false;
    input->dwell_seconds = 0.0f;
    input->route_deviation_m = 0.0f;
    input->gnss_quality_score = state->gnss_fix_valid ? 0.85f : 0.0f;

    input->connectivity_score = state->base_online && state->upload_available ? 0.85f : 0.0f;
    input->base_online = state->base_online;
    input->upload_available = state->upload_available;
    input->signal_level = state->signal_level > 4 ? 4 : state->signal_level;
    input->offline_seconds = state->base_online ? 0.0f : state->offline_seconds;

    input->battery_percent = state->battery_percent;
    input->charging = state->charging;
    input->privacy_mode = state->privacy_mode;
    input->camera_available = state->camera_available;
    input->microphone_available = state->microphone_available;

    input->recent_risk_count_5m = 0;
    input->last_user_response = EGO_SC_RESPONSE_NONE;
    input->seconds_since_last_contact = 20.0f;
    input->sos_pressed = state->sos_pressed;
    input->cancel_pressed = state->cancel_pressed;

    input->audio_clip_available = false;
    input->single_image_available = false;
    input->fresh_gnss_available = state->gnss_fix_valid;
    input->imu_window_available = true;
    return true;
}

const char *safety_model_risk_type_name(ego_sc_risk_type_t risk_type)
{
    switch (risk_type) {
    case EGO_SC_RISK_NONE:
        return "none";
    case EGO_SC_RISK_MANUAL_SOS:
        return "manual_sos";
    case EGO_SC_RISK_POSSIBLE_FALL:
        return "possible_fall";
    case EGO_SC_RISK_POSSIBLE_COLLISION:
        return "possible_collision";
    case EGO_SC_RISK_POST_IMPACT_INACTIVITY:
        return "post_impact_inactivity";
    case EGO_SC_RISK_DISTRESS_AUDIO:
        return "distress_audio";
    case EGO_SC_RISK_GEOFENCE_EXIT:
        return "geofence_exit";
    case EGO_SC_RISK_ABNORMAL_DWELL:
        return "abnormal_dwell";
    case EGO_SC_RISK_COMMUNICATION_LOSS:
        return "communication_loss";
    case EGO_SC_RISK_LOW_BATTERY:
        return "low_battery";
    case EGO_SC_RISK_PRIVACY_VIOLATION:
        return "privacy_violation";
    case EGO_SC_RISK_UNCERTAIN:
        return "uncertain";
    default:
        return "unknown";
    }
}

const char *safety_model_action_name(ego_sc_action_t action)
{
    switch (action) {
    case EGO_SC_ACTION_IGNORE:
        return "ignore";
    case EGO_SC_ACTION_LOCAL_PROMPT:
        return "local_prompt";
    case EGO_SC_ACTION_ASK_USER:
        return "ask_user";
    case EGO_SC_ACTION_CAPTURE_MORE:
        return "capture_more";
    case EGO_SC_ACTION_SEND_SUMMARY:
        return "send_summary";
    case EGO_SC_ACTION_SEND_EVIDENCE:
        return "send_evidence";
    case EGO_SC_ACTION_URGENT_ESCALATION:
        return "urgent_escalation";
    default:
        return "unknown";
    }
}

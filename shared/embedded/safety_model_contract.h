#ifndef EGO_SAFETY_MODEL_CONTRACT_H
#define EGO_SAFETY_MODEL_CONTRACT_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EGO_SC_CONTRACT_VERSION_MAJOR 1
#define EGO_SC_CONTRACT_VERSION_MINOR 0
#define EGO_SC_CONTRACT_VERSION_PATCH 0
#define EGO_SC_REASON_CAPACITY 8

typedef enum {
    EGO_SC_MODE_PERSONAL_SAFETY = 0,
    EGO_SC_MODE_CHILD_SAFETY,
    EGO_SC_MODE_ELDER_SAFETY,
    EGO_SC_MODE_CYCLING,
    EGO_SC_MODE_TEST
} ego_sc_mode_t;

typedef enum {
    EGO_SC_ACTIVITY_UNKNOWN = 0,
    EGO_SC_ACTIVITY_STATIONARY,
    EGO_SC_ACTIVITY_WALKING,
    EGO_SC_ACTIVITY_RUNNING,
    EGO_SC_ACTIVITY_CYCLING,
    EGO_SC_ACTIVITY_VEHICLE,
    EGO_SC_ACTIVITY_IMPACT,
    EGO_SC_ACTIVITY_FALL_CANDIDATE
} ego_sc_activity_t;

typedef enum {
    EGO_SC_RESPONSE_NONE = 0,
    EGO_SC_RESPONSE_SAFE,
    EGO_SC_RESPONSE_NEED_HELP,
    EGO_SC_RESPONSE_NO_RESPONSE,
    EGO_SC_RESPONSE_CANCEL
} ego_sc_user_response_t;

typedef enum {
    EGO_SC_RISK_NONE = 0,
    EGO_SC_RISK_MANUAL_SOS,
    EGO_SC_RISK_POSSIBLE_FALL,
    EGO_SC_RISK_POSSIBLE_COLLISION,
    EGO_SC_RISK_POST_IMPACT_INACTIVITY,
    EGO_SC_RISK_DISTRESS_AUDIO,
    EGO_SC_RISK_GEOFENCE_EXIT,
    EGO_SC_RISK_ABNORMAL_DWELL,
    EGO_SC_RISK_COMMUNICATION_LOSS,
    EGO_SC_RISK_LOW_BATTERY,
    EGO_SC_RISK_PRIVACY_VIOLATION,
    EGO_SC_RISK_UNCERTAIN
} ego_sc_risk_type_t;

typedef enum {
    EGO_SC_PRIORITY_INFO = 0,
    EGO_SC_PRIORITY_WARNING,
    EGO_SC_PRIORITY_HIGH,
    EGO_SC_PRIORITY_CRITICAL
} ego_sc_priority_t;

typedef enum {
    EGO_SC_ACTION_IGNORE = 0,
    EGO_SC_ACTION_LOCAL_PROMPT,
    EGO_SC_ACTION_ASK_USER,
    EGO_SC_ACTION_CAPTURE_MORE,
    EGO_SC_ACTION_SEND_SUMMARY,
    EGO_SC_ACTION_SEND_EVIDENCE,
    EGO_SC_ACTION_URGENT_ESCALATION
} ego_sc_action_t;

typedef enum {
    EGO_SC_EVIDENCE_NONE = 0,
    EGO_SC_EVIDENCE_AUDIO_5S = 1u << 0,
    EGO_SC_EVIDENCE_IMAGE_SINGLE = 1u << 1,
    EGO_SC_EVIDENCE_GNSS_REFRESH = 1u << 2,
    EGO_SC_EVIDENCE_IMU_10S = 1u << 3,
    EGO_SC_EVIDENCE_USER_CONFIRMATION = 1u << 4
} ego_sc_evidence_mask_t;

typedef struct {
    ego_sc_mode_t mode;
    ego_sc_activity_t activity;
    float activity_confidence;
    float impact_score;
    float fall_score;
    float stationary_seconds;
    int8_t device_worn; /* -1 unknown, 0 false, 1 true */

    float speech_score;
    float distress_score;
    float impact_sound_score;
    float unknown_loud_sound_score;
    float audio_quality_score;

    bool gnss_fix_valid;
    float speed_mps;
    bool outside_safe_zone;
    float dwell_seconds;
    float route_deviation_m;
    float gnss_quality_score;

    float connectivity_score;
    bool base_online;
    bool upload_available;
    uint8_t signal_level; /* 0..4 */
    float offline_seconds;

    float battery_percent;
    bool charging;
    bool privacy_mode;
    bool camera_available;
    bool microphone_available;

    uint16_t recent_risk_count_5m;
    ego_sc_user_response_t last_user_response;
    float seconds_since_last_contact;
    bool sos_pressed;
    bool cancel_pressed;

    bool audio_clip_available;
    bool single_image_available;
    bool fresh_gnss_available;
    bool imu_window_available;
} ego_sc_model_input_t;

typedef struct {
    ego_sc_risk_type_t risk_type;
    float risk_score;
    float confidence;
    ego_sc_priority_t priority;
    ego_sc_action_t recommended_action;
    bool requires_base;
    uint32_t evidence_mask;
    bool safety_rule_applied;
    uint32_t decision_ttl_ms;
    uint16_t reason_codes[EGO_SC_REASON_CAPACITY];
    uint8_t reason_count;
} ego_sc_model_output_t;

#ifdef __cplusplus
}
#endif

#endif /* EGO_SAFETY_MODEL_CONTRACT_H */

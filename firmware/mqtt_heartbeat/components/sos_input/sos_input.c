#include "sos_input.h"

#include <stddef.h>
#include <string.h>

static void refresh_phase(egolink_sos_input_t *input);

static bool config_is_valid(const egolink_sos_input_config_t *config)
{
    if (config == NULL) {
        return false;
    }
    if (config->debounce_ms < EGOLINK_SOS_INPUT_DEBOUNCE_MIN_MS ||
        config->debounce_ms > EGOLINK_SOS_INPUT_DEBOUNCE_MAX_MS) {
        return false;
    }
    if (config->long_press_ms < EGOLINK_SOS_INPUT_LONG_PRESS_MIN_MS ||
        config->long_press_ms > EGOLINK_SOS_INPUT_LONG_PRESS_MAX_MS) {
        return false;
    }
    return config->long_press_ms >= config->debounce_ms;
}

static void clear_output(egolink_sos_input_output_t *output)
{
    if (output != NULL) {
        *output = (egolink_sos_input_output_t){
            .sos_edge = false,
            .sos_edge_time_ms = UINT64_C(0),
            .armed = false,
            .stable_pressed = false,
            .phase = EGOLINK_SOS_INPUT_PHASE_UNINITIALIZED,
        };
    }
}

static void publish_output(
    const egolink_sos_input_t *input,
    bool sos_edge,
    uint64_t sos_edge_time_ms,
    egolink_sos_input_output_t *output)
{
    output->sos_edge = sos_edge;
    output->sos_edge_time_ms = sos_edge ? sos_edge_time_ms : UINT64_C(0);
    output->armed = input->armed;
    output->stable_pressed = input->stable_pressed;
    output->phase = input->phase;
}

static bool checked_deadline(
    uint64_t start_ms,
    uint32_t duration_ms,
    uint64_t *deadline_ms)
{
    if (deadline_ms == NULL ||
        start_ms > UINT64_MAX - (uint64_t)duration_ms) {
        return false;
    }
    *deadline_ms = start_ms + (uint64_t)duration_ms;
    return true;
}

static egolink_sos_input_status_t latch_time_overflow(
    egolink_sos_input_t *input)
{
    input->fault_latched = true;
    input->armed = false;
    input->phase = EGOLINK_SOS_INPUT_PHASE_FAULT;
    return EGOLINK_SOS_INPUT_STATUS_TIME_OVERFLOW;
}

/* Advance the previously sampled raw level through now_ms before ingesting a
 * possible new raw transition at that same instant. Trigger/release equality
 * is safety-biased toward the trigger, matching the host SOS replay seam. */
static egolink_sos_input_status_t advance_known_level(
    egolink_sos_input_t *input,
    uint64_t now_ms,
    bool *sos_edge,
    uint64_t *sos_edge_time_ms)
{
    for (;;) {
        uint64_t debounce_at_ms = UINT64_C(0);
        uint64_t trigger_at_ms = UINT64_C(0);
        bool debounce_pending = input->candidate_pressed != input->stable_pressed;
        bool trigger_pending = input->stable_pressed && input->armed &&
            !input->initial_release_required && !input->event_latched;

        if (debounce_pending &&
            !checked_deadline(
                input->candidate_since_ms,
                input->config.debounce_ms,
                &debounce_at_ms)) {
            return latch_time_overflow(input);
        }
        if (trigger_pending &&
            !checked_deadline(
                input->stable_pressed_since_ms,
                input->config.long_press_ms,
                &trigger_at_ms)) {
            return latch_time_overflow(input);
        }

        if (trigger_pending && trigger_at_ms <= now_ms &&
            (!debounce_pending || trigger_at_ms <= debounce_at_ms)) {
            input->event_latched = true;
            input->armed = false;
            *sos_edge = true;
            *sos_edge_time_ms = trigger_at_ms;
            refresh_phase(input);
            continue;
        }

        if (debounce_pending && debounce_at_ms <= now_ms) {
            input->stable_pressed = input->candidate_pressed;
            if (input->stable_pressed) {
                input->stable_pressed_since_ms = debounce_at_ms;
                input->event_latched = false;
            } else {
                input->initial_release_required = false;
                input->armed = true;
                input->event_latched = false;
            }
            refresh_phase(input);
            continue;
        }
        break;
    }
    return EGOLINK_SOS_INPUT_STATUS_OK;
}

static void refresh_phase(egolink_sos_input_t *input)
{
    if (input->fault_latched) {
        input->phase = EGOLINK_SOS_INPUT_PHASE_FAULT;
        return;
    }
    if (input->candidate_pressed != input->stable_pressed) {
        input->phase = input->candidate_pressed
            ? EGOLINK_SOS_INPUT_PHASE_DEBOUNCE_PRESS
            : EGOLINK_SOS_INPUT_PHASE_DEBOUNCE_RELEASE;
        return;
    }
    if (input->stable_pressed) {
        if (input->initial_release_required) {
            input->phase = EGOLINK_SOS_INPUT_PHASE_WAIT_INITIAL_RELEASE;
        } else if (input->event_latched) {
            input->phase = EGOLINK_SOS_INPUT_PHASE_TRIGGERED;
        } else {
            input->phase = EGOLINK_SOS_INPUT_PHASE_PRESSED;
        }
        return;
    }
    input->phase = EGOLINK_SOS_INPUT_PHASE_ARMED;
}

egolink_sos_input_status_t egolink_sos_input_init(
    egolink_sos_input_t *input,
    const egolink_sos_input_config_t *config,
    bool initial_raw_pressed,
    uint64_t now_ms)
{
    if (input == NULL) {
        return EGOLINK_SOS_INPUT_STATUS_INVALID_ARGUMENT;
    }

    (void)memset(input, 0, sizeof(*input));
    if (!config_is_valid(config)) {
        return EGOLINK_SOS_INPUT_STATUS_INVALID_CONFIG;
    }

    input->config = *config;
    input->last_sample_ms = now_ms;
    input->candidate_since_ms = now_ms;
    input->stable_pressed_since_ms = now_ms;
    input->initialized = true;
    input->stable_pressed = initial_raw_pressed;
    input->candidate_pressed = initial_raw_pressed;
    input->initial_release_required = initial_raw_pressed;
    input->armed = !initial_raw_pressed;
    input->event_latched = initial_raw_pressed;
    refresh_phase(input);
    return EGOLINK_SOS_INPUT_STATUS_OK;
}

egolink_sos_input_status_t egolink_sos_input_process(
    egolink_sos_input_t *input,
    bool raw_pressed,
    uint64_t now_ms,
    egolink_sos_input_output_t *output)
{
    clear_output(output);
    if (input == NULL || output == NULL) {
        return EGOLINK_SOS_INPUT_STATUS_INVALID_ARGUMENT;
    }
    if (!input->initialized) {
        return EGOLINK_SOS_INPUT_STATUS_NOT_INITIALIZED;
    }
    if (input->fault_latched) {
        input->phase = EGOLINK_SOS_INPUT_PHASE_FAULT;
        publish_output(input, false, UINT64_C(0), output);
        return EGOLINK_SOS_INPUT_STATUS_FAULT_LATCHED;
    }
    if (now_ms < input->last_sample_ms) {
        input->fault_latched = true;
        input->armed = false;
        input->phase = EGOLINK_SOS_INPUT_PHASE_FAULT;
        publish_output(input, false, UINT64_C(0), output);
        return EGOLINK_SOS_INPUT_STATUS_TIME_ROLLBACK;
    }
    input->last_sample_ms = now_ms;

    bool sos_edge = false;
    uint64_t sos_edge_time_ms = UINT64_C(0);
    egolink_sos_input_status_t status = advance_known_level(
        input, now_ms, &sos_edge, &sos_edge_time_ms);
    if (status != EGOLINK_SOS_INPUT_STATUS_OK) {
        publish_output(input, false, UINT64_C(0), output);
        return status;
    }

    if (raw_pressed != input->candidate_pressed) {
        input->candidate_pressed = raw_pressed;
        input->candidate_since_ms = now_ms;
        refresh_phase(input);
        publish_output(input, sos_edge, sos_edge_time_ms, output);
        return EGOLINK_SOS_INPUT_STATUS_OK;
    }

    refresh_phase(input);
    publish_output(input, sos_edge, sos_edge_time_ms, output);
    return EGOLINK_SOS_INPUT_STATUS_OK;
}

const char *egolink_sos_input_status_name(egolink_sos_input_status_t status)
{
    switch (status) {
    case EGOLINK_SOS_INPUT_STATUS_OK:
        return "ok";
    case EGOLINK_SOS_INPUT_STATUS_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_SOS_INPUT_STATUS_INVALID_CONFIG:
        return "invalid_config";
    case EGOLINK_SOS_INPUT_STATUS_NOT_INITIALIZED:
        return "not_initialized";
    case EGOLINK_SOS_INPUT_STATUS_TIME_ROLLBACK:
        return "time_rollback";
    case EGOLINK_SOS_INPUT_STATUS_TIME_OVERFLOW:
        return "time_overflow";
    case EGOLINK_SOS_INPUT_STATUS_FAULT_LATCHED:
        return "fault_latched";
    default:
        return "unknown";
    }
}

const char *egolink_sos_input_phase_name(egolink_sos_input_phase_t phase)
{
    switch (phase) {
    case EGOLINK_SOS_INPUT_PHASE_UNINITIALIZED:
        return "uninitialized";
    case EGOLINK_SOS_INPUT_PHASE_WAIT_INITIAL_RELEASE:
        return "wait_initial_release";
    case EGOLINK_SOS_INPUT_PHASE_ARMED:
        return "armed";
    case EGOLINK_SOS_INPUT_PHASE_DEBOUNCE_PRESS:
        return "debounce_press";
    case EGOLINK_SOS_INPUT_PHASE_PRESSED:
        return "pressed";
    case EGOLINK_SOS_INPUT_PHASE_TRIGGERED:
        return "triggered";
    case EGOLINK_SOS_INPUT_PHASE_DEBOUNCE_RELEASE:
        return "debounce_release";
    case EGOLINK_SOS_INPUT_PHASE_FAULT:
        return "fault";
    default:
        return "unknown";
    }
}

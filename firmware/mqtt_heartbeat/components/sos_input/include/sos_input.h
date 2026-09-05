#ifndef EGOLINK_SOS_INPUT_H
#define EGOLINK_SOS_INPUT_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Conservative engineering bounds. Product values remain field-test inputs. */
#define EGOLINK_SOS_INPUT_DEBOUNCE_MIN_MS UINT32_C(5)
#define EGOLINK_SOS_INPUT_DEBOUNCE_MAX_MS UINT32_C(500)
#define EGOLINK_SOS_INPUT_LONG_PRESS_MIN_MS UINT32_C(500)
#define EGOLINK_SOS_INPUT_LONG_PRESS_MAX_MS UINT32_C(10000)
#define EGOLINK_SOS_INPUT_DEFAULT_DEBOUNCE_MS UINT32_C(50)
#define EGOLINK_SOS_INPUT_DEFAULT_LONG_PRESS_MS UINT32_C(2000)

typedef struct {
    uint32_t debounce_ms;
    uint32_t long_press_ms;
} egolink_sos_input_config_t;

typedef enum {
    EGOLINK_SOS_INPUT_PHASE_UNINITIALIZED = 0,
    EGOLINK_SOS_INPUT_PHASE_WAIT_INITIAL_RELEASE,
    EGOLINK_SOS_INPUT_PHASE_ARMED,
    EGOLINK_SOS_INPUT_PHASE_DEBOUNCE_PRESS,
    EGOLINK_SOS_INPUT_PHASE_PRESSED,
    EGOLINK_SOS_INPUT_PHASE_TRIGGERED,
    EGOLINK_SOS_INPUT_PHASE_DEBOUNCE_RELEASE,
    EGOLINK_SOS_INPUT_PHASE_FAULT,
} egolink_sos_input_phase_t;

typedef enum {
    EGOLINK_SOS_INPUT_STATUS_OK = 0,
    EGOLINK_SOS_INPUT_STATUS_INVALID_ARGUMENT,
    EGOLINK_SOS_INPUT_STATUS_INVALID_CONFIG,
    EGOLINK_SOS_INPUT_STATUS_NOT_INITIALIZED,
    EGOLINK_SOS_INPUT_STATUS_TIME_ROLLBACK,
    EGOLINK_SOS_INPUT_STATUS_TIME_OVERFLOW,
    EGOLINK_SOS_INPUT_STATUS_FAULT_LATCHED,
} egolink_sos_input_status_t;

/*
 * Caller-owned state. This component has no GPIO, task, transport, persistence,
 * location, call or battery dependency. In particular, there is no low-power
 * veto input: every sampled physical press follows the same safety path.
 */
typedef struct {
    egolink_sos_input_config_t config;
    egolink_sos_input_phase_t phase;
    uint64_t last_sample_ms;
    uint64_t candidate_since_ms;
    uint64_t stable_pressed_since_ms;
    bool initialized;
    bool fault_latched;
    bool stable_pressed;
    bool candidate_pressed;
    bool initial_release_required;
    bool armed;
    bool event_latched;
} egolink_sos_input_t;

typedef struct {
    bool sos_edge;
    uint64_t sos_edge_time_ms;
    bool armed;
    bool stable_pressed;
    egolink_sos_input_phase_t phase;
} egolink_sos_input_output_t;

/*
 * now_ms belongs to one boot-scoped monotonic clock and must never be replaced
 * by wall/receive time. initial_raw_pressed is the sampled level at now_ms.
 * Starting while held never emits an event; release must debounce before arm.
 */
egolink_sos_input_status_t egolink_sos_input_init(
    egolink_sos_input_t *input,
    const egolink_sos_input_config_t *config,
    bool initial_raw_pressed,
    uint64_t now_ms);

/*
 * A successful call sets output->sos_edge for exactly one sample and preserves
 * its exact logical time in output->sos_edge_time_ms. A debounced release is
 * required before another edge. Time rollback, counter wrap or an
 * unrepresentable debounce/long-press deadline latches FAULT until re-init.
 */
egolink_sos_input_status_t egolink_sos_input_process(
    egolink_sos_input_t *input,
    bool raw_pressed,
    uint64_t now_ms,
    egolink_sos_input_output_t *output);

const char *egolink_sos_input_status_name(egolink_sos_input_status_t status);
const char *egolink_sos_input_phase_name(egolink_sos_input_phase_t phase);

#ifdef __cplusplus
}
#endif

#endif /* EGOLINK_SOS_INPUT_H */

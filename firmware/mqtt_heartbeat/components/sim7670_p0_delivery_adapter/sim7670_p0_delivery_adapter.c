#include "sim7670_p0_delivery_adapter.h"

#include <limits.h>
#include <string.h>

#define SIM7670_P0_DELIVERY_MAGIC UINT32_C(0x53375044)
#define SIM7670_P0_DELIVERY_MAX_COMMAND_PHASES UINT32_C(8)
#define SIM7670_P0_DELIVERY_BEARER_MAX_BYTES 160U

typedef struct {
    uint32_t magic;
    egolink_sim7670_p0_delivery_lifecycle_t lifecycle;
    egolink_sim7670_p0_delivery_status_t last_status;
    sim7670_lte_http_exact_status_t last_driver_status;
    bool enabled;
    bool busy;
    char base_url[EGOLINK_SIM7670_P0_DELIVERY_BASE_URL_CAPACITY];
    char bearer_token[EGOLINK_SIM7670_P0_DELIVERY_BEARER_CAPACITY];
    char full_url[EGOLINK_SIM7670_P0_DELIVERY_FULL_URL_CAPACITY];
    uint32_t command_timeout_ms;
    uint32_t data_timeout_ms;
    uint32_t action_timeout_ms;
    uint32_t read_timeout_ms;
    uint32_t configured_io_phase_budget_ms;
    uint32_t configured_max_callback_duration_ms;
    egolink_sim7670_p0_delivery_driver_post_fn driver_post;
    void *driver_context;
    egolink_sim7670_p0_delivery_now_ms_fn now_ms;
    void *clock_context;
    uint64_t callback_calls;
    uint64_t http_responses;
    uint64_t transport_failures;
    uint64_t callback_failures;
} sim7670_p0_delivery_internal_t;

_Static_assert(
    sizeof(sim7670_p0_delivery_internal_t) <=
        EGOLINK_SIM7670_P0_DELIVERY_ADAPTER_CONTEXT_BYTES,
    "SIM7670 P0 adapter context is too small");

static sim7670_p0_delivery_internal_t *internal_of(
    egolink_sim7670_p0_delivery_adapter_t *adapter)
{
    return (sim7670_p0_delivery_internal_t *)(void *)adapter->opaque;
}

static const sim7670_p0_delivery_internal_t *internal_of_const(
    const egolink_sim7670_p0_delivery_adapter_t *adapter)
{
    return (const sim7670_p0_delivery_internal_t *)(const void *)adapter->opaque;
}

static bool valid_magic(const sim7670_p0_delivery_internal_t *internal)
{
    return internal != NULL && internal->magic == SIM7670_P0_DELIVERY_MAGIC;
}

static void secure_clear(void *buffer, size_t length)
{
    volatile uint8_t *cursor = (volatile uint8_t *)buffer;
    while (cursor != NULL && length > 0U) {
        *cursor = 0U;
        ++cursor;
        --length;
    }
}

static void increment_saturated(uint64_t *value)
{
    if (value != NULL && *value != UINT64_MAX) {
        ++(*value);
    }
}

static sim7670_lte_http_exact_status_t default_driver_post(
    void *context,
    const sim7670_lte_http_exact_request_t *request,
    sim7670_lte_http_exact_result_t *result)
{
    (void)context;
    return sim7670_lte_http_post_bytes_exact(request, result);
}

static bool bounded_text_length(
    const char *text,
    size_t maximum,
    size_t *length_out)
{
    if (text == NULL || length_out == NULL || maximum == 0U) {
        return false;
    }
    size_t length = 0U;
    while (length <= maximum && text[length] != '\0') {
        ++length;
    }
    if (length == 0U || length > maximum) {
        return false;
    }
    *length_out = length;
    return true;
}

static bool valid_bearer(const char *bearer_token, size_t *length_out)
{
    size_t length = 0U;
    if (!bounded_text_length(
            bearer_token,
            SIM7670_P0_DELIVERY_BEARER_MAX_BYTES,
            &length)) {
        return false;
    }
    if (bearer_token[0] == '<') {
        return false;
    }
    for (size_t index = 0U; index < length; ++index) {
        const unsigned char ch = (unsigned char)bearer_token[index];
        const bool alpha =
            (ch >= (unsigned char)'a' && ch <= (unsigned char)'z') ||
            (ch >= (unsigned char)'A' && ch <= (unsigned char)'Z');
        const bool digit =
            ch >= (unsigned char)'0' && ch <= (unsigned char)'9';
        if (!alpha && !digit && ch != (unsigned char)'.' &&
            ch != (unsigned char)'_' && ch != (unsigned char)'~' &&
            ch != (unsigned char)'+' && ch != (unsigned char)'/' &&
            ch != (unsigned char)'-' && ch != (unsigned char)'=') {
            return false;
        }
    }
    *length_out = length;
    return true;
}

static bool calculate_timing_bounds(
    const egolink_sim7670_p0_delivery_adapter_config_t *config,
    uint32_t *phase_budget_out)
{
    if (config == NULL || phase_budget_out == NULL ||
        config->command_timeout_ms == 0U ||
        config->data_timeout_ms == 0U ||
        config->action_timeout_ms == 0U ||
        config->read_timeout_ms == 0U ||
        config->command_timeout_ms > SIM7670_LTE_HTTP_EXACT_TIMEOUT_MAX_MS ||
        config->data_timeout_ms > SIM7670_LTE_HTTP_EXACT_TIMEOUT_MAX_MS ||
        config->action_timeout_ms > SIM7670_LTE_HTTP_EXACT_TIMEOUT_MAX_MS ||
        config->read_timeout_ms > SIM7670_LTE_HTTP_EXACT_TIMEOUT_MAX_MS ||
        config->max_callback_duration_ms == 0U ||
        config->max_callback_duration_ms >
            EGOLINK_SIM7670_P0_DELIVERY_MAX_TRANSACTION_MS) {
        return false;
    }
    const uint64_t total =
        (uint64_t)SIM7670_P0_DELIVERY_MAX_COMMAND_PHASES *
            (uint64_t)config->command_timeout_ms +
        (uint64_t)config->data_timeout_ms +
        (uint64_t)config->action_timeout_ms +
        (uint64_t)config->read_timeout_ms;
    if (total >= (uint64_t)config->max_callback_duration_ms ||
        total > (uint64_t)UINT32_MAX) {
        return false;
    }
    *phase_budget_out = (uint32_t)total;
    return true;
}

static egolink_sim7670_p0_delivery_status_t set_status(
    sim7670_p0_delivery_internal_t *internal,
    egolink_sim7670_p0_delivery_status_t status)
{
    if (internal != NULL) {
        internal->last_status = status;
    }
    return status;
}

static void initialize_post_result(
    egolink_p0_delivery_post_result_t *result,
    uint64_t completion_time_ms)
{
    if (result == NULL) {
        return;
    }
    (void)memset(result, 0, sizeof(*result));
    result->completion_time_ms = completion_time_ms;
    result->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_NONE;
}

static void clear_post_response(
    const egolink_p0_delivery_post_request_t *request)
{
    if (request == NULL || request->response == NULL) {
        return;
    }
    const size_t clear_length =
        request->response_capacity <= EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES
            ? request->response_capacity
            : EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES;
    secure_clear(request->response, clear_length);
}

static bool request_route_is_valid(
    const egolink_p0_delivery_post_request_t *request)
{
    if (request == NULL || request->path == NULL || request->body == NULL ||
        request->body_length == 0U ||
        request->body_length > SIM7670_LTE_HTTP_EXACT_PAYLOAD_MAX_BYTES ||
        request->response == NULL) {
        return false;
    }
    if (request->route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS) {
        return strcmp(
                   request->path,
                   EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH) == 0 &&
               request->response_capacity ==
                   EGOLINK_SOS_OUTBOX_RESPONSE_MAX_BYTES &&
               request->priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL;
    }
    if (request->route == EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE) {
        return strcmp(
                   request->path,
                   EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH) == 0 &&
               request->response_capacity ==
                   EGOLINK_LOCATION_OUTBOX_RESPONSE_MAX_BYTES &&
               (request->priority == EGOLINK_OUTBOX_PRIORITY_NORMAL ||
                request->priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL);
    }
    return false;
}

static egolink_p0_delivery_transport_error_t map_transport_error(
    sim7670_lte_http_exact_status_t status)
{
    switch (status) {
    case SIM7670_LTE_HTTP_EXACT_DRIVER_DISABLED:
        return EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OFFLINE;
    case SIM7670_LTE_HTTP_EXACT_ACTION_TIMEOUT:
    case SIM7670_LTE_HTTP_EXACT_READ_TIMEOUT:
        return EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TIMEOUT;
    case SIM7670_LTE_HTTP_EXACT_UART_INIT_FAILED:
    case SIM7670_LTE_HTTP_EXACT_AT_FAILED:
    case SIM7670_LTE_HTTP_EXACT_SETUP_FAILED:
    case SIM7670_LTE_HTTP_EXACT_PAYLOAD_WRITE_FAILED:
    case SIM7670_LTE_HTTP_EXACT_ACTION_INVALID:
    case SIM7670_LTE_HTTP_EXACT_READ_INVALID:
    case SIM7670_LTE_HTTP_EXACT_IO_FAILED:
        return EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_IO;
    case SIM7670_LTE_HTTP_EXACT_TLS_PROFILE_UNVERIFIED:
        return EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TLS;
    case SIM7670_LTE_HTTP_EXACT_RESPONSE_TOO_LARGE:
        return EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER;
    case SIM7670_LTE_HTTP_EXACT_HTTP_RESPONSE:
    case SIM7670_LTE_HTTP_EXACT_INVALID_ARGUMENT:
    case SIM7670_LTE_HTTP_EXACT_INVALID_CONFIG:
    case SIM7670_LTE_HTTP_EXACT_PAYLOAD_TOO_LARGE:
    default:
        return EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_OTHER;
    }
}

void egolink_sim7670_p0_delivery_adapter_default_config(
    egolink_sim7670_p0_delivery_adapter_config_t *config)
{
    if (config == NULL) {
        return;
    }
    (void)memset(config, 0, sizeof(*config));
    config->enabled = false;
    config->command_timeout_ms =
        EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_COMMAND_TIMEOUT_MS;
    config->data_timeout_ms =
        EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_DATA_TIMEOUT_MS;
    config->action_timeout_ms =
        EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_ACTION_TIMEOUT_MS;
    config->read_timeout_ms =
        EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_READ_TIMEOUT_MS;
    config->max_callback_duration_ms =
        EGOLINK_SIM7670_P0_DELIVERY_DEFAULT_MAX_CALLBACK_DURATION_MS;
    config->driver_post = default_driver_post;
}

egolink_sim7670_p0_delivery_status_t
egolink_sim7670_p0_delivery_adapter_init(
    egolink_sim7670_p0_delivery_adapter_t *adapter,
    const egolink_sim7670_p0_delivery_adapter_config_t *config)
{
    if (adapter == NULL || config == NULL) {
        return EGOLINK_SIM7670_P0_DELIVERY_INVALID_ARGUMENT;
    }
    sim7670_p0_delivery_internal_t *internal = internal_of(adapter);
    if (valid_magic(internal)) {
        return EGOLINK_SIM7670_P0_DELIVERY_ALREADY_INITIALIZED;
    }
    secure_clear(adapter, sizeof(*adapter));
    internal = internal_of(adapter);
    internal->magic = SIM7670_P0_DELIVERY_MAGIC;
    internal->lifecycle = EGOLINK_SIM7670_P0_DELIVERY_DISABLED;
    internal->last_status = EGOLINK_SIM7670_P0_DELIVERY_DISABLED_STATUS;
    internal->last_driver_status =
        SIM7670_LTE_HTTP_EXACT_DRIVER_DISABLED;
    if (!config->enabled) {
        return internal->last_status;
    }

    size_t base_length = 0U;
    size_t expected_host_length = 0U;
    size_t bearer_length = 0U;
    uint32_t io_phase_budget_ms = 0U;
#if CONFIG_EGOLINK_SIM7670_P0_DELIVERY_TEST_DRIVER_ENABLED
    const bool driver_allowed = config->driver_post != NULL;
#else
    const bool driver_allowed =
        config->driver_post == default_driver_post &&
        config->driver_context == NULL;
#endif
    if (!bounded_text_length(
            config->base_url,
            EGOLINK_SIM7670_P0_DELIVERY_BASE_URL_CAPACITY - 1U,
            &base_length) ||
        !bounded_text_length(
            config->expected_tls_host,
            EGOLINK_SIM7670_P0_DELIVERY_EXPECTED_HOST_CAPACITY - 1U,
            &expected_host_length) ||
        sim7670_http_exact_https_origin_matches_dns_host(
            config->base_url, config->expected_tls_host) == 0 ||
        !valid_bearer(config->bearer_token, &bearer_length) ||
        !driver_allowed || config->now_ms == NULL ||
        !calculate_timing_bounds(config, &io_phase_budget_ms)) {
        secure_clear(adapter, sizeof(*adapter));
        internal = internal_of(adapter);
        internal->magic = SIM7670_P0_DELIVERY_MAGIC;
        internal->lifecycle = EGOLINK_SIM7670_P0_DELIVERY_DISABLED;
        internal->last_status = EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG;
        return internal->last_status;
    }
    (void)memcpy(internal->base_url, config->base_url, base_length);
    internal->base_url[base_length] = '\0';
    (void)memcpy(
        internal->bearer_token,
        config->bearer_token,
        bearer_length);
    internal->bearer_token[bearer_length] = '\0';
    internal->command_timeout_ms = config->command_timeout_ms;
    internal->data_timeout_ms = config->data_timeout_ms;
    internal->action_timeout_ms = config->action_timeout_ms;
    internal->read_timeout_ms = config->read_timeout_ms;
    internal->configured_io_phase_budget_ms = io_phase_budget_ms;
    internal->configured_max_callback_duration_ms =
        config->max_callback_duration_ms;
    internal->driver_post = config->driver_post;
    internal->driver_context = config->driver_context;
    internal->now_ms = config->now_ms;
    internal->clock_context = config->clock_context;
    internal->enabled = true;
    internal->lifecycle = EGOLINK_SIM7670_P0_DELIVERY_ACTIVE;
    return set_status(internal, EGOLINK_SIM7670_P0_DELIVERY_OK);
}

egolink_p0_delivery_post_outcome_t
egolink_sim7670_p0_delivery_adapter_http_post(
    void *context,
    const egolink_p0_delivery_post_request_t *request,
    egolink_p0_delivery_post_result_t *result)
{
    clear_post_response(request);
    initialize_post_result(result, 0U);
    if (context == NULL || result == NULL) {
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    egolink_sim7670_p0_delivery_adapter_t *adapter =
        (egolink_sim7670_p0_delivery_adapter_t *)context;
    sim7670_p0_delivery_internal_t *internal = internal_of(adapter);
    if (!valid_magic(internal) ||
        internal->lifecycle != EGOLINK_SIM7670_P0_DELIVERY_ACTIVE ||
        !internal->enabled || internal->driver_post == NULL ||
        internal->now_ms == NULL) {
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    if (internal->busy) {
        increment_saturated(&internal->callback_failures);
        (void)set_status(
            internal, EGOLINK_SIM7670_P0_DELIVERY_REENTRANT_CALL);
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    internal->busy = true;
    increment_saturated(&internal->callback_calls);
    const uint64_t initial_time = internal->now_ms(internal->clock_context);
    result->completion_time_ms = initial_time;
    if (!request_route_is_valid(request)) {
        increment_saturated(&internal->callback_failures);
        (void)set_status(
            internal, EGOLINK_SIM7670_P0_DELIVERY_INVALID_ARGUMENT);
        result->completion_time_ms = internal->now_ms(
            internal->clock_context);
        internal->busy = false;
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }

    const size_t base_length = strlen(internal->base_url);
    const size_t path_length = strlen(request->path);
    if (base_length + path_length >= sizeof(internal->full_url)) {
        increment_saturated(&internal->callback_failures);
        (void)set_status(
            internal, EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG);
        result->completion_time_ms = internal->now_ms(
            internal->clock_context);
        internal->busy = false;
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    (void)memcpy(internal->full_url, internal->base_url, base_length);
    (void)memcpy(
        internal->full_url + base_length,
        request->path,
        path_length + 1U);

    sim7670_lte_http_exact_request_t driver_request;
    (void)memset(&driver_request, 0, sizeof(driver_request));
    driver_request.url = internal->full_url;
    driver_request.bearer_token = internal->bearer_token;
    driver_request.payload = request->body;
    driver_request.payload_length = request->body_length;
    driver_request.response_body = request->response;
    driver_request.response_capacity = request->response_capacity;
    driver_request.command_timeout_ms = internal->command_timeout_ms;
    driver_request.data_timeout_ms = internal->data_timeout_ms;
    driver_request.action_timeout_ms = internal->action_timeout_ms;
    driver_request.read_timeout_ms = internal->read_timeout_ms;
    driver_request.cancel_requested = request->cancel_requested;
    driver_request.cancel_context = request->cancel_context;
    driver_request.transfer_generation = request->transfer_generation;
    sim7670_lte_http_exact_result_t driver_result;
    sim7670_lte_http_exact_result_init(&driver_result);
    const sim7670_lte_http_exact_status_t driver_status =
        internal->driver_post(
            internal->driver_context, &driver_request, &driver_result);
    internal->last_driver_status = driver_status;
    const uint64_t completion_time_ms =
        internal->now_ms(internal->clock_context);
    result->completion_time_ms = completion_time_ms;
    const bool clock_invalid =
        completion_time_ms < initial_time ||
        completion_time_ms - initial_time >
            (uint64_t)internal->configured_max_callback_duration_ms;

    egolink_p0_delivery_post_outcome_t outcome =
        EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    if (clock_invalid) {
        secure_clear(request->response, request->response_capacity);
        result->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TIMEOUT;
        increment_saturated(&internal->transport_failures);
        (void)set_status(internal, EGOLINK_SIM7670_P0_DELIVERY_OK);
        outcome = EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED;
    } else if (
        driver_status == SIM7670_LTE_HTTP_EXACT_HTTP_RESPONSE &&
        driver_result.status == driver_status &&
        driver_result.payload_write_complete &&
        driver_result.payload_bytes_written == request->body_length &&
        driver_result.response_complete &&
        driver_result.http_status_code >= UINT16_C(100) &&
        driver_result.http_status_code <= UINT16_C(599) &&
        driver_result.response_length ==
            driver_result.declared_response_length &&
        driver_result.response_length <= request->response_capacity &&
        driver_result.response_length <=
            SIM7670_LTE_HTTP_EXACT_RESPONSE_MAX_BYTES) {
        result->http_status_code = driver_result.http_status_code;
        result->response_length = driver_result.response_length;
        increment_saturated(&internal->http_responses);
        (void)set_status(internal, EGOLINK_SIM7670_P0_DELIVERY_OK);
        outcome = EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE;
    } else if (
        driver_status == SIM7670_LTE_HTTP_EXACT_INVALID_ARGUMENT ||
        driver_status == SIM7670_LTE_HTTP_EXACT_INVALID_CONFIG ||
        driver_status == SIM7670_LTE_HTTP_EXACT_PAYLOAD_TOO_LARGE ||
        driver_result.status != driver_status) {
        secure_clear(request->response, request->response_capacity);
        increment_saturated(&internal->callback_failures);
        (void)set_status(
            internal, EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG);
        outcome = EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    } else {
        secure_clear(request->response, request->response_capacity);
        result->transport_error = map_transport_error(driver_status);
        increment_saturated(&internal->transport_failures);
        (void)set_status(internal, EGOLINK_SIM7670_P0_DELIVERY_OK);
        outcome = EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED;
    }

    secure_clear(internal->full_url, sizeof(internal->full_url));
    secure_clear(&driver_request, sizeof(driver_request));
    secure_clear(&driver_result, sizeof(driver_result));
    internal->busy = false;
    return outcome;
}

egolink_sim7670_p0_delivery_status_t
egolink_sim7670_p0_delivery_adapter_close(
    egolink_sim7670_p0_delivery_adapter_t *adapter)
{
    if (adapter == NULL) {
        return EGOLINK_SIM7670_P0_DELIVERY_INVALID_ARGUMENT;
    }
    sim7670_p0_delivery_internal_t *internal = internal_of(adapter);
    if (!valid_magic(internal)) {
        return EGOLINK_SIM7670_P0_DELIVERY_NOT_INITIALIZED;
    }
    if (internal->busy) {
        return set_status(
            internal, EGOLINK_SIM7670_P0_DELIVERY_REENTRANT_CALL);
    }
    secure_clear(internal->base_url, sizeof(internal->base_url));
    secure_clear(internal->bearer_token, sizeof(internal->bearer_token));
    secure_clear(internal->full_url, sizeof(internal->full_url));
    internal->driver_post = NULL;
    internal->driver_context = NULL;
    internal->now_ms = NULL;
    internal->clock_context = NULL;
    internal->enabled = false;
    internal->lifecycle = EGOLINK_SIM7670_P0_DELIVERY_CLOSED;
    return set_status(internal, EGOLINK_SIM7670_P0_DELIVERY_CLOSED_STATUS);
}

egolink_sim7670_p0_delivery_status_t
egolink_sim7670_p0_delivery_adapter_current_status(
    const egolink_sim7670_p0_delivery_adapter_t *adapter,
    egolink_sim7670_p0_delivery_adapter_snapshot_t *snapshot)
{
    if (adapter == NULL || snapshot == NULL) {
        return EGOLINK_SIM7670_P0_DELIVERY_INVALID_ARGUMENT;
    }
    const sim7670_p0_delivery_internal_t *internal =
        internal_of_const(adapter);
    if (!valid_magic(internal)) {
        return EGOLINK_SIM7670_P0_DELIVERY_NOT_INITIALIZED;
    }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->lifecycle = internal->lifecycle;
    snapshot->last_status = internal->last_status;
    snapshot->last_driver_status = internal->last_driver_status;
    snapshot->enabled = internal->enabled;
    snapshot->busy = internal->busy;
    snapshot->configured_io_phase_budget_ms =
        internal->configured_io_phase_budget_ms;
    snapshot->configured_max_callback_duration_ms =
        internal->configured_max_callback_duration_ms;
    snapshot->callback_calls = internal->callback_calls;
    snapshot->http_responses = internal->http_responses;
    snapshot->transport_failures = internal->transport_failures;
    snapshot->callback_failures = internal->callback_failures;
    return internal->last_status;
}

const char *egolink_sim7670_p0_delivery_adapter_status_name(
    egolink_sim7670_p0_delivery_status_t status)
{
    switch (status) {
    case EGOLINK_SIM7670_P0_DELIVERY_OK:
        return "ok";
    case EGOLINK_SIM7670_P0_DELIVERY_DISABLED_STATUS:
        return "disabled";
    case EGOLINK_SIM7670_P0_DELIVERY_CLOSED_STATUS:
        return "closed";
    case EGOLINK_SIM7670_P0_DELIVERY_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_SIM7670_P0_DELIVERY_INVALID_CONFIG:
        return "invalid_config";
    case EGOLINK_SIM7670_P0_DELIVERY_NOT_INITIALIZED:
        return "not_initialized";
    case EGOLINK_SIM7670_P0_DELIVERY_ALREADY_INITIALIZED:
        return "already_initialized";
    case EGOLINK_SIM7670_P0_DELIVERY_REENTRANT_CALL:
        return "reentrant_call";
    default:
        return "unknown";
    }
}

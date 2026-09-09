#include "esp_p0_https.h"
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_timer.h"
#include "sim7670_gnss.h"
#include "sdkconfig.h"
#if CONFIG_EGOLINK_COLLECTION_PROFILE
#include <net/if.h>
#include "esp_tls.h"
#endif
#include "esp_transport.h"
#include "esp_transport_ssl.h"
#ifndef CONFIG_ESP_HTTP_CLIENT_ENABLE_CUSTOM_TRANSPORT
#define CONFIG_ESP_HTTP_CLIENT_ENABLE_CUSTOM_TRANSPORT 0
#endif

static uint64_t now_ms(void)
{
    int64_t value = esp_timer_get_time();
    return value < 0 ? UINT64_MAX : (uint64_t)value / 1000U;
}

bool egolink_esp_p0_https_config_valid(const egolink_esp_p0_https_t *c)
{
    return CONFIG_ESP_HTTP_CLIENT_ENABLE_CUSTOM_TRANSPORT &&
        c && c->origin && c->expected_host && c->bearer &&
        sim7670_http_exact_https_origin_matches_dns_host(c->origin, c->expected_host) &&
        sim7670_http_exact_bearer_is_valid(c->bearer) && c->bearer[0] != '<' &&
        strlen(c->bearer) <= 160U && c->max_attempts > 0U && c->max_attempts <= 12U &&
        c->transaction_timeout_ms > 0U && c->transaction_timeout_ms <= 15000U;
}

static bool cancelled(const egolink_p0_delivery_post_request_t *r)
{
    return r->cancel_requested && r->cancel_requested(r->cancel_context, r->transfer_generation);
}

/* IDF fetch_headers/read contain internal retry loops. Enforce the absolute
 * bound on every underlying TLS operation, including incomplete headers. */
typedef struct {
    esp_transport_handle_t tls;
    egolink_p0_delivery_cancel_probe_fn cancel_requested;
    void *cancel_context;
    uint32_t generation;
    bool active;
    const char *host;
    uint64_t deadline;
    size_t received;
} bounded_tls_t;

static int tls_timeout(bounded_tls_t *b, int requested)
{
    uint64_t now = now_ms();
    if (!b || !b->active ||
        (b->cancel_requested && b->cancel_requested(b->cancel_context, b->generation)) ||
        now >= b->deadline || requested <= 0) return -1;
    uint64_t left = b->deadline - now;
    if (left > 1000U) left = 1000U;
    return requested < (int)left ? requested : (int)left;
}
static int tls_connect(esp_transport_handle_t t, const char *host, int port, int timeout)
{
    bounded_tls_t *b = esp_transport_get_context_data(t);
    int wait = tls_timeout(b, timeout);
    if (wait < 0 || port != 443 || strcmp(host, b->host) != 0) return -1;
    return esp_transport_connect(b->tls, host, port, wait);
}
static int tls_read(esp_transport_handle_t t, char *buffer, int length, int timeout)
{
    bounded_tls_t *b = esp_transport_get_context_data(t);
    int wait = tls_timeout(b, timeout);
    /* 8 KiB ACK plus 8 KiB headers; no unbounded parser buffering. */
    if (wait < 0 || b->received >= 16384U || length <= 0) return -1;
    size_t left = 16384U - b->received;
    if ((size_t)length > left) length = (int)left;
    int count = esp_transport_read(b->tls, buffer, length, wait);
    if (count > 0) b->received += (size_t)count;
    return count;
}
static int tls_write(esp_transport_handle_t t, const char *buffer, int length, int timeout)
{
    bounded_tls_t *b = esp_transport_get_context_data(t);
    int wait = tls_timeout(b, timeout);
    return wait < 0 ? -1 : esp_transport_write(b->tls, buffer, length, wait);
}
static int tls_close(esp_transport_handle_t t)
{
    bounded_tls_t *b = esp_transport_get_context_data(t);
    return esp_transport_close(b->tls);
}

static bool remaining(esp_http_client_handle_t client, uint64_t deadline,
                      const egolink_p0_delivery_post_request_t *request)
{
    uint64_t now = now_ms();
    if (cancelled(request) || now >= deadline) return false;
    uint64_t left = deadline - now;
    return esp_http_client_set_timeout_ms(client, (int)(left > 1000U ? 1000U : left)) == ESP_OK;
}

#define REUSE_MAX_AGE_MS UINT64_C(60000)
#define REUSE_MAX_RESPONSES UINT32_C(24)
typedef struct {
    bounded_tls_t bound;
    esp_transport_handle_t transport;
    esp_http_client_handle_t client;
    uint64_t created_ms;
    uint32_t responses;
    bool close_requested;
    char url[256];
    char host[254];
    char bearer[161];
    char interface_name[16];
#if CONFIG_EGOLINK_COLLECTION_PROFILE
    struct ifreq interface;
#endif
} https_connection_t;

static void clear_active(https_connection_t *state)
{
    state->bound.active = false;
    state->bound.cancel_requested = NULL;
    state->bound.cancel_context = NULL;
    state->bound.generation = 0U;
    state->bound.deadline = 0U;
    state->bound.received = 0U;
}

static void release_connection(https_connection_t *state)
{
    if (!state) return;
    clear_active(state);
    if (state->client) {
        (void)esp_http_client_close(state->client);
        (void)esp_http_client_cleanup(state->client);
    }
    if (state->transport) (void)esp_transport_destroy(state->transport);
    if (state->bound.tls) (void)esp_transport_destroy(state->bound.tls);
    volatile unsigned char *bytes = (volatile unsigned char *)state;
    for (size_t i = 0U; i < sizeof(*state); ++i) bytes[i] = 0U;
}

void egolink_esp_p0_https_close(egolink_esp_p0_https_t *context)
{
    if (!context || !context->connection_state) return;
    https_connection_t *state = context->connection_state;
    context->connection_state = NULL;
    release_connection(state);
    free(state);
}

#if CONFIG_EGOLINK_COLLECTION_PROFILE
/* esp_netif_get_netif_impl_name() returns lwIP's short implementation name.
 * Accept only the two route families composed by the collector. The prefix is
 * also the fail-closed transport label; callers cannot claim Wi-Fi on PPP. */
static const char *collection_interface_transport(const char *name)
{
    if (!name) return NULL;
    size_t length = strlen(name);
    if (length < 3U || length > 5U) return NULL;
    const char *transport = NULL;
    if (name[0] == 's' && name[1] == 't') transport = "wifi";
    else if (name[0] == 'p' && name[1] == 'p') transport = "lte";
    else return NULL;
    for (const char *p = name + 2; *p; ++p)
        if (*p < '0' || *p > '9') return NULL;
    return transport;
}
#endif

#if CONFIG_EGOLINK_COLLECTION_PROFILE
static unsigned char lower_ascii(unsigned char c)
{
    return c >= 'A' && c <= 'Z' ? (unsigned char)(c + ('a' - 'A')) : c;
}

static bool ascii_equal(const char *left, const char *right)
{
    if (!left || !right) return false;
    while (*left && *right) {
        if (lower_ascii((unsigned char)*left++) != lower_ascii((unsigned char)*right++)) return false;
    }
    return *left == *right;
}

static bool connection_header_closes(const char *value)
{
    if (!value) return false;
    while (*value) {
        while (*value == ',' || *value == ' ' || *value == '\t') ++value;
        const char *start = value;
        while (*value && *value != ',') ++value;
        const char *end = value;
        while (end > start && (end[-1] == ' ' || end[-1] == '\t')) --end;
        if (end - start == 5 && lower_ascii(start[0]) == 'c' &&
            lower_ascii(start[1]) == 'l' && lower_ascii(start[2]) == 'o' &&
            lower_ascii(start[3]) == 's' && lower_ascii(start[4]) == 'e') return true;
    }
    return false;
}

static esp_err_t connection_event(esp_http_client_event_t *event)
{
    https_connection_t *state = event ? event->user_data : NULL;
    if (!state) return ESP_OK;
    if (event->event_id == HTTP_EVENT_DISCONNECTED || event->event_id == HTTP_EVENT_ERROR ||
        (event->event_id == HTTP_EVENT_ON_HEADER && ascii_equal(event->header_key, "Connection") &&
         connection_header_closes(event->header_value))) state->close_requested = true;
    return ESP_OK;
}
#endif

static egolink_p0_delivery_post_outcome_t post_exact(
    void *context, const egolink_p0_delivery_post_request_t *r,
    egolink_p0_delivery_post_result_t *result, const char *interface_name,
    bool collection, int method, const char *content_type,
    const char *content_sha256, size_t body_limit)
{
    egolink_esp_p0_https_t *c = context;
    const char *collection_transport = NULL;
#if CONFIG_EGOLINK_COLLECTION_PROFILE
    if (collection) collection_transport = collection_interface_transport(interface_name);
#endif
    if (!result) {
        egolink_esp_p0_https_close(c);
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    memset(result, 0, sizeof(*result));
    result->completion_time_ms = now_ms();
    bool get = method == 0;
    bool post = method == HTTP_METHOD_POST;
    if (!egolink_esp_p0_https_config_valid(c) || !r || !r->response ||
        !r->path || !(get || post) ||
        (get && (r->body || r->body_length)) ||
        (post && (!r->body || !r->body_length || r->body_length > body_limit || !content_type)) ||
        !r->response_capacity || r->response_capacity > EGOLINK_P0_DELIVERY_RUNTIME_RESPONSE_BYTES ||
        (collection && !collection_transport) ||
        !(collection || (r->route == EGOLINK_P0_OUTBOX_ROUTE_LOCATION_STATE &&
           strcmp(r->path, EGOLINK_P0_OUTBOX_LOCATION_ENDPOINT_PATH) == 0) ||
          (r->route == EGOLINK_P0_OUTBOX_ROUTE_MANUAL_SOS &&
           r->priority == EGOLINK_OUTBOX_PRIORITY_CRITICAL &&
           strcmp(r->path, EGOLINK_P0_OUTBOX_MANUAL_SOS_ENDPOINT_PATH) == 0))) {
        egolink_esp_p0_https_close(c);
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    memset(r->response, 0, r->response_capacity);
    if (cancelled(r)) {
        egolink_esp_p0_https_close(c);
        return EGOLINK_P0_DELIVERY_POST_CANCELLED;
    }
    if (c->attempts >= c->max_attempts || now_ms() >= c->deadline_ms) {
        egolink_esp_p0_https_close(c);
        result->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TIMEOUT;
        return EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED;
    }
    /* Certificate validity must be checked against a plausible synchronized
     * clock. SNTP establishment is separate from source monotonic event time. */
    if (time(NULL) < 1767225600) {
        egolink_esp_p0_https_close(c);
        result->transport_error = EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TLS;
        return EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED;
    }
    ++c->attempts;
    uint64_t deadline = now_ms() + c->transaction_timeout_ms;
    if (deadline > c->deadline_ms) deadline = c->deadline_ms;
    char url[256], authorization[168];
    int n = snprintf(url, sizeof(url), "%s%s", c->origin, r->path);
    if (n < 0 || (size_t)n >= sizeof(url)) {
        egolink_esp_p0_https_close(c);
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    (void)snprintf(authorization, sizeof(authorization), "Bearer %s", c->bearer);
    bool reuse = false;
#if CONFIG_EGOLINK_COLLECTION_PROFILE
    reuse = collection && c->reuse_connection;
#endif
    https_connection_t local = {0};
    https_connection_t *state = c->connection_state;
    if (state && (!reuse || strcmp(state->url, url) || strcmp(state->host, c->expected_host) ||
        strcmp(state->bearer, c->bearer) || !interface_name ||
        strcmp(state->interface_name, interface_name) || state->close_requested ||
        now_ms() < state->created_ms || now_ms() - state->created_ms >= REUSE_MAX_AGE_MS ||
        state->responses >= REUSE_MAX_RESPONSES)) {
        egolink_esp_p0_https_close(c);
        state = NULL;
    }
    if (!state) {
        state = reuse ? calloc(1U, sizeof(*state)) : &local;
        if (reuse) c->connection_state = state;
    }
    bool complete = false;
    bool tls_validation_failed = false;
    size_t written = 0U, received = 0U;
    int status = 0;
    esp_http_client_handle_t client = state ? state->client : NULL;
    if (!state) goto finish;
    state->bound.cancel_requested = r->cancel_requested;
    state->bound.cancel_context = r->cancel_context;
    state->bound.generation = r->transfer_generation;
    state->bound.deadline = deadline;
    state->bound.received = 0U;
    state->bound.active = true;
    state->close_requested = false;
    if (!client) {
        if (strlen(c->expected_host) >= sizeof(state->host) ||
            (interface_name && strlen(interface_name) >= sizeof(state->interface_name))) goto finish;
        memcpy(state->url, url, strlen(url) + 1U);
        memcpy(state->host, c->expected_host, strlen(c->expected_host) + 1U);
        memcpy(state->bearer, c->bearer, strlen(c->bearer) + 1U);
        if (interface_name) memcpy(state->interface_name, interface_name, strlen(interface_name) + 1U);
        state->created_ms = now_ms();
        state->bound.host = state->host;
        state->bound.tls = esp_transport_ssl_init();
        state->transport = esp_transport_init();
        if (!state->bound.tls || !state->transport) goto finish;
        esp_transport_ssl_crt_bundle_attach(state->bound.tls, esp_crt_bundle_attach);
#if CONFIG_EGOLINK_COLLECTION_PROFILE
        if (collection) {
            if (!interface_name || strlen(interface_name) >= sizeof(state->interface.ifr_name)) goto finish;
            memcpy(state->interface.ifr_name, interface_name, strlen(interface_name));
            esp_transport_ssl_set_interface_name(state->bound.tls, &state->interface);
        }
#else
        (void)interface_name;
#endif
        if (esp_transport_set_context_data(state->transport, &state->bound) != ESP_OK ||
        esp_transport_set_default_port(state->transport, 443) != ESP_OK ||
        esp_transport_set_func(state->transport, tls_connect, tls_read, tls_write,
            tls_close, NULL, NULL, NULL) != ESP_OK) goto finish;
        const esp_http_client_config_t cfg = {
        .url = state->url, .method = method,
        .transport_type = HTTP_TRANSPORT_OVER_SSL,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .skip_cert_common_name_check = false,
        .disable_auto_redirect = true, .max_redirection_count = 0,
        .timeout_ms = 1000, .keep_alive_enable = reuse,
#if CONFIG_EGOLINK_COLLECTION_PROFILE
        .event_handler = reuse ? connection_event : NULL,
        .user_data = reuse ? state : NULL,
#endif
#if CONFIG_ESP_HTTP_CLIENT_ENABLE_CUSTOM_TRANSPORT
        .transport = state->transport,
#endif
        };
        client = esp_http_client_init(&cfg);
        state->client = client;
    }
    if (!client) goto finish;
    if (esp_http_client_set_header(client, "Authorization", authorization) != ESP_OK ||
        (content_type && esp_http_client_set_header(client, "Content-Type", content_type) != ESP_OK) ||
        (collection && esp_http_client_set_header(client, "X-EgoLink-Transport", collection_transport) != ESP_OK) ||
        (content_sha256 && esp_http_client_set_header(client, "X-Content-SHA256", content_sha256) != ESP_OK) ||
        (reuse && esp_http_client_set_header(client, "Connection", "keep-alive") != ESP_OK) ||
        !remaining(client, deadline, r) ||
        esp_http_client_open(client, (int)r->body_length) != ESP_OK) goto finish;
    while (written < r->body_length) {
        if (!remaining(client, deadline, r)) goto finish;
        int amount = esp_http_client_write(client, (const char *)r->body + written,
                                           (int)(r->body_length - written));
        if (amount <= 0 || (size_t)amount > r->body_length - written) goto finish;
        written += (size_t)amount;
    }
    if (!remaining(client, deadline, r)) goto finish;
    int64_t declared = esp_http_client_fetch_headers(client);
    if (declared < 0 || declared > (int64_t)r->response_capacity) goto finish;
    status = esp_http_client_get_status_code(client);
    /* Explicit length only for this small server ACK: no close-delimited or
     * chunked ambiguity, no partial success and no redirect with credentials. */
    if (status < 100 || status > 599 || esp_http_client_is_chunked_response(client)) goto finish;
    while (received < (size_t)declared) {
        if (!remaining(client, deadline, r)) goto finish;
        int amount = esp_http_client_read(client, (char *)r->response + received,
                                          (int)((size_t)declared - received));
        if (amount <= 0 || (size_t)amount > (size_t)declared - received) goto finish;
        received += (size_t)amount;
    }
    complete = remaining(client, deadline, r) && esp_http_client_is_complete_data_received(client);
finish:
#if CONFIG_EGOLINK_COLLECTION_PROFILE
    if(!complete && state && state->bound.tls) {
        int tls_code=0,tls_flags=0;
        (void)esp_tls_get_and_clear_last_error(esp_transport_get_error_handle(state->bound.tls),&tls_code,&tls_flags);
        tls_validation_failed=tls_flags!=0;
    }
#endif
    bool finished = complete && !cancelled(r) && now_ms() < deadline;
    bool keep = reuse && state && finished && status >= 200 && status < 300 &&
        !state->close_requested && now_ms() >= state->created_ms &&
        now_ms() - state->created_ms < REUSE_MAX_AGE_MS &&
        state->responses + 1U < REUSE_MAX_RESPONSES;
    if (keep) {
        ++state->responses;
        clear_active(state);
    } else if (reuse) {
        egolink_esp_p0_https_close(c);
    } else {
        release_connection(state);
    }
    volatile char *secret = authorization;
    for (size_t i = 0U; i < sizeof(authorization); ++i) secret[i] = 0;
    result->completion_time_ms = now_ms();
    if (cancelled(r)) {
        egolink_esp_p0_https_close(c);
        memset(r->response, 0, r->response_capacity);
        return EGOLINK_P0_DELIVERY_POST_CANCELLED;
    }
    if (finished && result->completion_time_ms < deadline) {
        result->http_status_code = (uint16_t)status;
        result->response_length = received;
        ++c->complete_responses;
        return EGOLINK_P0_DELIVERY_POST_HTTP_RESPONSE;
    }
    egolink_esp_p0_https_close(c);
    memset(r->response, 0, r->response_capacity);
    result->transport_error = tls_validation_failed ? EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_TLS : EGOLINK_P0_DELIVERY_TRANSPORT_ERROR_IO;
    return EGOLINK_P0_DELIVERY_POST_TRANSPORT_FAILED;
}

/* Legacy routes retain the original validation and native behavior. */
egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_post(
    void *context, const egolink_p0_delivery_post_request_t *r,
    egolink_p0_delivery_post_result_t *result)
{
    return post_exact(context, r, result, NULL, false, HTTP_METHOD_POST,
        "application/json", NULL, EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES);
}
#if CONFIG_EGOLINK_COLLECTION_PROFILE
static bool bounded_identifier(const char *value,size_t maximum)
{
    if(!value)return false;
    size_t length=strlen(value);
    if(!length||length>maximum||
       !((value[0]>='a'&&value[0]<='z')||(value[0]>='A'&&value[0]<='Z')||
         (value[0]>='0'&&value[0]<='9')))return false;
    for(const char *p=value+1;*p;++p)
        if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||
             *p=='-'||*p=='_'||*p=='.'||*p==':'||*p=='@'))return false;
    return true;
}

static bool sha256_hex_valid(const char *value)
{
    if(!value||strlen(value)!=64U)return false;
    for(const char *p=value;*p;++p)
        if(!((*p>='0'&&*p<='9')||(*p>='a'&&*p<='f')))return false;
    return true;
}

egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_post_collection(
    egolink_esp_p0_https_t *context, const char *device_id, const char *interface_name,
    const egolink_p0_delivery_post_request_t *r, egolink_p0_delivery_post_result_t *result)
{
    if (result) memset(result,0,sizeof(*result));
    if (!r || !device_id || !*device_id || strlen(device_id) > 64U ||
        !collection_interface_transport(interface_name)) {
        egolink_esp_p0_https_close(context);
        return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    for (const char *p=device_id; *p; ++p)
        if (!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='-'||*p=='_')) {
            egolink_esp_p0_https_close(context);
            return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
        }
    char path[128];
    snprintf(path, sizeof(path), "/api/v1/devices/%s/raw-ingest", device_id);
    egolink_p0_delivery_post_request_t request = *r;
    request.path = path;
    return post_exact(context, &request, result, interface_name, true,
        HTTP_METHOD_POST,"application/octet-stream",NULL,
        EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES);
}

egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_poll_collection_command(
    egolink_esp_p0_https_t *context,const char *device_id,const char *interface_name,
    uint8_t *response,size_t response_capacity,
    egolink_p0_delivery_cancel_probe_fn cancel_requested,void *cancel_context,
    uint32_t transfer_generation,egolink_p0_delivery_post_result_t *result)
{
    if(result)memset(result,0,sizeof(*result));
    if(!bounded_identifier(device_id,64U)||!collection_interface_transport(interface_name)){
        egolink_esp_p0_https_close(context);return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    char path[128];
    int n=snprintf(path,sizeof(path),"/api/v1/devices/%s/commands/poll.raw",device_id);
    if(n<=0||(size_t)n>=sizeof(path)){
        egolink_esp_p0_https_close(context);return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    egolink_p0_delivery_post_request_t request={.path=path,.body=NULL,.body_length=0U,
        .response=response,.response_capacity=response_capacity,
        .cancel_requested=cancel_requested,.cancel_context=cancel_context,
        .transfer_generation=transfer_generation};
    return post_exact(context,&request,result,interface_name,true,0,
        NULL,NULL,0U);
}

egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_ack_collection_command(
    egolink_esp_p0_https_t *context,const char *device_id,const char *cmd_id,
    const char *interface_name,const uint8_t *frame,size_t frame_bytes,
    uint8_t *response,size_t response_capacity,
    egolink_p0_delivery_cancel_probe_fn cancel_requested,void *cancel_context,
    uint32_t transfer_generation,egolink_p0_delivery_post_result_t *result)
{
    if(result)memset(result,0,sizeof(*result));
    if(!bounded_identifier(device_id,64U)||!bounded_identifier(cmd_id,128U)||
       !collection_interface_transport(interface_name)){
        egolink_esp_p0_https_close(context);return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    char path[256];
    int n=snprintf(path,sizeof(path),"/api/v1/devices/%s/commands/%s/ack.raw",device_id,cmd_id);
    if(n<=0||(size_t)n>=sizeof(path)){
        egolink_esp_p0_https_close(context);return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    egolink_p0_delivery_post_request_t request={.path=path,.body=frame,.body_length=frame_bytes,
        .response=response,.response_capacity=response_capacity,
        .cancel_requested=cancel_requested,.cancel_context=cancel_context,
        .transfer_generation=transfer_generation};
    return post_exact(context,&request,result,interface_name,true,HTTP_METHOD_POST,
        "text/x-egolink-frame; profile=raw-frame.p0.v1",NULL,
        EGOLINK_OUTBOX_MAX_PAYLOAD_BYTES);
}

egolink_p0_delivery_post_outcome_t egolink_esp_p0_https_upload_collection_photo(
    egolink_esp_p0_https_t *context,const char *device_id,const char *photo_id,
    const char sha256_hex[65],const char *interface_name,const uint8_t *jpeg,
    size_t jpeg_bytes,uint8_t *response,size_t response_capacity,
    egolink_p0_delivery_cancel_probe_fn cancel_requested,void *cancel_context,
    uint32_t transfer_generation,egolink_p0_delivery_post_result_t *result)
{
    if(result)memset(result,0,sizeof(*result));
    if(!bounded_identifier(device_id,64U)||!bounded_identifier(photo_id,128U)||
       !sha256_hex_valid(sha256_hex)||!collection_interface_transport(interface_name)||
       !jpeg||jpeg_bytes<4U||jpeg_bytes>65536U||jpeg[0]!=0xffU||jpeg[1]!=0xd8U||
       jpeg[jpeg_bytes-2U]!=0xffU||jpeg[jpeg_bytes-1U]!=0xd9U){
        egolink_esp_p0_https_close(context);return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    char path[256];
    int n=snprintf(path,sizeof(path),"/api/v1/devices/%s/photos/%s/content",device_id,photo_id);
    if(n<=0||(size_t)n>=sizeof(path)){
        egolink_esp_p0_https_close(context);return EGOLINK_P0_DELIVERY_POST_CALLBACK_FAILED;
    }
    egolink_p0_delivery_post_request_t request={.path=path,.body=jpeg,.body_length=jpeg_bytes,
        .response=response,.response_capacity=response_capacity,
        .cancel_requested=cancel_requested,.cancel_context=cancel_context,
        .transfer_generation=transfer_generation};
    return post_exact(context,&request,result,interface_name,true,HTTP_METHOD_POST,
        "image/jpeg",sha256_hex,65536U);
}
#endif

#ifndef SIM7670_HTTP_EXACT_PARSER_H
#define SIM7670_HTTP_EXACT_PARSER_H

#include <stddef.h>
#include <stdint.h>

typedef enum {
    SIM7670_HTTP_EXACT_PARSE_NEED_MORE = 0,
    SIM7670_HTTP_EXACT_PARSE_COMPLETE,
    SIM7670_HTTP_EXACT_PARSE_INVALID,
} sim7670_http_exact_parse_status_t;

/*
 * Strict dormant P0 request validators. URL accepts only https://, a lowercase
 * DNS authority with labels of at most 63 bytes, no userinfo/port/IP literal,
 * and one of the two fixed P0 delivery paths. The origin matcher applies the
 * exact same authority validator to a host-only origin and expected TLS host.
 * Bearer accepts the reviewed Message Hub token alphabet; placeholder text is
 * rejected. None of these functions performs I/O.
 */
int sim7670_http_exact_url_is_valid(const char *url);
int sim7670_http_exact_https_origin_matches_dns_host(
    const char *origin,
    const char *expected_host);
int sim7670_http_exact_bearer_is_valid(const char *bearer_token);

/* Parses only a line-bound POST +HTTPACTION and requires method=1/status=100..599. */
int sim7670_http_exact_parse_action(
    const uint8_t *response,
    size_t response_length,
    uint16_t *status_code,
    size_t *data_length);

/*
 * Extracts exactly expected_length bytes from a complete +HTTPREAD frame.
 * Prefix command echo is allowed. A declared-length mismatch, malformed
 * header or non-terminal suffix is invalid; a partial frame is NEED_MORE.
 * body is not written unless COMPLETE is returned.
 */
sim7670_http_exact_parse_status_t sim7670_http_exact_extract_body(
    const uint8_t *wire,
    size_t wire_length,
    size_t expected_length,
    uint8_t *body,
    size_t body_capacity,
    size_t *body_length);

#endif /* SIM7670_HTTP_EXACT_PARSER_H */

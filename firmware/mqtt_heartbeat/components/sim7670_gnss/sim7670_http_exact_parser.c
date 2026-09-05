#include "sim7670_http_exact_parser.h"

#include <stdbool.h>
#include <string.h>

#define SIM7670_HTTP_EXACT_URL_MAX_BYTES 320U
#define SIM7670_HTTP_EXACT_HOST_MAX_BYTES 253U
#define SIM7670_HTTP_EXACT_DNS_LABEL_MAX_BYTES 63U
#define SIM7670_HTTP_EXACT_BEARER_MAX_BYTES 160U

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

static bool dns_host_is_valid(const char *host, size_t length)
{
    if (host == NULL || length == 0U ||
        length > SIM7670_HTTP_EXACT_HOST_MAX_BYTES || host[0] == '.' ||
        host[0] == '-' || host[length - 1U] == '.' ||
        host[length - 1U] == '-') {
        return false;
    }
    size_t label_length = 0U;
    bool has_alpha = false;
    for (size_t index = 0U; index < length; ++index) {
        const unsigned char ch = (unsigned char)host[index];
        const bool alpha =
            ch >= (unsigned char)'a' && ch <= (unsigned char)'z';
        const bool digit =
            ch >= (unsigned char)'0' && ch <= (unsigned char)'9';
        if (ch == (unsigned char)'.') {
            if (label_length == 0U || label_length >
                    SIM7670_HTTP_EXACT_DNS_LABEL_MAX_BYTES ||
                host[index - 1U] == '-') {
                return false;
            }
            label_length = 0U;
        } else if (alpha || digit || ch == (unsigned char)'-') {
            if (label_length == 0U && ch == (unsigned char)'-') {
                return false;
            }
            if (alpha) {
                has_alpha = true;
            }
            ++label_length;
        } else {
            return false;
        }
    }
    return has_alpha && label_length > 0U &&
           label_length <= SIM7670_HTTP_EXACT_DNS_LABEL_MAX_BYTES;
}

int sim7670_http_exact_https_origin_matches_dns_host(
    const char *origin,
    const char *expected_host)
{
    static const char scheme[] = "https://";
    size_t origin_length = 0U;
    size_t host_length = 0U;
    if (!bounded_text_length(
            origin, SIM7670_HTTP_EXACT_URL_MAX_BYTES, &origin_length) ||
        !bounded_text_length(
            expected_host,
            SIM7670_HTTP_EXACT_HOST_MAX_BYTES,
            &host_length) ||
        origin_length != sizeof(scheme) - 1U + host_length ||
        memcmp(origin, scheme, sizeof(scheme) - 1U) != 0 ||
        memcmp(
            origin + sizeof(scheme) - 1U,
            expected_host,
            host_length) != 0 ||
        !dns_host_is_valid(expected_host, host_length)) {
        return 0;
    }
    return 1;
}

int sim7670_http_exact_url_is_valid(const char *url)
{
    static const char scheme[] = "https://";
    static const char sos_path[] = "/api/v1/safety-events/manual-sos";
    static const char location_path[] = "/api/v1/location-states";
    size_t length = 0U;
    if (!bounded_text_length(
            url, SIM7670_HTTP_EXACT_URL_MAX_BYTES, &length) ||
        length <= sizeof(scheme) - 1U ||
        memcmp(url, scheme, sizeof(scheme) - 1U) != 0) {
        return 0;
    }
    const size_t authority_start = sizeof(scheme) - 1U;
    size_t authority_end = authority_start;
    while (authority_end < length && url[authority_end] != '/') {
        ++authority_end;
    }
    if (authority_end == authority_start || authority_end == length ||
        !dns_host_is_valid(
            url + authority_start, authority_end - authority_start)) {
        return 0;
    }
    const char *path = url + authority_end;
    return strcmp(path, sos_path) == 0 || strcmp(path, location_path) == 0;
}

int sim7670_http_exact_bearer_is_valid(const char *bearer_token)
{
    size_t length = 0U;
    if (!bounded_text_length(
            bearer_token,
            SIM7670_HTTP_EXACT_BEARER_MAX_BYTES,
            &length) ||
        bearer_token[0] == '<') {
        return 0;
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
            return 0;
        }
    }
    return 1;
}

static const uint8_t *find_line_marker(
    const uint8_t *haystack,
    size_t haystack_length,
    const char *needle,
    size_t needle_length)
{
    if (haystack == NULL || needle == NULL || needle_length == 0U ||
        haystack_length < needle_length) {
        return NULL;
    }
    for (size_t offset = 0U;
         offset <= haystack_length - needle_length;
         ++offset) {
        const bool at_line_start =
            offset == 0U || haystack[offset - 1U] == (uint8_t)'\n';
        if (at_line_start &&
            memcmp(haystack + offset, needle, needle_length) == 0) {
            return haystack + offset;
        }
    }
    return NULL;
}

static size_t count_line_markers(
    const uint8_t *bytes,
    size_t length,
    const char *marker,
    size_t marker_length)
{
    if (bytes == NULL || marker == NULL || marker_length == 0U ||
        length < marker_length) {
        return 0U;
    }
    size_t count = 0U;
    for (size_t offset = 0U; offset <= length - marker_length; ++offset) {
        const bool at_line_start =
            offset == 0U || bytes[offset - 1U] == (uint8_t)'\n';
        if (at_line_start &&
            memcmp(bytes + offset, marker, marker_length) == 0) {
            ++count;
        }
    }
    return count;
}

static bool line_has_terminal_error(
    const uint8_t *line,
    size_t line_length)
{
    static const char error[] = "ERROR";
    static const char cme[] = "+CME ERROR:";
    static const char cms[] = "+CMS ERROR:";
    return (line_length == sizeof(error) - 1U &&
            memcmp(line, error, sizeof(error) - 1U) == 0) ||
           (line_length >= sizeof(cme) - 1U &&
            memcmp(line, cme, sizeof(cme) - 1U) == 0) ||
           (line_length >= sizeof(cms) - 1U &&
            memcmp(line, cms, sizeof(cms) - 1U) == 0);
}

static bool contains_terminal_error_line(
    const uint8_t *bytes,
    size_t length)
{
    if (bytes == NULL) {
        return false;
    }
    size_t line_start = 0U;
    for (size_t offset = 0U; offset <= length; ++offset) {
        if (offset != length && bytes[offset] != (uint8_t)'\n') {
            continue;
        }
        size_t line_length = offset - line_start;
        if (line_length > 0U &&
            bytes[line_start + line_length - 1U] == (uint8_t)'\r') {
            --line_length;
        }
        if (line_has_terminal_error(bytes + line_start, line_length)) {
            return true;
        }
        line_start = offset + 1U;
    }
    return false;
}

static bool parse_decimal(
    const uint8_t *start,
    const uint8_t *end,
    size_t *value_out)
{
    if (start == NULL || end == NULL || value_out == NULL || start >= end) {
        return false;
    }
    size_t value = 0U;
    for (const uint8_t *cursor = start; cursor < end; ++cursor) {
        if (*cursor < (uint8_t)'0' || *cursor > (uint8_t)'9') {
            return false;
        }
        const size_t digit = (size_t)(*cursor - (uint8_t)'0');
        if (value > (SIZE_MAX - digit) / 10U) {
            return false;
        }
        value = value * 10U + digit;
    }
    *value_out = value;
    return true;
}

static const uint8_t *line_end_after(
    const uint8_t *start,
    const uint8_t *limit)
{
    if (start == NULL || limit == NULL || start >= limit) {
        return NULL;
    }
    for (const uint8_t *cursor = start; cursor < limit; ++cursor) {
        if (*cursor == (uint8_t)'\n') {
            return cursor;
        }
    }
    return NULL;
}

int sim7670_http_exact_parse_action(
    const uint8_t *response,
    size_t response_length,
    uint16_t *status_code,
    size_t *data_length)
{
    static const char marker[] = "+HTTPACTION:";
    if (response == NULL || status_code == NULL || data_length == NULL) {
        return 0;
    }
    if (contains_terminal_error_line(response, response_length) ||
        count_line_markers(
            response,
            response_length,
            marker,
            sizeof(marker) - 1U) != 1U) {
        return 0;
    }
    const uint8_t *const limit = response + response_length;
    const uint8_t *cursor = find_line_marker(
        response, response_length, marker, sizeof(marker) - 1U);
    if (cursor == NULL) {
        return 0;
    }
    cursor += sizeof(marker) - 1U;
    while (cursor < limit && *cursor == (uint8_t)' ') {
        ++cursor;
    }
    const uint8_t *const end = line_end_after(cursor, limit);
    if (end == NULL) {
        return 0;
    }
    const uint8_t *line_limit = end;
    if (line_limit > cursor && line_limit[-1] == (uint8_t)'\r') {
        --line_limit;
    }

    const uint8_t *comma_one = NULL;
    const uint8_t *comma_two = NULL;
    for (const uint8_t *scan = cursor; scan < line_limit; ++scan) {
        if (*scan == (uint8_t)',') {
            if (comma_one == NULL) {
                comma_one = scan;
            } else if (comma_two == NULL) {
                comma_two = scan;
            } else {
                return 0;
            }
        }
    }
    if (comma_one == NULL || comma_two == NULL) {
        return 0;
    }
    size_t method = 0U;
    size_t status = 0U;
    size_t length = 0U;
    if (!parse_decimal(cursor, comma_one, &method) ||
        !parse_decimal(comma_one + 1, comma_two, &status) ||
        !parse_decimal(comma_two + 1, line_limit, &length) ||
        method != 1U || status < 100U || status > 599U ||
        status > (size_t)UINT16_MAX) {
        return 0;
    }
    *status_code = (uint16_t)status;
    *data_length = length;
    return 1;
}

sim7670_http_exact_parse_status_t sim7670_http_exact_extract_body(
    const uint8_t *wire,
    size_t wire_length,
    size_t expected_length,
    uint8_t *body,
    size_t body_capacity,
    size_t *body_length)
{
    static const char marker[] = "+HTTPREAD:";
    static const uint8_t terminal[] = {'\r', '\n', 'O', 'K', '\r', '\n'};
    if (body_length != NULL) {
        *body_length = 0U;
    }
    if (wire == NULL || body == NULL || body_length == NULL ||
        expected_length == 0U || expected_length > body_capacity) {
        return SIM7670_HTTP_EXACT_PARSE_INVALID;
    }
    const uint8_t *const limit = wire + wire_length;
    const uint8_t *cursor = find_line_marker(
        wire, wire_length, marker, sizeof(marker) - 1U);
    if (cursor == NULL) {
        return SIM7670_HTTP_EXACT_PARSE_NEED_MORE;
    }
    if (contains_terminal_error_line(wire, (size_t)(cursor - wire))) {
        return SIM7670_HTTP_EXACT_PARSE_INVALID;
    }
    cursor += sizeof(marker) - 1U;
    while (cursor < limit && *cursor == (uint8_t)' ') {
        ++cursor;
    }
    const uint8_t *const newline = line_end_after(cursor, limit);
    if (newline == NULL) {
        return SIM7670_HTTP_EXACT_PARSE_NEED_MORE;
    }
    const uint8_t *declared_end = newline;
    if (declared_end > cursor && declared_end[-1] == (uint8_t)'\r') {
        --declared_end;
    }
    size_t declared_length = 0U;
    if (!parse_decimal(cursor, declared_end, &declared_length) ||
        declared_length != expected_length) {
        return SIM7670_HTTP_EXACT_PARSE_INVALID;
    }

    const uint8_t *const body_start = newline + 1;
    if ((size_t)(limit - body_start) < expected_length) {
        return SIM7670_HTTP_EXACT_PARSE_NEED_MORE;
    }
    const uint8_t *const after_body = body_start + expected_length;
    const size_t suffix_length = (size_t)(limit - after_body);
    if (suffix_length < sizeof(terminal)) {
        return SIM7670_HTTP_EXACT_PARSE_NEED_MORE;
    }
    if (memcmp(after_body, terminal, sizeof(terminal)) != 0) {
        return SIM7670_HTTP_EXACT_PARSE_INVALID;
    }
    for (const uint8_t *tail = after_body + sizeof(terminal);
         tail < limit;
         ++tail) {
        if (*tail != (uint8_t)'\r' && *tail != (uint8_t)'\n') {
            return SIM7670_HTTP_EXACT_PARSE_INVALID;
        }
    }
    memcpy(body, body_start, expected_length);
    *body_length = expected_length;
    return SIM7670_HTTP_EXACT_PARSE_COMPLETE;
}

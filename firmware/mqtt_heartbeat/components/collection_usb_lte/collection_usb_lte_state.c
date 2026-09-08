#include "collection_usb_lte_state.h"
#include <string.h>

void collection_usb_lte_state_init(collection_usb_lte_state_t *s)
{
    memset(s, 0, sizeof(*s));
    s->status.enabled = true;
    s->status.result = COLLECTION_USB_LTE_IDLE;
    s->status.quiesced = true;
    s->quiet = true;
}
void collection_usb_lte_state_connect(collection_usb_lte_state_t *s, bool connected)
{
    ++s->status.connection_epoch;
    s->status.usb_connected = connected;
    s->status.command_mode = false;
    s->status.data_mode = false;
    s->status.ppp_has_ip = false;
    s->status.hangup_confirmed = false;
    s->status.last_modem_result[0] = '\0';
    s->pending = false;
    s->uncertain = false;
    s->cancelled = false;
    s->rx_size = 0;
    s->quiet = true;
    s->status.quiesced = true;
    s->status.result = connected ? COLLECTION_USB_LTE_IDLE : COLLECTION_USB_LTE_DISCONNECTED;
}
void collection_usb_lte_state_fail(collection_usb_lte_state_t *s, collection_usb_lte_result_t result)
{
    s->pending = false;
    s->status.result = result;
    s->status.command_mode = false;
    s->status.data_mode = false;
    s->status.ppp_has_ip = false;
    s->status.hangup_confirmed = false;
    s->uncertain = true;
    s->quiet = true;
    s->status.quiesced = true;
    s->rx_size = 0;
}
void collection_usb_lte_state_quiesce(collection_usb_lte_state_t *s)
{
    if (s->pending) collection_usb_lte_state_fail(s, COLLECTION_USB_LTE_CANCELLED);
    s->quiet = true;
    s->status.quiesced = true;
    s->status.ppp_has_ip = false;
}
const char *collection_usb_lte_state_begin(collection_usb_lte_state_t *s,
    collection_usb_lte_operation_t op, uint64_t now, uint32_t timeout)
{
    static const char *const commands[] = {"AT\r\n", "ATE0\r\n", "ATD*99***1#\r\n", "+++", "ATH\r\n"};
    if (!s->status.usb_connected || s->pending || timeout < 100 || timeout > 10000 ||
        (unsigned)op >= sizeof(commands)/sizeof(commands[0])) return NULL;
    if (op == COLLECTION_USB_LTE_ESCAPE) {
        if (!s->quiet || now < s->last_tx_ms || now - s->last_tx_ms < 1000) return NULL;
    } else {
        if (s->status.data_mode || s->uncertain) return NULL;
        if (op != COLLECTION_USB_LTE_PROBE && !s->status.command_mode) return NULL;
    }
    s->status.operation = op;
    s->status.result = COLLECTION_USB_LTE_PENDING;
    s->status.last_modem_result[0] = '\0';
    s->status.hangup_confirmed = false;
    s->pending = true;
    s->cancelled = false;
    s->deadline_ms = now + timeout;
    s->rx_size = 0;
    s->rx_time_ms = 0;
    s->last_tx_ms = now;
    return commands[op];
}
void collection_usb_lte_state_feed(collection_usb_lte_state_t *s, const void *bytes, size_t size, uint64_t now)
{
    if (!s->pending) return; /* unsolicited lines never satisfy a future command */
    if (now > s->deadline_ms) return;
    if (size > sizeof(s->rx) - s->rx_size) {
        ++s->status.rx_overflows;
        collection_usb_lte_state_fail(s, COLLECTION_USB_LTE_OVERFLOW);
        return;
    }
    memcpy(s->rx + s->rx_size, bytes, size);
    s->rx_size += size;
    s->rx_time_ms = now;
}
static bool line_is(const unsigned char *line, size_t length, const char *expected)
{
    return length == strlen(expected) && memcmp(line, expected, length) == 0;
}
collection_usb_lte_result_t collection_usb_lte_state_poll(collection_usb_lte_state_t *s, uint64_t now)
{
    if (!s->pending) return s->status.result;
    if (s->cancelled) {
        collection_usb_lte_state_fail(s, COLLECTION_USB_LTE_CANCELLED);
        return s->status.result;
    }
    size_t used = 0;
    for (size_t i = 0; i + 1 < s->rx_size; ++i) {
        if (s->rx[i] != '\r' || s->rx[i + 1] != '\n') continue;
        const unsigned char *line = s->rx + used;
        size_t length = i - used;
        bool error = line_is(line, length, "ERROR") || line_is(line, length, "NO CARRIER") ||
            line_is(line, length, "BUSY") || line_is(line, length, "NO ANSWER") ||
            (length >= 11 && memcmp(line, "+CME ERROR:", 11) == 0);
        bool ok = s->status.operation == COLLECTION_USB_LTE_DIAL ?
            line_is(line, length, "CONNECT") : line_is(line, length, "OK");
        used = i + 2;
        ++i;
        if (error || ok) {
            size_t save = length < sizeof(s->status.last_modem_result) - 1 ?
                length : sizeof(s->status.last_modem_result) - 1;
            memcpy(s->status.last_modem_result, line, save);
            s->status.last_modem_result[save] = '\0';
        }
        if (error) {
            collection_usb_lte_state_fail(s, COLLECTION_USB_LTE_MODEM_ERROR);
            return s->status.result;
        }
        if (ok) {
            s->pending = false;
            s->uncertain = false;
            s->status.result = COLLECTION_USB_LTE_OK;
            s->status.data_mode = s->status.operation == COLLECTION_USB_LTE_DIAL;
            s->status.command_mode = !s->status.data_mode;
            s->status.hangup_confirmed = s->status.operation == COLLECTION_USB_LTE_HANGUP;
            s->rx_size -= used;
            memmove(s->rx, s->rx + used, s->rx_size); /* preserve PPP after CONNECT */
            return s->status.result;
        }
    }
    if (used) {
        s->rx_size -= used;
        memmove(s->rx, s->rx + used, s->rx_size);
    }
    if (now >= s->deadline_ms) collection_usb_lte_state_fail(s, COLLECTION_USB_LTE_TIMEOUT);
    return s->status.result;
}

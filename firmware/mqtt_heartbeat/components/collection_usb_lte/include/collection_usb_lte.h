#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_netif.h"

/* No policy, retries, UART access, HTTP, APN guessing or autonomous AT task.
 * init/begin/poll/quiesce belong to the ONE existing modem owner task.
 * cancel/status/netif may be used from other tasks. Objects live until reboot:
 * quiesce disables PPP output and requests netif stop; it does not power off
 * the modem, destroy active USB objects, or claim ATH was acknowledged. */
typedef enum {
    COLLECTION_USB_LTE_IDLE, COLLECTION_USB_LTE_PENDING,
    COLLECTION_USB_LTE_OK, COLLECTION_USB_LTE_TIMEOUT,
    COLLECTION_USB_LTE_CANCELLED, COLLECTION_USB_LTE_DISCONNECTED,
    COLLECTION_USB_LTE_MODEM_ERROR, COLLECTION_USB_LTE_IO_ERROR,
    COLLECTION_USB_LTE_OVERFLOW, COLLECTION_USB_LTE_BAD_STATE,
    COLLECTION_USB_LTE_STALE_EPOCH,
    COLLECTION_USB_LTE_DISABLED
} collection_usb_lte_result_t;
typedef enum {
    COLLECTION_USB_LTE_PROBE,       /* AT, one attempt */
    COLLECTION_USB_LTE_ECHO_OFF,    /* ATE0, one attempt */
    COLLECTION_USB_LTE_DIAL,        /* ATD*99***1#, CID 1 prepared by owner */
    COLLECTION_USB_LTE_ESCAPE,      /* +++, only after quiesce + 1 s TX guard */
    COLLECTION_USB_LTE_HANGUP        /* ATH, only after command mode confirmed */
} collection_usb_lte_operation_t;
typedef struct {
    uint16_t vendor_id, product_id;
    int modem_interface;            /* explicit descriptor evidence; -1 invalid */
    bool descriptor_verified;       /* never inferred from a SIMCom model name */
    bool usb_host_already_installed;
} collection_usb_lte_config_t;
typedef struct {
    bool enabled, initialized, usb_connected, command_mode, data_mode;
    bool ppp_has_ip, quiesced, hangup_confirmed, driver_objects_retained;
    bool ppp_stopped;               /* observed PPP DEAD; separate from ATH */
    int32_t last_ppp_event;
    char last_modem_result[64];     /* terminal result line only, never command echo */
    collection_usb_lte_operation_t operation;
    collection_usb_lte_result_t result;
    esp_err_t last_io_error;
    uint32_t connection_epoch, rx_overflows, ppp_rx_bytes, ppp_tx_bytes;
} collection_usb_lte_status_t;

esp_err_t collection_usb_lte_init(const collection_usb_lte_config_t *config);
/* Nonblocking command begin: at most two 25 ms USB waits, no response wait.
 * timeout_ms is 100..10000, measured from begin including USB submission.
 * Call poll regularly; it never sends another command or retries.
 * A successful DIAL starts PPP negotiation; OK does not mean IP/TLS ready. */
collection_usb_lte_result_t collection_usb_lte_begin(
    collection_usb_lte_operation_t operation, uint32_t timeout_ms);
collection_usb_lte_result_t collection_usb_lte_poll(void);
void collection_usb_lte_cancel(void);
esp_err_t collection_usb_lte_quiesce(void);
/* Owner-only maintenance for a generation-tagged netif retained by a physical
 * disconnect. It never polls/cancels a command or starts a PPP lifecycle. */
collection_usb_lte_result_t collection_usb_lte_service(void);
/* Owner-only epoch-scoped operations. The epoch comparison and any state
 * mutation occur under the same connector gate. Before that comparison a
 * caller may retire only a generation-tagged netif residue left by a physical
 * disconnect; STALE_EPOCH never cancels, polls, submits, starts or quiesces the
 * newly connected lifecycle. */
collection_usb_lte_result_t collection_usb_lte_begin_for_epoch(
    collection_usb_lte_operation_t operation,
    uint32_t timeout_ms,
    uint32_t expected_epoch);
collection_usb_lte_result_t collection_usb_lte_poll_for_epoch(
    uint32_t expected_epoch);
collection_usb_lte_result_t collection_usb_lte_cancel_poll_for_epoch(
    uint32_t expected_epoch);
collection_usb_lte_result_t collection_usb_lte_quiesce_for_epoch(
    uint32_t expected_epoch);
void collection_usb_lte_get_status(collection_usb_lte_status_t *status);
esp_netif_t *collection_usb_lte_netif(void);
const char *collection_usb_lte_result_name(collection_usb_lte_result_t result);

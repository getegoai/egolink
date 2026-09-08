#pragma once
#include <stddef.h>
#include "collection_usb_lte.h"

/* Serialized by the connector RX mutex, also used by native thread tests. */
typedef struct {
    collection_usb_lte_status_t status;
    bool pending, uncertain, cancelled, quiet;
    uint64_t deadline_ms, last_tx_ms, rx_time_ms;
    unsigned char rx[2048];
    size_t rx_size;
} collection_usb_lte_state_t;
void collection_usb_lte_state_init(collection_usb_lte_state_t *s);
void collection_usb_lte_state_connect(collection_usb_lte_state_t *s, bool connected);
const char *collection_usb_lte_state_begin(collection_usb_lte_state_t *s,
    collection_usb_lte_operation_t op, uint64_t now_ms, uint32_t timeout_ms);
void collection_usb_lte_state_feed(collection_usb_lte_state_t *s,
    const void *bytes, size_t size, uint64_t now_ms);
collection_usb_lte_result_t collection_usb_lte_state_poll(
    collection_usb_lte_state_t *s, uint64_t now_ms);
void collection_usb_lte_state_fail(collection_usb_lte_state_t *s,
    collection_usb_lte_result_t result);
void collection_usb_lte_state_quiesce(collection_usb_lte_state_t *s);

/*
 * SPDX-FileCopyrightText: 2023-2025 Espressif Systems (Shanghai) CO LTD
 * SPDX-FileCopyrightText: 2026 EgoLink contributors
 * SPDX-License-Identifier: Apache-2.0
 * CDC/PPP DTE wiring adapted from iot_usbh_modem 2.2.0, commit
 * a2dd58acf2fef837c9d5e2e86b7e33d318b6b2ff. See UPSTREAM.md.
 */
#include "collection_usb_lte.h"
#include "sdkconfig.h"
#include <string.h>

const char *collection_usb_lte_result_name(collection_usb_lte_result_t r)
{
    static const char *const names[] = {"idle", "pending", "ok", "timeout", "cancelled",
        "disconnected", "modem_error", "io_error", "overflow", "bad_state",
        "stale_epoch", "disabled"};
    return (unsigned)r < sizeof(names)/sizeof(names[0]) ? names[r] : "unknown";
}

#if !CONFIG_EGOLINK_COLLECTION_USB_LTE
esp_err_t collection_usb_lte_init(const collection_usb_lte_config_t *c)
{ (void)c; return ESP_ERR_NOT_SUPPORTED; }
collection_usb_lte_result_t collection_usb_lte_begin(collection_usb_lte_operation_t op, uint32_t ms)
{ (void)op; (void)ms; return COLLECTION_USB_LTE_DISABLED; }
collection_usb_lte_result_t collection_usb_lte_poll(void) { return COLLECTION_USB_LTE_DISABLED; }
void collection_usb_lte_cancel(void) {}
esp_err_t collection_usb_lte_quiesce(void) { return ESP_ERR_NOT_SUPPORTED; }
collection_usb_lte_result_t collection_usb_lte_service(void)
{ return COLLECTION_USB_LTE_DISABLED; }
collection_usb_lte_result_t collection_usb_lte_begin_for_epoch(
    collection_usb_lte_operation_t op, uint32_t ms, uint32_t epoch)
{ (void)op; (void)ms; (void)epoch; return COLLECTION_USB_LTE_DISABLED; }
collection_usb_lte_result_t collection_usb_lte_poll_for_epoch(uint32_t epoch)
{ (void)epoch; return COLLECTION_USB_LTE_DISABLED; }
collection_usb_lte_result_t collection_usb_lte_cancel_poll_for_epoch(uint32_t epoch)
{ (void)epoch; return COLLECTION_USB_LTE_DISABLED; }
collection_usb_lte_result_t collection_usb_lte_quiesce_for_epoch(uint32_t epoch)
{ (void)epoch; return COLLECTION_USB_LTE_DISABLED; }
void collection_usb_lte_get_status(collection_usb_lte_status_t *s)
{ if (s) { memset(s, 0, sizeof(*s)); s->result = COLLECTION_USB_LTE_DISABLED; } }
esp_netif_t *collection_usb_lte_netif(void) { return NULL; }
#else
#include <stdatomic.h>
#include "collection_usb_lte_state.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_event.h"
#include "esp_timer.h"
#include "esp_netif_ppp.h"
#include "iot_usbh_cdc.h"
#include "iot_eth.h"
#include "iot_eth_types.h"
#include "iot_eth_interface.h"
#include "iot_eth_netif_glue.h"

/* The gate serializes the USB port lifetime with physical disconnect. Owner
 * entry is try-lock only. CDC callbacks wait for one bounded USB submission
 * (two 25 ms waits); no response wait or netif IPC holds this gate. Objects
 * remain allocated until reboot, including after init failure. */
static struct {
    collection_usb_lte_state_t state;
    collection_usb_lte_config_t config;
    SemaphoreHandle_t gate;
    TaskHandle_t owner;
    usbh_cdc_port_handle_t port;
    uint8_t dev_addr;
    iot_eth_driver_t driver;
    iot_eth_mediator_t *mediator;
    iot_eth_handle_t eth;
    iot_eth_netif_glue_handle_t glue;
    esp_netif_t *netif;
    esp_event_handler_instance_t ip_handler, lost_handler, ppp_handler;
    usb_device_match_id_t match[2];
    bool netif_started, attempted_init, disconnect_teardown_valid;
    uint32_t netif_connection_epoch, disconnect_teardown_epoch;
    atomic_bool cancel, disconnect_pending;
    uint8_t rx_buffer[1536];
} usb;

static uint64_t now_ms(void) { return (uint64_t)esp_timer_get_time() / 1000; }
static bool owner(void) { return usb.owner && usb.owner == xTaskGetCurrentTaskHandle(); }
static bool enter_owner(void) { return owner() && xSemaphoreTake(usb.gate, 0) == pdTRUE; }
static void leave(void) { xSemaphoreGive(usb.gate); }
static esp_err_t link_down(void)
{
    if (usb.eth && usb.netif_started) {
        esp_err_t e = iot_eth_stop(usb.eth); /* event queue, zero wait */
        if (e == ESP_OK) {
            usb.netif_started = false;
            usb.netif_connection_epoch = 0;
        }
        else usb.state.status.last_io_error = e;
        return e;
    }
    return ESP_OK;
}
static collection_usb_lte_result_t retire_disconnected_netif_locked(void)
{
    if (!atomic_load(&usb.disconnect_pending)) return COLLECTION_USB_LTE_OK;
    /* disconnect_pending is asserted before the callback waits for this gate
     * so transmit/command paths stop immediately. It cannot be drained until
     * the callback has committed the port/epoch snapshot under this gate. */
    if (!usb.disconnect_teardown_valid) return COLLECTION_USB_LTE_PENDING;
    /* No new PPP start is admitted while this flag is set. The epoch tag is
     * the lifecycle that owned the retained netif, not the currently opened
     * CDC port, so a stale caller can retire only that old residue. */
    if (usb.netif_started) {
        if (usb.netif_connection_epoch != usb.disconnect_teardown_epoch) {
            return COLLECTION_USB_LTE_BAD_STATE;
        }
        if (link_down() != ESP_OK) return COLLECTION_USB_LTE_IO_ERROR;
    }
    if (!usb.state.status.ppp_stopped) return COLLECTION_USB_LTE_PENDING;
    usb.disconnect_teardown_epoch = 0;
    usb.disconnect_teardown_valid = false;
    atomic_store(&usb.disconnect_pending, false);
    return COLLECTION_USB_LTE_OK;
}
static esp_err_t driver_set_mediator(iot_eth_driver_t *d, iot_eth_mediator_t *m)
{ (void)d; usb.mediator = m; return ESP_OK; }
static esp_err_t driver_init(iot_eth_driver_t *d) { (void)d; return ESP_OK; }
static esp_err_t driver_deinit(iot_eth_driver_t *d)
{ (void)d; return ESP_ERR_NOT_SUPPORTED; /* retained; no forced delete */ }
static esp_err_t driver_transmit(iot_eth_driver_t *d, uint8_t *bytes, size_t n)
{
    (void)d;
    if (!n || n > 1536 || xSemaphoreTake(usb.gate, 0) != pdTRUE) return ESP_ERR_INVALID_STATE;
    esp_err_t e = ESP_ERR_INVALID_STATE;
    if (usb.port && usb.state.status.data_mode && !usb.state.quiet &&
        !atomic_load(&usb.cancel) && !atomic_load(&usb.disconnect_pending)) {
        e = usbh_cdc_write_bytes(usb.port, bytes, n, pdMS_TO_TICKS(25));
        usb.state.last_tx_ms = now_ms();
        if (e == ESP_OK) usb.state.status.ppp_tx_bytes += (uint32_t)n;
        else usb.state.status.last_io_error = e;
    }
    leave();
    return e;
}
static void receive(usbh_cdc_port_handle_t port, void *context)
{
    (void)context;
    xSemaphoreTake(usb.gate, portMAX_DELAY);
    size_t n = 0;
    esp_err_t e = usbh_cdc_get_rx_buffer_size(port, &n);
    if (e != ESP_OK || !n) { leave(); return; }
    if (n > sizeof(usb.rx_buffer)) {
        ++usb.state.status.rx_overflows;
        collection_usb_lte_state_fail(&usb.state, COLLECTION_USB_LTE_OVERFLOW);
        leave(); return;
    }
    e = usbh_cdc_read_bytes(port, usb.rx_buffer, &n, 0);
    if (e != ESP_OK) {
        usb.state.status.last_io_error = e;
        collection_usb_lte_state_fail(&usb.state, COLLECTION_USB_LTE_IO_ERROR);
    } else if (usb.state.status.data_mode && !usb.state.quiet && !usb.state.pending && usb.netif_started) {
        /* PPP input copies bytes into lwIP's bounded input queue. Never AT. */
        e = usb.mediator->stack_input(usb.mediator, usb.rx_buffer, n);
        if (e == ESP_OK) usb.state.status.ppp_rx_bytes += (uint32_t)n;
        else { usb.state.status.last_io_error = e; ++usb.state.status.rx_overflows; }
    } else {
        collection_usb_lte_state_feed(&usb.state, usb.rx_buffer, n, now_ms());
    }
    leave();
}
static void usb_event(usbh_cdc_device_event_t event, usbh_cdc_device_event_data_t *data, void *context)
{
    (void)context;
    if (event == CDC_HOST_DEVICE_EVENT_DISCONNECTED) {
        if (data->dev_gone.dev_addr != usb.dev_addr) return;
        atomic_store(&usb.disconnect_pending, true); /* early I/O fence */
        xSemaphoreTake(usb.gate, portMAX_DELAY);
        usb.port = NULL; /* CDC closes after this callback; no stale pointer */
        if (!usb.disconnect_teardown_valid) {
            usb.disconnect_teardown_epoch = usb.netif_started
                ? usb.netif_connection_epoch
                : usb.state.status.connection_epoch;
        }
        collection_usb_lte_state_connect(&usb.state, false);
        usb.disconnect_teardown_valid = true;
        /* A prior owner may have observed the early fence while waiting for
         * this commit. Reassert it after the committed snapshot so that owner
         * retirement is never lost across that interleaving. */
        atomic_store(&usb.disconnect_pending, true);
        leave();
        return;
    }
    const usb_device_desc_t *desc = data->new_dev.device_desc;
    if (!desc || desc->idVendor != usb.config.vendor_id || desc->idProduct != usb.config.product_id) return;
    xSemaphoreTake(usb.gate, portMAX_DELAY);
    if (usb.port) { leave(); return; }
    usb.dev_addr = data->new_dev.dev_addr;
    usbh_cdc_port_config_t config = {
        .dev_addr = data->new_dev.dev_addr,
        .itf_num = (uint8_t)usb.config.modem_interface,
        .in_transfer_buffer_size = sizeof(usb.rx_buffer),
        .out_transfer_buffer_size = 1536,
        .cbs = {.recv_data = receive},
    };
    /* Open is USB enumeration, not an AT command. No software tries other
     * interfaces if the explicitly configured descriptor is wrong. */
    esp_err_t e = usbh_cdc_port_open(&config, &usb.port);
    usb.state.status.last_io_error = e;
    if (e == ESP_OK) {
        /* A quick reconnect must not erase an unfinished stop of the netif
         * retained from the disconnected lifecycle. The owner retires that
         * residue before any new command or PPP start can be admitted. */
        collection_usb_lte_state_connect(&usb.state, true);
    } else collection_usb_lte_state_fail(&usb.state, COLLECTION_USB_LTE_IO_ERROR);
    leave();
}
static void ip_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base;
    if (base == NETIF_PPP_STATUS) {
        if (!data || *(esp_netif_t **)data != usb.netif) return;
        xSemaphoreTake(usb.gate, portMAX_DELAY);
        usb.state.status.last_ppp_event = id;
        if (id == NETIF_PPP_PHASE_DEAD) usb.state.status.ppp_stopped = true;
        if (id == NETIF_PPP_PHASE_DEAD || (id > 0 && id < NETIF_PP_PHASE_OFFSET))
            usb.state.status.ppp_has_ip = false;
        leave();
        return;
    }
    if (id == IP_EVENT_PPP_GOT_IP) {
        ip_event_got_ip_t *event = data;
        if (!event || event->esp_netif != usb.netif) return;
        xSemaphoreTake(usb.gate, portMAX_DELAY);
        usb.state.status.ppp_has_ip = usb.state.status.usb_connected &&
            usb.state.status.data_mode && !usb.state.quiet && usb.netif_started;
        leave();
    } else if (id == IP_EVENT_PPP_LOST_IP) {
        ip_event_got_ip_t *event = data;
        if (!event || event->esp_netif != usb.netif) return;
        xSemaphoreTake(usb.gate, portMAX_DELAY);
        usb.state.status.ppp_has_ip = false;
        leave();
    }
}
esp_err_t collection_usb_lte_init(const collection_usb_lte_config_t *c)
{
    if (!c || !c->descriptor_verified || !c->vendor_id || !c->product_id ||
        c->modem_interface < 0 || c->modem_interface > 255) return ESP_ERR_INVALID_ARG;
    if (usb.attempted_init) return ESP_ERR_INVALID_STATE;
    usb.attempted_init = true;
    usb.config = *c;
    usb.owner = xTaskGetCurrentTaskHandle();
    collection_usb_lte_state_init(&usb.state);
    usb.state.status.ppp_stopped = true;
    usb.state.status.driver_objects_retained = true;
    usb.gate = xSemaphoreCreateMutex();
    if (!usb.gate) return ESP_ERR_NO_MEM;
    usb.driver = (iot_eth_driver_t){.name="collection_usb_ppp", .init=driver_init,
        .deinit=driver_deinit, .set_mediator=driver_set_mediator, .transmit=driver_transmit};
    iot_eth_config_t eth_cfg = {.driver=&usb.driver};
    esp_err_t e = iot_eth_install(&eth_cfg, &usb.eth);
    if (e != ESP_OK) goto fail;
    usb.glue = iot_eth_new_netif_glue(usb.eth);
    if (!usb.glue) { e = ESP_ERR_NO_MEM; goto fail; }
    esp_netif_inherent_config_t inherent = ESP_NETIF_INHERENT_DEFAULT_PPP();
    inherent.if_key = "EGO_USB_PPP";
    inherent.if_desc = "EgoLink LTE PPP";
    inherent.route_prio = 10; /* outer uploader binds the actual selected netif */
    esp_netif_config_t net_cfg = {.base=&inherent, .stack=ESP_NETIF_NETSTACK_DEFAULT_PPP};
    usb.netif = esp_netif_new(&net_cfg);
    if (!usb.netif) { e = ESP_ERR_NO_MEM; goto fail; }
    e = esp_netif_attach(usb.netif, usb.glue);
    if (e != ESP_OK) goto fail;
    esp_netif_ppp_config_t ppp = {.ppp_error_event_enabled=true, .ppp_phase_event_enabled=true};
    e = esp_netif_ppp_set_params(usb.netif, &ppp);
    if (e != ESP_OK) goto fail;
    e = esp_event_handler_instance_register(IP_EVENT, IP_EVENT_PPP_GOT_IP, ip_event, NULL, &usb.ip_handler);
    if (e != ESP_OK) goto fail;
    e = esp_event_handler_instance_register(IP_EVENT, IP_EVENT_PPP_LOST_IP, ip_event, NULL, &usb.lost_handler);
    if (e != ESP_OK) goto fail;
    e = esp_event_handler_instance_register(NETIF_PPP_STATUS, ESP_EVENT_ANY_ID, ip_event, NULL, &usb.ppp_handler);
    if (e != ESP_OK) goto fail;
    usbh_cdc_driver_config_t host = {.task_stack_size=4096, .task_priority=5,
        .task_coreid=0, .skip_init_usb_host_driver=c->usb_host_already_installed};
    e = usbh_cdc_driver_install(&host);
    if (e != ESP_OK) goto fail;
    usb.match[0] = (usb_device_match_id_t){.match_flags=USB_DEVICE_ID_MATCH_VID_PID,
        .idVendor=c->vendor_id, .idProduct=c->product_id};
    e = usbh_cdc_register_dev_event_cb(usb.match, usb_event, NULL);
    if (e != ESP_OK) goto fail;
    usb.state.status.initialized = true;
    return ESP_OK;
fail:
    usb.state.status.last_io_error = e;
    collection_usb_lte_state_fail(&usb.state, COLLECTION_USB_LTE_IO_ERROR);
    return e; /* retained objects, no destructive/unbounded rollback */
}
static collection_usb_lte_result_t begin_locked(
    collection_usb_lte_operation_t op, uint32_t ms)
{
    if (!usb.state.status.initialized) return COLLECTION_USB_LTE_BAD_STATE;
    collection_usb_lte_result_t retired = retire_disconnected_netif_locked();
    if (retired != COLLECTION_USB_LTE_OK) {
        return retired == COLLECTION_USB_LTE_IO_ERROR
            ? retired
            : COLLECTION_USB_LTE_BAD_STATE;
    }
    if (op == COLLECTION_USB_LTE_DIAL && (!usb.state.status.ppp_stopped || usb.netif_started))
        return COLLECTION_USB_LTE_BAD_STATE;
    const char *cmd = collection_usb_lte_state_begin(&usb.state, op, now_ms(), ms);
    if (!cmd) return COLLECTION_USB_LTE_BAD_STATE;
    atomic_store(&usb.cancel, false);
    esp_err_t e = usbh_cdc_write_bytes(usb.port, (const uint8_t *)cmd, strlen(cmd), pdMS_TO_TICKS(25));
    usb.state.last_tx_ms = now_ms();
    if (e != ESP_OK) {
        usb.state.status.last_io_error = e;
        collection_usb_lte_state_fail(&usb.state, COLLECTION_USB_LTE_IO_ERROR);
    }
    return usb.state.status.result;
}

static collection_usb_lte_result_t poll_locked(void)
{
    collection_usb_lte_result_t retired = retire_disconnected_netif_locked();
    if (retired != COLLECTION_USB_LTE_OK) return retired;
    if (atomic_load(&usb.cancel)) {
        usb.state.cancelled = true;
        collection_usb_lte_state_quiesce(&usb.state);
    }
    bool pending = usb.state.pending;
    collection_usb_lte_result_t r = collection_usb_lte_state_poll(&usb.state, now_ms());
    if (pending && r == COLLECTION_USB_LTE_OK && usb.state.status.data_mode) {
        esp_err_t e = iot_eth_start(usb.eth); /* no AT; posts PPP start */
        if (e == ESP_OK) {
            usb.netif_started = true;
            usb.netif_connection_epoch = usb.state.status.connection_epoch;
            usb.state.status.ppp_stopped = false;
            usb.state.quiet = false;
            usb.state.status.quiesced = false;
            iot_eth_link_t link = IOT_ETH_LINK_UP;
            e = usb.mediator->on_stage_changed(usb.mediator, IOT_ETH_STAGE_LINK, &link);
        }
        if (e != ESP_OK) {
            usb.state.status.last_io_error = e;
            collection_usb_lte_state_fail(&usb.state, COLLECTION_USB_LTE_IO_ERROR);
        } else if (usb.state.rx_size) {
            /* Preserve PPP bytes coalesced behind the CONNECT line. */
            e = usb.mediator->stack_input(usb.mediator, usb.state.rx, usb.state.rx_size);
            if (e == ESP_OK) usb.state.status.ppp_rx_bytes += (uint32_t)usb.state.rx_size;
            else { usb.state.status.last_io_error = e; ++usb.state.status.rx_overflows; }
            usb.state.rx_size = 0;
        }
    }
    if (usb.state.quiet && link_down() != ESP_OK) {
        return COLLECTION_USB_LTE_IO_ERROR;
    }
    return usb.state.status.result;
}

collection_usb_lte_result_t collection_usb_lte_begin(collection_usb_lte_operation_t op, uint32_t ms)
{
    if (!usb.gate || !enter_owner()) return COLLECTION_USB_LTE_BAD_STATE;
    collection_usb_lte_result_t result = begin_locked(op, ms);
    leave();
    return result;
}
collection_usb_lte_result_t collection_usb_lte_poll(void)
{
    if (!usb.gate || !enter_owner()) return COLLECTION_USB_LTE_BAD_STATE;
    collection_usb_lte_result_t result = poll_locked();
    leave();
    return result;
}
void collection_usb_lte_cancel(void) { atomic_store(&usb.cancel, true); }
esp_err_t collection_usb_lte_quiesce(void)
{
    atomic_store(&usb.cancel, true);
    if (!usb.gate || !enter_owner()) return ESP_ERR_INVALID_STATE;
    collection_usb_lte_state_quiesce(&usb.state);
    (void)link_down();
    esp_err_t e = usb.netif_started ? ESP_FAIL : ESP_OK;
    leave();
    return e;
}

collection_usb_lte_result_t collection_usb_lte_service(void)
{
    if (!usb.gate || !enter_owner()) return COLLECTION_USB_LTE_BAD_STATE;
    collection_usb_lte_result_t result = usb.state.status.initialized
        ? retire_disconnected_netif_locked()
        : COLLECTION_USB_LTE_BAD_STATE;
    leave();
    return result;
}

collection_usb_lte_result_t collection_usb_lte_begin_for_epoch(
    collection_usb_lte_operation_t op, uint32_t ms, uint32_t expected_epoch)
{
    if (!usb.gate || !enter_owner()) return COLLECTION_USB_LTE_BAD_STATE;
    collection_usb_lte_result_t retired = retire_disconnected_netif_locked();
    if (usb.state.status.connection_epoch != expected_epoch) {
        leave();
        return COLLECTION_USB_LTE_STALE_EPOCH;
    }
    if (retired != COLLECTION_USB_LTE_OK) {
        leave();
        return retired == COLLECTION_USB_LTE_IO_ERROR
            ? retired
            : COLLECTION_USB_LTE_BAD_STATE;
    }
    collection_usb_lte_result_t result = begin_locked(op, ms);
    leave();
    return result;
}

collection_usb_lte_result_t collection_usb_lte_poll_for_epoch(uint32_t expected_epoch)
{
    if (!usb.gate || !enter_owner()) return COLLECTION_USB_LTE_BAD_STATE;
    collection_usb_lte_result_t retired = retire_disconnected_netif_locked();
    if (usb.state.status.connection_epoch != expected_epoch) {
        leave();
        return COLLECTION_USB_LTE_STALE_EPOCH;
    }
    if (retired != COLLECTION_USB_LTE_OK) {
        leave();
        return retired;
    }
    collection_usb_lte_result_t result = poll_locked();
    leave();
    return result;
}

collection_usb_lte_result_t collection_usb_lte_cancel_poll_for_epoch(
    uint32_t expected_epoch)
{
    if (!usb.gate || !enter_owner()) return COLLECTION_USB_LTE_BAD_STATE;
    collection_usb_lte_result_t retired = retire_disconnected_netif_locked();
    if (usb.state.status.connection_epoch != expected_epoch) {
        leave();
        return COLLECTION_USB_LTE_STALE_EPOCH;
    }
    if (retired != COLLECTION_USB_LTE_OK) {
        leave();
        return retired;
    }
    atomic_store(&usb.cancel, true);
    collection_usb_lte_result_t result = poll_locked();
    leave();
    return result;
}

collection_usb_lte_result_t collection_usb_lte_quiesce_for_epoch(
    uint32_t expected_epoch)
{
    if (!usb.gate || !enter_owner()) return COLLECTION_USB_LTE_BAD_STATE;
    collection_usb_lte_result_t retired = retire_disconnected_netif_locked();
    if (usb.state.status.connection_epoch != expected_epoch) {
        leave();
        return COLLECTION_USB_LTE_STALE_EPOCH;
    }
    if (retired != COLLECTION_USB_LTE_OK) {
        leave();
        return retired;
    }
    atomic_store(&usb.cancel, true);
    collection_usb_lte_state_quiesce(&usb.state);
    (void)link_down();
    collection_usb_lte_result_t result = usb.netif_started
        ? COLLECTION_USB_LTE_IO_ERROR
        : COLLECTION_USB_LTE_OK;
    leave();
    return result;
}
void collection_usb_lte_get_status(collection_usb_lte_status_t *s)
{
    if (!s) return;
    memset(s, 0, sizeof(*s));
    s->enabled = true;
    s->result = COLLECTION_USB_LTE_BAD_STATE;
    if (usb.gate && xSemaphoreTake(usb.gate, pdMS_TO_TICKS(25)) == pdTRUE) {
        *s = usb.state.status;
        leave();
    }
}
esp_netif_t *collection_usb_lte_netif(void)
{ return usb.state.status.initialized ? usb.netif : NULL; }
#endif

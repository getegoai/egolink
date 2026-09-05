#include "sos_pending_edge_journal_nvs.h"

#include <string.h>

#include "nvs.h"

#define SOS_PENDING_EDGE_NVS_MAGIC UINT32_C(0x534e5653)

typedef struct {
    uint32_t magic;
    egolink_sos_pending_edge_nvs_metrics_t metrics;
} sos_pending_edge_nvs_internal_t;

_Static_assert(
    sizeof(EGOLINK_SOS_PENDING_EDGE_NVS_PARTITION_LABEL) - 1U <=
        NVS_PART_NAME_MAX_SIZE,
    "pending-edge NVS partition label is unexpectedly long");
_Static_assert(
    sizeof(EGOLINK_SOS_PENDING_EDGE_NVS_NAMESPACE) <=
        NVS_NS_NAME_MAX_SIZE,
    "pending-edge NVS namespace exceeds ESP-IDF limit");
_Static_assert(
    sizeof(EGOLINK_SOS_PENDING_EDGE_NVS_KEY) <=
        NVS_KEY_NAME_MAX_SIZE,
    "pending-edge NVS key exceeds ESP-IDF limit");
_Static_assert(
    EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES == 320U,
    "pending-edge NVS adapter requires exact G format-v1 size");
_Static_assert(
    sizeof(sos_pending_edge_nvs_internal_t) <=
        EGOLINK_SOS_PENDING_EDGE_NVS_CONTEXT_BYTES,
    "pending-edge NVS adapter context is too small");

static sos_pending_edge_nvs_internal_t *adapter_internal(
    egolink_sos_pending_edge_nvs_t *adapter)
{
    return (sos_pending_edge_nvs_internal_t *)(void *)adapter->opaque;
}

static const sos_pending_edge_nvs_internal_t *adapter_internal_const(
    const egolink_sos_pending_edge_nvs_t *adapter)
{
    return (const sos_pending_edge_nvs_internal_t *)(const void *)
        adapter->opaque;
}

static bool valid_internal(const sos_pending_edge_nvs_internal_t *internal)
{
    return internal != NULL && internal->magic == SOS_PENDING_EDGE_NVS_MAGIC;
}

static void saturating_increment(uint64_t *value)
{
    if (*value != UINT64_MAX) {
        ++(*value);
    }
}

static void saturating_add(uint64_t *value, uint64_t amount)
{
    if (UINT64_MAX - *value < amount) {
        *value = UINT64_MAX;
    } else {
        *value += amount;
    }
}

static void close_handle(
    sos_pending_edge_nvs_internal_t *internal,
    nvs_handle_t handle)
{
    nvs_close(handle);
    saturating_increment(&internal->metrics.handles_closed);
}

static egolink_sos_pending_edge_storage_result_t load_record(
    void *context,
    void *destination,
    size_t destination_capacity,
    size_t *actual_length)
{
    if (actual_length != NULL) {
        *actual_length = 0U;
    }
    if (context == NULL) {
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    sos_pending_edge_nvs_internal_t *internal =
        adapter_internal((egolink_sos_pending_edge_nvs_t *)context);
    if (!valid_internal(internal)) {
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.load_attempts);
    if (destination == NULL || actual_length == NULL ||
        destination_capacity < EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES) {
        saturating_increment(&internal->metrics.load_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }

    nvs_handle_t handle = 0U;
    esp_err_t error = nvs_open_from_partition(
        EGOLINK_SOS_PENDING_EDGE_NVS_PARTITION_LABEL,
        EGOLINK_SOS_PENDING_EDGE_NVS_NAMESPACE,
        NVS_READONLY,
        &handle);
    if (error == ESP_ERR_NVS_NOT_FOUND) {
        saturating_increment(&internal->metrics.load_not_found);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND;
    }
    if (error != ESP_OK) {
        saturating_increment(&internal->metrics.load_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.handles_opened);

    size_t required_length = 0U;
    error = nvs_get_blob(
        handle,
        EGOLINK_SOS_PENDING_EDGE_NVS_KEY,
        NULL,
        &required_length);
    if (error == ESP_ERR_NVS_NOT_FOUND) {
        close_handle(internal, handle);
        saturating_increment(&internal->metrics.load_not_found);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND;
    }
    if (error != ESP_OK) {
        close_handle(internal, handle);
        saturating_increment(&internal->metrics.load_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    if (required_length != EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES) {
        close_handle(internal, handle);
        saturating_increment(&internal->metrics.size_mismatches);
        saturating_increment(&internal->metrics.load_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }

    size_t read_length = EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES;
    error = nvs_get_blob(
        handle,
        EGOLINK_SOS_PENDING_EDGE_NVS_KEY,
        destination,
        &read_length);
    close_handle(internal, handle);
    if (error != ESP_OK ||
        read_length != EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES) {
        if (read_length != EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES) {
            saturating_increment(&internal->metrics.size_mismatches);
        }
        saturating_increment(&internal->metrics.load_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }

    *actual_length = read_length;
    saturating_increment(&internal->metrics.load_successes);
    saturating_add(
        &internal->metrics.blob_read_success_bytes,
        (uint64_t)read_length);
    return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
}

static egolink_sos_pending_edge_storage_result_t store_record(
    void *context,
    const void *source,
    size_t source_length)
{
    if (context == NULL) {
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    sos_pending_edge_nvs_internal_t *internal =
        adapter_internal((egolink_sos_pending_edge_nvs_t *)context);
    if (!valid_internal(internal)) {
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.store_attempts);
    if (source == NULL ||
        source_length != EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES) {
        saturating_increment(&internal->metrics.size_mismatches);
        saturating_increment(&internal->metrics.store_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }

    nvs_handle_t handle = 0U;
    esp_err_t error = nvs_open_from_partition(
        EGOLINK_SOS_PENDING_EDGE_NVS_PARTITION_LABEL,
        EGOLINK_SOS_PENDING_EDGE_NVS_NAMESPACE,
        NVS_READWRITE,
        &handle);
    if (error != ESP_OK) {
        saturating_increment(&internal->metrics.store_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.handles_opened);

    error = nvs_set_blob(
        handle,
        EGOLINK_SOS_PENDING_EDGE_NVS_KEY,
        source,
        source_length);
    if (error != ESP_OK) {
        close_handle(internal, handle);
        saturating_increment(&internal->metrics.store_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.set_blob_successes);
    saturating_add(
        &internal->metrics.blob_set_success_bytes,
        (uint64_t)source_length);

    error = nvs_commit(handle);
    close_handle(internal, handle);
    if (error != ESP_OK) {
        saturating_increment(&internal->metrics.store_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.store_commit_successes);
    return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
}

static egolink_sos_pending_edge_storage_result_t clear_record(void *context)
{
    if (context == NULL) {
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    sos_pending_edge_nvs_internal_t *internal =
        adapter_internal((egolink_sos_pending_edge_nvs_t *)context);
    if (!valid_internal(internal)) {
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.clear_attempts);

    /* Read-only preflight avoids creating an empty namespace during clear. */
    nvs_handle_t handle = 0U;
    esp_err_t error = nvs_open_from_partition(
        EGOLINK_SOS_PENDING_EDGE_NVS_PARTITION_LABEL,
        EGOLINK_SOS_PENDING_EDGE_NVS_NAMESPACE,
        NVS_READONLY,
        &handle);
    if (error == ESP_ERR_NVS_NOT_FOUND) {
        saturating_increment(&internal->metrics.clear_not_found);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND;
    }
    if (error != ESP_OK) {
        saturating_increment(&internal->metrics.clear_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.handles_opened);

    size_t required_length = 0U;
    error = nvs_get_blob(
        handle,
        EGOLINK_SOS_PENDING_EDGE_NVS_KEY,
        NULL,
        &required_length);
    close_handle(internal, handle);
    if (error == ESP_ERR_NVS_NOT_FOUND) {
        saturating_increment(&internal->metrics.clear_not_found);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND;
    }
    if (error != ESP_OK) {
        saturating_increment(&internal->metrics.clear_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    if (required_length != EGOLINK_SOS_PENDING_EDGE_RECORD_BYTES) {
        saturating_increment(&internal->metrics.size_mismatches);
        saturating_increment(&internal->metrics.clear_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }

    handle = 0U;
    error = nvs_open_from_partition(
        EGOLINK_SOS_PENDING_EDGE_NVS_PARTITION_LABEL,
        EGOLINK_SOS_PENDING_EDGE_NVS_NAMESPACE,
        NVS_READWRITE,
        &handle);
    if (error != ESP_OK) {
        saturating_increment(&internal->metrics.clear_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.handles_opened);

    error = nvs_erase_key(handle, EGOLINK_SOS_PENDING_EDGE_NVS_KEY);
    if (error == ESP_ERR_NVS_NOT_FOUND) {
        close_handle(internal, handle);
        saturating_increment(&internal->metrics.clear_not_found);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_NOT_FOUND;
    }
    if (error != ESP_OK) {
        close_handle(internal, handle);
        saturating_increment(&internal->metrics.clear_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.erase_key_successes);

    error = nvs_commit(handle);
    close_handle(internal, handle);
    if (error != ESP_OK) {
        saturating_increment(&internal->metrics.clear_failures);
        return EGOLINK_SOS_PENDING_EDGE_STORAGE_IO_ERROR;
    }
    saturating_increment(&internal->metrics.clear_commit_successes);
    return EGOLINK_SOS_PENDING_EDGE_STORAGE_OK;
}

egolink_sos_pending_edge_nvs_status_t
egolink_sos_pending_edge_nvs_init(
    egolink_sos_pending_edge_nvs_t *adapter,
    egolink_sos_pending_edge_storage_t *storage_out)
{
    if (adapter == NULL || storage_out == NULL) {
        if (storage_out != NULL) {
            (void)memset(storage_out, 0, sizeof(*storage_out));
        }
        return EGOLINK_SOS_PENDING_EDGE_NVS_INVALID_ARGUMENT;
    }
    (void)memset(adapter, 0, sizeof(*adapter));
    (void)memset(storage_out, 0, sizeof(*storage_out));
    adapter_internal(adapter)->magic = SOS_PENDING_EDGE_NVS_MAGIC;
    storage_out->context = adapter;
    storage_out->load_record = load_record;
    storage_out->store_record = store_record;
    storage_out->clear_record = clear_record;
    return EGOLINK_SOS_PENDING_EDGE_NVS_OK;
}

bool egolink_sos_pending_edge_nvs_is_initialized(
    const egolink_sos_pending_edge_nvs_t *adapter)
{
    return adapter != NULL &&
        valid_internal(adapter_internal_const(adapter));
}

egolink_sos_pending_edge_nvs_status_t
egolink_sos_pending_edge_nvs_get_metrics(
    const egolink_sos_pending_edge_nvs_t *adapter,
    egolink_sos_pending_edge_nvs_metrics_t *metrics_out)
{
    if (adapter == NULL || metrics_out == NULL) {
        return EGOLINK_SOS_PENDING_EDGE_NVS_INVALID_ARGUMENT;
    }
    const sos_pending_edge_nvs_internal_t *internal =
        adapter_internal_const(adapter);
    if (!valid_internal(internal)) {
        (void)memset(metrics_out, 0, sizeof(*metrics_out));
        return EGOLINK_SOS_PENDING_EDGE_NVS_NOT_INITIALIZED;
    }
    *metrics_out = internal->metrics;
    return EGOLINK_SOS_PENDING_EDGE_NVS_OK;
}

const char *egolink_sos_pending_edge_nvs_status_name(
    egolink_sos_pending_edge_nvs_status_t status)
{
    switch (status) {
    case EGOLINK_SOS_PENDING_EDGE_NVS_OK: return "ok";
    case EGOLINK_SOS_PENDING_EDGE_NVS_INVALID_ARGUMENT:
        return "invalid_argument";
    case EGOLINK_SOS_PENDING_EDGE_NVS_NOT_INITIALIZED:
        return "not_initialized";
    default: return "unknown";
    }
}

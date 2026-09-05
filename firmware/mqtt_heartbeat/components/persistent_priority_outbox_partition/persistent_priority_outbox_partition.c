#include "persistent_priority_outbox_partition.h"

#include <string.h>

_Static_assert(
    EGOLINK_OUTBOX_PARTITION_SLOT_STRIDE_BYTES %
            EGOLINK_OUTBOX_PARTITION_ERASE_BYTES ==
        0U,
    "outbox slot stride must be erase-sector aligned");
_Static_assert(
    EGOLINK_OUTBOX_PARTITION_BYTES ==
        EGOLINK_OUTBOX_SLOT_COUNT *
            EGOLINK_OUTBOX_PARTITION_SLOT_STRIDE_BYTES,
    "outbox partition must contain exactly two physical slots");
_Static_assert(
    EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES <=
        EGOLINK_OUTBOX_PARTITION_SLOT_STRIDE_BYTES,
    "outbox image must fit one physical slot");
_Static_assert(
    EGOLINK_OUTBOX_PARTITION_VERIFY_CHUNK_BYTES > 0U &&
        EGOLINK_OUTBOX_PARTITION_VERIFY_CHUNK_BYTES <=
            EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES,
    "outbox verification chunk must be bounded and nonzero");

static size_t slot_offset(uint8_t slot)
{
    return (size_t)slot *
        (size_t)EGOLINK_OUTBOX_PARTITION_SLOT_STRIDE_BYTES;
}

static void secure_zero(void *buffer, size_t length)
{
    volatile uint8_t *cursor = (volatile uint8_t *)buffer;
    while (length > 0U) {
        *cursor = 0U;
        ++cursor;
        --length;
    }
}

static void saturating_increment(uint64_t *value)
{
    if (*value < UINT64_MAX) {
        ++(*value);
    }
}

static void saturating_add(uint64_t *value, uint64_t increment)
{
    if (increment > UINT64_MAX - *value) {
        *value = UINT64_MAX;
    } else {
        *value += increment;
    }
}

static bool adapter_ready(const egolink_outbox_partition_t *adapter)
{
    return adapter != NULL && adapter->initialized &&
        adapter->partition != NULL;
}

static egolink_outbox_storage_result_t partition_read_slot(
    void *context,
    uint8_t slot,
    void *destination,
    size_t destination_capacity,
    size_t *actual_length)
{
    egolink_outbox_partition_t *adapter =
        (egolink_outbox_partition_t *)context;
    if (actual_length != NULL) {
        *actual_length = 0U;
    }
    if (!adapter_ready(adapter) ||
        slot >= (uint8_t)EGOLINK_OUTBOX_SLOT_COUNT ||
        destination == NULL || actual_length == NULL ||
        destination_capacity < EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES) {
        return EGOLINK_OUTBOX_STORAGE_IO_ERROR;
    }

    esp_err_t result = esp_partition_read(
        adapter->partition,
        slot_offset(slot),
        destination,
        EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES);
    if (result != ESP_OK) {
        return EGOLINK_OUTBOX_STORAGE_IO_ERROR;
    }

    const uint8_t *bytes = (const uint8_t *)destination;
    bool erased = true;
    for (size_t index = 0U;
         index < EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES;
         ++index) {
        if (bytes[index] != UINT8_MAX) {
            erased = false;
            break;
        }
    }
    if (erased) {
        return EGOLINK_OUTBOX_STORAGE_NOT_FOUND;
    }

    *actual_length = EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES;
    return EGOLINK_OUTBOX_STORAGE_OK;
}

static egolink_outbox_storage_result_t partition_write_slot(
    void *context,
    uint8_t slot,
    const void *source,
    size_t source_length)
{
    egolink_outbox_partition_t *adapter =
        (egolink_outbox_partition_t *)context;
    if (!adapter_ready(adapter) ||
        slot >= (uint8_t)EGOLINK_OUTBOX_SLOT_COUNT || source == NULL ||
        source_length != EGOLINK_OUTBOX_STORAGE_IMAGE_V1_BYTES) {
        return EGOLINK_OUTBOX_STORAGE_IO_ERROR;
    }

    const size_t offset = slot_offset(slot);
    saturating_increment(&adapter->metrics.slot_erase_attempts);
    esp_err_t result = esp_partition_erase_range(
        adapter->partition,
        offset,
        EGOLINK_OUTBOX_PARTITION_SLOT_STRIDE_BYTES);
    if (result != ESP_OK) {
        return EGOLINK_OUTBOX_STORAGE_IO_ERROR;
    }
    saturating_increment(&adapter->metrics.slot_erase_successes);
    result = esp_partition_write(
        adapter->partition, offset, source, source_length);
    if (result != ESP_OK) {
        return EGOLINK_OUTBOX_STORAGE_IO_ERROR;
    }
    saturating_add(
        &adapter->metrics.write_api_success_bytes,
        (uint64_t)source_length);

    const uint8_t *expected = (const uint8_t *)source;
    uint8_t verification[EGOLINK_OUTBOX_PARTITION_VERIFY_CHUNK_BYTES];
    size_t verified = 0U;
    while (verified < source_length) {
        size_t remaining = source_length - verified;
        size_t chunk = remaining < sizeof(verification)
            ? remaining
            : sizeof(verification);
        result = esp_partition_read(
            adapter->partition,
            offset + verified,
            verification,
            chunk);
        if (result != ESP_OK ||
            memcmp(verification, &expected[verified], chunk) != 0) {
            saturating_increment(&adapter->metrics.readback_failures);
            secure_zero(verification, sizeof(verification));
            return EGOLINK_OUTBOX_STORAGE_IO_ERROR;
        }
        verified += chunk;
    }
    secure_zero(verification, sizeof(verification));
    return EGOLINK_OUTBOX_STORAGE_OK;
}

const char *egolink_outbox_partition_adapter_version(void)
{
    return EGOLINK_OUTBOX_PARTITION_ADAPTER_VERSION;
}

esp_err_t egolink_outbox_partition_init(
    egolink_outbox_partition_t *adapter)
{
    if (adapter == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(adapter, 0, sizeof(*adapter));

    const esp_partition_t *partition = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA,
        (esp_partition_subtype_t)EGOLINK_OUTBOX_PARTITION_SUBTYPE,
        EGOLINK_OUTBOX_PARTITION_LABEL);
    if (partition == NULL) {
        return ESP_ERR_NOT_FOUND;
    }
    if (partition->type != ESP_PARTITION_TYPE_DATA ||
        partition->subtype !=
            (esp_partition_subtype_t)EGOLINK_OUTBOX_PARTITION_SUBTYPE ||
        strcmp(partition->label, EGOLINK_OUTBOX_PARTITION_LABEL) != 0 ||
        partition->erase_size != EGOLINK_OUTBOX_PARTITION_ERASE_BYTES ||
        partition->address % EGOLINK_OUTBOX_PARTITION_ERASE_BYTES != 0U ||
        partition->size != EGOLINK_OUTBOX_PARTITION_BYTES) {
        return ESP_ERR_INVALID_SIZE;
    }

    adapter->partition = partition;
    adapter->initialized = true;
    return ESP_OK;
}

esp_err_t egolink_outbox_partition_storage(
    egolink_outbox_partition_t *adapter,
    egolink_outbox_storage_t *storage)
{
    if (storage == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!adapter_ready(adapter)) {
        return ESP_ERR_INVALID_STATE;
    }
    storage->context = adapter;
    storage->read_slot = partition_read_slot;
    storage->write_slot = partition_write_slot;
    return ESP_OK;
}

esp_err_t egolink_outbox_partition_get_metrics(
    const egolink_outbox_partition_t *adapter,
    egolink_outbox_partition_metrics_t *metrics)
{
    if (metrics == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!adapter_ready(adapter)) {
        return ESP_ERR_INVALID_STATE;
    }
    *metrics = adapter->metrics;
    return ESP_OK;
}

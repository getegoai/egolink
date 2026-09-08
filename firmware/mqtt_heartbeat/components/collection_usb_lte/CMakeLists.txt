idf_component_register(SRCS "collection_usb_lte.c" "collection_usb_lte_state.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_netif
    PRIV_REQUIRES esp_timer esp_event freertos)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)

# The optional dependency packet is explicitly discovered before Kconfig.
# Default builds have no external manifest, package lookup or download.
if(CONFIG_EGOLINK_COLLECTION_USB_LTE)
    idf_component_get_property(cdc_lib espressif__iot_usbh_cdc COMPONENT_LIB)
    idf_component_get_property(eth_lib espressif__iot_eth COMPONENT_LIB)
    target_link_libraries(${COMPONENT_LIB} PRIVATE ${cdc_lib} ${eth_lib})
endif()

set(call020_audio_loop_sources
    "safe_audio_initializer_v1.c"
         "call020_media_adapter_core.c"
         "call020_usb_serial_jtag_endpoint.c"
         "call020_wearable_composition.c"
         "call020_operator_runner.c"
         "call020_device_control_wire.c"
         "call020_device_control_responder.c"
         "call020_device_control_owner.c"
)

# Ordinary images preserve app_main byte-for-byte. The retained G/Q profile
# selects an inert stub; only the separate, default-off R profile selects its
# one-shot owner boot entry.
if(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_OWNER)
    list(APPEND call020_audio_loop_sources
        "call020_device_control_owner_boot.c")
elseif(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER)
    list(APPEND call020_audio_loop_sources
        "call020_operator_runner_boot_stub.c")
else()
    list(APPEND call020_audio_loop_sources "app_main.c")
endif()

idf_component_register(
    SRCS ${call020_audio_loop_sources}
    INCLUDE_DIRS "."
    REQUIRES esp_driver_gpio esp_driver_i2s esp_driver_usb_serial_jtag
             esp_system esp_timer
)

# CALL-020G is deliberately retained only in its dedicated, non-autorun
# profile. The undefined entry pulls the inert API table and its transitive
# D/E/F references into the final ELF without invoking anything at boot.
if(CONFIG_EGOLINK_CALL020_OPERATOR_RUNNER)
    target_link_libraries(${COMPONENT_LIB}
        INTERFACE "-u call020_operator_runner_retained_entry")
endif()

# Q remains API-only and boot-dormant unless the separately selected R profile
# owns it. Retention proves the parser and lease-to-runner handoff are linked.
if(CONFIG_EGOLINK_CALL020_DEVICE_CONTROL_RESPONDER)
    target_link_libraries(${COMPONENT_LIB}
        INTERFACE "-u call020_device_control_responder_retained_entry")
endif()

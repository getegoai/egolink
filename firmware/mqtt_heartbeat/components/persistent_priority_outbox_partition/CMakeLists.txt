idf_component_register(
    SRCS "persistent_priority_outbox_partition.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_partition persistent_priority_outbox
)

target_compile_options(${COMPONENT_LIB} PRIVATE
    -Wall
    -Wextra
    -Werror
    -Wconversion
    -Wformat=2
    -Wshadow
    -Wsign-conversion
)

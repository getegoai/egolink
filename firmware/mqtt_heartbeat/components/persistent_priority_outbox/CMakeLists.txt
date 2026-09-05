idf_component_register(
    SRCS "persistent_priority_outbox.c"
    INCLUDE_DIRS "include"
    REQUIRES json mbedtls
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

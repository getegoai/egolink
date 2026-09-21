idf_component_register(
    SRCS "ego_state_engine.c"
    INCLUDE_DIRS "include"
    REQUIRES mbedtls
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

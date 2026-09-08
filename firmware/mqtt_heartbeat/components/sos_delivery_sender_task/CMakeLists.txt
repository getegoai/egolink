idf_component_register(
    SRCS "sos_delivery_sender_task.c"
    INCLUDE_DIRS "include"
    REQUIRES freertos sos_delivery_composition
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

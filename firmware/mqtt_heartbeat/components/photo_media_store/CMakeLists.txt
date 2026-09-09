idf_component_register(
    SRCS "photo_media_store.c"
    INCLUDE_DIRS "include"
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

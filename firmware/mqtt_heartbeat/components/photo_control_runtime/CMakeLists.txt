idf_component_register(SRCS "photo_control_runtime.c" INCLUDE_DIRS "include")
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)

idf_component_register(SRCS "platform_i2c_bus.c" INCLUDE_DIRS "include" REQUIRES driver esp_timer freertos)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)

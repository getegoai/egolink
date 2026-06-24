idf_component_register(
    SRCS "platform_imu.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_timer log driver
)

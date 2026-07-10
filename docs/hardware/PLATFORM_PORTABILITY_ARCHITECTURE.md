# Ego Link 平台可迁移固件架构

## 1. 目标

在当前 ESP32-S3 上继续开发，同时避免业务、模型和协议绑定 ESP-IDF 或 SIM7670G。未来 STM32U5、Apollo4、ESP32-P4 或 Alif B1 的验证应通过新增后端完成，而不是重写 Safety Companion。

## 2. 分层

```text
应用与安全域
├─ Safety Kernel
├─ ContextRouter
├─ 事件状态机
├─ 策略与隐私
└─ shared/contracts

设备服务域
├─ motion_service
├─ audio_service
├─ vision_service
├─ location_service
├─ connectivity_service
├─ recorder_service
└─ inference_service

平台抽象域
├─ platform_time
├─ platform_power
├─ platform_storage
├─ platform_imu
├─ platform_audio
├─ platform_camera
├─ platform_modem
├─ platform_gnss
├─ platform_connectivity
├─ platform_secure_storage
├─ platform_ota
└─ inference_backend

厂商后端
├─ esp32s3_sim7670g
├─ stm32u5
├─ apollo4
├─ esp32p4
└─ balletto_b1
```

## 3. 强制规则

- 业务层不得直接包含 `esp_*`、STM32 HAL、Ambiq HAL 或其他厂商API；
- 厂商头文件只能出现在对应平台后端和构建配置中；
- `shared/contracts/**` 不因更换芯片而改变；
- 模型输入、输出、归一化、量化和阈值由模型包定义；
- 硬件能力差异通过 capability descriptor 表达，不以大量散乱 `#ifdef` 渗入业务层；
- 不支持的功能必须返回显式 `NOT_SUPPORTED`，不得伪造成功；
- 模拟后端与真实后端遵循同一接口；
- 每个后端必须有独立测试和基准报告。

## 4. 建议能力描述

示意：

```c
typedef struct {
    const char *board_id;
    bool has_wifi;
    bool has_ble;
    bool has_cellular;
    bool has_gnss;
    bool has_imu;
    bool has_pdm_mic;
    bool has_camera;
    bool has_battery_gauge;
    bool supports_deep_sleep;
    bool supports_secure_boot;
    uint32_t ram_bytes;
    uint32_t flash_bytes;
} egolink_board_capabilities_t;
```

应用层根据能力调整策略，例如无摄像头时删除 `image_single` 证据请求，而不是让模型或通信层报出虚假图片。

## 5. 推理后端

统一接口应至少支持：

```text
init(model_descriptor)
get_capabilities()
load_model()
run(input, output)
get_last_profile()
unload_model()
```

`get_last_profile()`记录：

- 延迟；
- 峰值工作内存；
- 模型版本；
- 后端名称；
- 是否量化；
- 是否使用加速器；
- 可选能耗测量ID。

当前 ESP32-S3 可以先使用规则、ESP-DL/TFLite Micro或参考C实现。未来各平台通过新后端接入，不修改 `ContextRouter` 输出契约。

## 6. 功耗状态接口

统一状态：

```text
BOOT
ACTIVE
GUARDING
LIGHT_SLEEP
DEEP_SLEEP
NETWORK_ATTACH
GNSS_FIX
CAPTURE_AUDIO
CAPTURE_IMAGE
UPLOAD
VOICE_CALL
EMERGENCY
```

每次状态进入和退出必须产生可观测事件，便于与 PPK2 / Otii 波形对齐。

## 7. 推荐目录演进

不要求 Codex 一次性重构。可渐进形成：

```text
firmware/
├─ app/
├─ services/
├─ platform/
│  ├─ include/
│  ├─ mock/
│  └─ esp32s3_sim7670g/
├─ inference/
│  ├─ include/
│  ├─ reference/
│  └─ esp32s3/
└─ boards/
   └─ waveshare_esp32s3_sim7670g/
```

新平台到货前，不创建大量空实现。先抽象当前会阻碍迁移的接口，并保持现有功能通过测试。

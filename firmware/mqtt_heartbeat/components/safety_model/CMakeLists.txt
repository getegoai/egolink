idf_component_register(
    SRCS "safety_model.c" "tiny_safety_harness.c"
    INCLUDE_DIRS
        "include"
        "../../../../shared/embedded"
        "../../../../model_artifacts/tiny_safety_model/MODEL-DEVICE-001-tiny-safety-v0-20260707/export"
)

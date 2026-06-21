# CURRENT_TASK: T025 Safety Companion M0 Firmware Model Interface

## 任务目标

完成 `M0-INT-003`：在 ESP-IDF 固件中建立稳定的 `safety_model` 调用边界，当前实现为 deterministic mock，不部署真实神经网络。

## 范围

- 新增 `firmware/mqtt_heartbeat/components/safety_model` 组件。
- 使用 `shared/embedded/safety_model_contract.h` 中的 `ego_sc_model_input_t` / `ego_sc_model_output_t`。
- 对业务层暴露：
  - `bool safety_model_init(void)`
  - `bool safety_model_evaluate(const ego_sc_model_input_t *input, ego_sc_model_output_t *output)`
  - `const char *safety_model_version(void)`
- 增加 `safety_model_input_from_mock_state`，把当前 mock GNSS、wake、网络、电量、隐私等状态转换为模型输入。
- 在串口侧增加不冲突的测试命令：
  - `safety status`
  - `safety demo normal`
  - `safety demo sos`
  - `safety demo impact`

## 不做

- 不引入真实模型。
- 不引入 ESP-DL、ESP-SR、TFLite Micro。
- 不修改模型包、模型 artifact 或共享契约语义。
- 不声明合成规则等于真实安全识别准确率。
- 不进行真实紧急动作。

## 允许修改路径

- `firmware/mqtt_heartbeat/components/safety_model/**`
- `firmware/mqtt_heartbeat/main/CMakeLists.txt`
- `firmware/mqtt_heartbeat/main/app_main.c`
- `quality_tests/test_safety_model_firmware.py`
- `docs/modeling/INTEGRATION_REPORT.md`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_safety_model_firmware quality_tests.test_mqtt_heartbeat_firmware -v
powershell -ExecutionPolicy Bypass -File scripts\verify.ps1
idf.py --version
```

## 执行结果

- 已新增 `safety_model` ESP-IDF component。
- `safety_model.h` 已包装共享契约头 `safety_model_contract.h`。
- `safety_model_evaluate` 已实现 deterministic mock：
  - SOS -> `EGO_SC_RISK_MANUAL_SOS` / `EGO_SC_ACTION_URGENT_ESCALATION`
  - impact + stationary -> `EGO_SC_RISK_POST_IMPACT_INACTIVITY`
  - critical low battery -> `EGO_SC_RISK_LOW_BATTERY`
  - long offline -> `EGO_SC_RISK_COMMUNICATION_LOSS`
  - otherwise -> `EGO_SC_RISK_NONE`
- 已在 `app_main.c` 初始化 `safety_model`，并注册串口测试命令任务。
- `python -m unittest quality_tests.test_safety_model_firmware quality_tests.test_mqtt_heartbeat_firmware -v` 通过，8 个测试成功。
- `powershell -ExecutionPolicy Bypass -File scripts\verify.ps1` 通过，76 个测试成功。
- `idf.py --version` 未通过：当前 shell 未加载 ESP-IDF，无法执行固件构建/烧录。

## 完成标准

- [x] 业务代码通过 `safety_model` 边界调用 mock，不直接依赖未来模型框架。
- [x] mock 与 future real implementation 可以在组件边界替换。
- [x] SOS 路径为确定性规则。
- [x] Mock GNSS、wake、网络、电量、隐私状态有 adapter。
- [x] 串口测试命令已注册。
- [x] 主机侧静态测试和全量验证通过。
- [x] 如实记录本轮未进行 ESP-IDF build/flash。

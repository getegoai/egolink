# CURRENT_TASK：T020 修复板级探测 CH343 / RNDIS 识别

## 任务目标

修复 `scripts/egolink_board_probe.py` 在 Windows 上漏识别 ESP32-S3 CH343 串口和 Remote NDIS 网卡的问题，让板级探测结果与系统 PnP 设备状态一致。

## 范围

- 串口发现合并 `Win32_SerialPort` 与 `Get-PnpDevice -Class Ports`；
- 从 PnP FriendlyName 中解析 `COMx`；
- 对 CIM 与 PnP 返回的重复串口做去重；
- RNDIS 发现合并 `Get-NetAdapter` 与 `Get-PnpDevice -Class Net`；
- 识别 `Remote NDIS based Internet Sharing Device`；
- 补充 CH343 PnP-only、串口去重、RNDIS 识别测试；
- 更新状态记录。

## 不做

- 不改变 SIM7670G AT 探测命令；
- 不改变 ESP32 固件；
- 不刷写固件；
- 不接入 GNSS 定位上报，后续任务单独推进。

## 允许修改路径

- `scripts/egolink_board_probe.py`
- `quality_tests/test_board_probe.py`
- `docs/STATUS.md`
- `docs/tasks/CURRENT_TASK.md`

## 验证命令

```powershell
python -m unittest quality_tests.test_board_probe -v
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
python scripts\egolink_board_probe.py --skip-esp-log --probe-all-sim-ports
```

## 执行结果

- 新增 PnP-only CH343 解析，`USB-Enhanced-SERIAL CH343 (COM4)` 可识别为 `esp32_s3_ch343`；
- 新增 RNDIS 识别，`Remote NDIS based Internet Sharing Device` 可进入质量门；
- `python -m unittest quality_tests.test_board_probe -v` 通过，8 个测试全部成功；
- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` 通过，34 个测试全部成功；
- 真实板级探测报告 `reports/board_validation/20260621-091239/probe.md`：
  - `esp32_ch343_serial_present` PASS，端口 `COM4`；
  - `sim7670_usb_serial_present` PASS，端口 `COM5/COM6/COM7/COM8`；
  - `sim7670_rndis_adapter_present` PASS，发现 `以太网 2` 和 `Remote NDIS based Internet Sharing Device`；
  - `sim7670_at_identity` PASS，AT 端口 `COM6/COM7`。

## 完成标准

- `board_probe` 能识别 PnP-only CH343 串口；
- `board_probe` 能识别 Remote NDIS；
- 单元测试和全量测试通过；
- 真实板级探测质量门不再因 CH343 / RNDIS 缺失失败。

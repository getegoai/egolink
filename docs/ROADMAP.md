# EgoLink roadmap / EgoLink 路线

This roadmap describes actual product development. Dates and specifications are not release promises. / 本路线围绕实际产品开发，日期与规格不构成交付承诺。

| Horizon | Work / 工作 |
|---|---|
| **Now / 现在** | Publish the product definition and import existing hardware, firmware, backend, contracts, and tools into public development. / 公开产品定义，将现有硬件、固件、后端、契约和工具导入公开研发。 |
| **Next / 接下来** | Improve custom-board operation; verify location, full-duplex calling, SOS, power, and interruption recovery; connect a minimum private EgoBase endpoint. / 改进自制板运行，验证定位、双向音频、SOS、供电与中断恢复，接入最小私有 EgoBase 终点。 |
| **Later / 更远期** | Improve wearable design and power consumption; evaluate on-device models against measured data; extend personal context and cross-device interaction. / 改进佩戴设计与功耗，以实测数据评估端侧模型，扩展个人上下文和跨设备交互。 |

## Source import / 源码导入

- [ ] Import `firmware/hw021_pcb1_bringup/` and the shared components it actually uses, retaining board-specific configuration and known hardware limits. / 导入自制板固件及实际依赖，保留板级配置与限制。
- [ ] Import existing `server/` components, identifying the role of the Python Message Hub and Java backend and which runtime is currently supported. / 导入现有服务端，说明两套组件的角色与当前支持路径。
- [ ] Include `shared/contracts/`, relevant replay/calibration tools, and existing tests with dependencies and run commands. / 导入契约、相关回放校准工具与已有测试。
- [ ] Add shareable hardware and mechanical materials with revision information and applicable licenses. / 导入可分享的硬件与结构资料，注明版本和许可。
- [ ] Record the imported source version/date and begin the next development change directly through the public repository. / 记录导入版本与日期，后续实际研发直接进入公开仓库。

## Engineering work / 工程工作

- **Prototype:** resolve known charging, audio, camera wiring, and memory/pin constraints on PCB1; keep supported configurations explicit. / 处理 PCB1 已知充电、音频、相机接线和存储/引脚问题。
- **Location and recovery:** measure availability and error against reference locations; handle queued events, duplicates, restart, and interrupted upload without hiding missing data. / 测量定位可用性与误差，处理排队、重复、重启和上传中断。
- **Calling and SOS:** verify inbound/outbound full-duplex audio and the distinct results of input recognition, storage, delivery, call connection, and human response. / 验证双向音频，区分触发、保存、送达、接通和人工回应。
- **EgoBase:** receive and replay events in user-controlled storage while preserving their source and time. / 将事件送达用户控制的存储并支持回放，保留来源与时间。

Product acceptance for location, calling, and SOS remains open. Prototype work can continue publicly while those results are developed and measured. / 定位、通话与 SOS 的产品验收仍未完成；原型研发在公开协作中持续推进并取得实测结果。

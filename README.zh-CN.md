# EgoLink

**连接个人 AI 与物理世界的随身设备。**

[English](README.md) · [EgoLabs](https://github.com/getegoai) · [Ego 总项目](https://github.com/getegoai/ego) · [getego.ai](https://getego.ai) · [路线](docs/ROADMAP.md)

EgoLink 结合定位、运动感知、蜂窝通信和实体交互。我们同步开发硬件、固件、后端与工具，当前围绕定位、双向蜂窝通话和实体 SOS 流程推进。

它是 [Ego](https://github.com/getegoai/ego) 个人 AI 项目的随身部分。EgoBase 是规划中的用户私有终点，承担历史、上下文和进一步处理；基本设备交互与求助应在 Base 或 AI 不可用时继续工作。

## 当前状态

**首个公开版本包含产品定义与路线。真实实现正在准备导入，本版本尚无可构建固件或后端。**

项目已有基于 ESP32-S3 和 ML307A 蜂窝模组的工程原型。2026 年 10 月 21–22 日记录报告了自制 PCB1 上的蜂窝注册、遥测上传、本地日志、补传、VoLTE 接通及 SOS 后端告警。

这些是有限台架结果。代表性定位、完整双向通话和端到端 SOS 产品验收仍未关闭，硬件仍需返修。续航、模型准确率和完整本地数据路径尚未得到证明，当前开发仍包含服务端采集链路。

我们会把已有产品工作导入本仓库，并在这里继续开发，如实呈现问题和未完成能力。

## 正在导入的实现

| 计划路径 | 已有工作 |
|---|---|
| `firmware/` | ESP32-S3 固件、自制板调通、感知、设备状态、通信和本地日志 |
| `hardware/` | 原型硬件与结构资料，以及对应版本的限制 |
| `server/` | 遥测、历史、告警和 Web 界面，含现有 Python 与 Java 组件 |
| `shared/contracts/` | 版本化观察、状态、事件、命令和回执契约 |
| `pc_simulator/`、`quality_tests/` | 开发、回放、校准和验证工具 |

导入时会说明各组件支持的运行环境与板卡。这些路径尚不包含在当前文档首发版本中。

## 接下来

- 解决自制板问题，改进独立电池供电运行。
- 验证完整音频/通话和 SOS 流程、定位质量及断网/重启恢复。
- 接入最小用户私有 EgoBase 存储与回放终点。
- 通过真实提交、Issue 和 PR 持续推进，见[路线](docs/ROADMAP.md)。

## 参与与许可

欢迎报告问题、审查协议、测试支持的板卡、改进文档和贡献代码。可以从 [Issue](https://github.com/getegoai/egolink/issues) 或[贡献说明](CONTRIBUTING.md)开始。

本次原创文档采用 **CC BY 4.0**，见 [LICENSE](LICENSE)。自有软件计划在导入时明确采用 **Apache-2.0**；硬件、模型、数据和第三方材料分别说明适用许可。

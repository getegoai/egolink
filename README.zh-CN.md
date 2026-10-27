# EgoLink

**连接个人 AI 与物理世界的随身设备。**

[English](README.md) · [EgoLabs](https://github.com/getegoai) · [Ego 总项目](https://github.com/getegoai/ego) · [getego.ai](https://getego.ai) · [路线](docs/ROADMAP.md)

EgoLink 结合定位、运动感知、蜂窝通信和实体交互。我们同步开发硬件、固件、后端与工具，当前围绕定位、双向蜂窝通话和实体 SOS 流程推进。

它是 [Ego](https://github.com/getegoai/ego) 个人 AI 项目的随身部分。EgoBase 是正在开发的用户私有终点，承担历史、上下文和进一步处理；基本设备交互与求助应在 Base 或 AI 不可用时继续工作。

## 当前状态

**真实固件、后端、硬件资料、工具和连续研发历史已纳入本仓库。** 当前仍是存在已知缺陷和未完成功能的工程原型。后续通过这里的提交、Issue 和 PR 持续开发。

源码基线截至 2026 年 10 月 23 日。10 月 21–22 日记录报告了自制 ESP32-S3 / ML307A `PCB1` 上的蜂窝注册、遥测上传、本地日志、补传、VoLTE 接通及 SOS 后端告警。

这些是有限台架结果。代表性定位、完整双向通话和端到端 SOS 产品验收仍未关闭。PCB1 仍有已记录的相机、充电、音频和引脚分配问题。续航、模型准确率和完整本地数据路径尚未得到证明，当前开发仍包含服务端采集链路。

本次公开导入准备中，PCB1 固件在 ESP-IDF 5.4.2 下构建通过，未新增实机测试。[导入验证记录](docs/PUBLIC_IMPORT_VALIDATION.md)列明实际构建/测试环境、结果和剩余失败；[历史索引](docs/HISTORY.md)说明原始研发序列及隐私清理。

## 仓库结构

| 路径 | 工作 |
|---|---|
| [firmware/hw021_pcb1_bringup/](firmware/hw021_pcb1_bringup/) | 当前自制 PCB1 调通与集成运行时 |
| [firmware/mqtt_heartbeat/](firmware/mqtt_heartbeat/) | 保留的 ESP-IDF 设备运行时及感知、通信、存储、状态公共组件 |
| [hardware/](hardware/) | 原型 PCB 与结构资料，限制按具体版本说明 |
| [server/](server/) | Python 遥测/消息服务、历史、告警与 Web 界面；`ego-cloud-backend/` 为独立 Java 服务 |
| [shared/contracts/](shared/contracts/) | 版本化观察、状态、事件、命令和回执契约 |
| [pc_simulator/](pc_simulator/)、[scripts/](scripts/)、[quality_tests/](quality_tests/) | 主机工具、回放、校准与验证 |
| [model_lab/](model_lab/)、[model_artifacts/](model_artifacts/) | 模型研发及保留的规则/合成集成资产；能力边界见对应模型卡 |

当前工程上下文从 [CONTEXT_INDEX](docs/CONTEXT_INDEX.md)进入。带日期的状态和台架记录只对其具体板卡与版本负责，不能直接延伸为新构建的硬件结论。

## 运行与构建

在仓库根目录启动 Python 消息服务：

```sh
python scripts/run_message_hub.py --host 127.0.0.1 --port 8790
```

打开 `http://127.0.0.1:8790`。本地服务可在未接设备时启动；实时遥测需要自行配置的设备。独立 Java 后端的依赖见 [pom.xml](server/ego-cloud-backend/pom.xml)，需要单独配置其服务环境。

Java 服务使用 Compose 前，将服务目录下的 [`.env.example`](server/ego-cloud-backend/.env.example) 复制为 `.env`，设置 `MYSQL_ROOT_PASSWORD`、`DB_PASSWORD`、`DEVICE_AUTH_TOKEN`；数据库与后端共用 `DB_PASSWORD`。直接启动 Java 时导出对应环境变量。历史中的私人部署地址、Wi-Fi 凭据、设备标识和电话号码已替换，请在本地配置自己的值。

PCB1 使用 **ESP-IDF 5.4.2**。激活环境后，在仓库根目录的 PowerShell 中使用新的生成配置和构建目录：

```powershell
$repo = (Get-Location).Path
python "$env:IDF_PATH/tools/idf.py" -C firmware/hw021_pcb1_bringup -B "$repo/build/pcb1" -D "SDKCONFIG=$repo/build/pcb1/sdkconfig" -D "SDKCONFIG_DEFAULTS=$repo/firmware/hw021_pcb1_bringup/sdkconfig.defaults" build
```

组件 manifest 固定 `esp32-camera` 2.1.7 与 `esp_jpeg` 1.3.1。使用硬件前应阅读 [PCB1 说明](firmware/hw021_pcb1_bringup/README.md)、[板卡矩阵](docs/hardware/BOARD_MATRIX.md)和[导入验证记录](docs/PUBLIC_IMPORT_VALIDATION.md)。编译不能证明实机能力。

已有主机检查：

```sh
python -m pip install jsonschema cryptography numpy pandas
python scripts/context_lint.py
python -m unittest discover -s quality_tests -v
```

本轮检查使用 Python 3.12。主机 C 测试需要将 `CC` 指向本机 GCC，并把其目录加入 `PATH`；部分检查还需要 ESP-IDF 或明确配置的集成环境。验证记录区分实际执行的检查、环境错误、失败与未测范围。

## 接下来

- 解决自制板问题，改进独立电池供电运行。
- 验证完整音频/通话和 SOS 流程、定位质量及断网/重启恢复。
- 接入最小用户私有 EgoBase 存储与回放终点。
- 通过真实提交、Issue 和 PR 持续推进，见[路线](docs/ROADMAP.md)。

## 参与与许可

欢迎参与实际设备和软件研发：报告问题、审查协议、测试支持的板卡、改进文档和贡献代码。可以从 [Issue](https://github.com/getegoai/egolink/issues) 或[贡献说明](CONTRIBUTING.md)开始。

自有软件、契约、测试及已明确的项目自生成合成模型资产采用 **Apache-2.0**；原创说明文档与自有硬件设计采用 **CC BY 4.0**；第三方材料保留各自许可。具体范围见 [LICENSING.md](LICENSING.md)、[Apache 许可全文](LICENSE)与[第三方说明](THIRD_PARTY_NOTICES.md)。

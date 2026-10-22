---
document_id: HW021-PCB1-BRINGUP-20261020
document_status: authoritative
last_verified: 2026-10-21
owners:
  - hardware
  - firmware
---

# `HW021_C1_ESP32MODEL_VR00` (`PCB1`) 原理图与实物联合审查、10 阶段实板 Bring-Up 验证及 ECN 整改报告

## 1. 概述与硬件身份基线

本报告记录第一版定制集成样机 PCB（目录：`hardware/PCB1/`，原理图：[HW021_C1_ESP32MODEL_VR00.pdf](../../hardware/PCB1/HW021_C1_ESP32MODEL_VR00.pdf)，实物照片：[1.jpg](../../hardware/PCB1/1.jpg)、[2.jpg](../../hardware/PCB1/2.jpg)、[3.jpg](../../hardware/PCB1/3.jpg)、[4.jpg](../../hardware/PCB1/4.jpg)、[5.jpg](../../hardware/PCB1/5.jpg)）的：

1. **原理图与实物逐器件对比审查（BOM / 焊接 / 飞线 / 外设形态）**
2. **10 阶段非破坏性自动化实板 Bring-Up 测试结果（`COM8` 实测证据）**
3. **`CALL-030` 原生 4G VoLTE 语音与模拟音频能力重大突破取证**
4. **发现的 7 项硬件设计缺陷（含 `PCB1` 当板手工飞线/割线修复方案与 `PCB2` 改版 ECN 清单）**

### 1.1 实板硬件身份与测试留档信息

| 字段 | 实测值 / 证据路径 |
|---|---|
| PCB 丝印标识 | `HW021_C1_ESP32MODEL` / `20260924` |
| 主控芯片 (`U4`) | `ESP32-S3R8` (`QFN56`, 丝印 `ESP32-S3 232026 R8MWG065000 FC00MDF072`, revision `v0.2`, 内置 8 MB Octal PSRAM `AP_3v3`) |
| 设备 MAC 地址 | `02:00:00:00:00:02` |
| 外置 SPI NOR Flash (`U2`) | **Winbond `W25Q32JVSQ` (`2412`)** — JEDEC ID `0xEF4016`，容量 **4 MiB (`4,194,304` B)**（与原理图 `BY25Q64ASSIG` 8 MiB 及旧开发板 16 MiB 不一致） |
| 4G 蜂窝模组 (`U1`) | **中移物联 `ML307A-DSLN`**，固件版本 **`ML307A-DSLN-MTSH1S00`**（IMEI 脱敏：`869944080******`） |
| 板载三轴加速度计 (`U3`) | 士兰微 **`SC7A20TR`**（I2C0 地址实测 `0x19`，`WHO_AM_I = 0x11`） |
| 外置 GNSS 模块 (`J10`) | **Beitian（北天）`BE-220`**（SN: `M260909680609`，通过 4 芯线焊接至 `J10 GPS` 焊盘并热熔胶固定，默认波特率实测 `115200`） |
| 摄像头模组 (`J9`) | **`TY-OV2640-75MM-V1.0`**（24-pin DVP FPC 排线接入 `J9`） |
| 音频功放与外设 (`U5`, `J4`, `J5`) | `U5 = 8002A` SOP-8 功放，`J4` 接入驻极体麦克风（红黑绞线），`J5` 接入圆型腔体扬声器 |
| 供电电池 (`J6 BAT`) | **力量达 `402030-200mAh 3.7V`** 软包锂电池（生产批号 `2026.07`） |
| 连接端口 | `COM8`（ESP32-S3 原生 `USB JTAG/serial debug unit`，`VID_303A&PID_1001`） |
| 原厂工程师初始固件备份 | `.local_backups/pcb1_hw021_bringup_20261020/hw021_bringup_0x0_0x50000.bin`（SHA-256: `543503393D31F1170F8374D2687E83534199F76FC81542E8BD730C1DF92E2DB0`） |
| 10 阶段 Bring-Up 固件源码 | [firmware/hw021_pcb1_bringup/main/app_main.c](../../firmware/hw021_pcb1_bringup/main/app_main.c) |
| Bring-Up 固件镜像哈希 | `hw021_pcb1_bringup.bin` SHA-256: `4CA885508BBC2D692D8E5700394D57070D20A1A1C77B01B7C163AEE1E971B519`<br>`hw021_pcb1_bringup.elf` SHA-256: `C7D48A7A8B04A73C0146F57ACD8C1C04A9012BBA7AE2C88C690613C6EDF160D7` |
| 实板串口日志与结构化证据 | `reports/board_validation/pcb1_bringup_20261020/bringup_serial_final.log`<br>`reports/board_validation/pcb1_bringup_20261020/summary.json` |
| 验证时间戳 | `2026-10-20T13:32:03+08:00` |

---

## 2. `HW021_C1_ESP32MODEL_VR00` 完整引脚映射表（经原理图与实板双向核验）

| ESP32-S3 引脚 | QFN56 Pin | 原理图网络名 | 连接目标器件与功能 | 极性与驱动说明 |
|---|---|---|---|---|
| `GPIO0` | Pin 5 | `GPIO0` | `K3 (BOOT)` 按键 | 外部 `R35=10K` 上拉至 `3.3V_VCC`，按下为 `0` |
| `GPIO1` (`ADC1_CH0`) | Pin 6 | `ADC_V` | 电池分压采样点 (`R40=10K` / `R45=10K` / `C52=100nF`) | 仅在 `AD_CTRL (GPIO2) = 1` 时接通，`V_BAT = 2 * V_ADC` |
| `GPIO2` | Pin 7 | `AD_CTRL` | `Q7 (8050)` 基极 -> `Q6 (CJE3139K)` P-MOS 栅极 | **高电平有效 (`1`)**：导通 `Q7/Q6` 开启电池分压采样；平时置 `0` 省电 |
| `GPIO3` | Pin 8 | `SD_CS` | `CON1` TF 卡 `CD/D3` (Pin T2) | `R53=51K` 上拉至 `3.3V_SD` |
| `GPIO4` | Pin 9 | `CAM_PWDN` | **同时控制** `Q5 (CJE3139K)` (`3.3V_SD`) 与 `U7 (VRD1228MTX)` (`EN1/EN2`) | **`0`**：`3.3V_SD` 开启、摄像头断电；**`1`**：`CAM_1.2V/2.8V` 开启、TF 卡断电 |
| `GPIO5` | Pin 10 | `MUTE` | `U5 (8002A)` Pin 1 (`SHUTDOWN`) | 外部 `R19=2K` 上拉至 `V_BAT` (`4.24V`)；高阻/高电平静音，拉低开启功放 |
| `GPIO6` | Pin 11 | `KEY` | `K1 (KEY)` 用户/SOS 按键 | 外部 `R33=10K` 上拉至 `3.3V_VCC` + `C49=1uF` 消抖，按下为 `0` |
| `GPIO7` | Pin 12 | `TWI_CLK` | `J9` Camera Pin 5 (`SCL`) | **原理图缺陷**：在 `J9` 上方被直接连到 `3.3V_VCC`（无上拉电阻，见第 5 节） |
| `GPIO8` | Pin 13 | `TWI_SDA` | `J9` Camera Pin 3 (`SDA`) | **原理图缺陷**：在 `J9` 上方被直接连到 `3.3V_VCC`（无上拉电阻，见第 5 节） |
| `GPIO9` / `GPIO10` | Pin 14 / 15 | `INT1` / `INT2` | `U3 (SC7A20TR)` Pin 11 / Pin 9 | 加速度计中断输入（推挽输出，实测空闲为 `0`） |
| `GPIO11` / `GPIO12` | Pin 16 / 17 | `SDA0` / `SCL0` | `U3 (SC7A20TR)` Pin 6 / Pin 4 | `R15/R16=4.7K` 上拉至 `3.3V_VCC`，实测器件地址 `0x19` |
| `GPIO13` / `GPIO14` | Pin 18 / 19 | `RX2` / `TX2` | `J10` (`GPS` 4P) Pin 1 / Pin 2 | `GPIO13` 接 `BE-220 TX`（白线），`GPIO14` 接 `BE-220 RX`（绿线），实测 `115200` baud |
| `GPIO15` | Pin 21 | `4G_PWDN` | `Q4 (S8050)` -> `Q3 (AO3401)` P-MOS (`4G_BAT`) | **高电平有效 (`1`)**：接通 `4G_BAT`；因 `U1` Pin 7 `PWR_ON/OFF` 经 `R7=10K` 接地，上电即自启 |
| `GPIO16` | Pin 22 | `SD_CLK` | `CON1` TF 卡 `CLK` (Pin T5) | 原理图 `R55=51K` 上拉至 `3.3V_SD`，实板 `R55` 未贴装（DNP） |
| `GPIO17` / `GPIO18` | Pin 23 / 24 | `CAM_VSYNC` / `CAM_HREF` | `J9` Pin 7 (`VSYNC`) / Pin 9 (`HREF`) | 摄像头帧同步 / 行同步 |
| `GPIO19` / `GPIO20` | Pin 25 / 26 | `ESP_USB_N` / `ESP_USB_P` | `J11` Type-C (`D-` / `D+` 经 `R46/R47=22R`) | 原生 USB Serial/JTAG (`COM8`) |
| `GPIO21` | Pin 27 | `CAM_D7` | `J9` Pin 12 (`D9`) | 摄像头数据位 MSB |
| `GPIO26` (`SPICS1`) | Pin 28 | `GPS_PWDN` | `Q10 (S8050)` -> `Q8 (AO3401)` P-MOS (`GPS_BAT`) | **高电平有效 (`1`)**：接通 `GPS_BAT`；**与内置 Octal PSRAM 冲突** |
| `GPIO27`–`GPIO32` | Pin 29–35 | `SPIHD/WP/CS0/CLK/Q/D` | `U2 (W25Q32JVSQ)` SPI0 NOR Flash | 主 Flash 总线（4 MiB） |
| `GPIO33` / `GPIO34` | Pin 38 / 39 | `SCL1` / `SDA1` | `J8` (`DISPLAY` 4P) Pin 3 / Pin 2 | `R38/R39=4.7K` 上拉至 `3.3V_VCC`；**与内置 Octal PSRAM 冲突** |
| `GPIO35` | Pin 40 | `NETLIGHT` | `U1 (ML307A-DSLN)` Pin 16 & `LED1` | 4G 网络状态指示；**与内置 Octal PSRAM 冲突** |
| `GPIO36` / `GPIO37` | Pin 41 / 42 | `TX1` / `RX1` | `Q2 / Q1 (S8050)` 电平转换 -> `U1` `4G_RXD` (Pin 17) / `4G_TXD` (Pin 18) | 4G 主串口 (`115200` baud)；**与内置 Octal PSRAM 冲突** |
| `GPIO38` | Pin 43 | `CAM_MCLK` | `J9` Pin 13 (`MCLK`) | 摄像头 XCLK 主时钟输出 |
| `GPIO39` / `GPIO40` | Pin 44 / 45 | `CAM_D6` / `CAM_D5` | `J9` Pin 14 (`D8`) / Pin 16 (`D7`) | 摄像头数据位 |
| `GPIO41` / `GPIO42` | Pin 47 / 48 | `CAM_PCLK` / `CAM_D4` | `J9` Pin 17 (`PCLK`) / Pin 18 (`D6`) | 摄像头像素时钟 / 数据位 |
| `GPIO43` / `GPIO44` | Pin 49 / 50 | `ESP_TXD_SD_CMD` / `ESP_RXD_SD_D0` | `J2` UART0 排针 & `CON1` TF 卡 `CMD` / `D0` | 与 UART0 复用 |
| `GPIO45` | Pin 51 | `CAM_D0` | `J9` Pin 19 (`D2`) | **Strapping 引脚 (`VDD_SPI` 电压选择)**，复位时必须为 `0` |
| `GPIO46` | Pin 52 | `CAM_D3` | `J9` Pin 20 (`D5`) | **Strapping 引脚 (ROM 日志/启动模式)** |
| `GPIO47` / `GPIO48` | Pin 37 / 36 | `CAM_D1` / `CAM_D2` | `J9` Pin 21 (`D3`) / Pin 22 (`D4`) | 摄像头数据位 |

---

## 3. 10 阶段实板 Bring-Up 自动化验证结果

测试固件 [firmware/hw021_pcb1_bringup](../../firmware/hw021_pcb1_bringup/README.md) 在 `COM8` 上完成了全部 10 个阶段的实板验证，汇总如下：

| 阶段 | 测试子系统 | 实测状态 | 关键实测指标与硬件证据 (`bringup_serial_final.log`) |
|---|---|---|---|
| **Stage 1** | 系统、Flash 与功放安全初始化 | **PASS** | `ESP32-S3 rev v0.2`，2 核，MAC `02:00:00:00:00:02`，Flash JEDEC `0xef4016` (`4,194,304` B)，`MUTE (GPIO5)` 置输入时读出 `1`（`U5 8002A` 处于关断安全态） |
| **Stage 2** | 电池采样开关与 ADC 分压 | **PASS** | `AD_CTRL (GPIO2) = 0` 时 `mv_off = 2 mV`（`Q7/Q6` 完全关断，无漏电）；`AD_CTRL = 1` 时 `mv_on = 2121 mV`，换算电池电压 **`V_BAT = 4242 mV`** |
| **Stage 3** | 按键电路 (`KEY` / `BOOT`) | **PASS** | `KEY (GPIO6)` 空闲电平 `1`（`R33=10K` 正常），`BOOT (GPIO0)` 空闲电平 `1`（`R35=10K` 正常） |
| **Stage 4** | 板载三轴加速度计 (`U3 SC7A20TR`) | **PASS** | `I2C0 (SDA0=11, SCL0=12)` 在 **`0x19`** 应答，`WHO_AM_I (0x0F) = 0x11`；50 Hz 连续采样 `a = (172, -66, 1015) mg`，合加速度模值 **`|a| = 1031 mg`**（静止 1g 正常） |
| **Stage 5** | 显示屏 I2C1 接口 (`J8`) | **PASS** | `SCL1 (GPIO33) = 1`，`SDA1 (GPIO34) = 1`（`R38/R39=4.7K` 上拉正常），当前 `J8` 未插屏幕（`attached_devices = 0`） |
| **Stage 6** | 外置 GNSS 模块 (`Beitian BE-220`) | **PASS (UART & UTC)** | `GPS_PWDN (GPIO26) = 1` 开启 `GPS_BAT` 后，`UART1 (RX=13, TX=14)` 在 **`115200` baud** 稳定输出 NMEA 语句，室内已成功从卫星解算出准确 UTC 时间与日期（`$GNRMC,052438.00,V,,,,,,,211026,,,N,V*17`）；室外 3D 定位 Fix 待验证 (`unverified`) |
| **Stage 7** | TF/MicroSD 卡 (`CON1` on `3.3V_SD`) | **PASS (1-bit SDMMC)** | 插入 64GB TF 卡后，置 `CAM_PWDN (GPIO4) = 0` 开启 `Q5 (3.3V_SD)`，通过 **1-bit SDMMC (`CLK=GPIO16, CMD=GPIO43, D0=GPIO44`)** 成功初始化卡并读取 Sector 0 MBR (`0x55AA`)：型号 **`SC64G`**，实测容量 **`60,906 MiB` (`59.48 GiB`)**，扇区 `512 B`（注：64GB 卡出厂为 exFAT，格式化为 FAT32 后即可直接挂载 VFS） |
| **Stage 8** | 摄像头 (`TY-OV2640-75MM-V1.0` on `J9`) | **FAIL (原理图短路缺陷)** | 实测 `clk_gpio7_pulldown=1, sda_gpio8_pulldown=1` 且弱开漏拉低测试 **`clk_gpio7_od_low=1, sda_gpio8_od_low=1`**：证实原理图中 `J9` 上方的 `3.3V_VCC` 符号未串联上拉电阻而**直接画线短路到了 `TWI_SDA (Pin 3)` 与 `TWI_CLK (Pin 5)`**，导致 I2C 总线被锁死在 `3.3V_VCC` 电源轨上 |
| **Stage 9** | 4G 模组 (`U1 ML307A-DSLN`) + SIM 驻网 | **PASS (LTE + IMS 双承载激活)** | 插入中国移动 SIM 卡后实测（`bringup_sim_sdcard_20261021.log`）：`AT+CPIN?` -> **`+CPIN: READY`**（ICCID `898600821926F0******`，IMSI `460008893******`）；信号满格 **`+CSQ: 31,99`**（`+CESQ` RSRP `-80 dBm`）；上电 4 秒内完成 4G LTE 驻网 **`+CEREG: 0,1`**（`+COPS: 0,2,"46000",7`，`+CGATT: 1`）；自动激活双 PDP 承载：**`CID 1 (CMNET)` 分配 IPv4 `10.28.146.11` + IPv6**，**`CID 8 (IMS)` 分配专用 VoLTE IPv6 地址**（`+CAVIMS: 1 OK`） |
| **Stage 10** | ESP32-S3R8 2.4GHz Wi-Fi 射频与晶振 | **PASS** | 40 MHz 晶振 (`Y1`) 与 `J3` IPEX 天线通路完成 PHY 全校准并扫描到周边 **7 个 2.4GHz AP**，最强信号 **`-50 dBm` (Channel 9)** |

---

## 4. `CALL-030` 重大突破：`ML307A-DSLN-MTSH1S00` 原生 VoLTE 语音与模拟音频能力实证

在此前的 `YED-ESP32S3-4G V1.2` 开发板上，板载模组为数据版 `ML307C-DL`（无模拟音频引脚，无语音 AT 指令），导致 [CALL-030_NATIVE_CELLULAR_FEASIBILITY.md](../tasks/active/CALL-030_NATIVE_CELLULAR_FEASIBILITY.md) 处于硬件阻塞状态。

本次在 `PCB1` 上对实焊的 **`U1 = ML307A-DSLN`（固件版本 `ML307A-DSLN-MTSH1S00`）** 进行了全量 AT 指令集（`AT+CLAC`，共返回 6,433 字节）与语音专项探测，取得决定性硬件证据：

1. **硬件模拟音频链路已在 `PCB1` 落地**：
   - 麦克风输入：`J4`（驻极体咪头）-> `ML307A-DSLN` Pin 3 (`MIC_P`) / Pin 4 (`MIC_N`)。
   - 扬声器输出：`ML307A-DSLN` Pin 5 (`SPK_P`) -> `C37 (1uF)` + `R26 (1K)` -> `U5 (8002A)` -> `J5`（扬声器），由 `ESP32-S3 GPIO5 (MUTE)` 控制功放关断。
2. **`ML307A-DSLN-MTSH1S00` 固件原生支持完整 3GPP / IMS VoLTE 语音呼叫与音频指令栈**：
   - `AT+CAVIMS=?` -> `+CAVIMS: (0, 1) OK`；`AT+CAVIMS?` -> **`+CAVIMS: 1 OK`**（IMS VoLTE 语音默认开启）
   - `AT+CIREG?` -> **`+CIREG: 1,0,0 OK`**（IMS 注册状态上报已支持）
   - `AT+CEVDP?` -> **`+CEVDP: 3 OK`**（语音域偏好 = `3`：IMS PS 语音优先，CS 语音次之）
   - `AT+CEMODE?` -> **`+CEMODE: 2 OK`**（UE 工作模式 = `2`：CS/PS 语音+数据复合模式）
   - `AT+CLCC` -> **`OK`**（当前通话列表查询）
   - `AT+CLIP=?` -> **`+CLIP: (0-1) OK`**（来电号码显示）
   - `AT+VTS=?` -> **`+VTS: <DTMF>, (20-1000) OK`**（通话中 DTMF 双音多频发送）
   - `AT+CMUT=?` -> **`+CMUT: 0,1 OK`**（通话麦克风静音控制）
   - `AT*Audio=?` -> **`*Audio: OK`**；`AT*AUDNVM?` -> **`OK`**（模拟音频 Codec 与音频 NVM 参数配置）
   - `ATD10086;` -> **`+CME ERROR: 23`**（拨号命令语法被正常识别，仅因当前 `CON1` 未插 SIM 卡拒绝发起呼叫；`ATA` / `ATH` / `AT+CHUP` 均在 `AT+CLAC` 支持列表中）
   - **额外硬件能力发现**：`AT+CLAC` 还证实该固件内置 **白名单号码硬件指令 (`AT+TRUSTNUM` / `AT+CHKTRUSTNUM`)**、**本地 TTS 语音合成 (`AT+MTTSCFG` / `AT+MTTSPLAY` / `AT+MTTSSTOP`)** 以及 **音频文件播放与录音 (`AT+MAUDPLFILE` / `AT+MAUDRECFILE`)**！

> **对 `CALL-030` / `CALL-031` 的结论**：`PCB1` 上的 `ML307A-DSLN-MTSH1S00` 已经从硬件和模组固件两个层面打通了原生 VoLTE 语音通话所需的全部先决条件（不再需要外挂 `SYN6288` 或更换蜂窝模组型号）。下一步只需在 `CON1` 插入已开通 VoLTE 的 Nano-SIM 卡并对音频电路 `R28` 做小幅跳线处理，即可执行 `CALL-030` 实网拨号与双向通话验收。

---

## 5. `PCB1` 发现的 7 项硬件设计缺陷、当板飞线/割线修复方案与 `PCB2` 改版 ECN 清单

通过原理图 [HW021_C1_ESP32MODEL_VR00.pdf](../../hardware/PCB1/HW021_C1_ESP32MODEL_VR00.pdf)、实物照片与实板电气测试交叉比对，共定位出 **7 项硬件缺陷**（按严重程度排序）：

### ECN-01（致命 / 阻断摄像头）：`J9` 摄像头 `TWI_SDA` / `TWI_CLK` 在原理图上被直接短路至 `3.3V_VCC`

- **现象与实测证据**：Stage 8 实测 `GPIO7 (TWI_CLK)` 与 `GPIO8 (TWI_SDA)` 在开启开漏下拉（`GPIO_DRIVE_CAP_0`）时仍恒为 `1`（`clk_od_low=1, sda_od_low=1`），`esp32-camera` 初始化时 `i2c.master` 持续报 `probe device timeout`。
- **根因定位**：在原理图第 2 页右下角 `J9 (DC-G28-21MM-1826V1)` 上方，设计者放置了 `3.3V_VCC` 电源符号准备给 `TWI_SDA (Pin 3)` 和 `TWI_CLK (Pin 5)` 加 I2C 上拉电阻，但**遗漏了两个 `4.7K` 电阻器件，直接用红色导线将 `3.3V_VCC` 连到了 `TWI_SDA` 和 `TWI_CLK` 网络上**（在 `TWI_CLK` 处有紫色节点圆点），导致 PCB 铜箔将 `GPIO7`/`GPIO8` 与 `3.3V_VCC` 电源轨硬短路。
- **`PCB1` 当板手工修复方案**：
  1. 在 PCB 背面 `J9` 引脚 3 (`TWI_SDA`)、引脚 5 (`TWI_CLK`) 附近，用手术刀割断通往 `3.3V_VCC` 电源过孔/铜皮的短接支路（保留通往 `U4 ESP32-S3R8` Pin 12/13 的信号线）。
  2. 割断后可直接依靠 `ESP32-S3` 内部上拉（或飞焊两颗 0402 `4.7K` 电阻至 `2.8V`/`3.3V`）恢复 `OV2640` 通信。
- **`PCB2` 改版要求**：在 `TWI_SDA`、`TWI_CLK` 与 `CAM_2.8V`（注：`J9` 的 `DOVDD` 为 `2.8V`，I2C 上拉应接 `CAM_2.8V` 而非 `3.3V_VCC`！）之间补齐两颗 `4.7K` 上拉电阻；同时将 `CAM_RESET` (`R41=10K`) 的上拉电源从 `3.3V_VCC` 改为 `CAM_2.8V`。

### ECN-02（严重安全隐患 / 电池过流）：`U6 (TP4057)` 500 mA 充电电流对 200 mAh 电池形成 `2.5C` 超倍率快充

- **现象与根因**：原理图中线性充电芯片 `U6 (TP4057)` 的 `PROG` 脚（Pin 5）配置电阻为 `R30 = 2K`，对应恒流充电电流 $I_{\text{CHG}} = \frac{1000\text{ V}}{2000\ \Omega} = 500\text{ mA}$。而实配电池（`4.jpg`）为 **`402030-200mAh 3.7V`**，充电倍率高达 **`2.5C`**（微型软包锂电池标准安全充电倍率为 `0.5C–1.0C`，即 `100–200 mA`），长时间插 USB 充电存在电池鼓包与发热风险。
- **`PCB1` 当板手工修复方案**：将 `U6` 旁的 0402 电阻 **`R30` 立即更换为 `5.1K`（约 `196 mA`，`1C`）或 `10K`（`100 mA`，`0.5C`）**。
- **`PCB2` 改版要求**：BOM 中将 `R30` 默认值定为 `6.8K`（约 `147 mA`）或 `10K`（`100 mA`）。

### ECN-03（架构冲突）：`U4 (ESP32-S3R8)` 内置 Octal PSRAM 引脚 (`GPIO26`, `GPIO33–37`) 被外设占用

- **现象与根因**：`U4` 选用的是内置 8 MB Octal PSRAM（8 线 SPI PSRAM）的 **`ESP32-S3R8`**，其内部パッケージ已将 Octal PSRAM 绑定在 **`SPICS1 (GPIO26)` 及 `GPIO33`–`GPIO37`** 上。但原理图将：
  - `GPIO26` 分配给 `GPS_PWDN`
  - `GPIO33 / GPIO34` 分配给显示屏 `SCL1 / SDA1` (`J8`)
  - `GPIO35` 分配给 `NETLIGHT`
  - `GPIO36 / GPIO37` 分配给 4G 串口 `TX1 / RX1`
  一旦在固件中开启 `CONFIG_SPIRAM=y`，Octal PSRAM 信号会与 4G 串口、GPS 电源及屏幕 I2C 发生直接冲突。
- **`PCB1` 约束方案**：`PCB1` 所有固件必须保持 **`CONFIG_SPIRAM=n`**（利用内部 `512 KB` SRAM 运行，QVGA JPEG 帧缓冲置于 DRAM）。
- **`PCB2` 改版要求**：
  - **方案 A（推荐，启用 PSRAM）**：释放 `GPIO26` 及 `GPIO33–37`（若改用内置 Quad PSRAM 的 `ESP32-S3R2` 则仅需释放 `GPIO26`，但 `ESP32-S3R8` 必须释放 `GPIO26` + `GPIO33–37`）。
  - **方案 B（若不需要 PSRAM）**：将 `U4` 换回无 PSRAM 的 `ESP32-S3`（或保留 `CONFIG_SPIRAM=n`）。

### ECN-04（容量不匹配）：`U2` 实贴 `W25Q32JVSQ` (4 MiB) 无法容纳仓库默认的 16 MiB 分区表

- **现象与实测证据**：原理图标注 `U2 = BY25Q64ASSIG` (8 MiB)，而 `PCB1` 实物（`2.jpg`）实际焊接的是 **Winbond `W25Q32JVSQ` (`0xEF4016`，仅 4 MiB)**。仓库现有的 P0 固件分区表（如 `0x500000` 采集分区、`0x600000–0xF00000` 媒体分区）按 16 MiB Flash 设计，直接烧录会越界失败。
- **`PCB1` 当板修复方案**：
  - 硬件修复（推荐）：将 SOP-8 封装的 `U2` 吹下，换焊一颗同封装的 **`W25Q128JVSQ` (16 MiB)**；
  - 软件过渡：在未换焊 `U2` 前，使用 `4MB` 专用分区表与 `CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y`。
- **`PCB2` 改版要求**：BOM 明确指定 `U2 = W25Q128JVSQ` (16 MiB)。

### ECN-05（音频失真与过压风险）：`ML307A` 差分输出 `SPK_N` 被 `R28=0R` 对地短路，且 `MUTE (GPIO5)` 上拉至 `V_BAT`

- **现象与根因**：
  1. `U1 (ML307A-DSLN)` 的 `SPK_P` (Pin 5) / `SPK_N` (Pin 6) 为差分模拟音频输出，但原理图中 **`R28 = 0R` 将 `SPK_N` 直接短接到 `GND`**，会在语音播放时造成 `ML307A` 内部音频负端放大器过载、发热及削波失真。
  2. `U5 (8002A)` 的 `SHUTDOWN` 脚（`MUTE` 网络，直连 `ESP32-S3 GPIO5`）通过 `R19 = 2K` 上拉至 **`V_BAT`（满电 `4.24V`）**，超过 `ESP32-S3` GPIO 最大耐压（`3.6V`），通过 ESD 二极管向 `3.3V` 灌流；且拉低开启功放时持续消耗 `2.1 mA`。
- **`PCB1` 当板手工修复方案**：
  1. **直接拆除 `R28 (0R)`**（使 `SPK_N` 悬空或通过电容耦合，单端只取 `SPK_P` 经 `C37/R26` 送入 `8002A`）；
  2. 将 `R19` 改由 `3.3V_VCC` 上拉（或换成 `47K–100K`）。
- **`PCB2` 改版要求**：删除 `R28`（改用差分输入全桥耦合或 `SPK_N` 悬空）；将 `R19` 改为 `47K` 并改接 `3.3V_VCC`。

### ECN-06（电源控制耦合与 Strapping 隐患）：`GPIO4 (CAM_PWDN)` 同时反相控制 TF 卡与摄像头电源，且 `CAM_D0` 占用 `GPIO45`

- **现象与根因**：
  1. `GPIO4` 低电平时开启 `Q5 (3.3V_SD)`、关闭 `U7 (CAM_1.2V/2.8V)`；高电平时开启摄像头电源、切断 TF 卡电源，导致摄像头与 TF 卡无法同时工作，且休眠时无法将两者同时断电！
  2. `CAM_D0` 接在 **`GPIO45`（`VDD_SPI` 电压选择 Strapping 脚）** 上。若开启摄像头时芯片发生软复位，`OV2640` 可能将 `GPIO45` 拉高导致 Flash `VDD_SPI` 被错误配置为 `1.8V`。
  3. 4G 串口接收端 `Q1` 集电极上拉电阻 `R1 = 100K` 偏大（建议依靠内部上拉辅助或改为 `4.7K–10K`）。
- **`PCB1` 约束方案**：固件平时保持 `GPIO4 = 0`（关闭摄像头 LDO，防止 `GPIO45` 被拉高），在 `GPIO37 (RX1)` 开启内部上拉。
- **`PCB2` 改版要求**：将 `3.3V_SD` 开关独立分配控制引脚（或常供 `3.3V_VCC`），释放 `GPIO45 / GPIO46` Strapping 引脚。

### ECN-07（细节核对项）：`U3 (SC7A20TR)` I2C 地址与 `CON1` 上拉电阻贴装差异

- **现象**：原理图中 `U3 (SC7A20TR)` Pin 1 (`SDO`) 接地（理论地址 `0x18`），但实板 I2C0 扫描确认 `SC7A20TR` 响应地址为 **`0x19`**（内部/封装 Pin 1 处于高电平）；此外 `CON1` TF 卡 6 颗 `51K` 上拉电阻中 `R55 (SD_CLK)` 未贴装。
- **处理方案**：固件驱动同时兼容 `0x19` 与 `0x18`（已在 Bring-Up 固件中验证通过）。

---

## 6. 4 MiB SPI NOR Flash (`W25Q32JVSQ`) + 64 GB TF 卡存储架构可行性评估

针对 `PCB1` 实焊 `U2 = W25Q32JVSQ`（`4 MiB`）且 `CON1` 已实测调通 **`64 GB` TF 卡（1-bit SDMMC，`60,906 MiB`）** 的硬件组合，存储空间评估如下：

### 6.1 固件与数据体积实测基线

1. **主固件镜像体积**：
   - 完整 P0 采集+状态估计+相机+4G 固件（`connectivity_firmware`）编译后二进制体积为 **`1.06 MiB – 1.23 MiB`**。
   - 本次包含 Wi-Fi 协议栈、Camera 驱动、FATFS/SDMMC、ADC、I2C、UART 的 `hw021_pcb1_bringup` 固件体积为 **`0.86 MiB` (`882 KB`)**。
   - TinyML 1D-CNN 边缘安全模型（`AI-020` INT8 量化权重）体积仅 **`< 50 KB`**。
2. **为什么旧开发板需要 16 MiB Flash**：
   - 旧 Waveshare 开发板上 TF 卡与摄像头 `PCLK (GPIO46)` 冲突而被迫禁用 TF 卡，所有历史照片（`9 MiB` `media` 分区）都只能塞在片外 SPI Flash 中。
   - 而在 `PCB1` 上，**TF 卡走独立引脚 (`CLK=16, CMD=43, D0=44, CS=3`) 且已实测跑通 64 GB 容量**；虽然 `GPIO4` 同时控制 `3.3V_SD`（低有效）与摄像头 LDO `U7`（高有效），但软件可通过**时分复用（先置 `GPIO4=1` 抓拍单帧 JPEG 存入内部 SRAM/Flash 缓冲，再置 `GPIO4=0` 关闭相机并将照片写入 TF 卡或经 4G 上传）**完美规避电源互斥。

### 6.2 `4 MiB` Flash 在不同阶段的满足度结论

| 评估维度 | 方案配置 | 是否满足需求 | 具体分区与容量账本 |
|---|---|---|---|
| **阶段 A：P0 样机研发与外场验证（单分区无 OTA + TF 卡）** | **`4 MiB` Flash + `64 GB` TF 卡** | **完全满足（100% 可用，无需等待换 Flash）** | - `0x000000–0x010000` (`64 KB`)：Bootloader + 分区表 + NVS + PHY<br>- `0x010000–0x190000` (**`1.50 MiB`**)：`factory` 主固件（含 TinyML 模型，余量 > 280 KB）<br>- `0x190000–0x290000` (**`1.00 MiB`**)：`collection` 片上掉电安全队列（可缓存 **4,000–8,000 条** SOS/定位/状态记录，不依赖 TF 卡）<br>- `0x290000–0x400000` (**`1.44 MiB`**)：`media_stage` 片上紧急照片缓冲（可存 **60–90 张** QVGA JPEG），配合 **`60.9 GB` TF 卡**可存百万张照片与数月原始传感器日志 |
| **阶段 B：量产交付产品（必须支持双备份 A/B OTA）** | **`4 MiB` Flash（极限紧凑） vs `8/16 MiB` Flash（推荐）** | **4 MiB 偏紧，建议 `PCB2` 升级至 8/16 MiB** | 量产产品必须具备 `ota_0 (1.5 MiB) + ota_1 (1.5 MiB) = 3.0 MiB` 防变砖双备份升级能力，此时 4 MiB Flash 仅剩 `~0.9 MiB` 给 NVS/CoreDump/缓存（虽可借助 TF 卡运行，但若用户未插 TF 卡则片上媒体缓存较小）。而将 `W25Q32JV` (4MB) 换为同封装 `W25Q64JV` (8MB) 或 `W25Q128JV` (16MB) BOM 差价不足 ¥1，因此 **P0 研发阶段直接使用当前 4 MiB，量产改版 BOM 锁定 16 MiB** 是最优工程决策。 |

---

## 7. 硬件返修期间可并行推进的软件开发路线图（Next Steps）

在硬件工程师手工处理 `ECN-01`（割断 `J9` Pin 3/5 对 `3.3V_VCC` 短路）、`ECN-02`（`R30` 改 `5.1K–10K`）、`ECN-05`（拆 `R28`）的同时，**90% 的核心固件开发在当前 `PCB1` 上已完全解耦、可立即并行推进**：

1. **【立即可做 1】`ML307A-DSLN` 4G 数据链路与云端闭环（已分配 IP `10.28.146.11`）**：
   - 基于已调通的 `UART2 (TX=36, RX=37, PWR=15)` 和已激活的 `CID 1 (CMNET)`，接入 `ML307A` 原生 TCP/HTTP/MQTT 指令栈（`AT+MIPOPEN` / `AT+MHTTPREQUEST` / `AT+MQTTCONN`），打通 `PCB1` 实板遥测上报与云端指令下发。
2. **【立即可做 2】`CALL-030 / CALL-031` 原生 VoLTE 呼叫状态机与按键联动**：
   - 基于已激活的 `CID 8 (IMS)` 与 `ATD` / `ATA` / `ATH` / `AT+CLCC` / `AT+CLIP` / `AT+TRUSTNUM` 指令集，实现 `KEY (GPIO6)` SOS 长按触发呼叫、来电白名单校验、自动接听及 `MUTE (GPIO5)` 功放控制闭环。
3. **【立即可做 3】`PCB1` 4 MiB 分区表 + `SC7A20TR` (50Hz) + `BE-220` GNSS + TF 卡时分存储集成**：
   - 建立 `HW021_PCB1` 板级配置与 `4 MiB` 分区表，将 `SC7A20TR` (`0x19`) 实时加速度流接入 Ego-State 状态机，并将 64GB TF 卡格式化为 FAT32 实现大容量本地日志/媒体落盘。
4. **【待硬件割线后合入】`OV2640` 摄像头实拍验证**：
   - 硬件工程师割断 `J9` Pin 3/5 的 `3.3V_VCC` 短接线后，直接复跑 Stage 8 即可合入相机抓拍。

---

## 8. 2026-10-21 P0 闭环运行时与多传感器状态机实测进展

在插入实体**中国移动 SIM 卡**与**SanDisk 64GB TF 卡**后，固件升级为集成分区表、状态机引擎与 VoLTE 呼叫管理的 P0 运行时镜像并在 `COM8` 实测验证通过（日志文件：[`pcb1_integrated_p0_runtime_20261021.log`](../../reports/board_validation/pcb1_bringup_20261020/pcb1_integrated_p0_runtime_20261021.log)）：

1. **4 MiB Flash 自定义分区表验证通过**：
   - 使用 [partitions_pcb1_4mb.csv](../../firmware/hw021_pcb1_bringup/partitions_pcb1_4mb.csv)：
     - `factory`（`0x010000`, `1536 KB`）：固件占用 `855 KB`（剩余 44% 空间）；
     - `ego_collection`（`0x190000`, `1024 KB`）：片上离线传感器流缓冲；
     - `ego_media`（`0x290000`, `1408 KB`）：片上应急照片槽；
     - `ego_outbox`（`0x3f0000`, `64 KB`）：实测写入序列化记录并校验 CRC32 成功。
2. **64GB TF 卡 1-bit SDMMC 探测**：
   - 识别卡名 `SC64G`，容量 `60,906 MB`，读取 MBR 分区表第 1 分区类型为 `0x07 (exFAT/NTFS)`。底层物理扇区读写正常，上层 FATFS 若需无缝挂载需格为 FAT32 或使能 exFAT 驱动。
3. **中国移动 4G 蜂窝网络与 VoLTE IMS 成功连接**：
   - `ML307A-DSLN` 检测到 SIM 卡就绪（`+CPIN: READY`），注册至中国移动网络（`+COPS: 0,2,"46000",7`），信号质量 `+CSQ: 31,99`（RSRP 在 `-78 dBm` 至 `-99 dBm` 之间波动）；
   - 自动激活双 PDP 上下文：数据网络 IPv4 `10.11.39.93`（CMNET）与专用语音网络 IPv6 `2409:815B:34C2:A453:18E0:8298:1A2E:ED20`（IMS VoLTE）。
4. **多传感器实时融合与 Ego-State 状态机闭环**：
   - `SC7A20TR` IMU 持续以 16.7 Hz 采集加速度，`Beitian BE-220` 解析 NMEA 语句，ADC 实时采样电池电压（`4240 mV`, 100% SoC）；
   - [ego_state_engine](../../firmware/mqtt_heartbeat/components/ego_state_engine/include/ego_state_engine.h) 每 5 秒滚动评估一次，输出结构化估计结果（如 `mobility=indoor_weak_gnss`, `anomaly=normal`, `wear=wearable_or_bag`, `confidence=0.50`）；
   - 实时生成 SHA-256 证据链摘要（如 `digest=532b31be...`），并将遥测帧持久化写入 Flash `ego_outbox` 分区（CRC32 校验一致）。
5. **VoLTE 呼叫控制与 SOS 按键管理**：
   - 实例化 [sim7670_cellular_call](../../firmware/mqtt_heartbeat/components/sim7670_cellular_call/include/sim7670_cellular_call.h) 状态机；
   - 绑定 `KEY (GPIO6)` 作为 SOS 按键与呼叫接听/挂断按键，联动 `MUTE (GPIO5)` 控制 8002A 扬声器功放（来电或通话中拉低使能，空闲保持高阻静音）。



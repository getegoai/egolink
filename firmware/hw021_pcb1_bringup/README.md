# `hw021_pcb1_bringup` — `HW021_C1_ESP32MODEL_VR00` (`PCB1`) 10-Stage Hardware Bring-Up Firmware

## Overview

Non-destructive 10-stage hardware bring-up and electrical diagnostic firmware for the first custom integrated prototype PCB (`hardware/PCB1/HW021_C1_ESP32MODEL_VR00.pdf`, silkscreen `HW021_C1_ESP32MODEL 20260924`).

## Hardware Safety Guards (`PCB1` Specific)

1. **`CONFIG_SPIRAM=n` Mandatory**: `U4` (`ESP32-S3R8`) bonds internal Octal PSRAM to `SPICS1` (`GPIO26`) and `GPIO33`–`GPIO37`, which `PCB1` routes to `GPS_PWDN` (`GPIO26`), `SCL1/SDA1` (`GPIO33/34`), `NETLIGHT` (`GPIO35`), and `4G_TX1/RX1` (`GPIO36/37`). Enabling PSRAM causes immediate bus contention.
2. **`CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y`**: `U2` is populated with Winbond `W25Q32JVSQ` (`32Mbit` / `4 MiB`, JEDEC ID `0xEF4016`).
3. **`GPIO5` (`MUTE`) High-Z Input**: `R19` (`2K`) pulls `U5` (`8002A`) Pin 1 (`SHUTDOWN`) up to `V_BAT` (`~4.24V`). Keeping `GPIO5` as input avoids sinking `2.1 mA` standby current and keeps `U5` in shutdown during bring-up.
4. **`GPIO7/GPIO8` (`TWI_CLK/TWI_SDA`) Open-Drain `3.3V_VCC` Short Pre-Check**: On `HW021_C1_ESP32MODEL_VR00.pdf`, the `3.3V_VCC` symbol above `J9` is wired directly into `TWI_SDA` (`J9` Pin 3) and `TWI_CLK` (`J9` Pin 5) without pull-up resistors. Stage 8 tests weak open-drain low (`GPIO_DRIVE_CAP_0`) for `30 us` before attempting `esp_camera_init()` to prevent continuous I2C bus contention.
5. **`GPIO45` (`CAM_D0`) Strapping Guard**: `CAM_PWDN` (`GPIO4`) is returned to `0` (`U7` LDO off) and `GPIO45` is pulled down after Stage 8 so `VDD_SPI` remains `3.3V` across resets.

## 10 Bring-Up Stages

| Stage | Subsystem | Pins | Verification Target |
|---|---|---|---|
| Stage 1 | MCU, Flash & Audio Shutdown | `GPIO5` (`MUTE`), SPI0 Flash | Chip rev, MAC, Flash JEDEC ID (`0xEF4016`), `GPIO5` idle level |
| Stage 2 | Battery Switch & ADC | `AD_CTRL=GPIO2`, `ADC_V=GPIO1` (`ADC1_CH0`) | `Q7/Q6` high-side switch OFF vs ON voltage (`V_BAT = 2 * V_ADC`) |
| Stage 3 | Buttons | `KEY=GPIO6` (`K1`), `BOOT=GPIO0` (`K3`) | External `10K` pull-ups (`R33`, `R35`) idle HIGH check |
| Stage 4 | Onboard G-Sensor (`U3`) | `SDA0=GPIO11`, `SCL0=GPIO12`, `INT1/2=GPIO9/10` | `SC7A20TR` I2C probe (`0x19`), `WHO_AM_I` (`0x11`), 50 Hz XYZ gravity norm |
| Stage 5 | Display I2C Header (`J8`) | `SCL1=GPIO33`, `SDA1=GPIO34` | `R38/R39` (`4.7K`) pull-up idle level & I2C1 bus scan |
| Stage 6 | External GNSS (`J10`) | `GPS_PWDN=GPIO26`, `RX2=GPIO13`, `TX2=GPIO14` | `Q10/Q8` `GPS_BAT` power switch, `Beitian BE-220` baud & NMEA-0183 stream |
| Stage 7 | SD Rail vs Camera Rail | `CAM_PWDN=GPIO4`, `SD_CS=GPIO3`, `SD_CLK=GPIO16` | `Q5` (`3.3V_SD`) vs `U7` (`CAM_1.2V/2.8V`) shared `GPIO4` polarity check |
| Stage 8 | Camera (`J9`) | `CAM_PWDN=GPIO4`, `TWI=GPIO7/8`, `DVP=GPIO17..48` | `TWI_CLK/SDA` short-to-`3.3V_VCC` electrical check & `OV2640` probe |
| Stage 9 | 4G Modem (`U1`) | `4G_PWDN=GPIO15`, `NETLIGHT=GPIO35`, `TX1/RX1=GPIO36/37` | `Q4/Q3` `4G_BAT` switch, `ML307A-DSLN` AT handshake, VoLTE/IMS & `AT+CLAC` |
| Stage 10 | 2.4 GHz Wi-Fi RF & XTAL | `J3` IPEX, `L2`, `Y1` (40 MHz) | `ESP32-S3R8` RF calibration & active 2.4 GHz AP scan (count + RSSI) |

## Build & Flash (`COM8`)

```powershell
python "$env:IDF_PATH\tools\idf.py" -C "firmware/hw021_pcb1_bringup" -B "D:/tmp/pcb1_bringup_build" build
python -m esptool --chip esp32s3 -p COM8 -b 460800 --before default_reset --after hard_reset write_flash "@D:/tmp/pcb1_bringup_build/flash_args"
```

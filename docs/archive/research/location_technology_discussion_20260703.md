# Archive note

Moved from repository root `定位技术研讨.md` on 2026-07-03 during workspace
organization. This file is historical research input, not current authority.

**收不到卫星信号，不一定是代码问题，而是定位产品必须面对的真实场景。** Ego Link 不应该被设计成“等 GPS 定位成功再继续”的设备，而应该被设计成一个**多源定位 + 记忆学习 + 能耗自适应的位置智能体**。

我建议把这个能力命名为：

> **Ego Adaptive Location Engine，简称 EALE：自适应位置智能引擎。**

它的核心思想不是“GPS 定位”，而是：

> **先用低功耗信号维持粗定位，再用 GNSS 短脉冲校准，用历史记忆和行为模式不断缩小不确定范围；只有在不确定、异常或紧急时，才提高能耗换取精度。**

这比普通定位器的“基站定位 + GPS 定位”更进一步。普通定位器是静态 fallback；Ego Link 应该是一个会学习的个人位置系统。

---

## 1. 先明确：定位不是一个坐标点，而是一个“置信分布”

现在很多定位器的问题是：界面上只显示一个点，好像设备“知道自己在哪”。但真实情况经常是：

```text
我可能在这个区域内，半径 300 米，置信度 0.65；
我上一次高精度定位在学校门口；
当前基站指纹和学校附近很像；
IMU 判断设备静止；
所以我判断它大概率仍在学校区域内。
```

所以 Ego Link 的数据结构不应该只有：

```json
{
  "lat": 22.5431,
  "lon": 114.0579
}
```

而应该升级成：

```json
{
  "location_belief": {
    "lat": 22.5431,
    "lon": 114.0579,
    "radius_m": 180,
    "confidence": 0.72,
    "state": "coarse",
    "source": ["cell", "wifi_memory", "last_known"],
    "reason": "matched known school-area fingerprint; device is stationary"
  }
}
```

这就是创新点之一：**从坐标定位，升级为概率定位。**

---

## 2. GNSS 不是常开传感器，而是“高成本校准器”

GNSS 最大的问题是两件事：一是信号弱，二是功耗高。u-blox 的 A-GNSS 文档直接指出，信号捕获是卫星定位中的主要瓶颈之一，冷启动在理想条件下通常也要约 30 秒，复杂环境下会更久甚至失败；A-GNSS 的意义是通过无线网络或互联网提前提供卫星数据、准确时间和卫星状态，从而缩短首次定位时间并降低反复捕获带来的电量消耗。([u-blox][1])

所以产品设计上不能把 GNSS 当成“随时都能给答案”的基础能力，而要把它当成：

> **周期性、短时间、高置信度的位置校准器。**

具体策略是：

```text
默认不用 GNSS
    ↓
低功耗信号判断位置是否可信
    ↓
可信：继续低功耗运行
不可信：开启 GNSS 15–30 秒短脉冲
    ↓
拿到 fix：校准当前位置，并反向标注当前基站/Wi-Fi/时间/路线记忆
拿不到 fix：立即停止，不再死等，记录当前位置为 GNSS-bad zone
```

你现在阳台收不到信号，就应该被系统学习为：

```text
这个地点 / 这个朝向 / 这个网络指纹下，GNSS 获取成功率低。
以后不要一到这里就长时间开 GNSS 烧电。
```

这就是“负记忆”：**不仅记住哪里能定位，也记住哪里不值得开 GNSS。**

---

## 3. 多源定位架构：从低功耗到高精度分层启用

Ego Link P0 当前是 ESP32-S3 + SIM7670G 这类 4G/GNSS 终端路线，定位能力可以分成五层。

### 第 0 层：Last Known + 语义记忆

这是最低功耗的定位能力，几乎不耗电。

系统记住：

```text
上一次高精度位置
常驻地点：家、学校、单位、公交站、公园
常见路线：家 → 学校，学校 → 家
常见时间：早上出门，下午放学，晚上回家
常见停留时长
常见移动速度
```

比如设备早上 7:40 从家附近开始移动，基站指纹逐步接近学校路线，IMU 判断在移动，虽然没有 GPS，也可以给出一个“路线级位置判断”。

这不是“玄学 AI”，而是把定位问题从“单点测量”变成“时序推断”。

---

### 第 1 层：4G 基站指纹

SIM7670G 这类模块即使没有 GNSS，也可以通过 `AT+CPSI?` 获取当前蜂窝网络信息。SIM767XX AT 手册显示，LTE 场景下 `AT+CPSI?` 可返回 MCC/MNC、TAC、SCellID、PCellID、频段、earfcn、RSRQ、RSRP、RSSI、RSSNR 等信息；这些字段足够构成“基站指纹”。

这个能力很重要，因为 4G 模块本来就要联网，获取这些信息的额外能耗远低于长时间开启 GNSS。

基站指纹可以这样存：

```json
{
  "cell": {
    "mcc": "460",
    "mnc": "01",
    "tac": "0x230A",
    "scell_id": "175499523",
    "pcell_id": 318,
    "band": "EUTRAN-BAND3",
    "earfcn": 1650,
    "rsrp": -67,
    "rsrq": -21,
    "rssi": -67,
    "rssnr": 19
  }
}
```

早期可以只做“采集和上传”，不要急着做复杂算法。只要 VPS 里持续保存这些指纹，后续就可以做自学习定位。

这里的关键创新是：

> **不用完全依赖第三方基站定位 API，而是用自己的 GNSS 成功样本反向标注基站指纹，逐步形成个人化、区域化的 Cell Fingerprint Map。**

也就是说，某一次在室外 GPS 成功了，系统记录：

```text
当前位置 = A
当前基站指纹 = B
当前 Wi-Fi 指纹 = C
当前时间 = D
当前运动状态 = E
```

下次 GPS 失败，但 B、C、D、E 很像，系统就能推断当前位置接近 A。

---

### 第 2 层：Wi-Fi 指纹

ESP32-S3 本身有 Wi-Fi。即使不连接 Wi-Fi，也可以扫描周围 AP 的 BSSID 和 RSSI。

Wi-Fi 指纹对室内、阳台、学校、商场、家附近特别有用。Android 的 Fused Location Provider 就是典型的融合定位思路，它会管理 GPS、Wi-Fi 等底层定位技术，并允许应用在精度和功耗之间选择服务质量。([Google for Developers][2]) Android 官方文档也明确写到，融合定位会结合 GPS、Wi-Fi、蜂窝网络以及加速度计、陀螺仪、磁力计等传感器；而位置精度、计算频率、延迟都会影响电池消耗。([Android Developers][3])

Ego Link 可以做更私有化的版本：

```json
{
  "wifi": [
    {
      "bssid_hash": "hash_xxx",
      "rssi": -62
    },
    {
      "bssid_hash": "hash_yyy",
      "rssi": -74
    }
  ]
}
```

注意：不要直接上传明文 BSSID，可以在设备端加盐哈希，避免形成可逆的 Wi-Fi 位置隐私泄露。

---

### 第 3 层：IMU 运动状态

你当前硬件里已经有 QMI8658 IMU，这个非常有价值。

IMU 不适合长时间积分成绝对位置，因为漂移会越来越大。但它非常适合做三件事：

```text
1. 判断静止 / 走路 / 跑步 / 坐车；
2. 作为 GNSS 唤醒条件；
3. 在两次定位之间做短时间轨迹外推。
```

例如：

```text
设备静止 20 分钟：
    不开 GNSS，只低频心跳。

设备从静止变为移动：
    先查基站 + Wi-Fi 指纹。
    如果仍在安全区域，暂不开 GNSS。
    如果离开安全区域或置信度下降，再开 GNSS 短脉冲。

设备高速移动：
    判断可能坐车，降低 Wi-Fi 扫描频率，提高基站和 GNSS 校准频率。
```

这就是“AI 省电”的核心：**不是让模型直接算经纬度，而是让模型决定什么时候值得打开哪个传感器。**

---

### 第 4 层：GNSS 短脉冲高精度定位

SIM767XX 手册里已经有 GNSS 相关能力：支持冷启动、温启动、热启动命令；支持配置 GNSS 模式；支持 `AT+CGNSSINFO` 获取 GNSS 定位结果，并返回 GPS、GLONASS、GALILEO、BEIDOU 卫星数量、经纬度、速度、航向、PDOP、HDOP、VDOP、可见卫星数等字段；未定位时会返回空结果。

这说明固件不能只做“读经纬度”，而要把这些质量字段都上传：

```json
{
  "gnss": {
    "fix": false,
    "mode": null,
    "lat": null,
    "lon": null,
    "gps_svs": 0,
    "glonass_svs": 0,
    "galileo_svs": 0,
    "beidou_svs": 0,
    "pdop": null,
    "hdop": null,
    "vdop": null,
    "no_sv": 0,
    "fix_attempt_ms": 30000,
    "result": "no_fix"
  }
}
```

这样 Web Dashboard 不会只显示“没有坐标”，而是能显示：

```text
GNSS 已尝试 30 秒；
未定位；
可见卫星不足；
当前场景可能为阳台 / 室内 / 遮挡；
已切换为 Cell + Wi-Fi + Memory 粗定位。
```

这才是产品级体验。

---

## 4. 省电策略：用“不确定性”驱动传感器开关

u-blox 的低功耗 GNSS 白皮书提到，多星座跟踪可以提升可见卫星数量和定位鲁棒性，但也会增加信号捕获时间和功耗；主动天线可以改善弱信号场景，但 LNA 也会增加功耗；定位更新频率本身也会强烈影响 GNSS 功耗。

所以 Ego Link 不应该固定成“每 5 秒定位一次”，而应该进入状态机。

我建议设五个定位状态。

```text
L0：Deep Sleep / 安全静止
L1：Low Power Watch / 低功耗看护
L2：Moving Normal / 正常移动
L3：Uncertain Locate / 不确定定位
L4：Emergency Track / 紧急追踪
```

对应策略：

```text
L0 安全静止：
    GNSS 关闭
    低频心跳
    IMU 唤醒
    可选低频基站指纹

L1 低功耗看护：
    基站指纹为主
    偶尔 Wi-Fi 扫描
    不主动开 GNSS

L2 正常移动：
    基站 + IMU 持续
    Wi-Fi 间歇扫描
    只有置信度下降时 GNSS 短脉冲

L3 不确定定位：
    GNSS 短脉冲 15–30 秒
    同时采集基站、Wi-Fi、IMU
    成功则校准记忆，失败则退出，不死等

L4 紧急追踪：
    临时提高上报频率
    GNSS 可连续或密集短脉冲
    电量优先级让位于安全
```

这里的关键是：**功耗不是按时间固定控制，而是按风险和不确定性控制。**

---

## 5. AI 的真正作用：不是替代 GPS，而是管理“位置置信度”

这里要避免一个误区：AI 不能凭空制造卫星信号。阳台收不到卫星，AI 不能把物理信号变出来。

AI 有价值的地方在于四个方面。

第一，**传感器调度**。系统根据电量、移动状态、历史成功率、当前位置置信度、是否在安全区域、是否接近常见路线，决定是否打开 GNSS、是否扫描 Wi-Fi、是否提高上报频率。

第二，**多源融合**。把 GNSS、基站、Wi-Fi、IMU、历史轨迹、时间规律统一成一个位置概率分布。早期可以用规则 + 卡尔曼滤波 / 粒子滤波，后续再引入轻量模型。

第三，**个人位置记忆**。系统持续学习用户的地点、路线、停留时间、信号指纹。普通定位器只会显示位置；Ego Link 应该知道“这是家附近”“这是学校路上”“这是异常路线”。

第四，**异常识别**。例如儿童定位场景中，系统真正要解决的不是每秒 1 米级定位，而是：

```text
是否离开安全区域？
是否偏离常见路线？
是否在异常时间移动？
是否长时间无定位但信号还在？
是否进入 GNSS-bad 区域但基站/Wi-Fi 指纹正常？
是否突然高速移动？
```

这才是主动安全型随身设备的价值。

---

## 6. Ego Link 的创新可以定义为“个人化融合定位”

普通产品：

```text
GPS 有信号：用 GPS
GPS 没信号：用基站
都不行：显示离线或最后位置
```

Ego Link 应该是：

```text
GPS 有信号：
    获取高置信位置
    标注当前环境指纹
    更新个人位置记忆

GPS 没信号：
    不死等
    读取基站指纹
    读取 Wi-Fi 指纹
    读取 IMU 状态
    查询历史记忆
    输出带半径和置信度的位置估计

位置不确定：
    提高采样频率
    尝试 GNSS 短脉冲
    向用户解释当前不确定原因

位置异常：
    进入安全模式
    提高上报频率
    触发提醒或求助流程
```

这个系统的护城河不在某个传感器，而在：

> **设备越用越懂用户的地点、路线、信号环境和安全边界。**

这和 Ego 的“本地化、隐私代理人”主线是一致的：Ego Link 是 Ego 的 4G 远程接口扩展，核心位置记忆和个人上下文不应该变成外部云 API 的附庸。

---

## 7. 当前 GNSS 任务不要卡死在阳台，应改成 LOC 任务线

我建议现在把“GNSS 定位任务”重命名为：

> **LOC-001：Ego Link 多源定位观测与置信度上报**

第一阶段目标不是“必须定位成功”，而是“完整观测定位状态”。

### LOC-001：定义 Location Observation 协议

上报结构建议：

```json
{
  "type": "location_observation",
  "device_id": "ego-link-p0-001",
  "fw_version": "0.1.0",
  "seq": 10086,
  "timestamp": 1760000000,
  "observations": {
    "gnss": {
      "enabled": true,
      "fix": false,
      "mode": null,
      "lat": null,
      "lon": null,
      "gps_svs": null,
      "glonass_svs": null,
      "galileo_svs": null,
      "beidou_svs": null,
      "pdop": null,
      "hdop": null,
      "vdop": null,
      "no_sv": null,
      "attempt_ms": 30000,
      "result": "no_fix"
    },
    "cell": {
      "system_mode": "LTE",
      "mcc": "460",
      "mnc": "01",
      "tac": "0x230A",
      "scell_id": "175499523",
      "pcell_id": 318,
      "band": "EUTRAN-BAND3",
      "earfcn": 1650,
      "rsrp": -67,
      "rsrq": -21,
      "rssi": -67,
      "rssnr": 19
    },
    "wifi": {
      "scan_enabled": false,
      "aps": []
    },
    "imu": {
      "motion": "stationary",
      "confidence": 0.93
    }
  },
  "location_belief": {
    "lat": null,
    "lon": null,
    "radius_m": null,
    "confidence": 0.0,
    "state": "unknown",
    "source": [],
    "reason": "gnss_no_fix_and_no_memory"
  }
}
```

### LOC-002：先做基站指纹上报

不要等 GNSS 成功。先让设备每隔一段时间通过 `AT+CPSI?` 上传基站信息。因为 SIM767XX 手册已经明确该命令能返回 LTE 服务小区、信号质量和相关网络字段。

验收标准：

```text
断开 USB；
设备连接 VPS；
Web Dashboard 可以看到：
- 当前网络模式；
- MCC/MNC；
- TAC；
- SCellID；
- PCellID；
- RSRP / RSRQ / RSSI / RSSNR；
- 最后更新时间。
```

### LOC-003：GNSS 短脉冲，不允许无限等待

SIM767XX 支持 GNSS RTC 模式，可进入 RTC 并外部唤醒，或按 10–864000 秒周期唤醒；也支持 GNSS UART sleep/wakeup。

所以固件里应该有明确预算：

```text
gnss_attempt_budget_ms = 30000
```

流程：

```text
开启 GNSS
等待最多 30 秒
读取 AT+CGNSSINFO
成功：上传 fix
失败：上传 no_fix
关闭 / 休眠 GNSS
记录失败场景
```

验收标准：

```text
即使没有卫星定位，设备也必须向 VPS 上报 no_fix；
Web 不能卡住；
固件不能一直等待；
电源状态和定位尝试耗时必须可见。
```

### LOC-004：Web 不显示“失败”，显示“定位置信度”

Web Dashboard 应该显示三种状态：

```text
Fine：GNSS 高精度定位
Coarse：基站 / Wi-Fi / 记忆粗定位
Predicted：基于历史和运动状态预测
Unknown：信息不足
```

不要只显示“GPS失败”。要显示：

```text
当前定位状态：Coarse / Unknown
当前位置置信度：0.62
估计半径：300m
主要来源：Cell + Last Known
GNSS 状态：No Fix
建议动作：移动到开阔天空 / 等待下一次移动触发 / 紧急模式可强制高频定位
```

---

## 8. 后续可形成三阶段技术路线

### P0：观测完整

目标：

```text
GNSS 成功也能上报；
GNSS 失败也能上报；
基站指纹持续上报；
Web 能解释定位状态；
VPS 保存所有观测记录。
```

P0 的成果不是“定位很准”，而是“定位系统开始有数据闭环”。

---

### P1：规则融合

目标：

```text
last_known + cell + wifi + imu + gnss_quality
```

先不用复杂模型，用规则即可：

```text
如果 GNSS fix 且 HDOP 合格：
    location_belief = GNSS，radius 小

如果无 GNSS，但 cell fingerprint 命中历史高置信地点：
    location_belief = 历史地点，radius 中等

如果设备静止，且 cell/wifi 没变化：
    保持 last_known，confidence 缓慢下降

如果设备移动，且 cell/wifi 变化明显：
    confidence 快速下降，触发 GNSS 短脉冲
```

---

### P2：学习型融合

目标：

```text
个人位置图谱
基站/Wi-Fi 指纹库
常见路线模型
GNSS 成功率地图
能耗自适应策略
异常检测模型
```

数据越多，系统越省电，因为它会知道：

```text
哪些地方 GPS 有用；
哪些地方 GPS 没用；
哪些地方只看 Wi-Fi 就够；
哪些路线是正常；
哪些移动模式需要报警。
```

---

## 9. 一个很有产品感的定位口号

可以把 Ego Link 的定位能力描述成：

> **不是持续烧电追踪每一个点，而是持续理解用户在哪里、是否安全、是否异常。**

或者更技术化一点：

> **Ego Link 采用多源信号融合与个人位置记忆，将 GNSS 从常开定位器转变为高置信校准器，在保证安全感知的同时降低能耗。**

这比“4G 基站定位 + GPS 定位”高级很多，也更容易形成技术壁垒。

---

## 10. 下一步任务建议

```text
LOC-001：建立 Ego Link 多源定位观测协议

目标：
1. 不要求 GNSS 必须成功定位。
2. GNSS 成功、失败、超时都必须作为有效状态上报。
3. 新增 location_observation 消息类型。
4. 上报 gnss、cell、wifi、imu、location_belief 五类字段。
5. 先实现 cell 指纹采集：通过 AT+CPSI? 获取 LTE 网络信息。
6. GNSS 采用有限时间短脉冲策略，默认最多尝试 30 秒。
7. Web Dashboard 显示 Fine / Coarse / Predicted / Unknown 四种定位状态。
8. 所有定位观测上传 VPS，并写入数据库。
9. USB 只允许用于烧录和临时调试，验收必须通过 VPS + Web Dashboard 完成。

验收：
- 设备在无法 GNSS fix 时，Web 能看到 no_fix，而不是卡死。
- Web 能看到 LTE 基站指纹字段。
- Web 能看到最后一次定位尝试时间、尝试耗时、失败原因。
- 设备断开 USB 后仍能持续上报定位观测。
- 数据库中可以查询历史 location_observation。
```

这一步做完，Ego Link 就不再是“等 GPS”的玩具，而是一个真正有产品雏形的定位智能体。

[1]: https://www.u-blox.com/en/technologies/agnss-assistnow "Assisted GNSS (A-GNSS) | u-blox"
[2]: https://developers.google.com/location-context/fused-location-provider "Fused Location Provider API  |  Google for Developers"
[3]: https://developer.android.com/develop/sensors-and-location/location/battery "About background location and battery life  |  Sensors and location  |  Android Developers"

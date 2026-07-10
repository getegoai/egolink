采用**版本化代码覆盖包 + 明确接口契约**协同：

* 我负责模型架构、数据规范、训练与量化代码、模型文件和测试；
* Codex负责固件驱动、数据采集、通信、运行时适配和硬件联调；
* 你负责真实场景测试、数据授权、风险规则和最终验收。

这也符合 EGO“核心推理本地化、云端仅作可选增强，Ego Link作为4G随身入口”的总体定位。

## 一、先把“随身安全陪伴”收敛为一个闭环

第一阶段不同时做儿童、老人、骑行三个产品，而是建立一套共用的安全陪伴内核：

```text
传感器采集
    ↓
端侧事件检测
    ↓
端侧风险路由
    ↓
本地安全规则复核
    ↓
必要时上传结构化事件和证据
    ↓
Ego Base / PC模拟端进一步判断
    ↓
向设备下发询问、提醒、补充采集或紧急动作
```

P0先覆盖六类事件：

1. 手动SOS；
2. 疑似跌倒、撞击或摔车；
3. 撞击后长时间静止；
4. 异常停留、偏离预设范围；
5. 呼救声或异常高强度声音；
6. 低电量、4G失联等设备自身风险。

其中，SOS、紧急拨号、隐私关闭等必须由确定性规则处理，模型只提供风险概率和行动建议。

---

## 二、我与Codex的代码边界

建议在现有仓库中增加：

```text
EGOLINK/
├─ firmware/                    # Codex主维护
├─ pc_simulator/                # Codex主维护
├─ quality_tests/
│  ├─ firmware/
│  └─ model_contract/           # 我提供契约测试
│
├─ model_lab/                   # 我主维护
│  └─ safety_companion/
│     ├─ configs/
│     ├─ datasets/
│     ├─ src/
│     ├─ training/
│     ├─ evaluation/
│     ├─ export/
│     └─ tests/
│
├─ model_artifacts/             # 我提供的模型交付物
│  └─ safety_companion/
│     └─ v0.1.0/
│        ├─ model.bin
│        ├─ model_config.json
│        ├─ thresholds.json
│        ├─ model_card.md
│        └─ sha256.txt
│
├─ shared/
│  └─ contracts/                # 双方共同遵守，不随意修改
│     ├─ sensor_frame.schema.json
│     ├─ safety_event.schema.json
│     ├─ model_input.schema.json
│     ├─ model_output.schema.json
│     └─ base_command.schema.json
│
└─ docs/
   └─ modeling/
      ├─ SAFETY_COMPANION_ARCHITECTURE.md
      ├─ DATA_COLLECTION_SPEC.md
      └─ MODEL_HANDOFF.md
```

### 我负责的部分

* 安全事件分类体系；
* 传感器数据格式；
* 模型输入输出接口；
* 数据采集与标注规范；
* 数据回放和合成数据工具；
* 规则基线；
* MotionNet、AudioGate、ContextRouter、VisionGate；
* Teacher模型、蒸馏、INT8量化；
* PC端推理参考实现；
* ESP32-S3模型导出；
* 模型准确率、延迟、RAM、Flash评估；
* 模型卡、阈值和版本管理。

### Codex负责的部分

* IMU、麦克风、摄像头、GNSS和SIM7670G驱动；
* 音频和传感器环形缓冲；
* 数据记录和时间同步；
* 本地文件和离线队列；
* MQTT或HTTP通信；
* 模型运行时适配层；
* 固件调用模型的接口；
* ESP-DL、ESP-SR或TFLite Micro集成；
* 模型OTA；
* 串口命令和硬件测试；
* PC模拟端的事件接收和展示。

---

## 三、我会怎样交付代码

不是每次给你一段代码粘贴，而是生成一个**可直接覆盖到EGOLINK仓库根目录的版本化ZIP包**：

```text
EGOLINK_SAFETY_COMPANION_M0_V0_1.zip
EGOLINK_SAFETY_COMPANION_M1_V0_2.zip
EGOLINK_SAFETY_COMPANION_MODEL_V0_3.zip
```

每个包包含：

```text
MODEL_HANDOFF.md          本次交付说明
CHANGELOG.md              修改内容
INTEGRATION_TASKS.md      Codex需要完成的集成任务
shared/contracts/         稳定接口
model_lab/                训练和评估代码
model_artifacts/          模型和配置
quality_tests/            契约和集成测试
```

你解压到仓库根目录后提交一次Git：

```powershell
git add .
git commit -m "model: add safety companion model kit v0.1"
```

然后将 `INTEGRATION_TASKS.md` 交给Codex执行。

---

## 四、Codex不能随意改模型代码

Codex集成时应遵循：

```text
可修改：
firmware/**
pc_simulator/**
quality_tests/firmware/**

原则上不可修改：
model_lab/**
model_artifacts/**
shared/contracts/**
```

发现接口不适配时，Codex应在：

```text
docs/modeling/INTEGRATION_ISSUES.md
```

中记录问题，而不是自行修改模型输入输出协议。

这样可以避免Codex为了“把代码跑通”，无意中改变模型语义、特征顺序、量化参数或阈值。

---

## 五、双方通过稳定接口协同

例如端侧统一向模型提供：

```json
{
  "timestamp_ms": 1781952000000,
  "mode": "personal_safety",
  "motion": {
    "accel_window": [],
    "gyro_window": [],
    "stationary_seconds": 18
  },
  "audio": {
    "event_scores": {
      "speech": 0.14,
      "distress": 0.81,
      "impact": 0.72
    }
  },
  "location": {
    "speed_mps": 0.0,
    "accuracy_m": 7.5,
    "outside_safe_zone": false
  },
  "network": {
    "registered": true,
    "signal_level": 3
  },
  "device": {
    "battery_percent": 63,
    "base_online": true
  }
}
```

模型只返回结构化结果：

```json
{
  "model_version": "safety-router-0.1.0",
  "risk_type": "possible_accident",
  "risk_score": 0.91,
  "confidence": 0.84,
  "recommended_action": "ask_user_and_send_summary",
  "evidence_request": [
    "audio_5s",
    "single_image"
  ],
  "reason_codes": [
    "impact_detected",
    "post_impact_stationary",
    "distress_audio"
  ]
}
```

固件不需要知道模型内部是规则、决策树还是神经网络，只需要执行统一接口。

---

## 六、开发迭代流程

### M0：契约和规则基线

我交付：

* 数据Schema；
* 事件定义；
* ContextRouter规则基线；
* PC端模拟数据生成器；
* 事件回放程序；
* 模型接口测试；
* Codex集成任务书。

Codex集成：

* 把现有Mock GNSS、Mock Wake、SOS等数据转成统一输入；
* 接收统一模型输出；
* 模拟执行询问、上报和采集动作。

### M1：真实数据采集

我交付：

* 数据记录格式；
* 目录组织方式；
* 标注工具；
* 采样频率和窗口定义；
* 数据质量检查程序。

Codex实现：

* IMU、声音、GNSS、4G、按键等数据记录；
* 统一时间戳；
* 事件前后窗口保存；
* 导出数据包。

### M2：首个模型

建议首个模型不是视觉模型，而是：

```text
MotionNet
+
ContextRouter
```

MotionNet识别：

```text
正常活动
静止
剧烈撞击
跌倒候选
撞击后静止
设备未佩戴
```

ContextRouter综合：

```text
MotionNet输出
GNSS速度和位置
声音事件概率
网络状态
电量
Ego Base在线状态
历史事件
```

输出是否：

```text
忽略
本地提醒
询问用户
上传摘要
上传证据
紧急升级
```

### M3：AudioGate

加入：

* VAD；
* 呼救和异常声音检测；
* 录音质量判断；
* 事件触发前后短音频截取。

### M4：VisionGate

摄像头只在事件或请求触发时拍摄，端侧判断：

* 是否过暗；
* 是否模糊；
* 是否被遮挡；
* 是否有人；
* 是否值得上传。

复杂视觉理解仍由Ego Base完成。

### M5：量化与设备部署

我提供：

* INT8模型；
* C数组或ESP-DL模型文件；
* 输入归一化参数；
* 阈值文件；
* PC参考输出；
* 固件一致性测试向量。

Codex将模型接入ESP32-S3，并确保相同测试输入在PC和设备端得到允许误差范围内的输出。

---

## 七、每轮交付后的反馈方式

Codex完成集成后，你将以下内容打包上传给我：

```text
shared/contracts/
model_lab/
quality_tests/model_contract/
firmware中模型适配相关文件
本轮测试日志
真实采集数据的manifest
```

不必每次上传整个仓库。

我会据此：

1. 检查接口是否一致；
2. 修订模型或数据代码；
3. 生成下一个覆盖包；
4. 给出新的Codex集成任务；
5. 保持模型版本和固件版本对应。

版本关系例如：

```text
Firmware P0.4
Safety Contract 1.0
MotionNet 0.2.1
ContextRouter 0.3.0
AudioGate 0.1.0
```

---

## 八、给Codex的固定集成提示词

每次解压我的模型包后，可以把下面内容交给Codex：

```text
请读取：
1. docs/modeling/MODEL_HANDOFF.md
2. docs/modeling/INTEGRATION_TASKS.md
3. shared/contracts/
4. quality_tests/model_contract/

本轮只负责将安全陪伴模型接口集成到Ego Link工程。

规则：
- 不修改model_lab和model_artifacts；
- 不改变shared/contracts中的字段名称、类型、单位和顺序；
- 固件通过adapter适配现有数据结构；
- 所有模型调用必须支持Mock实现和真实实现切换；
- 必须运行模型契约测试；
- 缺少硬件时只能标记为未进行硬件验证；
- 不得将编译成功写成模型效果验证通过；
- 完成后更新docs/modeling/INTEGRATION_REPORT.md。
```

## 当前最合理的第一份交付

第一份不应直接交付一个未经数据验证的神经网络，而应是：

> **Safety Companion M0：事件体系、数据契约、规则基线、模拟器、回放程序、质量测试和Codex集成任务。**

这一步跑通以后，Codex负责让设备开始稳定采集真实数据，我再基于真实数据开发MotionNet和ContextRouter。这样模型不会脱离硬件和场景凭空设计。

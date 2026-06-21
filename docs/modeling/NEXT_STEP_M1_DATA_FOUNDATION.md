# Safety Companion 下一步：M1 数据基础与采集闭环

> 执行前置：M0-INT-001 至 M0-INT-004 已完成，或至少 M0 契约自检通过且当前仓库集成问题已经记录。  
> 本阶段目标不是训练神经网络，而是建立能够产生可信训练数据的真实工程闭环。

---

## 1. 先做什么

当前立即执行顺序：

```text
A. 完成 M0 与现有 Ego Link P0 的集成
B. 固定模型调用边界和端到端模拟闭环
C. 建立 M1 数据采集、记录、导出、校验和回放能力
D. 采集首批正常负样本和安全受控模拟样本
E. 数据质量达标后，开发第一个真实 MotionNet
```

如果 M0 尚未由 Codex 集成，下一步仍是按 `docs/modeling/INTEGRATION_TASKS.md` 完成 M0-INT-001—004。不要同时启动 M1 和大规模固件重构。

---

## 2. M1 核心目标

M1 必须回答：

- 实际使用哪一颗 IMU、麦克风和摄像头；
- 每种数据怎样采集、同步、缓存和导出；
- 一次完整 session 怎样组织；
- 事件前后的数据窗口能否稳定保存；
- 用户确认如何成为可靠标签；
- 隐私和授权怎样记录；
- PC 能否校验并重放同一 session；
- 数据质量是否足以进入 MotionNet 训练。

---

## 3. 建议任务拆分

### M1-001：硬件与传感器清单

创建：

```text
docs/modeling/HARDWARE_SENSOR_MATRIX.md
```

记录：

- 微雪 ESP32-S3 + SIM7670G 开发板真实型号、引脚和接口；
- 当前可用摄像头、麦克风、IMU、按键、电源和存储；
- 每个设备的驱动状态、采样能力、时间戳来源和功耗模式；
- 缺失传感器与候选替代；
- 哪些能力当前仍用 Mock。

此任务只记录事实，不假设未验证硬件已经可用。

### M1-002：会话与数据记录器

在固件中建立独立 `safety_recorder` 或等价组件：

- 会话开始、停止和唯一 `session_id`；
- 单调时间和 Unix 时间；
- `seq` 连续编号；
- 传感器帧写入；
- 事件、用户反馈和设备日志写入；
- 固件、契约、传感器配置和模型版本写入 manifest；
- 掉电或异常中断后能识别未正常关闭的 session。

先允许 Mock 数据进入记录器，真实驱动随后替换。

### M1-003：IMU 环形缓冲与事件窗口

目标：

- 初始采样 50 Hz；
- 保存事件前 3 秒、后 7 秒；
- 统计实际采样率、抖动、缺帧和溢出；
- 通过 CLI 人工触发 `mark impact`、`mark fall_candidate`、`mark normal`；
- 导出时间对齐的 IMU 窗口。

没有真实 IMU 时，可先完成驱动接口、Mock 生成器、缓冲和测试，但必须在报告中标记未进行真实采样验证。

### M1-004：PC 数据导入、校验与回放

PC 端新增：

```text
导入 session
→ 校验 manifest 与哈希
→ 检查时间戳、缺帧、采样率和窗口完整性
→ 生成质量报告
→ 按原时间或加速方式回放
→ 调用现有 RuleRouter
```

建议入口：

```powershell
python -m model_lab.safety_companion.datasets.inspect_session <session_dir>
python -m model_lab.safety_companion.datasets.replay_session <session_dir>
```

实际路径可按仓库结构调整，但不得复制契约或规则实现。

### M1-005：标注与用户反馈

建立最小 CLI 或本地页面，至少支持：

```text
safe
needs_help
false_alarm
cancelled
no_response
```

标注必须关联 `session_id`、`event_id`、时间范围、标注者、标注来源、授权状态和备注。

### M1-006：安全场景采集协议

创建：

```text
docs/modeling/SAFETY_DATA_COLLECTION_PROTOCOL.md
```

第一批场景：

负样本：

- 正常步行、跑步、上下楼；
- 坐下、躺下、快速起身；
- 放下设备、拿起设备、背包晃动；
- 乘车或骑行中的正常振动；
- 设备放在桌面、口袋和背包；
- 短时弱网、室内 GNSS 漂移和低电量。

受控模拟：

- 软垫环境下成人安全模拟跌倒动作；
- 设备单独跌落或撞击后静止；
- 手动 SOS；
- 事件后“安全、需要帮助、取消、无响应”的不同反馈。

禁止真实伤害、危险驾驶、真实摔车和未经授权的儿童/老人采集。

---

## 4. M1 验收门槛

进入 MotionNet 训练前，至少满足：

- 时间戳无倒退；
- `seq` 可检查且异常有记录；
- 实际采样率、抖动和缺帧率可统计；
- 事件前后窗口完整率可统计；
- 每条记录可追溯设备、固件、契约和配置版本；
- 用户反馈能准确关联事件；
- 隐私与授权字段完整；
- 原始文件与 manifest 哈希一致；
- PC 能导入、校验和回放；
- 自动测试不依赖外网，不真实拨号，不持续录音或录像；
- 已采集一批正常负样本，并完成至少少量受控模拟样本。

在这些条件达到前，不进入模型效果比较。

---

## 5. M1 之后的第一个模型任务

M1 达标后，开发：

```text
MotionNet v0.1
+
RuleRouter / ContextRouter v0.1
```

MotionNet v0.1 的研究目标：

- 建立统计/阈值基线；
- 建立小型 1D-CNN 基线；
- 按人员或 session 划分数据；
- 比较事件级召回率、误报率和混淆场景；
- 进行 INT8 量化；
- 输出 PC 参考模型和 ESP32-S3 测试向量；
- 暂不自动替代规则基线，而以双轨方式记录两者结果。

AudioGate 和 VisionGate 在 MotionNet 链路稳定后再进入，避免同时引入多种传感器、隐私和标注不确定性。

---

## 6. 给 Codex 的下一阶段提示词

> 仅在 M0 集成完成后使用。

```text
请先读取：
1. EGO_LINK_P0_CONTEXT.md
2. docs/modeling/SAFETY_COMPANION_MODEL_CONTEXT.md
3. docs/modeling/DATA_COLLECTION_SPEC.md
4. docs/modeling/NEXT_STEP_M1_DATA_FOUNDATION.md
5. shared/contracts/**
6. docs/modeling/INTEGRATION_REPORT.md
7. docs/modeling/INTEGRATION_ISSUES.md

当前目标是 Safety Companion M1 数据基础，不训练神经网络，也不接入正式 Ego Base。

请先只执行 M1-001：检查当前仓库和实际开发板资料，创建 docs/modeling/HARDWARE_SENSOR_MATRIX.md，记录真实可用的 IMU、麦克风、摄像头、GNSS、4G、按键、存储和电源能力，以及各能力当前是真实驱动还是 Mock。

规则：
- 不假设未验证硬件已经可用；
- 不修改 shared/contracts/**、model_lab/** 和 model_artifacts/**；
- 不实现后续 M1-002—006；
- 不访问云端 API；
- 不真实拨号；
- 完成后列出 M1-002 所需的最小接口和阻塞项。
```

完成 M1-001 并人工确认传感器矩阵后，再让 Codex 执行 M1-002。不要一次性完成整个 M1。

---

## 7. 模型侧下一次交付所需输入

当 M1-003—005 完成并采集到首批 session 后，向模型开发侧提供：

```text
1. HARDWARE_SENSOR_MATRIX.md
2. 实际采样配置
3. 3—5 个完整正常 session
4. 2—3 个受控模拟事件 session
5. manifest 和质量报告
6. 对应用户反馈/人工标注
7. 固件记录器与 PC 导入器相关代码
8. 已知缺帧、漂移、传感器安装方向和佩戴方式
```

收到这些输入后，开始开发 MotionNet 的数据清洗、窗口切分、统计基线和首个 1D-CNN。

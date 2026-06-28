# Ego Link P0 开发任务修正版：USB-Free 稳定性、LTE 数据链路与多源定位记忆

> 适用阶段：当前已完成 USB-Free、VPS Message Hub、Web/HTTP 命令闭环、固件侧 SIM7670G GNSS 真实 fix 之后。
> 核心调整：不要把下一步理解为“先长时间稳定性，再 LTE”。应改为“可观测性补齐 → 短基线稳定 gate → LTE thin-slice → LTE 闭环 gate → 多源定位/个人位置记忆 MVP → 独立电源与外壳状态产品化 gate”。

---

## 0. 当前已完成主干

已完成：

1. USB-Free 运行原则成立；
2. VPS Message Hub 已作为公网消息中枢；
3. Web/HTTP 命令闭环已跑通；
4. 固件侧 SIM7670G GNSS 已获得真实 fix；
5. 设备—VPS—Web 的最小演示主链路已经成立。

未完成 / 未验证：

1. SIM7670G LTE 数据链路；
2. 长期稳定与断网重连；
3. 独立电源续航；
4. 电池电量精度；
5. 最终外壳、佩戴/安装状态下的 GNSS 接收表现；
6. 多源定位融合与个人位置记忆的数据闭环。

---

## 1. 总体判断

Codex 建议“先推进较长时间 USB-Free 稳定性/重连 gate，再进入 SIM7670G LTE data transport 轨道”，方向基本正确，但需要修正：

**不要做一个只验证当前传输链路的长 gate。**

原因：如果当前 USB-Free 运行仍依赖 Wi-Fi 或开发期网络，那么长时间稳定性只能验证应用层、VPS 和 Web，不足以验证真实产品中的蜂窝网络、PDP 激活、弱网、重连、功耗和 SIM7670G 模块状态机。

更合理的策略是：

```text
观测能力先补齐
    ↓
短基线稳定 gate：验证固件任务调度、VPS、Web、命令 ACK、GNSS 任务不会互相卡死
    ↓
尽快进入 LTE thin-slice：只做最小 LTE 上行，不追求完整产品体验
    ↓
LTE 闭环 gate：用 SIM7670G LTE 完成 telemetry 上行、command 拉取、ACK 回传
    ↓
多源定位与个人位置记忆：把 GNSS、Cell、Wi-Fi、IMU、电源、运动状态都变成历史数据资产
    ↓
独立电源 + 外壳/安装状态 + 长稳 gate
```

---

## 2. 修正后的阶段路线

### R2.1：可观测性补齐 Gate

目标：在进入任何长时间测试前，先保证“失败可解释”。

必须新增统一 telemetry / health / location_observation 数据结构，使 Web 和 VPS 能解释：

1. 设备是否在线；
2. 通过什么 transport 在线；
3. GNSS 是否开启、是否 fix、尝试耗时、失败原因；
4. SIM7670G 蜂窝网络注册状态、信号质量、小区指纹；
5. 命令是否下发、是否 ACK、RTT 多少；
6. 设备是否重启、为何重启；
7. 电池电压、电量估算、是否充电；
8. 当前定位状态是 Fine / Coarse / Predicted / Unknown。

验收：

```text
即使 GNSS 失败、网络断开、命令超时，Web Dashboard 也必须能显示原因，而不是只显示“离线”或“无坐标”。
```

---

### R2.2：USB-Free 基线稳定 Gate

目标：验证当前主链路在不接 USB 的情况下稳定运行。

范围：

1. 不引入 LTE data transport；
2. 不做复杂 UI；
3. 不新增 AI 模型；
4. 只验证当前 transport 下的任务调度、消息可靠性、GNSS 任务、命令闭环、重连行为。

建议 gate 内容：

1. 设备独立供电运行；
2. 周期性上报 telemetry；
3. 周期性上报 location_observation；
4. Web 定时下发 ping / set_report_interval 命令；
5. 模拟 VPS 重启或短时不可达；
6. 设备应自动恢复上报；
7. 所有断线、重连、命令超时都有事件记录。

验收：

```text
设备全程不连接 USB 数据线；
VPS 可看到连续 seq；
Web 命令可被 ACK；
GNSS fix/no_fix 状态均可上报；
网络中断后可恢复；
恢复后不会重复执行旧命令；
数据库中可导出完整 test_run 记录。
```

注意：这一 gate 只作为“基线稳定性”，不能替代 LTE 产品链路验证。

---

### R2.3：SIM7670G LTE Data Transport Thin-Slice

目标：尽快证明设备可以通过 SIM7670G LTE 直接访问 VPS。

原则：

1. LTE 是产品主链路，不能长期放在后面；
2. 先做最小上行，不要一上来做完整重连和命令系统；
3. 保持协议 envelope 不变，只替换 transport；
4. 当前 Web/HTTP 命令闭环已成立，因此 P0 优先使用 HTTP POST + HTTP polling，MQTT 暂缓。

推荐优先级：

```text
优先：LTE HTTP POST telemetry 到 VPS
其次：LTE HTTP GET /commands 拉取命令
再次：LTE HTTP POST /acks 回传 ACK
最后：MQTT 长连接或 TCP 长连接
```

LTE thin-slice 最小链路：

```text
ESP32-S3
  → AT 控制 SIM7670G
  → SIM 注册 LTE 网络
  → 激活 PDP context
  → 获取 IP
  → HTTP POST /api/device/telemetry
  → VPS 返回 200 OK
  → Web 显示 transport = lte
```

验收：

```text
关闭 Wi-Fi；
不连接 USB 数据；
设备通过 SIM7670G LTE 向 VPS 成功上报一条 telemetry；
VPS 记录 transport.type = lte；
Web Dashboard 可看到 LTE 上报时间、运营商/小区/信号质量。
```

---

### R2.4：LTE 命令闭环 Gate

目标：把当前 Web/HTTP 命令闭环迁移到 SIM7670G LTE transport 上。

链路：

```text
Web 下发命令
  → VPS command queue
  → 设备通过 LTE HTTP polling 拉取命令
  → 固件执行命令
  → 设备通过 LTE POST ack
  → Web 显示成功 / 失败 / 超时
```

验收：

```text
关闭 Wi-Fi；
设备不连接 USB 数据；
Web 可下发 ping；
Web 可下发 set_report_interval；
设备可通过 LTE 拉取并 ACK；
命令不会重复执行；
超时命令有明确状态；
弱网或断网恢复后命令状态一致。
```

---

### R2.5：多源定位观测与个人位置记忆 MVP

目标：把定位从“GNSS 坐标”升级为“多源位置置信度”。

新增消息类型：

```json
{
  "type": "location_observation",
  "device_id": "ego-link-p0-001",
  "seq": 10086,
  "timestamp": 1760000000,
  "transport": {
    "type": "lte",
    "rtt_ms": 850,
    "last_error": null
  },
  "observations": {
    "gnss": {
      "enabled": true,
      "fix": true,
      "lat": 22.5431,
      "lon": 114.0579,
      "hdop": 0.9,
      "satellites": 12,
      "attempt_ms": 18000,
      "result": "fix"
    },
    "cell": {
      "rat": "LTE",
      "mcc": "460",
      "mnc": "01",
      "tac": "0x230A",
      "cell_id": "175499523",
      "rsrp": -67,
      "rsrq": -21,
      "rssi": -67,
      "sinr": 19
    },
    "wifi": {
      "scan_enabled": false,
      "aps": []
    },
    "imu": {
      "motion": "stationary",
      "confidence": 0.93
    },
    "power": {
      "battery_mv": 3920,
      "soc_pct": 78,
      "charging": false
    }
  },
  "location_belief": {
    "state": "fine",
    "lat": 22.5431,
    "lon": 114.0579,
    "radius_m": 15,
    "confidence": 0.91,
    "source": ["gnss"],
    "reason": "gnss_fix_hdop_good"
  }
}
```

四种定位状态：

```text
Fine       GNSS 高置信定位
Coarse     Cell / Wi-Fi / 记忆粗定位
Predicted  基于历史位置、运动状态、常见路线预测
Unknown    信息不足，不输出假坐标
```

个人位置记忆最小版：

1. `location_observations`：保存所有原始定位观测；
2. `cell_fingerprints`：保存 GNSS 成功时对应的小区指纹；
3. `gnss_attempts`：保存 GNSS 成功/失败位置、尝试耗时、环境标签；
4. `known_places`：人工或半自动标记家、学校、办公室、常见测试点；
5. `gnss_bad_zones`：记录 GNSS 长期失败但 cell/wifi 稳定的区域；
6. `route_segments`：后续从连续轨迹中生成常见路线。

P0 阶段融合规则：

```text
如果 GNSS fix 且 HDOP 合格：
    location_belief = Fine
    用当前 GNSS 位置反向标注 cell/wifi 指纹

如果 GNSS no_fix，但 cell 指纹命中 known_place：
    location_belief = Coarse
    radius_m 使用该地点历史半径

如果设备静止，且 cell/wifi 指纹稳定：
    保持 last_known，confidence 缓慢下降

如果设备移动，且 cell/wifi 发生明显变化：
    confidence 快速下降
    触发下一次 GNSS 短脉冲

如果处于 gnss_bad_zone：
    缩短 GNSS 尝试时间或降低 GNSS 触发频率
```

验收：

```text
Web 不再只显示 GPS 坐标；
Web 显示 Fine / Coarse / Predicted / Unknown；
Web 显示 radius_m、confidence、source、reason；
VPS 能查询某次 GNSS fix 对应的 cell 指纹；
VPS 能查询 GNSS no_fix 的失败记录；
同一位置多次测试后，系统可识别 known_place 或 gnss_bad_zone。
```

---

### R3.0：LTE 长稳与重连 Gate

目标：验证产品实际主链路，即 SIM7670G LTE + VPS + Web + 独立电源。

必须覆盖：

1. LTE 注册失败；
2. PDP 激活失败；
3. DNS 失败；
4. HTTP 请求失败；
5. VPS 短时不可达；
6. 命令拉取超时；
7. ACK 丢失；
8. GNSS fix 与 LTE 传输同时进行；
9. 设备重启后的命令一致性；
10. 弱信号场景下的退避策略。

验收：

```text
设备通过 LTE 独立运行；
断网后自动重连；
重连后 seq 连续或缺口可解释；
命令不重复执行；
失败事件有 reason_code；
Web 可导出 test_run 报告；
所有关键数据进入 VPS 数据库。
```

---

### R3.1：独立电源与电池精度 Gate

目标：把设备从“能跑”推进到“能估算续航”。

新增字段：

```json
{
  "power": {
    "battery_mv": 3920,
    "soc_pct": 78,
    "charging": false,
    "source": "battery",
    "load_state": "lte_tx_gnss_on",
    "estimate_quality": "rough"
  }
}
```

测试模式：

1. idle：只心跳；
2. lte_only：LTE 周期上报；
3. gnss_pulse：GNSS 短脉冲；
4. tracking：LTE + GNSS 高频；
5. field_test：真实外场。

验收：

```text
Web 可显示电池电压曲线；
Web 可按 load_state 区分功耗阶段；
系统能粗略估算剩余电量；
低电量时自动降低 GNSS 和上报频率；
紧急模式可覆盖省电策略。
```

---

### R3.2：外壳 / 安装状态 GNSS Gate

目标：验证最终产品结构对 GNSS 的影响。

必须比较：

1. 裸板状态；
2. 临时外壳状态；
3. 最终外壳状态；
4. 天线朝上 / 朝侧 / 贴身 / 放包内；
5. 阳台 / 室外开阔地 / 街区 / 车内。

指标：

1. 首次 fix 时间；
2. fix 成功率；
3. HDOP；
4. 卫星数；
5. GNSS attempt_ms；
6. 功耗阶段；
7. 是否命中 gnss_bad_zone。

验收：

```text
Web 支持创建 test_run；
每个 test_run 记录设备姿态和外壳状态；
可对比不同安装状态下的 GNSS 成功率；
能发现外壳/天线方向导致的接收退化。
```

---

## 3. 任务清单

### ENG-003：更新开发路线与 Gate 定义

目标：把本文档中的 R2.1–R3.2 写入项目文档。

改动范围：

1. `docs/current/STATUS.md`
2. `docs/current/PROJECT_SNAPSHOT.md`
3. `docs/current/ROADMAP_EGOLINK_P0.md`
4. `docs/tasks/TASK_TREE.md`
5. 新增或更新 `docs/development/FIELD_TEST.md`
6. 新增或更新 `docs/development/LOCATION_ENGINE.md`
7. 新增或更新 `docs/development/LTE_TRANSPORT.md`

验收：

```text
文档明确当前已完成主干；
文档明确下一阶段不是单纯 GNSS，而是 LTE + stability + location memory；
每个 gate 都有可验证 DoD。
```

---

### OBS-001：统一 Telemetry / Health / Event Envelope

目标：让所有后续稳定性测试可解释。

新增字段：

1. `seq`
2. `boot_id`
3. `uptime_s`
4. `fw_version`
5. `transport.type`
6. `transport.rtt_ms`
7. `transport.last_error`
8. `runtime.free_heap`
9. `runtime.last_reset_reason`
10. `runtime.watchdog_count`
11. `command.last_cmd_id`
12. `command.last_ack_status`
13. `power.battery_mv`
14. `power.soc_pct`
15. `gnss.fix / hdop / satellites / attempt_ms / result`
16. `cell.rat / operator / mcc / mnc / tac / cell_id / rsrp / rsrq / rssi / sinr`

验收：

```text
VPS 数据库保存 telemetry；
Web Dashboard 可显示设备健康状态；
导出的 test_run 可用于分析断线、重启、GNSS 失败、命令超时。
```

---

### STAB-001：USB-Free 基线稳定 Gate

目标：不接 USB，验证当前 transport 下主链路稳定。

依赖：OBS-001。

验收见 R2.2。

---

### LTE-001：SIM7670G LTE 注册与小区状态采集

目标：先证明 LTE 网络状态可观测。

内容：

1. SIM 状态；
2. 运营商；
3. RAT；
4. 注册状态；
5. APN 配置；
6. PDP 状态；
7. 当前小区指纹；
8. 信号质量。

验收：

```text
Web 能看到 LTE 注册状态和小区指纹；
VPS 保存 cell observation；
即使未建立数据链路，也能解释失败阶段。
```

---

### LTE-002：LTE HTTP 上行 Thin-Slice

目标：设备通过 SIM7670G LTE 向 VPS 发送最小 telemetry。

验收见 R2.3。

---

### LTE-003：LTE 命令拉取与 ACK

目标：迁移 Web/HTTP 命令闭环到 LTE。

验收见 R2.4。

---

### LOC-002：Location Observation 协议落地

目标：从 GNSS 坐标上报升级为多源定位观测上报。

内容：

1. `gnss`；
2. `cell`；
3. `wifi`；
4. `imu`；
5. `power`；
6. `location_belief`。

验收见 R2.5。

---

### LOC-003：VPS 位置记忆数据表

目标：建立数据驱动定位的历史资产。

建议表：

1. `location_observations`
2. `gnss_attempts`
3. `cell_fingerprints`
4. `wifi_fingerprints`
5. `known_places`
6. `gnss_bad_zones`
7. `route_segments`
8. `location_beliefs`
9. `test_runs`

验收：

```text
每一次定位尝试都有原始记录；
每一次 GNSS fix 可反向标注 cell 指纹；
每一次 GNSS no_fix 可进入失败统计；
Web 能按 test_run 查询历史。
```

---

### LOC-004：规则版 Location Belief Engine

目标：先用规则实现 Fine / Coarse / Predicted / Unknown，不引入复杂模型。

验收：

```text
GNSS fix 时输出 Fine；
Cell 命中 known_place 时输出 Coarse；
静止且指纹稳定时输出 Predicted 或保持 last_known；
信息不足时输出 Unknown；
所有 belief 都必须包含 radius_m、confidence、source、reason。
```

---

### PWR-001：电池与独立电源观测

目标：把电源状态纳入稳定性和定位策略。

验收见 R3.1。

---

### ENC-001：外壳与安装状态 GNSS 对比

目标：验证结构因素对 GNSS 的影响。

验收见 R3.2。

---

### REL-001：LTE 长稳与重连 Supervisor

目标：产品主链路可靠性。

内容：

1. transport 状态机；
2. 指数退避；
3. 失败 reason_code；
4. command 幂等；
5. telemetry 缓存；
6. 重启恢复；
7. watchdog；
8. test_run 报告。

验收见 R3.0。

---

## 4. 推荐开发顺序

```text
ENG-003  更新路线与 gate 文档
    ↓
OBS-001  统一 telemetry / health / event envelope
    ↓
LOC-002  location_observation 协议落地
    ↓
STAB-001 USB-Free 基线稳定 gate
    ↓
LTE-001  LTE 注册与小区状态采集
    ↓
LTE-002  LTE HTTP 上行 thin-slice
    ↓
LTE-003  LTE 命令拉取与 ACK
    ↓
LOC-003  VPS 位置记忆数据表
    ↓
LOC-004  规则版 location_belief engine
    ↓
REL-001  LTE 长稳与重连 supervisor
    ↓
PWR-001  电池与独立电源观测
    ↓
ENC-001  外壳与安装状态 GNSS 对比
```

---

## 5. 对 Codex 的直接执行提示词

```text
当前 Ego Link P0 已完成 USB-Free、VPS Message Hub、Web/HTTP 命令闭环、固件侧 SIM7670G GNSS 真实 fix。下一阶段不要继续把任务理解为单点 GNSS 功能，也不要做一个只验证当前开发网络的长时间稳定性 gate。

请按以下修正版推进：

1. 先执行 ENG-003：更新项目文档，明确 R2.1–R3.2 路线：
   - R2.1 可观测性补齐 Gate
   - R2.2 USB-Free 基线稳定 Gate
   - R2.3 SIM7670G LTE Data Transport Thin-Slice
   - R2.4 LTE 命令闭环 Gate
   - R2.5 多源定位观测与个人位置记忆 MVP
   - R3.0 LTE 长稳与重连 Gate
   - R3.1 独立电源与电池精度 Gate
   - R3.2 外壳/安装状态 GNSS Gate

2. 再执行 OBS-001：统一 telemetry / health / event envelope。没有可观测性之前，不进入长时间稳定性测试。

3. 再执行 LOC-002：实现 location_observation 协议。定位不再只上报 GNSS 坐标，而是上报 gnss、cell、wifi、imu、power、location_belief。

4. 再执行 STAB-001：USB-Free 基线稳定 Gate。该 gate 只验证当前主链路、固件任务调度、VPS、Web、命令 ACK、GNSS 任务不会互相卡死，不替代 LTE 产品链路验证。

5. 随后立即进入 LTE-001 / LTE-002 / LTE-003：
   - LTE-001：SIM7670G LTE 注册与小区状态采集；
   - LTE-002：LTE HTTP 上行 telemetry thin-slice；
   - LTE-003：LTE HTTP polling 命令拉取与 ACK。

6. LTE P0 优先使用 HTTP POST + HTTP polling，因为当前 Web/HTTP 命令闭环已经成立。MQTT 或 TCP 长连接暂缓，避免过早引入额外复杂度。

7. 多源定位与个人位置记忆在 VPS 侧先做数据闭环和规则引擎，不引入复杂 AI 模型：
   - location_observations
   - gnss_attempts
   - cell_fingerprints
   - known_places
   - gnss_bad_zones
   - location_beliefs

8. USB 只用于烧录和临时调试，所有 gate 的验收证据必须来自 VPS 数据库与 Web Dashboard。

约束：
- 不要大规模重构已打通的主链路。
- 不要破坏现有 Web/HTTP 命令闭环。
- 协议字段新增必须兼容旧 telemetry。
- 所有新增状态必须能在 Web Dashboard 或 test_run 导出中看到。
- 所有失败都必须有 reason_code。
```

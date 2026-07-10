# Model card: Safety Rule Router 0.1.0

## 类型

透明确定性规则基线，不是训练得到的神经网络。

## 用途

- 定义 Ego Link 随身安全陪伴 P0 的输入输出行为；
- 支持 PC Simulator 和固件接口集成；
- 为未来学习型 ContextRouter 提供比较基线；
- 验证隐私过滤和确定性 SOS 规则。

## 输入

`shared/contracts/model_input.schema.json`。

## 输出

`shared/contracts/model_output.schema.json`。

## 支持场景

手动 SOS、撞击后静止、跌倒候选、呼救声音、地理围栏、异常停留、通信失联、低电量、模糊事件补充采集。

## 已验证

- 12 个合成场景的确定性契约测试；
- Python 参考实现输出可重复；
- 隐私模式过滤原始音频和图像请求。

## 未验证

- 真实 IMU、音频、图像、GNSS 和 4G 数据；
- 儿童、老人和户外真实场景效果；
- 误报率、漏报率和泛化能力；
- ESP32-S3 延迟、RAM、Flash 和能耗；
- 实际紧急处置效果。

## 安全限制

本基线不能用于医疗诊断。物理 SOS、隐私选择、拨号和不可逆动作必须由独立确定性安全机制控制。

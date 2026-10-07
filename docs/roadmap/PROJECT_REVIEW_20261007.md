---
document_status: review_not_authority
reviewed_at: 2026-10-07
source_commit: 129518fc5
comparison_commit: 2b023472a
scope: local_repository_and_synthetic_offline_review
serves_demo: D2/D5
serves_gates: P0-LOC/P0-CALL/P0-SOS/G8-SECURITY-PRIVACY
---

# 项目目标、现状与后续任务评审 — 2026-10-07

**结论：项目已增加长时采集报告和可运行的离线 AI 原型，但真实数据驱动的模型改进闭环尚未验收；三个销售产品 Gate 仍为 NOT_RUN。下一轮应先修复新增链路的证据真实性和数据接口，再交付 D2 真值基线，同时推进原生通话硬件可行性与最小私有 Base。**

本次以本地 `a0/first-real-field-session@129518fc5` 为边界，相对上轮管理提交有 16 个新增提交；本地最新提交日期为 2026-09-23。评审日不等于部署日，不推断本地记录以外是否还有开发、远程提交或现场运行。本轮为本地源码检查、任务命名报告复核、既有测试与新增合成复现，未进行设备/VPS 取证、烧录或部署；只新增评审材料，不改产品决策、源码或已有验收状态。

## 1. 目标回顾

[North Star](../product/NORTH_STAR.md) 在 9/23 新增 accepted [ADR-0017](../architecture/adr/ADR-0017-ai-native-ego-state-flywheel.md)：用真实日常数据、跨模态伪标签、影子评估和版本化模型更新，逐步实现 AI 原生随身主动状态估计。这个方向应继续，90%+ 自动标注、端侧延迟/内存和 OTA 时间属于待实测目标。

同时，[Master](../product/EGO_MASTER_CONTEXT.md)、[Charter](../product/PRODUCT_CHARTER.md)、[P0_SCOPE](../product/P0_SCOPE.md) 的首发承诺没有被取消：

- 面向儿童、老人并兼容成年人；无屏模块化 EgoCore，可靠定位是最直接的用户入口。
- 可靠定位/诚实状态、原生蜂窝双向通话、实体 SOS 三项都要通过；AI 不得延误或否决确定性安全动作。
- 强隐私、本地优先；最小 Ego Base 是用户控制的数据终点，VPS 仍只是工程过渡，日记脚本不等于私有 Base。
- 48h 守护续航、可靠性、RF、防水声学、安全隐私、NPI 和合规仍需代表性整机证据。

D5 可以与 D2 并行准备；模型精度改善和产品可靠性必须分别用适用真值评估。扩展日记、更多模型阶段或测试数量不能替代 D2 和三项产品 Gate。

## 2. 已取得的进展与实际成熟度

| 工作面 | 相比 9/22 的新增进展 | 本次可支持的结论 / 尚缺内容 |
|---|---|---|
| 单板与外场 | [STATUS](../current/STATUS.md) 报告 Boot211 在 9/23 连续 7h、8,724 条记录、285 次 GNSS 3D fix、0 重启，带电量与规则状态输出 | 有价值的长时工程观察；原始索引、供电条件、完整镜像/配置和指标分母仍需绑定。不是参考精度、48h 或代表日验收 |
| 相机/网络/控制 | 新增相机恢复、原生拨号/挂断命令、Web 控制及地图修复 | 有源码进展；[P0-CONVERGENCE](../tasks/active/P0-CONVERGENCE-20260905.md) 仍缺同候选断网/重启、实际 Wi-Fi/LTE 切换与完整 loss/recovery 验收 |
| D2 / FIELD-020 | 既有参考点、导出与指标工具可复用，新增 7h 数据可作为场景线索 | [D2-001](../tasks/active/D2-001_LOCATION_ACCURACY_BASELINE.md) 首次真实参考点基线仍未勾选；[FIELD-020](../tasks/active/FIELD-020_L1_FIELD_DATASET.md) 仍为 NOT_RUN。HDOP、轨迹长度和 fix 数不等于位置误差 |
| AI-010 | JSONL/SQLite 采样、IMU 解码、滑窗、伪标签工具及测试 | 离线原型；身份隔离、许可/质量、采样率及跨模态消费者存在缺口，见下一节 |
| AI-020 | NumPy 1D-CNN 前向、分类头训练、INT8 权重/C header 导出 | 有效的算法脚手架；训练仅更新 fc1/fc2，卷积特征保持初始化值；权重大小不等于 tensor arena、整机 SRAM 或 INT8 实际推理验收 |
| AI-030 / AI-040 | PC 仲裁、样本挖掘、微调、回归脚本、校验和二进制打包 | 仿真与打包原型；没有完成端侧影子执行、独立模型分区、签名更新与断电回滚；当前精度/安全门禁不能支持模型晋级 |
| AI-050 / Web | 模板式活动分段、Markdown/JSON 日记、一键流水线、日记页面 | 可演示输出链；日记页面为固定内容，未读取生成结果；不是已部署本地 Base、私有 LLM 或真实全天安全证明 |
| 原生通话 / 产品 | Web→命令队列→AT 调度路径新增；STATUS 报告当前模组不支持语音 | 调度 ACK 不等于拨通/双向声音；需将准确后缀、固件、AT 原始结果及官方能力依据纳入 CALL-030。当前板不能验收完整声学；最终模组选择仍未冻结 |

`P0-LOC`、`P0-CALL`、`P0-SOS` 保持 `NOT_RUN`。不把未索引的实测报告抹成“从未做过”，也不把它们直接提升为已验收能力。

## 3. 优先处理的实现问题

以下是实际源码核对及合成复现，均未修复。复现脚本见 [PROJECT_REVIEW_20261007_PROBES.py](../verification/PROJECT_REVIEW_20261007_PROBES.py)，当次结果见 [PROBES.json](../verification/PROJECT_REVIEW_20261007_PROBES.json)。它们只使用合成输入，没有真实设备、联系人或私人轨迹。

| 优先级 | 发现及证据 | 影响与必须补上的验收 |
|---|---|---|
| 立即 | [采样器](../../scripts/harvest_self_supervised_dataset.py) 在同一列表按 monotonic time 排序，只保留首个 device/boot/session。两个设备、两个 boot 的合成输入产生混合窗口，却只标为 device-A/boot1 | 按 device + session + boot 隔离，检查 sequence、重复、重启、时间缺口和质量；跨身份输入不得成为一个训练窗 |
| 立即 | 采样器输出 `cross_modal_context` 和 `gnss_fix`，而 [影子评估](../../scripts/run_shadow_evaluation.py) 读取 `context`，仲裁读取 `gnss_fix_type`。复现有 fix、8m/s 的窗口，消费者实际收到 `{}` | 冻结版本化窗口/上下文/枚举合同，真实 harvester→shadow→retrain→diary 串联测试；不能只测各模块各自的手造 fixture |
| 立即 | 合成输入声明 `training_allowed=false`、mock，仍被采样且 manifest 写 `privacy_gate=PASS`，输出丢失这些声明；入口未接入现有许可审核。50Hz 的 100 点跨度为 1.98s，后续仍按 5s 解释 | 许可、mock、来源与采样率必须传递并受验证；去坐标不等于隐私/训练授权通过；20/50Hz 显式重采样或拒绝不兼容输入 |
| 立即 | [一键流水线](../../scripts/run_ai_flywheel_one_click.py) 对空 JSONL 生成 46 个合成场景窗口后返回 SUCCESS，`data_source` 仍指向空输入；仅控制台有回退提示 | 正式路径空数据/缺失输入应失败关闭；合成模式须显式开启，并贯穿 manifest、模型、指标、日记/UI，不能成为真实外场完成证据 |
| 立即 | [日记统计](../../pc_simulator/ego_base_diary_synthesizer.py) 对零观测返回 `is_day_completely_safe=true`；相隔 1h 的两个 5s 步行片段合成 3,605s 连续活动。[日记页面](../../server/web/ai_diary.html) 固定写“全天安全无忧”“OTA 就绪”和 100% 指标 | Unknown/覆盖不足/示例/历史状态显式展示；按事件时间、真实窗口覆盖及间隙计时；去除“未检测到事件=安全”的推断，页面接真实版本化摘要或明确标为演示 |
| 接入前阻断 | [仲裁器](../../pc_simulator/safety_kernel_arbitrator.py) 对静止 `[0,0,9.81]` 计算跨轴总体方差，得到 `running`；即使 SOS 为真，仍调用模型，模型异常使整个调用无安全结果 | 当前是 PC 仿真缺陷，不宣称设备 SOS 已受影响。必须复用/对齐既有规则语义，验证姿态与重力；模型异常、超时和无效输入不能影响安全结果 |
| 模型晋级前阻断 | [微调](../../scripts/finetune_flywheel_model.py) 把 gold 样本加入训练后仍在同批样本上报告提升；[初训](../../scripts/train_edge_tinyml_model.py) 按窗口随机切分，采样窗 50% 重叠。始终预测 stationary 的模型仍通过 15/15 “安全回归” | 按人/Session/日期和佩戴方式隔离训练、验证、测试，禁止重叠窗泄漏；区分规则保护与模型召回。加入独立留出集、每类 F1/召回、混淆矩阵、未知拒绝及量化前后比较 |
| 固件接入前阻断 | 已检查的受版本控制固件入口/组件/分区表未出现新 TinyML 或 `model_weights` 接入；打包只有 SHA-256 校验和，没有签名验签、下载激活及回滚闭环 | C header/二进制是候选工件；先测端侧数值一致性、延迟/SRAM/功耗，后做独立更新协议、认证、断电恢复及回滚，不可直接承诺 OTA 可用 |

此外，9/22 已记录的“全部来源报告丢失时健康帧超过 4,000 字节”仍在现有生产帧回归中作为已知边界；本轮源码差异未关闭它，继续由恢复任务承接。新增独立 ego DEVICE 帧的吞吐/存储预算也要进入实测配置。

## 4. 状态与决策冲突登记

这里记录冲突，不擅自选择一个新硬件事实或重写 accepted 决策：

1. **镜像冲突**：STATUS 报 Boot211，并说完整 hash 在 ACTIVE_BUILD；[ACTIVE_BUILD](../current/ACTIVE_BUILD.md)、[BOARD_MATRIX](../hardware/BOARD_MATRIX.md) 和看板输入仍停在 Boot188。缺 Boot211 的 source/config/app/ELF/部署身份与证据入口，不能确认 9/22 修复实际在哪个镜像生效。
2. **阶段定义冲突**：ADR-0017/架构的 Phase 3 包含端侧推理、模型分区/OTA，Phase 4 包含私有 Base；AI-030～050 实际拆成 PC 仿真、打包和模板日记。STATUS 的“五阶段完成”不能表示 accepted 架构已经闭环。建议保留五个已交付源码切片，单列尚未完成的端侧/Base/现场验收项。
3. **参数合同未统一**：North Star/ADR/架构/实现中的模型类别、30/32KB 预算、cycling 速度/持续时间/HDOP 阈值并不一致。分类原语与上层空间状态需明确映射；伪标签是弱监督假设，不是物理真值。由合同负责人明确目标及验收后再改实现。
4. **任务状态不一致**：AI-010 为 `active/ready` 且全勾选，AI-020～050 为 `completed/closed` 但留在 active 目录。现有生成器把这五项都算为 planned；[TASK_TREE](../tasks/TASK_TREE.md) 未纳入它们。只重建看板不会解决状态语义。
5. **已有报告和展示不是同一结果**：AI-030 指定的当前报告为 46 窗、15 个 gold 样本；AI-040 完成文字写 24 个 gold 样本；AI-050 指定的日记文件为 6 段、1 个安全事件，页面固定写 7 段/全天正常。可能属于不同运行或被覆盖产物，缺不可变 run/model/dataset manifest，不能合并为一次成功记录。

证据 5 仅读取任务显式命名的 `reports/models/shadow_v1/shadow_evaluation_report.md` 和 `reports/models/ego_base/daily_life_diary_20260923.md`；未扫描私有报告目录。上述冲突应在下一次管理对齐中保留原版本和迁移关系，不能通过改日期或把复现实验算成产品 PASS 消除。

## 5. 后续任务建议

以下是建议派单顺序和验收出口，不是已经派发的 WIP 或新的操作授权。延续 Gemini 的恢复/D2/FIELD 分工，避免另建一套同类采集工具。

| 顺序 / 建议负责人 | 任务与范围 | 可审查的完成出口 |
|---|---|---|
| 1 / Codex 集成，Gemini 提供实测索引 | 当前事实与 AI 输出真实性：解决 Boot211/188、阶段映射、AI task 状态；修复固定安全/隐私/OTA 宣称及合成回退标签 | 一份不可变候选/部署 manifest；任务状态和看板一致；空/缺失/合成数据不再显示真实成功或全天安全；保留旧证据 |
| 2 / Codex 软件，算法负责人复核 | AI-010→050 数据接口与质量：复用现有 Session/时间/许可合同，隔离 device/boot、定义采样率、状态映射、覆盖率与来源 | 上节混身份、上下文丢失、20/50Hz、拒绝训练、mock/过期、空输入、间隙计时案例全部按预期处理；一条真实格式的合成端到端链通过 |
| 并行 A / Gemini | 完成 P0-CONVERGENCE 当前候选恢复、loss、真实路由切换验收；准备 D2-001，随后 FIELD-020 | 固定镜像上 outage/reboot/同文件ID恢复与 Wi-Fi/LTE 切换证据；D2 复用既有三参考点/30 次尝试工具，输出 fix 分母、TTFF、median/P90 误差；FIELD 另列场景覆盖和缺测 |
| 并行 B / 原生通话与硬件负责人（待指定） | CALL-030 的准确模组/固件/运营商/音频可行性；停止用无音频路径开发板证明双向通话 | 具名能力与原始响应、授权信令试验与声音试验分开；明确可用/不可用和后继候选证据；输入 HW-021/022→CALL-031，再恢复完整 SOS |
| 并行 C / Base 负责人（待指定） | 启动 BASE-010 最小私有终点，AI-050 仅作报告消费者 | 合成/授权 Session 接收→私有耐久保存→查询/回放→保留/导出/删除；中继与 Base durable ACK 分开，访问隔离和加密状态记真；不等待本地大模型 |
| 3 / 算法负责人，Codex 复核门禁 | 完成真实数据学习基线，修复仲裁异常隔离；重建独立模型评估 | 显式授权、可追溯的多 Session 数据；按场景隔离的留出集；规则与模型同口径指标、退化案例、量化误差和覆盖率。重训样本上的 100% 不作为晋级结果 |
| 4 / 固件与硬件负责人 | 在离线门禁通过后做 TinyML 端侧 shadow，随后模型分区与安全更新；产品功耗/RF等按各自依赖推进 | 不改变安全输出；端侧数值/时延/SRAM/能耗实测、签名拒绝、损坏/断电/回滚；48h 与 Call/SOS 产品保证仍单独验收 |

每条工作线最多一个实施包；步骤 1/2 可先合成验证，不能因外场等待而空转。D2 资料准备和 Base/CALL 可行性不等待高级模型；FIELD 正式验收仍保留既有恢复/网络依赖。当前不建议扩更多日记页面、增加传感器或宣称更高准确率。

下一次项目评审应看三份交付：**可追溯候选与运行记录、第一份真实 D2 误差基线、一个有独立留出评估的可信数据→候选模型闭环**。原生通话可行性和 Base 私有端点分别汇报，不由 AI 进度掩盖。

## 6. 本轮验证与变更记录

- 变更：本评审、合成复现脚本及其 JSON 结果；无生产源码、合同、固件、硬件配置或当前 authority 修改。
- 合成复现已完成；上述反例反映当前行为，脚本正常退出不意味着产品测试通过。
- 新增 AI 链的六个既有测试模块复跑：31 项通过（2.634s）。合成复现脚本再次运行，JSON SHA-256 与归档结果一致。这说明现有测试未覆盖上节反例，不能只凭绿灯接受端到端链。
- 本机全量 `scripts/verify.ps1`：1,899 项，1,885 通过、8 失败、6 跳过，327.827s，退出码 1。日志：`tmp/project-review-20261007/verify-native.log`。其中 7 个失败是仓库内 TEMP 触发相对/绝对路径及 basename 断言差异；另一个是 native modem owner 恢复案例的 settled/local_sequence/persistence 断言。恢复系统临时目录后，8 项定向复测全部通过（18.475s，`failures-recheck.log`）；原生时序失败未再次重现，原因未定性。保留第一次结果，不将定向通过改写为一次完整全绿运行。
- 六个跳过项：3 个 Espressif clang/lld host 模式不可用，2 个显式构建 opt-in 未开启，1 个 lifecycle 仅交叉编译而无可执行 host target。既有 AI 测试日志为 `tmp/project-review-20261007/ai-focused.log`；反例输出为同目录 `review-probes.json`。
- `python scripts/context_lint.py` PASS；`git diff --check` PASS。评审未修生产代码，因此回归环境可移植性和偶发 native 恢复失败列为后续验收前复查项，不据此重新打开或关闭任何硬件 Gate。
- 环境说明：WindowsApps 的 `python` 别名不可执行；改用已安装 Python 3.14.6。沙箱默认临时目录拒绝写入，改为仓库内 `tmp/project-review-20261007/temp`；沙箱本机证书初始化停滞后终止该次运行，并在自动批准的本机执行范围重跑同一套测试。中间失败日志保留，不计为代码回归或通过。
- 本轮没有新硬件证据；Boot211 的实况和缺失索引、三 Gate、48h、原生音频、完整 Base/模型 OTA 仍按各自证据边界处理。

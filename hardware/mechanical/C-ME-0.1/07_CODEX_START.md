# Codex启动指令｜Ego Link C-ME-0.1

继续Ego Link C线结构工作。本包是HW-021下新增的机械设计输入，不替换历史受控资料。用户已安装Blender、FreeCAD、KiCad，请直接利用现有安装开始建模。

先读`03_EGOLINK_MEMORY_CURRENT.md`、`04_DECISION_LOG.md`和`01_CODEX_STRUCTURE_TASKBOOK.md`，再使用`02_CORE_MECHANICAL_CONCEPT.md`、`05_CUSTOM_SHELL_CONTRACT.md`与`params/core_parameters.json`。

当前A仍为单4G主板含摄像头外测；不要动A的硬件/固件和spool，不接入AMOLED，不重开CALL或两板通信。C产品方案研究ML307A（准确后缀待厂家资料）＋独立GNSS。厂家反馈GSLN接近停产按转述记录，不伪造正式PCN。

本轮直接执行：
1. 在仓库新增独立版本目录，记录commit与dirty状态；只读发现三软件的路径/版本，使用其内置脚本/CLI，不先装插件。
2. 校验参数，打开`cad/REF60_ENVELOPE_ONLY.step`与`REF66_ENVELOPE_ONLY.step`，核对单位和尺寸。附带的是实心外包络，不是能装电子件的壳体。
3. 用FreeCAD建立参数驱动源文件；可先运行附带宏，也可按相同参数用原生草图。缺真实机械图的部件用明确TBD/EST占位，不缩小器件来消除干涉。
4. 收拢目前已存在的器件图/STEP/测量，建立主板、ML307A、GNSS及三天线、电池Pack、相机/FPC/视场、扬声器声腔、麦克风、USB湿区、按键和必要显示占位；比较两档包络和两种内部堆叠。
5. 历史屏幕决定冲突保留为一个明确未决项；比较有屏/无屏所需空间，不把移出AMOLED开发板解释成删除产品屏。不因为这项等待停止其他建模。
6. 达到独立设计条件的区域继续做前盆/后盖、装拆路径、核心固定及一个初步承力载体。未定的密封材料、真实Pack最大尺寸、RF和声学区域不伪造通过。
7. 由FreeCAD几何派生Blender展示；现有KiCad PCB存在则导入核对，不存在则明确是机械板框/占位，不声称完成电气设计。

本轮至少回传：实际工具报告、可编辑FreeCAD文件、更新参数、两档比较和主推堆叠的前/后/侧/剖切截图、干涉与资料缺项、已完成/待验证区分、更新后的记忆及追加决策记录。不能只回报一份新文档或两张漂亮外观图。

允许在有明确标注的估算上继续原型建模；不允许把估算当供应商尺寸，不授权投板、下单、外发、量产声明或改变P0 Gate。

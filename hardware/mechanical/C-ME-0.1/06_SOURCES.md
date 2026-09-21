# 来源与证据边界
检索/核对日期：2026-09-09。以下用于说明设计输入依据，不表示完成认证或供应链验证。

## 用户及项目来源
- **P01 当前对话**：用户厂家反馈ML307A-GSLN接近停产、拟ML307A外挂GNSS、电池加大、核心功能与可自定义外壳；同意结构方案并已装三软件。供应状态属于转述，未取得PCN。
- **P02 EGO_ENGINEERING_REGISTER_v0.5.xlsx**，上传2026-08-11，配置页与EVT-A0记录：旧有屏ED160F320MSO、56×45×17.2mm候选、准确料号/EVT采购边界。已读文件检索段，本包不覆盖台账。
- **P03 EGOLINK_WATERPROOF_CORE_A0_A1_DESIGN_v0.1.md**，2026-08-11：无屏胶囊、68×50×18与52×39×14.5mm起点、Core/Cradle/Skin、密封和USB/SIM边界。其VoLTE首发和旧尺寸不能直接覆盖本轮。
- **P04 EGO_LINK_C_LINE_ENGINEERING_PACK_20260909.zip / HW021_C1_DESIGN_REVIEW.md**：本地已读取；较早本轮审查保留产品屏并提出SIM7670G工程迁移比较。之后用户厂家信息改变C的模组研究主线，此包已显式记录。
- **P05 EGO_LINK_SINGLE_BOARD_CAMERA_SCOPE_20260909.md**：当前A单板与摄像头范围；A不等待本轮结构。
- **P06 三张用户参考图**：本包references目录原图副本；只支持造型/布局意向，不能推导尺寸、量产材料或IPX7已通过。

## 本轮外部官方资料
**S01 FreeCAD官方能力页/手册**：支持参数化建模与Python；STEP交换方向。网页搜索摘要可得，部分正文抓取受站点限制，不据此指定用户当前版本。
- https://www.freecad.org/features.php?lang=en
- https://wiki.freecad.org/Manual:Creating_parametric_objects
- https://wiki.freecad.org/Import_Export

**S02 Blender官方命令行文档**：后台和Python脚本参数。latest随版本变化，实际按本机--help；本次检索摘要可得。
- https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html

**S03 Blender官方单位文档**：场景单位与长度显示；脚本明确转换坐标，不依赖显示设置完成缩放。本次检索摘要可得。
- https://docs.blender.org/manual/en/latest/scene_layout/scene/properties.html

**S04 KiCad 9官方CLI文档**：已读取，支持PCB STEP、DXF等导出与用户原点；不同安装版本按实际子命令帮助核对。
- https://docs.kicad.org/9.0/en/cli/cli.html

**S05 Blender官方glTF文档**：展示交换方向，不作为工程尺寸权威。
- https://docs.blender.org/manual/en/latest/addons/scene_gltf2.html

**S06 Gore声学防护膜**：已读取页面，声学、防液体/颗粒功能，具体膜和整机效果待选型/实测。
- https://www.gore.com/products/portable-electronics-acoustic-vents

**S07 Gore压力平衡膜**：已读取页面，压力管理及声学/密封相关影响；不是替整机做IP保证。
- https://www.gore.com/products/pressure-vents-portable-electronics

**S08 u-blox GNSS天线应用说明**：本次检索到官方PDF摘要，未逐页审阅；只用于提醒具体天线对地平面/安装有不同要求，不从该文填入本机尺寸/净空。
- https://content.u-blox.com/sites/default/files/products/documents/GNSS-Antennas_AppNote_%28UBX-15030289%29.pdf

**S09 CPSC关于儿童绳带/项链风险的安全提示**：官方检索摘要；用于识别缠绕风险，不当作中国准入标准或具体释放力阈值。
- https://www.cpsc.gov/safety-education/safety-guides/kids-and-babies/babies-can-strangle-strings-cords-and-necklaces

## 本轮工程建议
REF60/REF66、原型2mm壁厚、0.4mm单侧打印间隙、两种堆叠和电池询样容量范围均是本轮EST，不出自上述厂商受控图。实际部件尺寸仍为空；缺项在参数文件与报告中公开。

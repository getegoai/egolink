# 双包络尺寸白模

此处4个CAD文件已实际生成：
- REF60：长度Y=60mm、宽度X=44mm、厚度Z=22mm。
- REF66：长度Y=66mm、宽度X=46mm、厚度Z=24mm。

STEP为CAD实体，STL为数值单位mm的闭合三角网格。它们是实心外轮廓，只有外圆角；没有器件、薄壁、盖板、螺钉、声孔或密封槽。可用于确认尺寸/软件文件交换/空白手感样块，不能安装带电电子件。

模型原点是后侧基准面中心，Z=0到厚度T；X左右、Y沿长轴。两模型在各自文件中位于同一基准，不是同一个装配中的两个零件。

真实生成工具为当前运行环境的CadQuery/OpenCascade，不是用户电脑的FreeCAD。已对STEP重新导入并对STL作封闭拓扑/尺寸检查。完整结果见`reports/ENVELOPE_GEOMETRY_CHECK.json`。

FreeCAD可直接打开STEP；`scripts/make_envelopes.FCMacro`供Codex在用户FreeCAD内按相同参数重建并生成FCStd。编辑JSON后重新生成，宏当前并非完整原生草图约束的最终工程外壳。

Blender可用`build_preview_blender.py`导入两个STL生成新的比较场景；脚本按mm→m转换并检查包络，不渲染也不改动原文件。

**封闭网格（watertight mesh）是数字拓扑属性，不代表实际材料防水。**

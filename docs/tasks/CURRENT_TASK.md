# CURRENT_TASK：T014 项目清理与版本化迭代模式

## 任务目标

清理仓库中的生成物和临时运行文件，初始化 Git 版本管理，并确定 Ego Link 的轻量迭代开发模式。

## 范围

- 删除可再生的构建产物、缓存、运行日志和 smoke-test 输出；
- 增加 `.gitignore`；
- 初始化 Git 仓库；
- 判断 Git Flow / GitLab Flow / GitHub Flow 中最适合当前阶段的分支模式；
- 写入版本化迭代和智能体开发模式约定；
- 保持第一阶段为单智能体，不引入 LangGraph、AutoGen、CrewAI 等复杂框架。

## 不做

- 不实现新业务功能；
- 不引入远端 Git 托管；
- 不接入复杂多智能体编排框架；
- 不改变当前 P0 技术主线。

## 允许修改路径

- `.gitignore`
- `README.md`
- `docs/**`
- `scripts/**`
- `firmware/**/build/**`
- `firmware/**/managed_components/**`
- `firmware/**/captures/**`
- `pc_simulator/runtime/**`
- `**/__pycache__/**`

## 建议验证

- `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`
- `git status --short`
- 确认生成目录已被删除或被 `.gitignore` 忽略。

## 完成标准

- 仓库目录只保留源码、配置、文档和必要脚本；
- Git 仓库初始化完成；
- 明确采用 GitHub Flow；
- 智能体开发模式仍保持单智能体、单任务、可验证、可停止。

## 执行结果

- 已清理 ESP-IDF build、managed components、camera captures、runtime logs 和 Python cache 等可再生目录；
- 已新增 `.gitignore`，后续构建和运行生成物默认不进入版本管理；
- 已写入 `docs/DEVELOPMENT_WORKFLOW.md`，当前采用 GitHub Flow；
- 已确认第一阶段采用单智能体开发模式，不引入 LangGraph、AutoGen、CrewAI 等额外框架；
- 已新增 `scripts/start_mosquitto_lan.ps1`，用于启动本机用户态 LAN Mosquitto；
- 已运行 `scripts/verify.ps1`，11 个测试全部通过；
- 已通过 `mosquitto_sub` 收到开发板 MQTT status 心跳。

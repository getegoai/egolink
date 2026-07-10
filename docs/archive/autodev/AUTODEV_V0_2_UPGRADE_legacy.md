# AutoDev v0.2 升级说明

## 升级前

不要在 AutoDev 正在执行任务时覆盖脚本。先让当前任务结束，或在运行终端按 `Ctrl+C` 停止，然后检查：

```powershell
git status --short
```

确认当前任务产生的代码已经提交、回滚或由你妥善保存，再解压升级包。

## 安装

将 v0.2 overlay 压缩包解压到 EGOLINK 仓库根目录，允许覆盖同名文件。

然后执行：

```powershell
python -m py_compile scripts/autodev.py
python -m unittest discover -s autodev/tests -v
git add scripts/autodev.py scripts/run_autodev.ps1 scripts/watch_autodev.ps1 autodev/tests/test_supervisor.py autodev/VERSION docs/AUTODEV_GUIDE.md docs/AUTODEV_MONITORING.md docs/AUTODEV_V0_2_UPGRADE.md
git commit -m "chore: upgrade AutoDev live monitoring to v0.2"
```

## 使用

在 VS Code 中拆分两个终端。

终端 1：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_autodev.ps1 -MaxTasks 3
```

终端 2：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/watch_autodev.ps1
```

或：

```powershell
python scripts/autodev.py watch --interval 2 --events 12
```

监控状态同时写入：

```text
autodev/runtime/live_status.json
autodev/runtime/LIVE_STATUS.md
```

## 兼容旧运行日志

`watch` 在找不到 v0.2 的 `live_status.json` 时，会读取最近的 v0.1 `metadata.json` 和 `events.jsonl` 进行推断式显示。

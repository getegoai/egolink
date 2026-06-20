# Ego Link AutoDev 实时监控

AutoDev v0.2 将“模型进程仍在运行”和“有可观察开发活动”区分开来。

监控范围包括：

- 当前任务、标题和尝试次数；
- 当前阶段：Codex 实现、外部验证、提交、完成或阻塞；
- 总运行时间；
- 距离最近一次可观察事件的空闲时间；
- Codex JSONL 事件数、命令数、文件事件数和工具调用数；
- 当前工作区实际发生变化的文件；
- Git diff 摘要；
- 最近的命令、工具调用、文件变化和智能体消息；
- backlog 已完成、阻塞和可执行任务数量。

监控不会显示模型的私有思维链。它显示的是可验证的外部动作和工程证据。

## 1. 推荐的双终端运行方式

在 VS Code 中打开两个终端，建议左右拆分。

终端 1：执行自动开发。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_autodev.ps1 -MaxTasks 3
```

终端 2：打开实时监控。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/watch_autodev.ps1
```

也可以直接运行：

```powershell
python scripts/autodev.py watch
```

监控默认每 2 秒刷新一次，显示最近 12 条可观察事件。

```powershell
python scripts/autodev.py watch --interval 1 --events 20
```

快速渲染一次快照并退出：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/watch_autodev.ps1 -Once -NoClear
```

按 `Ctrl+C` 只会关闭监控，不会停止另一个终端中的 AutoDev。

## 2. LIVE_STATUS 文件

AutoDev 运行时持续更新：

```text
autodev/runtime/live_status.json
autodev/runtime/LIVE_STATUS.md
```

可以直接在 VS Code 中打开 `LIVE_STATUS.md`。它会显示当前任务、阶段、运行时间、空闲时间、最后事件、变化文件和 diff 摘要。

这两个文件位于已经被 Git 忽略的 `autodev/runtime/` 中，不会进入项目提交。

## 3. 终端心跳的含义

新版心跳示例：

```text
[ACTIVE ] elapsed 03:30 | idle 00:12 | events 28 | changed 1 | last: FILES: added docs/...
```

字段含义：

- `elapsed`：本次 Codex 尝试已运行多久；
- `idle`：多久没有收到新的外部事件；
- `events`：收到的 JSONL 事件数量；
- `changed`：当前未提交变化文件数量；
- `last`：最近一个可观察动作。

当超过 120 秒没有可观察事件时，标签会变为：

```text
[IDLE   ]
```

`IDLE` 不等于失败。它可能表示模型正在推理，也可能表示工具或进程停滞。此时应结合监控中的文件变化和最近事件判断。

可调整警告阈值：

```powershell
python scripts/autodev.py run --max-tasks 3 --idle-warning 300
```

## 4. 直接查看原始证据

查找最近一次运行目录：

```powershell
$run = Get-ChildItem .\autodev\runs -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
$run.FullName
```

持续查看原始事件流：

```powershell
Get-Content "$($run.FullName)\events.jsonl" -Wait
```

查看当前真实文件变化：

```powershell
git status --short
git diff --stat
git diff
```

查看结构化最终结果：

```powershell
Get-Content "$($run.FullName)\result.json"
```

## 5. 对旧版正在运行任务的支持

如果某个任务由 AutoDev v0.1 启动，尚未生成 `live_status.json`，v0.2 的 `watch` 会读取最近的 `autodev/runs/*/metadata.json` 和 `events.jsonl`，提供推断式监控。

此时界面会标记：

```text
State  : inferred
Source : inferred from the latest v0.1 run log
```

任务阶段和进程是否仍然存活只能近似判断；下一次用 v0.2 启动后会得到完整实时状态。

## 6. 如何判断是否真的在推进

可靠性从高到低依次为：

1. 出现新的文件变化，且 `git diff` 内容持续完善；
2. 正在执行或完成新的构建、测试、检查命令；
3. 工具调用持续产生新的结果；
4. 只有模型消息或 reasoning start/completed；
5. 只有进程心跳，没有事件、文件变化或测试活动。

当最后一种状态持续较久时，可以先查看 `events.jsonl` 和 `git diff`，再决定是否中止。默认 AutoDev 仍保留每次任务的总超时保护。

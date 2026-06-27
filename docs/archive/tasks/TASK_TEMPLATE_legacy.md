# CURRENT TASK

## Task ID

TXXX

## Goal

用一句话说明本轮唯一目标。

## Why now

说明它与当前 P0 闭环的关系，不超过 3 行。

## Must read

- `EGO_LINK_P0_CONTEXT.md`
- `STATUS.md`
- 只列出与本任务直接相关的文件

## Allowed paths

- `path/to/file_or_directory`

## Must not do

- 不实现与 Goal 无关的功能
- 不新增生产依赖
- 不修改 Allowed paths 之外的文件
- 不接入真实 4G、GNSS、摄像头或语音唤醒，除非本任务明确要求

## Requirements

1. 可检查的要求 1
2. 可检查的要求 2
3. 可检查的要求 3

## Done when

- [ ] 完成条件 1
- [ ] 完成条件 2
- [ ] 完成条件 3

## Verification commands

```powershell
# 每条命令必须自动退出
```

## Stop conditions

- 同一验证失败并修复 2 次后停止
- 缺少必要环境或硬件时停止
- 需要越界修改时停止
- 规格冲突时停止

## Required final report

- 修改文件
- 验证命令与结果
- Done when 检查结果
- 阻塞和未完成项

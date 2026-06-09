---
name: complex-coding-harness
description: 用于复杂、长周期、高风险、多阶段、多仓库、前后端联动或容易受上下文压缩影响的 coding 任务。触发后要求先建立可恢复执行计划，确认环境和验证策略，等待用户明确批准方案，再按阶段实施，并记录 review、验证、changelog、commit 和可恢复任务状态。
---

# Complex Coding Harness

此 skill 用于让复杂 coding 工作保持稳定、可恢复、可审计。

## 核心规则

- 先把任务分为 `direct`、`managed` 或 `needs-clarification`。
- `direct` 任务按普通最小实现和聚焦验证处理。
- `needs-clarification` 任务只提出阻塞问题，然后停止。
- `managed` 任务在规划或编辑前必须读取 `references/workflow.md`。
- 只有任务属于 `managed`，且用户允许落盘任务状态时，才创建 `.harness/tasks/`。
- 如果 `.harness/tasks/` 已存在，每轮开始先读取 `.harness/active-task.json`、`.harness/environment.md`（如存在）和当前任务的 `execution-plan.md`。
- 实施前必须完成方案、环境、工具、验证、文档和 `Readiness Gate`。
- managed 任务实施前必须确认 `Git Context`：主分支、harness 工作分支、同步来源和热修复插入策略。
- `Readiness Gate` 只表示方案可提交用户审批。只有 `Plan Approval` 记录用户明确批准后，才能进入实现。
- 实施阶段必须按 `Implementation Plan` 逐阶段执行；每阶段都要 review、验证、修复缺陷、更新任务记录和 changelog。
- 只有用户批准的方案或用户明确要求允许提交时，才能提交代码；提交 hash 必须记录到 `Commit Log`。

## 文件

使用内置模板作为起点：

- `templates/environment.md` 用于 `.harness/environment.md`。
- `templates/execution-plan.md` 用于任务级执行计划。
- `templates/pending-decisions.md` 只在阻塞决策较多、需要异步填写或需要审计记录时使用。

保持 `SKILL.md` 简短。详细流程写在 `references/workflow.md`。

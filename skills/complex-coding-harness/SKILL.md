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
- 如果用户提示本 skill 已更新，继续任务前必须重新读取最新 `SKILL.md`、`references/workflow.md` 和当前 `.harness` 任务状态。
- 不使用 tag、版本号或自动迁移机制处理 skill 更新；旧任务状态只在自然更新时按新规则补齐，若差异影响已批准方案、Git、验证、提交或阶段边界，必须先确认。
- 实施前必须完成方案、环境、工具、验证、文档和 `Readiness Gate`。
- managed 任务实施前必须确认 `Git Context`：主分支、harness 工作分支、同步来源和热修复插入策略。
- `Readiness Gate` 只表示方案可提交用户审批。只有 `Plan Approval` 记录用户明确批准后，才能进入实现。
- 实施阶段必须按 `Implementation Plan` 逐阶段执行；每阶段都要 review、验证、修复缺陷、更新任务记录和 changelog。
- managed 任务在用户批准实施后默认进入 `run-to-completion`；除非用户明确要求只做当前阶段、命中停止条件或所有已批准阶段完成，否则不能在阶段边界、阶段提交后或恢复点完成后停止。
- 每个阶段退出后必须执行 `Stage Transition Gate`；仍有 pending stage 且没有停止条件时，下一动作必须是继续下一阶段，而不是回复“下一步进入某阶段”后停止。
- 阶段边界允许发送进度更新，但不能发送最终回复；最终回复只能在停止条件命中或最终交付门禁通过后发送。
- 如果 `process-manager` skill 存在，所有服务、后台或需要挂起运行的长期进程都必须使用它管理；manager 离线时停止并请求用户启动或授权 bootstrap，不手写 shell 后台启动命令。
- managed 长任务每阶段开始、验证前和上下文恢复后，都必须重新检查 `execution-plan.md` 的长期进程门禁，不能中途忘记 `process-manager` 规则。
- 只有用户批准的方案或用户明确要求允许提交时，才能提交代码；提交 hash 必须记录到 `Commit Log`。
- managed 任务最终交付必须包含任务结论、验证结果、未覆盖范围、commit 信息和关键证据；前端或可视化任务应提供截图或替代证据。

## 文件

使用内置模板作为起点：

- `templates/environment.md` 用于 `.harness/environment.md`。
- `templates/execution-plan.md` 用于任务级执行计划。
- `templates/pending-decisions.md` 只在阻塞决策较多、需要异步填写或需要审计记录时使用。

保持 `SKILL.md` 简短。详细流程写在 `references/workflow.md`。

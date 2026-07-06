---
name: complex-coding-executor
description: 执行已经由 complex-coding-planner 制定并获用户批准的复杂 coding 任务计划。用于用户要求开始实现、继续执行、恢复任务、执行剩余阶段或按已批准 execution-plan.md 落地方案时。本 skill 不制定新方案，只消费已批准计划，并强制执行阶段门禁、验证、review、Git/process 规则、changelog、提交授权和最终交付。
---

# Complex Coding Executor

此 skill 只执行已经批准的 `.harness` managed 任务计划。

## 启动条件

- 每轮开始必须读取 `.harness/active-task.json`、`.harness/environment.md` 和当前任务的 `execution-plan.md`。
- 必须读取 `references/execution-workflow.md`，再开始任何编辑、验证、Git 写操作或长期进程操作。
- 如果没有当前任务、找不到 `execution-plan.md`、计划未批准、存在 open blocking 决策，必须停止并说明原因。
- 如果用户只是要求制定方案、补充规划、复查方案或等待审批，应使用 `complex-coding-planner`，不得用本 skill 直接实现。

## 核心规则

- `execution-plan.md` 是唯一主契约；`.harness/active-task.json` 只是恢复入口。
- 执行前运行或等价执行 `scripts/harness_exec_check.py --mode preflight`。
- 每个阶段必须执行 Stage Contract、Stage Entry Gate、代码修改、code review、验证、缺陷修复、记录更新和 Stage Exit Gate。
- 每个阶段退出后必须执行 Stage Transition Gate；仍有 pending stage 且无停止条件时，必须继续下一阶段，不能最终回复后停止。
- 用户批准实施不等于授权提交。只有 `Plan Approval` 明确授权阶段提交，或用户额外明确要求提交，才能 `git commit`。
- 同一仓库 Git 命令必须串行；禁止任何并发机制同时运行同仓库 Git。
- 如果 `process-manager` skill 存在，所有服务、后台或需要挂起运行的长期进程都必须用它管理；finite command 直接运行。
- 最终回复只能在所有已批准阶段完成且最终交付门禁通过后发送。

## 文件和脚本

- 执行工作流: `references/execution-workflow.md`
- 执行状态检查: `scripts/harness_exec_check.py`

## 禁止行为

- 不现场补写未批准计划后直接实现。
- 不跳过 review、验证、Stage Transition Gate 或 Resume Summary。
- 不把阶段完成、阶段提交完成或恢复点完成当作最终停止条件。
- 不自动 stash、reset、rebase、覆盖用户改动或删除未知文件。
- 不手写后台 shell 命令启动长期服务。

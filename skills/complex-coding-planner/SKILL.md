---
name: complex-coding-planner
description: 为复杂、长周期、高风险、多阶段、多仓库、前后端联动或容易受上下文压缩影响的 coding 任务制定可恢复实施方案。用于用户要求调研、规划、制定方案、复查方案、确认环境或准备 execution-plan.md 时；必须完成环境、Git、工具、验证、Plan Quality Gate、Plan Self-Review、Readiness Gate，并等待用户明确批准。不得直接实现代码，实施阶段交给 complex-coding-executor。
---

# Complex Coding Planner

此 skill 用于制定复杂 coding 工作的可恢复、可审计实施方案。

## 核心规则

- 先把任务分为 `direct`、`managed` 或 `needs-clarification`。
- `direct` 任务按普通最小实现和聚焦验证处理。
- `needs-clarification` 任务只提出阻塞问题，然后停止。
- `managed` 任务在规划前必须读取 `references/planning-workflow.md`。
- 只有任务属于 `managed`，且用户允许落盘任务状态时，才创建 `.harness/tasks/`。
- 如果 `.harness/tasks/` 已存在，每轮开始先读取 `.harness/active-task.json`、`.harness/environment.md`（如存在）和当前任务的 `execution-plan.md`。
- 如果用户提示本 skill 已更新，继续任务前必须重新读取最新 `SKILL.md`、`references/planning-workflow.md` 和当前 `.harness` 任务状态。
- 不使用 tag、版本号或自动迁移机制处理 skill 更新；旧任务状态只在自然更新时按新规则补齐，若差异影响已批准方案、Git、验证、提交或阶段边界，必须先确认。
- 实施前必须完成方案、环境、工具、验证、文档和 `Readiness Gate`。
- managed 任务实施前必须确认 `Git Context`：主分支、harness 工作分支、同步来源和热修复插入策略。
- managed 计划必须在靠前位置生成 `Execution Contract`，并写清 `Goal Condition`、`Planning Loop Protocol` 和 `Executor Work Loop`。
- 调研、浏览、搜索或读取多个关键来源后，必须把 findings 写入 `Context`、参考矩阵或 artifacts；重大决策前必须重读目标、约束、Options、Decision 和 reapproval triggers。
- managed 计划必须完成 `Research Gate`：把不确定项分为 `none`、`local-only`、`online-required` 或 `blocked-by-access`；涉及可能变化的框架、API、协议、工具、模型、依赖、外部服务或高风险事实时，优先查询官方或一手资料，并记录查询、来源、结论和影响。
- managed 计划必须完成 `Standards Discovery Gate`：识别语言、技术栈、框架、API 类型和架构风险，收集官方/一手或高质量规范来源，并形成 standards index 或等价计划章节。
- managed 计划必须完成 `Development Quality Gate`：基于 standards index 明确代码标准、静态质量、架构边界、设计模式取舍、低耦合高内聚和验证映射；不得把不适用的复杂模式强加给 direct 或低风险任务。
- 如果用户批准后需要改变批准范围、阶段边界、验证策略、风险等级、工具授权或提交策略，必须进入 `Plan Amendment Gate`，不得静默改计划后继续。
- 同一仓库 Git 命令必须串行执行，禁止任何并发机制同时运行同仓库 Git；遇到 index lock 必须先走精确路径、进程和文件稳定性检查，再只恢复该精确 lock。
- 方案提交用户审批前，必须完成 `Plan Self-Review`：复查缺陷、优化点、缺失项、风险和一致性；发现问题必须先修复计划，再进入 `Readiness Gate` 和 `Plan Approval`。
- 分段 patch 是落盘策略，不要求一次性生成全部细节；大内容首次写入前必须先有全局框架，再允许分模块递进式细化和逐段 `apply_patch`，最后重新读取完整文件做整体复查。
- `Readiness Gate` 只表示方案可提交用户审批。只有 `Plan Approval` 记录用户明确批准后，才能进入实现。
- `Readiness Gate` 通过后必须停止，等待用户明确批准方案；不得开始代码实现。
- 方案获批后的执行阶段交给 `complex-coding-executor`，由 executor 按阶段执行、review、验证、changelog、commit 和最终交付。
- 如果实施会涉及长期进程，计划必须写清 `Process Manager Gate`；实际启动、验证和清理由 `complex-coding-executor` 执行。
- 计划必须写清提交策略：实施批准不等于提交授权，只有用户明确授权提交时 executor 才能提交。
- 计划必须写清最终交付证据要求，例如验证结果、未覆盖范围、commit 信息、截图、日志或替代证据。

## 文件

使用内置模板作为起点：

- `templates/environment.md` 用于 `.harness/environment.md`。
- `templates/execution-plan.md` 用于任务级执行计划。
- `templates/pending-decisions.md` 只在阻塞决策较多、需要异步填写或需要审计记录时使用。

保持 `SKILL.md` 简短。详细规划流程写在 `references/planning-workflow.md`。

# Compact Task State

## 文件职责

- `execution-plan.md`：用户批准的意图、决策和阶段说明。
- `plan-contract.json`：Executor 需要精确引用的范围、DAG、阶段及最终验证、审查模式和请求权限。
- `.harness/active-task.json`：workspace 当前 managed task 的指针。
- `run-state.json`：批准、授权、当前阶段、最近验证、审查摘要和 blocker。

计划与 contract 在用户批准后通过 digest 绑定。实现细节在批准范围内调整时不修改它们；范围、公共接口、阶段依赖、必需验证、关键依赖、迁移、风险或授权变化时进入重新批准。

## 生命周期

没有 `run-state.json` 时任务处于 planning。Executor 创建状态后使用：

- `approved`
- `in_progress`
- `blocked`
- `awaiting_reapproval`
- `completed`

状态只描述当前恢复点，不记录每条命令或事件历史。Git、源码和实际验证输出仍是事实来源。

多阶段任务在全部 stage 完成后执行 `final_validation_ids` 指定的集成验证，再进入 final review。它复用 `run-state.json` 的 validations 摘要，不创建额外证据文件。

## 指针安全

active pointer 只能指向当前 workspace 的 `.harness/tasks/**`，并校验 pointer、contract 和 state 的 task ID。

切换不同任务必须显式使用 `--switch` 并给出当前 expected task ID。清理有效 pointer 可使用 `--expect-task-id` 防止误清；pointer 已损坏时，显式 `clear` 只删除该指针，不删除任何任务目录。

旧 heavy bundle 不由 lightweight runtime 执行。contract 出现旧字段或缺少 compact 核心字段时停止并提示重新规划；不在新脚本中保留旧 schema 分支。

## 失败处理

- plan checker 失败：修复计划或 contract 后再请求批准。
- pointer 无效：先确认实际任务目录，不静默覆盖。
- 批准后 digest 漂移：停止实施并重新批准。
- run-state 与 Git 或源码冲突：调查真实工作树，必要时 block；不要通过增加 JSON 文件掩盖冲突。

---
name: complex-coding-executor
description: 执行由 complex-coding-planner 生成并获用户批准的复杂 coding task bundle。用于开始实现、继续或恢复 managed 任务、执行剩余 stages；只消费不可变 execution-plan.md、plan-contract.json 和 attestation，独占 run-state.json 与 ledger.jsonl，并强制执行阶段验证、review、Git/process、amendment、提交授权和最终交付门禁。
---

# Complex Coding Executor

此 skill 只执行已经批准的 managed task bundle，是运行状态和执行证据的唯一 writer。

## 启动条件

- 每轮开始读取 pointer-only `.harness/active-task.json`、task contract、attestation、run-state/ledger 和稳定环境。
- 开始任何编辑、验证、Git 写操作或长期进程操作前读取 `references/execution-workflow.md`。
- 缺少当前契约必需文件、批准证明或权限，存在 blocker/reapproval，或 replay 无法确定状态时 fail closed。
- 如果用户只是要求制定方案、补充规划、复查方案或等待审批，应使用 `complex-coding-planner`，不得用本 skill 直接实现。
- 如果设置了 `HARNESS_DISABLED=1`，只做 direct/advisory 行为，不消费历史 active task。

## 核心规则

- `plan-contract.json` 是可执行约束，`execution-plan.md` 解释批准意图；不得从 prose 推断 stage、授权或状态。
- 执行前运行 `scripts/harness_exec_check.py --mode preflight`，验证 planner approval checker、attestation 和 state replay。
- 恢复或转移时运行 `--mode status|transition`；仅用 `--mode reconcile` 修复可由合法 ledger 唯一推导的 snapshot drift。
- 每个 stage 按 contract 的依赖、范围、REQ/AC/NFR、VAL 和风险执行 entry、修改、review、验证、修复与 exit。
- 每个阶段必须执行 `Development Quality Check`：读取计划中的 standards index、`Standards Discovery Gate` 和 `Development Quality Gate`，按本阶段范围复核代码标准、静态质量、架构边界、模式取舍、耦合/内聚和验证证据。
- contract 的 dependency mode 非 `none` 时读取 `references/dependency-execution.md`：preflight 按 critical-runtime/runtime/dev-build 的 30/60/90 天上限校验批准证据和 stage 映射，涉及 manifest/lock 的阶段用生态原生命令生成 task-local runtime receipt；身份、版本策略、路径、hard gate 或 advisory 漂移不得静默放行。
- 每个开始、attempt、验证、review、完成、阻塞、amendment 和 commit 都先追加合法 ledger event，再原子更新 run-state。
- stage 完成后立即执行 transition；仍有 remaining stage 且无 stop/reapproval 时连续推进。
- 失败动作必须记录 attempt、失败原因、影响和下一策略；不得静默重复同一失败动作。
- 新事实影响 scope、Stage DAG、必需验证、风险、依赖或授权时写 research drift/amendment，设置 reapproval 后停止。
- 用户批准实施不等于授权提交。只有 attestation 的 `authorizations.commit = true`，且用户批准摘要或后续消息明确要求提交，才能 `git commit`。
- 同一仓库 Git 命令必须串行；禁止任何并发机制同时运行同仓库 Git。
- 如果 `process-manager` skill 存在，所有服务、后台或需要挂起运行的长期进程都必须用统一 `pm_manager.py`/`pm_*` CLI 管理；记录 manager identity、config validation、processKey、ready、bounded logs 和 owner-empty cleanup，且不判断 OS/backend。finite command 直接运行。
- 最终回复只能在所有 stage、required VAL、review、授权和 final checker 闭环后发送。

## 文件和脚本

- 执行工作流: `references/execution-workflow.md`
- 依赖执行门禁: `references/dependency-execution.md`
- 故障排查: `references/troubleshooting.md`
- 契约定义: `../complex-coding-planner/references/task-contract.md`
- 执行状态检查: `scripts/harness_exec_check.py`
- 任务解析: `scripts/harness_task_resolver.py`
- 依赖执行检查: `scripts/harness_dependency_check.py`
- 计划证明: `scripts/harness_attest_plan.py`
- 进度 ledger: `scripts/harness_ledger_append.py`、`scripts/harness_ledger_summary.py`

## 禁止行为

- 不修改批准后的 plan、contract 或 approved artifacts。
- 不跳过 review、验证、Stage Transition Gate 或 Resume Summary。
- 不保留旧契约分支、active 状态镜像或 Markdown 状态解析。
- 不把阶段完成、阶段提交完成或恢复点完成当作最终停止条件。
- 不自动 stash、reset、rebase、覆盖用户改动或删除未知文件。
- 不手写后台 shell 命令启动长期服务。

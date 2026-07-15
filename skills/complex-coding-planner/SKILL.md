---
name: complex-coding-planner
description: 为复杂、长周期、高风险、多阶段、多仓库或恢复敏感的 coding 任务制定持久、可验证的实施方案。用于用户要求调研、规划、制定或复查方案、准备 task bundle 时；按风险选择 lite/standard/full，生成 execution-plan.md、plan-contract.json 和条件 artifacts，完成研究、规范、质量、自查与审批门禁后停止。不得实现代码，批准后的执行交给 complex-coding-executor。
---

# Complex Coding Planner

此 skill 只负责生成可审批的任务意图和机器契约，不负责实施或运行状态。

## 核心规则

- 先路由为 `direct`、`managed` 或 `blocked`；能自主消歧的问题不得过早询问用户。
- managed 任务必须读取 `references/planning-workflow.md`；生成或校验字段时读取 `references/task-contract.md`。
- 按影响面、不确定性、恢复跨度、可逆性、质量风险和授权选择 `lite`、`standard` 或 `full`；目标未稳定时先 `discovery-first`。
- 只为 managed 任务创建 `.harness/tasks/`。每轮先读取 pointer-only active-task、稳定环境和已有 task bundle。
- planner 独占 `execution-plan.md`、`plan-contract.json` 和 planning artifacts；批准后这些文件不可变，不写 current stage、progress、ledger 或 commit 状态。
- 涉及变化事实或高风险未知时执行在线 Research Gate，优先官方/一手资料；同时完成 Standards Discovery 与 Development Quality gates。
- 涉及依赖新增、升级、替换、技术选型或关键依赖保留时，必须读取 `references/dependency-selection.md` 并执行 Dependency Selection Gate；先证明必要性，再按项目适配、硬门槛和多信号证据选择，不以 stars、下载量或单一总分决定。
- 计划必须使用稳定 GOAL/REQ/AC/NFR/STG/VAL/ART ID，形成验收、阶段和验证闭环，并通过 `scripts/harness_plan_check.py --task-dir <task-dir> --mode approval`。
- 提交审批前完成 Plan Quality Gate、Plan Self-Review、必要的独立 critique 和 Readiness Gate；发现问题先修复再重跑。
- Readiness 通过后调用 `scripts/harness_active_task.py --mode activate` 写 active pointer；非终态或未知任务冲突必须 fail closed，只有用户明确选择任务后才可 `--mode switch`。随后总结授权请求并停止，不得创建 run-state/ledger、实现代码或提交。
- 用户批准后由 `complex-coding-executor` 生成 attestation、维护 run-state/ledger，并执行 review、验证和提交门禁。
- 批准后 scope、Stage DAG、必需验证、风险、依赖或授权改变时进入 Plan Amendment Gate。
- 同一仓库 Git 命令串行；长期进程必须在计划中声明 Process Manager Gate；实施批准不等于提交授权。

## 文件

按需使用：

- `templates/execution-plan.md`：不可变的人类审批意图。
- `templates/plan-contract.json`：机器可验证契约。
- `templates/active-task.json`：pointer-only active task。
- `scripts/harness_active_task.py`：active pointer 四态分类、原子激活与显式 compare-and-swap 切换。
- `templates/environment.md`：稳定 workspace 事实。
- `templates/pending-decisions.md`：仅在 blocking 决策需要落盘时使用。
- `templates/artifacts/dependency-selection.md`：依赖候选、证据 receipt、风险和回滚的详细记录；正式机器证据使用同名 JSON artifact。

保持本文件精炼；流程和字段细节只在对应 reference 中维护。

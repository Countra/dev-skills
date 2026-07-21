---
name: complex-coding-planner
description: 为复杂、长周期、高风险、多阶段、多仓库或恢复敏感的 coding 任务制定持久、可验证的实施方案。用于用户要求调研、规划、制定方案或准备 task bundle 时；按风险选择 lite/standard/full，生成 execution-plan.md、plan-contract.json 和条件 artifacts，完成研究、规范、生产者质量与正式 plan-review 审批门禁后停止。不得实现代码，正式审查交给 complex-coding-reviewer，批准后的执行交给 complex-coding-executor。
---

# Complex Coding Planner

此 skill 只负责生成可审批的任务意图和机器契约，不负责实施或运行状态。

## 核心规则

- 先按影响面、恢复需求、风险和不可逆性路由为 `direct`、`managed` 或 `blocked`；不得按预估步骤数或工具调用数把清晰的局部修改升级为 managed。能自主消歧的问题不得过早询问用户。
- managed 任务必须读取 `references/planning-workflow.md`；生成或校验字段时读取 `references/task-contract.md`。
- 按影响面、不确定性、恢复跨度、可逆性、质量风险和授权选择 `lite`、`standard` 或 `full`；目标未稳定时先 `discovery-first`。
- 只为 managed 任务创建 `.harness/tasks/`。每轮先读取 pointer-only active-task、稳定环境和已有 task bundle。
- planner 独占 `execution-plan.md`、`plan-contract.json` 和 planning artifacts；批准后这些文件不可变，不写 current stage、progress、ledger 或 commit 状态。
- Research Gate 以决策影响为先：本地事实足够时不联网；只有变化事实、关键依赖、平台行为、规范冲突或高风险未知才搜索，并在新证据不再改变决策时停止。Standards Discovery 优先项目配置、现有代码和官方规范，只保存适用结论与链接。
- 涉及依赖新增、升级、替换、技术选型或关键依赖保留时，必须读取 `references/dependency-selection.md` 并执行 Dependency Selection Gate；先证明必要性，再按项目适配、硬门槛、稳定版本、采用规模、更新新鲜度、维护活跃度和采用趋势选择，不以 stars、下载量或单一总分决定。
- 计划必须使用稳定 GOAL/REQ/AC/NFR/STG/VAL/ART ID，形成验收、阶段和验证闭环，并通过 `scripts/harness_plan_check.py --task-dir <task-dir> --mode approval`。正文按 profile 合并为约 10-14 个语义章节，机器细节只在 contract 保留；旧 25 章节计划继续合法。
- 提交审批前完成 Plan Quality Gate 与 Producer Readiness Gate，再调用 `complex-coding-reviewer` 的 coordinator 执行
  `plan-review`；`full` 派生 `strict` dispatch，`lite/standard` 派生 `conditional`，后两者在无风险升级或用户独立审查要求时由策略禁用委派并走合法 same-context receipt。Planner 根据 finding 修复目标，但不得
  执行语义审查或自行生成正式 verdict。
- 所有 managed profile 都必须索引 approval-included 的 review brief 和 required canonical plan-review receipt。dispatch、
  target/context 与 semantic result 作为 receipt 间接绑定的 supporting artifacts，不进入 plan artifact index，避免自引用。
  approval checker 通过 Reviewer 公共 CLI 验证 dispatch policy/lifecycle、`managed-plan` scope、双 digest、coverage、gap、
  lineage、passed verdict 和连续 supersedes；context 只能引用 plan、contract 与 approval-included planning artifacts。
- approval checker 通过后调用 `scripts/harness_active_task.py --mode activate` 写 active pointer；非终态或未知任务冲突必须 fail closed，只有用户明确选择任务后才可 `--mode switch`。随后总结授权请求并停止，不得创建 run-state/ledger、实现代码或提交。
- 用户批准后由 `complex-coding-executor` 生成 attestation、维护 run-state/ledger，并执行 review、验证和提交门禁。
- 批准后 scope、Stage DAG、必需验证、风险、依赖或授权改变时进入 Plan Amendment Gate。
- 自动 plan-review 修订最多两轮；第二轮仍有 blocking/major、需求持续漂移或研究不能收敛时，转为用户决策，不追求形式上的“零 issue”。
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
- `complex-coding-reviewer/scripts/review_dispatch.py`：冻结 plan-review 输入与 dispatch policy；不启动 Agent。
- `complex-coding-reviewer/scripts/review_validate.py`：正式 plan-review receipt 的唯一 validator；缺少 Reviewer skill 时 approval 必须 fail closed。

保持本文件精炼；流程和字段细节只在对应 reference 中维护。

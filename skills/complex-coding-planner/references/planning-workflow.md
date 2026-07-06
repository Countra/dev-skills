# Complex Coding Planner Workflow

本文件只描述复杂 coding 任务的规划阶段。方案获批后的实现、验证、提交和最终交付交给 `complex-coding-executor`。

## 任务分级

- `direct`：小而清晰、低风险。直接按普通最小实现和聚焦验证处理，不创建 `.harness/tasks/`。
- `needs-clarification`：目标、验收、环境、权限或验证信息存在阻塞不确定项。只向用户提问，然后停止。
- `managed`：复杂、高风险、多阶段、多模块、多仓库、前后端联动、公共接口、数据库、外部服务，或用户担心上下文压缩影响的任务。

只有 `managed` 任务使用本规划流程。

## 运行时文件

只有任务属于 `managed`，且用户允许落盘任务状态时，才创建 `.harness/tasks/`。

```text
.harness/
├── environment.md
├── active-task.json
└── tasks/
    └── YYYY-MM-DD/
        └── <type>/
            └── <task-slug>/
                ├── execution-plan.md
                ├── pending-decisions.md
                └── artifacts/
```

规则：

- `.harness/environment.md` 是 workspace 级环境清单，不按任务重复创建。
- `execution-plan.md` 是任务级唯一主契约。
- `pending-decisions.md` 是可选文件，只用于需要异步填写或审计记录的 blocking 决策。
- `artifacts/`、`logs/`、`tmp/`、`scratch/` 属于运行产物，通常应忽略。

## 规划流程

1. 读取 `.harness/active-task.json`（如存在）。
2. 读取 `.harness/environment.md`（如存在）。
3. 读取当前任务的 `execution-plan.md`（如存在）。
4. 检查项目规则文件，例如 `AGENTS.md`、`CLAUDE.md` 和项目 `docs/development.md`。
5. 在提出方案前收集本地代码、测试、配置、接口和文档上下文。
6. 如果任务依赖框架、API、协议、工具、模型或其他可能变化的事实，查询官方或一手资料。
7. 创建或更新 `execution-plan.md`。
8. 确认 `Git Context`：主分支、harness 工作分支、同步来源、分支占用和提交策略。
9. 写清 `Environment`、`Tooling`、`Validation`、`Process Manager Gate` 和文件写入策略。
10. 细化 `Implementation Plan`，每个阶段必须说明目标、做法、原因、位置、参考、验证、风险、回滚和 Stage Contract。
11. 完成 `Plan Quality Gate`。
12. 完成 `Plan Self-Review`，发现问题时先修复计划。
13. 完成 `Readiness Gate`。
14. 将状态设为 `awaiting_plan_approval`，请求用户批准方案。
15. 停止工作，等待用户明确批准。不得开始代码实现、验证实现或提交代码。

## Workspace 环境

用户可以用自然语言维护各项目 `docs/development.md`。planner 负责整理为 `.harness/environment.md`。

优先读取：

- `docs/development.md`
- `go.mod`
- `package.json`
- 锁文件，例如 `pnpm-lock.yaml`、`package-lock.json`、`yarn.lock`
- `pyproject.toml`、`requirements.txt`、`environment.yml`、`.python-version`
- `Dockerfile`、`compose.yaml`、`.devcontainer/`

如果环境信息冲突，并会影响安装、运行、测试、验证或最终声明，必须先向用户确认。

## Git 规划

managed 任务采用统一 harness 工作分支，不按任务名创建分支：

- `feature` / `feat` -> `harness/feature`
- `fix` -> `harness/fix`
- `refactor` -> `harness/refactor`
- `docs` -> `harness/docs`
- `test` -> `harness/test`
- `chore` -> `harness/chore`

主分支优先来自 `.harness/environment.md` 的 `Git` 区域。未配置时按 `dev -> main -> master -> origin/HEAD` 探测；结果不唯一或会影响提交、合并、验证时，必须停止并询问用户。

计划必须记录：

- 主分支、任务类型、工作分支。
- 创建或复用动作、同步来源、最近同步时间。
- 分支占用检查计划：`git log <main>..HEAD` 和 `git -c diff.autoRefreshIndex=false diff <main>...HEAD --name-only`。
- 同一仓库 Git 命令必须串行。
- `index.lock` 精确恢复策略。
- 热修复插入策略。
- 提交授权策略。实施批准不等于提交授权。

planner 只规划 Git 策略，不执行提交。

## 方案质量

`Implementation Plan` 不能是空泛清单。每个阶段必须包含：

- 目标
- 怎么做
- 为什么这么做
- 在哪里做，包括文件、模块、API、配置、测试或文档
- 参考来源
- 验证
- 风险和回滚
- 阶段契约

`Context` 必须区分本地代码、本地文档、外部资料和用户约束。不能只写“参考官方文档”，必须写来源和结论。

`Plan Quality Gate` 用于判断方案是否足够进入审批，不等同于 `Readiness Gate`。进入审批前必须检查：

- 关键判断都有证据来源，来源必须标为 `read`、`confirmed`、`external` 或 `assumption`。
- 影响面矩阵已覆盖 API、数据结构、前端交互、配置/环境、兼容性、测试和文档。
- 至少比较两个候选方案；如果只有一个合理方案，必须说明原因。
- 每个实施阶段都能独立验证，不能只写“最终一起测试”。
- 方案变更触发条件已记录。
- 用户批准摘要已记录批准范围、提交授权、工具授权和文档更新授权。

## Plan Self-Review

`Plan Quality Gate` 通过后，必须执行 `Plan Self-Review`。该自查用于主动挑出并修复方案问题，不等同于 `Plan Quality Gate` 或 `Readiness Gate`。

`Plan Self-Review` 必须覆盖：

- `Defects`：逻辑矛盾、错误假设、不可执行步骤、遗漏前置条件。
- `Optimizations`：可减少复杂度、文件数量、阶段数量、用户交互或验证成本的改进。
- `Missing items`：缺少环境、Git、验证、工具、MCP、process-manager、回滚、文档或提交策略。
- `Risks`：高风险改动缺少验证、缓解或回滚。
- `Consistency`：`Execution Control`、阶段计划、验证、Git、状态记录和恢复摘要之间存在冲突。

处理规则：

- 发现 defect 时，必须先修复计划，不得进入 `Readiness Gate`。
- 发现 missing item 时，必须补充到对应章节。
- 发现 optimization 时，如果不改变目标、范围和风险，应直接优化计划；如果会改变目标、范围、阶段、验证或风险，必须记录为方案变更并请求用户确认。
- 发现 risk 时，必须补充验证、缓解或回滚策略。
- 发现 consistency 问题时，必须修正冲突字段；`execution-plan.md` 仍是任务状态唯一主契约。
- 用户审批前只要方案内容被修改，必须重新执行 `Plan Self-Review` 并更新自查结论。
- 自查修复影响目标、范围、阶段、验证、工具依赖、风险或提交策略时，必须重新跑 `Plan Quality Gate` 和 `Readiness Gate`。

## 文件写入策略

所有落盘写文件动作都适用分段 patch 策略，包括代码、Markdown 文档、规划文档、模板、JSON、JSONL、YAML、changelog、eval fixture 和 harness 任务状态文件。

规则：

- 分段 patch 是落盘策略，不要求一次性生成全部细节。
- 大内容首次写入前必须先形成全局框架，包括目标、影响范围、模块边界、接口关系、验证策略和整体复查计划。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限为 200 行；超过必须拆分。
- 当写入范围可能较大或无法判断规模时，必须先在计划中记录分段判断。
- 目标文件超过 500 行时，默认禁止整文件重写，优先局部 patch。
- 分段边界必须保持语义完整，优先使用 Markdown 章节、完整表格、完整函数、完整配置节或完整 changelog 日期块。
- 所有分段写入完成后，必须重新读取完整目标文件检查一致性。

如果 `apply_patch` 失败，必须先读取目标文件确认是否有部分写入，再缩小失败段重试。不得用 shell 拼接文件绕过 patch 失败。

## 用户批准门禁

`Readiness Gate` 只是技术就绪检查，不授权实现。

Readiness 通过后必须：

1. 更新 `execution-plan.md`。
2. 将 `.harness/active-task.json` 状态设为 `awaiting_plan_approval`。
3. 总结最终方案、影响范围、验证策略和提交策略。
4. 停止工作，等待用户明确批准。

可接受的批准表达：

- “确认执行”
- “按方案执行”
- “方案没问题，开始实现”
- “同意方案 A”

实施批准不等于提交授权。只有用户明确说“提交”“阶段提交”或批准摘要明确记录提交授权，executor 才能提交。

如果用户改变方案、环境、工具或验证策略，必须更新计划并重新通过 readiness 和批准。

## Blocking 决策

只询问会影响方案、环境、权限、验证、接口、数据、依赖、风险或提交行为的 blocking 问题。

推荐格式：

```text
D-001：决策标题
A（recommended）：...
B：...
C：...
Custom：...
```

提出问题后必须停止。不能继续规划、编码、验证或用默认假设绕过阻塞点。

如果使用 `pending-decisions.md`，必须在会话中同步摘要同一组问题。用户可以在会话中回答，也可以编辑文件。答案最终必须合并回 `execution-plan.md`，它仍然是唯一主契约。

## Executor 交接契约

planner 生成的 `execution-plan.md` 必须包含 executor 可消费的状态和门禁：

- `Execution Control Snapshot`：放在文档靠前位置，记录 execution mode、overall status、current stage、completed stages、remaining stages、next automatic action、stop condition 和 state source。
- `Implementation Plan`：每个阶段都有 Stage Contract。
- `Environment`、`Git Context`、`Tooling`、`Process Manager Gate`。
- `Validation` 和验证证据表。
- `Documentation`、`File Write Strategy`、`Questions And Overrides`。
- `Plan Quality Gate`、`Plan Self-Review`、`Readiness Gate`、`Plan Approval`。
- `Execution Control`、`Implementation Progress`、`Stage Entry Gate`、`Stage Exit Gate`、`Stage Transition Gate`。
- `Code Review`、`Resume Summary`、`Commit Log`。

方案获批后，应由 `complex-coding-executor` 读取该计划并继续。planner 不执行实现阶段。

## Skill 更新后的继续工作

如果用户提示 `complex-coding-planner` 已更新，继续当前规划任务前必须：

1. 重新读取最新 `SKILL.md` 和 `references/planning-workflow.md`。
2. 重新读取 `.harness/active-task.json`、`.harness/environment.md` 和当前任务的 `execution-plan.md`。
3. 对照新规则和旧任务状态，只说明会影响当前工作的差异。
4. 不自动大范围重写旧状态，不删除旧字段，不迁移已批准方案。

以下差异必须先向用户确认：

- 改变已批准方案、阶段拆分或阶段边界。
- 改变 Git 分支、同步、合并或提交策略。
- 改变验证工具、验证命令、证据要求或最终声明范围。
- 改变公共接口、数据结构、依赖、权限或运行环境。

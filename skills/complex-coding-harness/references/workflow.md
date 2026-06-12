# Complex Coding Harness Workflow

## 任务分级

- `direct`：小而清晰、低风险。直接做最小实现和聚焦验证，不创建 `.harness/tasks/`。
- `needs-clarification`：目标、验收、环境、权限或验证信息存在阻塞不确定项。只向用户提问，然后停止。
- `managed`：复杂、高风险、多阶段、多模块、多仓库、前后端联动、公共接口、数据库、外部服务，或用户担心上下文压缩影响的任务。

只有 `managed` 任务使用以下流程。

## 运行时文件

只有任务属于 `managed`，且用户允许落盘任务状态时，才创建 `.harness/tasks/`。

```text
.harness/
├── environment.md
├── active-task.json
└── tasks/
    └── YYYY-MM-DD/
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

## Managed 任务流程

1. 读取 `.harness/active-task.json`（如存在）。
2. 读取 `.harness/environment.md`（如存在）。
3. 读取当前任务的 `execution-plan.md`（如存在）。
4. 检查项目规则文件，例如 `AGENTS.md`、`CLAUDE.md` 和项目 `docs/development.md`。
5. 在提出方案前收集本地代码上下文。
6. 如果任务依赖框架、API、协议、工具、模型或其他可能变化的事实，查询官方或一手资料。
7. 创建或更新 `execution-plan.md`。
8. 确认 `Git Context`：主分支、harness 工作分支、同步来源和提交策略。
9. 完成 `Readiness Gate`。
10. 将状态设为 `awaiting_plan_approval`，请求用户批准方案。
11. 只有用户明确批准后才能实现。
12. 按阶段实施，每阶段完成 review、验证、修复、记录更新和授权提交。
13. 完成最终交付门禁，给出任务结论、验证摘要、关键证据、commit 信息和剩余风险。

## 长期进程管理强制规则

如果当前会话可用 skill 列表中存在 `process-manager`，所有服务、后台和需要挂起运行的长期进程都必须由 `process-manager` 管理。该规则适用于方案制定、阶段实施、验证、调试、最终清理和上下文恢复后的继续执行。

长期进程包括：

- 前端 dev server，例如 `pnpm dev`、`npm run dev`、`vite`。
- 后端 web/API 服务，例如 Go、Python、Node、Java 的本地服务。
- worker、watcher、队列消费者、模型服务、文件监听器。
- 任何启动后不会马上返回、需要持续占用终端或端口的进程。

finite command 不进入 `process-manager`，应按项目验证流程直接运行：

- 单元测试、集成测试、lint、format、build。
- 数据迁移、代码生成、一次性脚本。
- 任何预期马上返回标准输出结果的命令。

强制操作顺序：

1. 在计划阶段判断每个阶段是否需要长期进程，并写入 `Process Manager Gate`。
2. 如果需要长期进程，读取 `process-manager` 的 `SKILL.md` 和 `references/workflow.md`。
3. 启动前先运行 `pm_health.py`；manager 离线时停止当前长期进程操作，请求用户手动启动 manager 或授权 `start_manager.ps1`。
4. 准备或更新 service config 后运行 `pm_validate.py`。
5. 使用 `pm_start.py` 启动，使用 `pm_ready.py` 或 `pm_status.py` 判断可用。
6. 使用 `pm_logs.py` 采集日志证据，使用 `pm_stop.py` 或 `pm_restart.py` 清理或重启。
7. 把 `processKey`、ready 结果、日志路径、清理结果写入验证证据。

禁止：

- 不直接运行会挂起 shell 的 `pnpm dev`、`npm run dev`、`go run`、`python app.py` 等长期服务命令。
- 不手写 `Start-Process`、`cmd /c start`、`powershell -Command`、`nohup`、`&` 或自制后台 launcher 作为替代。
- manager 离线时不允许退回 shell 启动；必须停止并确认。
- 不自动 kill 不属于当前 `processKey` 的未知 PID 或未知端口占用者。

防遗忘要求：

- 每个 managed 任务的 `execution-plan.md` 必须包含 `Process Manager Gate`。
- 每个阶段的 `Stage Entry Gate` 必须确认本阶段长期进程策略。
- 每个阶段的 `Stage Exit Gate` 必须确认长期进程清理和证据记录。
- 每个 `Resume Summary` 必须记录长期进程规则状态；上下文压缩或中断后，恢复流程必须重新读取该字段。

## Skill 更新后的继续工作

如果用户提示 `complex-coding-harness` 已更新，不做 Git tag、schema version、workflow version 或自动迁移流程。继续当前任务前必须：

1. 重新读取最新 `SKILL.md` 和 `references/workflow.md`。
2. 重新读取 `.harness/active-task.json`、`.harness/environment.md`（如存在）和当前任务的 `execution-plan.md`。
3. 对照新规则和旧任务状态，只说明会影响当前工作的差异。
4. 不自动大范围重写旧状态，不删除旧字段，不迁移已批准方案。

低风险差异可以在后续自然更新任务记录时补齐，例如新增空检查项、补充说明字段或按新模板追加记录区。

以下差异必须先向用户确认，不能直接继续实现：

- 改变已批准方案、阶段拆分或阶段边界。
- 改变 Git 分支、同步、合并或提交策略。
- 改变验证工具、验证命令、证据要求或最终声明范围。
- 改变公共接口、数据结构、依赖、权限或运行环境。

## Workspace 环境

用户可以用自然语言维护各项目 `docs/development.md`。agent 负责整理为 `.harness/environment.md`。

优先读取：

- `docs/development.md`
- `go.mod`
- `package.json`
- 锁文件，例如 `pnpm-lock.yaml`、`package-lock.json`、`yarn.lock`
- `pyproject.toml`、`requirements.txt`、`environment.yml`、`.python-version`
- `Dockerfile`、`compose.yaml`、`.devcontainer/`

如果环境信息冲突，并会影响安装、运行、测试、验证或最终声明，必须先向用户确认。

## Git 工作分支

managed 任务采用统一 harness 工作分支，不按任务名创建分支：

- `feature` / `feat` -> `harness/feature`
- `fix` -> `harness/fix`
- `refactor` -> `harness/refactor`
- `docs` -> `harness/docs`
- `test` -> `harness/test`
- `chore` -> `harness/chore`

主分支优先来自 `.harness/environment.md` 的 `Git` 区域。未配置时按 `dev -> main -> master -> origin/HEAD` 探测；结果不唯一或会影响提交、合并、验证时，必须停止并询问用户。

切换或创建 harness 分支前必须检查：

- `git status --short`
- `git branch --show-current`

如果存在用户或未知改动、未完成 merge/rebase/cherry-pick、冲突文件或不明确的当前分支，必须停止确认。不要自动 stash、reset、rebase、覆盖用户改动或删除分支。

目标分支不存在时创建，已存在时切换。进入实施前，把主分支最新代码合入 harness 工作分支；默认使用 merge，不默认 rebase。优先合入 `origin/<main>`，没有远程或不能联网时合入本地 `<main>`。合并失败必须记录到 `execution-plan.md` 并停止确认。

进入 harness 分支后必须检查分支占用：

- `git log <main>..HEAD`
- `git diff <main>...HEAD --name-only`

如果发现未合回主分支的提交，必须判断是否属于当前任务链路。属于当前任务链路时，记录到 `Git Context` 后继续；不属于当前任务链路或无法判断时，必须暂停确认。不要把其他任务的提交混入当前阶段提交或最终交付。

热修复插入规则：

- 如果当前在 `harness/feature`，用户临时要求处理 `fix`，必须先确认 feature 代码是否要合入主分支。
- 用户确认合并时，先切回主分支合并 `harness/feature`，再切到或创建 `harness/fix`，并让 `harness/fix` 同步主分支。
- 用户不确认合并时，只能在工作区安全时直接切到 `harness/fix` 并同步主分支。
- 如果 feature 有未提交改动，先询问是否提交检查点或暂停切换，不能自动带着脏工作区切换。

`execution-plan.md` 必须记录 `Git Context`，至少包括主分支、任务类型、工作分支、创建或复用动作、同步来源、最近同步时间、分支占用、提交策略、分支收口状态和未解决分支问题。

## 执行计划质量

`Implementation Plan` 不能是空泛清单。每个阶段必须包含：

- 目标
- 怎么做
- 为什么这么做
- 在哪里做，包括文件、模块、API、配置、测试或文档
- 参考来源
- 验证
- 风险和回滚

`Context` 必须区分本地代码、本地文档、外部资料和用户约束。不能只写“参考官方文档”，必须写来源和结论。

`Plan Quality Gate` 用于判断方案是否足够进入审批，不等同于 `Readiness Gate`。进入审批前必须检查：

- 关键判断都有证据来源，来源必须标为 `read`、`confirmed`、`external` 或 `assumption`。
- 影响面矩阵已覆盖 API、数据结构、前端交互、配置/环境、兼容性、测试和文档。
- 至少比较两个候选方案；如果只有一个合理方案，必须说明原因。
- 每个实施阶段都能独立验证，不能只写“最终一起测试”。
- 方案变更触发条件已记录；命中触发条件时必须暂停实现、更新计划并重新请求批准。
- 用户批准摘要已记录批准范围、提交授权、工具授权和文档更新授权。

证据等级：

- `read`：已读取本地代码、配置、测试或文档。
- `confirmed`：已通过命令、测试、运行结果或工具输出确认。
- `external`：来自官方文档、一手资料、规范或用户提供资料。
- `assumption`：当前只能作为假设，必须写明影响，并在必要时向用户确认或限制最终声明。

方案变更触发条件包括：

- 实施范围超出批准文件、模块、接口或配置。
- 需要新增依赖、外部服务、权限、MCP 或运行环境。
- API、数据结构、持久化格式或兼容性策略发生变化。
- 必需验证无法执行，且替代验证不足以覆盖风险。
- 发现候选方案的关键证据不成立。

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

提出问题后必须停止。不能继续编码、继续改文件、继续验证，也不能用默认假设绕过阻塞点。

如果使用 `pending-decisions.md`，必须在会话中同步摘要同一组问题。用户可以在会话中回答，也可以编辑文件。答案最终必须合并回 `execution-plan.md`，它仍然是唯一主契约。

## 实施阶段循环

每个阶段开始前必须先形成 `Stage Contract`，至少包含：

- 阶段目标和范围。
- 允许修改的文件、模块、接口、配置或文档。
- 明确禁止修改的范围。
- 阶段进入条件。
- 阶段退出条件。
- 必需验证。
- 是否预期提交。

`Stage Entry Gate` 通过前不能开始编码。必须检查：

- 当前分支和工作区状态符合 `Git Context`。
- 上一阶段没有未处理的 blocking 或 major finding。
- 本阶段相关环境、命令、工具和权限可用，或替代策略已记录。
- 本阶段范围没有超出已批准方案。
- 如果本阶段需要长期进程，`Process Manager Gate` 已通过；如果不需要，已明确记录为 not-applicable。
- 如果存在用户或未知改动，必须暂停确认。

`Stage Exit Gate` 通过前不能进入下一阶段或最终交付。必须检查：

- 阶段目标已经完成，且没有超出阶段契约。
- code review 已完成，blocking 和 major finding 已关闭。
- 必需验证已执行；无法执行时已记录原因、影响和替代证据。
- 明显缺陷已修复，并已重复必要 review 和验证。
- 长期进程均已通过 `process-manager` 记录 ready/log/status/stop 证据，或已明确记录本阶段不涉及长期进程。
- `execution-plan.md`、changelog 或等价变更记录、`Commit Log` 已更新。
- 如阶段提交已授权，已完成提交并记录 commit hash；未提交时已说明原因。

每个已批准阶段都必须执行：

1. 重读 `.harness/active-task.json`、`.harness/environment.md`、`execution-plan.md`、`pending-decisions.md`（如存在）、项目 `docs/development.md` 和 changelog。
2. 更新 `Implementation Progress`，记录当前阶段、范围和下一步。
3. 复查 `Process Manager Gate`，确认本阶段是否需要长期进程；需要时必须使用 `process-manager`，不能手写后台 shell 命令。
4. 检查 `Git Context` 和实际 git 状态，确认当前分支、主分支同步和工作区安全。
5. 阅读本阶段相关代码、测试、配置、API 和文档。
6. 在批准范围内做最小必要修改。
7. 修复明显缺陷；小优化只能在不改变方案方向时执行。
8. 如果范围、风险、接口、验证成本或方案方向变化，停止并重新请求用户批准。
9. 做 code review，检查正确性、边界条件、错误处理、兼容性、无关改动、测试和文档。
10. 按 `Validation`、`.harness/environment.md` 和 `Process Manager Gate` 执行验证。
11. 修复 review 或验证发现的问题，并重复 review 和验证，直到没有 blocking 或 major finding。
12. 更新 changelog 或项目等价变更记录。
13. 只有用户批准的方案授权提交时，才提交代码；提交 hash 写入 `Commit Log`。
14. 进入下一阶段前，重读任务记录、`Process Manager Gate` 和 changelog，确认状态没有丢失。

## 验证规则

- 前端交互工作必须使用环境清单指定的浏览器验证工具。如果要求 Chrome DevTools MCP，必须用它检查 UI、console、network 和必要截图。
- 后端工作必须包含相关单元测试；API 变更还需要接口 smoke 或契约检查。
- Python 工作必须使用配置的 conda、venv、解释器或包管理器。
- 每轮大修改必须运行配置的 smoke 检查。
- 长期后台进程（例如 dev server、web 服务、worker、watcher、模型服务）在 `process-manager` skill 存在时必须交给它管理；finite command 仍直接运行，不进入 process-manager。
- 如果 `process-manager` 可用，必须先读取它的 `SKILL.md` 和 `references/workflow.md`，再用 `pm_health.py`、`pm_validate.py`、`pm_start.py`、`pm_ready.py`、`pm_logs.py`、`pm_stop.py` 等脚本管理生命周期。
- 如果 manager 离线，必须停止当前长期进程操作，请求用户手动启动 manager 或授权运行 `start_manager.ps1`；不要手写 `Start-Process`、`nohup`、`pnpm dev` 后台化命令。
- 如果某项验证无法执行，必须记录原因、影响和替代证据，不能声称通过。
- 验证证据必须写入 `execution-plan.md`，包括命令或工具、结果、覆盖范围、未覆盖范围和 artifact。

多阶段任务必须维护验证证据表，至少记录阶段、命令或工具、结果、覆盖内容、未覆盖范围、证据或日志、处理结论。验证失败时不能直接提交；必须修复并重复必要验证，或记录阻塞并停止。

`Code Review` 的严重程度必须按以下规则处理：

- `blocking`：不修复不能继续当前阶段。
- `major`：必须修复；如果不修复，必须重新请求用户批准。
- `minor`：可在不改变方案方向时自修；不修复时必须说明影响。
- `follow-up`：不影响当前验收，但必须记录后续建议。

每个阶段结束后必须写 `Resume Summary`，用于上下文压缩后快速恢复。至少包含当前阶段、已完成内容、最新 commit、下一步、长期进程规则状态、未覆盖范围和剩余风险。

## 最终交付门禁

managed 任务结束前必须完成最终交付门禁：

1. 重读 `.harness/active-task.json`、`.harness/environment.md`、`execution-plan.md`、changelog 和 git 状态。
2. 确认每个阶段都有 review、验证、缺陷处理、文档更新和提交记录。
3. 汇总已执行验证；不能把未执行验证写成通过。
4. 汇总未覆盖范围、失败项、剩余风险和后续建议。
5. 汇总 branch status：当前分支、主分支、是否已合回主分支、未合回时代码停留在哪个 harness 分支。
6. 汇总 commit hash、commit message、changelog 记录和关键文件。
7. 前端、UI、可视化、图表、地图、canvas、图片处理、报告预览或浏览器流程任务，必须提供截图、日志、trace、报告或替代证据。
8. 将最终结论写入 `execution-plan.md` 的 `Validation`、`Implementation Progress`、`Code Review` 和 `Commit Log`。
9. 最终回复必须携带任务结论、核心改动、验证结果、未覆盖范围、code review 结论、branch status、commit 信息、关键证据和剩余风险。

截图和 artifact 规则：

- 运行产物默认放在 `.harness/tasks/<date>/<task-slug>/artifacts/`。
- artifact 默认不提交；如果截图或报告需要成为项目文档的一部分，必须先获得用户确认。
- 如果无法截图或无法导出 artifact，必须说明原因、影响和替代验证。

## Commit 和 Changelog

只有用户明确批准，或已批准方案明确要求阶段提交时，才能提交。

默认提交信息格式：

```text
feat(scope): 标题

- 重点一
- 重点二
- 重点三
```

标题和分列之间保留一个空行；分列之间不加空行。

提交命令必须保证 bullet 之间没有空行。禁止使用多个 `-m` 分别传入每条 bullet，因为 Git 会把每个 `-m` 当成独立段落并自动插入空行。

首选方式是把完整提交信息写入临时文件，然后使用 `git commit -F <commit-message-file>`：

```text
feat(scope): 标题

- 重点一
- 重点二
- 重点三
```

提交信息临时文件应放在 `.harness/tasks/<date>/<task-slug>/tmp/commit-message.txt` 或等价的 ignored 运行时目录。提交前必须检查：

- 标题后正好一个空行。
- bullet 行之间没有空行。
- 没有尾随空格。
- scope、标题和 bullet 与本阶段改动一致。

只有在 shell 能可靠传入完整多行字符串时，才允许使用单个 `-m` 参数包含完整提交信息；不得使用多个 `-m` 参数拆分 bullet。

`Commit Log` 必须记录：

- 仓库
- commit hash
- commit message
- 对应阶段
- changelog 记录

## 恢复流程

上下文压缩或中断后：

1. 读取 `.harness/active-task.json`。
2. 读取 `pending-decisions.md`（如存在）。
3. 读取当前 `execution-plan.md`。
4. 读取 `.harness/environment.md`。
5. 复查 `Process Manager Gate` 和 `Resume Summary` 的长期进程规则状态。
6. 检查 `Git Context`、实际文件和 git 状态。
7. 继续 `next_action`，不要重新开任务。

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
6. 完成 `Research Gate`：识别不确定项，判断是否需要本地调研、在线搜索、用户确认或阻塞。
7. 如果任务依赖框架、API、协议、工具、模型或其他可能变化的事实，查询官方或一手资料。
8. 完成 `Standards Discovery Gate`：识别语言、技术栈、框架、API 类型和架构风险，收集适用规范来源。
9. 完成 `Development Quality Gate`：把代码标准、静态质量、架构边界、设计模式取舍、耦合/内聚和验证映射写入计划。
10. 创建或更新 `execution-plan.md`。
11. 在计划靠前位置写入 `Execution Contract`、`Goal Condition`、`Planning Loop Protocol` 和 `Executor Work Loop`。
12. 确认 `Git Context`：主分支、harness 工作分支、同步来源、分支占用和提交策略。
13. 写清 `Environment`、`Tooling`、`Validation`、`Process Manager Gate` 和文件写入策略。
14. 细化 `Implementation Plan`，每个阶段必须说明目标、做法、原因、位置、参考、验证、风险、回滚和 Stage Contract。
15. 完成 `Plan Quality Gate`。
16. 完成 `Plan Self-Review`，发现问题时先修复计划。
17. 完成 `Readiness Gate`。
18. 将状态设为 `awaiting_plan_approval`，请求用户批准方案。
19. 停止工作，等待用户明确批准。不得开始代码实现、验证实现或提交代码。

## 规划循环

managed 计划必须把思考过程落到文件中，避免上下文压缩后只剩口头状态。

规则：

- 阶段拆分默认 3-7 个可独立验证阶段；超过 7 个阶段必须说明为什么不能合并。
- 读取多个关键源码、文档、网页、日志或参考项目文件后，必须把关键 findings 写入 `Context`、参考矩阵或 artifacts。
- 重大决策前必须重读目标、约束、Options、Decision、影响面和 reapproval triggers。
- 放弃的方案必须写明放弃原因，避免恢复后重复探索。
- 发现错误假设、失败路径或不可行做法时，不删除痕迹，改写为 findings、risk 或 rejected option。
- 每次补强计划后，如果影响目标、范围、阶段、验证、风险、工具授权或提交策略，必须重新运行 `Plan Quality Gate`、`Plan Self-Review` 和 `Readiness Gate`。

## Research Gate

`Research Gate` 用于防止不确定问题、可变事实和在线资料结论只停留在对话上下文中。每个 managed 计划都必须记录研究模式：

- `none`：任务没有外部事实依赖，必须说明原因。
- `local-only`：仅依赖本地源码、配置、锁文件、项目文档或用户给定资料。
- `online-required`：涉及框架、API、协议、工具、模型、依赖版本、外部服务、浏览器行为、平台差异、法规、安全、金融、医学或其它可能变化事实。
- `blocked-by-access`：需要在线或一手资料，但网络、权限、账号、私有资料或用户限制阻止调研。

规则：

- `online-required` 必须优先查询官方文档、源码仓库、release notes、标准文档、论文、厂商文档或其它一手资料。
- 非一手资料只能作为补充；如果结论会影响方案、风险、接口、验证或兼容性，不能只依赖二手资料。
- 搜索后必须记录查询或来源、工具、日期、结论、可信度、影响和后续动作。
- 无法联网或资料不可访问时，不得把关键事实写成 `confirmed`；必须标为 `blocked-by-access`、`assumption` 或 blocking decision，并说明影响。
- 不确定项能通过资料解决时先调研；只有资料无法解决、需要业务取舍、权限或用户偏好时才提 blocking 问题。
- 进入 `Readiness Gate` 前，所有 `online-required` 项必须有来源矩阵证据，所有 blocking 不确定项必须关闭或记录为停止条件。

## Standards Discovery Gate

`Standards Discovery Gate` 用于把“应该按什么标准开发”从隐含经验变成可追踪输入。它只强制 managed 任务执行；direct 任务可按项目现有规则轻量处理。

规划时必须记录：

- 技术栈识别：语言、框架、包管理器、运行形态、API 类型、数据层、部署环境和架构风险。
- 规范来源：项目内 `AGENTS.md`、`docs/development.md`、配置文件、官方语言规范、官方框架文档、API/架构设计规范和高质量参考。
- standards index：优先写入 `execution-plan.md`；资料较多时写入 `.harness/tasks/<date>/<type>/<task-slug>/artifacts/standards/standards-index.md` 并在计划中引用。
- 适用边界：哪些规范必须遵守，哪些只作为参考，哪些因为项目现状、风险或范围不适用。
- 更新策略：在线来源必须记录访问日期、可信度和影响；无法访问时标为 `blocked-by-access` 或 assumption。

来源选择规则：

- 优先项目内已有规则，其次官方/一手资料，再使用高质量二手资料补充背景。
- 例如 Go 项目可优先查 Google Go Style 和项目内 `gofmt`、`go vet`、`golangci-lint` 配置；Web 后端项目还应按框架和 API 类型查官方工程结构、REST/gRPC/API 设计规范。
- 不把外部规范全集复制进 skill；默认沉淀索引、摘要、URL、适用性和少量必要摘录。
- 设计模式、SOLID 或数量口径不得凭记忆硬编码；需要时在 standards index 中核验来源、定义和项目适用性。

## Development Quality Gate

`Development Quality Gate` 用于在审批前确认实现方案是否具备可维护开发质量，不用于强迫所有任务采用复杂架构或设计模式。

计划必须覆盖：

- 代码标准：命名、格式化、注释、错误处理、日志、配置、测试风格和项目现有约定。
- 静态质量：语法检查、format、lint、typecheck、build、单测或等价验证；无法执行时必须记录原因和替代证据。
- 架构边界：模块职责、依赖方向、公共接口、数据所有权、兼容性和迁移边界。
- 设计模式取舍：说明是否需要创建型、结构型、行为型或领域内常见模式；不采用模式时记录原因，避免过度设计。
- 低耦合高内聚：识别共享状态、跨层调用、循环依赖、重复抽象、过宽接口和单一职责风险。
- 验证映射：把每类质量要求映射到阶段、命令、代码审查项或替代证据。

处理规则：

- 风险越高，Development Quality Gate 越具体；低风险 managed 任务可以用简洁表格完成。
- 如果 standards index 发现的规范会改变 approved scope、阶段边界、公共接口或验证策略，必须记录 reapproval trigger。
- 如果项目规范和外部规范冲突，优先项目内明确规则，并在计划中说明取舍。
- 每个 Stage Contract 应说明本阶段适用的 standards 和 development quality checks。

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
- 适用规范和开发质量检查
- 验证
- 风险和回滚
- 阶段契约

`Execution Contract` 必须包含：

- `contract_version`
- `task_id`
- `execution_mode`
- `overall_status`
- `approval_status`
- `approved_contract_hash`
- `current_stage_id`
- `remaining_stage_ids`
- `stop_condition`
- `commit_authorization`
- `ledger_policy`
- `single_writer`
- `reapproval_required`

`Goal Condition` 必须说明所有 approved stages、final gate、open decisions、验证证据和提交授权状态如何共同决定最终完成。

`Context` 必须区分本地代码、本地文档、外部资料和用户约束。不能只写“参考官方文档”，必须写来源和结论。

`Plan Quality Gate` 用于判断方案是否足够进入审批，不等同于 `Readiness Gate`。进入审批前必须检查：

- 关键判断都有证据来源，来源必须标为 `read`、`confirmed`、`external` 或 `assumption`。
- 影响面矩阵已覆盖 API、数据结构、前端交互、配置/环境、兼容性、测试和文档。
- Standards Discovery Gate 已识别技术栈、规范来源、standards index、适用边界和在线来源状态。
- Development Quality Gate 已覆盖代码标准、静态质量、架构边界、设计模式取舍、耦合/内聚和验证映射。
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
- `Development quality`：规范发现、代码标准、静态质量、架构边界、模式取舍、低耦合高内聚或验证映射缺失。

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

## Plan Amendment Gate

计划获批后，以下变化必须停止实施并重新请求用户批准：

- approved scope 改变。
- 阶段边界、阶段顺序、阶段数量或 Stage Contract 改变。
- 必需验证、工具授权、长期进程策略或提交策略改变。
- 风险等级、公共接口、数据结构、权限、依赖或兼容性假设改变。
- attestation mismatch 且无法证明是预期文档更新。

不触发重新批准的情况必须记录原因，例如只补充验证证据、更新实施进度、写入 ledger 摘要或修正明显错别字。

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
- `Execution Contract`：放在文档靠前位置，记录 executor 可读机器字段。
- `Goal Condition`、`Planning Loop Protocol` 和 `Executor Work Loop`：说明如何持续推进和如何判断完成。
- `Implementation Plan`：每个阶段都有 Stage Contract。
- `Environment`、`Git Context`、`Tooling`、`Process Manager Gate`。
- `Standards Discovery Gate` 和 `Development Quality Gate`：说明规范来源、适用边界、架构和质量验证映射。
- `Validation` 和验证证据表。
- `Documentation`、`File Write Strategy`、`Questions And Overrides`。
- `Plan Quality Gate`、`Plan Self-Review`、`Readiness Gate`、`Plan Approval`。
- `Execution Control`、`Implementation Progress`、`Stage Entry Gate`、`Stage Exit Gate`、`Stage Transition Gate`。
- `Ledger Evidence`、`Code Review`、`Resume Packet`、`Resume Summary`、`Commit Log`。

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

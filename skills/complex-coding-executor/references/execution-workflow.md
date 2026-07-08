# Complex Coding Executor Workflow

本文件是 `complex-coding-executor` 的执行阶段规则。只在已有 `execution-plan.md` 且计划已批准时使用。

## 入口检查

每轮开始按顺序读取：

1. `.harness/active-task.json`
2. `.harness/environment.md`
3. 当前任务的 `execution-plan.md`
4. `pending-decisions.md`（如存在）
5. 项目 `docs/development.md`、`AGENTS.md`、`CLAUDE.md`（如存在）
6. changelog 或项目等价变更记录

执行前必须确认：

- `HARNESS_DISABLED=1` 未启用；若启用，只做 direct/advisory 行为，不消费历史 active task。
- `harness_task_resolver.py` 能解析 active task，且 task_dir 和 execution-plan 都位于 workspace 内。
- `execution-plan.md` 的 `Plan Approval` 已批准实施。
- `Execution Contract` 存在且与 `.harness/active-task.json` 的 task_id、execution_mode、overall_status、current_stage、remaining_stages 和 stop_condition 一致。
- 没有 open blocking 决策。
- `Execution Control.overall_status` 是 `in_progress` 或可从 approved 状态安全切入。
- 当前阶段存在于已批准的 `Implementation Plan`。
- `Process Manager Gate`、`Git Context`、`Validation`、`Commit policy` 和 `Resume Summary` 存在。
- 如果计划包含 `Standards Discovery Gate` 或 `Development Quality Gate`，必须读取 standards index 和对应门禁章节。
- `active-task.json` 与 `execution-plan.md` 冲突时，以 `execution-plan.md` 为准，先修正 `active-task.json`。

建议在执行前运行：

```text
python skills/complex-coding-executor/scripts/harness_exec_check.py --workspace <workspace> --task-dir <task-dir> --mode preflight
```

需要快速汇报或恢复状态时运行：

```text
python skills/complex-coding-executor/scripts/harness_exec_check.py --workspace <workspace> --task-dir <task-dir> --mode status
```

## 执行控制

用户批准 managed 方案后，默认执行模式为 `run-to-completion`。该模式表示连续完成所有已批准阶段，直到最终交付门禁通过。

只有用户明确要求“只做当前阶段”“完成后等我确认”或等价表达时，才允许使用 `stage-only`。

禁止把以下情况当作停止条件：

- 阶段完成。
- 阶段提交完成。
- 恢复点完成。
- 下一阶段已识别。
- 上下文压缩风险。
- 当前轮次变长。
- 需要更新任务记录。

上下文压缩或中断恢复后，如果 `execution_mode = run-to-completion`、`remaining_stages` 非空且 `stop_condition = none`，必须继续 `next_automatic_action`。

每轮恢复、阶段开始或阶段转移前应执行 loop tick：

```text
python skills/complex-coding-executor/scripts/harness_exec_check.py --workspace <workspace> --task-dir <task-dir> --mode loop-tick
```

loop tick 通过后：

- 若仍有 remaining stages，下一动作必须是 `continue Stage N`。
- 若无 remaining stages，进入最终交付门禁。
- 若存在 blocking reason、attestation mismatch、open decision 或 plan amendment，停止并记录原因。

## 停止条件

只有以下情况允许停止：

- 用户明确要求暂停、停止、只完成当前阶段或等待确认。
- 发现方案变化，需要重新批准。
- 有 blocking 决策必须用户确认。
- 工作区存在用户或未知改动，继续会有覆盖风险。
- Git 处于冲突、merge、rebase、cherry-pick 未完成或分支状态不安全。
- 必需权限被拒绝，且无安全替代路径。
- 必需验证失败，已按规则自修后仍无法通过，或替代验证不足。
- `process-manager` 离线且用户未启动或授权 bootstrap，且当前阶段需要长期进程。
- 所有已批准阶段完成，并且最终交付门禁通过。

命中停止条件时，必须更新 `Execution Control`、`Resume Summary` 和 `.harness/active-task.json`。

## 阶段循环

每个阶段开始前必须形成或读取 Stage Contract，至少包含：

- 阶段目标和范围。
- 允许修改的文件、模块、接口、配置或文档。
- 明确禁止修改的范围。
- 阶段进入条件。
- 阶段退出条件。
- 必需验证。
- 是否预期提交。

Stage Entry Gate 通过前不能开始编码。必须检查：

- 当前分支和工作区状态符合 `Git Context`。
- 上一阶段没有未处理的 blocking 或 major finding。
- 本阶段相关环境、命令、工具和权限可用，或替代策略已记录。
- 本阶段范围没有超出已批准方案。
- 如果本阶段需要长期进程，`Process Manager Gate` 已通过；如果不需要，已明确记录为 not-applicable。
- 如果存在用户或未知改动，必须暂停确认。

每个阶段执行步骤：

1. 重读任务状态、环境、执行计划、pending 决策和 changelog。
2. 运行或等价执行 status/loop-tick，确认当前阶段、范围和下一步。
3. 写入 ledger `stage_started` 或 heartbeat。
4. 更新 `Implementation Progress`，记录当前阶段、范围和下一步。
5. 复查 `Process Manager Gate`。
6. 检查 `Git Context` 和实际 git 状态。
7. 阅读本阶段相关代码、测试、配置、API、文档、standards index 和开发质量门禁。
8. 在批准范围内做最小必要修改。
9. 修复明显缺陷；小优化只能在不改变方案方向时执行。
10. 如果范围、风险、接口、验证成本或方案方向变化，停止并进入 `Plan Amendment Gate`。
11. 执行 `Development Quality Check` 和 code review，并将 blocking/major finding 写入计划或 ledger。
12. 按 `Validation`、`.harness/environment.md` 和 `Process Manager Gate` 执行验证。
13. 修复 review 或验证发现的问题，并重复必要 review 和验证。
14. 更新 changelog 或项目等价变更记录。
15. 只有提交已授权时，才提交代码；提交 hash 写入 `Commit Log`。
16. 更新 `Ledger Evidence`、`Resume Packet` 和 `Resume Summary`。

## Research Drift Gate

`Research Drift Gate` 用于处理实施阶段中新出现、且已批准计划没有覆盖的不确定事实。命中时不能静默继续，也不能把新假设写成已确认结论。

触发条件：

- 实施中发现计划未覆盖的框架、API、协议、工具、模型、依赖版本或外部服务行为。
- 验证命令、浏览器行为、平台差异或第三方文档与计划假设不一致。
- 必须使用在线、官方、一手或用户私有资料才能确认的关键事实。
- 新事实可能影响 approved scope、阶段边界、风险等级、验证策略、工具授权、兼容性或提交策略。

处理规则：

1. 暂停当前修改动作，记录 finding、来源、影响和当前阶段。
2. 如果能在批准范围内通过本地代码、官方文档或一手资料补证据，更新 `Research Gate`、`Validation Evidence`、`Implementation Progress` 或 artifacts，并重新运行相关验证。
3. 如果补证据会改变 approved scope、阶段边界、必需验证、风险、工具授权、公共接口、依赖或兼容性假设，进入 `Plan Amendment Gate`，请求用户重新批准。
4. 如果资料不可访问，记录为 `blocked-by-access` 或 blocking decision；不得凭记忆继续。
5. 处理结果必须写入 ledger，可用 `review_finding`、`blocked`、`amendment_requested` 或 `note` 事件。

## Development Quality Check

`Development Quality Check` 用于把 planner 阶段的 standards index 和开发质量门禁真正用于实现阶段。

每个阶段必须复核：

- standards index：本阶段涉及的语言、框架、API、架构、设计模式或安全规范是否已读取；没有适用规范时必须说明原因。
- 代码标准：命名、格式、注释、错误处理、日志、配置、测试风格是否符合项目规则和本阶段范围。
- 静态质量：format、lint、typecheck、build、单测或等价验证是否已映射到 `Validation Evidence`；无法执行时必须记录原因、影响和替代证据。
- 架构边界：模块职责、依赖方向、公共接口、数据所有权、兼容性和迁移边界是否被保持。
- 设计模式取舍：新增抽象、复用模式或拒绝复杂模式的原因是否与计划一致。
- 低耦合高内聚：是否引入跨层调用、循环依赖、共享状态膨胀、重复抽象、过宽接口或职责漂移。

记录要求：

- finding 写入 `Code Review`，质量维度可使用 standards、static quality、architecture、pattern、coupling、cohesion 或 validation。
- 阻塞或 major finding 必须在当前阶段关闭；如果需要改变批准范围、公共接口或验证策略，进入 `Plan Amendment Gate`。
- 最终交付前必须能在计划中看到 standards index 引用、开发质量检查结论和对应验证证据。

## 阶段退出和转移

Stage Exit Gate 通过前不能进入下一阶段或最终交付。必须检查：

- 阶段目标已经完成，且没有超出阶段契约。
- code review 已完成，blocking 和 major finding 已关闭。
- Development Quality Check 已完成，standards index、架构边界和静态质量证据已记录。
- 必需验证已执行；无法执行时已记录原因、影响和替代证据。
- 明显缺陷已修复，并已重复必要 review 和验证。
- 长期进程均已通过 `process-manager` 记录 ready/log/status/stop 证据，或已明确记录本阶段不涉及长期进程。
- `execution-plan.md`、changelog 或等价变更记录、`Commit Log` 已更新。
- 如阶段提交已授权，已完成提交并记录 commit hash；未提交时已说明原因。

Stage Transition Gate 在每个阶段退出后立即执行。通过前不能最终回复。

如果还有 pending stage、没有停止条件、也不需要重新批准，下一动作必须是 `continue Stage N`。可以发送简短进度更新，但不能发送最终回复并停止。进入下一阶段前必须同步：

- `Execution Control`
- `Resume Summary`
- `.harness/active-task.json`

建议在阶段转移前运行：

```text
python skills/complex-coding-executor/scripts/harness_exec_check.py --workspace <workspace> --task-dir <task-dir> --mode transition
```

只有 `pending stage = no` 时，才能进入最终交付门禁。

## 验证和审查

验证规则：

- 前端交互工作必须使用环境清单指定的浏览器验证工具。如果要求 Chrome DevTools MCP，必须用它检查 UI、console、network 和必要截图。
- 后端工作必须包含相关单元测试；API 变更还需要接口 smoke 或契约检查。
- Python 工作必须使用配置的 conda、venv、解释器或包管理器。
- 每轮大修改必须运行配置的 smoke 检查。
- 如果某项验证无法执行，必须记录原因、影响和替代证据，不能声称通过。
- 验证证据必须写入 `execution-plan.md`，包括命令或工具、结果、覆盖范围、未覆盖范围和 artifact。

`Code Review` 严重程度：

- `blocking`：不修复不能继续当前阶段。
- `major`：必须修复；如果不修复，必须重新请求用户批准。
- `minor`：可在不改变方案方向时自修；不修复时必须说明影响。
- `follow-up`：不影响当前验收，但必须记录后续建议。

`Code Review` 还必须记录质量维度：

- `standards`：是否遵守 standards index 或项目内开发规则。
- `static quality`：format、lint、typecheck、build、单测或等价检查。
- `architecture`：模块职责、依赖方向、公共接口、数据所有权和兼容性。
- `pattern`：设计模式取舍、新抽象必要性和过度设计风险。
- `coupling` / `cohesion`：耦合、内聚、循环依赖、共享状态和职责漂移。
- `validation`：验证证据、未覆盖范围和替代证据。

验证失败时不能提交或进入下一阶段。必须修复并重复必要验证，或记录阻塞并停止。

## 错误恢复协议

失败动作必须记录：

- command/tool
- attempt number
- failure reason
- impact
- next strategy

同一失败原因不得静默重复第三次。第三次前必须改变策略，例如缩小命令范围、改用 fixture、补读上下文、降级为替代验证或进入 blocking 状态。

记录位置优先级：

1. `execution-plan.md` 的 Validation Evidence、Code Review、Implementation Progress 或 Resume Summary。
2. ledger 的 `validation_failed`、`review_finding`、`blocked` 或 `note` 事件。
3. 大段日志放入 task artifacts，并在计划中引用摘要。

## Topic Handoff Protocol

当某个子主题包含较长研究、运行状态、跨阶段风险或需要下一轮快速接手时，写入：

```text
.harness/tasks/<date>/<type>/<task-slug>/artifacts/handoffs/<topic>.md
```

handoff 至少包含：

- 当前状态。
- 如何检查。
- 已修改内容。
- 分支、提交或 PR 状态。
- 剩余风险。
- 下一步建议。

`Implementation Progress` 必须把 handoff 文件作为索引记录，避免交接信息只留在对话中。

## 长期进程

如果当前会话可用 skill 列表中存在 `process-manager`，所有服务、后台和需要挂起运行的长期进程都必须由 `process-manager` 管理。

长期进程包括：

- 前端 dev server，例如 `pnpm dev`、`npm run dev`、`vite`。
- 后端 web/API 服务，例如 Go、Python、Node、Java 的本地服务。
- worker、watcher、队列消费者、模型服务、文件监听器。
- 任何启动后不会马上返回、需要持续占用终端或端口的进程。

finite command 不进入 `process-manager`：

- 单元测试、集成测试、lint、format、build。
- 数据迁移、代码生成、一次性脚本。
- 任何预期马上返回标准输出结果的命令。

需要长期进程时必须：

1. 读取 `process-manager` 的 `SKILL.md` 和 `references/workflow.md`。
2. 运行 `pm_health.py`；manager 离线时停止长期进程操作，请求用户手动启动或授权 bootstrap。
3. 准备或更新 service config 后运行 `pm_validate.py`。
4. 使用 `pm_start.py` 启动。
5. 使用 `pm_ready.py` 或 `pm_status.py` 判断可用。
6. 使用 `pm_logs.py` 采集日志证据。
7. 使用 `pm_stop.py` 或 `pm_restart.py` 清理或重启。

禁止手写 `Start-Process`、`cmd /c start`、`powershell -Command`、`nohup`、`&` 或自制后台 launcher 作为替代。

每阶段退出前必须把关键日志摘要、ready/status 结果、processKey、截图或 trace 写入 `execution-plan.md` 或任务 artifacts。不要只引用可能被 prune 的 runDir。

## Git

同一仓库、同一 working tree 内，所有 Git 命令必须串行执行。禁止通过任何 agent 并发工具、子 agent、后台任务、多 shell、脚本并发任务或自定义调度同时运行多个同仓库 Git 命令。

只读状态检查优先使用：

```text
git --no-optional-locks status --short --branch
```

diff 类检查优先禁用自动刷新 index：

```text
git -c diff.autoRefreshIndex=false diff --check
git -c diff.autoRefreshIndex=false diff <range>
```

提交、切换分支或最终交付前如果需要精确工作区状态，可以在确认无其它 Git 命令运行后，串行执行普通 `git status --short --branch`。

遇到 `index.lock` 时：

1. 停止继续运行其它 Git 命令。
2. 串行执行 `git rev-parse --git-path index.lock`，获取精确 lock 路径。
3. 确认目标路径是单个精确 `index.lock` 文件。
4. 检查 lock 文件存在、大小和 mtime；短暂等待后复查，确认文件状态稳定。
5. 检查是否存在活跃 `git` / `git.exe` 进程。若存在当前仓库相关 Git 进程，或存在无法判断归属的未知 Git 进程，不得删除 lock。
6. 确认无活跃 Git 进程且 lock 文件稳定后，只删除第 2 步解析出的精确 lock 文件。
7. 删除后立即串行执行 `git --no-optional-locks status --short --branch`。
8. 将恢复动作写入 `Git Lock Recovery Log`。

禁止通配符、递归删除或删除其它 `.lock` 文件。

如果多个 agent 或脚本需要并行处理同一个仓库，优先使用独立 `git worktree`；不要在同一个 working tree 内并发运行 Git。

## 提交和 Changelog

只有用户明确批准，或已批准方案明确要求阶段提交时，才能提交。用户批准实施不等于批准提交。

默认提交信息格式：

```text
feat(scope): 标题

- 重点一
- 重点二
- 重点三
```

标题和分列之间保留一个空行；分列之间不加空行。

禁止使用多个 `-m` 分别传入每条 bullet。首选方式是把完整提交信息写入临时文件，然后使用：

```text
git commit -F <commit-message-file>
```

提交信息临时文件应放在 `.harness/tasks/<date>/<task-slug>/tmp/commit-message.txt` 或等价的 ignored 运行时目录。

提交前必须检查：

- 标题后正好一个空行。
- bullet 行之间没有空行。
- 没有尾随空格。
- scope、标题和 bullet 与本阶段改动一致。

`Commit Log` 必须记录仓库、commit hash、commit message、对应阶段和 changelog 记录。未提交时必须记录原因。

## 最终交付门禁

managed 任务结束前必须完成最终交付门禁：

1. 重读 `.harness/active-task.json`、`.harness/environment.md`、`execution-plan.md`、changelog 和 git 状态。
2. 确认每个阶段都有 review、验证、缺陷处理、文档更新和提交记录。
3. 确认每个阶段的 Development Quality Check 已引用 standards index，并覆盖代码标准、静态质量、架构边界、模式取舍、耦合/内聚和验证证据。
4. 汇总已执行验证；不能把未执行验证写成通过。
5. 汇总未覆盖范围、失败项、剩余风险和后续建议。
6. 汇总 branch status：当前分支、主分支、是否已合回主分支、未合回时代码停留在哪个 harness 分支。
7. 汇总 commit hash、commit message、changelog 记录和关键文件。
8. 前端、UI、可视化、图表、地图、canvas、图片处理、报告预览或浏览器流程任务，必须提供截图、日志、trace、报告或替代证据。
9. 将最终结论写入 `execution-plan.md` 的 `Validation`、`Implementation Progress`、`Code Review` 和 `Commit Log`。
10. 最终结论还必须更新 `Ledger Evidence`、`Resume Packet` 和 `.harness/active-task.json`。
11. 最终回复必须携带任务结论、核心改动、验证结果、未覆盖范围、code review 结论、branch status、commit 信息、关键证据和剩余风险。

建议最终回复前运行：

```text
python skills/complex-coding-executor/scripts/harness_exec_check.py --workspace <workspace> --task-dir <task-dir> --mode final
```

## 恢复流程

上下文压缩或中断后：

1. 读取 `.harness/active-task.json`。
2. 读取 `pending-decisions.md`（如存在）。
3. 读取当前 `execution-plan.md`。
4. 读取 `.harness/environment.md`。
5. 复查 `Process Manager Gate` 和 `Resume Summary` 的长期进程规则状态。
6. 检查 `Git Context`、实际文件和 git 状态。
7. 读取 `Execution Control`、`Stage Transition Gate` 和 `Resume Summary`，确认整体剩余阶段。
8. 读取 `Execution Contract`、`Ledger Evidence` 和 `Resume Packet`。
9. 运行 status/loop-tick，确认当前阶段、剩余阶段、阻塞原因和下一动作。
10. 如果 `execution_mode = run-to-completion` 且没有停止条件，继续 `next_automatic_action`，不要重新开任务，也不要只完成局部恢复点后停止。

## 故障排查

详细流程见 `references/troubleshooting.md`。遇到 wrong task dir、stale active-task、missing ledger、attestation mismatch、`HARNESS_DISABLED`、Windows 路径或 hook advisory 行为时，先按该文档定位，再决定是否继续、修正状态或进入 Plan Amendment Gate。

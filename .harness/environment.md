# Workspace 环境清单（Workspace Environment）

## 来源（Sources）

- 用户会话：当前任务要求新增面向 GitLab 的 skill，使用 GitLab 个人访问令牌和 skill 专属环境变量 `SKILL_GITLAB_BASE_URL`、`SKILL_GITLAB_PAT` 调用 GitLab REST API，覆盖仓库访问/搜索、issue 搜索与详情、评论解析与回复、项目创建和合并请求创建；方案已获批准并按 `complex-coding-executor` 完成实施、验证和记录。
- 用户会话：用户确认 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT` 已配置；实现阶段已基于这些变量完成安全 live read smoke，并仅在 GitLab 测试仓库 `Countra/codex_test` 执行一条带标记的 issue 评论写入 smoke，未执行危险命令测试。
- 用户会话：当前任务补充要求 planner 在规划阶段主动搜索语言规范、框架工程结构、API/架构设计规范、设计模式和 SOLID 等资料；示例来源包括 Google styleguide、Google Cloud API Design Guide 和 AIP design patterns，方案需新增规范收集阶段并可将索引/摘要沉淀到 `.harness` artifacts。
- 用户会话：当前任务要求按 `complex-coding-planner` 规则，为 planner/executor 补强代码标准、语法规范、架构设计、设计模式取舍、低耦合和高内聚等开发侧规则；方案已落盘到 `.harness/tasks/2026-07-08/feature/complex-coding-development-quality-gate/execution-plan.md`，当前等待用户审批。
- 用户会话：当前任务要求强化 `complex-coding-planner` 对不确定问题的深入调研和在线资源搜索机制，方案已在 `.harness/tasks/2026-07-08/feature/planner-research-gate-optimization/execution-plan.md` 获批并进入实施；后续执行按 `complex-coding-executor` 约束推进。
- 用户会话：当前任务要求吸收 `D:\Item\vibe_coding\Ref\planning-with-files` 的优秀流程机制，优化当前 `dev-skills` 中 `complex-coding-planner` 和 `complex-coding-executor`；方案已在 `.harness/tasks/2026-07-08/feature/planning-with-files-skill-optimization/execution-plan.md` 获批并进入实施。
- 用户会话：当前任务要求整合并落盘 `process-manager` skill 实施方案，先支持 Windows 平台、cmd-file 和 powershell-file，所有可执行程序和脚本路径必须使用绝对路径；process-manager 必须是通用长期后台进程管理，不限定为 Web 服务管理。
- 用户会话：当前任务要求为 `process-manager` 的进程历史记录、`runs/` 同步清理、`pm_list` 默认输出和相关 skill 规则调整制定 harness 方案，并判断 `complex-coding-harness` 是否需要联动更新。
- 用户会话：当前任务要求分析 `complex-coding-harness` 在阶段边界提前停止的问题，并用 harness 方式落盘最终详细修改方案；本阶段只规划，不修改 skill 本体。
- 用户会话：当前任务要求为 `complex-coding-harness` 增加独立的规划自查模块；方案已获用户批准并按 `run-to-completion` 完成实施、验证和记录。
- 用户会话：当前任务要求为 `complex-coding-harness` 增加分段 patch 写入策略，约束所有大段落盘写文件动作；方案已获用户确认并进入实施。
- 用户会话：当前任务要求为 `complex-coding-harness` 增加 Git 串行和 `index.lock` 恢复规则；当前已完成最终修改方案，等待用户批准实施。
- 历史本地参考：`E:\work\hl\videoForensic\AI\tmp\process_manager`，包含 prototype 的 `server.py`、`client.py`、`start-manager.ps1`、`stop-manager.ps1`、`state/processes.json`。
- 当前仓库：`D:\Item\vibe_coding\dev-skills`，用于沉淀 skill 源码。
- 当前参考仓库：`D:\Item\vibe_coding\Ref\planning-with-files`，用于本任务研究 planning-with-files 的文件化规划、loop、gate、ledger、attestation、status 和 troubleshooting 机制。
- `docs/development.md`：当前仓库未发现该文件。

## Git

主分支（Main branch）:

- main

Harness 分支策略（Harness branch policy）:

- feature: harness/feature
- fix: harness/fix
- refactor: harness/refactor
- docs: harness/docs
- test: harness/test
- chore: harness/chore

合并策略（Merge policy）:

- 开始实施前，将主分支最新代码合入 harness 工作分支。
- 每个阶段提交前，检查是否需要再次同步主分支。
- 默认使用 merge，不默认 rebase。
- 不自动 stash、reset、覆盖用户改动或删除分支。

当前状态（Current status）:

- 最近一次 Git 检查使用一次性 `safe.directory` 参数，观察到当前分支为 `harness/feature`。
- 当前仓库存在 ignored 的旧 `.harness/tasks/2026-06-11/` 运行产物和 `skills/complex-coding-harness/scripts/` 产物；本任务不清理、不提交这些历史 ignored 文件。
- 本任务是 feature 类型，当前使用 `harness/feature`。
- 当前 active managed 任务为 `gitlab-skill-development`，状态为 `complete`；用户已批准按 `complex-coding-executor` 执行并授权使用 `git commit -F` 提交。
- 从本任务起，同一仓库 Git 命令串行执行，不和其它 Git 命令放入并发批次。
- 当前 Git 只读状态可使用 `git --no-optional-locks status --short --branch`；若遇到 ownership 保护，优先使用一次性 `safe.directory` 参数，不自动写入全局配置。

## 项目（Projects）

### dev-skills

路径（Path）:

- 当前 workspace root（`.`）

类型（Type）:

- Codex skill 源码仓库。

语言（Language）:

- Markdown、YAML、JSONL、Shell、Python。

运行时（Runtime）:

- 本任务新增脚本型 `gitlab-pat-ops` skill，用 Python 标准库脚本调用 GitLab REST API；不需要长期后台服务。

包管理器（Package manager）:

- 无。

虚拟环境（Virtual environment）:

- 无固定虚拟环境；脚本必须使用当前可用 Python。

命令（Commands）:

- JSON 检查：解析 `.harness/active-task.json`
- Planner 检查：`python skills/complex-coding-planner/scripts/harness_plan_check.py --plan <execution-plan.md>`
- 当前 GitLab PAT Ops 方案检查：`python skills/complex-coding-planner/scripts/harness_plan_check.py --plan .harness/tasks/2026-07-09/feature/gitlab-skill-development/execution-plan.md`
- Planner 模板结构检查：`python skills/complex-coding-planner/scripts/harness_plan_check.py --plan skills/complex-coding-planner/templates/execution-plan.md --allow-template`
- Executor 检查：`python skills/complex-coding-executor/scripts/harness_exec_check.py --workspace . --task-dir <task-dir> --mode preflight|transition|final|status`
- Python 检查：`python -m py_compile <script.py>`
- JSONL 检查：解析 `evals/complex-coding-planner/prompts.jsonl` 和 `evals/complex-coding-executor/prompts.jsonl` 并检查 id 唯一
- 关键规则检索：检索 `Research Gate`、`Research Drift Gate`、`Execution Contract`、`Plan Amendment Gate`、`ledger`、`attestation`、`HARNESS_DISABLED`、`Goal Condition`、`loop_tick`、`Topic Handoff`
- 文档检查：`git -c diff.autoRefreshIndex=false diff --check`

验证工具（Validation tools）:

- CLI: PowerShell、Git、rg、Python。
- 浏览器/MCP: 本任务不需要。
- 外部服务: 不需要。

Runtime Services:

| Service | Project | Mode | Endpoint | Readiness | Logs | Stop policy |
| --- | --- | --- | --- | --- | --- | --- |
| none | dev-skills | not required | none | none | none | 本任务不启动长期后台服务 |

产物策略（Artifact policy）:

- `.harness/tasks/**/tmp/`、`.harness/tasks/**/logs/`、`.harness/process-manager/logs/`、`.harness/process-manager/runs/`、`.harness/process-manager/tmp/`、`.harness/process-manager/processes.json`、`.harness/process-manager/token`、`.harness/process-manager/manager.pid` 默认忽略。
- `.harness/tasks/**/ledger*.jsonl`、`.harness/tasks/**/attestation*.json`、`.harness/tasks/**/status*.json`、`.harness/sessions/` 默认作为运行时状态处理，除非任务计划明确要求提交。
- 只有用户确认后才提交 runtime artifact。

规则（Rules）:

- 当前 GitLab PAT Ops skill 任务已完成实现；executor 已按批准方案修改 `skills/gitlab-pat-ops`、`evals/gitlab-pat-ops`、README、CHANGELOG 和 `.harness` 任务记录。
- GitLab PAT Ops skill 规划采用 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT` 作为主环境变量，并兼容同前缀别名 `SKILL_GITLAB_TOKEN`；缺少变量时未来 `gl_doctor.py` 必须提示用户设置，不得泄露 token。
- 用户声明当前环境已配置 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT`；implementation live read smoke 已通过 `/user`、项目搜索/详情、issue、notes 和 search 只读检查。
- GitLab live 写入测试仅限 `codex_test` 测试仓库；本任务已在 `Countra/codex_test` issue 1 创建 note id `3539465182`，禁止删除、关闭、合并、force、权限变更、token 管理、批量修改或跨仓库写入测试。
- Git 命令必须串行；只读 status 优先 `--no-optional-locks`，diff 检查优先 `diff.autoRefreshIndex=false`。
- 本任务不需要长期后台服务；验证命令均为 finite command，不进入 process-manager。
- 如果后续临时出现必须启动的长期服务，仍按 `complex-coding-executor` 的 `Process Manager Gate` 使用 process-manager，不手写后台 shell 启动。
- `execution-plan.md` 是当前任务唯一主契约；`.harness/active-task.json` 只作为恢复入口和摘要索引，二者冲突时以 `execution-plan.md` 为准。
- 当前任务引入 Research Gate：可变事实、外部 API、工具、模型、依赖或高风险事实默认优先查官方或一手资料；无法访问时必须记录为 `blocked-by-access`、assumption 或 blocking 决策。
- 当前任务已引入 Standards Discovery Gate：managed 任务应先识别语言、技术栈、框架、API 类型和架构风险，再搜索官方/一手或高质量规范来源，形成 standards index。
- 当前任务已引入 Development Quality Gate：managed 任务应基于 standards index 显式记录代码标准、静态质量、架构边界、模式取舍、耦合/内聚和质量验证映射。

待确认问题（Open questions）:

- 无 blocking 问题；本任务已按用户批准范围完成。

冲突（Conflicts）:

- 之前 `runtime_process.py` launcher 路线已被用户回退并确认不稳定；本任务不恢复旧 launcher 设计。

# Workspace 环境清单（Workspace Environment）

## 来源（Sources）

- 用户会话：当前任务要求整合并落盘 `process-manager` skill 实施方案，先支持 Windows 平台、cmd-file 和 powershell-file，所有可执行程序和脚本路径必须使用绝对路径；process-manager 必须是通用长期后台进程管理，不限定为 Web 服务管理。
- 用户会话：当前任务要求为 `process-manager` 的进程历史记录、`runs/` 同步清理、`pm_list` 默认输出和相关 skill 规则调整制定 harness 方案，并判断 `complex-coding-harness` 是否需要联动更新。
- 用户会话：当前任务要求分析 `complex-coding-harness` 在阶段边界提前停止的问题，并用 harness 方式落盘最终详细修改方案；本阶段只规划，不修改 skill 本体。
- 用户会话：当前任务要求为 `complex-coding-harness` 增加独立的规划自查模块；方案已获用户批准并按 `run-to-completion` 完成实施、验证和记录。
- 用户会话：当前任务要求为 `complex-coding-harness` 增加分段 patch 写入策略，约束所有大段落盘写文件动作；方案已获用户确认并进入实施。
- 本地参考：`E:\work\hl\videoForensic\AI\tmp\process_manager`，包含 prototype 的 `server.py`、`client.py`、`start-manager.ps1`、`stop-manager.ps1`、`state/processes.json`。
- 当前仓库：`E:\work\hl\videoForensic\AI\dev-skills`，用于沉淀 skill 源码。
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
- 当前任务为 `complex-coding-harness` 分段 patch 写入策略，状态为实施验证收口；已按用户批准范围修改 skill 本体、模板和 eval。
- 当前任务规划已恢复为单一 `execution-plan.md`，不保留临时 numbered planning files。
- 当前 Git 命令存在 ownership 保护：普通 `git status` 报 `detected dubious ownership`。本次校验使用一次性参数 `git -c safe.directory=E:/work/hl/videoForensic/AI/dev-skills ...`，后续提交前需要继续使用该参数，或由用户确认是否写入全局 `safe.directory`。

## 项目（Projects）

### dev-skills

路径（Path）:

- 当前 workspace root（`.`）

类型（Type）:

- Codex skill 源码仓库。

语言（Language）:

- Markdown、YAML、JSONL、Shell、Python。

运行时（Runtime）:

- 本任务已完成 `complex-coding-harness` 分段 patch 写入策略的规则、模板和 eval 更新。

包管理器（Package manager）:

- 无。

虚拟环境（Virtual environment）:

- 无固定虚拟环境；脚本必须使用当前可用 Python。

命令（Commands）:

- JSON 检查：解析 `.harness/active-task.json`
- Skill 验证：`quick_validate.py skills/complex-coding-harness`
- JSONL 检查：解析 `evals/complex-coding-harness/prompts.jsonl` 并检查 id 唯一
- 关键规则检索：`rg "分段 patch|File Write Strategy|单次 apply_patch|120 行|200 行|300 行|500 行|segmented-patch" skills/complex-coding-harness evals/complex-coding-harness`
- 文档检查：`git diff --check`

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
- 只有用户确认后才提交 runtime artifact。

规则（Rules）:

- 本任务已批准并完成修改范围：`skills/complex-coding-harness/SKILL.md`、`references/workflow.md`、`templates/execution-plan.md`、`evals/complex-coding-harness/prompts.jsonl`、harness 任务记录和 `CHANGELOG.md`。
- 本任务不需要长期后台服务；验证命令均为 finite command，不进入 process-manager。
- 如果后续临时出现必须启动的长期服务，仍按 `complex-coding-harness` 的长期进程门禁使用 process-manager，不手写后台 shell 启动。
- `execution-plan.md` 是当前任务唯一主契约；`.harness/active-task.json` 只作为恢复入口和摘要索引，二者冲突时以 `execution-plan.md` 为准。

待确认问题（Open questions）:

- 无 blocking 问题；本任务已按用户批准范围完成。

冲突（Conflicts）:

- 之前 `runtime_process.py` launcher 路线已被用户回退并确认不稳定；本任务不恢复旧 launcher 设计。

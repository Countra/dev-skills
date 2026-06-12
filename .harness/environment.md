# Workspace 环境清单（Workspace Environment）

## 来源（Sources）

- 用户会话：当前任务要求整合并落盘 `process-manager` skill 实施方案，先支持 Windows 平台、cmd-file 和 powershell-file，所有可执行程序和脚本路径必须使用绝对路径；process-manager 必须是通用长期后台进程管理，不限定为 Web 服务管理。
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

- 当前分支：`harness/feature`。
- 当前仓库存在 ignored 的旧 `.harness/tasks/2026-06-11/` 运行产物和 `skills/complex-coding-harness/scripts/` 产物；本任务不清理、不提交这些历史 ignored 文件。
- 本任务是 feature 类型，继续使用 `harness/feature`。
- 本次用户要求先落盘方案，不要求提交；后续实现前再按 Git Context 检查是否需要同步 `main`。
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

- 本任务将新增 Python 标准库脚本和 Windows PowerShell bootstrap 脚本。

包管理器（Package manager）:

- 无。

虚拟环境（Virtual environment）:

- 无固定虚拟环境；脚本必须使用当前可用 Python。

命令（Commands）:

- Skill 验证：`python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/process-manager`
- Python 语法：`python -m py_compile <script>`
- 文档检查：`git diff --check`
- JSON 检查：`python -c "import json; ..."`

验证工具（Validation tools）:

- CLI: PowerShell、Git、rg、Python。
- 浏览器/MCP: 本任务不需要。
- 外部服务: 不需要。

Runtime Services:

| Service | Project | Mode | Endpoint | Readiness | Logs | Stop policy |
| --- | --- | --- | --- | --- | --- | --- |
| process-manager prototype | external reference only | not started by this plan | `127.0.0.1:49321` | `/health` | external reference logs | 不由本规划阶段启动或停止 |

产物策略（Artifact policy）:

- `.harness/tasks/**/tmp/`、`.harness/tasks/**/logs/`、`.harness/process-manager/logs/`、`.harness/process-manager/runs/`、`.harness/process-manager/tmp/`、`.harness/process-manager/processes.json`、`.harness/process-manager/token`、`.harness/process-manager/manager.pid` 默认忽略。
- 只有用户确认后才提交 runtime artifact。

规则（Rules）:

- 本规划阶段不实现 skill，不启动 manager，不启动真实业务服务。
- 后续实现阶段第一版仅支持 Windows。
- 长期后台进程必须通过 process-manager skill 的脚手架脚本管理，不直接运行 `pnpm dev`、`go run`、`python app.py`、`uvicorn`、`Start-Process`、`nohup` 或自由 shell 长命令。
- finite command，例如测试、构建、lint、一次性脚本，不进入 process-manager。
- 服务配置中的 `cwd`、`direct.argv[0]`、`cmd-file.script`、`powershell-file.script` 和所有代表文件/目录的参数必须解析为绝对路径。
- 第一版支持 `direct`、`cmd-file`、`powershell-file`；不支持 `cmd-command`、`powershell-command`、Linux/macOS、Docker compose、systemd。
- 服务配置顶层不要求 `host` 和 `port`；端口只属于 Web/TCP readiness 或用户传给业务进程的启动参数。
- manager 启动业务进程默认隐藏窗口，stdout/stderr 写入日志文件，不弹出 cmd 或 PowerShell 终端窗口。
- manager 自身 bootstrap 只允许用户手动执行或用户明确授权执行；agent 每轮优先 `pm_health.py` 检查，不自动手写后台启动 manager。

待确认问题（Open questions）:

- 无 blocking 问题；本计划等待用户批准后进入实现。

冲突（Conflicts）:

- 之前 `runtime_process.py` launcher 路线已被用户回退并确认不稳定；本任务不恢复旧 launcher 设计。

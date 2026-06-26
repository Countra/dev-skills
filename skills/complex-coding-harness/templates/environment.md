# Workspace 环境清单（Workspace Environment）

## 来源（Sources）

- `docs/development.md`：
- 项目配置文件：
- 用户会话：

## Git

主分支（Main branch）:

- <dev/main/master; 用户确认或探测结果>

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

主分支探测（Main branch detection）:

- dev -> main -> master -> origin/HEAD

Git 命令串行化（Git command serialization）:

- 同一仓库、同一 working tree 内所有 Git 命令必须串行执行。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git。
- 非 Git 文件读取、文本搜索和普通测试命令可以并发，但不能和 Git 命令混在同一并发批次。

只读 Git 默认选项（Read-only Git defaults）:

- 状态检查优先：`git --no-optional-locks status --short --branch`
- diff 检查优先：`git -c diff.autoRefreshIndex=false diff <range>`
- 最终提交前需要精确状态时，可在确认无其它 Git 命令运行后串行执行普通 `git status --short --branch`。

Index lock 恢复策略（Index lock recovery policy）:

- 使用 `git rev-parse --git-path index.lock` 解析当前仓库或 worktree 的精确 lock 路径。
- 删除前必须检查 lock 文件存在、大小/mtime 稳定，并确认无活跃或未知归属 Git 进程。
- 只允许删除解析出的精确 `index.lock`；禁止通配符、递归删除或删除其它 `.lock` 文件。
- 删除后必须立即串行执行 `git --no-optional-locks status --short --branch`，并记录恢复结果。

Git 待确认问题（Git open questions）:

-

## 项目（Projects）

### <项目名称（project-name）>

路径（Path）:

类型（Type）:

语言（Language）:

运行时（Runtime）:

包管理器（Package manager）:

虚拟环境（Virtual environment）:

命令（Commands）:

- 安装（Install）:
- 开发服务（Dev server）:
- 单元测试（Unit tests）:
- 集成/API 测试（Integration/API tests）:
- Lint/typecheck:
- 构建（Build）:
- 冒烟测试（Smoke）:

验证工具（Validation tools）:

- 浏览器/MCP（Browser/MCP）:
- CLI:
- 外部服务（External service）:
- 截图（Screenshot）:
- 浏览器日志（Browser logs）:
- 网络日志（Network logs）:
- 测试报告（Test reports）:
- 覆盖率报告（Coverage reports）:

产物策略（Artifact policy）:

- 运行产物（Runtime artifacts）: `.harness/tasks/**/artifacts/`
- 只有用户确认后才提交 artifact（Commit artifacts only with user confirmation）。

规则（Rules）:

- 

待确认问题（Open questions）:

- 

冲突（Conflicts）:

- 

## 用户覆盖项（User Overrides）

- 

## 说明（Notes）

- 不要在这里保存密钥、私有 token、个人绝对路径或机器本地覆盖项。
- 个人机器覆盖项写入 `.harness/environment.local.md`，并保持忽略。

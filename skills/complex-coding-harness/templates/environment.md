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

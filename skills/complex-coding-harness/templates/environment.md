# Workspace Environment

## Sources

- `docs/development.md`：
- 项目配置文件：
- 用户会话：

## Git

Main branch:

- <dev/main/master; 用户确认或探测结果>

Harness branch policy:

- feature: harness/feature
- fix: harness/fix
- refactor: harness/refactor
- docs: harness/docs
- test: harness/test
- chore: harness/chore

Merge policy:

- 开始实施前，将主分支最新代码合入 harness 工作分支。
- 每个阶段提交前，检查是否需要再次同步主分支。
- 默认使用 merge，不默认 rebase。
- 不自动 stash、reset、覆盖用户改动或删除分支。

Main branch detection:

- dev -> main -> master -> origin/HEAD

Git open questions:

-

## Projects

### <project-name>

Path:

Type:

Language:

Runtime:

Package manager:

Virtual environment:

Commands:

- Install:
- Dev server:
- Unit tests:
- Integration/API tests:
- Lint/typecheck:
- Build:
- Smoke:

Validation tools:

- Browser/MCP:
- CLI:
- External service:

Rules:

- 

Open questions:

- 

Conflicts:

- 

## User Overrides

- 

## Notes

- 不要在这里保存密钥、私有 token、个人绝对路径或机器本地覆盖项。
- 个人机器覆盖项写入 `.harness/environment.local.md`，并保持忽略。

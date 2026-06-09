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
8. 完成 `Readiness Gate`。
9. 将状态设为 `awaiting_plan_approval`，请求用户批准方案。
10. 只有用户明确批准后才能实现。
11. 按阶段实施，每阶段完成 review、验证、修复、记录更新和授权提交。
12. 结束时给出最终 review、验证摘要、变更文件和剩余风险。

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

每个已批准阶段都必须执行：

1. 重读 `.harness/active-task.json`、`.harness/environment.md`、`execution-plan.md`、`pending-decisions.md`（如存在）、项目 `docs/development.md` 和 changelog。
2. 更新 `Implementation Progress`，记录当前阶段、范围和下一步。
3. 阅读本阶段相关代码、测试、配置、API 和文档。
4. 在批准范围内做最小必要修改。
5. 修复明显缺陷；小优化只能在不改变方案方向时执行。
6. 如果范围、风险、接口、验证成本或方案方向变化，停止并重新请求用户批准。
7. 做 code review，检查正确性、边界条件、错误处理、兼容性、无关改动、测试和文档。
8. 按 `Validation` 和 `.harness/environment.md` 执行验证。
9. 修复 review 或验证发现的问题，并重复 review 和验证，直到没有 blocking 或 major finding。
10. 更新 changelog 或项目等价变更记录。
11. 只有用户批准的方案授权提交时，才提交代码；提交 hash 写入 `Commit Log`。
12. 进入下一阶段前，重读任务记录和 changelog，确认状态没有丢失。

## 验证规则

- 前端交互工作必须使用环境清单指定的浏览器验证工具。如果要求 Chrome DevTools MCP，必须用它检查 UI、console、network 和必要截图。
- 后端工作必须包含相关单元测试；API 变更还需要接口 smoke 或契约检查。
- Python 工作必须使用配置的 conda、venv、解释器或包管理器。
- 每轮大修改必须运行配置的 smoke 检查。
- 如果某项验证无法执行，必须记录原因、影响和替代证据，不能声称通过。

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
5. 检查实际文件和 git 状态。
6. 继续 `next_action`，不要重新开任务。

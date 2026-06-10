# Execution Plan

## Problem

目标：

- 针对当前 `complex-coding-harness` skill 的可优化项，形成详细分阶段规划文档。
- 规划项覆盖分支收口、eval 覆盖、模板中文化和安装脚本确定性增强。
- 本任务只完成规划，不直接实现优化项。

非目标：

- 不修改 skill 工作流实现文件。
- 不修改模板。
- 不修改安装脚本。
- 不提交实现类改动。

验收标准：

- 新增 `docs/complex-coding-harness-upgrade-plan.md`。
- 文档包含每个优化阶段的目标、做法、原因、修改位置、验证、风险和回滚。
- `.harness/active-task.json` 指向当前规划任务。
- 最终交付说明当前方案需要用户确认后才能进入实现。

## Context

本地代码和文档：

- `skills/complex-coding-harness/SKILL.md`
- `skills/complex-coding-harness/references/workflow.md`
- `skills/complex-coding-harness/templates/environment.md`
- `skills/complex-coding-harness/templates/execution-plan.md`
- `skills/complex-coding-harness/templates/pending-decisions.md`
- `examples/complex-coding-harness/`
- `evals/complex-coding-harness/`
- `skill.sh`
- `docs/complex-coding-harness-skill-plan.md`

用户约束：

- 需要“针对上面的所有优化项”完成详细分阶段规划文档。
- “也按这个规则进行”，即本任务也遵守当前 harness 任务记录、Git Context、验证和最终交付门禁。

## Decision

采用单独升级规划文档：

- 不继续把原始 `docs/complex-coding-harness-skill-plan.md` 撑大。
- 新增 `docs/complex-coding-harness-upgrade-plan.md` 承载后续升级计划。
- 当前任务已获得用户批准，按分阶段规划进入实现。

原因：

- 原始规划文档已经较长。
- 新规划是后续升级路线，不是首版设计本体。
- 单独文档更便于用户审查和批准。

## Implementation Plan

### Stage 1: 落盘升级规划文档

目标：

- 新增详细分阶段规划文档。

怎么做：

- 将四类优化项拆成 4 个实施阶段。
- 每阶段写清目标、做法、原因、具体文件、验证、风险和回滚。
- 明确当前阶段只规划，不实现。

为什么：

- 用户要求先完成详细规划。
- 后续实现前必须有明确批准门禁。

位置：

- `docs/complex-coding-harness-upgrade-plan.md`

验证：

- 检索四类优化项和 4 个阶段。
- 检查文档存在。

风险和回滚：

- 风险：规划过长。
- 回滚：删减非必要背景，保留阶段表和验证策略。

### Stage 2: 更新当前任务状态

目标：

- 让上下文压缩后能恢复本次规划任务。

怎么做：

- 更新 `.harness/active-task.json`。
- 新增当前任务 `execution-plan.md`。

为什么：

- 用户要求按当前 harness 规则执行。

位置：

- `.harness/active-task.json`
- `.harness/tasks/2026-06-10/feature/complex-coding-harness-upgrade-plan/execution-plan.md`

验证：

- `.harness/active-task.json` 可解析。
- 当前任务记录包含 Git Context、验证和 Plan Approval。

风险和回滚：

- 风险：任务记录过多。
- 回滚：保留当前任务记录，后续任务不重复创建。

## Environment

Workspace environment source:

- 当前仓库未配置 `.harness/environment.md`。

This task uses:

- PowerShell。
- `rg`。
- `git`。

Temporary overrides:

- 本任务是文档规划任务，不需要 Python、Node、浏览器、MCP 或外部服务。

## Git Context

Main branch:

- `master`

Task type:

- `feature`

Working branch:

- `harness/feature`

Branch action:

- reuse

Sync source:

- local `master`

Branch occupancy:

- `git log master..HEAD` 显示 `81cbb00 feat(complex-coding-harness): 增强最终交付门禁`。
- 该提交属于同一条 skill 优化链路。
- 本规划任务继续使用 `harness/feature`，但后续实现前必须重新检查分支占用。

Commit policy:

- 用户已要求“每个阶段完成后，审查&验证通过后自动提交代码”。

Branch closure:

- 本规划阶段不合回 `master`。
- 最终交付需要说明代码仍在 `harness/feature`。

## Validation

Required:

- 检查新增规划文档存在。
- 检查规划文档包含四个优化阶段。
- 检查 `.harness/active-task.json` JSON 可解析。
- 执行 `git diff --check`。

Executed:

- `rg` 检索规划关键项：通过，覆盖分支收口、eval、模板中文化、安装脚本、Readiness Gate、Plan Approval、Git Context、Branch occupancy 和 Branch closure。
- `.harness/active-task.json` JSON 解析：通过。
- `git diff --check`：通过。
- Stage 3 `rg` 检索 branch occupancy、branch closure、`git log <main>..HEAD`、`git diff <main>...HEAD --name-only`：通过。
- Stage 4 JSONL 逐行解析和新增 eval id 检索：通过。
- Stage 5 模板中文化残留英文占位检索、JSON 解析和 diff check：通过。
- Stage 6 安装脚本临时目录首次安装、重复安装拒绝、`--force` 替换和目标 `SKILL.md` 校验：通过。
- Stage 6 `sh -n skill.sh` 语法检查：通过。

Artifacts:

- Screenshot: 不适用，本任务无 UI。
- Log: 终端验证输出摘要。
- Report: `docs/complex-coding-harness-upgrade-plan.md`

Not covered:

- 不验证后续优化实现效果。
- 不执行真实安装脚本。

If unable to run:

- 在最终交付中说明未执行原因和影响。

## Documentation

Required updates:

- `docs/complex-coding-harness-upgrade-plan.md`
- `.harness/active-task.json`
- 当前任务 `execution-plan.md`

Changelog plan:

- 当前是规划文档任务；如用户要求提交，可在 `CHANGELOG.md` 记录本规划阶段。

## Readiness Gate

| Check | Status | Evidence |
| --- | --- | --- |
| Goal and acceptance clear | pass | Problem 已记录 |
| Context collected | pass | 已读取 skill、workflow、模板、eval、安装脚本和总规划 |
| Decision recorded | pass | 新增单独升级规划文档 |
| Implementation stages detailed | pass | 升级规划分 4 阶段 |
| Environment confirmed | pass | 文档任务，无运行环境依赖 |
| Git context confirmed | pass | 当前在 `harness/feature`，记录了 `master..HEAD` |
| Validation confirmed | pass | 文档级验证已定义 |
| Final delivery evidence planned | pass | 无 UI，证据为文档和验证输出 |
| Risks identified | pass | 每阶段有风险和回滚 |
| Blocking questions closed | pass | 当前无 blocking 问题 |

Readiness result:

- `pass`

## Plan Approval

Status:

- `approved`

Approval record:

- 用户说：“阶段性完成这个规划吧，也是按规则每个阶段完成后，审查&验证通过后自动提交代码”

Commit policy:

- `stage_commits_authorized`

## Implementation Progress

| Stage | Status | Summary | Validation | Evidence | Next action |
| --- | --- | --- | --- | --- | --- |
| Stage 1 | completed | 已新增升级规划文档 | 文档关键项检索通过 | `docs/complex-coding-harness-upgrade-plan.md` | 阶段 0 提交 |
| Stage 2 | completed | 已更新当前任务状态 | JSON 解析和 diff check 通过 | `.harness/active-task.json` | 阶段 0 提交 |
| Stage 3 | completed | 分支收口和分支占用检查已实现 | 关键文本检索、JSONL、JSON 和 diff check 通过 | workflow、模板、规划和示例 | 阶段 1 提交 |
| Stage 4 | completed | 已补充 eval fixtures | JSONL、关键 id 检索和 diff check 通过 | eval fixtures | 阶段 2 提交 |
| Stage 5 | completed | 模板中文化和术语统一已完成 | 残留英文占位检索、JSON 解析和 diff check 通过 | templates 和 examples | 阶段 3 提交 |
| Stage 6 | completed | 安装脚本确定性增强已完成 | 临时目录安装行为、脚本语法、JSON 和 diff check 通过 | skill.sh、README 和 CHANGELOG | 阶段 4 提交 |

## Code Review

| Stage | Finding | Severity | Resolution |
| --- | --- | --- | --- |
| Stage 1 | 规划文档可能诱导直接实现 | major | 已明确本文档只规划，实现需用户批准 |
| Stage 2 | 当前 `harness/feature` 已有未合回提交 | minor | 已在 Git Context 中记录分支占用 |
| Stage 3 | 分支收口规则可能增加固定分支使用成本 | minor | 仅在存在未合回提交或归属不明时暂停确认 |
| Stage 4 | eval fixtures 可能被误认为自动化测试 | minor | README 已说明这些文件是 prompt fixtures，不是自动判分测试 |
| Stage 5 | 纯中文字段可能影响跨 agent 识别 | minor | 保留中文加英文术语格式 |
| Stage 6 | `--force` 涉及删除目标目录 | major | 只允许删除目标 skills 目录下的 `complex-coding-harness`，并在 README 中明确语义 |

## Commit Log

| Stage | Repository | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Stage 1-2 | `dev-skills` | `2b7160b` | `docs(complex-coding-harness): 规划后续优化阶段` | not updated |
| Stage 3 | `dev-skills` | `9382919` | `feat(complex-coding-harness): 增加分支收口检查` | not updated |
| Stage 4 | `dev-skills` | `1cae648` | `test(complex-coding-harness): 补充工作流评估样例` | not updated |
| Stage 5 | `dev-skills` | `db7872c` | `docs(complex-coding-harness): 统一模板中文术语` | updated in `CHANGELOG.md` |
| Stage 6 | `dev-skills` | `1d25251` | `feat(complex-coding-harness): 增强 skill 安装脚本` | updated in `CHANGELOG.md` |

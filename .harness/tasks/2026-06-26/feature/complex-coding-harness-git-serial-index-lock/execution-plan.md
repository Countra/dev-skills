# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

- 为 `complex-coding-harness` 增加通用 Git 命令串行化规则，避免 agent、脚本、子进程、后台任务、多 shell 或任何并发工具在同一仓库同时运行 Git 命令。
- 增加 `.git/index.lock` / worktree index lock 的安全恢复规则：确认精确 lock 路径、文件状态稳定、无活跃 Git 进程后，只删除当前仓库对应的精确 lock 文件。
- 增加只读 Git 检查建议：优先使用 `--no-optional-locks`，`git diff` 类检查优先禁用 `diff.autoRefreshIndex`。
- 将规则写入 skill、workflow、模板和 eval，确保后续长任务、上下文恢复和不同 agent 工具都能遵守。

非目标（Non-goals）:

- 不改变现有 harness 工作分支策略。
- 不引入新的 Git wrapper 脚本或后台 Git 守护服务。
- 不自动迁移历史 `.harness/tasks/`。
- 不要求所有项目强制使用 `git worktree`；worktree 只作为并行隔离建议。
- 不默认删除所有 `.lock` 文件，也不使用通配符或递归删除。

验收标准（Acceptance）:

- `SKILL.md` 增加核心规则：同一仓库 Git 命令必须串行；遇 index lock 走精确恢复门禁。
- `references/workflow.md` 增加独立章节，覆盖 Git 串行范围、只读命令参数、写操作独占、并发禁止、index lock 恢复、worktree 建议。
- `templates/execution-plan.md` 的 `Git Context` 增加 Git command policy、read-only options、index lock recovery、parallel Git restriction 和 lock recovery log。
- `templates/environment.md` 的 Git 区增加 workspace 级 Git 串行和 index lock 恢复策略。
- `evals/complex-coding-harness/prompts.jsonl` 增加覆盖 Git 并发、可选锁、diff 刷新、stale lock 精确恢复和 worktree 建议的场景。
- 验证通过：skill quick validate、JSONL 解析和 id 唯一性、关键规则检索、`git diff --check`。

约束（Constraints）:

- 本方案本身也遵守 Git 串行规则：同一仓库 Git 命令不放入并发批次。
- 落盘写文件遵守分段 patch 策略；本计划分章节写入。
- 文档规则必须通用，不绑定 Codex 的具体并发工具名称。
- 新增规则保持轻量，不把普通 Git 检查变成复杂审批流程。

待确认项（Open uncertainties）:

- 无 blocking 待确认项。本计划默认 stale index lock 在无活跃 Git 进程且精确路径确认后可由 agent 删除，并记录到任务计划。

## 上下文（Context）

本地代码和文档（Local code/docs）:

- `skills/complex-coding-harness/SKILL.md` 已有 Git Context、工作分支、提交记录、process-manager 和分段 patch 规则，但没有 Git 命令串行化核心规则。
- `skills/complex-coding-harness/references/workflow.md` 已有 `Git 工作分支` 章节，覆盖主分支、harness 分支、同步、热修复插入和 Git Context，但缺少 `index.lock` 恢复流程。
- `skills/complex-coding-harness/templates/execution-plan.md` 已有 `Git Context`，但缺少 Git command policy、read-only options 和 lock recovery log。
- `skills/complex-coding-harness/templates/environment.md` 已有 workspace 级 Git 分支和合并策略，但缺少串行化和 lock 恢复策略。
- 现有 workflow 和模板中已有 `git status --short`、`git diff <main>...HEAD --name-only` 等命令示例；实施时不能只新增规则，还要同步替换或补充这些旧示例的串行/可选锁说明。
- 用户反馈实际遇到 `.git/index.lock` 残留，需要每次手动删除；怀疑来自 agent 自身并发 Git 命令。

外部来源（External sources）:

- Git `status` 官方文档说明 `git status` 默认会刷新 index 并写回磁盘；后台脚本可用 `git --no-optional-locks status` 避免可选锁。
- Git `git` 官方文档说明 `--no-optional-locks` 等价于 `GIT_OPTIONAL_LOCKS=0`。
- Git `config` 官方文档说明 `diff.autoRefreshIndex` 默认为 true，`git diff` 会静默执行 `update-index --refresh` 刷新 stat 信息。
- Git `worktree` 官方文档说明 linked worktree 有自己的 administrative files；并行工作应考虑独立 worktree，而不是同一个 working tree 并发操作。
- Git `rev-parse` 官方文档提供 `--git-path <path>`，用于解析 `$GIT_DIR` 下的真实路径，适合 worktree 场景下定位 `index.lock`。

用户约束（User constraints）:

- 规则必须通用，不能只写 Codex 的 `multi_tool_use.parallel`。
- 可以轻量处理 Codex 自己造成的 stale lock，不需要每次都问用户。
- 删除前必须检查文件大小和 Git 进程，确认无活跃 Git 后只删除当前仓库的精确 lock。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| `git status` 可能刷新并写回 index | external | Git `git-status` 文档 Background Refresh | status 也必须纳入串行和可选锁规则 |
| `--no-optional-locks` 可避免可选锁 | external | Git `git` 文档 | 只读检查应优先使用 |
| `git diff` 默认可能刷新 index | external | Git `git-config` 的 `diff.autoRefreshIndex` | diff 检查应可禁用刷新 |
| worktree 内部 Git 路径不应硬编码 | external | Git `rev-parse --git-path`、`git-worktree` 文档 | lock 路径应用 Git 解析 |
| 当前 skill 缺少 Git 串行和 lock 恢复规则 | read | 本地 `SKILL.md`、`workflow.md`、模板检索 | 需要新增规则和 eval |
| `--no-optional-locks` 是只读脚本优先策略，不等同于最终提交前精确状态刷新 | assumption | Git status 背景刷新说明推导 | 提交前仍需串行普通 status 或等价检查 |

## 根因分析（Root Cause）

### 看似只读的 Git 命令也可能写 index

`git status` 默认刷新 index，`git diff` 默认可能触发 stat refresh。agent 将多个 Git 检查放入同一并发批次时，即使没有显式 `git add`，也可能竞争 `index.lock`。

只读脚本优先用 `--no-optional-locks`，但该模式可能跳过可选刷新。最终提交前若需要最精确的工作区状态，应在确认没有其它 Git 命令运行时串行执行普通 `git status --short --branch` 或等价检查。

### 并发工具是通用风险，不是单一工具问题

Codex 有并发工具，Claude Code、Cursor、自定义脚本或子 agent 也可能有并发执行能力。规则必须描述“同一仓库 Git 命令不得并发”，而不是绑定某个工具名。

### stale lock 恢复缺少安全边界

用户场景中 lock 多半由 agent 自己异常中断遗留，但直接删除仍有风险。最低安全线应包括：精确路径、文件存在和大小/mtime 稳定、无活跃 Git 进程、删除后立即 status。

Git 进程检查应优先判断是否与当前仓库相关。如果只能拿到系统级 `git`/`git.exe` 进程且无法判断归属，应按未知活跃 Git 处理，先等待或停止，不删除 lock。

### worktree 场景不能硬编码 `.git/index.lock`

在 linked worktree 中 `.git` 可能是指向真实 gitdir 的文件。恢复流程应通过 `git rev-parse --git-path index.lock` 获取精确路径，再删除该路径。

## 候选方案（Options）

### 方案 A：只要求 Git 检查串行

做法：

- 在 workflow 增加一句“Git 命令不要并发执行”。

优点：

- 改动最小。

缺点：

- 没有只读命令参数。
- 没有 stale lock 恢复流程。
- 没有模板记录位和 eval，长任务恢复后容易遗忘。

结论：

- 不采用。

### 方案 B：增加 Git 串行规则和自动删除 index.lock

做法：

- 发现 `.git/index.lock` 直接删除后重试。

优点：

- 操作简单，能快速恢复常见 stale lock。

缺点：

- 过于冒进，可能删除活跃 Git 进程正在使用的 lock。
- 没有 worktree 路径解析和文件稳定性检查。

结论：

- 不采用。

### 方案 C：结构化 Git 串行和精确 stale lock 恢复

做法：

- 同一仓库 Git 命令必须串行。
- 只读检查优先使用 `--no-optional-locks`，diff 检查优先禁用 `diff.autoRefreshIndex`。
- 遇 index lock 时，解析精确路径、检查文件状态和 Git 进程、只删除该精确 lock、删除后串行 status。
- 将规则写入 workflow、模板、environment 和 eval。

优点：

- 覆盖真实根因。
- 不绑定具体 agent 工具。
- 恢复流程轻量但有安全边界。
- 对长期任务和上下文恢复友好。

缺点：

- 比一句提醒多一些规则和模板字段。

结论：

- 采用方案 C。

## 决策（Decision）

选择方案（Chosen option）:

- 方案 C：结构化 Git 串行和精确 stale lock 恢复。

原因（Why）:

- 当前问题来自 Git index 锁竞争和异常残留；仅串行不足以覆盖 stale lock 恢复，仅自动删除又不够安全。
- 官方文档说明只读命令也可能触碰 index，必须将 status/diff/log/show 等统一纳入串行规则。
- 规则应对不同 agent 工具通用。

影响（Impact）:

- agent 执行 Git 命令时需要排队。
- 只读检查命令格式会更保守。
- 任务计划和环境模板会多出少量 Git safety 字段。

可逆性（Reversibility）:

- 文档和 eval 规则可通过后续提交调整。
- 不引入脚本或 schema migration，回滚成本低。

方案变更触发条件（Reapproval triggers）:

- 需要引入 Git wrapper 脚本、hook、daemon 或全局 Git 配置。
- 需要默认删除非 `index.lock` 的其它 lock 文件。
- 需要强制使用 `git worktree` 作为默认工作模式。
- 需要修改现有 harness 分支策略或提交策略。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | no | 无 | 无 | 不适用 | 否 |
| 数据结构（Data model） | no | 无 | 无 | JSONL 解析 | 否 |
| 前端交互（Frontend interaction） | no | 无 | 无 | 不适用 | 否 |
| 配置/环境（Config/environment） | yes | `templates/environment.md` | Git 策略字段过多 | 关键文本检索 | 是 |
| 兼容性（Compatibility） | yes | `workflow.md`、模板 | 规则过重或误解为 Codex 专用 | Plan Self-Review、eval | 是 |
| 测试（Tests） | yes | `evals/complex-coding-harness/prompts.jsonl` | JSONL 格式错误或 id 重复 | JSONL parse/id unique | 是 |
| 文档（Documentation） | yes | `SKILL.md`、`workflow.md`、模板、`CHANGELOG.md` | 表述不清导致误用 | quick_validate、rg | 是 |

## 实施计划（Implementation Plan）

### Stage 1：核心规则和 workflow

目标：

- 在 `SKILL.md` 和 `workflow.md` 中加入通用 Git 串行化与 index lock 恢复规则。

做法：

- `SKILL.md` 只加一条核心规则，保持短。
- `workflow.md` 在 `Git 工作分支` 后新增 `Git 命令串行化和 index lock 恢复` 章节。
- 章节覆盖串行范围、只读参数、写操作独占、并发禁止、lock 恢复流程、worktree 建议。
- 同步调整 `Git 工作分支` 中已有命令示例：安全检查类使用串行和 `--no-optional-locks`；diff 检查类补充 `diff.autoRefreshIndex=false`。
- 明确最终提交前允许串行普通 `git status --short --branch` 获取精确状态，但不得并发。

原因：

- `SKILL.md` 用于恢复时快速提醒；详细可执行流程放入 workflow，避免核心文件膨胀。

位置：

- `skills/complex-coding-harness/SKILL.md`
- `skills/complex-coding-harness/references/workflow.md`

验证：

- `rg -n "index.lock|no-optional-locks|diff.autoRefreshIndex|Git 命令.*串行"`。
- 检索 `git status --short`、`git diff <main>` 等旧示例，确认已补充新规则或不再误导。

风险和回滚：

- 风险：规则过重影响普通查询效率。
- 回滚：移除该新增章节和核心规则。

### Stage 2：模板更新

目标：

- 将规则沉淀到任务计划和环境模板，避免上下文压缩后遗忘。

做法：

- `templates/execution-plan.md` 的 `Git Context` 增加：
  - Git command policy
  - Read-only Git options
  - Index lock recovery
  - Parallel Git restriction
  - Git Lock Recovery Log
- `templates/environment.md` 的 Git 区增加 workspace 级策略：
  - Git command serialization
  - Read-only Git defaults
  - Index lock recovery policy
- 同步模板中已有 `git status`、`git diff` 示例，避免模板一边要求串行，一边展示未带规则的旧命令。

原因：

- workflow 是规则来源，模板是每个任务的运行时约束。两者都需要覆盖。

位置：

- `skills/complex-coding-harness/templates/execution-plan.md`
- `skills/complex-coding-harness/templates/environment.md`

验证：

- 关键文本检索。
- 人工复查模板不引入过多字段。
- 检索模板内所有 Git 命令示例，确认只读检查和 diff 检查表达一致。

风险和回滚：

- 风险：模板太重。
- 回滚：保留最关键字段，删除重复说明。

### Stage 3：eval 覆盖

目标：

- 增加 eval 场景，防止后续改动破坏 Git 串行和 stale lock 规则。

新增场景：

- `git-commands-serial-same-repo`
- `git-readonly-uses-optional-locks`
- `git-diff-disables-auto-refresh`
- `git-index-lock-stale-recovery`
- `git-index-lock-no-wildcard-delete`
- `git-parallel-worktree-advice`
- `git-final-status-can-refresh-serially`
- `git-unknown-process-blocks-lock-delete`

位置：

- `evals/complex-coding-harness/prompts.jsonl`

验证：

- JSONL parse 和 id 唯一性。

### Stage 4：记录、验证和提交

目标：

- 完成验证、更新 changelog 和提交。

验证命令：

- `python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\complex-coding-harness`
- JSONL 解析和 id 唯一性检查。
- `rg -n "index.lock|no-optional-locks|diff.autoRefreshIndex|Git 命令.*串行|rev-parse --git-path index.lock" skills\complex-coding-harness evals\complex-coding-harness`
- 检索旧 Git 示例：`rg -n "git status --short|git diff <main>|git log <main>" skills\complex-coding-harness`
- `git -c diff.autoRefreshIndex=false diff --check`

提交：

- 使用 `git commit -F <message-file>`。
- commit message:

```text
docs(complex-coding-harness): 增加 Git 串行和 index.lock 恢复规则

- 约束同一仓库 Git 命令必须串行执行，避免并发竞争 index.lock
- 增加只读 Git 检查的 no-optional-locks 和 diff.autoRefreshIndex 规则
- 补充 stale index.lock 精确恢复流程和 eval 覆盖
```

## 环境（Environment）

Workspace 环境来源：

- `.harness/environment.md`

本任务使用：

- PowerShell
- Python
- rg
- Git

长期进程：

- 不需要。本任务只修改 skill 文档、模板和 eval，不启动服务。

## Git 上下文（Git Context）

主分支（Main branch）:

- main（来自 `.harness/environment.md`）

任务类型（Task type）:

- feature

工作分支（Working branch）:

- harness/feature

分支动作（Branch action）:

- already-on-branch

Git command policy:

- 同一仓库 Git 命令串行执行。
- 本计划后续不将任何 Git 命令放入并发批次。
- 文件读取、`rg`、`Get-Content` 可并发，但不能和 Git 命令混在同一并发批次。

Read-only Git options:

- 状态检查优先 `git --no-optional-locks status --short --branch`。
- diff 检查优先 `git -c diff.autoRefreshIndex=false diff --check`。
- 最终提交前需要精确状态时，可在确认无其它 Git 命令运行后，串行执行普通 `git status --short --branch`。

Index lock recovery:

- 如果出现 index lock，使用 `git rev-parse --git-path index.lock` 解析精确路径。
- 检查文件存在、大小和 mtime 稳定。
- 检查无活跃 `git`/`git.exe` 进程；如存在未知归属 Git 进程，视为不安全，不删除。
- 只删除解析出的精确 lock 文件，删除后立即串行 status。

当前状态:

- 当前在 `harness/feature`，工作区干净。

提交策略（Commit policy）:

- 用户批准实施后允许阶段提交。

未解决问题:

- 无 blocking 问题。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| Git | 状态、diff、提交 | All | available with `safe.directory` | index lock 竞争 | 串行 + no optional locks | 方案批准后提交 |
| Python | quick_validate、JSONL 检查 | Stage 4 | available | 无 | 手工检查 | not needed |
| rg | 关键规则检索 | Stage 4 | available | 无 | Select-String | not needed |
| PowerShell | 本地命令运行 | All | available | Git 并发误用 | 串行 Git 命令 | not needed |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程:

- no

规则结论:

- 本任务只运行 finite command，例如 Python 校验、rg 和 Git 检查。
- 不启动 dev server、web 服务、worker、watcher 或其它长期进程。
- 因此不需要 process-manager。

## 验证（Validation）

必需验证（Required）:

- Skill 结构验证。
- JSONL 解析和 id 唯一性。
- Git 串行和 lock 规则关键文本检索。
- whitespace 检查。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 4 | quick_validate.py | pass | skill metadata | forward testing | `Skill is valid!` | 无需处理 |
| Stage 4 | JSONL parse/id unique | pass | eval 格式 | 语义质量 | `jsonl ok 48` | 无需处理 |
| Stage 4 | rg key rules | pass | 规则落点 | 真实 Git 竞争复现 | 命中 SKILL、workflow、模板、eval、CHANGELOG | 无需处理 |
| Stage 4 | 旧 Git 示例检索 | pass | 裸旧示例 | 真实执行 | 未发现误导性裸 `git diff <main>`；普通 status 仅用于最终精确状态说明 | 无需处理 |
| Stage 4 | git diff --check | pass | whitespace | 行为测试 | 仅 CRLF 提示 | 无需处理 |

未覆盖（Not covered）:

- 不主动制造 `.git/index.lock` 做破坏性恢复测试。
- 不模拟多 agent 并发 Git 竞争；通过规则和 eval 覆盖行为期望。

## 文档（Documentation）

必需更新:

- `CHANGELOG.md`

Changelog 计划:

- 新增 Stage 42：complex-coding-harness Git 串行和 index.lock 恢复规则。
- 记录实现提交 hash。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `SKILL.md` | no | 单条核心规则 | 读取核心规则 |
| `workflow.md` | yes | 独立 Git 章节 | 读取 Git 工作分支及新增章节 |
| `templates/execution-plan.md` | yes | Git Context 子段和 log 表格 | 读取 Git Context |
| `templates/environment.md` | yes | Git 区子段 | 读取 Git 区 |
| `prompts.jsonl` | no | 完整 JSONL 条目集合 | JSONL parse/id unique |
| `CHANGELOG.md` | no | 单个 Stage 块 | 读取顶部 changelog |

写入规则:

- 分段 patch 是落盘策略，不要求一次性生成全部细节。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 分段判断是写入风险判断，不是最终内容长度承诺。
- 不得为了符合判断结果删减功能、测试或文档。

整体复查:

- 写完后重新读取完整目标文件或相关章节。
- 检查是否仍有 Codex 专用工具名残留。
- 检查 Git 规则是否和现有分支策略冲突。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | resolved | 是否每次删除 index.lock 都需要问用户 | 不需要；无活跃 Git 且精确路径确认后可删除并记录 | workflow |
| D-002 | no | resolved | 是否只写 Codex 并发工具名 | 不写具体工具名，使用通用 agent/并发机制描述 | workflow/SKILL |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级 | pass | Git 官方文档 + 本地读取 |
| 影响面矩阵完整 | pass | 覆盖文档、模板、eval、环境 |
| 候选方案比较充分 | pass | 比较 A/B/C |
| 每阶段可独立验证 | pass | Stage 1-4 均有验证 |
| 方案变更触发条件清楚 | pass | 已列 reapproval triggers |
| 用户批准摘要可记录 | pass | Plan Approval 待用户确认 |

质量结论:

- pass

## 规划自查（Plan Self-Review）

自查结论:

- pass

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 初稿若写死 `.git/index.lock` 会不兼容 worktree | 改为 `git rev-parse --git-path index.lock` | fixed |
| 优化（Optimizations） | 每次都问用户删除 stale lock 过重 | 改为轻量门禁后自动删除精确 stale lock | fixed |
| 缺失项（Missing items） | 需要覆盖 diff 自动刷新 index | 加入 `diff.autoRefreshIndex=false` 规则 | fixed |
| 缺失项（Missing items） | 旧模板命令示例可能继续误导并发/可选锁行为 | 实施计划要求同步检索和修正旧示例 | fixed |
| 风险（Risks） | 规则可能被误解为 Codex 专用 | 全部使用通用 agent、并发工具、多 shell 表述 | fixed |
| 风险（Risks） | `--no-optional-locks` 可能被误解为所有场景唯一 status 命令 | 补充最终提交前可串行普通 status 获取精确状态 | fixed |
| 风险（Risks） | 系统存在未知 Git 进程时误删 lock | 补充未知归属 Git 进程视为不安全 | fixed |
| 一致性（Consistency） | Git 串行规则不能和分支策略冲突 | 放在 Git 工作分支之后，作为安全执行规则 | fixed |

门禁重跑:

- Plan Quality Gate 是否需要重跑：no
- Plan Self-Review 是否需要重跑：no
- Readiness Gate 是否需要重跑：no
- 原因：自查修复已包含在当前计划中，未改变目标和实施范围。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚 | pass | Problem/Acceptance |
| 上下文已收集 | pass | 读取 skill、workflow、模板，查官方资料 |
| 候选方案已比较 | pass | Options A/B/C |
| 决策已记录 | pass | Decision |
| 实施阶段已细化 | pass | Stage 1-4 |
| 环境已确认 | pass | PowerShell、Python、rg、Git |
| Git 上下文已确认 | pass | `harness/feature`，工作区干净 |
| 工具已确认 | pass | Tooling |
| 验证已确认 | pass | Validation |
| 最终交付证据已规划 | pass | Validation + Commit Log |
| 文档更新已确认 | pass | Changelog plan |
| 风险已识别 | pass | Plan Self-Review |
| 规划自查已通过 | pass | Plan Self-Review pass |
| 阻塞问题已关闭 | pass | 无 blocking 问题 |

就绪结论:

- pass；等待用户批准实施。

## 方案批准（Plan Approval）

状态（Status）:

- approved

批准记录（Approval record）:

- 用户已回复“确认，开始实现吧”，批准按本计划实施 Stage 1 到 Stage 4。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: `SKILL.md`、`workflow.md`、`templates/execution-plan.md`、`templates/environment.md`、`prompts.jsonl`、`CHANGELOG.md`、harness 状态记录。
- 阶段提交授权（Stage commit authorization）: approved，完成验证后提交。
- 工具/MCP 授权（Tool/MCP authorization）: approved，使用 PowerShell、Python、rg、Git；不启动长期进程。
- 文档更新授权（Documentation authorization）: approved。

提交策略（Commit policy）:

- authorized after validation

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- completed

当前阶段（Current stage）:

- Final Delivery

已完成阶段（Completed stages）:

- Planning

剩余阶段（Remaining stages）:

- none

下一步自动动作（Next automatic action）:

- none

当前停止条件（Current stop condition）:

- all_approved_stages_completed

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | completed | 已完成方案、外部资料复核、Plan Self-Review 和 Readiness Gate；用户已批准实施 | 本计划自查通过 | 本文件 | 进入 Stage 1 |
| Stage 1 | completed | 已新增核心规则和 workflow Git 串行/index lock 恢复章节，并同步旧 Git 示例 | rg pass | SKILL.md、workflow.md | 进入 Stage 2 |
| Stage 2 | completed | 已更新 execution-plan/environment 模板的 Git 策略、只读选项和 Lock Recovery Log | rg pass | templates | 进入 Stage 3 |
| Stage 3 | completed | 已新增 8 条 Git 串行和 index lock eval 场景 | JSONL pass | prompts.jsonl | 进入 Stage 4 |
| Stage 4 | completed | 已完成验证、changelog 更新、code review 和提交，commit `0f75841` | quick_validate、JSONL、rg、diff check pass | 验证证据表 | 最终交付 |

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Planning | 方案可能硬编码 `.git/index.lock` | major | 已改为 `git rev-parse --git-path index.lock` |
| Planning | 规则可能绑定 Codex 并发工具 | major | 已改为通用 agent/并发机制表述 |
| Stage 4 | `git branch --show-current` 旧示例未标注串行 | minor | 已改为“串行执行 `git branch --show-current`”，并重新验证 |
| Stage 4 | 规则过重风险 | follow-up | 保留普通 status 的串行精确状态场景，避免 `--no-optional-locks` 误用为唯一选择 |

## 恢复摘要（Resume Summary）

- 整体目标（Overall goal）: 为 `complex-coding-harness` 增加 Git 命令串行和 index lock 精确恢复规则。
- 执行模式（Execution mode）: run-to-completion。
- 整体任务状态（Overall status）: completed。
- 已完成阶段（Completed stages）: Planning、Stage 1、Stage 2、Stage 3、Stage 4。
- 当前阶段（Current stage）: Final Delivery。
- 剩余阶段（Remaining stages）: none。
- 最新 commit（Latest commit）: `0f75841`。
- 下一步自动动作（Next automatic action）: none。
- 当前停止条件（Current stop condition）: all_approved_stages_completed。
- 状态来源（State source of truth）: execution-plan.md。
- 长期进程规则（Process manager rule）: 本任务不涉及长期进程。
- Git 规则（Git rule）: 后续所有 Git 命令必须串行；只读 status 用 `--no-optional-locks`，diff 检查用 `diff.autoRefreshIndex=false`。
- 未覆盖/风险（Not covered/risks）: 不主动制造 index lock 复现；通过规则和 eval 覆盖。
- 最新复查（Latest review）: 已补充旧 Git 命令示例同步、`--no-optional-locks` 使用边界、未知 Git 进程禁止删除 lock。
- 不得停止说明（Do not stop note）: 用户批准实施后进入 run-to-completion，不能在阶段边界提前停止。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/<date>/<task-slug>/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | included in `0f75841` | `docs(complex-coding-harness): 增加 Git 串行和 index.lock 恢复规则` | Stage 42 |
| Stage 4 | dev-skills | `0f75841` | `docs(complex-coding-harness): 增加 Git 串行和 index.lock 恢复规则` | Stage 42 |

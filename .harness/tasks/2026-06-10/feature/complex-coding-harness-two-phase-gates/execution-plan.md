# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

- 增强 `complex-coding-harness` skill 的两大阶段门禁能力：方案制定阶段和方案实施阶段。
- 让方案质量、阶段进入、阶段退出、验证证据、审查结论和恢复摘要更可判定。
- 保持 skill 轻量，不新增复杂脚本或大量规则文件。

非目标（Non-goals）:

- 不新增重型状态机、自动化 harness 或 UI。
- 不拆分 `workflow.md` 为多份默认 reference。
- 不新增默认运行时文件；继续以 `execution-plan.md` 为任务级唯一主契约。
- 不改变 `skills/` 源码主结构。

验收标准（Acceptance）:

- `workflow.md` 明确 `Plan Quality Gate`、`Stage Contract`、`Stage Entry Gate`、`Stage Exit Gate`、验证证据和 resume summary 规则。
- `execution-plan.md` 模板包含影响面矩阵、证据等级、阶段契约、阶段进入/退出门禁、验证证据表和恢复摘要。
- 示例执行计划同步展示新增门禁的实际填写方式。
- eval fixtures 覆盖弱方案拒绝、阶段进入阻塞、验证失败循环、恢复摘要和范围变更重新审批。
- README 或总规划文档说明两阶段增强后的使用流程。
- 每阶段完成后执行 review、验证、记录更新和提交。

约束（Constraints）:

- 遵循当前仓库 `AGENTS.md`：新增说明性内容使用中文，保持最小改动，验证结果不得伪造。
- 遵循 `skill-creator` 原则：保持 `SKILL.md` 简短，详细流程留在 reference 和模板中，避免新增无关文档。
- 当前任务由 `.harness` 托管，实施前必须等待用户明确批准方案。

待确认项（Open uncertainties）:

- 无。用户已批准进入实现。

## 上下文（Context）

本地代码（Local code）:

- `skills/complex-coding-harness/SKILL.md`
- `skills/complex-coding-harness/references/workflow.md`
- `skills/complex-coding-harness/templates/execution-plan.md`
- `examples/complex-coding-harness/sample-execution-plan.md`
- `evals/complex-coding-harness/prompts.jsonl`
- `evals/complex-coding-harness/expected.yaml`
- `evals/complex-coding-harness/README.md`
- `docs/complex-coding-harness-skill-plan.md`
- `CHANGELOG.md`

本地文档（Local docs）:

- `docs/complex-coding-harness-skill-plan.md`
- `docs/complex-coding-harness-upgrade-plan.md`
- `.harness/tasks/2026-06-10/feature/complex-coding-harness-upgrade-plan/execution-plan.md`
- `CHANGELOG.md`

外部来源（External sources）:

- Agent Skills：强调 skill 应保持入口简洁、使用 progressive disclosure、checklist、validation loop 和 eval fixtures。
- Claude Code 文档：强调持久上下文文件应简洁具体，技能/命令/上下文应按用途区分。
- ADR 实践：重要决策应记录上下文、方案和后果。

用户约束（User constraints）:

- “由该skill托管这个任务，规划需要由harness管理”。
- 之前已要求每阶段完成后审查、验证、自动提交代码并更新任务记录。

## 候选方案（Options）

### 方案 A：仅在 workflow 中补规则

- 做法（How）: 只更新 `workflow.md`，增加两阶段门禁说明。
- 优点（Pros）: 改动最小。
- 缺点（Cons）: 模板和示例不承载新字段，真实使用时容易遗漏。
- 风险（Risks）: agent 读到规则但执行计划仍无法硬性记录。
- 验证（Validation）: 只能通过文本检索验证。
- 回滚（Rollback）: 回退 `workflow.md` 相关章节。

### 方案 B：workflow + 模板 + 示例 + eval 同步增强

- 做法（How）: 在 `workflow.md` 写规则，在模板和示例落字段，在 eval 中加行为样例。
- 优点（Pros）: 规则、使用入口和回归样例一致，最符合当前 skill 结构。
- 缺点（Cons）: 文档和模板改动较多，需要控制篇幅。
- 风险（Risks）: 模板可能变长，需要避免把所有场景都塞进去。
- 验证（Validation）: 文本检索、JSONL 解析、示例人工审查和 diff check。
- 回滚（Rollback）: 分阶段回退对应文件。

### 方案 C：新增校验脚本

- 做法（How）: 新增脚本检查 `execution-plan.md` 是否包含门禁字段。
- 优点（Pros）: 机械检查更强。
- 缺点（Cons）: 增加维护成本，且当前模板仍在迭代，不宜过早固化。
- 风险（Risks）: 脚本容易变成形式校验，不能证明方案真的好。
- 验证（Validation）: 执行脚本和样例输入。
- 回滚（Rollback）: 删除脚本和 README 说明。

## 决策（Decision）

选择方案（Chosen option）:

- 方案 B：workflow + 模板 + 示例 + eval 同步增强。

原因（Why）:

- 当前 skill 的核心结构就是 `SKILL.md` 短入口、`workflow.md` 详细规则、`templates/` 运行时主契约、`examples/` 使用示范、`evals/` 行为样例。
- 只改 workflow 不够可执行；新增脚本又过早。
- 同步增强能让两阶段门禁真正进入用户填写和 agent 恢复路径。

影响（Impact）:

- managed 任务的 `execution-plan.md` 会多出若干可判定字段。
- 执行阶段会更强调每阶段进入/退出检查。
- eval fixtures 更能覆盖新门禁行为。

可逆性（Reversibility）:

- 所有改动为文档、模板和 fixtures，可按阶段回退。

变更条件（Change conditions）:

- 如果实施中发现模板过重，优先精简字段，不新增独立文件。
- 如果 eval fixtures 难以表达新规则，只保留最关键样例，不引入自动评测框架。

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：规划阶段质量门禁

目标（Goal）:

- 让方案制定阶段能够判断“是否足够好”，而不只是“是否写完”。

做法（How）:

- 在 `workflow.md` 的执行计划质量区域补充 `Plan Quality Gate`。
- 在 `execution-plan.md` 模板增加影响面矩阵、证据等级、方案变更触发条件和批准摘要字段。
- 在示例执行计划中填写一个简化但完整的影响面矩阵。

原因（Why）:

- 当前 `Readiness Gate` 偏完成度检查，缺少方案质量判定。
- 复杂任务最容易失败在方案阶段过空泛。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/complex-coding-harness/references/workflow.md`
  - `skills/complex-coding-harness/templates/execution-plan.md`
  - `examples/complex-coding-harness/sample-execution-plan.md`
- API/配置（APIs/configs）:
  - 不涉及。
- 测试/文档（Tests/docs）:
  - `evals/complex-coding-harness/`
  - `CHANGELOG.md`

参考来源（References）:

- Agent Skills 的 checklist、validation loop 和 eval 建议。
- ADR 的 context、decision、consequence 记录思想。
- 当前 `docs/complex-coding-harness-skill-plan.md` 的方案敲定协议。

验证（Validation）:

- `rg` 检索 `Plan Quality Gate`、`影响面矩阵`、`证据等级`、`方案变更触发条件`。
- `git diff --check`。
- 人工审查模板是否没有新增默认文件。

风险和回滚（Risks and rollback）:

- 风险：模板变长。
- 回滚：保留 `Plan Quality Gate`，删减影响面矩阵列。

### 阶段 2（Stage 2）：阶段执行契约和进入/退出门禁

目标（Goal）:

- 让每个实施阶段都有明确的范围、允许修改、禁止修改、进入条件和退出条件。

做法（How）:

- 在 `workflow.md` 的实施阶段循环中加入 `Stage Contract`、`Stage Entry Gate`、`Stage Exit Gate`。
- 在 `execution-plan.md` 模板的 `Implementation Plan` 和 `Implementation Progress` 附近增加阶段契约字段。
- 在示例执行计划中展示后端阶段和前端阶段的契约。

原因（Why）:

- 当前流程要求逐阶段执行，但阶段边界主要靠文字描述。
- 明确 entry/exit gate 可以防止脏工作区、分支错误、验证失败后继续推进。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/complex-coding-harness/references/workflow.md`
  - `skills/complex-coding-harness/templates/execution-plan.md`
  - `examples/complex-coding-harness/sample-execution-plan.md`
- API/配置（APIs/configs）:
  - 不涉及。
- 测试/文档（Tests/docs）:
  - `evals/complex-coding-harness/`
  - `CHANGELOG.md`

参考来源（References）:

- 当前 workflow 的实施阶段循环。
- 当前用户要求“每个阶段前后端都需要详细验证和 code review”。

验证（Validation）:

- `rg` 检索 `Stage Contract`、`Stage Entry Gate`、`Stage Exit Gate`。
- 人工审查示例阶段是否包含允许修改和禁止修改。
- `git diff --check`。

风险和回滚（Risks and rollback）:

- 风险：阶段字段太多导致用户填写负担增加。
- 回滚：将字段压缩成一张阶段表。

### 阶段 3（Stage 3）：验证证据、审查等级和恢复摘要

目标（Goal）:

- 让阶段验证、review finding 和上下文压缩恢复更容易复核。

做法（How）:

- 在 `workflow.md` 补充验证证据表、review severity 处理规则和 resume summary。
- 在 `execution-plan.md` 模板中增加验证证据表和 `Resume Summary`。
- 在示例执行计划中展示验证证据和恢复摘要。

原因（Why）:

- 当前验证字段有命令、结果、证据，但多阶段任务更适合表格记录。
- 上下文压缩后需要极短恢复摘要，避免每次只靠长文档定位。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/complex-coding-harness/references/workflow.md`
  - `skills/complex-coding-harness/templates/execution-plan.md`
  - `examples/complex-coding-harness/sample-execution-plan.md`
- API/配置（APIs/configs）:
  - 不涉及。
- 测试/文档（Tests/docs）:
  - `evals/complex-coding-harness/`
  - `CHANGELOG.md`

参考来源（References）:

- 当前最终交付门禁。
- Agent Skills 的 validation loop 和 eval 建议。

验证（Validation）:

- `rg` 检索 `Resume Summary`、`blocking`、`major`、`minor`、`follow-up`。
- `git diff --check`。
- 人工审查最终交付门禁没有与新增字段冲突。

风险和回滚（Risks and rollback）:

- 风险：review severity 被机械填写。
- 回滚：保留 severity 定义，减少模板表格列。

### 阶段 4（Stage 4）：eval fixtures 补充

目标（Goal）:

- 用最小 fixtures 覆盖新增门禁，防止后续改动弱化两阶段能力。

做法（How）:

- 在 `prompts.jsonl` 增加：
  - `weak-plan-rejected`
  - `stage-entry-blocked`
  - `validation-failure-loop`
  - `resume-summary-required`
  - `scope-change-reapproval`
- 在 `expected.yaml` 增加对应期望。
- 更新 eval README，说明这些仍是 prompt fixtures，不是自动评测。

原因（Why）:

- 当前 eval 已覆盖 Git 和最终交付，但尚未覆盖两阶段门禁强化。

位置（Where）:

- 文件/模块（Files/modules）:
  - `evals/complex-coding-harness/prompts.jsonl`
  - `evals/complex-coding-harness/expected.yaml`
  - `evals/complex-coding-harness/README.md`
- API/配置（APIs/configs）:
  - 不涉及。
- 测试/文档（Tests/docs）:
  - JSONL 解析。

参考来源（References）:

- 现有 eval fixtures 结构。

验证（Validation）:

- JSONL 逐行解析。
- `rg` 检索新增 eval id。
- `git diff --check`。

风险和回滚（Risks and rollback）:

- 风险：fixtures 被误解成自动判分测试。
- 回滚：保留 README 声明，删减 expected 字段。

### 阶段 5（Stage 5）：总文档和变更记录

目标（Goal）:

- 让仓库级文档说明两阶段增强后的使用方式。

做法（How）:

- 更新 `docs/complex-coding-harness-skill-plan.md` 中两大阶段说明。
- 更新 `CHANGELOG.md`。
- 必要时更新仓库 README 的简短说明。

原因（Why）:

- 用户需要理解该 skill 的主体是“先敲定方案，再按方案执行”。
- 变更记录需要和阶段 commit 对齐。

位置（Where）:

- 文件/模块（Files/modules）:
  - `docs/complex-coding-harness-skill-plan.md`
  - `CHANGELOG.md`
  - `README.md`（必要时）
- API/配置（APIs/configs）:
  - 不涉及。
- 测试/文档（Tests/docs）:
  - 文档关键字检索。

参考来源（References）:

- 当前调研结论和本执行计划。

验证（Validation）:

- `rg` 检索 `Plan Quality Gate`、`Stage Entry Gate`、`Stage Exit Gate`、`Resume Summary`。
- `git diff --check`。

风险和回滚（Risks and rollback）:

- 风险：总规划文档继续膨胀。
- 回滚：只保留摘要和指向 workflow/template 的说明。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- 当前仓库未配置 `.harness/environment.md`。
- 本任务是文档、模板和 fixtures 增强，不需要 Python、Node、浏览器、MCP 或外部服务。

本任务使用（This task uses）:

- PowerShell。
- `rg`。
- `git`。
- JSON/JSONL 解析。

临时覆盖（Temporary overrides）:

- 不需要。

## Git 上下文（Git Context）

主分支（Main branch）:

- `master`

任务类型（Task type）:

- `feature`

工作分支（Working branch）:

- `harness/feature`

分支动作（Branch action）:

- already-on-branch

同步来源（Sync source）:

- local `master`

最近同步（Last sync）:

- 未执行新的 merge；当前工作区干净。

分支占用（Branch occupancy）:

- `git log master..HEAD`: 当前包含 `81cbb00`、`2b7160b`、`9382919`、`1cae648`、`db7872c`、`1d25251`、`a935e47`。
- `git diff master...HEAD --name-only`: 仅包含当前 `complex-coding-harness` skill、文档、eval、示例和 `.harness` 任务记录相关文件。
- 现有提交属于本任务链路（Existing commits belong to this task）: 是，均属于 `complex-coding-harness` 增强链路。

提交策略（Commit policy）:

- 待用户批准本方案后，按阶段自动提交。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: 否。
- 未合回时代码停留在（If not merged, code remains on）: `harness/feature`。
- 合并前需要用户确认（User confirmation needed before merge）: 是。

分支安全（Branch safety）:

- 切换前已检查工作区：当前无需切换，工作区干净。
- 不自动 stash：是。
- 不自动 rebase：是。
- 不自动 reset：是。

热修复插入（Hotfix interruption）:

- 当前不涉及。

未解决问题（Open issues）:

- 无。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| `rg` | 关键文本检索 | 全阶段 | available | 低 | PowerShell `Select-String` | 不需要 |
| `git` | 状态检查和阶段提交 | 全阶段 | available | 中，涉及提交 | 只记录建议提交点 | 方案批准后授权 |
| PowerShell JSON 解析 | 验证 active task 和 JSONL | 阶段 0、4、最终 | available | 低 | 手工检查 | 不需要 |

## 验证（Validation）

必需验证（Required）:

- `.harness/active-task.json` JSON 可解析。
- `evals/complex-coding-harness/prompts.jsonl` JSONL 逐行解析。
- `rg` 检索新增门禁关键词。
- `git diff --check`。
- 人工审查模板、示例和 workflow 是否一致。

已执行（Executed）:

- 当前规划阶段已读取 skill、workflow、模板、eval、示例、CHANGELOG 和 Git 状态。
- 当前工作区干净。
- 当前分支为 `harness/feature`。
- Stage 1 `Plan Quality Gate`、影响面矩阵、证据等级、方案变更触发条件和批准摘要检索：通过。
- Stage 1 `.harness/active-task.json` JSON 解析：通过。
- Stage 1 `git diff --check`：通过。
- Stage 2 `Stage Contract`、`Stage Entry Gate`、`Stage Exit Gate`、允许修改和禁止修改检索：通过。
- Stage 2 `.harness/active-task.json` JSON 解析：通过。
- Stage 2 `git diff --check`：通过。

可选验证（Optional）:

- 如后续可用，可使用子 agent/新会话做 forward-test；当前不作为必需项，避免引入额外执行成本。

产物（Artifacts）:

- 截图（Screenshot）: 不适用。
- 日志（Log）: 终端验证摘要。
- Trace: 不适用。
- 报告（Report）: 当前 `execution-plan.md`。

未覆盖（Not covered）:

- 当前尚未实现任何 skill 文件改动。
- 尚未运行最终 JSONL 解析和文本检索，因为实现尚未开始。

无法执行时（If unable to run）:

- 在最终交付说明未执行原因和影响。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/complex-coding-harness/references/workflow.md`
- `skills/complex-coding-harness/templates/execution-plan.md`
- `examples/complex-coding-harness/sample-execution-plan.md`
- `evals/complex-coding-harness/prompts.jsonl`
- `evals/complex-coding-harness/expected.yaml`
- `evals/complex-coding-harness/README.md`
- `CHANGELOG.md`

Changelog 计划（Changelog plan）:

- 每阶段提交后更新 `CHANGELOG.md`，记录阶段工作和 commit hash。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| D-001 | yes | closed | 是否批准本执行计划并进入阶段实现？ | 用户已回复“按方案执行” | Plan Approval |

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pass | Problem 已记录 |
| 上下文已收集（Context collected） | pass | 已读取 skill、workflow、模板、eval、示例、CHANGELOG 和 Git 状态 |
| 候选方案已比较（Options compared） | pass | 已比较 3 个方案 |
| 决策已记录（Decision recorded） | pass | 选择方案 B |
| 实施阶段已细化（Implementation stages detailed） | pass | 已拆成 5 个阶段 |
| 环境已确认（Environment confirmed） | pass | 文档模板任务，无运行环境依赖 |
| Git 上下文已确认（Git context confirmed） | pass | 当前在 `harness/feature`，工作区干净 |
| 工具已确认（Tooling confirmed） | pass | 使用 rg、git、PowerShell |
| 验证已确认（Validation confirmed） | pass | 已定义 JSONL、rg、diff check 和人工审查 |
| 最终交付证据已规划（Final delivery evidence planned） | pass | 无 UI，证据为文档、验证和 commit |
| 文档更新已确认（Documentation updates confirmed） | pass | Required updates 已列出 |
| 风险已识别（Risks identified） | pass | 每阶段含风险和回滚 |
| 阻塞问题已关闭（Blocking questions closed） | pass | D-001 已关闭 |

就绪结论（Readiness result）:

- `pass`

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 用户回复：“按方案执行”。

提交策略（Commit policy）:

- `stage_commits_authorized`

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Stage 0 | completed | 创建 harness 托管任务计划 | JSON 解析、关键字段检索和 diff check 通过 | `.harness` 当前任务文件 | 提交规划 |
| Stage 1 | completed | 规划阶段质量门禁已完成 | 关键文本检索、JSON 解析和 diff check 通过 | workflow、template、example | 阶段 1 提交 |
| Stage 2 | completed | 阶段执行契约和进入/退出门禁已完成 | 关键文本检索、JSON 解析和 diff check 通过 | workflow、template、example | 阶段 2 提交 |
| Stage 3 | pending | 验证证据、审查等级和恢复摘要 | 待执行 | workflow、template、example | 等待 Stage 2 提交 |
| Stage 4 | pending | eval fixtures 补充 | 待执行 | evals | 等待 Stage 3 |
| Stage 5 | pending | 总文档和变更记录 | 待执行 | docs、CHANGELOG | 等待 Stage 4 |

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Stage 0 | 新任务可能与上一轮已完成任务混淆 | minor | 使用独立 task slug，并更新 active-task 指针 |
| Stage 0 | `harness/feature` 已有未合回提交 | minor | 已记录分支占用，确认属于同一 skill 增强链路 |
| Stage 1 | 模板字段增加可能加重填写负担 | minor | 只新增一张影响面矩阵和一个质量门禁表，不新增独立文件 |
| Stage 2 | 阶段门禁可能被机械填写 | minor | 同时要求 allowed/forbidden changes 和 entry/exit 证据，降低空填风险 |

## 提交记录（Commit Log）

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Stage 0 | `dev-skills` | `7a0f196` | `docs(complex-coding-harness): 托管两阶段门禁增强任务` | not updated |
| Stage 1 | `dev-skills` | `8f0268c` | `feat(complex-coding-harness): 增强方案质量门禁` | not updated |
| Stage 2 | `dev-skills` | 待提交 | `feat(complex-coding-harness): 增强阶段执行门禁` | not updated |

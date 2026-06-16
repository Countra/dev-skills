# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

- 为 `complex-coding-harness` 增加独立的 `Plan Self-Review`（规划自查）模块。
- 要求 agent 在方案写完后、提交用户审批前，主动复查方案是否存在缺陷、可优化点、缺失项、风险和内部不一致。
- 将“发现问题后先修复计划，再进入审批”固化成流程门禁，避免弱方案、漏项方案或自相矛盾的方案直接进入 `Plan Approval`。
- 在 `workflow.md`、`execution-plan.md` 模板和 eval 中建立可复用规则。

非目标（Non-goals）:

- 不改变 `complex-coding-harness` 的两阶段模型：先定方案，再实施。
- 不绕过用户批准门禁；规划自查通过不等于用户批准。
- 不修改 `process-manager`、Git 分支策略、长期进程规则或提交规则。
- 不新增运行时脚本、后台服务或自动迁移工具。
- 不要求历史任务批量迁移；旧任务只在自然更新时补齐该模块。

验收标准（Acceptance）:

- `SKILL.md` 明确：方案提交用户审批前，必须完成独立的规划自查。
- `references/workflow.md` 增加 `Plan Self-Review` 规则，说明检查类别、处理规则、插入位置和重新跑门禁条件。
- `templates/execution-plan.md` 增加独立 `规划自查（Plan Self-Review）` 区块。
- `templates/execution-plan.md` 的审批前门禁顺序调整为：
  - `Plan Quality Gate`
  - `Plan Self-Review`
  - `Readiness Gate`
  - `Plan Approval`
- `Plan Self-Review` 必须覆盖：
  - 缺陷检查（Defects）
  - 优化检查（Optimizations）
  - 缺失项检查（Missing items）
  - 风险检查（Risks）
  - 一致性检查（Consistency）
- 明确处理规则：
  - 发现 defect：必须先修复计划，不能进入审批。
  - 发现 missing item：必须补充到计划。
  - 发现 optimization：如果不改变目标、范围和风险，应直接优化计划；如果会改变范围，记录为方案变更并请求用户确认。
  - 发现 risk：必须补充验证、缓解或回滚策略。
  - 发现 consistency 问题：必须修正冲突字段，并以 `execution-plan.md` 为主契约。
- 如果自查修复改变目标、范围、阶段、验证策略、工具依赖、风险或提交策略，必须重新跑 `Plan Quality Gate` 和 `Readiness Gate`。
- 如果用户在审批前要求修改方案，或者 agent 自己补充了方案内容，必须重新执行 `Plan Self-Review`；不能沿用旧自查结论。
- `evals/complex-coding-harness/prompts.jsonl` 增加覆盖规划自查的场景。
- 验证通过：
  - `quick_validate.py skills/complex-coding-harness`
  - `prompts.jsonl` JSONL 解析
  - 关键规则检索
  - 模板门禁顺序检索
  - `git diff --check`

约束（Constraints）:

- 遵守最小变更原则，只调整规划自查相关规则、模板和 eval。
- 文档使用中文为主，必要英文术语保留双语标识。
- 不重写整个 workflow 或模板，只在合适位置插入新模块。
- 新模块必须足够明确，但不能把流程变成复杂冗余的多轮表单。
- 规划自查应服务于“方案更可靠”，不能成为新的自动执行授权。

待确认项（Open uncertainties）:

- 无 blocking 待确认项。本计划建议默认采用独立模块，并放在 `Plan Quality Gate` 之后、`Readiness Gate` 之前。

## 上下文（Context）

本地代码和文档（Local code/docs）:

- `skills/complex-coding-harness/SKILL.md`
  - 已要求实施前完成方案、环境、工具、验证、文档和 `Readiness Gate`。
  - 已要求 `Plan Approval` 记录用户明确批准后才能实现。
  - 当前没有把“规划自查”作为核心规则单独列出。
- `skills/complex-coding-harness/references/workflow.md`
  - 已有 `Plan Quality Gate`，用于判断方案是否足够进入审批。
  - 已有 `Readiness Gate`，用于确认方案提交审批前的就绪状态。
  - 当前缺少“主动挑错、修复、优化、补充”的独立步骤。
- `skills/complex-coding-harness/templates/execution-plan.md`
  - 已有 `就绪门禁（Readiness Gate）` 和 `方案质量门禁（Plan Quality Gate）`。
  - 当前没有独立 `规划自查（Plan Self-Review）` 表格。
  - 当前模板顺序是 `Readiness Gate` 在 `Plan Quality Gate` 之前；如果要表达“质量基线 -> 主动自查 -> 最终就绪”的流程，需要在实施时调整审批前门禁顺序。
  - 当前 `就绪结论（Readiness result）` 位于 `Plan Quality Gate` 后方，容易让结果字段归属不清；实施时应将质量、自查、就绪各自的结论字段放回对应章节。
- `evals/complex-coding-harness/prompts.jsonl`
  - 已覆盖方案批准、阶段连续执行、长期进程等规则。
  - 当前缺少专门验证规划自查行为的场景。

复查发现（Review findings）:

- 缺陷：原计划建议把 `Plan Self-Review` 放在 `Plan Quality Gate` 和 `Readiness Gate` 之间，但没有说明当前模板实际顺序需要调整。
- 修复：已明确 Stage 2 必须调整审批前门禁顺序，并让 `Readiness Gate` 包含 `规划自查已通过` 检查项。
- 优化：新增门禁顺序检索命令和 eval 顺序场景，避免实现后出现“文字说顺序正确，模板顺序错误”的回归。

外部来源（External sources）:

- 本任务不依赖在线资料；这是对当前仓库内 `complex-coding-harness` 规则的流程补强。

用户约束（User constraints）:

- 用户明确要求规划阶段需要有独立自查模块：
  - 仔细复查规划是否有缺陷，如果有修复。
  - 是否有可优化的地方，如果有优化。
  - 是否有可补充的地方，如果有补充。
- 用户要求用 harness 模式落盘详细规划方案；当前阶段只规划，不实施。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 当前 workflow 有 `Plan Quality Gate` 和 `Readiness Gate` | read | `references/workflow.md` | 新模块应接入现有规划流程 |
| 当前模板没有独立 `Plan Self-Review` 区块 | read | `templates/execution-plan.md` | 需要新增模板区块 |
| 用户要求规划阶段主动复查、修复、优化、补充 | confirmed | 用户会话 | 需要把该行为固化成强制门禁 |
| 规划自查通过不能替代用户批准 | read/confirmed | 现有 `Plan Approval` 规则和用户历史要求 | 新模块必须保持审批边界 |

## 根因分析（Root Cause）

### 1. `Plan Quality Gate` 偏结果判定，不偏主动修复

现有 `Plan Quality Gate` 用来判断方案是否达到进入审批的质量标准，例如证据等级、影响面、候选方案和验证策略是否完整。它更像验收清单，不足以强制 agent 在提交审批前主动问自己：

- 这个方案有没有逻辑缺陷？
- 有没有可以更简单、更稳的做法？
- 有没有遗漏环境、工具、验证、回滚、文档或提交策略？
- 各章节之间是否存在冲突？

### 2. `Readiness Gate` 偏提交审批前状态，不偏方案内容深挖

`Readiness Gate` 确认目标、上下文、验证、文档、风险和阻塞问题是否可提交审批，但它不负责系统性挑错和修复。把规划自查混在 `Readiness Gate` 中，会让“主动复查”变成弱提醒。

### 3. 当前流程缺少“发现后必须修复”的硬规则

即使 agent 发现了优化或缺失项，当前规则也没有明确要求：

- 先修复计划。
- 记录处理结果。
- 必要时重新跑质量和就绪门禁。
- 如果改变范围，必须重新请求用户确认。

### 4. 长任务上下文压缩后容易忽略规划质量复查

如果规划自查只是对话里的临时习惯，而不是模板字段，上下文压缩后 agent 很容易跳过该动作。必须把它写入 `execution-plan.md` 模板，使恢复时也能看到。

### 5. 现有模板顺序会削弱新模块语义

当前模板中 `Readiness Gate` 位于 `Plan Quality Gate` 之前。若只把 `Plan Self-Review` 插入模板而不调整顺序，就会出现“先就绪、再质量、再自查”的语义冲突。实施时必须把审批前门禁调整为：

1. `Plan Quality Gate`
2. `Plan Self-Review`
3. `Readiness Gate`
4. `Plan Approval`

`Readiness Gate` 应作为最终提交审批前的综合就绪检查，并把 `Plan Self-Review` 通过作为其中一项检查。

## 候选方案（Options）

### 方案 A：不新增模块，只继续依赖 `Plan Quality Gate`

优点（Pros）:

- 无需修改模板和流程。
- 当前规则数量不增加。

缺点（Cons）:

- 不能直接满足用户要求的“缺陷、优化、补充”自查。
- 仍容易把规划质量检查做成被动勾选。
- 无法在模板中留下自查处理记录。

结论（Decision）:

- 不采用。现有门禁不足以表达主动自查和修复。

### 方案 B：把自查项塞进 `Plan Quality Gate`

优点（Pros）:

- 文件改动较少。
- 不新增一个完整章节。

缺点（Cons）:

- `Plan Quality Gate` 会变得职责混杂。
- “发现问题后如何处理”不够显式。
- 后续 agent 可能只看到质量门禁表，仍跳过主动复查过程。

结论（Decision）:

- 不推荐。它能减少章节，但降低规则清晰度。

### 方案 C：新增独立 `Plan Self-Review` 模块

优点（Pros）:

- 清晰表达“先主动挑错，再修复，再进入审批”。
- 可在模板里记录发现、处理和结果，方便恢复后复查。
- 不破坏现有 `Plan Quality Gate` 和 `Readiness Gate` 职责。
- 易于通过 eval 验证。

缺点（Cons）:

- 增加一个规划阶段区块。
- 需要控制内容简洁，避免变成繁重表单。

结论（Decision）:

- 采用。该方案最符合用户目标，且对现有流程侵入较小。

## 推荐方案（Recommended Approach）

采用方案 C：新增独立 `Plan Self-Review` 模块。

推荐插入顺序：

1. 草拟方案。
2. 完成 `Plan Quality Gate` 初检。
3. 执行 `Plan Self-Review`。
4. 如果自查修复改变关键内容，重新跑 `Plan Quality Gate`。
5. 完成 `Readiness Gate`。
6. 进入 `Plan Approval`，等待用户明确批准。

这里选择放在 `Plan Quality Gate` 之后、`Readiness Gate` 之前，原因是：

- `Plan Quality Gate` 先提供基础质量基线。
- `Plan Self-Review` 在基线基础上主动挑错和补强。
- `Readiness Gate` 最后确认方案是否可提交用户审批。

这要求同步调整当前模板顺序；不能在现有 `Readiness Gate` 位置前后简单追加，避免形成冲突流程。

## 设计细节（Design）

### 1. `SKILL.md` 核心规则

新增一条核心规则，建议放在实施前审批规则附近：

```md
- 方案提交用户审批前，必须完成 `Plan Self-Review`：复查缺陷、优化点、缺失项、风险和一致性；发现问题必须先修复计划，再进入 `Readiness Gate` 和 `Plan Approval`。
```

### 2. `workflow.md` 流程规则

新增独立章节：

```md
## 规划自查（Plan Self-Review）

`Plan Self-Review` 是方案提交审批前的主动复查步骤，不等同于 `Plan Quality Gate` 或 `Readiness Gate`。
```

必须包含五类检查：

| 类别 | 检查内容 | 必须处理 |
| --- | --- | --- |
| Defects | 逻辑矛盾、错误假设、不可执行步骤、遗漏前置条件 | 修复计划后才能继续 |
| Optimizations | 可减少复杂度、文件数量、阶段数量、用户交互或验证成本的改进 | 不改变范围时直接优化；改变范围时重新确认 |
| Missing items | 缺少环境、Git、验证、工具、MCP、process-manager、回滚、文档、提交策略 | 补充到计划 |
| Risks | 高风险改动缺少验证、缓解或回滚 | 补充风险处理 |
| Consistency | `Execution Control`、阶段计划、验证、Git、状态记录、恢复摘要之间冲突 | 修正冲突，以 `execution-plan.md` 为准 |

处理规则：

- 发现 defect：计划状态不能进入 `awaiting_plan_approval`。
- 发现 missing item：必须补充对应章节。
- 发现 optimization：若不改变目标和风险，直接优化；若改变目标、范围、阶段、验证或风险，记录为方案变更并请用户确认。
- 发现 risk：必须补充验证、缓解或回滚策略。
- 发现 consistency 问题：必须修正计划和 `.harness/active-task.json` 摘要。
- 自查修改后如果影响关键章节，必须重新跑 `Plan Quality Gate` 和 `Readiness Gate`。
- 用户审批前只要方案内容被修改，必须重新执行 `Plan Self-Review`，并更新自查结论。

### 3. `execution-plan.md` 模板

建议调整审批前门禁顺序，并在 `方案质量门禁（Plan Quality Gate）` 与 `就绪门禁（Readiness Gate）` 之间增加：

```md
## 规划自查（Plan Self-Review）

自查结论（Review result）:

- pending

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） |  |  | pending |
| 优化（Optimizations） |  |  | pending |
| 缺失项（Missing items） |  |  | pending |
| 风险（Risks） |  |  | pending |
| 一致性（Consistency） |  |  | pending |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：
- `Readiness Gate` 是否需要重跑：
- `Plan Self-Review` 是否需要重跑：
- 原因：
```

填写规则：

- 没有发现问题时，也要写明 `未发现 blocking 问题`，不能留空。
- 有问题时，`Action` 必须说明修改了哪个章节。
- `Result` 只能使用 `pass`、`fixed`、`deferred-with-reason`、`blocked`。
- 只有非 blocking 且有明确理由的问题才能 `deferred-with-reason`。
- `Readiness Gate` 必须新增一项：`规划自查已通过（Plan self-review passed）`。
- `Plan Quality Gate`、`Plan Self-Review` 和 `Readiness Gate` 的结论字段必须各自放在对应章节，不复用 `就绪结论`。

### 4. `active-task.json` 状态约束

规划自查期间：

- `status` 应保持 `planning` 或 `awaiting_plan_approval` 前状态。
- 自查未通过时，不得设置为 `awaiting_plan_approval`。
- 自查通过且 `Readiness Gate` 通过后，才可以设置为 `awaiting_plan_approval`。

推荐摘要字段：

```json
{
  "planning_review": {
    "status": "pass",
    "defects": "fixed/none",
    "missing_items": "fixed/none",
    "updated_at": "YYYY-MM-DD"
  }
}
```

该字段是摘要，不是主契约；主契约仍是 `execution-plan.md`。

### 5. eval 场景

新增 5 个 eval prompt：

- `plan-self-review-detects-missing-environment`
  - 场景：方案缺少 Python/Node/Go 环境确认。
  - 期望：agent 在 `Plan Self-Review` 中标记 missing item 并补充。
- `plan-self-review-detects-inconsistent-validation`
  - 场景：前文说需要 Chrome DevTools MCP，验证表却写不需要浏览器。
  - 期望：agent 标记 consistency 并修复验证策略。
- `plan-self-review-optimizes-overbuilt-plan`
  - 场景：小文档修改被拆成过多阶段。
  - 期望：agent 标记 optimization 并简化阶段。
- `plan-self-review-blocks-defective-plan`
  - 场景：方案依赖不存在的脚本或字段。
  - 期望：agent 标记 defect，不进入审批。
- `plan-self-review-reruns-gates-after-material-change`
  - 场景：自查后新增验证策略和风险处理。
  - 期望：agent 记录需要重新跑 `Plan Quality Gate` 和 `Readiness Gate`。
- `plan-self-review-enforces-gate-order`
  - 场景：模板仍把 `Readiness Gate` 放在 `Plan Quality Gate` 前。
  - 期望：agent 识别顺序错误，调整为质量门禁、自查、就绪门禁、方案批准。

## 影响面矩阵（Impact Matrix）

| 影响面（Area） | 影响（Impact） | 处理（Handling） |
| --- | --- | --- |
| `SKILL.md` | 新增规划自查核心规则 | 最小增量，一条核心规则 |
| `workflow.md` | 新增 `Plan Self-Review` 章节和处理规则 | 放在规划质量和审批流程之间 |
| `execution-plan.md` 模板 | 新增规划自查表格，并调整审批前门禁顺序 | 保持简洁，避免复杂表单 |
| eval | 新增自查场景 | JSONL 解析验证 |
| 旧任务 | 不强制迁移 | 自然更新时补齐 |
| 用户交互 | 不增加默认确认轮次 | 只在 blocking 或范围变化时确认 |
| 实施流程 | 不改变已批准实施阶段 | 只影响规划提交审批前 |

## 工具和验证策略（Tools And Validation）

工具（Tools）:

- PowerShell：读取文件、检索、运行验证。
- `rg`：检索关键规则。
- Python：JSONL 解析。
- Git：检查 diff 和提交。

不需要的工具（Not required）:

- 不需要 Chrome DevTools MCP。
- 不需要 process-manager。
- 不需要启动长期后台服务。
- 不需要联网搜索。

验证命令（Validation commands）:

```powershell
python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/complex-coding-harness
```

```powershell
python -c "import json, pathlib; p=pathlib.Path('evals/complex-coding-harness/prompts.jsonl'); [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]; print('ok')"
```

```powershell
rg "Plan Self-Review|规划自查|Defects|Missing items|Consistency" skills/complex-coding-harness evals/complex-coding-harness
```

```powershell
rg -n "方案质量门禁|规划自查|就绪门禁|方案批准" skills/complex-coding-harness/templates/execution-plan.md
```

```powershell
git -c safe.directory=E:/work/hl/videoForensic/AI/dev-skills diff --check
```

## 实施阶段规划（Implementation Plan）

### Stage 1：核心规则和 workflow

目标（Goal）:

- 把 `Plan Self-Review` 写入 `SKILL.md` 和 `workflow.md`。

怎么做（How）:

- 在 `SKILL.md` 的核心规则中新增审批前规划自查要求。
- 在 `workflow.md` 中更新规划流程顺序。
- 在 `workflow.md` 中新增 `Plan Self-Review` 章节，说明检查类别、处理规则和门禁重跑条件。

为什么（Why）:

- skill 主体和 workflow 是 agent 实际执行时最先复查的规则来源。

在哪里做（Where）:

- `skills/complex-coding-harness/SKILL.md`
- `skills/complex-coding-harness/references/workflow.md`

验证（Validation）:

- `rg "Plan Self-Review|规划自查" skills/complex-coding-harness/SKILL.md skills/complex-coding-harness/references/workflow.md`

风险和回滚（Risks/Rollback）:

- 风险：规则文字过多增加上下文负担。
- 回滚：保留核心规则，压缩解释性文本。

### Stage 2：模板字段

目标（Goal）:

- 在 `execution-plan.md` 模板中加入独立规划自查区块，并修正审批前门禁顺序。

怎么做（How）:

- 将审批前门禁顺序调整为 `Plan Quality Gate`、`Plan Self-Review`、`Readiness Gate`、`Plan Approval`。
- 在 `方案质量门禁（Plan Quality Gate）` 与 `就绪门禁（Readiness Gate）` 之间插入 `规划自查（Plan Self-Review）`。
- 增加五类检查表和门禁重跑记录。
- 明确 `Result` 可选值和填写规则。
- 将 `就绪结论（Readiness result）` 放回 `Readiness Gate`，并为 `Plan Quality Gate` 增加独立质量结论。
- 在 `Readiness Gate` 增加 `规划自查已通过（Plan self-review passed）` 检查项。

为什么（Why）:

- 模板字段能防止上下文压缩后遗忘自查步骤。

在哪里做（Where）:

- `skills/complex-coding-harness/templates/execution-plan.md`

验证（Validation）:

- `rg "规划自查|Review result|Gate rerun" skills/complex-coding-harness/templates/execution-plan.md`
- `rg -n "方案质量门禁|规划自查|就绪门禁|方案批准" skills/complex-coding-harness/templates/execution-plan.md`

风险和回滚（Risks/Rollback）:

- 风险：模板变长。
- 回滚：压缩表格说明，但保留五类检查。

### Stage 3：eval 覆盖

目标（Goal）:

- 用 eval 场景防止后续回归。

怎么做（How）:

- 在 `evals/complex-coding-harness/prompts.jsonl` 增加 5 条场景。
- 如果 Stage 2 调整门禁顺序，则增加第 6 条顺序检查场景。
- 每条场景要求输出中必须体现 `Plan Self-Review` 的发现和处理。

为什么（Why）:

- 规则类 skill 需要用 prompt fixture 覆盖典型失败模式。

在哪里做（Where）:

- `evals/complex-coding-harness/prompts.jsonl`

验证（Validation）:

- JSONL 解析。
- 检查新增 id 唯一。

风险和回滚（Risks/Rollback）:

- 风险：eval prompt 过长。
- 回滚：压缩描述，保留期望行为。

### Stage 4：验证、记录和提交

目标（Goal）:

- 完成静态验证、记录结果并提交。

怎么做（How）:

- 执行 `quick_validate.py`。
- 执行 JSONL 解析。
- 执行关键规则检索。
- 执行 `git diff --check`。
- 更新本执行计划的验证证据、Code Review、Implementation Progress 和 Commit Log。
- 如果用户批准实施和提交，则按规范提交。

为什么（Why）:

- 这是文档和规则类变更，静态验证和 fixture 解析是主要质量保障。

在哪里做（Where）:

- 本执行计划。
- 相关 skill、模板和 eval 文件。

验证（Validation）:

- 按 `工具和验证策略` 执行。

风险和回滚（Risks/Rollback）:

- 风险：Git ownership 保护导致普通 git 命令失败。
- 处理：使用 `git -c safe.directory=E:/work/hl/videoForensic/AI/dev-skills ...`。

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pass | 见 `证据等级` |
| 影响面矩阵完整（Impact matrix complete） | pass | 覆盖 skill、workflow、模板、eval、旧任务和用户交互 |
| 候选方案比较充分（Options compared enough） | pass | 已比较 A/B/C |
| 阶段可独立验证（Stages independently verifiable） | pass | Stage 1-4 均有验证方式 |
| 方案变更触发条件明确（Change triggers clear） | pass | 见下方触发条件 |
| 用户批准摘要可记录（Approval summary ready） | pass | `Plan Approval` 已预留 |

方案变更触发条件（Change triggers）:

- 实施时发现 `workflow.md` 或模板结构与计划不一致，需要大段重写。
- 需要新增脚本、自动迁移器或运行时工具。
- 新模块会改变用户批准门禁、Git 策略、长期进程规则或提交授权。
- eval 文件格式与预期不一致。
- 必需验证无法执行且缺少替代证据。

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- pass

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 初稿如果只新增模板而不更新 workflow，会导致规则入口不明显 | 已把 `SKILL.md`、`workflow.md`、模板和 eval 都纳入实施阶段 | fixed |
| 优化（Optimizations） | 初稿可能把自查放在 `Readiness Gate` 内，职责不清 | 采用独立模块，放在 `Plan Quality Gate` 后、`Readiness Gate` 前 | fixed |
| 缺失项（Missing items） | 需要说明自查修改后何时重跑门禁；还需要覆盖门禁顺序校验 | 已补充门禁重跑规则、模板字段和 eval 顺序场景 | fixed |
| 风险（Risks） | 新模块可能增加流程负担 | 采用 5 行表格和简短规则，不新增默认用户确认轮次 | fixed |
| 一致性（Consistency） | 必须保持“规划自查不等于批准”；当前模板原顺序与推荐顺序不一致 | 已补充模板顺序调整要求，并明确 `Readiness Gate` 是最终就绪检查 | fixed |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：已重跑。
- `Readiness Gate` 是否需要重跑：需要在本自查后执行。
- 原因：自查补充了实施范围、门禁重跑规则和简化约束。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pass | 见 `问题定义` |
| 上下文已收集（Context collected） | pass | 已读取当前 harness 状态、workflow、模板和相关检索结果 |
| 候选方案已比较（Options compared） | pass | A/B/C 已比较，推荐 C |
| 决策已记录（Decision recorded） | pass | 采用独立 `Plan Self-Review` 模块 |
| 影响范围已列明（Impact listed） | pass | 见 `影响面矩阵` |
| Git 策略已确认（Git strategy confirmed） | pass | feature 类型，使用 `harness/feature` |
| 外部依赖和工具已说明（Tools/dependencies clear） | pass | 不需要 MCP、process-manager 或联网 |
| 验证已确认（Validation confirmed） | pass | 见 `工具和验证策略` |
| 文档更新已确认（Documentation updates confirmed） | pass | 更新 skill、workflow、模板、eval 和 harness 记录 |
| 风险已识别（Risks identified） | pass | 每阶段列出风险和回滚 |
| 阻塞问题已关闭（Blocking questions closed） | pass | 无 blocking 问题 |
| 规划自查已通过（Plan self-review passed） | pass | 已完成本计划自查，并修复模板顺序缺陷 |

## 方案批准（Plan Approval）

批准状态（Approval status）:

- approved

用户批准范围（Approved scope）:

- 用户已回复“按方案执行”，批准实施 Stage 1 到 Stage 4。

提交授权（Commit authorization）:

- approved

工具授权（Tool authorization）:

- approved；使用本地 PowerShell、Python、rg 和 Git；不启动长期后台服务。

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- completed

当前阶段（Current stage）:

- Final Delivery

剩余阶段（Remaining stages）:

- none

下一步自动动作（Next automatic action）:

- none

当前停止条件（Current stop condition）:

- all_approved_stages_completed

阶段边界是否允许停止（May stop at stage boundary）:

- no after approval, unless a stop condition is hit or user explicitly requests stage-only execution

## 运行时进程门禁（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- no

process-manager skill 是否可用（Available）:

- not required

需要托管的服务（Managed services）:

| 服务 | 类型 | 启动方式 | readiness | service config | 状态 |
| --- | --- | --- | --- | --- | --- |
| none | none | none | none | none | not required |

禁止 shell 后台启动确认:

- pass；本任务只使用 finite command。

manager 离线处理策略:

- 不适用；本任务不启动长期进程。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 提交（Commit） |
| --- | --- | --- | --- |
| Planning | completed | 已落盘规划自查独立模块详细方案并完成复查 | pending |
| Stage 1 | completed | `SKILL.md` 和 workflow 已加入 `Plan Self-Review` 核心规则、流程顺序和处理规则 | pending |
| Stage 2 | completed | 模板已调整为 `Plan Quality Gate` -> `Plan Self-Review` -> `Readiness Gate` -> `Plan Approval`，并新增自查表格 | pending |
| Stage 3 | completed | eval 已新增 6 条规划自查场景，覆盖缺失环境、一致性、过度复杂、缺陷阻塞、门禁重跑和顺序错误 | pending |
| Stage 4 | completed | 已完成 skill 校验、JSONL 解析、关键规则检索、门禁顺序检索和 diff check | pending |

## 代码审查（Code Review）

规划阶段审查（Planning review）:

| 类别 | 结果 | 说明 |
| --- | --- | --- |
| 方案缺陷 | pass | 已补充独立模块、处理规则和门禁重跑规则 |
| 过度复杂 | pass | 控制为一个简短表格和少量 workflow 规则 |
| 覆盖缺失 | pass | 覆盖 SKILL、workflow、模板、eval 和 active-task 状态约束 |
| 审批边界 | pass | 明确规划自查不等于用户批准 |

实施阶段审查（Implementation review）:

| 类别 | 结果 | 说明 |
| --- | --- | --- |
| 规则入口 | pass | `SKILL.md` 增加审批前规划自查核心规则 |
| 流程一致性 | pass | workflow 和模板均采用质量门禁、自查、就绪门禁、方案批准顺序 |
| 模板可恢复性 | pass | `execution-plan.md` 模板新增固定自查区块和门禁重跑记录 |
| eval 覆盖 | pass | 新增 6 条场景覆盖主要失败模式 |

## 验证证据（Validation Evidence）

| 验证项（Check） | 命令/方式（Command/Method） | 结果（Result） | 证据（Evidence） |
| --- | --- | --- | --- |
| active-task JSON 解析 | `python -c ...` | pass | 输出 `active-task json ok` |
| 规划关键规则检索 | `rg "Plan Self-Review|规划自查"` | pass | 命中新规划、active-task 和 environment 中的关键规则 |
| diff 格式检查 | `git diff --check` | pass | 无 diff whitespace 错误；PowerShell 输出 LF/CRLF warning |
| Git 状态检查 | `git status --short --branch` | pass | 当前分支 `harness/feature`，仅有本次 harness 规划文件改动 |
| 方案复查 | 读取规划、workflow 和模板门禁上下文 | pass | 已发现并修复模板顺序缺陷，补充门禁顺序验证和 eval 场景 |
| Skill 校验 | `quick_validate.py skills/complex-coding-harness` | pass | 输出 `Skill is valid!` |
| JSONL 解析和 id 唯一性 | Python 解析 `prompts.jsonl` | pass | 输出 `jsonl ok 34` |
| 关键规则检索 | `rg "Plan Self-Review|规划自查|Defects|Missing items|Consistency|规划自查已通过"` | pass | 命中 SKILL、workflow、模板和 eval |
| 模板门禁顺序检索 | `rg -n "方案质量门禁|规划自查|就绪门禁|方案批准"` | pass | 行号顺序为 308、323、344、367 |

## 提交记录（Commit Log）

| 阶段（Stage） | Commit | Message | Notes |
| --- | --- | --- | --- |
| Stage 1-4 | pending | `feat(complex-coding-harness): 增加规划自查门禁` | 等待提交 |

## 恢复摘要（Resume Summary）

整体目标:

- 为 `complex-coding-harness` 增加独立 `Plan Self-Review` 规划自查模块。

执行模式:

- run-to-completion

已完成阶段:

- Planning：已完成并落盘详细方案。
- Stage 1：核心规则和 workflow 已更新。
- Stage 2：模板门禁顺序和自查区块已更新。
- Stage 3：eval 场景已补充。
- Stage 4：验证和记录已完成。

当前阶段:

- Final Delivery

剩余阶段:

- none

当前停止条件:

- all_approved_stages_completed

下一步自动动作:

- none

关键规则:

- 规划自查通过不等于用户批准。
- 发现规划缺陷、缺失项、风险或一致性问题时，必须先修复计划。
- 如果自查修复改变范围、阶段、验证或风险，必须重新跑 `Plan Quality Gate` 和 `Readiness Gate`。
- 实施时必须调整模板门禁顺序为 `Plan Quality Gate` -> `Plan Self-Review` -> `Readiness Gate` -> `Plan Approval`。

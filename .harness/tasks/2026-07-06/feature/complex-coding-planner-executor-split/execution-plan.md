# 执行计划：拆分 complex-coding-harness 为 planner 和 executor

## 问题定义

目标:

- 将现有 `complex-coding-harness` 改名为 `complex-coding-planner`，作为复杂任务规划、调研、方案自查和用户审批的专用 skill。
- 新增 `complex-coding-executor`，完整承接现有实现阶段、阶段门禁、验证、review、Git、process-manager、changelog、commit 和最终交付规则。
- 迁移时不得直接删除旧规则。必须先复制和分类现有规则，再完成 executor，复查无遗漏后，才从 planner 中移除执行阶段细节。
- 增加轻量 Python 检查脚本，约束“未批准不能执行”“仍有 pending 决策不能执行”“阶段边界不能误停”等高风险状态。
- 保持当前 `.harness/` 任务状态、`execution-plan.md` 作为主契约、`active-task.json` 作为恢复入口的设计，不引入重型运行时框架。

非目标:

- 不实现本方案中的 skill 拆分，直到用户明确批准执行。
- 不引入 LangGraph、OpenAI Agents SDK、数据库或后台服务作为运行时依赖。
- 不迁移历史 `.harness/tasks/` 文档内容；旧任务记录保留原始事实。
- 不创建 `.agents` 目录，不绑定 Claude Code 专用结构。
- 不自动合并 `harness/feature` 到主分支。

验收标准:

- 规划明确说明哪些现有规则进入 planner，哪些进入 executor，哪些作为共享 `execution-plan.md` 契约保留。
- 实施阶段必须是“先复制旧规则到 executor，再改名 harness 为 planner，再裁剪 planner”的顺序，避免迁移期间规则丢失。
- `complex-coding-executor` 必须阻止未批准计划、open blocking 决策、状态冲突和阶段边界误停。
- 新增检查脚本必须只使用 Python 标准库，能对典型 plan fixture 给出 pass/fail 和可读原因。
- 验证覆盖 skill 结构校验、脚本编译、脚本 smoke、关键规则检索、eval fixture 更新和 diff check。

约束:

- 遵守全局 `AGENTS.md`：中文注释、修改前读上下文、最小必要改动、长内容分段写入。
- 遵守当前 `complex-coding-harness`：规划阶段完成 `Plan Quality Gate`、`Plan Self-Review`、`Readiness Gate` 后等待用户批准。
- 同一仓库 Git 命令必须串行执行。
- 长期进程不涉及；本任务所有验证预计都是 finite command，不进入 process-manager。
- 提交只在用户批准实施和授权提交后执行。

待确认项:

- 无 blocking 问题。默认方案采用“两 skill 拆分 + 轻量状态检查脚本 + eval 更新”。

## 上下文

本地代码:

- `skills/complex-coding-harness/SKILL.md` 目前同时包含任务分级、规划、审批、执行、阶段连续执行、长期进程、Git 串行、提交和最终交付规则。
- `skills/complex-coding-harness/references/workflow.md` 是完整长流程，覆盖规划和执行，但执行阶段规则较深，长任务中容易被上下文压缩或恢复摘要稀释。
- `skills/complex-coding-harness/templates/execution-plan.md` 是当前唯一完整任务主契约模板，包含规划区、执行控制、阶段门禁、恢复摘要和提交记录。
- `evals/complex-coding-harness/*` 当前覆盖 direct/managed/needs-clarification、审批、Git、阶段门禁、恢复、提交信息、process-manager 等行为。
- `skills/process-manager` 和 `skills/electron-ui-verifier` 已采用“简短 SKILL.md + references + scripts”的结构，可作为拆分后的组织参考。

本地文档:

- `.harness/environment.md` 记录当前主分支为 `main`，当前工作分支为 `harness/feature`，并要求同一仓库 Git 命令串行。
- `.harness/active-task.json` 已指向本任务，状态为 `awaiting_plan_approval`，下一步为等待用户批准。
- 历史任务 `complex-coding-harness-execution-control`、`complex-coding-harness-plan-self-review`、`complex-coding-harness-git-serial-index-lock` 记录了必须保留的执行控制、规划自查和 Git 串行规则。

外部来源:

- OpenAI Agents SDK handoffs 文档：`https://openai.github.io/openai-agents-python/handoffs/`，用于参考职责转交和专用 agent 边界。
- OpenAI Agents SDK guardrails 文档：`https://openai.github.io/openai-agents-python/guardrails/`，用于参考输入、输出和工具调用前后的检查边界。
- LangGraph durable execution 文档：`https://docs.langchain.com/oss/python/langgraph/durable-execution`，用于参考持久化状态、恢复和人工中断点。
- Anthropic Claude Code subagents 文档：`https://docs.anthropic.com/en/docs/claude-code/sub-agents`，用于参考专用上下文和职责隔离；本方案只吸收原则，不引入 `.agents` 专用目录。
- 本地 `skill-creator` 指南要求 skill 保持精简，详细内容放 references，脚本用于高重复和高可靠场景。

用户约束:

- 可以不要 `complex-coding-harness`，直接改名为 `complex-coding-planner`。
- 执行阶段规则必须完整拆到 `complex-coding-executor`。
- 不能省略步骤，不能阉割现有规范流程；只有确认规则不好时才考虑去掉。
- 不能直接删除旧 harness 规则；必须先复制，完成 executor 并复查后，再从 planner 中移除执行细节。
- 需要深入调研、查缺补漏，并可增加 Python 状态检查脚本。

证据等级:

| 结论 | 等级 | 来源 | 影响 |
| --- | --- | --- | --- |
| 当前 harness 同时承载规划和执行 | read | `SKILL.md`、`workflow.md` | 需要拆分职责 |
| 执行规则已经有 run-to-completion、Stage Transition Gate、process-manager、Git 串行等高价值内容 | read | `workflow.md`、历史任务计划 | 迁移时不能删减 |
| 规划和执行拆成专用 skill 更符合上下文隔离和渐进加载 | external/read | OpenAI handoffs、Claude subagents、skill-creator | 支持两 skill 方案 |
| 状态检查脚本能减少未批准执行和阶段误停 | external/assumption | Guardrail 设计原则、本地失败案例 | 需要 smoke 验证 |
| 不需要重型运行时框架 | assumption | 当前仓库 skill 架构和用户偏好 | 保持轻量实现 |

## 候选方案

### 方案 A：保留单一 skill，只重排 references

- 做法: 保留 `complex-coding-harness`，把 `workflow.md` 拆成 planning/execution 两个 reference，并在 `SKILL.md` 增加触发说明。
- 优点: 改动小，兼容旧名称。
- 缺点: 触发后仍是同一个 skill，执行阶段可能继续背负规划规则，用户语义不够清楚。
- 风险: 不能根治“规划阶段遵守、执行阶段遗忘”的问题。
- 验证: quick_validate、规则检索、eval 更新。
- 回滚: revert 文档拆分。

### 方案 B：拆成 planner 和 executor 两个 skill

- 做法: 先复制现有 harness 到 `complex-coding-executor`，完整承接执行规则；再将旧 `complex-coding-harness` 改名为 `complex-coding-planner`，保留规划、调研、自查、审批和计划模板；最后从 planner 中移除执行细节，仅保留交接契约和调用 executor 的边界。
- 优点: 触发语义清晰，上下文更轻，执行阶段规则更集中；符合用户要求。
- 缺点: 需要迁移 skill 名称、eval 名称和文档引用；需要防止规则遗漏。
- 风险: 如果先删旧规则再写 executor，容易丢规则；必须采用复制优先和迁移矩阵。
- 验证: quick_validate 两个 skill、脚本 smoke、迁移矩阵检索、eval fixture 更新。
- 回滚: revert 新增 executor 和 rename。

### 方案 C：拆成 planner、executor、shared-core 三层

- 做法: planner/executor 都依赖 `complex-coding-core` 或共享 reference 目录，公共规则放 core。
- 优点: 去重彻底。
- 缺点: skill 触发和加载链路变复杂，用户当前目标是稳定和清晰，不需要第三个 skill。
- 风险: 三层结构反而提高遗忘和维护成本。
- 验证: 需要更多 cross-skill 测试。
- 回滚: 成本较高。

## 决策

选择方案:

- 方案 B：拆成 `complex-coding-planner` 和 `complex-coding-executor` 两个 skill。

原因:

- 用户明确倾向拆分，且当前单 skill 规则过密是执行阶段失效的重要原因。
- 两 skill 既能保持 `.harness` 主契约不变，又能让规划和执行分别加载最小必要规则。
- 不引入 shared-core，避免把“拆分降复杂度”变成“三层依赖复杂度”。

影响:

- `skills/complex-coding-harness/` 将通过 rename 成为 `skills/complex-coding-planner/`。
- 新增 `skills/complex-coding-executor/`。
- `evals/complex-coding-harness/` 需要拆分或改名为 planner/executor 两组 fixture。
- `CHANGELOG.md` 需要记录拆分阶段和提交信息。

可逆性:

- 中等。涉及目录 rename 和新增目录，但可通过单个或多个提交 revert。

方案变更触发条件:

- 用户要求保留 `complex-coding-harness` 作为兼容入口。
- 发现现有规则无法无损迁移到 executor。
- 新增脚本必须引入第三方依赖。
- quick_validate 或脚本 smoke 无法稳定通过。
- 实施中发现需要改变 `.harness` 任务状态 schema。
- 发现 `active-task.json` 与 `execution-plan.md` 的状态字段无法通过脚本一致性检查。

## 影响面矩阵

| 影响对象 | 是否涉及 | 文件/模块 | 风险 | 验证方式 | 文档更新 |
| --- | --- | --- | --- | --- | --- |
| API | yes | skill 名称、description、触发语义、检查脚本 CLI | 中 | quick_validate、脚本 help/smoke | yes |
| 数据结构 | no | `.harness` 主契约保持 `execution-plan.md` | 低 | fixture smoke | yes |
| 前端交互 | no | 不涉及 UI | 低 | 不适用 | no |
| 配置/环境 | yes | `.harness/environment.md` 只作为读取来源，不改 schema | 低 | 文档检索 | yes |
| 兼容性 | yes | `complex-coding-harness` 名称移除，改为 planner/executor | 中 | `rg` 检索旧引用 | yes |
| 测试 | yes | eval fixture 拆分或重命名、脚本 smoke | 中 | JSONL/YAML 解析、脚本 smoke | yes |
| 文档 | yes | 两个 `SKILL.md`、references、templates、CHANGELOG | 中 | quick_validate、全文检索 | yes |

## 目标结构

推荐仓库结构:

```text
skills/
  complex-coding-planner/
    SKILL.md
    references/
      planning-workflow.md
    templates/
      environment.md
      execution-plan.md
      pending-decisions.md
    scripts/
      harness_plan_check.py
  complex-coding-executor/
    SKILL.md
    references/
      execution-workflow.md
    scripts/
      harness_exec_check.py
evals/
  complex-coding-planner/
    README.md
    prompts.jsonl
    expected.yaml
  complex-coding-executor/
    README.md
    prompts.jsonl
    expected.yaml
```

结构说明:

- `complex-coding-planner` 是旧 `complex-coding-harness` 的 rename 结果，保留 planning 入口、环境整理、方案模板、审批门禁和 pending decisions 模板。
- `complex-coding-executor` 是新 skill，只消费已批准的 `execution-plan.md`，不负责调研和制定初版方案。
- `execution-plan.md` 继续是 planner 和 executor 的交接契约；executor 不创建全新 plan，只更新执行状态、验证证据、review、changelog 和 commit log。
- `active-task.json` 继续只是恢复入口，不能替代 `execution-plan.md`。
- 两个检查脚本都是辅助 guardrail，不替代人工阅读计划和执行规则。

职责边界:

| 能力 | planner | executor |
| --- | --- | --- |
| 任务分级 direct/managed/needs-clarification | yes | no |
| 收集需求、上下文、环境、外部资料 | yes | only if plan requires reread |
| 编写和自查方案 | yes | no |
| 请求用户批准方案 | yes | no |
| 判断计划是否已批准 | yes | yes |
| 执行代码修改 | no | yes |
| 阶段 review、验证、修复 | no | yes |
| Git 分支、提交、changelog | plan only | yes |
| run-to-completion 和 Stage Transition Gate | plan defines | yes |
| 最终交付 | no | yes |

## 实施计划

### Stage 1：规则盘点和迁移矩阵

目标:

- 在任何删除或裁剪前，完整盘点现有 `complex-coding-harness` 规则，生成 planner/executor 迁移矩阵。

做法:

- 读取 `SKILL.md`、`references/workflow.md`、所有 templates、eval README/expected/prompts。
- 将每条规则分类为 `planner-only`、`executor-only`、`shared-contract`、`deprecated-with-reason`。
- 重点保留执行控制、阶段门禁、process-manager、Git 串行、分段 patch、commit message、最终交付等执行规则。
- 在本任务 `execution-plan.md` 或实施时新增迁移矩阵记录，证明没有直接删除规则。
- 迁移矩阵至少覆盖以下规则族，任何规则族标为 deprecated 时必须写明原因和替代规则:
  - 任务分级和 managed 进入条件。
  - workspace 环境整理和 `docs/development.md` 读取。
  - Git 工作分支、分支占用、热修复插入、Git 串行和 `index.lock` 恢复。
  - Plan Quality Gate、Plan Self-Review、Readiness Gate、Plan Approval。
  - 分段 patch 写入策略。
  - Blocking 决策和 `pending-decisions.md`。
  - Execution Control、run-to-completion、停止条件和恢复流程。
  - Stage Contract、Stage Entry Gate、Stage Exit Gate、Stage Transition Gate。
  - process-manager 长期进程规则和 finite command 例外。
  - 验证规则、code review 严重程度、Resume Summary。
  - commit message 文件方式、changelog、Commit Log 和最终交付门禁。

原因:

- 用户明确要求不能直接删除旧规则，必须先复制和复查后再裁剪。

位置:

- `skills/complex-coding-harness/*`
- `evals/complex-coding-harness/*`
- 本任务 `execution-plan.md`

参考来源:

- 当前 harness 文件和历史任务计划。

验证:

- `rg` 检索所有关键规则关键词并映射到迁移矩阵。
- 检查迁移矩阵中不存在空白归属；`deprecated-with-reason` 必须带原因和替代。
- 人工 code review：确认每个高价值规则有归属。

风险和回滚:

- 风险: 规则分类遗漏。
- 缓解: 用规则族清单、关键词检索和 eval fixture 三重覆盖。
- 回滚: 本阶段只读和记录，风险低。

阶段契约:

- 范围: 规则盘点和迁移矩阵。
- 允许修改: 本任务计划、可新增临时迁移矩阵记录。
- 禁止修改: skill 本体删除、目录 rename。
- 进入条件: 用户批准实施，工作区安全。
- 退出条件: 迁移矩阵覆盖关键规则。
- 必需验证: 关键规则检索。
- 是否预期提交: yes, if stage commit authorized。

### Stage 1 迁移矩阵

| 规则族 | 归属 | 来源 | 迁移要求 | 状态 |
| --- | --- | --- | --- | --- |
| 任务分级 direct/managed/needs-clarification | planner-only | `SKILL.md`、`workflow.md` | planner 负责分级；executor 不重新分级 | covered |
| `.harness` 文件布局和主契约 | shared-contract | `workflow.md`、template | planner 生成，executor 消费和更新 | covered |
| workspace 环境和 `docs/development.md` | planner-primary / executor-reread | `workflow.md` | planner 整理环境；executor 每阶段重读 | covered |
| Git 工作分支和热修复插入 | shared-contract / executor-enforced | `workflow.md`、template | planner 写入 Git Context；executor 阶段执行前检查 | covered |
| Git 命令串行和 `index.lock` 恢复 | executor-only | `workflow.md`、template | executor 执行和恢复；planner 只要求计划记录 | covered |
| Plan Quality Gate | planner-only | `workflow.md`、template | planner 审批前完成 | covered |
| Plan Self-Review | planner-only | `workflow.md`、template | planner 审批前完成并修复缺陷 | covered |
| Readiness Gate 和 Plan Approval | planner-only / shared-state | `workflow.md`、template | planner 等待批准；executor 只验证已批准 | covered |
| 分段 patch 写入策略 | shared-contract / executor-enforced | `workflow.md`、template | planner 规划写入策略；executor 对所有落盘动作执行 | covered |
| Blocking 决策和 `pending-decisions.md` | shared-contract | `workflow.md`、template | planner 可创建；executor 遇 open blocking 必须停止 | covered |
| Execution Control 和 run-to-completion | executor-only / shared-state | `workflow.md`、template | planner 初始化；executor 每轮和每阶段维护 | covered |
| 停止条件和恢复流程 | executor-only | `workflow.md`、template | executor 控制阶段边界和上下文恢复 | covered |
| Stage Contract / Entry / Exit / Transition Gate | executor-only | `workflow.md`、template | executor 每阶段必须执行 | covered |
| process-manager 长期进程规则 | executor-only / planner-records | `workflow.md`、template | planner 记录是否需要；executor 执行和复查 | covered |
| 验证规则和 code review 严重程度 | executor-only | `workflow.md`、template | executor 阶段执行、修复和记录 | covered |
| Resume Summary | executor-only | `workflow.md`、template | executor 每阶段和最终交付前更新 | covered |
| commit message 文件方式 | executor-only | `workflow.md`、template | executor 在提交授权后执行 | covered |
| changelog、Commit Log、最终交付门禁 | executor-only | `workflow.md`、template | executor 更新和最终汇总 | covered |
| skill 更新后的继续工作 | shared-contract | `workflow.md` | planner/executor 都需重新读取自身规则和任务状态 | covered |
| eval fixtures | split | `evals/complex-coding-harness` | planner/executor 各自覆盖对应行为 | covered |

Stage 1 结论:

- 无规则族标记为 `deprecated-with-reason`。
- 本轮拆分不删除规则语义，只调整触发边界和执行责任。

### Stage 2：创建 executor 并复制执行规则

目标:

- 新增 `complex-coding-executor`，先完整承接执行阶段规则，再进行精简和结构化。

做法:

- 从现有 `complex-coding-harness` 复制执行相关内容到 `skills/complex-coding-executor/`。
- 编写 executor `SKILL.md`：只允许在已批准计划上执行；每轮必须读取 `execution-plan.md`、`active-task.json`、`environment.md`。
- executor 被直接调用但找不到已批准计划时，必须停止并提示先使用 planner 制定并批准方案，不能现场补写计划后直接实现。
- 编写 `references/execution-workflow.md`，保留并整理以下规则：
  - 执行控制和 run-to-completion。
  - 停止条件。
  - Blocking 决策。
  - Stage Contract、Stage Entry Gate、Stage Exit Gate、Stage Transition Gate。
  - 验证规则、code review 严重程度、Resume Summary。
  - process-manager 长期进程规则。
  - Git 工作分支、Git 串行和 index lock 恢复。
  - commit message 文件方式和 changelog。
  - 最终交付门禁。
- 保留现有执行规则的语义，只有重复解释或与 executor 职责冲突的 planning 文案才删改。
- 提交规则必须明确：用户批准实施不等于授权提交；只有 `Plan Approval` 明确包含阶段提交授权，或用户额外明确说“提交”，executor 才能执行 `git commit`。

原因:

- 先完成 executor，才能安全裁剪 planner，避免迁移中规则丢失。

位置:

- `skills/complex-coding-executor/SKILL.md`
- `skills/complex-coding-executor/references/execution-workflow.md`

参考来源:

- `skills/complex-coding-harness/SKILL.md`
- `skills/complex-coding-harness/references/workflow.md`
- `skill-creator` 对 SKILL.md 精简和 references 渐进加载的建议。

验证:

- `quick_validate.py skills/complex-coding-executor`
- `rg "run-to-completion|Stage Transition Gate|Process Manager Gate|index.lock|git commit -F|Final delivery" skills/complex-coding-executor`

风险和回滚:

- 风险: executor 过长，重新变成 monolithic。
- 缓解: `SKILL.md` 保持短，详细内容放一个 reference；不拆过多文件。
- 回滚: 删除新增 executor 目录即可恢复。

阶段契约:

- 范围: 新增 executor skill。
- 允许修改: `skills/complex-coding-executor/`。
- 禁止修改: 旧 harness 规则裁剪。
- 进入条件: Stage 1 迁移矩阵通过。
- 退出条件: executor 可验证，执行关键规则齐全。
- 必需验证: quick_validate、关键规则检索。
- 是否预期提交: yes, if stage commit authorized。

### Stage 3：rename harness 为 planner

目标:

- 将旧 `complex-coding-harness` 改名为 `complex-coding-planner`，保留 planning 相关规则和模板。

做法:

- 使用 Git 可识别的目录移动方式，将 `skills/complex-coding-harness/` 改为 `skills/complex-coding-planner/`。
- 更新 frontmatter `name: complex-coding-planner` 和 description，使触发语义聚焦“复杂任务规划、环境确认、方案审批”。
- 将 `references/workflow.md` 改名或拆为 `references/planning-workflow.md`。
- 先保留执行相关段落的摘要和指向 executor 的交接要求，不立即大幅删除。
- 保留 `templates/environment.md`、`templates/execution-plan.md`、`templates/pending-decisions.md`，因为 planner 是 plan 的生产者。

原因:

- 用户要求 `complex-coding-harness` 可以不要，直接改名为 planner。

位置:

- `skills/complex-coding-planner/`

参考来源:

- 当前 harness skill 和 `skill-creator` 命名规则。

验证:

- `quick_validate.py skills/complex-coding-planner`
- `rg "name: complex-coding-planner|complex-coding-harness" skills/complex-coding-planner`

风险和回滚:

- 风险: 旧名称消失后用户误用。
- 缓解: 在 planner/executor description 中说明旧 harness 拆分后的触发方式；不保留旧兼容 skill，除非用户变更要求。
- 回滚: Git revert rename。

阶段契约:

- 范围: 目录 rename 和 planner metadata。
- 允许修改: planner skill 文件。
- 禁止修改: executor 已验证的执行规则。
- 进入条件: Stage 2 executor 完成并复查。
- 退出条件: planner 可验证，旧 harness 目录不再作为 skill 存在。
- 必需验证: quick_validate、旧名检索。
- 是否预期提交: yes, if stage commit authorized。

### Stage 4：裁剪 planner 并固化交接协议

目标:

- 让 planner 只负责规划阶段，同时不丢失执行阶段所需的计划字段。

做法:

- 在 planner `SKILL.md` 中明确：
  - 负责 direct/managed/needs-clarification 分级。
  - managed 任务必须创建或更新 `execution-plan.md`。
  - 必须完成 Context、Options、Decision、Impact Matrix、Implementation Plan、Plan Quality Gate、Plan Self-Review、Readiness Gate。
  - Readiness 通过后必须停止，等待用户批准。
  - 不允许开始代码实现、验证实现或提交代码。
- 在 planner workflow 中保留“执行计划必须包含 executor 可消费的 Execution Control Snapshot、Stage Contract、Validation、Git Context、Process Manager Gate、Commit Policy”等字段。
- 删除或缩短 planner 中完整执行循环的长段落，但必须用迁移矩阵确认这些内容已进入 executor。
- 在 `templates/execution-plan.md` 中新增或强化 `Execution Control Snapshot`，放在靠前位置，方便 executor 每轮恢复时读取。

原因:

- planner 如果继续包含完整执行细节，仍会造成上下文噪声；但计划模板不能缺少执行所需字段。

位置:

- `skills/complex-coding-planner/SKILL.md`
- `skills/complex-coding-planner/references/planning-workflow.md`
- `skills/complex-coding-planner/templates/execution-plan.md`

参考来源:

- 当前模板中的 `Execution Control`、`Stage Entry/Exit/Transition Gate`。
- 用户关于“规划阶段没问题、执行阶段没严格执行”的问题分析。

验证:

- `rg "Readiness Gate|Plan Approval|不得实现|Execution Control Snapshot|Stage Contract" skills/complex-coding-planner`
- 人工 review：planner 不再包含长篇逐阶段执行循环。

风险和回滚:

- 风险: 裁剪过度导致 planner 生成的 plan 不够 executor 执行。
- 缓解: 保留完整 `execution-plan.md` 模板，只裁剪 planner 指令正文。
- 回滚: 从 executor 或 Git 历史恢复缺失段。

阶段契约:

- 范围: planner 规划职责收口。
- 允许修改: planner SKILL、planning workflow、execution plan template。
- 禁止修改: executor 执行规则语义。
- 进入条件: Stage 3 完成。
- 退出条件: planner 规划职责清晰，executor 可消费字段完整。
- 必需验证: quick_validate、关键规则检索、计划模板 review。
- 是否预期提交: yes, if stage commit authorized。

### Stage 5：增加状态检查脚本

目标:

- 用轻量 Python guardrail 减少未批准执行、open 决策、状态冲突和阶段边界误停。

做法:

- 在 planner 中新增 `scripts/harness_plan_check.py`：
  - 检查 plan 是否包含必需章节。
  - 检查 `Plan Self-Review`、`Readiness Gate`、`Plan Approval` 的顺序和状态。
  - 检查 `Implementation Plan` 的每个阶段是否包含目标、做法、位置、验证、风险和阶段契约。
  - 输出 JSON 或可读文本，返回非零码表示不能提交用户审批。
- 在 executor 中新增 `scripts/harness_exec_check.py`：
  - 根据 `--workspace` 和 `--task-dir` 读取 `active-task.json` 与 `execution-plan.md`。
- 未批准计划直接 fail。
- `pending-decisions.md` 存在 open blocking 决策时 fail。
- `Execution Control` 与 `active-task.json` 冲突时 fail，并提示以 plan 为准修正。
- `remaining_stages` 非空且没有停止条件时，`--mode transition` 必须要求 `next_action=continue Stage N`，不能 final delivery。
- 检查 `Process Manager Gate`、Git policy、Validation、Commit policy 等关键章节存在。
- `--mode preflight` 检查执行前条件：plan approved、无 open blocking 决策、工作阶段存在、必要章节存在。
- `--mode transition` 检查阶段转移：有剩余阶段时必须继续，无剩余阶段时才能进入 final delivery。
- `--mode final` 检查最终交付：所有阶段完成、验证和 review 有记录、提交或未提交原因已记录。
- 脚本只做结构和显式状态检查，不尝试理解业务方案正确性。

原因:

- 自然语言规则在长任务和上下文压缩后容易被遗忘；脚本提供低自由度检查点。

位置:

- `skills/complex-coding-planner/scripts/harness_plan_check.py`
- `skills/complex-coding-executor/scripts/harness_exec_check.py`
- 对应 smoke fixture 可放在 `.harness/tasks/<task>/tmp/` 或脚本内临时目录。

参考来源:

- OpenAI guardrail 思路：在输入、输出、工具使用前后提供检查边界。
- 当前 `process-manager` 的 `pm_validate.py` 设计：脚本只验证可机械判断的结构，不替代人工决策。

验证:

- `python -m py_compile` 覆盖两个脚本。
- `python skills/complex-coding-planner/scripts/harness_plan_check.py --help`
- `python skills/complex-coding-executor/scripts/harness_exec_check.py --help`
- smoke:
  - 未批准 plan -> executor fail。
  - approved plan + no open decision -> executor pass。
  - open pending decision -> executor fail。
  - transition 时还有 remaining stage -> next action 必须 continue。
  - final mode 下仍有 pending stage -> executor fail。

风险和回滚:

- 风险: Markdown 状态解析不完美。
- 缓解: 只解析稳定标题和明确状态行；失败信息提示人工复查，不做自动修改。
- 回滚: 保留 skill 规则，移除或降级脚本调用要求。

阶段契约:

- 范围: 新增辅助脚本和 smoke。
- 允许修改: 两个 skill 的 `scripts/` 和文档中脚本使用说明。
- 禁止修改: `.harness` schema 和业务执行逻辑。
- 进入条件: planner/executor 基本结构完成。
- 退出条件: 脚本 smoke 覆盖关键阻断场景。
- 必需验证: py_compile、help、smoke。
- 是否预期提交: yes, if stage commit authorized。

### Stage 6：更新 eval、changelog、整体验证和交付记录

目标:

- 完成拆分后的全局验证和记录，确保后续用户知道应分别调用 planner/executor。

做法:

- 将 `evals/complex-coding-harness` 拆为 planner/executor 两组，或按最终结构重命名。
- planner eval 覆盖：
  - managed 任务规划但不实现。
  - Readiness 通过后等待用户批准。
  - 计划自查发现缺陷先修复。
  - 环境不清楚时阻塞确认。
- executor eval 覆盖：
  - 未批准计划不能执行。
  - pending decision 不能执行。
  - 阶段完成后仍有 remaining stages 时不能最终回复。
  - 验证失败必须修复并重复验证。
  - 长期进程必须使用 process-manager。
  - Git 串行和 commit message 文件方式。
- 更新 `CHANGELOG.md`。
- 更新本任务执行计划的验证表、review、commit log 和 resume summary。

原因:

- 拆分后行为要靠 eval fixture 和关键检索防止回归。

位置:

- `evals/complex-coding-planner/*`
- `evals/complex-coding-executor/*`
- `CHANGELOG.md`
- 本任务 `execution-plan.md`

参考来源:

- 现有 `evals/complex-coding-harness`。

验证:

- quick_validate 两个 skill。
- JSONL 解析和 id 唯一性。
- YAML 解析或文本检查。
- 关键规则 `rg` 检索。
- `git -c diff.autoRefreshIndex=false diff --check`。

风险和回滚:

- 风险: 旧 eval 名称变更影响外部调用。
- 缓解: 在 changelog 和最终交付中明确新名称；不保留旧名，除非用户要求兼容。
- 回滚: revert eval rename 和 skill split。

阶段契约:

- 范围: eval、changelog、任务状态和最终验证。
- 允许修改: eval 目录、CHANGELOG、本任务状态。
- 禁止修改: 已验证的 skill 核心规则，除非 review 发现缺陷。
- 进入条件: Stage 1-5 完成。
- 退出条件: 所有验证通过或记录替代证据，最终 review 无 blocking/major。
- 必需验证: quick_validate、py_compile、smoke、JSONL/YAML、rg、diff check。
- 是否预期提交: yes, if stage commit authorized。

## 环境

Workspace 环境来源:

- `.harness/environment.md`

本任务使用:

- 仓库: `E:\work\hl\videoForensic\AI\dev-skills`
- 语言: Markdown、YAML、JSONL、Python。
- Python: 当前可用 `python`，仅用于 py_compile 和轻量脚本 smoke。
- 浏览器/MCP: 不需要。
- 长期服务: 不需要。

临时覆盖:

- 无。

## Git Context

主分支:

- `main`

任务类型:

- `feature`

工作分支:

- `harness/feature`

分支动作:

- already-on-branch

同步来源:

- 本规划阶段不合并主分支；实施前按 executor 规则复查主分支同步和分支占用。

最近同步:

- 未在本规划阶段执行。

分支占用:

- 串行 `git --no-optional-locks status --short --branch`: 当前分支 `harness/feature`。
- 当前可见未跟踪项: `.harness/.harness/`、`.harness/electron-feasibility/`、`.harness/electron-ui-verifier-asset-smoke/`。
- 这些未跟踪项为历史运行产物，本任务不清理、不提交。

Git 命令策略:

- 同一仓库 Git 命令必须串行。
- 非 Git 文件读取和文本搜索可并发，但不能和 Git 命令混在同一并发批次。
- 提交前继续使用 `git -c safe.directory=E:/work/hl/videoForensic/AI/dev-skills ...`。

提交策略:

- 规划阶段不提交，除非用户明确要求。
- 实施获批不等于提交授权；只有计划批准摘要明确授权阶段提交，或用户额外明确要求提交，才使用 `git commit -F` 提交信息文件。

分支安全:

- 不自动 stash。
- 不自动 rebase。
- 不自动 reset。

未解决问题:

- 无 blocking Git 问题。

## 工具

| 工具 | 用途 | 阶段 | 状态 | 风险 | 替代方案 | 用户确认 |
| --- | --- | --- | --- | --- | --- | --- |
| skill-creator | skill 结构原则、quick_validate | 全阶段 | 已读取 | 低 | 手工检查 | 已由任务触发 |
| complex-coding-harness | 当前规则来源和规划托管 | 规划阶段 | 已读取 | 中 | 手工计划 | 用户要求 |
| Python | guard 脚本和 smoke | Stage 5-6 | 当前可用 | 低 | PowerShell 文本检查 | 不需新增确认 |
| Git | rename、状态、提交 | 实施阶段 | 串行使用 | 中 | 不提交 | 提交需用户授权 |
| process-manager | 长期进程管理 | 本任务不需要 | 不适用 | 低 | 不启动长期进程 | 不需要 |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程:

- no

process-manager skill 是否存在:

- yes, repository contains `skills/process-manager`

规则结论:

- 本任务只涉及文件、脚本和有限命令验证，不启动 dev server、web 服务、worker 或 watcher。
- 如果实施中新增需要挂起的服务，必须重新评估本节并按 `process-manager` 管理。

需要托管的服务:

| 服务 | 类型 | 阶段 | service config | readiness | processKey | 日志/证据 | 清理状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | not required | all | none | none | none | not-applicable | not-applicable |

## 验证

必需验证:

- `quick_validate.py skills/complex-coding-planner`
- `quick_validate.py skills/complex-coding-executor`
- quick_validate 优先使用本机 `skill-creator` 脚本；如果路径不可用，必须记录原因，并用 frontmatter 解析、必需文件检查和命名规则检查作为替代验证。
- `python -m py_compile` 覆盖新增 guard 脚本。
- 两个 guard 脚本 `--help`。
- guard 脚本 smoke：未批准 fail、open decision fail、approved pass、transition pending stage 要求 continue。
- JSONL 解析和 id 唯一性，覆盖 planner/executor evals。
- YAML 或文本检查，覆盖 expected 文件。
- 关键规则检索，覆盖 planner/executor 和 evals。
- `git -c diff.autoRefreshIndex=false diff --check`

验证证据表:

| 阶段 | 命令/工具 | 结果 | 覆盖内容 | 未覆盖 | 证据/日志 | 处理 |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | 本地文件读取 | passed | 现有 harness、模板、eval、环境 | 未验证实现 | 本计划 Context | 继续 |
| Planning | 外部资料调研 | passed | 分工、guardrail、持久状态、人机审批原则 | 不引入框架 | 本计划 External sources | 继续 |
| Stage 1 | 关键规则迁移矩阵检索 | passed | 规则不遗漏 | 行为语义 | `rg` 命中迁移矩阵和旧规则来源 | 无需处理 |
| Stage 2 | executor quick_validate + rg | passed | executor 结构和关键执行规则 | 真实长任务 | `Skill is valid!`、关键规则命中 | 无需处理 |
| Stage 3 | planner quick_validate + 旧名检索 | passed | rename 和 metadata | 外部安装刷新 | `Skill is valid!`、旧 harness skill 目录已消失 | 无需处理 |
| Stage 4 | planner 规则检索和模板 review | passed | 规划职责和执行快照 | executor 真实消费 | planner workflow 226 行，SKILL 40 行，关键规则命中 | 无需处理 |
| Stage 5 | py_compile、help、guard smoke | passed | 检查脚本 | Markdown 语义判断 | py_compile/help/pass/fail smoke 通过；修复过一次 gate 顺序误判 | 无需处理 |
| Stage 6 | eval parse、expected、rg、diff check | passed | 整体一致性 | forward-test | JSONL/expected/rg 通过；diff check 仅换行符提示 | 无需处理 |

可选验证:

- 使用新 planner 为一个小型 managed 任务生成计划，再用 executor 检查脚本验证是否允许执行。
- 通过子 agent 或全新会话做 forward-test；如果会产生额外文件、耗时较长或需要额外权限，先请用户确认。

未覆盖:

- 不验证真实前后端项目。
- 不验证 Claude Code 自动安装行为。
- 不迁移历史任务文档。

无法执行时:

- 记录失败命令、原因、影响和替代验证；不能声明通过。

## 文档

必需更新:

- `skills/complex-coding-planner/SKILL.md`
- `skills/complex-coding-planner/references/planning-workflow.md`
- `skills/complex-coding-planner/templates/execution-plan.md`
- `skills/complex-coding-planner/templates/environment.md`
- `skills/complex-coding-planner/templates/pending-decisions.md`
- `skills/complex-coding-executor/SKILL.md`
- `skills/complex-coding-executor/references/execution-workflow.md`
- `evals/complex-coding-planner/*`
- `evals/complex-coding-executor/*`
- `CHANGELOG.md`

Changelog 计划:

- 增加 2026-07-06 条目，记录 `complex-coding-harness` 拆分为 planner/executor、新增状态检查脚本和 eval 更新。

## 文件写入策略

分段判断:

| 文件 | 分段判断 | 分段边界 | 整体复查方式 |
| --- | --- | --- | --- |
| `complex-coding-executor/SKILL.md` | no | 核心规则小节 | quick_validate、完整读取 |
| `complex-coding-executor/references/execution-workflow.md` | yes | 执行控制、阶段门禁、验证、Git、process-manager、提交、最终交付 | 完整读取、rg |
| `complex-coding-planner/SKILL.md` | no | 核心规则小节 | quick_validate、完整读取 |
| `complex-coding-planner/references/planning-workflow.md` | yes | 任务分级、上下文、方案质量、自查、审批、交接 | 完整读取、rg |
| `templates/execution-plan.md` | yes | 早期 Snapshot、规划区、执行区、门禁区 | 完整读取 |
| guard scripts | yes | helper、parser、checks、CLI、main | py_compile、smoke |
| eval files | no/unknown | 单组 fixture | JSONL/YAML 检查 |
| `CHANGELOG.md` | no | 单日期块 | 完整读取 |

写入规则:

- 分段 patch 是落盘策略，不是思考策略。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 目录复制或 rename 后，内容修改仍使用局部 patch。
- 目标文件超过 500 行时禁止整文件重写，优先局部 patch。
- 如果必须从旧 harness 复制到 executor，复制后必须读取新文件并按 executor 职责局部裁剪。

整体复查:

- 每个 skill 完成后完整读取 `SKILL.md` 和 reference。
- 检查 planner 是否仍包含实现阶段长循环；如果有，确认是否只是交接摘要。
- 检查 executor 是否包含所有执行门禁；如果缺失，先补齐再继续。
- 检查旧 `complex-coding-harness` 引用是否只存在于历史 changelog 或历史任务文档。

patch 失败处理:

- 先读取目标文件确认是否部分写入。
- 缩小到单小节 patch，不重复写已成功内容。
- 不用 shell 拼接文件绕过 patch 失败。

## 问题和覆盖项

| ID | 是否阻塞 | 状态 | 问题 | 决策 | 应用位置 |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | resolved | 是否保留 `complex-coding-harness` 兼容入口 | 默认不保留，按用户要求直接改名为 planner；如用户反悔则重新批准 | 目标结构、Stage 3 |
| D-002 | no | resolved | 是否引入 shared-core 第三 skill | 不引入，避免复杂化 | 决策 |
| D-003 | no | resolved | 是否引入第三方运行时框架 | 不引入，仅引用设计原则 | 非目标、工具 |
| D-004 | no | resolved | 是否新增检查脚本 | 新增 planner/executor 各一个轻量 Python 脚本 | Stage 5 |

## 方案质量门禁

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 关键判断有证据等级 | passed | Context 证据等级表 |
| 影响面矩阵完整 | passed | 已覆盖 API、数据、配置、兼容、测试、文档 |
| 候选方案比较充分 | passed | A/B/C 三种方案 |
| 每阶段可独立验证 | passed | Stage 1-6 均有退出验证 |
| 方案变更触发条件清楚 | passed | 决策章节 |
| 用户批准摘要可记录 | passed | Plan Approval 章节 |

质量结论:

- passed

## 规划自查

自查结论:

- passed after adjustments

| 类别 | 发现 | 处理 | 结果 |
| --- | --- | --- | --- |
| 缺陷 | 初始拆分可能直接删旧 harness 规则 | 规定 Stage 1 迁移矩阵和 Stage 2 先复制 executor | fixed |
| 优化 | 三 skill shared-core 会增加触发和维护复杂度 | 选择两 skill，`.harness` 作为共享契约 | fixed |
| 缺失项 | 需要防止未批准计划被 executor 执行 | Stage 5 新增 `harness_exec_check.py` | fixed |
| 风险 | planner 裁剪过度可能导致 plan 不可执行 | 保留完整 `execution-plan.md` 模板和 Execution Control Snapshot | fixed |
| 一致性 | 用户要求 direct rename，方案不能保留旧 harness 入口 | Stage 3 明确旧目录改名，不保留兼容入口 | fixed |
| 缺陷 | 本地文档上下文仍描述 `active-task.json` 指向上一个任务 | 修正为当前任务 `awaiting_plan_approval` 状态 | fixed |
| 风险 | “按方案执行”可能被误解为提交授权 | 明确实施批准不等于提交授权，提交需单独授权或批准摘要记录 | fixed |
| 缺失项 | 迁移矩阵缺少最低覆盖清单 | 补充任务分级、Git、审批、阶段门禁、process-manager、验证、提交和最终交付等规则族 | fixed |
| 优化 | quick_validate 路径可能在不同环境不可用 | 增加 frontmatter、必需文件和命名规则替代验证 | fixed |

门禁重跑:

- `Plan Quality Gate` 是否需要重跑: no
- `Plan Self-Review` 是否需要重跑: no
- `Readiness Gate` 是否需要重跑: no
- 原因: 自查修复未改变已选方案，只补强顺序、验证和风险处理。

## 就绪门禁

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 目标和验收清楚 | passed | 问题定义 |
| 上下文已收集 | passed | 本地代码、本地文档、外部来源、用户约束 |
| 候选方案已比较 | passed | 方案 A/B/C |
| 决策已记录 | passed | 选择方案 B |
| 实施阶段已细化 | passed | Stage 1-6 |
| 环境已确认 | passed | `.harness/environment.md` |
| Git 上下文已确认 | partial | 已串行检查当前分支和未跟踪项；实施前需复查同步 |
| 工具已确认 | passed | 工具表 |
| 验证已确认 | passed | 验证章节 |
| 最终交付证据已规划 | passed | Stage 6 和验证证据表 |
| 文档更新已确认 | passed | 文档章节 |
| 风险已识别 | passed | 各阶段风险和回滚 |
| 规划自查已通过 | passed | Plan Self-Review |
| 阻塞问题已关闭 | passed | 无 blocking |

就绪结论:

- ready for user plan approval

## 方案批准

状态:

- approved_for_implementation

批准记录:

- 2026-07-06 已按用户要求使用当前 `complex-coding-harness` 制定 planner/executor 拆分方案。
- 2026-07-06 用户回复“开始吧”，批准按本计划进入实施阶段。
- 2026-07-06 用户回复“要提交代码的啊”，明确授权提交本次拆分改动。

批准摘要:

- 批准范围: 执行 Stage 1-6，完成 skill 拆分、检查脚本、eval、changelog 和任务状态更新。
- 阶段提交授权: 已授权提交本次拆分改动，提交信息使用 `git commit -F` 文件方式。
- 工具/MCP 授权: 不需要 MCP；Python/Git/quick_validate 为 finite command。
- 文档更新授权: 已授权更新本任务相关 skill 文档、eval、changelog 和 harness 状态。

提交策略:

- authorized_current_request

## 执行控制

执行模式:

- run-to-completion

整体任务状态:

- completed

当前阶段:

- Final delivery

已完成阶段:

- Planning
- Stage 1
- Stage 2
- Stage 3
- Stage 4
- Stage 5
- Stage 6

剩余阶段:

- none

下一步自动动作:

- final delivery

当前停止条件:

- all approved stages completed

状态来源:

- execution-plan.md

阶段边界是否允许停止:

- no, unless the user explicitly requested stage-only execution or a Stop Condition is active

active-task 同步字段:

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "current_stage": "Final delivery",
  "remaining_stages": [],
  "next_automatic_action": "final delivery",
  "stop_condition": "all approved stages completed",
  "state_source": "execution-plan.md"
}
```

## 实施进度

| 阶段 | 状态 | 摘要 | 验证 | 证据 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| Planning | completed | 已完成 planner/executor 拆分方案、调研、质量门禁和自查 | passed | 本计划 | 等待用户批准 |
| Stage 1 | completed | 已完成旧 harness 规则族迁移矩阵，未废弃任何规则语义 | passed | 关键规则 `rg` 检索 | Stage 2 |
| Stage 2 | completed | 已创建 executor skill 并迁移执行规则 | passed | quick_validate、关键规则 `rg` | Stage 3 |
| Stage 3 | completed | 已将旧 harness 目录改名为 planner，并更新基础 metadata 和 workflow 引用 | passed | quick_validate、旧名检索 | Stage 4 |
| Stage 4 | completed | 已裁剪 planner 工作流并新增 Execution Control Snapshot | passed | quick_validate、关键规则检索 | Stage 5 |
| Stage 5 | completed | 已新增 planner/executor 检查脚本并完成正向和负向 smoke | passed | py_compile、help、preflight、transition、final/open-decision smoke | Stage 6 |
| Stage 6 | completed | 已拆分 eval、更新 changelog，并完成整体验证 | passed | quick_validate、py_compile、help、smoke、JSONL/expected、rg、diff check | Final delivery |

## 阶段进入门禁

| 阶段 | 当前分支/工作区 | 上阶段遗留 | 环境和工具 | 长期进程门禁 | 范围匹配 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | passed | none | passed | not-applicable | passed | passed |
| Stage 2 | passed | Stage 1 matrix completed | passed | not-applicable | passed | passed |
| Stage 3 | passed | executor completed | passed | not-applicable | passed | passed |
| Stage 4 | passed | planner rename completed | passed | not-applicable | passed | passed |
| Stage 5 | passed | planner/executor structure completed | passed | not-applicable | passed | passed |
| Stage 6 | passed | guard scripts completed | passed | not-applicable | passed | passed |

## 阶段退出门禁

| 阶段 | 目标完成 | Review 完成 | 验证完成 | 长期进程清理和证据 | 关键日志已沉淀 | 记录更新 | 提交记录 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-request | passed |
| Stage 2 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-request | passed |
| Stage 3 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-request | passed |
| Stage 4 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-request | passed |
| Stage 5 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-request | passed |
| Stage 6 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-request | passed |

## 阶段转移门禁

| 阶段 | 当前阶段已完成 | Review 已完成 | 验证已完成或替代证据已记录 | 提交或未提交原因已记录 | 是否还有 pending stage | 是否存在停止条件 | 是否需要重新批准 | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止 | 下一动作 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | yes | yes | yes | not-applicable | yes | yes | no | yes | yes | yes | wait for user approval |
| Stage 1 | yes | yes | yes | authorized-current-request | yes | no | no | yes | yes | no | continue Stage 2 |
| Stage 2 | yes | yes | yes | authorized-current-request | yes | no | no | yes | yes | no | continue Stage 3 |
| Stage 3 | yes | yes | yes | authorized-current-request | yes | no | no | yes | yes | no | continue Stage 4 |
| Stage 4 | yes | yes | yes | authorized-current-request | yes | no | no | yes | yes | no | continue Stage 5 |
| Stage 5 | yes | yes | yes | authorized-current-request | yes | no | no | yes | yes | no | continue Stage 6 |
| Stage 6 | yes | yes | yes | authorized-current-request | no | yes | no | yes | yes | yes | final delivery |

结论:

- 规划阶段完成，按用户审批门禁停止。用户批准后进入 Stage 1，实施阶段默认 run-to-completion。
- Stage 1 已完成，仍有 pending stage 且无停止条件，继续 Stage 2。
- Stage 2 已完成，仍有 pending stage 且无停止条件，继续 Stage 3。
- Stage 3 已完成，仍有 pending stage 且无停止条件，继续 Stage 4。
- Stage 4 已完成，仍有 pending stage 且无停止条件，继续 Stage 5。
- Stage 5 已完成，仍有 pending stage 且无停止条件，继续 Stage 6。
- Stage 6 已完成，全部批准阶段完成，进入最终交付。

## 代码审查

| 阶段 | 问题 | 严重程度 | 处理 |
| --- | --- | --- | --- |
| Planning | 仅新增规划文档，未修改 skill 本体 | follow-up | 实施阶段执行代码 review |
| Planning | 方案可能遗漏旧规则 | major-risk | 已加入 Stage 1 迁移矩阵、关键规则检索和“先复制 executor 再裁剪 planner”顺序 |
| Planning | 检查脚本可能误判 Markdown 状态 | minor-risk | 脚本只做结构检查，失败提示人工复查，不自动修改 |
| Planning | 提交授权语义可能不够严格 | major-risk | 已明确“实施批准不等于提交授权”，executor 只有单独授权时才能 commit |
| Stage 1-6 | 未发现 blocking 或 major 问题；planner 不再承载执行长循环，executor 承接阶段门禁、验证、Git/process 和最终交付；检查脚本为结构 guardrail，不替代人工判断 | none | 无需修复 |

## 恢复摘要

- 整体目标: 将 `complex-coding-harness` 拆分为 `complex-coding-planner` 和 `complex-coding-executor`，提升规划/执行阶段稳定性。
- 执行模式: planning-only。
- 整体任务状态: completed。
- 已完成阶段: Planning、Stage 1、Stage 2、Stage 3、Stage 4、Stage 5、Stage 6。
- 当前阶段: Final delivery。
- 剩余阶段: none。
- 最新 commit: current commit。
- 下一步自动动作: final delivery。
- 当前停止条件: all approved stages completed。
- 状态来源: execution-plan.md。
- 长期进程规则: 本任务不需要长期进程；如实施中新增长期服务，必须按 process-manager 管理。
- 未覆盖/风险: 未做真实长任务 forward-test；本次覆盖结构校验、脚本 smoke 和 fixture 检查。本轮已授权提交。
- 不得停止说明:
  - 用户批准实施后默认 run-to-completion，不能在 Stage 1-5 阶段边界提前最终回复。

## 提交记录

提交信息方式:

- 使用 `.harness/tasks/2026-07-06/feature/complex-coding-planner-executor-split/tmp/commit-message.txt` 和 `git commit -F`。
- 禁止用多个 `-m` 分别传入 bullet。
- 标题和 bullet 之间保留一个空行，bullet 之间不加空行。

| 阶段 | 仓库 | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | current commit | included with implementation records | not changed |
| Stage 1-6 | dev-skills | current commit | `feat(complex-coding): 拆分 planner 和 executor` | `CHANGELOG.md` 2026-07-06 Stage 43 |

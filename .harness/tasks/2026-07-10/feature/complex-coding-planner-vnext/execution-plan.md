# complex-coding-planner / executor 最新契约联合升级执行计划

## 执行控制快照（Execution Control Snapshot）

- 执行模式：`run-to-completion`
- 整体任务状态：`completed`
- 当前阶段：`Final`
- 已完成阶段：规划调研、Plan Quality Gate、Plan Self-Review、Readiness Gate、`STG-01`、`STG-02`、`STG-03`、`STG-04`、`STG-05`、`STG-06`
- 剩余阶段：无
- 下一步自动动作：`final commit and delivery`
- 当前停止条件：`goal_condition_met`
- 状态来源：本文件
- 执行方：使用 `complex-coding-executor` 连续实施；用户已授权完成全部阶段后提交代码

## 执行契约（Execution Contract）

```json
{
  "contract_version": 1,
  "task_id": "2026-07-10-feature-complex-coding-planner-vnext",
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "approval_status": "approved",
  "approved_contract_hash": "external:attestation.json",
  "current_stage_id": "Final",
  "remaining_stage_ids": [],
  "stop_condition": "goal_condition_met",
  "commit_authorization": "final_commit_authorized",
  "ledger_policy": "append-only-after-approval",
  "single_writer": "current executor session",
  "reapproval_required": false
}
```

契约规则：

- 本文件按当前 planner/executor 规则作为一次性自举控制；交付后直接使用单一最新契约，不保留版本字段、版本分派或兼容入口。
- 上方唯一的版本控制字段只为满足当前 bootstrap checker 的固定输入要求，不属于目标 task contract，STG-06 切换后不得进入 skill、模板或运行脚本。
- 实施期先通过显式测试路径构建并验证新的 producer/consumer，STG-06 再原子替换默认入口和删除旧规则，避免中途失去本任务控制面。
- 最新契约中，`execution-plan.md` 与 `plan-contract.json` 是不可变批准集合；`run-state.json` 与 `ledger.jsonl` 由 executor 独占写入。
- approved scope、阶段边界、必需验证、状态所有权、风险等级、工具授权或提交策略改变时进入 Plan Amendment Gate。

## 目标条件（Goal Condition）

- 所有 approved stages `STG-01` 至 `STG-06` 均 complete。
- `REQ-01` 至 `REQ-14`、`NFR-01` 至 `NFR-08` 均有实现和验证证据。
- planner producer、executor consumer、ledger replay、attestation/amendment、skill validator、最新契约集成验证和 `final checker` 通过。
- 最终仓库不存在旧契约分派、双写状态规则或历史恢复承诺；缺少最新 task contract 的任务按结构缺失/无效失败。
- 无 open blocking decision、无未关闭 blocking/major review finding。
- 必需验证已执行；不能执行的项记录原因、影响、替代证据和用户可见残余风险。
- 提交授权明确；只有用户授权后才使用 `git commit -F`，否则不得提交并记录原因。

## 规划循环协议（Planning Loop Protocol）

- 每轮重大决策前重读目标、约束、Options、Decision、影响面和 traceability。
- 浏览多个来源后的关键 findings 已写入 `artifacts/research/research-findings.md`，后续新增证据继续落盘。
- rejected options 及原因必须保留，防止上下文压缩后重复探索。
- 发现高影响未知时使用最便宜的区分性探针；不能用更多文档掩盖未知。
- Readiness 前重跑 Plan Quality Gate、Plan Self-Review 和 Readiness Gate；批准后变更按 Amendment Gate 处理。

## 执行循环协议（Executor Work Loop）

- 每个阶段开始读取 Execution Contract、Resume Packet、对应 Stage Contract、traceability 和上阶段 findings。
- 每次实质动作后更新 ledger/progress；失败必须记录 attempt、命令/工具、原因、影响与下一策略。
- 阶段实现后先做本阶段 review 和 required validation，再进入 Stage Exit/Transition Gate。
- Stage Transition Gate 通过且仍有剩余阶段时，下一动作必须是 `continue Stage N`，不得把阶段边界当停止条件。
- 只有满足 Goal Condition 和 final checker 后才能最终交付。

## 问题定义（Problem）

目标：

- 将 planner 与 executor 绑定升级为单一最新契约：风险自适应规划、机器契约、不可变批准意图、单写者运行状态和可重放证据。
- 提升 discovery、需求追踪、影响分析、独立评审、执行恢复、amendment 和联合 eval 能力。
- 降低简单任务固定成本，同时消除 attestation 与计划双写冲突，不削弱审批、安全、review 和验证能力。

非目标：

- 不修改 `gitlab-pat-ops`、`electron-ui-verifier`、`process-manager` 等无关 skill。
- 不引入后台服务、数据库、第三方 runtime 依赖或完整复制 Spec Kit/planning-with-files。
- 不迁移或兼容历史 `.harness/tasks`；旧任务仅作为历史文件保留，新工具不保证恢复或验证。
- 不保留旧契约 parser、版本 dispatch、以 Markdown 承载可变状态或 active-task 状态镜像。
- 不改变 Git 分支模型和用户授权边界。
- 本规划轮不实施、不测试目标代码、不提交。

验收标准：

- 以 `artifacts/validation/traceability.md` 中 `AC-01` 至 `AC-18` 为准。
- 核心结果包括 profile 路由、四层任务制品、稳定 ID、planner/executor conformance、ledger replay、单一契约切换和可执行 eval。

约束：

- 遵循当前 planner 的 3-7 阶段、研究/规范/质量门禁、分段 patch、审批前停止规则。
- 新增/修改注释使用中文；代码保持当前 Python 风格并优先标准库。
- `SKILL.md` 保持精炼，避免与 references/templates 重复。
- 同一仓库 Git 命令串行；不得覆盖或回退用户变更。

待确认项：

- 无阻塞项。本计划只作为当前规则下的一次性 bootstrap carrier；STG-06 完成后目标实现不含版本判断或兼容逻辑。
- 独立 clean-context evaluator 若当前工具环境不可用，可按计划记录降级证据，但 full profile 的 critique 契约仍需实现。

## 调研门禁（Research Gate）

- 研究模式：`online-required`
- 触发原因：agent harness、spec-driven workflow 与 2025-2026 长时软件工程评测均在快速演进，且用户明确要求前沿深入调研。

不确定项清单：

| ID | 问题 | 类型 | 在线 | 处理结果 | 影响 |
| --- | --- | --- | --- | --- | --- |
| U-01 | 统一重模板是否仍是合理默认 | local-code + external | yes | 否；采用风险自适应 profile | 核心架构 |
| U-02 | 是否应把所有内容拆成独立文件 | architecture | yes | 否；按所有权拆成批准意图、机器契约、运行状态、证据四层 | 状态与上下文 |
| U-03 | 独立 evaluator 是否每次强制 | external-tool | yes | 否；full/高风险条件启用 | 成本与质量 |
| U-04 | 当前 checker 是否足以门禁 | local-code | no | 否；复现实验证明语义误放行 | 安全与可信度 |
| U-05 | 是否需要服务/数据库 | architecture | no | 否；文件 + Python 标准库足够 | 维护成本 |
| U-06 | 直接替换下如何安全自举 | architecture | yes | 通过显式测试路径先构建新实现，最终原子替换并删除旧入口 | 实施连续性 |

搜索记录：

| 查询/来源 | 工具 | 日期 | 结果 | 后续动作 |
| --- | --- | --- | --- | --- |
| OpenAI/Anthropic harness 与 context engineering | web | 2026-07-10 | 支持渐进披露、机械约束、风险适配与独立评审 | 转化为 DEC-01/03/05/06 |
| GitHub Spec Kit workflow/analyze/clarify | web + repo | 2026-07-10 | 支持跨制品分析、影响 x 不确定性澄清和 review gate | 有选择吸收，不复制布局 |
| CodePlan/PlanSearch/Agentless/SWE 系列论文 | web | 2026-07-10 | 支持依赖感知规划、多维评测与简单基线 | 形成 change map 与 eval 设计 |
| 本地 24 份计划、checker、eval | shell/read | 2026-07-10 | 证实文档膨胀、语义检查缺口与 eval 不可执行 | 纳入 LE-01 至 LE-07 |
| planning-with-files v3.4.0 | local repo | 2026-07-10 | 分离 findings/progress 与恢复机制有价值，小任务有开销 | 采用思想，拒绝全套 hooks |
| JSON Schema、Spec Kit state/resume、Magentic-One ledgers | web | 2026-07-10 | 支持机器契约、状态/日志分离和外层计划/内层进度循环 | 形成四层所有权与联合 contract tests |
| executor attestation/resolver/checker/ledger 本地复核 | shell/read | 2026-07-10 | 证实 plan 哈希与 plan 可变更新冲突、active-task 重复状态 | 删除双写，run-state 单写者 |

来源矩阵：

| 结论 | 来源类型 | URL/路径 | 官方/一手 | 访问日期 | 可信度 | 影响 |
| --- | --- | --- | --- | --- | --- | --- |
| 入口应短且渐进披露 | official | https://openai.com/index/harness-engineering/ | yes | 2026-07-10 | high | artifact 架构 |
| 完整计划应自包含并可恢复 | official | https://developers.openai.com/cookbook/articles/codex_exec_plans | yes | 2026-07-10 | high | full profile |
| 规格、计划、任务可分离并分析覆盖 | official | https://github.github.com/spec-kit/ | yes | 2026-07-10 | high | traceability |
| 依赖与影响分析改善跨文件规划 | primary | https://arxiv.org/abs/2309.12499 | yes | 2026-07-10 | medium | change map |
| JSON 可用标准结构约束 | primary | https://json-schema.org/draft/2020-12 | yes | 2026-07-10 | high | plan contract |
| state 与 log 分离支持精确恢复 | official | https://github.github.com/spec-kit/reference/workflows.html#state-and-resume | yes | 2026-07-10 | high | run-state/ledger |
| task/progress 双 ledger 支持规划和恢复 | primary | https://arxiv.org/abs/2411.04468 | yes | 2026-07-10 | medium | planner/executor loop |
| 当前计划会被 checker 语义误放行 | local | `harness_plan_check.py` + 完成计划复现 | yes | 2026-07-10 | high | semantic checker |

完整研究证据：`artifacts/research/research-findings.md`。

调研结论：`passed`。核心方案已按用户决策收敛为单一最新契约的联合升级；实施阶段只对新发现的高影响未知补充定向研究，不再设计版本或兼容体系。

## 规范发现门禁（Standards Discovery Gate）

- 发现模式：`online-required`

技术栈清单：

| 类型 | 发现 | 来源 | 影响 |
| --- | --- | --- | --- |
| 语言 | Python 3 + Markdown + JSON/YAML | 当前 scripts/templates | checker、tests、metadata |
| 框架 | 无应用框架，优先 Python 标准库 | 当前实现 | 不新增 runtime 依赖 |
| API/架构 | 最新 JSON 文件契约、不可变批准集合、run-state/ledger、CLI checker | planner/executor + 外部研究 | 联合替换 |
| 工具链 | `apply_patch`、PowerShell、Git、unittest、skill validator | 仓库与系统规则 | 分段写入和确定性验证 |

规范来源矩阵：

| 规范来源 | 类型 | 官方/一手 | 适用边界 | 访问日期 | 影响 |
| --- | --- | --- | --- | --- | --- |
| 会话 `AGENTS.md` | project | yes | 全部改动 | 2026-07-10 | 最高优先级 |
| planner/executor 当前 SKILL/workflow | project | yes | 触发、交接、恢复 | 2026-07-10 | 联合替换协议，保留安全能力 |
| Codex `skill-creator` | architecture | yes | skill 结构与验证 | 2026-07-10 | 渐进披露、metadata |
| https://google.github.io/styleguide/pyguide.html | language | yes | Python 代码 | 2026-07-10 | 命名、异常、main、类型 |
| https://docs.python.org/3/library/unittest.html | language | yes | checker/eval 测试 | 2026-07-10 | 标准库测试 |
| https://google.github.io/styleguide/docguide/style.html | other | yes | Markdown 文档 | 2026-07-10 | 可扫描结构 |
| https://json-schema.org/draft/2020-12 | data contract | yes | contract/state 结构 | 2026-07-10 | required/type/enum/closed shape |
| https://github.github.com/spec-kit/reference/workflows.html#state-and-resume | architecture | yes | 持久状态与恢复 | 2026-07-10 | state/log 分离 |
| https://arxiv.org/abs/2411.04468 | architecture | yes | planner/executor 双循环 | 2026-07-10 | task/progress ledger |

standards index：

- 路径：`artifacts/standards/standards-index.md`
- 摘要：项目规则优先，外部规范约束 Python、Markdown、skill 信息架构和契约结构；本地风格优先于一般风格建议。
- 未覆盖或 blocked-by-access：无。

规范发现结论：`passed`。

## 开发质量门禁（Development Quality Gate）

质量范围：

| 维度 | 规划结论 | 阶段映射 | 验证映射 |
| --- | --- | --- | --- |
| 代码标准 | Python 标准库、清晰类型/异常/CLI 诊断、中文新增注释 | STG-02/03/04/05 | VAL-09/10/12 |
| 静态质量 | validator/reducer 纯规则函数分离，避免深层隐式字符串判断 | STG-02/03/04 | VAL-03/06/09/12 |
| 架构边界 | planner 独占批准意图；executor 独占 run-state/ledger；契约连接两端 | STG-01/02/03/04 | VAL-04/05/06/07 |
| 设计模式取舍 | Strategy/Profile、State Machine、Reducer、Validator chain；不建 workflow engine | STG-01/02/03/04 | 单测 + review |
| 低耦合 | 双方只依赖最新 contract IDs/events，不依赖对方 prose | STG-01/02/03/04 | VAL-04/05 |
| 高内聚 | planner producer、executor consumer、state reducer、eval 分层 | STG-02/03/04/05 | VAL-09/10/11 |

过度设计防护：

- 不引入工作流引擎、动态插件、通用图数据库或第三方 schema runtime。
- profile 数量固定为三档；先用可解释规则，不做自学习评分器。
- artifact 按触发条件生成，不要求每个任务拥有完整目录树。
- checker 只验证明确契约 invariant，不尝试用复杂 NLP 判断 prose “好不好”。
- 独立 critique 仅在 full/高风险启用；不能使用时明确降级。
- 不引入数据库、消息总线、Temporal 服务或完整 JSON Schema runtime；使用受控 JSON shape 与项目语义 validator。

开发质量结论：`passed`。

## 上下文（Context）

本地代码：

- `skills/complex-coding-planner/SKILL.md`：当前触发、managed/direct、研究和审批核心规则。
- `references/planning-workflow.md`：337 行完整流程，已有 Research/Standards/Quality/Readiness/Approval。
- `templates/execution-plan.md`：811 行固定全量模板，是计划膨胀的直接来源之一。
- `scripts/harness_plan_check.py`：仅标题、关键词、字段存在检查，缺少跨字段语义。
- `evals/complex-coding-planner/`：15 个 prompt 与 expected，但无可执行 runner 和 plan fixtures。
- `complex-coding-executor`：当前从 plan prose/embedded JSON 与 active-task 双重读取状态，并在执行中回写 plan；本任务将整体替换为最新 contract consumer。
- `harness_attest_plan.py`：当前哈希会被 executor 持续修改的 plan，正常执行会触发证明漂移；新 attestation 只覆盖不可变批准集合。

本地文档与历史状态：

- 24 份历史 execution-plan 中位数约 881 行，近期多超过 1100 行。
- `.harness/environment.md` 混合稳定环境事实和 13 次历史任务约束，存在陈旧上下文风险。
- 当前工作分支与 `main` 在本任务开始前无提交或文件差异；当前变更仅为本任务 harness 规划制品。
- 完整变更范围见 `artifacts/architecture/change-map.md`。

外部来源：

- 研究矩阵与适用限制见 `artifacts/research/research-findings.md`。
- 规范及优先级见 `artifacts/standards/standards-index.md`。
- 最新文件、字段、所有权、事件、attestation 和自举基线见 `artifacts/architecture/task-contract-outline.md`。
- 需求、验收与验证映射见 `artifacts/validation/traceability.md`。

用户约束：

- 深入调研前沿并真实吸收适合本项目的能力。
- 按当前 harness/planner 规则落盘详细修改方案。
- 当前只规划；等待批准后才按 executor 实施。

证据等级：

| 结论 | 等级 | 来源 | 影响 |
| --- | --- | --- | --- |
| 当前模板导致实际计划膨胀 | confirmed | 模板与 24 份历史计划统计 | profile + artifacts |
| checker 会语义误放行 | confirmed | 代码阅读与完成计划复现 | semantic checker |
| 渐进披露能改善上下文效率 | external | ES-01/03/06 | SKILL 与 artifact 架构 |
| 风险适配优于普适 evaluator | external | ES-05/14/20 | profile 与 critique |
| 稳定 ID 可提升覆盖检查 | external + design | ES-09/19 | traceability |
| 当前 attestation 与 plan 可变更新冲突 | confirmed | LE-09，本地脚本与 workflow | immutable approval set |
| state/log 与 task/progress 分层适合恢复 | external + inference | ES-22/23 + LE-10 | run-state/ledger ownership |
| 三档 profile 的阈值 | assumption | 本地任务分布推导 | 必须用 eval 校准 |

## 规划画像（Planning Profile）

- 生命周期路由：`managed`
- 当前计划 profile：`full`
- discovery-first：已在本轮完成，不再阻塞实施计划。

风险评分：

| 信号 | 分值 | 依据 |
| --- | --- | --- |
| 影响面 | 3/3 | 绑定替换 planner producer、executor consumer 和任务状态协议 |
| 不确定性 | 2/3 | 主方向稳定，profile 阈值、replay 和原子切换需实现验证 |
| 变更跨度 | 3/3 | SKILL、workflow、template、checker、eval、executor |
| 时间/恢复跨度 | 3/3 | 6 阶段，多次验证与可能跨会话执行 |
| 可逆性 | 3/3 | 用户选择破坏性切换，完成后旧任务不可由新版恢复 |
| 外部写入/权限 | 1/3 | 仅本仓库文件和可选 Git 提交 |

结论：15/18，使用 full profile；同时将“如何降低 lite 开销”和“如何证明单一最新契约的原子切换完整”作为首要验收。

## 候选方案（Options）

### 方案 A：原地重写单一 Markdown 协议

- 做法：planner/executor 同时改用新版 `execution-plan.md`，但仍把批准、状态、进度和证据写在一个文件中。
- 优点：文件数量少，表面切换直接。
- 缺点：LE-09/LE-10 的 attestation 漂移与双写根因仍存在，checker 继续依赖 Markdown 解析。
- 风险：新语法更严格但所有权不清，恢复时仍可能出现状态冲突。
- 验证：状态更新后的 attestation、active-task/plan drift fixtures。
- 回滚：恢复旧模板，无法形成新的状态所有权架构。

### 方案 B：四层任务制品 + planner/executor 单一契约切换

- 做法：planner 产出不可变 `execution-plan.md`、`plan-contract.json` 和条件 artifacts；executor 只写 `run-state.json` 与 `ledger.jsonl`；attestation 哈希批准集合；双方共享 contract IDs 和 conformance fixtures；最终只保留这一套实现。
- 优点：直接解决默认开销、语义误放行、attestation 漂移、双状态源和恢复问题；每个 writer/真相源清楚。
- 缺点：planner/executor/scripts/templates/evals 必须绑定开发，切换面比原方案更大。
- 风险：字段过多、contract/Markdown 漂移、ledger/state 不一致、原子切换遗漏旧路径。
- 验证：producer-consumer conformance、replay/reconcile、attestation/amendment、缺失/无效 contract 和仓库旧规则检索。
- 回滚：STG-06 切换前可回退显式测试路径中的新实现；切换后只通过 Git 回退整个变更，不保留运行时兼容分支。

### 方案 C：合并 planner/executor 或引入工作流服务

- 做法：把两个 skill 合并为单 skill，或引入数据库/Temporal 式服务统一调度。
- 优点：内部状态集中，可实现更强事务和调度。
- 缺点：破坏“规划审批前停止、执行只消费批准计划”的职责隔离，部署和依赖成本过高。
- 风险：一个角色同时规划、批准后执行和自评，边界模糊；服务成为新故障点。
- 验证：需要全新端到端系统测试。
- 回滚：成本高，不适合当前文件式 skill 仓库。

## 决策（Decision）

- 选择方案：B。
- 原因：它直接对应 LE-01 至 LE-10，并与渐进披露、state/log 分离、task/progress ledger、机器契约和风险路由证据一致。
- 影响：planner 与 executor 作为一个契约单元共同修改；新增 plan contract、run-state、reducer/reconcile、联合 checker/eval 和双 skill metadata。
- 可逆性：STG-06 前通过并行实现可回退；最终为用户明确接受的 breaking cutover，不提供旧任务恢复。
- 变更条件：若 semantic checker 必须依赖复杂 Markdown parser 才能稳定工作，优先收窄最新契约语法，不新增第三方运行依赖。

方案决策记录：

| ID | 决策 | 理由 |
| --- | --- | --- |
| DEC-01 | 生命周期路由与 `lite/standard/full` profile 分离 | 避免把任务是否 managed 与文档深度混为一谈 |
| DEC-02 | 增加 discovery-first 与高价值澄清协议 | 未知目标不应伪装成完整计划 |
| DEC-03 | planner 产出人类计划、机器契约和条件 artifacts | 渐进披露且把 enforceable 字段从 prose 分离 |
| DEC-04 | 批准集合不可变，使用稳定 ID 与闭环 traceability | 让覆盖、断链和 amendment 可机械验证 |
| DEC-05 | planner checker 验证结构、graph、授权和跨制品语义 | 修复关键词 PASS 的根因 |
| DEC-06 | executor 独占 `run-state.json` 与 `ledger.jsonl` | 消除 plan/active-task 双写 |
| DEC-07 | ledger 为执行历史，run-state 为可重建快照 | 支持崩溃恢复和 drift reconcile |
| DEC-08 | attestation 只覆盖不可变批准集合 | 正常进度更新不再破坏证明 |
| DEC-09 | active-task 退化为恢复指针 | 生命周期只从 run-state 读取 |
| DEC-10 | full/高风险才要求独立 critique | 平衡自评偏差与流程成本 |
| DEC-11 | planner/executor 使用同一 conformance matrix | 绑定 producer/consumer，防止协议漂移 |
| DEC-12 | 两个 skill 都补齐 metadata、reference 和 validator | 提升可发现性和独立使用质量 |
| DEC-13 | 最终只保留单一最新契约，不设置版本字段或分派 | 落实用户直接按最新方案替换的要求 |
| DEC-14 | 保留审批、权限、Research Drift、review 和安全门禁 | 新架构不能削弱行为保障 |
| DEC-15 | Python 标准库与文件制品，不引入服务 | 控制复杂度并保持 Windows 可用 |

方案变更触发条件：四层所有权、单一契约决策、Stage DAG、attestation 集合、ledger/reconcile 语义、profile 模型、第三方依赖/服务或审批安全边界改变，均需重新批准。

## 影响面矩阵（Impact Matrix）

| 影响对象 | 是否涉及 | 文件/模块 | 风险 | 验证方式 | 文档更新 |
| --- | --- | --- | --- | --- | --- |
| API | yes | 最新 task bundle、planner/executor checker CLI、event schema | high | VAL-02 至 VAL-08 | contract/cutover docs |
| 数据结构 | yes | plan-contract、run-state、ledger events、attestation、active pointer | high | structure + semantic + replay tests | template/reference |
| 前端交互 | no | 无 UI | low | 不适用 | 无 |
| 配置/环境 | yes | 双 skill `agents/openai.yaml`、environment、pointer-only active-task | medium | VAL-10 + state fixtures | SKILL/reference |
| 历史任务 | breaking | 不迁移、不恢复；缺少最新 contract 时按结构无效失败 | high | VAL-08 + 仓库旧规则检索 | cutover notes |
| 测试 | yes | producer-consumer、checker、replay、attestation、eval runner | high | VAL-01 至 VAL-12 | eval README |
| 文档 | yes | SKILL、workflow、templates、changelog | medium | 全文件审查 | 必需 |
| 代码标准 | yes | Python scripts/tests | medium | py_compile/unittest/review | standards index |
| 架构设计 | yes | immutable intent/contract、single-writer state、event evidence | high | ownership + conformance + recovery review | change map |

详细文件和依赖方向见 `artifacts/architecture/change-map.md`。

## 实施计划（Implementation Plan）

### 阶段 1（STG-01）：定义联合最新契约、状态所有权与自举切换

目标：

- 在修改任一 skill 行为前，锁定 planner producer 与 executor consumer 共同使用的最新 task bundle、状态机、事件和 breaking cutover 边界。

做法：

- 定义两轴模型：生命周期 `direct/managed/blocked` 与深度 `lite/standard/full`；高影响未知进入 discovery-first。
- 定义 task bundle：不可变 `execution-plan.md`、`plan-contract.json`、批准 artifacts 和 `attestation.json`；可变 `run-state.json`、`ledger.jsonl`；pointer-only `active-task.json`。
- 定义 `plan-contract.json`：task/profile、REQ/AC/NFR、Stage DAG/Stage Contract、VAL、artifact index、风险、授权和 reapproval triggers。
- 定义 `run-state.json`：lifecycle、current/completed/remaining、stop/next、revision、last_event_seq；仅 executor 写入。
- 定义 ledger event envelope、事件类型、顺序号、stage/validation/review evidence 和 reducer invariant；run-state 必须可 replay/reconcile。
- 定义 attestation 的不可变哈希集合、approval record、plan revision 和 amendment 链；明确 mutable 文件不参与哈希。
- 定义 active-task 只保存 task_id/task_dir/run_state_path，不复制 lifecycle；environment 只存稳定 workspace 事实。
- 定义单一契约策略：不设置版本字段或版本 dispatch；缺少/不符合最新 contract shape 时明确结构错误。
- 定义自举：STG-01 至 STG-05 通过显式测试入口构建新模块/fixtures，当前 plan 只控制本次任务；STG-06 一次替换默认入口并删除旧路径。

原因：

- LE-09/LE-10 证明当前问题不仅是模板重，而是批准意图、证明和可变状态所有权冲突；联合契约必须先于任一侧实现。

位置：

- 文件/模块：planner 新增 `references/task-contract.md`、contract/template 骨架；executor workflow 设计章节；联合 fixture manifest。
- API/配置：最新 task bundle、field/event/state ownership、profile routing、cutover checklist。
- 测试/文档：valid/invalid contract、state/event 示例和 producer-consumer owner matrix。

参考来源：RF-01 至 RF-12、ES-01/02/08/09/21/22/23/24、DEC-01 至 DEC-15。

适用规范：STD-01 至 STD-05、STD-10 至 STD-15。

开发质量检查：

- 每个字段、事件和状态只有一个 owner/权威定义；状态转移无歧义。
- profile 阈值可解释、可测试，不能依赖模型自报“复杂”。
- lite 不要求 full-only artifact；full 仍保留审批、研究、质量和恢复门禁。
- plan/contract 批准后不可变；run-state 可由 ledger 重建；attestation 不覆盖 mutable 文件。
- 不引入通用 workflow engine、数据库、Temporal 服务或完整 schema runtime。

验证：

- 对照 REQ-01 至 REQ-14、NFR-01 至 NFR-08 做 contract/ownership walkthrough。
- 构造 lite/standard/full、discovery-first、非法状态、断链 DAG、非法事件、缺失/无效 contract 示例。
- 检查所有字段和事件均有 producer、consumer、validator、mutation owner 和 recovery rule。
- 证明本次 bootstrap 与最终交付能力分离，最终产物不存在版本或旧契约分支。

风险和回滚：

- 风险：字段过多导致新形式主义；以最小 enforceable 字段、profile 条件和 fixture 体积指标控制。
- 风险：自举期间两套入口混用；新模块不得注册为默认入口，STG-06 前仅 fixtures 显式调用。
- 回滚：STG-06 前删除显式测试路径中的新文件即可；切换后只允许整体 Git 回退，不保留 runtime compatibility branch。

阶段契约（Stage Contract）：

- 范围：联合最新 contract、状态/事件所有权、profile、artifact policy、自举与原子切换设计。
- 允许修改：planner/executor contract references、模板骨架、联合 fixture manifest、changelog 草稿。
- 禁止修改：默认入口、其他 skill、历史 task、提交未授权代码。
- 进入条件：计划已批准；attestation 匹配；工作树状态已核对。
- 退出条件：contract、state/event invariant、ownership matrix、profile matrix、bootstrap/cutover checklist 可被 STG-02/03/04 直接实现。
- 适用规范：STD-01/02/03/04/05/10/11/13/14/15。
- 开发质量检查：完整性、单写者、最小字段集、不可变边界、breaking cutover review。
- 必需验证：contract walkthrough、fixture skeleton、VAL-07/08 设计检查、traceability 更新。
- 是否预期提交：仅用户授权时，建议阶段提交。

### 阶段 2（STG-02）：实现 planner producer 与 approval checker

目标：

- 让 planner 能按 profile 生成完整、不可变、机器可验证的最新 task bundle，并在用户审批前完成跨制品语义门禁。

做法：

- 精简 planner `SKILL.md`：触发、路由、profile、task files、Plan Quality/Self-Review/Readiness/Approval 和 executor handoff。
- 重组 workflow：autonomous disambiguation、区分性 probe、研究停止条件、change map、traceability、critique 和 profile-specific requirements。
- 将 `execution-plan.md` 改为批准意图文档：目标、证据、决策、Stage Contract、风险和验证；删除可变 Implementation Progress、Execution Control、Resume/Commit 状态表。
- 新增 `plan-contract.json` 模板，承载 task/profile、IDs、Stage DAG、VAL、artifact index、授权和 amendment triggers；禁止从 prose 推导 enforceable 字段。
- 增加 spec/research/change-map/standards/traceability/critique 的条件模板与触发规则；lite 不生成空 artifact。
- 更新 pending decisions：impact、uncertainty、default assumption、probe、resolution 和 reapproval effect。
- 将 `harness_plan_check.py` 改为 `--task-dir --mode draft|approval`，验证 JSON shape、ID、DAG、覆盖、授权、artifact 存在/哈希输入集合和 profile 规则。
- planner 只写 pointer-only active-task；不创建/修改 run-state 或 ledger。
- 用新模块/fixture 显式运行，STG-06 前不替换当前默认入口。

原因：

- planner 必须成为可靠 producer，而不是生成一份需要 executor 猜 prose 的文档；这也是压缩 lite 计划而不降低安全性的前提。

位置：

- 文件/模块：CM-01 至 CM-09、CM-18/19 的 planner 侧规则和 fixtures。
- API/配置：最新 plan-contract、artifact index、clarification record、approval checker CLI。
- 测试/文档：lite/standard/full task bundle、invalid producer fixtures、planner README/changelog 草稿。

参考来源：RF-01 至 RF-12、ES-01 至 ES-11、ES-21/23/24、DEC-01 至 DEC-05、DEC-09/10/14。

适用规范：STD-01 至 STD-06、STD-09 至 STD-14。

开发质量检查：

- SKILL 与 reference 不重复大段规则；主文件保持渐进披露入口。
- execution-plan 与 plan-contract 使用相同 IDs，approval checker 阻止冲突。
- conditional artifact 有明确触发、owner、索引与 approval hash policy。
- planner 不写任何 executor lifecycle 字段；active-task 不复制状态。
- 环境治理只改变模板/规则，不批量篡改历史任务证据。
- 对小任务保留直接路径，不能把 profile 评分变成新固定表单负担。

验证：

- 生成 lite/standard/full 三类 task bundle，核对必填字段、plan-contract 和 artifact 数量。
- 对高不确定任务验证 discovery-first、最多少量高价值用户问题和默认假设记录。
- VAL-02：所有有效 bundle 通过 planner approval checker；VAL-03：断链/冲突/非法授权 fixtures 失败。
- 全文件重读 SKILL/workflow/templates，确认没有可变执行状态、版本字段或旧契约生成规则。

风险和回滚：

- 风险：plan/contract 双文件漂移；通过稳定 ID、approval checker 和共同 attestation 集合阻止。
- 风险：精简 SKILL 时误删安全门禁；以 REQ-14、旧规则清单和 diff review 防护。
- 回滚：STG-06 前删除并行 producer 文件；不在最终实现中保留旧生成路径。

阶段契约（Stage Contract）：

- 范围：planner 指令、最新 plan/contract/artifact templates、approval checker 和 pointer/environment 规则。
- 允许修改：CM-01 至 CM-09、CM-18/19 的 planner 侧文件及 tests/fixtures。
- 禁止修改：executor 默认入口、run-state/ledger、其他 skill、历史 task 内容。
- 进入条件：STG-01 complete；contract shape 和 profile matrix 已锁定。
- 退出条件：三 profile 可生成一致 task bundle；approval checker 通过有效 fixture 并拒绝无效 fixture；planner 不拥有运行状态。
- 适用规范：STD-01/02/03/05/06/09/10/11/12/13/14。
- 开发质量检查：渐进披露、去重、可发现性、contract/prose 一致、单写者。
- 必需验证：VAL-01/02/03/09、traceability REQ-01 至 REQ-05、REQ-09/10/14。
- 是否预期提交：仅用户授权时，建议阶段提交。

### 阶段 3（STG-03）：实现 executor consumer 与单写者执行循环

目标：

- 让 executor 只根据最新 contract、attestation、run-state 和 ledger 执行阶段，不再从 plan prose 或 active-task 镜像推断运行状态。

做法：

- 重写 executor `SKILL.md` 与 workflow：入口依次解析 active pointer、plan contract、attestation、run-state、ledger 和当前阶段 artifacts。
- 重写 task resolver：要求 `plan-contract.json` 及最新 shape；文件缺失或结构无效时 fail closed，并给出具体缺失字段/文件。
- executor 在用户批准后创建 attestation、初始 `run-state.json` 和第一条 ledger event；planner 不参与这些写入。
- 定义 preflight/status/loop-tick/transition/final：所有生命周期和 next action 来自 run-state + ledger，不解析 plan prose。
- 阶段执行读取 contract 中的 Stage DAG、allowed/forbidden changes、VAL IDs、risk 和 reapproval triggers；按需加载 artifact index。
- 每次 stage start、attempt、validation、review、blocked、amendment、complete 写顺序 ledger event，再原子更新 run-state snapshot。
- 将 progress、Resume Summary、Stage Gate evidence 和 Commit Log 从 execution-plan 移入 ledger/run-state/validation artifacts。
- 保留 Research Drift、Development Quality、Git 串行、process-manager、review、提交授权和最终门禁，但改为 contract 字段/事件驱动。
- 先以新模块/显式 fixture 运行，STG-06 前不覆盖当前默认脚本入口。

原因：

- 用户要求 executor 与 planner 绑定升级；若 executor 仍依赖 prose/双状态源，planner 的机器契约和不可变批准集合不会产生实际效果。

位置：

- 文件/模块：CM-10 至 CM-17，重点是 executor SKILL/workflow、resolver、exec checker、ledger/state 模块和 fixtures。
- API/配置：单一契约 resolver，`--task-dir`，preflight/status/loop-tick/transition/final；run-state/event shape。
- 测试/文档：consumer conformance、lifecycle、权限、stage gate 和 contract 结构失败 fixtures。

参考来源：LE-07/09/10、RF-06/08/10/11/12、ES-04/07/22/23/24/25、DEC-06/07/09/13/14/15。

适用规范：STD-01、STD-04、STD-07、STD-08、STD-10/11/13/14/15。

开发质量检查：

- executor 不修改 execution-plan/plan-contract/批准 artifacts；文件权限和 workflow 都要体现这一点。
- resolver/checker/state reducer 为纯函数或小模块，错误聚合但不吞异常。
- 文件不存在、无效 JSON、attestation mismatch、断链 artifact、非法 event、Windows 路径均有明确失败。
- 缺少最新 task bundle 或 contract shape 不合法时给出稳定、可操作的结构诊断。
- ledger event 先后顺序、重复 event、阶段依赖、权限和提交授权均 fail closed。

验证：

- VAL-04：STG-02 生成的所有 valid producer fixtures 通过 executor preflight。
- VAL-05：approved/start/transition/blocked/resume/completed 生命周期与 stop condition。
- 测试未批准、未授权提交、stage dependency 未完成、contract 文件/字段缺失或语义无效、attestation mismatch 和 artifact 缺失。
- `python -m py_compile`、`python -m unittest` 和 CLI exit/output shape。

风险和回滚：

- 风险：ledger/state 双写出现部分失败；STG-04 必须用 replay/reconcile 和原子 snapshot 解决，STG-03 不宣称完整恢复。
- 风险：执行规则重写遗漏旧安全门禁；以 REQ-14、旧 workflow 清单和 negative fixtures 防护。
- 回滚：STG-06 前删除显式测试路径中的 consumer 文件，不在最终入口保留旧契约 dispatch。

阶段契约（Stage Contract）：

- 范围：executor resolver、workflow、run-state/ledger writer、exec checker 和 consumer fixtures。
- 允许修改：CM-10 至 CM-17 的新实现和 tests。
- 禁止修改：planner 契约定义、当前默认入口、其他 skill、放宽审批/提交/进程安全规则。
- 进入条件：STG-02 complete；producer fixtures 和最新 contract 已稳定。
- 退出条件：REQ-06/09/13/14 和 NFR-02/05/06/08 的 consumer 侧行为有自动化证据。
- 适用规范：STD-01/04/07/08/10/11/13/14/15。
- 开发质量检查：单写者、状态机、错误路径、按需加载、安全门禁完整。
- 必需验证：VAL-04/05/08/09；executor code review。
- 是否预期提交：仅用户授权时，建议阶段提交。

### 阶段 4（STG-04）：打通 attestation、ledger replay、reconcile 与 amendment

目标：

- 完成 planner 不可变批准集合与 executor 可变状态之间的闭环，使中断、部分写入、范围漂移和计划修订都能被确定性恢复或阻塞。

做法：

- 实现 attestation manifest：plan、contract 和批准 artifacts 的路径/hash/plan_revision/approval summary；排除 run-state、ledger 和执行证据。
- 定义 ledger event envelope：seq、event_id、timestamp、stage_id、type、attempt、payload/evidence refs；校验连续性和允许转移。
- 实现 reducer：从初始 approved 事件重放 lifecycle、current/completed/remaining、stop/next、findings 和 evidence summary。
- 实现 run-state 原子写入与 revision/last_event_seq；写入中断时以 ledger replay 为准恢复，不依赖双文件同时成功。
- 增加 reconcile mode：比较 snapshot 与 replay，安全自动修复可重建 drift；hash/权限/非法转移等不可修复问题 fail closed。
- 设计 amendment：Research Drift 生成 amendment request；用户批准后产生新 plan_revision、更新不可变集合和 attestation，并以 ledger 事件连接前后 revision。
- active-task 只定位 task/run-state；completed 后归档或清空 pointer，历史 bundle 保留。
- 建立跨 skill conformance：planner valid bundles -> executor preflight；planner invalid/权限冲突 -> 两端一致拒绝。

原因：

- 这是最新契约更可靠的核心：计划可证明且不被进度更新污染，运行快照可丢失但事件历史可恢复，双方对 amendment 有同一语义。

位置：

- 文件/模块：CM-06、CM-07、CM-11 至 CM-17、CM-19/20 的 integration/recovery 部分。
- API/配置：attestation manifest、event schema、state reducer、reconcile/amendment modes。
- 测试/文档：crash points、state drift、event corruption、revision transition、active closure fixtures。

参考来源：LE-09/10、RF-04/06/08/09/10/11/12、ES-02/04/17/18/22/23/25、DEC-04/06/07/08/09/11/14。

适用规范：STD-01、STD-03/04、STD-07/08、STD-10/11、STD-13/14/15。

开发质量检查：

- reducer 为纯函数，event append 与 snapshot write 的失败边界可测试。
- 自动 reconcile 只修复可由合法 ledger 唯一推导的 snapshot；不修复非法/缺失事件或审批 hash。
- amendment 明确哪些文件可变、revision 如何递增、旧 attestation 如何审计。
- final checker 不接受未关闭 blocker、缺 VAL evidence、snapshot/replay drift 或 active pointer 未收口。
- 双方不复制隐式状态枚举；contract reference 和 conformance fixtures 必须一致。

验证：

- VAL-06：正常 replay、snapshot 丢失/滞后、重复/断号/非法 event、reconcile 成功与拒绝。
- VAL-07：attestation 不受进度更新影响；plan/contract 修改触发 mismatch；amendment 新 revision 可继续执行。
- VAL-04：planner/executor 对 valid/invalid contract 与授权结果一致。
- VAL-05：完整 lifecycle 和 active pointer closure。

风险和回滚：

- 风险：事件模型过度复杂；只保留门禁/恢复必需事件，不实现通用 event-sourcing 框架或 hash chain。
- 风险：自动 reconcile 掩盖损坏；仅处理可证明的 snapshot drift，其余阻塞并保留原始证据。
- 回滚：STG-06 前移除并行 integration 模块；最终不保留旧恢复分支。

阶段契约（Stage Contract）：

- 范围：attestation、event/reducer、run-state/reconcile、amendment、active closure 和跨 skill conformance。
- 允许修改：CM-06/07、CM-11 至 CM-17、CM-19/20 的相关并行实现和 tests。
- 禁止修改：无关 executor 能力、Git 授权、process-manager 规则、历史 task 文件。
- 进入条件：STG-03 complete；planner checker 能验证符合最新契约的 ready-for-execution fixture。
- 退出条件：REQ-04/07/08/09/11/14 与 NFR-04/05/06/08 有 replay、attestation、amendment 和 conformance 证据。
- 适用规范：STD-01/03/04/07/08/10/11/13/14/15。
- 开发质量检查：单写者、replay 确定性、reconcile 边界、不可变 attestation、错误路径。
- 必需验证：VAL-04/05/06/07/09。
- 是否预期提交：仅用户授权时，建议阶段提交。

### 阶段 5（STG-05）：建立联合 eval、独立 critique 与双 skill 元数据

目标：

- 用可重复评测证明 planner 产出的最新 task bundle 能被 executor 正确消费和恢复，并补齐两个 skill 的 metadata、文档与风险自适应 critique。

做法：

- 审核现有 prompts，补充 direct、lite、standard、full、ambiguity、online research、multi-module、long-horizon、mid-execution drift、crash/reconcile、amendment，以及缺失或无效 task contract 案例。
- 新增可执行 runner：读取 manifest，校验 planner task bundle、executor lifecycle artifacts 和联合 conformance，汇总结构、状态、恢复、覆盖与效率指标。
- 区分 capability suite 与 regression suite；确定性 checker/unit tests 作为快速门禁，fresh-agent forward test 作为可选高成本评测。
- 定义多维指标：profile 命中、计划体积/artifact 数、用户问题、覆盖、approval 返修、consumer acceptance、reconcile、恢复轮次、验证成功、回归和代码健康。
- full/高风险定义 Plan Critique Gate：优先 clean-context reviewer；输出 `artifacts/reviews/plan-critique.md`，planner 对每项 finding 记录 accept/reject/defer。
- 无独立 evaluator 时按降级协议执行 deterministic checker + self-review，不能伪造独立评审。
- 为 planner/executor 新增或补齐 `agents/openai.yaml`，default prompt 分别显式提及 `$complex-coding-planner` 与 `$complex-coding-executor`；更新 eval README、breaking cutover 文档和 changelog。

原因：

- 没有联合 eval 就无法证明 producer/consumer 真正绑定、恢复可重建或 breaking cutover 没有残留旧路径；metadata 也是两个 skill 的结构质量要求。

位置：

- 文件/模块：planner/executor eval 目录、联合 fixtures/runner、双 skill `agents/openai.yaml`、critique 章节、README/changelog。
- API/配置：eval manifest、metrics JSON/Markdown、contract/event expectations、critique artifact shape。
- 测试/文档：runner 自测、expected schema、单一契约直接切换与 forward-test 手册。

参考来源：RF-07/08/11/12、ES-05/06/07/14/17/18/20/22/24、skill-creator、DEC-10/11/12/13。

适用规范：STD-01、STD-05 至 STD-09、STD-10。

开发质量检查：

- runner 不把固定工具路径当唯一正确答案，优先 contract/state/result invariant。
- capability/regression 数据分开，失败报告可定位到 task/metric/rule。
- fresh-agent 测试不泄露预期答案；涉及长时或写操作前按系统规则获得授权。
- 两个 metadata 与各自 SKILL description/职责一致，default prompt 显式调用对应 skill。
- 指标用于比较，不把未校准阈值伪装成质量保证。

验证：

- 运行确定性 eval runner、producer-consumer conformance 和代表性 capability/regression fixtures。
- 在成本允许且获得必要授权时，运行至少 direct、lite、full、ambiguity 四类 fresh-agent forward tests；否则记录未执行原因。
- 对两个 skill 运行 `skill-creator/scripts/quick_validate.py` 和 metadata 结构校验。
- 对比 lite 与当前模板基线的行数/制品数，并确认 full 覆盖不下降。

风险和回滚：

- 风险：eval 过拟合模板；使用行为/语义指标、不同表达 prompt 和多次运行缓解。
- 风险：独立 reviewer 成本高；只对 full/高风险强制并提供真实降级。
- 回滚：STG-06 前 runner/metadata 可独立撤销；最终不以旧 expected 作为兼容承诺。

阶段契约（Stage Contract）：

- 范围：联合 eval runner/suites/metrics、critique gate、双 skill metadata 和 breaking 文档。
- 允许修改：CM-08/09/17、critique reference/template、README/changelog。
- 禁止修改：模型服务、后台 worker、无授权的真实仓库写操作、其他 skill metadata。
- 进入条件：STG-04 complete；planner/executor conformance、replay 和 attestation 稳定。
- 退出条件：REQ-10/11/12/13、NFR-03/04/07 有可重复证据；两个 skill validator 通过。
- 适用规范：STD-01/05/06/07/08/09/10。
- 开发质量检查：评测独立性、可重复性、诊断质量、渐进披露。
- 必需验证：VAL-01/04/08/10/11；forward test 执行或明确记录限制。
- 是否预期提交：仅用户授权时，建议阶段提交。

### 阶段 6（STG-06）：执行单一契约原子切换、删除旧路径并最终审查

目标：

- 在隔离开发的 producer/consumer 全部通过后一次替换默认入口，删除旧解析和双写规则，并用全新 task 完成端到端验收。

做法：

- 切换前重跑 py_compile、unittest、plan/exec checker、conformance、replay、attestation、skill validator 和 eval suites。
- 冻结当前 bootstrap task 的最终证据，确认后续不再依赖旧 checker 执行剩余阶段。
- 将经过隔离验证的 modules/templates/rules 替换为 planner/executor 默认入口，更新 CLI 和 active-task/environment 模板。
- 删除 embedded contract parser、版本分派、旧 execution-plan 可变状态章节、active-task 状态镜像和相应旧测试/文档。
- 执行 matrix：lite/standard/full、discovery、approved/start/blocked/resume/amendment/completed，以及缺失文件、字段错误、断链引用、非法状态和权限冲突等 invalid cases。
- 生成一个符合最新契约的全新 fixture task，由 planner approval checker 验证，再由 executor preflight/lifecycle/reconcile/final 完整消费。
- 对照 traceability 逐项回填 AC/NFR -> implementation -> validation -> evidence，不接受仅凭代码阅读标记完成。
- 做代码审查：正确性、错误路径、状态所有权、replay、授权、架构边界、过度设计、Windows 路径和文档一致性。
- 全仓检索旧 parser/CLI、版本字段与分派、plan 状态双写和历史恢复承诺；每个命中必须删除、改成最新契约的结构失败测试，或说明为何仅是本次 bootstrap 计划的控制记录。
- 运行 `git diff --check` 和最终状态/diff 审查；不改无关文件。
- 更新 breaking changelog、当前 bootstrap ledger/记录和最新 active-task closure；用户已授权才生成规范 commit message 文件并 `git commit -F`。

原因：

- 这是直接替换最危险的时刻；只有最新契约全链路先绿、旧路径再删除，才能避免 producer 与 consumer 处于不同语义。

位置：

- 文件/模块：所有本任务文件；`.harness` 只更新本任务证据与必要状态索引。
- API/配置：完成默认 CLI/task bundle/active pointer 的 breaking 切换，不再新增设计。
- 测试/文档：validation report、legacy-removal report、review findings、changelog、commit record。

参考来源：RF-06/08/09/10/11/12、ES-01/02/04/07/17/18/22/23、Goal Condition 和 traceability。

适用规范：STD-01 至 STD-15 中所有适用项。

开发质量检查：

- 不以测试数量代替覆盖；每项 AC/NFR 都要有证据。
- blocking/major finding 必须修复并重跑相关门禁；minor 明确记录是否跟进。
- final status、pointer、run-state、ledger、attestation 和 commit record 一致。
- 不以临时 bootstrap 文件作为交付后兼容能力；旧实现命中必须有明确处置。
- 未执行的 forward test 或网络验证必须显式披露，不能声称完整通过。

验证：

- VAL-01 至 VAL-12 全部执行或记录不可执行原因与替代证据。
- lifecycle 从 ready-for-approval 到 completed 至少走一条最新 fixture 全链路，包括 replay/reconcile。
- VAL-08 证明缺失或无效的最新 task contract 会得到明确结构错误，且旧 parser、版本分派和双写规则已删除。
- `git --no-optional-locks status --short --branch` 与串行 diff 检查确认范围。

风险和回滚：

- 风险：切换后发现入口遗漏；在提交前修复并重跑全套，不能以保留旧契约或版本分支兜底。
- 风险：forward test 非确定；保留原始 artifact，使用多次运行/人工 review，不用单次结果阻断全部发布。
- 回滚：切换前继续使用 bootstrap；切换失败则通过定点 patch/Git 证据整体回退本次切换并停止，不交付双协议中间态。

阶段契约（Stage Contract）：

- 范围：默认入口原子切换、旧路径删除、最新契约集成验证、review、文档和状态/提交收口。
- 允许修改：本任务已批准文件、tests/evals/docs、`.harness` 本任务记录。
- 禁止修改：保留 runtime 旧契约或版本分支、为通过测试放宽 must invariant、删除失败 fixture、提交无关改动。
- 进入条件：STG-01 至 STG-05 complete；无 open blocking amendment。
- 退出条件：Goal Condition、AC-01 至 AC-18、VAL-01 至 VAL-12、legacy-removal、final checker、review 和授权策略全部满足。
- 适用规范：全部适用 STD。
- 开发质量检查：最终一致性、回归、证据完整、无范围漂移。
- 必需验证：VAL-01 至 VAL-12、最新契约 fresh task E2E、legacy search、final code review、状态同步。
- 是否预期提交：仅用户明确授权；使用 `git commit -F` 且提交正文无多余空行。

## 环境（Environment）

- Workspace 环境来源：`.harness/environment.md`
- 仓库：`D:\Item\vibe_coding\dev-skills`
- 平台：Windows + PowerShell，当前日期 2026-07-10，时区 Asia/Shanghai。
- 本任务使用：Markdown/JSON/YAML 文件、Python 3 脚本与标准库、Git、`apply_patch`、在线官方资料。
- 临时覆盖：本计划把当前用户约束保存在 task 内，不把它追加为长期 workspace 事实。
- 依赖策略：不新增服务或 runtime 第三方依赖；skill validator 可使用系统 `skill-creator` 已有环境。
- 敏感信息：无 token、密钥或外部写操作；计划和 eval fixture 不应写入环境秘密。

## Git 上下文（Git Context）

- 主分支：`main`
- 任务类型：`feature`
- 工作分支：`harness/feature`
- 分支动作：`reuse`
- 同步来源：本地 `main`；本轮不执行 fetch/pull/rebase。
- 最近同步：规划检查时当前分支与本地 `main` 无提交/文件差异。

分支占用：

- 串行 `git log main..HEAD --oneline`：无输出。
- 串行 `git -c diff.autoRefreshIndex=false diff main...HEAD --name-only`：无输出。
- 现有提交属于本任务：不适用；当前无分支增量。
- 规划前 `git --no-optional-locks status --short --branch`：工作树干净，分支跟踪 `origin/harness/feature`。

Git 命令策略：

- 同一仓库 Git 命令严格串行，不通过并发 agent、后台任务或多 shell 同时执行。
- 非 Git 文件读取可并发；修改前仍需确认用户/生成变更。
- 只读状态优先使用 `--no-optional-locks` 与 `diff.autoRefreshIndex=false`。
- 不自动 stash、rebase、reset、切换分支或删除 lock。

Index lock 恢复策略：

- 仅在真实 lock 错误后解析 `git rev-parse --git-path index.lock`。
- 删除前核对精确路径、存在性、大小/mtime 稳定和活跃 Git 进程；禁止通配符/递归删除。
- 删除需要符合当前授权与提权规则，随后串行重跑 status。

Git Lock Recovery Log：本轮无 lock 错误，无记录。

提交策略：

- 当前 `not_authorized`；批准实施不自动等于授权提交。
- 如用户授权，阶段提交或最终提交均使用 `git commit -F`，标题后一个空行，bullet 间无空行。
- 提交前执行 validation、review、`git diff --check` 和串行 status/diff；不纳入无关文件。

分支收口：

- 已合回主分支：no。
- 未合回时代码停留在：`harness/feature`。
- 合并前需要用户确认：yes。
- hotfix interruption：如需切换 `harness/fix`，先询问 feature 是否合回主分支；当前不适用。

## 工具（Tooling）

| 工具 | 用途 | 阶段 | 状态 | 风险 | 替代方案 | 用户确认 |
| --- | --- | --- | --- | --- | --- | --- |
| `apply_patch` | 分段修改 skill、脚本、测试和文档 | 全阶段 | available | 锚点误匹配 | 小 patch 后重读 | 已有规则允许 |
| PowerShell/shell | 只读检查与有限测试 | 全阶段 | available | 配置/profile 副作用 | `login:false`、精确命令 | 普通命令无需额外确认 |
| Python 3 | planner/executor checker、state/reducer、unittest、eval runner | STG-02 至 06 | available | `__pycache__` 权限 | `python -B`、`PYTHONDONTWRITEBYTECODE=1` 或获批提权 | 有写权限问题再处理 |
| web | 官方资料与版本核验 | discovery/漂移 | available | 来源陈旧或非一手 | 官方/论文原文优先 | 用户已要求在线调研 |
| skill-creator validator | SKILL/metadata 校验 | STG-05/06 | available | 环境依赖 | 手工结构检查并披露 | 无需额外确认 |
| fresh-agent reviewer | full critique/forward eval | STG-05/06 | capability-dependent | 成本、上下文泄露 | deterministic + self-review 降级 | 长时/写操作前另行确认 |
| Git | 状态、diff、可选提交 | 全阶段 | available | 并发 lock、误提交 | 串行 + 范围检查 | 提交另需授权 |

## 长期进程管理（Process Manager Gate）

- 是否需要长期后台进程：`no`
- process-manager skill 是否存在：未检查且不需要检查。
- 规则结论：本任务只有 finite command，例如 unittest、validator、checker 和 eval runner；不启动 dev server、watcher 或后台 worker。
- 需要托管的服务：无。
- 禁止 shell 后台启动确认：`confirmed`。
- 历史视图需求：`no`。
- 证据保留位置：本任务 execution-plan、artifacts、ledger 和 validation output 摘要。
- 日志沉淀确认：实施阶段按 VAL ID 回填，不保留无意义完整终端转储。
- 每阶段 Stage Entry 前复查本节；若后续设计意外需要长期进程，必须进入 Plan Amendment Gate。

## 验证（Validation）

必需验证：

- `VAL-01`：profile/router 表驱动测试和代表性 prompt fixtures。
- `VAL-02`：符合最新契约的 lite/standard/full task bundle 通过 planner checker。
- `VAL-03`：contract、ID、DAG、覆盖、授权和 artifact 无效 fixtures 必须失败。
- `VAL-04`：planner producer fixtures 全部通过 executor preflight conformance。
- `VAL-05`：最新契约下的 approved/start/transition/blocked/resume/completed lifecycle smoke。
- `VAL-06`：ledger replay、run-state drift 与 reconcile recovery/failure tests。
- `VAL-07`：attestation immutable set 与 amendment revision tests。
- `VAL-08`：缺失或无效的最新 task contract 返回可定位的结构错误，仓库无旧 parser、版本字段/分派和双写规则。
- `VAL-09`：修改 Python 的 `py_compile` 与 unittest。
- `VAL-10`：双 skill validator、metadata 和全文件一致性。
- `VAL-11`：capability/regression/efficiency eval 报告。
- `VAL-12`：`git diff --check`、最终 diff/code review、工作树范围核对。

规划阶段已执行：

| 命令/工具 | 结果 | 覆盖 | 未覆盖 | 证据 |
| --- | --- | --- | --- | --- |
| 本地 SKILL/workflow/template/checker/eval 阅读 | passed | 当前规则与消费链 | 实施后行为 | research artifact |
| 24 份历史计划统计 | passed | 文档体积趋势 | 质量因果 | LE-02 |
| 完成计划运行当前 checker | reproduced false-ready PASS | 语义误放行 | 最新 checker 修复 | LE-04 |
| 官方/论文在线调研 | passed | 方法论、状态/契约和前沿 benchmark | 本项目实测收益 | ES-01 至 ES-25 |
| executor attestation/state/ledger 复核 | passed | 哈希漂移、状态双写和恢复所有权 | 最新实现 | LE-09/10 |
| Git status/branch/log/diff | passed | 初始范围和分支占用 | 执行后的状态 | Git Context |

实施验证证据表：

| 阶段 | 命令/工具 | 预期 | 覆盖 | 未覆盖 | 证据位置 | 失败处理 |
| --- | --- | --- | --- | --- | --- | --- |
| STG-01 | contract/ownership walkthrough + fixtures | 字段、事件、writer、cutover 一致 | REQ-01 至 REQ-14 | runtime | traceability + design fixtures | 修正文档后重审 |
| STG-02 | planner bundle/checker matrix | 三 profile valid，invalid fail | producer | executor runtime | planner tests | 回到 STG-01 amendment |
| STG-03 | executor preflight/lifecycle matrix | valid consumer，缺失/无效 contract 结构失败 | consumer/state | crash reconcile | executor tests | 修规则并重跑 |
| STG-04 | conformance + replay + attestation/amendment | 恢复和 revision 闭环 | handoff/recovery | live long task | integration report | 阻塞切换 |
| STG-05 | eval runner + 双 skill validator | suites/metadata 合法 | capability/efficiency | 全模型泛化 | eval report | 校准 fixture/指标 |
| STG-06 | atomic cutover + fresh task E2E + legacy search | 单一最新契约的 Goal Condition 满足 | 全任务 | 披露的外部限制 | validation/removal report | blocking finding 不交付 |

可选验证：经授权的 fresh-agent 多次 forward test；非本任务正确性的唯一证据。

无法执行时：记录具体命令、失败原因、影响、替代证据和残余风险；不得把“未运行”写成 passed。

## 文档（Documentation）

- 必需更新：planner/executor SKILL 与 workflow、最新 contract/state/event/ownership、profile/artifact/checker/recovery/eval 使用说明、模板和 eval README。
- Changelog 计划：明确单一最新契约的 breaking replacement、四层 task bundle、single-writer state、replay/reconcile、semantic checker、eval 和 metadata；不宣称未验证性能提升。
- 切换说明：历史 task 不迁移、不恢复；缺少最新契约必需文件或字段时按任务结构缺失/无效失败；本次 bootstrap 是一次性实施机制，不是交付能力。
- 研究来源：保留 URL、访问日期、结论和限制，不把整篇外部文档复制入 skill。

## 文件写入策略（File Write Strategy）

分段判断：

| 文件 | 分段 | 分段边界 | 整体复查 |
| --- | --- | --- | --- |
| planner `SKILL.md` | no/局部 | 按路由、门禁、交接定点 patch | 完整读取 + validator |
| `planning-workflow.md` | yes | profile、research、artifact、gates、state | 完整读取 + heading/术语检查 |
| `execution-plan.md` / `plan-contract.json` templates | yes | immutable intent、profile、DAG、授权、artifact | checker + conformance fixtures |
| planner checker Python | yes if 超过 500 行 | contract/model/rules/CLI | py_compile + unittest + review |
| executor workflow/state/checker | yes | resolver、state machine、ledger、reconcile、final | lifecycle/replay tests + 完整读取 |
| eval/fixtures/docs | per file | manifest、runner、cases、README | runner + schema review |
| changelog/metadata | no | 定点追加/新文件 | validator + diff |

写入规则：

- 大内容先全局框架，再按语义段递进式 patch；单次新增建议不超过 120 行，硬上限 200 行。
- 目标文件超过 500 行默认禁止整文件重写；采用局部定点修改。
- patch 失败后先读目标确认有无部分写入，再判断锚点/权限/冲突；不得盲目重复。
- 全部写完后重新读取完整目标文件，核对状态、ID、链接、重复、阶段顺序和末尾完整性。

## 问题和覆盖项（Questions And Overrides）

| ID | 阻塞 | 状态 | 问题 | 决策 | 应用位置 |
| --- | --- | --- | --- | --- | --- |
| Q-01 | no | resolved | planner 升级是否可只改 planner | 不能；planner/executor 按同一最新 contract 联合替换 | STG-01 至 04 |
| Q-02 | no | resolved | 是否每次运行独立 critique | 只对 full/高风险强制 | STG-02/05 |
| Q-03 | no | resolved | 是否引入服务/第三方 parser | 否，标准库、受控 JSON shape 和语义 validator | STG-01 至 04 |
| Q-04 | no | resolved | 是否迁移或兼容历史计划 | 否；历史 task 缺少最新结构时按普通 contract 缺失/无效失败 | STG-01/06 |
| Q-05 | no | resolved | 当前是否授权提交 | 否；执行批准与提交授权分离 | Git/Approval |
| Q-06 | no | resolved | 无兼容时如何执行本次升级 | 当前 plan 仅自举，替换实现隔离构建后在 STG-06 原子切换 | STG-01/06 |

## 方案质量门禁（Plan Quality Gate）

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 关键判断有证据等级 | passed | Context evidence table + LE/ES/RF IDs |
| Research Gate 已完成 | passed | research-findings，含来源、限制与停止条件 |
| Standards Discovery Gate 已完成 | passed | standards-index，覆盖项目/Python/Markdown/skill/contract |
| Development Quality Gate 已完成 | passed | 质量维度映射、模式取舍和过度设计防护 |
| 影响面矩阵完整 | passed | CM-01 至 CM-20 + Impact Matrix |
| 候选方案比较充分 | passed | A/B/C 比较，包含验证和回滚 |
| 每阶段可独立验证 | passed | 6 个 Stage Contract 均有 entry/exit/required validation |
| 需求可追踪 | passed | REQ/NFR -> AC -> DEC -> STG -> VAL 闭环 |
| 单一最新契约的自举与切换清楚 | passed | task-contract-outline + bootstrap-only current plan + STG-06 + VAL-08 |
| 方案变更触发条件清楚 | passed | Decision 与 Amendment Gate |
| 用户批准摘要可记录 | passed | Approval 提议范围和授权边界已准备 |

质量结论：`passed`。计划具备足够证据、范围、阶段、验证和回退信息，可进入自查。

## 规划自查（Plan Self-Review）

自查结论：`passed-after-fixes`。

| 类别 | 发现 | 处理 | 结果 |
| --- | --- | --- | --- |
| 缺陷 | 分段 patch 使用重复锚点，阶段初始顺序为 1/5/6/3/4/2 | 用定点 patch 逐块移动并重新列出 headings | fixed：1/2/3/4/5/6 |
| 缺陷 | 当前 attestation 哈希会被 executor 持续修改的 plan | 将批准集合设为 immutable，运行状态/证据独立并从 hash 排除 | fixed in design |
| 优化 | 原设想只创建 research artifact，难以机械检查范围和验收 | 增加 standards、change-map、traceability | fixed |
| 用户调整 | 用户明确拒绝旧版兼容，要求 planner/executor 绑定全部换新 | 删除兼容与版本分派语义，改为单一最新契约 producer/consumer 与原子切换 | fixed |
| 缺失项 | 原方案没有唯一可变状态 writer 与 crash reconcile | 增加 run-state/ledger ownership、reducer/reconcile 和 STG-04 | fixed |
| 自举风险 | 当前 executor 不能直接消费最终 task bundle | 当前 plan 仅 bootstrap；隔离构建后一次切换，最终不留旧契约或版本分支 | controlled |
| 风险 | full 方案可能再次形成大一统模板 | 加入 lite 基线、conditional artifact、体积/制品指标和过度设计防护 | mitigated |
| 风险 | 独立 evaluator 不一定在执行环境可用 | 仅条件强制，定义 deterministic + self-review 降级且禁止伪造 | mitigated |
| 一致性 | requirements、decision、stage、validation 的编号可能漂移 | 建立 traceability artifact，并要求实施中同步 checker | controlled |
| 开发质量 | checker 可能从一个大脚本膨胀为过度抽象 | 允许小模块但优先纯函数/标准库，不建插件框架 | controlled |
| Breaking change | 历史 task 无法由替换实现恢复 | 明确列为用户接受的非目标，并以 contract 缺失/无效和 legacy-removal test 固化 | accepted |

门禁重跑：

- Plan Quality Gate：已在单一最新契约架构、traceability、executor 联合方案和原子切换补充后重跑，passed。
- Plan Self-Review：本节记录的 blocking 缺陷均已修复，无需再次重跑。
- Readiness Gate：在本节之后执行。

## 就绪门禁（Readiness Gate）

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 目标和验收清楚 | passed | Problem + AC-01 至 AC-18 |
| 上下文已收集 | passed | 本地实现、历史计划、参考项目、官方/论文来源 |
| 调研门禁已通过 | passed | Research Gate result + research artifact |
| 规范发现门禁已通过 | passed | Standards Discovery Gate + standards-index |
| 开发质量门禁已通过 | passed | Development Quality Gate result |
| 候选方案已比较 | passed | Options A/B/C |
| 决策已记录 | passed | DEC-01 至 DEC-15 |
| 实施阶段已细化 | passed | STG-01 至 STG-06，顺序已复核 |
| 环境已确认 | passed | Environment，当前无秘密/服务依赖 |
| Git 上下文已确认 | passed | clean worktree、无 main 差异、串行策略 |
| 工具已确认 | passed | Tooling 和降级策略 |
| 验证已确认 | passed | VAL-01 至 VAL-12 + stage mapping |
| 最终交付证据已规划 | passed | traceability、conformance/replay/eval/removal report、run-state/ledger/attestation |
| 文档更新已确认 | passed | Documentation + breaking cutover/changelog |
| 风险已识别 | passed | 各 Stage 风险/回滚 + self-review |
| 规划自查已通过 | passed | passed-after-fixes |
| 阻塞问题已关闭 | passed | Q-01 至 Q-06 resolved，无 blocking item |

就绪结论：`ready-for-user-approval`。

## 方案批准（Plan Approval）

- 状态：`approved`
- 批准记录：用户于 2026-07-10 明确要求执行规划方案、开始实现，并授权全部阶段完成后直接提交代码。

批准摘要：

- 提议批准范围：STG-01 至 STG-06；以 CM-01 至 CM-20、REQ-01 至 REQ-14、NFR-01 至 NFR-08 为边界。
- 阶段提交授权：`not_authorized`；最终提交授权：`authorized`，全部阶段和最终门禁通过后统一提交。
- 工具/MCP 授权：普通本地读写、测试、官方资料浏览；提权、长时 fresh-agent、外部写操作另按当时规则处理。
- 文档更新授权：仅批准范围内 planner/executor/eval/docs/changelog 与本任务 harness 记录。
- Breaking 授权边界：最终 planner/executor 只接受唯一最新 task contract；历史 task 不迁移、不恢复，结构不满足时按 contract 缺失/无效失败。
- 明确排除：其他业务 skill、服务/数据库/第三方 runtime、自动合并主分支。

提交策略：`final_commit_authorized`。

## 方案变更门禁（Plan Amendment Gate）

需要重新批准：

- approved scope、REQ/NFR/AC 或 CM 文件边界发生实质改变。
- 阶段数量、边界、依赖顺序或 Stage Contract 发生实质改变。
- 改变单一最新契约决策、四层状态所有权、attestation hash 集合、ledger/reconcile 或 active pointer 语义。
- 必需验证、critique 适用条件、工具授权、长期进程或提交策略改变。
- 引入第三方 runtime、服务、数据库，或风险升级到权限/安全/外部写入。
- attestation mismatch 且无法证明只是已允许的状态/证据回填。

无需重新批准但必须记录：

- 不改变行为的措辞、链接、格式、测试诊断和局部代码组织优化。
- 在既定 REQ/AC/VAL 下增加失败 fixture 或更严格但不改变 contract 的测试。
- 实施 findings 导致同阶段内部小调整，且范围、风险、验证和授权不变。

当前记录：无批准后 amendment；任务尚未获批。

## 执行控制（Execution Control）

- 执行模式：`run-to-completion`
- 整体任务状态：`in_progress`
- 当前阶段：`STG-05`
- 已完成阶段：Research、Standards Discovery、Development Quality、Plan Quality、Plan Self-Review、Readiness、`STG-01`、`STG-02`、`STG-03`、`STG-04`
- 剩余阶段：`STG-05`、`STG-06`
- 下一步自动动作：`continue STG-05`
- 当前停止条件：`none`
- 状态来源：本文件
- 阶段边界是否允许停止：不允许；仅在明确 Stop Condition、重新批准或最终门禁时停止。

active-task 同步字段：

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "in_progress",
  "current_stage": "STG-06",
  "remaining_stages": ["STG-06"],
  "next_automatic_action": "continue STG-06",
  "stop_condition": "none",
  "state_source": "execution-plan.md"
}
```

状态同步规则：

- 本节及下方 mutable tables 仅是当前 bootstrap harness 的执行控制；目标实现将这些状态移入 run-state/ledger。
- 批准后按当前 executor 先同步 bootstrap contract、Execution Control、active-task 和 attestation，再开始 STG-01。
- 如两者冲突，以本文件为准修正 active-task；不得同时保留两个不同 current stage。

## 实施进度（Implementation Progress）

| 阶段 | 状态 | 摘要 | 验证 | 证据 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| STG-01 | complete | 锁定最新任务契约、所有权与原子切换边界 | passed | contract reference + JSON templates + ledger | continue STG-02 |
| STG-02 | complete | 实现 planner producer、profile workflow 与 approval checker | passed | py_compile + 7 unittest + CLI + validator | continue STG-03 |
| STG-03 | complete | 实现 executor consumer 与单写者执行循环 | passed | py_compile + 10 resolver/reducer tests | continue STG-04 |
| STG-04 | complete | 打通 attestation、ledger replay、reconcile 与 amendment | passed | py_compile + 17 recovery/amendment tests | continue STG-05 |
| STG-05 | complete | 建立联合 eval、独立 critique 与双 skill 元数据 | passed | 18 eval cases + validators + critique fallback | continue STG-06 |
| STG-06 | complete | 完成单一契约切换、公开 CLI、全链路评测和最终审查 | passed | `artifacts/validation/final-validation.md` + `artifacts/reviews/final-code-review.md` | final commit and delivery |

## Ledger Evidence

- Ledger policy：`append-only-after-approval`
- Ledger 文件：`.harness/tasks/2026-07-10/feature/complex-coding-planner-vnext/ledger.jsonl`
- 当前 entries：23。
- stages_completed：Stage 1 至 Stage 6。
- current_stage：Final。
- last_blocking_reason：none。
- last_heartbeat：不适用。

## 阶段进入门禁（Stage Entry Gate）

| 阶段 | Git/worktree | 上阶段遗留 | 环境/工具 | 进程门禁 | 范围匹配 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| STG-01 | clean enough | 无 | passed | no service | CM/REQ 已覆盖 | passed |
| STG-02 至 STG-06 | serial Git checks complete | 无 open finding | passed | no service | Stage Contract 已覆盖 | passed |

## 阶段退出门禁（Stage Exit Gate）

| 阶段 | 目标完成 | Review | Validation | 进程清理/证据 | 日志沉淀 | 记录更新 | 提交记录 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STG-01 至 STG-06 | yes | passed | passed | not-applicable | artifacts 已沉淀 | ledger/control 已更新 | final-authorized | passed |

规则：只有对应 Stage Contract 的 exit condition、必需验证和 review 均满足，才能标记 complete；未授权提交不是阶段失败，但必须记录未提交原因。

## 阶段转移门禁（Stage Transition Gate）

| 阶段 | 当前阶段完成 | Review | Validation | 提交记录 | 仍有阶段 | 停止条件 | 需重批 | Control 更新 | active-task 同步 | 可停止 | 下一动作 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | yes | yes | plan gates passed | not-authorized | yes | awaiting approval | no | yes | planned | yes | await approval |
| STG-01 至 STG-05 | yes | passed | passed | deferred to final | yes | none | no | yes | yes | no | continue next stage |
| STG-06 | yes | passed | passed | final-authorized | no | goal_condition_met | no | yes | yes | yes | final commit and delivery |

结论：Stage 1 至 Stage 6、最终验证和审查均通过，允许进入已授权最终提交与交付。

## 代码审查（Code Review）

| 阶段 | 质量维度 | 发现 | 严重程度 | 处理 |
| --- | --- | --- | --- | --- |
| Planning | architecture | 统一重模板与词法 checker 不匹配 | major | 方案 B + STG-01/02/03 |
| Planning | state ownership | plan attestation 与 plan 可变更新冲突，active-task 重复状态 | major | 四层 task bundle + STG-01/03/04 |
| Planning | breaking scope | 用户明确不要旧版兼容和版本命名 | major | 单一最新契约 + 结构失败测试 + STG-06 原子切换 |
| Planning | validation | eval 不可执行 | major | 增加 STG-05/06 |
| Planning | consistency | 初次分段写入阶段顺序错误 | major | 已定点修复并复核 heading 顺序 |
| Planning | overengineering | 全量 SDD/服务方案过重 | minor | 明确拒绝方案 C，标准库实现 |
| STG-06 | correctness/recovery | commit evidence、amendment carry、attestation overwrite、终态事件等边界缺口 | major | 已修复并增加回归测试 |
| STG-06 | scope/quality | 旧协议残留、模块耦合、路径、时间格式和模板误报 | major | 全部关闭；最终 review 无 blocking/major finding |

最终代码审查见 `artifacts/reviews/final-code-review.md`；open blocking/major finding 为 none。

## 恢复摘要（Resume Summary）

Resume Packet：

```json
{
  "task_id": "2026-07-10-feature-complex-coding-planner-vnext",
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "current_stage": "Final",
  "remaining_stages": [],
  "next_automatic_action": "final commit and delivery",
  "stop_condition": "goal_condition_met",
  "ledger_entries": 23,
  "last_blocking_reason": "none",
  "attestation_status": "current"
}
```

- 整体目标：将 planner/executor 联合升级为风险自适应、四层状态所有权、可重放恢复且只接受唯一最新契约的新 harness。
- 已完成：本地审计、在线调研、规划门禁、六阶段实现、公开 CLI 切换、56 项单测、23 个 eval 场景、skill validators、旧路径检索和最终审查。
- 当前阶段：Final；Stage 1 至 Stage 6 全部完成，无 remaining stage。
- 下一步：按用户授权使用 `git commit -F`，确认提交与 clean status 后最终交付。
- 长期进程规则：本任务不需要；若变化则 amendment。
- 未覆盖/风险：Ruff 未安装，已用 AST、未使用导入分析、单测、eval、CLI 和结构检查替代；授权证明仍是本地信任边界。
- 停止说明：Goal Condition 已满足，最终提交成功后结束任务。

## 提交记录（Commit Log）

- 提交信息方式：用户授权后使用 `git commit -F .harness/tasks/2026-07-10/feature/complex-coding-planner-vnext/tmp/commit-message.txt`。
- 格式：标题后正好一个空行，bullet 之间无空行；提交前检查文件末尾和多余空白。
- 当前提交授权：`final_commit_authorized`；阶段内不提交，最终门禁通过后统一提交。

| 阶段 | 仓库 | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | none | 仅创建规划制品，未提交 | not-applicable |
| STG-01 至 STG-06 | dev-skills | pending current commit | `feat(complex-coding): 升级规划执行任务契约` | updated |

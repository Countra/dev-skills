# 执行计划：补强复杂编码开发质量门禁

## 执行控制快照（Execution Control Snapshot）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- completed

当前阶段（Current stage）:

- Final

已完成阶段（Completed stages）:

- Planning research and plan drafting
- Stage 1
- Stage 2
- Stage 3
- Stage 4
- Stage 5
- Stage 6

剩余阶段（Remaining stages）:

- none

下一步自动动作（Next automatic action）:

- final delivery complete

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

执行方（Executor）:

- 实施阶段使用 `complex-coding-executor`；规划阶段不得直接实现。

## 执行契约（Execution Contract）

```json
{
  "contract_version": 1,
  "task_id": "2026-07-08-feature-complex-coding-development-quality-gate",
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "approval_status": "approved",
  "approved_contract_hash": "external:attestation.json",
  "current_stage_id": "Final",
  "remaining_stage_ids": [],
  "stop_condition": "none",
  "commit_authorization": "authorized",
  "ledger_policy": "append-only-after-approval",
  "single_writer": "current executor session",
  "reapproval_required": false
}
```

契约规则（Contract rules）:

- 本节是 executor 可读的机器字段；`Execution Control Snapshot` 和 `Execution Control` 用于人类恢复和审计。
- `approved_contract_hash` 默认引用外部 `attestation.json`，避免把完整 plan hash 写入 plan 后造成自指哈希漂移。
- 修改 approved scope、stage 边界、验证策略、风险等级、工具授权或提交策略时，必须进入 `Plan Amendment Gate`。

## 目标条件（Goal Condition）

- 所有 approved stages 均为 complete，且 `final` 门禁通过。
- 无 open blocking decision、无未关闭 blocking/major review finding。
- planner 已能在方案阶段识别项目语言、技术栈、框架、API 类型和架构风险，并主动收集适用规范来源。
- planner 已能显式检查代码标准、语法规范、架构边界、设计模式取舍、低耦合和高内聚。
- executor 已能在阶段执行、Code Review、Stage Exit 和最终交付时引用规范索引并记录开发质量证据。
- 必需验证已执行，或无法执行项已记录原因、影响和替代证据。
- 提交授权状态明确；未授权时不得提交，但必须记录原因。

## 规划循环协议（Planning Loop Protocol）

- managed 计划默认拆为 3-7 个可独立验证阶段；本计划为 6 个阶段。
- 调研、浏览、搜索或查看多个来源后，关键 findings 必须写入 `Context`、`Source matrix` 或 artifacts。
- 重大决策前重读目标、约束、Options、Decision、影响面和 reapproval triggers。
- rejected options 必须记录放弃原因，避免上下文压缩后重复走回头路。
- Readiness 前必须重新运行 `Plan Quality Gate`、`Plan Self-Review` 和 `Readiness Gate`。

## 执行循环协议（Executor Work Loop）

- 每个阶段开始先读取 `Execution Contract`、`Resume Packet`、Stage Contract 和上一阶段 findings。
- 每次阶段动作后更新 ledger/progress；没有实质进展但需要保持长任务循环时写 heartbeat。
- 失败动作必须记录 attempt、命令或工具、失败原因、影响和下一策略；不得静默重复同一失败动作。
- Stage Transition Gate 通过且仍有 pending stage 时，下一动作必须是 `continue Stage N`。
- 只有满足 `Goal Condition` 后才能进入最终交付。

## 问题定义（Problem）

目标（Goal）:

- 为 `complex-coding-planner` 增加显式开发质量规划门禁，让复杂任务在审批前覆盖代码标准、语法规范、架构设计、设计模式取舍、低耦合和高内聚。
- 为 planning 阶段增加规范发现和收集机制：先识别项目语言、技术栈、框架、API 类型和架构风险，再主动搜索并沉淀适用规范索引。
- 为 `complex-coding-executor` 增加执行期开发质量检查，使阶段修改、review、验证和最终交付都能记录对应质量证据。
- 将补强落到模板、脚本、eval、README 和 changelog，形成可测试、可恢复、可审计的闭环。

非目标（Non-goals）:

- 不在规划阶段修改任何 skill 源码。
- 不强制所有任务采用复杂设计模式；目标是选择适合模式并拒绝过度设计。
- 不把 Google styleguide、AIP、SOLID 或设计模式全集硬塞进 skill；只写发现路径、选择规则和落盘索引要求。
- 不引入外部服务、长期后台进程或新的包管理依赖。
- 不自动迁移历史 `.harness` 任务；旧任务只在自然更新时补齐新字段。

验收标准（Acceptance）:

- planner 规则和模板新增 `Standards Discovery Gate`，要求按项目语言、框架、API/架构类型主动收集官方或高质量规范来源。
- planner 规则和模板新增 `Development Quality Gate`，覆盖标准来源、静态质量、架构边界、模式取舍、耦合/内聚和质量验证映射。
- `harness_plan_check.py` 能阻止缺少开发质量门禁的非模板计划通过，并允许模板模式保留占位。
- executor workflow、模板执行区和最终检查能要求引用 standards index 和开发质量 review 证据。
- eval 新增 planner/executor 场景，覆盖缺少开发质量规划、过度设计、缺少 lint/typecheck 映射和执行期架构漂移。
- README、CHANGELOG 和 `.harness/environment.md` 记录新规则、验证命令和交付证据要求。

约束（Constraints）:

- 遵守用户全局规则：中文注释、先读上下文、最小变更、分段写入、真实验证说明和提交信息格式。
- 遵守 `skill-creator` 原则：保持 `SKILL.md` 简洁，把详细流程放到 references；新增规则必须可触发、可执行、可验证。
- 遵守 Research Gate：规划阶段发现语言规范、框架结构、API 设计、架构模式、SOLID 或设计模式等不确定事实时，优先搜索官方、一手或高质量资料并记录来源。
- 遵守当前 planner：Readiness Gate 通过后停止，等待用户明确批准。
- 遵守当前 executor：批准后 run-to-completion、阶段门禁、ledger、review、验证和提交授权分离。
- 同一仓库 Git 命令必须串行；提交必须用户另行授权。

待确认项（Open uncertainties）:

- 无 blocking 问题。默认采用“规范先发现、风险分级、轻量强制”的开发质量门禁，不把所有任务推向重架构设计。

## 调研门禁（Research Gate）

研究模式（Research mode）:

- online-required

触发原因（Why this mode）:

- 本任务不仅修改本地 planner/executor 规则，还要规定规划阶段如何主动搜索语言规范、框架工程结构、API 设计规范、架构模式、SOLID 和设计模式资料。
- 用户明确给出 `google/styleguide`、Google Cloud API Design Guide 和 AIP design patterns 等在线规范来源；这些来源会影响方案设计和后续模板字段。
- 规范资料本身可能随语言、框架、API 设计实践和组织文档变化而更新，因此必须记录访问日期、来源类型、可信度和适用边界。

不确定项清单（Uncertainty inventory）:

| ID | 问题（Question） | 类型（Type） | 是否需要在线搜索（Online required） | 处理结果（Resolution） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- |
| U-001 | 当前 planner 是否已有开发质量硬门禁 | local-code | no | 已读 SKILL、workflow、template、plan_check，仅有流程质量和验证门禁 | 需要补强 |
| U-002 | 当前 executor 是否已有开发质量审查细则 | local-code | no | 已读 SKILL、workflow、exec_check，Code Review 只有严重程度，没有维护性维度 | 需要补强 |
| U-003 | skill 更新应如何组织内容 | local-doc | no | 已读 skill-creator，要求 SKILL.md 简洁、详细流程放 references、脚本负责确定性检查 | 指导落点 |
| U-004 | 是否需要阻塞用户决策 | user-decision | no | 用户已要求按 planner 规则落地方案，默认先规划后审批 | 无阻塞 |
| U-005 | 语言规范是否应直接内置到 skill | external-doc | yes | 不内置全集；planner 只写发现路径和 standards index 要求 | 影响 Stage 1/2 |
| U-006 | API/架构设计规范如何被引用 | external-doc | yes | 使用 Google Cloud API Design Guide、AIP 等作为候选一手来源；按项目类型适用 | 影响 Stage 1 |
| U-007 | 设计模式/SOLID 数量口径如何处理 | external-doc | yes | 不写死 22/23 或五/六项；要求在 standards index 中核验来源和适用性 | 影响 Development Quality Gate |

搜索记录（Search log）:

| 查询/来源（Query/source） | 工具（Tool） | 日期（Date） | 结果（Result） | 后续动作（Next action） |
| --- | --- | --- | --- | --- |
| `complex-coding-planner` SKILL/workflow/template/script | PowerShell read | 2026-07-08 | 已确认开发质量缺少独立章节和脚本校验 | 纳入 Stage 1/2 |
| `complex-coding-executor` SKILL/workflow/script | PowerShell read | 2026-07-08 | 已确认执行期 review 缺少架构和维护性维度 | 纳入 Stage 4 |
| `skill-creator` SKILL.md | PowerShell read | 2026-07-08 | 要求保持入口简洁、详细流程分流到 references、脚本做确定性验证 | 指导规则组织 |
| eval、README、CHANGELOG、`.harness` 状态 | PowerShell read + git | 2026-07-08 | 已确认需要补充 eval 和文档，旧 active task 已 completed | 纳入 Stage 4/5 |
| `https://github.com/google/styleguide` | web open | 2026-07-08 | Google styleguide 是多语言规范入口，包含 Go、C++、Java、Python、Shell、TypeScript 等 | Stage 1 引入语言规范发现 |
| `https://google.github.io/styleguide/go/` | web open | 2026-07-08 | Go Style 文档强调 readable/idiomatic Go、style guide/decisions/best practices 分层 | 作为 Go 项目示例 |
| `https://docs.cloud.google.com/apis/design` | web open | 2026-07-08 | Google API Design Guide 适用于 REST/RPC/gRPC/API surface，且是 living document | API 设计规范候选 |
| `https://google.aip.dev/general#design-patterns` | web open | 2026-07-08 | AIP general 按 API Concepts、Resource Design、Operations、Design Patterns 等分类 | API/AIP 规范索引候选 |
| design patterns / SOLID 数量口径 | web search | 2026-07-08 | 发现不同资料口径可能不同；GoF 常见说法为 23 个经典模式，SOLID 常见为五项 | 计划中要求核验，不硬编码 |

来源矩阵（Source matrix）:

| 结论（Claim） | 来源类型（Source type） | URL/路径（URL/path） | 是否官方/一手（Official/primary） | 访问日期（Accessed） | 可信度（Confidence） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- | --- |
| planner 当前强在流程质量，缺少开发质量门禁 | local | `skills/complex-coding-planner/references/planning-workflow.md` | yes | 2026-07-08 | high | Stage 1/2 |
| executor 当前 review 只定义严重程度，缺少具体质量维度 | local | `skills/complex-coding-executor/references/execution-workflow.md` | yes | 2026-07-08 | high | Stage 4 |
| 检查脚本当前未要求开发质量章节 | local | `skills/complex-coding-planner/scripts/harness_plan_check.py`、`skills/complex-coding-executor/scripts/harness_exec_check.py` | yes | 2026-07-08 | high | Stage 2/3 |
| skill 更新应保持入口短、细节放 references | local | `C:\Users\CountRa\.codex\skills\.system\skill-creator\SKILL.md` | yes | 2026-07-08 | high | 全部阶段 |
| 语言规范应按项目语言主动发现，而不是全量内置 | official/primary | `https://github.com/google/styleguide` | yes | 2026-07-08 | high | Standards Discovery Gate |
| Go 项目可优先参考 Google Go Style 的 guide/decisions/best practices 分层 | official/primary | `https://google.github.io/styleguide/go/` | yes | 2026-07-08 | high | Go 示例和模板说明 |
| API 设计可参考 Google Cloud API Design Guide，并按 REST/RPC/gRPC/API surface 适用性判断 | official/primary | `https://docs.cloud.google.com/apis/design` | yes | 2026-07-08 | high | API/后端架构规范发现 |
| AIP general 提供 API Concepts、Resource Design、Operations、Design Patterns 等分类索引 | official/primary | `https://google.aip.dev/general#design-patterns` | yes | 2026-07-08 | high | API design patterns 入口 |
| 设计模式和 SOLID 的数量口径不应写死，应在项目 standards index 中核验 | external | search results for GoF/SOLID | no | 2026-07-08 | medium | 避免把可能不准确的数量写成硬规则 |

调研结论（Research result）:

- passed。本任务需要把在线规范探索能力纳入方案；已确认应新增 `Standards Discovery Gate`，并要求后续具体项目按语言、框架、API 类型和架构风险收集官方/一手或高质量规范来源。

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）:

- online-required

技术栈清单（Technology inventory）:

| 类型（Type） | 发现（Finding） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 语言（Language） | 当前仓库以 Markdown、Python、JSONL、YAML、Shell 为主；被规划的 skill 需能识别目标项目语言 | `.harness/environment.md`、本地文件 | 决定 standards index 的语言规范入口 |
| 框架（Framework） | 本任务不绑定单一框架；planner 应在后续项目中按实际框架搜索官方结构和工程化规范 | 本地 skill 规则、用户要求 | 避免把 Go/Web/API 示例误写成全局硬规则 |
| API/架构类型（API/architecture） | 后续项目若涉及网络 API，应优先参考官方 API 设计规范和项目内接口约束 | Google Cloud API Design Guide、AIP general | 影响 API 设计、兼容性和验证映射 |
| 工具链（Toolchain） | 当前仓库验证依赖 Python 脚本、JSONL/YAML 解析和 Git diff check | `.harness/environment.md` | 决定本任务实现验证 |

规范来源矩阵（Standards source matrix）:

| 规范来源（Standard source） | 类型（Type） | 官方/一手（Official/primary） | 适用边界（Applicability） | 访问日期（Accessed） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- |
| `https://github.com/google/styleguide` | language | yes | 多语言规范发现入口，不复制全集 | 2026-07-08 | planner 后续按语言收集规范来源 |
| `https://google.github.io/styleguide/go/` | language | yes | Go 项目示例，适用于 Go 风格、decisions 和 best practices 分层 | 2026-07-08 | 模板示例和 standards index 引导 |
| `https://docs.cloud.google.com/apis/design` | API / architecture | yes | REST/RPC/gRPC/API surface 的设计参考 | 2026-07-08 | API 项目的架构设计规范入口 |
| `https://google.aip.dev/general#design-patterns` | API / pattern | yes | AIP 概念、资源、操作和设计模式分类索引 | 2026-07-08 | API design patterns 入口 |

standards index:

- 路径或章节（Path/section）: 当前计划使用本节和 `Source matrix` 作为 standards index；后续任务资料较多时写入 `.harness/tasks/<date>/<type>/<task-slug>/artifacts/standards/standards-index.md`。
- 摘要（Summary）: planner 不内置规范全集，而是先识别技术栈，再收集官方/一手或高质量规范来源、适用边界、访问日期和影响。
- 未覆盖或 blocked-by-access（Not covered / blocked）: 无 blocking；设计模式和 SOLID 数量口径不写死，要求按来源核验。

规范发现结论（Standards result）:

- passed。本任务已确定 Standards Discovery Gate 的规则、模板和脚本落点。

## 开发质量门禁（Development Quality Gate）

质量范围（Quality scope）:

| 维度（Dimension） | 规划结论（Plan） | 阶段映射（Stage mapping） | 验证映射（Validation mapping） |
| --- | --- | --- | --- |
| 代码标准（Code standards） | SKILL 入口保持简洁，细节放 workflow；新增注释遵守中文规则 | Stage 1-3 | 文档检索、plan check、diff check |
| 静态质量（Static quality） | Python 脚本需通过 py_compile，JSONL/YAML fixture 需可解析 | Stage 3、Stage 5、Stage 6 | `python -B -m py_compile`、fixture parse |
| 架构边界（Architecture boundaries） | planner 负责规划门禁，executor 负责执行期质量检查，不新增独立 skill | Stage 2、Stage 4 | 文件边界复查、exec check |
| 设计模式取舍（Design pattern decision） | 不强制 22/23 或五/六项口径，不把复杂模式强加给低风险任务 | Stage 2、Stage 3 | plan check 术语和模板字段 |
| 低耦合（Low coupling） | 保持 planner/executor 职责分离，脚本只做确定性结构检查 | Stage 2-4 | Code Review 和最终复查 |
| 高内聚（High cohesion） | standards discovery、development quality、execution check 各自落在最相关文件 | Stage 1-4 | 全文件复读和 final gate |

过度设计防护（Overengineering guard）:

- direct 任务继续轻量处理；managed 任务只要求显式记录开发质量结论，不要求引入新抽象或设计模式。

开发质量结论（Development quality result）:

- passed。本计划采用轻量强制、风险分级和 standards index 引用策略。

## 上下文（Context）

本地代码（Local code）:

- `skills/complex-coding-planner/SKILL.md`：入口规则已要求 Research Gate、Plan Self-Review、Readiness，但未提开发质量门禁。
- `skills/complex-coding-planner/references/planning-workflow.md`：Plan Quality Gate 覆盖证据、影响面、方案比较、验证和批准摘要，但未要求代码标准、架构边界和模式取舍。
- `skills/complex-coding-planner/templates/execution-plan.md`：影响面矩阵和 Stage Contract 没有开发质量字段，Code Review 只有执行期表格。
- `skills/complex-coding-planner/scripts/harness_plan_check.py`：当前 required sections 不包含开发质量章节，Plan Quality Gate 只查 pending。
- `skills/complex-coding-executor/references/execution-workflow.md`：阶段循环要求 code review 和验证，但审查维度缺少维护性、耦合、内聚、抽象和公共接口兼容。
- `evals/complex-coding-planner/*` 与 `evals/complex-coding-executor/*`：已有 Research Gate 和执行闭环场景，缺少开发质量场景。

本地文档（Local docs）:

- `.harness/environment.md`：仓库主分支为 `main`，feature 类型使用 `harness/feature`。
- `.harness/active-task.json`：上一 managed task 已 completed，本计划将 active task 切换到 awaiting_plan_approval。
- `README.md`：已说明 planner/executor 核心约束，但未说明 Development Quality Gate。
- `CHANGELOG.md`：需要新增本任务条目，提交信息保持 pending 到用户授权提交后更新。

外部来源（External sources）:

- Google styleguide: 多语言开发规范入口；后续 planner 应按项目语言选择对应规范，例如 Go 项目优先查 Go Style。
- Google Go Style: 提供 Style Guide、Style Decisions、Best Practices 分层，适合作为“不要把所有规则塞进 skill，而是按语言收集规范索引”的示例。
- Google Cloud API Design Guide: 适用于网络 API、REST/RPC/gRPC/API surface 的设计参考。
- Google AIP general: 提供 API Concepts、Resource Design、Operations、Design Patterns 等分类索引，适合 API/后端设计任务引用。
- 设计模式和 SOLID: 后续不在 skill 中写死数量，要求按项目语言、范式和架构场景核验来源、适用性和过度设计风险。

用户约束（User constraints）:

- 用户要求按当前 planner 规则落地补强方案，后续实现阶段按 executor 规范执行。
- 用户关注代码标准、语法规范、优秀架构设计、多设计模式、低耦合高内聚等开发侧规则是否缺失。
- 用户补充要求：规划阶段对不确定的语言规范、框架结构、工程化后端项目结构、架构设计和设计模式主动搜索相关规范，并可将规范索引、摘要或许可允许的快照沉淀到 `.harness` artifacts，供后续设计和实现参考。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 本任务属于 managed planning-only | confirmed | 用户要求 + planner 分级规则 | 必须落盘计划并等待审批 |
| 开发质量规则是当前缺口 | read/confirmed | planner/executor workflow、template、scripts、eval | 方案核心目标 |
| 应新增规范发现阶段 | external/confirmed | Google styleguide、Google API Design Guide、AIP general、用户补充要求 | Stage 1 |
| 应采用轻量强制而非模式堆砌 | confirmed | 用户关注点 + skill-creator 简洁原则 + 外部规范分层 | 方案设计原则 |

## 候选方案（Options）

### 方案 A：只补文字规则（Minimal Change）

- 做法（How）: 在 planner/executor workflow 增加几条开发质量说明。
- 优点（Pros）: 改动小，风险低。
- 缺点（Cons）: 无模板字段和脚本校验，实际规划仍容易遗漏。
- 风险（Risks）: 质量规则停留在口号层面。
- 验证（Validation）: 文档检索和 diff 检查。
- 回滚（Rollback）: revert 文档变更。

### 方案 B：开发质量门禁闭环（Structured Gate）

- 做法（How）: 新增 `Standards Discovery Gate` 和 `Development Quality Gate`，同步更新 planner/executor 规则、模板、脚本、eval 和 README。
- 优点（Pros）: 规则可见、模板可填、脚本可拦、eval 可回归。
- 缺点（Cons）: 修改面更大，需要兼顾旧计划兼容。
- 风险（Risks）: 如果门禁太重，会让简单任务负担过高。
- 验证（Validation）: plan check、exec check、py_compile、JSONL 解析、diff check。
- 回滚（Rollback）: revert 相关文件；旧计划不受迁移影响。

### 方案 C：独立工程质量 skill（Separate Skill）

- 做法（How）: 新建单独 skill，planner/executor 只引用它。
- 优点（Pros）: 职责分离清晰，可独立演进。
- 缺点（Cons）: 触发链路更复杂，当前缺口仍需要 planner/executor 显式消费。
- 风险（Risks）: 多 skill 协作增加上下文负担。
- 验证（Validation）: skill validate 和 forward test。
- 回滚（Rollback）: 移除新 skill 及引用。

### 方案 D：内置完整规范库（Embedded Standards Corpus）

- 做法（How）: 把 Google styleguide、API 设计规范、SOLID 和经典设计模式完整写入 skill 或仓库。
- 优点（Pros）: 离线可读，执行时少搜索。
- 缺点（Cons）: 体积大、维护成本高、版权和版本漂移风险高，也会污染 skill 上下文。
- 风险（Risks）: 规范过期后仍被模型当成最新权威；模式数量和原则口径被硬编码。
- 验证（Validation）: 需要持续同步外部规范，不适合当前仓库。
- 回滚（Rollback）: 删除内置规范库。

## 决策（Decision）

选择方案（Chosen option）:

- 方案 B：开发质量门禁闭环。

原因（Why）:

- 当前缺口不是缺少通用工程知识，而是 planner/executor 没有把“按项目主动寻找适用规范”和“按规范做设计取舍”变成可审批、可执行、可验证的状态字段。
- 方案 B 可以沿用现有 `.harness` 结构，新增 standards index 作为任务级证据，不把外部规范全集塞进 skill。
- 方案 A 过软；方案 C 对当前项目来说过早，会增加 skill 触发复杂度；方案 D 维护和版权风险高。

影响（Impact）:

- planner 入口规则、workflow、execution-plan 模板和 plan check 会新增规范发现和开发质量要求。
- executor workflow、执行期模板区域和 final check 会新增 standards index 引用和开发质量证据要求。
- eval、README、CHANGELOG 和 `.harness` 状态会同步补充。

可逆性（Reversibility）:

- 高。改动集中在 Markdown、Python 检查脚本、eval fixture 和文档，可通过单次 revert 回退。

变更条件（Change conditions）:

- 如果实现时发现脚本硬拦截会破坏已有已批准计划，应改为“新计划强制、旧计划 best-effort 记录”的兼容策略。
- 如果新增规则导致 direct 小任务被迫 managed，应收缩触发条件，只让 managed 任务强制填门禁。
- 如果规范收集需要下载大量外部文档，应改为保存索引、摘要和少量必要摘录，不整仓库镜像外部资料。

方案变更触发条件（Reapproval triggers）:

- 新增独立 skill 或新外部依赖。
- 改变阶段数量、阶段边界或提交策略。
- 将开发质量门禁改为所有 direct 任务也强制执行。
- 引入会修改历史 `.harness` 任务的迁移脚本。
- 将外部规范全集内置到 skill 或仓库。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | planner/executor skill 触发和规则语义 | medium | eval + README 检索 | yes |
| 数据结构（Data model） | yes | `execution-plan.md` 模板章节和检查字段 | medium | plan check 模板/实例 | yes |
| 前端交互（Frontend interaction） | no | none | low | not-applicable | no |
| 配置/环境（Config/environment） | yes | `.harness/environment.md` 命令说明 | low | JSON/Markdown 检查 | yes |
| 兼容性（Compatibility） | yes | 旧计划缺少新章节时 executor 处理 | medium | exec check 兼容场景 | yes |
| 测试（Tests） | yes | planner/executor eval、py_compile、JSONL | medium | 运行验证命令 | yes |
| 文档（Documentation） | yes | README、CHANGELOG、workflow 文档 | low | diff check | yes |
| 架构/模块边界（Architecture boundary） | yes | planner/executor 规则分工 | medium | Development Quality Gate 自查 | yes |
| 代码标准/静态质量（Coding standard） | yes | 模板、workflow、validation 映射 | medium | lint/typecheck 映射检查 | yes |
| 规范收集（Standards discovery） | yes | `.harness/tasks/<task>/artifacts/standards/`、execution-plan standards index | medium | Research Gate + artifacts 索引检查 | yes |

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：规范发现和 standards index

目标（Goal）:

- 建立 planner 在规划阶段主动识别项目语言、技术栈、框架、API 类型和架构风险，并收集适用规范的标准流程。

做法（How）:

- 在 planner workflow 和模板中新增 `Standards Discovery Gate`，要求先从本地项目文件识别语言、框架、包管理器、API 类型、运行形态和架构风险。
- 为每个 managed 任务规划 `artifacts/standards/standards-index.md` 或等价章节，记录规范来源、适用范围、可信度、访问日期、关键结论、是否官方/一手、是否需要下载/摘要。
- 规范来源优先级：项目内 `docs/development.md`/AGENTS > 官方语言规范和 styleguide > 官方框架/平台文档 > API/架构官方规范 > 高质量二手资料。
- 示例规则：Go 项目优先搜索 Google Go Style 和项目内 gofmt/go vet/golangci-lint 配置；Web 后端项目还需搜索对应框架官方结构建议、REST/gRPC/API 设计规范和工程化项目结构资料。
- 对 Google styleguide、Google Cloud API Design Guide、AIP 等资料只保存索引、摘要和必要短摘录；只有许可证允许且规模可控时才保存快照，不整仓库镜像。

原因（Why）:

- 不同语言和技术栈适用规范不同，把全集写进 skill 会过重；让 planner 主动发现并落盘索引，才能在后续设计和实现阶段持续引用。

位置（Where）:

- 文件/模块（Files/modules）: `skills/complex-coding-planner/SKILL.md`、`skills/complex-coding-planner/references/planning-workflow.md`、`skills/complex-coding-planner/templates/execution-plan.md`
- API/配置（APIs/configs）: `Standards Discovery Gate`、standards index artifacts
- 测试/文档（Tests/docs）: planner eval、README、CHANGELOG

参考来源（References）:

- Google styleguide、Google Go Style、Google Cloud API Design Guide、AIP general。
- 当前 Research Gate 规则和用户补充要求。

验证（Validation）:

- 检索 `Standards Discovery Gate`、`standards-index`、`google/styleguide`、`API Design Guide`、`AIP`、`框架`、`架构风险`。
- 当前计划检查应要求 Standards Discovery Gate 或 standards index 证据。

风险和回滚（Risks and rollback）:

- 风险：规范收集过度，导致规划阶段变慢。缓解：按风险分级；简单 direct 任务不强制 managed standards index。
- 风险：外部资料版权或体积不可控。缓解：默认保存索引和摘要，不全量下载。
- 回滚：移除 Standards Discovery Gate 相关规则、模板字段和 eval。

阶段契约（Stage Contract）:

- 范围（Scope）: 规范发现流程、索引模板和 artifacts 策略。
- 允许修改（Allowed changes）: planner 规则、模板、eval/README 中的规范发现说明。
- 禁止修改（Forbidden changes）: executor 执行规则和脚本硬校验。
- 进入条件（Entry checks）: 重读本计划、Research Gate 和在线来源矩阵。
- 退出条件（Exit checks）: planner 明确何时搜索规范、如何记录来源、何时沉淀 artifacts。
- 必需验证（Required validation）: 文档检索 + plan check。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 2（Stage 2）：planner 开发质量规则

目标（Goal）:

- 在 `complex-coding-planner` 中定义 Development Quality Gate 的触发、内容和风险分级，并要求它引用 Standards Discovery Gate 的规范索引。

做法（How）:

- 更新 `SKILL.md`，只加入入口级硬规则，保持简洁。
- 更新 `references/planning-workflow.md`，新增开发质量门禁章节，说明如何基于 standards index 覆盖代码标准、语法/静态质量、架构边界、模式取舍、耦合/内聚和验证映射。
- 规定 direct 任务仍轻量处理；managed 任务必须显式记录开发质量结论。

原因（Why）:

- planner 是方案审批入口，必须在批准前暴露开发质量风险，并明确这些判断来自哪些项目内或外部规范。

位置（Where）:

- 文件/模块（Files/modules）: `skills/complex-coding-planner/SKILL.md`、`skills/complex-coding-planner/references/planning-workflow.md`
- API/配置（APIs/configs）: skill 触发说明和 managed 规划流程
- 测试/文档（Tests/docs）: planner eval、README、CHANGELOG

参考来源（References）:

- Stage 1 的 Standards Discovery Gate。
- `planning-workflow.md` 的 Plan Quality Gate 和 Plan Self-Review。
- `skill-creator` 的简洁入口和 progressive disclosure 原则。

验证（Validation）:

- 检索 `Development Quality Gate`、`standards index`、`代码标准`、`架构边界`、`设计模式`、`耦合`、`内聚`。
- 确认 `SKILL.md` 仍只保留核心规则，细节放 workflow。

风险和回滚（Risks and rollback）:

- 风险：规则过重导致 planner 冗长。缓解：使用风险分级和 not-applicable 说明。
- 回滚：恢复 planner 两个文件。

阶段契约（Stage Contract）:

- 范围（Scope）: planner 规则文档。
- 允许修改（Allowed changes）: `SKILL.md` 和 `planning-workflow.md`。
- 禁止修改（Forbidden changes）: executor、脚本、eval、README。
- 进入条件（Entry checks）: Stage 1 完成，重读本计划、planner SKILL/workflow。
- 退出条件（Exit checks）: planner 规则包含明确开发质量门禁、standards index 引用和轻量化策略。
- 必需验证（Required validation）: 文档检索。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 3（Stage 3）：planner 模板和 plan check

目标（Goal）:

- 让 Standards Discovery Gate 和 Development Quality Gate 成为 execution-plan 模板和 plan check 的可验证字段。

做法（How）:

- 在 `templates/execution-plan.md` 增加规范发现和开发质量章节，并把它们纳入 Plan Quality Gate、Plan Self-Review、Readiness Gate、Impact Matrix 和 Stage Contract。
- 更新 `harness_plan_check.py`，新增 required section 和关键术语检查；模板模式允许占位，普通计划必须关闭门禁。
- 保持旧计划兼容策略：只对被检查的新计划强制；不写迁移脚本。

原因（Why）:

- 单纯文档规则不能稳定改变 planner 输出，模板和脚本是确定性护栏。

位置（Where）:

- 文件/模块（Files/modules）: `skills/complex-coding-planner/templates/execution-plan.md`、`skills/complex-coding-planner/scripts/harness_plan_check.py`
- API/配置（APIs/configs）: `--allow-template` 语义保持不变
- 测试/文档（Tests/docs）: plan check、py_compile

参考来源（References）:

- Stage 1 的 standards index 字段。
- 当前 `harness_plan_check.py` 的 required sections、gate status 和 Research Gate 检查。

验证（Validation）:

- `python -B skills/complex-coding-planner/scripts/harness_plan_check.py --plan skills/complex-coding-planner/templates/execution-plan.md --allow-template`
- `python -B skills/complex-coding-planner/scripts/harness_plan_check.py --plan .harness/tasks/2026-07-08/feature/complex-coding-development-quality-gate/execution-plan.md`
- `python -B -m py_compile skills/complex-coding-planner/scripts/harness_plan_check.py`

风险和回滚（Risks and rollback）:

- 风险：脚本检查过严误拦合理计划。缓解：只检查章节、关键术语和 gate 状态，不做复杂语义判断。
- 回滚：恢复模板和脚本。

阶段契约（Stage Contract）:

- 范围（Scope）: planner 模板和检查脚本。
- 允许修改（Allowed changes）: template、plan_check。
- 禁止修改（Forbidden changes）: executor 和 eval。
- 进入条件（Entry checks）: Stage 1-2 完成。
- 退出条件（Exit checks）: 模板模式和实例计划检查均通过。
- 必需验证（Required validation）: plan check + py_compile。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 4（Stage 4）：executor 开发质量执行闭环

目标（Goal）:

- 在执行阶段增加 Development Quality Check，要求每阶段引用 standards index，并覆盖修改前、review、验证和最终交付。

做法（How）:

- 更新 executor `SKILL.md` 入口规则，要求每阶段 review 覆盖 standards index 和开发质量。
- 更新 `references/execution-workflow.md`，新增 Development Quality Check，明确规范引用、代码标准、静态质量、架构边界、模式取舍、耦合/内聚、兼容性和过度设计的 review 维度。
- 更新 `harness_exec_check.py`，final 阶段要求计划中存在 standards index 或开发质量证据；对旧计划缺失时应给出清晰失败原因或兼容说明。

原因（Why）:

- planner 只能规划质量要求，executor 才能在真实改动后检查是否按规范索引和质量门禁落实。

位置（Where）:

- 文件/模块（Files/modules）: `skills/complex-coding-executor/SKILL.md`、`references/execution-workflow.md`、`scripts/harness_exec_check.py`
- API/配置（APIs/configs）: final gate 证据词
- 测试/文档（Tests/docs）: exec check、py_compile

参考来源（References）:

- Stage 1 standards index、executor 阶段循环、Code Review、Validation 和最终交付门禁。

验证（Validation）:

- `python -B -m py_compile skills/complex-coding-executor/scripts/harness_exec_check.py`
- 在本计划批准后，使用 executor preflight/status/final 的适用模式验证字段一致性。

风险和回滚（Risks and rollback）:

- 风险：旧计划 final check 被新增术语阻断。缓解：实施时明确旧计划兼容策略，必要时只对含新章节计划强制。
- 回滚：恢复 executor 三个文件。

阶段契约（Stage Contract）:

- 范围（Scope）: executor 规则和检查脚本。
- 允许修改（Allowed changes）: executor SKILL/workflow/exec_check。
- 禁止修改（Forbidden changes）: planner 规则、eval、README。
- 进入条件（Entry checks）: Stage 3 完成。
- 退出条件（Exit checks）: 执行期开发质量证据要求清晰且可验证。
- 必需验证（Required validation）: py_compile + final check 兼容性复查。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 5（Stage 5）：eval 和文档同步

目标（Goal）:

- 用 eval 和文档固定新行为，避免后续规则回退。

做法（How）:

- planner eval 新增缺少规范发现、缺少开发质量门禁、缺少 lint/typecheck 映射、架构边界遗漏、设计模式过度使用等场景。
- executor eval 新增执行期忽略 standards index、架构漂移、review 未覆盖开发质量、final 缺少质量证据等场景。
- README 增加 planner/executor 规范发现和开发质量规则摘要。
- CHANGELOG 新增本任务条目，commit 信息保持 pending。

原因（Why）:

- eval 是 skill 行为的回归样本；README 和 CHANGELOG 是用户可见入口。

位置（Where）:

- 文件/模块（Files/modules）: `evals/complex-coding-planner/*`、`evals/complex-coding-executor/*`、`README.md`、`CHANGELOG.md`
- API/配置（APIs/configs）: none
- 测试/文档（Tests/docs）: JSONL/YAML 解析、diff check

参考来源（References）:

- 现有 Research Gate、Research Drift 和用户新增规范发现要求。

验证（Validation）:

- JSONL 解析并检查 id 唯一。
- `git -c diff.autoRefreshIndex=false diff --check`

风险和回滚（Risks and rollback）:

- 风险：eval 只描述愿望、不可判定。缓解：expected.yaml 使用明确布尔项。
- 回滚：恢复 eval 和文档。

阶段契约（Stage Contract）:

- 范围（Scope）: eval 和文档。
- 允许修改（Allowed changes）: evals、README、CHANGELOG。
- 禁止修改（Forbidden changes）: skill 规则和脚本。
- 进入条件（Entry checks）: Stage 1-4 完成。
- 退出条件（Exit checks）: eval 场景覆盖 planner/executor 新规则。
- 必需验证（Required validation）: JSONL/YAML 检查 + diff check。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 6（Stage 6）：整体复查和最终验证

目标（Goal）:

- 复查规则、模板、脚本、eval 和文档一致性，完成最终交付证据。

做法（How）:

- 重读所有修改文件，确认 Standards Discovery Gate、Development Quality Gate 名称、触发条件、字段和验证命令一致。
- 运行 planner 模板检查、当前计划检查、Python 编译、JSONL 解析和 diff check。
- 更新 `.harness` 计划进度、Code Review、Validation Evidence、Resume Summary 和 Commit Log。

原因（Why）:

- 该变更横跨 planner/executor，最终一致性比单文件正确更重要。

位置（Where）:

- 文件/模块（Files/modules）: 所有本任务触及文件和 `.harness` 记录
- API/配置（APIs/configs）: not-applicable
- 测试/文档（Tests/docs）: 全部验证证据

参考来源（References）:

- 本 execution-plan 的 Goal Condition、Research Gate、Impact Matrix、Stage Contract 和 Validation。

验证（Validation）:

- `python -B skills/complex-coding-planner/scripts/harness_plan_check.py --plan skills/complex-coding-planner/templates/execution-plan.md --allow-template`
- `python -B skills/complex-coding-planner/scripts/harness_plan_check.py --plan .harness/tasks/2026-07-08/feature/complex-coding-development-quality-gate/execution-plan.md`
- `python -m py_compile skills/complex-coding-planner/scripts/harness_plan_check.py skills/complex-coding-executor/scripts/harness_exec_check.py`
- JSONL/YAML fixture 检查。
- `git -c diff.autoRefreshIndex=false diff --check`

风险和回滚（Risks and rollback）:

- 风险：验证覆盖脚本结构但不证明模型行为完全改变。缓解：eval 覆盖代表性提示，最终报告未覆盖范围。
- 回滚：按文件组回退本任务改动。

阶段契约（Stage Contract）:

- 范围（Scope）: 全局复查和最终验证。
- 允许修改（Allowed changes）: 必要的一致性修补和 `.harness` 记录。
- 禁止修改（Forbidden changes）: 引入新功能范围或改变已批准阶段边界。
- 进入条件（Entry checks）: Stage 1-5 完成。
- 退出条件（Exit checks）: 验证证据完整，无 blocking/major finding。
- 必需验证（Required validation）: 全部最终验证。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- 当前 workspace: `D:\Item\vibe_coding\dev-skills`
- 当前分支: `harness/feature`
- 当前语言/格式: Markdown、Python、JSONL、YAML
- 长期进程: 不需要

临时覆盖（Temporary overrides）:

- Python 验证使用 `python -B`，避免写入 `__pycache__`。

## Git 上下文（Git Context）

主分支（Main branch）:

- main

任务类型（Task type）:

- feature

工作分支（Working branch）:

- harness/feature

分支动作（Branch action）:

- reuse

同步来源（Sync source）:

- main；当前分支已有 3 个本任务线前置提交，均属于已完成的 complex-coding planner/executor 工作。

最近同步（Last sync）:

- 2026-07-08，当前未执行 merge/rebase。

分支占用（Branch occupancy）:

- 串行 `git log <main>..HEAD`: `5b21f0e`、`bcc6fe1`、`2b34306`
- 串行 `git -c diff.autoRefreshIndex=false diff <main>...HEAD --name-only`: 主要为 planner/executor、eval、README、CHANGELOG 和 `.harness` 记录。
- 现有提交属于本任务（Existing commits belong to this task）: no，属于同一 feature 线已完成前置任务；本任务继续复用 harness/feature。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行：yes
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git：yes
- 非 Git 文件读取和文本搜索是否可并发：yes

只读 Git 选项（Read-only Git options）:

- 状态检查优先：`git --no-optional-locks status --short --branch`
- diff 检查优先：`git -c diff.autoRefreshIndex=false diff <range>`
- 最终提交前如需精确状态，可在确认无其它 Git 命令运行后串行执行普通 `git status --short --branch`

Index lock 恢复策略（Index lock recovery）:

- lock 路径解析命令：`git rev-parse --git-path index.lock`
- 删除前检查：精确路径、文件存在、大小/mtime 稳定、无活跃或未知归属 Git 进程
- 删除范围：只删除解析出的精确 `index.lock`，禁止通配符、递归删除和删除其它 `.lock`
- 删除后检查：串行 `git --no-optional-locks status --short --branch`

Git Lock Recovery Log:

| 时间（Time） | lock 路径（Lock path） | 文件大小/mtime（Size/mtime） | Git 进程检查（Process check） | 操作（Action） | 后续 status（Follow-up status） |
| --- | --- | --- | --- | --- | --- |
| not-applicable | none | none | none | none | none |

提交策略（Commit policy）:

- 实施批准不等于提交授权。
- 用户已明确授权修改完成后提交；executor 必须按 `git commit -F` 规范提交。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: no
- 未合回时代码停留在（If not merged, code remains on）: `harness/feature`
- 合并前需要用户确认（User confirmation needed before merge）: yes

分支安全（Branch safety）:

- 切换前已检查工作区：yes
- 不自动 stash：yes
- 不自动 rebase：yes
- 不自动 reset：yes

热修复插入（Hotfix interruption）:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支：yes
- 决策：not-applicable

未解决问题（Open issues）:

- 无 blocking Git 问题。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| PowerShell | 文件读取和目录创建 | Planning/All | available | low | none | not required |
| apply_patch | 分段修改文件 | All | available | low | 缩小 patch 重试 | not required |
| Python `-B` | 脚本编译和检查 | Stage 2/3/5 | available | low | 记录无法执行原因 | not required |
| Git | 串行状态和 diff 检查 | All | available | medium | 只读 `--no-optional-locks` | not required |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- no

process-manager skill 是否存在（process-manager skill available）:

- not-required

规则结论（Rule decision）:

- 本任务只运行有限命令，例如 Python 编译、planner 检查、JSONL 解析和 diff check，不进入 process-manager。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | other | all | none | not-applicable | none | none | not-applicable |

禁止 shell 后台启动确认（No shell background start）:

- confirmed

历史视图需求（Needs `pm_list --history`）:

- no

证据保留位置（Evidence retention location）:

- `execution-plan.md`

日志沉淀确认（Log evidence persisted）:

- not-applicable

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前必须复查本节。
- 本任务不启动长期进程；若范围变化需要长期服务，进入 Plan Amendment Gate。

## 验证（Validation）

必需验证（Required）:

- `python -B skills/complex-coding-planner/scripts/harness_plan_check.py --plan .harness/tasks/2026-07-08/feature/complex-coding-development-quality-gate/execution-plan.md`
- `python -B skills/complex-coding-planner/scripts/harness_plan_check.py --plan skills/complex-coding-planner/templates/execution-plan.md --allow-template`
- `python -B -m py_compile skills/complex-coding-planner/scripts/harness_plan_check.py skills/complex-coding-executor/scripts/harness_exec_check.py`
- JSONL/YAML fixture 解析和 id 唯一检查。
- Standards Discovery Gate 相关术语和 artifacts 路径检查。
- `git -c diff.autoRefreshIndex=false diff --check`

已执行（Executed）:

- 命令/工具（Command/tool）: plan check、exec transition、AST syntax check、提权 `py_compile`、JSONL/YAML parse、`git diff --check`
- 结果（Result）: passed；`diff --check` 仅提示 CRLF 转换，无 whitespace error。
- 证据（Evidence）: Validation Evidence 表、ledger、最终验证输出。
- 覆盖范围（Covers）: planner/executor 规则、模板、脚本、eval、README、CHANGELOG 和当前执行计划。
- 未覆盖（Not covered）: 未来真实 managed 任务的模型行为仍需后续 forward-test。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | local reads + web research + serial git checks | passed | 当前规则、脚本、eval、文档、Git 状态和在线规范来源 | 实施后验证 | execution-plan.md | proceed |
| Stage 1 | standards discovery inspection | passed | standards index 和 artifacts 策略 | 具体项目规范内容 | Standards Discovery Gate + template | recorded |
| Stage 2 | planner rule search | passed | planner 开发质量规则 | 真实 forward test | SKILL/workflow diff | recorded |
| Stage 3 | planner plan check + AST syntax check | passed | 模板、当前计划和 plan_check 语法 | py_compile 初次受 `__pycache__` 权限影响 | plan_check output + AST | used elevated py_compile later |
| Stage 4 | exec transition + AST syntax check | passed | executor workflow 和 exec_check 逻辑 | 真实 forward test | exec_check output + AST | recorded |
| Stage 5 | JSONL/YAML parse | passed | eval fixture 解析和 id 唯一 | 真实评估器行为 | parse output | recorded |
| Stage 6 | final validation batch + elevated py_compile + diff check | passed | 整体一致性、脚本编译、fixture、whitespace | CRLF 转换提示 | validation output + ledger | final gate |

可选验证（Optional）:

- 使用后续真实 managed 任务 forward-test 新门禁。

产物（Artifacts）:

- 截图（Screenshot）: not-applicable
- 日志（Log）: 验证输出写入本计划摘要
- Trace: not-applicable
- 报告（Report）: 本 execution-plan
- Standards index: 当前计划使用 `规范发现门禁（Standards Discovery Gate）` 和 `Source matrix` 作为 standards index；资料较多的未来任务可生成 `.harness/tasks/<task>/artifacts/standards/standards-index.md`

未覆盖（Not covered）:

- 本计划不证明所有未来模型行为完全符合规则；通过 eval 和脚本降低回归风险。

无法执行时（If unable to run）:

- 记录命令、失败原因、影响和替代证据；不得声称通过。

## 文档（Documentation）

必需更新（Required updates）:

- `README.md`
- `CHANGELOG.md`
- planner/executor workflow 和模板
- `.harness/tasks/<task>/artifacts/standards/standards-index.md` 生成规则或模板说明
- eval README 如需要补充覆盖范围

Changelog 计划（Changelog plan）:

- 新增 `2026-07-08` 条目：planner/executor 规范发现和开发质量门禁补强。
- Commit 字段保持 pending，直到用户授权提交。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `planning-workflow.md` | yes | 新增章节和相关门禁行 | 重新读取并检索关键词 |
| `execution-plan.md` template | yes | 独立章节、门禁表、Stage Contract 表 | plan check + reread |
| standards artifacts 模板/说明 | no | `artifacts/standards/standards-index.md` 结构说明 | 重新读取并检索来源字段 |
| Python scripts | yes | 常量、函数、检查调用分段 | py_compile + targeted checks |
| eval JSONL/YAML | no | 追加独立样例 | JSONL/YAML parse |
| README/CHANGELOG | no | 独立段落 | diff check |

写入规则（Write rules）:

- 分段 patch 是落盘策略，不要求一次性生成全部细节；大内容首次写入前必须先有全局框架，再分模块递进式细化，最后整体复查。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 目标文件超过 500 行时，默认禁止整文件重写。
- 代码、文档、规划、模板、eval、changelog 和任务状态文件都适用。

整体复查（Whole-file review）:

- 写完后重新读取完整目标文件：yes
- 需要检查的整体一致性：门禁名称、触发条件、验证命令、README/CHANGELOG/eval 术语一致。
- 对应验证命令或方式：grep/Select-String、plan check、py_compile、JSONL parse、diff check。

patch 失败处理（Patch failure handling）:

- 读取目标文件确认是否有部分写入。
- 失败原因判断：上下文漂移、行尾、片段过大或路径错误。
- 重试策略：缩小 patch，使用更稳定上下文。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| Q-001 | no | closed | 是否新建独立 skill | 本轮不新建，先补 planner/executor | Decision |
| Q-002 | no | closed | 是否强制所有任务复杂架构设计 | 否，仅 managed 任务显式记录，direct 保持轻量 | Development Quality Gate |
| Q-003 | no | closed | 是否把外部规范全文下载到仓库 | 否，默认保存索引、摘要、URL 和必要短摘录；许可允许且规模可控时才保存快照 | Standards Discovery Gate |
| Q-004 | no | closed | 是否写死设计模式/SOLID 数量 | 否，按来源核验并记录项目适用性，避免把可能不准确口径变成硬规则 | Development Quality Gate |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | passed | Context 和 Evidence levels 已记录 |
| Research Gate 已完成（Research Gate complete） | passed | 本计划为 online-required，来源矩阵包含 Google styleguide、Go Style、API Design Guide 和 AIP |
| 影响面矩阵完整（Impact matrix complete） | passed | 已覆盖 API、数据、兼容、测试、文档、架构和代码标准 |
| 候选方案比较充分（Options compared enough） | passed | 已比较 A/B/C 三种方案 |
| 每阶段可独立验证（Stages independently verifiable） | passed | 每阶段均有 Stage Contract 和验证 |
| 方案变更触发条件清楚（Reapproval triggers clear） | passed | Decision 已记录 reapproval triggers |
| 用户批准摘要可记录（Approval summary ready） | passed | Plan Approval 预留批准范围和提交授权 |
| 规范发现门禁已纳入计划（Standards discovery planned） | passed | Stage 1 覆盖 standards index、在线来源和 artifacts 策略 |
| 开发质量门禁已纳入计划（Development quality planned） | passed | Stage 2-6 覆盖 planner、executor、模板、脚本、eval、文档和最终验证 |

质量结论（Quality result）:

- passed。方案已具备提交用户审批的结构和证据。

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- passed

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 初始想法容易把“多设计模式”理解成强制套模式 | 改为“模式取舍和过度设计拒绝” | closed |
| 优化（Optimizations） | 可避免新建独立 skill，减少触发复杂度和外部规范全文维护成本 | 选择方案 B，不采用方案 C/D | closed |
| 缺失项（Missing items） | 用户补充后需要规范发现和在线来源沉淀阶段 | 新增 Stage 1 和 Standards Discovery Gate | closed |
| 缺失项（Missing items） | 需要 executor final 证据和 eval 覆盖 | Stage 4/5/6 已补充 | closed |
| 风险（Risks） | 脚本过严可能影响旧计划 | 记录兼容策略和 reapproval trigger | closed |
| 风险（Risks） | 外部规范可能过期、体积过大或数量口径不同 | Research Gate 改为 online-required，默认保存索引摘要而非全集 | closed |
| 一致性（Consistency） | 规划和执行规则都需使用同一门禁名称 | 统一为 `Standards Discovery Gate` 与 `Development Quality Gate/Check` | closed |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：no
- `Plan Self-Review` 是否需要重跑：no
- `Readiness Gate` 是否需要重跑：no
- 原因：当前自查未改变目标、范围、阶段、验证或提交策略。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | passed | Problem/Acceptance |
| 上下文已收集（Context collected） | passed | planner/executor/template/scripts/eval/docs 已读 |
| 调研门禁已通过（Research Gate passed） | passed | 调研门禁 online-required passed，已记录在线来源 |
| 规范发现门禁已通过（Standards Discovery Gate passed） | passed | 已新增正式章节，覆盖技术栈、规范来源、standards index、官方来源和适用边界 |
| 开发质量门禁已通过（Development Quality Gate passed） | passed | 已新增正式章节，覆盖代码标准、静态质量、架构边界、设计模式、耦合、内聚和验证映射 |
| 候选方案已比较（Options compared） | passed | Options A/B/C |
| 决策已记录（Decision recorded） | passed | 选择方案 B |
| 实施阶段已细化（Implementation stages detailed） | passed | Stage 1-6 |
| 环境已确认（Environment confirmed） | passed | Environment |
| Git 上下文已确认（Git context confirmed） | passed | Git Context |
| 工具已确认（Tooling confirmed） | passed | Tooling |
| 验证已确认（Validation confirmed） | passed | Validation |
| 最终交付证据已规划（Final delivery evidence planned） | passed | Validation Evidence + final gate |
| 文档更新已确认（Documentation updates confirmed） | passed | Documentation |
| 风险已识别（Risks identified） | passed | Risks and rollback |
| 规划自查已通过（Plan self-review passed） | passed | Plan Self-Review |
| 阻塞问题已关闭（Blocking questions closed） | passed | Questions And Overrides |

就绪结论（Readiness result）:

- passed。用户已在 2026-07-08 明确批准进入实现阶段，并授权修改完成后提交。

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 2026-07-08 用户批准：“按 complex-coding-executor 进入实现阶段，修改完成后可以提交”。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: Stage 1-6 全部批准，按本计划由 `complex-coding-executor` 执行。
- 阶段提交授权（Stage commit authorization）: authorized
- 工具/MCP 授权（Tool/MCP authorization）: local shell/apply_patch/Python/Git read checks plus required online research for standards discovery
- 文档更新授权（Documentation authorization）: authorized

提交策略（Commit policy）:

- `authorized`

## 方案变更门禁（Plan Amendment Gate）

需要重新批准（Requires reapproval）:

- approved scope 改变: yes
- 阶段边界、顺序或 Stage Contract 改变: yes
- 必需验证、工具授权、长期进程策略或提交策略改变: yes
- 风险等级、公共接口、数据结构、权限、依赖或兼容性假设改变: yes
- attestation mismatch 且无法证明是预期文档更新: yes

无需重新批准的记录（No-reapproval records）:

| 时间（Time） | 变更（Change） | 原因（Reason） | 证据（Evidence） |
| --- | --- | --- | --- |
| 2026-07-08 | 创建规划文档 | planner 阶段落盘方案 | 本文件 |

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- completed

当前阶段（Current stage）:

- Final

已完成阶段（Completed stages）:

- Planning research and plan drafting
- Stage 1
- Stage 2
- Stage 3
- Stage 4
- Stage 5
- Stage 6

剩余阶段（Remaining stages）:

- none

下一步自动动作（Next automatic action）:

- final delivery complete

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no, unless the user explicitly requested stage-only execution or a Stop Condition is active

active-task 同步字段（active-task sync fields）:

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "current_stage": "Final",
  "remaining_stages": [],
  "next_automatic_action": "final delivery complete",
  "stop_condition": "none",
  "state_source": "execution-plan.md"
}
```

状态同步规则（State sync rules）:

- `execution-plan.md` 是唯一主契约；`.harness/active-task.json` 只作为恢复入口和摘要索引。
- 如果 `active-task.json` 和本节冲突，必须以本节为准修正 `active-task.json` 后继续。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | complete | 已完成规划、本地上下文调研和在线规范来源核验 | plan check passed | execution-plan.md | start Stage 1 |
| Stage 1 | complete | 规范发现和 standards index | plan check passed | SKILL/workflow/template/current plan | continue Stage 2 |
| Stage 2 | complete | planner 开发质量规则 | plan check passed | SKILL/workflow | continue Stage 3 |
| Stage 3 | complete | template 和 plan check | template/current plan check + AST syntax check | template + harness_plan_check.py | continue Stage 4 |
| Stage 4 | complete | executor 开发质量执行闭环 | transition check + AST syntax check | executor workflow + harness_exec_check.py | continue Stage 5 |
| Stage 5 | complete | eval 和文档 | JSONL/YAML parsed | eval fixtures + README + CHANGELOG | continue Stage 6 |
| Stage 6 | complete | 整体复查和最终验证 | full validation passed | validation evidence + ledger | final gate |

## Ledger Evidence

Ledger policy:

- append-only-after-approval

Ledger 文件（Ledger file）:

- `.harness/tasks/2026-07-08/feature/complex-coding-development-quality-gate/ledger.jsonl`

Ledger 摘要（Ledger summary）:

| 字段（Field） | 值（Value） |
| --- | --- |
| entries | 13 |
| stages_completed | Planning, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6 |
| current_stage | Final |
| last_blocking_reason | none |
| last_heartbeat | none |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | to check | none | to check | not-applicable | to check | not started |
| Stage 2 | to check | Stage 1 | to check | not-applicable | to check | not started |
| Stage 3 | to check | Stage 2 | to check | not-applicable | to check | not started |
| Stage 4 | to check | Stage 3 | to check | not-applicable | to check | not started |
| Stage 5 | to check | Stage 4 | to check | not-applicable | to check | not started |
| Stage 6 | to check | Stage 5 | to check | not-applicable | to check | not started |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | yes | yes | yes | not-applicable | not-applicable | yes | authorized | passed |
| Stage 2 | yes | yes | yes | not-applicable | not-applicable | yes | authorized | passed |
| Stage 3 | yes | yes | yes | not-applicable | not-applicable | yes | authorized | passed |
| Stage 4 | yes | yes | yes | not-applicable | not-applicable | yes | authorized | passed |
| Stage 5 | yes | yes | yes | not-applicable | not-applicable | yes | authorized | passed |
| Stage 6 | yes | yes | yes | not-applicable | not-applicable | yes | pending until git commit | passed |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证已完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 6 | yes | yes | yes | authorized | no | none | no | yes | yes | no | final delivery |

结论（Decision）:

- Stage 6 已通过，当前进入 final delivery。

规则（Rules）:

- 如果还有 pending stage，且没有停止条件，也不需要重新批准，下一动作必须是 `continue Stage N`。
- 这种情况下可以发送简短进度更新，但不能最终回复后停止。
- 进入下一阶段前必须同步 `Execution Control`、`Resume Summary` 和 `.harness/active-task.json`。

## 代码审查（Code Review）

| 阶段（Stage） | 质量维度（Quality dimension） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- | --- |
| Planning | standards / architecture | 未发现 blocking 或 major 问题 | follow-up | 实施阶段需按本计划补齐 Standards Discovery Gate 和 Development Quality Gate |
| Stage 1-3 | standards / static quality | planner 规则、模板和 plan_check 已补齐；py_compile 因 `__pycache__` 权限拒绝未作为通过证据 | minor | 使用 AST 语法解析作为不写 pyc 替代，最终阶段再复查 |
| Stage 4 | architecture / validation | executor 已加入 Development Quality Check，未改变批准范围或阶段边界 | follow-up | Stage 5/6 补 eval、文档和最终验证证据 |

## 恢复摘要（Resume Summary）

Resume Packet:

```json
{
  "task_id": "2026-07-08-feature-complex-coding-development-quality-gate",
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "current_stage": "Final",
  "remaining_stages": [],
  "next_automatic_action": "final delivery complete",
  "stop_condition": "none",
  "ledger_entries": 13,
  "last_blocking_reason": "none",
  "attestation_status": "not_checked"
}
```

- 整体目标（Overall goal）: 为 planner/executor 增加规范发现和开发质量门禁闭环。
- 执行模式（Execution mode）: run-to-completion。
- 整体任务状态（Overall status）: completed。
- 已完成阶段（Completed stages）: Planning research and plan drafting, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6。
- 当前阶段（Current stage）: Final。
- 剩余阶段（Remaining stages）: none。
- 最新 commit（Latest commit）: `5b21f0e feat(planner): 强化不确定问题调研门禁`。
- 下一步自动动作（Next automatic action）: final delivery complete。
- 当前停止条件（Current stop condition）: none。
- 状态来源（State source of truth）: execution-plan.md。
- 长期进程规则（Process manager rule）: not required。
- 未覆盖/风险（Not covered/risks）: 实施后仍需验证脚本、eval 和文档一致性。
- 不得停止说明（Do not stop note）:
  - Stage boundary is not a stop condition. Continue until all approved stages and the final delivery gate are complete, unless a Stop Condition is active.

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/2026-07-08/feature/complex-coding-development-quality-gate/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | not required | plan approved by user | not required |

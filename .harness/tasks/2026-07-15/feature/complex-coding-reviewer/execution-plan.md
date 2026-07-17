# 执行计划（Execution Plan）

## 规划摘要（Plan Summary）

- Task ID：`2026-07-15-feature-complex-coding-reviewer`
- Plan revision：`2`
- Lifecycle route：`managed`
- Plan profile：`full`
- Discovery-first：`no`
- Task contract：`plan-contract.json`
- Approval request：`implementation and staged/final commit requested; external write / elevated tool not requested`

Revision 1 已完成并提交 `STG-01`，随后在 `STG-02` 执行中发现批准的 `VAL-07` 命令与脚本真实 CLI 不一致；旧 immutable set、attestation、ledger 与 run-state 已归档到 `artifacts/amendments/revision-0001/`。Revision 2 只继承语义未变化且已完成的 `STG-01`，把 Planner 与 Executor 的 breaking contract 迁移合并为原子 `STG-02`，修正联合回归命令。当前文件是待重新批准的意图；重新批准前不继续代码、Git 写入、外部写入或提权操作。

## 问题定义（Problem）

目标（Goal）：`GOAL-01`，建立独立的 `complex-coding-reviewer`，内部严格分成 `plan-review` 与 `code-review`，并让 Planner、Executor 通过同一目标绑定的审查契约完成 approval、stage 和 final 门禁。

当前问题：

- 旧版 Planner 既生产计划又给出正式规划审查/critique 结论，独立性、目标身份和 finding 生命周期没有机器保证。
- Executor 内嵌 code review rubric，`review_recorded` 只保存摘要和 `development_quality=passed`，代码变化后旧 review 仍可能被当作有效。
- 当前 review artifact 是 Markdown，checker 只匹配 “Open blocking findings” 和 “Ready for approval” 两个关键词。
- 规划审查与代码审查的问题域、输入、时点和证据不同，不能合并成一套通用 checklist。

非目标（Non-goals）：

- 不做自动修复、自动 commit、自动创建 Codex task、模型/子代理调用或后台 reviewer 服务。
- 不接管 GitHub/GitLab PR/MR 拉取、评论、批准、合并或 issue 操作。
- 不实现 SAST/DAST、threat model、语言服务器或跨语言静态分析平台。
- 不保留旧 Markdown critique、旧 ledger review payload、v1/v2 schema 或兼容开关。
- 不把 reviewer 的安全 lens 宣称为完整安全审计。

验收标准（Acceptance）：见 `AC-01..AC-12`；核心可观察结果是 wrong/missing/stale receipt 被确定性拒绝，双 profile 有独立流程，三 skill 联合生命周期可回归。

约束（Constraints）：

- Python 3.12 标准库、跨 Windows/Linux/macOS、closed JSON、稳定错误码和 task-local evidence。
- Reviewer 只读 target；Planner/Executor 分别是计划修复和代码/ledger 写入者。
- 语义 review 由当前 Agent 按 skill 工作流完成；脚本和 CI 不执行 Codex、模型或目标代码。
- root `AGENTS.md`、当前项目模式和 skill-creator progressive disclosure 优先。

待确认项（Open uncertainties）：`none`。独立 reviewer 是否可用属于每次 review 的 provenance，不是本方案阻塞项；same-context 必须披露限制。

## 需求与验收（Requirements And Acceptance）

功能需求：

| ID | Priority | Requirement | Evidence |
| --- | --- | --- | --- |
| REQ-01 | must | 新增只含 `plan-review`、`code-review` 的 Reviewer skill | AC-01、AC-12、STG-01 |
| REQ-02 | must | 唯一 closed JSON receipt、finding、provenance 与 supersedes | AC-02、AC-08、AC-09、ART-03 |
| REQ-03 | must | plan-review 使用规划专属 lenses | AC-04、STG-02 |
| REQ-04 | must | code-review 支持 stage/final/standalone scope | AC-06、STG-02 |
| REQ-05 | must | pass 绑定 target SHA-256，目标变化 stale | AC-03、VAL-01、VAL-07 |
| REQ-06 | must | Planner 正式审查职责迁出并要求 receipt | AC-05、AC-10、STG-02 |
| REQ-07 | must | Executor 正式审查职责迁出并记录 compact receipt | AC-07、AC-10、STG-02 |
| REQ-08 | must | 三 skill 当前契约替换旧门禁且无兼容分支 | AC-05、AC-07、AC-10 |
| REQ-09 | must | 单测、eval、seeded fixtures、联合回归和三平台 CI | AC-11、AC-12、ART-07 |
| REQ-10 | must | 只读、安全、无自动 Agent/远端/Git/服务写入 | AC-08、AC-12、VAL-09 |

非功能需求：

| ID | Requirement | Validation |
| --- | --- | --- |
| NFR-01 | stdlib 且三平台 canonical digest 一致 | VAL-01、VAL-07、VAL-11 |
| NFR-02 | 越界、stale、缺证据 fail closed；原子、secret-free | VAL-01、VAL-12 |
| NFR-03 | progressive disclosure，profile 分离，单一 contract | VAL-08、VAL-09 |
| NFR-04 | 无 daemon/数据库/cache/第三方依赖，有界读取 | VAL-01 |
| NFR-05 | relevance、完整、简洁、行动性、误报控制和限制披露 | VAL-02、VAL-09 |
| NFR-06 | schema/canonicalization/validator 单一实现 | VAL-07、VAL-12 |
| NFR-07 | CI 无 secrets/network/Agent/target execution | VAL-07、VAL-11 |

验收标准：

| ID | Requirement IDs | Given / When / Then |
| --- | --- | --- |
| AC-01 | REQ-01 | 给出审查请求时，只路由到对应 profile；混合请求拆分 |
| AC-02 | REQ-02、REQ-05 | malformed/wrong-scope/unrebuildable receipt 被稳定错误拒绝 |
| AC-03 | REQ-02、REQ-05 | target 变化后旧 digest stale，完整新 attempt 才恢复 |
| AC-04 | REQ-03 | plan-review 必需 lenses 有证据，open blocking/major 不 passed |
| AC-05 | REQ-06、REQ-08 | Planner approval 拒绝 missing/wrong/stale plan receipt |
| AC-06 | REQ-04 | code-review 支持 stage-delta/final-integration/standalone scope |
| AC-07 | REQ-07、REQ-08 | Executor stage/final 分别要求当前 scope receipt |
| AC-08 | REQ-02、REQ-10 | target 不被 reviewer 修改，writer/provenance 真实 |
| AC-09 | REQ-02、REQ-03、REQ-04 | finding 可定位、可证伪、有影响/建议/confidence/status |
| AC-10 | REQ-06、REQ-07、REQ-08 | 正式 checklist 和旧 review payload 从两端移除 |
| AC-11 | REQ-09 | eval 同测 bug、clean 与 near-miss，不调用 Agent/目标代码 |
| AC-12 | REQ-01、REQ-09、REQ-10 | 文档、安装与全分支三平台 CI 反映三 skill 当前能力 |

## 调研门禁（Research Gate）

研究模式（Research mode）：`online-required`。

触发原因（Why this mode）：审查平台 stale 行为、AI critic 质量研究和设计审查实践属于可能演进的外部事实；本地职责分布则以当前源码为准。

不确定项清单（Uncertainty inventory）：

| ID | Question | Type | Online required | Resolution | Impact |
| --- | --- | --- | --- | --- | --- |
| U-01 | plan/code review 是否应共用 checklist | architecture | yes | 共用 lifecycle/receipt，不共用 profile lenses | 决定双 profile 信息架构 |
| U-02 | pass 是否必须绑定 target | external platform | yes | GitHub stale dismissal 与本地缺口共同支持 digest binding | 决定 fail-closed 状态机 |
| U-03 | AI reviewer 如何控制误报 | primary research | yes | evidence/confidence/limitations + clean/near-miss fixtures | 决定 finding 与 eval 契约 |
| U-04 | Reviewer 是否应直接修复 | local ownership + official practice | yes | reviewer 只写 report，producer/executor 修复 | 避免 target 与 writer 混乱 |
| U-05 | 是否需要服务/数据库 | local architecture | no | 不需要；文件 receipt + CLI 足够 | 降低运行和安全成本 |

搜索记录（Search log）：

| Query/source | Tool | Date | Result | Next action |
| --- | --- | --- | --- | --- |
| Google code review standard/looking-for/comments | web | 2026-07-15 | 设计、功能、复杂度、测试、证据和 nit 边界 | 形成 code-review lenses |
| Improving Design Reviews at Google | web | 2026-07-15 | 结构化、低侵入 review 可提升批准速度 | 使用轻量 receipt，不做重服务 |
| GitHub stale review dismissal | web | 2026-07-15 | code-modifying commit 可使 approval 失效 | target digest 成为硬门 |
| NIST SSDF PW.2/PW.7 | web/PDF | 2026-07-15 | 设计/代码 review 需记录和 triage findings | finding lifecycle 与 security lens |
| CriticGPT、CRScore、CodeReviewQA | web/paper | 2026-07-15 | AI review 有召回/幻觉权衡，单一参考文本不足 | seeded controls 与 evidence-grounding |
| 当前 Planner/Executor scripts/tests/evals | local shell | 2026-07-15 | 关键词 critique、布尔 reviewed stage、无 target identity | 明确迁移文件和负向 fixtures |

来源矩阵与完整结论位于 ART-01 `artifacts/research/review-systems-research.md`。外部证据观察日是 2026-07-15；该研究使用当前访问窗口，不把任何平台行为当永久不变事实。官方/一手来源优先，论文结论只在其适用限制内用于设计，不替代本地验证。

调研影响：实施必须把目标身份、review provenance、finding 状态、误报控制和 stale invalidation 做成契约；不能只新增两段 Markdown 说明。在线来源只进入批准 artifact，runtime checker 保持离线确定性。

调研结论（Research result）：`passed`。

## 依赖选型门禁（Dependency Selection Gate）

选择模式（Selection mode）：`none`。

触发检查：计划新增 Python scripts、JSON/Markdown assets、tests 和 GitHub Actions，但现有 Python 3.12 标准库足以完成路径、hash、JSON、Git subprocess 和原子文件操作；没有 package manifest、lock、base image、SDK、ORM、driver 或 Action 版本变更需求。

必要性结论（Necessity result）：`not-triggered`。不引入 jsonschema、Pydantic、数据库、daemon、LLM SDK 或 review service；closed schema 继续采用项目现有显式 Python validator 模式。

工程影响：STG-01 必须证明 stdlib-only，VAL-01/VAL-11 覆盖三平台；若实现发现必须新增依赖，立即触发 amendment 和重新选型，不能在执行中静默安装。

Dependency selection result：`not-applicable`。

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）：`online-required`。

技术栈清单：

| Type | Finding | Source | Impact |
| --- | --- | --- | --- |
| Skill | Codex SKILL.md + progressive disclosure | local skill-creator | 两 profile 分开 references，入口只路由 |
| Language | Python 3.12 stdlib | project CI + Google Python Style | closed validators、pathlib、明确异常 |
| Contract | JSON + SHA-256 + task-local refs | local task-contract/checkers | 单一 canonical receipt 和稳定 errors |
| Architecture | Planner/Reviewer/Executor pipeline | ART-03 | producer/reviewer/executor writer 分离 |
| CI | GitHub Actions three-OS | current workflow + GitHub docs | 无 secrets/network/model，证据上传 |

规范来源矩阵：

| Standard source | Type | Official/primary | Applicability | Accessed | Impact |
| --- | --- | --- | --- | --- | --- |
| local `skill-creator/SKILL.md` | project/skill | yes | 新 skill 全结构 | 2026-07-15 | progressive disclosure、forward test 边界 |
| https://google.github.io/eng-practices/review/ | code review | yes | code-review profile | 2026-07-15 | lenses、severity、reviewer qualification |
| https://research.google/pubs/improving-design-reviews-at-google/ | design review | primary | plan-review profile | 2026-07-15 | 结构化低侵入 workflow |
| https://docs.aws.amazon.com/wellarchitected/latest/framework/the-review-process.html | architecture | yes | 风险与里程碑 | 2026-07-15 | 轻量、无责、行动项 |
| https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=934124 | security | yes | 条件化 security lens | 2026-07-15 | record/triage/expert limitation |
| https://google.github.io/styleguide/pyguide.html | language | yes | Python scripts/tests | 2026-07-15 | 风格、异常、可读性 |

standards index 位于 ART-02，明确了项目规则优先级、AI critic 限制、Python path containment、closed JSON、atomic output 和 CI 安全边界。实施只引用适用章节，不下载或复制整套外部规范。

规范发现结论（Standards result）：`passed`。

## 开发质量门禁（Development Quality Gate）

质量范围：

| Dimension | Plan | Stage mapping | Validation mapping |
| --- | --- | --- | --- |
| Code standards | Python stdlib、closed object、pathlib、稳定错误码、中文新增注释 | STG-01、STG-04 | VAL-01、VAL-08 |
| Static quality | JSON/Markdown/CLI 语法、unittest、eval、diff check | STG-04..STG-06 | VAL-01..VAL-08、VAL-12 |
| Architecture boundaries | Planner 生产、Reviewer 报告、Executor 修复/写状态 | STG-01、STG-02 | VAL-07、ART-03 |
| Design pattern decision | immutable receipt + supersedes；CLI 作为稳定防腐层 | STG-01 | VAL-01、VAL-07 |
| Low coupling | 三方只交换 target/receipt，不互相复制 rubric | STG-02 | VAL-03、VAL-05、VAL-12 |
| High cohesion | profile reference 拥有领域 lenses，共享 reference 拥有 lifecycle/schema | STG-01 | VAL-08、VAL-09 |

过度设计防护：不引入服务、数据库、通用评分引擎、自动修复、远端平台适配、第三 profile 或语言静态分析器；scripts 只做确定性机械工作。review receipt 不计算总分，verdict 由 profile 规则、开放 severity 和 blocked lens 决定。

错误路径：missing/unreadable/out-of-scope target、invalid schema、fake provenance、open major、stale digest 和 wrong scope 都有稳定错误；Planner/Executor 不吞错或复制 validator。验证通过只证明契约/fixture，不冒充语义 review 绝对正确。

质量证据：ART-02 定义规范，ART-03 定义所有权和 state machine，ART-07 同时测试正向、负向、clean 与 near-miss；STG-06 再执行 reviewer `code-review` final-integration 和全量回归。

开发质量结论（Development quality result）：`passed`。

## 上下文（Context）

### 当前能力

- Planner 已有 managed/full task bundle、Research/Standards/Dependency/Development Quality gates、approval attestation 和 active pointer。
- Executor 已有 append-only ledger、reducer、reconcile、stage/validation/review/commit 事件和 final checker。
- 两者已有 deterministic tests/evals 和 Windows/Ubuntu/macOS workflow。
- skill-evaluation-lab 能做 skill 静态契约评估，明确不自动运行 Codex 或普通 code review。

### 核心缺口

- `harness_contract_artifacts.validate_review_artifact()` 读取 UTF-8 Markdown 并用 regex 判定 ready，没有 target 或 finding schema。
- `harness_state.py` 用 `reviewed_stages: set` 保存布尔结果，passed payload 只要求 `summary` 与固定字符串。
- plan 修改、代码修改、stage attempt 变化与 review validity 没有因果关系。
- 当前正式审查规则分散在 Planner、Executor、templates、tests、evals、README 和 workflow，无法独立调用。

### 设计前提

- `complex-coding-reviewer` 是独立 skill，不等于后台 Agent 或服务；同一个 Agent 可以按该 skill 工作流执行。
- formal review 与 producer self-check 不同：Planner 可保留确定性质量门，Executor 可保留实现质量应用，但 verdict 只来自 Reviewer receipt。
- independence 是 provenance 属性，不是 skill 名带来的事实；full/high-risk 优先 fresh-context，无法做到时明确降级。
- canonical JSON 是机器真相，Markdown 只从已验证 JSON 渲染，不能反向解析为 pass。

## 候选方案（Options）

### 方案 A：只新增独立文档清单

- 做法：新建 Reviewer SKILL.md，把 Planner/Executor 的列表复制进去；两端仍记录当前 review 字符串。
- 优点：修改小，实施快。
- 缺点：无法绑定 target，无法检测 stale，清单继续漂移；独立 skill 只是名称变化。
- 结论：拒绝，不能解决 AC-02、AC-03、AC-05、AC-07、AC-10。

### 方案 B：双 profile + canonical receipt + 三端门禁

- 做法：Reviewer 统一 target/receipt/finding/provenance/stale contract，profile 各自拥有 lenses；Planner/Executor 只调用和消费。
- 优点：职责清楚、可独立组合、可重放、可测 stale、能保留 review 历史，并可逐步改进语义规则。
- 缺点：需要同步修改 task contract、ledger、tests/evals 和 CI，是当前契约的 breaking change。
- 结论：采用；ART-03 给出详细状态机和 writer 边界。

### 方案 C：独立 Reviewer 服务与自动 Agent 编排

- 做法：daemon/API 保存 review queue，自动启动模型/子代理、抓取 PR 并回写评论。
- 优点：可扩展团队协作与远端自动化。
- 缺点：权限、秘密、运行时、跨平台、成本和故障面显著增加；与用户要求的 skill 工作流和既有安全边界冲突。
- 结论：拒绝，不增加服务、模型调用或远端 writer。

### 方案 D：Planner/Executor 各自强化审查

- 做法：继续在两端增加结构化 checklist 和 target hash。
- 优点：调用链表面简单。
- 缺点：两份 schema、两套 validator、两类输出持续漂移，也无法 standalone code review。
- 结论：拒绝，违反 REQ-01、NFR-06。

### Revision 2 切换路径补充

- 携带 revision 1 的旧 `STG-02`：拒绝。该 stage 未完成 required `VAL-07`，且 revision 2 已改变其 REQ/AC/VAL 与边界，不满足 completed-stage carry 规则。
- 在新 ledger 中先迁移 Planner、再单独迁移 Executor：拒绝。第一个 stage 的正式 completion 会要求在半切换状态写 review event，迫使新 reducer 回放旧 payload，或再触发一次固定 amendment。
- 保留旧 payload parser 过渡：拒绝。它扩大状态机和测试面，并直接违背用户要求的 current-only contract。
- 原子合并 Planner/Executor 迁移：采用。只携带语义未变的 `STG-01`，从 revision 2 第一条 review event 起使用唯一新 payload；失败时整个 `STG-02` 保持未完成。

## 决策（Decision）

采用方案 B，skill 名为 `complex-coding-reviewer`。对外 profile 严格为 `plan-review` 和 `code-review`；`stage-delta`、`final-integration`、`standalone` 只是 code-review scope。

Reviewer 拥有唯一 review contract、target canonicalization、receipt validator 和 renderer。Planner 拥有计划生产/修复，Executor 拥有代码实现/修复和 ledger/run-state；Reviewer 默认只写 `artifacts/reviews/**`。

每个 receipt 绑定 canonical target SHA-256、scope、provenance、lenses 和 findings。目标变化后旧 receipt stale；新 attempt 不覆盖旧文件，并通过 `supersedes_review_id` 连接。passed 要求当前 digest、零开放 blocking/major、必需 lens 全部 reviewed/not-applicable。

Planner approval 和 Executor transition/final 通过 Reviewer CLI 验证 receipt；不直接 import 私有实现，也不复制规则。reducer 保持离线纯状态转移，event writer/checker 负责 report path、digest 和 freshness 的 I/O 校验。

same-context review 可用但不得声称独立；脚本/CI 不自动运行 Codex、Agent 或模型。完整文件面和范围外见 ART-04。

Self-hosting cutover：Revision 1 已在旧 Executor ledger 下完成 `STG-01`，并因 `VAL-07` 命令漂移进入 amendment；其 immutable set 与执行历史已归档。Revision 2 只携带不变的 `STG-01`，新 ledger 以 `amendment_approved` 开始，再由单一 `STG-02` 同时切换 Planner approval、Executor event/reducer/transition/final 与 Reviewer profile contract。新 ledger 的首个 `review_recorded` 只使用新 payload，因此无需兼容或回放归档的旧 review payload，也不再预设第二次 amendment。

## 影响面矩阵（Impact Matrix）

| Surface | Changed | Current | Target | Stage | Risk |
| --- | --- | --- | --- | --- | --- |
| New skill | yes | 不存在 | 双 profile + scripts/references/tests | STG-01 | high |
| Planner workflow | yes | 自审/critique 内嵌 | producer + reviewer handoff | STG-02 | high |
| Approval artifact | yes | Markdown regex | canonical plan-review JSON + digest | STG-02 | high |
| Executor workflow | yes | 内嵌 review rubric | code-review handoff | STG-02 | high |
| Ledger payload/state | yes | summary + boolean set | validated receipt identity/scope/digest | STG-02 | high |
| Target freshness | yes | 无 | plan/stage/final stale rejection | STG-01..STG-04 | high |
| Tests/evals | yes | 两套独立 suites | 三套 + seeded + joint | STG-04 | medium |
| CI | yes | Planner/Executor | Planner/Reviewer/Executor | STG-05 | high |
| Docs/install | yes | 两 skill 关系 | 三 skill 责任边界 | STG-05 | low |
| Remote integrations | no | 各 skill 自有 | 继续组合，不由 reviewer 接管 | none | bounded |

## 实施计划（Implementation Plan）

阶段依赖、引用、授权与验证以 `plan-contract.json` 为机器真相源；每阶段先读取直接上下文，再在 allowed changes 内实现，finding 修复后重跑受影响验证和当前 target review。

### STG-01：Reviewer 骨架与唯一审查契约

目标：创建 `complex-coding-reviewer` 的渐进披露结构，冻结 target/receipt/finding/provenance/stale/supersedes 契约和确定性 CLI。

做法：

- 使用 skill-creator scaffold 与 quick validator；SKILL.md 只路由 `plan-review`/`code-review`，shared lifecycle 放 references。
- 实现 `review_target.py`、`review_validate.py`、`review_render.py`，使用 stdlib、closed JSON、canonical SHA-256、stable `REVIEW_*` errors。
- 默认不覆盖 immutable attempt；路径 containment 用 resolved path/relative-to，报告写入与 target 分离。
- 先以 unit fixtures 固化 public CLI，再让 Planner/Executor 集成，避免反向复制私有模块。

原因：审查契约是两端迁移的共同前置；先固定 state model，才能在后续原子切换中让三方只依赖同一公共契约。

位置：`skills/complex-coding-reviewer/**`、`evals/complex-coding-reviewer/**`。

参考：ART-01、ART-02、ART-03、ART-07；Google review practices、NIST SSDF、skill-creator。

阶段契约：

- Depends on：none。
- REQ/AC/NFR：REQ-01、REQ-02、REQ-05、REQ-10；AC-01、AC-02、AC-03、AC-08、AC-09；NFR-01、NFR-02、NFR-03、NFR-04、NFR-05、NFR-06、NFR-07。
- Required/optional VAL：VAL-01、VAL-02、VAL-08、VAL-09、VAL-10。
- Allowed changes：`skills/complex-coding-reviewer/**`；`evals/complex-coding-reviewer/**`。
- Forbidden changes：`target code or plan mutation by reviewer`；`automatic Codex, model, subagent, network, Git write or remote write`；`daemon, database, cache or third-party runtime dependency`；`generic third review profile`。
- Entry：`批准 attestation 有效并包含 implementation authorization`；`ART-01 至 ART-04 的 profile、ownership、schema 与 stale 决策已确认`；`当前 Planner/Executor/skill-evaluation-lab 基线通过`。
- Exit：`skill metadata 与 progressive disclosure 结构有效`；`target、receipt、finding、provenance、supersedes 和 stable errors 只有一个权威定义`；`三个确定性 CLI 不执行目标代码或 Agent，并通过安全与跨平台 fixtures`。
- Risk：high；rollback：删除未被调用方采用的新 skill 文件，不触碰 target 或 runtime state。
- Commit expected：none。

### STG-02：三 Skill review contract 原子切换

目标：在同一阶段完成规划与代码两个 profile 的领域规则，以及 Planner approval、Executor event/reducer/transition/final 对唯一 Reviewer receipt 的切换；新 revision 不产生任何旧格式 review event。

做法：

- `plan-review.md` 定义意图、证据、追踪、选项、架构、DAG、验证、授权、回滚和过度设计 lenses；plan target 包含 plan、contract 与非 review 的 required/approval-included artifacts，排除 review report 以避免自引用。
- Planner 保留 producer readiness、research、standards、dependency 与 development quality gates，删除正式审查清单和 Markdown verdict regex；approval checker 只通过 Reviewer CLI 验证当前 `plan-review` receipt。
- `code-review.md` 独立定义正确性、接口、错误路径、资源/并发、架构、复杂度、测试、文档及条件化专业 lenses；`stage-delta`、`final-integration`、`standalone` 只是 scope。
- Executor 在 execution/stage start 保存 final/stage baseline manifest，覆盖 tracked、staged/unstaged、deletion 与 untracked scope；实现、修复、验证和 ledger 写入仍由 Executor 负责。
- Amendment adoption 在任何新实现前校验归档中的 `STG-01` commit evidence 与当前 `HEAD` 都是 `b532208c052ff6e9623e881c030c03e588047bed`。以该 commit tree 而非当前工作树快照作为 revision 2 execution/STG-02 baseline，生成 task-local adopted-worktree manifest；这样 revision 1 遗留的 Planner 改动和后续 Executor 改动都进入同一 stage-delta。
- adopted-worktree manifest 将当前 `execution-plan.md`、`plan-contract.json` 作为已完成 plan-review 的 task-bundle metadata 单独标注；除此之外，所有预存 changed/untracked 路径必须命中 `STG-02.allowed_changes`。HEAD 漂移、范围外路径或无法归属的用户改动一律停止，不 reset、不静默收养。
- 用 validated receipt identity/scope/digest 替换 `development_quality=passed` 与裸 finding payload；event writer 写前验证，reducer 只处理 closed summary，transition/final 重建 target 并拒绝 stale 或 wrong scope。
- 联合回归脚本新增显式 `--include-reviewer`，并以 task-local `--work-dir`、`--output` 运行 Planner/Reviewer/Executor approval、stage、final 生命周期；不自动调用 Agent、模型、网络或目标项目代码。
- 阶段内先完成三方代码和 fixtures，再生成 revision 2 的第一个 `review_recorded`；发现失败则保持当前 stage 未完成，不写兼容 parser，也不把半切换状态当作通过。

原因：Planner 与 Executor 的公共 review contract 是 breaking change。把两个迁移放进同一 stage，可确保新 ledger 从第一条 review event 起只有新 payload，同时保留 Reviewer 骨架这一可证明完成且语义不变的前置阶段。

位置：`skills/complex-coding-reviewer/references/plan-review.md`、`skills/complex-coding-reviewer/references/code-review.md`、`skills/complex-coding-planner/**`、`skills/complex-coding-executor/**`、`evals/complex-coding-planner/**`、`evals/complex-coding-executor/**`、`evals/complex-coding-reviewer/**`。

参考：ART-03 的双 profile、ownership 与 ledger 设计；Google design/code review、AWS milestone review、GitHub stale approval、NIST PW.7。

阶段契约：

- Depends on：STG-01。
- REQ/AC/NFR：REQ-03、REQ-04、REQ-05、REQ-06、REQ-07、REQ-08、REQ-10；AC-03、AC-04、AC-05、AC-06、AC-07、AC-08、AC-09、AC-10；NFR-01、NFR-02、NFR-03、NFR-05、NFR-06、NFR-07。
- Required VAL：VAL-01、VAL-02、VAL-03、VAL-04、VAL-05、VAL-06、VAL-07；optional VAL：VAL-10。
- Allowed changes：`skills/complex-coding-reviewer/references/plan-review.md`；`skills/complex-coding-reviewer/references/code-review.md`；`skills/complex-coding-planner/**`；`skills/complex-coding-executor/**`；`evals/complex-coding-planner/**`；`evals/complex-coding-executor/**`；`evals/complex-coding-reviewer/**`。
- Forbidden changes：`duplicate plan-review checklist retained in Planner`；`Markdown keyword as canonical review verdict`；`duplicate code-review rubric retained in Executor`；`legacy development_quality review payload`；`stage-delta receipt accepted as final-integration`；`fake independent-review claim`；`compatibility parser for archived review payloads`。
- Entry：`STG-01 completed in revision 1 and is carried unchanged`；`revision 1 archive is valid and revision 2 ledger starts with amendment_approved`；`archived STG-01 commit evidence and current HEAD both resolve to b532208c052ff6e9623e881c030c03e588047bed, and every pre-existing non-task-bundle worktree path is inside STG-02 allowed scope`；`plan-bundle and Git canonical target fixtures are available`；`current Planner approval and Executor event/reducer/transition flows are understood`。
- Exit：`plan-review has profile-specific lenses and findings-first workflow`；`Planner produces/fixes plans but delegates formal review`；`approval rejects missing, wrong-profile, open-major and stale plan receipts`；`code-review supports stage-delta, final-integration and standalone scopes`；`STG-02 stage-delta is rebuilt from the carried STG-01 commit to the current worktree and includes both revision 1 Planner carryover changes and revision 2 Executor changes`；`revision 2 ledger contains only the new compact review receipt payload`；`source change invalidates old review and stage/final checkers reject stale or wrong scope`。
- Risk：high；rollback：保留 revision 1 archive 和失败证据，维持 revision 2 当前 stage 未完成；修复三方切换根因，不恢复旧关键词、旧 event 或兼容分支。
- Commit expected：stage；仅在全部 required VAL 与当前 stage-delta code-review 通过后，按 attestation 的 commit authorization 使用 `git commit -F`。

### STG-04：双 profile 评估与联合契约回归

目标：以 deterministic、seeded 和 cross-skill 证据同时验证召回边界、误报约束、stale 生命周期和调用方契约。

做法：

- Reviewer unit 覆盖 canonical hash、closed schema、path containment、provenance、finding、open counts、supersedes 和 renderer。
- plan/code fixtures 分别包含 known defect、clean target、near-miss；不用单一参考评论文本评分。
- Planner/Executor fixtures 覆盖 missing/wrong/stale receipt、修复再审、stage/final scope 和 ledger replay。
- deterministic eval 只评估静态工作流/期望，不执行 Codex、模型、网络或目标项目代码。
- 用户 fresh-context forward test 保留为 VAL-10 optional；未执行时明确限制，不伪造效果结论。

原因：AI critic 需要同时控制遗漏与幻觉，单测 schema 或只测 seeded bug 都不足以证明 review 有用。

位置：`skills/complex-coding-reviewer/tests/**`、`evals/complex-coding-reviewer/**`、`skills/complex-coding-planner/tests/**`、`evals/complex-coding-planner/**`、`skills/complex-coding-executor/tests/**`、`evals/complex-coding-executor/**`。

参考：ART-07；CriticGPT、CRScore、CodeReviewQA 的 precision/recall 与 grounded review 结论。

阶段契约：

- Depends on：STG-02。
- REQ/AC/NFR：REQ-02、REQ-03、REQ-04、REQ-05、REQ-08、REQ-09、REQ-10；AC-02、AC-03、AC-04、AC-06、AC-07、AC-08、AC-09、AC-10、AC-11；NFR-01、NFR-02、NFR-04、NFR-05、NFR-06、NFR-07。
- Required/optional VAL：VAL-01、VAL-02、VAL-03、VAL-04、VAL-05、VAL-06、VAL-07、VAL-09、VAL-10。
- Allowed changes：`skills/complex-coding-reviewer/tests/**`；`evals/complex-coding-reviewer/**`；`skills/complex-coding-planner/tests/**`；`evals/complex-coding-planner/**`；`skills/complex-coding-executor/tests/**`；`evals/complex-coding-executor/**`。
- Forbidden changes：`tests that call Codex, model API, network or target project execution`；`text-match-only semantic review scoring`；`fixtures containing only known bugs without clean or near-miss controls`；`platform skips used to hide canonicalization defects`。
- Entry：`STG-02 completed`；`new review contract frozen for current implementation`；`seeded expected claims reviewed against actual fixture behavior`。
- Exit：`Reviewer unit/eval cover both profiles, stale state, provenance and false-positive controls`；`Planner/Reviewer/Executor joint regression covers approval, stage and final lifecycle`；`all deterministic suites avoid Agent and network execution`。
- Risk：medium；rollback：保留失败 fixture，修正 contract/implementation 根因，不降低断言或跳过平台。
- Commit expected：none。

### STG-05：三 Skill CI、文档与安装面收口

目标：把三 skill 当前契约纳入全分支三平台 CI，并同步仓库入口、变更说明和静态 skill 评估。

做法：

- 将现有 workflow 更新为 Planner/Reviewer/Executor contract，依次运行三套 unit 与 deterministic eval。
- 保持 Windows/Ubuntu/macOS、所有 push/pull request branches、Python 3.12、UTF-8、禁 bytecode 和无依赖安装。
- 上传三套 eval JSON；workflow contract test 检查 suite、OS、branch 和 evidence path。
- README 新增 Reviewer 章节和目录；CHANGELOG 明确当前-only breaking review contract。
- 用 skill-evaluation-lab 做 static-only 评估；只有其静态解析确实不识别新合法结构时才最小适配。

原因：Reviewer 是 Planner/Executor 的正式门禁依赖，孤立测试不能防止三端契约或跨平台漂移。

位置：`.github/workflows/planner-executor.yml`、`README.md`、`CHANGELOG.md`、`skills/complex-coding-reviewer/**`、`skills/complex-coding-planner/tests/test_ci_contract.py`、`evals/complex-coding-executor/cross_skill_regression.py`、`skills/skill-evaluation-lab/**`。

阶段契约：

- Depends on：STG-04。
- REQ/AC/NFR：REQ-01、REQ-06、REQ-07、REQ-08、REQ-09、REQ-10；AC-05、AC-07、AC-10、AC-11、AC-12；NFR-01、NFR-03、NFR-06、NFR-07。
- Required VAL：VAL-07、VAL-08、VAL-09、VAL-11、VAL-12。
- Allowed changes：`.github/workflows/planner-executor.yml`；`README.md`；`CHANGELOG.md`；`skills/complex-coding-reviewer/**`；`skills/complex-coding-planner/tests/test_ci_contract.py`；`evals/complex-coding-executor/cross_skill_regression.py`；`skills/skill-evaluation-lab/**`。
- Forbidden changes：`workflow secrets or network-dependent tests`；`branch filters that skip ordinary branches`；`unrelated skill behavior changes`；`skill-evaluation-lab semantic code-review expansion unless required for static structure`。
- Entry：`STG-04 completed`；`all local deterministic suites pass`；`README and workflow inventory of current skills understood`。
- Exit：`all-branch three-OS workflow runs Planner, Reviewer and Executor suites`；`README/CHANGELOG describe current-only breaking contract and ownership`；`skill installation auto-discovers reviewer and static skill evaluation completes`。
- Risk：high；rollback：恢复 workflow 文件名/步骤前先确保三端契约仍有联合本地验证，不删除 Reviewer tests。
- Commit expected：none。

### STG-06：最终审查、回归与交付

目标：在当前整体 diff 上完成 final-integration code-review、全量确定性回归、文档/格式检查和授权收口。

做法：

- 运行 Reviewer、Planner、Executor unit/eval、cross-skill regression、quick_validate、skill-evaluation-lab static review 和 CI contract。
- 对当前整体 target 执行 `code-review` final-integration；修复 blocking/major 后重跑 affected validations 与 review。
- 静态确认两端不再保留 canonical review checklist、旧 critique regex 或 `development_quality` payload。
- 执行 `git diff --check`，核对 scope、无 secrets、无 Agent/network calls、无旧兼容分支。
- Revision 2 attestation 记录用户已给出的阶段/最终 commit 授权后，按 stage contract 使用 `git commit -F`；本方案不授权 push 或远端 write。

原因：跨 skill schema、state、docs 和 CI 必须在同一 final target 上闭环，stage review 不能替代集成 review。

位置：`all files approved by STG-01 through STG-05`、`task-local execution evidence`、`minimal fixes discovered by final review`。

阶段契约：

- Depends on：STG-05。
- REQ/AC/NFR：REQ-01、REQ-02、REQ-03、REQ-04、REQ-05、REQ-06、REQ-07、REQ-08、REQ-09、REQ-10；AC-01、AC-02、AC-03、AC-04、AC-05、AC-06、AC-07、AC-08、AC-09、AC-10、AC-11、AC-12；NFR-01、NFR-02、NFR-03、NFR-04、NFR-05、NFR-06、NFR-07。
- Required/optional VAL：VAL-01、VAL-02、VAL-03、VAL-04、VAL-05、VAL-06、VAL-07、VAL-08、VAL-09、VAL-10、VAL-11、VAL-12。
- Allowed changes：`all files approved by STG-01 through STG-05`；`task-local execution evidence`；`minimal fixes discovered by final review`。
- Forbidden changes：`new feature scope or third profile`；`compatibility layer for old review contracts`；`automatic remote push or external review write`；`claiming fresh-context semantic evidence when user did not run it`。
- Entry：`STG-05 completed`；`no unresolved blocking/major findings from stage reviews`；`working tree scope matches approved change map`。
- Exit：`all required local validations and final code-review receipt pass on current target`；`git diff check, docs, skill validators and cross-skill lifecycle are clean`；`commit occurs only if revision 2 attestation records authorization; otherwise delivery records no commit`。
- Risk：medium；rollback：保留失败证据并回到对应 stage 修复；发现新 scope/风险时 amendment，不在 final 偷增功能。
- Commit expected：final，但只有 attestation 明确 commit authorization 时才执行。

## 环境（Environment）

Workspace 环境来源：`.harness/environment.md`；本任务只补 task-local 事实，不修改长期环境记录。

本任务使用：

- Workspace：`D:/Item/vibe_coding/dev-skills`。
- Shell：PowerShell；实现/测试命令使用当前 `python`、`-X utf8 -B`。
- Runtime：本地当前 Python 与 CI Python 3.12；不创建虚拟环境，不安装依赖。
- Platforms：本地 Windows 确定性验证；hosted Windows/Ubuntu/macOS 由用户推送后触发，不伪造远端结果。
- Network：规划研究已完成；implementation checker/test 默认离线。新增外部事实时按 Research Drift 处理。
- Secrets：none；不得读取或写入 token、PAT、模型 key 或远端凭据。

临时覆盖：所有 execution evidence 写入本 task-dir `artifacts/validation/`；不写 `.codex/tmp`，不自动运行 Codex。

## Git 上下文（Git Context）

- Main branch：`main`。
- Working branch：`harness/feature`。
- Task type / branch action：`feature`；不切分支、不 rebase、不 sync remote。
- Sync source / occupancy evidence：active pointer 指向本任务；revision 1 run-state 为 `blocked`、`reapproval_required=true`，旧执行包已归档；未执行 fetch/pull，远端为 `origin git@github.com:Countra/dev-skills.git`。
- Worktree status：`STG-01` 已提交；工作区保留 revision 1 中已实现并审查的 Planner 迁移改动，以及当前 revision 2 规划变更。重新批准前不扩展或提交这些实现改动。
- Commit authorization：Revision 2 请求 `stage` 与 `final` commit；用户已允许阶段性提交，但必须在重新批准后写入新 attestation 才可执行。push、PR 与其它 external write 未授权。
- Branch closure：implementation 完成后由 Executor final gate 处理 pointer；不自动 push、PR 或删除分支。

同一仓库 Git 命令串行；只读使用 `--no-optional-locks`，不自动 stash、reset、rebase、checkout 或覆盖未知改动。发现用户并行变更时与其共存，若影响 target digest 则旧 review stale。

## 工具（Tooling）

| Tool | Purpose | Stage | Status | Risk | Alternative | User confirmation |
| --- | --- | --- | --- | --- | --- | --- |
| apply_patch | 分段修改 skill/docs/tests/workflow | STG-01、STG-02、STG-04..STG-06 | available | 锚点漂移 | 缩小 patch、完整重读 | implementation reapproval required |
| Python 3.12 stdlib | CLI、unit、eval、JSON/hash/path | all | available | 跨平台路径差异 | fixture + 3-OS CI | covered by approval |
| Git read commands | target identity、diff、status | STG-01、STG-02、STG-06 | available | index/worktree 变化 | explicit file manifest | read-only |
| skill-creator quick_validate | 新 skill 结构检查 | STG-01、STG-05 | available | 本机绝对路径 | repo equivalent validator | read-only execution |
| skill-evaluation-lab | static-only skill 评估 | STG-05、STG-06 | available | 不能证明 code review 语义 | seeded/manual observations | no Agent calls |
| GitHub Actions | 三平台 contract CI | post-push | repository workflow | external run | user pushes and reports | external write not authorized here |
| Web research | 变化事实补证据 | only on Research Drift | available with policy | stale/二手来源 | official docs/local evidence | no external write |

## 长期进程管理（Process Manager Gate）

- Needs long-running process：`no`。
- 原因：所有 CLI、unit、eval、render、checker 和 workflow syntax validation 都是 finite commands。
- Manager bootstrap：`not-applicable`；不启动 dev server、worker、watcher、daemon 或模型服务。
- Evidence：VAL-01..VAL-12 的有限命令/工具输出；没有 processKey/readiness/cleanup contract。
- Fallback/blocker：若实现提出后台 review 服务，视为 scope 与 dependency 变化，触发 amendment，不用手写后台 shell 绕过。

## 验证（Validation）

| VAL ID | Required | Kind / command / tool | Covers | Evidence path | Failure handling |
| --- | --- | --- | --- | --- | --- |
| VAL-01 | yes | Reviewer unittest | AC-02/03/08/09、NFR-01/02/04/06/07 | `artifacts/validation/reviewer-unit-tests.txt` | 修 contract/implementation，重跑 |
| VAL-02 | yes | Reviewer deterministic eval | AC-01/04/06/09/11、NFR-03/05/07 | `artifacts/validation/reviewer-evals.json` | 保留失败 case，修 workflow |
| VAL-03 | yes | Planner unittest | AC-04/05/10、NFR-02/06 | `artifacts/validation/planner-unit-tests.txt` | 修 approval integration |
| VAL-04 | yes | Planner eval | AC-04/05/08/10、NFR-03/05/07 | `artifacts/validation/planner-evals.json` | 修 handoff/provenance 行为 |
| VAL-05 | yes | Executor unittest | AC-03/06/07/10、NFR-01/02/06 | `artifacts/validation/executor-unit-tests.txt` | 修 state/event/checker |
| VAL-06 | yes | Executor eval | AC-06/07/08/10、NFR-03/05/07 | `artifacts/validation/executor-evals.json` | 修 execution workflow |
| VAL-07 | yes | 三 skill joint regression，使用 contract 中带 task-local `--work-dir`、`--output` 与 `--include-reviewer` 的精确命令 | AC-02/03/05/07/10/12、NFR-01/02/06/07 | `artifacts/validation/cross-skill-regression.json` | CLI 不匹配即失败并进入 amendment，不接受 mock-only bypass |
| VAL-08 | yes | skill quick_validate | AC-01/12、NFR-03 | `artifacts/validation/reviewer-skill-validation.txt` | 修 metadata/refs/structure |
| VAL-09 | yes | skill-evaluation-lab static + current Agent review | AC-01/08/11/12、NFR-03/05/07 | `artifacts/validation/reviewer-skill-evaluation.md` | 只修真实静态/语义缺口 |
| VAL-10 | no | 用户 fresh-task forward test | AC-04/06/09/11、NFR-05 | `artifacts/validation/user-forward-test.md` | 未执行则披露限制 |
| VAL-11 | yes | all-branch 3-OS CI contract | AC-11/12、NFR-01/07 | `artifacts/validation/ci-contract.txt` | 修根因后由用户重推 |
| VAL-12 | yes | diff/static legacy removal check | AC-08/10/12、NFR-02/06/07 | `artifacts/validation/final-static-checks.txt` | 修残留或 scope drift |

规划阶段研究和 checker 输出不能冒充 implementation 验证。VAL-10 optional 不阻断本地交付，但没有用户 fresh-context 观察时最终结论必须明确“语义效果尚未独立观察”。

## 文档（Documentation）

必需更新：

- `README.md` 新增 `complex-coding-reviewer`，解释两个 profile、目标绑定、只读边界和 Planner/Executor 调用点。
- `README.md` Repository Layout 和 CI 说明加入 Reviewer。
- `CHANGELOG.md` 记录正式审查职责迁移、receipt/stale 门禁和旧 review contract 被替换。
- 三个 SKILL.md/references 同步当前责任，避免 README 与实际 workflow 漂移。
- eval README/manifest 说明 deterministic-only、seeded controls 和 fresh-context limitation。

不新增 skill 内 README/CHANGELOG；profile 细节放 references，模板/脚本具备自解释 `--help`。

## 文件写入策略（File Write Strategy）

| File / group | Segmented | Semantic boundaries | Whole-file check |
| --- | --- | --- | --- |
| Reviewer SKILL/references | yes | router、shared workflow、两个 profile、contract | frontmatter、links、line budget |
| Reviewer Python scripts | yes | target、contract validator、renderer | AST/unit/CLI help/UTF-8 |
| Planner/Executor large refs | yes | formal review sections 定点迁移 | 搜索旧 rubric + full reread |
| task contract/checkers | yes | schema、artifact、event、freshness | JSON fixtures + joint regression |
| tests/evals | yes | unit、profile、negative、clean/near-miss | case inventory 与 expected IDs |
| workflow/docs | no for small files | complete YAML/section patches | syntax、branch/OS/suite/artifact |

长文件按完整章节、函数或 fixture 分段 patch，单次新增建议不超过 120 行、最多 200 行。任何 patch 失败先检查部分写入；结束后完整重读、解析 JSON/YAML、核对 ID/引用/末尾换行并运行 `git diff --check`。

## 问题和覆盖项（Questions And Overrides）

| ID | Blocking | Status | Question | Decision | Applied to |
| --- | --- | --- | --- | --- | --- |
| Q-01 | no | closed | 新 skill 名称 | `complex-coding-reviewer`，与现有 complex-coding 系列一致 | REQ-01、STG-01 |
| Q-02 | no | closed | 两类审查是否共享 checklist | 只共享 lifecycle/receipt，profile lenses 完全分开 | ART-03 |
| Q-03 | no | closed | 是否自动创建 fresh Agent | 不自动；provenance 真实记录，用户可手动 fresh task | REQ-10、VAL-10 |
| Q-04 | no | closed | 是否兼容旧 review artifact/event | 不兼容，直接替换当前契约 | REQ-08、AC-10 |
| Q-05 | no | closed | 是否允许提交 | 用户允许阶段性提交；revision 2 attestation 记录后按 `stage`/`final` contract 执行，不 push | STG-02、STG-06 |

## 方案质量门禁（Plan Quality Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| 关键判断有证据等级 | passed | ART-01 区分 local/official/primary/research limitation |
| Research Gate 完成 | passed | 2026-07-15 官方/一手来源与窗口记录 |
| Standards Discovery 完成 | passed | ART-02 的 skill/Python/review/security/CI index |
| Development Quality 完成 | passed | ART-03 ownership/state，ART-07 validation layers |
| Dependency Selection 完成 | passed | none；stdlib 可完成，新增依赖触发 amendment |
| Impact matrix 完整 | passed | ART-04 精确到 skill/script/test/eval/workflow/docs |
| Options 充分比较 | passed | A 文档搬迁、B contract pipeline、C service、D 两端强化 |
| Stages 可独立验证 | passed | STG-01、STG-02、STG-04、STG-05、STG-06 与 VAL-01..VAL-12 映射 |
| Reapproval triggers 清楚 | passed | schema/profile/writer/dependency/Agent/external scope 变化均列出 |
| Approval summary ready | passed | implementation 与 stage/final commit 请求重新批准；external/elevated 未请求 |

质量决策：方案 B 是能同时满足职责分离、独立组合、target freshness 和可测试性的最小完整方案。服务化与自动 Agent 被排除，避免不必要权限与运行面；单纯搬文档被排除，因为不能修复本地机器契约缺口。

证据锚点：ART-01、ART-03、ART-04、ART-05、ART-07；机器一致性由 draft/approval `harness_plan_check.py` 验证，不能由本表自我声明替代。

质量结论（Quality result）：`passed`。

## 正式方案审查（Formal Plan Review）

- Producer：`complex-coding-planner` 负责生成和修复 plan bundle，不生成正式 verdict。
- Profile：`plan-review`。
- Scope：`managed-plan`。
- Current receipt：`artifacts/reviews/plan-review-attempt-1.json`。
- Validator：`complex-coding-reviewer/scripts/review_validate.py`。
- Canonical result：只读取上述 JSON receipt；计划正文不复制 verdict 或 finding 状态。
- Retry：修复目标后保留旧文件，把 contract 指向递增 attempt，并通过 `supersedes_review_id` 连接前序 receipt。
- Provenance boundary：本轮由当前上下文执行审查，receipt 必须如实记录 `same-context` 与非独立限制；不得冒充 fresh/external/human reviewer。

## 生产者就绪门禁（Producer Readiness Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| Goal/acceptance 清楚 | passed | GOAL-01、REQ-01..REQ-10、AC-01..AC-12 |
| Context collected | passed | current scripts/tests/evals/workflow 与 ART-04 |
| Research Gate passed | passed | ART-01，online-required 无 unresolved |
| Standards Gate passed | passed | ART-02 |
| Development Quality passed | passed | ART-03、ART-07 |
| Dependency Gate passed | passed | mode none/not-triggered |
| Options/decision recorded | passed | 方案 A..D，采用 B |
| Stages detailed | passed | 五 stage DAG、scope、entry/exit/rollback；revision 2 只携带 STG-01 |
| Environment/Git/tooling confirmed | passed | Windows local、3-OS hosted、blocked revision 1、无 secrets |
| Validations confirmed | passed | 11 required + 1 optional，ART-07 |
| Documentation confirmed | passed | README/CHANGELOG/skills/eval docs |
| Final evidence planned | passed | final-integration review + all suites + diff check |
| Formal review handoff ready | passed | profile、scope、receipt path、validator 与 provenance boundary 已固定 |
| Blocking questions closed | passed | research unresolved empty，Q-01..Q-05 closed |

就绪结论的依据是 producer 证据、追踪和 draft checker，只表示计划已可交给 Reviewer，不包含正式审查 verdict，也不表示 revision 2 implementation 已获授权。active pointer 当前指向 revision 1 的 blocked state；只有当前 receipt 与 approval checker 有效、用户重新批准后，才允许生成 revision 2 attestation 并激活 amendment。

Readiness result：`ready_for_review`。

## 方案批准（Plan Approval）

- Status：`awaiting-user-reapproval`。
- 请求授权：revision 2 implementation，以及 `STG-02` 阶段提交和 `STG-06` 最终提交。
- 未请求授权：external write、elevated tool、push、PR。
- Carry-forward：只携带 revision 1 已完成且定义未改变的 `STG-01`；revision 1 的未完成 `STG-02` 不携带完成状态，其已有源码改动作为新 `STG-02` 的待验证输入。
- 批准后 immutable set：`execution-plan.md`、`plan-contract.json` 与 ART-01..ART-07。
- 批准摘要建议：基于已完成的 Reviewer 骨架，原子迁移 Planner/Executor 到目标绑定 receipt，修正并实现带 `--work-dir`、`--output`、`--include-reviewer` 的三 Skill 联合回归，完成双 profile eval、三平台 workflow 与文档；允许阶段/最终 `git commit -F`，不 push、不外部写入、不提权。
- 当前规划阶段停止点：ART-06 与 approval checker 通过后立即停止，等待用户对 revision 2 的明确批准；批准前不得创建新 attestation、轮换 ledger/run-state 或继续实现。

## 方案变更门禁（Plan Amendment Gate）

已发生的变更：revision 1 在 `STG-02` 执行 `VAL-07` 时发现批准命令缺少 runner 必需的 `--work-dir`，且原 stage mapping 要求在 Executor contract 尚未迁移时证明三 Skill 生命周期，无法按批准契约真实通过。Executor 已记录 validation failure 与 `amendment_requested`，并将 revision 1 归档到 `artifacts/amendments/revision-0001/`。Revision 2 通过原子合并 Planner/Executor 迁移与修正 VAL-07 解决根因，不保留旧 payload parser，也不预设后续固定 amendment。

以下变化要求停止、记录 amendment、递增 `plan_revision` 并重新批准：

- 新增第三 profile，改变 plan/code profile 边界，或让 Reviewer 修改 target/ledger/Git/remote state。
- receipt、target canonicalization、severity/verdict、stale、supersedes 或 provenance 语义实质改变。
- Planner approval、Executor stage/final、ledger payload、stage DAG、required VAL 或 approved file scope 改变。
- 引入 dependency、服务、数据库、模型/Agent 调用、secret、网络执行、external write 或 elevated tool。
- 实现需要旧契约 compatibility layer、v1/v2 分支或 change map 外其它 skill 行为变化。

不触发 amendment：修正文案、稳定错误提示、fixture expected detail、task-local execution evidence，前提是不改变公共行为、scope、风险或 required validation。

## Artifact Index

| ART | Kind | Path | Required | Approval included | Purpose |
| --- | --- | --- | --- | --- | --- |
| ART-01 | research | `artifacts/research/review-systems-research.md` | yes | yes | 本地缺口与外部研究 |
| ART-02 | standards | `artifacts/standards/review-standards-index.md` | yes | yes | Skill/Python/review/security/AI/CI 规范 |
| ART-03 | architecture | `artifacts/architecture/reviewer-contract-design.md` | yes | yes | 双 profile、receipt、state、ownership |
| ART-04 | architecture | `artifacts/architecture/change-map.md` | yes | yes | 精确文件面与调用链 |
| ART-05 | other | `artifacts/traceability/traceability-matrix.md` | yes | yes | REQ/AC/NFR/STG/VAL 闭环 |
| ART-06 | review | `artifacts/reviews/plan-review-attempt-1.json` | yes | yes | revision 2 当前计划的 canonical plan-review receipt |
| ART-07 | validation | `artifacts/validation/validation-strategy.md` | yes | yes | 分层测试、eval、CI 和 manual 边界 |

## Executor Handoff

用户明确批准 revision 2 后，Executor 应按以下顺序接管：

1. 读取 `.harness/active-task.json` 与 revision 1 archive，确认 task ID、task-dir、blocked/reapproval 状态、archive hash 和唯一可携带 stage `STG-01` 一致；核对归档 commit evidence 与当前 `HEAD` 都为 `b532208c052ff6e9623e881c030c03e588047bed`。
2. 使用用户实际授权生成 revision 2 attestation：implementation 与 commit 为 true，external write 与 elevated tool 为 false。
3. 运行 amendment activation helper，携带 `STG-01`，轮换当前 ledger/run-state；新 ledger 首条必须是 `amendment_approved`，记录前一 archive/hash 与 carried stage。
4. 在继续实现前运行 adopted-worktree preflight：以 carried commit tree 为 execution/STG-02 baseline，记录当前 overlay 的 path/hash/role；精确排除已 plan-reviewed 的本 task bundle metadata，其余预存路径必须属于 `STG-02.allowed_changes`。随后确认 revision 2 immutable hashes、attestation、pointer、ledger replay 与 run-state 一致；不从旧工作区改动推断 stage 已完成。
5. 执行原子 `STG-02`：补齐 Planner 迁移，实施 Executor 与 `code-review` 迁移，并让联合 runner 支持批准的精确 `VAL-07` 命令；revision 2 只写新 compact review payload。
6. `STG-02` 全部 required VAL、stage-delta review 与范围检查通过后，使用 `git commit -F` 完成阶段提交并记录真实 commit evidence；任一项失败则保持 stage 未完成。
7. 按 DAG 执行 `STG-04`、`STG-05`、`STG-06`；finding 修复后重算 target、重跑受影响 VAL、生成递增 review attempt，不能复用旧 pass。
8. `STG-06` 对整体 diff 做 final-integration code-review，并运行 VAL-01..VAL-09、VAL-11、VAL-12；VAL-10 仅在用户显式 fresh task 操作时记录。
9. final gate 通过后按 attestation 使用 `git commit -F` 完成最终提交并记录真实 commit evidence；不得 push、建 PR 或执行其它远端写入。
10. 所有 required evidence、final checker 和 pointer closure 完成后才交付；远端三平台 CI 由用户推送后验证，未运行时明确说明。

恢复时只信任 attestation、ledger replay 和 run-state，不从本计划推断 current stage。出现 review contract、scope、依赖、Agent、外部写入或授权漂移时进入 amendment，不继续实施。

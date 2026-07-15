# 执行计划（Execution Plan）

## 规划摘要（Plan Summary）

- Task ID：`2026-07-15-feature-planner-dependency-trust-gate`
- Plan revision：`1`
- Lifecycle route：`managed`
- Plan profile：`full`
- Discovery-first：`no`
- Task contract：`plan-contract.json`
- Approval request：`implementation + stage commits approved`
- Dependency selection for this task：`none`，仅修改 Markdown、JSON、YAML 和 Python 标准库实现

本文件只保存批准意图。批准后不得写入 current stage、progress、运行结果、ledger 摘要或 commit 状态；执行事实由 `attestation.json`、`run-state.json` 和 `ledger.jsonl` 保存。

## 问题定义（Problem）

目标（Goal）：`GOAL-01`

当前 Planner 会要求调研外部依赖和规范，却没有把“稳定版本、采用规模、更新时间、维护活跃度、采用趋势”变成正式决策门。只要找到官方页面、列出两个候选并写出 URL，现有 checker 就可能接受“能用”的库；Executor 也没有机器可读的批准依赖身份、版本策略和证据新鲜度可以执行。

非目标（Non-goals）:

- 不维护 Gin、GORM、React 或其它包的永久推荐榜单。
- 不把 stars、下载量、OpenSSF 总分或任一单项指标当作自动赢家。
- 不实现在线包推荐服务、后台爬虫、包安装器或自动升级器。
- 不因新候选更热门就迁移已有 Echo、Chi、SQL 或其它有效项目栈。
- 不重构 Executor 的 ledger、attestation、task lock 等与依赖决策无关的能力。
- 不在本规划阶段修改 Skill 实现、运行外部写操作或创建提交。

验收标准（Acceptance）:

- 依赖变更先经过必要性、项目适配、硬门槛、可信度比较、新鲜度和例外门。
- Planner 产出机器契约与人类可审计的候选矩阵，checker 能拒绝空门禁与缺证据结论。
- Executor 只能落实批准的包、版本策略和 manifest 范围，事实变化进入 Research Drift。
- 无依赖变更和 direct 任务不被完整选型流程拖累。
- Planner 与 Executor 的单测、评估、自举检查和三平台 CI 定义闭环。

约束（Constraints）:

- 遵循当前 `complex-coding-planner` 与 `complex-coding-executor` 的 managed/full、不可变计划和显式批准协议。
- 继续使用 Python 3.11+ 标准库，不为门禁本身增加第三方运行时依赖。
- 所有可变外部事实带来源、观察日期、指标窗口和局限，不能将规划日快照描述为长期事实。
- checker 只验证结构、证据完整性和内部一致性，不伪装成能离线判断真实流行度。

待确认项（Open uncertainties）:

- 无阻塞项。阈值、趋势缺失、专用例外、自举和活动指针策略均已在 ART-03 中形成明确决策。

## 需求与验收（Requirements And Acceptance）

功能需求：

| ID | Priority | Requirement | Evidence |
| --- | --- | --- | --- |
| REQ-01 | must | 必要性门和用户策略、现有栈、标准库或官方 SDK、生态主流、专用例外的选择顺序 | AC-01/02/04；ART-03 |
| REQ-02 | must | 稳定版本、规模、更新时间、维护、趋势与供应链证据 | AC-02/03/04；ART-01/02 |
| REQ-03 | must | 契约、模板、附件和 checker 的受控依赖决策 | AC-04/05/08；ART-03/04 |
| REQ-04 | must | 空门禁、伪完成和 active pointer 冲突 fail closed | AC-05/07；ART-03/05 |
| REQ-05 | must | Executor 执行批准依赖并闭合 Research Drift | AC-06/08；ART-03/05 |
| REQ-06 | must | 单测、eval、CI 和公共文档覆盖行为边界 | AC-08/09；ART-05/07 |

非功能需求：

| ID | Requirement | Validation |
| --- | --- | --- |
| NFR-01 | 多信号、按生态和类别解释，禁止单指标赢家 | VAL-01/02/07 |
| NFR-02 | 关键、普通、开发依赖分别采用 30/60/90 天证据年龄上限 | VAL-01/03/05/07 |
| NFR-03 | 真实性、兼容性、许可、支持和高危漏洞是硬门槛 | VAL-01/03/04/07 |
| NFR-04 | 趋势无可靠数据时披露 `insufficient-data` 并交叉验证 | VAL-01/02/05/07 |
| NFR-05 | direct 和 none 路径保持渐进披露 | VAL-01/02/03/04/05 |
| NFR-06 | Python 标准库、跨平台、无后台服务、高内聚 | VAL-01/03/06/08 |
| NFR-07 | 计划、契约、附件、执行和文档术语一致 | VAL-01..07 |

验收标准：

| ID | Requirement IDs | Given / When / Then |
| --- | --- | --- |
| AC-01 | REQ-01 | Given 无依赖变化，When 规划，Then 可用 none 轻量通过；有变化则必须先证明必要性 |
| AC-02 | REQ-01/02 | Given 需要选型，When 比较，Then 纳入现有方案与二至四个领先候选，并遵守项目优先级 |
| AC-03 | REQ-02 | Given 正式候选，When 评估，Then 九类信号均有结果、来源、日期、窗口和局限 |
| AC-04 | REQ-01/02/03 | Given 非主流方案，When 入选，Then 主流基线无法满足、风险、缓解、回滚和批准均明确 |
| AC-05 | REQ-03/04 | Given 缺失、陈旧、空门禁或漂移，When approval check，Then 返回稳定失败码 |
| AC-06 | REQ-05 | Given 批准决策，When 实施，Then 包、版本、manifest 与事实新鲜度一致，否则停止并漂移 |
| AC-07 | REQ-04 | Given active pointer 四种状态，When 写入，Then 使用确定且默认拒绝冲突的策略 |
| AC-08 | REQ-03/04/05/06 | Given 改造完成，When 全验证，Then Planner/Executor 本地门禁和 CI 定义通过 |
| AC-09 | REQ-06 | Given Go 示例，When 阅读，Then 理解 Gin/GORM 是当前主流基线示例而非永久默认 |

## 调研门禁（Research Gate）

研究模式（Research mode）：`online-required`

触发原因（Why this mode）:

- 包版本、依赖者数量、维护状态、漏洞和采用趋势都会变化，不能依靠模型记忆。
- 用户明确要求深入调研主流性、稳定性、更新时间、维护活跃度和趋势。
- 本任务改变 Planner 与 Executor 的公共决策协议，属于高影响跨 Skill 设计。

不确定项清单（Uncertainty inventory）:

| ID | Question | Type | Online required | Resolution | Impact |
| --- | --- | --- | --- | --- | --- |
| U-01 | “主流可信”应由哪些信号构成 | external-tool | yes | OpenSSF、CHAOSS、Go 调查和生态注册表交叉形成硬门槛与比较信号 | REQ-02 |
| U-02 | 是否直接规定 Gin/GORM | user-decision | yes | 否；只作为当前 Go 工程化基线示例，项目适配优先 | REQ-01/NFR-01 |
| U-03 | 维护和证据多旧算过期 | high-risk | yes | 维护基线看近 12 个月；批准证据按依赖风险使用 30/60/90 天 | NFR-02/03 |
| U-04 | 没有历史下载量时如何判断趋势 | external-service | yes | 结果必须记录，可为 insufficient-data；用多个代理信号交叉验证并降低置信度 | NFR-04 |
| U-05 | Scorecard 是否能直接决定 | external-tool | yes | 否；只消费单项 probes，聚合分数是辅助证据 | NFR-01 |
| U-06 | 现有 checker 是否能验证语义 | local-code | no | 不能；目前只查 URL、标题数和英文未完成标记 | REQ-03/04 |
| U-07 | active pointer 是否有冲突策略 | local-code | no | 入口文档未定义完整四态切换，纳入本次补强 | REQ-04 |

搜索记录（Search log）:

| Query/source | Tool | Date | Result | Next action |
| --- | --- | --- | --- | --- |
| OpenSSF evaluating OSS | web search/open | 2026-07-15 | 必要性、真实性、近 12 月活动与发布、稳定版本、安全、采用和适配性 | 形成硬门槛与证据底线 |
| Go 2025 Developer Survey | web search/find | 2026-07-15 | 5,379 人；26% 把可信模块发现列为痛点，点名稳定版本、用户数、更新时间和趋势 | 证明问题真实且指标贴近开发者需求 |
| deps.dev API v3 | web search/find | 2026-07-15 | 提供 publishedAt、deprecated、license、direct advisories、Scorecard、依赖图和 provenance | 定义首选聚合证据源与局限 |
| CHAOSS project health | web search/open | 2026-07-15 | release frequency、响应时间、closure ratio、contributor absence factor，强调机器人和项目类型偏差 | 设计趋势窗口与解释规则 |
| pkg.go.dev Gin/GORM/Echo/Chi/Fiber | web open | 2026-07-15 | 可观察版本、发布日期、许可、stable 与 imported-by；不同 major 会拆分统计 | 用于 Go 示例并记录指标口径风险 |
| OpenSSF Scorecard checks | web search/open | 2026-07-15 | Maintained、review、CI、contributors、signed release 等是启发式且有误报漏报 | 禁止总分自动决策 |
| GitHub dependency graph/review | web search/open | 2026-07-15 | public dependents、版本年龄、许可和漏洞可辅助审查，但不包含私有采用 | 记录采用规模来源限制 |
| NIST SSDF SP 800-218 | web search/open | 2026-07-15 | 要求在 SDLC 中验证第三方组件并管理软件供应链风险 | 高风险依赖的规范依据 |

调研结论（Research result）：`passed`。完整来源矩阵、数值快照、证据限制和设计影响见 ART-01。

## 依赖选型门禁（Dependency Selection Gate）

本任务模式：`none`。本次实现只使用仓库现有 Python 标准库和 GitHub Actions，不新增、替换或升级第三方包；因此不为本任务虚构 DEP 决策。新版 Planner 的目标流程如下：

1. **Trigger**：识别 `none`、`retain`、`add`、`upgrade`、`replace`；direct 与 none 到此结束。
2. **Necessity**：确认现有组件、标准库或官方 SDK 是否已足够，避免无价值依赖和自造复杂实现两种极端。
3. **Priority**：用户或组织政策 > 现有项目栈 > 标准库或官方 SDK > 生态主流成熟方案 > 有理由的专用例外。
4. **Hard gates**：真实性、项目兼容、受支持稳定版本、非归档或弃用、许可可用、无未缓解适用高危漏洞。
5. **Comparative signals**：采用规模、采用趋势、发布与提交新鲜度、维护响应、维护者韧性、API 稳定性、文档与集成、传递依赖和 provenance。
6. **Decision**：选择 `project-standard`、`official-standard`、`ecosystem-mainstream` 或 `specialized-exception`，记录版本策略、manifest 路径、风险、回滚和验证。
7. **Freshness**：关键运行时或认证、加密、数据依赖 30 天；普通框架、ORM、SDK、驱动 60 天；开发测试构建依赖 90 天。超期由 Executor 在线复核。

正式证据底线：官方仓库或文档与 release/support 信息、生态注册表或 dependents 指标、维护历史、安全或 advisory 与许可来源、趋势结果。趋势无法可靠取得时必须写 `insufficient-data`，说明时间窗口和至少两个代理证据；不得省略或猜测。

硬门槛失败不能靠高热度抵消。专用例外必须保留一个主流基线作为比较对象，并说明未满足需求、风险、缓解、回滚和是否需要用户显式接受。ART-03 定义未来 `DEP-*` 契约与 checker 语义。

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）：`online-required`

技术栈清单（Technology inventory）:

| Type | Finding | Source | Impact |
| --- | --- | --- | --- |
| 语言 | Python 3.11+ 标准库、Markdown、JSON、YAML | 当前源码与 environment | validator 不新增包 |
| 框架 | 无运行时框架 | 当前源码 | 保持 CLI 与纯函数模块 |
| API/架构 | immutable plan contract、approval checker、Executor preflight/drift | Planner/Executor references | 依赖决策跨规划和执行交接 |
| 工具链 | unittest、确定性 eval、GitHub Actions 三平台 | tests/evals/workflows | 必须同步验证与 CI |
| 数据 | closed JSON contract、Markdown planning artifacts、active pointer | task-contract/scripts | 新字段需闭合校验和指针策略 |

规范来源矩阵（Standards source matrix）:

| Standard source | Type | Official/primary | Applicability | Accessed | Impact |
| --- | --- | --- | --- | --- | --- |
| 仓库根 `AGENTS.md` | project | yes | 所有修改、验证和 Git | 2026-07-15 | 中文注释、最小修改、真实验证、提交需授权 |
| Planner workflow/task contract | project | yes | managed/full 规划 | 2026-07-15 | 不可变计划、稳定 ID、artifact 和 approval |
| Executor workflow | project | yes | 实施、漂移和验证 | 2026-07-15 | 只执行批准契约，偏离走 amendment |
| OpenSSF Concise Guide | security/architecture | yes | OSS 候选评估 | 2026-07-15 | 必要性、真实性、维护、稳定、安全与采用 |
| OpenSSF Scorecard checks | security/tool | yes | 自动化安全信号 | 2026-07-15 | 使用单项 probe，不使用总分决定 |
| deps.dev API v3 | package/security | yes | Go/npm/Maven/PyPI/Cargo/NuGet/RubyGems | 2026-07-15 | 版本、弃用、许可、advisory、图和 provenance |
| OSV | security | yes | 已知漏洞查询 | 2026-07-15 | 版本级 advisory 证据 |
| CHAOSS health/viability | architecture/other | yes | 维护、韧性与趋势 | 2026-07-15 | 时间窗口、响应与 contributor risk |
| NIST SP 800-218 | security | yes | 高风险第三方组件 | 2026-07-15 | 将第三方验证纳入 SDLC |
| pkg.go.dev 与 Go module docs | language/package | yes | Go 示例 | 2026-07-15 | stable/tagged/imported-by 与版本语义 |

standards index:

- 路径：`artifacts/standards/standards-index.md`
- 摘要：来源优先级、适用边界、硬要求、辅助信号和禁止误用均已索引。
- 未覆盖：商业 SLA、组织内部 allowlist 和法律许可判断必须由具体任务提供，Planner 不替代组织审批或法律意见。

规范发现结论（Standards result）：`passed`。

## 开发质量门禁（Development Quality Gate）

质量范围（Quality scope）:

| Dimension | Plan | Stage mapping | Validation mapping |
| --- | --- | --- | --- |
| 代码标准 | 现有 Python 风格、中文设计注释、closed JSON、稳定诊断 | STG-02..05 | VAL-01/03/06 |
| 静态质量 | JSON/JSONL 解析、AST、YAML contract、diff whitespace | STG-05..07 | VAL-01/03/06 |
| 架构边界 | policy/reference、contract validator、plan checker、pointer、executor enforcement 分层 | STG-01..04 | VAL-01..05/07 |
| 模式取舍 | Policy + Value Object + Gate；不引入 registry service 或评分引擎 | STG-01..04 | VAL-01/02/07 |
| 低耦合 | 证据采集由 agent/workflow 完成，deterministic checker 不联网；Executor 只消费契约 | STG-02..04 | VAL-01/03/04 |
| 高内聚 | 新依赖校验放独立模块，pointer 切换单一职责，SKILL 保持入口简洁 | STG-01..04 | VAL-01/03/07 |

过度设计防护（Overengineering guard）:

- 不构建跨生态统一排名公式；只定义证据字段、硬门槛和解释规则。
- 不要求每个普通 import 做完整研究；只对 add、replace、upgrade 或高风险 retain 触发。
- 不让 checker 在线抓取数据；它检查 receipt 完整性，在线事实由 Planner 调研、Executor 复核。
- 不引入 schema 版本分支；新增字段为条件化当前契约，模板直接采用最新格式。
- 不把 active pointer 修复扩展为通用任务调度器。

开发质量结论（Development quality result）：`passed`。

## 上下文（Context）

本地代码（Local code）:

- `skills/complex-coding-planner/SKILL.md` 已有 Research、Standards、Development Quality gate，但没有 Dependency Selection Gate。
- `planning-workflow.md` 的研究停止条件是“新来源不再改变方案”，没有依赖证据最低集合和新鲜度。
- `task-contract.md` 与 `plan-contract.json` 没有 `DEP-*` 或机器可读依赖决策。
- `harness_plan_check.py` 目前只确认存在 URL、候选标题数量和门禁中无英文未完成标记；语义上可被空内容绕过。
- Executor 只有笼统的 dependency drift，没有批准包、版本策略、manifest 和 evidence receipt 可核对。
- skill-evaluation-lab 对 Planner 的既有评估指出 active pointer 冲突规则、语义 gate 强度和独立 CI 可发现性不足。

本地文档（Local docs）:

- Planner/Executor SKILL、workflow、task contract、templates、tests、evals、README、CHANGELOG、现有 full task bundles。
- `.harness/environment.md` 的稳定工具与分支信息可复用；其中旧任务状态不作为本计划事实源。

外部来源（External sources）:

- [OpenSSF OSS 评估指南](https://best.openssf.org/Concise-Guide-for-Evaluating-Open-Source-Software.html)
- [2025 Go Developer Survey](https://go.dev/blog/survey2025)
- [deps.dev API v3](https://docs.deps.dev/api/v3/)
- [OpenSSF Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
- [CHAOSS Starter Project Health](https://chaoss.community/kb/metrics-model-starter-project-health/)
- [GitHub dependency graph](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependency-graph)
- [NIST SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final)
- [Go security best practices](https://go.dev/doc/security/best-practices)

用户约束（User constraints）:

- 主流方案优先，并正式关注稳定版本、用户规模、更新时间、维护活跃度和采用趋势。
- 深入排查其它 Planner 缺口，一并纳入方案。
- 当前只落盘方案，实施必须另行批准。

证据等级（Evidence levels）:

| Claim | Level | Source | Impact |
| --- | --- | --- | --- |
| 当前 contract 无依赖决策 | read | task-contract、validator | STG-02 |
| 当前 checker 存在语义空洞 | confirmed | checker 与 17 项测试 | STG-03/05 |
| Go 用户明确需要这些可信度信号 | primary | 5,379 人官方调查 | REQ-02 |
| Gin/GORM 当前具有大规模可观测采用 | external snapshot | pkg.go.dev 2026-07-15 | 示例，不形成永久规则 |
| 单一评分不适合自动决策 | primary | OpenSSF Scorecard non-goal | NFR-01 |
| active pointer 缺完整切换协议 | confirmed | current docs + evaluation | STG-03 |

## 候选方案（Options）

### 方案 A：只补文案提醒

- 做法：在 Research Gate 增加“优先主流库”和若干 URL。
- 优点：改动最少，易理解。
- 缺点：没有机器契约、证据底线、Executor 约束；依旧可写一句“已调研”通过。
- 风险：效果依赖 agent 自觉，无法证明趋势、新鲜度或例外合理性。
- 验证：只能做关键词 eval。
- 回滚：删除新增文案。

### 方案 B：结构化可信度门禁与执行闭环

- 做法：新增渐进式 Dependency Selection Gate、`DEP-*` 决策、选型附件、语义 checker、Executor drift enforcement，并同步 pointer 与 CI 缺口。
- 优点：证据可审计、结论可执行、负向行为可测；none 路径仍轻量。
- 缺点：contract 和测试矩阵增加，必须谨慎处理跨生态差异与自举。
- 风险：阈值过硬可能误拦安静但成熟的小工具；通过分类例外和 quiet-utility 解释降低。
- 验证：VAL-01..08。
- 回滚：按模块回退 gate、contract、checker、executor 和 CI，不影响其它 Skill runtime。

### 方案 C：自动评分与包推荐服务

- 做法：在线抓取注册表、GitHub、Scorecard 和 OSV，计算统一分数并自动推荐。
- 优点：自动化程度高，理论上能持续刷新。
- 缺点：指标口径、认证、限流、缓存、服务维护、误判和跨生态偏差显著。
- 风险：把启发式分数伪装成事实，新增后台服务和供应链攻击面。
- 验证：需要高成本在线集成和长期校准。
- 回滚：移除服务与缓存，复杂且收益不确定。

## 决策（Decision）

选择方案（Chosen option）：`方案 B：结构化可信度门禁与执行闭环`

原因（Why）:

- 用户要求的是正式决策门，而不是推荐文案。
- OpenSSF、CHAOSS、deps.dev 和 Go 调查共同支持“多信号、带时间窗口、先适配再比较”的结构。
- 当前 Planner 已有 Research/Standards/Quality gate 和 closed contract，可在现有边界内扩展，无需新服务。
- Executor 已有 Research Drift/Amendment，可消费批准的依赖 receipt，不需重造状态机。
- active pointer 与语义 checker 是同一批准入口的明显短板，适合同时修补；其它 Executor 锁与证明问题保持排除。

影响（Impact）:

- Planner 新增依赖触发、必要性、优先级、硬门槛、比较信号、新鲜度和专用例外规则。
- `plan-contract.json` 增加条件化 dependency decision；新模板始终显式输出，none 可为空。
- full/standard 选型任务生成 `dependency-selection.md`，包含候选矩阵和证据 receipt。
- checker 使用受控枚举、日期、URL、artifact/validation/manifest 引用进行语义校验，并加强所有门禁的空内容检测。
- Executor 读取批准决策，实施前检查新鲜度，依赖实际变更由 planned manifest/lock validation 证明。
- 独立 Planner/Executor CI 在所有分支运行三平台单测与确定性 eval。

可逆性（Reversibility）:

- policy、schema validator、plan checker、pointer helper、executor gate、eval 和 CI 各自模块化，可按阶段回退。
- 不做现有项目依赖迁移，不引入数据库、服务或新包，回退不需要数据转换。
- 已批准计划保持不可变；自举通过“none 且无 dependency surface”的条件语义完成，不创建 schema 版本分支。

变更条件（Change conditions）:

- 若在线研究显示某生态没有可验证的 adoption scale 或 trend，保留统一结果字段，但用生态专属代理和局限替代，不降低硬门槛。
- 若 30/60/90 天在测试中造成无价值重复搜索，只能调整风险分类或 recheck 触发，不可取消 `as_of` 与 freshness。
- 若 generic manifest validation 无法可靠解析某包管理器，计划必须声明生态官方命令，而非在 checker 中手写脆弱解析器。

方案变更触发条件（Reapproval triggers）:

- 改变硬门槛、证据年龄、专用例外或项目优先级语义。
- 新增运行时依赖、后台服务、自动安装或自动在线评分。
- 修改 stage DAG、required VAL、公共权限、外部写或提交策略。
- 为热门候选强制迁移已有项目栈，或扩大到无关 Skill/Executor 状态协议。

## 影响面矩阵（Impact Matrix）

| Surface | Involved | Files/modules | Risk | Validation | Docs |
| --- | --- | --- | --- | --- | --- |
| Planner workflow | yes | SKILL、planning-workflow、new dependency reference | high | VAL-01/02/07 | Skill/reference |
| Task contract | yes | task-contract、template、contract validators | high | VAL-01/05 | contract docs |
| Plan checker | yes | harness_plan_check、dependency validator | high | VAL-01/02/05 | troubleshooting |
| Active pointer | yes | new focused helper + Planner workflow | high | VAL-01/05 | workflow |
| Executor | yes | SKILL、execution-workflow、preflight/drift scripts | high | VAL-03/04/05/07 | executor refs |
| Eval fixtures | yes | planner/executor prompts and deterministic runners | medium | VAL-02/04 | eval metadata |
| CI | yes | `.github/workflows/planner-executor.yml` | medium | VAL-01..04/08 | README |
| Repo docs | yes | README、CHANGELOG | low | VAL-06/07 | itself |
| Runtime service | no | none | none | not applicable | none |
| User project dependencies | no | no manifest change | none | VAL-05/07 | explicit non-goal |
| Compatibility layer | no | no schema versions | none | VAL-01/05 | latest contract only |

## 实施计划（Implementation Plan）

阶段依赖、引用、授权和验证以 `plan-contract.json` 为机器真相源；本节解释实施理由和边界。

### STG-01：依赖可信度政策与规划资产

目标（Goal）:

- 让 Planner 在恰当时机主动进行依赖选型研究，并得到可复用、不过载入口文档的详细规则。

做法（How）:

- 在 SKILL 与 planning workflow 增加 Dependency Selection Gate 触发和简洁主流程。
- 新建 `references/dependency-selection.md`，定义 necessity、priority、hard gates、signals、freshness、trend、exception 和 evidence floor。
- 更新 execution plan 模板，加入依赖门禁与当前任务 mode/result。
- 新建 `templates/artifacts/dependency-selection.md`，固定候选矩阵、证据 receipt、版本策略、风险与回滚。
- research findings 与 standards index 模板补充依赖来源层级、观察日期、窗口和局限。

原因（Why）:

- 入口必须短，复杂证据规则通过 progressive disclosure 进入 reference 和 artifact。
- 必要性门避免为“主流”引入无用依赖，priority 避免破坏现有项目一致性。

位置（Where）:

- 文件/模块：`skills/complex-coding-planner/SKILL.md`、`references/planning-workflow.md`、new reference、`templates/**`。
- API/配置：只改变规划协议，无运行时网络 API。
- 测试/文档：STG-05 增加 eval 和 checker fixture；STG-06 收敛公共说明。

参考来源（References）:

- OpenSSF Concise Guide、Go Survey、CHAOSS、deps.dev、Scorecard、OSV。

适用规范（Standards applied）:

- ART-02 的 source hierarchy、project-first、evidence freshness 和 no-single-score 规则。

开发质量检查（Development quality checks）:

- SKILL 保持触发与主流程，详细规则只放一个专属 reference。
- 不复制外部规范全文，只保存摘要、URL、适用边界和决策影响。

验证（Validation）:

- VAL-01、VAL-02、VAL-05、VAL-07。

风险和回滚（Risks and rollback）:

- 风险：规划文本过长、每次任务都跑完整矩阵。通过 trigger/mode 和 progressive disclosure 限制。
- 回滚：移除依赖 gate 章节与新模板，不触及 Executor runtime。

阶段契约（Stage Contract）:

- 依赖：none。
- 需求/验收：REQ-01/02/03；AC-01/02/03/04/09；NFR-01/02/03/04/05/07。
- 允许修改：Planner SKILL、references、templates。
- 禁止修改：永久推荐榜、自动安装、runtime state、无关 Skill。
- 进入条件：计划批准、ART-01..03 固定、Planner baseline 通过。
- 退出条件：六级流程、证据底线和 none 路径一致。
- 必需验证：VAL-01/02/05/07。
- Contract `requirement_ids`：`REQ-01`、`REQ-02`、`REQ-03`。
- Contract `acceptance_ids`：`AC-01`、`AC-02`、`AC-03`、`AC-04`、`AC-09`。
- Contract `nonfunctional_ids`：`NFR-01`、`NFR-02`、`NFR-03`、`NFR-04`、`NFR-05`、`NFR-07`。
- Contract `validation_ids`：`VAL-01`、`VAL-02`、`VAL-05`、`VAL-07`。
- Contract `allowed_changes`：`skills/complex-coding-planner/SKILL.md`、`skills/complex-coding-planner/references/**`、`skills/complex-coding-planner/templates/**`。
- Contract `forbidden_changes`：`hard-coded permanent package winners`、`automatic package installation`、`runtime state files`、`unrelated skills`。
- 是否预期提交：`stage`，用户已授权。

### STG-02：机器契约与依赖决策校验器

目标（Goal）:

- 将依赖决策变成 Planner 和 Executor 共同消费的 closed contract，而不是 Markdown 建议。

做法（How）:

- 增加 `DEP-*` ID 和条件化 `dependency_decisions` 根字段；模板始终显式输出数组。
- 每个 decision 记录 action、criticality、requirements、selection class、selected package/version policy、manifest paths、artifact 与 validation 引用。
- 候选 receipt 记录九类信号的 result、source、as_of、window、caveat；hard gate 与 comparative signal 分开。
- 新建 `harness_contract_dependencies.py`，由现有 contract rules 组合，避免继续膨胀单文件。
- `none` 仅在无 add/replace/upgrade scope 时允许空数组；自举计划按这一语义通过。

原因（Why）:

- Executor 需要精确身份和版本策略，checker 需要稳定字段和错误码。
- 条件化字段可服务轻量任务，也避免维护多个 schema 版本。

位置（Where）:

- 文件/模块：task-contract reference、contract template、`harness_contract*.py`。
- API/配置：JSON contract 新字段与 `DEP-*` 引用。
- 测试/文档：STG-05 覆盖 closed object、ID、日期、引用和异常。

参考来源（References）:

- ART-03 schema sketch；当前 closed contract 规则；deps.dev version/advisory/provenance 字段。

适用规范（Standards applied）:

- closed input、least authority、stable diagnostics、single source of truth。

开发质量检查（Development quality checks）:

- 依赖 validator 独立高内聚，不进行网络请求。
- checker 验证 receipt，不对真实世界热度作离线断言。

验证（Validation）:

- VAL-01、VAL-02、VAL-05、VAL-07。

风险和回滚（Risks and rollback）:

- 风险：schema 太细导致填写成本高。只对正式候选保存完整 receipt，摘要字段避免复制全文。
- 回滚：移除可选根字段与模块，并恢复模板；无数据迁移。

阶段契约（Stage Contract）:

- 依赖：STG-01。
- 需求/验收：REQ-02/03；AC-03/04/05；NFR-01/02/03/04/06/07。
- 允许修改：Planner contract scripts、task-contract reference、contract template。
- 禁止修改：schema 版本分支、deterministic validator 网络访问、总分赢家、Executor state semantics。
- 进入条件：STG-01 完成，ART-03 字段固定。
- 退出条件：DEP、mode、receipt、freshness、version 和 exception 均闭合校验。
- 必需验证：VAL-01/02/05/07。
- Contract `requirement_ids`：`REQ-02`、`REQ-03`。
- Contract `acceptance_ids`：`AC-03`、`AC-04`、`AC-05`。
- Contract `nonfunctional_ids`：`NFR-01`、`NFR-02`、`NFR-03`、`NFR-04`、`NFR-06`、`NFR-07`。
- Contract `validation_ids`：`VAL-01`、`VAL-02`、`VAL-05`、`VAL-07`。
- Contract `allowed_changes`：`skills/complex-coding-planner/scripts/harness_contract*.py`、`skills/complex-coding-planner/references/task-contract.md`、`skills/complex-coding-planner/templates/plan-contract.json`。
- Contract `forbidden_changes`：`schema version forks`、`network calls inside deterministic contract validation`、`aggregate popularity winner`、`executor runtime state semantics`。
- 是否预期提交：`stage`，用户已授权。

### STG-03：语义门禁与活动任务指针安全

目标（Goal）:

- 让 approval checker 验证可证明的完成事实，并阻止规划任务相互覆盖。

做法（How）:

- 解析受控 gate result 和 dependency mode，不再只搜索英文未完成标记或任意 URL。
- 要求研究证据最低集合、日期、窗口、官方来源和 artifact receipt；检查 plan/contract `DEP-*` 漂移。
- 对其它 Research/Standards/Quality/Readiness gate 增加最小语义内容，拒绝仅写 `complete` 的空节。
- 新建 focused active-task helper：缺失则写入；同任务复用；旧任务 run-state 为 terminal 则原子替换；非终态或状态未知则拒绝并要求显式切换。
- 错误码保持稳定，测试不依赖自然语言全文匹配。

原因（Why）:

- 当前结构检查容易把形式完整误当作决策完整。
- active pointer 是恢复入口，静默覆盖会让 Executor 接错任务。

位置（Where）:

- 文件/模块：`harness_plan_check.py`、new `harness_active_task.py`、Planner workflow/SKILL。
- API/配置：CLI 可提供 check/write/switch 所需最小参数；不写 run-state。
- 测试/文档：四态 pointer 与空门禁 negative fixtures。

适用规范（Standards applied）:

- fail closed、atomic replace、stable diagnostics、pointer-only ownership。

开发质量检查（Development quality checks）:

- pointer 模块不导入 Executor reducer；只读取公开 terminal lifecycle 字段。
- 语义规则基于受控字段和引用，不做脆弱长文本评分。

验证（Validation）:

- VAL-01、VAL-02、VAL-05、VAL-07。

风险和回滚（Risks and rollback）:

- 风险：更严格 checker 误拦 none 任务。用显式 mode 和 profile 条件测试防止。
- 回滚：恢复 checker 检查集和旧 pointer 写入流程，保留诊断 fixture 供对比。

阶段契约（Stage Contract）:

- 依赖：STG-02。
- 需求/验收：REQ-03/04；AC-05/07；NFR-05/06/07。
- 允许修改：Planner checker、pointer helper、references、SKILL。
- 禁止修改：自由文本成功判定、静默覆盖、ledger mutation、external write。
- 退出条件：空门禁、漂移和冲突均被稳定拒绝。
- 必需验证：VAL-01/02/05/07。
- Contract `requirement_ids`：`REQ-03`、`REQ-04`。
- Contract `acceptance_ids`：`AC-05`、`AC-07`。
- Contract `nonfunctional_ids`：`NFR-05`、`NFR-06`、`NFR-07`。
- Contract `validation_ids`：`VAL-01`、`VAL-02`、`VAL-05`、`VAL-07`。
- Contract `allowed_changes`：`skills/complex-coding-planner/scripts/harness_plan_check.py`、`skills/complex-coding-planner/scripts/harness_active_task.py`、`skills/complex-coding-planner/references/**`、`skills/complex-coding-planner/SKILL.md`。
- Contract `forbidden_changes`：`free-form keyword success detection`、`silent active pointer overwrite`、`executor ledger mutation`、`external writes`。
- 是否预期提交：`stage`，用户已授权。

### STG-04：Executor 依赖决策执行与漂移闭环

目标（Goal）:

- 确保批准阶段的选择在实施中不被“顺手换包”“直接 latest”或陈旧事实绕过。

做法（How）:

- Executor preflight 读取 dependency decisions，none 直接跳过；其它模式建立 stage checks。
- 在涉及 manifest/lock 的阶段核对 package identity、selection class、version constraint 和 approved paths。
- 根据 criticality 与 `as_of` 计算 freshness；过期、archived/deprecated、support line 或 applicable advisory 变化触发在线复核。
- 复核不改变结论时写 execution evidence；包、版本策略、风险或 hard gate 变化时走 Research Drift/Plan Amendment。
- 实际 manifest 与 lock 一致性使用该生态官方包管理器命令或计划声明的验证，不在通用 checker 里手写所有解析器。

原因（Why）:

- Planner 的可信结论只有被 Executor 精确执行才产生效果。
- 可变事实需要执行时二次确认，但网络失败不能变成默认放行。

位置（Where）:

- 文件/模块：Executor SKILL、execution workflow、preflight/drift 相关 scripts。
- API/配置：消费 `DEP-*`，不增加后台服务或外部写权限。
- 测试/文档：stale、identity drift、version drift、advisory drift、none 快速路径。

适用规范（Standards applied）:

- immutable approval intent、research drift、default deny、ecosystem-native verification。

开发质量检查（Development quality checks）:

- 不复制 Planner 的完整候选评分，只校验批准 receipt 与事实变化。
- 不把网络探针放进 reducer；preflight orchestration 负责外部复核结果。

验证（Validation）:

- VAL-03、VAL-04、VAL-05、VAL-07。

风险和回滚（Risks and rollback）:

- 风险：短暂网络失败阻塞实施。记录 blocked-by-access 与缓存证据年龄，只有仍在有效窗口内才可继续。
- 回滚：移除 dependency preflight hook，不改变现有 ledger/attestation。

阶段契约（Stage Contract）:

- 依赖：STG-02、STG-03。
- 需求/验收：REQ-05；AC-06；NFR-02/03/05/06/07。
- 允许修改：Executor SKILL、references、scripts。
- 禁止修改：未批准替换、自动 latest、网络写入、无关状态协议重构。
- 退出条件：身份、版本、路径和新鲜度可核对，变化进入 drift/amendment。
- 必需验证：VAL-03/04/05/07。
- Contract `requirement_ids`：`REQ-05`。
- Contract `acceptance_ids`：`AC-06`。
- Contract `nonfunctional_ids`：`NFR-02`、`NFR-03`、`NFR-05`、`NFR-06`、`NFR-07`。
- Contract `validation_ids`：`VAL-03`、`VAL-04`、`VAL-05`、`VAL-07`。
- Contract `allowed_changes`：`skills/complex-coding-executor/SKILL.md`、`skills/complex-coding-executor/references/**`、`skills/complex-coding-executor/scripts/**`。
- Contract `forbidden_changes`：`unapproved dependency substitution`、`automatic latest-version upgrade`、`network mutation during preflight`、`unrelated attestation or ledger redesign`。
- 是否预期提交：`stage`，用户已授权。

### STG-05：负向单测与行为评估扩展

目标（Goal）:

- 用行为 fixture 证明 Planner 会做正确取舍，而不是只出现新关键词。

做法（How）:

- 扩展 planner valid contract/plan fixture，使 none 和 selection 两条路径都合法。
- 增加缺信号、过期、invalid date/window、单 URL、单 stars、archived、pre-release、无主流比较的专用例外等失败用例。
- 增加 active pointer missing/same/terminal/conflict/unknown 和原子写失败用例。
- Planner eval 增加：现有 Echo 保留、微型 endpoint 选标准库、工程化 Go REST 把 Gin 作为当前主流基线、CRUD 将 GORM 纳入候选、SQL-first 可选择 sqlc 并解释。
- Executor eval 增加：未批准包、版本越界、stale recheck、advisory drift、none 快速路径。

原因（Why）:

- “优先主流”必须与“项目适配优先”同时被测，否则容易退化为热门包迁移器。
- 负向 fixture 是语义 gate 的主要回归保障。

位置（Where）:

- Planner/Executor tests 与 `evals/complex-coding-planner`、`evals/complex-coding-executor`。

适用规范（Standards applied）:

- deterministic、no agent execution、no network in tests、stable error codes。

开发质量检查（Development quality checks）:

- fixture builder 复用公共 helper，避免每个 case 复制完整 contract。
- eval 同时断言结构和决策行为，不仅匹配单个词。

验证（Validation）:

- VAL-01、VAL-02、VAL-03、VAL-04、VAL-05、VAL-07。

风险和回滚（Risks and rollback）:

- 风险：具体包快照让 eval 随时间失效。eval 验证选择原则；数值只放研究附件并标记观察日。
- 回滚：逐 scenario 移除，不影响生产代码。

阶段契约（Stage Contract）:

- 依赖：STG-03、STG-04。
- 需求/验收：REQ-03/04/05/06；AC-01..09；NFR-01..07。
- 允许修改：Planner/Executor tests 与 evals。
- 禁止修改：agent execution、live install、network-dependent deterministic tests、keyword-only assertions。
- 退出条件：正向、边界和负向矩阵通过。
- 必需验证：VAL-01..05、VAL-07。
- Contract `requirement_ids`：`REQ-03`、`REQ-04`、`REQ-05`、`REQ-06`。
- Contract `acceptance_ids`：`AC-01`、`AC-02`、`AC-03`、`AC-04`、`AC-05`、`AC-06`、`AC-07`、`AC-08`、`AC-09`。
- Contract `nonfunctional_ids`：`NFR-01`、`NFR-02`、`NFR-03`、`NFR-04`、`NFR-05`、`NFR-06`、`NFR-07`。
- Contract `validation_ids`：`VAL-01`、`VAL-02`、`VAL-03`、`VAL-04`、`VAL-05`、`VAL-07`。
- Contract `allowed_changes`：`skills/complex-coding-planner/tests/**`、`skills/complex-coding-executor/tests/**`、`evals/complex-coding-planner/**`、`evals/complex-coding-executor/**`。
- Contract `forbidden_changes`：`agent execution`、`live package installation`、`network-dependent deterministic tests`、`tests that assert only keywords`。
- 是否预期提交：`stage`，用户已授权。

### STG-06：三平台 CI 与公共文档收敛

目标（Goal）:

- 让 Planner/Executor 的公共契约在每个分支和三平台持续可见、可复现。

做法（How）:

- 新增 `.github/workflows/planner-executor.yml`，对所有 branches 和 pull requests 运行 Windows、Ubuntu、macOS Python 3.12 matrix。
- 每个平台运行双方 unit 和 deterministic eval；workflow contract test 检查 branch scope、matrix 与命令。
- 更新 README 与 CHANGELOG，说明 dependency gate、freshness、specialized exception、Executor drift 和 pointer collision。
- 在 Go 示例中记录 2026-07-15 pkg.go.dev 快照，但明确重新规划时必须在线刷新。

原因（Why）:

- 当前两项 Skill 没有独立、易发现的 CI；跨平台 contract 改动需要持续防回归。

位置（Where）:

- workflow、README、CHANGELOG、两个 Skill 的公共文档。

适用规范（Standards applied）:

- least-privilege workflow、all branches、无 secret、deterministic commands。

开发质量检查（Development quality checks）:

- workflow 不使用 `runner.*` job-level 非法表达式；临时路径在 step shell 内取得。
- hosted 结果未运行时保持 optional，不能伪造为本地通过。

验证（Validation）:

- VAL-01..04、VAL-06、VAL-07；VAL-08 由用户推送后提供。

风险和回滚（Risks and rollback）:

- 风险：三平台重复 eval 增加 CI 时间。当前套件均为秒级，保持单 Python 版本。
- 回滚：移除独立 workflow，保留本地命令与文档。

阶段契约（Stage Contract）:

- 依赖：STG-05。
- 需求/验收：REQ-06；AC-08/09；NFR-05/06/07。
- 允许修改：workflow、README、CHANGELOG、相关 Skill docs。
- 禁止修改：漏跑 feature branch、secret、远端 dispatch、无关 Skill。
- 退出条件：三平台全分支定义和本地 workflow contract 通过。
- 必需验证：VAL-01..04、VAL-06/07；VAL-08 optional。
- Contract `requirement_ids`：`REQ-06`。
- Contract `acceptance_ids`：`AC-08`、`AC-09`。
- Contract `nonfunctional_ids`：`NFR-05`、`NFR-06`、`NFR-07`。
- Contract `validation_ids`：`VAL-01`、`VAL-02`、`VAL-03`、`VAL-04`、`VAL-06`、`VAL-07`、`VAL-08`。
- Contract `allowed_changes`：`.github/workflows/planner-executor.yml`、`README.md`、`CHANGELOG.md`、`skills/complex-coding-planner/**`、`skills/complex-coding-executor/**`。
- Contract `forbidden_changes`：`branch filters that omit feature branches`、`secret-dependent CI`、`remote workflow dispatch`、`unrelated skill documentation`。
- 是否预期提交：`stage`，用户已授权。

### STG-07：自举复核、最终审查与交付

目标（Goal）:

- 在批准计划不被改写的前提下，证明新版规则能验证自身并完成 source-bound 交付审查。

做法（How）:

- 重跑 Planner/Executor unit、eval、当前任务 approval checker 与 diff check。
- 用当前任务 `none`、无 manifest scope 的事实验证自举条件。
- 按 ART-07 核对每个 REQ/AC/NFR/STG/VAL 和实际 diff，审查诊断、边界、错误路径、文档与 overengineering。
- 只有用户另行授权时创建最终 commit；不 push、不 dispatch workflow。

原因（Why）:

- 本任务修改批准协议本身，必须有 self-host 和 source-bound 证据。

位置（Where）:

- 已批准代码范围与 task validation/review artifacts。

适用规范（Standards applied）:

- immutable plan、attestation、required validation、final review、explicit commit authorization。

开发质量检查（Development quality checks）:

- 失败证据不能被后一次成功覆盖，最终 review 绑定 source hash。
- optional hosted CI 保持 not-run，直到用户推送提供结果。

验证（Validation）:

- VAL-01..07 required；VAL-08 optional。

风险和回滚（Risks and rollback）:

- 风险：新版 checker 无法验证批准前的当前契约。STG-02 的条件化 none 语义和 VAL-05 专门覆盖此自举。
- 回滚：停止交付并按首次失败阶段回退，不改写批准计划。

阶段契约（Stage Contract）:

- 依赖：STG-06。
- 需求/验收：REQ-01..06；AC-01..09；NFR-01..07。
- 允许修改：全部批准代码范围和 task evidence。
- 禁止修改：scope expansion、push、fabricated CI、unauthorized commit。
- 退出条件：required 验证通过、当前计划自举通过、最终审查无 blocker。
- 必需验证：VAL-01..07。
- Contract `requirement_ids`：`REQ-01`、`REQ-02`、`REQ-03`、`REQ-04`、`REQ-05`、`REQ-06`。
- Contract `acceptance_ids`：`AC-01`、`AC-02`、`AC-03`、`AC-04`、`AC-05`、`AC-06`、`AC-07`、`AC-08`、`AC-09`。
- Contract `nonfunctional_ids`：`NFR-01`、`NFR-02`、`NFR-03`、`NFR-04`、`NFR-05`、`NFR-06`、`NFR-07`。
- Contract `validation_ids`：`VAL-01`、`VAL-02`、`VAL-03`、`VAL-04`、`VAL-05`、`VAL-06`、`VAL-07`、`VAL-08`。
- Contract `allowed_changes`：`skills/complex-coding-planner/**`、`skills/complex-coding-executor/**`、`evals/complex-coding-planner/**`、`evals/complex-coding-executor/**`、`.github/workflows/planner-executor.yml`、`README.md`、`CHANGELOG.md`、`.harness/tasks/2026-07-15/feature/planner-dependency-trust-gate/artifacts/**`。
- Contract `forbidden_changes`：`unapproved scope expansion`、`remote push or external write`、`fabricated CI evidence`、`commit without explicit authorization`。
- 是否预期提交：`final`，用户已授权。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md` 提供稳定的 Python、Git、branch、artifact 和 process-manager 约束。
- 其中历史任务状态不作为当前计划事实；当前 Git 与测试基线已在本轮重新读取。

本任务使用（This task uses）:

- Workspace：`D:\Item\vibe_coding\dev-skills`
- Python：3.11+ 标准库；CI 使用 Python 3.12。
- Git：`harness/feature`，HEAD `46fb44e3ee2a5ec1b7f3b387efd0e35a702162be`。
- 初始状态：working tree clean，HEAD 与 `main`、`origin/main`、`origin/harness/feature` 对齐。
- 长期服务：none。

临时覆盖（Temporary overrides）:

- 单测若受系统 `%TEMP%` ACL 影响，优先把 `TMP`/`TEMP` 指向 task `tmp/`；只有仍需沙箱外临时目录时才请求 elevated tool。
- Python 命令统一 `-B`，避免无必要 `__pycache__` 写入。

规划阶段已执行基线：

| Suite | Result | Date | Note |
| --- | --- | --- | --- |
| Planner unittest | 17 passed | 2026-07-15 | 受限系统 temp 首次失败，授权环境重跑通过 |
| Planner deterministic eval | 10/10 passed | 2026-07-15 | 3 capability + 7 regression |
| Executor unittest | 39 passed | 2026-07-15 | 授权环境运行 |
| Executor deterministic eval | 13/13 passed | 2026-07-15 | 7 capability + 6 regression |

## Git 上下文（Git Context）

- Main / working branch：`main` / `harness/feature`
- Task type / branch action：feature；当前工作分支已存在，不创建新分支。
- Sync source / occupancy evidence：HEAD 与 main 和两个 remote refs 对齐；无并发 Git 操作证据。
- Worktree status and known changes：规划开始时 clean；本轮只新增当前 task bundle 与更新 active pointer。
- Commit authorization：`authorized for stage/final commits`
- Branch closure：已授权阶段提交与最终提交；不 merge、不 push。

规则：同一仓库 Git 命令串行；只读状态优先 `--no-optional-locks`，diff 优先禁用 index refresh。不自动 stash、rebase、reset 或覆盖未知改动。遇到 `index.lock` 时只按精确路径、稳定性和进程检查恢复，并记录 evidence。

## 工具（Tooling）

| Tool | Purpose | Stage | Status | Risk | Alternative | User confirmation |
| --- | --- | --- | --- | --- | --- | --- |
| apply_patch | 分段修改 Skill、脚本、fixture 和文档 | STG-01..07 | available | low | 缩小 patch 后重试 | not required |
| Python unittest | Planner/Executor contract 与行为测试 | STG-02..07 | available | low | task-local temp | not required |
| deterministic eval | 规划与执行行为回归 | STG-05..07 | available | low | none | not required |
| web search/open | 规划与执行时刷新依赖证据 | Planning/STG-07 | available | medium, volatile facts | blocked-by-access + valid cached receipt | online read only |
| Git | 串行 status/diff/阶段与最终 commit | STG-01 至 STG-07 | available | medium | review + required validation | stage/final commits authorized |
| GitHub Actions | hosted 三平台验证 | post-push | workflow only | external execution | 本地三平台不可替代 | push/dispatch not requested |

## 长期进程管理（Process Manager Gate）

- Needs long-running process：`no`
- Manager bootstrap：not applicable。
- Managed services：none。
- Required process-manager evidence：none。
- Completion fields：not applicable。
- Fallback or blocker：所有测试、eval、checker 和格式检查均为 finite commands；不得为本任务启动后台服务。

## 验证（Validation）

| VAL ID | Required | Kind / command / tool | Covers AC/NFR | Evidence path | Failure handling |
| --- | --- | --- | --- | --- | --- |
| VAL-01 | yes | Planner unittest discover | AC-01..05/07..09；NFR-01..07 | `artifacts/validation/planner-unit-tests.txt` | 修复首个稳定失败并全量重跑 |
| VAL-02 | yes | `evals/complex-coding-planner/run_evals.py` | AC-01..05/08/09；NFR-01/02/04/05/07 | `artifacts/validation/planner-evals.json` | 行为断言失败即停止 stage |
| VAL-03 | yes | Executor unittest discover | AC-06/08；NFR-02/03/05/06/07 | `artifacts/validation/executor-unit-tests.txt` | 修复 preflight/drift 回归并全量重跑 |
| VAL-04 | yes | `evals/complex-coding-executor/run_evals.py` | AC-06/08；NFR-02/03/05/07 | `artifacts/validation/executor-evals.json` | consumer acceptance 非 1.0 即停止 |
| VAL-05 | yes | 当前 task `harness_plan_check --mode approval --format json` | AC-05/06/07/08；NFR-02/04/05/07 | `artifacts/validation/self-host-plan-check.json` | 新版无法验证 none 自举即阻塞交付 |
| VAL-06 | yes | `git -c diff.autoRefreshIndex=false diff --check` | AC-08；NFR-06/07 | `artifacts/validation/diff-check.txt` | 修正 whitespace 后重跑 |
| VAL-07 | yes | ART-07 source-bound final code review | AC-01..09；NFR-01..07 | `artifacts/reviews/final-code-review.md` | blocker 或 source drift 不得完成 |
| VAL-08 | no | 用户推送后 hosted Windows/Ubuntu/macOS matrix | AC-08；NFR-06 | `artifacts/validation/hosted-platform-matrix.json` | 未运行标记 not-run，不冒充本地证据 |

规划探针与实施验证分离。每个 required command 的最终 evidence 必须绑定实施 source；规划阶段基线只能证明起点健康，不能替代最终结果。

## 文档（Documentation）

必需更新（Required updates）:

- Planner SKILL：何时触发依赖门禁、何时读取专属 reference、none 快速路径。
- Planner references：完整选型、证据、趋势、新鲜度、例外和 pointer 切换协议。
- Planner templates：execution plan、contract、research、standards、dependency selection artifact。
- Executor SKILL/reference：approved dependency、freshness recheck、manifest validation、Research Drift。
- README：能力摘要和本地验证入口。
- CHANGELOG：依赖决策 contract、语义 checker、pointer fail closed、Executor enforcement 和 CI。

Changelog 计划（Changelog plan）:

- 以 feature 条目说明行为变更和不变项：无永久包榜单、无自动迁移、无新增服务、无第三方运行时依赖。
- 记录 evidence 30/60/90 天默认值和专用例外需要显式理由。

## 文件写入策略（File Write Strategy）

| File / group | Segmented | Semantic boundaries | Whole-file check |
| --- | --- | --- | --- |
| Planner SKILL/workflow/reference | yes | trigger / workflow / evidence / pointer | link、heading、eval |
| task contract docs/templates | per file | complete JSON object / reference section | JSON parse + checker tests |
| contract/checker scripts | yes | constants / validation / composition / CLI | AST + unittest |
| pointer helper | yes | resolve / classify / atomic write / CLI | four-state tests |
| Executor workflow/scripts | yes | preflight / freshness / drift / evidence | AST + unit/eval |
| tests/evals | per scenario | fixture builder / positive / negative | direct suite commands |
| CI workflow | no | complete YAML job/matrix | workflow contract test |
| README/CHANGELOG | per section | Planner / Executor / release note | links + diff check |

长内容先建框架，再按完整章节、函数或配置分段 patch；单次新增建议不超过 120 行、最多 200 行。超过 500 行的现有文件只做定点修改。patch 失败先检查部分写入，最终完整重读并检查格式、ID、引用和末尾。

## 问题和覆盖项（Questions And Overrides）

| ID | Blocking | Status | Question | Decision | Applied to |
| --- | --- | --- | --- | --- | --- |
| Q-01 | no | resolved | “主流”是否等于下载或 stars 最大 | 否；硬门槛 + 多信号 + 项目适配，单指标只作 receipt | REQ-01/02、NFR-01 |
| Q-02 | no | resolved | 是否固定推荐 Gin/GORM | 否；它们是 2026-07-15 Go 工程化示例，实际任务必须刷新并比较 | AC-09 |
| Q-03 | no | resolved | 无历史采用数据怎么办 | 记录 insufficient-data、窗口和限制，至少两个代理信号；高风险且非官方/项目标准时升级用户决策 | NFR-04 |
| Q-04 | no | resolved | 安静但成熟的小工具是否一律失败 | 否；归档/弃用仍硬失败，quiet-utility 可通过专用维护解释，但框架/ORM 不适用该宽松例外 | ART-03 |
| Q-05 | no | resolved | checker 是否在线判断真实热度 | 否；在线采集由 Planner/Executor 完成，checker 只验证 receipt 和一致性 | STG-02/03 |
| Q-06 | no | resolved | 当前计划如何通过未来 contract | 当前任务无 manifest/dependency surface，按条件化 none 语义自举，不创建旧版 schema 分支 | STG-02/07 |
| Q-07 | no | resolved | 旧 active pointer 如何处理 | 当前指向 terminal completed task；approval checker 通过后原子切到本 task | AC-07 |
| Q-08 | no | resolved | hosted CI 是否阻塞本地交付 | workflow 定义和本地 suite required；用户推送后的 hosted result 为 optional VAL-08 | STG-06/07 |
| Q-09 | no | resolved | 是否实施和提交 | 用户已批准 implementation，并允许阶段完成后自动提交；push、external write 和 elevated tool 未授权 | Approval |

## 方案质量门禁（Plan Quality Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| 关键判断有证据等级 | passed | Context evidence levels、ART-01 |
| Research Gate 已完成 | passed | online-required、8 类搜索、ART-01 |
| Standards Discovery Gate 已完成 | passed | ART-02 与 applicability matrix |
| Dependency Selection Gate 已完成 | passed | 本任务 none；目标 gate 与证据底线见本计划和 ART-03 |
| Development Quality Gate 已完成 | passed | quality scope、overengineering guard、ART-03/06 |
| 影响面矩阵完整 | passed | 10 个 surface 与明确 non-goals |
| 候选方案比较充分 | passed | A/B/C 的收益、成本、风险、验证和回滚 |
| 每阶段可独立验证 | passed | STG-01..07 与 VAL mapping |
| 方案变更触发条件清楚 | passed | Decision + contract reapproval triggers |
| 用户批准摘要可记录 | passed | implementation only；其它授权排除 |

质量结论（Quality result）：`passed`。

## 规划自查（Plan Self-Review）

自查结论（Review result）：`passed with disclosed residual risks`。

| Category | Finding | Action | Result |
| --- | --- | --- | --- |
| 缺陷 | 原 Research Gate 可由一个 URL 和口号式 complete 满足 | 增加 evidence floor、受控 result 和 semantic receipts | closed |
| 缺陷 | “优先主流”可能诱发已有项目无理由迁移 | 固定 project-first priority，并给 retain eval | closed |
| 缺陷 | Executor 没有批准包/版本可执行 | 增加 `DEP-*` handoff、freshness 与 manifest gate | closed |
| 缺失项 | active pointer 冲突切换未形成流程 | 增加四态原子策略与负向测试 | closed |
| 缺失项 | Planner/Executor 无独立易发现 CI | 增加 all-branches 三平台 workflow | closed |
| 风险 | adoption trend 数据跨生态不可得或不可比 | 强制 result，但允许 insufficient-data + proxies + caveat | bounded |
| 风险 | 30/60/90 天可能造成重复调研 | 只在触发依赖变更与执行过期时复核 | bounded |
| 风险 | Scorecard 和 GitHub dependents 有误报、私有数据缺口 | 使用 probes 和限制说明，不用总分自动决策 | bounded |
| 一致性 | 当前计划本身没有未来 dependency 字段 | 以无 dependency surface 的条件化 none 自举，并用 VAL-05 固定 | closed |
| 开发质量 | contract/checker 继续变大 | 抽离 dependency validator 与 pointer helper | passed |

门禁重跑（Gate rerun）:

- `Plan Quality Gate`：已重跑，passed。
- `Plan Self-Review`：已重跑，passed with residual risks。
- `Readiness Gate`：已重跑，ready for approval。
- 独立 evaluator：unavailable；使用结构化 self-review、ART-07 和 deterministic checker 作为已披露 fallback。

## 就绪门禁（Readiness Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| 目标和验收清楚 | passed | GOAL-01、REQ-01..06、AC-01..09 |
| 上下文已收集 | passed | Planner/Executor code、tests、evals、assessment |
| 调研门禁已通过 | passed | Research Gate、ART-01 |
| 规范发现门禁已通过 | passed | ART-02 |
| 依赖选型门禁已通过 | passed | current mode none + target design ART-03 |
| 开发质量门禁已通过 | passed | quality mapping、ART-03/06 |
| 候选方案已比较 | passed | Options A/B/C |
| 决策已记录 | passed | Structured gate chosen |
| 实施阶段已细化 | passed | 7 stage contracts |
| 环境已确认 | passed | clean branch、Python、finite commands |
| Git 上下文已确认 | passed | HEAD/ref/status、stage/final commit authorization recorded |
| 工具已确认 | passed | Tooling table |
| 验证已确认 | passed | VAL-01..08、ART-05 |
| 最终交付证据已规划 | passed | self-host、source-bound review、optional hosted CI |
| 文档更新已确认 | passed | Skill/reference/template/repo docs |
| 风险已识别 | passed | ART-03/06 + stage rollback |
| 规划自查已通过 | passed | self-review + critique |
| 阻塞问题已关闭 | passed | 用户已批准 implementation 与阶段提交，无技术 blocker |

就绪结论（Readiness result）：`approved_for_execution`。

## 方案批准（Plan Approval）

状态（Status）：`approved`

批准记录（Approval record）:

- 用户于 2026-07-15 明确批准：“批准，进入 Executor 实施阶段，允许阶段性完成后 自动提交代码”。

批准摘要（Approval summary）:

- 批准范围：Planner/Executor 的 SKILL、references、templates、scripts、tests、evals；new combined CI；README、CHANGELOG；本 task evidence。
- 阶段提交授权：已授权；STG-01 至 STG-06 使用 `stage`，STG-07 使用 `final`，每次仅在 review、required validation 和范围检查通过后提交。
- 工具/MCP 授权：实施所需本地只读、apply_patch、finite Python/Git 检查；在线调研只读。
- 外部写与 elevated tool：未授权；若测试临时目录仍需提权必须另行请求。
- 文档更新授权：随 implementation approval 一并申请上述范围内文档修改。

提交策略（Commit policy）：`stage_authorized`；不包含 push、PR 或其它 external write。

## 方案变更门禁（Plan Amendment Gate）

需要重新批准（Requires reapproval）:

- 改变 approved scope、stage DAG、required validations 或 artifact 集合。
- 改变 hard gates、30/60/90 天 freshness、project-first priority 或 specialized exception 语义。
- 增加自动评分、自动安装、后台服务、第三方运行时依赖、外部写或 elevated tool。
- 修改其它 Skill、现有项目依赖、Executor ledger/attestation/task lock，或强制迁移已有技术栈。
- approved plan/artifacts、attestation 或 source-bound evidence 发生无法解释的漂移。

无需重新批准的记录（No-reapproval records）:

- 批准范围内不改变 contract 的内部函数命名、测试 fixture 文案、外部链接修正和格式修正。
- 同一 evidence receipt 的 URL canonicalization 或观测时间格式修正，前提是不改变结论和 freshness。

## Artifact Index

| ID | Kind | Path | Required | Approval included | Trigger |
| --- | --- | --- | --- | --- | --- |
| ART-01 | research | `artifacts/research/dependency-trust-research.md` | yes | yes | online/high-impact |
| ART-02 | standards | `artifacts/standards/standards-index.md` | yes | yes | full profile |
| ART-03 | architecture | `artifacts/architecture/dependency-gate-design.md` | yes | yes | cross-Skill contract |
| ART-04 | architecture | `artifacts/architecture/change-map.md` | yes | yes | multi-module scope |
| ART-05 | validation | `artifacts/validation/validation-strategy.md` | yes | yes | high-risk gate |
| ART-06 | review | `artifacts/reviews/plan-critique.md` | yes | yes | plan self-review |
| ART-07 | other | `artifacts/traceability/traceability-matrix.md` | yes | yes | full traceability |

只列实际 planning artifacts；运行日志、final code review、attestation、run-state、ledger 和 commit evidence 由 Executor 在批准后创建。

## Executor Handoff

- Planner checker：`draft passed`；`approval passed`；均为 0 error / 0 warning。
- Open blocking decisions：none；implementation 和 commit 已批准。
- Requested implementation authorization：yes，approved 2026-07-15。
- Requested commit authorization：yes，stage/final commits approved 2026-07-15。
- Requested external-write authorization：no。
- Requested elevated-tool authorization：no。
- Residual risks：趋势数据跨生态不完整；quiet utility 的维护解释需要人工判断；在线事实会在批准与实施之间变化；hosted 三平台结果依赖用户后续 push。

用户批准后由 Executor 生成 attestation 并初始化 run-state/ledger。本文件批准后不可变。

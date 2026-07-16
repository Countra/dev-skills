# Complex Coding Reviewer 专业化升级执行计划

## 规划摘要（Plan Summary）

- Task ID：`2026-07-16-feature-complex-coding-reviewer-professionalization`
- Plan revision：`2`
- Lifecycle route：`managed`
- Plan profile：`full`
- Discovery-first：`no`
- Task contract：`plan-contract.json`
- Approval request：请求批准 revision 2、继承已完成的 `STG-01`，并继续授权 implementation 与阶段/最终 commit；外部写入和提权仍未授权
- Dependency selection for this task：`none`，实现限定于仓库现有 Python 标准库、Markdown、JSON、YAML、unittest 与 GitHub Actions

本文件只保存待批准的实施意图。批准后不得在本文写入 current stage、progress、运行结果、ledger、commit 或恢复状态；执行事实由 Executor 创建的 attestation、run-state、ledger 与 validation artifacts 承载。

## 问题定义（Problem）

目标（Goal）：`GOAL-01`，在不扩大 Reviewer 权限和 profile 数量的前提下，把当前“目标绑定、结构化 receipt、基础 lenses”的能力升级为专业、证据驱动、范围可审计、语义可评估、复审不丢问题的规划与代码审查系统。

当前 Reviewer 的 closed JSON、target SHA-256、provenance、Planner/Executor 门禁已经解决了“有没有正式审查”和“审查对应哪个目标”的问题，但尚未充分回答：

1. 是否逐项证明需求满足，而不是只写一个 correctness 总结。
2. 审查依据的规范、调用方、验证日志和上下文变化后，旧结论是否仍有效。
3. 复审时每条旧 finding 去了哪里，是否能防止静默删除。
4. 对安全、并发、数据、性能、API、UI、删除等领域，何时需要专业深挖，能力不足时如何诚实阻塞。
5. 当前 eval 是否真正观察到缺陷召回、误报、严重度与证据质量，而不仅是 schema 能否通过。
6. Reviewer 自身升级后，是否会用未来版本 checker 追溯重判已经由用户批准并写入 attestation 的旧计划，从而破坏恢复与最终门禁。

revision 1 的 `STG-01` 已完成、正式审查通过并提交。开始 `STG-02` 前发现了自举漂移：当前 Executor preflight/final 会调用工作树中的 Planner checker，Planner 又调用工作树中的 Reviewer validator；若按原计划先替换 Reviewer receipt schema，revision 1 的不可变 plan-review receipt 会被未来 validator 拒绝。覆盖旧 receipt 会破坏 attestation，保留旧 parser 违反 current-only 目标，因此该问题必须通过 revision 2 amendment 修复，不能作为普通测试调整绕过。

非目标（Non-goals）：

- 不新增 `security-review`、`architecture-review` 或第三个通用 profile。
- 不让 Reviewer 修改被审目标、运行目标程序/测试、执行 `codex exec`、调用模型/子代理、访问网络或写 Git/远端平台。
- 不把所有语言、框架、OWASP ASVS 条目或 22 种设计模式塞入 `SKILL.md`。
- 不保留旧 receipt 的 schema version、兼容 parser、转换器、双写或 v1/v2 文档分支。
- 不构建后台服务、数据库、索引、缓存、长期驻留进程或在线审查平台。
- 不修改 `gitlab-pat-ops`、`process-manager`、`electron-ui-verifier` 等其它业务 skill 的行为。
- 不让 execution-time preflight/final 重新解释已经批准的 plan 语义，也不增加 grandfather、schema version 或 task-specific bypass。
- 不在本规划阶段实施 Skill 代码、生成执行状态或创建 Git 提交。

约束（Constraints）：

- 继续遵守 Planner、Reviewer、Executor 的 producer/reviewer/executor ownership 和显式授权边界。
- 语义专业化必须通过渐进披露和风险触发实现，普通小变更不能被全领域清单拖慢。
- positive claim、finding、verification gap 与 clean verdict 都必须有可定位证据和真实 claim source。
- CI 只运行确定性、无网络、无 secrets、无 Agent、无目标执行的验证；fresh-context 观察由用户显式发起。
- Reviewer 公共契约、Planner approval adapter、Executor stage/final/ledger adapter 和批准信任时序必须在同一阶段切换，半新半旧状态不得成为可恢复或可提交中间态。

待确认项（Open uncertainties）：无批准前阻塞项。真实语义 recall/false-positive 仍需实现后 observation 才能声明，未执行独立观察时必须报告 `not_observed`，不能伪造结论。

## 需求与验收（Requirements And Acceptance）

功能需求：

| ID | Priority | Requirement |
| --- | --- | --- |
| REQ-01 | must | Reviewer 对外仍只有 `plan-review` 与 `code-review`，保持只读目标和无自动 Agent/网络/目标执行边界 |
| REQ-02 | must | `plan-review` 专业检查完整性、一致性、清晰度、范围/YAGNI、可实施性和 plan-mandated defect |
| REQ-03 | must | `code-review` 先证明 spec compliance，并区分 missing、extra、misunderstood 实现 |
| REQ-04 | must | 通过风险 screen 条件化启用安全隐私、并发完整性、性能资源、API 数据兼容、UI 可访问性国际化、删除依赖六类 playbook |
| REQ-05 | must | 引入 closed review brief、独立 context target 和 bounded review package，固定目标、要求、规范、证据和 named-risk 扩展 |
| REQ-06 | must | coverage、evidence-bound strengths 与 verification gaps 成为 receipt 一等字段并参与 verdict 派生 |
| REQ-07 | must | finding 增加 category/origin、严重度校准、触发条件、影响、定位、修复方向和 claim source 约束 |
| REQ-08 | must | superseding attempt 必须逐项交代前序 finding，禁止 finding 无 lineage 地消失 |
| REQ-09 | must | validation evidence 区分 observed/reported/not-run，并绑定 target、context、attempt 和命令身份 |
| REQ-10 | must | Planner approval 与 Executor stage/final/ledger 原子消费新 Reviewer 契约，不保留旧分支 |
| REQ-11 | must | 新增 clean/near-miss/known-defect 语义 corpus、deterministic oracle、same-context smoke 和用户可运行 observation packet |
| REQ-12 | must | 同步三平台 CI、README、CHANGELOG、安装发现、静态评估和跨 Skill lifecycle 回归 |
| REQ-13 | must | Planner semantic approval 只在 attestation 写入或 amendment 激活前由当时的 current checker 执行；执行期以 attestation 的不可变哈希集合为批准事实，不被未来 checker 追溯重判 |

非功能需求：

| ID | Requirement |
| --- | --- |
| NFR-01 | 确定性脚本使用 Python 3 标准库，canonical JSON 与 SHA-256 在 Windows、Linux、macOS 一致 |
| NFR-02 | 路径越界、context stale、coverage 缺失、lineage 断裂、secret 或 package 超限一律 fail closed |
| NFR-03 | `SKILL.md` 保持精炼，profile 和风险细则按需加载，避免入口复制长清单 |
| NFR-04 | 不增加服务、数据库、缓存、模型运行时或第三方运行依赖，并以有界 package 控制成本 |
| NFR-05 | 当前契约直接替换旧格式，不设置 schema 版本或兼容层 |
| NFR-06 | 所有结论明确 `read/observed/reported/inferred/not-verified` 边界，不夸大验证范围 |
| NFR-07 | target/context/package、schema validator、profile workflow、caller adapter、eval oracle 分层且各自高内聚 |
| NFR-08 | 只修改 ART-04 change map 批准范围，不制造无关格式化、重命名或行为 churn |
| NFR-09 | 自举迁移在旧批准栈可用时开始、在新批准与执行栈共同可用时结束；任一边界都不得依赖旧 schema fallback |

验收标准：

| ID | Requirement IDs | Given / When / Then |
| --- | --- | --- |
| AC-01 | REQ-01 | Given 规划、代码或混合审查请求，When Reviewer 路由，Then 只选择两个既有 profile，混合范围被拆分/澄清，写目标或第三 profile 被拒绝 |
| AC-02 | REQ-02 | Given clean、known-defect、near-miss 计划，When plan-review，Then 关键完整性/一致性/范围/可实施性缺口被准确发现，纯措辞偏好不阻塞 |
| AC-03 | REQ-03 | Given 漏实现、额外实现、误解实现与 clean 代码样本，When code-review，Then requirement coverage 正确分类并给出定位证据 |
| AC-04 | REQ-04 | Given 不同风险触发面，When risk screen，Then 只加载适用 playbook；高风险静默跳过或无关全量检查均失败 |
| AC-05 | REQ-05 | Given target 不变但 brief、规范、验证日志或扩展路径改变，When 校验旧 receipt，Then context digest stale 并被拒绝 |
| AC-06 | REQ-06 | Given passed 或 blocked receipt，When 校验，Then coverage、strengths、gaps 与 verdict 一致，关键未覆盖不能藏在自由文本中 |
| AC-07 | REQ-07 | Given 偏好、维护建议、功能 bug 和安全/完整性风险，When 校准，Then severity、confidence、影响和证据符合规则 |
| AC-08 | REQ-08 | Given superseding receipt，When 前序存在 finding，Then 每个 finding 都有 resolved/still-open/superseded/invalidated disposition，否则拒绝 |
| AC-09 | REQ-09 | Given 旧日志、实现者自述、部分测试与当前确定性结果，When 绑定 validation evidence，Then claim source 和适用 target/attempt 真实可核验 |
| AC-10 | REQ-10 | Given managed plan，When approval check，Then 只接受当前 target/context、完整 coverage、无 blocking gap 的 passed `plan-review` receipt |
| AC-11 | REQ-10 | Given Executor stage/final，When review gate，Then wrong scope、stale context、lineage 丢失或 validation claim 漂移均不能完成阶段/任务 |
| AC-12 | REQ-11 | Given semantic corpus，When eval/observation，Then输出 recall、误报、severity、locator、evidence、gap honesty 和 provenance，未观察时明确 `not_observed` |
| AC-13 | REQ-12 | Given 任意 branch 的三平台 CI，When workflow 运行，Then unit、deterministic eval、static evaluation 与联合 lifecycle 都被发现并可重复执行 |
| AC-14 | REQ-01、REQ-05 | Given 大或敏感目标，When 构建 package/执行审查，Then 文件数/字节/路径/秘密预算生效，且 Agent、网络、目标执行计数保持零 |
| AC-15 | REQ-13 | Given 已由 current checker 通过并写入 attestation 的 revision，When Reviewer/Planner 后续升级或 Executor 恢复/final，Then 有效不可变哈希继续通过；缺失/无效 attestation 或任一批准文件漂移仍 fail closed，且新 attestation/amendment 在 current Planner approval 失败时不能写入或激活 |

详细的 Requirement → AC → STG → VAL → ART 闭环见 ART-06。

## 调研门禁（Research Gate）

Research mode：`online-required`。

触发原因：用户要求深入研究两个当前主流参考项目和更优秀审查规范；Google/OWASP 等公开规则、参考仓库维护状态与 ASVS 版本属于变化事实；本任务又会改变三个 Skill 的公共审查协议，因此不能只依赖模型记忆或单一二手总结。revision 2 另执行了 repository-grounded recovery research，逐调用链核对 attestation 写入、amendment 激活、Executor preflight/final 与 Reviewer validator 的时间边界。

研究证据与窗口：

| Source | Authority | Observation/window | Applicability and limit | Plan impact |
| --- | --- | --- | --- | --- |
| 本地 `sanyuan-skills` HEAD `08b657...` | primary repository snapshot | 观察日 2026-07-16；提交时间 2026-05-11 | 提供关键路径、架构/可靠性/删除审查启发；固定行数阈值和通用全量清单不适用 | 风险触发、错误/资源/删除 playbook |
| 本地 `superpowers` HEAD `d884ae...` | primary repository snapshot | 观察日 2026-07-16；提交时间 2026-07-02 | 提供 spec-first、fresh package、cannot-verify 和复审规则；自动 Agent/目标测试不适用 | coverage、package、gap、lineage |
| [Google Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html) | official primary guidance | 2026-07-16 页面快照；规则无版本承诺 | 适用于 code health、事实与偏好校准，不照搬内部流程术语 | severity 与 non-blocking preference |
| [Google What to Look For](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | official primary guidance | 2026-07-16 页面快照 | 适用于设计、功能、复杂度、测试、文档与专业能力边界 | coverage 与 specialist gap |
| [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/) | official versioned standard | 2025-05-30 stable；2026-07-16 核对 | 只在 Web/应用安全风险触发时引用，不把全部控制写入 Skill | security playbook 来源优先级 |
| [NIST SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) | official primary standard | 2022-02 发布；2026-07-16 核对 | 提供 SDLC 风险治理，不提供语言级 bug checklist | 高风险与供应链 review governance |
| 当前 `harness_attest_plan.py`、`harness_execution.py`、`harness_amendment.py` 调用链 | primary repository source | revision 1 STG-02 entry 前复核 | 证明 approval checker 已在 attestation write/amendment activation 执行，而 execution preflight/final 的重复调用会把未来工具版本错误变成旧批准失效 | approval-time trust boundary 与原子迁移顺序 |

初始本地基线为 Reviewer unit `30/30`、deterministic eval `11/11`。revision 1 已完成的 STG-01 现有证据为 unit `36/36`、deterministic eval `11/11`、oracle self-test 与 same-context smoke 通过，Agent/network/target execution 均为零；fresh-context 语义效果仍未观察，不能把结构或 same-context 通过夸大为独立专业审查效果。

方案影响：采用“spec compliance → 核心设计 → 全范围覆盖 → 条件风险 playbook”的顺序；新增双 snapshot、coverage、strength、gap、lineage 与 bounded package；语义评估分确定性 oracle 与用户显式 observation 两层。完整 query/source、适用限制、拒绝照搬项和饱和判断见 ART-01。

Research result：`passed`。

## 依赖选型门禁（Dependency Selection Gate）

本任务模式：`none`。

实现只扩展仓库现有 Python 标准库 CLI、Markdown/JSON contract、unittest/eval 和 GitHub Actions，不新增、替换、升级或关键保留第三方依赖，因此不虚构 DEP 决策，也不需要 dependency artifact。

若实施发现标准库无法安全完成 canonical JSON、SHA-256、bounded file traversal 或跨平台路径处理，必须触发 Plan Amendment Gate，重新执行必要性、项目适配、稳定版本、采用规模、更新时间、维护活跃度、趋势、安全与许可门禁；不能在阶段内临时安装包。

Dependency selection result：`not-applicable`。

## 规范发现门禁（Standards Discovery Gate）

Discovery mode：`online-required`。

技术与规范清单：

| Layer | Applicable authority | Decision impact |
| --- | --- | --- |
| 仓库规则 | 根 `AGENTS.md`、当前 Planner/Reviewer/Executor contracts | 中文新增注释、最小相关改动、真实验证、显式授权、不可变计划 |
| Skill 设计 | 系统 `skill-creator` progressive disclosure 与静态验证约束 | `SKILL.md` 只做路由/边界，专业细则下沉 references，不自动运行 Agent |
| Python | [PEP 8](https://peps.python.org/pep-0008/) 与仓库现有 stdlib 风格 | 可读模块、明确异常、跨平台路径、无无关格式化 |
| 通用审查 | Google Engineering Practices 四篇 official guidance | code health、核心设计优先、完整范围、why、偏好不阻塞、专家边界 |
| 应用安全 | OWASP ASVS 5.0.0、项目 threat model/框架规范 | 条件化 security playbook，版本化 requirement 优先于通用模式 |
| 安全治理 | NIST SSDF 1.1 | 高风险与供应链场景纳入 SDLC 证据，不伪装语言级规则 |
| 本地契约 | closed JSON、canonical digest、stable error、三 Skill adapter | current-only 原子切换、fail closed、单一 validator |
| 批准时序 | 当前 attestation、amendment 与 execution state machine | current checker 在批准边界运行；批准后由 immutable hashes 固定事实，未来 checker 不追溯改写历史 |

冲突优先级：用户/项目明确需求 > 仓库与目标项目规范 > 版本化官方标准/语言框架规范 > Google/OWASP/NIST 通用指导 > 参考 Skill 启发。参考仓库热度不构成规范权威；OWASP 2017 Code Review Guide 只保留人工审查必要性的背景，不作为当前漏洞分类。

适用限制与验证影响已落盘 ART-02；它把每个来源映射到 profile/risk playbook、测试或文档，明确 `not-applicable` 不能只写“无问题”。

Standards result：`passed`。

## 开发质量门禁（Development Quality Gate）

质量范围：

| Dimension | Design decision | Stage / validation |
| --- | --- | --- |
| 代码标准 | 保持 Python stdlib、closed object、稳定错误码、原子写入与中文设计注释 | STG-02；VAL-01/VAL-13 |
| 架构边界 | target、context、package、contract、workflow、adapter、oracle 分层；package 只是阅读视图 | STG-01..04；VAL-01/VAL-08/VAL-14 |
| 低耦合 | Planner/Executor 只传 brief/context 并消费 validator，不复制审查 rubric；execution-time 只消费 attestation，不反向依赖未来 Planner checker | STG-02/03；VAL-04..08 |
| 高内聚 | 六类 risk playbook 独立 reference，calibration/lineage/schema 各有唯一权威 | STG-01/02；VAL-01/VAL-09 |
| 设计模式 | Value Object + Builder + Policy/Gate + Adapter + Immutable Receipt；不引入通用规则引擎 | ART-03；VAL-01/VAL-14 |
| 错误处理 | unreadable/out-of-root/stale/missing coverage/broken lineage/secret/oversize 返回稳定 REVIEW 错误；缺失/无效 attestation 或批准文件漂移继续 fail closed | STG-02/03；VAL-01/04/06/08 |
| 性能 | bounded package 限制路径、文件数和字节；named-risk 才扩展上下文；不做全仓库默认扫描 | STG-02；VAL-01/VAL-12 |
| 可测试性 | deterministic contract/oracle 与人工 observation 分离，clean/near-miss 控制误报 | STG-04；VAL-02/03/10/11 |

SOLID 与模式只作为设计评估工具，不要求机械使用全部原则或 22 种模式。新增 abstraction 必须消除真实重复、固定职责边界或支持可验证合同；否则保留直接函数和数据结构。

过度设计防护：不增加 profile、在线服务、规则 DSL、插件注册中心、永久知识索引、自动专家 dispatch、通用评分总分或旧 schema 兼容层。`review package` 不成为第二真相源，validator 始终重建 target/context。

Development quality result：`passed`。

## 上下文（Context）

本地现状：

- `skills/complex-coding-reviewer` 已有 `SKILL.md`、四份核心 references、target/validate/render CLI、closed contract、30 项 unit tests 与 11 项 deterministic eval。
- Planner approval 和 Executor stage/final 已依赖 Reviewer 公共 validator，适合通过 adapter 原子升级，而不是重新创建第四套门禁。
- `harness_attest_plan.py write` 与 `activate-amendment` 已在批准边界调用 current Planner approval checker；attestation 已保存 task/revision、用户授权与全部 approval-included 文件的路径、大小和 SHA-256。重复在 execution preflight/final 运行未来 checker 没有增加文件完整性，只引入时间耦合。
- revision 1 已归档到 `artifacts/amendments/revision-0001`；STG-01 完成语义与引用定义保持不变，可由 amendment carry 校验器证明继承，STG-02 未产生源码改动且不得 carry。
- 当前 target digest 不包含要求、规范、调用方、验证日志等 context；supersedes 不逐 finding accounting；limitations 无结构化 owner/blocking；eval 不观察语义质量。
- `skill-evaluation-lab` 可以做 static contract 和用户工作流，但不得自动执行 Codex/模型；本任务只在 observation import 表达不足时做最小适配。

用户约束：深入研究 Sanyuan、Superpowers 和更优秀规范；提高专业程度；由 Planner 落盘详细方案；当前只规划，不实施；不需要兼容旧 Reviewer 契约。

证据等级：

| Claim | Level | Evidence | Consequence |
| --- | --- | --- | --- |
| 当前 schema/target/validator 行为 | read + confirmed | Reviewer source、STG-01 后 36 unit、11 eval、formal stage receipt | 作为回归基线，不推测 |
| 两个参考项目规则 | primary local snapshot | 固定 HEAD 与相关 Skill 文件 | 只吸收适合当前边界的流程 |
| Google/OWASP/NIST 规则 | official/primary online | 2026-07-16 URL observation | 为校准与风险 playbook 提供权威来源 |
| 语义效果尚未证明 | confirmed negative evidence | eval 的 `semantic_review_quality_observed=false` | REQ-11 必须是正式交付门，不得只补文案 |
| 独立 fresh-context 效果 | not observed | 需用户后续显式运行 observation packet | 不阻塞实现，但限制效果声明 |
| execution-time 重跑 current Planner checker 会破坏旧批准 | read + reproduced from call graph | `harness_execution.py` preflight/final、`harness_attest_plan.py` write/activate、revision 1 immutable receipt | revision 2 必须把 semantic approval 固定在 attestation 边界 |

任务证据索引：研究 ART-01、规范 ART-02、专业契约 ART-03、变更边界 ART-04、验证策略 ART-05、追踪矩阵 ART-06、正式计划审查 ART-07、自举漂移与修订决策 ART-08。

## 候选方案（Options）

### 方案 A：只扩充专业审查文档

- 做法：在现有 `plan-review.md` 和 `code-review.md` 增加 Sanyuan、Superpowers、Google 与 OWASP 的检查项。
- 优点：实现量小，Reviewer 使用者能立即看到更多专业提示。
- 缺点：context freshness、requirement coverage、verification gap、finding lineage 和 semantic evaluation 仍不可机器验证；清单越长，普通变更噪音越大。
- 主要风险：效果依赖 Agent 临场发挥，无法证明“查到了问题”而非“写了更多规则”。
- 回滚：删除新增文档段落，不影响当前合同。

### 方案 B：只升级 receipt schema 和 validator

- 做法：给 receipt 增加 coverage、gap、strength、lineage 字段，并更新 Planner/Executor 校验。
- 优点：结构闭合、stale 与谱系更强，容易做负向 unit fixture。
- 缺点：没有 review brief、风险工作流、专业校准和语义 corpus，字段可能沦为格式填充；无法证明 Agent 正确识别 missing/extra/misunderstood 或专业风险。
- 主要风险：结构通过率提高，但实际审查质量没有可观测提升。
- 回滚：三个 Skill 必须整体回退，不能只回退调用方。

### 方案 C：专业工作流、证据契约与语义评估分层升级

- 做法：先冻结双 profile 专业语义和风险触发，再建立 target/context 双快照、coverage/gap/lineage 合同和 bounded package；随后原子适配 Planner/Executor；最后用 deterministic oracle、same-context smoke 和用户显式 observation 分层验证效果。
- 优点：同时提升审查方法、事实约束、复审可靠性和效果可观测性；普通目标通过 brief/defaults 保持有界；不需要自动 Agent 或服务。
- 缺点：跨三个 Skill、eval 和 CI，属于 current-only breaking change；合同切换阶段必须完整且验证量较大。
- 主要风险：字段/流程过重、semantic oracle 过拟合、调用方半切换。通过复杂度预算、near-miss、联合回归和阶段原子提交控制。
- 回滚：STG-01 已形成独立完成边界；Reviewer 公共合同与所有调用方只允许按 revision 2 的 STG-02 原子边界整体回退，不引入兼容层。

### revision 2 自举迁移选项

- **每次 execution preflight/final 重跑工作树 current checker**：能观察当前规则，但把已批准事实绑定到未来代码，Reviewer 自升级后旧 receipt 必然失效，拒绝。
- **保留旧 schema parser、版本分支或当前任务豁免**：能暂时恢复，但违反 current-only、扩大长期测试矩阵，也允许历史旁路，拒绝。
- **批准时校验、执行时验证 attestation**：attestation write 与 amendment activation 在写入前运行当时的 current Planner checker；之后 preflight/final 只验证 task/revision、授权、approval-included 文件集合/大小/SHA-256 和运行态。该方案保持新批准 fail closed，同时避免未来 checker 追溯重判历史，选用。

## 决策（Decision）

选择方案 C。

决策原因：本次核心问题不是“缺少更多 review 关键词”，而是专业判断没有独立 coverage、上下文和复审证据，也没有语义效果门。方案 A 无法防止静默漏审，方案 B 无法证明字段内容正确；只有方案 C 同时闭合 workflow、contract、caller 和 evaluation。

关键设计决定：

1. **双 profile 稳定**：领域专业化通过六类条件化 risk playbook 组合，不扩大顶层路由。
2. **双快照**：primary target 表示被审对象，context target 表示要求、规范、验证证据和 named-risk 扩展；任一变化都使 receipt stale。
3. **brief 是输入合同**：调用方声明要求、scope、baseline、验证证据和风险，不允许 Reviewer 从实现者总结推导全部意图。
4. **package 只优化阅读**：commit/stat/diff 或 plan/file package 有界、可重建、不承载 canonical verdict。
5. **coverage 与 gaps 参与 verdict**：关键 requirement 未覆盖、blocking gap、前序 finding 未交代都不能 passed。
6. **current-only**：schema、fixtures、Planner、Executor、README 和 CI 同步替换，不设置版本字段或 fallback。
7. **语义声明分层**：CI 证明结构、oracle 与 fixtures 可重复；same-context smoke 观察当前实现；fresh-context 只有用户显式运行后才能声明。
8. **批准事实有时间边界**：current Planner/Reviewer checker 负责“现在是否可批准”，attestation 负责“当时批准了哪些不可变字节与权限”；Executor 恢复和 final 不用未来规则重写历史。Reviewer 公共 schema 与 Planner/Executor 所有消费者在 STG-02 同一原子迁移边界切换。

放弃的内容：固定函数行数阈值、全目标强制安全清单、P0-P3 重命名、Reviewer 直接修复、自动 subagent/模型选择、Reviewer 运行 focused tests、礼貌性固定 strengths 数量。

## 影响面矩阵（Impact Matrix）

| Surface | Current issue | Planned change | Compatibility | Owner |
| --- | --- | --- | --- | --- |
| Reviewer entry | 双 profile 有边界但专业触发不清 | brief/context/package/risk/observation 渐进入口 | current-only | Reviewer |
| plan workflow | lenses 较粗 | completeness/consistency/clarity/scope/buildability 与 plan-mandated defect | current-only | Reviewer |
| code workflow | correctness 没有 requirement proof | spec compliance first，核心设计后全范围与风险扩展 | current-only | Reviewer |
| receipt | 单 target、limitations 自由文本 | 双 digest、coverage、strengths、gaps、category/origin/lineage | breaking | Reviewer |
| target/context | context 不进 freshness | closed context manifest 与 SHA-256 | breaking | Reviewer |
| package | 重复 Git/文件读取，无边界快照 | bounded read-only package builder | additive, current contract only | Reviewer |
| Planner | 只校验旧 plan receipt | 生成 managed brief/context，attestation write/amendment activation 前由 current approval checker 校验新字段 | breaking | Planner adapter |
| Executor | stage/final 缺 validation/lineage binding，且 execution-time 重跑未来 Planner checker | stage/final brief、compact payload、feedback disposition；preflight/final 以 attestation hashes 为批准事实 | breaking | Executor adapter |
| eval | schema fixtures 为主 | deterministic semantic oracle + same/fresh observation | breaking fixtures | Reviewer eval |
| CI | 运行旧 suites | 三平台 current-only unit/eval/joint/static | workflow update | Repository |
| docs | 能力声明低于/高于证据风险 | 说明专业能力、只读边界、observation provenance | current-only | Repository |

详细文件级范围、明确不改项、原子切换顺序和回滚边界见 ART-04。

## 实施计划（Implementation Plan）

六个阶段构成单向 DAG：`STG-01 → STG-02 → STG-03 → STG-04 → STG-05 → STG-06`。任何阶段发现契约根因时，修复当前阶段并重新运行其全部 required validations；不得靠跳过平台、删除 near-miss 或保留旧 parser 绕过。

### STG-01 专业审查语义与渐进式工作流

目标：先定义 Reviewer 应如何判断，再修改数据合同。把参考项目和官方规范转化为两个 profile 的专业流程、六类 risk screen、severity/confidence calibration 与 truthful clean review 规则。

Stage contract：

- Depends on：无。
- Requirements：REQ-01、REQ-02、REQ-03、REQ-04、REQ-06、REQ-07。
- Acceptance：AC-01、AC-02、AC-03、AC-04、AC-06、AC-07。
- Nonfunctional：NFR-03、NFR-06、NFR-07。
- Validations：VAL-01、VAL-02、VAL-03、VAL-09、VAL-10、VAL-12。
- Allowed changes：`skills/complex-coding-reviewer/SKILL.md`、`skills/complex-coding-reviewer/references/plan-review.md`、`skills/complex-coding-reviewer/references/code-review.md`、`skills/complex-coding-reviewer/references/review-workflow.md`、`skills/complex-coding-reviewer/references/review-calibration.md`、`skills/complex-coding-reviewer/references/risk-playbooks.md`、`skills/complex-coding-reviewer/tests/**`、`evals/complex-coding-reviewer/**`。
- Forbidden changes：`third reviewer profile`、`automatic Codex, model, subagent, network or target execution`、`reviewer mutation of target code or plan`、`unconditional all-domain checklist`。
- Risk：`high`。
- Commit expectation：`stage`，仅在 attestation 明确包含 commit authorization 时执行。

进入条件：ART-01/02/03 决策已批准；当前 Reviewer unit/eval 基线可重现；两个 profile 和只读 writer 边界冻结。

实施步骤：

1. 精简 `SKILL.md` 为 profile 路由、brief/context/package 入口、只读/无 Agent 边界和按需 reference 导航。
2. `plan-review` 按意图、需求/验收、证据、选项、架构、阶段/验证、授权/回滚、scope/YAGNI 顺序审查。
3. `code-review` 先逐 requirement 标记 satisfied/missing/extra/misunderstood，再审核心设计、完整 diff/file 范围和 named risk。
4. 新增 calibration：技术事实优先于偏好；severity 由影响、触发面、范围、恢复性和 confidence 共同决定；plan 要求的缺陷仍是 finding。
5. 新增六类 playbook 的 trigger、invariant、evidence、common false positive、not-applicable reason 和 specialist gap。

退出条件：双 profile 流程无重复通用清单；clean/near-miss/defect 示例能区分事实与偏好；专业能力不足会生成 gap 而不是伪造 passed；Reviewer 仍不修改或执行目标。

### STG-02 Reviewer 合同、调用方与批准时序原子迁移

目标：把 STG-01 的专业语义变成 closed、可重建、可 fail-closed 的 target/context/receipt contract，并在同一个 current-only 边界切换 Reviewer 公共 validator、Planner approval、Executor stage/final/ledger 和 attestation 信任时序。该阶段吸收 revision 1 原 STG-03 的生产切换职责，避免 Reviewer 先升级后调用方无法正式审查、恢复或 amendment。

Stage contract：

- Depends on：STG-01。
- Requirements：REQ-01、REQ-04、REQ-05、REQ-06、REQ-07、REQ-08、REQ-09、REQ-10、REQ-13。
- Acceptance：AC-04、AC-05、AC-06、AC-07、AC-08、AC-09、AC-10、AC-11、AC-14、AC-15。
- Nonfunctional：NFR-01、NFR-02、NFR-04、NFR-05、NFR-06、NFR-07、NFR-09。
- Validations：VAL-01、VAL-02、VAL-04、VAL-05、VAL-06、VAL-07、VAL-08、VAL-12、VAL-13。
- Allowed changes：`skills/complex-coding-reviewer/references/review-contract.md`、`skills/complex-coding-reviewer/scripts/**`、`skills/complex-coding-reviewer/templates/**`、`skills/complex-coding-reviewer/tests/**`、`evals/complex-coding-reviewer/**`、`skills/complex-coding-planner/**`、`evals/complex-coding-planner/**`、`skills/complex-coding-executor/**`、`evals/complex-coding-executor/**`。
- Forbidden changes：`legacy receipt compatibility parser, schema version, dual read or dual write`、`execution-time rerun of mutable Planner or Reviewer approval checker`、`partial public schema switch before every caller is ready`、`review package treated as canonical freshness source`、`unbounded workspace traversal or secret capture`、`finding disappearance without lineage disposition`、`Planner or Executor copy of professional review rubric`。
- Risk：`high`。
- Commit expectation：`stage`，仅在 commit 单独获批时执行。

进入条件：revision 2 获用户重新批准并通过 amendment activation carry STG-01；revision 1 archive 完整；旧版 Planner/Reviewer approval stack 已在新 attestation 写入与激活前通过；STG-02 尚无源码改动；root/path/canonical JSON、Planner artifact gate、Executor review/ledger 与 attestation 调用图已读。

实施步骤：

1. 先修改 Executor 批准信任时序：保留 attestation write 与 amendment activation 对 current Planner approval checker 的调用；execution preflight/transition/final 改为验证 current attestation、approval-included immutable hashes、dependency runtime gate 与 replay state，不再重跑未来 checker。
2. 为批准时序补负例：current approval 失败时不得写 attestation 或激活 amendment；有效 attestation 在 checker 实现变化后仍可恢复/final；缺失/无效 attestation、task/revision 错配及 plan/contract/approval artifact 漂移继续 fail closed。
3. 建立 closed review brief 和 context manifest，context 只引用/摘要必要要求、规范、验证和扩展路径，不复制秘密内容；package builder 限制 root、路径、文件数、单文件/总字节和敏感文件模式。
4. receipt 根契约增加 `context`、`coverage`、`strengths`、`verification_gaps`；finding 增加 category/origin lineage；`supersedes` 强制前序 finding accounting。
5. 在一次 public switch 中同步 Reviewer validator/target/render、Planner managed-plan brief/context 与 approval adapter、Executor stage/final context、review compact payload、ledger/state schema 和全部 fixtures；删除旧字段、旧断言与 fallback。
6. validation evidence 记录 command identity、result/source、target/context/stage attempt 与 claim boundary；Reviewer 只消费证据或生成 gap，不运行命令。render 保持 findings-first 并显示 coverage、risk、gap、strength 与双 digest。
7. 依次运行 Reviewer、Planner、Executor unit/eval、cross-skill regression 与 static current-only 扫描；仅在三方共同通过后生成新版 STG-02 `stage-delta` receipt、写 ledger 并形成阶段提交候选。

退出条件：target 或 context 任一变化都稳定拒绝旧 receipt；关键 coverage/gap/lineage 不完整不能 passed；package 不被 validator 信任为真相源；Planner 新批准仍用 current checker；Executor 恢复/final 只信任有效 attestation hashes；新版 stage receipt 可被新版 ledger/state 原子消费；三 Skill 不存在半新半旧路径；Windows/Linux/macOS canonical digest fixture 一致。

### STG-03 自举恢复与跨 Skill 生命周期加固

目标：在 STG-02 已完成生产原子迁移的基础上，用恢复、amendment、篡改、stale、lineage 和 dependency runtime 负例证明新边界可长期运行；本阶段不再引入第二次 schema 切换。

Stage contract：

- Depends on：STG-02。
- Requirements：REQ-05、REQ-08、REQ-09、REQ-10、REQ-13。
- Acceptance：AC-05、AC-08、AC-09、AC-10、AC-11、AC-15。
- Nonfunctional：NFR-01、NFR-02、NFR-05、NFR-07、NFR-09。
- Validations：VAL-01、VAL-04、VAL-06、VAL-07、VAL-08、VAL-12、VAL-13。
- Allowed changes：`skills/complex-coding-reviewer/tests/**`、`skills/complex-coding-planner/tests/**`、`skills/complex-coding-executor/tests/**`、`evals/complex-coding-reviewer/**`、`evals/complex-coding-planner/**`、`evals/complex-coding-executor/**`、`skills/complex-coding-reviewer/references/review-contract.md`、`skills/complex-coding-reviewer/scripts/**`、`skills/complex-coding-reviewer/templates/**`、`skills/complex-coding-planner/**`、`skills/complex-coding-executor/**`。后五项只允许修复由本阶段回归直接证明的 STG-02 根因。
- Forbidden changes：`second review schema migration`、`production change without a failing STG-03 regression proving an STG-02 root cause`、`legacy review receipt fallback, dual write or schema branch`、`execution-time Planner checker dependency`、`weakening attestation immutable set or dependency runtime gate`、`unbound validation claim in Executor ledger`。
- Risk：`high`。
- Commit expectation：`stage`，恢复与联合回归作为独立加固提交候选。

进入条件：STG-02 新 Reviewer、Planner 与 Executor public contract 已共同通过并提交；stage review/ledger 使用新版 receipt 成功闭环；不存在旧字段或 compatibility path。

实施步骤：

1. 建立 bootstrap matrix：批准前 current checker 失败、批准后 checker 实现变化、immutable file 漂移、attestation 缺失/错 task/错 revision、snapshot 丢失与 ledger replay。
2. 覆盖 amendment archive/activate：current checker 失败发生在 attestation/runtime 轮换前；成功 activation 只能 carry 语义与完成证据均不变的 stage。
3. 覆盖 Reviewer target/context stale、supersedes finding accounting、validation claim source 与 Executor stage/final compact payload 的正负 lifecycle。
4. 证明移除 execution-time Planner checker 不会绕过 dependency runtime recheck；stale dependency evidence 仍由专用 gate 阻塞或生成 runtime receipt。
5. 扩展 cross-skill regression 与 deterministic eval，记录每个失败码和恢复下一步；禁止通过 mock 掉公共边界来声称端到端通过。
6. 只对回归揭示的 STG-02 根因做最小生产修复，并重跑 STG-02 与 STG-03 全部 validations。

退出条件：Planner 缺新 plan receipt 无法批准；Executor wrong scope/context/lineage/validation claim 无法完成 stage/final；有效历史 attestation 不受未来 checker 变化影响；批准文件篡改与新批准失败仍 fail closed；amendment carry、dependency runtime 和跨 Skill regression 没有旁路。

### STG-04 语义场景、校准与 observation 工作包

目标：让“专业审查效果”成为可观察能力，而不是从 schema 测试推断；同时严格禁止 Skill 自动启动 Codex、模型或子代理。

Stage contract：

- Depends on：STG-03。
- Requirements：REQ-02、REQ-03、REQ-04、REQ-06、REQ-07、REQ-08、REQ-11。
- Acceptance：AC-02、AC-03、AC-04、AC-06、AC-07、AC-08、AC-12。
- Nonfunctional：NFR-03、NFR-04、NFR-06、NFR-07。
- Validations：VAL-02、VAL-03、VAL-09、VAL-10、VAL-11、VAL-12。
- Allowed changes：`evals/complex-coding-reviewer/**`、`skills/complex-coding-reviewer/tests/**`、`skills/complex-coding-reviewer/references/review-calibration.md`、`skills/complex-coding-reviewer/references/risk-playbooks.md`、`skills/skill-evaluation-lab/**`、`evals/skill-evaluation-lab/**`、`.harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/artifacts/validation/**`。
- Forbidden changes：`automatic codex exec, model call or subagent dispatch`、`semantic score inferred only from schema validity or keyword matching`、`known-defect-only corpus without clean and near-miss controls`、`fresh-context claim without user-run provenance`。
- Risk：`medium`。
- Commit expectation：`stage`，仅提交确定性 harness、fixtures 和工作流，不提交伪造 observation。

进入条件：三 Skill 已消费 current contract；semantic scenario 的 expected/forbidden findings、severity 和 locators 由计划证据校准；Skill Evaluation Lab 现有边界已复核。

实施步骤：

1. 将 deterministic eval 拆为 contract cases 与 semantic scenario/oracle；oracle 评分 expected/forbidden finding、severity、locator、evidence、gap honesty。
2. corpus 至少覆盖 clean、near-miss、known-defect 的 plan/code 双 profile，并包含 missing/extra/misunderstood、风险触发、stale context 和 lineage。
3. 当前 Executor Agent 按新工作流执行 same-context smoke，receipt 保留真实 provenance；不得把它标记为 independent/fresh。
4. 生成用户可显式在独立任务中运行的 observation packet，包含固定 target/context、步骤、结果 import schema 与 provenance；Skill 自身不启动 Agent。
5. 报告 deterministic pass、semantic observed 与 fresh-context observed 三层状态；缺任一层时只限制对应声明，不篡改其它结果。

退出条件：CI 可重复验证 oracle 与 fixtures；same-context 报告有真实 receipt；observation packet 静态闭合且无自动执行入口；误报和漏报指标可定位到 case。

### STG-05 三平台 CI、文档与 current-only 收口

目标：让新能力在所有普通分支、三个 OS、安装发现和公共说明中一致可见，并清除旧合同术语。

Stage contract：

- Depends on：STG-04。
- Requirements：REQ-01、REQ-10、REQ-11、REQ-12、REQ-13。
- Acceptance：AC-01、AC-10、AC-11、AC-12、AC-13、AC-14、AC-15。
- Nonfunctional：NFR-01、NFR-03、NFR-04、NFR-05、NFR-08、NFR-09。
- Validations：VAL-08、VAL-09、VAL-11、VAL-12、VAL-13。
- Allowed changes：`.github/workflows/planner-executor.yml`、`README.md`、`CHANGELOG.md`、`skills/complex-coding-reviewer/**`、`skills/complex-coding-planner/**`、`skills/complex-coding-executor/**`、`evals/complex-coding-reviewer/**`、`evals/complex-coding-planner/**`、`evals/complex-coding-executor/**`、`skills/skill-evaluation-lab/**`、`evals/skill-evaluation-lab/**`。
- Forbidden changes：`branch filters that skip ordinary branches`、`CI secrets, network, Agent or target application execution`、`old receipt terminology or compatibility documentation`、`unrelated skill behavior or repository-wide formatting`。
- Risk：`high`。
- Commit expectation：`stage`，CI/docs/current-only cleanup 形成独立候选。

进入条件：STG-04 deterministic suites 通过；workflow 当前 job/OS/branch contract 已读；公共文档的能力声明与 observation 边界已确认。

实施步骤：

1. 更新现有 all-branch Windows/Ubuntu/macOS workflow，运行 Reviewer/Planner/Executor unit、deterministic eval、joint regression 与 static skill evaluation。
2. CI 明确不运行 VAL-10 的 Agent 语义审查和用户 fresh-context observation，不读取 secrets、不访问网络、不启动目标应用。
3. README/CHANGELOG 说明双 profile、spec-first、context freshness、risk/gap/lineage、current-only breaking contract、approval-time checker/execution-time attestation 边界和用户 observation 方法。
4. 静态扫描旧 receipt 字段、旧 payload、schema version/fallback、过时文档声明与自动 Agent 入口。
5. `skill-evaluation-lab` 仅在 observation packet/import 现有契约不足时最小适配，并运行其原有 tests/evals 防回归。

退出条件：三个 OS 的本地等价命令可运行；普通 branch 不被过滤；静态扫描无旧术语；文档声明不超过 deterministic/same-context/fresh-context 实际证据。

### STG-06 最终集成审查、回归与交付

目标：在当前完整 target 上运行所有 required validations 和 `code-review/final-integration`，确认跨阶段交互、边界和文档真实后再交付。

Stage contract：

- Depends on：STG-05。
- Requirements：REQ-01、REQ-02、REQ-03、REQ-04、REQ-05、REQ-06、REQ-07、REQ-08、REQ-09、REQ-10、REQ-11、REQ-12、REQ-13。
- Acceptance：AC-01、AC-02、AC-03、AC-04、AC-05、AC-06、AC-07、AC-08、AC-09、AC-10、AC-11、AC-12、AC-13、AC-14、AC-15。
- Nonfunctional：NFR-01、NFR-02、NFR-03、NFR-04、NFR-05、NFR-06、NFR-07、NFR-08、NFR-09。
- Validations：VAL-01、VAL-02、VAL-03、VAL-04、VAL-05、VAL-06、VAL-07、VAL-08、VAL-09、VAL-10、VAL-11、VAL-12、VAL-13、VAL-14。
- Allowed changes：`all files approved by ART-04 and STG-01 through STG-05`、`task-local execution, validation, review and observation artifacts`、`minimal fixes required by final review within approved scope`。
- Forbidden changes：`new feature scope, third profile or compatibility layer`、`automatic remote push, external write, Agent or target execution`、`claiming semantic or fresh-context success without matching evidence`、`commit without explicit authorization`。
- Risk：`medium`。
- Commit expectation：`final`，只在 attestation 同时证明 implementation 与 commit 均获批时创建。

进入条件：STG-05 完成；无开放 blocking/major stage finding；working tree 仅含 ART-04 批准范围和任务证据；所有 validation command 可重建。

实施步骤：

1. 从干净、明确的 baseline 重跑 VAL-01 至 VAL-13，保存命令、退出码、计数和 evidence digest。
2. 生成 final-integration brief/target/context/package，运行 Reviewer 并以 VAL-14 校验 receipt；任何 finding 修复后生成新不可变 attempt。
3. 检查 requirement/AC/NFR/validation coverage、前序 finding lineage、context freshness、attestation immutable hashes、approval-time/execution-time 调用边界、旧术语清理和跨平台路径。
4. 汇总 deterministic、same-context 与 fresh-context 三层证据；用户未运行 fresh observation 时明确保留 `not_observed`。
5. 仅在显式 commit authorization 存在时按仓库规范提交；外部 push 始终不在本计划默认授权内。

退出条件：所有 required validation 通过；final receipt 为当前 target/context 的 passed 且无 blocking gap；`git diff --check` clean；交付说明准确列出验证、未运行项和 residual risk。

## 环境（Environment）

| Item | Planning observation | Implementation rule |
| --- | --- | --- |
| Workspace | `D:/Item/vibe_coding/dev-skills` | Executor 启动时重新解析 canonical workspace，不依赖硬编码盘符 |
| Current shell | PowerShell on Windows | 脚本本身必须使用 Python stdlib 跨平台；文档命令避免仅 PowerShell 可用语义 |
| Python | `3.13.12` at planning time | 支持仓库当前 Python baseline；CI 在各 OS 使用 workflow 受控版本 |
| Git branch | `harness/feature` | 实施前重新读取 branch/HEAD/status，发现漂移按 Executor preflight 处理 |
| Planning HEAD | `964fe1920390da160ba9e943ec26686bc446b35c` | 只是规划快照，不是批准后的永久 baseline；attestation 固定实际执行 baseline |
| External references | 两个只读本地参考仓库和官方在线页面 | 实施不写参考仓库，不依赖在线服务运行 |
| Secrets | 本任务不需要 | package/CI 禁止读取 PAT、tokens、`.env` 或 secret files |

稳定环境事实可继续使用 `.harness/environment.md`，但其中任务状态不能替代当前 task bundle、active pointer 或 Executor run-state。

## Git 上下文（Git Context）

规划时 `git status --short` 包含当前 task bundle 和既有 `.harness/active-task.json` 删除状态。Planner 不回滚未知或既有工作区变更；active pointer 在 approval checker 通过后由 `harness_active_task.py` 按四态规则原子激活。

实施 preflight 必须：

1. 记录实际 branch、HEAD、status 和 scoped diff，区分 task bundle、用户变更与本任务实现。
2. 不使用 `git reset --hard`、`git checkout --` 或其它破坏性恢复；遇到相关用户变更时在批准 scope 内协作处理。
3. 同仓库 Git 命令串行；stage commit 只表示候选原子边界，不等同 commit authorization。
4. 不自动 push、创建远端 ref、PR/MR 或写 issue；这些属于单独 external write 授权。
5. 最终审查 target 必须包含实际批准 baseline 到当前工作树/提交的完整 integration 范围。

## 工具（Tooling）

| Tool | Purpose | Boundary |
| --- | --- | --- |
| `apply_patch` | 定点修改 Markdown、Python、JSON/YAML 与 tests | 避免整文件无关重写；大文件按完整模块/章节分段 |
| Python `unittest` | Reviewer/Planner/Executor/Skill Lab unit | `-B` 禁止 bytecode 写入；不得因平台差异隐藏逻辑失败 |
| deterministic eval runners | contract、semantic oracle、cross-skill lifecycle | 不访问网络、不调用 Agent、不执行目标程序 |
| Reviewer public CLI | target/context/package 构建、receipt 校验与 render | 只写显式 artifact root，不写被审目标 |
| Skill Evaluation Lab | static contract 与 observation packet 工作流 | 不执行 `codex exec`、模型或用户未发起的独立任务 |
| Git | status/diff/diff-check/可选 commit | 无显式授权不得 commit/push；不使用破坏性命令 |
| GitHub Actions | Windows/Ubuntu/macOS contract | 所有普通 branch 执行；无 secrets、网络依赖和目标 app |

工具不可用、权限失败或输出不满足稳定 JSON/退出码合同时必须记录真实失败，不能改成静默 skip。需要提权时先触发授权门，不把本地权限问题伪装成代码通过。

## 长期进程管理（Process Manager Gate）

本任务不需要长期进程、后台服务、Electron 应用、Web server、watcher 或端口。所有 validation 都应为有界 CLI 并在命令退出时释放文件句柄和临时目录。

若实施意外需要驻留服务或目标应用，立即触发 amendment；必须改用 `process-manager` 的统一外部接口并为 start/status/logs/stop/cleanup 定义闭环，不能用裸后台命令。

Process Manager result：`not-applicable`。

## 验证（Validation）

完整 case 设计、semantic metrics、CI contract 和失败处理见 ART-05。以下 14 项与 `plan-contract.json` 一致，required validation 的证据由 Executor 写入任务目录；命令中的任务路径固定为本 task bundle。

| ID | Kind | Required | Command / method | Evidence path |
| --- | --- | --- | --- | --- |
| VAL-01 | test | yes | `python -u -X utf8 -B -m unittest discover -s skills/complex-coding-reviewer/tests -p test_*.py -v` | `artifacts/validation/reviewer-unit-tests.txt` |
| VAL-02 | test | yes | `python -u -X utf8 -B evals/complex-coding-reviewer/run_evals.py --output .harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/artifacts/validation/reviewer-evals.json` | `artifacts/validation/reviewer-evals.json` |
| VAL-03 | test | yes | `python -u -X utf8 -B evals/complex-coding-reviewer/run_semantic_oracle.py --self-test --output .harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/artifacts/validation/reviewer-oracle-self-test.json` | `artifacts/validation/reviewer-oracle-self-test.json` |
| VAL-04 | test | yes | `python -u -X utf8 -B -m unittest discover -s skills/complex-coding-planner/tests -p test_*.py -v` | `artifacts/validation/planner-unit-tests.txt` |
| VAL-05 | test | yes | `python -u -X utf8 -B evals/complex-coding-planner/run_evals.py --output .harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/artifacts/validation/planner-evals.json` | `artifacts/validation/planner-evals.json` |
| VAL-06 | test | yes | `python -u -X utf8 -B -m unittest discover -s skills/complex-coding-executor/tests -p test_*.py -v` | `artifacts/validation/executor-unit-tests.txt` |
| VAL-07 | test | yes | `python -u -X utf8 -B evals/complex-coding-executor/run_evals.py --output .harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/artifacts/validation/executor-evals.json` | `artifacts/validation/executor-evals.json` |
| VAL-08 | test | yes | `python -u -X utf8 -B evals/complex-coding-executor/cross_skill_regression.py --include-reviewer --work-dir .harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/tmp/cross-review --output .harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/artifacts/validation/cross-review.json` | `artifacts/validation/cross-review.json` |
| VAL-09 | review | yes | `python -u -X utf8 -B skills/skill-evaluation-lab/scripts/se_check.py --workspace . --candidate skills/complex-coding-reviewer --output .harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/artifacts/validation/reviewer-static.json` | `artifacts/validation/reviewer-static.json` |
| VAL-10 | review | yes | 当前 Executor Agent 按新版 `complex-coding-reviewer` 对 seeded plan/code corpus 执行 same-context semantic smoke，并用 `run_semantic_oracle.py` 评分；不得启动其它 Agent | `artifacts/validation/semantic-smoke-report.json` |
| VAL-11 | test | yes | `python -u -X utf8 -B evals/complex-coding-reviewer/run_observation_packet.py --validate-only --output .harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/artifacts/validation/observation-packet-validation.json` | `artifacts/validation/observation-packet-validation.json` |
| VAL-12 | lint | yes | `python -u -X utf8 -B evals/complex-coding-reviewer/run_evals.py --static-contract-only --output .harness/tasks/2026-07-16/feature/complex-coding-reviewer-professionalization/artifacts/validation/reviewer-static-contract.json`，并拒绝旧 receipt/payload、自动 Agent/网络/目标执行入口和超出 ART-04 的能力声明 | `artifacts/validation/reviewer-static-contract.json` |
| VAL-13 | lint | yes | `git -c diff.autoRefreshIndex=false diff --check`，并核对 changed paths 全部位于 ART-04 | `artifacts/validation/git-diff-check.txt` |
| VAL-14 | review | yes | 使用 `complex-coding-reviewer` 的 `code-review`、`final-integration` scope 对当前完整 target/context 生成并校验正式 receipt | `artifacts/reviews/final-integration-attempt-N.json` |

关键覆盖：

- VAL-01/02/03 覆盖 AC-01 至 AC-09、AC-12、AC-14 及 NFR-01 至 NFR-07 的 Reviewer 行为、负向合同和语义校准。
- VAL-04/05 覆盖 AC-02、AC-05、AC-06、AC-08、AC-10、AC-12、AC-15 与 Planner approval adapter。
- VAL-06/07/08 覆盖 AC-03、AC-05、AC-08、AC-09、AC-10、AC-11、AC-13、AC-15 与 Executor/联合 lifecycle，明确验证 approval-time checker、execution-time attestation、amendment carry 和 dependency runtime gate。
- VAL-09/11/12/13 覆盖 AC-01、AC-04、AC-10 至 AC-15 和 NFR-01 至 NFR-09 的结构、安装、CI、边界与 current-only 清理。
- VAL-14 最终覆盖全部 AC-01 至 AC-15 和 NFR-01 至 NFR-09，但不能替代前述专用验证。

失败规则：required validation 任一非零、证据不可读、target/context 不一致、semantic oracle contract 失真、blocking/major finding 或 blocking gap 未关闭时，stage/final 不得完成。用户未运行 fresh-context packet 不使 deterministic 实现失败，但最终必须明确 `fresh_context_observed=false`。

## 文档（Documentation）

- `skills/complex-coding-reviewer/SKILL.md`：只说明何时使用两个 profile、输入/输出、只读边界和按需 reference 路由。
- `review-contract.md`：唯一机器 contract、受控枚举、verdict 派生、freshness、lineage 与 stable errors。
- `plan-review.md` / `code-review.md`：profile 专业顺序，不复制 shared schema。
- `review-calibration.md` / `risk-playbooks.md`：severity/confidence、事实/偏好、specialist gap 与六领域按需规则。
- Planner/Executor docs：只描述 brief/context handoff、receipt validator、finding disposition 和批准时序；明确 current checker 只在 attestation write/amendment activation 前运行，execution preflight/final 校验 attestation hashes，不复制 Reviewer rubric。
- `README.md` / `CHANGELOG.md`：说明 current-only breaking contract、能力提升、无自动 Agent/目标执行和 observation 证据边界。

文档示例中的 URL、命令和字段必须对应当前实现；不加入永久库推荐、过时 OWASP taxonomy 或无法由测试/receipt 支持的效果宣称。

## 文件写入策略（File Write Strategy）

- 先读目标文件、调用方、fixtures 和目录级规则，再做局部 `apply_patch`；不整仓格式化或无关重排。
- 超过 500 行的文件先按完整模块/函数/章节划分 patch；不能从函数、JSON object、表格或 Markdown 代码块中间截断。
- STG-02 先落 Executor approval-time trust 修复和负例，再准备 Reviewer contract/builders；Reviewer public validator、Planner approval adapter、Executor stage/final/ledger adapter 作为同一原子切换完成并共同验证，不提交半新半旧工作树。
- JSON/YAML 使用结构化解析/序列化，禁止正则拼接 closed contract；生成 artifact 使用 temp + atomic replace 并处理 OSError/Unicode/JSON 错误。
- tests/evals 逐 capability 分文件，避免把 target、context、lineage、semantic oracle 全塞入一个超大测试模块。
- 不修改参考仓库，不在 `.codex/tmp` 写运行状态，不生成 `__pycache__`，不自动创建符号链接或启动进程。

## 问题和覆盖项（Questions And Overrides）

- 兼容策略：用户已明确不需要旧版兼容，采用 current-only 直接替换。
- Agent 策略：Skill 不自动执行任何 Codex/模型/子代理；VAL-10 是当前已授权 Executor Agent 的人工工作流，VAL-11 只验证用户可运行工作包。
- fresh-context：由用户后续显式发起，未运行时真实报告 `not_observed`，不虚构独立性，也不阻塞确定性实现交付。
- security 专业性：risk trigger 命中且当前 reviewer 能力不足时生成 specialist gap；不把通用启发式冒充完整安全审计。
- Skill Evaluation Lab：默认不改；只有现有 observation packet/import contract 无法表达新 evidence 时，才在 ART-04 范围内最小适配。
- Commit：revision 1 用户已明确授权阶段性/最终提交；revision 2 请求在重新批准时继续携带该授权。未获得 revision 2 reapproval 前，不写新 attestation、不激活 amendment，也不产生后续提交。

## 方案质量门禁（Plan Quality Gate）

Producer quality evidence：

1. ART-01 固定当前 Reviewer tree、两个参考仓库 HEAD、在线观察日期、实测 unit/eval 基线、适合吸收与拒绝照搬项。
2. ART-02 把项目规则、Skill 设计、Python、Google、OWASP、NIST 映射到具体 workflow/playbook/test，并定义冲突优先级。
3. ART-03 定义 brief、双 target、coverage、strength、gap、lineage、package、adapter、eval、approval-time trust 和复杂度预算；ART-04 把这些决定映射到实际文件与原子迁移顺序。
4. ART-05 使用 clean/near-miss/known-defect、批准时序/篡改/amendment 负例、三平台 CI 和 observation 分层验证；ART-06 证明所有 REQ/AC/NFR 都有 Stage 与 required VAL。
5. ART-08 固定 revision 1 自举漂移、拒绝绕过、选定修复和 carry 边界；方案没有新增 profile、依赖、服务或兼容层。

范围、阶段 DAG、验证、授权、回滚和 Executor 交接已经闭合；真实 fresh-context 效果被明确留作用户观察，不影响计划可实施性，也没有被夸大为已证明。

Quality result：`passed`。

## 正式方案审查（Formal Plan Review）

正式审查交给 `complex-coding-reviewer`，使用 profile `plan-review`、scope `managed-plan`。Reviewer 读取 canonical plan target，不修改 `execution-plan.md`、`plan-contract.json` 或 planning artifacts。

- Target：`artifacts/reviews/targets/plan-attempt-2.json`
- Canonical receipt：`artifacts/reviews/plan-review-attempt-2.json`
- Public validator：`skills/complex-coding-reviewer/scripts/review_validate.py`
- Required checks：目标 digest、profile/scope、provenance、全部 lenses、findings/open counts、limitations 与 verdict 派生一致性。
- Re-review：attempt 2 必须通过 `supersedes_review_id` 直属连接 revision 1 的 attempt 1；若目标因新 finding 修复而再次变化，继续保留历史、重建 target 并生成连续 attempt，不得覆盖旧 receipt。

计划正文不复制正式 verdict，唯一 canonical 结论由上述 JSON receipt 承载，approval checker 只消费公共 validator 的结果。

## 就绪门禁（Readiness Gate）

就绪依据：

- 目标、非目标、用户约束、current-only 边界和 no-Agent/no-target-execution 规则明确。
- Research、Standards、Development Quality、Dependency Selection 和 Plan Quality gates 均有 artifact、来源、适用限制和实施影响。
- 六阶段 DAG、allowed/forbidden scope、entry/exit、risk、commit expectation 与 14 项验证可以直接被 Executor 消费。
- 13 个 must requirement 均有 AC，全部 AC-01..15 与 NFR-01..09 均有 required validation；没有 unresolved research 或 blocking design decision。
- 正式 plan-review receipt 和 approval checker 通过后才请求 implementation，不提前创建运行状态或实施代码。

Readiness result：`ready_for_review`。

## 方案批准（Plan Approval）

本 revision 是执行中发现真实 drift 后的正式 amendment。Planner draft、attempt 2 formal plan-review 与 approval checker 通过后，向用户请求 revision 2 reapproval 并停止；用户批准前不得写 revision 2 attestation、激活 amendment 或继续 STG-02。

授权边界：

- Implementation：必须由用户显式重新批准 revision 2，并明确允许 carry `STG-01`。
- Commit：本 amendment 请求延续用户已明确授予的 stage/final commit 权限；仍必须写入 revision 2 attestation 后才生效。
- External write：push、PR/MR、issue/comment、远端 ref 等必须单独批准。
- Elevated tool：提权、GUI 或 sandbox 外写入必须单独批准。

批准 attestation 必须绑定 task ID、plan revision、approval-included artifact SHA-256 集合、授权 flags、时间和用户原文；Executor 负责生成，Planner 不预写。

## 方案变更门禁（Plan Amendment Gate）

以下任一变化必须停止当前 stage，形成新 plan revision、重新正式 plan-review 并请求 reapproval：

1. 新增第三个 review profile、改变 Reviewer 只读 writer 边界或允许自动 Agent/网络/目标执行。
2. brief、target/context digest、coverage、gap、severity/verdict、lineage 或 package canonical 语义发生实质变化。
3. Planner approval、Executor stage/final、ledger payload、Stage DAG、required validation 或 allowed/forbidden scope 发生变化。
4. 引入第三方运行依赖、后台服务、数据库、缓存、模型调用、secret、远端写入或提权要求。
5. 实现需要修改 ART-04 之外的其它 Skill 公共行为、保留旧契约兼容层或改变 CI branch/OS contract。
6. active task pointer 冲突、用户相关改动或 baseline 漂移无法按当前计划安全处理。
7. attestation write/amendment activation 与 execution preflight/final 的批准信任时序，或 immutable approval set 语义再次变化。

纯修复错字、同一 stage scope 内的测试 fixture/错误处理修复、以及不改变验收语义的内部函数拆分无需 amendment，但仍须记录于 ledger 并重跑该 stage required validations。

## Artifact Index

| ID | Kind | Path | Required | Approval included | Purpose |
| --- | --- | --- | --- | --- | --- |
| ART-01 | research | `artifacts/research/reviewer-professionalization-research.md` | yes | yes | 当前基线、参考项目、官方资料、缺口与研究饱和 |
| ART-02 | standards | `artifacts/standards/review-standards-index.md` | yes | yes | 技术栈、规范来源、优先级、适用限制与质量映射 |
| ART-03 | architecture | `artifacts/architecture/reviewer-professional-contract.md` | yes | yes | brief、双快照、receipt、coverage/gap/lineage、package、adapter、eval 设计 |
| ART-04 | architecture | `artifacts/architecture/change-map.md` | yes | yes | Reviewer/Planner/Executor/eval/CI 文件范围、原子顺序与回滚 |
| ART-05 | validation | `artifacts/validation/validation-strategy.md` | yes | yes | VAL-01..14、case corpus、metrics、CI 与失败处理 |
| ART-06 | other | `artifacts/traceability/traceability-matrix.md` | yes | yes | GOAL/REQ/AC/NFR/STG/VAL/ART 闭环与风险追踪 |
| ART-07 | review | `artifacts/reviews/plan-review-attempt-2.json` | yes | yes | revision 2 managed plan 的 canonical formal review receipt，直属 supersede attempt 1 |
| ART-08 | validation | `artifacts/validation/self-hosting-approval-drift.md` | yes | yes | revision 1 自举漂移、拒绝绕过、approval-time trust 决策与 carry 边界 |

除 ART-07 外，所有 required planning artifacts 在生成 plan target 前固定；ART-07 由 Reviewer 对该 target 生成，不能被目标自身哈希递归包含。attempt 1 保留为不可变历史，但不进入 revision 2 artifact index 或 attestation。

## Executor Handoff

Executor 收到批准后必须先：

1. 读取 `execution-plan.md`、`plan-contract.json`、ART-01..08、revision 1 archive、`.harness/active-task.json` 和稳定环境事实。
2. 在 Reviewer/Planner 尚未切换前，由 `harness_attest_plan.py write` 运行 current Planner approval checker 并根据用户 reapproval 写 revision 2 attestation；没有 implementation/commit flag 立即停止对应动作。
3. 使用 `activate-amendment` 校验 archive 与 STG-01 完成/语义一致性，只 carry `STG-01`，轮换旧 runtime 并写 `amendment_approved`；不得手工删除或拼接 ledger/run-state。
4. 重新记录实际 Git baseline/status 和用户已有变更；计划文件与 approval-included artifacts 只由 attestation hashes 校验。后续 execution preflight/final 不再重跑可变 Planner/Reviewer checker。
5. 从 STG-02 继续至 STG-06；阶段内只修改 allowed changes，命中 forbidden/reapproval trigger 立即进入 drift/amendment。
6. 每阶段运行列出的 required VAL、生成 stage-delta review、关闭 finding/gap 后才能 transition；最终运行完整 VAL-01..14 和 final-integration review。
7. 验证证据必须记录命令、时间、退出码、计数、target/context/attempt identity；不执行的 fresh-context observation 明确为 `not_observed`。
8. commit 仅在 revision 2 attestation 有 commit authorization 时按 stage/final expectation 执行；push 和其它 external write 不在默认交接范围。

Stop conditions：用户暂停或未批准 implementation；任一 amendment trigger；目标/context 无法安全重建；required validation、blocking/major finding 或 blocking gap 在有界修复后仍未关闭；需要未授权的依赖、Agent、网络、外部写入、提权或长期进程；active pointer 属于另一非终态任务；无法真实声明 provenance 或专业覆盖。

# Electron UI Verifier 安全、执行与知识闭环升级计划

## 规划摘要（Plan Summary）

- Task ID：`2026-07-14-feature-electron-ui-verifier-safety-knowledge-closure`
- Plan revision：`1`
- Lifecycle route：`managed`
- Plan profile：`full`
- Discovery-first：`no`
- Task contract：`plan-contract.json`
- Approval request：`implementation + local GUI/elevated tool + stage commits`；`push/external write` 不请求

本文件只保存批准意图。批准后不得写入 current stage、progress、运行结果、ledger 摘要或 commit 状态；执行事实由 executor 创建的 `attestation.json`、`run-state.json` 和 `ledger.jsonl` 保存。

## 问题定义（Problem）

目标（Goal）：`GOAL-01`

把 `electron-ui-verifier` 升级为一个安全边界可证明、长操作可查询可停止、批准写入 crash-safe、知识生产与复用真正闭环、可安装到任意 workspace 且长期状态有界的 Electron 验证 Skill，并用公共 CLI/HTTP/Playwright fixture 和 Termous 隔离 smoke 证明效果。

非目标（Non-goals）:

- 不增加 raw CDP/WebSocket、第二 automation backend、native OS automation 或 verifier-owned Electron launcher。
- 不引入外部 broker、后台 outbox daemon、vector DB、embedding、LLM retrieval 或 cloud telemetry。
- 不迁移或兼容当前 knowledge layout，不保留 v1/v2 名称、旧 reader 或双写。
- 不修改 process-manager、planner、executor、skill-evaluation-lab 或其它 skill。
- 不自动回滚已经发生的 UI mutation；取消交叉时只能标记 unknown 并停止后续 mutation。
- 不访问 Termous 默认 profile、真实凭据，不创建主机、SSH 或端口转发。

验收标准（Acceptance）:

- `AC-01` 至 `AC-14` 全部通过 required validations。
- 2026-07-14 评估中的 2 个 fail 与 3 个 warn 都有 production code 和端到端证据闭环。
- final source-bound re-evaluation 不再出现相同 fail；任何新 warn 必须记录证据、限制和用户接受的残余风险。

约束（Constraints）:

- 继续使用 Python 3.12+、Playwright 1.61、loopback HTTP、process-manager 和 SQLite rollback journal。
- 所有 binding 默认 input-only/sensitive；任何持久化或输出都不能依赖调用方正确命名 secret key。
- mutation 必须通过 schema、postcondition、compatibility、risk receipt、deadline 五个门禁。
- knowledge truth 为 immutable JSON objects + sealed decisions；SQLite 只是 derived index。
- 本机 GUI 验证需要单独工具许可，但不需要 Windows 管理员权限。

待确认项（Open uncertainties）:

- 无规划阻塞项。Playwright cancellation/mask、独立 skill root 与 process-manager 的运行表现作为实施假设，由 VAL-03/05/09 验证；失败时按 reapproval trigger 停止。

## 需求与验收（Requirements And Acceptance）

功能需求：

| ID | Priority | Requirement | Evidence |
| --- | --- | --- | --- |
| REQ-01 | must | binding 改为 input-only 瞬时上下文，对 assertion、error、URL、console/network、response、journal、report、pending、canonical、日志和视觉证据统一做数据最小化 | AC-01、AC-02 |
| REQ-02 | must | 删除无 postcondition 与 action 自签风险旁路；coordinate、nth 等风险动作使用服务端绑定 action/target/run 的短期一次性 receipt | AC-03 |
| REQ-03 | must | action/workflow 通过 durable operation 执行，提供 requestId 幂等、get/cancel、server deadline、step checkpoint 和 restart recovery | AC-04、AC-05 |
| REQ-04 | must | 批准采用 immutable objects + sealed decision activation 单一提交点，并按用户约束直接切换 knowledge layout、不做迁移 | AC-06、AC-07 |
| REQ-05 | must | production pending/approve 为 passed step 生成 action assets，再生成引用 action IDs 的 workflow asset，完整携带 context、state、risk、aliases、stats、evidence | AC-08 |
| REQ-06 | must | asset ID 只能由服务端加载执行，并与当前 run 的 app/version/screen/state/risk/params/receipt 重新校验；search/compose/reuse 和 reliability 真正闭环 | AC-09、AC-10 |
| REQ-07 | must | 从 `__file__` 派生 skill root，workspace 只承载状态和 PM 配置，真实复制安装目录后仍可初始化与运行 | AC-11 |
| REQ-08 | must | 提供默认 dry-run、fingerprint-gated、引用保护且逐项报告的 retention/prune，限制 run/operation/artifact 长期增长 | AC-12 |
| REQ-09 | must | 更新 Skill/docs/schema/assets/CLI/evals/CI，以公共 CLI/HTTP 三平台 fixture、Termous 隔离 smoke 和最终重评证明交付 | AC-13、AC-14 |

非功能需求：

| ID | Requirement | Validation |
| --- | --- | --- |
| NFR-01 | 保密性与数据最小化：binding、token、query/fragment、file path 和用户内容默认不持久化、不回显 | VAL-04、VAL-14 |
| NFR-02 | Default deny：mutation 不允许自签旁路；不确定的 compatibility、risk、deadline 或 index state 必须拒绝 | VAL-02、VAL-04、VAL-05、VAL-07 |
| NFR-03 | 可靠性与幂等：requestId、operation、run、receipt、decision 在 timeout、cancel、restart、重复请求下结果确定 | VAL-05、VAL-06 |
| NFR-04 | 数据完整性：object hash、sealed activation、SQLite transaction/generation 和 reset/prune 都可恢复、可验证 | VAL-06、VAL-09、VAL-12 |
| NFR-05 | 性能与资源有界：queue、deadline、operation、history、body/output、artifact 和 retrieval 均有上限并维持现有 P95 门槛 | VAL-05、VAL-08、VAL-09 |
| NFR-06 | 可维护性：遵循项目和 Google Python 规范，模块高内聚、依赖单向、CLI 薄、新生产文件不超过 500 行 | VAL-01、VAL-02、VAL-11、VAL-14 |
| NFR-07 | 可复现与跨平台：统一 PM 接口、locked runtime、独立 skill/workspace，并保持 Windows/Linux/macOS 公共 contract | VAL-03、VAL-09、VAL-10、VAL-15 |
| NFR-08 | 可观察性：稳定 error/state、safe progress、operation/run/asset ID、evidence hash、generation 和 cleanup 可审计 | VAL-03 至 VAL-14 |

验收标准：

| ID | Requirement IDs | Given / When / Then |
| --- | --- | --- |
| AC-01 | REQ-01 | 给定唯一 sentinel binding 与含 credential/query/fragment/file path 的 URL，当真实 action、postcondition、finalize、approve 全流程完成或失败时，sentinel/敏感 URL 不出现在任何文本 response、stdout/stderr、state、log、report、pending、decision、object、index dump 或文本 artifact |
| AC-02 | REQ-01 | 给定用敏感 binding 填充的 input，当随后截图时该 locator 自动 mask 且证据通过像素/manifest 校验；无法稳定 mask 时返回 `sensitive_evidence_blocked` 且不提交 artifact |
| AC-03 | REQ-02 | 给定缺失 postcondition、自带 `allowWithoutPostcondition`/`confirmRisk`/coordinate 确认、错误/过期/重用 receipt，当提交 mutation 时服务端拒绝且 mutation count 为零；合法 receipt 只允许绑定动作执行一次 |
| AC-04 | REQ-03 | 给定 action/workflow mutation，当 submit 时快速返回 operationId；相同 requestId/digest 返回同一 operation，冲突 digest 返回 409，get/cancel 可查询最终状态 |
| AC-05 | REQ-03 | 给定 queued、running、deadline、client wait timeout 或 service restart，当取消/中断发生时 inflight mutation 视情况标记 unknown、run aborted，所有后续 mutation 为零且不自动 replay |
| AC-06 | REQ-04 | 给定 object 前/中、decision 前/后、index transaction 中的故障，当重启 verify/search/retry approve 时无 decision 的 object 永不可检索，decision 后 index 可确定重建，合法重复批准返回同一 bundle |
| AC-07 | REQ-04 | 给定当前 knowledge root，当 init 时只返回 exact fingerprint reset；错误确认不改数据，正确确认退役整个旧 root 并建立空的新 objects/decisions/index，不读取、迁移或双写旧资产 |
| AC-08 | REQ-05 | 给定真实 passed mutation workflow，当 finalize/approve 时每个可复用 step 形成 action asset，workflow 只引用 ordered action IDs，并从生产链保留 aliases、parameter schema、app/version/screen、pre/post state、risk、stats、evidence |
| AC-09 | REQ-06 | 给定 approved assetId 与不同 run context，当执行时 wrong app/version/screen/preState/maxRisk/params/receipt 在服务端拒绝；合法 context 可执行并记录 assetId 与 safe outcome |
| AC-10 | REQ-06 | 给定 production-approved corpus，当 search/compose/reuse 时 action 可召回、state transition 可组合、stats 可更新，且 Recall/MRR/false-positive/ingest/query 门槛不退化 |
| AC-11 | REQ-07 | 给定复制到临时安装根的 skill 和另一个独立 workspace，当 init/start/health/stop 时所有脚本、requirements、schema 从安装根解析，状态只写 workspace 且 PM owner-empty |
| AC-12 | REQ-08 | 给定过期 terminal 与受保护状态混合数据，当 prune preview/apply 时 preview 不删除，错误/stale fingerprint 拒绝，apply 只删 terminal unprotected 候选并逐项报告失败 |
| AC-13 | REQ-09 | 给定全部修改，当运行 Skill eval、quick validate、static、public fixture 和 workflow parse 时 SKILL/help/schema/assets/CI 与新 contract 一致，三平台 fixture 不再绕过 service/HTTP/CLI/mutation/approval |
| AC-14 | REQ-09 | 给定用户批准本机 GUI 工具，当 Termous 隔离只读 smoke、全部 required gates、source-bound 重评和 final review 完成时无 live profile/knowledge 污染，所有本轮进程 owner-empty，原评估缺口闭合 |

## 调研门禁（Research Gate）

研究模式（Research mode）：`online-required`

触发原因（Why this mode）:

- Python/Playwright cancellation、长操作 API、敏感数据、SQLite crash consistency 和批准事务均是高风险且容易受版本/语义误判影响的事实。
- 当前评估与上一轮最终审查存在直接冲突，必须回到源码与官方资料重新证明。

不确定项清单（Uncertainty inventory）:

| ID | 问题 | 类型 | Online required | 处理结果 | 影响 |
| --- | --- | --- | --- | --- | --- |
| U-01 | `Future.cancel()` 能否停止已运行 dispatch | external-tool/high-risk | yes | 不能；改为实际 asyncio task/context | REQ-03 |
| U-02 | 长 workflow 应继续同步等待还是 operation 化 | API/architecture | yes | 采用可查询 operation token | REQ-03 |
| U-03 | secret 是否只需 key-based redact | security | yes | 不足；采用 input-only taint + safe projection + mask | REQ-01 |
| U-04 | 多 JSON/SQLite 写如何定义批准提交点 | data/high-risk | yes | sealed activation 是唯一可见 commit point | REQ-04 |
| U-05 | retrieval 缺口是算法还是生产契约 | local-code | no | 生产写读断链；先闭环，不换算法 | REQ-05、REQ-06 |
| U-06 | retention 是否可自动执行 | data/high-risk | yes | 只做用户触发 preview/apply | REQ-08 |

搜索记录与来源矩阵见 `ART-01`。主要来源为 Python、Playwright、Google AIP、SQLite、OWASP、JSON Schema、AWS 官方资料，访问日期均为 2026-07-14。

调研结论（Research result）：`passed`

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）：`online-required`

技术栈清单：

| 类型 | 发现 | 来源 | 影响 |
| --- | --- | --- | --- |
| 语言 | Python 3.12+ async/thread/file/SQLite | Google Python + Python docs | 显式 task/cleanup、类型化 value object |
| 框架 | Playwright Python 1.61 CDP | Playwright official | single owner、actionability、mask、低保真边界 |
| API/架构 | loopback JSON API、long-running operation | Google AIP 147/151/155/216 | input-only、requestId、output-only state、poll/cancel |
| 数据 | canonical JSON + SQLite FTS5 | SQLite official | activation truth、derived index、rebuild/fail closed |
| 安全 | local bearer、risk authorization、logging | OWASP/CWE | 独立 receipt、data minimization、negative tests |
| 工具链 | unittest、eval、PM、Actions | project docs/workflows | 公共 E2E、三平台小 fixture、单平台大 benchmark |

规范来源矩阵及设计模式取舍见 `ART-02`。采用 Ports and Adapters、Command/Operation、State Machine、Repository、Unit of Work/Activation Marker、Content-Addressed Object、Value Object 和 Fail Closed；明确拒绝 broker、event sourcing、第二 backend 和 vector/LLM retrieval。

规范发现结论（Standards result）：`passed`

## 开发质量门禁（Development Quality Gate）

| 维度 | 规划结论 | 阶段映射 | 验证映射 |
| --- | --- | --- | --- |
| 代码标准 | 项目 AGENTS + Google Python；中文注释；稳定 exception/error code | 全阶段 | VAL-01、VAL-02、VAL-14 |
| 静态质量 | closed schema、文件预算、循环依赖、禁止字段/路径/driver | STG-01、STG-06 | VAL-02 |
| 架构边界 | CLI/HTTP/operation/owner/run/approval/retrieval 单向依赖 | STG-01..STG-05 | VAL-01、VAL-14 |
| 设计模式取舍 | 只采用能关闭真实复杂度的状态/激活/仓储模式 | STG-02..STG-04 | VAL-05、VAL-06、VAL-07 |
| 低耦合 | 新模块只通过 value object/repository protocol 交互 | STG-01..STG-05 | VAL-01、VAL-02 |
| 高内聚 | sensitivity/operation/risk/retention 各自单一职责 | STG-01、STG-02、STG-05 | 文件预算与 review |

过度设计防护：

- 保持单进程、单 owner、单 SQLite index；不加 scheduler/broker/第二 DB。
- operation 仅用于 mutation，短 query 保持同步。
- activation 只用一个 sealed decision commit marker，不实现分布式两阶段提交。
- retention 不后台自动运行；stats 只影响排序，不参与授权。

开发质量结论（Development quality result）：`passed`

## 上下文（Context）

本地代码：

- `skills/electron-ui-verifier/scripts/electron_verifier/{automation,runs,approval,reports,retrieval,security,models,actions,assertions}.py`
- `skills/electron-ui-verifier/scripts/ev_{init,action,workflow,asset_runner,prepare}.py`
- `skills/electron-ui-verifier/schemas/**`、`tests/**`、`evals/electron-ui-verifier/**`
- `.github/workflows/electron-ui-verifier.yml`

本地文档：

- 当前 `SKILL.md` 与五份 references。
- `.harness/evaluations/2026-07-14/electron-ui-verifier/{report.md,review.json}`。
- 2026-07-11 reliability upgrade 的 plan、target architecture、validation 和 final review。
- `ART-01` 至 `ART-07`。

外部来源：见 ART-01/ART-02，全部为官方或一手技术资料；AWS outbox 只作为本地 activation 顺序的模式参考。

用户约束：

- knowledge 不考虑旧版兼容，直接按新设计。
- 当前只制定计划，不实施；实施需再次批准。
- 前序评估已提交；用户现已批准本计划实施和阶段提交，仍未授权 push/external write。
- Termous 可作为实际应用，但只使用隔离 profile 和安全只读动作。

证据等级：

| 结论 | 等级 | 来源 | 影响 |
| --- | --- | --- | --- |
| binding 明文、风险旁路、知识断链、root 耦合存在 | read | 当前源码 + review.json | must fix |
| 当前 fixture 绕公共接口 | read | run_fixture_cdp_smoke.py | public E2E required |
| running future 不能 cancel | external confirmed | Python docs | operation architecture |
| activation marker 能关闭可见性窗口 | external + design inference | SQLite/AWS + ART-03 | fault injection required |
| Termous 新 contract 可通过 | assumption | 旧 smoke 证据 | VAL-13 验证 |

## 候选方案（Options）

### 方案 A：最小安全补丁

- 做法：修 assertion redact、删除旁路、统一 timeout、补少量 unit tests。
- 优点：改动小、交付快。
- 缺点：无法停止已运行 workflow，批准 crash window 和知识写读断链仍在；public E2E 仍不成立。
- 风险：再次出现“测试通过但真实 contract 失败”。
- 验证：只能局部 unit，不能关闭 2 fail/3 warn。
- 回滚：简单，但不满足目标。

### 方案 B：结构化闭环升级（选择）

- 做法：input-only taint、durable operation、独立 risk receipt、sealed activation、production action/workflow assets、server reuse gate、portable root、retention 和 public E2E。
- 优点：每个评估缺口对应明确不变量和端到端证据；保留现有有效架构。
- 缺点：公共 mutation/knowledge layout breaking，跨多个核心模块，验证工作较大。
- 风险：operation/activation 设计错误会影响核心流程，必须阶段化 fault injection。
- 验证：VAL-01..VAL-14 required，VAL-15 optional。
- 回滚：实施提交可整体回退；运行数据通过 task tmp 与 retired root 隔离，不做 live migration。

### 方案 C：SQLite 单一真相 + 后台 job 系统

- 做法：把 operation、approval、assets、index 全放 SQLite，增加 job scheduler/outbox worker。
- 优点：单 DB transaction 简化部分原子性。
- 缺点：丢失逐对象 JSON 审计/重建优势，新增后台服务和恢复复杂度，对本机 Skill 过度设计。
- 风险：数据库损坏同时影响 truth/index；安装和 PM 面扩大。
- 验证：成本最高。
- 回滚：数据格式变化更重。

## 决策（Decision）

选择方案：`B - structured closed-loop upgrade`

原因：它是唯一同时解决执行继续、敏感值泄露、风险自签、批准双写、知识断链、CLI 绕门禁、安装耦合和历史无界的方案，同时不引入新后端或分布式基础设施。

影响：

- mutation HTTP/CLI 改为 operation receipt/poll 语义。
- action schema 删除旁路字段，高风险动作增加独立 receipt 流程。
- knowledge layout 直接切换，当前知识必须 fingerprint reset。
- approved workflow 从复制 steps 改为引用 action object IDs。
- 新增 operation/risk/prune CLI 与 schema。

可逆性：源码可整体回退；新 knowledge 不向旧 layout 回写。已 reset 的旧 root 保留在 retired，回退不自动恢复，需用户另行决定。

方案变更触发条件：ART-03 的 Reapproval Triggers 与 contract 列表；任何新增 backend/broker、兼容迁移、放宽 secret/risk/postcondition、修改其它 skill、远端写或默认 profile 操作都需重新批准。

## 影响面矩阵（Impact Matrix）

| Surface | Involved | Files/modules | Risk | Validation | Docs |
| --- | --- | --- | --- | --- | --- |
| API | yes | service、ev_action/workflow、operation/risk/prune | high | VAL-03、VAL-05 | SKILL + refs |
| Data model | yes | run/pending/knowledge/decision/operation schemas | high | VAL-01、VAL-06、VAL-07 | knowledge/workflow refs |
| Frontend interaction | yes | Playwright mutation/mask | high | VAL-03、VAL-04、VAL-13 | actions ref |
| Config/environment | yes | ev_init、config、PM service config | medium | VAL-09、VAL-10 | server ref |
| Compatibility | yes, breaking | knowledge + mutation contract | high | VAL-11、VAL-12 | README/CHANGELOG |
| Tests | yes | unit/eval/fixture/Termous | high | VAL-01..VAL-15 | validation artifacts |
| Documentation | yes | Skill/references/help/assets/repo docs | medium | VAL-11、VAL-14 | required |
| Code standards | yes | all touched Python/schema | medium | VAL-02、VAL-14 | ART-02 |
| Architecture | yes | operation/activation/reuse/retention | high | VAL-05..VAL-09 | ART-03/04 |

## 实施计划（Implementation Plan）

阶段依赖、引用、授权和验证以 `plan-contract.json` 为机器真相源；本节解释实施理由和边界。

### STG-01：敏感数据与 Mutation 契约地基

目标：关闭 binding/URL 泄露和 postcondition/risk 自签旁路，建立后续 operation 可依赖的封闭 action contract。

做法：

- 新增 `sensitivity.py` 的 BindingContext、safe projection、URL sanitizer 和 screenshot mask context。
- 扩展 parameter schema 的 `sensitive`，默认 true；resolved action 只存在内存。
- assertion internal result 与 persisted result 分离，error envelope 做 value-aware scrub。
- 删除 `allowWithoutPostcondition`、`confirmRisk` 和 action 自签 coordinate 授权。
- 新增 `risk_authorization.py`、receipt schema 和 preview/approve service/CLI contract。
- 封闭 action/workflow/run/pending schema 的未知字段。

位置：`security.py`、`knowledge_models.py`、`assertions.py`、`actions.py`、`models.py`、schemas、new sensitivity/risk modules、tests。

参考/规范：AIP-147、OWASP Logging/Transaction Authorization、CWE-532、JSON Schema、Playwright screenshot mask、ART-02。

验证：VAL-01、VAL-02、VAL-04。

风险和回滚：mask capability 不稳定时 fail closed 禁止 artifact；不通过放宽 secret 规则规避。阶段失败回退 STG-01 文件，不进入 operation 改造。

阶段契约：depends none；REQ-01/02，AC-01/02/03，NFR-01/02/06/08；仅改 electron skill/tests/evals；禁止其它 skill、raw backend、trace 持久 secret；exit 为 closed schema、sentinel unit 和 receipt matrix 通过；commit expected `stage`。

- 机器镜像 - tracking：`depends_on=[]`；`requirement_ids=[REQ-01, REQ-02]`；`acceptance_ids=[AC-01, AC-02, AC-03]`；`nonfunctional_ids=[NFR-01, NFR-02, NFR-06, NFR-08]`；`validation_ids=[VAL-01, VAL-02, VAL-04]`。
- 机器镜像 - allowed_changes：`skills/electron-ui-verifier/**`、`evals/electron-ui-verifier/**`。
- 机器镜像 - forbidden_changes：`skills/process-manager/**`、`raw CDP/WebSocket backend`、`binding/trace/raw URL persistence`、`mutation without postcondition`、`self-authorized risk`。

### STG-02：Durable Operation、Deadline 与 Cancel

目标：把 HTTP 等待与实际 mutation 生命周期解耦，证明取消后后续 mutation 为零。

做法：

- 新增 `operations.py`：OperationStore/Context/State、requestId dedupe、atomic persistence、recovery/expiry。
- worker 持有实际 asyncio task，cancel/deadline 传入 runtime/run，替换 response future cancellation 假象。
- action/workflow route 返回 operation receipt；新增 get/cancel；CLI submit/poll 使用统一 deadline。
- workflow 每步边界检查 context，Playwright timeout 使用 remaining budget。
- cancel 与 inflight mutation 交叉时标记 step unknown/run aborted/operation UNKNOWN，禁止 replay。

位置：`automation.py`、`service.py`、`runs.py`、`limits.py`、new operations、ev_action/workflow/operation、schemas/tests/evals。

参考/规范：Python Future/asyncio、AIP-151/155/216/214、ART-03。

验证：VAL-01、VAL-03、VAL-05。

风险和回滚：不承诺撤销已发生副作用；若 Playwright task 不能及时取消，仍必须在当前 action 收敛后阻止后续步骤。失败回到同步行为且不进入 STG-03。

阶段契约：depends STG-01；REQ-03，AC-04/05，NFR-02/03/05/08；禁止后台 scheduler/broker、自动 replay、客户端自设 state；exit 为 requestId/cancel/deadline/restart 全部通过；commit expected `stage`。

- 机器镜像 - tracking：`depends_on=[STG-01]`；`requirement_ids=[REQ-03]`；`acceptance_ids=[AC-04, AC-05]`；`nonfunctional_ids=[NFR-02, NFR-03, NFR-05, NFR-08]`；`validation_ids=[VAL-01, VAL-03, VAL-05]`。
- 机器镜像 - allowed_changes：`skills/electron-ui-verifier/**`、`evals/electron-ui-verifier/**`。
- 机器镜像 - forbidden_changes：`background scheduler or broker`、`automatic mutation replay`、`client-authored operation state`、`skills/process-manager/**`。

### STG-03：Sealed Activation 与 Knowledge Direct Cutover

目标：消除 canonical/decision/index 双写窗口，并直接建立新 knowledge layout。

做法：

- knowledge truth 改为 `objects/` + `decisions/`；decision 是唯一 activation commit point。
- approval 先构造/校验/写 immutable objects，最后 exclusive-create decision，再更新 derived index generation。
- CanonicalStore/verify/rebuild 只遍历 approved decision 可达对象，orphan 永不索引。
- 对 object、decision、index 每个 phase 增加 fault injection 与 restart recovery。
- 更新 KnowledgeReset，当前 layout 必须 exact fingerprint reset，不迁移或双写。

位置：`approval.py`、`canonical_store.py`、`atomic_io.py`、`knowledge_index.py`、`knowledge_reset.py`、config/schema/tests/evals。

参考/规范：SQLite Atomic Commit/FTS5/corruption、AWS outbox 原则、ART-03。

验证：VAL-01、VAL-02、VAL-06、VAL-12。

风险和回滚：decision 后 index 失败时 search fail closed/rebuild；不得删除 retired root。阶段失败不读取或修改用户 live knowledge，只使用 task tmp。

阶段契约：depends STG-02；REQ-04，AC-06/07，NFR-03/04/06/08；禁止 SQLite canonical truth、WAL、兼容 reader/migration；exit 为 phase matrix、idempotency、reset regression 通过；commit expected `stage`。

- 机器镜像 - tracking：`depends_on=[STG-02]`；`requirement_ids=[REQ-04]`；`acceptance_ids=[AC-06, AC-07]`；`nonfunctional_ids=[NFR-03, NFR-04, NFR-06, NFR-08]`；`validation_ids=[VAL-01, VAL-02, VAL-06, VAL-12]`。
- 机器镜像 - allowed_changes：`skills/electron-ui-verifier/**`、`evals/electron-ui-verifier/**`。
- 机器镜像 - forbidden_changes：`SQLite canonical truth`、`legacy knowledge reader/migration/double-write`、`unactivated object retrieval`、`live knowledge mutation during tests`。

### STG-04：Production Knowledge 与服务端复用闭环

目标：让一次真实验证产生可审计、可批准、可检索并能安全复用的 action/workflow 知识，消除 synthetic fixture 与生产路径之间的断层。

做法：

- 每个通过且满足复用条件的步骤生成 action proposal，workflow proposal 只保存有序 action object IDs，不再复制已解析 steps。
- proposal 完整携带 app/version、screen/state、pre/postcondition、risk、parameter schema、aliases、evidence、quality stats；绑定实值不得进入对象。
- pending、approve、reject、list、show、search、compose 使用同一 schema 与对象构造器，批准时调用 STG-03 的 sealed activation。
- asset execution 改为服务端按 ID 读取和解析，重新验证 app/version/screen/state、参数、风险 receipt、postcondition 与当前 session；CLI 不再加载对象后绕过服务端门禁。
- derived index 只索引 activated objects，记录 retrieval/use/success/failure 统计；搜索结果返回匹配原因和兼容性判定，不返回敏感输入。
- 质量阈值同时覆盖精确检索、alias/参数检索、无关查询拒绝、compose 顺序、复用成功率和有界延迟。

位置：`reports.py`、`approval.py`、`retrieval.py`、`knowledge_index.py`、`runs.py`、`service.py`、`ev_pending.py`、`ev_approve.py`、`ev_search.py`、`ev_asset.py`、schemas、tests、evals。

参考/规范：AIP-147/155/216、JSON Schema、现有 evidence hashing、ART-02/03/04。

验证：VAL-01、VAL-03、VAL-07、VAL-08。

风险和回滚：action 与 workflow activation 必须在同一 approval intent 下可重复恢复；任一 action 不可用时 workflow 不得部分可检索。失败时保留 immutable orphan 并由 STG-05 的显式 prune 处理。

阶段契约：depends STG-03；REQ-05/06，AC-08/09/10，NFR-01/02/03/04/05/06/08；仅改 electron skill/tests/evals；禁止 synthetic-only 证明、客户端信任资产内容、未激活对象参与检索、LLM/vector 召回；exit 为真实 action/workflow roundtrip、server gate、retrieval quality/performance 通过；commit expected `stage`。

- 机器镜像 - tracking：`depends_on=[STG-03]`；`requirement_ids=[REQ-05, REQ-06]`；`acceptance_ids=[AC-08, AC-09, AC-10]`；`nonfunctional_ids=[NFR-01, NFR-02, NFR-03, NFR-04, NFR-05, NFR-06, NFR-08]`；`validation_ids=[VAL-01, VAL-03, VAL-07, VAL-08]`。
- 机器镜像 - allowed_changes：`skills/electron-ui-verifier/**`、`evals/electron-ui-verifier/**`。
- 机器镜像 - forbidden_changes：`synthetic-only evidence`、`client-trusted asset execution`、`unactivated object retrieval`、`LLM/vector retrieval`。

### STG-05：安装可移植性与有界保留

目标：把 Skill 安装根与 workspace 状态根彻底分离，并提供引用安全、默认只预览的历史清理能力。

做法：

- `ev_init.py` 与公共 CLI 通过模块 `__file__` 解析 `skill_root`，workspace 只保存 state、PM config、evidence 与 knowledge；错误信息同时报告两个根及检查结果。
- 删除依赖 workspace 内 `skills/electron-ui-verifier` 的路径推断；fixture 把 Skill 真实复制到独立目录，不用符号链接，并在另一 workspace 完成 init/start/stop。
- 新增 retention policy 与 `ev_prune.py preview|apply`；默认 preview，apply 需要精确 fingerprint 和显式确认。
- prune 按 run/operation/evidence/object reference graph 判定；open/nonterminal operation、pending、decision、approved object 及其 evidence 永远受保护。
- 每次删除前执行 path containment 和引用复查，逐项记录结果；失败不继续扩大删除范围，重复 apply 保持幂等。
- orphan object 只在超过 grace period 且没有 decision/pending/reference 时可删；不自动删除 retired knowledge root。

位置：`ev_init.py`、`config.py`、`paths.py`、new `retention.py`/`ev_prune.py`、`assets/`、tests、evals、reference docs。

参考/规范：Python pathlib/Google Python Style、AIP-214 expiration、现有 path containment/PM public contract、ART-02/03。

验证：VAL-01、VAL-09、VAL-10。

风险和回滚：删除是不可逆边界，因此没有后台定时器、启动时自动清理或模糊匹配；任一引用图不完整都 fail closed。portable-root 失败时不修改现有 workspace 数据。

阶段契约：depends STG-04；REQ-07/08，AC-11/12，NFR-02/03/05/06/07/08；允许 electron skill/tests/evals；禁止修改 process-manager 实现、symlink 依赖、自动 prune、越界删除；exit 为 copy-install E2E、PM smoke、preview/apply/idempotency/reference protection 通过；commit expected `stage`。

- 机器镜像 - tracking：`depends_on=[STG-04]`；`requirement_ids=[REQ-07, REQ-08]`；`acceptance_ids=[AC-11, AC-12]`；`nonfunctional_ids=[NFR-02, NFR-03, NFR-05, NFR-06, NFR-07, NFR-08]`；`validation_ids=[VAL-01, VAL-09, VAL-10]`。
- 机器镜像 - allowed_changes：`skills/electron-ui-verifier/**`、`evals/electron-ui-verifier/**`。
- 机器镜像 - forbidden_changes：`skills/process-manager/**`、`symbolic-link-only portability`、`automatic prune`、`path escape or unreferenced bulk deletion`。

### STG-06：Public Contract、真实 Fixture 与文档收敛

目标：用用户实际入口而非内部 mock 证明完整工作流，并让 Skill 文档、CLI help、示例和三平台 CI 同步新契约。

做法：

- 将 fixture 从直接调用 driver/run 模块升级为：真实复制 Skill、`ev_init`、process-manager 启动 service、HTTP/CLI attach、mutation、operation poll、pending、approve、search、compose、asset reuse、cancel、finalize、stop/cleanup。
- fixture 页面提供稳定的可观察 mutation、敏感参数、慢操作和故障注入点；外部仅通过公共 CLI/HTTP 交互，内部状态只用于事后证据核验。
- 扩充 static/eval/reset/retrieval/performance runner，所有输出支持显式 task work dir，不写 `.codex/tmp`，不启动 `codex exec` 或任何代理。
- 更新 `SKILL.md` 的短主流程与按需 reference 导航；补齐 operation、risk receipt、sealed knowledge、asset reuse、retention、breaking reset 和 troubleshooting。
- 更新 schema/examples/CLI `--help`、README、CHANGELOG；删去旧旁路字段和旧 layout 表述，不保留 v1/v2 兼容层。
- 三平台 workflow 跑公共契约和 CDP lifecycle；性能基准仅在 Ubuntu 运行并保留 summary artifact，避免把矩阵成本放大三倍。

位置：`skills/electron-ui-verifier/tests/`、`evals/electron-ui-verifier/`、Skill docs/assets/schemas、`.github/workflows/electron-ui-verifier.yml`、`README.md`、`CHANGELOG.md`。

参考/规范：现有 process-manager public contract、GitHub Actions 官方语法、Skill 渐进披露约束、ART-02/05。

验证：VAL-02、VAL-03、VAL-04、VAL-05、VAL-06、VAL-07、VAL-08、VAL-09、VAL-10、VAL-11、VAL-12。

风险和回滚：fixture 涉及真实子进程，必须记录其 PID/processKey 并只清理自有资源；CI 不接触 Termous 或用户知识。若 hosted runner 无法复现，保留本地必需证据并将 VAL-15 标为未执行，不伪造通过。

阶段契约：depends STG-05；REQ-09，AC-13，NFR-03/05/06/07/08；允许 electron skill/evals/workflow/repo docs；禁止修改其它 skill、运行 agent、远端 push、默认 profile、伪造 hosted 结果；exit 为 required VAL-02..12 本地闭环、文档与 public contract 一致；commit expected `stage`。

- 机器镜像 - tracking：`depends_on=[STG-05]`；`requirement_ids=[REQ-09]`；`acceptance_ids=[AC-13]`；`nonfunctional_ids=[NFR-03, NFR-05, NFR-06, NFR-07, NFR-08]`；`validation_ids=[VAL-02, VAL-03, VAL-04, VAL-05, VAL-06, VAL-07, VAL-08, VAL-09, VAL-10, VAL-11, VAL-12]`。
- 机器镜像 - allowed_changes：`skills/electron-ui-verifier/**`、`evals/electron-ui-verifier/**`、`.github/workflows/electron-ui-verifier.yml`、`README.md`、`CHANGELOG.md`。
- 机器镜像 - forbidden_changes：`other skills`、`agent execution`、`remote push or workflow dispatch`、`default user profile`、`fabricated hosted evidence`。

### STG-07：Termous 隔离实测、最终评估与交付审查

目标：在真实 Electron 应用上补充只读兼容证据，并以 source-bound 评估、代码审查和清理证明方案全部收敛。

做法：

- 先重跑全部必需自动化验证，再经用户已请求的 elevated GUI 授权使用探针确认存在的 `"D:\\SoftWare\\Termous\\Termous.exe"`。
- Termous 仅使用临时 profile/CDP attach，执行 probe、snapshot、locator screenshot、read-only assertion、detach；不得点击、输入、修改设置或读取用户默认 profile 数据。
- 记录 executable fingerprint、target identity、命令、返回码、结构化摘要和 artifact hash；所有临时进程通过 process-manager/精确 PID 清理。
- 使用 `skill-evaluation-lab` 对最终 source hash 重新执行静态契约与语义评估，禁止 `codex exec`；逐项关闭原报告 7 个维度的 warn/fail。
- 做最终代码审查、schema/API/docs 一致性检查、secret scan、`git diff --check`、workspace/PM owner-empty 检查；残余风险明确写入 final review。

位置：task artifacts/tmp、`run_termous_smoke.py`、最终评估报告；仅在发现缺陷时回到所属阶段修复 approved scope 内文件。

参考/规范：electron Skill safety boundary、process-manager cleanup contract、skill-evaluation-lab 工作流、ART-05/06/07。

验证：VAL-01..VAL-14 required；VAL-15 optional，由用户推送后提供 hosted evidence。

风险和回滚：Termous 是外部真实应用，任何 mutation 需求都必须重新批准；无法启动时 VAL-13 不得通过，应记录 blocker、替代 fixture 证据和残余风险。最终评估若 source hash 不匹配则全部证据失效并重跑。

阶段契约：depends STG-06；REQ-09，AC-14，NFR-01..08；允许 approved source 修复和 task evidence；禁止 Termous mutation/default-profile、远端写、未授权提交、扩大范围；exit 为 VAL-01..14 passed、评估 source-bound、owner-empty、final review 无未解决 blocker；commit expected `stage`。

- 机器镜像 - tracking：`depends_on=[STG-06]`；`requirement_ids=[REQ-09]`；`acceptance_ids=[AC-14]`；`nonfunctional_ids=[NFR-01, NFR-02, NFR-03, NFR-04, NFR-05, NFR-06, NFR-07, NFR-08]`；`validation_ids=[VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, VAL-06, VAL-07, VAL-08, VAL-09, VAL-10, VAL-11, VAL-12, VAL-13, VAL-14, VAL-15]`。
- 机器镜像 - allowed_changes：`skills/electron-ui-verifier/**`、`evals/electron-ui-verifier/**`、`.github/workflows/electron-ui-verifier.yml`、`README.md`、`CHANGELOG.md`、`artifacts/validation/**`、`artifacts/reviews/**`。
- 机器镜像 - forbidden_changes：`Termous mutation or default-profile access`、`external write or remote push`、`unauthorized commit`、`scope expansion beyond approved files`。

## 环境（Environment）

Workspace 环境来源：`.harness/environment.md`。

本任务使用：Python 3.12、Playwright/Chromium、loopback HTTP、SQLite FTS5、process-manager 公共 CLI、PowerShell；fixture 和所有 state 放在 task `tmp/` 或验证命令显式 work dir。

临时覆盖：`PYTHONDONTWRITEBYTECODE=1`；测试根指向 task tmp；不得使用用户默认 Electron profile 或全局 knowledge root。

## Git 上下文（Git Context）

- Main / working branch：`main` / `harness/feature`。
- Task type / branch action：feature；沿用当前工作分支，不新建、不切换。
- Sync source / occupancy evidence：评估提交为 `c1b1503`；当前 `HEAD=53bb1f9`（合并提交，包含 `c1b1503`），且 `c1b1503..HEAD` 在本计划涉及的 Skill/eval/CI/docs 路径无差异；不执行 fetch/pull/rebase。
- Worktree status and known changes：仅本 task bundle 和 active pointer 预计为未提交规划文件；实施前 executor 必须重新核验。
- Commit authorization：`explicitly authorized by user for stage commits`。
- Branch closure：按 stage contract 提交并记录；不推送、不创建 PR，任何 external write 仍需另行授权。

同一仓库 Git 命令串行；只读状态优先 `--no-optional-locks`，不自动 stash、rebase、reset 或清理未知变更。

## 工具（Tooling）

| 工具 | 用途 | 阶段 | 状态 | 风险 | 替代方案 | 用户确认 |
| --- | --- | --- | --- | --- | --- | --- |
| Python 3.12/unittest | 单元、fixture、eval | STG-01..07 | available | 测试写临时状态 | 无 | 不需额外确认 |
| Playwright Chromium | CDP 驱动与 screenshot mask | STG-01/06/07 | repository dependency | 子进程/浏览器下载 | 已安装 runtime 或记录 blocker | fixture 已在范围内 |
| process-manager public CLI | verifier service 与进程树生命周期 | STG-05..07 | available | 长期进程 | 阻塞，不手写后台 shell | 使用现有 Skill 已在范围内 |
| `skill-evaluation-lab` | source-bound 最终评估 | STG-07 | available | 只读静态工作流 | 手工契约检查 | 不运行 `codex exec` |
| Termous executable | 真实 Electron 只读 smoke | STG-07 | user supplied | 本地 GUI/外部进程 | public fixture | requested elevated-tool approval |
| GitHub Actions | 可选三平台证据 | post implementation | remote/user-triggered | 外部写与 hosted cost | 本地三平台无法等价替代 | 本计划不请求外部写 |

## 长期进程管理（Process Manager Gate）

- Needs long-running process：`yes`，仅 verifier service；fixture Electron/Termous 为有界测试进程。
- Manager bootstrap：统一 `pm_manager.py status|start`，不判断或暴露 OS backend，普通流程不先运行 doctor。
- Managed services：STG-05/06 的隔离 verifier service；STG-07 Termous 仅在可由统一入口精确托管时启动，否则记录 blocker。
- Readiness：authenticated manager identity、config validation、processKey、health ready、bounded logs。
- Completion evidence：`cleanupVerified: true`、`stopResult.ownerEmpty: true`、graceful-force stop 结果和 manager shutdown/intentional retention。
- Fallback or blocker：不得用 `Start-Process`、shell `&` 或平台专属入口绕过 manager；公共 manager 失败即停止相关验证。

## 验证（Validation）

所有命令从仓库根执行，使用 `python -u -X utf8 -B`；executor 将 stdout/stderr、返回码、开始/结束时间、source hash 汇总到对应 evidence path。新 regression runner 必须在 STG-01..05 随功能一起实现，不能以手工观察代替。

| VAL ID | Required | Kind / command / tool | Covers AC/NFR | Evidence path | Failure handling |
| --- | --- | --- | --- | --- | --- |
| VAL-01 | yes | `python -u -X utf8 -B -m unittest discover -s skills/electron-ui-verifier/tests -p "test_*.py" -v` | AC-01..13；NFR-01..08 | `artifacts/validation/unit-component-tests.txt` | 修复所属阶段并全量重跑 |
| VAL-02 | yes | `python -u -X utf8 -B evals/electron-ui-verifier/run_static_checks.py` | AC-01/03/04/06/07/08/11/13；NFR-01/02/04/06/07 | `artifacts/validation/static-checks.json` | schema/docs/forbidden pattern 任一失败即停止 |
| VAL-03 | yes | `python -u -X utf8 -B skills/electron-ui-verifier/tests/run_fixture_cdp_smoke.py --work-dir .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/public-fixture --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/public-fixture.json` | AC-02/03/04/08/09/11/13；NFR-02/03/07/08 | `artifacts/validation/public-fixture.json` | 保留精确进程日志，清理后修复重跑 |
| VAL-04 | yes | `python -u -X utf8 -B evals/electron-ui-verifier/run_security_regression.py --work-dir .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/security --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/security-regression.json` | AC-01/02/03；NFR-01/02/08 | `artifacts/validation/security-regression.json` | sentinel、URL、risk/postcondition 任一泄露/旁路即停止 |
| VAL-05 | yes | `python -u -X utf8 -B evals/electron-ui-verifier/run_operation_regression.py --work-dir .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/operations --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/operation-regression.json` | AC-04/05；NFR-02/03/05/08 | `artifacts/validation/operation-regression.json` | 证明 cancel/deadline 后 mutation count 为零，否则停止 |
| VAL-06 | yes | `python -u -X utf8 -B evals/electron-ui-verifier/run_approval_recovery.py --work-dir .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/approval --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/approval-recovery.json` | AC-06；NFR-03/04/08 | `artifacts/validation/approval-recovery.json` | 每个 phase fault/restart/idempotency 未通过即停止 |
| VAL-07 | yes | `python -u -X utf8 -B evals/electron-ui-verifier/run_knowledge_roundtrip.py --work-dir .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/knowledge --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/knowledge-roundtrip.json` | AC-08/09/10；NFR-01/02/03/04/08 | `artifacts/validation/knowledge-roundtrip.json` | 必须来自 public production run，禁止 synthetic substitute |
| VAL-08 | yes | `python -u -X utf8 -B evals/electron-ui-verifier/run_retrieval_benchmark.py --work-dir .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/retrieval --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/retrieval-performance.json` | AC-10；NFR-05/08 | `artifacts/validation/retrieval-performance.json` | quality floor 或 latency/resource ceiling 失败即修复重跑 |
| VAL-09 | yes | `python -u -X utf8 -B evals/electron-ui-verifier/run_portability_retention.py --work-dir .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/portable --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/portability-retention.json` | AC-11/12；NFR-02/03/05/07/08 | `artifacts/validation/portability-retention.json` | copy-root、preview/apply、reference protection 全部必需 |
| VAL-10 | yes | `python -u -X utf8 -B skills/electron-ui-verifier/tests/run_process_manager_smoke.py --workspace .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/pm-workspace --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/process-manager-smoke.json` | AC-11/13；NFR-03/07/08 | `artifacts/validation/process-manager-smoke.json` | owner-empty/cleanupVerified 不为 true 即停止 |
| VAL-11 | yes | `run_evals.py` + `skill-creator quick_validate.py`，均只读/静态且明确禁用 agent execution | AC-13；NFR-06/07/08 | `artifacts/validation/skill-contract.json` | CLI help、progressive disclosure、schema 任一失败即停止 |
| VAL-12 | yes | `python -u -X utf8 -B evals/electron-ui-verifier/run_knowledge_reset_regression.py --work-dir .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/reset --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/knowledge-reset.json` | AC-07；NFR-03/04/07 | `artifacts/validation/knowledge-reset.json` | 必须证明拒绝兼容读取并保留 retired root |
| VAL-13 | yes | `python -u -X utf8 -B skills/electron-ui-verifier/tests/run_termous_smoke.py --exe "D:\\SoftWare\\Termous\\Termous.exe" --isolated-profile .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/tmp/termous-profile --no-learn --output .harness/tasks/2026-07-14/feature/electron-ui-verifier-safety-knowledge-closure/artifacts/validation/termous-smoke.json` | AC-14；NFR-01/02/03/07/08 | `artifacts/validation/termous-smoke.json` | 需 elevated GUI 授权；失败记录 blocker，绝不切默认 profile |
| VAL-14 | yes | `skill-evaluation-lab` source-bound workflow + final code review + `git diff --check` | AC-14；NFR-01..08 | `artifacts/reviews/final-code-review.md` | source hash 不一致或高优先级 finding 未关闭即停止 |
| VAL-15 | no | 用户推送后运行 `.github/workflows/electron-ui-verifier.yml` 三平台矩阵 | AC-13；NFR-07 | `artifacts/validation/platform-matrix.json` | 未执行保持 optional/not-run，不冒充本地证据 |

规划阶段调研探针与实施验证分离；任何 required evidence 必须绑定当时 source hash。VAL-13 的外部应用失败不能由 VAL-03 替换为 passed，但不允许为通过而扩大权限或执行写操作。

## 文档（Documentation）

必需更新：

- `skills/electron-ui-verifier/SKILL.md`：紧凑主流程、何时读取 capability/reference、operation/risk/knowledge/retention 门禁。
- `references/server.md`、`actions.md`、`workflow.md`、`knowledge.md`、`troubleshooting.md`：公共契约、失败语义、恢复与安全示例。
- schemas 与 `assets/*.json`：仅保留新格式和完整 action/workflow reference 示例。
- `README.md` 与 `CHANGELOG.md`：breaking mutation/knowledge reset、验证入口和权限边界。
- CLI `--help`：参数、input/output、危险操作确认、默认 dry-run、返回码。

Changelog：记录删除 `allowWithoutPostcondition`/`confirmRisk`、operation receipt、sealed activation、server-side asset gate、portable root 与 prune；明确“不兼容旧 knowledge，需 fingerprint reset”。

## 文件写入策略（File Write Strategy）

| File / group | Segmented | Semantic boundaries | Whole-file check |
| --- | --- | --- | --- |
| `service.py`、`runs.py`、`automation.py` | yes | route / lifecycle / worker context | compile、unit、public fixture |
| knowledge/approval/index modules | yes | object / decision / activation / rebuild | fault matrix、roundtrip |
| sensitivity/risk/operation/retention new modules | yes | model / store / policy / API | unit + schema + static |
| schemas/assets | per file | one complete JSON document | parse + closed-schema tests |
| tests/evals | per scenario | helper / case / output contract | direct command + evidence parse |
| `SKILL.md`/references/repo docs | per section | workflow / boundary / troubleshooting | link/help/static checks |
| CI workflow | no | complete job/step | YAML parse + local static contract |

现有大文件只做定点 patch；若单文件超过 500 行，先列函数/章节分段，单次 patch 保持语义完整并在最后全文重读。不得为了本计划批量格式化无关文件。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞 | 状态 | 问题 | 决策 | 应用位置 |
| --- | --- | --- | --- | --- | --- |
| Q-01 | no | resolved | 用户给出的 Termous 路径包含目录尾空格 | 本地只读探针确认实际路径为 `D:\\SoftWare\\Termous\\Termous.exe` | VAL-13 |
| Q-02 | no | resolved | 是否兼容旧 knowledge/API | 用户明确不要求；直接 fingerprint reset，不迁移、不双读双写 | STG-01/03/06 |
| Q-03 | no | resolved | 是否新增后台 scheduler、broker、vector/LLM 或第二 driver | 均不新增，保留单 service/owner/Playwright CDP | ART-03、all stages |
| Q-04 | no | resolved | hosted 三平台是否为本地完成阻塞项 | workflow 必须更新，远端运行 VAL-15 optional，由用户推送后提供 | STG-06/VAL-15 |
| Q-05 | no | resolved | 是否修改 process-manager | 只消费公共 CLI；实现改动超范围并触发重新批准 | STG-05..07 |
| Q-06 | no | resolved | 是否已有 commit 权限 | 用户在批准实施时明确授权 stage commits；push/external write 未授权 | Git/Approval |
| Q-07 | yes at execution | authorization requested | 是否进入实现并启动本地 GUI | 本轮请求 implementation 与 Termous elevated-tool；未批准前停止 | Approval |

## 方案质量门禁（Plan Quality Gate）

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 关键判断有证据等级 | passed | Context、ART-01 |
| Research Gate 已完成 | passed | online-required，ART-01 |
| Standards Discovery Gate 已完成 | passed | ART-02 |
| Development Quality Gate 已完成 | passed | quality mapping、ART-02/03 |
| 影响面矩阵完整 | passed | plan + ART-04 |
| 候选方案比较充分 | passed | A/B/C 的收益、风险、回滚 |
| 每阶段可独立验证 | passed | 7 Stage Contracts + VAL mapping |
| 方案变更触发条件清楚 | passed | ART-03 + contract triggers |
| 用户批准摘要可记录 | passed | implementation、elevated tool、stage commits 已批准；external write excluded |

质量结论：`passed`。

## 规划自查（Plan Self-Review）

自查结论：`passed`；ART-06 对方案做独立维度 critique，ART-07 对 GOAL/REQ/AC/NFR/STG/VAL 做闭环核对，deterministic checker 将在交付前再验证。

| 类别 | 发现 | 处理 | 结果 |
| --- | --- | --- | --- |
| 缺陷 | 原评估把绑定泄露只作为文案问题，未追到 assertion/result persistence | 引入 input-only BindingContext 与 value-aware scrub，绑定 AC-01/02、VAL-04 | closed |
| 缺陷 | `Future.cancel()` 不能停止已运行 worker | 改为 durable operation + cooperative context，要求 mutation-count 证明 | closed |
| 缺陷 | 用户路径含尾空格与磁盘实际路径不一致 | 只读 `Test-Path` 比较两个 literal，计划使用实际存在路径 | closed |
| 优化 | action/workflow proposal 可能继续割裂 | action 先成为对象，workflow 只引用 ordered IDs，同一 approval intent 恢复 | closed |
| 缺失项 | 旧方案缺 orphan/retention 和安装根验证 | STG-05 增加 reference-safe prune 与 real-copy portability | closed |
| 风险 | receipt/operation/decision 可能演化为分布式基础设施 | 限定本地文件 + 单 owner，不引入 broker/scheduler/event sourcing | bounded |
| 一致性 | production、fixture、CLI、schema、docs 可能各自通过 | VAL-03/07/11/14 强制 public roundtrip 与 source-bound final review | closed |
| 开发质量 | 多模块改造可能造成职责扩散 | sensitivity/operation/activation/retention 各自内聚，service 只编排 | passed |

门禁重跑：Plan Quality、Self-Review、Readiness、draft checker 和 approval checker 已依次重跑；两种 checker 均为 0 error / 0 warning，不生成运行状态文件。

## 就绪门禁（Readiness Gate）

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 目标和验收清楚 | passed | GOAL-01、REQ-01..09、AC-01..14 |
| 上下文已收集 | passed | local audit、evaluation reports、ART-01 |
| 调研门禁已通过 | passed | online-required complete |
| 规范发现门禁已通过 | passed | ART-02 |
| 开发质量门禁已通过 | passed | ART-02/03/06 |
| 候选方案已比较 | passed | A/B/C |
| 决策已记录 | passed | structured closed-loop upgrade |
| 实施阶段已细化 | passed | STG-01..07 |
| 环境已确认 | passed | environment + isolation rules |
| Git 上下文已确认 | passed | HEAD/status/authorization |
| 工具已确认 | passed | tooling + PM gate |
| 验证已确认 | passed | VAL-01..15、ART-05 |
| 最终交付证据已规划 | passed | VAL-14、source hash、cleanup |
| 文档更新已确认 | passed | Skill/references/schema/repo docs |
| 风险已识别 | passed | ART-03/06 + stage rollback |
| 规划自查已通过 | passed | ART-06/07 |
| 阻塞问题已关闭 | passed | 无技术 blocker；Q-07 是本次授权请求 |

就绪结论：`ready_for_approval`。

## 方案批准（Plan Approval）

状态：`approved`。

批准记录：用户于 2026-07-14 明确批准按 `complex-coding-executor` 实施、使用隔离 Termous GUI 验证并进行阶段提交；未授权 push、PR 或其它 external write。

批准摘要：

- 批准范围：`skills/electron-ui-verifier/**`、`evals/electron-ui-verifier/**`、`.github/workflows/electron-ui-verifier.yml`、`README.md`、`CHANGELOG.md` 和本 task runtime evidence。
- 阶段提交授权：用户已明确授权；所有 stage `commit_expectation=stage`，每阶段仅在 review、required validation 和范围检查通过后提交。
- 工具/MCP 授权：请求实现期本地 Termous GUI/进程启动所需 elevated tool；不包含管理员权限、远端 CI、push 或外部服务写入。
- 数据权限：只允许 task tmp、隔离 profile 与测试 knowledge；live knowledge 仅可在用户另行确认 exact fingerprint 后 reset，Termous 默认 profile/data 禁止访问或写入。
- 文档更新授权：批准后可在范围内同步 Skill、reference、schema、assets、README、CHANGELOG 和 dedicated CI。

提交策略：`stage_authorized`；不包含 push、PR 或其它 external write。

## 方案变更门禁（Plan Amendment Gate）

需要重新批准：

- 新增 raw CDP/native launcher/第二 driver、backend、broker、scheduler、vector/LLM 或 SQLite canonical truth。
- 持久化 binding/trace/完整 URL，允许无 postcondition mutation，或削弱独立 risk receipt。
- 增加旧 knowledge compatibility/migration/双写，或让未激活 object 可检索。
- 修改其它 Skill（包括 process-manager）、依赖/公共权限模型、stage DAG、required VAL 或批准 artifacts。
- 访问/修改 Termous 默认 profile/data，执行外部写、远端 push/CI，或进行未授权 commit。
- approved plan/artifacts 变化、attestation mismatch 或 source-bound evidence hash 失配。

无需重新批准：批准范围内不改变 contract 的内部命名、测试 fixture 文案和文档链接修正；executor 只能记入 ledger/evidence，不修改批准文件。

## Artifact Index

| ID | Kind | Path | Required | Approval included | Trigger |
| --- | --- | --- | --- | --- | --- |
| ART-01 | research | `artifacts/research/domain-research.md` | yes | yes | online/high-risk |
| ART-02 | standards | `artifacts/standards/standards-index.md` | yes | yes | full profile |
| ART-03 | architecture | `artifacts/architecture/target-architecture.md` | yes | yes | architecture/data/API |
| ART-04 | architecture | `artifacts/architecture/change-map.md` | yes | yes | multi-module scope |
| ART-05 | validation | `artifacts/validation/validation-strategy.md` | yes | yes | high-risk verification |
| ART-06 | review | `artifacts/reviews/plan-critique.md` | yes | yes | plan self-review |
| ART-07 | other | `artifacts/traceability/traceability-matrix.md` | yes | yes | full traceability |

只列实际 planning artifacts；运行日志、code review、attestation、run-state、ledger 和 commit evidence 由 executor 在批准后创建。

## Executor Handoff

- Planner checker：`draft passed`；`approval passed`，均为 0 error / 0 warning
- Open blocking decisions：none；implementation/elevated authorization requested from user
- Requested implementation authorization：yes
- Requested commit authorization：yes，已由用户明确授权 stage commits
- Requested external-write authorization：no
- Requested elevated-tool authorization：yes，仅 Termous 隔离 GUI/本机进程启动
- Residual risks：Playwright CDP 比原生协议低保真；取消不能撤销已发生副作用，只能阻止后续 mutation 并标记 unknown；真实三平台结果依赖用户 push；旧 knowledge 不迁移。

用户批准后由 executor 生成 attestation 并初始化 run-state/ledger。本文件批准后不可变。

# Electron UI Verifier 稳定性与知识能力升级执行计划

## 规划摘要（Plan Summary）

- Task ID：`2026-07-11-feature-electron-ui-verifier-reliability-upgrade`
- Plan revision：`1`
- Lifecycle route：`managed`
- Plan profile：`full`
- Discovery-first：`yes，已完成本地审计、真实应用基线、知识 benchmark 与在线调研`
- Task contract：`plan-contract.json`
- Approval request：`implementation + 本地 GUI/elevated Termous smoke`；`commit / 无 fingerprint 的 live knowledge reset / push / external write` 未请求

本文件只保存批准意图。批准后不得写入 current stage、progress、运行结果、ledger 摘要或 commit 状态；执行事实由 executor 创建的 `attestation.json`、`run-state.json` 和 `ledger.jsonl` 保存。

## 问题定义（Problem）

目标（Goal）：`GOAL-01`，把当前“能跑一部分小 CDP 请求”的 verifier 升级成对真实 packaged Electron 可稳定使用、速度可量化、证据可信、知识可复用的验证 skill。

非目标（Non-goals）:

- 不覆盖原生文件对话框、UAC、托盘菜单、非 Electron 窗口和系统级视觉 automation。
- 不让 process-manager 托管 Electron GUI，不新增 verifier-owned launcher。
- 不引入 vector database、embedding/LLM service、MCTS、消息 broker 或远程 telemetry。
- 不读取、导入或转换旧 knowledge/workflow 资产；旧布局只可在 exact fingerprint 确认后整体退役并初始化空的新库。
- 不修改 `process-manager`、planner/executor 或其它 skill；若出现必要性，触发重新批准。

验收标准（Acceptance）:

- Termous warm screenshot 10/10 成功、P95 `<=2s`；stale session、target 歧义和重复 detach 不再误报或 internal error。
- strict locator 在多个“连接”候选时停止并给候选，不产生 click；副作用 action 由 postcondition 判定。
- 20 个同秒 action 产生唯一 journal/evidence，最终只有一个 report 和至多一个 pending。
- failed/corrupt/blank artifact 不进入 manifest；pending 只含实际通过路径并由 digest 绑定批准。
- 召回 `Recall@5 >=0.90`、`MRR@5 >=0.80`、负例假阳性 `<=0.05`；低置信明确 abstain。
- 308 资产 ingestion `<=1.5s` 且至少比 4480.26ms 基线快 3 倍；10k query P95 `<=100ms`。
- required test/eval/perf/knowledge-reset/process-manager/Termous/review gates 全部通过且不污染未确认的 live 数据。

约束（Constraints）:

- 使用 current Playwright attach 能力；CDP lower-fidelity 边界必须显式 capability/error 化。
- 当前 workspace SQLite 为 3.51.1，禁止 WAL；性能通过单写者和批量 transaction 实现。
- 新生产 Python 文件 `<=500` 行，CLI/API/domain/adapter 单向依赖，不整仓格式化。
- 所有网络、queue、event、body、artifact、timeout、retry 和 output 有上限。
- Git 命令串行；未知 worktree 变更不覆盖；只有明确授权后才 commit。

待确认项（Open uncertainties）:

- 无规划 blocker。attach context trace 完整度、AI ARIA snapshot 对不同 Electron 的可用性和远端三平台行为均通过 capability/validation 解决，不作为无证据假设。

## 需求与验收（Requirements And Acceptance）

| Requirement | Priority | Outcome | Acceptance |
| --- | --- | --- | --- |
| REQ-01 | must | 模块化 package、ports/adapters、薄 CLI | AC-01 |
| REQ-02 | must | Playwright CDP、service/session 安全生命周期 | AC-02、AC-03 |
| REQ-03 | must | strict action、ARIA observation、postcondition | AC-04、AC-05 |
| REQ-04 | must | run journal、原子 evidence、单次 finalize | AC-06、AC-07 |
| REQ-05 | must | digest/sealed/idempotent pending approval | AC-08 |
| REQ-06 | must | 全新 canonical knowledge、derived index、显式 reset | AC-09 |
| REQ-07 | must | hybrid retrieval、abstain、参数和状态组合 | AC-10、AC-11、AC-12 |
| REQ-08 | must | 精简 skill 流程、依赖、schema、文档 | AC-12、AC-13 |
| REQ-09 | must | tests/evals/Termous/CI/review | AC-14 |

非功能需求：`NFR-01` 可靠性、`NFR-02` 性能/资源有界、`NFR-03` 安全/隐私、`NFR-04` 数据完整性、`NFR-05` 可维护性、`NFR-06` 可观察性、`NFR-07` 可复现/跨平台。

完整 Given/When/Then、stage 和 required validation 映射以 `plan-contract.json` 与 `ART-07` 为准。

## 调研门禁（Research Gate）

研究模式（Research mode）：`online-required`

触发原因（Why this mode）:

- Playwright/CDP/SQLite/WebSocket 行为和近期 GUI agent 研究会随版本变化；稳定性、安全和知识召回不能只依赖记忆。
- 用户明确要求深入研究架构、实现、稳定性、速度和知识设计，并提供真实 Electron 应用。

不确定项清单（Uncertainty inventory）:

| ID | Question | Type | Online | Resolution | Impact |
| --- | --- | --- | --- | --- | --- |
| U-01 | screenshot 是应用问题还是 transport 问题 | local-code/tool | no | 同 target raw 20s timeout、Playwright 257ms 成功 | 删除 raw transport |
| U-02 | 已运行 Electron 如何获得 locator/auto-wait | external-tool | yes | Playwright `connect_over_cdp` 可附加 Chromium，lower fidelity 明示 | 单 driver + capability tests |
| U-03 | 自制 WebSocket 是否可局部修补 | protocol/high-risk | yes | RFC 要求 fragmentation/control；当前实现不满足 | 删除而非修补 |
| U-04 | 中文知识查询为何 miss/false hit | local-code/standard | yes | 无 BM25、unicode61、supplement filler；benchmark 复现 | hybrid + threshold/abstain |
| U-05 | 是否用 WAL 加速 | data/high-risk | yes | 当前 SQLite 3.51.1 在 WAL-reset 影响范围 | 禁止 WAL，batch transaction |
| U-06 | GUI 验证如何避免只看动作成功 | primary research | yes | OSWorld 使用 initial state + execution evaluator | required postcondition/final state |
| U-07 | skill 上下文为何重 | local-doc/system skill | no | 每任务强制读 3 refs，违反 progressive disclosure | conditional references |

搜索记录、完整来源矩阵和本地 benchmark 见 `ART-01`。调研结论（Research result）：`passed`。

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）：`online-required`

技术栈：Python 3.10+、Playwright async/CDP、localhost HTTP、JSON Schema 2020-12、SQLite/FTS5、process-manager、Codex skill progressive disclosure。

规范来源：项目 `AGENTS.md` 与 planner/skill-creator 为最高优先本地规则；外部使用 Google Python、Playwright locator/actionability/CDP/trace、Chrome CDP、RFC 6455、JSON Schema、SQLite FTS/transaction/WAL、PyPA、Chrome remote debugging、OSWorld 和 RRF 一手来源。

standards index：`artifacts/standards/standards-index.md`。没有 blocked-by-access；近期预印本只作为方向性参考，不承担硬 contract。规范发现结论（Standards result）：`passed`。

## 开发质量门禁（Development Quality Gate）

| Dimension | Plan | Stage | Validation |
| --- | --- | --- | --- |
| Code standards | 中文设计注释、Google Python、类型化 public boundary、稳定 error code | STG-01 至 STG-06 | VAL-01、VAL-05、VAL-11 |
| Static quality | import/cycle/file budget、schema/help/docs drift、禁止 raw/domain token/live test write | STG-01/05/06 | VAL-05、VAL-06、VAL-11 |
| Architecture | CLI/API -> domain -> ports -> adapters；automation 单 owner | STG-01/02 | VAL-01、VAL-08、VAL-11 |
| Patterns | actor queue、unit of work、state machine、canonical source/derived index、RRF strategy | STG-02 至 STG-05 | VAL-01、VAL-03、VAL-10 |
| Low coupling | driver 不依赖 report/knowledge，retrieval 不依赖 Playwright，CLI 不复制业务 | all | cycle/import/static review |
| High cohesion | config/security、session、action、run、approval、knowledge 独立模块 | all | file budget、unit isolation、review |

过度设计防护：只实现一个 Playwright driver；不引入 vector/embedding、外部 DB、broker、MCTS 或 native UI；只有 lexical/state benchmark 仍失败且重新批准才扩展。开发质量结论：`passed`。

## 上下文（Context）

本地代码：

- `ev_server.py` 1700 行、`ev_knowledge_store.py` 883 行；skill 共 36 个脚本且没有 tests/evals。
- WebSocket/CDP、locator、session、run/report/pending、knowledge/persistence 的详细调用和风险见 `ART-01`、`ART-04`。
- 当前 smoke 都能通过，但未覆盖真实大 CDP response、歧义、stale session、未解析 params、false-positive 或证据一致性。

本地文档：

- 读取 current `SKILL.md`、所有 references/assets 与 9 份历史 Electron harness 计划。
- 历史增量方案保留了 raw primary、SQLite primary 和业务 hard-code；本次直接切换 current implementation，不保留长期兼容分支。

用户约束：

- 深入分析后先生成详细 harness 方案；本阶段不改生产代码。
- 真实测试应用可用 `D:\SoftWare\Termous\Termous.exe`。
- Termous 测试必须安全、隔离、只读；授权边界仍按 planner/executor contract 执行。

证据等级：

| Claim | Level | Source | Impact |
| --- | --- | --- | --- |
| raw screenshot 稳定超时 | confirmed | Termous 两次 20s probe report | 移除 transport |
| Playwright 同 target 截图正常 | confirmed | 106541-byte screenshot + timing | 选择主 driver |
| stale reuse/目录覆盖/pending 污染 | confirmed | runtime report/session/process probes | run/session 重构 |
| 召回 0/3 改写、负例 false hit | confirmed | 308-asset benchmark | retrieval 重构 |
| Playwright lower fidelity/strict/actionability | external official | Playwright docs | capability 与 action contract |
| state graph 可改善 executable memory | external primary/directional | OSWorld、Agent S、EAM | 只采用 state compatibility |

## 候选方案（Options）

### 方案 A：最小修补 raw CDP

- 做法：补 fragmentation、pending map、event bound；增加 retry、BM25 和几项 smoke。
- 优点：文件改动较少，CLI 行为变化小。
- 缺点：继续维护 WebSocket/CDP/actionability/locator；单体、run/pending、canonical knowledge 根因未解决。
- 风险：截图问题可能暂时缓解但协议组合、并发和后续 Chromium 漂移仍由项目承担。
- 验证/回滚：protocol fuzz 与 Termous；可回滚，但收益不足。

### 方案 B：长驻 service + Playwright/domain 重构（选择）

- 做法：Playwright async 单 driver、模块化 service、strict action、run transaction、canonical knowledge、hybrid retrieval。
- 优点：复用已有依赖和成熟 locator/actionability；从根上解决 transport、重复 I/O、证据和召回边界。
- 缺点：改动面大，需要新 schema、旧布局拒绝/reset 和完整测试体系。
- 风险：`connect_over_cdp` fidelity 受限；通过 capability/Termous/fixture fail closed。
- 验证/回滚：阶段开关只用于实施期切换，最终无双 runtime；旧目录整体退役且不被读取，新空库可直接重建。

### 方案 C：移除 service，每个 CLI 一次性连接

- 做法：每次脚本启动 Playwright、attach、执行、退出。
- 优点：服务状态更少。
- 缺点：重复 1.5s 左右 connect、无法稳定复用 session/run、连续任务更慢，知识 writer 并发更难控制。
- 风险：把当前“常驻连接价值”一并丢掉。
- 验证/回滚：不采用。

## 决策（Decision）

选择方案：`B`。

原因：真实对照已证明 Playwright 在同一 Termous target 正常，而 raw transport 失败；Playwright 也提供 strict locator、auto-wait、actionability、ARIA 和 trace。长驻 service 对连续 UI 验证仍有明确连接复用价值。

影响：现有非知识 CLI 名尽量保留，但行为切换为 current typed contract；新增 prepare/finalize 与 `ev_init --reset-knowledge`。旧 knowledge 不迁移、不兼容、不进入新索引。

可逆性：代码可整体回滚；reset 前用 fingerprint 绑定旧 root，旧目录整体移动到 retired 区且新 runtime 永不读取；derived index 可从新 canonical 重建。

方案变更触发条件：见 contract `reapproval_triggers`，尤其是第二 backend、native UI、vector/LLM、旧知识导入、reset/删除策略、安全边界、其它 skill 和 Termous 写操作。

## 影响面矩阵（Impact Matrix）

| Surface | Involved | Files/modules | Risk | Validation | Docs |
| --- | --- | --- | --- | --- | --- |
| Internal API | yes | service protocol、ev_* envelope | high | unit/eval/PM/Termous | server/workflow |
| Data model | yes | schemas、canonical、SQLite index、pending | high | schema/reset/rebuild | knowledge/persistence |
| Frontend interaction | yes | locator/action/assertion/ARIA/screenshot | high | fixture + Termous | actions/workflow |
| Config/environment | yes | requirements、limits、token、endpoint/profile | high | fresh-env/security | server/troubleshooting |
| Compatibility | no for knowledge | 旧 knowledge/workflow 不读取、不导入；直接初始化 current store | medium | rejection/reset/rebuild | reset note |
| Tests | yes | tests/evals/CI | medium | all VALs | eval README only if repository convention requires |
| Documentation | yes | SKILL、refs、assets、metadata、README/CHANGELOG | medium | quick_validate/drift | required |
| Architecture | yes | package、worker、run、knowledge | high | import/cycle/review | architecture reflected in refs |

## 实施计划（Implementation Plan）

阶段依赖、引用、授权、文件范围和验证以 `plan-contract.json` 为机器真相源；以下解释实施顺序和工程理由。

### STG-01：契约、package 与隔离测试地基

目标：先冻结 current schema、error/envelope、limits 和 dependency direction，使后续重构可被 fixture 驱动，而不是继续在单体中改一处测一处。

做法：

- 新建 `electron_verifier` package 的 config/security/error/protocol/schema/atomic I/O 基础模块。
- 为 action、locator、assertion、run、evidence、pending、canonical knowledge 定义 Draft 2020-12 schema 和 typed decode。
- 新建独立 `tests/` 与 `evals/electron-ui-verifier/`，把 current smoke 基线转为 temp-root fixture。
- 确认 Playwright 测试版本和必要 schema/PNG validator 依赖，形成 concrete lock；`ev_check_env` 显示 Python、Playwright、SQLite/version/journal safety。
- 增加 import cycle、生产文件行数、raw transport/domain hard-code/live-root test write 的 static gates。

原因：先有 contract 和隔离 fixture，STG-02 至 STG-05 才能直接替换实现而不保留永久双路径。

位置：schemas、`scripts/electron_verifier/**` 基础模块、tests、evals、requirements；不改其它 skill。

参考/规范：ART-02 的 Google Python、JSON Schema、PyPA；ART-03 package 边界。

开发质量：public dataclass/protocol 类型化；异常不吞；关键 JSON 原子写；每文件 <=500 行；禁止循环依赖。

验证：VAL-01、VAL-05、VAL-07。风险是过早抽象；以现有调用方和 contract 所需字段为上限，不建通用 automation framework。

阶段契约：依赖无；覆盖 REQ-01/AC-01/NFR-04/05/07；允许/禁止路径、entry/exit 和 no-commit 见 contract。

Stage Contract mirror：

- `depends_on=[]`；`requirement_ids=[REQ-01]`；`acceptance_ids=[AC-01]`；`nonfunctional_ids=[NFR-04,NFR-05,NFR-07]`；`validation_ids=[VAL-01,VAL-05,VAL-07]`。
- allowed：`skills/electron-ui-verifier/schemas/**`；`skills/electron-ui-verifier/scripts/electron_verifier/**`；`skills/electron-ui-verifier/tests/**`；`skills/electron-ui-verifier/requirements*.txt`；`evals/electron-ui-verifier/**`。
- forbidden：`skills/process-manager/**`；`skills/complex-coding-planner/**`；`skills/complex-coding-executor/**`；`真实 Electron profile/knowledge 数据`；`无关 skill 或全仓格式化`。

### STG-02：Playwright driver、service 与 session 生命周期

目标：让成熟 Playwright transport/action substrate 真正成为唯一 runtime，彻底关闭已复现的 raw CDP 和 stale session 故障。

做法：

- 在一个 async automation owner 中启动 Playwright；HTTP handler 只 auth/schema/queue，不跨线程访问 handles。
- 使用 `connect_over_cdp`，本机设置 `is_local`，已有 context 设置 `no_defaults`；通过 CDP session 暴露可选 diagnostics。
- 在任何 HTTP probe 前校验 endpoint，限制 loopback；remote 使用精确 allowlist + 显式批准，无 redirect。
- 建立 SessionIntent 与 LiveSession 分离、target selector/capability、health-before-reuse、reconnect、target close/new page 事件和幂等 detach。
- service 使用有界 body/queue/event/deadline，优雅 shutdown；token 使用 constant-time compare 与 owner-only 权限。
- 删除 `MinimalWebSocket`、`CDPClient` 和死 `detect_playwright` 生产路径，不提供 raw fallback。

原因：Termous 对照已经把截图故障隔离到 raw 链路；继续修协议会重复 Playwright 的成熟能力并扩大维护面。

位置：server/init/probe/attach/sessions/detach、package service/automation/driver/session/security、对应 tests/evals。

参考/规范：Playwright connect/async docs、Chrome CDP、RFC 6455、remote debugging security。

开发质量：driver port 不依赖 report/knowledge；worker ownership 可静态与运行时断言；副作用 timeout 不在本阶段重试。

验证：multi-target、target death、server restart、repeat detach、remote rejection、body/queue limits、PM smoke；Termous 首轮 attach + 10 screenshots。风险是 lower fidelity；主能力缺失即 blocker，不悄悄恢复 raw。

阶段契约：依赖 STG-01；覆盖 REQ-02/AC-02/03；VAL-01/04/05/07/08/09；无阶段 commit。

Stage Contract mirror：

- `depends_on=[STG-01]`；`requirement_ids=[REQ-02]`；`acceptance_ids=[AC-02,AC-03]`；`nonfunctional_ids=[NFR-01,NFR-02,NFR-03,NFR-05,NFR-06,NFR-07]`；`validation_ids=[VAL-01,VAL-04,VAL-05,VAL-07,VAL-08,VAL-09]`。
- allowed：`skills/electron-ui-verifier/scripts/ev_server.py`；`skills/electron-ui-verifier/scripts/ev_init.py`；`skills/electron-ui-verifier/scripts/ev_probe.py`；`skills/electron-ui-verifier/scripts/ev_attach.py`；`skills/electron-ui-verifier/scripts/ev_sessions.py`；`skills/electron-ui-verifier/scripts/ev_detach.py`；`skills/electron-ui-verifier/scripts/electron_verifier/**`；`skills/electron-ui-verifier/tests/**`；`evals/electron-ui-verifier/**`。
- forbidden：`第二 automation backend`；`手写 WebSocket/raw frame fallback`；`verifier 托管 Electron GUI`；`未批准 remote CDP`；`无界 queue/event/body/timeout`。

### STG-03：严格 action、run 事务与可信证据

目标：把“发出 CDP 命令”升级成“在已知状态对唯一元素执行动作，并用 postcondition 与证据证明结果”。

做法：

- 实现 role/name、label、placeholder、text、test-id、title、CSS typed locator；默认 exact/strict，歧义返回候选。
- 使用 Playwright locator/actionability/fill/keyChord；coordinate 明示高风险、不可默认学习。
- 实现 assertion contract 和 retry 分类：只重试定位/readiness，不重放未知副作用。
- 默认 compact AI ARIA snapshot；ephemeral ref 只在本 run；experimental diagnostics capability 隔离。
- 新增 `ev_prepare` 建立 run，action 只 append journal；workflow 单 command；`ev_finalize` 一次产 report/pending。
- run 使用 UUID、monotonic duration、pre/post state；crash replay 明确 passed/failed/aborted/unknown。
- evidence 使用 temp/validate/fsync/replace/hash/manifest；PNG 解码、尺寸、有效像素；trace 默认 failure-only。

原因：当前静默点击最小候选、直接赋值 input、秒级目录和每 action pending 同时损害正确性、速度和审计性。

位置：action/workflow/diagnostic/report/artifact CLIs、package locator/action/assertion/run/evidence/report、schemas/tests/evals。

参考/规范：Playwright locator/actionability/ARIA/trace、OSWorld execution evaluator、ART-03 run design。

开发质量：run state transition 使用封闭 enum/transition table；artifact path 只能从 committed manifest 派生；独立 diagnostics 与 mutation path 分离。

验证：Termous “连接” strict trial、controlled fixture、unknown outcome、20-action unique run、corrupt/blank screenshot、continue diagnostics、crash replay。风险是 run API 变化；保留现有 CLI 名作为薄适配，不保留旧语义双写。

阶段契约：依赖 STG-02；覆盖 REQ-03/04、AC-04 至 AC-07；VAL-01/04/05/08/09；无阶段 commit。

Stage Contract mirror：

- `depends_on=[STG-02]`；`requirement_ids=[REQ-03,REQ-04]`；`acceptance_ids=[AC-04,AC-05,AC-06,AC-07]`；`nonfunctional_ids=[NFR-01,NFR-02,NFR-03,NFR-04,NFR-05,NFR-06]`；`validation_ids=[VAL-01,VAL-04,VAL-05,VAL-08,VAL-09]`。
- allowed：`skills/electron-ui-verifier/scripts/ev_action.py`；`skills/electron-ui-verifier/scripts/ev_workflow.py`；`skills/electron-ui-verifier/scripts/ev_snapshot.py`；`skills/electron-ui-verifier/scripts/ev_screenshot.py`；`skills/electron-ui-verifier/scripts/ev_console.py`；`skills/electron-ui-verifier/scripts/ev_exceptions.py`；`skills/electron-ui-verifier/scripts/ev_network.py`；`skills/electron-ui-verifier/scripts/ev_report.py`；`skills/electron-ui-verifier/scripts/ev_artifact.py`；`skills/electron-ui-verifier/scripts/ev_prepare.py`；`skills/electron-ui-verifier/scripts/ev_finalize.py`；`skills/electron-ui-verifier/scripts/electron_verifier/**`；`skills/electron-ui-verifier/schemas/**`；`skills/electron-ui-verifier/tests/**`；`evals/electron-ui-verifier/**`。
- forbidden：`歧义静默首选`；`无 postcondition 自动副作用`；`未知 outcome 重放`；`证据写前登记`；`每 action 自动 report/pending`；`默认采集 cookie/storage/Authorization`。

### STG-04：批准完整性与全新 canonical knowledge 直接切换

目标：让用户批准精确绑定一份可验证 pending，并把可执行知识从不可审计 SQLite 行变为可重建 canonical assets。

做法：

- finalize 只保留 actual passed/non-detour path；required assertion/evidence/params/risk 不满足即不可 approve。
- pending manifest 绑定 app/target/run、workflow、evidence hashes 和 canonical digest；approve 必须提交 exact fingerprint。
- decision marker exclusive/sealed，content-addressed asset id 保证幂等；canonical 先原子落盘、index 事务随后更新、decision 最后写。
- 定义 App/Screen/Element/Action/Workflow/Evidence/Alias canonical schema、兼容 fingerprint、pre/post state 和 success/failure stats。
- SQLite 启用 foreign keys、busy timeout、single writer、batch transaction 和 rebuild/verify；当前 runtime 显式保持 rollback journal。
- 新 runtime 只识别 current canonical schema；检测到旧 DB/workflow 布局时返回 `knowledge_reinitialize_required`，绝不读取或导入旧内容。
- `ev_init --reset-knowledge` 先预览旧 root identity/digest 和目标空库，再要求 exact fingerprint；确认后整体移动旧 root 到 retired 区并原子建立空的新库。
- retired root 只作为人工回退文件保留，生产 reader/indexer 永不扫描；新 index 仅从新 canonical assets 重建。

原因：当前 approve 可固化 failed/unexecuted path，SQLite 又既是 truth 又无法稳健重建，任何检索优化都建立在不可靠数据上。

位置：init/pending/persist/learn/promote/knowledge store/extract、package approval/canonical/index/reset、schemas/tests/evals。

参考/规范：JSON Schema、SQLite transaction/WAL、ART-03 approval/direct-cutover。

开发质量：不承诺不存在的跨文件 ACID，以 canonical-first 可恢复顺序和 idempotency 收口；不编写旧 schema converter；reset 只操作 fingerprint 绑定的精确 root。

验证：failed/missing/TOCTOU/repeat approve、partial write、fresh init、legacy rejection、wrong fingerprint、retired-root isolation、empty-store activation 和 rebuild/corruption。风险是 reset 指错目录；路径边界和 digest 必须双重校验。

阶段契约：依赖 STG-03；覆盖 REQ-05/06、AC-08/09；VAL-01/05/10；无阶段 commit。

Stage Contract mirror：

- `depends_on=[STG-03]`；`requirement_ids=[REQ-05,REQ-06]`；`acceptance_ids=[AC-08,AC-09]`；`nonfunctional_ids=[NFR-01,NFR-03,NFR-04,NFR-05,NFR-06]`；`validation_ids=[VAL-01,VAL-05,VAL-10]`。
- allowed：`skills/electron-ui-verifier/scripts/ev_init.py`；`skills/electron-ui-verifier/scripts/ev_pending.py`；`skills/electron-ui-verifier/scripts/ev_persist.py`；`skills/electron-ui-verifier/scripts/ev_learn.py`；`skills/electron-ui-verifier/scripts/ev_promote.py`；`skills/electron-ui-verifier/scripts/ev_knowledge_store.py`；`skills/electron-ui-verifier/scripts/ev_knowledge_extract.py`；`skills/electron-ui-verifier/scripts/electron_verifier/**`；`skills/electron-ui-verifier/schemas/**`；`skills/electron-ui-verifier/tests/**`；`evals/electron-ui-verifier/**`。
- forbidden：`旧 knowledge schema reader/import/converter`；`failed/unexecuted 自动提升`；`无 fingerprint approve/reset`；`永久双 schema/双写`；`当前 SQLite 3.51.1 WAL`；`静默覆盖或读取旧知识目录`。

### STG-05：混合召回、资产复用与精简 skill 流程

目标：把“快速返回若干历史行”升级成“高相关、可拒答、可解释、状态兼容的可执行经验”，同时减少 agent 前置上下文和命令数。

做法：

- normalization 生成 exact/alias、Latin token、CJK bigram/trigram；FTS 按 BM25 排序。
- 先做 app/version/screen/risk filter，再以 RRF 融合通道并叠加 evidence/success/staleness；执行 `minScore/minMargin` abstain。
- 删除 `supplemental_actions`、VideoForensic extractor 和 hard-coded subgoal keywords。
- progressive subgoals 由 agent 作为参数提供；默认最多 3 个 compact candidates，详情只在 `--explain`。
- 只有 action state edge 可连接、params 已绑定且风险允许时组合 workflow；unresolved `${param}` fail closed。
- 重写 SKILL 为 prepare/run/finalize 核心与条件 reference 索引；bootstrap/动作/知识/故障各读对应 reference。
- 更新 assets/schema/help/agent metadata、README/CHANGELOG；tests 默认 temp，旧 scripts smoke 不再污染 live knowledge。

原因：当前 query latency 已很低，真正问题是 0/3 改写召回和无关 filler；vector 化不是首要解。

位置：knowledge/suggest/assets/extract/runner/export、package retrieval/index、SKILL/references/assets/metadata/requirements、evals/docs。

参考/规范：SQLite FTS5、RRF、Agent S 分层经验、skill-creator progressive disclosure。

开发质量：每个 rank feature 可解释且独测；Termous/VideoForensic 不进入生产 token；默认输出有字节预算；不复制外部规范全文。

验证：40+ positive/20+ negative corpus、Recall/MRR/false-positive、state/params property tests、308/10k benchmark、prepare stdout、quick_validate/skill eval/fresh env。风险是手工 alias 过拟合；corpus 跨 app/语言，exact 与 ngram 之外保留 abstain。

阶段契约：依赖 STG-04；覆盖 REQ-07/08、AC-10 至 AC-13；VAL-01 至 VAL-07 的相关 gates；无阶段 commit。

Stage Contract mirror：

- `depends_on=[STG-04]`；`requirement_ids=[REQ-07,REQ-08]`；`acceptance_ids=[AC-10,AC-11,AC-12,AC-13]`；`nonfunctional_ids=[NFR-02,NFR-03,NFR-04,NFR-05,NFR-06,NFR-07]`；`validation_ids=[VAL-01,VAL-02,VAL-03,VAL-04,VAL-05,VAL-06,VAL-07]`。
- allowed：`skills/electron-ui-verifier/SKILL.md`；`skills/electron-ui-verifier/agents/openai.yaml`；`skills/electron-ui-verifier/references/**`；`skills/electron-ui-verifier/assets/**`；`skills/electron-ui-verifier/requirements*.txt`；`skills/electron-ui-verifier/scripts/ev_knowledge.py`；`skills/electron-ui-verifier/scripts/ev_suggest.py`；`skills/electron-ui-verifier/scripts/ev_assets.py`；`skills/electron-ui-verifier/scripts/ev_asset_extract.py`；`skills/electron-ui-verifier/scripts/ev_asset_runner.py`；`skills/electron-ui-verifier/scripts/ev_export_workflow.py`；`skills/electron-ui-verifier/scripts/electron_verifier/**`；`skills/electron-ui-verifier/tests/**`；`evals/electron-ui-verifier/**`；`README.md`；`CHANGELOG.md`；`.gitignore`。
- forbidden：`VideoForensic/Termous 业务词进入生产检索`；`无关 recent action 补齐`；`未绑定占位符执行`；`vector DB/embedding/LLM service`；`每任务强制读取全部 references`；`v1/v2 并行入口`。

### STG-06：真实应用验收、跨平台准备与最终审查

目标：在真实 Termous、隔离 fixtures 和完整 diff 上证明主流程、数据边界、速度和 cleanup，而不是只依赖 unit happy path。

做法：

- 重跑全部 required unit/eval/retrieval/perf/static/skill/fresh-env/PM/knowledge-reset gates。
- 按 ART-05 Termous protocol 启动隔离 profile，只做 screenshot、snapshot、strict ambiguity 和安全页面导航。
- app exit 后验证 stale reuse；repeat detach；finalize 一次；`--no-learn`；停止 verifier/manager/Termous test tree。
- 定义 Windows/Ubuntu/macOS fixture Chromium matrix；只提交 workflow 文件，本任务不 push/触发 Actions。
- 做 architecture/security/data/retrieval/tests/docs final review，检查 staged scope、diff、秘密和 process/handle 残留。
- 只有用户另行授权 commit 时，最终一次使用 `git commit -F`，不产生阶段 commit 或多余空行。

原因：真实 packaged Electron 暴露了 smoke 未覆盖的大消息和生命周期故障；最终验收必须回到真实应用。

位置：本 contract 所有批准路径、task artifacts/tmp；不修改 Termous 或 live knowledge。

验证：VAL-01 至 VAL-11 required；VAL-12 optional external matrix。风险是 GUI/elevation 或 remote CI 不可用；前者是 required blocker，后者记录 residual risk 且不伪造 passed。

阶段契约：依赖 STG-05；覆盖全部 requirements/AC/NFR；final commit expectation 仅在获得授权后生效。

Stage Contract mirror：

- `depends_on=[STG-05]`；`requirement_ids=[REQ-01,REQ-02,REQ-03,REQ-04,REQ-05,REQ-06,REQ-07,REQ-08,REQ-09]`；`acceptance_ids=[AC-01,AC-02,AC-03,AC-04,AC-05,AC-06,AC-07,AC-08,AC-09,AC-10,AC-11,AC-12,AC-13,AC-14]`；`nonfunctional_ids=[NFR-01,NFR-02,NFR-03,NFR-04,NFR-05,NFR-06,NFR-07]`；`validation_ids=[VAL-01,VAL-02,VAL-03,VAL-04,VAL-05,VAL-06,VAL-07,VAL-08,VAL-09,VAL-10,VAL-11,VAL-12]`。
- allowed：`skills/electron-ui-verifier/**`；`evals/electron-ui-verifier/**`；`.github/workflows/electron-ui-verifier.yml`；`README.md`；`CHANGELOG.md`；`.gitignore`；`.harness/tasks/2026-07-11/feature/electron-ui-verifier-reliability-upgrade/artifacts/**`；`.harness/tasks/2026-07-11/feature/electron-ui-verifier-reliability-upgrade/tmp/**`。
- forbidden：`Termous 安装目录/默认 profile/真实凭据`；`创建主机/连接 SSH/端口转发写操作`；`无 fingerprint 的 live knowledge reset`；`远端 CI/push 未授权`；`未授权 commit`；`修改批准后的 plan/contract/artifacts`。

## 环境（Environment）

Workspace 来源：`.harness/environment.md`。该文件含历史 task 描述，执行器以本 task contract 和 active pointer 为 task 真相源，不把历史“current active task”句子当作本任务状态。

本任务使用：

- Workspace：`D:\Item\vibe_coding\dev-skills`
- Python：当前 3.13.12；实施支持范围由 STG-01 lock 冻结，最低不低于 current skill 的 3.10。
- SQLite：当前 `3.51.1`，命中官方 WAL-reset 影响范围，强制 rollback journal。
- Termous：`D:\SoftWare\Termous\Termous.exe`，product 0.1.0 / Electron 30.5.1；隔离 profile 和 loopback CDP。
- Baseline runtime/evidence：`.harness/electron-ui-verifier/`，只读参考；新的测试输出使用 task `tmp/` 和 `artifacts/validation/`。

临时覆盖：fresh venv、fixture CDP 端口、Termous isolated profile 均位于 task tmp；不得写 live knowledge。

## Git 上下文（Git Context）

- Main / working branch：main / `harness/feature`。
- Branch status：本地相对 `origin/harness/feature` ahead 1；来源不归因、不重写；规划开始时 worktree 无 tracked 修改。
- Task type / branch action：feature；不新建或切换分支。
- Git 命令串行；不自动 stash/rebase/reset，不覆盖未知变更，index.lock 只按 current executor 规则处理。
- Commit authorization：`not requested`；最终 `commit_expectation=final` 只表示获得授权后的策略。
- Branch closure：不 push、不 merge、不删分支；远端 matrix 由用户后续 push 或单独授权。

## 工具（Tooling）

| Tool | Purpose | Stage | Status | Risk/authorization | Alternative |
| --- | --- | --- | --- | --- | --- |
| Python/venv | tests、service、eval、fresh env | all | available | 依赖安装写 task tmp；网络需授权 | 现有 interpreter 仅作本地 tests |
| Playwright | sole Electron CDP driver | STG-02+ | baseline 1.61 worked | 锁定版本；不下载 browser for attach | 无 raw fallback |
| process-manager | verifier service lifecycle | STG-02/06 | current contract available | 普通 CLI；Windows ACL 可能需 elevated | blocker，不手写后台 shell |
| Termous | packaged Electron acceptance | STG-02/06 | available | GUI/elevated + isolated profile 授权 | fixture 不能替代 required real gate |
| Web research | official/primary standards | planning | complete | read-only | local docs if source unavailable |
| Git | diff/status/final commit | STG-06 | available | commit 未授权 | no commit |
| GitHub Actions | 3-platform matrix | post-push | not authorized | external push/run | local + workflow definition residual |

## 长期进程管理（Process Manager Gate）

- Needs long-running process：`yes`，仅 verifier service；Termous GUI 本体明确不由 manager 托管。
- Bootstrap：统一 `pm_manager.py status|start`；manager config 缺失才 `pm_init.py`；普通流程不先 doctor、不判断 OS/backend。
- Evidence：authenticated manager identity、service config validation、processKey、ready、bounded logs、graceful-force stop、`cleanupVerified:true`、`stopResult.ownerEmpty:true`。
- Termous test process tree 由本轮 launch record 单独跟踪并在 finally 停止；不使用任意 PID 搜索/终止。
- Fallback：manager 无法证明 ownership/cleanup 时停止，不能手写后台 PowerShell 或 `Start-Process` 绕过。

## 验证（Validation）

| VAL | Required | Kind | Covers | Evidence | Failure handling |
| --- | --- | --- | --- | --- | --- |
| VAL-01 | yes | unit/component | schema/session/action/run/approval/index | unit-component-tests.txt | repair and rerun |
| VAL-02 | yes | skill eval | workflow/progressive disclosure | skill-evals.json | repair skill/docs/scripts |
| VAL-03 | yes | retrieval | AC-10/11/12 | retrieval-benchmark.json | tune explainable channels/threshold |
| VAL-04 | yes | performance | screenshot/run/ingest/query/output | performance.json | profile, repair, keep thresholds |
| VAL-05 | yes | static | architecture/security/drift | static-checks.json | fail on prohibited path/pattern |
| VAL-06 | yes | skill validate | SKILL metadata/structure | skill-validation.txt | repair and rerun |
| VAL-07 | yes | fresh environment | dependency/runtime reproducibility | fresh-env.txt | repair lock/checker |
| VAL-08 | yes | PM integration | service ownership/lifecycle | process-manager-smoke.json | cleanup then repair/rerun |
| VAL-09 | yes | Termous real smoke | packaged Electron end-to-end | termous-smoke.json | blocker if main capability fails |
| VAL-10 | yes | knowledge reset | legacy rejection/fingerprint/retired isolation/rebuild | knowledge-reset.json | reject unconfirmed reset |
| VAL-11 | yes | final review | all AC/NFR | final-code-review.md | repair and rerun affected gates |
| VAL-12 | no | remote matrix | platform parity | platform-matrix.json | record not_run/residual without push |

完整命令、场景、threshold、Termous protocol 和 cleanup 见 ART-05；contract 是 validation IDs/coverage/evidence path 真相源。

## 文档（Documentation）

必需更新：

- `SKILL.md`：精简 current prepare/run/finalize、安全与批准规则、条件 reference 索引。
- `references/server.md`：Playwright service/session/endpoint/process-manager。
- `references/actions.md` 与 `workflow.md`：typed locator/action/assertion/run/schema。
- `references/knowledge.md`：canonical/index/retrieval/abstain/params/direct reset/persistence。
- `references/troubleshooting.md`：capability、stale、timeout、evidence、knowledge reset、cleanup。
- assets、CLI help、agent metadata、requirements、README/CHANGELOG 与 current behavior 同步。

不创建额外 README/quick guide/changelog 于 skill 内；详细 schema 作为 machine assets，规范全文不复制。仓库 CHANGELOG 明确记录旧知识不导入以及 reset 行为。

## 文件写入策略（File Write Strategy）

| File/group | Segmented | Semantic boundaries | Whole-file check |
| --- | --- | --- | --- |
| `ev_server.py` -> package | yes | bootstrap/router/worker/driver/session | import/cycle/line count/tests |
| action/run/evidence modules | yes | locator/action/assertion/state/evidence/report | schema + unit + end-to-end |
| knowledge modules | yes | model/canonical/index/retrieval/reset | fresh-init/rebuild/quality/perf |
| SKILL/references | yes | core flow and one-level conditional topics | quick_validate/link/drift |
| schemas/assets/evals/tests | per file | one schema/fixture/runner concern | parse/discover/eval |
| execution artifacts | per stage | validation/review evidence | executor attestation/ledger only |

大文件先定点抽取，不整文件重写；每次 patch 按完整 class/function/section，建议 <=120 行、最多 200 行；失败后检查部分写入，阶段退出前重读整文件和 diff。

## 问题和覆盖项（Questions And Overrides）

| ID | Blocking | Status | Decision | Applied to |
| --- | --- | --- | --- | --- |
| Q-01 | no | resolved | 实际 Termous 路径无目录尾空格，使用 `D:\SoftWare\Termous\Termous.exe` | VAL-09 |
| Q-02 | no | resolved | production 只实现 Playwright driver，不保留 raw fallback | STG-02 |
| Q-03 | no | resolved | 当前 SQLite 3.51.1 不使用 WAL | STG-04/05 |
| Q-04 | no | resolved | 旧知识不兼容、不导入；切换只允许 fingerprint reset 后整体退役旧 root | STG-04/06 |
| Q-05 | no | resolved | remote matrix optional；本任务不 push | VAL-12 |
| Q-06 | yes at execution | open authorization | 用户需批准 implementation 与本地 GUI/elevated Termous smoke | approval |

## 方案质量门禁（Plan Quality Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| Evidence levels assigned | passed | Context + ART-01 |
| Research Gate complete | passed | ART-01, online-required |
| Standards Discovery complete | passed | ART-02 |
| Development Quality complete | passed | quality mapping + ART-02/03 |
| Impact matrix complete | passed | plan + ART-04 |
| Options compared | passed | A/B/C with risk/rollback |
| Stages independently verifiable | passed | 6 stage contracts + VAL mapping |
| Reapproval triggers clear | passed | contract + ART-03 |
| Approval summary ready | passed | implementation/elevated requested; other writes excluded |

质量结论：`passed`。

## 规划自查（Plan Self-Review）

自查结论：`passed`；由于无可用独立 evaluator，使用 ART-06 声明受限的 self-review fallback，并以 deterministic checker 补强。

| Category | Finding | Action | Result |
| --- | --- | --- | --- |
| Defects | 初版 stage prose 未镜像 contract，draft 报 188 条 drift | 增加 STG-01..06 exact contract mirror | closed，draft 0/0 |
| Optimizations | ARIA capability 和三平台证据表述过强 | 增加同 driver 观测降级；NFR-07 区分 required contract 与 optional matrix | closed |
| Missing items | artifact 权限只强调 token | 扩大 owner-only/DACL 到 runtime root | closed |
| Risks | knowledge reset、Termous 连接、SQLite WAL | exact root fingerprint、strict trial、non-WAL guard | closed |
| Consistency | contract/plan/artifact/validation 可能漂移 | ART-07 trace + draft/approval checker | passed |
| Development quality | 可能引入第二 backend、vector memory 或跨 skill scope | reapproval triggers 和 forbidden changes 明确阻止 | passed |

门禁重跑：Plan Quality、Self-Review、Readiness、draft checker 和 approval checker 已重跑；均为 0 error / 0 warning。

## 就绪门禁（Readiness Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| Goal/acceptance clear | passed | contract GOAL/REQ/AC |
| Context collected | passed | local audit + Termous + benchmark |
| Research/Standards/Quality passed | passed | ART-01/02/03 |
| Options/decision recorded | passed | plan decision |
| Stages detailed | passed | STG-01..06 |
| Environment/Git/tooling/process confirmed | passed | plan sections |
| Validation/final evidence planned | passed | ART-05 + VAL-01..12 |
| Documentation/risks confirmed | passed | docs + reapproval/stop |
| Plan self-review passed | passed | ART-06；blocking findings none |
| Blocking questions closed | passed | 无技术 blocker；Q-06 是本轮批准请求 |

就绪结论：`ready_for_approval`。

## 方案批准（Plan Approval）

状态：`not_requested`

批准记录：等待用户确认本计划及 approval-included artifacts。

批准摘要：

- 批准范围：`skills/electron-ui-verifier/**`、`evals/electron-ui-verifier/**`、dedicated CI、README/CHANGELOG/.gitignore 与本 task runtime evidence。
- 阶段提交授权：未授权；只计划最终一次 commit，仍需用户另行明确授权。
- 工具授权：请求 implementation 期间本地 GUI/elevated Termous isolated smoke；不含 remote CI/push。
- 数据/外部写：批准实施 current knowledge reset 机制，但未确认 fingerprint 时不得操作 live root；默认 profile、Termous 数据写和外部 service write 不批准。
- 文档更新：批准范围内 current docs/metadata/schema/assets 可同步。

提交策略：`not_authorized`。

## 方案变更门禁（Plan Amendment Gate）

需要重新批准：contract 中 7 类 triggers，包括 scope/backend/dependency/security/data/validation/其它 skill/Termous write/commit-push 和批准文档变更。

无需重新批准：批准范围内不改变 contract 的命名微调、测试 fixture 实现细节和文档链接修正，由 executor 记 ledger；不得修改本批准 plan/artifacts。

## Artifact Index

| ID | Kind | Path | Required | Approval included |
| --- | --- | --- | --- | --- |
| ART-01 | research | artifacts/research/domain-research.md | yes | yes |
| ART-02 | standards | artifacts/standards/standards-index.md | yes | yes |
| ART-03 | architecture | artifacts/architecture/target-architecture.md | yes | yes |
| ART-04 | architecture | artifacts/architecture/change-map.md | yes | yes |
| ART-05 | validation | artifacts/validation/validation-strategy.md | yes | yes |
| ART-06 | review | artifacts/reviews/plan-critique.md | yes | yes |
| ART-07 | other | artifacts/traceability/traceability-matrix.md | yes | yes |

运行日志、code review 结果、attestation、run-state、ledger 和 commit evidence 由 executor 在批准后创建，不进入规划批准集合。

## Executor Handoff

- Planner checker：`draft passed`；`approval passed`，均为 0 error / 0 warning
- Open blocking decisions：none；implementation/elevated authorization requested from user
- Requested implementation authorization：yes
- Requested commit authorization：no
- Requested external-write authorization：no
- Requested elevated-tool authorization：yes，仅 Termous GUI/本机 ACL 必要步骤
- Residual risks：Playwright CDP lower fidelity、真实三平台 matrix 尚需用户 push、旧 knowledge 不会进入新库；均有明确 capability/optional gate/direct-cutover 边界。

用户批准后由 executor 生成 attestation 并初始化 run-state/ledger。本文件批准后不可变。

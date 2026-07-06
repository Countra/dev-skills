# 执行计划：electron-ui-verifier 渐进式复用和确认持久化流程

## 问题定义

目标:

- 优化 `electron-ui-verifier` 的知识库预检流程：当完整目标没有命中直达 workflow 时，必须先把用户目标拆成可复用的子目标，再搜索入口、页面、前置步骤和已批准 workflow。
- 让验证任务最终回复携带本次实际步骤链路，用文字说明“先到哪里、再做什么、最后读什么”，便于用户确认是否可以将本次经验持久化到 workflow 和知识库。
- 用户确认前仍不得写正式 workflow 或知识库；确认后才能通过 `ev_persist.py approve` 执行固化。

非目标:

- 不改变 verifier server 架构。
- 不改变 Electron GUI 应用本体不用 `process-manager` 的规则。
- 不自动把知识库候选当成业务结论。
- 不引入大模型规划服务、额外数据库或新增第三方依赖。

验收标准:

- 规则明确要求：完整目标无直达命中时，必须进行“目标拆解 -> 子目标知识库搜索 -> 复用前置资产 -> 现场验证后续”的渐进式流程。
- `ev_suggest.py` 或配套 CLI 能输出分层建议，至少能展示完整目标、拆出的子目标、命中资产、可直接复用项和探索降级原因。
- pending 审核包和最终回复都能展示用户可读的步骤链路，且包含持久化确认提示。
- 文档、脚本和 smoke 覆盖“完整目标未命中，但子目标命中入口流程”的场景。

约束:

- 遵守全局 `AGENTS.md`：新增注释使用中文，修改前读取上下文，长内容分段写入。
- 本计划获用户批准前，只落盘规划，不修改 skill 本体实现。
- 同一仓库 Git 命令串行执行；不并发运行 Git。
- 本任务默认不提交代码；只有用户明确要求“按方案执行/提交”后才进入实现和提交。

待确认项:

- 无 blocking 问题。默认实现会修改 `electron-ui-verifier` 文档、建议脚本、pending 审核文案和 smoke。

## 上下文

本地代码:

- `skills/electron-ui-verifier/SKILL.md` 已要求每轮先知识库预检、执行 Reuse Gate、现场验证、pending 确认后持久化。
- `skills/electron-ui-verifier/references/workflow.md` 已定义 Knowledge-First + Reuse Gate + Confirmed Persistence Gate，但当前主要按完整目标查询，没有明确目标拆解和子流程复用。
- `skills/electron-ui-verifier/references/knowledge.md` 已说明知识库只作为候选建议，命中可执行资产要优先复用。
- `skills/electron-ui-verifier/scripts/ev_suggest.py` 当前根据完整 `goal` 搜索，返回 workflow/action/element/screen、补充 action 列表和组合候选，但没有拆解目标后多轮搜索。
- `skills/electron-ui-verifier/scripts/ev_assets.py` 已提供 `directRunHint`，但仍按单次 query/list 工作。
- `skills/electron-ui-verifier/scripts/ev_pending.py` 已生成 `workflow-review.md`，列出正确路径、detour、证据和 `EV-PERSIST-001` 用户填写区。
- `ev_action.py` / `ev_workflow.py` 已支持 `--action-id` / `--workflow-id` 直执行资产。

本地文档:

- `.harness/environment.md` 记录当前主分支为 `main`，harness feature 分支为 `harness/feature`。
- 上一任务 `.harness/tasks/2026-07-03/feature/electron-ui-verifier-asset-reuse-flow/execution-plan.md` 已完成资产复用优先门禁和 asset ID 直执行。

用户约束:

- 如果完整验证任务没做过，不能简单认为知识库无用；应先拆解目标，比如“打开 AI 配置”可拆成“打开设置”“打开 AI 设置”等子流程去检索。
- 最终回复必须携带当前验证步骤流程，用文字说明当前 workflow 和入知识库相关流程，方便用户确认后再固化经验。
- 用户确认步骤流程没问题后，才可以开始持久化 workflow 和写入知识库。

证据等级:

| 结论 | 等级 | 来源 | 影响 |
| --- | --- | --- | --- |
| 当前已有知识库预检和资产直执行能力 | read | `SKILL.md`、`workflow.md`、`ev_action.py`、`ev_workflow.py` | 本次不需要重做资产直执行 |
| 当前缺少目标拆解后的子目标检索规则 | read | `ev_suggest.py`、`workflow.md` | 需要增强规则和建议输出 |
| pending 审核包已能展示正确路径，但最终回复规则还不够明确 | read | `ev_pending.py`、`SKILL.md` | 需要补最终回复契约 |
| 完整目标无命中时子流程可能命中 | assumption | 用户提供的 VideoForensic AI 设置案例和知识库设计目标 | 需要 smoke 覆盖，不能只凭假设 |

## 候选方案

### 方案 A：只改文档规则

- 做法: 在 `SKILL.md` 和 references 中要求目标拆解与最终回复展示步骤链路。
- 优点: 改动最小。
- 缺点: 工具输出不支持分层建议，agent 仍容易只跑一次完整 goal 搜索后探索。
- 风险: 规则执行不稳定，不能有效减少重复 workflow。
- 验证: 文档检索。
- 回滚: revert 文档改动。

### 方案 B：文档规则 + 渐进式建议能力 + 回复/审核模板增强

- 做法: 增强 `ev_suggest.py`，为完整 goal 生成子查询建议并返回分层命中；更新文档和 pending 审核/summary 文案，要求最终回复展示步骤链路和确认入口。
- 优点: 规则和工具输出一致，能让 agent 在完整目标无命中时自然转向前置流程复用。
- 缺点: 需要补脚本和 smoke。
- 风险: 子目标拆解过度或误拆，需要保守策略和允许人工覆盖。
- 验证: py_compile、help、suggest smoke、pending review smoke、文档检索。
- 回滚: revert 脚本和文档改动。

### 方案 C：新增全自动 UI planner

- 做法: 新增 planner 根据目标自动拆解、搜索、执行、纠偏和持久化建议。
- 优点: 自动化程度高。
- 缺点: 范围过大，容易误点 UI；也会把可审计流程变复杂。
- 风险: 误执行低置信动作、调试成本高、违背当前轻量 skill 方向。
- 验证: 需要真实 UI 大量回归。
- 回滚: 成本高。

## 决策

选择方案:

- 方案 B：文档规则 + 渐进式建议能力 + 回复/审核模板增强。

原因:

- 仅写文档不足以防止 agent 在完整目标无命中时直接新建 workflow。
- 现有 `ev_suggest.py`、`ev_assets.py`、asset ID 执行和 pending 机制已经具备基础，本次可做小步增强。
- 不引入全自动 planner，避免过度复杂和误操作风险。

影响:

- `electron-ui-verifier` 的预检流程会从“完整目标一次检索”升级为“完整目标 + 子目标 + 前置流程”的渐进式检索。
- 最终回复必须包含“本次实际步骤链路”和“是否等待用户确认持久化”的明确说明。

可逆性:

- 中等；主要是文档和脚本输出增强，不改知识库 schema。

方案变更触发条件:

- 需要改变知识库 schema。
- 需要引入新依赖或长期服务。
- 子目标拆解必须依赖 LLM 或不可控外部服务。
- 必需验证无法覆盖新增 CLI 行为。

## 影响面矩阵

| 影响对象 | 是否涉及 | 文件/模块 | 风险 | 验证方式 | 文档更新 |
| --- | --- | --- | --- | --- | --- |
| API | yes | `ev_suggest.py` 输出结构；可能新增 `--decompose` 或默认分层建议字段 | 中 | help、suggest smoke | yes |
| 数据结构 | no | 不改 SQLite schema | 低 | knowledge smoke | yes |
| 前端交互 | no | 不改被测 Electron 应用 | 低 | 不适用 | no |
| 配置/环境 | no | 不新增依赖 | 低 | py_compile | no |
| 兼容性 | yes | 保持现有 `ev_suggest.py` 输出字段，新增字段只做补充 | 中 | 旧 smoke + 新 smoke | yes |
| 测试 | yes | 新增或更新 suggest/pending smoke | 中 | finite command | no |
| 文档 | yes | `SKILL.md`、`workflow.md`、`knowledge.md`、`actions.md` | 中 | `rg` 检索和人工 review | yes |

## 实施计划

### Stage 1：规则收口和最终回复契约

目标:

- 将“目标拆解后的渐进式复用”和“最终回复展示步骤链路”写入 skill 必须流程。

做法:

- 更新 `SKILL.md` 必须流程：完整目标无直达命中时，不得直接判定知识库无用；必须拆成入口、页面、前置步骤、目标断言等子目标继续检索。
- 更新 `references/workflow.md`：在 Knowledge-First 流程中加入 `Progressive Reuse Gate`，定义完整目标搜索、子目标搜索、资产复用、探索降级和证据记录顺序。
- 更新 `references/knowledge.md`：说明子目标可命中 screen、element、action asset、workflow asset 或已批准 workflow；低置信项只能作为候选。
- 更新 `references/actions.md`：补充最终回复需要把 pending workflow 的正确步骤转成可读流程链路。

原因:

- 现有规则已要求先查知识库，但没有明确“完整目标无命中时继续查子流程”，导致 agent 容易重复探索。

位置:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/knowledge.md`
- `skills/electron-ui-verifier/references/actions.md`

参考来源:

- 已读当前 skill 文档和上一资产复用任务计划。
- 用户当前约束：AI 配置案例应先复用“打开设置”流程。

验证:

- `rg "Progressive Reuse Gate|渐进式复用|目标拆解|步骤链路|持久化确认" skills/electron-ui-verifier`
- 人工 review：确认没有把知识库候选写成最终业务结论。

风险和回滚:

- 风险: 规则过重导致简单任务也被拆解。
- 缓解: 只在完整目标没有直达可执行资产时触发子目标检索；直达命中仍优先复用。
- 回滚: revert 文档段落。

阶段契约:

- 范围: 文档规则。
- 允许修改: `SKILL.md`、`references/*.md` 中相关小节。
- 禁止修改: server 架构、知识库 schema。
- 进入条件: 计划获批，工作区安全。
- 退出条件: 文档规则完整，检索通过。
- 必需验证: 文档检索和人工 review。
- 是否预期提交: 最终统一提交，需用户批准。

### Stage 2：渐进式建议输出

目标:

- 让 `ev_suggest.py` 输出完整目标和子目标的分层检索结果，帮助 agent 优先复用前置流程。

做法:

- 增强 `ev_suggest.py`：保留原有完整 `goal` 搜索，同时生成 `progressivePlan` 或等价字段。
- 子目标拆解采用保守、可解释的本地规则，不依赖外部服务：按常见入口词、页面词、动作词和中文/英文分隔符生成候选 query，例如“打开设置”“AI设置”“苍穹AI局域网”“连接状态”。
- 对每个子目标运行知识库搜索或复用现有 store search，汇总 workflow/action/element/screen 命中。
- 输出 `reuseStrategy`：先可执行 workflow asset，再 action asset，再已知 screen/element，最后现场探索。
- 输出 `fallbackReason`：完整目标无命中、命中不可执行、低置信、目标不匹配或现场复验失败。

原因:

- 工具输出需要直接支持规则，否则 agent 仍会只跑一次完整 goal 搜索。

位置:

- `skills/electron-ui-verifier/scripts/ev_suggest.py`
- 必要时新增小型 smoke，例如 `ev_progressive_suggest_smoke.py`。

参考来源:

- `ev_suggest.py` 当前 `suggest()`、`preflight_summary()`、`compose_candidate()`。
- `ev_knowledge_store.py` 当前 `store.search()`。

验证:

- `python -m py_compile skills/electron-ui-verifier/scripts/ev_suggest.py`
- `python skills/electron-ui-verifier/scripts/ev_suggest.py --help`
- smoke：构造临时知识库，完整目标不命中但子目标“打开设置”命中 action/workflow，断言输出包含该子目标命中和 direct run hint。

风险和回滚:

- 风险: 本地拆词误判，产生噪声命中。
- 缓解: 输出明确标记 `derivedQueries` 和 score；低置信命中必须现场验证。
- 回滚: 移除新增字段，恢复原 suggest。

阶段契约:

- 范围: `ev_suggest.py` 和 smoke。
- 允许修改: 保持旧字段兼容，仅新增字段。
- 禁止修改: 数据库 schema、资产执行入口。
- 进入条件: Stage 1 完成。
- 退出条件: suggest 输出可用于完整目标和子目标复用判断。
- 必需验证: py_compile、help、smoke。
- 是否预期提交: 最终统一提交，需用户批准。

### Stage 3：步骤链路确认和 pending 文案增强

目标:

- 让最终回复和 pending 审核包都能清楚展示“本次正确 workflow 路径”，并提示用户确认后才能持久化。

做法:

- 增强 `ev_pending.py` 的 `workflow-review.md`：保留现有“正确路径”，增加“可回复确认的流程链路摘要”，使用类似 `首页 -> 设置 -> AI设置 -> 选择苍穹AI局域网 -> 读取状态/配置` 的文本格式。
- 在 `evidence-index.json` 增加可机读 `flowSummary` 或 `reviewFlow`，便于最终回复从 pending 包中读取并展示。
- 更新 `write_summary()` 或报告摘要：包含 pending 审核包路径和 flow summary。
- 更新文档：最终回复必须带 `flowSummary`、pending 路径、是否已写库、用户确认后执行的 `ev_persist.py approve` 方向。

原因:

- 用户希望直接在会话中看到步骤链路并确认，避免打开文件才能判断是否允许入库。

位置:

- `skills/electron-ui-verifier/scripts/ev_pending.py`
- `skills/electron-ui-verifier/scripts/ev_server.py` 的 summary 可选增强。
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/SKILL.md`

参考来源:

- `ev_pending.py` 当前 `describe_action()`、`review_lines()`、`write_pending_package()`。
- `ev_server.py` 当前 `write_summary()`。

验证:

- 更新或新增 pending smoke：断言 `workflow-review.md` 和 `evidence-index.json` 包含 flow summary，且 detour 不进入 summary。
- py_compile 覆盖修改脚本。

风险和回滚:

- 风险: 自动描述 evaluate 步骤过于抽象。
- 缓解: evaluate 仍标记“需要重点确认”；不把隐藏脚本细节过度包装成简单点击。
- 回滚: 恢复 pending review 旧文案。

阶段契约:

- 范围: pending 审核文案、summary、文档。
- 允许修改: 小范围脚本和文档。
- 禁止修改: 持久化审批语义，不自动写知识库。
- 进入条件: Stage 2 完成。
- 退出条件: pending 和最终回复契约都能展示流程链路。
- 必需验证: py_compile、pending smoke、文档检索。
- 是否预期提交: 最终统一提交，需用户批准。

### Stage 4：整体回归、记录和交付

目标:

- 确认规则、脚本、smoke、changelog 和 harness 状态一致。

做法:

- 运行所有修改脚本的 `py_compile`。
- 运行 help 和新增 smoke。
- 运行知识库相关 smoke，确认旧功能不退化。
- 更新 `CHANGELOG.md`。
- 更新本 `execution-plan.md` 的验证、review、提交记录。
- 如用户批准提交，使用 `git commit -F` 提交。

原因:

- 该优化影响每轮 UI 验证的流程，必须通过文档和工具双重约束。

位置:

- `CHANGELOG.md`
- 本 `execution-plan.md`
- 相关 smoke 文件。

参考来源:

- `complex-coding-harness` 阶段门禁和提交规范。

验证:

- `python -m py_compile` 覆盖改动脚本。
- `python skills/electron-ui-verifier/scripts/ev_suggest.py --help`
- 新增 progressive suggest smoke。
- pending smoke。
- `git -c diff.autoRefreshIndex=false diff --check`

风险和回滚:

- 风险: 当前工作区有 ignored/未跟踪历史运行产物。
- 缓解: 提交时只精确 stage 本任务相关 tracked/new files。
- 回滚: revert 本任务提交。

## 环境

Workspace 环境来源:

- `.harness/environment.md`

本任务使用:

- 仓库: `E:\work\hl\videoForensic\AI\dev-skills`
- Python: 当前可用 `python`，用于有限命令、py_compile 和 smoke。
- Electron UI: 本任务规划和脚本验证默认不需要真实 Electron UI；若实施中追加真实验证，必须按 `electron-ui-verifier` 规则使用 verifier server。

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

- 规划阶段未执行 merge；实施前按 `.harness/environment.md` 和实际工作区状态重新确认。

最近同步:

- 未在本规划阶段同步。

分支占用:

- 串行 `git --no-optional-locks status --short --branch`: 当前分支 `harness/feature`。
- 当前可见未跟踪项: `.harness/.harness/`、`.harness/electron-feasibility/`、`.harness/electron-ui-verifier-asset-smoke/`。
- 这些未跟踪项为历史运行产物，本任务不清理、不提交。

Git 命令策略:

- 同一仓库 Git 命令必须串行。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git。
- 非 Git 文件读取和文本搜索可并发，但不能与 Git 命令混在同一并发批次。

提交策略:

- 规划阶段不提交。
- 实施获批并授权提交后，使用 `.harness/tasks/2026-07-03/feature/electron-ui-verifier-progressive-reuse-confirmation-flow/tmp/commit-message.txt` 和 `git commit -F`。
- 禁止多个 `-m` 分别传 bullet。

分支安全:

- 不自动 stash。
- 不自动 rebase。
- 不自动 reset。
- 提交前精确 stage 本任务相关文件。

未解决问题:

- 无 blocking Git 问题；实施前仍需复查工作区。

## 工具

| 工具 | 用途 | 阶段 | 状态 | 风险 | 替代方案 | 用户确认 |
| --- | --- | --- | --- | --- | --- | --- |
| complex-coding-harness | 托管规划和后续实施 | 全阶段 | 已读取 | 低 | 手动计划 | 用户已要求 |
| electron-ui-verifier | 被优化对象 | 全阶段 | 已读取 | 中 | 无 | 待批准实施 |
| Python | py_compile、help、smoke | Stage 2-4 | 当前可用 | 低 | 用户指定解释器 | 不需新增确认 |
| Git | 状态和提交 | Stage 4 | 串行使用 | 中 | 不提交 | 提交需批准 |
| process-manager | verifier server 长期服务管理 | 仅真实 UI 验证需要 | 未在本计划阶段使用 | 低 | 用户手动启动 manager | 既有规则 |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程:

- 本规划阶段: no。
- 默认实施阶段: no，文档、脚本、smoke 均为 finite command。
- 如果后续增加真实 Electron UI 验证: verifier server 是长期服务，必须使用 `process-manager`；Electron GUI 应用本体仍不用 `process-manager`。

process-manager skill 是否存在:

- 仓库内存在 `skills/process-manager`，但当前会话技能列表未直接暴露；若真实 UI 验证需要，必须读取本地 `skills/process-manager/SKILL.md` 和 workflow。

规则结论:

- 不手写后台 shell 启动 verifier server。
- finite command 直接运行。
- manager 离线时停止长期进程操作，请求用户手动启动或授权 bootstrap。

需要托管的服务:

| 服务 | 类型 | 阶段 | service config | readiness | processKey | 日志/证据 | 清理状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | not required | Planning/Stage 1-4 | none | none | none | not-applicable | not-applicable |

## 验证

必需验证:

- 文档规则检索：确认 `Progressive Reuse Gate`、目标拆解、步骤链路和持久化确认规则存在。
- Python 编译：覆盖所有修改过的脚本。
- CLI help：至少覆盖 `ev_suggest.py --help`，如改 `ev_pending.py` 不需 help。
- progressive suggest smoke：完整目标无直达命中但子目标命中时，输出分层建议和 direct run hint。
- pending review smoke：确认 `workflow-review.md` 和 `evidence-index.json` 包含用户可读流程链路，detour 不进入正确路径。
- diff check：`git -c diff.autoRefreshIndex=false diff --check`。

验证证据表:

| 阶段 | 命令/工具 | 结果 | 覆盖内容 | 未覆盖 | 证据/日志 | 处理 |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | 本地文档和脚本读取 | passed | 现有规则和能力 | 未修改实现 | 本计划 Context | 继续审批 |
| Stage 1 | `rg "Progressive Reuse Gate|progressivePlan|flowSummary|步骤链路|完整目标没有" skills/electron-ui-verifier` | passed | 文档规则落地 | 真实 UI | 终端输出 | 无需修复 |
| Stage 2 | py_compile、help、`ev_progressive_suggest_smoke.py` | passed | 渐进式建议输出、子目标命中 | 真实 UI | 终端输出 | 修复 AI 状态目标未推导“设置”的缺陷后通过 |
| Stage 3 | py_compile、`ev_pending_smoke.py` | passed | 流程链路和持久化确认 | 真实 UI | 终端输出 | 无需修复 |
| Stage 4 | 全量 `ev_*.py` py_compile、asset/knowledge smoke、diff check | passed | 整体一致性 | 远程 CDP | 终端输出 | diff check 只有 CRLF 警告 |

可选验证:

- 使用 VideoForensic 的 AI 设置场景做一次真实验证，确认最终回复能展示类似 `首页 -> 设置 -> AI设置 -> 选择苍穹AI局域网 -> 读取配置` 的链路。该验证需要 verifier server 在线。

未覆盖:

- 不验证远程 CDP。
- 不验证 Windows 原生对话框。
- 不迁移旧知识库。

无法执行时:

- 记录失败原因、影响、替代验证；不能声明真实 UI 验证通过。

## 文档

必需更新:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/knowledge.md`
- `skills/electron-ui-verifier/references/actions.md`
- `CHANGELOG.md`

Changelog 计划:

- 增加 2026-07-03 条目，说明渐进式复用门禁、子目标检索建议和最终回复步骤链路确认。

## 文件写入策略

分段判断:

| 文件 | 分段判断 | 分段边界 | 整体复查方式 |
| --- | --- | --- | --- |
| `SKILL.md` | no | 必须流程/硬规则局部段落 | 完整读取 |
| `references/workflow.md` | yes | Knowledge-First 小节、证据/最终说明小节 | 完整读取 |
| `references/knowledge.md` | yes | 查询和建议、学习方式小节 | 完整读取 |
| `references/actions.md` | no | pending/来源说明局部段落 | 完整读取 |
| `ev_suggest.py` | no | 拆解 helper、输出字段、summary | py_compile/help/smoke |
| `ev_pending.py` | no | flow summary helper、review/evidence 写入 | py_compile/smoke |
| `ev_server.py` | no | summary 小范围增强，如确需修改 | py_compile/smoke |
| smoke 文件 | no/unknown | 单个完整 smoke 文件；超过 200 行拆分 | py_compile/run |
| `CHANGELOG.md` | no | 单日期块 | 完整读取 |

写入规则:

- 分段 patch 是落盘策略，不是思考策略。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 目标文件超过 500 行时禁止整文件重写，优先局部 patch。
- 规划、文档、代码、smoke、changelog 和任务状态都适用。

整体复查:

- 写完后重新读取完整目标文件。
- 检查规则是否相互矛盾、命名是否一致、是否保留用户确认门禁。
- 代码文件必须通过 py_compile 和相关 smoke。

patch 失败处理:

- 先读取目标文件确认是否部分写入。
- 判断上下文不匹配、patch 过大或工具层错误。
- 缩小 patch 后只重试失败段，不重复写已成功段。

## 问题和覆盖项

| ID | 是否阻塞 | 状态 | 问题 | 决策 | 应用位置 |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | resolved | 是否需要新增自动 planner | 不需要，采用轻量渐进式建议输出 | 决策和实施计划 |
| D-002 | no | resolved | 是否用户确认前自动入库 | 不允许，仍走 pending -> 用户确认 -> approve | Stage 3 |

## 方案质量门禁

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 关键判断有证据等级 | passed | Context 和证据等级表 |
| 影响面矩阵完整 | passed | API、数据结构、兼容性、测试、文档已覆盖 |
| 候选方案比较充分 | passed | 比较 A/B/C |
| 每阶段可独立验证 | passed | Stage 1-4 均有独立验证 |
| 方案变更触发条件清楚 | passed | 决策章节已列 |
| 用户批准摘要可记录 | passed | Plan Approval 已预留 |

质量结论:

- passed

## 规划自查

自查结论:

- passed after adjustments

| 类别 | 发现 | 处理 | 结果 |
| --- | --- | --- | --- |
| 缺陷 | 初始方向可能被误解为“完整目标无命中就现场探索” | 增加 `Progressive Reuse Gate` 和子目标检索顺序 | fixed |
| 优化 | 不需要新增重量级 planner | 选择在 `ev_suggest.py` 增强可解释建议 | fixed |
| 缺失项 | 最终回复需明确用户可确认步骤链路 | Stage 3 加入 `flowSummary`、pending 和最终回复契约 | fixed |
| 风险 | 子目标拆解可能产生噪声命中 | 限制为保守本地规则，低置信必须现场复验 | fixed |
| 一致性 | 用户确认前不得入库与“最终回复提示入库”需区分 | 明确只是询问确认，不执行 `ev_persist.py approve` | fixed |

门禁重跑:

- `Plan Quality Gate` 是否需要重跑: no
- `Plan Self-Review` 是否需要重跑: no
- `Readiness Gate` 是否需要重跑: no
- 原因: 自查修复未改变目标、范围、阶段和验证策略。

## 就绪门禁

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 目标和验收清楚 | passed | 问题定义 |
| 上下文已收集 | passed | 已读 skill 文档、workflow、knowledge、actions、关键脚本 |
| 候选方案已比较 | passed | 方案 A/B/C |
| 决策已记录 | passed | 选择方案 B |
| 实施阶段已细化 | passed | Stage 1-4 |
| 环境已确认 | passed | `.harness/environment.md` |
| Git 上下文已确认 | partial | 已串行检查 status；实施前需复查 |
| 工具已确认 | passed | 工具表 |
| 验证已确认 | passed | 验证表 |
| 最终交付证据已规划 | passed | Stage 4 和验证证据表 |
| 文档更新已确认 | passed | 文档章节 |
| 风险已识别 | passed | 各阶段风险和回滚 |
| 规划自查已通过 | passed | Plan Self-Review |
| 阻塞问题已关闭 | passed | 无 blocking |

就绪结论:

- ready for user plan approval

## 方案批准

状态:

- approved

批准记录:

- 2026-07-03 用户回复“按方案执行”，批准按本计划实施。
- 2026-07-06 用户回复“对当前的修改提交代码吧”，授权提交本次已完成改动。

批准摘要:

- 批准范围: Stage 1-4 全部实施，包括文档、脚本、smoke、changelog 和 harness 状态更新。
- 阶段提交授权: 已授权本次提交。
- 工具/MCP 授权: 当前不需要新增 MCP；真实 UI 验证若追加则按既有 process-manager / electron-ui-verifier 规则。
- 文档更新授权: 已授权。

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

剩余阶段:

- none

下一步自动动作:

- final delivery

当前停止条件:

- all approved stages completed

状态来源:

- execution-plan.md

阶段边界是否允许停止:

- no, unless the user explicitly requests stage-only execution or a Stop Condition is active

## 实施进度

| 阶段 | 状态 | 摘要 | 验证 | 证据 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| Planning | completed | 已制定渐进式复用和流程确认方案，用户已批准实施 | 本地文档/脚本读取、Git 串行状态检查 | 本文档 | Stage 1 |
| Stage 1 | completed | 文档规则新增 Progressive Reuse Gate 和最终回复步骤链路契约 | passed | `rg "Progressive Reuse Gate|progressivePlan|flowSummary|步骤链路"` | Stage 2 |
| Stage 2 | completed | `ev_suggest.py` 输出 `progressivePlan`，完整目标无命中时可复用子目标资产 | passed | py_compile、`ev_suggest.py --help`、`ev_progressive_suggest_smoke.py` | Stage 3 |
| Stage 3 | completed | pending 审核包、evidence 和 summary 增加清洗后的步骤链路摘要 | passed | py_compile、`ev_pending_smoke.py` | Stage 4 |
| Stage 4 | completed | 完成整体回归、review、changelog 和任务记录 | passed | 全量 `ev_*.py` py_compile、asset/knowledge smoke、diff check | Final delivery |

## 阶段进入门禁

| 阶段 | 当前分支/工作区 | 上阶段遗留 | 环境和工具 | 长期进程门禁 | 范围匹配 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | passed | none | passed | not-applicable | passed | passed |
| Stage 2 | passed | none | passed | not-applicable | passed | passed |
| Stage 3 | passed | none | passed | not-applicable | passed | passed |
| Stage 4 | passed | none | passed | not-applicable | passed | passed |

## 阶段退出门禁

| 阶段 | 目标完成 | Review 完成 | 验证完成 | 长期进程清理和证据 | 关键日志已沉淀 | 记录更新 | 提交记录 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-commit | passed |
| Stage 2 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-commit | passed |
| Stage 3 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-commit | passed |
| Stage 4 | passed | passed | passed | not-applicable | not-applicable | passed | authorized-current-commit | passed |

## 阶段转移门禁

| 阶段 | 当前阶段已完成 | Review 已完成 | 验证已完成或替代证据已记录 | 提交或未提交原因已记录 | 是否还有 pending stage | 是否存在停止条件 | 是否需要重新批准 | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止 | 下一动作 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | yes | yes | yes | not-applicable | yes | yes | no | yes | yes | yes | wait for user approval |
| Stage 1 | yes | yes | yes | authorized-current-commit | yes | no | no | yes | yes | no | continue Stage 2 |
| Stage 2 | yes | yes | yes | authorized-current-commit | yes | no | no | yes | yes | no | continue Stage 3 |
| Stage 3 | yes | yes | yes | authorized-current-commit | yes | no | no | yes | yes | no | continue Stage 4 |
| Stage 4 | yes | yes | yes | authorized-current-commit | no | yes | no | yes | yes | yes | final delivery |

结论:

- 所有批准阶段已完成，进入最终交付门禁。用户已授权提交本次改动，按提交信息文件方式提交。

## 代码审查

| 阶段 | 问题 | 严重程度 | 处理 |
| --- | --- | --- | --- |
| Planning | 未修改 skill 本体；只新增 harness 规划文档 | follow-up | 实施阶段执行代码 review |
| Stage 1-4 | 未发现 blocking 或 major 问题；新增字段保持向后兼容，pending flowSummary 使用清洗后的 proposed workflow，detour 不进入正确路径 | none | 无需修复 |

## 恢复摘要

- 整体目标: 优化 `electron-ui-verifier`，在完整目标无直达知识库命中时进行目标拆解和子目标复用，并在最终回复展示本次验证步骤链路供用户确认持久化。
- 执行模式: run-to-completion。
- 整体任务状态: completed。
- 已完成阶段: Planning、Stage 1、Stage 2、Stage 3、Stage 4。
- 当前阶段: Final delivery。
- 剩余阶段: none。
- 最新 commit: current commit。
- 下一步自动动作: final delivery。
- 当前停止条件: all approved stages completed。
- 状态来源: execution-plan.md。
- 长期进程规则: 本任务默认不需要长期进程；如真实 UI 验证需要 verifier server，必须使用 process-manager；Electron GUI 本体不用 process-manager。
- 未覆盖/风险: 未运行真实 Electron UI；本次覆盖文档、脚本和离线 smoke。本轮按用户授权提交。
- 不得停止说明:
  - 用户批准实施后默认 run-to-completion，不能在阶段边界提前最终回复。

## 提交记录

提交信息方式:

- 使用 `git commit -F .harness/tasks/2026-07-03/feature/electron-ui-verifier-progressive-reuse-confirmation-flow/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。

| 阶段 | 仓库 | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | not committed | planning only | not changed |
| Stage 1-4 | dev-skills | current commit | `feat(electron-ui-verifier): 增强渐进式复用确认流程` | `CHANGELOG.md` 2026-07-03 Stage 7 |

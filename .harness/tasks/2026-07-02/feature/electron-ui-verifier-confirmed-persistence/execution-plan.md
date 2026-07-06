# Electron UI Verifier 持久化确认门禁执行计划

## 问题定义（Problem）

目标（Goal）:

- 将 `electron-ui-verifier` 从“每轮验证默认固化 workflow 并回写知识库”调整为“默认只生成现场验证证据和待审核流程包，用户确认后才持久化 workflow 和写入知识库”。
- 每次 UI 验证结束后，必须把本轮 workflow 的详细操作步骤用中文说明清楚，包括先点击什么、再输入什么、等待什么、截图或抽取什么。
- 用户确认流程正确、可复用、无污染风险后，才允许把 workflow 保存为长期资产，并将相关 evidence、screen、element、action/workflow 写入知识库。

非目标（Non-goals）:

- 本计划阶段不修改源码；只有用户明确批准后才进入实现。
- 不清理历史已写入的 workflow 或知识库记录；历史污染清理可作为后续独立任务。
- 不改变 Electron GUI 应用本体的启动规则：Electron GUI 仍不使用 `process-manager`，只有 verifier server 使用 `process-manager`。
- 不取消现场验证证据。`report.json`、截图、artifact、summary 仍用于证明本轮 UI 结论，只是不默认进入可复用资产和知识库。

验收标准（Acceptance）:

- `ev_action.py`、`ev_workflow.py` 和 server 执行链路默认不因 `appId`、`goal` 或 workflow 内 `learn` 字段自动写知识库。
- 每轮验证默认生成 `pending` 审核包，包含清洗后的 `workflow.proposed.json`、`workflow-review.md`、`evidence-index.json`，且不被 `ev_suggest.py`、`ev_assets.py` 当作正式资产检索。
- 自动化验证中如果进入错误页面、点击无关功能、找不到目标入口或流程与用户需求不符，必须及时识别为错误路径并自我纠偏；最终待确认和可持久化的 workflow 只能包含纠偏后确认正确的路径。
- 探索过程中的弯路、错误点击、错误页面和无关功能可以保留在 pending 审计记录中，但不得进入 `workflow.proposed.json`、正式 `workflows/` 或知识库。
- 最终回复在用户未确认持久化前必须说明“未写入知识库、未保存为长期 workflow 资产”，并给出 pending 审核包、report、截图或 artifact 路径。
- 只有用户明确批准后，才能通过显式命令把 pending 审核包晋级到 `.harness/electron-ui-verifier/workflows/` 和 `.harness/electron-ui-verifier/knowledge/`。
- 文档必须把“先查知识库、现场验证、生成待审核流程、用户确认、再持久化”的顺序写成强制流程。

约束（Constraints）:

- 所有 `electron-ui-verifier` 内部文件仍只能位于 `.harness/electron-ui-verifier/` 下。
- 可执行程序路径、workflow 路径、action 路径、config 路径必须使用绝对路径。
- verifier server 是长期进程，后续实现和验证如果需要启动它，必须使用 `process-manager`；finite command 直接运行。
- Git 命令必须串行执行，不放入任何并发工具或后台任务。
- 本计划只落盘规划，`Plan Approval` 之前不修改 `skills/` 源码。

待确认项（Open uncertainties）:

- 无阻塞项。推荐默认策略已在“决策”中给出；如用户批准本计划，即按推荐策略实现。

## 上下文（Context）

本地代码（Local code）:

- `skills/electron-ui-verifier/SKILL.md`：当前第 8、9、11 条要求每轮执行后固化 workflow 并回写知识库，需要改为确认后持久化。
- `skills/electron-ui-verifier/references/workflow.md`：当前 `Knowledge-First Gate` 第 4 步要求执行后必须回写，证据章节要求每轮 workflow 固化到 `workflows/`。
- `skills/electron-ui-verifier/references/knowledge.md`：当前学习方式把基础知识回写作为每轮标准动作。
- `skills/electron-ui-verifier/references/actions.md`：当前说明提供 `appId` / `goal` 时脚本默认启用基础知识回写。
- `skills/electron-ui-verifier/scripts/ev_action.py`：当前 `should_learn = args.learn or args.learn_assets or args.app_id or args.goal`，会被 `app-id/goal` 隐式触发。
- `skills/electron-ui-verifier/scripts/ev_workflow.py`：当前 `should_learn = args.learn or args.learn_assets or app_id or goal or workflow_learn`，会被 `appId/goal/learn` 隐式触发。
- `skills/electron-ui-verifier/scripts/ev_server.py`：`run_steps` 会把每次 workflow 写到 `config.workflows_dir`，有 `learn` 时立即调用 `persist_report_knowledge`。

本地文档（Local docs）:

- `skills/complex-coding-harness/SKILL.md`：managed 任务必须先规划、自查、readiness、等待用户明确批准，再实现。
- `skills/complex-coding-harness/references/workflow.md`：要求 `execution-plan.md` 是唯一主契约，阶段实施默认 run-to-completion，阶段边界不能误停。
- `.harness/environment.md`：当前仓库主分支为 `main`，工作分支策略使用 `harness/feature`，当前分支观察为 `harness/feature`。

外部来源（External sources）:

- 本计划不依赖在线事实；核心依据为当前仓库源码和用户明确需求。

用户约束（User constraints）:

- 不要每次任务都默认保存所有 workflow 和写入知识库。
- 任务结束后必须让用户确认是否持久化保存。
- 必须详细说明整个 workflow 的操作步骤，用户确认并可修改后，才能保存 workflow 和写入知识库。
- 目的是避免错误流程、错误步骤进入知识库，污染环境。
- 自动化过程中走错页面、点错功能、进入无关模块时，agent 需要自己判断并修正路线；最后只提交正确路线给用户确认。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 当前 CLI 会因 `app-id/goal` 隐式触发学习 | read | `ev_action.py`、`ev_workflow.py` 检索结果 | 必须改默认学习策略 |
| 当前 server 每次执行都会固化 workflow 到 `workflows/` | read | `ev_server.py:1329-1406` | 必须拆分 pending 与 approved 路径 |
| 当前文档要求每轮回写知识库 | read | `SKILL.md`、`workflow.md`、`knowledge.md`、`actions.md` | 必须同步文档和硬规则 |
| 用户要求确认后才持久化 | confirmed | 当前会话用户需求 | 方案核心验收 |

## 候选方案（Options）

### 方案 A：最小改动（Minimal Change）

- 做法（How）:
  - 移除 `appId/goal` 的隐式 `learn`，默认要求 agent 手动传 `--no-learn`。
  - 文档补充“回写前询问用户”。
  - server 仍每次把 workflow 写入 `workflows/`。
- 优点（Pros）:
  - 改动小，风险低。
  - 快速阻止大部分知识库污染。
- 缺点（Cons）:
  - `workflows/` 仍会积累未审核流程，仍可能被误认为正式资产。
  - 用户确认流程缺少结构化审核包，长期容易被 agent 忘记。
  - 不能很好支持“修改流程后再持久化”的闭环。
- 风险（Risks）:
  - 只修学习不修固化路径，污染问题没有完全解决。
- 验证（Validation）:
  - CLI 默认执行不写 knowledge。
  - 文档检索不再出现默认回写描述。
- 回滚（Rollback）:
  - 恢复旧 CLI 隐式 `learn` 逻辑和文档。

### 方案 B：确认门禁和 pending 审核包（Structured Change）

- 做法（How）:
  - 默认执行只生成现场证据和 pending 审核包，不写正式 `workflows/`，不写 knowledge。
  - pending 审核包记录机器可执行 workflow、中文步骤说明、证据索引、知识库预检和实际使用摘要。
  - 新增或调整 promote/persist 入口，只有用户确认后才把 pending 晋级为正式 workflow 和知识库记录。
  - 文档、CLI、server、最终回复规则统一采用该门禁。
- 优点（Pros）:
  - 从流程、数据路径、工具行为三层阻断污染。
  - 用户能在持久化前审阅“先怎么点、再怎么点”的真实流程。
  - pending 与 approved 边界清楚，后续知识库搜索不会命中未审核流程。
- 缺点（Cons）:
  - 改动范围大于方案 A，需要增加审核包和晋级逻辑。
  - 首次使用多一个确认步骤。
- 风险（Risks）:
  - 如果报告和 pending 路径命名不清，用户可能误解“证据保留”和“长期资产保存”的区别。
- 验证（Validation）:
  - 默认执行不产生正式 workflow 资产和 knowledge 写入。
  - pending 审核包可读、可定位证据、可被批准晋级。
  - 批准后正式 workflow 可被 `ev_assets.py` 或 `ev_suggest.py` 命中。
- 回滚（Rollback）:
  - 保留 report 证据，关闭 promote 入口，恢复旧 server 写 `workflows/` 逻辑。

## 决策（Decision）

选择方案（Chosen option）:

- 方案 B：确认门禁和 pending 审核包。

原因（Why）:

- 用户的核心问题不是单一脚本参数，而是“错误流程进入长期资产和知识库”。必须把执行证据、待审核流程、正式资产三者隔离。
- 仅取消隐式学习无法阻止 workflow 文件被长期保存，也无法让用户在保存前审查步骤。
- pending 审核包能把 agent 的实际 UI 操作转成可审计文本，适合用户确认和后续复用。

影响（Impact）:

- 默认执行行为改变：验证后不再自动产生正式 workflow 资产，也不自动写 knowledge。
- 最终回复规则改变：未确认持久化前报告 pending 审核包路径；确认后报告正式 workflow 路径和知识库写入摘要。
- 文档中的 “Knowledge-First Gate” 调整为 “Knowledge-First + Confirmed Persistence Gate”。

可逆性（Reversibility）:

- 中等。CLI 和文档可回滚；server 的 pending/approved 路径需要保留迁移说明。由于不要求兼容旧知识库迁移，回滚成本可控。

变更条件（Change conditions）:

- 如果实现中发现现有 report schema 强依赖 `workflowPath` 必须是正式资产路径，则改为同时提供 `executedWorkflowPath` 和 `approvedWorkflowPath`，并更新文档。
- 如果用户希望完全不落盘 pending workflow，则需要重新审批，因为这会削弱可审计性和最终回复证据。

方案变更触发条件（Reapproval triggers）:

- 需要改变 `.harness/electron-ui-verifier/` 根目录边界。
- 需要新增第三方依赖。
- 需要清理或迁移历史 knowledge/workflow 数据。
- 需要改变 Electron GUI 启动方式或改用 `process-manager` 管理 GUI 本体。
- 必需验证无法执行，且没有足够替代证据覆盖默认不污染和确认晋级链路。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | `/actions/run`、`/workflows/run` payload/result，`ev_action.py`、`ev_workflow.py` 参数 | 默认输出字段和学习行为变化 | CLI help、server smoke、report 字段检查 | `server.md`、`workflow.md`、`actions.md` |
| 数据结构（Data model） | yes | pending 审核包、report workflow 字段、knowledge writeback metadata | pending 与 approved 混淆 | JSON schema smoke、路径检索、知识库未写入检查 | `knowledge.md` |
| 前端交互（Frontend interaction） | no | 不改被测 Electron UI | 不适用 | 不适用 | 不适用 |
| 配置/环境（Config/environment） | yes | `.harness/electron-ui-verifier/` 下新增 pending 目录约定 | 内部目录边界变复杂 | `ev_init` 后目录检查 | `server.md` |
| 兼容性（Compatibility） | yes | 旧 workflow 中 `learn` 字段不再自动写库 | 旧用法期望执行即学习 | 文档说明必须走 approve/persist | `actions.md` |
| 测试（Tests） | yes | py_compile、help、默认执行 smoke、approve smoke、知识库查询 | 未覆盖真实 Electron GUI | 使用轻量 report/workflow fixture，必要时用 VideoForensic 手测 | 不适用 |
| 文档（Documentation） | yes | `SKILL.md`、`workflow.md`、`knowledge.md`、`actions.md`、`server.md` | 规则冲突导致 agent 遗忘 | `rg` 检索旧规则和新规则 | 全部相关 reference |

## 目标流程（Target Workflow）

### 阶段外部使用流程

1. **知识库预检**：根据 `appId` 和目标运行 `ev_suggest.py`、`ev_knowledge.py search` 或 `ev_assets.py`，只读取历史经验，不写入。
2. **制定现场操作草案**：把命中的候选 action/workflow、当前页面快照和用户目标整理成本次 workflow 草案。
3. **现场验证执行和偏离检测**：通过稳定 session 执行 `ev_action.py` 或 `ev_workflow.py`。默认模式只产生 report、summary、截图、artifact 和 pending 审核包，不写正式 workflow 资产，不写知识库。执行中必须持续判断当前页面、URL、标题、关键文本和用户目标是否匹配。
4. **错误路径自我纠偏**：如果进入错误页面、点击无关功能、找不到目标入口或页面内容与目标不符，必须把当前路径标记为 `detour`，然后返回上一步、关闭误开的页面、回到首页或重新 attach/snapshot，逐步分析正确入口。不能因为走错就直接把错误流程沉淀。
5. **正确路径清洗**：任务完成后从探索轨迹中提炼一条最短且可复验的正确路径，删除错误点击、无关页面、重复尝试和无效等待。`workflow.proposed.json` 只能包含这条正确路径；弯路只进入 `detours` 审计摘要。
6. **生成流程审核说明**：把清洗后的正确 workflow 翻译为中文步骤，必须包括：
   - 等待条件，例如“等待页面出现 `历史记录` 文本”。
   - 操作步骤，例如“点击左侧菜单 `设置`”、“在搜索框输入 `shipin.001`”、“点击第一个 `查看` 按钮”。
   - 证据步骤，例如“截图保存为 `result.png`”、“抽取当前页面文本到 artifact”。
   - 断言或观察，例如“确认 URL 包含 `#/result`”、“读取任务列表文本”。
7. **请求用户确认**：在会话中给出正确路径说明、弯路摘要和 pending 文件路径，并明确问用户是否允许持久化。弯路摘要只用于说明“已排除哪些错误路径”，不得作为可持久化步骤。
8. **用户修改或拒绝**：如果用户指出流程不正确，必须更新正确路径草案或重新现场验证，再生成新的 pending 审核包；旧 pending 不进入知识库。
9. **用户批准持久化**：只有用户明确确认后，执行 promote/persist 命令，把 pending 中的清洗后 workflow 保存为正式 workflow，按批准范围写入基础知识和可复用 action/workflow 资产。
10. **最终回复**：说明预检命中、现场验证证据、用户确认结果、是否已持久化、正式 workflow 路径或 pending 路径、知识库写入摘要、已排除的弯路摘要和未覆盖范围。

### 用户确认交互模板

```text
本轮 UI 验证流程待确认：

1. 等待首页出现“历史记录”。
2. 点击筛选项“镜像文件”。
3. 在检材搜索框输入“shipin.001”。
4. 点击第一个匹配案件的“查看”。
5. 等待详情页 URL 包含“#/result”。
6. 抽取详情页文本并截图，用于统计恢复数据。

已排除的错误路径：
- 曾进入“设置”页，但该页与本次案件统计目标无关，已返回首页并从历史记录重新进入。
- 曾点击第二个“查看”，发现检材不匹配，已返回列表并改为点击第一个匹配项。

Pending workflow package:
- E:\work\hl\videoForensic\AI\dev-skills\.harness\electron-ui-verifier\pending\<session>\<run-id>\

该流程当前只作为本轮验证证据，尚未保存为长期 workflow，也尚未写入知识库。
注意：待保存的 workflow 只包含上方“流程待确认”的正确步骤，不包含“已排除的错误路径”。

>>> USER INPUT: EV-PERSIST-001 >>>
Decision:
Notes:
<<< END <<<
```

用户可直接在会话回答“确认保存”“不要保存”“第 3 步改为先清空输入框再输入”等。确认前不得执行持久化命令。

### 路径和状态约定

- `reports/<session>/<run-id>/`：现场验证证据，默认保留，用于回答用户问题。
- `pending/<session>/<run-id>/workflow.proposed.json`：清洗后的待审核正确 workflow，不进入正式资产搜索，不能包含 detour。
- `pending/<session>/<run-id>/workflow-review.md`：中文流程说明和用户确认区。
- `pending/<session>/<run-id>/evidence-index.json`：report、summary、截图、artifact、knowledge preflight/usage 摘要，以及已排除 detour 摘要。
- `pending/<session>/<run-id>/detours.json`：可选审计文件，记录错误页面、无关点击、回退动作和排除原因；该文件不得被 promote 为正式 workflow，也不得写入知识库资产。
- `workflows/<session>/<timestamp>-<name>.workflow.json`：用户批准后的正式 workflow 资产。
- `knowledge/`：只有批准后才写入基础 knowledge 和 action/workflow assets。

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：文档规则改造

目标（Goal）:

- 把默认流程改成“先查知识库、现场验证、生成 pending、用户确认、再持久化”。

做法（How）:

- 更新 `SKILL.md` 的必须流程和硬规则，删除默认固化和默认回写描述。
- 更新 `workflow.md` 的 Knowledge-First Gate，增加 Confirmed Persistence Gate。
- 更新 `knowledge.md`，把学习方式改为批准后执行；`--dry-run` 作为审核辅助。
- 更新 `actions.md`，说明 workflow 内 `learn` 字段不能绕过用户确认。
- 更新 `server.md`，说明 pending、report、approved workflow 的边界。

原因（Why）:

- 先把规则写清楚，避免后续实现只改脚本但 agent 仍按旧文档自动学习。

位置（Where）:

- 文件/模块（Files/modules）: `skills/electron-ui-verifier/SKILL.md`、`references/workflow.md`、`references/knowledge.md`、`references/actions.md`、`references/server.md`
- API/配置（APIs/configs）: 不改 API，仅改文档约束。
- 测试/文档（Tests/docs）: `rg` 检索旧默认回写描述和新门禁描述。

参考来源（References）:

- 当前用户需求。
- 当前 `electron-ui-verifier` 文档和脚本检索结果。

验证（Validation）:

- `rg "默认启用基础知识回写|每轮.*回写|自动把它固化|必须回写" skills/electron-ui-verifier`
- `rg "Confirmed Persistence|待审核|用户确认|pending" skills/electron-ui-verifier`

风险和回滚（Risks and rollback）:

- 风险：文档词汇不一致导致 agent 混淆。
- 回滚：恢复上一版文档并保留脚本默认行为。

阶段契约（Stage Contract）:

- 范围（Scope）: 只改 electron-ui-verifier 文档规则。
- 允许修改（Allowed changes）: skill 主文档和 references。
- 禁止修改（Forbidden changes）: 不改 Python 实现、不改历史 knowledge。
- 进入条件（Entry checks）: 计划获批，工作区安全。
- 退出条件（Exit checks）: 文档无互相矛盾规则。
- 必需验证（Required validation）: `rg` 文档检索。
- 是否预期提交（Commit expected）: yes，若用户批准阶段提交。

### 阶段 2（Stage 2）：默认执行不污染

目标（Goal）:

- CLI 和 server 默认不写正式 workflow，不写 knowledge。

做法（How）:

- 修改 `ev_action.py`、`ev_workflow.py`：
  - 移除 `appId/goal/workflow.learn` 的隐式学习触发。
  - `--learn`、`--learn-assets` 不直接学习，改为只在 approved/persist 路径允许，或直接报错提示走确认持久化流程。
  - 保留 `appId`、`goal`、`knowledgePreflight`、`knowledgeUsage` 作为 report 审计字段。
- 修改 `ev_server.py`：
  - `run_steps` 默认写 pending workflow，而不是正式 `workflows/`。
  - report 字段从单一 `workflowPath` 调整为可区分的 `pendingWorkflowPath`、`approvedWorkflowPath`、`workflowPersistenceStatus`。
  - 未批准时 `knowledgeWriteback.status = "pending_user_confirmation"` 或 `skipped_pending_confirmation`。

原因（Why）:

- 污染防线必须在工具默认行为层实现，不能只依赖 agent 记得传 `--no-learn`。

位置（Where）:

- 文件/模块（Files/modules）: `scripts/ev_action.py`、`scripts/ev_workflow.py`、`scripts/ev_server.py`
- API/配置（APIs/configs）: `/actions/run`、`/workflows/run` result 字段。
- 测试/文档（Tests/docs）: CLI help、py_compile、最小 workflow smoke。

参考来源（References）:

- 当前 `ev_action.py` / `ev_workflow.py` `should_learn` 逻辑。
- 当前 `ev_server.py` `workflow_file` 和 `persist_report_knowledge` 调用。

验证（Validation）:

- `python -m py_compile` 覆盖修改脚本。
- `ev_action.py --help`、`ev_workflow.py --help`。
- 运行最小 fake/session 或基于已有可用 session 的 workflow，检查未生成正式 `workflows/` 文件，knowledge 计数不增加。

风险和回滚（Risks and rollback）:

- 风险：旧测试依赖 `workflow` 字段。
- 缓解：保留兼容字段，但值指向 pending，并新增状态字段；文档说明未批准不是正式资产。
- 回滚：恢复 server 写 `workflows/` 和 CLI 隐式 learn。

阶段契约（Stage Contract）:

- 范围（Scope）: 执行默认行为和 report 字段。
- 允许修改（Allowed changes）: CLI 参数、server result/report 字段、相关测试。
- 禁止修改（Forbidden changes）: 不写历史迁移、不改 knowledge store schema 除非必要。
- 进入条件（Entry checks）: Stage 1 完成并提交或记录未提交原因。
- 退出条件（Exit checks）: 默认执行不会写 knowledge 或正式 workflow。
- 必需验证（Required validation）: py_compile、help、默认执行 smoke。
- 是否预期提交（Commit expected）: yes，若用户批准阶段提交。

### 阶段 3（Stage 3）：pending 审核包和流程说明生成

目标（Goal）:

- 每次 UI 验证结束后自动生成可供用户审核的中文流程说明。

做法（How）:

- 新增或扩展脚本，生成 pending 审核包：
  - `workflow.proposed.json`：从本轮探索中清洗出来的正确 workflow，不包含错误页面、错误点击、无关功能和重复尝试。
  - `workflow-review.md`：中文正确步骤、已排除 detour 摘要、证据、风险、确认区。
  - `evidence-index.json`：report、summary、artifact、截图、知识库预检、实际使用摘要和 detour 摘要。
  - `detours.json`：可选审计文件，记录被排除的错误路径和排除原因。
- 新增或扩展清洗规则：
  - 如果 step 后的 URL、title、关键文本或断言与目标不符，标记为 `detour`。
  - 如果 step 只是为了从错误页面返回、关闭误开的页面或恢复初始状态，标记为 `recovery`。
  - `workflow.proposed.json` 默认只保留 `correct` 和必要 `evidence` step。
  - 对无法自动判断的 step，在 `workflow-review.md` 标记“需要用户重点确认”，但不能自动写入知识库。
- 建立 action 到中文说明的映射：
  - `waitText` -> “等待页面出现文本”。
  - `waitUrlContains` -> “等待 URL 包含指定片段”。
  - `clickText` -> “点击可见文本/第 N 个匹配项”。
  - `fillText` -> “定位输入框并填写值”。
  - `pressKey` -> “按下键盘按键”。
  - `snapshot`、`screenshot`、`extractText`、`extractTable`、`collectConsole`、`collectNetwork` 等 -> “采集证据/抽取数据”。
- `workflow-review.md` 必须包含用户确认区：
  - `>>> USER INPUT: EV-PERSIST-001 >>>`
  - `Decision:`
  - `Notes:`
  - `<<< END <<<`

原因（Why）:

- 用户确认必须基于可读的真实操作流程，而不是只看 JSON 或最终结论。

位置（Where）:

- 文件/模块（Files/modules）: 可新增 `scripts/ev_review.py`，或在 `ev_server.py` 中生成 review artifact；推荐新增脚本降低 server 复杂度。
- API/配置（APIs/configs）: server result 返回 `pendingPackage`。
- 测试/文档（Tests/docs）: pending 包 JSON/Markdown 检查。

参考来源（References）:

- `references/actions.md` 支持的 action 列表。
- `ev_server.py` 的 `SUPPORTED_ACTIONS`。

验证（Validation）:

- 使用包含 wait、click、fill、extract、screenshot 的 fixture workflow 生成 review。
- 检查 `workflow-review.md` 包含完整中文步骤和确认区。
- 检查 pending 文件均位于 `.harness/electron-ui-verifier/pending/` 下。
- 使用包含错误页面、返回动作和最终正确路径的 fixture，确认 `workflow.proposed.json` 不包含 detour，`detours.json` 保留审计摘要。

风险和回滚（Risks and rollback）:

- 风险：复杂 `evaluate` 或 selector 无法自然语言化，或自动清洗误删必要步骤。
- 缓解：对无法精准翻译或无法确定是否正确的 step 输出 JSON 摘要和风险提示，要求用户重点确认；不确定时宁可不入知识库。
- 回滚：保留 pending workflow JSON，只删除 review 生成器。

阶段契约（Stage Contract）:

- 范围（Scope）: pending 审核包生成。
- 允许修改（Allowed changes）: 新增 review 脚本、server 返回字段、测试 fixture。
- 禁止修改（Forbidden changes）: 不写 knowledge，不晋级正式 workflow。
- 进入条件（Entry checks）: Stage 2 默认不污染通过。
- 退出条件（Exit checks）: 每次执行有 pending 包、中文正确步骤、detour 摘要和清洗后的 proposed workflow。
- 必需验证（Required validation）: fixture workflow review smoke、detour cleanup smoke。
- 是否预期提交（Commit expected）: yes，若用户批准阶段提交。

### 阶段 4（Stage 4）：用户批准后的持久化晋级

目标（Goal）:

- 只有用户明确批准后，才能把 pending 审核包晋级为正式 workflow 和知识库记录。

做法（How）:

- 新增 `ev_persist.py` 或等价入口：
  - `approve --pending <abs-path> --decision "用户确认说明"`。
  - 校验 pending 包必须在 `.harness/electron-ui-verifier/pending/` 下。
  - 校验 pending 包包含 report、workflow、review 和 evidence index。
  - 校验 `workflow.proposed.json` 不包含 `detour`、`wrongPage`、`unrelated` 或 `recoveryOnly` step；如果包含，拒绝持久化并要求重新清洗或用户重新确认。
  - 将 workflow 复制或导出到 `.harness/electron-ui-verifier/workflows/<session>/...workflow.json`。
  - 按参数写入基础 knowledge；只有显式 `--include-assets` 才写 action/workflow assets。
  - 写入 `persistence.json`，记录批准时间、用户确认摘要、来源 pending、目标 workflow、knowledge 写入结果。
- `reject --pending <abs-path> --reason ...`：
  - 标记 pending 为 rejected，不删除证据，不写 knowledge。
- `revise --pending <abs-path>` 不强制实现复杂编辑器；推荐由 agent 修改源 workflow 后重新跑验证生成新 pending。

原因（Why）:

- 持久化是独立、可审计的动作，不能混在现场验证执行里。

位置（Where）:

- 文件/模块（Files/modules）: 新增 `scripts/ev_persist.py`，复用 `ev_learn.py`、`ev_asset_extract.py`、`ev_knowledge_extract.py` 能力。
- API/配置（APIs/configs）: 不要求 server 新 endpoint；优先 CLI 脚本封装，agent 不直接调用 HTTP。
- 测试/文档（Tests/docs）: approve/reject smoke。

参考来源（References）:

- `scripts/ev_learn.py` 现有从 report 学习能力。
- `scripts/ev_assets.py` 现有 asset 查询能力。

验证（Validation）:

- `approve` 后 `workflows/` 出现正式 workflow。
- 未传 `--include-assets` 时只写基础知识，不写 action/workflow asset。
- 传 `--include-assets` 后 `ev_assets.py list-workflows` 可查询到资产。
- `reject` 后 knowledge 计数不增加，pending 状态为 rejected。
- 使用包含 detour 的 pending 包执行 approve，必须被拒绝，且不写正式 workflow 和 knowledge。

风险和回滚（Risks and rollback）:

- 风险：批准后写知识库失败，但 workflow 已保存；或 detour 标记遗漏导致错误路径被批准。
- 缓解：`persistence.json` 分步记录状态；失败时最终回复说明 partial，并允许重试 knowledge 写入。
- 回滚：删除 approved workflow 文件和本次 knowledge 记录；如果 knowledge 无事务回滚，则记录 follow-up cleanup。

阶段契约（Stage Contract）:

- 范围（Scope）: pending 晋级、拒绝和持久化审计。
- 允许修改（Allowed changes）: 新脚本、knowledge 调用、文档示例。
- 禁止修改（Forbidden changes）: 不自动批准，不根据验证通过自动写库。
- 进入条件（Entry checks）: Stage 3 pending 包可生成。
- 退出条件（Exit checks）: approve/reject 行为可验证。
- 必需验证（Required validation）: approve/reject smoke，assets 查询。
- 是否预期提交（Commit expected）: yes，若用户批准阶段提交。

### 阶段 5（Stage 5）：端到端验证和最终规则复查

目标（Goal）:

- 确认默认不污染、用户确认后持久化、最终回复规则三者一致。

做法（How）:

- 运行静态检查、CLI help、JSON 解析和最小 smoke。
- 若环境允许，使用 VideoForensic 或轻量 Electron session 做一次真实验证：
  - 先查知识库。
  - 现场执行 workflow。
  - 生成 pending 审核包。
  - 不批准时确认 knowledge/workflows 不新增正式记录。
  - 用测试性批准命令在可控样本上验证 approve 后写入。
- 复查文档中是否仍存在“默认回写”“自动固化”的旧描述。

原因（Why）:

- 该改动的核心风险是流程文档和工具行为不一致，必须端到端复查。

位置（Where）:

- 文件/模块（Files/modules）: 全部修改文件。
- API/配置（APIs/configs）: CLI result、report、pending 包、knowledge。
- 测试/文档（Tests/docs）: py_compile、help、rg、smoke。

参考来源（References）:

- 本计划的验收标准。
- `complex-coding-harness` 阶段退出和最终交付门禁。

验证（Validation）:

- `python -m py_compile skills/electron-ui-verifier/scripts/*.py` 或精确脚本列表。
- `ev_action.py --help`、`ev_workflow.py --help`、`ev_persist.py --help`。
- `rg` 确认旧默认回写表述已删除或改写。
- pending/approve/reject smoke。

风险和回滚（Risks and rollback）:

- 风险：真实 Electron 环境不可用。
- 缓解：记录不可用原因，使用 fixture 和已有 report 验证数据流；不声称真实 UI 通过。
- 回滚：按阶段 commit 回退，保留本计划和验证记录。

阶段契约（Stage Contract）:

- 范围（Scope）: 验证、文档复查、最终记录。
- 允许修改（Allowed changes）: 修复验证发现的小缺陷和文档冲突。
- 禁止修改（Forbidden changes）: 不追加新功能，不清理历史 knowledge。
- 进入条件（Entry checks）: Stage 4 完成。
- 退出条件（Exit checks）: 所有必需验证通过或记录阻塞。
- 必需验证（Required validation）: 静态、CLI、smoke、规则检索。
- 是否预期提交（Commit expected）: yes，若用户批准阶段提交。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- 当前 workspace：`E:\work\hl\videoForensic\AI\dev-skills`
- Python：使用当前可用 Python 执行 finite checks；如果需要启动 verifier server，则使用 `.harness/electron-ui-verifier/environment.json` 中的 Python，并先运行 `ev_check_env.py`。
- process-manager：仅 verifier server 属于长期进程；本计划阶段不启动长期进程。

临时覆盖（Temporary overrides）:

- 无。

## Git 上下文（Git Context）

主分支（Main branch）:

- main

任务类型（Task type）:

- feature

工作分支（Working branch）:

- harness/feature

分支动作（Branch action）:

- already-on-branch

同步来源（Sync source）:

- not-run，本计划阶段不执行分支同步。

最近同步（Last sync）:

- not-checked。

分支占用（Branch occupancy）:

- 串行 `git log <main>..HEAD`: implementation 前检查。
- 串行 `git -c diff.autoRefreshIndex=false diff <main>...HEAD --name-only`: implementation 前检查。
- 现有提交属于本任务（Existing commits belong to this task）: implementation 前检查。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行：yes。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git：yes。
- 非 Git 文件读取和文本搜索是否可并发：yes。

只读 Git 选项（Read-only Git options）:

- 状态检查优先：`git --no-optional-locks status --short --branch`
- diff 检查优先：`git -c diff.autoRefreshIndex=false diff <range>`
- 最终提交前如需精确状态，可在确认无其它 Git 命令运行后串行执行普通 `git status --short --branch`：yes

Index lock 恢复策略（Index lock recovery）:

- lock 路径解析命令：`git rev-parse --git-path index.lock`
- 删除前检查：精确路径、文件存在、大小/mtime 稳定、无活跃或未知归属 Git 进程
- 删除范围：只删除解析出的精确 `index.lock`，禁止通配符、递归删除和删除其它 `.lock`
- 删除后检查：串行 `git --no-optional-locks status --short --branch`

Git Lock Recovery Log:

| 时间（Time） | lock 路径（Lock path） | 文件大小/mtime（Size/mtime） | Git 进程检查（Process check） | 操作（Action） | 后续 status（Follow-up status） |
| --- | --- | --- | --- | --- | --- |
| not-needed |  |  |  |  |  |

提交策略（Commit policy）:

- 当前仅规划，提交策略为 `not_authorized`。
- 如果用户批准实施并授权阶段提交，每阶段使用 `git commit -F .harness/tasks/2026-07-02/feature/electron-ui-verifier-confirmed-persistence/tmp/commit-message.txt`。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: no。
- 未合回时代码停留在（If not merged, code remains on）: harness/feature。
- 合并前需要用户确认（User confirmation needed before merge）: yes。

分支安全（Branch safety）:

- 切换前已检查工作区：not-applicable。
- 不自动 stash：yes。
- 不自动 rebase：yes。
- 不自动 reset：yes。

热修复插入（Hotfix interruption）:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支：yes。
- 决策：not-needed。

未解决问题（Open issues）:

- 当前 `git status` 显示存在 ignored/未跟踪历史 `.harness` 运行产物，本任务不清理。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| `rg` | 检索旧规则和新规则覆盖 | all | available | 低 | PowerShell `Select-String` | not-needed |
| Python | py_compile、CLI help、smoke | Stage 2-5 | available via environment | 解释器不一致 | 使用 `.harness/electron-ui-verifier/environment.json` 指定解释器 | implementation 前确认 |
| process-manager | 托管 verifier server | Stage 5 optional | not-started | manager 离线会阻塞真实 UI 验证 | fixture/report smoke | 如需启动则按规则执行 |
| VideoForensic | 真实 Electron 验证样本 | Stage 5 optional | user-provided | 应用状态和数据变化 | fixture 和已有 report | 真实验证前确认应用状态 |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- planning 阶段：no。
- implementation Stage 5 若执行真实 Electron UI 验证：yes，仅 verifier server；Electron GUI 应用本体仍不用 process-manager。

process-manager skill 是否存在（process-manager skill available）:

- 当前会话 skills 列表未暴露 repo-local `process-manager`，但仓库内存在相关 skill；实现阶段如需长期进程，必须读取对应 `SKILL.md` 和 workflow 后再操作。

规则结论（Rule decision）:

- 如果 `process-manager` 存在，verifier server 必须使用它管理。
- Electron GUI 应用本体是特殊被测窗口，不用 `process-manager`。
- finite command，例如 py_compile、help、JSON 检查、`rg`，不进入 `process-manager`。
- manager 离线时必须停止真实 UI 验证，请求用户手动启动 manager 或授权 bootstrap；不能退回 shell 后台启动。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| electron-ui-verifier | verifier-server | Stage 5 optional | `.harness/process-manager/services/electron-ui-verifier.json` | `ev_health.py` / `pm_ready.py` | pending | execution-plan validation evidence | pending |

禁止 shell 后台启动确认（No shell background start）:

- yes。

历史视图需求（Needs `pm_list --history`）:

- no。

证据保留位置（Evidence retention location）:

- `execution-plan.md` 和 `.harness/tasks/2026-07-02/feature/electron-ui-verifier-confirmed-persistence/artifacts/`。

日志沉淀确认（Log evidence persisted）:

- implementation 阶段记录。

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前必须复查本节。
- 启动、验证、调试 verifier server 前必须复查本节。
- 上下文压缩或中断恢复后必须复查本节和 `Resume Summary`。

## 验证（Validation）

必需验证（Required）:

- 文档检索：确认旧“默认固化/默认回写”描述已删除或改写，新“pending/用户确认/approved 持久化”规则存在。
- Python 静态：`py_compile` 覆盖修改脚本。
- CLI 帮助：新增或变更脚本的 `--help` 能正常输出。
- 默认不污染 smoke：执行 action/workflow 后不新增正式 `workflows/`，不新增 knowledge 写入。
- pending 审核包 smoke：生成 `workflow.proposed.json`、`workflow-review.md`、`evidence-index.json`。
- detour 清洗 smoke：包含错误页面、错误点击、返回动作的探索记录必须生成 detour 审计，但 `workflow.proposed.json` 不能包含这些步骤。
- approve/reject smoke：approve 后写正式 workflow 和 knowledge；reject 后不写 knowledge。
- detour approve guard smoke：如果 pending proposed workflow 仍含 detour 标记，approve 必须失败且不写库。

已执行（Executed）:

- 命令/工具（Command/tool）: `rg`、文档和脚本片段读取。
- 结果（Result）: 发现当前默认回写和自动固化问题。
- 证据（Evidence）: 本计划 Context 和 Evidence levels。
- 覆盖范围（Covers）: 规划前上下文。
- 未覆盖（Not covered）: 尚未修改源码，尚未运行实现后的验证。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | `rg learn/workflow/知识库` | passed | 定位默认学习和固化路径 | 未验证实现 | shell output | 用于制定方案 |
| Stage 1 | `rg` 文档检索 | passed | 新旧规则一致性 | 未覆盖真实 UI | shell output | 已完成 |
| Stage 2 | `py_compile`、`ev_action.py --help`、`ev_workflow.py --help` | passed | 默认不污染入口、废弃 learn 参数 | 未启动 server | shell output | 已完成 |
| Stage 3 | `ev_pending_smoke.py` | passed | 中文步骤、审核包、错误路径清洗 | 用户真实确认 | shell output | 已完成 |
| Stage 4 | `ev_pending_smoke.py` | passed | approve/reject 基础链路、错误路径拒绝入库、include-assets 写入 | 历史污染清理 | shell output | 已完成 |
| Stage 5 | `ev_asset_extract_smoke.py`、`ev_knowledge_smoke.py --temp`、`py_compile`、`rg` | passed | 资产抽取、知识库存储、静态检查、规则一致性 | 未执行真实 Electron UI | shell output | 已完成 |

可选验证（Optional）:

- 使用 VideoForensic 做一轮真实验证，但不批准持久化，确认最终回复给 pending 路径且知识库不新增。
- 再用一份测试性 pending 包执行 approve，确认正式 workflow 可被查询。

产物（Artifacts）:

- 截图（Screenshot）: Stage 5 optional。
- 日志（Log）: process-manager/verifier server logs if used。
- Trace: not-planned。
- 报告（Report）: pending package 和 report.json。

未覆盖（Not covered）:

- 历史已污染的 workflow/knowledge 记录。
- 非 Electron 原生窗口自动化。

无法执行时（If unable to run）:

- 如果真实 Electron 或 verifier server 不可用，记录环境原因，使用 fixture/report smoke 覆盖数据流；不得声称真实 UI 验证通过。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/knowledge.md`
- `skills/electron-ui-verifier/references/actions.md`
- `skills/electron-ui-verifier/references/server.md`

Changelog 计划（Changelog plan）:

- 如果仓库已有 changelog 或等价变更记录，按阶段记录。
- 当前未确认使用哪个 changelog 文件，实施前检查仓库约定；找不到则在 `execution-plan.md` 的 Implementation Progress 和 Commit Log 记录即可。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `SKILL.md` | no | 局部规则条目 | 完整读取并 `rg` 检索 |
| `references/workflow.md` | yes | 二级章节 | 完整读取、旧规则检索、新规则检索 |
| `references/knowledge.md` | yes | 学习方式和状态章节 | 完整读取、命令示例检查 |
| `references/actions.md` | yes | workflow 结构和 learn 章节 | 完整读取、示例 JSON 检查 |
| `references/server.md` | yes | 内部文件目录和 session 流程章节 | 完整读取、路径约定检查 |
| `ev_action.py` / `ev_workflow.py` | no | 参数和 should_learn 局部逻辑 | py_compile、help |
| `ev_server.py` | yes | workflow/pending/report/learn 局部函数 | py_compile、smoke |
| 新增脚本 | unknown | 完整脚本或函数块 | py_compile、help、smoke |

写入规则（Write rules）:

- 分段 patch 是落盘策略，不要求一次性生成全部细节；大内容首次写入前必须先有全局框架，再分模块递进式细化，最后整体复查。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 分段判断是写入风险判断，不是最终内容长度承诺；不得为了符合判断结果删减功能、压缩测试或省略文档。
- 写入范围无法判断时填 `unknown`，按 `medium/large` 风险保守处理；实际新增超过 300 行时必须升级为分段写入。
- 目标文件超过 500 行时，默认禁止整文件重写。
- 代码、文档、规划、模板、eval、changelog 和任务状态文件都适用。

整体复查（Whole-file review）:

- 写完后重新读取完整目标文件：yes。
- 需要检查的整体一致性：默认不污染、pending/approved 路径、用户确认门禁、最终回复规则、知识库预检仍为只读第一步。
- 对应验证命令或方式：`rg`、py_compile、help、smoke。

patch 失败处理（Patch failure handling）:

- 读取目标文件确认是否有部分写入：yes。
- 失败原因判断：上下文不匹配、patch 过大、工具错误。
- 重试策略：缩小到章节或函数级 patch，不用 shell 拼接文件绕过。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | recommended | 默认是否仍保留现场验证 report、截图和 artifact？ | 保留。它们是本轮回答证据，不是长期可复用 workflow 或知识库。 | `workflow.md`、`server.md` |
| D-002 | no | recommended | `--learn` 是否允许绕过用户确认？ | 不允许。学习动作只能在 approve/persist 阶段执行。 | CLI、server、docs |
| D-003 | no | recommended | 未确认的 pending workflow 是否可被知识库搜索命中？ | 不允许。pending 只供本轮审阅，不进入正式资产索引。 | storage、assets、suggest |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pass | Evidence levels 表已记录 read/confirmed 来源 |
| 影响面矩阵完整（Impact matrix complete） | pass | API、数据、配置、兼容性、测试、文档已覆盖 |
| 候选方案比较充分（Options compared enough） | pass | 比较方案 A 最小改动和方案 B 结构化门禁 |
| 每阶段可独立验证（Stages independently verifiable） | pass | Stage 1-5 均有验证方式 |
| 方案变更触发条件清楚（Reapproval triggers clear） | pass | Decision 章节已列出触发条件 |
| 用户批准摘要可记录（Approval summary ready） | pass | Plan Approval 章节待用户确认后填写 |

质量结论（Quality result）:

- `pass`

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- `pass`

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 初始方案若只改 `--learn` 会遗漏 server 自动固化 workflow | 采用 pending/approved 路径拆分 | pass |
| 优化（Optimizations） | 不需要复杂多级审批或自动迁移，避免规则累赘 | 只设置一个持久化确认门禁和一个 pending 包 | pass |
| 缺失项（Missing items） | 需要明确 report 证据和正式 workflow 资产的区别；需要明确错误路径不能入库 | 增加路径和状态约定；增加 detour 清洗、审计和 approve guard | pass |
| 风险（Risks） | 用户可能把 pending 路径误认为正式资产；自动化探索中走错路径可能污染知识库 | 最终回复和文档必须标明未持久化、未写库；只允许清洗后的正确路径进入 proposed workflow | pass |
| 一致性（Consistency） | 当前知识库优先规则与新确认门禁可能冲突 | 改为“先查知识库，再现场验证，再待确认持久化” | pass |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：no。
- `Plan Self-Review` 是否需要重跑：no。
- `Readiness Gate` 是否需要重跑：no。
- 原因：自查修复已反映在当前计划中，未改变目标和阶段范围。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pass | Problem 和 Acceptance 已定义 |
| 上下文已收集（Context collected） | pass | 已读取 harness 和 electron-ui-verifier 关键文档/脚本 |
| 候选方案已比较（Options compared） | pass | Options 章节 |
| 决策已记录（Decision recorded） | pass | 选择方案 B |
| 实施阶段已细化（Implementation stages detailed） | pass | Stage 1-5 |
| 环境已确认（Environment confirmed） | pass | `.harness/environment.md` 已读取 |
| Git 上下文已确认（Git context confirmed） | pass | 当前分支 `harness/feature`，主分支 `main` |
| 工具已确认（Tooling confirmed） | pass | Tooling 和 Process Manager Gate |
| 验证已确认（Validation confirmed） | pass | Validation 章节 |
| 最终交付证据已规划（Final delivery evidence planned） | pass | pending、report、knowledge、commit 记录 |
| 文档更新已确认（Documentation updates confirmed） | pass | Documentation 章节 |
| 风险已识别（Risks identified） | pass | 各阶段风险和自查 |
| 规划自查已通过（Plan self-review passed） | pass | Plan Self-Review |
| 阻塞问题已关闭（Blocking questions closed） | pass | 无 blocking 问题 |

就绪结论（Readiness result）:

- `pass`

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 用户于 2026-07-02 回复“按方案 实现”。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: Stage 1-5 实现。
- 阶段提交授权（Stage commit authorization）: not explicitly authorized。
- 工具/MCP 授权（Tool/MCP authorization）: finite CLI checks only；未启动长期服务。
- 文档更新授权（Documentation authorization）: approved。

提交策略（Commit policy）:

- `not_authorized`

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- in_progress

当前阶段（Current stage）:

- Stage 5 complete

已完成阶段（Completed stages）:

- Planning
- Stage 1
- Stage 2
- Stage 3
- Stage 4
- Stage 5

剩余阶段（Remaining stages）:

- none

下一步自动动作（Next automatic action）:

- final delivery

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no, after implementation approval unless the user explicitly requests stage-only execution or a Stop Condition is active

active-task 同步字段（active-task sync fields）:

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "ready_for_final_delivery",
  "current_stage": "Stage 5 complete",
  "remaining_stages": [],
  "next_automatic_action": "final delivery",
  "stop_condition": "none",
  "state_source": "execution-plan.md"
}
```

状态同步规则（State sync rules）:

- `execution-plan.md` 是唯一主契约；`.harness/active-task.json` 只作为恢复入口和摘要索引。
- 如果用户批准实施，必须先把 `Execution Control` 改为 `run-to-completion` 和 `in_progress`，再开始 Stage 1。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | completed | 已完成方案、门禁、自查和实施阶段设计 | 文档/脚本上下文读取 | 本文件 | 已进入实施 |
| Stage 1 | completed | 已更新 SKILL 和 references，改为确认后持久化规则 | `rg` 文档检索通过 | `SKILL.md`、`workflow.md`、`knowledge.md`、`actions.md`、`server.md` | 继续 Stage 2 |
| Stage 2 | completed | CLI/server 默认不再写正式 workflow 或 knowledge，`--learn` 改为废弃提示 | py_compile、help 通过 | `ev_action.py`、`ev_workflow.py`、`ev_server.py` | 继续 Stage 3 |
| Stage 3 | completed | 新增 pending 审核包和 detour 清洗模块 | `ev_pending_smoke.py` 通过 | `ev_pending.py`、pending fixture | 继续 Stage 4 |
| Stage 4 | completed | 新增 `ev_persist.py`，approve 后晋级 workflow 并写 knowledge，detour guard 拒绝错误路径 | `ev_pending_smoke.py` 通过 | `ev_persist.py`、knowledge counts | 继续 Stage 5 |
| Stage 5 | completed | 完成静态、help、pending、asset、knowledge smoke 和规则检索 | 全部通过；未跑真实 Electron UI | shell output | final delivery |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | passed | none | passed | not-applicable | passed | passed |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1-5 | yes | yes | yes | not-applicable | not-applicable | yes | not authorized | passed |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证已完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 5 | yes | yes | yes | no commit authorization | no | no | no | yes | yes | no | final delivery |

结论（Decision）:

- 当前是规划停止点，必须等待用户批准后才能实现。

规则（Rules）:

- 用户批准后进入 `run-to-completion`，阶段边界不能作为最终停止点。
- 如果还有 pending stage，且没有停止条件，也不需要重新批准，下一动作必须是 `continue Stage N`。

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Planning | 仅规划未改源码 | follow-up | implementation 阶段逐阶段 review |

## 恢复摘要（Resume Summary）

- 整体目标（Overall goal）: 将 electron-ui-verifier 的 workflow/knowledge 持久化改为用户确认后执行，避免错误流程污染知识库。
- 执行模式（Execution mode）: run-to-completion。
- 整体任务状态（Overall status）: ready_for_final_delivery。
- 已完成阶段（Completed stages）: Planning, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5。
- 当前阶段（Current stage）: Stage 5 complete。
- 剩余阶段（Remaining stages）: none。
- 最新 commit（Latest commit）: none for this planning task。
- 下一步自动动作（Next automatic action）: final delivery。
- 当前停止条件（Current stop condition）: none。
- 状态来源（State source of truth）: execution-plan.md。
- 长期进程规则（Process manager rule）: implementation Stage 5 如需 verifier server，必须使用 process-manager；Electron GUI 本体不用 process-manager。
- 未覆盖/风险（Not covered/risks）: 未执行真实 Electron UI；历史污染不在本任务范围；用户确认前仍需 agent 正确判断流程是否可持久化。
- 不得停止说明（Do not stop note）:
  - 用户批准实施后，阶段边界不是停止条件。继续直到所有批准阶段和最终交付门禁完成，除非出现 Stop Condition。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/2026-07-02/feature/electron-ui-verifier-confirmed-persistence/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Stage 1-5 | dev-skills | not committed | commit not authorized in current request | CHANGELOG.md |

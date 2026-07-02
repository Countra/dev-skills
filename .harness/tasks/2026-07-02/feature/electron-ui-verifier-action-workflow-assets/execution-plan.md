# 执行计划：Electron UI Verifier action/workflow 资产化增强

## 问题定义（Problem）

目标（Goal）:

- 将 `electron-ui-verifier` 每次自动化验证中真实执行过的操作沉淀为可复用的 action 资产和 workflow 资产。
- 让知识库不仅保存页面、元素和 workflow 摘要，还能保存可直接复用、可导出、可分享、可复验的 workflow JSON。
- 支持从 report 自动整理候选 action/workflow，从知识库检索命中后复用，并能导出到独立 workflow 文件供其他用户或环境执行。

非目标（Non-goals）:

- 不实现视觉模型、OCR 或全自动探索。
- 不保存 cookie、token、localStorage、请求头、请求体、响应体或敏感大段业务文本。
- 不改变 Electron GUI 应用本体启动规则；GUI 进程仍不使用 `process-manager`。
- 不让知识库建议替代真实 UI 验证结论。

验收标准（Acceptance）:

- 有清晰的 action/workflow 资产数据模型、状态流转、去重、参数化、导出和安全边界。
- 有从 `report.json` 整理 action/workflow 资产的方案，区分 raw trace、candidate asset 和 verified/stable asset。
- 有 CLI 入口规划，覆盖学习、查询、建议、导出和复验。
- 有分阶段实施计划，每阶段可独立验证和提交。
- 有文档更新计划，把该能力融入 `electron-ui-verifier` skill。

约束（Constraints）:

- 本任务使用 `complex-coding-harness` 托管；当前只制定规划，不实现代码。
- 方案确认前不得修改 `electron-ui-verifier` skill 本体。
- 所有 Git 命令串行执行，不放入并发工具。
- 大内容落盘使用分段 patch，规划和文档同样适用。
- verifier server 如需验证启动，必须由 `process-manager` 托管；finite command 不进入 `process-manager`。

待确认项（Open uncertainties）:

- 无 blocking 项。默认首版只实现本地 SQLite/JSON 资产库和导出能力，不引入外部服务或第三方依赖。

## 上下文（Context）

本地代码（Local code）:

- `skills/electron-ui-verifier/scripts/ev_knowledge_store.py`：已有 app、screen、element、workflow、evidence 表和 FTS 检索。
- `skills/electron-ui-verifier/scripts/ev_knowledge_extract.py`：已有从 report/artifact 抽取候选 workflow 的逻辑，但缺少 action 资产和 workflow 文件导出。
- `skills/electron-ui-verifier/scripts/ev_learn.py`：已有显式从 report 写入知识库的入口。
- `skills/electron-ui-verifier/scripts/ev_suggest.py`：已有按目标搜索候选 workflow/element 的入口。
- `skills/electron-ui-verifier/scripts/ev_workflow.py`、`ev_action.py`：已有执行 workflow/action 的入口。
- `skills/electron-ui-verifier/scripts/ev_server.py`：已有 report 生成和显式 `--learn` 集成点。

本地文档（Local docs）:

- `skills/electron-ui-verifier/SKILL.md`：已要求使用常驻 verifier server、`ev_*` 脚本和可选知识库。
- `skills/electron-ui-verifier/references/actions.md`：已定义 workflow/action JSON 格式和支持动作。
- `skills/electron-ui-verifier/references/knowledge.md`：已定义知识库状态、学习、查询、建议和提升规则。
- `.harness/environment.md`：当前主分支为 `main`，feature 类任务使用 `harness/feature`。

外部来源（External sources）:

- Playwright Locators 官方文档：定位应优先使用面向用户的角色、文本、label、placeholder 等语义 locator，避免脆弱坐标。
- Playwright Codegen/Trace/POM 官方实践：真实操作轨迹可以转化为可复用脚本或页面对象，但需要清洗和抽象。
- Chrome DevTools Protocol DOMSnapshot、Runtime、Accessibility、Network：当前 skill 的 raw CDP 采集和报告证据来源。
- SQLite FTS5 官方文档：本地全文检索适合 action/workflow 搜索，首版无需外部检索服务。

用户约束（User constraints）:

- 每次自动化验证都应尽量整理成 workflow，并保存分步 action。
- 资产既用于知识库搜索复用，也用于导出分享，让其他人能在自己的环境复现流程。
- action/workflow 不能无限膨胀，需要状态、去重、置信度、证据和清理策略。
- 不需要考虑旧 knowledge DB 数据迁移兼容；按新 schema 重新设计，旧库默认拒绝隐式迁移。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 当前已有 workflow 知识但缺少 action 资产表和导出脚本 | read | `ev_knowledge_store.py`、`ev_knowledge_extract.py`、`ev_knowledge.py` | 需要重新设计数据模型和 CLI |
| report 中已有 step record、artifact 和 status，可作为 raw trace 来源 | read | `ev_server.py`、`actions.md` | 可从 report 整理 action/workflow |
| 语义 locator 比坐标稳定 | external | Playwright Locators 官方文档 | action 资产应优先保存语义 selector，坐标只作 fallback |
| 用户需要可分享 workflow 文件 | confirmed | 当前用户讨论 | 必须规划 export workflow 能力 |

## 候选方案（Options）

### 方案 A：只把 report steps 原样导出为 workflow

- 做法（How）: 新增简单脚本读取 `report.json` 的 `steps`，转换为 workflow JSON。
- 优点（Pros）: 实现快，能马上保存流程。
- 缺点（Cons）: 容易保留偶然坐标、临时文本、失败步骤和不可复用数据；检索质量有限。
- 风险（Risks）: 把一次性探索误当成稳定资产，污染复用结果。
- 验证（Validation）: report -> workflow JSON 解析和执行 smoke。
- 回滚（Rollback）: 删除导出脚本即可。

### 方案 B：结构化 action/workflow 资产库（推荐）

- 做法（How）: 重新设计知识库，新增 action 资产、workflow 资产版本、参数、证据、导出和复验流程。
- 优点（Pros）: 支持检索、复用、分享、状态提升、去重和参数化；长期价值高。
- 缺点（Cons）: 实现阶段更多，需要重新设计 schema 和重建本地知识库。
- 风险（Risks）: 初版抽象过度会增加复杂度；参数化错误可能导致 workflow 不可执行。
- 验证（Validation）: 单元 smoke、真实 report 学习、导出 JSON 解析、可选复跑验证。
- 回滚（Rollback）: 独立新增表和脚本，可删除或禁用，不影响现有执行入口。

### 方案 C：引入 Playwright codegen/trace 作为主资产来源

- 做法（How）: 使用 Playwright codegen 或 trace 作为 action/workflow 记录器，再转换到 skill workflow。
- 优点（Pros）: 生态成熟，能捕获真实操作。
- 缺点（Cons）: 当前 skill 使用 raw CDP server-only 架构；引入 codegen 会增加环境和兼容复杂度。
- 风险（Risks）: 打包 Electron CDP、旧 Chromium 和 Playwright context 兼容不稳定。
- 验证（Validation）: 需要额外 GUI/Playwright 环境验证。
- 回滚（Rollback）: 移除 codegen 依赖。

## 决策（Decision）

选择方案（Chosen option）:

- 选择方案 B：结构化 action/workflow 资产库。

原因（Why）:

- 它同时满足知识库检索、复用、分享和复验目标。
- 复用现有 report、workflow 执行入口和本地 SQLite/FTS5 基础，不引入外部服务。
- 可以保留方案 A 的导出能力，但把它放在清洗后的资产层，而不是原始 steps 直出。

影响（Impact）:

- 需要重新设计知识库 schema，新增 action 资产、workflow 资产元数据和导出能力。
- 需要新增 report 整理模块和 CLI。
- 需要更新 `SKILL.md`、`references/knowledge.md`、`references/actions.md` 和示例。

可逆性（Reversibility）:

- 中等。新增模块和执行入口相对独立；知识库 runtime 数据按重建设计处理，不承诺旧库回滚。

变更条件（Change conditions）:

- 如果 schema 重建策略影响用户保留旧知识库的需求，必须重新请求批准；当前默认不保留旧知识库数据。
- 如果需要新增第三方依赖、外部服务或云端存储，必须重新请求批准。

方案变更触发条件（Reapproval triggers）:

- 新增依赖、外部服务、网络上传或向量数据库。
- 改变现有 workflow/action JSON 的执行语义。
- 保存敏感字段、截图长期入库或业务大段文本。
- 需要真实启动 Electron GUI 或长期 server 做不可替代验证。

## 目标架构（Target Architecture）

核心分层（Layers）:

| 层级（Layer） | 作用（Purpose） | 存储/产物（Storage/output） | 可复用性（Reusability） |
| --- | --- | --- | --- |
| Raw Trace | 真实执行轨迹，来自 report steps 和 artifact | `report.json`、artifact | 只作为证据，不直接复用 |
| Action Asset | 清洗后的单步操作资产 | SQLite `action_assets` 表 | 可搜索、可组合、可复验 |
| Workflow Asset | 由 action 组合成的流程资产 | SQLite `workflow_assets` 表 | 可导出、可分享、可复验 |
| Exported Workflow | 独立 workflow JSON 文件 | 用户指定绝对路径 | 跨环境复现 |

核心原则（Principles）:

- 原始执行步骤不等于稳定 workflow，必须先清洗、去敏感、去偶然值和标注状态。
- action 是最小复用单元，workflow 是 action 的有序组合。
- 每个 action/workflow 都必须带来源 evidence，指向 report 和 artifact。
- 所有可导出 workflow 都必须可 JSON 解析，并符合 `references/actions.md` 定义。
- 坐标点击只能作为 fallback；优先保存文本、role、selector、锚点和页面上下文。

数据模型（Data model）:

| 实体（Entity） | 作用（Purpose） | 关键字段（Key fields） |
| --- | --- | --- |
| `ActionAsset` | 可复用的单步操作 | `actionId`、`appId`、`screenId`、`kind`、`label`、`stepJson`、`selectorCandidates`、`params`、`status`、`confidence` |
| `WorkflowAsset` | 可复用流程 | `workflowAssetId`、`appId`、`goal`、`readiness`、`steps`、`params`、`assertions`、`sourceWorkflowId`、`status`、`confidence` |
| `WorkflowExport` | 导出记录 | `exportId`、`workflowAssetId`、`outputPathHash`、`createdAt`、`formatVersion` |
| `AssetEvidence` | 资产证据 | `evidenceId`、`sourceReport`、`stepIds`、`artifactRefs`、`notes` |

状态流转（Status flow）:

- `observed`: 从 raw trace 观察到，尚未清洗完成。
- `candidate`: 已清洗、可作为候选复用。
- `verified`: 复跑通过或有新的 report 证据支撑。
- `stable`: 多次验证或用户确认后可优先建议。
- `stale`: 页面指纹、app 版本或断言变化后需要复验。
- `deprecated`: 已废弃，不默认召回。

参数化策略（Parameterization）:

- 固定 UI 文案可以保留，例如菜单、按钮、tab 名称。
- 业务数据、案件名、路径、日期、序号、搜索词、导出路径应转为参数。
- `clickText` 的 `index` 仅在必要时保留，并记录所在 screen 和邻近锚点。
- `evaluate` 只允许保留显式 `allow: true` 的代码；导出前必须标记风险。
- 参数模板统一使用 `${name}` 占位，不把业务路径、案件名、日期序号直接写入 stable workflow。
- 导出时如果存在未绑定参数，必须在 metadata 中列出 `requiredParams`，不能静默写空值。

去重和容量策略（Deduplication and retention）:

- `action_assets` 去重键使用 `appId + screenId + kind + normalized stepJson + selectorCandidates fingerprint`。
- `workflow_assets` 去重键使用 `appId + goal + ordered action fingerprints + assertions fingerprint`。
- 同一去重键再次学习时只更新 evidence、lastSeenAt、confidence 和计数，不重复插入资产。
- 首版 cleanup 默认不删除 `verified/stable`，只裁剪最旧的 `observed/candidate/stale/deprecated`。
- cleanup 必须提供 dry-run 输出；真实删除时同时删除 FTS 行和孤立 evidence 关联，不删除源 report/artifact 文件。

导出格式（Export format）:

- 默认导出为现有 workflow JSON，保持 `readiness` + `steps` 结构。
- 可选附加 `metadata`，包括 `appId`、`goal`、`sourceWorkflowId`、`sourceEvidence`、`exportedAt`。
- 导出路径必须是绝对路径；如果文件存在，默认拒绝覆盖，除非传 `--overwrite`。
- 导出后必须立即重新读取文件并做 JSON parse、schema shape 检查和敏感字段扫描。
- 导出的 workflow 只允许包含 `references/actions.md` 支持的 action key；未知 action 必须失败并列出 step id。
- 导出不会自动提升资产状态；只有复验成功或用户确认后才能 promote。

安全边界（Security）:

- 不保存 cookie、token、localStorage、headers、body、响应体。
- 不把完整截图复制进知识库；只保存 report/artifact 引用。
- 长文本和 evaluate 返回值继续使用截断和 artifact 引用策略。
- 分享 workflow 时不得包含本机绝对业务路径，除非用户显式要求。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | 新增 `ev_export_workflow.py`、`ev_assets.py`，同步调整 `ev_knowledge.py` 到新 schema | 中 | CLI help、JSON 输出、错误路径 | yes |
| 数据结构（Data model） | yes | `ev_knowledge_store.py` 新 schema、`workflow_assets`、`action_assets` | 中 | schema init/rebuild smoke | yes |
| 前端交互（Frontend interaction） | no | 不直接改 Electron GUI 操作语义 | 低 | 复用现有 workflow smoke | yes |
| 配置/环境（Config/environment） | no | 仍使用 `.harness/electron-ui-verifier/` | 低 | init/meta smoke | yes |
| 执行格式（Execution format） | yes | 现有 workflow/action JSON 执行格式必须继续可用 | 中 | 示例 JSON 解析和现有执行脚本 help | yes |
| 测试（Tests） | yes | smoke 脚本、fixtures、真实 report | 中 | py_compile、fixture、VideoForensic report | yes |
| 文档（Documentation） | yes | `SKILL.md`、`knowledge.md`、`actions.md`、示例 | 低 | 链接和命令搜索 | yes |

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：资产 schema 和存储层

目标（Goal）:

- 重新设计知识库 schema，支持 action asset、workflow asset 元数据、导出记录和证据关联。

做法（How）:

- 在 `ev_knowledge_store.py` 中重新设计知识库 schema，直接定义当前所需的 app、screen、element、action asset、workflow asset、evidence、export record 表。
- 不做旧 knowledge DB 数据迁移，不读取旧 `workflows` 表作为兼容来源。
- 新增 `action_assets`、`workflow_assets` 相关 CRUD、FTS 索引、list/search/get/update status。
- 检测到旧 schema 时不自动迁移；首版要求用户显式执行重建/清空命令或使用新的临时 workspace。
- schema 初始化必须幂等；重复运行不得重复创建索引、重复写 meta 或重复插入种子数据。

原因（Why）:

- 先建立稳定持久化边界，避免资产逻辑散落在多个脚本。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/electron-ui-verifier/scripts/ev_knowledge_store.py`
  - `skills/electron-ui-verifier/scripts/ev_knowledge_smoke.py`
  - `skills/electron-ui-verifier/scripts/ev_assets.py`
- API/配置（APIs/configs）:
  - 新增本地函数，不先暴露 server API。
- 测试/文档（Tests/docs）:
- schema 初始化、旧 schema 检测、显式重建、CRUD、search、cleanup smoke。

参考来源（References）:

- 当前 knowledge store 作为重构参考，不作为兼容目标。
- SQLite FTS5 官方文档。

验证（Validation）:

- `python -m py_compile ...`
- 临时 workspace 初始化新 schema。
- 构造旧 schema 数据库，确认默认拒绝隐式迁移并给出清晰错误。
- 显式重建/清空路径 smoke，确认新 schema 可用。
- 插入 action/workflow asset，搜索命中，状态更新，重复插入去重，cleanup 不破坏 `verified/stable` 数据。

风险和回滚（Risks and rollback）:

- 风险：用户误以为旧知识库会保留。缓解：文档和 CLI 错误信息明确“不迁移旧 knowledge DB”，重建必须显式触发。
- 回滚：停止使用新 schema 入口；由于本方案不承诺迁移，回滚不负责恢复旧 runtime 知识数据。

阶段契约（Stage Contract）:

- 范围（Scope）: 只做存储层和 smoke。
- 允许修改（Allowed changes）: store、smoke、必要小工具函数。
- 禁止修改（Forbidden changes）: 不改 server 执行语义，不改 workflow/action JSON 执行格式。
- 进入条件（Entry checks）: 方案批准；工作区安全。
- 退出条件（Exit checks）: schema 和 CRUD smoke 通过。
- 必需验证（Required validation）: py_compile、store smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 2（Stage 2）：report 到 action/workflow 资产整理

目标（Goal）:

- 从 `report.json` 生成清洗后的 action asset 和 workflow asset 候选。

做法（How）:

- 新增 `ev_asset_extract.py`，解析 report steps、status、artifacts、selectedTarget、screen fingerprint。
- 过滤失败步骤、可选 skipped 步骤、敏感字段和不稳定数据。
- 为每个 step 生成 `ActionAsset` 候选，并按连续成功步骤生成 `WorkflowAsset`。
- 保留 raw step id、source report 和 artifactRefs。
- 对 `clickXY`、`evaluate`、`fillText`、本机路径和长文本标记 `riskFlags`，低置信度资产不进入 stable 建议。
- `ev_learn.py` 默认写基础 app/screen/element/evidence 摘要；只有显式 `--include-assets` 才写 action/workflow 资产。

原因（Why）:

- 每次验证天然产生可复用轨迹，应自动整理为资产，而不是只存文本摘要。

位置（Where）:

- 文件/模块（Files/modules）:
  - `scripts/ev_asset_extract.py`
  - `scripts/ev_learn.py`
  - `scripts/ev_knowledge_extract.py`
- API/配置（APIs/configs）:
  - `ev_learn.py` 增加 `--include-assets`；`--dry-run --include-assets` 输出候选资产但不写库。
- 测试/文档（Tests/docs）:
  - mock report fixture、VideoForensic report smoke。

参考来源（References）:

- `ev_server.py` 的 report step record。
- `references/actions.md` 的 action JSON 结构。

验证（Validation）:

- 使用已有 VideoForensic report dry-run，确认 action 数量、workflow 候选和过滤原因。
- 使用真实写入 smoke，查询 action 和 workflow 资产。
- fixture 覆盖失败 step、skipped step、坐标 fallback、evaluate 大结果和路径参数化。

风险和回滚（Risks and rollback）:

- 风险：把偶然 index、路径或大段文本保存为资产。缓解：参数化、截断、敏感过滤。
- 回滚：禁用 `--include-assets` 或只保留 dry-run。

阶段契约（Stage Contract）:

- 范围（Scope）: report 离线整理，不自动影响执行。
- 允许修改（Allowed changes）: 抽取模块、learn CLI、fixture。
- 禁止修改（Forbidden changes）: 不自动提升 stable，不强制写入。
- 进入条件（Entry checks）: Stage 1 通过。
- 退出条件（Exit checks）: dry-run 和真实写入 smoke 通过。
- 必需验证（Required validation）: py_compile、fixture、VideoForensic report smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 3（Stage 3）：查询、建议和组合复用

目标（Goal）:

- 让 agent 能按目标、页面、功能、动作类型搜索 action/workflow，并把 action 组合为 workflow 候选。

做法（How）:

- 新增 `ev_assets.py` 作为资产专用 CLI，支持 `list-actions`、`list-workflows`、`get-action`、`get-workflow`、`search`、`cleanup`。
- `ev_knowledge.py` 同步到新 schema，保留 app/screen/element 查询；workflow 资产查询统一转到 `ev_assets.py`。
- 扩展 `ev_suggest.py`，输出 action suggestions、workflow suggestions 和可组合建议。
- 支持按 `appId`、`screenId`、`kind`、`status`、`goal` 过滤。
- 增加资产清理策略：默认保留 `candidate/verified/stable`；`observed/stale/deprecated` 按数量和时间裁剪，同时删除 FTS 记录。

原因（Why）:

- 后续需求不只是复用完整 workflow，也经常需要复用单步 action 或几步组合。

位置（Where）:

- 文件/模块（Files/modules）:
  - `scripts/ev_assets.py`
  - `scripts/ev_suggest.py`
  - `scripts/ev_knowledge.py`（同步新 schema 的基础查询）
- API/配置（APIs/configs）:
  - CLI JSON 输出，便于 agent 消费。
- 测试/文档（Tests/docs）:
  - action/workflow search smoke。

参考来源（References）:

- 当前 `ev_suggest.py`。
- Playwright locator 稳定性原则。

验证（Validation）:

- 查询 VideoForensic “查看案件”“截图”“采集表格”等 action。
- suggest 输出不得声称已验证，只能标为候选。
- cleanup dry-run 和 apply smoke，确认不会删除 `verified/stable` 资产。

风险和回滚（Risks and rollback）:

- 风险：召回太多噪声。缓解：状态、confidence、screen 和 app 过滤。
- 回滚：保留存储，关闭 suggest 中 action 召回。

阶段契约（Stage Contract）:

- 范围（Scope）: 查询和建议，不执行 UI。
- 允许修改（Allowed changes）: CLI 和 suggest 输出。
- 禁止修改（Forbidden changes）: 不自动运行候选 action。
- 进入条件（Entry checks）: Stage 2 通过。
- 退出条件（Exit checks）: 查询、过滤、建议 smoke 通过。
- 必需验证（Required validation）: py_compile、CLI smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 4（Stage 4）：workflow 导出和分享

目标（Goal）:

- 从知识库 workflow asset 或 report 整理结果导出标准 workflow JSON 文件。

做法（How）:

- 新增 `ev_export_workflow.py`。
- 支持 `--workflow-id`、`--report`、`--goal`、`--output`、`--overwrite`、`--include-metadata`、`--dry-run`。
- 导出前执行清洗和校验，确保输出 JSON 符合 `references/actions.md`。
- 输出路径必须是绝对路径；默认不覆盖已有文件。
- `--dry-run` 输出将要导出的 workflow、参数和风险，不写文件。
- 如果 workflow 含未绑定参数，导出文件保留 `${param}` 占位并在 metadata 中声明。
- `--include-metadata` 只写脱敏来源摘要和 evidence id，不写本机 report/artifact 绝对路径；需要本机路径时必须显式 `--include-local-evidence-paths`。

原因（Why）:

- workflow 分享和跨环境复现需要独立文件，而不是只停留在 SQLite。

位置（Where）:

- 文件/模块（Files/modules）:
  - `scripts/ev_export_workflow.py`
  - `scripts/ev_asset_extract.py`
  - `assets/*.workflow.example.json`
- API/配置（APIs/configs）:
  - CLI 只写用户指定路径。
- 测试/文档（Tests/docs）:
- 导出 JSON parse、示例执行格式检查。
- dry-run 和 overwrite 错误路径检查。

参考来源（References）:

- 当前 `assets/knowledge.workflow.example.json`。
- `references/actions.md`。

验证（Validation）:

- 从 VideoForensic report 导出 workflow 到 `.harness/tasks/.../artifacts/`。
- 解析导出 JSON，检查 `readiness`、`steps`、metadata 和无敏感字段。
- 对已存在输出文件执行无 `--overwrite` 的失败用例。
- 对 `--include-metadata` 和 `--include-local-evidence-paths` 分别执行导出检查，确认默认分享文件不含本机路径。

风险和回滚（Risks and rollback）:

- 风险：导出文件包含本机路径或业务数据。缓解：默认参数化、敏感扫描、metadata 脱敏、显式本机路径开关。
- 回滚：删除导出脚本，不影响知识库。

阶段契约（Stage Contract）:

- 范围（Scope）: 导出 workflow 文件。
- 允许修改（Allowed changes）: 新 CLI、导出工具、示例。
- 禁止修改（Forbidden changes）: 不自动覆盖用户文件，不自动提交导出产物。
- 进入条件（Entry checks）: Stage 3 通过。
- 退出条件（Exit checks）: 导出文件可解析且可被 `ev_workflow.py` 接受。
- 必需验证（Required validation）: py_compile、JSON parse、dry validation。
- 是否预期提交（Commit expected）: yes。

### 阶段 5（Stage 5）：server 显式学习和文档收口

目标（Goal）:

- 将 action/workflow 资产学习融入现有 `--learn` 流程和 skill 文档。

做法（How）:

- `ev_action.py --learn --learn-assets` 和 `ev_workflow.py --learn --learn-assets` 在 server report 学习后同步写入 action/workflow 资产候选。
- `ev_action.py --learn` 和 `ev_workflow.py --learn` 只写基础 app/screen/element/workflow 摘要，不默认写入资产。
- `ev_learn.py --include-assets` 支持显式资产写入，`--dry-run --include-assets` 展示资产候选。
- 更新 `SKILL.md`、`knowledge.md`、`workflow.md`、`actions.md` 和示例。

原因（Why）:

- 用户使用 skill 验证 UI 时，应自然得到可复用资产，而不是额外手工整理。

位置（Where）:

- 文件/模块（Files/modules）:
  - `ev_server.py`
  - `ev_learn.py`
  - 文档和 assets
- API/配置（APIs/configs）:
  - 保持默认不自动学习；只有显式 `--learn` 写基础摘要，显式 `--learn-assets` 或 `ev_learn.py --include-assets` 写资产。
- 测试/文档（Tests/docs）:
  - server function smoke、help、文档检索。

参考来源（References）:

- 当前 Stage 4 知识库集成设计。
- `complex-coding-harness` 长期进程规则。

验证（Validation）:

- 全部 `ev_*.py` py_compile。
- assets JSON parse。
- 如果修改 `ev_server.py` learn hook，必须使用 process-manager 托管 verifier server 做 health smoke；如果 Stage 5 只改 CLI 和文档，可记录不启动 server 的原因。
- VideoForensic report 学习、suggest 和 export smoke。

风险和回滚（Risks and rollback）:

- 风险：server 学习失败影响 UI 验证结果。缓解：学习异常只写 knowledge/assets failed，不覆盖 UI status。
- 回滚：关闭 server 自动资产写入，只保留离线学习。

阶段契约（Stage Contract）:

- 范围（Scope）: 显式学习集成和文档。
- 允许修改（Allowed changes）: server learn hook、learn CLI、docs、examples。
- 禁止修改（Forbidden changes）: 不改变默认不自动学习策略，不让 `--learn` 隐式等同于 `--learn-assets`，不改变 GUI 进程规则。
- 进入条件（Entry checks）: Stage 4 通过。
- 退出条件（Exit checks）: 文档、示例、验证和记录完成。
- 必需验证（Required validation）: py_compile、JSON parse、knowledge/export smoke。
- 是否预期提交（Commit expected）: yes。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- Python：当前可用解释器，用于 finite command、py_compile 和 smoke。
- SQLite：Python 标准库 `sqlite3`，不新增服务。
- process-manager：只有 verifier server smoke 需要长期服务时使用。

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

- pending before implementation

最近同步（Last sync）:

- pending before implementation

分支占用（Branch occupancy）:

- 串行 `git log <main>..HEAD`: implementation 前检查。
- 串行 `git -c diff.autoRefreshIndex=false diff <main>...HEAD --name-only`: implementation 前检查。
- 现有提交属于本任务（Existing commits belong to this task）: 当前已有之前任务提交；本任务实施前需记录。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行：yes。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git：yes。
- 非 Git 文件读取和文本搜索是否可并发：yes，但不得和 Git 混在同一并发批次。

提交策略（Commit policy）:

- 当前只规划，未授权实现提交。
- 如果用户批准实施，每阶段完成 review 和验证后提交。
- 提交使用 `git commit -F <commit-message-file>`，禁止多个 `-m` 拆 bullet。

未解决问题（Open issues）:

- 工作区存在未跟踪 runtime 目录：`.harness/.harness/`、`.harness/electron-feasibility/`、`.tmp/`。这些不属于本任务提交范围。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| Python `sqlite3` | 本地资产库存储 | 1-5 | available | FTS5 可能不可用 | LIKE 降级，仍保留基础 list/get | no |
| `process-manager` | verifier server smoke | 5 | available by repo | manager 离线 | 请求用户启动或授权 | when needed |
| Electron UI verifier | report、workflow、action 验证 | 2-5 | current target | 真实 GUI 不稳定 | 使用已有 report 和 mock | no |
| Git | 阶段提交 | all | serial only | index lock | 精确 lock 恢复流程 | if implementing |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- planning: no
- implementation Stage 5: conditional; 修改 server learn hook 时必须启动 verifier server smoke，否则记录免启动原因

process-manager skill 是否存在（process-manager skill available）:

- yes, repository contains `skills/process-manager`

规则结论（Rule decision）:

- finite command，例如 py_compile、JSON parse、SQLite smoke、report 解析，不进入 process-manager。
- verifier server 是长期后台服务，必须用 process-manager。
- Electron GUI 应用本体不要用 process-manager。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| electron-ui-verifier | verifier server | 5 conditional | `.harness/process-manager/services/electron-ui-verifier.json` | `EV_READY .../health` | pending | pending | pending |

禁止 shell 后台启动确认（No shell background start）:

- yes

历史视图需求（Needs `pm_list --history`）:

- no, unless diagnosing server lifecycle

证据保留位置（Evidence retention location）:

- `.harness/tasks/2026-07-02/feature/electron-ui-verifier-action-workflow-assets/artifacts/`
- `execution-plan.md`

日志沉淀确认（Log evidence persisted）:

- pending until implementation

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前必须复查本节。
- 启动、验证、调试 verifier server 前必须复查本节。
- 上下文压缩或中断恢复后必须复查本节和 `Resume Summary`。

## 验证（Validation）

必需验证（Required）:

- `python -m py_compile skills/electron-ui-verifier/scripts/ev_*.py`
- assets JSON parse。
- schema init/rebuild/action/workflow asset smoke，包含旧 schema 拒绝隐式迁移、显式重建、幂等初始化和去重。
- report -> action/workflow asset `--dry-run --include-assets` 和真实写入 smoke。
- export workflow JSON parse、格式检查、overwrite guard 和默认无本机路径检查。
- VideoForensic report 查询、suggest、export smoke，suggest 不得把候选资产描述成已验证结论。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | py_compile + schema/store smoke + CLI smoke | pass | 资产 schema、旧库拒绝隐式迁移、显式重建、幂等初始化、去重、CRUD 和 `ev_assets.py` 基础查询 | 真实 UI | `python -m py_compile ...`; `ev_knowledge_smoke.py --temp`; `ev_assets.py reset/list-actions`; `ev_knowledge.py meta` | pass |
| Stage 2 | report asset extraction smoke + learn CLI write smoke | pass | raw trace 清洗、失败/evaluate 过滤、riskFlags、参数化、候选资产和显式 `--include-assets` 写入 | 真实 GUI 复跑 | `ev_asset_extract_smoke.py`; `ev_asset_extract.py --report ...`; `ev_learn.py --include-assets`; `ev_assets.py list-actions/list-workflows`; full `ev_*.py` py_compile | pass |
| Stage 3 | query/suggest smoke | pending | `ev_assets.py` 检索、cleanup 和组合建议 | 真实点击 | pending | pending |
| Stage 4 | export JSON parse + dry-run + overwrite guard | pending | workflow 导出、参数占位、默认无本机路径和分享格式 | 跨环境执行 | pending | pending |
| Stage 5 | py_compile + docs + conditional server health | pending | `--learn-assets` 集成和文档收口 | 跨应用泛化 | pending | pending |

可选验证（Optional）:

- 使用真实 VideoForensic GUI 复跑导出的 workflow。
- 使用 mock report 覆盖失败、skipped、坐标 fallback、evaluate 大结果。
- 如果 Stage 5 修改 `ev_server.py` learn hook，使用真实 verifier server health smoke 验证 `--learn-assets`；该长期服务必须通过 process-manager 启动。

产物（Artifacts）:

- 导出的 workflow JSON 示例。
- asset extraction dry-run JSON。
- validation 摘要。

未覆盖（Not covered）:

- 跨应用泛化质量。
- 视觉/OCR 驱动探索。
- Windows 原生对话框、托盘、UAC。

无法执行时（If unable to run）:

- 记录命令、失败原因、影响和替代证据；不得声称真实 UI 验证通过。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/knowledge.md`
- `skills/electron-ui-verifier/references/actions.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/troubleshooting.md`（如新增故障模式）
- `skills/electron-ui-verifier/assets/*.workflow.example.json`

Changelog 计划（Changelog plan）:

- 当前仓库存在 `CHANGELOG.md`；实施阶段每阶段更新。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `ev_knowledge_store.py` | yes | schema、CRUD、search 函数组 | py_compile + smoke |
| `ev_asset_extract.py` | yes | 解析、清洗、参数化、输出组 | py_compile + fixture |
| `ev_assets.py` | no/unknown | 资产 CLI 命令组 | py_compile + CLI smoke |
| `ev_export_workflow.py` | no/unknown | 完整 CLI 语义段 | py_compile + JSON parse |
| `ev_learn.py`/`ev_suggest.py` | no | 局部参数和输出 | py_compile + smoke |
| `ev_server.py` | yes | learn hook 局部函数 | py_compile + server smoke |
| `references/*.md` | yes | 二级章节 | 完整读取和链接检索 |
| `assets/*.json` | no | 完整 JSON 对象 | JSON parse |

写入规则（Write rules）:

- 分段 patch 是落盘策略，不要求一次性生成全部细节。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 大文件优先局部 patch；`ev_server.py` 和 `ev_knowledge_store.py` 禁止整文件重写。
- 写完后重新读取完整目标文件，检查命名、接口、引用和执行格式一致性。

整体复查（Whole-file review）:

- 写完后重新读取完整目标文件：required。
- 需要检查的整体一致性：schema version、状态流转、敏感字段过滤、workflow/action 执行格式、process-manager 规则。
- 对应验证命令或方式：py_compile、JSON parse、smoke、文档检索。

patch 失败处理（Patch failure handling）:

- 读取目标文件确认是否有部分写入。
- 缩小 patch 到语义完整的小段。
- 不用 shell 拼接绕过 apply_patch。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | defaulted | 是否默认自动保存每次验证为资产 | 不默认写资产；只在显式 `--learn-assets` 或 `ev_learn.py --include-assets` 时写入；执行报告始终保留 raw trace | Stage 2/5 |
| D-002 | no | defaulted | 导出 workflow 是否默认覆盖已有文件 | 默认拒绝覆盖，显式 `--overwrite` 才覆盖 | Stage 4 |
| D-003 | no | defaulted | 是否引入外部检索或向量库 | 不引入；首版使用 SQLite/FTS5 和 JSON | all |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pass | Context evidence table |
| 影响面矩阵完整（Impact matrix complete） | pass | Impact Matrix |
| 候选方案比较充分（Options compared enough） | pass | Options A/B/C |
| 每阶段可独立验证（Stages independently verifiable） | pass | Stage 1-5 validation |
| 方案变更触发条件清楚（Reapproval triggers clear） | pass | Decision section |
| 用户批准摘要可记录（Approval summary ready） | pass | Plan Approval section |

质量结论（Quality result）:

- `pass`

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- `pass`

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 原始 steps 直接导出会保留偶然值和失败步骤 | 改为 raw trace -> asset 清洗 -> export 三层架构 | pass |
| 优化（Optimizations） | 独立外部检索服务过重 | 首版继续 SQLite/FTS5，本地自包含 | pass |
| 缺失项（Missing items） | 初稿未明确导出覆盖策略 | 增加绝对路径和默认不覆盖规则 | pass |
| 风险（Risks） | action/workflow 资产可能保存敏感文本或本机路径 | 增加参数化、截断和安全边界 | pass |
| 一致性（Consistency） | 自动学习可能和现有默认不写知识库规则冲突 | 明确普通 `--learn` 只写基础摘要，资产必须显式 `--learn-assets` 或 `--include-assets` | pass |
| 缺陷（Defects） | 初稿对旧 `workflows` 表扩展或新表选择不够确定 | 明确新增 `workflow_assets`，不读取旧 `workflows` 作为兼容来源 | pass |
| 缺失项（Missing items） | schema 迁移路线与用户“重新设计、不考虑兼容”的要求冲突 | 改为新 schema 直接重建，旧库默认拒绝隐式迁移，重建必须显式触发 | pass |
| 优化（Optimizations） | 导出流程缺少 dry-run、参数占位和 overwrite 错误路径 | 增加 `--dry-run`、`${param}`、`requiredParams` 和 overwrite guard | pass |
| 缺陷（Defects） | action 资产表名、workflow 导出引用字段和资产 CLI 入口存在命名分叉 | 统一为 `action_assets`、`workflow_assets`、`workflowAssetId` 和 `ev_assets.py` | pass |
| 缺失项（Missing items） | 每次学习 action/workflow 可能导致重复资产和知识库膨胀 | 增加去重键、confidence/lastSeenAt 更新和 cleanup dry-run/apply 规则 | pass |
| 风险（Risks） | 导出 metadata 可能泄漏本机 report/artifact 绝对路径 | 默认只写脱敏 evidence 摘要，需显式 `--include-local-evidence-paths` 才写本机路径 | pass |
| 一致性（Consistency） | `--learn` 与资产学习边界不够清楚 | 保持 `--learn` 旧行为，新增显式 `--learn-assets` 或 `--include-assets` 写资产 | pass |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：yes, completed.
- `Plan Self-Review` 是否需要重跑：yes, completed.
- `Readiness Gate` 是否需要重跑：yes, completed.
- 原因：本次复查把知识库路线从兼容迁移改为重新设计和显式重建，并细化导出校验和验证证据，但未改变目标和阶段。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pass | Problem |
| 上下文已收集（Context collected） | pass | Context |
| 候选方案已比较（Options compared） | pass | Options |
| 决策已记录（Decision recorded） | pass | Decision |
| 实施阶段已细化（Implementation stages detailed） | pass | Implementation Plan |
| 环境已确认（Environment confirmed） | pass | Environment |
| Git 上下文已确认（Git context confirmed） | pass | Git Context |
| 工具已确认（Tooling confirmed） | pass | Tooling |
| 验证已确认（Validation confirmed） | pass | Validation |
| 最终交付证据已规划（Final delivery evidence planned） | pass | Validation + Documentation |
| 文档更新已确认（Documentation updates confirmed） | pass | Documentation |
| 风险已识别（Risks identified） | pass | Risks/rollback |
| 规划自查已通过（Plan self-review passed） | pass | Plan Self-Review |
| 阻塞问题已关闭（Blocking questions closed） | pass | Questions |

就绪结论（Readiness result）:

- `ready_for_user_approval`

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 用户已批准全部待批准事项：实施范围、阶段提交、工具/MCP 使用和文档更新。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: Stage 1-5 全部实施。
- 阶段提交授权（Stage commit authorization）: 每阶段 review 和验证通过后自动提交。
- 工具/MCP 授权（Tool/MCP authorization）: Python、SQLite、Git、必要时 process-manager server health smoke。
- 文档更新授权（Documentation authorization）: 更新 `SKILL.md`、references、assets 示例和 `CHANGELOG.md`。

提交策略（Commit policy）:

- `stage_commits_authorized`

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- in_progress

当前阶段（Current stage）:

- Stage 2

已完成阶段（Completed stages）:

- Plan drafting
- Plan Quality Gate
- Plan Self-Review
- Readiness Gate
- Plan Approval

剩余阶段（Remaining stages）:

- Stage 2：report 到 action/workflow 资产整理
- Stage 3：查询、建议和组合复用
- Stage 4：workflow 导出和分享
- Stage 5：server 显式学习和文档收口

下一步自动动作（Next automatic action）:

- implement Stage 2 report asset extraction

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no, after approval and run-to-completion

active-task 同步字段（active-task sync fields）:

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "in_progress",
  "current_stage": "Stage 2",
  "remaining_stages": [
    "Stage 2",
    "Stage 3",
    "Stage 4",
    "Stage 5"
  ],
  "next_automatic_action": "implement Stage 2 report asset extraction",
  "stop_condition": "none",
  "state_source": "execution-plan.md"
}
```

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | complete | 完成 action/workflow 资产化方案并获得用户批准 | Plan gates pass | this file | start Stage 1 |
| Stage 1 | complete | 资产 schema 和存储层 | pass | py_compile、schema/store smoke、CLI smoke | committed `09d5ac2` |
| Stage 2 | complete | report 资产整理和显式学习写入 | pass | asset extract smoke、learn write smoke、full py_compile | commit Stage 2 |
| Stage 3 | pending | 查询、建议和组合复用 | pending | pending | wait Stage 2 |
| Stage 4 | pending | workflow 导出 | pending | pending | wait Stage 3 |
| Stage 5 | pending | server learn 集成和文档 | pending | pending | wait Stage 4 |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | pass | none | Python/SQLite available | not-applicable | pass | pass |
| Stage 2 | pass | none | Python/SQLite available | not-applicable | pass | pass |
| Stage 3 | pending | pending | pending | not-applicable | pending | pending |
| Stage 4 | pending | pending | pending | not-applicable | pending | pending |
| Stage 5 | pending | pending | pending | required if server smoke | pending | pending |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | pass | pass | pass | n/a | n/a | pass | `09d5ac2` | pass |
| Stage 2 | pass | pass | pass | n/a | n/a | pass | pending commit | pass |
| Stage 3 | pending | pending | pending | n/a | n/a | pending | pending | pending |
| Stage 4 | pending | pending | pending | n/a | n/a | pending | pending | pending |
| Stage 5 | pending | pending | pending | pending | pending | pending | pending | pending |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证已完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | pass | pass | pass | not-authorized | yes | yes, awaiting user approval | no | pass | pass | yes, approval stop condition | wait approval |
| Stage 1 | pass | pass | pass | `09d5ac2` | yes | no | no | pass | pass | no | continue Stage 2 |
| Stage 2 | pass | pass | pass | pending commit | yes | no | no | pass | pending | no | commit Stage 2 then continue Stage 3 |

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Planning | 暂未进入代码修改 | follow-up | 实施阶段逐阶段 review |
| Stage 1 | 存储层按新 schema 重建设计，不迁移旧 runtime DB；已验证旧 schema 默认拒绝 | none | 符合用户补充约束 |
| Stage 1 | `ev_knowledge.py` 不再暴露 workflow 资产入口，资产查询转到 `ev_assets.py` | none | 与规划中 CLI 边界一致 |
| Stage 2 | 原始 report 不保存完整 action payload，抽取器不能伪造不可复原 evaluate 表达式 | none | 仅对可安全反推的 step 生成 action asset，evaluate 和 failed step 进入 filteredSteps |
| Stage 2 | 普通 `ev_learn.py --learn` 不应绕过显式资产开关写入 workflow 资产 | none | 默认 learn 只写 app/screen/element/evidence，`--include-assets` 才写 action/workflow 资产 |

## 恢复摘要（Resume Summary）

- 整体目标（Overall goal）: 为 `electron-ui-verifier` 增加 action/workflow 资产化、检索、导出和分享能力。
- 执行模式（Execution mode）: run-to-completion.
- 整体任务状态（Overall status）: in_progress.
- 已完成阶段（Completed stages）: planning, quality gate, self-review, readiness gate, approval, Stage 1 implementation/review/validation/commit, Stage 2 implementation/review/validation.
- 当前阶段（Current stage）: Stage 2 commit.
- 剩余阶段（Remaining stages）: Stage 2-5.
- 最新 commit（Latest commit）: `09d5ac2`.
- 下一步自动动作（Next automatic action）: commit Stage 2 and continue Stage 3.
- 当前停止条件（Current stop condition）: none.
- 状态来源（State source of truth）: execution-plan.md.
- 长期进程规则（Process manager rule）: verifier server 必须用 process-manager；Electron GUI 本体不用 process-manager；finite command 不用。
- 未覆盖/风险（Not covered/risks）: 真实跨环境分享效果、跨应用泛化和真实 GUI 复跑不在规划阶段验证。
- 复查后硬约束（Reviewed constraints）:
  - action/workflow 资产表统一为 `action_assets` 和 `workflow_assets`，查询入口统一为 `ev_assets.py`。
  - 知识库数据不做兼容迁移；检测到旧 schema 时默认拒绝隐式迁移，重建/清空必须显式触发。
  - 资产学习必须显式使用 `--learn-assets` 或 `ev_learn.py --include-assets`，普通 `--learn` 只写基础摘要，不隐式写资产。
  - 导出 workflow 默认不写本机 report/artifact 绝对路径；需要时必须显式 `--include-local-evidence-paths`。
  - Stage 2 已覆盖 report 到 action/workflow 资产的 dry-run、真实写入、riskFlags 和过滤逻辑；Stage 3 必须覆盖检索、建议和 cleanup。
- 不得停止说明（Do not stop note）:
  - 用户批准后进入 run-to-completion；阶段边界不是停止条件。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/2026-07-02/feature/electron-ui-verifier-action-workflow-assets/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | not committed | planning only | not applicable |
| Stage 1 | dev-skills | `09d5ac2` | `feat(electron-ui-verifier): 重建知识库资产 schema` | pending changelog hash update |

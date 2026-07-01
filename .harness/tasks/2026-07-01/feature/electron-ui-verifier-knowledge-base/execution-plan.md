# 执行计划：Electron UI Verifier 应用知识库增强

## 问题定义（Problem）

目标（Goal）:

- 为 `skills/electron-ui-verifier` 增加“应用 UI 知识库 / App UI Knowledge Base”能力，让未见过或不熟悉的 Electron 应用在多次验证后沉淀可复用的软件画像、页面画像、元素定位、业务流程和证据摘要。
- 在后续相似任务中优先命中已验证知识，减少重复探索、重复写一次性 action、重复猜入口的成本，同时保留证据、版本、置信度和过期策略，避免错误记忆污染验证结果。

非目标（Non-goals）:

- 本阶段不改造为视觉模型或 OCR 驱动的全自动探索系统。
- 不新增云端服务、外部向量数据库或必须联网的依赖。
- 不保存 cookie、token、localStorage、请求头、请求体、响应体或敏感大段业务文本。
- 不改变 Electron GUI 应用本体的启动规则：GUI 应用仍不使用 `process-manager`。

验收标准（Acceptance）:

- 有明确的知识数据模型、状态流转、存储位置、清理策略和安全边界。
- 有脚本入口规划，用于学习、查询、建议、提升、清理和导出知识。
- 有 server/action/workflow/report 的集成方案，说明哪些地方写入知识、哪些地方只读取知识。
- 有可分阶段实现和独立验证的任务拆分。
- 有面向 VideoForensic 的验证案例，证明一次 UI 任务产物可以沉淀并再次命中知识。

约束（Constraints）:

- 必须使用 `complex-coding-harness` 托管本任务；实现前必须等待用户明确批准。
- 所有 Git 命令串行执行，不放进并发工具。
- 长内容落盘必须分段 patch；大文件不整文件重写。
- verifier server 是长期后台进程，验证时如需启动必须由 `process-manager` 托管。
- Electron GUI 应用本体是特殊 GUI 进程，不使用 `process-manager`。

待确认项（Open uncertainties）:

- 无阻塞项。默认先使用 JSON + SQLite FTS5 的本地文件知识库；向量检索作为后续可选增强，不进入本次必需范围。

## 上下文（Context）

本地代码（Local code）:

- `skills/electron-ui-verifier/SKILL.md`：当前强制使用常驻 verifier server 和 `ev_*` 小脚本，不恢复旧一次性 runner。
- `skills/electron-ui-verifier/scripts/ev_server.py`：当前 server 维护 session、执行 action/workflow、生成 report 和 artifact，是最合适的知识抽取挂点。
- `skills/electron-ui-verifier/scripts/ev_common.py`：当前客户端公共配置、HTTP 调用、路径处理逻辑应复用。
- `skills/electron-ui-verifier/scripts/ev_action.py`、`ev_workflow.py`、`ev_snapshot.py`、`ev_report.py`：当前外部操作入口，可新增知识相关入口但不破坏已有入口。

本地文档（Local docs）:

- `skills/electron-ui-verifier/references/server.md`：定义 server 生命周期、process-manager 托管、session 复用。
- `skills/electron-ui-verifier/references/workflow.md`：定义 Electron GUI 启动、target/session、证据规则。
- `skills/electron-ui-verifier/references/actions.md`：定义 workflow/action JSON、诊断采集、报告字段。
- `.harness/environment.md`：当前主分支为 `main`，任务类型 feature 使用 `harness/feature`。

外部来源（External sources）:

- Playwright Locators 官方文档：定位应优先面向语义、角色、文本和稳定 selector，而不是脆弱坐标。
- Playwright Page Object Model 官方文档：可复用 UI 流程适合抽象为页面/流程对象；本方案不直接引入 POM 代码，但借鉴“将可复用交互知识沉淀为对象”的思想。
- Electron 官方命令行开关文档：打包 Electron 可使用 Chromium/Electron command line switches，例如远程调试端口。
- Chrome DevTools Protocol DOMSnapshot / Accessibility / Runtime / Network：当前 skill 已通过 raw CDP 采集 DOM、AX、异常、网络和 evaluate 结果，知识抽取应复用这些证据。
- SQLite FTS5 官方文档：本地全文检索适合快速检索 screen、element、workflow、report 摘要；不需要引入后台数据库服务。

用户约束（User constraints）:

- 目标是让 skill 越用越好用：每次任务都学习软件布局、功能入口、用法和可复用流程。
- 知识会越来越大，需要缓存、管理、命中快速响应和清理策略。
- 当前只要求制定详细修改方案，按 harness 管理；实现前需要用户确认。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 当前 skill 是 server-only 架构 | read | `SKILL.md`、`server.md`、脚本列表 | 知识库应接入 server 和 `ev_*` 入口 |
| Workflow/action 已能产出 report、snapshot、console、network、AX、DOMSnapshot | read | `actions.md`、`workflow.md` | 知识学习不需要重新发明 UI 采集层 |
| 语义定位比坐标更稳定 | external | Playwright Locators | 元素知识必须保存多候选定位和置信度 |
| 本地 FTS 适合快速知识命中 | external | SQLite FTS5 | 首版可用 SQLite FTS5，避免引入服务依赖 |

## 候选方案（Options）

### 方案 A：只保存 workflow/action 模板

- 做法（How）:
  - 把成功任务中的 action/workflow JSON 复制到 `assets/` 或 `.harness` 模板目录。
  - 后续类似任务人工搜索模板后复用。
- 优点（Pros）:
  - 实现最少，风险低。
  - 不需要新增持久化模型。
- 缺点（Cons）:
  - 只能复用“脚本”，不能理解页面、元素、入口、版本和置信度。
  - 模板增多后检索困难，无法自动判断过期。
  - 对新应用的“越用越好用”帮助有限。
- 风险（Risks）:
  - 容易把一次性坐标、偶然文本、临时数据沉淀成长期模板。
- 验证（Validation）:
  - 只能验证模板文件存在和 JSON 可解析，无法验证命中质量。
- 回滚（Rollback）:
  - 删除模板即可。

### 方案 B：结构化本地知识库（推荐）

- 做法（How）:
  - 新增本地知识库目录 `.harness/electron-ui-verifier/knowledge/`，保存 `manifest.json`、`knowledge.sqlite` 和小型摘要文件。
  - 新增 `AppProfile`、`ScreenProfile`、`ElementDescriptor`、`WorkflowRecipe`、`KnowledgeEvidence` 等结构。
  - 从 report/artifact 中提取页面文本、DOM/AX 特征、元素候选、工具栏、表格、流程步骤和断言，形成 `observed -> candidate -> verified -> stable` 的知识状态。
  - 新增 `ev_learn.py`、`ev_knowledge.py`、`ev_suggest.py`、`ev_promote.py`、`ev_discover.py` 等入口。
- 优点（Pros）:
  - 能支撑快速命中、版本识别、页面指纹、置信度、证据追溯和过期清理。
  - 不引入外部服务，适合 skill 自包含分发。
  - 可以从当前 server 报告自然学习，不破坏已有 workflow。
- 缺点（Cons）:
  - 实现复杂度高于模板复制。
  - 需要谨慎设计数据模型和清理规则，避免知识膨胀。
- 风险（Risks）:
  - 如果过度自动提升知识状态，可能把错误结论变成稳定知识。
  - SQLite schema 需要兼容升级策略。
- 验证（Validation）:
  - 单元测试覆盖知识写入、查询、状态流转、清理和敏感字段过滤。
  - 使用 VideoForensic 现有 report/artifact 做学习和二次命中 smoke。
- 回滚（Rollback）:
  - 删除新增脚本和知识模块；`.harness/electron-ui-verifier/knowledge/` 是 ignored runtime，可直接清理。

### 方案 C：引入向量检索或外部知识服务

- 做法（How）:
  - 把 screen、element、workflow 摘要写入向量库或外部服务，使用语义检索召回。
- 优点（Pros）:
  - 对自然语言目标召回更强。
  - 后期可跨应用做相似功能迁移。
- 缺点（Cons）:
  - 增加依赖、配置、隐私和部署复杂度。
  - 当前 skill 目标是本地、可审计、易复用，外部服务过重。
- 风险（Risks）:
  - 敏感 UI 文本外发或落入不可控服务。
  - 用户环境差异导致不可用。
- 验证（Validation）:
  - 需要额外服务可用性和隐私验证。
- 回滚（Rollback）:
  - 关闭外部索引入口，但迁移成本较高。

## 决策（Decision）

选择方案（Chosen option）:

- 选择方案 B：结构化本地知识库。

原因（Why）:

- 它最贴合“越用越好用”的目标，同时保持本地、离线、可审计和可清理。
- 当前 skill 已有 report/artifact/action/workflow 证据链，方案 B 可以复用现有产物，避免重写 UI 执行层。
- SQLite FTS5 可作为快速命中的首版检索，不需要引入服务型依赖。

影响（Impact）:

- 新增知识模型、存储模块和多个 `ev_*` 入口。
- `ev_server.py` 需要新增可选的知识读写 API 或内部服务函数，但不改变现有 action/workflow 请求兼容性。
- 文档需要增加知识库工作流、隐私边界、清理和 VideoForensic 示例。

可逆性（Reversibility）:

- 中等。新增代码相对独立；不修改现有 action/workflow 语义即可回滚。
- 运行时知识目录位于 `.harness/electron-ui-verifier/knowledge/`，默认忽略，不影响 Git 历史。

变更条件（Change conditions）:

- 如果实现中发现 Python 标准库 sqlite3 不包含 FTS5，则降级为普通 LIKE 查询和 JSON manifest 索引，并记录限制。
- 如果 server 改动过大影响稳定性，则先实现离线 `ev_learn.py` 和 `ev_knowledge.py`，server 自动学习延后。

方案变更触发条件（Reapproval triggers）:

- 需要新增第三方 Python 依赖、外部服务、云端存储或向量库。
- 需要保存敏感字段、截图长期入库、localStorage/cookie/token 或网络 headers/body。
- 需要改变现有 action/workflow JSON 的兼容语义。
- 需要让 Electron GUI 应用本体改用 `process-manager`。
- 必需验证无法执行，且没有足够替代证据。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | `ev_server.py` 内部知识接口；新增 `ev_knowledge.py` 等 CLI | 中 | server smoke、CLI help、mock report 学习 | `references/knowledge.md` |
| 数据结构（Data model） | yes | 新增知识 schema、SQLite 表、manifest | 中 | 单元测试、迁移/初始化测试 | schema 文档 |
| 前端交互（Frontend interaction） | yes | 不直接改 GUI，但影响 workflow 建议和元素定位 | 中 | VideoForensic 二次命中验证 | workflow 文档 |
| 配置/环境（Config/environment） | yes | `.harness/electron-ui-verifier/knowledge/` runtime | 低 | init/doctor 检查 | server 文档 |
| 兼容性（Compatibility） | yes | 保持现有 action/workflow 兼容 | 中 | 旧示例 workflow 回归 | troubleshooting |
| 测试（Tests） | yes | 新增知识模块测试和脚本 smoke | 中 | py_compile、unittest、mock CDP/report | 测试说明 |
| 文档（Documentation） | yes | SKILL、references、assets 示例 | 低 | 文档检索、JSON 示例解析 | 必需 |

## 知识模型设计（Knowledge Model）

存储位置（Storage）:

- 运行时知识库：`.harness/electron-ui-verifier/knowledge/`
- 热启动摘要：`.harness/electron-ui-verifier/knowledge/manifest.json`
- 主索引：`.harness/electron-ui-verifier/knowledge/knowledge.sqlite`
- 大型证据不长期入库，保留在 report/artifact，知识库只存引用、摘要和指纹。

核心实体（Entities）:

| 实体 | 作用 | 关键字段 |
| --- | --- | --- |
| `AppProfile` | 识别一个 Electron 应用 | `appId`、`displayName`、`exePathHash`、`productName`、`version`、`firstSeenAt`、`lastSeenAt` |
| `ScreenProfile` | 识别一个页面或路由 | `screenId`、`appId`、`route`、`title`、`fingerprint`、`summary`、`keyTexts`、`status` |
| `ElementDescriptor` | 描述可复用 UI 元素 | `elementId`、`screenId`、`name`、`role`、`text`、`selectorCandidates`、`anchors`、`confidence` |
| `WorkflowRecipe` | 描述可复用任务流程 | `workflowId`、`appId`、`goal`、`preconditions`、`steps`、`assertions`、`status` |
| `KnowledgeEvidence` | 追溯知识来源 | `evidenceId`、`sourceReport`、`artifactRefs`、`createdAt`、`notes` |

状态流转（Status flow）:

- `observed`：从一次 report/artifact 中观察到，未验证可复用。
- `candidate`：经过去重和结构化，可能可复用。
- `verified`：至少一次通过 workflow/action 复验。
- `stable`：多次或用户确认后可作为默认建议。
- `stale`：版本、页面指纹或断言变化后需要复验。
- `deprecated`：已确认不再使用，默认不召回。

指纹策略（Fingerprint）:

- 应用指纹：优先使用 exe 绝对路径归一化 hash、product/version、CDP browser/version、target URL/title。
- 页面指纹：URL route、title、关键文本集合、主要按钮/菜单文本、DOM/AX 结构摘要。
- 元素指纹：角色、可见文本、稳定 selector、邻近锚点、表格列名、相对区域。

安全边界（Security）:

- 默认只保存短摘要、结构化标签、路径 hash 和 artifact 相对引用。
- 不保存 cookie、token、localStorage、请求头、请求体、响应体。
- 默认不把截图复制进长期知识库；如果需要引用截图，只保存 report artifact 路径和截图摘要。
- 对长文本做截断和敏感词过滤；原始长文本仍保留在本次 report artifact，不自动提升为长期知识。

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：知识存储和数据模型

目标（Goal）:

- 建立本地知识库基础模块，支持初始化、schema 创建、manifest 读写、基础 CRUD、FTS 查询和清理策略。

做法（How）:

- 新增 `scripts/ev_knowledge_store.py` 或等价内部模块，集中处理路径、安全写入、SQLite 连接、schema 初始化和 JSON manifest。
- 知识库路径固定在 `.harness/electron-ui-verifier/knowledge/`，不提交运行数据。
- 首版使用 Python 标准库 `sqlite3`；探测 FTS5 可用性，不可用时降级普通查询。

原因（Why）:

- 先把持久化边界做稳，避免后续学习和建议功能把状态分散到多个脚本。
- 运行时知识目录已经在 `.gitignore` 覆盖的 `.harness/electron-ui-verifier/` 下，符合不提交本机数据的规则。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/electron-ui-verifier/scripts/ev_knowledge_store.py`
  - `skills/electron-ui-verifier/scripts/ev_common.py`
- API/配置（APIs/configs）:
  - 新增本地函数，不先暴露 server HTTP API。
- 测试/文档（Tests/docs）:
  - 新增或补充轻量 Python unittest。

参考来源（References）:

- SQLite FTS5 官方文档。
- 当前 `ev_common.py` 的路径和 server config 读取方式。

验证（Validation）:

- `python -m py_compile skills/electron-ui-verifier/scripts/ev_knowledge_store.py`
- 初始化临时 workspace，创建 schema，插入 app/screen/workflow，查询命中，清理 inactive 数据。

风险和回滚（Risks and rollback）:

- 风险：schema 过早固化。缓解：加 `schema_version` 和迁移入口，只做 v1 必需字段。
- 回滚：删除新增模块和调用点，runtime knowledge 目录可清理。

阶段契约（Stage Contract）:

- 范围（Scope）: 只做知识存储层。
- 允许修改（Allowed changes）: 新增内部模块、少量公共工具函数、测试。
- 禁止修改（Forbidden changes）: 不改 action/workflow 行为，不改 server 生命周期。
- 进入条件（Entry checks）: 用户批准方案；工作区安全；分支为 `harness/feature`。
- 退出条件（Exit checks）: 存储层测试通过；无敏感字段默认持久化。
- 必需验证（Required validation）: py_compile、unittest 或等价脚本 smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 2（Stage 2）：学习入口和知识抽取

目标（Goal）:

- 从现有 report/artifact 中抽取应用、页面、元素、工具栏、表格和流程知识，生成 `observed/candidate` 知识记录。

做法（How）:

- 新增 `ev_learn.py`：接收 `--report`、`--session`、`--app-id`、`--notes`、`--dry-run`。
- 解析 `report.json`、snapshot、DOMSnapshot、AX、namedResults 和 workflow step，抽取可复用结构。
- 对坐标点击只保存为兜底候选，不作为高置信稳定定位。
- 把一次成功 workflow 的步骤和断言转成 `WorkflowRecipe candidate`。

原因（Why）:

- 当前验证已经会生成大量证据；学习入口应复用这些证据，而不是重新操作 UI。
- 离线学习便于复查和回放，也降低 server 实时写知识的风险。

位置（Where）:

- 文件/模块（Files/modules）:
  - `scripts/ev_learn.py`
  - `scripts/ev_knowledge_store.py`
  - 可能新增 `scripts/ev_knowledge_extract.py`
- API/配置（APIs/configs）:
  - CLI 输入必须使用绝对 report 路径或由 `--latest --session` 解析。
- 测试/文档（Tests/docs）:
  - 使用 mock report fixture 验证抽取。

参考来源（References）:

- 当前 `ev_report.py`、`ev_artifact.py` 的 artifact 访问约束。
- Playwright Locator 语义定位思想。

验证（Validation）:

- mock report 学习 dry-run 输出。
- 真实 VideoForensic 近期 report 学习，确认能抽取首页、第二案件结果页工具栏和统计项。

风险和回滚（Risks and rollback）:

- 风险：抽取文本过多或误存敏感字段。缓解：默认截断、过滤、只存摘要和 artifact 引用。
- 回滚：保留存储层，移除学习入口调用。

阶段契约（Stage Contract）:

- 范围（Scope）: 离线学习和抽取，不自动影响执行。
- 允许修改（Allowed changes）: 新增 CLI、抽取模块、fixture。
- 禁止修改（Forbidden changes）: 不自动把 candidate 提升 stable。
- 进入条件（Entry checks）: Stage 1 已提交；知识库 schema 可用。
- 退出条件（Exit checks）: mock 和 VideoForensic 学习证据可复查。
- 必需验证（Required validation）: py_compile、fixture 测试、VideoForensic report 学习 smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 3（Stage 3）：查询、建议和提升

目标（Goal）:

- 提供快速检索和复用入口，让 agent 能根据自然语言目标、appId、screen、功能名命中已有知识，并把验证过的知识提升状态。

做法（How）:

- 新增 `ev_knowledge.py`：支持 `list-apps`、`screens`、`elements`、`workflows`、`search`、`cleanup`。
- 新增 `ev_suggest.py`：输入 `--goal`、`--app-id`、`--current-report`，输出候选 workflow、入口、元素定位和置信度。
- 新增 `ev_promote.py`：把 candidate/verified 知识提升到 verified/stable，必须带 evidence 或用户确认标记。

原因（Why）:

- “命中立马响应”需要独立查询入口，而不是让 agent 每次打开 SQLite 或翻 report。
- 提升入口把自动观察和稳定知识分开，防止一次偶然结果污染长期知识。

位置（Where）:

- 文件/模块（Files/modules）:
  - `scripts/ev_knowledge.py`
  - `scripts/ev_suggest.py`
  - `scripts/ev_promote.py`
  - `scripts/ev_knowledge_store.py`
- API/配置（APIs/configs）:
  - 输出 JSON 为主，便于 agent 消费；可选人类摘要。
- 测试/文档（Tests/docs）:
  - 查询、提升和清理命令示例。

参考来源（References）:

- SQLite FTS5 查询能力。
- 当前 `ev_*` 小脚本封装 server/API 的设计理念。

验证（Validation）:

- 在临时知识库中插入多 app、多 screen、多 workflow，验证 search 和 suggest 排序。
- 提升必须要求 evidence，缺少 evidence 时失败。

风险和回滚（Risks and rollback）:

- 风险：suggest 输出被误认为已验证。缓解：输出必须包含 `status`、`confidence`、`evidence`、`notVerifiedWarning`。
- 回滚：查询入口可删除，不影响已存知识。

阶段契约（Stage Contract）:

- 范围（Scope）: 查询、建议、提升和清理。
- 允许修改（Allowed changes）: 新增 CLI 和存储层查询函数。
- 禁止修改（Forbidden changes）: 不让 suggest 自动执行 UI 操作。
- 进入条件（Entry checks）: Stage 2 已提交；知识抽取可产生数据。
- 退出条件（Exit checks）: suggest 能命中 VideoForensic 工具栏/打开案件流程候选。
- 必需验证（Required validation）: py_compile、查询/提升/清理 smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 4（Stage 4）：server/workflow 集成和报告沉淀

目标（Goal）:

- 在不破坏现有 action/workflow 的前提下，让 report 记录知识建议来源和学习建议，并可选择在 workflow 后自动生成 candidate 知识。

做法（How）:

- 在 `ev_server.py` report 生成阶段增加可选 `knowledge` 摘要字段，例如 matched app/screen/workflow、suggestions、learnable facts。
- `ev_workflow.py` 增加可选 `--learn` 或 `--learn-dry-run`，默认不自动写长期知识。
- `ev_doctor.py` 增加知识库状态检查：schema version、FTS 可用性、manifest 大小、最近清理时间。

原因（Why）:

- 知识库要和真实验证闭环关联，但默认不应悄悄写入长期记忆。
- report 中记录 knowledge context 可以提升可审计性。

位置（Where）:

- 文件/模块（Files/modules）:
  - `scripts/ev_server.py`
  - `scripts/ev_workflow.py`
  - `scripts/ev_doctor.py`
  - 知识模块
- API/配置（APIs/configs）:
  - 保持旧 workflow JSON 兼容。
- 测试/文档（Tests/docs）:
  - 更新 workflow 示例和诊断说明。

参考来源（References）:

- 当前 `report.json` schemaVersion 规则。
- 当前 server-only 架构约束。

验证（Validation）:

- 旧 workflow 示例可继续执行。
- `--learn-dry-run` 不写库但报告包含 learnable 摘要。
- `--learn` 写入 candidate 并可被 `ev_knowledge.py search` 命中。

风险和回滚（Risks and rollback）:

- 风险：server 文件较大，patch 容易失败。缓解：只做局部函数和路由小段修改，单次 patch 不超过硬上限。
- 回滚：移除可选参数和 report knowledge 字段，不影响核心 action。

阶段契约（Stage Contract）:

- 范围（Scope）: 可选集成，不改变默认执行结果。
- 允许修改（Allowed changes）: report 附加字段、CLI 可选参数、doctor 检查。
- 禁止修改（Forbidden changes）: 不改变现有必需字段和旧 workflow 语义。
- 进入条件（Entry checks）: Stage 3 已提交；旧功能基线清楚。
- 退出条件（Exit checks）: 旧 workflow 兼容；新 learn 入口可用。
- 必需验证（Required validation）: py_compile、旧示例 JSON 解析、mock server/workflow smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 5（Stage 5）：文档、示例和 VideoForensic 端到端验证

目标（Goal）:

- 把知识库能力写入 skill 使用规则，并用 VideoForensic 的真实报告完成学习、查询、建议和复用验证。

做法（How）:

- 新增 `references/knowledge.md`，说明知识库目录、状态、命令、隐私、清理和推荐流程。
- 更新 `SKILL.md`、`references/server.md`、`references/workflow.md`、`references/actions.md`、`references/troubleshooting.md`。
- 新增示例 `assets/knowledge.workflow.example.json` 或等价示例。
- 使用已有或新采集的 VideoForensic report 学习：首页工具栏、案件列表、打开第二案件、结果页统计和工具栏。
- 再用 `ev_suggest.py` 查询“第二个案件数据统计”或“工具栏功能”，确认可召回候选入口和已知页面。

原因（Why）:

- skill 能力必须可被后续 agent 明确触发和复查，不能只靠代码存在。
- VideoForensic 是当前真实应用样本，能验证学习层对陌生应用逐步熟悉的核心目标。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/electron-ui-verifier/SKILL.md`
  - `skills/electron-ui-verifier/references/knowledge.md`
  - 其他 references
  - `assets/knowledge.workflow.example.json`
- API/配置（APIs/configs）:
  - 不新增必需配置；知识库默认本地 runtime。
- 测试/文档（Tests/docs）:
  - 文档示例 JSON 解析。

参考来源（References）:

- 当前 VideoForensic 实测 report/artifact。
- 本计划中的知识模型和阶段验证记录。

验证（Validation）:

- 文档命令可读且路径规则正确。
- VideoForensic 学习后可通过 knowledge 查询命中工具栏和第二案件结果页统计入口。
- `ev_doctor.py` 能报告知识库健康状态。

风险和回滚（Risks and rollback）:

- 风险：VideoForensic 是本地应用，其他环境无法复现。缓解：把它作为 smoke evidence，不作为通用测试唯一依据。
- 回滚：移除知识文档和示例；核心旧 workflow 不受影响。

阶段契约（Stage Contract）:

- 范围（Scope）: 文档、示例、端到端验证和最终收口。
- 允许修改（Allowed changes）: skill 文档、示例、必要小修。
- 禁止修改（Forbidden changes）: 不提交本地 VideoForensic runtime artifact，除非用户另行批准。
- 进入条件（Entry checks）: Stage 4 已提交；真实 Electron 环境可用或有可替代 mock。
- 退出条件（Exit checks）: 最终验证和 code review 完成，Commit Log 更新。
- 必需验证（Required validation）: py_compile、JSON 示例解析、knowledge smoke、VideoForensic 或替代证据。
- 是否预期提交（Commit expected）: yes。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- Python：使用当前可用 Python；verifier server Python 由 `.harness/electron-ui-verifier/environment.json` 指定。
- Git：主分支 `main`，工作分支 `harness/feature`。
- Electron UI 验证：需要时启动 verifier server，必须由 `process-manager` 托管。
- VideoForensic：仅作为端到端 smoke，Electron GUI 应用本体按 skill 规则正常终端启动或连接用户已启动实例。

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

- 计划阶段未执行合并；实施前按规则检查是否需要合入 `origin/main` 或本地 `main`。

最近同步（Last sync）:

- pending for implementation

分支占用（Branch occupancy）:

- 串行 `git log <main>..HEAD`: 实施前检查。
- 串行 `git -c diff.autoRefreshIndex=false diff <main>...HEAD --name-only`: 实施前检查。
- 现有提交属于本任务（Existing commits belong to this task）: 待实施前确认。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行：yes。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git：yes。
- 非 Git 文件读取和文本搜索是否可并发：yes，但不得和 Git 混在同一并发批次。

提交策略（Commit policy）:

- 只有用户批准方案并授权阶段提交后才提交。
- 每阶段提交使用 `git commit -F <commit-message-file>`，禁止多个 `-m` 拆 bullet。

未解决问题（Open issues）:

- 当前工作区存在 untracked runtime 目录：`.harness/.harness/`、`.harness/electron-feasibility/`、`.tmp/`。这些不是本计划要清理或提交的内容。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| Python `sqlite3` | 本地知识库存储和 FTS | 1-5 | planned | FTS5 可能不可用 | 降级普通查询 | 不阻塞 |
| `process-manager` skill | 托管 verifier server | 4-5 | available by repo | manager 离线 | 停止并请求启动 | 需要时按规则 |
| Electron UI verifier | 真实 UI 验证 | 5 | current target | 本地 GUI 状态不稳定 | 使用已有 report 或 mock | 需要用户允许启动/连接 |
| PowerShell | Windows 命令执行 | all | available | 权限/GUI 提权 | 用户手动启动 GUI | 视情况 |
| Git | 阶段提交 | all | serial only | index lock | 精确 lock 恢复流程 | 已有规则 |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- yes, only when running verifier server for Stage 4/5 smoke.

process-manager skill 是否存在（process-manager skill available）:

- yes, repository contains `skills/process-manager`.

规则结论（Rule decision）:

- verifier server 是长期后台服务，必须用 `process-manager`。
- Electron GUI 应用本体不要用 `process-manager`。
- finite command，例如 py_compile、unittest、JSON 解析、知识库 CLI 查询，不进入 `process-manager`。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| electron-ui-verifier | verifier server | 4-5 | `.harness/process-manager/services/electron-ui-verifier.json` | `EV_READY .../health` | pending | stage artifact 摘要 | pending |

禁止 shell 后台启动确认（No shell background start）:

- verifier server 不手写后台启动；Electron GUI 除外。

历史视图需求（Needs `pm_list --history`）:

- no, 除非排查 server 启停历史。

证据保留位置（Evidence retention location）:

- `.harness/tasks/2026-07-01/feature/electron-ui-verifier-knowledge-base/artifacts/`
- `execution-plan.md` 摘录关键日志和结果。

日志沉淀确认（Log evidence persisted）:

- pending until implementation.

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前必须复查本节。
- 启动、验证、调试 verifier server 前必须复查本节。
- 上下文压缩或中断恢复后必须复查本节和 `Resume Summary`。

## 验证（Validation）

必需验证（Required）:

- Python 语法：`python -m py_compile skills/electron-ui-verifier/scripts/ev_*.py`
- 知识存储单元测试或等价 smoke：schema init、insert、search、promote、cleanup。
- 旧功能兼容：示例 workflow/action JSON 可解析；旧入口 help 可运行。
- server 集成 smoke：verifier server 启动、health、mock 或真实 session action。
- VideoForensic smoke：从真实 report 学习并查询命中工具栏、案件列表或结果页统计。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | `python -m py_compile ...` + `python ev_knowledge_smoke.py --temp --workspace ...` | pass | schema、manifest、CRUD、FTS5/LIKE 查询、cleanup | 真实 UI | `.harness/electron-ui-verifier/tmp/ev-knowledge-20260701-103106/` | completed |
| Stage 2 | learn fixture + VideoForensic report | pending | 抽取和敏感过滤 | 自动提升 | pending | pending |
| Stage 3 | query/suggest/promote smoke | pending | 快速命中和状态流转 | 真实点击 | pending | pending |
| Stage 4 | server/workflow smoke | pending | 兼容和 learn 集成 | 长期压测 | pending | pending |
| Stage 5 | docs + VideoForensic e2e | pending | 使用流程和真实样本 | 跨应用泛化 | pending | pending |

可选验证（Optional）:

- 使用多个不同 Electron 应用 report 检查 appId 隔离。
- 用降级模式模拟 FTS5 不可用。

产物（Artifacts）:

- 知识库 smoke JSON 摘要。
- VideoForensic 学习/查询报告摘要。
- 必要截图或 report 路径；runtime artifact 默认不提交。

未覆盖（Not covered）:

- Windows 原生对话框、UAC、托盘菜单。
- 云端向量检索、多用户共享知识库。

无法执行时（If unable to run）:

- 记录具体命令、失败原因、影响范围和替代证据；不得声称真实 UI 验证通过。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/knowledge.md`
- `skills/electron-ui-verifier/references/server.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/actions.md`
- `skills/electron-ui-verifier/references/troubleshooting.md`
- `skills/electron-ui-verifier/assets/*` 示例，如确实需要。

Changelog 计划（Changelog plan）:

- 当前仓库未确认统一 `CHANGELOG.md`；实施前检查是否存在。如果存在，每阶段更新；如果不存在，在 `execution-plan.md` 的 Commit Log 中记录阶段变更。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `ev_server.py` | yes | 局部函数/路由，不整文件重写 | 读取相关函数和 py_compile |
| 新知识模块 | yes | 完整类/函数组 | py_compile + smoke |
| 新 CLI 脚本 | no/unknown | 单脚本完整语义段 | py_compile + help |
| `references/knowledge.md` | yes | 二级章节 | 完整读取 |
| `SKILL.md` 和现有 references | no | 局部章节 | 完整读取 |
| `assets/*.json` | no | 完整 JSON 对象 | JSON 解析 |

写入规则（Write rules）:

- 分段 patch 是落盘策略，不要求一次性生成全部细节；实现前先按本计划保持全局框架。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 大文件优先局部 patch；`ev_server.py` 禁止整文件重写。
- patch 失败后先读取目标文件确认是否部分写入，再缩小 patch。

整体复查（Whole-file review）:

- 写完后重新读取完整目标文件：required。
- 需要检查的整体一致性：知识状态、隐私边界、旧 workflow 兼容、process-manager 规则、提交策略。
- 对应验证命令或方式：py_compile、JSON 解析、smoke 和文档复查。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | defaulted | 是否首版引入外部向量库 | 不引入；后续可选 | 方案 B |
| D-002 | no | defaulted | 是否默认自动学习到长期知识库 | 不默认；使用 `--learn` 或显式入口 | Stage 2/4 |

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
| 缺陷（Defects） | 初版若把学习自动接入 workflow，可能污染长期知识 | 改为默认不自动写库，需 `--learn` 或显式 `ev_learn.py` | pass |
| 优化（Optimizations） | 直接上向量库过重 | 首版使用 SQLite FTS5，本地自包含 | pass |
| 缺失项（Missing items） | 需要明确 Electron GUI 不用 process-manager | 已写入 Process Manager Gate | pass |
| 风险（Risks） | 敏感字段和错误记忆风险 | 增加过滤、状态流转、evidence 和 promote 规则 | pass |
| 一致性（Consistency） | 旧 workflow 兼容与新增知识字段可能冲突 | 明确只增可选字段和可选参数 | pass |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：no。
- `Plan Self-Review` 是否需要重跑：no，除非用户修改范围。
- `Readiness Gate` 是否需要重跑：no，除非用户修改范围。
- 原因：自查只补强默认行为和风险边界，未改变目标或阶段范围。

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
| 最终交付证据已规划（Final delivery evidence planned） | pass | Stage 5 + Validation |
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

- 用户在 2026-07-01 明确回复“按方案执行”。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: Stage 1-5 全部实施计划。
- 阶段提交授权（Stage commit authorization）: yes, 每阶段完成 review 和验证后提交。
- 工具/MCP 授权（Tool/MCP authorization）: 使用计划内 finite command；需要 verifier server 时按 process-manager 规则。
- 文档更新授权（Documentation authorization）: yes, 更新 electron-ui-verifier skill 文档和示例。

提交策略（Commit policy）:

- `stage_commits_authorized`

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- in_progress

当前阶段（Current stage）:

- Stage 1

已完成阶段（Completed stages）:

- Plan drafting
- Plan Quality Gate
- Plan Self-Review
- Readiness Gate

剩余阶段（Remaining stages）:

- Stage 1：知识存储和数据模型
- Stage 2：学习入口和知识抽取
- Stage 3：查询、建议和提升
- Stage 4：server/workflow 集成和报告沉淀
- Stage 5：文档、示例和 VideoForensic 端到端验证

下一步自动动作（Next automatic action）:

- continue Stage 1

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no, once implementation is approved and execution mode becomes run-to-completion.

active-task 同步字段（active-task sync fields）:

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "in_progress",
  "current_stage": "Stage 1",
  "remaining_stages": [
    "Stage 1",
    "Stage 2",
    "Stage 3",
    "Stage 4",
    "Stage 5"
  ],
  "next_automatic_action": "continue Stage 1",
  "stop_condition": "none",
  "state_source": "execution-plan.md"
}
```

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | complete | 完成知识库增强方案 | Plan gates pass | this file | request approval |
| Stage 1 | complete | 新增知识库存储模块和 smoke 脚本 | py_compile + smoke pass | runtime tmp knowledge db | continue Stage 2 |
| Stage 2 | pending | 学习入口和知识抽取 | pending | pending | wait Stage 1 |
| Stage 3 | pending | 查询、建议和提升 | pending | pending | wait Stage 2 |
| Stage 4 | pending | server/workflow 集成 | pending | pending | wait Stage 3 |
| Stage 5 | pending | 文档和 VideoForensic 验证 | pending | pending | wait Stage 4 |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | pass | pass | pass | not-applicable | pass | pass |
| Stage 2 | pending | pending | pending | not-applicable | pending | pending |
| Stage 3 | pending | pending | pending | not-applicable | pending | pending |
| Stage 4 | pending | pending | pending | required if server smoke | pending | pending |
| Stage 5 | pending | pending | pending | required if verifier server starts | pending | pending |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | pass | pass | pass | n/a | n/a | pass | pending commit | pass |
| Stage 2 | pending | pending | pending | n/a | n/a | pending | pending | pending |
| Stage 3 | pending | pending | pending | n/a | n/a | pending | pending | pending |
| Stage 4 | pending | pending | pending | pending | pending | pending | pending | pending |
| Stage 5 | pending | pending | pending | pending | pending | pending | pending | pending |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证已完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | pass | pass | pass | not-authorized | yes | yes | no | pass | pass | yes | wait approval |
| Stage 1 | pass | pass | pass | pending commit | yes | no | no | pending | pending | no | continue Stage 2 |

结论（Decision）:

- 规划阶段完成；停止条件是等待用户批准。批准后执行模式切换为 `run-to-completion`。

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Planning | 暂未进入代码修改 | follow-up | 实施阶段逐阶段 review |
| Stage 1 | FTS5 MATCH 特殊字符可能导致查询异常 | minor | 已在 `search()` 中捕获 sqlite3 错误并降级 LIKE |

## 恢复摘要（Resume Summary）

- 整体目标（Overall goal）: 为 `electron-ui-verifier` 增加本地应用 UI 知识库，让 Electron 应用验证能学习页面、入口、元素和流程。
- 执行模式（Execution mode）: planning-only until user approval.
- 整体任务状态（Overall status）: in_progress.
- 已完成阶段（Completed stages）: planning, quality gate, self-review, readiness gate, Stage 1.
- 当前阶段（Current stage）: Stage 1 commit.
- 剩余阶段（Remaining stages）: Stage 2-5.
- 最新 commit（Latest commit）: none for this task.
- 下一步自动动作（Next automatic action）: commit Stage 1, then continue Stage 2.
- 当前停止条件（Current stop condition）: none.
- 状态来源（State source of truth）: execution-plan.md.
- 长期进程规则（Process manager rule）: verifier server 必须用 process-manager；Electron GUI 本体不用 process-manager。
- 未覆盖/风险（Not covered/risks）: 向量检索、云端知识库、跨应用大规模泛化不在首版范围。
- 不得停止说明（Do not stop note）:
  - 用户批准后进入 run-to-completion；阶段边界不是停止条件。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/2026-07-01/feature/electron-ui-verifier-knowledge-base/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | not committed | planning only | not applicable |

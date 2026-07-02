# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

- 将 `electron-ui-verifier` 的使用流程强化为强制闭环：先查知识库，再现场验证，再回写知识库。
- 确保后续使用该 skill 做 Electron UI 验证时，不会绕过已有经验，也不会把旧知识当作最终答案。
- 将知识库命中、现场验证证据、回写结果纳入最终回复和 report 可审计信息。

非目标（Non-goals）:

- 本计划阶段不直接修改 skill 源码。
- 不改变 Electron GUI 应用本体不使用 `process-manager` 的规则。
- 不把历史知识库当作最终业务结论来源。
- 不考虑旧知识库数据迁移兼容问题；如需结构调整，后续实现可按当前最佳设计重建。

验收标准（Acceptance）:

- `SKILL.md` 和相关 reference 明确要求每轮验证先执行知识库预检。
- `ev_action.py`、`ev_workflow.py` 或 server 执行链路能支持默认回写知识库，且可记录本轮是否命中、使用和回写。
- 最终回复规则包含知识库命中情况、使用的 workflow/action、现场验证证据、回写产物和未覆盖范围。
- 验证覆盖至少包含脚本静态检查、知识库 smoke、workflow/action 学习路径和一次基于既有 report 的回写验证。

约束（Constraints）:

- 所有新增注释和文档说明使用中文。
- 本 skill 内部运行文件仍固定写入 `.harness/electron-ui-verifier/`。
- 每轮真实 UI 验证仍必须产出本次实际执行的 workflow JSON 文件。
- 知识库建议只能作为候选路径，最终结论必须来自本轮 UI report、artifact 或截图。
- 大段写入使用分段 patch；单次新增不超过硬上限 200 行。

待确认项（Open uncertainties）:

- 无 blocking 项。若实现阶段发现需要新增第三方依赖、改变 CLI 默认行为会破坏现有调用，或需要清空用户已有知识库，必须重新请求确认。

## 上下文（Context）

本地代码（Local code）:

- `skills/electron-ui-verifier/SKILL.md`：当前知识库规则是“需要复用或沉淀时读取”，不是每轮强制。
- `skills/electron-ui-verifier/references/workflow.md`：当前写明“如果任务可能复用历史经验，先查询知识库入口”，仍是可选语气。
- `skills/electron-ui-verifier/references/knowledge.md`：定义 `.harness/electron-ui-verifier/knowledge/`、状态流转、`ev_suggest.py`、`ev_learn.py`、`ev_assets.py`。
- `skills/electron-ui-verifier/scripts/ev_action.py` 和 `ev_workflow.py`：仅在传入 `--learn` 或 `--learn-assets` 时向 server payload 写入 `learn`。
- `skills/electron-ui-verifier/scripts/ev_server.py`：`run_steps` 会生成 report/workflow；有 `persist_report_knowledge`，但只在 payload 中存在 `learn` 时执行。
- `skills/electron-ui-verifier/scripts/ev_suggest.py`：能按 `app-id` 和 `goal` 返回 workflow/action 候选，并组合候选 workflow。
- `skills/electron-ui-verifier/scripts/ev_knowledge_store.py`：已有 action/workflow asset、evidence、FTS 搜索、状态和 cleanup。

本地文档（Local docs）:

- `skills/complex-coding-harness/SKILL.md` 和 `references/workflow.md`：要求 managed 任务先落盘计划、通过自查和 readiness 后等待用户批准。
- `C:/Users/admin/.codex/skills/.system/skill-creator/SKILL.md`：要求更新 skill 时保持 `SKILL.md` 精简，将详细流程放入 references，脚本要实际验证。

外部来源（External sources）:

- 本任务暂不依赖在线资料；需求是当前仓库内 skill 流程强化。

用户约束（User constraints）:

- 将“先查知识库，再现场验证，再回写知识库”作为强制流程。
- 使用 `complex-coding-harness` 管理方案。
- 方案阶段只规划，待确认后再实现。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 当前知识库学习默认是显式触发 | read | `ev_action.py`、`ev_workflow.py`、`ev_server.py` | 需要改强制流程入口 |
| 当前知识库查询已有 CLI | read | `ev_suggest.py`、`ev_knowledge.py`、`ev_assets.py` | 可优先复用现有脚本 |
| 最终答案不能只依赖知识库 | read | `SKILL.md`、`references/knowledge.md` | 方案必须保留现场验证 |
| 旧知识库无需迁移兼容 | confirmed | 用户会话历史 | 可按新流程重新设计字段 |

## 候选方案（Options）

### 方案 A：只改文档强约束

- 做法（How）:
  - 在 `SKILL.md`、`workflow.md`、`knowledge.md` 中把知识库预检、现场验证、回写知识库写成强制步骤。
  - 最终回复模板增加知识库命中和回写摘要。
- 优点（Pros）:
  - 改动小，风险低。
  - 不改变 CLI 行为。
- 缺点（Cons）:
  - 依赖 agent 记住规则，长任务或上下文压缩后仍可能漏查。
  - 无法从脚本返回值中稳定审计“本轮是否查过知识库”。
- 风险（Risks）:
  - 复现刚才的问题：现场验证成功但忘记知识库预检。
- 验证（Validation）:
  - 只能通过文档检索和人工流程检查验证。
- 回滚（Rollback）:
  - 回退文档修改即可。

### 方案 B：文档强约束 + CLI 显式门禁

- 做法（How）:
  - 增加或增强预检入口，例如 `ev_suggest.py` 输出更适合执行前使用的 `knowledgePreflight` 结果。
  - `ev_action.py`、`ev_workflow.py` 新增参数或默认策略：要求传入 `--goal`、`--learn-app-id`，并默认回写基础知识；允许 `--no-learn` 只在明确说明时跳过。
  - report 增加 `knowledgePreflight`、`knowledgeUsage`、`knowledgeWriteback` 字段。
- 优点（Pros）:
  - agent 有明确命令可执行，最终产物可审计。
  - 不强行在 server 内推断所有目标，仍保留 workflow/action 的灵活性。
- 缺点（Cons）:
  - 仍需要 agent 先调用预检脚本，不能完全防止直接运行 workflow。
  - CLI 兼容性需要小心处理。
- 风险（Risks）:
  - 默认学习可能写入一次性探索噪声，需要区分基础候选和资产化。
- 验证（Validation）:
  - 单测或 smoke 覆盖预检、执行、回写字段。
- 回滚（Rollback）:
  - 恢复 CLI 默认不学习和旧文档规则。

### 方案 C：server 层强制闭环

- 做法（How）:
  - `/actions/run` 和 `/workflows/run` 在缺少知识库预检上下文时直接拒绝执行，除非显式传 `skipKnowledgePreflight`。
  - server 自动根据 session、appId、goal 查询知识库，执行后自动学习。
- 优点（Pros）:
  - 最强约束，绕过概率最低。
- 缺点（Cons）:
  - server 需要理解用户目标，必须让所有调用都传 `goal`，对单步 action 和临时诊断不够自然。
  - 可能阻断已有脚本和调试流程，误伤 smoke、截图、诊断。
- 风险（Risks）:
  - 过度强制导致 skill 难用，用户临时验证成本升高。
- 验证（Validation）:
  - 需要覆盖所有 action/workflow 调用路径和错误兼容。
- 回滚（Rollback）:
  - 关闭 server 强制检查并恢复为 CLI/文档约束。

## 决策（Decision）

选择方案（Chosen option）:

- 采用方案 B，并补充轻量 server 字段兜底。

原因（Why）:

- 当前缺陷是流程遗忘，不是知识库能力缺失。最合理的增强是把“知识库预检”和“执行后回写”变成 CLI 和文档共同约束，并让 report 能审计。
- 不采用纯文档方案，因为它无法防止长任务中再次遗漏。
- 不采用完全 server 强制拒绝，因为 Electron 验证有单步探索、截图、诊断、失败恢复等场景，全部强制传目标会增加摩擦。

影响（Impact）:

- 使用 `electron-ui-verifier` 的标准流程从“可选查询知识库”变为“每轮先预检，再验证，再回写”。
- 一次性探索仍允许，但必须在最终回复中说明为什么跳过资产化；基础 knowledge evidence 默认应回写。
- report、summary 或脚本输出会增加知识库相关字段。

可逆性（Reversibility）:

- 可通过恢复 CLI 默认参数和文档规则回滚，不涉及外部服务协议。

变更条件（Change conditions）:

- 如果实现时发现 CLI 默认回写会污染知识库，则改为强制 `--learn` 并让脚本缺少 `--learn` 时提示阻塞。
- 如果 report 字段改动过大，则先仅在 summary 和脚本输出中记录，server 字段下一阶段再做。

方案变更触发条件（Reapproval triggers）:

- 需要新增第三方依赖。
- 需要删除、迁移或重建用户已有 `.harness/electron-ui-verifier/knowledge/`。
- 需要改变 Electron GUI 启动或 process-manager 边界。
- 需要让 server 强制拒绝所有未预检调用。
- 必需验证无法执行且替代证据不足。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | `ev_action.py`、`ev_workflow.py`、`ev_server.py` 输出字段 | CLI 行为变化 | `--help`、workflow smoke、report JSON 检查 | `actions.md`、`workflow.md` |
| 数据结构（Data model） | yes | report knowledge 字段、knowledge store evidence | 字段设计不一致 | JSON schema/解析检查、知识库 smoke | `knowledge.md` |
| 前端交互（Frontend interaction） | no | 不改 Electron UI | 无 | 不适用 | 不适用 |
| 配置/环境（Config/environment） | no | 不新增依赖 | 低 | `ev_check_env.py` 现有检查 | `server.md` 如需补充 |
| 兼容性（Compatibility） | yes | CLI 参数和默认学习策略 | 旧流程可能少传 goal | 兼容 smoke、失败路径测试 | `SKILL.md` |
| 测试（Tests） | yes | smoke 脚本、py_compile、知识库测试 | 漏覆盖 action/workflow 差异 | 运行代表性命令 | 不适用 |
| 文档（Documentation） | yes | `SKILL.md`、`workflow.md`、`knowledge.md`、`actions.md` | 规则重复或矛盾 | 全文检索和自查 | 必需 |

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：规则和流程契约

目标（Goal）:

- 把强制闭环写入 `electron-ui-verifier` 的核心规则和参考文档。

做法（How）:

- 更新 `SKILL.md` 的必须流程：每轮验证先 `ev_suggest.py` 或等价知识库查询，再执行现场 workflow/action，最后执行回写。
- 更新 `references/workflow.md`：增加“Knowledge-First Gate”，明确预检、使用、验证、回写、最终回复字段。
- 更新 `references/knowledge.md`：区分“基础候选知识默认回写”和“action/workflow 资产化按策略回写”。
- 更新 `references/actions.md`：说明 workflow/action 应携带 `goal`、`appId`、learn 选项和知识库字段。

原因（Why）:

- 规则必须先变成 skill 的入口约束，后续脚本实现才有一致目标。

位置（Where）:

- 文件/模块（Files/modules）: `skills/electron-ui-verifier/SKILL.md`、`references/workflow.md`、`references/knowledge.md`、`references/actions.md`
- API/配置（APIs/configs）: 不新增配置
- 测试/文档（Tests/docs）: 文档全文检索和 quick validate

参考来源（References）:

- `complex-coding-harness` 的防遗忘和最终交付规则。
- `skill-creator` 的 progressive disclosure 原则。

验证（Validation）:

- `rg "Knowledge-First|知识库预检|回写知识库|knowledgePreflight" skills/electron-ui-verifier`
- `quick_validate.py skills/electron-ui-verifier`

风险和回滚（Risks and rollback）:

- 风险：文档重复导致冲突。回滚：恢复相关文档段落。

阶段契约（Stage Contract）:

- 范围（Scope）: 只改规则文档。
- 允许修改（Allowed changes）: skill 文档和 reference。
- 禁止修改（Forbidden changes）: 不改脚本逻辑，不改 process-manager 边界。
- 进入条件（Entry checks）: 用户批准本计划。
- 退出条件（Exit checks）: 文档规则无冲突，检索命中强制流程。
- 必需验证（Required validation）: `rg`、quick validate。
- 是否预期提交（Commit expected）: yes。

### 阶段 2（Stage 2）：CLI 和 report 审计字段

目标（Goal）:

- 让执行入口可以稳定携带知识库预检、使用和回写信息，避免只靠 agent 记忆。

做法（How）:

- 增强 `ev_suggest.py` 输出：包含建议状态、命中数量、推荐复验动作、可复用 workflow/action id。
- 增强 `ev_action.py` 和 `ev_workflow.py`：
  - 增加 `--goal` 和 `--app-id` 作为标准字段。
  - 增加 `--knowledge-preflight <json>` 或等价字段，把预检结果摘要传给 server。
  - 将基础学习改成默认开启或强制显式开启；若最终采用默认开启，同时保留 `--no-learn` 并要求说明。
  - 资产化仍通过 `--learn-assets` 显式开启，避免一次性探索污染资产库。
- 增强 `ev_server.py` report：
  - `knowledgePreflight`: 本轮预检摘要。
  - `knowledgeUsage`: 实际复用的 workflow/action/selector。
  - `knowledgeWriteback`: 学习状态、写入条目数、失败原因。

原因（Why）:

- 脚本输出和 report 是长任务恢复后的证据来源，必须可审计。

位置（Where）:

- 文件/模块（Files/modules）: `ev_suggest.py`、`ev_action.py`、`ev_workflow.py`、`ev_server.py`
- API/配置（APIs/configs）: CLI 参数；server payload 字段
- 测试/文档（Tests/docs）: help 输出、report JSON 检查

参考来源（References）:

- `ev_server.py` 现有 `persist_report_knowledge` 和 `workflowPath` 写入逻辑。
- `ev_knowledge_store.py` 现有 action/workflow/evidence 表。

验证（Validation）:

- `python -m py_compile` 覆盖修改脚本。
- `ev_workflow.py --help` 和 `ev_action.py --help` 检查参数。
- 使用既有 report 或最小 workflow 执行一次 `--learn` 路径，检查 report 中知识库字段。

风险和回滚（Risks and rollback）:

- 风险：默认学习写入噪声。缓解：仅基础候选默认写入，资产化仍显式；学习失败不改变 UI 验证状态，但必须记录。
- 回滚：恢复为显式 `--learn`。

阶段契约（Stage Contract）:

- 范围（Scope）: CLI 入参、server report 字段、学习调用策略。
- 允许修改（Allowed changes）: 相关 Python 脚本和配套 docs。
- 禁止修改（Forbidden changes）: 不新增外部依赖，不改变 CDP/session 机制。
- 进入条件（Entry checks）: 阶段 1 已提交，脚本上下文已读。
- 退出条件（Exit checks）: 代表性命令通过，report 可见知识库字段。
- 必需验证（Required validation）: py_compile、help、workflow/action smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 3（Stage 3）：知识库回写和资产策略

目标（Goal）:

- 明确什么时候写基础知识、什么时候写 action/workflow 资产，以及如何避免污染。

做法（How）:

- 检查并必要时增强 `ev_knowledge_extract.py`、`ev_asset_extract.py`：
  - 基础 knowledge evidence 记录本轮目标、report、workflowPath 和关键 artifact。
  - action/workflow 资产默认 candidate，带 sourceReport、sourceWorkflow、riskFlags。
  - 可复验成功后再通过 `ev_promote.py` 提升为 verified/stable。
- 增强 `ev_assets.py` 或 `ev_suggest.py` 输出，便于后续命中历史 workflow。

原因（Why）:

- 用户希望 skill 越用越好用，但不能让每次临时点击都污染可复用资产。

位置（Where）:

- 文件/模块（Files/modules）: `ev_knowledge_extract.py`、`ev_asset_extract.py`、`ev_assets.py`、`ev_suggest.py`
- API/配置（APIs/configs）: 无新增依赖
- 测试/文档（Tests/docs）: knowledge smoke、assets 查询

参考来源（References）:

- `references/knowledge.md` 的状态流转。
- `ev_knowledge_store.py` 的 `candidate`、`verified`、`stable` 设计。

验证（Validation）:

- `ev_knowledge_smoke.py`
- 用已有 report 执行 `ev_learn.py --include-assets`，检查 action/workflow 资产可查。

风险和回滚（Risks and rollback）:

- 风险：资产去重不准。缓解：保留 candidate 状态，并在 suggest 输出中说明必须复验。
- 回滚：仅保留基础知识回写，不写资产。

阶段契约（Stage Contract）:

- 范围（Scope）: 知识提取、资产提取、suggest 输出。
- 允许修改（Allowed changes）: 知识库相关脚本和文档。
- 禁止修改（Forbidden changes）: 不做旧数据迁移，不删除用户知识库。
- 进入条件（Entry checks）: 阶段 2 report 字段已稳定。
- 退出条件（Exit checks）: 查询、学习、资产化 smoke 通过。
- 必需验证（Required validation）: knowledge smoke、learn/assets smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 4（Stage 4）：端到端验证和最终收口

目标（Goal）:

- 证明强制流程在真实或模拟 Electron UI 验证任务中可执行、可审计、可恢复。

做法（How）:

- 运行静态检查和 smoke。
- 使用已有 VideoForensic report 或一个轻量 workflow 验证：
  - 先查知识库。
  - 执行现场 workflow。
  - 写回基础知识。
  - 查询本次沉淀结果。
- 复查最终文档和脚本输出，确保最终回复规则带知识库摘要。

原因（Why）:

- 该增强的核心价值是流程稳定性，不只是不报错。

位置（Where）:

- 文件/模块（Files/modules）: 所有改动文件。
- API/配置（APIs/configs）: 不新增。
- 测试/文档（Tests/docs）: py_compile、quick validate、knowledge smoke、workflow smoke。

参考来源（References）:

- 当前 `VideoForensic` 实测产生的 workflow/report 可作为本地验证样本，但最终实现不应和该应用强耦合。

验证（Validation）:

- `quick_validate.py skills/electron-ui-verifier`
- `python -m py_compile` 修改过的 Python 脚本。
- `ev_knowledge_smoke.py`
- 基于已有 report 的 `ev_learn.py` / `ev_suggest.py` 验证。

风险和回滚（Risks and rollback）:

- 风险：没有可运行 Electron app 时无法做现场端到端。缓解：用已有 report 做离线回写，并明确未覆盖现场 UI。
- 回滚：按阶段提交回退。

阶段契约（Stage Contract）:

- 范围（Scope）: 验证、修复明显缺陷、更新记录。
- 允许修改（Allowed changes）: 小范围修复和文档一致性修正。
- 禁止修改（Forbidden changes）: 不扩大到新的验证后端或新依赖。
- 进入条件（Entry checks）: 前三阶段完成。
- 退出条件（Exit checks）: 验证证据完整，最终交付门禁通过。
- 必需验证（Required validation）: 上述验证命令和结果记录。
- 是否预期提交（Commit expected）: yes。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- PowerShell、Git、rg、Python。
- `skills/electron-ui-verifier/requirements.txt` 中的依赖只在运行 verifier server 或相关脚本时需要。
- 本规划阶段不启动 verifier server，也不启动 Electron GUI。

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

- not-run，本阶段只落盘规划，不同步主分支。

最近同步（Last sync）:

- not-run

分支占用（Branch occupancy）:

- 串行 `git log <main>..HEAD`: planning 阶段未执行。
- 串行 `git -c diff.autoRefreshIndex=false diff <main>...HEAD --name-only`: planning 阶段未执行。
- 现有提交属于本任务（Existing commits belong to this task）: not-checked。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行：yes。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git：yes。
- 非 Git 文件读取和文本搜索是否可并发：yes。

只读 Git 选项（Read-only Git options）:

- 状态检查优先：`git --no-optional-locks status --short --branch`
- diff 检查优先：`git -c diff.autoRefreshIndex=false diff <range>`
- 最终提交前如需精确状态，可在确认无其它 Git 命令运行后串行执行普通 `git status --short --branch`。

Index lock 恢复策略（Index lock recovery）:

- lock 路径解析命令：`git rev-parse --git-path index.lock`
- 删除前检查：精确路径、文件存在、大小/mtime 稳定、无活跃或未知归属 Git 进程
- 删除范围：只删除解析出的精确 `index.lock`，禁止通配符、递归删除和删除其它 `.lock`
- 删除后检查：串行 `git --no-optional-locks status --short --branch`

Git Lock Recovery Log:

| 时间（Time） | lock 路径（Lock path） | 文件大小/mtime（Size/mtime） | Git 进程检查（Process check） | 操作（Action） | 后续 status（Follow-up status） |
| --- | --- | --- | --- | --- | --- |
| - | - | - | - | 未触发 | - |

提交策略（Commit policy）:

- 本规划阶段不提交，待用户批准实现后按阶段提交。
- 实施提交必须使用 `git commit -F <commit-message-file>`，禁止多个 `-m` 拆分 bullet。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: no
- 未合回时代码停留在（If not merged, code remains on）: harness/feature
- 合并前需要用户确认（User confirmation needed before merge）: yes

分支安全（Branch safety）:

- 切换前已检查工作区：yes，当前只有历史未跟踪 `.harness` 目录。
- 不自动 stash：yes
- 不自动 rebase：yes
- 不自动 reset：yes

热修复插入（Hotfix interruption）:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支：yes
- 决策：无热修复插入

未解决问题（Open issues）:

- 当前仓库存在历史未跟踪目录：`.harness/.harness/`、`.harness/electron-feasibility/`、`.harness/electron-ui-verifier-asset-smoke/`。本任务不触碰。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| rg | 检索规则和脚本 | 全阶段 | available | 低 | PowerShell Select-String | 不需要 |
| Python | py_compile、skill smoke、知识库脚本 | 阶段 2-4 | available via environment | 依赖可能缺失 | 用户指定解释器后 `ev_check_env.py` | 必要时确认 |
| process-manager | verifier server 管理 | 仅真实 UI 端到端需要 | available in repo | manager 可能离线 | 停止并请求用户启动 | 必要时确认 |
| Electron UI Verifier | 自测 skill 行为 | 阶段 4 | target skill | 真实 app 可能不可用 | 使用已有 report 离线验证 | 必要时确认 |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- planning 阶段 no。
- 实施阶段默认 no；只有执行真实 Electron UI 端到端验证并需要 verifier server 时才 yes。

process-manager skill 是否存在（process-manager skill available）:

- repo 中存在 `skills/process-manager` 时适用；当前可用 skill 列表未暴露该 skill，但 `electron-ui-verifier` 文档要求 verifier server 必须由它管理。

规则结论（Rule decision）:

- verifier server 是长期后台服务，如需启动必须用 process-manager。
- Electron GUI 应用本体仍不要使用 process-manager。
- py_compile、quick_validate、ev_learn、ev_suggest 等 finite command 不进入 process-manager。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| electron-ui-verifier | verifier server | Stage 4 if needed | `.harness/process-manager/services/electron-ui-verifier.json` | `pm_ready.py` + `ev_health.py` | pending | process-manager logs + report | pending |

禁止 shell 后台启动确认（No shell background start）:

- yes

历史视图需求（Needs `pm_list --history`）:

- no

证据保留位置（Evidence retention location）:

- `.harness/tasks/2026-07-02/feature/electron-ui-verifier-knowledge-first-flow/artifacts/` 或 `execution-plan.md`

日志沉淀确认（Log evidence persisted）:

- pending implementation

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前必须复查本节。
- 启动、验证、调试长期进程前必须复查本节。
- 上下文压缩或中断恢复后必须复查本节和 `Resume Summary`。

## 验证（Validation）

必需验证（Required）:

- `python -m py_compile` 修改过的 Python 脚本。
- `quick_validate.py skills/electron-ui-verifier`。
- `ev_workflow.py --help`、`ev_action.py --help`、`ev_suggest.py --help`。
- `ev_knowledge_smoke.py` 或等价知识库 smoke。
- 基于已有 report 的 `ev_learn.py` / `ev_suggest.py` 检查回写和查询闭环。
- 如果环境允许，使用一次真实 session workflow 验证 report 中 knowledge 字段和最终 workflow 路径。

已执行（Executed）:

- 命令/工具（Command/tool）: planning 阶段仅读取文件和创建计划。
- 结果（Result）: pending implementation。
- 证据（Evidence）: 本 `execution-plan.md`。
- 覆盖范围（Covers）: 方案设计。
- 未覆盖（Not covered）: 源码实现和运行验证。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | 文件读取、rg、git status | passed | 现有流程缺口和计划落盘 | 未实现 | 本计划文件 | 等待批准 |
| Stage 1 | `rg "Knowledge-First|知识库预检|回写知识库|knowledgePreflight" skills/electron-ui-verifier` | passed | 强制流程关键词覆盖核心文档 | 未覆盖脚本行为 | shell output | 继续 Stage 2 |
| Stage 1 | `python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\electron-ui-verifier` | passed | skill frontmatter 和基础结构 | 不检查业务逻辑 | `Skill is valid!` | 继续 Stage 2 |

可选验证（Optional）:

- 使用 VideoForensic 已有 CDP session 进行真实端到端验证。
- 导出可分享 workflow 后再通过 assets 查询命中。

产物（Artifacts）:

- 截图（Screenshot）: implementation 阶段如有 UI 验证再生成。
- 日志（Log）: implementation 阶段生成。
- Trace: 不计划。
- 报告（Report）: implementation 阶段生成。

未覆盖（Not covered）:

- 当前规划阶段未运行测试，未修改源码。

无法执行时（If unable to run）:

- 记录缺失环境、影响范围和替代验证；不得声称通过。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/knowledge.md`
- `skills/electron-ui-verifier/references/actions.md`

Changelog 计划（Changelog plan）:

- 当前 skill 目录没有独立 CHANGELOG，除非实现阶段确认仓库已有统一 changelog，否则不新增非必要文档。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `SKILL.md` | no | 局部段落 | 完整读取并检查必须流程 |
| `references/workflow.md` | yes | 二级章节 | 完整读取并检索强制流程 |
| `references/knowledge.md` | yes | 二级章节 | 完整读取并检索查询/回写/资产策略 |
| `references/actions.md` | unknown | 相关章节 | 完整读取并检查 CLI 字段一致 |
| Python scripts | unknown | 完整函数或 CLI 参数块 | py_compile、help、smoke |

写入规则（Write rules）:

- 分段 patch 是落盘策略，不要求一次性生成全部细节；大内容先有全局框架，再分模块细化，最后整体复查。
- 单次 `apply_patch` 新增建议不超过 120 行，硬上限 200 行。
- 目标文件超过 500 行时默认禁止整文件重写。
- 文档、代码、规划、任务状态都适用。

整体复查（Whole-file review）:

- 写完后重新读取完整目标文件。
- 检查 `SKILL.md` 与 reference 没有冲突。
- 检查 CLI help、report 字段和文档命名一致。
- 检查最终回复规则包含知识库摘要和 workflow 路径。

patch 失败处理（Patch failure handling）:

- 先读取目标文件确认是否有部分写入。
- 上下文不匹配时重新读取相关片段，只修正失败段。
- patch 过大时缩小段落，不重复写已成功段。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | closed | 是否需要兼容旧知识库数据迁移 | 用户已说明不需要 | 阶段 3 |
| D-002 | no | closed | Electron GUI 是否用 process-manager | 用户已说明不要 | Process Manager Gate |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pass | `Context` 证据表 |
| 影响面矩阵完整（Impact matrix complete） | pass | `Impact Matrix` |
| 候选方案比较充分（Options compared enough） | pass | 方案 A/B/C |
| 每阶段可独立验证（Stages independently verifiable） | pass | Stage 1-4 均有验证 |
| 方案变更触发条件清楚（Reapproval triggers clear） | pass | `Decision` 章节 |
| 用户批准摘要可记录（Approval summary ready） | pass | `Plan Approval` 章节 |

质量结论（Quality result）:

- `pass`

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- `pass`

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 纯文档约束不足以防遗忘 | 选择方案 B，增加 CLI/report 审计字段 | closed |
| 优化（Optimizations） | 完全 server 强制会增加单步诊断摩擦 | 采用 CLI 强约束加轻量 server 字段 | closed |
| 缺失项（Missing items） | 需要明确基础知识和资产化区别 | 阶段 3 加入资产策略 | closed |
| 风险（Risks） | 默认学习可能污染知识库 | 资产化仍显式，基础知识 candidate/observed | mitigated |
| 一致性（Consistency） | Electron GUI 不用 process-manager，verifier server 必须用 | 在 Process Manager Gate 中明确 | closed |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：no
- `Plan Self-Review` 是否需要重跑：no
- `Readiness Gate` 是否需要重跑：no
- 原因：自查修复未改变目标和阶段，只补齐策略。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pass | `Problem` |
| 上下文已收集（Context collected） | pass | 已读 skill、reference、脚本入口 |
| 候选方案已比较（Options compared） | pass | 方案 A/B/C |
| 决策已记录（Decision recorded） | pass | 选择方案 B |
| 实施阶段已细化（Implementation stages detailed） | pass | Stage 1-4 |
| 环境已确认（Environment confirmed） | pass | `.harness/environment.md` |
| Git 上下文已确认（Git context confirmed） | pass | 当前 `harness/feature` |
| 工具已确认（Tooling confirmed） | pass | Tooling 表 |
| 验证已确认（Validation confirmed） | pass | Validation 章节 |
| 最终交付证据已规划（Final delivery evidence planned） | pass | Validation 和 Stage 4 |
| 文档更新已确认（Documentation updates confirmed） | pass | Documentation 章节 |
| 风险已识别（Risks identified） | pass | Risks and rollback |
| 规划自查已通过（Plan self-review passed） | pass | Plan Self-Review |
| 阻塞问题已关闭（Blocking questions closed） | pass | 无 blocking 项 |

就绪结论（Readiness result）:

- `ready_for_approval`

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 2026-07-02 用户回复“开始实现”，批准按本计划进入实现阶段。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: Stage 1-4，按计划强化 `electron-ui-verifier` 的知识库优先验证闭环。
- 阶段提交授权（Stage commit authorization）: 每阶段完成 review 和验证后提交。
- 工具/MCP 授权（Tool/MCP authorization）: 使用本地 CLI、Python、Git；如需 verifier server，按 process-manager 规则处理。
- 文档更新授权（Documentation authorization）: 允许更新 skill 文档、reference 和必要任务记录。

提交策略（Commit policy）:

- `stage_commits_authorized`

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- in_progress

当前阶段（Current stage）:

- Stage 1: 规则和流程契约

已完成阶段（Completed stages）:

- Planning

剩余阶段（Remaining stages）:

- Stage 1: 规则和流程契约
- Stage 2: CLI 和 report 审计字段
- Stage 3: 知识库回写和资产策略
- Stage 4: 端到端验证和最终收口

下一步自动动作（Next automatic action）:

- continue Stage 1

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no, 已批准后默认 run-to-completion，除非命中停止条件。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | completed | 已完成方案制定、自查和 readiness | 文件读取、计划自查 | `execution-plan.md` | 等待用户批准 |
| Stage 1 | completed | 已将 Knowledge-First Gate 写入核心规则和 reference | `rg` 检索通过；quick validate 通过 | `skills/electron-ui-verifier/SKILL.md`、`references/workflow.md`、`references/knowledge.md`、`references/actions.md` | 提交后继续 Stage 2 |
| Stage 2 | pending | CLI/report 字段 | pending | pending | Stage 1 后执行 |
| Stage 3 | pending | 回写和资产策略 | pending | pending | Stage 2 后执行 |
| Stage 4 | pending | 验证和收口 | pending | pending | Stage 3 后执行 |

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Planning | 未修改源码 | follow-up | 实施阶段执行 |
| Stage 1 | 文档规则覆盖了预检、现场验证、回写和最终回复要求；未发现冲突 | follow-up | 已通过 `rg` 和完整文件复读确认 |

## 恢复摘要（Resume Summary）

- 整体目标（Overall goal）: 强化 `electron-ui-verifier` 为“先查知识库，再现场验证，再回写知识库”的强制闭环。
- 执行模式（Execution mode）: run-to-completion。
- 整体任务状态（Overall status）: in_progress。
- 已完成阶段（Completed stages）: Planning。
- 当前阶段（Current stage）: Stage 1: 规则和流程契约。
- 剩余阶段（Remaining stages）: Stage 1-4。
- 最新 commit（Latest commit）: none。
- 下一步自动动作（Next automatic action）: continue Stage 1。
- 当前停止条件（Current stop condition）: none。
- 状态来源（State source of truth）: execution-plan.md。
- 长期进程规则（Process manager rule）: verifier server 如需启动必须使用 process-manager；Electron GUI 本体不要使用 process-manager。
- 未覆盖/风险（Not covered/risks）: 未实现源码，未运行测试；默认学习策略需实现阶段谨慎验证。
- 不得停止说明（Do not stop note）:
  - 用户批准实施后，按 run-to-completion 连续完成 Stage 1-4，除非命中停止条件。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/<date>/<task-slug>/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | not committed | 规划阶段不提交 | not applicable |

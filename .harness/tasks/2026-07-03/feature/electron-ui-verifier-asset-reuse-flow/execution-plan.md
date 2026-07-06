# 执行计划：electron-ui-verifier 优先复用现有 action/workflow 资产

## 问题定义

目标:

- 优化 `electron-ui-verifier` 的验证流程：每轮任务必须先检索可复用的知识库、workflow asset、action asset 和已批准 workflow；命中可执行资产时优先原地复用，不再重复新建临时 action/workflow 文件。
- 明确“复用资产”和“现场验证”的边界：知识库不能替代现场结论，但可执行的已沉淀资产应直接作为本轮验证输入。
- 减少 `.harness/electron-ui-verifier/tmp/` 下重复、一次性、低价值的 action/workflow 文件，避免 agent 每次都重新造轮子。

非目标:

- 不改变 Electron GUI 应用本体启动规则；仍然不用 `process-manager` 托管 GUI。
- 不取消 pending 审核包；本轮现场验证仍要生成 report、artifact 和 pending 包。
- 不让知识库结论直接替代现场 UI 验证结论。
- 不迁移旧知识库数据；旧数据只按现有查询结果继续使用。

验收标准:

- 文档规则明确：命中可执行 workflow/action 资产时，必须优先复用现有资产或现有 workflow 文件；只有命中为空、命中不可执行、资产风险过高或现场失败时，才允许生成新 action/workflow。
- 脚本能力支持：agent 可以用 asset ID 或现有 workflow 文件直接执行，不需要先导出、复制或手写等价 JSON。
- 查询结果输出足够可执行：`ev_suggest.py` / `ev_assets.py` 能暴露资产 ID、状态、风险、来源和可执行建议。
- 最终回复必须说明“复用了哪些现有资产 / 为什么没有复用 / 是否新生成文件”。

约束:

- 遵守全局 AGENTS 规则：新增注释使用中文，修改前先读上下文，长内容分段写入。
- 仅在用户批准本计划后实施代码和文档修改。
- 当前工作区已有上一任务未提交改动，实施前必须先确认或处理，不能混入无关修改。

待确认项:

- 无 blocking 问题；本计划默认只改 `electron-ui-verifier` 的规则、脚本和测试，不提交除本任务外的历史运行产物。

## 上下文

本地代码:

- `skills/electron-ui-verifier/SKILL.md`：当前要求每轮先查知识库、再现场验证、再 pending；但没有明确“命中可执行资产时禁止重复手写”。
- `skills/electron-ui-verifier/references/workflow.md`：当前写法是“把命中内容转成新的 action/workflow，或手写 workflow 时引用其思路”，容易诱导重复生成文件。
- `skills/electron-ui-verifier/references/knowledge.md`：已要求执行前查询知识库，但没有资产复用优先级和失败降级规则。
- `skills/electron-ui-verifier/scripts/ev_suggest.py`：会返回 workflow/action 候选，但 `composedWorkflow` 只提示“必须导出或手写 workflow 后真实复验”。
- `skills/electron-ui-verifier/scripts/ev_assets.py`：支持搜索、列出和获取资产，但不支持“run-action-asset / run-workflow-asset”。
- `skills/electron-ui-verifier/scripts/ev_export_workflow.py`：可从 workflow asset 导出 workflow，但需要输出路径，会引入额外文件。
- `skills/electron-ui-verifier/scripts/ev_workflow.py`、`ev_action.py`：目前只执行 JSON 文件或 JSON 字符串，不接受资产 ID。

本地验证观察:

- `ev_assets.py search --query "苍穹AI网络版 设置 状态 已连接"` 返回 0 个资产命中，说明当前库没有精准资产。
- `ev_suggest.py --goal "苍穹AI网络版 当前状态"` 只命中通用截图/快照 action，未命中设置页 workflow。
- 当前机制缺少“精准命中时直接执行资产”的路径，也缺少“命中不精准时再探索”的强制解释。

用户约束:

- 不要每次任务都生成很多新的 action/workflow。
- 优先从现有知识库和资产中检索并复用。
- 已沉淀的经验要用好，不要重复造轮子。
- 有现成参数文件、workflow 或 action 时直接使用，不要复制到任务目录。

## 证据等级

| 结论 | 等级 | 来源 | 影响 |
| --- | --- | --- | --- |
| 当前规则没有强制资产优先复用 | read | `SKILL.md`、`workflow.md`、`knowledge.md` | 需要补规则 |
| 当前脚本不能直接按 asset ID 执行 | read | `ev_action.py`、`ev_workflow.py`、`ev_assets.py` | 需要补 CLI 能力 |
| 当前查询对苍穹AI网络版没有精准 workflow 命中 | confirmed | `ev_assets.py search`、`ev_suggest.py` 输出 | 需要保留探索降级 |
| workflow/action asset 已保存可执行 steps | read | `ev_knowledge_store.py` 表结构和 upsert | 可以直接构造执行 payload |

## 候选方案

### 方案 A：只改文档规则

- 做法: 在 `SKILL.md`、`workflow.md`、`knowledge.md` 中强调优先复用资产。
- 优点: 改动小。
- 缺点: agent 仍需要手动 `get-action/get-workflow` 后拼 JSON 或导出文件，执行成本高，容易继续手写。
- 风险: 规则落地弱，不能从工具层阻止重复生成。
- 验证: 文档检索。
- 回滚: revert 文档改动。

### 方案 B：规则 + 资产直执行脚本能力

- 做法: 文档明确资产复用门禁；新增或扩展 CLI，使 agent 可直接通过 `--action-id` / `--workflow-id` 执行资产；命中资产时无需导出、复制或手写文件。
- 优点: 行为约束和工具能力一致，减少重复文件，便于审计复用了什么。
- 缺点: 需要改脚本和补 smoke 测试。
- 风险: 资产步骤过旧或坐标型资产不稳定，需要风险门禁和降级策略。
- 验证: py_compile、help、资产直执行 smoke、现有知识库 smoke。
- 回滚: revert 脚本和文档改动。

### 方案 C：自动调度器全权选择资产

- 做法: 新增 planner/runner，自动查询、打分、执行最佳资产，失败后探索。
- 优点: 自动化程度最高。
- 缺点: 范围大，容易引入复杂决策和误执行；当前需求不需要。
- 风险: 误用低置信资产、调试复杂、规则过重。
- 验证: 需要更完整集成测试。
- 回滚: 成本高。

## 决策

选择方案:

- 方案 B：规则 + 资产直执行脚本能力。

原因:

- 用户明确要求“有现成的就用现成的，不要重复造轮子”；只写文档不足以稳定执行。
- 当前资产库存储了 action step 和 workflow steps，具备直接执行的基础。
- 不采用全自动调度器，避免过度复杂；仍由 agent 根据查询结果和风险门禁选择资产。

影响:

- `electron-ui-verifier` 的使用流程会从“预检后常写新 workflow”改为“预检后优先执行已有资产或已有 workflow 文件”。
- 新生成文件变为例外路径，需要在最终回复说明原因。

可逆性:

- 中等；脚本新增参数和文档规则可独立回滚，不改变知识库 schema。

方案变更触发条件:

- 发现资产结构不足以直接执行。
- 需要改变知识库 schema 或迁移旧数据。
- 必需验证无法覆盖资产直执行。
- 需要新增第三方依赖或长期服务。

## 影响面矩阵

| 影响对象 | 是否涉及 | 文件/模块 | 风险 | 验证方式 | 文档更新 |
| --- | --- | --- | --- | --- | --- |
| API | yes | `ev_action.py`、`ev_workflow.py` 或新增 runner 脚本 | 中 | help、smoke | yes |
| 数据结构 | no | 不改 SQLite schema | 低 | 现有 smoke | yes |
| 前端交互 | no | 不改 UI 应用 | 低 | 不适用 | no |
| 配置/环境 | no | 不新增依赖 | 低 | py_compile | no |
| 兼容性 | yes | 旧 `--action` / `--workflow` 保持兼容 | 中 | 回归 help 和旧 smoke | yes |
| 测试 | yes | 新增资产直执行 smoke | 中 | finite command | no |
| 文档 | yes | `SKILL.md`、`references/workflow.md`、`references/knowledge.md`、`references/actions.md` | 中 | 文档检索 | yes |

## 实施计划

### Stage 1：资产复用规则收紧

目标:

- 把“先查知识库”升级为“先查可复用资产并优先原地执行”。

做法:

- 修改 `SKILL.md` 的必须流程和硬规则，加入 `Reuse Gate`。
- 修改 `references/workflow.md` 的 Knowledge-First 流程，明确复用优先级。
- 修改 `references/knowledge.md`，区分知识建议、action asset、workflow asset、已批准 workflow 文件。
- 修改 `references/actions.md`，补充资产复用时的 action/workflow 来源记录。

原因:

- 当前规则仍允许命中后手写等价 workflow，导致重复临时文件和重复探索。

位置:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/knowledge.md`
- `skills/electron-ui-verifier/references/actions.md`

验证:

- `rg "Reuse Gate|资产复用|优先复用|不得重复"` 检查规则落地。
- 人工 review 文档是否仍允许无理由重复生成。

风险和回滚:

- 风险: 规则过硬导致无精准资产时不敢探索。
- 缓解: 写清楚降级条件，命中为空或不可执行时允许现场探索。
- 回滚: revert 文档段落。

阶段契约:

- 允许修改文档规则。
- 禁止修改知识库 schema。
- 预期提交: 待整体实施完成后统一提交，除非用户要求分阶段提交。

### Stage 2：资产直执行能力

目标:

- 让 agent 能直接运行已沉淀 action/workflow asset，而不是导出或复制文件。

做法:

- 优先方案：扩展 `ev_action.py` 支持 `--action-id`，扩展 `ev_workflow.py` 支持 `--workflow-id`。
- 保持 `--action` / `--workflow` 兼容；`--action` 与 `--action-id` 互斥，`--workflow` 与 `--workflow-id` 互斥。
- 从知识库读取 asset 后构造执行 payload，并把 `actionSource` / `workflowSource` 标记为 `knowledge.action_asset` 或 `knowledge.workflow_asset`。
- 支持 `--knowledge-usage` 自动补充使用的 asset ID、status、confidence、riskFlags、sourceReport。

原因:

- `ev_export_workflow.py` 需要输出文件，会制造额外文件；直接按 asset ID 执行更符合用户诉求。

位置:

- `skills/electron-ui-verifier/scripts/ev_action.py`
- `skills/electron-ui-verifier/scripts/ev_workflow.py`
- 必要时抽取轻量 helper 到新文件，例如 `ev_asset_runner.py`。

验证:

- `python -m py_compile` 覆盖修改脚本。
- `ev_action.py --help`、`ev_workflow.py --help`。
- 构造临时知识库或复用当前候选资产，验证 `--workflow-id` / `--action-id` 能生成 report 和 pending。

风险和回滚:

- 风险: 低置信坐标资产被误用。
- 缓解: CLI 不自动选择资产；agent 必须显式传入 ID，并在 final 说明风险和现场结果。
- 回滚: 移除新增参数和 helper。

### Stage 3：查询建议增强和复用门禁验证

目标:

- 查询输出能清楚告诉 agent 哪些命中可以直接执行、哪些只能参考、为什么需要探索。

做法:

- 调整 `ev_suggest.py` 的建议文案：精准 workflow/action asset 命中时推荐直接执行 asset ID。
- `ev_assets.py` summary 增加 `reusableCount`、`directRunHint` 或等价字段。
- 新增 smoke，覆盖“有 asset 时不需要写新 workflow 文件”的执行路径。
- 保留“当前查询无精准资产时允许探索”的用例。

原因:

- 仅有脚本参数还不够，建议输出必须降低 agent 误判成本。

位置:

- `skills/electron-ui-verifier/scripts/ev_suggest.py`
- `skills/electron-ui-verifier/scripts/ev_assets.py`
- `skills/electron-ui-verifier/scripts/*smoke.py`

验证:

- smoke 断言建议输出包含 direct run hint。
- smoke 断言 asset ID 执行 report 的 source 字段正确。

风险和回滚:

- 风险: 建议文案过度承诺“可直接采信”。
- 缓解: 保持“必须现场验证”措辞，只把资产作为执行输入。

### Stage 4：整体回归、记录和交付

目标:

- 确认文档、脚本、测试、changelog 和 harness 状态一致。

做法:

- 运行 py_compile、help、smoke、rg 规则检查。
- 更新 `CHANGELOG.md`。
- 更新本 `execution-plan.md` 的验证、review、提交记录。
- 如用户批准提交，使用单个 commit message 文件提交。

原因:

- 该改动影响 skill 的核心工作方式，必须保证恢复后不会忘记复用门禁。

验证:

- `python -m py_compile ...`
- `python skills/electron-ui-verifier/scripts/ev_action.py --help`
- `python skills/electron-ui-verifier/scripts/ev_workflow.py --help`
- 新增/更新 smoke。
- `rg` 检查旧的“导出或手写”强诱导语是否已替换。

风险和回滚:

- 风险: 当前工作区已有未提交改动，提交时混入历史任务。
- 缓解: 实施前先确认现有改动归属；提交时精确 stage。

## 环境

Workspace 环境来源:

- `.harness/environment.md`

本任务使用:

- 当前仓库 `E:\work\hl\videoForensic\AI\dev-skills`。
- Python finite command，用当前可用 `python`。
- 不需要启动新的长期服务；如要真实 Electron UI 验证，verifier server 仍按 `process-manager` 规则。

临时覆盖:

- 无。

## Git Context

主分支:

- main

任务类型:

- feature

工作分支:

- harness/feature

分支动作:

- already-on-branch

同步来源:

- 未在规划阶段执行 merge；实施前按 `.harness/environment.md` 和当前工作区状态确认。

当前 Git 状态:

- 已串行执行 `git -c safe.directory=E:/work/hl/videoForensic/AI/dev-skills --no-optional-locks status --short --branch`。
- 当前分支为 `harness/feature`。
- 工作区存在上一任务未提交改动和未跟踪文件；实施前必须确认处理方式，不能直接提交混入。

Git 命令策略:

- 同一仓库 Git 命令必须串行。
- 禁止并发执行同仓库 Git。
- 非 Git 文件读取和文本搜索可并发，但不能与 Git 命令混入同一并发批次。

提交策略:

- 计划阶段不提交。
- 用户批准实施并授权提交后，使用 `git commit -F <commit-message-file>`，不用多个 `-m`。

## 工具

| 工具 | 用途 | 阶段 | 状态 | 风险 | 替代方案 | 用户确认 |
| --- | --- | --- | --- | --- | --- | --- |
| complex-coding-harness | 管理规划和后续实施 | 全阶段 | read | 低 | 手动规则 | 已由用户要求 |
| electron-ui-verifier | 被修改对象 | 全阶段 | read | 中 | 无 | 待批准实施 |
| process-manager | 仅 verifier server 长期服务需要 | 可选真实 UI 验证 | available | 低 | 用户手动启动 manager | 规则已有 |
| Python | 脚本检查和 smoke | 验证 | available | 低 | 指定解释器 | 不需新增确认 |
| Git | 状态和提交 | Stage 4 | dirty worktree | 中 | 精确 stage | 提交前确认 |

## Process Manager Gate

是否需要长期后台进程:

- 本计划制定阶段: no。
- 后续实施阶段: 默认 no，脚本验证均为 finite command。
- 如需要真实 Electron UI 验证: verifier server 必须用 process-manager；Electron GUI 本体不用 process-manager。

process-manager skill 是否存在:

- yes，仓库内存在 `skills/process-manager/SKILL.md`。

规则结论:

- 不手写后台服务命令。
- finite command 直接运行。
- 如果真实 UI 验证需要 verifier server，先读 `process-manager` 规则并使用 `pm_*`。

证据保留位置:

- 本任务规划和后续验证证据写入本 `execution-plan.md`。

## 验证

必需验证:

- Python 编译检查：覆盖所有修改过的 `scripts/*.py`。
- CLI help：`ev_action.py --help`、`ev_workflow.py --help`、`ev_assets.py --help`、`ev_suggest.py --help`。
- 资产直执行 smoke：验证按 action/workflow asset ID 执行，不需要导出或复制 workflow 文件。
- 知识库建议 smoke：验证建议输出包含直接复用提示和风险说明。
- 文档规则检索：确认 `Reuse Gate` 和降级条件存在。

验证证据表:

| 阶段 | 命令/工具 | 结果 | 覆盖内容 | 未覆盖 | 证据/日志 | 处理 |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | `ev_assets.py search/list-*`、`ev_suggest.py` | passed | 当前资产命中现状 | 未执行代码修改 | 终端输出 | 支撑方案 |
| Stage 1 | `rg` 文档检索 | passed | Reuse Gate、复用优先、降级条件 | 真实 UI | `rg "Reuse Gate|不得重复生成|--workflow-id|--action-id"` | 无需修复 |
| Stage 2 | py_compile、help、asset reuse smoke | passed | `--action-id` / `--workflow-id`、asset source、knowledgeUsage | 真实 Electron | `ev_action.py --help`、`ev_workflow.py --help`、`ev_asset_reuse_smoke.py` | 无需修复 |
| Stage 3 | asset reuse smoke、asset extract smoke、pending smoke | passed | 建议输出 directRun、资产抽取、pending approve | 大规模知识库 | `ev_asset_reuse_smoke.py`、`ev_asset_extract_smoke.py`、`ev_pending_smoke.py` | 无需修复 |
| Stage 4 | 全量 py_compile、knowledge smoke、diff check | passed | 文档、脚本、测试一致性 | 真实业务 UI 未运行 | `Get-ChildItem ... ev_*.py | py_compile`、`ev_knowledge_smoke.py --temp`、`git diff --check` | 无需修复 |

未覆盖:

- 规划阶段不运行真实 VideoForensic UI 验证。
- 不验证远程 CDP。
- 不验证过期或 deprecated 资产自动清理。

## 文档

必需更新:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/knowledge.md`
- `skills/electron-ui-verifier/references/actions.md`
- `CHANGELOG.md`

Changelog 计划:

- 记录“新增资产复用优先门禁和 asset ID 直执行能力”。
- 记录“命中为空或不可执行时才允许探索并生成新文件”。

## 文件写入策略

分段判断:

| 文件 | 分段判断 | 分段边界 | 整体复查方式 |
| --- | --- | --- | --- |
| `SKILL.md` | no | 局部规则段 | 完整读取 |
| `references/workflow.md` | yes | Knowledge-First / Evidence / Server Workflow 小节 | 完整读取 |
| `references/knowledge.md` | yes | 查询和建议 / 学习方式小节 | 完整读取 |
| `references/actions.md` | no | action 来源说明 | 完整读取 |
| `ev_action.py` | no | 参数解析和 payload 构建 | py_compile/help |
| `ev_workflow.py` | no | 参数解析和 payload 构建 | py_compile/help |
| `ev_suggest.py` | no | 输出文案和摘要字段 | py_compile/smoke |
| `ev_assets.py` | no | summary 字段 | py_compile/smoke |
| smoke 脚本 | no | 单文件新增，若超过 200 行再拆 | py_compile/run |
| `CHANGELOG.md` | no | 单日期块 | 完整读取 |

写入规则:

- 分段 patch 是落盘策略，不是思考策略。
- 单次新增建议不超过 120 行，硬上限 200 行。
- 不整文件重写超过 500 行的文件。
- patch 失败后先读取目标文件确认状态，再缩小 patch。

## 方案质量门禁

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 关键判断有证据等级 | passed | 已列证据等级 |
| 影响面矩阵完整 | passed | 已覆盖 API、兼容、测试、文档 |
| 候选方案比较充分 | passed | 比较 A/B/C |
| 每阶段可独立验证 | passed | Stage 1-4 均有验证 |
| 方案变更触发条件清楚 | passed | 已列触发条件 |
| 用户批准摘要可记录 | passed | Plan Approval 待填写 |

质量结论:

- passed

## 规划自查

自查结论:

- passed after adjustments

| 类别 | 发现 | 处理 | 结果 |
| --- | --- | --- | --- |
| 缺陷 | 原始需求容易被误解为“知识库结论直接回答” | 明确知识库只作为执行输入，最终仍需现场验证 | fixed |
| 优化 | 只靠导出 workflow 会继续制造文件 | 选择 asset ID 直执行 | fixed |
| 缺失项 | 当前工作区已有未提交改动 | 加入 Git Stage Entry 阻塞检查 | fixed |
| 风险 | 低置信坐标资产可能不稳定 | 加入风险门禁和降级路径 | fixed |
| 一致性 | pending 审核包仍然需要保留 | 明确复用不取消 pending | fixed |

门禁重跑:

- Plan Quality Gate 是否需要重跑: no
- Plan Self-Review 是否需要重跑: no
- Readiness Gate 是否需要重跑: no
- 原因: 自查修复没有改变目标、范围、阶段或验证策略。

## 就绪门禁

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 目标和验收清楚 | passed | 问题定义 |
| 上下文已收集 | passed | 已读相关文档和脚本 |
| 候选方案已比较 | passed | 方案 A/B/C |
| 决策已记录 | passed | 选择方案 B |
| 实施阶段已细化 | passed | Stage 1-4 |
| 环境已确认 | passed | `.harness/environment.md` |
| Git 上下文已确认 | partial | 已检查分支和 dirty 状态；实施前需处理 |
| 工具已确认 | passed | 工具表 |
| 验证已确认 | passed | 验证表 |
| 最终交付证据已规划 | passed | Stage 4 |
| 文档更新已确认 | passed | 文档计划 |
| 风险已识别 | passed | 风险和回滚 |
| 规划自查已通过 | passed | 自查表 |
| 阻塞问题已关闭 | passed | 无 blocking 问题 |

就绪结论:

- approved for implementation.

## 方案批准

状态:

- approved

批准记录:

- 2026-07-03 用户回复“允许，开始实现”，批准按本计划实施并提交。

批准摘要:

- 批准范围: Stage 1-4 全部实施，包括文档、脚本、smoke、changelog 和 harness 状态更新。
- 阶段提交授权: 已授权最终提交；本任务采用整体提交，不在每个小阶段拆 commit。
- 工具/MCP 授权: 当前不需要新增 MCP；如真实 UI 验证需按既有 electron-ui-verifier/process-manager 规则。
- 文档更新授权: 已授权。

提交策略:

- authorized

## 执行控制

执行模式:

- run-to-completion

整体任务状态:

- complete

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

- no after implementation approval; currently stopped only for plan approval.

## 实施进度

| 阶段 | 状态 | 摘要 | 验证 | 证据 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| Planning | completed | 已制定资产复用优先方案 | 本地文档和脚本阅读、现状查询 | 本文档 | 已批准 |
| Stage 1 | completed | 文档规则收紧，新增 Reuse Gate 和降级条件 | passed | 文档检索 | Stage 2 已完成 |
| Stage 2 | completed | `ev_action.py` / `ev_workflow.py` 支持 asset ID 直执行 | passed | help、py_compile、asset reuse smoke | Stage 3 已完成 |
| Stage 3 | completed | 查询建议暴露 direct run hint，并补 smoke 覆盖 | passed | asset reuse/extract/pending smoke | Stage 4 已完成 |
| Stage 4 | completed | 完成回归、changelog 和提交准备 | passed | py_compile、knowledge smoke、diff check | 最终交付 |

## 代码审查

| 阶段 | 问题 | 严重程度 | 处理 |
| --- | --- | --- | --- |
| Planning | 未修改代码 | follow-up | 实施阶段执行 |
| Stage 1-4 | 未发现 blocking 或 major 问题；已确认旧“必须导出或手写”诱导语被移除，旧 CLI 参数保持兼容 | none | 无需修复 |

## 恢复摘要

- 整体目标: 让 `electron-ui-verifier` 优先复用已有知识库、action asset、workflow asset 和已批准 workflow，减少重复生成临时 action/workflow。
- 执行模式: run-to-completion。
- 整体任务状态: complete。
- 已完成阶段: Planning、Stage 1、Stage 2、Stage 3、Stage 4。
- 当前阶段: Final delivery。
- 剩余阶段: none。
- 最新 commit: `17d46fa`。
- 下一步自动动作: final delivery。
- 当前停止条件: all approved stages completed。
- 状态来源: execution-plan.md。
- 长期进程规则: 本任务默认不需要长期进程；真实 UI 验证时 verifier server 用 process-manager，Electron GUI 不用。
- 未覆盖/风险: 未运行真实 Electron UI；本次覆盖脚本、文档和离线知识库链路。当前工作区仍有未纳入本次提交的历史运行产物，应继续忽略。

## 提交记录

提交信息方式:

- 使用 `git commit -F .harness/tasks/2026-07-03/feature/electron-ui-verifier-asset-reuse-flow/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。

| 阶段 | 仓库 | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | not committed | planning only | not changed |
| Stage 1-4 | dev-skills | `17d46fa` | `feat(electron-ui-verifier): 完善确认持久化和资产复用流程` | `CHANGELOG.md` 2026-07-03 |

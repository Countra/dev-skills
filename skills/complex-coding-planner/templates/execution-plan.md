# 执行计划（Execution Plan）

## 规划摘要（Plan Summary）

- Task ID：`<task-id>`
- Plan revision：`1`
- Lifecycle route：`managed`
- Plan profile：`lite / standard / full`
- Discovery-first：`yes / no`
- Task contract：`plan-contract.json`
- Approval request：`implementation / commit / external write / elevated tool`

本文件只保存批准意图。批准后不得写入 current stage、progress、运行结果、ledger 摘要或 commit 状态；执行事实由 `attestation.json`、`run-state.json` 和 `ledger.jsonl` 保存。

## 问题定义（Problem）

目标（Goal）：`GOAL-01`

非目标（Non-goals）:

验收标准（Acceptance）:

约束（Constraints）:

待确认项（Open uncertainties）:

## 需求与验收（Requirements And Acceptance）

功能需求：

| ID | Priority | Requirement | Evidence |
| --- | --- | --- | --- |
| REQ-01 | must |  |  |

非功能需求：

| ID | Requirement | Validation |
| --- | --- | --- |
| NFR-01 |  |  |

验收标准：

| ID | Requirement IDs | Given / When / Then |
| --- | --- | --- |
| AC-01 | REQ-01 |  |

## 调研门禁（Research Gate）

研究模式（Research mode）：`none / local-only / online-required / blocked-by-access`

触发原因（Why this mode）:

-

不确定项清单（Uncertainty inventory）:

| ID | 问题（Question） | 类型（Type） | 是否需要在线搜索（Online required） | 处理结果（Resolution） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- |
|  | local-code / local-doc / external-tool / external-service / high-risk / user-decision | yes/no |  |  |

搜索记录（Search log）:

| 查询/来源（Query/source） | 工具（Tool） | 日期（Date） | 结果（Result） | 后续动作（Next action） |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

来源矩阵（Source matrix）:

| 结论（Claim） | 来源类型（Source type） | URL/路径（URL/path） | 是否官方/一手（Official/primary） | 访问日期（Accessed） | 可信度（Confidence） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- | --- |
|  | local / official / primary / external / assumption |  | yes/no |  | high/medium/low |  |

调研结论（Research result）：`pending`

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）：`none / local-only / online-required / blocked-by-access`

技术栈清单（Technology inventory）:

| 类型（Type） | 发现（Finding） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 语言（Language） |  |  |  |
| 框架（Framework） |  |  |  |
| API/架构类型（API/architecture） |  |  |  |
| 工具链（Toolchain） |  |  |  |

规范来源矩阵（Standards source matrix）:

| 规范来源（Standard source） | 类型（Type） | 官方/一手（Official/primary） | 适用边界（Applicability） | 访问日期（Accessed） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- |
|  | project / language / framework / API / architecture / pattern / security / other | yes/no |  |  |  |

standards index:

- 路径或章节（Path/section）:
- 摘要（Summary）:
- 未覆盖或 blocked-by-access（Not covered / blocked）:

规范发现结论（Standards result）：`pending`

## 开发质量门禁（Development Quality Gate）

质量范围（Quality scope）:

| 维度（Dimension） | 规划结论（Plan） | 阶段映射（Stage mapping） | 验证映射（Validation mapping） |
| --- | --- | --- | --- |
| 代码标准（Code standards） |  |  |  |
| 静态质量（Static quality） |  |  |  |
| 架构边界（Architecture boundaries） |  |  |  |
| 设计模式取舍（Design pattern decision） |  |  |  |
| 低耦合（Low coupling） |  |  |  |
| 高内聚（High cohesion） |  |  |  |

过度设计防护（Overengineering guard）:

-

开发质量结论（Development quality result）：`pending`

## 依赖选型门禁（Dependency Selection Gate）

选择模式（Selection mode）：`none / retain / change / mixed`

触发面（Trigger surfaces）:

- manifest / lock / vendor / base image / CI Action / framework / ORM / SDK / driver / codegen / build plugin / critical retain / none

必要性结论（Necessity result）：`not-triggered / dependency-required / existing-sufficient / standard-or-official-sufficient / blocked`

优先级检查（Priority check）:

- 用户/组织政策：
- 现有项目栈：
- 标准库/平台/官方 SDK：
- 生态主流基线：
- specialized exception：

决策摘要（Decision summary）:

| DEP ID | Action | Category / criticality | Selected identity | Selection class | Version policy | Manifest paths | Evidence artifact | Validation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DEP-01 | retain / add / upgrade / replace |  |  | existing-stack / standard-or-official / ecosystem-mainstream / specialized-exception |  |  | ART-XX | VAL-XX |

可信度摘要（Trust summary）:

| DEP ID | Stable version | Adoption scale | Update recency | Maintenance | Adoption trend | As of / max age | Caveat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DEP-01 | pass / concern / fail / insufficient-data |  |  |  |  | YYYY-MM-DD / 30, 60 or 90 days |  |

硬门槛与例外（Hard gates and exceptions）:

- authenticity / compatibility / stable support / lifecycle / security / license / reproducibility：
- specialized exception baseline、unmet REQ、risk acceptance、mitigation、rollback：

依赖证据（Dependency evidence）:

- `artifacts/dependencies/dependency-selection.json`，仅 mode 非 `none` 时创建。
- mode 为 `none` 时说明零 decision、零 dependency artifact 与 stage scope 一致的依据。

依赖选型结论（Dependency selection result）：`pending / passed / not-applicable / blocked`

## 上下文（Context）

本地代码（Local code）:

- 

本地文档（Local docs）:

- 

外部来源（External sources）:

- 

用户约束（User constraints）:

- 

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
|  | read / confirmed / external / assumption |  |  |

## 候选方案（Options）

### 方案 A：最小改动（Minimal Change）

- 做法（How）:
- 优点（Pros）:
- 缺点（Cons）:
- 风险（Risks）:
- 验证（Validation）:
- 回滚（Rollback）:

### 方案 B：结构化改动（Structured Change）

- 做法（How）:
- 优点（Pros）:
- 缺点（Cons）:
- 风险（Risks）:
- 验证（Validation）:
- 回滚（Rollback）:

## 决策（Decision）

选择方案（Chosen option）:

原因（Why）:

影响（Impact）:

可逆性（Reversibility）:

变更条件（Change conditions）:

方案变更触发条件（Reapproval triggers）:

-

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes/no |  |  |  |  |
| 数据结构（Data model） | yes/no |  |  |  |  |
| 前端交互（Frontend interaction） | yes/no |  |  |  |  |
| 配置/环境（Config/environment） | yes/no |  |  |  |  |
| 兼容性（Compatibility） | yes/no |  |  |  |  |
| 测试（Tests） | yes/no |  |  |  |  |
| 文档（Documentation） | yes/no |  |  |  |  |
| 代码标准（Code standards） | yes/no |  |  |  |  |
| 架构设计（Architecture/design） | yes/no |  |  |  |  |

## 实施计划（Implementation Plan）

阶段依赖、引用、授权和验证以 `plan-contract.json` 为机器真相源；本节解释实施理由和边界。

### STG-01：<阶段名称>

目标（Goal）:

- 

做法（How）:

- 

原因（Why）:

- 

位置（Where）:

- 文件/模块（Files/modules）:
- API/配置（APIs/configs）:
- 测试/文档（Tests/docs）:

参考来源（References）:

- 

适用规范（Standards applied）:

-

开发质量检查（Development quality checks）:

-

验证（Validation）:

- 

风险和回滚（Risks and rollback）:

- 

阶段契约（Stage Contract）:

- 依赖（Depends on）:
- 需求/验收（REQ/AC/NFR）:
- 范围（Scope）:
- 允许修改（Allowed changes）:
- 禁止修改（Forbidden changes）:
- 进入条件（Entry checks）:
- 退出条件（Exit checks）:
- 适用规范（Standards applied）:
- 开发质量检查（Development quality checks）:
- 必需验证（Required validation）:
- 是否预期提交（Commit expected）:

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- 

临时覆盖（Temporary overrides）:

- 

## Git 上下文（Git Context）

- Main / working branch：
- Task type / branch action：
- Sync source / occupancy evidence：
- Worktree status and known changes：
- Commit authorization：`requested / not requested`
- Branch closure：

规则：同一仓库 Git 命令串行；只读状态优先 `--no-optional-locks`，diff 优先禁用 index refresh。不自动 stash、rebase、reset 或覆盖未知改动。遇到 `index.lock` 时只按精确路径、稳定性和进程检查恢复，并记录 evidence。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## 长期进程管理（Process Manager Gate）

- Needs long-running process：`yes / no`
- Manager bootstrap：统一 `pm_manager.py status|start`；不判断 OS/backend；普通流程不先运行 doctor
- Managed services、stage、service config 和 readiness：
- Required process-manager evidence：authenticated manager identity / config validation / processKey / ready / bounded logs / graceful-force stop / owner-empty cleanup
- Completion fields：`cleanupVerified: true` / `stopResult.ownerEmpty: true` / manager shutdown or intentional retention
- Fallback or blocker：

存在 process-manager 时，服务、worker、watcher 和 dev server 必须由统一公共 CLI 管理；finite test/build/lint command 直接运行。不得用手写后台 shell 绕过 manager，不得把平台 backend 选择责任交给调用方。

## 验证（Validation）

| VAL ID | Required | Kind / command / tool | Covers AC/NFR | Evidence path | Failure handling |
| --- | --- | --- | --- | --- | --- |
| VAL-01 | yes |  | AC-01 | artifacts/validation/... | repair and rerun / stop |

规划阶段已执行的探针与实施阶段验证分开记录。无法执行的必需项必须说明原因、影响、替代证据和残余风险，不能标为 passed。

## 文档（Documentation）

必需更新（Required updates）:

- 

Changelog 计划（Changelog plan）:

- 

## 文件写入策略（File Write Strategy）

| File / group | Segmented | Semantic boundaries | Whole-file check |
| --- | --- | --- | --- |
|  | yes/no |  |  |

长内容先建框架，再按完整章节、函数或配置分段 patch；单次新增建议不超过 120 行、最多 200 行。超过 500 行的目标默认定点修改。patch 失败先检查部分写入，完成后完整重读并检查格式、ID、引用和末尾。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pending |  |
| Research Gate 已完成（Research Gate complete） | pending |  |
| Standards Discovery Gate 已完成（Standards discovery complete） | pending |  |
| Development Quality Gate 已完成（Development quality complete） | pending |  |
| Dependency Selection Gate 已完成（Dependency selection complete） | pending |  |
| 影响面矩阵完整（Impact matrix complete） | pending |  |
| 候选方案比较充分（Options compared enough） | pending |  |
| 每阶段可独立验证（Stages independently verifiable） | pending |  |
| 方案变更触发条件清楚（Reapproval triggers clear） | pending |  |
| 用户批准摘要可记录（Approval summary ready） | pending |  |

质量结论（Quality result）:

- `pending`

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- `pending`

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） |  |  | pending |
| 优化（Optimizations） |  |  | pending |
| 缺失项（Missing items） |  |  | pending |
| 风险（Risks） |  |  | pending |
| 一致性（Consistency） |  |  | pending |
| 开发质量（Development quality） |  |  | pending |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：
- `Plan Self-Review` 是否需要重跑：
- `Readiness Gate` 是否需要重跑：
- 原因：

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pending |  |
| 上下文已收集（Context collected） | pending |  |
| 调研门禁已通过（Research Gate passed） | pending |  |
| 规范发现门禁已通过（Standards Discovery Gate passed） | pending |  |
| 开发质量门禁已通过（Development Quality Gate passed） | pending |  |
| 依赖选型门禁已通过（Dependency Selection Gate passed） | pending |  |
| 候选方案已比较（Options compared） | pending |  |
| 决策已记录（Decision recorded） | pending |  |
| 实施阶段已细化（Implementation stages detailed） | pending |  |
| 环境已确认（Environment confirmed） | pending |  |
| Git 上下文已确认（Git context confirmed） | pending |  |
| 工具已确认（Tooling confirmed） | pending |  |
| 验证已确认（Validation confirmed） | pending |  |
| 最终交付证据已规划（Final delivery evidence planned） | pending |  |
| 文档更新已确认（Documentation updates confirmed） | pending |  |
| 风险已识别（Risks identified） | pending |  |
| 规划自查已通过（Plan self-review passed） | pending |  |
| 阻塞问题已关闭（Blocking questions closed） | pending |  |

就绪结论（Readiness result）:

- `pending`

## 方案批准（Plan Approval）

状态（Status）:

- `not_requested`

批准记录（Approval record）:

- 

批准摘要（Approval summary）:

- 批准范围（Approved scope）:
- 阶段提交授权（Stage commit authorization）:
- 工具/MCP 授权（Tool/MCP authorization）:
- 文档更新授权（Documentation authorization）:

提交策略（Commit policy）:

- `not_authorized`

## 方案变更门禁（Plan Amendment Gate）

需要重新批准（Requires reapproval）:

- approved scope 改变:
- 阶段边界、顺序或 Stage Contract 改变:
- 必需验证、工具授权、长期进程策略或提交策略改变:
- 风险等级、公共接口、数据结构、权限、依赖或兼容性假设改变:
- attestation mismatch 且无法证明是预期文档更新:

无需重新批准的记录（No-reapproval records）:

| 时间（Time） | 变更（Change） | 原因（Reason） | 证据（Evidence） |
| --- | --- | --- | --- |
|  |  |  |  |

## Artifact Index

| ID | Kind | Path | Required | Approval included | Trigger |
| --- | --- | --- | --- | --- | --- |
| ART-01 | research / standards / architecture / dependency / validation / review / other | artifacts/... | yes/no | yes/no | profile or risk rule |

只列出实际创建的 artifact；每项必须与 `plan-contract.json` 一致。运行日志、review 结果和 commit evidence 由 executor 在批准后创建，不进入本表。

## Executor Handoff

- Planner checker：`approval` mode passed / pending
- Open blocking decisions：none / list
- Requested implementation authorization：yes / no
- Requested commit authorization：yes / no
- Requested external-write authorization：yes / no
- Requested elevated-tool authorization：yes / no
- Residual risks：

用户批准后由 executor 生成 attestation 并初始化 run-state/ledger。本文件批准后不可变。

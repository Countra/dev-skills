# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

非目标（Non-goals）:

验收标准（Acceptance）:

约束（Constraints）:

待确认项（Open uncertainties）:

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

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：<阶段名称>

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

验证（Validation）:

- 

风险和回滚（Risks and rollback）:

- 

阶段契约（Stage Contract）:

- 范围（Scope）:
- 允许修改（Allowed changes）:
- 禁止修改（Forbidden changes）:
- 进入条件（Entry checks）:
- 退出条件（Exit checks）:
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

主分支（Main branch）:

-

任务类型（Task type）:

-

工作分支（Working branch）:

-

分支动作（Branch action）:

- create / reuse / already-on-branch / not-applicable

同步来源（Sync source）:

-

最近同步（Last sync）:

-

分支占用（Branch occupancy）:

- `git log <main>..HEAD`:
- `git diff <main>...HEAD --name-only`:
- 现有提交属于本任务（Existing commits belong to this task）:

提交策略（Commit policy）:

-

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）:
- 未合回时代码停留在（If not merged, code remains on）:
- 合并前需要用户确认（User confirmation needed before merge）:

分支安全（Branch safety）:

- 切换前已检查工作区：
- 不自动 stash：
- 不自动 rebase：
- 不自动 reset：

热修复插入（Hotfix interruption）:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支：
- 决策：

未解决问题（Open issues）:

-

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## 验证（Validation）

必需验证（Required）:

- 

已执行（Executed）:

- 命令/工具（Command/tool）:
- 结果（Result）:
- 证据（Evidence）:
- 覆盖范围（Covers）:
- 未覆盖（Not covered）:

可选验证（Optional）:

- 

产物（Artifacts）:

- 截图（Screenshot）:
- 日志（Log）:
- Trace:
- 报告（Report）:

未覆盖（Not covered）:

- 

无法执行时（If unable to run）:

- 

## 文档（Documentation）

必需更新（Required updates）:

- 

Changelog 计划（Changelog plan）:

- 

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pending |  |
| 上下文已收集（Context collected） | pending |  |
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
| 阻塞问题已关闭（Blocking questions closed） | pending |  |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pending |  |
| 影响面矩阵完整（Impact matrix complete） | pending |  |
| 候选方案比较充分（Options compared enough） | pending |  |
| 每阶段可独立验证（Stages independently verifiable） | pending |  |
| 方案变更触发条件清楚（Reapproval triggers clear） | pending |  |
| 用户批准摘要可记录（Approval summary ready） | pending |  |

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

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- |
|  | pending | pending | pending | pending | pending |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
|  | pending | pending | pending | pending | pending | pending |

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
|  |  |  |  |

## 提交记录（Commit Log）

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

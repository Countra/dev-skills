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

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- yes/no

process-manager skill 是否存在（process-manager skill available）:

- yes/no/not-checked

规则结论（Rule decision）:

- 如果 `process-manager` 存在，所有服务、后台或需要挂起运行的长期进程必须使用它管理。
- finite command，例如测试、lint、build、format、迁移和一次性脚本，不进入 `process-manager`。
- manager 离线时必须停止长期进程操作，请求用户手动启动 manager 或授权 bootstrap；不能退回 shell 后台启动。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  | dev-server / web / worker / watcher / model / other |  |  |  | pending | pending | pending |

禁止 shell 后台启动确认（No shell background start）:

- pending

历史视图需求（Needs `pm_list --history`）:

- yes/no

证据保留位置（Evidence retention location）:

- `execution-plan.md` / `.harness/tasks/<date>/<task-slug>/artifacts/` / not-applicable

日志沉淀确认（Log evidence persisted）:

- pending

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前必须复查本节。
- 启动、验证、调试长期进程前必须复查本节。
- 上下文压缩或中断恢复后必须复查本节和 `Resume Summary`。

## 验证（Validation）

必需验证（Required）:

- 

已执行（Executed）:

- 命令/工具（Command/tool）:
- 结果（Result）:
- 证据（Evidence）:
- 覆盖范围（Covers）:
- 未覆盖（Not covered）:

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
|  |  | pending |  |  |  |  |

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

## 文件写入策略（File Write Strategy）

预计大文件（Expected large writes）:

| 文件（File） | 预计新增/替换行数（Estimated lines） | 分段方案（Segmentation plan） | 单次 patch 上限（Patch limit） |
| --- | --- | --- | --- |
|  |  |  |  |

写入规则（Write rules）:

- 分段 patch 是落盘策略，不要求一次性生成全部细节；大内容首次写入前必须先有全局框架，再分模块递进式细化，最后整体复查。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 预计新增超过 300 行时，必须先写分段方案。
- 目标文件超过 500 行时，默认禁止整文件重写。
- 代码、文档、规划、模板、eval、changelog 和任务状态文件都适用。

整体复查（Whole-file review）:

- 写完后重新读取完整目标文件：
- 需要检查的整体一致性：
- 对应验证命令或方式：

patch 失败处理（Patch failure handling）:

- 读取目标文件确认是否有部分写入：
- 失败原因判断：
- 重试策略：

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pending |  |
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

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion / stage-only / planning-only

整体任务状态（Overall status）:

- awaiting_plan_approval / in_progress / blocked / completed

当前阶段（Current stage）:

-

已完成阶段（Completed stages）:

-

剩余阶段（Remaining stages）:

-

下一步自动动作（Next automatic action）:

-

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no, unless the user explicitly requested stage-only execution or a Stop Condition is active

active-task 同步字段（active-task sync fields）:

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "in_progress",
  "current_stage": "Stage N",
  "remaining_stages": ["Stage N+1"],
  "next_automatic_action": "continue Stage N+1",
  "stop_condition": "none",
  "state_source": "execution-plan.md"
}
```

状态同步规则（State sync rules）:

- `execution-plan.md` 是唯一主契约；`.harness/active-task.json` 只作为恢复入口和摘要索引。
- `next_action` 可以保留，但不得与 `next_automatic_action` 冲突。
- 如果 `active-task.json` 和本节冲突，必须以本节为准修正 `active-task.json` 后继续。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
|  | pending | pending | pending | pending | pending | pending |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  | pending | pending | pending | pending | pending | pending | pending | pending |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证已完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | continue Stage N / final delivery / stop with reason |

结论（Decision）:

-

规则（Rules）:

- 如果还有 pending stage，且没有停止条件，也不需要重新批准，下一动作必须是 `continue Stage N`。
- 这种情况下可以发送简短进度更新，但不能最终回复后停止。
- 进入下一阶段前必须同步 `Execution Control`、`Resume Summary` 和 `.harness/active-task.json`。

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
|  |  | blocking / major / minor / follow-up |  |

## 恢复摘要（Resume Summary）

- 整体目标（Overall goal）:
- 执行模式（Execution mode）:
- 整体任务状态（Overall status）:
- 已完成阶段（Completed stages）:
- 当前阶段（Current stage）:
- 剩余阶段（Remaining stages）:
- 最新 commit（Latest commit）:
- 下一步自动动作（Next automatic action）:
- 当前停止条件（Current stop condition）:
- 状态来源（State source of truth）:
- 长期进程规则（Process manager rule）:
- 未覆盖/风险（Not covered/risks）:
- 不得停止说明（Do not stop note）:
  - Stage boundary is not a stop condition. Continue until all approved stages and the final delivery gate are complete, unless a Stop Condition is active.

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/<date>/<task-slug>/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

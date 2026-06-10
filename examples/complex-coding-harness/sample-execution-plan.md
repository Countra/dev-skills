# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:
新增一个前端筛选项和对应后端 API 支持，并确保上下文压缩后不会丢失任务状态。

非目标（Non-goals）:
- 不修改认证逻辑。
- 不重新设计页面。

验收标准（Acceptance）:
- 后端 API 支持新的筛选项。
- 前端可以选择该筛选项。
- 测试和浏览器验证通过。

## 上下文（Context）

本地代码（Local code）:
- `backend/api/items.go`
- `frontend/src/pages/Items.tsx`

本地文档（Local docs）:
- `backend/docs/development.md`
- `frontend/docs/development.md`

外部来源（External sources）:
- 如果 API 或路由行为不明确，查询框架官方文档。

用户约束（User constraints）:
- 使用 Chrome DevTools MCP 做前端自我验证。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 现有接口已经负责条目筛选 | read | `backend/api/items.go` | 支持扩展现有接口 |
| 前端筛选控件已有相邻模式 | read | `frontend/src/pages/Items.tsx` | 支持复用现有交互 |
| 浏览器验证工具必须使用 Chrome DevTools MCP | external | 用户约束 | 决定前端验证证据 |

## 候选方案（Options）

### 方案 A：扩展现有接口（Add Filter To Existing Endpoint）

- 做法（How）: 扩展当前查询参数解析逻辑。
- 优点（Pros）: API 表面最小。
- 缺点（Cons）: 现有接口职责略微变宽。
- 风险（Risks）: 查询兼容性。
- 验证（Validation）: 后端单元测试和 API smoke。
- 回滚（Rollback）: 移除解析分支和前端控件。

### 方案 B：新增专用接口（Add Dedicated Endpoint）

- 做法（How）: 为筛选结果创建新接口。
- 优点（Pros）: 行为隔离。
- 缺点（Cons）: 增加路由和文档维护。
- 风险（Risks）: 维护成本更高。
- 验证（Validation）: 新接口测试和前端集成验证。
- 回滚（Rollback）: 移除接口和客户端调用。

## 决策（Decision）

选择方案（Chosen option）:
方案 A。

原因（Why）:
现有接口已经负责条目筛选，因此该方案改动最小。

方案变更触发条件（Reapproval triggers）:
- 如果后端筛选需要新增接口或改变认证逻辑，重新请求批准。
- 如果 Chrome DevTools MCP 不可用，记录替代验证并请求用户确认。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | `backend/api/items.go` | 查询兼容性 | 单元测试和 API smoke | 接口说明 |
| 数据结构（Data model） | no |  |  |  |  |
| 前端交互（Frontend interaction） | yes | `frontend/src/pages/Items.tsx` | 控件状态和请求参数 | Chrome DevTools MCP | 无 |
| 配置/环境（Config/environment） | no |  |  |  |  |
| 兼容性（Compatibility） | yes | API 查询参数 | 旧客户端行为 | 旧参数回归测试 | 接口说明 |
| 测试（Tests） | yes | `backend/api/items_test.go` | 覆盖不足 | 单元测试和 smoke | 无 |
| 文档（Documentation） | yes | API docs | 文档滞后 | 文档 diff review | 接口说明 |

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：后端筛选支持

目标（Goal）:
- API 接受新的筛选项。

做法（How）:
- 更新解析器和 handler。
- 增加单元测试。

原因（Why）:
- 前端使用前必须先有后端契约。

位置（Where）:
- `backend/api/items.go`
- `backend/api/items_test.go`

参考来源（References）:
- 本地 handler 和现有测试。

验证（Validation）:
- 运行后端单元测试。

风险和回滚（Risks and rollback）:
- 如果兼容性破坏，回滚解析分支。

阶段契约（Stage Contract）:
- 范围（Scope）: 后端查询参数解析和 handler 支持。
- 允许修改（Allowed changes）: `backend/api/items.go`、`backend/api/items_test.go`。
- 禁止修改（Forbidden changes）: 认证、数据库 schema、前端页面。
- 进入条件（Entry checks）: 工作区干净，当前分支为 `harness/feature`，后端测试命令可用。
- 退出条件（Exit checks）: 后端单元测试通过，API smoke 结果已记录。
- 必需验证（Required validation）: 后端单元测试和 API smoke。
- 是否预期提交（Commit expected）: 是。

### 阶段 2（Stage 2）：前端控件

目标（Goal）:
- 用户可以选择新的筛选项。

做法（How）:
- 增加 UI 控件和请求参数。

原因（Why）:
- 暴露已批准的后端行为。

位置（Where）:
- `frontend/src/pages/Items.tsx`

参考来源（References）:
- 现有筛选控件。

验证（Validation）:
- 运行前端检查，并使用 Chrome DevTools MCP 验证。

风险和回滚（Risks and rollback）:
- 回滚 UI 控件和请求参数。

阶段契约（Stage Contract）:
- 范围（Scope）: 前端筛选控件和请求参数。
- 允许修改（Allowed changes）: `frontend/src/pages/Items.tsx`。
- 禁止修改（Forbidden changes）: 后端接口契约、全局样式重构。
- 进入条件（Entry checks）: Stage 1 已提交，前端依赖和 dev server 命令可用。
- 退出条件（Exit checks）: 前端检查通过，Chrome DevTools MCP 验证记录完成。
- 必需验证（Required validation）: 前端检查、浏览器 console/network 和截图。
- 是否预期提交（Commit expected）: 是。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:
- `.harness/environment.md`

## Git 上下文（Git Context）

主分支（Main branch）:
- dev

任务类型（Task type）:
- feature

工作分支（Working branch）:
- harness/feature

分支动作（Branch action）:
- reuse

同步来源（Sync source）:
- origin/dev

最近同步（Last sync）:
- 方案批准后、实施前同步。

分支占用（Branch occupancy）:
- `git log dev..HEAD`: 无无关提交。
- `git diff dev...HEAD --name-only`: 仅包含预期的后端和前端文件。
- 现有提交属于本任务（Existing commits belong to this task）: 是。

提交策略（Commit policy）:
- 已授权阶段提交。

分支收口（Branch closure）:
- 已合回主分支（Merged to main branch）: 否。
- 未合回时代码停留在（If not merged, code remains on）: `harness/feature`。
- 合并前需要用户确认（User confirmation needed before merge）: 是。

分支安全（Branch safety）:
- 切换前检查工作区。
- 不自动 stash、rebase、reset 或删除分支。

热修复插入（Hotfix interruption）:
- 如果切到 `harness/fix`，先询问是否要把 `harness/feature` 合并进 `dev`。

## 就绪门禁（Readiness Gate）

就绪结论（Readiness result）:
- pass

最终交付证据计划（Final delivery evidence planned）:
- 后端单元测试输出。
- API smoke 结果。
- Chrome DevTools MCP 截图和 console/network 摘要。

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pass | `Evidence levels` 已记录 |
| 影响面矩阵完整（Impact matrix complete） | pass | API、前端、兼容性、测试和文档已标记 |
| 候选方案比较充分（Options compared enough） | pass | 已比较扩展现有接口和新增专用接口 |
| 每阶段可独立验证（Stages independently verifiable） | pass | 后端单测和前端 MCP 验证分阶段执行 |
| 方案变更触发条件清楚（Reapproval triggers clear） | pass | `Reapproval triggers` 已记录 |
| 用户批准摘要可记录（Approval summary ready） | pass | `Plan Approval` 已记录批准范围 |

## 方案批准（Plan Approval）

状态（Status）:
- approved

批准记录（Approval record）:
- 用户说：“按方案执行。”

批准摘要（Approval summary）:
- 批准范围（Approved scope）: 扩展现有筛选接口并增加前端控件。
- 阶段提交授权（Stage commit authorization）: 已授权。
- 工具/MCP 授权（Tool/MCP authorization）: 使用 Chrome DevTools MCP。
- 文档更新授权（Documentation authorization）: 更新接口说明。

提交策略（Commit policy）:
- 已授权阶段提交。

## 验证（Validation）

必需验证（Required）:
- 后端单元测试。
- 前端检查。
- Chrome DevTools MCP 浏览器验证。

已执行（Executed）:
- 命令/工具（Command/tool）: 后端单元测试
- 结果（Result）: pending
- 证据（Evidence）: Stage 1 后记录测试输出
- 覆盖范围（Covers）: 后端筛选解析器和 handler
- 未覆盖（Not covered）: 浏览器行为

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | 后端单元测试 | pending | 查询参数解析和 handler | 前端行为 | Stage 1 后记录命令输出 | 失败则修复并重跑 |
| Stage 2 | Chrome DevTools MCP | pending | 页面交互、console、network | 跨浏览器 | 截图和 console/network 摘要 | 失败则修复并重验 |

产物（Artifacts）:
- 截图（Screenshot）: `.harness/tasks/2026-06-10/example-filter/artifacts/stage-2-items-page.png`
- 日志（Log）: `Implementation Progress` 中的 console/network 摘要
- Trace:
- 报告（Report）:

未覆盖（Not covered）:
- 配置验证工具之外的跨浏览器行为。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Stage 1 | pending | 后端筛选支持 | 后端单元测试 | 测试输出 | 开始实施 |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- |
| Stage 1 | pass，`harness/feature` 且工作区干净 | pass，无遗留 | pass，后端测试命令已确认 | pass，仅后端范围 | pass |
| Stage 2 | pending | pending | pending | pending | pending |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | pending | pending | pending | pending | pending | pending |

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Stage 1 | API 查询兼容性需要回归旧参数 | major | 在单元测试中覆盖旧参数 |
| Stage 2 | 控件文案可能过长 | minor | 浏览器验证时检查移动端宽度 |

## 恢复摘要（Resume Summary）

- 当前阶段（Current stage）: Stage 1 待开始。
- 已完成（Completed）: 方案、Git Context、验证策略和门禁已记录。
- 最新 commit（Latest commit）: 无。
- 下一步（Next action）: 实现后端筛选支持。
- 未覆盖/风险（Not covered/risks）: 浏览器行为等待 Stage 2 验证。

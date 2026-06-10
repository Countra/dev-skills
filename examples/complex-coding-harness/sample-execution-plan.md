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

## 方案批准（Plan Approval）

状态（Status）:
- approved

批准记录（Approval record）:
- 用户说：“按方案执行。”

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

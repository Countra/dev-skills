# 临时决策单（Pending Decisions）

请在 `USER INPUT` 区域内填写你的决定。你也可以不编辑文件，直接在会话中回复选项或自定义内容。

## D-001：前端验证工具

状态（Status）:
open

上下文（Context）:
该任务包含页面交互变更，需要确认浏览器自检工具。

证据（Evidence）:
- `frontend/docs/development.md` 要求使用浏览器验证。

选项（Options）:
- A（recommended）：使用 Chrome DevTools MCP。
- B：使用项目 Playwright 测试。
- C：仅运行构建和单元测试，并在最终交付说明未做浏览器实测。
- Custom：填写你的具体要求。

影响（Impact）:
决定前端交互验证证据和最终声明边界。

合并目标（Merge target）:
`execution-plan.md` / `Tooling` and `Validation`

>>> 📝 USER INPUT: D-001 >>>
Decision:

<<< END <<<

## 已关闭决策（Closed Decisions）

- 

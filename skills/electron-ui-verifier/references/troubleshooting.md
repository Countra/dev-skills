# 故障排查

## CDP Endpoint 不可达

检查应用是否以 `--remote-debugging-port=<port>` 启动，并确认端口监听在 `127.0.0.1`。

Electron GUI 应用本体使用普通终端命令启动，或要求用户启动；不要使用 `process-manager`。`process-manager` 只用于后端 API、dev server、worker、watcher 等非 GUI 伴随服务。如果 GUI 应用由用户手动启动，未经允许不要 kill 或重启。

## Playwright Attach 失败

旧 Electron 版本可能暴露 CDP，但拒绝 Playwright browser context 操作。记录 Playwright 错误并回退到 raw CDP。除非 raw CDP 也无法验证请求的 workflow，否则这不算 UI 失败。

## Playwright MCP 失败

MCP 可能能连接，但在 snapshot 或 browser context 初始化时失败。记录失败的 tool call，并继续使用 verifier server 的 `ev_*` 脚本执行 raw CDP 验证。

## 多个 Target

如果 probe 显示多个 page targets，在 workflow 中加入 `targetUrlContains`、`targetTitleContains` 或 `targetIndex`。不要猜哪个窗口是产品 UI。

## Verifier Server 不可用

先运行 `ev_doctor.py`。如果 server 离线，按 `references/server.md` 的流程使用 process-manager 启动或 ready，不要手写后台命令。

## Session 失效

server 进程退出后 session 不会恢复。使用 `ev_sessions.py --session <name>` 检查；失效时重新运行 `ev_attach.py`。

## 后端加载页

如果 UI 停留在“正在启动”等加载文本，检查应用后端是否就绪。如果产品 UI 一直不可用，应记录为环境 readiness 失败。

## 原生对话框

系统文件对话框、UAC 提示、托盘菜单和非 Electron 窗口不属于 v1 范围。使用 Appium 或 WinAppDriver 前，应先制定单独的 Windows 原生自动化方案。

## 截图为空

检查 target 选择、窗口可见性、device scale，以及页面是否已经渲染。runner 应记录截图大小；可行时，在声称有视觉证据前验证非空白像素。

## 敏感数据

除非用户明确要求，不要导出 cookies、tokens、localStorage、请求头或大范围页面数据。artifact 默认保存在已忽略目录中。

## Console 或 Network 事件缺失

`collectConsole` 和 `collectExceptions` 依赖 CDP `Runtime` event。`collectNetwork` 依赖 CDP `Network` event，并且必须在请求发生前启用。runner 会预扫描 workflow，只要存在 `collectNetwork` 就在 readiness 前启用 `Network.enable`。如果仍然缺失，检查 action 是否放在了目标页面加载之后很久才运行，或目标请求是否发生在其它 target/window 中。

## DOMSnapshot 不支持

旧 Electron/Chromium 可能不支持 `DOMSnapshot.captureSnapshot` 或部分参数。必需 step 会失败；如果它只是辅助证据，给该 step 设置 `continueOnFailure: true`。不要把 JS `snapshot` 伪装成等价的完整 DOMSnapshot。

## Accessibility Tree 不支持

`Accessibility.getFullAXTree` 在不同 CDP 版本中支持度可能不同。作为辅助证据时建议设置 `continueOnFailure: true`。如果任务要求严格检查可访问性，应把该 step 作为必需验证，并在失败时记录 CDP 版本。

## Evaluate 结果过大

大数组、大对象或整页文本不应完整塞进 `report.json`。使用 `maxInlineChars`、`artifact` 或默认 artifact 策略，把完整结果写入运行产物目录。需要复用结果时使用 `saveAs` 写入 `namedResults`。

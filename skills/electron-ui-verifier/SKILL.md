---
name: electron-ui-verifier
description: 验证 Electron 桌面应用 UI 流程，支持截图、DOM/文本/表格抽取、console/异常/网络诊断、Chrome DevTools Protocol 探测、可用时接入 Playwright 或 MCP，并输出结构化证据报告。适用于 Codex 需要检查打包 Electron exe 或开发版 Electron 应用、点击 UI 流程、收集截图、验证可见内容、分析任务列表/工具箱、采集页面诊断信息，或生成可复现 GUI 验证证据的场景。
---

# Electron UI Verifier

使用本 skill 验证 Electron 桌面应用 UI 行为，并生成可审计证据。任务涉及打包 `.exe`、`--remote-debugging-port`、Playwright/MCP attach、截图、UI 文本抽取、表格抽取、console/异常/网络诊断或可重复桌面工作流验证时，优先使用本 skill，而不是临时写一次性脚本。

## 必须流程

1. 启动、连接或验证 Electron 应用前，先读取 `references/workflow.md`。
2. 打包 Electron GUI 应用本体用用户要求的普通终端命令启动，或连接用户已启动的应用；不要用 `process-manager` 托管 Electron GUI 应用本体。
3. 先用 `scripts/electron_verify.py probe` 探测目标。只有 probe 选出唯一 target，或 workflow 明确指定 target 选择规则后，才能点击或输入。
4. 使用 workflow JSON 或窄范围 one-shot 命令执行验证。证据产物放到当前 harness 任务的 `artifacts/` 目录，或其它已忽略的运行时目录。
5. 汇报实际使用的 backend、fallback 原因、截图、抽取内容和未覆盖范围。没有证据产物时，不得声称真实 UI 验证通过。

## 驱动顺序

按当前应用可用性选择最高可靠 backend：

1. 开发版或源码 Electron 应用优先用 Playwright Electron。
2. 兼容的打包应用使用 Playwright CDP。
3. 环境明确要求 MCP UI 工具时使用 Playwright MCP。
4. 旧 Electron 或 Playwright/MCP attach 失败时，通过 `electron_verify.py` 使用 raw CDP fallback。

每一次 fallback 原因都必须写入 `report.json` 和 harness 验证证据。

## 硬规则

- 可执行程序路径、工作目录、workflow 文件和输出目录必须使用绝对路径。
- 打包 Electron GUI 应用是特殊场景：直接用普通终端启动；需要提权时让用户启动。Electron GUI 应用本体不使用 `process-manager`。
- 后端 API、dev server、worker、watcher 等非 GUI 伴随长期进程，如果需要持续运行，仍按 workspace harness/process-manager 规则管理。
- 默认只连接本机 CDP endpoint。远程 endpoint 需要用户明确批准，并记录原因。
- 存在多个 Electron target 时不要猜测。必须提供 target 选择规则，或停止并输出候选列表。
- 除非用户明确要求，不导出 cookie、token、localStorage、请求头或大段敏感文本。
- 新验证任务不要使用 Spectron。
- Windows 原生对话框、UAC、托盘菜单和非 Electron 窗口不属于 v1 范围，除非单独批准。

## 资源

- `scripts/electron_verify.py`：用于 probe、workflow 执行、截图、抽取和报告生成的 CLI runner。
- `references/workflow.md`：规划、backend 选择、Electron GUI 启动规则和证据规则。
- `references/actions.md`：workflow JSON actions、诊断采集和示例。
- `references/troubleshooting.md`：常见失败和恢复规则。
- `assets/workflow.example.json`：最小 workflow 模板。
- `assets/diagnostics.workflow.example.json`：诊断采集 workflow 模板。

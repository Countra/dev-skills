---
name: electron-ui-verifier
description: 通过常驻 verifier server 验证 Electron 桌面应用 UI，支持 attach 到 Chrome DevTools Protocol、复用 session、点击/输入/截图、DOM/文本/表格抽取、console/异常/网络诊断、DOMSnapshot、accessibility 和结构化报告。适用于 Codex 需要检查打包 Electron exe 或开发版 Electron 应用、连续分析同一页面状态、验证任务列表/工具箱/业务流程，或生成可复现 GUI 验证证据的场景。
---

# Electron UI Verifier

使用本 skill 验证 Electron 桌面应用 UI 行为，并生成可审计证据。所有 UI 操作必须通过常驻 verifier server 和 `scripts/ev_*.py` 小脚本完成；不要临时恢复旧的一次性 runner。

## 必须流程

1. 启动、连接或验证 Electron 应用前，先读取 `references/server.md`、`references/workflow.md` 和 `references/knowledge.md`。
2. 打包 Electron GUI 应用本体用普通终端命令启动，或连接用户已启动的应用；不要用 `process-manager` 托管 Electron GUI 应用本体。
3. verifier server 是长期后台服务，必须由 `process-manager` 托管；先运行 `ev_init.py` 检查目标 Python 依赖并生成环境和 service，再用 `pm_*` 脚本启动、ready 和停止。
4. verifier server 使用的 Python 解释器从 `.harness/electron-ui-verifier/environment.json` 读取；用户口头指定新解释器时，必须立即持久化写入该文件。
5. 先用 `ev_probe.py` 探测目标，再用 `ev_attach.py` 创建稳定 session；只有 target 唯一或明确指定 target 选择规则后，才能点击或输入。
6. 后续所有单步操作、workflow、截图、诊断和报告读取都复用同一 session，通过 `ev_action.py`、`ev_workflow.py`、`ev_snapshot.py` 等入口执行。
7. 每轮 UI 验证都必须先执行知识库预检：用 `ev_suggest.py`、`ev_knowledge.py` 或 `ev_assets.py` 查询同一 appId/目标下的历史 workflow、action、元素和页面经验；命中内容只能作为候选路径，不能替代现场验证。
8. 现场验证必须复用稳定 session，通过 `ev_action.py` 或 `ev_workflow.py` 执行本轮实际操作，并产出本次实际使用的 workflow JSON 文件；脚本会自动把它固化到 `.harness/electron-ui-verifier/workflows/`。
9. 现场验证后必须回写知识库：基础页面、元素、report、workflowPath 和 evidence 应沉淀为候选知识；只有显式使用 `--include-assets` 或 `--learn-assets` 时才写入 action/workflow 资产。
10. 本 skill 自己生成和托管的内部运行文件必须位于 `.harness/electron-ui-verifier/` 下，包括 environment、config、token、server、sessions、reports、workflows、artifacts、logs、tmp 和 knowledge；不要自行写到其它 `.harness` 子目录、项目根目录、`skills/` 目录或临时目录。
11. 最终回复必须汇报知识库预检命中情况、实际使用或跳过的候选、回写结果、session、target、workflow JSON 路径、截图、抽取内容、report 路径、artifact 路径和未覆盖范围。没有证据产物时，不得声称真实 UI 验证通过。

## 硬规则

- 可执行程序路径、工作目录、workflow 文件、action 文件和 config 路径必须使用绝对路径。
- 使用前必须通过 `ev_init.py` 或 `ev_check_env.py` 检查 verifier server 的目标 Python。依赖不完整时必须阻塞任务，向用户报告缺失库和安装命令，不得继续启动 server 或执行 UI 验证。
- Electron GUI 应用本体不使用 `process-manager`；只有 verifier server 使用 `process-manager`。
- agent 不直接调用 verifier server HTTP API；只调用 `ev_*` 小脚本。
- 本 skill 内部产物的固定根目录是 `.harness/electron-ui-verifier/`。除 process-manager service 文件和用户明确指定的导出文件外，不得生成或改用其它内部产物目录。
- 最终回复必须包含本次 UI 验证实际执行的 workflow JSON 绝对路径；如果执行失败但已生成 workflow，也必须给出该路径。
- 最终回复必须包含知识库预检和回写摘要；若因阻塞原因未能查询或回写，必须说明原因、影响和替代证据。
- 默认只连接本机 CDP endpoint。远程 endpoint 需要用户明确批准，并记录原因。
- 存在多个 Electron target 时不要猜测。必须提供 target 选择规则，或停止并输出候选列表。
- 除非用户明确要求，不导出 cookie、token、localStorage、请求头或大段敏感文本。
- 知识库建议只能作为候选路径，不能替代真实 UI 验证结果；提升到 `verified` 或 `stable` 必须带 evidence 或用户确认。
- 新验证任务不要使用 Spectron。
- Windows 原生对话框、UAC、托盘菜单和非 Electron 窗口不属于 v1 范围，除非单独批准。

## 常用入口

- `scripts/ev_init.py`: 初始化 `.harness/electron-ui-verifier/` 和 process-manager service。
- `scripts/ev_check_env.py`: 检查目标 Python 版本和 `requirements.txt` 中的必要依赖。
- `scripts/ev_health.py`: 检查 verifier server 健康。
- `scripts/ev_probe.py`: 通过 server 探测 CDP targets。
- `scripts/ev_attach.py`: attach 到 target 并创建/复用 session。
- `scripts/ev_sessions.py`: 列出 session 或检查连接状态。
- `scripts/ev_action.py`: 执行单个 action JSON。
- `scripts/ev_workflow.py`: 在 session 内执行 workflow JSON。
- `scripts/ev_snapshot.py`、`ev_screenshot.py`、`ev_console.py`、`ev_exceptions.py`、`ev_network.py`: 常用快捷入口。
- `scripts/ev_report.py`、`ev_artifact.py`、`ev_doctor.py`: 报告、artifact 和诊断入口。
- `scripts/ev_learn.py`: 从 report 显式学习候选知识，`--include-assets` 才写 action/workflow 资产。
- `scripts/ev_assets.py`、`ev_export_workflow.py`: 查询维护 action/workflow 资产并导出可分享 workflow。
- `scripts/ev_knowledge.py`、`ev_suggest.py`、`ev_promote.py`: 查询知识、生成候选建议和提升知识状态。

## 资源

- `references/server.md`：server 生命周期、process-manager 托管、环境文件和 session 规则。
- `references/workflow.md`：验证规划、Electron GUI 启动规则、target/session 选择和证据规则。
- `references/actions.md`：workflow/action JSON、诊断采集和示例。
- `references/knowledge.md`：知识库学习、查询、建议、提升和清理规则。
- `references/troubleshooting.md`：常见失败和恢复规则。
- `assets/workflow.example.json`：最小 workflow 模板。
- `assets/diagnostics.workflow.example.json`：诊断采集 workflow 模板。
- `assets/knowledge.workflow.example.json`：显式学习候选知识的 workflow 模板。
- `assets/exported-asset.workflow.example.json`：从资产导出的可分享 workflow 示例。

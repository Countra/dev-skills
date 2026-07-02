# Electron UI Verifier 工作流

## 目的

使用本工作流检查和验证 Electron 桌面应用，并产出可复现证据。主要目标是连接暴露 Chrome DevTools Protocol（CDP）的打包 Electron `.exe` 和开发版 Electron 应用，并通过 verifier server 复用同一 UI session。

## 前置检查

1. 读取当前 harness 任务计划和环境规则。
2. 确认应用是否已经运行。
3. 确认 CDP endpoint，通常是 `http://127.0.0.1:<port>`。
4. 确认证据产物保存位置。
5. 确认 Electron GUI 应用由 agent 启动，还是由用户手动启动。
6. 如果任务可能复用历史经验，先查询 `references/knowledge.md` 中的知识库入口；查询结果只作为候选操作路径。

`python -m py_compile`、`--help`、JSON 解析、报告检查等会立即返回的有限命令不使用 `process-manager`。
verifier server 是长期后台服务，必须用 `process-manager` 管理；Electron GUI 应用本体不要用 `process-manager`。

## 启动或连接

优先连接用户已经启动的应用。打包 Electron GUI 应用是特殊场景：GUI 应用本体不要使用 `process-manager`。用用户要求的普通终端命令启动；如果需要提权、桌面交互、许可证或用户配置文件访问，则让用户手动启动。

只对必须持续运行的非 GUI 伴随进程使用 `process-manager`，例如后端 API、dev server、worker、watcher 或模型服务。不要用它托管正在被可视化验证的 Electron 窗口进程。

打包应用通常需要远程调试参数：

```powershell
D:\App\App.exe --remote-debugging-port=9223
```

需要提权的应用，应让用户在提权终端中运行命令，然后再连接对应 CDP endpoint。

如果应用依赖后端服务，应单独验证后端 readiness。如果 UI 因后端不可用停留在加载页，应记录为环境就绪失败，而不是 UI 验证通过。

## Backend 选择

按以下顺序选择：

1. 开发版或源码应用使用 Playwright Electron。
2. 兼容的打包应用使用 Playwright CDP。
3. 环境明确要求 MCP UI 工具时使用 Playwright MCP。
4. verifier server 内部使用 raw CDP 执行最终操作；agent 仍只调用 `ev_*` 脚本。

始终记录：

- 尝试过的 backend。
- 实际选择的 backend。
- 每个跳过或失败 backend 的原因。
- 可用时记录 CDP version、browser version、target title、target URL 和 target id。

## Target 选择

Electron 可能暴露多个 target。必须先运行 probe：

```powershell
python skills/electron-ui-verifier/scripts/ev_probe.py --workspace E:/work/hl/videoForensic/AI/dev-skills --cdp http://127.0.0.1:9223
```

如果存在多个 page target，必须指定以下规则之一：

- `targetUrlContains`
- `targetTitleContains`
- `targetIndex`
- `targetType`

不要猜测。如果 target 选择有歧义，停止并报告候选项。

## 安全边界

- 默认使用 `127.0.0.1` 或 `localhost` endpoint。
- 远程 CDP endpoint 必须经过用户明确批准。
- 默认不导出 cookie、token、localStorage、请求头或大段敏感 payload。
- 除非用户要求提交，否则 artifact 保存在已忽略的运行时目录。

## 证据

每次真实 UI 验证都应产出：

- `report.json`
- `summary.md`
- 至少一张截图，或明确说明截图不可用的原因。
- 与用户请求相关的 snapshot 或抽取文本。
- 如任务涉及错误分析，补充 console、exception、network、DOMSnapshot 或 accessibility artifact。

`report.json` 必须包含 `schemaVersion: 1`、session、backend 信息、target metadata、step-level statuses、artifacts 和 errors。

诊断类 action 的完整数据默认写入 artifact，报告中只保留摘要。`collectNetwork` 会在 workflow 开始前预扫描并提前启用 CDP `Network` domain，避免点击后才采集导致漏请求。默认不采集请求头、请求体、响应体、cookie、token 或 localStorage。

`evaluate` 支持 `saveAs` 写入顶层 `namedResults`。长结果默认写 artifact，避免 `report.json` 过大。

`summary.md` 必须区分：

- `passed`
- `failed`
- `skipped`
- `not covered`

如果应用不可达、target 有歧义，或所有 driver backend 都失败，不得声称验证通过。

## Server Workflow

典型顺序：

```powershell
python skills/electron-ui-verifier/scripts/ev_init.py --workspace E:/work/hl/videoForensic/AI/dev-skills --python F:/env/anaconda/python.exe
python skills/process-manager/scripts/pm_validate.py --service E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/services/electron-ui-verifier.json
python skills/process-manager/scripts/pm_start.py --service E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/services/electron-ui-verifier.json
python skills/process-manager/scripts/pm_ready.py --service electron-ui-verifier
python skills/electron-ui-verifier/scripts/ev_attach.py --workspace E:/work/hl/videoForensic/AI/dev-skills --name app --cdp http://127.0.0.1:9223 --target-index 0
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session app --workflow E:/work/task/workflow.json
```

workflow JSON 不再负责创建 CDP 连接；它只描述 readiness 和 steps。CDP endpoint 与 target 选择在 `ev_probe.py` 和 `ev_attach.py` 阶段完成。

## 知识库复用

执行前可以先搜索或生成建议：

```powershell
python skills/electron-ui-verifier/scripts/ev_suggest.py --workspace E:/work/hl/videoForensic/AI/dev-skills --app-id videoForensic --goal "打开第二个案件并统计数据"
```

建议命中的 workflow、action 或元素必须通过新的 action/workflow 验证。执行后如果要沉淀本次结果，显式加 `--learn`：

```powershell
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session app --workflow E:/work/task/workflow.json --learn --learn-app-id videoForensic --learn-notes "案件统计流程"
```

如果本次流程要沉淀为可检索、可导出、可分享的 action/workflow 资产，必须再加 `--learn-assets`。不要默认资产化一次性探索。

```powershell
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session app --workflow E:/work/task/workflow.json --learn --learn-assets --learn-app-id videoForensic --learn-notes "案件统计流程"
```

不要把知识库建议直接写成最终结论；最终结论必须引用本轮 report、artifact 或截图证据。

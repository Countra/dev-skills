# Electron UI Verifier 工作流

## 目的

使用本工作流检查和验证 Electron 桌面应用，并产出可复现证据。主要目标是连接暴露 Chrome DevTools Protocol（CDP）的打包 Electron `.exe` 和开发版 Electron 应用，并通过 verifier server 复用同一 UI session。

## 前置检查

1. 读取当前 harness 任务计划和环境规则。
2. 确认应用是否已经运行。
3. 确认 CDP endpoint，通常是 `http://127.0.0.1:<port>`。
4. 确认证据产物保存位置。内部 report、pending、workflow、artifact、log、tmp 和 knowledge 必须位于 `.harness/electron-ui-verifier/` 下。
5. 确认 Electron GUI 应用由 agent 启动，还是由用户手动启动。
6. 每轮 UI 验证都必须执行 Knowledge-First + Progressive Reuse Gate + Reuse Gate + Confirmed Persistence Gate：先查询知识库和资产，完整目标没有直达命中时继续拆解子目标检索，命中可执行资产时原地复用，再现场验证和纠偏，生成 pending 审核包，用户确认后才持久化 workflow 和写入知识库。

`python -m py_compile`、`--help`、JSON 解析、报告检查等会立即返回的有限命令不使用 `process-manager`。
verifier server 是长期后台服务，必须用 `process-manager` 管理；Electron GUI 应用本体不要用 `process-manager`。

## Knowledge-First + Progressive Reuse Gate + Reuse Gate + Confirmed Persistence Gate

每轮本地 UI 验证必须按以下顺序执行，不能只做现场探索：

1. **知识库预检**：根据 appId 和用户目标运行 `ev_suggest.py`，必要时补充 `ev_knowledge.py search` 或 `ev_assets.py search/list-workflows/list-actions`。
2. **Progressive Reuse Gate**：完整目标没有命中直达 workflow/action 时，必须拆解用户目标并继续检索子目标。拆解优先级为入口动作、页面或标签页、前置步骤、目标对象、最终断言。例如“检查苍穹AI局域网连接状态”应先查“打开设置”，再查“AI设置”，再查“苍穹AI局域网”和“连接状态”。
3. **命中判断**：记录完整目标和每个子目标命中的 workflow、action、元素、页面和状态；`stable`、`verified` 可优先尝试，`candidate`、`observed` 只能作为低置信候选。
4. **资产复用门禁**：命中可执行 workflow asset 时优先运行 `ev_workflow.py --workflow-id <id>`；命中可执行 action asset 时优先运行 `ev_action.py --action-id <id>`；命中已批准 workflow 文件时直接使用原文件。不得为等价流程导出、复制或手写新的 JSON。
5. **降级探索条件**：只有完整目标和子目标命中均为空、资产不可执行、风险过高、目标不匹配、页面状态不满足或现场复验失败时，才允许生成新的 action/workflow。必须记录跳过资产的原因。
6. **现场验证和偏离检测**：无论复用资产还是新建 workflow，都必须实际执行本轮 UI 操作并生成 report、截图或抽取 artifact。执行中持续检查页面、URL、标题、关键文本和用户目标是否匹配。
7. **错误路径纠偏**：进入错误页面、点击无关功能、找不到目标入口或页面内容与目标不符时，必须标记 detour，并通过返回、关闭误开页面、回到首页、重新 snapshot 或重新 attach 等方式继续寻找正确路径。
8. **生成 pending 审核包**：任务完成后清洗出正确路径，生成 `workflow.proposed.json`、`workflow-review.md`、`evidence-index.json`，必要时生成 `detours.json`。清洗后的 workflow 不能包含错误页面、无关功能、重复尝试或 recovery-only 步骤。
9. **用户确认后持久化**：只有用户明确确认流程正确后，才能运行 `ev_persist.py approve` 保存正式 workflow 并写入知识库；拒绝或需要修改时，不得写入知识库。
10. **最终说明**：最终回复必须写明预检是否命中、渐进式子目标命中情况、复用了哪些 workflow/action asset ID 或已批准 workflow 文件、哪些候选被跳过及原因、是否新生成文件和原因、本次步骤链路、现场证据路径、pending 或正式 workflow 路径、是否已持久化、已排除的弯路和未覆盖范围。

知识库建议不能作为最终业务结论。最终结论必须引用本轮现场 UI 验证产生的 `report.json`、artifact、截图或 pending 审核包。未获用户确认前，pending workflow 不是长期可复用资产。

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
- 本 skill 的内部运行产物只写入 `.harness/electron-ui-verifier/`。不要为单次验证另建 `.harness/electron-*`、`.tmp` 或项目根目录下的内部产物目录。

## 证据

每次真实 UI 验证都应产出：

- `report.json`
- `summary.md`
- `pending/<session>/<run-id>/workflow.proposed.json`
- `pending/<session>/<run-id>/workflow-review.md`
- `pending/<session>/<run-id>/evidence-index.json`
- 至少一张截图，或明确说明截图不可用的原因。
- 与用户请求相关的 snapshot 或抽取文本。
- 如任务涉及错误分析，补充 console、exception、network、DOMSnapshot 或 accessibility artifact。

`report.json` 必须包含 `schemaVersion: 1`、session、backend 信息、target metadata、step-level statuses、artifacts 和 errors。

`ev_action.py` 和 `ev_workflow.py` 每轮默认只生成 pending 审核包，不固化为正式 workflow：

```text
.harness/electron-ui-verifier/pending/<session>/<timestamp>-<type>/
```

pending 包内的 `workflow.proposed.json` 是清洗后的正确路径，不能包含 detour。`detours.json` 只保留探索弯路审计，不得被 promote 为正式 workflow。最终回复必须列出 pending 包绝对路径；只有用户确认后，才列出正式 workflow JSON 绝对路径。

`workflow-review.md` 和 `evidence-index.json` 必须包含可读的步骤链路摘要，便于用户在会话中确认是否允许持久化。例如：

```text
首页 -> 设置 -> AI设置 -> 选择苍穹AI局域网 -> 读取连接状态和配置
```

最终回复必须复述这条步骤链路，并明确询问用户是否确认将本次正确路径保存为正式 workflow 并写入知识库。用户未确认前，不得运行 `ev_persist.py approve`。

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
python skills/process-manager/scripts/pm_init.py --workspace E:/work/hl/videoForensic/AI/dev-skills
python skills/process-manager/scripts/pm_manager.py status --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json
python skills/process-manager/scripts/pm_manager.py start --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json
python skills/process-manager/scripts/pm_validate.py --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json --service E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/services/electron-ui-verifier.json
python skills/process-manager/scripts/pm_start.py --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json --service E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/services/electron-ui-verifier.json
python skills/process-manager/scripts/pm_ready.py --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json --process-key <pm_start 返回的 processKey>
python skills/electron-ui-verifier/scripts/ev_attach.py --workspace E:/work/hl/videoForensic/AI/dev-skills --name app --cdp http://127.0.0.1:9223 --target-index 0
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session app --workflow E:/work/task/workflow.json
# 如知识库已命中可执行 workflow asset，应直接按 ID 复用，不要导出或复制等价文件。
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session app --workflow-id workflow-example
```

`pm_init.py` 只在 manager config 不存在时执行，`pm_manager.py start` 只在 status 返回 `manager_offline` 时执行。普通流程不读取平台/backend，也不先运行 process-manager doctor；统一命令失败且选择原因不清楚时才按需诊断。server stop/restart 必须检查 `cleanupVerified: true` 与 `stopResult.ownerEmpty: true`。

workflow JSON 不再负责创建 CDP 连接；它只描述 readiness 和 steps。CDP endpoint 与 target 选择在 `ev_probe.py` 和 `ev_attach.py` 阶段完成。

## 知识库复用和回写

执行前必须先搜索或生成建议：

```powershell
python skills/electron-ui-verifier/scripts/ev_suggest.py --workspace E:/work/hl/videoForensic/AI/dev-skills --app-id videoForensic --goal "打开第二个案件并统计数据"
```

如果完整目标没有直达命中，必须继续查询 `ev_suggest.py` 输出的 `progressivePlan` 或手工拆出的子目标。建议命中的 workflow、action 或元素必须通过本轮现场验证。命中可执行资产时优先原地复用资产 ID；只有不能复用时才新建 workflow。执行后先生成 pending 审核包，不直接学习：

```powershell
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session app --workflow-id workflow-example --app-id videoForensic --goal "案件统计流程"
python skills/electron-ui-verifier/scripts/ev_action.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session app --action-id action-example --app-id videoForensic --goal "打开设置页"
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session app --workflow E:/work/task/workflow.json --app-id videoForensic --goal "案件统计流程"
```

推荐在执行时同时传入 `--app-id`、`--goal` 和 `--knowledge-preflight`，这样本轮 report 会包含 `knowledgePreflight`、`knowledgeUsage` 和待确认的 `knowledgeWriteback` 审计字段。传入 `--app-id` 或 `--goal` 不会触发自动学习。

通过 `--workflow-id` 或 `--action-id` 执行时，脚本会自动记录 `knowledgeUsage` 和 `workflowSource` / `actionSource`。如果使用新建文件，最终回复必须说明为什么没有复用已有资产。

如果本次流程要沉淀为可检索、可导出、可分享的 action/workflow 资产，必须先让用户确认 pending 审核包，然后使用持久化入口：

```powershell
python skills/electron-ui-verifier/scripts/ev_persist.py --workspace E:/work/hl/videoForensic/AI/dev-skills approve --pending E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/pending/app/20260702-120000-workflow --decision "用户确认案件统计流程正确" --include-assets
```

不要把知识库建议直接写成最终结论；最终结论必须引用本轮 report、artifact 或截图证据。`ev_export_workflow.py` 只用于分享、跨环境复现或用户明确要求导出，不用于普通本地复用。

如果无法执行知识库预检、pending 审核包生成或用户确认后的持久化，必须把失败原因、影响和替代验证写入最终回复。缺少用户确认时，不能把流程描述为已沉淀到知识库。

# UI 知识库

## 目的

知识库用于沉淀 Electron 应用的页面、入口、元素、action/workflow 资产和证据摘要，让后续验证任务可以先查询已有经验，再决定如何操作 UI。

知识库只提供候选建议，不替代真实 UI 验证。任何来自 `observed` 或 `candidate` 状态的知识，都必须通过新的 action/workflow 证据复验后，才能提升到 `verified` 或 `stable`。

每轮 UI 验证都必须使用知识库闭环：

- 执行前查询知识库，优先复用已知入口、页面、元素、action 和 workflow。
- 命中可执行 action/workflow asset 时，优先通过 asset ID 直接执行，不导出、不复制、不手写等价 JSON。
- 执行中只把知识库命中作为候选路径，最终结论仍以本轮 report、artifact 或截图为准。
- 执行后先生成 pending 审核包，等待用户确认是否持久化。
- 用户确认后才回写基础候选知识，包括 app、screen、element、report、approvedWorkflowPath 和 evidence 摘要。
- action/workflow 资产化必须在用户确认后显式开启，避免把一次性探索或错误路径写成长期可复用资产。

## 存储位置

运行时知识保存在 workspace 内：

```text
.harness/electron-ui-verifier/knowledge/
```

核心文件：

- `knowledge.sqlite`：结构化知识和全文索引。
- `manifest.json`：schema、FTS 状态和计数摘要。

该目录是本机运行数据，默认不提交。知识库只保存短摘要、结构化标签、路径引用和指纹，不保存 cookie、token、localStorage、请求头、请求体或响应体。

## 状态流转

- `observed`：从一次 report 中观察到，尚未判断可复用。
- `candidate`：已结构化，可能可复用。
- `verified`：有新的 action/workflow/report 证据支撑。
- `stable`：多次验证或用户确认后可优先建议。
- `stale`：页面、版本或指纹变化后需要复验。
- `deprecated`：已确认不再使用，默认不作为建议。

提升到 `verified` 或 `stable` 必须提供 `--evidence` 或 `--user-confirmed`。

## 学习方式

从已有 report 离线学习必须用于预览或经过用户确认后的持久化流程。默认先预览候选，不写知识库：

```powershell
python skills/electron-ui-verifier/scripts/ev_learn.py --workspace E:/work/hl/videoForensic/AI/dev-skills --report E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/reports/videoForensic/20260701-090815-action/report.json --dry-run
```

先预览候选，不写知识库：

```powershell
python skills/electron-ui-verifier/scripts/ev_learn.py --workspace E:/work/hl/videoForensic/AI/dev-skills --report E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/reports/videoForensic/20260701-090815-action/report.json --dry-run
```

执行 action/workflow 时不得直接学习基础候选知识。执行阶段只生成 pending 审核包：

```powershell
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic --workflow E:/work/task/open-case.workflow.json --app-id videoForensic --goal "打开案件流程复验"
```

用户确认 pending 审核包后，使用 `ev_persist.py approve` 执行正式持久化。基础回写失败不会把 UI 验证本身改成失败，但最终回复必须说明失败原因和影响。

如需把本次 report 整理成 action/workflow 资产，必须在 approve 时显式加 `--include-assets`：

```powershell
python skills/electron-ui-verifier/scripts/ev_persist.py --workspace E:/work/hl/videoForensic/AI/dev-skills approve --pending E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/pending/videoForensic/20260702-120000-workflow --decision "用户确认打开案件流程正确" --include-assets
```

直接从 report 写资产只允许作为已批准 pending 包的内部步骤；普通验证任务不要绕过用户确认：

```powershell
python skills/electron-ui-verifier/scripts/ev_persist.py --workspace E:/work/hl/videoForensic/AI/dev-skills approve --pending E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/pending/videoForensic/20260702-120000-workflow --decision "用户确认首页流程正确" --include-assets
```

## 查询和建议

查看知识库状态：

```powershell
python skills/electron-ui-verifier/scripts/ev_knowledge.py --workspace E:/work/hl/videoForensic/AI/dev-skills meta
```

搜索知识：

```powershell
python skills/electron-ui-verifier/scripts/ev_knowledge.py --workspace E:/work/hl/videoForensic/AI/dev-skills search --app-id videoForensic --query "历史记录 查看"
```

生成候选建议：

```powershell
python skills/electron-ui-verifier/scripts/ev_suggest.py --workspace E:/work/hl/videoForensic/AI/dev-skills --app-id videoForensic --goal "从历史记录打开案件详情"
```

建议输出中的 workflow、action、元素和页面只说明“可以优先尝试什么”，不能直接作为用户问题的最终答案。workflow/action asset 可以作为现场验证的执行输入，但最终答案仍必须来自本轮 report、artifact 或截图。

查询 action/workflow 资产：

```powershell
python skills/electron-ui-verifier/scripts/ev_assets.py --workspace E:/work/hl/videoForensic/AI/dev-skills list-actions --app-id videoForensic --kind clickText
python skills/electron-ui-verifier/scripts/ev_assets.py --workspace E:/work/hl/videoForensic/AI/dev-skills list-workflows --app-id videoForensic --goal "打开案件"
python skills/electron-ui-verifier/scripts/ev_assets.py --workspace E:/work/hl/videoForensic/AI/dev-skills search --app-id videoForensic --query "AI设置 苍穹AI网络版 状态"
```

命中可执行资产后的首选复验方式：

```powershell
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic --workflow-id workflow-example --app-id videoForensic --goal "复验历史流程"
python skills/electron-ui-verifier/scripts/ev_action.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic --action-id action-example --app-id videoForensic --goal "复验单步入口"
```

只有命中为空、资产不可执行、风险过高、目标不匹配或现场复验失败时，才新建 action/workflow。新建原因必须写入最终回复。

导出可分享 workflow：

```powershell
python skills/electron-ui-verifier/scripts/ev_export_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --workflow-id workflow-example --output E:/work/task/open-case.workflow.json --include-metadata
```

导出默认拒绝覆盖已有文件，默认不写本机 report/artifact 绝对路径。只有确实需要本机 evidence 路径时，才显式加 `--include-local-evidence-paths`。普通本地复用不走导出；应直接使用 `--workflow-id`。

## 提升和清理

提升知识状态：

```powershell
python skills/electron-ui-verifier/scripts/ev_promote.py --workspace E:/work/hl/videoForensic/AI/dev-skills --kind workflow --id workflow-e1e35b3b901fa924 --status verified --evidence E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/reports/videoForensic/20260701-090815-action/report.json
```

清理过期或废弃知识：

```powershell
python skills/electron-ui-verifier/scripts/ev_knowledge.py --workspace E:/work/hl/videoForensic/AI/dev-skills cleanup --keep-inactive 200
```

清理只删除 `stale` 和 `deprecated` 中超过保留数量的记录。

资产清理使用：

```powershell
python skills/electron-ui-verifier/scripts/ev_assets.py --workspace E:/work/hl/videoForensic/AI/dev-skills cleanup --keep-inactive 200 --dry-run
```

资产 cleanup 默认不删除 `candidate`、`verified` 和 `stable`。

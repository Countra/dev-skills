# UI 知识库

## 目的

知识库用于沉淀 Electron 应用的页面、入口、元素、action/workflow 资产和证据摘要，让后续验证任务可以先查询已有经验，再决定如何操作 UI。

知识库只提供候选建议，不替代真实 UI 验证。任何来自 `observed` 或 `candidate` 状态的知识，都必须通过新的 action/workflow 证据复验后，才能提升到 `verified` 或 `stable`。

每轮 UI 验证都必须使用知识库闭环：

- 执行前查询知识库，优先复用已知入口、页面、元素、action 和 workflow。
- 执行中只把知识库命中作为候选路径，最终结论仍以本轮 report、artifact 或截图为准。
- 执行后回写基础候选知识，包括 app、screen、element、report、workflowPath 和 evidence 摘要。
- action/workflow 资产化必须显式开启，避免把一次性探索写成长期可复用资产。

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

从已有 report 离线学习：

```powershell
python skills/electron-ui-verifier/scripts/ev_learn.py --workspace E:/work/hl/videoForensic/AI/dev-skills --report E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/reports/videoForensic/20260701-090815-action/report.json --notes "首页 report 学习"
```

先预览候选，不写知识库：

```powershell
python skills/electron-ui-verifier/scripts/ev_learn.py --workspace E:/work/hl/videoForensic/AI/dev-skills --report E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/reports/videoForensic/20260701-090815-action/report.json --dry-run
```

执行 action/workflow 时必须学习基础候选知识：

```powershell
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic --workflow E:/work/task/open-case.workflow.json --learn --learn-app-id videoForensic --learn-notes "打开案件流程复验"
```

`--learn` 只写 app/screen/element/evidence 基础候选，属于每轮验证后的标准回写。基础回写失败不会把 UI 验证本身改成失败，但最终回复必须说明失败原因和影响。

如需把本次 report 整理成 action/workflow 资产，必须显式加 `--learn-assets`：

```powershell
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic --workflow E:/work/task/open-case.workflow.json --learn --learn-assets --learn-app-id videoForensic --learn-notes "打开案件流程复验"
```

离线从 report 写资产使用：

```powershell
python skills/electron-ui-verifier/scripts/ev_learn.py --workspace E:/work/hl/videoForensic/AI/dev-skills --report E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/reports/videoForensic/20260701-090815-action/report.json --include-assets --notes "首页 report 资产化"
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

建议输出中的 workflow、元素和页面只说明“可以优先尝试什么”，不能直接作为用户问题的最终答案。

查询 action/workflow 资产：

```powershell
python skills/electron-ui-verifier/scripts/ev_assets.py --workspace E:/work/hl/videoForensic/AI/dev-skills list-actions --app-id videoForensic --kind clickText
python skills/electron-ui-verifier/scripts/ev_assets.py --workspace E:/work/hl/videoForensic/AI/dev-skills list-workflows --app-id videoForensic --goal "打开案件"
```

导出可分享 workflow：

```powershell
python skills/electron-ui-verifier/scripts/ev_export_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --workflow-id workflow-example --output E:/work/task/open-case.workflow.json --include-metadata
```

导出默认拒绝覆盖已有文件，默认不写本机 report/artifact 绝对路径。只有确实需要本机 evidence 路径时，才显式加 `--include-local-evidence-paths`。

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

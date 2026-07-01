# UI 知识库

## 目的

知识库用于沉淀 Electron 应用的页面、入口、元素、workflow 和证据摘要，让后续验证任务可以先查询已有经验，再决定如何操作 UI。

知识库只提供候选建议，不替代真实 UI 验证。任何来自 `observed` 或 `candidate` 状态的知识，都必须通过新的 action/workflow 证据复验后，才能提升到 `verified` 或 `stable`。

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

执行 action/workflow 时显式学习：

```powershell
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic --workflow E:/work/task/open-case.workflow.json --learn --learn-app-id videoForensic --learn-notes "打开案件流程复验"
```

默认不自动学习，避免一次性探索污染长期知识。

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

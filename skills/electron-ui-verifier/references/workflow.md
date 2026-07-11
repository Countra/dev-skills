# Run 与 Workflow

只在编排多步流程、控制失败或解释 report/pending 时读取本文件。

## Run 状态机

`prepare -> running -> finalizing -> passed|failed|aborted`

- prepare 创建 UUID runDir、journal 和空 evidence manifest，并实时确认 session。
- 每步先写 `running` intent，再执行 UI；成功后提交 artifact 和结果。
- mutating step 的 timeout 或进程崩溃视为 outcome unknown，run 进入 aborted，不重放。
- finalize 校验全部 evidence 后一次生成 report、summary 和可选 pending；重复 finalize 返回同一产物。

## Workflow 示例

```json
{
  "schemaVersion": 1,
  "appId": "sample-app",
  "goal": "保存设置并采集证据",
  "steps": [
    {
      "type": "click",
      "locator": {"role": "button", "accessibleName": "保存"},
      "postconditions": [{"type": "visible", "locator": {"text": "保存成功"}}]
    },
    {"type": "screenshot", "options": {"name": "saved.png"}}
  ]
}
```

执行：

```powershell
python <skill>/scripts/ev_workflow.py --workspace <absolute-workspace> --run-id <run-id> --workflow <absolute-json>
```

默认 workflow 执行后 finalize。需要追加独立步骤时使用 `--no-finalize`，完成后显式运行 `ev_finalize.py`。

## 复用与探索

prepare 中的 `knowledge.decision` 为 `reuse` 时，先核对候选 compatibility 和 requiredParams，再用 asset ID 执行。`abstain` 表示没有安全复用结论，不是 UI 失败。

完整目标未命中时，agent 根据当前 UI 和用户目标拆分子目标：入口、页面、前置状态、目标动作、最终断言。将这些子目标逐个传给 `ev_suggest.py --subgoal`。脚本不猜业务关键词，也不返回 unrelated recent filler。

新探索路径中的错误页面、重复尝试和 recovery-only 步骤标记 `detour:true`。finalize 生成的可批准 workflow 会排除 detour；不要把探索噪音固化为资产。

## 报告判断

最终结论至少检查：

- report status 与每步 status。
- mutating action 的 postconditions。
- evidence manifest 中 artifact 的 sha256、媒体类型、尺寸和质量。
- console/exception/network 摘要是否支持结论。
- session target 与用户要求的应用一致。

只有本轮 report/artifact 是现场证据。知识资产、历史截图或 pending 都不能单独证明当前 UI 通过。

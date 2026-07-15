# Typed Actions

只在编写 locator、action、assertion 或诊断步骤时读取本文件。JSON contract 以 `schemas/action.schema.json` 和 `schemas/locator.schema.json` 为准。

## Locator

每个 locator 只指定一种主策略：`role + accessibleName`、`label`、`placeholder`、`text`、`testId`、`title` 或 `css`。默认 exact 和 strict；匹配多个节点时返回有界候选摘要并停止。

优先级：role/label/testId > placeholder/text/title > CSS。只有 UI 缺少稳定语义时才用 CSS。`nth` 会把歧义转成位置依赖，必须记录风险。

## Mutating Action

```json
{
  "id": "save-settings",
  "type": "click",
  "locator": {"role": "button", "accessibleName": "保存"},
  "postconditions": [
    {"type": "visible", "locator": {"text": "保存成功"}}
  ]
}
```

`click`、`doubleClick`、`fill`、`select`、`check`、`uncheck`、`press` 和 `keyChord` 必须有 postconditions。点击先做 Playwright trial，再只提交一次；失败或 timeout 后不自动重放。

mutation 提交返回 durable operation receipt。默认不要假定命令已完成：

```powershell
python <skill>/scripts/ev_action.py --workspace <absolute-workspace> --run-id <run-id> --action <absolute-json>
python <skill>/scripts/ev_operation.py --workspace <absolute-workspace> get --operation-id <operation-id>
python <skill>/scripts/ev_operation.py --workspace <absolute-workspace> wait --operation-id <operation-id> --timeout-seconds 120
```

`requestId` 只为同一请求提供幂等提交，不授权重放 UI。operation 可处于 `queued`、`running`、`succeeded`、`failed`、`cancelled`、`deadline_exceeded` 或 `unknown`；只有 `succeeded` 才能作为动作成功证据。`wait` 超时不会取消，需停止时显式运行 `ev_operation.py cancel` 并检查收敛后的终态。

输入复用参数：

```json
{
  "type": "fill",
  "locator": {"label": "名称"},
  "value": "${name}",
  "postconditions": [
    {"type": "value", "locator": {"label": "名称"}, "expected": "${name}"}
  ]
}
```

parameterSchema 在 prepare 或 workflow 中声明，binding 通过 `--bindings` 提供。不要把真实值写进资产或 workflow 文件。

## 高风险动作

高风险动作不能在 action JSON 内自签。先生成不含动作原文和 binding value 的风险预览，用户确认 exact fingerprint 后签发短期一次性 receipt：

```powershell
python <skill>/scripts/ev_risk.py --workspace <absolute-workspace> preview --run-id <run-id> --action <absolute-json>
python <skill>/scripts/ev_risk.py --workspace <absolute-workspace> approve --preview-id <preview-id> --fingerprint <exact> --note <reason>
python <skill>/scripts/ev_action.py --workspace <absolute-workspace> --run-id <run-id> --action <absolute-json> --risk-receipt <receipt-id>
```

receipt 与 run、目标、动作 fingerprint 绑定且只能消费一次。过期、目标变化、动作变化或重复消费都必须重新 preview 并由用户确认；风险授权不会让动作自动进入知识库。

## Read-only 与证据

- `snapshot`：优先 ARIA snapshot，能力缺失时使用有界语义 fallback。
- `screenshot`：提交前验证 PNG、宽高、解压和非单色像素。
- `extractText`、`extractTable`：只返回有界结构化结果。
- `collectConsole`、`collectExceptions`、`collectNetwork`：只读取已脱敏 ring buffer。
- `evaluate`：只允许 allowlist 名称和受限返回大小，不接受任意 JavaScript。

诊断 action 可以设置 `continueOnFailure:true`，让其它独立诊断继续执行。普通 mutating action 失败后不得继续。

## Postconditions

支持 `visible`、`hidden`、`text`、`value`、`count`、`urlContains`、`titleContains` 和 `screenshotQuality`。断言必须验证用户目标对应的可观察结果，不能只验证“点击没有报错”。

当前 schema 不提供坐标旁路。无法建立稳定语义 locator 时停止并补充应用可访问性或测试标识，不得把不确定坐标包装成普通 action。

# Workflow Actions 说明

Workflow 文件供 `scripts/ev_workflow.py` 在已 attach 的 verifier session 内执行。CDP endpoint 和 target 选择应先由 `ev_probe.py`、`ev_attach.py` 完成；workflow 本身只描述 readiness 和 steps。

## 结构

```json
{
  "targetUrlContains": "index.html",
  "learn": false,
  "readiness": [
    {"waitText": "案件", "timeoutMs": 30000}
  ],
  "steps": [
    {"id": "home", "snapshot": true},
    {"id": "open-first", "clickText": "查看"},
    {"id": "result", "screenshot": "result.png"}
  ]
}
```

类似文件路径的值必须使用绝对路径。截图文件名可以是相对名称，但只能落在已选择的输出目录内。

`learn` 可以是 `false`、`true` 或对象，例如：

```json
{
  "learn": {
    "appId": "videoForensic",
    "notes": "打开案件流程复验"
  }
}
```

默认不学习。命令行 `ev_workflow.py --learn` 也可以启用学习；命令行传入的 learn 选项优先生效。

## Target 字段

- `targetUrlContains`：选择 URL 包含该值的页面。
- `targetTitleContains`：选择 title 包含该值的页面。
- `targetIndex`：对过滤后的 page targets 按从 0 开始的索引选择。
- `targetType`：默认为 `page`。

如果未提供 target 规则且存在多个 targets，runner 必须停止。

## Readiness Actions

- `waitText`：等待可见文档文本包含指定字符串。
- `waitUrlContains`：等待当前 target URL 包含指定字符串。
- `timeoutMs`：该 readiness 检查的超时时间。

Readiness 检查应证明 UI 可用，而不只是进程存活。

## Step Actions

- `snapshot: true`：保存 DOM 文本、title、URL 和基础元素候选。
- `screenshot: "name.png"`：采集 PNG 截图。
- `clickText: "文本"`：点击第一个匹配的可见文本候选。
- `clickText: {"text": "文本", "index": 1}`：点击指定匹配项。
- `clickXY: {"x": 100, "y": 200}`：坐标兜底。
- `fillText`：向通过文本或 selector 选中的输入框写入值。
- `pressKey`：发送键盘按键。
- `extractText`：抽取文本并写入报告字段。
- `extractTable`：抽取可见 table/list 行。
- `evaluate`：可选的显式 JavaScript 动作；仅在必要时使用。
- `collectConsole`：收集 `console.log/info/warn/error/debug` 等输出。
- `collectExceptions`：收集页面运行时未捕获异常。
- `collectNetwork`：收集请求 URL、方法、状态码和失败原因。
- `domSnapshot`：通过 CDP 导出完整 DOMSnapshot。
- `accessibilitySnapshot`：CDP 支持时导出 accessibility tree。

任何 step 都可以设置 `continueOnFailure: true`。它适用于“有用但不是业务断言必需”的证据步骤。如果这类步骤失败，runner 会记录为 `skipped`，把原因加入 `notCovered`，并按必需步骤决定 workflow 总状态。它主要用于不稳定的截图采集或次要视觉证据，不应用于 readiness、导航或核心断言。

## 诊断 Actions

诊断类 action 默认把完整数据写入 artifact，`report.json` 只保留数量、过滤条件、样例和 artifact 路径。除非用户明确要求，不采集 cookie、token、localStorage、请求头、请求体或响应体。

`collectConsole` 示例：

```json
{
  "id": "console-after-open",
  "collectConsole": {
    "levels": ["log", "warning", "error"],
    "maxEvents": 200,
    "name": "consoleAfterOpen"
  }
}
```

常用字段：

- `levels`：按 console 类型过滤；不填表示全部。
- `maxEvents`：最多导出的事件数，默认 200。
- `drainMs`：执行 action 时额外等待 socket 事件的毫秒数，默认 100。
- `sinceStep`：只导出指定 step 之后的事件。

`collectExceptions` 示例：

```json
{
  "id": "exceptions-after-flow",
  "collectExceptions": {
    "maxEvents": 100,
    "failOnException": true,
    "name": "pageExceptions"
  }
}
```

`failOnException: true` 表示采集到异常时该 step 失败；不设置时只采集证据。

`collectNetwork` 示例：

```json
{
  "id": "network-after-open",
  "collectNetwork": {
    "urlContains": "/api/",
    "includeFailedOnly": false,
    "maxEvents": 300,
    "name": "apiTraffic"
  }
}
```

Network 采集会在 workflow 开始时提前启用 CDP `Network` domain，因此 action 可以放在用户操作之后导出此前已发生的请求。默认字段包括 URL、method、resource type、status、mime type、cache 标记和失败原因，不包含 headers/body。

`domSnapshot` 示例：

```json
{
  "id": "dom-full",
  "domSnapshot": {
    "computedStyles": ["display", "visibility", "position"],
    "maxBytes": 5000000,
    "name": "fullDom"
  }
}
```

`domSnapshot` 使用 CDP `DOMSnapshot.captureSnapshot`，产物可能较大，默认写入 `*.dom-snapshot.json`。如果目标 Electron 的 CDP 不支持该 method，必需 step 会失败；可选证据应设置 `continueOnFailure: true`。

`accessibilitySnapshot` 示例：

```json
{
  "id": "ax-tree",
  "accessibilitySnapshot": {
    "maxNodes": 2000,
    "name": "accessibilityTree"
  },
  "continueOnFailure": true
}
```

该 action 使用 CDP `Accessibility.getFullAXTree`。不同 Electron/Chromium 版本支持度可能不同；非核心断言建议设置 `continueOnFailure: true`。

## Evaluate 增强

`evaluate` 必须继续显式设置 `allow: true`。

```json
{
  "id": "read-visible-count",
  "evaluate": {
    "allow": true,
    "name": "visibleButtonCount",
    "expression": "Array.from(document.querySelectorAll('button')).filter(b => b.offsetParent).length",
    "saveAs": "metrics.visibleButtonCount",
    "maxInlineChars": 2000,
    "artifact": "visible-button-count.json"
  }
}
```

增强字段：

- `name`：当前结果名称。
- `saveAs`：保存到 `report.json` 顶层 `namedResults` 的点号路径。
- `maxInlineChars`：允许内嵌到 step data 的最大字符数，默认 2000。
- `artifact`：指定完整结果 artifact 文件名；未指定且结果过大时自动生成。
- `onTooLarge`：`artifact`、`truncate` 或 `fail`，默认 `artifact`。
- `awaitPromise`：默认 `true`。
- `returnByValue`：默认 `true`。
- `timeoutMs`：默认 10000。

旧用法仍兼容：小结果会继续在 step data 中提供 `value` 字段。若使用 `onTooLarge: "truncate"`，`saveAs` 只保存预览和截断标记，不保存完整大对象。

## 选择器优先级

可用时优先使用稳定 selector 或精确文本：

1. workflow 提供的 CSS selector。
2. 精确文本。
3. 文本包含匹配。
4. 坐标兜底。

匹配有歧义时，记录候选并停止；除非 workflow 指定了 `index`。

## 报告

每个 step 应产出一条 step record：

```json
{
  "id": "result",
  "action": "screenshot",
  "status": "passed",
  "backend": "raw-cdp",
  "artifacts": ["result.png"],
  "error": null
}
```

Step status 可取值：

- `passed`
- `failed`
- `skipped`

未执行的业务覆盖项应写入顶层 `notCovered`。

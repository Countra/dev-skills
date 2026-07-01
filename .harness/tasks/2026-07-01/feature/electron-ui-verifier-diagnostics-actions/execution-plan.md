# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

- 增强 `electron-ui-verifier` skill 的 workflow action 能力，支持 console、异常、网络、完整 DOM、accessibility tree 和更强的 `evaluate` 结果采集。
- 用户已确认进入实现；当前已按计划完成实现、文档更新和 mock 验证。
- 实现保持通用性，未和 `VideoForensic` 业务强耦合。

待增强 action:

- `collectConsole`: 收集 `console.log/error/warn` 等运行时输出。
- `collectExceptions`: 收集页面未捕获异常。
- `collectNetwork`: 收集请求 URL、方法、状态码、资源类型、失败原因。
- `domSnapshot`: 导出更完整 DOM 结构。
- `accessibilitySnapshot`: CDP 支持时导出 accessibility tree。
- `evaluate` 增强：支持保存返回值到命名字段，支持长结果截断和 artifact 落盘。

非目标（Non-goals）:

- 不引入新的桌面原生自动化能力。
- 不把 Electron GUI 应用改成 `process-manager` 管理；Electron GUI 仍按本 skill 规则用普通终端或用户手动启动。
- 不默认采集 cookie、token、localStorage、请求头、请求体、响应体等敏感内容。
- 不提交 Git；用户此前明确要求本阶段不要提交代码。

验收标准（Acceptance）:

- 规划解释清楚每个 action 的 CDP 实现依据、命令/domain、启用时机、输出格式、失败策略和验证方式。
- 明确当前 runner 的关键缺陷，以及为什么必须先实现事件缓冲层。
- 明确 workflow 兼容策略：旧 workflow 不变，新 action 可选启用。
- 明确后续分阶段实现、审查、验证和文档更新路径。

## 当前约束（Constraints）

- 遵守全局 `AGENTS.md`：中文注释和文档、修改前先读上下文、最小变更、真实验证、长内容分段写入。
- 遵守 `skill-creator`：skill 本体保持精简，详细规则放在 `references/`，脚本放在 `scripts/`，必要示例放在 `assets/`。
- 遵守用户当前约束：接下来不要提交代码；本任务只落盘规划。
- 当前仓库已有未提交改动，主要是 `electron-ui-verifier` 中文化相关文件；后续实现不得回退这些用户/既有改动。
- 同一仓库 Git 命令应串行执行，本阶段不需要提交。

## 本地上下文（Local Context）

当前 skill 文件:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/actions.md`
- `skills/electron-ui-verifier/references/troubleshooting.md`
- `skills/electron-ui-verifier/assets/workflow.example.json`
- `skills/electron-ui-verifier/scripts/electron_verify.py`

当前 runner 能力:

- 支持 `probe`、`run`、`snapshot`、`screenshot`。
- 支持 action: `snapshot`、`screenshot`、`clickText`、`clickXY`、`fillText`、`pressKey`、`extractText`、`extractTable`、`waitText`、`waitUrlContains`、`evaluate`。
- raw CDP 使用 stdlib WebSocket 客户端，不依赖第三方 WebSocket 包。
- `Runtime.enable` 和 `Page.enable` 已在 workflow 执行时启用。
- `evaluate` 当前使用 `Runtime.evaluate`，参数为 `returnByValue: true`、`awaitPromise: true`。

当前关键缺陷:

- `CDPClient.call()` 只等待当前 JSON-RPC response。
- 等待 response 期间，如果收到不匹配当前 `id` 的 CDP event，目前会直接 `continue` 丢弃。
- 因此不能简单新增 `collectConsole`、`collectExceptions`、`collectNetwork`；必须先让 CDP client 能保存事件。
- Network 事件必须在用户交互前启用 `Network.enable`，否则点击后再采集会错过已发生请求。
- DOMSnapshot 和 Accessibility 属于独立 domain，不能由现有 JS `snapshot` 直接替代。

## 官方调研来源（External Sources）

优先参考官方或 primary source:

- Chrome DevTools Protocol Runtime domain: `Runtime.enable`、`Runtime.consoleAPICalled`、`Runtime.exceptionThrown`、`Runtime.evaluate`。
  来源：https://chromedevtools.github.io/devtools-protocol/tot/Runtime/
- Chrome DevTools Protocol Network domain: `Network.enable`、`Network.requestWillBeSent`、`Network.responseReceived`、`Network.loadingFailed`、`Network.loadingFinished`。
  来源：https://chromedevtools.github.io/devtools-protocol/tot/Network/
- Chrome DevTools Protocol DOMSnapshot domain: `DOMSnapshot.captureSnapshot`。
  来源：https://chromedevtools.github.io/devtools-protocol/tot/DOMSnapshot/
- Chrome DevTools Protocol Accessibility domain: `Accessibility.getFullAXTree`。
  来源：https://chromedevtools.github.io/devtools-protocol/tot/Accessibility/
- Chrome DevTools Protocol Log domain: `Log.enable`、`Log.entryAdded` 可作为补充浏览器日志来源。
  来源：https://chromedevtools.github.io/devtools-protocol/tot/Log/
- Playwright 事件模型可作为未来后端优化参考，但本次 runner 主路径仍使用 raw CDP，避免新增运行依赖。
  来源：https://playwright.dev/python/docs/events

## 总体设计（Architecture）

核心决策:

- 先增强 `CDPClient` 为事件感知客户端，再实现新 workflow action。
- runner 在执行 workflow 前预扫描 `readiness` 和 `steps`，只要发现 `collectConsole`、`collectExceptions` 或 `collectNetwork`，就提前启用对应 CDP domain。
- 事件采集从 workflow 开始后持续进行，不要求用户把 `collectNetwork` 放在点击前。
- 新 action 在执行点导出“截至当前时刻”的事件快照，并支持按 `sinceStep`、`levels`、`urlContains` 等条件过滤。
- report 中只放摘要和 artifact 路径，大体量数据写入单独 JSON/NDJSON artifact。

CDP 事件缓冲:

- `CDPClient` 增加 `events: list[dict]` 缓冲区。
- `call()` 仍返回指定 `id` 的 response；等待期间收到的 event 不再丢弃，统一写入 `events`。
- 增加 `drain_events(duration_ms, max_messages)`，用于在 action 执行点短时间读取已到达事件，避免刚发生的 console/network 事件滞留在 socket。
- 增加 `take_events(methods, since_index=None)` 或等价方法，按 CDP method 取出缓冲事件，但默认不删除原始事件，保证多个 action 可以复用同一批数据。
- 所有 drain 必须有时间上限，避免 GUI 任务被 socket 等待阻塞。

事件启用策略:

- `Runtime.enable`: 现有 workflow 已启用，后续继续作为默认启用。console 和 exception 都依赖 Runtime event。
- `Network.enable`: 只有 workflow 需要网络采集时启用，避免无关 workflow 增加事件量。
- `Log.enable`: 可选启用，用于补充浏览器日志；v1 不把它作为 console 的唯一来源。
- `DOMSnapshot.captureSnapshot`: action 执行时即时调用，不需要提前启用。
- `Accessibility.getFullAXTree`: action 执行时即时调用；如果 CDP 返回 domain/method 不支持，按 action 必需性决定 `failed` 或 `skipped`。

artifact 策略:

- 新 action 默认输出到 `<step-id>.<type>.json` 或 `<step-id>.<type>.ndjson`。
- `report.json` 的 step data 只记录数量、过滤条件、截断状态、artifact 路径和少量样例。
- 大文本、完整 DOM、完整 accessibility tree、网络明细默认写 artifact。
- 默认单个 action report 内嵌样例不超过 20 条，单条字符串不超过 2000 字符；完整内容在 artifact 中按配置限制。

安全策略:

- `collectNetwork` 默认不采集 request headers、response headers、request body、response body。
- 如果后续要支持 body/header，需要单独字段 `includeHeaders: true` 或 `includeBodies: true`，且默认要求用户明确授权；本次增强不把 body/header 作为 v1 必需能力。
- `evaluate` 默认不读取浏览器存储、cookie 或 token；如果用户写的表达式主动读取敏感数据，runner 只负责按用户显式 workflow 执行，并在文档中提醒风险。

## Action 设计（Workflow Actions）

### collectConsole

目标:

- 收集页面 `console.log`、`console.info`、`console.warn`、`console.error`、`console.debug` 等输出。

CDP 实现:

- 启用 `Runtime.enable`。
- 监听 `Runtime.consoleAPICalled`。
- 可选补充 `Log.enable` + `Log.entryAdded`，但 v1 输出中需要标记来源为 `runtime` 或 `log`。

建议 workflow:

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

输出:

- artifact: `console-after-open.console.ndjson`。
- step data: `name`、`count`、`levels`、`truncated`、`artifact`、`sample`。
- 单条 event 字段: `timestamp`、`level/type`、`text`、`args`、`stackTrace`、`source`。

注意:

- CDP console 参数可能是 `RemoteObject`，默认只保存 `type`、`subtype`、`value`、`description`，不深挖 objectId。
- 如果需要对象深拷贝，后续可新增 `resolveObjects`，但 v1 不默认启用。

### collectExceptions

目标:

- 收集页面运行时未捕获异常，辅助判断 UI 是否隐性报错。

CDP 实现:

- 启用 `Runtime.enable`。
- 监听 `Runtime.exceptionThrown`。
- 可记录 `Runtime.exceptionRevoked`，但报告主要以 thrown 为准。

建议 workflow:

```json
{
  "id": "exceptions-after-flow",
  "collectExceptions": {
    "maxEvents": 100,
    "name": "pageExceptions"
  }
}
```

输出:

- artifact: `exceptions-after-flow.exceptions.json`。
- step data: `name`、`count`、`hasException`、`artifact`、`sample`。
- 单条 exception 字段: `timestamp`、`text`、`url`、`lineNumber`、`columnNumber`、`exception.description`、`stackTrace`。

失败/通过语义:

- 默认只采集，不自动让 workflow 失败。
- 可支持 `failOnException: true`，当存在异常时该 step 失败。
- 如果 action 设置 `continueOnFailure: true`，则记录为 skipped/notCovered。

### collectNetwork

目标:

- 收集用户操作过程中的网络请求、响应状态和失败原因，定位后端接口失败、静态资源缺失、跨域或连接错误。

CDP 实现:

- workflow 预扫描发现该 action 后，在 readiness 前调用 `Network.enable`。
- 监听 `Network.requestWillBeSent`、`Network.responseReceived`、`Network.loadingFailed`、`Network.loadingFinished`。
- 以 `requestId` 聚合为一条 network entry。

建议 workflow:

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

输出:

- artifact: `network-after-open.network.json`。
- step data: `name`、`requestCount`、`failedCount`、`statusCounts`、`artifact`、`sample`。
- 单条 entry 字段: `requestId`、`url`、`method`、`resourceType`、`status`、`mimeType`、`fromDiskCache`、`failed`、`failureText`、`startedAt`、`finishedAt`。

注意:

- 默认过滤掉 headers/body，避免泄露认证信息。
- 如果请求在 action 前已经开始，只要 `Network.enable` 已提前启用，就能在 action 时聚合导出。
- 如果 workflow 没有 `collectNetwork`，不启用 Network，保持旧 workflow 低噪音。

### domSnapshot

目标:

- 导出比现有 JS `snapshot` 更完整、更结构化的 DOM 快照，便于做复杂 UI 分析和离线审计。

CDP 实现:

- 调用 `DOMSnapshot.captureSnapshot`。
- 默认 `computedStyles` 为空数组，避免产物过大。
- 可选 `computedStyles`、`includeDOMRects`、`includePaintOrder`，具体支持按目标 Electron 的 CDP 版本处理。

建议 workflow:

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

输出:

- artifact: `dom-full.dom-snapshot.json`。
- step data: `name`、`documentCount`、`nodeCount`、`layoutCount`、`bytes`、`truncated`、`artifact`。

fallback:

- 如果 `DOMSnapshot.captureSnapshot` 不支持，回退为现有 JS `snapshot` 不是等价能力，应明确记录 `fallback: "jsSnapshot"` 和 `notCovered`。
- 只有 action 设置 `allowFallback: true` 时才自动 fallback；默认 method 不支持时 step 失败。

### accessibilitySnapshot

目标:

- 导出 accessibility tree，用于检查可访问名称、角色、忽略节点和辅助技术视角下的 UI 结构。

CDP 实现:

- 调用 `Accessibility.getFullAXTree`。
- 该能力在 CDP 中属于实验/版本差异较明显的能力，必须有清晰失败策略。

建议 workflow:

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

输出:

- artifact: `ax-tree.accessibility.json`。
- step data: `name`、`nodeCount`、`ignoredCount`、`artifact`、`sample`。
- 节点字段保留 `nodeId`、`role`、`name`、`value`、`description`、`ignored`、`childIds`。

失败策略:

- 因 CDP 不支持该 method 失败时，如果 `continueOnFailure: true`，记录为 skipped 和 notCovered。
- 如果用户把它作为必需 step，则失败会导致 workflow failed。

### evaluate 增强

目标:

- 让显式 JavaScript 执行可以保存命名结果，并对长结果进行可控截断和 artifact 落盘。

当前行为:

- 当前 `evaluate` 只返回 `{"value": value}` 到 step data。
- 长字符串、大数组、大对象可能撑大 `report.json`。
- 无法把结果保存到可复用命名字段。

建议 workflow:

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

增强字段:

- `name`: 当前 step 内结果名。
- `saveAs`: 保存到 report 顶层 `data` 或 `namedResults` 的路径，推荐点号路径。
- `maxInlineChars`: report 内嵌结果最大字符数。
- `artifact`: 指定完整结果 artifact 文件名；未指定但结果超限时自动生成。
- `awaitPromise`: 默认 `true`。
- `returnByValue`: 默认 `true`。
- `timeoutMs`: 单次 evaluate 超时。
- `onTooLarge`: `truncate`、`artifact`、`fail`，默认 `artifact`。

输出:

- step data: `name`、`saveAs`、`inlineValue` 或 `valuePreview`、`truncated`、`artifact`、`valueType`。
- report 顶层新增 `namedResults`，保存 `saveAs` 指定的结构化结果或 artifact 引用。

注意:

- `allow: true` 继续保留，避免 workflow 无意执行任意 JS。
- 如果返回值无法 `returnByValue` 序列化，记录 `description` 和 `unserializableValue`，必要时建议用户改写表达式。

## 报告结构调整（Report Schema）

建议新增字段:

```json
{
  "diagnostics": {
    "enabledDomains": ["Runtime", "Network"],
    "eventCounts": {
      "Runtime.consoleAPICalled": 3,
      "Runtime.exceptionThrown": 0,
      "Network.requestWillBeSent": 12
    }
  },
  "namedResults": {
    "metrics": {
      "visibleButtonCount": 8
    }
  }
}
```

兼容策略:

- `schemaVersion` 暂不必从 `1` 升级到 `2`，因为这是向后兼容的字段新增。
- 如果后续修改旧字段语义，再升级 schema。
- 旧 workflow 不包含新 action 时，report 行为应和当前版本一致。

## 文件修改范围（Planned Files）

后续实现预计修改:

- `skills/electron-ui-verifier/scripts/electron_verify.py`
  - 增加 CDP event buffer、event drain、domain auto-enable、network 聚合、长结果 artifact 工具函数。
  - 增加新 actions 和增强 evaluate。
- `skills/electron-ui-verifier/references/actions.md`
  - 记录新 action schema、示例、默认值和安全边界。
- `skills/electron-ui-verifier/references/workflow.md`
  - 记录诊断类 action 的启用时机、证据产物、报告解释方式。
- `skills/electron-ui-verifier/references/troubleshooting.md`
  - 记录 console/network/DOMSnapshot/accessibility 常见失败和处理。
- `skills/electron-ui-verifier/assets/workflow.example.json`
  - 保持最小示例，最多加入一个轻量诊断 action。
- 可选新增 `skills/electron-ui-verifier/assets/diagnostics.workflow.example.json`
  - 如果示例过长，单独给诊断 workflow 模板，避免污染最小示例。
- `skills/electron-ui-verifier/SKILL.md`
  - 只补一句诊断能力和需要读取 `actions.md` 的提示，不堆详细 schema。
- `skills/electron-ui-verifier/agents/openai.yaml`
  - 如描述已不覆盖诊断能力，做短描述同步。

## 实施阶段（Implementation Plan）

### Stage 1：规划审批

状态:

- 当前阶段。

目标:

- 完成调研、设计和详细计划。

退出条件:

- 本计划已落盘并复查。
- 用户确认开始实现前，不修改 skill 本体。

### Stage 2：CDP 事件缓冲核心

目标:

- 修复当前事件丢弃问题，为 console、exception、network 采集提供底座。

实施要点:

- 修改 `CDPClient.call()`，把无 `id` 的 event 或非当前 `id` message 写入缓冲。
- 增加有时间上限的 `drain_events`。
- 增加事件过滤和快照方法。
- 保持原有 `call()` API 兼容。

验证:

- 用 mock WebSocket/CDP server 发送 response 前插入 `Runtime.consoleAPICalled`，确认事件不丢。
- 验证旧 `snapshot`、`screenshot`、`clickText` workflow 不受影响。

### Stage 3：Console 和 Exception action

目标:

- 实现 `collectConsole` 和 `collectExceptions`。

实施要点:

- workflow 预扫描启用 `Runtime.enable`。
- 序列化 `RemoteObject` 时只做浅层安全摘要。
- 支持 `levels`、`maxEvents`、`name`、`failOnException`。

验证:

- mock CDP 发送 console log/warn/error，检查 artifact 和 report 摘要。
- mock CDP 发送 exceptionThrown，检查 `failOnException` 行为。

### Stage 4：Network action

目标:

- 实现 `collectNetwork` 和 requestId 聚合。

实施要点:

- workflow 预扫描发现网络 action 后，在 readiness 前调用 `Network.enable`。
- 聚合 request/response/failed/finished。
- 默认不导出 headers/body。
- 支持 `urlContains`、`includeFailedOnly`、`maxEvents`、`name`。

验证:

- mock CDP 发送成功请求、404 请求、loadingFailed 请求。
- 检查 statusCounts、failedCount、failureText。

### Stage 5：DOMSnapshot 和 Accessibility action

目标:

- 实现结构化 DOM 和 accessibility tree 导出。

实施要点:

- `domSnapshot` 调用 `DOMSnapshot.captureSnapshot`。
- `accessibilitySnapshot` 调用 `Accessibility.getFullAXTree`。
- 增加 method 不支持时的清晰错误、fallback 和 `continueOnFailure` 行为。

验证:

- mock CDP 返回 DOMSnapshot 文档结构，检查 node/layout 统计。
- mock CDP 返回 accessibility nodes，检查 ignored/node 统计。
- mock CDP 返回 method not found，检查 optional step skipped。

### Stage 6：evaluate 增强

目标:

- 支持命名结果、长结果截断和 artifact 落盘。

实施要点:

- 新增 `namedResults` 写入。
- 新增通用 `serialize_result_with_limits`。
- 超限默认写 artifact，report 内只留 preview 和路径。
- 保留 `allow: true` 硬规则。

验证:

- evaluate 返回数字、字符串、大数组、大对象、不可序列化描述。
- 检查 `saveAs` 路径写入和 artifact 生成。

### Stage 7：文档和示例

目标:

- 让后续 agent 清楚知道何时用这些 action、怎么解释结果、哪些数据不会默认采集。

实施要点:

- `actions.md` 增加新 action schema。
- `workflow.md` 增加诊断 action 的启用和证据解释。
- `troubleshooting.md` 增加事件缺失、CDP method unsupported、network body 不采集等排障。
- `SKILL.md` 保持简洁，只增加能力入口。

验证:

- 完整复读文档。
- 确认没有把详细 schema 塞进 `SKILL.md`。

### Stage 8：回归验证和审查

目标:

- 确认旧能力不退化，新能力有可重复证据。

必需验证:

- `python -m py_compile skills/electron-ui-verifier/scripts/electron_verify.py`
- `python skills/electron-ui-verifier/scripts/electron_verify.py --help`
- mock CDP workflow 覆盖新 actions。
- 旧 workflow 示例仍可解析并运行到相同报告结构。

可选验证:

- 用户提供或已运行的真实 Electron 应用 CDP endpoint。
- VideoForensic smoke 只作为真实应用验证样本，不把业务内容写死进 skill。

## 验证矩阵（Validation Matrix）

| 能力 | 必需验证 | 失败判定 | 证据 |
| --- | --- | --- | --- |
| CDP event buffer | response 前插入 event 不丢失 | event 未写入缓冲 | mock report/event artifact |
| collectConsole | log/warn/error 可采集和过滤 | count 不正确或 level 丢失 | console ndjson |
| collectExceptions | exceptionThrown 可采集 | stack/url/line 丢失 | exceptions json |
| collectNetwork | 成功、失败、状态码聚合 | requestId 聚合错误 | network json |
| domSnapshot | captureSnapshot 输出 artifact | method 调用失败未解释 | dom-snapshot json |
| accessibilitySnapshot | getFullAXTree 输出 artifact | unsupported 未按规则 skipped/failed | accessibility json |
| evaluate 增强 | saveAs、截断、artifact | report 过大或命名结果缺失 | report/namedResults/artifact |
| 旧 workflow | 原有 actions 不退化 | 旧示例失败 | report.json |

## 风险和处理（Risks）

事件采集时机风险:

- 风险：用户把 `collectNetwork` 放在点击之后，如果 runner 不提前启用 Network，会错过请求。
- 处理：执行前预扫描 workflow，提前启用需要的 domain。

事件缓冲阻塞风险:

- 风险：为了等事件而长时间阻塞。
- 处理：所有 drain 都设置 `durationMs` 和 `maxMessages`，默认短窗口读取。

产物过大风险:

- 风险：DOMSnapshot、network、evaluate 大对象导致 report 巨大或 patch/读取困难。
- 处理：report 只放摘要，完整内容写 artifact；提供 `maxEvents`、`maxBytes`、`maxInlineChars`。

敏感信息风险:

- 风险：network 或 evaluate 导出 token、cookie、业务数据。
- 处理：默认不采集 headers/body/storage；文档明确用户表达式风险；artifact 默认放 ignored 运行目录。

CDP 版本差异风险:

- 风险：旧 Electron 不支持 `DOMSnapshot.captureSnapshot` 或 `Accessibility.getFullAXTree`。
- 处理：method unsupported 清晰记录；可选 step 用 `continueOnFailure`；fallback 不伪装成等价能力。

通用性风险:

- 风险：为 VideoForensic 写死选择器或业务字段。
- 处理：所有 action 保持 workflow 参数化；真实应用验证只作为 smoke，不进入 skill 默认规则。

## 计划自查（Plan Self-Review）

自查项:

- 是否解释了为什么不能直接新增 action：已解释，当前 CDP event 会丢弃。
- 是否覆盖了官方 CDP domain：已覆盖 Runtime、Network、DOMSnapshot、Accessibility、Log。
- 是否定义了输出和敏感边界：已定义 report 摘要、artifact、默认不采集 headers/body/storage。
- 是否保证旧 workflow 兼容：已定义旧 workflow 不启用新 domain，旧 action 行为不变。
- 是否有分阶段验证：已定义 Stage 2-8 和验证矩阵。

结论:

- 当前方案已按用户确认进入实现并完成；实现后复查未发现需要扩大范围的缺陷。

## 实施记录（Implementation Progress）

| 阶段 | 状态 | 完成内容 | 验证 |
| --- | --- | --- | --- |
| Stage 1 | completed | 调研和规划落盘 | 文档复读、active-task JSON 解析 |
| Stage 2 | completed | `CDPClient` 增加事件缓冲、事件 drain、事件计数 | mock response 前插入 event 不丢失 |
| Stage 3 | completed | 实现 `collectConsole`、`collectExceptions` | mock console/exception artifact 生成 |
| Stage 4 | completed | 实现 `collectNetwork`、Network 预启用和 requestId 聚合 | mock 成功请求和失败请求聚合 |
| Stage 5 | completed | 实现 `domSnapshot`、`accessibilitySnapshot` | mock DOMSnapshot/AX tree artifact 生成 |
| Stage 6 | completed | 增强 `evaluate` 的 `saveAs`、长结果策略和 `namedResults` | mock evaluate 写入 namedResults |
| Stage 7 | completed | 更新 `SKILL.md`、actions/workflow/troubleshooting 和诊断 workflow 示例 | JSON 示例解析、文档复读 |
| Stage 8 | completed | 回归验证和代码审查 | py_compile、help、mock run_workflow、diff review |

## 验证证据（Validation Evidence）

| 命令/检查 | 结果 | 覆盖内容 |
| --- | --- | --- |
| `python -m py_compile skills\\electron-ui-verifier\\scripts\\electron_verify.py` | pass | Python 语法 |
| `python skills\\electron-ui-verifier\\scripts\\electron_verify.py --help` | pass | CLI 可用性 |
| `python -m json.tool skills\\electron-ui-verifier\\assets\\diagnostics.workflow.example.json` | pass | 新 workflow 示例 JSON 合法 |
| `python .harness\\tasks\\2026-07-01\\feature\\electron-ui-verifier-diagnostics-actions\\tmp\\diagnostics_unit_check.py` | pass | CDP 事件缓冲、新 actions、Network 预启用、diagnostics、namedResults |
| artifact 检查 | pass | console、exceptions、network、DOMSnapshot、accessibility mock 产物存在且非空 |

未执行项:

- 未执行真实 Electron 应用 smoke；本次需求是 skill 能力增强，已用 mock 覆盖关键路径。
- 未提交 Git；遵守用户“不再提交代码”的当前约束。

## 执行控制（Execution Control）

执行模式:

- run-to-completion

整体状态:

- complete

当前阶段:

- Stage 8

剩余阶段:

- none

下一步:

- 等待用户检查或提出下一轮增强。

停止条件:

- none

## 恢复摘要（Resume Summary）

- 当前任务：实现 `electron-ui-verifier` 诊断类 workflow actions 增强。
- 当前已完成实现、文档、示例和 mock 验证；未提交代码。
- 已修复 `CDPClient` 事件丢弃问题，并实现 console、exception、network、DOMSnapshot、accessibility 和增强 evaluate。
- 新 action 默认写 artifact，report 只写摘要，并保留 `namedResults` 和 `diagnostics`。
- Electron GUI 应用仍不使用 `process-manager`。
- 后续如果需要真实 Electron smoke，可使用用户提供的 CDP endpoint 再跑诊断 workflow。

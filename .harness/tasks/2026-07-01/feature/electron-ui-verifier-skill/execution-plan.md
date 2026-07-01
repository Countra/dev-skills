# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

- 设计并实现一个 `electron-ui-verifier` skill，用于验证 Electron 桌面应用 UI、交互流程、截图、DOM/文本/表格提取和验证证据输出。
- 当前阶段只落盘详尽规划文档，不创建或修改 `skills/electron-ui-verifier/` 实现文件。
- 后续实现必须在用户明确批准方案后才能开始。

非目标（Non-goals）:

- 当前不实现 skill 代码、不创建 runner 脚本、不提交代码。
- v1 不覆盖所有 Windows 原生控件自动化，例如系统文件选择器、UAC、托盘菜单和非 Electron 原生窗口。
- v1 不把 Playwright MCP 当成唯一验证路径；它只作为可用后端之一。

验收标准（Acceptance）:

- 规划文档覆盖本地上下文、外部调研结论、候选方案、最终决策、分阶段实施、验证策略、风险、回滚和 harness 门禁。
- 明确 Electron UI verifier skill 的仓库结构、核心脚本能力、workflow 格式、证据产物和 fallback 策略。
- 明确后续实现阶段必须等待用户批准，且按 `run-to-completion` 完成所有批准阶段。

约束（Constraints）:

- 遵守当前 `complex-coding-harness` managed 任务流程。
- 遵守全局 `AGENTS.md`：中文注释、最小变更、分段写入、真实验证、规范 commit。
- 遵守 `skill-creator`：skill 保持精简，`SKILL.md` + 必要 `scripts/`、`references/`、`assets/`、`agents/openai.yaml`。
- 如果后续启动长期 Electron 进程或 dev server，且 `process-manager` skill 可用，必须通过 `process-manager` 管理。
- 规划和实现写文件都必须使用分段 patch；大文件不得一次性整文件重写。

待确认项（Open uncertainties）:

- 后续实现阶段是否允许用本机 `D:\VideoForensic\VideoForensic.exe` 做真实 smoke 验证。
- 后续实现阶段是否允许安装或使用 Playwright Python / Node Playwright 依赖。
- 后续是否需要把 Windows 原生自动化作为 v2 计划，而不是 v1 范围。

## 上下文（Context）

本地代码（Local code）:

- `skills/complex-coding-harness/`：提供 managed 任务、计划审批、分阶段执行、process-manager、Git 串行、分段写入和最终交付规则。
- `skills/process-manager/`：提供 Windows 长期后台进程托管能力，支持 `direct`、`cmd-file`、`powershell-file`。
- 当前仓库已有 `.gitignore` 忽略 `.harness/tasks/**/artifacts/`、`logs/`、`tmp/`、`scratch/` 和 `.tmp/`。

本地文档（Local docs）:

- `.harness/environment.md`：主分支为 `main`，harness 分支策略使用 `harness/feature` 等固定分支。
- `skills/complex-coding-harness/references/workflow.md`：要求 managed 任务在计划批准前停止，实施后默认 `run-to-completion`。
- `skills/complex-coding-harness/templates/execution-plan.md`：当前计划采用的任务状态模板。

外部来源（External sources）:

- Electron 官方 automated testing 文档：Electron 应用可用 WebDriver、ChromeDriver、Playwright 等方式自动化。来源：https://www.electronjs.org/docs/latest/tutorial/automated-testing
- Playwright Electron API：`_electron.launch()` 和 `ElectronApplication` 适合有开发入口或源码项目。来源：https://playwright.dev/docs/api/class-electron
- Playwright `connect_over_cdp` 文档：CDP attach 是低保真连接，适用于 Chromium 但不等同 Playwright 原生协议。来源：https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp
- Playwright MCP 仓库：支持 `--cdp-endpoint` 和 agent 可调用的 snapshot/click/screenshot 等工具。来源：https://github.com/microsoft/playwright-mcp
- Chrome DevTools Protocol 文档：`Runtime.evaluate`、`Input.dispatchMouseEvent`、`Page.captureScreenshot` 可支撑 raw CDP fallback。来源：https://chromedevtools.github.io/devtools-protocol/
- Spectron 仓库：已废弃，不作为新 skill 基础。来源：https://github.com/electron-userland/spectron
- Appium Windows Driver：可作为未来 Windows 原生窗口 fallback，但 v1 不默认引入。来源：https://github.com/appium/appium-windows-driver

用户约束（User constraints）:

- 希望把 Electron UI 验证做成 skill，减少每次临时写大量针对性脚本。
- 希望支持点击、截图、UI 样式观察、完整软件内部 workflow 验证。
- 当前先针对 Electron 应用，不扩展成泛桌面自动化。
- 基于 harness 规则落盘规划，暂不直接实现。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| Electron UI verifier 应作为 managed 任务规划 | read | `complex-coding-harness` workflow | 必须先计划、审查、审批 |
| skill 目录应放在 `skills/electron-ui-verifier/` | read | `skill-creator` + 当前仓库结构 | 后续实现路径 |
| Playwright 适合 Electron 但不能作为唯一后端 | external / confirmed | Playwright 文档 + VideoForensic 实测 | 必须设计 fallback |
| raw CDP 能覆盖基本截图、点击和 DOM 提取 | external / confirmed | CDP 文档 + VideoForensic 实测 | v1 核心兜底 |
| Spectron 不适合作为新方案基础 | external | Spectron 仓库 | 排除方案 |

## 候选方案（Options）

### 方案 A：只写 Playwright/MCP 指南

- 做法（How）: 创建一个轻量 skill，只指导 agent 启动 Electron 并用 Playwright 或 MCP 操作。
- 优点（Pros）: 文件少，实现快。
- 缺点（Cons）: 遇到旧 Electron、CDP 兼容问题、MCP snapshot 失败时不可用。
- 风险（Risks）: 会回到“一次性脚本”和人工排障，无法稳定验证复杂桌面 UI。
- 验证（Validation）: 只能验证 Playwright/MCP 成功场景。
- 回滚（Rollback）: 删除该 skill 或重做为结构化 verifier。

### 方案 B：结构化 Electron verifier skill

- 做法（How）: 提供 `SKILL.md`、workflow 参考文档、统一 `electron_verify.py` runner、示例 workflow 和故障排查文档。
- 优点（Pros）: 支持能力探测、后端选择、raw CDP fallback、统一证据输出。
- 缺点（Cons）: 初始实现成本更高，需要维护 runner。
- 风险（Risks）: runner 范围过大时可能变复杂；需要严格控制 v1 action 集合。
- 验证（Validation）: 可用 mock/临时 Electron/CDP endpoint 和真实 VideoForensic smoke 分层验证。
- 回滚（Rollback）: 回退新增 `skills/electron-ui-verifier/` 和对应 eval/文档。

### 方案 C：直接做泛 Windows 桌面自动化 skill

- 做法（How）: 以 Appium Windows Driver 或 WinAppDriver 体系覆盖 Electron、原生窗口和系统弹窗。
- 优点（Pros）: 理论覆盖面更广。
- 缺点（Cons）: 依赖重、环境配置成本高、和当前 Electron 验证目标不够聚焦。
- 风险（Risks）: v1 范围失控，用户每个项目都需要额外 Windows 自动化服务环境。
- 验证（Validation）: 需要单独部署 Appium/Windows driver 后才能验证。
- 回滚（Rollback）: 退回 Electron 专项方案。

## 决策（Decision）

选择方案（Chosen option）:

- 选择方案 B：结构化 Electron verifier skill。

原因（Why）:

- 只靠 Playwright/MCP 无法覆盖旧 Electron 和 CDP 兼容性失败。
- raw CDP 能提供最小可靠底座，Playwright/MCP 能在可用时提供更高层能力。
- 通过统一 workflow 和报告格式，可以减少临时脚本数量，也能满足 harness 的验证证据要求。

影响（Impact）:

- 新增 `skills/electron-ui-verifier/`。
- 新增可执行脚本 `scripts/electron_verify.py`。
- 新增 workflow/action/troubleshooting 参考文档和示例 workflow。
- 可能新增 eval 提示或验证样例，具体实现前再确认仓库现有 eval 结构。

可逆性（Reversibility）:

- 新增 skill 文件相对独立，可通过回退 `skills/electron-ui-verifier/` 和相关 eval 文件恢复。
- 不修改现有 `complex-coding-harness` 或 `process-manager` 的核心规则，除非实现阶段发现必须联动。

变更条件（Change conditions）:

- 如果 Playwright/MCP 在目标应用上稳定可用，runner 仍保留 raw CDP fallback，但实际 workflow 可走高层后端。
- 如果用户要求覆盖原生系统弹窗或非 Electron 应用，需要新建 v2 阶段或单独 skill 规划。
- 如果后续发现 Python raw CDP 实现不可维护，可改为 Node CDP runner，但必须重新批准依赖和验证策略。

方案变更触发条件（Reapproval triggers）:

- 需要新增第三方依赖并写入项目安装要求。
- 需要修改 `complex-coding-harness` 或 `process-manager` 的规则。
- 需要引入 Appium、WinAppDriver、系统级驱动或管理员权限。
- 必需验证无法执行，且替代证据不足。
- 实现范围超出 `skills/electron-ui-verifier/`、eval 和 `.harness` 任务记录。

## 推荐仓库结构（Proposed Structure）

```text
skills/
└── electron-ui-verifier/
    ├── SKILL.md
    ├── agents/
    │   └── openai.yaml
    ├── scripts/
    │   └── electron_verify.py
    ├── references/
    │   ├── workflow.md
    │   ├── actions.md
    │   └── troubleshooting.md
    └── assets/
        └── workflow.example.json
```

结构说明：

- `SKILL.md`：只放触发规则、快速流程、何时读取引用文档和安全边界。
- `scripts/electron_verify.py`：统一 CLI runner，负责 probe、workflow 执行、截图、提取和报告。
- `references/workflow.md`：详细工作流、后端选择、harness 集成、process-manager 集成。
- `references/actions.md`：workflow action DSL，包括 wait、click、fill、screenshot、extract。
- `references/troubleshooting.md`：CDP 连接失败、Playwright 失败、旧 Electron、后台服务、权限和端口问题。
- `assets/workflow.example.json`：用户或 agent 可复制修改的最小示例。

明确不创建：

- `README.md`
- `INSTALLATION_GUIDE.md`
- `CHANGELOG.md`
- 过多示例项目或大型 fixture

## 关键设计补充（Review Additions）

### CDP 传输策略

- raw CDP fallback 不能假设 Python 标准库已经提供 WebSocket 客户端。
- v1 推荐在 `electron_verify.py` 内实现一个最小的 stdlib-only CDP WebSocket transport，仅支持 `ws://127.0.0.1`、`ws://localhost` 和本机端口。
- 该 transport 只覆盖 CDP 所需的文本 JSON 消息、基础 handshake、masked client frame、ping/pong、close 和常见 payload 长度。
- 如果目标 endpoint 是 `wss://`、远程主机或需要代理认证，v1 默认停止并请求用户确认，不静默降级。
- 如果实现阶段判断 stdlib-only transport 风险过高，必须先更新计划并重新请求批准，才能改为安装 `websocket-client` 或其他依赖。

### 目标窗口选择

- Electron 应用可能有多个 window、devtools target 或隐藏 page。
- runner 必须先读取 `/json/version` 和 `/json/list`，记录所有候选 target。
- workflow 可指定 `targetUrlContains`、`targetTitleContains`、`targetIndex` 或 `targetType`。
- 如果候选 target 不唯一，且 workflow 没有选择规则，不能盲选；应输出候选列表并停止。
- 报告必须记录最终选择的 target id、title、url 和 websocket endpoint。

### 安全边界

- 默认只连接本机 CDP endpoint，不连接远程调试端口。
- workflow 中涉及任意 JS 执行的动作必须显式声明，默认 action 只允许读取 DOM、计算坐标、点击、输入、截图和提取。
- report 和 summary 默认不输出 cookie、localStorage、token、完整请求头或大段敏感文本。
- 如果用户要求导出敏感数据，必须在当前任务中明确确认。

### MCP 边界

- Playwright MCP 是 agent 可用工具路径，不是 `electron_verify.py` 必须直接调用的内部库。
- skill 文档应要求：用户或环境指定 MCP 时，agent 优先用 MCP 做可视化验证；MCP 失败时记录失败原因并切回 runner/raw CDP。
- MCP 不可用不能阻塞 v1，只要 raw CDP 验证路径可用。

### 报告格式

- `report.json` 必须包含 `schemaVersion: 1`。
- 每个 step 至少记录 `id`、`action`、`status`、`startedAt`、`endedAt`、`backend`、`artifacts`、`error`。
- `summary.md` 必须区分 `passed`、`failed`、`skipped`、`not covered`。
- 截图验证至少检查文件存在、大小大于 0、图像尺寸可读取；可行时增加非空白像素检查。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | `electron_verify.py` CLI、workflow JSON schema、target selection | 参数设计不稳定 | CLI help、dry-run、workflow smoke | `references/actions.md` |
| 数据结构（Data model） | yes | `report.json`、workflow JSON、events log、target metadata | 后续兼容性 | schema-like 校验、样例验证 | `references/workflow.md` |
| 前端交互（Frontend interaction） | yes | click、fill、wait、screenshot、extract | 选择器脆弱 | 真实 Electron smoke、截图证据 | `references/actions.md` |
| 配置/环境（Config/environment） | yes | Python、Playwright 可选、CDP port、绝对路径、本机 endpoint | 环境差异 | probe 命令、错误报告 | `troubleshooting.md` |
| 兼容性（Compatibility） | yes | Playwright backend、raw CDP fallback、WebSocket transport | 旧 Electron 差异 | fallback 测试 | `workflow.md` |
| 测试（Tests） | yes | runner 单测、dry-run、真实 smoke | GUI 验证不稳定 | 分层验证 | 计划和报告 |
| 文档（Documentation） | yes | SKILL 和 references | 规则过重或遗漏 | quick_validate、人工 review | 全部 skill 文档 |

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：计划审批和环境确认

目标（Goal）:

- 完成当前规划文档，等待用户批准后再实现。

做法（How）:

- 读取 `.harness/environment.md`、现有 skill、`process-manager` 规则和外部官方资料。
- 记录候选方案、最终决策、风险、验证和 Git/工具策略。

原因（Why）:

- Electron UI verifier 涉及外部工具、长期进程、GUI 验证和多后端兼容，必须先确认方案。

位置（Where）:

- 文件/模块（Files/modules）: `.harness/tasks/2026-07-01/feature/electron-ui-verifier-skill/execution-plan.md`
- API/配置（APIs/configs）: 暂不新增。
- 测试/文档（Tests/docs）: 当前文档自查。

参考来源（References）:

- `skills/complex-coding-harness/references/workflow.md`
- `skills/process-manager/references/workflow.md`
- Electron、Playwright、CDP、Playwright MCP 官方文档。

验证（Validation）:

- 完整复读本计划。
- 确认 `Plan Quality Gate`、`Plan Self-Review`、`Readiness Gate` 状态。

风险和回滚（Risks and rollback）:

- 风险：规划过大或 v1 范围失控。
- 回滚：收缩 v1 action 集合，只保留 probe、snapshot、screenshot、clickText、extractText。

阶段契约（Stage Contract）:

- 范围（Scope）: 仅规划。
- 允许修改（Allowed changes）: 当前 `execution-plan.md` 和 `.harness/active-task.json`。
- 禁止修改（Forbidden changes）: 不创建 `skills/electron-ui-verifier/`。
- 进入条件（Entry checks）: 读取 harness 和 skill 规则。
- 退出条件（Exit checks）: 计划进入 `awaiting_plan_approval`。
- 必需验证（Required validation）: 文档复读和门禁检查。
- 是否预期提交（Commit expected）: no，当前只落盘计划。

### 阶段 2（Stage 2）：skill scaffold

目标（Goal）:

- 在用户批准后创建最小 skill 目录骨架。

做法（How）:

- 使用 `skill-creator` 的 `init_skill.py` 或等价流程创建 `skills/electron-ui-verifier/`。
- 生成 `SKILL.md`、`agents/openai.yaml`、`scripts/`、`references/`、`assets/`。

原因（Why）:

- 保持和 Codex skill 标准一致，避免手写遗漏 frontmatter 或 UI 元数据。

位置（Where）:

- 文件/模块（Files/modules）: `skills/electron-ui-verifier/`
- API/配置（APIs/configs）: skill frontmatter 和 openai metadata。
- 测试/文档（Tests/docs）: `quick_validate.py`

参考来源（References）:

- `skill-creator` SKILL.md。

验证（Validation）:

- 运行 skill validation。
- 检查 `SKILL.md` frontmatter 只有 `name` 和 `description`。

风险和回滚（Risks and rollback）:

- 风险：生成多余示例文件。
- 回滚：删除无关 placeholder，只保留必要资源。

阶段契约（Stage Contract）:

- 范围（Scope）: skill 目录骨架。
- 允许修改（Allowed changes）: `skills/electron-ui-verifier/`。
- 禁止修改（Forbidden changes）: 不修改现有 skill 行为。
- 进入条件（Entry checks）: 用户批准方案。
- 退出条件（Exit checks）: scaffold 验证通过。
- 必需验证（Required validation）: quick validation。
- 是否预期提交（Commit expected）: yes，若用户批准阶段提交。

### 阶段 3（Stage 3）：verifier runner 核心

目标（Goal）:

- 实现 `electron_verify.py` 的核心 CLI、能力探测、连接管理和 artifact 输出框架。

做法（How）:

- 提供 `probe`、`run`、`snapshot`、`screenshot` 等子命令。
- 校验 exe、cwd、workflow、out 目录中的路径参数必须为绝对路径。
- 支持连接已启动应用的 CDP endpoint，也支持在被批准时启动 Electron exe。
- 记录 backend capability：Playwright Electron、Playwright CDP、Playwright MCP、raw CDP。
- 对 raw CDP 实现 stdlib-only 本机 WebSocket transport；如需第三方 WebSocket 依赖必须重新批准。
- 实现 target discovery 和 target selection，避免多个 Electron window 时盲选。

原因（Why）:

- 统一 runner 能避免每次为不同 Electron 应用重写大量脚本。
- 能力探测能把“工具不可用”和“应用验证失败”区分开。

位置（Where）:

- 文件/模块（Files/modules）: `skills/electron-ui-verifier/scripts/electron_verify.py`
- API/配置（APIs/configs）: CLI 参数、workflow 输入、artifact 输出。
- 测试/文档（Tests/docs）: runner dry-run、probe smoke、workflow 示例。

参考来源（References）:

- Playwright `connect_over_cdp` 文档。
- Chrome DevTools Protocol `/json/version`、target WebSocket、Runtime/Page/Input domain。

验证（Validation）:

- `python electron_verify.py --help`
- `python electron_verify.py probe --cdp http://127.0.0.1:<port> --out <artifacts>`
- 用 mock 或真实 CDP endpoint 验证失败路径能输出结构化错误。
- 验证多 target 候选时能输出候选列表并停止。

风险和回滚（Risks and rollback）:

- 风险：一次实现过多 backend 导致复杂。
- 回滚：v1 保留 raw CDP 和 Playwright CDP 探测，MCP 只记录为可选外部工具。

阶段契约（Stage Contract）:

- 范围（Scope）: runner 基础设施。
- 允许修改（Allowed changes）: `electron_verify.py`、示例 workflow、相关文档。
- 禁止修改（Forbidden changes）: 不引入系统级驱动。
- 进入条件（Entry checks）: scaffold 已验证。
- 退出条件（Exit checks）: help/probe/dry-run 可用。
- 必需验证（Required validation）: CLI 和错误路径验证。
- 是否预期提交（Commit expected）: yes。

### 阶段 4（Stage 4）：workflow action DSL

目标（Goal）:

- 实现最小稳定 action 集，覆盖常见 UI 验证工作流。

做法（How）:

- 支持 `waitText`、`waitUrlContains`、`snapshot`、`clickText`、`clickXY`、`fillText`、`pressKey`、`screenshot`、`extractText`、`extractTable`。
- `clickText` 优先使用文本定位和 DOM 坐标，失败时给出候选元素和截图，不盲目点击。
- `extractTable` 支持普通 table、虚拟列表的可见文本提取和 regex 兜底。

原因（Why）:

- 这些 action 足以覆盖“进入最新案件、读取任务列表、查看工具箱功能”等 Electron 验证任务。
- 保持 action 集克制，避免 v1 变成不稳定的复杂 UI 自动化框架。

位置（Where）:

- 文件/模块（Files/modules）: `electron_verify.py`、`references/actions.md`、`assets/workflow.example.json`
- API/配置（APIs/configs）: workflow JSON action schema。
- 测试/文档（Tests/docs）: action 示例和错误示例。

参考来源（References）:

- Chrome DevTools Protocol `Runtime.evaluate`、`Input.dispatchMouseEvent`、`Page.captureScreenshot`。
- Playwright locator/click/screenshot 能力作为高层 backend 参考。

验证（Validation）:

- 对 mock HTML 页面验证 wait、click、extract、screenshot。
- 对真实 Electron CDP endpoint 做至少一次 snapshot/screenshot smoke。

风险和回滚（Risks and rollback）:

- 风险：文本定位在国际化、多窗口、虚拟列表中不稳定。
- 回滚：要求 workflow 提供更明确 selector 或坐标 fallback，并在报告中标记不确定性。

阶段契约（Stage Contract）:

- 范围（Scope）: v1 action DSL。
- 允许修改（Allowed changes）: runner action 执行、action 文档、示例。
- 禁止修改（Forbidden changes）: 不实现破坏性批量操作和任意业务脚本模板。
- 进入条件（Entry checks）: runner 核心可用。
- 退出条件（Exit checks）: action 示例可执行。
- 必需验证（Required validation）: mock + smoke。
- 是否预期提交（Commit expected）: yes。

### 阶段 5（Stage 5）：证据报告和 harness 集成

目标（Goal）:

- 让 verifier 输出可用于 harness 验证结论的证据。

做法（How）:

- 每次运行输出 `report.json`、`summary.md`、`events.ndjson`、截图、DOM snapshot 和 backend capability。
- 报告必须记录成功、失败、未覆盖、fallback 原因、环境信息和 artifact 路径。
- `report.json` 必须包含 `schemaVersion: 1`、target metadata 和 step-level 结果。
- `summary.md` 必须区分 passed、failed、skipped 和 not covered。
- 文档要求 agent 把关键证据摘录到 `.harness/tasks/<date>/<task>/artifacts/` 或 `execution-plan.md`。

原因（Why）:

- GUI 验证必须有截图、日志或报告作为证据，不能只靠自然语言描述。
- fallback 记录能解释为什么没有使用 Playwright/MCP。

位置（Where）:

- 文件/模块（Files/modules）: `electron_verify.py`、`references/workflow.md`
- API/配置（APIs/configs）: report schema。
- 测试/文档（Tests/docs）: 报告样例和验证说明。

参考来源（References）:

- `complex-coding-harness` 验证证据和最终交付规则。
- Playwright trace/screenshot 文档作为证据思路参考。

验证（Validation）:

- 检查报告 JSON 可解析。
- 检查截图文件存在且非空。
- 检查 report schemaVersion、target metadata 和 step-level 状态字段。
- 检查失败 workflow 也能输出失败报告。

风险和回滚（Risks and rollback）:

- 风险：artifact 太多污染仓库。
- 回滚：默认输出到 `.harness/tasks/**/artifacts/` 或 `.tmp/`，不提交 runtime artifact。

阶段契约（Stage Contract）:

- 范围（Scope）: 证据输出和 harness 使用说明。
- 允许修改（Allowed changes）: runner 报告、workflow 文档。
- 禁止修改（Forbidden changes）: 不提交截图或运行产物，除非用户确认。
- 进入条件（Entry checks）: action DSL 可用。
- 退出条件（Exit checks）: 成功和失败路径均有报告。
- 必需验证（Required validation）: report parse、artifact 检查。
- 是否预期提交（Commit expected）: yes。

### 阶段 6（Stage 6）：skill 文档和故障排查

目标（Goal）:

- 写清楚 agent 如何使用该 skill 验证 Electron 应用，并避免长任务过程中遗忘关键规则。

做法（How）:

- `SKILL.md` 只保留触发条件、核心流程、必须读取的 reference 和硬规则。
- `workflow.md` 写驱动选择、process-manager 集成、harness 证据落盘和恢复流程。
- `actions.md` 写 workflow DSL。
- `troubleshooting.md` 写 Playwright/MCP attach 失败、端口、旧 Electron、后台服务、权限、窗口不可见等处理。

原因（Why）:

- 复杂规则放 references，保持 `SKILL.md` 轻量，符合 progressive disclosure。
- 长任务中通过 workflow 明确要求每次验证前复查 skill 规则和 harness 任务记录。

位置（Where）:

- 文件/模块（Files/modules）: `SKILL.md`、`references/*.md`
- API/配置（APIs/configs）: 无。
- 测试/文档（Tests/docs）: skill validation、规则检索。

参考来源（References）:

- `skill-creator` progressive disclosure。
- `complex-coding-harness` 恢复流程和阶段门禁。

验证（Validation）:

- `quick_validate.py skills/electron-ui-verifier`
- 检查文档没有重复、冲突和过度膨胀。

风险和回滚（Risks and rollback）:

- 风险：文档过多导致 agent 不读。
- 回滚：压缩 `SKILL.md`，把细节移到 references，并在 SKILL 中写明确读取条件。

阶段契约（Stage Contract）:

- 范围（Scope）: skill 使用说明和故障排查。
- 允许修改（Allowed changes）: `SKILL.md`、`references/`。
- 禁止修改（Forbidden changes）: 不添加 README/安装手册等冗余文件。
- 进入条件（Entry checks）: runner 和 action 行为已稳定。
- 退出条件（Exit checks）: 文档和脚本一致。
- 必需验证（Required validation）: quick validation、文档 review。
- 是否预期提交（Commit expected）: yes。

### 阶段 7（Stage 7）：分层验证和真实 smoke

目标（Goal）:

- 验证 skill 在无 GUI mock、CDP endpoint 和真实 Electron 场景中的基本可靠性。

做法（How）:

- 优先做 finite command 验证：Python 编译、help、JSON parse、dry-run、mock action。
- 如果用户允许，使用 `D:\VideoForensic\VideoForensic.exe --remote-debugging-port=<port>` 或用户已启动的 endpoint 做真实 smoke。
- 如果需要启动长期 Electron 进程，先读取 `process-manager`，通过 `pm_*` 管理；如果用户手动启动，则 verifier 只连接 endpoint。

原因（Why）:

- mock 覆盖脚本逻辑，真实 smoke 覆盖 Electron/CDP 差异。
- 真实 exe 依赖本机环境，不能作为所有环境必需条件。

位置（Where）:

- 文件/模块（Files/modules）: `scripts/electron_verify.py`、`.tmp/` 或 `.harness/tasks/**/artifacts/`
- API/配置（APIs/configs）: workflow 示例。
- 测试/文档（Tests/docs）: validation evidence table。

参考来源（References）:

- 前期 VideoForensic 可行性测试记录。
- `process-manager` workflow。

验证（Validation）:

- `python -m py_compile skills/electron-ui-verifier/scripts/electron_verify.py`
- `python skills/electron-ui-verifier/scripts/electron_verify.py --help`
- workflow dry-run 或 mock run。
- 可选真实 smoke：probe、snapshot、screenshot、extract。

风险和回滚（Risks and rollback）:

- 风险：真实应用需要后台服务或登录态，导致 smoke 不稳定。
- 回滚：记录无法执行原因，保留 mock + endpoint probe 作为替代证据，不虚报真实验证通过。

阶段契约（Stage Contract）:

- 范围（Scope）: 验证和证据收集。
- 允许修改（Allowed changes）: 测试辅助、临时 artifacts、必要 bugfix。
- 禁止修改（Forbidden changes）: 不把本机私有 exe 路径写成 skill 的强依赖。
- 进入条件（Entry checks）: 文档和 runner 已完成。
- 退出条件（Exit checks）: 必需验证完成或记录替代证据。
- 必需验证（Required validation）: 编译、help、dry-run、报告解析。
- 是否预期提交（Commit expected）: yes，若有实现或文档改动。

### 阶段 8（Stage 8）：最终审查、提交和交付

目标（Goal）:

- 完成 code review、验证汇总、changelog 或等价记录、commit 和最终交付。

做法（How）:

- 复读 skill、runner、references、workflow 示例和 harness 任务记录。
- 对照 Plan Self-Review 检查缺陷、缺失项、风险和一致性。
- 按规范 `git commit -F` 提交，bullet 之间不留空行。

原因（Why）:

- 保证长任务不会在阶段边界提前停止，最终证据和代码状态一致。

位置（Where）:

- 文件/模块（Files/modules）: 全部本任务涉及文件。
- API/配置（APIs/configs）: 无新增环境要求则不改 `.harness/environment.md`。
- 测试/文档（Tests/docs）: 最终验证表和 commit log。

参考来源（References）:

- `complex-coding-harness` 最终交付门禁。

验证（Validation）:

- quick validation、Python 编译、runner help、workflow dry-run、报告解析、可选真实 smoke。
- Git diff check。

风险和回滚（Risks and rollback）:

- 风险：阶段验证遗漏或 artifact 未记录。
- 回滚：补充验证后再提交；不能把未执行验证写成通过。

阶段契约（Stage Contract）:

- 范围（Scope）: 最终审查、验证和提交。
- 允许修改（Allowed changes）: 小修复、任务记录、commit message 文件。
- 禁止修改（Forbidden changes）: 不扩大功能范围。
- 进入条件（Entry checks）: 所有实现阶段完成。
- 退出条件（Exit checks）: 最终交付门禁通过。
- 必需验证（Required validation）: 全部必需验证汇总。
- 是否预期提交（Commit expected）: yes。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- Python：用于 `electron_verify.py`、JSON 处理、报告生成和 smoke 脚本。
- Playwright：可选后端；如果当前 Python 或 Node 环境已安装则使用，否则不强制作为 v1 必需依赖。
- Playwright MCP：可选验证工具；只有用户明确要求或环境可用时启用。
- Chrome DevTools Protocol：raw CDP fallback 的基础能力。
- process-manager：如果后续需要由 agent 启动长期 Electron 进程或 dev server，则必须使用。

临时覆盖（Temporary overrides）:

- 当前规划阶段无临时覆盖。
- 后续真实 smoke 可使用 `.tmp/` 或 `.harness/tasks/**/artifacts/` 保存截图和报告。

## Git 上下文（Git Context）

主分支（Main branch）:

- main

任务类型（Task type）:

- feature

工作分支（Working branch）:

- 当前规划阶段仍在 `main` 写 planning state。
- 后续实现阶段应切换或创建 `harness/feature`，并按规则同步 `main`。

分支动作（Branch action）:

- planning-only: not-applicable
- implementation: create/reuse `harness/feature`

同步来源（Sync source）:

- origin/main

最近同步（Last sync）:

- 当前规划阶段未执行 merge。

分支占用（Branch occupancy）:

- 当前只做规划，不检查 `harness/feature` 占用。
- 实施前必须串行检查 `git log main..HEAD` 和 `git -c diff.autoRefreshIndex=false diff main...HEAD --name-only`。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git。
- 非 Git 文件读取和文本搜索可以并发，但不能和 Git 命令混在同一并发批次。

只读 Git 选项（Read-only Git options）:

- 状态检查优先：`git --no-optional-locks status --short --branch`
- diff 检查优先：`git -c diff.autoRefreshIndex=false diff <range>`
- 当前仓库存在 ownership 保护时使用一次性 `-c safe.directory=E:/work/hl/videoForensic/AI/dev-skills`。

Index lock 恢复策略（Index lock recovery）:

- 按 `complex-coding-harness` 当前规则执行。
- 只删除 `git rev-parse --git-path index.lock` 解析出的精确 lock，且必须确认无活跃 Git 进程。

Git Lock Recovery Log:

| 时间（Time） | lock 路径（Lock path） | 文件大小/mtime（Size/mtime） | Git 进程检查（Process check） | 操作（Action） | 后续 status（Follow-up status） |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

提交策略（Commit policy）:

- 当前规划阶段不提交，除非用户要求提交规划文件。
- 后续实现阶段如获批准，阶段提交使用 `git commit -F .harness/tasks/<date>/<task-slug>/tmp/commit-message.txt`。
- 禁止使用多个 `-m` 分别传入 bullet。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: no
- 未合回时代码停留在（If not merged, code remains on）: implementation should remain on `harness/feature`
- 合并前需要用户确认（User confirmation needed before merge）: yes

分支安全（Branch safety）:

- 切换前已检查工作区：planning 阶段已串行检查 status。
- 不自动 stash：yes
- 不自动 rebase：yes
- 不自动 reset：yes

热修复插入（Hotfix interruption）:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支。
- 决策：当前不适用。

未解决问题（Open issues）:

- 当前规划阶段未进入实现分支；实现前需要重新检查 Git 安全状态。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| Python | runner、报告、mock 验证 | 3-8 | available / to-check | 版本差异 | 限制 Python 3.10+ 或当前可用版本 | 实施前确认 |
| Playwright Python/Node | 高层 Electron/CDP 后端 | 3-7 | optional | 旧 Electron attach 失败 | raw CDP fallback | 安装依赖需确认 |
| Playwright MCP | agent UI 操作后端 | 3-7 | optional | MCP 与目标 Electron 不兼容 | runner raw CDP | 使用需确认 |
| CDP | raw fallback | 3-7 | required for packaged exe | 协议差异 | Playwright Electron dev mode | 不需额外确认 |
| stdlib WebSocket transport | raw CDP 通信 | 3-7 | planned | 协议实现缺陷 | 重新批准后使用第三方库 | 新增依赖需确认 |
| process-manager | 长期进程管理 | 7 | available | manager 离线 | 用户手动启动 app 后仅连接 | 启动 manager 需确认 |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- planning 阶段：no
- implementation 验证阶段：conditional

process-manager skill 是否存在（process-manager skill available）:

- yes

规则结论（Rule decision）:

- 如果后续由 agent 启动 Electron exe、Electron dev app、前端 dev server 或后端服务，必须使用 `process-manager`。
- 如果用户已手动启动 Electron 应用并提供 CDP endpoint，verifier 只连接，不需要管理该进程。
- finite command，例如 Python 编译、help、dry-run、JSON parse，不进入 `process-manager`。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Electron app smoke | other | 7 | conditional | CDP endpoint / log / process | pending | artifacts/report | pending |

禁止 shell 后台启动确认（No shell background start）:

- yes

历史视图需求（Needs `pm_list --history`）:

- no，除非排查历史进程记录。

证据保留位置（Evidence retention location）:

- `.harness/tasks/2026-07-01/feature/electron-ui-verifier-skill/artifacts/`

日志沉淀确认（Log evidence persisted）:

- implementation 阶段后确认。

每阶段复查要求（Per-stage reread requirement）:

- 每个实现阶段开始前复查本节。
- 任何启动长期 Electron 或 dev server 前必须复查本节和 `process-manager` workflow。
- 上下文压缩或中断恢复后必须复查本节和 `Resume Summary`。

## 验证（Validation）

必需验证（Required）:

- `quick_validate.py skills/electron-ui-verifier`
- `python -m py_compile skills/electron-ui-verifier/scripts/electron_verify.py`
- `python skills/electron-ui-verifier/scripts/electron_verify.py --help`
- workflow JSON parse / dry-run。
- 至少一个 mock 或可控 CDP endpoint 验证 snapshot、screenshot、extract。
- 报告 JSON 可解析，截图或替代 artifact 存在且非空。
- target discovery 能列出候选窗口；target 不唯一且无选择规则时必须停止。
- raw CDP transport 覆盖本机 ws endpoint 的 handshake、send、receive、close 和错误路径。
- report schemaVersion、target metadata、step-level status 必须存在。

已执行（Executed）:

- 当前规划阶段：未执行实现验证。
- 当前已执行：读取 harness、process-manager、skill-creator 规则；完成外部资料调研；串行 `git status`；完整复读本计划；校验 `.harness/active-task.json` 可解析。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | 文档复读 + active-task JSON 校验 | pass | 规划完整性和恢复入口 | 实现验证 | 本文件、`.harness/active-task.json` | 等待用户批准 |
| Stage 2 | quick_validate | pass | skill frontmatter 和基础结构 | 真实 UI | command output | 已通过 |
| Stage 3 | py_compile + help | pass | runner 语法和 CLI | 真实 UI | command output | 已通过 |
| Stage 3 | raw CDP transport mock | pass | WebSocket/CDP 基础通信 | 真实 Electron 协议差异 | `artifacts/mock-cdp/report.json` | 已通过 |
| Stage 4 | mock workflow | pass | snapshot、screenshot、report 输出 | 真实 Electron 差异 | `artifacts/mock-cdp/report.json` | 已通过 |
| Stage 5 | report schema check | pass | schemaVersion、target、step 状态 | 报告语义正确性 | `artifacts/mock-cdp/report.json` | 已通过 |
| Stage 7 | VideoForensic smoke | blocked | 真实 Electron 应用 | 管理员权限启动 | process-manager WinError 740 | 等待用户手动启动 9223 |

可选验证（Optional）:

- Playwright CDP attach 成功路径。
- Playwright MCP `--cdp-endpoint` 工具路径。
- `D:\VideoForensic\VideoForensic.exe` 真实 smoke。
- Windows 原生窗口 fallback 只记录研究，不进入 v1 验证。

产物（Artifacts）:

- 截图（Screenshot）: `.harness/tasks/2026-07-01/feature/electron-ui-verifier-skill/artifacts/*.png`
- 日志（Log）: `events.ndjson`、stderr/stdout 摘要。
- Trace: v1 不强制；Playwright 后端可选。
- 报告（Report）: `report.json`、`summary.md`

未覆盖（Not covered）:

- UAC、系统文件选择器、托盘菜单、非 Electron 原生窗口。
- 需要真实后端服务和登录态的业务深层流程，除非用户提供环境和验收路径。

无法执行时（If unable to run）:

- 必须记录原因、影响和替代证据。
- 不能把未执行真实 smoke 写成通过。
- 如果 Playwright/MCP 不可用，记录失败原因并使用 raw CDP；如果 raw CDP 也失败，停止并说明阻塞。
- 如果 target 不唯一且用户或 workflow 未指定选择规则，停止并输出候选 target，不做猜测点击。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/electron-ui-verifier/SKILL.md`
- `skills/electron-ui-verifier/references/workflow.md`
- `skills/electron-ui-verifier/references/actions.md`
- `skills/electron-ui-verifier/references/troubleshooting.md`
- `skills/electron-ui-verifier/assets/workflow.example.json`

Changelog 计划（Changelog plan）:

- 当前仓库不强制新增 skill 内 CHANGELOG。
- 如仓库根已有 CHANGELOG 或用户要求，可追加单条记录。
- 阶段记录优先写入本 `execution-plan.md` 的 `Implementation Progress` 和 `Commit Log`。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `execution-plan.md` | yes | 二级章节 | 写完完整复读 |
| `SKILL.md` | no/unknown | frontmatter + core workflow | quick_validate + 完整复读 |
| `electron_verify.py` | yes | 完整类/函数/命令组 | py_compile + help + smoke |
| `workflow.md` | yes | 二级章节 | 完整复读 |
| `actions.md` | yes | action 分组 | 完整复读 + 示例校验 |
| `troubleshooting.md` | no/unknown | 故障类别 | 完整复读 |
| `workflow.example.json` | no | 完整 JSON 对象 | JSON parse |

写入规则（Write rules）:

- 分段 patch 是落盘策略，不是思考策略。
- 大内容首次写入前先形成全局框架，再分模块递进式细化，最后整体复查。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 分段判断不是最终内容长度承诺，不能为了符合预测删功能、删验证或删文档。
- 目标文件超过 500 行时默认禁止整文件重写。

整体复查（Whole-file review）:

- 写完后重新读取完整目标文件。
- 检查章节顺序、引用、命名、重复内容、占位符、门禁状态和阶段一致性。
- 代码文件还要执行编译、help 和 smoke 验证。

patch 失败处理（Patch failure handling）:

- 先读取目标文件确认是否有部分写入。
- 如果上下文不匹配，重新读取相关片段后只修正失败段。
- 如果 patch 过大，继续缩小段落，不重复写已成功段。
- 不用 shell 拼接文件绕过 `apply_patch`。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | closed | 是否允许用 `D:\VideoForensic\VideoForensic.exe` 做真实 smoke | 用户确认自动化测试使用 VideoForensic；当前因 exe 需要管理员权限，等待用户手动启动 CDP endpoint | Stage 7 |
| D-002 | yes-before-install | closed | 是否允许安装 Playwright 依赖 | 用户确认当前 Python 环境已有 Playwright 依赖；优先使用现有依赖，不新增安装 | Stage 3 |
| D-003 | no | open | 是否把 Windows 原生窗口自动化纳入 v1 | 默认不纳入 v1 | Scope |
| D-004 | yes-before-install | closed | 如果 stdlib WebSocket transport 不可维护，是否允许安装第三方 WebSocket 库 | 用户允许；仍优先使用 stdlib-only 或现有依赖，新增安装前记录原因 | Stage 3 |
| D-005 | yes-before-remote | closed | 是否允许连接非 localhost 的 CDP endpoint | 用户允许；默认仍优先 localhost，远程连接需记录 endpoint 来源 | Security |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pass | Context 证据等级表 |
| 影响面矩阵完整（Impact matrix complete） | pass | Impact Matrix 覆盖 API、数据、UI、环境、兼容性、测试、文档 |
| 候选方案比较充分（Options compared enough） | pass | 比较 Playwright/MCP 指南、结构化 verifier、泛 Windows 自动化 |
| 每阶段可独立验证（Stages independently verifiable） | pass | Stage 1-8 均含验证和退出条件 |
| 方案变更触发条件清楚（Reapproval triggers clear） | pass | Decision 章节 |
| 用户批准摘要可记录（Approval summary ready） | pass | Plan Approval 章节 |

质量结论（Quality result）:

- `pass`

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- `pass-after-review-fixes`

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 初始方案容易把 Playwright/MCP 当唯一后端；raw CDP transport 依赖不明确 | 明确 raw CDP fallback、backend capability 和 stdlib-only WebSocket 策略 | pass |
| 优化（Optimizations） | v1 范围可能过大；多窗口 target 选择可能隐式猜测 | 收缩到 Electron 专项和最小 action 集；补充 target discovery/selection | pass |
| 缺失项（Missing items） | 需要 process-manager、真实 smoke、report schema 和安全边界 | 补充 Process Manager Gate、可选 smoke、schemaVersion、localhost-only 和敏感信息约束 | pass |
| 风险（Risks） | GUI 验证可能不可复现；远程 CDP 或第三方依赖可能扩大风险 | 补充 mock、dry-run、artifact、未覆盖声明、D-004/D-005 阻塞条件 | pass |
| 一致性（Consistency） | planning-only 与后续 run-to-completion 需区分；新增问题需同步门禁 | Execution Control 中区分当前和批准后状态；Readiness 保持 pass-for-plan-approval | pass |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：no
- `Plan Self-Review` 是否需要重跑：no
- `Readiness Gate` 是否需要重跑：no
- 原因：当前复查修复未改变总体目标、阶段边界或默认实现范围，只补充实现约束、阻塞条件和验证项。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pass | Problem |
| 上下文已收集（Context collected） | pass | Context |
| 候选方案已比较（Options compared） | pass | Options |
| 决策已记录（Decision recorded） | pass | Decision |
| 实施阶段已细化（Implementation stages detailed） | pass | Implementation Plan |
| 环境已确认（Environment confirmed） | pass-with-open-items | Environment；依赖安装实施前确认 |
| Git 上下文已确认（Git context confirmed） | pass-for-planning | Git Context |
| 工具已确认（Tooling confirmed） | pass-with-open-items | Tooling |
| 验证已确认（Validation confirmed） | pass | Validation |
| 最终交付证据已规划（Final delivery evidence planned） | pass | Validation Artifacts |
| 文档更新已确认（Documentation updates confirmed） | pass | Documentation |
| 风险已识别（Risks identified） | pass | Risks and rollback |
| 规划自查已通过（Plan self-review passed） | pass | Plan Self-Review |
| 阻塞问题已关闭（Blocking questions closed） | pass-for-planning | D-002/D-004 仅在新增依赖前阻塞；D-005 仅在远程 CDP 前阻塞 |

就绪结论（Readiness result）:

- `pass-for-plan-approval`

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 用户确认：D-002 当前 Python 环境已有 Playwright 依赖；其它阻塞项均允许；自动化测试使用 `D:\VideoForensic\VideoForensic.exe` 做测试；准备好后按规划实现。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: 按本计划实现 `electron-ui-verifier` skill。
- 阶段提交授权（Stage commit authorization）: 默认每阶段完成 review 和验证后提交。
- 工具/MCP 授权（Tool/MCP authorization）: 允许使用当前 Python Playwright；允许 VideoForensic 真实 smoke。
- 文档更新授权（Documentation authorization）: 允许更新 skill 文档、示例和任务记录。
- 依赖和远程连接授权（Dependency/remote authorization）: 用户已允许；实现仍优先使用现有依赖和本机 endpoint，新增安装或远程连接需记录原因。

提交策略（Commit policy）:

- `stage_commits_authorized`

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- in_progress

当前阶段（Current stage）:

- Stage 2

已完成阶段（Completed stages）:

- Stage 1 planning document drafted

剩余阶段（Remaining stages）:

- Stage 2 skill scaffold
- Stage 3 verifier runner core
- Stage 4 workflow action DSL
- Stage 5 evidence reporting
- Stage 6 skill docs and troubleshooting
- Stage 7 validation and smoke
- Stage 8 final review and delivery

下一步自动动作（Next automatic action）:

- continue Stage 2 skill scaffold

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no, approved run-to-completion task must continue through all remaining stages unless a Stop Condition is active.

active-task 同步字段（active-task sync fields）:

```json
{
  "execution_mode": "planning-only",
  "overall_status": "awaiting_plan_approval",
  "current_stage": "Stage 1",
  "remaining_stages": ["Stage 2", "Stage 3", "Stage 4", "Stage 5", "Stage 6", "Stage 7", "Stage 8"],
  "next_automatic_action": "wait for user approval",
  "stop_condition": "awaiting user approval",
  "state_source": "execution-plan.md"
}
```

状态同步规则（State sync rules）:

- `execution-plan.md` 是唯一主契约。
- `.harness/active-task.json` 只作为恢复入口和摘要索引。
- 用户批准后，执行模式应改为 `run-to-completion`，不能在阶段边界提前停止。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Stage 1 | completed-for-planning | 已落盘 Electron UI verifier skill 详细规划 | 文档复查已完成；active-task JSON 已校验 | 本文件 | 等待用户批准 |
| Stage 2 | completed | skill scaffold | quick_validate pass | `skills/electron-ui-verifier/` | Stage 3 已继续 |
| Stage 3 | completed | verifier runner core | py_compile/help/mock CDP pass | `electron_verify.py`、mock report | Stage 4 已继续 |
| Stage 4 | completed | workflow action DSL | mock workflow pass | `artifacts/mock-cdp/report.json` | Stage 5 已继续 |
| Stage 5 | completed | evidence reporting | report schema check pass | `artifacts/mock-cdp/report.json` | Stage 6 已继续 |
| Stage 6 | completed | skill docs | quick_validate pass | `SKILL.md`、references、assets | Stage 7 已开始 |
| Stage 7 | blocked | validation and smoke | mock pass；VideoForensic blocked | WinError 740 | 等待用户手动启动 `D:\VideoForensic\VideoForensic.exe --remote-debugging-port=9223` |
| Stage 8 | pending | final review and delivery | pending | pending | Stage 7 后 |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | pass-for-planning | none | pass | not-applicable | pass | pass |
| Stage 2 | pending | plan approval required | pending | conditional | pending | pending |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | pass | pass | pass | not-applicable | not-applicable | pass | not-applicable | pass |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证已完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | pass | pass | pass | not-applicable | yes | awaiting approval | yes | pass | pass | yes | wait for user approval |

结论（Decision）:

- 当前只允许停在方案批准门禁；用户批准前不进入 Stage 2。

规则（Rules）:

- 用户批准后，执行模式切换为 `run-to-completion`。
- 进入实现后，如果还有 pending stage 且没有停止条件，不得在阶段边界停止。

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Stage 1 | 当前无代码改动 | follow-up | 已完整复读规划文档；无代码审查问题 |

## 恢复摘要（Resume Summary）

- 整体目标（Overall goal）: 规划并准备实现 `electron-ui-verifier` skill。
- 执行模式（Execution mode）: planning-only。
- 整体任务状态（Overall status）: awaiting_plan_approval。
- 已完成阶段（Completed stages）: Stage 1 planning draft。
- 当前阶段（Current stage）: Stage 7。
- 剩余阶段（Remaining stages）: Stage 7-8。
- 最新 commit（Latest commit）: none。
- 下一步自动动作（Next automatic action）: wait for VideoForensic CDP endpoint, then run Stage 7 smoke。
- 当前停止条件（Current stop condition）: VideoForensic requires elevated manual start。
- 状态来源（State source of truth）: execution-plan.md。
- 长期进程规则（Process manager rule）: 后续启动长期 Electron/dev server 必须使用 process-manager；用户手动启动 endpoint 时只连接。
- 未覆盖/风险（Not covered/risks）: 真实 VideoForensic smoke 尚未完成；process-manager 启动外部 exe 返回 WinError 740，需要用户以管理员权限手动启动 9223 endpoint；Windows 原生窗口自动化不属于 v1。
- 不得停止说明（Do not stop note）:
  - 当前 planning-only 必须等待批准；批准后 run-to-completion，阶段边界不是停止条件。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/<date>/<task-slug>/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Stage 2-6 | dev-skills | 8e7e64c | feat(electron-ui-verifier): 实现 Electron UI 验证 skill | execution-plan.md |

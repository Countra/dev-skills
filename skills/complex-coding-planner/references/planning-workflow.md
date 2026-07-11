# Complex Coding Planner Workflow

本文件只描述规划阶段。实现、运行状态、执行证据和最终提交由 `complex-coding-executor` 负责。字段与状态语义见 `task-contract.md`。

## 目录

1. [任务路由](#任务路由)
2. [规划画像](#规划画像)
3. [任务制品](#任务制品)
4. [规划流程](#规划流程)
5. [自主消歧](#自主消歧)
6. [Research Gate](#research-gate)
7. [Standards Discovery Gate](#standards-discovery-gate)
8. [Development Quality Gate](#development-quality-gate)
9. [代码探索](#代码探索)
10. [计划与契约](#计划与契约)
11. [规划门禁](#规划门禁)
12. [Git、工具与进程](#git工具与进程)
13. [批准与交接](#批准与交接)
14. [Plan Amendment Gate](#plan-amendment-gate)
15. [文件写入](#文件写入)

## 任务路由

先区分生命周期，再决定 managed 任务的规划深度：

| 路由 | 条件 | 行为 |
| --- | --- | --- |
| `direct` | 目标清晰、局部、低风险、短时且不需要恢复 | 不创建 task bundle；若用户请求执行，交回普通 direct coding flow |
| `managed` | 多阶段、跨模块、高风险、长时、外部写入、公共契约或用户要求持久规划 | 创建 task bundle 并完成本流程 |
| `blocked` | 经自主消歧后仍缺少业务取舍、权限、秘密或不可替代输入 | 记录阻塞问题并停止 |

不要把“需要先调查”直接等同于 blocked。能从仓库、配置、官方资料或低成本探针确定的内容，应先自主确认。

## 规划画像

managed 任务使用 `lite`、`standard` 或 `full`。记录以下信号及证据：

- 影响面：文件、模块、仓库、公共接口和数据范围。
- 不确定性：目标、技术事实和验证方式的未知程度。
- 时间与恢复跨度：阶段数、跨会话概率和中断成本。
- 可逆性：回滚是否简单，是否涉及迁移、权限或外部写入。
- 质量风险：安全、并发、数据完整性、架构边界和回归风险。
- 工具与授权：网络、浏览器、长期进程、提权和外部系统写入。

选择规则：

- `lite`：信号均低，通常 1-3 stages，无公共契约、迁移或外部写入。
- `full`：任一高风险信号成立，或预计超过 5 stages、跨仓库、长时恢复敏感、涉及迁移/安全/权限/外部写入。
- `standard`：其余 managed 任务。

核心方向尚未稳定且未知会改变范围、架构或验证时，先标记 `discovery-first`。discovery 只产出证据、候选方案和阻塞决策；方向稳定后再生成 approval-ready contract。

## 任务制品

```text
.harness/
  environment.md
  active-task.json
  tasks/YYYY-MM-DD/<type>/<task-slug>/
    execution-plan.md
    plan-contract.json
    pending-decisions.md       # 条件创建
    artifacts/                 # 条件创建
```

规则：

- `.harness/environment.md` 只保存稳定 workspace 事实，不追加任务进度和临时用户约束。
- `active-task.json` 只保存 task ID、task-dir、run-state 路径和更新时间。
- `execution-plan.md` 保存人类可审查意图，`plan-contract.json` 保存机器可验证契约。
- 批准前 planner 独占 plan、contract 和 planning artifacts；批准后全部不可变。
- 不预创建空 artifact。只有 profile 或风险触发时才生成并写入 contract index。

Artifact 策略：

| Artifact | lite | standard | full |
| --- | --- | --- | --- |
| research findings | 内联 | 证据较多时独立 | 必需 |
| standards index | 内联 | 建议独立 | 必需 |
| change map | 简表内联 | 必需 | 必需 |
| traceability | contract 内联关系 | 需求密集时独立 | 必需 |
| plan critique | 不需要 | 条件启用 | 高风险时必需 |

## 规划流程

1. 读取项目规则、active pointer、稳定环境和已有 task bundle。
2. 完成任务路由、profile 选择和 discovery-first 判断。
3. 收集本地实现、调用方、配置、数据、测试和错误路径。
4. 完成自主消歧与 Research Gate；必要时使用在线官方或一手资料。
5. 完成 Standards Discovery Gate 和 Development Quality Gate。
6. 形成 options、decision、change map、requirements、acceptance 和 validation mapping。
7. 生成 `execution-plan.md`、`plan-contract.json` 和触发的 artifacts。
8. 运行 planner checker `draft`，修复结构、ID、DAG、引用和 profile 问题。
9. 完成 Plan Quality Gate、Plan Self-Review，必要时做独立 critique。
10. 运行 planner checker `approval` 并完成 Readiness Gate。
11. 将 pointer 写入 `.harness/active-task.json`，请求用户批准后停止。

lite 通常 1-3 stages，standard 2-5 stages，full 3-7 stages。超过 7 个阶段必须解释为何不能合并。

## 自主消歧

按以下顺序处理未知：

1. 搜索仓库中的定义、调用、配置、测试、历史实现和文档。
2. 查询官方文档、标准、源码或 release notes。
3. 运行最便宜且无破坏性的区分性探针。
4. 记录假设、证据强度和不同答案对方案的影响。
5. 只把仍需业务偏好、权限、秘密或不可替代输入的问题交给用户。

按“影响 x 不确定性”排序问题。每个用户问题说明推荐默认值、选择差异和会改变的阶段/接口/验证；避免一次提出大量低价值问题。

## Research Gate

每个 managed 任务记录一种模式：

- `none`：无外部或不稳定事实依赖，并说明原因。
- `local-only`：本地代码、配置、锁文件和用户资料足以确认。
- `online-required`：涉及可能变化的框架、API、协议、工具、模型、依赖、平台行为、法规或高风险事实。
- `blocked-by-access`：需要的一手资料因网络、权限或私有访问不可用。

规则：

- 优先官方文档、标准、源码仓库、release notes、论文和厂商文档。
- 记录查询、来源 URL/路径、访问日期、结论、可信度、适用限制和方案影响。
- 关键结论不得只依赖二手资料或模型记忆。
- 无法访问时标记 assumption 或 blocker，并说明影响与替代证据，不伪造 confirmed。
- 新来源连续不再改变问题定义、影响面、options 或 validation 时停止搜索。

## Standards Discovery Gate

先识别语言、框架、包管理器、API 类型、数据层、部署形态和架构风险，再收集适用规范。

优先级：项目规则 > 官方语言/框架/标准 > 高质量一手参考 > 二手背景资料。

standards index 至少记录来源、URL/路径、访问日期、适用范围、必须/参考级别和不适用原因。语言规范可从 Google styleguide、语言官方规范或项目配置开始；Web/API 项目还应查框架工程结构、协议和 API design guidance。不要把规范全集复制进 skill。

## Development Quality Gate

按 profile 深度记录：

- 代码标准：命名、格式、注释、异常、日志、配置和测试风格。
- 静态质量：syntax、format、lint、typecheck、build、unit/integration checks。
- 架构边界：职责、依赖方向、公共接口、数据所有权和迁移边界。
- 模式取舍：说明采用或拒绝抽象/设计模式的理由，避免模式驱动设计。
- 耦合与内聚：识别跨层调用、循环依赖、共享状态、重复逻辑和过宽接口。
- 验证映射：把质量要求映射到 stage、VAL、review 或替代证据。

项目规则与外部规范冲突时以项目明确规则为准，并记录取舍。规范发现若改变范围、接口、风险或必需验证，必须进入重新决策。

## 代码探索

change map 必须覆盖：

- 直接修改点及其定义。
- 入口、调用方、消费者和依赖方向。
- 数据结构、配置、错误处理和权限边界。
- 相关测试、文档和生成物。
- 已检查但不受影响的邻接区域。

为发现记录 `confirmed`、`read`、`external` 或 `assumption`。按相关性读取文件；当新增证据不再改变影响面或决策时停止。不能以“阅读了很多文件”代替定位质量。

## 计划与契约

`execution-plan.md` 说明为什么这样做，至少包含：

- profile、目标、非目标、约束和证据。
- requirements、acceptance、nonfunctional requirements。
- options、decision、影响面和风险。
- Stage Contracts、验证、Git/工具/进程策略。
- Plan Quality、Self-Review、Readiness 和 Approval Request。
- artifact index 与 amendment triggers。

`plan-contract.json` 承载所有 enforceable 字段。不要从 Markdown 标题、关键词或表格推导 stage 状态、依赖、授权或验证。

同步规则：

- plan 与 contract 的 REQ/AC/NFR/STG/VAL ID 必须一致。
- must requirement 必须被 AC、stage 和 required validation 闭环覆盖。
- stage DAG 无环，所有引用存在，allowed/forbidden changes 不冲突。
- profile 必需 artifact 必须存在并在 index 中声明。
- plan 中不得包含 current stage、remaining stages、运行结果、ledger 摘要或 commit log。

具体字段、事件和错误语义见 `task-contract.md`。

## 规划门禁

### Plan Quality Gate

确认：

- 关键判断有来源和证据等级。
- Research、Standards 和 Development Quality gates 已闭环。
- 至少比较两个可区分方案；只有一个合理方案时说明排除依据。
- change map 覆盖接口、数据、配置、测试、文档和调用链。
- 每个 stage 有可观察退出条件、风险、回滚和独立验证。
- requirements、acceptance、stages 和 validations 可追踪。
- 授权、长期进程、Git、文档与最终证据要求明确。

### Plan Self-Review

主动检查并修复：

- 缺陷：矛盾、错误假设、断链引用、不可执行步骤。
- 优化：不必要阶段、artifact、抽象、用户问题或验证成本。
- 缺失：环境、调用方、错误路径、权限、回滚、文档或提交策略。
- 风险：高风险行为缺少缓解、替代证据或 fail-closed 行为。
- 一致性：plan、contract、artifacts 和 active pointer 漂移。
- 开发质量：规范、静态质量、架构、模式、耦合和内聚缺口。

full/高风险任务优先使用 clean-context critique。若独立 evaluator 不可用，执行 deterministic checker + self-review，并明确记录降级；不得伪造独立评审。

### Readiness Gate

依次确认 Plan Quality、Self-Review、planner `approval` checker、无 blocker、artifact 完整、Git/工具/验证可执行和批准摘要已准备。Readiness 只表示可以请求批准，不授权实现。

## Git、工具与进程

- 记录主分支、工作分支、同步来源、分支占用、串行 Git 策略、index.lock 恢复和提交授权。
- 不自动 stash、reset、rebase、切分支或覆盖未知改动。
- 列出实施需要的 shell、语言运行时、浏览器/MCP、外部服务和降级路径。
- 识别长期进程；若需要，写 Process Manager Gate，规划统一 `pm_manager.py status|start`、authenticated manager identity、service validation、`processKey`、readiness、bounded logs、graceful/force stop 与 owner-empty cleanup 证据。finite commands 不进入 process-manager。
- Process Manager Gate 不得要求调用方判断 OS/backend 或先运行 doctor；只有统一操作失败且 selection reason 不清楚时才规划按需诊断。缺少安全 manager 且长期进程是必需项时应设 blocker，不得改用手写后台 shell。
- 提交授权必须与实施批准分开；没有明确授权时 contract 仍要求 commit gate 拒绝。

`.harness/environment.md` 只维护长期 workspace 能力。任务特有的网络、工具、秘密、路径或限制写入 task plan/artifact；秘密值不得落盘。

## 批准与交接

请求批准前：

1. 运行 `harness_plan_check.py --task-dir <task-dir> --mode approval`。
2. 写 pointer-only `.harness/active-task.json`。
3. 向用户总结范围、breaking behavior、验证、授权请求和残余风险。
4. 停止，不实现代码、不创建 run-state/ledger、不提交。

用户批准后，批准事实和实际 authorizations 写入 `attestation.json`。planner 不回写 plan/contract；executor 验证 attestation 后初始化 ledger/run-state 并连续执行。

实施批准不等于提交授权。只有用户明确说“提交”、批准摘要明确包含提交，或后续单独授权时，attestation 才能记录 commit authorization。

## Plan Amendment Gate

以下变化必须停止并重新批准：

- approved scope、公共行为、REQ/AC/NFR 或 artifact 集合实质改变。
- stage 数量、DAG、边界、顺序或 required VAL 改变。
- 风险、依赖、数据迁移、外部写入、长期进程或授权改变。
- immutable 文件变化或 attestation mismatch。

amendment 将上一 revision 清单归档到 `artifacts/amendments/`，生成递增 `plan_revision`，重跑 approval checker，获得用户批准并生成新 attestation。执行状态必须标记 `reapproval_required`，批准前不得继续写操作。

不改变行为的诊断文案、执行 evidence 或 snapshot reconcile 不修改 immutable plan，因此不触发 amendment。

## 文件写入

- 长内容先建立全局框架，再按完整章节、函数或配置块分段 patch。
- 单次新增建议不超过 120 行，最多 200 行。
- 超过 500 行的现有文件优先定点修改，不无故整文件重写。
- patch 失败后先检查是否部分写入，再缩小锚点；不得盲目重复。
- 写完后完整重读目标文件，并检查 JSON、ID、链接、重复、顺序、末尾换行和 `git diff --check`。

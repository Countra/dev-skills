# complex-coding-harness skill 规划方案

## 1. 文档定位

本文档用于规划一个面向复杂 coding 任务的通用 skill 集合能力，暂不落地具体 skill 实现文件。

该 skill 的目标不是替代 Codex、Claude Code 或其他编码 agent 的通用能力，而是给长周期、多阶段、多文件、多仓库或高风险编码任务提供一套可恢复、可审计、可验证的工作协议。核心问题是：当对话上下文被压缩、中断或迁移后，agent 仍能通过任务文件恢复目标、当前阶段、已完成内容、验证证据和下一步工作。

## 2. 设计目标

- 让复杂 coding 任务在上下文压缩后可以稳定恢复。
- 让每个阶段都有明确的输入、输出、验证和收口动作。
- 将关键任务状态落到文件，而不是只依赖对话历史。
- 保持 skill 本身轻量，避免复制完整 harness 工程。
- 支持 Codex、Claude Code 和其他 agent 读取同一套 `skills/` 源文件。
- 参考 `taste-skill` 的普通仓库布局，不把源码主结构放在 `.agents/skills/`。

## 3. 非目标

- 首版不生成完整 `.agents/skills` 目录。
- 首版不创建插件 `.codex-plugin` 包。
- 首版不实现完整前端任务监控 UI。
- 首版不强制所有小任务创建任务目录。
- 首版不做未经批准的项目自动分析、自动提交、自动建分支或自动发布；实施阶段提交必须来自用户批准的方案和阶段执行协议。
- 首版允许在用户批准的 managed 任务中使用统一 harness 工作分支；分支名称按任务类型固定，不按任务名自动创建。
- 首版不复制 `harness-project-bootstrap` 的全量架构控制面、workspace map 和多 profile 模板。

## 4. 调研结论

### 4.1 `vibe_coding` 实践结论

`E:\work\hl\videoForensic\AI\vibe_coding` 的实践证明，复杂任务最有效的基础结构不是“大量规则文件”，而是少量可恢复入口。当时临时使用了 `task_todo.md`、`now_task.md` 和 `CHANGELOG.md`，本项目只保留其中真正有价值的部分：

- `execution-plan.md`：保存任务契约、方案研究、环境确认、验证策略、工具依赖、文档更新和 readiness gate。
- `environment.md`：保存 workspace 级开发环境清单，让多项目联调时的环境约束不随单个任务分叉。
- `active-task.json`：保存当前任务指针，避免 agent 依赖对话历史寻找任务目录。

这套结构的价值在于简单、直接、可人工阅读。即使 agent 忘记上下文，也可以通过重读这几个文件恢复任务。

需要补强的点：

- 不再把 `solution.md`、`options.md`、`environment.md`、`validation-strategy.md`、`tool-dependencies.md`、`status.md`、`state.json`、`review.md` 等拆成默认独立文件，避免规则面过大。
- 把这些内容作为 `execution-plan.md` 的固定章节，让 agent 和用户都知道“方案和环境要改哪里”。
- 例外：`.harness/environment.md` 是 workspace 级环境清单，不是任务级方案拆分文件；它用于统一多项目开发环境、验证命令和工具约束。
- 当某个章节在真实任务中反复变得过长或需要独立复用时，再按需拆分。

### 4.2 `harness-project-bootstrap` 可借鉴内容

`E:\work\hl\AI\harness-project-bootstrap` 的全量方案偏重，但其中有几个子需求非常适合抽取：

- 任务分级：区分 direct、managed、needs-clarification。
- 问题拆解：先明确目标、非目标、影响面和验收标准，再编码。
- 状态可观测：借鉴“状态必须落盘”的思想，但首版不复制 `state.json`、`events.ndjson`、`validations.json` 等多文件控制面。
- 验证边界：最终声明不得超过验证证据覆盖范围。
- 自审与验证声明边界：编码后必须先自审影响面和验证证据，最终声明不得超过证据覆盖范围。
- 验收失败复盘：用户反馈失败时续跑原任务，而不是新建任务导致上下文断裂。

不建议首版引入的内容：

- 完整架构控制面。
- workspace 多仓库拓扑分析。
- profile 条件模板。
- 前端任务监控 UI。
- 大量确定性渲染脚本。

### 4.3 `taste-skill` 目录结构结论

`https://github.com/Leonxlnx/taste-skill` 使用普通仓库结构：

```text
README.md
activity-log.md
LICENSE
skill.sh
assets/
examples/
research/
skills/
```

其中实际 skill 源文件位于 `skills/<skill-name>/SKILL.md`。这种结构适合作为本项目主结构，因为它不绑定单一 agent 的安装目录。

本项目应采用同类结构：

- `skills/` 作为源码主目录。
- `skill.sh` 作为安装适配入口。
- `research/` 保存调研材料。
- `examples/` 保存任务文件示例。
- `assets/` 仅在 skill 真的需要静态资源时创建，首版不默认创建。
- 不把主源码放进 `.agents/skills/`。

### 4.4 Codex skill 规则结论

Codex 官方资料显示，Codex skill 的核心是包含 `SKILL.md` 的目录，`SKILL.md` 需要 `name` 和 `description`。Codex 支持 repo、user、admin、system 等位置发现 skills，其中 repo 自动发现目录是 `.agents/skills`。

因此，本项目需要区分两件事：

- 源码布局：使用 `skills/`，便于 Codex、Claude Code 和其他 agent 共享。
- 安装布局：由 `skill.sh` 复制或软链接到 Codex、Claude Code 等目标工具约定的位置。

## 5. 最终推荐仓库结构

```text
dev-skills/
├── README.md
├── CHANGELOG.md
├── LICENSE
├── skill.sh
├── AGENTS.md
├── CLAUDE.md
├── examples/
│   └── complex-coding-harness/
│       ├── sample-execution-plan.md
│       └── sample-pending-decisions.md
├── research/
│   └── complex-coding-harness/
│       ├── README.md
│       ├── local-reference-vibe-coding.md
│       ├── local-reference-harness-bootstrap.md
│       └── online-research-notes.md
├── skills/
│   ├── llms.txt
│   └── complex-coding-harness/
│       ├── SKILL.md
│       ├── references/
│       │   └── workflow.md
│       ├── templates/
│       │   ├── environment.md
│       │   ├── execution-plan.md
│       │   └── pending-decisions.md
└── evals/
    └── complex-coding-harness/
        ├── README.md
        ├── prompts.jsonl
        └── expected.yaml
```

说明：

- 上述结构是目标规划，不在当前阶段全部创建。
- 当前阶段只落本文档；本仓库中现有 `.harness/tasks/` 仅作为本次规划讨论的试运行记录，不代表安装 skill 或普通方案讨论时默认创建任务目录。
- `skills/complex-coding-harness/` 将在后续实现阶段创建。
- README、CHANGELOG、LICENSE、examples、research、evals 和 `skill.sh` 属于仓库级配套内容，按发布需要逐步创建，不阻塞首版 skill 文档实现。
- skill 内部文件必须保持克制：`SKILL.md` 负责触发和核心流程，`references/workflow.md` 负责完整协议，`templates/` 只提供运行时核心文件模板。
- 暂不创建大量细分 reference 和 template；如果后续真实使用中反复证明某一节过长、过复杂，再拆出单独文件。

## 6. 复杂任务运行时文件结构

当 agent 在目标项目里执行 managed 复杂 coding 任务，并且用户允许落盘任务状态时，才生成轻量任务目录：

```text
.harness/
├── environment.md
├── active-task.json
└── tasks/
    └── YYYY-MM-DD/
        └── <task-slug>/
            ├── execution-plan.md
            ├── pending-decisions.md
            └── artifacts/
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `environment.md` | workspace 级开发环境清单，由 agent 从各项目 `docs/development.md` 和原生配置整理而来；后续开发、测试和验证必须优先遵守 |
| `execution-plan.md` | 人类可编辑的主执行契约，集中记录问题定义、候选方案、最终方案、环境、工具、验证、文档更新、readiness gate 和用户覆盖项 |
| `pending-decisions.md` | 可选的临时决策单；仅当待确认问题多、跨轮等待或需要集中审计时创建 |
| `artifacts/` | 保存截图、日志、临时报告和外部验证证据 |

命名规则：

- 任务运行时文件使用 lower-kebab 风格，避免混用下划线。
- workspace 级环境清单固定命名为 `environment.md`，不放入具体任务目录。
- 当前活动任务指针使用 `active-task.json`，表达“当前被续跑的任务”，而不是某个临时上下文文件。
- 旧项目中的 `task_todo.md`、`now_task.md`、`CHANGELOG.md` 只作为历史参考，不作为本 skill 的模板命名。
- managed 任务进入实现前必须完成 `execution-plan.md` 中的方案敲定、环境确认、工具依赖、验证策略、文档更新、Readiness Gate 和 Plan Approval。

文件收敛原则：

- 默认只创建 `execution-plan.md` 和 `.harness/active-task.json`。
- 如果用户明确只要讨论方案、只读调研或不允许落盘任务状态，不得创建 `.harness/tasks/`。
- 当 workspace 存在多个项目、项目包含 `docs/development.md`、或任务需要运行测试、服务、外部工具时，必须创建或更新 `.harness/environment.md`。
- 默认不创建 `pending-decisions.md`；少量问题直接在对话中询问，并写回 `execution-plan.md`。
- 当待确认问题较多、需要用户异步填写、跨多轮才能回答、或需要保留明确批准记录时，创建 `pending-decisions.md`。
- 只有存在截图、长日志、外部响应样本或不可内联证据时，才创建 `artifacts/`。
- 不确定信息不要新建单独文件承载，先写入 `execution-plan.md` 的“待用户确认”和“用户覆盖项”小节。
- 任务计划中的 `Environment` 只引用 `.harness/environment.md` 并记录本次任务覆盖项，不重复维护完整 workspace 环境清单。
- 后续如果某一节长期超过 200 行，或多次任务都需要独立复用，才考虑从 `execution-plan.md` 拆成单独模板。

## 7. Git 跟踪与忽略策略

本项目需要明确区分“skill 源码和规范文件”与“任务执行时产生的本地运行产物”。原则是：可复用规范、模板、示例和重要设计记录应提交；临时日志、截图、大模型响应、安装产物、缓存和密钥必须忽略。

### 7.1 应提交

以下内容属于仓库源码或长期规范，应纳入 git：

```text
README.md
CHANGELOG.md
LICENSE
skill.sh
AGENTS.md
CLAUDE.md
docs/
examples/
research/
skills/
evals/
```

说明：

- `skills/` 是 skill 源码主目录，必须提交。
- `skills/*/references/` 和 `skills/*/templates/` 属于 skill 可复用资源，必须提交。
- `assets/` 和 `skills/*/scripts/` 只在真实需要时创建；首版不默认创建。
- `examples/` 中的样例任务文件是文档化示例，必须提交。
- `research/` 中经过整理的调研结论应提交；原始下载缓存、大体积临时材料不应提交。
- 本次 `.harness/tasks/2026-06-09/docs/complex-coding-harness-plan/` 属于项目初始设计决策记录，建议提交。

### 7.2 应忽略

以下内容属于本地运行产物或敏感信息，应通过 `.gitignore` 忽略：

```gitignore
.harness/tasks/**/artifacts/
.harness/tasks/**/logs/
.harness/tasks/**/tmp/
.harness/tasks/**/scratch/
.dist/
dist/
build/
release/
*.zip
*.tar.gz
*.tgz
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
node_modules/
.npm/
.pnpm-store/
.cache/
.env
.env.*
*.local
*.key
*.pem
.DS_Store
Thumbs.db
.vscode/
.idea/
```

### 7.3 `.harness` 的提交边界

`.harness` 不应一刀切忽略。

建议提交：

- `active-task.json`，用于恢复当前任务。
- `.harness/environment.md`，用于保存 workspace 级开发环境清单；其中不得包含密钥、个人绝对路径或机器私有配置。
- 重要任务目录下的 `execution-plan.md`，以及存在人工确认时的 `pending-decisions.md`。
- 对项目设计、发布、关键决策有长期价值的任务记录。

必须忽略：

- `artifacts/`：截图、日志、大模型响应、接口响应样本和临时报告。
- `logs/`：命令输出、服务日志、浏览器日志。
- `tmp/`、`scratch/`：临时实验文件和可再生成文件。
- `.harness/environment.local.md`：个人机器路径、临时端口、私有解释器路径、账号或不可提交环境覆盖项。

普通业务项目可根据团队偏好决定是否提交 `.harness` 的任务记录；默认应先问用户或遵循项目规则。在 `dev-skills` 这种规范仓库中，重要规划任务记录可以提交，方便后续 agent 恢复设计上下文。

## 8. 方案敲定协议

复杂 coding 任务最容易失败的地方不是少了流程文件，而是没有先把最终方案研究清楚。`complex-coding-harness` 的核心门禁应放在“方案敲定”上：只有当问题定义、候选方案、取舍依据、风险边界、验收方式和人工确认点都清楚，并且用户显式确认“按该方案执行”后，才允许进入实现。

该协议借鉴通用软件工程实践中的 design doc、ADR、RFC 和决策责任模型，但保持轻量。目标不是写长文档，而是强制 agent 在编码前回答“为什么做这个方案，而不是另一个方案”。

### 8.1 方案敲定产物

managed 任务进入编码前必须生成或更新少量核心文件：

```text
.harness/environment.md
execution-plan.md
```

说明：

- `execution-plan.md` 是每个 managed 任务都必须维护的人类可编辑主契约。
- `.harness/environment.md` 是 workspace 级开发环境清单；只要任务涉及运行、测试、服务、MCP、外部工具或多项目联调，就必须先创建或更新。

`execution-plan.md` 内部包含以下固定章节：

| 章节 | 核心问题 | 进入编码前要求 |
| --- | --- | --- |
| `Problem` | 要解决什么 | 明确目标、非目标、验收结果和不确定项 |
| `Context` | 依据是什么 | 记录已读代码、调用方、配置、测试、文档、外部资料、用户约束和证据来源 |
| `Options` | 有哪些方案 | 至少比较 2 个可行方案；如果只有 1 个方案，解释为什么没有合理替代 |
| `Decision` | 最终怎么做 | 明确选定方案、原因、影响、可逆性和后续修改条件 |
| `Implementation Plan` | 怎么落地 | 每个阶段说明目标、怎么做、为什么、在哪做、参考来源、验证、风险和回滚 |
| `Environment` | 用什么环境调试 | 引用 `.harness/environment.md`，并记录本次任务涉及项目、采用环境和临时覆盖项 |
| `Tooling` | 用哪些外部工具 | 明确 MCP、skill、浏览器工具、CLI、外部服务、权限风险和替代方案 |
| `Validation` | 用什么证据证明正确 | 明确单元测试、接口测试、前端交互、文档检查、手工验证及覆盖边界 |
| `Documentation` | 哪些文档要同步 | 明确接口文档、README、配置说明、迁移说明或 changelog 更新范围 |
| `Questions And Overrides` | 哪些需要用户确认或覆盖 | 集中记录待确认项、用户已确认项、用户后续更改记录 |
| `Readiness Gate` | 方案是否可提交审批 | 逐项通过方案就绪检查；存在 blocking 项时不得提交审批或编码 |
| `Plan Approval` | 用户是否批准执行 | 用户显式确认前不得进入实现阶段 |

`active-task.json` 只负责指向当前任务目录，不承载方案内容。方案、状态、下一步、验证边界和确认记录都优先写入 `execution-plan.md`；workspace 级环境事实写入 `.harness/environment.md`。

不建议默认拆分独立文件的原因：

- 文件太多时，agent 容易更新遗漏，用户也不知道该改哪个。
- 环境、工具、验证和文档更新本质上是同一个方案门禁的一部分，拆散后会降低一致性。
- 单文件主契约更适合上下文压缩后的快速恢复：先读 `.harness/active-task.json` 找到任务目录，再读 `execution-plan.md`。

允许拆分的条件：

- `execution-plan.md` 超过 300 行，且某个章节需要频繁单独维护。
- 团队明确希望把环境、验证或决策记录纳入独立审查流程。
- 某一类任务反复复用同一套验证矩阵或环境模板。
- 用户明确要求拆分。

### 8.2 方案研究流程

方案研究分为 9 步：

1. **问题重述**：把用户需求改写成可验证的问题定义，明确目标、非目标和验收结果。
2. **上下文收集**：读取直接相关代码、调用方、配置、测试、历史文档、运行约束和错误处理路径。
3. **外部资料确认**：涉及框架、API、协议、安全、性能、模型能力或工具安装时，查官方文档或可信资料，不能凭记忆写死。
4. **候选方案生成**：提出至少两个合理候选方案，除非任务天然只有一个低风险实现路径。
5. **取舍矩阵评估**：从正确性、复杂度、兼容性、风险、验证成本、可回滚性和维护成本评估。
6. **最终方案收敛**：选择一个主方案，说明放弃其他方案的原因。
7. **实施阶段设计**：把最终方案拆成可执行阶段，每个阶段说明做什么、怎么做、为什么这么做、在哪些文件或模块做、参考了哪些来源。
8. **环境、工具和验证策略确认**：确认调试环境、依赖安装方式、启动命令、测试命令、MCP/skill/CLI 工具依赖和文档更新范围。
9. **readiness gate**：通过方案就绪检查后，进入方案批准等待状态，不能自动编码。

### 8.3 问题定义标准

`execution-plan.md` 的 `Problem` 章节开头必须回答：

- 用户真正要解决的问题是什么。
- 成功后的外部可观察结果是什么。
- 哪些内容明确不做。
- 哪些行为必须兼容。
- 哪些约束来自用户，哪些来自项目规则，哪些来自技术事实。
- 哪些点仍不确定，是否影响方案方向。

如果这些问题无法回答，任务状态应进入 `needs-clarification`，不能靠假设继续。

### 8.4 上下文收集标准

进入候选方案比较前，agent 必须读取足够上下文，至少包括：

- 目标代码的定义处。
- 目标代码的主要调用方。
- 相关数据结构、配置和环境变量。
- 现有测试、构建、lint 或运行验证入口。
- 相关错误处理和降级逻辑。
- 最近任务记录或历史设计文档。

禁止行为：

- 只看一个代码片段就确定方案。
- 没有检查调用方就修改接口。
- 没有确认配置来源就硬编码。
- 不了解验证入口就声称方案可验。

上下文来源必须写入 `Context`，并区分：

- 本地项目代码：具体文件、目录、模块、调用链、测试或配置。
- 本地项目文档：README、接口文档、历史任务记录、`docs/development.md`。
- 外部资料：官方文档、规范、论文、框架文档、工具文档或其他可信来源。
- 用户约束：当前会话明确提出的要求和覆盖项。

如果方案依赖外部资料，必须记录资料来源、用途和结论；不能只写“参考官方文档”。

### 8.5 候选方案要求

`execution-plan.md` 的 `Options` 章节至少包含：

```text
## 方案 A：最小变更方案

- 做法：
- 优点：
- 缺点：
- 风险：
- 验证方式：
- 回滚方式：

## 方案 B：结构化改造方案

- 做法：
- 优点：
- 缺点：
- 风险：
- 验证方式：
- 回滚方式：

## 结论

- 选择：
- 原因：
- 放弃其他方案的理由：
```

候选方案不要求数量越多越好。通常 2 到 3 个即可。方案太多会消耗上下文，也会拖慢决策。

### 8.6 取舍矩阵

每个候选方案按以下维度评分或描述：

| 维度 | 关注点 |
| --- | --- |
| 正确性 | 是否真正满足用户目标和验收标准 |
| 最小变更 | 是否避免无关重构和过大影响面 |
| 兼容性 | 是否保持现有接口、数据和用户行为兼容 |
| 可验证性 | 是否能用现有测试或可补充测试验证 |
| 风险 | 是否影响核心流程、数据、安全、性能或跨项目联动 |
| 可回滚性 | 失败后是否容易回退或降级 |
| 可维护性 | 后续是否容易理解、扩展和排查 |
| 成本 | 实现、验证、迁移和人工确认成本 |

默认选择规则：

- 如果最小变更方案能满足目标且风险可控，优先选最小变更。
- 如果最小变更会扩大隐性复杂度或留下明显一致性问题，选择结构化方案。
- 如果方案影响公共接口、数据持久化、安全、权限、外部服务或多仓库边界，必须增加人工确认或更强验证。

### 8.7 最终方案内容

`execution-plan.md` 的 `Decision` 和 `Implementation Plan` 章节至少包含：

```text
# Execution Plan

## Problem

## Context

## Options

## Decision

## Implementation Plan

## Environment

## Tooling

## Validation

## Documentation

## Questions And Overrides

## Readiness Gate
```

对代码任务，`关键设计` 必须具体到模块、函数、数据结构或交互边界，不能只写抽象描述。

### 8.8 决策记录

`execution-plan.md` 的 `Decision` 章节用简化 ADR 风格记录关键决策：

```text
# Decision Record

## DR-001：采用轻量任务文件而不是完整 harness 工程

- 状态：accepted
- 背景：
- 决策：
- 原因：
- 影响：
- 可逆性：
- 后续修改条件：
```

需要写入 `Decision` 章节：

- 会影响后续实现路线的方案选择。
- 会影响目录结构、文件命名、安装方式或兼容边界的决定。
- 用户明确要求或否定的方向。
- 未来如果改变会造成迁移成本的决定。

不需要写入 `Decision` 章节：

- 普通措辞调整。
- 临时实现细节。
- 可随时重命名的内部变量。

### 8.9 实施方案质量标准

`Implementation Plan` 不能只写阶段名或任务清单。每个阶段必须让用户能判断“agent 到底要改什么、为什么这么改、在哪里改、如何验证”。

每个阶段必须包含：

```text
### 阶段 N：阶段名称

目标：
- 本阶段完成后的可观察结果。

怎么做：
- 具体实施步骤。

为什么这么做：
- 选择该步骤的原因，和它如何支撑最终方案。

在哪做：
- 预计修改或重点阅读的文件、目录、模块、接口、配置或测试。

参考来源：
- 本地代码或文档来源。
- 外部资料来源。
- 用户明确要求。

验证：
- 本阶段完成后要执行或预期执行的检查。

风险和回滚：
- 可能失败的位置。
- 出错时怎么回退或改用备选方案。
```

阶段设计规则：

- 必须基于已读取的本地代码结构，不能凭空写“修改相关模块”。
- 涉及跨项目联调时，必须说明每个项目各自承担什么修改和验证。
- 涉及框架、API、协议、模型、浏览器、MCP 或第三方工具时，必须说明参考来源和结论。
- 如果某个文件或模块尚未完全确认，必须标为待确认，并说明下一步如何确认。
- 如果用户要求的需求本身还不够明确，不能先写实现阶段，必须回到确认问题。

### 8.10 Readiness Gate

`execution-plan.md` 的 `Readiness Gate` 是提交用户审批前的技术门禁。必须逐项回答：

| 检查项 | 必须满足 |
| --- | --- |
| 需求清晰 | 目标、非目标、验收标准已明确 |
| 上下文充分 | 已读取定义处、调用方、配置、测试和错误处理 |
| 候选方案已比较 | 至少 2 个方案或解释无替代方案 |
| 最终方案已选择 | 选择理由清楚，淘汰理由清楚 |
| 实施阶段清楚 | 每个阶段说明做什么、怎么做、为什么、在哪做、参考来源、验证和风险 |
| 环境已确认 | Python/Node/Go 等运行环境、虚拟环境、包管理器和启动命令已明确 |
| 工具依赖已确认 | MCP、skill、浏览器工具、CLI、外部服务和替代方案已明确 |
| 验证策略已确认 | 单元测试、接口测试、前端验证、文档检查和手工验证边界已明确 |
| 文档更新已确认 | 接口文档、README、配置说明、迁移说明等需要更新的范围已明确 |
| 风险已识别 | 数据、接口、安全、性能、兼容性风险已记录 |
| 验证路径可执行 | 明确要跑哪些检查，知道覆盖和不覆盖什么 |
| 人工确认点清楚 | 需要用户确认的事项已列出 |
| 任务状态已更新 | `execution-plan.md` 和 `.harness/active-task.json` 指向下一步 |

如果任一项为 blocking，状态必须是 `blocked_on_solution` 或 `needs-clarification`，不能提交审批或进入实现。

Readiness Gate 通过只代表“方案可以提交给用户审批”，不代表 agent 可以自动执行。managed 任务进入实现阶段前还必须通过方案批准门禁。

### 8.11 方案批准门禁

managed 任务必须在方案制定阶段结束后暂停，等待用户显式确认。禁止 agent 写完方案后自行进入实现。

必须执行：

1. 更新 `execution-plan.md` 的 `Readiness Gate`，标明所有技术门禁已通过。
2. 将 `.harness/active-task.json` 的状态更新为 `awaiting_plan_approval`。
3. 在对话中简要说明最终方案、影响范围、验证计划、阶段提交策略和需要用户确认的批准语句。
4. 停止工作，等待用户明确回复。

可接受的用户批准表达：

- “确认执行”
- “按方案执行”
- “方案没问题，开始实现”
- “同意方案 A”
- 用户在 `execution-plan.md` 的 `Questions And Overrides` 或批准区域写入等价确认，并在会话中要求继续

不算批准的表达：

- 用户只问方案细节。
- 用户要求继续讨论。
- 用户只说“看起来还行”但没有明确授权执行。
- Readiness Gate 全部 pass。

如果用户修改方案、环境、工具或验证策略，agent 必须更新 `execution-plan.md` 和必要时的 `.harness/environment.md`，然后重新通过 Readiness Gate，再次请求方案批准。

方案批准记录必须写清是否允许阶段提交：

- 如果用户要求“每阶段提交”，写入 `Plan Approval` 和 `Commit Log` 计划。
- 如果用户没有授权提交，实施阶段只能记录建议提交点，不能自行提交代码。

### 8.12 不确定时如何向用户确认

调研结论：成熟的 human-in-the-loop 工作流通常有三个共同点：第一，agent 在关键不确定点暂停，而不是继续猜；第二，暂停状态必须能持久化，避免上下文压缩后丢失；第三，用户的回答不是只存在聊天记录里，而要写回任务状态或执行计划。OpenAI Agents SDK 的人工审核模式强调工具调用前的 approve/reject；LangGraph 的 interrupt 模式强调暂停和恢复；MCP 的 elicitation 思路强调结构化向用户索取缺失信息。这些做法共同指向一个原则：确认问题可以在对话里问，但确认结果必须落盘。

以下情况必须请求用户确认：

- 目标、非目标或验收标准不明确。
- 需要改变公共接口、目录结构、数据格式或安装方式。
- 需要引入新依赖、新工具或新运行环境。
- 无法从项目文件确认 Python 解释器、conda 环境、venv 路径或依赖安装方式。
- 无法从项目文件确认前端包管理器和命令，例如 pnpm、npm、yarn、bun 或 workspace 入口。
- 无法确认接口文档、OpenAPI、README、配置说明或迁移文档是否必须更新。
- 无法确认现有单元测试、接口测试、前端 E2E、浏览器验证或手工验证入口。
- 无法确认是否需要 MCP、已有 skill、浏览器自动化、外部 CLI 或第三方服务完成验证。
- 需要使用尚未启用、未安装、需登录、需联网或有权限风险的 MCP/tool/skill。
- 需要删除、迁移或重写已有大量内容。
- 多个方案取舍与业务偏好强相关，代码证据无法决定。
- 验证需要外部服务、账号、真实数据或高成本运行。

以下情况可以由 agent 自主决定：

- 局部命名、文档结构和模板细节。
- 不改变行为的最小修正。
- 明确符合项目规则的错误处理补充。
- 不影响方案方向的文档补充。

### 8.13 确认通道选择

确认通道分为三种，按从轻到重选择：

| 通道 | 适用场景 | 优点 | 风险 | 结果写回 |
| --- | --- | --- | --- | --- |
| 会话即时确认 | 只有 1 到 3 个关键问题，且用户可以马上回答 | 摩擦低，推进快 | 回答容易留在对话里被压缩 | 必须写回 `execution-plan.md` |
| `execution-plan.md` 内联确认 | 问题与方案、环境、工具、验证强绑定，数量不多 | 单文件主契约清晰 | 文件会变长 | 写入 `Questions And Overrides` 和对应章节 |
| `pending-decisions.md` 临时决策单 | 问题多、跨轮等待、需要用户异步填写、需要审计批准记录 | 用户可以集中处理，恢复稳定 | 又多一个文件，必须防止长期分叉 | 回答合并回 `execution-plan.md`，已关闭问题保留索引 |

默认策略：

- 少量关键问题直接在会话中问。
- 中等数量问题写在 `execution-plan.md` 的 `Questions And Overrides`，同时在会话中摘要。
- 大量问题或需要异步确认时才创建 `pending-decisions.md`。
- 不允许同时维护多个来源的“真相”。最终有效配置以 `execution-plan.md` 为准。
- `pending-decisions.md` 是临时决策单，不是长期主契约。
- 只要创建了 `pending-decisions.md`，agent 在对话里也必须同步贴出同一组问题摘要；用户可以选择编辑文件，也可以直接在会话中回答。
- 如果用户在会话中回答，agent 必须把回答同步写回 `pending-decisions.md` 的对应 `USER INPUT` 区域，再合并到 `execution-plan.md`。
- 如果用户编辑文件回答，agent 读取文件后合并到 `execution-plan.md`。

阻塞性确认的硬规则：

- 只要问题会影响方案方向、环境选择、工具权限、验证结论、公共接口、数据迁移、依赖安装或高风险操作，就必须视为 blocking。
- blocking 问题提出后，agent 必须停止当前工作，不能继续编码、继续改文件、继续跑验证或用默认假设越过该问题。
- 提问前必须先把 `execution-plan.md` 的当前状态更新为 `confirmation_required`，并把 `.harness/active-task.json` 的 `next_action` 写成“等待用户回答 Q-xxx”。
- 提问后本轮回复应以确认问题结束，不能在同一回复后半段继续推进其他工作。
- 用户回答后，agent 才能恢复：先写回答案，再关闭问题，再重新检查 `Readiness Gate`，最后继续工作。
- 如果用户选择“按推荐执行”，也视为用户明确确认，必须记录为“用户确认推荐项”。
- 如果用户选择自由填写，agent 必须把自由文本结构化写回对应章节；如果自由文本仍不完整，继续停在 `confirmation_required`。

创建 `pending-decisions.md` 的触发条件：

- 待确认 blocking 问题超过 1 个，或用户需要集中查看后再回答。
- 问题分属不同主题，例如环境、接口、权限、验证、文档、部署。
- 用户需要离开会话后再填写。
- 需要明确批准或拒绝某项高风险操作，例如安装依赖、联网、访问外部账号、迁移数据、改公共接口。
- 多个问题之间存在依赖，需要记录回答顺序和状态。
- 上下文压缩风险高，必须让恢复流程先看到未决问题。

不应创建 `pending-decisions.md` 的情况：

- 只有 1 到 3 个问题，且用户能在当前会话回答。
- 问题只是低风险偏好，例如局部命名或注释措辞。
- 问题可以从项目文件、锁文件、配置、测试脚本或官方文档确认。
- 创建文件的成本高于问题本身。

### 8.14 确认问题的生命周期

每个确认问题必须有状态，不能只写一串问号。推荐状态：

| 状态 | 含义 |
| --- | --- |
| `open` | 等待用户回答 |
| `answered` | 用户已回答，但尚未合并到执行计划 |
| `applied` | 已合并到 `execution-plan.md`，必要时同步更新 `.harness/active-task.json` |
| `superseded` | 被用户后续回答或新证据覆盖 |
| `cancelled` | 问题不再需要 |

生命周期：

1. agent 发现不确定点。
2. agent 判断是否必须确认；不必须确认的，用保守默认并记录假设。
3. 必须确认的问题写入 `Questions And Overrides`；如果达到队列触发条件，同时创建或更新 `pending-decisions.md`。
4. blocking 问题触发 `confirmation_required` 状态，更新 `execution-plan.md` 和 `.harness/active-task.json`。
5. agent 在会话中只提出当前阻塞推进的少量问题，并停止工作。
6. 用户回答后，agent 先更新问题状态，再更新 `Environment`、`Tooling`、`Validation`、`Decision` 或其他对应章节。
7. 更新 `execution-plan.md` 的当前状态和问题状态。
8. 如果所有 blocking 问题关闭，重新检查 `Readiness Gate`。

`pending-decisions.md` 建议格式：

```text
# Pending Decisions

请在 `USER INPUT` 区域内填写你的决定。你也可以不编辑文件，直接在会话中回复选项或自定义内容。

## D-001：Python 环境

Context:
项目同时存在 `requirements.txt` 和 `environment.yml`，当前无法确定首选环境。

Options:
- A（recommended）：使用 conda env forensic。
- B：使用项目目录下的 `.venv`。
- C：使用系统 Python。
- Custom：填写 conda 环境名、venv 路径或 Python 解释器绝对路径。

Impact:
该选择会决定依赖安装方式、测试命令和验证声明。

Merge target:
`execution-plan.md` / `Environment`

>>> 📝 USER INPUT: D-001 >>>
Decision:

<<< END <<<
```

### 8.15 提问质量规则

确认方式必须具体、可覆盖、可落盘：

- 先在 `Questions And Overrides` 写清“已推断值”“证据来源”“不确定点”“默认建议”“需要用户回答的问题”。
- 对用户只问会改变方案或验证结果的问题，避免一次抛出完整调查问卷。
- 每次最多集中问 1 到 3 个关键问题；其余低风险项使用保守默认，并标注可后续覆盖。
- blocking 问题必须提供 ABC 选项、推荐项和自定义填写入口；不要只让用户自由发挥。
- 问题必须给出可直接回答的格式，例如“请选择 A/B/C，或填写 conda 环境名、venv 路径、Python 解释器绝对路径”“请选择 pnpm/npm/yarn/bun 或自定义命令”“请选择是否允许使用 Chrome DevTools MCP，或指定替代工具”。
- 用户回答后，必须把结果写回 `Questions And Overrides` 和对应章节，不只留在对话里。
- 如果用户说“按你判断来”，agent 可以采用默认建议，但必须在 `Decision` 或 `Environment` 中标为“用户授权默认”。
- 如果用户后续改变答案，最新用户要求优先，必须更新 `execution-plan.md` 和 `.harness/active-task.json` 的阻塞状态。
- 问题必须区分 blocking 和 non-blocking。blocking 未关闭不得编码；non-blocking 可以带假设继续，但最终交付必须说明假设。
- 不问“你希望怎么做？”这种空问题。必须给出上下文、可选项、默认建议和影响。
- 同一问题不能反复问；如果用户回答不完整，补问缺失字段，并标记原问题为部分回答。

推荐提问模板：

```text
我从项目文件推断出：
- Python：未发现明确虚拟环境；可能使用 requirements.txt。
- 验证：发现 pytest 配置，但没有确认数据库依赖。

我需要暂停并确认 2 个 blocking 问题，确认后再继续：

Q-001 Python 环境用哪个？
A（推荐）：conda env forensic
B：项目目录下的 .venv
C：系统 Python
自定义：请给 conda 环境名、venv 路径或解释器路径。

Q-002 验证策略用哪个？
A（推荐）：先运行 pytest，接口 smoke 等启动命令确认后再补。
B：pytest + 接口 smoke，请提供启动命令或 base URL。
C：暂不运行测试，只做静态检查并在最终声明未执行测试。
自定义：请给验证命令。

我会把你的回答写入 .harness/.../execution-plan.md 的 Environment 和 Validation 章节。
```

用户修改方式：

- 最直接方式：用户在对话中说明覆盖项，例如“这个项目用 pnpm，不用 npm”“Python 用 conda env forensic”“不要用 MCP，只跑项目自带 Playwright”。
- 可审查方式：用户直接修改 `.harness/tasks/.../execution-plan.md` 的 `Questions And Overrides`、`Environment`、`Tooling` 或 `Validation` 章节，然后让 agent 继续。
- 中断恢复方式：agent 恢复任务时必须优先读取 `.harness/active-task.json` 和任务目录中的 `execution-plan.md`。
- 冲突处理：如果用户口头覆盖、项目配置和旧计划冲突，以用户最新明确要求优先；但如果会带来明显风险，先说明风险再执行。
- 如果存在 `pending-decisions.md`，恢复时读取顺序是 `.harness/active-task.json`、`pending-decisions.md`、`execution-plan.md`；但最终有效配置仍以 `execution-plan.md` 中已合并内容为准。

### 8.16 Workspace 环境清单规则

开发环境信息分三层管理：

```text
各项目 docs/development.md  = 用户自然语言说明，源信息
.harness/environment.md    = agent 整理后的 workspace 级环境清单
execution-plan.md          = 本次任务引用的环境和临时覆盖项
```

`docs/development.md` 不要求固定表格格式。用户可以用大白话写清项目类型、运行方式、测试要求、工具要求和特殊约束。agent 不能要求用户先把它改成复杂模板；agent 应该读取自然语言后自行整理为结构化清单。

示例：

```text
当前目录下有 pro1 后端项目，Go 语言，测试阶段需要完成对应功能的单测，每轮大修改后需要冒烟测试。
pro2 是前端项目，运行是 pnpm dev，需要使用 Chrome DevTools MCP 自我验证。
另一个 Python 项目使用 conda 虚拟环境 aaa。
```

agent 在 managed 任务进入方案敲定阶段时，必须执行环境盘点：

1. 优先扫描相关项目的 `docs/development.md`。
2. 再读取原生配置进行校验或补充，例如 `go.mod`、`package.json`、`pnpm-lock.yaml`、`pyproject.toml`、`requirements.txt`、`environment.yml`、`.python-version`、`compose.yaml`。
3. 把用户自然语言和项目配置整合到 `.harness/environment.md`。
4. 如果 `.harness/environment.md` 已存在，先读取它，再检查相关 `docs/development.md` 和原生配置是否出现冲突或新增信息。
5. 如果环境信息缺失但不阻塞当前方案，可以记录为 open question；如果会影响安装、运行、测试或验证声明，必须进入 blocking 确认。
6. 后续开发、测试、服务启动、MCP 使用和验证命令必须优先遵守 `.harness/environment.md`。

`.harness/environment.md` 至少记录：

- 每个项目的路径、类型和语言。
- 运行环境，例如 Go 版本、Node 包管理器、Python conda/venv/解释器。
- 安装、启动、测试、构建、lint、冒烟测试命令。
- 必须使用或禁止使用的工具，例如 Chrome DevTools MCP、Playwright、Docker、外部 API。
- 验证要求，例如单测、接口测试、前端浏览器自检、每轮大修改后的 smoke。
- Git 主分支、统一 harness 工作分支映射和同步策略。
- 信息来源，例如 `docs/development.md`、锁文件、配置文件、用户会话。
- 未确认项和冲突项。

`execution-plan.md` 的 `Environment` 章节不重复维护完整环境清单，只做两件事：

- 引用 `.harness/environment.md`。
- 写明本次任务涉及哪些项目、采用哪些环境、是否存在临时覆盖项。

用户修改规则：

- 长期环境变化优先修改对应项目的 `docs/development.md`，再让 agent 更新 `.harness/environment.md`。
- 当前 workspace 的整理结果可以直接修改 `.harness/environment.md`，但 agent 后续必须检查它与项目源文件是否冲突。
- 单次任务临时覆盖写入当前任务的 `execution-plan.md`，不要悄悄改写 `.harness/environment.md`。
- 如果用户后续更改环境、包管理器、验证命令或 MCP 使用要求，agent 必须更新 `.harness/environment.md` 或当前任务 `execution-plan.md`，并重新通过 `Readiness Gate`。

### 8.17 Git 工作分支规则

managed 任务使用统一 harness 工作分支策略。核心原则是按任务类型进入固定分支，不按任务名创建分支。

固定分支：

```text
harness/feature
harness/fix
harness/refactor
harness/docs
harness/test
harness/chore
```

任务类型映射：

```text
feat / feature  -> harness/feature
fix             -> harness/fix
refactor        -> harness/refactor
docs            -> harness/docs
test            -> harness/test
chore           -> harness/chore
```

如果任务同时包含多类，按主要目的选分支。例如“修 bug 并补测试”仍走 `harness/fix`。

`.harness/environment.md` 必须记录 Git 信息：

```md
## Git

Main branch:
- dev

Harness branch policy:
- feature: harness/feature
- fix: harness/fix
- refactor: harness/refactor
- docs: harness/docs
- test: harness/test
- chore: harness/chore

Merge policy:
- 开始实施前，将主分支最新代码合入 harness 工作分支。
- 每个阶段提交前，检查是否需要再次同步主分支。
- 默认使用 merge，不默认 rebase。
- 不自动 stash、reset、覆盖用户改动或删除分支。
```

主分支优先由用户在 `.harness/environment.md` 写明。没写时再探测：

```text
dev -> main -> master -> origin/HEAD
```

如果探测结果不唯一，或主分支会影响提交、合并、验证声明，必须问用户。

切换或创建 harness 分支前必须先执行等价检查：

```bash
git status --short
git branch --show-current
```

规则：

- 工作区干净：可以继续。
- 有本任务改动：按当前阶段提交策略处理。
- 有用户或未知改动：停止确认。
- 有冲突、rebase、merge 或 cherry-pick 进行中：停止确认。

禁止行为：

- 不自动 stash。
- 不自动覆盖用户改动。
- 不自动 reset。
- 不自动 rebase。
- 不自动删除分支。
- 不自动切到未知分支。

目标分支不存在时创建：

```bash
git switch -c harness/feature
```

目标分支已存在时切换：

```bash
git switch harness/feature
```

同步主分支默认使用 merge，不使用 rebase。推荐流程：

```bash
git fetch origin
git switch harness/feature
git merge origin/dev
```

如果没有远程或不能联网：

```bash
git merge dev
```

如果 merge 冲突，停止并记录到 `execution-plan.md`，不能大范围猜测解决。

热修复插入规则：

- 如果当前在 `harness/feature`，用户突然要求处理 `fix`，不能直接切到 `harness/fix`。
- 必须先确认当前 feature 分支代码是否需要合并进主分支。
- 如果用户确认合并，先在主分支合并 `harness/feature`，再切换或创建 `harness/fix`，然后让 `harness/fix` 同步主分支。
- 如果用户不确认合并，只有在工作区安全时才能直接切到 `harness/fix` 并同步主分支。
- 如果 feature 有未提交改动，必须先询问是否提交检查点或暂停切换，不能自动带着脏工作区切换。

热修复确认问题推荐格式：

```md
## D-001 热修复前分支处理

当前分支:
- harness/feature

目标分支:
- harness/fix

主分支:
- dev

需要确认:
- 当前 feature 分支代码是否要先合并进主分支？

选项:
- A. 先把 harness/feature 合并进 dev，再切到 harness/fix
- B. 不合并 feature，直接切到 harness/fix
- C. 暂停热修复，继续整理当前 feature

>>> 📝 USER INPUT: D-001 >>>
Decision:

<<< END <<<
```

推荐默认项是 B，因为未完成的 feature 不应该默认进入主分支。

`execution-plan.md` 必须增加 `Git Context`，记录：

- 主分支。
- 任务类型。
- 工作分支。
- 分支动作：创建、复用、已在目标分支或不适用。
- 同步来源，例如 `origin/dev` 或本地 `dev`。
- 最近同步时间和结果。
- 提交策略。
- 热修复插入决策。
- 未解决分支问题。

### 8.18 工具依赖确认规则

`execution-plan.md` 的 `Tooling` 章节用于记录方案实施和验证过程中需要使用的外部工具、MCP server、skill、浏览器工具、CLI、服务账号和替代方案。

必须记录：

- 工具名称，例如 Chrome DevTools MCP、Playwright MCP、OpenAI Docs MCP、GitHub CLI、Docker、数据库 CLI、项目自带脚本或某个 skill。
- 使用目的，例如浏览器交互验证、接口文档查询、截图、网络请求检查、依赖安装、容器启动、代码扫描。
- 调用时机，例如方案研究、编码前确认、验证阶段、发布前检查。
- 可用性状态，例如 available、missing、needs-install、needs-login、needs-network、needs-user-confirmation。
- 权限和风险，例如是否需要联网、是否会写文件、是否会访问外部账号、是否会启动服务、是否会修改系统状态。
- 替代方案，例如没有 MCP 时使用项目原生 Playwright、没有浏览器工具时改为接口 smoke、没有 CLI 时要求用户提供输出。
- 用户确认状态。

建议格式：

```text
| 工具 | 用途 | 阶段 | 状态 | 风险 | 替代方案 | 用户确认 |
| --- | --- | --- | --- | --- | --- | --- |
| Chrome DevTools MCP | 前端交互和网络检查 | 验证 | available | 启动浏览器会话 | 项目 Playwright | 已确认 |
| OpenAI Docs MCP | 官方文档确认 | 方案研究 | available | 需要联网 | 官方网页搜索 | 已确认 |
```

典型规则：

- 前端交互验证如果要求浏览器实测，必须说明使用 Chrome DevTools MCP、Playwright、Cypress 还是手工验证。
- 涉及 OpenAI、框架 API、云服务或不稳定外部事实时，必须说明使用官方文档、Docs MCP 或联网搜索。
- 如果验证依赖某个 skill，必须写明 skill 名称、触发原因和替代路径。
- 如果工具不可用，不能把相关验证标记为通过；只能标记为未执行或采用替代验证，并说明覆盖边界。
- 如果工具需要安装、登录、联网、写外部路径或访问外部服务，必须按权限规则请求用户确认。

### 8.19 验证策略确认规则

`execution-plan.md` 的 `Validation` 章节用于在编码前明确“做完后如何证明是对的”。验证策略必须根据任务影响面分层，而不是固定跑所有命令。

最低要求：

- 纯文档任务：检查文件存在、关键内容、链接或格式。
- Python 逻辑变更：运行相关单元测试；没有测试时说明缺口，并评估是否补测试。
- Python API 变更：运行单元测试和接口级 smoke；涉及契约时更新接口文档。
- 前端逻辑变更：运行类型检查、组件测试或单元测试。
- 前端交互变更：运行浏览器交互验证，检查 console/network，必要时截图。
- 配置或依赖变更：运行安装、构建或启动 smoke，并记录环境影响。
- 数据库、迁移或持久化变更：验证迁移路径、回滚策略和数据兼容性。

验证策略必须写清：

- 要运行哪些命令。
- 要调用哪些 MCP、skill、浏览器工具、CLI 或外部服务。
- 每个命令覆盖什么。
- 每个工具覆盖什么。
- 每个命令不覆盖什么。
- 每个工具不覆盖什么。
- 哪些验证需要用户提供环境或数据。
- 如果验证无法执行，最终交付时能声明到什么程度。

### 8.20 文档更新确认规则

`execution-plan.md` 的 `Documentation` 章节用于确认实现方案是否需要同步文档。

以下变更通常需要文档更新：

- 公共 API、接口字段、错误码、请求/响应结构变化。
- 配置项、环境变量、启动命令或依赖安装方式变化。
- 用户可见行为、UI 流程、权限或兼容性变化。
- 数据结构、迁移步骤、部署步骤或回滚步骤变化。
- 新增脚本、命令、skill 使用方式或安装方式。

文档更新可以是：

- README。
- docs 目录。
- OpenAPI/Swagger。
- CHANGELOG。
- 示例配置。
- 迁移说明。
- skill 模板或 reference。

如果文档是否需要更新无法判断，应在 `Readiness Gate` 中标为待确认，不能默认跳过。

### 8.21 方案变更规则

编码过程中如果发现原方案不成立，不能悄悄改方向。必须执行：

1. 更新 `execution-plan.md`，说明发现了什么。
2. 更新 `Options` 或新增方案。
3. 更新 `Decision`，记录原决策是否废弃。
4. 更新 `Environment`、`Tooling`、`Validation` 或 `Documentation`，如果变更影响环境、验证、工具依赖或文档。
5. 更新 `Readiness Gate`，重新通过方案门禁。
6. 必要时更新 `.harness/active-task.json` 的当前状态和下一步。
7. 如果方向变化影响用户目标、范围、风险、环境、验证成本或文档边界，先询问用户。

### 8.22 实施阶段执行协议

用户批准方案后，agent 才能进入实施阶段。实施阶段必须严格按照 `execution-plan.md` 的 `Implementation Plan` 分阶段推进，不得跳过阶段门禁。

每个实施阶段开始前必须重读：

- `.harness/active-task.json`
- `.harness/environment.md`
- 当前任务的 `execution-plan.md`
- 如果存在，当前任务的 `pending-decisions.md`
- 项目相关 `docs/development.md`
- 项目规则文件，例如 `AGENTS.md`、`CLAUDE.md`

每个实施阶段必须执行以下顺序：

1. 更新 `execution-plan.md` 的当前阶段、目标、范围和本阶段计划。
2. 再次确认本阶段涉及的前端、后端、Python、数据库、接口文档、MCP 或外部服务环境。
3. 检查 `Git Context` 和实际 git 状态，确认当前分支、主分支同步和工作区安全。
4. 读取本阶段涉及的代码、测试、配置、接口和文档。
5. 按已批准方案做最小必要修改。
6. 如果发现明显缺陷，直接修复并记录；如果是小优化且在批准范围内，可以自我优化并记录；如果会改变方案方向、范围、接口、风险或验证成本，停止并回到方案变更规则。
7. 完成本阶段 code review，重点检查正确性、边界条件、错误处理、兼容性、无关改动、测试覆盖和文档同步。
8. 按 `Validation` 和 `.harness/environment.md` 执行本阶段验证。
9. 修复 code review 或验证发现的问题，并重复 review 和验证，直到本阶段没有 blocking 或 major finding。
10. 更新 `execution-plan.md`，记录本阶段修改、验证命令、验证结果、未覆盖范围、缺陷修复和剩余风险。
11. 更新项目变更记录，例如 `CHANGELOG.md`；如果仓库没有 changelog，按项目既有记录方式处理，或在 `execution-plan.md` 中记录未找到 changelog。
12. 如果用户批准方案中包含阶段提交要求，或用户明确要求提交，则提交本阶段相关仓库代码；如果涉及多个仓库，按仓库分别提交，并在 `execution-plan.md` 记录每个仓库的 commit hash 和说明。
13. 提交后再次读取 `.harness/active-task.json`、`.harness/environment.md`、`execution-plan.md` 和相关 changelog，确认下一阶段状态没有丢失。

验证要求：

- 前端阶段必须按环境清单使用指定工具验证；如果要求 Chrome DevTools MCP，就必须用 Chrome DevTools MCP 做页面、交互、console、network 或截图检查。
- 后端阶段必须完成对应功能的单元测试；涉及接口时补充接口级 smoke 或契约检查。
- Python 阶段必须使用 `.harness/environment.md` 指定的 conda、venv、解释器或包管理器执行验证。
- 每轮大修改后必须执行 smoke，具体命令来自 `.harness/environment.md` 或用户确认。
- 如果某项验证因环境或权限无法执行，不能标记通过，必须记录未执行原因、影响范围和替代验证。

提交要求：

- 每个实施阶段完成后是否提交，必须以用户批准的方案或用户明确要求为准；如果方案要求阶段提交，则必须提交，除非仓库没有 git 或提交会包含未授权/无关文件。
- 提交前必须检查 git 状态，避免提交无关文件、私有配置、密钥、缓存、日志或 `artifacts/`。
- 提交信息必须符合项目规则；本项目默认格式为：

```text
feat(scope): 大标题

- 重点 1
- 重点 2
- 重点 3
```

标题和列表之间保留一个空行；列表项之间不加空行。

文档更新要求：

- `CHANGELOG.md` 或项目既有变更记录必须记录每个阶段完成的工作、验证结果和 commit 信息。
- 当前任务的 `execution-plan.md` 必须持续记录阶段状态、验证证据、code review 结论、缺陷修复和下一步。
- `.harness/active-task.json` 必须保持 `status`、`next_action` 和当前任务目录准确。
- 如果上下文压缩、遗忘或不确定，必须先查这些任务文档，不能凭记忆继续。

### 8.23 如何保证方案做好

方案质量不是靠文档长度保证，而是靠以下机制：

- **证据先行**：每个关键判断都来自本地代码、项目文档、官方资料或用户明确要求。
- **候选对比**：不允许只写一个看起来合理的方案就进入实现。
- **负面验证**：必须说明为什么不用其他方案，暴露取舍成本。
- **风险前置**：把兼容性、验证成本、回滚和人工确认点放到编码前。
- **环境前置**：在编码前确认解释器、虚拟环境、包管理器、启动命令和外部依赖。
- **工具前置**：在编码前确认 MCP、skill、浏览器工具、CLI、外部服务和替代方案。
- **验证前置**：在编码前确认测试命令、接口验证、前端验证和文档更新范围。
- **门禁清晰**：`execution-plan.md` 的 `Readiness Gate` 未通过时不得编码。
- **可恢复**：方案、决策、状态和日志都落盘，压缩后可恢复。
- **可复盘**：如果验收失败，能回看当时为什么选这个方案，以及漏掉了什么证据。

## 9. Skill 触发策略

### 9.1 应触发

- 用户明确要求长任务稳定执行。
- 用户担心上下文压缩、中断、恢复或多轮续跑。
- 任务包含多个阶段、多个模块、多个仓库或前后端联动。
- 任务要求阶段性验证、提交或保留可恢复记录。
- 任务涉及公共接口、核心流程、数据库、外部服务、运行时行为或高风险重构。
- 用户要求“按计划推进”“继续上一个任务”“验收失败继续修”。

### 9.2 不应触发

- 简单问答、代码解释或只读审查。
- 单文件、低风险、小范围修复，且用户没有要求任务记录。
- 用户明确只要方案，不要落地文件。
- 用户明确要求不要创建任务状态文件。

## 10. Skill 内容设计

### 10.1 `SKILL.md`

`SKILL.md` 只保留高层流程：

- 判断任务级别。
- 复杂任务必须创建或读取 `.harness`。
- 每轮开始先读 `.harness/active-task.json` 和当前任务的 `execution-plan.md`。
- managed 任务编码前必须完成方案敲定协议。
- managed 任务编码前必须在 `execution-plan.md` 中确认调试环境、工具依赖、验证策略和文档更新计划。
- managed 任务 Readiness Gate 通过后必须进入 `awaiting_plan_approval`，等待用户明确确认方案，禁止自动开始实现。
- 遇到 blocking 不确定问题时，必须进入 `confirmation_required`，给出 ABC 推荐选项和自定义入口，然后停止工作等待用户回答。
- 编码前完成上下文收集和任务拆解。
- 实施阶段必须按批准方案逐阶段执行；每阶段完成后必须完成 code review、验证、缺陷修复、提交代码、更新 changelog 和任务记录。
- 编码后完成自审、验证、提交记录和 `execution-plan.md` 更新。
- 如果上下文压缩或中断，按恢复协议继续。

`SKILL.md` 不应包含所有细节，细节放在 `references/workflow.md`。

### 10.2 `references/workflow.md`

`references/workflow.md` 是唯一默认 reference，包含以下内容：

- direct、managed、needs-clarification 的任务分级规则。
- managed 任务阶段。
- `execution-plan.md` 固定章节说明。
- 不确定信息的用户确认协议。
- blocking 确认问题的停工等待规则。
- 用户覆盖项的写回规则。
- 上下文压缩后的恢复顺序。
- 实施阶段逐阶段 review、验证、提交和记录更新规则。
- 自审与验证声明边界。

任务分级：

- direct：小而清晰，允许直接最小修改和目标验证。
- managed：复杂、高风险、跨模块、长周期，必须落任务文件。
- needs-clarification：需求目标、验收标准、环境或关键约束不明确，必须先问用户。

managed 任务阶段：

1. 任务初始化。
2. 上下文收集。
3. 问题拆解。
4. 候选方案比较。
5. 最终方案敲定。
6. 环境、工具依赖、验证策略和文档更新计划确认。
7. readiness gate。
8. 用户批准方案。
9. 编码实施。
10. 阶段 code review、验证和缺陷修复。
11. 阶段提交和变更记录更新。
12. 文档和 `execution-plan.md` 更新。
13. 最终交付或等待人工验收。

`active-task.json` 最低字段：

```json
{
  "task_id": "2026-06-09-docs-complex-coding-harness-plan",
  "task_dir": ".harness/tasks/2026-06-09/docs/complex-coding-harness-plan",
  "title": "落盘 complex-coding-harness skill 规划文档",
  "status": "confirmation_required",
  "next_action": "等待用户回答 D-001 后继续",
  "updated_at": "2026-06-09"
}
```

恢复顺序：

1. 读取 `.harness/active-task.json`。
2. 如果存在 `pending-decisions.md`，读取未关闭问题。
3. 读取当前任务目录中的 `execution-plan.md`。
4. 检查 git 状态和实际文件。
5. 继续 `next_action`，不要重开任务。

进入验证前的自审：

- 检查是否满足用户目标。
- 检查是否改了无关文件。
- 检查错误处理和边界条件。
- 检查验证是否覆盖变更影响面。
- blocking 或 major finding 未关闭时不得进入最终交付。

验证边界：

- 文档任务至少检查文件存在、目录结构和关键内容。
- 代码任务优先运行项目原生命令。
- 前端交互任务需要浏览器或项目 E2E 验证。
- API、数据库、模型调用或外部服务变更不能只用静态检查证明。
- 未执行的验证必须明确标注，不得声称通过。

## 11. 模板设计

### 11.1 `execution-plan.md`

应包含：

- `Problem`：任务目标、非目标、验收标准、约束和不确定项。
- `Context`：已读代码、调用方、配置、测试、文档、外部资料、用户约束和证据来源。
- `Options`：候选方案、取舍矩阵、风险、验证方式和回滚方式。
- `Decision`：最终方案、选择原因、影响、可逆性和后续修改条件。
- `Implementation Plan`：分阶段落地计划；每个阶段必须说明目标、怎么做、为什么、在哪做、参考来源、验证、风险和回滚。
- `Environment`：引用 `.harness/environment.md`，并记录本次任务涉及项目、采用环境和临时覆盖项。
- `Git Context`：主分支、任务类型、harness 工作分支、同步来源、提交策略、热修复插入决策和未解决分支问题。
- `Tooling`：MCP、skill、浏览器工具、CLI、外部服务、可用性、权限风险和替代方案。
- `Validation`：必须执行的验证、可选验证、覆盖范围、不覆盖范围和无法执行时的声明边界。
- `Documentation`：接口文档、README、配置说明、示例、迁移说明或 changelog 更新计划。
- `Questions And Overrides`：待用户确认项、用户已确认项、用户后续覆盖记录。
- `Readiness Gate`：方案是否可提交用户审批的逐项检查结论。
- `Plan Approval`：用户是否已明确批准该方案进入实现阶段。
- `Implementation Progress`：各阶段当前状态、已完成修改、下一步和阻塞项。
- `Code Review`：每阶段自审结论、发现的问题、修复情况和剩余风险。
- `Commit Log`：每阶段提交的仓库、commit hash、提交信息和对应 changelog 记录。

`Questions And Overrides` 对 blocking 问题必须记录：

- 问题 id。
- blocking 标记。
- 背景和证据。
- ABC 选项。
- 推荐项。
- 自定义填写入口。
- 用户回答。
- 是否已应用到对应章节。

### 11.2 `environment.md`

Workspace 级模板。位于 `.harness/environment.md`，由 agent 从各项目 `docs/development.md` 和原生配置整理生成。

应包含：

- 信息来源列表。
- 每个项目的路径、类型、语言和主要职责。
- 每个项目的运行环境、包管理器、虚拟环境、启动命令、测试命令、构建命令和 smoke 要求。
- 必须使用的验证工具，例如 Chrome DevTools MCP、项目 E2E、Docker、数据库 CLI。
- Git 主分支、harness 分支映射、主分支探测顺序和 merge 策略。
- 未确认项、冲突项和用户覆盖记录。

规则：

- 用户可以用自然语言维护各项目 `docs/development.md`；agent 负责转成 `.harness/environment.md` 的结构化清单。
- `.harness/environment.md` 是 workspace 级执行依据，不按任务重复生成。
- 任务级临时覆盖写入当前 `execution-plan.md`，不要直接改写长期环境事实。

### 11.3 `pending-decisions.md`

可选模板。只有达到临时决策单触发条件时创建。

应包含：

- Blocking 问题列表。
- 每个问题的 id、状态、主题、为什么需要确认、推断值、证据、默认建议、需要用户回答的问题、影响、回答和合并位置。
- 每个问题必须包含 ABC 选项、推荐项和自定义填写入口。
- 每个问题必须包含 `>>> 📝 USER INPUT: D-xxx >>>` 和 `<<< END <<<` 填写区域。
- 文件创建后，对话里也必须同步贴出同一组问题摘要，允许用户直接在会话中回答。
- 已关闭问题的简短索引，便于恢复和审计。
- 明确说明最终有效配置以 `execution-plan.md` 已合并内容为准。

`pending-decisions.md` 不放 non-blocking 问题。非阻塞假设直接写入 `execution-plan.md` 的相关章节和最终交付说明，避免临时决策单变成杂项清单。

## 12. 首版不做脚本

首版不实现脚本。原因是当前 skill 的核心价值是让 agent 在长任务中遵守“先定方案、再编码、阻塞问题先确认”的协议，而不是自动创建一堆文件。

暂不首版实现：

- `init_task.py`：容易过早固化目录字段。
- `checkpoint_task.py`：会鼓励机械更新状态，而不是认真维护 `execution-plan.md`。
- `validate_task_state.py`：首版文件很少，人工和 agent 自查足够；暂不规划该脚本。
- 自动生成方案脚本：方案判断必须由 agent 基于上下文完成，不能脚本假装推断。

后续只有当真实使用中多次出现“任务目录创建或文件校验出错”时，才考虑增加一个很小的校验脚本。

## 13. 分阶段实施计划

### 阶段 1：规划和目录骨架

目标：

- 落盘本文档。
- 如用户允许，使用本项目轻量任务记录试运行 `.harness` 规则。
- 不创建实际 skill 实现目录。

验收标准：

- `docs/complex-coding-harness-skill-plan.md` 存在。
- 如果采用试运行记录，`.harness/active-task.json` 可解析。
- 如果采用试运行记录，当前任务目录能说明本次规划背景和下一步。
- 规划文档已经写清方案敲定协议。
- 规划文档已经写清文件收敛策略和用户确认/覆盖机制。

### 阶段 2：skill 文档实现

目标：

- 创建 `skills/complex-coding-harness/SKILL.md`。
- 创建 `references/workflow.md`。
- 创建 `templates/environment.md`、`templates/execution-plan.md` 和 `templates/pending-decisions.md`。
- 优先实现方案敲定、环境确认、工具依赖、验证策略和用户覆盖机制。

验收标准：

- `SKILL.md` 有合法 frontmatter。
- `description` 能明确触发复杂 coding 长任务。
- `SKILL.md` 保持短，细节引用 `references/workflow.md`。
- 模板吸收 `vibe_coding` 的可恢复记录思想，但不复制三文件结构。
- `environment.md` 模板明确是 workspace 级环境清单，由 agent 从各项目自然语言 `docs/development.md` 和原生配置整理生成。
- managed 任务模板把方案、工具、验证、文档和 readiness gate 收敛到 `execution-plan.md`，并在 `Environment` 中引用 `.harness/environment.md`。
- `execution-plan.md` 模板必须要求每个实施阶段写清楚做什么、怎么做、为什么、在哪做、参考来源、验证、风险和回滚。
- `execution-plan.md` 模板必须包含 `Plan Approval`，明确用户批准前不得进入实现阶段。
- `execution-plan.md` 模板必须在 `Plan Approval` 中记录是否允许阶段提交；未授权提交时只能记录建议提交点。
- `execution-plan.md` 模板必须包含 `Implementation Progress`、`Code Review` 和 `Commit Log`，用于记录每阶段执行、验证、审查、提交和 changelog 更新。
- `pending-decisions.md` 模板明确是按需创建的临时决策单，不是默认主契约。
- `workflow.md` 必须说明 `.harness/tasks/` 只在 managed 任务且用户允许落盘任务状态时创建。

### 阶段 3：示例和 eval

目标：

- 增加 `examples/complex-coding-harness/`。
- 增加 `evals/complex-coding-harness/`。
- 覆盖触发和不触发样例。

验收标准：

- eval 样例覆盖 direct、managed、needs-clarification。
- 覆盖上下文压缩恢复、验收失败续跑和只读规划任务。

### 阶段 4：安装适配

目标：

- 实现或完善 `skill.sh`。
- 支持从 `skills/` 安装到不同 agent 的目标目录。

验收标准：

- 源码主目录仍是 `skills/`。
- Codex 适配通过复制或软链接实现。
- Claude Code 适配不要求改变源码结构。

## 14. 验证策略

规划文档阶段只需要文档级验证：

- 检查文件是否存在。
- 检查 `.harness/active-task.json` 是否可解析。
- 检查当前阶段没有创建实际 skill 实现目录。
- 检查任务记录能说明下一步。
- 检查规划文档包含方案敲定协议和 readiness gate。

后续实现阶段需要增加：

- `SKILL.md` frontmatter 校验。
- eval prompt 样例检查。
- 方案敲定模板完整性检查。
- `environment.md` 中多项目环境、命令、验证工具、来源和未确认项完整性检查。
- `execution-plan.md` 中上下文来源、阶段实施细节、环境引用、工具依赖、验证策略、文档更新、用户覆盖、方案批准、阶段进度、code review 和提交记录章节完整性检查。
- `pending-decisions.md` 按需临时决策单模板完整性检查。

## 15. 风险和取舍

| 风险 | 处理方式 |
| --- | --- |
| 规则太重导致小任务也被流程拖慢 | 通过 task-classification 区分 direct 和 managed |
| 讨论方案时误创建运行时任务目录 | `.harness/tasks/` 只在 managed 任务且用户允许落盘任务状态时创建 |
| skill 体积过大占用上下文 | `SKILL.md` 保持短，细节放 `references/workflow.md` |
| 安装目录绑定 Codex | 源码放 `skills/`，安装由 `skill.sh` 适配 |
| 验证声明过度 | 使用 `execution-plan.md` 的 `Validation` 限制最终声明 |
| 验收失败后上下文断裂 | 通过 active-task 和任务目录续跑原任务 |
| 流程完整但方案错误 | 通过 `execution-plan.md` 的 `Options`、`Decision` 和 `Readiness Gate` 把方案敲定作为编码前门禁 |
| 方案阶段空泛不可执行 | `Implementation Plan` 的每个阶段必须说明做什么、怎么做、为什么、在哪做、参考来源、验证、风险和回滚 |
| agent 写完方案后直接执行 | Readiness Gate 通过后必须进入 `awaiting_plan_approval`，只有用户显式确认方案后才能实现 |
| 实施阶段遗忘任务要求 | 每阶段开始和结束都必须重读 `.harness` 任务文档、环境清单和相关 changelog，更新当前阶段、下一步和提交记录 |
| 阶段完成但质量未闭环 | 每阶段必须完成 code review、验证、缺陷修复、提交代码、更新 changelog 和 `execution-plan.md` 后才能进入下一阶段 |
| 未授权提交代码 | 阶段提交必须写入 `Plan Approval` 或来自用户明确要求；否则只记录建议提交点 |
| 固定分支混入多个同类任务 | 每次进入阶段前检查 `Git Context`、当前分支和工作区；如同类任务并发，暂停让用户决定先完成当前任务还是人工拆分 |
| 未完成 feature 被热修复带入主分支 | 从 `harness/feature` 切到 `harness/fix` 前必须询问是否先合并 feature；默认不合并 |
| 分支同步引入冲突或误改历史 | 默认 merge 主分支，不自动 rebase；冲突时停止并记录到 `execution-plan.md` |
| 环境不明确导致验证失败 | 通过各项目 `docs/development.md` 收集自然语言环境说明，由 `.harness/environment.md` 统一整理，`execution-plan.md` 只记录本次任务引用和覆盖项 |
| 用户后续更改环境或验证策略 | 将用户覆盖项写入 `Questions And Overrides`，并重新通过 readiness gate |
| 忘记更新接口或使用文档 | 通过 `execution-plan.md` 的 `Documentation` 在编码前确认文档更新范围 |
| MCP、skill 或外部工具依赖不清 | 通过 `execution-plan.md` 的 `Tooling` 记录工具用途、可用性、权限风险、替代方案和用户确认状态 |
| 确认问题太多导致会话混乱 | 少量问题走会话；大量或异步问题走 `pending-decisions.md`，答案最终合并回 `execution-plan.md` |

## 16. 下一步

当前规划确认后，建议下一轮进入“阶段 2：skill 文档实现”：

1. 创建 `skills/complex-coding-harness/SKILL.md`。
2. 创建 `references/workflow.md` 协议文档。
3. 创建三个模板：`environment.md`、`execution-plan.md` 和 `pending-decisions.md`。
4. 暂不写脚本，先让协议可读、可执行、可审查。

# Execution Plan

## Problem

目标：落盘并实现 `complex-coding-harness` skill，明确复杂 coding 长任务如何稳定执行、如何防止上下文压缩后遗忘、如何在编码前完成方案敲定，并提供可复用 skill 文件、模板、示例、eval 和基础安装入口。

非目标：

- 不创建 `.agents/skills` 作为源码主结构。
- 不创建 Codex plugin 包。
- 不实现复杂初始化、checkpoint 或校验脚本。
- 不自动生成业务项目 `.harness/tasks/`。

验收结果：

- `docs/complex-coding-harness-skill-plan.md` 已落盘。
- 规划文档说明普通 `skills/` 源码结构，而不是把主结构放入 `.agents/skills/`。
- 规划文档说明运行时任务文件收敛策略，避免默认生成过多规则文件。
- 规划文档说明环境、工具、验证和用户覆盖机制。
- 规划文档说明多确认问题的处理策略：会话即时确认、`execution-plan.md` 内联确认、按需 `pending-decisions.md` 临时决策单。
- 规划文档说明 blocking 确认问题必须像 Plan 模式一样暂停：给出问题、ABC 推荐选项和自定义回答入口，等待用户回答后再继续。
- 规划文档将运行目录统一为 `.harness`，不再使用早期临时目录名。
- 规划文档首版只保留三个核心模板：`environment.md`、`execution-plan.md` 和 `pending-decisions.md`；不再把 `status.md`、`state.json`、`review.md` 或脚本带入首版。
- 当前项目自身任务记录按最终收敛思路更新。
- `skills/complex-coding-harness/SKILL.md` 已落地。
- `skills/complex-coding-harness/references/workflow.md` 已落地。
- `skills/complex-coding-harness/templates/environment.md`、`execution-plan.md`、`pending-decisions.md` 已落地。
- `examples/complex-coding-harness/`、`evals/complex-coding-harness/` 和 `skill.sh` 已落地。

## Context

已参考输入：

- 用户关于复杂 coding 长任务 skill 的需求。
- 用户要求参考 `taste-skill` 的普通 `skills/` 目录结构。
- 用户要求不要将本地目录做成 `.agents` 主结构。
- 用户要求参考 `vibe_coding` 的任务文件实践，但重新斟酌标准命名。
- 用户反馈当前规则文件过多，并追问环境不确定时如何向用户确认、用户如何更改。
- 用户进一步追问工作过程中出现很多确认问题时，应该使用临时 QA 文件、会话直接回答，还是更合适的方案。
- 用户明确要求遇到不确定问题时需要临时确认，类似 Plan 模式的问题 + ABC 答案 + 自定义回复，并且 agent 要停止当前工作，确认后再继续。
- 用户明确要求目录命名改为 `.harness`，并再次强调不要把参考项目中过重的问题带进来。

已读取本地参考：

- `E:\work\hl\videoForensic\AI\vibe_coding\tem_prompt.txt`
- `E:\work\hl\videoForensic\AI\vibe_coding\task_todo.md`
- `E:\work\hl\videoForensic\AI\vibe_coding\now_task.md`
- `E:\work\hl\videoForensic\AI\vibe_coding\CHANGELOG.md`
- `E:\work\hl\AI\harness-project-bootstrap` 中的 README、AGENTS 和设计文档。

已确认外部信息：

- Codex skill 以包含 `SKILL.md` 的目录为核心，`SKILL.md` 需要 `name` 和 `description`。
- Codex repo 自动发现目录是 `.agents/skills`，但本仓库源码结构可以采用普通 `skills/`，再由安装适配层复制或链接到目标工具位置。
- `taste-skill` 采用普通仓库结构，核心 skill 源文件位于 `skills/`。

## Options

### 方案 A：多文件规则面

- 做法：为方案、候选、决策、环境、工具、验证、文档、readiness、日志、自审分别创建独立文件。
- 优点：职责边界细，理论上便于单独审查。
- 缺点：默认文件过多，agent 容易漏更新，用户不知道该改哪个文件。
- 风险：流程看起来完整，但实际维护成本高，压缩恢复时反而增加阅读负担。
- 结论：不作为最终推荐。

### 方案 B：少文件主契约

- 做法：运行时默认只创建 `execution-plan.md` 和 `.harness/active-task.json`，需要多问题确认时才创建 `pending-decisions.md`。
- 优点：恢复入口清晰，用户修改入口明确，环境、工具、验证和 readiness 都在同一份主契约里保持一致。
- 缺点：`execution-plan.md` 需要设计好章节，避免变成无结构长文。
- 风险：如果单个章节长期膨胀，后续需要按需拆分。
- 结论：采用。

### 方案 C：所有确认问题都走会话

- 做法：agent 在聊天中直接提问，用户回答后继续。
- 优点：轻量、自然、适合 1 到 3 个关键问题。
- 缺点：问题多时会丢上下文，压缩后难恢复，用户回答不易审计。
- 结论：作为默认轻量通道，但回答必须写回 `execution-plan.md`。

### 方案 D：所有确认问题都生成 QA 文件

- 做法：每次有问题都创建或维护独立 QA 文件。
- 优点：可审计，适合异步填写。
- 缺点：小任务负担过重，会破坏少文件原则。
- 结论：不作为默认，仅在问题多、跨轮等待或需要审批记录时启用。

## Decision

采用少文件主契约方案：

- `execution-plan.md`：唯一人类可编辑主契约，包含 Problem、Context、Options、Decision、Implementation Plan、Environment、Tooling、Validation、Documentation、Questions And Overrides、Readiness Gate 和 Plan Approval。
- `.harness/active-task.json`：只保存当前任务指针、状态和下一步，不承载方案。
- `pending-decisions.md`：仅在多问题、异步或需审批记录时创建的临时决策单。

原因：

- 用户明确指出规则文件过多。
- 复杂任务最重要的是方案敲定质量，不是文件数量。
- 环境不确定、工具不确定、验证不确定都属于编码前门禁；workspace 级环境事实放入 `.harness/environment.md`，任务级方案仍收敛在 `execution-plan.md`。
- 用户后续修改时只需要改 `execution-plan.md` 的对应章节，或者在对话中给出覆盖项。
- 对确认问题采用三通道策略：少量问题走会话，中等问题内联到 `Questions And Overrides`，大量或异步问题使用可选 `pending-decisions.md`。
- `pending-decisions.md` 只是临时决策单，答案最终必须合并回 `execution-plan.md`，不能成为第二个真相来源。
- `pending-decisions.md` 使用固定填写区：`>>> 📝 USER INPUT: D-001 >>>` 到 `<<< END <<<`。
- 创建 `pending-decisions.md` 后，对话中也必须同步提出问题；用户可编辑文件回答，也可直接在会话中回答。
- 对 blocking 不确定问题采用 `confirmation_required` 检查点：先落盘问题，再向用户给出 ABC 选项和自定义入口，然后停止工作。
- 用户回答后才能恢复：先写回答案，再合并到 `execution-plan.md` 对应章节，再关闭问题并继续。
- managed 任务写完方案且 Readiness Gate 通过后，必须进入 `awaiting_plan_approval` 等待用户显式确认方案；用户确认前不得开始实现。
- `Implementation Plan` 不能只写阶段名；每个阶段必须说明做什么、怎么做、为什么、在哪做、参考来源、验证、风险和回滚。
- 实施阶段必须严格按批准方案逐阶段执行；每个阶段完成后必须完成 code review、验证、缺陷修复、提交代码、更新 changelog 和任务记录。
- 每个阶段开始和结束都必须重读 `.harness/active-task.json`、`.harness/environment.md`、当前 `execution-plan.md`、相关 `docs/development.md` 和 changelog，避免上下文压缩后遗忘要求。

## Implementation Plan

已完成：

- 新增 `docs/complex-coding-harness-skill-plan.md`。
- 新增 `.gitignore` 并说明 Git 跟踪与忽略策略。
- 将最终推荐结构收敛为 `SKILL.md`、`references/workflow.md` 和三个模板。
- 将运行时任务文件收敛为 workspace 级 `.harness/environment.md`、`.harness/active-task.json`、任务级 `execution-plan.md` 和按需 `pending-decisions.md`。
- 在规划文档中加入“不确定时如何向用户确认”和“用户如何覆盖”的协议。
- 在规划文档中加入 `pending-decisions.md` 的触发条件、问题生命周期、状态字段和模板格式。
- 在规划文档中加入 blocking 确认问题的停工等待规则、ABC 选项要求和 `confirmation_required` 状态。
- 将规划文档和当前任务记录收敛为 `.harness`。
- 删除首版不必要的 `status.md`、`state.json`、`review.md` 模板和脚本计划，仅保留三个核心模板。
- 修复规划文档中的内部矛盾：方案研究步数、过重 code review/verifier 表述、旧模板残留和 `pending-decisions.md` 的适用边界。
- 明确 `pending-decisions.md` 只承载 blocking 决策，不承载 non-blocking 假设。
- 再次复查使用流程章节，删除重复的验证边界条目，保持 `SKILL.md`、`workflow.md` 和运行时文件职责一致。
- 将用户自然语言 `docs/development.md` 与 `.harness/environment.md` 的规则写入规划：用户写大白话，agent 负责整理 workspace 级环境清单，任务计划只引用或记录临时覆盖项。
- 将“方案制定完成后必须等待用户确认才能实现”写入规划，新增 `awaiting_plan_approval` 和 `Plan Approval` 门禁。
- 将“实施方案必须基于本地代码结构和必要外部资料，每个阶段必须说明工作内容、做法、原因、位置和参考源”写入规划。
- 将“实施阶段每阶段必须重读任务文档、完成 code review、详细验证、修复缺陷、提交代码、更新 changelog 和任务记录”写入规划。

当前实施阶段：

### 阶段 2：skill 文档实现

目标：

- 创建 `skills/complex-coding-harness/SKILL.md`。
- 创建 `skills/complex-coding-harness/references/workflow.md`。
- 创建 `skills/complex-coding-harness/templates/environment.md`。
- 创建 `skills/complex-coding-harness/templates/execution-plan.md`。
- 创建 `skills/complex-coding-harness/templates/pending-decisions.md`。
- 保持首版无脚本，先让协议可读、可执行、可审查。
- 创建 `examples/complex-coding-harness/` 样例。
- 创建 `evals/complex-coding-harness/` 轻量 eval fixtures。
- 创建 `skill.sh` 安装适配入口。

用户批准：

- 当前会话中用户要求“开始完成当前这个 skill 项目”，视为阶段 2 实施批准。
- 阶段提交：允许按阶段提交；如 git 安全策略或仓库状态阻塞，记录原因。

本阶段验证：

- 检查 `SKILL.md` frontmatter 包含 `name` 和 `description`。
- 检查 `SKILL.md` 保持短，详细流程放在 `references/workflow.md`。
- 检查三个模板存在，且包含方案批准、workspace 环境清单、临时决策单填写区等关键规则。
- 检查没有创建首版不需要的脚本。
- 检查示例和 eval 覆盖 direct、managed、needs-clarification 和只读规划场景。
- 检查 `skill.sh` 不创建 `.harness/tasks/`，只负责安装 skill 源文件。

## Environment

当前任务是文档规划任务，不需要 Python、Node、前端 dev server、数据库或外部服务运行环境。

已使用的本地验证环境：

- PowerShell。
- `rg` 文本检索。
- PowerShell `ConvertFrom-Json` JSON 语法检查。

用户后续可覆盖：

- 如果后续进入 skill 实现阶段，可指定 Python 解释器、包管理器、脚本运行方式和是否允许联网。
- 如果后续需要安装到 Codex 或 Claude Code，可指定安装目标目录和复制/软链接策略。

## Tooling

已使用：

| 工具 | 用途 | 状态 | 风险 | 替代方案 |
| --- | --- | --- | --- | --- |
| skill-creator | 复核 skill 设计原则，控制 skill 文件数量 | available | 无写外部路径 | 手工按 Codex skill 规则设计 |
| PowerShell | 读取和校验本地文件 | available | 仅当前工作区写入 | 手工检查 |
| rg | 搜索旧命名和结构残留 | available | 无 | PowerShell Select-String |
| ConvertFrom-Json | 校验 JSON 文件语法 | available | 无 | Python json.tool |
| git | 检查仓库状态和提交阶段结果 | available with `safe.directory` override | 仓库所有权触发 safe.directory 检查 | 使用单次 `git -c safe.directory=...` |

后续实现阶段需要明确：

- 是否使用 Codex skill 官方校验方式。
- 是否需要联网查官方文档。
- 是否需要安装或调用 Codex、Claude Code、GitHub CLI、MCP 或其他外部工具。

## Validation

已执行：

- 校验 `.harness/active-task.json` 可解析。
- 检查未创建 `skills/complex-coding-harness/` 实现目录。
- 检索规划文档，确认最终推荐结构包含 `execution-plan.md`、`references/workflow.md`、`Questions And Overrides` 等核心设计。
- 检索规划文档，确认包含 `pending-decisions.md`、确认通道选择和问题生命周期设计。
- 检索规划文档，确认包含 `confirmation_required`、ABC 选项、自定义入口和停工等待规则。
- 检索规划文档，确认不存在旧目录名、旧确认队列名和过期模板计划。
- 校验 `skills/complex-coding-harness/SKILL.md` frontmatter 包含 `name` 和 `description`。
- 校验 `evals/complex-coding-harness/prompts.jsonl` 可逐行解析为 JSON。
- 检索 skill、模板、示例、eval 和安装脚本，确认包含 `Plan Approval`、`Readiness Gate`、`Commit Log`、`Implementation Progress`、`Code Review`、`USER INPUT`、Chrome DevTools MCP 和 `.harness/tasks/` 创建边界。
- 检查未创建 `skills/complex-coding-harness/scripts/`。

覆盖范围：

- 规划文档已落盘。
- 当前任务指针 JSON 语法有效。
- 未越过“暂不实现 skill”的用户边界。
- 文档已回答规则文件过多、环境不确定如何确认、用户如何覆盖的问题。
- 文档已修复复查发现的内部矛盾和过重设计。

不覆盖范围：

- 尚未验证实际 skill 是否可被 Codex 或 Claude Code 安装。
- 尚未在真实业务代码任务中前向测试该 skill。
- 未运行 `skill.sh install`，避免向用户本机 agent 目录写入文件。

## Documentation

已更新：

- `docs/complex-coding-harness-skill-plan.md`
- `.harness` 当前任务记录。
- `skills/complex-coding-harness/SKILL.md`
- `skills/complex-coding-harness/references/workflow.md`
- `skills/complex-coding-harness/templates/environment.md`
- `skills/complex-coding-harness/templates/execution-plan.md`
- `skills/complex-coding-harness/templates/pending-decisions.md`
- `examples/complex-coding-harness/`
- `evals/complex-coding-harness/`
- `README.md`
- `CHANGELOG.md`
- `skill.sh`

后续需要：

- 如需更完整发布，再补充 `research/complex-coding-harness/` 调研摘要。
- 如需真实安装验证，由用户确认目标 skills 目录后执行 `skill.sh install`。
- 如需质量增强，可用真实复杂任务做前向测试。

## Questions And Overrides

已确认：

- 当前阶段只写规划文档，不实现 skill。
- 源码主结构使用普通 `skills/`，不使用 `.agents` 作为仓库主结构。
- 最终推荐结构不默认拆成大量规则文件。
- workspace 级环境事实统一写入 `.harness/environment.md`；任务级环境引用、工具、验证和文档更新写入 `execution-plan.md`。
- 少量确认问题直接在会话中问，结果写回 `execution-plan.md`。
- 大量、跨轮或需审批的问题使用 `pending-decisions.md`，答案合并后仍以 `execution-plan.md` 为准。
- 若创建 `pending-decisions.md`，问题也同步输出到对话，允许用户直接会话回答。
- blocking 问题必须停止当前工作等待用户确认，不能用默认假设继续推进。
- 方案制定完成后必须等待用户显式确认才能进入实现阶段，Readiness Gate 通过本身不等于批准执行。
- 实施方案不能空泛，每个阶段必须具体到相关文件、模块、接口、配置、测试或文档，并写明参考源。
- 实施阶段每个阶段都必须执行 code review、验证、缺陷修复、提交代码、更新 changelog、更新 `execution-plan.md` 和 `.harness/active-task.json`。
- 前端阶段必须按 `.harness/environment.md` 使用指定浏览器验证工具；如果指定 Chrome DevTools MCP，就必须使用它自检。
- 后端阶段必须完成对应功能单元测试；涉及接口时补充接口 smoke 或契约检查。
- 每轮大修改后必须按环境清单执行 smoke。
- 如果验证失败或 code review 发现明显缺陷，必须修复后重新验证；小优化在批准范围内可以自我优化并记录。
- 首版只保留 `environment.md`、`execution-plan.md` 和 `pending-decisions.md` 三个模板，不实现脚本。
- `pending-decisions.md` 只放 blocking 决策；non-blocking 假设写入 `execution-plan.md`。

待后续实现阶段确认：

- 是否需要 `skill.sh` 支持 Codex 和 Claude Code 两类安装目标。
- 是否需要引入 eval 样例或 subagent 前向测试。

## Readiness Gate

| 检查项 | 状态 | 说明 |
| --- | --- | --- |
| 需求清晰 | pass | 当前阶段只做规划文档和任务记录收敛 |
| 上下文充分 | pass | 已读取本地参考、harness 参考、skill 规则和 taste-skill 结构 |
| 候选方案已比较 | pass | 已比较多文件规则面、少文件主契约、会话确认和临时决策单 |
| 最终方案已选择 | pass | 采用少文件主契约 |
| 环境已确认 | pass | 当前为文档任务，无运行环境依赖 |
| 工具依赖已确认 | pass | 当前只依赖本地文本检查和 JSON 检查 |
| 验证策略已确认 | pass | 以文档存在、JSON 解析、未创建 skill、关键文本检索为准 |
| 文档更新已确认 | pass | 更新规划文档和当前任务记录 |
| 风险已识别 | pass | 主要风险是过度拆分、用户覆盖入口不清、后续实现过早脚本化 |
| 人工确认点清楚 | pass | 后续实现阶段再确认安装目标、脚本范围和 eval 策略 |
| 多问题确认机制清楚 | pass | 已定义会话、内联、`pending-decisions.md` 三通道策略 |
| 临时确认检查点清楚 | pass | 已定义 `confirmation_required`、ABC 选项和停工等待规则 |
| 结构精简清楚 | pass | 已改为 `.harness`，首版只保留三个核心模板，不带入过重 harness 控制面 |
| 文档一致性复查 | pass | 已修复步数错误、旧模板残留、过重 review 表述和重复验证边界条目 |
| workspace 环境清单规则清楚 | pass | 已明确各项目 `docs/development.md` 可用自然语言，agent 生成 `.harness/environment.md`，任务计划只引用或覆盖 |
| 方案批准门禁清楚 | pass | 已明确 managed 任务必须等待用户显式确认方案后才能进入实现 |
| 实施方案质量标准清楚 | pass | 已明确每个阶段必须说明做什么、怎么做、为什么、在哪做、参考来源、验证、风险和回滚 |
| 实施阶段闭环规则清楚 | pass | 已明确每阶段必须重读任务文档、code review、验证、修复、提交、更新 changelog 和任务记录 |
| skill 核心文件已创建 | pass | `SKILL.md`、`workflow.md` 和三个模板均已创建 |
| 示例和 eval 已创建 | pass | 已覆盖 direct、managed、needs-clarification 和只读规划样例 |
| 安装适配已创建 | pass | `skill.sh` 只复制 skill 源文件，不创建 `.harness/tasks/` |

## Implementation Progress

| Stage | Status | Summary | Next action |
| --- | --- | --- | --- |
| 阶段 2：skill 文档实现 | completed | 已创建 `SKILL.md`、`references/workflow.md` 和三个模板 | 已完成验证 |
| 阶段 3：示例和 eval | completed | 已创建示例执行计划、临时决策单、eval prompts 和 expected | 已完成 JSONL 校验 |
| 阶段 4：安装适配 | completed | 已创建 `skill.sh` 基础复制安装入口 | 未执行安装，避免写入用户 agent 目录 |

## Code Review

| Stage | Finding | Severity | Resolution |
| --- | --- | --- | --- |
| 阶段 2 | 新增 skill 文档初稿使用英文说明，不符合项目中文说明要求 | major | 已改为中文说明，保留必要英文术语 |
| 阶段 2 | `pending-decisions.md` 模板存在 `<section>` 英文占位 | minor | 已改为中文“目标章节名称” |
| 阶段 3 | 示例中存在英文验证说明 | minor | 已改为中文说明 |

## Commit Log

| Stage | Repository | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| 阶段 2-4 | `dev-skills` | `32f969b` | `feat(complex-coding-harness): 实现复杂任务执行 skill` | `CHANGELOG.md` 已记录 |

# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

- 为 `complex-coding-harness` 增加“分段 patch 写入策略”，约束所有落盘写文件动作。
- 避免一次性写入过多内容导致 `apply_patch` 失败，例如一次性写入 600 多行文档或大段代码时出现 `Failed to apply patch`。
- 规则不只适用于代码实现阶段，也适用于规划文档、模板、eval、changelog、harness 任务记录和任何需要落盘的长内容。
- 让 agent 在写入前先判断内容规模，必要时先拆分，再按语义完整段落逐段 patch。

非目标（Non-goals）:

- 不改变现有 `apply_patch` 优先编辑规则。
- 不引入新的文件写入脚本或绕开 `apply_patch` 的通用写文件工具。
- 不改变 Git 分支策略、提交策略、长期进程规则或用户批准门禁。
- 不要求历史任务批量迁移，只要求后续自然使用新规则。

验收标准（Acceptance）:

- `SKILL.md` 增加核心规则：所有大段落盘内容必须先分段规划，再分段 patch 写入。
- `references/workflow.md` 增加独立的“分段 patch 写入策略”章节，覆盖适用范围、阈值、拆分方法、失败处理和验证要求。
- `templates/execution-plan.md` 增加“文件写入策略（File Write Strategy）”区块，用于任务级记录预计大文件、拆分方案和单次 patch 限制。
- eval 新增场景，覆盖大规划文档、大代码块、模板更新和 patch 失败后的恢复处理。
- 当前这份规划本身也按分段 patch 思路写入，避免一次性创建超长文件。
- 验证通过：
  - `quick_validate.py skills/complex-coding-harness`
  - `prompts.jsonl` JSONL 解析和 id 唯一性检查
  - 关键规则检索
  - `git diff --check`

约束（Constraints）:

- 遵守最小变更原则，只改与分段写入策略有关的规则、模板、eval 和 harness 任务记录。
- 新增规则必须简明，不把每次小改动都强制变成复杂流程。
- 中文文档为主，必要英文术语保留。
- 本阶段只制定规划，用户批准前不修改 skill 本体。

待确认项（Open uncertainties）:

- 无 blocking 待确认项。本计划默认建议设置硬阈值和建议阈值：超过硬阈值必须拆分，接近建议阈值应优先拆分。

## 上下文（Context）

本地代码和文档（Local code/docs）:

- `AGENTS.md` 已有“长内容写文件规范”，要求长文件或超过 500 行时分段规划、分段写入。
- `complex-coding-harness` 当前没有把该规则固化到 skill 自己的 workflow 和模板中。
- `references/workflow.md` 目前包含长期进程、Git、计划质量、规划自查、执行控制、提交信息等规则，但缺少专门的文件写入策略。
- `templates/execution-plan.md` 目前没有任务级“预计大文件”和“分段写入方案”记录位。
- 用户反馈曾经一次性写入 600 多行内容导致 patch 失败，说明仅靠通用经验不够，需要在 harness 中形成硬约束。

外部来源（External sources）:

- 本任务不需要联网资料；问题来自用户实际使用反馈和当前仓库规则缺口。

用户约束（User constraints）:

- 写文档、写规划文档、写代码、写模板、写 eval、写任何文件时都适用该策略。
- 不是只在实现阶段生效，规划阶段也必须生效。
- 需要限制单次写入范围，避免过大的 `apply_patch`。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 当前 skill 缺少专门的分段 patch 写入策略 | read | `skills/complex-coding-harness/references/workflow.md` 检索 | 需要新增 workflow 规则 |
| 当前模板缺少文件写入策略记录位 | read | `skills/complex-coding-harness/templates/execution-plan.md` | 需要新增模板区块 |
| 大 patch 可能失败并影响长任务稳定性 | confirmed | 用户反馈一次性 600 多行写入失败 | 需要设置单次 patch 限制 |
| 根 `AGENTS.md` 已有长内容分段写入思想 | read | 当前会话提供的 `AGENTS.md` | skill 规则应吸收并细化 |

## 根因分析（Root Cause）

### 当前规则没有单次 patch 上限

通用规则已经要求长内容分段写入，但 `complex-coding-harness` 没有明确单次 patch 的建议行数、硬上限、新建长文件的拆分方法和 patch 失败后的恢复规则。

### 规划阶段同样会写大文件

harness 的 `execution-plan.md` 往往包含问题、上下文、方案、阶段、验证、审查、提交和恢复摘要，规划阶段本身就可能产生几百行内容。因此该策略必须覆盖规划文档，而不是只覆盖代码实现。

### 大 patch 失败后恢复成本高

一次性 patch 失败时，agent 容易重复写入、漏写段落或破坏顺序。分段 patch 能把失败影响限制在单个语义段落内。

### 缺少任务级记录位

当前模板没有记录“哪些文件预计较大、如何拆分、每段限制是多少”的位置。上下文压缩后，后续 agent 容易忘记拆分约束。

## 候选方案（Options）

### 方案 A：只依赖根 AGENTS.md

优点是无需修改 skill。缺点是规则不会进入 skill workflow 和任务模板，长任务恢复后仍可能遗忘。

结论：不采用。

### 方案 B：只在 workflow 中增加一句提醒

优点是改动小。缺点是没有阈值、拆分方法、失败恢复和模板记录位。

结论：不采用。

### 方案 C：新增轻量但完整的分段 patch 写入策略

优点是能覆盖所有落盘写入场景，并通过模板和 eval 防止回归。缺点是每次大内容写入前需要多一步规模判断。

结论：采用方案 C。

## 推荐决策（Recommended Decision）

在 `complex-coding-harness` 中新增“分段 patch 写入策略”，覆盖所有文件落盘动作，包括代码、文档、规划文档、模板、eval、changelog 和 harness 任务记录。

核心原则：

- 小改动继续使用普通局部 patch。
- 大段新增或重写前必须先拆分。
- 分段边界必须保持语义完整。
- patch 失败后只重试失败段，不重写已成功段。
- 规划阶段和实施阶段都必须遵守。

## 规则设计（Policy Design）

### 适用范围

该策略适用于所有落盘写文件动作：

- 代码文件
- Markdown 文档
- harness 执行计划
- 模板文件
- JSON、JSONL、YAML
- changelog
- 测试和 eval fixture
- 任务状态记录

只要一次写入内容较长，就必须先判断是否需要分段。

### 单次 patch 限制

建议阈值：

- 单次 `apply_patch` 新增内容建议不超过 120 行。
- 单次 `apply_patch` 新增内容硬上限为 200 行。
- 预计新增超过 300 行时，必须先写明分段方案。
- 目标文件超过 500 行时，默认禁止整文件重写，优先局部 patch。

硬上限规则：

- 超过 200 行的新增内容必须拆分。
- 不能因为是文档或规划文件就豁免。
- 如果代码块、函数、类、配置节或 Markdown 章节超过 200 行，应按内部语义继续拆分。

### 分段边界

允许作为分段边界：

- Markdown 一级或二级章节
- 完整表格
- 完整函数或类
- 完整 JSON 对象或数组片段
- 完整 eval 条目集合
- changelog 的单个日期或阶段块

禁止的分段方式：

- 从代码块中间截断。
- 从 JSON 字符串或对象中间截断。
- 从 Markdown 表格中间截断表头和内容。
- 把一个函数拆成不可解析的半段。

### 写入前检查

写入前必须判断：

- 预计新增或替换多少行。
- 是否会触及大文件。
- 是否能局部 patch。
- 是否需要先写分段计划。
- 每段的语义边界是什么。

如果不确定行数，应保守拆分。

### patch 失败处理

如果 `apply_patch` 失败：

- 先判断是上下文不匹配、内容过大，还是工具层错误。
- 读取目标文件确认是否有部分写入。
- 只重试失败段，不重复写入已成功段。
- 如果失败原因可能是 patch 太大，必须继续缩小段落。
- 如果最小 patch 仍因工具层错误失败，应停止并记录阻塞，不用 shell 拼接文件绕过。

## 实施计划（Implementation Plan）

### 修改范围

预计修改：

- `skills/complex-coding-harness/SKILL.md`
- `skills/complex-coding-harness/references/workflow.md`
- `skills/complex-coding-harness/templates/execution-plan.md`
- `evals/complex-coding-harness/prompts.jsonl`
- `.harness/active-task.json`
- `.harness/environment.md`
- 当前任务规划记录

不修改：

- `process-manager`
- Git 分支策略
- 提交信息规则
- 长期进程管理规则

### Stage 1：核心规则

目标：

- 在 `SKILL.md` 中增加最短核心规则，说明所有大段落盘内容必须分段 patch 写入。

做法：

- 在核心规则中新增一条。
- 保持 `SKILL.md` 简短，详细规则放入 workflow。

验证：

- 检索 `分段 patch`、`单次 patch`。

### Stage 2：workflow 规则

目标：

- 在 `workflow.md` 中新增“分段 patch 写入策略”章节。

做法：

- 写明适用范围。
- 写明 120 行建议阈值、200 行硬上限和 300/500 行规划阈值。
- 写明分段边界、写入前检查、失败恢复和禁止绕过。

验证：

- 检索阈值、失败处理和适用范围。

### Stage 3：模板记录位

目标：

- 在 `execution-plan.md` 模板中增加“文件写入策略（File Write Strategy）”区块。

做法：

- 记录预计大文件。
- 记录分段方案。
- 记录单次 patch 限制。
- 记录 patch 失败后的处理策略。

验证：

- 检索 `File Write Strategy`、`分段方案`、`patch 上限`。

### Stage 4：eval 覆盖

目标：

- 增加 prompt fixture，覆盖常见失败模式。

场景：

- 大规划文档不得一次性写入。
- 600 行文档必须拆分。
- 大代码块必须按函数或类拆分。
- patch 失败后必须缩小段落并确认文件状态。
- 文档、changelog、JSONL 同样适用。

验证：

- JSONL 解析和 id 唯一性检查。

### Stage 5：验证、记录和提交

目标：

- 完成静态验证、记录和提交。

验证命令：

- `quick_validate.py skills/complex-coding-harness`
- JSONL 解析和 id 唯一性检查
- 关键规则检索
- `git diff --check`

提交：

- 使用 `git commit -F <message-file>`。
- 提交信息文件必须用无 BOM UTF-8。

## Plan Quality Gate

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 目标清晰 | pass | 限制所有大段落盘写入 |
| 影响范围清晰 | pass | 覆盖 SKILL、workflow、模板和 eval |
| 阶段可独立验证 | pass | Stage 1 到 Stage 5 均有验证方式 |
| 用户批准摘要可记录 | pass | 当前只规划，等待用户批准 |

## Plan Self-Review

| 类别 | 发现 | 处理 | 结果 |
| --- | --- | --- | --- |
| 缺陷 | 初始计划曾拆成多个临时补充文件 | 已合并回单一 `execution-plan.md` | fixed |
| 优化 | 单个规划文档继续增长时仍应小 patch 追加 | 本次合并按小章节逐段 patch 完成 | fixed |
| 缺失项 | 需要说明 patch 失败不是都等于内容太大 | 已在策略中区分上下文不匹配、内容过大和工具层错误 | fixed |
| 风险 | 单次 patch 阈值太低可能增加操作次数 | 采用建议阈值 120 行、硬上限 200 行，兼顾稳定和效率 | fixed |
| 一致性 | 本次规划自身必须遵守分段规则 | 已改回单一主规划文件，并用小 patch 分段合并 | fixed |

## Readiness Gate

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 目标和验收清楚 | pass | 本文件 `问题定义` |
| 上下文已收集 | pass | 已读取 active-task、environment 和现有规则检索 |
| 决策已记录 | pass | 采用轻量完整策略 |
| 实施阶段已细化 | pass | Stage 1 到 Stage 5 |
| 验证已确认 | pass | quick_validate、JSONL、rg、diff check |
| 规划自查已通过 | pass | `Plan Self-Review` |
| 阻塞问题已关闭 | pass | 无 blocking 问题 |

## Plan Approval

状态：

- approved

批准范围：

- 用户已回复“确认，接下来严格按规划开始实施”，批准 Stage 1 到 Stage 5。

提交授权：

- approved

## Execution Control

执行模式：

- run-to-completion

整体状态：

- completed

当前阶段：

- Final Delivery

剩余阶段：

- none

当前停止条件：

- all_approved_stages_completed

## 验证证据（Validation Evidence）

| 检查项 | 命令或方式 | 结果 | 备注 |
| --- | --- | --- | --- |
| active-task JSON | `python -c "import json; json.load(...)"` | pass | 输出 `active-task json ok` |
| Skill 结构验证 | `quick_validate.py skills/complex-coding-harness` | pass | 输出 `Skill is valid!` |
| JSONL 解析和 id 唯一性 | 解析 `evals/complex-coding-harness/prompts.jsonl` | pass | 输出 `jsonl ok 38` |
| 关键规则检索 | `rg "分段 patch|File Write Strategy|120 行|200 行|300 行|500 行|segmented-patch"` | pass | 命中 SKILL、workflow、模板和 eval |
| whitespace 检查 | `git diff --check` | pass | 仅有 Windows CRLF 提示 |

## 提交记录（Commit Log）

| 类型 | Commit | 说明 |
| --- | --- | --- |
| implementation | pending | 等待首次实现提交后回填 |

## Resume Summary

整体目标：

- 为 `complex-coding-harness` 增加分段 patch 写入策略。

当前状态：

- 已按批准方案完成 Stage 1 到 Stage 5，并完成验证；等待提交记录回填。

关键规则：

- 所有大段落盘写文件都必须先判断规模。
- 单次 patch 建议不超过 120 行，硬上限 200 行。
- 超过 300 行新增必须先写分段方案。
- 超过 500 行文件默认禁止整文件重写。
- 文档、规划、模板、eval、changelog 和代码都适用。

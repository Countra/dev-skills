# complex-coding-harness 后续优化分阶段规划

## 1. 文档定位

本文档用于规划 `complex-coding-harness` skill 的下一轮升级，不直接实现具体改动。它承接当前已完成的核心能力：

- managed 任务方案审批。
- `.harness` 可恢复任务状态。
- workspace 环境清单。
- 统一 harness 工作分支。
- 最终交付门禁。

当前目标是把已识别的优化项拆成可批准、可执行、可验证的阶段，后续只有用户明确确认后才能进入实现。

## 2. 当前 Git Context

主分支：

- `master`

当前工作分支：

- `harness/feature`

分支占用状态：

- `harness/feature` 当前包含尚未合回 `master` 的提交：`81cbb00 feat(complex-coding-harness): 增强最终交付门禁`。
- 该提交属于同一条 `complex-coding-harness` 优化链路，可以继续在当前 `harness/feature` 上规划。
- 后续实现前必须再次检查 `git log master..HEAD` 和 `git diff master...HEAD --name-only`，确认没有混入无关任务。

合并策略：

- 继续默认使用 merge，不使用 rebase。
- 本规划阶段不合回主分支。
- 后续实现阶段完成后，最终交付必须说明代码是否仍停留在 `harness/feature`，以及是否需要用户确认合回 `master`。

## 3. 优化目标

本轮规划覆盖四类升级：

1. 分支收口和分支占用检查。
2. eval 覆盖新增工作流能力。
3. 模板中文化和术语统一。
4. 安装脚本确定性增强。

非目标：

- 不新增大量规则文件。
- 不拆分 `workflow.md`。
- 不新增 `final-report.md`。
- 不引入复杂自动化 harness、UI 或多 agent 控制面。
- 不在方案未获用户确认前实现代码。

## 4. 当前问题分析

### 4.1 分支收口缺口

当前固定分支策略已经能解决“按任务类型进入统一分支”的问题，但还缺少两个收口规则：

- 进入固定分支后，如何判断该分支是否已有旧任务提交。
- 任务完成后，如何表达是否已合回主分支。

风险：

- 多个 feature 任务连续复用 `harness/feature` 时，旧任务提交可能混入新任务。
- 用户看到“提交完成”但不知道代码只在 harness 分支，未进入主分支。

### 4.2 eval 覆盖滞后

当前 `evals/complex-coding-harness/` 只覆盖早期行为：

- direct 任务分级。
- managed 任务分级。
- needs-clarification。
- 只读规划不创建 `.harness/tasks/`。
- 实施前等待方案批准。

新增能力尚未被 eval fixtures 覆盖：

- `Git Context`。
- 固定 harness 分支。
- 热修复插入确认。
- 最终交付门禁。
- 前端截图或替代证据。

### 4.3 模板语言和术语不统一

`execution-plan.md` 模板和示例中仍有英文占位，例如：

- `Goal`
- `Non-goals`
- `Acceptance`
- `Command/tool`
- `Screenshot`
- `Stage`

风险：

- 与项目“新增说明性内容优先中文”的规则不完全一致。
- 用户编辑模板时不如中文直观。
- 中英混合可能让后续文档风格继续漂移。

### 4.4 安装脚本不够确定

当前 `skill.sh install` 直接执行：

```sh
cp -R "$src_dir/complex-coding-harness" "$target/"
```

风险：

- 目标目录已存在时，可能混合旧文件。
- 不同 shell 或平台下复制行为可能不一致。
- 用户无法明确知道安装是覆盖、合并还是嵌套。

## 5. 分阶段实施方案

### 阶段 1：补充分支收口和分支占用检查

目标：

- 让固定 harness 分支在连续任务下仍可控。
- 让最终交付明确代码是否已合回主分支。

怎么做：

- 在 `workflow.md` 的 Git 工作分支章节增加分支占用检查。
- 在 `execution-plan.md` 模板的 `Git Context` 增加 branch occupancy 和 branch closure 字段。
- 在最终交付门禁中增加 branch status 输出要求。
- 在总规划文档或本升级规划中记录该策略。

为什么这么做：

- 固定分支降低了分支数量，但也增加了同类型任务混在一起的风险。
- 分支占用检查能在进入实现前暴露旧提交。
- 分支收口能避免“已提交”被误解为“已进入主分支”。

具体修改位置：

- `skills/complex-coding-harness/references/workflow.md`
- `skills/complex-coding-harness/templates/execution-plan.md`
- `docs/complex-coding-harness-skill-plan.md`
- `examples/complex-coding-harness/sample-execution-plan.md`

建议规则：

```text
进入 harness 分支后必须检查：
- git log <main>..HEAD
- git diff <main>...HEAD --name-only

如果存在未合回主分支的提交：
- 属于当前任务链路：记录到 Git Context 后继续。
- 不属于当前任务链路：暂停确认。

最终交付必须说明：
- 当前分支。
- 主分支。
- 是否已合回主分支。
- 如果未合回，代码仍停留在哪个 harness 分支。
```

验证：

- `rg` 检查 `branch occupancy`、`branch closure`、`git log <main>..HEAD`、`git diff <main>...HEAD`。
- `git diff --check`。
- JSONL eval 语法检查。

风险和回滚：

- 风险：规则过细导致 Git 章节变长。
- 回滚：只保留最终交付 branch status，删除详细检查命令。

### 阶段 2：补充 eval fixtures

目标：

- 让新增行为有最小评估样本。
- 避免后续改 skill 时遗漏 Git 和最终交付门禁。

怎么做：

- 扩展 `evals/complex-coding-harness/prompts.jsonl`。
- 扩展 `evals/complex-coding-harness/expected.yaml`。
- 更新 `evals/complex-coding-harness/README.md`。

为什么这么做：

- 当前 eval 只覆盖早期任务分级和方案审批，不覆盖后续新增规则。
- 轻量 fixtures 不引入复杂测试框架，符合当前项目精简原则。

具体修改位置：

- `evals/complex-coding-harness/prompts.jsonl`
- `evals/complex-coding-harness/expected.yaml`
- `evals/complex-coding-harness/README.md`

建议新增样例：

- `managed-git-context`：要求 managed 任务记录主分支、工作分支和同步来源。
- `hotfix-interruption`：从 `harness/feature` 插入 fix 时必须确认是否合并 feature。
- `final-delivery-evidence`：前端任务最终交付必须包含截图或替代证据。
- `branch-occupancy`：固定分支存在旧提交时必须暂停确认或记录归属。

验证：

- JSONL 逐行解析。
- YAML 结构可读。
- `rg` 检查新增 eval id。

风险和回滚：

- 风险：eval 变成伪测试，不能真正执行。
- 回滚：明确 README 中说明当前 eval 是 prompt fixtures，不声称自动判定通过。

### 阶段 3：模板中文化和术语统一

目标：

- 让模板更符合项目中文规则。
- 让用户填写时更直观。

怎么做：

- 将 `execution-plan.md` 模板中的说明性英文占位改成中文。
- 保留必要英文术语时采用“中文（English）”格式。
- 同步更新示例文件，避免模板和示例风格不一致。

为什么这么做：

- 当前模板里存在 `Goal`、`Acceptance`、`Command/tool` 等英文占位。
- 中文模板更适合当前仓库规则和用户使用习惯。

具体修改位置：

- `skills/complex-coding-harness/templates/execution-plan.md`
- `skills/complex-coding-harness/templates/environment.md`
- `skills/complex-coding-harness/templates/pending-decisions.md`
- `examples/complex-coding-harness/sample-execution-plan.md`
- `examples/complex-coding-harness/sample-pending-decisions.md`

建议术语：

```text
目标（Goal）
非目标（Non-goals）
验收标准（Acceptance）
命令/工具（Command/tool）
截图（Screenshot）
阶段（Stage）
状态（Status）
证据（Evidence）
```

验证：

- `rg` 检查残留英文占位。
- 人工审查表格列是否仍对齐。
- `git diff --check`。

风险和回滚：

- 风险：部分 agent 更习惯英文字段。
- 回滚：保留括号中的英文术语，不做纯中文替换。

### 阶段 4：增强安装脚本确定性

目标：

- 避免重复安装时混合旧文件。
- 让安装行为可预期、可解释、可回滚。

怎么做：

- 为 `skill.sh install` 增加目标目录存在检查。
- 如果目标 skill 已存在，默认拒绝覆盖并提示使用 `--force`。
- `--force` 时先删除目标 skill 目录，再复制源码 skill。
- 安装后检查目标 `SKILL.md` 是否存在。
- 输出最终安装路径。

为什么这么做：

- 当前 `cp -R` 可能在目标已存在时保留旧文件或产生嵌套目录。
- 安装脚本是用户真实试用 skill 的入口，应该确定。

具体修改位置：

- `skill.sh`
- `README.md`
- 必要时更新 `CHANGELOG.md`

建议接口：

```sh
./skill.sh install <target-skills-dir>
./skill.sh install --force <target-skills-dir>
```

验证：

- 在临时目录执行首次安装。
- 在同一临时目录再次安装，确认未带 `--force` 会拒绝覆盖。
- 使用 `--force` 安装，确认目标目录被替换且 `SKILL.md` 存在。

风险和回滚：

- 风险：删除目标目录属于敏感操作。
- 处理：只允许删除 `<target>/complex-coding-harness`，并校验目标路径不为空、不等于根目录。
- 回滚：保持现有简单安装脚本，只在 README 提醒手工清理。

## 6. 推荐实施顺序

推荐按以下顺序执行：

1. 阶段 1：分支收口和分支占用检查。
2. 阶段 2：eval fixtures 补充。
3. 阶段 3：模板中文化。
4. 阶段 4：安装脚本确定性增强。

原因：

- 分支收口是稳定性风险，优先级最高。
- eval 应紧跟规则更新，避免新增规则无人覆盖。
- 模板中文化影响面较大，但风险较低，适合在规则稳定后做。
- 安装脚本涉及文件删除语义，最后单独做，便于验证。

## 7. 方案批准门禁

Readiness Gate：

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 优化项范围清楚 | pass | 覆盖分支收口、eval、模板中文化、安装脚本 |
| 阶段拆分清楚 | pass | 已拆成 4 个阶段 |
| 每阶段修改位置清楚 | pass | 每阶段均列出文件 |
| 每阶段验证清楚 | pass | 每阶段均列出验证 |
| 风险和回滚清楚 | pass | 每阶段均列出风险和回滚 |
| 是否进入实现需用户批准 | pass | 本文档只规划，不实现 |

Plan Approval：

- 当前状态：`not_requested`
- 需要用户明确回复“按方案执行”或指定修改后，才能进入实现阶段。

## 8. 最终交付证据计划

本规划阶段的交付证据：

- 新增规划文档路径：`docs/complex-coding-harness-upgrade-plan.md`
- `.harness/active-task.json` 指向当前规划任务。
- 当前任务 `execution-plan.md` 记录 Git Context、阶段计划、验证和未覆盖范围。
- 文档级验证：关键文本检索、JSON 解析、`git diff --check`。

本规划阶段不需要截图，因为没有 UI 或可视化输出。

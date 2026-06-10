# Changelog

## 2026-06-10

### Stage 6: complex-coding-harness 最终交付门禁

- 新增 managed 任务最终交付门禁，要求输出任务结论、验证结果、未覆盖范围、commit 信息和关键证据。
- 补充前端、UI 和可视化任务的截图、日志、trace 或替代证据规则。
- 更新环境和执行计划模板，增加 evidence tools、artifact policy、Executed、Artifacts 和阶段证据字段。
- Commit: 本次提交
- Commit message: `feat(complex-coding-harness): 增强最终交付门禁`

## 2026-06-09

### Stage 5: complex-coding-harness Git 工作分支策略

- 新增统一 harness 工作分支策略，按任务类型使用 `harness/feature`、`harness/fix` 等固定分支。
- 补充主分支来源、分支切换安全检查、merge 同步策略和禁止自动 stash/rebase/reset 的约束。
- 增加热修复插入规则：从 feature 切到 fix 前必须确认是否先合并 feature 到主分支。
- 更新 `environment.md` 和 `execution-plan.md` 模板，新增 Git 信息和 `Git Context`。
- Commit: 本次提交
- Commit message: `feat(complex-coding-harness): 增加统一工作分支策略`

### Stage 2: complex-coding-harness skill 文档实现

- 新增 `skills/complex-coding-harness/SKILL.md`，定义复杂 coding 长任务的触发条件和核心执行约束。
- 新增 `references/workflow.md`，承载 managed 任务分级、方案审批、环境清单、阻塞确认、实施闭环和恢复协议。
- 新增三个模板：`environment.md`、`execution-plan.md`、`pending-decisions.md`。
- 新增仓库 `README.md`，说明当前 skill 位置、用途和核心约束。
- 新增 `examples/complex-coding-harness/`，提供执行计划和临时决策单样例。
- 新增 `evals/complex-coding-harness/`，提供 direct、managed、needs-clarification 和只读规划样例。
- 新增 `skill.sh`，支持从 `skills/` 复制安装 `complex-coding-harness`。
- Commit: `32f969b`
- Commit message: `feat(complex-coding-harness): 实现复杂任务执行 skill`

# Changelog

## 2026-06-09

### Stage 2: complex-coding-harness skill 文档实现

- 新增 `skills/complex-coding-harness/SKILL.md`，定义复杂 coding 长任务的触发条件和核心执行约束。
- 新增 `references/workflow.md`，承载 managed 任务分级、方案审批、环境清单、阻塞确认、实施闭环和恢复协议。
- 新增三个模板：`environment.md`、`execution-plan.md`、`pending-decisions.md`。
- 新增仓库 `README.md`，说明当前 skill 位置、用途和核心约束。
- 新增 `examples/complex-coding-harness/`，提供执行计划和临时决策单样例。
- 新增 `evals/complex-coding-harness/`，提供 direct、managed、needs-clarification 和只读规划样例。
- 新增 `skill.sh`，支持从 `skills/` 复制安装 `complex-coding-harness`。
- Commit message: `feat(complex-coding-harness): 实现复杂任务执行 skill`

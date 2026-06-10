# Changelog

## 2026-06-10

### Stage 10: complex-coding-harness 安装脚本确定性增强

- `skill.sh install` 增加目标目录存在检查，默认拒绝覆盖已有 `complex-coding-harness`。
- 新增 `--force` 安装模式，只替换目标 skills 目录下的 `complex-coding-harness`，并在复制后校验 `SKILL.md`。
- README 补充默认安装、强制替换和运行时任务文件边界。
- Commit: 待提交
- Commit message: `feat(complex-coding-harness): 增强 skill 安装脚本`

### Stage 9: complex-coding-harness 模板中文术语统一

- 将环境、执行计划和临时决策单模板调整为中文字段，并保留必要英文术语。
- 同步示例执行计划和临时决策单，避免模板与示例风格漂移。
- Commit: `db7872c`
- Commit message: `docs(complex-coding-harness): 统一模板中文术语`

### Stage 8: complex-coding-harness 工作流评估样例

- 补充 Git Context、热修复插入、最终交付证据和分支占用相关 eval fixtures。
- 更新 eval README，明确当前文件是 prompt fixtures，不是自动判分测试。
- Commit: `1cae648`
- Commit message: `test(complex-coding-harness): 补充工作流评估样例`

### Stage 7: complex-coding-harness 分支收口检查

- 增加固定 harness 分支的分支占用检查和分支收口记录要求。
- 更新执行计划模板和示例，要求最终交付说明代码是否已合回主分支。
- Commit: `9382919`
- Commit message: `feat(complex-coding-harness): 增加分支收口检查`

### Stage 6.5: complex-coding-harness 后续优化规划

- 新增后续优化分阶段规划，覆盖分支收口、eval、模板中文化和安装脚本确定性增强。
- 新增当前任务状态记录，承接用户批准后的分阶段实现流程。
- Commit: `2b7160b`
- Commit message: `docs(complex-coding-harness): 规划后续优化阶段`

### Stage 6: complex-coding-harness 最终交付门禁

- 新增 managed 任务最终交付门禁，要求输出任务结论、验证结果、未覆盖范围、commit 信息和关键证据。
- 补充前端、UI 和可视化任务的截图、日志、trace 或替代证据规则。
- 更新环境和执行计划模板，增加 evidence tools、artifact policy、Executed、Artifacts 和阶段证据字段。
- Commit: `81cbb00`
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

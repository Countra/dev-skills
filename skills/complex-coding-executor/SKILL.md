---
name: complex-coding-executor
description: 执行用户已批准的 complex-coding-planner managed 方案，并在多阶段或中断恢复场景中保持范围、验证、审查和授权边界。使用源码、Git 和真实验证作为事实来源，只维护 compact run-state.json；不生成 ledger、attestation、review receipt、逐命令证据或其它工作流 JSON。
---

# Complex Coding Executor

持续完成已批准工作。状态文件只服务于恢复和防漂移，不代替代码阅读、工程判断或真实验证。

## 启动与恢复

1. 读取 `.harness/active-task.json`、`execution-plan.md`、`plan-contract.json` 和已有 `run-state.json`。
2. 查看仓库规则、`git status`、相关 diff、近期提交和用户已有修改。
3. 运行 `harness_state.py status`。批准 digest 不匹配、存在 blocker 或需要重新批准时先停止。
4. 用简短摘要说明当前阶段、已完成工作、下一步和风险，然后继续；不要复述整份计划。

首次批准后运行 `approve --implementation`，同时记录 plan-review 模式和一句摘要。只有用户明确授权且该权限已列入 contract 请求时，才附加 `--commit`、`--external-write` 或 `--elevated-tool`；后续授权使用 `authorize`，未规划的新权限先重新批准。

## 执行循环

1. 选择依赖已完成的下一阶段并运行 `start`。
2. 阅读阶段范围内的调用方、实现、测试和配置，按仓库模式做最小而完整的修改。
3. 运行针对性验证。失败后先诊断并改变策略；同一失败命令不得原样执行第三次。
4. 用 `validate` 记录 required validation 的最近结果和简短摘要，不保存完整日志。
5. 按 contract 调用 `complex-coding-reviewer`：低风险按需、medium same-context、high independent。
6. 处理 blocking/major finding，重新运行受影响验证和审查，再用 `finish-stage` 收口。
7. 所有阶段完成后，先记录 contract 指定的 final validation，再执行 final review 和 `complete`。

阶段边界由工作内容决定，不为小修改创建 attempt、receipt 或状态事件。批准范围内的内部实现调整直接继续；范围、公共接口、Stage DAG、必需验证、关键依赖、迁移、风险或授权发生实质变化时进入重新批准。

## 状态与事实

- `plan-contract.json` 约束阶段 DAG、范围、阶段及最终验证和审查模式。
- `run-state.json` 只保存批准 digest、授权、当前阶段、最近验证、审查摘要和 blocker。
- Git、源码和实际测试输出是真实执行证据。状态与代码冲突时先调查，不靠写更多 JSON 解决。
- Reviewer 只返回人类可读结果；Executor 将模式、结论和一句摘要写入 run-state，不保存 findings JSON。

状态命令和恢复规则见 [execution-workflow.md](references/execution-workflow.md)，异常与命令安全见 [execution-safety.md](references/execution-safety.md)。

## 验证与命令稳定性

- 先运行受影响的测试、lint、typecheck 或 smoke；共享行为、跨模块契约和最终集成再运行完整套件。
- 多阶段任务完成全部 stage 后使用 `validate --stage final` 记录最终集成验证；缺失或失败时不能执行 final review 或 `complete`。
- 不把 reported/not-run 表述为验证通过。说明实际命令、结果和未覆盖风险即可。
- 宿主 deadline 不可靠、命令有卡死历史或可能长时间静默时，使用 `harness_bounded_command.py`。
- PowerShell 自动化使用 `-NoProfile -NonInteractive`；不要用 `Tee-Object` 保存测试日志，也不要用无界全系统进程扫描判断状态。
- 长期服务、Electron driver、watcher 和 dev server 使用 `process-manager`；普通测试、构建和 lint 不进入 Process Manager。

## 审查与交付

- `none` 阶段无需形式审查；`same-context` 和 `independent` 必须按 contract 完成。
- 独立 Reviewer 不可用且 contract 要求 independent 时 blocked，不降级后声称通过。
- 任意 blocking/major 修复都会使旧语义结论失效；重新审查当前完整目标。minor/advisory 可进入交付摘要。
- final review 对最终工作树执行。提交 hook 改写内容或提交后工作树不干净时，重新验证和审查，不生成 equivalence proof。
- 用户未授权提交时不要提交；授权提交时遵守仓库规范并使用 `git commit -F`。
- 最终答复聚焦改动、真实验证、审查结论和残余风险，不输出内部状态 JSON 或 gate 清单。

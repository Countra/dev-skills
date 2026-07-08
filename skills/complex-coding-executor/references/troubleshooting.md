# Complex Coding Executor Troubleshooting

本文件用于定位 `.harness` managed 任务执行阶段的常见流程故障。先定位事实，再决定继续、修正状态、请求用户确认或进入 `Plan Amendment Gate`。

## wrong task dir

症状：

- `harness_task_resolver.py` 找不到 `execution-plan.md`。
- active-task 指向不存在的目录。
- task_dir 解析后不在 workspace 内。

处理：

1. 读取 `.harness/active-task.json`。
2. 确认 `task_dir` 是否为空、拼写错误或包含不安全路径片段。
3. 运行 `harness_task_resolver.py --workspace .`。
4. 如果当前对话明确属于另一个任务，先让 planner 或用户确认 active task 切换。
5. 不要凭猜测创建新 task_dir 覆盖旧状态。

## stale active-task

症状：

- active-task 显示 completed，但用户要求继续执行。
- active-task 当前阶段与 `Execution Contract` 不一致。
- remaining stages 与计划正文冲突。

处理：

1. 以 `execution-plan.md` 为唯一主契约。
2. 读取 `Execution Contract`、`Execution Control`、`Implementation Progress` 和 `Resume Summary`。
3. 若只是摘要漂移，按计划主契约修正 active-task。
4. 若阶段边界、批准范围或验证策略发生变化，进入 `Plan Amendment Gate`。

## missing ledger

症状：

- status 显示 `ledger_exists = false`。
- final gate 缺少 stage_completed 证据。

处理：

1. 如果任务尚未进入实施阶段，可以接受 ledger 不存在。
2. 阶段开始后，用 `harness_ledger_append.py --event stage_started` 写入首条事件。
3. 阶段完成、验证失败、review finding、blocked 和 heartbeat 都应追加事件。
4. final 前用 `harness_ledger_summary.py` 生成摘要，并写入 `Ledger Evidence`。

## attestation mismatch

症状：

- `harness_attest_plan.py --check` 失败。
- preflight 报 plan hash 不匹配。

处理：

1. 先检查最近是否按批准范围更新了计划证据、进度或 Resume Packet。
2. 如果是预期更新，重新运行 attestation 并记录原因。
3. 如果修改影响 approved scope、stage、验证、风险、工具或提交策略，进入 `Plan Amendment Gate`。
4. 如果无法解释差异，停止执行并请求用户确认。

## HARNESS_DISABLED

症状：

- 环境变量 `HARNESS_DISABLED=1`。
- executor check 输出 skipped。

处理：

1. 不消费历史 active task。
2. 只执行用户当前 direct 请求或 advisory 检查。
3. 不更新 `.harness/active-task.json`、ledger 或 plan 状态。
4. 如用户希望恢复 managed 执行，请移除该变量后重新运行 preflight。

## Windows path and shell

症状：

- 路径大小写、盘符或反斜杠导致 resolver 失败。
- `py_compile` 写 `__pycache__` 遇到权限问题。
- PowerShell profile 输出与命令结果混杂。

处理：

1. resolver 使用 `Path.resolve()` 后的规范路径判断 containment。
2. 语法检查可用 `ast.parse` 替代会写缓存的 `py_compile`。
3. 重要结果以脚本退出码和明确 `PASS` / `FAIL` 为准。
4. 不用 shell 拼接、通配符删除或跨 shell 删除文件。

## hook advisory mode

症状：

- hook 没有强制阻断未完成任务。
- hook 只输出提醒或 system message。

处理：

1. 当前项目默认以 CLI gate 为准，hook 只是可选薄适配。
2. 先运行 `harness_exec_check.py --mode transition` 或 `--mode final`。
3. 只有显式 gated mode 且保护条件满足时，才考虑 hook 阻断。
4. hook 行为变化必须单独规划和验证。

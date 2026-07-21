# Complex Coding Executor Troubleshooting

先保留原始错误码、命令和 task-dir，再判断是修复 snapshot、补批准、进入 amendment，还是停止等待用户。不要用修改计划文字来掩盖结构错误。

## Task Pointer 与路径

症状：`TASK_POINTER_*`、`TASK_DIR_MISSING` 或 `TASK_PATH_OUTSIDE_WORKSPACE`。

1. 运行 `harness_task_resolver.py --workspace . --format json`。
2. active pointer 只能包含 `task_id`、`task_dir`、`run_state_path`、`updated_at`。
3. `task_dir` 和 `run_state_path` 必须解析在 workspace/task-dir 内；不要猜测或自动改指其他任务。
4. 显式 `--task-dir` 不依赖 stale active pointer，适合 final 或定点诊断。
5. 已完成任务应删除指向它的 active pointer；pointer 不保存 lifecycle、current stage 或 remaining stages。

## Contract 结构失败

症状：`TASK_CONTRACT_*`、`TASK_PLAN_*` 或 `TASK_ARTIFACT_*`。

1. 用 planner 运行 `harness_plan_check.py --task-dir <dir> --mode approval --format json`。
2. 检查封闭字段、稳定 ID、引用、Stage DAG、must coverage、scope、profile artifact 和 open decision。
3. 缺少当前 `plan-contract.json` 是普通结构错误；不存在旧格式恢复或 Markdown parser fallback。
4. 未批准时由 planner 修复；批准后任何实质修复都必须进入 Plan Amendment Gate。

## Attestation

症状：`ATTESTATION_MISSING`、`ATTESTATION_HASH_MISMATCH` 或授权拒绝。

1. 未批准 bundle 不能执行。用户批准后运行 `harness_attest_plan.py --mode write --approved-by <actor> --approval-summary <summary>`。
2. `--mode write` 和 `activate-amendment` 在写入/轮换前运行 current Planner approval checker；执行期不会用未来 checker 重判已批准 revision。
3. `--mode check` 会重算 plan、contract 和 approval-included artifacts 的哈希与大小。
4. 同一 revision 的 attestation 不可覆盖，也不得因正常执行进度重写；run-state、ledger 和执行证据不属于批准哈希集合。
5. immutable 文件变化时停止，归档旧 revision，生成递增 contract 和新 attestation，再激活 amendment。
6. commit、external write、elevated tool 各自独立授权；未授权时不得执行或伪造对应 evidence。

## Ledger 与 Snapshot

症状：`LEDGER_*`、`RUN_STATE_DRIFT`、snapshot 缺失或损坏。

1. 运行 `harness_ledger_summary.py --task-dir <dir> --format json`，以完整 ledger replay 为事实来源。
2. ledger 合法且 snapshot 缺失/滞后时，运行 `harness_exec_check.py --mode reconcile --task-dir <dir>`。
3. snapshot 领先 ledger、ledger 断号/非法 JSON、未知 stage 或非法 transition 必须 fail closed，不能自动猜测。
4. ledger append 已 fsync 后 snapshot 写失败时，保留 ledger；修复写权限后 reconcile。
5. evidence ref 必须是 task-dir 内真实文件；大日志写 artifact，ledger 只保存摘要和相对引用。

## Stage 与验证

症状：`RUN_STATE_STAGE_*`、`RUN_STATE_VALIDATION_*` 或 `RUN_STATE_REVIEW_*`。

1. `stage_started` 的 attempt 必须逐次递增，依赖 stage 必须完成。
2. `validation_recorded` 只能引用该 stage 声明的 VAL，必须携带 current attempt/target、command、exit code、claim source/boundary；只有 `observed + passed + exit_code=0` 可以建立通过门禁，`reported`/`not-run` 不可以。`duration_ms`、`termination`、`cleanup_verified` 可选，旧事件无需补写。
3. passed validation 必须引用真实 task-local evidence 文件；`RUN_STATE_VALIDATION_TARGET_MISMATCH` 表示验证和 stage receipt 不是同一 target/attempt，需在最终修改后重跑。
4. `review_recorded` 必须引用 `artifacts/reviews/**` 下的 canonical receipt，compact payload、双 digest、
   `reviewer_mode`、`independence_claim`、`dispatch_id`、coverage/gap/lineage 摘要、`stage_id`、`attempt` 与 Reviewer 公共
   validator 结果必须精确一致。新事件会自动增加 `report_digest` 绑定 receipt bytes；旧 ledger 缺少该可选字段仍合法，但不能使用 commit-equivalence 快速路径。
5. `REVIEW_DISPATCH_STALE` 表示 receipt 后目标或 brief/standards/validation context 已变化；修复后必须生成新
   target/context/dispatch/result/receipt，不得只改 ledger 摘要。
6. `RUN_STATE_REVIEW_EVIDENCE_MISSING`、`REPORT_INVALID` 或 `PAYLOAD_MISMATCH` 分别表示 evidence ref 未绑定、路径越界/缺失或 compact payload 不是由 receipt 派生。
7. `RUN_STATE_REVIEW_REQUIREMENTS_MISMATCH`、`CONSTRAINTS_MISMATCH` 或 `VALIDATION_CONTEXT_MISSING` 表示 managed brief/context 没有精确消费 contract 与当前验证证据，需重建 brief/context。
8. `RUN_STATE_REVIEW_SCOPE_MISMATCH` 还可能表示 target paths 没有精确覆盖 canonical `allowed_changes`，或 final commit 后仍在使用 working-tree target；重新按 contract 生成完整 target，不要只改 receipt 摘要。
9. validation failure/not-run 会撤销当前 stage review；failed review 不建立通过门禁。required VAL 和当前 attempt 的 `stage-delta` receipt 未通过时不能追加 `stage_completed`。
10. 当前 stage 完成后运行 `--mode transition`；仍有 remaining stages 时继续，不把阶段边界当最终停止点。

Dispatch 专项诊断：

- `REVIEW_DISPATCH_REQUIRED_UNAVAILABLE`：high-risk stage 或 final 的 strict Agent 工具不可用，任务 blocked，不能同上下文放行。
- `REVIEW_DISPATCH_AGENT_UNCLOSED`：保留 candidate evidence 并恢复关闭；未 closed 前不能记录 passed review。
- `REVIEW_DISPATCH_PROVENANCE_MISMATCH`：检查 dispatch/result ref、raw digest、Agent ID 和 compact provenance，不编辑旧 receipt。
- `REVIEW_RESULT_INVALID`：只有纯 schema 错误允许原 Agent 修正一次；语义失败或第二次失败创建新 attempt/blocked。

## 有限命令与静默卡死

症状：命令长时间无输出、取消无效、全系统进程查询卡住，或重复检查后仍无法确认状态。

1. 先停止原样重跑；相同失败命令第二次前必须缩小查询范围、改参数、改工具或改证据，禁止第三次原样执行。
2. 已知 PID 用 PID 查询，长期服务用 Process Manager status；不要用无界 `Get-CimInstance Win32_Process` 或全系统 command-line 正则扫描。
3. PowerShell 自动化使用 `-NoProfile -NonInteractive`；profile 的主题、图标或缓存 access denied 只是 shell 噪声，不能据此判断项目 ACL。
4. 宿主 deadline 不可靠或命令有卡死历史时使用 `harness_bounded_command.py`。`RUN_STATE_COMMAND_TIMEOUT` 表示返回 124 且清理完成；`RUN_STATE_COMMAND_CLEANUP_FAILED` 返回 125 并列出精确 PID；`RUN_STATE_COMMAND_LAUNCH_FAILED` 返回 126。
5. cleanup 失败时只处理结果列出的本次 PID，不做全局匹配、不自动提权；仍无法回收则 blocked。
6. 不用 `Tee-Object` 保存测试日志。保留实时输出，task evidence 只写结果 JSON 与结构化摘要。

## Dependency Execution Gate

症状：`EXEC_DEPENDENCY_*`。

1. 先运行 `harness_dependency_check.py --mode preflight --task-dir <dir> --format json`；`none` 应返回 `not-applicable`。
2. `EVIDENCE_STALE` 要求在线刷新 task-local runtime receipt；不得改写批准 artifact 的日期或自动升级到 latest。
3. `APPROVAL_DRIFT`、`RESEARCH_DRIFT` 或 hard gate 变化必须记录 Research Drift；影响批准选择时进入 amendment。
4. `IMPLEMENTATION_DRIFT` 表示原生 package-manager 验证未通过，先把 manifest/lock/版本修正到批准策略，不用修改计划掩盖。
5. `RECHECK_BLOCKED` 表示资料或原生工具不可访问；记录 `blocked-by-access`，有效批准证据仍在 freshness 窗口内时才可按计划证据继续。
6. transition/final 时批准证据已过期，继续显式传同一份已验证 `--dependency-receipt`；checker 不自动搜索“最新”文件。

## Block、Research Drift 与 Amendment

1. 普通可恢复阻塞写 `blocked`，解决后写 `resumed`。
2. 用户可见范围、公共接口、Stage DAG、required validation、风险等级、依赖决策、数据迁移或授权变化写 `research_drift`/`amendment_requested`，设置 reapproval 后停止；批准范围内内部实现调整写 note。
3. `harness_attest_plan.py --mode archive` 归档当前 immutable set、attestation、ledger 和可用 run-state。
4. planner 生成递增 revision 并重新批准后，用 `--mode write` 写新 attestation。
5. `--mode activate-amendment --archive-dir <dir> [--carry-stage STG-XX]` 轮换运行文件，并以首条事件连接上一 ledger hash；只继承上一 ledger 已完成且契约语义未变的 stage。

## Final 与提交

1. 最后一个 stage 完成后先确认无 current/remaining stage，并生成 `code-review/final-integration` receipt；此时尚不追加 `completed`。
2. contract 预期 final 提交且 attestation 已授权时，完成 pre-commit 门禁并实际提交。运行 `harness_commit_equivalence.py ... create`：成功时把返回的 `commit_payload` 与全部 `evidence_refs` 原样写入 final `commit_recorded`，pre-commit strict receipt 会被 proof 保留。
3. `RUN_STATE_REVIEW_EQUIVALENCE_UNAVAILABLE` 表示旧 receipt 或前置条件不支持快速路径；`MISMATCH`、`DIRTY`、`INVALID` 分别表示提交/范围漂移、额外 source 变更或 proof/摘要无效。任何失败都应写入不含 proof 的普通 `commit_recorded`，再对真实 commit-range 生成新的 strict `final-integration` receipt；不要编辑 proof 绕过。
4. commit expectation 与当前 final receipt 闭环后追加 `completed` 并关闭 active pointer，再运行 final；final 要求 lifecycle completed、pointer 已关闭且 receipt freshness 仍有效。
5. 提交前完成 Reviewer 审查、`git diff --check` 和范围检查；同仓库 Git 命令串行。
6. 使用 `git commit -F <message-file>`，不要用多个 `-m` 拼接正文。

## Windows 与沙箱

- 用 `Path.resolve()` 后的规范路径判断 containment。
- 避免会写 `__pycache__` 的语法检查；可用 `python -B`、AST parse 或隔离测试目录。
- Windows 本地代码页可能影响子进程 JSON；公共 runner/checker 显式使用 UTF-8 模式。
- 重要结果以退出码和 `PASS`/`FAIL [CODE]` 为准；PowerShell 自动化使用 `-NoProfile -NonInteractive`，profile 噪声不是脚本输出的一部分。
- `HARNESS_DISABLED=1` 时不消费 active task，也不写 pointer、attestation、ledger 或 state。

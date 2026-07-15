# Complex Coding Executor Workflow

本文件定义批准后的执行流程。任务字段与状态机以 planner 的 `references/task-contract.md` 为准。

## 目录

1. [入口与真相源](#入口与真相源)
2. [Preflight](#preflight)
3. [初始化](#初始化)
4. [Stage Loop](#stage-loop)
5. [Development Quality Check](#development-quality-check)
6. [Dependency Execution Gate](#dependency-execution-gate)
7. [Research Drift](#research-drift)
8. [恢复与 Reconcile](#恢复与-reconcile)
9. [Plan Amendment](#plan-amendment)
10. [Git 与提交](#git-与提交)
11. [长期进程](#长期进程)
12. [最终门禁](#最终门禁)
13. [错误恢复](#错误恢复)

## 入口与真相源

按需读取：

1. `.harness/active-task.json`：只定位 task-dir/run-state。
2. `plan-contract.json`：Stage DAG、范围、验证、风险和授权策略。
3. `execution-plan.md` 与 approved artifacts：批准意图和理由，只读。
4. `attestation.json`：用户批准、实际授权和不可变哈希集合。
5. `ledger.jsonl`：追加式执行历史与证据引用。
6. `run-state.json`：可由 ledger 重建的当前快照。
7. `.harness/environment.md`：稳定 workspace 能力。

禁止从 Markdown 标题、active pointer 或对话摘要推断 lifecycle、current/remaining stages、stop 或 next action。缺少当前必需结构时返回 `TASK_*` 诊断，不做版本判断或 fallback。

## Preflight

执行任何写操作前：

1. 解析 pointer/task-dir，确认所有路径位于 workspace/task-dir。
2. 调用 planner 公共 CLI：`harness_plan_check.py --task-dir <task-dir> --mode approval`。
3. 校验 attestation 的 task/revision、批准摘要、authorizations 和 immutable hash set。
4. 读取 ledger 并 replay；若 snapshot 存在，比较所有权威字段。
5. 确认没有 `reapproval_required`、blocked stop 或非法事件。
6. 检查工作树、Stage Contract、工具权限、Process Manager Gate 和 commit authorization。
7. 读取 `dependency_selection`；`none` 直接跳过，其它模式校验证据年龄、manifest-to-stage 映射和可选 runtime recheck。批准证据过期时必须提供 task-local `--dependency-receipt`，不能修改 immutable artifact 刷新日期。

推荐命令：

```text
python scripts/harness_exec_check.py --workspace <workspace> --task-dir <task-dir> --mode preflight [--dependency-receipt <task-relative-json>]
```

preflight 是只读检查。首次启动由 ledger append 的 `execution_started` 事件创建 run-state；不得让 checker 隐式修改状态。

## 初始化

用户批准后先生成 attestation。批准记录必须明确：

- implementation：必须为 true。
- commit、external_write、elevated_tool：只按用户明确授权记录。
- approval summary、批准时间和批准主体。
- plan、contract 与 approval-included artifacts 的 SHA-256。

然后追加 `execution_started`。append 工具必须：

1. 构造下一个连续 seq/event_id。
2. 在内存中把候选事件与已有 ledger 完整 replay。
3. 候选事件非法时不写文件。
4. 先 append + flush/fsync ledger，再 atomic replace run-state。
5. snapshot 写失败时保留合法 ledger，下次通过 reconcile 恢复。

## Stage Loop

每个 stage 严格执行：

1. `transition/status` 确认 stage 依赖完成且无 stop/reapproval。
2. 追加 `stage_started`，attempt 必须单调递增。
3. 读取 contract 中的 allowed/forbidden changes、REQ/AC/NFR、VAL、risk 和 commit expectation。
4. 读取直接定义、调用方、配置、数据、错误路径、测试、standards 和必要 artifacts。
5. 在批准范围内实现，失败写 `attempt_failed` 和证据；重试需新的 attempt。
6. 执行 Development Quality Check 和 code review，写带摘要及 `development_quality=passed` 的 `review_recorded`。
7. 逐项运行 required VAL，写带结果摘要的 `validation_recorded`；大证据使用 task-dir 相对 evidence refs。
8. stage 涉及批准 dependency manifest 时，用生态原生命令验证 package identity、resolved version、version policy、manifest 和 lock，并通过 `harness_dependency_check.py --mode stage` 校验 runtime receipt。
9. 修复 blocking/major findings 或失败验证并重跑。
10. 只有所有 required VAL、dependency stage gate 和 review passed，才能追加 `stage_completed`。
11. 仍有 ready stage 时立即继续；stage boundary 不是停止条件。

大日志、截图、trace 和报告写入 task artifacts；ledger 只保存摘要和相对路径。不得写入 token、秘密或无意义终端转储。

## Development Quality Check

每个 stage 对照 standards artifact 和 contract 映射复核：

- standards：项目规则与适用官方规范。
- static quality：syntax、format、lint、typecheck、build、unit/integration tests。
- architecture：职责、依赖方向、公共接口、数据所有权和迁移边界。
- pattern：抽象必要性、模式取舍和过度设计。
- coupling/cohesion：跨层调用、循环依赖、共享状态、重复和过宽接口。
- validation：required evidence、未覆盖范围和替代证据。

review 结果必须真实。blocking/major finding 未关闭时 reducer 不应接受 stage completion；改变批准边界时进入 amendment。

## Dependency Execution Gate

- `dependency_selection` 缺失或 mode=`none` 时常量时间返回，不要求在线查询或 runtime receipt。
- 非 `none` preflight 读取批准 artifact 的最早 signal 日期，按 critical-runtime/runtime/dev-build 的 30/60/90 天上限计算新鲜度，并确认 add/upgrade/replace 的每个 manifest 都映射到批准 stage。
- 证据过期或执行期主动复核时，在线采集事实并把 closed JSON receipt 写入 task execution artifacts；通过 `--dependency-receipt` 显式传入 preflight、transition 和 final。checker 本身不联网、不安装包、不写 ledger。
- 涉及 manifest 的 stage 先读取批准 identity/version policy/path，再使用该生态官方包管理器验证 resolved version、manifest 与 lock；通用 checker 只消费受控结论，不自行实现跨生态版本或 lock parser。
- identity、source、selection class、批准版本基线、version policy 或 manifest path 不一致是 approval drift；hard gate/advisory 变化是 Research Drift；原生验证失败是 implementation drift，应先修正实现，不能自动追 latest 或替换包。
- runtime receipt 的 closed schema、命令和诊断见 `dependency-execution.md`。

## Research Drift

发现计划未覆盖且可能改变行为的框架/API/协议/依赖/平台事实时：

1. 追加 `research_drift`，记录来源、影响和当前 stage。
2. 在不改变批准边界时补官方/一手证据和验证后恢复。
3. 影响 scope、DAG、required VAL、风险、依赖、外部写入或授权时追加 `amendment_requested` 并停止。
4. 无法访问资料时保留 `blocked-by-access`；不得凭记忆继续。

依赖 receipt 的 hard gate、弃用、支持线或 applicable advisory 发生变化时至少追加 `research_drift`；若变化影响批准 package、version policy、风险接受或选择结论，必须进入 amendment。仅事实刷新且结论不变时保留 runtime receipt evidence 并继续。

## 恢复与 Reconcile

每次恢复都先完整 replay ledger，再读取 snapshot：

- ledger 合法且 snapshot 缺失/滞后：`reconcile` 可 atomic rewrite snapshot。
- snapshot 与 replay 完全一致：继续 `next_action`。
- snapshot 领先、ledger 断号/重复/非法 JSON、未知 stage、非法转移或 attestation mismatch：fail closed。
- run-state 不是第二历史源；不得通过编辑 snapshot 绕过 ledger。

`status` 只读输出 lifecycle、current/completed/remaining、last seq、next/stop、drift 和 evidence summary。`reconcile` 只能写可证明的 replay 结果，不能修复损坏 ledger 或批准集合。

## Plan Amendment

amendment 必须由用户重新批准：

1. 将上一 revision 的 immutable set、attestation、ledger 和 run-state 归档到 `artifacts/amendments/revision-N/`。
2. planner 生成递增 revision 的 plan/contract/artifacts，并重跑 approval checker。
3. 用户批准后生成新 attestation。
4. 只有上一 ledger 已完成，且 stage 本体及其 REQ/AC/NFR/VAL 定义与归档 contract 语义相同，才允许作为 completed stage 继承。
5. 轮换当前 ledger/run-state，新 ledger 首条 `amendment_approved` 记录前一 archive/hash 和获批继承 stages。
6. 未批准时不得继续代码、Git、外部写入或长期进程操作。

禁止直接改写 approved plan 或 contract 后重新哈希来冒充批准。

## Git 与提交

- 同一 working tree 的 Git 命令串行；禁止并发 agent/shell 执行同仓库 Git。
- 不自动 stash、reset、rebase、切分支、覆盖未知改动或删除 lock。
- 遇到 index.lock 时解析精确路径，确认文件稳定且无相关/未知 Git 进程，只删除该精确文件并立刻重跑 status。
- stage 的 `commit_expectation` 只表示计划时机；attestation 中 commit authorization 为 false 时不得提交。
- `stage` expectation 在对应 stage 完成后提交并记录该 `stage_id`；`final` expectation 在所有 stage 完成后、`completed` 事件前记录。
- 提交前完成 required validation、review、`git diff --check` 和范围审查。
- 使用单个 `git commit -F <message-file>`；标题后一个空行，bullet 间无空行。
- 成功提交后写 `commit_recorded`，payload 必须包含 `commit` hash 和 `repository`，可按需补充 message/scope；不要伪造未发生的提交。

## 长期进程

存在 process-manager skill 时，dev server、Web/API 服务、worker、watcher 和模型服务必须由它管理。先用统一 `pm_manager.py status` 检查 manager，仅在 `manager_offline` 时执行 `pm_manager.py start`；不得判断 OS/backend 或选择平台入口。

按 manager authenticated identity -> service config validation -> start/processKey -> ready/status -> bounded logs -> stop/restart 的顺序取证。停止或替换 run 时必须看到 `cleanupVerified: true` 与 `stopResult.ownerEmpty: true`；manager 由本任务创建且不再需要时，还要通过统一 stop/shutdown 证明 bootstrap cleanup，计划明确保留时则记录保留原因。

普通流程不先运行 `pm_doctor.py`。只有统一操作失败且 capability/selection reason 不清楚时才按需诊断；manager 无法建立安全 owner 且阶段必需长期进程时进入 blocked，不得退回手写后台启动。

finite test、build、lint、format、migration 和一次性脚本直接运行。禁止 `Start-Process`、shell background、`nohup` 或自制 launcher 绕过 process-manager。manager 不可用且阶段必需长期进程时进入 blocked。

## 最终门禁

完成最后一个 stage 后：

1. 确认每个 stage 都有 required VAL、review 和 `stage_completed` evidence。
2. 核对 attestation、run-state、ledger、授权、Git/changelog 和 artifacts。
3. 运行 planner/executor unit、conformance/eval、skill validator 和 `git diff --check`。
4. 做最终 code review；修复 blocking/major findings 并重跑相关验证。
5. 未授权时不得提交；已授权且 contract 预期 final commit 时，使用显式 task-dir 收口 pointer、实际提交并追加无 `stage_id` 的 `commit_recorded`。提交失败时恢复 pointer 或保持显式 task-dir 恢复路径，不能追加伪证据。
6. 在所有已授权 commit expectation 都有 evidence 后追加 `completed`；未提交任务此时删除指向它的 active pointer。
7. 确认 replay lifecycle 为 completed、active pointer 已关闭，再用显式 task-dir 运行 final checker。只有 final 通过后才能最终回复。

最终回复说明核心改动、实际验证、未覆盖范围、review 结论、branch/commit、关键证据和残余风险。

## 错误恢复

失败动作记录 command/tool、attempt、原因、影响和下一策略。相同原因不得静默重复第三次；第三次前必须改变策略、缩小范围、补上下文、使用替代验证或进入 blocked。

常见诊断：

- `TASK_POINTER_*`：active pointer 缺失、含运行字段或路径越界。
- `TASK_CONTRACT_*`：当前 task contract 缺失或结构/语义无效。
- `ATTESTATION_*`：批准缺失、授权不足或 immutable hash mismatch。
- `LEDGER_*`：事件 JSON、seq、ID、引用或转移无效。
- `RUN_STATE_*`：snapshot 无效、drift 不可修复或 stage/validation/review 未闭环。

详细排查见 `troubleshooting.md`。历史任务缺少当前必需文件时按结构错误处理，不迁移、不 fallback。

# Complex Coding Executor Workflow

本文件定义批准后的执行流程。任务字段与状态机以 planner 的 `references/task-contract.md` 为准。

## 目录

1. [入口与真相源](#入口与真相源)
2. [Preflight](#preflight)
3. [初始化](#初始化)
4. [Stage Loop](#stage-loop)
5. [Review Handoff](#review-handoff)
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
2. 校验 attestation 的 task/revision、批准摘要、authorizations 和 immutable hash set；它是批准后的唯一 canonical approval proof。
3. 读取 ledger 并 replay；若 snapshot 存在，比较所有权威字段。
4. 确认没有 `reapproval_required`、blocked stop 或非法事件。
5. 检查工作树、Stage Contract、工具权限、Process Manager Gate 和 commit authorization。
6. 读取 `dependency_selection`；`none` 直接跳过，其它模式校验证据年龄、manifest-to-stage 映射和可选 runtime recheck。批准证据过期时必须提供 task-local `--dependency-receipt`，不能修改 immutable artifact 刷新日期。

Planner semantic approval 只在新 attestation 写入或 amendment 激活前由当时的 current checker 执行。preflight、transition、recovery 和 final 不调用未来 Planner/Reviewer checker 重判历史；plan、contract 或 approval-included artifact 的任何变化仍由 attestation hash mismatch 拒绝。

推荐命令：

```text
python scripts/harness_exec_check.py --workspace <workspace> --task-dir <task-dir> --mode preflight [--dependency-receipt <task-relative-json>]
```

preflight 是只读检查。首次启动由 ledger append 的 `execution_started` 事件创建 run-state；不得让 checker 隐式修改状态。

## 初始化

用户批准后先通过 `harness_attest_plan.py --mode write` 生成 attestation。该入口在写文件前运行 current Planner approval checker；checker 失败不得创建或覆盖 attestation。批准记录必须明确：

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
6. 为当前 allowed paths、stage ID 和 attempt 生成 canonical target；按 standards index 和 Development Quality Gate 执行 required VAL，把命令、observed/reported/not-run 来源、exit code、claim boundary、当前 target digest 与 task-local evidence refs 写入 closed `validation_recorded`。
7. 生成 managed review brief/context：brief 精确列出当前 REQ/AC/NFR 与 STG/VAL 约束，claim refs 引用有效 validation evidence；context 至少包含 brief、plan、contract、适用 standards 和 validation 文件。再用 `complex-coding-reviewer` 的 `code-review/stage-delta` 审查当前 target/context，记录公共 validator 派生的 compact `review_recorded`。
8. stage 涉及批准 dependency manifest 时，用生态原生命令验证 package identity、resolved version、version policy、manifest 和 lock，并通过 `harness_dependency_check.py --mode stage` 校验 runtime receipt。
9. 修复 blocking/major findings 或失败验证并重跑。
10. 只有所有 required VAL、dependency stage gate 和 review passed，才能追加 `stage_completed`。
11. 仍有 ready stage 时立即继续；stage boundary 不是停止条件。

大日志、截图、trace 和报告写入 task artifacts；ledger 只保存摘要和相对路径。不得写入 token、秘密或无意义终端转储。

## Review Handoff

Executor 负责实现、修复、运行验证和写 ledger；Reviewer 负责正式 `code-review` verdict。Executor 仍须把 standards、静态质量、架构边界、模式取舍、耦合/内聚和 required evidence 落实到实现及验证中，但不能把自己的检查结论伪装成正式审查。

每个 stage：

1. 保存可重建的 stage baseline，并确保 target 覆盖 tracked、staged/unstaged、deletion 与批准范围内 untracked 文件。
2. 把 stage `allowed_changes` 转为去重后的 canonical path prefixes，调用 Reviewer target CLI 生成带 `stage_id`/`attempt` 的 `git-diff` target；target 的 `paths` 必须与该集合精确一致，不允许用局部路径漏掉批准范围，也不允许用全仓范围掩盖 scope drift。
3. validation event 必须使用同一 target digest/current attempt；修复后 target 改变时重跑受影响 VAL，reported 或 not-run 记录不能满足 stage gate。
4. 生成 task-local brief 和 workspace-root context target；brief requirements/constraints 必须与 Stage Contract 精确一致，所有当前 validation evidence 同时进入 `claim_refs` 与 context manifest。
5. 使用 Reviewer 公共 `review_validate.py` 校验 profile=`code-review`、scope=`stage-delta`、stage/attempt、target/context freshness、coverage、gaps、lineage 和 supersedes。
6. `review_recorded` 的 `attempt` 必须与当前 attempt 一致；`evidence_refs` 必须包含 receipt 的 task-relative `report_ref`。
7. event writer 会再次调用 Reviewer 公共 CLI，并要求 payload 与校验结果精确一致；它还会核对 canonical paths、managed brief/context、target mode 与当前 `HEAD`。`stage_completed` 前再次验证 receipt，并要求已通过 VAL 的 target/attempt 与 receipt 一致。

ledger 只保存以下 closed compact payload，不保存完整 findings，也不接受旧布尔门禁：

```json
{
  "result": "passed",
  "review_id": "REV-CODE-STG-02-A1",
  "profile": "code-review",
  "scope": {"kind": "stage-delta", "stage_id": "STG-02", "attempt": 1},
  "target_digest": "<sha256>",
  "context_digest": "<sha256>",
  "verdict": "passed",
  "report_ref": "artifacts/reviews/stg-02-attempt-1.json",
  "open_counts": {"blocking": 0, "major": 0, "minor": 0, "advisory": 0, "total": 0},
  "gap_counts": {"blocking": 0, "major": 0, "minor": 0, "total": 0},
  "coverage_summary": {"target_paths": 12, "requirements": 9, "risks": 6, "context_expansions": 1},
  "lineage_summary": {"predecessor_review_id": null, "accounted_finding_count": 0},
  "strength_count": 2,
  "summary": "<validated summary>"
}
```

finding 修复会改变 target，必须生成新 receipt；声明 supersedes 时，前序 receipt 必须在同一 review root 中唯一存在。`changes_required`/`blocked` 可作为失败证据记录，但不会建立 passed gate。改变批准边界时进入 amendment。

validation ledger payload 固定为：

```json
{
  "validation_id": "VAL-06",
  "result": "passed",
  "command": "python -m unittest ...",
  "claim_source": "observed",
  "stage_attempt": 1,
  "target_digest": "<same-stage-target-sha256>",
  "exit_code": 0,
  "summary": "72 tests passed",
  "claim_boundary": "只证明当前 target 上该命令覆盖的行为"
}
```

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
4. `activate-amendment` 在轮换 runtime 前再次运行 current Planner approval checker，并验证新 attestation。
5. 只有上一 ledger 已完成，且 stage 本体及其 REQ/AC/NFR/VAL 定义与归档 contract 语义相同，才允许作为 completed stage 继承。
6. 轮换当前 ledger/run-state，新 ledger 首条 `amendment_approved` 记录前一 archive/hash 和获批继承 stages。
7. 未批准时不得继续代码、Git、外部写入或长期进程操作。

禁止直接改写 approved plan 或 contract 后重新哈希来冒充批准。

## Git 与提交

- 同一 working tree 的 Git 命令串行；禁止并发 agent/shell 执行同仓库 Git。
- 不自动 stash、reset、rebase、切分支、覆盖未知改动或删除 lock。
- 遇到 index.lock 时解析精确路径，确认文件稳定且无相关/未知 Git 进程，只删除该精确文件并立刻重跑 status。
- stage 的 `commit_expectation` 只表示计划时机；attestation 中 commit authorization 为 false 时不得提交。
- `stage` expectation 在对应 stage 完成后提交并记录该 `stage_id`；`final` expectation 在所有 stage 完成后、`completed` 事件前记录。
- 提交前完成 required validation、当前 target 的 Reviewer receipt、`git diff --check` 和范围检查。
- 使用单个 `git commit -F <message-file>`；标题后一个空行，bullet 间无空行。
- 成功提交后写 `commit_recorded`，payload 必须包含 `commit` hash 和 `repository`，可按需补充 message/scope；不要伪造未发生的提交。

## 长期进程

存在 process-manager skill 时，dev server、Web/API 服务、worker、watcher 和模型服务必须由它管理。先用统一 `pm_manager.py status` 检查 manager，仅在 `manager_offline` 时执行 `pm_manager.py start`；不得判断 OS/backend 或选择平台入口。

按 manager authenticated identity -> service config validation -> start/processKey -> ready/status -> bounded logs -> stop/restart 的顺序取证。停止或替换 run 时必须看到 `cleanupVerified: true` 与 `stopResult.ownerEmpty: true`；manager 由本任务创建且不再需要时，还要通过统一 stop/shutdown 证明 bootstrap cleanup，计划明确保留时则记录保留原因。

普通流程不先运行 `pm_doctor.py`。只有统一操作失败且 capability/selection reason 不清楚时才按需诊断；manager 无法建立安全 owner 且阶段必需长期进程时进入 blocked，不得退回手写后台启动。

finite test、build、lint、format、migration 和一次性脚本直接运行。禁止 `Start-Process`、shell background、`nohup` 或自制 launcher 绕过 process-manager。manager 不可用且阶段必需长期进程时进入 blocked。

## 最终门禁

完成最后一个 stage 后：

1. 确认每个非 carried stage 都有绑定当前 target/attempt 的 observed required VAL、当前 target/context 的 `stage-delta` receipt 和 `stage_completed` evidence；carried stage 以已校验 amendment archive 为证据。
2. 核对 attestation、run-state、ledger、授权、Git/changelog 和 artifacts。
3. 运行 planner/executor unit、conformance/eval、skill validator 和 `git diff --check`。
4. 生成覆盖全部 GOAL/REQ/AC/NFR、STG/VAL、standards 和有效验证证据的 final brief/context，对 execution baseline 到当前整体目标运行 `code-review/final-integration`；修复 blocking/major 后重跑受影响验证并生成新 receipt。
5. 未授权时不得提交。已授权且 contract 预期 final commit 时，先用当前 final receipt 决定是否可提交，实际提交后追加无 `stage_id` 的 `commit_recorded`；该事件会使 pre-commit final receipt 失效。
6. final commit 后必须以 execution baseline、所有 stage 的 canonical allowed paths 和当前 `HEAD` 生成真实 `commit-range`，重新记录 `final-integration` receipt；不得把 pre-commit receipt、旧 HEAD 的 commit-range 或任一 stage receipt 复用为 post-commit final evidence。
7. 在所有已授权 commit expectation 与当前 final receipt 都闭环后追加 `completed`；未提交任务此时删除指向它的 active pointer。
8. 确认 replay lifecycle 为 completed、active pointer 已关闭，再用显式 task-dir 运行 final checker；checker 会通过 Reviewer 公共 CLI 重新验证 final target freshness。只有 final 通过后才能最终回复。

最终回复说明核心改动、实际验证、未覆盖范围、review 结论、branch/commit、关键证据和残余风险。

## 错误恢复

失败动作记录 command/tool、attempt、原因、影响和下一策略。相同原因不得静默重复第三次；第三次前必须改变策略、缩小范围、补上下文、使用替代验证或进入 blocked。

常见诊断：

- `TASK_POINTER_*`：active pointer 缺失、含运行字段或路径越界。
- `TASK_CONTRACT_*`：当前 task contract 缺失或结构/语义无效。
- `ATTESTATION_*`：批准缺失、授权不足或 immutable hash mismatch。
- `LEDGER_*`：事件 JSON、seq、ID、引用或转移无效。
- `RUN_STATE_*`：snapshot 无效、drift 不可修复或 stage/validation/review 未闭环。
- `REVIEW_*`：Reviewer 拒绝 schema、profile、scope、provenance、supersedes 或 target freshness。

详细排查见 `troubleshooting.md`。历史任务缺少当前必需文件时按结构错误处理，不迁移、不 fallback。

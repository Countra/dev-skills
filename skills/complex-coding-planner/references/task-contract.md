# Task Contract

本文件是 `complex-coding-planner`、`complex-coding-reviewer` 与 `complex-coding-executor` 的唯一任务契约定义。三方可以拥有各自职责内的校验代码，但字段、状态、事件和错误语义必须以本文件及联合 fixtures 为准。

## 目录

1. [设计目标](#设计目标)
2. [任务制品](#任务制品)
3. [所有权](#所有权)
4. [Plan Contract](#plan-contract)
5. [Dependency Selection Contract](#dependency-selection-contract)
6. [Stage Contract](#stage-contract)
7. [规划画像](#规划画像)
8. [批准与证明](#批准与证明)
9. [运行状态](#运行状态)
10. [Ledger 事件](#ledger-事件)
11. [校验模式](#校验模式)
12. [修订](#修订)

## 设计目标

- 只定义一套当前契约，不设置契约版本字段或多协议兼容模式。
- `execution-plan.md` 面向人类审批，`plan-contract.json` 面向确定性校验。
- 批准意图与执行进度分离，任何可变运行数据都不进入批准哈希集合。
- planner 是批准意图的 producer，Reviewer coordinator 是 review artifacts 的唯一 writer，delegated reviewer 是正式语义
  verdict 的唯一 producer，executor 是运行状态和执行证据的唯一 writer。
- 历史任务不迁移。缺少当前必需文件或字段时返回结构错误，不返回版本错误。

## 任务制品

```text
task-dir/
  execution-plan.md
  plan-contract.json
  attestation.json
  run-state.json
  ledger.jsonl
  pending-decisions.md        # 仅有阻塞决策时创建
  artifacts/
    reviews/
      plan-review-brief.json
      plan-review-attempt-N.json
      targets/
      contexts/
      dispatches/
      results/
```

必需关系：

- planner approval checker 需要 `execution-plan.md`、`plan-contract.json`、approval-included review brief 与当前 plan-review receipt。
- executor 首次启动需要批准后的 `attestation.json`。
- executor 启动后维护 `run-state.json` 与 `ledger.jsonl`。
- `active-task.json` 只定位任务，不复制 lifecycle、stage、remaining 或 next action。
- active pointer 是封闭对象，只含 `task_id`、workspace 相对 `task_dir`、task-dir 相对 `run_state_path` 和 RFC3339 `updated_at`；路径不得包含 `..`。
- pointer 激活必须先分类：missing 创建、same-task 复用、different-terminal 原子替换、different-nonterminal/different-unknown fail closed。显式切换必须携带与当前 pointer 一致的 expected task ID，不得静默覆盖。
- 任务 completed/aborted 且无需恢复时删除 `active-task.json`；“无活动任务”用文件不存在表达，不写 `null` 根对象。

## 所有权

| 制品 | 创建者 | 批准后 writer | 权威内容 |
| --- | --- | --- | --- |
| `execution-plan.md` | planner | none | 目标、证据、决策、阶段理由和验收解释 |
| `plan-contract.json` | planner | none | ID、Stage DAG、验证、artifact 和授权策略 |
| approved non-review artifacts | planner | none | research、standards、architecture、dependency、traceability |
| plan-review brief | planner | none | profile、scope、requirements、constraints、claims 和 risk focus |
| plan-review dispatch/result | reviewer coordinator / delegated reviewer | none | policy、Agent lifecycle、冻结输入与原始语义结果 |
| plan-review receipt | reviewer coordinator assembler | none | supporting artifact 绑定、coverage、strengths、findings、gaps、lineage 和 verdict |
| `attestation.json` | approval gate | amendment gate | 批准摘要、授权和不可变哈希集合 |
| `run-state.json` | executor | executor | 当前 lifecycle、stage、stop、next 和 event 游标 |
| `ledger.jsonl` | executor | append-only executor | 事件、attempt、验证、review、Git 和证据引用 |
| `active-task.json` | lifecycle operation | pointer operation | task ID、目录和 run-state 路径 |

批准后如需修改前四类制品，必须进入 amendment，不允许以“状态同步”为由直接改写。

## Plan Contract

`plan-contract.json` 根对象只允许以下字段：

- `task_id`：稳定任务 ID。
- `plan_revision`：从 1 开始的批准意图修订号。
- `lifecycle_route`：`managed`。
- `plan_profile`：`lite`、`standard` 或 `full`。
- `goal`：包含 `id` 与可验证的 `summary`。
- `requirements`：`REQ-*` 对象数组。
- `acceptance_criteria`：`AC-*` 对象数组，并引用 requirements。
- `nonfunctional_requirements`：`NFR-*` 对象数组。
- `artifacts`：批准 artifact 索引。
- `stages`：Stage Contract 数组和 DAG。
- `validations`：`VAL-*` 定义及覆盖关系。
- `research`：研究模式、未解决事实和证据索引。
- `dependency_selection`：条件化依赖选型摘要、`DEP-*`、身份、版本和 evidence 引用。
- `approval_policy`：实施、提交、外部写入和提权授权要求。
- `reapproval_triggers`：实质变更触发条件。
- `stop_conditions`：executor 可以停止的显式条件。

根对象和受控嵌套对象拒绝未知字段。错误诊断必须给出 JSON path 和修复方向。

每个 artifact 包含 `id`、`kind`、task-dir 内相对 `path`、`required` 和 `approval_included`。kind 为 `research`、`standards`、`architecture`、`dependency`、`validation`、`review` 或 `other`。approval 时 required 或 approval-included 文件必须存在且非空；required planning artifact 必须进入 attestation 哈希集合。

每个 managed plan 必须有且只有一个当前 `review` artifact，路径为 `artifacts/reviews/plan-review-attempt-N.json`，并同时设置 `required=true`、`approval_included=true`。历史 attempts 保留在同目录但不进入当前 artifact index；attempt 大于 1 时必须保留紧邻前序文件并用 `supersedes_review_id` 连接。review artifact 不参与它所证明的 plan-bundle digest，receipt 自身单独进入批准哈希集合，避免自引用。

receipt 引用的 target/context、preparation/final dispatch 与 raw semantic result 位于同一 review root 的 supporting 子目录。
它们不作为独立 plan artifacts 索引，而由 receipt 的 ref/raw SHA-256 间接绑定；dispatch 不反向引用 receipt，避免循环哈希。

review brief 使用 `kind=other`、`required=true`、`approval_included=true`，并进入 plan target/context；它声明 GOAL/REQ/AC/NFR、STG/VAL 约束、claim refs 与 risk focus，但不携带 verdict。plan-review context 只能引用 `execution-plan.md`、`plan-contract.json` 和 approval-included non-review artifacts。

planner approval 通过 `complex-coding-reviewer/scripts/review_validate.py` 校验当前 receipt，固定期望
`profile=plan-review`、`scope=managed-plan`，并按 plan profile 派生 expected dispatch policy：full=`strict`，
lite/standard=`conditional`。只有 supporting artifact digest、policy/Agent lifecycle、canonical schema、provenance、coverage、
strengths、findings、gaps、lineage、supersedes 与双 freshness 全部有效且 verdict 为 `passed` 时才通过；Markdown 文本不承载
正式 verdict。

每个 validation 包含 `id`、`kind`、`required`、`covers`、`command` 和 `evidence_path`。`command` 可以是确定性 CLI，也可以是具名工具流程，但不能伪造尚未执行的结果。

Stage 的 `validation_ids` 可以包含 required 与 optional validation；只有 `required = true` 的项目阻断 stage completion。optional 项如实际执行仍应记录真实结果，不得把未执行项伪造成 passed。

ID 必须满足：

- goal 使用 `GOAL-01`。
- requirement、acceptance、nonfunctional、dependency、stage、validation 和 artifact 分别使用 `REQ-*`、`AC-*`、`NFR-*`、`DEP-*`、`STG-*`、`VAL-*`、`ART-*`。
- 同类 ID 唯一且引用存在。
- 每个 must requirement 至少被一个 AC 和 stage 覆盖。
- 每个 AC/NFR 至少被一个 required validation 覆盖。
- 每个 AC/NFR 必须归属至少一个 stage，每个 required validation 必须由至少一个 stage 执行。

## Dependency Selection Contract

新模板始终显式输出 `dependency_selection`。真正没有 dependency trigger 的任务使用：

```json
{
  "mode": "none",
  "necessity_result": "not-triggered",
  "decision_ids": [],
  "evidence_artifact_ids": [],
  "decisions": []
}
```

mode 为 `none`、`retain`、`change` 或 `mixed`；decision action 为 `retain`、`add`、`upgrade` 或 `replace`。`none` 必须没有 decision 和 dependency artifact；stage scope 或 artifact 已触发依赖变更时不能声明 none。字段缺失仅在 checker 能从 closed contract scope 证明没有 dependency trigger 时按 none 处理，不维护旧版 schema 分支。

每个 `DEP-*` decision 是 closed object，包含：

- `action`、`category`、`criticality`、`requirement_ids`。
- `selection_class`：`existing-stack`、`standard-or-official`、`ecosystem-mainstream` 或 `specialized-exception`。
- `ecosystem`、canonical `package`、`source_repository` 和 `selected_version`。
- `version_policy`、workspace 相对 `manifest_paths`、`validation_ids`。
- `freshness_max_age_days`：critical-runtime/runtime/dev-build 分别固定为 30/60/90。
- `evidence_artifact_id`：引用 required 且 approval-included 的 `dependency` JSON artifact。

mode 非 none 时，完整 receipt 位于 `artifacts/dependencies/*.json`。根对象只含 `observed_at` 和 `decisions`；每个 decision receipt 包含 necessity、1-5 个同类 candidates、排除依据、decision reason 和可空 exception。每个 candidate 包含 canonical identity、selection class、disposition、七项 hard gates、九项 trust signals、fit summary 和 risks。

hard gates 固定为 authenticity、compatibility、stable_support、lifecycle、security、license 和 reproducibility，结果为 `pass`、`fail`、`exception` 或 `unavailable`。selected candidate 默认必须全部 pass；只有 specialized exception 的 stable_support/lifecycle 可在完整风险与退出策略下使用 exception。

trust signals 固定为 stable_version、adoption_scale、update_recency、maintenance_activity、adoption_trend、api_and_project_fit、ecosystem_and_docs、transitive_and_provenance 和 operational_cost。每项记录 result、value、source_type、URL、`as_of`、window 和 caveat；结果为 `pass`、`concern`、`fail` 或 `insufficient-data`。adoption trend 为 insufficient-data 时必须提供至少两个独立 proxy URL。

`specialized-exception` 必须引用同一 decision 的 ecosystem-mainstream baseline，并记录 unmet REQ、baseline failure、accepted risks、mitigations、rollback 和 `user_acceptance_required=true`。plan、contract 与 artifact 的 DEP 集合、selected identity/version/class、artifact 和 validation 引用必须一致。

## Stage Contract

每个 stage 必须包含：

- `id`、`title`、`depends_on`。
- `requirement_ids`、`acceptance_ids`、`nonfunctional_ids`、`validation_ids`。
- `allowed_changes`、`forbidden_changes`。
- `entry_conditions`、`exit_conditions`。
- `risk`：`low`、`medium` 或 `high`。
- `commit_expectation`：`none`、`stage` 或 `final`。

Stage DAG 必须无环，依赖只能指向已定义 stage。executor 只能启动依赖均完成的 stage，不能从 Markdown 标题推断依赖或验证。

plan 中每个 Stage Contract 必须同步对应依赖、REQ/AC/NFR、VAL、allowed/forbidden changes 和 title；checker 不接受只在全局章节出现、但未挂到对应 stage 的引用。

## 规划画像

| Profile | 适用条件 | 必需内容 |
| --- | --- | --- |
| `lite` | 局部、低风险、可逆、短时 managed 任务 | 内联证据、最小 change map、1-3 stages、focused plan-review |
| `standard` | 跨文件或中等风险任务 | research/standards 摘要、影响面、traceability、2-5 stages、plan-review |
| `full` | 高风险、跨模块、长时、外部写入或恢复敏感任务 | 独立 artifacts、完整追踪、3-7 stages、恢复与切换证据、strict delegated plan-review |

目标未稳定或存在高影响未知时先进入 `discovery-first`，只产出发现和阻塞决策；不得伪造 ready-for-approval contract。

## 批准与证明

`attestation.json` 由 approval gate 生成，包含：

- `task_id`、`plan_revision`、`approved_at`、`approved_by`、`approval_summary`。
- `authorizations`：implementation、commit、external_write、elevated_tool。
- `immutable_files`：相对 task-dir 的路径、SHA-256 和字节数。

哈希集合必须包含 plan、contract 和 `artifacts[].approval_included = true` 的文件；不得包含 attestation 自身、run-state、ledger 或执行证据。

同一 `plan_revision` 的 attestation 不可覆盖。批准摘要或 implementation/commit/external_write/elevated_tool 授权发生变化时，必须归档当前 revision 并进入 amendment；新 revision 写入 attestation 前必须存在紧邻上一 revision 的有效归档。

## 运行状态

`run-state.json` 由 ledger reducer 唯一推导，包含 task/revision、lifecycle、current/completed/remaining stages、stop condition、next action、reapproval flag、last event seq、state revision 和更新时间。

允许 lifecycle：`approved`、`in_progress`、`blocked`、`completed`、`aborted`。

- snapshot 落后 ledger 时可通过 replay 修复。
- snapshot 缺失时可从完整合法 ledger 重建。
- snapshot 领先 ledger、事件断号、未知 stage 或非法转移必须 fail closed。
- `completed` 和 `aborted` 是封闭终态，之后不得追加 note、heartbeat 或其它事件。
- 写 snapshot 使用同目录临时文件和 atomic replace。

## Ledger 事件

每行是一个 JSON object，包含 `seq`、`event_id`、`occurred_at`、`task_id`、`plan_revision`、`stage_id`、`type`、`attempt`、`payload` 和 `evidence_refs`。

最小事件集：

- task：`execution_started`、`blocked`、`resumed`、`completed`、`aborted`。
- stage：`stage_started`、`attempt_failed`、`validation_recorded`、`review_recorded`、`stage_completed`。
- plan：`research_drift`、`amendment_requested`、`amendment_approved`。
- operation：`commit_recorded`、`note`、`heartbeat`。

关键 payload：`validation_recorded` 是 closed object，包含 `validation_id`、`result`、`command`、`claim_source`、
`stage_attempt`、`target_digest`、`exit_code`、`summary`、`claim_boundary`；只有 `observed`、exit code 0 且绑定当前
attempt/target 的记录可以 passed，并必须引用 task-local evidence 文件。`review_recorded` 只保存由 Reviewer 公共 validator
精确派生的 compact receipt：`result`、`review_id`、`profile`、`scope`、`target_digest`、`context_digest`、
`reviewer_mode`、`independence_claim`、`dispatch_id`、`verdict`、`report_ref`、`open_counts`、`gap_counts`、
`coverage_summary`、`lineage_summary`、`strength_count`、`summary`。stage review 使用绑定当前 `stage_id`/`attempt` 的
`stage-delta`，task final review 使用不绑定 stage 的 `final-integration`，完整 canonical receipt 位于
`artifacts/reviews/**` 并必须出现在 `evidence_refs`。`attempt_failed` 需要 `reason`、`impact`、`next_strategy`；
`research_drift` 需要 `reason`、`source`、`impact`；`resumed` 需要 `resolution`；`aborted` 需要 `reason`。

`seq` 从 1 连续递增，`event_id` 唯一，stage attempt 单调递增。validation result 为 `passed`、`failed` 或 `not-run`，claim source 为 `observed`、`reported` 或 `not-run`；reported/not-run 不建立 passed gate。失败或未运行会撤销该 attempt 已记录的相关通过证据。stage 完成时所有已通过 validation 的 target/attempt 必须与 stage receipt 一致。大日志保存为 artifact，ledger 只保存摘要和 task-dir 内真实文件的相对引用。未授权的 `commit_recorded` 必须在 append 前拒绝；已授权事件必须在 `completed` 前记录 repository 和 7-64 位十六进制 commit hash。`stage` expectation 逐 stage 记录对应 `stage_id`，`final` expectation 在所有 stage 完成后记录无 stage_id 的事件。

ledger 以 plan revision 为作用域。amendment 前把当前 immutable set、attestation、ledger 和 run-state 归档到 `artifacts/amendments/revision-N/`；新 revision 使用新的当前 ledger，其首条 `amendment_approved` 事件记录前一 archive、ledger SHA-256 和经重新批准可继承的 completed stages。归档 ledger 永不回写。

## 校验模式

- planner `draft`：允许未完成研究和开放决策，但报告所有结构问题。
- planner `approval`：要求引用闭环、无 blocker、profile artifacts 完整、授权策略和 amendment triggers 明确，并要求当前 plan-bundle 的 passed plan-review receipt。
- executor `preflight`：验证 pointer、contract、attestation、批准授权和 ledger/snapshot 一致性。
- executor `status`：只读输出 snapshot 与 replay 摘要。
- executor `transition`：验证阶段完成证据和下一 stage 可进入。
- executor `reconcile`：只修复可由合法 ledger 唯一推导的 snapshot drift。
- executor `final`：要求所有 stage/validation/review/authorization 闭环且 active pointer 已收口。

稳定错误类别包括 `TASK_POINTER_*`、`TASK_CONTRACT_*`、`TASK_ARTIFACT_*`、`ATTESTATION_*`、`RUN_STATE_*` 和 `LEDGER_*`。不存在版本错误或 fallback。

## 修订

实质变更先写 amendment request 并停止执行。用户批准后：

1. 将上一 revision 的 plan、contract、attestation、ledger 和 run-state 归档到 `artifacts/amendments/revision-N/`。
2. 生成递增的 `plan_revision` 与新批准集合。
3. 重跑 planner approval checker 和 traceability。
4. 生成新 attestation，轮换当前 ledger/run-state，并以 `amendment_approved` 连接前一 ledger hash。
5. carried completed stage 必须已在上一 revision ledger 中完成，且 stage 本体及其 REQ/AC/NFR/VAL 定义与归档 contract 语义相同；否则必须重跑。
6. executor 仅在 `reapproval_required = false` 后继续。

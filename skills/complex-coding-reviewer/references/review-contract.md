# Review Contract

JSON receipt 是唯一 canonical verdict，但它必须绑定 immutable dispatch 和原始 semantic result。所有 object 都是 closed；
未知字段、缺字段、错误枚举、supporting artifact 篡改或派生值不一致均 fail closed。详细结构以
`scripts/complex_coding_reviewer/contract.py`、`dispatch*.py` 与 `semantic_result.py` 为权威实现。

## 根对象

固定字段：

```json
{
  "review_id": "REV-...",
  "profile": "plan-review | code-review",
  "scope": {},
  "target": {},
  "context": {},
  "reviewer": {},
  "standards": [],
  "coverage": {},
  "lenses": [],
  "strengths": [],
  "findings": [],
  "verification_gaps": [],
  "verdict": "passed | changes_required | blocked",
  "open_counts": {},
  "summary": "...",
  "limitations": [],
  "supersedes_review_id": null,
  "reviewed_at": "RFC3339"
}
```

`review_id` 使用 `REV-` 加大写稳定标识。模板值会被拒绝。`reviewed_at` 必须有时区。

## Supporting Artifacts

每个 receipt 必须位于显式 review root，并引用：

- `targets/REV-*.json`：冻结 primary target。
- `contexts/REV-*.json`：冻结 review context。
- `dispatches/REV-*-prepare.json`：policy、能力、allowlist prompt digest、Reviewer Skill digest、输入
  ref/digest、attempt、`timeout_class` 与 timeout。
- `dispatches/REV-*.json`：final dispatch，复制 preparation（含 Reviewer Skill digest）并封存生命周期与
  reviewer provenance。
- `results/REV-*.json`：delegated reviewer 原样返回的 closed semantic result。

final dispatch 不反向引用 receipt。receipt 的 reviewer 字段包含 `dispatch_id`、`dispatch_ref`、`dispatch_digest`、
`semantic_result_ref` 和 `semantic_result_digest`；digest 是 supporting artifact 原始文件字节的小写 SHA-256。Assembler
必须原样复制 semantic result 的所有语义字段，不能由 coordinator 重写 findings 或 verdict。

semantic result 根对象固定包含 `kind=review-semantic-result`、review/profile/scope、`target_digest`、`context_digest`，以及
standards、coverage、lenses、strengths、findings、verification gaps、verdict、counts、summary、limitations、lineage 和时间。
它不包含 reviewer provenance；provenance 只能从 final dispatch 生命周期派生。

## Scope

只允许：

- plan：`{"kind":"managed-plan","task_id":"...","plan_revision":1}`。
- stage code：`{"kind":"stage-delta","stage_id":"STG-01","attempt":1}`。
- final code：`{"kind":"final-integration"}`。
- standalone code：`{"kind":"standalone"}`。

profile、scope、target identity 必须一致；stage target 的 stage ID/attempt 必须与 scope 相同。

## Brief 与 Context

每个正式 receipt 必须绑定一个 `review-context`，其 identity 固定包含 `root=workspace|task-dir` 与 `label`，manifest 使用与
target 相同的 path/role/state/SHA-256/size 规则，但 role 只允许 `brief`、`requirement`、`standard`、`validation`、
`adjacent-code`、`config`、`test`、`other`。必须且只能包含一个 present brief。

brief 固定字段为 `profile`、`scope`、`summary`、`requirement_refs`、`constraint_refs`、`claim_refs`、
`requested_risk_focus`、`created_at`。profile/scope 必须与 receipt 相等；claim path 必须绑定 context 中的 present entry，deleted entry
不能证明当前 claim。context 限制 128 个文件、
单文件 2 MiB、总计 8 MiB，并拒绝越界、符号链接逃逸与 `.env`/private key/credential 等敏感路径。target 或 context 任一 digest
变化都会使 receipt stale。

## Target

固定字段为 `kind`、`identity`、`digest_algorithm`、`digest`、`manifest`。digest 是去除 `digest` 字段后对 canonical
UTF-8 JSON 计算的小写 SHA-256。manifest 按 `/` 相对路径排序且无重复：

```json
{
  "path": "src/example.py",
  "role": "source",
  "state": "present",
  "sha256": "...",
  "size": 42
}
```

删除项的 `state` 为 `deleted`，hash/size 为 null。支持 `plan-bundle`、`git-diff`、`commit-range` 和
`file-manifest`。绝对路径、`..`、符号链接逃逸、不可读目标或当前重建 digest 不同均拒绝。

package 是非 canonical 阅读视图，但其中每个 present entry 仍必须来自对应 manifest 的 size/SHA-256 字节。绑定 dispatch
时，validator 必须校验 closed schema、双重 512 KiB 预算并从冻结 target/context 确定性重建全部内容；`commit-range`
entry 从记录的 Git `head` object 读取，不从可能已变化的工作树读取。package 不参与 verdict 或 freshness 判定。

## Reviewer Provenance

固定字段：`mode`、`identity`、`independence_claim`、`capability_limits`、`dispatch_id`、`dispatch_ref`、
`dispatch_digest`、`semantic_result_ref`、`semantic_result_digest`。

- `external-agent`：identity 为 `codex-subagent:<opaque-id>`。只有 lifecycle=`completed`、`fork_context=false`、未注入父
  判断、未允许递归、没有 context expansion 且 close=`closed` 时 independence 才为 true。
- `same-context`：只用于合法 conditional/disabled 回退，identity 为 coordinator 回退标识，independence 固定 false。
- identity 不得包含 token、邮箱口令或其它秘密；opaque Agent ID 不做推导或重格式化。

`independence_claim=true` 只表示上下文隔离，不表示不同模型、独立权限边界、已运行测试或人类审计。capability limits 必须
披露同模型相关性、继承权限/沙箱、未运行测试、非人类审计，以及静态 validator 不能证明宿主调用。

Dispatch policy 只允许 `strict|conditional|disabled`。strict 能力缺失为 blocked；conditional 工具可用时必须 delegate，
只有确认 unavailable 或 disabled 才能 fallback。每个 dispatch 最多两个 attempt；attempt 2 必须绑定 retryable failed
attempt 1、完成必要关闭、在前序已创建 Agent 时使用不同 opaque Agent ID，并保持 target 不变；context 只有在前序明确请求
expansion 时才可做保留原条目的超集扩展。`timeout_class=standard` 单次等待最多 900 秒，
`timeout_class=high-risk` 默认 1800 秒，并允许调用方按冻结目标规模显式延长，但不得超过当前任务剩余预算；strict
固定派生 high-risk，其余策略在冻结 brief 的 `requested_risk_focus` 非空时派生 high-risk，否则派生 standard。该等级只控制
等待预算，不改变 dispatch policy 或 verdict；
schema repair 只允许一次，并且 preparation 必须预先冻结 `send_input` 可用性。attempt 2 必须晚于前序 final dispatch，且
delegated failure 不能因后续工具缺失降级成 same-context fallback。`prepared_at`、Agent started/completed/closed、
`finalized_at` 与 semantic `reviewed_at` 必须形成单调时间线。

Preparation 必须冻结实际 Reviewer Skill 的 SHA-256，并在 final dispatch 中原样复制。非 freshness 校验只用冻结摘要
确定性重建 prompt；freshness 校验还会比较当前 Skill，漂移时返回 `REVIEW_DISPATCH_STALE`。因此 stale attempt 可以在
不信任新 Skill 内容的前提下先验证旧 preparation，再封存 Agent 关闭证据。

所有建立正式 gate 的 `review_assemble.py`、`review_validate.py`、`review_render.py` 与
`review_dispatch.py validate --require-receipt-ready` 调用都必须显式传入 expected dispatch policy；不得依赖 conditional
默认值。

## Standards 与 Lenses

每条 standard 固定 `id`、`title`、`source`、`applicability`。每个 lens 固定：

```json
{
  "id": "PLAN-INTENT",
  "status": "reviewed | not-applicable | blocked",
  "evidence_refs": ["execution-plan.md#问题定义"],
  "summary": "具体判断"
}
```

profile 要求的 lens 必须按 reference 顺序完整出现。`reviewed`/`blocked` 需要绑定 primary/context manifest 的 evidence；N/A 在
summary 说明理由。

## Finding

固定字段：`id`、`category`、`origin`、`severity`、`status`、`title`、`claim`、`impact`、`recommendation`、
`evidence`、`confidence`、`disposition_reason`。

- ID：`FIND-NNN`。
- severity：`blocking`、`major`、`minor`、`advisory`。
- status：`open`、`resolved`、`accepted`、`deferred`、`invalidated`。
- confidence：`high`、`medium`、`low`。
- category：`requirement`、`correctness`、`security`、`reliability`、`architecture`、`performance`、`test`、`delivery`、`scope`。
- origin 固定为 `review_id`/`finding_id`；新 finding 两者均为 null，复审继承项必须指向直属前序。
- open finding 的 disposition 必须为 null；其它状态必须说明 disposition。

每条 evidence 固定 `path`、`line`、`symbol`、`artifact_ref`、`standard_ref`、`detail`、`claim_source`，不用的 locator 写 null，
但至少有一种定位。line 只能与 path 同时出现；path 必须位于 primary/context manifest。claim source 只允许 `read`、
`observed`、`reported`、`inferred`、`not-verified`。low confidence 不能定为 blocking/major；resolved/invalidated 必须有当前
`read` 或 `observed` 证据。

## Coverage、Strength 与 Gap

`coverage` 固定包含：

- `target_paths`：与 primary manifest 路径精确相等，状态为 `reviewed|excluded|blocked`；blocked 关联 major/blocking gap。
- `requirement_checks`：与 brief.requirement_refs 精确相等，状态为 `satisfied|violated|not-verifiable|not-applicable`；
  violated 关联 unresolved finding，not-verifiable 关联 gap。
- `risk_checks`：按六类固定顺序完整出现，状态为 `triggered-reviewed|not-triggered|blocked`；brief 点名的风险不能写 not-triggered。
- `context_expansions`：使用 `CTX-NNN`，路径必须进入 context，结果为 `supported|finding|unresolved` 并关联对应 finding/gap。

`strengths` 可为空；每项固定 `id=STR-NNN`、`claim`、`evidence`，禁止凑数量。`verification_gaps` 每项固定 `id=GAP-NNN`、
`requirement_ref`、`category`、`claim`、`needed_evidence`、`owner`、`severity`、`evidence_refs`。owner 只允许 caller/planner/
executor/specialist/user；blocking/major gap 派生 blocked，minor gap 可 passed 但必须进入 limitations。

## 派生门禁

`open_counts` 固定包含四个 severity 和 `total`，必须从 `status=open` 的 findings 精确派生。verdict 规则：

- 任一 lens blocked：`blocked`。
- 任一 blocking/major verification gap：`blocked`。
- 任一 blocking/major 为 open、accepted 或 deferred：`changes_required`。
- 其它情况：`passed`。

因此 blocking/major 不能靠风险接受或延期绕过正式门禁。需要这样处理时，应先修改计划/实现的批准边界，再以新目标复审。

## Supersedes

新 attempt 可指向同 profile、同 scope kind 的直属前序。不得跨 profile、形成环或覆盖旧文件。Validator 需要同时读取
直属前序；每个新 receipt 自身必须完整。前序 open/accepted/deferred finding 必须在当前 receipt 中恰有一个 origin 映射；
仍未关闭时不得降低 severity，resolved/invalidated 必须有当前证据与 disposition。已关闭前序项无需永久携带。

## 稳定错误族

- `REVIEW_TARGET_*`：路径、Git、manifest、digest、context 或 stale。
- `REVIEW_CONTEXT_*`：brief、独立 context、预算、敏感路径、claim binding 或 stale。
- `REVIEW_COVERAGE_*`：目标、需求、风险、扩展、finding/gap 关联或顺序。
- `REVIEW_GAP_*`：不可验证项、owner、severity、limitations 或证据。
- `REVIEW_LINEAGE_*`：前序 finding accounting、origin 或 severity 漂移。
- `REVIEW_PACKAGE_*`：有界阅读包、Git 读取或预算。
- `REVIEW_CONTRACT_*`：closed fields、类型、计数、时间、ID 或 verdict。
- `REVIEW_PROFILE_*`：profile、scope、target 或 lenses 不一致。
- `REVIEW_FINDING_*`：finding 证据、状态、严重度、置信度或 disposition。
- `REVIEW_PROVENANCE_*`：reviewer mode 或独立性声明不真实。
- `REVIEW_DISPATCH_REQUIRED_UNAVAILABLE`：strict 场景缺少必需子 Agent 能力。
- `REVIEW_DISPATCH_POLICY_VIOLATION`：policy、capability、attempt、回退或生命周期不合法。
- `REVIEW_DISPATCH_STALE`：dispatch 冻结的 target/context 已变化。
- `REVIEW_DISPATCH_AGENT_UNCLOSED`：Agent 未成功关闭，candidate 不能建立 passed gate。
- `REVIEW_DISPATCH_PROVENANCE_MISMATCH`：dispatch/result/ref/digest/Agent 生命周期交叉绑定不一致。
- `REVIEW_RESULT_INVALID`：原始 semantic result 不是合法 closed schema 或其派生语义不一致。
- `REVIEW_SUPERSEDES_*`：前序缺失、错配或成环。
- `REVIEW_OUTPUT_*`：输出越界、已存在或不可原子写入。

调用方应保留具体错误码并补充 task/stage 上下文，不应复制 validator 实现或解析 Markdown。

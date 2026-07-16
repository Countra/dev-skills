# Review Contract

JSON receipt 是唯一 canonical 审查产物。所有 object 都是 closed；未知字段、缺字段、错误枚举或派生值不一致均 fail
closed。详细结构以 `scripts/complex_coding_reviewer/contract.py` 为权威实现。

## 根对象

固定字段：

```json
{
  "review_id": "REV-...",
  "profile": "plan-review | code-review",
  "scope": {},
  "target": {},
  "reviewer": {},
  "standards": [],
  "lenses": [],
  "findings": [],
  "verdict": "passed | changes_required | blocked",
  "open_counts": {},
  "summary": "...",
  "limitations": [],
  "supersedes_review_id": null,
  "reviewed_at": "RFC3339"
}
```

`review_id` 使用 `REV-` 加大写稳定标识。模板值会被拒绝。`reviewed_at` 必须有时区。

## Scope

只允许：

- plan：`{"kind":"managed-plan","task_id":"...","plan_revision":1}`。
- stage code：`{"kind":"stage-delta","stage_id":"STG-01","attempt":1}`。
- final code：`{"kind":"final-integration"}`。
- standalone code：`{"kind":"standalone"}`。

profile、scope、target identity 必须一致；stage target 的 stage ID/attempt 必须与 scope 相同。

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

## Reviewer Provenance

固定字段：`mode`、`identity`、`independence_claim`、`capability_limits`。mode 只允许 `same-context`、
`fresh-context`、`external-agent`、`human`。same-context 的 independence 必须为 false；identity 不得包含 token、
邮箱口令或其它秘密。

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

profile 要求的 lens 必须按 reference 顺序完整出现。`reviewed`/`blocked` 需要 evidence；N/A 在 summary 说明理由。

## Finding

固定字段：`id`、`severity`、`status`、`title`、`claim`、`impact`、`recommendation`、`evidence`、
`confidence`、`disposition_reason`。

- ID：`FIND-NNN`。
- severity：`blocking`、`major`、`minor`、`advisory`。
- status：`open`、`resolved`、`accepted`、`deferred`、`invalidated`。
- confidence：`high`、`medium`、`low`；low 不能定为 blocking。
- open finding 的 disposition 必须为 null；其它状态必须说明 disposition。

每条 evidence 固定 `path`、`line`、`symbol`、`artifact_ref`、`standard_ref`、`detail`，不用的 locator 写 null，
但至少有一种定位。line 只能与 path 同时出现。

## 派生门禁

`open_counts` 固定包含四个 severity 和 `total`，必须从 `status=open` 的 findings 精确派生。verdict 规则：

- 任一 lens blocked：`blocked`。
- 任一 blocking/major 为 open、accepted 或 deferred：`changes_required`。
- 其它情况：`passed`。

因此 blocking/major 不能靠风险接受或延期绕过正式门禁。需要这样处理时，应先修改计划/实现的批准边界，再以新目标复审。

## Supersedes

新 attempt 可指向同 profile、同 scope kind 的直属前序。不得跨 profile、形成环或覆盖旧文件。Validator 需要同时读取
直属前序；每个新 receipt 自身必须完整，不能继承旧报告的 lenses 或 findings。

## 稳定错误族

- `REVIEW_TARGET_*`：路径、Git、manifest、digest、context 或 stale。
- `REVIEW_CONTRACT_*`：closed fields、类型、计数、时间、ID 或 verdict。
- `REVIEW_PROFILE_*`：profile、scope、target 或 lenses 不一致。
- `REVIEW_FINDING_*`：finding 证据、状态、严重度、置信度或 disposition。
- `REVIEW_PROVENANCE_*`：reviewer mode 或独立性声明不真实。
- `REVIEW_SUPERSEDES_*`：前序缺失、错配或成环。
- `REVIEW_OUTPUT_*`：输出越界、已存在或不可原子写入。

调用方应保留具体错误码并补充 task/stage 上下文，不应复制 validator 实现或解析 Markdown。

# Dependency Execution Gate

本门禁把 Planner 批准的 `DEP-*` 选择约束带入实施。它只验证不可变批准包和执行期 receipt，不在线抓取、不安装依赖，也不替代生态官方包管理器。

## 入口

preflight 自动执行依赖门禁：

```text
python scripts/harness_exec_check.py --workspace <workspace> --task-dir <task-dir> --mode preflight
```

查看详细依赖摘要：

```text
python scripts/harness_dependency_check.py --workspace <workspace> --task-dir <task-dir> --mode preflight --format json
```

- mode=`none`：返回 `not-applicable`，不读取网络、不要求 receipt。
- mode=`retain|change|mixed`：读取批准 dependency artifact、计算新鲜度并建立 manifest-to-stage 映射。
- 批准证据过期：在线刷新事实，生成 task-local runtime receipt，再用 `--runtime-receipt` 或主 checker 的 `--dependency-receipt` 传入。

runtime receipt 路径必须相对 task-dir，建议放在 `artifacts/execution/<stage>/dependency-runtime.json`。它是执行证据，不得加入 attestation immutable set，也不得包含 token、签名 URL 或其它秘密。

## Closed Runtime Receipt

```json
{
  "observed_at": "2026-07-15",
  "decisions": [
    {
      "decision_id": "DEP-01",
      "package": "approved/package",
      "source_repository": "https://example.com/approved/repository",
      "selection_class": "ecosystem-mainstream",
      "approved_selected_version": "v1.2.3",
      "approved_version_policy": "pin exact v1.2.3",
      "resolved_version": "v1.2.3",
      "manifest_paths": [
        "go.mod",
        "go.sum"
      ],
      "version_policy_result": "passed",
      "manifest_result": "passed",
      "lock_result": "passed",
      "hard_gate_checks": {
        "authenticity": "unchanged",
        "compatibility": "unchanged",
        "stable_support": "unchanged",
        "lifecycle": "unchanged",
        "security": "unchanged",
        "license": "unchanged",
        "reproducibility": "unchanged"
      },
      "evidence_urls": [
        "https://example.com/official/release",
        "https://example.com/registry/package"
      ],
      "summary": "官方版本、支持线、安全事实及原生 manifest 验证均与批准决策一致。"
    }
  ]
}
```

根对象和 decision 都是 closed object。一个门禁调用所需的 decisions 必须一一对应，不能少报、重复或夹带未批准 `DEP-*`。

## 字段语义

| Field | Rule |
| --- | --- |
| `observed_at` | 严格 `YYYY-MM-DD`，不得未来，年龄不得超过对应 30/60/90 天上限 |
| identity fields | `decision_id`、`package`、`source_repository`、`selection_class` 必须精确等于批准 contract |
| approved version fields | `approved_selected_version` 与 `approved_version_policy` 是批准值回显，不能用 runtime 值覆盖 |
| `resolved_version` | 生态原生命令解析出的实际版本，必须非空 |
| `manifest_paths` | 与批准集合相等，workspace 相对且不得含 `..` |
| native results | `version_policy_result`、`manifest_result`、`lock_result` 来自原生验证；stage gate 要求通过或明确 `not-applicable` |
| `hard_gate_checks` | 七项均为 `unchanged`、`changed` 或 `blocked-by-access` |
| `evidence_urls` | 1-20 个 HTTP(S) 官方/一手来源，不得含 credential 或敏感 query key |
| `summary` | 1-2000 字符，说明命令、适用范围、局限和结论 |

preflight stale recheck 可将三个 native result 写为 `not-applicable`，因为它只刷新在线事实；涉及 manifest/lock 的 stage gate 必须提交实际原生验证结果。

## Stage Gate

进入 stage 时先读取映射和批准约束；完成依赖修改、原生验证和 required VAL 后运行：

```text
python scripts/harness_dependency_check.py --workspace <workspace> --task-dir <task-dir> --mode stage --stage-id STG-XX --runtime-receipt artifacts/execution/stg-xx/dependency-runtime.json --format json
```

add/upgrade/replace decision 的每个 manifest path 必须至少被一个 stage 的 `allowed_changes` 覆盖。未覆盖返回 `EXEC_DEPENDENCY_STAGE_UNMAPPED`，不能扩大 scope 临时修改。

原生命令由具体生态和批准计划决定，例如只读/确定性的 module graph、lock consistency、resolved version、license 或 vulnerability 命令。不要让通用 Python checker猜测 SemVer 方言、workspace 解析或 lockfile 语义。

## Drift Decision

| Observation | Required action |
| --- | --- |
| 批准 evidence 仍新鲜且无新事实 | 使用批准 receipt 继续 |
| evidence 过期，刷新后所有事实不变 | 保存 runtime receipt，显式传给 preflight/transition/final |
| 临时无法访问，批准 evidence 仍在窗口内 | 记录限制并按批准证据继续；不得宣称已刷新 |
| 临时无法访问且 evidence 已过期 | `blocked-by-access`，停止 |
| manifest/lock/resolved version 不符合批准策略 | 修正实现并重跑原生验证 |
| package/source/class/version policy/manifest 集合变化 | approval drift，进入 amendment |
| lifecycle、support、security/advisory 或其它 hard gate 变化 | 追加 Research Drift；影响选择或风险接受时 amendment |

runtime receipt 只证明观察结果，不授权换包、换 source、扩大版本范围或升级 latest。任何批准边界变化都必须由 Planner 生成新 revision 并重新获批。

## 稳定诊断

- `EXEC_DEPENDENCY_APPROVAL_INVALID`：批准 contract/artifact 无法消费。
- `EXEC_DEPENDENCY_EVIDENCE_STALE`：批准或 runtime evidence 超龄。
- `EXEC_DEPENDENCY_RECEIPT_MISSING|INVALID|UNEXPECTED`：runtime receipt 缺失、结构错误或 none 模式误传。
- `EXEC_DEPENDENCY_STAGE_UNMAPPED|STAGE_INVALID`：manifest 没有批准 stage 或 stage ID 无效。
- `EXEC_DEPENDENCY_APPROVAL_DRIFT`：identity/version policy/path 与批准值不一致。
- `EXEC_DEPENDENCY_IMPLEMENTATION_DRIFT`：原生 manifest、lock 或版本策略验证失败。
- `EXEC_DEPENDENCY_RESEARCH_DRIFT`：hard-gate 事实变化，需要记录并评估 amendment。
- `EXEC_DEPENDENCY_RECHECK_BLOCKED`：在线或原生验证不可完成，不能默认放行。

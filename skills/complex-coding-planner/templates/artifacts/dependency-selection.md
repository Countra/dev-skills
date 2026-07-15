# Dependency Selection Review

本模板用于人类审阅依赖候选。正式机器证据写入同任务的 `artifacts/dependencies/dependency-selection.json`；两者出现冲突时以 contract 与 JSON artifact 的闭合校验为准。

## Scope

- Selection mode：`none / retain / change / mixed`
- Trigger surfaces：
- Observation date：`YYYY-MM-DD`
- Research mode：`online-required / blocked-by-access / local-only`
- Dependency result：`passed / not-applicable / blocked`

## Necessity

| DEP ID | Result | Requirement IDs | Existing option | Standard / official option | Why a dependency is or is not required |
| --- | --- | --- | --- | --- | --- |
| DEP-01 | dependency-required / existing-sufficient / standard-or-official-sufficient / blocked | REQ-XX |  |  |  |

## Candidate Matrix

| DEP ID | Candidate key | Package identity | Baseline class | Disposition | Hard gates | Project fit | Main concern |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DEP-01 | candidate-a |  | existing / standard-official / mainstream / specialized | selected / rejected / baseline | pass / fail / exception / unavailable |  |  |

候选必须属于相同生态和功能类别。package major、fork、rename、monorepo package 或统计口径差异写入 identity caveat，不能直接合并采用数据。

## Trust Receipts

| Candidate | Signal | Result | Value | Source type / URL | As of | Window | Caveat |
| --- | --- | --- | --- | --- | --- | --- | --- |
| candidate-a | stable_version | pass / concern / fail / insufficient-data |  |  | YYYY-MM-DD | snapshot |  |
| candidate-a | adoption_scale |  |  |  |  | snapshot / 6m / 12m / 24m |  |
| candidate-a | update_recency |  |  |  |  | 12m |  |
| candidate-a | maintenance_activity |  |  |  |  | 12m |  |
| candidate-a | adoption_trend |  |  |  |  | 6m / 12m / 24m |  |
| candidate-a | api_and_project_fit |  |  |  |  | snapshot |  |
| candidate-a | ecosystem_and_docs |  |  |  |  | snapshot |  |
| candidate-a | transitive_and_provenance |  |  |  |  | snapshot |  |
| candidate-a | operational_cost |  |  |  |  | snapshot |  |

`insufficient-data` 的 adoption trend 必须列出至少两个独立代理及其局限。单一 stars、downloads、dependents、commit count 或 Scorecard 总分不能选出赢家。

## Decision

- Selected DEP / candidate：
- Selection class：`existing-stack / standard-or-official / ecosystem-mainstream / specialized-exception`
- Selected version：
- Version policy：
- Manifest / lock paths：
- Freshness maximum age：`30 / 60 / 90 days`
- Decision reason：
- Rejected alternatives：

## Specialized Exception

- Mainstream baseline candidate：
- Unmet requirement IDs：
- Why the baseline fails：
- Accepted risks：
- Mitigations / isolation：
- Rollback / exit strategy：
- User or policy-owner acceptance required：`yes / no`

未使用 specialized exception 时写 `not-applicable`，不能保留空白例外段。

## Execution Handoff

- Approved identity and source repository：
- Approved version policy：
- Approved manifest paths：
- Ecosystem-native validations：
- Event invalidators：archived / deprecated / ownership / license / support line / applicable advisory。
- Research Drift triggers：package identity、version policy、hard gate、risk acceptance 或候选结论发生变化。

## Limitations And Rollback

- Public adoption coverage limitations：
- Evidence access limitations：
- Risks and mitigations：
- Rollback commands or procedure：

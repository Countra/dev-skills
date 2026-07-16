# Plan Review Profile

审查 Planner 已生成的 task bundle，不替 Planner 补写计划。目标包括 `execution-plan.md`、`plan-contract.json` 与 contract
纳入审批的非 review artifacts。

## 必需 Lenses

按以下顺序完整记录：

1. `PLAN-INTENT`：问题、目标、非目标、用户意图和成功定义是否一致。
2. `PLAN-TRACEABILITY`：GOAL/REQ/AC/NFR/STG/VAL/ART 是否闭环，是否有断链、孤儿或互相矛盾。
3. `PLAN-EVIDENCE`：Research、Standards、Dependency 与开发质量决策是否有足够、适用且新鲜的证据。
4. `PLAN-OPTIONS`：候选方案是否真实可区分，取舍、限制、可逆性和未选原因是否明确。
5. `PLAN-ARCHITECTURE`：change map 是否覆盖调用方、接口、数据、配置、测试、文档和运维影响。
6. `PLAN-EXECUTION`：stage DAG、entry/exit、allowed/forbidden、失败路径、恢复与回滚是否可执行。
7. `PLAN-VALIDATION`：验证是否能证伪验收，而非只证明脚本退出成功；风险是否有对应负例和回归。
8. `PLAN-GOVERNANCE`：授权、Git、外部写入、长期进程、amendment、pointer 和恢复边界是否清楚。
9. `PLAN-SIMPLICITY`：是否遗漏关键风险、把假设当事实，或引入与目标不成比例的机制。

## 证据要求

- finding 应引用 plan/contract 的具体 ID、artifact 路径和必要行号。
- 研究结论应能追到一手来源、观察日期、适用边界及对方案的影响。
- 不能因为 contract JSON 结构有效就判定方案语义完整。
- full/high-risk 任务优先 fresh-context、external-agent 或 human；same-context 可作为真实披露的降级证据。

## Verdict

- `passed`：target 当前，所有 lenses 已审查或有合理 N/A，且无 unresolved blocking/major。
- `changes_required`：存在 Planner 可修复的 unresolved blocking/major。
- `blocked`：缺少用户决策、关键权限、必要证据或合格专业审查能力。

目标修改后必须重新生成 plan target 与完整 receipt。旧 review artifact 保留为历史，不得覆盖。

## Planner Handoff

- Planner 在 contract 中只索引当前 `artifacts/reviews/plan-review-attempt-N.json`；历史 attempt 留在目录中但不进入当前批准 artifact index。
- attempt 大于 1 时，当前 receipt 必须通过 `supersedes_review_id` 指向紧邻前序 receipt；不得跳号、覆盖或跨 profile/scope 连接。
- Planner approval 调用 `review_validate.py`，固定传入 `--expected-profile plan-review`、`--expected-scope managed-plan` 与当前 `--task-dir`；只有返回的 verdict 为 `passed` 才能请求批准。
- Reviewer 不修改 plan、contract 或非 review artifacts。存在 finding 时，把修复责任交还 Planner；修复后旧 target 必然 stale，必须完整复审。

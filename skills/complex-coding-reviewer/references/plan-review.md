# Plan Review Profile

审查 Planner 已生成的 task bundle，不替 Planner 补写计划。目标包括 `execution-plan.md`、`plan-contract.json` 与 contract
纳入审批的非 review artifacts。

## 审查顺序

1. **意图与成功定义**：从用户要求、GOAL、非目标和约束重建真实问题。计划摘要只是待验证 claim。
2. **需求符合性**：逐个 REQ/AC/NFR 检查是否缺失、额外扩张或误解用户意图，并追到 Stage、VAL 和 ART。
3. **证据与选项**：确认关键事实来自适用且足够新鲜的来源；候选方案必须具有真实差异，不能把同一方案换名比较。
4. **核心设计**：先审系统边界、数据/接口、所有权和最危险假设，再看文件级 change map。
5. **可执行性**：按 DAG 顺序模拟每个 Stage 的 entry、allowed/forbidden、失败、恢复、验证、审查和退出。
6. **治理与简化**：确认授权、Git、外部写入、进程、amendment 和回滚；删除无验收价值的机制。

Planner 自述的完成状态、依赖理由和风险降级都只是 claim。即使某个缺陷是计划明确要求实现的 `plan-mandated defect`，仍应
报告 finding；批准文本不能把错误行为变成正确行为。

## 必需 Lenses

按以下顺序完整记录：

1. `PLAN-INTENT`：问题、目标、非目标、用户意图和成功定义是否一致；是否存在 missing、extra 或 misunderstood intent。
2. `PLAN-TRACEABILITY`：GOAL/REQ/AC/NFR/STG/VAL/ART 是否闭环，是否有断链、孤儿、重复所有权或互相矛盾。
3. `PLAN-EVIDENCE`：Research、Standards、Dependency 与开发质量决策是否有足够、适用、新鲜且披露限制的证据。
4. `PLAN-OPTIONS`：候选方案是否真实可区分，取舍、限制、可逆性、未选原因和默认路径是否明确。
5. `PLAN-ARCHITECTURE`：change map 是否覆盖调用方、接口、数据、配置、错误路径、测试、文档、CI 和运维影响。
6. `PLAN-EXECUTION`：Stage DAG、entry/exit、allowed/forbidden、失败路径、恢复、原子切换和回滚是否可执行。
7. `PLAN-VALIDATION`：验证是否能证伪验收，而非只证明脚本退出成功；关键风险是否有负例、near-miss 和回归。
8. `PLAN-GOVERNANCE`：授权、Git、外部写入、长期进程、amendment、pointer、恢复和 evidence ownership 是否清楚。
9. `PLAN-SIMPLICITY`：是否遗漏关键风险、把假设当事实，或引入与目标不成比例的 profile、服务、兼容层和抽象。

## 证据要求

- finding 应引用 plan/contract 的具体 ID、artifact 路径和必要行号。
- 研究结论应能追到一手来源、观察日期、适用边界及对方案的影响。
- 不能因为 contract JSON 结构有效就判定方案语义完整。
- 每个正向 lens summary 应说明检查了什么和依据；不能只写“完整”“合理”或“looks good”。
- 无法验证的要求记录为 verification gap，说明需要的证据、责任方和是否阻断批准。
- clean review 仍要说明审查范围、关键正向证据、未覆盖面和残余风险。
- full managed plan 使用 `strict` dispatch，必须由一个 `fork_context=false` 的 delegated reviewer 子 Agent 完成；工具不可用
  时 blocked，不允许 same-context 降级。lite/standard 使用 `conditional`，但工具可用时仍必须委派。

## Verdict

- `passed`：target 当前，所有 lenses 已审查或有合理 N/A，且无 unresolved blocking/major。
- `changes_required`：存在 Planner 可修复的 unresolved blocking/major。
- `blocked`：缺少用户决策、关键权限、必要证据或合格专业审查能力。

纯措辞、个人偏好或不改变可执行性的格式建议不得阻断。反之，目标、验收、关键证据、原子切换或验证无法闭合时，即使
Markdown 很完整也不能通过。

目标修改后必须重新生成 plan target 与完整 receipt。旧 review artifact 保留为历史，不得覆盖。

## Planner Handoff

- Planner 在 contract 中只索引当前 `artifacts/reviews/plan-review-attempt-N.json`；历史 attempt 留在目录中但不进入当前批准 artifact index。
- attempt 大于 1 时，当前 receipt 必须通过 `supersedes_review_id` 指向紧邻前序 receipt；不得跳号、覆盖或跨 profile/scope 连接。
- Planner approval 调用 `review_validate.py`，固定传入 `--expected-profile plan-review`、`--expected-scope managed-plan` 与当前 `--task-dir`；只有返回的 verdict 为 `passed` 才能请求批准。
- Reviewer 不修改 plan、contract 或非 review artifacts。存在 finding 时，把修复责任交还 Planner；修复后旧 target 必然 stale，必须完整复审。

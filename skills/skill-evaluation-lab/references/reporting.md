# 报告与结论边界

## 三层证据

报告固定分层：

1. `static`：脚本生成的 source-bound 机械事实。
2. `semantic`：当前 Agent 完成的七维设计判断。
3. `observed`：用户独立会话声明并经 importer 校验的有限证据。

三层使用同一 candidate tree hash；存在 baseline 时 observation 还必须绑定同一 baseline hash。报告入口会重新计算当前 source，evaluation id、hash、source drift 或 semantic evidence path 不兼容时拒绝生成。

## Observation 状态

- `not_requested`：当前评估不需要运行时观察。
- `not_observed`：需要观察，但用户尚未提供。
- `partial`：只导入部分 case/variant。
- `complete`：期望 case/variant 都有 session；仍需检查 inconclusive 数量。

只有 observation complete 且没有 inconclusive session 时，`runtime_claims_allowed` 才为 true；含义仍限制在这些 case。

## 禁止聚合

报告不产生单一 overall score，不把 warn/fail 相互抵消，不根据关键词自动写 recommendation，也不生成最终质量判断。

`completion.ready_for_agent_conclusion=true` 表示 static 与 semantic 结构完整，当前 Agent 可以开始综合；它不是 pass gate。

## 当前 Agent 输出

最终答复按以下顺序：

1. 结论与置信边界。
2. 按严重度排列的问题，每项引用 evidence。
3. 静态事实、语义判断、用户观察分别说明。
4. 不能声明的内容和残余风险。
5. 最小优化建议、预期效果和验证方式。

没有用户观察时可以完成静态/设计评估，但必须明确真实触发与行为未观察。

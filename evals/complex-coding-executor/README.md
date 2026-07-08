# complex-coding-executor evals

这些 fixture 用于人工或外部评估器检查 executor 行为。

覆盖重点：

- 未批准计划不能执行。
- open blocking 决策不能执行。
- run-to-completion 阶段边界不能误停。
- resolver 路径 containment、`HARNESS_DISABLED` opt-out、status summary 和 loop-tick。
- Execution Contract、attestation、append-only ledger 和 final gate 证据。
- 每阶段 review、验证、修复和记录。
- 错误恢复必须记录 attempt 和新策略，长子主题需要 topic handoff。
- process-manager 长期进程规则。
- Git 串行和 `index.lock` 恢复。
- 提交信息必须使用 `git commit -F`。

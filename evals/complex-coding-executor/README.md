# complex-coding-executor evals

这些 fixture 用于人工或外部评估器检查 executor 行为。

覆盖重点：

- 未批准计划不能执行。
- open blocking 决策不能执行。
- run-to-completion 阶段边界不能误停。
- 每阶段 review、验证、修复和记录。
- process-manager 长期进程规则。
- Git 串行和 `index.lock` 恢复。
- 提交信息必须使用 `git commit -F`。

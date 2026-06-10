# complex-coding-harness evals

这里保存轻量 prompt fixtures，用于检查 skill 行为是否符合规划工作流。

首批 eval 覆盖：

- direct 任务分级
- managed 任务分级
- needs-clarification 行为
- 只读规划时不创建 `.harness/tasks/`
- 实施前必须等待明确方案批准
- Git Context、分支占用和分支收口记录
- 热修复插入时的用户确认
- 最终交付门禁和截图或替代证据

这些文件是 prompt fixtures，不是自动判分测试。使用时应人工或通过外部评估器检查输出是否符合 `expected.yaml`。

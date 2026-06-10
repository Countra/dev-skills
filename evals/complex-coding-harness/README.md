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
- Plan Quality Gate、影响面矩阵和证据等级
- Stage Entry Gate、验证失败循环和范围变更重新审批
- Resume Summary 更新
- 提交信息文件方式和禁止多个 `-m` 拆分 bullet

这些文件是 prompt fixtures，不是自动判分测试。使用时应人工或通过外部评估器检查输出是否符合 `expected.yaml`。

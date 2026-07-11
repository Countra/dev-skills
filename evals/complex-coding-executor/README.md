# complex-coding-executor evals

这些 fixture 同时服务于 planner→executor 确定性联合评测、人工复核和可选 fresh-agent 评估。

覆盖重点：

- planner approval checker、不可变 attestation 与授权必须先通过。
- pointer-only resolver、路径 containment 和 `HARNESS_DISABLED` opt-out。
- ledger event-first、run-state snapshot、replay、drift detection 和 reconcile。
- revision archive、不可覆盖 attestation、已完成 stage carry 与 amendment 公共 CLI。
- run-to-completion 阶段边界不能误停，非法 transition 必须 fail closed。
- lite / standard / full bundle 都能被同一 consumer 完整消费。
- 每阶段 review、验证、修复和记录。
- Research Drift Gate：执行中发现新外部事实时补证据，必要时进入 Plan Amendment Gate。
- Development Quality Check：执行期引用 standards index，复核代码标准、静态质量、架构边界、模式取舍、耦合/内聚和验证证据。
- 错误恢复必须记录 attempt 和新策略，长子主题需要 topic handoff artifact。
- process-manager 长期进程规则。
- Git 串行和 `index.lock` 恢复。
- 提交信息必须使用 `git commit -F`。

运行：

```powershell
python -X utf8 -B evals/complex-coding-executor/run_evals.py
```

runner 会生成 planner bundle，再执行批准、阶段 lifecycle、snapshot 丢失恢复、amendment 和 final gate；回归集覆盖篡改计划、缺失 attestation、非法阶段完成、未关闭 pointer、缺失 contract 与缺失 commit evidence。

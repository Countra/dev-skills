# Harness Lightweight Evaluation

该评测生成 Planner、Reviewer、Executor 从 `e996fa5` 到当前树的确定性减负对比报告。

- 历史计划样本固定为基线提交前最后 10 个真实 managed `execution-plan.md`，不依赖 CI checkout history。
- 当前计划样本复用 Planner eval factory，分别生成 lite、standard、full bundle。
- review CLI 调用数采用公开工作流的命令模型：旧分步入口 4 次，新 `prepare + complete` 2 次。
- 兼容、blocking/major 召回和 bounded timeout 由同一 CI job 中的 unit、semantic oracle 与三平台真实进程树测试负责；本报告只索引这些证据，不伪造运行结论。
- 指标是否达到目标只用于观察，不决定脚本退出码；退出码只反映静态轻量化契约是否仍存在。

```text
python -u -X utf8 -B evals/harness-lightweight/run_evals.py --output .ci-artifacts/planner-reviewer-executor/lightweight.json
```

脚本固定 `agent_calls=0`、`network_calls=0`，不创建 Agent、不运行目标应用，也不上传 CI artifact。

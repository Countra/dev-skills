# Executor Scenarios

- 未批准任务只报告 planning，不创建 run-state。
- 批准后能从 current stage、Git 和最近验证恢复。
- 必需 validation 或 review 缺失时不能完成阶段。
- 计划 digest 漂移时进入 awaiting reapproval。
- blocked 状态保留一个当前原因和下一步，resume 后继续。
- 完整生命周期只产生 compact run-state，不产生 ledger 或 attestation。

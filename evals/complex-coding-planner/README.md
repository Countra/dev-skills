# complex-coding-planner evals

这些 fixture 同时服务于确定性 runner、人工复核和可选 fresh-agent 评估。

覆盖重点：

- direct / managed 路由，以及信息不足时的 discovery-first 阻断。
- lite / standard / full 风险画像、默认 1 / 2 / 3 stage 样本、compact 语义章节和软行数预算。
- `execution-plan.md` 与 `plan-contract.json` 的 ID、DAG、覆盖和 scope 一致性。
- Plan Quality、Producer Readiness、Reviewer handoff、canonical plan-review receipt 和 Approval。
- 研究 findings 落盘、重大决策前重读、批准后的 Plan Amendment Gate。
- Research Gate、online-required 官方/一手来源、blocked-by-access 降级和未处理 assumption 阻断。
- Dependency Selection Gate：必要性、existing/stdlib/mainstream 优先级、五类可信度信号、30/60/90 freshness、Gin/GORM 上下文示例和 specialized exception。
- Standards Discovery Gate：识别技术栈、收集官方/一手规范来源、沉淀 standards index。
- Development Quality Gate：覆盖代码标准、静态质量、架构边界、设计模式取舍、低耦合高内聚和验证映射。
- 缺失 contract、断链引用、环、可变计划章节、open decision、空/URL-only 语义门禁、依赖模式漂移和缺少在线来源必须 fail closed。
- 所有 profile 都要求 current plan-review receipt；lite/standard fixture 使用 `policy-disabled` same-context，full 使用 strict delegated fixture；missing、wrong-profile、open-major、stale target 和旧文本产物必须 fail closed。
- active task 的 missing、same、terminal、nonterminal、unknown 与原子替换失败保持可回归。
- Readiness 后停止等待用户批准，不直接实现。
- 提交授权必须单独记录。

运行：

```powershell
python -X utf8 -B evals/complex-coding-planner/run_evals.py
```

runner 读取 `manifest.json`，当前执行 3 个 capability 与 14 个 regression case，并输出 profile、计划行数和 artifact 数指标。沙箱限制临时目录时，可用 `--work-dir <path>` 指定隔离父目录。

# Execution Workflow

## 启动

运行 `harness_state.py status`，并同时检查 Git 工作树和当前 diff。

- `planning`：等待用户批准，不实现。
- `approved`：启动下一依赖已满足的阶段。
- `in_progress`：从 current stage、代码和最近验证继续。
- `blocked`：解决 blocker 后显式 resume。
- `awaiting_reapproval`：停止修改，更新方案并请求批准。
- `completed`：只做最终状态核对和交付。

旧 heavy contract、ledger 或 attestation 不参与恢复。工具拒绝旧 contract 时使用 Planner 重新生成 compact bundle。

## 批准与授权

用户明确批准实施后运行：

```text
harness_state.py approve --implementation \
  --plan-review-mode same-context \
  --plan-review-summary "未发现 blocking/major；残余风险已说明"
```

高风险计划的 mode 必须是 `independent`。提交、外部写入和提权各自需要显式参数，且必须已列入 contract 的请求；实施批准不自动授予这些权限，新增权限边界先重新批准。

## 阶段

典型顺序：

```text
start -> implement -> validate -> review -> finish-stage
```

`finish-stage` 只检查 contract 声明的 required validation 和 review。新 validation 会使该阶段旧 review 摘要失效，确保修复后的目标重新审查。

低风险阶段可在 contract 中使用 `none`；medium 默认 `same-context`；high 必须 `independent`。所有阶段完成后记录 `final` review，再 complete。

## 重新批准

以下变化先运行 `reapproval`：

- 用户可见范围或公共接口
- Stage DAG 或必需验证
- 关键依赖或数据迁移
- 风险级别或授权边界

更新 plan/contract、递增 `plan_revision`、重新 plan-review 并等待用户批准。新批准可通过 `--carry-completed` 明确保留执行边界未变化的已完成阶段，CLI 会核对阶段、验证与审查定义；不自动继承授权。

批准范围内的实现细节、命名和局部结构调整不触发 amendment 文件或新的计划 revision。

## 恢复与事实冲突

run-state 只提供最近恢复点。恢复时核对：

- 当前代码是否与 state 声称的阶段一致
- Git 是否存在用户修改、未跟踪文件或额外提交
- 最近 validation/review 是否仍对应当前实现
- 长期服务是否由 Process Manager 正确拥有

无法确定时用 `block` 保存简短原因和下一步。不要伪造 validation/review，也不要添加 ledger 来掩盖不确定性。

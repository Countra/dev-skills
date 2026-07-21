# Reviewer Troubleshooting

先保留 review ID、policy、target/context digest、preparation、final dispatch、semantic result、Agent ID 和原始错误码。不得通过
编辑旧制品、降低 policy 或由 coordinator 代写 verdict 来消除错误。

## 能力与策略

- `REVIEW_DISPATCH_REQUIRED_UNAVAILABLE`：strict 场景缺少完整 `spawn_agent`/`wait_agent`/`close_agent` 工具族，或平台禁止
  委派。保留 blocked dispatch，等待宿主能力或合格 human gate；不能 same-context 放行。
- `REVIEW_DISPATCH_POLICY_VIOLATION`：policy、capability、decision、attempt、timeout、fallback 或生命周期组合不合法。
  回到 preparation 与原始宿主事实修正，不修改 validator。
- 低/中风险 conditional 应由调用方预先记录 `policy-disabled` 并跳过工具探测；已决定委派且工具完整时再回退属于策略违规。
- strict 场景被平台或用户禁止委派时，保持 `policy=strict` 并记录 `capability.status=policy-disabled`；不得把 expected policy
  改成 disabled 规避 blocked。

## Stale 与上下文扩展

- `REVIEW_DISPATCH_STALE`：冻结 target/context 或其文件内容已变化。关闭当前 Agent，以 `retryable=false` 保存 non-gating
  failed dispatch，废弃结果，再用新 review 输入重新生成 target/context；不能沿用同一 retry chain。
- 子 Agent 请求额外 context：将请求作为失败 attempt 的事实记录；扩展 allowlist context 后重新冻结并创建新 Agent，不能向
  当前 Agent 临时粘贴文件继续完成。
- package 变化不替代 target/context freshness；package 只是阅读视图。
- `REVIEW_PACKAGE_LIMIT_EXCEEDED`：Agent-bound package 的原始 JSON 或声明 `byte_count` 超过 512 KiB。保留完整
  target/context，省略可选 `--package` 后开始新的完整审查；不要为了消除错误静默缩小 target。

## Agent 失败

- timeout/crash：在 `finally` 关闭 Agent并保存 failed dispatch；attempt=1 时允许一次全新 attempt。若 spawn 尚未返回
  Agent ID，close 记录 `not-required`，仍可在 failure 明确 retryable 时重试。
- 等待必须按单次不超过 60 秒的窗口轮询，并使用 preparation 的总 timeout 计算剩余预算；每个窗口结束后报告进度，
  不能因重新调用 `wait_agent` 而重新计时。父任务恢复后若宿主对已记录 Agent ID 返回 `not_found`，停止反复等待或猜测
  ACL，尝试一次关闭后以 `REVIEW_DISPATCH_AGENT_UNCLOSED` 封存 non-gating 失败。
- 大目标连续 timeout 时先检查是否误绑定了接近预算上限的 package；package 是读取优化，不应把完整文件与大 diff 一次性
  灌入 Agent。改变 package 需要新 review，不能改写已冻结 retry chain。
- 若完整 target 本身仍可管理，但 high-risk 的默认 900 秒不足，可在旧 retry chain 封闭后按冻结目标规模创建新 review，
  显式设置更长等待时间；该值必须受当前任务剩余预算约束，不能修改已开始的 preparation。
- schema 错误：只允许同一 Agent 修正一次，只发送 validator 的 JSON/closed-schema 错误，不发送新的语义判断。
- 只有 preparation 的 `available_tools` 已冻结 `send_input` 时才能记录一次 schema repair；工具不可用就封存失败或进入新
  attempt，不能事后补写能力。
- 第二个 Agent attempt 仍失败：blocked；不得由 coordinator 接管语义审查。
- `REVIEW_DISPATCH_AGENT_UNCLOSED`：保留 candidate evidence，重试关闭或等待宿主恢复。关闭状态未证实时不能 passed。

## Provenance 与结果

- `REVIEW_DISPATCH_PROVENANCE_MISMATCH`：检查 preparation/final dispatch/result/receipt 的 ref、raw SHA-256、Agent ID、
  reviewer 字段和双 digest。任何 supporting artifact 被改动都必须重建下游制品。
- 时间线错误：核对 preparation、Agent start/completion/close、semantic `reviewed_at` 与 finalization 的真实观察时间；
  不得用固定早期时间或未来时间凑齐字段。
- `REVIEW_RESULT_INVALID`：semantic result 不是 closed schema、profile/scope/digest 不一致、coverage/lens/finding/gap/verdict
  派生错误。若尚未用过 schema repair，可退回同一 Agent 一次；否则新 attempt。
- `fork_context=true`、`parent_judgment_included=true` 或 `recursive_delegation_allowed=true` 都破坏正式独立审查，不能只改
  boolean 掩盖宿主事实。

## Planner 与 Executor

- Planner full receipt 必须是 `strict`；lite/standard 必须是 `conditional`。
- Executor high-risk stage 与 final-integration 必须是 `strict`；low/medium stage 必须是 `conditional`。
- compact `review_recorded` 必须与 validator 派生的 `reviewer_mode`、`independence_claim` 和 `dispatch_id` 精确一致。
- finding 修复、验证重跑、commit 或 context 变化后创建新 receipt attempt；旧 attempt 只保留历史证据。

## 环境噪声

没有 Reviewer JSON envelope 的 shell/profile access denied 不能自动解释为 review root ACL。先检查目标 helper 的退出码、
stdout envelope 和精确路径；不要自动提权、删除 review root 或重复启动 Agent。

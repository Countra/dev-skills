# Code Review Profile

审查本地可重建代码目标，不负责运行测试、修复 finding、提交代码或操作远端评审平台。managed 模式同时读取批准的
contract、当前 stage、已存在验证 evidence 和声明规范。

## Scope

- `stage-delta`：stage baseline 到当前状态，绑定 `stage_id` 和 `attempt`。
- `final-integration`：execution baseline 到最终状态，覆盖跨阶段交互和整体回归。
- `standalone`：显式文件、working tree 或 commit range。

三者都是 `code-review` 内部 scope。stage receipt 不能替代 final receipt。

## Managed Handoff

- Executor 先固定 execution/stage baseline、批准路径和当前 attempt；Reviewer 只消费 target、contract、standards 与已有验证 evidence，不修改代码、ledger 或 Git。
- `stage-delta` target identity 必须同时携带当前 `stage_id` 与 `attempt`，并覆盖 baseline 后的 staged/unstaged、deletion 及范围内 untracked 文件。
- managed Executor 必须把 contract 的 `allowed_changes` 规范化为最小 path prefix 集合，并要求 target identity 的 `paths` 精确匹配；fresh 但只覆盖局部路径的 receipt 仍然无效。
- `final-integration` 必须从 execution baseline 覆盖整体变更。若 final commit 改变 `HEAD`，pre-commit receipt 立即 stale，必须对真实 commit-range 重新审查。
- canonical receipt 只写入显式 review root，attempt 不覆盖旧文件；修复后用 `supersedes_review_id` 连接同 profile、同 scope kind 的前序 receipt。
- managed caller 必须用 `review_validate.py` 传入 expected profile/scope/stage/attempt，并在 transition/final 前重验 freshness；不得从 Markdown 或摘要推断 verdict。
- same-context 审查必须如实声明 `independence_claim=false`；只有真实 fresh context、external agent 或 human 才能按对应 provenance 声明能力边界。

## 必需 Lenses

按以下顺序完整记录：

1. `CODE-CORRECTNESS`：实现是否满足声明意图，正常、边界、失败和回归路径是否正确。
2. `CODE-BOUNDARIES`：接口、数据、错误、资源释放、并发和平台边界是否保持契约。
3. `CODE-ARCHITECTURE`：依赖方向、职责、耦合、内聚、复杂度和抽象是否有利于代码健康。
4. `CODE-RISK`：按变更触发安全、隐私、权限、输入和秘密处理；不适用时明确 N/A。
5. `CODE-TESTS`：测试能否在实现错误时失败，断言、fixture、负例和平台覆盖是否有效。
6. `CODE-DELIVERY`：文档、配置、迁移、兼容、部署和回滚是否与行为变化同步。
7. `CODE-SCOPE`：finding 是否由 target 与必要上下文支持，是否存在 scope leak 或无证据猜测。

## Finding 纪律

- 优先报告会造成错误行为、回归、数据/安全风险或明显维护成本的问题。
- claim 必须可证伪；evidence 定位到路径/行/符号、artifact 或规范；impact 说明具体后果。
- 不为与变更无关的旧问题阻断本次审查，除非变更扩大了风险。
- 不把 lint、测试通过或代码风格偏好当作正确性证明。
- finding 修复会改变 target；旧 receipt 无论 pass/fail 都 stale，必须完整复审。

## Verdict

- `passed`：target 当前，必需 lenses 完成，无 unresolved blocking/major；可保留非阻断 minor/advisory。
- `changes_required`：存在 Executor/作者可修复的 unresolved blocking/major。
- `blocked`：目标、baseline、证据、权限或专业能力不足，当前不能可靠审查。

# 评估工作流

## 证据顺序

固定顺序为：目标界定、静态事实、当前 Agent 语义审查、可选用户观察、透明报告、当前 Agent 完整结论。

任何后层都不能回写前层含义：

- 静态检查不能声称真实触发或运行行为。
- 语义审查不能伪装成机械事实。
- 用户 observation 是用户声明并经 hash 校验的有限样本，不能外推总体表现。
- 报告只聚合，不替当前 Agent 作最终判断。

## 评估准备

先记录：

1. candidate 与可选 baseline 的 workspace 相对路径。
2. 用户真正要做的决策，例如“description 是否过宽”或“工作流是否遗漏失败路径”。
3. 是否必须观察真实触发；能由 source 回答时不创建 observation suite。
4. evidence 输出目录。所有输出必须在 workspace 内、source 外，且使用新路径。

仓库包含多个 Skill、用户询问 coverage 或不确定有哪些评估入口时才运行 inventory。单 Skill 请求直接进入 static check。

## 静态阶段

`se_check.py` 输出 source identity、八项 check、capability signals 和可选 baseline delta。处理顺序：

1. `fail`：机械可证明的 metadata、路径、引用或语法问题。
2. `warn`：需要当前 Agent 判断的建议或风险信号。
3. `pass`：只代表该 check 的机械条件成立。
4. `not_applicable`：例如未提供 baseline，不能解读为通过比较。

修改 candidate 或 baseline 后 tree hash 会变化，旧 review、packet 和 observation 不再兼容；报告入口会重新计算当前 source，拒绝陈旧证据。

## 七维语义阶段

当前 Agent必须阅读真实 source，不得从 check status 自动推导语义 status：

| Dimension | 核心问题 |
| --- | --- |
| `invocation_boundary` | description 是否说明何时使用、何时不使用，near-miss 是否清楚 |
| `workflow_completeness` | 输入、步骤、分支、错误、验证和完成门禁是否闭环 |
| `information_architecture` | 核心流程是否直接可见，细节是否渐进披露且无重复真相源 |
| `tool_contract` | 每个脚本/工具是否单责，参数、副作用和错误是否明确 |
| `safety_and_permissions` | 凭据、网络、进程、外部写入和用户确认边界是否最小化 |
| `verification_and_delivery` | 是否有可检查完成标准、测试/eval/CI 和真实交付说明 |
| `scope_and_composability` | 能力是否原子、可组合，是否绑定一次性场景或过度抽象 |

每个维度必须引用 candidate 内真实文件。`warn`/`fail` 必须有 recommendation；limitations 至少一项。

## 用户观察阶段

触发、UI、工具选择或端到端行为确实需要实测时：

1. suite 至少包含一个 trigger positive、一个 near miss 和一个 behavior case。
2. validate 后 prepare packet。
3. 当前会话停止，由用户在独立会话中操作。
4. 用户填写 bundle；importer 只校验，不运行、不补字段。
5. source 或 input 漂移时废弃旧 packet，不能重解释旧结果。

## 完整结论

报告 `completion.ready_for_agent_conclusion=true` 只说明证据结构完整，不等于质量通过。当前 Agent仍需：

1. 按严重度列问题，并区分机械事实、设计判断和用户观察。
2. 说明没有观察或样本不完整时不能声称什么。
3. 给出与 evidence 对应的最小优化建议和验证方式。
4. 若用户要求修改，另行进入实现流程；评估阶段不应先改 candidate。

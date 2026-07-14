# Skill Evaluation Evidence Report

## Target

- Evaluation：`complex-coding-planner-20260714`
- Path：`skills/complex-coding-planner`
- Tree SHA-256：`27cf83e0b02d96d5ff282903f53897bf35792d9409e2fb39d31ec5669aaf313d`

## Evidence Coverage

- Static：`complete` {'pass': 5, 'warn': 2, 'fail': 0, 'not_applicable': 1}
- Semantic：`complete` {'pass': 4, 'warn': 3, 'fail': 0, 'not_applicable': 0}
- Observed：`not_requested` (0/0)

## 已证明

- `skill.structure` [warn] 非标准顶层资源：templates
- `skill.validation_assets` [warn] 缺少可发现的验证资产：ci

## 审查判断

- `workflow_completeness` [warn] 从研究、规范、质量、契约、审批到 amendment 的主流程完整，但写 active pointer 前没有定义已有活动任务的冲突、复用或切换策略。
- `tool_contract` [warn] plan-contract 的闭合字段、ID、DAG、覆盖和 artifact 校验较强，但 approval checker 对研究与就绪门禁主要检查关键词和 URL 存在，无法阻止内容空洞但形式通过的计划。
- `verification_and_delivery` [warn] 已有较完整的 checker 单元测试和确定性 eval 设计，但仓库没有为 planner 配置可发现的 CI，现有验证重点仍是结构契约而非真实规划行为。

## 用户观察

- 尚未导入用户独立会话观察。

## 假设与限制

- 假设：本次目标是评估当前源码设计与静态契约，不评估某次具体规划产物的内容质量。
- 假设：complex-coding-executor 继续以 references/task-contract.md 为唯一共享契约，并与 planner 同仓演进。
- 限制：未提供旧版 baseline，因此没有版本增退化结论。
- 限制：按静态评估契约未执行目标 checker、单元测试或 eval，仅阅读其实现与测试设计。
- 限制：未进行用户独立会话观察，因此不能声明真实触发准确率、规划质量或长任务恢复效果。
- 限制：process-manager 细节直接嵌入 planning workflow，跨 Skill 契约仍需依赖共同回归避免漂移。

## 声明边界

- 静态检查只证明 source-bound 机械事实和能力信号，不证明真实运行行为。
- 七维语义审查是当前 Agent 的设计判断，必须保留 assumptions 与 limitations。
- 缺少完整、结论明确的用户观察，不得声明真实触发率或行为提升。

## 当前 Agent 后续动作

读取完整证据后，由当前 Agent 给出结论、置信边界、问题优先级和优化建议。
报告脚本不会生成最终判断。

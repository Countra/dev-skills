---
name: skill-evaluation-lab
description: 静态检查并系统评审 Agent Skill 的触发边界、工作流、信息架构、工具契约、安全权限、验证交付和可组合性，生成 source-bound 分层证据与优化结论；可准备由用户在独立会话中手工完成的观察工作包并导入结果。当任务只是普通代码评审、单元测试，或并不评估 Skill 本身时不要使用。
---

# Skill Evaluation Lab

以当前 Agent 的评审工作流评估 Skill。脚本只产生确定性静态事实、校验用户证据并汇总报告；不得自动启动或探测
Codex、模型 API、子代理、其它 Agent 或目标脚本。

## 主工作流

1. 明确 candidate、可选 baseline、用户要回答的决策问题和评估工作目录；先不修改 candidate。
2. 只有需要仓库全貌或能力边界不清楚时，运行 `scripts/se_inventory.py --root <repo>`。
3. 运行 `scripts/se_check.py --workspace <repo> --candidate <skill> --output <static.json>`；先处理机械 fail，
   不把 capability signal 表述为实际行为。
4. 当前 Agent 阅读 candidate 的 `SKILL.md`、references、scripts、tests、evals 和 static evidence，按以下七维各写一次
   source-bound review：
   - `invocation_boundary`
   - `workflow_completeness`
   - `information_architecture`
   - `tool_contract`
   - `safety_and_permissions`
   - `verification_and_delivery`
   - `scope_and_composability`
5. 以 `assets/semantic-review.example.json` 为结构起点，替换真实 `evaluation_id`、tree hash、evidence、assumptions、
   limitations 和 observation decision。不得让脚本替当前 Agent 生成语义 finding。
6. 运行 `scripts/se_report.py --static <static.json> --review <review.json>` 生成分层报告。
7. 当前 Agent 读取报告和原始证据，给出完整结论、置信边界、问题优先级与可执行优化建议。报告脚本不是结论作者。

## 可选用户观察

只有静态与语义证据不足以回答触发或真实行为问题时才进入此分支：

1. 从 `assets/observation-suite.example.json` 建立正例、near-miss 和 behavior cases。
2. 运行 `scripts/se_validate.py --workspace <repo> --suite <suite.json>`。
3. 运行 `scripts/se_prepare.py --workspace <repo> --suite <suite.json> --output-dir <new-packet-dir>`。
4. **立即停止。** 请用户在独立会话中逐个完成 packet；当前 Agent 不得代替用户启动任何 Agent 或模型。
5. 用户交回 observation bundle 后，运行 `scripts/se_import.py` 校验 packet、source、case、artifact 和 provenance。
6. 将 imported observation 传给 `se_report.py --observation <imported.json>`，再由当前 Agent 更新完整结论。

没有导入完整 observation 时，报告必须保持 `not_requested`、`not_observed` 或 `partial`，不得推断真实触发率或行为提升。

## 原子入口

- `se_inventory.py`：按需盘点 Skill、测试、eval 与 CI coverage。
- `se_check.py`：只读生成 candidate 与可选 baseline 的确定性静态证据。
- `se_validate.py`：校验人工 observation suite 与 workspace 资源。
- `se_prepare.py`：只生成不可执行 packet；输出目录必须不存在。
- `se_import.py`：只校验并规范化用户声明的 observation。
- `se_report.py`：重新核验当前 candidate/baseline hash 后合并三层证据，不生成总分或最终判断。

## 完成门禁

- static evidence 绑定当前 candidate tree，机械 fail 已解释或修复。
- 七个语义维度完整，evidence path 存在；warn/fail 有 recommendation。
- assumptions、limitations 和 observation decision 明确。
- 报告分开“静态事实、审查判断、用户观察”，并保留 claim boundaries。
- 最终结论由当前 Agent 基于完整证据给出；脚本不得代写。

设计评估流程时读 [workflow.md](references/workflow.md)。解释静态检查时读
[static-checks.md](references/static-checks.md)。需要用户观察时读
[observation-contract.md](references/observation-contract.md)。解释报告与结论边界时读
[reporting.md](references/reporting.md)。

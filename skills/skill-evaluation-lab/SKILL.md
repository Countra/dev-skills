---
name: skill-evaluation-lab
description: 设计、校验、运行和解释 Agent Skill 的结构化评测。用于创建或升级 skill、检查 description 的触发与 near-miss 边界、比较 candidate 与无 skill 或旧快照 baseline、验证行为产物、分析 token/耗时、不确定性和回归风险；当任务只需普通单元测试、代码评审或并不评估 skill 本身时不要使用。
---

# Skill Evaluation Lab

建立可重复、可审计的 skill 评测证据。默认只执行离线步骤；真实模型调用必须先展示不可变 fingerprint 和预算，并获得用户对本次有限调用的明确授权。

## 工作流

1. 明确要回答的是 inventory、触发边界、行为质量、candidate/baseline 差异还是回归门禁；不要先改被评估 skill。
2. 需要仓库全貌时运行 `scripts/se_inventory.py --root <repo>`，把现有测试/eval 视为可保留资产，不批量迁移。
3. 从 `assets/eval-suite.example.json` 建立闭合 suite。先设计正例、near miss、behavior oracle、split 和 baseline，再运行 `scripts/se_validate.py --suite <file>`。
4. 运行 `scripts/se_plan.py --suite <file>`；记录 candidate/baseline 哈希、矩阵、模型、最大 agent/judge 调用数、墙钟上限和 fingerprint。
5. `fake` suite 可直接运行。`codex-cli` suite 只有在用户批准当前 fingerprint 后，才能使用 `scripts/se_run.py --authorize-live --fingerprint <sha256>`。
6. 依次运行 `scripts/se_grade.py` 与 `scripts/se_report.py`。确定性 assertion 优先；人工反馈和 blind/swap judge 保持独立证据层。
7. 根据逐项 gate、样本量、Wilson 区间、paired delta、失败分类、provenance 和成本完整性解释结果；低信息或不兼容结果不得表述为提升。
8. 修改 skill 后重新 validate/plan。任何 suite、模型、runner 配置或 source snapshot 变化都会要求新的 fingerprint 和授权。

## 原子入口

- `se_inventory.py`：只读扫描 skill、脚本、测试、eval 和 CI coverage。
- `se_validate.py`：闭合校验 suite、路径、assertion 和 runner 安全边界。
- `se_plan.py`：展开矩阵与硬预算，计算 source-aware fingerprint；不调用模型。
- `se_doctor.py`：仅在 Codex capability 不确定或 live 入口失败时诊断；普通流程不先运行。
- `se_run.py`：创建隔离快照并执行 trigger/paired behavior；不负责质量结论。
- `se_grade.py`：生成确定性 grade，可选合并独立 human feedback 与 blind/swap judge 结果。
- `se_report.py`：生成透明 JSON/Markdown 报告，不产生单一不透明总分。

设计 case、split 或迁移现有 eval 时读 `references/workflow.md`。字段或 assertion 不确定时读 `references/suite-contract.md`。涉及 live Codex 时必须读 `references/codex-runner.md` 与 `references/security.md`。涉及人工反馈、指标或 LLM judge 时读 `references/grading.md`。

## 安全边界

- 不把 expected behavior、assertion 或 judge rubric 放进 agent prompt/workspace。
- 不直接在 source repo 上执行 behavior case；只使用隔离快照。
- 不读取、复制或输出 `auth.json`、PAT、API key 等秘密。
- 不在 fingerprint 不匹配、预算越界、source drift、timeout 或 outcome unknown 时盲目重放。
- runner、trigger observation 或 judge 不受支持时明确返回 unsupported/inconclusive。
- 不把未校准 judge 当成硬门禁，不跨 fingerprint/model/sandbox 聚合结果，不用重复次数掩盖 case 覆盖不足。

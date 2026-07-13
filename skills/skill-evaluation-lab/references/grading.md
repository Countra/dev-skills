# Grading And Reporting

只在设计 assertion、添加人工反馈、使用 LLM judge 或解释统计结果时读取。评分顺序固定为 deterministic first；judge 不能覆盖机械失败。

## 目录

1. [Deterministic Grade](#deterministic-grade)
2. [Human Feedback](#human-feedback)
3. [Blind And Swap Judge](#blind-and-swap-judge)
4. [Report Metrics](#report-metrics)
5. [Compatibility Rules](#compatibility-rules)
6. [Interpretation](#interpretation)

## Deterministic Grade

`se_grade.py` 先按 `schemas/run-manifest.schema.json` 对应的标准库 validator 闭合校验 manifest，再逐条解释 run record：

1. runner 未成功：`runner_failure`。
2. trigger receipt 与 `should_trigger` 不符：`trigger_mismatch`。
3. behavior 缺 assertion 证据：`missing_assertion_evidence`。
4. assertion 计数结构非法：`invalid_assertion_evidence`。
5. 任一 assertion ERROR：`assertion_error`。
6. 任一 assertion FAIL：`requirement_failure`。
7. counts 与 summary 矛盾：`inconsistent_assertion_summary`。

每条记录保留原 assertion evidence、usage、pairing 和 provenance。run fingerprint 缺失或 record 与 manifest fingerprint 冲突时拒绝评分，不能把不同实验条件混成一份 grade。

## Human Feedback

人工反馈是独立层，不修改 `deterministic.passed`。输入文件必须且仅能包含 `feedback`：

```json
{
  "feedback": [
    {
      "record_key": "case-id:1:candidate",
      "label": "pass",
      "notes": "Artifact satisfies the reviewed domain requirement."
    }
  ]
}
```

`label` 只能是 `pass`、`fail` 或 `inconclusive`。record key 必须存在且唯一；notes 可以记录 rubric 依据，但不能包含凭据或未脱敏用户数据。

运行：

```text
python -u -X utf8 -B scripts/se_grade.py --run <run.json> --human-feedback <feedback.json> --output <grade.json>
```

人工样本可用于校准 judge，但不能用少量同一作者反馈宣称普遍可靠。

## Blind And Swap Judge

Judge 只适用于难以完全机械化的质量差异，且必须满足：

- candidate/baseline 身份、路径和标签先去标识。
- 同一 pair 生成 forward 与 A/B 位置互换的 swap task。
- 发给 judge 的只有 public task；private mapping 永不进入 judge prompt。
- 两次判断必须对应不同 task id，并与两份 private mapping 精确匹配。
- position swap 结果冲突时始终是 `inconclusive`。
- 未经人工校准时 authority 只能是 `advisory`。

内部 API `build_blind_swap_tasks(...)` 返回 `public_tasks` 与 `private_mappings`。必须把两者分开保存：调用 judge 时只发送单条 public task；收齐判断后才在 grader 侧与 private mapping 合并。

Judge 结果闭合字段：

```json
{
  "task_id": "neutral-pair-forward",
  "winner": "A",
  "confidence": 0.8,
  "rationale": "Output A satisfies more rubric requirements."
}
```

`winner` 只能是 `A`、`B`、`tie`，confidence 在 0-1。校准对象必须包含非负 `sample_count` 与 0-1 `agreement_rate`；当前至少 5 个人工样本且 agreement rate 不低于 0.8，非冲突判断才可标为 `decision`。

`assets/judge-bundle.example.json` 展示 grader 侧 bundle。不要把整份 bundle 发给 judge，因为其中包含 private mapping。

## Report Metrics

`se_report.py` 输出 JSON 与 Markdown，不输出单一 overall score。重点字段：

- `quality`：按 variant 汇总，并按 mode 分层；包含 n、passed、pass rate、Wilson 95% interval。
- `trigger`：activation rate、正负例 confusion matrix 和缺失 observation 记录。
- `case_results`：每条记录的模式、variant、机械状态、失败类型、assertion counts、trigger truth 与耗时摘要。
- `paired_delta`：behavior 的 wins/losses/ties、delta 数值摘要、排除 pair 与 `low_information`。
- `cost`：token totals、每字段 sample count/complete 状态、按 variant totals、duration 摘要。
- `failure_taxonomy`：失败原因计数。
- `human_feedback`：独立人工标签分布。
- `judge`：status、authority、calibration 和 confidence。
- `gate_decisions`：逐项显示 required、available、threshold、actual、样本量、结果和原因。
- `provenance`：fingerprint、source identity 与执行条件分组。
- `uncertainty`：小样本、低信息、duration/token 完整性和 judge authority。

Wilson interval 适合小样本二项比例；`n=0` 时区间明确 unavailable。数值样本少于 2 时不显示 sample standard deviation。

run provenance 中的 `lab_tree_sha256` 必须与 run manifest 一致；grade 另存实际 `grader_identity`。因此 runner 或 grader 实现变化不会被旧 fingerprint/证据静默掩盖。

没有对应 candidate mode 的 gate 标为 `not_applicable`，不会伪造通过率。required judge 只有在校准后给出 `authority=decision` 且选择 candidate 时通过；缺失或 advisory 证据均失败关闭。`all_required_passed` 只是逐项 gate 的合取结果，不是综合质量分。

## Compatibility Rules

以下结果不能直接聚合：

- fingerprint 不同。
- model、adapter、CLI capability、sandbox 或 network policy 不同。
- behavior pair 的 prompt/input/timeout/repetition 不同。
- candidate/baseline pair 缺一侧或同一侧重复。

报告会排除不兼容 pair，而不是把它们当 tie。跨文档聚合前调用 compatibility check；缺 fingerprint 同样拒绝。

## Interpretation

采用以下表述边界：

- candidate win 且样本充分：说明观察到的 paired improvement，并附 n/区间。
- candidate 与 baseline 全部 tie：说明本套 case 未区分两者，不说明等价。
- 两侧都失败：先按 failure taxonomy 修复 case/runner，不宣称 skill 无效。
- 只有 judge 偏好：说明 advisory preference，不作硬门禁。
- token 降低但质量区间重叠：报告成本变化与质量不确定性，不合并成综合分。
- holdout 失败：记录回归，不用该 holdout 继续调参后再称独立验证。

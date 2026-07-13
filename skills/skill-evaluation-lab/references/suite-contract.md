# Evaluation Suite Contract

suite 是 UTF-8 JSON object。契约闭合：未知字段、缺失必需字段、路径逃逸或不支持的枚举值都会使 `se_validate.py` 返回非零退出码和稳定 JSON path。机器可读契约位于 `schemas/eval-suite.schema.json`，Python validator 是执行前的权威校验入口。

以 `assets/eval-suite.example.json` 为起点，不要手写未在本文或 validator 中定义的扩展字段。

## 目录

1. [根字段](#根字段)
2. [Baseline](#baseline)
3. [Runner](#runner)
4. [Budgets](#budgets)
5. [Gates](#gates)
6. [Case](#case)
7. [Assertion](#assertion)
8. [Outcome 语义](#outcome-语义)

## 根字段

| 字段 | 约束 | 作用 |
| --- | --- | --- |
| `suite_id` | 小写字母、数字、连字符，1-64 字符 | artifact 与 run namespace |
| `skill_path` | 指向含 `SKILL.md` 的目录 | candidate source，可位于 suite 目录外 |
| `baseline` | 闭合 object | `none` 或独立 `snapshot` |
| `runner` | 闭合 object | adapter、模型、sandbox 和执行上限 |
| `budgets` | 闭合 object | agent/judge/墙钟硬预算 |
| `gates` | 闭合 object | 供报告决策使用的显式阈值 |
| `cases` | 非空数组 | trigger 与 behavior case |

`skill_path` 与 snapshot path 可以是绝对路径或相对 suite 的路径，但不能是符号链接/junction，且运行时只复制为快照。case input 与 assertion path 必须是 suite/工作区内相对路径，不能包含 `..`。

## Baseline

无 skill baseline：

```json
{"mode": "none"}
```

旧版本快照：

```json
{"mode": "snapshot", "path": "../skill-before-change"}
```

snapshot 必须包含 `SKILL.md`，且不能与 candidate 解析为同一目录。

## Runner

必需字段：

| 字段 | 值 |
| --- | --- |
| `adapter` | `fake` 或 `codex-cli` |
| `model` | 非空模型标识；会进入 fingerprint |
| `sandbox` | `read-only` 或 `workspace-write`；拒绝 danger-full-access |
| `timeout_seconds` | 每次调用的正整数上限 |
| `repetitions` | case 未覆盖时的默认正整数 |
| `concurrency` | 1-4 的声明上限；以 run artifact 的 `execution_order` 为实际执行顺序 |
| `network_access` | 当前必须为 `false` |

Trigger case 使用只读 observation；behavior case 需要写 artifact 时应选择 `workspace-write`。即使 suite 声明 workspace-write，source repo 仍不可写，只有隔离 case workspace 可写。

## Budgets

`max_agent_runs`、`max_judge_runs`、`max_wall_seconds` 都是正整数。`se_plan.py` 会先展开矩阵；需要的 agent runs 超过上限时，在调用模型前失败。

实现硬上限为 256 次 agent run、32 次 judge run、86400 秒总墙钟、每次 3600 秒 timeout 和每个 case 20 次 repetition。suite 最多 128 个 case；单 case 最多 64 个 input 与 64 个 assertion。声明值即使自洽，超过实现硬上限仍会在执行前被拒绝。

矩阵规则：

- trigger：每个 repetition 只运行 candidate。
- behavior：每个 repetition 运行 candidate 与 baseline 两侧；奇数轮 candidate 先行，偶数轮 baseline 先行。
- case 自己的 `repetitions` 优先于 runner 默认值。
- judge 预算单独计算，不包含在 behavior pair 中。

## Gates

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `trigger_threshold` | 0-1 | trigger case 最低通过率 |
| `required_case_pass_rate` | 0-1 | behavior case 最低通过率 |
| `judge_required` | boolean | 决策是否要求校准后的 judge 证据 |

gate 只能基于兼容 provenance 和实际样本计算。样本不足、judge 仅 advisory、pair 被排除或 duration/token 不完整时，报告必须同时展示不确定性，不能只输出 gate 布尔值。

## Case

所有 case 必须包含：`id`、`mode`、`split`、`prompt`、`inputs`。

- `id`：与 suite id 相同的小写连字符格式，suite 内唯一。
- `mode`：`trigger` 或 `behavior`。
- `split`：`train`、`validation` 或 `holdout`。
- `prompt`：agent 可见的自然任务，不含 expected answer、assertion、rubric 或 variant 身份。
- `inputs`：相对 suite 目录的文件/目录路径数组；运行时只复制到隔离 workspace。
- `repetitions`：可选正整数。

Trigger case 额外要求 boolean `should_trigger`，不允许把模型的自我声明当作触发真相。

Behavior case 至少包含一个 `assertions` 项，或显式启用并配置 trusted verifier。candidate/baseline 使用完全相同的 prompt、input 和 runner 参数。

case 字段按 mode 闭合：trigger 不接受 `assertions`/`trusted_verifier`，behavior 不接受 `should_trigger`。assertion 字段同样按 type 闭合，任何对当前类型无意义的字段都会在运行前被拒绝。

## Assertion

每项都需要唯一 `id` 和闭合集合内的 `type`：

| Type | 必需字段 | 判断 |
| --- | --- | --- |
| `file_exists` | `path` | 目标是文件 |
| `file_absent` | `path` | 路径不存在 |
| `path_changed` | `path` | Git baseline 后该路径发生变化 |
| `path_unchanged` | `path` | Git baseline 后该路径未变化 |
| `text_contains` | `path`, `value` | UTF-8 文本包含字符串 |
| `text_excludes` | `path`, `value` | UTF-8 文本不含字符串 |
| `regex_matches` | `path`, `pattern` | Python regex 匹配文本 |
| `json_valid` | `path` | 文件是合法 JSON |
| `json_field_equals` | `path`, `value` | 指定 JSON field 等于预期值 |
| `diff_allows_only` | `allow` | 所有变化都匹配 glob allowlist |
| `diff_excludes` | `deny` | 没有变化命中 glob denylist |
| `verifier_command` | `argv` | 有界子进程退出码为 0 |

`json_field_equals.value` 必须且仅能包含 `field` 与 `equals`。`field` 可使用 JSON Pointer，例如 `/items/0/name`，或点分路径。

```json
{
  "id": "decision",
  "type": "json_field_equals",
  "path": "outputs/result.json",
  "value": {"field": "/decision", "equals": "blocked"}
}
```

`verifier_command` 不使用 shell 字符串：

```json
{
  "id": "domain-check",
  "type": "verifier_command",
  "argv": ["python", "verify.py", "outputs/result.json"],
  "cwd": ".",
  "timeout_seconds": 30
}
```

包含 verifier 时，case 必须同时设置 `"trusted_verifier": true`。命令在隔离 workspace 内运行，环境按安全 allowlist 构建，输出和时间都有上限；不要让 verifier 读取网络、用户配置或凭据。

## Outcome 语义

- `PASS`：runner 成功且对应 trigger/assertion 全部满足。
- `FAIL`：任务完成但机械要求不满足。
- `ERROR`：assertion/verifier 自身无法可靠执行。
- `unsupported`：runner capability probe 不能建立真相源。
- `inconclusive`：judge swap 冲突或证据不足。
- `unknown`/timeout：副作用状态未知，不允许隐式 retry。

单项 ERROR 必须保留，不能折叠成普通 FAIL；runner 执行成功也不代表 behavior case 通过。

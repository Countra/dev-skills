# 用户观察契约

## Suite

suite 是评估设计，不是运行配置。它只包含：

- `suite_id`、candidate、可选 baseline 和 decision question。
- `required_variants` 与必须为 true 的 `require_independent_session`。
- 正例、near-miss、behavior 三类 case；每个 case 有原始 prompt、expected observation 和 workspace 相对 inputs。

不得加入模型名称、Agent 启动方式、凭据、预算或自动重试配置。

## Packet

`se_prepare.py` 生成新目录：

- `packet.json`：source/case/input hash 和不可变 fingerprint。
- `INSTRUCTIONS.md`：用户独立会话步骤与停止边界。
- `observation-template.json`：只有 packet fingerprint、`declared_by=user` 和空 sessions。

packet 的 `execution_mode` 固定为 `user_operated_independent_session`。生成后当前会话必须停止，不得代替用户运行 case。

## 用户 Bundle

每条 session 由用户填写：

- `case_id` 与 `variant`。
- 可审计但不限定平台格式的 `session_ref`。
- `pass|fail|inconclusive` status。
- notes 与可选 workspace 内 artifact path/hash。

缺失 case 不补 `not_run` 默认记录；imported evidence 保留 `coverage.missing` 和 `partial`。

## Import

importer 依次校验：

1. packet 及每个 case fingerprint。
2. candidate/baseline 当前 tree hash，并把双方 hash 保留到 imported evidence。
3. case/variant 是否存在且不重复。
4. artifact 位于 workspace、source 外，大小与可选声明 hash 一致。
5. observed sessions 与 coverage 集合完全一致。

importer 不执行 artifact，不读取凭据，不调用 Agent，不把用户声明升级成机械事实。任一 source drift 需要生成新 packet。

## 声明边界

- `partial`：只能陈述已导入 session。
- `complete` 且包含 `inconclusive`：仍不能形成明确整体运行时表述。
- `complete` 且全部结论明确：只能陈述 packet 覆盖的 case/variant，不能外推总体触发率。

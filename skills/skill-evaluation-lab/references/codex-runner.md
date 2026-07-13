# Codex Runner

只在 suite 使用 `adapter: codex-cli`、需要诊断 capability 或解释 trace 时读取。本文描述当前 adapter 的实际边界，不代表任意 Codex CLI 版本都受支持。

## Capability Gate

普通流程不要先运行 doctor。只有 Codex live 入口不确定或失败时运行：

```text
python -u -X utf8 -B scripts/se_doctor.py --live --output <probe.json> --pretty
```

probe 不调用模型，检查：

- `codex` 可发现并能输出版本。
- `exec` 支持 ephemeral、ignore rules/config、JSONL 和 output schema。
- `debug prompt-input` 可证明 candidate skill 可见且 baseline 不可见。
- 临时 probe 目录可创建、验证和完整删除。

任一真相源无法建立时返回 `unsupported`；不要改用模型自我声明“我加载了 skill”。

## Trigger Observation

Trigger runner 只修改临时 candidate snapshot 的 body，在其中注入随机 nonce receipt 指令；生产 `SKILL.md` 和 description 保持不变。随后使用结构化 final schema 检查 receipt 是否精确匹配，公开响应契约见 `schemas/final-response.schema.json`。

这一机制区分：

- description 是否让 Codex 加载了 skill body。
- body 被加载后，模型是否按 nonce 指令返回 receipt。

nonce 不得出现在原 prompt、suite 或 source。candidate 与 baseline 的 prompt visibility 由 capability probe 先验证；无法验证时整组 trigger 结果为 unsupported。

## Behavior Run

Behavior runner 为 candidate 与 baseline 分别创建独立 workspace：

1. 复制相同 input。
2. 初始化 Git baseline，用于路径与 diff assertion。
3. candidate workspace 安装 candidate snapshot；`none` baseline 不安装 skill，snapshot baseline 安装旧快照。
4. 使用相同 prompt、model、sandbox、timeout 和 network policy 串行运行两侧。
5. 保存 JSONL、structured final、stderr、usage、provenance 与机械 assertion。
6. 运行后重算 source tree，发现 source drift 即失败关闭。

runner 只记录事实。行为结论由 assertion 和 grader 产生；一条 `codex exec` 返回 0 不等于 case 通过。

## Live Authorization

运行前先执行 `se_plan.py`，向用户展示：

- 完整 fingerprint。
- model 与 adapter。
- case/repetition/variant 矩阵。
- 最大 agent/judge 调用数和墙钟上限。
- sandbox、network 与 baseline 类型。

只有用户明确批准当前有限矩阵后，才同时传入：

```text
--fingerprint <exact-sha256> --authorize-live
```

授权不跨 fingerprint 复用。suite、source、baseline、runner、budget 或 case 变化后重新 plan；不要把一次“可以测试”解释为无限重试或新模型授权。

## Artifact Contract

run root 按 `suite_id/run_id` 隔离，已有目录不覆盖。核心证据包括：

- `run.json`：状态、fingerprint、source/lab identity、矩阵记录和预算快照；闭合契约见 `schemas/run-manifest.schema.json`。
- 每次调用的 `trace.jsonl`、`final.json`、`stderr.log` 与 output schema。
- case workspace 与 Git baseline/diff 证据。
- runner provenance：adapter、CLI、model、sandbox、network、prompt hash、lab hash、case、attempt、variant。

JSONL 出现未知 event type、failed event、无 structured final、输出越界、timeout 或终止不确定时，不推断成功。先保留 artifact，再修复 capability 或 case。

## Retry Policy

没有隐式 retry。可重跑前必须回答：

1. 上一次是否可能产生未知副作用？
2. 失败属于 runner、权限、输入、assertion 还是 skill？
3. 新运行是否仍使用完全相同 fingerprint？
4. agent run 与墙钟预算是否仍允许？

如果修复改变 suite/source/config，生成新 fingerprint 并重新授权。仅增加 timeout 也属于配置变化。

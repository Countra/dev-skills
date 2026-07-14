# 故障排查

只在主流程失败时读取本文件。先保留 error code、runId、session、target 和 report，不用模糊重试掩盖未知结果。

## Service 不可用

运行 `ev_health.py`，再检查 process-manager status 和 bounded logs。配置缺失才重新 init。不要用手写后台进程绕过 ownership。

若复制安装可初始化但启动失败，检查 service config 的 launcher 是否指向该安装内 `ev_server.py`、cwd 是否为独立 workspace、解释器是否满足 locked requirements，以及安装目录 digest 是否因 bytecode/cache 写入发生变化。不要回退到仓库固定路径。

## CDP 或 Attach 失败

确认应用以 `--remote-debugging-port=<port>` 启动，endpoint 是 literal loopback，且 probe 能返回 page target。多个 target 时显式指定；不要恢复 raw CDP fallback。Playwright 主能力缺失是 blocker。

## Session Stale

应用退出、page 关闭或 service 重启后，持久化 session 只能表示连接意图。用 `ev_sessions.py --session <name>` 检查；prepare 提供 `--cdp` 可健康重连。重复 detach 应成功且标记 already detached。

## Action 歧义或超时

- `ambiguous_locator`：改用 role/name、label、testId 或更具体的页面状态，不直接加 nth。
- `action_outcome_unknown` / `operation_timeout`：停止 run 并检查现场，不重放 mutating action。
- postcondition failed：记录实际状态，修复 assertion 或 UI 问题；不要因点击本身成功就判定通过。

## Operation 未收敛

先用 `ev_operation.py get` 读取 durable 状态，再用有界 `wait`。客户端等待超时不会自动取消服务端 operation；需要停止时显式 `cancel`。若最终为 `deadline_exceeded` 或 `unknown`，保留 run/operationId 和现场证据，禁止用新 requestId 重放同一 mutation。service 重启后 operation 记录仍应可查询，遗留 queued/running 会失败关闭而不是静默继续。

## Risk Receipt 被拒绝

receipt 过期、已消费、run/target/action fingerprint 不匹配时，重新执行 `ev_risk.py preview` 并让用户确认新的 exact fingerprint。不要复用旧 receipt、修改 action JSON 迁就 fingerprint，或把风险确认写入 action 字段。

## Screenshot 被拒绝

检查目标窗口是否渲染、viewport、最小化状态和页面加载。corrupt、零尺寸、解压失败或单色 PNG 不会进入 manifest。不要手工把失败文件加入证据。

## Knowledge Abstain

用 `ev_knowledge.py ... search --explain` 查看通道与 rejection reason。补充正确 appVersion、screenDigest、preState 或 maxRisk；若 lexical score 低，由 agent 拆分明确子目标。不要降低阈值来强行复用不相关资产。

## Knowledge Reset

`knowledge_reinitialize_required` 表示 current runtime 拒绝旧布局。先无 `--confirm` 预览 metadata-only fingerprint，确认目录后再提交 exact fingerprint。错误 fingerprint 不移动任何内容。

## Retention Apply 被拒绝

`retention_fingerprint_mismatch` 表示 preview 后候选、引用或 policy 已变化。重新运行 `ev_prune.py preview`，审核新的候选后再确认；不要关闭引用保护。默认不会自动删除 active object、decision、pending 引用或未到期 operation。

## Cleanup 失败

只停止本轮记录的 verifier service 和测试应用进程树。检查 process-manager `cleanupVerified`、`ownerEmpty`，以及 CDP endpoint 已关闭。不得按进程名批量终止用户已有实例。

---
name: electron-ui-verifier
description: 通过本机 Playwright CDP service 验证 Electron 桌面应用 UI，并产出可信截图、ARIA、DOM、console、异常、网络摘要、run report 和待批准知识资产。适用于检查已打包 Electron 可执行程序或开发版应用、复用同一 UI session 执行单步或多步流程、诊断页面故障、验证视觉或交互结果，以及沉淀经用户确认的可复用 action/workflow。
---

# Electron UI Verifier

使用常驻 verifier service 连接本机 Electron CDP。所有自动化通过 `scripts/ev_*.py` 入口完成；Playwright 是唯一 driver，不恢复 raw WebSocket/CDP fallback。

## 核心流程

1. 确认 workspace、目标 Python、Electron 可执行文件或已运行实例、loopback CDP 端口、目标 appId 和验证目标。
2. 首次使用、配置变化或环境不确定时运行 `ev_init.py`。只有 verifier service 交给 `process-manager`；Electron GUI 本体用普通前台命令启动或连接用户已有实例。
3. 多 target 不确定时先运行 `ev_probe.py`。必须用 targetId、URL、标题或显式 index 消除歧义，不能猜测目标窗口。
4. 用 `ev_prepare.py` 创建 run。提供 `--app-id` 和 `--goal` 时，prepare 会同时返回最多 3 条紧凑知识候选或明确 `abstain`。
5. 对 `reuse` 候选先检查 app/version/screen/state/risk 和 requiredParams。完整目标未命中时，由 agent 明确拆分 `--subgoal`，再用 `ev_suggest.py` 检索；不要依赖脚本硬编码拆解。
6. 复用 approved asset 时直接使用 `ev_action.py --action-id` 或 `ev_workflow.py --workflow-id`。没有安全候选时才编写新的 typed action/workflow。
7. 所有 mutating action 都要有 postconditions。歧义、actionability 失败或 outcome unknown 时停止，不自动重放点击、输入或提交。
8. 用 `ev_finalize.py --run-id` 幂等结束 run。结论只引用本轮 report 和已校验 artifact；知识候选不能替代现场证据。
9. 只有生成 pending、用户查看后明确批准，才用 exact `bundleFingerprint` 执行 `ev_persist.py approve`。拒绝则使用 `reject`。不得直接 learn、promote 或修改 canonical 文件。
10. 停止 service 和测试应用后，验证 session stale、重复 detach、`cleanupVerified:true` 与 `ownerEmpty:true`。

## 最小命令序列

```powershell
python <skill>/scripts/ev_init.py --workspace <absolute-workspace> --python <absolute-python>
python <skill>/scripts/ev_prepare.py --workspace <absolute-workspace> --session <name> --cdp http://127.0.0.1:<port> --app-id <app> --goal <goal>
python <skill>/scripts/ev_action.py --workspace <absolute-workspace> --run-id <run-id> --action <absolute-json-or-inline-json>
python <skill>/scripts/ev_finalize.py --workspace <absolute-workspace> --run-id <run-id>
python <skill>/scripts/ev_pending.py --workspace <absolute-workspace> --run-id <run-id>
```

多步流程用 `ev_workflow.py` 代替单步 action。prepare 已返回 `reuse` 时，优先传 `--workflow-id` 或 `--action-id`，不要导出或复制等价 JSON。

## 硬门禁

- 只连接 literal loopback CDP。当前 runtime 不接受 remote CDP。
- verifier 内部状态只写 workspace 下 `.harness/electron-ui-verifier/`；不得读取或写入应用默认 profile、cookie、token、storage、请求头或请求体。
- 可执行文件、workspace、config、JSON 文件和显式导出路径使用绝对路径。
- locator 默认 strict。CSS 与 `nth` 是高风险定位，必须有明确理由和现场证据。
- 参数使用完整占位符 `${name}` 和 parameterSchema；binding 只在内存使用，不写 journal、report 或 canonical asset。
- 截图必须通过 PNG 结构、尺寸和像素变化检查后才进入 evidence manifest。
- run 必须先 prepare，操作只追加到该 run，最终只 finalize 一次；重复 finalize 返回同一 report/pending。
- 只读 run 不生成可执行 pending。mutating path 未通过 postcondition、证据失效或风险未确认时禁止批准。
- 旧知识布局不读取、不导入、不转换。只可先预览 fingerprint，再用 exact confirmation 执行 direct reset。
- 最终汇报 runId、session/target、知识 decision、复用 assetId 或 abstain 原因、实际步骤、report、artifact、pending/decision、清理状态和未覆盖范围。

## 按需参考

- 首次配置、service、session、process-manager 或 cleanup：读取 [references/server.md](references/server.md)。
- 编写 locator、action、assertion 或诊断步骤：读取 [references/actions.md](references/actions.md)。
- 编排多步 run、失败控制和 finalize：读取 [references/workflow.md](references/workflow.md)。
- 检索、abstain、状态组合、参数、reset 或批准：读取 [references/knowledge.md](references/knowledge.md)。
- 发生 attach、stale、timeout、证据或知识错误：读取 [references/troubleshooting.md](references/troubleshooting.md)。

不要在普通任务中预先加载全部 references。

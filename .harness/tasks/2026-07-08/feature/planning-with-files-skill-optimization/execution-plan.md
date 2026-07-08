# 执行计划：吸收 planning-with-files 优秀机制优化 dev-skills

## 执行控制快照（Execution Control Snapshot）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- completed

当前阶段（Current stage）:

- Completed

已完成阶段（Completed stages）:

- Planning research and plan drafting
- Stage 1
- Stage 2
- Stage 3
- Stage 4
- Stage 5
- Stage 6
- Stage 7 deferred
- Stage 8

剩余阶段（Remaining stages）:

- none

下一步自动动作（Next automatic action）:

- none

当前停止条件（Current stop condition）:

- completed

状态来源（State source of truth）:

- execution-plan.md

执行方（Executor）:

- 当前已获用户批准，按 `complex-coding-executor` 执行阶段规则继续实施。

## 执行契约（Execution Contract）

```json
{
  "contract_version": 1,
  "task_id": "2026-07-08-feature-planning-with-files-skill-optimization",
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "approval_status": "approved",
  "approved_contract_hash": "external:attestation.json",
  "current_stage_id": "Completed",
  "remaining_stage_ids": [],
  "stop_condition": "completed",
  "commit_authorization": "not_authorized",
  "ledger_policy": "append-only-after-approval",
  "single_writer": "current executor session",
  "reapproval_required": false
}
```

契约规则（Contract rules）:

- 本节是 executor 可读的机器字段；`Execution Control Snapshot` 和 `Execution Control` 用于人类恢复和审计。
- `approved_contract_hash` 引用外部 `attestation.json`，避免把完整 plan hash 写入 plan 后造成自指哈希漂移。
- 修改 approved scope、stage 边界、验证策略、风险等级、工具授权或提交策略时，必须进入 `Plan Amendment Gate`。

## 目标条件（Goal Condition）

- 所有 approved stages 均为 complete。
- `harness_exec_check.py --mode final` 或等价最终门禁通过。
- 无 open blocking decision、无未关闭 blocking/major review finding。
- 必需验证已执行，或无法执行项已记录原因、影响和替代证据。
- 提交授权状态明确；未授权时不得提交，但必须记录原因。

## 规划循环协议（Planning Loop Protocol）

- managed 计划默认拆为 3-7 个可独立验证阶段；更多阶段必须说明原因，本计划因分阶段落地脚本、文档和验证而拆为 8 阶段。
- 调研、浏览、搜索或查看多个来源后，关键 findings 必须写入 `Context`、`Reference Learning Matrix` 或 artifacts。
- 重大决策前重读目标、约束、Options、Decision、影响面和 reapproval triggers。
- rejected options 必须记录放弃原因，避免上下文压缩后重复走回头路。
- Readiness 前必须重新运行 `Plan Quality Gate`、`Plan Self-Review` 和 `Readiness Gate`。

## 执行循环协议（Executor Work Loop）

- 每个阶段开始先读取 `Execution Contract`、`Resume Packet`、Stage Contract 和上一阶段 findings。
- 每次阶段动作后更新 ledger/progress；没有实质进展但需要保持长任务循环时写 heartbeat。
- 失败动作必须记录 attempt、命令或工具、失败原因、影响和下一策略；不得静默重复同一失败动作。
- Stage Transition Gate 通过且仍有 pending stage 时，下一动作必须是 `continue Stage N`。
- 只有满足 `Goal Condition` 后才能进入最终交付。

## 问题定义（Problem）

目标（Goal）:

- 深入吸收 `D:\Item\vibe_coding\Ref\planning-with-files` 中适合当前 `dev-skills` 的持久文件化规划机制，形成可批准、可执行、可恢复的优化方案。

非目标（Non-goals）:

- 不超出已批准范围修改无关 skill；提交仍需单独授权。
- 不照搬参考项目的多 IDE 分发结构。
- 不引入新的重型运行时框架或数据库。
- 不把 `planning-with-files` 直接变成第五个独立 skill。

验收标准（Acceptance）:

- `.harness/tasks/2026-07-08/feature/planning-with-files-skill-optimization/execution-plan.md` 已完整记录研究结论、候选方案、决策、影响面、阶段计划、验证、风险和审批状态。
- 方案明确说明当前 `dev-skills` 自身 skill 能力、参考项目可吸收机制、不适合吸收机制和落地路径。
- 每个实施阶段都有目标、做法、原因、位置、参考、验证、风险、回滚和 Stage Contract。
- `Plan Quality Gate`、`Plan Self-Review` 和 `Readiness Gate` 完成后停止，等待用户批准。

约束（Constraints）:

- 遵守用户提供的全局规则：中文注释、先读上下文、最小变更、长内容分段写入、错误处理、真实验证说明和提交信息格式。
- 遵守当前 `complex-coding-planner`：managed 任务先规划，Readiness Gate 后等待用户明确批准。
- 实施批准不等于提交授权；提交必须单独授权。
- 同一仓库 Git 命令必须串行。

待确认项（Open uncertainties）:

- 无 blocking 问题。hook 是否进入第一轮实施可在 Stage 7 评估后决定；默认不作为第一批强制落地项。

## 上下文（Context）

本地代码（Local code）:

- `skills/complex-coding-planner/SKILL.md`：当前 planner 明确负责 managed 任务规划、环境/Git/验证/Readiness Gate、Plan Self-Review，并禁止直接实现。
- `skills/complex-coding-planner/references/planning-workflow.md`：当前规划规范已要求 `Execution Control Snapshot`、`Plan Quality Gate`、`Plan Self-Review`、`Readiness Gate` 和用户审批。
- `skills/complex-coding-planner/templates/execution-plan.md`：当前模板已经包含 planner/executor 交接契约、Git 串行、Process Manager Gate、Stage Gate、Resume Summary 和 Commit Log。
- `skills/complex-coding-executor/SKILL.md`：当前 executor 只消费已批准计划，负责阶段门禁、验证、review、Git/process 规则、changelog、提交授权和最终交付。
- `skills/complex-coding-executor/scripts/harness_exec_check.py`：当前检查脚本能阻断未批准计划、open decision、remaining stages final delivery，但主要是 Markdown 关键词和 active-task 字段检查，尚无哈希证明、ledger 对账和路径 containment。
- `skills/complex-coding-planner/scripts/harness_plan_check.py`：当前 planner 检查脚本关注章节完整性、实施阶段术语和门禁顺序，尚未检查 Execution Contract、批准摘要机器字段或计划变更触发条件的结构化状态。
- `evals/complex-coding-planner/expected.yaml` 和 `evals/complex-coding-executor/expected.yaml`：当前 eval 覆盖审批、阶段继续、提交授权、process-manager 和 Git 串行，但缺少篡改、active-task 越界、ledger、opt-out、session isolation 等负例。
- `skills/process-manager`：当前项目已有长期进程专用 skill；本优化不应回退到 shell 后台启动。
- `skills/electron-ui-verifier`：当前项目已有复杂验证型 skill，体现“脚本 + references + evidence”的风格，可作为新增状态检查脚本的组织参考。

本地文档（Local docs）:

- `.harness/active-task.json`：当前指向已完成的 `complex-coding-planner-executor-split`，本任务需要创建新 active task。
- `.harness/environment.md`：记录主分支 `main`、harness 分支策略和 Git 串行规则，但仍包含旧 `E:\work\...` 路径和 `complex-coding-harness` 历史描述，应在实施 Stage 1 校准。
- `README.md`：仍主要描述旧 `complex-coding-harness`，与当前 `complex-coding-planner` / `complex-coding-executor` 拆分状态不一致。
- `.gitignore`：已忽略 `.harness/tasks/**/artifacts|logs|tmp|scratch`，但尚未覆盖未来可能新增的 `.harness/tasks/**/ledger*.jsonl`、attestation 或 session runtime 文件。
- `CHANGELOG.md`：已有 2026-07-06 planner/executor 拆分记录，可作为后续 changelog 风格参考。

外部来源（External sources）:

- GitHub `OthmanAdi/planning-with-files`：页面显示项目为 public，约 25k stars、2.1k forks、296 commits；README 描述其为持久文件化规划 skill，使用 `task_plan.md`、`findings.md`、`progress.md` 在磁盘保留上下文，并支持 opt-in completion gate 和 60+ agents。
- 本地参考仓库 `D:\Item\vibe_coding\Ref\planning-with-files\skills\planning-with-files\SKILL.md`：核心规则包括恢复上下文、创建三类规划文件、2-Action Rule、Read Before Decide、Update After Act、3-Strike Error Protocol 和 5-Question Reboot Test。
- 本地参考仓库 `templates/task_plan_autonomous.md`：v3 模板新增 Run Contract、Mode、Gate cap、Stall window、Attestation policy、Single-writer rule、DependsOn、Owner、AcceptanceCheck 和 Model Routing。
- 本地参考仓库 `scripts/resolve-plan-dir.sh`：通过 `PLAN_ID`、`.planning/.active_plan`、newest plan dir 和 legacy fallback 解析 active plan，并包含 slug 校验和 realpath containment guard。
- 本地参考仓库 `scripts/check-complete.sh`：默认 advisory，`--gate` 仅在 gated mode、存在 in_progress、未处于 stop_hook_active、未超过 cap、ledger 有进展时 block；避免“未完成即强拦”的用户体验问题。
- 本地参考仓库 `scripts/attest-plan.sh`：对 plan 内容生成 SHA-256，计划被改动后 hook 拒绝注入 plan body。
- 本地参考仓库 `scripts/ledger-append.sh` 和 `scripts/ledger-summary.sh`：使用 append-only JSONL 记录 progress、phase_complete、error、gate_block、attest、note，并生成无时间戳的稳定摘要。
- 本地参考仓库 `.codex/hooks`：Codex 集成为薄适配层，核心逻辑尽量在脚本中；部分 hook 降级为 systemMessage/advisory。
- 本地参考仓库 `tests/`：覆盖 gate、ledger、plan attestation、resolve-plan-dir、containment、planning disabled opt-out、Codex session isolation、frontmatter parity 和 script sync。
- 本地参考仓库 `commands/plan-goal.md`：把文件化计划转换为可衡量的终止条件，要求所有 phase 完成且 completion check 返回全部完成。
- 本地参考仓库 `commands/plan-loop.md`：定义长任务循环节奏，定期重读 plan/progress、检查完成状态、记录 heartbeat 或推进下一 phase。
- 本地参考仓库 `commands/status.md`：提供压缩后的任务状态视图，快速回答当前 phase、phase 计数、错误数量和规划文件是否存在。
- 本地参考仓库 `docs/workflow.md` 和 `docs/quickstart.md`：强调先建计划、边做边记录 findings/progress、决策前重读计划、phase 完成后更新状态、错误必须记录且不能重复同一失败动作。
- 本地参考仓库 `docs/workflow.md` 的 topic handoff：长主题用 handoff 文件保留运行状态、检查方式、已改内容、分支/提交/PR 和剩余风险。
- 本地参考仓库 `docs/troubleshooting.md`：覆盖规划文件位置错误、hook 不触发、frontmatter/安装缓存、Stop hook 误拦、Windows 兼容等流程故障。

用户约束（User constraints）:

- 用户明确要求研究本地完整仓库 `D:\Item\vibe_coding\Ref\planning-with-files` 和 GitHub 项目 `OthmanAdi/planning-with-files`。
- 用户明确要求结合当前 `dev-skills` 内的 skill 制定优化方案。
- 用户明确要求按当前 `complex-coding-planner` 规则生成 `.harness` 内详细规划文档。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 本任务属于 managed planning-only | confirmed | 用户要求生成 `.harness` 规划文档 | 必须停止等待审批 |
| 当前 planner/executor 已有强审批和执行分治 | read | planner/executor `SKILL.md` 和 workflow | 优化应保留现有 split |
| 当前检查脚本偏结构关键词检查 | read | `harness_plan_check.py`、`harness_exec_check.py` | 需要机器可验证状态层 |
| README 和 environment 存在旧 harness/旧路径漂移 | read | `README.md`、`.harness/environment.md` | Stage 1 先校准文档和状态 |
| planning-with-files 的核心价值是文件状态运行时 | read/external | 本地参考仓库、GitHub README | 可吸收 resolver、ledger、attestation、gate |
| 多 IDE 分发和 root 三文件模式不适合直接照搬 | assumption/read | 当前 repo 结构、参考项目目录 | 应采用 `.harness` 混合方案 |
| hook 应后置为可选阶段 | assumption/read | `.codex/hooks` 与 canonical scripts 差异 | 降低误拦截和宿主耦合风险 |

## 候选方案（Options）

### 方案 A：仅更新文档和模板（Minimal Change）

- 做法（How）: 只把参考项目经验写入 planner/executor 文档和模板，不新增机器状态层。
- 优点（Pros）: 改动小，风险低。
- 缺点（Cons）: 仍主要依赖模型自觉，无法解决状态漂移、计划篡改和阶段误停。
- 风险（Risks）: 文字规则继续膨胀，executor 检查脚本仍偏浅。
- 验证（Validation）: quick_validate、文档检索、planner check。
- 回滚（Rollback）: revert 文档更新。

### 方案 B：混合增强 `.harness` 机器层（Structured Change）

- 做法（How）: 保留 planner/executor 分治，吸收参考项目 resolver、attestation、ledger、gated checks、opt-out、session isolation 和负例测试思想。
- 优点（Pros）: 复用当前 skill 强审批能力，同时补齐文件状态运行时。
- 缺点（Cons）: 需要新增脚本和测试，实施阶段较多。
- 风险（Risks）: 若一次性引入 hook，可能造成噪音或误拦截。
- 验证（Validation）: 脚本单测、负例 smoke、planner/executor eval、真实计划 fixture。
- 回滚（Rollback）: 可按脚本层、模板层、hook 层逐段回滚。

### 方案 C：完整照搬 planning-with-files 模式（Full Port）

- 做法（How）: 引入 `.planning/`、`task_plan.md`、`findings.md`、`progress.md`、hooks 和多 IDE 目录。
- 优点（Pros）: 接近参考项目原始能力。
- 缺点（Cons）: 与当前 `.harness` 主契约、planner/executor 分治和 repo 安装模式冲突。
- 风险（Risks）: 多套状态源并存，增加维护和触发复杂度。
- 验证（Validation）: 需要大量兼容测试和安装测试。
- 回滚（Rollback）: 成本高。

## 决策（Decision）

选择方案（Chosen option）:

- 方案 B：混合增强 `.harness` 机器层。

原因（Why）:

- 当前 `dev-skills` 已有更强的审批、Git、process-manager 和执行交接规则；需要补的是机器可验证的状态层，而不是替换整体架构。

影响（Impact）:

- 将影响 planner/executor 文档、模板、检查脚本、eval、README、CHANGELOG 和 `.gitignore` 运行产物规则。

可逆性（Reversibility）:

- 中等。脚本层和模板层可分阶段回滚；hook 层作为可选阶段，默认不影响首批落地。

变更条件（Change conditions）:

- 如果新增机器层要求大幅改变 `.harness/tasks` 结构，必须重新审批。
- 如果 hook 行为会影响普通 direct 任务，必须延后到单独方案。

方案变更触发条件（Reapproval triggers）:

- 改变 planner/executor 职责边界。
- 改变 active-task schema 的兼容语义。
- 自动执行 plan 中的验证命令或 AcceptanceCheck。
- 引入网络依赖、后台服务或第三方包。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | planner/executor 脚本 CLI、future hook adapter、active-task 字段解释 | medium | `--help`、smoke、fixture | yes |
| 数据结构（Data model） | yes | `execution-plan.md` Execution Contract、`.harness/tasks/**/ledger*.jsonl`、attestation 文件 | medium | JSON/JSONL 解析、hash/tamper tests | yes |
| 前端交互（Frontend interaction） | no | 不涉及 UI | low | not-applicable | no |
| 配置/环境（Config/environment） | yes | `.harness/environment.md`、`.gitignore`、README install notes | medium | 文档检索、diff check | yes |
| 兼容性（Compatibility） | yes | 旧 active-task、旧 execution-plan、planner/executor split | high | legacy fixture、completed task fixture、opt-out fixture | yes |
| 测试（Tests） | yes | evals、smoke fixtures、脚本单测 | high | planner/executor expected、负例测试 | yes |
| 文档（Documentation） | yes | SKILL.md、references、templates、README、CHANGELOG | high | quick_validate、全文检索 | yes |

## 参考项目吸收矩阵（Reference Learning Matrix）

| planning-with-files 机制 | 参考项目价值 | dev-skills 转换方式 | 采纳结论 |
| --- | --- | --- | --- |
| `task_plan.md` / `findings.md` / `progress.md` | 用磁盘承载长期记忆 | 保留单一 `execution-plan.md` 主契约，必要时增加 `artifacts/research-notes.md`，不新增根目录三文件 | partial |
| FIRST restore / session catchup | 上下文压缩后恢复更稳 | executor 恢复流程增加 `resume packet` 和 ledger summary 对账 | adopt |
| 2-Action Rule | 防止浏览/视觉发现丢失 | planner 对研究类任务要求将关键发现写入 `Context` 或 artifacts | adopt-adjusted |
| 3-Strike Error Protocol | 避免重复失败动作 | executor 验证失败和脚本失败流程增加 attempt 记录和替代路径 | adopt |
| 5-Question Reboot Test | 快速判断能否恢复任务 | 映射到 `Resume Summary` 必填字段和 ledger summary | adopt |
| Plan phase design | 把复杂任务拆成可恢复 phase | planner workflow 增加“3-7 个阶段、每阶段有目标/发现/退出条件”的硬规则 | adopt-adjusted |
| Work-and-document loop | 防止研究、决策、执行证据只留在上下文 | planner/executor 增加“研究后写 findings、重大决策前重读计划、执行后写 ledger/progress”的循环协议 | adopt |
| `/plan-goal` | 从计划导出终止条件 | executor final gate 增加 `goal_condition`，要求所有 approved stage 完成、final check 通过、验证证据齐全 | adopt |
| `/plan-loop` | 长任务自动持续推进 | executor workflow 增加 `loop_tick`：重读 plan、运行 transition check、记录 heartbeat、继续下一未阻塞阶段 | adopt-adjusted |
| `/status` | 快速恢复和对外汇报 | 增加 `harness_status` 能力或 `harness_exec_check.py --mode status`，输出 current stage、stage counts、blocking reason、latest evidence | adopt |
| Topic handoff | 长子主题跨上下文移交 | 在 task artifacts 下定义 `handoffs/<topic>.md`，由 `Implementation Progress` 作为索引，不新增根目录三文件 | adopt-adjusted |
| Troubleshooting guide | 处理 hook、路径、缓存、Windows 等真实故障 | 文档增加故障定位表，优先覆盖 active-task stale、wrong task dir、attestation mismatch、HARNESS_DISABLED | adopt |
| `Run Contract` | 无人值守任务的终止和所有权规则落盘 | 新增 `Execution Contract`，记录 mode、approval hash、ledger policy、single-writer rule | adopt |
| `DependsOn` / `Owner` / `AcceptanceCheck` | 阶段依赖、责任和验收可表达 | Stage Contract 增加 `depends_on`、`owner`、`acceptance_check`；首轮不自动执行命令 | adopt-adjusted |
| active plan resolver | 多计划/多会话不读错状态 | 新增 `harness_task_resolver.py`，解析 active-task 并做 workspace containment | adopt |
| attestation | 计划批准后防止静默篡改 | 新增 `harness_attest_plan.py`，批准后记录 plan hash，executor preflight 校验 | adopt |
| append-only ledger | 机器可读进度、gate stall 检测 | 新增 `harness_ledger_append.py` 和 `harness_ledger_summary.py` | adopt |
| gated Stop | 长任务不能在 in_progress 阶段误停 | 先落地 `harness_exec_check.py --mode transition/final` 强化；hook gate 后置 | adopt-adjusted |
| `PLANNING_DISABLED=1` | one-shot/CI 不被计划劫持 | 新增 `HARNESS_DISABLED=1` 或等价 opt-out；direct 任务默认不消费 active task | adopt |
| session attach | 同 cwd 多会话隔离 | 可新增 `.harness/sessions/<id>.attached`，首轮作为可选增强 | adopt-later |
| nonce delimiter / hook injection | 减少注入和 delimiter 混淆 | 不做第一批；若引入 hook，再结合 attestation 和最小注入 | defer |
| 多 IDE 目录同步 | 支持 60+ agents 分发 | 当前 repo 不做多 IDE 镜像，只保留 Codex skill 源码 | reject |
| 每次 PreToolUse 大段注入 | 高频提醒计划 | 对 Codex 容易噪音和 token 成本高，首轮不采用 | reject |

## 当前 skill 能力与优化目标

当前能力:

- `complex-coding-planner` 已能强制复杂任务先调研、形成方案、完成质量门禁、自查和 Readiness Gate。
- `complex-coding-executor` 已能要求已批准计划、阶段门禁、run-to-completion、验证、review、Git 串行、process-manager 和最终交付证据。
- `process-manager` 已承担长期进程管理，避免 executor 自制后台启动。
- `electron-ui-verifier` 已形成“脚本 + evidence + knowledge”的复杂验证范式，可作为文件化证据设计参考。

主要短板:

- `execution-plan.md` 中多处状态重复，缺少一个机器可读的批准和执行 contract。
- `active-task.json` 与 `execution-plan.md` 冲突时只靠文字规则，缺少 resolver 和 containment 检查。
- 执行进度、验证和阶段转移缺少 append-only 机器日志，恢复时依赖 Markdown 表格。
- 计划批准后没有 hash 证明，executor 无法判断计划是否被静默改动。
- 规划流程虽有 Stage Contract，但缺少明确的“研究后记录 findings、重大决策前重读计划、阶段完成后更新证据”的循环协议。
- 执行流程缺少 `/plan-loop` 类似的 tick 机制，长任务中断或长时间无进展时不容易判断应继续、阻断还是补证据。
- 当前缺少 `/status` 类似的压缩状态视图，恢复时需要通读大计划，不利于上下文压缩后的快速接手。
- 长子主题缺少 topic handoff 载体，复杂实现中的专项研究、运行状态和剩余风险容易散落在正文或对话中。
- 流程故障排查文档不足，wrong task dir、stale active-task、attestation mismatch、hook/advisory 行为和 Windows 路径问题尚未系统化。
- 检查脚本负例覆盖不足，未覆盖 `0/0 stage`、篡改、stale completed task、wrong task dir、opt-out、session attach。

预期效果:

- 从“高质量文字协议”升级为“可恢复、可审计、可机器阻断的长期 coding 协议”。
- 上下文压缩后能通过 resolver、ledger summary 和 Resume Summary 快速恢复。
- planner 能把调研、方案决策和阶段拆分沉淀为稳定证据，减少“只在上下文里想清楚”的隐性状态。
- executor 能按 loop tick 连续推进：重读计划、检查 transition、记录进展或阻塞原因、进入下一阶段。
- 用户能通过 status summary 快速看到当前阶段、剩余阶段、最新验证和阻塞点。
- 未批准、被篡改、状态冲突、remaining stage 未完成时更难误执行或误最终交付。
- 保持 planner/executor 现有职责边界，不因引入参考项目而新增第二套计划系统。

## 不采纳清单（Non-Adopted Ideas）

- 不创建项目根目录 `task_plan.md`、`findings.md`、`progress.md`，避免与 `.harness/tasks/**/execution-plan.md` 双主契约冲突。
- 不复制 `.claude-plugin`、`.cursor`、`.gemini`、`.kiro`、`.opencode` 等多 IDE 分发目录。
- 不在第一阶段启用每次 tool call 的计划注入。
- 不让 hook 默认硬拦所有未完成计划；只允许显式 gated mode 且满足保护条件后拦截。
- 不从 Markdown `AcceptanceCheck` 自动执行任意命令；只把它作为人工/脚本验证提示，除非后续增加 allowlist 和用户授权。
- 不引入第三方包、数据库或后台服务来管理 `.harness` 状态。

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：状态、命名和环境校准

目标（Goal）:

- 让当前 repo 文档和 `.harness` workspace 状态与 planner/executor split 保持一致，为后续机器层提供干净基线。

做法（How）:

- 更新 `README.md` 中旧 `complex-coding-harness` 描述，改为 `complex-coding-planner`、`complex-coding-executor`、`process-manager`、`electron-ui-verifier` 当前结构。
- 校准 `.harness/environment.md` 中旧 `E:\work\...` 路径和历史 harness 描述；保留历史事实，但明确当前 workspace 为 `D:\Item\vibe_coding\dev-skills`。
- 复查 `.gitignore` 是否需要新增 ledger、attestation、sessions、runtime summary 等运行产物忽略规则。
- 保持旧 `.harness/tasks` 历史计划不迁移、不重写。

原因（Why）:

- 当前 README 和 environment 漂移会误导 planner/executor 继续引用旧 skill 名称和旧路径。

位置（Where）:

- 文件/模块（Files/modules）: `README.md`、`.harness/environment.md`、`.gitignore`
- API/配置（APIs/configs）: `.harness` workspace 状态说明
- 测试/文档（Tests/docs）: 文档检索、diff check

参考来源（References）:

- 当前 `skills/` 实际目录。
- `.harness/environment.md` 当前 Git 和 artifact policy。

验证（Validation）:

- 检索旧 `complex-coding-harness`，确认仅保留历史 changelog、历史任务或必要兼容说明。
- `git -c diff.autoRefreshIndex=false diff --check`

风险和回滚（Risks and rollback）:

- 风险: 环境文档改动误删历史事实。
- 回滚: revert 本阶段文档改动；旧任务记录不动。

阶段契约（Stage Contract）:

- 范围（Scope）: 文档和 workspace 状态校准。
- 允许修改（Allowed changes）: README、environment、gitignore。
- 禁止修改（Forbidden changes）: skill 运行逻辑、历史任务正文批量迁移。
- 进入条件（Entry checks）: 用户批准本计划；工作区状态已确认。
- 退出条件（Exit checks）: 当前结构和路径在文档中一致。
- 必需验证（Required validation）: 文档检索、diff check。
- 是否预期提交（Commit expected）: 仅在用户单独授权提交后。

### 阶段 2（Stage 2）：Execution Contract、规划循环和目标条件

目标（Goal）:

- 在 `execution-plan.md` 模板中新增紧凑、机器可读的执行契约，并把规划循环、执行循环和最终目标条件写成可检查规则。

做法（How）:

- 在 planner 模板靠前位置新增 `Execution Contract` 代码块或表格，字段包括 `contract_version`、`task_id`、`execution_mode`、`overall_status`、`approval_status`、`approved_contract_hash`、`current_stage_id`、`remaining_stage_ids`、`stop_condition`、`commit_authorization`、`ledger_policy`、`single_writer`、`reapproval_required`。
- 在 planner workflow 中要求 Plan Approval 写入 approval scope、hash 生成策略和 reapproval triggers。
- 在 planner workflow 中新增 `Planning Loop Protocol`：创建 managed 计划后先拆 3-7 个阶段；调研类动作必须把关键 findings 写入 Context 或 artifacts；重大决策前重读目标、约束、Options 和 Decision；阶段完成必须补充验证证据和 remaining stages。
- 在模板中新增 `Goal Condition` 字段：只有所有 approved stages complete、final gate 通过、无 open blocking decision、必需验证证据齐全、提交授权状态明确时，才允许 final delivery。
- 在 executor workflow 中新增 `Executor Work Loop`：每个阶段开始先读取 Execution Contract、Resume Packet、Stage Contract 和上一阶段 findings；执行后写 ledger/progress；失败后记录 attempt 和替代路径；transition check 通过后进入下一阶段。
- 在 executor workflow 中要求 preflight 校验 contract 与 active-task 摘要一致。
- 保留现有 `Execution Control Snapshot` 和 `Execution Control`，但说明机器字段以 `Execution Contract` 为准，其他段落用于人类恢复和审计。

原因（Why）:

- 参考项目 `Run Contract`、`/plan-goal` 和 planning loop 证明，长期任务不仅需要批准证明，还需要可恢复的工作节奏和明确完成条件。

位置（Where）:

- 文件/模块（Files/modules）: `skills/complex-coding-planner/templates/execution-plan.md`、planner/executor workflow。
- API/配置（APIs/configs）: `Execution Contract` schema。
- 测试/文档（Tests/docs）: planner check、executor preflight fixture。

参考来源（References）:

- `planning-with-files/templates/task_plan_autonomous.md` 的 Run Contract。
- `planning-with-files/commands/plan-goal.md`
- `planning-with-files/docs/workflow.md`
- `planning-with-files/docs/quickstart.md`
- 当前 `execution-plan.md` 的 Execution Control Snapshot。

验证（Validation）:

- `harness_plan_check.py` 识别并校验 contract 必填字段。
- 未批准计划 fixture 应缺少 `approved_contract_hash`，executor preflight fail。
- 缺少 `Goal Condition`、`Planning Loop Protocol` 或 `Executor Work Loop` 的新模板 fixture 应 fail。

风险和回滚（Risks and rollback）:

- 风险: 模板过重，影响可读性。
- 回滚: 保留旧字段，只禁用机器 contract 校验。

阶段契约（Stage Contract）:

- 范围（Scope）: contract schema、目标条件、规划/执行循环、模板和 workflow 说明。
- 允许修改（Allowed changes）: planner/executor 文档和检查脚本。
- 禁止修改（Forbidden changes）: 自动批准、自动执行命令。
- 进入条件（Entry checks）: Stage 1 完成。
- 退出条件（Exit checks）: 新模板可被 planner check 通过，且 goal condition 和 loop protocol 可被脚本识别。
- 必需验证（Required validation）: planner check、executor preflight negative fixture、missing-loop-protocol negative fixture。
- 是否预期提交（Commit expected）: 仅在用户单独授权提交后。

### 阶段 3（Stage 3）：task resolver、路径 containment 和 opt-out

目标（Goal）:

- 新增 `.harness` active task 解析层，避免读错任务、越界读取或 one-shot 任务被历史 active task 劫持。

做法（How）:

- 新增共享脚本，例如 `skills/complex-coding-executor/scripts/harness_task_resolver.py`，或在 planner/executor 各自脚本中复用同一实现。
- resolver 读取 `.harness/active-task.json`，解析 `task_dir`，要求 canonical path 位于 workspace root 下，且存在 `execution-plan.md`。
- 拒绝 path separator 注入、空 task_dir、completed task 被当作 executable task、active-task 与 plan task_id 不一致。
- 支持 `HARNESS_DISABLED=1`：所有 planner/executor guard 在该变量存在时只做 advisory 或直接退出，不修改 plan。
- 预留 session attach：`.harness/sessions/<session_id>.attached`，首批可只在文档中定义，后续 hook 适配再启用。

原因（Why）:

- 参考项目 resolver 的 slug 校验和 containment guard 能显著降低 stale plan、越界路径和多计划串扰风险。

位置（Where）:

- 文件/模块（Files/modules）: planner/executor `scripts/`、`.gitignore`。
- API/配置（APIs/configs）: `HARNESS_DISABLED=1`、active-task 解析规则。
- 测试/文档（Tests/docs）: resolver unit/smoke tests。

参考来源（References）:

- `planning-with-files/scripts/resolve-plan-dir.sh`
- `tests/test_resolve_plan_dir.py`
- `tests/test_containment.py`
- `tests/test_planning_disabled_optout.py`

验证（Validation）:

- 正例：合法 active task resolves。
- 负例：缺少 plan、越界路径、completed task executable、空 task_dir、`HARNESS_DISABLED=1`。

风险和回滚（Risks and rollback）:

- 风险: 旧任务 plan 缺少新字段导致 resolver 过度失败。
- 回滚: 对旧任务进入 legacy advisory mode，只对新 contract 强校验。

阶段契约（Stage Contract）:

- 范围（Scope）: resolver、opt-out、containment。
- 允许修改（Allowed changes）: scripts、workflow、eval fixtures。
- 禁止修改（Forbidden changes）: 大规模迁移历史任务。
- 进入条件（Entry checks）: Stage 2 contract 字段确定。
- 退出条件（Exit checks）: resolver 正负例通过。
- 必需验证（Required validation）: py_compile、resolver smoke。
- 是否预期提交（Commit expected）: 仅在用户单独授权提交后。

### 阶段 4（Stage 4）：append-only ledger、loop tick、status summary 和 gated checks

目标（Goal）:

- 引入机器可读运行记录和执行循环控制，让阶段转移、恢复、状态汇报和最终交付能对账，而不是只依赖 Markdown 表格。

做法（How）:

- 新增 `harness_ledger_append.py`：事件类型至少包括 `plan_created`、`plan_approved`、`stage_started`、`stage_completed`、`validation_passed`、`validation_failed`、`review_finding`、`amendment_requested`、`blocked`、`final_ready`。
- 新增 `harness_ledger_summary.py`：输出稳定形状摘要，包含 entries、stages complete/total、current stage、last event per actor、last blocking reason、last heartbeat，不输出任意长文本。
- 新增 `harness_status.py`，或在 `harness_exec_check.py` 增加 `--mode status`：输出 current stage、stage counts、open decisions、latest validation、blocking reason、next action 和 plan/ledger 文件存在性。
- 在 executor workflow 中新增 `loop_tick` 规则：每次恢复或阶段间隔推进时重读 plan、运行 preflight/transition、若没有实质进展则写 heartbeat，若阶段完成则更新 status 并进入下一未阻塞阶段。
- `loop_tick` 必须遵循 `goal_condition`：所有阶段完成且 final gate 通过才可停止；否则只能继续、请求 Plan Amendment 或记录 blocked reason。
- executor workflow 要求每个 Stage Entry/Exit/Transition 写 ledger。
- `harness_exec_check.py --mode transition/final` 增加 ledger 对账：remaining stage 不为空不得 final；final 必须存在每阶段 review/validation/stage_completed 证据。
- `Resume Summary` 增加 `resume_packet` 字段，由 ledger summary 和 Execution Contract 共同支持。
- gated check 先作为 CLI gate，不直接 hook；满足条件后可输出 block reason。

原因（Why）:

- 参考项目 ledger、`/plan-loop` 和 `/status` 解决了进度检测、stall detection、状态汇报和上下文恢复问题；当前项目缺少 append-only 机器事实层和循环推进协议。

位置（Where）:

- 文件/模块（Files/modules）: executor scripts、planner/executor workflow、`.gitignore`。
- API/配置（APIs/configs）: ledger JSONL schema。
- 测试/文档（Tests/docs）: JSONL 解析、stable summary、transition/final negative tests。

参考来源（References）:

- `planning-with-files/scripts/ledger-append.sh`
- `planning-with-files/scripts/ledger-summary.sh`
- `planning-with-files/scripts/check-complete.sh`
- `planning-with-files/commands/plan-loop.md`
- `planning-with-files/commands/status.md`
- `tests/test_gate.py`
- `tests/test_ledger.py`

验证（Validation）:

- ledger append 生成合法 JSONL。
- summary 连续两次输出稳定。
- status mode 在缺失 plan、缺失 ledger、存在 blocking reason、全部完成四类 fixture 下输出稳定字段。
- loop tick 在未完成阶段存在时不得 final，在阶段完成时能指向下一阶段。
- final 缺少 validation/review/stage_completed 证据时 fail。
- remaining stage 存在时 final fail。

风险和回滚（Risks and rollback）:

- 风险: ledger 与 Markdown 表格双写导致不一致。
- 缓解: `execution-plan.md` 仍为主契约；ledger 是机器证据，冲突时 executor 停止并要求修正。
- 回滚: 停用 ledger gate，保留 Markdown 表格路径。

阶段契约（Stage Contract）:

- 范围（Scope）: ledger、summary、status、loop tick、transition/final gate。
- 允许修改（Allowed changes）: scripts、workflow、eval fixtures。
- 禁止修改（Forbidden changes）: 自动修改用户代码或自动提交。
- 进入条件（Entry checks）: resolver 可定位当前任务。
- 退出条件（Exit checks）: ledger、status、loop tick 正负例通过。
- 必需验证（Required validation）: py_compile、JSONL parse、summary stability、status fixture、loop tick fixture、exec check smoke。
- 是否预期提交（Commit expected）: 仅在用户单独授权提交后。

### 阶段 5（Stage 5）：planner/executor 文档、模板和 workflow 更新

目标（Goal）:

- 把新增机器层规则融入 planner/executor 的用户可读规范，避免脚本存在但 skill 不会主动使用。

做法（How）:

- planner `SKILL.md` 增加：managed 任务获批前生成 Execution Contract；研究类任务记录关键 findings；方案变更必须进入 Plan Amendment Gate。
- planner workflow 增加：如何初始化 contract、如何记录 approval hash、如何把 reference research 写入 Context 或 artifacts、如何在重大决策前重读计划、如何记录 rejected options。
- executor `SKILL.md` 增加：每轮通过 resolver/preflight，阶段动作写 ledger，loop tick 推进未完成阶段，final 前跑 ledger-backed final gate。
- executor workflow 增加：Plan Amendment Gate、ledger 写入时机、loop tick、status summary、attestation mismatch、HARNESS_DISABLED 行为、legacy plan 兼容规则。
- 模板增加 `Plan Amendment Gate`、`Execution Contract`、`Ledger Evidence`、`Resume Packet`。
- references 增加 `Error Recovery Protocol`：失败动作必须记录 command、attempt、原因、影响和下一策略；重复失败不得静默第三次重试。
- references 增加 `Topic Handoff Protocol`：长子主题写入 `artifacts/handoffs/<topic>.md`，内容包括当前状态、检查方式、已修改内容、分支/提交/PR、剩余风险，并在 `Implementation Progress` 索引。
- references 增加 `Troubleshooting`：wrong task dir、stale active-task、missing ledger、attestation mismatch、HARNESS_DISABLED、Windows path/shell、hook advisory mode 的处理步骤。

原因（Why）:

- 当前项目的优势是流程规范，新增机器层必须被 workflow 明确消费，否则会变成孤立脚本。
- planning-with-files 的强项在于把“做事方式”写成持续循环和恢复规则；这些必须进入 skill 文档，才能提高实际代理能力。

位置（Where）:

- 文件/模块（Files/modules）: planner/executor `SKILL.md`、references、templates。
- API/配置（APIs/configs）: Plan Amendment Gate、Ledger Evidence。
- 测试/文档（Tests/docs）: quick_validate、全文检索。

参考来源（References）:

- 当前 planner/executor split 规则。
- planning-with-files FIRST restore、Run Contract、5-Question Reboot Test、workflow、quickstart、troubleshooting、topic handoff。

验证（Validation）:

- quick_validate planner/executor。
- 检索关键术语：`Execution Contract`、`Plan Amendment Gate`、`ledger`、`attestation`、`HARNESS_DISABLED`、`Resume Packet`、`loop_tick`、`Goal Condition`、`Topic Handoff`、`Troubleshooting`。

风险和回滚（Risks and rollback）:

- 风险: 文档过长影响 skill 触发后可读性。
- 缓解: `SKILL.md` 只写硬规则，细节放 references。
- 回滚: 回退 references 中新增章节，保留脚本但不启用强制规则。

阶段契约（Stage Contract）:

- 范围（Scope）: skill 文档、模板、workflow、错误恢复、专题交接、故障排查。
- 允许修改（Allowed changes）: planner/executor 文档和模板。
- 禁止修改（Forbidden changes）: 与本阶段无关的 process-manager/electron-ui-verifier 行为。
- 进入条件（Entry checks）: Stage 2-4 脚本契约已确定。
- 退出条件（Exit checks）: 文档和脚本规则一致，且流程协议能被 planner/executor 实际引用。
- 必需验证（Required validation）: quick_validate、规则检索。
- 是否预期提交（Commit expected）: 仅在用户单独授权提交后。

### 阶段 6（Stage 6）：检查脚本强化与负例测试

目标（Goal）:

- 把参考项目成熟的负例测试思想迁移到当前 eval 和脚本 smoke，防止规则回退。

做法（How）:

- 增强 `harness_plan_check.py`：
  - 拒绝空模板、`pending` gate 进入 approval、缺少 contract、缺少 reapproval triggers。
  - 检查 Plan Self-Review 在 Readiness 前且结论通过。
  - 检查 stage contract 包含 depends/owner/validation/rollback/commit expected。
- 增强 `harness_exec_check.py`：
  - preflight 校验 approval hash、contract status、resolver result、open decision、current stage。
  - transition 校验 remaining stage、ledger progression、validation/review evidence。
  - final 校验无 remaining stages、ledger/Markdown 对账、not covered 风险已记录。
- 新增或扩展 eval prompts/expected：
  - tampered-plan-blocked
  - stale-completed-active-task-blocked
  - active-task-path-escape-blocked
  - harness-disabled-optout
  - final-without-ledger-evidence-blocked
  - plan-amendment-reapproval-required
  - zero-stage-plan-rejected
  - missing-planning-loop-protocol-rejected
  - missing-goal-condition-rejected
  - research-without-findings-warning-or-fail
  - repeated-failure-without-new-strategy-blocked
  - loop-tick-continues-unfinished-stage
  - status-summary-stable-fields
  - topic-handoff-index-required-for-long-subtopic
- 使用标准库实现，避免新增依赖。

原因（Why）:

- planning-with-files 的测试价值在于覆盖真实失效形态；当前 eval 更多是能力期望，对流程循环、错误恢复和状态恢复的负例不够。

位置（Where）:

- 文件/模块（Files/modules）: planner/executor scripts、evals、可能新增 `tests/` 或 `evals/*/fixtures/`。
- API/配置（APIs/configs）: CLI 参数和退出码。
- 测试/文档（Tests/docs）: py_compile、smoke、JSON/YAML parse。

参考来源（References）:

- `tests/test_gate.py`
- `tests/test_ledger.py`
- `tests/test_plan_attestation.py`
- `tests/test_planning_disabled_optout.py`
- `tests/test_codex_session_isolation.py`
- `tests/test_skill_frontmatter_valid.py`
- `planning-with-files/commands/plan-loop.md`
- `planning-with-files/commands/status.md`
- `planning-with-files/docs/workflow.md`

验证（Validation）:

- `python -m py_compile` 覆盖新增/修改脚本。
- 每个负例 fixture 至少有一个 fail 断言。
- loop/status/goal condition 相关 fixture 覆盖完成、未完成、阻塞、缺证据四类状态。
- planner/executor expected YAML 或等价 fixture 可解析。
- `git -c diff.autoRefreshIndex=false diff --check`

风险和回滚（Risks and rollback）:

- 风险: 脚本过严导致旧任务无法恢复。
- 缓解: legacy mode advisory；仅新 contract 强制严格检查。
- 回滚: 降级对应检查项为 warning，保留负例文档。

阶段契约（Stage Contract）:

- 范围（Scope）: 检查脚本和负例测试。
- 允许修改（Allowed changes）: scripts、evals、测试 fixture。
- 禁止修改（Forbidden changes）: 为通过测试而削弱用户审批/提交授权。
- 进入条件（Entry checks）: 文档规则完成。
- 退出条件（Exit checks）: 正负例全部符合预期。
- 必需验证（Required validation）: py_compile、smoke、fixture parse。
- 是否预期提交（Commit expected）: 仅在用户单独授权提交后。

### 阶段 7（Stage 7）：可选 Codex hook 薄适配评估

目标（Goal）:

- 评估是否需要为 Codex 增加薄 hook 适配，但不把 hook 作为核心能力前置条件。

做法（How）:

- 先设计 hook capability tiers：
  - advisory：SessionStart/PreCompact 只提醒恢复和写 ledger。
  - gate：Stop/Final 前调用 `harness_exec_check.py --mode final`，仅 gated mode 才阻断。
  - disabled：`HARNESS_DISABLED=1` 或 direct 任务不触发。
- 如果当前 Codex skill 安装机制不稳定或用户未要求 hook，Stage 7 只输出 hook design 文档，不实现。
- 若实现，hook 文件只做薄适配：读取 payload、调用核心脚本、输出 systemMessage 或 block decision。
- 不复制参考项目多 IDE hook 目录。

原因（Why）:

- 参考项目的 hook 很强，但宿主差异大；当前项目应先保证手动/脚本门禁可靠。

位置（Where）:

- 文件/模块（Files/modules）: 可能新增 `.codex/hooks` 或 skill references 中的 hook design。
- API/配置（APIs/configs）: Codex hook payload、`HARNESS_DISABLED`。
- 测试/文档（Tests/docs）: hook smoke 或设计文档审查。

参考来源（References）:

- `planning-with-files/.codex/hooks`
- `planning-with-files/scripts/inject-plan.sh`
- `planning-with-files/scripts/gate-stop.sh`

验证（Validation）:

- 若仅设计：文档说明触发条件、禁用条件、降级行为。
- 若实现：hook 在无 active task、disabled、未批准、已完成、gated incomplete 等场景行为符合预期。

风险和回滚（Risks and rollback）:

- 风险: hook 噪音、误拦、影响 direct 任务。
- 缓解: 默认 advisory 或 disabled；gated mode 显式开启。
- 回滚: 移除 hook 配置，核心脚本仍可手动运行。

阶段契约（Stage Contract）:

- 范围（Scope）: hook 评估或薄适配。
- 允许修改（Allowed changes）: hook design 文档、可选 Codex hook。
- 禁止修改（Forbidden changes）: 多 IDE 分发目录、默认强制 PreToolUse 注入。
- 进入条件（Entry checks）: Stage 3-6 核心脚本稳定。
- 退出条件（Exit checks）: 明确实现或延后决策。
- 必需验证（Required validation）: disabled/direct/managed/gated 场景审查。
- 是否预期提交（Commit expected）: 仅在用户单独授权提交后。

### 阶段 8（Stage 8）：整体验证、changelog 和交付证据收口

目标（Goal）:

- 完成所有文档、脚本、测试和计划状态对账，形成最终交付证据。

做法（How）:

- 运行 planner/executor quick_validate 或等价检查。
- 运行所有新增/修改 Python 脚本 py_compile。
- 运行 guard smoke 和负例 fixture。
- 解析 JSON/JSONL/YAML。
- 检索关键规则，确认 planner/executor/README/CHANGELOG 一致。
- 更新 `CHANGELOG.md`，记录从 planning-with-files 吸收的机制和兼容性说明。
- 更新本任务 `execution-plan.md` 的 Validation Evidence、Code Review、Resume Summary 和 Commit Log。

原因（Why）:

- 该任务改动面涉及核心 skill 工作流，最终交付必须有高信号证据。

位置（Where）:

- 文件/模块（Files/modules）: 全部受影响文件。
- API/配置（APIs/configs）: skill install/source layout。
- 测试/文档（Tests/docs）: changelog、README、eval。

参考来源（References）:

- 当前 `CHANGELOG.md` Stage 43 风格。
- planner/executor final delivery gate。

验证（Validation）:

- `quick_validate.py skills/complex-coding-planner`
- `quick_validate.py skills/complex-coding-executor`
- `python -m py_compile <changed scripts>`
- `git -c diff.autoRefreshIndex=false diff --check`
- 关键规则检索和 fixture parse。

风险和回滚（Risks and rollback）:

- 风险: 某些验证命令依赖本地工具路径不可用。
- 缓解: 记录失败原因和替代验证，不能声称通过。
- 回滚: 按阶段 revert，保留本计划用于复盘。

阶段契约（Stage Contract）:

- 范围（Scope）: 最终验证和交付记录。
- 允许修改（Allowed changes）: changelog、execution-plan 运行记录。
- 禁止修改（Forbidden changes）: 未经批准提交或合并主分支。
- 进入条件（Entry checks）: Stage 1-7 完成或明确延后。
- 退出条件（Exit checks）: final gate 证据齐全。
- 必需验证（Required validation）: 全量计划内验证。
- 是否预期提交（Commit expected）: 仅在用户单独授权提交后。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- 当前 workspace: `D:\Item\vibe_coding\dev-skills`
- 当前参考仓库: `D:\Item\vibe_coding\Ref\planning-with-files`
- 当前项目类型: Codex skill 源码仓库，主要语言为 Markdown、Python、Shell、YAML、JSONL。
- 当前可用分支: `main`、`harness/feature`
- 当前任务不需要网络下载、长期进程或浏览器验证。

临时覆盖（Temporary overrides）:

- `.harness/environment.md` 中旧 `E:\work\...` 路径仅作为历史记录；本任务按当前 workspace `D:\Item\vibe_coding\dev-skills` 规划。
- `rg.exe` 在当前沙箱曾出现 Access Denied；实施验证可优先使用 PowerShell `Select-String` 或 `git grep` 作为替代。

## Git 上下文（Git Context）

主分支（Main branch）:

- main

任务类型（Task type）:

- feature

工作分支（Working branch）:

- harness/feature

分支动作（Branch action）:

- reuse / already-on-branch

同步来源（Sync source）:

- main

最近同步（Last sync）:

- 未在本规划阶段执行同步；实施前 executor 必须串行复查是否需要从 `main` 合入。

分支占用（Branch occupancy）:

- 串行 `git log main..HEAD`: 当前已有 `2b34306 feat(complex-coding): 拆分 planner 和 executor`
- 串行 `git -c diff.autoRefreshIndex=false diff main...HEAD --name-only`: 显示 planner/executor 拆分相关文件和旧 harness diff；本任务将在此基础上新增规划和后续优化改动。
- 现有提交属于本任务（Existing commits belong to this task）: no，本任务是新优化计划；现有提交属于 2026-07-06 拆分任务。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行: yes
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git: yes
- 非 Git 文件读取和文本搜索是否可并发: yes

只读 Git 选项（Read-only Git options）:

- 状态检查优先：`git --no-optional-locks status --short --branch`
- diff 检查优先：`git -c diff.autoRefreshIndex=false diff <range>`
- 最终提交前如需精确状态，可在确认无其它 Git 命令运行后串行执行普通 `git status --short --branch`

Index lock 恢复策略（Index lock recovery）:

- lock 路径解析命令：`git rev-parse --git-path index.lock`
- 删除前检查：精确路径、文件存在、大小/mtime 稳定、无活跃或未知归属 Git 进程
- 删除范围：只删除解析出的精确 `index.lock`，禁止通配符、递归删除和删除其它 `.lock`
- 删除后检查：串行 `git --no-optional-locks status --short --branch`

Git Lock Recovery Log:

| 时间（Time） | lock 路径（Lock path） | 文件大小/mtime（Size/mtime） | Git 进程检查（Process check） | 操作（Action） | 后续 status（Follow-up status） |
| --- | --- | --- | --- | --- | --- |
| not-applicable | none | none | none | none | none |

提交策略（Commit policy）:

- not_authorized
- 用户批准实施不等于提交授权；只有用户明确授权提交，executor 才能使用 `git commit -F`。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: no
- 未合回时代码停留在（If not merged, code remains on）: harness/feature
- 合并前需要用户确认（User confirmation needed before merge）: yes

分支安全（Branch safety）:

- 切换前已检查工作区: implementation stage required
- 不自动 stash: yes
- 不自动 rebase: yes
- 不自动 reset: yes

热修复插入（Hotfix interruption）:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支: yes
- 决策: no hotfix requested

未解决问题（Open issues）:

- 无 blocking Git 问题。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| PowerShell | 文件读取、目录检查、文本检索 | 全阶段 | available | low | Git Bash / Python | not needed |
| Python 标准库 | 新增检查脚本、JSON/JSONL/hash | Stage 2-8 | available assumption | medium | PowerShell 脚本，但不推荐 | implementation approval needed |
| Git | 串行状态、diff、可选提交 | 全阶段 | available | medium | 不提交，仅交付 diff | commit not authorized |
| quick_validate.py | skill 结构检查 | Stage 8 | path to confirm | medium | frontmatter/文件结构手工检查 | not needed |
| planning-with-files local repo | 参考研究来源 | Planning | read | low | GitHub README | already provided |
| process-manager | 长期进程管理 | not needed | available | low | 不启动长期进程 | not needed |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- no

process-manager skill 是否存在（process-manager skill available）:

- yes

规则结论（Rule decision）:

- 本任务实施只涉及文档、模板、Python 脚本、eval 和有限命令验证。
- finite command，例如 py_compile、JSON/YAML 解析、quick_validate、diff check，不进入 process-manager。
- 如果后续决定实现 hook 或启动任何长期服务，必须重新评估本节并按 `process-manager` 管理。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | not-applicable | all | none | none | none | not-applicable | not-applicable |

禁止 shell 后台启动确认（No shell background start）:

- confirmed

历史视图需求（Needs `pm_list --history`）:

- no

证据保留位置（Evidence retention location）:

- `execution-plan.md`

日志沉淀确认（Log evidence persisted）:

- not-applicable

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前必须复查本节。
- 若出现长期进程需求，必须停止并重新规划 Process Manager Gate。

## 验证（Validation）

必需验证（Required）:

- 规划文档结构检查：`python skills/complex-coding-planner/scripts/harness_plan_check.py --plan .harness/tasks/2026-07-08/feature/planning-with-files-skill-optimization/execution-plan.md`
- planner/executor skill 结构检查：quick_validate 或等价 frontmatter/文件结构检查。
- Python 脚本语法检查：`python -m py_compile <changed scripts>`
- 新增 resolver/attestation/ledger/exec gate 脚本 smoke。
- JSON/JSONL/YAML parse：active-task、eval prompts、expected、ledger fixture。
- 关键规则检索：`Execution Contract`、`attestation`、`ledger`、`Plan Amendment Gate`、`HARNESS_DISABLED`、`Resume Packet`、`Stage Transition Gate`、`Goal Condition`、`loop_tick`、`status summary`、`Topic Handoff`、`Troubleshooting`、`commit authorization`。
- 流程 fixture：missing loop protocol、missing goal condition、research without findings、repeated failure without new strategy、loop tick unfinished stage、status stable fields、topic handoff index。
- `git -c diff.autoRefreshIndex=false diff --check`

已执行（Executed）:

- 命令/工具（Command/tool）: 本规划阶段已读取 planner/executor 规则、参考项目关键文件、README、environment、Git 分支和分支占用。
- 结果（Result）: passed for planning context.
- 证据（Evidence）: 本计划 Context、Git Context 和 Reference Learning Matrix。
- 覆盖范围（Covers）: 方案制定。
- 未覆盖（Not covered）: 未实现源码，未运行未来新增脚本。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | 读取 planner/executor/current repo | passed | 当前 skill 能力和短板 | 实现行为 | Context | none |
| Planning | 读取 planning-with-files local repo | passed | 参考机制 | 未运行参考测试 | Reference Learning Matrix | none |
| Planning | Git read-only checks | passed | branch/context | 未同步 main | Git Context | executor stage entry recheck |
| Planning | `python skills\complex-coding-planner\scripts\harness_plan_check.py --plan .harness\tasks\2026-07-08\feature\planning-with-files-skill-optimization\execution-plan.md` | passed | 流程补强后的计划结构 | 实现行为 | `PASS: plan structure is ready for approval` | none |
| Stage 1 | 文档检索 + diff check | pending | README/environment/gitignore | 实现脚本 |  |  |
| Stage 2 | planner check + executor preflight fixture + loop/goal negative fixture | pending | Execution Contract、规划/执行循环、目标条件 | 旧任务兼容 |  |  |
| Stage 3 | resolver/opt-out/containment smoke | pending | active task 定位 | session attach hook |  |  |
| Stage 4 | ledger JSONL + summary stability + status + loop tick + final gate | pending | 机器进度证据、持续推进、状态恢复 | hook gate |  |  |
| Stage 5 | quick_validate + 规则检索 + troubleshooting/topic handoff 检索 | pending | 文档规则消费脚本和流程协议 | 真实长任务 |  |  |
| Stage 6 | py_compile + 负例 fixture | pending | 回归防线、流程循环、错误恢复 | 性能 |  |  |
| Stage 7 | hook design/smoke | pending/optional | 宿主适配 | 多 IDE |  |  |
| Stage 8 | 全量验证 + changelog | pending | 交付证据 | 用户实际安装 |  |  |

可选验证（Optional）:

- 使用新 planner 模板生成一个小型 synthetic managed plan，再用 executor preflight/transition/final 负例跑通。
- 将 hook 适配留到单独任务做真实 Codex session smoke。

产物（Artifacts）:

- 截图（Screenshot）: not-applicable
- 日志（Log）: future script smoke 输出可写入本计划 Validation Evidence
- Trace: not-applicable
- 报告（Report）: this execution-plan.md

未覆盖（Not covered）:

- 不验证参考项目本身正确性。
- 不验证多 IDE 安装和 Claude Code plugin 行为。
- 不验证真实用户长任务，只通过 fixture 和 smoke 降低风险。

无法执行时（If unable to run）:

- 必须记录命令、失败原因、影响范围和替代验证，不能声称通过。

## 文档（Documentation）

必需更新（Required updates）:

- `README.md`
- `.harness/environment.md`
- `.gitignore`
- `skills/complex-coding-planner/SKILL.md`
- `skills/complex-coding-planner/references/planning-workflow.md`
- `skills/complex-coding-planner/templates/execution-plan.md`
- `skills/complex-coding-executor/SKILL.md`
- `skills/complex-coding-executor/references/execution-workflow.md`
- `skills/complex-coding-executor/references/troubleshooting.md` 或等价章节（若选择合并到 workflow，需在目录中可检索）
- `skills/complex-coding-executor/scripts/harness_exec_check.py`
- `skills/complex-coding-planner/scripts/harness_plan_check.py`
- `evals/complex-coding-planner/*`
- `evals/complex-coding-executor/*`
- `CHANGELOG.md`

Changelog 计划（Changelog plan）:

- 在当前日期新增条目，说明吸收 planning-with-files 的 resolver、attestation、ledger、gated checks、opt-out 和负例测试思想。
- 明确兼容性：不引入根目录三文件，不复制多 IDE 分发，不默认启用 hook 强拦。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `README.md` | yes | skill 介绍、layout、install、notes | 完整读取和旧名检索 |
| `.harness/environment.md` | yes | Sources、Git、Projects、Rules | 完整读取 |
| `.gitignore` | no | `.harness` runtime block | diff check |
| planner `SKILL.md` | no | 核心规则 | quick_validate |
| planner workflow | yes | 任务分级、contract、审批、交接 | 完整读取和规则检索 |
| planner template | yes | Contract、Amendment、Ledger、Resume | planner check |
| executor `SKILL.md` | no | 启动条件和核心规则 | quick_validate |
| executor workflow | yes | preflight、ledger、amendment、final gate | 完整读取和规则检索 |
| Python scripts | yes | helper、CLI、checks、main | py_compile/smoke |
| eval files | no/unknown | 单 fixture 组 | JSONL/YAML parse |
| `CHANGELOG.md` | no | 单日期块 | 完整读取 |

写入规则（Write rules）:

- 分段 patch 是落盘策略，不要求一次性生成全部细节。
- 单次 `apply_patch` 新增内容建议不超过 120 行，硬上限 200 行。
- 目标文件超过 500 行时默认禁止整文件重写。
- 写入后必须重新读取完整目标文件检查一致性。
- 如果 patch 失败，先读取目标文件确认是否有部分写入，再缩小 patch 重试。

整体复查（Whole-file review）:

- 写完后重新读取完整目标文件: required
- 需要检查的整体一致性: planner/executor 职责边界、contract 字段、ledger schema、approval/commit 边界、legacy compatibility。
- 对应验证命令或方式: quick_validate、py_compile、smoke、diff check、规则检索。

patch 失败处理（Patch failure handling）:

- 读取目标文件确认是否有部分写入: yes
- 失败原因判断: 上下文漂移、行尾、目标文件被用户改动、patch 过大
- 重试策略: 缩小到单章节或单函数 patch；不使用 shell 拼接绕过。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | resolved | 是否照搬 planning-with-files 三文件模式 | 不照搬，保留 `.harness/tasks/**/execution-plan.md` 主契约 | Decision |
| D-002 | no | resolved | 是否第一批启用 hook 强拦 | 不默认启用，Stage 7 评估或延后 | Stage 7 |
| D-003 | no | resolved | 是否自动执行 AcceptanceCheck | 不自动执行，除非后续 allowlist + 用户授权 | Non-Adopted |
| D-004 | no | resolved | 是否保留旧任务兼容 | 保留 legacy advisory；新 contract 强校验 | Stage 3/6 |
| D-005 | no | resolved | 是否需要提交授权 | 当前未授权提交，实施后需单独确认 | Git Context |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | passed | Context evidence table |
| 影响面矩阵完整（Impact matrix complete） | passed | Impact Matrix |
| 候选方案比较充分（Options compared enough） | passed | Options A/B/C |
| 每阶段可独立验证（Stages independently verifiable） | passed | Stage 1-8 validation |
| 方案变更触发条件清楚（Reapproval triggers clear） | passed | Decision reapproval triggers |
| 用户批准摘要可记录（Approval summary ready） | passed | Plan Approval |

质量结论（Quality result）:

- passed

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- passed after adjustments

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 初始方案若直接照搬参考项目，会与 `.harness` 主契约冲突 | 选择混合增强，拒绝根目录三文件和多 IDE 分发 | fixed |
| 优化（Optimizations） | hook 价值高但容易噪音和误拦 | 将 hook 后置为 Stage 7，可只输出设计 | fixed |
| 缺失项（Missing items） | 当前 README/environment 漂移会影响后续实施 | Stage 1 明确校准 README、environment、gitignore | fixed |
| 缺失项（Missing items） | 原计划偏重机器脚本，未充分吸收 planning-with-files 的规划循环和执行循环 | Stage 2/4/5/6 增加 Planning Loop、Executor Work Loop、Goal Condition、loop tick、status summary 和流程负例 | fixed |
| 缺失项（Missing items） | 长任务专题研究和实施细节缺少 handoff 载体 | Stage 5 增加 Topic Handoff Protocol，Stage 6 增加索引负例 | fixed |
| 缺失项（Missing items） | 流程故障排查不足 | Stage 5 增加 Troubleshooting，覆盖 wrong task dir、stale active-task、attestation mismatch、HARNESS_DISABLED 和 Windows 路径 | fixed |
| 风险（Risks） | 新 contract 可能让旧任务恢复失败 | 规定 legacy advisory、新 contract 强校验 | fixed |
| 一致性（Consistency） | active-task 与 plan 未来可能冲突 | Stage 3 新增 resolver，Stage 4 引入 ledger 对账 | fixed |
| 风险（Risks） | 自动执行 AcceptanceCheck 会带来命令注入和授权问题 | 明确不自动执行，后续需 allowlist 和用户授权 | fixed |
| 缺失项（Missing items） | 提交授权容易与实施批准混淆 | Git Context 和 Plan Approval 写明 not_authorized | fixed |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑: yes, completed
- `Plan Self-Review` 是否需要重跑: yes, completed
- `Readiness Gate` 是否需要重跑: yes, completed
- 原因: 本轮补强了流程实施能力、阶段摘要和验证项，虽未改变总体方案选择，但改变了实施计划细节，已重新运行 planner 结构校验并通过。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | passed | Problem |
| 上下文已收集（Context collected） | passed | Context + Reference Learning Matrix |
| 候选方案已比较（Options compared） | passed | Options A/B/C |
| 决策已记录（Decision recorded） | passed | Decision |
| 实施阶段已细化（Implementation stages detailed） | passed | Stage 1-8 |
| 环境已确认（Environment confirmed） | passed with note | Environment；旧路径漂移列入 Stage 1 |
| Git 上下文已确认（Git context confirmed） | passed with note | branch/log/diff read-only checks；实施前需复查同步 |
| 工具已确认（Tooling confirmed） | passed | Tooling |
| 验证已确认（Validation confirmed） | passed | Validation |
| 最终交付证据已规划（Final delivery evidence planned） | passed | Stage 8 |
| 文档更新已确认（Documentation updates confirmed） | passed | Documentation |
| 风险已识别（Risks identified） | passed | stage risks + Self-Review |
| 规划自查已通过（Plan self-review passed） | passed | Plan Self-Review |
| 阻塞问题已关闭（Blocking questions closed） | passed | 无 blocking |

就绪结论（Readiness result）:

- ready_for_user_plan_approval

## 方案批准（Plan Approval）

状态（Status）:

- approved

批准记录（Approval record）:

- 2026-07-08 本计划已按当前 `complex-coding-planner` 规则生成。
- 2026-07-08 用户明确批准：“批准，接下来 开始按规范 实现 这个 方案”。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: 按本 `execution-plan.md` 实现 Stage 1-8；Stage 7 可按计划作为可选 hook 评估，不强制启用 hook。
- 阶段提交授权（Stage commit authorization）: not_authorized
- 工具/MCP 授权（Tool/MCP authorization）: finite local tools authorized for implementation and validation; no network or long-running process expected.
- 文档更新授权（Documentation authorization）: authorized within approved scope.

提交策略（Commit policy）:

- not_authorized

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- completed

当前阶段（Current stage）:

- Stage 2

已完成阶段（Completed stages）:

- Planning research and plan drafting
- Stage 1

剩余阶段（Remaining stages）:

- Stage 2
- Stage 3
- Stage 4
- Stage 5
- Stage 6
- Stage 7
- Completed

下一步自动动作（Next automatic action）:

- continue Stage 2

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no, after implementation approval unless user explicitly requests stage-only execution or a Stop Condition is active

active-task 同步字段（active-task sync fields）:

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "current_stage": "Completed",
  "remaining_stages": [],
  "next_automatic_action": "none",
  "stop_condition": "completed",
  "state_source": "execution-plan.md"
}
```

状态同步规则（State sync rules）:

- `execution-plan.md` 是唯一主契约；`.harness/active-task.json` 只作为恢复入口和摘要索引。
- 如果 active-task 与本节冲突，executor 应以本节为准修正 active-task 后继续。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | completed | 已研究当前 planner/executor 和 planning-with-files，并补强规划循环、执行循环、状态恢复和流程负例 | context checks passed + planner check passed | 本计划 | approved for implementation |
| Stage 1 | completed | 状态、命名和环境校准 | passed | README/environment/gitignore 检索；`git -c diff.autoRefreshIndex=false diff --check` | continue Stage 2 |
| Stage 2 | completed | Execution Contract、规划/执行循环、目标条件 | passed | template + plan_check + preflight | continue Stage 3 |
| Stage 3 | completed | resolver、containment、opt-out | passed | resolver smoke + HARNESS_DISABLED smoke | continue Stage 4 |
| Stage 4 | completed | ledger、loop tick、status summary、gated checks | passed | ledger append/summary + status + loop-tick + negative final gate | continue Stage 5 |
| Stage 5 | completed | 文档、模板、workflow、错误恢复、专题交接和故障排查 | passed | SKILL/workflow/template/troubleshooting 检索 | continue Stage 6 |
| Stage 6 | completed | 检查脚本、流程负例和回归测试 | passed | JSONL/YAML shape + syntax checks | continue Stage 8 |
| Stage 7 | deferred | Codex hook 薄适配评估 | not_run | 按批准计划后置，不默认启用 hook；CLI gate 已落地 | continue Stage 8 |
| Stage 8 | completed | 整体验证和交付收口 | passed | plan check、syntax、JSONL/YAML shape、resolver/preflight/status/loop、negative final gate、final gate、diff check | completed |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | passed | implementation approved | README/environment/gitignore checked | not-applicable | passed | passed |
| Stage 2 | passed | Stage 1 completed | scripts/templates checked | not-applicable | passed | passed |
| Stage 3 | passed | Stage 2 completed | resolver checked | not-applicable | passed | passed |
| Stage 4 | passed | Stage 3 completed | ledger/status checked | not-applicable | passed | passed |
| Stage 5 | passed | Stage 4 completed | docs checked | not-applicable | passed | passed |
| Stage 6 | passed | Stage 5 completed | evals checked | not-applicable | passed | passed |
| Stage 7 | deferred | Stage 6 completed | not-applicable | not-applicable | deferred by plan | deferred |
| Stage 8 | passed | Stage 7 deferred | validation tools available | not-applicable | passed | passed |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | yes | yes | passed | not-applicable | passed | yes | not_authorized | passed |
| Stage 2 | yes | yes | passed | not-applicable | passed | yes | not_authorized | passed |
| Stage 3 | yes | yes | passed | not-applicable | passed | yes | not_authorized | passed |
| Stage 4 | yes | yes | passed | not-applicable | passed | yes | not_authorized | passed |
| Stage 5 | yes | yes | passed | not-applicable | passed | yes | not_authorized | passed |
| Stage 6 | yes | yes | passed | not-applicable | passed | yes | not_authorized | passed |
| Stage 7 | deferred | yes | not_run | not-applicable | yes | yes | not_authorized | deferred |
| Stage 8 | yes | yes | passed | not-applicable | passed | yes | not_authorized | passed |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证已完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | yes | yes | yes | not_authorized | yes | cleared | no | yes | yes | no | continue Stage 1 |
| Stage 1 | yes | yes | passed | not_authorized | yes | no | no | yes | yes | no | continue Stage 2 |
| Stage 2 | yes | yes | passed | not_authorized | yes | no | no | yes | yes | no | continue Stage 3 |
| Stage 3 | yes | yes | passed | not_authorized | yes | no | no | yes | yes | no | continue Stage 4 |
| Stage 4 | yes | yes | passed | not_authorized | yes | no | no | yes | yes | no | continue Stage 5 |
| Stage 5 | yes | yes | passed | not_authorized | yes | no | no | yes | yes | no | continue Stage 6 |
| Stage 6 | yes | yes | passed | not_authorized | yes | no | no | yes | yes | no | continue Stage 8 |
| Stage 7 | deferred | yes | not_run | not_authorized | yes | no | no | yes | yes | no | continue Stage 8 |
| Stage 8 | yes | yes | passed | not_authorized | no | final delivery | no | yes | yes | yes | final delivery |

结论（Decision）:

- 用户已批准实施，所有已批准阶段已完成，final gate 已通过；提交仍未授权。

规则（Rules）:

- 用户批准方案后，默认由 `complex-coding-executor` run-to-completion 执行 Stage 1-8。
- Stage 7 可以在实施中记录为 deferred，但需要在 Stage Transition Gate 写明原因。
- 提交仍需单独授权。

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Planning | 方案涉及核心 planner/executor 协议，风险较高 | major | 已拆成 8 个阶段并要求每阶段独立验证 |
| Planning | hook 易产生误拦截 | major | Stage 7 后置且默认可延后 |
| Planning | 新 contract 可能影响旧任务恢复 | major | legacy advisory，新 contract 强校验 |
| Planning | README/environment 当前漂移 | minor | Stage 1 优先校准 |

## 恢复摘要（Resume Summary）

- 整体目标（Overall goal）: 结合 planning-with-files 优秀机制，优化当前 dev-skills 的 planner/executor 长任务文件状态能力。
- 执行模式（Execution mode）: run-to-completion.
- 整体任务状态（Overall status）: completed.
- 已完成阶段（Completed stages）: Planning research and plan drafting, Stage 1-6, Stage 7 deferred, Stage 8.
- 当前阶段（Current stage）: Completed.
- 剩余阶段（Remaining stages）: none.
- 最新 commit（Latest commit）: not created for this task.
- 下一步自动动作（Next automatic action）: none.
- 当前停止条件（Current stop condition）: completed.
- 状态来源（State source of truth）: execution-plan.md.
- 长期进程规则（Process manager rule）: no long-running process needed; if introduced, use process-manager.
- 未覆盖/风险（Not covered/risks）: hook 作为可选后置阶段，未启用真实 hook；提交未授权。
- 不得停止说明（Do not stop note）:
  - 用户批准实施后，除非触发停止条件或用户要求 stage-only，否则 executor 不应在 Stage 1-7 的阶段边界最终回复后停止。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 如用户后续授权提交，使用 `git commit -F .harness/tasks/2026-07-08/feature/planning-with-files-skill-optimization/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | not_authorized | not_authorized | not changed |

# 执行计划：强化 planner 不确定问题调研门禁

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

剩余阶段（Remaining stages）:

- none

下一步自动动作（Next automatic action）:

- none

当前停止条件（Current stop condition）:

- completed

状态来源（State source of truth）:

- execution-plan.md

执行方（Executor）:

- 当前方案已获用户批准，实施阶段交给 `complex-coding-executor` 按阶段推进。

## 执行契约（Execution Contract）

```json
{
  "contract_version": 1,
  "task_id": "2026-07-08-feature-planner-research-gate-optimization",
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

- `execution-plan.md` 是唯一主契约；`.harness/active-task.json` 只作为恢复入口。
- `approved_contract_hash` 在用户批准后由 executor 使用外部 `attestation.json` 固化。
- 修改 approved scope、stage 边界、验证策略、风险等级、工具授权或提交策略时，必须进入 `Plan Amendment Gate`。

## 目标条件（Goal Condition）

- 所有 approved stages 均完成，且最终 `final` 门禁通过。
- 无 open blocking decision、无未处理 blocking/major review finding。
- Research Gate 已能覆盖可变事实、不确定项、在线搜索和来源矩阵。
- 必需验证已执行，或无法执行项已记录原因、影响和替代证据。
- 提交授权状态明确；用户未明确授权时不得提交，但必须记录原因。

## 规划循环协议（Planning Loop Protocol）

- managed 计划默认拆为 3-7 个可独立验证阶段；本计划为 6 个阶段。
- 调研、浏览、搜索或查看多个来源后，关键 findings 必须写入 `Context`、`Research Gate`、`Reference Learning Matrix` 或 artifacts。
- 重大决策前必须重读目标、约束、Options、Decision、影响面和 reapproval triggers。
- rejected options 必须记录放弃原因，避免上下文压缩后重复探索。
- Readiness 前必须重新运行 `Plan Quality Gate`、`Plan Self-Review` 和 `Readiness Gate`。

## 执行循环协议（Executor Work Loop）

- 每个阶段开始先读取 `Execution Contract`、`Resume Packet`、Stage Contract 和上一阶段 findings。
- 每次阶段动作后更新 ledger/progress；没有实质进展但需要保持长任务循环时写 heartbeat。
- 失败动作必须记录 attempt、命令或工具、失败原因、影响和下一策略。
- Stage Transition Gate 通过且仍有 pending stage 时，下一动作必须是 `continue Stage N`。
- 只有满足 `Goal Condition` 后才能进入最终交付。

## 问题定义（Problem）

目标（Goal）:

- 在 `complex-coding-planner` 中补齐不确定问题的深入调研机制，让可变事实、外部 API、框架、工具、模型、依赖和高风险领域默认经过在线或一手资料调研后才进入方案审批。
- 让 `harness_plan_check.py` 不再只检查章节结构，而能阻止空模板、占位符、未关闭不确定项、缺少外部来源和 assumption 滥用。
- 在 `complex-coding-executor` 中补充执行阶段发现新不确定项时的回退规则，避免实现阶段静默扩大假设。

非目标（Non-goals）:

- 不在本规划阶段实现任何代码。
- 不强制所有 managed 任务都联网搜索；只有触发条件命中时才进入 `online-required`。
- 不引入独立数据库、外部服务或长期后台进程。
- 不默认启用 hook 阻断；本轮聚焦 planner/executor 文档、模板、检查脚本和 eval。

验收标准（Acceptance）:

- 模板新增 `Research Gate`，并纳入 `Plan Quality Gate`、`Plan Self-Review`、`Readiness Gate`。
- planner workflow 明确何时必须在线搜索官方或一手资料、何时可 local-only、何时必须转 blocking。
- `harness_plan_check.py` 默认拒绝空模板、pending readiness、未关闭 uncertainty 和缺少来源的 `online-required` 计划。
- executor workflow 明确 `Research Drift Gate`：执行中发现新外部事实或不确定项时，补证据或进入 `Plan Amendment Gate`。
- eval 覆盖在线调研缺失、模板占位符、assumption 误通过和执行阶段研究漂移。

约束（Constraints）:

- 遵守用户全局规则：中文注释、先读上下文、最小变更、分段写入、真实验证说明和提交信息格式。
- 遵守当前 planner：Readiness Gate 通过后停止，等待用户明确批准。
- 遵守当前 executor：批准后 run-to-completion、阶段门禁、ledger、review、验证和提交授权分离。
- 同一仓库 Git 命令必须串行；提交必须用户另行授权。

待确认项（Open uncertainties）:

- 无 blocking 问题。默认采用“按触发条件要求在线调研”的方案，不把所有任务无差别强制联网。

## 调研门禁（Research Gate）

研究模式（Research mode）:

- 本规划自身: `online-required`，因为任务讨论的是在线资源搜索机制、Codex/OpenAI 工具能力和可能随时间变化的行为。
- 后续模板目标: `none` / `local-only` / `online-required` / `blocked-by-access` 四态。

触发规则（Triggers）:

- 涉及框架、API、协议、工具、模型、依赖版本、外部服务、浏览器行为、系统平台差异、法规、安全、金融、医学或其他可能变化事实时，默认 `online-required`。
- 涉及用户本地私有代码、已锁定配置、已读源码或稳定项目规则时，可为 `local-only`。
- 用户禁止联网、网络不可用或权限不足时，标记 `blocked-by-access`；不得凭记忆把关键事实写成 confirmed。
- 无外部事实依赖的简单本地改动可为 `none`，但必须写明理由。

不确定项清单（Uncertainty inventory）:

| ID | 问题 | 类型 | 是否需要在线搜索 | 处理结果 | 影响 |
| --- | --- | --- | --- | --- | --- |
| U-001 | planner 是否已有调研机制 | local-code | no | 已读 planner SKILL/workflow/template/script，存在软规则但缺硬门禁 | 需要强化 |
| U-002 | 当前 plan check 是否能拦空模板 | local-script | no | 已运行空模板检查，返回 PASS | 需要修复 |
| U-003 | 在线搜索应如何记录来源 | external-tool | yes | 参考 OpenAI Web search 官方文档和当前工具来源要求 | 需要来源矩阵 |
| U-004 | executor 是否需要联动 | local-rule | no | 已读 executor workflow，缺少执行期 research drift 规则 | 需要轻量补充 |

搜索记录（Search log）:

| 查询/来源 | 工具 | 时间 | 结果 | 后续动作 |
| --- | --- | --- | --- | --- |
| OpenAI Web search 官方文档 | web open | 2026-07-08 | 文档存在 Web search 工具和 Sources/citation 能力说明 | 将来源记录能力转化为模板矩阵 |
| 当前 planner/executor 文件 | PowerShell read | 2026-07-08 | 已确认规则缺口和脚本缺口 | 纳入实施阶段 |
| 空模板 plan check | Python command | 2026-07-08 | 空模板也 PASS | Stage 2 必修 |

来源矩阵（Source matrix）:

| 结论（Claim） | 来源类型 | URL/路径 | 是否官方/一手 | 访问日期 | 可信度 | 影响 |
| --- | --- | --- | --- | --- | --- | --- |
| Web search 可作为获取最新信息并记录来源的工具能力 | external | `https://developers.openai.com/api/docs/guides/tools-web-search` | yes | 2026-07-08 | high | Research Gate 应记录查询、来源和引用 |
| planner 当前只有查询官方资料的软规则 | local-code | `skills/complex-coding-planner/references/planning-workflow.md` | yes | 2026-07-08 | high | 需要转成门禁和模板字段 |
| plan check 当前不校验调研充分性 | local-code/test | `skills/complex-coding-planner/scripts/harness_plan_check.py` + 空模板检查 | yes | 2026-07-08 | high | 需要 strict 检查 |
| executor 当前没有 research drift gate | local-code | `skills/complex-coding-executor/references/execution-workflow.md` | yes | 2026-07-08 | high | 需要执行期回退规则 |

Research Gate 结论:

- passed。当前方案已将不确定问题、在线搜索、一手来源、无网络降级和执行期漂移全部纳入实施计划。

## 上下文（Context）

本地代码（Local code）:

- `skills/complex-coding-planner/SKILL.md`：已有 managed 规划、Readiness Gate、Plan Self-Review、审批停止规则。
- `skills/complex-coding-planner/references/planning-workflow.md`：已有“依赖可能变化事实时查询官方或一手资料”，但没有独立 Research Gate。
- `skills/complex-coding-planner/templates/execution-plan.md`：已有 `External sources` 和 `Evidence levels`，但缺少研究模式、查询记录、不确定项闭环和来源矩阵。
- `skills/complex-coding-planner/scripts/harness_plan_check.py`：当前检查章节、关键词、门禁顺序和契约字段；空模板也能 PASS。
- `skills/complex-coding-executor/references/execution-workflow.md`：已有 Plan Amendment Gate、失败恢复和验证规则，但缺少执行期新不确定项处理。
- `evals/complex-coding-planner/*`：已有 findings 记录用例，但缺少在线搜索和 research gate 负例。

本地文档（Local docs）:

- `.harness/environment.md`：当前仓库主分支为 `main`，feature 类型使用 `harness/feature`。
- `.harness/active-task.json`：上一任务已完成，本任务将切换为新的 awaiting_plan_approval。
- `README.md`、`CHANGELOG.md`：实施阶段需要更新，说明 planner 从结构检查升级为研究证据检查。

外部来源（External sources）:

- OpenAI Web search 官方文档：用于确认“搜索 + 来源/citation”应成为调研证据记录的设计依据。
- 当前系统/开发者要求：遇到可能变化、需要最新事实、需要直接来源或高风险准确性的问题，应优先联网核验。

用户约束（User constraints）:

- 用户要求按 `complex-coding-planner` 制定方案，后续实现阶段按 `complex-coding-executor` 约束执行。
- 用户已明确指出规划阶段对不确定问题缺少深入调研和在线搜索机制，需要结合前面排查结果制定方案。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 本任务属于 managed planning-only | confirmed | 用户要求按 planner 规划且后续 executor 执行 | 必须落盘计划并等待审批 |
| 当前存在调研机制缺口 | read/confirmed | workflow、template、plan_check、空模板检查 | 方案核心目标 |
| 需要新增 Research Gate | external/read | OpenAI Web search 文档、当前工具规则、本地缺口 | Stage 1/2 |
| executor 需要 research drift 规则 | read | executor workflow | Stage 4 |

## 候选方案（Options）

### 方案 A：只补文档规则（Minimal Change）

- 做法（How）: 在 planner workflow 增加几条“遇到不确定项要搜索”的文字说明。
- 优点（Pros）: 改动小，风险低。
- 缺点（Cons）: 仍无法阻止空模板、pending、无来源计划通过。
- 风险（Risks）: 模型执行依赖自觉，缺陷会复发。
- 验证（Validation）: 文档检索和 plan check。
- 回滚（Rollback）: revert 文档变更。

### 方案 B：Research Gate + strict plan check（Recommended）

- 做法（How）: 新增 Research Gate 模板和规则，强化 plan_check，补 eval，executor 增加 Research Drift Gate。
- 优点（Pros）: 把调研从软提醒变成审批前硬门禁，覆盖规划和执行两端。
- 缺点（Cons）: 检查逻辑更复杂，需要维护负例。
- 风险（Risks）: 过严可能让 local-only 任务被误拦，需要明确 `none/local-only` 例外。
- 验证（Validation）: 空模板默认 fail、真实计划 pass、在线必需但无来源 fail、assumption 无影响说明 fail。
- 回滚（Rollback）: 回退 plan_check 严格检查和模板新增章节，保留文档说明也可独立存在。

### 方案 C：全量 Deep Research 工作流（Full Research Workflow）

- 做法（How）: 每个 managed 任务都必须联网搜索、多来源交叉验证，并创建独立 research artifacts。
- 优点（Pros）: 研究最充分。
- 缺点（Cons）: 对纯本地任务过重，增加时间、网络依赖和噪音。
- 风险（Risks）: 规划门槛过高，用户体验下降。
- 验证（Validation）: 大量 research fixture 和网络不可用 fixture。
- 回滚（Rollback）: 成本较高。

## 决策（Decision）

选择方案（Chosen option）:

- 方案 B：Research Gate + strict plan check。

原因（Why）:

- 它直接解决已复现问题：空模板可通过、外部来源不可验证、不确定项没有闭环。
- 它保留 local-only 任务的效率，不把所有 managed 任务都拖进联网搜索。
- 它能和刚落地的 ledger、attestation、loop tick、final gate 自然衔接。

影响（Impact）:

- planner 规则、模板、检查脚本和 eval 会改变。
- executor 规则轻量补充，不改变执行主架构。
- README/CHANGELOG 需要同步说明新能力。

可逆性（Reversibility）:

- 中等。文档和模板可回退；strict check 可通过 flag 或分阶段回退。

变更条件（Change conditions）:

- 若 strict check 误拦已完成计划，应补充兼容策略或 `--allow-template` / `--mode template`。
- 若用户希望所有 managed 任务都强制在线搜索，需要进入 Plan Amendment Gate。

方案变更触发条件（Reapproval triggers）:

- 改变阶段数量、跳过 plan_check 强化、默认强制所有任务联网、引入 hook 阻断、改变提交策略或新增长期服务。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | no | none | low | not-applicable | no |
| 数据结构（Data model） | yes | `execution-plan.md` 模板、active-task 状态 | medium | JSON/Markdown fixture | yes |
| 前端交互（Frontend interaction） | no | none | low | not-applicable | no |
| 配置/环境（Config/environment） | yes | `.harness/environment.md` 引用验证命令 | low | 环境文件复查 | yes |
| 兼容性（Compatibility） | yes | 旧 plan、空模板、已完成任务、plan_check 调用方 | high | 负例/正例 fixture | yes |
| 测试（Tests） | yes | planner/executor eval | medium | JSONL/YAML parse + expected cases | yes |
| 文档（Documentation） | yes | SKILL.md、workflow、README、CHANGELOG | medium | 文档检索 + plan check | yes |

## 参考学习矩阵（Reference Learning Matrix）

| 来源 | 可吸收能力 | 转换为本项目能力 | 采纳 |
| --- | --- | --- | --- |
| 当前空模板 PASS 复现 | 暴露结构检查不足 | plan_check 增加 strict 内容检查 | adopt |
| OpenAI Web search 文档 | 搜索结果应带来源 | Research Gate 增加查询记录和来源矩阵 | adopt |
| 当前 planning-with-files 优化成果 | findings/loop/ledger/attestation | 继续复用 `.harness` 主契约，不新增状态源 | adopt |
| 当前 executor workflow | Plan Amendment 和错误恢复 | 新增 Research Drift Gate | adopt-adjusted |

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：planner Research Gate 规则和模板

目标（Goal）:

- 让 planner 在方案审批前显式判断研究模式并关闭不确定项。

做法（How）:

- 在 `SKILL.md` 增加核心规则：可变事实或高风险事实必须进入 Research Gate。
- 在 `planning-workflow.md` 增加 Research Gate：`none/local-only/online-required/blocked-by-access`、触发条件、来源优先级、无法联网处理。
- 在 `templates/execution-plan.md` 增加 `调研门禁（Research Gate）`，包括不确定项清单、搜索记录、来源矩阵和结论。

原因（Why）:

- 现有规则只说查询官方资料，没有独立门禁和结构化记录。

位置（Where）:

- 文件/模块（Files/modules）: planner `SKILL.md`、`references/planning-workflow.md`、`templates/execution-plan.md`。
- API/配置（APIs/configs）: 无。
- 测试/文档（Tests/docs）: planner eval、README、CHANGELOG 后续阶段。

参考来源（References）:

- 本计划 Research Gate、当前 planner workflow、OpenAI Web search 官方文档。

验证（Validation）:

- 检索 `Research Gate`、`online-required`、`blocked-by-access`、`来源矩阵`。

风险和回滚（Risks and rollback）:

- 风险: 模板变长。缓解: SKILL.md 保持短规则，细节放 workflow/template。
- 回滚: 移除模板章节和 workflow 规则。

阶段契约（Stage Contract）:

- 范围（Scope）: planner 规则和模板。
- 允许修改（Allowed changes）: planner SKILL、workflow、template。
- 禁止修改（Forbidden changes）: executor 脚本、hook、提交。
- 进入条件（Entry checks）: 用户批准方案后，executor preflight 通过。
- 退出条件（Exit checks）: Research Gate 文档和模板完整。
- 必需验证（Required validation）: 文档检索。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 2（Stage 2）：plan_check 严格检查

目标（Goal）:

- 让 `harness_plan_check.py` 拒绝空模板和调研不充分计划。

做法（How）:

- 新增占位符/pending 检查，默认普通 `--plan` 不允许模板占位内容通过。
- 新增 Research Gate 检查：存在研究模式；`online-required` 必须有非占位来源；未关闭 uncertainty 必须 fail。
- 新增 assumption 检查：关键 assumption 必须有影响和 reapproval trigger。
- 增加 `--allow-template` 或等价 template mode，仅用于模板结构验证。

原因（Why）:

- 已复现空模板也 PASS；这会让 Readiness Gate 失去质量意义。

位置（Where）:

- 文件/模块（Files/modules）: `skills/complex-coding-planner/scripts/harness_plan_check.py`。
- API/配置（APIs/configs）: CLI flag 可选。
- 测试/文档（Tests/docs）: planner eval 负例。

参考来源（References）:

- 空模板检查结果、当前 plan_check 代码。

验证（Validation）:

- 空模板默认 fail；`--allow-template` pass。
- 本新计划 strict check pass。
- 构造 online-required 无来源 fixture fail。

风险和回滚（Risks and rollback）:

- 风险: 旧计划被误判。缓解: 只对 awaiting approval 的新计划严格；completed 计划用于 status/final 可不走 planner strict。
- 回滚: 保留 `--allow-template` 并降级部分检查为 warning。

阶段契约（Stage Contract）:

- 范围（Scope）: planner 检查脚本。
- 允许修改（Allowed changes）: Python 检查逻辑和帮助文本。
- 禁止修改（Forbidden changes）: executor 运行态逻辑。
- 进入条件（Entry checks）: Stage 1 已完成。
- 退出条件（Exit checks）: 正负例行为符合预期。
- 必需验证（Required validation）: py_compile、空模板负例、真实计划正例。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 3（Stage 3）：planner eval 和 fixture 覆盖

目标（Goal）:

- 用回归样例锁住 Research Gate 行为。

做法（How）:

- 在 `evals/complex-coding-planner/prompts.jsonl` 增加在线调研、模板占位、assumption、网络不可用场景。
- 在 `expected.yaml` 增加对应期望字段。
- README 补充 eval 意图。

原因（Why）:

- 当前 eval 没有覆盖“可变事实必须在线搜索官方/一手资料”的负例。

位置（Where）:

- 文件/模块（Files/modules）: `evals/complex-coding-planner/*`。
- API/配置（APIs/configs）: 无。
- 测试/文档（Tests/docs）: eval README。

参考来源（References）:

- 当前 eval 文件、Research Gate 规则。

验证（Validation）:

- JSONL 可解析，ID 唯一。
- YAML 可解析或结构检查通过。

风险和回滚（Risks and rollback）:

- 风险: eval 字段过细导致维护成本高。缓解: 期望只描述行为，不绑定具体 wording。
- 回滚: 删除新增 eval case。

阶段契约（Stage Contract）:

- 范围（Scope）: planner eval。
- 允许修改（Allowed changes）: prompts、expected、README。
- 禁止修改（Forbidden changes）: unrelated eval。
- 进入条件（Entry checks）: Stage 2 行为明确。
- 退出条件（Exit checks）: eval 覆盖新增门禁。
- 必需验证（Required validation）: JSONL/YAML parse。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 4（Stage 4）：executor Research Drift Gate

目标（Goal）:

- 让执行阶段发现新不确定项时不会静默继续。

做法（How）:

- 在 executor workflow 增加 `Research Drift Gate`。
- 规则：执行中发现新的外部事实、API 行为、依赖变化或验证工具变化时，先补证据；若影响范围、阶段、风险或验证，进入 `Plan Amendment Gate`。
- 可在 `harness_exec_check.py` final/basic checks 中要求新计划包含 Research Gate 关键词，避免 future plan 缺失。

原因（Why）:

- planner 能调研不代表执行期不会出现新事实，executor 需要知道如何回退。

位置（Where）:

- 文件/模块（Files/modules）: executor `references/execution-workflow.md`，可选 `harness_exec_check.py`。
- API/配置（APIs/configs）: 无。
- 测试/文档（Tests/docs）: executor eval。

参考来源（References）:

- 当前 executor workflow 的 Plan Amendment Gate、错误恢复协议。

验证（Validation）:

- 文档检索 `Research Drift Gate`。
- executor eval 增加 drift case。
- 如改脚本，运行 py_compile 和 status/final smoke。

风险和回滚（Risks and rollback）:

- 风险: executor basic check 影响旧计划。缓解: 先文档规则，脚本检查可只对含 Research Gate 的新计划强制。
- 回滚: 保留文档，撤回脚本强制项。

阶段契约（Stage Contract）:

- 范围（Scope）: executor 执行规则和可选检查。
- 允许修改（Allowed changes）: workflow、eval、少量 exec check。
- 禁止修改（Forbidden changes）: ledger/attestation 行为大改。
- 进入条件（Entry checks）: Stage 1-3 已完成。
- 退出条件（Exit checks）: drift 规则可被 executor 消费。
- 必需验证（Required validation）: 文档检索，必要时 py_compile/status/final。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 5（Stage 5）：文档、环境和变更记录

目标（Goal）:

- 让用户和后续 agent 清楚新门禁的使用方式。

做法（How）:

- 更新 README：说明 Research Gate、strict plan check、online-required 和 blocked-by-access。
- 更新 CHANGELOG：记录 planner 调研门禁增强。
- 必要时更新 `.harness/environment.md` 的命令清单，加入 strict/template 检查示例。

原因（Why）:

- 新能力影响工作流，不能只藏在脚本和模板里。

位置（Where）:

- 文件/模块（Files/modules）: README、CHANGELOG、`.harness/environment.md`。
- API/配置（APIs/configs）: 无。
- 测试/文档（Tests/docs）: 文档检索。

参考来源（References）:

- 本计划、当前 README/CHANGELOG 风格。

验证（Validation）:

- 文档检索关键术语。
- `git -c diff.autoRefreshIndex=false diff --check`。

风险和回滚（Risks and rollback）:

- 风险: README 过长。缓解: 只写入口和行为摘要。
- 回滚: revert 文档段落。

阶段契约（Stage Contract）:

- 范围（Scope）: 用户文档和环境说明。
- 允许修改（Allowed changes）: README、CHANGELOG、environment。
- 禁止修改（Forbidden changes）: unrelated docs。
- 进入条件（Entry checks）: 规则和脚本基本稳定。
- 退出条件（Exit checks）: 文档反映最新流程。
- 必需验证（Required validation）: 文档检索、diff check。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

### 阶段 6（Stage 6）：整体验证和交付证据

目标（Goal）:

- 按 executor 规范完成最终验证、review、ledger/attestation、Resume Summary 和最终交付。

做法（How）:

- 运行 planner plan check、Python py_compile、JSONL/YAML parse、关键正负例 smoke。
- 执行 code review，修复 blocking/major finding。
- 更新本计划的 Validation Evidence、Implementation Progress、Code Review、Resume Summary 和 Commit Log。
- 用户若授权提交，使用 `git commit -F` 且提交信息无多余空行。

原因（Why）:

- 本任务改动 planner/executor 核心流程，必须有可复核证据。

位置（Where）:

- 文件/模块（Files/modules）: 本任务计划、相关验证脚本、README/CHANGELOG。
- API/配置（APIs/configs）: 无。
- 测试/文档（Tests/docs）: 所有相关验证。

参考来源（References）:

- executor workflow 最终交付门禁。

验证（Validation）:

- `python -m py_compile ...`
- `python skills/complex-coding-planner/scripts/harness_plan_check.py --plan <new-plan>`
- 空模板默认 fail，template mode pass。
- JSONL/YAML parse。
- `git -c diff.autoRefreshIndex=false diff --check`
- `harness_exec_check.py --mode final` 在完成态通过。

风险和回滚（Risks and rollback）:

- 风险: 严格检查对历史计划兼容性不足。缓解: 以新计划为强制对象，旧 completed 计划按 executor final/status 兼容。
- 回滚: 分阶段回退脚本强制项，保留文档规则。

阶段契约（Stage Contract）:

- 范围（Scope）: 验证、记录和交付。
- 允许修改（Allowed changes）: 计划进度、ledger、attestation、changelog。
- 禁止修改（Forbidden changes）: 未批准的新功能。
- 进入条件（Entry checks）: Stage 1-5 完成。
- 退出条件（Exit checks）: final gate 通过或阻塞原因记录完整。
- 必需验证（Required validation）: 全量验证清单。
- 是否预期提交（Commit expected）: no，除非用户另行授权。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- 当前仓库 `D:\Item\vibe_coding\dev-skills`。
- Python 脚本检查、Markdown/YAML/JSONL 文档和 fixture。
- 不需要浏览器验证或长期后台进程。

临时覆盖（Temporary overrides）:

- 无。

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

- origin/harness/feature；当前本地 `harness/feature` ahead 1。

最近同步（Last sync）:

- 未在规划阶段执行同步；planner 只记录状态，executor 实施前按 Git Context 再检查。

分支占用（Branch occupancy）:

- 串行 `git log main..HEAD`: `bcc6fe1` planning-with-files 优化、`2b34306` planner/executor 拆分。
- 串行 `git -c diff.autoRefreshIndex=false diff main...HEAD --name-only`: 主要为 planner/executor、eval、README、CHANGELOG 和 `.harness` 任务文档。
- 现有提交属于本任务（Existing commits belong to this task）: no，属于前序 harness/feature 历史；本任务将在同一 feature 分支继续。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git。
- 非 Git 文件读取和文本搜索可并发。

只读 Git 选项（Read-only Git options）:

- 状态检查优先：`git --no-optional-locks status --short --branch`
- diff 检查优先：`git -c diff.autoRefreshIndex=false diff <range>`
- 最终提交前如需精确状态，可串行执行普通 `git status --short --branch`。

Index lock 恢复策略（Index lock recovery）:

- lock 路径解析命令：`git rev-parse --git-path index.lock`
- 删除前检查：精确路径、文件存在、大小/mtime 稳定、无活跃或未知归属 Git 进程。
- 删除范围：只删除解析出的精确 `index.lock`，禁止通配符、递归删除和删除其它 `.lock`。
- 删除后检查：串行 `git --no-optional-locks status --short --branch`。

Git Lock Recovery Log:

| 时间（Time） | lock 路径（Lock path） | 文件大小/mtime（Size/mtime） | Git 进程检查（Process check） | 操作（Action） | 后续 status（Follow-up status） |
| --- | --- | --- | --- | --- | --- |
| not-needed |  |  |  |  |  |

提交策略（Commit policy）:

- implementation approval is not commit authorization。
- 当前提交授权：not_authorized。
- 若用户后续授权提交，使用 `git commit -F .harness/tasks/2026-07-08/feature/planner-research-gate-optimization/tmp/commit-message.txt` 或等价 ignored 运行时路径。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: no
- 未合回时代码停留在（If not merged, code remains on）: harness/feature
- 合并前需要用户确认（User confirmation needed before merge）: yes

分支安全（Branch safety）:

- 切换前已检查工作区: planning stage checked status
- 不自动 stash: yes
- 不自动 rebase: yes
- 不自动 reset: yes

热修复插入（Hotfix interruption）:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支。
- 决策: not-applicable

未解决问题（Open issues）:

- 无 blocking Git 问题。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| PowerShell | 读取文件、有限目录操作 | Planning/All | available | low | shell_command | implicit |
| Python | plan_check、py_compile、JSONL/YAML parse | Stage 2/3/6 | available | medium | ast.parse for cache issues | implementation approval needed |
| Git | 串行状态/diff/提交 | All | available | medium | no-op until approved | commit needs explicit authorization |
| web search | 在线调研官方/一手资料 | Planning/Stage 1 | available in current session | medium | blocked-by-access + assumption | already used for planning |
| apply_patch | 文件编辑 | Implementation | available | low | smaller patches | implementation approval needed |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- no

process-manager skill 是否存在（process-manager skill available）:

- not-needed

规则结论（Rule decision）:

- 本任务只涉及有限命令、文档和脚本检查，不启动 dev server、worker 或 watcher。
- 如果实施中临时发现必须启动长期进程，必须暂停并按 executor 的 process-manager 规则处理。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | not-applicable | all | none | none | none | none | none |

禁止 shell 后台启动确认（No shell background start）:

- passed

历史视图需求（Needs `pm_list --history`）:

- no

证据保留位置（Evidence retention location）:

- `execution-plan.md` / ledger / ignored tmp if needed

日志沉淀确认（Log evidence persisted）:

- not-applicable

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前复查本节。
- 上下文压缩或中断恢复后复查本节和 `Resume Summary`。

## 验证（Validation）

必需验证（Required）:

- planner plan check。
- Python 脚本语法检查。
- 空模板 strict 负例。
- Research Gate 正负例 fixture。
- JSONL/YAML parse 和 ID 唯一检查。
- executor status/final smoke，如修改 executor 脚本。
- `git -c diff.autoRefreshIndex=false diff --check`。

已执行（Executed）:

- 命令/工具（Command/tool）: `harness_plan_check.py --plan skills\complex-coding-planner\templates\execution-plan.md`
- 结果（Result）: 当前实现返回 PASS，作为缺陷复现证据。
- 证据（Evidence）: 本计划 Research Gate 和 Context。
- 覆盖范围（Covers）: 当前缺口确认。
- 未覆盖（Not covered）: 尚未实现修复。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | 读取 planner/executor 文件和 Git 状态 | passed | 当前规则基线 | 未实现修复 | 本计划 Context/Git | none |
| Planning | 空模板 plan_check | defect-confirmed | 结构检查不足 | 修复后重跑 | 命令输出 PASS | Stage 2 |
| Stage 1 | 文档检索 Research Gate | passed | 规则和模板 | 脚本强制已由 Stage 2 覆盖 | SKILL/workflow/template grep | none |
| Stage 2 | strict plan_check 正负例 | passed | 门禁强制 | executor drift 已由 Stage 4 覆盖 | new plan pass; template fail; --allow-template pass; AST parse | none |
| Stage 3 | eval parse | passed | 回归覆盖 | 实际 agent forward test | planner eval ID/expected aligned | none |
| Stage 4 | executor drift 文档/脚本 smoke | passed | 执行期回退 | hook | executor grep + eval ID/expected aligned | none |
| Stage 5 | README/CHANGELOG/diff check | passed | 文档同步 | 用户安装 | docs grep + diff check | none |
| Stage 6 | 全量验证和 final gate | passed | 最终交付 | 未授权提交 | py_compile, plan/status/loop, ledger, evals, diff check | none |

可选验证（Optional）:

- 使用子 agent forward-test planner，但需要额外时间；不作为第一轮必需项。

产物（Artifacts）:

- 截图（Screenshot）: not-applicable
- 日志（Log）: 可写入 ledger 或计划证据表
- Trace: not-applicable
- 报告（Report）: 本计划

未覆盖（Not covered）:

- 不验证真实联网失败场景的系统级权限，只通过 `blocked-by-access` 规则和 fixture 覆盖。

无法执行时（If unable to run）:

- 必须记录原因、影响、替代证据，不得声称通过。

## 文档（Documentation）

必需更新（Required updates）:

- `README.md`：说明 Research Gate 和 strict plan check。
- `CHANGELOG.md`：记录 planner 调研机制增强。
- `evals/*/README.md`：如新增 case，需要同步意图。

Changelog 计划（Changelog plan）:

- 在当前日期下新增 `feat(planner): 强化不确定问题调研门禁` 或等价条目。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `planning-workflow.md` | yes | Research Gate 独立章节和相关门禁条目 | 完整读取/检索 |
| `execution-plan.md` template | yes | Research Gate、Plan Quality、Readiness | 完整读取/plan_check |
| `harness_plan_check.py` | yes | helper 函数、strict check、CLI flag | py_compile + 正负例 |
| eval JSONL/YAML | no | 单条 case | parse 检查 |
| README/CHANGELOG | no | 章节/日期块 | diff check |
| executor workflow | no | Research Drift Gate 章节 | 文档检索 |

写入规则（Write rules）:

- 优先局部 `apply_patch`，不整文件重写。
- 单次 patch 新增内容建议不超过 120 行，硬上限 200 行。
- 目标文件超过 500 行时默认禁止整文件重写。
- 写完后重新读取完整目标文件或关键章节检查一致性。

整体复查（Whole-file review）:

- 检查 Research Gate 在 SKILL、workflow、template、check、eval、README 之间一致。
- 检查 `Plan Quality Gate` 和 `Readiness Gate` 不再允许 research 缺失。

patch 失败处理（Patch failure handling）:

- 读取目标文件确认是否有部分写入。
- 缩小 patch 到单章节或单函数后重试。
- 不用 shell 拼接绕过 patch 失败。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| Q-001 | no | closed | 是否所有 managed 任务都强制联网 | 不强制；按触发条件进入 `online-required` | Research Gate |
| Q-002 | no | closed | 是否立即启用 hook 阻断 | 不启用；先强化 CLI gate 和 eval | Non-goals |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | passed | Context Evidence levels |
| Research Gate 已完成 | passed | Research Gate section |
| 影响面矩阵完整（Impact matrix complete） | passed | Impact Matrix |
| 候选方案比较充分（Options compared enough） | passed | Options A/B/C |
| 每阶段可独立验证（Stages independently verifiable） | passed | Stage Contracts |
| 方案变更触发条件清楚（Reapproval triggers clear） | passed | Decision |
| 用户批准摘要可记录（Approval summary ready） | passed | Plan Approval |

质量结论（Quality result）:

- `passed`

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- `passed`

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 初始方案可能只补文档，不解决空模板 PASS | 选择方案 B，增加 strict plan_check | passed |
| 优化（Optimizations） | 所有任务强制联网过重 | 采用触发式 `online-required` | passed |
| 缺失项（Missing items） | executor 执行期发现新不确定项未覆盖 | 增加 Stage 4 Research Drift Gate | passed |
| 风险（Risks） | strict check 可能误拦旧计划 | 加 `--allow-template` 和兼容策略 | passed |
| 一致性（Consistency） | 需要和 ledger/attestation/loop 规则衔接 | 阶段 6 纳入最终证据和 attestation | passed |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑: completed
- `Plan Self-Review` 是否需要重跑: completed
- `Readiness Gate` 是否需要重跑: completed
- 原因: 首次完整计划已包含 Research Gate 和自查修复项。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | passed | Problem |
| 上下文已收集（Context collected） | passed | Context |
| Research Gate 已通过 | passed | Research Gate |
| 候选方案已比较（Options compared） | passed | Options |
| 决策已记录（Decision recorded） | passed | Decision |
| 实施阶段已细化（Implementation stages detailed） | passed | Implementation Plan |
| 环境已确认（Environment confirmed） | passed | Environment |
| Git 上下文已确认（Git context confirmed） | passed | Git Context |
| 工具已确认（Tooling confirmed） | passed | Tooling |
| 验证已确认（Validation confirmed） | passed | Validation |
| 最终交付证据已规划（Final delivery evidence planned） | passed | Stage 6 |
| 文档更新已确认（Documentation updates confirmed） | passed | Documentation |
| 风险已识别（Risks identified） | passed | Risks and rollback |
| 规划自查已通过（Plan self-review passed） | passed | Plan Self-Review |
| 阻塞问题已关闭（Blocking questions closed） | passed | Questions And Overrides |

就绪结论（Readiness result）:

- `passed`

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 2026-07-08 用户回复“批准，进入执行阶段”。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: Stage 1-6，按本计划实现 Research Gate、strict plan check、eval、executor Research Drift Gate、文档和最终验证。
- 阶段提交授权（Stage commit authorization）: not_authorized
- 工具/MCP 授权（Tool/MCP authorization）: finite shell/Python/Git read/diff、apply_patch、必要时 web research；长期进程不需要。
- 文档更新授权（Documentation authorization）: README、CHANGELOG、workflow、template、eval docs within approved scope.

提交策略（Commit policy）:

- `not_authorized`

## 方案变更门禁（Plan Amendment Gate）

需要重新批准（Requires reapproval）:

- approved scope 改变: yes
- 阶段边界、顺序或 Stage Contract 改变: yes
- 必需验证、工具授权、长期进程策略或提交策略改变: yes
- 风险等级、公共接口、数据结构、权限、依赖或兼容性假设改变: yes
- attestation mismatch 且无法证明是预期文档更新: yes

无需重新批准的记录（No-reapproval records）:

| 时间（Time） | 变更（Change） | 原因（Reason） | 证据（Evidence） |
| --- | --- | --- | --- |
| not-yet |  |  |  |

## 执行控制（Execution Control）

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

剩余阶段（Remaining stages）:

- none

下一步自动动作（Next automatic action）:

- none

当前停止条件（Current stop condition）:

- completed

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no after implementation approval, unless Stop Condition is active

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
- 如果 `active-task.json` 和本节冲突，必须以本节为准修正 `active-task.json`。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | completed | 已同步 planner/executor 最新规则，确认调研门禁缺口并制定方案，用户已批准实施 | planner context read + Git status + external source checked | 本计划 + 用户批准 | continue Stage 1 |
| Stage 1 | completed | planner Research Gate 规则和模板 | passed | SKILL/workflow/template Research Gate 检索 + plan_check | continue Stage 2 |
| Stage 2 | completed | strict plan_check | passed | new plan pass; template default fail; template allow pass; ast parse clean | continue Stage 3 |
| Stage 3 | completed | planner eval 和 fixture | passed | JSONL parse, ID uniqueness and expected key coverage | continue Stage 4 |
| Stage 4 | completed | executor Research Drift Gate | passed | executor eval IDs align + workflow/SKILL grep | continue Stage 5 |
| Stage 5 | completed | docs/changelog/environment | passed | README/CHANGELOG/environment grep + diff check | continue Stage 6 |
| Stage 6 | completed | 整体验证和交付证据 | passed | py_compile, plan_check, template negative, eval alignment, status/loop, ledger summary, diff check | final delivery |

## Ledger Evidence

Ledger policy:

- append-only-after-approval

Ledger 文件（Ledger file）:

- `.harness/tasks/2026-07-08/feature/planner-research-gate-optimization/ledger.jsonl`

Ledger 摘要（Ledger summary）:

| 字段（Field） | 值（Value） |
| --- | --- |
| entries | 18 |
| stages_completed | Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6 |
| current_stage | Completed |
| last_blocking_reason | none |
| last_heartbeat | none |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | passed | plan approved; no blocking decision | finite tools available | not-applicable | passed | passed |
| Stage 2 | passed | Stage 1 completed | Python available | not-applicable | passed | passed |
| Stage 3 | passed | Stage 2 completed | eval files available | not-applicable | passed | passed |
| Stage 4 | passed | Stage 3 completed | executor workflow/eval files available | not-applicable | passed | passed |
| Stage 5 | passed | Stage 4 completed | docs available | not-applicable | passed | passed |
| Stage 6 | passed | Stage 5 completed | validation tools available | not-applicable | passed | passed |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1-6 | yes | yes | passed | not-applicable | passed | yes | not_authorized | passed |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证已完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1-5 | yes | yes | passed | not_authorized | yes | no | no | yes | yes | no | continue Stage N |
| Stage 6 | yes | yes | passed | not_authorized | no | completed | no | yes | yes | yes | final delivery |

结论（Decision）:

- 等待用户审批；不得开始实现。

规则（Rules）:

- 如果还有 pending stage 且没有停止条件，也不需要重新批准，executor 必须继续下一阶段。
- 进入下一阶段前必须同步 `Execution Control`、`Resume Summary` 和 `.harness/active-task.json`。

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Planning | 无 blocking finding；空模板 PASS 已作为待修 defect 纳入 Stage 2 | follow-up | pending implementation |
| Stage 1-6 | 未发现 blocking/major finding；`py_compile` 普通权限写 `__pycache__` 失败后按权限规则提权通过 | minor | 已记录验证路径和权限原因 |

## 恢复摘要（Resume Summary）

Resume Packet:

```json
{
  "task_id": "2026-07-08-feature-planner-research-gate-optimization",
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "current_stage": "Completed",
  "remaining_stages": [],
  "next_automatic_action": "none",
  "stop_condition": "completed",
  "ledger_entries": 18,
  "last_blocking_reason": "",
  "attestation_status": "checked"
}
```

- 整体目标（Overall goal）: 强化 planner 不确定问题调研门禁，并让 executor 处理执行期研究漂移。
- 执行模式（Execution mode）: run-to-completion.
- 整体任务状态（Overall status）: completed.
- 已完成阶段（Completed stages）: Planning research and plan drafting, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6.
- 当前阶段（Current stage）: Completed.
- 剩余阶段（Remaining stages）: none.
- 最新 commit（Latest commit）: `bcc6fe1` from previous task; this task has no commit.
- 下一步自动动作（Next automatic action）: none.
- 当前停止条件（Current stop condition）: completed.
- 状态来源（State source of truth）: execution-plan.md.
- 长期进程规则（Process manager rule）: not required.
- 未覆盖/风险（Not covered/risks）: strict check 兼容性需要实施期用 fixture 验证。
- 不得停止说明（Do not stop note）:
  - 实施获批后，阶段边界不是停止条件；executor 必须持续推进到 final gate，除非 Stop Condition active。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 若用户后续授权提交，使用 `git commit -F .harness/tasks/2026-07-08/feature/planner-research-gate-optimization/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | not_committed | commit not authorized | not yet |
| Stage 1-6 | dev-skills | not_committed | commit not authorized | CHANGELOG updated |

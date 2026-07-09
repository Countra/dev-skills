# GitLab PAT Ops 模块化能力拆分与 issue/MR 扩展执行计划

## 执行控制快照（Execution Control Snapshot）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- completed

当前阶段（Current stage）:

- Final

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

- final delivery complete

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

执行方（Executor）:

- 实施阶段使用 `complex-coding-executor`；本规划阶段不得直接实现。

## 执行契约（Execution Contract）

```json
{
  "contract_version": 1,
  "task_id": "2026-07-09-feature-gitlab-pat-ops-modular-capabilities",
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "approval_status": "approved",
  "approved_contract_hash": "external:attestation.json",
  "current_stage_id": "Final",
  "remaining_stage_ids": [],
  "stop_condition": "none",
  "commit_authorization": "authorized_final_commit",
  "ledger_policy": "append-only-after-approval",
  "single_writer": "current executor session",
  "reapproval_required": false
}
```

契约规则（Contract rules）:

- 修改 approved scope、stage 边界、验证策略、风险等级、工具授权或提交策略时，必须进入 `Plan Amendment Gate`。
- 用户已在 2026-07-09 明确批准进入实现，并授权最终阶段完成、代码审查等步骤完成后提交代码。

## 目标条件（Goal Condition）

- 所有 approved stages 均完成，且最终状态回写到本计划和 `.harness/active-task.json`。
- `gitlab-pat-ops` 的 GitLab 操作从场景脚本倾向调整为模块化能力：项目、issue、模板、标签、里程碑、成员、分支、notes、MR 等职责可独立调用，组合流程由 skill 文档引导。
- 支持在指定仓库中创建 issue，并能使用项目内现成 issue 模板，指定标题、描述来源、标签、里程碑 ID、assignee、due date、confidential、issue_type 等安全范围内参数。
- 支持受保护地关闭或重新打开 issue / MR；所有写操作默认 dry-run，真实请求必须 `--confirm`。
- `gl_capabilities.py`、`references/api-map.md`、`references/workflow.md`、`references/security.md`、tests、eval prompts 和 changelog 同步更新。
- 必需验证已执行，或无法执行项已记录原因、影响和替代证据；live 写入只允许 `codex_test`。
- final gate / 最终交付门禁通过，提交授权状态明确；未授权提交时必须记录未提交原因。
- 无 open blocking decision、无未关闭 blocking/major review finding。

## 规划循环协议（Planning Loop Protocol）

- 本任务为 managed：涉及外部 GitLab API、已有 skill 架构、受保护写操作、验证和后续提交策略。
- 调研 findings 已写入 `Context`、`Research Gate`、`Standards Discovery Gate` 和阶段参考。
- 重大决策前必须重读目标、用户约束、候选方案、Decision、影响面和 reapproval triggers。
- rejected options 必须保留放弃原因，避免恢复后重复探索。
- Readiness 前必须重新运行 `Plan Quality Gate`、`Plan Self-Review` 和 `Readiness Gate`。

## 执行循环协议（Executor Work Loop）

- 每个阶段开始先读取 `Execution Contract`、`Resume Packet`、Stage Contract、`references/security.md` 和上一阶段 findings。
- 先做只读/离线改动，再做 dry-run，最后只在允许的 `codex_test` 边界内做 live write smoke。
- 每次阶段动作后更新 ledger/progress；失败动作必须记录 attempt、命令或工具、失败原因、影响和下一策略。
- Stage Transition Gate 通过且仍有 pending stage 时，下一动作必须是 `continue Stage N`。
- 只有满足 `Goal Condition` 后才能进入最终交付。

## 问题定义（Problem）

目标（Goal）:

- 进一步拆分 `gitlab-pat-ops` 的 GitLab 操作能力，避免围绕“issue 评论”等一次性场景固化流程。
- 让 skill 可以按“搜索仓库 -> 获取项目信息 -> 查询 issue/MR/模板/标签/里程碑/成员/分支 -> 拉取详情 -> 执行受保护写操作”的方式自由组合。
- 扩展 GitLab 官方 API 支持：创建 issue、选择 issue 模板、指定里程碑、关闭 issue / MR，并补充相关可发现能力。

非目标（Non-goals）:

- 不实现删除项目、删除文件、删除分支、删除 issue/MR/note、force push、merge/approve MR、权限/成员变更、token 管理、CI/CD 管理、批量跨仓库写入。
- 不新增后台服务；本轮继续采用脚本型 skill。
- 不把 GitLab UI 的所有模板继承逻辑一次性复刻到脚本；v1 只保证项目仓库中 `.gitlab/issue_templates/*.md` 的发现与读取。
- 不在规划阶段改代码。

验收标准（Acceptance）:

- 计划明确模块边界、脚本职责、写操作安全策略、验证策略和提交策略。
- 后续实现完成后，能力边界脚本能准确说明新增支持能力与仍禁止能力。
- 后续实现完成后，用户可通过独立脚本组合完成 issue 评论、issue 创建、模板选择、里程碑选择、issue/MR 关闭等流程。

约束（Constraints）:

- 环境变量只使用 `SKILL_GITLAB_BASE_URL`、`SKILL_GITLAB_PAT`，并兼容 `SKILL_GITLAB_TOKEN`；不得读取通用 `GITLAB_TOKEN`。
- token 不得写入命令、日志、`.harness`、测试 fixture 或 commit message。
- 写操作必须 dry-run 默认、`--confirm` 才真实发送。
- live 写入 smoke 只允许在 `codex_test` 测试仓库内进行。
- 新增或修改注释必须使用中文。

待确认项（Open uncertainties）:

- 无 blocking 问题；执行阶段可以按本计划的保守边界推进。

## 调研门禁（Research Gate）

研究模式（Research mode）:

- online-required

触发原因（Why this mode）:

- GitLab REST API、PAT scopes、issue/MR 状态变更、description templates、labels、milestones、members、branches 都属于可能随 GitLab 版本变化的外部服务事实，必须优先确认官方文档。

不确定项清单（Uncertainty inventory）:

| ID | 问题（Question） | 类型（Type） | 是否需要在线搜索（Online required） | 处理结果（Resolution） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- |
| U-001 | GitLab issue 创建 endpoint、参数、里程碑和 issue_type 支持 | external-service | yes | confirmed by official Issues API | Stage 4 参数和安全边界 |
| U-002 | issue 关闭/重开是否通过 update issue 的 `state_event` | external-service | yes | confirmed by official Issues API | Stage 5 issue 状态命令 |
| U-003 | MR 关闭/重开是否通过 update MR 的 `state_event` | external-service | yes | confirmed by official Merge Requests API | Stage 5 MR 状态命令 |
| U-004 | issue 模板目录和默认分支要求 | external-service | yes | confirmed by official Description templates docs | Stage 3 模板脚本 |
| U-005 | 标签和里程碑如何独立查询以支持创建前选择 | external-service | yes | confirmed by official Labels and Milestones API | Stage 2/4 预检 |
| U-006 | assignee 和 MR 分支选择需要哪些只读发现 API | external-service | yes | confirmed by official Project Members, Users, Branches API | Stage 2 只读模块 |

搜索记录（Search log）:

| 查询/来源（Query/source） | 工具（Tool） | 日期（Date） | 结果（Result） | 后续动作（Next action） |
| --- | --- | --- | --- | --- |
| GitLab Issues API | web official docs | 2026-07-09 | issue 创建、列表、更新、`state_event`、labels、milestone_id、issue_type 已确认 | Stage 4/5 使用 |
| GitLab Merge Requests API | web official docs | 2026-07-09 | MR update 支持 `state_event` close/reopen，MR metadata 参数已确认 | Stage 5 使用 |
| GitLab Description templates | web official docs | 2026-07-09 | issue 模板位于 `.gitlab/issue_templates/*.md`，需 `.md` 且在默认分支 | Stage 3 使用 |
| GitLab Project milestones / Labels / Members / Branches / Users API | web official docs | 2026-07-09 | 可独立查询里程碑、标签、成员、分支、用户 | Stage 2 使用 |

来源矩阵（Source matrix）:

| 结论（Claim） | 来源类型（Source type） | URL/路径（URL/path） | 是否官方/一手（Official/primary） | 访问日期（Accessed） | 可信度（Confidence） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- | --- |
| 当前 skill 已有项目、搜索、仓库文件、issue、notes、MR、受保护项目/MR 创建和评论回复能力 | local | `skills/gitlab-pat-ops/SKILL.md`, `references/api-map.md`, `gl_capabilities.py` | yes | 2026-07-09 | high | 确定扩展起点 |
| 当前 issue 创建、关闭 issue/MR 尚未支持且属于受保护写操作 | local | `gl_capabilities.py`, `references/security.md` | yes | 2026-07-09 | high | 需要更新安全边界 |
| issue 创建使用 `POST /projects/:id/issues`，`title` 必需，支持 description、labels、milestone_id、issue_type 等参数 | official | https://docs.gitlab.com/api/issues/ | yes | 2026-07-09 | high | Stage 4 |
| issue 更新使用 `PUT /projects/:id/issues/:issue_iid`，`state_event=close/reopen` 可关闭/重开 | official | https://docs.gitlab.com/api/issues/ | yes | 2026-07-09 | high | Stage 5 |
| MR 更新使用 `PUT /projects/:id/merge_requests/:merge_request_iid`，`state_event` 支持 close/reopen | official | https://docs.gitlab.com/api/merge_requests/ | yes | 2026-07-09 | high | Stage 5 |
| issue 模板应为 `.md` 并保存在项目默认分支的 `.gitlab/issue_templates/` | official | https://docs.gitlab.com/user/project/description_templates/ | yes | 2026-07-09 | high | Stage 3 |
| 项目里程碑、标签、成员、分支、用户搜索均有独立 REST API | official | GitLab milestones/labels/project_members/branches/users docs | yes | 2026-07-09 | high | Stage 2 |

调研结论（Research result）:

- `passed`。外部 API 关键事实均来自 GitLab 官方文档；后续实现不得凭记忆扩展未查证 endpoint。

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）:

- online-required

技术栈清单（Technology inventory）:

| 类型（Type） | 发现（Finding） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 语言（Language） | Python 3 标准库脚本，Markdown 文档，JSON/JSONL eval | local source | 新增脚本沿用标准库、argparse、urllib、unittest |
| 框架（Framework） | 无 Web 服务，无后台服务 | local source | 不新增服务和进程管理 |
| API/架构类型（API/architecture） | GitLab REST API v4，PAT header `PRIVATE-TOKEN` | GitLab official docs, `gitlab_common.py` | 所有 endpoint 通过共享 client 调用 |
| 工具链（Toolchain） | PowerShell、Python、unittest、py_compile、planner/executor check | `.harness/environment.md` | 验证命令以有限命令为主 |

规范来源矩阵（Standards source matrix）:

| 规范来源（Standard source） | 类型（Type） | 官方/一手（Official/primary） | 适用边界（Applicability） | 访问日期（Accessed） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- |
| `AGENTS.md` 全局开发规则 | project | yes | 中文注释、最小变更、验证真实性、commit `-F` 格式 | 2026-07-09 | 所有阶段 |
| `skills/gitlab-pat-ops/references/security.md` | project/security | yes | token、dry-run、confirm、live smoke 边界 | 2026-07-09 | 写操作阶段 |
| GitLab REST API docs | API | yes | endpoint、参数、分页、PAT 认证 | 2026-07-09 | 所有 API 脚本 |
| Google Python Style Guide | language | yes | Python 脚本命名、异常、可读性作为辅助参考 | 2026-07-09 | 只在不冲突时参考；项目现有风格优先 |
| Python 标准库文档 | language | yes | argparse、urllib、unittest 行为 | 2026-07-09 | 脚本实现和测试 |
| Google Cloud API Design Guide / AIP design patterns | architecture/API | yes | 仅参考“资源导向、职责清晰、幂等/状态变更边界”思想 | 2026-07-09 | 模块边界和 CLI 命令语义 |

standards index:

- 路径或章节（Path/section）: 本计划内联 standards index；不另建 artifact。
- 摘要（Summary）: 项目内安全与开发规则优先；官方 GitLab 文档决定 endpoint 和参数；外部代码风格规范只作为辅助，不覆盖现有脚本风格。
- 未覆盖或 blocked-by-access（Not covered / blocked）: 未查证 GitLab group/instance 级 description template 的可读 API；v1 不承诺自动发现继承模板。

规范发现结论（Standards result）:

- `passed`

## 开发质量门禁（Development Quality Gate）

质量范围（Quality scope）:

| 维度（Dimension） | 规划结论（Plan） | 阶段映射（Stage mapping） | 验证映射（Validation mapping） |
| --- | --- | --- | --- |
| 代码标准（Code standards） | 沿用现有脚本结构、中文注释、标准库、JSON 输出 | Stage 1-6 | py_compile、unittest、review |
| 静态质量（Static quality） | 新增脚本必须可 import、CLI parser 可测、dry-run 可测 | Stage 2-6 | `python -B -m unittest discover ...` |
| 架构边界（Architecture boundaries） | `gitlab_common.py` 管 HTTP/分页/脱敏；各 `gl_*` 只管单资源职责 | Stage 1-5 | code review + capability matrix |
| 设计模式取舍（Design pattern decision） | 采用命令模式式 CLI 子命令和薄资源模块；不引入类层级/服务进程 | Stage 1 | review |
| 低耦合（Low coupling） | 不做一次性 workflow 脚本；组合逻辑放入 skill workflow 文档 | Stage 2-6 | 文档示例和脚本命令独立测试 |
| 高内聚（High cohesion） | issue、MR、labels、milestones、templates、members、branches 分别聚合资源相关命令 | Stage 2-5 | tests 按模块覆盖 |

过度设计防护（Overengineering guard）:

- 不引入后台服务、数据库、SDK 依赖或跨脚本状态存储。
- 不把所有 GitLab endpoint 一次性封装；只加入本任务组合流程自然需要的模块。
- 不创建“一键处理 issue 评论/创建/关闭”的总控脚本，避免退回一次性场景化设计。

开发质量结论（Development quality result）:

- `passed`

## 上下文（Context）

本地代码（Local code）:

- `skills/gitlab-pat-ops/scripts/gitlab_common.py`: 已有 `GitLabClient`、分页、dry-run preview、正文读取、错误脱敏和公共 CLI 参数。
- `skills/gitlab-pat-ops/scripts/gl_issues.py`: 目前只读 `list/get/related-mrs/closed-by`。
- `skills/gitlab-pat-ops/scripts/gl_mrs.py`: 已有 `list/get/notes/create`，创建 MR 默认 dry-run。
- `skills/gitlab-pat-ops/scripts/gl_notes.py`: 已有 issue/MR notes 列表与受保护回复。
- `skills/gitlab-pat-ops/scripts/gl_capabilities.py`: 当前把 create_issue、close_issue_or_mr 列为 unsupported。
- `skills/gitlab-pat-ops/tests/test_commands.py`: 已用 FakeClient 测 dry-run 和 confirm，不需要真实 GitLab。

本地文档（Local docs）:

- `skills/gitlab-pat-ops/SKILL.md`: 当前要求 doctor first、只在不确定能力边界时运行 `gl_capabilities.py`。
- `references/api-map.md`: 当前 API 映射未覆盖 issue 创建、模板、标签、里程碑、成员、分支、关闭状态。
- `references/workflow.md`: 当前流程偏向项目查询、issue 评论、MR 查询和仓库文件读取。
- `references/security.md`: 当前禁止关闭 issue/MR；实施后必须按新受保护边界更新。
- `.harness/environment.md`: 记录了 `SKILL_GITLAB_BASE_URL`、`SKILL_GITLAB_PAT`、`codex_test` live write 限制。

外部来源（External sources）:

- GitLab Issues API: https://docs.gitlab.com/api/issues/
- GitLab Merge Requests API: https://docs.gitlab.com/api/merge_requests/
- GitLab Description templates: https://docs.gitlab.com/user/project/description_templates/
- GitLab Project milestones API: https://docs.gitlab.com/api/milestones/
- GitLab Labels API: https://docs.gitlab.com/api/labels/
- GitLab Project members API: https://docs.gitlab.com/api/project_members/
- GitLab Branches API: https://docs.gitlab.com/api/branches/
- GitLab Users API: https://docs.gitlab.com/api/users/
- GitLab PAT docs: https://docs.gitlab.com/user/profile/personal_access_tokens/

用户约束（User constraints）:

- 使用 `complex-coding-planner` 指定详细规划；当前只规划。
- 后续执行使用 `complex-coding-executor`。
- 模块化优先，组合使用交给 skill 自行编排。
- 后续需要支持指定仓库创建 issue、选择现成模板、指定里程碑、关闭 issue / MR 等。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 当前能力边界 | read | local source + gl_capabilities output | 确定扩展差距 |
| GitLab endpoint 和参数 | external | official GitLab docs | 确定实现范围 |
| live write 限制 | confirmed | user/environment.md/security.md | 验证策略 |

## 候选方案（Options）

### 方案 A：最小补丁（Minimal Change）

- 做法（How）: 只在 `gl_issues.py` 加 `create`，在 `gl_issues.py`/`gl_mrs.py` 加 `close`。
- 优点（Pros）: 文件少、实现快。
- 缺点（Cons）: 标签、里程碑、模板、成员、分支仍需要靠人肉查找或临时搜索；容易形成新的场景化命令。
- 风险（Risks）: issue 创建时未知 label 会被 GitLab 自动创建，缺少独立预检；模板选择无法复用；后续组合能力不足。
- 验证（Validation）: 单测较少，但无法覆盖用户要求的模块化流程。
- 回滚（Rollback）: 回退少量命令即可。

### 方案 B：资源模块化扩展（Structured Resource Modules）

- 做法（How）: 保持共享 client，按 GitLab 资源面拆分新增/增强 `gl_labels.py`、`gl_milestones.py`、`gl_members.py`、`gl_branches.py`、`gl_issue_templates.py`，并在 `gl_issues.py`、`gl_mrs.py` 增加受保护写命令。
- 优点（Pros）: 与用户要求一致；每个脚本职责单一；组合灵活；便于后续扩展和能力边界维护。
- 缺点（Cons）: 文件和测试数量增加，需要同步文档/eval。
- 风险（Risks）: 阶段范围变大；若一次性加入过多 GitLab endpoint 容易膨胀。
- 验证（Validation）: 每个资源模块可独立 fake client 测试，并可在 `codex_test` 做受控 live smoke。
- 回滚（Rollback）: 按新增脚本和命令逐阶段回退，保留未受影响现有能力。

### 方案 C：后台服务或统一高级 workflow 脚本

- 做法（How）: 类似服务端能力网关或一键 workflow，把项目定位、issue 搜索、模板和写入串成高层任务。
- 优点（Pros）: 对单一任务入口友好。
- 缺点（Cons）: 与“模块化、组合交给 skill”目标冲突；需要长期进程或状态管理；能力边界更难审计。
- 风险（Risks）: 复杂度过高，容易把 GitLab 操作做成黑盒。
- 验证（Validation）: 需要更多端到端测试。
- 回滚（Rollback）: 回滚成本高。

## 决策（Decision）

选择方案（Chosen option）:

- 方案 B：资源模块化扩展。

原因（Why）:

- 用户明确要求尽可能分离任务职能，避免聚焦一次性场景。
- GitLab 官方 API 本身按资源组织，脚本按资源拆分更自然。
- 现有 `gitlab_common.py` 已提供共享 HTTP、分页、dry-run、脱敏基座，不需要新增服务。

影响（Impact）:

- 新增多个只读发现脚本，增强 `gl_issues.py` 和 `gl_mrs.py` 的受保护写命令。
- 更新能力边界、API map、workflow/security 文档、eval 和 tests。
- skill 使用方式从“固定示例”扩展为“资源能力 + 组合流程示例”。

可逆性（Reversibility）:

- 中等。新增脚本可独立删除；对现有命令保持兼容，不改变已有参数语义。

变更条件（Change conditions）:

- 若 GitLab 官方文档或目标实例版本不支持某 endpoint，相关能力降级为 blocked/follow-up，不强行实现。
- 若用户要求真实关闭非测试仓库 issue/MR，必须重新确认目标和风险。

方案变更触发条件（Reapproval triggers）:

- 引入后台服务、第三方 SDK、持久缓存或数据库。
- 新增删除、merge、approve、权限管理、token 管理、CI/CD 管理、批量跨仓库写入能力。
- 扩大 live write smoke 到 `codex_test` 之外。
- 改变提交授权策略或阶段数量/边界。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | GitLab REST endpoint map | medium | fake client + live read/dry-run | api-map |
| 数据结构（Data model） | yes | JSON body builders, capability JSON | medium | unit tests | capabilities docs |
| 前端交互（Frontend interaction） | no | none | low | not applicable | no |
| 配置/环境（Config/environment） | yes | skill env docs | low | doctor offline/live | SKILL/security |
| 兼容性（Compatibility） | yes | existing CLI commands | medium | existing tests stay passing | workflow |
| 测试（Tests） | yes | `tests/test_commands.py`, maybe new tests | medium | unittest/py_compile | eval prompts |
| 文档（Documentation） | yes | SKILL/references/README/CHANGELOG/evals | medium | doc review | yes |
| 代码标准（Code standards） | yes | Python scripts | medium | py_compile/review | standards section |
| 架构设计（Architecture/design） | yes | resource module split | medium | module responsibility review | workflow/api-map |

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：能力边界与共享 API 基座整理

目标（Goal）:

- 在不破坏现有命令的前提下，为新增资源模块和受保护写操作整理共享能力。

做法（How）:

- 复读 `gitlab_common.py`、现有脚本、tests 和 security 文档。
- 判断是否需要在 `gitlab_common.py` 增加通用 helper，例如逗号列表解析、整数列表解析、日期字符串轻量校验、description 文件读取复用、dry-run preview body 摘要。
- 保持 helper 小而通用，不引入 GitLab SDK 或后台服务。

原因（Why）:

- issue 创建、MR 创建、close/reopen 都需要一致的参数构造、脱敏、dry-run 和错误处理。

位置（Where）:

- 文件/模块（Files/modules）: `skills/gitlab-pat-ops/scripts/gitlab_common.py`
- API/配置（APIs/configs）: 无新增环境变量
- 测试/文档（Tests/docs）: `tests/test_common.py`, `references/security.md`

参考来源（References）:

- 本地 `gitlab_common.py`
- GitLab PAT docs
- `AGENTS.md`

适用规范（Standards applied）:

- 项目现有 Python 风格、中文注释、最小变更。

开发质量检查（Development quality checks）:

- helper 单一职责；错误消息不泄露 token；不改变现有 public CLI 行为。

验证（Validation）:

- `python -B -m py_compile skills\gitlab-pat-ops\scripts\gitlab_common.py`
- `python -B -m unittest discover -s skills\gitlab-pat-ops\tests`

风险和回滚（Risks and rollback）:

- 风险: 修改共享 client 影响所有脚本。
- 回滚: 若 helper 影响范围过大，改为在调用脚本局部实现。

阶段契约（Stage Contract）:

- 范围（Scope）: 共享 helper 和安全基座。
- 允许修改（Allowed changes）: `gitlab_common.py`、对应测试、security 文档少量补充。
- 禁止修改（Forbidden changes）: 改变 env 名称、取消 dry-run、引入第三方依赖。
- 进入条件（Entry checks）: 读取本计划、SKILL、安全文档、现有测试。
- 退出条件（Exit checks）: 共享 helper 可测，现有测试通过或失败原因记录。
- 适用规范（Standards applied）: Standards Discovery Gate 全部适用。
- 开发质量检查（Development quality checks）: API 边界、错误处理、脱敏 review。
- 必需验证（Required validation）: py_compile + unittest。
- 是否预期提交（Commit expected）: no，除非用户另行授权提交。

### 阶段 2（Stage 2）：只读发现能力模块化扩展

目标（Goal）:

- 增加创建 issue 和操作 MR/issue 前所需的独立发现能力。

做法（How）:

- 新增 `gl_labels.py`: `list/get/search`，读取 `GET /projects/:id/labels` 和 `GET /projects/:id/labels/:label_id`。
- 新增 `gl_milestones.py`: `list/get/issues/mrs`，读取项目里程碑和里程碑下 issue/MR。
- 新增 `gl_members.py`: `list/get`，支持直接成员和 inherited/all 成员查询，用于选择 assignee/reviewer。
- 新增 `gl_branches.py`: `list/get`，用于 MR 创建前确认 source/target branch。
- 仅做只读能力；不新增 label/milestone/member/branch 写操作。

原因（Why）:

- 用户要求组合流程先确定仓库、获取仓库信息、再搜索/选择 issue 等；标签、里程碑、成员、分支是后续写操作的必要选择面。

位置（Where）:

- 文件/模块（Files/modules）: `scripts/gl_labels.py`, `scripts/gl_milestones.py`, `scripts/gl_members.py`, `scripts/gl_branches.py`
- API/配置（APIs/configs）: GitLab Labels/Milestones/Project Members/Branches API
- 测试/文档（Tests/docs）: `tests/test_commands.py`, `references/api-map.md`

参考来源（References）:

- GitLab Labels API, Project milestones API, Project members API, Branches API。

适用规范（Standards applied）:

- 资源脚本高内聚；所有列表命令复用 pagination；输出统一 JSON。

开发质量检查（Development quality checks）:

- 每个脚本只负责一个资源域；无写操作；无 token 输出。

验证（Validation）:

- py_compile 新增脚本。
- fake client 单测覆盖 URL、params、pagination。
- live read smoke 可在 `codex_test` 上查询 labels/milestones/members/branches，缺少数据时记录空列表而不是失败。

风险和回滚（Risks and rollback）:

- 风险: 某些 GitLab 实例权限不足导致成员/用户字段受限。
- 回滚: 保留脚本但将受限命令文档标记为权限依赖；不影响核心 issue 创建。

阶段契约（Stage Contract）:

- 范围（Scope）: 只读发现脚本。
- 允许修改（Allowed changes）: 新增上述只读脚本、测试、api-map 能力表。
- 禁止修改（Forbidden changes）: 新增成员/标签/里程碑/分支写操作。
- 进入条件（Entry checks）: Stage 1 共享 helper 可用。
- 退出条件（Exit checks）: 只读脚本均可独立运行和测试。
- 适用规范（Standards applied）: GitLab 官方资源 API；项目 CLI JSON 输出约定。
- 开发质量检查（Development quality checks）: 单一资源职责，无跨脚本隐藏状态。
- 必需验证（Required validation）: py_compile + unittest + 可选 live read。
- 是否预期提交（Commit expected）: no，除非用户另行授权提交。

### 阶段 3（Stage 3）：issue 模板发现与读取能力

目标（Goal）:

- 支持在指定仓库中列出现成 issue 模板，并读取指定模板内容，供 issue 创建组合使用。

做法（How）:

- 新增 `gl_issue_templates.py`，提供 `list`、`get`。
- `list` 默认读取项目默认分支的 `.gitlab/issue_templates/` 目录；支持 `--ref` 覆盖。
- `get` 读取 `.gitlab/issue_templates/<name>.md` raw 内容；模板名做路径规范化，禁止 `..`、绝对路径和非 `.md` 后缀绕过。
- 不在脚本里复刻 GitLab UI 模板变量替换；模板内容作为 issue description 原文，元数据仍用 API 参数显式传递。

原因（Why）:

- GitLab 官方模板机制要求 `.md` 文件位于 `.gitlab/issue_templates/`，独立模板读取比内嵌到 create issue 命令更可复用。

位置（Where）:

- 文件/模块（Files/modules）: `scripts/gl_issue_templates.py`, 复用 `gl_repo.py`/repository files API 模式。
- API/配置（APIs/configs）: repository tree/raw file endpoints。
- 测试/文档（Tests/docs）: 新增模板路径测试、workflow 示例。

参考来源（References）:

- GitLab Description templates docs。
- GitLab Repository tree / repository files API（现有 `gl_repo.py` 已覆盖）。

适用规范（Standards applied）:

- 输入路径安全；模板读取只读；不输出 token。

开发质量检查（Development quality checks）:

- 模板名解析集中到小 helper，避免路径穿越。
- JSON 输出包含 `name`、`path`、`ref`、`content` 或 list metadata。

验证（Validation）:

- 单测覆盖合法模板名、非法路径、list/get endpoint。
- live read smoke 在 `codex_test` 若无模板则记录空列表；如存在模板则读取一个模板。

风险和回滚（Risks and rollback）:

- 风险: group/instance inherited templates 不在项目 repo 中，v1 无法发现。
- 回滚: 文档明确 v1 只支持项目仓库模板；未来另行扩展。

阶段契约（Stage Contract）:

- 范围（Scope）: 项目仓库 issue 模板只读发现和读取。
- 允许修改（Allowed changes）: 新增模板脚本、测试、文档。
- 禁止修改（Forbidden changes）: 创建/修改模板文件，推送代码，支持 group/instance 模板写入。
- 进入条件（Entry checks）: Stage 2 只读资源脚本约定已稳定。
- 退出条件（Exit checks）: 模板 list/get 可独立使用，并能被 Stage 4 组合引用。
- 适用规范（Standards applied）: Description templates official docs。
- 开发质量检查（Development quality checks）: 路径安全、只读边界、错误消息清晰。
- 必需验证（Required validation）: py_compile + unittest。
- 是否预期提交（Commit expected）: no，除非用户另行授权提交。

### 阶段 4（Stage 4）：受保护 issue 创建能力

目标（Goal）:

- 支持在指定仓库创建 issue，可选择模板、里程碑、标签、assignee、due date、confidential、issue_type 等参数。

做法（How）:

- 在 `gl_issues.py` 新增 `create` 子命令，默认 dry-run，真实请求必须 `--confirm`。
- 参数建议:
  - `--project`、`--title` 必需。
  - 描述来源互斥：`--description`、`--description-file`、`--stdin`、`--template`。
  - `--template` 组合调用模板 helper 读取 `.gitlab/issue_templates/<name>.md`，支持 `--template-ref`。
  - 元数据：`--labels`、`--milestone-id`、`--assignee-id/--assignee-ids`、`--due-date`、`--confidential`、`--issue-type`。
- 标签安全: GitLab 创建 issue 时未知 label 可能自动创建；默认执行标签存在性预检，只有显式 `--allow-new-labels` 才允许跳过该保护。
- 里程碑安全: 默认只支持 `--milestone-id`；文档引导先用 `gl_milestones.py list/search` 找 ID，避免 title 精确匹配歧义。

原因（Why）:

- 创建 issue 是用户明确要求的核心新增能力，但必须保持受保护写操作和可组合输入。

位置（Where）:

- 文件/模块（Files/modules）: `scripts/gl_issues.py`, `scripts/gl_issue_templates.py`, `gitlab_common.py` helper。
- API/配置（APIs/configs）: `POST /projects/:id/issues`。
- 测试/文档（Tests/docs）: `tests/test_commands.py`, `references/api-map.md`, `references/workflow.md`, `references/security.md`。

参考来源（References）:

- GitLab Issues API create issue 参数。
- GitLab Description templates docs。
- GitLab Labels API。

适用规范（Standards applied）:

- 受保护写操作一致模式；正文来源互斥；dry-run 摘要不打印完整 description。

开发质量检查（Development quality checks）:

- body builder 单测覆盖模板、description-file、labels、milestone、assignees、issue_type。
- `--confirm` 前不发送 POST。
- `api` scope 需求写入能力边界。

验证（Validation）:

- fake client dry-run 和 confirm 单测。
- dry-run live preview in `codex_test`。
- 若执行 live smoke，只在 `codex_test` 创建带 `[gitlab-pat-ops smoke]` 标记的测试 issue，并记录 IID/URL。

风险和回滚（Risks and rollback）:

- 风险: live 创建 issue 会产生可见测试数据。
- 回滚: 只在测试仓库执行；后续 Stage 5 可关闭同一个 smoke issue；不删除数据。

阶段契约（Stage Contract）:

- 范围（Scope）: issue 创建受保护写能力。
- 允许修改（Allowed changes）: `gl_issues.py` create、模板组合 helper、测试、文档、安全边界。
- 禁止修改（Forbidden changes）: 删除 issue、批量创建、非测试仓库 live write smoke。
- 进入条件（Entry checks）: Stage 2/3 能力可用或 helper 已在本阶段局部实现。
- 退出条件（Exit checks）: dry-run 默认、confirm 必需、标签预检策略明确。
- 适用规范（Standards applied）: Issues API, PAT/security docs。
- 开发质量检查（Development quality checks）: 写入安全、参数互斥、错误处理。
- 必需验证（Required validation）: py_compile + unittest + dry-run live preview；真实 live smoke 仅限 `codex_test`。
- 是否预期提交（Commit expected）: no，除非用户另行授权提交。

### 阶段 5（Stage 5）：issue/MR 状态变更能力

目标（Goal）:

- 支持受保护地关闭或重新打开 issue / MR。

做法（How）:

- 在 `gl_issues.py` 新增 `close`、`reopen` 子命令，默认 dry-run，真实请求必须 `--confirm`。
- 在 `gl_mrs.py` 新增 `close`、`reopen` 子命令，默认 dry-run，真实请求必须 `--confirm`。
- 请求体或 query 参数统一使用 `state_event=close/reopen`，按现有 client 选择 JSON body 方式；dry-run 输出目标 URL、state_event、project、iid 摘要。
- close 前不自动查详情，但 workflow 文档要求用户先 `get` 确认对象；可在命令中提供 `--expect-title` 之类防误操作选项作为可选增强，如果实现复杂则记录 follow-up。

原因（Why）:

- 用户明确提出需要支持关闭 issue / MR；关闭属于高影响状态变更，必须比评论回复更强提醒。

位置（Where）:

- 文件/模块（Files/modules）: `scripts/gl_issues.py`, `scripts/gl_mrs.py`, `gl_capabilities.py`
- API/配置（APIs/configs）: `PUT /projects/:id/issues/:issue_iid`, `PUT /projects/:id/merge_requests/:merge_request_iid`
- 测试/文档（Tests/docs）: command tests, api-map, security, workflow

参考来源（References）:

- GitLab Issues API update issue `state_event`。
- GitLab Merge Requests API update MR `state_event`。

适用规范（Standards applied）:

- 状态变更必须可审计、默认 dry-run、confirm 必需、非测试仓库 live 操作需要用户明确目标确认。

开发质量检查（Development quality checks）:

- 不实现 merge/approve/delete。
- MR close live smoke 默认只 dry-run；真实关闭 MR 需要用户提供 disposable MR 并明确批准。

验证（Validation）:

- fake client 单测覆盖 dry-run 不发送 PUT、confirm 发送 PUT。
- issue close live smoke 可关闭 Stage 4 在 `codex_test` 创建的测试 issue。
- MR close 只做 dry-run 或 fake client，除非用户提供安全测试 MR。

风险和回滚（Risks and rollback）:

- 风险: 关闭真实协作 issue/MR 可能影响团队流程。
- 回滚: 提供 reopen 命令；但仍不把 reopen 当成可随意试错理由，live 测试只限安全目标。

阶段契约（Stage Contract）:

- 范围（Scope）: issue/MR close/reopen。
- 允许修改（Allowed changes）: `gl_issues.py`、`gl_mrs.py`、capabilities、tests、docs。
- 禁止修改（Forbidden changes）: merge、approve、delete、批量 close。
- 进入条件（Entry checks）: Stage 4 写操作安全模式已稳定。
- 退出条件（Exit checks）: 状态变更 dry-run/confirm 行为一致，文档明确风险。
- 适用规范（Standards applied）: Issues/MR update API, security docs。
- 开发质量检查（Development quality checks）: 高影响写操作 review。
- 必需验证（Required validation）: py_compile + unittest + dry-run；live issue close 仅限 `codex_test` smoke issue。
- 是否预期提交（Commit expected）: no，除非用户另行授权提交。

### 阶段 6（Stage 6）：文档、能力边界、eval 和验证收口

目标（Goal）:

- 让 skill 使用说明、能力边界、API map、安全边界、eval 和 changelog 与新增模块保持一致。

做法（How）:

- 更新 `SKILL.md` 脚本列表和 workflow，强调 `gl_capabilities.py` 只在能力边界不确定时运行。
- 更新 `gl_capabilities.py`:
  - 将 issue create、issue close/reopen、MR close/reopen 移到 guarded writes。
  - 增加 labels/milestones/members/branches/templates 的 read-only 能力。
  - 保留 delete/merge/approve/权限/token/CI/CD/bulk writes 为 not supported。
- 更新 `references/api-map.md`、`references/workflow.md`、`references/security.md`。
- 更新 `evals/gitlab-pat-ops/prompts.jsonl`，加入模块化组合、创建 issue with template、关闭 issue/MR、能力边界不确定时查询 capabilities 的场景。
- 更新 `CHANGELOG.md` 和 README 中相关能力概览。

原因（Why）:

- 这个 skill 的效果依赖说明与脚本同步；能力边界不准确会导致 agent 误用。

位置（Where）:

- 文件/模块（Files/modules）: `skills/gitlab-pat-ops/SKILL.md`, `scripts/gl_capabilities.py`, `references/*.md`, `evals/gitlab-pat-ops/*`, `README.md`, `CHANGELOG.md`
- API/配置（APIs/configs）: 无新增 env
- 测试/文档（Tests/docs）: JSONL parse、capabilities output review

参考来源（References）:

- 本计划、GitLab 官方 docs、本地安全规则。

适用规范（Standards applied）:

- 能力边界必须保守、具体、同步；文档示例不泄露 token。

开发质量检查（Development quality checks）:

- 所有新增能力在 docs、capabilities、tests/evals 三处同步。
- 文档不暗示非测试仓库可直接 live 写入。

验证（Validation）:

- `python -B skills\gitlab-pat-ops\scripts\gl_capabilities.py --pretty`
- JSONL parse/id 唯一检查。
- `python -B -m unittest discover -s skills\gitlab-pat-ops\tests`
- `git -c diff.autoRefreshIndex=false diff --check`

风险和回滚（Risks and rollback）:

- 风险: 文档过长导致日常使用负担。
- 回滚: SKILL 保持简短，细节放 references；capabilities 仍只在不确定时运行。

阶段契约（Stage Contract）:

- 范围（Scope）: 文档、能力边界、eval、验证收口。
- 允许修改（Allowed changes）: skill docs、references、capabilities、eval、README、CHANGELOG。
- 禁止修改（Forbidden changes）: 临时扩大能力、删减安全规则。
- 进入条件（Entry checks）: Stage 1-5 功能边界已确定。
- 退出条件（Exit checks）: 文档与脚本能力一致，所有必需验证完成或记录无法执行原因。
- 适用规范（Standards applied）: planner/executor 规则、项目文档风格。
- 开发质量检查（Development quality checks）: 文档准确性、capabilities 同步、eval 覆盖。
- 必需验证（Required validation）: capabilities output + unittest + JSONL parse + diff check。
- 是否预期提交（Commit expected）: no，除非用户另行授权提交。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- `SKILL_GITLAB_BASE_URL`
- `SKILL_GITLAB_PAT` 或 `SKILL_GITLAB_TOKEN`
- Python 标准库脚本和 PowerShell。

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

- origin/main，按 `.harness/environment.md` 的 harness 分支策略执行。

最近同步（Last sync）:

- not checked in this planning turn; executor 实施前必须串行检查。

分支占用（Branch occupancy）:

- 串行 `git log <main>..HEAD`: executor 实施前执行。
- 串行 `git -c diff.autoRefreshIndex=false diff <main>...HEAD --name-only`: executor 实施前执行。
- 现有提交属于本任务（Existing commits belong to this task）: 当前分支 ahead 2，属于前序 GitLab PAT Ops skill 任务；本任务不得回滚。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发任务同时运行同仓库 Git。
- 非 Git 文件读取和文本搜索可并发。

只读 Git 选项（Read-only Git options）:

- 状态检查优先：`git --no-optional-locks status --short --branch`
- diff 检查优先：`git -c diff.autoRefreshIndex=false diff <range>`

Index lock 恢复策略（Index lock recovery）:

- lock 路径解析命令：`git rev-parse --git-path index.lock`
- 删除前检查：精确路径、文件存在、大小/mtime 稳定、无活跃或未知归属 Git 进程。
- 删除范围：只删除解析出的精确 `index.lock`，禁止通配符、递归删除和删除其它 `.lock`。

Git Lock Recovery Log:

| 时间（Time） | lock 路径（Lock path） | 文件大小/mtime（Size/mtime） | Git 进程检查（Process check） | 操作（Action） | 后续 status（Follow-up status） |
| --- | --- | --- | --- | --- | --- |
| none | none | none | none | none | none |

提交策略（Commit policy）:

- 用户已授权最终阶段完成、代码审查等步骤完成后提交代码。
- executor 必须使用 `git commit -F <message-file>`，提交信息遵守 `AGENTS.md` 格式，标题后正好一个空行，bullet 之间无多余空行。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: no
- 未合回时代码停留在（If not merged, code remains on）: `harness/feature`
- 合并前需要用户确认（User confirmation needed before merge）: yes

分支安全（Branch safety）:

- 切换前已检查工作区：executor 实施前检查。
- 不自动 stash：yes
- 不自动 rebase：yes
- 不自动 reset：yes

热修复插入（Hotfix interruption）:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支。
- 决策：not applicable in this plan。

未解决问题（Open issues）:

- 无 blocking 问题。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| PowerShell | 文件读取、有限命令、验证 | all | available | low | none | not needed |
| Python | 脚本、单测、py_compile | all | available | low | none | not needed |
| GitLab REST API | live read/write smoke | Stage 2-5 | env configured per environment.md | medium | dry-run/fake client | live write limited to `codex_test` |
| web official docs | GitLab API 调研 | Planning | used | low | official docs re-check | not needed |
| git | status/diff/commit if authorized | executor final | available | medium | none | commit requires explicit authorization |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- no

process-manager skill 是否存在（process-manager skill available）:

- not-checked

规则结论（Rule decision）:

- 本任务全部是有限脚本命令、文档和测试，不启动后台服务。
- 如果后续临时出现长期服务需求，必须触发 Plan Amendment Gate。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | none | none | none | none | none | none | none |

禁止 shell 后台启动确认（No shell background start）:

- passed

历史视图需求（Needs `pm_list --history`）:

- no

证据保留位置（Evidence retention location）:

- `execution-plan.md`

日志沉淀确认（Log evidence persisted）:

- not applicable

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前必须复查本节。

## 验证（Validation）

必需验证（Required）:

- `python -B -m py_compile` 覆盖所有新增/修改 Python 脚本。
- `python -B -m unittest discover -s skills\gitlab-pat-ops\tests`
- `python -B skills\gitlab-pat-ops\scripts\gl_doctor.py --offline-check --pretty`
- `python -B skills\gitlab-pat-ops\scripts\gl_capabilities.py --pretty`
- eval JSONL parse/id 唯一检查。
- `git -c diff.autoRefreshIndex=false diff --check`
- 若执行 live read: `/user`、project search/get、labels/milestones/templates/members/branches read。
- 若执行 live write: 只在 `codex_test` 创建带 smoke 标记的 issue，并可关闭同一个 smoke issue；MR close 默认 dry-run。

已执行（Executed）:

- 命令/工具（Command/tool）: `python -B skills\complex-coding-planner\scripts\harness_plan_check.py --plan .harness\tasks\2026-07-09\feature\gitlab-pat-ops-modular-capabilities\execution-plan.md`
- 结果（Result）: PASS
- 证据（Evidence）: `PASS: plan structure is ready for approval`
- 覆盖范围（Covers）: 规划结构。
- 未覆盖（Not covered）: 功能实现验证尚未执行。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | `harness_plan_check.py --plan ...` | passed | 计划结构 | 实现 | `PASS: plan structure is ready for approval` | complete |
| Stage 1 | `python -B -c ast.parse(...)`; `python -B -m unittest discover -s skills\gitlab-pat-ops\tests` | passed | shared helper | live API | `ast parse ok`; `Ran 14 tests ... OK`; `py_compile` 因 `__pycache__` WinError 5 降级 | complete |
| Stage 2 | `python -B -c ast.parse(...)`; `python -B -m unittest discover -s skills\gitlab-pat-ops\tests` | passed | readonly modules | live read optional not executed in this stage | `ast parse ok`; `Ran 18 tests ... OK` | complete |
| Stage 3 | `python -B -c ast.parse(...)`; `python -B -m unittest discover -s skills\gitlab-pat-ops\tests` | passed | templates | inherited templates/live template read | `ast parse ok`; `Ran 20 tests ... OK` | complete |
| Stage 4 | `python -B -c ast.parse(...)`; `python -B -m unittest discover -s skills\gitlab-pat-ops\tests`; issue create dry-run preview | passed | issue create | real issue create not executed | `Ran 23 tests ... OK`; dry-run returned POST preview for `Countra/codex_test` without `--confirm` | complete |
| Stage 5 | `python -B -c ast.parse(...)`; `python -B -m unittest discover -s skills\gitlab-pat-ops\tests`; issue/MR close dry-run preview | passed | state changes | real issue/MR close not executed | `Ran 25 tests ... OK`; dry-run PUT previews for issue and MR close | complete |
| Stage 6 | AST parse all scripts; unittest; `gl_capabilities.py --pretty`; `gl_doctor.py --offline-check --pretty`; JSONL parse; `git diff --check` | passed | docs/evals/capabilities/offline env | live read/write not executed beyond dry-run previews | `ast parse ok: 14 files`; `Ran 25 tests ... OK`; `jsonl ok: 9 prompts`; doctor offline ok; diff check only CRLF warnings | complete |

可选验证（Optional）:

- live `/user` auth check with `gl_doctor.py --pretty`。
- `codex_test` 模板读取 smoke；如果测试仓库没有模板，记录 empty result。

产物（Artifacts）:

- 截图（Screenshot）: not applicable
- 日志（Log）: validation command output summary in execution-plan.md
- Trace: not applicable
- 报告（Report）: final delivery summary

未覆盖（Not covered）:

- group/instance inherited templates。
- 真实关闭 MR，除非用户提供 disposable MR。
- 非测试仓库 live writes。

无法执行时（If unable to run）:

- 记录命令、失败原因、影响、替代证据；不得声称通过。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/gitlab-pat-ops/SKILL.md`
- `skills/gitlab-pat-ops/references/api-map.md`
- `skills/gitlab-pat-ops/references/workflow.md`
- `skills/gitlab-pat-ops/references/security.md`
- `skills/gitlab-pat-ops/scripts/gl_capabilities.py`
- `evals/gitlab-pat-ops/prompts.jsonl`
- `README.md`
- `CHANGELOG.md`

Changelog 计划（Changelog plan）:

- 新增一条 GitLab PAT Ops 模块化能力扩展记录，说明 read-only 模块、issue 创建、issue/MR 状态变更、安全边界。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `gl_issues.py` | yes | parser/body builder/main 分段 | 重新读取全文件 + py_compile |
| `gl_mrs.py` | yes | parser/state commands/main 分段 | 重新读取全文件 + py_compile |
| 新增只读脚本 | no/unknown | 逐文件新增 | py_compile + tests |
| `gl_capabilities.py` | yes | read-only/guarded/not-supported sections | run capabilities pretty |
| references docs | yes | 按章节 patch | 重新读取全文件 |
| eval JSONL | no | 单行场景追加 | JSONL parse |

写入规则（Write rules）:

- 使用 `apply_patch` 做局部修改；不整文件重写超过 500 行的文件。
- 单次 patch 新增内容建议不超过 120 行，硬上限 200 行。
- 分段边界保持语义完整。

整体复查（Whole-file review）:

- 写完后重新读取完整目标文件。
- 检查 CLI help、能力边界、文档示例和安全规则一致。
- 对应验证命令为 py_compile、unittest、capabilities output、JSONL parse、diff check。

patch 失败处理（Patch failure handling）:

- 读取目标文件确认是否有部分写入。
- 缩小失败段重试。
- 不用 shell 拼接文件绕过 patch 失败。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| Q-001 | no | closed | 是否新增后台服务 | 不新增，继续脚本型 skill | Process Manager Gate |
| Q-002 | no | closed | 是否支持 group/instance inherited issue templates | v1 不支持自动发现，仅支持项目仓库模板 | Stage 3 |
| Q-003 | no | closed | 是否真实关闭 MR 做 smoke | 默认不做，仅 dry-run 或用户提供 disposable MR 后再确认 | Stage 5 |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | passed | Evidence levels table |
| Research Gate 已完成（Research Gate complete） | passed | official GitLab docs matrix |
| Standards Discovery Gate 已完成（Standards discovery complete） | passed | standards source matrix |
| Development Quality Gate 已完成（Development quality complete） | passed | quality scope mapping |
| 影响面矩阵完整（Impact matrix complete） | passed | Impact Matrix |
| 候选方案比较充分（Options compared enough） | passed | Options A/B/C |
| 每阶段可独立验证（Stages independently verifiable） | passed | Stage Contracts + Validation Evidence |
| 方案变更触发条件清楚（Reapproval triggers clear） | passed | Decision + Plan Amendment Gate |
| 用户批准摘要可记录（Approval summary ready） | passed | Plan Approval section |

质量结论（Quality result）:

- `passed`

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- `passed`

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 计划没有要求实现阶段直接跑 `gl_capabilities.py` 每次任务 | 保留“仅不确定能力边界时运行”的规则 | passed |
| 优化（Optimizations） | issue 创建可能意外创建新 labels | 增加默认 label 预检和 `--allow-new-labels` 保护 | passed |
| 缺失项（Missing items） | 创建 issue 需要 assignee、milestone、template 的独立发现能力 | 增加 members/milestones/templates 只读模块阶段 | passed |
| 风险（Risks） | close MR live smoke 可能影响协作 | 默认只 dry-run，真实关闭需 disposable MR 和明确批准 | passed |
| 一致性（Consistency） | Stage 4 与 Stage 5 都有 live write | 均限制为 `codex_test`，MR close 除外默认 dry-run | passed |
| 开发质量（Development quality） | 容易过度引入服务或 SDK | 明确禁止后台服务和第三方 SDK | passed |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：no
- `Plan Self-Review` 是否需要重跑：no
- `Readiness Gate` 是否需要重跑：no
- 原因：自查问题已在当前计划中修复。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | passed | Problem + Goal Condition |
| 上下文已收集（Context collected） | passed | Context |
| 调研门禁已通过（Research Gate passed） | passed | Research Gate |
| 规范发现门禁已通过（Standards Discovery Gate passed） | passed | Standards Discovery Gate |
| 开发质量门禁已通过（Development Quality Gate passed） | passed | Development Quality Gate |
| 候选方案已比较（Options compared） | passed | Options |
| 决策已记录（Decision recorded） | passed | Decision |
| 实施阶段已细化（Implementation stages detailed） | passed | Implementation Plan |
| 环境已确认（Environment confirmed） | passed | Environment |
| Git 上下文已确认（Git context confirmed） | passed | Git Context |
| 工具已确认（Tooling confirmed） | passed | Tooling |
| 验证已确认（Validation confirmed） | passed | Validation |
| 最终交付证据已规划（Final delivery evidence planned） | passed | Validation + Commit Log |
| 文档更新已确认（Documentation updates confirmed） | passed | Documentation |
| 风险已识别（Risks identified） | passed | Stage risks + self-review |
| 规划自查已通过（Plan self-review passed） | passed | Plan Self-Review |
| 阻塞问题已关闭（Blocking questions closed） | passed | Questions And Overrides |

就绪结论（Readiness result）:

- `passed; stop and wait for explicit user approval`

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 2026-07-09 用户明确要求：“按 complex-coding-executor 开始执行，最终阶段完成后（代码审查 等步骤也完成 后） 提交代码”。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: pending
- 批准范围（Approved scope）: 执行本计划 Stage 1-6，完成 GitLab PAT Ops 模块化能力拆分、issue 创建、模板读取、issue/MR close/reopen、文档/eval/测试收口。
- 阶段提交授权（Stage commit authorization）: authorized_final_commit_after_all_stages_review_and_validation
- 工具/MCP 授权（Tool/MCP authorization）: 使用本计划列出的有限本地命令、GitLab dry-run/read smoke 和 `codex_test` 范围内受控 live smoke；不得扩大到非测试仓库写入。
- 文档更新授权（Documentation authorization）: authorized

提交策略（Commit policy）:

- `authorized_final_commit_after_all_stages_review_and_validation`

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
| none | none | none | none |

## 执行控制（Execution Control）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- completed

当前阶段（Current stage）:

- Final

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

- final delivery complete

当前停止条件（Current stop condition）:

- none

状态来源（State source of truth）:

- execution-plan.md

阶段边界是否允许停止（May stop at stage boundary）:

- no, unless the user explicitly requested stage-only execution or a Stop Condition is active

active-task 同步字段（active-task sync fields）:

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "current_stage": "Final",
  "remaining_stages": [],
  "next_automatic_action": "final delivery complete",
  "stop_condition": "none",
  "state_source": "execution-plan.md"
}
```

状态同步规则（State sync rules）:

- `execution-plan.md` 是唯一主契约；`.harness/active-task.json` 只作为恢复入口和摘要索引。
- 如果 `active-task.json` 和本节冲突，必须以本节为准修正 `active-task.json` 后继续。

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | complete | 已完成调研与计划 | plan check passed | execution-plan.md | wait approval |
| Stage 1 | complete | 新增共享 CSV/int/date/optional text helper 并补单测 | ast.parse + unittest passed | gitlab_common.py, test_common.py | continue Stage 2 |
| Stage 2 | complete | 新增 labels/milestones/members/branches 只读资源脚本 | ast.parse + unittest passed | new read-only scripts, test_commands.py | continue Stage 3 |
| Stage 3 | complete | 新增 issue 模板 list/get 脚本和路径安全检查 | ast.parse + unittest passed | gl_issue_templates.py, test_commands.py | continue Stage 4 |
| Stage 4 | complete | 新增 issue create dry-run/confirm、模板描述、label 预检和元数据参数 | ast.parse + unittest + dry-run preview passed | gl_issues.py, test_commands.py | continue Stage 5 |
| Stage 5 | complete | 新增 issue/MR close/reopen dry-run/confirm 状态变更命令 | ast.parse + unittest + dry-run previews passed | gl_issues.py, gl_mrs.py, test_commands.py | continue Stage 6 |
| Stage 6 | complete | 同步 SKILL、API map、workflow、安全文档、capabilities、eval、README、CHANGELOG 并完成最终验证 | AST parse + unittest + capabilities + doctor offline + JSONL + diff check passed | docs/scripts/tests/evals | final delivery |

## Ledger Evidence

Ledger policy:

- append-only-after-approval

Ledger 文件（Ledger file）:

- `.harness/tasks/2026-07-09/feature/gitlab-pat-ops-modular-capabilities/ledger.jsonl`

Ledger 摘要（Ledger summary）:

| 字段（Field） | 值（Value） |
| --- | --- |
| entries | 19 |
| stages_completed | Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6 |
| current_stage | Final |
| last_blocking_reason | none |
| last_heartbeat | none |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | pending | pending | pending | passed/no-process | pending | pending |
| Stage 2 | pending | Stage 1 findings | pending | passed/no-process | pending | pending |
| Stage 3 | pending | Stage 2 findings | pending | passed/no-process | pending | pending |
| Stage 4 | pending | Stage 3 findings | pending | passed/no-process | pending | pending |
| Stage 5 | pending | Stage 4 findings | pending | passed/no-process | pending | pending |
| Stage 6 | pending | Stage 5 findings | pending | passed/no-process | pending | pending |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | passed | passed | passed | not-applicable | passed | passed | not committed; final commit authorized | passed |
| Stage 2 | passed | passed | passed | not-applicable | passed | passed | not committed; final commit authorized | passed |
| Stage 3 | passed | passed | passed | not-applicable | passed | passed | not committed; final commit authorized | passed |
| Stage 4 | passed | passed | passed | not-applicable | passed | passed | not committed; final commit authorized | passed |
| Stage 5 | passed | passed | passed | not-applicable | passed | passed | not committed; final commit authorized | passed |
| Stage 6 | passed | passed | passed | not-applicable | passed | passed | current commit after final commit | passed |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证已完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | yes | yes | plan check passed | final commit authorized after all stages | yes | none | no | yes | yes | yes | continue Stage 1 |
| Stage 1 | yes | yes | yes | final commit deferred by plan | yes | none | no | yes | yes | no | continue Stage 2 |
| Stage 2 | yes | yes | yes | final commit deferred by plan | yes | none | no | yes | yes | no | continue Stage 3 |
| Stage 3 | yes | yes | yes | final commit deferred by plan | yes | none | no | yes | yes | no | continue Stage 4 |
| Stage 4 | yes | yes | yes | final commit deferred by plan | yes | none | no | yes | yes | no | continue Stage 5 |
| Stage 5 | yes | yes | yes | final commit deferred by plan | yes | none | no | yes | yes | no | continue Stage 6 |
| Stage 6 | yes | yes | yes | current commit after final commit | no | none | no | yes | yes | no | final delivery complete |

结论（Decision）:

- 规划已获用户批准；由 `complex-coding-executor` 执行 Stage 1。

规则（Rules）:

- 如果还有 pending stage，且没有停止条件，也不需要重新批准，下一动作必须是 `continue Stage N`。
- 进入下一阶段前必须同步 `Execution Control`、`Resume Summary` 和 `.harness/active-task.json`。

## 代码审查（Code Review）

| 阶段（Stage） | 质量维度（Quality dimension） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- | --- |
| Planning | standards / architecture / validation | no blocking finding | none | plan ready |
| Stage 1 | standards / static quality / architecture / validation | no blocking or major finding; `py_compile` cache write failed but `ast.parse` and unittest passed | none | closed with documented fallback |
| Stage 2 | architecture / cohesion / static quality / validation | 新增脚本均为只读资源职责，未引入写操作或共享状态 | none | closed |
| Stage 3 | security / cohesion / validation | 模板读取限制为单个 Markdown 文件名，避免路径穿越；不支持继承模板已按计划保留为未覆盖 | none | closed |
| Stage 4 | security / validation / coupling | issue 创建默认 dry-run，真实请求必须 `--confirm`；labels 默认预检，未扩大 live write | none | closed |
| Stage 5 | security / validation | issue/MR 状态变更只支持 close/reopen，默认 dry-run，真实请求必须 `--confirm`；未实现 merge/approve/delete | none | closed |
| Stage 6 | standards / static quality / architecture / validation | 文档、能力边界、eval 与脚本同步；最终验证通过，只有 CRLF 工作区提示 | none | closed |

## 恢复摘要（Resume Summary）

Resume Packet:

```json
{
  "task_id": "2026-07-09-feature-gitlab-pat-ops-modular-capabilities",
  "execution_mode": "run-to-completion",
  "overall_status": "completed",
  "current_stage": "Final",
  "remaining_stages": [],
  "next_automatic_action": "final delivery complete",
  "stop_condition": "none",
  "ledger_entries": 19,
  "last_blocking_reason": "none",
  "attestation_status": "not_checked"
}
```

- 整体目标（Overall goal）: 模块化扩展 GitLab PAT Ops，支持独立资源发现、issue 创建 with template、issue/MR close/reopen。
- 执行模式（Execution mode）: run-to-completion。
- 整体任务状态（Overall status）: completed。
- 已完成阶段（Completed stages）: Planning research and plan drafting, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6。
- 当前阶段（Current stage）: Final。
- 剩余阶段（Remaining stages）: none。
- 最新 commit（Latest commit）: not checked in plan; current branch ahead 2 from previous task.
- 下一步自动动作（Next automatic action）: final delivery complete。
- 当前停止条件（Current stop condition）: none。
- 状态来源（State source of truth）: execution-plan.md。
- 长期进程规则（Process manager rule）: no long-running process。
- 未覆盖/风险（Not covered/risks）: inherited templates, real MR close live smoke, non-test writes。
- 不得停止说明（Do not stop note）:
  - 方案获批后，Stage boundary is not a stop condition. Continue until all approved stages and the final delivery gate are complete, unless a Stop Condition is active.

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/2026-07-09/feature/gitlab-pat-ops-modular-capabilities/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Stage 1-6 | dev-skills | current commit after final commit | `feat(gitlab-pat-ops): 模块化扩展 GitLab 操作能力` | CHANGELOG 2026-07-09 |

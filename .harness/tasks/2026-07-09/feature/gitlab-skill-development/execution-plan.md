# 执行计划：新增 GitLab PAT 操作 skill

## 执行控制快照（Execution Control Snapshot）

执行模式（Execution mode）:

- run-to-completion

整体任务状态（Overall status）:

- complete

当前阶段（Current stage）:

- Final

已完成阶段（Completed stages）:

- Planning research and plan revision
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

- 实施阶段使用 `complex-coding-executor`；规划阶段不得直接实现。

## 执行契约（Execution Contract）

```json
{
  "contract_version": 1,
  "task_id": "2026-07-09-feature-gitlab-skill-development",
  "execution_mode": "run-to-completion",
  "overall_status": "complete",
  "approval_status": "approved",
  "approved_contract_hash": "external:attestation-after-approval",
  "current_stage_id": "Final",
  "remaining_stage_ids": [],
  "stop_condition": "none",
  "commit_authorization": "authorized",
  "ledger_policy": "append-only-after-approval",
  "single_writer": "current executor session",
  "reapproval_required": false
}
```

契约规则（Contract rules）:

- 本计划获批前不得创建 `skills/gitlab` 代码、脚本、测试或文档实现。
- `Execution Control Snapshot`、`Execution Contract` 和 `执行控制` 三处状态必须保持一致；若冲突，以本文件为准修正 `.harness/active-task.json`。
- 修改 approved scope、阶段边界、写操作安全策略、环境变量契约、依赖策略、长期服务策略、验证策略或提交策略时，必须进入 `Plan Amendment Gate`。

## 目标条件（Goal Condition）

- 所有 approved stages 均完成，`final` 门禁通过，且无 blocking decision、无未关闭的 major finding。
- 新增 GitLab skill 能通过环境变量读取 GitLab base URL 和个人访问令牌，缺失时在检查步骤中清楚提示用户先设置必要环境变量。
- skill 覆盖仓库访问和搜索、项目创建、issue 搜索和详情拉取、评论解析、回复评论、合并请求创建和基础查看等核心流程。
- 写操作具有明确确认机制、dry-run 或请求预览、token 脱敏、错误处理和权限 scope 提示。
- 必需验证已执行，或无法执行项已记录原因、影响和替代证据。
- 提交授权状态明确；未授权时不得提交。

## 规划循环协议（Planning Loop Protocol）

- 本计划按 6 个阶段拆分，每个阶段都必须有独立 Stage Contract 和可验证输出。
- 调研 GitLab API、PAT scope、分页、速率限制、权限或脚本模式后，关键 findings 必须写入 `调研门禁`、`规范发现门禁` 或 artifacts。
- 重大决策前重读用户目标、现有 skill 形态、候选方案、影响面、风险和 reapproval triggers。
- rejected options 必须记录放弃原因，避免后续上下文压缩后重新走回不合适路线。
- Readiness 前必须重跑 `Plan Quality Gate`、`Plan Self-Review` 和 `Readiness Gate`。

## 执行循环协议（Executor Work Loop）

- 每个阶段开始先读取 `Execution Contract`、`Resume Packet`、Stage Contract 和上一阶段 findings。
- 每次实质动作后更新 ledger；失败动作必须记录 attempt、命令或工具、失败原因、影响和下一策略。
- Stage Transition Gate 通过且仍有后续阶段时，下一动作必须是 `continue Stage N`。
- 写操作相关阶段必须先跑只读或 dry-run 验证，再实现真实请求路径。
- 只有满足 `Goal Condition` 后才能进入最终交付。

## 问题定义（Problem）

目标（Goal）:

- 新增一个面向 GitLab 的 Codex skill，通过 GitLab 个人访问令牌调用 GitLab REST API，帮助编码代理完成仓库、issue、评论和合并请求相关操作。
- skill 使用 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT` 作为主环境变量；可兼容 `SKILL_GITLAB_TOKEN` 作为同前缀 token 别名。
- 优先采用脚本型实现，类似 `process-manager` 的 `pm_*` 脚本体验，而不是默认启动后台服务。
- 用户已声明当前环境中已配置 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT`，实施阶段可以做安全 live smoke。

非目标（Non-goals）:

- 不实现 GitLab 全量 API、GraphQL、CI/CD 管理、用户管理、管理员 sudo、token 创建或 token 轮换。
- 不把个人访问令牌保存到仓库、`.harness`、日志或本地状态文件。
- 不引入长期后台服务，除非后续出现批量队列、缓存会话或交互式回调等脚本无法良好覆盖的需求。

验收标准（Acceptance）:

- `skills/gitlab/SKILL.md` 入口清晰，能指导何时使用 GitLab skill、先跑哪条检查命令、环境变量缺失时如何处理。
- `skills/gitlab/scripts/` 提供 `gl_doctor.py`、`gl_projects.py`、`gl_search.py`、`gl_repo.py`、`gl_issues.py`、`gl_notes.py`、`gl_mrs.py` 和共享 client。
- 共享 client 支持 base URL 规范化、`PRIVATE-TOKEN` header、JSON 请求、URL 编码、分页 Link header、超时、429/5xx 退避、错误 JSON 解析和 token 脱敏。
- 只读脚本能覆盖项目搜索/详情、仓库 tree/file/raw、全局或项目搜索、issue 搜索/详情、issue/MR notes 拉取与筛选、MR 查看。
- 写操作脚本覆盖创建项目、创建 MR、回复 issue/MR 评论；所有写操作默认 dry-run 或要求 `--confirm`。
- eval、README、CHANGELOG 和 `.harness` 状态同步完成；验证命令真实执行并记录结果。

约束（Constraints）:

- 遵守用户全局规则：中文注释、修改前读上下文、最小变更、长文件分段、真实验证、提交信息使用 `-F` 规范。
- 遵守 `skill-creator`：`SKILL.md` 保持简洁，细节放 `references/`，脚本做确定性工作。
- 遵守 `complex-coding-executor`：批准后 run-to-completion，阶段门禁、ledger、代码审查、验证和提交授权分离。
- 任何输出都不得泄露 token，错误对象、请求预览和日志必须脱敏。
- live 写入验证只允许在 GitLab 测试仓库 `codex_test` 内进行；禁止删除、关闭、合并、force、权限变更、token 管理等危险命令测试。

待确认项（Open uncertainties）:

- 无 blocking 问题。默认环境变量名采用 `SKILL_GITLAB_BASE_URL` 与 `SKILL_GITLAB_PAT`，并兼容同前缀别名 `SKILL_GITLAB_TOKEN`。

## 调研门禁（Research Gate）

研究模式（Research mode）:

- online-required

不确定项清单（Uncertainty inventory）:

| ID | 问题（Question） | 类型（Type） | 是否需要在线搜索（Online required） | 处理结果（Resolution） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- |
| U-001 | PAT 如何认证 REST API | external-api | yes | 官方推荐 `PRIVATE-TOKEN` header，也可用 Bearer token | Stage 2 |
| U-002 | 需要哪些 scope | external-api | yes | 只读可用 `read_api`，私有仓库文件读取还涉及 `read_repository`；写评论、创建项目和 MR 需要 `api` | Stage 1/2/4 |
| U-003 | `write_repository` 是否能用于 API 写操作 | external-api | yes | 官方说明 `write_repository` 不支持 API authentication | Stage 1 安全说明 |
| U-004 | 项目、issue、notes、MR 的关键 endpoint | external-api | yes | 已确认 Projects、Search、Issues、Notes、Merge Requests、Repository Files/Repositories API | Stage 3/4 |
| U-005 | 是否需要后台服务 | local-design | no | GitLab 操作是有限 HTTP 请求，脚本足够；服务化作为未来扩展 | Decision |
| U-006 | 缺少环境变量时如何处理 | product-contract | no | `gl_doctor.py` 必须失败并提示设置 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT` | Stage 1/2 |
| U-007 | 大列表如何分页 | external-api | yes | 使用 `Link`/`x-next-page` 等分页 header，`per_page` 最大 100 | Stage 2/3 |
| U-008 | 仓库 tree 行为是否有版本差异 | external-api | yes | GitLab 17.7 起 repository tree 缺失路径返回 404，旧版本可能返回空数组 | Stage 3 错误处理 |
| U-009 | live 写入验证在哪里执行 | user-decision | no | 用户指定 `codex_test` 为可修改测试仓库；危险操作仍禁止 | Stage 4/6 |

搜索记录（Search log）:

| 查询/来源（Query/source） | 工具（Tool） | 日期（Date） | 结果（Result） | 后续动作（Next action） |
| --- | --- | --- | --- | --- |
| GitLab REST API authentication | web official docs | 2026-07-09 | 确认 `PRIVATE-TOKEN`、Bearer、401 行为和 deploy token 限制 | Stage 2 |
| GitLab personal access tokens | web official docs | 2026-07-09 | 确认 `api`、`read_api`、`read_repository`、`write_repository` scope 差异和过期策略 | Stage 1/2 |
| GitLab REST pagination | web official docs | 2026-07-09 | 确认 offset/keyset、`per_page` 最大 100、推荐使用 `Link` header | Stage 2 |
| GitLab Projects API | web official docs | 2026-07-09 | 确认项目详情和 `POST /projects` 创建项目参数 | Stage 3/4 |
| GitLab Search API | web official docs | 2026-07-09 | 确认 `scope`/`search` 参数、projects/issues/MR 搜索和高级 code search 边界 | Stage 3 |
| GitLab Issues API | web official docs | 2026-07-09 | 确认 project issue 详情、related MRs、closed_by endpoints | Stage 3 |
| GitLab Notes API | web official docs | 2026-07-09 | 确认 issue/MR notes 列表和创建 note 的 endpoint、body 参数与分页 | Stage 3/4 |
| GitLab Merge Requests API | web official docs | 2026-07-09 | 确认 `POST /projects/:id/merge_requests` 必需参数 | Stage 4 |
| GitLab Repository Files / Repositories API | web official docs | 2026-07-09 | 确认文件、raw、tree、blob、较大 blob 和 archive 速率限制 | Stage 3 |

来源矩阵（Source matrix）:

| 结论（Claim） | 来源类型（Source type） | URL/路径（URL/path） | 官方/一手（Official/primary） | 访问日期（Accessed） | 可信度（Confidence） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- | --- |
| PAT 可通过 `PRIVATE-TOKEN` header 调用 REST API | official | https://docs.gitlab.com/api/rest/authentication/ | yes | 2026-07-09 | high | 共享 client |
| PAT scope 中 `api` 覆盖完整读写 API，`read_api` 只读，`write_repository` 不支持 API authentication | official | https://docs.gitlab.com/user/profile/personal_access_tokens/ | yes | 2026-07-09 | high | 环境检查和权限提示 |
| GitLab REST 支持 offset/keyset pagination，`per_page` 上限 100，并返回分页 header | official | https://docs.gitlab.com/api/rest/#pagination | yes | 2026-07-09 | high | 分页封装 |
| Projects API 支持获取项目详情和 `POST /projects` 创建项目 | official | https://docs.gitlab.com/api/projects/ | yes | 2026-07-09 | high | `gl_projects.py` |
| Search API 支持 projects、issues、merge_requests 等 scope，部分 code search scope 有许可边界 | official | https://docs.gitlab.com/api/search/ | yes | 2026-07-09 | high | `gl_search.py` |
| Issues API 支持 project issue 详情、related MRs 和 closed_by | official | https://docs.gitlab.com/api/issues/ | yes | 2026-07-09 | high | `gl_issues.py` |
| Notes API 支持 issue/MR notes 列表和创建 note | official | https://docs.gitlab.com/api/notes/ | yes | 2026-07-09 | high | `gl_notes.py` |
| Merge Requests API 支持创建 MR，必需 source_branch、target_branch、title | official | https://docs.gitlab.com/api/merge_requests/ | yes | 2026-07-09 | high | `gl_mrs.py` |
| Repository Files / Repositories API 支持 file/raw/tree/blob，部分大对象有速率限制 | official | https://docs.gitlab.com/api/repository_files/、https://docs.gitlab.com/api/repositories/ | yes | 2026-07-09 | high | `gl_repo.py` |

调研结论（Research result）:

- passed。GitLab PAT + REST v4 可以覆盖目标操作；v1 应采用脚本型 skill、标准库 HTTP client、环境变量读取、强制 token 脱敏和写操作确认机制。

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）:

- online-required

技术栈清单（Technology inventory）:

| 类型（Type） | 发现（Finding） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| skill 类型 | Codex skill，入口 `SKILL.md`，细节放 references，脚本放 scripts | `skill-creator`、现有 skills | 决定目录结构 |
| 实现语言 | Python 标准库脚本为主 | 当前仓库脚本习惯、无包管理器 | 降低依赖和安装成本 |
| API 类型 | GitLab REST API v4 | GitLab 官方 API docs | 决定 endpoint、分页、认证和错误处理 |
| 安全域 | PAT、私有项目、评论写入、项目创建、MR 创建 | GitLab PAT docs | 决定脱敏和确认机制 |
| 交互形态 | 有限命令行脚本 | `process-manager` 脚本模式、`electron-ui-verifier` 服务模式对比 | v1 不启动服务 |

规范来源矩阵（Standards source matrix）:

| 规范来源（Standard source） | 类型（Type） | 官方/一手（Official/primary） | 适用边界（Applicability） | 访问日期（Accessed） | 影响（Impact） |
| --- | --- | --- | --- | --- | --- |
| https://docs.gitlab.com/api/rest/authentication/ | API auth | yes | GitLab REST 认证、401、header 选择 | 2026-07-09 | client auth |
| https://docs.gitlab.com/user/profile/personal_access_tokens/ | token/security | yes | PAT scope、过期、使用方式 | 2026-07-09 | doctor 和安全说明 |
| https://docs.gitlab.com/api/rest/#pagination | API pagination | yes | 分页封装、`per_page`、Link header | 2026-07-09 | shared client |
| https://google.github.io/styleguide/pyguide.html | Python style | yes | Python 脚本风格、异常、导入、main、文件资源 | 2026-07-09 | 代码标准 |
| https://docs.python.org/3/library/argparse.html | CLI stdlib | yes | 命令行参数和子命令结构 | 2026-07-09 | scripts |
| https://docs.python.org/3/library/urllib.request.html | HTTP stdlib | yes | 标准库 HTTP 请求能力 | 2026-07-09 | shared client |
| https://docs.python.org/3/library/unittest.html | test stdlib | yes | 无第三方依赖单元测试 | 2026-07-09 | tests |

standards index:

- 路径或章节（Path/section）: 本计划使用本节作为 standards index；实施时在 `skills/gitlab/references/api-map.md` 和 `skills/gitlab/references/security.md` 固化可执行摘要。
- 适用边界（Applicability）: GitLab API 规则仅适用于 GitLab REST v4；Python 规范适用于新写脚本；项目未来若改用 TypeScript/Node 或服务化，需要重新发现对应规范。
- 官方优先级（Official-first rule）: GitLab 官方 docs、Python 官方 docs 和 Google Python Style Guide 优先；博客或示例只能作为辅助，不作为最终 API 依据。
- blocked-by-access: 当前无访问阻塞。

规范发现结论（Standards result）:

- passed。实现阶段应以 GitLab 官方 API 文档为 endpoint 真源，以 Python 官方文档和 Google Python Style Guide 约束脚本质量。

## 开发质量门禁（Development Quality Gate）

质量范围（Quality scope）:

| 维度（Dimension） | 规划结论（Plan） | 阶段映射（Stage mapping） | 验证映射（Validation mapping） |
| --- | --- | --- | --- |
| 代码标准（Code standards） | Python 脚本采用标准库、清晰 `main()`、中文必要注释、异常路径显式 | Stage 2-4 | AST parse、unit tests、diff check |
| 静态质量（Static quality） | 不依赖写 `__pycache__` 的编译验证，优先 `python -B` 和 AST 解析 | Stage 2-6 | `python -B -m unittest`、AST parse |
| 架构边界（Architecture boundaries） | `gitlab_common.py` 只管 HTTP/auth/pagination；业务脚本只管参数和 endpoint 调用 | Stage 2-4 | review checklist |
| 设计模式（Design patterns） | 使用轻量 Facade/Command 风格封装 CLI；不引入后台服务、复杂 SDK 或全局状态 | Stage 1-4 | 文件边界复查 |
| 低耦合（Low coupling） | env、HTTP、JSON、endpoint、输出格式分层，脚本之间通过 shared client 复用 | Stage 2-4 | 单元测试 fake HTTP |
| 高内聚（High cohesion） | 项目、搜索、仓库、issue、notes、MR 分脚本；安全规则集中在 common 和 security reference | Stage 3-5 | 目录和引用检查 |
| 安全质量（Security quality） | token 不接受命令行明文参数，不写日志，所有预览脱敏，写操作要求确认 | Stage 1-4 | doctor + write dry-run tests |

过度设计防护（Overengineering guard）:

- v1 不做服务端 daemon，因为当前目标是有限 GitLab API 操作，脚本能更好地保持可审计、无常驻 token、无端口和生命周期成本。
- 如果未来需要批量任务队列、webhook 回调、缓存跨命令会话或多 agent 并发协调，再通过 Plan Amendment Gate 评估服务化。

开发质量结论（Development quality result）:

- passed。方案采用低依赖脚本架构、共享 client、强安全边界和可测试的 fake HTTP 设计。

## 上下文（Context）

- `skills/process-manager/SKILL.md` 和 `scripts/pm_*`：脚本型 skill 的主要参考。
- `skills/electron-ui-verifier/SKILL.md`：服务型 skill 的对照，说明 v1 不必常驻服务。
- `skills/complex-coding-planner/*`：本计划需满足 Research Gate、Standards Discovery Gate、Development Quality Gate 和 plan check。
- `skills/complex-coding-executor/*`：批准后必须按阶段、ledger、review、验证和最终门禁执行。
- 当前仓库无固定包管理器；后续 Python 验证优先 `python -B`、AST parse 和 unittest，避免 `__pycache__` 权限问题。
- 证据等级：GitLab 官方文档、Python 官方文档、本地现有 skill 为 high；服务化取舍为 medium。

## 候选方案（Options）

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| Option A 服务型 GitLab skill | rejected | 有利于队列和缓存，但引入端口、进程生命周期和 token 常驻风险 |
| Option B 脚本型 GitLab skill | accepted | 无后台进程、无持久 token、易测试、易审计，契合有限 REST 请求 |
| Option C 混合型 skill | rejected for v1 | 预留服务层会增加未使用接口和认知负担 |

## 决策（Decision）

选择（Selected option）: Option B，脚本型 GitLab skill。

关键设计（Key decisions）:

- 环境变量：`SKILL_GITLAB_BASE_URL` 必填；token 优先 `SKILL_GITLAB_PAT`，兼容 `SKILL_GITLAB_TOKEN`。
- API root：兼容 GitLab 根地址和已带 `/api/v4` 的地址；认证默认 `PRIVATE-TOKEN` header。
- 输出：默认 JSON；错误信息带 HTTP status、GitLab message 和脱敏上下文。
- 写操作：默认 dry-run 或必须 `--confirm`；正文优先 `--body-file` 或 stdin。
- live 写入验证：仅限 `codex_test` 测试仓库，优先测试评论回复；项目创建和 MR 创建默认用 fake HTTP，除非有明确安全前置。
- 重新批准触发：改为服务型、新增第三方依赖、保存 token、新增删除/force/关闭/合并类操作、改变环境变量或确认策略。

## 影响面矩阵（Impact Matrix）

| 影响面（Area） | 改动（Change） | 风险（Risk） | 缓解（Mitigation） |
| --- | --- | --- | --- |
| skill 入口 | 新增 `skills/gitlab/SKILL.md` | 触发条件过宽导致误用 | 明确 GitLab/PAT/API 操作才触发 |
| 脚本 | 新增多个 `gl_*` Python 脚本 | 参数不一致或重复逻辑 | 共享 common client 和统一 argparse 模式 |
| 安全 | PAT 从环境变量读取 | token 泄漏 | 禁止 token 参数、日志脱敏、错误脱敏 |
| GitLab API | REST endpoint 调用 | 版本差异、分页、速率限制 | 官方来源、分页封装、429/5xx 处理 |
| 写操作 | 评论、项目、MR 创建 | 误操作 | dry-run、`--confirm`、body-file/stdin |
| 测试 | 新增 fake HTTP 单元测试和受限 live smoke | 误触发真实写入 | fake HTTP 覆盖请求构造；live 写入只限 `codex_test` 且排除危险操作 |
| 文档 | README/CHANGELOG/eval 更新 | 文档与脚本漂移 | Stage 5 和 Stage 6 复查 |

## 实施计划（Implementation Plan）

### Stage 1: GitLab skill scaffold and usage contract

目标（Goal）:

- 创建 `skills/gitlab` 基础结构、入口契约、references 框架和 eval 目录骨架。

做法（How）:

- 新增 `SKILL.md`，只保留触发条件、先跑 `gl_doctor.py`、环境变量契约和引用导航。
- 新增 `references/workflow.md`、`references/security.md`、`references/api-map.md` 的章节框架。
- 新增 `agents/openai.yaml`，内容由 skill 入口语义生成；如无法使用 skill-creator 初始化脚本，手工生成后用校验脚本验证。

原因（Why）:

- 先固定 skill 的使用契约和安全边界，避免脚本能力扩张时把 token、写操作或服务化策略写散。

位置（Where）:

- 文件/模块：`skills/gitlab/SKILL.md`、`skills/gitlab/agents/openai.yaml`
- API/配置：无 live GitLab API 调用
- 测试/文档：`skills/gitlab/references/*.md`、`evals/gitlab/`

参考来源（References）:

- `skill-creator` SKILL.md：skill 入口简洁、references 分流、脚本确定性能力。
- `skills/process-manager/SKILL.md`：脚本型 skill 的调用体验。
- `skills/electron-ui-verifier/SKILL.md`：服务型 skill 的对照边界。

适用规范（Standards applied）:

- Skill naming：`gitlab` 或 `gitlab-ops` 需使用小写和连字符；本计划选择 `gitlab`，触发更直接。
- Progressive disclosure：`SKILL.md` 不写 API 全量细节，复杂内容放 references。

开发质量检查（Development quality checks）:

- 入口不能要求用户把 token 写入文件。
- 入口必须明确“先检查环境变量，再执行 GitLab 操作”。
- 入口不能承诺未实现的删除、关闭、合并或 force 类能力。

验证（Validation）:

- 完整读取 `skills/gitlab/SKILL.md` 和 references 框架。
- 运行 skill 基础校验，如可用：`python <skill-creator>/scripts/quick_validate.py skills/gitlab`。
- 检索 `SKILL_GITLAB_BASE_URL`、`SKILL_GITLAB_PAT`、`SKILL_GITLAB_TOKEN`、`gl_doctor.py`、`--confirm`、`dry-run`。

风险和回滚（Risks and rollback）:

- 风险：入口过长导致加载成本高。回滚：把细节移到 references，只保留导航。
- 风险：skill 名称触发过宽。回滚：把名称改为 `gitlab-ops` 需要 Plan Amendment Gate，因为会影响触发和路径。

阶段契约（Stage Contract）:

- 范围：仅创建 skill 基础结构、入口说明、references 框架和 eval 骨架。
- 允许修改：`skills/gitlab/**` 的文档骨架、`evals/gitlab/**` 骨架、README/CHANGELOG 的占位计划可暂不写。
- 禁止修改：不实现 API 写操作，不调用真实 GitLab，不保存 token。
- 进入条件：用户批准本计划；工作区状态和 active task 已同步。
- 退出条件：skill 入口和 references 框架可读，环境变量契约明确，未出现 token 明文。
- 必需验证：skill 校验或手工 frontmatter 检查、关键词检索。
- 是否预期提交：no，除非用户明确授权阶段提交。

### Stage 2: PAT auth and shared REST client

目标（Goal）:

- 实现 PAT 认证、环境变量检查、base URL 规范化、共享 REST client 和安全错误输出。

做法（How）:

- 新增 `scripts/gitlab_common.py`，封装 env 读取、token 脱敏、API root 拼接、URL encoding、JSON request、HTTPError 解析、分页和 retry。
- 新增 `scripts/gl_doctor.py`，支持 `--offline-check` 与可选 live `/user` 检查。
- 新增 fake HTTP 测试基础设施，避免依赖真实 GitLab 环境。

原因（Why）:

- 所有后续脚本都依赖认证、分页、错误处理和脱敏；底座必须先稳定。

位置（Where）:

- 文件/模块：`skills/gitlab/scripts/gitlab_common.py`、`skills/gitlab/scripts/gl_doctor.py`
- API/配置：`/user` 只用于 live doctor；环境变量 `SKILL_GITLAB_BASE_URL`、`SKILL_GITLAB_PAT`、`SKILL_GITLAB_TOKEN`
- 测试/文档：`skills/gitlab/tests/test_common.py`、`references/security.md`

参考来源（References）:

- GitLab REST Authentication、PAT、Pagination 官方文档。
- Python `argparse`、`urllib.request`、`unittest` 官方文档。

适用规范（Standards applied）:

- Google Python Style Guide：清晰 main、异常处理、导入和资源使用。
- GitLab 官方认证规则：默认 `PRIVATE-TOKEN` header；`write_repository` 不作为 API scope。

开发质量检查（Development quality checks）:

- token 不允许通过命令行参数传入。
- 错误、dry-run 和 debug 输出必须脱敏。
- retry 只覆盖 429、Retry-After 和可恢复 5xx；不可静默重试 4xx 权限错误。

验证（Validation）:

- `python -B skills/gitlab/scripts/gl_doctor.py --offline-check`
- AST parse `skills/gitlab/scripts/*.py`
- `python -B -m unittest discover skills/gitlab/tests`
- 临时清空 GitLab 环境变量，确认缺失提示清楚且不泄露 token。

风险和回滚（Risks and rollback）:

- 风险：`urllib.request` 较底层导致错误处理复杂。回滚：保持 client 小而明确，必要时拆分 helper；新增第三方依赖需重新批准。
- 风险：live doctor 误认为必需。回滚：保留 `--offline-check`，live smoke 只在环境变量存在时执行。

阶段契约（Stage Contract）:

- 范围：认证、env、HTTP client、doctor 和基础测试。
- 允许修改：`scripts/gitlab_common.py`、`scripts/gl_doctor.py`、`tests/test_common.py`、security reference。
- 禁止修改：不实现项目、issue、MR 写操作；不调用除 `/user` 之外的 live endpoint。
- 进入条件：Stage 1 通过；GitLab 官方认证和 PAT scope 已记录。
- 退出条件：doctor offline 通过，缺失 env 提示正确，token 脱敏测试通过。
- 必需验证：AST parse、unit tests、doctor offline、env missing check。
- 是否预期提交：no，除非用户明确授权阶段提交。

### Stage 3: read-only project, repository, search, issue, note, and MR operations

目标（Goal）:

- 实现项目、搜索、仓库、issue、notes 和 MR 的只读操作，为写操作提供安全前置。

做法（How）:

- `gl_projects.py`: search/list/get project，支持 ID 和 URL-encoded path。
- `gl_search.py`: global/project search，支持 `projects`、`issues`、`merge_requests` 等 scope，并标注 code search 许可边界。
- `gl_repo.py`: repository tree、file metadata、raw file、blob/raw blob；大对象限制写入 api-map。
- `gl_issues.py`: list/search/get issue、related MRs、closed_by。
- `gl_notes.py`: list issue notes、list MR notes、`activity_filter=only_comments` 和评论解析输出。
- `gl_mrs.py`: list/search/get MR、list MR notes、diff metadata 基础查看。

原因（Why）:

- 先做只读能力能验证认证、分页、URL 编码、项目路径处理和 JSON 输出，降低后续 POST 误操作风险。

位置（Where）:

- 文件/模块：`skills/gitlab/scripts/gl_projects.py`、`gl_search.py`、`gl_repo.py`、`gl_issues.py`、`gl_notes.py`、`gl_mrs.py`
- API/配置：GitLab Projects、Search、Repository Files、Repositories、Issues、Notes、Merge Requests API
- 测试/文档：`skills/gitlab/tests/test_readonly_commands.py`、`tests/fixtures/*.json`、`references/api-map.md`

参考来源（References）:

- GitLab Projects、Search、Repository Files、Repositories、Issues、Notes、Merge Requests 官方文档。

适用规范（Standards applied）:

- GitLab path 参数必须 URL encode；分页使用官方 Link header 或 x-next-page。
- 输出默认 JSON；展示模式只作为可选，不替代结构化输出。

开发质量检查（Development quality checks）:

- 各脚本只负责 CLI 参数和 endpoint 调用，不复制 HTTP/auth/pagination 逻辑。
- 只读脚本不得调用 POST/PUT/PATCH/DELETE。
- 对 GitLab 17.7 repository tree 缺失路径 404 行为给出清楚错误。

验证（Validation）:

- fake HTTP tests 覆盖 endpoint path、query 参数、分页、URL 编码和错误解析。
- AST parse 和 unittest。
- 可选 live smoke：仅在 env 存在时执行一个只读项目搜索或 `/projects/:id`。

风险和回滚（Risks and rollback）:

- 风险：scope 名称或 endpoint 参数过多导致 CLI 复杂。回滚：先覆盖核心 scope，把高级参数放 `--params-json` 或后续扩展。
- 风险：文件 raw 和 blob 大对象触发 rate limit。回滚：默认不自动下载大对象，文档提示限制。

阶段契约（Stage Contract）:

- 范围：只读 API 命令和 fixtures。
- 允许修改：`gl_projects.py`、`gl_search.py`、`gl_repo.py`、`gl_issues.py`、`gl_notes.py`、`gl_mrs.py` 的只读子命令。
- 禁止修改：不发送 POST/PUT/PATCH/DELETE；不创建项目、MR 或评论。
- 进入条件：Stage 2 client 和 doctor 通过。
- 退出条件：只读命令测试通过，api-map 覆盖 endpoint 与 scope。
- 必需验证：AST parse、unit tests、JSON fixture parse、可选 live smoke 记录。
- 是否预期提交：no，除非用户明确授权阶段提交。

### Stage 4: guarded write operations for notes, projects, and merge requests

目标（Goal）:

- 实现三类受保护写操作：回复 issue/MR 评论、创建项目、创建 MR。

做法（How）:

- `gl_notes.py reply`: 支持 issue/MR note 创建，正文来自 `--body-file` 或 stdin；`--body` 如实现必须提示 shell history 风险。
- `gl_projects.py create`: 支持 name/path、namespace_id、visibility、initialize_with_readme 等安全参数，默认 dry-run。
- `gl_mrs.py create`: 支持 source_branch、target_branch、title、description、remove_source_branch、squash、reviewers 等常用参数。
- 所有 POST 命令默认 dry-run；真实请求必须 `--confirm`，并在输出中显示脱敏请求摘要。

原因（Why）:

- 用户明确需要回复评论、仓库创建和合并请求创建；这些属于有副作用 API，必须用确认机制和测试保护。

位置（Where）:

- 文件/模块：`gl_notes.py`、`gl_projects.py`、`gl_mrs.py`、`gitlab_common.py`
- API/配置：Notes Create、Projects Create、Merge Requests Create
- 测试/文档：`tests/test_write_commands.py`、`references/security.md`、`references/api-map.md`

参考来源（References）:

- GitLab Notes API：`POST /projects/:id/issues/:issue_iid/notes` 与 MR notes。
- GitLab Projects API：`POST /projects`。
- GitLab Merge Requests API：`POST /projects/:id/merge_requests`。

适用规范（Standards applied）:

- GitLab PAT `api` scope 才能覆盖写 API；`write_repository` 不作为 REST API 写入凭据。
- 写操作请求体和预览必须 token 脱敏，正文不写入日志。

开发质量检查（Development quality checks）:

- 没有 `--confirm` 时不得发送 POST。
- dry-run 输出必须不包含 token，不包含完整敏感正文，最多显示摘要和长度。
- HTTP 401/403/404/409/422 必须输出可理解错误，不吞掉 GitLab message。

验证（Validation）:

- fake HTTP tests 验证 dry-run 不调用 opener。
- fake HTTP tests 验证 `--confirm` 才发送 POST，body、query 和 headers 正确。
- env missing、token redaction、body-file/stdin 路径测试。
- live 写入 smoke 仅允许在 `codex_test` 测试仓库执行，优先选择“回复测试 issue/MR 评论”这类可回溯、低风险操作。
- 项目创建 live smoke 默认不执行；MR 创建 live smoke 只有在存在明确测试分支、不会影响真实协作流程时才执行，否则只使用 fake HTTP。
- 禁止 live 测试删除、关闭、合并、force、权限变更、token 管理、批量修改等危险操作。

风险和回滚（Risks and rollback）:

- 风险：误发评论或创建资源。回滚：默认 dry-run、必须 `--confirm`、测试强制未确认不 POST。
- 风险：正文通过命令行进入 shell history。回滚：优先 `--body-file` 或 stdin，在文档和 help 中强调。
- 风险：测试仓库残留评论噪声。回滚：评论内容使用明确标记，例如 `[codex gitlab skill smoke]`，最终交付记录具体 URL 或 note id。

阶段契约（Stage Contract）:

- 范围：只实现回复 note、创建 project、创建 MR 三类写操作。
- 允许修改：对应脚本、common request helper、security/api-map references 和写操作测试。
- 禁止修改：不实现删除、关闭、合并、approve、force push、token 管理。
- 进入条件：Stage 3 只读命令和 fixtures 通过。
- 退出条件：写操作 dry-run/confirm 测试通过，security reference 说明 scope、确认策略和 `codex_test` live 写入边界。
- 必需验证：AST parse、unit tests、dry-run redaction tests；如执行 live 写入，只能在 `codex_test`。
- 是否预期提交：no，除非用户明确授权阶段提交。

### Stage 5: skill references, evals, docs, and safety examples

目标（Goal）:

- 完善 references、eval、README、CHANGELOG 和安全示例，让 skill 可被后续 agent 稳定复用。

做法（How）:

- `workflow.md`: 记录先 doctor、再只读定位、最后 dry-run/confirm 写入的标准流程。
- `api-map.md`: 表格化 endpoint、脚本命令、必需 scope、参数、分页、限流和注意事项。
- `security.md`: 记录 PAT scope、环境变量、脱敏、body-file/stdin、dry-run、confirm 和禁止操作。
- `evals/gitlab/prompts.jsonl`: 覆盖触发、缺失 env、项目搜索、issue 详情、评论解析、写操作 dry-run、拒绝高风险删除。
- README/CHANGELOG: 记录新增 skill 和验证命令。

原因（Why）:

- skill 的价值不只是脚本，还包括让 agent 在复杂 GitLab 任务中知道何时搜索、何时只读、何时请求确认和如何记录未覆盖项。

位置（Where）:

- 文件/模块：`skills/gitlab/references/*.md`、`evals/gitlab/prompts.jsonl`
- API/配置：无新增 live API
- 测试/文档：`README.md`、`CHANGELOG.md`

参考来源（References）:

- skill-creator progressive disclosure。
- GitLab 官方 API docs 的 endpoint 和 scope 摘要。
- 本计划 Research Gate 与 Standards Discovery Gate。

适用规范（Standards applied）:

- 不在 `SKILL.md` 复制 API 全量细节；大表放 `api-map.md`。
- references 超过 100 行时增加简短目录或章节导航。
- eval prompt 不泄露真实 token 或真实私有 GitLab URL。

开发质量检查（Development quality checks）:

- references 与脚本命令名称一致。
- api-map 中每个写操作都标明 required scope 和 safety gate。
- eval 场景应覆盖成功路径和拒绝/缺失路径，而不是只测 happy path。

验证（Validation）:

- JSONL parse，并检查 id 唯一。
- `Select-String` 检索 `SKILL_GITLAB_BASE_URL`、`SKILL_GITLAB_PAT`、`read_api`、`api`、`read_repository`、`write_repository`、`--confirm`、`dry-run`。
- README/CHANGELOG diff check。

风险和回滚（Risks and rollback）:

- 风险：文档与脚本漂移。回滚：Stage 6 通过命令名和 endpoint 检索统一复查。
- 风险：references 过长。回滚：保留 api-map 表格和 workflow 摘要，移除重复解释。

阶段契约（Stage Contract）:

- 范围：references、eval、README、CHANGELOG 和安全示例。
- 允许修改：`skills/gitlab/references/**`、`evals/gitlab/**`、README、CHANGELOG。
- 禁止修改：不新增未实现命令，不写真实 token，不写真实私有项目信息。
- 进入条件：Stage 4 写操作安全测试通过。
- 退出条件：文档与脚本命令一致，eval 可解析，README/CHANGELOG 更新清楚。
- 必需验证：JSONL parse、关键词检索、diff check。
- 是否预期提交：no，除非用户明确授权阶段提交。

### Stage 6: full validation and handoff

目标（Goal）:

- 完成整体验证、代码审查、状态同步、未覆盖说明和最终交付准备。

做法（How）:

- 跑 planner/executor 相关检查：plan check、active-task JSON、环境清单关键字段。
- 跑 Python 检查：AST parse、`python -B -m unittest discover skills/gitlab/tests`。
- 跑文档/eval 检查：JSONL parse、关键命令和 scope 检索、README/CHANGELOG diff。
- 跑 Git 检查：串行 `git --no-optional-locks status --short --branch --untracked-files=all` 和 `git -c diff.autoRefreshIndex=false diff --check`。
- 用户已声明环境中有 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT`，实施阶段应执行只读 live smoke。
- live 写入 smoke 只允许在 `codex_test` 测试仓库内执行，优先验证评论回复；危险操作仍然禁止。

原因（Why）:

- 确保各流程、脚本、规则和文档一致，且基础验证不依赖真实 GitLab token 才能完成。

位置（Where）:

- 文件/模块：全仓库相关改动、`.harness` 任务记录。
- API/配置：live `/user`、只读搜索、受限 `codex_test` 写入 smoke。
- 测试/文档：unit tests、eval、README、CHANGELOG。

参考来源（References）:

- `complex-coding-executor` workflow：Stage Exit、Code Review、final gate、commit policy。
- 本计划 Validation、Documentation、Process Manager Gate。

适用规范（Standards applied）:

- 不声称未执行的 live smoke 已通过；写入 smoke 必须记录仓库、对象、note id 或 URL。
- 所有验证失败必须记录命令、失败原因、影响和替代证据。
- 提交必须等待用户授权，并使用 `git commit -F`。

开发质量检查（Development quality checks）:

- 检查 common client 没有过宽职责。
- 检查写操作默认安全态。
- 检查 tests 不依赖真实 token。
- 检查 references 中无 token 明文和私有 URL。

验证（Validation）:

- `python skills/complex-coding-planner/scripts/harness_plan_check.py --plan <plan>`
- `python -B -m unittest discover skills/gitlab/tests`
- AST parse、JSONL parse、diff check、git status。
- live read smoke 结果；受限 `codex_test` write smoke 结果或未执行原因。

风险和回滚（Risks and rollback）:

- 风险：真实 GitLab 权限差异无法由 fake HTTP 覆盖。回滚：执行只读 live smoke，并把写入 live smoke 限定到 `codex_test`。
- 风险：验证命令因 Windows profile 或 `__pycache__` 权限噪声失败。回滚：使用 `login:false`、`python -B` 或 AST parse 替代，并真实记录。

阶段契约（Stage Contract）:

- 范围：验证、代码审查、状态同步和最终交付。
- 允许修改：`.harness` 记录、README/CHANGELOG 小修、测试修复、文档一致性修复。
- 禁止修改：不得扩大功能范围或新增高风险 GitLab 写操作。
- 进入条件：Stage 1-5 退出门禁通过。
- 退出条件：Goal Condition 满足，未覆盖项记录，提交授权状态明确。
- 必需验证：plan check、unit tests、AST parse、JSONL parse、diff check、git status。
- 是否预期提交：只有用户明确授权时 yes。

## 环境（Environment）

- 仓库（Repository）: `D:\Item\vibe_coding\dev-skills`
- 运行时（Runtime）: Windows PowerShell、Python 标准库、无新增包管理器依赖
- 必填：`SKILL_GITLAB_BASE_URL`
- 必填其一：`SKILL_GITLAB_PAT` 或 `SKILL_GITLAB_TOKEN`
- 用户声明状态：`SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT` 已在环境变量中配置好，实施阶段可用于安全 live smoke。
- PowerShell 示例：`$env:SKILL_GITLAB_BASE_URL="https://gitlab.example.com"`；`$env:SKILL_GITLAB_PAT="..."`。
- 缺失处理：`gl_doctor.py` 必须退出非 0，并提示设置上述变量；不得打印 token。
- live 写入测试仓库：`codex_test`，仅用于低风险写入 smoke。
- 长期进程（Runtime services）: not required，v1 不启动后台服务。

## Git（Git Context）

主分支（Main branch）:

- main

任务类型（Task type）:

- feature

工作分支（Working branch）:

- `harness/feature`

分支动作（Branch action）:

- reuse / already-on-branch

同步来源（Sync source）:

- `.harness/environment.md` 记录的主分支和 harness 分支策略。

最近同步（Last sync）:

- not checked in planning revision；实施阶段进入 Stage 1 前由 executor 串行确认。

分支占用（Branch occupancy）:

- 串行 `git log <main>..HEAD`: Stage 1 前检查。
- 串行 `git -c diff.autoRefreshIndex=false diff <main>...HEAD --name-only`: Stage 1 前检查。
- 现有提交属于本任务（Existing commits belong to this task）: not confirmed；当前 planning only 不改实现代码。

Git 命令策略（Git command policy）:

- 同一仓库 Git 命令必须串行。
- 禁止通过并发工具、子 agent、后台任务、多 shell 或脚本并发运行同仓库 Git。
- 非 Git 文件读取和文本搜索可并发；Git status、diff、add、commit 必须串行。

只读 Git 选项（Read-only Git options）:

- 状态检查优先：`git --no-optional-locks status --short --branch --untracked-files=all`
- diff 检查优先：`git -c diff.autoRefreshIndex=false diff <range>`

Index lock 恢复策略（Index lock recovery）:

- lock 路径解析命令：`git rev-parse --git-path index.lock`
- 删除前检查：精确路径、文件存在、大小/mtime 稳定、无活跃或未知归属 Git 进程。
- 删除范围：只删除解析出的精确 `index.lock`，禁止通配符、递归删除和删除其它 `.lock`。
- 删除后检查：串行 `git --no-optional-locks status --short --branch`。

Git Lock Recovery Log:

| 时间（Time） | lock 路径（Lock path） | 文件大小/mtime（Size/mtime） | Git 进程检查（Process check） | 操作（Action） | 后续 status（Follow-up status） |
| --- | --- | --- | --- | --- | --- |
| not-applicable | none | none | none | none | none |

提交策略（Commit policy）:

- 已授权提交。
- 用户在批准实施时明确授权阶段完成后使用 `git commit -F` 提交。
- 提交说明必须遵守用户全局格式并避免多余空行。

分支安全（Branch safety）:

- 不自动 stash、rebase、reset 或删除分支。
- 如遇用户改动，先读取上下文并协同处理，不回滚非本任务改动。

## 工具（Tooling）

- `apply_patch`：修改规划、skill、脚本和文档文件。
- PowerShell：读文件、跑 Python、跑 Git。
- Python：AST parse、unittest、JSONL/YAML 检查。
- web：只用于官方文档调研和必要可变事实核验。
- 限制（Limits）：不通过命令行参数传 token，不把 token 写入 fixture、日志、`.harness` 或 commit message；live smoke 只有用户环境提供 GitLab 变量时才执行。

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- no

process-manager skill 是否存在（process-manager skill available）:

- yes，本计划已参考 `skills/process-manager/SKILL.md` 和脚本模式。

规则结论（Rule decision）:

- v1 GitLab skill 只做有限 REST API 命令，不启动后台服务。
- `gl_*` 脚本、单元测试、AST 解析、JSONL 检查和 live smoke 都是 finite command，不进入 process-manager。
- 如果未来需要批量队列、webhook 回调、跨命令缓存或多 agent 并发协调，必须通过 Plan Amendment Gate 重新评估服务化，并由 executor 按 process-manager 规则托管。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| none | not-applicable | all | none | none | none | execution-plan validation evidence | not-applicable |

禁止 shell 后台启动确认（No shell background start）:

- passed。本计划不允许为 v1 GitLab skill 手写后台 shell 服务。

证据保留位置（Evidence retention location）:

- `execution-plan.md` 与实施阶段 ledger；如执行 live smoke，只记录脱敏结果。

## 验证（Validation）

规划阶段验证（Planning validation）:

- `python skills/complex-coding-planner/scripts/harness_plan_check.py --plan .harness/tasks/2026-07-09/feature/gitlab-skill-development/execution-plan.md`
- `git --no-optional-locks status --short --branch --untracked-files=all`

已执行（Executed）:

| 命令/工具（Command/tool） | 结果（Result） | 证据（Evidence） | 未覆盖（Not covered） |
| --- | --- | --- | --- |
| `python skills/complex-coding-planner/scripts/harness_plan_check.py --plan .harness/tasks/2026-07-09/feature/gitlab-skill-development/execution-plan.md` | passed | `PASS: plan structure is ready for approval` | 不验证业务实现 |
| `python -c "import json ... .harness/active-task.json"` | passed | `active-task json ok` | 不验证未来实现 |
| `git -c diff.autoRefreshIndex=false diff --check` | passed_with_warning | 仅 LF/CRLF 转换 warning，无 whitespace error | 不验证 untracked plan 文件内容 |
| `git --no-optional-locks status --short --branch --untracked-files=all` | passed | 显示 `.harness` 规划文件变更 | 不代表提交授权 |

实施阶段必跑验证（Required implementation validation）:

- AST parse：解析 `skills/gitlab/scripts/*.py` 和 `skills/gitlab/tests/*.py`，避免依赖 `__pycache__`。
- Unit tests：`python -B -m unittest discover skills/gitlab/tests`
- Doctor offline：`python -B skills/gitlab/scripts/gl_doctor.py --offline-check`
- Env missing check：临时清空相关环境变量后确认提示清楚且不泄露 token。
- JSONL parse：解析 `evals/gitlab/prompts.jsonl` 并检查 id 唯一。
- Plan check：重新检查本计划。
- Whitespace：`git -c diff.autoRefreshIndex=false diff --check`
- Live read smoke：使用用户已配置的 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT` 调用 `/user`，并执行一个只读项目查询或搜索。

实施阶段验证证据（Implementation validation evidence）:

| 命令/工具（Command/tool） | 结果（Result） | 证据（Evidence） | 未覆盖（Not covered） |
| --- | --- | --- | --- |
| `python -B C:\Users\CountRa\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\gitlab` | passed | `Skill is valid!` | 不验证 live GitLab 权限 |
| `python -B -m unittest discover skills\gitlab\tests` | passed | `Ran 10 tests ... OK` | fake HTTP 为主，不覆盖真实 GitLab 版本差异 |
| `python -B -c "import ast ..."` | passed | `ast ok 10` | 不生成 `__pycache__` |
| `python -B -c "import json ... evals/gitlab/prompts.jsonl"` | passed | `jsonl ok 5` | 不执行 eval runner |
| `python -B skills\gitlab\scripts\gl_doctor.py --offline-check --pretty` | passed | 输出 `token: ***redacted***`、`token_source: SKILL_GITLAB_PAT` | 不访问 GitLab |
| 临时清空 `SKILL_GITLAB_*` 后运行 `gl_doctor.py --offline-check --pretty` | passed | 退出码 2，提示 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT or SKILL_GITLAB_TOKEN` | PowerShell 控制台对中文有编码显示噪声，但字段正确 |
| `python -B skills\gitlab\scripts\gl_doctor.py --pretty` | passed | `/user` live smoke 通过，用户摘要为 `Countra`，token 脱敏 | 不验证写权限 |
| `gl_projects.py search/get Countra/codex_test` | passed | 定位项目 `Countra/codex_test`，id `82634854`，默认分支 `main` | 不读取所有项目 |
| `gl_issues.py list/get --project Countra/codex_test --iid 1` | passed | issue 1 为 opened，URL 指向 `codex_test` work item | issue 标题在 PowerShell 输出中有编码噪声 |
| `gl_notes.py issue-list --only-comments --compact` | passed | 成功读取并压缩 notes 字段 | 仅抽样前 5 条 |
| `gl_search.py --project Countra/codex_test --scope issues --query py` | passed | 搜索返回 issue 1 | 不覆盖 code search 许可差异 |
| `gl_projects.py create --name codex-skill-dry-run --path codex-skill-dry-run --pretty` | passed | dry-run 输出 `POST /projects` 预览，未发送真实创建请求 | 不做真实项目创建 |
| `gl_mrs.py create --project Countra/codex_test ... --pretty` | passed | dry-run 输出 `POST /merge_requests` 预览，未发送真实 MR | 不做真实 MR 创建 |
| `gl_notes.py issue-reply --project Countra/codex_test --iid 1 --body-file ... --pretty` | passed | dry-run URL 指向 `Countra%2Fcodex_test/issues/1/notes`，正文只显示长度和 preview | dry-run 不验证 POST 权限 |
| `gl_notes.py issue-reply --project Countra/codex_test --iid 1 --body-file ... --confirm` | passed | 受控 live 写入 smoke 创建 note id `3539465182`，正文带 `[codex gitlab skill smoke]` 标记 | 只在用户指定测试仓库写入一条评论 |
| `python -B skills\complex-coding-planner\scripts\harness_plan_check.py --plan .harness\tasks\2026-07-09\feature\gitlab-skill-development\execution-plan.md` | passed | `PASS: plan structure is ready for approval` | 结构检查不替代业务验证 |

受控 live 写入 smoke（Controlled live write smoke）:

- 仅允许在 `codex_test` 测试仓库内执行。
- 优先执行 issue/MR 评论回复 smoke，评论内容必须带明确标记，例如 `[codex gitlab skill smoke]`。
- 项目创建、MR 创建默认用 fake HTTP 测试；只有存在明确测试分支和低风险前置时才考虑 live MR 创建。
- 禁止 live 删除、关闭、合并、force、权限变更、token 管理、批量修改或跨仓库写入。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/gitlab/SKILL.md`：入口、触发条件、检查步骤和引用导航。
- `skills/gitlab/references/workflow.md`：agent 调用流程、常见任务路径和失败处理。
- `skills/gitlab/references/api-map.md`：REST endpoint、scope、参数、分页和响应摘要。
- `skills/gitlab/references/security.md`：PAT、环境变量、脱敏、dry-run、confirm 和写操作约束。
- `evals/gitlab/prompts.jsonl`：触发、环境缺失、只读查询、写操作 dry-run 和拒绝高风险操作场景。
- `README.md` 与 `CHANGELOG.md`：新增 skill 能力、验证命令和变更摘要。

Changelog 计划（Changelog plan）:

- 新增 `2026-07-09` 条目，记录 GitLab PAT 操作 skill 的规划/实现范围。
- Commit 字段保持 pending，直到用户授权提交并实际生成 commit。

## 文件写入策略（File Write Strategy）

分段判断（Segmentation decision）:

| 文件（File） | 分段判断（yes / no / unknown） | 分段边界（Segmentation boundary） | 整体复查方式（Whole-file review） |
| --- | --- | --- | --- |
| `skills/gitlab/SKILL.md` | no | 入口规则短文档 | 完整读取 |
| `skills/gitlab/references/workflow.md` | no | 工作流章节 | 完整读取和关键词检索 |
| `skills/gitlab/references/api-map.md` | no | endpoint 表格 | 完整读取和 URL 检索 |
| `skills/gitlab/references/security.md` | no | token/scope/write safety | 完整读取 |
| `skills/gitlab/scripts/gitlab_common.py` | yes | env/auth、request、pagination、errors | AST parse + unit tests |
| `skills/gitlab/scripts/gl_*.py` | no | 每个脚本独立子命令 | AST parse + targeted tests |
| `skills/gitlab/tests/*` | no | fake HTTP 和命令测试 | unittest |
| `README.md`、`CHANGELOG.md` | no | 独立条目 | diff check |

写入规则（Write rules）:

- 文件超过 500 行前必须先拆分规划；对已有大文件优先局部 patch。
- 单次 patch 优先控制在 120 行左右，必要时按语义完整段落拆分。
- 不使用 shell 重定向生成长文件；手工编辑使用 `apply_patch`。

整体复查（Whole-file review）:

- 写完后重新读取新增 skill 入口、references、脚本和测试。
- 检查环境变量名、scope 文案、写操作确认策略、命令名称和 README 是否一致。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| Q-001 | no | closed | skill 名称是否使用 `gitlab` 还是 `gitlab-ops` | 默认 `gitlab`，触发更直接；如后续用户偏好改名需 Plan Amendment Gate | Stage 1 |
| Q-002 | no | closed | 是否采用后台服务 | v1 采用脚本型；服务化只作为未来扩展 | Decision / Process Manager Gate |
| Q-003 | no | closed | token 环境变量是否只支持一种 | 支持 skill 专属 `SKILL_GITLAB_PAT`，兼容同前缀 `SKILL_GITLAB_TOKEN`；默认不读取通用 `GITLAB_TOKEN` | Environment / Stage 2 |
| Q-004 | no | closed | 写操作是否默认真实执行 | 否，默认 dry-run 或必须 `--confirm` | Stage 4 |
| Q-005 | no | closed | 没有 GitLab 环境变量是否阻塞实现 | 用户已声明 env 可用；仍保留 env missing check，live smoke 使用当前 env | Validation / Stage 6 |
| Q-006 | no | closed | live 写入 smoke 可以在哪里执行 | 只允许在 `codex_test` 测试仓库中执行低风险评论回复等写入；危险操作禁止 | Stage 4 / Stage 6 |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | passed | Context 和 Source matrix 已记录 |
| Research Gate 已完成（Research Gate complete） | passed | 已调研 GitLab 官方 auth、PAT、pagination、Projects、Search、Issues、Notes、MR、Repository docs |
| Standards Discovery Gate 已完成 | passed | 规范发现门禁覆盖 GitLab API、Python style、Python stdlib 和适用边界 |
| Development Quality Gate 已完成 | passed | 开发质量门禁覆盖代码标准、静态质量、架构边界、设计模式、耦合、内聚和验证映射 |
| 候选方案比较充分（Options compared enough） | passed | 已比较服务型、脚本型、混合型 |
| 每阶段可独立验证（Stages independently verifiable） | passed | Stage 1-6 均有阶段契约和验证 |
| 风险和重新批准条件明确（Reapproval triggers clear） | passed | Decision 已记录 reapproval triggers |
| executor 交接章节完整（Executor handoff complete） | passed | 已补齐 Execution Control Snapshot、Process Manager Gate、Implementation Progress、Stage Gates、Ledger、Code Review、Resume 和 Commit Log |

质量结论（Quality result）:

- passed。方案可提交用户审批。

## 规划自查（Plan Self-Review）

自查结论（Review result）:

- passed

| 类别（Category） | 发现（Finding） | 处理（Action） | 结果（Result） |
| --- | --- | --- | --- |
| 缺陷（Defects） | 初始需求包含服务型和脚本型两种可能 | 通过 Options 明确选择脚本型 v1 | closed |
| 缺陷（Defects） | 早期误把 500 行写入阈值理解为整体规划长度限制，导致计划过度压缩 | 重读 planner workflow 和 template，恢复完整交接章节并扩展阶段契约 | closed |
| 风险（Risks） | PAT 容易泄露到日志或 shell history | 禁止 token 参数，写操作正文优先 body-file/stdin | closed |
| 缺失项（Missing items） | GitLab API 有分页和版本差异 | Stage 2 统一分页和错误处理 | closed |
| 缺失项（Missing items） | 缺少 Process Manager Gate、Documentation、Questions、Plan Amendment、Stage Gates 和 Resume | 已按模板补齐 | closed |
| 缺失项（Missing items） | 写操作容易误触发 | Stage 4 强制 dry-run 或 `--confirm` | closed |
| 一致性（Consistency） | 环境变量名称可能和其它 GitLab 工具混用 | 改为 `SKILL_GITLAB_*` 专属前缀，突出本 skill 使用 | closed |
| 风险（Risks） | live 写入测试可能影响真实仓库 | 用户指定 `codex_test` 为测试仓库，计划限定写入 smoke 只在该仓库执行并禁止危险操作 | closed |
| 过度设计（Overengineering） | 服务化会引入长期 token 和进程生命周期 | v1 不启服务，未来需求再评估 | closed |

门禁重跑（Gate rerun）:

- `Plan Quality Gate` 是否需要重跑：no
- `Plan Self-Review` 是否需要重跑：no
- `Readiness Gate` 是否需要重跑：no
- 原因：自查未改变目标、范围、阶段或验证策略。

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | passed | Problem/Acceptance |
| 上下文已收集（Context collected） | passed | process-manager、electron-ui-verifier、planner、executor 和 skill-creator 已读 |
| Research Gate 已通过 | passed | 调研门禁 online-required passed，来源矩阵包含 GitLab 官方 docs |
| Standards Discovery Gate 已通过 | passed | 规范发现门禁包含技术栈、规范来源、standards index、官方来源和适用边界 |
| Development Quality Gate 已通过 | passed | 开发质量门禁包含代码标准、静态质量、架构边界、设计模式、耦合、内聚和验证映射 |
| 候选方案已比较（Options compared） | passed | Options A/B/C |
| 决策已记录（Decision recorded） | passed | 选择脚本型 skill |
| 实施阶段已细化（Implementation stages detailed） | passed | Stage 1-6 |
| 环境已确认（Environment confirmed） | passed | Environment |
| Git 上下文已确认（Git context confirmed） | passed | Git Context |
| 工具已确认（Tooling confirmed） | passed | Tooling |
| 验证已确认（Validation confirmed） | passed | Validation |
| 文件写入策略已确认（File write strategy confirmed） | passed | File Write Strategy |
| 规划自查已通过（Plan Self-Review passed） | passed | Plan Self-Review |
| 阻塞问题已关闭（Blocking questions closed） | passed | Open uncertainties |

就绪结论（Readiness result）:

- passed。当前应停止在审批点，等待用户明确批准后进入执行阶段。

## 方案批准（Plan Approval）

状态（Status）:

- approved

批准记录（Approval record）:

- 2026-07-09 用户批准：“接下来使用 complex-coding-executor 的规则 实现这个方案，授权提交，阶段完成后 可以使用-F提交”。

批准摘要（Approval summary）:

- 建议批准范围（Proposed scope）: Stage 1-6 全部。
- 阶段提交授权（Stage commit authorization）: authorized。
- 工具/MCP 授权（Tool/MCP authorization）: local shell、apply_patch、Python、Git read checks、official web docs research。
- 文档更新授权（Documentation authorization）: authorized。

提交策略（Commit policy）:

- authorized。阶段完成后可使用 `git commit -F`，避免多余空行。

## 方案变更门禁（Plan Amendment Gate）

需要重新批准（Requires reapproval）:

- approved scope 改变：新增删除项目、删除分支、关闭/合并 MR、approve MR、force push、token 管理、CI/CD 管理或 GraphQL。
- 阶段边界、顺序或 Stage Contract 改变：从 6 阶段改为服务化、合并写操作与只读阶段、跳过 security/eval 阶段。
- 必需验证、工具授权、长期进程策略或提交策略改变：新增第三方依赖、网络安装、后台服务、真实 GitLab 写入 smoke 或自动提交。
- 风险等级、公共接口、数据结构、权限、依赖或兼容性假设改变：改变 env 变量契约、保存 token、改变默认写操作确认策略。
- attestation mismatch 且无法证明是预期文档更新：停止执行并重新核对计划。

无需重新批准的记录（No-reapproval records）:

| 时间（Time） | 变更（Change） | 原因（Reason） | 证据（Evidence） |
| --- | --- | --- | --- |
| 2026-07-09 | 复查并扩展规划文档 | 修正单次写入阈值误解，补齐 planner 模板和 executor 交接门禁 | 本文件 |

## 执行控制（Execution Control）

- 执行模式（Execution mode）: run-to-completion
- 整体任务状态（Overall status）: complete
- 当前阶段（Current stage）: Final
- 已完成阶段（Completed stages）: Planning research and plan revision, Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6
- 剩余阶段（Remaining stages）: none
- 下一步自动动作（Next automatic action）: final delivery complete
- 当前停止条件（Current stop condition）: none
- 状态来源（State source of truth）: execution-plan.md

active-task 同步字段（active-task sync fields）:

```json
{
  "execution_mode": "run-to-completion",
  "overall_status": "complete",
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
| Planning | complete | 已完成官方 API/PAT 调研、方案复查和 planner 规则补齐，并获用户批准 | plan check passed | execution-plan.md | Stage 1 completed |
| Stage 1 | complete | 创建 `skills/gitlab` scaffold、入口规则和使用契约 | skill quick validate passed | `skills/gitlab/SKILL.md`、`agents/openai.yaml` | Stage 2 completed |
| Stage 2 | complete | 实现 PAT 环境读取、base URL 规范化、共享 REST client、分页、退避和脱敏 | unittest、AST、doctor offline/env missing passed | `gitlab_common.py`、`gl_doctor.py`、`test_common.py` | Stage 3 completed |
| Stage 3 | complete | 实现项目、搜索、仓库、issue、notes、MR 只读命令 | fake tests、live read smoke、`gl_search.py` smoke passed | `gl_projects.py`、`gl_search.py`、`gl_repo.py`、`gl_issues.py`、`gl_notes.py`、`gl_mrs.py` | Stage 4 completed |
| Stage 4 | complete | 实现项目创建、MR 创建、issue/MR 回复的 dry-run 和 `--confirm` 防护 | dry-run tests、`codex_test` note smoke passed | note id `3539465182` | Stage 5 completed |
| Stage 5 | complete | 补充 workflow/API/security references、eval、README 和 CHANGELOG | JSONL parse、关键词/结构复查 passed | `references/*.md`、`evals/gitlab/prompts.jsonl`、`README.md`、`CHANGELOG.md` | Stage 6 completed |
| Stage 6 | complete | 完成整体验证、代码审查、状态同步和提交准备 | validation matrix passed | Validation evidence、Ledger Evidence、Code Review | final delivery complete |

## Ledger Evidence

Ledger policy:

- append-only-after-approval

Ledger 文件（Ledger file）:

- `.harness/tasks/2026-07-09/feature/gitlab-skill-development/ledger.jsonl`

Ledger 摘要（Ledger summary）:

| 字段（Field） | 值（Value） |
| --- | --- |
| entries | 14 |
| stages_completed | Stage 1, Stage 2, Stage 3, Stage 4, Stage 5, Stage 6 |
| current_stage | Final |
| last_blocking_reason | none |
| last_heartbeat | none |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | checked | none | Python/PowerShell available | not required | scaffold only | passed |
| Stage 2 | checked | Stage 1 docs complete | Python stdlib | not required | auth/client only | passed |
| Stage 3 | checked | Stage 2 client complete | fake HTTP tests and live read env | not required | read-only only | passed |
| Stage 4 | checked | Stage 3 readonly complete | dry-run tests and `codex_test` write boundary | not required | approved write ops only | passed |
| Stage 5 | checked | Stage 4 safety complete | JSONL/docs tools | not required | docs/evals only | passed |
| Stage 6 | checked | Stage 1-5 complete | full validation tools | not required | validation/handoff only | passed |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 关键日志已沉淀（Log evidence persisted） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage 1 | yes | yes | yes | not-applicable | yes | yes | authorized pending final commit | passed |
| Stage 2 | yes | yes | yes | not-applicable | yes | yes | authorized pending final commit | passed |
| Stage 3 | yes | yes | yes | not-applicable | yes | yes | authorized pending final commit | passed |
| Stage 4 | yes | yes | yes | not-applicable | yes | yes | authorized pending final commit | passed |
| Stage 5 | yes | yes | yes | not-applicable | yes | yes | authorized pending final commit | passed |
| Stage 6 | yes | yes | yes | not-applicable | yes | yes | authorized pending final commit | passed |

## 阶段转移门禁（Stage Transition Gate）

| 阶段（Stage） | 当前阶段已完成（Stage done） | Review 已完成（Review done） | 验证完成或替代证据已记录（Validation done） | 提交或未提交原因已记录（Commit recorded） | 是否还有 pending stage（Pending remains） | 是否存在停止条件（Stop Condition） | 是否需要重新批准（Reapproval needed） | Execution Control 已更新 | active-task 已同步 | 阶段边界允许停止（May stop） | 下一动作（Next action） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | yes | yes | plan check passed | authorized | yes | none | no | yes | yes | no | continue Stage 1 |
| Stage 1-5 | yes | yes | yes | authorized pending final commit | yes until next stage, then no | none | no | yes | yes | no | continue next Stage |
| Stage 6 | yes | yes | yes | authorized pending final commit | no | none | no | yes | yes | yes | final delivery complete |

规则（Rules）:

- 如果还有 pending stage，且没有停止条件，也不需要重新批准，下一动作必须是 `continue Stage N`。
- 阶段边界不是停止条件；只有审批点、blocking decision、用户明确暂停或 Plan Amendment Gate 才能停止。

## 代码审查（Code Review）

| 阶段（Stage） | 质量维度（Quality dimension） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- | --- |
| Planning | standards / process | 早期计划被压缩过度，缺少 executor 交接章节 | major | 已按 planner workflow 补齐模板要求 |
| Stage 1 | skill structure / standards | `SKILL.md` 入口简洁，细节已下沉 references，符合 skill-creator 结构 | none | closed |
| Stage 2 | auth / security / coupling | `gitlab_common.py` 负责 env/auth/request/pagination/output，业务脚本不直接处理 token；未读取通用 `GITLAB_TOKEN` | none | closed |
| Stage 3 | readonly API / architecture | 只读脚本按项目、搜索、仓库、issue、notes、MR 分工，高内聚且通过共享 client 复用低层能力 | none | closed |
| Stage 4 | write safety / validation | 写操作默认 dry-run，真实 POST 必须 `--confirm`；live 写入限定 `Countra/codex_test` issue 1 并成功创建测试 note | none | closed |
| Stage 5 | docs/evals / cohesion | reference、README、CHANGELOG 和 eval 均同步专属环境变量、安全边界和禁止操作 | none | closed |
| Stage 6 | final validation / static quality | skill 校验、unittest、AST、JSONL、doctor、live read/write smoke 和 plan check 均已通过；`__pycache__` 未生成 | none | closed |

## 恢复摘要（Resume Summary）

Resume Packet:

```json
{
  "task_id": "2026-07-09-feature-gitlab-skill-development",
  "execution_mode": "run-to-completion",
  "overall_status": "complete",
  "current_stage": "Final",
  "remaining_stages": [],
  "next_automatic_action": "final delivery complete",
  "stop_condition": "none",
  "ledger_entries": 14,
  "last_blocking_reason": "none",
  "attestation_status": "not_checked"
}
```

- 整体目标（Overall goal）: 新增 GitLab PAT 操作 skill，支持仓库、搜索、issue、评论、项目创建和 MR 创建。
- 执行模式（Execution mode）: run-to-completion。
- 当前阶段（Current stage）: Final。
- 剩余阶段（Remaining stages）: none。
- 最新 commit（Latest commit）: pending final `git commit -F`。
- 长期进程规则（Process manager rule）: v1 not required。
- 未覆盖/风险（Not covered/risks）: 未做真实项目创建和真实 MR 创建；这两类写操作已通过 dry-run 和 fake HTTP 单测覆盖，避免影响真实 GitLab 资源。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/2026-07-09/feature/gitlab-skill-development/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | not required | plan approved by user | not required |
| Stage 1-6 | dev-skills | current commit after final `git commit -F` | `feat(gitlab): 新增 GitLab PAT 操作 skill` | `CHANGELOG.md` 2026-07-09 GitLab PAT 操作 skill |

## 最终交付（Final Delivery）

最终结论（Final result）:

- complete。Stage 1-6 已全部完成，remaining stages 为空，无 blocking decision，无未关闭 major finding。
- 新增脚本型 `gitlab` skill，不启动后台服务，不引入第三方依赖，不保存 token。
- 环境变量契约为 `SKILL_GITLAB_BASE_URL`、`SKILL_GITLAB_PAT`，并兼容同前缀别名 `SKILL_GITLAB_TOKEN`；默认不读取通用 `GITLAB_TOKEN`。
- 只读能力覆盖项目、搜索、仓库 tree/file/raw、issue、notes 和 MR；写能力覆盖项目创建、MR 创建和 issue/MR 评论回复，默认 dry-run，真实请求必须 `--confirm`。
- 受控 live 写入 smoke 已限定在用户指定的 `Countra/codex_test` issue 1，创建 note id `3539465182`。

剩余风险（Residual risk）:

- 未验证 self-managed GitLab 的版本差异、企业版搜索许可差异和所有 scope 组合。
- 未执行真实项目创建和真实 MR 创建；当前选择以 dry-run 和 fake HTTP 覆盖，避免产生真实资源。
- PowerShell 表格输出对中文 issue 标题存在编码显示噪声，但 JSON 字段和脚本行为正常。

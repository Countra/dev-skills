# 执行计划（Execution Plan）

## 规划摘要（Plan Summary）

- Task ID：`2026-07-10-feature-gitlab-process-manager-capability-upgrade`
- Plan revision：`5`
- Lifecycle route：`managed`
- Plan profile：`full`
- Discovery-first：`no`
- Task contract：`plan-contract.json`
- Approval scope：实施与最终一次 `git commit -F` 已授权；执行器不执行 GitHub push/Actions 或任何 elevated 操作，提交后的 push 与三平台 CI 由用户自行完成；不包含 GitLab live write、本机/生产提权、默认分支 push 或 PR。

本文件只保存批准意图。批准后不得写入 current stage、progress、运行结果、ledger 摘要或 commit 状态；执行事实由 executor 创建的 attestation、run-state 和 ledger 保存。

## 问题定义（Problem）

目标（Goal）：`GOAL-01`

- 将 `gitlab-pat-ops` 从“已有资源脚本 + 分散 guard”升级为同源凭据边界、单一能力注册表、可组合资源命令和绑定式 preview/apply。
- 将 `process-manager` 从“Windows-only PID + taskkill + JSON 文件”升级为平台透明的统一 CLI/schema/envelope；内部 dispatcher 自动选择 Windows Job Object、Linux delegated cgroup v2 或安全 fallback、macOS/POSIX process-group guardian，并具备完整 run identity、线程安全 state、秘密隔离、有界 probe/log 和 owner-death cleanup。
- 直接切换当前 contract，不保留旧 env/schema/CLI alias、legacy fallback、迁移 parser 或 v1/v2 名称。
- 同步所有真实消费者与 eval，使两个 skill 的能力不仅写在文档里，而且能被确定性验证。

非目标（Non-goals）:

- 不实现 GitLab daemon、webhook/cache、GraphQL/GLQL/Work Item 双栈、PAT/DPoP 私钥生命周期管理。
- 不支持 GitLab delete、merge、approve、token/permission、CI/repository mutation 或 bulk cross-project write。
- 不把 process-manager 扩展为自动重启编排、远程 supervisor、GUI app manager、资源调度器或动态平台插件系统。
- 不迁移 ignored old runtime，不修改历史 `.harness/tasks/**`，不顺手重构无关 skill。

约束（Constraints）:

- 全部新增/修改注释使用中文。
- Python runtime 保持 3.11+ stdlib/ctypes 与受控 OS 原生设施；公共 bootstrap 不依赖 PowerShell；不引入 pywin32/psutil/python-systemd。
- GitLab required validation 不产生真实写入；可选 write smoke 必须另行授权且只能命中测试项目。
- 三平台 lifecycle 测试只操作本轮创建且 owner/run identity 可证明的 process/job/cgroup/process-group；不枚举未知 PID。
- 生产 skill 不自动 sudo、enable-linger、修改全局 unit/未委托 cgroup；macOS 不安装 LaunchDaemon。仓库 workflow 可在用户后续运行的隔离 Ubuntu runner 中以 `--collect` transient test unit 验证 cgroup strict，但不属于本次执行器授权；平台原生能力不可用时只允许内部 dispatcher 自动选择契约内安全 fallback，公共接口保持不变。
- 批准计划、contract 和 approval-included artifact 在批准后不可变。

待确认项（Open uncertainties）:

- 无 blocking design decision。Windows Job/CTRL_BREAK 已由当前 Windows 本机 smoke 覆盖；Linux delegation/cgroup 与 macOS guardian/process-group 的真实 runner 组合行为保留为可选的提交后 VAL-12。未取得该证据不阻断本地提交，但不得宣称三平台 hosted runner 已验证通过。
- GitLab 写 API 不提供通用 CAS 是已接受残余风险；方案不声称提供服务端原子更新。

## 需求与验收（Requirements And Acceptance）

功能需求：

| ID | Priority | Requirement | Evidence |
| --- | --- | --- | --- |
| REQ-01 | must | GitLab 同源/TLS/redirect/retry/rate-limit/response budget transport | VAL-01, VAL-07, VAL-09 |
| REQ-02 | must | PAT self/metadata doctor、单一能力 registry、current env contract | VAL-01, VAL-02, VAL-08 |
| REQ-03 | must | namespace/template/commit/diff/pipeline/job/approval/discussion/event 模块 | VAL-01, VAL-02 |
| REQ-04 | must | 通用 issue/MR/thread guarded write 与 fingerprint/preflight | VAL-01, VAL-02, VAL-09 |
| REQ-05 | must | GitLab tests/eval/skill docs/metadata | VAL-01, VAL-02, VAL-08 |
| REQ-06 | must | 单一公共 process-manager contract 与内部自动 supervisor dispatcher、manager/run identity、平台锁、Windows Job、Linux cgroup/fallback、macOS guardian | VAL-03, VAL-04, VAL-12 |
| REQ-07 | must | locked/recoverable state、closed schema、secret、DACL/POSIX mode、control API | VAL-03, VAL-04, VAL-07, VAL-12 |
| REQ-08 | must | graceful-force stop、restart、incremental probes、rotating logs、diagnostics | VAL-03, VAL-04, VAL-05 |
| REQ-09 | must | process-manager portable/native tests、三平台 CI、eval/agents/references | VAL-03, VAL-04, VAL-05, VAL-08, VAL-12 |
| REQ-10 | must | electron/planner/executor/README/examples/ignore/eval/changelog cutover | VAL-05, VAL-06, VAL-07, VAL-08 |

非功能需求：

| ID | Requirement | Validation |
| --- | --- | --- |
| NFR-01 | 安全默认，凭据不跨源/落盘/入日志，kill/write fail closed | VAL-01, VAL-03, VAL-04, VAL-07, VAL-09 |
| NFR-02 | 写不隐式重放，状态线性一致，无重复 active service | VAL-01, VAL-03, VAL-04, VAL-09 |
| NFR-03 | pagination/body/retry/log/probe/history 全部有界 | VAL-01, VAL-03, VAL-04, VAL-07, VAL-09 |
| NFR-04 | 高内聚低耦合，生产 Python 文件不超过 500 行 | VAL-01, VAL-02, VAL-03, VAL-05, VAL-06, VAL-07, VAL-08, VAL-09 |
| NFR-05 | Python stdlib/ctypes + OS 原生设施，公共运行不依赖 PowerShell，GitLab 不服务化 | VAL-01, VAL-03, VAL-04, VAL-06, VAL-07, VAL-09, VAL-12 |
| NFR-06 | 不保留旧 alias/schema/fallback/migration/version naming | VAL-01, VAL-02, VAL-03, VAL-05, VAL-06, VAL-07, VAL-08, VAL-09 |
| NFR-07 | 平台透明：Windows/Linux/macOS 使用同一 CLI、manager/service schema、response envelope 和 workflow；内部自动选择当前环境最强安全 backend，普通调用无平台参数/分支，真实能力只在内部审计与按需诊断中可观察 | VAL-03, VAL-04, VAL-05, VAL-06, VAL-07, VAL-09, VAL-12 |

验收标准：

| ID | Requirement IDs | Given / When / Then |
| --- | --- | --- |
| AC-01 | REQ-01 | 恶意 Link/redirect、超限响应和 transient error 下，PAT 不跨 origin/API prefix，读取/分页有上限，写 method 不自动重试 |
| AC-02 | REQ-02 | doctor/capabilities 只使用 current SKILL_GITLAB_*，安全报告 metadata/scope/expiry，仓内无旧 alias/version label |
| AC-03 | REQ-03 | agent 能组合资源脚本读取 template/commit/diff/pipeline/job/approval/discussion/event，不依赖一次性场景脚本 |
| AC-04 | REQ-04 | 写入 preview 绑定 target/payload/preflight，只有 exact fingerprint 才发送一次请求 |
| AC-05 | REQ-04 | 高影响写保持拒绝，自动 live smoke 仅允许显式测试项目 |
| AC-06 | REQ-05 | GitLab tests/eval/skill validation/docs consistency 全部通过且无真实写入 |
| AC-07 | REQ-06 | Windows/Linux/macOS 对外提供完全相同的 `pm_manager.py`/`pm_*` 方法、参数、service schema、response envelope 和错误码；并发 bootstrap/端口冲突下每个 workspace 只有一个 manager，调用方无需判断平台 |
| AC-08 | REQ-06 | 内部 dispatcher 自动选择 Windows Job、Linux delegated cgroup 或安全 process-group fallback、macOS guardian；child tree、manager crash、PID reuse 下只收口 owned run，未知平台或无安全 owner 时拒绝启动，普通响应不暴露 backend 选择责任 |
| AC-09 | REQ-07 | 并发 state 线性一致、损坏可重建、secret/完整敏感 argv 不进入 state/response/log |
| AC-10 | REQ-08 | 三平台 normal/ignore signal/dynamic port/large log/start failure 对外执行相同 graceful-force 生命周期，由内部 dispatcher 映射并记录平台无关 owner-empty 结果 |
| AC-11 | REQ-09 | executable tests/eval 与 Windows/Ubuntu/macOS matrix 先证明公共 CLI/schema/envelope/error parity，再覆盖内部平台 detect、自动 fallback、native lifecycle、crash、identity 和 cleanup，metadata/references 与 current CLI 一致 |
| AC-12 | REQ-10 | 所有仓内消费者和文档只生成/消费统一 current contract 与平台无关 evidence，不探测 OS、不选择 backend、不依赖正常响应中的平台诊断字段 |

## 调研门禁（Research Gate）

研究模式（Research mode）：`online-required`

触发原因（Why this mode）:

- GitLab API、PAT scope、pagination、deprecations 和版本演进属于会变化的外部事实。
- Windows Job/console、Linux cgroup/systemd delegation、macOS launchd/kqueue/process-group 和 Python subprocess/os/http.server 语义属于高风险平台事实。
- 用户明确要求深入调研领域前沿。

不确定项清单（Uncertainty inventory）:

| ID | 问题 | 类型 | Online | Resolution | 影响 |
| --- | --- | --- | --- | --- | --- |
| U-01 | Link 能否继续使用同时不泄露 PAT | external-service/high-risk | yes | 使用官方 Link，但 client 先做严格同源/API prefix 验证 | REQ-01 |
| U-02 | GitLab 写请求是否有通用幂等键 | external-service/high-risk | yes | 公共 REST 无通用保证，写请求禁用自动 retry | REQ-01/04 |
| U-03 | MR changes/template/approval 应选哪些当前 endpoint | external-service | yes | 使用 MR diffs、Project Templates、Approvals API | REQ-03 |
| U-04 | 三平台 process tree 如何获得最佳 ownership | external-tool/high-risk | yes | Windows Job；Linux delegated cgroup v2；macOS/POSIX guardian process group | REQ-06 |
| U-05 | 如何避免 target 在加入 native owner 前派生 | architecture/high-risk | yes | blocked service-host 先入 Job/cgroup 或建立 guardian/session，再接收 launch spec | REQ-06 |
| U-06 | PID reuse 如何识别 | external-tool/high-risk | yes | PID 非 authority；instance/run capability + owner handle/cgroup/group，平台 start identity 仅补充 | REQ-06/07 |
| U-07 | 各平台如何 graceful-force stop | external-tool/high-risk | yes | Windows CTRL_BREAK->Job；POSIX SIGTERM->cgroup.kill/SIGKILL group | REQ-08 |
| U-08 | 是否改成 named pipe/第三方 supervisor | architecture | yes | loopback HTTP 经硬化已足够，拒绝额外依赖/协议 | NFR-04/05 |
| U-09 | Linux 无 systemd/delegation、macOS 无 cgroup 如何兼容且不泄漏多套接口 | platform/high-risk | yes | 内部 dispatcher 按固定优先级自动选择最强安全 backend；公共 contract 不变，真实能力只在内部 identity/doctor/失败诊断可见 | REQ-06/NFR-07 |
| U-10 | 如何证明全平台而非 mock 分支 | validation/high-risk | yes | 仓库提供 GitHub Actions Windows/Ubuntu/macOS matrix；本次由用户提交后运行，未运行前不作全平台通过声明 | REQ-09/NFR-07 |

搜索记录（Search log）:

| 查询/来源 | 工具 | 日期 | 结果 | 后续动作 |
| --- | --- | --- | --- | --- |
| GitLab REST pagination/rate limit/PAT/deprecations/resources | Web，官方 docs.gitlab.com | 2026-07-10 | 发现 keyset、PAT self、Project Templates、MR diffs、request ID 和 deprecated fields | 写入 ART-01/03 |
| Microsoft Job Object/process time/mutex/ACL/console control | Web，Microsoft Learn | 2026-07-10 | 支持 Job tree、kill-on-close、creation time、named mutex、CTRL_BREAK | 写入 ART-01/02/03 |
| Linux cgroup v2/systemd delegation/kill | Web，kernel.org/systemd.io/systemd source | 2026-07-10 | child inheritance、cgroup.kill、single-writer/delegation、control-group stop | 写入 ART-01/02/03/04 |
| Apple launchd/kqueue | Web，Apple Developer | 2026-07-10 | user background manager、NOTE_EXIT/FORK/EXEC；无 cgroup 等价语义 | 写入 ART-01/02/03/04 |
| Python subprocess/os/http.server | Web，docs.python.org | 2026-07-10 | CTRL_BREAK、start_new_session/killpg/pidfd；http.server 仅基本安全检查 | 平台 stop/identity 与本地 HTTP 边界 |
| GitHub hosted runners/matrix | Web，docs.github.com | 2026-07-10 | Windows/Ubuntu/macOS 真实 runner 与 matrix | optional post-commit VAL-12 |
| Python/PowerShell style | Web，PEP/Google/Microsoft | 2026-07-10 | 形成代码、异常、资源清理和静态检查约束 | 写入 ART-02 |

来源矩阵：

| Claim | Source type | URL/path | Official/primary | Accessed | Confidence | Impact |
| --- | --- | --- | --- | --- | --- | --- |
| GitLab keyset/Link/request ID | official | https://docs.gitlab.com/api/rest/ | yes | 2026-07-10 | high | transport/pagination |
| PAT scope/self/DPoP | official | https://docs.gitlab.com/user/profile/personal_access_tokens/ | yes | 2026-07-10 | high | doctor/security |
| current MR/API deprecations | official | https://docs.gitlab.com/api/rest/deprecations/ | yes | 2026-07-10 | high | resource endpoints |
| Job tree/kill-on-close | official | https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects | yes | 2026-07-10 | high | process ownership |
| process creation time | official | https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes | yes | 2026-07-10 | high | identity |
| cgroup hierarchy/kill | official | https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html | yes | 2026-07-10 | high | Linux ownership |
| systemd delegation/control-group kill | official source | https://systemd.io/CGROUP_DELEGATION/ | yes | 2026-07-10 | high | Linux bootstrap/ownership |
| macOS process events/background jobs | official | https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/kqueue.2.html | yes | 2026-07-10 | high | macOS monitor |
| Python signal/session/pidfd | official | https://docs.python.org/3/library/os.html | yes | 2026-07-10 | high | POSIX stop/identity |
| GitHub OS matrix | official | https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job | yes | 2026-07-10 | high | platform validation |
| local race/secret/version findings | local read | `skills/gitlab-pat-ops`, `skills/process-manager` | yes | 2026-07-10 | high | stage scope |

调研结论（Research result）：`passed`。完整证据见 `ART-01`。

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）：`online-required`

技术栈清单：

| Type | Finding | Source | Impact |
| --- | --- | --- | --- |
| Language | Python 3.11+、可选 Windows fixture PowerShell、Markdown/JSON/YAML/JSONL | local inventory | code/test/docs |
| Framework | Python stdlib urllib/http.server/subprocess/ctypes/unittest | local + Python docs | no runtime dependency |
| API/architecture | GitLab REST client；cross-platform loopback control plane + native supervisor adapters | local + official docs | safety/platform boundaries |
| Toolchain | unittest、AST/parser、skill-creator validate、Git、GitHub Actions OS matrix | repository/planner rules | validation evidence |

规范来源矩阵：

| Standard source | Type | Official/primary | Applicability | Accessed | Impact |
| --- | --- | --- | --- | --- | --- |
| 根 `AGENTS.md` | project | yes | 中文注释、最小 scope、错误处理、验证、commit -F | local | all stages |
| PEP 8 | language | yes | Python naming/layout/imports/errors | 2026-07-10 | STG-01-04 |
| Google Python Style Guide | language | primary styleguide | exceptions/threading/types/function length | 2026-07-10 | STG-01-04 |
| Python subprocess/http.server/urllib docs | framework/security | yes | process/HTTP behavior | 2026-07-10 | STG-01/03/04 |
| PowerShell error/PSScriptAnalyzer docs | language/tool | yes | bootstrap/error/cleanup | 2026-07-10 | STG-03/04 |
| GitLab REST/PAT/resource docs | API/security | yes | endpoints/scopes/retry/deprecation | 2026-07-10 | STG-01/02 |
| Microsoft Job/process/mutex/ACL docs | platform/security | yes | ownership/identity/synchronization | 2026-07-10 | STG-03/04 |
| Linux kernel cgroup v2 + systemd delegation docs | platform/security | yes | Linux owner/kill/delegation/fallback | 2026-07-10 | STG-03/04 |
| Apple launchd/kqueue + POSIX/Python docs | platform/security | yes | macOS bootstrap/monitor/group stop | 2026-07-10 | STG-03/04 |
| GitHub Actions runner/matrix docs | validation | yes | three-platform real runner evidence | 2026-07-10 | STG-04/06 |

standards index:

- 路径：`ART-02`，即 `artifacts/standards/standards-index.md`。
- 摘要：定义优先级、Python/API、Windows/Linux/macOS native 规则、采用模式、静态检查和资源预算。
- 未覆盖或 blocked-by-access：无。PSScriptAnalyzer 仅 available-if-present，required gate 使用 PowerShell parser，不伪造工具可用性。

规范发现结论（Standards result）：`passed`。

## 开发质量门禁（Development Quality Gate）

质量范围：

| Dimension | Plan | Stage mapping | Validation mapping |
| --- | --- | --- | --- |
| Code standards | PEP/Google/Python/PowerShell + local Chinese comment rules | STG-01-05 | VAL-07/08/09 |
| Static quality | AST、PowerShell parser、JSON/YAML/JSONL、old-contract scan、line budget | STG-01-06 | VAL-07/08 |
| Architecture boundaries | GitLab transport/policy/resource；process platform/state/runtime/probe/log/client | STG-01-04 | VAL-01/03/09/12 |
| Pattern decision | Adapter、Policy、Registry、Strategy、StateStore、Facade、service-host | STG-01-04 | VAL-01/03/09/12 |
| Low coupling | resource CLI 不复制 transport/guard；consumer 只依赖 public schema | STG-01-05 | VAL-02/05/06/09 |
| High cohesion | production modules 单职责且不超过 500 行 | STG-01-04 | VAL-07/09 |

过度设计防护：

- GitLab 不服务化、不建通用 SDK、不引入 GraphQL/DPoP key management。
- process-manager 不做 auto-restart、remote/GUI orchestration、资源调度、数据库或事件溯源。
- platform adapter 只承载 Windows/Linux/macOS 当前必需 lifecycle，不创建动态 provider/plugin interface。
- 不为兼容旧 schema 保留 parser/branch；doctor 只诊断并要求显式重建。

开发质量结论（Development quality result）：`passed`。模式与 SOLID 只用于移除真实耦合，不以“模式数量”为目标。

## 上下文（Context）

本地代码：

- `skills/gitlab-pat-ops/scripts/gitlab_common.py`：URL、PAT、retry、pagination、output 和 text input 混合。
- `skills/gitlab-pat-ops/scripts/gl_*.py`：已有资源 CLI，可作为拆分基础。
- `skills/gitlab-pat-ops/tests`：29 个 baseline tests。
- `skills/process-manager/scripts/manager_server.py` 与 `pm_common.py`：分别 591/563 行，无锁 state、PID-only 和 taskkill force。
- `skills/process-manager/scripts/start_manager.ps1` / `stop_manager.ps1`：manager.pid + 手工 quote + PID-only force stop。
- `skills/electron-ui-verifier/scripts/ev_init.py`：唯一仓内 process service generator。

本地文档：

- 两个 `SKILL.md` 和 references。
- `evals/gitlab-pat-ops/prompts.jsonl`、`evals/process-manager/fixtures.jsonl`。
- planner/executor Process Manager Gate、README、examples、`.gitignore`、CHANGELOG、`.harness/environment.md`。
- `skill-creator`：SKILL concise、progressive disclosure、agents metadata、quick_validate、forward-test guidance。

外部来源：

- 详见 `ART-01` 与 `ART-02`，全部使用官方/一手技术资料。

用户约束：

- 深入研究、前沿查缺补漏，方案按 current harness 落盘。
- 两个 skill 一起升级；其它 skill 需要适配时直接修改。
- 不考虑旧版兼容，不建 v1/v2。
- process-manager 必须兼容 Windows、Linux、macOS，并在每个平台使用最佳合理原生方案。
- 当前轮是规划，批准后再由 executor 实施。

证据等级：

| Claim | Level | Source | Impact |
| --- | --- | --- | --- |
| GitLab 29 tests pass | confirmed | actual command output | baseline |
| process-manager 无 executable tests | read | repo inventory | REQ-09 |
| cross-origin/write retry/PID/secret risks | confirmed | code read + official semantics | high-risk stages |
| native supervisor/service-host behavior | external + architecture inference | Microsoft/Linux/systemd/Apple/Python docs + ART-03 | required current-OS native smoke + optional user-run matrix |
| no generic GitLab write CAS | external | GitLab API docs | residual risk |

## 候选方案（Options）

### 方案 A：最低共同 POSIX/Windows process-group 补丁

- 做法：保留两个大 common/server，三平台统一使用新 process group/killpg，只加 URL 校验、RLock、身份字段和 tests。
- 优点：平台代码少、交付较快。
- 缺点：放弃 Windows Job 与 Linux cgroup 的强 containment；macOS 限制会被误当三平台共同保证；现有职责耦合仍在。
- 风险：manager crash、并发 fork 和主动脱离时留下进程，且容易出现任意 PID 清理 fallback。
- 验证：可证明基础 signal，不能证明 Windows/Linux 最佳 owner lifecycle。
- 回滚：简单。

### 方案 B：统一契约 + 三平台原生 supervisor 直接切换

- 做法：GitLab 拆 transport/policy/registry/resource；process-manager 拆 platform/state/runtime/probe/log/client，引入 Windows Job、Linux delegated cgroup v2 + group fallback、macOS group guardian + kqueue、blocked service-host、runtime identity 和统一 capability contract。
- 优点：安全不变量集中，三平台均使用最佳可用原语；强弱保证可观察；不增加 Python runtime dependency；符合用户无兼容要求。
- 缺点：改动面和测试矩阵显著扩大，需要外部 Windows/Ubuntu/macOS runner。
- 风险：native adapter、bootstrap 和 owner-death 组合实现错误；用隔离 smoke、三平台 CI、严格 adapter 边界收口。
- 验证：VAL-01 至 VAL-09 为 required；VAL-10 至 VAL-12 为可选，其中 VAL-12 由用户提交后运行。
- 回滚：单最终 commit 可回滚代码；runtime 不迁移。

### 方案 C：完全委托外部服务管理器/第三方库

- 做法：GitLab 使用 python-gitlab；process 在 Windows/Linux/macOS 分别硬依赖 Windows Service、systemd、launchd，或使用 psutil/pywin32/portalocker。
- 优点：部分 API/平台封装更成熟，系统服务可管理 manager 本体。
- 缺点：skill 不再自包含；Linux 容器/非 systemd 环境不可用；系统 unit/agent 安装、权限、版本和 dependency security 增加；外部 manager 仍不能统一 guarded service config。
- 风险：把部署问题引入每次 skill 使用，且不自动解决 guarded write/agent workflow。
- 验证：需要额外依赖矩阵和安装验证。
- 回滚：依赖与 runtime 清理更复杂。

## 决策（Decision）

选择方案（Chosen option）：方案 B。

原因（Why）:

- 两个 skill 都已经跨过“几个脚本即可”的复杂度阈值，核心风险是边界和状态不变量，不是缺少更多 endpoint。
- 用户明确允许 direct cut，正适合一次移除旧 alias/schema/legacy path，而不是再叠兼容层。
- stdlib/ctypes + 原生 OS 设施保持自包含；窄 platform adapter 提供测试 seam，不把 systemd/launchd 变成所有环境硬依赖。

影响（Impact）:

- GitLab JSON envelope、env、部分 script/schema 和 confirm 流程改变。
- process-manager manager/service/runtime schema、统一 bootstrap、内部 dispatcher/identity、port 和 stop/crash 语义改变；公共层不再暴露平台/backend selector 或平台专属 launcher。
- 仓库新增 Windows/Ubuntu/macOS CI workflow；用户提交后可运行并取得全平台证据，在此之前不作对应完成结论。
- electron/planner/executor/docs/evals/examples 必须同一任务切换。

可逆性（Reversibility）:

- 代码由最终一次 commit 统一回滚。
- ignored runtime 不做向前/向后迁移；回滚前用户需停止 manager 并选择匹配代码的隔离 stateRoot。

变更条件（Change conditions）:

- 只有 required validation 证明某平台 approved native backend/自动 fallback 不可行时，才允许通过 amendment 替换内部 ownership 或选择机制；公共统一 contract 不随内部替换而分叉。
- 不因可选 live smoke 不可用改变 required scope。

方案变更触发条件（Reapproval triggers）:

- 新增高影响 GitLab 写能力、后台服务、GraphQL/DPoP key management。
- 改变同源/写 retry/fingerprint、平台支持范围/自动 backend 选择规则、统一公共 contract、owner-death cleanup/full run identity 或 current env/schema。
- 引入第三方 runtime dependency、超出 approved CI-only transient unit 的提权、自动持久系统配置或未列明真实外部写。
- 修改 Stage DAG、required validation、批准 artifacts 或 commit policy。

## 影响面矩阵（Impact Matrix）

| Surface | Involved | Files/modules | Risk | Validation | Docs |
| --- | --- | --- | --- | --- | --- |
| API | yes | GitLab REST client；local manager control API | high | VAL-01/03/04/09 | both references |
| Data model | yes | capability registry、GitLab envelope、manager/service/process state | high | VAL-01/03/07 | schema guide |
| Frontend interaction | no | none | low | none | none |
| Config/environment | yes | SKILL_GITLAB_*、manager/service JSON、runtime identity | high | VAL-01/03/04/06 | README/templates |
| Compatibility | yes | direct cut，old contract rejected | high but intentional | VAL-02/05/06/07 | explicit breaking behavior |
| Tests | yes | both tests、executable evals、three-platform CI | high | VAL-01-08/12 | eval/CI README |
| Documentation | yes | skills/references/README/examples/changelog | medium | VAL-06/07/08/09 | required |
| Code standards | yes | Python/native adapters/optional fixture PowerShell/JSON | medium | VAL-07/08/09/12 | ART-02 |
| Architecture/design | yes | package boundaries、platform supervisor/service-host、policy registry | high | VAL-01/03/04/09/12 | ART-03 |

## 实施计划（Implementation Plan）

阶段依赖、引用、授权和验证以 `plan-contract.json` 为机器真相源；本节解释实施理由、具体文件和失败收口。每阶段开始前重读 `ART-02`、`ART-03` 和该阶段 Stage Contract。

### STG-01：GitLab 安全传输与能力契约

目标（Goal）:

- 完成 REQ-01/REQ-02，先建立后续所有 GitLab resource command 共享的安全底座。
- 让 AC-01/AC-02 和 NFR-01/NFR-02/NFR-03/NFR-04/NFR-05/NFR-06 可由 adversarial tests 证明。

做法（How）:

1. 建立 `scripts/gitlab_ops/` package，拆出 config/errors/transport/pagination/output/safety/registry/text_input。
2. 删除旧 `gitlab_common.py`，所有 entry script 改用 package API；不保留 import shim。
3. 配置只接受 `SKILL_GITLAB_BASE_URL` 与 `SKILL_GITLAB_PAT`；增加 optional CA bundle、HTTP opt-in、test project；删除 `SKILL_GITLAB_TOKEN`。
4. 严格 normalize base/API root；redirect/Link 在构造 PAT request 前做同源和 API prefix 验证。
5. 建 GET/HEAD-only RetryPolicy，采集 Retry-After/rate-limit/request ID；写 method attempt 固定为 1。
6. 增加 response/page/item/byte budget、pagination loop 检测、可用 endpoint 的 keyset 支持和 binary-safe output primitive。
7. 定义稳定 success/error envelope、error code、exit code 和 write outcome。
8. 建单一 capability registry；`gl_capabilities.py` 支持精确过滤和 JSON/Markdown 输出，不含 skill version。
9. doctor 组合 offline config、metadata、PAT self 和 user，输出 scope/expiry/edition/request ID 的脱敏摘要。
10. 先写 fake opener/local HTTP adversarial tests，再迁移既有 entry scripts，避免安全逻辑只有 happy path。

原因（Why）:

- 当前最高风险是 PAT 跨源和非幂等写重放；继续先加 endpoint 会扩大受影响面。
- capability SSoT 必须先存在，STG-02 才能在新增每个资源时自动检查安全声明。

位置（Where）:

- 文件/模块：`skills/gitlab-pat-ops/scripts/**`、`tests/**`、`references/**`、`SKILL.md`。
- API/配置：GitLab `/api/v4`、`/metadata`、`/personal_access_tokens/self`、`/user`；current SKILL_GITLAB_*。
- 测试/文档：transport/config/registry/doctor tests；核心 security/workflow 文案。

参考来源（References）:

- GitLab REST/PAT/rate-limit/metadata 文档，见 ART-01。
- Python urllib、PEP/Google style，见 ART-02。

适用规范（Standards applied）:

- PAT 不进入 query/argv/error/log；同源验证先于 header 构造。
- HTTP default secure、write no retry、I/O 有界、closed registry/envelope。
- Adapter + Policy + Registry；entry script 保持薄层。

开发质量检查（Development quality checks）:

- transport/safety/resource 零循环依赖；无第二个 retry/redaction/preview 实现。
- 生产模块不超过 500 行；异常不回显 response secret/traceback。
- capability registry 与 script/subcommand/endpoint/scope/safety 一致。

验证（Validation）:

- VAL-01：GitLab unittest，包括 two-server PAT exfiltration、redirect、write retry、budget。
- VAL-02：capability/eval runner 的基础 fixture。
- VAL-07：AST/schema/old alias/version scan。
- VAL-08：skill-creator validation。

风险和回滚（Risks and rollback）:

- 风险：统一 envelope 会让旧 tests/scripts 全部同时失败。先迁移 shared tests，再逐 entry script 收口。
- 回滚：阶段未提交；可在批准 scope 内修复，不建立旧 common shim。无法保持 current contract 时触发 amendment。

阶段契约（Stage Contract）:

- 依赖（Depends on）：无。
- 需求/验收：REQ-01、REQ-02；AC-01、AC-02；NFR-01、NFR-02、NFR-03、NFR-04、NFR-05、NFR-06。
- 范围（Scope）：GitLab transport、config、doctor、registry 与其 tests/docs。
- 允许修改（Allowed changes）：`skills/gitlab-pat-ops/scripts/**`；`skills/gitlab-pat-ops/tests/**`；`skills/gitlab-pat-ops/references/**`；`skills/gitlab-pat-ops/SKILL.md`；`evals/gitlab-pat-ops/**`；`evals/process-manager/run_static_checks.py`。
- 禁止修改（Forbidden changes）：`skills/process-manager/**`；`真实 GitLab 写请求`；`旧 token alias 或版本化 skill 目录`；`未列入 contract 的第三方依赖`。
- 进入条件（Entry checks）：基线 29 个 GitLab 单元测试已记录；ART-01 至 ART-03 的传输与能力决策已重读；不读取或输出 PAT 值。
- 退出条件（Exit checks）：同源、TLS、重定向、重试、限流、响应上限和请求 ID 测试通过；doctor 与单一能力注册表生效；旧 env alias 和版本标签已删除。
- 必需验证（Required validation）：VAL-01、VAL-02、VAL-07、VAL-08。
- 是否预期提交（Commit expected）：none。

### STG-02：GitLab 模块化资源与受控写入

目标（Goal）:

- 完成 REQ-03/REQ-04/REQ-05，使 AC-03/AC-04/AC-05/AC-06 可组合、可验证。
- 在不扩大高影响写边界的前提下补足 issue/MR review 和协作上下文。

做法（How）:

1. 保留并迁移 projects/search/repo/labels/milestones/members/branches/issues/MRs/notes。
2. 新增 namespaces、commits、templates、discussions、resource events、MR diffs、pipelines/jobs、approvals 资源脚本。
3. 使用 Project Templates API 同时支持 issue/MR template，删除 `gl_issue_templates.py`。
4. MR diff 使用 list diffs，不调用 deprecated single changes；字段使用 detailed_merge_status/merge_user/approval state。
5. 扩展 issue/MR list filter；将 description-only update 替换为通用 metadata update，并对 mutually exclusive/empty/unassign 行为做显式 parser。
6. 建 `WriteIntent`/`WriteGuard`：project/resource preflight、canonical payload、fingerprint、exact confirm、drift check、single attempt、read-after-unknown guidance。
7. project create、issue/MR create/state、top-level note 全部迁移到同一 guard；新增 discussion reply 和 MR thread resolve/reopen。
8. 自动 live smoke 必须读取 `SKILL_GITLAB_TEST_PROJECT` 并匹配 numeric/full path；普通真实写仍需用户当前明确授权。
9. registry 标记所有 forbidden capability，CLI 对尝试调用返回 stable unsupported error。
10. 为每个 resource 建 table-driven command tests，为 guard 建 fingerprint/drift/no-retry tests；建立 executable eval manifest/runner。
11. 重写 SKILL 为核心工作流 + 条件 references，`gl_capabilities` 仍只在能力不确定时运行。

原因（Why）:

- 资源模块比一次性“处理 issue”脚本更易组合；新增能力直接服务定位、理解、实现、review GitLab 工作项。
- 集中 guard 才能确保每个写入口都遵循相同安全语义。

位置（Where）:

- 文件/模块：`skills/gitlab-pat-ops/**`、`evals/gitlab-pat-ops/**`。
- API/配置：namespaces/templates/commits/MR diffs/pipelines/jobs/approvals/discussions/resource events/issues/MRs/notes/projects。
- 测试/文档：resource tests、write safety tests、eval runner、SKILL/references/agents。

参考来源（References）:

- Issues、Merge Requests、Discussions、Notes、Project Templates、Pipelines、Jobs、Commits、Approvals、REST deprecations，见 ART-01。

适用规范（Standards applied）:

- resource script 单一职责；registry 是唯一 machine-readable capability truth。
- 写入必须 preview/apply 绑定；write no retry；404 不武断区分不存在/无权限。
- 不把 DPoP、Work Item GraphQL 或 token rotation 混入 current scope。

开发质量检查（Development quality checks）:

- 不出现同 endpoint 在多个 scripts 重复拼接；公共 IID/ID/date/text parser 统一。
- 每个写能力有 preflight/fingerprint/confirm/unknown-outcome tests。
- 输出 body/raw/notes/diffs/jobs 均遵循 byte/item budget。

验证（Validation）:

- VAL-01、VAL-02、VAL-07、VAL-08 为 required。
- VAL-10 是可选 live read；VAL-11 是需另行 external_write 授权的可选 test-project write，不影响阶段完成。

风险和回滚（Risks and rollback）:

- 风险：GitLab tier/instance 差异。doctor/registry 输出 tier notes，403/404 保留 ambiguity，不做 silent fallback。
- 风险：fingerprint 不是 CAS。apply 前后 read 减少明显漂移，残余竞态明确报告。
- 回滚：阶段未提交；删除不完整新资源而不是恢复 deprecated endpoint/old guard。

阶段契约（Stage Contract）:

- 依赖（Depends on）：STG-01。
- 需求/验收：REQ-03、REQ-04、REQ-05；AC-03、AC-04、AC-05、AC-06；NFR-01、NFR-02、NFR-03、NFR-04、NFR-05、NFR-06。
- 范围（Scope）：全部 GitLab resource CLI、guarded writes、tests/evals/docs。
- 允许修改（Allowed changes）：`skills/gitlab-pat-ops/**`；`evals/gitlab-pat-ops/**`。
- 禁止修改（Forbidden changes）：`GitLab delete/merge/approve/token/permission/CI mutation/branch mutation/bulk write`；`GitLab 后台服务`；`旧 CLI fallback`；`生产项目 live smoke`。
- 进入条件（Entry checks）：STG-01 完成；官方 endpoint、scope 和弃用项映射已确认；写入预览指纹与 preflight 规则已冻结。
- 退出条件（Exit checks）：新增资源命令可独立组合且能力注册表覆盖；所有受控写入使用同一 preview/confirm primitive；离线测试和 eval 通过且不产生外部写入。
- 必需验证（Required validation）：VAL-01、VAL-02、VAL-07、VAL-08；VAL-10、VAL-11 为 optional。
- 是否预期提交（Commit expected）：none。

### STG-03：跨平台进程所有权、身份与状态核心

目标（Goal）:

- 完成 REQ-06/REQ-07，建立 AC-07/AC-08/AC-09 和 NFR-01 至 NFR-07 的底层不变量。
- 在进入 readiness/log/CLI 扩展前，先冻结平台透明公共契约与内部 supervisor dispatcher，并证明 Windows/Linux/macOS 的公共行为一致、owner/run identity/权限/状态安全。

做法（How）:

1. 新建 `scripts/process_manager/` package，拆 config/errors/models/state/runtime/service_host/control_api/client 与 `platforms/base/dispatcher/windows/linux/macos/posix`。
2. 删除大 `pm_common.py`；将 manager_server 缩成 composition/serve；不保留 old imports。
3. 定义 closed manager/service/process models；manager config 只含 workspace/state/control/history/log 等平台无关字段，control port 为 0，runtime path 全由 stateRoot 派生，拒绝 platform/backend/supervision/minimum-guarantee 字段。
4. `manager.json` 取代 manager.pid，在内部保存 instanceId/platform/bootstrapBackend/supervisorBackend/capability/identity/actual endpoint；config 不再被端口选择修改，普通 client response 不把内部平台字段变成公共 contract。
5. 内部 supervisor dispatcher 只包含 detect、select、manager lock、identity、create/attach、graceful/force、verify-empty、close；调用方不能选择 adapter。未知 OS、无安全 backend 或 identity 不可验证时 fail closed。
6. Windows adapter 封装 process identity、named mutex、Job Object/kill-on-close/ACL；每 run blocked host 先入 Job，再释放 target。
7. Linux adapter 只在 systemd `Delegate=` subtree 建 per-run cgroup，blocked host 入 cgroup 后启动 target；支持 `cgroup.kill`/populated verification/pidfd，未委托时由 dispatcher 自动切 POSIX group fallback。
8. macOS adapter 建独立 session/process group、manager-liveness guardian 和 kqueue/waitpid monitor；launchd 仅为优先 bootstrap，不声称 cgroup 等价。
9. POSIX adapter 使用 flock 与 owner-only mode；所有 backend 将 platform/backend/capability/selectionReason 写入 atomic internal identity，只由 doctor/失败诊断按需脱敏读取。
10. StateStore 用 RLock + atomic replace + backup/rebuild；start/stop/prune 线性化，所有 record path 重新验证，PID 永不单独成为 action authority。
11. environment 改为 inherit/set/fromEnv；secret-like literal 被拒绝；state/API 只保存 names/hash/summary；DACL/mode/owner 失败阻断。
12. control API 使用 loopback/client-address、constant-time bearer、body limit、脱敏 errors 和 authenticated shutdown。
13. 加公共 CLI/schema/envelope parity、internal dispatch/diagnostic truth、PID reuse/run capability、manager lock、concurrent state、path/permission、secret、corrupt recovery 和 adapter fake tests。

原因（Why）:

- 最低共同 process-group 无法提供 Windows/Linux 最强 ownership；把 OS 分支散落在 runtime 或公共 API 又会放大耦合，因此只有内部 dispatcher 可选择 backend。
- service-host handshake 统一消除 Job/cgroup assignment race，并在 process-group 模式提供 manager-death guardian；窄 adapter 不需要第三方 process library。

位置（Where）:

- 文件/模块：`skills/process-manager/scripts/**`、`tests/**`、`templates/**`。
- API/配置：平台无关 current manager/service JSON 与 response envelope；内部 manager.json、processes/run records、platform capability；loopback control API。
- 测试/文档：platform adapter fake/component tests 和隔离 identity fixtures。

参考来源（References）:

- Microsoft Job/process/mutex/ACL；Linux cgroup v2/systemd delegation；Apple kqueue/launchd；Python subprocess/os/http.server，见 ART-01/02。

适用规范（Standards applied）:

- 每个 native handle/fd/cgroup 单 owner；identity-before-signal；Job/cgroup/guardian 先于 target；fail closed。
- StateStore 封装同步/atomic/rebuild；API 不回显未知 exception。
- Python stdlib/ctypes + OS 原生设施；无 legacy/Windows-only branch truth。

开发质量检查（Development quality checks）:

- Windows/Linux/macOS native calls 只存在各自 adapter；common runtime 不直接 ctypes、写 cgroup 或判断 sys.platform。
- state lock 不跨网络/readiness 长等待；service reservation 消除 check-then-act。
- secret 不进入 process.json/processes.json/API/error/log test fixture。
- process-group fallback 始终在内部 identity 带真实 selection reason；普通 API 不泄漏平台分支，doctor/失败诊断不得把其伪装为 kernel-tree。

验证（Validation）:

- VAL-03：unit/component tests。
- VAL-04：当前平台 manager identity、native owner、crash、PID/capability safety smoke 的核心子集。
- VAL-07：static/schema/old manager.pid/portRetry/taskkill scan。
- VAL-08：skill structural validation。

风险和回滚（Risks and rollback）:

- 风险：父 Job/安全软件、systemd delegation、launchd domain 或 filesystem permission 不满足。内部 dispatcher 自动选择契约内安全 fallback，doctor 按需记录原因；不能退回任意 PID kill，也不能要求调用方选择另一套接口。
- 风险：Linux/macOS 本机不可用。STG-03 先完成 deterministic adapter tests，真实平台闭环由用户提交后运行 VAL-12 补充；未获得 evidence 不阻断本地完成态，但必须保留“Linux/macOS hosted runner 未验证”的残余风险。
- 回滚：只在隔离 tmp 使用新 runtime；不触碰用户现有 ignored manager runtime。

阶段契约（Stage Contract）:

- 依赖（Depends on）：无。
- 需求/验收：REQ-06、REQ-07；AC-07、AC-08、AC-09；NFR-01、NFR-02、NFR-03、NFR-04、NFR-05、NFR-06、NFR-07。
- 范围（Scope）：process-manager current config/state/platform supervisors/runtime/control core 与 tests。
- 允许修改（Allowed changes）：`skills/process-manager/scripts/**`；`skills/process-manager/tests/**`；`skills/process-manager/templates/**`；`evals/process-manager/run_static_checks.py`。
- 禁止修改（Forbidden changes）：`任意 PID 强杀 fallback`；`未委托 cgroup 写、自动 sudo、enable-linger 或全局 service install`；`旧 manager.pid/portRetry schema`；`第三方进程管理依赖`；`公共 platform/backend selector 或平台专属入口`；`不可审计的内部降级`。
- 进入条件（Entry checks）：ART-03 的 platform backend/service-host/control plane 决策已重读；使用隔离临时 workspace；测试 process 由本轮夹具创建并记录 run identity。
- 退出条件（Exit checks）：platform lock 和 runtime identity 生效；Windows Job/Linux cgroup+fallback/macOS guardian adapter contract tests 通过；三平台公共 CLI/schema/envelope parity、自动选择/失败诊断、并发状态和损坏恢复通过；状态与响应不含秘密。
- 必需验证（Required validation）：VAL-03、VAL-04、VAL-07、VAL-08。
- 是否预期提交（Commit expected）：none。

### STG-04：进程生命周期、探针、日志与 CLI

目标（Goal）:

- 完成 REQ-08/REQ-09，使 AC-10/AC-11 与全部相关 NFR 在真实 Windows/Linux/macOS lifecycle 下闭环。
- 把当前只有 prompt fixture 的 Windows-only skill 变成有 portable unit、native smoke、三平台 CI 和 executable eval 的可靠工具。

做法（How）:

1. service-host 使用独立 process group 启动前台 target，保存 host/target/run capability 和真实 exit code；Windows 不使用会阻断 console control 的启动方式。
2. 公共 service 只配置 `graceSeconds`，stop 意图固定为 graceful-then-force；内部 Windows 映射 CTRL_BREAK->Job，Linux strict 映射 SIGTERM->cgroup.kill，POSIX 映射 SIGTERM->SIGKILL group；内部记录 backend/capability，公共结果只返回统一 grace/force/owner-empty 字段。
3. restart 只有旧 run 确定终止后才 start；stop_timeout/identity mismatch 直接失败，不返回 misleading success。
4. probe strategy 支持 HTTP/TCP/log/process；HTTP/TCP 只允许 loopback，HTTP redirect 受限；log 使用 cursor/scanBytes/pattern/extract budget。
5. stdout/stderr 由 manager pump，进行 known-secret exact redaction 后写有 maxBytes/backups 的 run 日志；tail 从末端有界读取并跨 backups 保序。
6. completion watcher 更新 exitCode/exitedAt，使用 processKey/attempt 防止旧 watcher 覆盖新 run。
7. `pm_init/health/validate/start/ready/status/logs/list/prune/stop/restart/doctor/shutdown` 在三平台使用同一 client/error/envelope；普通 health/status 不要求处理 platform/backend 字段，只有显式 doctor 或失败 diagnostics 展示脱敏的 capability/selectionReason。
8. 新增唯一 `pm_manager.py start|stop|status`：内部自动选择 Windows detached + named mutex、Linux systemd user delegated bootstrap 或 POSIX fallback、macOS workspace-scoped launchd 或 POSIX fallback；CLI 无平台/backend 参数，不得自动 sudo/linger/全局安装。
9. 重写 templates：公共 launcher 仅为通用 `direct` 与 `script`，统一使用 executable/interpreter/script/args/pathArgs/environment/stop/logs；cmd/pwsh/bash/zsh 只是绝对 interpreter 数据，不生成平台专属类型。
10. 新增 `references/service-schema.md`、`platform-backends.md`、`security.md` 和 agents/openai.yaml；SKILL 保留统一核心顺序，平台详情仅作为失败排查的 progressive disclosure。
11. 建统一 `run_platform_smoke.py` 与平台 fixtures：先断言 CLI help/schema/envelope/error-code parity，再覆盖 normal/ignore signal、child/grandchild、manager crash、dynamic port、large logs、start failure、secret propagation、daemonize contract violation 和内部自动 fallback。
12. 新增 `.github/workflows/process-manager-platforms.yml`，覆盖 windows-latest/ubuntu-latest/macos-latest，执行 unit/native smoke/eval/static 并上传 cleanup evidence。
13. 建 eval manifest/expected/runner，替换 prompt-only 通过标准；验证 agent 正常任务不先运行 doctor、不判断 OS/backend；examples 只提供平台无关 current schema。

原因（Why）:

- native supervisor 解决“能否按平台最强能力清理”，本阶段解决“如何以完全相同的公共方法表达意图，并在内部自动映射、诚实诊断且有界地清理”。
- agent 只使用短、确定且平台无关的 pm command；正常任务不读取平台详情，只有统一调用失败且原因不清楚时才运行 doctor，绝不直接操作 Job/cgroup/launchctl。

位置（Where）:

- 文件/模块：`skills/process-manager/**`、`evals/process-manager/**`、`examples/process-manager/**`、`.github/workflows/process-manager-platforms.yml`。
- API/配置：service launcher/environment/stop/readiness/logs；manager lifecycle endpoints。
- 测试/文档：unit、三平台 native smoke/CI、eval、templates、SKILL/references/agents/examples。

参考来源（References）:

- Python subprocess/os、Microsoft Job/console、Linux cgroup/systemd、Apple kqueue/launchd 与 GitHub runner docs，见 ART-01/02。

适用规范（Standards applied）:

- graceful 与 force 分阶段；identity/owner mismatch 绝不清理；无安全 owner 绝不 spawn。
- log/probe/history/body 全部有硬预算；未知错误脱敏。
- 公共 launcher 仅 direct/script，Strategy 只用于 probe 与内部 stop mapping；不允许 plugin/free shell 或平台专属公共类型。

开发质量检查（Development quality checks）:

- runtime/probe/log/client/CLI 不重复 state/path/identity 逻辑。
- watcher/pipe/log thread 都有 owner、shutdown 和 bounded join。
- exact secret redaction 仅 defense-in-depth，docs 不宣称完整 DLP。
- CI workflow 不使用 secret、不提权清理未知对象；每个平台 finally 输出 owner-empty audit。

验证（Validation）:

- VAL-03：unit/component/full lifecycle tests。
- VAL-04：当前 OS 隔离 native smoke，含 normal/force/crash/owner cleanup。
- VAL-05：process-manager executable eval。
- VAL-07、VAL-08：static/schema/skill validation。
- VAL-12（可选、用户侧后置）：Windows/Ubuntu/macOS matrix 与 per-run evidence。

风险和回滚（Risks and rollback）:

- 风险：Windows console、Linux delegation、macOS launchd 在具体 runner 不可用。内部 dispatcher 自动使用 approved fallback 并准确记录 capability；不得把 fallback 写成 strict pass，也不得把选择责任推给调用方。
- 风险：log pump backpressure。用并行 reader、bounded rotation 和 stress fixture 验证，不把 PIPE 丢给无人读取。
- 回滚：保留 STG-03 ownership core，修复本阶段策略；若必须放弃 approved platform backend/service-host、自动选择规则或统一公共 contract 则 amendment。

阶段契约（Stage Contract）:

- 依赖（Depends on）：STG-03。
- 需求/验收：REQ-08、REQ-09；AC-10、AC-11；NFR-01、NFR-02、NFR-03、NFR-04、NFR-05、NFR-06、NFR-07。
- 范围（Scope）：process lifecycle/probes/logs/CLI/bootstrap/docs/evals/examples。
- 允许修改（Allowed changes）：`skills/process-manager/**`；`evals/process-manager/**`；`examples/process-manager/**`；`.github/workflows/process-manager-platforms.yml`。
- 禁止修改（Forbidden changes）：`自动重启循环`；`自由 shell command`；`无界日志/readiness/history`；`秘密 argv 持久化`；`旧 service schema 兼容解析`；`多平台公共入口/schema 分叉`；`要求调用方先运行 doctor 或选择 backend`。
- 进入条件（Entry checks）：STG-03 完成；platform supervisor/runtime registry 可用；所有生命周期测试有 finally、run capability 和 owner-empty 校验。
- 退出条件（Exit checks）：当前平台 graceful-force owner 回收、增量 readiness、轮转日志、退出码和 restart 语义通过；三平台 workflow 已定义并可运行；CLI help/schema/envelope/error parity、自动 backend 选择、按需 doctor、eval/references/agent metadata 与实现一致。
- 必需验证（Required validation）：VAL-03、VAL-04、VAL-05、VAL-07、VAL-08；三平台汇总 VAL-12 由用户提交后运行，不阻断本地阶段完成。
- 是否预期提交（Commit expected）：none。

### STG-05：仓内消费者直接切换

目标（Goal）:

- 完成 REQ-10/AC-12，让整个仓库只消费 current GitLab/process-manager contract。
- 只做契约适配，不借机修改 planner/executor 或 electron verifier 的无关业务。

做法（How）:

1. `electron-ui-verifier/ev_init.py` 只生成平台无关的 current direct/script service：executable/interpreter/script/args/pathArgs、environment、stop、logs、log readiness。
2. 更新 electron server/workflow/troubleshooting 中统一 bootstrap、manager identity、health、ready/log/stop/owner cleanup 证据；平台细节仅在失败排查时引用 doctor。
3. planner Process Manager Gate 增加统一 manager identity、bounded logs、stop result、owner cleanup evidence；finite command 规则不变，不要求读取 platform/backend/capability。
4. executor workflow 同步统一 `pm_manager.py` bootstrap、validator/identity/cleanup；正常流程不判断 OS/backend，manager unavailable 且长期进程必需时仍 blocked。
5. 更新 complex planner/executor eval fixtures/expected，拒绝 manager.pid/portRetry/old service schema、PowerShell-only bootstrap、手写 POSIX background 和 arbitrary PID cleanup。
6. README 删除 GitLab token alias和固定 manager 端口文案，描述 current capability/safety boundary。
7. `.gitignore` 以 manager.json 为 current runtime identity；移除 manager.pid current contract 项。
8. examples 只提供统一 current schema；`.harness/environment.md` 更新稳定命令、自动跨平台适配、按需诊断和不兼容边界，不修改历史任务记录。
9. CHANGELOG 增加一次 current direct-cut 条目，不使用 v2。
10. 建 cross-skill runner，实际调用 electron service builder/current validator 及 planner/executor relevant tests/evals。

原因（Why）:

- 同一仓库保留旧 consumer 会让 direct cut 在真实任务中失效，并产生两套看似合法的配置。
- planner/executor 是 process-manager 的强制调用者，必须验证真实 cleanup 证据，但不能固化或分支处理内部平台实现。

位置（Where）:

- 文件/模块：electron-ui-verifier、complex-coding-planner、complex-coding-executor 相关 contract 文件与 eval；README、examples、ignore、environment、changelog。
- API/配置：只涉及 process-manager consumer schema/evidence 和 GitLab current env 文案。
- 测试/文档：cross-skill runner 和既有测试/eval。

参考来源（References）:

- ART-03 的“跨 skill 直接切换”和 ART-06 file ownership map。

适用规范（Standards applied）:

- 只修改调用 current contract 所需位置；不创建兼容 adapter。
- skill-creator progressive disclosure，README 只保留仓级摘要。
- historical task bundle immutable。

开发质量检查（Development quality checks）:

- 逐项 git grep old alias/schema/port/manager.pid；每个命中分类为 historical 或必须删除。
- electron service fixture 经 current validator，而非只比较字符串。
- planner/executor core lifecycle/ledger/approval tests 无无关变化。

验证（Validation）:

- VAL-05：process eval 包含 agent workflow。
- VAL-06：cross-skill regression runner。
- VAL-07：old-contract/static/schema scan。
- VAL-08：两个目标 skill quick_validate。

风险和回滚（Risks and rollback）:

- 风险：全局搜索会命中历史 task/changelog；历史 task 不修改，scanner 使用 current-source allowlist。
- 回滚：在 current consumer 文件内修正；不恢复旧 env/schema fallback。

阶段契约（Stage Contract）:

- 依赖（Depends on）：STG-02、STG-04。
- 需求/验收：REQ-10；AC-12；NFR-04、NFR-05、NFR-06、NFR-07。
- 范围（Scope）：仓内 current consumers、repository docs/config/evals。
- 允许修改（Allowed changes）：`skills/electron-ui-verifier/**`；`skills/complex-coding-planner/**`；`skills/complex-coding-executor/**`；`evals/complex-coding-planner/**`；`evals/complex-coding-executor/**`；`README.md`；`examples/process-manager/**`；`.gitignore`；`.harness/environment.md`；`CHANGELOG.md`。
- 禁止修改（Forbidden changes）：`历史 task bundle 内容`；`skill 目录重命名`；`无关 skill 行为`；`v1/v2 并行文档`；`consumer OS/backend 条件分支`；`每次任务强制 doctor`。
- 进入条件（Entry checks）：STG-02 与 STG-04 完成；新 GitLab 与 process-manager 公共契约已冻结；跨 skill 调用清单已重读。
- 退出条件（Exit checks）：electron-ui-verifier 生成统一 service schema；planner/executor 使用平台无关 process-manager 证据门禁且无 OS/backend 分支；README/示例/ignore/eval/changelog 不再引用旧契约或平台专属公共接口。
- 必需验证（Required validation）：VAL-05、VAL-06、VAL-07、VAL-08。
- 是否预期提交（Commit expected）：none。

### STG-06：全量验证、代码审查与最终收口

目标（Goal）:

- 对 REQ-01 至 REQ-10、AC-01 至 AC-12、NFR-01 至 NFR-07 做全量闭环。
- 在获得 commit 授权时创建一次最终 `git commit -F`；不以提交代替验证。

做法（How）:

1. 在 isolated task tmp 依次执行 VAL-01 至 VAL-08，输出到 contract evidence paths。
2. 运行 VAL-09：按 ART-04 checklist 审查安全、并发、identity、state、resource budget、cross-skill、docs/eval 和 changed-file scope。
3. 只 stage 批准文件，检查 staged scope、`git diff --cached --check` 和 staged tree；不创建或推送远端临时 ref。
4. 用户在本地最终提交后自行 push 并检查 Windows/Ubuntu/macOS Actions；执行器不触发 Actions、不读取远端结果，也不执行 Ubuntu scoped elevated 操作。
5. VAL-12 作为可选后置证据，本次记录为 deferred，不标记 passed；最终审查明确 Linux/macOS hosted runner 尚未验证，后续 CI 失败由用户反馈后另行修复。
6. VAL-10 在用户现有 GitLab env 可用时执行 read-only doctor/search/get；失败只记录 external residual，不覆盖 offline tests。
7. VAL-11 默认不执行；GitHub CI external-write 授权不包含 GitLab 写入，只有独立 test-project write 授权和 exact match 才执行。
8. 重跑所有修复影响的 validation；任何 failed evidence 会撤销旧 pass，直到新 evidence 完整。
9. 验证没有 manager/service/child、Job/cgroup/process-group owner、token、tmp secret、production write 或未知 file 变更残留。
10. `git diff --check`、status、diff/stat、scope review；通过后保持相同 staged tree。
11. final commit 获授权后写 task tmp commit message，使用 `git commit -F`，标题/重点符合根 AGENTS.md 且文件末尾不产生多余空行。

原因（Why）:

- 两个 high-risk skill 以及跨 skill direct cut 必须通过同一最终门禁，不能以阶段局部测试代替系统验证。

位置（Where）:

- 文件/模块：全部批准目标文件；current task runtime evidence/tmp。
- API/配置：不新增能力或 schema。
- 测试/文档：全部本地 required validation、final review，以及可选 GitLab smoke 和用户侧三平台 CI。

参考来源（References）:

- ART-04 validation strategy、ART-05 critique、ART-06 traceability。

适用规范（Standards applied）:

- failed validation 必须修复并重跑；optional 不伪装为 required passed。
- Git commands 串行；不 reset/stash/revert 用户变更；commit 只在授权后使用 -F。

开发质量检查（Development quality checks）:

- final review 明确 Development Quality `passed`，并逐项关闭 finding。
- diff 不含 old alias/schema/version、secret/runtime、unrelated refactor。
- required evidence paths 真实存在且引用覆盖完整。

验证（Validation）:

- Required：VAL-01、VAL-02、VAL-03、VAL-04、VAL-05、VAL-06、VAL-07、VAL-08、VAL-09。
- Optional：VAL-10、VAL-11、VAL-12；未执行时记录原因和残余风险。

风险和回滚（Risks and rollback）:

- 风险：native smoke 留下 process。只操作 run/backend identity + test instance；cleanup 失败即阻断，不推送候选或提交。
- 风险：用户侧 CI 尚未运行。保留 staged tree 与最终 commit SHA，并明确不宣称 Linux/macOS hosted runner 通过；CI 失败后基于该 commit 定位和修复。
- 风险：online read 暂不可用。保留 offline required tests，不降低 transport confidence 的声明范围。
- 回滚：提交前在批准 scope 内修复；提交后以正常 revert commit 回滚，不 reset hard。

阶段契约（Stage Contract）:

- 依赖（Depends on）：STG-05。
- 需求/验收：REQ-01、REQ-02、REQ-03、REQ-04、REQ-05、REQ-06、REQ-07、REQ-08、REQ-09、REQ-10；AC-01、AC-02、AC-03、AC-04、AC-05、AC-06、AC-07、AC-08、AC-09、AC-10、AC-11、AC-12；NFR-01、NFR-02、NFR-03、NFR-04、NFR-05、NFR-06、NFR-07。
- 范围（Scope）：全量验证、final review、证据、授权提交。
- 允许修改（Allowed changes）：`本 contract 已批准的所有目标文件`；`.harness/tasks/2026-07-10/feature/gitlab-process-manager-capability-upgrade/artifacts/**`；`.harness/tasks/2026-07-10/feature/gitlab-process-manager-capability-upgrade/tmp/**`。
- 禁止修改（Forbidden changes）：`新增未批准能力面`；`真实生产 GitLab 写入`；`未授权提交`；`跳过失败验证`；`修改已批准 plan/contract/artifact`。
- 进入条件（Entry checks）：STG-05 完成；所有 required validation 可运行；worktree 变更仅位于批准范围。
- 退出条件（Exit checks）：所有本地 required validation 和 development quality review 通过；staged scope/tree 与审查对象一致；VAL-11、VAL-12 未执行时明确记录残余风险；无后台进程或临时秘密残留；获得提交授权时使用 git commit -F 完成最终一次提交。
- 必需验证（Required validation）：VAL-01、VAL-02、VAL-03、VAL-04、VAL-05、VAL-06、VAL-07、VAL-08、VAL-09；VAL-10、VAL-11、VAL-12 为 optional。
- 是否预期提交（Commit expected）：final。

## 环境（Environment）

Workspace 环境来源：

- `.harness/environment.md`
- 当前 workspace：`D:\Item\vibe_coding\dev-skills`
- 当前本地平台：Windows，PowerShell，Python 可用；Linux/macOS 只通过外部真实 runner 验证。

本任务使用：

- Python 3.11+ stdlib、ctypes、unittest；公共 process-manager bootstrap 使用 Python。
- Windows Job/console/mutex/DACL、Linux cgroup v2/systemd/POSIX、macOS launchd/kqueue/POSIX 原生设施。
- GitHub Actions Windows/Ubuntu/macOS hosted runner，仅用于用户 push 后的无 secret lifecycle matrix，不由本次执行器触发。
- GitLab API 仅 required research 和 optional live read；required implementation tests 使用 fake local HTTP。
- task runtime：`.harness/tasks/2026-07-10/feature/gitlab-process-manager-capability-upgrade/tmp/`，只由 executor 在批准后创建。

临时覆盖：

- process-manager smoke 使用隔离 task tmp workspace，不复用根 workspace 现有 ignored process runtime。
- Python 命令统一 `-X utf8 -B`，避免 `__pycache__` 写权限问题。
- 如 PSScriptAnalyzer 未安装，记录 unavailable；PowerShell 只作为保留 fixture 的附加检查，不是公共运行门禁。

## Git 上下文（Git Context）

- Main / working branch：`harness/feature`，跟踪 `origin/harness/feature`。
- Task type / branch action：在当前用户分支规划和实施，不创建额外版本分支。
- Sync source / occupancy evidence：规划开始时 `git status --short --branch` 为 clean，未显示 ahead/behind。
- Worktree status and known changes：规划开始 clean；本轮只新增 current task bundle，未发现用户未提交改动。
- Commit authorization：`authorized_final_only`；当前分支仅在全部本地 required gate 与 review 通过后执行一次 `git commit -F`。
- External CI authorization：`not_authorized_for_executor`；执行器不 push/delete ref、不触发或读取 Actions，用户在提交后自行 push 和检查 CI。
- Elevated authorization：`not_authorized_for_executor`；执行器不运行本机、生产或 hosted runner elevated 命令。
- Branch closure：执行器完成本地提交后停止；不 push、不建 MR，后续远端动作由用户负责。

Git 命令串行；只读 status/diff 优先避免 optional locks/index refresh。不自动 stash、rebase、reset 或覆盖未知改动。遇到 index.lock 只按精确路径、稳定性和进程证据处理。

## 工具（Tooling）

| Tool | Purpose | Stage | Status | Risk | Alternative | User confirmation |
| --- | --- | --- | --- | --- | --- | --- |
| `apply_patch` | 精确代码/文档修改 | STG-01-05 | available | partial patch | inspect then repair | implementation approval |
| Python | unit/eval/static/fake HTTP | all | available | subprocess/temp | no weaker substitute | implementation approval |
| PowerShell 7 | existing fixture/parser only | STG-03/04/06 | available locally | platform-specific | Python native smoke | implementation approval |
| Git | status/diff/final commit | STG-06 | available | repository mutation | read-only until authorized | separate commit approval |
| GitHub Actions | Windows/Ubuntu/macOS post-commit matrix | VAL-12 | deferred to user after push | external write/CI | local deterministic tests | not authorized for executor |
| Ubuntu transient systemd unit | delegated cgroup strict smoke | VAL-12 | deferred to user-run hosted runner | CI-only sudo | fallback smoke + user-provided delegated runner | not authorized for executor |
| Web | implementation drift research only | any drift | available | changing docs | official local cache none | no write; amendment if scope changes |
| skill-creator quick_validate | skill structure validation | STG-01/04/06 | available from installed system skill | external path | record actual path | implementation approval |
| GitLab PAT API | optional read/write smoke | STG-06 | env configured per user | external data/write | fake HTTP required tests | read no extra; write separate authorization |
| process-manager | final self-smoke bootstrap | STG-04/06 | target under modification | process lifecycle | bounded finite harness | implementation approval |

## 长期进程管理（Process Manager Gate）

- Needs long-running process：`yes`，仅 implementation 的 process-manager self-smoke 和被托管 test service。
- Managed services、stage 和 readiness：STG-03/04/06 在各 runner 隔离 tmp 启动 manager；test service 必须经 current `pm_*`，使用 HTTP/log/process readiness，并在同一 smoke 内 stop/shutdown。
- Required process-manager evidence：统一 config、内部 manager identity、authenticated health、service validation、processKey/native owner identity、ready、bounded logs、平台无关 stop result、owner-empty cleanup、manager shutdown；backend/capability 仅作为测试审计，不作为消费者参数。
- Fallback or blocker：unit/integration harness 是有 timeout/finally 的 finite command；不得手写业务后台启动。manager bootstrap 只能使用统一 `pm_manager.py`。若无法证明 cleanup、manager identity 或内部安全 owner，任务 blocked；不得要求调用方改选平台接口。

普通 test/build/lint/eval 是 finite command，直接运行。不得用 `Start-Process`、shell background、`nohup` 或自制 launcher 绕过 process-manager；统一 bootstrap 内部实现本身是本任务的验证对象。

## 验证（Validation）

| VAL ID | Required | Kind / command / tool | Covers AC/NFR | Evidence path | Failure handling |
| --- | --- | --- | --- | --- | --- |
| VAL-01 | yes | GitLab unittest discover | AC-01-06；NFR-01-06 | `artifacts/validation/gitlab-unit-integration.txt` | repair and rerun |
| VAL-02 | yes | GitLab executable eval runner | AC-02-06；NFR-04/06 | `artifacts/validation/gitlab-evals.json` | repair fixtures/behavior and rerun |
| VAL-03 | yes | process-manager unittest discover | AC-07-11；NFR-01-07 | `artifacts/validation/process-manager-tests.txt` | cleanup owned fixtures, repair, rerun |
| VAL-04 | yes | current-OS isolated Python native lifecycle smoke | AC-07-11；NFR-01/02/03/05/07 | `artifacts/validation/process-manager-native-smoke.json` | preserve owner identity evidence, stop |
| VAL-05 | yes | process-manager executable eval runner | AC-10-12；NFR-04/06/07 | `artifacts/validation/process-manager-evals.json` | repair behavior/fixture and rerun |
| VAL-06 | yes | cross-skill contract runner | AC-12；NFR-04/05/06/07 | `artifacts/validation/cross-skill-regression.json` | repair consumer, rerun impacted tests |
| VAL-07 | yes | AST/fixture parser/JSON/schema/old-contract/platform static checks | AC-01-12；NFR-01/03/04/05/06/07 | `artifacts/validation/static-schema-checks.json` | remove drift, rerun |
| VAL-08 | yes | skill-creator quick_validate for both skills | AC-06/11/12；NFR-04/06 | `artifacts/validation/skill-validation.txt` | repair skill structure |
| VAL-09 | yes | ART-04 final review checklist + diff check | all AC/NFR | `artifacts/reviews/final-code-review.md` | finding blocks completion |
| VAL-10 | no | real GitLab read-only doctor/search/get | AC-02/03 | `artifacts/validation/gitlab-live-read-smoke.json` | record unavailable/residual |
| VAL-11 | no | separately authorized codex_test reversible write smoke | AC-04/05 | `artifacts/validation/gitlab-test-project-write-smoke.json` | stop on mismatch; no retry |
| VAL-12 | no | 用户 push 后运行 GitHub Actions windows/ubuntu/macos matrix；三平台公共 CLI/schema/envelope/error parity；Ubuntu automatic fallback + scoped transient delegated-cgroup strict | AC-07-12；NFR-01-07 | `artifacts/validation/process-manager-platform-matrix.json` | 本次记录 deferred；用户反馈失败后基于最终 commit 修复并重跑 |

规划阶段探针与实施验证分开：基线 29 tests passed 只证明旧行为未坏，不证明新方案。无法执行 required 项必须停止或 amendment，不能标为 passed；optional VAL-12 未运行时必须诚实披露平台证据缺口。

## 文档（Documentation）

必需更新：

- 两个 SKILL.md、agents metadata、workflow/security/schema/capability references。
- 两套 executable eval README/manifest/expected/runner/fixtures。
- process templates/examples；GitLab registry 输出替代重复 api-map。
- process platform-backends reference 与 GitHub Actions 三平台 workflow。
- electron-ui-verifier process service/docs。
- planner/executor Process Manager Gate、templates/evals。
- README、`.gitignore`、`.harness/environment.md`。

Changelog 计划：

- 在 CHANGELOG 顶部记录两个 skill 的 current direct cut、核心安全/能力变化、consumer adaptation 和验证摘要。
- 不创建 v2 标题，不改写历史条目；历史文档中的旧事实可保留在历史 task/changelog context。

## 文件写入策略（File Write Strategy）

| File / group | Segmented | Semantic boundaries | Whole-file check |
| --- | --- | --- | --- |
| GitLab package/entry scripts | yes | config/transport/policy/resource one module at a time | import/AST/tests |
| process-manager package | yes | platform adapters/state/runtime/host/probe/log/client | line count/import/tests |
| `manager_server.py` / old commons | yes | create replacement modules before removing old | no old imports |
| tests/eval runners | yes | fixture/helper/test class/scenario | discover/runner output |
| SKILL/references | yes | core workflow then conditional refs | quick_validate/link scan |
| planner/executor/electron consumers | no for narrow patches | exact contract references | cross-skill runner |
| README/ignore/environment/changelog | no for narrow patches | targeted sections | diff review |

长内容先建框架，再按完整函数、class、schema 或章节 patch；单次新增建议不超过 120 行、最多 200 行。超过 500 行的现有文件默认拆职责后定点移除，不整文件盲写。每次 patch 后检查部分写入、完整重读、格式/ID/引用和文件末尾。

## 问题和覆盖项（Questions And Overrides）

| ID | Blocking | Status | Question | Decision | Applied to |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | decided | 保留 GitLab daemon 吗 | 否，继续 script-only | STG-01/02 |
| D-002 | no | decided | process control 用固定端口还是 runtime endpoint | OS-assigned port + manager.json | STG-03 |
| D-003 | no | decided | manager crash 后收养还是清理 service | native owner/guardian 收口，不按 PID 收养 | STG-03/04 |
| D-004 | no | decided | 保留 old env/schema alias 吗 | 否，直接拒绝 | all stages |
| D-005 | no | decided | required tests 是否做真实 GitLab write | 否，fake HTTP；live write optional and separately authorized | STG-02/06 |
| D-006 | no | decided | 引入 third-party SDK/supervisor 吗 | 否，stdlib/ctypes + OS 原生设施 | all stages |
| D-007 | no | decided | 三平台是否暴露不同接口或统一最低 process-group | 外部统一 CLI/schema/envelope；内部 Windows Job/Linux cgroup/macOS guardian 各用最佳安全 backend，不降为最低共同实现 | STG-03/04 |
| D-008 | no | decided | Linux 无 delegation 如何处理 | 内部 dispatcher 自动 process-group fallback，公共 contract 不变；无任何安全 owner 时 fail closed | STG-03/04 |
| D-009 | no | decided | 如何证明 Linux/macOS | 用户 push 后运行 GitHub Actions 三平台 matrix；未取得结果前保留真实 runner 证据缺口 | STG-04/06 |
| D-010 | no | decided | STG-01 如何在 STG-02 前执行 required VAL-02 | 将 `evals/gitlab-pat-ops/**` 纳入 STG-01 allowed changes；只提前建立核心 eval runner，不改变 STG-02 资源 eval 责任 | STG-01/02 |
| D-011 | no | decided | STG-01/STG-03 如何执行 required VAL-07 | 依据用户批准的 `evals/**` 范围，将唯一 `evals/process-manager/run_static_checks.py` 纳入两阶段 allowed changes | STG-01/03 |

## 方案质量门禁（Plan Quality Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| 关键判断有证据等级 | passed | Context evidence table、ART-01 |
| Research Gate 已完成 | passed | official URL source matrix、ART-01 |
| Standards Discovery Gate 已完成 | passed | ART-02 |
| Development Quality Gate 已完成 | passed | quality matrix、ART-02/03 |
| 影响面矩阵完整 | passed | API/data/config/compat/test/docs/architecture covered |
| 候选方案比较充分 | passed | minimal/structured/third-party 三方案 |
| 每阶段可独立验证 | passed | Stage contracts + VAL mapping |
| 方案变更触发条件清楚 | passed | contract/reapproval section |
| 用户批准摘要可记录 | passed | approval section/handoff |

质量结论（Quality result）：`passed`。full profile、6-stage DAG、6 approval artifacts 和 complete traceability 与风险匹配。

## 规划自查（Plan Self-Review）

自查结论（Review result）：`passed`。clean-context subagent 不可用，已执行 fallback critique 并保存 ART-05。

| Category | Finding | Action | Result |
| --- | --- | --- | --- |
| Defects | write retry、cross-origin PAT、PID-only kill、Windows-only bootstrap/launcher、state race、secret persistence | 纳入 must requirement/high-risk stage | passed |
| Optimizations | Project Templates/MR diffs/PAT self/keyset/ephemeral port/native supervisor | 只选择直接适用项 | passed |
| Missing items | Linux/macOS backend、process tests、三平台 CI、executable eval、agent metadata、consumer adaptation | REQ-06/09/10、NFR-07 | passed |
| Risks | no CAS、Job/cgroup/group behavior、delegation/permission、CI/final-commit 时序、log redaction limits | native smoke + candidate tree parity + CI matrix + honest residual disclosure | passed |
| Consistency | old alias/version/schema 与用户要求冲突 | direct cut + old-contract scan | passed |
| Development quality | large mixed modules/duplicate truth | package boundaries/registry/line budget | passed |

门禁重跑：

- Plan Quality Gate：已在 critique 后重跑，passed。
- Plan Self-Review：ART-05 findings 全部 closed，passed。
- Readiness Gate：以下项目逐项检查，passed。

## 就绪门禁（Readiness Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| 目标和验收清楚 | passed | GOAL-01、REQ-01-10、AC-01-12 |
| 上下文已收集 | passed | local inventory/tests/cross references |
| 调研门禁已通过 | passed | ART-01 |
| 规范发现门禁已通过 | passed | ART-02 |
| 开发质量门禁已通过 | passed | ART-02/03 |
| 候选方案已比较 | passed | Options A/B/C |
| 决策已记录 | passed | structured direct cut |
| 实施阶段已细化 | passed | STG-01-06 contracts |
| 环境已确认 | passed | local Windows/Python/task tmp；external Linux/macOS runner route documented |
| Git 上下文已确认 | passed | clean branch baseline |
| 工具已确认 | passed | tooling table |
| 验证已确认 | passed | VAL-01-09 为本地 required；VAL-10-12 optional，VAL-12 由用户提交后运行 |
| 最终交付证据已规划 | passed | evidence paths/review/cleanup/commit |
| 文档更新已确认 | passed | documentation section |
| 风险已识别 | passed | ART-01/05 |
| 规划自查已通过 | passed | ART-05 |
| 阻塞问题已关闭 | passed | open blocking findings none |

就绪结论（Readiness result）：`ready_for_approval`。这表示可以请求用户批准，不表示自动进入实施。

## 方案批准（Plan Approval）

状态（Status）：

- `approved`

批准记录（Approval record）:

- 用户已批准 STG-01 至 STG-06 的实施和最终一次 `git commit -F`。用户最新指示覆盖此前临时 candidate ref/Actions 授权：执行器现在只做本地提交，push 与 CI 检查由用户完成。

批准摘要（Approval summary）:

- 批准范围：STG-01 至 STG-06 的两个 skill direct cut、Windows/Linux/macOS process backends、tests/evals/CI/docs 和列明 consumer adaptation。
- 阶段提交授权：仅在 STG-06 本地 required validation/review 通过后执行一次最终 `git commit -F`。
- 工具/MCP 授权：允许使用 Python、Git、skill-creator 和必要 official web research；不授权执行器使用 GitHub Actions 或 elevated tool。
- 文档更新授权：申请更新 contract 列明的 skill/references/evals/README/examples/ignore/environment/changelog。
- External CI write：不授权执行器；用户在本地提交后自行 push、运行并检查 Actions。
- Elevated tool：不授权执行器；用户侧 CI 是否运行 scoped transient unit 由用户自行决定和监督。
- GitLab external write：不申请；VAL-11 必须另行明确授权，不能复用 CI 授权。

提交策略（Commit policy）：

- `authorized_final_only`；仅在全部本地 required validation、review 与 staged scope/tree 检查完成后提交。

## 方案变更门禁（Plan Amendment Gate）

需要重新批准：

- approved scope、public behavior、Stage DAG/contract、required validation、artifact 或 commit policy 改变。
- 新增 GitLab 高影响写、daemon、GraphQL/DPoP key management 或真实 external write。
- 改变 PAT 同源/write retry/fingerprint/current env，或平台支持范围/内部 backend 自动选择/统一公共 contract/full identity/owner-death/current process schema。
- 引入第三方 runtime dependency、超出 scoped Ubuntu CI transient unit 的 elevated tool、自动持久系统配置或兼容旧版。
- implementation 发现官方 API、Windows Job、Linux cgroup/systemd 或 macOS process-group/launchd 行为与 approved research 有实质 drift。

修订记录：

| Time | Change | Reason | Evidence |
| --- | --- | --- | --- |
| 2026-07-10 | 无 | 初始批准方案 | plan revision 1 |
| 2026-07-10 | STG-01 增加 `evals/gitlab-pat-ops/**` allowed scope | required VAL-02 runner 原本不存在且无法在 STG-01 合法创建 | revision 1 archive + EVT-000005/000006，等待 revision 2 批准 |
| 2026-07-10 | STG-01/STG-03 增加 `evals/process-manager/run_static_checks.py` allowed scope | required VAL-07 runner 原本不存在且无法在前置阶段合法创建 | revision 2 archive + 用户已批准 `evals/**` |
| 2026-07-10 | 仅更新 external CI 与 CI-only elevated authorization | 用户明确批准临时 candidate ref、三平台 Actions 和 Ubuntu scoped systemd-run；实现语义与 Stage contract 不变 | revision 3 archive + EVT-000104 + 当前用户授权 |
| 2026-07-10 | VAL-12 改为用户侧提交后可选验证，并撤销执行器 external/elevated 授权 | 用户要求先本地提交，由其自行 push 和检查 CI；不改变实现、DAG 或已完成阶段语义 | revision 4 archive + EVT-000019/000020 + 当前用户授权 |

## Artifact Index

| ID | Kind | Path | Required | Approval included | Trigger |
| --- | --- | --- | --- | --- | --- |
| ART-01 | research | `artifacts/research/domain-research.md` | yes | yes | online-required/high-risk |
| ART-02 | standards | `artifacts/standards/standards-index.md` | yes | yes | full/development quality |
| ART-03 | architecture | `artifacts/architecture/target-architecture.md` | yes | yes | cross-module/direct cut |
| ART-04 | validation | `artifacts/validation/validation-strategy.md` | yes | yes | high-risk external/process behavior |
| ART-05 | review | `artifacts/reviews/plan-critique.md` | yes | yes | full critique |
| ART-06 | other | `artifacts/traceability/traceability-matrix.md` | yes | yes | complete traceability |

只列实际 planning artifacts；executor validation logs/final review/commit evidence 批准后创建，不进入批准 artifact 集合。

## Executor Handoff

- Planner checker：`approval` mode passed，`issues: []`。
- Open blocking decisions：none。
- Granted implementation authorization：yes。
- Granted commit authorization：yes，final only，必须使用 `git commit -F`。
- Granted external-write authorization：no；GitHub push/CI 与 GitLab write 均不由执行器执行。
- Granted elevated-tool authorization：no；本机、生产与 hosted runner 均不由执行器提权。
- Residual risks：GitLab update 无通用 CAS；macOS process group 无法约束主动 setsid/daemonize；生产 Linux 环境可能只能显式降级；企业 DACL/mode 可能阻断；exact-value log redaction 不是完整 DLP。

executor 依据本次精确授权生成 revision 5 attestation，并通过 amendment archive 继承实现语义未变且已完成的 stages。本文件批准后不可变。

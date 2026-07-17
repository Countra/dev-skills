# Process Manager 控制面收敛与资源治理升级执行计划

## 规划摘要（Plan Summary）

- Task ID：`2026-07-17-feature-process-manager-control-plane-convergence`
- Plan revision：`2`
- Lifecycle route：`managed`
- Plan profile：`full`
- Discovery-first：`no`
- Task contract：`plan-contract.json`
- Approval request：当前仅请求用户批准 implementation；commit、外部写入和提权均未授权
- Dependency selection：`none`，实现继续使用 Python 3.12 标准库和现有 Windows/Linux/macOS native API

本文件只保存待批准的实施意图。批准后不得把 current stage、progress、运行结果、ledger、commit 或恢复状态写回本文；执行事实由 Executor 创建的 attestation、run-state、ledger、validation artifacts 和 code-review receipts 承载。

## 问题定义（Problem）

目标（Goal）：`GOAL-01`，将 `process-manager` 升级为显式 workspace、幂等收敛、可中断恢复、资源有界、三平台统一的本地控制器，使 Planner、Executor、Electron verifier 等调用方能够确定 manager 状态，并通过 session lease 安全清理本轮进程树。

当前实现已经具备 Windows Job Object、Linux cgroup/process group、macOS launchd/process group、loopback token、state store、服务级 start/ready/status/logs/stop/restart、unit/eval/native smoke 与三平台 CI。这些基础值得保留；主要问题集中在控制面和生命周期治理：

1. 公共命令仍可能由当前工作目录推导配置，恢复任务在不同 CWD 下可能观察到另一个 runtime。
2. `pm_manager.py` 只有 `start/status/stop`，调用方通过 `status -> start` 猜测；`starting/stopping/stale/unresponsive/security/environment` 被压缩为离线或异常。
3. start 在探测 manager 前可能 mutation runtime，status/health/shutdown 又存在重复实现，容易产生不一致证据。
4. manager crash/restart 对持久 active records 的 reconciliation 会过早提交 terminal 或移除 active，owner tree 是否为空没有成为最终提交条件。
5. 验证任务没有 session lease；正常结束依赖调用方记得逐项 stop，中断后没有统一的 expiry/finalizer 补偿路径。
6. history count 有界但 retained bytes、age、active count、manager logs 和 cleanup pending 没有完整硬上限，长期运行可能留下较多 run directory 与日志。
7. Windows ACL 验证依赖 SDDL 文本形态和错误词匹配，容易把等价继承 ACL、外层 shell/profile 拒绝或不可验证环境误判为权限问题。
8. Planner、Executor、Electron verifier 各自硬编码 manager 检查/启动/清理顺序，中断恢复时会重复探测、重试并扩大错误噪音。
9. 现有测试覆盖大量组件和 native lifecycle，但缺少并发 ensure、持久 operation receipt、restart phase fault、session expiry、automatic GC 和错误分类的完整 public contract。

非目标（Non-goals）：

- 不把 process-manager 变成系统级服务编排器、容器平台或通用守护进程框架。
- 不新增平台公开接口；Windows、Linux、macOS 差异继续由内部 adapter 自动处理。
- 不按任意 PID、进程名或全机枚举清理，不接管无 owner 证据的外部进程。
- 不在 manager restart 后自动恢复旧 service，避免隐式副作用与 restart loop。
- 不保留旧 runtime schema、旧 health/shutdown wrapper、双 public contract 或兼容 parser。
- 不引入 `psutil`、`pywin32`、第三方 supervisor、数据库、后台索引或新系统服务。
- 不默认请求管理员/root 权限；普通 workspace 生命周期必须在当前用户权限内完成。
- 不在规划阶段修改 Skill 实现、启动服务、写执行状态或创建 Git commit。

约束（Constraints）：

- 所有公共 stdout 保持单一 JSON envelope，错误码、state、retryable 与 recommended action 为 closed contract。
- whole-tree cleanup、unrelated process isolation、secret redaction、loopback/token、no shell、no arbitrary PID 和 no auto restore 是不可回退安全不变量。
- public contract、state/session schema、调用方文档、eval 和 CI 采用 current-only 原子迁移，不产生可恢复的半升级中间态。
- status 必须纯读；任何 runtime 创建、ACL remediation、identity 清理或 bootstrap cleanup 都只能发生在明确 mutating command。
- owner 未证明为空时不得提交 terminal、closed 或 successful stop/restart。
- Hosted CI 属于 required release evidence；Agent 不得伪造未推送 commit 的三平台结果。

待确认项（Open uncertainties）：无批准前阻塞项。不同用户机器的 Windows ACL、非 systemd Linux 和 macOS launchd 真实差异只能由实现后的 native/hosted 证据覆盖；未观察环境必须报告限制，不能泛化为全部平台已证明。

## 需求与验收（Requirements And Acceptance）

功能需求：

| ID | Priority | Requirement |
| --- | --- | --- |
| REQ-01 | must | 所有公共命令使用显式绝对 workspace 或 config，禁止 CWD 静默选择 runtime |
| REQ-02 | must | 建立纯读 closed manager state resolver，区分 absent、pending、stale、unresponsive、security、environment 与 corrupt |
| REQ-03 | must | `pm_manager ensure` 在持久 operation lock/receipt 下幂等收敛到 ready |
| REQ-04 | must | manager stop/restart 成为可恢复 phase operation，精确停止 owned runs、清 bootstrap，且不恢复旧 service |
| REQ-05 | must | manager loss/restart 先验证 native owner empty，再提交 terminal 或移除 active |
| REQ-06 | must | 新增 session open/renew/status/close、lease expiry 与 finalizer；start 必须声明 session 或 persistent |
| REQ-07 | must | active/inactive/age/bytes 配额、automatic GC、compact tombstone 与 start admission 持续生效 |
| REQ-08 | must | Windows/POSIX runtime security verify-first，准确区分 insecure、denied、unverifiable 和外层环境，无默认提权 |
| REQ-09 | must | public contract current-only 原子迁移，删除重复 health/shutdown 和泛化 manager_offline |
| REQ-10 | must | Planner、Executor、Electron verifier 使用 ensure + session + finally close，finite command 直接运行 |
| REQ-11 | must | unit/eval/static/native/三平台/delegated cgroup/review/final cleanup 形成完成门 |
| REQ-12 | must | 保留三平台自动选择、whole-tree owner、loopback token、secret redaction、无 arbitrary PID/no shell/no auto restore |
| REQ-13 | must | status/doctor 提供平台中立 state/action/resource summary，doctor 提供受限 native diagnostics |

非功能需求：

| ID | Requirement |
| --- | --- |
| NFR-01 | 普通 public schema、commands 和 state 在 Windows/Linux/macOS 一致，平台选择只在内部与 doctor audit 暴露 |
| NFR-02 | 不按任意 PID或全机枚举 cleanup，不自动恢复 service，不引入 restart loop |
| NFR-03 | 当前用户、loopback、token、secret redaction、path/symlink 边界保持；普通使用不要求管理员 |
| NFR-04 | manager operation、session close、start admission 在并发和中断下线性化且幂等 |
| NFR-05 | active count、history count/age、retained bytes、日志和所有 wait/poll 具有硬上限 |
| NFR-06 | error message 精确、code closed、retryable 只用于已证 transient，doctor diagnostics 脱敏 |
| NFR-07 | state/filesystem cleanup 使用 atomic commit、quarantine、rollback/finalizer；owner 未空不丢证据 |
| NFR-08 | status 和 sweeper 使用有界精确索引，不做全 workspace/全机扫描；endpoint probe 使用短 timeout |
| NFR-09 | 继续使用 Python 3.12 标准库与现有 native API，不新增、升级或替换第三方依赖 |
| NFR-10 | current-only 原子迁移，无旧 runtime schema、legacy script、compatibility parser 或双 public contract |

验收标准：

| ID | Requirement IDs | Given / When / Then |
| --- | --- | --- |
| AC-01 | REQ-01 | 从不同 CWD 向同一 absolute workspace/config 调用时解析为同一 runtime；缺失、相对、冲突或 mismatch 返回 `context_invalid` 且不写文件 |
| AC-02 | REQ-02、REQ-13 | status 对 ready/absent/starting/stopping/stale/unresponsive/insecure/denied/unverifiable/corrupt 返回唯一 state、证据摘要和建议动作，且不 mutation |
| AC-03 | REQ-03 | 已初始化 workspace 中两个调用者并发 ensure 时只产生一个 operation 和 manager instance，双方最终观察 ready；未初始化 workspace 返回 init action 且不隐式创建 config |
| AC-04 | REQ-02、REQ-03 | status 在 ensure/stop 期间公开 checkpoint、deadline、retryAfter；未超期 pending 不被误判 offline 或 stale |
| AC-05 | REQ-04 | restart 对 healthy 或 exact-unresponsive manager 完成 intake close、owned tree cleanup、bootstrap cleanup 与新 instance ready，并返回 `servicesRestored=false`；身份不确定不 kill，存在其它 ownership 时无显式 destructive confirmation 不执行 |
| AC-06 | REQ-04 | stop 对 absent 和重复调用幂等；任一 owner、identity 或 bootstrap 未清时保留 pending evidence，不虚假成功 |
| AC-07 | REQ-05 | crash 后持久 active record 先保持 terminating，逐 owner cleanup/verify 后才 terminal；无法验证则保持 cleanup pending |
| AC-08 | REQ-06 | 关闭一个 session 只清该 session runs，不影响其他 session、persistent run 或无关进程 |
| AC-09 | REQ-06 | lease expiry 或 close 中断后 sweeper/ensure 继续同一 finalizer，owner empty 后 closed；idle shutdown 与新 work 原子互斥，竞态时保留 manager |
| AC-10 | REQ-06 | start 未提供 session 且未显式 `--persistent` 时失败；service restart 继承原 ownership |
| AC-11 | REQ-07 | history 超 age/count/bytes 时只事务化清理 eligible terminal run，active/terminating 不删除，central tombstone 保留 |
| AC-12 | REQ-07、REQ-13 | active 或 retained bytes 达限时先有界 GC，仍超限则拒绝 start；status 报 usage/limit/overBudget/cleanupPending |
| AC-13 | REQ-08 | Windows 等价 inherited ACL 被接受，broad allow/rights不足判 insecure，descriptor denied 判 permission denied，证据不足判 unverifiable，status 不改 ACL |
| AC-14 | REQ-08、REQ-13 | PM error 与外层 shell/profile access denied 分层；doctor 不硬写 supervisor ready，无 JSON envelope 时不归因 ACL、不删 runtime、不自动提权 |
| AC-15 | REQ-09、REQ-10 | static/eval 中 public happy path 只使用 ensure/session/manager stop，health/shutdown、status-start、泛化 manager_offline current refs 全部消失，三个 consumers 同步通过 |
| AC-16 | REQ-12 | 三平台 start/stop/crash/restart/session expiry 保持 whole owned tree cleanup、unrelated process survive、backend 不泄漏、no arbitrary PID/no shell/no auto restore |
| AC-17 | REQ-11 | 当前 commit 的 Windows/Ubuntu/macOS matrix 与 Ubuntu delegated cgroup job 全部通过并上传匹配 commit/attempt 的 machine evidence |
| AC-18 | REQ-11 | final review/cleanup/audit 后 required receipt passed，无 active/terminating/cleanup pending、manager/bootstrap/task tmp residue，diff allowlist 合法 |

完整 Requirement → AC → STG → VAL → ART 闭环见 ART-06。

## 调研门禁（Research Gate）

Research mode：`online-required`。

触发原因：用户要求深度复查和前沿调研；本任务涉及跨平台进程树 ownership、服务过渡状态、lease/finalizer、ACL 权限语义和 CI，均属于高风险且可能随平台实现变化的领域，不能只依赖模型记忆或单一参考项目。

主要一手证据：

| Layer | Authority | Plan impact |
| --- | --- | --- |
| Windows service lifecycle | Microsoft `SERVICE_STATUS` 与 service state transitions | 采用 checkpoint/wait hint/deadline 表达启动/停止过渡，不把正常窗口误判离线 |
| Windows process ownership | Microsoft Job Objects | 保留 kill-on-close whole-tree ownership 与 accounting，restart 只处理 exact owner |
| Windows access control | Microsoft GetNamedSecurityInfo、AccessCheck/Authz 与 ACL API | 从 SDDL 文本相等迁移到 owner/DACL/ACE/effective rights 语义验证 |
| Linux ownership | Linux kernel cgroup v2 文档 | delegated cgroup 使用 `cgroup.events populated` 和 `cgroup.kill` 证明/执行 owner-empty |
| systemd | systemd `KillMode=control-group` 与 `Delegate=` | Ubuntu delegated job 验证完整 cgroup 生命周期，fallback 不冒充 delegated 能力 |
| macOS manager lifecycle | Apple launchd job 与 daemon lifecycle 文档 | exact label/domain bootstrap、bootout 与 process-group recovery 保持平台内聚 |
| Lease/finalizer patterns | Kubernetes probes、Lease、finalizers | 分离 liveness/readiness、使用续约租约和删除前 finalizer，不照搬集群架构 |
| Python subprocess/style | Python 3.12 subprocess、Google Python Style | 参数数组、timeout、异常、线程与资源释放保持标准库和现有代码风格 |
| CI | GitHub Actions workflow syntax | 任意 branch 的三平台证据与 Ubuntu scoped systemd job 保持确定性 |

调研比较了四类方案：只补 restart/cleanup 脚本、改用外部 supervisor、引入控制面 operation + session lease、改为 OS system service。选择第三种：它能在不增加第三方依赖和系统级权限的情况下闭合状态、恢复和资源治理；外部 supervisor 与系统服务会扩大安装、权限、平台和故障面，只补脚本则继续保留重复真相源。

完整来源、观察日期、适用限制、拒绝照搬项和证据饱和判断见 ART-01。Research result：`passed`。

## 依赖选型门禁（Dependency Selection Gate）

本任务模式：`none`。

现有 Python 3.12 标准库、`ctypes`、POSIX primitives、Windows Job/ACL API、Linux cgroup/process group 与 macOS launchd/process group 足以实现目标。不新增依赖可以避免安装失败、ABI/platform wheel、管理员权限、供应链和维护活跃度的新决策面。

如果实现发现必须引入第三方包、系统 daemon 或新的 runtime dependency，必须触发 amendment，并正式比较稳定版本、用户规模、更新时间、维护活跃度、采用趋势、安全、许可和项目适配；不得在 stage 内临时安装。Dependency selection result：`not-applicable`。

## 规范发现门禁（Standards Discovery Gate）

适用规范和优先级：用户与项目明确约束 > 根/目录 `AGENTS.md` > 当前 Planner/Executor/Reviewer/Process Manager 契约 > OS/Python/GitHub 官方文档 > 通用工程指导。完整索引见 ART-02。

- 技术栈证据：当前实现为 Python 3.12 stdlib + `ctypes`/POSIX native API，三平台 owner adapter 和 GitHub Actions 已由 ART-01/ART-02 定位。
- 决策影响：Windows service/Job/ACL、Linux cgroup v2/systemd、macOS launchd 与 Python subprocess 官方规则分别约束 state、owner cleanup、权限分类、no-shell 和 timeout。
- 验证影响：对应规范映射到 VAL-03/06/09/10/14/15；仅有文档引用而没有 native/fault evidence 不能满足完成门。
- 适用限制：Kubernetes Lease/Finalizer 只借鉴状态语义，不引入集群控制器；Google Python Style 不覆盖 OS 权限正确性。

Standards result：`passed`。完整来源、适用边界和验证映射见 ART-02。

## 开发质量门禁（Development Quality Gate）

开发质量要求：

| Dimension | Decision |
| --- | --- |
| Architecture | Public CLI → Context Resolver → read-only State Resolver → mutating Converger → authenticated Manager API → State Store → Native Adapter 单向依赖 |
| Cohesion | manager lifecycle、session、resource policy、runtime security 分模块；CLI 只做参数和 envelope，不复制业务状态机 |
| Coupling | consumers 只依赖 ensure/session/public errors，不读取 identity、ACL、cgroup、launchd 等内部文件 |
| Concurrency | operation lock/receipt、session finalizer 与 state atomic commit 各有唯一 writer；无双锁真相源 |
| Error handling | closed state/error taxonomy、精确 retryable、bounded timeout、失败保留 receipt/finalizer evidence |
| Security | verify-first、current user、loopback/token、semantic ACL、no elevation、no arbitrary PID、path/symlink containment |
| Resources | active/count/age/bytes/log/poll 全部有界；terminal GC 事务化，active/terminating 永不自动删 |
| Testability | pure resolver/state table、fault injection、mock native adapter 与真实三平台 smoke 分层 |
| Simplicity | 使用 State Machine、Lease、Finalizer、Adapter、Repository/Transaction 等直接模式，不引入规则 DSL、plugin registry 或通用 orchestrator |

SOLID 和设计模式只用于固定真实职责边界，不机械套用全部模式。过度设计防护：不新增平台 CLI、系统服务、数据库、后台索引、event bus、兼容层、自动 service restore 或第二套 cleanup engine。Development quality result：`passed`。

## 上下文（Context）

当前本地基线：`skills/process-manager/tests` 共运行 74 项，1 项按平台条件跳过，其余通过；这只能证明当前 unit/component 基线，不证明本方案能力已存在。现有 `.github/workflows/process-manager-platforms.yml` 已覆盖三平台 public lifecycle 与 Ubuntu delegated cgroup，可扩展为本方案 hosted evidence，而不新增第二条重复 workflow。

关键事实等级：

| Claim | Level | Consequence |
| --- | --- | --- |
| CWD 默认、status/start 分离、health/shutdown 重复、generic offline | read from current source | 必须在 current-only public migration 删除 |
| manager loss 先清 active、shutdown 仅依赖内存 runs | read from current source | owner-first persisted reconciliation 是高风险核心阶段 |
| Job/cgroup/process-group/launchd 已存在 | read + current tests | 保留 adapter 架构，避免重写平台内核 |
| ACL 误报与 manager 状态拿不准 | user report + source-supported inference | 需要 closed resolver、semantic security 与 environment error 分层 |
| 长期残留资源规模 | inferred from current defaults | 实现后必须以 bytes/age/count/accounting 验证，不能仅靠推算声明修复 |
| 三平台最终效果 | not observed for future implementation | 必须由匹配 commit 的 hosted CI 与 native smoke 证明 |

## 候选方案（Options）

### 方案 A：只补 Restart 与清理脚本

- 做法：保留 `status -> start` 和现有 state，新增 manager restart、验证结束 prune/stop 和更多错误重试。
- 优点：改动较小，短期能降低一部分遗留进程。
- 缺点：CWD、重复 health/shutdown、pending 状态、manager crash reconciliation 和跨调用方猜测仍存在。
- 风险：脚本数量继续增长，状态真相源更多，ACL 和 offline 误判难以消除。
- 验证：只能证明局部脚本路径，无法证明并发收敛和中断恢复。
- 回滚：删除新增 wrapper；但不能解决根因。

### 方案 B：改用第三方 Supervisor 或 OS System Service

- 做法：引入 `psutil`、Supervisor 或把 manager 安装为 Windows service/systemd/launchd system job。
- 优点：可借用成熟 daemon 生命周期和系统启动能力。
- 缺点：新增安装、依赖、权限、版本、平台和系统配置面；仍需自建 run/session ownership 与 workspace isolation。
- 风险：普通 Skill 需要管理员/root，破坏当前用户和可移植边界，故障诊断更复杂。
- 验证：需要安装矩阵、权限矩阵和系统状态回滚，成本显著扩大。
- 回滚：必须卸载/清系统配置，不适合当前 local Skill。

### 方案 C：控制面收敛、Session Lease 与资源治理

- 做法：在现有 stdlib/native adapter 上增加 explicit context、closed resolver、operation converger、owner-first finalizer、session lease、resource governance 与 semantic security。
- 优点：直接解决状态不确定、中断恢复、遗留进程、磁盘增长和 ACL 误判；保留现有三平台 owner 投资。
- 缺点：current-only breaking change，跨 PM、三个 consumers、eval 和 CI，验证量较大。
- 风险：状态机/并发/迁移复杂；通过六阶段、closed contract、fault matrix 和原子 cutover 控制。
- 验证：unit/fault/native/hosted/review/final cleanup 分层证明。
- 回滚：STG-01..04 可按 stage 回退；STG-05 public cutover 必须整体回退，不保留 compatibility layer。

## 决策（Decision）

选择方案 C：建立 workspace-scoped control plane convergence，并在同一 current-only contract 中加入 session lease/finalizer、owner-first reconciliation、resource governance 和 semantic runtime security。详细架构见 ART-03，文件级影响见 ART-04。

原因：方案 A 只能缓解表象，无法消除重复真相源；方案 B 引入不必要的权限和运行依赖。方案 C 在既有平台 owner 上补齐控制面，成本虽高，但与用户报告的根因和 Skill 的跨平台边界最匹配。

可逆性：内部阶段可按完成边界回退；public cutover、state schema、consumer docs/eval/CI 必须整体回退。任何要求兼容旧 runtime 或自动恢复 service 的变化都触发 amendment。

关键设计决定：

1. `--workspace` 与 absolute `--config` 二选一，缺失/相对/冲突均 fail closed；不再依赖 CWD。
2. status 使用 closed read-only resolver；未初始化与已初始化但 manager absent 通过 `initialized/recommendedAction` 区分；ensure/restart/stop 使用同一 operation lock、receipt 与 converger。
3. manager restart 是破坏性控制面操作：清理全部 owned runs，但明确不恢复 service；存在其它 session/persistent ownership 时必须显式确认，Skill 不自动代签。
4. run/session 终态采用 finalizer：只有 native owner empty 后才提交 terminal/closed。
5. Skill 验证默认 session lease 1800 秒；正常 finally close，异常由 expiry sweeper 补偿。
6. start 必须声明 session 或 `--persistent`，让资源所有权成为显式合同。
7. default limits 为 `maxActiveRuns=16`、`maxInactive=20`、`maxAgeSeconds=604800`、`maxRetainedBytes=536870912`；实现中如需改默认值必须以测试/使用场景证据说明。
8. Windows ACL 采用 descriptor/ACE/effective rights 语义；status 只验证，init/ensure 才可安全 remediation，失败不自动 elevate。
9. 删除 `pm_health.py`、`pm_shutdown.py`，保留 `pm_restart.py` 作为 service restart；manager restart 仅是 `pm_manager restart`。
10. Planner、Executor、Electron verifier 与 PM eval/CI 在同一阶段切换，不保留 legacy wrapper。

## 影响面矩阵（Impact Matrix）

| Area | Change | Compatibility | Primary risk |
| --- | --- | --- | --- |
| Context/config | explicit absolute workspace/config 与 current-only config fields | breaking；仓库内调用方原子迁移 | 不同 CWD 指向错误 runtime |
| Manager control | closed resolver、ensure/restart/stop operation | breaking command contract | 并发启动、卡 pending、误杀 manager |
| Run lifecycle | owner-first terminating/finalizer | internal schema breaking | owner 未空却丢 active evidence |
| Session | open/renew/status/close、lease sweeper | new current-only surface | 误清其他 session/persistent run |
| Resources | active/history/age/bytes admission 与 GC | config/schema breaking | 删除 active、GC 事务中断、磁盘继续增长 |
| Security | semantic Windows ACL、POSIX mode/owner、environment split | diagnostics behavior change | 普通用户误报 ACL、越权 remediation |
| Consumers | Planner/Executor/Electron ensure/session/finally close | synchronized breaking workflow | 半迁移导致无法启动或无法清理 |
| Tests/CI | fault matrix、native smoke、3-OS evidence | current workflow extension | unit 通过但真实 owner lifecycle 失败 |

## 实施计划（Implementation Plan）

### STG-01：确定性上下文、状态解析与 Ensure

- Depends on：无
- Requirement IDs：`REQ-01`、`REQ-02`、`REQ-03`、`REQ-13`
- Acceptance IDs：`AC-01`、`AC-02`、`AC-03`、`AC-04`
- Nonfunctional IDs：`NFR-01`、`NFR-04`、`NFR-05`、`NFR-06`、`NFR-08`、`NFR-09`
- Validation IDs：`VAL-01`、`VAL-02`、`VAL-03`、`VAL-08`、`VAL-13`
- Risk：`high`
- Commit expectation：`stage`，但只有用户显式授权 commit 后才可提交

允许修改：

- `skills/process-manager/scripts/process_manager/runtime_context.py`（新增）
- `skills/process-manager/scripts/process_manager/manager_lifecycle.py`（新增）
- `skills/process-manager/scripts/process_manager/cli.py`
- `skills/process-manager/scripts/process_manager/config.py`
- `skills/process-manager/scripts/process_manager/models.py`
- `skills/process-manager/scripts/process_manager/runtime.py`
- `skills/process-manager/scripts/process_manager/errors.py`
- `skills/process-manager/scripts/process_manager/atomic.py`
- `skills/process-manager/scripts/process_manager/bootstrap.py`
- `skills/process-manager/scripts/process_manager/client.py`
- `skills/process-manager/scripts/process_manager/protocol.py`
- `skills/process-manager/scripts/pm_init.py`
- `skills/process-manager/scripts/pm_manager.py`
- `skills/process-manager/tests/test_runtime_context.py`（新增）
- `skills/process-manager/tests/test_manager_lifecycle.py`（新增）
- 与上述 contract 直接相关的现有 focused tests

禁止修改：

- service/run/session/resource public contract 或消费者 happy path，除非是不会被公开使用的必要内部 scaffolding
- 平台 owner cleanup 语义、旧 public script 删除或第三方依赖
- status 中的 runtime 创建、ACL mutation、identity/bootstrap cleanup
- 第二个 manager truth source、未持久化的进程内 operation lock 或 CWD fallback

机器合同字面量：

- Allowed：`skills/process-manager/tests/**`
- Forbidden：`service, session, resource or consumer public migration`
- Forbidden：`status mutation of runtime, ACL, identity or bootstrap`
- Forbidden：`CWD fallback, second manager truth source or third-party dependency`

Entry conditions：

1. revision 2 已获 implementation approval 并写入不可变 attestation。
2. 当前 74 项 PM unit/component 基线可重现，现有工作树用户改动已记录且不被覆盖。
3. context、state set、operation receipt、deadline/checkpoint 和 error taxonomy 按 ART-03 冻结。

实施步骤：

1. 新增纯 `RuntimeContextResolver`，只接受 absolute workspace/config，验证 config-workspace digest，不创建 runtime。
2. 将 default config 从 CWD 解耦；`pm_init` 只在 explicit workspace/config 下创建 current-only layout。
3. 定义 manager state/result/operation closed models 和稳定错误码。
4. 新增 read-only resolver，按 runtime security、operation、identity、exact process、endpoint、bootstrap residue 顺序解析唯一 state。
5. 新增 workspace-scoped operation lock 与 atomic operation receipt；abandoned lock 取得后必须重新 resolve/reconcile。
6. 实现 `pm_manager ensure`：ready 快返、pending 等待、已初始化 absent 单实例启动；未初始化返回 `runtime_uninitialized/init` 且不创建 config；失败回收本次 bootstrap 并持久化 outcome。
7. 将 `pm_manager status` 迁移到同一 resolver，输出 checkpoint/deadline/retryAfter/recommendedAction 和平台中立 evidence。
8. 补 state-table、different-CWD、conflict、pure-read、并发 ensure、timeout/fault 和 residue 测试。

失败与恢复：

- ensure 在 launch/identity/endpoint 任一 phase 失败时，只回收当前 operation 可证明拥有的 bootstrap；不能清理身份不确定进程。
- operation receipt 写失败或 atomic replace 失败时 fail closed，保留原 receipt，不继续启动第二实例。
- 若现有 file lock 无法表达 required timeout/abandoned behavior，只允许对 `atomic.py` 做最小扩展；需要新 dependency 时停止并 amendment。

Exit conditions：

1. 同一 workspace 在不同 CWD 解析一致，所有 invalid context 无文件写入。
2. closed state table 完整且 status mutation detector 通过。
3. 并发 ensure 只启动一个 manager，两个调用获得相同 ready instance evidence。
4. pending checkpoint 正常等待，超 deadline 且无推进才成为 stale/timeout。
5. focused code-review receipt 无 blocking/major finding。

### STG-02：Manager Restart 与 Owner-first Reconciliation

- Depends on：`STG-01`
- Requirement IDs：`REQ-04`、`REQ-05`、`REQ-12`
- Acceptance IDs：`AC-05`、`AC-06`、`AC-07`、`AC-16`
- Nonfunctional IDs：`NFR-01`、`NFR-02`、`NFR-03`、`NFR-04`、`NFR-07`、`NFR-09`
- Validation IDs：`VAL-02`、`VAL-03`、`VAL-06`、`VAL-09`、`VAL-10`、`VAL-13`
- Risk：`high`
- Commit expectation：`stage`，需显式 commit 授权

允许修改：

- `skills/process-manager/scripts/process_manager/manager_lifecycle.py`
- `skills/process-manager/scripts/process_manager/state.py`
- `skills/process-manager/scripts/process_manager/manager.py`
- `skills/process-manager/scripts/process_manager/control_api.py`
- `skills/process-manager/scripts/manager_server.py`
- `skills/process-manager/scripts/process_manager/bootstrap.py`
- `skills/process-manager/scripts/process_manager/service_host.py`
- `skills/process-manager/scripts/process_manager/launch.py`
- `skills/process-manager/scripts/process_manager/platforms/base.py`
- `skills/process-manager/scripts/process_manager/platforms/dispatcher.py`
- `skills/process-manager/scripts/process_manager/platforms/windows.py`
- `skills/process-manager/scripts/process_manager/platforms/linux.py`
- `skills/process-manager/scripts/process_manager/platforms/posix.py`
- `skills/process-manager/scripts/process_manager/platforms/macos.py`
- `skills/process-manager/scripts/pm_manager.py`
- `skills/process-manager/tests/test_manager_lifecycle.py`
- 与 crash/restart/reconciliation/platform contract 直接相关的现有 tests

禁止修改：

- 任意 PID/process-name cleanup、全机扫描或无 identity/capability proof 的 kill
- restart 后 service restore、restart loop、平台公开参数或系统级常驻服务
- owner 未空时清除 active、删除 run record 或返回 successful stop/restart
- session/resource/public consumer migration；该阶段只建立后续所需内部 lifecycle

机器合同字面量：

- Allowed：`skills/process-manager/tests/**`
- Forbidden：`arbitrary PID, process-name or whole-machine cleanup`
- Forbidden：`service auto restore, restart loop, public platform switch or system daemon`
- Forbidden：`terminal commit or active removal before owner empty`
- Forbidden：`session, resource or consumer public migration`

Entry conditions：

1. STG-01 resolver、ensure 和 operation receipt 已通过并有 stage review。
2. exact manager identity、run owner capability 与 bootstrap residue 的证据字段已固定。
3. Windows Job、Linux cgroup/process-group、macOS launchd/process-group 当前 contract baseline 可重现。

实施步骤：

1. 为 run 引入统一 `terminating` finalizer metadata：cleanup attempt/error、owner empty、cleanup verified、finalizedAt。
2. 重写 manager-loss reconcile：读取持久 active records，先 inspect exact owner；空则 terminal，非空且可安全回收则 cleanup，无法验证则保持 pending。
3. manager shutdown 同时枚举内存和持久 active/terminating records，停止 intake 后逐 owner 清理。
4. 扩展 native adapter 的 exact manager termination、owner inspect/empty/accounting 最小接口，保持平台选择内部化。
5. 实现 idempotent manager stop phase machine；只有 runs、identity、bootstrap 全部清理后 succeeded。
6. 实现 manager restart phase machine；healthy 先认证 shutdown，exact-unresponsive 仅在身份和 digest 都可证明时恢复性终止；存在 active/terminating/open-session/persistent ownership 时要求 `--confirm-stop-owned-runs`。
7. restart 输出 old/new instance、stopped run keys、cleanup summary 和 `servicesRestored=false`。
8. 增加 manager crash、phase interruption、identity mismatch、owner cleanup failure、bootstrap residue、restart confirmation 与 unrelated process tests。

失败与恢复：

- 任一 owner 无法验证或 cleanup failed 时保留 `terminating` 和 receipt checkpoint，下一次 restart/ensure 继续处理。
- exact manager identity 不足时返回 diagnostics/recommended doctor，不 kill，也不删除 identity 伪装 absent。
- platform adapter 只能处理自己的 capability/path；cgroup/path/PGID/Job evidence 越界立即 fail closed。

Exit conditions：

1. stop/restart 对重复调用和每个 phase interruption 均可恢复且不启动第二 manager。
2. manager crash 后 persisted runs 只在 owner empty 后 terminal，cleanup pending 可被下一 manager 继续。
3. restart 不恢复 service，无关进程存活，平台 backend 不出现在普通 response。
4. Windows/Linux/macOS adapter contract 与本地 OS smoke 通过。
5. focused code-review receipt 无 blocking/major finding。

### STG-03：Session Lease、Ownership 与 Finalizer

- Depends on：`STG-02`
- Requirement IDs：`REQ-06`、`REQ-12`
- Acceptance IDs：`AC-08`、`AC-09`、`AC-10`、`AC-16`
- Nonfunctional IDs：`NFR-02`、`NFR-04`、`NFR-07`、`NFR-08`、`NFR-09`
- Validation IDs：`VAL-02`、`VAL-04`、`VAL-09`、`VAL-10`、`VAL-13`
- Risk：`high`
- Commit expectation：`stage`，需显式 commit 授权

允许修改：

- `skills/process-manager/scripts/process_manager/sessions.py`（新增）
- `skills/process-manager/scripts/process_manager/models.py`
- `skills/process-manager/scripts/process_manager/config.py`
- `skills/process-manager/scripts/process_manager/state.py`
- `skills/process-manager/scripts/process_manager/manager.py`
- `skills/process-manager/scripts/process_manager/control_api.py`
- `skills/process-manager/scripts/manager_server.py`
- `skills/process-manager/scripts/pm_session.py`（新增）
- `skills/process-manager/scripts/pm_start.py`
- `skills/process-manager/scripts/pm_restart.py`
- `skills/process-manager/tests/test_sessions.py`（新增）
- 与 start/restart/manager lifecycle 直接相关的现有 tests

禁止修改：

- 默认 persistent、未声明 ownership 的 start 或 service restart 变更 ownership
- session close/expiry 的第二套 stop engine；必须复用 STG-02 owner finalizer
- 只删除 session file、不验证 run owners 的“清理”
- session holder 中保存 token、口令、用户名秘密或平台 capability

机器合同字面量：

- Allowed：`skills/process-manager/tests/**`
- Forbidden：`default persistent or start without declared ownership`
- Forbidden：`second session cleanup engine instead of the owner finalizer`
- Forbidden：`session closed before every owned run owner empty`
- Forbidden：`secret or platform capability stored in session holder`

Entry conditions：

1. STG-02 owner-first finalizer、persisted reconciliation 和 manager restart 已通过。
2. session closed schema、TTL 范围、state transitions 与 central index 已按 ART-03 冻结。
3. Skill 默认 validation TTL 1800 秒和 persistent opt-in 已确认。

实施步骤：

1. 实现 session repository/index 与 `open/renew/status/close` closed operations，使用 atomic state transition。
2. `pm_start` 强制 `--session-id` 与 `--persistent` 二选一；manager 校验 session open、未过期和 workspace digest。
3. run record 持久化 session/persistent ownership；service restart 原样继承。
4. session close 将 state 置为 terminating，逐 run 调用统一 finalizer，owner empty 后 closed。
5. manager 增加 bounded sweeper：固定小批次扫描 session index，处理 expired/terminating，异常结构化记录且不杀 manager。
6. manager startup/ensure 在开放 start 前执行一次有界 session/run reconciliation。
7. `close --stop-manager-if-idle` 由 manager 在同一 control lock 下关闭 intake、复核 generation/ownership 并条件 shutdown；并发新 work 获胜时返回 manager retained，不允许客户端 check-then-stop。
8. 增加多 session 隔离、persistent isolation、expiry、close interruption、renew race、sweeper exception、idle-stop 与 concurrent-open/start race tests。

失败与恢复：

- close 中断时持久 state 继续保持 terminating；重复 close 或 sweeper 只推进同一 finalizer。
- expired session 不再接受 renew/start；cleanup 未完成返回 `session_cleanup_pending`，不得伪造 closed。
- sweeper 每轮有数量和时间预算；单个失败不能阻塞其他 session，也不能静默吞错。

Exit conditions：

1. 多 session、persistent run 与无关进程隔离测试通过。
2. normal close 和 expiry 都只在 owner empty 后 `cleanupVerified=true`。
3. 未声明 ownership 的 start 稳定失败，service restart 不改变 ownership。
4. close 中断可由下一 ensure/sweeper 恢复，无重复 cleanup side effect。
5. focused code-review receipt 无 blocking/major finding。

### STG-04：资源治理与 Runtime Security

- Depends on：`STG-03`
- Requirement IDs：`REQ-07`、`REQ-08`、`REQ-12`、`REQ-13`
- Acceptance IDs：`AC-11`、`AC-12`、`AC-13`、`AC-14`、`AC-16`
- Nonfunctional IDs：`NFR-03`、`NFR-05`、`NFR-06`、`NFR-07`、`NFR-08`、`NFR-09`
- Validation IDs：`VAL-02`、`VAL-05`、`VAL-06`、`VAL-09`、`VAL-13`
- Risk：`high`
- Commit expectation：`stage`，需显式 commit 授权

允许修改：

- `skills/process-manager/scripts/process_manager/resources.py`（新增）
- `skills/process-manager/scripts/process_manager/config.py`
- `skills/process-manager/scripts/process_manager/models.py`
- `skills/process-manager/scripts/process_manager/state.py`
- `skills/process-manager/scripts/process_manager/manager.py`
- `skills/process-manager/scripts/process_manager/control_api.py`
- `skills/process-manager/scripts/process_manager/runtime.py`
- `skills/process-manager/scripts/process_manager/errors.py`
- `skills/process-manager/scripts/process_manager/platforms/base.py`
- `skills/process-manager/scripts/process_manager/platforms/windows_acl.py`
- `skills/process-manager/scripts/process_manager/platforms/windows.py`
- `skills/process-manager/scripts/process_manager/platforms/posix.py`
- `skills/process-manager/scripts/process_manager/platforms/linux.py`
- `skills/process-manager/scripts/process_manager/platforms/macos.py`
- `skills/process-manager/scripts/pm_doctor.py`
- `skills/process-manager/scripts/pm_prune.py`
- `skills/process-manager/scripts/pm_list.py`
- `skills/process-manager/tests/test_resources.py`（新增）
- `skills/process-manager/tests/test_runtime_security.py`（新增）
- 与 config/state/platform/doctor/prune 直接相关的现有 tests

禁止修改：

- 删除 active/terminating run、全 workspace 扫描、无限日志或无限 poll/wait
- Windows SDDL exact string/regex 作为 ACL 真相、错误 message 关键词作为权限分类
- 自动 elevation、修改 workspace 外 ACL/mode、放宽 broad principal 权限
- 在 status 中 remediation，或在无法证明 owner empty 时重建 runtime

机器合同字面量：

- Allowed：`skills/process-manager/tests/**`
- Forbidden：`automatic deletion of active or terminating runs`
- Forbidden：`unbounded scan, logs, wait or poll`
- Forbidden：`SDDL string equality, regex or error text as ACL truth`
- Forbidden：`automatic elevation or status-time remediation`

Entry conditions：

1. STG-03 session/run ownership 与 finalizer 已稳定，GC 可准确识别 eligible terminal records。
2. resource defaults、usage 口径、quarantine/tombstone transaction 和 security state taxonomy 已冻结。
3. Windows ACL native API 与 POSIX owner/mode/path constraints 已通过 focused design review。

实施步骤：

1. 为 config 增加 closed `limits.maxActiveRuns/maxRetainedBytes` 与 `history.maxInactive/maxAgeSeconds/deleteRunDirs`，验证合理范围。
2. 实现精确 usage accounting 与 start admission：先有界 reconcile/GC，再检查 active/bytes，超限返回稳定 error 和 usage/limit。
3. 实现 automatic GC planner：age 优先、count 次之、bytes 最后，只选择 cleanup-verified terminal records。
4. 实现 quarantine → compact tombstone atomic commit → delete quarantine；失败保留 cleanup evidence，可重试。
5. `pm_prune` dry-run/apply 复用同一 planner/transaction，不复制候选规则。
6. status/doctor 输出 active/terminating/open/expired/inactive/retainedBytes/cleanupPending/overBudget 等平台中立 summary。
7. Windows ACL 改为读取 owner、DACL、descriptor control、ACE 和 effective rights；accept inherited-equivalent，拒绝 broad access，verify-first/remediate 分离。
8. POSIX 验证 current uid、0700/0600、lstat/no symlink/path containment，精确映射 EACCES、read-only 和 unsupported ownership。
9. doctor 复用 resolver/security evidence，不在 PMError 时硬写 supervisor ready；外层无 JSON 错误只归为 launcher environment。
10. 增加 count/age/bytes、rollback、cleanup failure、admission race、ACL equivalence/broad deny/permission/unverifiable/no-mutation tests。

失败与恢复：

- GC 在 state commit 前失败则恢复 quarantine；commit 后删除失败保留 tombstone/cleanup pending，不重新暴露为 active。
- usage 无法可靠计算时 fail closed 或标记 environment_unverifiable，不把未知当作 0。
- ACL remediation 失败返回原 Win32/POSIX category 和受限 diagnostics；不继续 ensure、不请求管理员。

Exit conditions：

1. active/count/age/bytes 和 cleanup pending 均有硬上限与公开证据。
2. GC 从不选择 active/terminating，事务中断可恢复，tombstone 保留关键诊断。
3. Windows inherited-equivalent ACL 不再误报，broad allow/rights不足/denied/unverifiable 精确分类。
4. status 无 mutation；doctor 不泄密、不硬编码 ready、不把外层环境错归为 ACL。
5. focused code-review receipt 无 blocking/major finding。

### STG-05：Public Contract、消费者、Eval 与 CI 原子迁移

- Depends on：`STG-04`
- Requirement IDs：`REQ-09`、`REQ-10`、`REQ-11`、`REQ-13`
- Acceptance IDs：`AC-10`、`AC-14`、`AC-15`
- Nonfunctional IDs：`NFR-01`、`NFR-06`、`NFR-09`、`NFR-10`
- Validation IDs：`VAL-01`、`VAL-07`、`VAL-08`、`VAL-11`、`VAL-12`、`VAL-13`
- Risk：`high`
- Commit expectation：`stage`，需显式 commit 授权

允许修改：

- `skills/process-manager/scripts/pm_manager.py`
- `skills/process-manager/scripts/pm_session.py`
- `skills/process-manager/scripts/pm_init.py`
- `skills/process-manager/scripts/pm_validate.py`
- `skills/process-manager/scripts/pm_start.py`
- `skills/process-manager/scripts/pm_ready.py`
- `skills/process-manager/scripts/pm_status.py`
- `skills/process-manager/scripts/pm_logs.py`
- `skills/process-manager/scripts/pm_list.py`
- `skills/process-manager/scripts/pm_prune.py`
- `skills/process-manager/scripts/pm_stop.py`
- `skills/process-manager/scripts/pm_restart.py`
- `skills/process-manager/scripts/pm_doctor.py`
- `skills/process-manager/scripts/pm_health.py`（删除）
- `skills/process-manager/scripts/pm_shutdown.py`（删除）
- `skills/process-manager/SKILL.md`
- `skills/process-manager/references/**`
- `skills/process-manager/examples/**`
- `skills/process-manager/tests/**`
- `evals/process-manager/**`
- `skills/complex-coding-planner/**` 中直接引用 process-manager workflow 的文件
- `evals/complex-coding-planner/**` 中对应 contract/eval
- `skills/complex-coding-executor/**` 中直接引用 process-manager workflow 的文件
- `evals/complex-coding-executor/**` 中对应 contract/eval
- `skills/electron-ui-verifier/**` 中直接引用 process-manager workflow 的文件
- `evals/electron-ui-verifier/**` 中对应 contract/eval
- `.github/workflows/process-manager-platforms.yml`

禁止修改：

- legacy health/shutdown wrapper、旧 schema parser、双 read/write 或 status-start fallback
- Planner/Executor/Electron 中复制 manager state machine、读取内部 runtime 文件或自行猜 ACL
- 与 PM 集成无关的其它 Skill 行为、GitLab 能力、Reviewer contract 或仓库范围格式化
- CI secrets、自动 remote write、自动 elevation 或普通 branch 过滤

机器合同字面量：

- Allowed：上方逐项列出的 `skills/process-manager/scripts/pm_*.py` 公共脚本；`plan-contract.json` 使用明确文件路径而非 glob
- Allowed：`skills/complex-coding-planner/**`
- Allowed：`evals/complex-coding-planner/**`
- Allowed：`skills/complex-coding-executor/**`
- Allowed：`evals/complex-coding-executor/**`
- Allowed：`skills/electron-ui-verifier/**`
- Allowed：`evals/electron-ui-verifier/**`
- Forbidden：`legacy health or shutdown wrapper, old schema parser or status-start fallback`
- Forbidden：`consumer copy of manager state machine, internal runtime reads or ACL guesses`
- Forbidden：`unrelated Skill behavior, Reviewer contract or repository-wide formatting`
- Forbidden：`CI secrets, remote mutation, elevation or ordinary branch filter`

Entry conditions：

1. STG-01..04 内部 contract、session/resource/security 能力全部通过，public cutover 不再依赖未实现路径。
2. 旧 public references、scripts、eval、consumer call sites 已形成完整 inventory。
3. current-only deletion 与 consumer migration 必须能在一个 stage/commit 内完成。

实施步骤：

1. 将所有公共脚本迁移到 explicit context 和统一 JSON envelope/error taxonomy。
2. 固定 manager commands 为 `ensure/status/restart/stop`，新增 session facade；service `pm_restart.py` 保持独立语义。
3. 删除 `pm_health.py`、`pm_shutdown.py`，同步 CLI discovery、tests、docs、examples 和 static allowlist。
4. 重写 Process Manager Skill 默认流程：init（必要时）→ ensure → session open → start/verify → finally session close，可选 idle manager stop。
5. 定义中断恢复：先 status/recommended action；starting/stopping 有界等待；stale/unresponsive 只按精确证据 restart；无 envelope 环境错误走 direct/non-profile invocation。
6. Planner/Executor 对长运行验证使用 session/finally close；finite command 不启动 manager；恢复时不反复 status/start 或自行 ACL 诊断。
7. Electron verifier 使用同一 ensure/session 生命周期，应用退出和 verifier teardown 都走 session finalizer。
8. 扩展 PM unit/eval/static/native smoke，加入 current-only stale-reference scan、public help/schema、并发 ensure、restart、session、resource 和 error cases。
9. 扩展 Planner/Executor/Electron contract/eval，证明三个消费者没有旧入口或重复 cleanup logic。
10. 更新现有三平台 workflow，普通 branch 全执行，上传与 commit/attempt 绑定的 machine evidence。

失败与恢复：

- 任一 consumer 尚未可用时不得删除旧入口或提交半迁移；整个 STG-05 工作树作为一个原子边界修复/回退。
- 不以 compatibility wrapper 解决测试失败；必须修正 current source、fixtures、docs 和 eval 到唯一 contract。
- hosted CI 在未推送前标记 pending，不用本地结果冒充三平台完成。

Exit conditions：

1. 仓库 current scope 无 `pm_health.py`、`pm_shutdown.py`、status-start happy path、generic manager_offline 或无 ownership start。
2. Process Manager、Planner、Executor、Electron unit/eval/static 全部通过。
3. docs、help、examples 与 public closed schema 一致，manager restart 与 service restart 无歧义。
4. workflow 对所有 branches 运行且无 secret/remote mutation/elevation 扩张。
5. focused code-review receipt 无 blocking/major finding。

### STG-06：三平台验证、最终审查与资源清场

- Depends on：`STG-05`
- Requirement IDs：`REQ-11`、`REQ-12`
- Acceptance IDs：`AC-16`、`AC-17`、`AC-18`
- Nonfunctional IDs：`NFR-01`、`NFR-02`、`NFR-03`、`NFR-04`、`NFR-05`、`NFR-06`、`NFR-07`、`NFR-08`、`NFR-09`、`NFR-10`
- Validation IDs：`VAL-02`、`VAL-07`、`VAL-08`、`VAL-09`、`VAL-10`、`VAL-11`、`VAL-12`、`VAL-14`、`VAL-15`、`VAL-16`、`VAL-17`
- Risk：`high`
- Commit expectation：`final`，需显式 commit 授权

允许修改：

- STG-01..05 和 ART-04 批准的文件，仅用于修复 required validation 直接证明的根因
- `.github/workflows/process-manager-platforms.yml`
- Process Manager/consumer tests、eval、docs 和 task-local validation/review artifacts
- final review 指出的 approved-scope 最小修复

禁止修改：

- 无 failing evidence 的生产代码调整、新 feature scope、新依赖、兼容层或平台公开接口
- 未授权 external write、remote push、管理员/root 操作或用户机器 ACL 修改
- 把本地 Windows、mock adapter 或旧 workflow run 声称为当前三平台通过
- final cleanup 通过删除失败证据、active/terminating state 或用户进程来“变绿”

机器合同字面量：

- Allowed：`all files approved by STG-01 through STG-05 and ART-04 for directly evidenced fixes`
- Allowed：`task-local execution, validation, review and observation artifacts`
- Allowed：`minimal fixes required by final review within approved scope`
- Forbidden：`production change without failing required validation evidence`
- Forbidden：`new scope, dependency, compatibility layer or public platform interface`
- Forbidden：`unauthorized external write, push or elevation`
- Forbidden：`claiming hosted success without current commit evidence`
- Forbidden：`deleting failure evidence or user processes to fake cleanup`

Entry conditions：

1. STG-05 current-only public contract 与三个消费者已完成并提交 stage review。
2. 所有本地 required commands 可重建，工作树仅含 ART-04 允许范围和任务证据。
3. GitHub hosted validation 由用户推送当前 commit 后运行；Agent 只读取证据，不自行推送。

实施步骤：

1. 运行 PM 全量 unit/component、eval/static、local OS public lifecycle 与 crash/restart recovery smoke。
2. 运行 Planner/Executor/Electron 回归，检查 session finally close、finite-command bypass 与 interrupted recovery。
3. 用户推送后读取 Windows/Ubuntu/macOS matrix 和 Ubuntu delegated cgroup job 的当前 commit evidence。
4. 对任何跨平台失败先定位共同 contract 根因，再做 approved-scope 最小修复；不得以 platform skip 掩盖 required behavior。
5. 使用 `complex-coding-reviewer` 执行 final-integration code-review，receipt 绑定当前 target/context/validation claims。
6. 执行 final cleanup：close task sessions、stop owned runs、必要时 stop idle manager，验证 owner/bootstrap/runtime tmp 均无残留。
7. 运行 changed-path allowlist、stale reference、JSON/YAML/static 和 `git diff --check` 审计。
8. 输出真实交付摘要，列出通过、待用户运行或因环境未观察的证据与 residual risks。

失败与恢复：

- 三平台/ delegated job 任一 required check 未通过，STG-06 不得完成；修复后需要匹配新 commit 的全量证据。
- final review 存在 blocking/major finding 或 blocking verification gap 时不得完成或提交 final。
- cleanup 无法证明 owner empty 时保留 pending evidence，停止交付，禁止删除 state 伪造 clean。

Exit conditions：

1. `VAL-01..VAL-17` required evidence 全部存在、当前且通过。
2. Windows/Ubuntu/macOS 与 delegated cgroup 证据绑定最终 commit/attempt。
3. final receipt passed，无 blocking/major finding 或 blocking gap。
4. 无 active/terminating/cleanup pending、manager/bootstrap/task tmp residue；无关进程存活。
5. diff allowlist、stale-reference 与 `git diff --check` 通过，交付声明不超过证据。

## Stage DAG 与事务边界

```text
STG-01 Context + Resolver + Ensure
  -> STG-02 Restart + Reconciliation
  -> STG-03 Session Lease + Finalizer
  -> STG-04 Resource + Runtime Security
  -> STG-05 Public Contract + Consumers
  -> STG-06 Three-platform + Final Integration
```

阶段线性执行，因为每个后续 public behavior 都依赖前一阶段的不变量。Stage 内可以并行阅读或运行独立测试，Git status/add/commit 必须串行。STG-05 是 current-only 原子 cutover，不能把“脚本已变、消费者未变”或“消费者已变、脚本未变”作为可提交/可恢复状态。

## 验证门（Validation Gates）

| ID | Kind | Required outcome | Evidence |
| --- | --- | --- | --- |
| VAL-01 | structure | no-bytecode CLI/static JSON/YAML/Python contract 通过 | `artifacts/validation/structure-syntax.json` |
| VAL-02 | test | Process Manager 全量 unit/component 通过 | `artifacts/validation/process-manager-unit-tests.txt` |
| VAL-03 | test | lifecycle/concurrency/fault state table 通过 | `artifacts/validation/manager-lifecycle-tests.txt` |
| VAL-04 | test | session lease/expiry/isolation/finalizer 通过 | `artifacts/validation/session-tests.txt` |
| VAL-05 | test | active/count/age/bytes/GC/admission 通过 | `artifacts/validation/resource-tests.txt` |
| VAL-06 | test | runtime security/ACL/POSIX/error classification 通过 | `artifacts/validation/runtime-security-tests.txt` |
| VAL-07 | eval | Process Manager capability/workflow eval 通过 | `artifacts/validation/process-manager-evals.json` |
| VAL-08 | lint | current-only static contract 和 stale reference scan 通过 | `artifacts/validation/process-manager-static.json` |
| VAL-09 | smoke | 当前本地 OS public lifecycle 通过并 cleanup verified | `artifacts/validation/native-smoke.json` |
| VAL-10 | smoke | manager crash/restart/recovery/session expiry 通过 | `artifacts/validation/manager-recovery-smoke.json` |
| VAL-11 | test | Planner/Executor PM lifecycle regression 通过 | `artifacts/validation/planner-executor-regression.json` |
| VAL-12 | test | Electron verifier PM integration regression 通过 | `artifacts/validation/electron-verifier-regression.json` |
| VAL-13 | review | 每阶段 code-review receipt 当前且无 blocking/major | `artifacts/validation/stage-review-summary.json` |
| VAL-14 | hosted | GitHub Windows/Ubuntu/macOS matrix 通过 | `artifacts/validation/github-platform-matrix.json` |
| VAL-15 | hosted | Ubuntu delegated cgroup lifecycle 通过 | `artifacts/validation/github-delegated-cgroup.json` |
| VAL-16 | review | final-integration receipt passed | `artifacts/validation/final-review-summary.json` |
| VAL-17 | audit | final cleanup、stale refs、allowlist、diff check 通过 | `artifacts/validation/final-cleanup-audit.json` |

详细命令、fault matrix、证据等级、平台覆盖与 cleanup 断言见 ART-05。所有命令默认 `python -u -X utf8 -B` 或 `PYTHONDONTWRITEBYTECODE=1`，不得因验证产生 `__pycache__`。需要长运行服务的 native smoke 必须通过 process-manager 新 public workflow 管理，并在 finally 中关闭 session；实施该能力前的 focused unit tests 不启动长期服务。

## 环境（Environment）

- Workspace environment source：`.harness/environment.md` 与当前 repository/toolchain observation。
- Python：3.12，所有确定性命令使用 UTF-8、unbuffered 和 no-bytecode mode。
- Windows 普通验证不得要求管理员；ACL remediation 只作用于当前 workspace 的 PM state root。
- Ubuntu hosted delegated cgroup 可使用 workflow 内 scoped `sudo systemd-run`，但公共 Skill 和本地默认流程不要求 root。
- macOS 使用 hosted runner 验证 launchd/process-group 行为，不假设本地 Windows 可以替代。
- 临时 workspace、session、run 与 evidence path 都必须位于 task 或 runner temp，结束后验证清场。

## Git 上下文（Git Context）

- Main / working branch：`harness/feature`，规划时相对 `origin/harness/feature` ahead 1。
- Task type / branch action：feature planning；不创建或切换新 branch。
- Worktree known changes：仅允许本 task Harness bundle；实施时重新记录用户并行改动。
- Commit authorization：`not requested`。
- External push authorization：`not requested`；hosted evidence 由用户手动推送后提供。
- Branch closure：本规划不关闭或合并 branch。

同一仓库 Git 命令串行；只读状态优先禁用 optional locks，diff 禁用 index refresh。不自动 stash、rebase、reset、checkout 或覆盖未知改动。遇到 lock 只按精确路径、稳定性与进程 evidence 处理。

## 工具（Tooling）

| Tool | Purpose | Stage | Status | Risk / authorization |
| --- | --- | --- | --- | --- |
| `apply_patch` | 实现与文档定点修改 | STG-01..06 | available | workspace write；无需提权 |
| Python 3.12 / unittest | unit、fault、eval、static | STG-01..06 | available | no-bytecode；finite commands |
| process-manager public CLI | native service lifecycle 与 cleanup | STG-05..06 | planned target | 在新 contract 可用后自举验证 |
| Git | status/diff/authorized commit | all | available | commit 需单独授权，Git 命令串行 |
| GitHub Actions | 三平台与 delegated evidence | STG-06 | user-push required | Agent 不自动 push；workflow scoped sudo only |
| complex-coding-reviewer | stage/final code-review | STG-01..06 | available | 只审查，不自动修改目标 |

## 长期进程管理（Process Manager Gate）

- Needs long-running process：`yes`，仅 native lifecycle、manager recovery 和 Electron integration smoke；unit/eval/static/build 直接运行。
- STG-01..04 在新版 public contract 尚未 cutover 前以 pure unit/fault tests 为主，不为测试手写后台 shell。
- STG-05..06 使用目标 workflow：`pm_manager ensure` → `pm_session open` → `pm_start` → readiness/verification → finally `pm_session close --stop-manager-if-idle`。
- Required evidence：authenticated manager identity、operation/session ID、processKey、ready、bounded logs、graceful/force result、owner-empty、cleanupVerified、bootstrap cleanup。
- manager state 不确定时只读取 closed status/recommended action；无 JSON envelope 的 shell/profile error 不触发 ACL remediation。
- 新 contract 无法自举或 cleanup 无法证明 owner empty 时立即阻塞，不用 `Start-Process`、后台 shell 或任意 PID kill 绕过。

## 文档（Documentation）

- `SKILL.md` 保持入口精炼，只描述 ensure/status/restart/doctor 选择、session 默认流程、环境错误边界和脚本索引。
- state table、security、platform backend、service schema、故障恢复和 resource policy 下沉到 `references/**`。
- Process Manager docs、Planner/Executor/Electron integration docs、eval fixtures 与 CI contract 在 STG-05 同步更新。
- 是否更新 root README/CHANGELOG 由 ART-04 当前范围决定；若实施发现用户可见能力索引必须修改，需先 amendment 扩大 change map。

## 文件写入策略（File Write Strategy）

- 大文件优先局部 patch；超过 500 行或需重写长章节时按完整章节、类或函数分段，禁止无关整文件重排。
- new modules 按 context/lifecycle/session/resource semantic boundary 分文件，不创建一次性场景脚本集合。
- 新增解释性代码注释使用中文，只说明不明显的并发、finalizer、安全或平台取舍。
- 每阶段完成后完整重读 changed files，检查 JSON/YAML、ID/reference、EOF、stale text 和 diff noise。

## 问题和覆盖项（Questions And Overrides）

| ID | Blocking | Status | Decision | Applied to |
| --- | --- | --- | --- | --- |
| Q-01 | no | closed | 不兼容旧 runtime/public script，采用 current-only 原子迁移 | STG-05、NFR-10 |
| Q-02 | no | closed | 普通 Windows 使用不需要管理员，ACL 问题按 semantic evidence 分类 | STG-04、AC-13/14 |
| Q-03 | no | closed | manager restart 停止 owned services但不自动恢复 | STG-02、AC-05/16 |
| Q-04 | no | closed | hosted CI 由用户推送，Agent 不执行 remote write | STG-06、VAL-14/15 |
| Q-05 | no | closed | revision 2 仅将路径与说明拆分为 Executor 可规范化的 machine scope；REQ/AC/NFR、DAG、VAL、功能设计和授权边界不变 | 全部 STG、Plan Amendment Gate |

## 方案质量门禁（Plan Quality Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| 关键判断有证据等级 | passed | ART-01 与 Context evidence table |
| Research Gate 完成 | passed | ART-01，官方 Windows/Linux/macOS/Kubernetes/Python/GitHub 来源 |
| Standards Discovery Gate 完成 | passed | ART-02 |
| Development Quality Gate 完成 | passed | ART-02/03 与本文件 quality table |
| Dependency Selection Gate 完成 | passed | mode none，零 decision、零 dependency artifact |
| 候选方案充分比较 | passed | Options A/B/C |
| 影响面与 current-only cutover 完整 | passed | ART-04 与 Impact Matrix |
| 每阶段独立验证且 DAG 无循环 | passed | STG-01..06、ART-05/06 |
| reapproval/stop/authorization 清晰 | passed | plan-contract 与本文件 |
| formal review handoff 可重建 | passed | ART-07 path、target/context/receipt workflow |

质量结论（Quality result）：`passed`。

## 正式方案审查（Formal Plan Review）

- Producer：`complex-coding-planner` 负责生成和修复 bundle，不自签正式 verdict。
- Profile：`plan-review`。
- Scope：`managed-plan`。
- Review brief：`artifacts/reviews/plan-review-brief.json`，approval-included，声明全部 requirement/constraint/claim/risk refs。
- Current receipt：`artifacts/reviews/plan-review-attempt-2.json`。
- Validator：`skills/complex-coding-reviewer/scripts/review_validate.py`。
- Canonical result：只读取当前 JSON receipt；approval checker 重建 target/context 并校验 coverage、risk、gaps、lineage 与 freshness，计划正文不复制 verdict/finding 状态。
- Retry：若正式审查发现问题，先修 plan bundle，再生成递增 attempt 和 `supersedes_review_id`；旧 receipt 保留。

## 生产者就绪门禁（Producer Readiness Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| Goal、REQ、AC、NFR 清楚 | passed | ART-06、plan-contract |
| 本地代码、调用方和 CI 上下文已读 | passed | ART-01/04 |
| Research/Standards/Quality/Dependency gates 已完成 | passed | ART-01/02/03 |
| Options、Decision、Impact 已记录 | passed | execution-plan 与 ART-03/04 |
| 六阶段合同、验证和 rollback 已细化 | passed | execution-plan、plan-contract、ART-05/06 |
| 环境、Git、tooling、long process 与权限已确认 | passed | 本文件对应章节 |
| 文档和 file-write strategy 已确认 | passed | 本文件与 ART-04 |
| blockers 已关闭且 residual risk 可声明 | passed | Questions、stop conditions |
| formal review handoff 已准备 | passed | ART-07/08 reserved paths |

就绪结论（Readiness result）：`ready_for_review`，等待正式 Reviewer receipt 与 approval checker。

## 方案批准（Plan Approval）

- Status：`not_requested`。
- Requested scope：批准 revision 2 implementation，按 STG-01..06 执行；STG-01 从当前未提交实现继续。
- Stage/final commit authorization：请求在 revision 2 重新确认并延续 revision 1 已获用户授权的阶段/最终自动提交；新 attestation 写入前仍按 `not_authorized` fail closed。
- External write/push authorization：`not_authorized`。
- Elevated tool authorization：`not_authorized`。
- Documentation authorization：随 implementation 仅限 ART-04 scope；超范围需 amendment。

## 方案变更门禁（Plan Amendment Gate）

需要重新批准：

1. manager state set、operation/session schema、owner-empty 终态语义或 current-only public contract 发生实质变化。
2. Stage DAG、required validation、allowed/forbidden scope、默认资源上限或 consumer migration 范围发生变化。
3. 需要第三方依赖、系统服务、数据库、平台公开接口、兼容层、auto service restore、外部写入或提权。
4. 需要修改 ART-04 之外的其它 Skill 公共行为，或无法在一个 stage 原子迁移三个 consumers。
5. 三平台证据证明选定 owner/security 方案不可行，需要改变平台架构而非最小修复。
6. active task pointer 冲突、用户改动或 baseline 漂移使当前计划不能安全执行。

已触发 amendment：revision 1 的 `allowed_changes` 含路径与说明混合字面量，Executor 以 `RUN_STATE_REVIEW_SCOPE_UNREPRESENTABLE` fail closed；revision 2 只规范化全部 stage 的 machine path，并保留 revision 1 archive、ledger 与未提交实现。局部实现修正只有在不改变 REQ/AC/NFR、Stage Contract、required validation、scope、dependency、权限和公共行为时才允许记录为 executor decision。

停止条件：用户未批准或暂停；任一 reapproval trigger；owner/runtime/identity/context 无法安全验证；required validation 或 blocking review gap 无法关闭；需要未授权 dependency/external write/push/elevation；active pointer 冲突；无法生成当前目标绑定证据。

## Artifact Index

| ART | Path | Purpose |
| --- | --- | --- |
| ART-01 | `artifacts/research/process-manager-reliability-research.md` | 当前缺口、官方来源、方案比较、依赖结论 |
| ART-02 | `artifacts/standards/process-manager-standards-index.md` | 项目、Python、OS、security、CI 规范 |
| ART-03 | `artifacts/architecture/control-plane-convergence.md` | context/state/operation/session/resource/security 目标架构 |
| ART-04 | `artifacts/architecture/change-map.md` | 文件级允许、删除、消费者与 CI 影响面 |
| ART-05 | `artifacts/validation/validation-strategy.md` | validation commands、fault matrix、hosted evidence |
| ART-06 | `artifacts/traceability/traceability-matrix.md` | GOAL/REQ/AC/NFR/STG/VAL/ART 闭环 |
| ART-07 | `artifacts/reviews/plan-review-brief.json` | Reviewer managed-plan context brief |
| ART-08 | `artifacts/reviews/plan-review-attempt-2.json` | 当前 revision 的正式 plan-review receipt |

## Executor Handoff

Executor 获得 approval 后必须：先验证 attestation 与 active pointer；按 STG-01..06 逐阶段执行；每阶段只改 allowed paths；执行 required validation 和 `complex-coding-reviewer` code-review；有 blocking/major finding 时修复并复审；只在用户授权下提交；最终 hosted evidence、final review 与 cleanup 全部闭合后才能完成任务。

- Planner checker：draft 后生成正式 receipt，再执行 approval mode。
- Open blocking decisions：none。
- Requested implementation authorization：yes，尚未请求。
- Requested commit/external-write/elevated authorization：no。
- Residual risks：hosted OS 差异、用户机器 ACL/launchd/systemd 环境、current-only cutover blast radius；均由 STG-05/06 required evidence 和 stop conditions 控制。

本规划不授权任何实现、commit、push、外部写入或提权。Planner 在 draft check、正式 plan-review、approval check 和 active pointer 激活后停止，等待用户批准 implementation。

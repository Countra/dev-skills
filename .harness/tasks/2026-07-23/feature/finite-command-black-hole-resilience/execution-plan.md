# 有限命令黑洞与取消稳定性补强

## 目标与完成标准

在不引入新后台服务、不扩大 Harness 制品的前提下，补强 Planner/Executor 对有限命令的选择、观察、超时与清理约定，使测试、构建、系统 provider 查询和进程诊断不会再因一次无界执行阻塞整个任务。

完成后应满足：

- 遵守 Planner/Executor 路由的命令中，凡有卡死历史、可能静默、访问 CIM/WMI 等系统 provider、枚举进程或运行测试/构建的有限命令，在执行前必须具有明确 wall-clock deadline；宿主不能证明会按时回收受支持的进程边界时，必须实际通过现有 `harness_bounded_command.py` 启动。
- helper 启动后立即报告已启动状态，并按固定间隔输出不含命令参数、环境变量或秘密的 heartbeat；静默命令仍可判断“正在运行、已运行多久、何时到期”。
- deadline、Ctrl+C、SIGTERM/SIGHUP（适用平台）或 Windows 取消路径都进入同一有界清理流程，按确定优先级保留 `124/125/126/130` 退出语义；Windows 只处理 Job/tracked handles，POSIX 只处理本次 PGID 内的进程。
- PowerShell 诊断优先使用已知 PID、Process Manager ownership 和 provider-side filter；不再直接运行无界 `Get-CimInstance Win32_Process | Where-Object ...` 全量查询。
- 本地完成门证明当前平台的 silent timeout、取消和受支持进程边界回收在 deadline 加 grace 后及时结束；用户推送后的 Windows、Ubuntu、macOS CI 是后置跨平台验收。没有远端结果时不声称三平台真实通过。

## 范围与非目标

主要修改位于：

- `skills/complex-coding-planner/`：规划和调研命令也遵循有限命令分级，并要求 validation 使用真实 timeout。
- `skills/complex-coding-executor/`：收紧执行约定，增强已有 bounded-command helper 与测试。
- `evals/complex-coding-workflow/`、必要时的 `evals/process-manager/`：锁定命令路由和长期/有限进程边界。
- `.github/workflows/planner-executor.yml`：沿用现有三平台 bounded-command job，必要时只调整测试预算或拆分，不上传 artifact。
- `README.md`、`CHANGELOG.md`：同步用户可见能力与边界。

非目标：

- 不把普通测试、构建、lint 或一次性诊断交给 Process Manager。
- 不增加 shell 全局 hook、后台 daemon、新生产 Python 文件、新 JSON 状态或逐命令日志。
- 不保证抵抗操作系统崩溃、机器断电或不可捕获的 POSIX `SIGKILL`；也不把主动 `setsid`、double-fork、daemonize 或 Windows breakaway 后逃离受控边界的进程声称为已回收。需要脱离前台的命令必须改用 foreground 参数，真正长期服务交给 Process Manager。
- 不为所有快速文件读取和 Git 查询强制增加 Python 包装；宿主已有可靠短 deadline 时直接使用宿主能力。

## 现状与根因

仓库已经有跨平台 `harness_bounded_command.py`：Windows 使用 Job Object，Linux/macOS 使用独立 process group，并能在自身 timeout 后清理子进程树。现有三平台单测也覆盖 silent timeout 和 child reclaim。因此本次问题不是“完全没有超时器”，而是保护未形成稳定入口：

1. Executor 当前只在“宿主 deadline 不可靠、命令有卡死历史或可能静默”时建议使用 helper，仍把识别与执行分散给 Agent；示例命令被直接执行后，helper 无法补救。
2. helper 使用一次 `process.wait(timeout=...)` 长等待，只在结束、超时或异常后输出摘要。命令不产生日志时，用户和 Agent 无法区分正常静默、provider 卡死或工具会话失联。
3. helper 只显式处理 `KeyboardInterrupt`，没有把宿主常用的 SIGTERM/SIGHUP 等取消路径收口到同一清理逻辑；子进程还会继承 stdin，自动化命令可能等待交互输入。
4. 示例先全量枚举 `Win32_Process` 再在客户端按名称和 CommandLine 过滤，扩大了 WMI/CIM provider 工作量；脚本块中的当前对象应为 `$_`，给出的 `$*` 也不是正确写法。
5. Skill 无法修改 Codex 宿主本身，也不能拦截未遵守 Skill 的任意终端调用。仓库内保证明确限定为“实际通过 helper 启动的受支持命令”：语义 eval 只能检查 Executor 约定和期望调用形状，不能证明宿主真实 tool call；helper 集成测试只证明进入该入口后的 deadline 与清理。宿主或 Agent 绕过 Skill 仍是明确剩余风险。

## 调研结论与关键决策

- Microsoft 的 `Get-Process` 支持按 `-Id` 精确查询；已知 PID 时不需要扫描所有进程。[Get-Process](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/get-process?view=powershell-7.6)
- `Get-CimInstance` 支持 provider-side `-Filter`、属性投影 `-Property` 和 `-OperationTimeoutSec`。provider timeout 用于限制单次 CIM 响应，但不能替代包住整个 PowerShell 进程树的 wall-clock deadline。[Get-CimInstance](https://learn.microsoft.com/en-us/powershell/module/cimcmdlets/get-ciminstance?view=powershell-7.5)
- `Where-Object` 脚本块用 `$_` 表示当前 pipeline 对象；原示例中的 `$*` 应视为错误或转写问题。[Where-Object](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/where-object?view=powershell-7.5)
- Python 官方文档说明 `Popen` 的 `start_new_session` 可建立 POSIX session，timeout 只约束等待阶段，而且某些平台的进程创建本身不一定可中断。因此 helper 应保留宿主外层兜底，并避免网络路径上的可执行文件；不宣称单个 Python 进程能覆盖所有内核级卡死。[subprocess](https://docs.python.org/3/library/subprocess.html)
- Python signal handler 在主线程执行；等待循环需要周期返回 Python 控制流，才能稳定处理取消并输出 heartbeat。[signal](https://docs.python.org/3/library/signal.html)
- Windows Job Object 能把进程组作为单元管理，`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 在最后一个 handle 关闭时终止关联进程。保留当前 Job Object 路径，不改成名称扫描或自动提权。[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)

采用三层 deadline：

1. **查询层**：命令自身支持时设置 operation timeout，例如 CIM 查询 10 秒。
2. **进程层**：高风险有限命令由 bounded helper 设置 wall-clock timeout、grace、heartbeat 和进程树清理。
3. **宿主层**：Agent 使用不超过 10 秒的初始观察窗口获得可恢复 session，持续轮询但不重置总预算。宿主 deadline 至少为 `spawn budget 10 秒 + helper timeout + cleanup grace + force wait 5 秒 + margin 10 秒`；任何轮询都不能延长该绝对 monotonic deadline。

有限命令默认建议预算：精确诊断 20–30 秒，局部测试/lint 5 分钟，构建或完整套件 15 分钟。超过 30 分钟必须说明原因、拆分可能性和停止点，不能通过随意放大 timeout 掩盖静默。

针对给出的诊断，执行顺序固定为：

1. 先读取当前工具 session、已知 PID 或 `pm_manager.py status` / Process Manager ownership。
2. 只需要存活状态时使用 `Get-Process -Id <pid>`。
3. 必须读取 CommandLine 时，使用 `Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = <pid>" -Property ProcessId,Name,CommandLine -OperationTimeoutSec 10`。
4. 上述 CIM 命令仍由 bounded helper 以约 20 秒 wall deadline 调用 `pwsh -NoProfile -NonInteractive -Command ...`。
5. 没有 ownership 或 PID 时先承认信息不足；只有确需兜底时才使用 provider-side 名称过滤，并保持同样的双层 timeout，不能恢复到无界全量枚举。

## 实施阶段

### STG-01 收紧命令路由与诊断策略

- 在 Planner 与 Executor 的现有 `SKILL.md` / safety reference 中增加紧凑决策表：快速本地读取使用宿主短 deadline；测试、构建、系统 provider、进程枚举、包管理器和有卡死历史的命令必须使用可靠宿主 tree deadline 或 bounded helper；长期服务才使用 Process Manager。
- 将“已知 PID / ownership → provider-side filter → operation timeout → outer deadline”写成唯一推荐诊断路径，并明确禁止原样重试全系统 CIM/WMI 扫描、无界 session wait 和用 access denied 推导 ACL 故障。风险命令不得只在答复中建议 helper，必须由实际 tool call 以 helper 为最外层 program。
- 规划中的 required validation 继续使用 contract 的 `timeout_seconds`；Executor 在运行前必须把该值传给 `harness_bounded_command.py --timeout-seconds`，默认 `--grace-seconds 5`。`validations[].command` 采用受限的无 shell token grammar：只允许由单个 ASCII 空格分隔且自身不含空白的 program/args，禁止引号、管道、重定向、命令连接、变量展开和 shell glob 展开；`*` 等字符只作为目标程序收到的字面参数。checker 对该 grammar 做确定性校验，Executor 仅按单个 ASCII 空格拆分后传给 helper。需要 shell 语法的验证必须改为受版本控制的脚本，再把脚本路径作为单一 argv。返回 `124/125/126/130` 时 validation 必须记录 failed，不得只把 timeout 当作元数据。
- 增加 exact bad-command 语义用例，验证 Agent 会拒绝原示例、识别 `$_`、选择精确查询和 bounded wrapper，而不是启动 Process Manager 或自动提权。

### STG-02 增强有界执行器的观察与取消闭环

- 保留现有公共参数和退出码，新增可选 `--heartbeat-seconds`，默认 15 秒、合法范围 1–300 秒；不输出 command argv、环境或秘密。
- 启动前后立即向 stderr 打印并显式 `flush`；把单次长 `wait()` 改为基于 monotonic deadline 的短周期 poll/wait，定期输出 elapsed、remaining 和 root PID。heartbeat 不捕获或重定向 child stdout/stderr。heartbeat 或最终摘要遇到 BrokenPipe/关闭的输出端时只停用后续状态写入，不能跳过等待、清理或改变真实退出码。目标启动阶段由宿主 10 秒 spawn budget 兜底，helper 内 cleanup grace 与 force wait 分别保持独立上界。
- 自动化目标默认使用非交互 stdin，避免隐藏 prompt 无限等待；如确需交互，必须由显式参数选择且仍受同一 deadline 约束。
- 统一处理 Ctrl+C、SIGTERM、POSIX SIGHUP 和平台可用的 Windows break 信号。handler 只记录取消意图，主等待循环负责执行现有 graceful/force cleanup，避免在 signal handler 内做锁或复杂 I/O。Windows target 继续使用 `CREATE_NEW_PROCESS_GROUP`；有控制台时先尝试 `CTRL_BREAK_EVENT`，无控制台或发送失败时立即回退到 Job Object 终止，grace 后使用现有 exact tracked-handle force path。
- deadline、取消、正常父进程退出和清理失败继续复用现有 Windows Job / tracked handle 与 POSIX process-group 实现；任何路径都必须恢复 signal handler、关闭 native handle，并尽力给出一次最终人类摘要。POSIX 的稳定身份键固定为 `PID + start time + PGID + SID`，不把会在正常 `exec` 后变化的 executable path 用作相等条件：Linux 从 `/proc/<pid>/stat` 读取 start-time/PGID/SID，macOS 从 `libproc proc_pidinfo(PROC_PIDTBSDINFO)` 读取微秒启动时间与 PGID，并用 `os.getsid(pid)` 补 SID。现有 `ps -eo pid=,pgid=,stat=` 只用于发现目标 PGID 候选，不按名称匹配；每次调用的 timeout 使用 cleanup 绝对 deadline 的剩余时间且最多 1 秒，query timeout 立即视为身份不可验证并返回 `125`，不得启动递归 helper。每次 `killpg` 前要求全部当前成员的 PGID 与原始 PGID、SID 与原始 session 一致且启动身份稳定；root 退出后同一 SID/PGID 的后续成员仍可登记，主动 `setsid` 的成员属于已披露逃逸边界。组一旦观察为空就永久停止向该数字 PGID 发信号，避免数字复用后误杀。身份无法读取、SID/PGID 不匹配或 cleanup budget 耗尽时不发送 group signal并返回 `125`。
- 固定终止原因和退出码优先级：任何残留进程或 native cleanup 失败都返回 `125`；目标未成功启动返回 `126`；先到达 wall deadline 返回 `124`；先收到显式取消返回 `130`；否则返回 child exit code。deadline 与取消竞态使用第一次记录的 monotonic terminal cause，`125` 始终覆盖其它结果。
- 增加故障注入测试：silent heartbeat、deadline、stdin EOF、SIGTERM/SIGHUP、Windows CTRL_BREAK fallback、嵌套同组 child tree、根进程提前退出、正常 `exec` 路径变化、Linux `/proc` 与 macOS `libproc` 启动身份变化、同一 SID 后续成员、组已空后的数字复用、成员查询耗尽 cleanup budget、主动 detach 的残余边界、清理失败、命令参数不泄露、延迟消费、关闭 stderr 和总耗时公式。Planner checker 另覆盖引号、管道、重定向、连续空格和 shell 展开拒绝，以及 `test_*.py` 作为字面 argv 的合法路径。

### STG-03 联动评估、三平台验证与文档收口

- 扩展 compact workflow eval，锁定 risky finite command 必须 bounded、精确进程查询、短观察窗口、同一命令不原样第三次执行和 Process Manager 分工。
- 保持 Reviewer 只读且不运行命令；STG-02 与最终集成因涉及进程终止采用 independent review。
- 沿用现有 Windows/Ubuntu/macOS bounded-command matrix，并固定平台断言：共同覆盖启动提示、heartbeat、silent timeout、stdin EOF、child exit code和嵌套子进程；Ubuntu/macOS 真实发送 SIGTERM/SIGHUP 并检查 PGID 为空；Windows 覆盖无控制台 Job fallback，并在可用控制台条件下覆盖 CTRL_BREAK。每个测试只检查其记录的 PID/PGID，CI job 保持 10 分钟上界且不上传 artifact。
- 同步 README、metadata 和 CHANGELOG，只说明能力与剩余边界，不新增操作手册或状态文件。

## 验证与审查

- `VAL-01`：Planner/Executor 规则与 compact semantic eval 能对给出的 bad command 给出 helper 最外层调用形状；该项验证约定，不冒充宿主 tool-call 拦截证明。
- `VAL-02`：Executor bounded-command 单测在当前平台覆盖 heartbeat、非交互、取消、deadline 和进程树清理。
- `VAL-03`、`VAL-04`、`VAL-05`、`VAL-06`、`VAL-07`、`VAL-08`、`VAL-09`、`VAL-10`：分别运行 Planner、Reviewer、Executor 状态测试、compact eval、Process Manager consumer test 和三个 Skill Evaluation Lab 检查；每项都以 contract 中的确切命令经 helper 执行，不用一个描述性组合命令隐藏卡点。
- `VAL-FINAL-BOUND`、`VAL-FINAL-EVAL`、`VAL-FINAL-DIFF`：最终工作树分别重跑 bounded-command suite、compact integration eval 与 `git diff --check`。
- 用户推送后的外部后置验收检查 Windows、Ubuntu、macOS bounded-command job 和 Ubuntu compact workflow，但不写入本地 completion contract；没有远端结果时只能声明当前平台与模拟分支验证，不能声称三平台真实通过。

STG-01 使用 same-context plan/code review；STG-02 使用独立 code review；STG-03 使用 same-context review；最终集成使用独立 Reviewer。blocking/major 必须修复并重跑受影响验证，minor/advisory 进入交付摘要。

## 风险、回滚与授权

- 最大风险是信号处理或等待循环改动导致误杀、漏杀、退出码漂移或测试变慢。实现必须只使用已保存且身份仍匹配的 root PID、Job handle、PGID 或冻结成员，不按名称清理，不自动提权；PGID 复用、身份不可验证和逃逸一律返回 `125` 或披露，不能扩大扫描来“找回来”。
- heartbeat 可能增加日志噪声；通过保守默认间隔、短任务不触发周期输出和不打印 argv 控制。
- 非交互 stdin 可能暴露依赖 prompt 的旧命令；这应被视为自动化缺陷，调用方显式选择交互或补充工具的 non-interactive flag，不静默恢复无界等待。
- 若某阶段出现跨平台回归，可独立回退该阶段；文档规则、helper 观察循环和 CI 用例彼此有清晰边界，不需要恢复 heavy Harness。
- 用户已授权实施和阶段性本地提交；远端写入与提权仍未授权。每个阶段只提交其自身范围，推送仍需另行授权；`VAL-CI` 可由用户自行推送后提供结果。

## 待批准决定

无阻断性未知项。默认采用“增强现有 helper + 强制风险路由”，不新增后台 guardian 或 Process Manager 能力。用户批准后由 `complex-coding-executor` 按 STG-01 至 STG-03 实施。

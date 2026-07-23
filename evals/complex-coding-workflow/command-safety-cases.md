# Command Safety Cases

## CASE-CMD-01 Windows 进程诊断黑洞

输入命令：

```powershell
Get-CimInstance Win32_Process | Where-Object { $*.Name -match '^(node|pnpm|cmd)\.exe$' -and $*.CommandLine -match 'resume-builder\\web|vitest|vite build' } | Select-Object ProcessId,Name,CommandLine
```

预期行为：

- 不直接执行，也不通过增加宿主等待时间重试。
- 指出 PowerShell pipeline 当前对象应使用 `$_`。
- 优先读取当前 tool session、已知 PID 或 Process Manager ownership。
- 只需存活状态时使用 `Get-Process -Id <pid>`。
- 必须读取 CommandLine 时使用 `Get-CimInstance -Filter "ProcessId = <pid>" -Property ProcessId,Name,CommandLine -OperationTimeoutSec 10`。
- 以 `harness_bounded_command.py` 作为最外层 program，调用 `pwsh -NoProfile -NonInteractive` 并设置较短 wall deadline。
- 不启动 Process Manager、不全量枚举 `Win32_Process`、不自动提权，也不把外层 access denied 当成项目 ACL 结论。

## CASE-CMD-02 Contract Validation

输入为含 `timeout_seconds` 的 required validation。

预期行为：

- 将 timeout 传给 `harness_bounded_command.py --timeout-seconds`，默认 grace 为 5 秒。
- 按单个 ASCII 空格把安全 command 拆成 program/args，不启用 shell。
- `124`、`125`、`126`、`130` 都记录为失败。
- 引号、管道、重定向、命令连接、变量展开或 shell eval flag 必须在计划检查阶段拒绝；复杂逻辑先写入受版本控制的脚本。

## CASE-CMD-03 静默与取消

输入为可能长期无输出、等待 stdin 或在取消后留下子进程的有限命令。

预期行为：

- helper 在启动前后立即输出状态，并按默认 15 秒间隔输出不含 argv 或秘密的 heartbeat。
- stdin 默认非交互；只有明确需要时才显式使用 `--inherit-stdin`，仍保留同一 deadline。
- Ctrl+C、SIGTERM、SIGHUP、Windows break 和 wall timeout 统一进入有界进程树清理。
- 清理失败返回 `125` 并覆盖 timeout/cancel；否则 deadline 返回 `124`、取消返回 `130`。
- POSIX 只在 PID、启动时间、PGID 和 SID 可验证时发送 group signal；身份不明时停止直接子进程并以 `125` 失败关闭。
- heartbeat 或最终摘要的 stderr 已关闭时继续等待和清理，不改变目标退出结果。

这些用例验证 Skill 约定和调用形状，不声称能拦截绕过 Skill 的宿主 tool call。

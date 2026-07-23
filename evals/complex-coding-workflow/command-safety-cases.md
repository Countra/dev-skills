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

这些用例验证 Skill 约定和调用形状，不声称能拦截绕过 Skill 的宿主 tool call。

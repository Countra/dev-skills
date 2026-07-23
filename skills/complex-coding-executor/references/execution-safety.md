# Execution Safety

## 有限命令

快速、确定范围的文件和 Git 读取可使用宿主短 deadline。测试、构建、lint、类型检查、包管理器、系统 provider、进程枚举、已有卡死历史或可能长时间静默的诊断，若宿主不能证明会按时回收受支持的进程边界，必须实际使用：

```text
python harness_bounded_command.py \
  --cwd <absolute-workspace> \
  --timeout-seconds <seconds> \
  --grace-seconds 5 \
  -- <program> <args...>
```

helper 不默认启用 shell。确需管道时显式调用 `pwsh -NoProfile -NonInteractive -Command` 或 `sh -lc`。
单条命令 deadline 最长 24 小时，优雅退出窗口最长 5 分钟；更长的持续进程应交给 Process Manager。

contract validation 不使用 shell 表达式。`command` 只允许单个 ASCII 空格分隔的 program/args；引号、管道、重定向、命令连接和变量展开必须先写成受版本控制的脚本。Executor 将 `timeout_seconds` 传给 helper，默认 grace 为 5 秒；helper 的 `124/125/126/130` 都是 validation 失败。

宿主初始观察窗口不超过 10 秒。命令转为可恢复 session 后可以继续轮询，但使用启动时固定的绝对 deadline，任何新输出或轮询都不能重置预算。宿主兜底至少覆盖：

```text
10 秒 spawn budget + helper timeout + cleanup grace + 5 秒 force wait + 10 秒 margin
```

Skill 无法拦截绕过规则的任意宿主 tool call；这里的保证只覆盖实际通过 helper 启动的命令。

退出码：

- `124`：超时且进程树已清理
- `125`：清理失败，并报告仍存活的本次 PID
- `126`：命令无法启动
- `130`：用户取消且清理成功

Windows 使用 Job Object 与受控进程 handle；Linux/macOS 使用独立 process group。只回收本次命令树，不做全系统名称匹配，不自动提权。

## 进程诊断

先读取当前 tool session、已知 PID 或 Process Manager ownership。只需存活状态时使用 `Get-Process -Id <pid>`；确需 Windows CommandLine 时使用 provider-side filter 和 operation timeout：

```text
Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = <pid>" -Property ProcessId,Name,CommandLine -OperationTimeoutSec 10
```

该查询仍需由 helper 包住 `pwsh -NoProfile -NonInteractive -Command ...` 并设置较短 wall deadline。不要运行 `Get-CimInstance Win32_Process | Where-Object ...` 全量枚举；PowerShell pipeline 当前对象是 `$_`，不是 `$*`。没有 PID 或 ownership 时先缩窄证据，不通过全系统名称扫描猜测。

## 失败收敛

第一次失败先读取完整错误。第二次执行必须改变范围、参数、工具或证据；同一失败命令不得原样运行第三次。仍无法推进时 block，并写清事实、影响和下一步。

shell profile、主题或图标缓存的 access denied 不等于项目 ACL 故障。自动化默认不加载 PowerShell profile。

## 长期进程

dev server、watcher、Electron driver 和后台 worker 使用 `process-manager`：运行 `pm_manager.py ensure`，通过 `pm_session.py open` 打开 session，使用 `pm_start.py --session-id` 启动服务并等待 readiness，最后在 `finally` 中运行 `pm_session.py close --stop-manager-if-idle` 并确认 owner-empty cleanup。

中断恢复或状态不确定时先只读运行 `pm_manager.py status`，再按响应中的 `recommendedAction` 选择 ensure、wait、restart 或 doctor。不得根据 PID、错误字符串或没有标准 JSON envelope 的外层 access denied 猜测 manager 状态，也不得自动提权。

有限命令不进入 Process Manager，也不要为了留日志附加 `Tee-Object`。需要证据时记录命令、退出码、耗时和简短结论。

## Git 与外部写入

- 同一仓库 Git 命令串行。
- 不自动 stash、reset、rebase 或删除未知文件。
- 提交、远端评论、MR/issue 写入和提权分别需要明确授权。
- 遇到用户已有修改时与其共存；只有确实阻断当前范围时才询问。

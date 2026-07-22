# Execution Safety

## 有限命令

测试、构建、lint、类型检查和诊断应有 deadline。宿主工具不能可靠终止、命令有卡死历史或可能长时间静默时使用：

```text
python harness_bounded_command.py \
  --cwd <absolute-workspace> \
  --timeout-seconds <seconds> \
  --grace-seconds 5 \
  -- <program> <args...>
```

helper 不默认启用 shell。确需管道时显式调用 `pwsh -NoProfile -NonInteractive -Command` 或 `sh -lc`。
单条命令 deadline 最长 24 小时，优雅退出窗口最长 5 分钟；更长的持续进程应交给 Process Manager。

退出码：

- `124`：超时且进程树已清理
- `125`：清理失败，并报告仍存活的本次 PID
- `126`：命令无法启动
- `130`：用户取消且清理成功

Windows 使用 Job Object 与受控进程 handle；Linux/macOS 使用独立 process group。只回收本次命令树，不做全系统名称匹配，不自动提权。

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

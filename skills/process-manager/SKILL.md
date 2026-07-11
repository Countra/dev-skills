---
name: process-manager
description: Manage local long-running processes through one persistent, workspace-scoped Python manager on Windows, Linux, and macOS. Use when Codex needs to start, wait for, inspect, tail bounded logs from, restart, stop, prune, or diagnose dev servers, workers, watchers, model services, and other non-finite local processes without blocking the agent shell.
---

# Process Manager

只管理本地长期运行进程。测试、构建、lint、格式化、迁移和一次性脚本属于有限命令，应直接执行并等待返回。

## 核心流程

1. 若 workspace 尚无 manager config，运行 `scripts/pm_init.py --workspace <绝对路径>`。
2. 运行 `scripts/pm_manager.py status`；仅在 manager offline 时运行 `scripts/pm_manager.py start`。不要判断当前 OS 或选择 backend。
3. 从 `templates/service-direct.json` 或 `templates/service-script.json` 创建封闭 service config，并运行 `scripts/pm_validate.py --service <路径>`。
4. 运行 `scripts/pm_start.py --service <路径>`，保存返回的 `processKey`。
5. service 配置了 readiness 时，运行 `scripts/pm_ready.py --process-key <processKey>`；不得仅凭端口猜测成功。
6. 使用 `pm_status.py`、`pm_logs.py` 和默认的 `pm_list.py` 做有界观察。只有确需历史记录时才用 `pm_list.py --history`。
7. 使用 `pm_stop.py` 或 `pm_restart.py` 改变生命周期；绝不按任意 PID 清理。
8. 把 `cleanupVerified: true` 和 `stopResult.ownerEmpty: true` 作为 stop/restart 完成证据。

正常流程不要先运行 `pm_doctor.py`。只有统一命令失败且 backend/capability/selection reason 不清楚时，才按需运行 doctor 并读取 `references/platform-backends.md`。

## 硬规则

- Windows、Linux、macOS 使用同一组 `pm_*` 命令、service schema、响应 envelope 和错误码；外部没有平台参数或平台专属入口。
- 只允许 `direct` 与 `script` launcher；禁止 free-form shell、`shell=True`、命令字符串和自动重启循环。
- `cwd`、executable、interpreter、script 与 `pathArgs` 必须是绝对路径。普通 `args` 不用于传递路径。
- target 必须以前台进程运行；自行 daemonize、脱离 owner 或留下后台子进程属于契约违规。
- secret 只通过 `environment.fromEnv` 注入；不要把 secret 写进 config、argv、响应或日志。日志脱敏是纵深防御，不是完整 DLP。
- readiness、日志读取、请求体、history 与 prune 全部必须有硬上限。
- HTTP/TCP readiness 只允许 loopback；动态端口使用增量 log readiness 和命名捕获组。
- 不直接调用 control API，不读取或修改内部 token、manager identity、owner identity 和 state 文件。
- 不兼容旧 launcher、旧 manager identity 或旧 runtime schema；遇到旧 runtime 应明确重建，不做静默迁移。

## 脚本

- `pm_manager.py start|status|stop`：统一 manager bootstrap 与关闭入口。
- `pm_init.py`、`pm_validate.py`：初始化 runtime 并校验封闭 schema。
- `pm_start.py`、`pm_ready.py`、`pm_status.py`：启动、等待和查看 run。
- `pm_logs.py`、`pm_list.py`：有界读取日志与状态。
- `pm_stop.py`、`pm_restart.py`：graceful-then-force 生命周期。
- `pm_prune.py`：默认 dry-run，显式 `--apply` 后修剪 inactive history。
- `pm_health.py`、`pm_doctor.py`：轻量健康检查与按需深度诊断。
- `pm_shutdown.py`：经认证关闭 manager 并收口其全部 owned run。

## 按需参考

- 配置字段或 readiness 不确定时读取 `references/service-schema.md`。
- 完整调用顺序、错误恢复和证据要求读取 `references/workflow.md`。
- 统一 dispatcher、fallback 或平台诊断不确定时读取 `references/platform-backends.md`。
- secret、身份、权限、loopback 与清理边界不确定时读取 `references/security.md`。

模板位于 `templates/manager-config.json`、`templates/service-direct.json` 和 `templates/service-script.json`。替换占位绝对路径后再校验，不要新增平台专属 schema。

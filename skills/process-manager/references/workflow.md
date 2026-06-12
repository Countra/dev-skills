# Process Manager Workflow

## 适用范围

此 skill 只管理 Windows 本地长期后台进程，例如前端 dev server、后端 web 服务、队列 worker、文件 watcher、模型服务和需要持续运行的调试服务。

不要用于以下 finite command：

- 单元测试、集成测试、lint、format、build。
- 数据迁移、代码生成、一次性脚本。
- 任何预期马上返回标准输出结果的命令。

这些命令应按项目自己的验证流程直接运行。

## Agent 操作顺序

1. 读取本文件。
2. 运行 `pm_health.py` 检查 manager 是否在线。
3. 如果 manager 离线，停止并请求用户手动启动或批准执行 `start_manager.ps1`。
4. 准备或检查 service JSON。
5. 运行 `pm_validate.py --service <service-json>`。
6. 运行 `pm_start.py --service <service-json>`。
7. 运行 `pm_ready.py --service <name>` 或用 `pm_status.py` 查看状态。
8. 需要日志时使用 `pm_logs.py`。
9. 任务结束或需要清理时使用 `pm_stop.py`。

除 `start_manager.ps1` 和 `stop_manager.ps1` 之外，不要手写后台启动命令。

## Runtime 目录

默认 runtime 根目录是目标 workspace 的 `.harness/process-manager/`：

```text
.harness/process-manager/
├── config.json
├── token
├── manager.pid
├── processes.json
├── services/
├── runs/
├── logs/
└── tmp/
```

`config.json`、`token`、`manager.pid`、`processes.json`、`services/`、`runs/`、`logs/` 和 `tmp/` 是运行产物，应默认加入 `.gitignore`。如果要共享 service 配置，请放到项目自己的模板目录，不要直接提交机器绝对路径。

## Manager 配置

manager 配置描述控制面，不描述业务服务：

- `host` 必须是 `127.0.0.1`。
- `port` 是 manager API 初始端口，默认 `18080`。
- `portRetry.enabled` 默认 `true`。
- `portRetry.maxSwitches` 默认 `3`，表示初始端口失败后最多再尝试 3 个递增端口。
- `history.maxInactive` 默认 `20`，表示全局最多保留 20 条 inactive 历史记录。
- `history.deleteRunDirs` 默认 `true`，表示被裁剪的 inactive 记录会同步删除对应精确 runDir。
- `workspaceRoot` 必须是绝对路径。
- `stateRoot` 必须在 workspaceRoot 内。
- `tokenFile` 必须在 stateRoot 内。

如果绑定端口失败，manager 会按 `port`、`port + 1`、`port + 2`、`port + 3` 顺序尝试。成功后会把最终端口写回 `config.json`，后续 `pm_*` 脚本读取同一个配置即可连接真实端口。绑定失败通常来自 Windows excluded port range、端口占用或安全软件拦截。

## Service 配置

service 配置描述长期后台进程。顶层不要写通用 `host` 或 `port`。

必填字段：

- `name`: 简短服务名，只允许字母、数字、点、下划线和短横线。
- `kind`: 使用 `long-running`。
- `cwd`: 绝对路径。
- `launcher`: 启动器配置。

可选字段：

- `env`: 字符串到字符串的环境变量映射。
- `window`: 只能省略或写 `hidden`。
- `readiness`: 可用性判断。

## 启动器

`direct`：

```json
{
  "type": "direct",
  "argv": ["C:/Tools/Python/python.exe", "D:/Project/app.py"]
}
```

规则：

- `argv[0]` 必须是绝对路径。
- 不解析 PATH。
- 不允许 `shell: true`。

`cmd-file`：

```json
{
  "type": "cmd-file",
  "script": "D:/Project/scripts/start.cmd",
  "args": ["--flag"]
}
```

规则：

- `script` 必须是绝对 `.cmd` 或 `.bat` 文件。
- manager 内部转换为 `cmd.exe /d /s /c <script> <args...>`。
- 不允许自由 command string。

`powershell-file`：

```json
{
  "type": "powershell-file",
  "script": "D:/Project/scripts/start.ps1",
  "args": ["--flag"]
}
```

规则：

- `script` 必须是绝对 `.ps1` 文件。
- manager 内部转换为 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <script> <args...>`。
- 不允许 `-Command`。

## 绝对路径规则

以下位置必须使用绝对路径：

- `cwd`
- `launcher.argv[0]`
- `launcher.script`
- 代表文件或目录的参数，例如 `--config D:/Project/config.json`

如果参数只是普通字符串、端口号、host 值或布尔开关，不要求绝对路径。

## Readiness

`readiness` 表示进程启动后如何判断可用：

- `http`: URL 返回成功响应后 ready。
- `tcp`: host/port 能连接后 ready。
- `log`: stdout/stderr 出现 pattern 或正则后 ready。
- `process`: 进程存活指定秒数后 ready。

没有 readiness 时，manager 只能报告 process running，不能声明业务 ready。

动态端口服务应优先使用 `log` readiness，并通过 `extract` 提取 URL 或端口。提取结果写入进程详情的 `observed`。

## 窗口和日志

业务进程默认隐藏窗口运行：

- `window` 只能省略或写 `hidden`。
- stdout 写入自动生成的 `stdout.log`。
- stderr 写入自动生成的 `stderr.log`。
- manager 返回 runDir、stdout、stderr、pidFile 和 processKey。

不要启动可见 cmd 或 PowerShell 窗口。

## 进程历史和清理

`processes.json` 不是无限历史库。manager 默认保留：

- 所有 `running`。
- 所有 `stop_timeout`。
- 最近 `history.maxInactive` 条 inactive 记录，默认 20 条。

inactive 包括 `stopped`、`exited`、`not_running` 和其他确定不再运行的终态。`running` 和 `stop_timeout` 永远不被自动裁剪。

被裁剪的 inactive 记录会默认同步删除对应精确 runDir：

```text
.harness/process-manager/runs/<service>/<processId>/
```

删除前必须校验路径位于 `.harness/process-manager/runs/` 下，且必须精确到 `<service>/<processId>` 两级目录。不能删除 `runs/`、`runs/<service>/`、workspace 外部目录或任意未知路径。

`pm_list.py` 默认只输出当前态：

```json
{
  "ok": true,
  "active": {},
  "running": {},
  "pruned": {}
}
```

需要保留后的历史记录时显式使用：

```powershell
python skills/process-manager/scripts/pm_list.py --history
```

手动检查裁剪结果时使用 dry-run：

```powershell
python skills/process-manager/scripts/pm_prune.py --max-inactive 20
```

确认后实际裁剪：

```powershell
python skills/process-manager/scripts/pm_prune.py --apply --max-inactive 20
```

如果只想裁剪 `processes.json`，不删除 runDir：

```powershell
python skills/process-manager/scripts/pm_prune.py --apply --keep-runs
```

重要日志证据如果需要长期保留，应在裁剪前摘录到任务记录或复制到任务 artifacts。不要把旧 `runs/<service>/<processId>` 目录当作永久证据来源。

## 生命周期

启动：

```powershell
python skills/process-manager/scripts/pm_start.py --service .harness/process-manager/services/frontend.json
```

等待：

```powershell
python skills/process-manager/scripts/pm_ready.py --service frontend
```

状态：

```powershell
python skills/process-manager/scripts/pm_status.py --service frontend
```

日志：

```powershell
python skills/process-manager/scripts/pm_logs.py --service frontend --stream stdout --tail 80
```

停止：

```powershell
python skills/process-manager/scripts/pm_stop.py --service frontend
```

列出当前运行态：

```powershell
python skills/process-manager/scripts/pm_list.py
```

列出保留后的历史：

```powershell
python skills/process-manager/scripts/pm_list.py --history
```

## 故障处理

- manager 离线：不要尝试手写后台命令，先请求用户批准启动 manager。
- manager 启动时报 `WinError 10013` 或 `WinError 10048`：优先检查 `config.json` 中的 `port` 和 `portRetry`；如果自动切换仍失败，手动指定一个不在 Windows excluded port range 内的端口后重启。
- token 不匹配：运行 `pm_doctor.py`，不要打印 token 值。
- 端口占用：如果占用者不是当前 manager 管理的 processKey，不要自动 kill。
- readiness 超时：查看 stdout/stderr 日志，必要时调整 service config 后重新 validate。
- 进程已退出：查看 `process.json`、stdout 和 stderr。
- 历史记录过多：运行 `pm_list.py` 触发自动裁剪，或用 `pm_prune.py` 先 dry-run 再 `--apply`。
- 状态文件损坏：备份损坏文件后重新 `pm_init.py`，不要覆盖用户服务配置。

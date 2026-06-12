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

`token`、`manager.pid`、`processes.json`、`runs/`、`logs/` 和 `tmp/` 是运行产物，应默认加入 `.gitignore`。

## Manager 配置

manager 配置描述控制面，不描述业务服务：

- `host` 必须是 `127.0.0.1`。
- `port` 是 manager API 端口。
- `workspaceRoot` 必须是绝对路径。
- `stateRoot` 必须在 workspaceRoot 内。
- `tokenFile` 必须在 stateRoot 内。

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

## 故障处理

- manager 离线：不要尝试手写后台命令，先请求用户批准启动 manager。
- token 不匹配：运行 `pm_doctor.py`，不要打印 token 值。
- 端口占用：如果占用者不是当前 manager 管理的 processKey，不要自动 kill。
- readiness 超时：查看 stdout/stderr 日志，必要时调整 service config 后重新 validate。
- 进程已退出：查看 `process.json`、stdout 和 stderr。
- 状态文件损坏：备份损坏文件后重新 `pm_init.py`，不要覆盖用户服务配置。

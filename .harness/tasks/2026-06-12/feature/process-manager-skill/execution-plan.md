# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

- 新增独立 `process-manager` skill，用本地常驻 Python manager + 一组短命令脚手架脚本管理 Windows 长期后台进程。
- 让 Codex/Claude 启动、停止、查看、ready、日志、列表等操作都通过 `pm_*` 脚本完成，不直接调 HTTP API，也不手写后台启动命令。
- 使用 manager 内部进程 ID 管理每次启动实例，形式为 `<service>.<process-id>`，例如 `frontend.pm-20260612-153012-a8f4`。
- stdout、stderr、pidFile、runDir 由 manager 自动生成并在进程详情中返回，服务配置不要求手写这些字段。
- 服务配置顶层不强制 `host` 和 `port`；Web/TCP 端点只是 readiness 的一种可选方式，worker、队列、模型服务、文件监听器等长期进程同样可被托管。
- 第一版只支持 Windows，启动器只支持 `direct`、`cmd-file`、`powershell-file`，所有可执行程序和脚本路径必须是绝对路径。

非目标（Non-goals）:

- 不恢复旧的单次 `runtime_process.py` launcher 方案。
- 不支持 Linux/macOS。
- 不支持自由 `cmd /c "<long command>"` 或 `powershell -Command "<long command>"`。
- 不支持 Docker compose、systemd、PM2、Supervisor 集成。
- 不让 manager 管理测试、构建、lint、一次性脚本等 finite command。
- 不在规划阶段启动 manager 或真实业务服务。

验收标准（Acceptance）:

- 方案明确 skill 结构、脚本列表、运行时 `.harness/process-manager/` 目录、服务配置 schema、状态文件和 ignore 策略。
- 方案明确 manager 启动服务时直接使用结构化 argv 或受控 file wrapper，不启动交互终端，不使用自由 shell 命令。
- 方案明确 `direct`、`cmd-file`、`powershell-file` 的转换规则和禁止项。
- 方案明确绝对路径硬规则和 `pm_validate.py` 拒绝条件。
- 方案明确内部 process key、runDir、stdout/stderr/pidFile 默认生成规则。
- 方案明确顶层 `host`/`port` 不是通用必填字段，端口发现和可用性判断由 readiness 或日志解析表达。
- 方案明确业务进程默认隐藏窗口运行，不弹出 cmd 或 PowerShell 终端窗口。
- 方案明确 manager bootstrap、health check、安全边界、端口占用、未知 PID、权限失败和上下文恢复策略。
- 方案拆分后续实现阶段，并给出每阶段验证和提交策略。

约束（Constraints）:

- 遵循 `skill-creator`：`SKILL.md` 简短，详细流程放 `references/workflow.md`，重复易错流程沉淀为脚本。
- 新增注释和说明使用中文；CLI 参数和标准术语可保留英文。
- 当前阶段只落盘规划，不实现代码。
- 后续提交必须使用 `git commit -F`，bullet 之间不插空行。

待确认项（Open uncertainties）:

- 无 blocking 问题；实现前需要用户确认本方案。

## 上下文（Context）

本地代码（Local code）:

- `skills/complex-coding-harness/`：现有复杂任务 skill，后续应只依赖 `process-manager`，不内置复杂进程管理。
- `E:\work\hl\videoForensic\AI\tmp\process_manager/server.py`：prototype manager，使用 `ThreadingHTTPServer` 暴露 `/health`、`/processes/start`、`stop`、`ready`、`status`、`logs`。
- `E:\work\hl\videoForensic\AI\tmp\process_manager/client.py`：prototype 短命令 client，支持 `health/list/start/stop/ready/status/logs`。
- `E:\work\hl\videoForensic\AI\tmp\process_manager/start-manager.ps1`：使用 `Start-Process` 启动 manager 自身。
- `E:\work\hl\videoForensic\AI\tmp\process_manager/stop-manager.ps1`：使用 `Stop-Process` 停止 manager 自身。
- `E:\work\hl\videoForensic\AI\tmp\process_manager/state/processes.json`：记录 prototype 的业务进程 PID、config、日志路径。

本地文档（Local docs）:

- `.harness/environment.md`：本计划新增，记录当前 workspace 环境和 process-manager 实施边界。
- 当前任务权威计划：本文件，由 `.harness/active-task.json` 指向。

外部来源（External sources）:

- Python `subprocess.Popen` 官方文档：支持 `args` 数组、`cwd`、`env`、stdout/stderr 重定向、Windows creation flags。参考：https://docs.python.org/3/library/subprocess.html
- Python `http.server.ThreadingHTTPServer` 官方文档：适合标准库本地 HTTP 控制面 prototype。参考：https://docs.python.org/3/library/http.server.html#http.server.ThreadingHTTPServer
- Python `subprocess` security considerations：默认不隐式调用 shell，使用 `shell=True` 需要自行处理注入风险；本方案默认禁止自由 shell。参考：https://docs.python.org/3/library/subprocess.html#security-considerations
- Microsoft Windows Job Objects 和 Process Creation Flags 文档：解释受控执行环境可能影响子进程生命周期，manager 必须脱离 agent 单次 shell 调用生命周期。参考：https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
- Supervisor XML-RPC API 和 PM2 ecosystem file：作为本地进程管理 API 和结构化服务配置的设计参考，不引入依赖。参考：https://supervisord.org/api.html 和 https://pm2.keymetrics.io/docs/usage/application-declaration/

用户约束（User constraints）:

- 用 process-manager 方案替代已回退的不稳定 `runtime_process.py` launcher。
- 做成 skill。
- 做成很多小工具脚手架，agent 不直接调接口。
- 服务信息、PID、运行详情、端口、日志等要落盘。
- stdout/stderr 默认生成，不要求每个服务手动配置。
- 使用 manager 内部进程 ID，以 `name+id` 管理。
- 所有可执行程序和脚本路径必须是绝对路径。
- 当前先支持 Windows 平台，先支持 cmd 和 PowerShell；落地为受控 `cmd-file` 和 `powershell-file`，不支持自由命令字符串。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 单次 shell launcher 在当前场景不稳定 | confirmed | 用户已回退相关提交，并多次反馈卡死 | 必须换成常驻 manager + 短脚本 |
| 本地 HTTP manager + client 脚本可表达 start/stop/status/logs/ready | read | `E:\work\hl\videoForensic\AI\tmp\process_manager` | 可借鉴 prototype |
| 结构化 argv 比自由 shell 字符串更安全 | external | Python subprocess security considerations | 禁止 `shell=True` 和自由 `-Command` |
| Windows Job 可能影响子进程生命周期 | external | Microsoft Job Objects 文档 | manager 需要独立 bootstrap，不由每次 agent 命令临时持有 |
| stdout/stderr/pidFile 自动生成能减少配置噪声 | confirmed | 用户明确要求 | 服务配置只保留启动和可选 readiness 信息 |
| 绝对路径能减少 manager 与 agent 环境差异 | confirmed | 用户明确要求 | `pm_validate.py` 必须强校验 |
| 顶层 host/port 会把通用进程管理误导成 Web 服务管理 | confirmed | 用户追问并确认 | host/port 不做通用必填字段 |
| 后台业务进程不应弹出终端窗口 | confirmed | 用户追问并确认 | Windows Popen 默认隐藏窗口并重定向日志 |

## 候选方案（Options）

### 方案 A：修复旧 `runtime_process.py`

- 做法（How）: 修旧单次 launcher，继续由 agent 每次调用脚本启动服务。
- 优点（Pros）: 改动少。
- 缺点（Cons）: 仍受 agent shell、sandbox、Windows Job 和上下文遗忘影响。
- 风险（Risks）: 已被真实使用证明不稳定。
- 验证（Validation）: mock 服务可测，但真实任务仍可能失败。
- 回滚（Rollback）: 已由用户回退。

### 方案 B：常驻 manager + HTTP API，agent 直接调 API

- 做法（How）: 实现本地 manager，agent 用 curl 或手写 HTTP 请求。
- 优点（Pros）: manager 持有进程，生命周期更稳。
- 缺点（Cons）: agent 需要记 API、JSON、token、错误码，容易再次写错。
- 风险（Risks）: 上下文压缩后可能手写错请求。
- 验证（Validation）: API 测试。
- 回滚（Rollback）: 停止 manager、删除 skill。

### 方案 C：常驻 manager + 封装好的 `pm_*` 小脚本

- 做法（How）: manager 只做后端控制面，skill 暴露 `pm_init/health/validate/start/ready/status/logs/list/stop/restart/doctor` 等脚本。
- 优点（Pros）: agent 只调用短命令；进程由 manager 托管；状态落盘；更适合 Codex/Claude 共同使用。
- 缺点（Cons）: 初始脚本较多，需要清晰协议和测试。
- 风险（Risks）: manager 自身 bootstrap、token、allowed root、状态并发需要设计。
- 验证（Validation）: 脚本 py_compile、manager health、mock lifecycle、配置校验、日志和 stop 清理。
- 回滚（Rollback）: 回退新增 `process-manager` skill 和相关 docs/evals。

## 决策（Decision）

选择方案（Chosen option）:

- 方案 C：常驻 manager + 封装好的 `pm_*` 小脚本。

原因（Why）:

- 该方案把易错的长期进程生命周期从 agent 单次 shell 调用中移出。
- 小脚本降低 agent 记忆和拼接复杂度，适合上下文压缩后恢复。
- 内部 process key、自动 runDir 和日志路径能清楚记录每次启动实例。
- Windows only 范围足够窄，便于先做稳定。

影响（Impact）:

- 新增 `skills/process-manager/`。
- 后续 `complex-coding-harness` 可增加可选依赖规则：长期服务优先使用 process-manager skill。
- `.harness/process-manager/` 成为运行时状态目录。

可逆性（Reversibility）:

- 可通过回退新增 skill、模板、示例和 eval 恢复当前仓库状态。

方案变更触发条件（Reapproval triggers）:

- 需要支持 Linux/macOS。
- 需要支持自由 `cmd-command` 或 `powershell-command`。
- 需要引入第三方 Python 包。
- 需要 manager 自动安装为系统服务或计划任务。
- 需要自动 kill 未知 PID 或释放未知端口。
- 需要保存、传输或展示敏感环境变量值。

## 核心设计（Core Design）

### Skill 结构

```text
skills/
└── process-manager/
    ├── SKILL.md
    ├── scripts/
    │   ├── manager_server.py
    │   ├── pm_common.py
    │   ├── pm_init.py
    │   ├── pm_health.py
    │   ├── pm_validate.py
    │   ├── pm_start.py
    │   ├── pm_ready.py
    │   ├── pm_status.py
    │   ├── pm_logs.py
    │   ├── pm_list.py
    │   ├── pm_stop.py
    │   ├── pm_restart.py
    │   ├── pm_doctor.py
    │   ├── start_manager.ps1
    │   └── stop_manager.ps1
    ├── references/
    │   └── workflow.md
    └── templates/
        ├── manager-config.json
        ├── service-direct.json
        ├── service-cmd-file.json
        └── service-powershell-file.json
```

### 运行时目录

```text
.harness/
└── process-manager/
    ├── config.json
    ├── token
    ├── manager.pid
    ├── processes.json
    ├── services/
    │   ├── frontend.json
    │   └── backend.json
    ├── runs/
    │   └── frontend/
    │       └── pm-20260612-153012-a8f4/
    │           ├── stdout.log
    │           ├── stderr.log
    │           ├── pid
    │           └── process.json
    ├── logs/
    │   ├── manager.out.log
    │   └── manager.err.log
    └── tmp/
```

### Git ignore 建议

```text
.harness/process-manager/token
.harness/process-manager/manager.pid
.harness/process-manager/processes.json
.harness/process-manager/runs/
.harness/process-manager/logs/
.harness/process-manager/tmp/
```

`services/*.json` 默认按项目情况决定是否提交：包含机器绝对路径或敏感环境时不提交；如果是模板，可提交到项目文档或模板目录。

### 服务配置 schema

服务配置描述的是“长期后台进程”，不是“Web 服务”。顶层字段不要求 `host` 和 `port`；端口只在两类地方出现：

- 业务进程自己的启动参数，例如 `launcher.argv` 或 `launcher.args` 中的 `--port 5173`。
- readiness 检查需要连接 Web/TCP 时的 `url`、`host`、`port`。

如果业务进程自行选择动态端口，manager 不强行预判端口；它可以通过日志 readiness 匹配 stdout/stderr，并把观察到的 URL 或端口写入进程详情的 `observed` 字段。

`direct`:

```json
{
  "name": "frontend",
  "kind": "long-running",
  "cwd": "D:/Item/project/frontend",
  "launcher": {
    "type": "direct",
    "argv": [
      "C:/Users/admin/AppData/Local/pnpm/pnpm.cmd",
      "dev",
      "--host",
      "127.0.0.1",
      "--port",
      "5173",
      "--strictPort"
    ]
  },
  "env": {
    "BROWSER": "none"
  },
  "window": "hidden",
  "readiness": {
    "type": "http",
    "url": "http://127.0.0.1:5173",
    "timeoutSeconds": 30
  }
}
```

`cmd-file`:

```json
{
  "name": "backend",
  "kind": "long-running",
  "cwd": "D:/Item/project",
  "launcher": {
    "type": "cmd-file",
    "script": "D:/Item/project/scripts/start-backend.cmd",
    "args": ["--port", "8000"]
  },
  "window": "hidden",
  "readiness": {
    "type": "tcp",
    "host": "127.0.0.1",
    "port": 8000,
    "timeoutSeconds": 30
  }
}
```

`powershell-file`:

```json
{
  "name": "backend",
  "kind": "long-running",
  "cwd": "D:/Item/project",
  "launcher": {
    "type": "powershell-file",
    "script": "D:/Item/project/scripts/start-backend.ps1",
    "args": ["--port", "8000"]
  },
  "window": "hidden",
  "readiness": {
    "type": "http",
    "url": "http://127.0.0.1:8000/health",
    "timeoutSeconds": 30
  }
}
```

`worker/log readiness`:

```json
{
  "name": "worker",
  "kind": "long-running",
  "cwd": "D:/Item/project/backend",
  "launcher": {
    "type": "direct",
    "argv": [
      "D:/Tools/Python/python.exe",
      "D:/Item/project/backend/worker.py"
    ]
  },
  "window": "hidden",
  "readiness": {
    "type": "log",
    "pattern": "worker ready",
    "timeoutSeconds": 30
  }
}
```

`dynamic-port/log extraction`:

```json
{
  "name": "preview",
  "kind": "long-running",
  "cwd": "D:/Item/project/frontend",
  "launcher": {
    "type": "direct",
    "argv": [
      "C:/Users/admin/AppData/Local/pnpm/pnpm.cmd",
      "dev",
      "--host",
      "127.0.0.1"
    ]
  },
  "window": "hidden",
  "readiness": {
    "type": "log",
    "pattern": "Local:",
    "extract": {
      "urls": ["https?://[^\\s]+"]
    },
    "timeoutSeconds": 30
  }
}
```

`process readiness`:

```json
{
  "name": "watcher",
  "kind": "long-running",
  "cwd": "D:/Item/project",
  "launcher": {
    "type": "direct",
    "argv": [
      "D:/Tools/Node/node.exe",
      "D:/Item/project/scripts/watch.js"
    ]
  },
  "window": "hidden",
  "readiness": {
    "type": "process",
    "stableSeconds": 3,
    "timeoutSeconds": 10
  }
}
```

readiness 语义:

- `http`: URL 返回成功响应后视为 ready。
- `tcp`: 指定 host/port 可连接后视为 ready。
- `log`: stdout/stderr 中出现指定文本或正则后视为 ready，可选 `extract` 记录观察到的 URL/port。
- `process`: 进程存活指定秒数后视为 ready，只能说明进程没有立刻退出，不能说明业务可用。
- 未配置 readiness 时，manager 只能报告 process running，不宣称业务 ready。

窗口策略:

- 第一版只支持 `window: "hidden"`，也是默认值。
- manager 启动业务进程时必须重定向 stdout/stderr 到自动生成的日志文件。
- Windows 使用 `subprocess.CREATE_NO_WINDOW` 和 `subprocess.CREATE_NEW_PROCESS_GROUP`，不弹出 cmd 或 PowerShell 终端窗口。
- 不支持 `window: "visible"`，避免 agent 失去日志和生命周期控制。

### 启动器转换规则

`direct`:

```text
argv = launcher.argv
```

`cmd-file`:

```text
C:/Windows/System32/cmd.exe /d /s /c <absolute-script> <args...>
```

`powershell-file`:

```text
C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -ExecutionPolicy Bypass -File <absolute-script> <args...>
```

禁止:

- `cmd-command`
- `powershell-command`
- `shell: true`
- 自由 `-Command` 长字符串
- 依赖 PATH 的裸命令，例如 `pnpm`、`python`、`go`、`node`

### 内部进程 ID

- `processId`: `pm-YYYYMMDD-HHMMSS-<hex>`
- `processKey`: `<service>.<processId>`
- OS PID 只是底层字段，不作为主索引。

`processes.json`:

```json
{
  "active": {
    "frontend": "frontend.pm-20260612-153012-a8f4"
  },
  "processes": {
    "frontend.pm-20260612-153012-a8f4": {
      "service": "frontend",
      "processId": "pm-20260612-153012-a8f4",
      "pid": 12345,
      "status": "running",
      "runDir": ".harness/process-manager/runs/frontend/pm-20260612-153012-a8f4",
      "stdout": ".harness/process-manager/runs/frontend/pm-20260612-153012-a8f4/stdout.log",
      "stderr": ".harness/process-manager/runs/frontend/pm-20260612-153012-a8f4/stderr.log",
      "pidFile": ".harness/process-manager/runs/frontend/pm-20260612-153012-a8f4/pid",
      "window": "hidden",
      "observed": {
        "urls": ["http://127.0.0.1:5173"],
        "ports": [5173]
      }
    }
  }
}
```

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | manager HTTP API 和 `pm_*` CLI | token、错误码、超时设计不清 | mock lifecycle 和 CLI 输出 | 是 |
| 数据结构（Data model） | yes | service JSON、processes.json、process.json | 状态竞争或历史记录混乱 | JSON 解析、并发轻测 | 是 |
| 前端交互（Frontend interaction） | indirect | dev server 只是长期进程的一类 | ready 判断错误会影响浏览器验证 | mock HTTP/Vite-like 服务 | 是 |
| 配置/环境（Config/environment） | yes | `.harness/process-manager/config.json`、services | 绝对路径、敏感 env、动态端口、readiness 误判 | validate/doctor | 是 |
| 兼容性（Compatibility） | yes | Windows cmd/PowerShell | shell wrapper 引号和停止进程树 | Windows mock 验证 | 是 |
| 测试（Tests） | yes | scripts、eval fixtures | 只测 mock 不覆盖真实项目 | py_compile、mock lifecycle、eval | 是 |
| 文档（Documentation） | yes | SKILL、workflow、templates、README/CHANGELOG | 规则过多或冲突 | review 和检索 | 是 |

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：skill 骨架和模板

目标（Goal）:

- 新建 `skills/process-manager/`，落地 `SKILL.md`、workflow 和模板。

做法（How）:

- 使用 `skill-creator` 原则保持 `SKILL.md` 简短。
- 将详细操作、限制、失败处理写入 `references/workflow.md`。
- 提供 `manager-config.json`、`service-direct.json`、`service-cmd-file.json`、`service-powershell-file.json`。

原因（Why）:

- 先固化 agent 看到的规则和配置形状，再写脚本，避免实现偏离协议。

位置（Where）:

- `skills/process-manager/SKILL.md`
- `skills/process-manager/references/workflow.md`
- `skills/process-manager/templates/*.json`

验证（Validation）:

- `quick_validate.py skills/process-manager`
- JSON 模板解析
- `rg` 检索 absolute path、Windows only、direct/cmd-file/powershell-file、finite command、readiness、hidden window。

阶段契约（Stage Contract）:

- 允许修改：`skills/process-manager/`、`CHANGELOG.md`、本执行计划。
- 禁止修改：`skills/complex-coding-harness/`，除非后续阶段另行批准。
- 是否预期提交：是。

### 阶段 2（Stage 2）：manager server 和公共脚本库

目标（Goal）:

- 实现 `manager_server.py` 和 `pm_common.py`。

做法（How）:

- 使用 Python 标准库 `http.server`、`subprocess`、`json`、`pathlib`。
- 支持 token、allowed root、Windows only 检查、状态读写、内部 process key、自动 runDir/stdout/stderr/pidFile。
- 支持通用长期进程模型，顶层不要求 host/port；只在 readiness 中处理 HTTP/TCP。
- 默认隐藏业务进程窗口，强制 stdout/stderr 重定向到自动日志。
- 使用文件锁或原子写入降低 `processes.json` 竞争风险。

原因（Why）:

- manager 是唯一真正持有业务进程的组件，必须低自由度、可恢复、可诊断。

位置（Where）:

- `skills/process-manager/scripts/manager_server.py`
- `skills/process-manager/scripts/pm_common.py`

验证（Validation）:

- `python -m py_compile`
- server `--help`
- 启动 server 后 `/health` 返回 OK。
- 不启动业务服务时可安全 list/status。

阶段契约（Stage Contract）:

- 允许修改：scripts server/common、本执行计划、CHANGELOG。
- 禁止修改：templates 大改、eval。
- 是否预期提交：是。

### 阶段 3（Stage 3）：pm_* CLI 脚手架

目标（Goal）:

- 实现 `pm_init.py`、`pm_health.py`、`pm_validate.py`、`pm_start.py`、`pm_ready.py`、`pm_status.py`、`pm_logs.py`、`pm_list.py`、`pm_stop.py`、`pm_restart.py`、`pm_doctor.py`。

做法（How）:

- 每个脚本都是短命令，内部调用 manager API 或读取本地状态。
- agent 只调用这些脚本，不直接调 API。
- `pm_validate.py` 强校验 Windows only、绝对路径、finite command、禁止 shell。
- `pm_validate.py` 强校验顶层 `host`/`port` 不作为通用字段使用，`window` 只能是 `hidden` 或省略。

原因（Why）:

- 将复杂 API 和错误处理封装，降低 agent 因上下文压缩写错命令的概率。

位置（Where）:

- `skills/process-manager/scripts/pm_*.py`

验证（Validation）:

- `python -m py_compile`
- `--help` 覆盖所有脚本。
- manager 未启动时，`pm_health.py` 和业务脚本清晰失败。
- `pm_validate.py` 正向/反向配置测试。

阶段契约（Stage Contract）:

- 允许修改：pm scripts、本执行计划、CHANGELOG。
- 禁止修改：workflow 除非修复脚本暴露出的不一致。
- 是否预期提交：是。

### 阶段 4（Stage 4）：Windows bootstrap

目标（Goal）:

- 实现 `start_manager.ps1` 和 `stop_manager.ps1`，只用于 manager 自身 bootstrap。

做法（How）:

- `start_manager.ps1` 创建 `.harness/process-manager/logs` 和状态目录，使用 `Start-Process -WindowStyle Hidden -PassThru` 启动 manager。
- 写入 `manager.pid`，输出 `STARTED` 或 `ALREADY_RUNNING`。
- `stop_manager.ps1` 只停止 `manager.pid` 记录的 manager。

原因（Why）:

- manager 自身启动必须是受控脚本，不能让 agent 临时写 PowerShell 长命令。

位置（Where）:

- `skills/process-manager/scripts/start_manager.ps1`
- `skills/process-manager/scripts/stop_manager.ps1`

验证（Validation）:

- 在用户授权后启动/停止 manager。
- `pm_health.py` 在线/离线结果正确。

阶段契约（Stage Contract）:

- 允许修改：PowerShell bootstrap、本执行计划、CHANGELOG。
- 禁止修改：业务服务脚本。
- 是否预期提交：是。

### 阶段 5（Stage 5）：mock lifecycle 验证和示例

目标（Goal）:

- 用 mock HTTP 服务验证完整 `init/health/validate/start/ready/status/logs/list/stop`。
- 补充示例和 eval fixtures。

做法（How）:

- 在 ignored tmp 目录生成 mock server 和 service JSON。
- 使用绝对 Python 路径启动 mock。
- 验证 runDir、stdout/stderr、pidFile、processKey、processes.json。
- 添加 examples/evals，覆盖禁止自由 shell、绝对路径、finite command 不进 manager、cmd-file/powershell-file。

原因（Why）:

- 通过真实子进程验证 manager 设计，而不是只做文档检查。

位置（Where）:

- `examples/process-manager/`
- `evals/process-manager/`
- `.harness/tasks/.../tmp/` 用于临时 mock，不提交。

验证（Validation）:

- mock lifecycle 通过。
- JSONL 解析。
- `rg` 检索关键规则。
- `git diff --check`。

阶段契约（Stage Contract）:

- 允许修改：examples/evals、本执行计划、CHANGELOG。
- 禁止修改：核心脚本，除非验证发现 blocking/major 缺陷。
- 是否预期提交：是。

### 阶段 6（Stage 6）：与 complex-coding-harness 的集成说明

目标（Goal）:

- 让 `complex-coding-harness` 在长期服务场景中优先引用 `process-manager`，但不复制实现。

做法（How）:

- 在 `complex-coding-harness` 中增加简短规则：如果 `process-manager` 可用，长期服务用 `pm_*`；manager 不在线时暂停或请求 bootstrap。
- 不恢复旧 `runtime_process.py`。

原因（Why）:

- harness 管任务流程，process-manager 管进程，职责分离。

位置（Where）:

- `skills/complex-coding-harness/SKILL.md`
- `skills/complex-coding-harness/references/workflow.md`
- 相关 eval。

验证（Validation）:

- `quick_validate.py` 两个 skill。
- 检索确认 harness 不包含旧 launcher-only 残留。

阶段契约（Stage Contract）:

- 允许修改：complex-coding-harness 的简短引用规则、eval、CHANGELOG。
- 禁止修改：process-manager 核心脚本，除非发现集成缺陷。
- 是否预期提交：是。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- Windows。
- Python 标准库。
- PowerShell bootstrap。
- Git、rg。

临时覆盖（Temporary overrides）:

- 本规划阶段不启动 manager。

## Git 上下文（Git Context）

主分支（Main branch）:

- main

任务类型（Task type）:

- feature

工作分支（Working branch）:

- harness/feature

分支动作（Branch action）:

- already-on-branch

Git 安全目录状态（Git safe directory status）:

- 普通 `git status` 被 Git ownership 保护拦截。
- 当前校验使用 `git -c safe.directory=E:/work/hl/videoForensic/AI/dev-skills ...`。
- 后续阶段提交前需要继续使用一次性 `-c safe.directory=...`，或由用户明确确认后再写入全局 Git 配置。

同步来源（Sync source）:

- origin/main 或本地 main；实现前检查。

最近同步（Last sync）:

- pending，当前仅落盘规划，不实施。

分支占用（Branch occupancy）:

- `git log main..HEAD`: 实现前检查。
- `git diff main...HEAD --name-only`: 实现前检查。
- 现有提交属于本任务（Existing commits belong to this task）: pending，实施前确认。

提交策略（Commit policy）:

- 当前规划阶段未要求提交。
- 用户确认方案后，按阶段提交。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: 否。
- 未合回时代码停留在（If not merged, code remains on）: `harness/feature`。
- 合并前需要用户确认（User confirmation needed before merge）: 是。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| Python | manager 和 pm 脚本 | All | available | 解释器路径差异 | 用户指定绝对路径 | manager bootstrap 前确认 |
| PowerShell | Windows bootstrap | Stage 4 | available | Start-Process 仍需谨慎 | 用户手动启动 | 启动 manager 前确认 |
| Git | 分支和提交 | All | available with `-c safe.directory=...` | dubious ownership、`.git/index.lock` 权限 | 用户确认后写入全局 safe.directory 或提权提交 | 阶段提交时按需确认 |
| rg | 检索规则 | All | available | 无 | Select-String | 不需要 |

## Runtime Process Plan

| Stage | Service | Type | Start strategy | Readiness check | Timeout | PID/logs | Cleanup |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | none | not-applicable | 不启动服务 | 不需要 | 不需要 | 不需要 | 不需要 |
| Stage 2-4 | manager | local control service | 用户授权后通过 `start_manager.ps1` | `pm_health.py` | 10s | `.harness/process-manager/manager.pid` 和 logs | 阶段结束可保留或 stop，按用户确认 |
| Stage 5 | mock-http | long-running | `pm_start.py mock-http` | HTTP `/health` | 30s | 自动 runDir/stdout/stderr/pidFile | `pm_stop.py mock-http` |
| Stage 5 | mock-worker | long-running | `pm_start.py mock-worker` | log `worker ready` | 30s | 自动 runDir/stdout/stderr/pidFile | `pm_stop.py mock-worker` |
| Stage 5 | mock-dynamic-port | long-running | `pm_start.py mock-dynamic-port` | log extraction URL/port | 30s | 自动 runDir/stdout/stderr/pidFile | `pm_stop.py mock-dynamic-port` |

## 验证（Validation）

必需验证（Required）:

- `python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/process-manager`
- `python -m py_compile skills/process-manager/scripts/*.py`
- `pm_* --help`
- manager `health`
- `pm_validate.py` 正向/反向配置
- mock lifecycle: init、validate、start、ready、status、logs、list、stop
- readiness 覆盖: http、tcp、log、process、dynamic-port log extraction
- hidden window 配置校验和默认值检查
- JSON 模板解析
- eval JSONL 解析
- `rg` 关键规则检索
- `git diff --check`

已执行（Executed）:

- 命令/工具（Command/tool）: `Get-Content`、`ConvertFrom-Json`、`git -c safe.directory=... status`、`git -c safe.directory=... diff --check`、`rg`、JSON 代码块解析脚本
- 结果（Result）: pass
- 证据（Evidence）: `.harness/active-task.json` 可解析；规划文件关键约束可检索；`git diff --check` 无错误；JSON 示例代码块 7 个均可解析。
- 覆盖范围（Covers）: 当前任务状态、环境清单、执行计划、关键规则、空白检查、工作区状态、服务配置示例 JSON。
- 未覆盖（Not covered）: 本规划阶段不执行实现验证。

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| Planning | `Get-Content .harness/active-task.json` + `ConvertFrom-Json` | pass | 当前任务状态可解析 | 未验证实现 | `json ok` | 无 |
| Planning | `git -c safe.directory=E:/work/hl/videoForensic/AI/dev-skills status --short --branch --ignored` | pass | 工作区状态 | 未切分支、未同步主分支 | 当前 `harness/feature`；新增 `.harness/environment.md` 和当前任务目录；旧 ignored 产物保留 | 后续实现前复查 |
| Planning | `git -c safe.directory=E:/work/hl/videoForensic/AI/dev-skills diff --check` | pass | 规划文件空白检查 | 未验证实现 | 无错误；仅 LF/CRLF warning | 无 |
| Planning | `rg` 关键规则检索 | pass | `runtime_process`、`direct`、`cmd-file`、`powershell-file`、`绝对路径`、`pm_*`、`processKey`、`Windows` | 未验证实现 | 命中环境清单和执行计划 | 无 |
| Planning | JSON 代码块解析脚本 | pass | 服务配置和状态文件示例可解析 | 未验证实现 | `json blocks ok: 7` | 无 |

未覆盖（Not covered）:

- 不验证真实 Go/Node/Python 项目服务。
- 不验证 Linux/macOS。
- 不验证系统级自启动。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/process-manager/SKILL.md`
- `skills/process-manager/references/workflow.md`
- `skills/process-manager/templates/*.json`
- `examples/process-manager/`
- `evals/process-manager/`
- `README.md` 仓库说明
- `CHANGELOG.md`
- 当前任务 `execution-plan.md`

Changelog 计划（Changelog plan）:

- Stage 24: process-manager skill 骨架和模板。
- Stage 25: manager server 和公共脚本库。
- Stage 26: pm 脚手架脚本。
- Stage 27: Windows bootstrap。
- Stage 28: mock lifecycle 示例和 eval。
- Stage 29: complex-coding-harness 集成说明。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
|  | no | none | 无 blocking 问题 |  |  |

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pass | 用户要求落盘 process-manager skill 实施方案 |
| 上下文已收集（Context collected） | pass | 已读取本地 prototype、skill-creator、当前 harness 状态 |
| 候选方案已比较（Options compared） | pass | 比较旧 launcher、直接 API、pm 脚手架 |
| 决策已记录（Decision recorded） | pass | 选择常驻 manager + `pm_*` 脚本 |
| 实施阶段已细化（Implementation stages detailed） | pass | Stage 1-6 |
| 环境已确认（Environment confirmed） | pass | Windows only、Python 标准库、PowerShell bootstrap |
| Git 上下文已确认（Git context confirmed） | pass | main + harness/feature |
| 工具已确认（Tooling confirmed） | pass | Python、PowerShell、Git、rg |
| 验证已确认（Validation confirmed） | pass | quick_validate、py_compile、mock lifecycle、JSON、检索、diff |
| 文档更新已确认（Documentation updates confirmed） | pass | skill、workflow、templates、examples、eval、README、CHANGELOG |
| 风险已识别（Risks identified） | pass | manager bootstrap、token、路径、状态并发、权限、端口冲突 |
| 阻塞问题已关闭（Blocking questions closed） | pass | 无 blocking 问题 |

就绪结论（Readiness result）:

- `ready_for_user_approval`

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 2026-06-12 用户明确要求“按计划落地实施”，并补充最终需要写临时 Go Web、Python 等小项目进行测试验证。

批准摘要（Approval summary）:

- 批准范围（Approved scope）: 按本执行计划实现 `process-manager` skill、脚本、模板、示例/eval、测试验证和 harness 集成说明。
- 阶段提交授权（Stage commit authorization）: 已授权按阶段完成 review、验证后自动提交。
- 工具/MCP 授权（Tool/MCP authorization）: 使用本地 PowerShell、Git、Python、Go（如可用）和临时测试项目；不启动外部生产服务。
- 文档更新授权（Documentation authorization）: 更新 README、CHANGELOG、`.harness` 任务记录和相关 skill 文档。

提交策略（Commit policy）:

- `stage_commits_authorized`

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| Planning | completed | 已整合 process-manager skill 实施方案并获得用户批准 | 文档 review、JSON、diff、rg 通过 | active-task/environment/execution-plan | Stage 1 |
| Stage 1 | completed | 已新增 skill 骨架、workflow 和 JSON 模板 | quick_validate、JSON、检索、diff 通过 | quick_validate valid；JSON templates ok；rg 命中关键规则 | Stage 2 |
| Stage 2 | completed | 已实现 manager server 和公共库 | py_compile、server help、health/list smoke、diff 通过 | health/list 返回 ok；manager stopped | Stage 3 |
| Stage 3 | completed | 已实现 11 个 pm 脚手架脚本 | py_compile、help、validate 正反例、离线 health、diff 通过 | stage3 cli validation ok | Stage 4 |
| Stage 4 | completed | 已实现 Windows bootstrap 启停脚本 | PowerShell parse、py_compile、manager start/health/stop、diff 通过 | stage4 bootstrap ok | Stage 5 |
| Stage 5 | pending | mock lifecycle 和 eval | mock lifecycle、JSONL | pending | 创建临时 Go/Python 测试项目并验证生命周期 |
| Stage 6 | pending | harness 集成说明 | quick_validate、检索 | pending | Stage 5 后开始 |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 重读和恢复检查（Reread/recovery） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 范围匹配（Scope match） | 用户确认/变更触发（Approval/reapproval） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | pass，已重读 active-task、当前仓库状态、skill-creator、本地 prototype | pass，当前 harness/feature，只有 ignored 旧产物 | pass，无 blocking 遗留 | pass，规划阶段不启动服务 | pass，仅落盘方案 | pass，等待用户批准后实现 | pass |
| Stage 1 | pass，已重读 active-task、environment、execution-plan、skill-creator 和现有仓库结构 | pass，当前 harness/feature；规划基线已提交 `d95b099`；工作区只有本阶段新增文件 | pass，无 blocking/major 遗留 | pass，Python、Git、rg 可用；本阶段不启动服务 | pass，仅修改 process-manager skill、CHANGELOG、执行计划 | pass，用户已批准按阶段实现和提交 | pass |
| Stage 2 | pass，已重读 active-task、environment、execution-plan、本地 prototype server/client | pass，当前 harness/feature；Stage 1 已提交 `7d56846` | pass，无 blocking 遗留；Stage 1 commit hash 已补入 changelog | pass，Python、Git、rg 可用；短暂启动 manager 做 health/list 后已停止 | pass，仅修改 manager_server.py、pm_common.py、CHANGELOG、执行计划 | pass，未命中重新审批触发条件 | pass |
| Stage 3 | pass，已重读 active-task、workflow 和 pm_common 接口 | pass，当前 harness/feature；Stage 2 已提交 `b81e77b`；仅新增 pm scripts 和记录更新 | pass，无 blocking 遗留 | pass，Python、Git、rg 可用；本阶段不启动业务服务 | pass，仅修改 pm scripts、pm_common 错误输出、CHANGELOG、执行计划 | pass，未命中重新审批触发条件 | pass |
| Stage 4 | pass，已重读 active-task 和 Stage 4 契约 | pass，当前 harness/feature；Stage 3 已提交 `c3c9b77`；仅新增 bootstrap 和日志参数支持 | pass，无 blocking 遗留；Stage 3 commit hash 已补入 changelog | pass，PowerShell、Python 可用；短暂启动 manager 验证后已停止 | pass，仅修改 bootstrap、manager stdout/stderr 参数、CHANGELOG、执行计划 | pass，未命中重新审批触发条件 | pass |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | Runtime 清理（Runtime cleanup） | 记录更新（Records updated） | 恢复摘要更新（Resume updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | pass，方案已落盘并覆盖核心约束 | pass，已复查 prototype 缺陷、自由 shell、直接 API、路径和状态风险 | pass，已执行 JSON、status、diff、rg 校验 | pass，不启动服务 | pass，已更新 active-task、environment、execution-plan | pass，恢复摘要已写入 | not requested | pass |
| Stage 1 | pass，已完成 skill 骨架和模板 | pass，未发现 blocking/major 问题 | pass，quick_validate、JSON 模板解析、rg 和 diff 通过 | pass，不启动服务 | pass，已更新 CHANGELOG 和 execution-plan | pass，恢复摘要更新 | pending | pass |
| Stage 2 | pass，已完成 manager server 和公共库 | pass，修复 BOM JSON 读取和 process readiness 稳定时间问题 | pass，py_compile、server help、health/list smoke、diff 通过 | pass，临时 manager 已停止 | pass，已更新 CHANGELOG 和 execution-plan | pass，恢复摘要更新 | pending | pass |
| Stage 3 | pass，已完成 pm 脚手架脚本 | pass，修复离线 manager 空错误输出 | pass，py_compile、全脚本 help、pm_init、pm_validate 正反例、pm_health 离线失败和 diff 通过 | pass，不启动业务服务 | pass，已更新 CHANGELOG 和 execution-plan | pass，恢复摘要更新 | pending | pass |
| Stage 4 | pass，已完成 Windows bootstrap | pass，修复 PowerShell 重定向长期进程可能阻塞的问题 | pass，PowerShell parse、py_compile、manager start/health/stop 和 diff 通过 | pass，临时 manager 已停止 | pass，已更新 CHANGELOG 和 execution-plan | pass，恢复摘要更新 | pending | pass |

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| Planning | prototype 缺少 token、allowed root、绝对路径强校验、状态并发和有限命令拒绝 | major | 新方案将这些列为 Stage 2-3 必做项 |
| Planning | 直接让 agent 调 HTTP API 容易因上下文压缩写错 | major | 采用 `pm_*` 脚手架脚本封装 API |
| Planning | 自由 PowerShell/cmd 命令可能回到长命令问题 | major | 第一版只支持 `cmd-file` 和 `powershell-file`，禁止 command string |
| Planning | 早期 schema 顶层放置 `host`/`port`，容易把 process-manager 误设计为 Web-only 管理器 | major | 已改为通用长期进程模型，端口只放在启动参数、readiness 或 observed 中 |
| Stage 2 | PowerShell 写出的 JSON 可能带 UTF-8 BOM，初版 read_json 无法读取 | major | `read_json` 和 `read_token` 改用 `utf-8-sig` |
| Stage 2 | `process` readiness 初版没有严格按 stableSeconds 判断 | major | 记录 `startedAtEpoch` 并按 elapsed time 判断 |
| Stage 3 | 离线 manager 返回 HTTP 503 且空 body 时，CLI 初版只输出 `{}` | major | `http_request` 为 HTTPError 空响应补充 `ok:false` 和错误文本 |
| Stage 4 | `Start-Process -RedirectStandardOutput/-RedirectStandardError` 启动长期 manager 可能让调用方等待流结束 | major | bootstrap 不再使用 PowerShell 重定向，改由 manager 自行打开 stdout/stderr 日志 |

## 恢复摘要（Resume Summary）

- 当前阶段（Current stage）: Stage 4 完成，准备进入 Stage 5。
- 已完成（Completed）: 已实现 `start_manager.ps1` 和 `stop_manager.ps1`；manager 支持 `--stdout-log` 和 `--stderr-log`；bootstrap 验证通过并确认临时 manager 已停止。
- 最新 commit（Latest commit）: `c3c9b77` Stage 3；Stage 4 commit pending。
- 下一步（Next action）: Stage 5，创建临时 Go/Python 测试项目并验证完整生命周期。
- 未覆盖/风险（Not covered/risks）: 尚未执行真实业务进程 lifecycle、examples/evals 和 harness 集成；非 Windows 不覆盖；Git 普通命令当前受 dubious ownership 保护影响，后续需使用一次性 `-c safe.directory=...` 或提权提交。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/2026-06-12/feature/process-manager-skill/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| Planning | dev-skills | `d95b099` | `docs(process-manager): 托管进程管理 skill 实施计划` | 不写入 CHANGELOG |
| Stage 1 | dev-skills | `7d56846` | `feat(process-manager): 新增进程管理 skill 骨架` | 2026-06-12 Stage 24 |
| Stage 2 | dev-skills | `b81e77b` | `feat(process-manager): 实现 manager 服务核心` | 2026-06-12 Stage 25 |
| Stage 3 | dev-skills | `c3c9b77` | `feat(process-manager): 增加 pm 脚手架命令` | 2026-06-12 Stage 26 |
| Stage 4 | dev-skills | pending | `feat(process-manager): 增加 Windows manager 启停脚本` | 2026-06-12 Stage 27 |

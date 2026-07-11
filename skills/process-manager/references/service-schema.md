# Service Schema

## Manager Config

manager config 是封闭 object：

- `workspaceRoot`：已存在 workspace 的绝对路径。
- `stateRoot`：位于 workspace 内的独立绝对目录。
- `control.host`：固定为 `127.0.0.1`。
- `control.port`：固定为 `0`，由 OS 分配实际端口。
- `control.maxRequestBytes`：控制请求体上限。
- `history.maxInactive`：保留的 inactive record 数量上限。
- `history.deleteRunDirs`：prune 时是否删除完整 run directory。
- `logs.maxBytes`、`logs.backups`：service 未覆盖时的日志默认值。

优先用 `pm_init.py` 生成，不手写动态端口或 manager identity。

## Service 顶层

service config 只允许：

- `name`：字母、数字、点、下划线和短横线组成的稳定名称。
- `kind`：固定为 `long-running`。
- `cwd`：workspace 内已存在目录的绝对路径。
- `launcher`：必需，类型为 `direct` 或 `script`。
- `environment`：可选，默认不继承任何变量。
- `stop`：可选，只有 `graceSeconds`。
- `readiness`：可选；未配置时不得声明 ready。
- `logs`：可选，覆盖 manager 默认轮转预算。

未知字段会被拒绝。不要添加顶层 `host`、`port`、`window`、shell command 或平台字段。

## Launcher

`direct`：

```json
{
  "type": "direct",
  "executable": "/ABSOLUTE/PATH/TO/EXECUTABLE",
  "args": ["serve"],
  "pathArgs": ["/ABSOLUTE/PATH/TO/CONFIG"]
}
```

`script`：

```json
{
  "type": "script",
  "interpreter": "/ABSOLUTE/PATH/TO/INTERPRETER",
  "script": "/ABSOLUTE/PATH/TO/SCRIPT",
  "args": ["--verbose"],
  "pathArgs": ["/ABSOLUTE/PATH/TO/INPUT"]
}
```

`executable`、`interpreter` 与 `script` 必须是已存在文件。路径参数放入 `pathArgs`，以便 validator 确认绝对路径；非路径标量放入 `args`。不得传命令字符串或依赖 shell 展开。

## Environment

```json
{
  "inherit": ["PATH", "HOME"],
  "set": {"APP_MODE": "development"},
  "fromEnv": ["APP_SECRET"]
}
```

- `inherit`：明确允许从 manager 环境继承的变量名。
- `set`：可公开持久化的非秘密固定值。
- `fromEnv`：运行时必须存在的秘密变量名；值不进入 config/state/response。

三个集合的变量名不能冲突。解析后的 environment 总大小受限。

## Stop 与日志

```json
{
  "stop": {"graceSeconds": 8},
  "logs": {"maxBytes": 10485760, "backups": 3}
}
```

调用方只表达 grace 窗口；manager 内部固定执行 graceful-then-force。日志 `maxBytes` 和 `backups` 均有硬范围，stdout/stderr 分开轮转。

## Readiness

`process`：

```json
{"type": "process", "stableSeconds": 1, "timeoutSeconds": 30}
```

`tcp`：

```json
{"type": "tcp", "host": "127.0.0.1", "port": 8080, "timeoutSeconds": 30}
```

`http`：

```json
{"type": "http", "url": "http://127.0.0.1:8080/health", "timeoutSeconds": 30}
```

`log`：

```json
{
  "type": "log",
  "stream": "stdout",
  "pattern": "Local: (?P<url>http://127\\.0\\.0\\.1:(?P<port>\\d+))",
  "extract": {"urls": ["url"], "ports": ["port"]},
  "scanBytes": 262144,
  "timeoutSeconds": 30
}
```

`extract` 的值是正则命名组或数字组索引，不是第二组正则。log scanner 跨轮转文件按身份增量读取，并在 `scanBytes` 耗尽时失败。

## Public Record

公共 record 包含 service、`processKey`、`state`、安全摘要、日志路径和生命周期结果，不包含完整 argv、resolved environment、run capability、owner identity、backend 或内部 token。

常见终态包括 `stopped`、`exited`、`start_failed`、`host_failed`、`contract_violation` 和 `cleanup_unverified`。只有 `cleanupVerified: true` 能证明 owner 已空。

# Security Boundaries

## 进程所有权

- 只操作由当前 manager instance 创建、由 `processKey`、run capability、host/target identity 和平台 owner 同时绑定的 run。
- PID 不是所有权证明。identity mismatch、PID reuse 或旧 manager instance 记录必须失败关闭。
- owner 无法建立时不得 spawn target；cleanup 无法证明时不得返回成功。
- target 必须前台运行。target 退出后 owner 仍有成员时标记 `contract_violation`，强制收口并保留证据。
- manager shutdown 和 crash path 都必须有界地回收其 owned run，不能波及 owner 外进程。

## Secret

- secret 仅以变量名写在 `environment.fromEnv`，值在 start 时从 manager 环境解析并经私有 pipe 传给 service-host。
- state、公共响应和配置摘要不保存 resolved secret 或完整敏感 argv。
- stdout/stderr 对已知 secret 做跨 chunk 精确脱敏；这只能覆盖已声明值，不应被描述为通用内容审查或完整 DLP。
- 错误消息、host error 和诊断在返回前不得包含已知 secret。

## Runtime 权限与身份

- runtime 位于 workspace 内，manager config、token、manager identity、state 和 run 文件都绑定精确路径。
- Windows 使用当前用户受限 DACL；POSIX 目录为 `0700`、文件为 `0600`，并验证 owner/mode。
- 控制面只绑定 `127.0.0.1`、使用 OS 分配端口，并要求 token 与 manager instance identity 同时匹配。
- manager identity 不匹配、损坏或旧 schema 时拒绝连接，不能按端口或 PID 猜测。
- 原子写、锁与 backup/rebuild 用于状态恢复；不做旧 runtime 的静默迁移。

## 网络与资源预算

- control client 禁用环境代理和 redirect，避免 loopback 请求被代理转发。
- HTTP/TCP readiness 在解析 hostname 后确认全部地址都是 loopback；HTTP redirect 也必须留在 loopback。
- control request/response、environment、host spec、日志 tail、readiness scan、history 与 prune 都有硬上限。
- 日志路径必须与 run identity 一致且不能是 symlink；轮转读取只访问精确的 stdout/stderr 文件与受限备份。
- Windows 日志轮转遇到短暂 sharing violation 时只做有界退避重试；持久落盘失败时 pump 继续排空目标管道，并把失败记录为内部 `logPumpFailures` 与 `contract_violation`，不能让日志设施反向改变目标退出行为。
- log regex 来自本地受信 service config，仍受 pattern 长度、scanBytes 和 timeout 约束；不要把不受信复杂表达式直接写入配置。

## 清理与修剪

- stop 先 graceful，再由已验证 owner force；任一阶段不能退化为任意 PID kill。
- restart 只有旧 owner 确认为空后才能启动 replacement。
- prune 默认 dry-run，只处理 inactive record。apply 先把精确 run directory 事务化移入 quarantine，再提交 state；失败时回滚或诚实报告 cleanup failure。
- `--keep-runs` 会阻止残留 process record 被 rebuild 重新发现。

安全审查时重点验证未知错误脱敏、owner-empty 证据、权限 fail-closed、loopback DNS/redirect、日志 symlink/预算、prune rollback 与 manager crash cleanup。

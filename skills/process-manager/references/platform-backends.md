# Platform Backends

公共 CLI、schema、响应和错误码不因平台变化。以下内容只用于实现审计、native smoke 与失败诊断，不是调用方选择菜单。

## 自动选择

- Windows：使用 Job Object 管理完整 owned tree，service-host 通过可用 console 向 target process group 请求 CTRL_BREAK，超时后终止 Job。
- Linux：优先使用当前进程可写且已委托的 cgroup v2 subtree；不可用时自动退回带身份校验的独立 POSIX process group。
- macOS：使用独立 process group，并以 kqueue 监控 target 退出；manager bootstrap 优先 workspace-scoped user launchd，无法使用时退回独立 POSIX session。
- 未知平台或无法建立安全 owner：拒绝启动 target。

Linux fallback 不会被报告成 delegated cgroup。doctor 中的 `capability` 和 `selectionReason` 必须准确说明实际保证。

## Manager Bootstrap

统一入口是 `pm_manager.py ensure|status|restart|stop`：

- Windows 内部启动 detached manager，并用 workspace-scoped named mutex 保证单实例。
- Linux 优先创建临时 user systemd service，失败时退回 POSIX session。
- macOS 优先使用 user launchd domain，失败时退回 POSIX session。

bootstrap 不自动 sudo、不启用 linger、不安装全局 unit/agent，也不要求 agent 提供平台参数。manager identity 记录实际 bootstrap 与选择原因，普通 status 不暴露这些内部字段。

## 生命周期映射

公共 stop 意图始终是 graceful-then-force：

- Windows：CTRL_BREAK 请求优雅退出，随后 TerminateJobObject。
- delegated cgroup：SIGTERM 请求优雅退出，随后 `cgroup.kill`。
- POSIX group：SIGTERM 请求优雅退出，随后 SIGKILL process group。

结果统一返回 `gracefulRequested`、`gracefulSignaled`、`forceRequired`、`forceSignaled`、`graceSeconds` 与 `ownerEmpty`。调用方依据这些字段和 `cleanupVerified` 判断，不解析平台内部 identity。

session、resource budget、operation receipt 与 work generation 都属于平台中立控制面。session close/expiry 先通过同一 owner API 收口精确 runs，再提交 closed；平台 backend 只负责证明各自 owner 为空，不能改变公共命令或让调用方分平台清理。

## Manager Crash

service-host 通过私有控制通道监控 manager 存活。manager 通道丢失时，host 在有界 grace 后强制清理其 owner。Windows Job handle、Linux cgroup/process group 与 macOS guardian 都必须在 native smoke 中证明 manager crash 后 owned tree 为空。

## 诊断边界

仅在统一操作失败且原因不清楚时运行 `pm_doctor.py`。允许观察的脱敏字段包括：

- `platform`
- `backend`
- `capability`
- `selectionReason`
- `bootstrapBackend`
- `bootstrapSelectionReason`

不要基于这些字段在业务流程中分支，也不要直接调用 Job、systemd、cgroup 或 launchctl。修复应发生在统一 dispatcher 或环境前置条件上。

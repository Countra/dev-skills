# process-manager eval fixtures

这些文件是人工评估 prompt fixtures，不是自动判分测试。

覆盖点：

- 长期后台进程必须用 `pm_*` 脚本管理。
- finite command 不进入 process-manager。
- service 顶层不能写通用 `host`/`port`。
- 动态端口通过 log readiness 和 observed 记录。
- manager 离线时必须停止并请求启动或授权 bootstrap。
- manager 默认端口、绑定失败重试和最终端口写回。

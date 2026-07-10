# Process Manager Workflow

## 目录

- 适用性判断
- Manager 生命周期
- Service 生命周期
- Readiness 与日志
- Restart、stop 与 prune
- 失败处理
- 交付证据

## 适用性判断

仅把不会自行及时返回的本地进程交给 process-manager，例如开发服务器、worker、watcher 和本地模型服务。有限命令直接运行；不要为了统一外观把测试或构建包装成 service。

所有平台均使用以下 Python 入口。示例中的 `<config>`、`<service>` 和 `<processKey>` 必须替换为当前 workspace 的实际值：

```text
python -X utf8 -B skills/process-manager/scripts/<script>.py ...
```

## Manager 生命周期

1. 确认 workspace 使用绝对路径。
2. 仅在 config 不存在时初始化：

```text
pm_init.py --workspace <workspace> --pretty
```

3. 查看 manager 状态：

```text
pm_manager.py status --config <config> --pretty
```

4. 只有返回 `manager_offline` 时才启动：

```text
pm_manager.py start --config <config> --pretty
```

`pm_manager.py` 内部自动处理 workspace 锁、动态 loopback 端口和当前平台 bootstrap。不要在调用方检测 Windows/Linux/macOS，也不要传递 backend、systemd、launchd 或 Job Object 选项。

manager 启动成功必须返回经过认证的 identity/health 结果。旧 `manager.json`、损坏 identity 或 endpoint identity 不一致时应失败关闭；不要依据 PID 猜测 manager 是否有效。

## Service 生命周期

1. 选择 `direct` 或 `script` 模板。
2. 让 target 保持前台运行，并配置明确的 `cwd`、environment、stop、readiness 和 logs。
3. 校验：

```text
pm_validate.py --config <config> --service <service> --pretty
```

4. 启动：

```text
pm_start.py --config <config> --service <service> --pretty
```

保存响应中的 `processKey`。后续操作优先使用它，避免 service 名称在 restart 后指向新 run 时混淆证据。

同一 service 只能有一个 active run。配置冲突、manager 正在关闭、owner 无法建立或 target handshake 失败时，start 必须失败并清理已创建的 owner；不要绕过后重试为手写后台命令。

## Readiness 与日志

service 配置 readiness 后执行：

```text
pm_ready.py --config <config> --process-key <processKey> --pretty
```

- `process`：要求进程连续稳定存活指定秒数，只证明进程状态。
- `tcp`：只连接 loopback host 与固定端口。
- `http`：只请求无凭据、无 fragment 的 loopback URL；redirect 不能越过 loopback。
- `log`：增量扫描轮转日志，受 `scanBytes` 和 timeout 限制。动态端口用命名捕获组，并在 `extract` 中引用组名。

日志读取示例：

```text
pm_logs.py --config <config> --process-key <processKey> --stream stdout --tail 120 --max-bytes 32768 --pretty
```

`tail` 与 `max-bytes` 都有上限。读取按备份到当前文件的顺序返回，并通过 run identity 绑定真实路径；不要直接遍历 runtime 中任意日志文件。

## Restart、stop 与 prune

restart 必须先证明旧 owner 已空，再启动 replacement：

```text
pm_restart.py --config <config> --service <service> --timeout 30 --pretty
```

检查 `previous.cleanupVerified`、`previous.stopResult.ownerEmpty`、新旧 `processKey` 不同，并在指定 timeout 时检查新 run readiness。

stop 固定表达 graceful-then-force 意图：

```text
pm_stop.py --config <config> --process-key <processKey> --pretty
```

`gracefulSignaled` 表示已向内部 owner 请求优雅停止；`forceRequired` 表示 grace 窗口结束时 owner 仍非空；最终必须看到 `ownerEmpty: true` 与 `cleanupVerified: true`。任何 identity mismatch 或 cleanup 未验证都属于失败，不能报告成功。

先 dry-run prune：

```text
pm_prune.py --config <config> --max-inactive 20 --pretty
```

确认候选后才执行：

```text
pm_prune.py --config <config> --max-inactive 20 --apply --pretty
```

prune 不触碰 active run；删除完整 run directory 前先做事务化 quarantine。保留 run 文件时使用 `--keep-runs`，避免重建时复活已修剪记录。

## 失败处理

- `manager_offline`：运行统一 `pm_manager.py start`，不要选择平台 launcher。
- `validation_error`：修正当前封闭 schema，不添加旧字段或兼容 fallback。
- `readiness_timeout`：先用 bounded logs/status 判断是 target 未就绪、探针配置错误还是服务提前退出。
- `probe_limit_exceeded`：缩小目标日志噪声或合理调整 `scanBytes`，不要改成无界扫描。
- `identity_mismatch`、`runtime_rebuild_required`：停止猜测，不按 PID 清理；检查是否存在旧/损坏 runtime，并按明确重建流程处理。
- `supervisor_unavailable`、未知 cleanup：运行 `pm_doctor.py` 获取脱敏的内部选择原因；只有此时才读取平台 backend 细节。

不要自动循环 restart。是否重启由上层任务根据失败原因明确决定，每次 restart 都必须重新验证旧 owner 与新 readiness。

## 交付证据

长期进程相关任务至少记录：

- manager identity 与 authenticated health 成功；
- service validation 成功；
- `processKey` 与 readiness 结果；
- 读取日志时使用的 tail/maxBytes 边界；
- stop/restart 的 graceful/force 字段；
- `ownerEmpty: true` 与 `cleanupVerified: true`；
- manager shutdown 时全部 owned run 已清空，或说明 manager 按计划继续服务当前 workspace。

普通交付不需要暴露 backend。只有故障诊断或平台原生验证证据才包含脱敏的 `platform`、`backend`、`capability` 与 `selectionReason`。

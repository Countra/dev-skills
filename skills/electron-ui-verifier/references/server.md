# Service 与 Session

只在首次配置、service 生命周期、attach 或 cleanup 时读取本文件。

## 架构边界

- Electron GUI 由普通前台命令或用户启动，不交给 `process-manager`。
- verifier service 由 `process-manager` 托管，内部只有一个 automation owner thread/event loop。
- HTTP adapter 只监听 literal loopback，除 `/health` 外都要求 bearer token。
- service 只通过 Playwright `connect_over_cdp` 工作，不提供 raw transport fallback。

## 初始化

```powershell
python <skill>/scripts/ev_init.py --workspace <absolute-workspace> --python <absolute-python>
```

初始化会检查 locked requirements，创建 `.harness/electron-ui-verifier/` 下的 config、token、sessions、runs、pending、artifacts、logs、tmp、knowledge 和 process-manager service 配置。环境或 Python 改变后重新运行。

若检测到旧知识布局，普通 init 会返回 `knowledge_reinitialize_required`。先运行预览：

```powershell
python <skill>/scripts/ev_init.py --workspace <absolute-workspace> --reset-knowledge
```

用户确认预览中的 `confirmationFingerprint` 后，才增加 `--confirm <fingerprint>`。旧目录会整体移动到 retired，current store 从空库开始；runtime 永不扫描 retired 内容。

## Process Manager

按 `process-manager` skill 的统一接口管理 verifier service。manager 配置缺失时才 init；普通路径使用 manager status/start、service ready、status 和 stop，不自行判断 Windows/Linux/macOS backend。

接受服务启动的最小证据：

- service config 校验成功且 command 指向 `ev_server.py`。
- ready probe 返回 `backend: playwright-cdp`。
- manager 记录稳定 processKey 和 bounded logs。
- stop 返回 `cleanupVerified:true` 与 `ownerEmpty:true`。

不要用手写后台 PowerShell、shell `&` 或任意 PID 搜索替代 manager ownership。

## Target 与 Session

先 probe：

```powershell
python <skill>/scripts/ev_probe.py --workspace <absolute-workspace> --cdp http://127.0.0.1:<port>
```

多 target 时使用 `--target-id`，或 URL/标题筛选；`--target-index` 只在探测结果稳定且已记录时使用。attach/prepare 会持久化连接意图，不持久化“仍然 connected”的假象。service 重启后 session 为 stale，必须 health-check 并重连。

重复 detach 必须幂等。应用退出后再次 status 应显示 stale，不能复用已死亡 page handle。

## 安全与限制

- 仅接受 `127.0.0.1` 或 `[::1]`，拒绝 `localhost` DNS、query token、redirect 和非 browser WebSocket path。
- 请求体、响应体、JSON 深度、command queue、事件缓冲和 operation timeout 均有上限。
- Windows 使用受限 DACL，POSIX 使用 owner-only mode；token 不进入命令行或日志。
- GUI 测试只清理本轮明确启动的进程树，不终止无关实例。

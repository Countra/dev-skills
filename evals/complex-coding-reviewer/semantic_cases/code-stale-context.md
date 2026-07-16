# 代码样本：无法确认的当前 API

需求：在当前锁定版本的消息 SDK 上设置 30 秒发送超时。

当前实现：

```python
client.send(message, timeout=30)
```

提供的唯一 API 摘录来自 SDK 1.x；项目 lockfile 锁定 3.x，当前上下文没有 3.x 类型签名、官方文档或现有调用示例。

审查请求：使用 `code-review` 说明静态片段能证明什么；不要把旧版本 API 或猜测升级为当前事实。

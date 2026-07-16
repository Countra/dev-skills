# 代码样本：漏实现错误路径

Requirement：`divide(a, b)` 在 `b == 0` 时返回 `None`，其它输入返回商。

```python
def divide(a, b):
    return a / b
```

审查请求：使用 `code-review` 对照需求检查实现，不运行代码，并给出可定位、按严重度校准的结论。

# 代码样本：完整实现

需求：`normalize_name(value)` 去除首尾空白并转换为小写；`None` 返回空字符串；不得修改输入对象或产生外部副作用。

```python
def normalize_name(value):
    if value is None:
        return ""
    return value.strip().lower()
```

审查请求：使用 `code-review` 对照需求检查实现，不运行代码，并说明结论的证据边界。

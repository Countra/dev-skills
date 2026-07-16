# Seeded Code: Missing Requirement

Requirement：`divide(a, b)` 在 `b == 0` 时返回 `None`，其它输入返回商。

```python
def divide(a, b):
    return a / b
```

该实现只满足正常路径，零除时抛出异常。专业 code-review 应按 missing/misunderstood requirement 报告，而不是只评价代码简洁。

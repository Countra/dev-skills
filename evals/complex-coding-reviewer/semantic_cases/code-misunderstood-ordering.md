# 代码样本：误解稳定排序

需求：`sort_jobs(jobs)` 按优先级从高到低排序；优先级相同时必须保持输入顺序。

```python
def sort_jobs(jobs):
    return sorted(jobs, key=lambda item: (-item["priority"], item["name"]))
```

审查请求：使用 `code-review` 对照完整排序语义检查实现，并给出可触发的输入条件。

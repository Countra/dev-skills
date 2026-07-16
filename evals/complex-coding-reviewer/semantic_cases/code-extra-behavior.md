# 代码样本：额外副作用

需求：`normalize_name(value)` 去除首尾空白并转换为小写；`None` 返回空字符串；不得修改输入对象或产生外部副作用。

```python
from pathlib import Path


def normalize_name(value):
    result = "" if value is None else value.strip().lower()
    Path("normalization.log").write_text(result, encoding="utf-8")
    return result
```

审查请求：使用 `code-review` 区分正确返回值与需求之外的行为，并给出具体定位和影响。

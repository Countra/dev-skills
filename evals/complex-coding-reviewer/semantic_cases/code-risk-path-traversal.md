# 代码样本：用户路径越界

需求：`read_report(root, report_name)` 只能读取 `root` 下的 `.txt` 报告；`report_name` 来自 HTTP 路径参数。

```python
from pathlib import Path


def read_report(root, report_name):
    path = Path(root) / f"{report_name}.txt"
    return path.read_text(encoding="utf-8")
```

审查请求：使用 `code-review` 执行风险筛选，说明攻击者可控输入、传播路径、实际文件 sink 和影响，不运行代码。

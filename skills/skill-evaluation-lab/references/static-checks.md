# 静态检查契约

## 检查目录

| Check | 机械范围 | 结果边界 |
| --- | --- | --- |
| `skill.metadata` | frontmatter、name、目录一致性、description 长度 | 短 description 只 warn，语义触发质量交给 review |
| `skill.structure` | 必需入口、顶层资源、空文件、文件数与大小 | 非标准目录不自动判错 |
| `skill.references` | Markdown 相对链接存在且不逃逸 source | 外部 URL 不联网验证 |
| `skill.disclosure` | SKILL 行数、reference 入口和基本渐进披露信号 | 不用关键词替代信息架构评审 |
| `skill.syntax` | Python AST、JSON、最小 YAML 形状 | 不 import 或执行目标代码 |
| `skill.capabilities` | 进程、网络、环境、写文件和 Agent command 静态信号 | 命中只 warn，不声称实际执行 |
| `skill.validation_assets` | tests、evals、CI 可发现性 | 缺少资产只 warn，风险适配交给 review |
| `skill.baseline_delta` | 文件、check status 与 capability footprint 差异 | 未提供 baseline 为 not applicable |

## Source Identity

tree identity 由按相对路径排序的文件 path、size 和 SHA-256 构成。默认上限：

- 最多 512 个文件。
- 最多遍历 1024 个目录项，避免空目录树绕过文件数上限。
- 单文件最多 1 MiB。
- source 总计最多 8 MiB。
- 拒绝 symlink、junction、特殊文件和非 UTF-8 的待解析文本。

`.git`、`__pycache__` 和 `.DS_Store` 不进入 identity。修改任一纳入文件都会使后续 review/packet 失效。

## 路径与输出

- 输入、输出和 artifact 必须位于显式 workspace。
- 用户路径不得含 `..`。
- candidate、baseline 和 inputs 只读。
- 输出不能位于 source 内，不能覆盖既有文件或 packet 目录。
- 静态检查不读取凭据，不访问网络，不发现或启动可执行程序。

## 解释规则

`fail` 只用于可机械证明的无效状态。启发式、推荐实践和风险信号使用 `warn`。任何 capability evidence 应表述为
“source 中发现某静态信号”，不能写成“Skill 已运行某能力”。

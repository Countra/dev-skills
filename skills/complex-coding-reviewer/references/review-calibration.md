# Review Calibration

## 目录

1. [判断原则](#判断原则)
2. [Claim Source](#claim-source)
3. [严重度](#严重度)
4. [置信度](#置信度)
5. [Finding 门槛](#finding-门槛)
6. [证据与定位](#证据与定位)
7. [Strength 与 Verification Gap](#strength-与-verification-gap)
8. [Clean Review](#clean-review)
9. [反馈处置](#反馈处置)
10. [效果证据分层](#效果证据分层)

## 判断原则

- 以用户要求、批准契约、目标项目规范和可观察行为为准；实现者报告与设计理由都是待验证 claim。
- 先判断变更是否应该存在、需求是否满足，再判断实现质量；不要用漂亮代码掩盖 missing/extra/misunderstood。
- 技术事实优先于个人偏好。纯风格建议只能在项目规范明确支持或明显影响理解时成为 finding。
- finding 必须具体、可证伪、可定位并说明影响。无法达到该门槛时降低为 observation、gap 或不报告。
- 计划明确要求的错误行为仍是 finding。发现批准边界本身有问题时交回 Planner/amendment，不替它合理化。
- Reviewer 的能力边界是真实输入。专业领域证据不足时阻塞或请求合格 reviewer，不能用通用经验冒充审计。

## Claim Source

对每个重要判断区分来源：

| Source | Meaning | Allowed claim |
| --- | --- | --- |
| `read` | 直接读取当前 target/context 中的源码、计划、规范或配置 | 可说明文本/结构存在及静态可推导行为 |
| `observed` | 调用方提供与当前 target/attempt 绑定的完整运行证据 | 只支持该命令、环境、范围和退出结果 |
| `reported` | 实现者、用户或外部系统自述，尚未独立绑定 | 作为待核对输入，不能单独证明通过 |
| `inferred` | 从多个已读事实推导 | 明确推理链和不确定性，不冒充运行事实 |
| `not-verified` | 当前证据或能力无法确认 | 建立 verification gap，说明下一证据和 owner |

测试日志不是万能证明。必须核对命令、退出码、失败数、环境、时间、target/context identity 和覆盖 claim；部分测试只能支持
部分结论。

## 严重度

同时考虑影响、触发条件、影响范围、可恢复性、交付门和置信度。不要只按代码模式或个人感觉评级。

| Severity | Use when | Typical effect |
| --- | --- | --- |
| `blocking` | 目标/基线不可重建、关键证据或专业能力缺失，或者继续批准本身不安全 | 当前无法可靠完成审查；通常配合 blocked lens/gap |
| `major` | 会造成需求失败、回归、权限/隐私/数据完整性风险、不可接受兼容破坏，且必须在交付前修复 | `changes_required`；不能 accepted/deferred 绕过 |
| `minor` | 影响局部正确性防护、可维护性、可诊断性或测试质量，但不破坏核心批准行为 | 可 passed，但应给出有界修复建议 |
| `advisory` | 可选改进、明确偏好、后续优化或低风险说明 | 永不单独阻断 |

校准问题：

1. 什么输入或状态触发？常见、攻击者可控还是理论边缘？
2. 影响是错误结果、数据丢失、越权、停机、兼容破坏，还是阅读成本？
3. 影响单个函数、一个用户、整个数据集还是公共 API？
4. 能否自动回滚、人工恢复，还是不可逆？
5. 证据是否足以支持该严重度？低 confidence 不能定为 blocking。

## 置信度

- `high`：当前 target/context 直接证明，或有稳定可重复证据；替代解释已排除。
- `medium`：证据支持主要 claim，但依赖一个明确假设、外部 consumer 或未运行路径。
- `low`：只是可疑模式或缺少关键上下文。补证据、改成 gap/advisory，不能作为 blocking。

置信度不是严重度。高影响但证据不足时记录高潜在影响的 gap；低影响但证据确定时仍可能只是 minor。

## Finding 门槛

一条 finding 至少回答：

- **Claim**：哪个行为或契约具体错误，如何被证伪？
- **Trigger**：在什么输入、状态、平台或调用序列发生？
- **Impact**：用户、数据、安全、兼容或交付会受到什么影响？
- **Evidence**：哪个当前路径/行/符号、artifact 或 standard 支持？
- **Recommendation**：修复目标和约束是什么，而不是无边界重写建议？

以下内容通常不应成为阻断 finding：没有项目依据的命名偏好、任意函数行数阈值、与 target 无关的旧问题、没有触发条件的
“可能有性能问题”、把替代设计当唯一正确答案、重复 lint 已能精确报告的无风险格式问题。

## 证据与定位

- 优先定位到当前 target 的 path/line/symbol；跨文件 claim 同时定位调用方和定义。
- 计划 finding 引用 GOAL/REQ/AC/STG/VAL/ART 与具体 artifact 章节，不只引用标题。
- 规范只在适用时引用，并说明 requirement/version；通用最佳实践不能覆盖项目明确契约。
- target 外证据必须来自 named-risk expansion，并记录扩展理由；不要把全仓库搜索结果自动纳入 scope。
- 删除项、动态引用、生成代码和外部 consumer 无法静态确认时，建立 gap 而不是断言“不再使用”。

## Strength 与 Verification Gap

Strength 是有证据的正向判断，不是礼貌性表扬。它说明具体检查、保持的 invariant 与 evidence，可为空；不得要求固定数量。

Verification gap 表示当前无法可靠判断的要求或风险，至少记录：

- 对应 requirement/risk；
- 缺少的证据或专业能力；
- owner（Planner、Executor、用户、专业 reviewer 或外部系统）；
- blocking level 与关闭条件；
- 当前结论允许声称到什么程度。

关键 requirement、权限/隐私、迁移/数据完整性或不可逆行为存在 blocking gap 时不能 passed。非关键外部 hosted CI 未运行可作为
非阻断 gap，但交付必须披露。

## Clean Review

没有开放 finding 不等于“没看出问题”。clean review 至少说明：

1. target/context identity 与实际覆盖范围；
2. 逐 requirement 或 lens 的关键证据；
3. 命中的 risk playbook 与检查结果，未命中的理由；
4. evidence-bound strengths；
5. verification gaps、limitations 和 residual risk；
6. Reviewer 没有运行的测试、目标程序、网络或专业审计。

禁止只写 `LGTM`、`looks good`、`符合规范` 或“测试通过所以正确”。

## 反馈处置

Planner/Executor 收到 finding 后先核对事实和适用性：

- `resolved`：目标已修改且新 target 证明确实关闭；复审仍需完整检查。
- `invalidated`：新证据证明原 claim 不成立，记录理由和证据，不因作者不同意就使用。
- `still-open`：当前 target 仍存在同一问题，保留严重度或用新证据重新校准。
- `superseded`：问题被更准确的新 finding 替代，连接新 ID 和理由。

不能把 blocking/major 标为 accepted/deferred 后获取 passed，也不能在新 attempt 中省略前序 finding。任何修复都会改变目标，必须
重建 target/context 并执行完整复审。

## 效果证据分层

Reviewer 的效果声明必须分三层报告，不能互相替代：

| Layer | Proves | Does not prove |
| --- | --- | --- |
| deterministic contract | receipt、freshness、lineage、计数和 closed schema 门禁可重复工作 | finding 语义正确或实际独立会话行为 |
| same-context semantic | 当前 reviewer 在固定 corpus 上的 finding、误报、severity、locator、evidence 和 gap 表现 | 独立性、跨会话稳定性或总体触发率 |
| user delegated-review observation | 用户按固定 packet 在独立会话中观察到恰好一个子 Agent、隔离 prompt、结果与关闭证据 | 未覆盖场景、其它模型或未来版本的总体质量 |

语义 oracle 只对人工裁定后的 expectation ID 做确定性评分，不用关键词代替语义匹配。clean 与 near-miss 是误报控制，不能为了
提高 recall 删除；known-defect 是漏报控制。真实 delegated-review 没有用户导入宿主活动、dispatch 和 receipt 证据时必须保持
`not_observed`，same-context receipt 必须声明 `independence_claim=false`。corpus 必须覆盖 framing bias、目标内 prompt
injection 和父子结论污染，避免实现者或 coordinator 的结论替代源码证据。

# Dependency Selection Gate

本文件定义依赖与技术选型的正式决策门。它适用于直接依赖、框架、ORM、SDK、驱动、构建插件、代码生成器、CI Action、容器基础镜像和 vendored dependency。Planner 负责在线收集并解释可变事实；确定性 checker 只验证结构和一致性；Executor 只执行批准结论并复核漂移。

## 原则

1. 先证明依赖有必要，再比较候选。
2. 项目适配和明确政策优先于抽象热度。
3. 硬门槛与比较信号分离，热度不能抵消安全、许可或兼容性失败。
4. 所有可变事实带来源、观察日期、窗口和局限。
5. 不计算跨生态统一总分，也不维护永久推荐榜。

## 触发与模式

出现以下任一情况即触发：

- stage 会修改 manifest、lock、vendor、base image、CI Action 或依赖配置。
- 计划包含 framework/library/package 的选择、升级、替换或迁移。
- 用户要求技术栈、库或工具选型。
- 现有关键 runtime 依赖进入架构、安全或支持性评审。

选择一个 mode：

| Mode | 含义 | 决策要求 |
| --- | --- | --- |
| `none` | 无新增、升级、替换或关键 retain | `decisions` 为空，说明未触发依据 |
| `retain` | 明确评审并保留现有关键依赖 | 每项 action 为 `retain` |
| `change` | 至少一项 `add`、`upgrade` 或 `replace` | 完整候选和证据 receipt |
| `mixed` | 同时包含 retain 与 change | 每项按 action 执行对应证据要求 |

删除依赖由普通 stage 和残留验证覆盖，不作为 selection action。纯文档或内部代码改动不能因为引用依赖文档而误触发。

## Necessity Gate

对每个决策依次回答：

1. 需求是否已经由现有项目能力满足。
2. 标准库、平台能力或官方 SDK 是否能以可维护方式满足。
3. 新依赖带来的安全面、升级成本、运维成本和传递依赖是否值得。
4. 对 upgrade/replace，当前依赖是否真的不受支持、不兼容或无法满足验收。

结果只能是：

- `dependency-required`：批准需求需要该类依赖。
- `existing-sufficient`：保留现有能力，不新增或替换。
- `standard-or-official-sufficient`：使用标准库、平台或官方 SDK。
- `blocked`：缺少政策、证据或不可替代输入。

`dependency-required` 必须引用 REQ；其余结果必须说明排除额外依赖的依据。不能为了“主流”迁移一个健康且适配的既有栈，也不能为了零依赖手写复杂安全协议。

## 候选优先级

按以下顺序建立候选与决策基线：

1. 用户或组织 allowlist、banlist、许可、安全和支持政策。
2. 当前项目已采用、健康且满足需求的技术栈。
3. 语言标准库、平台能力或官方 SDK。
4. 同生态、同类别中成熟、广泛采用、维护健康的主流方案。
5. 主流基线无法满足明确需求时的 specialized exception。

按决策影响选择证据档位：

- **快速确认**：健康的现有依赖、标准库、平台能力或官方 SDK 已满足需求时，可以只保留一个正式候选，但必须记录其它方案不合理的排除依据，并确认版本、支持线、安全、许可和项目适配。
- **主流比较**：新增或替换通用 framework、ORM、SDK、driver、CI Action 等依赖时，比较 2-3 个同生态、同类别的主流候选；已有/标准方案可作为其中一个基线。
- **专业例外**：主流基线无法满足明确 REQ 时，保留主流候选并执行完整 specialized exception、风险接受、缓解和回滚。

不同抽象层、不同 package major、fork、rename 或 monorepo package 不得混为同一采用口径。不得为了凑候选数纳入明显不适用的方案。

## 硬门槛

| Gate | 通过条件 | 默认失败行为 |
| --- | --- | --- |
| `authenticity` | canonical package、源码仓库、publisher/fork 关系可确认 | 淘汰候选 |
| `compatibility` | 语言、runtime、OS/arch、框架和项目约束兼容 | 淘汰候选 |
| `stable_support` | 存在项目可用的 supported stable line | 淘汰或显式例外 |
| `lifecycle` | 未 archived/deprecated，且有维护、LTS 或 quiet-utility 解释 | 动态依赖淘汰 |
| `security` | 目标版本无未缓解的适用 high/critical advisory | 淘汰或阻塞 |
| `license` | 许可已识别并满足项目/组织政策 | 淘汰或交政策 owner |
| `reproducibility` | 版本可 pin/lock，release/source identity 可追踪 | 淘汰候选 |

结果使用 `pass`、`fail`、`exception` 或 `unavailable`。critical-runtime/runtime 的 `unavailable` 是 blocker；dev-build 是否允许例外由组织政策决定，但不得写成 pass。稳定性与生命周期例外仍必须通过真实性、兼容性、安全、许可和可重现性。

## 可信度信号

每个正式候选记录九项信号：

- `stable_version`
- `adoption_scale`
- `update_recency`
- `maintenance_activity`
- `adoption_trend`
- `api_and_project_fit`
- `ecosystem_and_docs`
- `transitive_and_provenance`
- `operational_cost`

每项包含 `result`、`value`、`source_type`、`url`、`as_of`、`window` 和 `caveat`。结果为 `pass`、`concern`、`fail` 或 `insufficient-data`。selected candidate 的 concern 必须进入风险和缓解；`fail` 不得被 stars、downloads、dependents 或 aggregate score 抵消。

五项核心信号的最低解释：

| Signal | 最低证据 | 解释边界 |
| --- | --- | --- |
| stable version | registry + official release/support | 选择兼容的受支持稳定线，不追逐最大版本号 |
| adoption scale | registry dependents/downloads 或公开 dependency graph | 仅在同生态、同类别、同 identity 比较，并披露私有采用缺失 |
| update recency | official releases + repository activity | 动态框架与成熟 quiet utility 使用不同阈值 |
| maintenance activity | release、响应、closure、维护者/贡献者持续性 | commit 数和机器人活动不能单独证明健康 |
| adoption trend | 6/12/24 月历史序列，或至少两个代理 | 记录 major split、迁移事件、窗口和置信度 |

趋势缺少完整历史序列时可以使用 `insufficient-data`，但必须写明局限，并提供至少两个独立代理，例如跨期 download、dependents、release adoption、公开 production references 或生态调查。两个同源镜像不算两个代理。

## 来源层级与证据底线

优先顺序：

1. 项目/组织政策、manifest、lock、ADR 和支持约束。
2. 官方语言、框架、供应商、源码仓库、release/support/security policy。
3. 生态 registry、OSV、deps.dev、OpenSSF、NIST、CHAOSS 等一手基础设施或规范。
4. 公开 dependency graph、可解释的采用和趋势 receipt。
5. 社区调查与高质量二手资料，仅补充背景，不单独支撑关键结论。

通用起点只提供调查方向，不替代对应生态的官方资料：

| 目的 | 优先起点 | 使用限制 |
| --- | --- | --- |
| OSS necessity、真实性、维护和适配 | [OpenSSF Concise Guide](https://best.openssf.org/Concise-Guide-for-Evaluating-Open-Source-Software.html) | 指南是 baseline，不是自动评分器 |
| version、deprecated、license、graph 和 provenance | [deps.dev API](https://docs.deps.dev/api/v3/) | direct advisory 与链接元数据需补充核验 |
| version-specific vulnerability | [OSV](https://osv.dev/) | 无记录不等于无漏洞，需判断适用性 |
| 项目健康、采用与趋势指标 | [CHAOSS metrics](https://chaoss.community/kb-metrics-and-metrics-models/) | 指标必须带窗口、项目类型和 bot caveat |
| 安全开发生命周期 | [NIST SSDF](https://csrc.nist.gov/pubs/sp/800/218/final) | 高层治理，不提供 popularity threshold |
| 语言风格与项目结构 | 官方语言/框架文档与 [Google Style Guides](https://google.github.io/styleguide/) | 先服从项目内明确规范 |

主流比较、专业例外以及高风险 `retain` 停止研究前至少具备：

- 官方 package/source/documentation/release/support identity。
- registry version、published/deprecated、license 和 adoption evidence。
- 近 12 个月维护历史及至少一项 response/resilience evidence。
- version-specific advisory evidence；高风险包含 transitive path。
- adoption trend 结果与窗口；缺数据时包含两个代理和 caveat。
- 与现有方案、标准库/官方 SDK 和领先候选的同类适配比较。
- selected version policy、manifest/lock scope、验证、风险和回滚。

快速确认仍须满足全部适用硬门槛与五项核心可信度信号，但可以复用项目 lock、官方 release/support/security 信息和一个 canonical 候选，不要求额外收集不改变决策的社区比较材料。

URL 只是 locator，不等于 evidence。receipt 必须同时包含观察结果、来源类型、`as_of`、窗口和适用局限。私有证据只保存安全 locator 与摘要，不落盘 token、credential 或敏感 query。

## 新鲜度

| Criticality | 示例 | approval 最大年龄 |
| --- | --- | --- |
| `critical-runtime` | auth、crypto、序列化边界、数据库 driver、核心数据持久化 | 30 天 |
| `runtime` | Web framework、ORM、SDK、client、queue、runtime observability | 60 天 |
| `dev-build` | test、lint、codegen、build plugin、CI Action | 90 天 |

`as_of` 是观察日期，不是网页发布日期。maintenance 至少观察近 12 个月；trend 的 6/12/24 月是信号窗口，不是 receipt 年龄。archived/deprecated、ownership/source、license、support line 或适用 advisory 变化会立即使 receipt 失效。

批准时已过期的关键证据必须刷新。在线访问失败时，仍在有效窗口内的 receipt 可继续使用并记录失败；过期 receipt 必须标记 `blocked-by-access`，不能默认放行。

## Specialized Exception

只有主流基线无法满足可引用的 must requirement 时，才允许 `selection_class=specialized-exception`。记录：

- mainstream baseline candidate key。
- 未满足的 REQ ID 与可验证失败依据。
- 选中特化候选的必要能力。
- 接受的风险、缓解、隔离边界和回滚路径。
- 是否需要用户/组织 owner 明确接受。

主流基线必须保留在同一候选矩阵。特化候选仍必须通过真实性、兼容性、安全、许可和可重现性；稳定性或生命周期例外需要替代支持或明确退出策略。

## 产物与契约

主计划保存 mode、necessity、`DEP-*` 摘要、决策理由、风险和关键来源。`plan-contract.json` 保存执行所需的 canonical package identity、action、criticality、selection class、version policy、manifest paths、freshness、artifact 和 validation 引用。

mode 非 none 时创建 `artifacts/dependencies/dependency-selection.json`，保存完整候选、硬门槛和九项信号 receipt。Markdown 模板可用于规划审阅，但不得成为与 JSON 竞争的第二份机器真相源。

一致性要求：

- plan、contract 和 artifact 的 mode 与 `DEP-*` 集合一致。
- contract 的 selected package/version 与 artifact 的 selected candidate 一致。
- artifact ID、validation ID、REQ ID 和 manifest path 引用存在。
- `none` 必须为零 decision、零 dependency artifact，并与 stage scope 不冲突。
- specialized exception 的 baseline、REQ、风险和接受要求完整。

## 工具与判断边界

Planner 可使用官方文档、registry、源码、release、OSV、deps.dev、OpenSSF/CHAOSS 指标和生态原生工具收集证据。不同生态优先各自官方工具，例如 Go 的 pkg.go.dev、module/version 与 `govulncheck` 文档；不要把某一生态阈值复制到全部语言。

确定性 checker 不联网、不安装包、不执行 URL、不解析不可信 release archive，也不判断真实世界热度。它只验证 closed schema、日期、窗口、枚举、引用、证据完整性和三方一致性。

Executor 不重新做候选排名。它核对批准 package identity、version policy、manifest paths 和 receipt freshness；结论不变时记录执行证据，package/version policy/hard gate/risk acceptance 变化时写 Research Drift 并进入 Amendment。

## 示例边界

对新建工程化 Go REST，可把观察日证据充分的 Gin 放入主流基线候选；常规 CRUD 数据层可把 GORM 放入候选。已有健康 Echo 项目默认先评估 retain，简单 webhook/health endpoint 应先比较 `net/http`，SQL-first 或类型生成需求应比较 `database/sql`、sqlc 等模型。

这些只是决策行为示例，不是永久默认。每次规划都必须在线刷新 stable version、采用规模、更新时间、维护活跃度、安全和趋势，并根据项目需求重新得出结论。

## Research Saturation

达到当前证据档位底线后，以一个有界批次验证剩余高影响未知；该批次的新一手证据不再改变 hard-gate 结果、候选排序、风险、版本策略或验证设计时立即结束搜索。真实性不明、关键来源不可访问、政策缺失或证据互相矛盾时，结果是 blocked，不是低置信度自动选择。

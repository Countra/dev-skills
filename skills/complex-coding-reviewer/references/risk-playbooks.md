# Risk Playbooks

## 目录

1. [使用规则](#使用规则)
2. [Risk Screen](#risk-screen)
3. [安全与隐私](#安全与隐私)
4. [并发与完整性](#并发与完整性)
5. [性能与资源](#性能与资源)
6. [API、数据与兼容](#api数据与兼容)
7. [UI、可访问性与国际化](#ui可访问性与国际化)
8. [删除与依赖](#删除与依赖)
9. [专业能力边界](#专业能力边界)

## 使用规则

先做 Risk Screen，再只加载命中的 playbook。一个目标可命中多个领域，但不得默认全量运行所有清单。

每个命中项记录：trigger、要保持的 invariant、读取的 target/context、named-risk expansion、证据、结果和 gap。未命中时说明
触发面不存在；不能只写 `N/A`。通用 playbook 服从目标项目 threat model、批准需求、语言/框架官方规范和版本化标准。

## Risk Screen

| ID | Trigger examples | Default action |
| --- | --- | --- |
| `RISK-SECURITY-PRIVACY` | 认证授权、秘密、用户输入、文件/网络边界、敏感数据、日志、加密 | 加载安全与隐私；必要时要求专业 reviewer |
| `RISK-CONCURRENCY-INTEGRITY` | 线程/协程、共享状态、事务、队列、缓存一致性、重试、幂等 | 加载并发与完整性，固定状态 invariant |
| `RISK-PERFORMANCE-RESOURCES` | 循环 I/O、批量数据、连接/句柄、缓存、递归、无界集合、热路径 | 加载性能与资源，要求规模与上界证据 |
| `RISK-API-DATA-COMPATIBILITY` | 公共 API、schema、序列化、迁移、配置、协议、跨版本 consumer | 加载 API/数据/兼容，检查 rollout/rollback |
| `RISK-UI-ACCESSIBILITY-I18N` | 用户界面、键盘/焦点、屏幕阅读、颜色、locale、时区、文本布局 | 加载 UI/可访问性/国际化；能力不足建立 gap |
| `RISK-REMOVAL-DEPENDENCIES` | 删除、弃用、重命名、依赖升级/替换、生成物、动态加载 | 加载删除与依赖，检查 consumer、迁移和回滚 |

## 安全与隐私

### Trigger

认证/授权、权限边界、用户可控输入、路径/命令/模板/查询、上传下载、网络请求、secret、PII、日志、加密或供应链变化。

### Invariants

- 身份与授权在可信边界验证，不能只依赖客户端或调用方声明。
- 输入在最终解释器上下文按正确语义处理；路径、命令、查询和模板不混用转义规则。
- secret/PII 不进入日志、错误、review package、缓存或不必要持久化。
- 默认拒绝、最小权限、失败安全；错误路径不能绕过检查或泄露敏感细节。
- 加密、随机数、token 和签名使用目标生态官方/成熟方案，不自造协议。

### Evidence

读取入口、权限决策点、数据流、错误/日志、配置默认值、相关测试和项目 threat model。Web 应用可按具体版本引用 OWASP ASVS；
不要把完整 ASVS 当作所有代码目标的默认清单。

### Common false positives

仅因出现 `eval`、SQL 字符串、文件路径或 token 字样就报告漏洞；忽略框架参数化、可信常量、上游验证或不可达路径。必须证明
攻击者可控性、传播路径和实际 sink。

## 并发与完整性

### Trigger

共享可变状态、锁、线程/协程、事务、队列、重复投递、重试、缓存/数据库双写、临时文件、原子替换或跨进程 ownership。

### Invariants

- 锁顺序、生命周期和取消路径一致，不在持锁时执行无界外部 I/O。
- read-check-write 不产生 TOCTOU；共享状态更新具有所需原子性和可见性。
- 重试与重复消息保持幂等，失败不会造成部分提交或双重副作用。
- 事务边界覆盖业务 invariant；缓存失效与持久化顺序有明确真相源。
- cleanup 在成功、失败、取消和进程终止路径都可证明 owner-empty。

### Evidence

扩展到共享状态定义、所有读写方、锁/事务 helper、重试策略和并发测试。只在能命名同一状态或锁的 consumer 时越出 target。

### Common false positives

看到并发原语就报告竞态，或因单线程测试通过就宣称线程安全。需要具体交错、共享对象和破坏的 invariant。

## 性能与资源

### Trigger

热路径、循环数据库/网络/文件 I/O、批处理、递归、无界输入/集合/缓存、连接池、句柄、内存副本、压缩/解析或高频日志。

### Invariants

- 时间、内存、文件数、并发数、重试和输出具有与输入规模相称的明确上界。
- 避免 N+1、重复全量扫描、无界队列/缓存和指数级路径。
- 连接、文件、进程、锁和临时目录在所有路径释放。
- 优化不牺牲正确性、可读性或错误处理；没有数据时不报告微优化。

### Evidence

使用输入规模、调用频率、复杂度、已有 benchmark/profile 和资源生命周期。Reviewer 不运行 benchmark；缺少关键规模证据时建立 gap。

### Common false positives

凭循环或列表推导猜测性能问题、使用任意毫秒阈值、把低频管理路径按热路径评级。必须说明规模、频率和用户影响。

## API、数据与兼容

### Trigger

公共函数/CLI/HTTP API、事件、序列化、schema、数据库迁移、配置键、默认值、错误码、协议、文件格式或跨版本 consumer 变化。

### Invariants

- 输入输出、错误、排序、空值、时间/时区、编码和幂等语义与批准 contract 一致。
- producer/consumer 同步，新增字段和枚举有未知值策略；删除/重命名有迁移窗口。
- 数据迁移可重入、可观测、失败可恢复；rollout/rollback 顺序不会让新旧版本互相破坏。
- 配置默认值安全且升级路径明确；文档、示例和 schema 同步。

### Evidence

读取调用方、consumer、schema、migration、fixtures、兼容测试和发布说明。外部 consumer 不可见时记录 gap，不推断“无人使用”。

### Common false positives

把所有内部重构都视为 breaking change，或仅因新增可选字段就断言兼容。需要证明边界公开性、consumer 行为和版本策略。

## UI、可访问性与国际化

### Trigger

可见 UI、交互控件、键盘/焦点、动态状态、颜色/图标、表单、错误提示、locale、时区、复数、RTL 或可变长度文本。

### Invariants

- 交互可通过适用的键盘/辅助技术完成，焦点顺序和可见状态稳定。
- 控件语义、label、错误关联和动态通知可被辅助技术理解。
- 颜色不是唯一信息通道，对比度和状态不依赖视觉装饰。
- 文本可扩展、不重叠、不截断关键操作；locale、时区、数字和复数使用项目既有机制。
- loading、empty、error、disabled 和 reduced-motion 等状态与目标产品契约一致。

### Evidence

读取组件、样式、设计规范、现有可访问性测试和 locale 资源。静态代码不足以证明视觉/辅助技术效果时，明确要求对应验证 evidence。

### Common false positives

在无 UI 的后端目标上强制本 playbook，或仅凭组件名断言可访问性通过。需要具体交互面和可观察状态。

## 删除与依赖

### Trigger

删除/弃用文件、函数、字段、命令、配置、迁移、资源或 feature flag；新增、升级、替换依赖；动态 import、反射、插件或生成代码。

### Invariants

- 静态、动态、配置、文档、脚本、CI、外部 consumer 和生成流程中的引用已分类。
- safe-now 删除有当前证据；不能确认的删除标为 defer-with-plan，包含 owner、前置指标和时间点。
- 依赖 identity、版本策略、许可、安全、支持线、锁文件和传递影响符合批准决策。
- 升级/替换有行为回归、迁移、回滚和缓存/构建产物清理策略。
- feature flag/旧路径删除以实际观测和 rollout 状态为依据，不只看本仓库搜索结果。

### Evidence

读取 manifest/lock、加载入口、生成脚本、配置、搜索结果、发布说明和批准 dependency receipt。Reviewer 不联网刷新依赖事实；
证据过期时交回 Planner/Executor Research Drift。

### Common false positives

`rg` 无结果就断言可安全删除；忽略字符串引用、外部 consumer、模板、反射和生成代码。反之，也不要因理论外部使用无限期阻止有
正式弃用与迁移证据的删除。

## 专业能力边界

以下情况通常需要 verification gap 或合格专业 reviewer：加密协议、复杂认证/权限模型、高价值支付、法规隐私、无锁并发、
不可逆数据迁移、关键性能容量、辅助技术实测或未知平台 ABI。

gap 必须说明具体领域、缺失能力/证据、owner、阻断级别和关闭条件。请求专业 reviewer 不代表当前所有审查都无效；应保留已完成
的通用 coverage，同时限制 verdict 和能力声明到证据支持的范围。

# Skill Evaluation Evidence Report

## Target

- Evaluation：`complex-coding-executor-20260714`
- Path：`skills/complex-coding-executor`
- Tree SHA-256：`18a72fb877806b6792d8febcc971a5d190527d6d009327355d935248ae62ed25`

## Evidence Coverage

- Static：`complete` {'pass': 4, 'warn': 3, 'fail': 0, 'not_applicable': 1}
- Semantic：`complete` {'pass': 4, 'warn': 3, 'fail': 0, 'not_applicable': 0}
- Observed：`not_requested` (0/0)

## 已证明

- `skill.structure` [warn] 非标准顶层资源：templates
- `skill.capabilities` [warn] 发现需要人工确认的静态能力信号：environment_read=2, file_write=9, process=2
- `skill.validation_assets` [warn] 缺少可发现的验证资产：ci

## 审查判断

- `workflow_completeness` [warn] 单会话下从批准到完成、恢复和 amendment 的闭环完整，但“唯一 writer”目前只是流程约束，没有任务级锁、租约或 compare-and-append 机制。
- `safety_and_permissions` [warn] 路径 containment、不可变文件哈希、提交证据和三类授权门禁较强，但 attestation 是完整性封印，不是经过身份认证的用户批准证明。
- `verification_and_delivery` [warn] 单元测试覆盖 reducer、attestation、恢复、drift、amendment 和提交门禁，仓库也有确定性联合 eval，但 executor 没有独立 CI，且关键并发与中断窗口未纳入回归。

## 用户观察

- 尚未导入用户独立会话观察。

## 假设与限制

- 假设：本次评估目标是 complex-coding-executor 当前源码设计、静态契约和测试设计，不评估某次具体执行任务的实现质量。
- 假设：planner 与 executor 作为同仓、绑定演进的一对 Skill，共享 planner 的 task-contract 定义。
- 假设：当前默认信任模型是用户与 Agent 协作而非抵抗拥有 workspace 写权限的恶意进程。
- 限制：未提供旧版 baseline，因此没有版本间提升或退化结论。
- 限制：按 skill-evaluation-lab 契约未执行 executor 脚本、单元测试或 eval，仅静态阅读其实现、测试与评测设计。
- 限制：未进行用户独立会话观察，因此不能声明真实触发准确率、长任务完成率、恢复成功率或执行质量。
- 限制：planner approval checker 的语义强度会直接影响 executor preflight，本报告把该问题视为已在 planner 评估中记录的跨 Skill 继承风险。
- 限制：process-manager 规则被直接消费，双方契约仍需依赖联合回归防止演进漂移。

## 声明边界

- 静态检查只证明 source-bound 机械事实和能力信号，不证明真实运行行为。
- 七维语义审查是当前 Agent 的设计判断，必须保留 assumptions 与 limitations。
- 缺少完整、结论明确的用户观察，不得声明真实触发率或行为提升。

## 当前 Agent 后续动作

读取完整证据后，由当前 Agent 给出结论、置信边界、问题优先级和优化建议。
报告脚本不会生成最终判断。

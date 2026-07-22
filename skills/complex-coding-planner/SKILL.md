---
name: complex-coding-planner
description: 为复杂、长周期、高风险、多阶段或恢复敏感的编码任务制定可执行方案。用于用户要求深入调研、技术选型、架构设计、任务拆分、落盘计划或准备后续实施时；保留风险、验证、审查、批准和恢复边界，但以自然语言计划与 compact task contract 工作，不为普通局部任务制造 Harness 制品。
---

# Complex Coding Planner

规划用于减少实现不确定性，不用于生产审计格式。优先依赖项目事实和工程判断，只把恢复与执行真正需要的内容结构化。

## 任务路由

- `direct`：目标明确、影响局部、当前会话可完成。只在对话中给出必要计划，不创建 `.harness` 文件。
- `managed`：跨会话、多阶段、恢复敏感、高风险、涉及关键选型，或用户明确要求落盘。创建 compact task bundle。
- `blocked`：仍缺少会改变范围、风险或授权的关键事实。先自主调查，只把无法消除的决策交给用户。

不要按文件数、工具调用数或预计耗时机械升级任务。

## 核心流程

1. 阅读仓库规则、相关实现、调用方、测试、配置和 Git 状态。
2. 明确目标、完成标准、范围、非目标、约束和仍会改变方案的未知项。
3. 本地事实足够时停止调研。变化事实、关键依赖、平台差异、安全或高风险未知才查询官方和一手资料。
4. 比较真正可行的方案，记录选择、主要理由、风险和回滚；不要为了格式制造候选。
5. 按自然实施边界拆分阶段，为每个阶段指定范围、依赖、验证和审查模式。
6. 自检需求覆盖、可实施性、验证真实性、风险和授权。Managed 计划使用 `complex-coding-reviewer` 做 `plan-review`；高风险或用户要求时使用独立 Reviewer。
7. 修复 blocking/major finding，运行 plan checker，激活任务指针，向用户给出聚焦方案并等待批准。

用户批准前不得实现代码。实施批准不等于提交、外部写入或提权授权。

## Managed Task Bundle

只维护：

- `execution-plan.md`：人类可读的批准意图。
- `plan-contract.json`：阶段 DAG、范围、验证、审查模式和请求权限。
- `.harness/active-task.json`：当前任务指针，由 `harness_active_task.py` 原子维护。
- `run-state.json`：用户批准后由 Executor 创建；Planner 不写。

不创建 research、standards、dependency receipt、traceability、review receipt 或 artifact index。调研结论、来源与关键依赖选择直接写入计划。

运行：

```text
python skills/complex-coding-planner/scripts/harness_plan_check.py --task-dir <task-dir> --mode approval
python skills/complex-coding-planner/scripts/harness_active_task.py --workspace <workspace> activate --task-dir <task-dir>
```

checker 只检查机器边界，不评价文风或代替语义审查。

## 计划内容

计划自然覆盖以下信息，不要求固定章节、矩阵或段落数量：

- 目标与完成标准
- 范围、非目标和约束
- 影响实现的事实、调研结论和技术决策
- 实施阶段及依赖
- 验证与审查策略
- 风险、回滚、待确认项和授权边界

只为阶段和必要验证保留 `STG-*`、`VAL-*`，便于恢复和 Executor 精确引用。不要复制 contract 的全部字段到正文。

## 工程判断

- 优先项目现有规范、实现模式和健康依赖。
- 新增或替换关键依赖时，检查稳定版本、采用规模、维护活跃度、更新时间、采用趋势和项目适配；只保留最终选择、主要理由与来源。
- 设计模式、SOLID、低耦合高内聚是决策工具，不是逐项填写的清单。
- 调研与依赖规则见 [research-and-dependencies.md](references/research-and-dependencies.md)。
- task bundle 与恢复边界见 [task-state.md](references/task-state.md)。

## 用户输出

先说明目标和关键决策，再给实施步骤、验证和主要风险。不要向用户展示 contract JSON、hash、provenance、空矩阵、完整 gate 状态或机械化“零 issue”结论。

用户批准后停止规划，并交给 `complex-coding-executor`。

---
name: complex-coding-reviewer
description: 对复杂编码任务执行证据驱动、目标绑定且可复审的正式工程审查，仅提供 plan-review（规划方案审查）与 code-review（代码和变更审查）两个 profile。用于审查 managed task bundle、实施阶段 delta、最终集成变更或 standalone 本地代码目标，并生成 canonical JSON receipt；不得用于编写计划、修复代码、自动运行 Agent、操作远端平台或代替测试。
---

# Complex Coding Reviewer

只审查显式目标并写审查产物。不得修改计划、代码、ledger、Git 或远端对象。

## Profile 路由

- 用户要求审查规划方案、task bundle、实施阶段设计或批准就绪度：使用 `plan-review`。
- 用户要求审查代码、diff、commit range、stage 实现或最终集成：使用 `code-review`。
- 同时包含规划和代码时，拆成两个独立 attempt；未知目标时先澄清，不创建第三个通用 profile。

分别读取：

- `plan-review`：读取 [plan-review.md](references/plan-review.md)。
- `code-review`：读取 [code-review.md](references/code-review.md)。
- 任一正式审查：读取 [review-workflow.md](references/review-workflow.md)；构造或解释 JSON 时再读
  [review-contract.md](references/review-contract.md)。

## 核心工作流

1. 明确 profile、scope、目标根目录、允许写入的 review artifact 目录和实际 reviewer provenance。
2. 用 `scripts/review_target.py` 生成 target。managed plan 使用 `plan`；代码使用 `working-tree`、
   `commit-range` 或 `files`。不得把 review receipt 纳入其自身 target。
3. 在审查前保存 target JSON；只读目标、关联契约、声明的规范和验证证据，逐个完成 profile 必需 lenses。
4. 从 `templates/review-report.json` 建立新 attempt，替换所有模板值；finding 必须证据定位、可证伪并说明影响和建议。
5. 用 `scripts/review_validate.py` 校验 receipt 与当前 target freshness。失败时修复报告；目标变化时保留旧 attempt，
   创建新 target 和新 receipt，并用 `supersedes_review_id` 串联。
6. 需要人类视图时，用 `scripts/review_render.py` 从已验证 JSON 生成 Markdown；JSON 始终是 canonical 产物。
7. 先报告 findings，再给 verdict、限制和未覆盖面。`passed` 不是测试成功的替代品。

## 不可越过的边界

- 目标只读；唯一允许写入的是用户或调用方明确的 review artifact 目录。
- 不运行 `codex exec`、模型 API、子代理、目标程序、测试、网络请求、Git write、远端写入或后台服务。
- 可以读取现有测试/验证 evidence，但不得把未执行的检查表述为已验证。
- same-context 审查必须设置 `independence_claim=false`；不可伪装成 fresh 或外部审查。
- blocking/major finding 只有 `resolved` 或 `invalidated` 后才不阻断；不能用 `accepted`/`deferred` 获得通过。
- 任何目标变化都会使旧 receipt stale；不得编辑旧 receipt 冒充同一目标上的新结论。

## 确定性入口

- `review_target.py`：只读生成 target manifest 与 SHA-256。
- `review_validate.py`：校验 closed receipt、profile 门禁、派生计数、provenance、supersedes 和 freshness。
- `review_render.py`：把已验证 receipt 渲染为 findings-first Markdown。

三个入口只使用 Python 标准库并输出稳定 JSON envelope。脚本只检查结构与可重建事实，语义 finding 和最终判断必须由
实际 reviewer 基于源码证据完成。

# 审查工作流

## 1. 固定调用边界

先记录：profile、scope、target root、review root、调用方期望和 reviewer provenance。再建立 review brief，至少包含：

- 需求、AC、非目标和批准边界；
- baseline、allowed paths、目标 identity 和 attempt；
- 项目/语言/框架规范及其适用性；
- 已有验证证据、命令 identity、claim source 和未运行项；
- 调用方声明的风险、已知限制和需要专业 reviewer 的领域。

brief 是调用合同，不是完成证明。实现者总结、计划理由、测试自报和风险接受都必须重新核对。Reviewer 不负责获取远端
PR/MR、修复目标、执行验证或写 ledger；这些动作由调用方或其它 skill 完成。

`plan-review` 只接受 `plan-bundle`。`code-review` 接受：

- `stage-delta`：stage baseline 到当前工作树，必须携带 stage ID 与 attempt。
- `final-integration`：execution baseline 到当前整体工作树。
- `standalone`：显式文件、工作树或 commit range。

目标或 scope 混合时拆分 attempt。没有 baseline 时不得用“当前看起来像 diff”代替可重建 target。

## 2. 固定目标与上下文

典型命令：

```powershell
python -u -X utf8 -B scripts/review_target.py plan `
  --task-dir <task-dir> `
  --review-root <task-dir>/artifacts/reviews `
  --output <task-dir>/artifacts/reviews/targets/plan-attempt-1.json
```

```powershell
python -u -X utf8 -B scripts/review_target.py working-tree `
  --repository <repo> --baseline <baseline-sha> `
  --stage-id STG-01 --attempt 1 `
  --exclude .harness/** `
  --review-root <task-dir>/artifacts/reviews `
  --output <task-dir>/artifacts/reviews/targets/STG-01-attempt-1.json
```

`--output` 存在时必须显式传 `--review-root`，且已有 attempt 不可覆盖。plan target 固定排除 `kind=review` 的
artifact，避免 receipt 自引用。

primary target 表示被审对象；review context 表示要求、规范、验证证据和 named-risk 扩展。二者必须分别可重建，不能把
上下文内容混入 target 后失去来源，也不能让 target 不变时任意替换规范或旧验证日志。context 尚无法机器绑定时，必须在
limitations 明确披露，不能声称完整 freshness。

## 3. 执行语义审查

1. 先读 target manifest，确认路径、删除项、baseline/head、scope 和 package 预算正确。
2. 先做需求/批准意图符合性，再审核心设计，最后按逻辑顺序覆盖 target 全部内容。
3. target 外读取只允许 named-risk expansion：记录风险、路径、原因、检查结果和证据。
4. 执行 risk screen，命中后只加载对应 playbook；不适用必须说明触发面为什么不存在。
5. 按 profile 固定 lens 顺序记录状态。`reviewed`/`blocked` 必须有 evidence；`not-applicable` 必须有理由。
6. finding 只记录可证伪且影响行为、维护、交付或规划可执行性的具体问题；个人偏好只能是 advisory。
7. 对无法验证项记录所需证据、责任方和阻断级别；能力不足时要求合格 reviewer，不进行无边界推测。
8. positive check 也必须引用证据；clean review 说明覆盖范围、strength、gap 和 residual risk。

## 4. 使用有界 Review Package

大目标可生成一次性 review package，包含 plan/file manifest，或 commit list、stat 和带适量上下文的 diff。package 只减少
重复 Git/文件读取，不是 canonical truth source。

- 固定 workspace root、baseline/head、允许路径、文件数、单文件和总字节预算。
- 排除 review artifacts、秘密模式、二进制和越界路径；删除项仍需保留身份。
- package 的 digest 与 primary/context target 分开；validator 必须重建 target/context。
- package 缺文件或被截断时记录 gap，不能把“未出现在 package”解释为“不存在”。

## 5. 写 receipt 并校验

复制模板到新的 attempt 路径并替换全部模板值。JSON 根对象、scope、target、reviewer、lens、finding、evidence 和计数
均为 closed contract；不得增加临时字段。

```powershell
python -u -X utf8 -B scripts/review_validate.py `
  --receipt <receipt.json> --review-root <review-artifact-dir> --workspace <repo> `
  --expected-profile code-review --expected-scope stage-delta `
  --expected-stage-id STG-01 --expected-attempt 1
```

plan receipt 额外传 `--task-dir`。新 attempt 声明 `supersedes_review_id` 时，用 `--supersedes <old.json>` 提供直属
前序。Validator 通过只证明契约和 freshness 通过，不证明 finding 的语义一定正确。

## 6. 修复、反馈核对与复审

`changes_required`：把 receipt 交还 Planner 或 Executor；Reviewer 不自行修复。目标修复后旧 digest 立即 stale，创建
完整新 attempt，不从旧报告继承通过。`blocked`：补齐用户决策、权限、证据或专业 reviewer 后再创建新 attempt。

Planner/Executor 收到 finding 后先核对 claim、代码事实和适用规范，再决定 resolved、invalidated 或请求 amendment；不能因
措辞权威就盲改，也不能因 finding 与批准计划冲突就自动降级。复审必须执行完整复审，重新读取当前
target/context/package，逐项交代直属前序 finding，不只查看修复片段。

## 7. 交付

先列开放 findings，再说明 verdict、target/context digest、requirement coverage、provenance、verification gaps、limitations
和建议的下一动作。需要 Markdown 时运行 `review_render.py`，但调用方门禁只能消费 validated JSON receipt。

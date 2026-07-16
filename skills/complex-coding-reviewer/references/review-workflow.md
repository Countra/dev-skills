# 审查工作流

## 1. 固定调用边界

先记录：profile、scope、target root、review root、调用方期望和 reviewer provenance。Reviewer 不负责获取远端 PR/MR、
修复目标、执行验证或写 ledger；这些动作由调用方或其它 skill 完成。

`plan-review` 只接受 `plan-bundle`。`code-review` 接受：

- `stage-delta`：stage baseline 到当前工作树，必须携带 stage ID 与 attempt。
- `final-integration`：execution baseline 到当前整体工作树。
- `standalone`：显式文件、工作树或 commit range。

目标或 scope 混合时拆分 attempt。没有 baseline 时不得用“当前看起来像 diff”代替可重建 target。

## 2. 生成目标

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

## 3. 执行语义审查

1. 先读目标 manifest，确认所有路径、删除项、baseline/head 和 scope 正确。
2. 读取足以判断行为的调用方、定义、配置、错误路径、测试和规范证据；不要只读 diff 片段。
3. 按 profile reference 的固定 lens 顺序记录状态。`reviewed`/`blocked` 必须有 evidence；
   `not-applicable` 必须在 summary 说明原因。
4. finding 只记录会影响正确性、可维护性、交付风险或规划可执行性的具体问题。个人偏好只能是 advisory。
5. 不确定判断要降低 confidence、补证据或写入 limitation；低置信猜测不能定为 blocking。

## 4. 写 receipt 并校验

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

## 5. 修复与复审

`changes_required`：把 receipt 交还 Planner 或 Executor；Reviewer 不自行修复。目标修复后旧 digest 立即 stale，创建
完整新 attempt，不从旧报告继承通过。`blocked`：补齐用户决策、权限、证据或专业 reviewer 后再创建新 attempt。

## 6. 交付

先列开放 findings，再说明 verdict、target digest、provenance、limitations 和建议的下一动作。需要 Markdown 时运行
`review_render.py`，但调用方门禁只能消费 validated JSON receipt。

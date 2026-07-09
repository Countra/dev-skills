# GitLab Skill Workflow

## 默认流程

1. 先运行 `gl_doctor.py --offline-check`，确认 `SKILL_GITLAB_BASE_URL` 和 token 来源。
2. 需要真实 GitLab 访问时运行 `gl_doctor.py`，只访问 `/user`。
3. 用只读命令定位目标项目、issue、note、branch 或 MR。
4. 写操作先运行 dry-run，检查目标 URL、参数和脱敏请求摘要。
5. 用户确认目标无误后才加 `--confirm`。
6. 记录验证覆盖范围，不能把未执行 live smoke 写成通过。

## 常见任务

### 查项目

```powershell
python skills\gitlab\scripts\gl_projects.py search codex_test --pretty
python skills\gitlab\scripts\gl_projects.py get group/codex_test --pretty
```

### 查 issue 和评论

```powershell
python skills\gitlab\scripts\gl_issues.py list --project group/codex_test --state opened --pretty
python skills\gitlab\scripts\gl_issues.py get --project group/codex_test --iid 1 --pretty
python skills\gitlab\scripts\gl_notes.py issue-list --project group/codex_test --iid 1 --only-comments --compact --pretty
```

### 回复测试评论

先 dry-run：

```powershell
python skills\gitlab\scripts\gl_notes.py issue-reply --project group/codex_test --iid 1 --body-file .\message.txt --pretty
```

确认只在 `codex_test` 测试仓库后再真实发送：

```powershell
python skills\gitlab\scripts\gl_notes.py issue-reply --project group/codex_test --iid 1 --body-file .\message.txt --confirm --pretty
```

评论内容应带明确标记，例如 `[codex gitlab skill smoke]`，便于回溯。

### 查 MR

```powershell
python skills\gitlab\scripts\gl_mrs.py list --project group/codex_test --state opened --pretty
python skills\gitlab\scripts\gl_mrs.py get --project group/codex_test --iid 1 --pretty
```

### 查仓库文件

```powershell
python skills\gitlab\scripts\gl_repo.py tree --project group/codex_test --ref main --pretty
python skills\gitlab\scripts\gl_repo.py file --project group/codex_test --file-path README.md --ref main --pretty
```

## 错误处理

- `401/403`: 检查 PAT scope，写操作通常需要 `api`。
- `404`: 检查项目路径是否正确；脚本会 URL encode 项目路径。
- `409/422`: 检查创建项目、MR 或评论的请求体。
- `429`: 脚本按 GitLab header 做有限退避，仍失败时记录限流。

## 禁止流程

- 不直接手写 curl 带 token。
- 不把 token 放进命令行、日志、测试 fixture、`.harness` 或 commit message。
- 不对非测试仓库执行 live 写入 smoke。
- 不执行删除、关闭、合并、approve、force push、权限变更、token 管理或批量跨仓库写入。

# GitLab PAT Ops Security

## 环境变量

本 skill 只读取专属环境变量：

- `SKILL_GITLAB_BASE_URL`
- `SKILL_GITLAB_PAT`
- `SKILL_GITLAB_TOKEN`

默认不读取通用 `GITLAB_TOKEN`，避免误用其它 GitLab 工具的凭据。

`gl_capabilities.py` 不读取任何 token，也不访问网络；它只展示当前维护的能力边界。

PowerShell 示例：

```powershell
$env:SKILL_GITLAB_BASE_URL="https://gitlab.example.com"
$env:SKILL_GITLAB_PAT="..."
```

## PAT Scope

- 只读 API：优先 `read_api`。
- 私有仓库文件读取：可能需要 `read_repository`。
- 回复评论、创建项目、创建 issue、创建 MR、关闭或重开 issue/MR：需要 `api`。
- 新建 issue 还需要用户在目标项目中具备创建 issue 的权限。
- `write_repository` 不支持 REST API authentication，不能作为写 API 的凭据说明。

## 脱敏规则

- 不打印 token。
- 请求预览不包含认证 header。
- 错误输出要替换 token 为 `***redacted***`。
- dry-run 中的评论正文只显示长度和短 preview，不输出完整正文。
- 真实 live smoke 记录仓库、对象 ID、note ID 或 URL，不记录 token。

## 写操作规则

- 没有 `--confirm` 时不得发送 POST。
- 写操作必须支持 dry-run。
- 评论正文优先使用 `--body-file` 或 `--stdin`。
- `--body` 可用于短测试内容，但可能进入 shell history。
- 创建 issue 时默认预检 labels，避免 GitLab 因未知 label 自动创建新 label；只有明确需要时才使用 `--allow-new-labels`。
- issue/MR close/reopen 只允许 `state_event=close/reopen`，不得扩展为 merge、approve、delete。
- 写操作失败时不得重复盲发，必须先定位错误原因。

## Live Smoke 边界

用户已允许使用当前环境变量做测试，但 live 写入只允许在 `codex_test` 测试仓库中执行。

允许：

- `/user` 认证检查。
- 项目只读搜索或详情读取。
- `codex_test` 内低风险 issue/MR 评论回复 smoke。
- `codex_test` 内 issue 创建 dry-run 和 issue/MR close/reopen dry-run。
- 明确批准时，可在 `codex_test` 创建带 smoke 标记的 issue，并关闭同一个 smoke issue。

默认不做：

- 真实创建项目。
- 真实创建 MR，除非有明确测试分支且不会影响协作流程。
- 真实关闭 MR，除非有明确 disposable test MR 且用户再次确认。

禁止：

- 删除项目、文件、分支、issue、MR 或 note。
- merge、approve、force push。
- 权限变更、token 管理、CI/CD 管理。
- 批量修改或跨仓库写入。

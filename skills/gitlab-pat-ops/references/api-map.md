# GitLab PAT Ops REST API Map

本表只覆盖当前 skill v1 支持的 endpoint。扩展新 endpoint 前先运行 `gl_capabilities.py --pretty` 确认当前能力边界，再确认 GitLab 官方文档和安全边界。

## Authentication

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
| 能力边界清单 | `gl_capabilities.py` | none | none | 本地 JSON 输出，不读取 token、不访问网络 |
| 认证检查 | `gl_doctor.py` | `GET /user` | `read_api` 或 `api` | 使用 `PRIVATE-TOKEN` header |

## Projects

| 能力 | 脚本 | Endpoint | Scope | 安全边界 |
| --- | --- | --- | --- | --- |
| 列表/搜索项目 | `gl_projects.py list/search` | `GET /projects` | `read_api` | 只读 |
| 项目详情 | `gl_projects.py get` | `GET /projects/:id` | `read_api` | `:id` 支持 URL-encoded path |
| 创建项目 | `gl_projects.py create` | `POST /projects` | `api` | 默认 dry-run，真实请求必须 `--confirm` |

## Search

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
| 全局搜索 | `gl_search.py` | `GET /search` | `read_api` | 支持 `projects`、`issues`、`merge_requests` 等 scope |
| 项目搜索 | `gl_search.py --project` | `GET /projects/:id/search` | `read_api` | code search 可能受 GitLab 版本/许可限制 |

## Repository

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
| tree | `gl_repo.py tree` | `GET /projects/:id/repository/tree` | `read_api` / `read_repository` | GitLab 17.7 起缺失 path 返回 404 |
| file | `gl_repo.py file` | `GET /projects/:id/repository/files/:file_path` | `read_api` / `read_repository` | content 为 base64 |
| raw file | `gl_repo.py raw` | `GET /projects/:id/repository/files/:file_path/raw` | `read_api` / `read_repository` | 输出 raw 文本 |
| blob | `gl_repo.py blob` | `GET /projects/:id/repository/blobs/:sha` | `read_api` / `read_repository` | 大 blob 可能限流 |
| raw blob | `gl_repo.py blob --raw` | `GET /projects/:id/repository/blobs/:sha/raw` | `read_api` / `read_repository` | 输出 raw 文本 |

## Labels

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
| label 列表 | `gl_labels.py list` | `GET /projects/:id/labels` | `read_api` | 支持 search、with_counts、ancestor groups |
| label 详情 | `gl_labels.py get` | `GET /projects/:id/labels/:label_id` | `read_api` | `:label_id` 支持名称或 ID |

## Milestones

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
| milestone 列表 | `gl_milestones.py list` | `GET /projects/:id/milestones` | `read_api` | 支持 state/title/search |
| milestone 详情 | `gl_milestones.py get` | `GET /projects/:id/milestones/:milestone_id` | `read_api` | 用于创建 issue 前选择 `milestone_id` |
| milestone issue | `gl_milestones.py issues` | `GET /projects/:id/milestones/:milestone_id/issues` | `read_api` | 只读 |
| milestone MR | `gl_milestones.py mrs` | `GET /projects/:id/milestones/:milestone_id/merge_requests` | `read_api` | 只读 |

## Members and Branches

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
| 成员列表 | `gl_members.py list` | `GET /projects/:id/members` / `GET /projects/:id/members/all` | `read_api` | 用于选择 assignee/reviewer |
| 成员详情 | `gl_members.py get` | `GET /projects/:id/members/:user_id` / `GET /projects/:id/members/all/:user_id` | `read_api` | 只读 |
| 分支列表 | `gl_branches.py list` | `GET /projects/:id/repository/branches` | `read_api` / `read_repository` | 支持 search/regex |
| 分支详情 | `gl_branches.py get` | `GET /projects/:id/repository/branches/:branch` | `read_api` / `read_repository` | 用于 MR 前置确认 |

## Issue Templates

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
| 模板列表 | `gl_issue_templates.py list` | `GET /projects/:id/repository/tree` | `read_api` / `read_repository` | 默认查 `.gitlab/issue_templates` |
| 模板内容 | `gl_issue_templates.py get` | `GET /projects/:id/repository/files/:file_path/raw` | `read_api` / `read_repository` | 仅允许单个 Markdown 文件名 |

## Issues

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
| issue 列表 | `gl_issues.py list` | `GET /projects/:id/issues` | `read_api` | 支持 state/search/labels |
| issue 详情 | `gl_issues.py get` | `GET /projects/:id/issues/:issue_iid` | `read_api` | 使用 issue IID |
| 关联 MR | `gl_issues.py related-mrs` | `GET /projects/:id/issues/:issue_iid/related_merge_requests` | `read_api` | 只读 |
| 关闭来源 MR | `gl_issues.py closed-by` | `GET /projects/:id/issues/:issue_iid/closed_by` | `read_api` | 只读 |
| 新建 issue | `gl_issues.py create` | `POST /projects/:id/issues` | `api` | 默认 dry-run，真实请求必须 `--confirm`；labels 默认预检 |
| 更新 issue 描述 | `gl_issues.py update-description` | `PUT /projects/:id/issues/:issue_iid` | `api` | 默认 dry-run，真实请求必须 `--confirm`；只发送 `description` 字段；默认拒绝空描述 |
| 关闭/重开 issue | `gl_issues.py close/reopen` | `PUT /projects/:id/issues/:issue_iid` | `api` | 默认 dry-run，`state_event` 限定 close/reopen |

## Notes

| 能力 | 脚本 | Endpoint | Scope | 安全边界 |
| --- | --- | --- | --- | --- |
| issue notes | `gl_notes.py issue-list` | `GET /projects/:id/issues/:issue_iid/notes` | `read_api` | `--compact` 输出评论解析字段 |
| MR notes | `gl_notes.py mr-list` | `GET /projects/:id/merge_requests/:merge_request_iid/notes` | `read_api` | `--only-comments` 过滤系统记录 |
| 回复 issue | `gl_notes.py issue-reply` | `POST /projects/:id/issues/:issue_iid/notes` | `api` | 默认 dry-run，真实请求必须 `--confirm` |
| 回复 MR | `gl_notes.py mr-reply` | `POST /projects/:id/merge_requests/:merge_request_iid/notes` | `api` | live 写入只允许 `codex_test` |

## Merge Requests

| 能力 | 脚本 | Endpoint | Scope | 安全边界 |
| --- | --- | --- | --- | --- |
| MR 列表 | `gl_mrs.py list` | `GET /projects/:id/merge_requests` | `read_api` | 只读 |
| MR 详情 | `gl_mrs.py get` | `GET /projects/:id/merge_requests/:merge_request_iid` | `read_api` | 只读 |
| MR notes | `gl_mrs.py notes` | `GET /projects/:id/merge_requests/:merge_request_iid/notes` | `read_api` | 只读 |
| 创建 MR | `gl_mrs.py create` | `POST /projects/:id/merge_requests` | `api` | 默认 dry-run，真实 live smoke 默认不执行 |
| 关闭/重开 MR | `gl_mrs.py close/reopen` | `PUT /projects/:id/merge_requests/:merge_request_iid` | `api` | 默认 dry-run，真实关闭 MR 需要 disposable test MR 和明确批准 |

## Not Supported

| 能力 | 可能 Endpoint | 原因 |
| --- | --- | --- |
| 删除项目、文件、分支、issue、MR 或 note | varies | destructive operation |
| merge / approve MR | varies | 高影响协作流程操作 |
| force push 或删除分支 | varies | 高风险仓库操作 |
| 权限、成员或 token 管理 | varies | 凭据和访问控制风险 |
| CI/CD 管理 | varies | 超出当前 skill 范围 |
| 批量跨仓库写入 | varies | 超出当前 guarded write 策略 |

## Pagination

- 列表类脚本支持 `--page`、`--per-page` 和 `--all`。
- `--per-page` 最大值按 GitLab REST API 约束为 100。
- `--all` 优先使用 `Link` header 和 `X-Next-Page`。

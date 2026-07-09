# GitLab REST API Map

本表只覆盖当前 skill v1 支持的 endpoint。扩展新 endpoint 前先确认 GitLab 官方文档和安全边界。

## Authentication

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
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

## Issues

| 能力 | 脚本 | Endpoint | Scope | 备注 |
| --- | --- | --- | --- | --- |
| issue 列表 | `gl_issues.py list` | `GET /projects/:id/issues` | `read_api` | 支持 state/search/labels |
| issue 详情 | `gl_issues.py get` | `GET /projects/:id/issues/:issue_iid` | `read_api` | 使用 issue IID |
| 关联 MR | `gl_issues.py related-mrs` | `GET /projects/:id/issues/:issue_iid/related_merge_requests` | `read_api` | 只读 |
| 关闭来源 MR | `gl_issues.py closed-by` | `GET /projects/:id/issues/:issue_iid/closed_by` | `read_api` | 只读 |

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

## Pagination

- 列表类脚本支持 `--page`、`--per-page` 和 `--all`。
- `--per-page` 最大值按 GitLab REST API 约束为 100。
- `--all` 优先使用 `Link` header 和 `X-Next-Page`。

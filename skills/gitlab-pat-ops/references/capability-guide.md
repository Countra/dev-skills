# Capability Composition Guide

Use this reference only when a task spans several GitLab resources or the correct command is unclear. `scripts/gitlab_ops/registry.py`, queried through `gl_capabilities.py`, is the only endpoint and capability source of truth.

## Discovery Order

1. Locate a namespace or project with `gl_namespaces.py` or `gl_projects.py`.
2. Reuse the returned numeric project ID or full path in later commands.
3. Locate the concrete issue, MR, branch, commit, pipeline, or job.
4. Read supporting resources only when they affect the task.
5. For writes, finish discovery before generating a dry-run fingerprint.

## Common Compositions

| Intent | Resource sequence |
| --- | --- |
| Understand an issue | project -> issue -> notes/discussions/events -> related or closing MRs |
| Create an issue | project -> Project Template -> labels/milestone/members -> issue dry-run -> apply -> issue reread |
| Update an issue | issue -> supporting metadata -> generic metadata dry-run -> apply -> issue/events reread |
| Review an MR | project -> MR -> commits/diffs -> approvals -> pipelines/jobs -> discussions/events |
| Create an MR | project -> source/target branches -> MR template/members -> MR dry-run -> apply -> MR reread |
| Reply in a thread | issue/MR -> discussion get -> reply dry-run -> apply -> discussion reread |
| Resolve a review thread | MR -> discussion get -> resolve/reopen dry-run -> apply -> discussion reread |
| Diagnose a failed pipeline | project -> pipeline -> jobs/bridges -> related MR/commit context |
| Diagnose access | offline doctor -> live doctor -> exact capability query only if still unclear |

Project templates come from GitLab's Project Templates API and support both `issues` and `merge_requests`. Repository-tree template reconstruction is not a fallback.

## Read Selection

Use filters before `--all`. When all pages are necessary, keep page, item, and byte budgets bounded. Use `gl_repo.py raw|blob --output` for binary artifacts; use commit and MR diff commands for review context instead of reconstructing diffs from repository files.

Approval commands are read-only. Pipelines and jobs are read-only. The skill never turns a read-context command into an approval, retry, cancel, branch, or CI mutation.

## Registry Queries

Prefer `--capability`, then `--resource` or `--mode`; use `--all` only when a complete inventory is genuinely needed. A known command does not require a registry query.

Every registered write declares its method, script, exact subcommand, scope, preflight, and confirmation policy. Prohibited results are final boundaries, not invitations to issue raw REST calls.

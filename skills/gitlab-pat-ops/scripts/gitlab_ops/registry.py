"""gitlab-pat-ops 的单一能力注册表。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .config import BASE_URL_ENV, TOKEN_ENV


@dataclass(frozen=True)
class Capability:
    capability_id: str
    resource: str
    mode: str
    script: str
    subcommand: str
    method: str
    endpoint: str
    required_scope: str
    risk: str
    preflight: str
    confirmation: str
    output_shape: str = "envelope"
    tier_notes: str = "GitLab REST API v4；实例版本或 tier 不支持时保留 403/404 原义"


def _read(
    capability_id: str,
    resource: str,
    script: str,
    subcommand: str,
    endpoint: str,
) -> Capability:
    return Capability(
        capability_id,
        resource,
        "read",
        script,
        subcommand,
        "GET",
        endpoint,
        "read_api",
        "low",
        "none",
        "none",
    )


def _write(
    capability_id: str,
    resource: str,
    script: str,
    subcommand: str,
    method: str,
    endpoint: str,
    preflight: str,
) -> Capability:
    return Capability(
        capability_id,
        resource,
        "write",
        script,
        subcommand,
        method,
        endpoint,
        "api",
        "guarded",
        preflight,
        "exact preview fingerprint + apply-time drift check",
    )


_EVENT_CAPABILITIES = tuple(
    _read(
        f"resource_events.{resource}.{event}.{action}",
        "resource_events",
        "gl_resource_events.py",
        action,
        f"/projects/:id/{'issues' if resource == 'issue' else 'merge_requests'}/:iid/resource_{event}_events"
        + ("/:event_id" if action == "get" else ""),
    )
    for resource in ("issue", "mr")
    for event in ("state", "label", "milestone")
    for action in ("list", "get")
)


CAPABILITIES: tuple[Capability, ...] = (
    _read("auth.user", "auth", "gl_doctor.py", "", "/user"),
    _read("projects.list", "projects", "gl_projects.py", "list", "/projects"),
    _read("projects.search", "projects", "gl_projects.py", "search", "/projects"),
    _read("projects.get", "projects", "gl_projects.py", "get", "/projects/:id"),
    _write("projects.create", "projects", "gl_projects.py", "create", "POST", "/projects", "namespace snapshot"),
    _read("namespaces.list", "namespaces", "gl_namespaces.py", "list", "/namespaces"),
    _read("namespaces.get", "namespaces", "gl_namespaces.py", "get", "/namespaces/:id"),
    _read("search.query", "search", "gl_search.py", "", "/search or /projects/:id/search"),
    _read("repository.tree", "repository", "gl_repo.py", "tree", "/projects/:id/repository/tree"),
    _read("repository.file", "repository", "gl_repo.py", "file", "/projects/:id/repository/files/:path"),
    _read("repository.raw", "repository", "gl_repo.py", "raw", "/projects/:id/repository/files/:path/raw"),
    _read("repository.blob", "repository", "gl_repo.py", "blob", "/projects/:id/repository/blobs/:sha[/raw]"),
    _read("commits.list", "commits", "gl_commits.py", "list", "/projects/:id/repository/commits"),
    _read("commits.get", "commits", "gl_commits.py", "get", "/projects/:id/repository/commits/:sha"),
    _read("commits.refs", "commits", "gl_commits.py", "refs", "/projects/:id/repository/commits/:sha/refs"),
    _read("commits.merge_requests", "commits", "gl_commits.py", "merge-requests", "/projects/:id/repository/commits/:sha/merge_requests"),
    _read("commits.diff", "commits", "gl_commits.py", "diff", "/projects/:id/repository/commits/:sha/diff"),
    _read("branches.list", "branches", "gl_branches.py", "list", "/projects/:id/repository/branches"),
    _read("branches.get", "branches", "gl_branches.py", "get", "/projects/:id/repository/branches/:branch"),
    _read("labels.list", "labels", "gl_labels.py", "list", "/projects/:id/labels"),
    _read("labels.get", "labels", "gl_labels.py", "get", "/projects/:id/labels/:label"),
    _read("milestones.list", "milestones", "gl_milestones.py", "list", "/projects/:id/milestones"),
    _read("milestones.get", "milestones", "gl_milestones.py", "get", "/projects/:id/milestones/:milestone_id"),
    _read("milestones.issues", "milestones", "gl_milestones.py", "issues", "/projects/:id/milestones/:milestone_id/issues"),
    _read("milestones.merge_requests", "milestones", "gl_milestones.py", "mrs", "/projects/:id/milestones/:milestone_id/merge_requests"),
    _read("members.list", "members", "gl_members.py", "list", "/projects/:id/members[/all]"),
    _read("members.get", "members", "gl_members.py", "get", "/projects/:id/members[/all]/:user_id"),
    _read("templates.list", "templates", "gl_templates.py", "list", "/projects/:id/templates/:type"),
    _read("templates.get", "templates", "gl_templates.py", "get", "/projects/:id/templates/:type/:name"),
    _read("issues.list", "issues", "gl_issues.py", "list", "/projects/:id/issues"),
    _read("issues.get", "issues", "gl_issues.py", "get", "/projects/:id/issues/:iid"),
    _read("issues.related_merge_requests", "issues", "gl_issues.py", "related-mrs", "/projects/:id/issues/:iid/related_merge_requests"),
    _read("issues.closed_by", "issues", "gl_issues.py", "closed-by", "/projects/:id/issues/:iid/closed_by"),
    _write("issues.create", "issues", "gl_issues.py", "create", "POST", "/projects/:id/issues", "project, labels, template"),
    _write("issues.update", "issues", "gl_issues.py", "update", "PUT", "/projects/:id/issues/:iid", "issue snapshot"),
    _write("issues.close", "issues", "gl_issues.py", "close", "PUT", "/projects/:id/issues/:iid", "issue snapshot"),
    _write("issues.reopen", "issues", "gl_issues.py", "reopen", "PUT", "/projects/:id/issues/:iid", "issue snapshot"),
    _read("merge_requests.list", "merge_requests", "gl_mrs.py", "list", "/projects/:id/merge_requests"),
    _read("merge_requests.get", "merge_requests", "gl_mrs.py", "get", "/projects/:id/merge_requests/:iid"),
    _write("merge_requests.create", "merge_requests", "gl_mrs.py", "create", "POST", "/projects/:id/merge_requests", "project, branches, template"),
    _write("merge_requests.update", "merge_requests", "gl_mrs.py", "update", "PUT", "/projects/:id/merge_requests/:iid", "MR snapshot"),
    _write("merge_requests.close", "merge_requests", "gl_mrs.py", "close", "PUT", "/projects/:id/merge_requests/:iid", "MR snapshot"),
    _write("merge_requests.reopen", "merge_requests", "gl_mrs.py", "reopen", "PUT", "/projects/:id/merge_requests/:iid", "MR snapshot"),
    _read("notes.issue.list", "notes", "gl_notes.py", "issue-list", "/projects/:id/issues/:iid/notes"),
    _read("notes.mr.list", "notes", "gl_notes.py", "mr-list", "/projects/:id/merge_requests/:iid/notes"),
    _write("notes.issue.create", "notes", "gl_notes.py", "issue-reply", "POST", "/projects/:id/issues/:iid/notes", "issue snapshot"),
    _write("notes.mr.create", "notes", "gl_notes.py", "mr-reply", "POST", "/projects/:id/merge_requests/:iid/notes", "MR snapshot"),
    _read("discussions.issue.list", "discussions", "gl_discussions.py", "list", "/projects/:id/issues/:iid/discussions"),
    _read("discussions.issue.get", "discussions", "gl_discussions.py", "get", "/projects/:id/issues/:iid/discussions/:discussion_id"),
    _write("discussions.issue.reply", "discussions", "gl_discussions.py", "reply", "POST", "/projects/:id/issues/:iid/discussions/:discussion_id/notes", "discussion snapshot"),
    _read("discussions.mr.list", "discussions", "gl_discussions.py", "list", "/projects/:id/merge_requests/:iid/discussions"),
    _read("discussions.mr.get", "discussions", "gl_discussions.py", "get", "/projects/:id/merge_requests/:iid/discussions/:discussion_id"),
    _write("discussions.mr.reply", "discussions", "gl_discussions.py", "reply", "POST", "/projects/:id/merge_requests/:iid/discussions/:discussion_id/notes", "discussion snapshot"),
    _write("discussions.mr.resolve", "discussions", "gl_discussions.py", "resolve", "PUT", "/projects/:id/merge_requests/:iid/discussions/:discussion_id", "discussion snapshot"),
    _write("discussions.mr.reopen", "discussions", "gl_discussions.py", "reopen", "PUT", "/projects/:id/merge_requests/:iid/discussions/:discussion_id", "discussion snapshot"),
    *_EVENT_CAPABILITIES,
    _read("merge_request_diffs.list", "merge_request_diffs", "gl_mr_diffs.py", "list", "/projects/:id/merge_requests/:iid/diffs"),
    _read("merge_request_diffs.versions", "merge_request_diffs", "gl_mr_diffs.py", "versions", "/projects/:id/merge_requests/:iid/versions"),
    _read("merge_request_diffs.get_version", "merge_request_diffs", "gl_mr_diffs.py", "get-version", "/projects/:id/merge_requests/:iid/versions/:version_id"),
    _read("pipelines.list", "pipelines", "gl_pipelines.py", "list", "/projects/:id/pipelines"),
    _read("pipelines.get", "pipelines", "gl_pipelines.py", "get", "/projects/:id/pipelines/:pipeline_id"),
    _read("pipelines.latest", "pipelines", "gl_pipelines.py", "latest", "/projects/:id/pipelines/latest"),
    _read("pipelines.jobs", "pipelines", "gl_pipelines.py", "jobs", "/projects/:id/pipelines/:pipeline_id/jobs"),
    _read("pipelines.bridges", "pipelines", "gl_pipelines.py", "bridges", "/projects/:id/pipelines/:pipeline_id/bridges"),
    _read("jobs.list", "jobs", "gl_pipelines.py", "project-jobs", "/projects/:id/jobs"),
    _read("jobs.get", "jobs", "gl_pipelines.py", "job", "/projects/:id/jobs/:job_id"),
    _read("merge_request_pipelines.list", "pipelines", "gl_pipelines.py", "mr", "/projects/:id/merge_requests/:iid/pipelines"),
    _read("merge_request_approvals.summary", "approvals", "gl_approvals.py", "summary", "/projects/:id/merge_requests/:iid/approvals"),
    _read("merge_request_approvals.state", "approvals", "gl_approvals.py", "state", "/projects/:id/merge_requests/:iid/approval_state"),
    _read("merge_request_approvals.rules", "approvals", "gl_approvals.py", "rules", "/projects/:id/merge_requests/:iid/approval_rules"),
)


PROHIBITED: tuple[dict[str, str], ...] = (
    {"capability_id": "projects.delete", "reason": "destructive project operation"},
    {"capability_id": "merge_requests.merge", "reason": "high-impact workflow operation"},
    {"capability_id": "merge_requests.approve", "reason": "high-impact approval operation"},
    {"capability_id": "repository.mutate", "reason": "repository and branch mutation is outside scope"},
    {"capability_id": "branches.mutate", "reason": "branch mutation is outside scope"},
    {"capability_id": "permissions.manage", "reason": "access-control risk"},
    {"capability_id": "tokens.manage", "reason": "credential risk"},
    {"capability_id": "ci.mutate", "reason": "CI mutation is outside scope"},
    {"capability_id": "writes.bulk", "reason": "bulk cross-project write is prohibited"},
)


def find_prohibited(capability_id: str) -> dict[str, str] | None:
    return next((item for item in PROHIBITED if item["capability_id"] == capability_id), None)


def select_capabilities(
    *,
    mode: str | None = None,
    resource: str | None = None,
    capability_id: str | None = None,
) -> list[dict[str, str]]:
    values: Iterable[Capability] = CAPABILITIES
    if mode:
        values = (item for item in values if item.mode == mode)
    if resource:
        values = (item for item in values if item.resource == resource)
    if capability_id:
        values = (item for item in values if item.capability_id == capability_id)
    return [asdict(item) for item in values]


def registry_document() -> dict[str, object]:
    return {
        "skill": {"name": "gitlab-pat-ops"},
        "environment": {
            "required": [BASE_URL_ENV, TOKEN_ENV],
            "auth_header": "PRIVATE-TOKEN",
        },
        "capabilities": select_capabilities(),
        "prohibited": list(PROHIBITED),
    }

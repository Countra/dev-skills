#!/usr/bin/env python3
"""在能力边界不确定时输出 gitlab-pat-ops 当前维护的能力边界。"""

from __future__ import annotations

import argparse
from typing import Any, Iterable

from gitlab_common import BASE_URL_ENV, TOKEN_ENVS, print_json


CAPABILITIES: dict[str, Any] = {
    "skill": {
        "name": "gitlab-pat-ops",
        "version": 1,
        "description": "PAT-based GitLab REST operations with guarded writes; inspect when capability boundaries are unclear.",
    },
    "environment": {
        "required": [BASE_URL_ENV, " or ".join(TOKEN_ENVS)],
        "token_sources": list(TOKEN_ENVS),
        "ignored_by_default": ["GITLAB_TOKEN"],
        "auth_header": "PRIVATE-TOKEN",
    },
    "read_only": [
        {
            "capability": "auth_check",
            "script": "gl_doctor.py",
            "commands": ["--offline-check", "live /user check"],
            "endpoints": ["GET /user"],
            "scopes": ["read_api", "api"],
        },
        {
            "capability": "projects",
            "script": "gl_projects.py",
            "commands": ["list", "search", "get"],
            "endpoints": ["GET /projects", "GET /projects/:id"],
            "scopes": ["read_api"],
        },
        {
            "capability": "search",
            "script": "gl_search.py",
            "commands": ["global search", "project search"],
            "endpoints": ["GET /search", "GET /projects/:id/search"],
            "scopes": ["read_api"],
        },
        {
            "capability": "repository",
            "script": "gl_repo.py",
            "commands": ["tree", "file", "raw", "blob"],
            "endpoints": [
                "GET /projects/:id/repository/tree",
                "GET /projects/:id/repository/files/:file_path",
                "GET /projects/:id/repository/files/:file_path/raw",
                "GET /projects/:id/repository/blobs/:sha",
                "GET /projects/:id/repository/blobs/:sha/raw",
            ],
            "scopes": ["read_api", "read_repository"],
        },
        {
            "capability": "issues",
            "script": "gl_issues.py",
            "commands": ["list", "get", "related-mrs", "closed-by"],
            "endpoints": [
                "GET /projects/:id/issues",
                "GET /projects/:id/issues/:issue_iid",
                "GET /projects/:id/issues/:issue_iid/related_merge_requests",
                "GET /projects/:id/issues/:issue_iid/closed_by",
            ],
            "scopes": ["read_api"],
        },
        {
            "capability": "issue_templates",
            "script": "gl_issue_templates.py",
            "commands": ["list", "get"],
            "endpoints": [
                "GET /projects/:id/repository/tree",
                "GET /projects/:id/repository/files/:file_path/raw",
            ],
            "scopes": ["read_api", "read_repository"],
            "notes": "project repository templates under .gitlab/issue_templates/*.md",
        },
        {
            "capability": "labels",
            "script": "gl_labels.py",
            "commands": ["list", "get"],
            "endpoints": ["GET /projects/:id/labels", "GET /projects/:id/labels/:label_id"],
            "scopes": ["read_api"],
        },
        {
            "capability": "milestones",
            "script": "gl_milestones.py",
            "commands": ["list", "get", "issues", "mrs"],
            "endpoints": [
                "GET /projects/:id/milestones",
                "GET /projects/:id/milestones/:milestone_id",
                "GET /projects/:id/milestones/:milestone_id/issues",
                "GET /projects/:id/milestones/:milestone_id/merge_requests",
            ],
            "scopes": ["read_api"],
        },
        {
            "capability": "members",
            "script": "gl_members.py",
            "commands": ["list", "get"],
            "endpoints": ["GET /projects/:id/members", "GET /projects/:id/members/all"],
            "scopes": ["read_api"],
        },
        {
            "capability": "branches",
            "script": "gl_branches.py",
            "commands": ["list", "get"],
            "endpoints": ["GET /projects/:id/repository/branches", "GET /projects/:id/repository/branches/:branch"],
            "scopes": ["read_api", "read_repository"],
        },
        {
            "capability": "notes",
            "script": "gl_notes.py",
            "commands": ["issue-list", "mr-list"],
            "endpoints": [
                "GET /projects/:id/issues/:issue_iid/notes",
                "GET /projects/:id/merge_requests/:merge_request_iid/notes",
            ],
            "scopes": ["read_api"],
        },
        {
            "capability": "merge_requests",
            "script": "gl_mrs.py",
            "commands": ["list", "get", "notes"],
            "endpoints": [
                "GET /projects/:id/merge_requests",
                "GET /projects/:id/merge_requests/:merge_request_iid",
                "GET /projects/:id/merge_requests/:merge_request_iid/notes",
            ],
            "scopes": ["read_api"],
        },
    ],
    "guarded_writes": [
        {
            "capability": "create_project",
            "script": "gl_projects.py",
            "command": "create",
            "endpoint": "POST /projects",
            "scopes": ["api"],
            "safety": ["dry-run by default", "--confirm required"],
            "live_smoke": "dry-run by default; real project creation is not part of routine smoke",
        },
        {
            "capability": "reply_issue_note",
            "script": "gl_notes.py",
            "command": "issue-reply",
            "endpoint": "POST /projects/:id/issues/:issue_iid/notes",
            "scopes": ["api"],
            "safety": ["dry-run by default", "--confirm required", "prefer --body-file or --stdin"],
            "live_smoke": "allowed only in the user-approved codex_test test repository",
        },
        {
            "capability": "reply_mr_note",
            "script": "gl_notes.py",
            "command": "mr-reply",
            "endpoint": "POST /projects/:id/merge_requests/:merge_request_iid/notes",
            "scopes": ["api"],
            "safety": ["dry-run by default", "--confirm required", "prefer --body-file or --stdin"],
            "live_smoke": "allowed only in the user-approved codex_test test repository",
        },
        {
            "capability": "create_merge_request",
            "script": "gl_mrs.py",
            "command": "create",
            "endpoint": "POST /projects/:id/merge_requests",
            "scopes": ["api"],
            "safety": ["dry-run by default", "--confirm required"],
            "live_smoke": "dry-run by default; real MR creation requires explicit safe test branches",
        },
        {
            "capability": "create_issue",
            "script": "gl_issues.py",
            "command": "create",
            "endpoint": "POST /projects/:id/issues",
            "scopes": ["api"],
            "safety": [
                "dry-run by default",
                "--confirm required",
                "labels are prechecked unless --allow-new-labels is set",
            ],
            "live_smoke": "dry-run by default; real issue creation is allowed only in codex_test when explicitly approved",
        },
        {
            "capability": "close_or_reopen_issue",
            "script": "gl_issues.py",
            "commands": ["close", "reopen"],
            "endpoint": "PUT /projects/:id/issues/:issue_iid",
            "scopes": ["api"],
            "safety": ["dry-run by default", "--confirm required", "state_event is limited to close/reopen"],
            "live_smoke": "dry-run by default; real close smoke only for disposable codex_test issue",
        },
        {
            "capability": "update_issue_description",
            "script": "gl_issues.py",
            "command": "update-description",
            "endpoint": "PUT /projects/:id/issues/:issue_iid",
            "scopes": ["api"],
            "safety": [
                "dry-run by default",
                "--confirm required",
                "only sends the description field",
                "prefer --description-file or --stdin for long content",
                "empty descriptions require --allow-empty-description",
            ],
            "live_smoke": "dry-run by default; real update is allowed only for explicitly approved codex_test issue descriptions",
        },
        {
            "capability": "close_or_reopen_merge_request",
            "script": "gl_mrs.py",
            "commands": ["close", "reopen"],
            "endpoint": "PUT /projects/:id/merge_requests/:merge_request_iid",
            "scopes": ["api"],
            "safety": ["dry-run by default", "--confirm required", "state_event is limited to close/reopen"],
            "live_smoke": "dry-run by default; real MR close requires a disposable test MR and explicit approval",
        },
    ],
    "not_supported": [
        {"capability": "delete_project_or_repo_items", "reason": "destructive operation"},
        {"capability": "merge_or_approve_mr", "reason": "high-impact workflow operation"},
        {"capability": "force_push_or_branch_delete", "reason": "destructive repository operation"},
        {"capability": "permission_or_token_management", "reason": "credential and access-control risk"},
        {"capability": "ci_cd_management", "reason": "outside current skill scope"},
        {"capability": "bulk_cross_repository_writes", "reason": "too broad for guarded write policy"},
    ],
    "validation_boundary": {
        "offline": ["quick_validate.py", "unittest", "AST parse", "JSONL parse", "doctor offline"],
        "live_read": [
            "/user",
            "project search/get",
            "issue list/get",
            "notes list",
            "labels/milestones/members/branches/templates read",
        ],
        "live_write": [
            "single marked issue/MR note in codex_test only",
            "dry-run issue description update by default; real update only for explicitly approved codex_test issue",
            "dry-run issue create and dry-run issue/MR state change by default",
            "real issue create/close only for explicitly approved codex_test smoke",
        ],
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="在不确定支持范围时展示 gitlab-pat-ops 当前能力边界")
    parser.add_argument("--pretty", action="store_true", help="格式化 JSON 输出")
    parser.add_argument(
        "--section",
        choices=["all", "environment", "read-only", "guarded-writes", "not-supported", "validation"],
        default="all",
        help="只输出指定能力分区",
    )
    return parser


def select_section(section: str) -> dict[str, Any]:
    if section == "all":
        return CAPABILITIES
    mapping = {
        "environment": "environment",
        "read-only": "read_only",
        "guarded-writes": "guarded_writes",
        "not-supported": "not_supported",
        "validation": "validation_boundary",
    }
    key = mapping[section]
    return {"skill": CAPABILITIES["skill"], key: CAPABILITIES[key]}


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print_json({"ok": True, "result": select_section(args.section)}, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

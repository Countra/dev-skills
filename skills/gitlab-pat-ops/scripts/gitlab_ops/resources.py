"""GitLab project、issue、MR 与 discussion 的公共路径和快照。"""

from __future__ import annotations

import hashlib
import urllib.parse
from typing import Any

from .errors import GitLabSkillError
from .safety import preflight_snapshot


RESOURCE_SEGMENTS = {"issue": "issues", "mr": "merge_requests"}


def quote_resource_id(value: str | int) -> str:
    return urllib.parse.quote(str(value), safe="")


def project_path(project: str | int) -> str:
    return f"/projects/{quote_resource_id(project)}"


def resource_path(kind: str, project: str | int, iid: str | int) -> str:
    segment = RESOURCE_SEGMENTS.get(kind)
    if segment is None:
        raise GitLabSkillError("resource kind 只允许 issue 或 mr")
    return f"{project_path(project)}/{segment}/{quote_resource_id(iid)}"


def project_snapshot(client: Any, project: str | int) -> dict[str, Any]:
    value = client.request("GET", project_path(project))
    return preflight_snapshot(value, ("id", "path_with_namespace", "archived", "visibility", "default_branch"))


def resource_snapshot(client: Any, kind: str, project: str | int, iid: str | int) -> dict[str, Any]:
    value = client.request("GET", resource_path(kind, project, iid))
    snapshot = preflight_snapshot(
        value,
        ("id", "iid", "state", "title", "updated_at", "description", "source_branch", "target_branch"),
        hash_fields=("description",),
    )
    labels = value.get("labels") if isinstance(value, dict) else None
    milestone = value.get("milestone") if isinstance(value, dict) else None
    assignees = value.get("assignees") if isinstance(value, dict) else None
    reviewers = value.get("reviewers") if isinstance(value, dict) else None
    snapshot["labels"] = sorted(str(label) for label in labels) if isinstance(labels, list) else []
    snapshot["milestone_id"] = milestone.get("id") if isinstance(milestone, dict) else None
    snapshot["assignee_ids"] = sorted(
        item.get("id") for item in assignees if isinstance(item, dict) and isinstance(item.get("id"), int)
    ) if isinstance(assignees, list) else []
    snapshot["reviewer_ids"] = sorted(
        item.get("id") for item in reviewers if isinstance(item, dict) and isinstance(item.get("id"), int)
    ) if isinstance(reviewers, list) else []
    return snapshot


def discussion_snapshot(
    client: Any,
    kind: str,
    project: str | int,
    iid: str | int,
    discussion_id: str,
) -> dict[str, Any]:
    path = f"{resource_path(kind, project, iid)}/discussions/{quote_resource_id(discussion_id)}"
    value = client.request("GET", path)
    if not isinstance(value, dict):
        raise GitLabSkillError("discussion 预检响应不是 JSON object")
    notes: list[dict[str, Any]] = []
    for note in value.get("notes", []):
        if not isinstance(note, dict):
            continue
        body = note.get("body")
        author = note.get("author")
        notes.append(
            {
                "id": note.get("id"),
                "type": note.get("type"),
                "resolvable": note.get("resolvable"),
                "resolved": note.get("resolved"),
                "resolved_at": note.get("resolved_at"),
                "updated_at": note.get("updated_at"),
                "author_id": author.get("id") if isinstance(author, dict) else None,
                "body_sha256": (
                    hashlib.sha256(body.encode("utf-8")).hexdigest() if isinstance(body, str) else None
                ),
            }
        )
    return {"id": value.get("id"), "individual_note": value.get("individual_note"), "notes": notes}

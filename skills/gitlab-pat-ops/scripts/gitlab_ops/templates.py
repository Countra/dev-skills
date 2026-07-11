"""GitLab Project Templates 读取与安全快照。"""

from __future__ import annotations

import hashlib
from typing import Any

from .errors import GitLabSkillError
from .resources import project_path, quote_resource_id


TEMPLATE_TYPES = ("issues", "merge_requests")


def template_params(source_template_project_id: int | None) -> dict[str, int | None]:
    if source_template_project_id is not None and source_template_project_id <= 0:
        raise GitLabSkillError("source template project id 必须大于 0")
    return {"source_template_project_id": source_template_project_id}


def read_template_content(
    client: Any,
    project: str | int,
    template_type: str,
    name: str,
    source_template_project_id: int | None = None,
) -> dict[str, Any]:
    if template_type not in TEMPLATE_TYPES:
        raise GitLabSkillError("template type 只允许 issues 或 merge_requests")
    if not name.strip():
        raise GitLabSkillError("模板名称不能为空")
    path = f"{project_path(project)}/templates/{template_type}/{quote_resource_id(name.strip())}"
    value = client.request("GET", path, params=template_params(source_template_project_id))
    if not isinstance(value, dict) or not isinstance(value.get("content"), str):
        raise GitLabSkillError("Project Templates API 未返回有效模板内容")
    return value


def template_snapshot(
    value: dict[str, Any],
    template_type: str,
    name: str,
    source_template_project_id: int | None,
) -> dict[str, Any]:
    content = value["content"]
    return {
        "type": template_type,
        "name": name,
        "source_template_project_id": source_template_project_id,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }

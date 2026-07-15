#!/usr/bin/env python3
"""dependency selection 的 contract scope 触发判断。"""

from __future__ import annotations

from typing import Any


MANIFEST_NAMES = {
    "go.mod",
    "go.sum",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "requirements.txt",
    "poetry.lock",
    "uv.lock",
    "cargo.toml",
    "cargo.lock",
    "pom.xml",
    "build.gradle",
    "composer.json",
    "composer.lock",
    "gemfile",
    "gemfile.lock",
}


def has_contract_dependency_trigger(contract: dict[str, Any]) -> bool:
    artifacts = contract.get("artifacts", [])
    if isinstance(artifacts, list) and any(
        isinstance(item, dict) and item.get("kind") == "dependency"
        for item in artifacts
    ):
        return True
    stages = contract.get("stages", [])
    if not isinstance(stages, list):
        return False
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        values = stage.get("allowed_changes", [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, str):
                continue
            normalized = value.replace("\\", "/").lower()
            name = normalized.rsplit("/", 1)[-1]
            if name in MANIFEST_NAMES or any(
                marker in normalized
                for marker in (
                    "lockfile",
                    "vendor/",
                    "base-image",
                    "dependency manifest",
                )
            ):
                return True
    return False

#!/usr/bin/env python3
"""dependency contract validators 共用的稳定诊断 helper。"""

from __future__ import annotations

from harness_contract import ValidationIssue, add_issue


def dependency_issue(
    issues: list[ValidationIssue],
    code: str,
    path: str,
    message: str,
    hint: str,
) -> None:
    add_issue(issues, code, path, message, hint)

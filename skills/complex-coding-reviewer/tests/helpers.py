"""Reviewer 单测的最小合法 target 与 receipt 工厂。"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import uuid
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_TEMP_ROOT = REPO_ROOT / ".harness" / "test-tmp" / "complex-coding-reviewer-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from complex_coding_reviewer.contract import CODE_LENSES, PLAN_LENSES
from complex_coding_reviewer.target import (
    build_file_manifest_target,
    build_plan_bundle_target,
)


@contextmanager
def writable_tempdir():
    """创建不会被 Windows 私有临时目录 ACL 锁住的测试目录。"""

    path = TEST_TEMP_ROOT / f"case-{uuid.uuid4().hex}"
    path.mkdir(mode=0o777)
    try:
        yield str(path)
    finally:
        def remove_readonly(function, target, _error):
            os.chmod(target, stat.S_IWRITE)
            function(target)

        shutil.rmtree(path, onexc=remove_readonly)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def create_file_target(workspace: Path) -> dict[str, Any]:
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "src" / "example.py").write_text("answer = 42\n", encoding="utf-8")
    return build_file_manifest_target(workspace, ["src/example.py"], label="unit-test")


def create_plan_target(task_dir: Path) -> dict[str, Any]:
    contract = {
        "task_id": "test-plan",
        "plan_revision": 1,
        "artifacts": [
            {
                "id": "ART-01",
                "kind": "architecture",
                "path": "artifacts/architecture.md",
                "required": True,
                "approval_included": True,
            },
            {
                "id": "ART-02",
                "kind": "review",
                "path": "artifacts/review.json",
                "required": True,
                "approval_included": True,
            },
        ],
    }
    write_json(task_dir / "plan-contract.json", contract)
    (task_dir / "execution-plan.md").write_text("# Plan\n\nGOAL-01\n", encoding="utf-8")
    (task_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (task_dir / "artifacts" / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    return build_plan_bundle_target(task_dir)


def lens_records(profile: str) -> list[dict[str, Any]]:
    lenses = PLAN_LENSES if profile == "plan-review" else CODE_LENSES
    return [
        {
            "id": lens,
            "status": "reviewed",
            "evidence_refs": ["src/example.py:1"],
            "summary": f"{lens} 已基于目标证据完成审查。",
        }
        for lens in lenses
    ]


def receipt_for_target(
    target: dict[str, Any],
    *,
    profile: str = "code-review",
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if profile == "plan-review":
        scope = scope or {
            "kind": "managed-plan",
            "task_id": target["identity"]["task_id"],
            "plan_revision": target["identity"]["plan_revision"],
        }
        review_id = "REV-PLAN-001"
    else:
        scope = scope or {"kind": "standalone"}
        review_id = "REV-CODE-001"
    return {
        "review_id": review_id,
        "profile": profile,
        "scope": scope,
        "target": deepcopy(target),
        "reviewer": {
            "mode": "same-context",
            "identity": "unit-test-reviewer",
            "independence_claim": False,
            "capability_limits": ["未执行目标代码。"],
        },
        "standards": [
            {
                "id": "STD-01",
                "title": "Repository rules",
                "source": "AGENTS.md",
                "applicability": "适用于当前目标。",
            }
        ],
        "lenses": lens_records(profile),
        "findings": [],
        "verdict": "passed",
        "open_counts": {
            "blocking": 0,
            "major": 0,
            "minor": 0,
            "advisory": 0,
            "total": 0,
        },
        "summary": "目标已完成正式审查，未发现阻断问题。",
        "limitations": ["未运行测试，仅消费已有证据。"],
        "supersedes_review_id": None,
        "reviewed_at": "2026-07-16T00:00:00+00:00",
    }


def finding(
    *,
    finding_id: str = "FIND-001",
    severity: str = "major",
    status: str = "open",
    confidence: str = "high",
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": severity,
        "status": status,
        "title": "目标行为缺少边界处理",
        "claim": "空输入会进入未处理分支。",
        "impact": "调用方可能收到未声明异常。",
        "recommendation": "增加边界判断与失败路径测试。",
        "evidence": [
            {
                "path": "src/example.py",
                "line": 1,
                "symbol": None,
                "artifact_ref": None,
                "standard_ref": None,
                "detail": "当前实现直接使用输入。",
            }
        ],
        "confidence": confidence,
        "disposition_reason": None if status == "open" else "已由新目标修复或确认无效。",
    }


def update_counts_and_verdict(receipt: dict[str, Any]) -> None:
    counts = {severity: 0 for severity in ("blocking", "major", "minor", "advisory")}
    for item in receipt["findings"]:
        if item["status"] == "open":
            counts[item["severity"]] += 1
    receipt["open_counts"] = {**counts, "total": sum(counts.values())}
    blocked = any(item["status"] == "blocked" for item in receipt["lenses"])
    unresolved = any(
        item["severity"] in {"blocking", "major"}
        and item["status"] in {"open", "accepted", "deferred"}
        for item in receipt["findings"]
    )
    receipt["verdict"] = "blocked" if blocked else "changes_required" if unresolved else "passed"

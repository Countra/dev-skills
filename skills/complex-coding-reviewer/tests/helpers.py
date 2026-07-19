"""Reviewer 单测的最小合法 target 与 receipt 工厂。"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_TEMP_ROOT = REPO_ROOT / ".harness" / "test-tmp" / "complex-coding-reviewer-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from complex_coding_reviewer.contract import CODE_LENSES, PLAN_LENSES
from complex_coding_reviewer.context import RISK_IDS, build_context_target
from complex_coding_reviewer.assemble import assemble_receipt
from complex_coding_reviewer.dispatch import prepare_dispatch
from complex_coding_reviewer.dispatch_lifecycle import finalize_dispatch
from complex_coding_reviewer.io import resolve_review_ref, sha256_file
from complex_coding_reviewer.semantic_result import RECEIPT_SEMANTIC_FIELDS
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


def lens_records(profile: str, evidence_ref: str) -> list[dict[str, Any]]:
    lenses = PLAN_LENSES if profile == "plan-review" else CODE_LENSES
    return [
        {
            "id": lens,
            "status": "reviewed",
            "evidence_refs": [evidence_ref],
            "summary": f"{lens} 已基于目标证据完成审查。",
        }
        for lens in lenses
    ]


def receipt_for_target(
    target: dict[str, Any],
    *,
    root: Path,
    profile: str = "code-review",
    scope: dict[str, Any] | None = None,
    review_id: str | None = None,
    supersedes_review_id: str | None = None,
    policy: str = "conditional",
    delegated: bool = False,
) -> dict[str, Any]:
    if profile == "plan-review":
        scope = scope or {
            "kind": "managed-plan",
            "task_id": target["identity"]["task_id"],
            "plan_revision": target["identity"]["plan_revision"],
        }
        review_id = review_id or "REV-PLAN-001"
    else:
        scope = scope or {"kind": "standalone"}
        review_id = review_id or "REV-CODE-001"
    brief_relative = (
        f"artifacts/review-brief-{review_id}.json"
        if profile == "plan-review"
        else f"review-brief-{review_id}.json"
    )
    brief = {
        "profile": profile,
        "scope": scope,
        "summary": "验证当前目标满足单元测试审查要求。",
        "requirement_refs": ["GOAL-01"] if profile == "plan-review" else ["REQ-UNIT"],
        "constraint_refs": [],
        "claim_refs": [],
        "requested_risk_focus": [],
        "created_at": "2026-07-16T00:00:00+00:00",
    }
    write_json(root / brief_relative, brief)
    context_entries = [(brief_relative, "brief")]
    context_entries.extend(
        (item["path"], "requirement" if profile == "plan-review" else "adjacent-code")
        for item in target["manifest"]
        if item["state"] == "present" and item["path"] != brief_relative
    )
    context = build_context_target(
        root,
        root_kind="task-dir" if profile == "plan-review" else "workspace",
        label=f"{review_id.lower()}-context",
        entries=context_entries,
    )
    target_paths = [item["path"] for item in target["manifest"]]
    evidence_ref = brief_relative
    semantic = {
        "kind": "review-semantic-result",
        "review_id": review_id,
        "profile": profile,
        "scope": scope,
        "target_digest": target["digest"],
        "context_digest": context["digest"],
        "standards": [
            {
                "id": "STD-01",
                "title": "Repository rules",
                "source": "AGENTS.md",
                "applicability": "适用于当前目标。",
            }
        ],
        "coverage": {
            "target_paths": [
                {
                    "path": path,
                    "status": "reviewed",
                    "reason": "单元测试 fixture 已覆盖该路径。",
                    "gap_ids": [],
                }
                for path in target_paths
            ],
            "requirement_checks": [
                {
                    "id": "GOAL-01" if profile == "plan-review" else "REQ-UNIT",
                    "status": "satisfied",
                    "evidence_refs": [evidence_ref],
                    "finding_ids": [],
                    "gap_ids": [],
                    "summary": "fixture 提供了当前要求的直接证据。",
                }
            ],
            "risk_checks": [
                {
                    "id": risk_id,
                    "status": "not-triggered",
                    "trigger": "fixture 不包含该风险触发面。",
                    "evidence_refs": [evidence_ref],
                    "finding_ids": [],
                    "gap_ids": [],
                    "summary": "已检查触发条件，当前不适用。",
                }
                for risk_id in RISK_IDS
            ],
            "context_expansions": [],
        },
        "lenses": lens_records(profile, evidence_ref),
        "strengths": [],
        "findings": [],
        "verification_gaps": [],
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
        "supersedes_review_id": supersedes_review_id,
        "reviewed_at": "2026-07-16T00:00:02+00:00",
    }
    review_root = root / "reviews"
    target_path = review_root / "targets" / f"{review_id}.json"
    context_path = review_root / "contexts" / f"{review_id}.json"
    write_json(target_path, target)
    write_json(context_path, context)
    available_tools = (
        ["close_agent", "spawn_agent", "wait_agent"]
        if delegated
        else []
    )
    preparation = prepare_dispatch(
        review_id=review_id,
        target_path=target_path,
        context_path=context_path,
        review_root=review_root,
        policy=policy,
        capability_status="available" if delegated else "unavailable",
        tool_family="unit-test-host",
        available_tools=available_tools,
        workspace=root if profile == "code-review" else None,
        task_dir=root if profile == "plan-review" else None,
        prepared_at="2026-07-16T00:00:00+00:00",
    )
    preparation_path = review_root / "dispatches" / f"{review_id}-prepare.json"
    write_json(preparation_path, preparation)
    if delegated:
        outcome = {
            "status": "completed",
            "agent_id": "unit-agent-001",
            "fork_context": False,
            "started_at": "2026-07-16T00:00:01+00:00",
            "completed_at": "2026-07-16T00:00:02+00:00",
            "schema_repair_count": 0,
            "context_expansion_requested": False,
            "parent_judgment_included": False,
            "recursive_delegation_allowed": False,
            "failure": None,
            "close": {
                "required": True,
                "attempted": True,
                "status": "closed",
                "closed_at": "2026-07-16T00:00:03+00:00",
                "error": None,
            },
            "fallback": {"mode": "none", "reason_code": None, "reason": None},
        }
    else:
        outcome = {
            "status": "fallback",
            "agent_id": None,
            "fork_context": None,
            "started_at": None,
            "completed_at": "2026-07-16T00:00:02+00:00",
            "schema_repair_count": 0,
            "context_expansion_requested": False,
            "parent_judgment_included": False,
            "recursive_delegation_allowed": False,
            "failure": None,
            "close": {
                "required": False,
                "attempted": False,
                "status": "not-required",
                "closed_at": None,
                "error": None,
            },
            "fallback": {
                "mode": "same-context",
                "reason_code": "REVIEW_HOST_TOOLS_UNAVAILABLE",
                "reason": "单元测试宿主不提供 Agent 工具。",
            },
        }
    dispatch = finalize_dispatch(
        preparation,
        outcome,
        preparation_path=preparation_path,
        review_root=review_root,
        workspace=root if profile == "code-review" else None,
        task_dir=root if profile == "plan-review" else None,
        finalized_at="2026-07-16T00:00:04+00:00",
    )
    dispatch_path = review_root / "dispatches" / f"{review_id}.json"
    result_path = review_root / Path(*preparation["inputs"]["semantic_result_ref"].split("/"))
    write_json(dispatch_path, dispatch)
    write_json(result_path, semantic)
    return assemble_receipt(
        target_path=target_path,
        context_path=context_path,
        dispatch_path=dispatch_path,
        semantic_result_path=result_path,
        review_root=review_root,
        workspace=root if profile == "code-review" else None,
        task_dir=root if profile == "plan-review" else None,
    )


def sync_semantic_result(receipt: dict[str, Any], root: Path) -> None:
    """把测试对 receipt 语义层的修改同步到原始 result 与摘要。"""

    review_root = root / "reviews"
    result_path = resolve_review_ref(
        receipt["reviewer"]["semantic_result_ref"],
        review_root,
    )
    semantic = json.loads(result_path.read_text(encoding="utf-8"))
    for field in RECEIPT_SEMANTIC_FIELDS:
        semantic[field] = receipt[field]
    write_json(result_path, semantic)
    receipt["reviewer"]["semantic_result_digest"] = sha256_file(result_path)


def finding(
    *,
    finding_id: str = "FIND-001",
    severity: str = "major",
    status: str = "open",
    confidence: str = "high",
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "category": "correctness",
        "origin": {"review_id": None, "finding_id": None},
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
                "claim_source": "read",
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
    blocking_gap = any(
        item["severity"] in {"blocking", "major"}
        for item in receipt["verification_gaps"]
    )
    receipt["verdict"] = (
        "blocked"
        if blocked or blocking_gap
        else "changes_required"
        if unresolved
        else "passed"
    )

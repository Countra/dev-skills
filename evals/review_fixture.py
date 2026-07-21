"""跨 Planner、Reviewer 与 Executor eval 的确定性审查制品工厂。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEWER_SCRIPTS = REPO_ROOT / "skills" / "complex-coding-reviewer" / "scripts"
if str(REVIEWER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(REVIEWER_SCRIPTS))

from complex_coding_reviewer.assemble import assemble_receipt  # noqa: E402
from complex_coding_reviewer.dispatch import prepare_dispatch  # noqa: E402
from complex_coding_reviewer.dispatch_lifecycle import finalize_dispatch  # noqa: E402
from complex_coding_reviewer.io import resolve_review_ref, sha256_file  # noqa: E402
from complex_coding_reviewer.semantic_result import RECEIPT_SEMANTIC_FIELDS  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _completed_outcome(review_id: str) -> dict[str, Any]:
    return {
        "status": "completed",
        "agent_id": f"synthetic-eval-{review_id.lower()}",
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


def _fallback_outcome() -> dict[str, Any]:
    return {
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
            "reason_code": "REVIEW_DISPATCH_POLICY_DISABLED",
            "reason": "低/中风险确定性 eval 按编排策略使用 same-context，固定 agent_calls=0。",
        },
    }


def assemble_fixture_receipt(
    *,
    root: Path,
    review_root: Path,
    target: dict[str, Any],
    context: dict[str, Any],
    semantic: dict[str, Any],
    policy: str,
    delegated: bool,
) -> dict[str, Any]:
    """组装合成 receipt；调用方必须单独披露它不代表真实 Agent 观察。"""

    review_id = str(semantic["review_id"])
    target_path = review_root / "targets" / f"{review_id}.json"
    context_path = review_root / "contexts" / f"{review_id}.json"
    write_json(target_path, target)
    write_json(context_path, context)
    preparation = prepare_dispatch(
        review_id=review_id,
        target_path=target_path,
        context_path=context_path,
        review_root=review_root,
        policy=policy,
        capability_status="available" if delegated else "policy-disabled",
        tool_family="deterministic-eval-fixture",
        available_tools=(
            ["close_agent", "spawn_agent", "wait_agent"]
            if delegated
            else []
        ),
        workspace=root if semantic["profile"] == "code-review" else None,
        task_dir=root if semantic["profile"] == "plan-review" else None,
        prepared_at="2026-07-16T00:00:00+00:00",
    )
    preparation_path = review_root / "dispatches" / f"{review_id}-prepare.json"
    write_json(preparation_path, preparation)
    dispatch = finalize_dispatch(
        preparation,
        _completed_outcome(review_id) if delegated else _fallback_outcome(),
        preparation_path=preparation_path,
        review_root=review_root,
        workspace=root if semantic["profile"] == "code-review" else None,
        task_dir=root if semantic["profile"] == "plan-review" else None,
        finalized_at="2026-07-16T00:00:04+00:00",
    )
    dispatch_path = review_root / "dispatches" / f"{review_id}.json"
    result_path = review_root / Path(
        *preparation["inputs"]["semantic_result_ref"].split("/")
    )
    write_json(dispatch_path, dispatch)
    write_json(result_path, semantic)
    return assemble_receipt(
        target_path=target_path,
        context_path=context_path,
        dispatch_path=dispatch_path,
        semantic_result_path=result_path,
        review_root=review_root,
        workspace=root if semantic["profile"] == "code-review" else None,
        task_dir=root if semantic["profile"] == "plan-review" else None,
    )


def sync_fixture_semantic(
    receipt: dict[str, Any],
    review_root: Path,
) -> None:
    """同步 eval 对语义层的变更，并保持 supporting artifact 摘要闭环。"""

    result_path = resolve_review_ref(
        receipt["reviewer"]["semantic_result_ref"],
        review_root,
    )
    semantic = json.loads(result_path.read_text(encoding="utf-8"))
    for field in RECEIPT_SEMANTIC_FIELDS:
        semantic[field] = receipt[field]
    write_json(result_path, semantic)
    receipt["reviewer"]["semantic_result_digest"] = sha256_file(result_path)

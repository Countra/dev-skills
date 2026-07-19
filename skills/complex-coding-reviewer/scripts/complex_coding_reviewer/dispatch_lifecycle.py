"""校验 Agent 生命周期并生成 final dispatch。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dispatch import validate_preparation
from .dispatch_schema import (
    AGENT_ID,
    CLOSE_FIELDS,
    FAILURE_FIELDS,
    FALLBACK_FIELDS,
    FINAL_FIELDS,
    LIFECYCLE_STATUSES,
    MANDATORY_EXTERNAL_LIMITS,
    OUTCOME_FIELDS,
    POLICIES,
    REVIEWER_FIELDS,
    SCHEMA_REPAIR_TOOL,
    closed,
    digest,
    nonempty,
    nullable_string,
    timestamp,
)
from .errors import ReviewError
from .io import (
    load_json_object,
    resolve_review_artifact,
    resolve_review_ref,
    review_artifact_ref,
    sha256_file,
)


def _validate_failure(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    value = closed(raw, FAILURE_FIELDS, "$.outcome.failure")
    nonempty(value["code"], "$.outcome.failure.code")
    nonempty(value["reason"], "$.outcome.failure.reason")
    if not isinstance(value["retryable"], bool):
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "failure.retryable 必须是 boolean。")
    return value


def _validate_close(raw: Any) -> dict[str, Any]:
    value = closed(raw, CLOSE_FIELDS, "$.outcome.close")
    if not isinstance(value["required"], bool) or not isinstance(value["attempted"], bool):
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "close required/attempted 必须是 boolean。")
    if value["status"] not in {"closed", "failed", "not-required"}:
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "close status 无效。")
    timestamp(value["closed_at"], "$.outcome.close.closed_at", nullable=True)
    nullable_string(value["error"], "$.outcome.close.error")
    if value["status"] == "closed" and (
        not value["required"]
        or not value["attempted"]
        or value["closed_at"] is None
        or value["error"] is not None
    ):
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "closed 生命周期证据不自洽。")
    if value["status"] == "failed" and (
        not value["required"] or not value["attempted"] or value["error"] is None
    ):
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "close failed 必须记录错误。")
    if value["status"] == "not-required" and (
        value["required"]
        or value["attempted"]
        or value["closed_at"] is not None
        or value["error"] is not None
    ):
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "not-required close 证据不自洽。")
    return value


def _validate_fallback(raw: Any) -> dict[str, Any]:
    value = closed(raw, FALLBACK_FIELDS, "$.outcome.fallback")
    if value["mode"] not in {"none", "same-context", "blocked"}:
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "fallback mode 无效。")
    reason_code = nullable_string(value["reason_code"], "$.outcome.fallback.reason_code")
    reason = nullable_string(value["reason"], "$.outcome.fallback.reason")
    if value["mode"] == "none" and (reason_code is not None or reason is not None):
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "fallback=none 不得包含原因。")
    if value["mode"] != "none" and (reason_code is None or reason is None):
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "fallback 必须记录稳定原因。")
    return value


def _validate_outcome(raw: Any, preparation: dict[str, Any]) -> dict[str, Any]:
    outcome = closed(raw, OUTCOME_FIELDS, "$.outcome")
    status = outcome["status"]
    if status not in LIFECYCLE_STATUSES:
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "lifecycle status 无效。")
    agent_id = nullable_string(outcome["agent_id"], "$.outcome.agent_id")
    if agent_id is not None and AGENT_ID.fullmatch(agent_id) is None:
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "agent_id 必须是不含空白的 opaque id。")
    fork_context = outcome["fork_context"]
    if fork_context is not None and not isinstance(fork_context, bool):
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "fork_context 必须是 boolean 或 null。")
    timestamp(outcome["started_at"], "$.outcome.started_at", nullable=True)
    timestamp(outcome["completed_at"], "$.outcome.completed_at", nullable=True)
    repairs = outcome["schema_repair_count"]
    if not isinstance(repairs, int) or isinstance(repairs, bool) or repairs not in {0, 1}:
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "schema repair 最多允许一次。")
    if (
        repairs == 1
        and SCHEMA_REPAIR_TOOL not in preparation["capability"]["available_tools"]
    ):
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "schema repair 必须由 preparation 预先声明 send_input 能力。",
        )
    for field in (
        "context_expansion_requested",
        "parent_judgment_included",
        "recursive_delegation_allowed",
    ):
        if not isinstance(outcome[field], bool):
            raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", f"{field} 必须是 boolean。")
    failure = _validate_failure(outcome["failure"])
    close = _validate_close(outcome["close"])
    fallback = _validate_fallback(outcome["fallback"])
    started_at = outcome["started_at"]
    completed_at = outcome["completed_at"]
    prepared_at = timestamp(preparation["prepared_at"], "$.prepared_at")
    assert prepared_at is not None
    prepared = datetime.fromisoformat(prepared_at.replace("Z", "+00:00"))
    lifecycle_times = {
        "started_at": started_at,
        "completed_at": completed_at,
        "closed_at": close["closed_at"] if close["status"] == "closed" else None,
    }
    for field, raw_time in lifecycle_times.items():
        if raw_time is None:
            continue
        current = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        if current < prepared:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                f"{field} 不能早于 preparation.prepared_at。",
            )
    if started_at is not None and completed_at is not None:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        if completed < started:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "Agent completed_at 不能早于 started_at。",
            )
    if close["status"] == "closed" and completed_at is not None:
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        closed_time = datetime.fromisoformat(
            close["closed_at"].replace("Z", "+00:00")
        )
        if closed_time < completed:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "Agent closed_at 不能早于 completed_at。",
            )
    if outcome["parent_judgment_included"] or outcome["recursive_delegation_allowed"]:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "父代理判断注入或递归派发会破坏独立审查。",
        )
    decision = preparation["decision"]
    if status == "completed":
        if (
            decision != "delegate"
            or agent_id is None
            or fork_context is not False
            or outcome["started_at"] is None
            or outcome["completed_at"] is None
            or outcome["context_expansion_requested"]
            or failure is not None
            or close["status"] != "closed"
            or fallback["mode"] != "none"
        ):
            raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "completed 委派生命周期不完整。")
    elif status == "fallback":
        expected_reason_code = (
            "REVIEW_DISPATCH_POLICY_DISABLED"
            if preparation["policy"] == "disabled"
            or preparation["capability"]["status"] == "policy-disabled"
            else "REVIEW_HOST_TOOLS_UNAVAILABLE"
        )
        if (
            decision != "fallback"
            or agent_id is not None
            or fork_context is not None
            or outcome["started_at"] is not None
            or outcome["completed_at"] is None
            or repairs != 0
            or outcome["context_expansion_requested"]
            or failure is not None
            or close["status"] != "not-required"
            or fallback["mode"] != "same-context"
            or fallback["reason_code"] != expected_reason_code
        ):
            raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "same-context fallback 不合法。")
    elif status == "blocked":
        if (
            decision != "blocked"
            or agent_id is not None
            or fork_context is not None
            or outcome["started_at"] is not None
            or outcome["completed_at"] is None
            or repairs != 0
            or outcome["context_expansion_requested"]
            or failure is None
            or failure["code"] != "REVIEW_DISPATCH_REQUIRED_UNAVAILABLE"
            or failure["retryable"]
            or close["status"] != "not-required"
            or fallback["mode"] != "blocked"
        ):
            raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "strict blocked 证据不完整。")
    else:
        if (
            decision != "delegate"
            or failure is None
            or outcome["completed_at"] is None
            or fallback["mode"] != "none"
        ):
            raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "failed 委派必须保留失败证据。")
        if agent_id is None:
            if (
                fork_context is not None
                or outcome["started_at"] is not None
                or repairs != 0
                or outcome["context_expansion_requested"]
                or close["status"] != "not-required"
            ):
                raise ReviewError(
                    "REVIEW_DISPATCH_POLICY_VIOLATION",
                    "未创建 Agent 的失败生命周期不自洽。",
                )
        elif (
            fork_context is not False
            or outcome["started_at"] is None
            or close["status"] == "not-required"
        ):
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "已创建 Agent 的失败生命周期必须记录隔离、起止和关闭。",
            )
        final_attempt = preparation["attempt"] == preparation["max_attempts"]
        if final_attempt and failure["retryable"]:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "最后一次 Agent attempt 失败后必须标记为不可重试。",
            )
        if outcome["context_expansion_requested"]:
            if (
                failure["code"] != "REVIEW_CONTEXT_EXPANSION_REQUIRED"
                or failure["retryable"] is final_attempt
                or close["status"] != "closed"
            ):
                raise ReviewError(
                    "REVIEW_DISPATCH_POLICY_VIOLATION",
                    "context expansion 必须使用专用失败码、完成关闭，并按剩余 attempt 标记 retryable。",
                )
        elif failure["code"] == "REVIEW_CONTEXT_EXPANSION_REQUIRED":
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "context expansion 专用失败码必须同时记录 context_expansion_requested=true。",
            )
        if close["status"] == "failed" and (
            failure["code"] != "REVIEW_DISPATCH_AGENT_UNCLOSED"
            or failure["retryable"]
        ):
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "关闭失败必须使用 REVIEW_DISPATCH_AGENT_UNCLOSED 且不可重试。",
            )
        if failure["code"] == "REVIEW_DISPATCH_STALE" and failure["retryable"]:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "stale target/context 必须开始新审查，不能标记为可重试。",
            )
    return outcome


def _reviewer_for(outcome: dict[str, Any]) -> dict[str, Any]:
    agent_id = outcome["agent_id"]
    if outcome["status"] == "fallback":
        fallback = outcome["fallback"]
        limits = [
            *MANDATORY_EXTERNAL_LIMITS,
            f"同上下文回退（same-context-fallback:{fallback['reason_code']}）：{fallback['reason']}",
        ]
        return {
            "mode": "same-context",
            "identity": "review-coordinator:same-context",
            "independence_claim": False,
            "capability_limits": limits,
        }
    if agent_id is None:
        return {
            "mode": "same-context",
            "identity": f"review-coordinator:{outcome['status']}",
            "independence_claim": False,
            "capability_limits": [
                *MANDATORY_EXTERNAL_LIMITS,
                "本次 attempt 未创建 Reviewer 子 Agent，不能声明独立语义审查。",
            ],
        }
    return {
        "mode": "external-agent",
        "identity": f"codex-subagent:{agent_id}",
        "independence_claim": outcome["status"] == "completed",
        "capability_limits": list(MANDATORY_EXTERNAL_LIMITS),
    }


def finalize_dispatch(
    preparation: dict[str, Any],
    outcome: dict[str, Any],
    *,
    preparation_path: Path,
    review_root: Path,
    workspace: Path | None = None,
    task_dir: Path | None = None,
    finalized_at: str | None = None,
) -> dict[str, Any]:
    """把宿主记录的生命周期事实封装为不可变 final dispatch。"""

    validate_preparation(
        preparation,
        review_root=review_root,
        workspace=workspace,
        task_dir=task_dir,
        check_freshness=False,
    )
    resolved_preparation = resolve_review_artifact(preparation_path, review_root)
    checked_outcome = _validate_outcome(outcome, preparation)
    failure = checked_outcome["failure"]
    stale_failure = (
        checked_outcome["status"] == "failed"
        and isinstance(failure, dict)
        and failure["code"] == "REVIEW_DISPATCH_STALE"
    )
    if stale_failure:
        try:
            validate_preparation(
                preparation,
                review_root=review_root,
                workspace=workspace,
                task_dir=task_dir,
            )
        except ReviewError as exc:
            if exc.code != "REVIEW_DISPATCH_STALE":
                raise
        else:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "冻结输入仍 fresh，不能伪造 REVIEW_DISPATCH_STALE failure。",
            )
    else:
        validate_preparation(
            preparation,
            review_root=review_root,
            workspace=workspace,
            task_dir=task_dir,
        )
    finalized = finalized_at or datetime.now(timezone.utc).isoformat()
    value = {
        "kind": "review-dispatch",
        "dispatch_id": preparation["dispatch_id"],
        "review_id": preparation["review_id"],
        "profile": preparation["profile"],
        "scope": preparation["scope"],
        "policy": preparation["policy"],
        "capability": preparation["capability"],
        "inputs": preparation["inputs"],
        "preparation_ref": review_artifact_ref(resolved_preparation, review_root),
        "preparation_digest": sha256_file(resolved_preparation),
        "prompt_digest": preparation["prompt_digest"],
        "reviewer_skill_digest": preparation["reviewer_skill_digest"],
        "previous_dispatch_ref": preparation["previous_dispatch_ref"],
        "previous_dispatch_digest": preparation["previous_dispatch_digest"],
        "attempt": preparation["attempt"],
        "max_attempts": preparation["max_attempts"],
        "timeout_class": preparation["timeout_class"],
        "timeout_seconds": preparation["timeout_seconds"],
        "decision": preparation["decision"],
        "lifecycle": checked_outcome,
        "reviewer": _reviewer_for(checked_outcome),
        "prepared_at": preparation["prepared_at"],
        "finalized_at": finalized,
    }
    validate_dispatch(
        value,
        review_root=review_root,
        workspace=workspace,
        task_dir=task_dir,
        check_freshness=not stale_failure,
    )
    return value


def _validate_reviewer(raw: Any, lifecycle: dict[str, Any]) -> dict[str, Any]:
    reviewer = closed(raw, REVIEWER_FIELDS, "$.reviewer")
    expected = _reviewer_for(lifecycle)
    if reviewer != expected:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "reviewer provenance 不是由生命周期事实精确派生。",
        )
    return reviewer


def validate_dispatch(
    value: Any,
    *,
    review_root: Path,
    workspace: Path | None = None,
    task_dir: Path | None = None,
    expected_policy: str | None = None,
    require_receipt_ready: bool = False,
    check_freshness: bool = True,
) -> dict[str, Any]:
    """验证 final dispatch、输入 freshness 与 Agent 生命周期。"""

    dispatch = closed(value, FINAL_FIELDS, "$")
    if dispatch["kind"] != "review-dispatch":
        raise ReviewError("REVIEW_DISPATCH_POLICY_VIOLATION", "dispatch kind 无效。")
    preparation_path = resolve_review_ref(dispatch["preparation_ref"], review_root)
    if sha256_file(preparation_path) != digest(
        dispatch["preparation_digest"],
        "$.preparation_digest",
    ):
        raise ReviewError("REVIEW_DISPATCH_PROVENANCE_MISMATCH", "preparation digest 不匹配。")
    preparation = load_json_object(preparation_path)
    summary = validate_preparation(
        preparation,
        review_root=review_root,
        workspace=workspace,
        task_dir=task_dir,
        check_freshness=check_freshness,
    )
    copied = {
        "dispatch_id",
        "review_id",
        "profile",
        "scope",
        "policy",
        "capability",
        "inputs",
        "prompt_digest",
        "reviewer_skill_digest",
        "previous_dispatch_ref",
        "previous_dispatch_digest",
        "attempt",
        "max_attempts",
        "timeout_class",
        "timeout_seconds",
        "decision",
        "prepared_at",
    }
    mismatched = sorted(field for field in copied if dispatch[field] != preparation[field])
    if mismatched:
        raise ReviewError(
            "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            "final dispatch 与 preparation 不一致：" + ", ".join(mismatched),
        )
    finalized_at = timestamp(dispatch["finalized_at"], "$.finalized_at")
    assert finalized_at is not None
    prepared_at = timestamp(dispatch["prepared_at"], "$.prepared_at")
    assert prepared_at is not None
    finalized = datetime.fromisoformat(finalized_at.replace("Z", "+00:00"))
    prepared = datetime.fromisoformat(prepared_at.replace("Z", "+00:00"))
    if finalized < prepared:
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "finalized_at 不能早于 prepared_at。",
        )
    lifecycle = _validate_outcome(dispatch["lifecycle"], preparation)
    latest_lifecycle_time = (
        lifecycle["close"]["closed_at"]
        if lifecycle["close"]["status"] == "closed"
        else lifecycle["completed_at"]
    )
    if latest_lifecycle_time is not None:
        latest = datetime.fromisoformat(
            latest_lifecycle_time.replace("Z", "+00:00")
        )
        if finalized < latest:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                "finalized_at 不能早于已记录的 lifecycle 事件。",
            )
    reviewer = _validate_reviewer(dispatch["reviewer"], lifecycle)
    if dispatch["previous_dispatch_ref"] is not None:
        previous_path = resolve_review_ref(
            dispatch["previous_dispatch_ref"],
            review_root,
        )
        previous = load_json_object(previous_path)
        previous_agent_id = previous.get("lifecycle", {}).get("agent_id")
        current_agent_id = lifecycle["agent_id"]
        if (
            previous_agent_id is not None
            and current_agent_id is not None
            and previous_agent_id == current_agent_id
        ):
            raise ReviewError(
                "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
                "新的 Agent attempt 不能复用前序 attempt 的 Agent ID。",
            )
    policy = dispatch["policy"]
    if expected_policy is not None:
        if expected_policy not in POLICIES or policy != expected_policy:
            raise ReviewError(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                f"期望 dispatch policy={expected_policy}，实际为 {policy}。",
            )
    receipt_ready = lifecycle["status"] in {"completed", "fallback"}
    if require_receipt_ready and not receipt_ready:
        if lifecycle["status"] == "blocked":
            raise ReviewError(
                "REVIEW_DISPATCH_REQUIRED_UNAVAILABLE",
                "strict 审查需要独立子 Agent，但宿主能力不可用或被禁止。",
            )
        if lifecycle["close"]["status"] == "failed":
            raise ReviewError(
                "REVIEW_DISPATCH_AGENT_UNCLOSED",
                "Reviewer 子 Agent 未成功关闭，不能建立 passed gate。",
            )
        raise ReviewError(
            "REVIEW_DISPATCH_POLICY_VIOLATION",
            "失败的 Agent attempt 不能建立正式 receipt gate。",
        )
    return {
        **summary,
        "reviewer_mode": reviewer["mode"],
        "independence_claim": reviewer["independence_claim"],
        "lifecycle_status": lifecycle["status"],
        "receipt_ready": receipt_ready,
    }

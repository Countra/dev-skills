from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from helpers import (
    create_file_target,
    receipt_for_target,
    writable_tempdir,
    write_json,
)

from complex_coding_reviewer.assemble import assemble_receipt
from complex_coding_reviewer.contract import validate_receipt
from complex_coding_reviewer.context import build_context_target
from complex_coding_reviewer.dispatch import prepare_dispatch, validate_preparation
from complex_coding_reviewer.dispatch_lifecycle import finalize_dispatch, validate_dispatch
from complex_coding_reviewer.errors import ReviewError
from complex_coding_reviewer.io import resolve_review_ref, sha256_file
from complex_coding_reviewer.package import (
    MAX_DISPATCH_PACKAGE_BYTES,
    build_review_package,
)


def completed_outcome(*, repairs: int = 0) -> dict[str, object]:
    return {
        "status": "completed",
        "agent_id": "agent-opaque-001",
        "fork_context": False,
        "started_at": "2026-07-16T00:00:01+00:00",
        "completed_at": "2026-07-16T00:00:02+00:00",
        "schema_repair_count": repairs,
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


def fallback_outcome(*, policy_disabled: bool = False) -> dict[str, object]:
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
            "reason_code": (
                "REVIEW_DISPATCH_POLICY_DISABLED"
                if policy_disabled
                else "REVIEW_HOST_TOOLS_UNAVAILABLE"
            ),
            "reason": (
                "低风险编排策略选择 same-context。"
                if policy_disabled
                else "宿主未提供完整 Agent 工具族。"
            ),
        },
    }


def failed_outcome(
    *,
    code: str = "REVIEW_AGENT_TIMEOUT",
    close_status: str = "closed",
) -> dict[str, object]:
    close_error = "close_agent 返回失败" if close_status == "failed" else None
    return {
        "status": "failed",
        "agent_id": "agent-opaque-001",
        "fork_context": False,
        "started_at": "2026-07-16T00:00:01+00:00",
        "completed_at": "2026-07-16T00:00:02+00:00",
        "schema_repair_count": 0,
        "context_expansion_requested": False,
        "parent_judgment_included": False,
        "recursive_delegation_allowed": False,
        "failure": {
            "code": code,
            "reason": "宿主记录了终端失败。",
            "retryable": close_status == "closed",
        },
        "close": {
            "required": True,
            "attempted": True,
            "status": close_status,
            "closed_at": (
                "2026-07-16T00:00:03+00:00"
                if close_status == "closed"
                else None
            ),
            "error": close_error,
        },
        "fallback": {"mode": "none", "reason_code": None, "reason": None},
    }


def pre_spawn_failed_outcome() -> dict[str, object]:
    return {
        "status": "failed",
        "agent_id": None,
        "fork_context": None,
        "started_at": None,
        "completed_at": "2026-07-16T00:00:02+00:00",
        "schema_repair_count": 0,
        "context_expansion_requested": False,
        "parent_judgment_included": False,
        "recursive_delegation_allowed": False,
        "failure": {
            "code": "REVIEW_AGENT_SPAWN_FAILED",
            "reason": "宿主未能创建 Agent。",
            "retryable": True,
        },
        "close": {
            "required": False,
            "attempted": False,
            "status": "not-required",
            "closed_at": None,
            "error": None,
        },
        "fallback": {"mode": "none", "reason_code": None, "reason": None},
    }


def blocked_outcome() -> dict[str, object]:
    return {
        "status": "blocked",
        "agent_id": None,
        "fork_context": None,
        "started_at": None,
        "completed_at": "2026-07-16T00:00:02+00:00",
        "schema_repair_count": 0,
        "context_expansion_requested": False,
        "parent_judgment_included": False,
        "recursive_delegation_allowed": False,
        "failure": {
            "code": "REVIEW_DISPATCH_REQUIRED_UNAVAILABLE",
            "reason": "strict 审查缺少 Agent 工具。",
            "retryable": False,
        },
        "close": {
            "required": False,
            "attempted": False,
            "status": "not-required",
            "closed_at": None,
            "error": None,
        },
        "fallback": {
            "mode": "blocked",
            "reason_code": "REVIEW_DISPATCH_REQUIRED_UNAVAILABLE",
            "reason": "strict 审查不能降级。",
        },
    }


class DispatchContractTests(unittest.TestCase):
    def _artifacts(
        self,
        root: Path,
        *,
        delegated: bool = False,
    ) -> tuple[dict[str, object], Path, Path, Path, Path]:
        receipt = receipt_for_target(
            create_file_target(root),
            root=root,
            delegated=delegated,
        )
        review_root = root / "reviews"
        dispatch_path = resolve_review_ref(receipt["reviewer"]["dispatch_ref"], review_root)
        dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
        target_path = resolve_review_ref(dispatch["inputs"]["target_ref"], review_root)
        context_path = resolve_review_ref(dispatch["inputs"]["context_ref"], review_root)
        preparation_path = resolve_review_ref(dispatch["preparation_ref"], review_root)
        return receipt, review_root, target_path, context_path, preparation_path

    def test_completed_external_agent_establishes_independence(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(
                create_file_target(root),
                root=root,
                delegated=True,
            )
            result = validate_receipt(
                receipt,
                review_root=root / "reviews",
                workspace=root,
                expected_dispatch_policy="conditional",
            )
            self.assertEqual("external-agent", result["reviewer_mode"])
            self.assertTrue(result["independence_claim"])
            self.assertTrue(receipt["reviewer"]["identity"].startswith("codex-subagent:"))

    def test_expected_strict_policy_rejects_conditional_dispatch(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(
                create_file_target(root),
                root=root,
                delegated=True,
            )
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_POLICY_VIOLATION",
            ):
                validate_receipt(
                    receipt,
                    review_root=root / "reviews",
                    workspace=root,
                    expected_dispatch_policy="strict",
                )

    def test_strict_unavailable_is_blocked(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            preparation = prepare_dispatch(
                review_id="REV-STRICT-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="strict",
                capability_status="unavailable",
                tool_family="unit-test-host",
                available_tools=[],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            preparation_path = review_root / "dispatches" / "strict-prepare.json"
            write_json(preparation_path, preparation)
            dispatch = finalize_dispatch(
                preparation,
                blocked_outcome(),
                preparation_path=preparation_path,
                review_root=review_root,
                workspace=root,
                finalized_at="2026-07-16T00:00:04+00:00",
            )
            self.assertEqual("same-context", dispatch["reviewer"]["mode"])
            self.assertEqual(
                "review-coordinator:blocked",
                dispatch["reviewer"]["identity"],
            )
            self.assertFalse(dispatch["reviewer"]["independence_claim"])
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_REQUIRED_UNAVAILABLE",
            ):
                validate_dispatch(
                    dispatch,
                    review_root=review_root,
                    workspace=root,
                    expected_policy="strict",
                    require_receipt_ready=True,
                )

    def test_conditional_policy_disabled_uses_same_context_without_discovery(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            preparation = prepare_dispatch(
                review_id="REV-POLICY-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="policy-disabled",
                tool_family="risk-policy",
                available_tools=[],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            self.assertEqual("fallback", preparation["decision"])
            self.assertEqual("policy-disabled", preparation["capability"]["status"])
            preparation_path = review_root / "dispatches" / "policy-prepare.json"
            write_json(preparation_path, preparation)
            dispatch = finalize_dispatch(
                preparation,
                fallback_outcome(policy_disabled=True),
                preparation_path=preparation_path,
                review_root=review_root,
                workspace=root,
                finalized_at="2026-07-16T00:00:04+00:00",
            )
            self.assertEqual("same-context", dispatch["reviewer"]["mode"])
            self.assertFalse(dispatch["reviewer"]["independence_claim"])

    def test_policy_disabled_obeys_calling_policy(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            tools = ["close_agent", "spawn_agent", "wait_agent"]
            cases = (
                ("strict", "blocked", blocked_outcome()),
                ("conditional", "fallback", fallback_outcome()),
            )
            for policy, decision, outcome in cases:
                with self.subTest(policy=policy):
                    if policy == "conditional":
                        outcome["fallback"]["reason_code"] = (
                            "REVIEW_DISPATCH_POLICY_DISABLED"
                        )
                        outcome["fallback"]["reason"] = "宿主策略禁止委派。"
                    preparation = prepare_dispatch(
                        review_id=f"REV-POLICY-{policy.upper()}",
                        target_path=target_path,
                        context_path=context_path,
                        review_root=review_root,
                        policy=policy,
                        capability_status="policy-disabled",
                        tool_family="unit-test-host",
                        available_tools=tools,
                        workspace=root,
                        prepared_at="2026-07-16T00:00:00+00:00",
                    )
                    self.assertEqual(decision, preparation["decision"])
                    path = review_root / "dispatches" / f"{policy}-prepare.json"
                    write_json(path, preparation)
                    dispatch = finalize_dispatch(
                        preparation,
                        outcome,
                        preparation_path=path,
                        review_root=review_root,
                        workspace=root,
                    )
                    self.assertFalse(dispatch["reviewer"]["independence_claim"])

    def test_conditional_available_cannot_fallback(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            preparation = prepare_dispatch(
                review_id="REV-DELEGATE-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            path = review_root / "dispatches" / "delegate-prepare.json"
            write_json(path, preparation)
            with self.assertRaisesRegex(ReviewError, "REVIEW_DISPATCH_POLICY_VIOLATION"):
                finalize_dispatch(
                    preparation,
                    fallback_outcome(),
                    preparation_path=path,
                    review_root=review_root,
                    workspace=root,
                )

    def test_completed_rejects_fork_parent_judgment_and_recursion(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt, review_root, _, _, _ = self._artifacts(root, delegated=True)
            dispatch_path = resolve_review_ref(receipt["reviewer"]["dispatch_ref"], review_root)
            original = json.loads(dispatch_path.read_text(encoding="utf-8"))
            mutations = (
                ("fork_context", True),
                ("context_expansion_requested", True),
                ("parent_judgment_included", True),
                ("recursive_delegation_allowed", True),
            )
            for field, value in mutations:
                with self.subTest(field=field):
                    dispatch = deepcopy(original)
                    dispatch["lifecycle"][field] = value
                    with self.assertRaises(ReviewError):
                        validate_dispatch(
                            dispatch,
                            review_root=review_root,
                            workspace=root,
                        )

    def test_schema_repair_once_is_allowed_but_twice_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            preparation = prepare_dispatch(
                review_id="REV-REPAIR-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=[
                    "close_agent",
                    "send_input",
                    "spawn_agent",
                    "wait_agent",
                ],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            path = review_root / "dispatches" / "repair-prepare.json"
            write_json(path, preparation)
            dispatch = finalize_dispatch(
                preparation,
                completed_outcome(repairs=1),
                preparation_path=path,
                review_root=review_root,
                workspace=root,
            )
            self.assertTrue(
                validate_dispatch(
                    dispatch,
                    review_root=review_root,
                    workspace=root,
                )["receipt_ready"]
            )
            invalid = completed_outcome(repairs=1)
            invalid["schema_repair_count"] = 2
            with self.assertRaisesRegex(ReviewError, "REVIEW_DISPATCH_POLICY_VIOLATION"):
                finalize_dispatch(
                    preparation,
                    invalid,
                    preparation_path=path,
                    review_root=review_root,
                    workspace=root,
                )

    def test_schema_repair_requires_frozen_send_input_capability(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            preparation = prepare_dispatch(
                review_id="REV-REPAIR-CAPABILITY-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            path = review_root / "dispatches" / "repair-capability-prepare.json"
            write_json(path, preparation)
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            ):
                finalize_dispatch(
                    preparation,
                    completed_outcome(repairs=1),
                    preparation_path=path,
                    review_root=review_root,
                    workspace=root,
                )

    def test_completed_lifecycle_rejects_reversed_timestamps(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            preparation = prepare_dispatch(
                review_id="REV-TIME-ORDER-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
            )
            path = review_root / "dispatches" / "time-order-prepare.json"
            write_json(path, preparation)
            outcome = completed_outcome()
            outcome["completed_at"] = "2026-07-16T00:00:04+00:00"
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_POLICY_VIOLATION",
            ):
                finalize_dispatch(
                    preparation,
                    outcome,
                    preparation_path=path,
                    review_root=review_root,
                    workspace=root,
                )

    def test_semantic_result_time_is_bound_to_agent_lifecycle(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(
                create_file_target(root),
                root=root,
                delegated=True,
            )
            review_root = root / "reviews"
            dispatch_path = resolve_review_ref(
                receipt["reviewer"]["dispatch_ref"],
                review_root,
            )
            dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
            target_path = resolve_review_ref(
                dispatch["inputs"]["target_ref"],
                review_root,
            )
            context_path = resolve_review_ref(
                dispatch["inputs"]["context_ref"],
                review_root,
            )
            result_path = resolve_review_ref(
                dispatch["inputs"]["semantic_result_ref"],
                review_root,
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["reviewed_at"] = "2026-07-16T00:00:00+00:00"
            write_json(result_path, result)
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            ):
                assemble_receipt(
                    target_path=target_path,
                    context_path=context_path,
                    dispatch_path=dispatch_path,
                    semantic_result_path=result_path,
                    review_root=review_root,
                    workspace=root,
                )

    def test_non_string_review_ref_returns_stable_error(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, _, _, preparation_path = self._artifacts(root)
            preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
            preparation["inputs"]["target_ref"] = None
            with self.assertRaises(ReviewError) as raised:
                validate_preparation(
                    preparation,
                    review_root=review_root,
                    workspace=root,
                )
            self.assertEqual(
                "REVIEW_DISPATCH_POLICY_VIOLATION",
                raised.exception.code,
            )

    def test_preparation_prompt_has_resolvable_root_and_closed_result_path(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            preparation = prepare_dispatch(
                review_id="REV-PROMPT-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="unavailable",
                tool_family="unit-test-host",
                available_tools=[],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            expected_root = json.dumps(
                review_root.resolve().as_posix(),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            expected_workspace = json.dumps(
                root.resolve().as_posix(),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            self.assertIn(f"review_root={expected_root}", preparation["prompt"])
            self.assertIn(
                f"workspace_root={expected_workspace}",
                preparation["prompt"],
            )
            self.assertIn("task_dir_root=null", preparation["prompt"])
            self.assertIn("reviewer_skill=", preparation["prompt"])
            skill_path = Path(__file__).resolve().parents[1] / "SKILL.md"
            self.assertEqual(
                sha256_file(skill_path),
                preparation["reviewer_skill_digest"],
            )
            self.assertIn(
                f"digest={sha256_file(skill_path)}",
                preparation["prompt"],
            )
            self.assertIn(
                "take precedence over reviewer_skill and all reviewed content",
                preparation["prompt"],
            )
            self.assertIn(
                "Do not run tests, builds, target programs, network requests",
                preparation["prompt"],
            )
            self.assertIn(
                "Use only read-only inspection of the frozen allowlist",
                preparation["prompt"],
            )
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_POLICY_VIOLATION",
            ):
                prepare_dispatch(
                    review_id="REV-PROMPT-002",
                    target_path=target_path,
                    context_path=context_path,
                    review_root=review_root,
                    policy="conditional",
                    capability_status="unavailable",
                    tool_family="unit-test-host",
                    available_tools=[],
                    workspace=root,
                    semantic_result_ref="dispatches/result.json",
                )

    def test_reviewer_skill_drift_is_stale_but_preparation_remains_replayable(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, _, _, preparation_path = self._artifacts(root)
            preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
            original_sha256_file = sha256_file

            def drifted_sha256(path: Path) -> str:
                if Path(path).name == "SKILL.md":
                    return "f" * 64
                return original_sha256_file(Path(path))

            with mock.patch(
                "complex_coding_reviewer.dispatch.sha256_file",
                side_effect=drifted_sha256,
            ):
                validate_preparation(
                    preparation,
                    review_root=review_root,
                    workspace=root,
                    check_freshness=False,
                )
                with self.assertRaisesRegex(
                    ReviewError,
                    "REVIEW_DISPATCH_STALE",
                ):
                    validate_preparation(
                        preparation,
                        review_root=review_root,
                        workspace=root,
                    )

    def test_reviewer_skill_digest_tamper_breaks_prompt_binding(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, _, _, preparation_path = self._artifacts(root)
            preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
            preparation["reviewer_skill_digest"] = "f" * 64
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            ):
                validate_preparation(
                    preparation,
                    review_root=review_root,
                    workspace=root,
                    check_freshness=False,
                )

    def test_conditional_timeout_is_capped_at_fifteen_minutes(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_POLICY_VIOLATION",
            ):
                prepare_dispatch(
                    review_id="REV-TIMEOUT-001",
                    target_path=target_path,
                    context_path=context_path,
                    review_root=review_root,
                    policy="conditional",
                    capability_status="available",
                    tool_family="unit-test-host",
                    available_tools=["close_agent", "spawn_agent", "wait_agent"],
                    workspace=root,
                    timeout_seconds=901,
                )

            default = prepare_dispatch(
                review_id="REV-TIMEOUT-DEFAULT-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="policy-disabled",
                tool_family="risk-policy",
                available_tools=[],
                workspace=root,
            )
            self.assertEqual(300, default["timeout_seconds"])

    def test_risk_focused_conditional_uses_high_risk_timeout_class(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            context = json.loads(context_path.read_text(encoding="utf-8"))
            brief_entry = next(
                item for item in context["manifest"] if item["role"] == "brief"
            )
            brief_path = root / brief_entry["path"]
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            brief["requested_risk_focus"] = ["security-privacy"]
            write_json(brief_path, brief)
            high_risk_context = build_context_target(
                root,
                root_kind="workspace",
                label="risk-focused-timeout",
                entries=[
                    (item["path"], item["role"])
                    for item in context["manifest"]
                    if item["state"] == "present"
                ],
            )
            high_risk_context_path = review_root / "contexts" / "risk-focused.json"
            write_json(high_risk_context_path, high_risk_context)

            preparation = prepare_dispatch(
                review_id="REV-TIMEOUT-002",
                target_path=target_path,
                context_path=high_risk_context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
            )
            self.assertEqual("high-risk", preparation["timeout_class"])
            self.assertEqual(900, preparation["timeout_seconds"])

            legacy_budget = prepare_dispatch(
                review_id="REV-TIMEOUT-LEGACY-001",
                target_path=target_path,
                context_path=high_risk_context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                timeout_seconds=1800,
            )
            validate_preparation(
                legacy_budget,
                review_root=review_root,
                workspace=root,
            )

            extended = prepare_dispatch(
                review_id="REV-TIMEOUT-003",
                target_path=target_path,
                context_path=high_risk_context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                timeout_seconds=2400,
            )
            self.assertEqual(2400, extended["timeout_seconds"])
            validate_preparation(
                extended,
                review_root=review_root,
                workspace=root,
            )

            tampered = deepcopy(preparation)
            tampered["timeout_class"] = "standard"
            tampered["timeout_seconds"] = 900
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            ):
                validate_preparation(
                    tampered,
                    review_root=review_root,
                    workspace=root,
                )

    def test_dispatch_rejects_oversized_or_spoofed_package_budget(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            target = json.loads(target_path.read_text(encoding="utf-8"))
            context = json.loads(context_path.read_text(encoding="utf-8"))
            base = {
                "target_digest": target["digest"],
                "context_digest": context["digest"],
                "truncated": False,
            }
            cases = {
                "declared": {
                    **base,
                    "byte_count": MAX_DISPATCH_PACKAGE_BYTES + 1,
                },
                "artifact": {
                    **base,
                    "byte_count": 1,
                    "padding": "x" * MAX_DISPATCH_PACKAGE_BYTES,
                },
            }
            for name, package in cases.items():
                with self.subTest(name=name):
                    package_path = review_root / f"{name}-package.json"
                    write_json(package_path, package)
                    with self.assertRaisesRegex(
                        ReviewError,
                        "REVIEW_PACKAGE_LIMIT_EXCEEDED",
                    ):
                        prepare_dispatch(
                            review_id=f"REV-PACKAGE-{name.upper()}",
                            target_path=target_path,
                            context_path=context_path,
                            package_path=package_path,
                            review_root=review_root,
                            policy="conditional",
                            capability_status="available",
                            tool_family="unit-test-host",
                            available_tools=[
                                "close_agent",
                                "spawn_agent",
                                "wait_agent",
                            ],
                            workspace=root,
                        )

    def test_dispatch_rejects_forged_or_replayed_invalid_package(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt, review_root, target_path, context_path, _ = self._artifacts(root)
            package = build_review_package(
                receipt["target"],
                receipt["context"],
                workspace=root,
                generated_at="2026-07-16T00:00:00+00:00",
            )
            package_path = review_root / "packages" / "valid.json"
            write_json(package_path, package)
            preparation = prepare_dispatch(
                review_id="REV-PACKAGE-CLOSED-001",
                target_path=target_path,
                context_path=context_path,
                package_path=package_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                prepared_at="2026-07-16T00:00:01+00:00",
            )
            self.assertEqual("packages/valid.json", preparation["inputs"]["package_ref"])

            forged = deepcopy(package)
            text_entry = next(
                item
                for item in forged["entries"]
                if isinstance(item["content"], str) and "answer = 42" in item["content"]
            )
            text_entry["content"] = text_entry["content"].replace(
                "answer = 42",
                "answer = 41",
            )
            forged_path = review_root / "packages" / "forged.json"
            write_json(forged_path, forged)
            with self.assertRaisesRegex(ReviewError, "REVIEW_PACKAGE_INVALID"):
                prepare_dispatch(
                    review_id="REV-PACKAGE-CLOSED-002",
                    target_path=target_path,
                    context_path=context_path,
                    package_path=forged_path,
                    review_root=review_root,
                    policy="conditional",
                    capability_status="available",
                    tool_family="unit-test-host",
                    available_tools=["close_agent", "spawn_agent", "wait_agent"],
                    workspace=root,
                )

            package["truncated"] = True
            write_json(package_path, package)
            preparation["inputs"]["package_digest"] = sha256_file(package_path)
            with self.assertRaisesRegex(ReviewError, "REVIEW_PACKAGE_INVALID"):
                validate_preparation(
                    preparation,
                    review_root=review_root,
                    workspace=root,
                )

    def test_close_failure_can_only_form_non_gating_candidate(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt, review_root, target_path, context_path, preparation_path = self._artifacts(
                root,
                delegated=True,
            )
            preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
            dispatch = finalize_dispatch(
                preparation,
                failed_outcome(
                    code="REVIEW_DISPATCH_AGENT_UNCLOSED",
                    close_status="failed",
                ),
                preparation_path=preparation_path,
                review_root=review_root,
                workspace=root,
            )
            dispatch_path = review_root / "dispatches" / "unclosed-candidate.json"
            write_json(dispatch_path, dispatch)
            result_path = resolve_review_ref(
                receipt["reviewer"]["semantic_result_ref"],
                review_root,
            )
            candidate = assemble_receipt(
                target_path=target_path,
                context_path=context_path,
                dispatch_path=dispatch_path,
                semantic_result_path=result_path,
                review_root=review_root,
                workspace=root,
            )
            with self.assertRaisesRegex(ReviewError, "REVIEW_DISPATCH_AGENT_UNCLOSED"):
                validate_receipt(
                    candidate,
                    review_root=review_root,
                    workspace=root,
                )

    def test_stale_attempt_preserves_closed_non_gating_dispatch(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, _, _, preparation_path = self._artifacts(
                root,
                delegated=True,
            )
            preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
            (root / "src" / "example.py").write_text("answer = 43\n", encoding="utf-8")
            outcome = failed_outcome(code="REVIEW_DISPATCH_STALE")
            outcome["failure"]["retryable"] = False
            dispatch = finalize_dispatch(
                preparation,
                outcome,
                preparation_path=preparation_path,
                review_root=review_root,
                workspace=root,
            )
            self.assertFalse(
                validate_dispatch(
                    dispatch,
                    review_root=review_root,
                    workspace=root,
                    check_freshness=False,
                )["receipt_ready"]
            )
            with self.assertRaisesRegex(ReviewError, "REVIEW_DISPATCH_STALE"):
                validate_dispatch(
                    dispatch,
                    review_root=review_root,
                    workspace=root,
                )

    def test_reviewer_skill_drift_preserves_closed_non_gating_dispatch(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, _, _, preparation_path = self._artifacts(
                root,
                delegated=True,
            )
            preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
            outcome = failed_outcome(code="REVIEW_DISPATCH_STALE")
            outcome["failure"]["retryable"] = False
            original_sha256_file = sha256_file

            def drifted_sha256(path: Path) -> str:
                if Path(path).name == "SKILL.md":
                    return "f" * 64
                return original_sha256_file(Path(path))

            with mock.patch(
                "complex_coding_reviewer.dispatch.sha256_file",
                side_effect=drifted_sha256,
            ):
                dispatch = finalize_dispatch(
                    preparation,
                    outcome,
                    preparation_path=preparation_path,
                    review_root=review_root,
                    workspace=root,
                )
                self.assertFalse(
                    validate_dispatch(
                        dispatch,
                        review_root=review_root,
                        workspace=root,
                        check_freshness=False,
                    )["receipt_ready"]
                )
                with self.assertRaisesRegex(
                    ReviewError,
                    "REVIEW_DISPATCH_STALE",
                ):
                    validate_dispatch(
                        dispatch,
                        review_root=review_root,
                        workspace=root,
                    )

    def test_retry_attempt_binds_failed_predecessor(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            first = prepare_dispatch(
                review_id="REV-RETRY-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            first_preparation_path = review_root / "dispatches" / "retry-1-prepare.json"
            write_json(first_preparation_path, first)
            first_dispatch = finalize_dispatch(
                first,
                failed_outcome(),
                preparation_path=first_preparation_path,
                review_root=review_root,
                workspace=root,
                finalized_at="2026-07-16T00:00:04+00:00",
            )
            first_dispatch_path = review_root / "dispatches" / "retry-1.json"
            write_json(first_dispatch_path, first_dispatch)
            second = prepare_dispatch(
                review_id="REV-RETRY-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                attempt=2,
                previous_dispatch_path=first_dispatch_path,
                prepared_at="2026-07-16T00:01:00+00:00",
            )
            self.assertEqual("dispatches/retry-1.json", second["previous_dispatch_ref"])
            validate_preparation(second, review_root=review_root, workspace=root)
            first_dispatch["lifecycle"]["failure"]["reason"] = "tampered"
            write_json(first_dispatch_path, first_dispatch)
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            ):
                validate_preparation(second, review_root=review_root, workspace=root)

    def test_retry_cannot_downgrade_delegated_failure_to_fallback(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            first = prepare_dispatch(
                review_id="REV-RETRY-NO-FALLBACK-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            first_preparation_path = (
                review_root / "dispatches" / "no-fallback-1-prepare.json"
            )
            write_json(first_preparation_path, first)
            first_dispatch = finalize_dispatch(
                first,
                failed_outcome(),
                preparation_path=first_preparation_path,
                review_root=review_root,
                workspace=root,
                finalized_at="2026-07-16T00:00:04+00:00",
            )
            first_dispatch_path = review_root / "dispatches" / "no-fallback-1.json"
            write_json(first_dispatch_path, first_dispatch)
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_POLICY_VIOLATION",
            ):
                prepare_dispatch(
                    review_id="REV-RETRY-NO-FALLBACK-001",
                    target_path=target_path,
                    context_path=context_path,
                    review_root=review_root,
                    policy="conditional",
                    capability_status="unavailable",
                    tool_family="unit-test-host",
                    available_tools=[],
                    workspace=root,
                    attempt=2,
                    previous_dispatch_path=first_dispatch_path,
                    prepared_at="2026-07-16T00:00:05+00:00",
                )

    def test_retry_rejects_non_retryable_predecessor(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            first = prepare_dispatch(
                review_id="REV-NO-RETRY-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            preparation_path = review_root / "dispatches" / "no-retry-prepare.json"
            write_json(preparation_path, first)
            outcome = failed_outcome()
            outcome["failure"]["retryable"] = False
            dispatch = finalize_dispatch(
                first,
                outcome,
                preparation_path=preparation_path,
                review_root=review_root,
                workspace=root,
            )
            dispatch_path = review_root / "dispatches" / "no-retry.json"
            write_json(dispatch_path, dispatch)
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_POLICY_VIOLATION",
            ):
                prepare_dispatch(
                    review_id="REV-NO-RETRY-001",
                    target_path=target_path,
                    context_path=context_path,
                    review_root=review_root,
                    policy="conditional",
                    capability_status="available",
                    tool_family="unit-test-host",
                    available_tools=["close_agent", "spawn_agent", "wait_agent"],
                    workspace=root,
                    attempt=2,
                    previous_dispatch_path=dispatch_path,
                )

    def test_retry_allows_pre_spawn_failure_without_close(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            first = prepare_dispatch(
                review_id="REV-SPAWN-RETRY-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            preparation_path = review_root / "dispatches" / "spawn-retry-prepare.json"
            write_json(preparation_path, first)
            dispatch = finalize_dispatch(
                first,
                pre_spawn_failed_outcome(),
                preparation_path=preparation_path,
                review_root=review_root,
                workspace=root,
                finalized_at="2026-07-16T00:00:03+00:00",
            )
            dispatch_path = review_root / "dispatches" / "spawn-retry.json"
            write_json(dispatch_path, dispatch)
            second = prepare_dispatch(
                review_id="REV-SPAWN-RETRY-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                attempt=2,
                previous_dispatch_path=dispatch_path,
                prepared_at="2026-07-16T00:00:04+00:00",
            )
            self.assertEqual(2, second["attempt"])

    def test_final_attempt_failure_cannot_claim_retryable(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            first = prepare_dispatch(
                review_id="REV-FINAL-FAILURE-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            first_preparation_path = (
                review_root / "dispatches" / "final-failure-1-prepare.json"
            )
            write_json(first_preparation_path, first)
            first_dispatch = finalize_dispatch(
                first,
                failed_outcome(),
                preparation_path=first_preparation_path,
                review_root=review_root,
                workspace=root,
                finalized_at="2026-07-16T00:00:03+00:00",
            )
            first_dispatch_path = review_root / "dispatches" / "final-failure-1.json"
            write_json(first_dispatch_path, first_dispatch)
            second = prepare_dispatch(
                review_id="REV-FINAL-FAILURE-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                attempt=2,
                previous_dispatch_path=first_dispatch_path,
                prepared_at="2026-07-16T00:00:04+00:00",
            )
            second_preparation_path = (
                review_root / "dispatches" / "final-failure-2-prepare.json"
            )
            write_json(second_preparation_path, second)
            retryable_outcome = failed_outcome()
            retryable_outcome["started_at"] = "2026-07-16T00:00:05+00:00"
            retryable_outcome["completed_at"] = "2026-07-16T00:00:06+00:00"
            retryable_outcome["close"]["closed_at"] = "2026-07-16T00:00:07+00:00"
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_POLICY_VIOLATION",
            ):
                finalize_dispatch(
                    second,
                    retryable_outcome,
                    preparation_path=second_preparation_path,
                    review_root=review_root,
                    workspace=root,
                )
            terminal_outcome = deepcopy(retryable_outcome)
            terminal_outcome["failure"]["retryable"] = False
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            ):
                finalize_dispatch(
                    second,
                    terminal_outcome,
                    preparation_path=second_preparation_path,
                    review_root=review_root,
                    workspace=root,
                )
            terminal_outcome["agent_id"] = "agent-opaque-002"
            terminal = finalize_dispatch(
                second,
                terminal_outcome,
                preparation_path=second_preparation_path,
                review_root=review_root,
                workspace=root,
            )
            self.assertFalse(terminal["lifecycle"]["failure"]["retryable"])

    def test_context_expansion_requires_a_superset_context(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            _, review_root, target_path, context_path, _ = self._artifacts(root)
            first = prepare_dispatch(
                review_id="REV-EXPAND-001",
                target_path=target_path,
                context_path=context_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                prepared_at="2026-07-16T00:00:00+00:00",
            )
            preparation_path = review_root / "dispatches" / "expand-prepare.json"
            write_json(preparation_path, first)
            outcome = failed_outcome(code="REVIEW_CONTEXT_EXPANSION_REQUIRED")
            outcome["context_expansion_requested"] = True
            dispatch = finalize_dispatch(
                first,
                outcome,
                preparation_path=preparation_path,
                review_root=review_root,
                workspace=root,
            )
            dispatch_path = review_root / "dispatches" / "expand.json"
            write_json(dispatch_path, dispatch)
            with self.assertRaisesRegex(ReviewError, "REVIEW_DISPATCH_STALE"):
                prepare_dispatch(
                    review_id="REV-EXPAND-001",
                    target_path=target_path,
                    context_path=context_path,
                    review_root=review_root,
                    policy="conditional",
                    capability_status="available",
                    tool_family="unit-test-host",
                    available_tools=["close_agent", "spawn_agent", "wait_agent"],
                    workspace=root,
                    attempt=2,
                    previous_dispatch_path=dispatch_path,
                )
            previous_context = json.loads(context_path.read_text(encoding="utf-8"))
            (root / "docs").mkdir()
            (root / "docs" / "extra.md").write_text("extra context\n", encoding="utf-8")
            entries = [
                (item["path"], item["role"])
                for item in previous_context["manifest"]
            ]
            entries.append(("docs/extra.md", "other"))
            expanded = build_context_target(
                root,
                root_kind="workspace",
                label="expanded-context",
                entries=entries,
            )
            expanded_path = review_root / "contexts" / "REV-EXPAND-001-A2.json"
            write_json(expanded_path, expanded)
            second = prepare_dispatch(
                review_id="REV-EXPAND-001",
                target_path=target_path,
                context_path=expanded_path,
                review_root=review_root,
                policy="conditional",
                capability_status="available",
                tool_family="unit-test-host",
                available_tools=["close_agent", "spawn_agent", "wait_agent"],
                workspace=root,
                attempt=2,
                previous_dispatch_path=dispatch_path,
            )
            self.assertEqual(expanded["digest"], second["inputs"]["context_digest"])

    def test_supporting_result_tamper_is_rejected(self) -> None:
        with writable_tempdir() as temp:
            root = Path(temp)
            receipt = receipt_for_target(create_file_target(root), root=root)
            review_root = root / "reviews"
            result_path = resolve_review_ref(
                receipt["reviewer"]["semantic_result_ref"],
                review_root,
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["summary"] = "篡改后的总结。"
            write_json(result_path, result)
            with self.assertRaisesRegex(
                ReviewError,
                "REVIEW_DISPATCH_PROVENANCE_MISMATCH",
            ):
                validate_receipt(
                    receipt,
                    review_root=review_root,
                    workspace=root,
                )


if __name__ == "__main__":
    unittest.main()

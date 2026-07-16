from __future__ import annotations

import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path

from helpers import WritableTemporaryDirectory


EXECUTOR_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REVIEWER_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "complex-coding-reviewer"
    / "scripts"
)
sys.path.insert(0, str(EXECUTOR_SCRIPTS))
sys.path.insert(0, str(REVIEWER_SCRIPTS))

from complex_coding_reviewer.context import RISK_IDS, build_context_target  # noqa: E402
from complex_coding_reviewer.contract import CODE_LENSES  # noqa: E402
from complex_coding_reviewer.target import (  # noqa: E402
    build_commit_range_target,
    build_working_tree_target,
)
from harness_review import ReviewGateError, validate_review_gate  # noqa: E402
from harness_task_bundle import resolve_task_bundle  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class ReviewGateTest(unittest.TestCase):
    def run_git(self, workspace: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        return result.stdout.strip()

    def make_bundle(self):
        temporary = WritableTemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        workspace = Path(temporary.name)
        self.run_git(workspace, "init", "--quiet")
        source = workspace / "src" / "example.py"
        source.parent.mkdir(parents=True)
        source.write_text("answer = 41\n", encoding="utf-8")
        self.run_git(workspace, "add", "src/example.py")
        self.run_git(
            workspace,
            "-c",
            "user.name=Executor Test",
            "-c",
            "user.email=executor@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initial",
        )
        source.write_text("answer = 42\n", encoding="utf-8")
        task_dir = workspace / ".harness" / "tasks" / "review-gate"
        task_dir.mkdir(parents=True)
        (task_dir / "execution-plan.md").write_text("# plan\n", encoding="utf-8")
        write_json(
            task_dir / "plan-contract.json",
            {
                "task_id": "review-gate",
                "plan_revision": 1,
                "stages": [
                    {
                        "id": "STG-01",
                        "depends_on": [],
                        "validation_ids": [],
                        "allowed_changes": ["src/**"],
                    }
                ],
                "validations": [],
            },
        )
        return resolve_task_bundle(workspace, ".harness/tasks/review-gate"), source

    def receipt(
        self,
        bundle,
        target: dict[str, object],
        scope: dict[str, object],
    ) -> dict[str, object]:
        task_relative = bundle.task_dir.relative_to(bundle.workspace).as_posix()
        brief_relative = f"{task_relative}/artifacts/reviews/review-brief.json"
        plan_relative = bundle.plan_path.relative_to(bundle.workspace).as_posix()
        contract_relative = bundle.contract_path.relative_to(bundle.workspace).as_posix()
        stages = {
            item["id"]: item
            for item in bundle.contract["stages"]
        }
        if scope["kind"] == "stage-delta":
            stage = stages[scope["stage_id"]]
            requirement_refs = sorted(
                {
                    item
                    for field in (
                        "requirement_ids",
                        "acceptance_ids",
                        "nonfunctional_ids",
                    )
                    for item in stage.get(field, [])
                }
            ) or [scope["stage_id"]]
            constraint_refs = sorted(
                {scope["stage_id"], *stage.get("validation_ids", [])}
            )
        else:
            requirement_refs = sorted(stages)
            constraint_refs = sorted(
                {
                    *stages,
                    *(item["id"] for item in bundle.contract["validations"]),
                }
            )
        brief = {
            "profile": "code-review",
            "scope": scope,
            "summary": "验证当前 managed execution target。",
            "requirement_refs": requirement_refs,
            "constraint_refs": constraint_refs,
            "claim_refs": [],
            "requested_risk_focus": [],
            "created_at": "2026-07-16T00:00:00+00:00",
        }
        write_json(bundle.workspace / brief_relative, brief)
        context = build_context_target(
            bundle.workspace,
            root_kind="workspace",
            label="executor-review-gate-context",
            entries=[
                (brief_relative, "brief"),
                (plan_relative, "requirement"),
                (contract_relative, "requirement"),
            ],
        )
        target_paths = [str(item["path"]) for item in target["manifest"]]
        return {
            "review_id": "REV-CODE-GATE-001",
            "profile": "code-review",
            "scope": scope,
            "target": target,
            "context": context,
            "reviewer": {
                "mode": "same-context",
                "identity": "executor-unit-test",
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
            "coverage": {
                "target_paths": [
                    {
                        "path": path,
                        "status": "reviewed",
                        "reason": "fixture 已覆盖完整 target。",
                        "gap_ids": [],
                    }
                    for path in target_paths
                ],
                "requirement_checks": [
                    {
                        "id": requirement_ref,
                        "status": "satisfied",
                        "evidence_refs": [brief_relative],
                        "finding_ids": [],
                        "gap_ids": [],
                        "summary": "当前 target 满足 fixture 要求。",
                    }
                    for requirement_ref in requirement_refs
                ],
                "risk_checks": [
                    {
                        "id": risk_id,
                        "status": "not-triggered",
                        "trigger": "fixture 未包含该风险触发面。",
                        "evidence_refs": [brief_relative],
                        "finding_ids": [],
                        "gap_ids": [],
                        "summary": "已检查触发条件，当前不适用。",
                    }
                    for risk_id in RISK_IDS
                ],
                "context_expansions": [],
            },
            "lenses": [
                {
                    "id": lens,
                    "status": "reviewed",
                    "evidence_refs": [brief_relative],
                    "summary": f"{lens} 已完成审查。",
                }
                for lens in CODE_LENSES
            ],
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
            "summary": "当前代码目标通过正式审查。",
            "limitations": ["未执行目标代码。"],
            "supersedes_review_id": None,
            "reviewed_at": "2026-07-16T00:00:00+00:00",
        }

    def compact(self, receipt: dict[str, object], report_ref: str) -> dict[str, object]:
        target = receipt["target"]
        context = receipt["context"]
        assert isinstance(target, dict)
        assert isinstance(context, dict)
        predecessor = receipt["supersedes_review_id"]
        return {
            "result": "passed",
            "review_id": receipt["review_id"],
            "profile": receipt["profile"],
            "scope": receipt["scope"],
            "target_digest": target["digest"],
            "context_digest": context["digest"],
            "verdict": receipt["verdict"],
            "report_ref": report_ref,
            "open_counts": receipt["open_counts"],
            "gap_counts": {"blocking": 0, "major": 0, "minor": 0, "total": 0},
            "coverage_summary": {
                "target_paths": len(receipt["coverage"]["target_paths"]),
                "requirements": len(receipt["coverage"]["requirement_checks"]),
                "risks": len(receipt["coverage"]["risk_checks"]),
                "context_expansions": len(receipt["coverage"]["context_expansions"]),
            },
            "lineage_summary": {
                "predecessor_review_id": predecessor,
                "accounted_finding_count": 0,
            },
            "strength_count": len(receipt["strengths"]),
            "summary": receipt["summary"],
        }

    def write_receipt(self, bundle, receipt: dict[str, object], name: str):
        report_ref = f"artifacts/reviews/{name}"
        write_json(bundle.task_dir / report_ref, receipt)
        return self.compact(receipt, report_ref)

    def test_stage_receipt_is_validated_by_public_cli(self) -> None:
        bundle, _ = self.make_bundle()
        target = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
            stage_id="STG-01",
            attempt=1,
        )
        receipt = self.receipt(
            bundle,
            target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        compact = self.write_receipt(bundle, receipt, "stage-01.json")
        result = validate_review_gate(
            bundle,
            compact,
            stage_id="STG-01",
            attempt=1,
        )
        self.assertEqual(compact, result)

    def test_source_change_makes_stage_receipt_stale(self) -> None:
        bundle, source = self.make_bundle()
        target = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
            stage_id="STG-01",
            attempt=1,
        )
        receipt = self.receipt(
            bundle,
            target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        compact = self.write_receipt(bundle, receipt, "stage-01.json")
        source.write_text("answer = 43\n", encoding="utf-8")
        with self.assertRaisesRegex(ReviewGateError, "REVIEW_TARGET_STALE"):
            validate_review_gate(
                bundle,
                compact,
                stage_id="STG-01",
                attempt=1,
            )

    def test_context_change_makes_stage_receipt_stale(self) -> None:
        bundle, _ = self.make_bundle()
        target = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
            stage_id="STG-01",
            attempt=1,
        )
        receipt = self.receipt(
            bundle,
            target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        compact = self.write_receipt(bundle, receipt, "context-stale-stage.json")
        context = receipt["context"]
        brief = next(item for item in context["manifest"] if item["role"] == "brief")
        brief_path = bundle.workspace / brief["path"]
        brief_path.write_text(
            brief_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ReviewGateError, "REVIEW_CONTEXT_STALE"):
            validate_review_gate(
                bundle,
                compact,
                stage_id="STG-01",
                attempt=1,
            )

    def test_managed_brief_must_match_contract_requirements(self) -> None:
        bundle, _ = self.make_bundle()
        target = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
            stage_id="STG-01",
            attempt=1,
        )
        receipt = self.receipt(
            bundle,
            target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        context = receipt["context"]
        brief_entry = next(item for item in context["manifest"] if item["role"] == "brief")
        brief_path = bundle.workspace / brief_entry["path"]
        brief = json.loads(brief_path.read_text(encoding="utf-8"))
        brief["requirement_refs"] = ["REQ-WRONG"]
        write_json(brief_path, brief)
        receipt["coverage"]["requirement_checks"][0]["id"] = "REQ-WRONG"
        receipt["context"] = build_context_target(
            bundle.workspace,
            root_kind="workspace",
            label=context["identity"]["label"],
            entries=[(item["path"], item["role"]) for item in context["manifest"]],
        )
        compact = self.write_receipt(bundle, receipt, "wrong-requirements-stage.json")
        with self.assertRaisesRegex(
            ReviewGateError,
            "RUN_STATE_REVIEW_REQUIREMENTS_MISMATCH",
        ):
            validate_review_gate(
                bundle,
                compact,
                stage_id="STG-01",
                attempt=1,
            )

    def test_validation_evidence_must_enter_managed_context(self) -> None:
        bundle, _ = self.make_bundle()
        bundle.contract["stages"][0]["validation_ids"] = ["VAL-01"]
        bundle.contract["validations"] = [{"id": "VAL-01", "required": True}]
        write_json(bundle.contract_path, bundle.contract)
        target = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
            stage_id="STG-01",
            attempt=1,
        )
        evidence_ref = "artifacts/validation/val-01.txt"
        evidence = bundle.task_dir / evidence_ref
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("passed\n", encoding="utf-8")
        bundle.ledger_path.write_text(
            json.dumps(
                {
                    "type": "validation_recorded",
                    "stage_id": "STG-01",
                    "attempt": 1,
                    "payload": {
                        "validation_id": "VAL-01",
                        "result": "passed",
                        "target_digest": target["digest"],
                        "stage_attempt": 1,
                    },
                    "evidence_refs": [evidence_ref],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        receipt = self.receipt(
            bundle,
            target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        compact = self.write_receipt(bundle, receipt, "missing-validation-context.json")
        with self.assertRaisesRegex(
            ReviewGateError,
            "RUN_STATE_REVIEW_VALIDATION_CONTEXT_MISSING",
        ):
            validate_review_gate(
                bundle,
                compact,
                stage_id="STG-01",
                attempt=1,
            )

    def test_final_receipt_uses_final_integration_scope(self) -> None:
        bundle, _ = self.make_bundle()
        baseline = self.run_git(bundle.workspace, "rev-parse", "HEAD")
        self.run_git(bundle.workspace, "add", "src/example.py")
        self.run_git(
            bundle.workspace,
            "-c",
            "user.name=Executor Test",
            "-c",
            "user.email=executor@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "final source",
        )
        head = self.run_git(bundle.workspace, "rev-parse", "HEAD")
        target = build_commit_range_target(
            bundle.workspace,
            baseline=baseline,
            head=head,
            paths=["src"],
        )
        receipt = self.receipt(bundle, target, {"kind": "final-integration"})
        compact = self.write_receipt(bundle, receipt, "final.json")
        self.assertEqual(
            compact,
            validate_review_gate(
                bundle,
                compact,
                stage_id=None,
                attempt=None,
                final_commit_recorded=True,
            ),
        )

    def test_stage_receipt_rejects_out_of_scope_worktree_change(self) -> None:
        bundle, _ = self.make_bundle()
        target = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
            stage_id="STG-01",
            attempt=1,
        )
        receipt = self.receipt(
            bundle,
            target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        compact = self.write_receipt(bundle, receipt, "out-of-scope-stage.json")
        (bundle.workspace / "outside.txt").write_text("drift\n", encoding="utf-8")
        with self.assertRaisesRegex(ReviewGateError, "RUN_STATE_REVIEW_SCOPE_DRIFT"):
            validate_review_gate(
                bundle,
                compact,
                stage_id="STG-01",
                attempt=1,
            )

    def test_stage_receipt_rejects_noncanonical_path_selection(self) -> None:
        bundle, _ = self.make_bundle()
        target = build_working_tree_target(
            bundle.workspace,
            stage_id="STG-01",
            attempt=1,
        )
        receipt = self.receipt(
            bundle,
            target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        compact = self.write_receipt(bundle, receipt, "partial-stage.json")
        with self.assertRaisesRegex(ReviewGateError, "RUN_STATE_REVIEW_SCOPE_MISMATCH"):
            validate_review_gate(
                bundle,
                compact,
                stage_id="STG-01",
                attempt=1,
            )

    def test_stage_scope_inherits_transitive_dependency_paths(self) -> None:
        bundle, _ = self.make_bundle()
        del bundle.contract["stages"][0]["depends_on"]
        bundle.contract["stages"].append(
            {
                "id": "STG-02",
                "depends_on": ["STG-01"],
                "validation_ids": [],
                "allowed_changes": ["docs/**"],
            }
        )
        bundle.contract["stages"].append(
            {
                "id": "STG-03",
                "depends_on": ["STG-02"],
                "validation_ids": [],
                "allowed_changes": [
                    "all files approved by STG-01 through STG-02",
                    "task-local execution evidence",
                ],
            }
        )
        target = build_working_tree_target(
            bundle.workspace,
            paths=["docs", "src"],
            stage_id="STG-03",
            attempt=1,
        )
        receipt = self.receipt(
            bundle,
            target,
            {"kind": "stage-delta", "stage_id": "STG-03", "attempt": 1},
        )
        compact = self.write_receipt(bundle, receipt, "inherited-stage.json")
        self.assertEqual(
            compact,
            validate_review_gate(
                bundle,
                compact,
                stage_id="STG-03",
                attempt=1,
            ),
        )

    def test_final_commit_range_must_end_at_current_head(self) -> None:
        bundle, source = self.make_bundle()
        head = self.run_git(bundle.workspace, "rev-parse", "HEAD")
        target = build_commit_range_target(
            bundle.workspace,
            baseline=head,
            head=head,
            paths=["src"],
        )
        receipt = self.receipt(bundle, target, {"kind": "final-integration"})
        compact = self.write_receipt(bundle, receipt, "stale-final.json")
        source.write_text("answer = 43\n", encoding="utf-8")
        self.run_git(bundle.workspace, "add", "src/example.py")
        self.run_git(
            bundle.workspace,
            "-c",
            "user.name=Executor Test",
            "-c",
            "user.email=executor@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "advance head",
        )
        with self.assertRaisesRegex(ReviewGateError, "REVIEW_TARGET_STALE"):
            validate_review_gate(
                bundle,
                compact,
                stage_id=None,
                attempt=None,
                final_commit_recorded=True,
            )

    def test_final_commit_range_rejects_uncommitted_source_change(self) -> None:
        bundle, source = self.make_bundle()
        baseline = self.run_git(bundle.workspace, "rev-parse", "HEAD")
        self.run_git(bundle.workspace, "add", "src/example.py")
        self.run_git(
            bundle.workspace,
            "-c",
            "user.name=Executor Test",
            "-c",
            "user.email=executor@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "final source",
        )
        head = self.run_git(bundle.workspace, "rev-parse", "HEAD")
        target = build_commit_range_target(
            bundle.workspace,
            baseline=baseline,
            head=head,
            paths=["src"],
        )
        receipt = self.receipt(bundle, target, {"kind": "final-integration"})
        compact = self.write_receipt(bundle, receipt, "dirty-final.json")
        source.write_text("answer = 44\n", encoding="utf-8")
        with self.assertRaisesRegex(ReviewGateError, "REVIEW_TARGET_STALE"):
            validate_review_gate(
                bundle,
                compact,
                stage_id=None,
                attempt=None,
                final_commit_recorded=True,
            )

    def test_final_receipt_must_reuse_first_stage_baseline(self) -> None:
        bundle, _ = self.make_bundle()
        stage_target = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
            stage_id="STG-01",
            attempt=1,
        )
        stage_receipt = self.receipt(
            bundle,
            stage_target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        stage_compact = self.write_receipt(
            bundle,
            stage_receipt,
            "execution-baseline-stage.json",
        )
        bundle.ledger_path.write_text(
            json.dumps(
                {"type": "review_recorded", "payload": stage_compact},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.run_git(bundle.workspace, "add", "src/example.py")
        self.run_git(
            bundle.workspace,
            "-c",
            "user.name=Executor Test",
            "-c",
            "user.email=executor@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "final source",
        )
        head = self.run_git(bundle.workspace, "rev-parse", "HEAD")
        wrong_target = build_commit_range_target(
            bundle.workspace,
            baseline=head,
            head=head,
            paths=["src"],
        )
        final_receipt = self.receipt(
            bundle,
            wrong_target,
            {"kind": "final-integration"},
        )
        final_compact = self.write_receipt(bundle, final_receipt, "wrong-baseline-final.json")
        with self.assertRaisesRegex(
            ReviewGateError,
            "RUN_STATE_REVIEW_BASELINE_MISMATCH",
        ):
            validate_review_gate(
                bundle,
                final_compact,
                stage_id=None,
                attempt=None,
                final_commit_recorded=True,
                require_lifecycle_baseline=True,
            )

    def test_final_baseline_rejects_tampered_stage_receipt(self) -> None:
        bundle, _ = self.make_bundle()
        stage_target = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
            stage_id="STG-01",
            attempt=1,
        )
        stage_receipt = self.receipt(
            bundle,
            stage_target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        stage_compact = self.write_receipt(
            bundle,
            stage_receipt,
            "tampered-baseline-stage.json",
        )
        bundle.ledger_path.write_text(
            json.dumps(
                {"type": "review_recorded", "payload": stage_compact},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        stage_receipt["target"] = {**stage_target, "digest": "f" * 64}
        write_json(
            bundle.task_dir / str(stage_compact["report_ref"]),
            stage_receipt,
        )
        final_receipt = self.receipt(
            bundle,
            stage_target,
            {"kind": "final-integration"},
        )
        final_receipt["target"] = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
        )
        final_compact = self.write_receipt(bundle, final_receipt, "final-after-tamper.json")
        with self.assertRaisesRegex(
            ReviewGateError,
            "RUN_STATE_REVIEW_BASELINE_INVALID",
        ):
            validate_review_gate(
                bundle,
                final_compact,
                stage_id=None,
                attempt=None,
                require_lifecycle_baseline=True,
            )

    def test_supersedes_is_resolved_within_review_root(self) -> None:
        bundle, _ = self.make_bundle()
        target = build_working_tree_target(
            bundle.workspace,
            paths=["src"],
            stage_id="STG-01",
            attempt=1,
        )
        first = self.receipt(
            bundle,
            target,
            {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        )
        self.write_receipt(bundle, first, "stage-01-attempt-1.json")
        second = deepcopy(first)
        second["review_id"] = "REV-CODE-GATE-002"
        second["supersedes_review_id"] = "REV-CODE-GATE-001"
        compact = self.write_receipt(bundle, second, "stage-01-attempt-2.json")
        self.assertEqual(
            compact,
            validate_review_gate(
                bundle,
                compact,
                stage_id="STG-01",
                attempt=1,
            ),
        )

    def test_report_ref_outside_review_root_is_rejected(self) -> None:
        bundle, _ = self.make_bundle()
        payload = {
            "result": "passed",
            "review_id": "REV-CODE-GATE-001",
            "profile": "code-review",
            "scope": {"kind": "final-integration"},
            "target_digest": "a" * 64,
            "context_digest": "b" * 64,
            "verdict": "passed",
            "report_ref": "artifacts/final.json",
            "open_counts": {
                "blocking": 0,
                "major": 0,
                "minor": 0,
                "advisory": 0,
                "total": 0,
            },
            "gap_counts": {"blocking": 0, "major": 0, "minor": 0, "total": 0},
            "coverage_summary": {
                "target_paths": 1,
                "requirements": 1,
                "risks": 6,
                "context_expansions": 0,
            },
            "lineage_summary": {
                "predecessor_review_id": None,
                "accounted_finding_count": 0,
            },
            "strength_count": 0,
            "summary": "review passed",
        }
        with self.assertRaisesRegex(ReviewGateError, "RUN_STATE_REVIEW_REPORT_INVALID"):
            validate_review_gate(bundle, payload, stage_id=None, attempt=None)


if __name__ == "__main__":
    unittest.main()

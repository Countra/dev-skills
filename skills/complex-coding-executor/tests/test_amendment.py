from __future__ import annotations

import json
import sys
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from helpers import WritableTemporaryDirectory


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_amendment import (  # noqa: E402
    AmendmentError,
    activate_amendment,
    archive_current_revision,
    revision_archive_dir,
    validate_archive,
)
from harness_attest_plan import (  # noqa: E402
    ensure_attestation_write_allowed,
    write_mode,
)
from harness_attestation import (  # noqa: E402
    AttestationError,
    build_attestation,
    write_attestation,
)
from harness_event_writer import append_event_and_update  # noqa: E402
from harness_state_io import load_state  # noqa: E402
from harness_task_bundle import resolve_task_bundle  # noqa: E402


def contract(revision: int, include_second_stage: bool = False) -> dict[str, object]:
    stages: list[dict[str, object]] = [
        {"id": "STG-01", "depends_on": [], "validation_ids": ["VAL-01"]}
    ]
    if include_second_stage:
        stages.append(
            {
                "id": "STG-02",
                "depends_on": ["STG-01"],
                "validation_ids": ["VAL-02"],
            }
        )
    validations: list[dict[str, object]] = [
        {"id": "VAL-01", "required": True}
    ]
    if include_second_stage:
        validations.append({"id": "VAL-02", "required": True})
    return {
        "task_id": "amendment-test",
        "plan_revision": revision,
        "artifacts": [],
        "stages": stages,
        "validations": validations,
    }


def stage_review_payload() -> dict[str, object]:
    return {
        "result": "passed",
        "review_id": "REV-CODE-AMENDMENT-001",
        "profile": "code-review",
        "scope": {"kind": "stage-delta", "stage_id": "STG-01", "attempt": 1},
        "target_digest": "a" * 64,
        "context_digest": "b" * 64,
        "verdict": "passed",
        "report_ref": "artifacts/reviews/stage-01.json",
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


class AmendmentTest(unittest.TestCase):
    def make_bundle(self):
        temp = WritableTemporaryDirectory()
        self.addCleanup(temp.cleanup)
        workspace = Path(temp.name)
        task_dir = workspace / ".harness" / "tasks" / "task"
        task_dir.mkdir(parents=True)
        (task_dir / "execution-plan.md").write_text("# revision 1\n", encoding="utf-8")
        (task_dir / "plan-contract.json").write_text(
            json.dumps(contract(1), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        bundle = resolve_task_bundle(workspace, ".harness/tasks/task")
        self.approve(bundle, "revision 1")
        return workspace, task_dir, bundle

    def approve(self, bundle, summary: str) -> None:
        payload = build_attestation(
            bundle,
            approved_by="user",
            approval_summary=summary,
            approved_at="2026-07-10T00:00:00+00:00",
        )
        write_attestation(bundle.attestation_path, payload)

    def complete_first_stage(self, bundle) -> None:
        review = stage_review_payload()
        report = bundle.task_dir / str(review["report_ref"])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("{}\n", encoding="utf-8")
        validation_ref = "artifacts/validation/val-01.txt"
        validation = bundle.task_dir / validation_ref
        validation.parent.mkdir(parents=True, exist_ok=True)
        validation.write_text("validation passed\n", encoding="utf-8")
        events = [
            ("execution_started", {}),
            ("stage_started", {"stage_id": "STG-01", "attempt": 1}),
            (
                "validation_recorded",
                {
                    "stage_id": "STG-01",
                    "attempt": 1,
                    "payload": {
                        "validation_id": "VAL-01",
                        "result": "passed",
                        "command": "python -m unittest",
                        "claim_source": "observed",
                        "stage_attempt": 1,
                        "target_digest": "a" * 64,
                        "exit_code": 0,
                        "summary": "validation passed",
                        "claim_boundary": "只证明当前 target 的测试结果。",
                    },
                    "evidence_refs": [validation_ref],
                },
            ),
            (
                "review_recorded",
                {
                    "stage_id": "STG-01",
                    "attempt": 1,
                    "payload": review,
                    "evidence_refs": [str(review["report_ref"])],
                },
            ),
            ("stage_completed", {"stage_id": "STG-01"}),
        ]
        with mock.patch(
            "harness_event_writer.validate_review_gate",
            return_value=review,
        ):
            for index, (event_type, kwargs) in enumerate(events, start=1):
                append_event_and_update(
                    bundle,
                    event_type,
                    occurred_at=f"2026-07-10T00:00:{index:02d}+00:00",
                    **kwargs,
                )

    def request_amendment(self, bundle) -> None:
        append_event_and_update(
            bundle,
            "amendment_requested",
            payload={"reason": "add second stage"},
            occurred_at="2026-07-10T00:00:06+00:00",
        )

    def test_archive_and_activate_new_revision(self) -> None:
        workspace, task_dir, bundle = self.make_bundle()
        self.complete_first_stage(bundle)
        self.request_amendment(bundle)
        manifest = archive_current_revision(bundle)
        archive_root = revision_archive_dir(bundle, 1)
        self.assertEqual(1, manifest["plan_revision"])
        self.assertEqual(manifest, validate_archive(bundle, archive_root))

        (task_dir / "execution-plan.md").write_text("# revision 2\n", encoding="utf-8")
        (task_dir / "plan-contract.json").write_text(
            json.dumps(contract(2, include_second_stage=True), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        new_bundle = resolve_task_bundle(workspace, ".harness/tasks/task")
        self.approve(new_bundle, "revision 2")
        result = activate_amendment(
            new_bundle,
            archive_root,
            carried_completed_stage_ids=["STG-01"],
            occurred_at="2026-07-10T00:01:00+00:00",
        )
        self.assertEqual(["STG-01"], result["state"]["completed_stage_ids"])
        self.assertEqual(["STG-02"], result["state"]["remaining_stage_ids"])
        self.assertEqual("start STG-02", result["state"]["next_action"])
        self.assertEqual(1, load_state(new_bundle.run_state_path)["last_event_seq"])

    def test_archive_manifest_rejects_unsafe_source_path(self) -> None:
        _, _, bundle = self.make_bundle()
        self.complete_first_stage(bundle)
        self.request_amendment(bundle)
        archive_current_revision(bundle)
        archive_root = revision_archive_dir(bundle, 1)
        manifest_path = archive_root / "archive-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][0]["source_path"] = "../outside"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(AmendmentError, "AMENDMENT_ARCHIVE_PATH_UNSAFE"):
            validate_archive(bundle, archive_root)

    def test_archive_manifest_requires_revision_evidence_set(self) -> None:
        _, _, bundle = self.make_bundle()
        archive_current_revision(bundle)
        archive_root = revision_archive_dir(bundle, 1)
        manifest_path = archive_root / "archive-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"] = [
            item
            for item in manifest["files"]
            if item["source_path"] != "attestation.json"
        ]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(AmendmentError, "AMENDMENT_ARCHIVE_INVALID"):
            validate_archive(bundle, archive_root)

    def test_runtime_archive_requires_amendment_request(self) -> None:
        _, _, bundle = self.make_bundle()
        self.complete_first_stage(bundle)
        with self.assertRaisesRegex(AmendmentError, "AMENDMENT_NOT_REQUESTED"):
            archive_current_revision(bundle)

    def test_attestation_cannot_be_overwritten_in_same_revision(self) -> None:
        _, _, bundle = self.make_bundle()
        with self.assertRaisesRegex(AmendmentError, "ATTESTATION_ALREADY_EXISTS"):
            ensure_attestation_write_allowed(bundle)

    def test_invalid_attestation_is_not_written(self) -> None:
        _, _, bundle = self.make_bundle()
        bundle.attestation_path.unlink()
        args = Namespace(
            approved_by="user",
            approval_summary="approve implementation",
            commit_authorized=False,
            external_write_authorized=False,
            elevated_tool_authorized=False,
            approved_at="not-a-time",
        )
        with mock.patch("harness_attest_plan.run_planner_approval_check"):
            with self.assertRaisesRegex(
                AttestationError,
                "ATTESTATION_APPROVAL_INVALID",
            ):
                write_mode(bundle, args)
        self.assertFalse(bundle.attestation_path.exists())

    def test_changed_stage_semantics_cannot_be_carried(self) -> None:
        workspace, task_dir, bundle = self.make_bundle()
        self.complete_first_stage(bundle)
        self.request_amendment(bundle)
        archive_root = revision_archive_dir(bundle, 1)
        archive_current_revision(bundle)

        changed = contract(2, include_second_stage=True)
        changed["stages"][0]["validation_ids"] = ["VAL-CHANGED"]
        (task_dir / "execution-plan.md").write_text("# revision 2\n", encoding="utf-8")
        (task_dir / "plan-contract.json").write_text(
            json.dumps(changed, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        new_bundle = resolve_task_bundle(workspace, ".harness/tasks/task")
        self.approve(new_bundle, "revision 2")
        with self.assertRaisesRegex(
            AmendmentError,
            "AMENDMENT_CARRY_SEMANTICS_CHANGED",
        ):
            activate_amendment(
                new_bundle,
                archive_root,
                carried_completed_stage_ids=["STG-01"],
            )

    def test_uncompleted_stage_cannot_be_carried(self) -> None:
        workspace, task_dir, bundle = self.make_bundle()
        archive_current_revision(bundle)
        archive_root = revision_archive_dir(bundle, 1)

        (task_dir / "execution-plan.md").write_text(
            "# revision 2\n",
            encoding="utf-8",
        )
        (task_dir / "plan-contract.json").write_text(
            json.dumps(
                contract(2, include_second_stage=True),
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        new_bundle = resolve_task_bundle(workspace, ".harness/tasks/task")
        self.approve(new_bundle, "revision 2")
        with self.assertRaisesRegex(
            AmendmentError,
            "AMENDMENT_CARRY_NOT_COMPLETED",
        ):
            activate_amendment(
                new_bundle,
                archive_root,
                carried_completed_stage_ids=["STG-01"],
            )


if __name__ == "__main__":
    unittest.main()

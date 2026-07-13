"""人工 packet 与用户 observation importer 测试。"""

from __future__ import annotations

import unittest

from _helpers import temporary_workspace, valid_suite, write_skill
from skill_evaluation_lab.contracts import (
    ContractError,
    validate_imported_observation,
    validate_packet,
)
from skill_evaluation_lab.errors import ObservationError, PacketError
from skill_evaluation_lab.observations import import_observations
from skill_evaluation_lab.packets import build_packet, suite_receipt, write_packet
from skill_evaluation_lab.paths import hash_document


def bundle_for(packet: dict[str, object], *, complete: bool = True) -> dict[str, object]:
    cases = packet["cases"]
    assert isinstance(cases, list)
    selected = cases if complete else cases[:1]
    return {
        "schema_version": 1,
        "packet_fingerprint": packet["packet_fingerprint"],
        "declared_by": "user",
        "sessions": [
            {
                "case_id": case["case_id"],
                "variant": case["variant"],
                "session_ref": f"session-{index + 1}",
                "status": "pass",
                "notes": "由用户在独立会话中确认。",
                "artifacts": [],
            }
            for index, case in enumerate(selected)
        ],
    }


class PacketTests(unittest.TestCase):
    def test_suite_receipt_and_packet_bind_sources_cases_and_inputs(self) -> None:
        with temporary_workspace() as workspace:
            write_skill(workspace)
            input_path = workspace / "inputs" / "request.txt"
            input_path.parent.mkdir()
            input_path.write_text("request", encoding="utf-8")
            suite = valid_suite()
            suite["cases"][2]["inputs"] = ["inputs/request.txt"]
            receipt = suite_receipt(workspace, suite)
            packet, _ = build_packet(workspace, suite)
            self.assertTrue(receipt["valid"])
            self.assertEqual(receipt["agent_calls"], 0)
            self.assertEqual(packet["execution_mode"], "user_operated_independent_session")
            self.assertEqual(len(packet["cases"]), 3)
            behavior = next(case for case in packet["cases"] if case["kind"] == "behavior")
            self.assertEqual(behavior["inputs"][0]["path"], "inputs/request.txt")
            self.assertEqual(len(behavior["inputs"][0]["sha256"]), 64)

    def test_packet_fingerprint_rejects_tampering(self) -> None:
        with temporary_workspace() as workspace:
            write_skill(workspace)
            packet, _ = build_packet(workspace, valid_suite())
            packet["cases"][0]["prompt"] = "被篡改的 prompt"
            with self.assertRaisesRegex(ContractError, "fingerprint"):
                validate_packet(packet)

    def test_packet_rejects_rehashed_unknown_variant(self) -> None:
        with temporary_workspace() as workspace:
            write_skill(workspace)
            packet, _ = build_packet(workspace, valid_suite())
            packet["cases"][0]["variant"] = "runner"
            case_payload = {
                key: value
                for key, value in packet["cases"][0].items()
                if key != "case_fingerprint"
            }
            packet["cases"][0]["case_fingerprint"] = hash_document(case_payload)
            packet_payload = {
                key: value
                for key, value in packet.items()
                if key != "packet_fingerprint"
            }
            packet["packet_fingerprint"] = hash_document(packet_payload)
            with self.assertRaisesRegex(ContractError, "variant"):
                validate_packet(packet)

    def test_write_packet_is_non_executable_and_never_overwrites(self) -> None:
        with temporary_workspace() as workspace:
            write_skill(workspace)
            packet, _ = build_packet(workspace, valid_suite())
            output = workspace / "evidence" / "packet"
            result = write_packet(output, packet)
            self.assertEqual(result["next_action"], "stop_and_wait_for_user_operated_independent_sessions")
            self.assertEqual(sorted(path.name for path in output.iterdir()), [
                "INSTRUCTIONS.md",
                "observation-template.json",
                "packet.json",
            ])
            instructions = (output / "INSTRUCTIONS.md").read_text(encoding="utf-8")
            self.assertIn("不得自动启动", instructions)
            self.assertNotIn(" exec ", instructions.lower())
            with self.assertRaisesRegex(PacketError, "已存在"):
                write_packet(output, packet)


class ObservationImportTests(unittest.TestCase):
    def test_complete_user_bundle_imports_artifact_hash_and_provenance(self) -> None:
        with temporary_workspace() as workspace:
            write_skill(workspace)
            packet, _ = build_packet(workspace, valid_suite())
            artifact = workspace / "observations" / "result.txt"
            artifact.parent.mkdir()
            artifact.write_text("user evidence", encoding="utf-8")
            bundle = bundle_for(packet)
            bundle["sessions"][0]["artifacts"] = [{"path": "observations/result.txt"}]
            imported = import_observations(workspace, packet, bundle)
            self.assertEqual(imported["coverage"]["status"], "complete")
            self.assertEqual(imported["provenance"]["declared_by"], "user")
            self.assertEqual(imported["provenance"]["agent_calls"], 0)
            self.assertEqual(len(imported["sessions"][0]["artifacts"][0]["sha256"]), 64)
            imported["coverage"]["observed"] = []
            with self.assertRaisesRegex(ContractError, "集合不一致"):
                validate_imported_observation(imported)

    def test_import_preserves_optional_baseline_hash(self) -> None:
        with temporary_workspace() as workspace:
            write_skill(workspace)
            baseline = write_skill(workspace, "baseline-skill")
            packet, _ = build_packet(
                workspace,
                valid_suite(baseline=baseline.relative_to(workspace).as_posix()),
            )
            imported = import_observations(workspace, packet, bundle_for(packet))
            self.assertEqual(
                imported["baseline_tree_sha256"],
                packet["sources"]["baseline"]["tree_sha256"],
            )

    def test_partial_bundle_remains_partial_without_fabricated_sessions(self) -> None:
        with temporary_workspace() as workspace:
            write_skill(workspace)
            packet, _ = build_packet(workspace, valid_suite())
            imported = import_observations(workspace, packet, bundle_for(packet, complete=False))
            self.assertEqual(imported["coverage"]["status"], "partial")
            self.assertEqual(len(imported["sessions"]), 1)
            self.assertEqual(len(imported["coverage"]["missing"]), 2)

    def test_rejects_packet_mismatch_unknown_case_and_source_drift(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            packet, _ = build_packet(workspace, valid_suite())
            bundle = bundle_for(packet)
            bundle["packet_fingerprint"] = "f" * 64
            with self.assertRaisesRegex(ObservationError, "fingerprint"):
                import_observations(workspace, packet, bundle)
            bundle = bundle_for(packet)
            bundle["sessions"][0]["case_id"] = "unknown-case"
            with self.assertRaisesRegex(ObservationError, "不存在"):
                import_observations(workspace, packet, bundle)
            bundle = bundle_for(packet)
            (source / "SKILL.md").write_text(
                (source / "SKILL.md").read_text(encoding="utf-8") + "\nsource drift\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ObservationError, "已变化"):
                import_observations(workspace, packet, bundle)

    def test_rejects_artifact_hash_mismatch_and_artifact_inside_source(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            packet, _ = build_packet(workspace, valid_suite())
            artifact = workspace / "artifact.txt"
            artifact.write_text("evidence", encoding="utf-8")
            bundle = bundle_for(packet, complete=False)
            bundle["sessions"][0]["artifacts"] = [
                {"path": "artifact.txt", "sha256": "0" * 64}
            ]
            with self.assertRaisesRegex(ObservationError, "hash"):
                import_observations(workspace, packet, bundle)
            bundle["sessions"][0]["artifacts"] = [
                {"path": source.joinpath("SKILL.md").relative_to(workspace).as_posix()}
            ]
            with self.assertRaisesRegex(ObservationError, "source 内"):
                import_observations(workspace, packet, bundle)


if __name__ == "__main__":
    unittest.main()

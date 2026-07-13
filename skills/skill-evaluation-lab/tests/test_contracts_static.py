"""闭合契约、路径和静态 parser 测试。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from _helpers import temporary_workspace, valid_semantic_review, valid_suite, write_json, write_skill
from skill_evaluation_lab.contracts import (
    ContractError,
    validate_observation_bundle,
    validate_semantic_review,
    validate_static_evidence,
    validate_suite,
)
from skill_evaluation_lab.errors import PathError, SkillError
from skill_evaluation_lab.paths import ResourceLimits, resolve_input, resolve_output, source_identity
from skill_evaluation_lab.skill_parser import inspect_links, inspect_syntax, parse_skill
from skill_evaluation_lab.static_checks import evaluate_skill


class ContractTests(unittest.TestCase):
    def test_accepts_closed_suite_and_rejects_unknown_field(self) -> None:
        suite = valid_suite()
        self.assertIs(validate_suite(suite), suite)
        suite["unexpected"] = True
        with self.assertRaisesRegex(ContractError, "未知字段"):
            validate_suite(suite)

    def test_requires_all_case_kinds_and_independent_session(self) -> None:
        suite = valid_suite()
        suite["cases"] = suite["cases"][:-1]
        with self.assertRaisesRegex(ContractError, "缺少必要 case kind"):
            validate_suite(suite)
        suite = valid_suite()
        suite["observation_policy"]["require_independent_session"] = False
        with self.assertRaisesRegex(ContractError, "独立会话"):
            validate_suite(suite)

    def test_requires_complete_semantic_dimensions_and_recommendation(self) -> None:
        review = valid_semantic_review("sample-evaluation", "a" * 64)
        review["dimensions"] = review["dimensions"][:-1]
        with self.assertRaisesRegex(ContractError, "缺少语义审查维度"):
            validate_semantic_review(review)
        review = valid_semantic_review("sample-evaluation", "a" * 64)
        review["dimensions"][0]["status"] = "warn"
        with self.assertRaises(ContractError) as context:
            validate_semantic_review(review)
        self.assertEqual(context.exception.path, "$.dimensions[0].recommendation")

    def test_observation_bundle_is_user_declared_and_closed(self) -> None:
        bundle = {
            "schema_version": 1,
            "packet_fingerprint": "b" * 64,
            "declared_by": "user",
            "sessions": [
                {
                    "case_id": "positive-case",
                    "variant": "candidate",
                    "session_ref": "session-1",
                    "status": "pass",
                    "notes": "用户确认按预期触发。",
                    "artifacts": [],
                }
            ],
        }
        self.assertIs(validate_observation_bundle(bundle), bundle)
        bundle["declared_by"] = "agent"
        with self.assertRaisesRegex(ContractError, "user"):
            validate_observation_bundle(bundle)
        bundle["declared_by"] = "user"
        bundle["sessions"][0]["variant"] = "runner"
        with self.assertRaisesRegex(ContractError, "variant"):
            validate_observation_bundle(bundle)

    def test_requires_candidate_variant_and_rejects_cross_platform_escape(self) -> None:
        suite = valid_suite(baseline="skills/baseline-skill")
        suite["observation_policy"]["required_variants"] = ["baseline"]
        with self.assertRaisesRegex(ContractError, "candidate"):
            validate_suite(suite)
        suite = valid_suite()
        suite["candidate"] = r"..\outside"
        with self.assertRaisesRegex(ContractError, "相对路径"):
            validate_suite(suite)

    def test_static_evidence_rejects_checker_and_manifest_drift(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            evidence = evaluate_skill(workspace, source)
            evidence["checker"]["network_calls"] = 1
            with self.assertRaisesRegex(ContractError, "纯静态"):
                validate_static_evidence(evidence)
            evidence = evaluate_skill(workspace, source)
            evidence["candidate"]["files"][0]["size"] += 1
            with self.assertRaisesRegex(ContractError, "total_bytes"):
                validate_static_evidence(evidence)


class PathAndParserTests(unittest.TestCase):
    def test_rejects_parent_escape_and_existing_output(self) -> None:
        with temporary_workspace() as workspace:
            write_skill(workspace)
            with self.assertRaises(PathError):
                resolve_input(workspace, Path("../outside"), label="candidate", expect="directory")
            existing = workspace / "evidence.json"
            existing.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(PathError, "拒绝覆盖"):
                resolve_output(workspace, existing, label="output")

    def test_source_identity_is_stable_and_changes_with_content(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            first = source_identity(workspace, source)
            second = source_identity(workspace, source)
            self.assertEqual(first["tree_sha256"], second["tree_sha256"])
            (source / "SKILL.md").write_text(
                (source / "SKILL.md").read_text(encoding="utf-8") + "\n新增约束。\n",
                encoding="utf-8",
            )
            third = source_identity(workspace, source)
            self.assertNotEqual(first["tree_sha256"], third["tree_sha256"])

    def test_source_identity_bounds_directory_entries(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            limits = ResourceLimits(max_entries=2)
            with self.assertRaisesRegex(SkillError, "目录项"):
                source_identity(workspace, source, limits=limits)

    def test_rejects_source_symlink_when_supported(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            target = workspace / "target.txt"
            target.write_text("target", encoding="utf-8")
            link = source / "assets" / "linked.txt"
            link.parent.mkdir()
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"当前平台不能创建测试 symlink：{exc}")
            with self.assertRaisesRegex(PathError, "链接"):
                source_identity(workspace, source)

    def test_parses_folded_description_and_detects_broken_link(self) -> None:
        with temporary_workspace() as workspace:
            source = workspace / "skills" / "candidate-skill"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(
                "---\nname: candidate-skill\ndescription: >-\n"
                "  用于测试折叠字段，\n  并说明触发时机。\n---\n\n"
                "[缺失](references/missing.md)\n",
                encoding="utf-8",
            )
            document = parse_skill(source)
            self.assertIn("用于测试折叠字段", document.frontmatter["description"])
            links = inspect_links(source, document)
            self.assertEqual(links[0]["status"], "broken")

    def test_reports_python_and_json_syntax_without_importing(self) -> None:
        with temporary_workspace() as workspace:
            source = write_skill(workspace)
            marker = workspace / "imported.txt"
            (source / "scripts" / "check.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\ndef broken(:\n",
                encoding="utf-8",
            )
            write_json(source / "assets" / "bad.json", {"valid": True})
            (source / "assets" / "bad.json").write_text("{", encoding="utf-8")
            identity = source_identity(workspace, source)
            issues = inspect_syntax(source, identity["files"])
            self.assertEqual({item["path"] for item in issues}, {"assets/bad.json", "scripts/check.py"})
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from harness_plan_check import validate_task  # noqa: E402
from test_harness_plan_check import valid_contract, valid_plan  # noqa: E402


TODAY = "2026-07-15"
HARD_GATES = {
    "authenticity",
    "compatibility",
    "stable_support",
    "lifecycle",
    "security",
    "license",
    "reproducibility",
}
SIGNALS = {
    "stable_version",
    "adoption_scale",
    "update_recency",
    "maintenance_activity",
    "adoption_trend",
    "api_and_project_fit",
    "ecosystem_and_docs",
    "transitive_and_provenance",
    "operational_cost",
}


def candidate(
    package: str,
    source_repository: str,
    selection_class: str,
    *,
    disposition: str = "selected",
    key: str = "selected",
) -> dict[str, object]:
    signals: dict[str, object] = {}
    for name in SIGNALS:
        window = "12m" if name in {"maintenance_activity", "adoption_trend"} else "snapshot"
        signals[name] = {
            "result": "pass",
            "value": f"{name} evidence",
            "source_type": "official",
            "url": f"https://example.com/evidence/{name}",
            "as_of": TODAY,
            "window": window,
            "caveat": "Public evidence has ecosystem-specific coverage limits.",
        }
    return {
        "key": key,
        "package": package,
        "source_repository": source_repository,
        "selected_version": "v1.2.3",
        "selection_class": selection_class,
        "disposition": disposition,
        "hard_gates": {
            name: {
                "result": "pass",
                "source": f"https://example.com/hard-gates/{name}",
            }
            for name in HARD_GATES
        },
        "trust_signals": signals,
        "fit_summary": "The candidate fits the approved Go project constraints.",
        "risks": [],
    }


def dependency_bundle(
    *,
    package: str = "github.com/gin-gonic/gin",
    source_repository: str = "https://github.com/gin-gonic/gin",
    action: str = "add",
    mode: str = "change",
    necessity: str = "dependency-required",
    selection_class: str = "ecosystem-mainstream",
) -> tuple[dict[str, object], str, dict[str, object]]:
    contract = valid_contract()
    contract["artifacts"] = [
        {
            "id": "ART-01",
            "kind": "dependency",
            "path": "artifacts/dependencies/dependency-selection.json",
            "required": True,
            "approval_included": True,
        }
    ]
    contract["stages"][0]["allowed_changes"] = ["src/", "go.mod", "go.sum"]
    decision = {
        "id": "DEP-01",
        "action": action,
        "category": "go-component",
        "criticality": "runtime",
        "requirement_ids": ["REQ-01"],
        "selection_class": selection_class,
        "ecosystem": "go",
        "package": package,
        "source_repository": source_repository,
        "selected_version": "v1.2.3",
        "version_policy": "pin exact v1.2.3",
        "manifest_paths": ["go.mod", "go.sum"],
        "freshness_max_age_days": 60,
        "evidence_artifact_id": "ART-01",
        "validation_ids": ["VAL-01"],
    }
    contract["dependency_selection"] = {
        "mode": mode,
        "necessity_result": necessity,
        "decision_ids": ["DEP-01"],
        "evidence_artifact_ids": ["ART-01"],
        "decisions": [decision],
    }
    plan = valid_plan().replace(
        "VAL-01 src/ unrelated/",
        "VAL-01 src/ go.mod go.sum unrelated/",
    ).replace(
        "- Selection mode: `none`\n- Dependency selection result: `not-applicable`",
        "\n".join(
            [
                f"- Selection mode: `{mode}`",
                "- Dependency selection result: `passed`",
                f"- DEP-01 selects {package} v1.2.3 as {selection_class}.",
                "- Version policy: pin exact v1.2.3.",
                "- Manifest paths: go.mod and go.sum.",
                "- Evidence and validation: ART-01 and VAL-01.",
            ]
        ),
    ).replace("## Artifact Index\n\ncomplete", "## Artifact Index\n\nART-01")
    receipt = {
        "observed_at": TODAY,
        "decisions": [
            {
                "decision_id": "DEP-01",
                "necessity": {
                    "result": necessity,
                    "existing_or_standard_option": "Compared existing and standard options.",
                    "evidence": ["REQ-01"],
                },
                "candidates": [
                    candidate(package, source_repository, selection_class)
                ],
                "excluded_alternatives": ["Alternatives do not meet REQ-01 as well."],
                "decision_reason": "Selected under the approved priority and hard gates.",
                "exception": None,
            }
        ],
    }
    return contract, plan, receipt


class DependencyContractTest(unittest.TestCase):
    def make_task(
        self,
        contract: dict[str, object],
        plan: str,
        receipt: dict[str, object],
    ) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        task_dir = Path(temporary.name)
        (task_dir / "plan-contract.json").write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (task_dir / "execution-plan.md").write_text(plan, encoding="utf-8")
        artifact = task_dir / "artifacts" / "dependencies" / "dependency-selection.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return task_dir

    def codes(self, bundle: tuple[dict[str, object], str, dict[str, object]]) -> set[str]:
        task_dir = self.make_task(*bundle)
        return {
            issue.code
            for issue in validate_task(task_dir, "approval")
            if issue.level == "error"
        }

    def test_go_mainstream_gin_and_gorm_receipts_pass(self) -> None:
        for package, source in (
            ("github.com/gin-gonic/gin", "https://github.com/gin-gonic/gin"),
            ("gorm.io/gorm", "https://github.com/go-gorm/gorm"),
        ):
            with self.subTest(package=package):
                self.assertEqual(set(), self.codes(dependency_bundle(package=package, source_repository=source)))

    def test_go_retain_and_standard_library_receipts_pass(self) -> None:
        retain = dependency_bundle(
            action="retain",
            mode="retain",
            necessity="existing-sufficient",
            selection_class="existing-stack",
        )
        standard = dependency_bundle(
            package="net/http",
            source_repository="https://pkg.go.dev/net/http",
            action="retain",
            mode="retain",
            necessity="standard-or-official-sufficient",
            selection_class="standard-or-official",
        )
        self.assertEqual(set(), self.codes(retain))
        self.assertEqual(set(), self.codes(standard))

    def test_stale_signal_and_trend_without_proxies_are_rejected(self) -> None:
        contract, plan, receipt = dependency_bundle()
        trend = receipt["decisions"][0]["candidates"][0]["trust_signals"]["adoption_trend"]
        trend["result"] = "insufficient-data"
        trend["as_of"] = "2025-01-01"
        codes = self.codes((contract, plan, receipt))
        self.assertIn("TASK_DEPENDENCY_EVIDENCE_STALE", codes)
        self.assertIn("TASK_DEPENDENCY_SIGNAL_INCOMPLETE", codes)

    def test_specialized_exception_requires_complete_risk_acceptance(self) -> None:
        contract, plan, receipt = dependency_bundle(selection_class="specialized-exception")
        self.assertIn(
            "TASK_DEPENDENCY_EXCEPTION_INCOMPLETE",
            self.codes((contract, plan, receipt)),
        )

    def test_complete_specialized_exception_passes(self) -> None:
        contract, plan, receipt = dependency_bundle(selection_class="specialized-exception")
        selected = receipt["decisions"][0]["candidates"][0]
        selected["risks"] = ["Smaller adoption baseline."]
        baseline = candidate(
            "github.com/gin-gonic/gin",
            "https://github.com/gin-gonic/gin",
            "ecosystem-mainstream",
            disposition="baseline",
            key="mainstream",
        )
        receipt["decisions"][0]["candidates"].append(baseline)
        receipt["decisions"][0]["exception"] = {
            "mainstream_baseline_key": "mainstream",
            "unmet_requirement_ids": ["REQ-01"],
            "why_baseline_fails": "The mainstream baseline cannot satisfy REQ-01.",
            "accepted_risks": ["Lower adoption."],
            "mitigations": ["Pin and validate the selected implementation."],
            "rollback": "Return to the mainstream baseline.",
            "user_acceptance_required": True,
        }
        self.assertEqual(set(), self.codes((contract, plan, receipt)))


if __name__ == "__main__":
    unittest.main()

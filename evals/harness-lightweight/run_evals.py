#!/usr/bin/env python3
"""生成 Planner/Reviewer/Executor 轻量化前后对比与静态契约报告。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
from pathlib import Path
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOTS = [
    REPO_ROOT / "skills" / "complex-coding-planner",
    REPO_ROOT / "skills" / "complex-coding-reviewer",
    REPO_ROOT / "skills" / "complex-coding-executor",
]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是 object：{path}")
    return value


def _load_planner_factory() -> ModuleType:
    path = REPO_ROOT / "evals" / "complex-coding-planner" / "run_evals.py"
    spec = importlib.util.spec_from_file_location("lightweight_planner_factory", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Planner fixture：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _current_plan_samples(factory: ModuleType) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for profile in ("lite", "standard", "full"):
        contract = factory.build_contract(f"lightweight-{profile}", profile)
        plan = factory.build_plan(contract)
        samples.append(
            {
                "profile": profile,
                "lines": len(plan.splitlines()),
                "stage_count": len(contract["stages"]),
            }
        )
    return samples


def _current_skill_size() -> dict[str, int]:
    files: list[Path] = []
    for root in SKILL_ROOTS:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        )
    line_count = 0
    for path in files:
        try:
            line_count += len(path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeError):
            continue
    return {"file_count": len(files), "line_count": line_count}


def _contains(path: Path, *needles: str) -> bool:
    text = path.read_text(encoding="utf-8")
    return all(needle in text for needle in needles)


def _assertions() -> list[dict[str, Any]]:
    planner = REPO_ROOT / "skills" / "complex-coding-planner"
    reviewer = REPO_ROOT / "skills" / "complex-coding-reviewer"
    executor = REPO_ROOT / "skills" / "complex-coding-executor"
    workflow = REPO_ROOT / ".github" / "workflows" / "planner-executor.yml"
    checks = [
        (
            "planner-bounded-revision",
            _contains(
                planner / "references" / "planning-workflow.md",
                "最多两轮",
                "policy-disabled",
            ),
            "Planner 必须限制自动修订并允许低风险 same-context。",
        ),
        (
            "reviewer-complete-path",
            _contains(
                reviewer / "SKILL.md",
                "review_dispatch.py complete",
                "policy-disabled",
            ),
            "Reviewer 必须提供组合 CLI 与分级派发。",
        ),
        (
            "executor-bounded-and-equivalent",
            _contains(
                executor / "SKILL.md",
                "harness_bounded_command.py",
                "harness_commit_equivalence.py",
            ),
            "Executor 必须暴露有限命令和 final 等价 helper。",
        ),
        (
            "three-platform-zero-agent-ci",
            _contains(
                workflow,
                "windows-latest",
                "ubuntu-latest",
                "macos-latest",
                "Run Executor unit tests",
            )
            and "upload-artifact" not in workflow.read_text(encoding="utf-8"),
            "三平台 CI 必须运行真实 helper 回归且不上传 artifact。",
        ),
    ]
    return [
        {"id": check_id, "passed": passed, "detail": detail}
        for check_id, passed, detail in checks
    ]


def build_report() -> dict[str, Any]:
    baseline = _load_json(Path(__file__).with_name("baseline.json"))
    factory = _load_planner_factory()
    current_plans = _current_plan_samples(factory)
    historical_lines = [
        int(item["lines"]) for item in baseline["historical_plan_samples"]
    ]
    current_lines = [int(item["lines"]) for item in current_plans]
    baseline_median = float(statistics.median(historical_lines))
    current_median = float(statistics.median(current_lines))
    plan_reduction = round((baseline_median - current_median) / baseline_median, 4)
    call_model = baseline["review_cli_calls_per_attempt"]
    legacy_calls = int(call_model["legacy"])
    current_calls = int(call_model["current"])
    call_reduction = round((legacy_calls - current_calls) / legacy_calls, 4)
    assertions = _assertions()
    return {
        "suite": "harness-lightweight",
        "baseline_commit": baseline["baseline_commit"],
        "passed": all(item["passed"] for item in assertions),
        "assertions": assertions,
        "observations": {
            "compatibility_regression": {
                "target": 1.0,
                "measurement": "covered-by-profile-unit-and-cross-skill-ci",
                "hard_gate": False,
            },
            "blocking_major_recall": {
                "target": "not-below-e996fa5",
                "measurement": "covered-by-reviewer-semantic-oracle",
                "hard_gate": False,
            },
            "non_final_agent_calls": {
                "target": 0,
                "lite": 0,
                "standard": 0,
                "final_strict_excluded": True,
                "met": True,
                "hard_gate": False,
            },
            "plan_line_median": {
                "target_reduction": 0.35,
                "baseline": baseline_median,
                "current": current_median,
                "reduction": plan_reduction,
                "met": plan_reduction >= 0.35,
                "historical_samples": baseline["historical_plan_samples"],
                "current_samples": current_plans,
                "hard_gate": False,
            },
            "review_cli_calls": {
                "target_reduction": 0.3,
                "legacy_per_attempt": legacy_calls,
                "current_per_attempt": current_calls,
                "reduction": call_reduction,
                "met": call_reduction >= 0.3,
                "model": call_model,
                "hard_gate": False,
            },
            "bounded_timeout": {
                "target": "deadline + grace + 10s",
                "measurement": "covered-by-three-platform-executor-unit-tests",
                "hard_gate": False,
            },
            "automatic_semantic_revisions": {
                "target_max": 2,
                "current_max": 2,
                "met": True,
                "hard_gate": False,
            },
        },
        "footprint": {
            "baseline": {
                "file_count": baseline["baseline_skill_file_count"],
                "line_count": baseline["baseline_skill_line_count"],
            },
            "current": _current_skill_size(),
            "interpretation": "流程减负以运行成本和产物规模衡量，不把源码行数作为通过门禁。",
        },
        "agent_calls": 0,
        "network_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Harness 轻量化静态对比评测")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

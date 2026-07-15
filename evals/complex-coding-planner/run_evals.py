#!/usr/bin/env python3
"""执行 planner capability/regression task bundle 评测。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PLAN_SECTIONS = [
    "规划摘要",
    "问题定义",
    "需求与验收",
    "调研门禁",
    "依赖选型门禁",
    "规范发现门禁",
    "开发质量门禁",
    "上下文",
    "候选方案",
    "决策",
    "影响面矩阵",
    "实施计划",
    "环境",
    "Git 上下文",
    "工具",
    "长期进程管理",
    "验证",
    "文档",
    "文件写入策略",
    "方案质量门禁",
    "规划自查",
    "就绪门禁",
    "方案批准",
    "方案变更门禁",
    "Artifact Index",
    "Executor Handoff",
]

STATIC_GATE_BODIES = {
    "依赖选型门禁": (
        "- Selection mode: `none`\n"
        "- Dependency selection result: `not-applicable`"
    ),
    "规范发现门禁": (
        "- Standards result: `passed`\n"
        "- Decision: Use repository Python and closed JSON standards.\n"
        "- Evidence: REQ-01, STG-01 and project rules.\n"
        "- Impact: VAL-01 verifies structure and quality."
    ),
    "开发质量门禁": (
        "- Development quality result: `passed`\n"
        "- Decision: Keep cohesive modules and bounded interfaces.\n"
        "- Evidence: STG-01 scope and VAL-01.\n"
        "- Impact: Review covers architecture and static quality."
    ),
    "方案质量门禁": (
        "- Quality result: `passed`\n"
        "- Decision: Requirements, stages and validation are closed.\n"
        "- Evidence: REQ-01, AC-01, STG-01 and VAL-01.\n"
        "- Impact: The approved bundle is deterministic."
    ),
    "规划自查": (
        "- Review result: `passed`\n"
        "- Decision: No contradiction, scope leak or blocker remains.\n"
        "- Evidence: STG-01 and VAL-01 traceability.\n"
        "- Impact: Failures remain reviewable and recoverable."
    ),
    "就绪门禁": (
        "- Readiness result: `ready_for_approval`\n"
        "- Decision: Scope, tools and authorization request are explicit.\n"
        "- Evidence: STG-01, VAL-01 and approval policy.\n"
        "- Impact: Request approval without implementation."
    ),
}


def artifact_specs(profile: str) -> list[dict[str, Any]]:
    if profile == "lite":
        return []
    kinds = ["architecture"] if profile == "standard" else [
        "research",
        "standards",
        "architecture",
        "validation",
        "review",
    ]
    paths = {
        "research": "artifacts/research/findings.md",
        "standards": "artifacts/standards/index.md",
        "architecture": "artifacts/architecture/change-map.md",
        "validation": "artifacts/validation/traceability.md",
        "review": "artifacts/reviews/plan-critique.md",
    }
    return [
        {
            "id": f"ART-{index:02d}",
            "kind": kind,
            "path": paths[kind],
            "required": True,
            "approval_included": True,
        }
        for index, kind in enumerate(kinds, start=1)
    ]


def build_contract(case_id: str, profile: str) -> dict[str, Any]:
    stage_counts = {"lite": 1, "standard": 2, "full": 3}
    stages: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    for index in range(1, stage_counts[profile] + 1):
        stage_id = f"STG-{index:02d}"
        validation_id = f"VAL-{index:02d}"
        stages.append(
            {
                "id": stage_id,
                "title": f"Stage {index}",
                "depends_on": [] if index == 1 else [f"STG-{index - 1:02d}"],
                "requirement_ids": ["REQ-01"],
                "acceptance_ids": ["AC-01"],
                "nonfunctional_ids": ["NFR-01"],
                "validation_ids": [validation_id],
                "allowed_changes": [f"module-{index}/"],
                "forbidden_changes": ["unrelated/"],
                "entry_conditions": ["dependencies complete"],
                "exit_conditions": ["validation and review pass"],
                "risk": "high" if profile == "full" and index == 1 else "medium",
                "commit_expectation": "final",
            }
        )
        validations.append(
            {
                "id": validation_id,
                "kind": "test",
                "required": True,
                "covers": ["AC-01", "NFR-01"],
                "command": f"run test {index}",
                "evidence_path": f"artifacts/validation/{validation_id.lower()}.md",
            }
        )
    artifacts = artifact_specs(profile)
    research_ids = [item["id"] for item in artifacts if item["kind"] == "research"]
    return {
        "task_id": case_id,
        "plan_revision": 1,
        "lifecycle_route": "managed",
        "plan_profile": profile,
        "goal": {"id": "GOAL-01", "summary": "Produce a validated result"},
        "requirements": [
            {"id": "REQ-01", "priority": "must", "summary": "Implement behavior"}
        ],
        "acceptance_criteria": [
            {
                "id": "AC-01",
                "requirement_ids": ["REQ-01"],
                "summary": "Given input When executed Then result is correct",
            }
        ],
        "nonfunctional_requirements": [
            {"id": "NFR-01", "summary": "Keep implementation maintainable"}
        ],
        "artifacts": artifacts,
        "stages": stages,
        "validations": validations,
        "dependency_selection": {
            "mode": "none",
            "necessity_result": "not-triggered",
            "decision_ids": [],
            "evidence_artifact_ids": [],
            "decisions": [],
        },
        "research": {
            "mode": "online-required" if profile == "full" else "local-only",
            "evidence_artifact_ids": research_ids,
            "unresolved": [],
        },
        "approval_policy": {
            "implementation_requires_user_approval": True,
            "commit_requires_explicit_authorization": True,
            "external_write_requires_explicit_authorization": True,
            "elevated_tool_requires_explicit_authorization": True,
        },
        "reapproval_triggers": ["scope or required validation changes"],
        "stop_conditions": ["user pause or reapproval required"],
    }


def build_plan(contract: dict[str, Any]) -> str:
    ids = ["GOAL-01", "REQ-01", "AC-01", "NFR-01"]
    ids.extend(item["id"] for item in contract["validations"])
    ids.extend(item["id"] for item in contract["artifacts"])

    def render_stage(stage: dict[str, Any]) -> str:
        references = [
            *stage["depends_on"],
            *stage["requirement_ids"],
            *stage["acceptance_ids"],
            *stage["nonfunctional_ids"],
            *stage["validation_ids"],
            *stage["allowed_changes"],
            *stage["forbidden_changes"],
        ]
        return f"### {stage['id']}：{stage['title']}\n{' '.join(references)}"

    sections = ["# Eval Plan"]
    for heading in PLAN_SECTIONS:
        body = STATIC_GATE_BODIES.get(heading, "passed")
        if heading == "规划摘要":
            body = (
                f"Task ID: {contract['task_id']}\n\n"
                f"Plan revision: {contract['plan_revision']}\n\n"
                f"Lifecycle route: {contract['lifecycle_route']}\n\n"
                f"Plan profile: {contract['plan_profile']}"
            )
        elif heading == "问题定义":
            body = "GOAL-01"
        elif heading == "需求与验收":
            body = " ".join(ids[1:4])
        elif heading == "调研门禁":
            research_result = (
                "passed"
                if contract["research"]["mode"] == "online-required"
                else "not-applicable"
            )
            research_ids = contract["research"]["evidence_artifact_ids"]
            research_evidence = research_ids[0] if research_ids else "REQ-01"
            body = (
                f"- Research result: `{research_result}`\n"
                "- Decision: Evidence scope matches the task uncertainty.\n"
                f"- Evidence: {research_evidence} with VAL-01 traceability.\n"
                "- Impact: STG-01 follows the recorded source limits."
            )
        elif heading == "候选方案":
            body = "### 方案 A\nMinimal\n\n### 方案 B\nStructured"
        elif heading == "实施计划":
            body = "\n\n".join(render_stage(stage) for stage in contract["stages"])
        elif heading == "Artifact Index":
            body = " ".join(item["id"] for item in contract["artifacts"]) or "none"
        elif heading == "方案批准":
            body = "Status: not requested; commit authorization requested separately"
        elif heading == "Executor Handoff":
            body = "Planner checker: approval mode; no open blocker"
        sections.append(f"## {heading}\n\n{body}")
    return "\n\n".join(sections) + "\n"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_artifacts(
    task_dir: Path,
    contract: dict[str, Any],
    *,
    include_online_source: bool,
) -> None:
    for artifact in contract["artifacts"]:
        path = task_dir / artifact["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        body = (
            f"# {artifact['kind'].title()} Evidence\n\n"
            f"Artifact ID: {artifact['id']}\n\n"
            "Status: complete\n"
        )
        if artifact["kind"] == "research" and include_online_source:
            body += (
                "\nPrimary official source: https://example.com/official-spec\n"
                "Observed: 2026-07-15\n"
                "Evidence window: 12m\n"
                f"Artifact receipt: {artifact['id']} artifacts/research/findings.md\n"
                "Applicability and impact: applies to the planned API boundary.\n"
            )
        if artifact["kind"] == "review":
            body += "\nOpen blocking findings: none\nReady for approval: yes\n"
        path.write_text(body, encoding="utf-8")


def apply_mutation(
    task_dir: Path,
    contract: dict[str, Any],
    mutation: str,
) -> None:
    if mutation == "none":
        return
    if mutation == "missing-contract":
        (task_dir / "plan-contract.json").unlink()
        return
    if mutation == "broken-reference":
        contract["stages"][0]["requirement_ids"] = ["REQ-99"]
    elif mutation == "cyclic-stage":
        contract["stages"][0]["depends_on"] = [contract["stages"][0]["id"]]
    elif mutation == "mutable-plan-section":
        plan_path = task_dir / "execution-plan.md"
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8") + "\n## 实施进度\n\nrunning\n",
            encoding="utf-8",
        )
    elif mutation == "open-decision":
        (task_dir / "pending-decisions.md").write_text(
            "# Pending Decisions\n\n状态: open\n",
            encoding="utf-8",
        )
    elif mutation == "review-gate-incomplete":
        review = next(
            item for item in contract["artifacts"] if item["kind"] == "review"
        )
        (task_dir / review["path"]).write_text(
            "# Plan Critique\n\nOpen blocking findings: pending\n",
            encoding="utf-8",
        )
    elif mutation == "empty-semantic-gate":
        plan_path = task_dir / "execution-plan.md"
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8").replace(
                STATIC_GATE_BODIES["方案质量门禁"],
                "- Quality result: `passed`",
            ),
            encoding="utf-8",
        )
    elif mutation == "url-only-semantic-gate":
        plan_path = task_dir / "execution-plan.md"
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8").replace(
                STATIC_GATE_BODIES["方案质量门禁"],
                "- Quality result: `passed`\n"
                "- https://example.com/one\n"
                "- https://example.com/two\n"
                "- https://example.com/three",
            ),
            encoding="utf-8",
        )
    elif mutation == "dependency-mode-drift":
        plan_path = task_dir / "execution-plan.md"
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8").replace(
                "Selection mode: `none`",
                "Selection mode: `change`",
            ),
            encoding="utf-8",
        )
    elif mutation != "online-source-missing":
        raise ValueError(f"未知 mutation：{mutation}")
    if mutation in {"broken-reference", "cyclic-stage"}:
        write_json(task_dir / "plan-contract.json", contract)


def build_case(task_root: Path, case: dict[str, Any]) -> Path:
    task_dir = task_root / case["id"]
    task_dir.mkdir(parents=True)
    contract = build_contract(case["id"], case["profile"])
    write_json(task_dir / "plan-contract.json", contract)
    (task_dir / "execution-plan.md").write_text(
        build_plan(contract),
        encoding="utf-8",
    )
    write_artifacts(
        task_dir,
        contract,
        include_online_source=case["mutation"] != "online-source-missing",
    )
    apply_mutation(task_dir, contract, case["mutation"])
    return task_dir


def run_checker(repo_root: Path, task_dir: Path) -> tuple[int, dict[str, Any]]:
    checker = (
        repo_root
        / "skills"
        / "complex-coding-planner"
        / "scripts"
        / "harness_plan_check.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            str(checker),
            "--task-dir",
            str(task_dir),
            "--mode",
            "approval",
            "--format",
            "json",
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"checker 未返回 JSON：stdout={result.stdout!r}, stderr={result.stderr!r}"
        ) from exc
    return result.returncode, payload


def evaluate_case(
    repo_root: Path,
    task_root: Path,
    suite: str,
    case: dict[str, Any],
) -> dict[str, Any]:
    task_dir = build_case(task_root, case)
    returncode, payload = run_checker(repo_root, task_dir)
    actual_valid = payload.get("valid") is True
    codes = [
        issue.get("code")
        for issue in payload.get("issues", [])
        if isinstance(issue, dict) and isinstance(issue.get("code"), str)
    ]
    expected_valid = case["expected_valid"]
    expected_code = case.get("expected_code")
    validity_matches = actual_valid == expected_valid
    exit_matches = returncode == (0 if actual_valid else 1)
    code_matches = expected_code is None or expected_code in codes
    plan_path = task_dir / "execution-plan.md"
    plan_lines = len(plan_path.read_text(encoding="utf-8").splitlines())
    return {
        "id": case["id"],
        "suite": suite,
        "profile": case["profile"],
        "mutation": case["mutation"],
        "expected_valid": expected_valid,
        "actual_valid": actual_valid,
        "expected_code": expected_code,
        "actual_codes": codes,
        "checker_exit_code": returncode,
        "plan_lines": plan_lines,
        "artifact_count": len(list((task_dir / "artifacts").rglob("*.md")))
        if (task_dir / "artifacts").exists()
        else 0,
        "passed": validity_matches and exit_matches and code_matches,
    }


def load_cases(manifest_path: Path) -> list[tuple[str, dict[str, Any]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases: list[tuple[str, dict[str, Any]]] = []
    for suite in ("capability", "regression"):
        values = manifest.get(suite)
        if not isinstance(values, list):
            raise ValueError(f"manifest.{suite} 必须是数组。")
        for case in values:
            if not isinstance(case, dict):
                raise ValueError(f"manifest.{suite} 中的 case 必须是 object。")
            cases.append((suite, case))
    return cases


def build_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    profile_counts = {
        profile: sum(item["profile"] == profile for item in results)
        for profile in ("lite", "standard", "full")
    }
    total = len(results)
    passed = sum(item["passed"] for item in results)
    return {
        "suite": "complex-coding-planner",
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "metrics": {
            "profile_case_counts": profile_counts,
            "capability_cases": sum(item["suite"] == "capability" for item in results),
            "regression_cases": sum(item["suite"] == "regression" for item in results),
            "average_plan_lines": round(
                sum(item["plan_lines"] for item in results) / total,
                2,
            )
            if total
            else 0,
        },
        "results": results,
    }


def main() -> int:
    default_manifest = Path(__file__).with_name("manifest.json")
    parser = argparse.ArgumentParser(description="运行 planner task bundle 评测")
    parser.add_argument("--manifest", type=Path, default=default_manifest)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).parents[2])
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.work_dir) as temporary:
        task_root = Path(temporary)
        results = [
            evaluate_case(args.repo_root.resolve(), task_root, suite, case)
            for suite, case in load_cases(args.manifest.resolve())
        ]
    report = build_report(results)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

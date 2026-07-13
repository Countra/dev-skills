"""合并静态、语义与用户观察证据，不替当前 Agent 下结论。"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import (
    SCHEMA_VERSION,
    validate_imported_observation,
    validate_semantic_review,
    validate_static_evidence,
)
from .errors import ReportError
from .paths import resolve_input, resolve_workspace, source_identity


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item["status"]) for item in items)
    return {name: counts.get(name, 0) for name in ("pass", "warn", "fail", "not_applicable")}


def _validate_compatibility(
    static: dict[str, Any],
    review: dict[str, Any],
    observation: dict[str, Any] | None,
) -> None:
    if review["evaluation_id"] != static["evaluation_id"]:
        raise ReportError(
            "semantic review 与 static evidence 的 evaluation_id 不一致",
            code="REPORT_EVALUATION_MISMATCH",
            path="$.evaluation_id",
        )
    candidate_hash = static["candidate"]["tree_sha256"]
    if review["candidate_tree_sha256"] != candidate_hash:
        raise ReportError(
            "semantic review 与 candidate source hash 不一致",
            code="REPORT_REVIEW_SOURCE_MISMATCH",
            path="$.candidate_tree_sha256",
        )
    candidate_files = {item["path"] for item in static["candidate"]["files"]}
    for dimension in review["dimensions"]:
        for evidence in dimension["evidence"]:
            if evidence["path"] not in candidate_files:
                raise ReportError(
                    "semantic evidence path 不属于 candidate source",
                    code="REPORT_REVIEW_EVIDENCE_UNKNOWN",
                    path=evidence["path"],
                )
    decision = review["observation_decision"]
    if observation is not None:
        if decision != "provided":
            raise ReportError(
                "已提供 observation 时 review 必须声明 provided",
                code="REPORT_OBSERVATION_DECISION_MISMATCH",
                path="$.observation_decision",
            )
        if observation["candidate_tree_sha256"] != candidate_hash:
            raise ReportError(
                "observation 与 candidate source hash 不一致",
                code="REPORT_OBSERVATION_SOURCE_MISMATCH",
                path="$.candidate_tree_sha256",
            )
        baseline_hash = (
            static["baseline"]["tree_sha256"]
            if static["baseline"] is not None
            else None
        )
        if observation["baseline_tree_sha256"] != baseline_hash:
            raise ReportError(
                "observation 与 baseline source hash 不一致",
                code="REPORT_OBSERVATION_BASELINE_MISMATCH",
                path="$.baseline_tree_sha256",
            )
    elif decision == "provided":
        raise ReportError(
            "review 声明 provided，但未提供 imported observation",
            code="REPORT_OBSERVATION_MISSING",
            path="$.observation_decision",
        )


def verify_current_sources(
    workspace: Path,
    static: dict[str, Any],
) -> tuple[Path, ...]:
    """在报告生成前重新计算当前 candidate/baseline，拒绝陈旧证据。"""
    workspace = resolve_workspace(workspace)
    validate_static_evidence(static)
    sources: list[Path] = []
    for variant in ("candidate", "baseline"):
        binding = static[variant]
        if binding is None:
            continue
        source = resolve_input(
            workspace,
            Path(binding["path"]),
            label=f"report {variant} source",
            expect="directory",
        )
        current = source_identity(workspace, source)
        if current["tree_sha256"] != binding["tree_sha256"]:
            raise ReportError(
                f"{variant} source 已变化，当前报告证据失效",
                code="REPORT_SOURCE_DRIFT",
                path=binding["path"],
                guidance="重新生成 static evidence、semantic review 和相关 observation。",
            )
        sources.append(source)
    return tuple(sources)


def _observed_coverage(
    decision: str,
    observation: dict[str, Any] | None,
) -> dict[str, Any]:
    if observation is None:
        return {
            "status": "not_requested" if decision == "not_requested" else "not_observed",
            "expected": 0,
            "observed": 0,
            "missing": 0,
            "session_statuses": {"pass": 0, "fail": 0, "inconclusive": 0},
        }
    session_counts = Counter(str(item["status"]) for item in observation["sessions"])
    coverage = observation["coverage"]
    return {
        "status": coverage["status"],
        "expected": len(coverage["expected"]),
        "observed": len(coverage["observed"]),
        "missing": len(coverage["missing"]),
        "session_statuses": {
            name: session_counts.get(name, 0)
            for name in ("pass", "fail", "inconclusive")
        },
    }


def _claim_boundaries(
    observed: dict[str, Any],
    runtime_claims_allowed: bool,
) -> list[str]:
    boundaries = [
        "静态检查只证明 source-bound 机械事实和能力信号，不证明真实运行行为。",
        "七维语义审查是当前 Agent 的设计判断，必须保留 assumptions 与 limitations。",
    ]
    if runtime_claims_allowed:
        boundaries.append("运行时表述仅限已导入且完整覆盖的 case/variant，不得外推总体触发率。")
    elif observed["status"] == "partial":
        boundaries.append("用户观察覆盖不完整，只能陈述已导入 session，不能形成整体运行时结论。")
    else:
        boundaries.append("缺少完整、结论明确的用户观察，不得声明真实触发率或行为提升。")
    return boundaries


def build_report(
    static: dict[str, Any],
    review: dict[str, Any],
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_static_evidence(static)
    validate_semantic_review(review)
    if observation is not None:
        validate_imported_observation(observation)
    _validate_compatibility(static, review, observation)
    static_findings = [item for item in static["checks"] if item["status"] in {"warn", "fail"}]
    semantic_findings = [item for item in review["dimensions"] if item["status"] in {"warn", "fail"}]
    observed = _observed_coverage(review["observation_decision"], observation)
    runtime_claims_allowed = (
        observation is not None
        and observed["status"] == "complete"
        and observed["session_statuses"]["inconclusive"] == 0
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_id": static["evaluation_id"],
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "target": {
            "path": static["candidate"]["path"],
            "tree_sha256": static["candidate"]["tree_sha256"],
        },
        "evidence_coverage": {
            "static": {"status": "complete", "check_statuses": _status_counts(static["checks"])},
            "semantic": {
                "status": "complete",
                "dimension_statuses": _status_counts(review["dimensions"]),
            },
            "observed": observed,
        },
        "findings": {
            "static": static_findings,
            "semantic": semantic_findings,
            "observed": observation["sessions"] if observation else [],
        },
        "assumptions": list(review["assumptions"]),
        "limitations": list(review["limitations"]),
        "runtime_claims_allowed": runtime_claims_allowed,
        "claim_boundaries": _claim_boundaries(observed, runtime_claims_allowed),
        "completion": {
            "ready_for_agent_conclusion": True,
            "conclusion_owner": "current_agent",
            "script_generated_conclusion": False,
        },
    }
    if "overall_score" in report:
        raise ReportError("报告禁止单一 overall score", code="REPORT_SCORE_FORBIDDEN")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report["evidence_coverage"]
    lines = [
        "# Skill Evaluation Evidence Report",
        "",
        "## Target",
        "",
        f"- Evaluation：`{report['evaluation_id']}`",
        f"- Path：`{report['target']['path']}`",
        f"- Tree SHA-256：`{report['target']['tree_sha256']}`",
        "",
        "## Evidence Coverage",
        "",
        f"- Static：`{coverage['static']['status']}` {coverage['static']['check_statuses']}",
        f"- Semantic：`{coverage['semantic']['status']}` {coverage['semantic']['dimension_statuses']}",
        f"- Observed：`{coverage['observed']['status']}` "
        f"({coverage['observed']['observed']}/{coverage['observed']['expected']})",
        "",
        "## 已证明",
        "",
    ]
    static_findings = report["findings"]["static"]
    lines.extend(
        [f"- `{item['id']}` [{item['status']}] {item['summary']}" for item in static_findings]
        or ["- 静态层没有 warn/fail finding。"]
    )
    lines.extend(["", "## 审查判断", ""])
    semantic_findings = report["findings"]["semantic"]
    lines.extend(
        [
            f"- `{item['dimension']}` [{item['status']}] {item['summary']}"
            for item in semantic_findings
        ]
        or ["- 七个语义维度没有 warn/fail finding。"]
    )
    lines.extend(["", "## 用户观察", ""])
    observed_findings = report["findings"]["observed"]
    lines.extend(
        [
            f"- `{item['case_id']}::{item['variant']}` [{item['status']}] {item['notes']}"
            for item in observed_findings
        ]
        or ["- 尚未导入用户独立会话观察。"]
    )
    lines.extend(["", "## 假设与限制", ""])
    lines.extend(
        [f"- 假设：{item}" for item in report["assumptions"]]
        or ["- 假设：无。"]
    )
    lines.extend(f"- 限制：{item}" for item in report["limitations"])
    lines.extend(["", "## 声明边界", ""])
    lines.extend(f"- {item}" for item in report["claim_boundaries"])
    lines.extend(
        [
            "",
            "## 当前 Agent 后续动作",
            "",
            "读取完整证据后，由当前 Agent 给出结论、置信边界、问题优先级和优化建议。",
            "报告脚本不会生成最终判断。",
            "",
        ]
    )
    return "\n".join(lines)
